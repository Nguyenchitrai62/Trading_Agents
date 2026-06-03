import logging
from typing import Annotated

logger = logging.getLogger(__name__)

from .ccxt_crypto import (
    get_crypto_indicators as get_ccxt_crypto_indicators,
    get_crypto_ohlcv as get_ccxt_crypto_ohlcv,
)

from .config import get_config

TOOLS_CATEGORIES = {
    "crypto_market_apis": {
        "description": "Intraday and multi-timeframe crypto OHLCV data",
        "tools": [
            "get_crypto_ohlcv",
            "get_crypto_indicators",
        ]
    },
}

VENDOR_LIST = [
    "ccxt",
]

VENDOR_METHODS = {
    "get_crypto_ohlcv": {
        "ccxt": get_ccxt_crypto_ohlcv,
    },
    "get_crypto_indicators": {
        "ccxt": get_ccxt_crypto_indicators,
    },
}

def get_category_for_method(method: str) -> str:
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    config = get_config()
    return config.get("data_vendors", {}).get(category, "ccxt")
def _is_vendor_failure_result(result) -> bool:
    if not isinstance(result, str):
        return False

    normalized = result.strip().lower()
    if not normalized:
        return True

    return (
        normalized.startswith("error ")
        or normalized.startswith("error:")
        or (
            normalized.startswith("no ")
            and (
                " found" in normalized
                or " available" in normalized
                or " returned" in normalized
            )
        )
        or "rate limit" in normalized
        or "http 429" in normalized
        or "<unavailable" in normalized
        or " timed out" in normalized
    )

def route_to_vendor(method: str, *args, **kwargs):
    category = get_category_for_method(method)
    vendor = get_vendor(category, method)

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    if vendor not in VENDOR_METHODS[method]:
        raise ValueError(f"Vendor '{vendor}' not available for '{method}'")

    impl_func = VENDOR_METHODS[method][vendor]
    try:
        result = impl_func(*args, **kwargs)
    except Exception as exc:
        logger.warning("Vendor %s failed for %s: %s", vendor, method, exc)
        return f"<{method} unavailable: {vendor}: {type(exc).__name__}>"

    if _is_vendor_failure_result(result):
        logger.warning("Vendor %s returned an unavailable result for %s", vendor, method)
        return f"<{method} unavailable: {vendor}: no data>"

    return result