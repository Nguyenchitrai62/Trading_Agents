from __future__ import annotations

from typing import Any


BUY_SIGNALS = {"Market Buy", "Limit Buy"}
SELL_SIGNALS = {"Market Sell", "Limit Sell"}
LIMIT_SIGNALS = {"Limit Buy", "Limit Sell"}


def coerce_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_signal(value: object) -> str:
    text = str(value or "").strip()
    aliases = {
        "market buy": "Market Buy",
        "limit buy": "Limit Buy",
        "hold": "Hold",
        "limit sell": "Limit Sell",
        "market sell": "Market Sell",
    }
    return aliases.get(text.lower(), text)


def active_limit_prices(decision: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return the compatibility primary/secondary prices for the active signal."""
    signal = normalize_signal(decision.get("signal"))
    if signal == "Limit Buy":
        return (
            coerce_float(decision.get("primary_limit_buy_price")),
            coerce_float(decision.get("secondary_limit_buy_price")),
        )
    if signal == "Limit Sell":
        return (
            coerce_float(decision.get("primary_limit_sell_price")),
            coerce_float(decision.get("secondary_limit_sell_price")),
        )
    return None, None


def compatibility_decision_fields(decision: dict[str, Any]) -> dict[str, Any]:
    """Return DB-compatible fields without parsing prose markdown."""
    primary, secondary = active_limit_prices(decision)
    stop_loss = coerce_float(decision.get("stop_loss"))
    take_profit = coerce_float(decision.get("take_profit"))
    if str(decision.get("decision_validation_status") or "").lower() == "invalid":
        errors = list(decision.get("decision_validation_errors") or [])
        if any("primary_limit" in str(e).lower() for e in errors):
            primary = None
        if any("secondary_limit" in str(e).lower() for e in errors):
            secondary = None
        if any("stop_loss" in str(e).lower() for e in errors):
            stop_loss = None
        if any("take_profit" in str(e).lower() for e in errors):
            take_profit = None
    return {
        "primary_limit_price": primary,
        "secondary_limit_price": secondary,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "position_sizing": decision.get("position_sizing"),
        "time_horizon": decision.get("time_horizon"),
    }


def validate_portfolio_decision(
    decision: dict[str, Any],
    *,
    current_price: float | None = None,
) -> list[str]:
    """Return deterministic validation errors for extracted PM decisions."""
    signal = normalize_signal(decision.get("signal"))
    errors: list[str] = []
    primary, secondary = active_limit_prices(decision)
    buy_primary = coerce_float(decision.get("primary_limit_buy_price"))
    buy_secondary = coerce_float(decision.get("secondary_limit_buy_price"))
    sell_primary = coerce_float(decision.get("primary_limit_sell_price"))
    sell_secondary = coerce_float(decision.get("secondary_limit_sell_price"))
    stop_loss = coerce_float(decision.get("stop_loss"))
    take_profit = coerce_float(decision.get("take_profit"))
    decision_text = _decision_text(decision)

    if signal not in {"Market Buy", "Limit Buy", "Hold", "Limit Sell", "Market Sell"}:
        errors.append("Signal must be exactly one of Market Buy, Limit Buy, Hold, Limit Sell, Market Sell.")
        return errors

    if signal == "Limit Buy":
        if primary is None:
            errors.append("Limit Buy requires primary_limit_buy_price.")
        if secondary is None:
            errors.append("Limit Buy requires secondary_limit_buy_price.")
        if stop_loss is None:
            errors.append("Limit Buy requires stop_loss.")
        if take_profit is None:
            errors.append("Limit Buy requires take_profit.")
        if sell_primary is not None or sell_secondary is not None:
            errors.append("Limit Buy must not contain sell limit ladder fields.")
        if current_price is not None and primary is not None and primary > current_price and not _allows_breakout_buy(decision_text):
            errors.append("Limit Buy price is above current price without explicit breakout-confirmation rationale.")
        reference_entry = min(value for value in (primary, secondary) if value is not None) if primary is not None or secondary is not None else None
        if reference_entry is not None and stop_loss is not None and stop_loss >= reference_entry:
            errors.append("Limit Buy stop_loss must be below the planned entry zone.")
        if reference_entry is not None and take_profit is not None and take_profit <= max(current_price or reference_entry, reference_entry):
            errors.append("Limit Buy take_profit must be above entry/current price context.")

    if signal == "Market Buy":
        if buy_primary is not None or buy_secondary is not None or sell_primary is not None or sell_secondary is not None:
            errors.append("Market Buy must not contain limit ladder fields.")
        if stop_loss is None:
            errors.append("Market Buy requires stop_loss.")
        if take_profit is None:
            errors.append("Market Buy requires take_profit.")
        if current_price is not None and stop_loss is not None and stop_loss >= current_price:
            errors.append("Market Buy stop_loss must be below current price.")
        if current_price is not None and take_profit is not None and take_profit <= current_price:
            errors.append("Market Buy take_profit must be above current price.")

    if signal == "Hold":
        if any(value is not None for value in (buy_primary, buy_secondary, sell_primary, sell_secondary, stop_loss, take_profit)):
            errors.append("Hold must not contain executable prices, stop_loss, or take_profit.")

    if signal == "Limit Sell":
        if primary is None:
            errors.append("Limit Sell requires primary_limit_sell_price.")
        if secondary is None:
            errors.append("Limit Sell requires secondary_limit_sell_price.")
        if stop_loss is None:
            errors.append("Limit Sell requires stop_loss.")
        if take_profit is None:
            errors.append("Limit Sell requires take_profit.")
        if buy_primary is not None or buy_secondary is not None:
            errors.append("Sell signals must not contain buy entry ladders.")
        if current_price is not None and primary is not None and primary < current_price:
            errors.append("Limit Sell price is below current price; use Market Sell when selling at or below spot is intended.")
        if stop_loss is not None and primary is not None and stop_loss < primary:
            errors.append("Limit Sell stop loss is below the primary limit price. For a sell signal the invalidation must be above the sell limit.")
        if take_profit is not None and primary is not None and take_profit > primary:
            errors.append("Limit Sell take profit is above the primary limit price. For a sell signal the target must be below the sell limit.")
        if current_price is not None and stop_loss is not None and primary is not None:
            if stop_loss < current_price < primary:
                errors.append("Limit Sell stop loss is below current price while the limit price is above. This sell order has no invalidation above.")

    if signal == "Market Sell":
        if any(value is not None for value in (buy_primary, buy_secondary, sell_primary, sell_secondary)):
            errors.append("Market Sell must not contain limit ladder fields.")
        if buy_primary is not None or buy_secondary is not None:
            errors.append("Sell signals must not contain buy entry ladders.")
        if stop_loss is None:
            errors.append("Market Sell requires stop_loss for remaining long exposure or execution invalidation.")
        if take_profit is None:
            errors.append("Market Sell requires take_profit as a next exit objective or profit-protection level.")

    if signal in SELL_SIGNALS and _mentions_short_exposure(decision_text):
        errors.append("Sell signals represent long-only reduction/exit and must not describe new short exposure.")

    return errors


def _decision_text(decision: dict[str, Any]) -> str:
    fields = (
        "execution_summary",
        "market_context",
        "investment_thesis",
        "position_sizing",
        "time_horizon",
    )
    return " ".join(str(decision.get(field) or "") for field in fields).lower()


def _allows_breakout_buy(text: str) -> bool:
    return any(term in text for term in ("breakout", "confirmation", "trigger", "reclaim", "momentum entry"))


def _mentions_short_exposure(text: str) -> bool:
    return any(term in text for term in ("short exposure", "open a short", "new short", "short position", "short thesis"))
