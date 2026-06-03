"""Tests for dataflows utilities: safe_ticker_component, get_current_date,
get_next_weekday, save_output, and normalize_content helper."""

import os
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from tradingagents.dataflows.utils import (
    safe_ticker_component,
    save_output,
    get_current_date,
    get_next_weekday,
)
from tradingagents.llm_clients.base_client import normalize_content


class TestSafeTickerComponent:
    def test_valid_tickers(self):
        assert safe_ticker_component("BTC") == "BTC"
        assert safe_ticker_component("ETH-USDT") == "ETH-USDT"
        assert safe_ticker_component("BTC_USDT") == "BTC_USDT"

    def test_alphanumeric(self):
        assert safe_ticker_component("BTC123") == "BTC123"

    def test_dots_in_ticker(self):
        assert safe_ticker_component("BTC.USD") == "BTC.USD"

    def test_index_symbol(self):
        assert safe_ticker_component("^GSPC") == "^GSPC"

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            safe_ticker_component("")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            safe_ticker_component(None)

    def test_long_ticker_raises(self):
        with pytest.raises(ValueError):
            safe_ticker_component("A" * 33)

    def test_path_traversal_raises(self):
        with pytest.raises(ValueError):
            safe_ticker_component("../../../etc/passwd")

    def test_dots_only_raises(self):
        with pytest.raises(ValueError):
            safe_ticker_component("..")

    def test_single_dot_raises(self):
        with pytest.raises(ValueError):
            safe_ticker_component(".")

    def test_invalid_chars(self):
        with pytest.raises(ValueError):
            safe_ticker_component("BTC\x00USDT")


class TestSaveOutput:
    def test_saves_csv(self):
        df = pd.DataFrame({"col": [1, 2, 3]})
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as f:
            path = f.name
        try:
            save_output(df, "test-tag", path)
            saved = pd.read_csv(path)
            assert len(saved) == 3
            assert "col" in saved.columns
        finally:
            os.unlink(path)

    def test_none_path_does_nothing(self):
        df = pd.DataFrame({"col": [1]})
        save_output(df, "tag", None)


class TestGetCurrentDate:
    def test_returns_today(self):
        result = get_current_date()
        from datetime import date
        today = date.today().strftime("%Y-%m-%d")
        assert result == today


class TestGetNextWeekday:
    def test_weekday_returns_same(self):
        wednesday = datetime(2025, 1, 15)  # Wednesday
        result = get_next_weekday(wednesday)
        assert result == wednesday

    def test_saturday_moves_to_monday(self):
        saturday = datetime(2025, 1, 18)  # Saturday
        result = get_next_weekday(saturday)
        assert result.weekday() < 5
        assert result.day == 20  # Monday

    def test_sunday_moves_to_monday(self):
        sunday = datetime(2025, 1, 19)  # Sunday
        result = get_next_weekday(sunday)
        assert result.weekday() < 5

    def test_string_date(self):
        result = get_next_weekday("2025-01-15")
        assert result.weekday() == 2  # Wednesday


class TestNormalizeContent:
    def test_string_content(self):
        response = MagicMock(content="Hello world")
        result = normalize_content(response)
        assert result.content == "Hello world"

    def test_list_content(self):
        response = MagicMock(content=[
            {"type": "text", "text": "Hello"},
            {"type": "text", "text": "World"},
        ])
        result = normalize_content(response)
        assert result.content == "Hello\nWorld"

    def test_list_with_reasoning(self):
        response = MagicMock(content=[
            {"type": "reasoning", "content": "Let me think..."},
            {"type": "text", "text": "Final answer."},
        ])
        result = normalize_content(response)
        assert result.content == "Final answer."

    def test_none_response(self):
        result = normalize_content(None)
        assert result is None

    def test_mixed_list(self):
        response = MagicMock(content=[
            "plain string",
            {"type": "text", "text": "structured text"},
        ])
        result = normalize_content(response)
        assert "plain string" in result.content
        assert "structured text" in result.content

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
