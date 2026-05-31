"""Pydantic schemas used by agents that produce structured output.

The framework's primary artifact is still prose: each agent's natural-language
reasoning is what users read in the saved markdown reports and what the
downstream agents read as context.  Structured output is layered onto the
three decision-making agents (Research Manager, Trader, Portfolio Manager)
so that:

- Their extracted handoffs follow consistent fields across runs and providers
- Each provider's native structured-output mode is used (json_schema for
  OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic)
- Schema field descriptions become the model's output instructions, freeing
  the prompt body to focus on context and the rating-scale guidance
- Render helpers can turn parsed Pydantic instances back into readable
  markdown when a fallback display is needed, but agent-facing reasoning stays
  prose-first.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Shared rating types
# ---------------------------------------------------------------------------


class PortfolioRating(str, Enum):
    """5-tier recommendation scale still used by the Research Manager."""

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class TraderAction(str, Enum):
    """3-tier transaction direction used by the Trader.

    The Trader's job is to translate the Research Manager's investment plan
    into a concrete transaction proposal: should the desk execute a Buy, a
    Sell, or sit on Hold this round. Position sizing and the final executable
    order plan happen later at the Portfolio Manager.
    """

    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"


class ExecutionSignal(str, Enum):
    """Actionable execution signal produced by the Portfolio Manager."""

    MARKET_BUY = "Market Buy"
    LIMIT_BUY = "Limit Buy"
    HOLD = "Hold"
    LIMIT_SELL = "Limit Sell"
    MARKET_SELL = "Market Sell"


# ---------------------------------------------------------------------------
# Research Manager
# ---------------------------------------------------------------------------


class ResearchPlan(BaseModel):
    """Structured investment plan produced by the Research Manager.

    Hand-off to the Trader: the recommendation pins the directional view,
    the rationale captures which side of the bull/bear debate carried the
    argument, and the strategic actions translate that into concrete
    instructions the trader can execute against.
    """

    recommendation: PortfolioRating = Field(
        description=(
            "The investment recommendation. Exactly one of Buy / Overweight / "
            "Hold / Underweight / Sell. Reserve Hold for situations where the "
            "evidence on both sides is genuinely balanced; otherwise commit to "
            "the side with the stronger arguments."
        ),
    )
    rationale: str = Field(
        description=(
            "Conversational summary of the key points from both sides of the "
            "debate, ending with which arguments led to the recommendation. "
            "Speak naturally, as if to a teammate."
        ),
    )
    strategic_actions: str = Field(
        description=(
            "Concrete steps for the trader to implement the recommendation, "
            "including position sizing guidance consistent with the rating."
        ),
    )


class DebateTurn(BaseModel):
    """Structured debate handoff used by non-tool debate and risk nodes."""

    thesis: str = Field(
        description=(
            "Core position this debater is advancing. Two to four sentences, "
            "anchored in the supplied reports and context."
        ),
    )
    supporting_evidence: str = Field(
        description=(
            "Specific evidence and signals from the supplied reports that "
            "support the thesis. Mention concrete facts, not generic claims."
        ),
    )
    rebuttal: str = Field(
        description=(
            "Direct response to the strongest opposing point so far. If no "
            "opposing view exists yet, say what objection is most likely and "
            "how this stance answers it."
        ),
    )
    caveats: str = Field(
        description=(
            "Main weaknesses, uncertainties, or invalidation conditions for "
            "this stance."
        ),
    )
    action_bias: str = Field(
        description=(
            "What this stance implies for the next decision step, such as add "
            "risk, reduce size, wait for confirmation, or avoid action."
        ),
    )


def render_debate_turn(turn: DebateTurn) -> str:
    """Render a DebateTurn to stable markdown for debate history and FE traces."""
    return "\n".join([
        f"**Thesis**: {turn.thesis}",
        "",
        f"**Supporting Evidence**: {turn.supporting_evidence}",
        "",
        f"**Rebuttal**: {turn.rebuttal}",
        "",
        f"**Caveats**: {turn.caveats}",
        "",
        f"**Action Bias**: {turn.action_bias}",
    ])


class VerificationVerdict(str, Enum):
    """Verifier outcome for the final portfolio decision."""

    APPROVED = "Approved"
    CAUTION = "Caution"
    REVISE = "Revise"


class VerificationReport(BaseModel):
    """Structured verification handoff after the Portfolio Manager."""

    verdict: VerificationVerdict = Field(
        description=(
            "Verification outcome. Use Approved when the decision is internally"
            " coherent and supported by evidence. Use Caution when the setup is"
            " mostly coherent but still has material caveats or thin evidence. Use"
            " Revise when deterministic blockers or unsupported claims make the"
            " current decision unsafe to trust as written."
        ),
    )
    deterministic_checks: str = Field(
        description=(
            "Summarize the deterministic order-logic checks, including current"
            " price context when available, any blockers, and any softer warnings."
        ),
    )
    evidence_support: str = Field(
        description=(
            "Explain whether the final signal is actually supported by the market,"
            " social, news, and flow evidence plus the intermediate structured"
            " handoffs from Research Manager and Trader."
        ),
    )
    unsupported_claims: str = Field(
        description=(
            "List any claims in the final decision that are not grounded in the"
            " available evidence or do not point to a source-supported rationale."
            " If none are found, say so explicitly."
        ),
    )
    confidence_note: str = Field(
        description=(
            "Short confidence note explaining the main reason this verification is"
            " strong, mixed, or weak."
        ),
    )
    recommended_action: str = Field(
        description=(
            "Precise next action after verification. For example: proceed as is,"
            " proceed with caution, revise price levels, or re-run after stronger"
            " evidence is collected."
        ),
    )


def render_verification_report(report: VerificationReport) -> str:
    """Render a VerificationReport to stable markdown for FE/history."""
    return "\n".join([
        f"**Verdict**: {report.verdict.value}",
        "",
        f"**Deterministic Checks**: {report.deterministic_checks}",
        "",
        f"**Evidence Support**: {report.evidence_support}",
        "",
        f"**Unsupported Claims**: {report.unsupported_claims}",
        "",
        f"**Confidence Note**: {report.confidence_note}",
        "",
        f"**Recommended Action**: {report.recommended_action}",
    ])


def render_research_plan(plan: ResearchPlan) -> str:
    """Render a ResearchPlan to markdown for storage and the trader's prompt context."""
    return "\n".join([
        f"**Recommendation**: {plan.recommendation.value}",
        "",
        f"**Rationale**: {plan.rationale}",
        "",
        f"**Strategic Actions**: {plan.strategic_actions}",
    ])


# ---------------------------------------------------------------------------
# Trader
# ---------------------------------------------------------------------------


class TraderProposal(BaseModel):
    """Structured transaction proposal produced by the Trader.

    The trader reads the Research Manager's investment plan and the analyst
    reports, then turns them into a concrete transaction: what action to
    take, the reasoning that justifies it, and the practical levels for
    entry, stop-loss, and sizing.
    """

    action: TraderAction = Field(
        description="The transaction direction. Exactly one of Buy / Hold / Sell.",
    )
    reasoning: str = Field(
        description=(
            "The case for this action, anchored in the analysts' reports and "
            "the research plan. Two to four sentences."
        ),
    )
    entry_price: Optional[float] = Field(
        default=None,
        description="Optional entry price target in the instrument's quote currency.",
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description="Optional stop-loss price in the instrument's quote currency.",
    )
    position_sizing: Optional[str] = Field(
        default=None,
        description="Optional sizing guidance, e.g. '5% of portfolio'.",
    )


def render_trader_proposal(proposal: TraderProposal) -> str:
    """Render a TraderProposal to markdown."""
    parts = [
        f"**Action**: {proposal.action.value}",
        "",
        f"**Reasoning**: {proposal.reasoning}",
    ]
    if proposal.entry_price is not None:
        parts.extend(["", f"**Entry Price**: {proposal.entry_price}"])
    if proposal.stop_loss is not None:
        parts.extend(["", f"**Stop Loss**: {proposal.stop_loss}"])
    if proposal.position_sizing:
        parts.extend(["", f"**Position Sizing**: {proposal.position_sizing}"])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Portfolio Manager
# ---------------------------------------------------------------------------


class PortfolioDecision(BaseModel):
    """Structured extraction of the prose Portfolio Manager decision.

    The Portfolio Manager first writes a readable final decision. This schema
    is used by the downstream extraction call so DB/FE consumers get stable
    fields without forcing the manager's reasoning itself into JSON.
    """

    signal: ExecutionSignal = Field(
        description=(
            "The final execution signal. Exactly one of Market Buy / Limit Buy / "
            "Hold / Limit Sell / Market Sell. Choose Market Buy or Market Sell "
            "only when the current market price is already attractive enough for "
            "immediate execution. Choose Limit Buy or Limit Sell only when waiting "
            "for specific price levels is clearly better than acting now. Use Hold "
            "only when the edge is too unclear to place any order yet. This "
            "workflow is long-only: Limit Sell and Market Sell mean reducing or "
            "exiting an existing long position, never opening a new short."
        ),
    )
    execution_summary: str = Field(
        description=(
            "A concise execution plan covering whether to act now or wait, which "
            "order type to place, and the key risk controls. Two to four sentences. "
            "If the signal is a sell, describe only the long-position reduction or "
            "exit plan."
        ),
    )
    market_context: str = Field(
        description=(
            "Explain why the current price is good enough for a market order, why "
            "specific limit levels are better, or why no order should be placed "
            "yet. This must directly justify the chosen signal. For Limit Sell, "
            "justify why waiting for a better exit level above or around current "
            "market is better than selling now."
        ),
    )
    investment_thesis: str = Field(
        description=(
            "Detailed reasoning anchored in specific evidence from the analysts' "
            "debate. If prior lessons are referenced in the prompt context, "
            "incorporate them; otherwise rely solely on the current analysis."
        ),
    )
    primary_limit_buy_price: Optional[float] = Field(
        default=None,
        description=(
            "Primary buy limit price in the instrument's quote currency. "
            "Required only when the signal is Limit Buy. Leave empty for Market "
            "Buy, Hold, Limit Sell, and Market Sell."
        ),
    )
    secondary_limit_buy_price: Optional[float] = Field(
        default=None,
        description=(
            "Optional second buy limit price for scaling into a long position. "
            "Use only when the signal is Limit Buy."
        ),
    )
    primary_limit_sell_price: Optional[float] = Field(
        default=None,
        description=(
            "Primary sell limit price in the instrument's quote currency. "
            "Required only when the signal is Limit Sell. In this long-only "
            "workflow, it is a better exit/reduction level for current long "
            "inventory, never a new short entry."
        ),
    )
    secondary_limit_sell_price: Optional[float] = Field(
        default=None,
        description=(
            "Optional second sell limit price for staging a long-position exit "
            "or reduction. Use only when the signal is Limit Sell."
        ),
    )
    stop_loss: Optional[float] = Field(
        default=None,
        description=(
            "Invalidation or stop-loss level in the instrument's quote currency. "
            "Required for Market Buy and Market Sell. Optional for Limit Buy or "
            "Limit Sell only when the prose explicitly says there is no remaining "
            "exposure after execution."
        ),
    )
    take_profit: Optional[float] = Field(
        default=None,
        description=(
            "First take-profit, target, or profit-protection level in the "
            "instrument's quote currency. Required for Market Buy and Market Sell. "
            "For Market Sell, this is the target level for any remaining long "
            "tranche or the next downside exit objective, not a new short thesis. "
            "Leave empty for Limit Sell in this long-only workflow."
        ),
    )
    position_sizing: Optional[str] = Field(
        default=None,
        description=(
            "Optional sizing guidance, e.g. '25% starter tranche' or 'no new "
            "position'. For sell signals, specify how much of the current long "
            "position to reduce or exit; do not describe new short exposure."
        ),
    )
    time_horizon: Optional[str] = Field(
        default=None,
        description="Optional recommended holding period, e.g. '3-6 months'.",
    )

    @model_validator(mode="after")
    def normalize_signal_specific_fields(self) -> "PortfolioDecision":
        if self.signal != ExecutionSignal.LIMIT_BUY:
            self.primary_limit_buy_price = None
            self.secondary_limit_buy_price = None
        if self.signal != ExecutionSignal.LIMIT_SELL:
            self.primary_limit_sell_price = None
            self.secondary_limit_sell_price = None
        if self.signal in {ExecutionSignal.LIMIT_SELL, ExecutionSignal.HOLD}:
            self.take_profit = None
        if self.signal == ExecutionSignal.HOLD:
            self.stop_loss = None
        return self

def render_pm_decision(decision: PortfolioDecision) -> str:
    """Render extracted PortfolioDecision fields to readable markdown."""
    parts = [
        decision.signal.value,
        "",
        f"**Execution Summary:** {decision.execution_summary}",
        "",
        f"**Market Context:** {decision.market_context}",
        "",
        f"**Investment Thesis:** {decision.investment_thesis}",
    ]
    if decision.primary_limit_buy_price is not None:
        parts.extend(["", f"**Primary Limit Buy Price:** {decision.primary_limit_buy_price}"])
    if decision.secondary_limit_buy_price is not None:
        parts.extend(["", f"**Secondary Limit Buy Price:** {decision.secondary_limit_buy_price}"])
    if decision.primary_limit_sell_price is not None:
        parts.extend(["", f"**Primary Limit Sell Price:** {decision.primary_limit_sell_price}"])
    if decision.secondary_limit_sell_price is not None:
        parts.extend(["", f"**Secondary Limit Sell Price:** {decision.secondary_limit_sell_price}"])
    if decision.stop_loss is not None:
        parts.extend(["", f"**Stop Loss:** {decision.stop_loss}"])
    if decision.take_profit is not None:
        parts.extend(["", f"**Take Profit:** {decision.take_profit}"])
    if decision.position_sizing:
        parts.extend(["", f"**Position Sizing:** {decision.position_sizing}"])
    if decision.time_horizon:
        parts.extend(["", f"**Time Horizon:** {decision.time_horizon}"])
    return "\n".join(parts)
