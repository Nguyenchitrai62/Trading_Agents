import asyncio
import contextlib
import gc
import hashlib
import io
import json
import logging
import os
import uuid
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
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from pydantic import BaseModel, Field, field_validator
import requests

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(ROOT_DIR / ".env.enterprise", override=False)


CPU_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def _auto_cpu_threads() -> int:
    return max(1, os.cpu_count() or 1)


def _configured_cpu_threads() -> int:
    for name in CPU_THREAD_ENV_VARS:
        raw = os.getenv(name, "").strip()
        if not raw:
            continue
        try:
            return max(1, int(raw))
        except ValueError:
            continue
    return _auto_cpu_threads()


def _apply_cpu_thread_defaults() -> None:
    thread_value = str(_configured_cpu_threads())
    for name in CPU_THREAD_ENV_VARS:
        os.environ.setdefault(name, thread_value)


_apply_cpu_thread_defaults()

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

FRONTEND_DIR = ROOT_DIR / "FE"
IMAGE_DIR = ROOT_DIR / "image"
INDEX_FILE = ROOT_DIR / "index.html"
CRYPTO_SUFFIXES = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")
DEFAULT_ANALYSTS = ["market", "social", "news", "fundamentals"]
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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _memory_limit_mb() -> int | None:
    candidates: list[int] = []
    for path in (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not raw or raw == "max":
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if 0 < value < 1 << 60:
            candidates.append(value // (1024 * 1024))

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        page_size = page_count = 0
    if page_size and page_count:
        candidates.append((page_size * page_count) // (1024 * 1024))

    return min(candidates) if candidates else None


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


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("tradingagents.app")


APP_TITLE = "TradingAgents Analysis API"
APP_VERSION = "0.1.0"


DEFAULT_MODEL = os.getenv("MINIMAX_MODEL", "").strip() or "MiniMax-M2.7"
DEFAULT_ANALYSIS_LOOKBACK_DAYS = 7
DEFAULT_ASSET_TYPE = "crypto"
DEFAULT_OUTPUT_LANGUAGE = "Vietnamese"
GOOGLE_ALLOWED_EMAIL = os.getenv("GOOGLE_ALLOWED_EMAIL", "trainguyenchi30@gmail.com").strip().lower()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()
RESOURCE_CONSTRAINED_MODE = False
ANALYSIS_CPU_THREADS = _configured_cpu_threads()
DEFAULT_RESEARCH_DEPTH = "medium"
DEFAULT_SELECTED_ANALYSTS = DEFAULT_ANALYSTS.copy()
DEFAULT_CHECKPOINT_ENABLED = False
STREAM_HEARTBEAT_SECONDS = max(1.0, _env_float("ANALYSIS_STREAM_HEARTBEAT_SECONDS", 2.0))
ANALYSIS_VERBOSE_RUNTIME_LOGS = _env_bool(
    "ANALYSIS_VERBOSE_RUNTIME_LOGS",
    not RESOURCE_CONSTRAINED_MODE,
)
ANALYSIS_MAX_CONCURRENT_RUNS = max(2, ANALYSIS_CPU_THREADS)
ANALYSIS_SSE_QUEUE_MAXSIZE = max(
    8,
    _env_int("ANALYSIS_SSE_QUEUE_MAXSIZE", 32 if RESOURCE_CONSTRAINED_MODE else 128),
)
ANALYSIS_LLM_MAX_TOKENS = max(
    512,
    _env_int("ANALYSIS_LLM_MAX_TOKENS", 8000),
)
ANALYSIS_TRACE_CHAR_LIMIT = max(
    400,
    _env_int("ANALYSIS_TRACE_CHAR_LIMIT", 1800 if RESOURCE_CONSTRAINED_MODE else 4000),
)
DROPPABLE_SSE_EVENTS = {"analysis_log", "agent_trace"}
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
    if origin.strip()
]
ALLOW_ALL_ORIGINS = not CORS_ALLOW_ORIGINS or CORS_ALLOW_ORIGINS == ["*"]

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

ACTIVE_ANALYSIS_CANCEL_EVENTS: dict[str, threading.Event] = {}
ACTIVE_ANALYSIS_LOCK = threading.Lock()
ACTIVE_ANALYSIS_COUNT = 0
AUTH_CACHE: dict[str, tuple[float, dict]] = {}
AUTH_CACHE_LOCK = threading.Lock()

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
    lookback_days: int = Field(default=DEFAULT_ANALYSIS_LOOKBACK_DAYS, ge=1)
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


class TursoHistoryStore:
    def __init__(self, database_url: str, auth_token: str):
        self.database_url = database_url.strip()
        self.auth_token = auth_token.strip()
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.database_url and self.auth_token)

    @property
    def pipeline_url(self) -> str:
        if self.database_url.startswith("libsql://"):
            base_url = "https://" + self.database_url[len("libsql://"):]
        else:
            base_url = self.database_url
        return f"{base_url.rstrip('/')}/v2/pipeline"

    def _value_to_hrana(self, value: object) -> dict:
        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "integer", "value": "1" if value else "0"}
        if isinstance(value, int):
            return {"type": "integer", "value": str(value)}
        if isinstance(value, float):
            return {"type": "float", "value": value}
        return {"type": "text", "value": str(value)}

    def _value_from_hrana(self, value: object) -> object:
        if not isinstance(value, dict):
            return value
        value_type = value.get("type")
        raw = value.get("value")
        if value_type == "null":
            return None
        if value_type == "integer":
            try:
                return int(raw)
            except (TypeError, ValueError):
                return raw
        if value_type == "float":
            try:
                return float(raw)
            except (TypeError, ValueError):
                return raw
        return raw

    def _execute(self, sql: str, args: list[object] | None = None) -> dict:
        if not self.configured:
            raise RuntimeError("Turso history database is not configured.")
        response = requests.post(
            self.pipeline_url,
            headers={
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json",
            },
            json={
                "requests": [
                    {
                        "type": "execute",
                        "stmt": {
                            "sql": sql,
                            "args": [self._value_to_hrana(arg) for arg in (args or [])],
                        },
                    },
                    {"type": "close"},
                ]
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("results") or [{}])[0]
        if result.get("type") == "error":
            error = result.get("error") or {}
            raise RuntimeError(error.get("message") or "Turso SQL execution failed.")
        return ((result.get("response") or {}).get("result") or {})

    def _query_rows(self, sql: str, args: list[object] | None = None) -> list[dict]:
        result = self._execute(sql, args)
        columns = [col.get("name") for col in result.get("cols", [])]
        rows = []
        for raw_row in result.get("rows", []):
            row_values = [self._value_from_hrana(value) for value in raw_row]
            rows.append(dict(zip(columns, row_values)))
        return rows

    def ensure_schema(self) -> None:
        if not self.configured or self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            statements = [
                """
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    analysis_date TEXT NOT NULL,
                    lookback_days INTEGER NOT NULL,
                    output_language TEXT NOT NULL,
                    research_depth TEXT NOT NULL,
                    model TEXT NOT NULL,
                    signal TEXT,
                    elapsed_seconds REAL,
                    user_email TEXT NOT NULL,
                    user_sub TEXT,
                    created_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS analysis_sections (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    section_key TEXT NOT NULL,
                    title TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    team TEXT NOT NULL,
                    display_order INTEGER NOT NULL,
                    markdown TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES analysis_runs(id) ON DELETE CASCADE
                )
                """,
                "CREATE INDEX IF NOT EXISTS idx_analysis_runs_user_created ON analysis_runs(user_email, created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_analysis_sections_run_order ON analysis_sections(run_id, display_order)",
            ]
            for statement in statements:
                self._execute(statement)
            self._schema_ready = True

    def save_analysis(
        self,
        request: AnalysisRequest,
        user: dict,
        symbol: str,
        signal: str,
        elapsed_seconds: float,
        sections: list[dict],
    ) -> str | None:
        if not self.configured or not sections:
            return None
        self.ensure_schema()
        run_id = request.run_id or f"history-{uuid.uuid4().hex}"
        created_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        self._execute(
            """
            INSERT INTO analysis_runs (
                id, symbol, asset_type, analysis_date, lookback_days, output_language,
                research_depth, model, signal, elapsed_seconds, user_email, user_sub, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                symbol = excluded.symbol,
                asset_type = excluded.asset_type,
                analysis_date = excluded.analysis_date,
                lookback_days = excluded.lookback_days,
                output_language = excluded.output_language,
                research_depth = excluded.research_depth,
                model = excluded.model,
                signal = excluded.signal,
                elapsed_seconds = excluded.elapsed_seconds,
                user_email = excluded.user_email,
                user_sub = excluded.user_sub,
                created_at = excluded.created_at
            """,
            [
                run_id,
                symbol,
                request.asset_type,
                request.analysis_date,
                request.lookback_days,
                request.output_language,
                request.research_depth,
                request.model,
                signal,
                elapsed_seconds,
                user.get("email"),
                user.get("sub"),
                created_at,
            ],
        )
        self._execute("DELETE FROM analysis_sections WHERE run_id = ?", [run_id])
        for index, section in enumerate(sections):
            markdown = str(section.get("markdown") or "").strip()
            if not markdown:
                continue
            section_id = hashlib.sha1(f"{run_id}:{section.get('section_key')}".encode()).hexdigest()
            self._execute(
                """
                INSERT INTO analysis_sections (
                    id, run_id, section_key, title, agent, team, display_order, markdown, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    section_id,
                    run_id,
                    section.get("section_key"),
                    section.get("title"),
                    section.get("agent"),
                    section.get("team"),
                    index,
                    markdown,
                    created_at,
                ],
            )
        return run_id

    def list_runs(self, user_email: str, limit: int = 40) -> list[dict]:
        self.ensure_schema()
        return self._query_rows(
            """
            SELECT
                r.id, r.symbol, r.asset_type, r.analysis_date, r.lookback_days,
                r.output_language, r.research_depth, r.model, r.signal,
                r.elapsed_seconds, r.created_at, COUNT(s.id) AS section_count
            FROM analysis_runs r
            LEFT JOIN analysis_sections s ON s.run_id = r.id
            WHERE r.user_email = ?
            GROUP BY r.id
            ORDER BY r.created_at DESC
            LIMIT ?
            """,
            [user_email, limit],
        )

    def get_run(self, run_id: str, user_email: str) -> dict | None:
        self.ensure_schema()
        runs = self._query_rows(
            """
            SELECT id, symbol, asset_type, analysis_date, lookback_days,
                output_language, research_depth, model, signal, elapsed_seconds, created_at
            FROM analysis_runs
            WHERE id = ? AND user_email = ?
            LIMIT 1
            """,
            [run_id, user_email],
        )
        if not runs:
            return None
        sections = self._query_rows(
            """
            SELECT section_key, title, agent, team, markdown, created_at
            FROM analysis_sections
            WHERE run_id = ?
            ORDER BY display_order ASC
            """,
            [run_id],
        )
        return {"item": runs[0], "sections": sections}


HISTORY_STORE = TursoHistoryStore(TURSO_DATABASE_URL, TURSO_AUTH_TOKEN)


@app.on_event("startup")
async def initialize_history_database() -> None:
    if not HISTORY_STORE.configured:
        logger.warning("Turso history database is not configured; history persistence is disabled.")
        return
    await asyncio.to_thread(HISTORY_STORE.ensure_schema)
    logger.info("Turso history database schema is ready.")


def _extract_auth_token(request: Request) -> str:
    bearer = request.headers.get("Authorization", "").strip()
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return request.headers.get("X-Google-ID-Token", "").strip()


def _validate_google_id_token(token: str) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Sign in with Google before running analysis.")

    token_hash = hashlib.sha256(token.encode("utf-8", errors="ignore")).hexdigest()
    now = time.time()
    with AUTH_CACHE_LOCK:
        cached = AUTH_CACHE.get(token_hash)
        if cached and cached[0] > now:
            return cached[1]

    try:
        response = requests.get(GOOGLE_TOKENINFO_URL, params={"id_token": token}, timeout=8)
    except requests.RequestException as exc:
        raise HTTPException(status_code=401, detail="Could not verify Google sign-in token.") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Google sign-in token is invalid or expired.")

    payload = response.json()
    email = str(payload.get("email") or "").strip().lower()
    email_verified = str(payload.get("email_verified") or "").lower() == "true"
    audience = str(payload.get("aud") or "").strip()
    if GOOGLE_CLIENT_ID and audience != GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=401, detail="Google sign-in token was issued for a different client.")
    if not email or not email_verified:
        raise HTTPException(status_code=403, detail="Google account email is not verified.")
    if email != GOOGLE_ALLOWED_EMAIL:
        raise HTTPException(status_code=403, detail="This Google account is not allowed to run analysis.")

    user = {
        "email": email,
        "sub": str(payload.get("sub") or ""),
        "name": str(payload.get("name") or ""),
        "picture": str(payload.get("picture") or ""),
        "authorized": True,
    }
    try:
        expires_at = float(payload.get("exp") or 0)
    except (TypeError, ValueError):
        expires_at = now + 300
    with AUTH_CACHE_LOCK:
        AUTH_CACHE[token_hash] = (max(now + 30, min(expires_at, now + 3600)), user)
    return user


async def require_authorized_user(request: Request) -> dict:
    token = _extract_auth_token(request)
    return await asyncio.to_thread(_validate_google_id_token, token)


def build_history_sections(final_state: dict) -> list[dict]:
    sections: list[dict] = []
    for section_key, meta in SECTION_META.items():
        markdown = str(final_state.get(section_key) or "").strip()
        if markdown:
            sections.append(
                {
                    "section_key": section_key,
                    "title": meta["title"],
                    "agent": meta["agent"],
                    "team": meta["team"],
                    "markdown": markdown,
                }
            )

    investment = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    extra_sections = [
        ("bull_research", "Bull Research", "Bull Researcher", "Research Team", investment.get("bull_history")),
        ("bear_research", "Bear Research", "Bear Researcher", "Research Team", investment.get("bear_history")),
        ("research_debate", "Research Debate", "Research Team", "Research Team", investment.get("history")),
        ("aggressive_risk", "Aggressive Risk", "Aggressive Analyst", "Risk Team", risk.get("aggressive_history") or risk.get("current_aggressive_response")),
        ("conservative_risk", "Conservative Risk", "Conservative Analyst", "Risk Team", risk.get("conservative_history") or risk.get("current_conservative_response")),
        ("neutral_risk", "Neutral Risk", "Neutral Analyst", "Risk Team", risk.get("neutral_history") or risk.get("current_neutral_response")),
        ("risk_debate", "Risk Debate", "Risk Team", "Risk Team", risk.get("history")),
    ]
    for section_key, title, agent, team, markdown in extra_sections:
        markdown = str(markdown or "").strip()
        if markdown:
            sections.append(
                {
                    "section_key": section_key,
                    "title": title,
                    "agent": agent,
                    "team": team,
                    "markdown": markdown,
                }
            )
    return sections


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
    return list(selected_analysts)


def _trim_text(value: str, limit: int) -> str:
    if limit <= 0 or len(value) <= limit:
        return value
    suffix = "\n\n[truncated for constrained runtime]"
    safe_limit = max(0, limit - len(suffix))
    return value[:safe_limit].rstrip() + suffix


def _try_reserve_analysis_slot() -> bool:
    global ACTIVE_ANALYSIS_COUNT
    with ACTIVE_ANALYSIS_LOCK:
        if ACTIVE_ANALYSIS_COUNT >= ANALYSIS_MAX_CONCURRENT_RUNS:
            return False
        ACTIVE_ANALYSIS_COUNT += 1
        return True


def _release_analysis_slot() -> None:
    global ACTIVE_ANALYSIS_COUNT
    with ACTIVE_ANALYSIS_LOCK:
        if ACTIVE_ANALYSIS_COUNT > 0:
            ACTIVE_ANALYSIS_COUNT -= 1


def build_analysis_runtime_profile(request: AnalysisRequest) -> dict:
    requested_rounds = RESEARCH_DEPTH_OPTIONS[request.research_depth]["rounds"]
    return {
        "requested_rounds": requested_rounds,
        "effective_rounds": requested_rounds,
        "llm_max_tokens": ANALYSIS_LLM_MAX_TOKENS,
    }


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


def build_analysis_config(request: AnalysisRequest, settings: dict, runtime_profile: dict) -> dict:
    config = deepcopy(DEFAULT_CONFIG)
    config.update(
        {
            "llm_provider": settings["provider"],
            "quick_think_llm": request.model,
            "deep_think_llm": request.model,
            "backend_url": settings["base_url"],
            "output_language": request.output_language,
            "max_debate_rounds": runtime_profile["effective_rounds"],
            "max_risk_discuss_rounds": runtime_profile["effective_rounds"],
            "global_news_lookback_days": request.lookback_days,
            "crypto_market_lookback_days": request.lookback_days,
            "analysis_llm_max_tokens": runtime_profile["llm_max_tokens"],
            "checkpoint_enabled": request.checkpoint_enabled,
            "memory_log_path": None,
            "persist_analysis_artifacts": False,
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
            content = _trim_text(
                _normalize_message_content(getattr(message, "content", "")),
                ANALYSIS_TRACE_CHAR_LIMIT,
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
                        "content": "\n".join(_tool_call_summary(tool_call) for tool_call in tool_calls),
                    },
                )
            content = _trim_text(
                _normalize_message_content(getattr(message, "content", "")),
                ANALYSIS_TRACE_CHAR_LIMIT,
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
    user: dict,
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
    runtime_profile = build_analysis_runtime_profile(request)

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
        effective_depth_rounds=runtime_profile["effective_rounds"],
        llm_max_tokens=runtime_profile["llm_max_tokens"],
        resource_constrained=RESOURCE_CONSTRAINED_MODE,
        memory_limit_mb=_memory_limit_mb(),
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

    config = build_analysis_config(request, settings, runtime_profile)
    emit_analysis_log(
        "Building TradingAgents graph.",
        "graph_setup",
        provider=settings["provider"],
        model=request.model,
        depth_rounds=runtime_profile["effective_rounds"],
        max_tokens=runtime_profile["llm_max_tokens"],
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
            "depth_rounds": runtime_profile["effective_rounds"],
            "model": request.model,
            "llm_max_tokens": runtime_profile["llm_max_tokens"],
            "resource_constrained": RESOURCE_CONSTRAINED_MODE,
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

    tradingagents_logger = logging.getLogger("tradingagents")
    log_capture: AnalysisLoggingHandler | None = None
    stdout_stream: AnalysisLogStream | None = None
    stderr_stream: AnalysisLogStream | None = None
    stdout_redirect = None
    stderr_redirect = None
    if ANALYSIS_VERBOSE_RUNTIME_LOGS:
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
            for node_name, update in iter_graph_state_updates(chunk):
                chunk_index += 1
                updated_keys = merge_graph_state_update(final_state, update)
                current_snapshot = extract_runtime_snapshot(final_state)
                current_agent = detect_current_agent(previous_snapshot, current_snapshot) or current_agent
                current_status = build_status_snapshot(current_snapshot, filtered_analysts, current_agent)
                emit_analysis_log(
                    "Graph emitted a state update.",
                    current_status["phase"],
                    chunk_index=chunk_index,
                    graph_node=node_name,
                    current_agent=current_agent,
                    updated_keys=updated_keys,
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
        if config.get("persist_analysis_artifacts"):
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
        signal = graph.process_signal(final_state["final_trade_decision"])
        elapsed_seconds = round(time.time() - started_at, 2)
        history_id = None
        history_sections = build_history_sections(final_state)
        if HISTORY_STORE.configured:
            try:
                history_id = HISTORY_STORE.save_analysis(
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
    analysis_request: AnalysisRequest,
    http_request: Request,
    user: dict,
    reserved_slot: bool = False,
) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=ANALYSIS_SSE_QUEUE_MAXSIZE)
    stream_started_at = time.time()
    cancel_event = threading.Event()

    if analysis_request.run_id:
        with ACTIVE_ANALYSIS_LOCK:
            ACTIVE_ANALYSIS_CANCEL_EVENTS[analysis_request.run_id] = cancel_event

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
        asyncio.run_coroutine_threadsafe(
            queue_sse_item(_sse(event, data), event in DROPPABLE_SSE_EVENTS),
            loop,
        ).result()

    def worker() -> None:
        try:
            run_trading_analysis(analysis_request, emit, user, cancel_event)
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
        if reserved_slot:
            _release_analysis_slot()
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
        "resource_constrained": RESOURCE_CONSTRAINED_MODE,
        "analysis_limits": {
            "cpu_threads": ANALYSIS_CPU_THREADS,
            "max_concurrent_runs": ANALYSIS_MAX_CONCURRENT_RUNS,
            "llm_max_tokens": ANALYSIS_LLM_MAX_TOKENS,
        },
        "modes": ["analysis", "chat"],
    }


@app.get("/api/config")
async def public_config() -> dict:
    settings = resolve_minimax_settings()
    return {
        "configured": settings["configured"],
        "provider": settings["provider"] or "minimax",
        "default_model": DEFAULT_MODEL,
        "analysis_defaults": {
            "symbol": "BTC-USDT",
            "asset_type": DEFAULT_ASSET_TYPE,
            "analysis_date": date.today().isoformat(),
            "lookback_days": DEFAULT_ANALYSIS_LOOKBACK_DAYS,
            "output_language": DEFAULT_OUTPUT_LANGUAGE,
            "selected_analysts": DEFAULT_SELECTED_ANALYSTS,
            "research_depth": DEFAULT_RESEARCH_DEPTH,
            "model": DEFAULT_MODEL,
            "checkpoint_enabled": DEFAULT_CHECKPOINT_ENABLED,
        },
        "auth": {
            "google_client_id": GOOGLE_CLIENT_ID,
        },
        "history": {
            "configured": HISTORY_STORE.configured,
            "schema_ready": HISTORY_STORE._schema_ready,
        },
        "trading_view": {
            "symbol": os.getenv("TRADING_VIEW_SYMBOL", "BINANCE:BTCUSDT"),
            "interval": os.getenv("TRADING_VIEW_INTERVAL", "60"),
            "symbols": ["BINANCE:BTCUSDT", "BINANCE:ETHUSDT", "BINANCE:SOLUSDT", "BINANCE:XRPUSDT"],
            "intervals": ["5", "15", "60", "240", "D"],
        },
    }


@app.get("/api/auth/me")
async def auth_me(http_request: Request) -> dict:
    return await require_authorized_user(http_request)


@app.get("/api/history")
async def list_analysis_history(http_request: Request, limit: int = 40) -> dict:
    user = await require_authorized_user(http_request)
    if not HISTORY_STORE.configured:
        raise HTTPException(status_code=503, detail="Turso history database is not configured.")
    safe_limit = max(1, min(int(limit or 40), 100))
    items = await asyncio.to_thread(HISTORY_STORE.list_runs, user["email"], safe_limit)
    return {"items": items, "configured": True}


@app.get("/api/history/{run_id}")
async def get_analysis_history(run_id: str, http_request: Request) -> dict:
    user = await require_authorized_user(http_request)
    if not HISTORY_STORE.configured:
        raise HTTPException(status_code=503, detail="Turso history database is not configured.")
    result = await asyncio.to_thread(HISTORY_STORE.get_run, run_id, user["email"])
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis history item was not found.")
    return result


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
    user = await require_authorized_user(http_request)
    if not _try_reserve_analysis_slot():
        raise HTTPException(
            status_code=429,
            detail=(
                "Analysis capacity is full for the current deployment size. "
                "Wait for the active run to finish before starting another."
            ),
        )

    try:
        return StreamingResponse(
            generate_analysis_stream(analysis_request, http_request, user, reserved_slot=True),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception:
        _release_analysis_slot()
        raise


if __name__ == "__main__":
    import uvicorn

    port = _env_int("PORT", 8000)
    uvicorn.run(app, host="0.0.0.0", port=port)