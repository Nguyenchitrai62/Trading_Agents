from langchain_core.messages import HumanMessage, RemoveMessage

from tradingagents.agents.utils.crypto_market_tools import (
    get_crypto_indicators,
    get_crypto_ohlcv
)


_ANALYST_ROLE_ALIASES = {
    "market_analyst": ("market", "market_analyst"),
    "social_analyst": ("social", "sentiment", "social_analyst"),
    "news_analyst": ("news", "news_analyst"),
    "onchain_analyst": ("onchain", "onchain_analyst"),
}


def _normalize_role_key(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _role_aliases(role_key: str) -> set[str]:
    normalized = _normalize_role_key(role_key)
    aliases = {normalized} if normalized else set()
    aliases.update(_ANALYST_ROLE_ALIASES.get(normalized, ()))
    for canonical, values in _ANALYST_ROLE_ALIASES.items():
        if normalized in values:
            aliases.add(canonical)
            aliases.update(values)
    return aliases


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Applied to every agent whose output reaches the saved report —
    analysts, researchers, debaters, risk, verifier, and portfolio manager,
    so a non-English run produces a fully localized report rather than a mix of languages.
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
        " Trusted reference sources for live validation when this role is explicitly assigned a"
        " web_search pass, or when a specific claim cannot be validated from the data already supplied."
        " Do not re-check every site in every role when a backend-prefetched source, tool result, or"
        " structured evidence ledger already supports the claim. If you do use MiniMax MCP browsing,"
        " use the exact tool name web_search and do not invent alternate tool names such as websearch."
        " If a trusted source is unreachable, state that limitation:\n"
        + "\n".join(lines)
    )


def get_coinglass_packages_for_role(role_key: str) -> tuple[str, ...]:
    """Resolve the configured CoinGlass package list for a specific agent role."""
    from tradingagents.dataflows.config import get_config

    role = str(role_key or "").strip()
    if not role:
        return ()

    packages_by_role = get_config().get("coinglass_packages_by_role") or {}
    packages = packages_by_role.get(role) or ()
    owner = get_config().get("coinglass_owner_analyst") or "onchain"
    if not packages and _role_aliases(role).intersection(_role_aliases(owner)):
        packages = packages_by_role.get("onchain_analyst") or ()
    return tuple(
        str(package).strip()
        for package in packages
        if str(package).strip()
    )


def build_instrument_context(ticker: str, asset_type: str = "crypto") -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    instrument_label = "asset" if asset_type == "crypto" else "instrument"
    extra_hint = (
        " Treat it as a crypto asset rather than a company, and do not assume company financial statements are available."
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
    char_limit: int | None = None,
) -> str:
    """Return CoinGlass context assigned to the configured analyst path."""
    from tradingagents.dataflows.config import get_config

    config = get_config()
    owner_label = str(config.get("coinglass_owner_agent_label") or "configured analyst").strip()
    if char_limit is None:
        char_limit = int(config.get("coinglass_prompt_char_limit") or 0)

    package_contexts = state.get("coinglass_package_contexts") or {}
    context_parts: list[str] = []
    packages_were_explicit = packages is not None
    requested_packages = tuple(str(package).strip() for package in (packages or ()) if str(package).strip())
    if requested_packages and isinstance(package_contexts, dict):
        for package in requested_packages:
            context = str(package_contexts.get(package) or "").strip()
            if context:
                context_parts.append(context)

    context = "\n\n".join(context_parts).strip()
    if not context and requested_packages and not package_contexts:
        context = str(state.get("coinglass_context") or "").strip()
    if not context and not packages_were_explicit:
        context = str(state.get("coinglass_context") or "").strip()
    if not context:
        if packages_were_explicit and not requested_packages:
            return (
                "\n\nCoinGlass raw endpoint context is not assigned to this role. "
                "Use the structured evidence ledger and endpoint summaries already collected in this run; "
                "do not repeat or invent CoinGlass metrics."
            )
        return (
            "\n\nCoinGlass high-value context: unavailable for this run. "
            "Do not invent CoinGlass metrics; rely on other available evidence."
        )

    if char_limit > 0 and len(context) > char_limit:
        context = context[: max(0, char_limit - 14)].rstrip() + "\n[truncated]"

    return (
        f"\n\nCoinGlass high-value context collected for the {owner_label} path in this same analysis run. "
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


        
