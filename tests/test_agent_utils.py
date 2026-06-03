"""Tests for agent utility functions: language instruction, instrument context,
coinglass context, coinglass package resolution, and message deletion helper."""

import pytest

from tradingagents.agents.utils.agent_utils import (
    get_language_instruction,
    build_instrument_context,
    get_coinglass_packages_for_role,
    get_preferred_reference_sources_instruction,
    _normalize_role_key,
    _role_aliases,
)
from tradingagents.dataflows.config import set_config, initialize_config


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config to defaults before and after each test."""
    initialize_config()
    yield
    initialize_config()


class TestNormalizeRoleKey:
    def test_standard_keys(self):
        assert _normalize_role_key("market_analyst") == "market_analyst"
        assert _normalize_role_key("onchain_analyst") == "onchain_analyst"
        assert _normalize_role_key("social_analyst") == "social_analyst"
        assert _normalize_role_key("news_analyst") == "news_analyst"

    def test_spaces_converted(self):
        assert _normalize_role_key("market analyst") == "market_analyst"
        assert _normalize_role_key("onchain analyst") == "onchain_analyst"

    def test_dashes_converted(self):
        assert _normalize_role_key("market-analyst") == "market_analyst"

    def test_case_normalized(self):
        assert _normalize_role_key("Market_Analyst") == "market_analyst"
        assert _normalize_role_key("ONCHAIN_ANALYST") == "onchain_analyst"

    def test_empty_input(self):
        assert _normalize_role_key("") == ""


class TestRoleAliases:
    def test_market_analyst_aliases(self):
        aliases = _role_aliases("market_analyst")
        assert "market" in aliases
        assert "market_analyst" in aliases

    def test_social_analyst_aliases(self):
        aliases = _role_aliases("social_analyst")
        assert "social" in aliases
        assert "sentiment" in aliases
        assert "social_analyst" in aliases

    def test_onchain_analyst_aliases(self):
        aliases = _role_aliases("onchain_analyst")
        assert "onchain" in aliases
        assert "onchain_analyst" in aliases

    def test_news_analyst_aliases(self):
        aliases = _role_aliases("news_analyst")
        assert "news" in aliases
        assert "news_analyst" in aliases

    def test_short_alias_resolves_to_full(self):
        aliases = _role_aliases("onchain")
        assert "onchain" in aliases
        assert "onchain_analyst" in aliases


class TestGetLanguageInstruction:
    def test_english_returns_empty(self):
        set_config({"output_language": "English"})
        assert get_language_instruction() == ""

    def test_english_case_insensitive(self):
        set_config({"output_language": "english"})
        assert get_language_instruction() == ""

    def test_vietnamese_returns_instruction(self):
        set_config({"output_language": "Vietnamese"})
        result = get_language_instruction()
        assert "Vietnamese" in result
        assert "Write your entire response in" in result

    def test_other_language(self):
        set_config({"output_language": "French"})
        result = get_language_instruction()
        assert "French" in result
        assert "Write your entire response in" in result

    def test_whitespace_handling(self):
        set_config({"output_language": "  English  "})
        assert get_language_instruction() == ""


class TestBuildInstrumentContext:
    def test_crypto_context(self):
        result = build_instrument_context("BTC-USDT", "crypto")
        assert "`BTC-USDT`" in result
        assert "crypto asset" in result.lower()
        assert "company financial statements" in result.lower()

    def test_non_crypto_context(self):
        result = build_instrument_context("AAPL", "stock")
        assert "`AAPL`" in result
        assert "instrument" in result.lower()
        assert "company financial statements" not in result.lower()

    def test_ticker_preserved(self):
        result = build_instrument_context("SOL/USDT")
        assert "`SOL/USDT`" in result

    def test_unknown_asset_type(self):
        result = build_instrument_context("ETH-USD", "forex")
        assert "`ETH-USD`" in result


class TestGetCoinglassPackagesForRole:
    def test_onchain_analyst_gets_default_packages(self):
        packages = get_coinglass_packages_for_role("onchain_analyst")
        assert len(packages) > 0
        assert "exchange_reserves" in packages
        assert "institutional_flow" in packages

    def test_market_analyst_empty_by_default(self):
        set_config({
            "coinglass_packages_by_role": {
                "market_analyst": (),
                "onchain_analyst": ("test_pkg",),
            },
        })
        packages = get_coinglass_packages_for_role("market_analyst")
        assert packages == ()

    def test_empty_role(self):
        packages = get_coinglass_packages_for_role("")
        assert packages == ()

    def test_role_alias_resolution(self):
        packages = get_coinglass_packages_for_role("onchain")
        assert len(packages) > 0

    def test_custom_packages_for_role(self):
        set_config({
            "coinglass_packages_by_role": {
                "bul_analyst": ("funding_pressure", "liquidation_risk"),
            },
        })
        packages = get_coinglass_packages_for_role("bul_analyst")
        assert "funding_pressure" in packages
        assert "liquidation_risk" in packages


class TestGetPreferredReferenceSourcesInstruction:
    def test_empty_sources(self):
        set_config({"preferred_reference_sources": []})
        assert get_preferred_reference_sources_instruction() == ""

    def test_with_sources(self):
        set_config({
            "preferred_reference_sources": [
                {
                    "name": "CryptoQuant",
                    "url": "https://cryptoquant.com",
                    "focus": "Exchange flows.",
                },
            ],
        })
        result = get_preferred_reference_sources_instruction()
        assert "CryptoQuant" in result
        assert "https://cryptoquant.com" in result
        assert "Exchange flows." in result

    def test_string_source(self):
        set_config({
            "preferred_reference_sources": ["CryptoQuant"],
        })
        result = get_preferred_reference_sources_instruction()
        assert "CryptoQuant" in result

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
