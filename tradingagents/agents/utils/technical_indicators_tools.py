from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


INDICATOR_ALIASES = {
    "ema": "close_10_ema",
    "close_ema": "close_10_ema",
    "close ema": "close_10_ema",
    "10ema": "close_10_ema",
    "10 ema": "close_10_ema",
    "ema10": "close_10_ema",
    "50sma": "close_50_sma",
    "50 sma": "close_50_sma",
    "200sma": "close_200_sma",
    "200 sma": "close_200_sma",
}


def normalize_indicator_name(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    return INDICATOR_ALIASES.get(normalized, normalized.replace(" ", "_"))

@tool
def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """
    Retrieve a single technical indicator for a given ticker symbol.
    Uses the configured technical_indicators vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        indicator (str): A single technical indicator name, e.g. 'rsi', 'macd'. Call this tool once per indicator.
        curr_date (str): The current trading date you are trading on, YYYY-mm-dd
        look_back_days (int): How many days to look back, default is 30
    Returns:
        str: A formatted dataframe containing the technical indicators for the specified ticker symbol and indicator.
    """
    # LLMs sometimes pass multiple indicators as a comma-separated string;
    # split and process each individually.
    indicators = [normalize_indicator_name(i) for i in indicator.split(",") if i.strip()]
    results = []
    for ind in indicators:
        try:
            results.append(route_to_vendor("get_indicators", symbol, ind, curr_date, look_back_days))
        except ValueError as e:
            results.append(str(e))
    return "\n\n".join(results)