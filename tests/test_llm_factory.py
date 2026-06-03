"""Tests for LLM client factory: provider routing and client creation."""

import pytest

from tradingagents.llm_clients.factory import create_llm_client, _OPENAI_COMPATIBLE
from tradingagents.llm_clients.base_client import BaseLLMClient


class TestOpenaiCompatibleProviders:
    def test_all_providers_in_list(self):
        expected = {"openai", "xai", "deepseek", "qwen", "qwen-cn", "glm", "glm-cn", "ollama", "openrouter"}
        assert set(_OPENAI_COMPATIBLE) == expected


class TestCreateLLMClient:
    def test_openai_provider(self):
        client = create_llm_client("openai", "gpt-4")
        assert isinstance(client, BaseLLMClient)
        assert client.model == "gpt-4"

    def test_deepseek_provider(self):
        client = create_llm_client("deepseek", "deepseek-chat")
        assert isinstance(client, BaseLLMClient)
        assert client.model == "deepseek-chat"

    def test_anthropic_provider(self):
        client = create_llm_client("anthropic", "claude-sonnet-4-5")
        assert isinstance(client, BaseLLMClient)
        assert client.model == "claude-sonnet-4-5"

    def test_minimax_provider(self):
        client = create_llm_client("minimax", "MiniMax-M2.7")
        assert isinstance(client, BaseLLMClient)
        assert client.model == "MiniMax-M2.7"

    def test_minimax_cn_provider(self):
        client = create_llm_client("minimax-cn", "MiniMax-M2.5")
        assert isinstance(client, BaseLLMClient)
        assert client.model == "MiniMax-M2.5"

    def test_google_provider(self):
        client = create_llm_client("google", "gemini-2.5-flash")
        assert isinstance(client, BaseLLMClient)
        assert client.model == "gemini-2.5-flash"

    def test_azure_provider(self):
        client = create_llm_client("azure", "gpt-4-deployment")
        assert isinstance(client, BaseLLMClient)
        assert client.model == "gpt-4-deployment"

    def test_ollama_provider(self):
        client = create_llm_client("ollama", "qwen3:latest")
        assert isinstance(client, BaseLLMClient)

    def test_case_insensitive_provider(self):
        client = create_llm_client("OPenAI", "gpt-4")
        assert isinstance(client, BaseLLMClient)
        client2 = create_llm_client("Anthropic", "claude-sonnet-4-5")
        assert isinstance(client2, BaseLLMClient)

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            create_llm_client("unsupported", "model")

    def test_with_base_url(self):
        client = create_llm_client("openai", "gpt-4", base_url="https://custom.io/v1")
        assert client.base_url == "https://custom.io/v1"

    def test_with_extra_kwargs(self):
        client = create_llm_client("openai", "gpt-4", timeout=60)
        assert "timeout" in client.kwargs
        assert client.kwargs["timeout"] == 60

    def test_openrouter_any_model_accepted(self):
        client = create_llm_client("openrouter", "any-model")
        assert isinstance(client, BaseLLMClient)

    def test_xai_provider(self):
        client = create_llm_client("xai", "grok-4-fast-non-reasoning")
        assert isinstance(client, BaseLLMClient)

    def test_qwen_provider(self):
        client = create_llm_client("qwen", "qwen3.6-flash")
        assert isinstance(client, BaseLLMClient)

    def test_glm_provider(self):
        client = create_llm_client("glm", "glm-5-turbo")
        assert isinstance(client, BaseLLMClient)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
