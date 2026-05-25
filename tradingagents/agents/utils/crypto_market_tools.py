from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_crypto_ohlcv(
    symbol: Annotated[str, "crypto pair such as BTC-USD, BTC-USDT, or BTC/USDT"],
    timeframe: Annotated[str, "timeframe hint such as 15m, 1h, 4h, or 1d; backend may override it with a memory-safe window"] = "1h",
    limit: Annotated[int, "candle-count hint; backend will cap and auto-select a memory-safe value under 200 candles"] = 96,
    exchange_name: Annotated[str, "ccxt exchange id such as binance or bybit"] = "binance",
) -> str:
    """
    Retrieve crypto OHLCV candles from a CCXT-supported exchange.

    The backend automatically chooses a single memory-safe timeframe and
    candle count from the active lookback window, so timeframe and limit are
    treated as hints and may be overridden.
    """
    return route_to_vendor("get_crypto_ohlcv", symbol, timeframe, limit, exchange_name)


@tool
def get_crypto_indicators(
    symbol: Annotated[str, "crypto pair such as BTC-USD, BTC-USDT, or BTC/USDT"],
    indicator: Annotated[str, "indicator name such as close_10_ema, close_50_sma, close_200_sma, rsi, macd, boll, atr, vwma, or mfi"],
    timeframe: Annotated[str, "timeframe hint such as 15m, 1h, 4h, or 1d; backend may override it with a memory-safe window"] = "1h",
    limit: Annotated[int, "output-window hint; backend may fetch more historical candles internally to compute long-window indicators on the chosen timeframe"] = 48,
    exchange_name: Annotated[str, "ccxt exchange id such as binance or bybit"] = "binance",
) -> str:
    """
    Retrieve crypto technical indicators calculated from CCXT OHLCV candles.

    This is the crypto-native alternative to the stock-oriented indicator tool.
    The backend uses one memory-safe OHLCV timeframe derived from the active
    lookback period, so timeframe is treated as a hint. It may fetch more
    historical candles internally on that same timeframe to compute long-window
    indicators such as close_200_sma.
    """
    return route_to_vendor("get_crypto_indicators", symbol, indicator, timeframe, limit, exchange_name)