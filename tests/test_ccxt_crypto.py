"""Integration tests for ccxt_crypto: validate ALL required timeframes are available on Binance.

No fallback. If any timeframe fails, the multi-timeframe market analysis is broken.
"""

import pytest

from tradingagents.dataflows.ccxt_crypto import (
    fetch_crypto_ohlcv_exact,
    get_crypto_bundle,
    _CRYPTO_INDICATOR_DESCRIPTIONS,
    _CRYPTO_TIMEFRAME_MINUTES,
)

_MARKET_TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w"]
_TEST_SYMBOL = "BTC-USDT"
_PREVIEW_LIMIT = 5

_KEY_INDICATORS = ["rsi", "macd", "close_200_sma"]


def _all_required_tfs():
    return list(_MARKET_TIMEFRAMES)


class TestTimeframeAvailability:
    def test_all_timeframes_in_crypto_timeframe_minutes(self):
        for tf in _MARKET_TIMEFRAMES:
            assert tf in _CRYPTO_TIMEFRAME_MINUTES, (
                f"Timeframe '{tf}' not found in _CRYPTO_TIMEFRAME_MINUTES. "
                f"Available: {sorted(_CRYPTO_TIMEFRAME_MINUTES)}"
            )

    def test_all_timeframes_ohlcv_available(self):
        """Every required TF must return valid OHLCV data from Binance."""
        failed = []
        for tf in _all_required_tfs():
            try:
                frame, policy = fetch_crypto_ohlcv_exact(
                    _TEST_SYMBOL, tf, preview_limit=_PREVIEW_LIMIT, exchange_name="binance"
                )
                assert len(frame) > 0, f"Empty DataFrame for {tf}"
                assert policy["timeframe"] == tf, f"Policy timeframe mismatch: {policy['timeframe']} != {tf}"
            except Exception as exc:
                failed.append(f"{tf}: {exc}")
        if failed:
            pytest.fail(
                f"Required timeframe(s) unavailable on Binance for {_TEST_SYMBOL}:\n"
                + "\n".join(f"  - {f}" for f in failed)
            )

    def test_all_timeframes_bundle_works(self):
        """get_crypto_bundle must return valid OHLCV + indicators for every TF."""
        failed = []
        for tf in _all_required_tfs():
            try:
                bundle = get_crypto_bundle(_TEST_SYMBOL, tf, preview_limit=_PREVIEW_LIMIT, exchange_name="binance")
                assert isinstance(bundle, dict), f"Bundle is not a dict for {tf}"
                assert "ohlcv" in bundle, f"Missing 'ohlcv' key for {tf}"
                assert "indicators" in bundle, f"Missing 'indicators' key for {tf}"
                assert "policy" in bundle, f"Missing 'policy' key for {tf}"
                assert isinstance(bundle["ohlcv"], str) and len(bundle["ohlcv"]) > 0, f"Empty OHLCV for {tf}"
                assert isinstance(bundle["indicators"], dict) and len(bundle["indicators"]) > 0, f"Empty indicators for {tf}"
                for ind_name in _CRYPTO_INDICATOR_DESCRIPTIONS:
                    assert ind_name in bundle["indicators"], f"Missing indicator '{ind_name}' for {tf}"
                    assert isinstance(bundle["indicators"][ind_name], str), f"Indicator '{ind_name}' not a string for {tf}"
                    assert len(bundle["indicators"][ind_name]) > 0, f"Empty indicator '{ind_name}' for {tf}"
            except Exception as exc:
                failed.append(f"{tf}: {exc}")
        if failed:
            pytest.fail(
                f"get_crypto_bundle failed for timeframe(s) on {_TEST_SYMBOL}:\n"
                + "\n".join(f"  - {f}" for f in failed)
            )

    def test_key_indicators_produce_valid_values(self):
        """Core indicators (RSI, MACD, SMA 200) must compute non-NaN latest values."""
        for tf in _all_required_tfs():
            bundle = get_crypto_bundle(_TEST_SYMBOL, tf, preview_limit=_PREVIEW_LIMIT, exchange_name="binance")
            for ind_name in _KEY_INDICATORS:
                ind_text = bundle["indicators"][ind_name]
                assert "Latest value:" in ind_text, f"'Latest value:' missing in {ind_name} for {tf}"
                latest_line = [line for line in ind_text.splitlines() if line.startswith("Latest value:")]
                assert latest_line, f"No 'Latest value:' line for {ind_name} in {tf}"
                latest_value = latest_line[0].split(":", 1)[-1].strip()
                assert latest_value, f"Empty latest value for {ind_name} in {tf}"

    def test_weekly_returns_minimum_candles(self):
        """1w timeframe with preview 50 should return at least 1 candle."""
        frame, policy = fetch_crypto_ohlcv_exact(
            _TEST_SYMBOL, "1w", preview_limit=50, exchange_name="binance"
        )
        assert len(frame) >= 1, "Weekly timeframe returned zero candles"


class TestExactTimeframeBehavior:
    def test_exact_timeframe_respected(self):
        """fetch_crypto_ohlcv_exact must use the exact requested TF, not auto-select."""
        for tf in ["15m", "1h", "4h"]:
            _, policy = fetch_crypto_ohlcv_exact(
                _TEST_SYMBOL, tf, preview_limit=5, exchange_name="binance"
            )
            assert policy["timeframe"] == tf, (
                f"Expected exact timeframe '{tf}' but got '{policy['timeframe']}'"
            )

    def test_invalid_timeframe_raises(self):
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            fetch_crypto_ohlcv_exact(_TEST_SYMBOL, "999m", preview_limit=5)

    def test_non_binance_raises(self):
        with pytest.raises(ValueError, match="binance"):
            fetch_crypto_ohlcv_exact(_TEST_SYMBOL, "1h", preview_limit=5, exchange_name="bybit")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
