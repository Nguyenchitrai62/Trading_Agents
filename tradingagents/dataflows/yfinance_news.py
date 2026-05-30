"""yfinance-based news data fetching functions."""

from collections.abc import Iterable
from typing import Optional

import yfinance as yf
from datetime import datetime
from dateutil.relativedelta import relativedelta

from .config import get_config
from .stockstats_utils import yf_retry


def _candidate_yfinance_news_tickers(ticker: str) -> list[str]:
    normalized = str(ticker or "").strip().upper().replace("/", "-")
    if not normalized:
        return []

    candidates: list[str] = [normalized]
    if "-" not in normalized:
        return candidates

    base, quote = normalized.split("-", 1)
    if not base or not quote:
        return candidates

    quote_aliases = {
        "USDT": "USD",
        "USDC": "USD",
        "BUSD": "USD",
    }
    alias_quote = quote_aliases.get(quote)
    if alias_quote:
        candidates.append(f"{base}-{alias_quote}")

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def _fetch_symbol_news(symbol: str) -> Iterable[dict]:
    stock = yf.Ticker(symbol)
    return yf_retry(lambda: stock.get_news())


def _article_text(article: dict) -> str:
    data = _extract_article_data(article)
    return " ".join(
        part for part in (
            data.get("title") or "",
            data.get("summary") or "",
            data.get("link") or "",
        )
        if part
    ).lower()


def _is_relevant_global_news_article(article: dict) -> bool:
    text = _article_text(article)
    if not text:
        return False

    relevant_keywords = (
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "solana",
        "sol",
        "xrp",
        "crypto",
        "stablecoin",
        "etf",
        "regulation",
        "sec",
        "cftc",
        "mica",
        "federal reserve",
        "fed",
        "treasury yield",
        "treasury yields",
        "dxy",
        "dollar index",
        "liquidity",
        "risk asset",
        "risk assets",
        "binance",
        "coinbase",
        "bybit",
        "open interest",
        "funding",
        "liquidation",
        "options skew",
        "exchange reserve",
        "exchange reserves",
        "whale",
        "on-chain",
        "miner",
        "hashrate",
        "macro",
    )
    return any(keyword in text for keyword in relevant_keywords)


def _extract_article_data(article: dict) -> dict:
    """Extract article data from yfinance news format (handles nested 'content' structure)."""
    # Handle nested content structure
    if "content" in article:
        content = article["content"]
        title = content.get("title", "No title")
        summary = content.get("summary", "")
        provider = content.get("provider", {})
        publisher = provider.get("displayName", "Unknown")

        # Get URL from canonicalUrl or clickThroughUrl
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = url_obj.get("url", "")

        # Get publish date
        pub_date_str = content.get("pubDate", "")
        pub_date = None
        if pub_date_str:
            try:
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return {
            "title": title,
            "summary": summary,
            "publisher": publisher,
            "link": link,
            "pub_date": pub_date,
        }
    else:
        # Fallback for flat structure
        return {
            "title": article.get("title", "No title"),
            "summary": article.get("summary", ""),
            "publisher": article.get("publisher", "Unknown"),
            "link": article.get("link", ""),
            "pub_date": None,
        }


def get_news_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Retrieve news for a specific stock ticker using yfinance.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string containing news articles
    """
    try:
        resolved_symbol = None
        news = []
        for candidate in _candidate_yfinance_news_tickers(ticker):
            candidate_news = _fetch_symbol_news(candidate)
            if candidate_news:
                resolved_symbol = candidate
                news = candidate_news
                break

        if not news:
            return f"No news found for {ticker}"

        # Parse date range for filtering
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        news_str = ""
        filtered_count = 0

        for article in news:
            data = _extract_article_data(article)

            # Filter by date if publish time is available
            if data["pub_date"]:
                pub_date_naive = data["pub_date"].replace(tzinfo=None)
                if not (start_dt <= pub_date_naive <= end_dt + relativedelta(days=1)):
                    continue

            news_str += f"### {data['title']} (source: {data['publisher']})\n"
            if data["summary"]:
                news_str += f"{data['summary']}\n"
            if data["link"]:
                news_str += f"Link: {data['link']}\n"
            news_str += "\n"
            filtered_count += 1

        if filtered_count == 0:
            return f"No news found for {ticker} between {start_date} and {end_date}"

        source_note = f" (yfinance symbol: {resolved_symbol})" if resolved_symbol and resolved_symbol != ticker else ""
        return f"## {ticker} News{source_note}, from {start_date} to {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


def get_global_news_yfinance(
    curr_date: str,
    look_back_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """
    Retrieve global/macro economic news using yfinance Search.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back. ``None`` falls back to
            ``global_news_lookback_days`` from the active config.
        limit: Optional maximum number of articles to return. ``None`` leaves
            article count to the provider/library default.

    Returns:
        Formatted string containing global news articles
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    search_queries = config["global_news_queries"]

    all_news = []
    seen_titles = set()

    try:
        for query in search_queries:
            if limit is None:
                search = yf_retry(lambda q=query: yf.Search(
                    query=q,
                    enable_fuzzy_query=True,
                ))
            else:
                search = yf_retry(lambda q=query: yf.Search(
                    query=q,
                    news_count=limit,
                    enable_fuzzy_query=True,
                ))

            if search.news:
                for article in search.news:
                    # Handle both flat and nested structures
                    if "content" in article:
                        data = _extract_article_data(article)
                        title = data["title"]
                    else:
                        title = article.get("title", "")

                    # Deduplicate by title
                    if title and title not in seen_titles and _is_relevant_global_news_article(article):
                        seen_titles.add(title)
                        all_news.append(article)

        if not all_news:
            return f"No global news found for {curr_date}"

        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")
        end_dt = curr_dt + relativedelta(days=1)

        news_str = ""
        rendered_count = 0
        for article in all_news:
            # Handle both flat and nested structures
            if "content" in article:
                data = _extract_article_data(article)
                pub_date = data.get("pub_date")
                if not pub_date:
                    continue
                pub_naive = pub_date.replace(tzinfo=None) if hasattr(pub_date, "replace") else pub_date
                if not (start_dt <= pub_naive <= end_dt):
                    continue
                title = data["title"]
                publisher = data["publisher"]
                link = data["link"]
                summary = data["summary"]
            else:
                continue

            news_str += f"### {title} (source: {publisher})\n"
            if summary:
                news_str += f"{summary}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"
            rendered_count += 1
            if limit is not None and rendered_count >= limit:
                break

        if rendered_count == 0:
            return f"No global news found between {start_date} and {curr_date}"

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching global news: {str(e)}"
