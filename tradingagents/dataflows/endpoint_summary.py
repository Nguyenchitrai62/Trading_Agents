from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Iterable


VALID_DIRECTIONS = {"bullish", "bearish", "neutral", "mixed"}


def stable_payload_hash(value: object) -> str:
    """Return a deterministic hash for compact endpoint payloads."""
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()


def summarize_endpoint_result(
    *,
    endpoint_name: str,
    request_metadata: dict[str, Any] | None,
    endpoint_result: dict[str, Any],
    symbol: str,
    analysis_date: str,
) -> dict[str, Any]:
    """Compress one endpoint result into a scored, prompt-friendly summary.

    This helper is intentionally deterministic. The orchestration layer can
    wrap it with an LLM later, but the shape is already stable for cache keys,
    prompt injection, SSE display, and tests.
    """
    request_metadata = request_metadata or {}
    payload_hash = stable_payload_hash(
        {
            "status": endpoint_result.get("status"),
            "summary": endpoint_result.get("summary") or {},
            "error": endpoint_result.get("error") or "",
        }
    )
    request_hash = stable_payload_hash(
        {
            "endpoint": endpoint_name,
            "request": request_metadata,
            "symbol": symbol,
            "analysis_date": analysis_date,
        }
    )
    summary = endpoint_result.get("summary") or {}
    status = str(endpoint_result.get("status") or "error")
    timestamp = str(endpoint_result.get("fetched_at") or endpoint_result.get("timestamp") or "")
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

    key_metrics = _extract_key_metrics(summary)
    facts = _build_summary_bullets(endpoint_result, summary, key_metrics)
    caveats = _build_caveats(endpoint_result, summary)
    direction = _infer_direction(endpoint_name, endpoint_result, key_metrics)
    confidence = _infer_confidence(endpoint_result, direction, key_metrics, caveats)

    return {
        "endpoint_name": endpoint_name,
        "title": str(endpoint_result.get("title") or endpoint_name),
        "package": str(endpoint_result.get("package") or ""),
        "package_label": str(endpoint_result.get("package_label") or endpoint_result.get("package") or ""),
        "source": str(endpoint_result.get("source") or endpoint_result.get("path") or endpoint_name),
        "source_type": str(endpoint_result.get("source_type") or "other"),
        "timestamp": timestamp,
        "direction": direction,
        "confidence": confidence,
        "summary_bullets": facts,
        "key_metrics": key_metrics,
        "caveats": caveats,
        "request_hash": request_hash,
        "raw_payload_hash": payload_hash,
        "status": status,
    }


def build_endpoint_summaries(
    results: Iterable[dict[str, Any]],
    *,
    symbol: str,
    analysis_date: str,
    max_workers: int = 4,
    cache: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Summarize independent endpoint results in parallel and preserve order."""
    ordered_results = [result for result in results if isinstance(result, dict)]
    if not ordered_results:
        return []

    cache = cache if cache is not None else {}
    safe_workers = max(1, min(len(ordered_results), int(max_workers or 1)))
    summaries_by_index: list[dict[str, Any] | None] = [None] * len(ordered_results)

    def summarize(index: int, result: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        endpoint_name = str(result.get("key") or result.get("title") or f"endpoint_{index}")
        request_metadata = {
            "path": result.get("path"),
            "params": result.get("params") or {},
            "source": result.get("source"),
        }
        payload_hash = stable_payload_hash(
            {
                "status": result.get("status"),
                "summary": result.get("summary") or {},
                "error": result.get("error") or "",
            }
        )
        request_hash = stable_payload_hash(
            {
                "endpoint": endpoint_name,
                "request": request_metadata,
                "symbol": symbol,
                "analysis_date": analysis_date,
            }
        )
        cache_key = f"{endpoint_name}:{request_hash}:{payload_hash}"
        if cache_key not in cache:
            cache[cache_key] = summarize_endpoint_result(
                endpoint_name=endpoint_name,
                request_metadata=request_metadata,
                endpoint_result=result,
                symbol=symbol,
                analysis_date=analysis_date,
            )
        return index, dict(cache[cache_key])

    if safe_workers == 1:
        for index, result in enumerate(ordered_results):
            result_index, summary = summarize(index, result)
            summaries_by_index[result_index] = summary
    else:
        with ThreadPoolExecutor(max_workers=safe_workers, thread_name_prefix="endpoint-summary") as executor:
            future_map = {
                executor.submit(summarize, index, result): index
                for index, result in enumerate(ordered_results)
            }
            for future in as_completed(future_map):
                result_index, summary = future.result()
                summaries_by_index[result_index] = summary

    return [summary for summary in summaries_by_index if summary is not None]


def endpoint_summaries_to_evidence_items(
    summaries: Iterable[dict[str, Any]],
    *,
    owner_agent_key: str,
    owner_agent_label: str,
    analysis_date: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for summary in list(summaries)[: max(1, limit)]:
        direction = str(summary.get("direction") or "neutral")
        if direction not in VALID_DIRECTIONS:
            direction = "neutral"
        metrics = summary.get("key_metrics") or {}
        metric_text = ", ".join(f"{key}={value}" for key, value in metrics.items())
        bullets = summary.get("summary_bullets") or []
        claim = "; ".join(str(item) for item in bullets[:2]) or f"{summary.get('title') or summary.get('endpoint_name')} summarized."
        items.append(
            {
                "agent": owner_agent_key,
                "agent_label": owner_agent_label,
                "report_section": "endpoint_summaries",
                "claim": claim,
                "source": summary.get("source") or summary.get("endpoint_name") or "endpoint",
                "source_type": summary.get("source_type") or "flow",
                "timestamp": summary.get("timestamp") or analysis_date,
                "metric": summary.get("title") or summary.get("endpoint_name") or "endpoint_summary",
                "value": metric_text or f"direction={direction}",
                "direction": direction,
                "confidence": summary.get("confidence") or 0.5,
                "freshness": "recent",
                "notes": "Endpoint summary layer compressed this source before downstream agent prompts.",
            }
        )
    return items


def format_endpoint_summaries_for_prompt(
    summaries: Iterable[dict[str, Any]] | None,
    *,
    focus_packages: Iterable[str] | None = None,
    limit: int = 30,
) -> str:
    summary_items = [item for item in (summaries or []) if isinstance(item, dict)]
    if focus_packages:
        focus_set = {str(item) for item in focus_packages}
        summary_items = [item for item in summary_items if str(item.get("package") or "") in focus_set]
    if not summary_items:
        return ""

    lines = ["Endpoint summary layer:"]
    for item in summary_items[: max(1, limit)]:
        title = str(item.get("title") or item.get("endpoint_name") or "Endpoint")
        package_label = str(item.get("package_label") or item.get("package") or "source")
        direction = str(item.get("direction") or "neutral")
        confidence = _coerce_float(item.get("confidence"), default=0.0)
        bullets = "; ".join(str(value) for value in (item.get("summary_bullets") or [])[:6])
        metrics = ", ".join(
            f"{key}={value}" for key, value in ((item.get("key_metrics") or {}).items())
        )
        caveats = "; ".join(str(value) for value in (item.get("caveats") or [])[:4])
        line = f"- {title} ({package_label}): direction={direction}, confidence={confidence:.2f}"
        if metrics:
            line += f"; metrics: {metrics}"
        if bullets:
            line += f"; facts: {bullets}"
        if caveats:
            line += f"; caveats: {caveats}"
        lines.append(_trim_text(line, 800))
    if len(summary_items) > limit:
        lines.append(f"- ... {len(summary_items) - limit} more endpoint summaries omitted.")
    return "\n".join(lines)


def _extract_key_metrics(summary: dict[str, Any]) -> dict[str, object]:
    metrics: dict[str, object] = {}
    item_count = summary.get("item_count")
    if item_count not in (None, ""):
        metrics["rows"] = item_count
    numeric = summary.get("numeric_summary") or {}
    if isinstance(numeric, dict):
        for key, values in numeric.items():
            if not isinstance(values, dict):
                continue
            latest = values.get("latest")
            if latest not in (None, ""):
                metrics[str(key)] = latest
    fields = summary.get("fields") or summary.get("keys") or []
    if isinstance(fields, list) and fields:
        metrics["fields"] = ", ".join(str(item) for item in fields)
    return metrics


def _build_summary_bullets(
    result: dict[str, Any],
    summary: dict[str, Any],
    key_metrics: dict[str, object],
) -> list[str]:
    if str(result.get("status") or "") != "ok":
        return [f"Endpoint unavailable: {result.get('error') or 'unknown error'}"]
    bullets = [
        f"status ok from {result.get('source') or result.get('path') or 'endpoint'}",
    ]
    freshness = str(result.get("freshness") or "").strip()
    if freshness:
        bullets.append(f"freshness={freshness}")
    data_kind = str(summary.get("data_kind") or "").strip()
    if data_kind:
        bullets.append(f"data_kind={data_kind}")
    if key_metrics:
        bullets.append(
            "key_metrics="
            + ", ".join(f"{key}={value}" for key, value in key_metrics.items())
        )
    return bullets[:8]


def _build_caveats(result: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    caveats: list[str] = []
    if str(result.get("status") or "") != "ok":
        caveats.append(str(result.get("error") or "endpoint failed"))
    if not summary:
        caveats.append("no compact summary available")
    if result.get("rate_limit"):
        caveats.append("rate-limit headers present")
    api_message = summary.get("api_message")
    if api_message:
        caveats.append(str(api_message))
    return caveats[:4]


def _infer_direction(
    endpoint_name: str,
    result: dict[str, Any],
    key_metrics: dict[str, object],
) -> str:
    if str(result.get("status") or "") != "ok":
        return "neutral"

    text = f"{endpoint_name} {result.get('title') or ''}".lower()
    metric_text = " ".join(f"{key} {value}" for key, value in key_metrics.items()).lower()
    combined = f"{text} {metric_text}"

    if any(term in combined for term in ("long/short", "long_short", "longshort")):
        ratio = _first_numeric_metric(key_metrics)
        if ratio is not None:
            if ratio >= 1.12:
                return "bullish"
            if ratio <= 0.88:
                return "bearish"
        return "mixed"

    if "funding" in combined:
        latest = _first_numeric_metric(key_metrics)
        if latest is None:
            # Try to parse funding rate from string-embedded values
            latest = _parse_funding_rate_from_metrics(key_metrics)
        if latest is not None:
            if latest > 0.03:
                return "bearish"
            if latest < -0.01:
                return "bullish"
        return "neutral"

    if any(term in combined for term in ("reserve", "balance")):
        return "mixed"

    if any(term in combined for term in ("etf", "grayscale", "flow")):
        latest = _first_numeric_metric(key_metrics)
        if latest is not None:
            if latest > 0:
                return "bullish"
            if latest < 0:
                return "bearish"
        return "mixed"

    if any(term in combined for term in ("liquidation", "taker", "option", "open interest", "oi")):
        return "mixed"

    # Fear & Greed index: "Value" field = index 0-100; <30 = extreme fear (bearish), >70 = greed (bullish)
    if "fear" in combined or "greed" in combined:
        value_metric = key_metrics.get("Value")
        fear_value = _coerce_float(value_metric)
        if fear_value is not None:
            if fear_value <= 25:
                return "bearish"
            if fear_value >= 65:
                return "bullish"
        return "neutral"

    # Coinbase premium index
    if "premium" in combined:
        premium = _first_numeric_metric(key_metrics)
        if premium is not None:
            if premium > 0:
                return "bullish"
            if premium < -0.1:
                return "bearish"
        return "mixed"

    return "neutral"


def _infer_confidence(
    result: dict[str, Any],
    direction: str,
    key_metrics: dict[str, object],
    caveats: list[str],
) -> float:
    if str(result.get("status") or "") != "ok":
        return 0.2
    confidence = 0.54
    if key_metrics:
        confidence += 0.16
    if direction in {"bullish", "bearish"}:
        confidence += 0.06
    confidence -= min(0.18, len(caveats) * 0.05)
    return round(max(0.05, min(confidence, 0.86)), 2)


def _first_numeric_metric(metrics: dict[str, object]) -> float | None:
    for key, value in metrics.items():
        if key == "rows":
            continue
        number = _coerce_float(value)
        if number is not None:
            return number
    return None


def _parse_funding_rate_from_metrics(metrics: dict[str, object]) -> float | None:
    """Try to extract a funding rate value from string-embedded metrics like 'Binance: 0.00373, ...'."""
    import re as _re

    for key, value in metrics.items():
        if key in ("rows", "fields"):
            continue
        text = str(value)
        rates: list[float] = []
        for match in _re.finditer(r'([-]?\d+\.?\d*)\s*$|:\s*([-]?\d+\.?\d*)', text):
            num_str = match.group(1) or match.group(2)
            try:
                rates.append(float(num_str))
            except (ValueError, TypeError):
                pass
        if rates:
            return sum(rates) / len(rates)
    return None


def _coerce_float(value: object, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _trim_text(value: str, limit: int) -> str:
    if limit <= 0 or len(value) <= limit:
        return value
    suffix = " [truncated]"
    return value[: max(0, limit - len(suffix))].rstrip() + suffix
