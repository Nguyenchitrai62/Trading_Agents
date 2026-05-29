"""Trader: turns the Research Manager's investment plan into a concrete transaction proposal."""

from __future__ import annotations

import functools

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
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


def _format_research_plan_context(structured_plan: dict, fallback_markdown: str) -> str:
    if not structured_plan:
        return fallback_markdown

    parts = []
    recommendation = structured_plan.get("recommendation")
    rationale = structured_plan.get("rationale")
    strategic_actions = structured_plan.get("strategic_actions")

    if recommendation:
        parts.append(f"- Recommendation: {recommendation}")
    if rationale:
        parts.append(f"- Rationale: {rationale}")
    if strategic_actions:
        parts.append(f"- Strategic Actions: {strategic_actions}")

    return "\n".join(parts) if parts else fallback_markdown


def create_trader(llm):
    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def trader_node(state, name):
        company_name = state["company_of_interest"]
        asset_type = state.get("asset_type", "crypto")
        instrument_context = build_instrument_context(company_name, asset_type)
        investment_plan = state["investment_plan"]
        investment_plan_structured = state.get("investment_plan_structured") or {}
        investment_plan_context = _format_research_plan_context(
            investment_plan_structured,
            investment_plan,
        )
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=14)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=get_coinglass_packages_for_role("trader"),
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a trading agent analyzing market data to make investment decisions. "
                    "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
                    "Anchor your reasoning in the analysts' reports and the research plan."
                    + get_language_instruction()
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                    f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                    f"insights from current technical market trends, macroeconomic indicators, and "
                    f"social media sentiment. Use this structured handoff as a foundation for evaluating your next "
                    f"trading decision.\n\nResearch Manager Handoff:\n{investment_plan_context}\n\n"
                    f"Structured Evidence Ledger:\n{evidence_ledger}\n\n"
                    f"{coinglass_context}\n\n"
                    f"Leverage these insights to make an informed and strategic decision."
                ),
            },
        ]

        trader_plan, parsed_proposal = invoke_structured_or_freetext_result(
            structured_llm,
            llm,
            messages,
            render_trader_proposal,
            "Trader",
        )
        structured_payload = parsed_proposal.model_dump(mode="json") if parsed_proposal is not None else {}

        return {
            "messages": [AIMessage(content=trader_plan)],
            "trader_investment_plan": trader_plan,
            "trader_investment_plan_structured": structured_payload,
            "sender": name,
        }

    return functools.partial(trader_node, name="Trader")
