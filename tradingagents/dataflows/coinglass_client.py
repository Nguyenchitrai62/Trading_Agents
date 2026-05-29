from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests


DEFAULT_COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com"
DEFAULT_EXCHANGE_LIST = "Binance,OKX,Bybit"
DEFAULT_PRIMARY_EXCHANGE = "Binance"
DEFAULT_OPTION_EXCHANGE = "Deribit"
DEFAULT_INTERVAL = "4h"
DEFAULT_RANGE = "4h"
DEFAULT_ACCUMULATED_FUNDING_RANGE = "1d"
DEFAULT_LIMIT = 42
MAX_HISTORY_LIMIT = 1000

PACKAGE_ORDER = (
    "derivatives_positioning",
    "funding_pressure",
    "liquidation_risk",
    "exchange_reserves",
    "institutional_flow",
    "options_context",
    "macro_cycle_context",
)

PACKAGE_LABELS = {
    "derivatives_positioning": "Derivatives positioning",
    "funding_pressure": "Funding pressure",
    "liquidation_risk": "Liquidation and taker pressure",
    "exchange_reserves": "Exchange reserves",
    "institutional_flow": "ETF and Grayscale flow",
    "options_context": "Options context",
    "macro_cycle_context": "Macro and cycle context",
}

PACKAGE_AGENT_HINTS = {
    "derivatives_positioning": "Market Analyst, Trader, Research Manager",
    "funding_pressure": "Market Analyst, Flow Analyst, Trader, Risk Room",
    "liquidation_risk": "Trader, Risk Room, Portfolio Manager",
    "exchange_reserves": "Flow Analyst, Research Manager, Risk Room",
    "institutional_flow": "Flow Analyst, Research Manager, Portfolio Manager",
    "options_context": "Risk Room, Portfolio Manager",
    "macro_cycle_context": "Market Analyst, Flow Analyst, Portfolio Manager",
}


ParamsFactory = Callable[[str, str, int], dict[str, object]]


@dataclass(frozen=True)
class CoinGlassEndpointSpec:
    key: str
    package: str
    title: str
    path: str
    params_factory: ParamsFactory
    source_type: str = "flow"
    freshness: str = "realtime"
    filter_symbol_from_payload: bool = False

    def params(self, coin_symbol: str, pair_symbol: str, limit: int) -> dict[str, object]:
        return self.params_factory(coin_symbol, pair_symbol, limit)


def _no_params(_: str, __: str, ___: int) -> dict[str, object]:
    return {}


def _coin_params(coin: str, _: str, __: int) -> dict[str, object]:
    return {"symbol": coin}


def _pair_history_params(coin: str, pair: str, limit: int) -> dict[str, object]:
    return {
        "exchange": DEFAULT_PRIMARY_EXCHANGE,
        "symbol": pair,
        "interval": DEFAULT_INTERVAL,
        "limit": limit,
    }


HIGH_VALUE_ENDPOINTS: tuple[CoinGlassEndpointSpec, ...] = (
    CoinGlassEndpointSpec(
        key="futures_pairs_markets",
        package="derivatives_positioning",
        title="Futures pairs market snapshot",
        path="/api/futures/pairs-markets",
        params_factory=_coin_params,
    ),
    CoinGlassEndpointSpec(
        key="futures_open_interest_exchange_list",
        package="derivatives_positioning",
        title="Open interest by exchange",
        path="/api/futures/open-interest/exchange-list",
        params_factory=_coin_params,
    ),
    CoinGlassEndpointSpec(
        key="futures_open_interest_aggregated_history",
        package="derivatives_positioning",
        title="Aggregated open-interest history",
        path="/api/futures/open-interest/aggregated-history",
        params_factory=lambda coin, _pair, limit: {
            "symbol": coin,
            "interval": DEFAULT_INTERVAL,
            "limit": limit,
            "unit": "usd",
        },
    ),
    CoinGlassEndpointSpec(
        key="futures_funding_rate_exchange_list",
        package="funding_pressure",
        title="Current funding rate by exchange",
        path="/api/futures/funding-rate/exchange-list",
        params_factory=_no_params,
        filter_symbol_from_payload=True,
    ),
    CoinGlassEndpointSpec(
        key="futures_funding_rate_accumulated_exchange_list",
        package="funding_pressure",
        title="Accumulated funding by exchange",
        path="/api/futures/funding-rate/accumulated-exchange-list",
        params_factory=lambda _coin, _pair, _limit: {"range": DEFAULT_ACCUMULATED_FUNDING_RANGE},
        filter_symbol_from_payload=True,
    ),
    CoinGlassEndpointSpec(
        key="futures_funding_rate_oi_weight_history",
        package="funding_pressure",
        title="OI-weighted funding history",
        path="/api/futures/funding-rate/oi-weight-history",
        params_factory=lambda coin, _pair, limit: {
            "symbol": coin,
            "interval": DEFAULT_INTERVAL,
            "limit": limit,
        },
    ),
    CoinGlassEndpointSpec(
        key="futures_liquidation_aggregated_history",
        package="liquidation_risk",
        title="Aggregated liquidation history",
        path="/api/futures/liquidation/aggregated-history",
        params_factory=lambda coin, _pair, limit: {
            "exchange_list": DEFAULT_EXCHANGE_LIST,
            "symbol": coin,
            "interval": DEFAULT_INTERVAL,
            "limit": limit,
        },
    ),
    CoinGlassEndpointSpec(
        key="futures_taker_buy_sell_volume_exchange_list",
        package="liquidation_risk",
        title="Taker buy/sell pressure by exchange",
        path="/api/futures/taker-buy-sell-volume/exchange-list",
        params_factory=lambda coin, _pair, _limit: {"symbol": coin, "range": DEFAULT_RANGE},
    ),
    CoinGlassEndpointSpec(
        key="exchange_balance_list",
        package="exchange_reserves",
        title="Exchange reserve snapshot",
        path="/api/exchange/balance/list",
        params_factory=_coin_params,
    ),
    CoinGlassEndpointSpec(
        key="exchange_balance_chart",
        package="exchange_reserves",
        title="Exchange reserve history",
        path="/api/exchange/balance/chart",
        params_factory=_coin_params,
        freshness="recent",
    ),
    CoinGlassEndpointSpec(
        key="etf_bitcoin_flow_history",
        package="institutional_flow",
        title="Bitcoin ETF flow history",
        path="/api/etf/bitcoin/flow-history",
        params_factory=_no_params,
        freshness="recent",
    ),
    CoinGlassEndpointSpec(
        key="etf_bitcoin_list",
        package="institutional_flow",
        title="Bitcoin ETF list and metadata",
        path="/api/etf/bitcoin/list",
        params_factory=_no_params,
        freshness="realtime",
    ),
    CoinGlassEndpointSpec(
        key="grayscale_holdings_list",
        package="institutional_flow",
        title="Grayscale holdings list",
        path="/api/grayscale/holdings-list",
        params_factory=_no_params,
        freshness="recent",
    ),
    CoinGlassEndpointSpec(
        key="option_info",
        package="options_context",
        title="Options market overview",
        path="/api/option/info",
        params_factory=_coin_params,
    ),
    CoinGlassEndpointSpec(
        key="option_max_pain",
        package="options_context",
        title="Deribit option max pain",
        path="/api/option/max-pain",
        params_factory=lambda coin, _pair, _limit: {
            "symbol": coin,
            "exchange": DEFAULT_OPTION_EXCHANGE,
        },
    ),
    CoinGlassEndpointSpec(
        key="coinbase_premium_index",
        package="macro_cycle_context",
        title="Coinbase premium index",
        path="/api/coinbase-premium-index",
        params_factory=lambda _coin, _pair, limit: {
            "interval": DEFAULT_INTERVAL,
            "limit": limit,
        },
    ),
    CoinGlassEndpointSpec(
        key="fear_greed_history",
        package="macro_cycle_context",
        title="Fear and greed history",
        path="/api/index/fear-greed-history",
        params_factory=_no_params,
        freshness="recent",
    ),
    CoinGlassEndpointSpec(
        key="stablecoin_marketcap_history",
        package="macro_cycle_context",
        title="Stablecoin market-cap history",
        path="/api/index/stableCoin-marketCap-history",
        params_factory=_no_params,
        freshness="recent",
    ),
    CoinGlassEndpointSpec(
        key="stock_flow",
        package="macro_cycle_context",
        title="Bitcoin stock-to-flow model",
        path="/api/index/stock-flow",
        params_factory=_no_params,
        freshness="historical",
    ),
)


class CoinGlassClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_COINGLASS_BASE_URL, timeout_seconds: float = 10.0):
        self.api_key = api_key.strip()
        self.base_url = (base_url or DEFAULT_COINGLASS_BASE_URL).strip().rstrip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds or 10.0))

    def fetch(self, spec: CoinGlassEndpointSpec, coin_symbol: str, pair_symbol: str, limit: int) -> dict[str, Any]:
        started_at = time.monotonic()
        params = spec.params(coin_symbol, pair_symbol, limit)
        url = urljoin(self.base_url + "/", spec.path.lstrip("/"))
        result: dict[str, Any] = {
            "key": spec.key,
            "package": spec.package,
            "package_label": PACKAGE_LABELS.get(spec.package, spec.package),
            "title": spec.title,
            "path": spec.path,
            "params": params,
            "source": _format_source(spec.path, params),
            "source_type": spec.source_type,
            "freshness": spec.freshness,
            "status": "error",
            "http_status": None,
            "elapsed_ms": None,
            "rate_limit": {},
            "summary": {},
            "error": "",
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers={
                    "CG-API-KEY": self.api_key,
                    "Accept": "application/json",
                    "User-Agent": "TradingAgents/0.1 CoinGlass dataflow",
                },
                timeout=self.timeout_seconds,
            )
            result["http_status"] = response.status_code
            result["rate_limit"] = _extract_rate_limit_headers(response.headers)
            response.raise_for_status()
            payload = response.json()
            payload = _maybe_filter_symbol_payload(payload, coin_symbol) if spec.filter_symbol_from_payload else payload
            api_error = _coinglass_api_error(payload)
            result["summary"] = summarize_payload(payload)
            if api_error:
                result["error"] = api_error
                return result
            result["status"] = "ok"
            return result
        except requests.Timeout:
            result["error"] = f"CoinGlass request timed out after {self.timeout_seconds:.1f}s."
            return result
        except requests.HTTPError as exc:
            response = exc.response
            status_code = response.status_code if response is not None else "unknown"
            body = _safe_response_text(response)
            result["error"] = f"CoinGlass HTTP {status_code}: {body}".strip()
            return result
        except requests.RequestException as exc:
            result["error"] = f"CoinGlass request failed: {exc}"
            return result
        except ValueError as exc:
            result["error"] = f"CoinGlass returned non-JSON data: {exc}"
            return result
        finally:
            result["elapsed_ms"] = round((time.monotonic() - started_at) * 1000, 1)


def normalize_coin_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper().replace(" ", "")
    if not value:
        return "BTC"
    if ":" in value:
        value = value.rsplit(":", 1)[-1]
    for separator in ("-", "/", "_"):
        if separator in value:
            return re.split(r"[-/_]", value, maxsplit=1)[0] or "BTC"
    for quote in ("USDT", "USDC", "USD", "BUSD", "BTC", "ETH"):
        if value.endswith(quote) and len(value) > len(quote):
            return value[: -len(quote)]
    return value


def normalize_pair_symbol(symbol: str, coin_symbol: str) -> str:
    value = str(symbol or "").strip().upper().replace(" ", "")
    if ":" in value:
        value = value.rsplit(":", 1)[-1]
    if "/" in value or "-" in value or "_" in value:
        base, quote = re.split(r"[-/_]", value, maxsplit=1)
        return f"{base}{quote}"
    if value == coin_symbol:
        return f"{coin_symbol}USDT"
    if value:
        return value
    return f"{coin_symbol}USDT"


def fetch_high_value_snapshot(
    *,
    api_key: str,
    symbol: str,
    base_url: str = DEFAULT_COINGLASS_BASE_URL,
    timeout_seconds: float = 10.0,
    history_limit: int = DEFAULT_LIMIT,
    request_interval_seconds: float = 0.0,
    on_endpoint_result: Callable[[dict[str, Any]], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    coin_symbol = normalize_coin_symbol(symbol)
    pair_symbol = normalize_pair_symbol(symbol, coin_symbol)
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if not api_key.strip():
        return {
            "configured": False,
            "enabled": False,
            "symbol": coin_symbol,
            "pair_symbol": pair_symbol,
            "fetched_at": fetched_at,
            "endpoint_count": len(HIGH_VALUE_ENDPOINTS),
            "successful_endpoint_count": 0,
            "failed_endpoint_count": 0,
            "packages": _empty_packages(),
            "results": [],
            "warnings": ["CoinGlass API key is not configured."],
        }

    client = CoinGlassClient(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)
    results: list[dict[str, Any]] = []
    safe_history_limit = max(1, min(MAX_HISTORY_LIMIT, int(history_limit or DEFAULT_LIMIT)))
    for spec in HIGH_VALUE_ENDPOINTS:
        if cancel_check:
            cancel_check()
        result = client.fetch(spec, coin_symbol, pair_symbol, safe_history_limit)
        results.append(result)
        if on_endpoint_result:
            on_endpoint_result(result)
        if request_interval_seconds > 0:
            time.sleep(request_interval_seconds)

    packages = _build_packages(results)
    successful = sum(1 for result in results if result.get("status") == "ok")
    failed = len(results) - successful
    return {
        "configured": True,
        "enabled": True,
        "symbol": coin_symbol,
        "pair_symbol": pair_symbol,
        "fetched_at": fetched_at,
        "base_url": client.base_url,
        "endpoint_count": len(results),
        "successful_endpoint_count": successful,
        "failed_endpoint_count": failed,
        "packages": packages,
        "results": results,
        "warnings": [
            f"{result.get('title') or result.get('key')} failed: {result.get('error')}"
            for result in results
            if result.get("status") != "ok"
        ],
    }


def build_coinglass_prompt_context(
    snapshot: dict[str, Any],
    *,
    focus_packages: Iterable[str] | None = None,
    char_limit: int = 24000,
) -> str:
    if not snapshot:
        return ""

    if not snapshot.get("enabled"):
        warnings = "; ".join(str(item) for item in snapshot.get("warnings") or [])
        return (
            "CoinGlass high-value data was not fetched for this run."
            + (f" Reason: {warnings}" if warnings else "")
            + " Do not invent CoinGlass metrics when this context is unavailable."
        )

    focus_set = set(focus_packages or PACKAGE_ORDER)
    selected_packages = [
        package
        for package in PACKAGE_ORDER
        if package in focus_set and package in (snapshot.get("packages") or {})
    ]
    if not selected_packages:
        selected_packages = [package for package in PACKAGE_ORDER if package in (snapshot.get("packages") or {})]

    lines: list[str] = [
        (
            f"CoinGlass high-value snapshot for {snapshot.get('symbol')} "
            f"(pair {snapshot.get('pair_symbol')}) fetched at {snapshot.get('fetched_at')} UTC."
        ),
        (
            f"Endpoint health: {snapshot.get('successful_endpoint_count', 0)}/"
            f"{snapshot.get('endpoint_count', 0)} succeeded."
        ),
        "Use this prefetched source as current market evidence. If an endpoint failed, state the data gap instead of filling it in.",
    ]

    for package in selected_packages:
        package_payload = (snapshot.get("packages") or {}).get(package) or {}
        label = package_payload.get("label") or PACKAGE_LABELS.get(package, package)
        results = package_payload.get("results") or []
        ok_count = sum(1 for result in results if result.get("status") == "ok")
        lines.append("")
        lines.append(f"## {label}")
        lines.append(
            f"Package health: {ok_count}/{len(results)} endpoints. Agent use: {PACKAGE_AGENT_HINTS.get(package, 'general analysis')}."
        )
        for result in results:
            status = result.get("status")
            source = result.get("source")
            title = result.get("title")
            elapsed_ms = result.get("elapsed_ms")
            if status != "ok":
                lines.append(f"- {title}: unavailable from `{source}`; error={result.get('error') or 'unknown'}")
                continue
            summary = result.get("summary") or {}
            summary_json = json.dumps(summary, ensure_ascii=False, sort_keys=True, default=str)
            lines.append(f"- {title}: `{source}`; elapsed_ms={elapsed_ms}; summary={summary_json}")

    return _trim_text("\n".join(lines), char_limit)


def build_coinglass_package_contexts(snapshot: dict[str, Any], *, char_limit: int = 0) -> dict[str, str]:
    contexts: dict[str, str] = {}
    for package in PACKAGE_ORDER:
        contexts[package] = build_coinglass_prompt_context(
            snapshot,
            focus_packages=(package,),
            char_limit=char_limit,
        )
    return contexts


def build_coinglass_evidence_items(snapshot: dict[str, Any], analysis_date: str) -> list[dict[str, Any]]:
    if not snapshot or not snapshot.get("enabled"):
        return []

    items: list[dict[str, Any]] = []
    packages = snapshot.get("packages") or {}
    for package in PACKAGE_ORDER:
        package_payload = packages.get(package) or {}
        results = package_payload.get("results") or []
        ok_results = [result for result in results if result.get("status") == "ok"]
        if not ok_results:
            continue

        endpoint_titles = ", ".join(str(result.get("title") or result.get("key")) for result in ok_results)
        latest_source = str(ok_results[0].get("source") or "CoinGlass")
        rows = [
            int((result.get("summary") or {}).get("item_count") or 0)
            for result in ok_results
            if isinstance((result.get("summary") or {}).get("item_count"), int)
        ]
        row_hint = f"{sum(rows)} summarized rows" if rows else f"{len(ok_results)} endpoint summaries"
        freshness = _combined_freshness(ok_results)
        items.append(
            {
                "agent": "coinglass",
                "agent_label": "CoinGlass Data Orchestrator",
                "report_section": package,
                "claim": (
                    f"CoinGlass package `{package}` was prefetched for {snapshot.get('symbol')} "
                    f"with {len(ok_results)}/{len(results)} high-value endpoints available."
                ),
                "source": latest_source,
                "source_type": "flow",
                "timestamp": snapshot.get("fetched_at") or analysis_date,
                "metric": PACKAGE_LABELS.get(package, package),
                "value": f"{row_hint}; endpoints: {endpoint_titles}",
                "direction": "unknown",
                "confidence": 0.78 if len(ok_results) == len(results) else 0.62,
                "freshness": freshness,
                "notes": "Backend-prefetched CoinGlass context shared across agents in this analysis run.",
            }
        )
    return items


def summarize_payload(payload: object) -> dict[str, Any]:
    data = _unwrap_coinglass_data(payload)
    summary: dict[str, Any] = {
        "data_kind": type(data).__name__,
    }

    if isinstance(payload, dict):
        api_code = payload.get("code") if "code" in payload else payload.get("status")
        api_message = payload.get("msg") if "msg" in payload else payload.get("message")
        if api_code not in (None, ""):
            summary["api_code"] = api_code
        if api_message:
            summary["api_message"] = _safe_scalar(api_message)

    if isinstance(data, list):
        summary["item_count"] = len(data)
        summary["fields"] = _collect_fields(data)
        summary["sample_items"] = _compact_json_value(data[:2])
        summary["latest_items"] = _compact_json_value(data[-3:])
        numeric = _numeric_summary(data)
        if numeric:
            summary["numeric_summary"] = numeric
        return summary

    if isinstance(data, dict):
        summary["keys"] = sorted(str(key) for key in list(data.keys())[:40])
        nested_list_key, nested_items = _largest_nested_list(data)
        if nested_list_key and nested_items is not None:
            summary["primary_list_key"] = nested_list_key
            summary["item_count"] = len(nested_items)
            summary["fields"] = _collect_fields(nested_items)
            summary["sample_items"] = _compact_json_value(nested_items[:2])
            summary["latest_items"] = _compact_json_value(nested_items[-3:])
            numeric = _numeric_summary(nested_items)
            if numeric:
                summary["numeric_summary"] = numeric
        else:
            summary["data"] = _compact_json_value(data)
        return summary

    summary["data"] = _compact_json_value(data)
    return summary


def _build_packages(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    packages = _empty_packages()
    for result in results:
        package = str(result.get("package") or "other")
        packages.setdefault(
            package,
            {
                "key": package,
                "label": PACKAGE_LABELS.get(package, package),
                "results": [],
            },
        )
        packages[package]["results"].append(result)
    return packages


def _empty_packages() -> dict[str, dict[str, Any]]:
    return {
        package: {
            "key": package,
            "label": PACKAGE_LABELS.get(package, package),
            "results": [],
        }
        for package in PACKAGE_ORDER
    }


def _format_source(path: str, params: dict[str, object]) -> str:
    if not params:
        return path
    pairs = [f"{key}={value}" for key, value in params.items()]
    return f"{path}?{'&'.join(pairs)}"


def _extract_rate_limit_headers(headers: object) -> dict[str, str]:
    if not headers:
        return {}
    candidates = ("API-KEY-MAX-LIMIT", "API-KEY-USE-LIMIT", "X-RateLimit-Limit", "X-RateLimit-Remaining")
    return {name: str(headers.get(name)) for name in candidates if headers.get(name) is not None}


def _safe_response_text(response: requests.Response | None) -> str:
    if response is None:
        return ""
    text = (response.text or "").strip()
    return _trim_text(text, 500)


def _coinglass_api_error(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    code = payload.get("code")
    if code in (None, "", 0, "0", "200", 200, "success", "SUCCESS"):
        return ""
    message = payload.get("msg") or payload.get("message") or payload.get("error") or "API returned non-success code"
    return f"code={code}; message={message}"


def _unwrap_coinglass_data(payload: object) -> object:
    if isinstance(payload, dict):
        for key in ("data", "result", "items"):
            if key in payload:
                return payload.get(key)
    return payload


def _maybe_filter_symbol_payload(payload: object, coin_symbol: str) -> object:
    if not isinstance(payload, dict):
        return payload
    data = payload.get("data")
    filtered = _filter_list_by_symbol(data, coin_symbol)
    if filtered is None:
        return payload
    clone = dict(payload)
    clone["data"] = filtered
    clone["filtered_symbol"] = coin_symbol
    return clone


def _filter_list_by_symbol(value: object, coin_symbol: str) -> list[object] | None:
    if isinstance(value, list):
        matched = [item for item in value if _item_matches_symbol(item, coin_symbol)]
        has_symbol_fields = any(_item_has_symbol_field(item) for item in value if isinstance(item, dict))
        if matched or has_symbol_fields:
            return matched
        return None

    if isinstance(value, dict):
        for key, nested in value.items():
            if isinstance(nested, list):
                matched = [item for item in nested if _item_matches_symbol(item, coin_symbol)]
                has_symbol_fields = any(_item_has_symbol_field(item) for item in nested if isinstance(item, dict))
                if matched or has_symbol_fields:
                    clone = dict(value)
                    clone[key] = matched
                    return [clone]
    return None


def _item_has_symbol_field(item: object) -> bool:
    return isinstance(item, dict) and any("symbol" in str(key).lower() or "coin" in str(key).lower() for key in item)


def _item_matches_symbol(item: object, coin_symbol: str) -> bool:
    if not isinstance(item, dict):
        return False
    target = coin_symbol.upper()
    for key, value in item.items():
        key_text = str(key).lower()
        if not any(marker in key_text for marker in ("symbol", "coin", "pair", "instrument", "base")):
            continue
        value_text = str(value or "").upper().replace("_", "").replace("-", "").replace("/", "")
        if value_text == target or value_text.startswith(target):
            return True
    return False


def _compact_json_value(value: object, max_depth: int = 4, max_items: int = 5) -> object:
    if max_depth <= 0:
        return _safe_scalar(value)
    if isinstance(value, dict):
        items = list(value.items())[:max_items]
        compact = {str(key): _compact_json_value(val, max_depth - 1, max_items) for key, val in items}
        if len(value) > max_items:
            compact["..."] = f"{len(value) - max_items} more key(s)"
        return compact
    if isinstance(value, list):
        compact_list = [_compact_json_value(item, max_depth - 1, max_items) for item in value[:max_items]]
        if len(value) > max_items:
            compact_list.append(f"... {len(value) - max_items} more item(s)")
        return compact_list
    return _safe_scalar(value)


def _safe_scalar(value: object) -> object:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = re.sub(r"\s+", " ", str(value)).strip()
    return _trim_text(text, 240)


def _collect_fields(items: list[object]) -> list[str]:
    fields: set[str] = set()
    for item in items[:10]:
        if isinstance(item, dict):
            fields.update(str(key) for key in item.keys())
    return sorted(fields)[:40]


def _largest_nested_list(data: dict[str, object]) -> tuple[str | None, list[object] | None]:
    best_key: str | None = None
    best_items: list[object] | None = None
    for key, value in data.items():
        if isinstance(value, list) and (best_items is None or len(value) > len(best_items)):
            best_key = str(key)
            best_items = value
    return best_key, best_items


def _numeric_summary(items: list[object]) -> dict[str, dict[str, float]]:
    numeric_values: dict[str, list[float]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            number = _coerce_number(value)
            if number is None:
                continue
            numeric_values.setdefault(str(key), []).append(number)

    summary: dict[str, dict[str, float]] = {}
    for key, values in list(numeric_values.items())[:12]:
        if not values:
            continue
        summary[key] = {
            "latest": round(values[-1], 8),
            "min": round(min(values), 8),
            "max": round(max(values), 8),
        }
    return summary


def _coerce_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text or len(text) > 32:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _combined_freshness(results: list[dict[str, Any]]) -> str:
    freshness_rank = {"realtime": 0, "recent": 1, "historical": 2, "stale": 3, "unknown": 4}
    freshness_values = [str(result.get("freshness") or "unknown") for result in results]
    return min(freshness_values, key=lambda value: freshness_rank.get(value, 4)) if freshness_values else "unknown"


def _trim_text(value: str, limit: int) -> str:
    if limit <= 0 or len(value) <= limit:
        return value
    suffix = "\n[truncated]"
    return value[: max(0, limit - len(suffix))].rstrip() + suffix
