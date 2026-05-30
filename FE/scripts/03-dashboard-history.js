function getCheckedAnalysts() {
    return Array.from(elements.analystOptions.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
}

function getSelectedDepth() {
    const checked = elements.depthOptions.querySelector('input[name="researchDepth"]:checked');
    return checked ? checked.value : state.config?.analysis_defaults?.research_depth || "auto";
}

function getOutputLanguage() {
    if (elements.languageSelect.value === "__custom__") {
        return elements.customLanguageInput.value.trim();
    }
    return elements.languageSelect.value;
}

function readConfigForm() {
    const payload = collectConfigDraft();
    if (payload.selected_analysts.length === 0) {
        throw new Error("Select at least one analyst.");
    }

    if (!payload.output_language) {
        throw new Error("Output language is required.");
    }

    return payload;
}

function syncLanguageControls() {
    const isCustom = elements.languageSelect.value === "__custom__";
    elements.customLanguageField?.classList.toggle("field-muted", !isCustom);
    elements.customLanguageInput.disabled = !isCustom;
    elements.customLanguageInput.required = isCustom;
}

function syncLookbackPreset() {
    if (!state.config) {
        return;
    }
    if (elements.lookbackPresetSelect.value === CUSTOM_LOOKBACK_VALUE) {
        syncLookbackControls();
        return;
    }
    const presets = state.config.analysis_options.lookback_presets || [];
    const days = Number(elements.lookbackDaysInput.value || 0);
    const matched = presets.find((preset) => preset.days === days);
    elements.lookbackPresetSelect.value = matched ? matched.value : CUSTOM_LOOKBACK_VALUE;
    syncLookbackControls();
}

function syncLookbackControls() {
    const isCustom = elements.lookbackPresetSelect.value === CUSTOM_LOOKBACK_VALUE;
    elements.lookbackDaysField?.classList.toggle("field-muted", !isCustom);
    elements.lookbackDaysInput.disabled = !isCustom;
    elements.lookbackDaysInput.required = isCustom;
}

function syncAnalystAvailability() {
    const fundamentalsInput = elements.analystOptions.querySelector('input[value="fundamentals"]');
    if (!fundamentalsInput) {
        return;
    }

    const card = fundamentalsInput.closest(".checkbox-card");
    fundamentalsInput.disabled = false;
    card?.classList.remove("checkbox-card-disabled");
}

function refreshConfigUi() {
    syncLanguageControls();
    syncLookbackPreset();
    syncAnalystAvailability();
    renderConfigPreview();
    renderTopNotice();
    if (!state.isBusy) {
        renderTeamStatusGrid();
    }
}

function renderTopNotice() {
    const warningText = state.run.warnings[0];
    if (warningText) {
        elements.topNoticeText.textContent = warningText;
        elements.topNoticeText.title = warningText;
        return;
    }

    if (!state.config) {
        const fallbackNotice = "Loading backend configuration.";
        elements.topNoticeText.textContent = fallbackNotice;
        elements.topNoticeText.title = fallbackNotice;
        return;
    }

    const payload = getConfigSnapshot();
    let notice = "Ready to run analysis.";
    if (state.run.cancelled) {
        const symbol = state.run.meta?.symbol || payload?.symbol || state.config.analysis_defaults.symbol;
        notice = `${symbol} - analysis stopped`;
    } else if (state.isBusy) {
        const progress = state.run.status?.progress || { completed: 0, total: 0 };
        const symbol = state.run.meta?.symbol || payload?.symbol || state.config.analysis_defaults.symbol;
        const depth = state.run.meta?.research_depth || payload?.research_depth || state.config.analysis_defaults.research_depth;
        const lookback = state.run.meta?.lookback_days || payload?.lookback_days || state.config.analysis_defaults.lookback_days;
        notice = `${symbol} - ${lookback}d - ${depth} depth - ${progress.completed}/${progress.total} tasks`;
    } else if (state.run.complete) {
        const symbol = state.run.meta?.symbol || payload?.symbol || state.config.analysis_defaults.symbol;
        const signal = state.run.complete.signal || "analysis completed";
        const elapsed = state.run.complete.elapsed_seconds ? ` - ${state.run.complete.elapsed_seconds}s` : "";
        notice = `${symbol} - ${signal}${elapsed}`;
    } else if (payload) {
        notice = `${payload.symbol || "-"} - ${payload.lookback_days || "-"}d - ${payload.output_language || "-"} - ${payload.selected_analysts.length} analysts`;
    }

    elements.topNoticeText.textContent = notice;
    elements.topNoticeText.title = notice;
}

function getCompactAgentLabel(label = "") {
    if (COMPACT_AGENT_LABELS[label]) {
        return COMPACT_AGENT_LABELS[label];
    }

    return String(label)
        .replace(/ Analyst$/, "")
        .replace(/ Researcher$/, "");
}

function getGroupDetailDescriptor(groupKey, items = []) {
    const preferredItem = items.find((item) => item.status === "completed") || items[0];
    return preferredItem ? getTaskDetailDescriptor(groupKey, preferredItem) : null;
}

function renderTeamStatusGrid() {
    const groups = getStatusGroups();
    setElementLoadingState(elements.teamStatusGrid, state.isBusy && !state.run.status, "Syncing teams");

    const renderAgentCell = (groupKey, item) => {
        const detail = getTaskDetailDescriptor(groupKey, item);
        const interactive = Boolean(detail);
        const dataset = interactive ? buildDetailDataset(detail) : "";
        const compactLabel = getCompactAgentLabel(item.label);
        const statusLabel = STATUS_LABELS[item.status] || item.status;
        const roleContent = `
            <span class="execution-status-icon status-${item.status}" title="${escapeHtml(item.status)}" aria-hidden="true"></span>
            <span class="execution-status-agent">${escapeHtml(compactLabel)}</span>
        `;

        if (interactive) {
            return `
                <button type="button"
                    class="execution-status-role role-${escapeHtml(item.key)} status-${item.status} detail-trigger"
                    ${dataset}
                    title="${escapeHtml(item.label)}"
                    aria-label="Open ${escapeHtml(item.label)} detail, ${escapeHtml(statusLabel)}">
                    ${roleContent}
                </button>
            `;
        }

        return `<span class="execution-status-role role-${escapeHtml(item.key)} status-${item.status}" title="${escapeHtml(item.label)}">${roleContent}</span>`;
    };

    elements.teamStatusGrid.innerHTML = `
        <div class="execution-status-table-wrap">
            <table class="execution-status-table">
                <thead>
                    <tr>
                        <th scope="col">Team</th>
                        <th scope="col">Role</th>
                    </tr>
                </thead>
                <tbody>
                    ${Object.entries(groups)
                        .map(
                            ([groupKey, items]) => {
                                const groupDetail = getGroupDetailDescriptor(groupKey, items);
                                const groupDataset = groupDetail ? buildDetailDataset(groupDetail) : "";
                                const groupLabel = GROUP_LABELS[groupKey] || groupKey;
                                return `
                                    <tr>
                                        <th scope="row" class="execution-status-team ${groupDetail ? "detail-trigger" : ""}"
                                            ${groupDataset}
                                            title="Open ${escapeHtml(groupLabel)} detail">
                                            ${escapeHtml(groupLabel)}
                                        </th>
                                        <td class="execution-status-role-cell ${groupDetail ? "detail-trigger" : ""}"
                                            ${groupDataset}
                                            title="Open ${escapeHtml(groupLabel)} detail">
                                            <div class="execution-status-list execution-status-list-${escapeHtml(groupKey)}">
                                                ${items.map((item) => renderAgentCell(groupKey, item)).join("")}
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            },
                        )
                        .join("")}
                </tbody>
            </table>
        </div>
    `;
}

function renderProgress() {
    const progress = state.run.status?.progress || { completed: 0, total: 0, percent: 0 };
    const runStatus = state.run.cancelled
        ? "Stopped"
        : state.isBusy
        ? "Running"
        : state.run.complete
        ? "Completed"
        : state.run.warnings.length
        ? "Attention"
        : "Idle";

    elements.progressText.textContent = `${progress.completed} / ${progress.total}`;
    elements.progressPercentText.textContent = `${progress.percent || 0}%`;
    elements.progressFill.style.width = `${progress.percent || 0}%`;
    const phaseLabel = state.run.cancelled
        ? "cancelled"
        : state.isBusy
        ? state.run.status?.phase || "running"
        : state.run.complete
        ? "completed"
        : "ready";
    elements.phaseText.textContent = phaseLabel;
    elements.currentAgentText.textContent = state.run.status?.current_agent || "Waiting";
    elements.currentAgentText.title = elements.currentAgentText.textContent;
    elements.runStatusBadge.textContent = runStatus;
    elements.runStatusBadge.dataset.state = runStatus.toLowerCase();
    elements.endpointText.textContent = formatApiBaseLabel(state.apiBaseUrl);
    elements.endpointText.title = state.apiBaseUrl || "API unresolved";
    if (state.run.complete?.elapsed_seconds) {
        elements.elapsedText.textContent = `${state.run.complete.elapsed_seconds} s total`;
    } else if (state.run.cancelled) {
        elements.elapsedText.textContent = "Stopped by client";
    } else {
        elements.elapsedText.textContent = state.isBusy ? "Live stream active" : "Awaiting run";
    }
}

function getAnalysisDepthLabel(source = {}) {
    const requested = String(source.research_depth || "auto").trim() || "auto";
    const effective = String(source.effective_research_depth || source.effective_depth || "").trim();
    if (effective && effective !== requested) {
        return `${requested} / ${effective}`;
    }
    return requested;
}

function getConfigAnalystLabel(value) {
    const analyst = state.config?.analysis_options?.analysts?.find((item) => item.value === value);
    return analyst?.label || value;
}

function renderConfigPreview() {
    if (!(elements.configPreview instanceof HTMLElement)) {
        return;
    }

    const payload = getConfigSnapshot();
    if (!payload) {
        elements.configPreview.innerHTML = '<div class="config-preview-empty">Loading config.</div>';
        return;
    }

    const depthOption = state.config?.analysis_options?.research_depths?.find((item) => item.value === payload.research_depth);
    const effectiveDepth = depthOption?.effective_depth && depthOption.effective_depth !== payload.research_depth
        ? ` / ${depthOption.effective_depth}`
        : "";
    const analysts = (payload.selected_analysts || []).map(getConfigAnalystLabel);
    const lookbackLabel = payload.lookback_days ? `${payload.lookback_days}d` : "-";

    elements.configPreview.innerHTML = `
        <div class="config-preview-header">
            <span>Run Snapshot</span>
            <strong>${escapeHtml(payload.symbol || "-")}</strong>
        </div>
        <div class="config-summary-grid">
            <div class="config-summary-chip">
                <span>Lookback</span>
                <strong>${escapeHtml(lookbackLabel)}</strong>
            </div>
            <div class="config-summary-chip">
                <span>Depth</span>
                <strong>${escapeHtml(`${payload.research_depth || "auto"}${effectiveDepth}`)}</strong>
            </div>
            <div class="config-summary-chip">
                <span>Model</span>
                <strong>${escapeHtml(payload.model || "-")}</strong>
            </div>
            <div class="config-summary-chip">
                <span>Language</span>
                <strong>${escapeHtml(payload.output_language || "-")}</strong>
            </div>
        </div>
        <div class="config-summary-note">
            <span>Analysts</span>
            <strong>${escapeHtml(analysts.join(", ") || "-")}</strong>
        </div>
    `;
}

function getFlowSectionOrder() {
    return [
        ...(HISTORY_FLOW_SECTION_ORDER.sources || []),
        ...(HISTORY_FLOW_SECTION_ORDER.inputs || []),
        ...(HISTORY_FLOW_SECTION_ORDER.evidence || []),
        ...(HISTORY_FLOW_SECTION_ORDER.research || []),
        ...(HISTORY_FLOW_SECTION_ORDER.trading || []),
        ...(HISTORY_FLOW_SECTION_ORDER.risk || []),
        ...(HISTORY_FLOW_SECTION_ORDER.portfolio || []),
    ];
}

function getFlowSectionTitle(sectionKey) {
    return HISTORY_FLOW_SECTION_META[sectionKey]?.shortTitle
        || sectionKey.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderFlowMetric(label, value, tone = "") {
    const normalizedValue = value === 0 ? "0" : value || "-";
    return `
        <div class="flow-metric ${tone ? `flow-metric-${escapeHtml(tone)}` : ""}">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(String(normalizedValue))}</strong>
        </div>
    `;
}

function getLiveEvidenceCount() {
    const completeCount = state.run.complete?.evidence_count;
    if (completeCount !== undefined && completeCount !== null) {
        return Number(completeCount) || 0;
    }
    return Number(state.run.evidenceCount || state.run.evidenceItems?.length || 0);
}

const SOURCE_ARTIFACT_GROUPS = {
    ccxt: { flowGroup: "ccxt_market_data", title: "CCXT Market Data" },
    coinglass: { flowGroup: "coinglass_data", title: "CoinGlass Data" },
    news: { flowGroup: "news_data", title: "News Data" },
    social: { flowGroup: "social_web_data", title: "Social / Web Data" },
    flow: { flowGroup: "flow_data", title: "Flow Data" },
};

function getLiveSourceArtifactCount() {
    if (state.run.complete?.source_artifact_count !== undefined && state.run.complete?.source_artifact_count !== null) {
        return Number(state.run.complete.source_artifact_count) || 0;
    }
    if (Number(state.run.sourceArtifactCount || 0) > 0) {
        return Number(state.run.sourceArtifactCount || 0);
    }
    const keys = new Set();
    ["ccxt", "coinglass", "news", "social", "flow"].forEach((groupKey) => {
        getLiveSourceTraceEntries(groupKey).forEach((entry) => keys.add(entry.id || `${entry.agent}:${entry.title}:${entry.traceId}`));
    });
    return keys.size;
}

function getLiveSourceTraceEntries(groupKey = "") {
    const entries = Array.isArray(state.run.traceFeed) ? state.run.traceFeed : [];
    return entries.filter((entry) => {
        if (!entry || !["tool_result", "tool_trace"].includes(entry.phase)) {
            return false;
        }
        const title = String(entry.title || "").toLowerCase();
        const agent = String(entry.agent || "").toLowerCase();
        const traceId = String(entry.traceId || entry.trace_id || "").toLowerCase();
        if (groupKey === "ccxt") {
            return title === "get_crypto_ohlcv" || title === "get_crypto_indicators";
        }
        if (groupKey === "coinglass") {
            return traceId.startsWith("coinglass:") || title.includes("coinglass");
        }
        if (groupKey === "news") {
            return agent.includes("news") || title.includes("news") || title === "get_global_news";
        }
        if (groupKey === "social") {
            return agent.includes("social") || title.includes("reddit") || title.includes("stocktwits");
        }
        if (groupKey === "flow") {
            return agent.includes("flow") && !traceId.startsWith("coinglass:");
        }
        return false;
    });
}

function requestSavedSourceArtifacts(groupKey = "") {
    const config = SOURCE_ARTIFACT_GROUPS[groupKey];
    const historyId = state.run.complete?.history_id;
    if (!config || !historyId || !canReadHistory()) {
        return;
    }
    state.run.sourceArtifactLists = state.run.sourceArtifactLists || {};
    state.run.sourceArtifactLoading = state.run.sourceArtifactLoading || {};
    state.run.sourceArtifactErrors = state.run.sourceArtifactErrors || {};
    if (Array.isArray(state.run.sourceArtifactLists[groupKey]) || state.run.sourceArtifactLoading[groupKey]) {
        return;
    }
    state.run.sourceArtifactLoading[groupKey] = true;
    state.run.sourceArtifactErrors[groupKey] = "";
    apiFetch(`/api/history/${encodeURIComponent(historyId)}/artifacts?flow_group=${encodeURIComponent(config.flowGroup)}`, {
        headers: getAuthHeaders(),
        cache: "no-store",
    })
        .then(async (response) => {
            if (!response.ok) {
                throw new Error(await readResponseError(response));
            }
            return response.json();
        })
        .then((payload) => {
            state.run.sourceArtifactLists[groupKey] = Array.isArray(payload.artifacts) ? payload.artifacts : [];
            state.run.sourceArtifactErrors[groupKey] = "";
        })
        .catch((error) => {
            state.run.sourceArtifactErrors[groupKey] = error instanceof Error ? error.message : String(error || "Could not load source artifacts.");
        })
        .finally(() => {
            state.run.sourceArtifactLoading[groupKey] = false;
            renderActiveDetail();
            renderReportGrid();
        });
}

function buildSourceArtifactRows(groupKey = "") {
    requestSavedSourceArtifacts(groupKey);
    const savedRows = (state.run.sourceArtifactLists?.[groupKey] || []).map((item) => ({
        kind: "saved",
        id: item.section_key || "",
        runId: state.run.complete?.history_id || "",
        sectionKey: item.section_key || "",
        title: item.title || item.source_key || "Source artifact",
        agent: item.agent || "-",
        sourceKind: item.source_kind || item.artifact_type || "-",
        sourceKey: item.source_key || "-",
        query: item.summary || item.source_key || "-",
        result: item.created_at ? `Saved ${formatHistoryTimestamp(item.created_at)}` : "Saved artifact",
    }));
    if (savedRows.length) {
        return savedRows;
    }
    return getLiveSourceTraceEntries(groupKey).map((entry) => ({
        kind: "trace",
        id: entry.id || "",
        traceId: entry.id || "",
        title: entry.title || "Tool",
        agent: entry.agent || "-",
        sourceKind: entry.phase || "tool_trace",
        sourceKey: entry.traceId || "-",
        query: compactText(stripMarkdownToPlainText(entry.toolCallContent || ""), 180) || "-",
        result: compactText(stripMarkdownToPlainText(entry.toolResultContent || entry.content || ""), 220) || "-",
    }));
}

function renderSourceArtifactTable(rows = [], fallback = "No source artifacts are available yet.", groupKey = "") {
    if (!rows.length) {
        return `<div class="source-artifact-empty">${escapeHtml(fallback)}</div>`;
    }
    const loading = Boolean(state.run.sourceArtifactLoading?.[groupKey]);
    const error = state.run.sourceArtifactErrors?.[groupKey] || "";
    return `
        <div class="source-artifact-table-shell">
            ${loading ? '<div class="source-artifact-note">Loading saved artifacts...</div>' : ""}
            ${error ? `<div class="source-artifact-note source-artifact-note-warning">${escapeHtml(error)}</div>` : ""}
            <div class="source-artifact-table-wrap">
                <table class="source-artifact-table">
                    <thead>
                        <tr>
                            <th scope="col">Source</th>
                            <th scope="col">Agent</th>
                            <th scope="col">Kind</th>
                            <th scope="col">Query / Endpoint</th>
                            <th scope="col">Result</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map((row) => `
                            <tr>
                                <td>
                                    <button class="source-artifact-open" type="button"
                                        data-source-detail-kind="${escapeHtml(row.kind)}"
                                        data-source-detail-id="${escapeHtml(row.id)}"
                                        data-source-detail-run-id="${escapeHtml(row.runId || "")}"
                                        data-source-detail-section-key="${escapeHtml(row.sectionKey || "")}">
                                        ${escapeHtml(row.title || "Source")}
                                    </button>
                                </td>
                                <td>${escapeHtml(row.agent || "-")}</td>
                                <td>${escapeHtml(row.sourceKind || "-")}</td>
                                <td>${escapeHtml(row.query || row.sourceKey || "-")}</td>
                                <td>${escapeHtml(row.result || "-")}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        </div>
    `;
}

function setSourceArtifactTablePreview(element, rows = [], fallback = "", groupKey = "") {
    element.innerHTML = renderSourceArtifactTable(rows, fallback, groupKey);
    element.classList.remove("compact-preview");
    element.classList.toggle("is-empty", !rows.length);
}

function getSourceArtifactDetailContent(groupKey = "", fallback = "") {
    const rows = buildSourceArtifactRows(groupKey);
    return {
        mode: "source-table",
        rows,
        groupKey,
        fallback: state.run.sourceArtifactLoading?.[groupKey] && !rows.length
            ? "Loading saved source artifacts..."
            : fallback,
    };
}

function formatLiveSourceTraceMarkdown(groupKey = "", title = "Source Data") {
    const entries = getLiveSourceTraceEntries(groupKey);
    if (!entries.length) {
        return "";
    }
    return entries
        .map((entry, index) => {
            const body = entry.toolResultContent || entry.content || "";
            return [
                `## ${index + 1}. ${entry.title || title}`,
                `- Agent: ${entry.agent || "-"}`,
                `- Phase: ${formatTracePhaseLabel(entry.phase)}`,
                `- Trace ID: ${entry.traceId || "-"}`,
                `- Captured: ${entry.timestamp || "-"}`,
                "",
                body,
            ].join("\n");
        })
        .join("\n\n");
}

function renderLiveFlowLeaf(node = {}) {
    const isReady = Boolean(node.ready);
    const detail = isReady ? node.detail : null;
    const dataset = detail ? buildDetailDataset(detail) : "";
    const tag = detail ? "button" : "span";
    const typeAttr = detail ? ' type="button"' : "";
    const classes = [
        "flow-section-item",
        "live-flow-node",
        node.tone ? `live-flow-node-${node.tone}` : "",
        isReady ? "is-ready detail-trigger" : "is-pending is-disabled",
    ].filter(Boolean).join(" ");
    return `
        <${tag}${typeAttr} class="${classes}" ${dataset} title="${escapeHtml(node.title || "Flow block")}">
            <span class="flow-section-dot" aria-hidden="true"></span>
            <span>${escapeHtml(node.title || "Flow")}</span>
        </${tag}>
    `;
}

function renderLiveFlowNode(node = {}) {
    if (Array.isArray(node.nodes)) {
        return `
            <div class="live-flow-group live-flow-group-${escapeHtml(node.tone || "neutral")}">
                <span class="live-flow-group-title">${escapeHtml(node.title || "Flow Stage")}</span>
                <div class="live-flow-group-grid">
                    ${node.nodes.map(renderLiveFlowLeaf).join("")}
                </div>
            </div>
        `;
    }
    return renderLiveFlowLeaf(node);
}

function buildLiveFlowNodes() {
    const selectedAnalysts = new Set(state.run.meta?.selected_analysts || ["market", "social", "news", "fundamentals"]);
    const hasSection = (key) => Boolean(String(state.run.sections?.[key] || "").trim());
    const hasStructuredPayload = (key) => {
        const payload = state.run.structured?.[key];
        return Boolean(payload && typeof payload === "object" && Object.keys(payload).length);
    };
    const evidenceReady = getLiveEvidenceCount() > 0;
    const endpointReady = Boolean(state.run.endpointSummaries?.length);
    const savedGroupReady = (groupKey) => {
        const flowGroup = SOURCE_ARTIFACT_GROUPS[groupKey]?.flowGroup || "";
        return Number(state.run.sourceArtifactGroups?.[flowGroup] || 0) > 0;
    };
    const ccxtReady = getLiveSourceTraceEntries("ccxt").length > 0 || savedGroupReady("ccxt");
    const coinglassReady = endpointReady || getLiveSourceTraceEntries("coinglass").length > 0 || savedGroupReady("coinglass");
    const newsSourceReady = getLiveSourceTraceEntries("news").length > 0 || savedGroupReady("news");
    const socialSourceReady = getLiveSourceTraceEntries("social").length > 0 || savedGroupReady("social");
    const flowSourceReady = getLiveSourceTraceEntries("flow").length > 0 || savedGroupReady("flow");
    const analystNodes = [
        ["market", "market_report", "Market Analyst"],
        ["social", "sentiment_report", "Social Analyst"],
        ["news", "news_report", "News Analyst"],
        ["fundamentals", "flow_report", "Flow Analyst"],
    ]
        .filter(([analystKey, sectionKey]) => selectedAnalysts.has(analystKey) || hasSection(sectionKey))
        .map(([_analystKey, sectionKey, title]) => ({
            title,
            ready: hasSection(sectionKey),
            tone: "signal",
            detail: {
                type: "report",
                section: sectionKey,
                title,
                subtitle: "Analyst report",
            },
        }));

    return [
        {
            title: "Parallel endpoint summaries",
            tone: "evidence",
            nodes: [
                {
                    title: "CCXT Market Data",
                    ready: ccxtReady,
                    tone: "signal",
                    detail: { key: "liveCcxtData" },
                },
                {
                    title: "CoinGlass Data",
                    ready: coinglassReady,
                    tone: "evidence",
                    detail: { key: "liveCoinGlassData" },
                },
                {
                    title: "News Data",
                    ready: newsSourceReady,
                    tone: "signal",
                    detail: { key: "liveNewsData" },
                },
                {
                    title: "Social / Web Data",
                    ready: socialSourceReady,
                    tone: "signal",
                    detail: { key: "liveSocialData" },
                },
                {
                    title: "Flow Data",
                    ready: flowSourceReady,
                    tone: "signal",
                    detail: { key: "liveFlowData" },
                },
                {
                    title: "Endpoint Summaries",
                    ready: endpointReady,
                    tone: "evidence",
                    detail: { key: "endpointSummaries" },
                },
            ],
        },
        {
            title: "Evidence Extractor",
            ready: evidenceReady,
            tone: "evidence",
            detail: { key: "evidenceExtractor" },
        },
        {
            title: "Analysts",
            tone: "signal",
            nodes: analystNodes,
        },
        {
            title: "Evidence Ledger",
            ready: evidenceReady,
            tone: "evidence",
            detail: { key: "evidenceLedger" },
        },
        {
            title: "Research Chamber",
            tone: "debate",
            nodes: [
                {
                    title: "Bull Researcher",
                    ready: Boolean(state.run.research?.bull_history),
                    tone: "bull",
                    detail: { key: "bullResearch" },
                },
                {
                    title: "Bear Researcher",
                    ready: Boolean(state.run.research?.bear_history),
                    tone: "bear",
                    detail: { key: "bearResearch" },
                },
                {
                    title: "Research Debate",
                    ready: Boolean(state.run.research?.history),
                    tone: "debate",
                    detail: { key: "researchDebate" },
                },
            ],
        },
        {
            title: "Research Manager",
            ready: hasSection("investment_plan"),
            tone: "plan",
            detail: {
                type: "report",
                section: "investment_plan",
                title: "Research Manager",
                subtitle: "Investment plan",
            },
        },
        ...(hasStructuredPayload("investment_plan") ? [{
            title: "Investment Extractor",
            ready: true,
            tone: "evidence",
            detail: { key: "investmentExtractor" },
        }] : []),
        {
            title: "Trader",
            ready: hasSection("trader_investment_plan"),
            tone: "trader",
            detail: {
                type: "report",
                section: "trader_investment_plan",
                title: "Trader",
                subtitle: "Transaction proposal",
            },
        },
        ...(hasStructuredPayload("trader_investment_plan") ? [{
            title: "Trader Extractor",
            ready: true,
            tone: "evidence",
            detail: { key: "traderExtractor" },
        }] : []),
        {
            title: "Risk Room",
            tone: "risk",
            nodes: [
                {
                    title: "Aggressive Risk",
                    ready: Boolean(state.run.risk?.aggressive_history),
                    tone: "aggressive",
                    detail: { key: "aggressiveRisk" },
                },
                {
                    title: "Neutral Risk",
                    ready: Boolean(state.run.risk?.neutral_history),
                    tone: "neutral",
                    detail: { key: "neutralRisk" },
                },
                {
                    title: "Conservative Risk",
                    ready: Boolean(state.run.risk?.conservative_history),
                    tone: "conservative",
                    detail: { key: "conservativeRisk" },
                },
                {
                    title: "Risk Debate",
                    ready: Boolean(state.run.risk?.history),
                    tone: "risk",
                    detail: { key: "riskDebate" },
                },
            ],
        },
        {
            title: "Portfolio Manager",
            ready: hasSection("final_trade_decision"),
            tone: "decision",
            detail: {
                type: "report",
                section: "final_trade_decision",
                title: "Portfolio Manager",
                subtitle: "Final decision",
            },
        },
        ...(hasStructuredPayload("final_trade_decision") ? [{
            title: "Decision Extractor",
            ready: true,
            tone: "evidence",
            detail: { key: "decisionExtractor" },
        }] : []),
        {
            title: "Verifier",
            ready: hasSection("verification_report"),
            tone: "review",
            detail: {
                type: "report",
                section: "verification_report",
                title: "Verifier",
                subtitle: "Decision audit",
            },
        },
        ...(hasStructuredPayload("verification_report") ? [{
            title: "Verifier Payload",
            ready: true,
            tone: "evidence",
            detail: { key: "verifierStructured" },
        }] : []),
    ];
}

function renderLiveAgentFlow() {
    const nodes = buildLiveFlowNodes();
    return nodes
        .map((node, index) => `
            <div class="live-flow-stage">
                ${renderLiveFlowNode(node)}
                ${index < nodes.length - 1 ? '<span class="live-flow-connector" aria-hidden="true"></span>' : ""}
            </div>
        `)
        .join("");
}

function renderFlowInspectorMarkup() {
    const complete = state.run.complete || {};
    const telemetry = complete.telemetry || {};
    const signal = complete.signal || (state.run.cancelled ? "Stopped" : state.isBusy ? "Running" : "Pending");
    const verdict = complete.verification_verdict || "-";
    const verificationAction = complete.verification_action || "-";
    const warningItems = state.run.warnings.slice(0, 2);
    const latestTool = [...state.run.traceFeed].reverse().find((item) => isToolTracePhase(item.phase));
    const currentFocus = state.run.status?.current_agent || "Waiting";
    const latestOutput = state.run.latestReportTitle || complete.signal || state.run.cancelled?.message || latestTool?.title || "-";

    return `
        <div class="flow-inspector-header">
            <span>Flow Snapshot</span>
            <strong>${escapeHtml(signal)}</strong>
        </div>
        <div class="flow-metric-grid">
            ${renderFlowMetric("Verdict", verdict, verdict === "Revise" || verdict === "Caution" ? "warning" : "")}
            ${renderFlowMetric("Action", verificationAction, verdict === "Revise" || verdict === "Caution" ? "warning" : "")}
            ${renderFlowMetric("Sources", getLiveSourceArtifactCount() || "-")}
            ${renderFlowMetric("Evidence", getLiveEvidenceCount() || "-")}
            ${renderFlowMetric("Web Search", telemetry.web_search_calls ?? "-")}
            ${renderFlowMetric("Model Calls", telemetry.model_calls ?? "-")}
            ${renderFlowMetric("Tool Events", telemetry.tool_calls ?? "-")}
        </div>
        <div class="flow-latest">
            <span>Current Focus</span>
            <strong>${escapeHtml(currentFocus)}</strong>
        </div>
        <div class="flow-latest">
            <span>Latest Output</span>
            <strong>${escapeHtml(latestOutput)}</strong>
        </div>
        <div class="flow-section-list live-agent-flow" aria-label="Agent flow">
            ${renderLiveAgentFlow()}
        </div>
        ${
            warningItems.length
                ? `<div class="flow-warning-list">${warningItems.map((warning) => `<span>${escapeHtml(compactText(warning, 96))}</span>`).join("")}</div>`
                : ""
        }
    `;
}

function clearDetailAttributes(element) {
    ["data-detail-key", "data-detail-section", "data-detail-title", "data-detail-subtitle"].forEach((attribute) => {
        element.removeAttribute(attribute);
    });
}

function applyDetailAttributes(element, detail) {
    clearDetailAttributes(element);
    if (!detail) {
        return;
    }
    if (detail.type === "report") {
        element.dataset.detailSection = detail.section || "";
        element.dataset.detailTitle = detail.title || "Report Detail";
        element.dataset.detailSubtitle = detail.subtitle || detail.title || "Agent report";
        return;
    }
    if (detail.key) {
        element.dataset.detailKey = detail.key;
    }
}

function renderReportGrid() {
    const focus = getCurrentLivePanel();
    const focusId = getFocusIdentity(focus);
    const hasInspector = Boolean(elements.reportGrid.querySelector(".flow-inspector"));
    let card = elements.reportGrid.querySelector(".live-focus-card");
    if (!(card instanceof HTMLElement) || !hasInspector || card.dataset.focusId !== focusId) {
        elements.reportGrid.innerHTML = `
            <div class="live-layout live-layout-with-inspector">
                <article class="live-focus-card live-focus-card-expanded">
                    <div class="live-focus-topline">
                        <span class="live-chip"></span>
                        <div class="live-focus-actions">
                            <span class="live-focus-status"></span>
                            <button class="live-detail-button detail-trigger hidden" type="button">Open</button>
                        </div>
                    </div>
                    <h3 class="live-focus-title"></h3>
                    <div class="live-focus-body markdown-preview"></div>
                </article>
                <aside class="flow-inspector" aria-label="Flow snapshot"></aside>
            </div>
        `;
        card = elements.reportGrid.querySelector(".live-focus-card");
    }

    if (!(card instanceof HTMLElement)) {
        return;
    }

    const liveChip = card.querySelector(".live-chip");
    const liveStatus = card.querySelector(".live-focus-status");
    const detailButton = card.querySelector(".live-detail-button");
    const liveTitle = card.querySelector(".live-focus-title");
    const liveBody = card.querySelector(".live-focus-body");
    const inspector = elements.reportGrid.querySelector(".flow-inspector");
    const tone = focus.tone || "idle";
    const bodyMarkup = formatBlock(focus.content, focus.fallback);
    const bodyFingerprint = `${focusId}:${focus.content || ""}:${focus.fallback}`;

    card.dataset.focusId = focusId;
    card.className = `live-focus-card live-focus-card-expanded live-tone-${tone}`;
    const isAwaitingFocus = state.isBusy && !String(focus.content || "").trim();
    setElementLoadingState(card, isAwaitingFocus, state.run.status?.current_agent ? `Waiting ${getCompactAgentLabel(state.run.status.current_agent)}` : "Streaming");
    card.removeAttribute("tabindex");
    card.removeAttribute("role");
    card.setAttribute("aria-label", focus.title);
    clearDetailAttributes(card);

    if (liveChip instanceof HTMLElement) {
        liveChip.className = `live-chip live-chip-${tone}`;
        liveChip.textContent = focus.badge || "Live";
    }
    if (liveStatus instanceof HTMLElement) {
        liveStatus.textContent = focus.subtitle || "";
    }
    if (detailButton instanceof HTMLElement) {
        detailButton.classList.toggle("hidden", !focus.detail);
        detailButton.removeAttribute("aria-label");
        applyDetailAttributes(detailButton, focus.detail);
        if (focus.detail) {
            detailButton.setAttribute("aria-label", `Open ${focus.title} detail`);
        }
    }
    if (liveTitle instanceof HTMLElement) {
        liveTitle.textContent = focus.title;
    }
    if (liveBody instanceof HTMLElement && liveBody.dataset.fingerprint !== bodyFingerprint) {
        preserveScrollPosition(liveBody, () => {
            liveBody.innerHTML = bodyMarkup;
            liveBody.classList.toggle("is-empty", !focus.content);
            liveBody.dataset.fingerprint = bodyFingerprint;
        });
    }
    if (inspector instanceof HTMLElement) {
        inspector.innerHTML = renderFlowInspectorMarkup();
    }

    elements.activeReportText.textContent = state.run.cancelled?.message
        || (state.isBusy ? "Live markdown stream" : state.run.complete?.signal || "Awaiting live stream");
}

function getLogEntryKey(item, index) {
    return item.id || buildContentFingerprint(item.label, item.timestamp, item.summary, item.detail, index) || `log-${index}`;
}

function createLogEntryNode() {
    const node = document.createElement("article");
    node.innerHTML = `
        <div class="event-log-topline">
            <strong class="event-log-label"></strong>
            <span></span>
        </div>
        <p class="event-log-message"></p>
    `;
    return node;
}

function updateLogEntryNode(node, item, key, useDetail) {
    node.dataset.logKey = key;
    node.className = `event-log-item event-log-level-${item.level || "info"}`;
    const label = node.querySelector(".event-log-label");
    const timestamp = node.querySelector(".event-log-topline span");
    const message = node.querySelector(".event-log-message");
    if (label instanceof HTMLElement) {
        label.textContent = item.label;
    }
    if (timestamp instanceof HTMLElement) {
        timestamp.textContent = item.timestamp;
    }
    if (message instanceof HTMLElement) {
        message.textContent = useDetail ? item.detail : item.summary;
    }
}

function createLogEmptyNode(emptyText) {
    const node = document.createElement("div");
    node.className = "event-log-empty";
    node.textContent = emptyText;
    return node;
}

function renderLogEntries(element, entries, emptyText, options = {}) {
    if (!(element instanceof HTMLElement)) {
        return;
    }

    const useDetail = Boolean(options.useDetail);
    const shouldStickToBottom = shouldAutoScrollLog(element);
    const existingNodes = new Map(
        Array.from(element.querySelectorAll(".event-log-item[data-log-key]"))
            .filter((child) => child instanceof HTMLElement)
            .map((child) => [String(child.dataset.logKey || ""), child]),
    );

    if (!entries.length) {
        const currentEmpty = element.querySelector(".event-log-empty");
        if (!(currentEmpty instanceof HTMLElement) || currentEmpty.textContent !== emptyText || element.children.length !== 1) {
            element.replaceChildren(createLogEmptyNode(emptyText));
        }
        return;
    }

    const newKeys = new Set();
    const desiredNodes = [];
    const desiredKeys = new Set();
    entries.forEach((item, index) => {
        const key = getLogEntryKey(item, index);
        desiredKeys.add(key);
        let node = existingNodes.get(key);
        if (!(node instanceof HTMLElement)) {
            node = createLogEntryNode();
            newKeys.add(key);
        }
        updateLogEntryNode(node, item, key, useDetail);
        desiredNodes.push(node);
    });

    const viewportSnapshot = shouldStickToBottom ? null : getLogScrollSnapshot(element, desiredKeys);

    Array.from(element.children).forEach((child) => {
        if (!(child instanceof HTMLElement)) {
            return;
        }
        const key = String(child.dataset.logKey || "");
        if (child.classList.contains("event-log-item") && !desiredKeys.has(key)) {
            child.remove();
        }
    });

    const firstMissingIndex = desiredNodes.findIndex((node) => node.parentElement !== element);
    if (firstMissingIndex >= 0) {
        for (let index = firstMissingIndex; index < desiredNodes.length; index += 1) {
            element.appendChild(desiredNodes[index]);
        }
    }

    desiredNodes.forEach((node) => {
        node.classList.toggle("event-log-item-new", shouldStickToBottom && newKeys.has(node.dataset.logKey || ""));
    });

    if (shouldStickToBottom) {
        requestAnimationFrame(() => {
            if (!shouldAutoScrollLog(element)) {
                return;
            }
            element.scrollTop = element.scrollHeight;
        });
        return;
    }

    if (viewportSnapshot) {
        const anchorNode = desiredNodes.find((node) => String(node.dataset.logKey || "") === viewportSnapshot.anchorKey) || null;
        if (anchorNode instanceof HTMLElement) {
            element.scrollTop = Math.max(0, anchorNode.offsetTop + viewportSnapshot.anchorOffset);
            return;
        }
        element.scrollTop = Math.max(0, viewportSnapshot.scrollTop - viewportSnapshot.removedAboveViewportHeight);
    }
}

function renderOperationsRail() {
    const toolFeed = state.run.traceFeed.filter((item) => isToolTracePhase(item.phase));
    const visibleToolLimit = Math.max(
        TRACE_DISPLAY_LIMIT,
        Math.min(TRACE_FEED_LIMIT, toolFeed.length),
    );
    const feed = toolFeed.slice(-visibleToolLimit);
    const newestTool = feed[feed.length - 1];
    const latestUpdate = state.run.latestReportTitle || state.run.complete?.signal || state.run.cancelled?.message || newestTool?.title || "No updates yet";
    const totalToolEvents = toolFeed.length;
    const totalLogEvents = state.run.logEntries.length;

    elements.opsStatusText.textContent = state.run.cancelled
        ? "Run stopped"
        : state.isBusy
        ? `${feed.length} live updates`
        : state.run.complete
        ? "Run completed"
        : "Watching stream";
    elements.opsAgentText.textContent = totalToolEvents ? `${totalToolEvents} captured` : "No tool events";
    elements.opsAgentText.title = elements.opsAgentText.textContent;
    elements.opsPhaseText.textContent = totalLogEvents ? `${totalLogEvents} unique` : "No log events";
    elements.opsPhaseText.title = elements.opsPhaseText.textContent;
    elements.opsLatestText.textContent = latestUpdate;
    elements.opsLatestText.title = latestUpdate;
    elements.executionLogStatusText.textContent = state.run.logEntries.length
        ? `${Math.min(state.run.logEntries.length, EXECUTION_LOG_DISPLAY_LIMIT)} backend lines`
        : "Waiting for stream";

    renderLogEntries(
        elements.executionLog,
        state.run.logEntries.slice(-EXECUTION_LOG_DISPLAY_LIMIT),
        "Backend log lines will appear here while analysis is running.",
        { useDetail: true },
    );

    setElementLoadingState(elements.toolTraceList, state.isBusy && !feed.length, "Waiting traces");
    setElementLoadingState(elements.executionLog, state.isBusy && !state.run.logEntries.length, "Waiting backend");

    const flashLatestTrace = state.run.flashLatestTrace;
    preserveScrollPosition(elements.toolTraceList, () => {
        elements.toolTraceList.innerHTML = feed.length
            ? feed
                  .map((item) => {
                      const shouldFlash = flashLatestTrace && item.id === state.run.latestTraceId;
                      return `
                    <article class="tool-trace-item trace-tone-${escapeHtml(item.tone || "progress")} ${shouldFlash ? "tool-trace-new" : ""} detail-trigger"
                        tabindex="0"
                        role="button"
                        data-detail-trace-id="${escapeHtml(item.id || "")}"
                        data-detail-title="${escapeHtml(`${item.agent || "Agent"} - ${formatTracePhaseLabel(item.phase)}`)}"
                        data-detail-subtitle="${escapeHtml(item.title || "Trace detail")}"
                        data-detail-mode="markdown">
                        <div class="tool-trace-topline">
                            <strong>${escapeHtml(item.agent || item.title || "Live update")}</strong>
                            <span>${escapeHtml(item.timestamp || "")}</span>
                        </div>
                        <div class="tool-trace-meta">
                            <span class="trace-phase-badge">${escapeHtml(formatTracePhaseLabel(item.phase))}</span>
                            <span>${escapeHtml(item.title || "Live update")}</span>
                        </div>
                        <p>${escapeHtml(compactText(stripMarkdownToPlainText(item.previewContent || item.content || ""), 320))}</p>
                    </article>
                                `;
                                    })
                                    .join("")
                        : '<div class="tool-trace-empty">Agent tool calls and reasoning traces will appear here when the backend stream starts.</div>';
        });
    state.run.flashLatestTrace = false;
}

function renderResearchRoom() {
    const research = state.run.research || {};
    setCompactPreview(elements.bullResearchPanel, research.bull_history, "The Bull Researcher has not responded yet.");
    setCompactPreview(elements.bearResearchPanel, research.bear_history, "The Bear Researcher has not responded yet.");
    setCompactPreview(
        elements.researchManagerPanel,
        state.run.sections.investment_plan || research.judge_decision,
        "The Research Manager has not synthesized a plan yet.",
    );

    elements.researchStatusText.textContent = state.run.sections.investment_plan
        ? "Investment plan ready"
        : research.history
        ? "Debate in progress"
        : "Awaiting analyst reports";
}

function renderTraderDesk() {
    setCompactPreview(
        elements.traderPlanPanel,
        state.run.sections.trader_investment_plan,
        "The Trader has not produced a transaction proposal yet.",
    );
}

function renderRiskRoom() {
    const risk = state.run.risk || {};
    setCompactPreview(elements.aggressiveRiskPanel, risk.aggressive_history, "The Aggressive Analyst has not responded yet.");
    setCompactPreview(elements.conservativeRiskPanel, risk.conservative_history, "The Conservative Analyst has not responded yet.");
    setCompactPreview(elements.neutralRiskPanel, risk.neutral_history, "The Neutral Analyst has not responded yet.");
    elements.riskStatusText.textContent = state.run.sections.final_trade_decision
        ? "Risk loop completed"
        : risk.history
        ? "Risk debate live"
        : "Waiting for trader";
}

function renderFinalDecision() {
    const combinedDecision = buildFinalDecisionMarkdown();
    const fallback = state.run.sections.verification_report
        ? "Verification completed. Open the panel for the full report."
        : "The Portfolio Manager has not finalized a decision yet.";
    setCompactPreview(elements.portfolioDecisionPanel, combinedDecision, fallback, 220);
    const signal = state.run.complete?.signal || "No signal";
    const verificationVerdict = getVerificationVerdictText();
    elements.signalBadge.textContent = verificationVerdict ? `${signal} / ${verificationVerdict}` : signal;
}

function renderSmartNotes() {
    const notes = [];
    if (state.run.meta) {
        notes.push(`Market mode: ${state.run.meta.asset_type}`);
        notes.push(`Lookback window: ${state.run.meta.lookback_days} day(s)`);
        notes.push(`Depth preset: ${getAnalysisDepthLabel(state.run.meta)} (${state.run.meta.depth_rounds} rounds)`);
        notes.push(`Output language: ${state.run.meta.output_language}`);
    }
    if (state.run.status?.current_agent) {
        notes.push(`Current agent: ${state.run.status.current_agent}`);
    }
    if (state.run.latestReportTitle) {
        notes.push(`Latest updated panel: ${state.run.latestReportTitle}`);
    }
    for (const warning of state.run.warnings.slice(0, 3)) {
        notes.push(`Warning: ${warning}`);
    }

    if (notes.length === 0) {
        notes.push("Open Config to adjust symbol, date, language, analysts, and depth before running analysis.");
    }

    elements.smartNotes.innerHTML = notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");
}

function markdownCell(value = "") {
    return String(value ?? "")
        .replace(/\|/g, "\\|")
        .replace(/\r?\n/g, " ")
        .trim();
}

function formatEvidenceItemsMarkdown(items = []) {
    const evidenceItems = Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
    if (!evidenceItems.length) {
        return "";
    }
    const rows = [
        "| Agent | Direction | Confidence | Metric | Value | Timestamp | Source | Claim |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- |",
    ];
    evidenceItems.forEach((item) => {
        const confidence = Number(item.confidence ?? 0);
        rows.push(`| ${[
            item.agent_label || item.agent || "",
            item.direction || "",
            Number.isFinite(confidence) ? confidence.toFixed(2) : "",
            item.metric || "",
            item.value || "",
            item.timestamp || "",
            item.source || "",
            item.claim || "",
        ].map(markdownCell).join(" | ")} |`);
    });
    return rows.join("\n");
}

function formatEndpointSummariesMarkdown(items = []) {
    const summaries = Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
    if (!summaries.length) {
        return "";
    }
    return summaries.map((item) => {
        const metrics = item.key_metrics && typeof item.key_metrics === "object"
            ? Object.entries(item.key_metrics).map(([key, value]) => `- ${key}: ${value}`).join("\n")
            : "";
        const bullets = (item.summary_bullets || []).map((value) => `- ${value}`).join("\n");
        const caveats = (item.caveats || []).map((value) => `- ${value}`).join("\n");
        return [
            `### ${item.title || item.endpoint_name || "Endpoint"}`,
            `- **Direction:** ${item.direction || "-"}`,
            `- **Confidence:** ${item.confidence ?? "-"}`,
            `- **Source:** ${item.source || "-"}`,
            `- **Timestamp:** ${item.timestamp || "-"}`,
            metrics ? `\n**Key Metrics**\n${metrics}` : "",
            bullets ? `\n**Facts**\n${bullets}` : "",
            caveats ? `\n**Caveats**\n${caveats}` : "",
        ].filter(Boolean).join("\n");
    }).join("\n\n");
}

function formatStructuredPayloadMarkdown(payload = {}, title = "Structured Payload") {
    if (!payload || typeof payload !== "object" || Array.isArray(payload) || Object.keys(payload).length === 0) {
        return "";
    }
    const rows = [
        "| Field | Value |",
        "| --- | --- |",
        ...Object.entries(payload).map(([key, value]) => {
            const rendered = typeof value === "object" && value !== null
                ? JSON.stringify(value, null, 2)
                : value;
            return `| ${markdownCell(key)} | ${markdownCell(rendered)} |`;
        }),
    ];
    return [`### ${title}`, rows.join("\n")].join("\n\n");
}

function formatResearchDebateMarkdown(research = {}) {
    return [
        research.bull_history ? `## Bull Researcher\n\n${research.bull_history}` : "",
        research.bear_history ? `## Bear Researcher\n\n${research.bear_history}` : "",
        research.history ? `## Debate\n\n${research.history}` : "",
    ].filter(Boolean).join("\n\n");
}

function formatRiskDebateMarkdown(risk = {}) {
    return [
        risk.aggressive_history ? `## Aggressive Analyst\n\n${risk.aggressive_history}` : "",
        risk.neutral_history ? `## Neutral Analyst\n\n${risk.neutral_history}` : "",
        risk.conservative_history ? `## Conservative Analyst\n\n${risk.conservative_history}` : "",
        risk.history ? `## Debate\n\n${risk.history}` : "",
    ].filter(Boolean).join("\n\n");
}

function getDetailContent(detail) {
    const research = state.run.research || {};
    const risk = state.run.risk || {};

    if (detail?.type === "report") {
        return {
            content: state.run.sections[detail.section] || "",
            fallback: "This report has no data yet. It will update when the agent completes.",
        };
    }

    if (detail?.type === "trace") {
        const entry = getTraceEntryById(detail.traceId);
        const hasToolPayload = Boolean(entry?.toolCallContent || entry?.toolResultContent);
        return {
            content: formatTraceDetailMarkdown(entry),
            fallback: "This trace is no longer available in the live feed.",
            toolResult: hasToolPayload
                ? entry?.toolResultData || { answer: "", sections: [], relatedSearches: [] }
                : null,
            traceEntry: entry || null,
        };
    }

    if (detail?.type === "history-section") {
        const section = getHistorySectionMeta(detail.sectionKey);
        const active = state.history.active || {};
        const content = active.sectionMarkdown?.[detail.sectionKey] || "";
        const loading = Array.isArray(active.sectionLoadingKeys) && active.sectionLoadingKeys.includes(detail.sectionKey);
        return {
            content,
            fallback: loading
                ? "Loading this saved markdown section..."
                : section
                ? "No markdown was saved for this section."
                : "This saved history section is no longer available.",
        };
    }

    if (detail?.type === "source-artifact" || detail?.type === "history-final-decision") {
        return {
            content: detail.content || "",
            fallback: detail.fallback || "No saved markdown was returned.",
        };
    }

    switch (detail?.key) {
        case "endpointSummaries":
            return {
                content: formatEndpointSummariesMarkdown(state.run.endpointSummaries),
                fallback: "Endpoint summaries are not available for this run yet.",
            };
        case "liveCcxtData":
            return getSourceArtifactDetailContent("ccxt", "CCXT market data tool results have not appeared yet.");
        case "liveCoinGlassData":
            return getSourceArtifactDetailContent("coinglass", "CoinGlass endpoint results are not available for this run yet.");
        case "liveNewsData":
            return getSourceArtifactDetailContent("news", "News source results have not appeared yet.");
        case "liveSocialData":
            return getSourceArtifactDetailContent("social", "Social or web source results have not appeared yet.");
        case "liveFlowData":
            return getSourceArtifactDetailContent("flow", "Flow source results have not appeared yet.");
        case "evidenceExtractor":
        case "evidenceLedger":
            return {
                content: state.run.sections.structured_evidence || formatEvidenceItemsMarkdown(state.run.evidenceItems),
                fallback: "Structured evidence is not available for this run yet.",
            };
        case "researchDebate":
            return {
                content: formatResearchDebateMarkdown(research),
                fallback: "The research debate has not produced content yet.",
            };
        case "riskDebate":
            return {
                content: formatRiskDebateMarkdown(risk),
                fallback: "The risk debate has not produced content yet.",
            };
        case "investmentExtractor":
            return {
                content: formatStructuredPayloadMarkdown(state.run.structured?.investment_plan, "Investment Plan Extractor"),
                fallback: "Structured investment plan is not available for this run yet.",
            };
        case "traderExtractor":
            return {
                content: formatStructuredPayloadMarkdown(state.run.structured?.trader_investment_plan, "Trader Plan Extractor"),
                fallback: "Structured trader plan is not available for this run yet.",
            };
        case "decisionExtractor":
            return {
                content: formatStructuredPayloadMarkdown(state.run.structured?.final_trade_decision, "Decision Extractor"),
                fallback: "Structured final decision is not available for this run yet.",
            };
        case "verifierStructured":
            return {
                content: formatStructuredPayloadMarkdown(state.run.structured?.verification_report, "Verifier Payload"),
                fallback: "Structured verification is not available for this run yet.",
            };
        case "bullResearch":
            return { content: research.bull_history || "", fallback: "The Bull Researcher has not responded yet." };
        case "bearResearch":
            return { content: research.bear_history || "", fallback: "The Bear Researcher has not responded yet." };
        case "researchManager":
            return {
                content: state.run.sections.investment_plan || research.judge_decision || "",
                fallback: "The Research Manager has not synthesized a plan yet.",
            };
        case "traderPlan":
            return { content: state.run.sections.trader_investment_plan || "", fallback: "The Trader has not produced a transaction proposal yet." };
        case "aggressiveRisk":
            return { content: risk.aggressive_history || "", fallback: "The Aggressive Analyst has not responded yet." };
        case "conservativeRisk":
            return { content: risk.conservative_history || "", fallback: "The Conservative Analyst has not responded yet." };
        case "neutralRisk":
            return { content: risk.neutral_history || "", fallback: "The Neutral Analyst has not responded yet." };
        case "verifierReport":
            return {
                content: state.run.sections.verification_report || "",
                fallback: "The Verifier has not completed the post-decision audit yet.",
            };
        case "portfolioDecision":
            return {
                content: buildFinalDecisionMarkdown(),
                fallback: "The Portfolio Manager has not finalized a decision yet.",
            };
        case "backendLog":
            return { content: formatBackendLogMarkdown(), fallback: "No backend log lines yet." };
        default:
            return { content: "", fallback: "No data yet." };
    }
}

function formatTraceDetailMarkdown(entry) {
    if (!entry) {
        return "";
    }

    if (entry.toolCallContent || entry.toolResultContent) {
        const toolResultBody = entry.toolResultData
            ? renderStructuredToolResultToMarkdown(entry.toolResultData)
            : formatRawToolResultMarkdown(entry.toolResultContent || "");
        return [
            `**Agent:** ${entry.agent || "Agent"}`,
            `**Phase:** ${formatTracePhaseLabel(entry.phase)}`,
            `**Time:** ${entry.timestamp || "-"}`,
            entry.toolCallContent ? `**Tool call**\n\n\`\`\`text\n${entry.toolCallContent}\n\`\`\`` : "",
            toolResultBody ? `**Tool result**\n\n${toolResultBody}` : "",
        ]
            .filter(Boolean)
            .join("\n\n");
    }

    const content = formatTraceContentForDisplay(entry.phase, entry.content || "");
    const looksStructured = entry.phase !== "tool_result" && (/^[\[{]/.test(content) || /^analysis\s/.test(content));
    const hasLink = /https?:\/\//.test(content);
    const body = looksStructured && !hasLink ? `\`\`\`text\n${content}\n\`\`\`` : content;
    return [
        `**Agent:** ${entry.agent || "Agent"}`,
        `**Phase:** ${formatTracePhaseLabel(entry.phase)}`,
        `**Time:** ${entry.timestamp || "-"}`,
        body,
    ]
        .filter(Boolean)
        .join("\n\n");
}

function renderToolResultCardMarkup(item) {
    const titleMarkup = item.link
        ? `<a class="tool-result-card-title" href="${escapeHtml(item.link)}" target="_blank" rel="noreferrer noopener">${escapeHtml(item.title)}</a>`
        : `<span class="tool-result-card-title">${escapeHtml(item.title)}</span>`;

    return `
        <article class="tool-result-card">
            <div class="tool-result-card-topline">
                ${titleMarkup}
                ${item.date ? `<span class="tool-result-card-date">${escapeHtml(item.date)}</span>` : ""}
            </div>
            ${item.snippet ? `<p class="tool-result-card-snippet">${escapeHtml(item.snippet)}</p>` : ""}
            <div class="tool-result-card-meta">
                <span>${escapeHtml(item.source || "Search result")}</span>
                ${item.link ? `<a class="tool-result-card-open" href="${escapeHtml(item.link)}" target="_blank" rel="noreferrer noopener">Open source</a>` : ""}
            </div>
        </article>
    `;
}

function renderToolResultDetailMarkup(toolResult, entry) {
    const toolCallContent = String(entry?.toolCallContent || "").trim();
    const rawResultContent = String(entry?.toolResultContent || entry?.content || "").trim();
    const rawResultMarkdown = formatRawToolResultMarkdown(rawResultContent);
    const hasStructuredContent = Boolean(toolResult.answer || toolResult.sections.length || toolResult.relatedSearches.length);
    const metaItems = [
        entry?.agent ? `Agent: ${entry.agent}` : "",
        entry?.title ? `Tool: ${entry.title}` : "",
        entry?.timestamp ? `Time: ${entry.timestamp}` : "",
    ].filter(Boolean);

    return `
        ${metaItems.length ? `<div class="tool-result-meta-strip">${metaItems.map((item) => `<span class="tool-result-meta-pill">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
        ${toolCallContent
            ? `
                <section class="tool-result-section">
                    <div class="tool-result-section-head">
                        <h3>Tool call</h3>
                        <span>Input</span>
                    </div>
                    <div class="tool-result-summary markdown-preview">${renderMarkdown(`\`\`\`text\n${toolCallContent}\n\`\`\``, "")}</div>
                </section>
            `
            : ""}
        ${toolResult.answer ? `<section class="tool-result-summary markdown-preview">${renderMarkdown(toolResult.answer, "")}</section>` : ""}
        ${toolResult.sections
            .map(
                (section) => `
                    <section class="tool-result-section">
                        <div class="tool-result-section-head">
                            <h3>${escapeHtml(section.title)}</h3>
                            <span>${escapeHtml(String(section.items.length))} items</span>
                        </div>
                        <div class="tool-result-card-list">
                            ${section.items.map((item) => renderToolResultCardMarkup(item)).join("")}
                        </div>
                    </section>
                `,
            )
            .join("")}
        ${toolResult.relatedSearches.length
            ? `
                <section class="tool-result-section">
                    <div class="tool-result-section-head">
                        <h3>Related searches</h3>
                        <span>${escapeHtml(String(toolResult.relatedSearches.length))} items</span>
                    </div>
                    <div class="tool-result-related-list">
                        ${toolResult.relatedSearches.map((item) => `<span class="tool-result-chip">${escapeHtml(item)}</span>`).join("")}
                    </div>
                </section>
            `
            : ""}
        ${!hasStructuredContent && rawResultContent
            ? `
                <section class="tool-result-section">
                    <div class="tool-result-section-head">
                        <h3>Tool result</h3>
                        <span>Raw output</span>
                    </div>
                    <div class="tool-result-summary markdown-preview">${renderMarkdown(rawResultMarkdown, "")}</div>
                </section>
            `
            : ""}
    `;
}

function setToolResultPreview(element, toolResult, entry, fallback) {
    const hasStructuredContent = Boolean(toolResult && (toolResult.answer || toolResult.sections.length || toolResult.relatedSearches.length));
    const hasRawContent = Boolean(entry?.toolCallContent || entry?.toolResultContent || entry?.content);
    const hasContent = Boolean(hasStructuredContent || hasRawContent);
    element.innerHTML = hasContent
        ? renderToolResultDetailMarkup(toolResult || { answer: "", sections: [], relatedSearches: [] }, entry)
        : `<div class="tool-result-empty">${escapeHtml(fallback)}</div>`;
    element.classList.toggle("is-empty", !hasContent);
}

function formatBackendLogMarkdown(limit = EXECUTION_LOG_DISPLAY_LIMIT) {
    const entries = state.run.logEntries.slice(-limit);
    if (!entries.length) {
        return "";
    }

    return entries
        .map(
            (entry) => {
                const detail = entry.detail || entry.summary || "";
                return `### ${entry.label}\n- **Time:** ${entry.timestamp}\n\n\`\`\`text\n${detail}\n\`\`\``;
            },
        )
        .join("\n\n");
}

function renderActiveDetail() {
    const detail = state.activeDetail;
    if (!detail || elements.detailModal.classList.contains("hidden")) {
        return;
    }

    const directMetaTypes = ["report", "trace", "history-section", "source-artifact", "history-final-decision"];
    const meta = directMetaTypes.includes(detail.type) ? detail : DETAIL_PANEL_META[detail.key] || {};
    const detailContent = getDetailContent(detail);
    const { content, fallback, toolResult, traceEntry } = detailContent;
    const mode = detailContent.mode || (toolResult ? "tool-result" : detail.mode || meta.mode || "markdown");
    elements.detailTitle.textContent = meta.title || "Panel Detail";
    elements.detailSubtitle.textContent = meta.subtitle || "Analysis detail";
    elements.detailBody.classList.toggle("plain-log", mode === "text");
    elements.detailBody.classList.toggle("markdown-preview", mode === "markdown");
    elements.detailBody.classList.toggle("tool-result-preview", mode === "tool-result");
    elements.detailBody.classList.toggle("source-table-preview", mode === "source-table");

    if (mode === "text") {
        elements.detailBody.textContent = content || fallback;
    } else if (mode === "source-table") {
        setSourceArtifactTablePreview(elements.detailBody, detailContent.rows || [], fallback, detailContent.groupKey || "");
    } else if (mode === "tool-result") {
        setToolResultPreview(elements.detailBody, toolResult, traceEntry, fallback);
    } else {
        setMarkdownPreview(elements.detailBody, content, fallback);
    }
}

function openDetailModal(detail) {
    state.activeDetail = detail;
    showModal(elements.detailModal);
    renderActiveDetail();
}

async function openSavedSourceArtifactDetail(runId = "", sectionKey = "") {
    const safeRunId = String(runId || "").trim();
    const safeSectionKey = String(sectionKey || "").trim();
    if (!safeRunId || !safeSectionKey) {
        return;
    }
    openDetailModal({
        type: "source-artifact",
        title: "Source Artifact",
        subtitle: "Loading saved source detail",
        content: "",
        fallback: "Loading saved source artifact...",
        mode: "markdown",
    });
    const response = await apiFetch(`/api/history/${encodeURIComponent(safeRunId)}/artifacts/${encodeURIComponent(safeSectionKey)}`, {
        headers: getAuthHeaders(),
        cache: "no-store",
    });
    if (!response.ok) {
        throw new Error(await readResponseError(response));
    }
    const payload = await response.json();
    const artifact = payload.artifact || {};
    openDetailModal({
        type: "source-artifact",
        title: artifact.title || "Source Artifact",
        subtitle: [artifact.agent, artifact.source_kind || artifact.flow_group].filter(Boolean).join(" - ") || "Saved source detail",
        content: artifact.markdown || "",
        fallback: "This artifact has no markdown content.",
        mode: "markdown",
    });
}

function closeDetailModal() {
    hideModal(elements.detailModal);
    state.activeDetail = null;
}

function renderPageShell() {
    const pagePanels = {
        agent: elements.agentPage,
        history: elements.historyPage,
        chart: elements.chartPage,
        admin: elements.adminPage,
        chat: elements.chatPage,
    };
    Object.entries(pagePanels).forEach(([page, panel]) => {
        if (panel instanceof HTMLElement) {
            panel.classList.toggle("hidden", page !== state.page);
        }
    });
    [elements.agentPageButton, elements.historyPageButton, elements.chartPageButton, elements.adminPageButton, elements.chatPageButton].forEach((button) => {
        if (!(button instanceof HTMLElement)) {
            return;
        }
        if (button.dataset.page === "admin" || button.dataset.page === "chat") {
            button.classList.toggle("hidden", !state.auth.isAdmin);
        }
        const isActive = button.dataset.page === state.page;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-current", isActive ? "page" : "false");
    });
}

