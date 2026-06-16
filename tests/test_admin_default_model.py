"""Tests for admin default-model runtime override and DB persistence."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from BE.analysis.service import AnalysisService
from BE.config import BackendSettings


@pytest.fixture
def mock_settings():
    return MagicMock(
        spec=BackendSettings,
        default_model="deepseek-v4-flash",
        analysis_max_concurrent_runs=2,
        analysis_llm_max_tokens=16384,
    )


@pytest.fixture
def mock_history_store():
    store = MagicMock()
    store.configured = False
    return store


@pytest.fixture
def service(mock_settings, mock_history_store):
    return AnalysisService(mock_settings, mock_history_store)


class TestDefaultModel:
    def test_get_default_model_returns_env_default_initially(self, service):
        assert service.get_default_model() == "deepseek-v4-flash"
        assert service.get_default_model_source() == "env"

    def test_set_default_model_updates_runtime_value(self, service):
        with patch("BE.analysis.service.resolve_provider_settings", return_value={"configured": True}):
            assert service.set_default_model("deepseek-v4-pro") is True
        assert service.get_default_model() == "deepseek-v4-pro"
        assert service.get_default_model_source() == "runtime"

    def test_set_default_model_rejects_empty_string(self, service):
        assert service.set_default_model("") is False

    def test_set_default_model_rejects_unconfigured_provider(self, service):
        with patch("BE.analysis.service.resolve_provider_settings", return_value={"configured": False}):
            assert service.set_default_model("minimax-m2.5") is False


class TestDefaultModelPersistence:
    def test_loads_persisted_model_from_db_when_provider_configured(self, mock_settings):
        store = MagicMock()
        store.configured = True
        store.get_app_setting.return_value = "minimax-m2.5"
        with patch("BE.analysis.service.resolve_provider_settings", return_value={"configured": True}):
            service = AnalysisService(mock_settings, store)
        assert service.get_default_model() == "minimax-m2.5"
        assert service.get_default_model_source() == "db"
        store.get_app_setting.assert_called_once_with("default_model")

    def test_falls_back_to_env_default_when_stored_provider_unconfigured(self, mock_settings):
        store = MagicMock()
        store.configured = True
        store.get_app_setting.return_value = "minimax-m2.5"
        with patch("BE.analysis.service.resolve_provider_settings", return_value={"configured": False}):
            service = AnalysisService(mock_settings, store)
        assert service.get_default_model() == "deepseek-v4-flash"
        assert service.get_default_model_source() == "env"

    def test_set_default_model_persists_to_db_when_configured(self, mock_settings):
        store = MagicMock()
        store.configured = True
        store.get_app_setting.return_value = None
        store.set_app_setting.return_value = True
        with patch("BE.analysis.service.resolve_provider_settings", return_value={"configured": True}):
            service = AnalysisService(mock_settings, store)
            assert service.set_default_model("deepseek-v4-pro") is True
        assert service.get_default_model() == "deepseek-v4-pro"
        assert service.get_default_model_source() == "db"
        store.set_app_setting.assert_called_once_with("default_model", "deepseek-v4-pro")

    def test_set_default_model_keeps_runtime_source_when_db_not_configured(self, mock_settings):
        store = MagicMock()
        store.configured = False
        with patch("BE.analysis.service.resolve_provider_settings", return_value={"configured": True}):
            service = AnalysisService(mock_settings, store)
            assert service.set_default_model("deepseek-v4-pro") is True
        assert service.get_default_model_source() == "runtime"
        store.set_app_setting.assert_not_called()
