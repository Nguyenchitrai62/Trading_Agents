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

function getLiveFlowBlockError(blockKey = "") {
    return state.run.blockErrors?.[blockKey] || "";
}

function isLiveFlowBlockLockedComplete(blockKey = "") {
    return Boolean(blockKey && state.run.flowCompletedBlocks?.has?.(blockKey));
}

function markLiveFlowBlockComplete(blockKey = "") {
    if (!blockKey) {
        return;
    }
    state.run.flowCompletedBlocks = state.run.flowCompletedBlocks || new Set();
    state.run.flowCompletedBlocks.add(blockKey);
}

function resolveLiveFlowNodeStatus(node = {}) {
    const fallbackStatus = node.ready ? "completed" : "pending";
    const rawStatus = String(node.status || fallbackStatus);
    if (rawStatus !== "error" && isLiveFlowBlockLockedComplete(node.blockKey)) {
        return "completed";
    }
    return rawStatus;
}

function getLiveEvidenceCount() {
    const completeCount = state.run.complete?.evidence_count;
    if (completeCount !== undefined && completeCount !== null) {
        return Number(completeCount) || 0;
    }
    return Number(state.run.evidenceCount || state.run.evidenceItems?.length || 0);
}

const SOURCE_ARTIFACT_GROUPS = {
    ccxt: {
        flowGroup: "ccxt_market_data",
        title: "CCXT Market Data",
        summaryTitle: "Market Summary",
        summaryFilter: (item) => ["ccxt", "market"].includes(getEndpointSummaryBucket(item)),
    },
    coinglass: {
        flowGroup: "coinglass_data",
        title: "CoinGlass Data",
        summaryTitle: "Derivatives / Flow Summary",
        summaryFilter: (item) => getEndpointSummaryBucket(item) === "coinglass",
    },
    news: {
        flowGroup: "news_data",
        title: "News Data",
        summaryTitle: "News Summary",
        summaryFilter: (item) => getEndpointSummaryBucket(item) === "news",
    },
    social: {
        flowGroup: "social_web_data",
        title: "Social / Web Data",
        summaryTitle: "Social Summary",
        summaryFilter: (item) => getEndpointSummaryBucket(item) === "social",
    },
    flow: {
        flowGroup: "flow_data",
        title: "On-chain Data",
        summaryTitle: "Flow Summary",
        summaryFilter: (item) => getEndpointSummaryBucket(item) === "flow",
    },
};

function getEndpointSummaryBucket(item = {}) {
    const text = [
        item.package,
        item.package_label,
        item.endpoint_name,
        item.title,
        item.source,
        item.source_type,
    ].map((value) => String(value || "").toLowerCase()).join(" ");
    if (text.includes("coinglass") || text.includes("derivative") || text.includes("funding") || text.includes("liquidation") || text.includes("open interest")) {
        return "coinglass";
    }
    if (text.includes("news") || text.includes("article") || text.includes("global")) {
        return "news";
    }
    if (text.includes("social") || text.includes("reddit") || text.includes("stocktwits") || text.includes("web")) {
        return "social";
    }
    if (text.includes("flow") || text.includes("on-chain") || text.includes("liquidity") || text.includes("stablecoin") || text.includes("tvl")) {
        return "flow";
    }
    if (text.includes("ccxt") || text.includes("ohlcv") || text.includes("indicator") || text.includes("market")) {
        return "ccxt";
    }
    return "";
}

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

function isLiveSourceTraceEntryForGroup(entry = {}, groupKey = "", phases = ["tool_result", "tool_trace"]) {
    if (!entry || !phases.includes(entry.phase)) {
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
}

function getLiveSourceTraceEntries(groupKey = "") {
    const entries = Array.isArray(state.run.traceFeed) ? state.run.traceFeed : [];
    return entries.filter((entry) => isLiveSourceTraceEntryForGroup(entry, groupKey, ["tool_result", "tool_trace"]));
}

function getLiveSourcePendingTraceEntries(groupKey = "") {
    const entries = Array.isArray(state.run.traceFeed) ? state.run.traceFeed : [];
    return entries.filter((entry) => isLiveSourceTraceEntryForGroup(entry, groupKey, ["tool_call"]));
}

function getEndpointSummariesForGroup(groupKey = "") {
    const config = SOURCE_ARTIFACT_GROUPS[groupKey];
    const items = Array.isArray(state.run.endpointSummaries) ? state.run.endpointSummaries : [];
    if (!config || typeof config.summaryFilter !== "function") {
        return [];
    }
    return items.filter(config.summaryFilter);
}

function getLiveSourceSummaryMarkdown(groupKey = "") {
    requestSavedSourceArtifacts(groupKey);
    const groupedSummaries = getEndpointSummariesForGroup(groupKey);
    if (groupedSummaries.length) {
        return formatEndpointSummariesMarkdown(groupedSummaries);
    }
    const config = SOURCE_ARTIFACT_GROUPS[groupKey] || {};
    const entries = getLiveSourceTraceEntries(groupKey);
    const savedArtifacts = (state.run.sourceArtifactLists?.[groupKey] || []).filter((item) => item.source_kind !== "flow_block");
    if (!entries.length && savedArtifacts.length) {
        const rows = [
            `# ${config.summaryTitle || config.title || "Source Summary"}`,
            "",
            "| Source | Kind | Summary |",
            "| --- | --- | --- |",
        ];
        savedArtifacts.slice(0, 24).forEach((item) => {
            rows.push(`| ${markdownCell(item.title || item.source_key || "")} | ${markdownCell(item.source_kind || item.artifact_type || "")} | ${markdownCell(item.summary || item.source_key || "")} |`);
        });
        return rows.join("\n");
    }
    if (!entries.length) {
        return "";
    }
    const lines = [`# ${config.summaryTitle || config.title || "Source Summary"}`, ""];
    entries.slice(-8).forEach((entry) => {
        const plain = compactText(stripMarkdownToPlainText(entry.toolResultContent || entry.content || ""), 240);
        if (!plain) {
            return;
        }
        lines.push(`- **${entry.title || "Tool"}:** ${plain}`);
    });
    return lines.length > 2 ? lines.join("\n") : "";
}

function getLiveSourceSummaryReady(groupKey = "") {
    return Boolean(
        getEndpointSummariesForGroup(groupKey).length
        || getLiveSourceTraceEntries(groupKey).length
        || (state.run.sourceArtifactLists?.[groupKey] || []).some((item) => item.source_kind !== "flow_block")
    );
}

function buildLiveSourceDataNode(groupKey, title, ready, status, tone, detailKey, blockKey) {
    const error = getLiveFlowBlockError(blockKey);
    const lockedComplete = isLiveFlowBlockLockedComplete(blockKey);
    const finalReady = Boolean(ready || lockedComplete);
    const finalStatus = error ? "error" : lockedComplete ? "completed" : status;
    return {
        blockKey,
        title,
        ready: finalReady,
        status: finalStatus,
        tone,
        detail: { key: detailKey },
        error,
    };
}

function buildLiveSourceSummaryNode(groupKey, title, ready, status, blockKey) {
    const error = getLiveFlowBlockError(blockKey);
    const lockedComplete = isLiveFlowBlockLockedComplete(blockKey);
    const finalReady = Boolean(ready || lockedComplete);
    const finalStatus = error ? "error" : lockedComplete ? "completed" : status;
    return {
        blockKey,
        title,
        ready: finalReady,
        status: finalStatus,
        tone: "evidence",
        detail: { key: `live${groupKey[0].toUpperCase()}${groupKey.slice(1)}Summary` },
        error,
    };
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
    })).filter((item) => item.sourceKind !== "flow_block");
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

function setDetailPayload(detail, detailContent) {
    if (!detail || !detailContent || detail.payload !== undefined) {
        return;
    }
    if (detailContent.payload !== undefined) {
        detail.payload = detailContent.payload;
        return;
    }
    if (detail.type === "report") {
        detail.payload = {
            section: detail.section || "",
            title: detail.title || "",
            markdown: state.run.sections?.[detail.section] || "",
        };
        return;
    }
    if (detail.key) {
        detail.payload = getLiveFlowBlockPayload(detail.key, DETAIL_PANEL_META[detail.key]?.title || detail.key, "pending", { key: detail.key }, detailContent.content || detailContent.fallback || "");
    }
}

function getSourceArtifactDetailContent(groupKey = "", fallback = "") {
    const rows = buildSourceArtifactRows(groupKey);
    return {
        mode: "source-table",
        rows,
        groupKey,
        payload: getSourceGroupArtifactRows(groupKey),
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

function buildLiveFlowNodes() {
    const selectedAnalysts = new Set(state.run.meta?.selected_analysts || ["market", "social", "news", "fundamentals"]);
    const hasSection = (key) => Boolean(String(state.run.sections?.[key] || "").trim());
    const flowSectionCompleted = (key) => Boolean(state.run.flowCompletedSections?.has?.(key) || state.run.complete);
    const hasStructuredPayload = (key) => {
        const payload = state.run.structured?.[key];
        return Boolean(payload && typeof payload === "object" && Object.keys(payload).length);
    };
    const currentAgent = String(state.run.status?.current_agent || "");
    const groupStatus = (groupKey, label) => {
        const item = (state.run.status?.groups?.[groupKey] || []).find((entry) => entry.label === label);
        return item?.status || "";
    };
    const normalizeStatus = (value) => String(value || "").trim();
    const isCurrent = (label) => Boolean(label && currentAgent === label);
    const statusFor = (ready, active = false, prerequisiteReady = true) => {
        if (state.run.complete && ready) {
            return "completed";
        }
        if (ready) {
            return "completed";
        }
        if (active && prerequisiteReady) {
            return "in_progress";
        }
        return "pending";
    };
    const analystSpecs = [
        ["market", "market_report", "Market Analyst", "market_analyst"],
        ["social", "sentiment_report", "Social Analyst", "social_analyst"],
        ["news", "news_report", "News Analyst", "news_analyst"],
        ["fundamentals", "flow_report", "Flow Analyst", "flow_analyst"],
    ];
    const selectedAnalystSpecs = analystSpecs.filter(([analystKey]) => selectedAnalysts.has(analystKey));
    const analystSourceGroups = {
        market: ["ccxt"],
        social: ["social"],
        news: ["news"],
        fundamentals: ["coinglass", "flow"],
    };
    const analystReportDone = (analystKey) => {
        const spec = analystSpecs.find(([key]) => key === analystKey);
        return spec ? hasSection(spec[1]) && flowSectionCompleted(spec[1]) : false;
    };
    const analystActive = (analystKey, title) => {
        if (!selectedAnalysts.has(analystKey) || analystReportDone(analystKey)) {
            return false;
        }
        const backendStatus = normalizeStatus(groupStatus("analysts", title));
        return backendStatus === "in_progress" || isCurrent(title) || currentAgent === "Analyst Team" || currentAgent === "Parallel Analyst Team";
    };
    const selectedAnalystReportsComplete = selectedAnalystSpecs.length
        ? selectedAnalystSpecs.every(([analystKey]) => analystReportDone(analystKey))
        : false;
    const endpointReady = Boolean(state.run.endpointSummaries?.length);
    const savedGroupReady = (groupKey) => {
        const flowGroup = SOURCE_ARTIFACT_GROUPS[groupKey]?.flowGroup || "";
        return Number(state.run.sourceArtifactGroups?.[flowGroup] || 0) > 0;
    };
    const sourceGroupOwnerReportsDone = (groupKey) => Object.entries(analystSourceGroups)
        .some(([analystKey, groupKeys]) => selectedAnalysts.has(analystKey) && groupKeys.includes(groupKey) && analystReportDone(analystKey));
    const sourceGroupSelected = (groupKey) => Object.entries(analystSourceGroups)
        .some(([analystKey, groupKeys]) => selectedAnalysts.has(analystKey) && groupKeys.includes(groupKey));
    const sourceDoneForGroup = (groupKey) => {
        const resultCount = getLiveSourceTraceEntries(groupKey).length;
        const pendingCount = getLiveSourcePendingTraceEntries(groupKey).length;
        const hasResult = resultCount > 0 || savedGroupReady(groupKey) || (groupKey === "coinglass" && endpointReady);
        const hasPending = pendingCount > 0;
        const lockedComplete = isLiveFlowBlockLockedComplete(`${groupKey}_data`) || isLiveFlowBlockLockedComplete(`${groupKey}_summary`);
        if (sourceGroupSelected(groupKey)) {
            return Boolean(sourceGroupOwnerReportsDone(groupKey) || lockedComplete || (hasResult && !hasPending));
        }
        return Boolean(hasResult && !hasPending);
    };
    const sourceActiveForGroup = (groupKey, analystKey, title) => Boolean(
        !sourceDoneForGroup(groupKey)
        && (
            getLiveSourcePendingTraceEntries(groupKey).length
            || getLiveSourceTraceEntries(groupKey).length
            || savedGroupReady(groupKey)
            || (groupKey === "coinglass" && endpointReady)
            || (analystKey && title && analystActive(analystKey, title))
        )
    );
    const ccxtReady = sourceDoneForGroup("ccxt");
    const coinglassReady = sourceDoneForGroup("coinglass");
    const newsSourceReady = sourceDoneForGroup("news");
    const socialSourceReady = sourceDoneForGroup("social");
    const flowSourceReady = sourceDoneForGroup("flow");
    const marketSummaryReady = getLiveSourceSummaryReady("ccxt");
    const coinglassSummaryReady = getLiveSourceSummaryReady("coinglass");
    const newsSummaryReady = getLiveSourceSummaryReady("news");
    const socialSummaryReady = getLiveSourceSummaryReady("social");
    const flowSummaryReady = getLiveSourceSummaryReady("flow");
    const sourceVisible = (analystKey, ready) => Boolean(ready || selectedAnalysts.has(analystKey) || state.isBusy || state.run.complete);
    const sourceStatus = (groupKey, analystKey, title, rawReady) => {
        const selected = selectedAnalysts.has(analystKey);
        const active = selected && sourceActiveForGroup(groupKey, analystKey, title);
        return statusFor(Boolean(rawReady), active, true);
    };
    const sourceSummaryStatus = (groupKey, analystKey, title, sourceReady) => {
        if (sourceReady) {
            return "completed";
        }
        return sourceStatus(groupKey, analystKey, title, false);
    };
    const analystInputsReady = (analystKey) => (analystSourceGroups[analystKey] || [])
        .every((groupKey) => sourceDoneForGroup(groupKey));
    const analystNode = ([analystKey, sectionKey, title, blockKey]) => {
        const reportDone = hasSection(sectionKey) && flowSectionCompleted(sectionKey);
        const backendStatus = normalizeStatus(groupStatus("analysts", title));
        const inputsReady = analystInputsReady(analystKey);
        const active = inputsReady && (backendStatus === "in_progress" || analystActive(analystKey, title));
        return {
            blockKey,
            title,
            ready: reportDone,
            status: getLiveFlowBlockError(blockKey) ? "error" : statusFor(reportDone, active, selectedAnalysts.has(analystKey) && inputsReady),
            visible: selectedAnalysts.has(analystKey) || reportDone,
            tone: "signal",
            detail: { type: "report", section: sectionKey, title, subtitle: "Analyst report" },
            error: getLiveFlowBlockError(blockKey),
        };
    };
    const depthRounds = Math.max(1, Number(state.run.meta?.depth_rounds || 1));
    const researchCount = Number(state.run.research?.count || 0);
    const expectedResearchTurns = depthRounds * 2;
    const researchManagerBackendStatus = normalizeStatus(groupStatus("research", "Research Manager"));
    const researchDebateReady = (hasSection("investment_plan") && flowSectionCompleted("investment_plan"))
        || researchCount >= expectedResearchTurns
        || researchManagerBackendStatus === "completed";
    const researchCanRun = selectedAnalystReportsComplete;
    const researchNodeStatus = (blockKey, label, hasContent) => {
        const backendStatus = normalizeStatus(groupStatus("research", label));
        const active = backendStatus === "in_progress" || isCurrent(label);
        const complete = Boolean(researchDebateReady && hasContent);
        return getLiveFlowBlockError(blockKey) ? "error" : statusFor(complete, active, researchCanRun);
    };
    const traderBackendStatus = normalizeStatus(groupStatus("trading", "Trader"));
    const investmentPlanReady = hasSection("investment_plan") && flowSectionCompleted("investment_plan");
    const investmentExtractorReady = hasStructuredPayload("investment_plan") && flowSectionCompleted("investment_plan_structured");
    const traderReady = hasSection("trader_investment_plan") && flowSectionCompleted("trader_investment_plan");
    const traderExtractorReady = hasStructuredPayload("trader_investment_plan") && flowSectionCompleted("trader_investment_plan_structured");
    const riskCount = Number(state.run.risk?.count || 0);
    const expectedRiskTurns = depthRounds * 3;
    const portfolioBackendStatus = normalizeStatus(groupStatus("portfolio", "Portfolio Manager"));
    const riskDebateReady = (hasSection("final_trade_decision") && flowSectionCompleted("final_trade_decision"))
        || riskCount >= expectedRiskTurns
        || portfolioBackendStatus === "completed";
    const riskCanRun = traderExtractorReady;
    const riskNodeStatus = (blockKey, label, hasContent) => {
        const backendStatus = normalizeStatus(groupStatus("risk", label));
        const active = backendStatus === "in_progress" || isCurrent(label);
        const complete = Boolean(riskDebateReady && hasContent);
        return getLiveFlowBlockError(blockKey) ? "error" : statusFor(complete, active, riskCanRun);
    };
    const finalDecisionReady = hasSection("final_trade_decision") && flowSectionCompleted("final_trade_decision");
    const decisionExtractorReady = hasStructuredPayload("final_trade_decision") && flowSectionCompleted("final_trade_decision_structured");
    const verifierReady = hasSection("verification_report") && flowSectionCompleted("verification_report");
    const persistenceReady = Boolean(state.run.complete);

    return {
        sourceNodes: [
            {
                visible: sourceVisible("market", ccxtReady),
                data: buildLiveSourceDataNode("ccxt", "CCXT Market Data", ccxtReady, sourceStatus("ccxt", "market", "Market Analyst", ccxtReady), "signal", "liveCcxtData", "ccxt_data"),
                summary: buildLiveSourceSummaryNode("ccxt", "Market Summary", marketSummaryReady && ccxtReady, sourceSummaryStatus("ccxt", "market", "Market Analyst", ccxtReady), "market_summary"),
            },
            {
                visible: sourceVisible("fundamentals", coinglassReady),
                data: buildLiveSourceDataNode("coinglass", "CoinGlass Data", coinglassReady, sourceStatus("coinglass", "fundamentals", "Flow Analyst", coinglassReady), "evidence", "liveCoinGlassData", "coinglass_data"),
                summary: buildLiveSourceSummaryNode("coinglass", "Derivatives / Flow Summary", coinglassSummaryReady && coinglassReady, sourceSummaryStatus("coinglass", "fundamentals", "Flow Analyst", coinglassReady), "coinglass_summary"),
            },
            {
                visible: sourceVisible("news", newsSourceReady),
                data: buildLiveSourceDataNode("news", "News Data", newsSourceReady, sourceStatus("news", "news", "News Analyst", newsSourceReady), "signal", "liveNewsData", "news_data"),
                summary: buildLiveSourceSummaryNode("news", "News Summary", newsSummaryReady && newsSourceReady, sourceSummaryStatus("news", "news", "News Analyst", newsSourceReady), "news_summary"),
            },
            {
                visible: sourceVisible("social", socialSourceReady),
                data: buildLiveSourceDataNode("social", "Social / Web Data", socialSourceReady, sourceStatus("social", "social", "Social Analyst", socialSourceReady), "signal", "liveSocialData", "social_data"),
                summary: buildLiveSourceSummaryNode("social", "Social Summary", socialSummaryReady && socialSourceReady, sourceSummaryStatus("social", "social", "Social Analyst", socialSourceReady), "social_summary"),
            },
            {
                visible: sourceVisible("fundamentals", flowSourceReady),
                data: buildLiveSourceDataNode("flow", "On-chain / Liquidity Data", flowSourceReady, sourceStatus("flow", "fundamentals", "Flow Analyst", flowSourceReady), "signal", "liveFlowData", "flow_data"),
                summary: buildLiveSourceSummaryNode("flow", "Flow Summary", flowSummaryReady && flowSourceReady, sourceSummaryStatus("flow", "fundamentals", "Flow Analyst", flowSourceReady), "flow_summary"),
            },
        ],
        evidenceExtractor: { blockKey: "evidence_extractor", title: "Evidence Extractor", ready: selectedAnalystReportsComplete, status: getLiveFlowBlockError("evidence_extractor") ? "error" : statusFor(selectedAnalystReportsComplete, false), tone: "evidence", detail: { key: "evidenceExtractor" }, error: getLiveFlowBlockError("evidence_extractor") },
        analystNodes: analystSpecs.map(analystNode),
        evidenceLedger: { blockKey: "evidence_ledger", title: "Evidence Ledger", ready: selectedAnalystReportsComplete, status: getLiveFlowBlockError("evidence_ledger") ? "error" : statusFor(selectedAnalystReportsComplete, false), tone: "evidence", detail: { key: "evidenceLedger" }, error: getLiveFlowBlockError("evidence_ledger") },
        bullResearcher: { blockKey: "bull_researcher", title: "Bull Researcher", ready: Boolean(researchDebateReady && state.run.research?.bull_history), status: researchNodeStatus("bull_researcher", "Bull Researcher", state.run.research?.bull_history), tone: "bull", detail: { key: "bullResearch" }, error: getLiveFlowBlockError("bull_researcher") },
        bearResearcher: { blockKey: "bear_researcher", title: "Bear Researcher", ready: Boolean(researchDebateReady && state.run.research?.bear_history), status: researchNodeStatus("bear_researcher", "Bear Researcher", state.run.research?.bear_history), tone: "bear", detail: { key: "bearResearch" }, error: getLiveFlowBlockError("bear_researcher") },
        researchDebate: { blockKey: "research_debate", title: "Research Debate", ready: researchDebateReady, status: getLiveFlowBlockError("research_debate") ? "error" : statusFor(researchDebateReady, researchCanRun && Boolean(state.run.research?.history || groupStatus("research", "Bull Researcher") === "in_progress" || groupStatus("research", "Bear Researcher") === "in_progress"), researchCanRun), tone: "debate", detail: { key: "researchDebate" }, error: getLiveFlowBlockError("research_debate") },
        researchManager: {
            blockKey: "research_manager",
            title: "Research Manager",
            ready: investmentPlanReady,
            status: getLiveFlowBlockError("research_manager") ? "error" : statusFor(investmentPlanReady, researchManagerBackendStatus === "in_progress" || isCurrent("Research Manager"), researchDebateReady),
            tone: "plan",
            detail: { type: "report", section: "investment_plan", title: "Research Manager", subtitle: "Investment plan" },
            error: getLiveFlowBlockError("research_manager"),
        },
        investmentExtractor: { blockKey: "investment_extractor", title: "Investment Plan Extractor", ready: investmentExtractorReady, status: getLiveFlowBlockError("investment_extractor") ? "error" : statusFor(investmentExtractorReady, investmentPlanReady, investmentPlanReady), tone: "evidence", detail: { key: "investmentExtractor" }, error: getLiveFlowBlockError("investment_extractor") },
        trader: {
            blockKey: "trader",
            title: "Trader",
            ready: traderReady,
            status: getLiveFlowBlockError("trader") ? "error" : statusFor(traderReady, traderBackendStatus === "in_progress" || isCurrent("Trader"), investmentExtractorReady),
            tone: "trader",
            detail: { type: "report", section: "trader_investment_plan", title: "Trader", subtitle: "Transaction proposal" },
            error: getLiveFlowBlockError("trader"),
        },
        traderExtractor: { blockKey: "trader_extractor", title: "Trader Plan Extractor", ready: traderExtractorReady, status: getLiveFlowBlockError("trader_extractor") ? "error" : statusFor(traderExtractorReady, traderReady, traderReady), tone: "evidence", detail: { key: "traderExtractor" }, error: getLiveFlowBlockError("trader_extractor") },
        aggressiveRisk: { blockKey: "aggressive_risk", title: "Aggressive Analyst", ready: Boolean(riskDebateReady && (state.run.risk?.aggressive_history || state.run.risk?.current_aggressive_response)), status: riskNodeStatus("aggressive_risk", "Aggressive Analyst", state.run.risk?.aggressive_history || state.run.risk?.current_aggressive_response), tone: "aggressive", detail: { key: "aggressiveRisk" }, error: getLiveFlowBlockError("aggressive_risk") },
        conservativeRisk: { blockKey: "conservative_risk", title: "Conservative Analyst", ready: Boolean(riskDebateReady && (state.run.risk?.conservative_history || state.run.risk?.current_conservative_response)), status: riskNodeStatus("conservative_risk", "Conservative Analyst", state.run.risk?.conservative_history || state.run.risk?.current_conservative_response), tone: "conservative", detail: { key: "conservativeRisk" }, error: getLiveFlowBlockError("conservative_risk") },
        neutralRisk: { blockKey: "neutral_risk", title: "Neutral Analyst", ready: Boolean(riskDebateReady && (state.run.risk?.neutral_history || state.run.risk?.current_neutral_response)), status: riskNodeStatus("neutral_risk", "Neutral Analyst", state.run.risk?.neutral_history || state.run.risk?.current_neutral_response), tone: "neutral", detail: { key: "neutralRisk" }, error: getLiveFlowBlockError("neutral_risk") },
        riskDebate: { blockKey: "risk_debate", title: "Risk Debate", ready: riskDebateReady, status: getLiveFlowBlockError("risk_debate") ? "error" : statusFor(riskDebateReady, riskCanRun && Boolean(state.run.risk?.history || groupStatus("risk", "Aggressive Analyst") === "in_progress" || groupStatus("risk", "Conservative Analyst") === "in_progress" || groupStatus("risk", "Neutral Analyst") === "in_progress"), riskCanRun), tone: "risk", detail: { key: "riskDebate" }, error: getLiveFlowBlockError("risk_debate") },
        portfolioManager: {
            blockKey: "portfolio_manager",
            title: "Portfolio Manager",
            ready: finalDecisionReady,
            status: getLiveFlowBlockError("portfolio_manager") ? "error" : statusFor(finalDecisionReady, portfolioBackendStatus === "in_progress" || isCurrent("Portfolio Manager"), riskDebateReady),
            tone: "decision",
            detail: { type: "report", section: "final_trade_decision", title: "Portfolio Manager", subtitle: "Final decision" },
            error: getLiveFlowBlockError("portfolio_manager"),
        },
        decisionExtractor: { blockKey: "decision_extractor", title: "Decision Extractor", ready: decisionExtractorReady, status: getLiveFlowBlockError("decision_extractor") ? "error" : statusFor(decisionExtractorReady, finalDecisionReady, finalDecisionReady), tone: "evidence", detail: { key: "decisionExtractor" }, error: getLiveFlowBlockError("decision_extractor") },
        verifier: {
            blockKey: "verifier",
            title: "Verifier",
            ready: verifierReady,
            status: getLiveFlowBlockError("verifier") ? "error" : statusFor(verifierReady, groupStatus("portfolio", "Verifier") === "in_progress" || isCurrent("Verifier"), decisionExtractorReady),
            tone: "review",
            detail: { type: "report", section: "verification_report", title: "Verifier", subtitle: "Decision audit" },
            error: getLiveFlowBlockError("verifier"),
        },
        persistence: { blockKey: "persistence", title: "History + Decision Persistence", ready: persistenceReady, status: getLiveFlowBlockError("persistence") ? "error" : statusFor(persistenceReady, verifierReady, verifierReady), tone: "evidence", detail: { key: "persistence" }, error: getLiveFlowBlockError("persistence") },
    };
}

function buildLiveFlowBoardState() {
    const complete = state.run.complete || {};
    const telemetry = complete.telemetry || {};
    const signal = complete.signal || (state.run.cancelled ? "Stopped" : state.isBusy ? "Running" : "Pending");
    const verdict = complete.verification_verdict || "-";
    const verificationAction = complete.verification_action || "-";
    const warningItems = state.run.warnings.slice(0, 2);
    const latestTool = [...state.run.traceFeed].reverse().find((item) => isToolTracePhase(item.phase));
    const currentFocus = state.run.status?.current_agent || "Waiting";
    const latestOutput = state.run.latestReportTitle || complete.signal || state.run.cancelled?.message || latestTool?.title || "-";
    const tone = state.run.cancelled ? "warning" : state.isBusy ? "progress" : state.run.complete ? "completed" : "idle";

    return {
        complete,
        telemetry,
        signal,
        verdict,
        verificationAction,
        warningItems,
        latestTool,
        currentFocus,
        latestOutput,
        tone,
    };
}

function renderLiveFlowCurveWire(paths = [], className = "", viewBox = "0 0 100 100") {
    if (!paths.length) {
        return "";
    }
    const wireMarkup = paths
        .map((path, index) => {
            const delay = (index * 0.18).toFixed(2);
            return `
                <path class="history-diagram-curve-base" d="${path}" pathLength="1"></path>
                <path class="history-diagram-curve-glow" d="${path}" pathLength="1"></path>
                <path class="history-diagram-curve-pulse" d="${path}" pathLength="1" style="--flow-delay: ${delay}s"></path>
                <path class="history-diagram-curve-pulse history-diagram-curve-pulse--late" d="${path}" pathLength="1" style="--flow-delay: ${(Number(delay) + 1.15).toFixed(2)}s"></path>
            `;
        })
        .join("");
    return `
        <div class="history-diagram-curve-wire ${className}" aria-hidden="true">
            <svg viewBox="${viewBox}" preserveAspectRatio="none" focusable="false">
                ${wireMarkup}
            </svg>
        </div>
    `;
}

const LIVE_FLOW_VERTICAL_WIRE_PATH = "M50 0 C36 7 64 15 50 22";
const LIVE_FLOW_SHORT_WIRE_PATH = "M50 0 C42 5 58 11 50 16";

function renderLiveFlowLeaf(node = {}, layout = {}) {
    const detail = node.detail || null;
    const dataset = detail ? buildDetailDataset(detail) : "";
    const tag = detail ? "button" : "span";
    const typeAttr = detail ? ' type="button"' : "";
    const currentAgent = String(state.run.status?.current_agent || "");
    const titleText = node.title || layout.shortTitle || "Flow block";
    const blockKey = node.blockKey || titleText.toLowerCase().replace(/[^a-z0-9]+/g, "_");
    const status = resolveLiveFlowNodeStatus({ ...node, blockKey });
    if (status === "completed") {
        markLiveFlowBlockComplete(blockKey);
    }
    const visualStatus = status === "not_selected" ? "pending" : status;
    const isReady = Boolean(node.ready || status === "completed");
    const isActive = Boolean(status === "in_progress" || (!isReady && currentAgent && currentAgent === node.title));
    const detailDataset = dataset ? `${dataset} data-flow-detail-signature="${escapeHtml(JSON.stringify(detail || {}))}"` : "";
    const classes = [
        "history-diagram-node",
        node.tone ? `history-diagram-node--${node.tone}` : "",
        `live-flow-node--${visualStatus}`,
        layout.compact ? "history-diagram-node--compact" : "",
        layout.output ? "history-diagram-node--output" : "",
        detail ? "detail-trigger" : "",
        isReady ? "is-ready" : "is-pending",
        !detail ? "is-disabled" : "",
        isActive ? "is-active" : "",
        layout.loading ? "is-loading" : "",
    ].filter(Boolean).join(" ");
    return `
        <${tag}${typeAttr} class="${classes}" data-flow-block-key="${escapeHtml(blockKey)}" data-flow-status="${escapeHtml(status)}" ${detailDataset} title="${escapeHtml(node.error || titleText)}" aria-label="${escapeHtml(detail ? `Open ${titleText} detail, ${status}` : `${titleText}, ${status}`)}"${!detail ? ' aria-disabled="true"' : ""}>
            <span class="history-diagram-node-head">
                <strong>${escapeHtml(layout.shortTitle || titleText)}</strong>
            </span>
        </${tag}>
    `;
}

function isLiveFlowNodeVisible(node = {}) {
    if (node.visible === false) {
        return false;
    }
    const status = resolveLiveFlowNodeStatus(node);
    if (node.ready || status === "completed" || status === "in_progress") {
        return true;
    }
    if (state.isBusy || !state.run.complete) {
        return true;
    }
    return Boolean(state.run.complete && status === "completed");
}

function renderLiveFlowNode(node = {}, layout = {}) {
    if (!Array.isArray(node.nodes)) {
        return renderLiveFlowLeaf(node, layout);
    }

    const title = node.title || "Flow Stage";
    const groupTone = String(node.tone || "neutral");
    if (title === "Parallel endpoint summaries") {
        return `
            <section class="history-diagram-group history-diagram-group--sources live-flow-group live-flow-group--sources">
                <span class="history-diagram-label">Parallel endpoint summaries</span>
                <div class="history-diagram-source-grid">
                    ${node.nodes
                        .map((child) => {
                            const shortTitle = child.title || "Source";
                            const columnKey = String(shortTitle || groupTone).toLowerCase().replace(/[^a-z0-9]+/g, "-");
                            return `
                                <div class="history-diagram-source-column history-diagram-source-column--${columnKey}">
                                    <span class="history-diagram-source-label">${escapeHtml(shortTitle)}</span>
                                    <div class="history-diagram-source-list">
                                        ${renderLiveFlowLeaf(child, { compact: true, shortTitle })}
                                    </div>
                                </div>
                            `;
                        })
                        .join("")}
                </div>
            </section>
        `;
    }

    if (title === "Analysts") {
        return `
            <section class="history-diagram-group history-diagram-group--signals live-flow-group live-flow-group--signals">
                <span class="history-diagram-label">Analysts</span>
                <div class="history-diagram-signal-grid">
                    ${node.nodes
                        .map((child) => `
                            <div class="history-diagram-signal-lane">
                                ${renderLiveFlowLeaf(child, { compact: true })}
                            </div>
                        `)
                        .join("")}
                </div>
            </section>
        `;
    }

    if (title === "Research Chamber") {
        return `
            <section class="history-diagram-group history-diagram-group--research live-flow-group live-flow-group--research">
                <span class="history-diagram-label">Research Chamber</span>
                <div class="history-diagram-cluster history-diagram-cluster--research">
                    <div class="history-diagram-cluster-grid history-diagram-cluster-grid--research">
                        ${node.nodes.map((child) => renderLiveFlowLeaf(child, { compact: true })).join("")}
                    </div>
                </div>
            </section>
        `;
    }

    if (title === "Risk Room") {
        return `
            <section class="history-diagram-group history-diagram-group--risk live-flow-group live-flow-group--risk">
                <span class="history-diagram-label">Risk Room</span>
                <div class="history-diagram-cluster history-diagram-cluster--risk">
                    <div class="history-diagram-cluster-grid history-diagram-cluster-grid--risk">
                        ${node.nodes.map((child) => renderLiveFlowLeaf(child, { compact: true })).join("")}
                    </div>
                </div>
            </section>
        `;
    }

    return `
        <section class="history-diagram-group history-diagram-group--${escapeHtml(groupTone)} live-flow-group live-flow-group--${escapeHtml(groupTone)}">
            <span class="history-diagram-label">${escapeHtml(title)}</span>
            <div class="history-diagram-extra">
                <div class="history-diagram-extra-grid">
                    ${node.nodes.map((child) => renderLiveFlowLeaf(child, { compact: true })).join("")}
                </div>
            </div>
        </section>
    `;
}

function renderLiveFlowStageConnector(fromStage = null, toStage = null) {
    if (!fromStage || !toStage) {
        return "";
    }
    return '<span class="history-diagram-vertical-connector live-flow-vertical-connector" aria-hidden="true"></span>';
}

function getLiveFlowWireStatusClass(fromNode = null, toNode = null) {
    if (!fromNode || !toNode || fromNode.visible === false || toNode.visible === false) {
        return "live-flow-wire--pending";
    }
    const fromStatus = resolveLiveFlowNodeStatus(fromNode);
    const toStatus = resolveLiveFlowNodeStatus(toNode);
    if (fromStatus === "error" || toStatus === "error") {
        return "live-flow-wire--error";
    }
    if (fromStatus === "completed" && toStatus === "completed") {
        return "live-flow-wire--complete";
    }
    if (fromStatus === "completed" && toStatus === "in_progress") {
        return "live-flow-wire--active";
    }
    return "live-flow-wire--pending";
}

function combineLiveFlowNodes(nodes = []) {
    const visibleNodes = nodes.filter((node) => node && node.visible !== false);
    if (!visibleNodes.length) {
        return { status: "pending", ready: false, visible: false };
    }
    const statuses = visibleNodes.map((node) => resolveLiveFlowNodeStatus(node));
    const allComplete = statuses.every((status) => status === "completed");
    const anyActive = statuses.some((status) => status === "in_progress");
    const anyError = statuses.some((status) => status === "error");
    return {
        status: anyError ? "error" : allComplete ? "completed" : anyActive ? "in_progress" : "pending",
        ready: allComplete,
        visible: true,
    };
}

function renderLiveFlowWire(className = "", fromNode = null, toNode = null) {
    const statusClass = getLiveFlowWireStatusClass(fromNode, toNode);
    const isPair = String(className || "").includes("--pair");
    return renderLiveFlowCurveWire(
        [isPair ? LIVE_FLOW_SHORT_WIRE_PATH : LIVE_FLOW_VERTICAL_WIRE_PATH],
        `live-flow-wire ${className} ${statusClass}`,
        isPair ? "0 0 100 16" : "0 0 100 22",
    );
}

function renderLiveFlowFanInWire(sourceCount = 0, className = "", fromNode = null, toNode = null) {
    const count = Math.max(1, Number(sourceCount || 0));
    const statusClass = getLiveFlowWireStatusClass(fromNode, toNode);
    const step = 100 / count;
    const paths = Array.from({ length: count }, (_unused, index) => {
        const x = Math.round((step * index + step / 2) * 100) / 100;
        return `M${x} 0 C${x} 12 50 16 50 34`;
    });
    return renderLiveFlowCurveWire(paths, `live-flow-wire live-flow-wire--fan-in ${className} ${statusClass}`, "0 0 100 36");
}

function renderLiveFlowFanOutWire(targetCount = 0, className = "", fromNode = null, toNode = null) {
    const count = Math.max(1, Number(targetCount || 0));
    const statusClass = getLiveFlowWireStatusClass(fromNode, toNode);
    const step = 100 / count;
    const paths = Array.from({ length: count }, (_unused, index) => {
        const x = Math.round((step * index + step / 2) * 100) / 100;
        return `M50 0 C50 12 ${x} 16 ${x} 34`;
    });
    return renderLiveFlowCurveWire(paths, `live-flow-wire live-flow-wire--fan-out ${className} ${statusClass}`, "0 0 100 36");
}

function renderLiveFlowSourceLayer(sourceNodes = []) {
    const visibleSources = sourceNodes.filter((source) => source?.visible !== false && (isLiveFlowNodeVisible(source.data) || isLiveFlowNodeVisible(source.summary)));
    if (!visibleSources.length) {
        return "";
    }
    return `
        <section class="live-flow-source-layer" aria-label="Parallel endpoint summaries">
            <div class="live-flow-source-grid">
                ${visibleSources.map((source) => `
                    <div class="live-flow-source-column">
                        ${renderLiveFlowLeaf(source.data, { compact: true })}
                        ${renderLiveFlowWire("live-flow-wire--pair", source.data, source.summary)}
                        ${renderLiveFlowLeaf(source.summary, { compact: true })}
                    </div>
                `).join("")}
            </div>
        </section>
    `;
}

function getVisibleLiveFlowSourceCount(sourceNodes = []) {
    return sourceNodes.filter((source) => source?.visible !== false && (isLiveFlowNodeVisible(source.data) || isLiveFlowNodeVisible(source.summary))).length;
}

function renderLiveFlowRow(nodes = [], className = "") {
    const visibleNodes = nodes.filter(isLiveFlowNodeVisible);
    if (!visibleNodes.length) {
        return "";
    }
    return `
        <section class="live-flow-row ${className}">
            ${visibleNodes.map((node) => renderLiveFlowLeaf(node, { compact: true })).join("")}
        </section>
    `;
}

function getVisibleLiveFlowRowCount(nodes = []) {
    return nodes.filter(isLiveFlowNodeVisible).length;
}

function renderLiveFlowWireIf(visible, className = "", fromNode = null, toNode = null) {
    return visible ? renderLiveFlowWire(className, fromNode, toNode) : "";
}

function renderLiveFlowSingle(node = {}, className = "") {
    if (!isLiveFlowNodeVisible(node)) {
        return "";
    }
    return `
        <section class="live-flow-single ${className}">
            ${renderLiveFlowLeaf(node, { compact: true })}
        </section>
    `;
}

function getLiveFlowSignature() {
    const flow = buildLiveFlowNodes();
    const sourceKeys = (flow.sourceNodes || [])
        .filter((source) => source?.visible !== false)
        .map((source) => [
            source.data?.blockKey,
            isLiveFlowNodeVisible(source.data) ? "1" : "0",
            resolveLiveFlowNodeStatus(source.data),
            source.summary?.blockKey,
            isLiveFlowNodeVisible(source.summary) ? "1" : "0",
            resolveLiveFlowNodeStatus(source.summary),
        ].join(":"))
        .join("|");
    const rowKeys = [
        ...(flow.analystNodes || []),
        flow.bullResearcher,
        flow.bearResearcher,
        flow.aggressiveRisk,
        flow.conservativeRisk,
        flow.neutralRisk,
    ]
        .filter(Boolean)
        .map((node) => `${node.blockKey}:${isLiveFlowNodeVisible(node) ? "1" : "0"}:${resolveLiveFlowNodeStatus(node)}`)
        .join("|");
    const singletonKeys = [
        flow.evidenceExtractor,
        flow.evidenceLedger,
        flow.researchDebate,
        flow.researchManager,
        flow.investmentExtractor,
        flow.trader,
        flow.traderExtractor,
        flow.riskDebate,
        flow.portfolioManager,
        flow.decisionExtractor,
        flow.verifier,
        flow.persistence,
    ]
        .filter(Boolean)
        .map((node) => `${node.blockKey}:${isLiveFlowNodeVisible(node) ? "1" : "0"}:${resolveLiveFlowNodeStatus(node)}`)
        .join("|");
    const selected = Array.from(new Set(state.run.meta?.selected_analysts || [])).sort().join(",");
    return `${selected}||${sourceKeys}||${rowKeys}||${singletonKeys}`;
}

function updateLiveFlowNodeDom(node = {}) {
    if (!node?.blockKey) {
        return;
    }
    const escapedBlockKey = window.CSS?.escape
        ? CSS.escape(node.blockKey)
        : String(node.blockKey).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
        const element = elements.reportGrid?.querySelector(`[data-flow-block-key="${escapedBlockKey}"]`);
    if (!(element instanceof HTMLElement)) {
        return;
    }
    const status = resolveLiveFlowNodeStatus(node);
    if (status === "completed") {
        markLiveFlowBlockComplete(node.blockKey);
    }
    const visualStatus = status === "not_selected" ? "pending" : status;
    const isReady = Boolean(node.ready || status === "completed");
    const isActive = Boolean(status === "in_progress" || (!isReady && state.run.status?.current_agent === node.title));
    ["pending", "in_progress", "completed", "error"].forEach((value) => {
        element.classList.toggle(`live-flow-node--${value}`, visualStatus === value);
    });
    element.classList.toggle("is-ready", isReady);
    element.classList.toggle("is-pending", !isReady);
    element.classList.toggle("is-active", isActive);
    element.dataset.flowStatus = status;
    if (node.error) {
        element.title = node.error;
    } else {
        element.title = node.title || element.title;
    }
    if (node.detail) {
        applyDetailAttributes(element, node.detail);
        element.dataset.flowDetailSignature = JSON.stringify(node.detail || {});
    }
}

function walkLiveFlowNodes(visitor) {
    const flow = buildLiveFlowNodes();
    (flow.sourceNodes || []).forEach((source) => {
        visitor(source.data);
        visitor(source.summary);
    });
    [
        ...(flow.analystNodes || []),
        flow.evidenceExtractor,
        flow.evidenceLedger,
        flow.bullResearcher,
        flow.bearResearcher,
        flow.researchDebate,
        flow.researchManager,
        flow.investmentExtractor,
        flow.trader,
        flow.traderExtractor,
        flow.aggressiveRisk,
        flow.conservativeRisk,
        flow.neutralRisk,
        flow.riskDebate,
        flow.portfolioManager,
        flow.decisionExtractor,
        flow.verifier,
        flow.persistence,
    ].filter(Boolean).forEach(visitor);
}

function syncLiveFlowDomState() {
    walkLiveFlowNodes(updateLiveFlowNodeDom);
}

function renderLiveAgentFlow() {
    const flow = buildLiveFlowNodes();
    const sourceCount = getVisibleLiveFlowSourceCount(flow.sourceNodes);
    const analystCount = getVisibleLiveFlowRowCount(flow.analystNodes);
    const researcherCount = getVisibleLiveFlowRowCount([flow.bullResearcher, flow.bearResearcher]);
    const riskCount = getVisibleLiveFlowRowCount([flow.aggressiveRisk, flow.conservativeRisk, flow.neutralRisk]);
    const evidenceVisible = isLiveFlowNodeVisible(flow.evidenceExtractor);
    const ledgerVisible = isLiveFlowNodeVisible(flow.evidenceLedger);
    const researchDebateVisible = isLiveFlowNodeVisible(flow.researchDebate);
    const researchManagerVisible = isLiveFlowNodeVisible(flow.researchManager);
    const investmentExtractorVisible = isLiveFlowNodeVisible(flow.investmentExtractor);
    const traderVisible = isLiveFlowNodeVisible(flow.trader);
    const traderExtractorVisible = isLiveFlowNodeVisible(flow.traderExtractor);
    const riskDebateVisible = isLiveFlowNodeVisible(flow.riskDebate);
    const portfolioVisible = isLiveFlowNodeVisible(flow.portfolioManager);
    const decisionExtractorVisible = isLiveFlowNodeVisible(flow.decisionExtractor);
    const verifierVisible = isLiveFlowNodeVisible(flow.verifier);
    const persistenceVisible = isLiveFlowNodeVisible(flow.persistence);
    const sourceDataNodes = (flow.sourceNodes || [])
        .filter((source) => source?.visible !== false && isLiveFlowNodeVisible(source.data))
        .map((source) => source.data);
    const sourceSummaryNodes = (flow.sourceNodes || [])
        .filter((source) => source?.visible !== false && isLiveFlowNodeVisible(source.summary))
        .map((source) => source.summary);
    const sourceGroupNode = combineLiveFlowNodes(sourceSummaryNodes.length ? sourceSummaryNodes : sourceDataNodes);
    const analystGroupNode = combineLiveFlowNodes(flow.analystNodes || []);
    const researcherGroupNode = combineLiveFlowNodes([flow.bullResearcher, flow.bearResearcher]);
    const riskGroupNode = combineLiveFlowNodes([flow.aggressiveRisk, flow.conservativeRisk, flow.neutralRisk]);

    const segments = [
        renderLiveFlowSourceLayer(flow.sourceNodes),
        sourceCount && analystCount ? renderLiveFlowFanOutWire(analystCount, "live-flow-wire--sources-to-analysts", sourceGroupNode, analystGroupNode) : "",
        renderLiveFlowRow(flow.analystNodes, "live-flow-row--analysts"),
        analystCount && evidenceVisible ? renderLiveFlowFanInWire(analystCount, "live-flow-wire--analysts-to-evidence", analystGroupNode, flow.evidenceExtractor) : "",
        renderLiveFlowSingle(flow.evidenceExtractor, "live-flow-single--evidence"),
        renderLiveFlowWireIf(evidenceVisible && ledgerVisible, "live-flow-wire--evidence-to-ledger", flow.evidenceExtractor, flow.evidenceLedger),
        renderLiveFlowSingle(flow.evidenceLedger, "live-flow-single--ledger"),
        ledgerVisible && researcherCount ? renderLiveFlowFanOutWire(researcherCount, "live-flow-wire--ledger-to-researchers", flow.evidenceLedger, researcherGroupNode) : "",
        renderLiveFlowRow([flow.bullResearcher, flow.bearResearcher], "live-flow-row--researchers"),
        researcherCount && researchDebateVisible ? renderLiveFlowFanInWire(researcherCount, "live-flow-wire--research-to-debate", researcherGroupNode, flow.researchDebate) : "",
        renderLiveFlowSingle(flow.researchDebate, "live-flow-single--debate"),
        renderLiveFlowWireIf(researchDebateVisible && researchManagerVisible, "live-flow-wire--debate-to-manager", flow.researchDebate, flow.researchManager),
        renderLiveFlowSingle(flow.researchManager, "live-flow-single--manager"),
        renderLiveFlowWireIf(researchManagerVisible && investmentExtractorVisible, "live-flow-wire--manager-to-extractor", flow.researchManager, flow.investmentExtractor),
        renderLiveFlowSingle(flow.investmentExtractor, "live-flow-single--extractor"),
        renderLiveFlowWireIf(investmentExtractorVisible && traderVisible, "live-flow-wire--extractor-to-trader", flow.investmentExtractor, flow.trader),
        renderLiveFlowSingle(flow.trader, "live-flow-single--trader"),
        renderLiveFlowWireIf(traderVisible && traderExtractorVisible, "live-flow-wire--trader-to-extractor", flow.trader, flow.traderExtractor),
        renderLiveFlowSingle(flow.traderExtractor, "live-flow-single--extractor"),
        traderExtractorVisible && riskCount ? renderLiveFlowFanOutWire(riskCount, "live-flow-wire--trader-to-risk", flow.traderExtractor, riskGroupNode) : "",
        renderLiveFlowRow([flow.aggressiveRisk, flow.conservativeRisk, flow.neutralRisk], "live-flow-row--risk-analysts"),
        riskCount && riskDebateVisible ? renderLiveFlowFanInWire(riskCount, "live-flow-wire--risk-to-debate", riskGroupNode, flow.riskDebate) : "",
        renderLiveFlowSingle(flow.riskDebate, "live-flow-single--risk"),
        renderLiveFlowWireIf(riskDebateVisible && portfolioVisible, "live-flow-wire--risk-to-portfolio", flow.riskDebate, flow.portfolioManager),
        renderLiveFlowSingle(flow.portfolioManager, "live-flow-single--portfolio"),
        renderLiveFlowWireIf(portfolioVisible && decisionExtractorVisible, "live-flow-wire--portfolio-to-extractor", flow.portfolioManager, flow.decisionExtractor),
        renderLiveFlowSingle(flow.decisionExtractor, "live-flow-single--extractor"),
        renderLiveFlowWireIf(decisionExtractorVisible && verifierVisible, "live-flow-wire--extractor-to-verifier", flow.decisionExtractor, flow.verifier),
        renderLiveFlowSingle(flow.verifier, "live-flow-single--verifier"),
        renderLiveFlowWireIf(verifierVisible && persistenceVisible, "live-flow-wire--verifier-to-persistence", flow.verifier, flow.persistence),
        renderLiveFlowSingle(flow.persistence, "live-flow-single--persistence"),
    ];

    return segments.filter(Boolean).join("");
}

function renderFlowInspectorMarkup() {
    return `
        <article class="live-focus-card live-focus-card-expanded live-flow-board">
            <div class="history-diagram-wrap live-flow-diagram-wrap" aria-label="Live flow diagram">
                <div class="history-diagram history-diagram--vertical live-flow-diagram">
                    ${renderLiveAgentFlow()}
                </div>
            </div>
        </article>
    `;
}

function clearDetailAttributes(element) {
    ["data-detail-key", "data-detail-section", "data-detail-title", "data-detail-subtitle", "data-detail-mode", "data-detail-trace-id"].forEach((attribute) => {
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
        if (detail.mode) {
            element.dataset.detailMode = detail.mode;
        }
        return;
    }
    if (detail.type === "trace") {
        element.dataset.detailTraceId = detail.traceId || "";
        element.dataset.detailTitle = detail.title || "Tool Detail";
        element.dataset.detailSubtitle = detail.subtitle || "Agent tool trace";
        element.dataset.detailMode = detail.mode || "markdown";
        return;
    }
    if (detail.key) {
        element.dataset.detailKey = detail.key;
    }
}

function renderReportGrid() {
    if (!(elements.reportGrid instanceof HTMLElement)) {
        return;
    }

    const nextSignature = getLiveFlowSignature();
    const existingDiagram = elements.reportGrid.querySelector(".live-flow-diagram");
    if (!(existingDiagram instanceof HTMLElement) || state.run.liveFlowSignature !== nextSignature) {
        const scrollHost = elements.reportGrid.querySelector(".live-flow-diagram-wrap");
        const previousScrollTop = scrollHost instanceof HTMLElement ? scrollHost.scrollTop : 0;
        const previousScrollLeft = scrollHost instanceof HTMLElement ? scrollHost.scrollLeft : 0;
        elements.reportGrid.innerHTML = `
            <div class="live-layout live-layout-single">
                ${renderFlowInspectorMarkup()}
            </div>
        `;
        state.run.liveFlowSignature = nextSignature;
        const nextScrollHost = elements.reportGrid.querySelector(".live-flow-diagram-wrap");
        if (nextScrollHost instanceof HTMLElement) {
            nextScrollHost.scrollTop = previousScrollTop;
            nextScrollHost.scrollLeft = previousScrollLeft;
        }
        syncLiveFlowDomState();
    } else {
        syncLiveFlowDomState();
    }

    elements.activeReportText.textContent = state.run.cancelled?.message
        || (state.isBusy ? "Live flow diagram" : state.run.complete?.signal || "Waiting for live stream");
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

function getSourceGroupArtifactRows(groupKey = "") {
    const config = SOURCE_ARTIFACT_GROUPS[groupKey] || {};
    const savedRows = (state.run.sourceArtifactLists?.[groupKey] || []).filter((item) => item.source_kind !== "flow_block");
    return {
        groupKey,
        flowGroup: config.flowGroup || "",
        saved: savedRows.map((item) => ({
            section_key: item.section_key || "",
            title: item.title || item.source_key || "",
            source_kind: item.source_kind || item.artifact_type || "",
            source_key: item.source_key || "",
            summary: item.summary || "",
            created_at: item.created_at || "",
        })),
        live: getLiveSourceTraceEntries(groupKey).map((entry) => ({
            id: entry.id || "",
            title: entry.title || "",
            agent: entry.agent || "",
            phase: entry.phase || "",
            trace_id: entry.traceId || "",
            query: entry.toolCallContent || "",
            result: entry.toolResultContent || entry.content || "",
            timestamp: entry.timestamp || "",
        })),
    };
}

function getLiveFlowBlockPayload(blockKey = "", title = "", status = "pending", detail = null, summary = "") {
    const relatedSections = [];
    if (detail?.section) {
        relatedSections.push(detail.section);
    }
    if (detail?.key) {
        relatedSections.push(detail.key);
    }
    return {
        block_key: blockKey,
        title,
        status,
        summary,
        detail,
        related_sections: relatedSections,
        error: getLiveFlowBlockError(blockKey),
    };
}

function formatStructuredPayloadMarkdown(payload = {}, title = "Structured Payload") {
    if (!payload || typeof payload !== "object" || Array.isArray(payload) || Object.keys(payload).length === 0) {
        return "";
    }
    const renderStructuredFieldValue = (value) => {
        if (value === null) {
            return "null";
        }
        if (value === undefined) {
            return "";
        }
        if (typeof value === "object") {
            return JSON.stringify(value, null, 2);
        }
        return value;
    };
    const rows = [
        "| Field | Value |",
        "| --- | --- |",
        ...Object.entries(payload).map(([key, value]) => {
            return `| ${markdownCell(key)} | ${markdownCell(renderStructuredFieldValue(value))} |`;
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
        case "liveCcxtSummary":
            return {
                content: getLiveSourceSummaryMarkdown("ccxt"),
                fallback: "Market summary markdown is not available yet.",
                payload: getSourceGroupArtifactRows("ccxt"),
            };
        case "liveCoinglassSummary":
            return {
                content: getLiveSourceSummaryMarkdown("coinglass"),
                fallback: "Derivatives / flow summary markdown is not available yet.",
                payload: getSourceGroupArtifactRows("coinglass"),
            };
        case "liveNewsSummary":
            return {
                content: getLiveSourceSummaryMarkdown("news"),
                fallback: "News summary markdown is not available yet.",
                payload: getSourceGroupArtifactRows("news"),
            };
        case "liveSocialSummary":
            return {
                content: getLiveSourceSummaryMarkdown("social"),
                fallback: "Social summary markdown is not available yet.",
                payload: getSourceGroupArtifactRows("social"),
            };
        case "liveFlowSummary":
            return {
                content: getLiveSourceSummaryMarkdown("flow"),
                fallback: "Flow summary markdown is not available yet.",
                payload: getSourceGroupArtifactRows("flow"),
            };
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
            return { content: risk.aggressive_history || risk.current_aggressive_response || "", fallback: "The Aggressive Analyst has not responded yet." };
        case "conservativeRisk":
            return { content: risk.conservative_history || risk.current_conservative_response || "", fallback: "The Conservative Analyst has not responded yet." };
        case "neutralRisk":
            return { content: risk.neutral_history || risk.current_neutral_response || "", fallback: "The Neutral Analyst has not responded yet." };
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
        case "persistence":
            return {
                content: [
                    "# History + Decision Persistence",
                    "",
                    `- History ID: ${state.run.complete?.history_id || "-"}`,
                    `- Source artifacts: ${getLiveSourceArtifactCount() || 0}`,
                    `- Evidence items: ${getLiveEvidenceCount() || 0}`,
                    `- Status: ${state.run.complete?.history_id ? "Saved" : state.run.complete ? "Completed without saved history ID" : "Pending"}`,
                ].join("\n"),
                fallback: "Persistence has not run yet.",
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
    setDetailPayload(detail, detailContent);
    const { content, fallback, toolResult, traceEntry } = detailContent;
    const mode = detailContent.mode || (toolResult ? "tool-result" : detail.mode || meta.mode || "markdown");
    const canGoBack = Array.isArray(state.detailBackStack) && state.detailBackStack.length > 0;
    if (elements.backDetailButton instanceof HTMLElement) {
        elements.backDetailButton.hidden = !canGoBack;
        elements.backDetailButton.disabled = !canGoBack;
    }
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

function openDetailModal(detail, options = {}) {
    if (options.pushHistory !== false && state.activeDetail && !elements.detailModal.classList.contains("hidden")) {
        state.detailBackStack = [...(state.detailBackStack || []), state.activeDetail].slice(-12);
    }
    state.activeDetail = detail;
    showModal(elements.detailModal);
    renderActiveDetail();
}

function goBackDetailModal() {
    const previousDetail = state.detailBackStack?.pop();
    if (!previousDetail) {
        return;
    }
    state.activeDetail = previousDetail;
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
    }, { pushHistory: false });
}

function closeDetailModal() {
    hideModal(elements.detailModal);
    state.activeDetail = null;
    state.detailBackStack = [];
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

