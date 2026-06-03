from __future__ import annotations

import json

from langchain_core.messages import AIMessage

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_crypto_indicators,
    get_crypto_ohlcv,
    get_language_instruction,
)
from tradingagents.agents.utils.evidence import (
    get_structured_evidence_instruction,
    split_report_and_evidence,
)
from tradingagents.agents.utils.structured import resolve_structured_base_llm
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


def _format_tool_call(tool_name: str, args: dict) -> str:
    try:
        return f"{tool_name}({json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)})"
    except TypeError:
        items = ", ".join(f"{key}={value}" for key, value in list(args.items())[:6])
        return f"{tool_name}({items})"


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


def _invoke_tool(tool, args: dict, trace_id: str) -> str:
    tool_name = str(getattr(tool, "name", "tool") or "tool")
    _emit_market_tool_trace("tool_call", tool_name, trace_id, _format_tool_call(tool_name, args))
    try:
        raw = tool.invoke(args)
        result = str(raw) if raw is not None else f"{tool_name} returned empty data"
    except Exception as exc:
        result = f"Error: {tool_name} failed: {exc}"
    _emit_market_tool_trace("tool_result", tool_name, trace_id, result)
    return result


def _collect_market_source_bundle(symbol: str) -> dict[str, object]:
    ohlcv = _invoke_tool(
        get_crypto_ohlcv,
        {
            "symbol": symbol,
            "timeframe": "auto",
            "limit": 96,
            "exchange_name": "binance",
        },
        "market:get_crypto_ohlcv",
    )
    indicators = {
        indicator: _invoke_tool(
            get_crypto_indicators,
            {
                "symbol": symbol,
                "indicator": indicator,
                "timeframe": "auto",
                "limit": 48,
                "exchange_name": "binance",
            },
            f"market:get_crypto_indicators:{indicator}",
        )
        for indicator in MARKET_INDICATORS
    }
    return {
        "symbol": symbol,
        "exchange": "binance",
        "ohlcv": ohlcv,
        "indicators": indicators,
        "indicator_names": list(MARKET_INDICATORS),
    }


def _format_market_bundle(bundle: dict[str, object]) -> str:
    lines = [
        "# Market Source Bundle",
        "",
        f"Symbol: {bundle.get('symbol')}",
        f"Exchange: {bundle.get('exchange')}",
        "",
        "## OHLCV",
        _trim(bundle.get("ohlcv"), _MAX_TOOL_BLOCK_CHARS),
    ]
    indicators = bundle.get("indicators") or {}
    if isinstance(indicators, dict):
        for name, content in indicators.items():
            lines.extend(["", f"## Indicator: {name}", _trim(content, _MAX_TOOL_BLOCK_CHARS)])
    return _trim("\n".join(lines), _MAX_MARKET_CONTEXT_CHARS)


def create_market_analyst(llm):
    base_llm = resolve_structured_base_llm(llm)

    def market_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "crypto")
        symbol = state["company_of_interest"]
        instrument_context = build_instrument_context(symbol, asset_type)
        market_bundle = _collect_market_source_bundle(symbol)
        market_context = _format_market_bundle(market_bundle)

        prompt = f"""You are the Market Analyst for this crypto trading workflow.

{instrument_context}
Current analysis date: {current_date}

The market branch is code-first. The backend has already collected CCXT OHLCV candles and calculated technical indicators. Do not use web search. Analyze only the market data below and preserve concrete values from the tool outputs.

Market data:
{market_context}

Produce a detailed market report covering:
1. Trend and market structure.
2. Momentum and moving-average regime.
3. Volatility, range, and stop-placement implications.
4. Volume/flow from exchange-traded data when available.
5. Support/resistance or invalidation zones supported by the data.
6. Confidence and data caveats.
7. A markdown table summarizing the highest-signal market findings.
{get_language_instruction()}{get_structured_evidence_instruction('market')}"""

        raw_report = _response_text(base_llm.invoke(prompt))
        report, evidence_items = split_report_and_evidence(
            raw_report,
            agent_key="market",
            agent_label="Market Analyst",
            report_section="market_report",
            analysis_date=current_date,
        )

        return {
            "messages": [AIMessage(content=report)],
            "market_source_bundle": market_bundle,
            "market_report": report,
            "evidence_items": evidence_items,
        }

    return market_analyst_node