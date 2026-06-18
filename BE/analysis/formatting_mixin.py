from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from ..config import logger


class AnalysisFormattingMixin:

    @staticmethod
    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def _trim_text(value: str, limit: int) -> str:
        if limit <= 0 or len(value) <= limit:
            return value
        suffix = "\n\n[truncated by configured trace limit]"
        safe_limit = max(0, limit - len(suffix))
        return value[:safe_limit].rstrip() + suffix

    @staticmethod
    def _try_parse_json(value: str) -> object | None:
        text = (value or "").strip()
        if not text or text[0] not in "[{":
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @classmethod
    def _unwrap_tool_display_payload(cls, value: object) -> object:
        if isinstance(value, str):
            parsed = cls._try_parse_json(value)
            return cls._unwrap_tool_display_payload(parsed) if parsed is not None else value.strip()

        if isinstance(value, list):
            if len(value) == 1:
                return cls._unwrap_tool_display_payload(value[0])
            return [cls._unwrap_tool_display_payload(item) for item in value]

        if isinstance(value, dict):
            block_type = str(value.get("type") or "").strip().lower()
            if block_type == "text" and isinstance(value.get("text"), str):
                return cls._unwrap_tool_display_payload(value.get("text") or "")
            if set(value.keys()) == {"content"}:
                return cls._unwrap_tool_display_payload(value.get("content"))
        return value

    @staticmethod
    def _format_search_result_items(items: list[object]) -> list[str]:
        lines: list[str] = []
        for item in items:
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or item.get("query") or item.get("link") or "Untitled").strip()
                link = str(item.get("link") or item.get("url") or "").strip()
                snippet = str(item.get("snippet") or item.get("description") or item.get("summary") or "").strip()
                date = str(item.get("date") or item.get("published") or item.get("published_at") or "").strip()
            else:
                title = str(item).strip()
                link = ""
                snippet = ""
                date = ""

            if not title:
                continue

            lines.append(f"- [{title}]({link})" if link else f"- {title}")
            if date:
                lines.append(f"  Date: {date}")
            if snippet:
                lines.append(f"  {snippet}")

        return lines

    @classmethod
    def format_tool_result_for_display(cls, content: object) -> str:
        payload = cls._unwrap_tool_display_payload(content)

        if isinstance(payload, dict):
            lines: list[str] = []
            answer = str(payload.get("answer") or payload.get("summary") or "").strip()
            if answer:
                lines.append(answer)

            organic = payload.get("organic")
            if isinstance(organic, list) and organic:
                if lines:
                    lines.append("")
                lines.append("Search results:")
                lines.extend(cls._format_search_result_items(organic))

            news = payload.get("news") or payload.get("top_stories")
            if isinstance(news, list) and news:
                if lines:
                    lines.append("")
                lines.append("Related news:")
                lines.extend(cls._format_search_result_items(news))

            related_searches = payload.get("related_searches")
            if isinstance(related_searches, list) and related_searches:
                related_queries = [
                    str(item.get("query") or "").strip() if isinstance(item, dict) else str(item).strip()
                    for item in related_searches
                ]
                related_queries = [item for item in related_queries if item]
                if related_queries:
                    if lines:
                        lines.append("")
                    lines.append("Related searches: " + "; ".join(related_queries))

            if lines:
                return "\n".join(lines).strip()

            return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n```"

        if isinstance(payload, list):
            return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n```"

        return str(payload or "").strip()

    @staticmethod
    def _slugify_artifact_key(value: object, fallback: str = "artifact") -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
        return slug[:96] or fallback

    @classmethod
    def _classify_tool_source(cls, *, agent: object, title: object) -> dict | None:
        agent_text = str(agent or "").strip().lower()
        title_text = str(title or "").strip().lower()
        if title_text in {"get_crypto_ohlcv", "get_crypto_indicators"}:
            return {
                "flow_group": "ccxt_market_data",
                "source_kind": "ccxt",
                "label": "CCXT Market Data",
            }
        if title_text in {"get_news", "get_global_news", "get_finnhub_news"} or "news" in title_text:
            return {
                "flow_group": "news_data",
                "source_kind": "news",
                "label": "News Data",
            }
        if title_text == "web_search":
            if "social" in agent_text:
                return {
                    "flow_group": "social_web_data",
                    "source_kind": "web_search",
                    "label": "Social / Web Data",
                }
            if "news" in agent_text:
                return {
                    "flow_group": "news_data",
                    "source_kind": "web_search",
                    "label": "News / Web Data",
                }
            return {
                "flow_group": "social_web_data",
                "source_kind": "web_search",
                "label": "Web Data",
            }
        if "reddit" in title_text or "stocktwits" in title_text or "social" in title_text:
            return {
                "flow_group": "social_web_data",
                "source_kind": "social",
                "label": "Social / Web Data",
            }
        return None

    @classmethod
    def _build_tool_source_artifact(
        cls,
        *,
        agent: object,
        title: object,
        trace_id: object,
        content: object,
        call_content: object = "",
    ) -> dict | None:
        classification = cls._classify_tool_source(agent=agent, title=title)
        if classification is None:
            return None
        raw_content = cls.format_tool_result_for_display(content)
        if not raw_content:
            return None
        agent_label = str(agent or "Tool Runner").strip() or "Tool Runner"
        tool_name = str(title or "tool").strip() or "tool"
        source_key = str(trace_id or tool_name).strip() or tool_name
        call_text = str(call_content or "").strip()
        fingerprint = hashlib.sha1(
            json.dumps(
                {
                    "agent": agent_label,
                    "title": tool_name,
                    "trace_id": source_key,
                    "call": call_text,
                    "content": raw_content,
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8", errors="ignore")
        ).hexdigest()[:12]
        section_key = f"source_{classification['flow_group']}_{cls._slugify_artifact_key(tool_name)}_{fingerprint}"
        # Cap content to avoid holding unbounded strings in final_state.
        capped_content = cls._trim_text(raw_content, 32_768)
        markdown = "\n".join(
            [
                f"# {classification['label']} - {tool_name}",
                "",
                f"- Agent: {agent_label}",
                f"- Tool: {tool_name}",
                f"- Trace ID: {source_key}",
                f"- Captured at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
                "",
                "## Tool call",
                "```text",
                call_text or f"{tool_name}()",
                "```",
                "",
                "## Result",
                capped_content,
            ]
        )
        return {
            "section_key": section_key,
            "title": f"{classification['label']} - {tool_name}",
            "agent": agent_label,
            "team": "Source Layer",
            "markdown": markdown,
            "artifact_type": "source",
            "flow_stage": "summaries",
            "flow_group": classification["flow_group"],
            "source_kind": classification["source_kind"],
            "source_key": source_key,
            "summary": call_text or source_key,
            "payload_json": cls._trim_text(
                json.dumps(
                    {
                        "agent": agent_label,
                        "tool": tool_name,
                        "trace_id": source_key,
                        "call": call_text,
                        "content": capped_content,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
                32_768,
            ),
        }

    @classmethod
    def _build_coinglass_source_artifact(cls, result: dict) -> dict | None:
        if not isinstance(result, dict):
            return None
        endpoint_key = str(result.get("key") or result.get("title") or "coinglass").strip()
        if not endpoint_key:
            return None
        payload = result.get("payload")
        markdown_payload = cls._build_coinglass_tool_result_payload(result).get("answer") or ""
        # Cap raw payload to 32 KB to prevent memory bloat in final_state.
        raw_payload_str = ""
        if payload not in (None, "", [], {}):
            json_str = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            capped_json_str = cls._trim_text(json_str, 32_768)
            raw_payload_str = "\n".join(
                [
                    "## Raw endpoint response",
                    "```json",
                    capped_json_str,
                    "```",
                ]
            )
        markdown = "\n\n".join(
            part
            for part in [
                f"# CoinGlass Data - {result.get('title') or endpoint_key}",
                markdown_payload,
                raw_payload_str,
            ]
            if str(part or "").strip()
        )
        # Serialize payload_json to string once; cap at 32 KB to keep final_state lean.
        payload_summary = result.get("summary") or {}
        inner_payload = {
            "endpoint": endpoint_key,
            "title": result.get("title"),
            "source": result.get("source"),
            "status": result.get("status"),
            "http_status": result.get("http_status"),
            "elapsed_ms": result.get("elapsed_ms"),
            "summary": payload_summary,
            "payload": payload,
            "error": result.get("error") or "",
        }
        capped_inner_payload = cls._trim_text(
            json.dumps(inner_payload, ensure_ascii=False, sort_keys=True, default=str),
            32_768,
        )
        return {
            "section_key": f"source_coinglass_data_{cls._slugify_artifact_key(endpoint_key)}",
            "title": f"CoinGlass - {result.get('title') or endpoint_key}",
            "agent": "CoinGlass Prefetch",
            "team": "Source Layer",
            "markdown": markdown,
            "artifact_type": "source",
            "flow_stage": "summaries",
            "flow_group": "coinglass_data",
            "source_kind": "coinglass",
            "source_key": endpoint_key,
            "summary": str(result.get("source") or endpoint_key),
            # Always store as string — never keep a dict reference alongside the rendered string.
            "payload_json": capped_inner_payload,
        }

    @staticmethod
    def _normalize_message_content(content: object) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("content") or block.get("thinking")
                    if text:
                        parts.append(str(text).strip())
                elif block:
                    parts.append(str(block).strip())
            return "\n".join(part for part in parts if part).strip()
        if content is None:
            return ""
        return str(content).strip()

    @staticmethod
    def _tool_call_summary(tool_call: dict) -> str:
        name = str(tool_call.get("name") or "tool")
        args = tool_call.get("args") or {}
        if not args:
            return name
        if isinstance(args, dict):
            items = ", ".join(f"{key}={value}" for key, value in list(args.items())[:4])
            return f"{name}({items})"
        return f"{name}({args})"

    @classmethod
    def _format_coinglass_endpoint_call(cls, result: dict) -> str:
        source = str(result.get("source") or result.get("path") or "CoinGlass endpoint")
        package_label = str(result.get("package_label") or result.get("package") or "CoinGlass")
        params = result.get("params") or {}
        param_text = ""
        if isinstance(params, dict) and params:
            param_text = ", ".join(f"{key}={value}" for key, value in list(params.items())[:6])

        lines = [f"Source: {source}", f"Package: {package_label}"]
        if param_text:
            lines.append(f"Input: {param_text}")
        return "\n".join(lines)

    @staticmethod
    def _format_coinglass_markdown_cell(value: object) -> str:
        if value in (None, "", [], {}):
            return "-"
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        else:
            text = str(value)
        return text.replace("\n", " ").replace("|", "\\|").strip() or "-"

    @classmethod
    def _build_coinglass_markdown_table(cls, title: str, rows: object) -> str:
        if not isinstance(rows, list) or not rows:
            return ""

        normalized_rows = [row for row in rows if isinstance(row, dict) and row]
        if not normalized_rows:
            return ""

        columns: list[str] = []
        for row in normalized_rows:
            for key in row.keys():
                label = str(key).strip()
                if not label or label == "..." or label in columns:
                    continue
                columns.append(label)

        if not columns:
            return ""

        lines = [
            f"### {title}",
            "| " + " | ".join(columns) + " |",
            "| " + " | ".join("---" for _ in columns) + " |",
        ]
        for row in normalized_rows:
            values = [cls._format_coinglass_markdown_cell(row.get(column)) for column in columns]
            lines.append("| " + " | ".join(values) + " |")
        return "\n".join(lines)

    @classmethod
    def _build_coinglass_tool_result_payload(cls, result: dict) -> dict[str, str]:
        source = str(result.get("source") or result.get("path") or "CoinGlass endpoint")
        package_label = str(result.get("package_label") or result.get("package") or "CoinGlass")
        status = str(result.get("status") or "unknown")
        http_status = result.get("http_status")
        elapsed_ms = result.get("elapsed_ms")
        summary = result.get("summary") or {}
        rate_limit = result.get("rate_limit") or {}

        meta_rows: list[tuple[str, object]] = [
            ("Source", source),
            ("Package", package_label),
            ("Status", status),
            ("HTTP status", http_status),
            ("Elapsed", f"{elapsed_ms}ms" if elapsed_ms is not None else ""),
            ("API code", summary.get("api_code") if isinstance(summary, dict) else ""),
            ("API message", summary.get("api_message") if isinstance(summary, dict) else ""),
            ("Rows", summary.get("item_count") if isinstance(summary, dict) else ""),
            ("Primary list", summary.get("primary_list_key") if isinstance(summary, dict) else ""),
            (
                "Rate limit",
                "; ".join(f"{key}={value}" for key, value in sorted(rate_limit.items())) if isinstance(rate_limit, dict) else "",
            ),
        ]

        lines = [
            "### API response",
            "| Field | Value |",
            "| --- | --- |",
        ]
        for label, value in meta_rows:
            if value in (None, "", [], {}):
                continue
            lines.append(f"| {label} | {cls._format_coinglass_markdown_cell(value)} |")

        if isinstance(summary, dict):
            fields = summary.get("fields") or summary.get("keys") or []
            if isinstance(fields, list) and fields:
                lines.extend([
                    "",
                    "### Fields",
                    ", ".join(f"`{cls._format_coinglass_markdown_cell(field)}`" for field in fields),
                ])

            numeric_summary = summary.get("numeric_summary") or {}
            if isinstance(numeric_summary, dict) and numeric_summary:
                lines.extend([
                    "",
                    "### Latest metrics",
                    "| Metric | Latest |",
                    "| --- | --- |",
                ])
                for key, values in numeric_summary.items():
                    if not isinstance(values, dict):
                        continue
                    latest = values.get("latest")
                    if latest in (None, ""):
                        continue
                    lines.append(
                        f"| {cls._format_coinglass_markdown_cell(key)} | {cls._format_coinglass_markdown_cell(latest)} |"
                    )

            sample_title = str(summary.get("sample_title") or "Sample rows").strip() or "Sample rows"
            sample_table = cls._build_coinglass_markdown_table(sample_title, summary.get("sample_items"))
            if sample_table:
                lines.extend(["", sample_table])

            latest_title = str(summary.get("latest_title") or "Recent rows").strip() or "Recent rows"
            recent_table = cls._build_coinglass_markdown_table(latest_title, summary.get("latest_items"))
            if recent_table:
                lines.extend(["", recent_table])
            elif summary.get("data") not in (None, "", [], {}):
                lines.extend([
                    "",
                    "### Data preview",
                    "```json",
                    json.dumps(summary.get("data"), ensure_ascii=False, indent=2, sort_keys=True, default=str),
                    "```",
                ])

            table_limit_warning = summary.get("table_limit_warning")
            if table_limit_warning:
                lines.extend(["", f"> **Warning:** {table_limit_warning}"])

        error = str(result.get("error") or "").strip()
        if error:
            lines.extend(["", f"> Error: {error}"])

        return {
            "type": "coinglass_api_result",
            "answer": "\n".join(lines).strip(),
        }

    @classmethod
    def _format_coinglass_endpoint_result(cls, result: dict) -> str:
        source = str(result.get("source") or result.get("path") or "CoinGlass endpoint")
        package_label = str(result.get("package_label") or result.get("package") or "CoinGlass")
        status = str(result.get("status") or "unknown")
        http_status = result.get("http_status")
        elapsed_ms = result.get("elapsed_ms")
        summary = result.get("summary") or {}
        rate_limit = result.get("rate_limit") or {}

        lines = [f"Source: {source}", f"Package: {package_label}", f"Status: {status}"]
        if http_status is not None:
            lines.append(f"HTTP status: {http_status}")
        if elapsed_ms is not None:
            lines.append(f"Elapsed: {elapsed_ms}ms")
        if isinstance(summary, dict) and summary:
            api_code = summary.get("api_code")
            if api_code not in (None, ""):
                lines.append(f"API code: {api_code}")
            api_message = str(summary.get("api_message") or "").strip()
            if api_message:
                lines.append(f"API message: {api_message}")
            item_count = summary.get("item_count")
            if item_count is not None:
                lines.append(f"Rows: {item_count}")
            primary_list_key = str(summary.get("primary_list_key") or "").strip()
            if primary_list_key:
                lines.append(f"Primary list: {primary_list_key}")
            fields = summary.get("fields") or summary.get("keys") or []
            if isinstance(fields, list) and fields:
                field_labels = ", ".join(str(field) for field in fields[:8])
                if len(fields) > 8:
                    field_labels += ", ..."
                lines.append(f"Fields: {field_labels}")
            numeric_summary = summary.get("numeric_summary") or {}
            if isinstance(numeric_summary, dict) and numeric_summary:
                metric_parts: list[str] = []
                for key, values in list(numeric_summary.items())[:4]:
                    if not isinstance(values, dict):
                        continue
                    latest = values.get("latest")
                    if latest in (None, ""):
                        continue
                    metric_parts.append(f"{key}={latest}")
                if metric_parts:
                    lines.append(f"Latest metrics: {', '.join(metric_parts)}")
            sample_items = summary.get("sample_items")
            if sample_items not in (None, "", [], {}):
                lines.append(
                    "Sample rows: "
                    + cls._trim_text(json.dumps(sample_items, ensure_ascii=False, sort_keys=True, default=str), 420)
                )
            latest_items = summary.get("latest_items")
            if latest_items not in (None, "", [], {}):
                lines.append(
                    "Recent rows: "
                    + cls._trim_text(json.dumps(latest_items, ensure_ascii=False, sort_keys=True, default=str), 420)
                )
            elif summary.get("data") not in (None, "", [], {}):
                lines.append(
                    "Data: "
                    + cls._trim_text(json.dumps(summary.get("data"), ensure_ascii=False, sort_keys=True, default=str), 320)
                )
        error = str(result.get("error") or "").strip()
        if error:
            lines.append(f"Error: {error}")
        if isinstance(rate_limit, dict) and rate_limit:
            rate_limit_text = ", ".join(f"{key}={value}" for key, value in sorted(rate_limit.items()))
            if rate_limit_text:
                lines.append(f"Rate limit: {rate_limit_text}")
        return "\n".join(lines)

    @classmethod
    def _build_message_signature(cls, message: object) -> str:
        raw_signature = ""
        if hasattr(message, "id") and getattr(message, "id"):
            raw_signature = str(getattr(message, "id"))
        else:
            raw_signature = json.dumps(
                {
                    "type": message.__class__.__name__,
                    "name": getattr(message, "name", ""),
                    "content": cls._normalize_message_content(getattr(message, "content", "")),
                    "tool_calls": getattr(message, "tool_calls", []),
                },
                sort_keys=True,
                default=str,
            )
        return hashlib.sha1(raw_signature.encode("utf-8", errors="ignore")).hexdigest()
