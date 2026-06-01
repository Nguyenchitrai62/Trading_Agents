# TradingAgents/graph/conditional_logic.py

from langgraph.graph import END

from tradingagents.agents.utils.agent_states import AgentState


class ConditionalLogic:
    """Handles conditional logic for determining graph flow."""

    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        """Initialize with configuration parameters."""
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds

    def should_continue_market(self, state: AgentState):
        """Determine if market analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_market"
        return "Msg Clear Market"

    def should_continue_social(self, state: AgentState):
        """Determine if social-analyst tool round should continue.

        Method name keeps the legacy ``social`` suffix to match the
        ``AnalystType.SOCIAL = "social"`` wire value (saved-config back-compat).
        """
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_social"
        return "Msg Clear Social"

    def should_continue_news(self, state: AgentState):
        """Determine if news analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_news"
        return "Msg Clear News"

    def should_continue_onchain(self, state: AgentState):
        """Determine if onchain analysis should continue."""
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools_onchain"
        return "Msg Clear Onchain"

    def should_continue_debate(self, state: AgentState) -> str:
        """Determine if debate should continue."""

        if (
            state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds
        ):  # 3 rounds of back-and-forth between 2 agents
            return "Risk Team"
        if state["investment_debate_state"]["current_response"].startswith("Bull"):
            return "Bear Researcher"
        return "Bull Researcher"

    def should_continue_risk_analysis(self, state: AgentState) -> str:
        """Legacy fallback for the fixed one-pass risk-scenario stage."""
        if state["risk_debate_state"]["count"] >= 3:
            return "Portfolio Manager"
        if state["risk_debate_state"]["latest_speaker"].startswith("Aggressive"):
            return "Conservative Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Conservative"):
            return "Neutral Analyst"
        if state["risk_debate_state"]["latest_speaker"].startswith("Neutral"):
            return "Portfolio Manager"
        return "Aggressive Analyst"

    def should_continue_portfolio_verification(self, state: AgentState) -> str:
        """Route verifier output to revision, extraction, or terminal failure."""
        verification = state.get("verification_report_structured") or {}
        verdict = str(verification.get("verdict") or "").strip().lower()
        revision_count = int(state.get("decision_revision_count") or 0)
        if verdict == "approved":
            return "Decision Extractor"
        if revision_count < 2:
            return "Portfolio Manager"
        return END
