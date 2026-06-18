from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests

from tradingagents.dataflows.endpoint_summary import format_endpoint_summaries_for_prompt

# Module-level shared session: one connection pool reused across all
# CoinGlassClient instances in this process.  Created lazily under lock,
# closed via atexit or when explicitly requested.
_SHARED_SESSION: requests.Session | None = None
_SHARED_SESSION_LOCK = threading.Lock()


def _get_shared_session() -> requests.Session:
    """Return the module-level shared session, creating it lazily (thread-safe)."""
    global _SHARED_SESSION  # noqa: PLW0603
    if _SHARED_SESSION is not None:
        return _SHARED_SESSION
    with _SHARED_SESSION_LOCK:
        if _SHARED_SESSION is not None:
            return _SHARED_SESSION
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=4,
            pool_maxsize=8,
            max_retries=0,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _SHARED_SESSION = session
        return session


def close_shared_session() -> None:
    """Close the module-level shared session and drop the reference."""
    global _SHARED_SESSION  # noqa: PLW0603
    with _SHARED_SESSION_LOCK:
        if _SHARED_SESSION is not None:
            try:
                _SHARED_SESSION.close()
            except Exception:
                pass
            _SHARED_SESSION = None


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
    "derivatives_positioning": "Market Analyst, Onchain Analyst, Risk Room",
    "funding_pressure": "Market Analyst, Onchain Analyst, Risk Room",
    "liquidation_risk": "Onchain Analyst, Risk Room, Portfolio Manager",
    "exchange_reserves": "Onchain Analyst, Risk Room",
    "institutional_flow": "Onchain Analyst, Portfolio Manager",
    "options_context": "Risk Room, Portfolio Manager",
    "macro_cycle_context": "Market Analyst, Onchain Analyst, Portfolio Manager",
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
    applicable_coins: frozenset[str] | None = None
    is_macro: bool = False

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
        applicable_coins=frozenset({"BTC"}),
    ),
    CoinGlassEndpointSpec(
        key="etf_bitcoin_list",
        package="institutional_flow",
        title="Bitcoin ETF list and metadata",
        path="/api/etf/bitcoin/list",
        params_factory=_no_params,
        freshness="realtime",
        applicable_coins=frozenset({"BTC"}),
    ),
    CoinGlassEndpointSpec(
        key="grayscale_holdings_list",
        package="institutional_flow",
        title="Grayscale holdings list",
        path="/api/grayscale/holdings-list",
        params_factory=_no_params,
        freshness="recent",
        applicable_coins=frozenset({"BTC"}),
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
        applicable_coins=frozenset({"BTC"}),
    ),
    CoinGlassEndpointSpec(
        key="fear_greed_history",
        package="macro_cycle_context",
        title="Fear and greed history",
        path="/api/index/fear-greed-history",
        params_factory=_no_params,
        freshness="recent",
        is_macro=True,
    ),
    CoinGlassEndpointSpec(
        key="stablecoin_marketcap_history",
        package="macro_cycle_context",
        title="Stablecoin market-cap history",
        path="/api/index/stableCoin-marketCap-history",
        params_factory=_no_params,
        freshness="recent",
        is_macro=True,
    ),
    CoinGlassEndpointSpec(
        key="stock_flow",
        package="macro_cycle_context",
        title="Bitcoin stock-to-flow model",
        path="/api/index/stock-flow",
        params_factory=_no_params,
        freshness="historical",
        applicable_coins=frozenset({"BTC"}),
    ),
)


class CoinGlassClient:
    def __init__(self, api_key: str, base_url: str = DEFAULT_COINGLASS_BASE_URL, timeout_seconds: float = 10.0):
        self.api_key = api_key.strip()
        self.base_url = (base_url or DEFAULT_COINGLASS_BASE_URL).strip().rstrip("/")
        self.timeout_seconds = max(1.0, float(timeout_seconds or 10.0))

    def _ensure_session(self) -> requests.Session:
        return _get_shared_session()

    def close(self) -> None:
        pass  # Shared session is managed at module level.

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
            response = self._ensure_session().get(
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
            result["payload"] = payload
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
    concurrency_limit: int = 1,
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
    try:
        safe_history_limit = max(1, min(MAX_HISTORY_LIMIT, int(history_limit or DEFAULT_LIMIT)))
        safe_concurrency_limit = max(1, int(concurrency_limit or 1))
        applicable_endpoints = [
            spec
            for spec in HIGH_VALUE_ENDPOINTS
            if spec.applicable_coins is None or coin_symbol in spec.applicable_coins
        ]
        results_by_index: list[dict[str, Any] | None] = [None] * len(applicable_endpoints)

        def store_result(index: int, result: dict[str, Any]) -> None:
            results_by_index[index] = result
            if on_endpoint_result:
                on_endpoint_result(result)

        if safe_concurrency_limit == 1:
            for index, spec in enumerate(applicable_endpoints):
                if cancel_check:
                    cancel_check()
                result = client.fetch(spec, coin_symbol, pair_symbol, safe_history_limit)
                store_result(index, result)
                if request_interval_seconds > 0 and index + 1 < len(applicable_endpoints):
                    time.sleep(request_interval_seconds)
        else:
            with ThreadPoolExecutor(max_workers=safe_concurrency_limit, thread_name_prefix="coinglass") as executor:
                future_map = {}
                for index, spec in enumerate(applicable_endpoints):
                    if cancel_check:
                        cancel_check()
                    future = executor.submit(client.fetch, spec, coin_symbol, pair_symbol, safe_history_limit)
                    future_map[future] = index
                    if request_interval_seconds > 0 and index + 1 < len(applicable_endpoints):
                        time.sleep(request_interval_seconds)

                for future in as_completed(future_map):
                    if cancel_check:
                        cancel_check()
                    index = future_map[future]
                    store_result(index, future.result())

        results = [result for result in results_by_index if result is not None]

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
            "total_available_endpoint_count": len(HIGH_VALUE_ENDPOINTS),
            "skipped_endpoint_count": len(HIGH_VALUE_ENDPOINTS) - len(applicable_endpoints),
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
    finally:
        client.close()


def build_coinglass_prompt_context(
    snapshot: dict[str, Any],
    *,
    focus_packages: Iterable[str] | None = None,
    char_limit: int = 50000,
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
    endpoint_summary_block = format_endpoint_summaries_for_prompt(
        snapshot.get("endpoint_summaries") or [],
        focus_packages=selected_packages,
    )
    if endpoint_summary_block:
        lines.append("")
        lines.append(endpoint_summary_block)

    for package in selected_packages:
        section = _build_coinglass_package_section(snapshot, package)
        if not section:
            continue
        lines.append("")
        lines.append(section)

    return _trim_text("\n".join(lines), char_limit)


def build_coinglass_package_contexts(snapshot: dict[str, Any], *, char_limit: int = 0) -> dict[str, str]:
    contexts: dict[str, str] = {}
    for package in PACKAGE_ORDER:
        contexts[package] = _trim_text(_build_coinglass_package_section(snapshot, package), char_limit)
    return contexts


def build_coinglass_evidence_items(
    snapshot: dict[str, Any],
    analysis_date: str,
    *,
    owner_agent_key: str,
    owner_agent_label: str,
) -> list[dict[str, Any]]:
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
                "agent": owner_agent_key,
                "agent_label": owner_agent_label,
                "report_section": package,
                "claim": (
                    f"CoinGlass package `{package}` was collected for the {owner_agent_label} path on {snapshot.get('symbol')} "
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
                "notes": f"CoinGlass context was collected for the {owner_agent_label} path and then shared with the wider analysis run.",
            }
        )
    return items


def summarize_payload(payload: object) -> dict[str, Any]:
    data = _unwrap_coinglass_data(payload)
    summary: dict[str, Any] = {
        "data_kind": type(data).__name__,
    }
    sample_row_limit, recent_row_limit = _get_preview_row_limits()

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
        formatted = _format_timestamps_in_items(data)
        summary["sample_items"] = _compact_json_value(formatted[:sample_row_limit])
        summary["latest_items"] = _compact_json_value(formatted[-recent_row_limit:])
        numeric = _numeric_summary(formatted)
        if numeric:
            summary["numeric_summary"] = numeric
        return summary

    if isinstance(data, dict):
        summary["keys"] = sorted(str(key) for key in data.keys())
        parallel_list_summary = _summarize_parallel_scalar_lists(
            data,
            sample_row_limit=sample_row_limit,
            recent_row_limit=recent_row_limit,
        )
        if parallel_list_summary is not None:
            summary.update(parallel_list_summary)
            return summary
        nested_list_key, nested_items = _largest_nested_list(data)
        if nested_list_key and nested_items is not None:
            summary["primary_list_key"] = nested_list_key
            summary["item_count"] = len(nested_items)
            summary["fields"] = _collect_fields(nested_items)
            formatted_nested = _format_timestamps_in_items(nested_items)
            summary["sample_items"] = _compact_json_value(formatted_nested[:sample_row_limit])
            summary["latest_items"] = _compact_json_value(formatted_nested[-recent_row_limit:])
            numeric = _numeric_summary(formatted_nested)
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


def _build_coinglass_package_section(snapshot: dict[str, Any], package: str) -> str:
    package_payload = (snapshot.get("packages") or {}).get(package) or {}
    label = package_payload.get("label") or PACKAGE_LABELS.get(package, package)
    results = package_payload.get("results") or []
    if not results:
        return ""

    ok_count = sum(1 for result in results if result.get("status") == "ok")
    lines = [
        f"## {label}",
        f"Package health: {ok_count}/{len(results)} endpoints. Agent use: {PACKAGE_AGENT_HINTS.get(package, 'general analysis')}.",
    ]
    endpoint_summary_block = format_endpoint_summaries_for_prompt(
        snapshot.get("endpoint_summaries") or [],
        focus_packages=(package,),
    )
    if endpoint_summary_block:
        lines.append(endpoint_summary_block)
    for result in results:
        lines.append(_format_coinglass_prompt_result_line(result))
    return "\n".join(line for line in lines if line).strip()


def _format_coinglass_prompt_result_line(result: dict[str, Any]) -> str:
    title = str(result.get("title") or result.get("key") or "CoinGlass endpoint")
    status = str(result.get("status") or "error")
    source = str(result.get("source") or result.get("path") or "")
    if status != "ok":
        error = _safe_scalar(result.get("error") or "unknown error")
        return f"- {title}: unavailable from `{source}`; error={error}"

    summary = result.get("summary") or {}
    parts: list[str] = []
    freshness = str(result.get("freshness") or "").strip()
    if freshness:
        parts.append(f"freshness={freshness}")
    item_count = summary.get("item_count")
    if item_count not in (None, ""):
        parts.append(f"rows={item_count}")
    primary_list_key = str(summary.get("primary_list_key") or "").strip()
    if primary_list_key:
        parts.append(f"list={primary_list_key}")
    field_brief = _format_coinglass_field_brief(summary)
    if field_brief:
        parts.append(field_brief)
    numeric_brief = _format_coinglass_numeric_brief(summary.get("numeric_summary") or {})
    if numeric_brief:
        parts.append(numeric_brief)
    elif summary.get("data") not in (None, ""):
        data_brief = _format_coinglass_data_brief(summary.get("data"))
        if data_brief:
            parts.append(data_brief)
    sample_brief = _format_coinglass_sample_brief(summary)
    if sample_brief:
        parts.append(sample_brief)

    detail = _trim_text("; ".join(part for part in parts if part), 800)
    return f"- {title}: {detail}" if detail else f"- {title}: available from `{source}`"


def _format_coinglass_field_brief(summary: dict[str, Any]) -> str:
    fields = summary.get("fields") or summary.get("keys") or []
    if not isinstance(fields, list) or not fields:
        return ""
    labels = [str(field) for field in fields if str(field).strip()]
    if not labels:
        return ""
    return f"fields={', '.join(labels)}"


def _format_coinglass_numeric_brief(numeric_summary: dict[str, Any]) -> str:
    if not isinstance(numeric_summary, dict) or not numeric_summary:
        return ""
    metrics: list[str] = []
    for key, values in numeric_summary.items():
        if not isinstance(values, dict):
            continue
        # Skip time/timestamp fields — meaningless as numeric metrics
        if _looks_like_time_field(key):
            continue
        latest = values.get("latest")
        if latest in (None, ""):
            continue
        metrics.append(f"{key}={_format_compact_number(latest)}")
    return f"latest={', '.join(metrics)}" if metrics else ""


def _format_coinglass_data_brief(value: object) -> str:
    compact = _compact_json_value(value, max_depth=2, max_items=3)
    try:
        text = json.dumps(compact, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        text = str(compact)
    return f"data={_trim_text(text, 180)}" if text else ""


def _format_coinglass_sample_brief(summary: dict[str, Any]) -> str:
    if not isinstance(summary, dict) or not summary:
        return ""
    label = "recent"
    value = summary.get("latest_items")
    if value in (None, "", [], {}):
        label = "sample"
        value = summary.get("sample_items")
    if value in (None, "", [], {}):
        return ""
    compact = _compact_json_value(value, max_depth=2, max_items=3)
    try:
        text = json.dumps(compact, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        text = str(compact)
    return f"{label}={_trim_text(text, 200)}" if text else ""


def _format_compact_number(value: object) -> str:
    number = _coerce_number(value)
    if number is None:
        return str(value)
    magnitude = abs(number)
    if magnitude >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"
    if magnitude >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    if magnitude >= 1_000:
        return f"{number / 1_000:.2f}K"
    if magnitude >= 1:
        return f"{number:.2f}"
    return f"{number:.4f}"


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
        items = list(value.items())
        compact = {str(key): _compact_json_value(val, max_depth - 1, max_items) for key, val in items}
        return compact
    if isinstance(value, list):
        if not value:
            return []
        # Compact exchange-per-row snapshots into a readable short table
        if all(isinstance(item, dict) and ('exchange' in item or 'exchange_name' in item) for item in value):
            return _compact_exchange_table(value, max_items)
        return [_compact_json_value(item, max_depth - 1, max_items) for item in value[:max_items]]
    return _safe_scalar(value)


def _compact_exchange_table(items: list[dict], max_exchanges: int) -> str:
    """Render exchange-per-row list as a compact pipe table with key metrics."""
    if not items:
        return ""
    # Determine the exchange key name
    ex_key = 'exchange_name' if all('exchange_name' in item for item in items) else 'exchange'
    # Pick meaningful numeric columns (skip symbol, exchange name, instrument_id)
    skip_keys = {ex_key, 'symbol', 'instrument_id', 'next_funding_time',
                 'update_time', 'close_time', 'last_trade_time', 'list_date',
                 'last_quote_time', 'asset_details', 'fund_type', 'market_status',
                 'primary_exchange', 'region', 'ticker', 'fund_name', 'cik_code'}
    # Collect candidate numeric columns and format them
    all_keys = sorted(set().union(*(d.keys() for d in items)))
    num_cols: list[str] = []
    for key in all_keys:
        if key in skip_keys or key.endswith('_list'):
            continue
        sample_vals = [d.get(key) for d in items[:5] if key in d]
        if sample_vals and all(_coerce_number(v) is not None for v in sample_vals if v is not None):
            num_cols.append(key)
    # Build compact rows — show all exchanges
    rows = []
    for item in items:
        ex_name = str(item.get(ex_key, '?'))[:14]
        cols = [ex_name]
        for col in num_cols:
            val = item.get(col)
            if val is None or val == '':
                cols.append('-')
            else:
                cols.append(_format_compact_number(val))
        rows.append(' | '.join(cols))
    header = f"exch({len(items)} rows)"
    if num_cols:
        header += f' | {" | ".join(col[:12] for col in num_cols)}'
    return header + '\n' + '\n'.join(rows)


def _format_timestamps_in_items(items: list[dict]) -> list[dict]:
    """Detect and format timestamp fields in list-of-dict items in-place."""
    if not items:
        return items
    time_keys: set[str] = set()
    for key in items[0].keys():
        if _looks_like_time_field(key):
            time_keys.add(key)
    if not time_keys:
        return items
    for item in items:
        for key in time_keys:
            val = item.get(key)
            if val is not None:
                formatted = _format_timestamp_value(val)
                if formatted:
                    item[key] = formatted
    return items


def _safe_scalar(value: object) -> object:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = re.sub(r"\s+", " ", str(value)).strip()
    return _trim_text(text, 240)


def _get_preview_row_limits() -> tuple[int, int]:
    sample_limit = 3
    recent_limit = 8
    try:
        from tradingagents.dataflows.config import get_config

        config = get_config()
        sample_limit = max(1, int(config.get("coinglass_preview_sample_rows") or sample_limit))
        recent_limit = max(1, int(config.get("coinglass_preview_recent_rows") or recent_limit))
    except Exception:
        pass
    return sample_limit, recent_limit


def _summarize_parallel_scalar_lists(
    data: dict[str, object],
    *,
    sample_row_limit: int,
    recent_row_limit: int,
) -> dict[str, Any] | None:
    grouped_lists: dict[int, list[tuple[str, list[object]]]] = {}
    for key, value in data.items():
        if not isinstance(value, list) or not value:
            continue
        if any(isinstance(item, (dict, list, tuple, set)) for item in value[: min(len(value), 24)]):
            continue
        grouped_lists.setdefault(len(value), []).append((str(key), value))

    best_group: list[tuple[str, list[object]]] | None = None
    for _length, items in grouped_lists.items():
        if len(items) < 2:
            continue
        if best_group is None or len(items) > len(best_group) or (
            len(items) == len(best_group) and len(items[0][1]) > len(best_group[0][1])
        ):
            best_group = items

    if not best_group:
        return None

    row_count = len(best_group[0][1])
    raw_columns = [key for key, _values in best_group]
    display_columns = _build_display_column_labels(raw_columns)
    series_rows = [
        {
            display_columns[key]: _format_parallel_series_value(key, values[index])
            for key, values in best_group
        }
        for index in range(row_count)
    ]

    numeric_summary: dict[str, dict[str, float]] = {}
    for key, values in best_group:
        if _looks_like_time_field(key):
            continue
        numeric_values = [number for number in (_coerce_number(value) for value in values) if number is not None]
        if not numeric_values:
            continue
        display_key = display_columns[key]
        numeric_summary[display_key] = {
            "latest": round(numeric_values[-1], 8),
            "min": round(min(numeric_values), 8),
            "max": round(max(numeric_values), 8),
        }

    warning = None
    capped = False
    if row_count > sample_row_limit:
        warning = f"Table too long (>{sample_row_limit} rows), only showing first {sample_row_limit} rows."
        capped = True
    sample_items = series_rows[:sample_row_limit] if capped else []
    latest_items = series_rows[-recent_row_limit:] if capped else series_rows

    summary: dict[str, Any] = {
        "primary_list_key": raw_columns[0],
        "item_count": row_count,
        "fields": list(display_columns.values()),
        "sample_items": sample_items,
        "latest_items": latest_items,
        "sample_title": "Earliest rows",
        "latest_title": "Most recent rows",
    }
    if warning:
        summary["table_limit_warning"] = warning
    if numeric_summary:
        summary["numeric_summary"] = numeric_summary
    return summary


def _looks_like_time_field(field_name: str) -> bool:
    normalized = str(field_name or "").strip().lower()
    return any(token in normalized for token in ("time", "date", "timestamp"))


def _build_display_column_labels(field_names: list[str]) -> dict[str, str]:
    used_labels: set[str] = set()
    labels: dict[str, str] = {}
    for field_name in field_names:
        base_label = _format_parallel_series_field_label(field_name)
        candidate = base_label
        suffix = 2
        while candidate in used_labels:
            candidate = f"{base_label} {suffix}"
            suffix += 1
        labels[field_name] = candidate
        used_labels.add(candidate)
    return labels


def _format_parallel_series_field_label(field_name: str) -> str:
    normalized = str(field_name or "").strip().lower().replace("-", "_")
    normalized = re.sub(r"_list$", "", normalized)
    if normalized in {"time", "date", "timestamp"}:
        return "Date"
    if normalized == "data":
        return "Value"
    if normalized == "price":
        return "Price"
    return str(normalized).replace("_", " ").title() or "Value"


def _format_parallel_series_value(field_name: str, value: object) -> object:
    if _looks_like_time_field(field_name):
        formatted = _format_timestamp_value(value)
        if formatted:
            return formatted
    return value


def _format_timestamp_value(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None

    if isinstance(value, bool) or value is None:
        return None

    timestamp = _coerce_number(value)
    if timestamp is None:
        return None

    try:
        normalized = float(timestamp)
        if normalized > 1_000_000_000_000:
            normalized /= 1000.0
        dt = datetime.fromtimestamp(normalized, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return str(value)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _collect_fields(items: list[object]) -> list[str]:
    fields: set[str] = set()
    for item in items[:10]:
        if isinstance(item, dict):
            fields.update(str(key) for key in item.keys())
    return sorted(fields)


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
            # Skip timestamp/date fields — they are not meaningful as numeric metrics
            if _looks_like_time_field(key):
                continue
            number = _coerce_number(value)
            if number is None:
                continue
            numeric_values.setdefault(str(key), []).append(number)

    # Detect if this is a time-series (has a time field in items) vs snapshot (exchange list)
    has_time_series_field = False
    if items and isinstance(items[0], dict):
        has_time_series_field = any(_looks_like_time_field(k) for k in items[0].keys())

    summary: dict[str, dict[str, float]] = {}
    for key, values in numeric_values.items():
        if not values:
            continue
        # For time-series: latest = most recent (last). For snapshots: first = aggregate/largest.
        latest_index = -1 if has_time_series_field else 0
        summary[key] = {
            "latest": round(values[latest_index], 8),
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
