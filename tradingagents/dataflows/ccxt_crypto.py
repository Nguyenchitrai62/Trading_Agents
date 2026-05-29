from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from typing import Annotated
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from .config import get_config


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

_CRYPTO_TIMEFRAME_MINUTES = {
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "8h": 480,
    "12h": 720,
    "1d": 1440,
}

_CRYPTO_OHLCV_PREVIEW_ROWS = 18
_CRYPTO_INDICATOR_PREVIEW_ROWS = 12
_BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
_BINANCE_KLINES_REQUEST_LIMIT = 1000
_BINANCE_USER_AGENT = "tradingagents/0.2"


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


def _normalize_binance_symbol(symbol: str) -> tuple[str, str]:
    normalized = symbol.strip().upper().replace(" ", "")
    if not normalized:
        raise ValueError("symbol is required")
    if "/" in normalized:
        base, quote = normalized.split("/", 1)
    elif "-" in normalized:
        base, quote = normalized.split("-", 1)
    else:
        raise ValueError(
            "Crypto symbol must look like BTC-USD, BTC-USDT, or BTC/USDT so the exchange pair can be resolved."
        )
    quote = _EXCHANGE_QUOTE_FALLBACKS.get("binance", {}).get(quote, quote)
    if not base or not quote:
        raise ValueError("Crypto symbol must include both base and quote assets.")
    market_symbol = f"{base}/{quote}"
    api_symbol = f"{base}{quote}"
    return api_symbol, market_symbol


def _normalize_indicator_name(indicator: str) -> str:
    normalized = indicator.strip().lower().replace("-", "_").replace(" ", "_")
    normalized = normalized.replace("close_10ema", "close_10_ema")
    return _CRYPTO_INDICATOR_ALIASES.get(normalized, normalized)


def _coerce_positive_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _select_crypto_window(
    lookback_days: int,
    available_timeframes: dict | None,
    requested_timeframe: str,
) -> dict[str, int | str]:
    supported = [
        timeframe
        for timeframe in _CRYPTO_TIMEFRAME_MINUTES
        if timeframe in (available_timeframes or {})
    ]
    if not supported:
        raise ValueError("No supported crypto timeframes are available for OHLCV fetching.")

    normalized_timeframe = requested_timeframe.strip().lower() or "1h"
    if normalized_timeframe not in supported:
        supported_examples = ", ".join(supported)
        raise ValueError(
            f"Timeframe '{requested_timeframe}' is not available. Supported exchange timeframes: {supported_examples}"
        )

    lookback_minutes = max(1, lookback_days) * 24 * 60
    minutes = _CRYPTO_TIMEFRAME_MINUTES[normalized_timeframe]
    candle_limit = max(1, math.ceil(lookback_minutes / minutes))
    return {
        "lookback_days": lookback_days,
        "timeframe": normalized_timeframe,
        "limit": candle_limit,
        "minutes": minutes,
    }


def _resolve_active_crypto_window(
    available_timeframes: dict | None,
    requested_timeframe: str,
) -> dict[str, int | str]:
    config = get_config()
    lookback_days = _coerce_positive_int(config.get("crypto_market_lookback_days"), 7)
    return _select_crypto_window(lookback_days, available_timeframes, requested_timeframe)


def _resolve_indicator_fetch_plan(
    requested: list[str],
    output_limit: int,
    analysis_limit: int,
) -> dict[str, int]:
    normalized_output_limit = _coerce_positive_int(output_limit, analysis_limit)
    required_window = max(_CRYPTO_INDICATOR_WINDOWS[item] for item in requested)
    fetch_limit = max(analysis_limit, normalized_output_limit, required_window)
    return {
        "output_limit": normalized_output_limit,
        "required_window": required_window,
        "fetch_limit": fetch_limit,
    }


def _fetch_ohlcv_frame(
    symbol: str,
    timeframe: str,
    limit: int,
    exchange_name: str,
    fetch_limit: int | None = None,
):
    if exchange_name.strip().lower() == "binance":
        return _fetch_binance_ohlcv_frame(symbol, timeframe, limit, fetch_limit)

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
        policy = _resolve_active_crypto_window(available_timeframes, timeframe)
        effective_timeframe = str(policy["timeframe"])
        analysis_limit = int(policy["limit"])
        effective_limit = max(analysis_limit, _coerce_positive_int(fetch_limit, analysis_limit))

        candles = exchange.fetch_ohlcv(market_symbol, timeframe=effective_timeframe, limit=effective_limit)
        if not candles:
            raise ValueError(
                f"No OHLCV data returned for {market_symbol} on {exchange_name} ({effective_timeframe})."
            )

        frame = pd.DataFrame(
            candles,
            columns=["timestamp_ms", "open", "high", "low", "close", "volume"],
        )
        frame["timestamp"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)

        for column in ["open", "high", "low", "close", "volume"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

        policy["analysis_limit"] = analysis_limit
        policy["fetch_limit"] = effective_limit
        policy["requested_timeframe"] = timeframe
        policy["requested_limit"] = limit
        return exchange, market_symbol, frame, policy
    except Exception:
        close_method = getattr(exchange, "close", None)
        if callable(close_method):
            try:
                close_method()
            except Exception:
                pass
        raise


def _fetch_binance_ohlcv_frame(
    symbol: str,
    timeframe: str,
    limit: int,
    fetch_limit: int | None = None,
):
    api_symbol, market_symbol = _normalize_binance_symbol(symbol)
    policy = _resolve_active_crypto_window(_CRYPTO_TIMEFRAME_MINUTES, timeframe)
    effective_timeframe = str(policy["timeframe"])
    analysis_limit = int(policy["limit"])
    effective_limit = max(analysis_limit, _coerce_positive_int(fetch_limit, analysis_limit))
    candles = _fetch_binance_klines(api_symbol, effective_timeframe, effective_limit)

    if not isinstance(candles, list) or not candles:
        raise ValueError(f"No OHLCV data returned for {market_symbol} on binance ({effective_timeframe}).")
    if isinstance(candles[0], dict):
        message = candles[0].get("msg") or candles[0]
        raise ValueError(f"Binance rejected pair '{market_symbol}': {message}")

    frame = pd.DataFrame(
        candles,
        columns=[
            "timestamp_ms",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time_ms",
            "quote_volume",
            "trade_count",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
            "ignore",
        ],
    )[["timestamp_ms", "open", "high", "low", "close", "volume"]]
    frame["timestamp"] = pd.to_datetime(frame["timestamp_ms"], unit="ms", utc=True)

    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    policy["analysis_limit"] = analysis_limit
    policy["fetch_limit"] = effective_limit
    policy["requested_timeframe"] = timeframe
    policy["requested_limit"] = limit
    return None, market_symbol, frame, policy


def _fetch_binance_klines(
    api_symbol: str,
    timeframe: str,
    candle_count: int,
) -> list[list]:
    interval_ms = _CRYPTO_TIMEFRAME_MINUTES[timeframe] * 60 * 1000
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    next_start_ms = end_ms - (max(1, candle_count) * interval_ms)
    candles: list[list] = []

    while len(candles) < candle_count and next_start_ms < end_ms:
        batch_limit = min(_BINANCE_KLINES_REQUEST_LIMIT, candle_count - len(candles))
        query = urlencode(
            {
                "symbol": api_symbol,
                "interval": timeframe,
                "startTime": next_start_ms,
                "endTime": end_ms,
                "limit": batch_limit,
            }
        )
        request = Request(
            f"{_BINANCE_KLINES_URL}?{query}",
            headers={"User-Agent": _BINANCE_USER_AGENT, "Accept": "application/json"},
        )

        try:
            with urlopen(request, timeout=12.0) as response:
                batch = json.loads(response.read())
        except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
            raise RuntimeError(f"Binance OHLCV fetch failed for {api_symbol}: {exc}") from exc

        if not batch:
            break
        if isinstance(batch, dict):
            message = batch.get("msg") or batch
            raise ValueError(f"Binance rejected pair '{api_symbol}': {message}")

        candles.extend(batch)
        last_open_time = int(batch[-1][0])
        following_start_ms = last_open_time + interval_ms
        if following_start_ms <= next_start_ms:
            break
        next_start_ms = following_start_ms

    return candles[-candle_count:]


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
    avg_loss_safe = avg_loss.where(avg_loss.ne(0))
    rs = avg_gain / avg_loss_safe
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

    volume_sum = working["volume"].rolling(20).sum()
    volume_sum = volume_sum.where(volume_sum.ne(0))
    working["vwma"] = (working["close"] * working["volume"]).rolling(20).sum() / volume_sum

    typical_price = (working["high"] + working["low"] + working["close"]) / 3
    raw_money_flow = typical_price * working["volume"]
    positive_flow = raw_money_flow.where(typical_price.diff() > 0, 0.0)
    negative_flow = raw_money_flow.where(typical_price.diff() < 0, 0.0).abs()
    negative_flow_sum = negative_flow.rolling(14).sum()
    negative_flow_sum = negative_flow_sum.where(negative_flow_sum.ne(0))
    flow_ratio = positive_flow.rolling(14).sum() / negative_flow_sum
    working["mfi"] = 100 - (100 / (1 + flow_ratio))

    return working


def _format_number(value: object, digits: int = 6) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "N/A"
    return f"{float(numeric):.{digits}f}"


def _format_percent(value: object) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "N/A"
    return f"{float(numeric):+.2f}%"


def _build_ohlcv_summary(frame: pd.DataFrame) -> list[str]:
    latest = frame.iloc[-1]
    first = frame.iloc[0]
    close_start = pd.to_numeric(first["close"], errors="coerce")
    close_end = pd.to_numeric(latest["close"], errors="coerce")
    window_return = ((close_end - close_start) / close_start * 100) if pd.notna(close_start) and close_start else pd.NA
    average_volume = pd.to_numeric(frame["volume"], errors="coerce").mean()
    average_range = (pd.to_numeric(frame["high"], errors="coerce") - pd.to_numeric(frame["low"], errors="coerce")).mean()

    return [
        f"- Latest close: {_format_number(close_end)}",
        f"- Window return: {_format_percent(window_return)}",
        f"- High / Low: {_format_number(frame['high'].max())} / {_format_number(frame['low'].min())}",
        f"- Total volume: {_format_number(frame['volume'].sum(), 3)}",
        f"- Average candle volume: {_format_number(average_volume, 3)}",
        f"- Average candle range: {_format_number(average_range)}",
    ]


def _build_indicator_summary(window: pd.DataFrame, indicator_name: str) -> list[str]:
    clean = pd.to_numeric(window[indicator_name], errors="coerce").dropna()
    if clean.empty:
        return [
            "- Latest value: N/A",
            "- Previous value: N/A",
            "- Window min / max: N/A / N/A",
            "- Window mean: N/A",
            "- Output-window change: N/A",
        ]

    latest_value = clean.iloc[-1]
    previous_value = clean.iloc[-2] if len(clean) > 1 else pd.NA
    start_value = clean.iloc[0]
    window_change = pd.NA
    if pd.notna(start_value) and float(start_value) != 0.0:
        window_change = (float(latest_value) - float(start_value)) / abs(float(start_value)) * 100

    return [
        f"- Latest value: {_format_number(latest_value)}",
        f"- Previous value: {_format_number(previous_value)}",
        f"- Window min / max: {_format_number(clean.min())} / {_format_number(clean.max())}",
        f"- Window mean: {_format_number(clean.mean())}",
        f"- Output-window change: {_format_percent(window_change)}",
    ]


def _format_markdown_table_cell(value: object) -> str:
    if pd.isna(value):
        return "N/A"
    return str(value).replace("\r\n", " ").replace("\n", " ").replace("|", "\\|")


def _format_compact_table(frame: pd.DataFrame, columns: list[str], preview_rows: int) -> str:
    preview = frame[columns].tail(min(preview_rows, len(frame))).copy()
    if preview.empty:
        return "No rows available."

    preview.rename(columns={"timestamp_label": "timestamp"}, inplace=True)
    header_cells = [str(column) for column in preview.columns]
    header = "| " + " | ".join(header_cells) + " |"
    separator = "| " + " | ".join(["---"] * len(header_cells)) + " |"
    rows = [
        "| " + " | ".join(_format_markdown_table_cell(value) for value in row) + " |"
        for row in preview.itertuples(index=False, name=None)
    ]
    return "\n".join([header, separator, *rows])


def get_crypto_ohlcv(
    symbol: Annotated[str, "crypto pair such as BTC-USD, BTC-USDT, or BTC/USDT"],
    timeframe: Annotated[str, "candle timeframe such as 15m, 1h, 4h, or 1d"] = "1h",
    limit: Annotated[int, "number of candles to fetch"] = 96,
    exchange_name: Annotated[str, "ccxt exchange id such as binance or bybit"] = "binance",
) -> str:
    if limit < 1:
        raise ValueError("limit must be a positive integer")

    exchange, market_symbol, frame, policy = _fetch_ohlcv_frame(symbol, timeframe, limit, exchange_name)
    try:
        price_columns = ["open", "high", "low", "close"]
        frame[price_columns] = frame[price_columns].round(6)
        frame["volume"] = frame["volume"].round(3)
        frame["timestamp"] = frame["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        header = [
            f"# Crypto OHLCV for {market_symbol} from {exchange_name}",
            (
                "# Applied analysis window: "
                f"{policy['timeframe']} x {policy['analysis_limit']} candles "
                f"for lookback {policy['lookback_days']} day(s)"
            ),
            f"# Requested window hint: {timeframe} x {limit}",
            f"# Timeframe: {policy['timeframe']}",
            f"# Total candles: {len(frame)}",
            f"# Window start: {frame.iloc[0]['timestamp']}",
            f"# Window end: {frame.iloc[-1]['timestamp']}",
            f"# Data retrieved on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "## Summary",
            *_build_ohlcv_summary(frame),
            "",
            f"## Recent candles shown ({min(_CRYPTO_OHLCV_PREVIEW_ROWS, len(frame))} of {len(frame)})",
            _format_compact_table(
                frame,
                ["timestamp", "open", "high", "low", "close", "volume"],
                _CRYPTO_OHLCV_PREVIEW_ROWS,
            ),
        ]

        return "\n".join(header)
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
    if limit < 1:
        raise ValueError("limit must be a positive integer")
    if not requested:
        raise ValueError("At least one crypto indicator is required.")
    unsupported = [item for item in requested if item not in _CRYPTO_INDICATOR_DESCRIPTIONS]
    if unsupported:
        supported = ", ".join(sorted(_CRYPTO_INDICATOR_DESCRIPTIONS))
        raise ValueError(f"Unsupported crypto indicator(s): {', '.join(unsupported)}. Supported indicators: {supported}")

    preflight_plan = _resolve_indicator_fetch_plan(requested, limit, analysis_limit=limit)
    exchange, market_symbol, frame, policy = _fetch_ohlcv_frame(
        symbol,
        timeframe,
        limit,
        exchange_name,
        fetch_limit=preflight_plan["fetch_limit"],
    )
    try:
        plan = _resolve_indicator_fetch_plan(requested, limit, int(policy["analysis_limit"]))

        enriched = _prepare_indicator_frame(frame)
        enriched["timestamp_label"] = enriched["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        blocks = []
        for item in requested:
            tail = enriched[["timestamp_label", item]].tail(plan["output_limit"]).copy()
            tail[item] = pd.to_numeric(tail[item], errors="coerce").round(6)
            latest_row = tail.dropna().tail(1)
            latest_value = "N/A"
            latest_timestamp = tail.iloc[-1]["timestamp_label"] if not tail.empty else "N/A"
            if not latest_row.empty:
                latest_value = latest_row.iloc[0][item]
                latest_timestamp = latest_row.iloc[0]["timestamp_label"]

            preview_rows = min(_CRYPTO_INDICATOR_PREVIEW_ROWS, len(tail))

            blocks.append(
                "\n".join(
                    [
                        f"## {item} for {market_symbol} on {exchange_name} ({policy['timeframe']})",
                        (
                            "Applied analysis window: "
                            f"{policy['timeframe']} x {policy['analysis_limit']} candles "
                            f"for lookback {policy['lookback_days']} day(s)"
                        ),
                        f"Indicator computation fetch depth: {policy['fetch_limit']} candles",
                        f"Indicator output window: {plan['output_limit']} candles",
                        f"Requested window hint: {timeframe} x {limit}",
                        f"Latest candle: {latest_timestamp}",
                        f"Latest value: {latest_value}",
                        f"Description: {_CRYPTO_INDICATOR_DESCRIPTIONS[item]}",
                        "",
                        "### Indicator summary",
                        *_build_indicator_summary(tail, item),
                        "",
                        f"### Recent indicator rows shown ({preview_rows} of {len(tail)})",
                        _format_compact_table(tail, ["timestamp_label", item], _CRYPTO_INDICATOR_PREVIEW_ROWS),
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