# TradingAgents/graph/propagation.py

from typing import Dict, Any, List, Optional
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)


class Propagator:
    """Handles state initialization and propagation through the graph."""

    def __init__(self, max_recur_limit=100):
        """Initialize with configuration parameters."""
        self.max_recur_limit = max_recur_limit

    def create_initial_state(
        self,
        company_name: str,
        trade_date: str,
        asset_type: str = "crypto",
        past_context: str = "",
        coinglass_context: str = "",
        coinglass_package_contexts: dict[str, str] | None = None,
        coinglass_endpoint_results: list[dict[str, Any]] | None = None,
        coinglass_evidence_items: list[dict[str, Any]] | None = None,
        endpoint_summaries: list[dict[str, Any]] | None = None,
        current_price: float | None = None,
        current_price_source: str = "",
    ) -> Dict[str, Any]:
        """Create the initial state for the agent graph."""
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "asset_type": asset_type,
            "trade_date": str(trade_date),
            "past_context": past_context,
            "coinglass_context": coinglass_context,
            "coinglass_package_contexts": coinglass_package_contexts or {},
            "coinglass_endpoint_results": list(coinglass_endpoint_results or []),
            "endpoint_summaries": list(endpoint_summaries or []),
            "investment_debate_state": InvestDebateState(
                {
                    "bull_history": "",
                    "bear_history": "",
                    "history": "",
                    "current_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "risk_debate_state": RiskDebateState(
                {
                    "aggressive_history": "",
                    "conservative_history": "",
                    "neutral_history": "",
                    "history": "",
                    "latest_speaker": "",
                    "current_aggressive_response": "",
                    "current_conservative_response": "",
                    "current_neutral_response": "",
                    "judge_decision": "",
                    "count": 0,
                }
            ),
            "market_report": "",
            "market_source_bundle": {},
            "onchain_report": "",
            "onchain_endpoint_analyses": [],
            "onchain_analysis_structured": {},
            "sentiment_report": "",
            "news_report": "",
            "evidence_items": list(coinglass_evidence_items or []),
            "verification_report": "",
            "final_trade_decision_structured": {},
            "verification_report_structured": {},
            "verification_reference_price": current_price,
            "verification_reference_price_source": current_price_source,
            "decision_revision_count": 0,
        }

    def get_graph_args(self, callbacks: Optional[List] = None) -> Dict[str, Any]:
        """Get arguments for the graph invocation.

        Args:
            callbacks: Optional list of callback handlers for tool execution tracking.
                       Note: LLM callbacks are handled separately via LLM constructor.
        """
        config = {"recursion_limit": self.max_recur_limit}
        if callbacks:
            config["callbacks"] = callbacks
        return {
            "stream_mode": "values",
            "config": config,
        }
