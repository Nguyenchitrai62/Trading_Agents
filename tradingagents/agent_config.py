import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

# Single source of truth for env-var -> config-key overrides. To expose
# a new config key for environment-based override, add a row here — no
# entry-point script changes required. Coercion is driven by the type
# of the existing default, so users can keep writing plain strings in
# their .env file.
_ENV_OVERRIDES = {
    "TRADINGAGENTS_LLM_PROVIDER": "llm_provider",
    "TRADINGAGENTS_DEEP_THINK_LLM": "deep_think_llm",
    "TRADINGAGENTS_QUICK_THINK_LLM": "quick_think_llm",
    "TRADINGAGENTS_LLM_BACKEND_URL": "backend_url",
    "TRADINGAGENTS_OUTPUT_LANGUAGE": "output_language",
    "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "max_debate_rounds",
    "TRADINGAGENTS_MAX_RISK_ROUNDS": "max_risk_discuss_rounds",
    "TRADINGAGENTS_ANALYST_CONCURRENCY_LIMIT": "analyst_concurrency_limit",
    "TRADINGAGENTS_COINGLASS_OWNER_ANALYST": "coinglass_owner_analyst",
    "TRADINGAGENTS_COINGLASS_OWNER_AGENT_LABEL": "coinglass_owner_agent_label",
    "TRADINGAGENTS_COINGLASS_PROMPT_CHAR_LIMIT": "coinglass_prompt_char_limit",
    "TRADINGAGENTS_ONCHAIN_ENDPOINT_LLM_CONCURRENCY": "onchain_endpoint_llm_concurrency",
    "TRADINGAGENTS_CHECKPOINT_ENABLED": "checkpoint_enabled",
    "MINIMAX_MCP_ENABLED": "minimax_mcp_enabled",
    "MINIMAX_MCP_COMMAND": "minimax_mcp_command",
    "MINIMAX_MCP_ARGS": "minimax_mcp_args",
    "MINIMAX_MCP_TOOL_NAMES": "minimax_mcp_tool_names",
    "MINIMAX_MCP_MAX_TOOL_ROUNDS": "minimax_mcp_max_tool_rounds",
    "MINIMAX_MCP_TOOL_RESULT_CHAR_LIMIT": "minimax_mcp_tool_result_char_limit",
    "MINIMAX_MCP_CALL_TIMEOUT_SECONDS": "minimax_mcp_call_timeout_seconds",
    "MINIMAX_MCP_LIST_TIMEOUT_SECONDS": "minimax_mcp_list_timeout_seconds",
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
    "google_thinking_level": None,               # "high", "minimal", etc.
    "openai_quick_reasoning_effort": "max",      # "max", "high", "medium", "low"
    "openai_deep_reasoning_effort": "max",       # "max", "high", "medium", "low"
    "anthropic_effort": None,                    # "high", "medium", "low"
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
    # CoinGlass context is owned by the Onchain analyst branch.
    "coinglass_owner_analyst": "onchain",
    "coinglass_owner_agent_label": "Onchain Analyst",
    "onchain_endpoint_llm_concurrency": 3,
    "coinglass_prompt_char_limit": 50000,
    "coinglass_preview_sample_rows": 50,
    "coinglass_preview_recent_rows": 50,
    "coinglass_packages_by_role": {
        "market_analyst": (),
        "onchain_analyst": (
            "exchange_reserves",
            "institutional_flow",
            "derivatives_positioning",
            "funding_pressure",
            "liquidation_risk",
            "macro_cycle_context",
        ),
        "portfolio_manager": (),
        "verifier": (),
        "bull_researcher": (),
        "bear_researcher": (),
        "aggressive_risk": (),
        "conservative_risk": (),
        "neutral_risk": (),
    },
    # News / data fetching parameters tuned for crypto-first analysis.
    # Article counts are left to the provider/tool defaults unless an agent
    # explicitly requests a limit through the tool interface.
    "global_news_lookback_days": 14,      # macro + crypto policy/news lookback window
    # Crypto market-data policy: fetch the full active lookback window at the
    # timeframe requested by the agent/tool call, paginating provider requests
    # when needed.
    "crypto_market_lookback_days": 14,
    # High-trust reference sites for the analyst assigned to live web validation.
    # CoinGlass is handled through the backend API prefetch path above, so it is
    # intentionally not repeated here as a web-search target.
    # These are advisory anchors, not a per-agent requirement and not a whitelist.
    "preferred_reference_sources": [
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
})