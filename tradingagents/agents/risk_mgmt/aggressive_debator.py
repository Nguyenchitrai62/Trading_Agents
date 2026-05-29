from tradingagents.agents.schemas import DebateTurn, render_debate_turn
from tradingagents.agents.utils.agent_utils import get_language_instruction
from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext


def create_aggressive_debator(llm):
    structured_llm = bind_structured(llm, DebateTurn, "Aggressive Analyst")

    def aggressive_node(state) -> dict:
        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        aggressive_history = risk_debate_state.get("aggressive_history", "")

        current_conservative_response = risk_debate_state.get("current_conservative_response", "")
        current_neutral_response = risk_debate_state.get("current_neutral_response", "")

        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        flow_report = state["flow_report"]

        trader_decision = state["trader_investment_plan"]

        prompt = f"""As the Aggressive Risk Analyst, actively champion high-reward, high-risk opportunities, emphasizing bold strategies and upside capture. Return a structured debate handoff with the fields thesis, supporting_evidence, rebuttal, caveats, and action_bias. Use the provided market data and trader plan to challenge the opposing views without inventing unsupported facts. Here is the trader's decision:

{trader_decision}

Your task is to create a compelling case for the trader's decision by questioning and critiquing the conservative and neutral stances to demonstrate why your high-reward perspective offers the best path forward. Incorporate insights from the following sources into your arguments:

Market Research Report: {market_research_report}
Social Report: {sentiment_report}
Latest World Affairs Report: {news_report}
Asset Flow Report: {flow_report}
Here is the current conversation history: {history} Here are the last arguments from the conservative analyst: {current_conservative_response} Here are the last arguments from the neutral analyst: {current_neutral_response}. If there are no responses from the other viewpoints yet, present your own argument based on the available data.

Engage actively by addressing specific concerns, refuting weak logic, and asserting the benefits of calculated risk-taking. Make every field concrete and decision-useful.""" + get_language_instruction()

        response = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_debate_turn,
            "Aggressive Analyst",
        )

        argument = f"Aggressive Analyst: {response}"

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
