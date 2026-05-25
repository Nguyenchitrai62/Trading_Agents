from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_crypto_ohlcv(
    symbol: Annotated[str, "crypto pair such as BTC-USD, BTC-USDT, or BTC/USDT"],
    timeframe: Annotated[str, "candle timeframe such as 15m, 1h, 4h, or 1d"] = "1h",
    limit: Annotated[int, "number of candles to fetch"] = 96,
    exchange_name: Annotated[str, "ccxt exchange id such as binance or bybit"] = "binance",
) -> str:
    """
    Retrieve crypto OHLCV candles from a CCXT-supported exchange.

    This is useful for intraday and multi-timeframe crypto analysis where
    daily stock data is not enough, for example 15m, 1h, 4h, and 1d candles.
    """
    return route_to_vendor("get_crypto_ohlcv", symbol, timeframe, limit, exchange_name)


@tool
def get_crypto_indicators(
    symbol: Annotated[str, "crypto pair such as BTC-USD, BTC-USDT, or BTC/USDT"],
    indicator: Annotated[str, "indicator name such as close_10_ema, rsi, macd, boll, atr, or vwma"],
    timeframe: Annotated[str, "candle timeframe such as 15m, 1h, 4h, or 1d"] = "1h",
    limit: Annotated[int, "number of candles to include in the final output window"] = 48,
    exchange_name: Annotated[str, "ccxt exchange id such as binance or bybit"] = "binance",
) -> str:
    """
    Retrieve crypto technical indicators calculated from CCXT OHLCV candles.

    This is the crypto-native alternative to the stock-oriented indicator tool.
    Use it for BTC, ETH, and other crypto pairs on intraday timeframes like
    15m, 1h, and 4h.
    """
    return route_to_vendor("get_crypto_indicators", symbol, indicator, timeframe, limit, exchange_name)