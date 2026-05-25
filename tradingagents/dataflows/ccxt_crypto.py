from __future__ import annotations

from datetime import datetime
from typing import Annotated

import pandas as pd


_EXCHANGE_QUOTE_FALLBACKS = {
    "binance": {
        "USD": "USDT",
    },
}

_CRYPTO_INDICATOR_ALIASES = {
    "ema": "close_10_ema",
    "close_ema": "close_10_ema",
    "closeema": "close_10_ema",
    "10ema": "close_10_ema",
    "10_ema": "close_10_ema",
    "ema10": "close_10_ema",
    "sma50": "close_50_sma",
    "50sma": "close_50_sma",
    "sma200": "close_200_sma",
    "200sma": "close_200_sma",
}

_CRYPTO_INDICATOR_WINDOWS = {
    "close_10_ema": 20,
    "close_50_sma": 70,
    "close_200_sma": 240,
    "rsi": 40,
    "macd": 60,
    "macds": 60,
    "macdh": 60,
    "boll": 40,
    "boll_ub": 40,
    "boll_lb": 40,
    "atr": 40,
    "vwma": 40,
    "mfi": 40,
}

_CRYPTO_INDICATOR_DESCRIPTIONS = {
    "close_10_ema": "10 EMA for short-term momentum and responsive trend shifts.",
    "close_50_sma": "50 SMA for medium-term trend direction and dynamic support/resistance.",
    "close_200_sma": "200 SMA for the long-term structural trend.",
    "rsi": "RSI to detect overbought and oversold momentum conditions.",
    "macd": "MACD line for momentum shifts and trend acceleration.",
    "macds": "MACD signal line for crossover confirmation.",
    "macdh": "MACD histogram to show momentum spread and early inflection.",
    "boll": "Bollinger middle line as the mean-reversion baseline.",
    "boll_ub": "Upper Bollinger Band for volatility expansion and breakout context.",
    "boll_lb": "Lower Bollinger Band for volatility compression and downside extension.",
    "atr": "ATR for realized volatility and stop-loss sizing.",
    "vwma": "VWMA to blend trend with volume confirmation.",
    "mfi": "Money Flow Index to combine price and volume pressure.",
}


def _resolve_exchange(exchange_name: str):
    try:
        import ccxt
    except ImportError as exc:
        raise RuntimeError(
            "ccxt is required for get_crypto_ohlcv. Install dependencies from requirements.txt before using this tool."
        ) from exc

    exchange_id = exchange_name.strip().lower()
    exchange_cls = getattr(ccxt, exchange_id, None)
    if exchange_cls is None:
        raise ValueError(f"Unsupported exchange '{exchange_name}'.")
    exchange = exchange_cls({"enableRateLimit": True})
    return exchange_id, exchange


def _normalize_market_symbol(symbol: str, exchange_id: str) -> str:
    normalized = symbol.strip().upper().replace(" ", "")
    if not normalized:
        raise ValueError("symbol is required")

    if "/" in normalized:
        return normalized

    if "-" not in normalized:
        raise ValueError(
            "Crypto symbol must look like BTC-USD, BTC-USDT, or BTC/USDT so the exchange pair can be resolved."
        )

    base, quote = normalized.split("-", 1)
    quote = _EXCHANGE_QUOTE_FALLBACKS.get(exchange_id, {}).get(quote, quote)
    return f"{base}/{quote}"


def _normalize_indicator_name(indicator: str) -> str:
    normalized = indicator.strip().lower().replace("-", "_").replace(" ", "_")
    normalized = normalized.replace("close_10ema", "close_10_ema")
    return _CRYPTO_INDICATOR_ALIASES.get(normalized, normalized)


def _fetch_ohlcv_frame(symbol: str, timeframe: str, limit: int, exchange_name: str):
    exchange_id, exchange = _resolve_exchange(exchange_name)
    try:
        markets = exchange.load_markets()
        if not exchange.has.get("fetchOHLCV"):
            raise ValueError(f"Exchange '{exchange_name}' does not support OHLCV fetching.")

        requested_symbol = _normalize_market_symbol(symbol, exchange_id)
        market_symbol = requested_symbol
        if market_symbol not in markets:
            candidates = [
                requested_symbol,
                requested_symbol.replace("/USD", "/USDT"),
                requested_symbol.replace("/USDC", "/USDT"),
            ]
            market_symbol = next((candidate for candidate in candidates if candidate in markets), "")

        if not market_symbol:
            raise ValueError(
                f"Pair '{symbol}' is not available on exchange '{exchange_name}'. Try a slash pair like BTC/USDT."
            )

        available_timeframes = exchange.timeframes or {}
        if timeframe not in available_timeframes:
            supported = ", ".join(sorted(available_timeframes.keys())[:12])
            raise ValueError(
                f"Timeframe '{timeframe}' is not supported on '{exchange_name}'. Supported examples: {supported}"
            )

        candles = exchange.fetch_ohlcv(market_symbol, timeframe=timeframe, limit=limit)
        if not candles:
            raise ValueError(f"No OHLCV data returned for {market_symbol} on {exchange_name} ({timeframe}).")

        frame = pd.DataFrame(
            candles,
            columns=["timestamp_ms", "open", "high", "low", "close", "volume"],
        )
        frame["timestamp"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)

        for column in ["open", "high", "low", "close", "volume"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        return exchange, market_symbol, frame
    except Exception:
        close_method = getattr(exchange, "close", None)
        if callable(close_method):
            try:
                close_method()
            except Exception:
                pass
        raise


def _prepare_indicator_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    working["close_10_ema"] = working["close"].ewm(span=10, adjust=False).mean()
    working["close_50_sma"] = working["close"].rolling(50).mean()
    working["close_200_sma"] = working["close"].rolling(200).mean()

    delta = working["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    working["rsi"] = 100 - (100 / (1 + rs))

    ema12 = working["close"].ewm(span=12, adjust=False).mean()
    ema26 = working["close"].ewm(span=26, adjust=False).mean()
    working["macd"] = ema12 - ema26
    working["macds"] = working["macd"].ewm(span=9, adjust=False).mean()
    working["macdh"] = working["macd"] - working["macds"]

    middle = working["close"].rolling(20).mean()
    stddev = working["close"].rolling(20).std(ddof=0)
    working["boll"] = middle
    working["boll_ub"] = middle + (2 * stddev)
    working["boll_lb"] = middle - (2 * stddev)

    previous_close = working["close"].shift(1)
    true_range = pd.concat(
        [
            working["high"] - working["low"],
            (working["high"] - previous_close).abs(),
            (working["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    working["atr"] = true_range.rolling(14).mean()

    volume_sum = working["volume"].rolling(20).sum().replace(0, pd.NA)
    working["vwma"] = (working["close"] * working["volume"]).rolling(20).sum() / volume_sum

    typical_price = (working["high"] + working["low"] + working["close"]) / 3
    raw_money_flow = typical_price * working["volume"]
    positive_flow = raw_money_flow.where(typical_price.diff() > 0, 0.0)
    negative_flow = raw_money_flow.where(typical_price.diff() < 0, 0.0).abs()
    flow_ratio = positive_flow.rolling(14).sum() / negative_flow.rolling(14).sum().replace(0, pd.NA)
    working["mfi"] = 100 - (100 / (1 + flow_ratio))

    return working


def get_crypto_ohlcv(
    symbol: Annotated[str, "crypto pair such as BTC-USD, BTC-USDT, or BTC/USDT"],
    timeframe: Annotated[str, "candle timeframe such as 15m, 1h, 4h, or 1d"] = "1h",
    limit: Annotated[int, "number of candles to fetch"] = 96,
    exchange_name: Annotated[str, "ccxt exchange id such as binance or bybit"] = "binance",
) -> str:
    if limit < 10 or limit > 500:
        raise ValueError("limit must be between 10 and 500 candles")

    exchange, market_symbol, frame = _fetch_ohlcv_frame(symbol, timeframe, limit, exchange_name)
    try:
        price_columns = ["open", "high", "low", "close"]
        frame[price_columns] = frame[price_columns].round(6)
        frame["volume"] = frame["volume"].round(3)
        frame["timestamp"] = frame["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        latest = frame.iloc[-1]
        first = frame.iloc[0]
        close_start = float(first["close"]) if first["close"] else 0.0
        close_end = float(latest["close"]) if latest["close"] else 0.0
        window_return = ((close_end - close_start) / close_start * 100) if close_start else 0.0
        range_high = float(frame["high"].max())
        range_low = float(frame["low"].min())
        quote_volume = float(frame["volume"].sum())

        header = [
            f"# Crypto OHLCV for {market_symbol} from {exchange_name}",
            f"# Timeframe: {timeframe}",
            f"# Total candles: {len(frame)}",
            f"# Window start: {frame.iloc[0]['timestamp']}",
            f"# Window end: {latest['timestamp']}",
            f"# Latest close: {close_end}",
            f"# Window return: {window_return:.2f}%",
            f"# High / Low: {range_high} / {range_low}",
            f"# Total volume: {quote_volume:.3f}",
            f"# Data retrieved on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
        ]

        return "\n".join(header) + frame.to_csv(index=False)
    finally:
        close_method = getattr(exchange, "close", None)
        if callable(close_method):
            try:
                close_method()
            except Exception:
                pass


def get_crypto_indicators(
    symbol: Annotated[str, "crypto pair such as BTC-USD, BTC-USDT, or BTC/USDT"],
    indicator: Annotated[str, "indicator name such as close_10_ema, rsi, macd, boll, atr, or vwma"],
    timeframe: Annotated[str, "candle timeframe such as 15m, 1h, 4h, or 1d"] = "1h",
    limit: Annotated[int, "number of candles to include in the final output window"] = 48,
    exchange_name: Annotated[str, "ccxt exchange id such as binance or bybit"] = "binance",
) -> str:
    requested = [_normalize_indicator_name(item) for item in indicator.split(",") if item.strip()]
    unsupported = [item for item in requested if item not in _CRYPTO_INDICATOR_DESCRIPTIONS]
    if unsupported:
        supported = ", ".join(sorted(_CRYPTO_INDICATOR_DESCRIPTIONS))
        raise ValueError(f"Unsupported crypto indicator(s): {', '.join(unsupported)}. Supported indicators: {supported}")

    fetch_limit = max(limit, max(_CRYPTO_INDICATOR_WINDOWS[item] for item in requested))
    exchange, market_symbol, frame = _fetch_ohlcv_frame(symbol, timeframe, fetch_limit, exchange_name)
    try:
        enriched = _prepare_indicator_frame(frame)
        enriched["timestamp_label"] = enriched["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        blocks = []
        for item in requested:
            tail = enriched[["timestamp_label", item]].tail(limit).copy()
            tail[item] = pd.to_numeric(tail[item], errors="coerce").round(6)
            latest_row = tail.dropna().tail(1)
            latest_value = "N/A"
            latest_timestamp = tail.iloc[-1]["timestamp_label"] if not tail.empty else "N/A"
            if not latest_row.empty:
                latest_value = latest_row.iloc[0][item]
                latest_timestamp = latest_row.iloc[0]["timestamp_label"]

            blocks.append(
                "\n".join(
                    [
                        f"## {item} for {market_symbol} on {exchange_name} ({timeframe})",
                        f"Latest candle: {latest_timestamp}",
                        f"Latest value: {latest_value}",
                        f"Description: {_CRYPTO_INDICATOR_DESCRIPTIONS[item]}",
                        "",
                        tail.to_csv(index=False),
                    ]
                )
            )

        return "\n\n".join(blocks)
    finally:
        close_method = getattr(exchange, "close", None)
        if callable(close_method):
            try:
                close_method()
            except Exception:
                pass