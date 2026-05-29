from tradingagents.agents.schemas import DebateTurn, render_debate_turn
from tradingagents.agents.utils.agent_utils import get_coinglass_context_instruction, get_language_instruction
from tradingagents.agents.utils.evidence import format_evidence_ledger
from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext


def create_bear_researcher(llm):
    structured_llm = bind_structured(llm, DebateTurn, "Bear Researcher")

    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        flow_report = state["flow_report"]
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=14)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=(
                "funding_pressure",
                "liquidation_risk",
                "exchange_reserves",
                "options_context",
                "macro_cycle_context",
            ),
        )
        target_label = "asset"
        flow_label = "Asset flow context report"

        prompt = f"""You are a Bear Analyst making the case against investing in the {target_label}. Present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Return a structured debate handoff with the fields thesis, supporting_evidence, rebuttal, caveats, and action_bias. Do not add conversational filler or invent unsupported facts.

Key points to focus on:

- Risks and Challenges: Highlight factors like liquidity stress, volatility, regulatory pressure, or macroeconomic threats that could hinder the asset's performance.
- Competitive Weaknesses: Emphasize vulnerabilities such as weaker market positioning, declining protocol usage, or threats from competing ecosystems.
- Negative Indicators: Use evidence from financial data, market trends, or recent adverse news to support your position.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning, exposing weaknesses or over-optimistic assumptions.
- Engagement: Present your argument in a conversational style, directly engaging with the bull analyst's points and debating effectively rather than simply listing facts.

Resources available:

Market research report: {market_research_report}
Social report: {sentiment_report}
Latest world affairs news: {news_report}
{flow_label}: {flow_report}
Structured evidence ledger:
{evidence_ledger}
{coinglass_context}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the {target_label}.
""" + get_language_instruction()

        response = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_debate_turn,
            "Bear Researcher",
        )

        argument = f"Bear Analyst: {response}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
