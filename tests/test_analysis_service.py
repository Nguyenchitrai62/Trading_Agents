"""Tests for AnalysisService: config building, slot management, analyst filtering,
symbol normalization, and runtime profile resolution."""

import threading
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from BE.analysis.service import AnalysisService, ANALYSIS_RUNTIME_IMPORT_ERROR
from BE.config import BackendSettings
from BE.models import AnalysisRequest


@pytest.fixture
def mock_settings():
    """Create a mock BackendSettings with realistic defaults."""
    return MagicMock(
        spec=BackendSettings,
        analysis_max_concurrent_runs=2,
        analysis_llm_max_tokens=16384,
    )


@pytest.fixture
def mock_history_store():
    return MagicMock()


@pytest.fixture
def service(mock_settings, mock_history_store):
    return AnalysisService(mock_settings, mock_history_store)


class TestEnsureAnalysisRuntimeAvailable:
    def test_available_when_import_error_is_none(self, service):
        service.ensure_analysis_runtime_available()

    def test_raises_when_missing(self, service, monkeypatch):
        from fastapi import HTTPException
        exc = ModuleNotFoundError()
        exc.name = "test-dep"
        monkeypatch.setattr("BE.analysis.service.ANALYSIS_RUNTIME_IMPORT_ERROR", exc)
        with pytest.raises(HTTPException) as exc_info:
            service.ensure_analysis_runtime_available()
        assert exc_info.value.status_code == 500
        assert "test-dep" in exc_info.value.detail


class TestNormalizeTickerSymbol:
    def test_adds_usdt_suffix(self):
        result = AnalysisService.normalize_ticker_symbol("btc")
        assert result == "BTC-USDT"

    def test_preserves_slash(self):
        result = AnalysisService.normalize_ticker_symbol("ETH/USDT")
        assert result == "ETH/USDT"

    def test_preserves_dash(self):
        result = AnalysisService.normalize_ticker_symbol("SOL-USDT")
        assert result == "SOL-USDT"

    def test_uppercases(self):
        result = AnalysisService.normalize_ticker_symbol("eth")
        assert result == "ETH-USDT"

    def test_strips_spaces(self):
        result = AnalysisService.normalize_ticker_symbol("  btc  ")
        assert result == "BTC-USDT"

    def test_empty_string(self):
        result = AnalysisService.normalize_ticker_symbol("")
        assert result == ""


class TestFilterAnalystsForCrypto:
    def test_filters_valid_analysts(self):
        result = AnalysisService.filter_analysts_for_crypto(
            ["market", "onchain", "social", "news"]
        )
        assert result == ["market", "onchain", "social", "news"]

    def test_filters_spaces(self):
        result = AnalysisService.filter_analysts_for_crypto(
            ["  market  ", "onchain"]
        )
        assert result == ["market", "onchain"]

    def test_filters_empty_strings(self):
        result = AnalysisService.filter_analysts_for_crypto(["", "market", ""])
        assert result == ["market"]

    def test_returns_empty_on_all_empty(self):
        result = AnalysisService.filter_analysts_for_crypto(["", "  "])
        assert result == []


class TestSlotManagement:
    def test_initial_count_is_zero(self, service):
        assert service.active_analysis_count == 0

    def test_reserve_increments_count(self, service):
        assert service.try_reserve_analysis_slot() is True
        assert service.active_analysis_count == 1

    def test_reserve_up_to_max(self, service):
        assert service.try_reserve_analysis_slot() is True
        assert service.try_reserve_analysis_slot() is True
        assert service.try_reserve_analysis_slot() is False
        assert service.active_analysis_count == 2

    def test_release_decrements(self, service):
        service.try_reserve_analysis_slot()
        service.try_reserve_analysis_slot()
        service.release_analysis_slot()
        assert service.active_analysis_count == 1
        service.release_analysis_slot()
        assert service.active_analysis_count == 0

    def test_release_below_zero(self, service):
        service.release_analysis_slot()
        assert service.active_analysis_count == 0


class TestCancelRun:
    def test_no_active_run(self, service):
        result = service.cancel_run("nonexistent")
        assert result["cancelled"] is False
        assert result["run_id"] == "nonexistent"

    def test_cancels_active_run(self, service):
        event = threading.Event()
        with service.active_analysis_lock:
            service.active_analysis_cancel_events["test-run"] = event

        result = service.cancel_run("test-run")
        assert result["cancelled"] is True
        assert event.is_set()


class TestBuildAnalysisRuntimeProfile:
    def test_quick_depth(self, service):
        req = AnalysisRequest(symbol="BTC-USDT", research_depth="quick")
        profile = service.build_analysis_runtime_profile(req)
        assert profile["requested_depth"] == "quick"
        assert profile["effective_depth"] == "quick"
        assert profile["requested_rounds"] == 1
        assert profile["mcp_max_tool_rounds"] == 3
        assert profile["auto_escalation"] is False

    def test_medium_depth(self, service):
        req = AnalysisRequest(symbol="BTC-USDT", research_depth="medium")
        profile = service.build_analysis_runtime_profile(req)
        assert profile["requested_rounds"] == 3
        assert profile["mcp_max_tool_rounds"] == 5

    def test_deep_depth(self, service):
        req = AnalysisRequest(symbol="BTC-USDT", research_depth="deep")
        profile = service.build_analysis_runtime_profile(req)
        assert profile["requested_rounds"] == 5
        assert profile["mcp_max_tool_rounds"] == 7

    def test_auto_depth(self, service):
        req = AnalysisRequest(symbol="BTC-USDT", research_depth="auto")
        profile = service.build_analysis_runtime_profile(req)
        assert profile["requested_rounds"] == 1
        assert profile["auto_escalation"] is True


class TestBuildAnalysisConfig:
    @patch("BE.analysis.service.TRADINGAGENTS_DEFAULT_CONFIG", {
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.4",
        "quick_think_llm": "gpt-5.4-mini",
        "backend_url": None,
        "output_language": "English",
        "analysis_date": None,
        "analyst_concurrency_limit": 4,
        "coinglass_owner_analyst": "onchain",
        "coinglass_owner_agent_label": "Onchain Analyst",
        "minimax_mcp_enabled": True,
        "openai_quick_reasoning_effort": "max",
        "openai_deep_reasoning_effort": "max",
        "checkpoint_enabled": False,
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
    })
    @patch("BE.analysis.service.ANALYST_NODE_SPECS", {})
    def test_builds_deepseek_config(self, service):
        req = AnalysisRequest(
            symbol="BTC-USDT",
            quick_think_model="deepseek-v4-flash",
            deep_think_model="deepseek-v4-flash",
            research_depth="quick",
            output_language="Vietnamese",
            selected_analysts=["market", "onchain"],
            checkpoint_enabled=True,
        )
        profile = service.build_analysis_runtime_profile(req)
        provider = {"configured": True, "provider": "deepseek", "base_url": "https://test.io/v1"}
        config = service.build_analysis_config(req, provider, profile, ["market", "onchain"])
        assert config["llm_provider"] == "deepseek"
        assert config["quick_think_llm"] == "deepseek-v4-flash"
        assert config["deep_think_llm"] == "deepseek-v4-flash"
        assert config["output_language"] == "Vietnamese"
        assert config["minimax_mcp_enabled"] is False
        assert config["checkpoint_enabled"] is True
        assert config["max_debate_rounds"] == 1
        assert config["analyst_concurrency_limit"] == 4  # max(analyst_count=2, 4) = 4

    @patch("BE.analysis.service.TRADINGAGENTS_DEFAULT_CONFIG", {
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.4",
        "quick_think_llm": "gpt-5.4-mini",
        "backend_url": None,
        "output_language": "English",
        "analysis_date": None,
        "analyst_concurrency_limit": 4,
        "coinglass_owner_analyst": "market",
        "coinglass_owner_agent_label": "Market Analyst",
        "minimax_mcp_enabled": True,
        "openai_quick_reasoning_effort": "max",
        "openai_deep_reasoning_effort": "max",
        "checkpoint_enabled": False,
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
    })
    @patch("BE.analysis.service.ANALYST_NODE_SPECS", {
        "market": MagicMock(agent_node="Market Analyst"),
    })
    def test_builds_minimax_config(self, service):
        req = AnalysisRequest(
            symbol="BTC-USDT",
            quick_think_model="MiniMax-M2.7",
            deep_think_model="MiniMax-M2.7",
            research_depth="deep",
            selected_analysts=["market", "onchain", "social"],
        )
        profile = service.build_analysis_runtime_profile(req)
        provider = {"configured": True, "provider": "minimax", "base_url": "https://api.minimax.io/anthropic"}
        config = service.build_analysis_config(req, provider, profile, ["market", "onchain", "social"])
        assert config["llm_provider"] == "minimax"
        assert config["minimax_mcp_enabled"] is True
        assert config["minimax_mcp_max_tool_rounds"] == 7
        assert config["max_debate_rounds"] == 5
        assert config["max_risk_discuss_rounds"] == 5
        assert config["coinglass_owner_analyst"] == "market"

    @patch("BE.analysis.service.TRADINGAGENTS_DEFAULT_CONFIG", {
        "llm_provider": "openai",
        "deep_think_llm": "gpt-5.4",
        "quick_think_llm": "gpt-5.4-mini",
        "backend_url": None,
        "output_language": "English",
        "analysis_date": None,
        "analyst_concurrency_limit": 4,
        "coinglass_owner_analyst": "onchain",
        "coinglass_owner_agent_label": "Onchain Analyst",
        "minimax_mcp_enabled": True,
        "openai_quick_reasoning_effort": "max",
        "openai_deep_reasoning_effort": "max",
        "checkpoint_enabled": False,
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
    })
    @patch("BE.analysis.service.ANALYST_NODE_SPECS", {
        "market": MagicMock(agent_node="Market Analyst"),
    })
    def test_coinglass_owner_falls_back_when_not_selected(self, service):
        req = AnalysisRequest(
            symbol="BTC-USDT",
            quick_think_model="Minimax-M2.7",
            deep_think_model="Minimax-M2.7",
            research_depth="quick",
            selected_analysts=["market", "social"],
        )
        profile = service.build_analysis_runtime_profile(req)
        provider = {"configured": True, "provider": "minimax", "base_url": "https://api.minimax.io/anthropic"}
        config = service.build_analysis_config(req, provider, profile, ["market", "social"])
        assert config["coinglass_owner_analyst"] == "market"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
