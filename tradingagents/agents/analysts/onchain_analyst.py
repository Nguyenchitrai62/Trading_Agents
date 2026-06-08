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
from tradingagents.llm_clients.base_client import normalize_content


_MAX_ENDPOINT_PROMPT_CHARS = 20000
_MAX_CATEGORY_ANALYSIS_CHARS = 5000
_MAX_AGGREGATE_INPUT_CHARS = 80000

_ONCHAIN_PACKAGES = [
    "exchange_reserves",
    "institutional_flow",
    "derivatives_positioning",
    "funding_pressure",
    "liquidation_risk",
    "macro_cycle_context",
]

_PACKAGE_LABELS: dict[str, str] = {
    "exchange_reserves": "Exchange Reserves",
    "institutional_flow": "Institutional Flow",
    "derivatives_positioning": "Derivatives Positioning",
    "funding_pressure": "Funding Pressure",
    "liquidation_risk": "Liquidation Risk",
    "macro_cycle_context": "Macro Cycle Context",
}


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


def _emit_package_trace(package_key: str, package_label: str, phase: str, content: str) -> None:
    callback = get_config().get("analysis_trace_callback")
    if not callable(callback):
        return
    callback(
        {
            "agent": "Onchain Analyst",
            "phase": phase,
            "title": f"Onchain: {package_label}",
            "trace_id": f"onchain:package:{package_key}",
            "content": content,
        }
    )


def _analyze_package(
    base_llm: Any,
    package_key: str,
    package_label: str,
    endpoints: list[dict[str, Any]],
    summaries_by_key: dict[str, dict[str, Any]],
    symbol: str,
    current_date: str,
) -> dict[str, Any]:
    _emit_package_trace(package_key, package_label, "analysis", f"Analyzing {len(endpoints)} endpoints for {package_label}...")

    if not endpoints:
        return {
            "package_key": package_key,
            "package_label": package_label,
            "status": "no_data",
            "analysis": f"No CoinGlass data available for {package_label}. This category could not be analyzed.",
            "direction": "unknown",
            "confidence": 0.0,
            "endpoint_count": 0,
            "successful_endpoints": 0,
        }

    endpoint_contexts: list[str] = []
    for result in endpoints:
        key = str(result.get("key") or "")
        endpoint_title = str(result.get("title") or key)
        summary = summaries_by_key.get(key)
        payload_text = _compact_endpoint_payload(result, summary)
        status = str(result.get("status") or "error")
        if status != "ok":
            endpoint_contexts.append(f"### {endpoint_title} [UNAVAILABLE]\n{payload_text}")
        else:
            endpoint_contexts.append(f"### {endpoint_title}\n{payload_text}")

    combined_context = _trim("\n\n".join(endpoint_contexts), _MAX_AGGREGATE_INPUT_CHARS)
    ok_count = sum(1 for r in endpoints if str(r.get("status") or "") == "ok")

    prompt = f"""You are a specialized onchain analyst for the **{package_label}** category.

Analyze the CoinGlass endpoint data below for {symbol} on {current_date}. The backend has prefetched this data from CoinGlass — you do NOT have live API access.

{combined_context}

Produce a concise {package_label} category analysis (under 250 words):
1. **Direction**: bullish, bearish, neutral, mixed, or unknown.
2. **Confidence**: numeric 0.0-1.0 based on data quality and signal clarity.
3. **Key findings**: concrete metrics and their interpretation — do not just repeat numbers.
4. **Contradictions**: mixed signals or conflicting endpoints within this category.
5. **Data quality**: note any thin samples, stale timestamps, or unavailable endpoints.

Start your response with:
Direction: <direction>
Confidence: <0.0-1.0>

Then write the analysis."""

    analysis = _trim(_response_text(base_llm.invoke(prompt)), _MAX_CATEGORY_ANALYSIS_CHARS)

    direction = "unknown"
    confidence = 0.0
    analysis_body = analysis
    for line in analysis.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("direction:") and not stripped.lower().startswith("direction:"):
            pass
        if ":" in stripped:
            prefix, _, value = stripped.partition(":")
            prefix_lower = prefix.strip().lower()
            value_stripped = value.strip()
            if prefix_lower == "direction":
                direction = value_stripped.strip().lower().rstrip(".")
                if direction not in ("bullish", "bearish", "neutral", "mixed", "unknown"):
                    direction = "unknown"
                analysis_body = analysis.split("\n", 2)[-1].strip() if analysis.count("\n") >= 2 else analysis
            elif prefix_lower == "confidence":
                try:
                    confidence = float(value_stripped.strip().rstrip("."))
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    confidence = 0.0
                if analysis_body == analysis:
                    analysis_body = analysis.split("\n", 2)[-1].strip() if analysis.count("\n") >= 2 else analysis

    _emit_package_trace(package_key, package_label, "analysis", f"Completed {package_label} analysis: direction={direction}, confidence={confidence:.2f}")

    return {
        "package_key": package_key,
        "package_label": package_label,
        "status": "analyzed",
        "analysis": analysis_body or analysis,
        "direction": direction,
        "confidence": confidence,
        "endpoint_count": len(endpoints),
        "successful_endpoints": ok_count,
    }


def create_onchain_analyst(llm):
    base_llm = resolve_structured_base_llm(llm)

    def onchain_analyst_node(state: dict) -> dict:
        current_date = state["trade_date"]
        symbol = state["company_of_interest"]
        endpoint_results = [item for item in (state.get("coinglass_endpoint_results") or []) if isinstance(item, dict)]
        endpoint_summaries = [item for item in (state.get("endpoint_summaries") or []) if isinstance(item, dict)]
        summaries_by_key = _summary_by_endpoint(endpoint_summaries)

        # Group endpoints by their package field
        endpoints_by_package: dict[str, list[dict[str, Any]]] = {}
        for result in endpoint_results:
            package = str(result.get("package") or "").strip()
            if not package:
                continue
            endpoints_by_package.setdefault(package, []).append(result)

        # Run 6 category sub-agents in parallel (one per configured package)
        category_analyses: list[dict[str, Any]] = []
        config = get_config()
        concurrency = max(1, int(config.get("onchain_endpoint_llm_concurrency") or 4))

        if endpoint_results:
            with ThreadPoolExecutor(max_workers=min(concurrency, len(_ONCHAIN_PACKAGES)), thread_name_prefix="onchain-package-llm") as executor:
                futures = {}
                for package_key in _ONCHAIN_PACKAGES:
                    package_label = _PACKAGE_LABELS.get(package_key, package_key)
                    package_endpoints = endpoints_by_package.get(package_key, [])
                    future = executor.submit(
                        _analyze_package,
                        base_llm,
                        package_key,
                        package_label,
                        package_endpoints,
                        summaries_by_key,
                        symbol,
                        current_date,
                    )
                    futures[future] = package_key

                for future in as_completed(futures):
                    try:
                        item = future.result()
                    except Exception as exc:
                        package_key = futures[future]
                        package_label = _PACKAGE_LABELS.get(package_key, package_key)
                        item = {
                            "package_key": package_key,
                            "package_label": package_label,
                            "status": "error",
                            "analysis": f"Category analysis failed: {exc}",
                            "direction": "unknown",
                            "confidence": 0.0,
                            "endpoint_count": len(endpoints_by_package.get(package_key, [])),
                            "successful_endpoints": 0,
                        }
                    category_analyses.append(item)

        if not category_analyses:
            report = (
                "# Onchain Analysis\n\n"
                "CoinGlass endpoint context was unavailable for this run. No onchain metrics were analyzed, "
                "so downstream agents should treat onchain evidence as missing rather than neutral."
            )
            evidence_items: list[dict[str, Any]] = []
            structured_payload = {"status": "unavailable", "category_count": 0, "category_analyses": []}
        else:
            # Build leader prompt from category analyses only — NO raw endpoint data
            category_context_lines: list[str] = []
            for item in category_analyses:
                label = item.get("package_label") or item.get("package_key") or "Unknown"
                direction = item.get("direction", "unknown")
                confidence = item.get("confidence", 0.0)
                analysis = str(item.get("analysis") or "").strip()
                category_context_lines.append(
                    f"## {label}\n"
                    f"Direction: {direction} | Confidence: {confidence:.2f} | "
                    f"Endpoints: {item.get('successful_endpoints', 0)}/{item.get('endpoint_count', 0)}\n\n"
                    f"{analysis}"
                )

            category_context = _trim("\n\n".join(category_context_lines), _MAX_AGGREGATE_INPUT_CHARS)

            _emit_package_trace("synthesis", "Synthesis", "analysis", f"Synthesizing {len(category_analyses)} category analyses into unified onchain report...")

            prompt = f"""You are the Lead Onchain Analyst synthesizing category-level analyses into a unified report for {symbol} on {current_date}.

Below are independent category analyses from 6 specialized onchain sub-analysts. Each sub-analyst analyzed only the CoinGlass endpoints in its assigned category. Synthesize their findings — do NOT request additional data or tools.

Category Analyses:
{category_context}

Produce a detailed markdown report with:
1. Overall onchain/derivatives regime and dominant signal direction.
2. Derivatives positioning and funding pressure.
3. Liquidation and taker-pressure risks.
4. Exchange reserves and institutional flow.
5. Options/macro-cycle context when present.
6. Key contradictions between categories and missing data notes.
7. A final markdown table of the highest-signal category findings.
{get_structured_evidence_instruction('onchain')}"""

            _emit_package_trace("synthesis", "Synthesis", "analysis", f"Lead synthesis prompt: {len(prompt)} chars")

            raw_report = _response_text(base_llm.invoke(prompt))
            report, evidence_items = split_report_and_evidence(
                raw_report,
                agent_key="onchain",
                agent_label="Onchain Analyst",
                report_section="onchain_report",
                analysis_date=current_date,
            )

            _emit_package_trace("synthesis", "Synthesis", "analysis", f"Lead synthesis complete ({len(report)} chars)")

            structured_payload = {
                "status": "completed",
                "category_count": len(category_analyses),
                "packages": sorted({str(item.get("package_key") or "") for item in category_analyses if item.get("package_key")}),
                "total_endpoints": sum(item.get("endpoint_count", 0) for item in category_analyses),
                "successful_endpoints": sum(item.get("successful_endpoints", 0) for item in category_analyses),
                "category_analyses": category_analyses,
            }

        return {
            "messages": [AIMessage(content=report)],
            "onchain_endpoint_analyses": category_analyses,
            "onchain_report": report,
            "onchain_analysis_structured": structured_payload,
            "evidence_items": evidence_items,
        }

    return onchain_analyst_node
