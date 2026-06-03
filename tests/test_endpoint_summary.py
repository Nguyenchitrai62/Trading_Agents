"""Tests for endpoint summary compression utilities."""

import pytest

from tradingagents.dataflows.endpoint_summary import (
    summarize_endpoint_result,
    endpoint_summaries_to_evidence_items,
    format_endpoint_summaries_for_prompt,
)


class TestSummarizeEndpointResult:
    def test_empty_result(self):
        result = summarize_endpoint_result(
            endpoint_name="test_endpoint",
            request_metadata={},
            endpoint_result={},
            symbol="BTC",
            analysis_date="2025-01-15",
        )
        assert isinstance(result, dict)
        assert "endpoint_name" in result or "title" in result

    def test_result_with_data(self):
        result = summarize_endpoint_result(
            endpoint_name="open_interest",
            request_metadata={"endpoint": "open_interest"},
            endpoint_result={
                "data": [
                    {"time": "2025-01-15", "value": 1000},
                    {"time": "2025-01-16", "value": 1100},
                ],
                "status": "success",
            },
            symbol="BTC",
            analysis_date="2025-01-15",
        )
        assert isinstance(result, dict)

    def test_encodes_summary_strings(self):
        result = summarize_endpoint_result(
            endpoint_name="funding_rate",
            request_metadata={},
            endpoint_result={"data": {"rate": 0.005, "symbol": "BTC"}, "status": "success"},
            symbol="ETH",
            analysis_date="2025-01-15",
        )
        assert isinstance(result, dict)
        for value in result.values():
            if isinstance(value, (list, dict)):
                continue
            if isinstance(value, float):
                continue


class TestEndpointSummariesToEvidenceItems:
    def test_empty_summaries(self):
        items = endpoint_summaries_to_evidence_items(
            [],
            owner_agent_key="onchain",
            owner_agent_label="Onchain Analyst",
            analysis_date="2025-01-15",
        )
        assert items == []

    def test_basic_summary(self):
        summaries = [
            {
                "endpoint_name": "open_interest",
                "title": "Open Interest",
                "status": "success",
                "key_metrics": {"rows": 10},
                "direction": "bullish",
                "source": "CoinGlass",
                "summary_bullets": ["OI has increased 5% in 24h", "Funding rate is positive"],
            },
        ]
        items = endpoint_summaries_to_evidence_items(
            summaries,
            owner_agent_key="onchain",
            owner_agent_label="Onchain Analyst",
            analysis_date="2025-01-15",
        )
        assert len(items) > 0
        for item in items:
            assert "claim" in item
            assert "source" in item
            assert "direction" in item


class TestFormatEndpointSummariesForPrompt:
    def test_empty_summaries(self):
        result = format_endpoint_summaries_for_prompt([])
        assert result == ""

    def test_none_summaries(self):
        result = format_endpoint_summaries_for_prompt(None)
        assert result == ""

    def test_with_summaries(self):
        summaries = [
            {
                "endpoint_name": "open_interest",
                "title": "Open Interest",
                "package": "derivatives",
                "direction": "bullish",
                "confidence": 0.8,
            },
            {
                "endpoint_name": "funding_rate",
                "title": "Funding Rate",
                "package": "funding",
                "direction": "bearish",
                "confidence": 0.6,
            },
        ]
        result = format_endpoint_summaries_for_prompt(summaries)
        assert "Open Interest" in result
        assert "Funding Rate" in result

    def test_with_limit(self):
        summaries = [
            {"title": f"Endpoint {i}", "endpoint_name": f"endpoint_{i}"}
            for i in range(30)
        ]
        result = format_endpoint_summaries_for_prompt(summaries, limit=5)
        lines = result.split("\n")
        max_item_lines = 5 + 1  # header + 5 items
        assert len(lines) <= max_item_lines + 1  # + possible truncation line

    def test_focus_packages_filter(self):
        summaries = [
            {"title": "OIX", "endpoint_name": "oi", "package": "derivatives", "direction": "bullish"},
            {"title": "Funding", "endpoint_name": "funding", "package": "funding", "direction": "bearish"},
            {"title": "Liquidations", "endpoint_name": "liquidations", "package": "liquidation", "direction": "neutral"},
        ]
        result = format_endpoint_summaries_for_prompt(summaries, focus_packages=["funding"])
        assert "Funding" in result
        assert "OIX" not in result
        assert "Liquidations" not in result

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
