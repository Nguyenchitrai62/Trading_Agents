from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.messages import AIMessage

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    LLM_INVOKE_LOCK,
)
from tradingagents.agents.utils.evidence import (
    get_structured_evidence_instruction,
    split_report_and_evidence,
)
from tradingagents.agents.utils.structured import resolve_structured_base_llm
from tradingagents.dataflows.ccxt_crypto import get_crypto_bundle
from tradingagents.dataflows.config import get_config
from tradingagents.llm_clients.base_client import normalize_content


MARKET_INDICATORS = (
    "close_10_ema",
    "close_50_sma",
    "close_200_sma",
    "rsi",
    "macd",
    "boll",
    "atr",
    "vwma",
    "mfi",
)

MARKET_TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w"]
TIMEFRAME_PREVIEW_LIMITS = {"15m": 200, "1h": 200, "4h": 200, "1d": 200, "1w": 50}

_MAX_TOOL_BLOCK_CHARS = 4000
_MAX_MARKET_CONTEXT_CHARS = 40000


def _response_text(response: object) -> str:
    normalized = normalize_content(response)
    content = getattr(normalized, "content", "")
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content).strip()


def _trim(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 14)].rstrip() + "\n[truncated]"


def _emit_market_tool_trace(phase: str, title: str, trace_id: str, content: object) -> None:
    callback = get_config().get("analysis_trace_callback")
    if not callable(callback):
        return
    callback(
        {
            "agent": "Market Analyst",
            "phase": phase,
            "title": title,
            "trace_id": trace_id,
            "content": content,
        }
    )


def _collect_tf_bundle(symbol: str, tf: str, preview_limit: int) -> dict:
    _emit_market_tool_trace(
        "tool_call",
        f"get_crypto_ohlcv:{tf}",
        f"market:ohlcv:{tf}",
        f"get_crypto_ohlcv({symbol}, {tf}, preview_limit={preview_limit})",
    )
    _emit_market_tool_trace(
        "tool_call",
        f"get_crypto_indicators:{tf}",
        f"market:indicators:{tf}",
        f"get_crypto_indicators({symbol}, {tf}, preview_limit={preview_limit})",
    )
    try:
        bundle = get_crypto_bundle(symbol, tf, preview_limit=preview_limit, exchange_name="binance")
        ohlcv_md = _trim(bundle.get("ohlcv", ""), _MAX_TOOL_BLOCK_CHARS)
        indicators = bundle.get("indicators") or {}
        indicator_lines = [f"# Indicators for {symbol} ({tf})", "", f"Computed indicators: {len(indicators)} items", ""]
        for name in MARKET_INDICATORS:
            if name in indicators:
                indicator_lines.append(_trim(indicators[name], _MAX_TOOL_BLOCK_CHARS))
                indicator_lines.append("")
        indicators_md = _trim("\n".join(indicator_lines), _MAX_MARKET_CONTEXT_CHARS)
        _emit_market_tool_trace("tool_result", f"get_crypto_ohlcv:{tf}", f"market:ohlcv:{tf}", ohlcv_md)
        _emit_market_tool_trace("tool_result", f"get_crypto_indicators:{tf}", f"market:indicators:{tf}", indicators_md)
        return bundle
    except Exception as exc:
        _emit_market_tool_trace("tool_result", f"get_crypto_ohlcv:{tf}", f"market:ohlcv:{tf}", f"Error: {exc}")
        _emit_market_tool_trace("tool_result", f"get_crypto_indicators:{tf}", f"market:indicators:{tf}", f"Error: {exc}")
        raise


def _format_tf_context(bundle: dict, tf: str) -> str:
    lines = [
        f"# {tf} Timeframe Data",
        "",
        "## OHLCV",
        _trim(bundle.get("ohlcv", ""), _MAX_TOOL_BLOCK_CHARS),
    ]
    indicators = bundle.get("indicators") or {}
    for name in MARKET_INDICATORS:
        if name in indicators:
            lines.extend(["", f"## Indicator: {name}", _trim(indicators[name], _MAX_TOOL_BLOCK_CHARS)])
    return _trim("\n".join(lines), _MAX_MARKET_CONTEXT_CHARS)


def _run_tf_agent(
    base_llm,
    symbol: str,
    tf: str,
    preview_limit: int,
    current_date: str,
    instrument_context: str,
) -> dict:
    bundle = _collect_tf_bundle(symbol, tf, preview_limit)
    tf_context = _format_tf_context(bundle, tf)

    _emit_market_tool_trace(
        "analysis",
        f"TF {tf} analyzing",
        f"market:llm:{tf}",
        f"Analyzing {symbol} on {tf} timeframe ({len(tf_context)} chars context)...",
    )

    prompt = f"""You are the Market Analyst for timeframe {tf}.

{instrument_context}
Current analysis date: {current_date}

The backend has collected CCXT OHLCV candles and technical indicators for the {tf} timeframe.
Do not use web search. Analyze only the {tf} data below.

{tf} Data:
{tf_context}

Produce a concise {tf} timeframe report covering:
1. Trend and market structure on {tf}.
2. Key support/resistance levels visible on {tf}.
3. Momentum signals (RSI, MACD) and their implications on this timeframe.
4. Volume and volatility observations.
5. A brief directional bias (bullish/bearish/neutral) with confidence level.

Keep the report focused on what the {tf} timeframe reveals. Preserve concrete values from the tool outputs.
{get_language_instruction()}"""

    with LLM_INVOKE_LOCK:
        raw_report = _response_text(base_llm.invoke(prompt))

    _emit_market_tool_trace(
        "analysis",
        f"TF {tf} complete",
        f"market:llm:{tf}",
        f"Completed {tf} analysis ({len(raw_report)} chars).",
    )

    return {"timeframe": tf, "report": raw_report, "bundle": bundle}


def create_market_analyst(llm):
    base_llm = resolve_structured_base_llm(llm)

    def market_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "crypto")
        symbol = state["company_of_interest"]
        instrument_context = build_instrument_context(symbol, asset_type)

        tf_results: dict[str, str] = {}
        tf_bundles: dict[str, dict] = {}

        with ThreadPoolExecutor(max_workers=len(MARKET_TIMEFRAMES)) as executor:
            futures = {}
            for tf in MARKET_TIMEFRAMES:
                preview_limit = TIMEFRAME_PREVIEW_LIMITS[tf]
                future = executor.submit(
                    _run_tf_agent,
                    base_llm,
                    symbol,
                    tf,
                    preview_limit,
                    current_date,
                    instrument_context,
                )
                futures[future] = tf

            for future in as_completed(futures):
                tf = futures[future]
                try:
                    result = future.result()
                    tf_results[tf] = result["report"]
                    tf_bundles[tf] = result["bundle"]
                    _emit_market_tool_trace(
                        "analysis",
                        f"TF {tf} received",
                        f"market:tf_done:{tf}",
                        f"{tf} analysis finished ({len(result['report'])} chars).",
                    )
                except Exception as exc:
                    tf_results[tf] = f"[{tf} analysis unavailable: {exc}]"
                    _emit_market_tool_trace(
                        "analysis",
                        f"TF {tf} failed",
                        f"market:tf_done:{tf}",
                        f"Error: {exc}",
                    )

        if not tf_bundles:
            raise RuntimeError(
                f"Market Analyst failed: no timeframe data could be fetched for {symbol}. "
                f"Timeframes attempted: {MARKET_TIMEFRAMES}"
            )

        synthesis_prompt = f"""You are the Multi-Timeframe Market Analyst synthesizing reports from sub-analysts across multiple timeframes.

{instrument_context}
Current analysis date: {current_date}

Each sub-analyst has independently analyzed {symbol} on their assigned timeframe using CCXT OHLCV candles and technical indicators. Synthesize their findings into a single unified market report.

--- Timeframe Reports ---"""
        for tf in MARKET_TIMEFRAMES:
            report = tf_results.get(tf, f"[{tf}: no data available]")
            synthesis_prompt += f"\n### {tf} Timeframe\n{report}\n"

        synthesis_prompt += f"""
---
Synthesize into a unified market report covering:
1. Multi-timeframe trend alignment: Where do timeframes agree or disagree on market direction?
2. Key divergences: Are shorter timeframes showing reversal or counter-trend signals that contradict higher timeframes?
3. Confluence zones: Price levels or ranges supported by multiple timeframes (strong support/resistance).
4. Overall market structure: The dominant trend across all timeframes after reconciling conflicts.
5. Momentum/volume confirmation: Which timeframes show the strongest momentum, and is it confirmed by volume?
6. Confidence and data caveats: Note any timeframes with missing data and the impact on the analysis.
7. A markdown table summarizing the highest-signal multi-timeframe findings with concrete values.

{get_language_instruction()}{get_structured_evidence_instruction('market')}"""

        _emit_market_tool_trace(
            "analysis",
            "Multi-TF synthesis",
            "market:synthesis",
            f"Synthesizing {len(tf_results)} timeframe reports into unified analysis...",
        )

        with LLM_INVOKE_LOCK:
            raw_report = _response_text(base_llm.invoke(synthesis_prompt))

        _emit_market_tool_trace(
            "analysis",
            "Multi-TF synthesis complete",
            "market:synthesis",
            f"Synthesis complete ({len(raw_report)} chars).",
        )
        report, evidence_items = split_report_and_evidence(
            raw_report,
            agent_key="market",
            agent_label="Market Analyst",
            report_section="market_report",
            analysis_date=current_date,
        )

        market_source_bundle = {
            "symbol": symbol,
            "exchange": "binance",
            "timeframes": tf_bundles,
        }

        return {
            "messages": [AIMessage(content=report)],
            "market_source_bundle": market_source_bundle,
            "market_report": report,
            "market_tf_reports": tf_results,
            "evidence_items": evidence_items,
        }

    return market_analyst_node
