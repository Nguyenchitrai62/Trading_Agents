from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from langchain_core.messages import AIMessage

from tradingagents.agents.utils.evidence import (
    get_structured_evidence_instruction,
    split_report_and_evidence,
)
from tradingagents.agents.utils.structured import resolve_structured_base_llm
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.endpoint_summary import format_endpoint_summaries_for_prompt
from tradingagents.llm_clients.base_client import normalize_content


_MAX_ENDPOINT_PROMPT_CHARS = 4200
_MAX_ENDPOINT_ANALYSIS_CHARS = 1800
_MAX_AGGREGATE_INPUT_CHARS = 18000


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


def _compact_endpoint_payload(result: dict[str, Any], summary: dict[str, Any] | None = None) -> str:
    payload = {
        "key": result.get("key"),
        "title": result.get("title"),
        "package": result.get("package"),
        "source": result.get("source") or result.get("path"),
        "status": result.get("status"),
        "freshness": result.get("freshness"),
        "http_status": result.get("http_status"),
        "error": result.get("error"),
        "summary": result.get("summary") or {},
        "deterministic_summary": summary or {},
    }
    return _trim(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), _MAX_ENDPOINT_PROMPT_CHARS)


def _summary_by_endpoint(summaries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for item in summaries:
        if not isinstance(item, dict):
            continue
        key = str(item.get("endpoint_name") or "").strip()
        if key:
            output[key] = item
    return output


def _analyze_endpoint(base_llm: Any, result: dict[str, Any], summary: dict[str, Any] | None) -> dict[str, Any]:
    endpoint_key = str(result.get("key") or result.get("title") or "coinglass_endpoint").strip()
    title = str(result.get("title") or endpoint_key).strip()
    status = str(result.get("status") or "error").strip()
    if status != "ok":
        return {
            "endpoint_key": endpoint_key,
            "title": title,
            "package": result.get("package") or "",
            "status": status,
            "analysis": f"Endpoint unavailable: {result.get('error') or 'unknown error'}.",
            "direction": "unknown",
            "confidence": 0.0,
            "freshness": result.get("freshness") or "unknown",
        }

    prompt = f"""You are analyzing one CoinGlass endpoint for a crypto trading workflow.

Endpoint payload and deterministic compression:
{_compact_endpoint_payload(result, summary)}

Write a concise endpoint analysis for downstream onchain synthesis. Use only the supplied endpoint data. Do not invent metrics, timestamps, exchanges, or URLs. If the sample size is thin, say so. Include:
- Direction: bullish, bearish, neutral, mixed, or unknown.
- Confidence: 0.0 to 1.0.
- Key findings with concrete metrics from the payload.
- Caveats and freshness limitations.
Keep the answer under 180 words."""
    analysis = _trim(_response_text(base_llm.invoke(prompt)), _MAX_ENDPOINT_ANALYSIS_CHARS)
    return {
        "endpoint_key": endpoint_key,
        "title": title,
        "package": result.get("package") or "",
        "status": status,
        "analysis": analysis,
        "direction": str((summary or {}).get("direction") or "unknown"),
        "confidence": float((summary or {}).get("confidence") or 0.5),
        "freshness": result.get("freshness") or (summary or {}).get("freshness") or "unknown",
    }


def _emit_endpoint_trace(item: dict[str, Any]) -> None:
    callback = get_config().get("analysis_trace_callback")
    if not callable(callback):
        return
    callback(
        {
            "agent": "Onchain Analyst",
            "phase": "analysis",
            "title": item.get("title") or item.get("endpoint_key") or "CoinGlass endpoint analysis",
            "trace_id": f"onchain:endpoint:{item.get('endpoint_key') or item.get('title') or 'endpoint'}",
            "content": item.get("analysis") or "",
        }
    )


def create_onchain_analyst(llm):
    base_llm = resolve_structured_base_llm(llm)

    def onchain_analyst_node(state: dict) -> dict:
        current_date = state["trade_date"]
        symbol = state["company_of_interest"]
        endpoint_results = [item for item in (state.get("coinglass_endpoint_results") or []) if isinstance(item, dict)]
        endpoint_summaries = [item for item in (state.get("endpoint_summaries") or []) if isinstance(item, dict)]
        summaries_by_key = _summary_by_endpoint(endpoint_summaries)
        config = get_config()
        concurrency = max(1, int(config.get("onchain_endpoint_llm_concurrency") or config.get("coinglass_concurrency_limit") or 2))

        if endpoint_results:
            analyses: list[dict[str, Any] | None] = [None] * len(endpoint_results)
            with ThreadPoolExecutor(max_workers=min(concurrency, len(endpoint_results)), thread_name_prefix="onchain-endpoint-llm") as executor:
                future_map = {
                    executor.submit(
                        _analyze_endpoint,
                        base_llm,
                        result,
                        summaries_by_key.get(str(result.get("key") or "")),
                    ): index
                    for index, result in enumerate(endpoint_results)
                }
                for future in as_completed(future_map):
                    index = future_map[future]
                    try:
                        item = future.result()
                    except Exception as exc:
                        result = endpoint_results[index]
                        endpoint_key = str(result.get("key") or result.get("title") or f"endpoint_{index}")
                        item = {
                            "endpoint_key": endpoint_key,
                            "title": str(result.get("title") or endpoint_key),
                            "package": result.get("package") or "",
                            "status": "error",
                            "analysis": f"Endpoint LLM analysis failed: {exc}",
                            "direction": "unknown",
                            "confidence": 0.0,
                            "freshness": result.get("freshness") or "unknown",
                        }
                    analyses[index] = item
                    _emit_endpoint_trace(item)
            endpoint_analyses = [item for item in analyses if item]
        else:
            endpoint_analyses = []

        if not endpoint_analyses:
            report = (
                "# Onchain Analysis\n\n"
                "CoinGlass endpoint context was unavailable for this run. No onchain metrics were analyzed, "
                "so downstream agents should treat onchain evidence as missing rather than neutral."
            )
            evidence_items: list[dict[str, Any]] = []
            structured_payload = {"status": "unavailable", "endpoint_count": 0, "endpoint_analyses": []}
        else:
            endpoint_lines = []
            for item in endpoint_analyses:
                endpoint_lines.append(
                    "\n".join(
                        [
                            f"## {item.get('title') or item.get('endpoint_key')}",
                            f"- Endpoint: {item.get('endpoint_key')}",
                            f"- Package: {item.get('package') or 'unknown'}",
                            f"- Direction: {item.get('direction')}",
                            f"- Confidence: {item.get('confidence')}",
                            f"- Freshness: {item.get('freshness')}",
                            "",
                            str(item.get("analysis") or "").strip(),
                        ]
                    )
                )
            endpoint_context = _trim("\n\n".join(endpoint_lines), _MAX_AGGREGATE_INPUT_CHARS)
            deterministic_context = format_endpoint_summaries_for_prompt(endpoint_summaries, limit=24)
            prompt = f"""You are the Onchain Analyst for {symbol} on {current_date}.

You receive one LLM analysis for each fetched CoinGlass endpoint plus deterministic endpoint summaries. Synthesize them into one complete onchain report. Deduplicate overlapping endpoint signals. Preserve contradictions instead of smoothing them away. Use CoinGlass as source-backed evidence only; do not invent unavailable metrics.

Endpoint LLM analyses:
{endpoint_context}

Deterministic endpoint summaries:
{deterministic_context or '<unavailable>'}

Produce a detailed markdown report with:
1. Overall onchain/derivatives regime.
2. Derivatives positioning and funding pressure.
3. Liquidation and taker-pressure risks.
4. Exchange reserves and institutional flow.
5. Options/macro-cycle context when present.
6. Key contradictions, missing data, and confidence.
7. A final markdown table of the highest-signal endpoint findings.
{get_structured_evidence_instruction('onchain')}"""
            raw_report = _response_text(base_llm.invoke(prompt))
            report, evidence_items = split_report_and_evidence(
                raw_report,
                agent_key="onchain",
                agent_label="Onchain Analyst",
                report_section="onchain_report",
                analysis_date=current_date,
            )
            structured_payload = {
                "status": "completed",
                "endpoint_count": len(endpoint_analyses),
                "successful_endpoint_count": sum(1 for item in endpoint_analyses if item.get("status") == "ok"),
                "packages": sorted({str(item.get("package") or "") for item in endpoint_analyses if item.get("package")}),
                "endpoint_analyses": endpoint_analyses,
            }

        return {
            "messages": [AIMessage(content=report)],
            "onchain_endpoint_analyses": endpoint_analyses,
            "onchain_report": report,
            "onchain_analysis_structured": structured_payload,
            "evidence_items": evidence_items,
        }

    return onchain_analyst_node
