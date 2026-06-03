"""Tests for BE request/response Pydantic models.

Covers AnalysisRequest, ChatRequest, AuthSessionRequest, and admin models.
"""

import pytest
from pydantic import ValidationError

from BE.models import (
    AnalysisRequest,
    ChatRequest,
    Message,
    AuthSessionRequest,
    AdminUserAccessUpdate,
    AdminHistoryAccessUpdate,
    realtime_analysis_date,
)


class TestRealtimeAnalysisDate:
    def test_returns_iso_date_string(self):
        result = realtime_analysis_date()
        import datetime
        parsed = datetime.date.fromisoformat(result)
        today = datetime.date.today()
        assert parsed == today


class TestAnalysisRequest:
    def test_valid_request(self):
        req = AnalysisRequest(
            symbol="BTC-USDT",
            asset_type="crypto",
            analysis_date="2025-01-15",
            lookback_days=30,
            output_language="Vietnamese",
            selected_analysts=["market", "onchain", "social", "news"],
            research_depth="medium",
            model="deepseek-v4-flash",
        )
        assert req.symbol == "BTC-USDT"
        assert req.asset_type == "crypto"
        assert req.lookback_days == 30
        assert len(req.selected_analysts) == 4

    def test_symbol_normalization_adds_usdt(self):
        req = AnalysisRequest(symbol="btc")
        assert req.symbol == "BTC-USDT"

    def test_symbol_normalization_with_separator(self):
        req = AnalysisRequest(symbol="ETH/USDT")
        assert req.symbol == "ETH/USDT"

    def test_symbol_normalization_case_and_spaces(self):
        req = AnalysisRequest(symbol="  sol / USDT  ")
        assert req.symbol == "SOL/USDT"

    def test_empty_symbol_raises(self):
        with pytest.raises(ValidationError):
            AnalysisRequest(symbol="")

    def test_selected_analysts_deduplication(self):
        req = AnalysisRequest(
            symbol="BTC-USDT",
            selected_analysts=["market", "market", "onchain"],
        )
        assert req.selected_analysts == ["market", "onchain"]

    def test_selected_analysts_empty_raises(self):
        with pytest.raises(ValidationError):
            AnalysisRequest(symbol="BTC-USDT", selected_analysts=[])

    def test_analysis_date_always_real_time(self):
        req = AnalysisRequest(
            symbol="BTC-USDT",
            analysis_date="2020-01-01",
        )
        today = realtime_analysis_date()
        assert req.analysis_date == today

    def test_lookback_days_minimum(self):
        with pytest.raises(ValidationError):
            AnalysisRequest(symbol="BTC-USDT", lookback_days=0)

    def test_default_values(self):
        req = AnalysisRequest(symbol="BTC-USDT")
        assert req.asset_type == "crypto"
        assert req.output_language is not None
        assert len(req.selected_analysts) == 4

    def test_run_id_normalization(self):
        req = AnalysisRequest(symbol="BTC-USDT", run_id="  my-run-123  ")
        assert req.run_id == "my-run-123"

    def test_run_id_none(self):
        req = AnalysisRequest(symbol="BTC-USDT", run_id=None)
        assert req.run_id is None

    def test_run_id_empty_string(self):
        req = AnalysisRequest(symbol="BTC-USDT", run_id="")
        assert req.run_id is None

    def test_output_language_empty_raises(self):
        with pytest.raises(ValidationError):
            AnalysisRequest(symbol="BTC-USDT", output_language="")


class TestMessage:
    def test_valid_message(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_assistant_message(self):
        msg = Message(role="assistant", content="Hi there")
        assert msg.role == "assistant"


class TestChatRequest:
    def test_valid_request(self):
        req = ChatRequest(
            messages=[Message(role="user", content="Hello")],
            model="deepseek-v4-flash",
            stream=True,
        )
        assert len(req.messages) == 1
        assert req.stream is True

    def test_default_values(self):
        req = ChatRequest(
            messages=[Message(role="user", content="Test")],
        )
        assert req.model != ""
        assert req.temperature == 1


class TestAuthSessionRequest:
    def test_valid_request(self):
        req = AuthSessionRequest(id_token="test-token-123")
        assert req.id_token == "test-token-123"

    def test_empty_token_raises(self):
        with pytest.raises(ValidationError):
            AuthSessionRequest(id_token="")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValidationError):
            AuthSessionRequest(id_token="   ")

    def test_token_trimmed(self):
        req = AuthSessionRequest(id_token="  token-value  ")
        assert req.id_token == "token-value"


class TestAdminModels:
    def test_admin_user_access_update(self):
        update = AdminUserAccessUpdate(
            is_admin=True,
            can_run_analysis=True,
            history_access_days=30,
        )
        assert update.is_admin is True
        assert update.can_run_analysis is True
        assert update.history_access_days == 30

    def test_admin_user_access_update_partial(self):
        update = AdminUserAccessUpdate(history_access_unlimited=True)
        assert update.is_admin is None
        assert update.history_access_days is None
        assert update.history_access_unlimited is True

    def test_admin_history_access_update(self):
        update = AdminHistoryAccessUpdate(history_public_read=True)
        assert update.history_public_read is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
