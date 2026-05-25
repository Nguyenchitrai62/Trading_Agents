import asyncio
import contextlib
import gc
import hashlib
import io
import json
import logging
import os
import threading
import time
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import AsyncIterator, Callable, List, Literal

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, Field, field_validator

try:
    from tradingagents.default_config import DEFAULT_CONFIG
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
    DEFAULT_CONFIG = {}
    ANALYST_NODE_SPECS = {}
    checkpoint_step = None
    clear_checkpoint = None
    get_checkpointer = None
    thread_id = None
    TradingAgentsGraph = None
    ANALYSIS_RUNTIME_IMPORT_ERROR = exc

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "FE"
IMAGE_DIR = ROOT_DIR / "image"
INDEX_FILE = ROOT_DIR / "index.html"
CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")
DEFAULT_ANALYSTS = ["market", "social", "news"]
RESEARCH_DEPTH_OPTIONS = {
    "quick": {
        "label": "Quick",
        "rounds": 1,
        "description": "Fast scan with minimal debate.",
    },
    "medium": {
        "label": "Medium",
        "rounds": 3,
        "description": "Balanced research depth for regular analysis.",
    },
    "deep": {
        "label": "Deep",
        "rounds": 5,
        "description": "More debate rounds before the final decision.",
    },
}
SECTION_META = {
    "market_report": {
        "title": "Market Analysis",
        "agent": "Market Analyst",
        "team": "Analyst Team",
    },
    "sentiment_report": {
        "title": "Sentiment Analysis",
        "agent": "Sentiment Analyst",
        "team": "Analyst Team",
    },
    "news_report": {
        "title": "News Analysis",
        "agent": "News Analyst",
        "team": "Analyst Team",
    },
    "fundamentals_report": {
        "title": "Fundamentals Analysis",
        "agent": "Fundamentals Analyst",
        "team": "Analyst Team",
    },
    "investment_plan": {
        "title": "Research Manager Plan",
        "agent": "Research Manager",
        "team": "Research Team",
    },
    "trader_investment_plan": {
        "title": "Trader Plan",
        "agent": "Trader",
        "team": "Trading Team",
    },
    "final_trade_decision": {
        "title": "Portfolio Decision",
        "agent": "Portfolio Manager",
        "team": "Portfolio Management",
    },
}

load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / ".env.enterprise", override=False)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("tradingagents.app")


APP_TITLE = "TradingAgents Analysis API"
APP_VERSION = "0.0.2"


DEFAULT_MODEL = os.getenv("MINIMAX_MODEL", "").strip() or "MiniMax-M2.7"
DEFAULT_ANALYSIS_LOOKBACK_DAYS = 7
DEFAULT_ASSET_TYPE = "crypto"
DEFAULT_OUTPUT_LANGUAGE = "Vietnamese"
DEFAULT_RESEARCH_DEPTH = "medium"
DEFAULT_SELECTED_ANALYSTS = DEFAULT_ANALYSTS.copy()
DEFAULT_CHECKPOINT_ENABLED = False
STREAM_HEARTBEAT_SECONDS = max(1.0, _env_float("ANALYSIS_STREAM_HEARTBEAT_SECONDS", 2.0))
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
    if origin.strip()
]
ALLOW_ALL_ORIGINS = not CORS_ALLOW_ORIGINS or CORS_ALLOW_ORIGINS == ["*"]

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

ACTIVE_ANALYSIS_CANCEL_EVENTS: dict[str, threading.Event] = {}
ACTIVE_ANALYSIS_LOCK = threading.Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ALLOW_ALL_ORIGINS else CORS_ALLOW_ORIGINS,
    allow_credentials=not ALLOW_ALL_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/FE", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")
if IMAGE_DIR.exists():
    app.mount("/image", StaticFiles(directory=str(IMAGE_DIR)), name="image")


class AnalysisRequest(BaseModel):
    symbol: str = Field(min_length=1)
    asset_type: Literal["crypto"] = DEFAULT_ASSET_TYPE
    run_id: str | None = Field(default=None, max_length=120)
    analysis_date: str = Field(default_factory=lambda: date.today().isoformat())
    lookback_days: int = Field(default=DEFAULT_ANALYSIS_LOOKBACK_DAYS, ge=1, le=90)
    output_language: str = Field(default=DEFAULT_OUTPUT_LANGUAGE)
    selected_analysts: List[Literal["market", "social", "news", "fundamentals"]] = Field(
        default_factory=lambda: DEFAULT_SELECTED_ANALYSTS.copy(),
        min_length=1,
    )
    research_depth: Literal["quick", "medium", "deep"] = DEFAULT_RESEARCH_DEPTH
    model: str = Field(default=DEFAULT_MODEL, min_length=1)
    checkpoint_enabled: bool = DEFAULT_CHECKPOINT_ENABLED

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper().replace(" ", "")
        if not normalized:
            raise ValueError("symbol is required")
        if "/" not in normalized and "-" not in normalized:
            return f"{normalized}-USDT"
        return normalized

    @field_validator("run_id")
    @classmethod
    def normalize_run_id(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("analysis_date")
    @classmethod
    def validate_analysis_date(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("analysis_date must be in YYYY-MM-DD format") from exc
        return value

    @field_validator("output_language")
    @classmethod
    def normalize_output_language(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("output_language is required")
        return normalized

    @field_validator("selected_analysts")
    @classmethod
    def normalize_selected_analysts(cls, value: List[str]) -> List[str]:
        seen = []
        for item in value:
            if item not in seen:
                seen.append(item)
        if not seen:
            raise ValueError("at least one analyst must be selected")
        return seen


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    model: str = DEFAULT_MODEL
    max_tokens: int = 128000
    temperature: float = 1
    stream: bool = True


def resolve_minimax_settings() -> dict:
    base_url_override = os.getenv("MINIMAX_BASE_URL", "").strip()
    global_key = os.getenv("MINIMAX_API_KEY", "").strip()
    china_key = os.getenv("MINIMAX_CN_API_KEY", "").strip()

    if global_key:
        return {
            "configured": True,
            "provider": "minimax",
            "api_key": global_key,
            "base_url": base_url_override or "https://api.minimax.io/anthropic",
        }

    if china_key:
        return {
            "configured": True,
            "provider": "minimax-cn",
            "api_key": china_key,
            "base_url": base_url_override or "https://api.minimaxi.com/anthropic",
        }

    return {
        "configured": False,
        "provider": None,
        "api_key": "",
        "base_url": base_url_override or "https://api.minimax.io/anthropic",
    }


def ensure_analysis_runtime_available() -> None:
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


def normalize_ticker_symbol(ticker: str) -> str:
    normalized = ticker.strip().upper().replace(" ", "")
    if normalized and "/" not in normalized and "-" not in normalized:
        return f"{normalized}-USDT"
    return normalized


def filter_analysts_for_crypto(selected_analysts: List[str]) -> List[str]:
    return [analyst for analyst in selected_analysts if analyst != "fundamentals"]


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


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def get_minimax_client() -> AsyncAnthropic:
    settings = resolve_minimax_settings()
    if not settings["configured"]:
        raise HTTPException(
            status_code=500,
            detail="Set MINIMAX_API_KEY or MINIMAX_CN_API_KEY in .env before using /api/chat.",
        )
    return AsyncAnthropic(api_key=settings["api_key"], base_url=settings["base_url"])


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


async def generate_chat_stream(request: ChatRequest) -> AsyncIterator[str]:
    try:
        start_time = time.time()
        client = get_minimax_client()
        system_message = "You are a helpful assistant."
        anthropic_messages = build_anthropic_chat_messages(request)

        stream = await client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
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
                        yield _sse("thinking", {"content": thinking})

                elif delta_type == "text_delta":
                    text = getattr(delta, "text", None)
                    if text is None and isinstance(delta, dict):
                        text = delta.get("text")
                    if text:
                        text_buffer += text
                        yield _sse("content", {"content": text})

            elif chunk_type == "message_stop":
                end_time = time.time()
                total_time = end_time - start_time
                generation_time = end_time - first_token_time if first_token_time else total_time
                estimated_tokens = len(text_buffer) // 4
                tokens = output_tokens if output_tokens > 0 else estimated_tokens
                tokens_per_second = tokens / generation_time if generation_time > 0 else 0

                yield _sse(
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
        yield _sse("error", {"error": str(exc)})


async def generate_non_streaming_chat(request: ChatRequest) -> dict:
    try:
        client = get_minimax_client()
        system_message = "You are a helpful assistant."
        anthropic_messages = build_anthropic_chat_messages(request)

        response = await client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
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


def build_analysis_config(request: AnalysisRequest, settings: dict) -> dict:
    depth_preset = RESEARCH_DEPTH_OPTIONS[request.research_depth]
    config = deepcopy(DEFAULT_CONFIG)
    config.update(
        {
            "llm_provider": settings["provider"],
            "quick_think_llm": request.model,
            "deep_think_llm": request.model,
            "backend_url": settings["base_url"],
            "output_language": request.output_language,
            "max_debate_rounds": depth_preset["rounds"],
            "max_risk_discuss_rounds": depth_preset["rounds"],
            "global_news_lookback_days": request.lookback_days,
            "crypto_market_lookback_days": request.lookback_days,
            "crypto_market_max_candles": 199,
            "checkpoint_enabled": request.checkpoint_enabled,
        }
    )
    return config


def extract_runtime_snapshot(state: dict) -> dict:
    investment_state = state.get("investment_debate_state") or {}
    risk_state = state.get("risk_debate_state") or {}
    return {
        "sections": {
            key: (state.get(key) or "")
            for key in SECTION_META
        },
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


def _tool_call_summary(tool_call: dict) -> str:
    name = str(tool_call.get("name") or "tool")
    args = tool_call.get("args") or {}
    if not args:
        return name
    if isinstance(args, dict):
        items = ", ".join(f"{key}={value}" for key, value in list(args.items())[:4])
        return f"{name}({items})"
    return f"{name}({args})"


def _build_message_signature(message: object) -> str:
    raw_signature = ""
    if hasattr(message, "id") and getattr(message, "id"):
        raw_signature = str(getattr(message, "id"))
    else:
        raw_signature = json.dumps(
            {
                "type": message.__class__.__name__,
                "name": getattr(message, "name", ""),
                "content": _normalize_message_content(getattr(message, "content", "")),
                "tool_calls": getattr(message, "tool_calls", []),
                "tool_call_id": getattr(message, "tool_call_id", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    return hashlib.sha1(raw_signature.encode("utf-8", errors="ignore")).hexdigest()


def emit_message_progress_updates(
    messages: list[object],
    current_agent: str | None,
    seen_signatures: set[str],
    emit: Callable[[str, dict], None],
) -> None:
    for message in messages:
        signature = _build_message_signature(message)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        if isinstance(message, HumanMessage):
            continue

        if isinstance(message, ToolMessage):
            tool_name = getattr(message, "name", None) or getattr(message, "tool_call_id", None) or "tool"
            content = _normalize_message_content(getattr(message, "content", ""))
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
                        "content": "\n".join(_tool_call_summary(tool_call) for tool_call in tool_calls),
                    },
                )
            content = _normalize_message_content(getattr(message, "content", ""))
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


def build_status_snapshot(snapshot: dict, selected_analysts: List[str], current_agent: str | None) -> dict:
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
            "percent": round((completed_sections / total_sections) * 100, 1)
            if total_sections
            else 0,
        },
        "groups": {
            "analysts": analysts,
            "research": research,
            "trading": trader,
            "risk": risk_items,
            "portfolio": portfolio,
        },
    }


def build_changed_fields(previous: dict, current: dict) -> dict:
    return {
        key: value
        for key, value in current.items()
        if value != previous.get(key)
    }


def build_changed_sections(previous: dict, current: dict) -> dict:
    return {
        key: value
        for key, value in current.items()
        if value and value != previous.get(key)
    }


def emit_snapshot_updates(previous: dict, current: dict, emit: Callable[[str, dict], None]) -> None:
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
                "patch": build_changed_fields(previous_investment, current_investment),
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
                    "patch": build_changed_fields(previous_risk, current_risk),
                },
            )


def run_trading_analysis(
    request: AnalysisRequest,
    emit: Callable[[str, dict], None],
    cancel_event: threading.Event | None = None,
) -> None:
    ensure_analysis_runtime_available()
    settings = resolve_minimax_settings()
    if not settings["configured"]:
        raise HTTPException(
            status_code=500,
            detail="Set MINIMAX_API_KEY or MINIMAX_CN_API_KEY in .env before running analysis.",
        )

    cancel_event = cancel_event or threading.Event()
    run_started_at = time.time()
    symbol = normalize_ticker_symbol(request.symbol)

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
    asset_type = DEFAULT_ASSET_TYPE
    filtered_analysts = filter_analysts_for_crypto(request.selected_analysts)
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

    config = build_analysis_config(request, settings)
    emit_analysis_log(
        "Building TradingAgents graph.",
        "graph_setup",
        provider=settings["provider"],
        model=request.model,
        depth_rounds=RESEARCH_DEPTH_OPTIONS[request.research_depth]["rounds"],
    )
    graph = TradingAgentsGraph(selected_analysts=filtered_analysts, debug=False, config=config)

    initial_snapshot = extract_runtime_snapshot({})
    current_agent = ANALYST_NODE_SPECS[filtered_analysts[0]].agent_node
    initial_status = build_status_snapshot(initial_snapshot, filtered_analysts, current_agent)
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
            "depth_rounds": RESEARCH_DEPTH_OPTIONS[request.research_depth]["rounds"],
            "model": request.model,
            "selected_analysts": filtered_analysts,
            "selected_analyst_labels": [ANALYST_NODE_SPECS[key].agent_node for key in filtered_analysts],
            "provider": settings["provider"],
            "base_url": settings["base_url"],
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

    log_capture = AnalysisLoggingHandler(emit_captured_log)
    log_capture.setFormatter(logging.Formatter("%(levelname)s %(name)s - %(message)s"))
    tradingagents_logger = logging.getLogger("tradingagents")
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
        emit_analysis_log("Loading past context from memory log.", "memory")
        past_context = graph.memory_log.get_past_context(symbol)
        ensure_not_cancelled()
        emit_analysis_log("Creating initial graph state.", "graph_setup")
        init_state = graph.propagator.create_initial_state(
            symbol,
            request.analysis_date,
            asset_type=asset_type,
            past_context=past_context,
        )
        args = graph.propagator.get_graph_args()
        if config.get("checkpoint_enabled"):
            tid = thread_id(symbol, request.analysis_date)
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = tid

        started_at = time.time()
        chunk_index = 0
        emit_analysis_log("Graph stream started.", "stream", current_agent=current_agent)
        for chunk in graph.graph.stream(init_state, **args):
            ensure_not_cancelled()
            chunk_index += 1
            final_state.update(chunk)
            current_snapshot = extract_runtime_snapshot(final_state)
            current_agent = detect_current_agent(previous_snapshot, current_snapshot) or current_agent
            current_status = build_status_snapshot(current_snapshot, filtered_analysts, current_agent)
            emit_analysis_log(
                "Graph emitted a state update.",
                current_status["phase"],
                chunk_index=chunk_index,
                current_agent=current_agent,
                updated_keys=sorted(chunk.keys()),
                progress=current_status["progress"],
            )
            emit_message_progress_updates(
                final_state.get("messages", []),
                current_agent,
                seen_message_signatures,
                emit,
            )
            if final_state.get("messages"):
                final_state["messages"] = []
            emit_snapshot_updates(previous_snapshot, current_snapshot, emit)
            if current_status != previous_status:
                emit("status_snapshot", current_status)
                previous_status = current_status
            previous_snapshot = current_snapshot
            ensure_not_cancelled()

        if not final_state.get("final_trade_decision"):
            raise RuntimeError("Analysis finished without a final_trade_decision.")

        graph.curr_state = final_state
        graph._log_state(request.analysis_date, final_state)
        graph.memory_log.store_decision(
            ticker=symbol,
            trade_date=request.analysis_date,
            final_trade_decision=final_state["final_trade_decision"],
        )
        if config.get("checkpoint_enabled"):
            clear_checkpoint(config["data_cache_dir"], symbol, request.analysis_date)

        completed_snapshot = extract_runtime_snapshot(final_state)
        completed_status = build_status_snapshot(completed_snapshot, filtered_analysts, "Portfolio Manager")
        completed_sections_patch = build_changed_sections(previous_snapshot.get("sections", {}), completed_snapshot["sections"])
        completed_research_patch = build_changed_fields(previous_snapshot.get("investment", {}), completed_snapshot["investment"])
        completed_risk_patch = build_changed_fields(previous_snapshot.get("risk", {}), completed_snapshot["risk"])
        emit_analysis_log(
            "Analysis completed and final decision stored.",
            "complete",
            signal=graph.process_signal(final_state["final_trade_decision"]),
            elapsed_seconds=round(time.time() - started_at, 2),
        )
        emit(
            "complete",
            {
                "elapsed_seconds": round(time.time() - started_at, 2),
                "signal": graph.process_signal(final_state["final_trade_decision"]),
                "sections_patch": completed_sections_patch,
                "research_patch": completed_research_patch,
                "risk_patch": completed_risk_patch,
                "status": completed_status,
            },
        )
    finally:
        stdout_stream.flush()
        stderr_stream.flush()
        stderr_redirect.__exit__(None, None, None)
        stdout_redirect.__exit__(None, None, None)
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


async def generate_analysis_stream(analysis_request: AnalysisRequest, http_request: Request) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    stream_started_at = time.time()
    cancel_event = threading.Event()

    if analysis_request.run_id:
        with ACTIVE_ANALYSIS_LOCK:
            ACTIVE_ANALYSIS_CANCEL_EVENTS[analysis_request.run_id] = cancel_event

    def emit(event: str, data: dict) -> None:
        asyncio.run_coroutine_threadsafe(queue.put(_sse(event, data)), loop).result()

    def worker() -> None:
        try:
            run_trading_analysis(analysis_request, emit, cancel_event)
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
            asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

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
                item = await asyncio.wait_for(queue.get(), timeout=STREAM_HEARTBEAT_SECONDS)
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
                yield _sse(
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
            with ACTIVE_ANALYSIS_LOCK:
                ACTIVE_ANALYSIS_CANCEL_EVENTS.pop(analysis_request.run_id, None)
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


@app.get("/", response_class=HTMLResponse)
async def serve_index() -> HTMLResponse:
    return HTMLResponse(INDEX_FILE.read_text(encoding="utf-8"))


@app.get("/favicon.ico")
async def favicon() -> Response:
    logo_file = IMAGE_DIR / "LOGO.png"
    if logo_file.exists():
        return FileResponse(logo_file, media_type="image/png")
    return Response(status_code=204)


@app.get("/health")
async def health_check() -> dict:
    settings = resolve_minimax_settings()
    return {
        "status": "healthy",
        "title": APP_TITLE,
        "version": APP_VERSION,
        "configured": settings["configured"],
        "provider": settings["provider"],
        "modes": ["analysis", "chat"],
    }


@app.post("/api/chat")
async def chat_completion(request: ChatRequest):
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages cannot be empty")

    if request.stream:
        return StreamingResponse(
            generate_chat_stream(request),
            media_type="text/event-stream",
        )

    return await generate_non_streaming_chat(request)


@app.post("/api/analyze/{run_id}/cancel")
async def cancel_trading_analysis(run_id: str) -> dict:
    with ACTIVE_ANALYSIS_LOCK:
        cancel_event = ACTIVE_ANALYSIS_CANCEL_EVENTS.get(run_id)

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


@app.post("/api/analyze")
async def analyze_trading_agents(analysis_request: AnalysisRequest, http_request: Request):
    return StreamingResponse(
        generate_analysis_stream(analysis_request, http_request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    port = _env_int("PORT", 8000)
    uvicorn.run(app, host="0.0.0.0", port=port)