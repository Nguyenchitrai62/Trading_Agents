"""StockTwits public symbol-stream fetcher.

StockTwits exposes a per-symbol message stream at
``api.stocktwits.com/api/2/streams/symbol/{ticker}.json`` that requires no
API key, no OAuth, and no registration. Each message includes a
user-labeled sentiment field (``Bullish``/``Bearish``/null), the message
body, timestamp, and posting user.

The function is deliberately self-contained: short timeout, graceful
degradation on any HTTP or parse failure, and a string return type so
the calling agent gets a uniform interface regardless of whether the
network call succeeded.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_UA = "Mozilla/5.0 (compatible; TradingAgents/0.2; +https://github.com/TauricResearch/TradingAgents)"
_CRYPTO_QUOTES = {"USD", "USDT", "USDC", "BTC", "ETH"}


def _stocktwits_symbol_candidates(ticker: str) -> list[str]:
    normalized = ticker.strip().upper().replace(" ", "")
    if not normalized:
        return []

    candidates: list[str] = []
    if "/" in normalized:
        base, quote_symbol = normalized.split("/", 1)
    elif "-" in normalized:
        base, quote_symbol = normalized.split("-", 1)
    else:
        base, quote_symbol = normalized, ""

    if quote_symbol in _CRYPTO_QUOTES and base:
        candidates.append(f"{base}.X")
        candidates.append(base)
    candidates.append(normalized)

    seen: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.append(candidate)
    return seen


def fetch_stocktwits_messages(ticker: str, limit: int | None = None, timeout: float = 10.0) -> str:
    """Fetch recent StockTwits messages for ``ticker`` and return them as a
    formatted plaintext block ready for prompt injection.

    Returns a placeholder string when the endpoint is unreachable, the
    symbol has no messages, or the response shape is unexpected — the
    caller never has to special-case None or exceptions.
    """
    data = None
    resolved_symbol = ticker.strip().upper()
    last_error: Exception | None = None
    for candidate in _stocktwits_symbol_candidates(ticker):
        url = _API.format(ticker=quote(candidate, safe="."))
        req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read())
            resolved_symbol = candidate
            break
        except HTTPError as exc:
            last_error = exc
            if exc.code == 404:
                continue
            if exc.code in {403, 429}:
                logger.debug("StockTwits fetch unavailable for %s via %s: %s", ticker, candidate, exc)
            else:
                logger.warning("StockTwits fetch failed for %s via %s: %s", ticker, candidate, exc)
            return f"<stocktwits unavailable for {ticker}: HTTP {exc.code}>"
        except (URLError, json.JSONDecodeError, TimeoutError) as exc:
            last_error = exc
            logger.debug("StockTwits fetch unavailable for %s via %s: %s", ticker, candidate, exc)
            return f"<stocktwits unavailable for {ticker}: {type(exc).__name__}>"

    if data is None:
        if last_error is not None:
            logger.debug("StockTwits symbol not found for %s after crypto normalization: %s", ticker, last_error)
        return f"<no StockTwits stream found for {ticker}>"

    messages = data.get("messages", []) if isinstance(data, dict) else []
    if not messages:
        return f"<no StockTwits messages found for ${resolved_symbol}>"

    lines = []
    bullish = bearish = unlabeled = 0
    selected_messages = messages if limit is None else messages[:limit]
    for m in selected_messages:
        created = m.get("created_at", "")
        user = (m.get("user") or {}).get("username", "?")
        entities = m.get("entities") or {}
        sentiment_obj = entities.get("sentiment") or {}
        sentiment = sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None
        body = (m.get("body") or "").replace("\n", " ").strip()
        if len(body) > 280:
            body = body[:280] + "…"

        if sentiment == "Bullish":
            bullish += 1
            tag = "Bullish"
        elif sentiment == "Bearish":
            bearish += 1
            tag = "Bearish"
        else:
            unlabeled += 1
            tag = "no-label"
        lines.append(f"[{created} · @{user} · {tag}] {body}")

    total = bullish + bearish + unlabeled
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0
    summary = (
        f"Bullish: {bullish} ({bull_pct}%) · "
        f"Bearish: {bearish} ({bear_pct}%) · "
        f"Unlabeled: {unlabeled} · "
        f"Total: {total} most-recent messages"
    )
    return summary + "\n\n" + "\n".join(lines)
