from __future__ import annotations

import asyncio
import contextlib
import gc
import hashlib
import io
import json
import logging
import re
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from concurrent.futures import TimeoutError as FutureTimeoutError
from copy import deepcopy

from anthropic import AsyncAnthropic
from fastapi import HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from .config import RESEARCH_DEPTH_OPTIONS, SECTION_META, BackendSettings, logger, resolve_minimax_settings
from .history import TursoHistoryStore, build_history_sections
from .models import AnalysisRequest, ChatRequest

try:
    from tradingagents.default_config import DEFAULT_CONFIG as TRADINGAGENTS_DEFAULT_CONFIG
    from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS
    from tradingagents.graph.checkpointer import (
        checkpoint_step,
        clear_checkpoint,
        get_checkpointer,
        thread_id,
    )
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    ANALYSIS_RUNTIME_IMPORT_ERROR: ModuleNotFoundError | None = None
except ModuleNotFoundError as exc:
    TRADINGAGENTS_DEFAULT_CONFIG = {}
    ANALYST_NODE_SPECS = {}
    checkpoint_step = None
    clear_checkpoint = None
    get_checkpointer = None
    thread_id = None
    TradingAgentsGraph = None
    ANALYSIS_RUNTIME_IMPORT_ERROR = exc


def _process_rss_mb() -> int | None:
    try:
        import resource
    except ImportError:
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:
        return None
    if usage <= 0:
        return None
    if usage > 10_000_000:
        return round(usage / (1024 * 1024))
    return round(usage / 1024)


class AnalysisCancelled(Exception):
    pass


class AnalysisLogStream(io.TextIOBase):
    def __init__(self, emit_log: Callable[[str, str, str], None], phase: str, level: str):
        self.emit_log = emit_log
        self.phase = phase
        self.level = level
        self._buffer = ""

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        if not value:
            return 0
        self._buffer += value
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self.emit_log(line.strip(), self.phase, self.level)
        return len(value)

    def flush(self) -> None:
        if self._buffer.strip():
            self.emit_log(self._buffer.strip(), self.phase, self.level)
        self._buffer = ""


class AnalysisLoggingHandler(logging.Handler):
    def __init__(self, emit_log: Callable[[str, str, str], None]):
        super().__init__(level=logging.INFO)
        self.emit_log = emit_log

    def emit(self, record: logging.LogRecord) -> None:
        if record.name == logger.name:
            return
        try:
            level = "warning" if record.levelno >= logging.WARNING else "info"
            self.emit_log(self.format(record), "backend_log", level)
        except Exception:
            self.handleError(record)


STATE_UPDATE_KEYS = {
    "messages",
    "company_of_interest",
    "asset_type",
    "trade_date",
    "past_context",
    "sender",
    "investment_debate_state",
    "risk_debate_state",
    "market_report",
    "fundamentals_report",
    "sentiment_report",
    "news_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
}

CHAT_WEB_SEARCH_HINT_TERMS = (
    "latest",
    "current",
    "today",
    "recent",
    "newest",
    "live",
    "real time",
    "real-time",
    "market data",
    "price",
    "pricing",
    "quote",
    "news",
    "headline",
    "earnings",
    "filing",
    "10-k",
    "10q",
    "investor relations",
    "guidance",
    "macro",
    "cpi",
    "fomc",
    "source",
    "sources",
    "citation",
    "citations",
    "cite",
    "reference",
    "references",
    "verify",
    "verification",
    "cross-check",
    "fact-check",
    "search",
    "web",
    "internet",
    "browse",
    "lookup",
    "look up",
    "website",
    "mcp",
    "web_search",
    "moi nhat",
    "mới nhất",
    "hom nay",
    "hôm nay",
    "hien tai",
    "hiện tại",
    "thoi gian thuc",
    "thời gian thực",
    "gia",
    "giá",
    "tin tuc",
    "tin tức",
    "tim kiem",
    "tìm kiếm",
    "tra cuu",
    "tra cứu",
    "nguon",
    "nguồn",
    "tham chieu",
    "tham chiếu",
    "xac minh",
    "xác minh",
    "kiem chung",
    "kiểm chứng",
    "kiem tra",
    "kiểm tra",
)

CHAT_IMAGE_HINT_TERMS = (
    "image",
    "screenshot",
    "photo",
    "picture",
    "chart",
    "graph",
    "candlestick",
    "heatmap",
    "visual",
    "understand_image",
    "anh",
    "ảnh",
    "hinh",
    "hình",
    "bieu do",
    "biểu đồ",
    "do thi",
    "đồ thị",
)

CHAT_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)


class AnalysisService:
    def __init__(self, settings: BackendSettings, history_store: TursoHistoryStore):
        self.settings = settings
        self.history_store = history_store
        self.active_analysis_cancel_events: dict[str, threading.Event] = {}
        self.active_analysis_lock = threading.Lock()
        self.active_analysis_count = 0

    def ensure_analysis_runtime_available(self) -> None:
        if ANALYSIS_RUNTIME_IMPORT_ERROR is None:
            return
        missing_name = ANALYSIS_RUNTIME_IMPORT_ERROR.name or "analysis dependency"
        raise HTTPException(
            status_code=500,
            detail=(
                "Analysis runtime dependencies are unavailable. Install the missing package "
                f"'{missing_name}' to use /api/analyze."
            ),
        )

    @staticmethod
    def normalize_ticker_symbol(ticker: str) -> str:
        normalized = ticker.strip().upper().replace(" ", "")
        if normalized and "/" not in normalized and "-" not in normalized:
            return f"{normalized}-USDT"
        return normalized

    @staticmethod
    def filter_analysts_for_crypto(selected_analysts: list[str]) -> list[str]:
        return list(selected_analysts)

    @staticmethod
    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @staticmethod
    def _trim_text(value: str, limit: int) -> str:
        if limit <= 0 or len(value) <= limit:
            return value
        suffix = "\n\n[truncated by configured trace limit]"
        safe_limit = max(0, limit - len(suffix))
        return value[:safe_limit].rstrip() + suffix

    @staticmethod
    def _try_parse_json(value: str) -> object | None:
        text = (value or "").strip()
        if not text or text[0] not in "[{":
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @classmethod
    def _unwrap_tool_display_payload(cls, value: object) -> object:
        if isinstance(value, str):
            parsed = cls._try_parse_json(value)
            return cls._unwrap_tool_display_payload(parsed) if parsed is not None else value.strip()

        if isinstance(value, list):
            if len(value) == 1:
                return cls._unwrap_tool_display_payload(value[0])
            return [cls._unwrap_tool_display_payload(item) for item in value]

        if isinstance(value, dict):
            block_type = str(value.get("type") or "").strip().lower()
            if block_type == "text" and isinstance(value.get("text"), str):
                return cls._unwrap_tool_display_payload(value.get("text") or "")
            if set(value.keys()) == {"content"}:
                return cls._unwrap_tool_display_payload(value.get("content"))
        return value

    @staticmethod
    def _format_search_result_items(items: list[object]) -> list[str]:
        lines: list[str] = []
        for item in items:
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or item.get("query") or item.get("link") or "Untitled").strip()
                link = str(item.get("link") or item.get("url") or "").strip()
                snippet = str(item.get("snippet") or item.get("description") or item.get("summary") or "").strip()
                date = str(item.get("date") or item.get("published") or item.get("published_at") or "").strip()
            else:
                title = str(item).strip()
                link = ""
                snippet = ""
                date = ""

            if not title:
                continue

            lines.append(f"- [{title}]({link})" if link else f"- {title}")
            if date:
                lines.append(f"  Date: {date}")
            if snippet:
                lines.append(f"  {snippet}")

        return lines

    @classmethod
    def format_tool_result_for_display(cls, content: object) -> str:
        payload = cls._unwrap_tool_display_payload(content)

        if isinstance(payload, dict):
            lines: list[str] = []
            answer = str(payload.get("answer") or payload.get("summary") or "").strip()
            if answer:
                lines.append(answer)

            organic = payload.get("organic")
            if isinstance(organic, list) and organic:
                if lines:
                    lines.append("")
                lines.append("Search results:")
                lines.extend(cls._format_search_result_items(organic))

            news = payload.get("news") or payload.get("top_stories")
            if isinstance(news, list) and news:
                if lines:
                    lines.append("")
                lines.append("Related news:")
                lines.extend(cls._format_search_result_items(news))

            related_searches = payload.get("related_searches")
            if isinstance(related_searches, list) and related_searches:
                related_queries = [
                    str(item.get("query") or "").strip() if isinstance(item, dict) else str(item).strip()
                    for item in related_searches
                ]
                related_queries = [item for item in related_queries if item]
                if related_queries:
                    if lines:
                        lines.append("")
                    lines.append("Related searches: " + "; ".join(related_queries))

            if lines:
                return "\n".join(lines).strip()

            return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n```"

        if isinstance(payload, list):
            return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n```"

        return str(payload or "").strip()

    def try_reserve_analysis_slot(self) -> bool:
        with self.active_analysis_lock:
            if self.active_analysis_count >= self.settings.analysis_max_concurrent_runs:
                return False
            self.active_analysis_count += 1
            return True

    def release_analysis_slot(self) -> None:
        with self.active_analysis_lock:
            if self.active_analysis_count > 0:
                self.active_analysis_count -= 1

    def cancel_run(self, run_id: str) -> dict:
        with self.active_analysis_lock:
            cancel_event = self.active_analysis_cancel_events.get(run_id)

        if cancel_event is None:
            return {
                "cancelled": False,
                "run_id": run_id,
                "message": "No active analysis stream matched this run id.",
            }

        cancel_event.set()
        logger.info("analysis cancel requested: run_id=%s", run_id)
        return {
            "cancelled": True,
            "run_id": run_id,
            "message": "Cancellation requested for the active analysis stream.",
        }

    def build_analysis_runtime_profile(self, request: AnalysisRequest) -> dict:
        depth_config = RESEARCH_DEPTH_OPTIONS[request.research_depth]
        requested_rounds = depth_config["rounds"]
        return {
            "requested_rounds": requested_rounds,
            "effective_rounds": requested_rounds,
            "llm_max_tokens": self.settings.analysis_llm_max_tokens,
            "mcp_max_tool_rounds": depth_config["mcp_tool_rounds"],
        }

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
    def build_chat_system_message(cls, request: ChatRequest) -> str:
        latest_prompt = cls.get_latest_chat_user_prompt(request)
        contains_direct_url = cls._prompt_contains_direct_url(latest_prompt)
        needs_web_search = contains_direct_url or cls._prompt_matches_any_term(latest_prompt, CHAT_WEB_SEARCH_HINT_TERMS)
        needs_image_tool = cls._prompt_matches_any_term(latest_prompt, CHAT_IMAGE_HINT_TERMS)

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

            chat_max_tokens = self.resolve_chat_max_tokens(request)
            tool_event_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

            async def enqueue_tool_event(tool_event: dict[str, object]) -> None:
                await tool_event_queue.put(dict(tool_event))

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

    def build_analysis_config(self, request: AnalysisRequest, minimax_settings: dict, runtime_profile: dict) -> dict:
        config = deepcopy(TRADINGAGENTS_DEFAULT_CONFIG)
        config.update(
            {
                "llm_provider": minimax_settings["provider"],
                "quick_think_llm": request.model,
                "deep_think_llm": request.model,
                "backend_url": minimax_settings["base_url"],
                "output_language": request.output_language,
                "max_debate_rounds": runtime_profile["effective_rounds"],
                "max_risk_discuss_rounds": runtime_profile["effective_rounds"],
                "global_news_lookback_days": request.lookback_days,
                "crypto_market_lookback_days": request.lookback_days,
                "analysis_llm_max_tokens": runtime_profile["llm_max_tokens"],
                "minimax_mcp_max_tool_rounds": runtime_profile["mcp_max_tool_rounds"],
                "checkpoint_enabled": request.checkpoint_enabled,
                "memory_log_path": None,
                "persist_analysis_artifacts": False,
            }
        )
        return config

    @staticmethod
    def extract_runtime_snapshot(state: dict) -> dict:
        investment_state = state.get("investment_debate_state") or {}
        risk_state = state.get("risk_debate_state") or {}
        return {
            "sections": {key: (state.get(key) or "") for key in SECTION_META},
            "investment": {
                "history": investment_state.get("history", "") or "",
                "bull_history": investment_state.get("bull_history", "") or "",
                "bear_history": investment_state.get("bear_history", "") or "",
                "current_response": investment_state.get("current_response", "") or "",
                "judge_decision": investment_state.get("judge_decision", "") or "",
                "count": investment_state.get("count", 0) or 0,
            },
            "risk": {
                "history": risk_state.get("history", "") or "",
                "aggressive_history": risk_state.get("aggressive_history", "") or "",
                "conservative_history": risk_state.get("conservative_history", "") or "",
                "neutral_history": risk_state.get("neutral_history", "") or "",
                "current_aggressive_response": risk_state.get("current_aggressive_response", "") or "",
                "current_conservative_response": risk_state.get("current_conservative_response", "") or "",
                "current_neutral_response": risk_state.get("current_neutral_response", "") or "",
                "judge_decision": risk_state.get("judge_decision", "") or "",
                "count": risk_state.get("count", 0) or 0,
            },
        }

    @staticmethod
    def _normalize_message_content(content: object) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("content") or block.get("thinking")
                    if text:
                        parts.append(str(text).strip())
                elif block:
                    parts.append(str(block).strip())
            return "\n".join(part for part in parts if part).strip()
        if content is None:
            return ""
        return str(content).strip()

    @staticmethod
    def _tool_call_summary(tool_call: dict) -> str:
        name = str(tool_call.get("name") or "tool")
        args = tool_call.get("args") or {}
        if not args:
            return name
        if isinstance(args, dict):
            items = ", ".join(f"{key}={value}" for key, value in list(args.items())[:4])
            return f"{name}({items})"
        return f"{name}({args})"

    @classmethod
    def _build_message_signature(cls, message: object) -> str:
        raw_signature = ""
        if hasattr(message, "id") and getattr(message, "id"):
            raw_signature = str(getattr(message, "id"))
        else:
            raw_signature = json.dumps(
                {
                    "type": message.__class__.__name__,
                    "name": getattr(message, "name", ""),
                    "content": cls._normalize_message_content(getattr(message, "content", "")),
                    "tool_calls": getattr(message, "tool_calls", []),
                    "tool_call_id": getattr(message, "tool_call_id", ""),
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
        return hashlib.sha1(raw_signature.encode("utf-8", errors="ignore")).hexdigest()

    def emit_message_progress_updates(
        self,
        messages: list[object],
        current_agent: str | None,
        seen_signatures: set[str],
        emit: Callable[[str, dict], None],
    ) -> None:
        for message in messages:
            signature = self._build_message_signature(message)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)

            if isinstance(message, HumanMessage):
                continue

            if isinstance(message, ToolMessage):
                tool_name = getattr(message, "name", None) or getattr(message, "tool_call_id", None) or "tool"
                content = self._trim_text(
                    self.format_tool_result_for_display(getattr(message, "content", "")),
                    self.settings.analysis_trace_char_limit,
                )
                if not content:
                    continue
                emit(
                    "agent_trace",
                    {
                        "agent": current_agent or "Tool Runner",
                        "phase": "tool_result",
                        "title": str(tool_name),
                        "content": content,
                    },
                )
                continue

            if isinstance(message, AIMessage):
                tool_calls = getattr(message, "tool_calls", []) or []
                if tool_calls:
                    emit(
                        "agent_trace",
                        {
                            "agent": current_agent or "Analyst",
                            "phase": "tool_call",
                            "title": current_agent or "Tool call",
                            "content": "\n".join(self._tool_call_summary(tool_call) for tool_call in tool_calls),
                        },
                    )
                content = self._trim_text(
                    self._normalize_message_content(getattr(message, "content", "")),
                    self.settings.analysis_trace_char_limit,
                )
                if content:
                    emit(
                        "agent_trace",
                        {
                            "agent": current_agent or "Analyst",
                            "phase": "analysis",
                            "title": current_agent or "Analysis",
                            "content": content,
                        },
                    )

    @staticmethod
    def detect_current_agent(previous: dict, current: dict) -> str | None:
        previous_sections = previous.get("sections", {})
        current_sections = current.get("sections", {})
        for key, meta in SECTION_META.items():
            if current_sections.get(key) and current_sections.get(key) != previous_sections.get(key):
                return meta["agent"]

        previous_investment = previous.get("investment", {})
        current_investment = current.get("investment", {})
        if current_investment.get("current_response") and current_investment.get("current_response") != previous_investment.get("current_response"):
            response = current_investment.get("current_response", "")
            if response.startswith("Bull Analyst:"):
                return "Bull Researcher"
            if response.startswith("Bear Analyst:"):
                return "Bear Researcher"
            return "Research Team"

        previous_risk = previous.get("risk", {})
        current_risk = current.get("risk", {})
        risk_fields = [
            ("current_aggressive_response", "Aggressive Analyst"),
            ("current_conservative_response", "Conservative Analyst"),
            ("current_neutral_response", "Neutral Analyst"),
        ]
        for field_name, label in risk_fields:
            if current_risk.get(field_name) and current_risk.get(field_name) != previous_risk.get(field_name):
                return label

        return None

    @staticmethod
    def build_changed_fields(previous: dict, current: dict) -> dict:
        return {key: value for key, value in current.items() if value != previous.get(key)}

    @staticmethod
    def build_changed_sections(previous: dict, current: dict) -> dict:
        return {key: value for key, value in current.items() if value and value != previous.get(key)}

    @staticmethod
    def iter_graph_state_updates(chunk: dict) -> list[tuple[str | None, dict]]:
        if not isinstance(chunk, dict):
            return []
        if any(key in STATE_UPDATE_KEYS for key in chunk):
            return [(None, chunk)]
        updates: list[tuple[str | None, dict]] = []
        for node_name, update in chunk.items():
            if isinstance(update, dict):
                updates.append((str(node_name), update))
        return updates

    @staticmethod
    def merge_graph_state_update(state: dict, update: dict) -> list[str]:
        changed_keys: list[str] = []
        for key, value in update.items():
            if key == "messages":
                state["messages"] = [
                    message for message in (value or []) if not isinstance(message, RemoveMessage)
                ]
            elif isinstance(value, dict) and isinstance(state.get(key), dict):
                merged = dict(state[key])
                merged.update(value)
                state[key] = merged
            else:
                state[key] = value
            changed_keys.append(key)
        return sorted(set(changed_keys))

    def build_status_snapshot(self, snapshot: dict, selected_analysts: list[str], current_agent: str | None) -> dict:
        selected_specs = [ANALYST_NODE_SPECS[key] for key in selected_analysts]
        sections = snapshot["sections"]
        analysts = []
        first_incomplete = True
        for spec in selected_specs:
            has_report = bool(sections.get(spec.report_key))
            if has_report:
                status = "completed"
            elif first_incomplete and not sections.get("investment_plan"):
                status = "in_progress"
                first_incomplete = False
            else:
                status = "pending"
            analysts.append({"key": spec.key, "label": spec.agent_node, "status": status})

        analyst_reports_complete = all(bool(sections.get(spec.report_key)) for spec in selected_specs)

        investment = snapshot["investment"]
        research = [
            {
                "key": "bull",
                "label": "Bull Researcher",
                "status": "completed"
                if investment["bull_history"]
                else "in_progress"
                if analyst_reports_complete and not sections.get("investment_plan")
                else "pending",
            },
            {
                "key": "bear",
                "label": "Bear Researcher",
                "status": "completed"
                if investment["bear_history"]
                else "in_progress"
                if investment["bull_history"] and not sections.get("investment_plan")
                else "pending",
            },
            {
                "key": "manager",
                "label": "Research Manager",
                "status": "completed"
                if sections.get("investment_plan")
                else "in_progress"
                if investment["history"]
                else "pending",
            },
        ]

        trader = [
            {
                "key": "trader",
                "label": "Trader",
                "status": "completed"
                if sections.get("trader_investment_plan")
                else "in_progress"
                if sections.get("investment_plan")
                else "pending",
            }
        ]

        risk = snapshot["risk"]
        risk_items = [
            {
                "key": "aggressive",
                "label": "Aggressive Analyst",
                "status": "completed"
                if risk["current_aggressive_response"]
                else "in_progress"
                if sections.get("trader_investment_plan") and not sections.get("final_trade_decision")
                else "pending",
            },
            {
                "key": "conservative",
                "label": "Conservative Analyst",
                "status": "completed"
                if risk["current_conservative_response"]
                else "in_progress"
                if risk["current_aggressive_response"] and not sections.get("final_trade_decision")
                else "pending",
            },
            {
                "key": "neutral",
                "label": "Neutral Analyst",
                "status": "completed"
                if risk["current_neutral_response"]
                else "in_progress"
                if risk["current_conservative_response"] and not sections.get("final_trade_decision")
                else "pending",
            },
        ]

        portfolio = [
            {
                "key": "portfolio_manager",
                "label": "Portfolio Manager",
                "status": "completed"
                if sections.get("final_trade_decision")
                else "in_progress"
                if risk["history"]
                else "pending",
            }
        ]

        for group in (analysts, research, trader, risk_items, portfolio):
            for item in group:
                if current_agent and item["label"] == current_agent and item["status"] == "pending":
                    item["status"] = "in_progress"

        total_sections = len(selected_specs) + 3
        completed_sections = sum(bool(sections.get(spec.report_key)) for spec in selected_specs)
        completed_sections += int(bool(sections.get("investment_plan")))
        completed_sections += int(bool(sections.get("trader_investment_plan")))
        completed_sections += int(bool(sections.get("final_trade_decision")))

        if sections.get("final_trade_decision"):
            phase = "portfolio"
        elif risk["history"] or sections.get("trader_investment_plan"):
            phase = "risk"
        elif sections.get("investment_plan"):
            phase = "trading"
        elif investment["history"] or analyst_reports_complete:
            phase = "research"
        elif any(bool(sections.get(spec.report_key)) for spec in selected_specs):
            phase = "analysts"
        else:
            phase = "booting"

        return {
            "current_agent": current_agent,
            "phase": phase,
            "progress": {
                "completed": completed_sections,
                "total": total_sections,
                "percent": round((completed_sections / total_sections) * 100, 1) if total_sections else 0,
            },
            "groups": {
                "analysts": analysts,
                "research": research,
                "trading": trader,
                "risk": risk_items,
                "portfolio": portfolio,
            },
        }

    def emit_snapshot_updates(self, previous: dict, current: dict, emit: Callable[[str, dict], None]) -> None:
        previous_sections = previous.get("sections", {})
        current_sections = current.get("sections", {})
        for key, meta in SECTION_META.items():
            content = current_sections.get(key, "")
            if content and content != previous_sections.get(key):
                emit(
                    "section_update",
                    {
                        "section": key,
                        "title": meta["title"],
                        "agent": meta["agent"],
                        "team": meta["team"],
                        "content": content,
                    },
                )

        previous_investment = previous.get("investment", {})
        current_investment = current.get("investment", {})
        if current_investment.get("current_response") and current_investment.get("current_response") != previous_investment.get("current_response"):
            speaker = "Research Team"
            if current_investment["current_response"].startswith("Bull Analyst:"):
                speaker = "Bull Researcher"
            if current_investment["current_response"].startswith("Bear Analyst:"):
                speaker = "Bear Researcher"
            emit(
                "debate_update",
                {
                    "team": "research",
                    "speaker": speaker,
                    "content": current_investment["current_response"],
                    "patch": self.build_changed_fields(previous_investment, current_investment),
                },
            )

        previous_risk = previous.get("risk", {})
        current_risk = current.get("risk", {})
        risk_speakers = {
            "current_aggressive_response": "Aggressive Analyst",
            "current_conservative_response": "Conservative Analyst",
            "current_neutral_response": "Neutral Analyst",
        }
        for field_name, speaker in risk_speakers.items():
            if current_risk.get(field_name) and current_risk.get(field_name) != previous_risk.get(field_name):
                emit(
                    "debate_update",
                    {
                        "team": "risk",
                        "speaker": speaker,
                        "content": current_risk[field_name],
                        "patch": self.build_changed_fields(previous_risk, current_risk),
                    },
                )

    def run_trading_analysis(
        self,
        request: AnalysisRequest,
        emit: Callable[[str, dict], None],
        user: dict,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self.ensure_analysis_runtime_available()
        minimax_settings = resolve_minimax_settings(self.settings)
        if not minimax_settings["configured"]:
            raise HTTPException(
                status_code=500,
                detail="Set MINIMAX_API_KEY or MINIMAX_CN_API_KEY in .env before running analysis.",
            )

        cancel_event = cancel_event or threading.Event()
        run_started_at = time.time()
        symbol = self.normalize_ticker_symbol(request.symbol)
        runtime_profile = self.build_analysis_runtime_profile(request)

        def emit_analysis_log(
            message: str,
            phase: str = "backend",
            level: str = "info",
            write_logger: bool = True,
            **extra: object,
        ) -> None:
            payload = {
                "level": level,
                "phase": phase,
                "message": message,
                "elapsed_seconds": round(time.time() - run_started_at, 2),
                **extra,
            }
            rss_mb = _process_rss_mb()
            if rss_mb is not None:
                payload["rss_mb"] = rss_mb
            extra_json = json.dumps(extra, ensure_ascii=False, default=str) if extra else "{}"
            payload["log_line"] = (
                f"analysis symbol={symbol} phase={phase} elapsed={payload['elapsed_seconds']}s "
                f"message={message} extra={extra_json}"
            )
            if write_logger:
                log_method = logger.warning if level == "warning" else logger.info
                log_method(
                    "analysis symbol=%s phase=%s elapsed=%ss message=%s extra=%s",
                    symbol,
                    phase,
                    payload["elapsed_seconds"],
                    message,
                    extra,
                )
            emit("analysis_log", payload)

        def ensure_not_cancelled() -> None:
            if cancel_event.is_set():
                emit_analysis_log("Analysis cancellation requested; stopping active graph run.", "cancelled", "warning")
                raise AnalysisCancelled()

        graph = None
        asset_type = self.settings.default_asset_type
        filtered_analysts = self.filter_analysts_for_crypto(request.selected_analysts)
        if not filtered_analysts:
            raise HTTPException(status_code=400, detail="No valid analysts remain for crypto analysis.")

        emit_analysis_log(
            "Request validated and runtime options resolved.",
            "prepare",
            requested_asset_type=request.asset_type,
            resolved_asset_type=asset_type,
            selected_analysts=filtered_analysts,
            lookback_days=request.lookback_days,
            research_depth=request.research_depth,
            effective_depth_rounds=runtime_profile["effective_rounds"],
            mcp_max_tool_rounds=runtime_profile["mcp_max_tool_rounds"],
            llm_max_tokens=runtime_profile["llm_max_tokens"],
            resource_constrained=self.settings.resource_constrained_mode,
            output_language=request.output_language,
        )

        if filtered_analysts != request.selected_analysts:
            emit_analysis_log(
                "Fundamentals Analyst disabled for crypto analysis.",
                "prepare",
                "warning",
            )
            emit(
                "warning",
                {
                    "message": "Fundamentals Analyst was disabled automatically for crypto analysis.",
                },
            )

        ensure_not_cancelled()

        config = self.build_analysis_config(request, minimax_settings, runtime_profile)
        emit_analysis_log(
            "Building TradingAgents graph.",
            "graph_setup",
            provider=minimax_settings["provider"],
            model=request.model,
            depth_rounds=runtime_profile["effective_rounds"],
            mcp_max_tool_rounds=runtime_profile["mcp_max_tool_rounds"],
            max_tokens=runtime_profile["llm_max_tokens"],
        )
        graph = TradingAgentsGraph(selected_analysts=filtered_analysts, debug=False, config=config)

        initial_snapshot = self.extract_runtime_snapshot({})
        current_agent = ANALYST_NODE_SPECS[filtered_analysts[0]].agent_node
        initial_status = self.build_status_snapshot(initial_snapshot, filtered_analysts, current_agent)
        emit(
            "analysis_meta",
            {
                "symbol": symbol,
                "asset_type_mode": request.asset_type,
                "analysis_date": request.analysis_date,
                "lookback_days": request.lookback_days,
                "asset_type": asset_type,
                "output_language": request.output_language,
                "research_depth": request.research_depth,
                "depth_rounds": runtime_profile["effective_rounds"],
                "mcp_max_tool_rounds": runtime_profile["mcp_max_tool_rounds"],
                "model": request.model,
                "llm_max_tokens": runtime_profile["llm_max_tokens"],
                "resource_constrained": self.settings.resource_constrained_mode,
                "selected_analysts": filtered_analysts,
                "selected_analyst_labels": [ANALYST_NODE_SPECS[key].agent_node for key in filtered_analysts],
                "provider": minimax_settings["provider"],
                "base_url": minimax_settings["base_url"],
                "initial_status": initial_status,
            },
        )
        emit("status_snapshot", initial_status)

        ensure_not_cancelled()
        graph.ticker = symbol
        emit_analysis_log("Skipping stock outcome reflection for crypto analysis.", "memory")

        ensure_not_cancelled()
        if config.get("checkpoint_enabled"):
            emit_analysis_log("Checkpoint resume requested; preparing checkpointer.", "checkpoint")
            graph._checkpointer_ctx = get_checkpointer(config["data_cache_dir"], symbol)
            saver = graph._checkpointer_ctx.__enter__()
            graph.graph = graph.workflow.compile(checkpointer=saver)
            step = checkpoint_step(config["data_cache_dir"], symbol, request.analysis_date)
            emit(
                "warning",
                {
                    "message": (
                        f"Checkpoint resume enabled. Resuming from step {step}."
                        if step is not None
                        else "Checkpoint resume enabled. Starting fresh."
                    )
                },
            )

        def emit_captured_log(message: str, phase: str = "backend_log", level: str = "info") -> None:
            emit_analysis_log(message, phase, level, write_logger=False)

        tradingagents_logger = logging.getLogger("tradingagents")
        log_capture: AnalysisLoggingHandler | None = None
        stdout_stream: AnalysisLogStream | None = None
        stderr_stream: AnalysisLogStream | None = None
        stdout_redirect = None
        stderr_redirect = None
        if self.settings.analysis_verbose_runtime_logs:
            log_capture = AnalysisLoggingHandler(emit_captured_log)
            log_capture.setFormatter(logging.Formatter("%(levelname)s %(name)s - %(message)s"))
            stdout_stream = AnalysisLogStream(emit_captured_log, "backend_stdout", "info")
            stderr_stream = AnalysisLogStream(emit_captured_log, "backend_stderr", "warning")
            stdout_redirect = contextlib.redirect_stdout(stdout_stream)
            stderr_redirect = contextlib.redirect_stderr(stderr_stream)
            tradingagents_logger.addHandler(log_capture)
            stdout_redirect.__enter__()
            stderr_redirect.__enter__()

        final_state: dict = {}
        previous_snapshot = initial_snapshot
        previous_status = initial_status
        seen_message_signatures: set[str] = set()
        try:
            ensure_not_cancelled()
            if config.get("memory_log_path"):
                emit_analysis_log("Loading past context from memory log.", "memory")
                past_context = graph.memory_log.get_past_context(symbol)
            else:
                emit_analysis_log("Persistent memory log disabled for stateless API run.", "memory")
                past_context = ""
            ensure_not_cancelled()
            emit_analysis_log("Creating initial graph state.", "graph_setup")
            init_state = graph.propagator.create_initial_state(
                symbol,
                request.analysis_date,
                asset_type=asset_type,
                past_context=past_context,
            )
            args = graph.propagator.get_graph_args()
            args["stream_mode"] = "updates"
            if config.get("checkpoint_enabled"):
                tid = thread_id(symbol, request.analysis_date)
                args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

            started_at = time.time()
            chunk_index = 0
            emit_analysis_log("Graph stream started.", "stream", current_agent=current_agent)
            final_state.update(init_state)
            final_state["messages"] = []
            for chunk in graph.graph.stream(init_state, **args):
                ensure_not_cancelled()
                for node_name, update in self.iter_graph_state_updates(chunk):
                    chunk_index += 1
                    updated_keys = self.merge_graph_state_update(final_state, update)
                    current_snapshot = self.extract_runtime_snapshot(final_state)
                    current_agent = self.detect_current_agent(previous_snapshot, current_snapshot) or current_agent
                    current_status = self.build_status_snapshot(current_snapshot, filtered_analysts, current_agent)
                    emit_analysis_log(
                        "Graph emitted a state update.",
                        current_status["phase"],
                        chunk_index=chunk_index,
                        graph_node=node_name,
                        current_agent=current_agent,
                        updated_keys=updated_keys,
                        progress=current_status["progress"],
                    )
                    self.emit_message_progress_updates(
                        final_state.get("messages", []),
                        current_agent,
                        seen_message_signatures,
                        emit,
                    )
                    if final_state.get("messages"):
                        final_state["messages"] = []
                    self.emit_snapshot_updates(previous_snapshot, current_snapshot, emit)
                    if current_status != previous_status:
                        emit("status_snapshot", current_status)
                        previous_status = current_status
                    previous_snapshot = current_snapshot
                    ensure_not_cancelled()

            if not final_state.get("final_trade_decision"):
                raise RuntimeError("Analysis finished without a final_trade_decision.")

            graph.curr_state = final_state
            if config.get("persist_analysis_artifacts"):
                graph._log_state(request.analysis_date, final_state)
                graph.memory_log.store_decision(
                    ticker=symbol,
                    trade_date=request.analysis_date,
                    final_trade_decision=final_state["final_trade_decision"],
                )
            if config.get("checkpoint_enabled"):
                clear_checkpoint(config["data_cache_dir"], symbol, request.analysis_date)

            completed_snapshot = self.extract_runtime_snapshot(final_state)
            completed_status = self.build_status_snapshot(completed_snapshot, filtered_analysts, "Portfolio Manager")
            completed_sections_patch = self.build_changed_sections(previous_snapshot.get("sections", {}), completed_snapshot["sections"])
            completed_research_patch = self.build_changed_fields(previous_snapshot.get("investment", {}), completed_snapshot["investment"])
            completed_risk_patch = self.build_changed_fields(previous_snapshot.get("risk", {}), completed_snapshot["risk"])
            signal = graph.process_signal(final_state["final_trade_decision"])
            elapsed_seconds = round(time.time() - started_at, 2)
            history_id = None
            history_sections = build_history_sections(final_state)
            if self.history_store.configured:
                try:
                    history_id = self.history_store.save_analysis(
                        request=request,
                        user=user,
                        symbol=symbol,
                        signal=signal,
                        elapsed_seconds=elapsed_seconds,
                        sections=history_sections,
                    )
                    if history_id:
                        emit_analysis_log(
                            "Analysis markdown sections saved to history database.",
                            "history",
                            history_id=history_id,
                            section_count=len(history_sections),
                        )
                except Exception as exc:
                    logger.exception("failed to save analysis history")
                    emit_analysis_log(
                        "Analysis completed, but history database save failed.",
                        "history",
                        "warning",
                        error=str(exc),
                    )
                    emit("warning", {"message": "Analysis completed, but history database save failed."})
            else:
                emit_analysis_log("History database is not configured; skipping DB save.", "history", "warning")

            emit_analysis_log(
                "Analysis completed.",
                "complete",
                signal=signal,
                elapsed_seconds=elapsed_seconds,
            )
            emit(
                "complete",
                {
                    "elapsed_seconds": elapsed_seconds,
                    "signal": signal,
                    "history_id": history_id,
                    "sections_patch": completed_sections_patch,
                    "research_patch": completed_research_patch,
                    "risk_patch": completed_risk_patch,
                    "status": completed_status,
                },
            )
        finally:
            if stdout_stream is not None:
                stdout_stream.flush()
            if stderr_stream is not None:
                stderr_stream.flush()
            if stderr_redirect is not None:
                stderr_redirect.__exit__(None, None, None)
            if stdout_redirect is not None:
                stdout_redirect.__exit__(None, None, None)
            if log_capture is not None:
                tradingagents_logger.removeHandler(log_capture)
            if graph is not None and graph._checkpointer_ctx is not None:
                graph._checkpointer_ctx.__exit__(None, None, None)
                graph._checkpointer_ctx = None
                graph.graph = graph.workflow.compile()
            if graph is not None:
                graph.curr_state = None
            final_state.clear()
            previous_snapshot.clear()
            previous_status.clear()
            seen_message_signatures.clear()
            gc.collect()

    async def generate_analysis_stream(
        self,
        analysis_request: AnalysisRequest,
        http_request: Request,
        user: dict,
        reserved_slot: bool = False,
    ) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=self.settings.analysis_sse_queue_maxsize)
        stream_started_at = time.time()
        cancel_event = threading.Event()
        slot_release_lock = threading.Lock()
        slot_released = False

        def release_slot_once() -> None:
            nonlocal slot_released
            if not reserved_slot:
                return
            with slot_release_lock:
                if slot_released:
                    return
                self.release_analysis_slot()
                slot_released = True

        if analysis_request.run_id:
            with self.active_analysis_lock:
                self.active_analysis_cancel_events[analysis_request.run_id] = cancel_event

        async def queue_sse_item(payload: str, drop_if_full: bool) -> bool:
            if drop_if_full:
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    return False
                return True
            await queue.put(payload)
            return True

        def emit(event: str, data: dict) -> None:
            if cancel_event.is_set() and event not in {"cancelled", "error"}:
                return
            future = asyncio.run_coroutine_threadsafe(
                queue_sse_item(self._sse(event, data), event in self.settings.droppable_sse_events),
                loop,
            )
            try:
                future.result(timeout=1.0 if cancel_event.is_set() else None)
            except FutureTimeoutError:
                future.cancel()
                logger.warning(
                    "dropping SSE event after client cancellation: run_id=%s event=%s",
                    analysis_request.run_id,
                    event,
                )

        def worker() -> None:
            try:
                self.run_trading_analysis(analysis_request, emit, user, cancel_event)
            except AnalysisCancelled:
                logger.info("analysis cancelled: run_id=%s symbol=%s", analysis_request.run_id, analysis_request.symbol)
                emit(
                    "cancelled",
                    {
                        "run_id": analysis_request.run_id,
                        "message": "Analysis was cancelled before completion.",
                    },
                )
            except HTTPException as exc:
                logger.warning("analysis request failed: %s", exc.detail)
                emit("error", {"error": exc.detail})
            except Exception as exc:
                logger.exception("analysis stream crashed")
                emit("error", {"error": str(exc)})
            finally:
                try:
                    finish_future = asyncio.run_coroutine_threadsafe(queue.put(None), loop)
                    finish_future.result(timeout=1.0)
                except FutureTimeoutError:
                    finish_future.cancel()
                except RuntimeError:
                    pass
                finally:
                    release_slot_once()

        worker_task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                if await http_request.is_disconnected():
                    cancel_event.set()
                    logger.info(
                        "analysis client disconnected: run_id=%s symbol=%s",
                        analysis_request.run_id,
                        analysis_request.symbol,
                    )
                    break

                try:
                    item = await asyncio.wait_for(queue.get(), timeout=self.settings.stream_heartbeat_seconds)
                except asyncio.TimeoutError:
                    if worker_task.done():
                        break
                    if await http_request.is_disconnected():
                        cancel_event.set()
                        logger.info(
                            "analysis client disconnected during heartbeat: run_id=%s symbol=%s",
                            analysis_request.run_id,
                            analysis_request.symbol,
                        )
                        break
                    heartbeat_elapsed = round(time.time() - stream_started_at, 2)
                    yield self._sse(
                        "analysis_log",
                        {
                            "level": "debug",
                            "phase": "heartbeat",
                            "message": "Backend is still processing the active graph node.",
                            "elapsed_seconds": heartbeat_elapsed,
                            "log_line": (
                                "analysis symbol="
                                f"{analysis_request.symbol} phase=heartbeat elapsed={heartbeat_elapsed}s "
                                "message=Backend is still processing the active graph node. extra={}"
                            ),
                        },
                    )
                    continue
                if item is None:
                    break
                yield item
        except asyncio.CancelledError:
            cancel_event.set()
            logger.info(
                "analysis stream task cancelled: run_id=%s symbol=%s",
                analysis_request.run_id,
                analysis_request.symbol,
            )
            raise
        finally:
            if analysis_request.run_id:
                with self.active_analysis_lock:
                    self.active_analysis_cancel_events.pop(analysis_request.run_id, None)
            if not worker_task.done():
                cancel_event.set()
                try:
                    await asyncio.wait_for(asyncio.shield(worker_task), timeout=1.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        "analysis worker is waiting for the active graph call to return: run_id=%s symbol=%s",
                        analysis_request.run_id,
                        analysis_request.symbol,
                    )
            else:
                await worker_task