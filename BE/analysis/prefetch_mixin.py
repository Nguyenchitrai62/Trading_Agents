from __future__ import annotations

from collections.abc import Callable

from ..config import logger
from tradingagents.dataflows.coinglass_client import (
    build_coinglass_evidence_items,
    build_coinglass_package_contexts,
    build_coinglass_prompt_context,
    fetch_high_value_snapshot,
)
from tradingagents.dataflows.endpoint_summary import (
    build_endpoint_summaries,
    endpoint_summaries_to_evidence_items,
    format_endpoint_summaries_for_prompt,
)


class AnalysisPrefetchMixin:

    def fetch_coinglass_context(
        self,
        *,
        symbol: str,
        analysis_date: str,
        owner_agent_key: str,
        owner_agent_label: str,
        emit: Callable[[str, dict], None],
        emit_analysis_log: Callable[..., None],
        ensure_not_cancelled: Callable[[], None],
        record_source_artifact: Callable[[dict], None] | None = None,
    ) -> tuple[str, dict[str, str], list[dict], list[dict], list[dict]]:
        if not self.settings.coinglass_enabled:
            emit_analysis_log("CoinGlass prefetch is disabled by configuration.", "coinglass", "warning")
            return "", {}, [], [], []

        if not self.settings.coinglass_api_key:
            message = (
                "CoinGlass API key is not configured. Set COINGLASS_API_KEY, COINGLASS-API-KEY, "
                "CG_API_KEY, or CG-API-KEY in .env to enable high-value realtime market context."
            )
            emit_analysis_log(message, "coinglass", "warning")
            emit("warning", {"message": message})
            return "", {}, [], [], []

        emit_analysis_log(
            "Prefetching CoinGlass high-value market context.",
            "coinglass",
            base_url=self.settings.coinglass_base_url,
            concurrency_limit=self.settings.coinglass_concurrency_limit,
            owner_agent=owner_agent_label,
        )

        def on_endpoint_result(result: dict) -> None:
            endpoint_title = str(result.get("title") or result.get("key") or "CoinGlass endpoint")
            trace_id = f"coinglass:{result.get('key') or endpoint_title}"
            if record_source_artifact is not None:
                artifact = self._build_coinglass_source_artifact(result)
                if artifact:
                    record_source_artifact(artifact)
            emit(
                "agent_trace",
                {
                    "agent": owner_agent_label,
                    "phase": "tool_call",
                    "title": endpoint_title,
                    "trace_id": trace_id,
                    "content": self._trim_text(
                        self._format_coinglass_endpoint_call(result),
                        self.settings.analysis_trace_char_limit,
                    ),
                },
            )

            if result.get("status") == "ok":
                summary = result.get("summary") or {}
                emit_analysis_log(
                    "CoinGlass endpoint fetched.",
                    "coinglass",
                    endpoint=result.get("key"),
                    package=result.get("package"),
                    http_status=result.get("http_status"),
                    elapsed_ms=result.get("elapsed_ms"),
                    item_count=summary.get("item_count"),
                    rate_limit=result.get("rate_limit") or {},
                )
                emit(
                    "agent_trace",
                    {
                        "agent": owner_agent_label,
                        "phase": "tool_result",
                        "title": endpoint_title,
                        "trace_id": trace_id,
                        "content": self._build_coinglass_tool_result_payload(result),
                    },
                )
                return

            title = result.get("title") or result.get("key") or "CoinGlass endpoint"
            error = result.get("error") or "unknown error"
            emit_analysis_log(
                "CoinGlass endpoint failed; continuing analysis without this slice.",
                "coinglass",
                "warning",
                endpoint=result.get("key"),
                package=result.get("package"),
                http_status=result.get("http_status"),
                elapsed_ms=result.get("elapsed_ms"),
                error=error,
                rate_limit=result.get("rate_limit") or {},
            )
            emit(
                "agent_trace",
                {
                    "agent": owner_agent_label,
                    "phase": "tool_result",
                    "title": endpoint_title,
                    "trace_id": trace_id,
                    "content": self._build_coinglass_tool_result_payload(result),
                },
            )
            emit("warning", {"message": f"{title} unavailable from CoinGlass: {error}"})

        snapshot = fetch_high_value_snapshot(
            api_key=self.settings.coinglass_api_key,
            symbol=symbol,
            base_url=self.settings.coinglass_base_url,
            timeout_seconds=self.settings.coinglass_timeout_seconds,
            request_interval_seconds=self.settings.coinglass_request_interval_seconds,
            concurrency_limit=self.settings.coinglass_concurrency_limit,
            on_endpoint_result=on_endpoint_result,
            cancel_check=ensure_not_cancelled,
        )
        endpoint_summary_cache: dict[str, dict] = {}
        endpoint_summaries = build_endpoint_summaries(
            snapshot.get("results") or [],
            symbol=symbol,
            analysis_date=analysis_date,
            max_workers=self.settings.coinglass_concurrency_limit,
            cache=endpoint_summary_cache,
        )
        snapshot["endpoint_summaries"] = endpoint_summaries
        if endpoint_summaries:
            emit_analysis_log(
                "CoinGlass endpoint summaries ready.",
                "coinglass",
                summary_count=len(endpoint_summaries),
                cache_entries=len(endpoint_summary_cache),
            )
            emit(
                "endpoint_summary",
                {
                    "items": endpoint_summaries,
                    "count": len(endpoint_summaries),
                },
            )
            emit(
                "agent_trace",
                {
                    "agent": owner_agent_label,
                    "phase": "analysis",
                    "title": "Endpoint summaries",
                    "trace_id": "coinglass:endpoint_summaries",
                    "content": self._trim_text(
                        format_endpoint_summaries_for_prompt(endpoint_summaries),
                        self.settings.analysis_trace_char_limit,
                    ),
                },
            )
        prompt_context = build_coinglass_prompt_context(
            snapshot,
            char_limit=self.settings.coinglass_context_char_limit,
        )
        package_contexts = build_coinglass_package_contexts(
            snapshot,
            char_limit=self.settings.coinglass_package_context_char_limit,
        )
        evidence_items = build_coinglass_evidence_items(
            snapshot,
            analysis_date,
            owner_agent_key=owner_agent_key,
            owner_agent_label=owner_agent_label,
        )
        evidence_items.extend(
            endpoint_summaries_to_evidence_items(
                endpoint_summaries,
                owner_agent_key=owner_agent_key,
                owner_agent_label=owner_agent_label,
                analysis_date=analysis_date,
            )
        )

        emit_analysis_log(
            "CoinGlass high-value context ready.",
            "coinglass",
            endpoint_count=snapshot.get("endpoint_count"),
            successful_endpoint_count=snapshot.get("successful_endpoint_count"),
            failed_endpoint_count=snapshot.get("failed_endpoint_count"),
            evidence_count=len(evidence_items),
            context_chars=len(prompt_context),
        )
        if prompt_context:
            emit(
                "agent_trace",
                {
                    "agent": owner_agent_label,
                    "phase": "analysis",
                    "title": "CoinGlass high-value snapshot",
                    "trace_id": "coinglass:snapshot",
                    "content": self._trim_text(prompt_context, self.settings.analysis_trace_char_limit),
                },
            )
        if evidence_items:
            emit(
                "evidence_update",
                {
                    "items": evidence_items,
                    "count": len(evidence_items),
                },
            )
        return prompt_context, package_contexts, evidence_items, endpoint_summaries, list(snapshot.get("results") or [])
