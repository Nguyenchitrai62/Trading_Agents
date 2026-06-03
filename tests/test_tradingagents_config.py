"""Tests for tradingagents DEFAULT_CONFIG, env overrides, and config store."""

import os
from copy import deepcopy

import pytest

from tradingagents.agent_config import (
    DEFAULT_CONFIG,
    _apply_env_overrides,
    _coerce,
    _ENV_OVERRIDES,
)
from tradingagents.dataflows.config import (
    initialize_config,
    set_config,
    get_config,
)


class TestCoerce:
    def test_bool_true(self):
        assert _coerce("true", True) is True
        assert _coerce("1", True) is True
        assert _coerce("yes", True) is True
        assert _coerce("on", True) is True

    def test_bool_false(self):
        assert _coerce("false", True) is False
        assert _coerce("0", True) is False
        assert _coerce("no", True) is False

    def test_int(self):
        assert _coerce("42", 0) == 42
        assert isinstance(_coerce("42", 0), int)

    def test_float(self):
        assert _coerce("3.14", 0.0) == 3.14
        assert isinstance(_coerce("3.14", 0.0), float)

    def test_string(self):
        assert _coerce("hello", "") == "hello"


class TestDefaultConfig:
    def test_has_required_keys(self):
        required = [
            "llm_provider",
            "deep_think_llm",
            "quick_think_llm",
            "backend_url",
            "output_language",
            "analysis_date",
            "max_debate_rounds",
            "max_risk_discuss_rounds",
            "analyst_concurrency_limit",
            "coinglass_owner_analyst",
            "coinglass_owner_agent_label",
            "coinglass_prompt_char_limit",
            "coinglass_packages_by_role",
            "global_news_lookback_days",
            "crypto_market_lookback_days",
            "minimax_mcp_enabled",
            "minimax_mcp_tool_names",
            "minimax_mcp_max_tool_rounds",
            "checkpoint_enabled",
            "preferred_reference_sources",
        ]
        for key in required:
            assert key in DEFAULT_CONFIG, f"Missing key in DEFAULT_CONFIG: {key}"

    def test_llm_defaults(self):
        assert DEFAULT_CONFIG["llm_provider"] == "openai"
        assert DEFAULT_CONFIG["deep_think_llm"] == "gpt-5.4"
        assert DEFAULT_CONFIG["quick_think_llm"] == "gpt-5.4-mini"

    def test_debate_defaults(self):
        assert DEFAULT_CONFIG["max_debate_rounds"] == 1
        assert DEFAULT_CONFIG["max_risk_discuss_rounds"] == 1

    def test_mcp_defaults(self):
        assert DEFAULT_CONFIG["minimax_mcp_enabled"] is True
        assert DEFAULT_CONFIG["minimax_mcp_tool_names"] == "web_search"
        assert DEFAULT_CONFIG["minimax_mcp_max_tool_rounds"] == 6

    def test_output_language_default(self):
        assert DEFAULT_CONFIG["output_language"] == "English"

    def test_coinglass_packages(self):
        packages_by_role = DEFAULT_CONFIG["coinglass_packages_by_role"]
        assert "onchain_analyst" in packages_by_role
        assert len(packages_by_role["onchain_analyst"]) > 0
        assert "exchange_reserves" in packages_by_role["onchain_analyst"]

    def test_preferred_reference_sources(self):
        sources = DEFAULT_CONFIG["preferred_reference_sources"]
        assert len(sources) == 3
        names = [s["name"] for s in sources]
        assert "CryptoQuant" in names
        assert "SoSoValue" in names
        assert "TradingEconomics" in names


class TestEnvOverrides:
    def test_apply_env_overrides_with_no_vars(self):
        config = {"max_debate_rounds": 1}
        with patch.dict(os.environ, {}, clear=True):
            result = _apply_env_overrides(deepcopy(config))
            assert result["max_debate_rounds"] == 1

    def test_apply_env_overrides_with_int_var(self):
        config = {"max_debate_rounds": 1}
        with patch.dict(os.environ, {"TRADINGAGENTS_MAX_DEBATE_ROUNDS": "5"}, clear=False):
            result = _apply_env_overrides(deepcopy(config))
            assert result["max_debate_rounds"] == 5

    def test_apply_env_overrides_with_bool(self):
        config = {"checkpoint_enabled": False}
        with patch.dict(os.environ, {"TRADINGAGENTS_CHECKPOINT_ENABLED": "true"}, clear=False):
            result = _apply_env_overrides(deepcopy(config))
            assert result["checkpoint_enabled"] is True

    def test_apply_env_overrides_with_string(self):
        config = {"output_language": "English"}
        with patch.dict(os.environ, {"TRADINGAGENTS_OUTPUT_LANGUAGE": "Vietnamese"}, clear=False):
            result = _apply_env_overrides(deepcopy(config))
            assert result["output_language"] == "Vietnamese"

    def test_env_overrides_map_completeness(self):
        config = DEFAULT_CONFIG
        for env_var, key in _ENV_OVERRIDES.items():
            assert key in config, f"Key {key} from env var {env_var} not in DEFAULT_CONFIG"


class TestDataflowsConfig:
    def setup_method(self):
        initialize_config()

    def test_initialize_config_sets_defaults(self):
        initialize_config()
        config = get_config()
        assert config["llm_provider"] == "openai"

    def test_set_config_overrides_scalar(self):
        set_config({"output_language": "French"})
        config = get_config()
        assert config["output_language"] == "French"

    def test_set_config_merges_dict_nested(self):
        original = get_config()
        original_packages = original["coinglass_packages_by_role"].get("bull_researcher", ())
        set_config({
            "coinglass_packages_by_role": {
                "bull_researcher": ("exchange_reserves",),
            }
        })
        config = get_config()
        assert "exchange_reserves" in config["coinglass_packages_by_role"]["bull_researcher"]

    def test_get_config_returns_deepcopy(self):
        set_config({"output_language": "Spanish"})
        cfg1 = get_config()
        cfg2 = get_config()
        cfg1["output_language"] = "German"
        assert cfg2["output_language"] == "Spanish"

    def test_set_config_returns_deepcopy_of_incoming(self):
        incoming = {"output_language": "Korean"}
        set_config(incoming)
        incoming["output_language"] = "Japanese"
        assert get_config()["output_language"] == "Korean"


from unittest.mock import patch

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
