"""Portfolio Manager: prose-first final signal plus structured extraction."""

from __future__ import annotations

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.decision import validate_portfolio_decision
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_coinglass_context_instruction,
    get_coinglass_packages_for_role,
    get_language_instruction,
)
from tradingagents.agents.utils.evidence import format_evidence_ledger
from tradingagents.agents.utils.market_price import fetch_current_binance_spot_price
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext_result,
    resolve_structured_base_llm,
)
from tradingagents.agents.utils.rating import parse_rating
from tradingagents.llm_clients.base_client import normalize_content


_SIGNALS = ("Market Buy", "Limit Buy", "Hold", "Limit Sell", "Market Sell")


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


def _normalize_response_text(response: object) -> str:
    normalized = normalize_content(response)
    content = getattr(normalized, "content", "")
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content).strip()


def _force_signal_first_line(text: str) -> str:
    body = str(text or "").strip()
    signal = parse_rating(body, default="Hold")
    lines = [line.strip() for line in body.splitlines()]
    first = lines[0] if lines else ""
    if first in _SIGNALS:
        rest = "\n".join(lines[1:]).strip()
        return f"{first}\n\n{rest}".strip()
    return f"{signal}\n\n{body}".strip()


def _extract_structured_decision(
    structured_llm,
    plain_llm,
    *,
    extraction_prompt: str,
    current_price: float | None,
) -> tuple[dict, list[str]]:
    if structured_llm is None:
        return {}, []

    _rendered, parsed_decision = invoke_structured_or_freetext_result(
        structured_llm,
        plain_llm,
        extraction_prompt,
        render_pm_decision,
        "Decision Extractor",
    )
    if parsed_decision is None:
        return {}, []

    payload = parsed_decision.model_dump(mode="json")
    validation_errors = validate_portfolio_decision(payload, current_price=current_price)
    return payload, validation_errors


def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Decision Extractor")

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
        verification_feedback = _format_structured_context(
            state.get("verification_report_structured") or {},
            state.get("verification_report") or "",
            [
                ("Verdict", "verdict"),
                ("Deterministic Checks", "deterministic_checks"),
                ("Evidence Support", "evidence_support"),
                ("Unsupported Claims", "unsupported_claims"),
                ("Confidence Note", "confidence_note"),
                ("Recommended Action", "recommended_action"),
            ],
        )
        verification_feedback_block = ""
        if verification_feedback:
            verification_feedback_block = (
                "Verifier feedback from the previous pass:\n"
                f"{verification_feedback}\n\n"
                "If the verifier asked for a revision, correct the signal and the structured price fields before you write the final decision again.\n"
            )

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading signal as readable prose.

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
    - The first line of your answer must be exactly one signal and nothing else:
      Market Buy, Limit Buy, Hold, Limit Sell, or Market Sell.
    - After the first line, write a concise prose explanation for a human reader. Do not output JSON.

**Context:**
- Research Manager's investment plan:\n{research_plan_context}
- Trader's transaction proposal:\n{trader_plan_context}
- Structured evidence ledger:\n{evidence_ledger}
{coinglass_context}
{lessons_line}
{verification_feedback_block}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        base_llm = resolve_structured_base_llm(llm)
        final_trade_decision = _force_signal_first_line(_normalize_response_text(base_llm.invoke(prompt)))
        current_price = fetch_current_binance_spot_price(state.get("company_of_interest") or "")

        extraction_prompt = f"""Extract a structured order plan from the Portfolio Manager prose.

Use only facts explicitly present in the prose and context. Do not invent missing prices.
Use signal-specific limit fields:
- primary_limit_buy_price / secondary_limit_buy_price only for Limit Buy.
- primary_limit_sell_price / secondary_limit_sell_price only for Limit Sell.
- Sell signals are long-only reduction or exit plans, never new short exposure.
- Sell signals must not contain buy ladders or upside take-profit ladders.

Current reference price: {current_price if current_price is not None else "unavailable"}

Portfolio Manager prose:
{final_trade_decision}

Research Manager handoff:
{research_plan_context}

Trader handoff:
{trader_plan_context}
"""

        structured_payload, validation_errors = _extract_structured_decision(
            structured_llm,
            llm,
            extraction_prompt=extraction_prompt,
            current_price=current_price,
        )
        if validation_errors and structured_payload:
            repair_prompt = f"""Repair the structured extraction only. Do not change the Portfolio Manager prose.

Validation errors:
{chr(10).join(f"- {error}" for error in validation_errors)}

Current reference price: {current_price if current_price is not None else "unavailable"}

Previous structured extraction:
{structured_payload}

Original Portfolio Manager prose:
{final_trade_decision}

Return a corrected structured extraction using the PortfolioDecision schema. If the prose does not support a safe numeric field, leave it empty.
"""
            repaired_payload, repaired_errors = _extract_structured_decision(
                structured_llm,
                llm,
                extraction_prompt=repair_prompt,
                current_price=current_price,
            )
            if repaired_payload and not repaired_errors:
                structured_payload = repaired_payload
                validation_errors = []
            else:
                validation_errors = repaired_errors or validation_errors

        if structured_payload:
            structured_payload["decision_validation_status"] = "invalid" if validation_errors else "valid"
            structured_payload["decision_validation_errors"] = validation_errors
            if current_price is not None:
                structured_payload["current_price"] = current_price

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
