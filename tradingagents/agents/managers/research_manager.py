"""Research Manager: turns the bull/bear debate into a structured investment plan for the trader."""

from __future__ import annotations

from tradingagents.agents.schemas import ResearchPlan, render_research_plan
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
    resolve_structured_base_llm,
)
from tradingagents.llm_clients.base_client import normalize_content


def _response_text(response: object) -> str:
    normalized = normalize_content(response)
    content = getattr(normalized, "content", "")
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content).strip()


def create_research_manager(llm):
    structured_llm = bind_structured(llm, ResearchPlan, "Investment Plan Extractor")

    def research_manager_node(state) -> dict:
        instrument_context = build_instrument_context(state["company_of_interest"])
        history = state["investment_debate_state"].get("history", "")
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=18)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=get_coinglass_packages_for_role("research_manager"),
        )

        investment_debate_state = state["investment_debate_state"]

        prompt = f"""As the Research Manager and debate facilitator, critically evaluate this round of debate and deliver a clear, readable investment plan for the trader.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction in the bull thesis; recommend taking or growing the position
- **Overweight**: Constructive view; recommend gradually increasing exposure
- **Hold**: Balanced view; recommend maintaining the current position
- **Underweight**: Cautious view; recommend trimming exposure
- **Sell**: Strong conviction in the bear thesis; recommend exiting or avoiding the position

Commit to a clear stance whenever the debate's strongest arguments warrant one; reserve Hold for situations where the evidence on both sides is genuinely balanced.
Write prose for a human trader. Do not output JSON.

---

**Debate History:**
{history}

**Structured Evidence Ledger:**
{evidence_ledger}
{coinglass_context}""" + get_language_instruction()

        base_llm = resolve_structured_base_llm(llm)
        investment_plan = _response_text(base_llm.invoke(prompt))

        extraction_prompt = f"""Extract the Research Manager prose into the ResearchPlan schema.

Use only the recommendation, rationale, and strategic actions supported by the prose. Do not invent details missing from the plan.

Research Manager prose:
{investment_plan}
"""
        parsed_plan = None
        if structured_llm is not None:
            _rendered_plan, parsed_plan = invoke_structured_or_freetext_result(
                structured_llm,
                llm,
                extraction_prompt,
                render_research_plan,
                "Investment Plan Extractor",
            )
        structured_payload = parsed_plan.model_dump(mode="json") if parsed_plan is not None else {}

        new_investment_debate_state = {
            "judge_decision": investment_plan,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": investment_plan,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": investment_plan,
            "investment_plan_structured": structured_payload,
        }

    return research_manager_node
