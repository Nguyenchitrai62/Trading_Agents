"""Social analyst — multi-source social analysis for a target ticker.

Previously named ``social_media_analyst``. Renamed and redesigned because
the old version had a prompt that demanded social-media analysis but the
only tool available was Yahoo Finance news — which led LLMs to fabricate
Reddit/X/StockTwits content under prompt pressure (verified live).

For non-crypto assets, the agent pre-fetches three complementary data
sources before the LLM is invoked and injects them into the prompt as
structured blocks:

    1. News headlines      — Yahoo Finance (institutional framing)
    2. StockTwits messages — retail-trader posts indexed by cashtag, with
                                                     user-labeled Bullish/Bearish sentiment tags
    3. Reddit posts        — r/wallstreetbets, r/stocks, r/investing

For crypto assets under the MiniMax MCP runtime, the agent still keeps those
internal sources as optional supporting inputs, but also keeps tool-calling
enabled and requires live `web_search` usage so sentiment evidence is grounded
in current web sources rather than stale vendor snapshots alone.

See: https://github.com/TauricResearch/TradingAgents/issues/557
"""

from datetime import datetime, timedelta
import logging

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
    get_preferred_reference_sources_instruction,
)
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from tradingagents.llm_clients.minimax_mcp import MiniMaxMCPChatModel


logger = logging.getLogger(__name__)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def _source_should_be_skipped(content: str) -> bool:
    normalized = str(content or "").strip().lower()
    if not normalized:
        return True
    return (
        normalized.startswith("error ")
        or normalized.startswith("error:")
        or "rate limit" in normalized
        or "http 429" in normalized
        or "<unavailable" in normalized
        or " timed out" in normalized
    )


def _prefetch_source_or_skip(source_name: str, fetcher) -> str:
    try:
        content = fetcher()
    except Exception as exc:
        logger.warning("%s source failed and will be skipped: %s", source_name, exc)
        return f"<{source_name} skipped: unavailable>"

    if _source_should_be_skipped(content):
        snippet = " ".join(str(content).split())[:220]
        logger.warning("%s source returned unavailable data and will be skipped: %s", source_name, snippet)
        return f"<{source_name} skipped: unavailable or rate limited>"

    return content


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches news + StockTwits + Reddit data as supporting context. When
    MiniMax MCP is available for crypto assets, the prompt also requires a
    live web_search pass before the report is drafted.
    """

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        asset_type = state.get("asset_type", "crypto")
        instrument_context = build_instrument_context(ticker, asset_type)
        prefer_mcp_web_search = asset_type == "crypto" and isinstance(llm, MiniMaxMCPChatModel)

        news_block = _prefetch_source_or_skip(
            "news",
            lambda: get_news.func(ticker, start_date, end_date),
        )
        stocktwits_block = _prefetch_source_or_skip(
            "stocktwits",
            lambda: fetch_stocktwits_messages(ticker),
        )
        reddit_block = _prefetch_source_or_skip(
            "reddit",
            lambda: fetch_reddit_posts(ticker),
        )

        if prefer_mcp_web_search:
            system_message = _build_crypto_web_search_system_message(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                news_block=news_block,
                stocktwits_block=stocktwits_block,
                reddit_block=reddit_block,
            )
        else:
            system_message = _build_system_message(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                news_block=news_block,
                stocktwits_block=stocktwits_block,
                reddit_block=reddit_block,
            )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # When MiniMax MCP is available for crypto, bind an empty local tool set
        # so the graph still exposes MCP web_search tool calls/results explicitly.
        chain = prompt | (llm.bind_tools([]) if prefer_mcp_web_search else llm)
        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "sentiment_report": result.content,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    """Assemble the sentiment-analyst system message with structured data blocks."""
    return f"""You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

## Data sources (pre-fetched, in this prompt)

### News headlines — Yahoo Finance, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

<start_of_news>
{news_block}
<end_of_news>

### StockTwits messages — retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>

### Reddit posts — r/wallstreetbets, r/stocks, r/investing (past 7 days)
Community discussion. Engagement signal via upvote score and comment count. Subreddit character matters (r/wallstreetbets is often contrarian/exuberant; r/stocks more measured; r/investing longer-term).

<start_of_reddit>
{reddit_block}
<end_of_reddit>

## How to analyze this data (best practices)

1. **Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal.** A 70/30 bullish/bearish split is moderately bullish; ≥90/10 may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters — base rates on the actual message count, not percentages alone.

2. **Look for cross-source divergences.** If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal — it can mean retail is leaning into a thesis the news flow hasn't caught up to (or vice versa, that retail is chasing while institutions are cautious).

3. **Weight Reddit posts by engagement.** A 400-upvote / 200-comment thread reflects community attention; a 3-upvote post is noise. Read the body excerpts for context — the title alone often misleads.

4. **Distinguish opinion from event.** A news headline ("Nvidia announces $500M Corning deal") is an event; a StockTwits post ("buying NVDA, this is going to moon") is opinion. Both are inputs but should be weighted differently in your conclusions.

5. **Identify recurring narrative themes.** What topic keeps coming up across sources? That's the dominant narrative driving current sentiment.

6. **Be honest about data limits.** If StockTwits returned only a handful of messages, or one or more sources returned an "<unavailable>" placeholder, the sentiment read is less robust — flag this caveat explicitly. If the sources are silent on a given subreddit, say so.

7. **Identify catalysts and risks** that emerge across sources — news of upcoming earnings, product launches, competitive threats, macro headlines, etc.

8. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output

Produce a sentiment report covering, in order:

1. **Overall sentiment direction** — Bullish / Bearish / Neutral / Mixed — with a brief confidence note based on data quality and sample size.
2. **Source-by-source breakdown** — what each of news / StockTwits / Reddit is telling you, with specific evidence (cite message counts, ratios, notable posts).
3. **Divergences, alignments, and key narratives** across sources.
4. **Catalysts and risks** surfaced by the data.
5. **Markdown table** at the end summarizing key sentiment signals, their direction, source, and supporting evidence.

{get_language_instruction()}"""


def _build_crypto_web_search_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    return f"""You are a crypto market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}.

Use the MiniMax MCP tool `web_search` as your live retrieval path and call it at least once before drafting the report. Treat the prefetched internal sources below as supporting inputs: if one of them was skipped or unavailable, note the limitation briefly and continue with the remaining sources plus `web_search`.

## Prefetched internal sources (supporting context)

### News headlines / vendor news block

<start_of_news>
{news_block}
<end_of_news>

### StockTwits messages / symbol stream block

<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>

### Reddit posts / community discussion block

<start_of_reddit>
{reddit_block}
<end_of_reddit>

Prioritize:

1. Crypto-native news and market commentary.
2. Community discussion and retail positioning signals surfaced by the current web results and the prefetched internal blocks when they are available.
3. ETF/institutional flow coverage, liquidations, funding-rate commentary, and macro narratives affecting crypto sentiment.
4. Source verification on any strong claim before you rely on it.

How to analyze:

1. Compare institutional/news framing with crowd and community tone.
2. Call out divergences between bullish narrative flow and bearish positioning or macro pressure.
3. Distinguish hard catalysts from opinion and speculation.
4. Be explicit about data quality: if current web evidence is thin or contradictory, say so.
5. Treat the output as a sentiment signal for the trader, not as a standalone price forecast.

Output:

1. Overall sentiment direction — Bullish / Bearish / Neutral / Mixed — with a confidence note.
2. Source-by-source breakdown with supporting evidence from the current web results.
3. Divergences, alignments, and dominant narratives.
4. Catalysts and risks.
5. A Markdown table summarizing key sentiment signals, their direction, source, and supporting evidence.

{get_preferred_reference_sources_instruction()}{get_language_instruction()}"""


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work.

    .. deprecated::
        Import :func:`create_sentiment_analyst` directly instead.
    """
    import warnings
    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
