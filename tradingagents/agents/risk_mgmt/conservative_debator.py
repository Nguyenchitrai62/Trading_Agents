from tradingagents.agents.schemas import DebateTurn, render_debate_turn
from tradingagents.agents.utils.agent_utils import (
    get_coinglass_context_instruction,
    get_coinglass_packages_for_role,
    get_language_instruction,
)
from tradingagents.agents.utils.evidence import format_evidence_ledger
from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext


def create_conservative_debator(llm):
    structured_llm = bind_structured(llm, DebateTurn, "Conservative Analyst")

    def conservative_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        conservative_history = risk_debate_state.get("conservative_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        onchain_report = state.get("onchain_report", "")
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=18)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=get_coinglass_packages_for_role("conservative_risk"),
        )

        research_debate_state = state.get("investment_debate_state") or {}
        research_context = research_debate_state.get("history", "")

        prompt = f"""As the Conservative Risk Analyst, protect capital, minimize volatility, and stress-test downside risk. Return a structured debate handoff with the fields thesis, supporting_evidence, rebuttal, caveats, and action_bias. Use the four branch reports and research debate to identify concrete risks and avoid unsupported claims.

    Research debate context:
    {research_context}

    Your task is to actively counter the arguments of the Aggressive and Neutral Analysts, highlighting where their views may overlook potential threats or fail to prioritize sustainability. Respond directly to their points, drawing from the following data sources to build a convincing case for a lower-risk approach:

Market Research Report: {market_research_report}
Social Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Onchain Report: {onchain_report}
Structured Evidence Ledger: {evidence_ledger}
{coinglass_context}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Question excessive optimism, highlight downside scenarios, and explain what safer positioning or confirmation is needed before action.""" + get_language_instruction()

        response = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_debate_turn,
            "Conservative Analyst",
        )

        argument = f"Conservative Analyst: {response}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": conservative_history + "\n" + argument,
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Conservative",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": argument,
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return conservative_node
