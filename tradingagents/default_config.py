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
    "TRADINGAGENTS_CHECKPOINT_ENABLED":   "checkpoint_enabled",
    "TRADINGAGENTS_BENCHMARK_TICKER":     "benchmark_ticker",
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
    # Checkpoint/resume: when True, LangGraph saves state after each node
    # so a crashed run can resume from the last successful step.
    "checkpoint_enabled": False,
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "English",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "analyst_concurrency_limit": 1,
    # News / data fetching parameters tuned for crypto-first analysis.
    # Token-level news still matters, but macro flow should stay compact so
    # prompts can reserve more room for market structure and debate.
    "news_article_limit": 12,             # max articles per symbol-specific news pull
    "global_news_article_limit": 8,       # max articles for macro / cross-asset news
    "global_news_lookback_days": 7,       # macro news lookback window
    # Crypto market-data policy: select the densest single timeframe whose
    # candle count still stays below the hard memory ceiling for the active
    # lookback window.
    "crypto_market_lookback_days": 7,
    "crypto_market_max_candles": 199,
    # High-trust reference sites that analysts should prioritize when the
    # current model/runtime has web access or can otherwise cross-check live
    # market context. This is a preference list, not a whitelist.
    "preferred_reference_sources": [
        {
            "name": "CoinGlass",
            "url": "https://www.coinglass.com/",
            "focus": "Crypto derivatives positioning, liquidation data, funding, and market-structure dashboards.",
        },
        {
            "name": "VNWallStreet",
            "url": "https://vnwallstreet.com/",
            "focus": "Real-time event flow and market-moving calendar context.",
        },
        {
            "name": "TradingEconomics",
            "url": "https://tradingeconomics.com/",
            "focus": "Macro releases, rates, liquidity, and cross-asset risk context that can spill directly into crypto.",
        },
    ],
    # Search queries used by get_global_news for crypto-relevant macro and
    # cross-asset headlines. Keep macro flow because liquidity, rates, and
    # regulation still move crypto even when no stock analysis is performed.
    "global_news_queries": [
        "Bitcoin Ethereum crypto ETF flows market structure",
        "Federal Reserve interest rates inflation dollar liquidity risk assets",
        "stablecoin regulation SEC Congress crypto banking policy",
        "crypto exchange flows liquidations funding open interest miners",
        "Nasdaq Treasury yields geopolitics recession cross-asset volatility",
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
