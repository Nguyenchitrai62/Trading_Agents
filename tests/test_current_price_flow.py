"""Tests for current_price flow through analysis history persistence."""

import pytest
from unittest.mock import MagicMock, patch

from BE.models import AnalysisRequest


class TestCurrentPriceFlow:
    """Verify current_price is correctly passed through the persistence chain."""

    def _make_store(self):
        from BE.history.store import TursoHistoryStore
        store = TursoHistoryStore("http://localhost", "test-token")
        assert store.configured is True
        return store

    def _make_request(self, run_id: str, asset_type: str = "crypto") -> MagicMock:
        mock_request = MagicMock()
        mock_request.run_id = run_id
        mock_request.asset_type = asset_type
        mock_request.analysis_date = "2026-06-20"
        mock_request.quick_think_model = "MiniMax-M2.1"
        mock_request.deep_think_model = "MiniMax-M2.1"
        mock_request.output_language = "Vietnamese"
        mock_request.research_depth = "medium"
        return mock_request

    def test_save_analysis_always_refreshes_price_for_crypto(self):
        """save_analysis always calls fetch_reference_price for crypto; mock it
        so the expected price is returned and persisted."""
        from BE.history.store import TursoHistoryStore

        mock_future = MagicMock()
        mock_future.result.return_value = "history-123"

        mock_executor = MagicMock()
        mock_executor.__enter__ = MagicMock(return_value=mock_executor)
        mock_executor.__exit__ = MagicMock(return_value=False)
        mock_executor.submit.return_value = mock_future

        expected_price = 100000.5
        with patch.object(TursoHistoryStore, "ensure_schema"), \
             patch.object(TursoHistoryStore, "_execute_many"), \
             patch.object(TursoHistoryStore, "_build_save_analysis_statements") as mock_build, \
             patch("BE.history.store.ThreadPoolExecutor", return_value=mock_executor), \
             patch("tradingagents.agents.utils.market_price.fetch_reference_price") as mock_fetch:

            mock_fetch.return_value = (expected_price, "binance_spot_urllib")

            store = self._make_store()

            mock_sections = [
                {
                    "section_key": "final_trade_decision",
                    "markdown": "## Final Trade Decision\n\n**Signal**: Market Buy\n\n**Stop Loss**: 95000\n\n**Take Profit**: 115000",
                }
            ]

            store.save_analysis(
                request=self._make_request("test-run-123"),
                user={"email": "test@example.com", "sub": "sub123"},
                symbol="BTC-USDT",
                signal="Market Buy",
                elapsed_seconds=120.0,
                sections=mock_sections,
                decision_payload={"signal": "Market Buy", "primary_limit_price": 100000, "stop_loss": 95000, "take_profit": 115000},
                verification_payload={"verdict": "ACCEPTED", "recommended_action": "PROCEED"},
                current_price=99999.0,
            )

        mock_fetch.assert_called_once_with("BTC-USDT")
        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs["current_price"] == expected_price, \
            f"Expected current_price={expected_price}, got {call_kwargs['current_price']}"

    def test_save_analysis_skips_recovery_for_non_crypto(self):
        """The in-store recovery should NOT fire for non-crypto asset types."""
        from BE.history.store import TursoHistoryStore

        mock_future = MagicMock()
        mock_future.result.return_value = "history-789"

        mock_executor = MagicMock()
        mock_executor.__enter__ = MagicMock(return_value=mock_executor)
        mock_executor.__exit__ = MagicMock(return_value=False)
        mock_executor.submit.return_value = mock_future

        with patch.object(TursoHistoryStore, "ensure_schema"), \
             patch.object(TursoHistoryStore, "_execute_many"), \
             patch.object(TursoHistoryStore, "_build_save_analysis_statements") as mock_build, \
             patch("BE.history.store.ThreadPoolExecutor", return_value=mock_executor), \
             patch("tradingagents.agents.utils.market_price.fetch_reference_price") as mock_fetch:

            store = self._make_store()

            mock_sections = [{"section_key": "decision", "markdown": "## Decision\n\n**Signal**: Hold"}]

            store.save_analysis(
                request=self._make_request("test-run-789", asset_type="stock"),
                user={"email": "test@example.com", "sub": "sub789"},
                symbol="AAPL",
                signal="Hold",
                elapsed_seconds=90.0,
                sections=mock_sections,
                decision_payload={"signal": "Hold"},
                verification_payload={},
                current_price=None,
            )

        mock_fetch.assert_not_called()

        call_kwargs = mock_build.call_args.kwargs
        assert call_kwargs["current_price"] is None


class TestAnalysisRequestAssetType:
    """Verify AnalysisRequest defaults asset_type correctly."""

    def test_default_asset_type_is_crypto(self):
        req = AnalysisRequest(symbol="BTC-USDT")
        assert req.asset_type == "crypto"

    def test_asset_type_preserved_through_normalize(self):
        req = AnalysisRequest(symbol="BTC/USDT", asset_type="crypto")
        assert req.asset_type == "crypto"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
