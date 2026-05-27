import os
import re
from typing import Any, Optional

from dotenv import find_dotenv, load_dotenv
from langchain_anthropic import ChatAnthropic

from .api_key_env import get_api_key_env
from .base_client import BaseLLMClient, normalize_content
from .minimax_mcp import MiniMaxMCPChatModel, resolve_minimax_mcp_settings
from .validators import validate_model

_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "api_key", "max_tokens",
    "callbacks", "http_client", "http_async_client", "effort",
)

_MCP_KWARGS = (
    "mcp_enabled", "mcp_command", "mcp_args", "mcp_tool_names",
    "mcp_max_tool_rounds", "mcp_tool_result_char_limit",
    "mcp_call_timeout_seconds", "mcp_list_timeout_seconds",
    "mcp_reference_sources",
)

# Anthropic's extended-thinking ``effort`` parameter is accepted by Opus 4.5+
# and Sonnet 4.5+ only. Haiku (any version shipped to date) 400s with
# ``"This model does not support the effort parameter"`` (#831). Future
# ``claude-{opus,sonnet}-X-Y`` releases inherit effort support via the
# forward-compat pattern below; future Haiku stays excluded by default.
_EFFORT_EXACT = {
    "claude-mythos-preview",  # non-standard preview name; effort-capable
}
_EFFORT_PATTERN = re.compile(r"^claude-(opus|sonnet)-\d+-\d+$")


def _supports_effort(model: str) -> bool:
    """Whether Anthropic accepts the ``effort`` parameter for this model."""
    model_lc = model.lower()
    return model_lc in _EFFORT_EXACT or bool(_EFFORT_PATTERN.match(model_lc))


class NormalizedChatAnthropic(ChatAnthropic):
    """ChatAnthropic with normalized content output.

    Claude models with extended thinking or tool use return content as a
    list of typed blocks. This normalizes to string for consistent
    downstream handling.
    """

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models and Anthropic-compatible MiniMax models."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "anthropic",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatAnthropic instance."""
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}
        mcp_kwargs = {key: self.kwargs.get(key) for key in _MCP_KWARGS if key in self.kwargs}

        # Resolve base URL and API key for MiniMax / minimax-cn or standard Anthropic
        if self.provider in ("minimax", "minimax-cn"):
            # Ensure .env variables are loaded explicitly
            try:
                load_dotenv(find_dotenv(usecwd=True))
            except Exception:
                pass

            # If the user passed a base_url from CLI/config that is the OpenAI-compatible one (ending in /v1),
            # we must convert it to the Anthropic-compatible one (/anthropic).
            resolved_base_url = self.base_url
            if resolved_base_url:
                if resolved_base_url.endswith("/v1"):
                    resolved_base_url = resolved_base_url[:-3] + "/anthropic"
                elif resolved_base_url.endswith("/v1/"):
                    resolved_base_url = resolved_base_url[:-4] + "/anthropic"

            default_base_url = (
                "https://api.minimax.io/anthropic"
                if self.provider == "minimax"
                else "https://api.minimaxi.com/anthropic"
            )
            llm_kwargs["base_url"] = resolved_base_url or default_base_url
            
            api_key_env = get_api_key_env(self.provider)
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
                else:
                    raise ValueError(
                        f"API key for provider '{self.provider}' is not set. "
                        f"Please set the {api_key_env} environment variable "
                        f"(e.g. add {api_key_env}=your_key to your .env file)."
                    )
        else:
            if self.base_url:
                llm_kwargs["base_url"] = self.base_url

        for key in _PASSTHROUGH_KWARGS:
            if key not in self.kwargs:
                continue
            if key == "effort" and not _supports_effort(self.model):
                continue
            llm_kwargs[key] = self.kwargs[key]

        llm = NormalizedChatAnthropic(**llm_kwargs)
        if self.provider in ("minimax", "minimax-cn"):
            mcp_settings = resolve_minimax_mcp_settings(
                provider=self.provider,
                base_url=llm_kwargs.get("base_url"),
                enabled=mcp_kwargs.get("mcp_enabled"),
                command=mcp_kwargs.get("mcp_command"),
                args=mcp_kwargs.get("mcp_args"),
                tool_names=mcp_kwargs.get("mcp_tool_names"),
                max_tool_rounds=mcp_kwargs.get("mcp_max_tool_rounds"),
                result_char_limit=mcp_kwargs.get("mcp_tool_result_char_limit"),
                call_timeout_seconds=mcp_kwargs.get("mcp_call_timeout_seconds"),
                list_timeout_seconds=mcp_kwargs.get("mcp_list_timeout_seconds"),
            )
            return MiniMaxMCPChatModel(
                llm,
                settings=mcp_settings,
                reference_sources=mcp_kwargs.get("mcp_reference_sources"),
            )

        return llm

    def validate_model(self) -> bool:
        """Validate model for Anthropic/MiniMax."""
        return validate_model(self.provider, self.model)
