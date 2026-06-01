from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
    get_preferred_reference_sources_instruction,
)
from tradingagents.agents.utils.evidence import (
    get_structured_evidence_instruction,
    split_report_and_evidence,
)
from tradingagents.dataflows.config import get_config
from tradingagents.llm_clients.minimax_mcp import MiniMaxMCPChatModel, has_minimax_mcp_tool


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "crypto")
        asset_label = "crypto asset" if asset_type == "crypto" else "asset"
        instrument_context = build_instrument_context(
            state["company_of_interest"], asset_type
        )
        use_mcp_web_search_only = (
            asset_type == "crypto"
            and isinstance(llm, MiniMaxMCPChatModel)
            and has_minimax_mcp_tool(llm.settings, "web_search")
        )
        is_deepseek = get_config().get("llm_provider", "") == "deepseek"
        use_deepseek_web_search = asset_type == "crypto" and is_deepseek
        active_llm = llm.with_trace_context("News Analyst") if isinstance(llm, MiniMaxMCPChatModel) else llm

        tools = [
            get_news,
            get_global_news,
        ]

        if use_mcp_web_search_only:
            system_message = (
            f"You are a news researcher tasked with analyzing recent news and trends over the past week for a {asset_label}. Use the exact MiniMax MCP tool `web_search` as your retrieval path and call it at least once before drafting. Do not call internal news tools in this branch. Search for asset-specific news, macro headlines, ETF and institutional flow coverage, exchange developments, liquidity shifts, and regulatory updates. When current evidence is incomplete, search again instead of relying on stale cached assumptions. Provide specific, actionable insights with supporting evidence for downstream debate."
                + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
                + get_preferred_reference_sources_instruction()
                + get_language_instruction()
                + get_structured_evidence_instruction("news")
            )
        elif use_deepseek_web_search:
            system_message = (
            f"You are a news researcher tasked with analyzing recent news and trends over the past week for a {asset_label}. Use the `webfetch(url, max_chars)` tool as your retrieval path. Fetch relevant crypto news sites, macro/economic data pages, ETF flow trackers, exchange announcements, and regulatory news sources directly. Suggested sources: CoinDesk, CoinTelegraph, The Block, Reuters crypto section, Bloomberg crypto, CoinGlass, CryptoQuant, and major exchange blogs. Call webfetch at least once with at least 2-3 different sources before drafting. If a fetch fails, try an alternative URL. Provide specific, actionable insights with supporting evidence for downstream debate."
                + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
                + get_preferred_reference_sources_instruction()
                + get_language_instruction()
                + get_structured_evidence_instruction("news")
            )
        else:
            system_message = (
                f"You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for {asset_label}-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence for downstream debate."
                + " Do not duplicate the broad live web validation pass assigned to another analyst; use the structured news tools first and only browse for a specific unsupported recency gap."
                + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
                + get_preferred_reference_sources_instruction()
                + get_language_instruction()
                + get_structured_evidence_instruction("news")
            )

        use_web_search_only = use_mcp_web_search_only or use_deepseek_web_search

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Build on earlier agent outputs when they already contain usable evidence or a completed section,"
                    " but do not restate obsolete buy/sell stop markers from older flows."
                    " Core analysis tools include: {tool_names}\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(
            tool_names="webfetch" if use_web_search_only else ", ".join([tool.name for tool in tools])
        )
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        if use_mcp_web_search_only:
            chain = prompt | active_llm
        elif use_deepseek_web_search:
            from tradingagents.agents.utils.web_search_tools import webfetch
            chain = prompt | active_llm.bind_tools([webfetch])
        else:
            chain = prompt | active_llm.bind_tools(tools)
        result = chain.invoke(state["messages"])

        report = ""

        evidence_items = []
        if len(result.tool_calls) == 0:
            report, evidence_items = split_report_and_evidence(
                result.content,
                agent_key="news",
                agent_label="News Analyst",
                report_section="news_report",
                analysis_date=current_date,
            )

        return {
            "messages": [result],
            "news_report": report,
            "evidence_items": evidence_items,
        }

    return news_analyst_node
