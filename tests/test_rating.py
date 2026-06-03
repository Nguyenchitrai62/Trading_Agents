"""Tests for signal rating/parsing from prose text.

Covers parse_rating heuristics for explicit signal labels and fallback matching.
"""

from tradingagents.agents.utils.rating import parse_rating, TRADING_SIGNALS


class TestTradingSignals:
    def test_canonical_order(self):
        assert TRADING_SIGNALS == (
            "Market Buy", "Limit Buy", "Hold", "Limit Sell", "Market Sell",
        )


class TestParseRating:
    def test_explicit_signal_label(self):
        text = "Signal: Market Buy\nReasoning follows..."
        assert parse_rating(text) == "Market Buy"

    def test_explicit_with_colon_dash(self):
        text = "Execution Signal - Limit Buy\nBased on the analysis..."
        assert parse_rating(text) == "Limit Buy"

    def test_explicit_recommendation_label(self):
        text = "Recommendation: Hold\nNo clear direction at this time."
        assert parse_rating(text) == "Hold"

    def test_explicit_action_label(self):
        text = "Action: Limit Sell\nReduce position at better prices."
        assert parse_rating(text) == "Limit Sell"

    def test_explicit_trading_signal_label(self):
        text = "Trading Signal: Market Sell\nExit the position now."
        assert parse_rating(text) == "Market Sell"

    def test_vietnamese_khuyen_nghi(self):
        text = "Khuyen nghi cuoi cung: Hold\nThi truong khong ro rang."
        assert parse_rating(text) == "Hold"

    def test_vietnamese_quyet_dinh(self):
        text = "Quyet dinh giao dich cuoi cung: Limit Buy\nGia hien tai: 100000."
        assert parse_rating(text) == "Limit Buy"

    def test_fallback_phrase_in_prose(self):
        text = "After thorough analysis, I recommend a limit buy at 95000."
        assert parse_rating(text) == "Limit Buy"

    def test_fallback_signal_in_text(self):
        text = "The market conditions suggest a Market Buy is the best approach."
        assert parse_rating(text) == "Market Buy"

    def test_alias_buy_now(self):
        text = "Recommendation: buy now at current price."
        assert parse_rating(text) == "Market Buy"

    def test_alias_sell_now(self):
        text = "Action: sell now to protect profits."
        assert parse_rating(text) == "Market Sell"

    def test_default_when_no_signal(self):
        text = "The market is complex and many factors are at play."
        assert parse_rating(text) == "Hold"

    def test_default_when_no_signal_custom_default(self):
        text = "Unclear what to do."
        assert parse_rating(text, default="Market Sell") == "Market Sell"

    def test_empty_text(self):
        assert parse_rating("") == "Hold"

    def test_debate_turn_text(self):
        text = """
        **Thesis**: The market is bullish.
        **Supporting Evidence**: ETF inflows are strong.
        **Rebuttal**: Macro risk exists but is overstated.
        **Caveats**: Watch for reversal at resistance.
        **Action Bias**: Add risk. Overall signal: Limit Buy.
        """
        assert parse_rating(text) == "Limit Buy"

    def test_signal_in_markdown_header(self):
        text = "# Market Buy Recommendation\n\nBullish conditions..."
        assert parse_rating(text) == "Market Buy"

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
