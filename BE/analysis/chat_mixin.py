from __future__ import annotations

import asyncio
import contextlib
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from anthropic import AsyncAnthropic
from fastapi import HTTPException

from ..analysis_telemetry import (
    AnalysisCancelled,
    AnalysisLogStream,
    AnalysisLoggingHandler,
    AnalysisTelemetry,
)
from ..config import logger, resolve_minimax_settings, is_deepseek_model
from ..models import ChatRequest
from .constants import CHAT_WEB_SEARCH_HINT_TERMS, CHAT_IMAGE_HINT_TERMS, CHAT_URL_PATTERN

try:
    from tradingagents.agent_config import DEFAULT_CONFIG as TRADINGAGENTS_DEFAULT_CONFIG
except ModuleNotFoundError:
    TRADINGAGENTS_DEFAULT_CONFIG = {}


class AnalysisChatMixin:

    def get_minimax_client(self) -> AsyncAnthropic:
        settings = resolve_minimax_settings(self.settings)
        if not settings["configured"]:
            raise HTTPException(
                status_code=500,
                detail="Set MINIMAX_API_KEY or MINIMAX_CN_API_KEY in .env before using /api/chat.",
            )
        return AsyncAnthropic(api_key=settings["api_key"], base_url=settings["base_url"])

    @staticmethod
    def build_anthropic_chat_messages(request: ChatRequest) -> list[dict]:
        anthropic_messages: list[dict] = []
        for msg in request.messages:
            anthropic_messages.append(
                {
                    "role": msg.role,
                    "content": [{"type": "text", "text": msg.content}],
                }
            )
        return anthropic_messages

    @staticmethod
    def _normalize_chat_prompt(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip().lower())

    @staticmethod
    def get_latest_chat_user_prompt(request: ChatRequest) -> str:
        for message in reversed(request.messages):
            if message.role == "user" and message.content.strip():
                return message.content.strip()
        return ""

    @classmethod
    def _prompt_matches_any_term(cls, prompt: str, terms: tuple[str, ...]) -> bool:
        normalized_prompt = cls._normalize_chat_prompt(prompt)
        return any(term in normalized_prompt for term in terms)

    @staticmethod
    def _prompt_contains_direct_url(prompt: str) -> bool:
        return bool(CHAT_URL_PATTERN.search(prompt or ""))

    @classmethod
    def get_chat_tool_routing_flags(cls, request: ChatRequest) -> dict[str, bool]:
        latest_prompt = cls.get_latest_chat_user_prompt(request)
        contains_direct_url = cls._prompt_contains_direct_url(latest_prompt)
        needs_web_search = contains_direct_url or cls._prompt_matches_any_term(latest_prompt, CHAT_WEB_SEARCH_HINT_TERMS)
        needs_image_tool = cls._prompt_matches_any_term(latest_prompt, CHAT_IMAGE_HINT_TERMS)
        return {
            "contains_direct_url": contains_direct_url,
            "needs_web_search": needs_web_search,
            "needs_image_tool": needs_image_tool,
            "needs_tool_assistance": needs_web_search or needs_image_tool,
        }

    @classmethod
    def build_chat_system_message(cls, request: ChatRequest) -> str:
        routing = cls.get_chat_tool_routing_flags(request)
        contains_direct_url = routing["contains_direct_url"]
        needs_web_search = routing["needs_web_search"]
        needs_image_tool = routing["needs_image_tool"]

        routing_lines = [
            "You are the TradingAgents admin assistant. Answer directly, stay evidence-grounded, and use MiniMax MCP tools whenever they materially improve correctness.",
            "Tool policy: use the exact tool name web_search for current market data, recent news, source verification, web citations, URL inspection, or whenever the user explicitly asks you to search or check online.",
            "Tool policy: use understand_image for chart, screenshot, or image inspection when the user provides a usable visual input or image URL.",
            "Do not say that you cannot access external websites or links when web_search is available in this runtime. Use the tool first, then answer from the retrieved evidence.",
        ]

        if contains_direct_url:
            routing_lines.append(
                "Prompt routing hint: the latest user request includes a direct URL. You should use web_search on that exact URL or a focused site-constrained query before giving the final answer."
            )

        if needs_web_search:
            routing_lines.append(
                "Prompt routing hint: the latest user request appears to need live or externally verified information. You should use web_search before giving the final answer."
            )
        if needs_image_tool:
            routing_lines.append(
                "Prompt routing hint: the latest user request appears to need chart or image inspection. Use understand_image if a usable visual input or image URL is available; otherwise ask the user for it."
            )
        if not needs_web_search and not needs_image_tool:
            routing_lines.append(
                "Prompt routing hint: the latest user request does not obviously require outside evidence. Do not force a tool call unless it materially improves the answer."
            )

        routing_lines.append(
            "When you use tools, synthesize the evidence instead of dumping raw results, and mention the key sources or artifacts you relied on."
        )

        return "\n".join(routing_lines)

    def resolve_chat_max_tokens(self, request: ChatRequest) -> int:
        requested_max_tokens = int(getattr(request, "max_tokens", 0) or 0)
        if requested_max_tokens <= 0:
            return self.settings.analysis_llm_max_tokens
        return max(512, min(requested_max_tokens, self.settings.analysis_llm_max_tokens))

    def build_chat_tool_event_sse(self, tool_event: dict[str, object]) -> str | None:
        phase = str(tool_event.get("phase") or "").strip()
        tool_name = str(tool_event.get("tool") or tool_event.get("requested_tool") or "tool")
        requested_tool = str(tool_event.get("requested_tool") or tool_name)

        if phase == "tool_use":
            return self._sse(
                "tool_use",
                {
                    "tool": tool_name,
                    "requested_tool": requested_tool,
                    "input": tool_event.get("input") or {},
                },
            )

        if phase == "tool_result":
            content = self._trim_text(
                self.format_tool_result_for_display(tool_event.get("content") or ""),
                self.settings.analysis_trace_char_limit,
            )
            if not content:
                return None
            return self._sse(
                "tool_result",
                {
                    "tool": tool_name,
                    "requested_tool": requested_tool,
                    "content": content,
                },
            )

        return None

    async def create_mcp_chat_response(
        self,
        client: AsyncAnthropic,
        request: ChatRequest,
        system_message: str,
        anthropic_messages: list[dict],
        max_tokens: int,
        on_tool_event: Callable[[dict[str, object]], Awaitable[None]] | None = None,
    ):
        from tradingagents.llm_clients.minimax_mcp import (
            build_mcp_reference_sources_instruction,
            get_minimax_mcp_anthropic_tools_async,
            resolve_minimax_mcp_settings,
            run_anthropic_mcp_message_loop,
        )

        minimax_settings = resolve_minimax_settings(self.settings)
        mcp_settings = resolve_minimax_mcp_settings(
            provider=minimax_settings["provider"] or "minimax",
            base_url=minimax_settings["base_url"],
        )
        mcp_tools = await get_minimax_mcp_anthropic_tools_async(mcp_settings)
        if not mcp_tools:
            return None

        reference_instruction = build_mcp_reference_sources_instruction(
            TRADINGAGENTS_DEFAULT_CONFIG.get("preferred_reference_sources") or []
        )
        full_system_message = (
            f"{system_message}\n\n{reference_instruction}"
            if reference_instruction
            else system_message
        )
        return await run_anthropic_mcp_message_loop(
            client,
            settings=mcp_settings,
            model=request.model,
            max_tokens=max_tokens,
            temperature=request.temperature,
            system=full_system_message,
            messages=anthropic_messages,
            tools=mcp_tools,
            on_tool_event=on_tool_event,
        )

    @staticmethod
    def extract_chat_response_payload(response) -> tuple[str, str, int, int, int]:
        from tradingagents.llm_clients.minimax_mcp import extract_anthropic_text_and_thinking

        resolved_response = getattr(response, "response", response)
        text, thinking = extract_anthropic_text_and_thinking(resolved_response)
        usage = getattr(resolved_response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        total_tokens = input_tokens + output_tokens
        return text, thinking, input_tokens, output_tokens, total_tokens

    async def generate_chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        try:
            start_time = time.time()
            client = self.get_minimax_client()
            system_message = self.build_chat_system_message(request)
            anthropic_messages = self.build_anthropic_chat_messages(request)
            use_mcp_chat_tools = bool(self.get_chat_tool_routing_flags(request)["needs_tool_assistance"])

            chat_max_tokens = self.resolve_chat_max_tokens(request)
            if use_mcp_chat_tools:
                tool_event_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

                async def enqueue_tool_event(tool_event: dict[str, object]) -> None:
                    await tool_event_queue.put(dict(tool_event))

                yield self._sse("thinking", {"content": "Preparing tool-assisted response..."})

                mcp_task = asyncio.create_task(
                    self.create_mcp_chat_response(
                        client,
                        request,
                        system_message,
                        anthropic_messages,
                        max_tokens=chat_max_tokens,
                        on_tool_event=enqueue_tool_event,
                    )
                )
                mcp_response = None
                while True:
                    if mcp_task.done() and tool_event_queue.empty():
                        mcp_response = mcp_task.result()
                        break

                    next_tool_event = asyncio.create_task(tool_event_queue.get())
                    done, _pending = await asyncio.wait(
                        {mcp_task, next_tool_event},
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if next_tool_event in done:
                        tool_event_payload = self.build_chat_tool_event_sse(next_tool_event.result())
                        if tool_event_payload:
                            yield tool_event_payload
                    else:
                        next_tool_event.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await next_tool_event

                    if mcp_task in done and tool_event_queue.empty():
                        mcp_response = mcp_task.result()
                        break

                    await asyncio.sleep(0)

                while not tool_event_queue.empty():
                    tool_event_payload = self.build_chat_tool_event_sse(tool_event_queue.get_nowait())
                    if tool_event_payload:
                        yield tool_event_payload

                if mcp_response is not None:
                    text, thinking, _input_tokens, output_tokens, _total_tokens = self.extract_chat_response_payload(mcp_response)
                    if thinking:
                        yield self._sse("thinking", {"content": thinking})
                    if text:
                        yield self._sse("content", {"content": text})

                    end_time = time.time()
                    total_time = end_time - start_time
                    tokens = output_tokens if output_tokens > 0 else len(text) // 4
                    tokens_per_second = tokens / total_time if total_time > 0 else 0
                    yield self._sse(
                        "complete",
                        {
                            "text": text,
                            "thinking": thinking,
                            "tokens": tokens,
                            "tokens_estimated": output_tokens == 0,
                            "tokens_per_second": round(tokens_per_second, 2),
                            "generation_time": round(total_time, 2),
                            "total_time": round(total_time, 2),
                        },
                    )
                    return

            stream = await client.messages.create(
                model=request.model,
                max_tokens=chat_max_tokens,
                temperature=request.temperature,
                system=system_message,
                messages=anthropic_messages,
                stream=True,
            )

            text_buffer = ""
            thinking_buffer = ""
            first_token_time = None
            output_tokens = 0

            async for chunk in stream:
                chunk_type = getattr(chunk, "type", None)
                if chunk_type is None:
                    continue

                if chunk_type == "message_delta":
                    usage = getattr(chunk, "usage", None)
                    if usage:
                        output_tokens = getattr(usage, "output_tokens", 0) or 0

                if chunk_type == "content_block_delta":
                    if first_token_time is None:
                        first_token_time = time.time()

                    delta = getattr(chunk, "delta", None)
                    if delta is None:
                        continue

                    delta_type = getattr(delta, "type", None)
                    if delta_type is None and isinstance(delta, dict):
                        delta_type = delta.get("type")

                    if delta_type == "thinking_delta":
                        thinking = getattr(delta, "thinking", None)
                        if thinking is None and isinstance(delta, dict):
                            thinking = delta.get("thinking")
                        if thinking:
                            thinking_buffer += thinking
                            yield self._sse("thinking", {"content": thinking})

                    elif delta_type == "text_delta":
                        text = getattr(delta, "text", None)
                        if text is None and isinstance(delta, dict):
                            text = delta.get("text")
                        if text:
                            text_buffer += text
                            yield self._sse("content", {"content": text})

                elif chunk_type == "message_stop":
                    end_time = time.time()
                    total_time = end_time - start_time
                    generation_time = end_time - first_token_time if first_token_time else total_time
                    estimated_tokens = len(text_buffer) // 4
                    tokens = output_tokens if output_tokens > 0 else estimated_tokens
                    tokens_per_second = tokens / generation_time if generation_time > 0 else 0

                    yield self._sse(
                        "complete",
                        {
                            "text": text_buffer,
                            "thinking": thinking_buffer,
                            "tokens": tokens,
                            "tokens_estimated": output_tokens == 0,
                            "tokens_per_second": round(tokens_per_second, 2),
                            "generation_time": round(generation_time, 2),
                            "total_time": round(total_time, 2),
                        },
                    )
                    break

                await asyncio.sleep(0)

        except Exception as exc:
            yield self._sse("error", {"error": str(exc)})

    async def generate_non_streaming_chat(self, request: ChatRequest) -> dict:
        try:
            client = self.get_minimax_client()
            system_message = self.build_chat_system_message(request)
            anthropic_messages = self.build_anthropic_chat_messages(request)
            chat_max_tokens = self.resolve_chat_max_tokens(request)
            use_mcp_chat_tools = bool(self.get_chat_tool_routing_flags(request)["needs_tool_assistance"])

            if use_mcp_chat_tools:
                mcp_response = await self.create_mcp_chat_response(
                    client,
                    request,
                    system_message,
                    anthropic_messages,
                    max_tokens=chat_max_tokens,
                )
                if mcp_response is not None:
                    text, _thinking, input_tokens, output_tokens, total_tokens = self.extract_chat_response_payload(mcp_response)
                    return {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": text,
                                }
                            }
                        ],
                        "usage": {
                            "prompt_tokens": input_tokens,
                            "completion_tokens": output_tokens,
                            "total_tokens": total_tokens,
                        },
                    }

            response = await client.messages.create(
                model=request.model,
                max_tokens=chat_max_tokens,
                temperature=request.temperature,
                system=system_message,
                messages=anthropic_messages,
                stream=False,
            )

            text = ""
            for content_block in response.content:
                if content_block.type == "text":
                    text += content_block.text

            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": text,
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
                },
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
