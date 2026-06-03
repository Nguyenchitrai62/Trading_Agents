"""Tests for model capabilities resolution for OpenAI-compatible providers."""

from tradingagents.llm_clients.capabilities import (
    get_capabilities,
    ModelCapabilities,
    _BY_ID,
    _BY_PATTERN,
)


class TestModelCapabilities:
    def test_default_capabilities(self):
        caps = ModelCapabilities(
            supports_tool_choice=True,
            supports_json_mode=True,
            supports_json_schema=True,
            preferred_structured_method="function_calling",
        )
        assert caps.supports_tool_choice is True
        assert caps.requires_reasoning_content_roundtrip is False
        assert caps.requires_reasoning_split is False


class TestGetCapabilities:
    def test_unknown_model_returns_default(self):
        caps = get_capabilities("random-model-123")
        assert caps.supports_tool_choice is True
        assert caps.supports_json_mode is True
        assert caps.supports_json_schema is True
        assert caps.preferred_structured_method == "function_calling"

    def test_deepseek_chat(self):
        caps = get_capabilities("deepseek-chat")
        assert caps.supports_tool_choice is True
        assert caps.requires_reasoning_content_roundtrip is False

    def test_deepseek_reasoner(self):
        caps = get_capabilities("deepseek-reasoner")
        assert caps.supports_tool_choice is False
        assert caps.requires_reasoning_content_roundtrip is True
        assert caps.preferred_structured_method == "function_calling"

    def test_deepseek_v4_flash(self):
        caps = get_capabilities("deepseek-v4-flash")
        assert caps.supports_tool_choice is False
        assert caps.requires_reasoning_content_roundtrip is True

    def test_deepseek_v4_pro(self):
        caps = get_capabilities("deepseek-v4-pro")
        assert caps.supports_tool_choice is False

    def test_minimax_m2_7(self):
        caps = get_capabilities("MiniMax-M2.7")
        assert caps.supports_tool_choice is False
        assert caps.supports_json_mode is False
        assert caps.supports_json_schema is False
        assert caps.requires_reasoning_split is True

    def test_minimax_m2_5(self):
        caps = get_capabilities("MiniMax-M2.5")
        assert caps.supports_tool_choice is False
        assert caps.requires_reasoning_split is True

    def test_minimax_m2_pattern_matching(self):
        caps = get_capabilities("MiniMax-M3.0")
        assert caps.supports_tool_choice is False
        assert caps.requires_reasoning_split is True

    def test_deepseek_v5_pattern_matching(self):
        caps = get_capabilities("deepseek-v5-flash")
        assert caps.supports_tool_choice is False
        assert caps.requires_reasoning_content_roundtrip is True

    def test_deepseek_reasoner_pattern_matching(self):
        caps = get_capabilities("deepseek-reasoner-v2")
        assert caps.supports_tool_choice is False
        assert caps.requires_reasoning_content_roundtrip is True

    def test_gpt_model_returns_default(self):
        caps = get_capabilities("gpt-5.4")
        assert caps.supports_tool_choice is True
        assert caps.supports_json_schema is True

    def test_claude_model_returns_default(self):
        caps = get_capabilities("claude-sonnet-4-5")
        assert caps.supports_tool_choice is True


class TestCapabilityStorage:
    def test_exact_id_matches(self):
        for model_id in _BY_ID:
            caps = get_capabilities(model_id)
            assert isinstance(caps, ModelCapabilities)
            assert caps == _BY_ID[model_id]

    def test_pattern_matches(self):
        for pattern, expected in _BY_PATTERN:
            test_name = pattern.pattern.replace("^", "").replace(r"\d", "9")
            caps = get_capabilities(test_name)
            assert caps.supports_tool_choice == expected.supports_tool_choice

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
