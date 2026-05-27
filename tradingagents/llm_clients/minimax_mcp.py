from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import threading
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import convert_to_messages
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import Field

from .base_client import normalize_content

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:  # pragma: no cover - handled as a runtime warning
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None


logger = logging.getLogger(__name__)

_DEFAULT_MCP_COMMAND = "uvx"
_DEFAULT_MCP_ARGS = "minimax-coding-plan-mcp -y"
_DEFAULT_MCP_TOOL_NAMES = "web_search,understand_image"
_DEFAULT_MCP_MAX_TOOL_ROUNDS = 4
_DEFAULT_MCP_RESULT_CHAR_LIMIT = 4000
_MCP_TOOL_ALIASES: dict[str, tuple[str, ...]] = {
    "web_search": ("websearch", "web-search", "webSearch"),
    "understand_image": ("understandimage", "understand-image", "understandImage"),
}
_MCP_TOOL_ALIAS_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in _MCP_TOOL_ALIASES.items()
    for alias in aliases
}
_TOOL_SPEC_CACHE: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
_CACHE_LOCK = threading.RLock()


@dataclass(frozen=True)
class MiniMaxMCPSettings:
    enabled: bool
    command: str
    args: tuple[str, ...]
    tool_names: tuple[str, ...]
    api_key: str
    api_host: str
    max_tool_rounds: int = _DEFAULT_MCP_MAX_TOOL_ROUNDS
    result_char_limit: int = _DEFAULT_MCP_RESULT_CHAR_LIMIT
    call_timeout_seconds: float = 90.0
    list_timeout_seconds: float = 45.0

    def cache_key(self) -> tuple[Any, ...]:
        return (
            self.enabled,
            self.command,
            self.args,
            self.tool_names,
            self.api_host,
        )


@dataclass(frozen=True)
class MiniMaxMCPMessageLoopResult:
    response: Any
    tool_events: tuple[dict[str, Any], ...] = ()


class MiniMaxMCPTool(BaseTool):
    mcp_settings: MiniMaxMCPSettings = Field(exclude=True)

    def _run(self, **kwargs: Any) -> str:
        kwargs.pop("run_manager", None)
        kwargs.pop("config", None)
        return call_mcp_tool_sync(self.mcp_settings, self.name, kwargs)

    async def _arun(self, **kwargs: Any) -> str:
        kwargs.pop("run_manager", None)
        kwargs.pop("config", None)
        return await call_mcp_tool_async(self.mcp_settings, self.name, kwargs)


class MiniMaxMCPBoundRunnable(Runnable[Any, Any]):
    def __init__(self, runnable: Runnable[Any, Any], instruction: str):
        self.runnable = runnable
        self.instruction = instruction

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        response = self.runnable.invoke(
            add_system_instruction(input, self.instruction),
            config=config,
            **kwargs,
        )
        return normalize_content(response)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        response = await self.runnable.ainvoke(
            add_system_instruction(input, self.instruction),
            config=config,
            **kwargs,
        )
        return normalize_content(response)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.runnable, name)


class MiniMaxMCPChatModel(Runnable[Any, Any]):
    def __init__(
        self,
        llm: Any,
        settings: MiniMaxMCPSettings,
        reference_sources: Sequence[Any] | None = None,
    ):
        self.llm = llm
        self.settings = settings
        self.instruction = build_mcp_reference_sources_instruction(reference_sources)

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return self._invoke_with_mcp_loop(input, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return await asyncio.to_thread(self._invoke_with_mcp_loop, input, config, **kwargs)

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> Runnable[Any, Any]:
        combined_tools = merge_tools_by_name(tools, get_minimax_mcp_langchain_tools(self.settings))
        bound = self.llm.bind_tools(combined_tools, **kwargs)
        return MiniMaxMCPBoundRunnable(bound, self.instruction)

    def with_structured_output(self, *args: Any, **kwargs: Any) -> Any:
        if self.settings.enabled:
            raise NotImplementedError(
                "MiniMax MCP tool access is enabled; using free-text invocation so "
                "web_search and understand_image remain available."
            )
        return self.llm.with_structured_output(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.llm, name)

    def _invoke_with_mcp_loop(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        messages = add_system_instruction(input, self.instruction)
        mcp_tools = get_minimax_mcp_langchain_tools(self.settings)
        if not mcp_tools:
            return normalize_content(self.llm.invoke(messages, config=config, **kwargs))

        bound = self.llm.bind_tools(mcp_tools)
        response: AIMessage | None = None
        for _ in range(max(1, self.settings.max_tool_rounds)):
            response = bound.invoke(messages, config=config, **kwargs)
            tool_calls = [
                tool_call for tool_call in (getattr(response, "tool_calls", None) or [])
                if tool_call.get("name") in {tool.name for tool in mcp_tools}
            ]
            if not tool_calls:
                return normalize_content(response)

            messages.append(response)
            for tool_call in tool_calls:
                tool_name = str(tool_call.get("name") or "")
                tool_args = tool_call.get("args") or {}
                tool_call_id = str(tool_call.get("id") or tool_name)
                try:
                    content = call_mcp_tool_sync(self.settings, tool_name, tool_args)
                except Exception as exc:  # pragma: no cover - external MCP failure path
                    logger.warning("MiniMax MCP tool %s failed: %s", tool_name, exc)
                    content = f"MiniMax MCP tool {tool_name} failed: {exc}"
                messages.append(
                    ToolMessage(content=content, name=tool_name, tool_call_id=tool_call_id)
                )

        messages.append(
            HumanMessage(
                content=(
                    "MCP tool round limit reached. Produce the best final answer "
                    "from the evidence already gathered and state any remaining uncertainty."
                )
            )
        )
        return normalize_content(self.llm.invoke(messages, config=config, **kwargs))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r; using %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float for %s=%r; using %s", name, raw, default)
        return default


def _split_args(raw: str | Sequence[str] | None) -> tuple[str, ...]:
    if raw is None:
        return tuple(shlex.split(_DEFAULT_MCP_ARGS, posix=os.name != "nt"))
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return ()
        if "," in value and " " not in value:
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return tuple(shlex.split(value, posix=os.name != "nt"))
    return tuple(str(part) for part in raw if str(part).strip())


def _split_tool_names(raw: str | Sequence[str] | None) -> tuple[str, ...]:
    if raw is None:
        raw = _DEFAULT_MCP_TOOL_NAMES
    if isinstance(raw, str):
        names = [part.strip() for part in raw.replace(";", ",").split(",")]
    else:
        names = [str(part).strip() for part in raw]
    return tuple(name for name in names if name)


def _derive_api_host(provider: str, base_url: str | None) -> str:
    explicit_host = os.getenv("MINIMAX_API_HOST", "").strip()
    if explicit_host:
        return explicit_host.rstrip("/")

    candidate = (base_url or os.getenv("MINIMAX_BASE_URL", "")).strip().rstrip("/")
    for suffix in ("/anthropic", "/v1"):
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)]
            break
    if candidate:
        return candidate
    return "https://api.minimaxi.com" if provider == "minimax-cn" else "https://api.minimax.io"


def _resolve_api_key(provider: str) -> str:
    if provider == "minimax-cn":
        return os.getenv("MINIMAX_CN_API_KEY", "").strip() or os.getenv("MINIMAX_API_KEY", "").strip()
    return os.getenv("MINIMAX_API_KEY", "").strip() or os.getenv("MINIMAX_CN_API_KEY", "").strip()


def resolve_minimax_mcp_settings(
    *,
    provider: str = "minimax",
    base_url: str | None = None,
    enabled: bool | None = None,
    command: str | None = None,
    args: str | Sequence[str] | None = None,
    tool_names: str | Sequence[str] | None = None,
    max_tool_rounds: int | None = None,
    result_char_limit: int | None = None,
    call_timeout_seconds: float | None = None,
    list_timeout_seconds: float | None = None,
) -> MiniMaxMCPSettings:
    try:
        load_dotenv(find_dotenv(usecwd=True))
    except Exception:
        pass

    provider = provider.lower()
    return MiniMaxMCPSettings(
        enabled=_env_bool("MINIMAX_MCP_ENABLED", True) if enabled is None else bool(enabled),
        command=(command or os.getenv("MINIMAX_MCP_COMMAND", _DEFAULT_MCP_COMMAND)).strip() or _DEFAULT_MCP_COMMAND,
        args=_split_args(args if args is not None else os.getenv("MINIMAX_MCP_ARGS", _DEFAULT_MCP_ARGS)),
        tool_names=_split_tool_names(tool_names if tool_names is not None else os.getenv("MINIMAX_MCP_TOOL_NAMES", _DEFAULT_MCP_TOOL_NAMES)),
        api_key=_resolve_api_key(provider),
        api_host=_derive_api_host(provider, base_url),
        max_tool_rounds=max(1, max_tool_rounds or _env_int("MINIMAX_MCP_MAX_TOOL_ROUNDS", _DEFAULT_MCP_MAX_TOOL_ROUNDS)),
        result_char_limit=max(1000, result_char_limit or _env_int("MINIMAX_MCP_TOOL_RESULT_CHAR_LIMIT", _DEFAULT_MCP_RESULT_CHAR_LIMIT)),
        call_timeout_seconds=max(5.0, call_timeout_seconds or _env_float("MINIMAX_MCP_CALL_TIMEOUT_SECONDS", 90.0)),
        list_timeout_seconds=max(5.0, list_timeout_seconds or _env_float("MINIMAX_MCP_LIST_TIMEOUT_SECONDS", 45.0)),
    )


def merge_tools_by_name(primary: Sequence[Any], extras: Sequence[Any]) -> list[Any]:
    merged = list(primary)
    seen = {str(getattr(tool, "name", "")) for tool in merged if getattr(tool, "name", None)}
    for tool in extras:
        name = str(getattr(tool, "name", ""))
        if name and name not in seen:
            merged.append(tool)
            seen.add(name)
    return merged


def _resolve_canonical_tool_name(tool_name: str) -> str:
    normalized_name = str(tool_name or "").strip()
    return _MCP_TOOL_ALIAS_TO_CANONICAL.get(normalized_name, normalized_name)


def _expand_tool_specs_with_aliases(specs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for spec in specs:
        canonical_name = str(spec.get("name") or "").strip()
        if not canonical_name:
            continue

        for tool_name in (canonical_name, *_MCP_TOOL_ALIASES.get(canonical_name, ())):
            if tool_name in seen_names:
                continue

            next_spec = dict(spec)
            next_spec["name"] = tool_name
            if tool_name != canonical_name:
                description = str(spec.get("description") or "").strip()
                alias_note = f"Alias for {canonical_name}. Use the same input schema and behavior."
                next_spec["description"] = f"{description} {alias_note}".strip()
            expanded.append(next_spec)
            seen_names.add(tool_name)

    return expanded


def build_mcp_reference_sources_instruction(reference_sources: Sequence[Any] | None) -> str:
    lines = _format_reference_source_lines(reference_sources)
    base = (
        "MiniMax MCP tools are available when the model needs live context: "
        "use web_search for current web evidence and understand_image for image or chart inspection. "
    )
    if not lines:
        return base + "Use them when they materially improve factual accuracy or recency."

    return (
        base
        + "Before writing any final market-facing conclusion, you must use web_search to retrieve "
        "or cross-check each configured trusted source URL below, using the URL directly or a focused "
        "site-constrained query. If a source is unreachable, say so and continue with other credible evidence. "
        "After checking the trusted sources, you may search additional credible sources when useful.\n"
        + "Trusted sources:\n"
        + "\n".join(lines)
    )


def _format_reference_source_lines(reference_sources: Sequence[Any] | None) -> list[str]:
    if not reference_sources:
        return []
    lines: list[str] = []
    for source in reference_sources:
        if isinstance(source, dict):
            name = str(source.get("name") or source.get("url") or "Source").strip()
            url = str(source.get("url") or "").strip()
            focus = str(source.get("focus") or source.get("description") or "").strip()
        else:
            name = str(source).strip()
            url = name if name.startswith(("http://", "https://")) else ""
            focus = ""
        if not name:
            continue
        line = f"- {name}"
        if url and url != name:
            line += f" ({url})"
        if focus:
            line += f": {focus}"
        lines.append(line)
    return lines


def add_system_instruction(input: Any, instruction: str) -> list[Any]:
    if not instruction:
        return _to_messages(input)
    return [SystemMessage(content=instruction), *_to_messages(input)]


def _to_messages(input: Any) -> list[Any]:
    if isinstance(input, str):
        return [HumanMessage(content=input)]
    if hasattr(input, "to_messages"):
        return list(input.to_messages())
    try:
        return convert_to_messages(input)
    except Exception:
        return [HumanMessage(content=str(input))]


def _run_async_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[Any] = []
    error: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:  # pragma: no cover - defensive bridge
            error.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result[0] if result else None


async def _with_mcp_session(settings: MiniMaxMCPSettings):
    if ClientSession is None or StdioServerParameters is None or stdio_client is None:
        raise RuntimeError("The 'mcp' package is not installed. Install requirements.txt first.")
    if not settings.api_key:
        raise RuntimeError("MINIMAX_API_KEY or MINIMAX_CN_API_KEY is required for MiniMax MCP tools.")

    env = dict(os.environ)
    env["MINIMAX_API_KEY"] = settings.api_key
    env["MINIMAX_API_HOST"] = settings.api_host
    if os.getenv("MINIMAX_CN_API_KEY"):
        env["MINIMAX_CN_API_KEY"] = os.getenv("MINIMAX_CN_API_KEY", "")

    return stdio_client(
        StdioServerParameters(
            command=settings.command,
            args=list(settings.args),
            env=env,
        )
    )


async def _list_mcp_tool_specs(settings: MiniMaxMCPSettings) -> list[dict[str, Any]]:
    async def list_once() -> list[dict[str, Any]]:
        async with await _with_mcp_session(settings) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                allowed = set(settings.tool_names)
                specs = []
                for tool in listed.tools:
                    if allowed and tool.name not in allowed:
                        continue
                    specs.append(
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "input_schema": tool.inputSchema,
                        }
                    )
                return specs

    return await asyncio.wait_for(list_once(), timeout=settings.list_timeout_seconds)


def get_minimax_mcp_tool_specs(settings: MiniMaxMCPSettings) -> list[dict[str, Any]]:
    if not settings.enabled:
        return []
    key = settings.cache_key()
    with _CACHE_LOCK:
        if key in _TOOL_SPEC_CACHE:
            return list(_TOOL_SPEC_CACHE[key])

    try:
        specs = _run_async_sync(_list_mcp_tool_specs(settings))
    except Exception as exc:  # pragma: no cover - external MCP failure path
        logger.warning("MiniMax MCP tools are unavailable: %s", exc)
        specs = []

    with _CACHE_LOCK:
        _TOOL_SPEC_CACHE[key] = list(specs)
    return list(specs)


async def get_minimax_mcp_tool_specs_async(settings: MiniMaxMCPSettings) -> list[dict[str, Any]]:
    if not settings.enabled:
        return []
    key = settings.cache_key()
    with _CACHE_LOCK:
        if key in _TOOL_SPEC_CACHE:
            return list(_TOOL_SPEC_CACHE[key])
    try:
        specs = await _list_mcp_tool_specs(settings)
    except Exception as exc:  # pragma: no cover - external MCP failure path
        logger.warning("MiniMax MCP tools are unavailable: %s", exc)
        specs = []
    with _CACHE_LOCK:
        _TOOL_SPEC_CACHE[key] = list(specs)
    return list(specs)


def get_minimax_mcp_anthropic_tools(settings: MiniMaxMCPSettings) -> list[dict[str, Any]]:
    return [
        {
            "name": spec["name"],
            "description": spec.get("description", ""),
            "input_schema": spec.get("input_schema") or {"type": "object", "properties": {}},
        }
        for spec in _expand_tool_specs_with_aliases(get_minimax_mcp_tool_specs(settings))
    ]


async def get_minimax_mcp_anthropic_tools_async(settings: MiniMaxMCPSettings) -> list[dict[str, Any]]:
    return [
        {
            "name": spec["name"],
            "description": spec.get("description", ""),
            "input_schema": spec.get("input_schema") or {"type": "object", "properties": {}},
        }
        for spec in _expand_tool_specs_with_aliases(await get_minimax_mcp_tool_specs_async(settings))
    ]


def get_minimax_mcp_langchain_tools(settings: MiniMaxMCPSettings) -> list[MiniMaxMCPTool]:
    return [
        MiniMaxMCPTool(
            name=spec["name"],
            description=spec.get("description", ""),
            args_schema=spec.get("input_schema") or {"type": "object", "properties": {}},
            mcp_settings=settings,
        )
        for spec in _expand_tool_specs_with_aliases(get_minimax_mcp_tool_specs(settings))
    ]


async def call_mcp_tool_async(
    settings: MiniMaxMCPSettings,
    tool_name: str,
    tool_input: dict[str, Any],
) -> str:
    canonical_tool_name = _resolve_canonical_tool_name(tool_name)

    async def call_once() -> str:
        async with await _with_mcp_session(settings) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(canonical_tool_name, tool_input)
                return _stringify_mcp_result(result, settings.result_char_limit)

    return await asyncio.wait_for(call_once(), timeout=settings.call_timeout_seconds)


def call_mcp_tool_sync(
    settings: MiniMaxMCPSettings,
    tool_name: str,
    tool_input: dict[str, Any],
) -> str:
    return _run_async_sync(call_mcp_tool_async(settings, tool_name, tool_input))


def _stringify_mcp_result(result: Any, char_limit: int) -> str:
    parts: list[str] = []
    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if structured:
        parts.append(json.dumps(structured, ensure_ascii=False, default=str))

    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(str(text))
        else:
            parts.append(str(item))

    text = "\n".join(part for part in parts if part).strip()
    if not text:
        text = str(result)
    if len(text) > char_limit:
        text = text[:char_limit].rstrip() + "\n\n[MiniMax MCP result truncated]"
    return text


async def run_anthropic_mcp_message_loop(
    client: Any,
    *,
    settings: MiniMaxMCPSettings,
    model: str,
    max_tokens: int,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    temperature: float | None = None,
) -> MiniMaxMCPMessageLoopResult:
    active_messages = list(messages)
    tool_names = {tool["name"] for tool in tools}
    tool_events: list[dict[str, Any]] = []

    for _ in range(max(1, settings.max_tool_rounds)):
        request_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": active_messages,
            "tools": tools,
            "stream": False,
        }
        if temperature is not None:
            request_kwargs["temperature"] = temperature

        response = await client.messages.create(**request_kwargs)
        active_messages.append({"role": "assistant", "content": response.content})

        tool_uses = [block for block in response.content if getattr(block, "type", None) == "tool_use"]
        tool_uses = [
            tool_use
            for tool_use in tool_uses
            if getattr(tool_use, "name", "") in tool_names
            or _resolve_canonical_tool_name(getattr(tool_use, "name", "")) in tool_names
        ]
        if not tool_uses:
            return MiniMaxMCPMessageLoopResult(response=response, tool_events=tuple(tool_events))

        tool_results = []
        for tool_use in tool_uses:
            requested_tool_name = str(getattr(tool_use, "name", "") or "")
            canonical_tool_name = _resolve_canonical_tool_name(requested_tool_name)
            tool_input = tool_use.input or {}
            tool_events.append(
                {
                    "phase": "tool_use",
                    "tool": canonical_tool_name,
                    "requested_tool": requested_tool_name,
                    "input": tool_input,
                }
            )
            try:
                content = await call_mcp_tool_async(settings, requested_tool_name, tool_input)
            except Exception as exc:  # pragma: no cover - external MCP failure path
                logger.warning("MiniMax MCP tool %s failed: %s", requested_tool_name, exc)
                content = f"MiniMax MCP tool {requested_tool_name} failed: {exc}"
            tool_events.append(
                {
                    "phase": "tool_result",
                    "tool": canonical_tool_name,
                    "requested_tool": requested_tool_name,
                    "content": content,
                }
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": content,
                }
            )
        active_messages.append({"role": "user", "content": tool_results})

    active_messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "MCP tool round limit reached. Produce the best final answer from "
                        "the evidence already gathered and state any remaining uncertainty."
                    ),
                }
            ],
        }
    )
    request_kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": active_messages,
        "stream": False,
    }
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    return MiniMaxMCPMessageLoopResult(
        response=await client.messages.create(**request_kwargs),
        tool_events=tuple(tool_events),
    )


def extract_anthropic_text_and_thinking(response: Any) -> tuple[str, str]:
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for content_block in getattr(response, "content", []) or []:
        block_type = getattr(content_block, "type", None)
        if block_type == "text":
            text_parts.append(getattr(content_block, "text", "") or "")
        elif block_type == "thinking":
            thinking_parts.append(getattr(content_block, "thinking", "") or "")
    return "".join(text_parts), "".join(thinking_parts)


def should_use_mcp_tools(settings: MiniMaxMCPSettings, tools: Iterable[Any]) -> bool:
    return settings.enabled and bool(list(tools))