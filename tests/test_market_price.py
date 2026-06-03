"""Tests for Binance market price fetching and symbol normalization."""

import pytest

from tradingagents.agents.utils.market_price import (
    normalize_binance_symbol,
    fetch_current_binance_spot_price,
)


class TestNormalizeBinanceSymbol:
    def test_standard_format_with_slash(self):
        api_symbol, market_symbol = normalize_binance_symbol("BTC/USDT")
        assert api_symbol == "BTCUSDT"
        assert market_symbol == "BTC/USDT"

    def test_standard_format_with_dash(self):
        api_symbol, market_symbol = normalize_binance_symbol("BTC-USDT")
        assert api_symbol == "BTCUSDT"
        assert market_symbol == "BTC/USDT"

    def test_lowercase_input(self):
        api_symbol, market_symbol = normalize_binance_symbol("btc/usdt")
        assert api_symbol == "BTCUSDT"
        assert market_symbol == "BTC/USDT"

    def test_spaces_in_input(self):
        api_symbol, market_symbol = normalize_binance_symbol(" BTC / USDT ")
        assert api_symbol == "BTCUSDT"
        assert market_symbol == "BTC/USDT"

    def test_usd_to_usdt_conversion(self):
        api_symbol, market_symbol = normalize_binance_symbol("ETH/USD")
        assert api_symbol == "ETHUSDT"
        assert market_symbol == "ETH/USDT"

    def test_multiple_dashes(self):
        api_symbol, market_symbol = normalize_binance_symbol("BTC-USD")
        assert api_symbol == "BTCUSDT"
        assert market_symbol == "BTC/USDT"

    def test_sol_usdt(self):
        api_symbol, market_symbol = normalize_binance_symbol("SOL/USDT")
        assert api_symbol == "SOLUSDT"
        assert market_symbol == "SOL/USDT"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            normalize_binance_symbol("")

    def test_no_separator_raises(self):
        with pytest.raises(ValueError):
            normalize_binance_symbol("BTC")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            normalize_binance_symbol(None)


class TestFetchCurrentBinanceSpotPrice:
    def test_invalid_symbol_returns_none(self):
        result = fetch_current_binance_spot_price("INVALID")
        assert result is None

    def test_empty_symbol_returns_none(self):
        result = fetch_current_binance_spot_price("")
        assert result is None

    def test_valid_symbol_makes_request(self):
        result = fetch_current_binance_spot_price("BTC/USDT")
        if result is not None:
            assert isinstance(result, float)
            assert result > 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
