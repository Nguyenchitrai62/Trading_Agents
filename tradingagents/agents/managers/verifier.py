"""Verifier: validates the final portfolio decision against deterministic rules and available evidence."""

from __future__ import annotations

import json
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import (
    VerificationReport,
    VerificationVerdict,
    render_verification_report,
)
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_coinglass_context_instruction,
    get_coinglass_packages_for_role,
    get_language_instruction,
)
from tradingagents.agents.utils.evidence import format_evidence_ledger
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext_result,
)


_BINANCE_TICKER_PRICE_URL = "https://api.binance.com/api/v3/ticker/price"
_BINANCE_USER_AGENT = "tradingagents/0.2"


def _normalize_binance_symbol(symbol: str) -> tuple[str, str]:
    normalized = str(symbol or "").strip().upper().replace(" ", "")
    if not normalized:
        raise ValueError("symbol is required")
    if "/" in normalized:
        base, quote = normalized.split("/", 1)
    elif "-" in normalized:
        base, quote = normalized.split("-", 1)
    else:
        raise ValueError("Crypto symbol must include base and quote assets.")
    if quote == "USD":
        quote = "USDT"
    market_symbol = f"{base}/{quote}"
    api_symbol = f"{base}{quote}"
    return api_symbol, market_symbol


def _fetch_current_price(symbol: str) -> Optional[float]:
    try:
        api_symbol, _market_symbol = _normalize_binance_symbol(symbol)
    except ValueError:
        return None

    url = f"{_BINANCE_TICKER_PRICE_URL}?{urlencode({'symbol': api_symbol})}"
    request = Request(url, headers={"User-Agent": _BINANCE_USER_AGENT})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None

    try:
        return float(payload.get("price"))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_structured_context(payload: dict, fallback: str, fields: list[tuple[str, str]]) -> str:
    if not payload:
        return fallback

    lines = []
    for label, key in fields:
        value = payload.get(key)
        if value in (None, "", []):
            continue
        lines.append(f"- {label}: {value}")
    return "\n".join(lines) if lines else fallback


def _format_list(items: list[str], *, default: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {default}"


def _build_deterministic_summary(state: dict) -> dict[str, object]:
    decision = state.get("final_trade_decision_structured") or {}
    signal = str(decision.get("signal") or "").strip()
    current_price = _fetch_current_price(state.get("company_of_interest") or "")
    findings: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []

    primary = _coerce_float(decision.get("primary_limit_price"))
    secondary = _coerce_float(decision.get("secondary_limit_price"))
    stop_loss = _coerce_float(decision.get("stop_loss"))
    take_profit = _coerce_float(decision.get("take_profit"))

    if current_price is None:
        warnings.append("Current Binance spot price could not be resolved, so price-relation checks are partial.")
    else:
        findings.append(f"Current Binance spot price: {current_price:.8g}")

    if not signal:
        blockers.append("Structured portfolio signal is missing, so deterministic verification cannot confirm order logic.")
    elif signal == "Limit Buy":
        if primary is None:
            blockers.append("Limit Buy is missing a primary limit price.")
        if current_price is not None and primary is not None and primary >= current_price:
            blockers.append("Limit Buy primary limit price is not below current spot price.")
        if secondary is not None and primary is not None and secondary > primary:
            warnings.append("Secondary Limit Buy is above the primary limit; scale-in ladders usually step lower.")
        reference_entry = min(value for value in (primary, secondary) if value is not None) if primary is not None or secondary is not None else None
        if stop_loss is not None and reference_entry is not None and stop_loss >= reference_entry:
            blockers.append("Limit Buy stop loss is not below the planned entry zone.")
        if take_profit is not None and reference_entry is not None:
            take_profit_floor = max(current_price or reference_entry, reference_entry)
            if take_profit <= take_profit_floor:
                blockers.append("Limit Buy take profit is not above the entry/current price context.")
    elif signal == "Market Buy":
        if primary is not None or secondary is not None:
            blockers.append("Market Buy should not include limit prices.")
        if current_price is not None and stop_loss is not None and stop_loss >= current_price:
            blockers.append("Market Buy stop loss is not below current spot price.")
        if current_price is not None and take_profit is not None and take_profit <= current_price:
            blockers.append("Market Buy take profit is not above current spot price.")
    elif signal == "Hold":
        if primary is not None or secondary is not None:
            blockers.append("Hold should not include executable limit prices.")
    elif signal == "Limit Sell":
        if primary is None:
            blockers.append("Limit Sell is missing a primary limit price.")
        if current_price is not None and primary is not None and primary <= current_price:
            blockers.append("Limit Sell primary limit price is not above current spot price.")
        if secondary is not None and primary is not None and secondary < primary:
            warnings.append("Secondary Limit Sell is below the primary limit; staged exits usually step higher.")
        if take_profit is not None:
            blockers.append("Limit Sell should not include a take-profit target in this long-only workflow.")
        if current_price is not None and stop_loss is not None and stop_loss >= current_price:
            warnings.append("Limit Sell stop loss sits above current spot price; confirm it only applies to a retained long tranche.")
    elif signal == "Market Sell":
        if primary is not None or secondary is not None:
            blockers.append("Market Sell should not include limit prices.")
        if take_profit is not None:
            blockers.append("Market Sell should not include a take-profit target in this long-only workflow.")

    summary_lines = []
    summary_lines.append("Deterministic findings:")
    summary_lines.append(_format_list(findings, default="No direct price context was available."))
    summary_lines.append("")
    summary_lines.append("Hard blockers:")
    summary_lines.append(_format_list(blockers, default="No hard deterministic blockers found."))
    summary_lines.append("")
    summary_lines.append("Warnings:")
    summary_lines.append(_format_list(warnings, default="No soft warnings found."))

    return {
        "current_price": current_price,
        "signal": signal,
        "blockers": blockers,
        "warnings": warnings,
        "summary": "\n".join(summary_lines).strip(),
    }


def create_verifier(llm):
    structured_llm = bind_structured(llm, VerificationReport, "Verifier")

    def verifier_node(state) -> dict:
        instrument_context = build_instrument_context(
            state["company_of_interest"],
            state.get("asset_type", "crypto"),
        )
        deterministic = _build_deterministic_summary(state)
        research_plan = _format_structured_context(
            state.get("investment_plan_structured") or {},
            state.get("investment_plan") or "",
            [
                ("Recommendation", "recommendation"),
                ("Rationale", "rationale"),
                ("Strategic Actions", "strategic_actions"),
            ],
        )
        trader_plan = _format_structured_context(
            state.get("trader_investment_plan_structured") or {},
            state.get("trader_investment_plan") or "",
            [
                ("Action", "action"),
                ("Reasoning", "reasoning"),
                ("Entry Price", "entry_price"),
                ("Stop Loss", "stop_loss"),
                ("Position Sizing", "position_sizing"),
            ],
        )
        portfolio_decision = _format_structured_context(
            state.get("final_trade_decision_structured") or {},
            state.get("final_trade_decision") or "",
            [
                ("Signal", "signal"),
                ("Execution Summary", "execution_summary"),
                ("Market Context", "market_context"),
                ("Investment Thesis", "investment_thesis"),
                ("Primary Limit Price", "primary_limit_price"),
                ("Secondary Limit Price", "secondary_limit_price"),
                ("Stop Loss", "stop_loss"),
                ("Take Profit", "take_profit"),
                ("Position Sizing", "position_sizing"),
                ("Time Horizon", "time_horizon"),
            ],
        )
        evidence_ledger = format_evidence_ledger(state.get("evidence_items"), limit=24)
        coinglass_context = get_coinglass_context_instruction(
            state,
            packages=get_coinglass_packages_for_role("verifier"),
        )

        blocker_rule = (
            "Hard rule: deterministic blockers are present, so the verdict must be Revise."
            if deterministic["blockers"]
            else "Hard rule: if you find no deterministic blockers, you may still use Caution or Revise when the evidence support is weak."
        )

        prompt = f"""As the Verifier, audit the final portfolio decision after the full agent workflow.

{instrument_context}

Your job is not to create a new trade plan from scratch. Your job is to verify whether the existing final decision is internally coherent and actually supported by the evidence gathered earlier.

{blocker_rule}

Audit in two layers:
1. Deterministic order logic: current price versus signal, limit prices, stop loss, and take profit.
2. Semantic support: whether the final signal and thesis are actually supported by the analyst evidence and intermediate handoffs, and whether any important claim lacks source-backed support.

Return a structured verification report with these fields only: verdict, deterministic_checks, evidence_support, unsupported_claims, confidence_note, recommended_action.

Deterministic check summary:
{deterministic['summary']}

Market report:
{state.get('market_report') or '<missing>'}

Social report:
{state.get('sentiment_report') or '<missing>'}

News report:
{state.get('news_report') or '<missing>'}

Flow report:
{state.get('flow_report') or '<missing>'}

Structured evidence ledger:
{evidence_ledger}

{coinglass_context}

Research Manager handoff:
{research_plan or '<missing>'}

Trader handoff:
{trader_plan or '<missing>'}

Portfolio Manager decision:
{portfolio_decision or '<missing>'}

Be strict. If a strong claim is not grounded in the supplied evidence, call it out explicitly instead of smoothing over it.{get_language_instruction()}"""

        verification_report, parsed_report = invoke_structured_or_freetext_result(
            structured_llm,
            llm,
            prompt,
            render_verification_report,
            "Verifier",
        )

        structured_payload = parsed_report.model_dump(mode="json") if parsed_report is not None else {}
        if parsed_report is not None and deterministic["blockers"] and parsed_report.verdict != VerificationVerdict.REVISE:
            parsed_report.verdict = VerificationVerdict.REVISE
            parsed_report.deterministic_checks = (
                f"{parsed_report.deterministic_checks}\n\nMandatory revision blockers:\n"
                + _format_list(list(deterministic["blockers"]), default="None")
            ).strip()
            if "revise" not in parsed_report.recommended_action.lower():
                parsed_report.recommended_action = (
                    "Revise the portfolio decision before acting. "
                    + parsed_report.recommended_action
                ).strip()
            verification_report = render_verification_report(parsed_report)
            structured_payload = parsed_report.model_dump(mode="json")
        elif parsed_report is None and deterministic["blockers"]:
            verification_report = (
                verification_report.rstrip()
                + "\n\n**Deterministic Override**: Hard blockers were detected, so the final decision should be revised before execution."
            )

        return {
            "messages": [AIMessage(content=verification_report)],
            "verification_report": verification_report,
            "verification_report_structured": structured_payload,
            "verification_reference_price": deterministic["current_price"],
            "verification_reference_price_source": "binance_spot" if deterministic["current_price"] is not None else "",
        }

    return verifier_node
