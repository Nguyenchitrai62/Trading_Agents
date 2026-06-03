from __future__ import annotations

from collections.abc import Callable

from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from ..analysis_telemetry import AnalysisTelemetry
from ..config import SECTION_META
from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS
from .constants import STATE_UPDATE_KEYS


class AnalysisGraphMixin:

    @staticmethod
    def extract_runtime_snapshot(state: dict) -> dict:
        investment_state = state.get("investment_debate_state") or {}
        risk_state = state.get("risk_debate_state") or {}
        return {
            "sections": {key: (state.get(key) or "") for key in SECTION_META},
            "structured": {
                "onchain_analysis": state.get("onchain_analysis_structured") or {},
                "final_trade_decision": state.get("final_trade_decision_structured") or {},
                "verification_report": state.get("verification_report_structured") or {},
            },
            "evidence_items": list(state.get("evidence_items") or []),
            "endpoint_summaries": list(state.get("endpoint_summaries") or []),
            "investment": {
                "history": investment_state.get("history", "") or "",
                "bull_history": investment_state.get("bull_history", "") or "",
                "bear_history": investment_state.get("bear_history", "") or "",
                "current_response": investment_state.get("current_response", "") or "",
                "judge_decision": investment_state.get("judge_decision", "") or "",
                "count": investment_state.get("count", 0) or 0,
            },
            "risk": {
                "history": risk_state.get("history", "") or "",
                "aggressive_history": risk_state.get("aggressive_history", "") or "",
                "conservative_history": risk_state.get("conservative_history", "") or "",
                "neutral_history": risk_state.get("neutral_history", "") or "",
                "current_aggressive_response": risk_state.get("current_aggressive_response", "") or "",
                "current_conservative_response": risk_state.get("current_conservative_response", "") or "",
                "current_neutral_response": risk_state.get("current_neutral_response", "") or "",
                "judge_decision": risk_state.get("judge_decision", "") or "",
                "count": risk_state.get("count", 0) or 0,
            },
            "decision_revision_count": state.get("decision_revision_count", 0) or 0,
        }

    @staticmethod
    def evaluate_evidence_quality(snapshot: dict, selected_analysts: list[str]) -> dict:
        evidence_items = list(snapshot.get("evidence_items") or [])
        sections = snapshot.get("sections") or {}
        spec_map = {key: ANALYST_NODE_SPECS[key] for key in selected_analysts if key in ANALYST_NODE_SPECS}

        analyst_report_count = sum(1 for spec in spec_map.values() if sections.get(spec.report_key))
        total_analysts = len(spec_map)
        if analyst_report_count < total_analysts:
            return {
                "score": 0.0,
                "should_escalate": False,
                "escalated_rounds": 1,
                "reason": f"Analysts still in progress ({analyst_report_count}/{total_analysts} reports complete).",
                "label": "quick",
                "evidence_count": len(evidence_items),
                "confidence_mean": 0.0,
            }

        if not evidence_items:
            return {
                "score": 0.0,
                "should_escalate": True,
                "escalated_rounds": 5,
                "reason": "Zero structured evidence items from any analyst — escalating to deep to force more rigorous debate and cross-validation.",
                "label": "deep",
                "evidence_count": 0,
                "confidence_mean": 0.0,
            }

        confidences = [float(item.get("confidence", 0.0) or 0.0) for item in evidence_items]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        low_conf_count = sum(1 for c in confidences if c < 0.5)
        evidence_count = len(evidence_items)
        fresh_count = sum(
            1 for item in evidence_items if str(item.get("freshness") or "").lower() in ("realtime", "recent")
        )
        unknown_direction = sum(
            1 for item in evidence_items if str(item.get("direction") or "").lower() in ("unknown", "")
        )
        source_types = {str(item.get("source_type") or "other") for item in evidence_items}
        source_diversity = len(source_types)
        agent_labels = {str(item.get("agent_label") or item.get("agent") or "unknown") for item in evidence_items}
        agent_contributors = len(agent_labels)

        quality_score = (
            avg_confidence * 0.35
            + min(evidence_count / 12.0, 1.0) * 0.25
            + min(fresh_count / 4.0, 1.0) * 0.20
            + min(source_diversity / 4.0, 1.0) * 0.10
            + min(agent_contributors / max(total_analysts, 1), 1.0) * 0.10
        )

        if quality_score < 0.35:
            escalated, label, reason = 5, "deep", (
                "Evidence quality critically low "
                f"(score={quality_score:.2f}, conf={avg_confidence:.2f}, items={evidence_count}, "
                f"fresh={fresh_count}, low-conf={low_conf_count}/{evidence_count}) — "
                "escalating to deep for maximum debate rigor and cross-validation."
            )
        elif quality_score < 0.55:
            escalated, label, reason = 3, "medium", (
                "Evidence quality moderate "
                f"(score={quality_score:.2f}, conf={avg_confidence:.2f}, items={evidence_count}, "
                f"fresh={fresh_count}, sources={source_diversity}, low-conf={low_conf_count}) — "
                "escalating to medium-depth debate."
            )
        else:
            escalated, label, reason = 1, "quick", (
                "Evidence quality sufficient "
                f"(score={quality_score:.2f}, conf={avg_confidence:.2f}, items={evidence_count}, "
                f"fresh={fresh_count}, sources={source_diversity}, contributors={agent_contributors}/{total_analysts}) — "
                "keeping quick baseline; no escalation needed."
            )

        return {
            "score": round(quality_score, 3),
            "should_escalate": escalated > 1,
            "escalated_rounds": escalated,
            "reason": reason,
            "label": label,
            "evidence_count": evidence_count,
            "confidence_mean": round(avg_confidence, 3),
            "fresh_count": fresh_count,
            "low_confidence_count": low_conf_count,
            "source_diversity": source_diversity,
            "agent_contributors": agent_contributors,
            "total_analysts": total_analysts,
        }

    def emit_message_progress_updates(
        self,
        messages: list[object],
        current_agent: str | None,
        seen_signatures: set[str],
        emit: Callable[[str, dict], None],
        telemetry: AnalysisTelemetry | None = None,
        trace_sink: Callable[..., None] | None = None,
        trace_call_sink: Callable[..., None] | None = None,
    ) -> None:
        for message in messages:
            signature = self._build_message_signature(message)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            message_agent = (
                (getattr(message, "additional_kwargs", {}) or {}).get("agent")
                or current_agent
            )

            if isinstance(message, HumanMessage):
                continue

            if isinstance(message, ToolMessage):
                tool_name = getattr(message, "name", None) or getattr(message, "tool_call_id", None) or "tool"
                trace_id = str(getattr(message, "tool_call_id", None) or tool_name)
                raw_content = getattr(message, "content", "")
                if trace_sink is not None:
                    trace_sink(
                        agent=message_agent or "Tool Runner",
                        title=str(tool_name),
                        trace_id=trace_id,
                        content=raw_content,
                    )
                content = self._trim_text(
                    self.format_tool_result_for_display(raw_content),
                    self.settings.analysis_trace_char_limit,
                )
                if not content:
                    continue
                if telemetry is not None:
                    telemetry.record_tool_trace("tool_result", tool_name)
                emit(
                    "agent_trace",
                    {
                        "agent": message_agent or "Tool Runner",
                        "phase": "tool_result",
                        "title": str(tool_name),
                        "trace_id": trace_id,
                        "content": content,
                    },
                )
                continue

            if isinstance(message, AIMessage):
                tool_calls = getattr(message, "tool_calls", []) or []
                if tool_calls:
                    for tool_call in tool_calls:
                        tool_name = str(tool_call.get("name") or "tool")
                        trace_id = str(tool_call.get("id") or tool_name)
                        call_summary = self._tool_call_summary(tool_call)
                        if trace_call_sink is not None:
                            trace_call_sink(
                                agent=message_agent or "Analyst",
                                title=tool_name,
                                trace_id=trace_id,
                                content=call_summary,
                            )
                        if telemetry is not None:
                            telemetry.record_tool_trace("tool_call", tool_name)
                        emit(
                            "agent_trace",
                            {
                                "agent": message_agent or "Analyst",
                                "phase": "tool_call",
                                "title": tool_name,
                                "trace_id": trace_id,
                                "content": call_summary,
                            },
                        )
                content = self._trim_text(
                    self._normalize_message_content(getattr(message, "content", "")),
                    self.settings.analysis_trace_char_limit,
                )
                if content:
                    emit(
                        "agent_trace",
                        {
                            "agent": message_agent or "Analyst",
                            "phase": "analysis",
                            "title": message_agent or "Analysis",
                            "content": content,
                        },
                    )

    @staticmethod
    def detect_current_agent(previous: dict, current: dict) -> str | None:
        previous_sections = previous.get("sections", {})
        current_sections = current.get("sections", {})
        for key, meta in SECTION_META.items():
            if current_sections.get(key) and current_sections.get(key) != previous_sections.get(key):
                return meta["agent"]

        previous_investment = previous.get("investment", {})
        current_investment = current.get("investment", {})
        if current_investment.get("current_response") and current_investment.get("current_response") != previous_investment.get("current_response"):
            response = current_investment.get("current_response", "")
            if response.startswith("Bull Analyst:"):
                return "Bull Researcher"
            if response.startswith("Bear Analyst:"):
                return "Bear Researcher"
            return "Research Team"

        previous_risk = previous.get("risk", {})
        current_risk = current.get("risk", {})
        risk_fields = [
            ("current_aggressive_response", "Aggressive Analyst"),
            ("current_conservative_response", "Conservative Analyst"),
            ("current_neutral_response", "Neutral Analyst"),
        ]
        for field_name, label in risk_fields:
            if current_risk.get(field_name) and current_risk.get(field_name) != previous_risk.get(field_name):
                return label

        return None

    @staticmethod
    def build_changed_fields(previous: dict, current: dict) -> dict:
        return {key: value for key, value in current.items() if value != previous.get(key)}

    @staticmethod
    def build_changed_sections(previous: dict, current: dict) -> dict:
        return {key: value for key, value in current.items() if value and value != previous.get(key)}

    @staticmethod
    def iter_graph_state_updates(chunk: dict) -> list[tuple[str | None, dict]]:
        if not isinstance(chunk, dict):
            return []
        if any(key in STATE_UPDATE_KEYS for key in chunk):
            return [(None, chunk)]
        updates: list[tuple[str | None, dict]] = []
        for node_name, update in chunk.items():
            if isinstance(update, dict):
                updates.append((str(node_name), update))
        return updates

    @staticmethod
    def graph_node_to_agent_label(node_name: str | None) -> str | None:
        if not node_name:
            return None
        normalized = str(node_name)
        if normalized in {
            "Parallel Analyst Team",
            "Bull Researcher",
            "Bear Researcher",
            "Aggressive Analyst",
            "Conservative Analyst",
            "Neutral Analyst",
            "Portfolio Manager",
            "Verifier",
            "Decision Extractor",
        }:
            return normalized
        for spec in ANALYST_NODE_SPECS.values():
            if normalized in {spec.agent_node, spec.tool_node}:
                return spec.agent_node
        return None

    @staticmethod
    def predict_next_graph_agent(
        snapshot: dict,
        selected_analysts: list[str],
        *,
        max_debate_rounds: int = 1,
        max_risk_rounds: int = 1,
    ) -> str | None:
        sections = snapshot.get("sections", {})
        selected_specs = [ANALYST_NODE_SPECS[key] for key in selected_analysts if key in ANALYST_NODE_SPECS]
        for spec in selected_specs:
            if not sections.get(spec.report_key):
                return spec.agent_node

        investment = snapshot.get("investment", {})
        expected_research_turns = max(1, int(max_debate_rounds or 1)) * 2
        investment_count = int(investment.get("count") or 0)
        if investment_count < expected_research_turns:
            current_response = str(investment.get("current_response") or "")
            if current_response.startswith("Bull"):
                return "Bear Researcher"
            return "Bull Researcher"

        risk = snapshot.get("risk", {})
        expected_risk_turns = max(1, int(max_risk_rounds or 1)) * 3
        risk_count = int(risk.get("count") or 0)
        if risk_count < expected_risk_turns and not sections.get("final_trade_decision"):
            latest_speaker = str(risk.get("latest_speaker") or "")
            if latest_speaker.startswith("Aggressive"):
                return "Conservative Analyst"
            if latest_speaker.startswith("Conservative"):
                return "Neutral Analyst"
            return "Aggressive Analyst"

        if not sections.get("final_trade_decision"):
            return "Portfolio Manager"
        if not sections.get("verification_report"):
            return "Verifier"
        return None

    @staticmethod
    def progress_phase_for_agent(agent: str | None) -> str:
        if agent in {"Bull Researcher", "Bear Researcher"}:
            return "research"
        if agent in {"Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"}:
            return "risk"
        if agent in {"Portfolio Manager", "Verifier"}:
            return "portfolio"
        if agent:
            return "analysts"
        return "stream"

    @staticmethod
    def agent_start_message(
        agent: str,
        snapshot: dict,
        *,
        max_debate_rounds: int = 1,
        max_risk_rounds: int = 1,
    ) -> str:
        if agent in {"Bull Researcher", "Bear Researcher"}:
            total = max(1, int(max_debate_rounds or 1)) * 2
            turn = min(total, int((snapshot.get("investment") or {}).get("count") or 0) + 1)
            return f"{agent} started research debate turn {turn}/{total}; waiting for model response."
        if agent in {"Aggressive Analyst", "Conservative Analyst", "Neutral Analyst"}:
            total = max(1, int(max_risk_rounds or 1)) * 3
            turn = min(total, int((snapshot.get("risk") or {}).get("count") or 0) + 1)
            return f"{agent} started risk debate turn {turn}/{total}; waiting for model response."
        return f"{agent} started; waiting for model response."

    @staticmethod
    def merge_graph_state_update(state: dict, update: dict) -> list[str]:
        changed_keys: list[str] = []
        for key, value in update.items():
            if key == "messages":
                state["messages"] = [
                    message for message in (value or []) if not isinstance(message, RemoveMessage)
                ]
            elif key == "evidence_items":
                state[key] = list(state.get(key) or []) + list(value or [])
            elif isinstance(value, dict) and isinstance(state.get(key), dict):
                merged = dict(state[key])
                merged.update(value)
                state[key] = merged
            else:
                state[key] = value
            changed_keys.append(key)
        return sorted(set(changed_keys))
