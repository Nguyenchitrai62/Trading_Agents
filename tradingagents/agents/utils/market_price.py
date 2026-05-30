from __future__ import annotations

import json
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BINANCE_TICKER_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
BINANCE_USER_AGENT = "tradingagents/0.2"


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
