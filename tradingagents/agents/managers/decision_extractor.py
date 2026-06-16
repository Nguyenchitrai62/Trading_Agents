"""Post-verification structured extraction for the final portfolio decision."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
from tradingagents.agents.utils.decision import validate_portfolio_decision
from tradingagents.agents.utils.market_price import fetch_current_binance_spot_price
from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext_result


def _format_context_block(title: str, value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return f"{title}: <missing>"
    return f"{title}:\n{text}"


def _extract_payload(structured_llm, plain_llm, prompt: str, current_price: float | None) -> tuple[dict, list[str], str]:
    if structured_llm is None:
        return {}, ["Structured output is unavailable for this provider."], ""

    rendered, parsed_decision = invoke_structured_or_freetext_result(
        structured_llm,
        plain_llm,
        prompt,
        render_pm_decision,
        "Decision Extractor",
    )
    if parsed_decision is None:
        return {}, ["Decision extraction did not return a structured payload."], rendered

    payload = parsed_decision.model_dump(mode="json")
    validation_errors = validate_portfolio_decision(payload, current_price=current_price)
    return payload, validation_errors, rendered


def create_decision_extractor(llm):
    import logging
    _logger = logging.getLogger(__name__)
    structured_llm = bind_structured(llm, PortfolioDecision, "Decision Extractor")

    def decision_extractor_node(state: dict) -> dict:
        try:
            return _decision_extractor_unsafe(state)
        except Exception as exc:
            _logger.exception("Decision Extractor crashed; falling back to Portfolio Manager payload.")
            existing_payload = dict(state.get("final_trade_decision_structured") or {})
            existing_payload["decision_extraction_fallback"] = True
            existing_payload["decision_extraction_error"] = str(exc)
            fallback_errors = list(existing_payload.get("decision_validation_errors") or [])
            fallback_errors.append(
                f"Decision Extractor crashed ({exc}); using Portfolio Manager payload."
            )
            existing_payload["decision_validation_errors"] = fallback_errors
            current_price = state.get("verification_reference_price")
            if current_price is not None:
                existing_payload["current_price"] = current_price
            return {
                "messages": [AIMessage(content=f"Decision extraction skipped due to error: {exc}. Using Portfolio Manager payload.")],
                "final_trade_decision_structured": existing_payload,
                "verification_reference_price": current_price,
                "verification_reference_price_source": "binance_spot" if current_price is not None else "",
            }

    def _decision_extractor_unsafe(state: dict) -> dict:
        final_markdown = str(state.get("final_trade_decision") or "").strip()
        current_price = state.get("verification_reference_price")
        if current_price is None:
            current_price = fetch_current_binance_spot_price(state.get("company_of_interest") or "")
        verification = state.get("verification_report_structured") or {}
        verification_verdict = str(verification.get("verdict") or "").strip()

        extraction_prompt = f"""Extract the verified Portfolio Manager markdown into the PortfolioDecision schema.

This extraction happens only after verifier approval. Use only facts explicitly present in the final markdown and supplied context. Do not invent prices, sizing, stop loss, take profit, or time horizon. Leave unsupported optional numeric fields empty.

Current reference price: {current_price if current_price is not None else "unavailable"}
Verifier verdict: {verification_verdict or "unknown"}

Final Portfolio Manager markdown:
{final_markdown or "<missing>"}

Context:
{_format_context_block("Market report", state.get("market_report"))}

{_format_context_block("Onchain report", state.get("onchain_report"))}

{_format_context_block("Social report", state.get("sentiment_report"))}

{_format_context_block("News report", state.get("news_report"))}

{_format_context_block("Verification report", state.get("verification_report"))}
"""

        payload, validation_errors, rendered = _extract_payload(
            structured_llm,
            llm,
            extraction_prompt,
            current_price,
        )

        if validation_errors and payload:
            repair_prompt = f"""Repair the structured extraction only. Do not change the Portfolio Manager markdown.

Validation errors:
{chr(10).join(f"- {error}" for error in validation_errors)}

Current reference price: {current_price if current_price is not None else "unavailable"}

Previous structured extraction:
{payload}

Final Portfolio Manager markdown:
{final_markdown}

Return a corrected PortfolioDecision. If a field is not explicitly supported by the markdown, leave it empty.
"""
            repaired_payload, repaired_errors, repaired_rendered = _extract_payload(
                structured_llm,
                llm,
                repair_prompt,
                current_price,
            )
            if repaired_payload and not repaired_errors:
                payload = repaired_payload
                validation_errors = []
                rendered = repaired_rendered
            else:
                validation_errors = repaired_errors or validation_errors

        existing_payload = state.get("final_trade_decision_structured") or {}
        if payload:
            payload["decision_validation_status"] = "invalid" if validation_errors else "valid"
            payload["decision_validation_errors"] = validation_errors
            payload["extracted_after_verification"] = True
            if verification_verdict.lower() == "revise":
                payload["extracted_after_max_revision_warning"] = True
            if current_price is not None:
                payload["current_price"] = current_price
        elif existing_payload:
            # Fall back to the Portfolio Manager payload if extraction fails,
            # but mark it clearly so downstream knows it did not go through
            # the dedicated extractor.
            payload = dict(existing_payload)
            payload["decision_extraction_fallback"] = True
            fallback_errors = list(existing_payload.get("decision_validation_errors") or [])
            fallback_errors.append(
                "Decision Extractor could not re-extract; using Portfolio Manager payload."
            )
            payload["decision_validation_errors"] = fallback_errors
            if current_price is not None:
                payload["current_price"] = current_price

        summary = rendered or ("Decision extraction completed." if payload else "Decision extraction did not produce a structured payload.")
        return {
            "messages": [AIMessage(content=summary)],
            "final_trade_decision_structured": payload,
            "verification_reference_price": current_price,
            "verification_reference_price_source": "binance_spot" if current_price is not None else "",
        }

    return decision_extractor_node
