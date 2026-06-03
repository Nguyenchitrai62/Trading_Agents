import json

from ..config import SECTION_META
from tradingagents.agents.utils.evidence import evidence_items_to_markdown
from tradingagents.dataflows.endpoint_summary import format_endpoint_summaries_for_prompt


def _history_section(
    section_key: str,
    title: str,
    agent: str,
    team: str,
    markdown: object,
    *,
    artifact_type: str = "markdown",
    flow_stage: str | None = None,
    flow_group: str | None = None,
    source_kind: str | None = None,
    source_key: str | None = None,
    summary: str | None = None,
    payload_json: object = None,
) -> dict | None:
    markdown_text = str(markdown or "").strip()
    if not markdown_text:
        return None
    return {
        "section_key": section_key,
        "title": title,
        "agent": agent,
        "team": team,
        "markdown": markdown_text,
        "artifact_type": artifact_type,
        "flow_stage": flow_stage,
        "flow_group": flow_group,
        "source_kind": source_kind,
        "source_key": source_key,
        "summary": summary,
        "payload_json": payload_json,
    }


def _structured_payload_to_markdown(title: str, payload: object) -> str:
    if not isinstance(payload, dict) or not payload:
        return ""
    return "\n".join(
        [
            f"# {title}",
            "",
            "```json",
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
            "```",
        ]
    )


def _endpoint_summaries_to_markdown(endpoint_summaries: object) -> str:
    if not isinstance(endpoint_summaries, list) or not endpoint_summaries:
        return ""
    prompt_block = format_endpoint_summaries_for_prompt(endpoint_summaries, limit=max(1, len(endpoint_summaries)))
    rows = [
        "| Endpoint | Package | Status | Direction | Confidence | Source |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for item in endpoint_summaries:
        if not isinstance(item, dict):
            continue
        confidence = item.get("confidence")
        try:
            confidence_text = f"{float(confidence):.2f}"
        except (TypeError, ValueError):
            confidence_text = ""
        cells = [
            item.get("title") or item.get("endpoint_name") or "",
            item.get("package_label") or item.get("package") or "",
            item.get("status") or "",
            item.get("direction") or "",
            confidence_text,
            item.get("source") or "",
        ]
        rows.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in cells) + " |")
    return "\n\n".join(["# Endpoint Summaries", prompt_block, "\n".join(rows)]).strip()


def _endpoint_summary_bucket(item: dict) -> str:
    text = " ".join(
        str(item.get(key) or "").lower()
        for key in ("package", "package_label", "endpoint_name", "title", "source", "source_type")
    )
    if any(token in text for token in ("coinglass", "derivative", "funding", "liquidation", "open interest")):
        return "coinglass"
    if any(token in text for token in ("news", "article", "global")):
        return "news"
    if any(token in text for token in ("social", "reddit", "stocktwits", "web")):
        return "social"
    if any(token in text for token in ("flow", "on-chain", "liquidity", "stablecoin", "tvl")):
        return "flow"
    if any(token in text for token in ("ccxt", "ohlcv", "indicator", "market")):
        return "ccxt"
    return ""


def _filter_endpoint_summaries(endpoint_summaries: object, bucket: str) -> list[dict]:
    if not isinstance(endpoint_summaries, list):
        return []
    return [
        item
        for item in endpoint_summaries
        if isinstance(item, dict) and _endpoint_summary_bucket(item) == bucket
    ]


def _source_group_artifacts(flow_artifacts: object, flow_group: str) -> list[dict]:
    if not isinstance(flow_artifacts, list):
        return []
    return [
        artifact
        for artifact in flow_artifacts
        if isinstance(artifact, dict) and artifact.get("flow_group") == flow_group
    ]


def _source_group_summary_markdown(title: str, endpoint_summaries: list[dict], artifacts: list[dict]) -> str:
    if endpoint_summaries:
        return _endpoint_summaries_to_markdown(endpoint_summaries).replace("# Endpoint Summaries", f"# {title}", 1)
    if not artifacts:
        return ""
    lines = [f"# {title}", "", "| Source | Kind | Summary |", "| --- | --- | --- |"]
    for artifact in artifacts[:24]:
        cells = [
            artifact.get("title") or artifact.get("source_key") or "",
            artifact.get("source_kind") or artifact.get("artifact_type") or "",
            artifact.get("summary") or artifact.get("source_key") or "",
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in cells) + " |")
    return "\n".join(lines).strip()


def _flow_block_markdown(title: str, status: str, summary: str, payload: dict) -> str:
    related_sections = payload.get("related_sections") if isinstance(payload, dict) else []
    related_sources = payload.get("source_groups") if isinstance(payload, dict) else []
    lines = [
        f"# {title}",
        "",
        f"- Status: {status or 'pending'}",
    ]
    if summary:
        lines.append(f"- Summary: {summary}")
    if isinstance(related_sections, list) and related_sections:
        lines.append("- Related sections: " + ", ".join(str(item) for item in related_sections if item))
    if isinstance(related_sources, list) and related_sources:
        lines.append("- Related source groups: " + ", ".join(str(item) for item in related_sources if item))
    lines.extend(["", "```json", json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), "```"])
    return "\n".join(lines).strip()


def _build_flow_block_sections(final_state: dict) -> list[dict]:
    sections: list[dict] = []
    selected_analysts = {
        str(item or "").strip().lower()
        for item in (final_state.get("selected_analysts") or ["market", "onchain", "social", "news"])
        if str(item or "").strip()
    }
    source_group_counts = final_state.get("source_artifact_groups") or {}
    flow_artifacts = final_state.get("flow_artifacts") or []
    endpoint_summaries = final_state.get("endpoint_summaries") or []

    def has_text(key: str) -> bool:
        return bool(str(final_state.get(key) or "").strip())

    def has_payload(key: str) -> bool:
        payload = final_state.get(key)
        return isinstance(payload, (dict, list)) and bool(payload)

    def status_for(ready: bool, prerequisite: bool = True) -> str:
        if ready:
            return "completed"
        return "pending" if prerequisite else "not_selected"

    def source_ready(*groups: str) -> bool:
        return any(int(source_group_counts.get(group) or 0) > 0 for group in groups)

    def add(
        block_key: str,
        title: str,
        stage: str,
        group: str,
        status: str,
        tone: str,
        *,
        summary: str = "",
        related_sections: list[str] | None = None,
        source_groups: list[str] | None = None,
        detail_type: str = "section",
        payload_extra: dict | None = None,
        markdown: str | None = None,
        agent: str = "Analysis Runtime",
        team: str = "Main View",
    ) -> None:
        payload = {
            "block_key": block_key,
            "title": title,
            "stage": stage,
            "group": group,
            "status": status,
            "tone": tone,
            "detail_type": detail_type,
            "related_sections": related_sections or [],
            "source_groups": source_groups or [],
        }
        if payload_extra:
            payload.update(payload_extra)
        sections.append(
            {
                "section_key": f"flow_block_{block_key}",
                "title": title,
                "agent": agent,
                "team": team,
                "markdown": markdown or _flow_block_markdown(title, status, summary, payload),
                "artifact_type": "flow_block",
                "flow_stage": stage,
                "flow_group": group,
                "source_kind": "flow_block",
                "source_key": block_key,
                "summary": summary,
                "payload_json": payload,
            }
        )

    source_specs = [
        ("ccxt_data", "CCXT Market Data", "market", "ccxt_market_data", "ccxt", ["ccxt_market_data"], False),
        ("market_summary", "Market Summary", "market", "ccxt_market_data", "ccxt", ["ccxt_market_data"], True),
        ("coinglass_data", "CoinGlass Data", "onchain", "coinglass_data", "coinglass", ["coinglass_data"], False),
        ("coinglass_summary", "Onchain Endpoint Summary", "onchain", "coinglass_data", "coinglass", ["coinglass_data", "endpoint_summaries"], True),
        ("news_data", "News Data", "news", "news_data", "news", ["news_data"], False),
        ("news_summary", "News Summary", "news", "news_data", "news", ["news_data"], True),
        ("social_data", "Social / Web Data", "social", "social_web_data", "social", ["social_web_data"], False),
        ("social_summary", "Social Summary", "social", "social_web_data", "social", ["social_web_data"], True),
    ]
    for block_key, title, analyst_key, group, bucket, source_groups, is_summary in source_specs:
        artifacts = _source_group_artifacts(flow_artifacts, group)
        summaries = _filter_endpoint_summaries(endpoint_summaries, bucket)
        ready = bool(summaries or artifacts or source_ready(group))
        selected = analyst_key in selected_analysts
        block_markdown = None
        detail_type = "source_summary" if is_summary else "source_group"
        block_summary = f"{title} source package for Main View."
        if is_summary:
            block_markdown = _source_group_summary_markdown(title, summaries, artifacts)
            block_summary = f"{len(summaries)} endpoint summary item(s), {len(artifacts)} source artifact(s)."
        else:
            block_summary = f"{len(artifacts)} source artifact(s) captured for {title}."
        add(
            block_key,
            title,
            "sources",
            group,
            status_for(ready, selected),
            "source",
            summary=block_summary,
            source_groups=source_groups,
            detail_type=detail_type,
            payload_extra={
                "endpoint_summary_count": len(summaries),
                "source_artifact_count": len(artifacts),
                "source_artifact_keys": [str(item.get("section_key") or "") for item in artifacts if item.get("section_key")],
                "source_artifacts": [
                    {
                        "section_key": str(item.get("section_key") or ""),
                        "title": str(item.get("title") or ""),
                        "source_kind": str(item.get("source_kind") or ""),
                        "source_key": str(item.get("source_key") or ""),
                        "summary": str(item.get("summary") or ""),
                    }
                    for item in artifacts[:48]
                ],
                "endpoint_summaries": summaries[:24],
            },
            markdown=block_markdown,
            agent="Source Layer",
            team="Source Layer",
        )

    evidence_ready = bool(final_state.get("evidence_items"))
    add("evidence_extractor", "Evidence Extractor", "evidence", "evidence_extractor", status_for(evidence_ready), "evidence", related_sections=["structured_evidence"], summary="Extracted structured evidence from source-backed analyst outputs.")

    analyst_specs = [
        ("market_analyst", "Market Analyst", "market", "market_report"),
        ("social_analyst", "Social Analyst", "social", "sentiment_report"),
        ("news_analyst", "News Analyst", "news", "news_report"),
        ("onchain_analyst", "Onchain Analyst", "onchain", "onchain_report"),
    ]
    for block_key, title, analyst_key, section_key in analyst_specs:
        selected = analyst_key in selected_analysts
        add(
            block_key,
            title,
            "analysts",
            "analyst_reports",
            status_for(has_text(section_key), selected),
            "signal",
            related_sections=[section_key],
            summary=f"{title} report block.",
            agent=title,
            team="Analyst Team",
        )

    add("evidence_ledger", "Evidence Ledger", "evidence", "evidence_extractor", status_for(evidence_ready), "evidence", related_sections=["structured_evidence"], summary="Evidence ledger available to downstream agents.")

    investment = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    add("bull_researcher", "Bull Researcher", "research", "research_debate", status_for(bool(investment.get("bull_history"))), "bull", related_sections=["bull_research"], agent="Bull Researcher", team="Research Team")
    add("bear_researcher", "Bear Researcher", "research", "research_debate", status_for(bool(investment.get("bear_history"))), "bear", related_sections=["bear_research"], agent="Bear Researcher", team="Research Team")
    add("research_debate", "Research Debate", "research", "research_debate", status_for(bool(investment.get("history"))), "debate", related_sections=["research_debate"], agent="Research Team", team="Research Team")
    add("aggressive_risk", "Aggressive Analyst", "risk", "risk_debate", status_for(bool(risk.get("aggressive_history") or risk.get("current_aggressive_response"))), "aggressive", related_sections=["aggressive_risk"], agent="Aggressive Analyst", team="Risk Team")
    add("conservative_risk", "Conservative Analyst", "risk", "risk_debate", status_for(bool(risk.get("conservative_history") or risk.get("current_conservative_response"))), "conservative", related_sections=["conservative_risk"], agent="Conservative Analyst", team="Risk Team")
    add("neutral_risk", "Neutral Analyst", "risk", "risk_debate", status_for(bool(risk.get("neutral_history") or risk.get("current_neutral_response"))), "neutral", related_sections=["neutral_risk"], agent="Neutral Analyst", team="Risk Team")
    add("risk_debate", "Risk Debate", "risk", "risk_debate", status_for(bool(risk.get("history"))), "risk", related_sections=["risk_debate"], agent="Risk Team", team="Risk Team")
    add("portfolio_manager", "Portfolio Manager", "portfolio", "final_trade_decision", status_for(has_text("final_trade_decision")), "decision", related_sections=["final_trade_decision"], agent="Portfolio Manager", team="Portfolio Management")
    add("verifier", "Verifier", "portfolio", "verification_report", status_for(has_text("verification_report")), "review", related_sections=["verification_report", "verification_report_structured"], agent="Verifier", team="Portfolio Management")
    add("decision_extractor", "Decision Extractor", "extraction", "final_trade_decision_structured", status_for(has_payload("final_trade_decision_structured")), "evidence", related_sections=["final_trade_decision_structured"], agent="Decision Extractor", team="Portfolio Management")
    add("persistence", "History + Decision Persistence", "persistence", "history_persistence", "completed", "evidence", related_sections=["history_persistence"], agent="History Store", team="Persistence")
    return sections


def build_history_sections(final_state: dict) -> list[dict]:
    sections: list[dict] = []
    seen_keys: set[str] = set()

    def add(section: dict | None) -> None:
        if not section:
            return
        key = str(section.get("section_key") or "").strip()
        if not key or key in seen_keys:
            return
        seen_keys.add(key)
        sections.append(section)

    for artifact in final_state.get("flow_artifacts") or []:
        if isinstance(artifact, dict):
            add(artifact)

    for flow_block in _build_flow_block_sections(final_state):
        add(flow_block)

    add(
        _history_section(
            "endpoint_summaries",
            "Endpoint Summaries",
            "Endpoint Summarizer",
            "Source Layer",
            _endpoint_summaries_to_markdown(final_state.get("endpoint_summaries") or []),
            artifact_type="summary",
            flow_stage="summaries",
            flow_group="endpoint_summaries",
            source_kind="summary",
            source_key="endpoint_summaries",
            payload_json=final_state.get("endpoint_summaries") or [],
        )
    )

    evidence_markdown = evidence_items_to_markdown(final_state.get("evidence_items") or [])
    add(
        _history_section(
            "structured_evidence",
            "Structured Evidence",
            "Evidence Extractor",
            "Verification",
            evidence_markdown,
            artifact_type="evidence",
            flow_stage="evidence",
            flow_group="evidence_extractor",
            source_kind="evidence",
            source_key="structured_evidence",
            payload_json=final_state.get("evidence_items") or [],
        )
    )

    for section_key in ("market_report", "onchain_report", "sentiment_report", "news_report"):
        meta = SECTION_META[section_key]
        add(
            _history_section(
                section_key,
                meta["title"],
                meta["agent"],
                meta["team"],
                final_state.get(section_key),
                artifact_type="agent_report",
                flow_stage="analysts",
                flow_group="analyst_reports",
                source_kind="agent_report",
                source_key=section_key,
            )
        )

    investment = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    extra_sections = [
        ("bull_research", "Bull Research", "Bull Researcher", "Research Team", investment.get("bull_history"), "research", "research_debate"),
        ("bear_research", "Bear Research", "Bear Researcher", "Research Team", investment.get("bear_history"), "research", "research_debate"),
        ("research_debate", "Research Debate", "Research Team", "Research Team", investment.get("history"), "research", "research_debate"),
        ("aggressive_risk", "Aggressive Risk", "Aggressive Analyst", "Risk Team", risk.get("aggressive_history") or risk.get("current_aggressive_response"), "risk", "risk_debate"),
        ("conservative_risk", "Conservative Risk", "Conservative Analyst", "Risk Team", risk.get("conservative_history") or risk.get("current_conservative_response"), "risk", "risk_debate"),
        ("neutral_risk", "Neutral Risk", "Neutral Analyst", "Risk Team", risk.get("neutral_history") or risk.get("current_neutral_response"), "risk", "risk_debate"),
        ("risk_debate", "Risk Debate", "Risk Team", "Risk Team", risk.get("history"), "risk", "risk_debate"),
    ]
    for section_key, title, agent, team, markdown, flow_stage, flow_group in extra_sections:
        add(
            _history_section(
                section_key,
                title,
                agent,
                team,
                markdown,
                artifact_type="agent_report",
                flow_stage=flow_stage,
                flow_group=flow_group,
                source_kind="agent_report",
                source_key=section_key,
            )
        )

    for section_key in ("final_trade_decision", "verification_report"):
        meta = SECTION_META[section_key]
        add(
            _history_section(
                section_key,
                meta["title"],
                meta["agent"],
                meta["team"],
                final_state.get(section_key),
                artifact_type="agent_report",
                flow_stage="decision",
                flow_group=section_key,
                source_kind="agent_report",
                source_key=section_key,
            )
        )

    structured_sections = [
        ("onchain_analysis_structured", "Onchain Analysis Payload", "Onchain Analyst", "Analyst Team", final_state.get("onchain_analysis_structured")),
        ("final_trade_decision_structured", "Decision Extractor", "Decision Extractor", "Portfolio Management", final_state.get("final_trade_decision_structured")),
        ("verification_report_structured", "Verifier Structured Payload", "Verifier", "Portfolio Management", final_state.get("verification_report_structured")),
    ]
    for section_key, title, agent, team, payload in structured_sections:
        add(
            _history_section(
                section_key,
                title,
                agent,
                team,
                _structured_payload_to_markdown(title, payload),
                artifact_type="structured_payload",
                flow_stage="extraction",
                flow_group=section_key,
                source_kind="structured_payload",
                source_key=section_key,
                payload_json=payload or {},
            )
        )
    add(
        _history_section(
            "history_persistence",
            "History + Decision Persistence",
            "History Store",
            "Persistence",
            "\n".join(
                [
                    "# History + Decision Persistence",
                    "",
                    "- Markdown/source sections were prepared from runtime state, source artifacts, debates, and final reports.",
                    "- Structured decision and verification payloads were prepared from `final_trade_decision_structured` and `verification_report_structured`.",
                    "- Numeric compatibility fields are written only when the structured decision passes validation.",
                ]
            ),
            artifact_type="persistence",
            flow_stage="persistence",
            flow_group="history_persistence",
            source_kind="persistence",
            source_key="history_persistence",
        )
    )
    return sections
