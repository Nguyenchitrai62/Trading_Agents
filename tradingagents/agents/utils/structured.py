"""Shared helpers for extraction calls with structured output.

Agent-facing reasoning remains prose-first. These helpers are used by the
downstream extractor calls that convert prose handoffs into typed Pydantic
payloads for DB/FE usage. If a provider cannot bind structured output, callers
can skip extraction or fall back to free text without blocking the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel

from tradingagents.llm_clients.base_client import normalize_content
from tradingagents.llm_clients.minimax_mcp import MiniMaxMCPChatModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _normalize_response_content(response: Any) -> str:
    normalized = normalize_content(response)
    content = getattr(normalized, "content", "")
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content).strip()


def resolve_structured_base_llm(llm: Any) -> Any:
    """Return the underlying model that should handle structured output.

    MiniMax MCP wrappers need tool loops only for tool-using nodes. For
    non-tool nodes we unwrap to the underlying Anthropic-compatible model so
    with_structured_output remains available.
    """
    if isinstance(llm, MiniMaxMCPChatModel):
        return llm.llm
    return llm


def bind_structured(llm: Any, schema: type[T], agent_name: str) -> Optional[Any]:
    """Return ``llm.with_structured_output(schema)`` or ``None`` if unsupported.

    Logs a warning when the binding fails so the user understands the agent
    will use free-text generation for every call instead of one-shot fallback.
    """
    llm = resolve_structured_base_llm(llm)
    try:
        return llm.with_structured_output(schema)
    except (NotImplementedError, AttributeError) as exc:
        logger.warning(
            "%s: provider does not support with_structured_output (%s); "
            "falling back to free-text generation",
            agent_name, exc,
        )
        return None


def invoke_structured_or_freetext_result(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> tuple[str, Optional[T]]:
    """Run the structured call when possible and also return the parsed object.

    When structured output is unavailable or fails, falls back to plain text
    generation and returns ``None`` for the parsed model.
    """
    if structured_llm is not None:
        try:
            result = structured_llm.invoke(prompt)
            if result is not None:
                return render(result), result
        except Exception as exc:
            logger.warning(
                "%s: structured-output invocation failed (%s); retrying once as free text",
                agent_name, exc,
            )

    fallback_llm = resolve_structured_base_llm(plain_llm)
    response = fallback_llm.invoke(prompt)
    return _normalize_response_content(response), None


def invoke_structured_or_freetext(
    structured_llm: Optional[Any],
    plain_llm: Any,
    prompt: Any,
    render: Callable[[T], str],
    agent_name: str,
) -> str:
    """Run the structured call and render to markdown; fall back to free-text on any failure.

    ``prompt`` is whatever the underlying LLM accepts (a string for chat
    invocations, a list of message dicts for chat models that take that
    shape). The same value is forwarded to the free-text path so the
    fallback sees the same input the structured call did.
    """
    rendered, _ = invoke_structured_or_freetext_result(
        structured_llm,
        plain_llm,
        prompt,
        render,
        agent_name,
    )
    return rendered
