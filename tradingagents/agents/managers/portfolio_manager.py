"""Portfolio Manager: synthesises the risk-analyst debate into the final signal.

Uses LangChain's ``with_structured_output`` so the LLM produces a typed
``PortfolioDecision`` directly, in a single call.  The result is rendered
back to markdown for storage in ``final_trade_decision`` so memory log,
CLI display, and saved reports continue to consume the same shape they do
today.  When a provider does not expose structured output, the agent falls
back gracefully to free-text generation.
"""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading signal.

{instrument_context}

---

    **Execution Signal** (use exactly one):
    - **Market Buy**: Buy immediately at the current market price because the setup is already attractive enough now
    - **Limit Buy**: Do not buy now; place one or more concrete buy limits below or around the trigger level instead
    - **Hold**: Do not place any order yet because the edge is too unclear or the trigger levels are not reliable enough
    - **Limit Sell**: Do not sell now; place one or more concrete sell limits at better exit levels instead
    - **Market Sell**: Sell immediately at the current market price because downside risk or weak structure justifies acting now

    **Hard rules:**
    - Never output generic final signals like Buy / Sell / Overweight / Underweight.
    - If you choose **Limit Buy** or **Limit Sell**, you must provide at least one exact limit price and explain why waiting is better than executing at market now.
    - If you choose **Market Buy** or **Market Sell**, you must explain why the current price is good enough for immediate execution.
    - If you choose **Hold**, explain what confirmation, catalyst, or price zone would be needed before placing an order.
    - When the setup is actionable, include stop-loss, take-profit, and position sizing.
    - If structured output is unavailable and you must answer in free text, still use these exact markdown headers: **Signal**, **Execution Summary**, **Market Context**, **Investment Thesis**, **Primary Limit Price**, **Secondary Limit Price**, **Stop Loss**, **Take Profit**, **Position Sizing**, **Time Horizon**.

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        final_trade_decision = invoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state["history"],
            "aggressive_history": risk_debate_state["aggressive_history"],
            "conservative_history": risk_debate_state["conservative_history"],
            "neutral_history": risk_debate_state["neutral_history"],
            "latest_speaker": "Judge",
            "current_aggressive_response": risk_debate_state["current_aggressive_response"],
            "current_conservative_response": risk_debate_state["current_conservative_response"],
            "current_neutral_response": risk_debate_state["current_neutral_response"],
            "count": risk_debate_state["count"],
        }

        return {
            "risk_debate_state": new_risk_debate_state,
            "final_trade_decision": final_trade_decision,
        }

    return portfolio_manager_node
