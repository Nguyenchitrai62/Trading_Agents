from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_crypto_ohlcv(
    symbol: Annotated[str, "crypto pair such as BTC-USD, BTC-USDT, or BTC/USDT"],
    timeframe: Annotated[str, "timeframe such as 15m, 1h, 4h, or 1d; backend fetches the full active lookback at this timeframe"] = "1h",
    limit: Annotated[int, "legacy candle-count hint recorded for traceability; active lookback controls fetch depth"] = 96,
    exchange_name: Annotated[str, "ccxt exchange id such as binance or bybit"] = "binance",
) -> str:
    """
    Retrieve crypto OHLCV candles from a CCXT-supported exchange.

    The backend fetches the full active lookback window at the requested
    timeframe and paginates provider requests when needed.
    """
    return route_to_vendor("get_crypto_ohlcv", symbol, timeframe, limit, exchange_name)


@tool
def get_crypto_indicators(
    symbol: Annotated[str, "crypto pair such as BTC-USD, BTC-USDT, or BTC/USDT"],
    indicator: Annotated[str, "indicator name such as close_10_ema, close_50_sma, close_200_sma, rsi, macd, boll, atr, vwma, or mfi"],
    timeframe: Annotated[str, "timeframe such as 15m, 1h, 4h, or 1d; backend fetches the full active lookback at this timeframe"] = "1h",
    limit: Annotated[int, "output-window hint; backend may fetch more historical candles internally to compute long-window indicators on the chosen timeframe"] = 48,
    exchange_name: Annotated[str, "ccxt exchange id such as binance or bybit"] = "binance",
) -> str:
    """
    Retrieve crypto technical indicators calculated from CCXT OHLCV candles.

    This is the crypto-native alternative to the stock-oriented indicator tool.
    The backend uses the requested OHLCV timeframe across the active lookback
    period. It may fetch more historical candles internally on that same timeframe to compute long-window
    indicators such as close_200_sma.
    """
    return route_to_vendor("get_crypto_indicators", symbol, indicator, timeframe, limit, exchange_name)