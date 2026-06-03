from __future__ import annotations

from collections.abc import Callable

from ..config import SECTION_META
from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS


class AnalysisEmitterMixin:

    def build_status_snapshot(
        self,
        snapshot: dict,
        selected_analysts: list[str],
        current_agent: str | None,
        *,
        max_debate_rounds: int = 1,
        max_risk_rounds: int = 1,
    ) -> dict:
        selected_specs = [ANALYST_NODE_SPECS[key] for key in selected_analysts]
        sections = snapshot["sections"]
        analysts = []
        parallel_analysts_active = current_agent in {"Analyst Team", "Parallel Analyst Team"}
        for spec in selected_specs:
            has_report = bool(sections.get(spec.report_key))
            if has_report:
                status = "completed"
            elif parallel_analysts_active:
                status = "in_progress"
            elif current_agent == spec.agent_node:
                status = "in_progress"
            else:
                status = "pending"
            analysts.append({"key": spec.key, "label": spec.agent_node, "status": status})

        analyst_reports_complete = all(bool(sections.get(spec.report_key)) for spec in selected_specs)

        investment = snapshot["investment"]
        expected_research_turns = max(1, int(max_debate_rounds or 1)) * 2
        research_turns_complete = int(investment.get("count") or 0) >= expected_research_turns
        research_active = analyst_reports_complete and not research_turns_complete
        research = [
            {
                "key": "bull",
                "label": "Bull Researcher",
                "status": "completed"
                if research_turns_complete and investment["bull_history"]
                else "in_progress"
                if research_active and (current_agent == "Bull Researcher" or not investment["bull_history"] or investment["history"])
                else "pending",
            },
            {
                "key": "bear",
                "label": "Bear Researcher",
                "status": "completed"
                if research_turns_complete and investment["bear_history"]
                else "in_progress"
                if research_active and (current_agent == "Bear Researcher" or investment["bull_history"])
                else "pending",
            },
        ]

        risk = snapshot["risk"]
        expected_risk_turns = max(1, int(max_risk_rounds or 1)) * 3
        risk_turns_complete = bool(sections.get("final_trade_decision")) or int(risk.get("count") or 0) >= expected_risk_turns
        risk_active = research_turns_complete and not sections.get("final_trade_decision")
        risk_items = [
            {
                "key": "aggressive",
                "label": "Aggressive Analyst",
                "status": "completed"
                if risk_turns_complete and risk["current_aggressive_response"]
                else "in_progress"
                if risk_active and (current_agent == "Aggressive Analyst" or not risk["current_aggressive_response"] or risk["history"])
                else "pending",
            },
            {
                "key": "conservative",
                "label": "Conservative Analyst",
                "status": "completed"
                if risk_turns_complete and risk["current_conservative_response"]
                else "in_progress"
                if risk_active and (current_agent == "Conservative Analyst" or risk["current_aggressive_response"])
                else "pending",
            },
            {
                "key": "neutral",
                "label": "Neutral Analyst",
                "status": "completed"
                if risk_turns_complete and risk["current_neutral_response"]
                else "in_progress"
                if risk_active and (current_agent == "Neutral Analyst" or risk["current_conservative_response"])
                else "pending",
            },
        ]

        portfolio = [
            {
                "key": "portfolio_manager",
                "label": "Portfolio Manager",
                "status": "in_progress"
                if current_agent == "Portfolio Manager"
                else "completed"
                if sections.get("final_trade_decision")
                else "pending",
            },
            {
                "key": "verifier",
                "label": "Verifier",
                "status": "in_progress"
                if current_agent == "Verifier" or (sections.get("final_trade_decision") and not sections.get("verification_report"))
                else "completed"
                if sections.get("verification_report")
                else "pending",
            },
        ]

        for group in (analysts, research, risk_items, portfolio):
            for item in group:
                if current_agent and item["label"] == current_agent and item["status"] == "pending":
                    item["status"] = "in_progress"

        total_sections = len(selected_specs) + 3
        completed_sections = sum(bool(sections.get(spec.report_key)) for spec in selected_specs)
        completed_sections += int(bool(sections.get("final_trade_decision")))
        completed_sections += int(bool(sections.get("verification_report")))
        completed_sections += int(bool(snapshot.get("structured", {}).get("final_trade_decision")))

        if sections.get("verification_report") and snapshot.get("structured", {}).get("final_trade_decision"):
            phase = "complete"
        elif sections.get("final_trade_decision"):
            phase = "verification"
        elif risk["history"] or research_turns_complete:
            phase = "risk"
        elif investment["history"] or analyst_reports_complete:
            phase = "research"
        elif any(bool(sections.get(spec.report_key)) for spec in selected_specs):
            phase = "analysts"
        else:
            phase = "booting"

        return {
            "current_agent": current_agent,
            "phase": phase,
            "decision_revision_count": snapshot.get("decision_revision_count", 0) or 0,
            "progress": {
                "completed": completed_sections,
                "total": total_sections,
                "percent": round((completed_sections / total_sections) * 100, 1) if total_sections else 0,
            },
            "groups": {
                "analysts": analysts,
                "research": research,
                "risk": risk_items,
                "portfolio": portfolio,
            },
        }

    def emit_snapshot_updates(self, previous: dict, current: dict, emit: Callable[[str, dict], None]) -> None:
        previous_sections = previous.get("sections", {})
        current_sections = current.get("sections", {})
        emitted_section_updates: set[str] = set()
        for key, meta in SECTION_META.items():
            content = current_sections.get(key, "")
            if content and content != previous_sections.get(key):
                emitted_section_updates.add(key)
                emit(
                    "section_update",
                    {
                        "section": key,
                        "title": meta["title"],
                        "agent": meta["agent"],
                        "team": meta["team"],
                        "content": content,
                    },
                )

        structured_meta = {
            "onchain_analysis": {
                "title": "Onchain Analysis Payload",
                "agent": "Onchain Analyst",
                "team": "Analyst Team",
            },
            "final_trade_decision": {
                "title": "Portfolio Manager Structured",
                "agent": "Portfolio Manager",
                "team": "Portfolio Management",
            },
            "verification_report": {
                "title": "Verifier Payload",
                "agent": "Verifier",
                "team": "Portfolio Management",
            },
        }
        previous_structured = previous.get("structured", {})
        current_structured = current.get("structured", {})
        for key, meta in structured_meta.items():
            payload = current_structured.get(key) or {}
            if payload and payload != previous_structured.get(key):
                emitted_section_updates.add(f"{key}_structured")
                emit(
                    "structured_update",
                    {
                        "section": key,
                        "title": meta["title"],
                        "agent": meta["agent"],
                        "team": meta["team"],
                        "payload": payload,
                    },
                )

        if emitted_section_updates:
            emit("flow_progress", {"completed": sorted(emitted_section_updates)})

        previous_evidence = previous.get("evidence_items", [])
        current_evidence = current.get("evidence_items", [])
        if len(current_evidence) > len(previous_evidence):
            emit(
                "evidence_update",
                {
                    "items": current_evidence[len(previous_evidence):],
                    "count": len(current_evidence),
                },
            )

        previous_investment = previous.get("investment", {})
        current_investment = current.get("investment", {})
        if current_investment.get("current_response") and current_investment.get("current_response") != previous_investment.get("current_response"):
            speaker = "Research Team"
            if current_investment["current_response"].startswith("Bull Analyst:"):
                speaker = "Bull Researcher"
            if current_investment["current_response"].startswith("Bear Analyst:"):
                speaker = "Bear Researcher"
            emit(
                "debate_update",
                {
                    "team": "research",
                    "speaker": speaker,
                    "content": current_investment["current_response"],
                    "patch": self.build_changed_fields(previous_investment, current_investment),
                },
            )

        previous_risk = previous.get("risk", {})
        current_risk = current.get("risk", {})
        risk_speakers = {
            "current_aggressive_response": "Aggressive Analyst",
            "current_conservative_response": "Conservative Analyst",
            "current_neutral_response": "Neutral Analyst",
        }
        for field_name, speaker in risk_speakers.items():
            if current_risk.get(field_name) and current_risk.get(field_name) != previous_risk.get(field_name):
                emit(
                    "debate_update",
                    {
                        "team": "risk",
                        "speaker": speaker,
                        "content": current_risk[field_name],
                        "patch": self.build_changed_fields(previous_risk, current_risk),
                    },
                )
