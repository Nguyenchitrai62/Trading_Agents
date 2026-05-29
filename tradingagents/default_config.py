import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

# Single source of truth for env-var → config-key overrides. To expose
# a new config key for environment-based override, add a row here — no
# entry-point script changes required. Coercion is driven by the type
# of the existing default, so users can keep writing plain strings in
# their .env file.
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER":         "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM":       "deep_think_llm",
    "TRADINGAGENTS_QUICK_THINK_LLM":      "quick_think_llm",
    "TRADINGAGENTS_LLM_BACKEND_URL":      "backend_url",
    "TRADINGAGENTS_OUTPUT_LANGUAGE":      "output_language",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS":    "max_debate_rounds",
    "TRADINGAGENTS_MAX_RISK_ROUNDS":      "max_risk_discuss_rounds",
    "TRADINGAGENTS_ANALYST_CONCURRENCY_LIMIT": "analyst_concurrency_limit",
    "TRADINGAGENTS_CHECKPOINT_ENABLED":   "checkpoint_enabled",
    "TRADINGAGENTS_BENCHMARK_TICKER":     "benchmark_ticker",
    "MINIMAX_MCP_ENABLED":                 "minimax_mcp_enabled",
    "MINIMAX_MCP_COMMAND":                 "minimax_mcp_command",
    "MINIMAX_MCP_ARGS":                    "minimax_mcp_args",
    "MINIMAX_MCP_TOOL_NAMES":              "minimax_mcp_tool_names",
    "MINIMAX_MCP_MAX_TOOL_ROUNDS":         "minimax_mcp_max_tool_rounds",
    "MINIMAX_MCP_TOOL_RESULT_CHAR_LIMIT":  "minimax_mcp_tool_result_char_limit",
    "MINIMAX_MCP_CALL_TIMEOUT_SECONDS":    "minimax_mcp_call_timeout_seconds",
    "MINIMAX_MCP_LIST_TIMEOUT_SECONDS":    "minimax_mcp_list_timeout_seconds",
}


def _coerce(value: str, reference):
    """Coerce env-var string to the type of the existing default value."""
    if isinstance(reference, bool):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(reference, int) and not isinstance(reference, bool):
        return int(value)
    if isinstance(reference, float):
        return float(value)
    return value


def _apply_env_overrides(config: dict) -> dict:
    """Apply TRADINGAGENTS_* env vars to the config dict in-place."""
    for env_var, key in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None or raw == "":
            continue
        config[key] = _coerce(raw, config.get(key))
    return config


DEFAULT_CONFIG = _apply_env_overrides({
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_log_path": os.getenv("TRADINGAGENTS_MEMORY_LOG_PATH", os.path.join(_TRADINGAGENTS_HOME, "memory", "trading_memory.md")),
    # Optional cap on the number of resolved memory log entries. When set,
    # the oldest resolved entries are pruned once this limit is exceeded.
    # Pending entries are never pruned. None disables rotation entirely.
    "memory_log_max_entries": None,
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    # When None, each provider's client falls back to its own default endpoint
    # (api.openai.com for OpenAI, generativelanguage.googleapis.com for Gemini, ...).
    # The CLI overrides this per provider when the user picks one. Keeping a
    # provider-specific URL here would leak (e.g. OpenAI's /v1 was previously
    # being forwarded to Gemini, producing malformed request URLs).
    "backend_url": None,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # MiniMax MCP web tools. These are loaded from the MCP server used by
    # _test_call_mcp.py, but credentials and host always come from .env.
    "minimax_mcp_enabled": True,
    "minimax_mcp_command": "uvx",
    "minimax_mcp_args": "minimax-coding-plan-mcp -y",
    # Analysis graph is text-first; keep the MCP tool list focused on live
    # market retrieval so crypto runs spend tool budget on web evidence rather
    # than image capabilities.
    "minimax_mcp_tool_names": "web_search",
    # Max number of MCP tool_use -> tool_result cycles before the model must
    # stop calling tools and produce its best final answer.
    "minimax_mcp_max_tool_rounds": 6,
    # Set to 0 to disable truncation. When positive, each MCP tool result is
    # truncated to this many characters before being sent back to the model.
    "minimax_mcp_tool_result_char_limit": 0,
    "minimax_mcp_call_timeout_seconds": 120.0,
    "minimax_mcp_list_timeout_seconds": 60.0,
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Optional YYYY-MM-DD cutoff used by market-data tools. When set to a
    # past date, crypto OHLCV/indicator tools end their window at that date
    # instead of leaking current candles into historical analysis.
    "analysis_date": None,
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "analyst_concurrency_limit": 4,
    # News / data fetching parameters tuned for crypto-first analysis.
    # Article counts are left to the provider/tool defaults unless an agent
    # explicitly requests a limit through the tool interface.
    "global_news_lookback_days": 14,      # macro + crypto policy/news lookback window
    # Crypto market-data policy: fetch the full active lookback window at the
    # timeframe requested by the agent/tool call, paginating provider requests
    # when needed.
    "crypto_market_lookback_days": 14,
    # High-trust reference sites. When MiniMax MCP web_search is enabled,
    # the model is instructed to retrieve or cross-check every configured URL
    # before writing market-facing conclusions, then optionally search beyond
    # them for additional credible context. This is not a whitelist.
    "preferred_reference_sources": [
        {
            "name": "CoinGlass",
            "url": "https://www.coinglass.com/",
            "focus": "Crypto derivatives positioning, liquidation data, funding, and market-structure dashboards.",
        },
        {
            "name": "CryptoQuant",
            "url": "https://cryptoquant.com/",
            "focus": "Exchange flows, reserves, whale behavior, miner activity, and on-chain pressure signals.",
        },
        {
            "name": "SoSoValue",
            "url": "https://www.sosovalue.com/",
            "focus": "Spot ETF flows, sector rotation, and institutional allocation context for crypto assets.",
        },
        {
            "name": "TradingEconomics",
            "url": "https://tradingeconomics.com/",
            "focus": "Rates, liquidity, DXY, macro releases, and cross-asset risk context that spills directly into crypto.",
        },
    ],
    # Search queries used by get_global_news for crypto-relevant macro and
    # cross-asset headlines. Keep macro flow because liquidity, rates, and
    # regulation still move crypto even when no stock analysis is performed.
    "global_news_queries": [
        "Bitcoin Ethereum Solana crypto ETF flows open interest funding liquidations market structure",
        "Federal Reserve inflation Treasury yields DXY liquidity crypto risk assets macro",
        "stablecoin regulation SEC CFTC MiCA crypto banking policy exchange enforcement",
        "bitcoin miners hashrate difficulty exchange reserves whale flows on-chain accumulation distribution",
        "Binance Coinbase Bybit derivatives basis options skew perp funding crypto market sentiment",
    ],
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Kept for legacy compatibility and benchmark/reflection paths
        "crypto_market_apis": "ccxt",        # Options: ccxt
        "technical_indicators": "yfinance",  # Legacy fallback; primary crypto market work stays on ccxt
        "fundamental_data": "yfinance",      # Legacy fallback for any non-price contextual pulls
        "news_data": "yfinance",             # Primary news vendor; tool-level fallback extends this below
    },
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        "get_news": "yfinance,alpha_vantage",
        "get_global_news": "yfinance,alpha_vantage",
    },
    # Benchmark for alpha calculation in the reflection layer.
    # The product is now crypto-first, so BTC is the default baseline for
    # relative performance instead of SPY.
    "benchmark_ticker": "BTC-USD",
    "benchmark_map": {
        "":     "BTC-USD",  # fallback if explicit benchmark_ticker is disabled
    },
})
