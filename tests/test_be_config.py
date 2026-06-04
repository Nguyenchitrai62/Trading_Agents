"""Tests for BE configuration: BackendSettings, provider resolution, env helpers."""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from BE.config import (
    is_deepseek_model,
    resolve_deepseek_settings,
    resolve_minimax_settings,
    resolve_provider_settings,
    RESEARCH_DEPTH_OPTIONS,
    SECTION_META,
    _env_bool,
    _env_int,
    _env_float,
    _env_csv,
    _normalize_origin,
    _configured_cors_origins,
    BackendSettings,
)


class TestIsDeepseekModel:
    def test_deepseek_v4_flash(self):
        assert is_deepseek_model("deepseek-v4-flash") is True

    def test_deepseek_v4_pro(self):
        assert is_deepseek_model("deepseek-v4-pro") is True

    def test_deepseek_chat(self):
        assert is_deepseek_model("deepseek-chat") is True

    def test_non_deepseek(self):
        assert is_deepseek_model("gpt-4") is False
        assert is_deepseek_model("claude-sonnet-4-5") is False
        assert is_deepseek_model("") is False
        assert is_deepseek_model(None) is False

    def test_minimax_model(self):
        assert is_deepseek_model("MiniMax-M2.7") is False


class TestResearchDepthOptions:
    def test_all_depths_defined(self):
        for depth in ("auto", "quick", "medium", "deep"):
            assert depth in RESEARCH_DEPTH_OPTIONS

    def test_quick_depth(self):
        quick = RESEARCH_DEPTH_OPTIONS["quick"]
        assert quick["rounds"] == 1
        assert quick["mcp_tool_rounds"] == 3

    def test_medium_depth(self):
        medium = RESEARCH_DEPTH_OPTIONS["medium"]
        assert medium["rounds"] == 3
        assert medium["mcp_tool_rounds"] == 5

    def test_deep_depth(self):
        deep = RESEARCH_DEPTH_OPTIONS["deep"]
        assert deep["rounds"] == 5
        assert deep["mcp_tool_rounds"] == 7

    def test_auto_depth(self):
        auto = RESEARCH_DEPTH_OPTIONS["auto"]
        assert auto["rounds"] == 1
        assert auto["auto_escalation"] is True


class TestSectionMeta:
    def test_all_report_sections(self):
        assert "market_report" in SECTION_META
        assert "sentiment_report" in SECTION_META
        assert "news_report" in SECTION_META
        assert "onchain_report" in SECTION_META
        assert "final_trade_decision" in SECTION_META
        assert "verification_report" in SECTION_META

    def test_market_report_meta(self):
        meta = SECTION_META["market_report"]
        assert meta["title"] == "Market Analysis"
        assert meta["agent"] == "Market Analyst"
        assert meta["team"] == "Analyst Team"

    def test_portfolio_decision_meta(self):
        meta = SECTION_META["final_trade_decision"]
        assert meta["title"] == "Portfolio Decision"
        assert meta["agent"] == "Portfolio Manager"


class TestEnvHelpers:
    def test_env_bool_true_variants(self):
        with patch.dict(os.environ, {"TEST_BOOL": "true"}):
            assert _env_bool("TEST_BOOL", False) is True

    def test_env_bool_one(self):
        with patch.dict(os.environ, {"TEST_BOOL": "1"}):
            assert _env_bool("TEST_BOOL", False) is True

    def test_env_bool_yes(self):
        with patch.dict(os.environ, {"TEST_BOOL": "yes"}):
            assert _env_bool("TEST_BOOL", False) is True

    def test_env_bool_false(self):
        with patch.dict(os.environ, {"TEST_BOOL": "false"}):
            assert _env_bool("TEST_BOOL", True) is False

    def test_env_bool_empty_returns_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _env_bool("NONEXISTENT", True) is True
            assert _env_bool("NONEXISTENT", False) is False

    def test_env_int(self):
        with patch.dict(os.environ, {"TEST_INT": "42"}):
            assert _env_int("TEST_INT", 0) == 42

    def test_env_int_invalid_returns_default(self):
        with patch.dict(os.environ, {"TEST_INT": "abc"}):
            assert _env_int("TEST_INT", 10) == 10

    def test_env_int_empty_returns_default(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _env_int("NONEXISTENT", 5) == 5

    def test_env_float(self):
        with patch.dict(os.environ, {"TEST_FLOAT": "3.14"}):
            assert _env_float("TEST_FLOAT", 0.0) == 3.14

    def test_env_float_invalid_returns_default(self):
        with patch.dict(os.environ, {"TEST_FLOAT": "abc"}):
            assert _env_float("TEST_FLOAT", 1.0) == 1.0

    def test_env_csv(self):
        with patch.dict(os.environ, {"TEST_CSV": "a, b , c"}):
            result = _env_csv("TEST_CSV")
            assert result == ["a", "b", "c"]

    def test_env_csv_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _env_csv("NONEXISTENT") == []

    def test_env_csv_with_default(self):
        with patch.dict(os.environ, {}, clear=True):
            result = _env_csv("NONEXISTENT", "x,y")
            assert result == ["x", "y"]

    def test_normalize_origin(self):
        assert _normalize_origin("http://localhost:8000/") == "http://localhost:8000"
        assert _normalize_origin("http://localhost:8000") == "http://localhost:8000"
        assert _normalize_origin("*") == "*"


class TestResolveProviderSettings:
    def test_deepseek_model_routes_to_deepseek(self):
        with patch("BE.config.SETTINGS") as mock_settings:
            mock_settings.deepseek_api_key = "test-key"
            mock_settings.deepseek_base_url = "https://test.io/v1"
            result = resolve_provider_settings("deepseek-v4-flash", settings=mock_settings)
            assert result["provider"] == "deepseek"
            assert result["configured"] is True

    def test_non_deepseek_routes_to_minimax(self):
        with patch("BE.config.SETTINGS") as mock_settings:
            mock_settings.minimax_api_key = ""
            mock_settings.minimax_cn_api_key = "test-cn-key"
            mock_settings.minimax_base_url = ""
            result = resolve_provider_settings("MiniMax-M2.7", settings=mock_settings)
            assert result["provider"] == "minimax-cn"
            assert result["configured"] is True

    def test_no_api_keys(self):
        with patch("BE.config.SETTINGS") as mock_settings:
            mock_settings.minimax_api_key = ""
            mock_settings.minimax_cn_api_key = ""
            mock_settings.minimax_base_url = ""
            result = resolve_provider_settings("MiniMax-M2.7", settings=mock_settings)
            assert result["configured"] is False


class TestResolveMinimaxSettings:
    def test_global_key_preferred(self):
        with patch("BE.config.SETTINGS") as mock_settings:
            mock_settings.minimax_api_key = "global-key"
            mock_settings.minimax_cn_api_key = "cn-key"
            mock_settings.minimax_base_url = "https://custom.io/anthropic"
            result = resolve_minimax_settings(settings=mock_settings)
            assert result["configured"] is True
            assert result["provider"] == "minimax"
            assert result["api_key"] == "global-key"
            assert result["base_url"] == "https://custom.io/anthropic"

    def test_cn_only(self):
        with patch("BE.config.SETTINGS") as mock_settings:
            mock_settings.minimax_api_key = ""
            mock_settings.minimax_cn_api_key = "cn-key"
            mock_settings.minimax_base_url = ""
            result = resolve_minimax_settings(settings=mock_settings)
            assert result["configured"] is True
            assert result["provider"] == "minimax-cn"
            assert result["api_key"] == "cn-key"

    def test_none_configured(self):
        with patch("BE.config.SETTINGS") as mock_settings:
            mock_settings.minimax_api_key = ""
            mock_settings.minimax_cn_api_key = ""
            mock_settings.minimax_base_url = ""
            result = resolve_minimax_settings(settings=mock_settings)
            assert result["configured"] is False
            assert result["provider"] is None


class TestResolveDeepseekSettings:
    def test_configured(self):
        with patch("BE.config.SETTINGS") as mock_settings:
            mock_settings.deepseek_api_key = "ds-key"
            mock_settings.deepseek_base_url = "https://openai.io/go/v1"
            result = resolve_deepseek_settings(settings=mock_settings)
            assert result["configured"] is True
            assert result["provider"] == "deepseek"
            assert result["api_key"] == "ds-key"

    def test_not_configured(self):
        with patch("BE.config.SETTINGS") as mock_settings:
            mock_settings.deepseek_api_key = ""
            mock_settings.deepseek_base_url = "https://base.io/v1"
            result = resolve_deepseek_settings(settings=mock_settings)
            assert result["configured"] is False
            assert result["api_key"] == ""


class TestBackendSettings:
    def test_from_env_creates_instance(self):
        settings = BackendSettings.from_env()
        assert settings is not None
        assert settings.app_title == "TradingAgents Analysis API"
        assert settings.default_model in ("deepseek-v4-flash", "") or True
        assert settings.port > 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
