"""Verifier: validates the final portfolio decision against deterministic rules and available evidence."""

from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage
from pydantic import ValidationError

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
from tradingagents.agents.utils.decision import (
    active_limit_prices,
    coerce_float,
    validate_portfolio_decision,
)
from tradingagents.agents.utils.evidence import format_evidence_ledger
from tradingagents.agents.utils.market_price import fetch_current_binance_spot_price
from tradingagents.agents.utils.rating import parse_rating
from tradingagents.agents.utils.structured import resolve_structured_base_llm
from tradingagents.llm_clients.base_client import normalize_content


def _response_text(response: object) -> str:
    normalized = normalize_content(response)
    content = getattr(normalized, "content", "")
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    return str(content).strip()


def _extract_json_object(text: str) -> dict | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL | re.IGNORECASE)
    candidates = [fenced.group(1)] if fenced else []
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start:end + 1])
    candidates.append(raw)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _fallback_verification_payload(raw_text: str, deterministic: dict[str, object]) -> dict:
    blockers = list(deterministic.get("blockers") or [])
    warnings = list(deterministic.get("warnings") or [])
    verdict = VerificationVerdict.REVISE.value if blockers else VerificationVerdict.CAUTION.value
    issues = [f"Deterministic blocker: {blocker}" for blocker in blockers]
    if not issues and warnings:
        issues = [f"Warning to review: {warning}" for warning in warnings]
    return {
        "verdict": verdict,
        "deterministic_checks": str(deterministic.get("summary") or ""),
        "evidence_support": "Verifier JSON could not be parsed; review the free-text verifier output.",
        "unsupported_claims": "Verifier JSON could not be parsed into structured unsupported-claim details.",
        "issues": issues,
        "confidence_note": "Structured verifier parsing fell back locally; deterministic checks were preserved.",
        "recommended_action": "Revise the portfolio decision before acting." if blockers else "Proceed only after manually reviewing the verifier free-text output.",
        "raw_verifier_output": raw_text,
    }


def _parse_verification_report(raw_text: str, deterministic: dict[str, object]) -> tuple[str, VerificationReport | None, dict]:
    payload = _extract_json_object(raw_text)
    if payload is not None:
        try:
            parsed = VerificationReport.model_validate(payload)
            return render_verification_report(parsed), parsed, parsed.model_dump(mode="json")
        except ValidationError:
            pass

    fallback_payload = _fallback_verification_payload(raw_text, deterministic)
    try:
        parsed = VerificationReport.model_validate(fallback_payload)
        structured_payload = parsed.model_dump(mode="json")
        structured_payload["raw_verifier_output"] = raw_text
        return render_verification_report(parsed), parsed, structured_payload
    except ValidationError:
        return raw_text, None, fallback_payload


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


def _extract_numeric_from_markdown(markdown: str, field_labels: list[str]) -> float | None:
    """Parse a numeric value preceded by one of the field labels in markdown prose."""
    for label in field_labels:
        escaped = re.escape(label)
        pattern = rf'(?i)(?:^|\n)\s*[-*]*\s*\**\s*{escaped}\s*\**\s*[:=-]\s*\$?\s*([\d,]+(?:\.\d+)?)'
        match = re.search(pattern, markdown)
        if match:
            raw = match.group(1).replace(",", "").replace("$", "").strip()
            value = coerce_float(raw)
            if value is not None:
                return value
    return None


def _build_effective_decision(decision: dict, markdown: str) -> dict:
    """Merge structured decision with values parsed from markdown for missing fields."""
    effective = dict(decision)
    effective.setdefault("signal", parse_rating(markdown, default="").strip())
    for field, labels in [
        ("stop_loss", ["Stop Loss", "Stop-Loss", "Stop loss", "Invalidation Level", "Invalidation"]),
        ("take_profit", ["Take Profit", "Take-Profit", "Take profit", "Target", "Profit Target", "Exit Target", "Exit Objective"]),
        ("primary_limit_buy_price", ["Primary Limit Buy", "Limit Buy Price", "Buy Limit", "Entry Limit", "Primary Limit Buy Price"]),
        ("secondary_limit_buy_price", ["Secondary Limit Buy", "Secondary Buy Limit", "Secondary Limit Buy Price"]),
        ("primary_limit_sell_price", ["Primary Limit Sell", "Limit Sell Price", "Sell Limit", "Exit Limit", "Primary Limit Sell Price"]),
        ("secondary_limit_sell_price", ["Secondary Limit Sell", "Secondary Sell Limit", "Secondary Limit Sell Price"]),
    ]:
        if effective.get(field) in (None, ""):
            value = _extract_numeric_from_markdown(markdown, labels)
            if value is not None:
                effective[field] = value
    return effective


def _build_deterministic_summary(state: dict) -> dict[str, object]:
    decision = state.get("final_trade_decision_structured") or {}
    decision_markdown = str(state.get("final_trade_decision") or "").strip()
    current_price = fetch_current_binance_spot_price(state.get("company_of_interest") or "")
    findings: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []

    effective_decision = _build_effective_decision(decision, decision_markdown)
    signal = str(effective_decision.get("signal") or parse_rating(decision_markdown, default="")).strip()
    primary, secondary = active_limit_prices(effective_decision)
    stop_loss = coerce_float(effective_decision.get("stop_loss"))
    take_profit = coerce_float(effective_decision.get("take_profit"))

    if current_price is None:
        warnings.append("Current Binance spot price could not be resolved, so price-relation checks are partial.")
    else:
        findings.append(f"Current Binance spot price: {current_price:.8g}")

    if not signal:
        blockers.append("Portfolio Manager markdown is missing a recognized execution signal.")
    elif not decision:
        for validation_error in validate_portfolio_decision(effective_decision, current_price=current_price):
            blockers.append(validation_error)
        if not blockers:
            warnings.append("Structured decision extraction is pending; markdown-level checks passed but final extraction may differ.")
    elif decision:
        for validation_error in validate_portfolio_decision(decision, current_price=current_price):
            blockers.append(validation_error)

    if signal == "Limit Buy":
        if primary is None:
            blockers.append("Limit Buy is missing a primary limit price.")
        if secondary is None:
            blockers.append("Limit Buy is missing a secondary limit price.")
        if stop_loss is None:
            blockers.append("Limit Buy is missing a stop-loss.")
        if take_profit is None:
            blockers.append("Limit Buy is missing a take-profit.")
        if current_price is not None and primary is not None and primary > current_price:
            blockers.append("Limit Buy primary limit price is above current spot price without breakout confirmation.")
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
        if stop_loss is None:
            blockers.append("Market Buy is missing a stop-loss.")
        if take_profit is None:
            blockers.append("Market Buy is missing a take-profit.")
        if current_price is not None and stop_loss is not None and stop_loss >= current_price:
            blockers.append("Market Buy stop loss is not below current spot price.")
        if current_price is not None and take_profit is not None and take_profit <= current_price:
            blockers.append("Market Buy take profit is not above current spot price.")
    elif signal == "Hold":
        if primary is not None or secondary is not None:
            blockers.append("Hold should not include executable limit prices.")
        if stop_loss is not None:
            blockers.append("Hold should not include a stop-loss.")
        if take_profit is not None:
            blockers.append("Hold should not include a take-profit.")
    elif signal == "Limit Sell":
        if primary is None:
            blockers.append("Limit Sell is missing a primary limit price.")
        if secondary is None:
            blockers.append("Limit Sell is missing a secondary limit price.")
        if stop_loss is None:
            blockers.append("Limit Sell is missing a stop-loss.")
        if take_profit is None:
            blockers.append("Limit Sell is missing a take-profit.")
        if current_price is not None and primary is not None and primary < current_price:
            blockers.append("Limit Sell primary limit price is below current spot price.")
        if secondary is not None and primary is not None and secondary < primary:
            warnings.append("Secondary Limit Sell is below the primary limit; staged exits usually step higher.")
        if current_price is not None and stop_loss is not None and stop_loss >= current_price:
            warnings.append("Limit Sell stop loss sits above current spot price; confirm it only applies to a retained long tranche.")
        if stop_loss is not None and primary is not None and stop_loss < primary:
            blockers.append("Limit Sell stop loss is below the primary limit price. For a sell signal the invalidation must be above the sell limit (to cancel the sell if the trend turns bullish). A stop below the sell limit belongs to a retained long tranche, not the sell order itself.")
        if take_profit is not None and primary is not None and take_profit > primary:
            blockers.append(f"Limit Sell take profit ({take_profit:.2f}) is above the primary limit price ({primary:.2f}). For a sell signal the take-profit target must be below the sell limit to capture downside profit. A target above the limit belongs to a retained long tranche, not the sell order.")
        if current_price is not None and stop_loss is not None and primary is not None:
            if stop_loss < current_price < primary:
                blockers.append(f"Limit Sell stop loss ({stop_loss:.2f}) is below current price ({current_price:.2f}) while the limit price ({primary:.2f}) is above. This sell order has no invalidation above — either set stop_loss above the limit price or use Market Sell for immediate execution at current.")
    elif signal == "Market Sell":
        if primary is not None or secondary is not None:
            blockers.append("Market Sell should not include limit prices.")
        if stop_loss is None:
            blockers.append("Market Sell is missing a stop-loss or invalidation level.")
        if take_profit is None:
            blockers.append("Market Sell is missing a take-profit or next exit objective.")

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
    base_llm = resolve_structured_base_llm(llm)

    def verifier_node(state) -> dict:
        instrument_context = build_instrument_context(
            state["company_of_interest"],
            state.get("asset_type", "crypto"),
        )
        deterministic = _build_deterministic_summary(state)
        investment_debate_state = state.get("investment_debate_state") or {}
        research_debate = investment_debate_state.get("history", "")
        portfolio_decision = _format_structured_context(
            state.get("final_trade_decision_structured") or {},
            state.get("final_trade_decision") or "",
            [
                ("Signal", "signal"),
                ("Execution Summary", "execution_summary"),
                ("Market Context", "market_context"),
                ("Investment Thesis", "investment_thesis"),
                ("Primary Limit Buy Price", "primary_limit_buy_price"),
                ("Secondary Limit Buy Price", "secondary_limit_buy_price"),
                ("Primary Limit Sell Price", "primary_limit_sell_price"),
                ("Secondary Limit Sell Price", "secondary_limit_sell_price"),
                ("Stop Loss", "stop_loss"),
                ("Take Profit", "take_profit"),
                ("Position Sizing", "position_sizing"),
                ("Time Horizon", "time_horizon"),
                ("Validation Status", "decision_validation_status"),
                ("Validation Errors", "decision_validation_errors"),
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

Return JSON only, with no markdown fence and no extra prose. The JSON object must contain exactly these keys:
- verdict: one of "Approved", "Caution", "Revise"
- deterministic_checks: string
- evidence_support: string
- unsupported_claims: string
- issues: array of strings; use as the precise fix-list for Portfolio Manager revision, or [] if no revision is needed
- confidence_note: string
- recommended_action: string

Deterministic check summary:
{deterministic['summary']}

Market report:
{state.get('market_report') or '<missing>'}

Social report:
{state.get('sentiment_report') or '<missing>'}

News report:
{state.get('news_report') or '<missing>'}

Onchain report:
{state.get('onchain_report') or '<missing>'}

Structured evidence ledger:
{evidence_ledger}

{coinglass_context}

Bull/Bear research debate:
{research_debate or '<missing>'}

Portfolio Manager decision:
{portfolio_decision or '<missing>'}

Be strict. If a strong claim is not grounded in the supplied evidence, call it out explicitly instead of smoothing over it.{get_language_instruction()}"""

        raw_verification = _response_text(base_llm.invoke(prompt))
        verification_report, parsed_report, structured_payload = _parse_verification_report(raw_verification, deterministic)
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
            existing_issues = list(parsed_report.issues or [])
            parsed_report.issues = existing_issues + [
                f"Deterministic blocker: {blocker}" for blocker in deterministic["blockers"]
            ]
            verification_report = render_verification_report(parsed_report)
            structured_payload = parsed_report.model_dump(mode="json")
        elif parsed_report is None and deterministic["blockers"]:
            verification_report = (
                verification_report.rstrip()
                + "\n\n**Deterministic Override**: Hard blockers were detected, so the final decision should be revised before execution."
            )
            structured_payload = {
                "verdict": VerificationVerdict.REVISE.value,
                "deterministic_checks": deterministic["summary"],
                "evidence_support": "",
                "unsupported_claims": "",
                "issues": [f"Deterministic blocker: {blocker}" for blocker in deterministic["blockers"]],
                "confidence_note": "Deterministic blockers were detected even though the structured verifier output could not be parsed.",
                "recommended_action": "Return to the Portfolio Manager and revise the order plan before execution.",
            }

        revision_count = int(state.get("decision_revision_count") or 0)
        verdict_text = str(structured_payload.get("verdict") or "").strip().lower()
        if verdict_text and verdict_text != "approved":
            revision_count += 1

        return {
            "messages": [AIMessage(content=verification_report)],
            "verification_report": verification_report,
            "verification_report_structured": structured_payload,
            "verification_reference_price": deterministic["current_price"],
            "verification_reference_price_source": "binance_spot" if deterministic["current_price"] is not None else "",
            "decision_revision_count": revision_count,
        }

    return verifier_node
