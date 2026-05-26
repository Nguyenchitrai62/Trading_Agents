"""Reddit search fetcher for ticker-specific discussion posts.

Uses Reddit's public JSON endpoints (``reddit.com/r/{sub}/search.json``)
which do not require an API key. Public throughput is ~10 requests per
minute per IP, well within budget for a single agent run that queries
a handful of finance subreddits per ticker.

Returns formatted plaintext blocks ready for prompt injection. Degrades
gracefully — returns a placeholder string rather than raising, so callers
never have to special-case missing data.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_UA = "Mozilla/5.0 (compatible; TradingAgents/0.2; +https://github.com/TauricResearch/TradingAgents)"
_CRYPTO_QUOTES = {"USD", "USDT", "USDC", "BTC", "ETH"}

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")


def _reddit_query(ticker: str) -> str:
    normalized = ticker.strip().upper().replace(" ", "")
    if not normalized:
        return ticker
    if "/" in normalized:
        base, quote_symbol = normalized.split("/", 1)
    elif "-" in normalized:
        base, quote_symbol = normalized.split("-", 1)
    else:
        base, quote_symbol = normalized, ""
    if quote_symbol in _CRYPTO_QUOTES and base:
        return base
    return normalized


def _fetch_subreddit(
    query: str,
    sub: str,
    limit: int | None,
    timeout: float,
) -> tuple[list[dict], str | None]:
    params = {
        "q": query,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",  # last 7 days
    }
    if limit is not None:
        params["limit"] = limit
    qs = urlencode(params)
    url = _API.format(sub=sub, qs=qs)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except HTTPError as exc:
        if exc.code in {403, 429}:
            logger.debug("Reddit public search unavailable for r/%s · %s: HTTP %s", sub, query, exc.code)
            return [], f"HTTP {exc.code} from Reddit public search"
        logger.warning("Reddit fetch failed for r/%s · %s: %s", sub, query, exc)
        return [], str(exc)
    except (URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.debug("Reddit fetch unavailable for r/%s · %s: %s", sub, query, exc)
        return [], type(exc).__name__
    children = (payload.get("data") or {}).get("children") or []
    return [c.get("data", {}) for c in children if isinstance(c, dict)], None


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int | None = None,
    timeout: float = 10.0,
    inter_request_delay: float = 0.4,
) -> str:
    """Fetch recent Reddit posts mentioning ``ticker`` across finance
    subreddits and return them as a formatted plaintext block.

    ``inter_request_delay`` keeps us under Reddit's public rate limit
    (~10 req/min per IP) even if the caller queries many subreddits.
    """
    query = _reddit_query(ticker)
    blocks = []
    total_posts = 0
    unavailable_reasons: list[str] = []
    for i, sub in enumerate(subreddits):
        if i > 0:
            time.sleep(inter_request_delay)
        posts, unavailable_reason = _fetch_subreddit(query, sub, limit_per_sub, timeout)
        if unavailable_reason:
            unavailable_reasons.append(f"r/{sub}: {unavailable_reason}")
            blocks.append(f"r/{sub}: <unavailable: {unavailable_reason}>")
            continue
        total_posts += len(posts)
        if not posts:
            blocks.append(f"r/{sub}: <no posts found mentioning {query.upper()} in the past 7 days>")
            continue

        lines = [f"r/{sub} - {len(posts)} recent posts mentioning {query.upper()}:"]
        for p in posts:
            title = (p.get("title") or "").replace("\n", " ").strip()
            score = p.get("score", 0)
            comments = p.get("num_comments", 0)
            created = p.get("created_utc")
            created_str = (
                time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            )
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            lines.append(
                f"  [{created_str} · {score:>4}↑ · {comments:>3}c] {title}"
                + (f"\n    body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        if unavailable_reasons:
            return (
                f"<Reddit public search unavailable for {ticker.upper()} "
                f"using query {query.upper()}: {'; '.join(unavailable_reasons)}>"
            )
        return (
            f"<no Reddit posts found mentioning {query.upper()} across "
            f"{', '.join(f'r/{s}' for s in subreddits)} in the past 7 days>"
        )
    return "\n\n".join(blocks)
