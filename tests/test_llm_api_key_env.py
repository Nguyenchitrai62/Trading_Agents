"""Tests for API key env var resolution across LLM providers."""

from tradingagents.llm_clients.api_key_env import get_api_key_env, PROVIDER_API_KEY_ENV


class TestGetApiKeyEnv:
    def test_openai(self):
        assert get_api_key_env("openai") == "OPENAI_API_KEY"

    def test_anthropic(self):
        assert get_api_key_env("anthropic") == "ANTHROPIC_API_KEY"

    def test_google(self):
        assert get_api_key_env("google") == "GOOGLE_API_KEY"

    def test_azure(self):
        assert get_api_key_env("azure") == "AZURE_OPENAI_API_KEY"

    def test_xai(self):
        assert get_api_key_env("xai") == "XAI_API_KEY"

    def test_deepseek(self):
        assert get_api_key_env("deepseek") == "DEEPSEEK_API_KEY"

    def test_qwen(self):
        assert get_api_key_env("qwen") == "DASHSCOPE_API_KEY"

    def test_qwen_cn(self):
        assert get_api_key_env("qwen-cn") == "DASHSCOPE_CN_API_KEY"

    def test_glm(self):
        assert get_api_key_env("glm") == "ZHIPU_API_KEY"

    def test_glm_cn(self):
        assert get_api_key_env("glm-cn") == "ZHIPU_CN_API_KEY"

    def test_minimax(self):
        assert get_api_key_env("minimax") == "MINIMAX_API_KEY"

    def test_minimax_cn(self):
        assert get_api_key_env("minimax-cn") == "MINIMAX_CN_API_KEY"

    def test_openrouter(self):
        assert get_api_key_env("openrouter") == "OPENROUTER_API_KEY"

    def test_ollama_returns_none(self):
        assert get_api_key_env("ollama") is None

    def test_unknown_provider_returns_none(self):
        assert get_api_key_env("unknown-provider") is None

    def test_case_insensitive(self):
        assert get_api_key_env("OPENAI") == "OPENAI_API_KEY"
        assert get_api_key_env("DeepSeek") == "DEEPSEEK_API_KEY"

    def test_all_providers_have_mapping(self):
        for provider in (
            "openai", "anthropic", "google", "azure",
            "xai", "deepseek",
            "qwen", "qwen-cn",
            "glm", "glm-cn",
            "minimax", "minimax-cn",
            "openrouter", "ollama",
        ):
            assert provider in PROVIDER_API_KEY_ENV, f"Missing mapping for: {provider}"

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
