"""Tests for Pydantic schemas used by agents that produce structured output.

Covers ExecutionSignal, DebateTurn, VerificationVerdict, VerificationReport,
PortfolioDecision, and their render helpers.
"""

import pytest
from pydantic import ValidationError

from tradingagents.agents.schemas import (
    DebateTurn,
    ExecutionSignal,
    PortfolioDecision,
    VerificationReport,
    VerificationVerdict,
    render_debate_turn,
    render_pm_decision,
    render_verification_report,
)


class TestExecutionSignal:
    def test_enum_values(self):
        assert ExecutionSignal.MARKET_BUY.value == "Market Buy"
        assert ExecutionSignal.LIMIT_BUY.value == "Limit Buy"
        assert ExecutionSignal.HOLD.value == "Hold"
        assert ExecutionSignal.LIMIT_SELL.value == "Limit Sell"
        assert ExecutionSignal.MARKET_SELL.value == "Market Sell"

    def test_enum_members_count(self):
        assert len(ExecutionSignal) == 5


class TestVerificationVerdict:
    def test_enum_values(self):
        assert VerificationVerdict.APPROVED.value == "Approved"
        assert VerificationVerdict.CAUTION.value == "Caution"
        assert VerificationVerdict.REVISE.value == "Revise"


class TestDebateTurn:
    def test_valid_debate_turn(self):
        turn = DebateTurn(
            thesis="Bullish on crypto due to ETF inflows.",
            supporting_evidence="ETF inflows reached $1B this week.",
            rebuttal="Some argue macro is bearish, but ETF flows offset this.",
            caveats="If ETF flows reverse, thesis invalidated.",
            action_bias="Add risk with a tight stop.",
        )
        assert turn.thesis == "Bullish on crypto due to ETF inflows."
        assert turn.supporting_evidence == "ETF inflows reached $1B this week."
        assert turn.caveats == "If ETF flows reverse, thesis invalidated."
        assert turn.action_bias == "Add risk with a tight stop."

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            DebateTurn(
                thesis="Only thesis provided.",
            )

    def test_render_debate_turn(self):
        turn = DebateTurn(
            thesis="Bullish.",
            supporting_evidence="Strong flows.",
            rebuttal="Macro risk overstated.",
            caveats="Volatility risk.",
            action_bias="Add small position.",
        )
        rendered = render_debate_turn(turn)
        assert "**Thesis**: Bullish." in rendered
        assert "**Supporting Evidence**: Strong flows." in rendered
        assert "**Rebuttal**: Macro risk overstated." in rendered
        assert "**Caveats**: Volatility risk." in rendered
        assert "**Action Bias**: Add small position." in rendered


class TestVerificationReport:
    def test_valid_approved_verdict(self):
        report = VerificationReport(
            verdict=VerificationVerdict.APPROVED,
            deterministic_checks="Price checks passed.",
            evidence_support="Market and onchain evidence support the decision.",
            unsupported_claims="None found.",
            issues=[],
            confidence_note="High confidence.",
            recommended_action="Proceed as is.",
        )
        assert report.verdict == VerificationVerdict.APPROVED
        assert report.issues == []

    def test_valid_caution_verdict(self):
        report = VerificationReport(
            verdict=VerificationVerdict.CAUTION,
            deterministic_checks="Order logic mostly sound.",
            evidence_support="Mixed evidence support.",
            unsupported_claims="Price target lacks source backing.",
            issues=["Price target is unsupported.", "Position sizing unclear."],
            confidence_note="Medium confidence.",
            recommended_action="Proceed with caution.",
        )
        assert report.verdict == VerificationVerdict.CAUTION
        assert len(report.issues) == 2

    def test_valid_revise_verdict(self):
        report = VerificationReport(
            verdict=VerificationVerdict.REVISE,
            deterministic_checks="Stop loss is above entry - incorrect.",
            evidence_support="Evidence contradicts the decision.",
            unsupported_claims="Multiple unsupported claims.",
            issues=["Stop loss logic error.", "Signal unsupported by evidence."],
            confidence_note="Low confidence.",
            recommended_action="Revise and re-run.",
        )
        assert report.verdict == VerificationVerdict.REVISE

    def test_verdict_normalization_approved_variants(self):
        for raw in ["approved", "approve", "pass", "passed", "ok", "okay", "proceed", "APPROVED", " Approved "]:
            report = VerificationReport(
                verdict=raw,
                deterministic_checks="",
                evidence_support="",
                unsupported_claims="",
                confidence_note="",
                recommended_action="",
            )
            assert report.verdict == VerificationVerdict.APPROVED

    def test_verdict_normalization_caution_variants(self):
        for raw in ["caution", "cautious", "warning", "warn", "proceed with caution"]:
            report = VerificationReport(
                verdict=raw,
                deterministic_checks="",
                evidence_support="",
                unsupported_claims="",
                confidence_note="",
                recommended_action="",
            )
            assert report.verdict == VerificationVerdict.CAUTION

    def test_verdict_normalization_revise_variants(self):
        for raw in ["revise", "revision", "needs revision", "requires revision", "reject", "rejected", "fail", "failed"]:
            report = VerificationReport(
                verdict=raw,
                deterministic_checks="",
                evidence_support="",
                unsupported_claims="",
                confidence_note="",
                recommended_action="",
            )
            assert report.verdict == VerificationVerdict.REVISE

    def test_text_field_normalization_list(self):
        report = VerificationReport(
            verdict=VerificationVerdict.APPROVED,
            deterministic_checks=["Check 1", "Check 2"],
            evidence_support=["Evidence A", "Evidence B"],
            unsupported_claims="",
            confidence_note=["High", "clear signal"],
            recommended_action=["Proceed"],
        )
        assert "Check 1" in report.deterministic_checks
        assert "Check 2" in report.deterministic_checks
        assert "Evidence A" in report.evidence_support

    def test_text_field_normalization_dict(self):
        report = VerificationReport(
            verdict=VerificationVerdict.APPROVED,
            deterministic_checks={"check1": "passed", "check2": "passed"},
            evidence_support="",
            unsupported_claims="",
            confidence_note="",
            recommended_action="",
        )
        assert "check1: passed" in report.deterministic_checks

    def test_text_field_normalization_none(self):
        report = VerificationReport(
            verdict=VerificationVerdict.APPROVED,
            deterministic_checks=None,
            evidence_support=None,
            unsupported_claims=None,
            confidence_note=None,
            recommended_action=None,
        )
        assert report.deterministic_checks == ""
        assert report.unsupported_claims == ""

    def test_issues_normalization_string_none(self):
        report = VerificationReport(
            verdict=VerificationVerdict.APPROVED,
            deterministic_checks="",
            evidence_support="",
            unsupported_claims="",
            confidence_note="",
            recommended_action="",
            issues="None",
        )
        assert report.issues == []

    def test_issues_normalization_na(self):
        report = VerificationReport(
            verdict=VerificationVerdict.APPROVED,
            deterministic_checks="",
            evidence_support="",
            unsupported_claims="",
            confidence_note="",
            recommended_action="",
            issues="n/a",
        )
        assert report.issues == []

    def test_issues_normalization_string_lines(self):
        report = VerificationReport(
            verdict=VerificationVerdict.APPROVED,
            deterministic_checks="",
            evidence_support="",
            unsupported_claims="",
            confidence_note="",
            recommended_action="",
            issues="- Issue 1\n- Issue 2",
        )
        assert report.issues == ["Issue 1", "Issue 2"]

    def test_issues_normalization_dict(self):
        report = VerificationReport(
            verdict=VerificationVerdict.APPROVED,
            deterministic_checks="",
            evidence_support="",
            unsupported_claims="",
            confidence_note="",
            recommended_action="",
            issues={"a": "problem a", "b": "problem b"},
        )
        assert len(report.issues) == 2

    def test_render_verification_report(self):
        report = VerificationReport(
            verdict=VerificationVerdict.APPROVED,
            deterministic_checks="All checks passed.",
            evidence_support="Strong support from market and onchain.",
            unsupported_claims="None.",
            issues=[],
            confidence_note="High confidence.",
            recommended_action="Proceed.",
        )
        rendered = render_verification_report(report)
        assert "**Verdict**: Approved" in rendered
        assert "**Deterministic Checks**" in rendered
        assert "**Evidence Support**" in rendered
        assert "**Confidence Note**" in rendered

    def test_render_verification_report_with_issues(self):
        report = VerificationReport(
            verdict=VerificationVerdict.REVISE,
            deterministic_checks="Problems found.",
            evidence_support="Weak.",
            unsupported_claims="Several.",
            issues=["Fix SL", "Fix TP"],
            confidence_note="Low.",
            recommended_action="Revise.",
        )
        rendered = render_verification_report(report)
        assert "- Fix SL" in rendered
        assert "- Fix TP" in rendered


class TestPortfolioDecision:
    def test_valid_market_buy(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.MARKET_BUY,
            execution_summary="Buy at market now.",
            market_context="Current price is attractive.",
            investment_thesis="Strong ETF flows and bullish onchain.",
            stop_loss=90000.0,
            take_profit=110000.0,
        )
        assert decision.signal == ExecutionSignal.MARKET_BUY
        assert decision.stop_loss == 90000.0
        assert decision.take_profit == 110000.0
        assert decision.primary_limit_buy_price is None
        assert decision.primary_limit_sell_price is None

    def test_valid_limit_buy(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.LIMIT_BUY,
            execution_summary="Buy at limit if dip occurs.",
            market_context="Price at resistance, wait for pullback.",
            investment_thesis="Bullish long term, better entry possible.",
            primary_limit_buy_price=95000.0,
            secondary_limit_buy_price=93000.0,
            stop_loss=88000.0,
            take_profit=110000.0,
            position_sizing="25% starter tranche",
            time_horizon="3-6 months",
        )
        assert decision.primary_limit_buy_price == 95000.0
        assert decision.secondary_limit_buy_price == 93000.0
        assert decision.position_sizing == "25% starter tranche"
        assert decision.time_horizon == "3-6 months"

    def test_valid_hold(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.HOLD,
            execution_summary="No action at this time.",
            market_context="Market is indecisive.",
            investment_thesis="No clear edge in either direction.",
        )
        assert decision.stop_loss is None
        assert decision.take_profit is None
        assert decision.primary_limit_buy_price is None

    def test_valid_limit_sell(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.LIMIT_SELL,
            execution_summary="Sell at limit to reduce exposure.",
            market_context="Overbought conditions, take some profit.",
            investment_thesis="Reduce long position at better price.",
            primary_limit_sell_price=120000.0,
            secondary_limit_sell_price=125000.0,
            stop_loss=110000.0,
            take_profit=105000.0,
        )
        assert decision.primary_limit_sell_price == 120000.0
        assert decision.secondary_limit_sell_price == 125000.0

    def test_valid_market_sell(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.MARKET_SELL,
            execution_summary="Exit long position now.",
            market_context="Bearish reversal confirmed.",
            investment_thesis="Fundamentals have changed, exit position.",
            stop_loss=95000.0,
            take_profit=80000.0,
        )
        assert decision.signal == ExecutionSignal.MARKET_SELL

    def test_signal_normalization_limit_buy_clears_sell_fields(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.LIMIT_BUY,
            execution_summary="Test.",
            market_context="Test.",
            investment_thesis="Test.",
            primary_limit_buy_price=100.0,
            secondary_limit_buy_price=90.0,
            primary_limit_sell_price=999.0,  # should be cleared
            secondary_limit_sell_price=888.0,  # should be cleared
            stop_loss=80.0,
            take_profit=120.0,
        )
        assert decision.primary_limit_sell_price is None
        assert decision.secondary_limit_sell_price is None

    def test_signal_normalization_limit_sell_clears_buy_fields(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.LIMIT_SELL,
            execution_summary="Test.",
            market_context="Test.",
            investment_thesis="Test.",
            primary_limit_buy_price=999.0,  # should be cleared
            secondary_limit_buy_price=888.0,  # should be cleared
            primary_limit_sell_price=150.0,
            secondary_limit_sell_price=160.0,
            stop_loss=170.0,
            take_profit=130.0,
        )
        assert decision.primary_limit_buy_price is None
        assert decision.secondary_limit_buy_price is None

    def test_signal_normalization_hold_clears_prices(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.HOLD,
            execution_summary="Test.",
            market_context="Test.",
            investment_thesis="Test.",
            stop_loss=100.0,
            take_profit=200.0,
        )
        assert decision.stop_loss is None
        assert decision.take_profit is None

    def test_signal_normalization_market_buy_clears_limit_fields(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.MARKET_BUY,
            execution_summary="Test.",
            market_context="Test.",
            investment_thesis="Test.",
            primary_limit_buy_price=100.0,
            secondary_limit_buy_price=90.0,
            stop_loss=80.0,
            take_profit=120.0,
        )
        assert decision.primary_limit_buy_price is None
        assert decision.secondary_limit_buy_price is None
        assert decision.stop_loss == 80.0
        assert decision.take_profit == 120.0

    def test_missing_required_fields_market_buy(self):
        with pytest.raises(ValidationError):
            PortfolioDecision(
                signal=ExecutionSignal.MARKET_BUY,
            )

    def test_optional_fields_none_by_default(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.HOLD,
            execution_summary="Wait.",
            market_context="Unclear.",
            investment_thesis="No edge.",
        )
        assert decision.position_sizing is None
        assert decision.time_horizon is None

    def test_render_pm_decision_market_buy(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.MARKET_BUY,
            execution_summary="Buy now.",
            market_context="Good price.",
            investment_thesis="Strong thesis.",
            stop_loss=90.0,
            take_profit=120.0,
        )
        rendered = render_pm_decision(decision)
        assert "Market Buy" in rendered
        assert "**Stop Loss:** 90.0" in rendered
        assert "**Take Profit:** 120.0" in rendered

    def test_render_pm_decision_limit_buy(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.LIMIT_BUY,
            execution_summary="Wait for dip.",
            market_context="Overbought.",
            investment_thesis="Bullish long term.",
            primary_limit_buy_price=95.0,
            secondary_limit_buy_price=90.0,
            stop_loss=85.0,
            take_profit=115.0,
            position_sizing="25%",
            time_horizon="3-6 months",
        )
        rendered = render_pm_decision(decision)
        assert "Limit Buy" in rendered
        assert "**Primary Limit Buy Price:** 95.0" in rendered
        assert "**Secondary Limit Buy Price:** 90.0" in rendered
        assert "**Position Sizing:** 25%" in rendered
        assert "**Time Horizon:** 3-6 months" in rendered

    def test_render_pm_decision_limit_sell(self):
        decision = PortfolioDecision(
            signal=ExecutionSignal.LIMIT_SELL,
            execution_summary="Reduce on strength.",
            market_context="Overbought, good exit opportunity.",
            investment_thesis="Take profit on long position.",
            primary_limit_sell_price=150.0,
            secondary_limit_sell_price=160.0,
            stop_loss=170.0,
            take_profit=130.0,
        )
        rendered = render_pm_decision(decision)
        assert "Limit Sell" in rendered
        assert "**Primary Limit Sell Price:** 150.0" in rendered
        assert "**Secondary Limit Sell Price:** 160.0" in rendered

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
