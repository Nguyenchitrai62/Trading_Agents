from __future__ import annotations

import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"
ENTERPRISE_ENV_FILE = ROOT_DIR / ".env.enterprise"
CPU_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)
DEFAULT_ANALYSTS = ("market", "social", "news", "fundamentals")
APP_TITLE = "TradingAgents Analysis API"
APP_VERSION = "0.1.1"
DEFAULT_MODEL = "MiniMax-M2.5"
DEFAULT_ANALYSIS_LOOKBACK_DAYS = 7
DEFAULT_ASSET_TYPE = "crypto"
DEFAULT_OUTPUT_LANGUAGE = "Vietnamese"
DEFAULT_RESEARCH_DEPTH = "medium"
DEFAULT_CHECKPOINT_ENABLED = False
DEFAULT_HISTORY_PAGE_SIZE = 10
DEFAULT_HISTORY_PUBLIC_READ = True
DEFAULT_HISTORY_ACCESS_DAYS = 7
DEFAULT_ANALYSIS_LLM_MAX_TOKENS = 16384
DEFAULT_ADMIN_EMAILS = ("trainguyenchi30@gmail.com",)
DEFAULT_TRADING_VIEW_SYMBOL = "BINANCE:BTCUSDT"
DEFAULT_TRADING_VIEW_INTERVAL = "60"
DEFAULT_TRADING_VIEW_SYMBOLS = (
    "BINANCE:BTCUSDT",
    "BINANCE:ETHUSDT",
    "BINANCE:SOLUSDT",
    "BINANCE:XRPUSDT",
)
DEFAULT_COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com"
DEFAULT_COINGLASS_TIMEOUT_SECONDS = 10.0
DEFAULT_COINGLASS_CONTEXT_CHAR_LIMIT = 0
DEFAULT_COINGLASS_PACKAGE_CONTEXT_CHAR_LIMIT = 0
DEFAULT_COINGLASS_REQUEST_INTERVAL_SECONDS = 0.05
RESEARCH_DEPTH_OPTIONS = {
    "quick": {
        "label": "Quick",
        "rounds": 1,
        "mcp_tool_rounds": 3,
        "description": "Fast scan with minimal debate and one extra live web cross-check round.",
    },
    "medium": {
        "label": "Medium",
        "rounds": 3,
        "mcp_tool_rounds": 5,
        "description": "Balanced research depth with broader live web validation for regular analysis.",
    },
    "deep": {
        "label": "Deep",
        "rounds": 5,
        "mcp_tool_rounds": 7,
        "description": "More debate rounds and deeper live web validation before the final decision.",
    },
}
SECTION_META = {
    "market_report": {
        "title": "Market Analysis",
        "agent": "Market Analyst",
        "team": "Analyst Team",
    },
    "sentiment_report": {
        "title": "Social Analysis",
        "agent": "Social Analyst",
        "team": "Analyst Team",
    },
    "news_report": {
        "title": "News Analysis",
        "agent": "News Analyst",
        "team": "Analyst Team",
    },
    "flow_report": {
        "title": "Flow Analysis",
        "agent": "Flow Analyst",
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
    "verification_report": {
        "title": "Verification Report",
        "agent": "Verifier",
        "team": "Portfolio Management",
    },
}


def load_environment() -> None:
    load_dotenv(ENV_FILE)
    load_dotenv(ENTERPRISE_ENV_FILE, override=False)


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


def _env_csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _coinglass_api_key() -> str:
    names = ("COINGLASS_API_KEY", "COINGLASS-API-KEY", "CG_API_KEY", "CG-API-KEY")
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    for env_file in (ENV_FILE, ENTERPRISE_ENV_FILE):
        try:
            lines = env_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, raw_value = stripped.split("=", 1)
            if key.strip() not in names:
                continue
            value = raw_value.strip().strip("\"'")
            if value:
                return value
    return ""


def _normalize_origin(value: str) -> str:
    origin = value.strip()
    if origin == "*":
        return origin
    return origin.rstrip("/")


def _configured_cors_origins() -> list[str]:
    configured = [_normalize_origin(origin) for origin in _env_csv("CORS_ALLOW_ORIGINS")]
    if configured:
        return configured

    frontend_origin = _normalize_origin(
        os.getenv("FRONTEND_ORIGIN", "")
        or os.getenv("FRONTEND_URL", "")
        or os.getenv("PUBLIC_FRONTEND_URL", "")
    )
    defaults = [
        "https://crypto.nguyenchitrai.id.vn",
        "https://www.lm.io.vn",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]
    if frontend_origin:
        defaults.insert(0, frontend_origin)
    return list(dict.fromkeys(defaults))


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


def _apply_cpu_thread_defaults() -> int:
    thread_value = str(_configured_cpu_threads())
    for name in CPU_THREAD_ENV_VARS:
        os.environ.setdefault(name, thread_value)
    return int(thread_value)


def _derive_auth_session_secret() -> tuple[str, bool]:
    configured_secret = os.getenv("AUTH_SESSION_SECRET", "").strip() or os.getenv("SESSION_SECRET", "").strip()
    if configured_secret:
        return configured_secret, True

    server_secret_seed = "|".join(
        value
        for value in (
            os.getenv("TURSO_AUTH_TOKEN", "").strip(),
            os.getenv("MINIMAX_API_KEY", "").strip(),
            os.getenv("MINIMAX_CN_API_KEY", "").strip(),
        )
        if value
    )
    if server_secret_seed:
        return hashlib.sha256(server_secret_seed.encode("utf-8")).hexdigest(), True

    return secrets.token_hex(32), False


@dataclass(frozen=True)
class BackendSettings:
    root_dir: Path
    frontend_dir: Path
    image_dir: Path
    index_file: Path
    app_title: str
    app_version: str
    log_level: str
    default_model: str
    default_analysis_lookback_days: int
    default_asset_type: str
    default_output_language: str
    default_selected_analysts: tuple[str, ...]
    default_research_depth: str
    default_checkpoint_enabled: bool
    default_history_access_days: int
    admin_emails: frozenset[str]
    auth_restrict_to_allowed_emails: bool
    google_allowed_email: str
    google_allowed_emails: frozenset[str]
    google_client_id: str
    google_tokeninfo_url: str
    turso_database_url: str
    turso_auth_token: str
    resource_constrained_mode: bool
    analysis_cpu_threads: int
    analysis_default_concurrent_runs: int
    stream_heartbeat_seconds: float
    analysis_verbose_runtime_logs: bool
    analysis_max_concurrent_runs: int
    analysis_sse_queue_maxsize: int
    analysis_llm_max_tokens: int
    analysis_trace_char_limit: int
    auth_cache_max_entries: int
    auth_session_secret: str
    auth_session_persistent: bool
    auth_session_ttl_seconds: int
    history_public_read: bool
    history_page_size: int
    droppable_sse_events: frozenset[str]
    cors_allow_origins: tuple[str, ...]
    allow_all_origins: bool
    minimax_base_url: str
    minimax_api_key: str
    minimax_cn_api_key: str
    coinglass_enabled: bool
    coinglass_api_key: str
    coinglass_base_url: str
    coinglass_timeout_seconds: float
    coinglass_context_char_limit: int
    coinglass_package_context_char_limit: int
    coinglass_request_interval_seconds: float
    trading_view_symbol: str
    trading_view_interval: str
    trading_view_symbols: tuple[str, ...]
    port: int

    @classmethod
    def from_env(cls) -> "BackendSettings":
        analysis_cpu_threads = _apply_cpu_thread_defaults()
        auth_session_secret, auth_session_persistent = _derive_auth_session_secret()
        memory_limit_mb = _memory_limit_mb() or 0
        analysis_default_concurrent_runs = (
            1 if memory_limit_mb and memory_limit_mb < 1024 else min(2, analysis_cpu_threads)
        )
        cors_allow_origins = tuple(_configured_cors_origins())
        allow_all_origins = not cors_allow_origins or cors_allow_origins == ("*",)
        default_model = os.getenv("MINIMAX_MODEL", "").strip() or DEFAULT_MODEL
        admin_emails = frozenset(
            email.lower() for email in _env_csv("ADMIN_EMAILS", ",".join(DEFAULT_ADMIN_EMAILS))
        )
        google_allowed_email = os.getenv("GOOGLE_ALLOWED_EMAIL", "").strip().lower()
        google_allowed_emails = frozenset(
            email.lower() for email in _env_csv("GOOGLE_ALLOWED_EMAILS", google_allowed_email)
        )
        trading_view_symbols = tuple(_env_csv("TRADING_VIEW_SYMBOLS")) or DEFAULT_TRADING_VIEW_SYMBOLS

        return cls(
            root_dir=ROOT_DIR,
            frontend_dir=ROOT_DIR / "FE",
            image_dir=ROOT_DIR / "image",
            index_file=ROOT_DIR / "index.html",
            app_title=APP_TITLE,
            app_version=APP_VERSION,
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
            default_model=default_model,
            default_analysis_lookback_days=DEFAULT_ANALYSIS_LOOKBACK_DAYS,
            default_asset_type=DEFAULT_ASSET_TYPE,
            default_output_language=DEFAULT_OUTPUT_LANGUAGE,
            default_selected_analysts=DEFAULT_ANALYSTS,
            default_research_depth=os.getenv("DEFAULT_RESEARCH_DEPTH", DEFAULT_RESEARCH_DEPTH).strip() or DEFAULT_RESEARCH_DEPTH,
            default_checkpoint_enabled=DEFAULT_CHECKPOINT_ENABLED,
            default_history_access_days=max(1, _env_int("DEFAULT_HISTORY_ACCESS_DAYS", DEFAULT_HISTORY_ACCESS_DAYS)),
            admin_emails=admin_emails,
            auth_restrict_to_allowed_emails=_env_bool("AUTH_RESTRICT_TO_ALLOWED_EMAILS", False),
            google_allowed_email=google_allowed_email,
            google_allowed_emails=google_allowed_emails,
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            google_tokeninfo_url="https://oauth2.googleapis.com/tokeninfo",
            turso_database_url=os.getenv("TURSO_DATABASE_URL", "").strip(),
            turso_auth_token=os.getenv("TURSO_AUTH_TOKEN", "").strip(),
            resource_constrained_mode=False,
            analysis_cpu_threads=analysis_cpu_threads,
            analysis_default_concurrent_runs=analysis_default_concurrent_runs,
            stream_heartbeat_seconds=max(1.0, _env_float("ANALYSIS_STREAM_HEARTBEAT_SECONDS", 2.0)),
            analysis_verbose_runtime_logs=_env_bool("ANALYSIS_VERBOSE_RUNTIME_LOGS", True),
            analysis_max_concurrent_runs=max(
                1,
                _env_int("ANALYSIS_MAX_CONCURRENT_RUNS", analysis_default_concurrent_runs),
            ),
            analysis_sse_queue_maxsize=max(
                8,
                _env_int("ANALYSIS_SSE_QUEUE_MAXSIZE", 128),
            ),
            analysis_llm_max_tokens=max(
                512,
                DEFAULT_ANALYSIS_LLM_MAX_TOKENS,
            ),
            analysis_trace_char_limit=max(0, _env_int("ANALYSIS_TRACE_CHAR_LIMIT", 0)),
            auth_cache_max_entries=max(8, _env_int("AUTH_CACHE_MAX_ENTRIES", 256)),
            auth_session_secret=auth_session_secret,
            auth_session_persistent=auth_session_persistent,
            auth_session_ttl_seconds=max(3600, _env_int("AUTH_SESSION_TTL_SECONDS", 60 * 60 * 24 * 7)),
            history_public_read=DEFAULT_HISTORY_PUBLIC_READ,
            history_page_size=max(1, _env_int("HISTORY_PAGE_SIZE", DEFAULT_HISTORY_PAGE_SIZE)),
            droppable_sse_events=frozenset({"analysis_log", "agent_trace"}),
            cors_allow_origins=cors_allow_origins,
            allow_all_origins=allow_all_origins,
            minimax_base_url=os.getenv("MINIMAX_BASE_URL", "").strip(),
            minimax_api_key=os.getenv("MINIMAX_API_KEY", "").strip(),
            minimax_cn_api_key=os.getenv("MINIMAX_CN_API_KEY", "").strip(),
            coinglass_enabled=_env_bool("COINGLASS_ENABLED", True),
            coinglass_api_key=_coinglass_api_key(),
            coinglass_base_url=os.getenv("COINGLASS_BASE_URL", DEFAULT_COINGLASS_BASE_URL).strip()
            or DEFAULT_COINGLASS_BASE_URL,
            coinglass_timeout_seconds=max(
                1.0,
                _env_float("COINGLASS_TIMEOUT_SECONDS", DEFAULT_COINGLASS_TIMEOUT_SECONDS),
            ),
            coinglass_context_char_limit=max(
                0,
                _env_int("COINGLASS_CONTEXT_CHAR_LIMIT", DEFAULT_COINGLASS_CONTEXT_CHAR_LIMIT),
            ),
            coinglass_package_context_char_limit=max(
                0,
                _env_int("COINGLASS_PACKAGE_CONTEXT_CHAR_LIMIT", DEFAULT_COINGLASS_PACKAGE_CONTEXT_CHAR_LIMIT),
            ),
            coinglass_request_interval_seconds=max(
                0.0,
                _env_float("COINGLASS_REQUEST_INTERVAL_SECONDS", DEFAULT_COINGLASS_REQUEST_INTERVAL_SECONDS),
            ),
            trading_view_symbol=os.getenv("TRADING_VIEW_SYMBOL", DEFAULT_TRADING_VIEW_SYMBOL),
            trading_view_interval=os.getenv("TRADING_VIEW_INTERVAL", DEFAULT_TRADING_VIEW_INTERVAL),
            trading_view_symbols=trading_view_symbols,
            port=_env_int("PORT", 8000),
        )


def configure_logging(log_level: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    return logging.getLogger("tradingagents.app")


def resolve_minimax_settings(settings: BackendSettings | None = None) -> dict:
    active_settings = settings or SETTINGS
    if active_settings.minimax_api_key:
        return {
            "configured": True,
            "provider": "minimax",
            "api_key": active_settings.minimax_api_key,
            "base_url": active_settings.minimax_base_url or "https://api.minimax.io/anthropic",
        }

    if active_settings.minimax_cn_api_key:
        return {
            "configured": True,
            "provider": "minimax-cn",
            "api_key": active_settings.minimax_cn_api_key,
            "base_url": active_settings.minimax_base_url or "https://api.minimaxi.com/anthropic",
        }

    return {
        "configured": False,
        "provider": None,
        "api_key": "",
        "base_url": active_settings.minimax_base_url or "https://api.minimax.io/anthropic",
    }


load_environment()
SETTINGS = BackendSettings.from_env()
logger = configure_logging(SETTINGS.log_level)
if not SETTINGS.auth_session_persistent:
    logger.warning(
        "AUTH_SESSION_SECRET is not configured and no server-side secret fallback was found. "
        "Frontend sessions will reset when the backend process restarts."
    )


__all__ = [
    "CPU_THREAD_ENV_VARS",
    "DEFAULT_ADMIN_EMAILS",
    "DEFAULT_ANALYSTS",
    "DEFAULT_COINGLASS_BASE_URL",
    "DEFAULT_HISTORY_ACCESS_DAYS",
    "RESEARCH_DEPTH_OPTIONS",
    "ROOT_DIR",
    "SECTION_META",
    "SETTINGS",
    "BackendSettings",
    "logger",
    "resolve_minimax_settings",
]
