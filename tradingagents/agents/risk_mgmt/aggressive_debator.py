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


def create_aggressive_debator(llm):
    base_llm = resolve_structured_base_llm(llm)

    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        onchain_report = state.get("onchain_report", "")
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=14)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=get_coinglass_packages_for_role("aggressive_risk"),
        )

        research_debate_state = state.get("investment_debate_state") or {}
        research_context = research_debate_state.get("history", "")

        prompt = f"""As the Aggressive Risk Analyst, write one independent upside-risk scenario memo for the Portfolio Manager. This is not a debate. Do not rebut other risk analysts and do not ask for another round. Focus on the high-reward path, the conditions that make it valid, and the exact controls needed if the manager chooses to take risk.

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
## Upside Scenario
## Conditions That Validate Risk-On
## Positioning Bias
## Invalidation And Stops
## What The Portfolio Manager Should Watch

Make the memo concrete and decision-useful. Preserve price levels, risk thresholds, and evidence caveats when available.""" + get_language_instruction()

        response = _response_text(base_llm.invoke(prompt))

        argument = f"Aggressive Risk Scenario: {response}"

        new_risk_debate_state = {
            "history": history + "\n" + argument,
            "aggressive_history": aggressive_history + "\n" + argument,
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get(
                "current_neutral_response", ""
            ),
            "count": risk_debate_state["count"] + 1,
        }

        return {"risk_debate_state": new_risk_debate_state}

    return aggressive_node
