from tradingagents.agents.schemas import DebateTurn, render_debate_turn
from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext


def create_neutral_debator(llm):
    structured_llm = bind_structured(llm, DebateTurn, "Neutral Analyst")

    def neutral_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        neutral_history = risk_debate_state.get("neutral_history", "")

        current_aggressive_response = risk_debate_state.get("current_aggressive_response", "")
        current_conservative_response = risk_debate_state.get("current_conservative_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        flow_report = state["flow_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Neutral Risk Analyst, provide a balanced perspective that weighs upside against downside and identifies what would shift conviction either way. Return a structured debate handoff with the fields thesis, supporting_evidence, rebuttal, caveats, and action_bias. Use only the provided evidence and keep the output decision-useful. Here is the trader's decision:

{trader_decision}

Your task is to challenge both the Aggressive and Conservative Analysts, pointing out where each perspective may be overly optimistic or overly cautious. Use insights from the following data sources to support a moderate, sustainable strategy to adjust the trader's decision:

Market Research Report: {market_research_report}
Social Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Asset Flow Report: {flow_report}
Here is the current conversation history: {history} Here is the last response from the aggressive analyst: {current_aggressive_response} Here is the last response from the conservative analyst: {current_conservative_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Analyze both sides critically, identify the strongest evidence on each side, and explain what balanced positioning or confirmation threshold best fits the current setup.""" + get_language_instruction()

        response = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_debate_turn,
            "Neutral Analyst",
        )

        argument = f"Neutral Analyst: {response}"

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
