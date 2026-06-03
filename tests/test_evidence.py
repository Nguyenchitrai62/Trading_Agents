"""Tests for evidence parsing, splitting, formatting, and markdown conversion."""

import json

from tradingagents.agents.utils.evidence import (
    split_report_and_evidence,
    format_evidence_ledger,
    evidence_items_to_markdown,
    get_structured_evidence_instruction,
    EVIDENCE_BLOCK_TAG,
)


class TestSplitReportAndEvidence:
    def test_split_with_valid_evidence_block(self):
        evidence_items = [
            {
                "claim": "BTC funding rate is positive.",
                "source": "CoinGlass",
                "source_type": "flow",
                "timestamp": "2025-01-15",
                "metric": "funding_rate",
                "value": "0.01%",
                "direction": "bullish",
                "confidence": 0.8,
                "freshness": "recent",
                "notes": "Strong bullish signal.",
            },
            {
                "claim": "Exchange reserves are decreasing.",
                "source": "CoinGlass",
                "source_type": "flow",
                "timestamp": "2025-01-15",
                "metric": "exchange_reserves",
                "value": "-500 BTC",
                "direction": "bullish",
                "confidence": 0.9,
                "freshness": "recent",
            },
        ]
        payload = json.dumps({"evidence_items": evidence_items})
        report = f"Market analysis report.\n<{EVIDENCE_BLOCK_TAG}>{payload}</{EVIDENCE_BLOCK_TAG}>"
        clean, items = split_report_and_evidence(
            report,
            agent_key="market",
            agent_label="Market Analyst",
            report_section="market_report",
            analysis_date="2025-01-15",
        )
        assert "Market analysis report." in clean
        assert f"<{EVIDENCE_BLOCK_TAG}>" not in clean
        assert f"</{EVIDENCE_BLOCK_TAG}>" not in clean
        assert len(items) == 2
        assert items[0]["agent"] == "market"
        assert items[0]["agent_label"] == "Market Analyst"
        assert items[0]["report_section"] == "market_report"
        assert items[0]["direction"] == "bullish"
        assert items[0]["confidence"] == 0.8
        assert items[1]["direction"] == "bullish"
        assert items[1]["confidence"] == 0.9

    def test_split_with_list_payload(self):
        evidence_items = [
            {
                "claim": "RSI is oversold.",
                "source": "TradingView",
                "source_type": "indicator",
                "timestamp": "2025-01-15",
                "metric": "RSI",
                "value": "28",
                "direction": "bullish",
                "confidence": 0.7,
                "freshness": "recent",
            },
        ]
        payload = json.dumps(evidence_items)
        report = f"Report text.\n<{EVIDENCE_BLOCK_TAG}>{payload}</{EVIDENCE_BLOCK_TAG}>"
        clean, items = split_report_and_evidence(
            report,
            agent_key="market",
            agent_label="Market Analyst",
            report_section="market_report",
            analysis_date="2025-01-15",
        )
        assert len(items) == 1
        assert items[0]["source"] == "TradingView"

    def test_split_with_missing_block_returns_fallback(self):
        report = "Just a prose report without any machine evidence block."
        clean, items = split_report_and_evidence(
            report,
            agent_key="news",
            agent_label="News Analyst",
            report_section="news_report",
            analysis_date="2025-01-15",
        )
        assert clean == report
        assert len(items) == 1
        assert items[0]["agent"] == "news"
        assert items[0]["source"] == "analyst_report"
        assert items[0]["direction"] == "unknown"
        assert items[0]["confidence"] == 0.2
        assert items[0]["metric"] == "structured_evidence_presence"
        assert items[0]["value"] == "missing"

    def test_split_with_empty_report_no_fallback(self):
        clean, items = split_report_and_evidence(
            "",
            agent_key="market",
            agent_label="Market Analyst",
            report_section="market_report",
            analysis_date="2025-01-15",
        )
        assert clean == ""
        assert items == []

    def test_split_with_invalid_json(self):
        report = f"Report text.\n<{EVIDENCE_BLOCK_TAG}>not valid json</{EVIDENCE_BLOCK_TAG}>"
        clean, items = split_report_and_evidence(
            report,
            agent_key="social",
            agent_label="Social Analyst",
            report_section="sentiment_report",
            analysis_date="2025-01-15",
        )
        assert len(items) == 1
        assert items[0]["value"] == "missing"

    def test_split_truncates_to_8_items(self):
        evidence_items = [
            {
                "claim": f"Claim {i}",
                "source": "Source",
                "source_type": "news",
                "direction": "neutral",
                "confidence": 0.5,
            }
            for i in range(15)
        ]
        payload = json.dumps({"evidence_items": evidence_items})
        report = f"Report.\n<{EVIDENCE_BLOCK_TAG}>{payload}</{EVIDENCE_BLOCK_TAG}>"
        clean, items = split_report_and_evidence(
            report,
            agent_key="news",
            agent_label="News Analyst",
            report_section="news_report",
            analysis_date="2025-01-15",
        )
        assert len(items) == 8

    def test_split_items_without_claim_skipped(self):
        evidence_items = [
            {
                "source": "Source",
                "source_type": "news",
            },
            {
                "claim": "Valid claim.",
                "source": "Source 2",
                "source_type": "news",
                "direction": "bearish",
                "confidence": 0.6,
            },
        ]
        payload = json.dumps({"evidence_items": evidence_items})
        report = f"Report.\n<{EVIDENCE_BLOCK_TAG}>{payload}</{EVIDENCE_BLOCK_TAG}>"
        clean, items = split_report_and_evidence(
            report,
            agent_key="news",
            agent_label="News Analyst",
            report_section="news_report",
            analysis_date="2025-01-15",
        )
        assert len(items) == 1
        assert items[0]["claim"] == "Valid claim."

    def test_split_with_items_key_instead_of_evidence_items(self):
        items_list = [
            {
                "claim": "Alt key test.",
                "source": "Src",
                "source_type": "other",
                "direction": "neutral",
                "confidence": 0.5,
            },
        ]
        payload = json.dumps({"items": items_list})
        report = f"Report.\n<{EVIDENCE_BLOCK_TAG}>{payload}</{EVIDENCE_BLOCK_TAG}>"
        clean, items = split_report_and_evidence(
            report,
            agent_key="market",
            agent_label="Market Analyst",
            report_section="market_report",
            analysis_date="2025-01-15",
        )
        assert len(items) == 1
        assert items[0]["claim"] == "Alt key test."


class TestFormatEvidenceLedger:
    def test_empty_items(self):
        result = format_evidence_ledger([])
        assert "unavailable" in result.lower()

    def test_none_items(self):
        result = format_evidence_ledger(None)
        assert "unavailable" in result.lower()

    def test_single_item(self):
        item = {
            "agent_label": "Market Analyst",
            "source": "CoinGlass",
            "metric": "funding_rate",
            "value": "0.05%",
            "direction": "bullish",
            "confidence": 0.8,
            "timestamp": "2025-01-15",
            "claim": "Funding rate is positive.",
            "notes": "Strong signal.",
        }
        result = format_evidence_ledger([item])
        assert "Market Analyst" in result
        assert "bullish" in result
        assert "0.80" in result
        assert "funding_rate=0.05%" in result

    def test_truncates_to_limit(self):
        items = [
            {
                "agent_label": f"Agent {i}",
                "source": f"Source {i}",
                "metric": f"metric_{i}",
                "value": f"val_{i}",
                "direction": "neutral",
                "confidence": 0.5,
                "timestamp": "2025-01-15",
                "claim": f"Claim {i}",
            }
            for i in range(30)
        ]
        result = format_evidence_ledger(items, limit=10)
        lines = result.split("\n")
        assert len(lines) <= 11  # 10 items + truncation line
        assert "more evidence item" in result.lower()

    def test_formats_without_agent_label(self):
        item = {
            "agent": "onchain",
            "source": "CoinGlass",
            "direction": "bearish",
            "confidence": 0.3,
            "timestamp": "2025-01-15",
            "claim": "Reserves increasing.",
            "metric": "reserves",
            "value": "1000 BTC",
        }
        result = format_evidence_ledger([item])
        assert "onchain" in result

    def test_confidence_clamping(self):
        item = {
            "agent_label": "Test",
            "source": "Test",
            "direction": "neutral",
            "confidence": 2.5,  # > 1.0, should be clamped to 1.0
            "timestamp": "2025-01-15",
            "claim": "Test.",
            "metric": "test",
            "value": "test",
        }
        result = format_evidence_ledger([item])
        assert "1.00" in result


class TestEvidenceItemsToMarkdown:
    def test_empty_items(self):
        result = evidence_items_to_markdown([])
        assert result == ""

    def test_none_items(self):
        result = evidence_items_to_markdown(None)
        assert result == ""

    def test_table_generation(self):
        items = [
            {
                "agent_label": "Market Analyst",
                "direction": "bullish",
                "confidence": 0.8,
                "metric": "funding",
                "value": "0.05%",
                "timestamp": "2025-01-15",
                "source": "CoinGlass",
                "claim": "Positive funding.",
            },
            {
                "agent": "onchain",
                "direction": "bearish",
                "confidence": 0.3,
                "metric": "reserves",
                "value": "+1000",
                "timestamp": "2025-01-15",
                "source": "CoinGlass",
                "claim": "Reserves increasing.",
            },
        ]
        result = evidence_items_to_markdown(items)
        assert "Market Analyst" in result
        assert "bullish" in result
        assert "0.80" in result
        assert "bearish" in result
        assert "0.30" in result


class TestGetStructuredEvidenceInstruction:
    def test_returns_non_empty_instruction(self):
        instruction = get_structured_evidence_instruction("market")
        assert EVIDENCE_BLOCK_TAG in instruction
        assert "evidence_items" in instruction
        assert "JSON" in instruction
        assert "market" in instruction

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
