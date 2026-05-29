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
    get_coinglass_context_instruction,
    get_coinglass_packages_for_role,
    get_language_instruction,
)
from tradingagents.agents.utils.evidence import format_evidence_ledger
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext_result,
)


def _format_structured_context(
    payload: dict,
    fallback_markdown: str,
    fields: list[tuple[str, str]],
) -> str:
    if not payload:
        return fallback_markdown

    parts = []
    for label, key in fields:
        value = payload.get(key)
        if value in (None, "", []):
            continue
        parts.append(f"- {label}: {value}")

    return "\n".join(parts) if parts else fallback_markdown


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])

        history = state["risk_debate_state"]["history"]
        risk_debate_state = state["risk_debate_state"]
        research_plan = state["investment_plan"]
        trader_plan = state["trader_investment_plan"]
        research_plan_payload = state.get("investment_plan_structured") or {}
        trader_plan_payload = state.get("trader_investment_plan_structured") or {}
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=18)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=get_coinglass_packages_for_role("portfolio_manager"),
        )
        research_plan_context = _format_structured_context(
            research_plan_payload,
            research_plan,
            [
                ("Recommendation", "recommendation"),
                ("Rationale", "rationale"),
                ("Strategic Actions", "strategic_actions"),
            ],
        )
        trader_plan_context = _format_structured_context(
            trader_plan_payload,
            trader_plan,
            [
                ("Action", "action"),
                ("Reasoning", "reasoning"),
                ("Entry Price", "entry_price"),
                ("Stop Loss", "stop_loss"),
                ("Position Sizing", "position_sizing"),
            ],
        )

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

    **Positioning scope:**
    - This workflow is long-only. A sell signal means reducing or exiting an existing long position, not opening a new short.
    - Do not mix multiple plans. If you choose a sell signal, describe only the exit or reduction plan for the current long inventory.

    **Hard rules:**
    - Never output generic final signals like Buy / Sell / Overweight / Underweight.
    - If you choose **Limit Buy** or **Limit Sell**, you must provide at least one exact limit price and explain why waiting is better than executing at market now.
    - If you choose **Market Buy** or **Market Sell**, you must explain why the current price is good enough for immediate execution.
    - For **Limit Sell**, the limit price must be a better exit level for the current long position. If immediate selling is the right action, choose **Market Sell** instead.
    - If you choose **Hold**, explain what confirmation, catalyst, or price zone would be needed before placing an order.
    - When the setup is actionable, include stop-loss, take-profit, and position sizing.
    - For **Limit Sell** or **Market Sell**, do not include a new short thesis or an upside take-profit ladder. Use **Position Sizing** to say how much of the current long to trim or exit, and only use **Stop Loss** if you explicitly keep a remaining long tranche.
    - If structured output is unavailable and you must answer in free text, still use these exact markdown headers: **Signal**, **Execution Summary**, **Market Context**, **Investment Thesis**, **Primary Limit Price**, **Secondary Limit Price**, **Stop Loss**, **Take Profit**, **Position Sizing**, **Time Horizon**.

**Context:**
- Research Manager's investment plan:\n{research_plan_context}
- Trader's transaction proposal:\n{trader_plan_context}
- Structured evidence ledger:\n{evidence_ledger}
{coinglass_context}
{lessons_line}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        final_trade_decision, parsed_decision = invoke_structured_or_freetext_result(
            structured_llm,
            llm,
            prompt,
            render_pm_decision,
            "Portfolio Manager",
        )
        structured_payload = parsed_decision.model_dump(mode="json") if parsed_decision is not None else {}

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
            "final_trade_decision_structured": structured_payload,
        }

    return portfolio_manager_node
