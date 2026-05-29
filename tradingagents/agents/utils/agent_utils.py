from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.crypto_market_tools import (
    get_crypto_indicators,
    get_crypto_ohlcv
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, research manager, trader, and
    portfolio manager — so a non-English run produces a fully localized
    report rather than a mix of languages.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def get_preferred_reference_sources_instruction() -> str:
    """Return a prompt hint for user-trusted reference sites when configured."""
    from tradingagents.dataflows.config import get_config

    sources = get_config().get("preferred_reference_sources") or []
    if not sources:
        return ""

    lines: list[str] = []
    for source in sources:
        if isinstance(source, dict):
            name = str(source.get("name") or source.get("url") or "Source").strip()
            url = str(source.get("url") or "").strip()
            focus = str(source.get("focus") or source.get("description") or "").strip()
        else:
            name = str(source).strip()
            url = ""
            focus = ""

        line = f"- {name}"
        if url:
            line += f" ({url})"
        if focus:
            line += f": {focus}"
        lines.append(line)

    return (
        " When MiniMax MCP browsing is available through the current model or tools, use the exact"
        " tool name web_search to retrieve or cross-check each of the following user-trusted reference"
        " sites before writing final market-facing conclusions. Do not invent alternate tool names"
        " such as websearch. You are not restricted to these sites; after checking them, use any"
        " other credible sources or broader web search when useful."
        " If a trusted source is unreachable, state that limitation:\n"
        + "\n".join(lines)
    )


def build_instrument_context(ticker: str, asset_type: str = "crypto") -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    instrument_label = "asset" if asset_type == "crypto" else "instrument"
    extra_hint = (
        " Treat it as a crypto asset rather than a company, and do not assume company fundamentals are available."
        if asset_type == "crypto"
        else ""
    )
    return (
        f"The {instrument_label} to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving the crypto pair suffix (e.g. `-USDT`, `-USD`, or `/USDT`)."
        + extra_hint
    )


def get_coinglass_context_instruction(
    state: dict,
    packages: list[str] | tuple[str, ...] | None = None,
    char_limit: int = 4800,
) -> str:
    """Return backend-prefetched CoinGlass context for prompts."""
    package_contexts = state.get("coinglass_package_contexts") or {}
    context_parts: list[str] = []
    if packages and isinstance(package_contexts, dict):
        for package in packages:
            context = str(package_contexts.get(package) or "").strip()
            if context:
                context_parts.append(context)

    context = "\n\n".join(context_parts).strip()
    if not context:
        context = str(state.get("coinglass_context") or "").strip()
    if not context:
        return (
            "\n\nCoinGlass high-value context: unavailable for this run. "
            "Do not invent CoinGlass metrics; rely on other available evidence."
        )

    if char_limit > 0 and len(context) > char_limit:
        context = context[: max(0, char_limit - 14)].rstrip() + "\n[truncated]"

    return (
        "\n\nCoinGlass high-value context prefetched by the backend for this same analysis run. "
        "Use it as source-backed market evidence, mention gaps when an endpoint failed, and do not call CoinGlass again:\n"
        f"{context}"
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
