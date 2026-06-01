from tradingagents.agents.utils.agent_utils import (
    get_coinglass_context_instruction,
    get_coinglass_packages_for_role,
    get_language_instruction,
)
from tradingagents.agents.utils.evidence import format_evidence_ledger
from tradingagents.agents.utils.structured import resolve_structured_base_llm
from tradingagents.llm_clients.base_client import normalize_content


def _response_text(response: object) -> str:
    normalized = normalize_content(response)
    content = getattr(normalized, "content", "")
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content).strip()


def create_neutral_debator(llm):
    base_llm = resolve_structured_base_llm(llm)

    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        onchain_report = state.get("onchain_report", "")
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=14)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=get_coinglass_packages_for_role("neutral_risk"),
        )

        research_debate_state = state.get("investment_debate_state") or {}
        research_context = research_debate_state.get("history", "")

        prompt = f"""As the Neutral Risk Analyst, write one independent base-case scenario memo for the Portfolio Manager. This is not a debate. Do not rebut other risk analysts and do not ask for another round. Focus on the most balanced path, range of outcomes, sizing discipline, and what evidence would shift the decision.

    Research debate context:
    {research_context}

    Use these sources only:

Market Research Report: {market_research_report}
Social Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Onchain Report: {onchain_report}
Structured Evidence Ledger: {evidence_ledger}
{coinglass_context}

Output concise markdown with these exact sections:
## Base Scenario
## Balanced Evidence Read
## Positioning Bias
## Confirmation And Invalidation
## What The Portfolio Manager Should Watch

Make the memo concrete and decision-useful. Preserve price levels, risk thresholds, and evidence caveats when available.""" + get_language_instruction()

        response = _response_text(base_llm.invoke(prompt))

        argument = f"Neutral Risk Scenario: {response}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": neutral_history + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_aggressive_response": risk_debate_state.get(
                "current_aggressive_response", ""
            ),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": argument,
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return neutral_node
