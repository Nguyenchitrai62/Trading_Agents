"""
Comprehensive test of CoinGlass data pipeline from raw API to agent prompt.
Tests every endpoint, traces data through all summarization/compression stages,
and identifies data loss at each layer.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections import OrderedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradingagents.dataflows.coinglass_client import (
    HIGH_VALUE_ENDPOINTS,
    CoinGlassClient,
    summarize_payload,
    DEFAULT_EXCHANGE_LIST,
    build_coinglass_prompt_context,
    build_coinglass_package_contexts,
    build_coinglass_evidence_items,
)
from tradingagents.dataflows.coinglass_client import (
    _format_coinglass_prompt_result_line,
    _compact_json_value,
    _summarize_parallel_scalar_lists,
)
from tradingagents.dataflows.endpoint_summary import (
    build_endpoint_summaries,
    format_endpoint_summaries_for_prompt,
    summarize_endpoint_result,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "coinglass_test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# --- helpers ---

def _type_summary(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, dict):
        keys = list(value.keys())
        return f"dict[{len(keys)} keys]: {keys[:12]}"
    if isinstance(value, list):
        if not value:
            return "list[0]"
        sample = value[0]
        inner = _type_summary(sample) if not isinstance(sample, (dict, list)) else type(sample).__name__
        return f"list[{len(value)}] of {inner}"
    return f"{type(value).__name__}: {_safe_str(value)[:80]}"

def _safe_str(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)[:200]

def _sample_keys(data: dict) -> dict:
    """Show structure of dict keys with their types"""
    result = OrderedDict()
    for key in list(data.keys())[:20]:
        val = data[key]
        if isinstance(val, list) and val:
            item = val[0]
            if isinstance(item, dict):
                result[key] = f"list[{len(val)}] of dict, sample keys: {list(item.keys())[:8]}"
            elif isinstance(item, list):
                result[key] = f"list[{len(val)}] of list"
            else:
                result[key] = f"list[{len(val)}] of {type(item).__name__}, sample: {_safe_str(val[:3])}"
        elif isinstance(val, dict):
            result[key] = f"dict[{len(val)} keys]: {list(val.keys())[:8]}"
        else:
            result[key] = _type_summary(val)
    return result

# --- Main test ---

def main():
    api_key = os.environ.get("COINGLASS_API_KEY") or os.environ.get("COINGLASS-API-KEY")
    if not api_key:
        # Try reading from .env
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("COINGLASS-API-KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        print("ERROR: COINGLASS_API_KEY not found in env or .env file")
        return

    symbol = "BTC"
    client = CoinGlassClient(api_key=api_key)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_lines: list[str] = []
    all_results: list[dict] = []

    print(f"Testing all {len(HIGH_VALUE_ENDPOINTS)} CoinGlass endpoints for {symbol}...\n")

    for idx, spec in enumerate(HIGH_VALUE_ENDPOINTS):
        print(f"[{idx+1}/{len(HIGH_VALUE_ENDPOINTS)}] {spec.title} ({spec.key})")

        result = client.fetch(spec, coin_symbol=symbol, pair_symbol=f"{symbol}USDT", limit=42)
        all_results.append(result)

        section: list[str] = []
        section.append(f"\n{'='*80}")
        section.append(f"ENDPOINT [{idx+1}/{len(HIGH_VALUE_ENDPOINTS)}]: {spec.title}")
        section.append(f"  Key: {spec.key}")
        section.append(f"  Package: {spec.package}")
        section.append(f"  Status: {result.get('status')} (HTTP {result.get('http_status')})")
        section.append(f"  Freshness: {spec.freshness}, Source: {result.get('source')}")

        if result.get("error"):
            section.append(f"  ERROR: {result['error']}")

        # --- STAGE 1: Raw payload structure ---
        payload = result.get("payload")
        if payload is not None:
            section.append(f"\n{'─'*60}")
            section.append("STAGE 1: RAW API PAYLOAD STRUCTURE")
            section.append(f"  Top-level type: {_type_summary(payload)}")
            if isinstance(payload, dict):
                unwrapped = payload.get("data") or payload
                if isinstance(unwrapped, dict):
                    section.append(f"  'data' keys: {list(unwrapped.keys())[:15]}")
                    for k, v in _sample_keys(unwrapped).items():
                        section.append(f"    {k}: {v}")
                elif isinstance(unwrapped, list):
                    if unwrapped:
                        item = unwrapped[0]
                        if isinstance(item, dict):
                            section.append(f"  'data' list[{len(unwrapped)}] of dict, all keys: {sorted(set().union(*(d.keys() for d in unwrapped if isinstance(d, dict))))[:25]}")
                            section.append(f"  Sample item: {_safe_str(_compact_json_value(item))[:300]}")
                        else:
                            section.append(f"  'data' list[{len(unwrapped)}] of {type(item).__name__}: {_safe_str(unwrapped[:5])[:200]}")
                else:
                    section.append(f"  'data' value: {_safe_str(unwrapped)[:200]}")
            elif isinstance(payload, list):
                if payload:
                    item = payload[0]
                    if isinstance(item, dict):
                        section.append(f"  Payload is list[{len(payload)}] of dict, keys: {list(item.keys())}")

        # --- STAGE 2: summarize_payload() output ---
        summary = result.get("summary") or {}
        section.append(f"\n{'─'*60}")
        section.append("STAGE 2: summarize_payload() OUTPUT")
        section.append(f"  data_kind: {summary.get('data_kind')}")
        section.append(f"  item_count: {summary.get('item_count')}")
        section.append(f"  fields: {summary.get('fields')}")
        section.append(f"  primary_list_key: {summary.get('primary_list_key')}")

        if summary.get("numeric_summary"):
            section.append(f"  numeric_summary: {_safe_str(summary['numeric_summary'])[:400]}")

        sample_items = summary.get("sample_items")
        if sample_items:
            section.append(f"  sample_items ({len(sample_items)} items): {_safe_str(sample_items)[:500]}")

        latest_items = summary.get("latest_items")
        if latest_items:
            section.append(f"  latest_items ({len(latest_items)} items): {_safe_str(latest_items)[:500]}")

        if summary.get("keys"):
            section.append(f"  keys: {summary['keys']}")

        if summary.get("data"):
            section.append(f"  data: {_safe_str(summary['data'])[:300]}")

        if summary.get("api_code") or summary.get("api_message"):
            section.append(f"  api_code: {summary.get('api_code')}, api_message: {summary.get('api_message')}")

        # --- STAGE 3: _format_coinglass_prompt_result_line() ---
        prompt_line = _format_coinglass_prompt_result_line(result)
        section.append(f"\n{'─'*60}")
        section.append("STAGE 3: _format_coinglass_prompt_result_line() (1 line per endpoint in package section)")
        section.append(f"  {prompt_line}")

        # --- STAGE 4: summarize_endpoint_result() ---
        endpoint_name = str(result.get("key") or result.get("title") or f"endpoint_{idx}")
        endpoint_summary = summarize_endpoint_result(
            endpoint_name=endpoint_name,
            request_metadata={"path": result.get("path"), "params": result.get("params") or {}, "source": result.get("source")},
            endpoint_result=result,
            symbol=symbol,
            analysis_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        section.append(f"\n{'─'*60}")
        section.append("STAGE 4: summarize_endpoint_result() (deterministic direction/confidence)")
        section.append(f"  direction: {endpoint_summary.get('direction')}")
        section.append(f"  confidence: {endpoint_summary.get('confidence')}")
        section.append(f"  summary_bullets: {endpoint_summary.get('summary_bullets')}")
        section.append(f"  key_metrics: {_safe_str(endpoint_summary.get('key_metrics'))[:300]}")
        section.append(f"  caveats: {endpoint_summary.get('caveats')}")

        # Join and print
        text = "\n".join(section)
        report_lines.append(text)
        print(text)

        if idx < len(HIGH_VALUE_ENDPOINTS) - 1:
            time.sleep(0.3)

    client.close()

    # --- STAGE 5: Build full snapshot and pipeline outputs ---
    print(f"\n{'='*80}")
    print("STAGE 5: BUILDING FULL PIPELINE OUTPUTS\n")

    from tradingagents.dataflows.coinglass_client import (
        _build_packages,
        normalize_coin_symbol,
        normalize_pair_symbol,
        fetch_high_value_snapshot,
    )

    # Build packages from results
    packages = _build_packages(all_results)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    successful = sum(1 for r in all_results if r.get("status") == "ok")
    snapshot = {
        "configured": True,
        "enabled": True,
        "symbol": "BTC",
        "pair_symbol": "BTCUSDT",
        "fetched_at": fetched_at,
        "base_url": "https://open-api-v4.coinglass.com",
        "endpoint_count": len(all_results),
        "successful_endpoint_count": successful,
        "failed_endpoint_count": len(all_results) - successful,
        "packages": packages,
        "results": all_results,
        "warnings": [
            f"{r.get('title') or r.get('key')} failed: {r.get('error')}"
            for r in all_results if r.get("status") != "ok"
        ],
    }

    # Build endpoint summaries
    analysis_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    endpoint_summaries = build_endpoint_summaries(
        all_results, symbol="BTC", analysis_date=analysis_date
    )
    snapshot["endpoint_summaries"] = endpoint_summaries

    # Build full prompt context
    full_context = build_coinglass_prompt_context(snapshot, char_limit=50000)
    package_contexts = build_coinglass_package_contexts(snapshot, char_limit=0)

    # Format endpoint summaries for prompt
    summary_block = format_endpoint_summaries_for_prompt(endpoint_summaries)

    # --- Write detailed report ---
    report_path = OUTPUT_DIR / f"coinglass_pipeline_report_{timestamp}.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"CoinGlass Pipeline Test Report\n")
        f.write(f"Symbol: BTC | Date: {timestamp}\n")
        f.write(f"Endpoints: {len(all_results)} total, {successful} ok, {len(all_results)-successful} failed\n")
        f.write(f"{'='*80}\n\n")
        f.write("=== PER-ENDPOINT DETAIL (Stages 1-4) ===\n")
        f.write("\n".join(report_lines))
        f.write(f"\n\n{'='*80}\n")
        f.write("=== STAGE 5: ENDPOINT SUMMARY LAYER (format_endpoint_summaries_for_prompt) ===\n")
        f.write(summary_block)
        f.write(f"\n\n{'='*80}\n")
        f.write("=== STAGE 5: FULL PROMPT CONTEXT (build_coinglass_prompt_context) ===\n")
        f.write(full_context)
        f.write(f"\n\n{'='*80}\n")
        f.write("=== STAGE 5: PER-PACKAGE CONTEXTS (build_coinglass_package_contexts) ===\n")
        for pkg_key, pkg_text in package_contexts.items():
            f.write(f"\n--- Package: {pkg_key} ---\n")
            f.write(pkg_text)
            f.write("\n")

    print(f"\nDetailed report saved to: {report_path}")

    # --- Summary analysis ---
    print(f"\n{'='*80}")
    print("DATA LOSS ANALYSIS SUMMARY")
    print(f"{'='*80}\n")

    loss_report: list[str] = []

    for result in all_results:
        key = result.get("key")
        title = result.get("title")
        status = result.get("status")
        payload = result.get("payload")
        summary = result.get("summary") or {}
        prompt_line = _format_coinglass_prompt_result_line(result)
        endpoint_summary = summarize_endpoint_result(
            endpoint_name=str(result.get("key") or result.get("title") or "endpoint"),
            request_metadata={"path": result.get("path"), "params": result.get("params") or {}, "source": result.get("source")},
            endpoint_result=result,
            symbol="BTC",
            analysis_date=analysis_date,
        )

        if status != "ok":
            loss_report.append(f"  [{key}] FAILED: {result.get('error')}")
            continue

        # Check for time field presence
        raw_fields = summary.get("fields") or []
        time_field_in_raw = any("time" in str(f).lower() or "date" in str(f).lower() for f in raw_fields)

        # Check if time field survived in prompt line
        time_in_prompt = "Date" in str(prompt_line) or "timestamp" in str(prompt_line).lower()

        # Check sample/latest items
        sample_items = summary.get("sample_items")
        latest_items = summary.get("latest_items")
        has_sample_data = bool(sample_items or latest_items)

        # Check fields count
        field_count = len(raw_fields) if isinstance(raw_fields, list) else 0
        fields_in_prompt = _safe_str(raw_fields[:4])

        issues: list[str] = []
        if time_field_in_raw and not time_in_prompt:
            issues.append("TIME FIELD LOST in prompt line")
        if has_sample_data and "recent=" not in prompt_line and "sample=" not in prompt_line:
            issues.append("SAMPLE DATA LOST in prompt line")
        if field_count > 4:
            issues.append(f"FIELDS TRUNCATED from {field_count} to 4: {fields_in_prompt}...")

        # Check if endpoint summary has direction
        direction = endpoint_summary.get("direction")
        if not direction or direction == "neutral":
            # Check if there's actually directional data
            numeric = summary.get("numeric_summary") or {}
            if numeric and any(v.get("latest") for v in numeric.values()):
                issues.append(f"DIRECTION defaulted to '{direction}' despite numeric data: {_safe_str(numeric)[:200]}")

        if issues:
            loss_report.append(f"  [{key}] {title}:")
            for issue in issues:
                loss_report.append(f"       - {issue}")
        else:
            loss_report.append(f"  [{key}] {title}: OK")

    print("\n".join(loss_report))

    # Save loss report
    loss_path = OUTPUT_DIR / f"coinglass_loss_report_{timestamp}.txt"
    with open(loss_path, "w", encoding="utf-8") as f:
        f.write("\n".join(loss_report))
    print(f"\nLoss report saved to: {loss_path}")

    # Save raw payloads for manual inspection
    payloads_path = OUTPUT_DIR / f"coinglass_raw_payloads_{timestamp}.json"
    with open(payloads_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"Raw results (with payloads) saved to: {payloads_path}")


if __name__ == "__main__":
    main()
