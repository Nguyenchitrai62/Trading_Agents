from __future__ import annotations

import json
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BINANCE_TICKER_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_USER_AGENT = "tradingagents/0.2"
CCXT_FETCH_TIMEOUT_SECONDS = 8.0
DEFAULT_REFERENCE_PRICE_SOURCE = "binance_spot_urllib"
CCXT_REFERENCE_PRICE_SOURCE = "ccxt_binance_ticker"


def normalize_binance_symbol(symbol: str) -> tuple[str, str]:
    normalized = str(symbol or "").strip().upper().replace(" ", "")
    if not normalized:
        raise ValueError("symbol is required")
    if "/" in normalized:
        base, quote = normalized.split("/", 1)
    elif "-" in normalized:
        base, quote = normalized.split("-", 1)
    else:
        raise ValueError("Crypto symbol must include base and quote assets.")
    if quote == "USD":
        quote = "USDT"
    market_symbol = f"{base}/{quote}"
    api_symbol = f"{base}{quote}"
    return api_symbol, market_symbol


def fetch_current_binance_spot_price(symbol: str) -> Optional[float]:
    try:
        api_symbol, _market_symbol = normalize_binance_symbol(symbol)
    except ValueError:
        return None

    url = f"{BINANCE_TICKER_PRICE_URL}?{urlencode({'symbol': api_symbol})}"
    request = Request(url, headers={"User-Agent": BINANCE_USER_AGENT})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    try:
        return float(payload.get("price"))
    except (TypeError, ValueError):
        return None


def _fetch_via_ccxt(symbol: str) -> Optional[float]:
    """Fetch via ccxt if the package is importable and the symbol is supported.

    Returns ``None`` for any failure mode so callers can fall back gracefully.
    """
    try:
        import ccxt  # type: ignore
    except ImportError:
        return None
    try:
        exchange = ccxt.binance({"enableRateLimit": True, "timeout": int(CCXT_FETCH_TIMEOUT_SECONDS * 1000)})
    except Exception:
        return None
    try:
        try:
            market_symbol = symbol.replace("-", "/").upper()
        except Exception:
            return None
        ticker = exchange.fetch_ticker(market_symbol)
        price = ticker.get("last") if isinstance(ticker, dict) else None
        if price is None:
            return None
        return float(price)
    except Exception:
        return None
    finally:
        try:
            close_fn = getattr(exchange, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass


def fetch_reference_price(symbol: str) -> tuple[Optional[float], str]:
    """Single source of truth for the current spot price.

    Tries ccxt first and falls back to the public Binance ticker endpoint
    over urllib. Returns ``(price, source)`` where ``source`` is a short tag
    describing which path succeeded, or ``""`` if both paths failed.
    Never raises.
    """
    if not symbol or not str(symbol).strip():
        return None, ""

    ccxt_price = _fetch_via_ccxt(symbol)
    if ccxt_price is not None and ccxt_price > 0:
        return ccxt_price, CCXT_REFERENCE_PRICE_SOURCE

    urllib_price = fetch_current_binance_spot_price(symbol)
    if urllib_price is not None and urllib_price > 0:
        return urllib_price, DEFAULT_REFERENCE_PRICE_SOURCE

    return None, ""
