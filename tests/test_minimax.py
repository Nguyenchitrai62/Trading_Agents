"""Tests for MiniMax Anthropic-compatible client.
"""

import os
import pytest

from tradingagents.llm_clients import anthropic_client as mod
from tradingagents.llm_clients.factory import create_llm_client


def _capture_kwargs(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        mod, "NormalizedChatAnthropic",
        lambda **kwargs: captured.setdefault("kwargs", kwargs),
    )
    return captured


@pytest.mark.unit
class TestMinimaxAnthropicClient:
    def test_minimax_resolves_api_key_and_base_url(self, monkeypatch):
        os.environ["MINIMAX_API_KEY"] = "test-key-global"
        captured = _capture_kwargs(monkeypatch)
        
        client = create_llm_client(provider="minimax", model="MiniMax-M2.7")
        client.get_llm()
        
        kwargs = captured["kwargs"]
        assert kwargs["model"] == "MiniMax-M2.7"
        assert kwargs["base_url"] == "https://api.minimax.io/anthropic"
        assert kwargs["api_key"] == "test-key-global"

    def test_minimax_cn_resolves_api_key_and_base_url(self, monkeypatch):
        os.environ["MINIMAX_CN_API_KEY"] = "test-key-cn"
        captured = _capture_kwargs(monkeypatch)
        
        client = create_llm_client(provider="minimax-cn", model="MiniMax-M2.7")
        client.get_llm()
        
        kwargs = captured["kwargs"]
        assert kwargs["model"] == "MiniMax-M2.7"
        assert kwargs["base_url"] == "https://api.minimaxi.com/anthropic"
        assert kwargs["api_key"] == "test-key-cn"

    def test_minimax_custom_base_url(self, monkeypatch):
        os.environ["MINIMAX_API_KEY"] = "test-key-global"
        captured = _capture_kwargs(monkeypatch)
        
        client = create_llm_client(
            provider="minimax",
            model="MiniMax-M2.7",
            base_url="https://custom.minimax.io/anthropic"
        )
        client.get_llm()
        
        kwargs = captured["kwargs"]
        assert kwargs["base_url"] == "https://custom.minimax.io/anthropic"

    def test_minimax_converts_v1_base_url_to_anthropic(self, monkeypatch):
        os.environ["MINIMAX_API_KEY"] = "test-key-global"
        captured = _capture_kwargs(monkeypatch)
        
        client = create_llm_client(
            provider="minimax",
            model="MiniMax-M2.7",
            base_url="https://api.minimax.io/v1"
        )
        client.get_llm()
        
        kwargs = captured["kwargs"]
        assert kwargs["base_url"] == "https://api.minimax.io/anthropic"

    def test_minimax_missing_key_raises_value_error(self, monkeypatch):
        if "MINIMAX_API_KEY" in os.environ:
            del os.environ["MINIMAX_API_KEY"]
        monkeypatch.setattr(mod, "load_dotenv", lambda *args, **kwargs: None)
            
        client = create_llm_client(provider="minimax", model="MiniMax-M2.7")
        with pytest.raises(ValueError, match="API key for provider 'minimax' is not set"):
            client.get_llm()

    def test_minimax_forwards_passthrough_kwargs(self, monkeypatch):
        os.environ["MINIMAX_API_KEY"] = "test-key-global"
        captured = _capture_kwargs(monkeypatch)
        
        client = create_llm_client(
            provider="minimax",
            model="MiniMax-M2.7",
            max_tokens=1024,
            timeout=30,
        )
        client.get_llm()
        
        kwargs = captured["kwargs"]
        assert kwargs["max_tokens"] == 1024
        assert kwargs["timeout"] == 30
