"""Tests for model name validation across providers."""

from tradingagents.llm_clients.validators import validate_model, VALID_MODELS


class TestValidateModel:
    def test_ollama_any_model(self):
        assert validate_model("ollama", "any-model") is True
        assert validate_model("ollama", "llama3:latest") is True
        assert validate_model("ollama", "") is True

    def test_openrouter_any_model(self):
        assert validate_model("openrouter", "any-model") is True
        assert validate_model("openrouter", "unknown-provider/model") is True

    def test_unknown_provider_any_model(self):
        assert validate_model("unknown-provider", "any-model") is True

    def test_openai_valid_model(self):
        assert validate_model("openai", "gpt-5.4") is True
        assert validate_model("openai", "gpt-5.4-mini") is True

    def test_openai_invalid_model(self):
        assert validate_model("openai", "nonexistent-model-xyz") is False

    def test_deepseek_valid_model(self):
        assert validate_model("deepseek", "deepseek-chat") is True
        assert validate_model("deepseek", "deepseek-reasoner") is True

    def test_deepseek_invalid_model(self):
        assert validate_model("deepseek", "gpt-4") is False

    def test_minimax_valid_model(self):
        assert validate_model("minimax", "MiniMax-M2.7") is True
        assert validate_model("minimax", "MiniMax-M2.5") is True

    def test_minimax_invalid_model(self):
        assert validate_model("minimax", "gpt-4") is False

    def test_case_insensitive_provider(self):
        assert validate_model("OPENAI", "gpt-5.4") is True
        assert validate_model("DeepSeek", "deepseek-chat") is True

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
