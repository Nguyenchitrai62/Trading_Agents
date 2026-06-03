"""Social analyst — crypto market sentiment analysis via live web_search / webfetch."""

from datetime import datetime, timedelta
import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_preferred_reference_sources_instruction,
)
from tradingagents.agents.utils.evidence import (
    get_structured_evidence_instruction,
    split_report_and_evidence,
)
from tradingagents.dataflows.config import get_config
from tradingagents.llm_clients.minimax_mcp import MiniMaxMCPChatModel, has_minimax_mcp_tool


logger = logging.getLogger(__name__)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = build_instrument_context(ticker, "crypto")
        has_mcp_web_search = isinstance(llm, MiniMaxMCPChatModel) and has_minimax_mcp_tool(llm.settings, "web_search")
        use_webfetch = get_config().get("llm_provider", "") == "deepseek"
        active_llm = llm.with_trace_context("Social Analyst") if isinstance(llm, MiniMaxMCPChatModel) else llm
        mcp_mode = has_mcp_web_search

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            mcp_mode=mcp_mode,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Build on earlier agent outputs when they already contain usable evidence or a completed section,"
                    " but do not restate obsolete buy/sell stop markers from older flows."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        if use_webfetch:
            from tradingagents.agents.utils.web_search_tools import webfetch
            chain = prompt | active_llm.bind_tools([webfetch])
        else:
            chain = prompt | active_llm
        result = chain.invoke(state["messages"])

        if result is None:
            return {
                "messages": [],
                "sentiment_report": "",
                "evidence_items": [],
            }

        evidence_items = []
        report = result.content
        if not (getattr(result, "tool_calls", None) or []):
            report, evidence_items = split_report_and_evidence(
                result.content,
                agent_key="social",
                agent_label="Social Analyst",
                report_section="sentiment_report",
                analysis_date=end_date,
            )

        return {
            "messages": [result],
            "sentiment_report": report,
            "evidence_items": evidence_items,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    mcp_mode: bool = True,
) -> str:
    if mcp_mode:
        tool_instruction = (
            "Use the MiniMax MCP tool `web_search` as your live retrieval path and call it at least once before drafting the report. "
            "Do not call internal news/social tools in this branch. If web evidence is thin, search again with a narrower query before drafting."
        )
    else:
        tool_instruction = (
            "Use the `webfetch(url, max_chars)` tool as your live retrieval path. "
            "Fetch relevant crypto news sites, data APIs, and market commentary pages directly. "
            "Suggested sources: CoinDesk, CoinTelegraph, The Block, CryptoQuant, Glassnode, "
            "DeFiLlama, CoinMarketCap, CoinGecko, TradingView crypto section, and any exchange blogs. "
            "Call webfetch at least once before drafting the report and fetch at least 2-3 different sources. "
            "If a fetch fails, try an alternative URL. Do not rely on stale internal data."
        )
    return f"""You are a crypto market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}.

{tool_instruction}

Prioritize:

1. Crypto-native news and market commentary.
2. Community discussion and retail positioning signals surfaced by the current web results.
3. ETF/institutional flow coverage, liquidations, funding-rate commentary, and macro narratives affecting crypto sentiment.
4. Source verification on any strong claim before you rely on it.

How to analyze:

1. Compare institutional/news framing with crowd and community tone.
2. Call out divergences between bullish narrative flow and bearish positioning or macro pressure.
3. Distinguish hard catalysts from opinion and speculation.
4. Be explicit about data quality: if current web evidence is thin or contradictory, say so.
5. Treat the output as a sentiment signal for downstream debate, not as a standalone price forecast.

Output:

1. Overall sentiment direction — Bullish / Bearish / Neutral / Mixed — with a confidence note.
2. Source-by-source breakdown with supporting evidence from the current web results.
3. Divergences, alignments, and dominant narratives.
4. Catalysts and risks.
5. A Markdown table summarizing key sentiment signals, their direction, source, and supporting evidence.

{get_preferred_reference_sources_instruction()}{get_language_instruction()}{get_structured_evidence_instruction("social")}"""
