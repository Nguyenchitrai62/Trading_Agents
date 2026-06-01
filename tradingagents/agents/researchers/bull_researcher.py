from tradingagents.agents.schemas import DebateTurn, render_debate_turn
from tradingagents.agents.utils.agent_utils import (
    get_coinglass_context_instruction,
    get_coinglass_packages_for_role,
    get_language_instruction,
)
from tradingagents.agents.utils.evidence import format_evidence_ledger
from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext


def create_bull_researcher(llm):
    structured_llm = bind_structured(llm, DebateTurn, "Bull Researcher")

    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = investment_debate_state.get("current_response", "")
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        onchain_report = state.get("onchain_report", "")
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=14)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=get_coinglass_packages_for_role("bull_researcher"),
        )
        target_label = "asset"
        flow_label = "Onchain context report"

        prompt = f"""You are a Bull Analyst advocating for investing in the {target_label}. Build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Return a structured debate handoff with the fields thesis, supporting_evidence, rebuttal, caveats, and action_bias. Do not add conversational filler or invent unsupported facts.

Key points to focus on:
- Growth Potential: Highlight market opportunities, adoption, liquidity, and upside catalysts.
- Competitive Advantages: Emphasize factors like network effects, ecosystem strength, market positioning, or structural demand.
- Positive Indicators: Use financial health, industry trends, and recent positive news as evidence.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning, addressing concerns thoroughly and showing why the bull perspective holds stronger merit.
- Engagement: Present your argument in a conversational style, engaging directly with the bear analyst's points and debating effectively rather than just listing data.

Resources available:
Market research report: {market_research_report}
Social report: {sentiment_report}
Latest world affairs news: {news_report}
{flow_label}: {onchain_report}
Structured evidence ledger:
{evidence_ledger}
{coinglass_context}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.
""" + get_language_instruction()

        response = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_debate_turn,
            "Bull Researcher",
        )

        argument = f"Bull Analyst: {response}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
