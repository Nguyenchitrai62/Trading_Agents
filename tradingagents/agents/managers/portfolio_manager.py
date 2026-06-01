"""Portfolio Manager: prose-first final signal."""

from __future__ import annotations

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_coinglass_context_instruction,
    get_coinglass_packages_for_role,
    get_language_instruction,
)
from tradingagents.agents.utils.evidence import format_evidence_ledger
from tradingagents.agents.utils.rating import parse_rating
from tradingagents.agents.utils.structured import resolve_structured_base_llm
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


def create_portfolio_manager(llm):
    def portfolio_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])

        risk_debate_state = state["risk_debate_state"]
        history = risk_debate_state.get("history", "")
        investment_debate_state = state.get("investment_debate_state") or {}
        research_debate_context = investment_debate_state.get("history", "")
        market_report = state.get("market_report", "")
        onchain_report = state.get("onchain_report", "")
        social_report = state.get("sentiment_report", "")
        news_report = state.get("news_report", "")
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=18)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=get_coinglass_packages_for_role("portfolio_manager"),
        )
        verification_feedback = _format_structured_context(
            state.get("verification_report_structured") or {},
            state.get("verification_report") or "",
            [
                ("Verdict", "verdict"),
                ("Deterministic Checks", "deterministic_checks"),
                ("Evidence Support", "evidence_support"),
                ("Unsupported Claims", "unsupported_claims"),
                ("Issues", "issues"),
                ("Confidence Note", "confidence_note"),
                ("Recommended Action", "recommended_action"),
            ],
        )
        verification_feedback_block = ""
        if verification_feedback:
            verification_feedback_block = (
                "Verifier feedback from the previous pass:\n"
                f"{verification_feedback}\n\n"
                "If the verifier asked for a revision, correct the signal, price levels, and evidence support before you write the final decision again.\n"
            )

        past_context = state.get("past_context", "")
        lessons_line = (
            f"- Lessons from prior decisions and outcomes:\n{past_context}\n"
            if past_context
            else ""
        )

        prompt = f"""As the Portfolio Manager, synthesize the three one-pass risk scenario memos and deliver the final trading signal as readable prose.

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
    - For **Market Buy** and **Market Sell**, stop-loss and take-profit are mandatory because a later verified extraction step persists these fields for execution review.
    - For **Limit Sell** or **Market Sell**, do not include a new short thesis or an upside take-profit ladder. Use **Position Sizing** to say how much of the current long to trim or exit, and use **Stop Loss**/**Take Profit** only for remaining long exposure or the next exit objective.
    - The first line of your answer must be exactly one signal and nothing else:
      Market Buy, Limit Buy, Hold, Limit Sell, or Market Sell.
    - After the first line, write a concise prose explanation for a human reader. Do not output JSON.

**Context:**
- Market report:\n{market_report}
- Onchain report:\n{onchain_report}
- Social report:\n{social_report}
- News report:\n{news_report}
- Bull/Bear research debate:\n{research_debate_context}
- Structured evidence ledger:\n{evidence_ledger}
{coinglass_context}
{lessons_line}
{verification_feedback_block}
**Risk Scenario Memos:**
{history}

---

Use the aggressive, neutral, and conservative scenario memos as three independent risk lenses. Choose the final action yourself; do not request another risk pass. Be decisive and ground every conclusion in specific evidence from the analysts.{get_language_instruction()}"""

        base_llm = resolve_structured_base_llm(llm)
        final_trade_decision = _force_signal_first_line(_normalize_response_text(base_llm.invoke(prompt)))

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
            "final_trade_decision_structured": {},
        }

    return portfolio_manager_node
