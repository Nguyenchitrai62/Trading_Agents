from __future__ import annotations

import asyncio
import contextlib
import gc
import json
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable
from concurrent.futures import TimeoutError as FutureTimeoutError

from fastapi import HTTPException, Request

from ..analysis_telemetry import (
    AnalysisCancelled,
    AnalysisLogStream,
    AnalysisLoggingHandler,
    AnalysisTelemetry,
    AnalysisTelemetryCallback,
    get_process_rss_mb,
)
from ..config import logger, resolve_provider_settings, is_deepseek_model
from ..history import build_history_sections
from ..models import AnalysisRequest

from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS

try:
    from tradingagents.graph.checkpointer import (
        checkpoint_step,
        clear_checkpoint,
        get_checkpointer,
        thread_id,
    )
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ORCHESTRATOR_IMPORT_OK = True
except ModuleNotFoundError:
    checkpoint_step = None
    clear_checkpoint = None
    get_checkpointer = None
    thread_id = None
    TradingAgentsGraph = None
    ORCHESTRATOR_IMPORT_OK = False


class AnalysisOrchestratorMixin:

    def run_trading_analysis(
        self,
        request: AnalysisRequest,
        emit: Callable[[str, dict], None],
        user: dict,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.ensure_analysis_runtime_available()
        provider_settings = resolve_provider_settings(request.model, self.settings)
        if not provider_settings["configured"]:
            provider = provider_settings.get("provider")
            if is_deepseek_model(request.model):
                raise HTTPException(
                    status_code=500,
                    detail="Set DEEPSEEK_API_KEY in .env before running analysis.",
                )
            raise HTTPException(
                status_code=500,
                detail="Set MINIMAX_API_KEY or MINIMAX_CN_API_KEY in .env before running analysis.",
            )

        cancel_event = cancel_event or threading.Event()
        run_started_at = time.time()
        symbol = self.normalize_ticker_symbol(request.symbol)
        runtime_profile = self.build_analysis_runtime_profile(request)
        telemetry = AnalysisTelemetry()
        telemetry_callback = AnalysisTelemetryCallback(telemetry)
        source_artifacts: list[dict] = []
        seen_source_artifacts: set[str] = set()
        pending_tool_calls: dict[str, str] = {}

        def source_trace_key(agent: object, title: object, trace_id: object) -> str:
            return "|".join(
                str(part or "").strip().lower()
                for part in (agent, title, trace_id)
            )

        def record_source_artifact(artifact: dict) -> None:
            section_key = str(artifact.get("section_key") or "").strip()
            if not section_key or section_key in seen_source_artifacts:
                return
            markdown = str(artifact.get("markdown") or "").strip()
            if not markdown:
                return
            seen_source_artifacts.add(section_key)
            source_artifacts.append(artifact)

        def record_tool_call_artifact_input(*, agent: object, title: object, trace_id: object, content: object) -> None:
            pending_tool_calls[source_trace_key(agent, title, trace_id)] = str(content or "").strip()

        def record_tool_source_artifact(*, agent: object, title: object, trace_id: object, content: object) -> None:
            call_content = pending_tool_calls.get(source_trace_key(agent, title, trace_id), "")
            artifact = self._build_tool_source_artifact(
                agent=agent,
                title=title,
                trace_id=trace_id,
                content=content,
                call_content=call_content,
            )
            if artifact:
                record_source_artifact(artifact)

        def emit_analysis_log(
            message: str,
            phase: str = "backend",
            level: str = "info",
            write_logger: bool = True,
            **extra: object,
        ) -> None:
            payload = {
                "level": level,
                "phase": phase,
                "message": message,
                "elapsed_seconds": round(time.time() - run_started_at, 2),
                **extra,
            }
            rss_mb = get_process_rss_mb()
            if rss_mb is not None:
                payload["rss_mb"] = rss_mb
            extra_json = json.dumps(extra, ensure_ascii=False, default=str) if extra else "{}"
            payload["log_line"] = (
                f"analysis symbol={symbol} phase={phase} elapsed={payload['elapsed_seconds']}s "
                f"message={message} extra={extra_json}"
            )
            if write_logger:
                log_method = logger.warning if level == "warning" else logger.info
                log_method(
                    "analysis symbol=%s phase=%s elapsed=%ss message=%s extra=%s",
                    symbol,
                    phase,
                    payload["elapsed_seconds"],
                    message,
                    extra,
                )
            emit("analysis_log", payload)

        def ensure_not_cancelled() -> None:
            if cancel_event.is_set():
                emit_analysis_log("Analysis cancellation requested; stopping active graph run.", "cancelled", "warning")
                raise AnalysisCancelled()

        graph = None
        asset_type = self.settings.default_asset_type
        filtered_analysts = self.filter_analysts_for_crypto(request.selected_analysts)
        if not filtered_analysts:
            raise HTTPException(status_code=400, detail="No valid analysts remain for crypto analysis.")

        config = self.build_analysis_config(request, provider_settings, runtime_profile, filtered_analysts)
        initial_snapshot = self.extract_runtime_snapshot({})
        analyst_parallel_enabled = (
            int(config.get("analyst_concurrency_limit") or 1) > 1
            and len(filtered_analysts) > 1
        )
        current_agent = "Analyst Team" if analyst_parallel_enabled else ANALYST_NODE_SPECS[filtered_analysts[0]].agent_node
        initial_status = self.build_status_snapshot(
            initial_snapshot,
            filtered_analysts,
            current_agent,
            max_debate_rounds=int(config.get("max_debate_rounds") or 1),
            max_risk_rounds=int(config.get("max_risk_discuss_rounds") or 1),
        )
        emit(
            "analysis_meta",
            {
                "symbol": symbol,
                "asset_type_mode": request.asset_type,
                "analysis_date": request.analysis_date,
                "lookback_days": request.lookback_days,
                "asset_type": asset_type,
                "output_language": request.output_language,
                "research_depth": request.research_depth,
                "effective_research_depth": runtime_profile["effective_depth"] or request.research_depth,
                "depth_rounds": runtime_profile["effective_rounds"],
                "mcp_max_tool_rounds": runtime_profile["mcp_max_tool_rounds"],
                "auto_escalation_enabled": runtime_profile.get("auto_escalation", False),
                "model": request.model,
                "llm_max_tokens": runtime_profile["llm_max_tokens"],
                "resource_constrained": self.settings.resource_constrained_mode,
                "selected_analysts": filtered_analysts,
                "selected_analyst_labels": [ANALYST_NODE_SPECS[key].agent_node for key in filtered_analysts],
                "analyst_concurrency_limit": int(config.get("analyst_concurrency_limit") or 1),
                "provider": provider_settings["provider"],
                "base_url": provider_settings["base_url"],
                "coinglass": {
                    "enabled": self.settings.coinglass_enabled,
                    "configured": bool(self.settings.coinglass_api_key),
                    "context_available": False,
                    "evidence_count": 0,
                    "concurrency_limit": self.settings.coinglass_concurrency_limit,
                    "owner_analyst_key": config.get("coinglass_owner_analyst"),
                    "owner_analyst_label": config.get("coinglass_owner_agent_label"),
                    "prefetch_pending": bool(self.settings.coinglass_enabled and self.settings.coinglass_api_key),
                },
                "initial_status": initial_status,
            },
        )
        emit("status_snapshot", initial_status)

        emit_analysis_log(
            "Request validated and runtime options resolved.",
            "prepare",
            requested_asset_type=request.asset_type,
            resolved_asset_type=asset_type,
            selected_analysts=filtered_analysts,
            lookback_days=request.lookback_days,
            research_depth=request.research_depth,
            effective_research_depth=runtime_profile["effective_depth"],
            effective_depth_rounds=runtime_profile["effective_rounds"],
            mcp_max_tool_rounds=runtime_profile["mcp_max_tool_rounds"],
            llm_max_tokens=runtime_profile["llm_max_tokens"],
            resource_constrained=self.settings.resource_constrained_mode,
            output_language=request.output_language,
        )

        if filtered_analysts != request.selected_analysts:
            emit_analysis_log(
                "Selected analyst list was adjusted for crypto analysis.",
                "prepare",
                "warning",
            )
            emit(
                "warning",
                {
                    "message": "Selected analyst list was adjusted automatically for crypto analysis.",
                },
            )

        ensure_not_cancelled()
        coinglass_context, coinglass_package_contexts, coinglass_evidence_items, endpoint_summaries, coinglass_endpoint_results = self.fetch_coinglass_context(
            symbol=symbol,
            analysis_date=request.analysis_date,
            owner_agent_key=str(config.get("coinglass_owner_analyst") or ""),
            owner_agent_label=str(config.get("coinglass_owner_agent_label") or "Analyst"),
            emit=emit,
            emit_analysis_log=emit_analysis_log,
            ensure_not_cancelled=ensure_not_cancelled,
            record_source_artifact=record_source_artifact,
        )
        ensure_not_cancelled()

        def emit_parallel_trace(trace: dict) -> None:
            if cancel_event.is_set():
                return
            phase = str(trace.get("phase") or "analysis")
            agent = trace.get("agent") or "Analyst"
            title = trace.get("title") or trace.get("agent") or "Analysis"
            trace_id = trace.get("trace_id") or trace.get("tool_call_id") or ""
            source_classification = self._classify_tool_source(agent=agent, title=title) or {}
            source_payload = (
                {
                    "source_group": source_classification.get("flow_group") or "",
                    "source_kind": source_classification.get("source_kind") or "",
                    "source_label": source_classification.get("label") or "",
                }
                if source_classification
                else {}
            )
            telemetry.record_tool_trace(phase, title)
            if phase == "tool_call":
                record_tool_call_artifact_input(
                    agent=agent,
                    title=title,
                    trace_id=trace_id or title or "tool",
                    content=trace.get("content") or "",
                )
            if phase == "tool_result":
                record_tool_source_artifact(
                    agent=agent,
                    title=title,
                    trace_id=trace_id or title or "tool",
                    content=trace.get("content") or "",
                )
            content = self._trim_text(
                self.format_tool_result_for_display(trace.get("content") or "")
                if phase == "tool_result"
                else self._normalize_message_content(trace.get("content") or ""),
                self.settings.analysis_trace_char_limit,
            )
            if not content:
                return
            emit(
                "agent_trace",
                {
                    "agent": agent,
                    "phase": phase,
                    "title": title,
                    "trace_id": trace_id,
                    "content": content,
                    **source_payload,
                },
            )

        config["analysis_trace_callback"] = emit_parallel_trace
        config["analysis_cancel_check"] = ensure_not_cancelled
        emit_analysis_log(
            "Building TradingAgents graph.",
            "graph_setup",
            provider=provider_settings["provider"],
            model=request.model,
            depth_rounds=runtime_profile["effective_rounds"],
            mcp_max_tool_rounds=runtime_profile["mcp_max_tool_rounds"],
            max_tokens=runtime_profile["llm_max_tokens"],
        )
        graph = TradingAgentsGraph(
            selected_analysts=filtered_analysts,
            debug=False,
            config=config,
            callbacks=[telemetry_callback],
        )

        ensure_not_cancelled()
        graph.ticker = symbol
        emit_analysis_log("Skipping stock outcome reflection for crypto analysis.", "memory")

        ensure_not_cancelled()
        if config.get("checkpoint_enabled"):
            emit_analysis_log("Checkpoint resume requested; preparing checkpointer.", "checkpoint")
            graph._checkpointer_ctx = get_checkpointer(config["data_cache_dir"], symbol)
            saver = graph._checkpointer_ctx.__enter__()
            graph.graph = graph.workflow.compile(checkpointer=saver)
            step = checkpoint_step(config["data_cache_dir"], symbol, request.analysis_date)
            emit(
                "warning",
                {
                    "message": (
                        f"Checkpoint resume enabled. Resuming from step {step}."
                        if step is not None
                        else "Checkpoint resume enabled. Starting fresh."
                    )
                },
            )

        def emit_captured_log(message: str, phase: str = "backend_log", level: str = "info") -> None:
            emit_analysis_log(message, phase, level, write_logger=False)

        tradingagents_logger = logging.getLogger("tradingagents")
        log_capture: AnalysisLoggingHandler | None = None
        stdout_stream: AnalysisLogStream | None = None
        stderr_stream: AnalysisLogStream | None = None
        stdout_redirect = None
        stderr_redirect = None
        if self.settings.analysis_verbose_runtime_logs:
            log_capture = AnalysisLoggingHandler(emit_captured_log)
            log_capture.setFormatter(logging.Formatter("%(levelname)s %(name)s - %(message)s"))
            stdout_stream = AnalysisLogStream(emit_captured_log, "backend_stdout", "info")
            stderr_stream = AnalysisLogStream(emit_captured_log, "backend_stderr", "warning")
            stdout_redirect = contextlib.redirect_stdout(stdout_stream)
            stderr_redirect = contextlib.redirect_stderr(stderr_stream)
            tradingagents_logger.addHandler(log_capture)
            stdout_redirect.__enter__()
            stderr_redirect.__enter__()

        final_state: dict = {}
        previous_snapshot = initial_snapshot
        previous_status = initial_status
        seen_message_signatures: set[str] = set()
        try:
            ensure_not_cancelled()
            past_context = ""
            emit_analysis_log("Creating initial graph state.", "graph_setup")
            init_state = graph.propagator.create_initial_state(
                symbol,
                request.analysis_date,
                asset_type=asset_type,
                past_context=past_context,
                coinglass_context=coinglass_context,
                coinglass_package_contexts=coinglass_package_contexts,
                coinglass_endpoint_results=coinglass_endpoint_results,
                coinglass_evidence_items=coinglass_evidence_items,
                endpoint_summaries=endpoint_summaries,
            )
            previous_snapshot = self.extract_runtime_snapshot(init_state)
            args = graph.propagator.get_graph_args()
            args["stream_mode"] = "updates"
            if config.get("checkpoint_enabled"):
                tid = thread_id(symbol, request.analysis_date)
                args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

            started_at = time.time()
            chunk_index = 0
            last_announced_agent = current_agent
            auto_depth_evaluated = False
            emit_analysis_log("Graph stream started.", "stream", current_agent=current_agent)
            final_state.update(init_state)
            final_state["messages"] = []
            for chunk in graph.graph.stream(init_state, **args):
                ensure_not_cancelled()
                for node_name, update in self.iter_graph_state_updates(chunk):
                    chunk_index += 1
                    updated_keys = self.merge_graph_state_update(final_state, update)
                    current_snapshot = self.extract_runtime_snapshot(final_state)

                    if runtime_profile.get("auto_escalation") and not auto_depth_evaluated:
                        quality = self.evaluate_evidence_quality(current_snapshot, filtered_analysts)
                        if quality["should_escalate"] or quality["score"] > 0:
                            spec_map = {
                                key: ANALYST_NODE_SPECS[key] for key in filtered_analysts if key in ANALYST_NODE_SPECS
                            }
                            all_complete = all(
                                current_snapshot.get("sections", {}).get(spec.report_key)
                                for spec in spec_map.values()
                            )
                            if all_complete:
                                auto_depth_evaluated = True
                                new_rounds = quality["escalated_rounds"]
                                old_rounds = graph.conditional_logic.max_debate_rounds
                                if new_rounds != old_rounds:
                                    graph.conditional_logic.max_debate_rounds = new_rounds
                                    graph.conditional_logic.max_risk_discuss_rounds = new_rounds
                                    config["max_debate_rounds"] = new_rounds
                                    config["max_risk_discuss_rounds"] = new_rounds
                                    emit(
                                        "depth_escalation",
                                        {
                                            "from_rounds": old_rounds,
                                            "from_label": {1: "quick", 3: "medium", 5: "deep"}.get(old_rounds, str(old_rounds)),
                                            "to_rounds": new_rounds,
                                            "to_label": quality["label"],
                                            "reason": quality["reason"],
                                            "quality_score": quality["score"],
                                            "evidence_summary": {
                                                "count": quality["evidence_count"],
                                                "mean_confidence": quality["confidence_mean"],
                                                "fresh_count": quality["fresh_count"],
                                                "low_confidence_count": quality["low_confidence_count"],
                                                "source_diversity": quality["source_diversity"],
                                                "agent_contributors": quality["agent_contributors"],
                                                "total_analysts": quality["total_analysts"],
                                            },
                                        },
                                    )
                                    emit_analysis_log(
                                        f"Auto depth escalated from {old_rounds} to {new_rounds} rounds ({quality['label']}): {quality['reason']}",
                                        "research",
                                        current_agent=current_agent,
                                    )
                                else:
                                    auto_depth_evaluated = True

                    current_agent = (
                        self.detect_current_agent(previous_snapshot, current_snapshot)
                        or self.graph_node_to_agent_label(node_name)
                        or current_agent
                    )
                    current_status = self.build_status_snapshot(
                        current_snapshot,
                        filtered_analysts,
                        current_agent,
                        max_debate_rounds=int(config.get("max_debate_rounds") or 1),
                        max_risk_rounds=int(config.get("max_risk_discuss_rounds") or 1),
                    )
                    emit_analysis_log(
                        "Graph emitted a state update.",
                        current_status["phase"],
                        chunk_index=chunk_index,
                        graph_node=node_name,
                        current_agent=current_agent,
                        updated_keys=updated_keys,
                        progress=current_status["progress"],
                    )
                    self.emit_message_progress_updates(
                        final_state.get("messages", []),
                        current_agent,
                        seen_message_signatures,
                        emit,
                        telemetry,
                        trace_sink=record_tool_source_artifact,
                        trace_call_sink=record_tool_call_artifact_input,
                    )
                    if final_state.get("messages"):
                        final_state["messages"] = []
                    self.emit_snapshot_updates(previous_snapshot, current_snapshot, emit)
                    if current_status != previous_status:
                        emit("status_snapshot", current_status)
                        previous_status = current_status
                    previous_snapshot = current_snapshot

                    max_debate_rounds = int(config.get("max_debate_rounds") or 1)
                    max_risk_rounds = int(config.get("max_risk_discuss_rounds") or 1)
                    next_agent = self.predict_next_graph_agent(
                        current_snapshot,
                        filtered_analysts,
                        max_debate_rounds=max_debate_rounds,
                        max_risk_rounds=max_risk_rounds,
                    )
                    if next_agent and next_agent != last_announced_agent:
                        next_phase = self.progress_phase_for_agent(next_agent)
                        next_status = self.build_status_snapshot(
                            current_snapshot,
                            filtered_analysts,
                            next_agent,
                            max_debate_rounds=max_debate_rounds,
                            max_risk_rounds=max_risk_rounds,
                        )
                        if next_agent == "Portfolio Manager" and current_snapshot.get("sections", {}).get("final_trade_decision"):
                            revision_count = int(current_snapshot.get("decision_revision_count") or 0)
                            verification = current_snapshot.get("structured", {}).get("verification_report") or {}
                            emit(
                                "verification_revision",
                                {
                                    "revision_count": revision_count,
                                    "max_revisions": 2,
                                    "previous_verdict": str(verification.get("verdict") or "Revise").strip(),
                                    "issues": verification.get("issues") or [],
                                    "message": f"Verifier requested revision {revision_count}/2. Portfolio Manager is re-evaluating the decision.",
                                },
                            )
                        emit_analysis_log(
                            self.agent_start_message(
                                next_agent,
                                current_snapshot,
                                max_debate_rounds=max_debate_rounds,
                                max_risk_rounds=max_risk_rounds,
                            ),
                            next_phase,
                            current_agent=next_agent,
                            graph_node=next_agent,
                            progress=next_status["progress"],
                        )
                        if next_status != previous_status:
                            emit("status_snapshot", next_status)
                            previous_status = next_status
                        current_agent = next_agent
                        last_announced_agent = next_agent
                    ensure_not_cancelled()

            if not final_state.get("final_trade_decision"):
                raise RuntimeError("Analysis finished without a final_trade_decision.")
            if not final_state.get("verification_report"):
                raise RuntimeError("Analysis finished without a verification_report.")

            graph.curr_state = final_state
            if config.get("checkpoint_enabled"):
                clear_checkpoint(config["data_cache_dir"], symbol, request.analysis_date)

            completed_snapshot = self.extract_runtime_snapshot(final_state)
            completed_status = self.build_status_snapshot(
                completed_snapshot,
                filtered_analysts,
                "Verifier",
                max_debate_rounds=int(config.get("max_debate_rounds") or 1),
                max_risk_rounds=int(config.get("max_risk_discuss_rounds") or 1),
            )
            completed_sections_patch = self.build_changed_sections(previous_snapshot.get("sections", {}), completed_snapshot["sections"])
            completed_research_patch = self.build_changed_fields(previous_snapshot.get("investment", {}), completed_snapshot["investment"])
            completed_risk_patch = self.build_changed_fields(previous_snapshot.get("risk", {}), completed_snapshot["risk"])
            final_progress_keys = set(completed_sections_patch)
            previous_structured = previous_snapshot.get("structured", {})
            for structured_key, payload in (completed_snapshot.get("structured") or {}).items():
                if payload and payload != previous_structured.get(structured_key):
                    final_progress_keys.add(f"{structured_key}_structured")
            verification_payload = final_state.get("verification_report_structured") or {}
            decision_payload = final_state.get("final_trade_decision_structured") or {}
            signal = str(decision_payload.get("signal") or graph.process_signal(final_state["final_trade_decision"])).strip()
            verification_verdict = str(verification_payload.get("verdict") or "").strip()
            verification_action = str(verification_payload.get("recommended_action") or "").strip()

            try:
                from tradingagents.agents.utils.decision import validate_portfolio_decision
                post_validation_errors = validate_portfolio_decision(
                    decision_payload,
                    current_price=final_state.get("verification_reference_price"),
                )
                if post_validation_errors:
                    emit_analysis_log(
                        "Structured decision payload has validation issues; DB numeric fields may be empty.",
                        "complete",
                        "warning",
                        errors=post_validation_errors,
                        status=decision_payload.get("decision_validation_status"),
                    )
                    emit(
                        "warning",
                        {
                            "message": (
                                f"Decision extraction had {len(post_validation_errors)} issue(s): "
                                + "; ".join(str(err) for err in post_validation_errors[:3])
                                + ("..." if len(post_validation_errors) > 3 else "")
                            )
                        },
                    )
            except ImportError:
                pass
            elapsed_seconds = round(time.time() - started_at, 2)
            history_id = None
            final_state["flow_artifacts"] = list(source_artifacts)
            source_artifact_groups: dict[str, int] = {}
            for artifact in source_artifacts:
                group_key = str(artifact.get("flow_group") or "other")
                source_artifact_groups[group_key] = source_artifact_groups.get(group_key, 0) + 1
            final_state["selected_analysts"] = list(filtered_analysts)
            final_state["source_artifact_groups"] = dict(source_artifact_groups)
            history_sections = build_history_sections(final_state)
            if self.history_store.configured:
                try:
                    history_id = self.history_store.save_analysis(
                        request=request,
                        user=user,
                        symbol=symbol,
                        signal=signal,
                        elapsed_seconds=elapsed_seconds,
                        sections=history_sections,
                        decision_payload=final_state.get("final_trade_decision_structured") or {},
                        verification_payload=verification_payload,
                        current_price=final_state.get("verification_reference_price"),
                    )
                    if history_id:
                        emit_analysis_log(
                            "Analysis markdown sections saved to history database.",
                            "history",
                            history_id=history_id,
                            section_count=len(history_sections),
                        )
                except Exception as exc:
                    logger.exception("failed to save analysis history")
                    emit_analysis_log(
                        "Analysis completed, but history database save failed.",
                        "history",
                        "warning",
                        error=str(exc),
                    )
                    emit("warning", {"message": "Analysis completed, but history database save failed."})
            else:
                emit_analysis_log("History database is not configured; skipping DB save.", "history", "warning")

            emit_analysis_log(
                "Analysis completed.",
                "complete",
                signal=signal,
                verification_verdict=verification_verdict,
                elapsed_seconds=elapsed_seconds,
                telemetry=telemetry.snapshot(),
            )
            if verification_verdict and verification_verdict.lower() != "approved":
                emit(
                    "warning",
                    {
                        "message": (
                            f"Verifier marked the decision as {verification_verdict}."
                            + (f" Recommended action: {verification_action}" if verification_action else "")
                        )
                    },
                )
            if final_progress_keys:
                emit("flow_progress", {"completed": sorted(final_progress_keys)})
            emit(
                "complete",
                {
                    "elapsed_seconds": elapsed_seconds,
                    "signal": signal,
                    "verification_verdict": verification_verdict,
                    "verification_action": verification_action,
                    "history_id": history_id,
                    "evidence_count": len(final_state.get("evidence_items") or []),
                    "source_artifact_count": len(source_artifacts),
                    "source_artifact_groups": source_artifact_groups,
                    "endpoint_summaries": final_state.get("endpoint_summaries") or endpoint_summaries,
                    "structured": {
                        "final_trade_decision": final_state.get("final_trade_decision_structured") or {},
                        "verification_report": final_state.get("verification_report_structured") or {},
                    },
                    "telemetry": telemetry.snapshot(),
                    "sections_patch": completed_sections_patch,
                    "research_patch": completed_research_patch,
                    "risk_patch": completed_risk_patch,
                    "status": completed_status,
                    "flow_block_count": sum(1 for section in history_sections if section.get("artifact_type") == "flow_block"),
                },
            )
        finally:
            if stdout_stream is not None:
                stdout_stream.flush()
            if stderr_stream is not None:
                stderr_stream.flush()
            if stderr_redirect is not None:
                stderr_redirect.__exit__(None, None, None)
            if stdout_redirect is not None:
                stdout_redirect.__exit__(None, None, None)
            if log_capture is not None:
                tradingagents_logger.removeHandler(log_capture)
            if graph is not None and graph._checkpointer_ctx is not None:
                graph._checkpointer_ctx.__exit__(None, None, None)
                graph._checkpointer_ctx = None
                graph.graph = graph.workflow.compile()
            if graph is not None:
                graph.curr_state = None
            final_state.clear()
            previous_snapshot.clear()
            previous_status.clear()
            seen_message_signatures.clear()
            source_artifacts.clear()
            seen_source_artifacts.clear()
            pending_tool_calls.clear()
            gc.collect()

    async def generate_analysis_stream(
        self,
        analysis_request: AnalysisRequest,
        http_request: Request,
        user: dict,
        reserved_slot: bool = False,
    ) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self.settings.analysis_sse_queue_maxsize)
        stream_started_at = time.time()
        cancel_event = threading.Event()
        stream_active = threading.Event()
        stream_active.set()
        slot_release_lock = threading.Lock()
        slot_released = False

        def release_slot_once() -> None:
            nonlocal slot_released
            if not reserved_slot:
                return
            with slot_release_lock:
                if slot_released:
                    return
                self.release_analysis_slot()
                slot_released = True

        if analysis_request.run_id:
            with self.active_analysis_lock:
                self.active_analysis_cancel_events[analysis_request.run_id] = cancel_event

        self._register_active_run(analysis_request.run_id, analysis_request.symbol, user, stream_started_at)

        async def queue_sse_item(payload: str, drop_if_full: bool) -> bool:
            if drop_if_full:
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    return False
                return True
            await queue.put(payload)
            return True

        def emit(event: str, data: dict) -> None:
            if not stream_active.is_set():
                return
            if cancel_event.is_set() and event not in {"cancelled", "error"}:
                return
            future = asyncio.run_coroutine_threadsafe(
                queue_sse_item(self._sse(event, data), event in self.settings.droppable_sse_events),
                loop,
            )
            try:
                future.result(timeout=1.0 if cancel_event.is_set() else None)
            except FutureTimeoutError:
                future.cancel()
                logger.warning(
                    "dropping SSE event after client cancellation: run_id=%s event=%s",
                    analysis_request.run_id,
                    event,
                )

        def worker() -> None:
            try:
                self.run_trading_analysis(analysis_request, emit, user, cancel_event)
            except AnalysisCancelled:
                logger.info("analysis cancelled: run_id=%s symbol=%s", analysis_request.run_id, analysis_request.symbol)
                emit(
                    "cancelled",
                    {
                        "run_id": analysis_request.run_id,
                        "message": "Analysis was cancelled before completion.",
                    },
                )
            except HTTPException as exc:
                logger.warning("analysis request failed: %s", exc.detail)
                emit("error", {"error": exc.detail})
            except Exception as exc:
                logger.exception("analysis stream crashed")
                emit("error", {"error": str(exc)})
            finally:
                self._unregister_active_run(analysis_request.run_id)
                try:
                    finish_future = asyncio.run_coroutine_threadsafe(queue.put(None), loop)
                    finish_future.result(timeout=1.0)
                except FutureTimeoutError:
                    finish_future.cancel()
                except RuntimeError:
                    pass
                finally:
                    release_slot_once()

        worker_task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                if await http_request.is_disconnected():
                    stream_active.clear()
                    logger.info(
                        "analysis client disconnected (analysis continues in background): run_id=%s symbol=%s",
                        analysis_request.run_id,
                        analysis_request.symbol,
                    )
                    break

                try:
                    item = await asyncio.wait_for(queue.get(), timeout=self.settings.stream_heartbeat_seconds)
                except asyncio.TimeoutError:
                    if worker_task.done():
                        break
                    if await http_request.is_disconnected():
                        stream_active.clear()
                        logger.info(
                            "analysis client disconnected during heartbeat (analysis continues in background): run_id=%s symbol=%s",
                            analysis_request.run_id,
                            analysis_request.symbol,
                        )
                        break
                    heartbeat_elapsed = round(time.time() - stream_started_at, 2)
                    yield self._sse(
                        "analysis_log",
                        {
                            "level": "debug",
                            "phase": "heartbeat",
                            "message": "Backend is still processing the active graph node.",
                            "elapsed_seconds": heartbeat_elapsed,
                            "log_line": (
                                "analysis symbol="
                                f"{analysis_request.symbol} phase=heartbeat elapsed={heartbeat_elapsed}s "
                                "message=Backend is still processing the active graph node. extra={}"
                            ),
                        },
                    )
                    continue
                if item is None:
                    break
                yield item
        except asyncio.CancelledError:
            stream_active.clear()
            logger.info(
                "analysis stream task cancelled, letting analysis continue in background: run_id=%s symbol=%s",
                analysis_request.run_id,
                analysis_request.symbol,
            )
            raise
        finally:
            if analysis_request.run_id:
                with self.active_analysis_lock:
                    self.active_analysis_cancel_events.pop(analysis_request.run_id, None)
            if not worker_task.done():
                logger.info(
                    "analysis still running in background after stream ended: run_id=%s symbol=%s",
                    analysis_request.run_id,
                    analysis_request.symbol,
                )
            else:
                try:
                    await worker_task
                except AnalysisCancelled:
                    pass
