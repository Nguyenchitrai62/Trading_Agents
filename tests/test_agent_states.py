"""Tests for AgentState, InvestDebateState, and RiskDebateState TypedDicts."""

from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class TestAgentState:
    def test_agent_state_keys(self):
        required_keys = {
            "company_of_interest",
            "asset_type",
            "trade_date",
            "sender",
            "market_report",
            "sentiment_report",
            "news_report",
            "onchain_report",
            "evidence_items",
            "investment_debate_state",
            "risk_debate_state",
            "final_trade_decision",
            "final_trade_decision_structured",
            "verification_report",
            "verification_report_structured",
        }
        annotations = getattr(AgentState, "__annotations__", {})
        for key in required_keys:
            assert key in annotations, f"AgentState missing key: {key}"

    def test_agent_state_has_messages(self):
        annotations = getattr(AgentState, "__annotations__", {})
        assert "messages" in annotations

    def test_evidence_items_operator_add(self):
        from typing import get_type_hints
        import operator

        hints = get_type_hints(AgentState, include_extras=True)
        evidence_type = hints.get("evidence_items")
        assert evidence_type is not None

    def test_agent_state_structured_fields(self):
        annotations = getattr(AgentState, "__annotations__", {})
        assert "final_trade_decision_structured" in annotations
        assert "verification_report_structured" in annotations
        assert "verification_reference_price" in annotations

    def test_agent_state_coinglass_fields(self):
        annotations = getattr(AgentState, "__annotations__", {})
        assert "coinglass_context" in annotations
        assert "coinglass_package_contexts" in annotations
        assert "endpoint_summaries" in annotations
        assert "coinglass_endpoint_results" in annotations

    def test_agent_state_market_fields(self):
        annotations = getattr(AgentState, "__annotations__", {})
        assert "market_source_bundle" in annotations

    def test_agent_state_past_context(self):
        annotations = getattr(AgentState, "__annotations__", {})
        assert "past_context" in annotations


class TestInvestDebateState:
    def test_invest_debate_state_keys(self):
        required_keys = {
            "bull_history",
            "bear_history",
            "history",
            "current_response",
            "judge_decision",
            "count",
        }
        annotations = getattr(InvestDebateState, "__annotations__", {})
        for key in required_keys:
            assert key in annotations, f"InvestDebateState missing key: {key}"

    def test_invest_debate_state_count_is_int(self):
        import typing
        annotations = getattr(InvestDebateState, "__annotations__", {})
        count_type = annotations.get("count")
        assert count_type is not None


class TestRiskDebateState:
    def test_risk_debate_state_keys(self):
        required_keys = {
            "aggressive_history",
            "conservative_history",
            "neutral_history",
            "history",
            "latest_speaker",
            "current_aggressive_response",
            "current_conservative_response",
            "current_neutral_response",
            "judge_decision",
            "count",
        }
        annotations = getattr(RiskDebateState, "__annotations__", {})
        for key in required_keys:
            assert key in annotations, f"RiskDebateState missing key: {key}"

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
