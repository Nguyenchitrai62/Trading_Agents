"""Tests for decision validation, signal normalization, and compatibility fields."""

from tradingagents.agents.utils.decision import (
    validate_portfolio_decision,
    normalize_signal,
    coerce_float,
    active_limit_prices,
    compatibility_decision_fields,
)


class TestNormalizeSignal:
    def test_canonical_signals(self):
        assert normalize_signal("Market Buy") == "Market Buy"
        assert normalize_signal("Limit Buy") == "Limit Buy"
        assert normalize_signal("Hold") == "Hold"
        assert normalize_signal("Limit Sell") == "Limit Sell"
        assert normalize_signal("Market Sell") == "Market Sell"

    def test_lowercase_aliases(self):
        assert normalize_signal("market buy") == "Market Buy"
        assert normalize_signal("limit buy") == "Limit Buy"
        assert normalize_signal("hold") == "Hold"
        assert normalize_signal("limit sell") == "Limit Sell"
        assert normalize_signal("market sell") == "Market Sell"

    def test_unknown_signal_passthrough(self):
        assert normalize_signal("Unknown") == "Unknown"
        assert normalize_signal("") == ""
        assert normalize_signal("Strong Buy") == "Strong Buy"

    def test_none_input(self):
        result = normalize_signal(None)
        assert result == ""

    def test_whitespace_handling(self):
        assert normalize_signal("  Market Buy  ") == "Market Buy"
        assert normalize_signal("  limit buy  ") == "Limit Buy"


class TestCoerceFloat:
    def test_valid_float(self):
        assert coerce_float(3.14) == 3.14
        assert coerce_float(42) == 42.0
        assert coerce_float("3.14") == 3.14
        assert coerce_float("42") == 42.0

    def test_invalid_float(self):
        assert coerce_float("abc") is None
        assert coerce_float(None) is None
        assert coerce_float("") is None

    def test_zero(self):
        assert coerce_float(0) == 0.0
        assert coerce_float("0") == 0.0

    def test_negative_float(self):
        assert coerce_float(-1.5) == -1.5
        assert coerce_float("-1.5") == -1.5


class TestActiveLimitPrices:
    def test_limit_buy(self):
        decision = {
            "signal": "Limit Buy",
            "primary_limit_buy_price": 100.0,
            "secondary_limit_buy_price": 90.0,
        }
        primary, secondary = active_limit_prices(decision)
        assert primary == 100.0
        assert secondary == 90.0

    def test_limit_sell(self):
        decision = {
            "signal": "Limit Sell",
            "primary_limit_sell_price": 150.0,
            "secondary_limit_sell_price": 160.0,
        }
        primary, secondary = active_limit_prices(decision)
        assert primary == 150.0
        assert secondary == 160.0

    def test_market_buy(self):
        decision = {
            "signal": "Market Buy",
        }
        primary, secondary = active_limit_prices(decision)
        assert primary is None
        assert secondary is None

    def test_hold(self):
        decision = {"signal": "Hold"}
        primary, secondary = active_limit_prices(decision)
        assert primary is None
        assert secondary is None


class TestCompatibilityDecisionFields:
    def test_limit_buy_fields(self):
        decision = {
            "signal": "Limit Buy",
            "primary_limit_buy_price": 100.0,
            "secondary_limit_buy_price": 90.0,
            "stop_loss": 80.0,
            "take_profit": 120.0,
            "position_sizing": "25%",
            "time_horizon": "3-6 months",
        }
        fields = compatibility_decision_fields(decision)
        assert fields["primary_limit_price"] == 100.0
        assert fields["secondary_limit_price"] == 90.0
        assert fields["stop_loss"] == 80.0
        assert fields["take_profit"] == 120.0
        assert fields["position_sizing"] == "25%"
        assert fields["time_horizon"] == "3-6 months"

    def test_invalid_decision_clears_prices(self):
        decision = {
            "signal": "Limit Buy",
            "decision_validation_status": "invalid",
            "decision_validation_errors": ["primary_limit_buy_price is missing"],
            "primary_limit_buy_price": 100.0,
            "secondary_limit_buy_price": 90.0,
        }
        fields = compatibility_decision_fields(decision)
        assert fields["primary_limit_price"] is None

    def test_invalid_decision_clears_stop_loss(self):
        decision = {
            "signal": "Market Buy",
            "decision_validation_status": "invalid",
            "decision_validation_errors": ["stop_loss is too high"],
            "stop_loss": 110.0,
        }
        fields = compatibility_decision_fields(decision)
        assert fields["stop_loss"] is None


class TestValidatePortfolioDecision:
    def test_valid_market_buy(self):
        decision = {
            "signal": "Market Buy",
            "stop_loss": 90000.0,
            "take_profit": 110000.0,
        }
        errors = validate_portfolio_decision(decision, current_price=100000.0)
        assert errors == []

    def test_market_buy_missing_stop_loss(self):
        decision = {
            "signal": "Market Buy",
            "take_profit": 110000.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("stop_loss" in e.lower() for e in errors)

    def test_market_buy_stop_loss_above_price(self):
        decision = {
            "signal": "Market Buy",
            "stop_loss": 105000.0,
            "take_profit": 120000.0,
        }
        errors = validate_portfolio_decision(decision, current_price=100000.0)
        assert any("below" in e.lower() for e in errors)

    def test_market_buy_take_profit_below_price(self):
        decision = {
            "signal": "Market Buy",
            "stop_loss": 90000.0,
            "take_profit": 95000.0,
        }
        errors = validate_portfolio_decision(decision, current_price=100000.0)
        assert any("above" in e.lower() for e in errors)

    def test_market_buy_with_limit_fields(self):
        decision = {
            "signal": "Market Buy",
            "primary_limit_buy_price": 100.0,
            "stop_loss": 90.0,
            "take_profit": 120.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("limit ladder" in e.lower() for e in errors)

    def test_valid_limit_buy(self):
        decision = {
            "signal": "Limit Buy",
            "primary_limit_buy_price": 95000.0,
            "secondary_limit_buy_price": 93000.0,
            "stop_loss": 88000.0,
            "take_profit": 110000.0,
        }
        errors = validate_portfolio_decision(decision, current_price=100000.0)
        assert errors == []

    def test_limit_buy_missing_primary(self):
        decision = {
            "signal": "Limit Buy",
            "secondary_limit_buy_price": 93000.0,
            "stop_loss": 88000.0,
            "take_profit": 110000.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("primary_limit_buy_price" in e.lower() for e in errors)

    def test_limit_buy_price_above_current_without_breakout(self):
        decision = {
            "signal": "Limit Buy",
            "primary_limit_buy_price": 105000.0,
            "secondary_limit_buy_price": 103000.0,
            "stop_loss": 98000.0,
            "take_profit": 120000.0,
        }
        errors = validate_portfolio_decision(decision, current_price=100000.0)
        assert any("breakout" in e.lower() for e in errors)

    def test_limit_buy_price_above_current_with_breakout(self):
        decision = {
            "signal": "Limit Buy",
            "primary_limit_buy_price": 105000.0,
            "secondary_limit_buy_price": 103000.0,
            "stop_loss": 98000.0,
            "take_profit": 120000.0,
            "execution_summary": "breakout confirmation triggered",
        }
        errors = validate_portfolio_decision(decision, current_price=100000.0)
        # Should not have the breakout error
        breakout_errors = [e for e in errors if "breakout" in e.lower()]
        assert len(breakout_errors) == 0

    def test_limit_buy_stop_loss_above_entry(self):
        decision = {
            "signal": "Limit Buy",
            "primary_limit_buy_price": 100.0,
            "secondary_limit_buy_price": 90.0,
            "stop_loss": 105.0,
            "take_profit": 150.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("below" in e.lower() for e in errors)

    def test_valid_hold(self):
        decision = {"signal": "Hold"}
        errors = validate_portfolio_decision(decision)
        assert errors == []

    def test_hold_with_prices(self):
        decision = {
            "signal": "Hold",
            "stop_loss": 100.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("executable prices" in e.lower() for e in errors)

    def test_valid_limit_sell(self):
        decision = {
            "signal": "Limit Sell",
            "primary_limit_sell_price": 120000.0,
            "secondary_limit_sell_price": 125000.0,
            "stop_loss": 130000.0,
            "take_profit": 110000.0,
        }
        errors = validate_portfolio_decision(decision, current_price=115000.0)
        assert errors == []

    def test_limit_sell_below_current_price(self):
        decision = {
            "signal": "Limit Sell",
            "primary_limit_sell_price": 90000.0,
            "secondary_limit_sell_price": 95000.0,
            "stop_loss": 100000.0,
            "take_profit": 80000.0,
        }
        errors = validate_portfolio_decision(decision, current_price=100000.0)
        assert any("below current price" in e.lower() for e in errors)

    def test_limit_sell_stop_loss_below_limit(self):
        decision = {
            "signal": "Limit Sell",
            "primary_limit_sell_price": 120.0,
            "secondary_limit_sell_price": 130.0,
            "stop_loss": 110.0,
            "take_profit": 100.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("above the sell limit" in e.lower() for e in errors)

    def test_limit_sell_take_profit_above_limit(self):
        decision = {
            "signal": "Limit Sell",
            "primary_limit_sell_price": 120.0,
            "secondary_limit_sell_price": 130.0,
            "stop_loss": 140.0,
            "take_profit": 150.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("below the sell limit" in e.lower() for e in errors)

    def test_valid_market_sell(self):
        decision = {
            "signal": "Market Sell",
            "stop_loss": 105000.0,
            "take_profit": 90000.0,
        }
        errors = validate_portfolio_decision(decision)
        assert errors == []

    def test_market_sell_with_limit_fields(self):
        decision = {
            "signal": "Market Sell",
            "primary_limit_buy_price": 100.0,
            "stop_loss": 105.0,
            "take_profit": 90.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("limit ladder" in e.lower() for e in errors)

    def test_market_sell_with_buy_entries(self):
        decision = {
            "signal": "Market Sell",
            "primary_limit_buy_price": 100.0,
            "stop_loss": 105.0,
            "take_profit": 90.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("buy entry" in e.lower() for e in errors)

    def test_sell_signal_short_exposure(self):
        decision = {
            "signal": "Market Sell",
            "stop_loss": 105.0,
            "take_profit": 90.0,
            "execution_summary": "Open a new short position on weakness.",
        }
        errors = validate_portfolio_decision(decision)
        assert any("short exposure" in e.lower() for e in errors)

    def test_invalid_signal(self):
        decision = {"signal": "Strong Buy"}
        errors = validate_portfolio_decision(decision)
        assert any("exactly one of" in e.lower() for e in errors)

    def test_limit_sell_with_buy_entries(self):
        decision = {
            "signal": "Limit Sell",
            "primary_limit_sell_price": 150.0,
            "secondary_limit_sell_price": 160.0,
            "primary_limit_buy_price": 100.0,
            "stop_loss": 170.0,
            "take_profit": 130.0,
        }
        errors = validate_portfolio_decision(decision)
        assert any("buy entry" in e.lower() for e in errors)

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
