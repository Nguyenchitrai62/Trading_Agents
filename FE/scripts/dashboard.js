function getCheckedAnalysts() {
    return normalizeAnalystKeys(Array.from(elements.analystOptions.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value));
}

function getSelectedDepth() {
    const checked = elements.depthOptions.querySelector('input[name="researchDepth"]:checked');
    return checked ? checked.value : state.config?.analysis_defaults?.research_depth || "auto";
}

function getOutputLanguage() {
    return elements.languageInput.value.trim();
}

function getQuickReasoningEffort() {
    return String(elements.quickReasoningSelect?.value || "max").trim();
}

function getDeepReasoningEffort() {
    return String(elements.deepReasoningSelect?.value || "max").trim();
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
    // No-op: language is now a free-text input.
}

function syncAnalystAvailability() {
    const onchainInput = elements.analystOptions.querySelector('input[value="onchain"]');
    if (!onchainInput) {
        return;
    }

    const card = onchainInput.closest(".checkbox-card");
    onchainInput.disabled = false;
    card?.classList.remove("checkbox-card-disabled");
}

function refreshConfigUi() {
    syncLanguageControls();
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
        const depth = state.run.depthEscalation
            ? `${state.run.depthEscalation.to_label || state.run.depthEscalation.to_rounds}r`
            : (state.run.meta?.effective_research_depth && state.run.meta.effective_research_depth !== state.run.meta.research_depth
                ? `${state.run.meta.research_depth || state.run.meta.effective_research_depth || "auto"} / ${state.run.meta.effective_research_depth}`
                : state.run.meta?.research_depth || payload?.research_depth || state.config.analysis_defaults.research_depth);
        const revCount = Number(state.run.revisionCount || 0);
        const revSuffix = revCount > 0 ? ` (Rev ${revCount})` : "";
        notice = `${symbol} - ${depth} depth - ${progress.completed}/${progress.total} tasks${revSuffix}`;
    } else if (state.run.complete) {
        const symbol = state.run.meta?.symbol || payload?.symbol || state.config.analysis_defaults.symbol;
        const signal = state.run.complete.signal || "analysis completed";
        const elapsed = state.run.complete.elapsed_seconds ? ` - ${state.run.complete.elapsed_seconds}s` : "";
        notice = `${symbol} - ${signal}${elapsed}`;
    } else if (payload) {
        notice = `${payload.symbol || "-"} - ${payload.output_language || "-"} - ${payload.selected_analysts.length} analysts`;
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

    elements.configPreview.innerHTML = `
        <div class="config-preview-header">
            <span>Run Snapshot</span>
            <strong>${escapeHtml(payload.symbol || "-")}</strong>
        </div>
        <div class="config-summary-grid">
            <div class="config-summary-chip">
                <span>Quick Model</span>
                <strong>${escapeHtml(`${payload.quick_think_model || "-"} (${payload.quick_reasoning_effort || "max"})`)}</strong>
            </div>
            <div class="config-summary-chip">
                <span>Deep Model</span>
                <strong>${escapeHtml(`${payload.deep_think_model || "-"} (${payload.deep_reasoning_effort || "max"})`)}</strong>
            </div>
            <div class="config-summary-chip">
                <span>Depth</span>
                <strong>${escapeHtml(`${payload.research_depth || "auto"}${effectiveDepth}`)}</strong>
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
        summaryTitle: "Onchain Endpoint Summary",
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
        return "coinglass";
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
    ["ccxt", "coinglass", "news", "social"].forEach((groupKey) => {
        getLiveSourceTraceEntries(groupKey).forEach((entry) => keys.add(entry.id || `${entry.agent}:${entry.title}:${entry.traceId}`));
    });
    return keys.size;
}

function isWebSearchTraceEntry(entry = {}) {
    const title = String(entry.title || "").toLowerCase();
    const traceId = String(entry.traceId || entry.trace_id || "").toLowerCase();
    const content = String(entry.toolCallContent || entry.content || "").toLowerCase();
    return title === "web_search"
        || title === "web search"
        || title.includes("web_search")
        || title.includes("web-search")
        || traceId.includes("web_search")
        || /^web_search\s*\(/.test(content);
}

function isLiveSourceTraceEntryForGroup(entry = {}, groupKey = "", phases = ["tool_result", "tool_trace"]) {
    if (!entry || !phases.includes(entry.phase)) {
        return false;
    }
    const title = String(entry.title || "").toLowerCase();
    const agent = String(entry.agent || "").toLowerCase();
    const traceId = String(entry.traceId || entry.trace_id || "").toLowerCase();
    const sourceGroup = String(entry.sourceGroup || entry.source_group || "").toLowerCase();
    const configuredFlowGroup = String(SOURCE_ARTIFACT_GROUPS[groupKey]?.flowGroup || "").toLowerCase();
    if (configuredFlowGroup && sourceGroup) {
        return sourceGroup === configuredFlowGroup;
    }
    const isWebSearch = isWebSearchTraceEntry(entry);
    if (groupKey === "ccxt") {
        return title === "get_crypto_ohlcv" || title === "get_crypto_indicators";
    }
    if (groupKey === "coinglass") {
        return traceId.startsWith("coinglass:") || title.includes("coinglass");
    }
    if (groupKey === "news") {
        return (isWebSearch && agent.includes("news"))
            || (!isWebSearch && (agent.includes("news") || title.includes("news") || title === "get_global_news"));
    }
    if (groupKey === "social") {
        return (isWebSearch && agent.includes("social"))
            || (!isWebSearch && (agent.includes("social") || title.includes("reddit") || title.includes("stocktwits")));
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
    if (!config || !config.flowGroup || !historyId || !canReadHistory()) {
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
    const selectedAnalysts = new Set(normalizeAnalystKeys(state.run.meta?.selected_analysts || ["market", "onchain", "social", "news"]));
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
        ["onchain", "onchain_report", "Onchain Analyst", "onchain_analyst"],
        ["social", "sentiment_report", "Social Analyst", "social_analyst"],
        ["news", "news_report", "News Analyst", "news_analyst"],
    ];
    const selectedAnalystSpecs = analystSpecs.filter(([analystKey]) => selectedAnalysts.has(analystKey));
    const analystSourceGroups = {
        market: ["ccxt"],
        onchain: ["coinglass"],
        social: ["social"],
        news: ["news"],
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
    const marketSummaryReady = getLiveSourceSummaryReady("ccxt");
    const coinglassSummaryReady = getLiveSourceSummaryReady("coinglass");
    const newsSummaryReady = getLiveSourceSummaryReady("news");
    const socialSummaryReady = getLiveSourceSummaryReady("social");
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
    const researchDebateReady = researchCount >= expectedResearchTurns
        || groupStatus("risk", "Aggressive Analyst") === "in_progress"
        || Boolean(state.run.risk?.history);
    const researchCanRun = selectedAnalystReportsComplete;
    const researchNodeStatus = (blockKey, label, hasContent) => {
        const backendStatus = normalizeStatus(groupStatus("research", label));
        const active = backendStatus === "in_progress" || isCurrent(label);
        const complete = Boolean(researchDebateReady && hasContent);
        return getLiveFlowBlockError(blockKey) ? "error" : statusFor(complete, active, researchCanRun);
    };
    const riskCount = Number(state.run.risk?.count || 0);
    const expectedRiskTurns = depthRounds * 3;
    const portfolioBackendStatus = normalizeStatus(groupStatus("portfolio", "Portfolio Manager"));
    const riskDebateReady = (hasSection("final_trade_decision") && flowSectionCompleted("final_trade_decision"))
        || riskCount >= expectedRiskTurns
        || portfolioBackendStatus === "completed";
    const riskCanRun = researchDebateReady;
    const riskNodeStatus = (blockKey, label, hasContent) => {
        const backendStatus = normalizeStatus(groupStatus("risk", label));
        const active = backendStatus === "in_progress" || isCurrent(label);
        const complete = Boolean(riskDebateReady && hasContent);
        return getLiveFlowBlockError(blockKey) ? "error" : statusFor(complete, active, riskCanRun);
    };
    const finalDecisionReady = hasSection("final_trade_decision") && flowSectionCompleted("final_trade_decision");
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
                visible: sourceVisible("onchain", coinglassReady),
                data: buildLiveSourceDataNode("coinglass", "CoinGlass Data", coinglassReady, sourceStatus("coinglass", "onchain", "Onchain Analyst", coinglassReady), "evidence", "liveCoinGlassData", "coinglass_data"),
                summary: buildLiveSourceSummaryNode("coinglass", "Onchain Endpoint Summary", coinglassSummaryReady && coinglassReady, sourceSummaryStatus("coinglass", "onchain", "Onchain Analyst", coinglassReady), "coinglass_summary"),
            },
            {
                visible: sourceVisible("social", socialSourceReady),
                data: buildLiveSourceDataNode("social", "Social / Web Data", socialSourceReady, sourceStatus("social", "social", "Social Analyst", socialSourceReady), "signal", "liveSocialData", "social_data"),
                summary: buildLiveSourceSummaryNode("social", "Social Summary", socialSummaryReady && socialSourceReady, sourceSummaryStatus("social", "social", "Social Analyst", socialSourceReady), "social_summary"),
            },
            {
                visible: sourceVisible("news", newsSourceReady),
                data: buildLiveSourceDataNode("news", "News Data", newsSourceReady, sourceStatus("news", "news", "News Analyst", newsSourceReady), "signal", "liveNewsData", "news_data"),
                summary: buildLiveSourceSummaryNode("news", "News Summary", newsSummaryReady && newsSourceReady, sourceSummaryStatus("news", "news", "News Analyst", newsSourceReady), "news_summary"),
            },
        ],
        evidenceExtractor: { blockKey: "evidence_extractor", title: "Evidence Extractor", ready: selectedAnalystReportsComplete, status: getLiveFlowBlockError("evidence_extractor") ? "error" : statusFor(selectedAnalystReportsComplete, false), tone: "evidence", detail: { key: "evidenceExtractor" }, error: getLiveFlowBlockError("evidence_extractor") },
        analystNodes: analystSpecs.map(analystNode),
        evidenceLedger: { blockKey: "evidence_ledger", title: "Evidence Ledger", ready: selectedAnalystReportsComplete, status: getLiveFlowBlockError("evidence_ledger") ? "error" : statusFor(selectedAnalystReportsComplete, false), tone: "evidence", detail: { key: "evidenceLedger" }, error: getLiveFlowBlockError("evidence_ledger") },
        bullResearcher: { blockKey: "bull_researcher", title: "Bull Researcher", ready: Boolean(researchDebateReady && state.run.research?.bull_history), status: researchNodeStatus("bull_researcher", "Bull Researcher", state.run.research?.bull_history), tone: "bull", detail: { key: "bullResearch" }, error: getLiveFlowBlockError("bull_researcher") },
        bearResearcher: { blockKey: "bear_researcher", title: "Bear Researcher", ready: Boolean(researchDebateReady && state.run.research?.bear_history), status: researchNodeStatus("bear_researcher", "Bear Researcher", state.run.research?.bear_history), tone: "bear", detail: { key: "bearResearch" }, error: getLiveFlowBlockError("bear_researcher") },
        researchDebate: { blockKey: "research_debate", title: "Research Debate", ready: researchDebateReady, status: getLiveFlowBlockError("research_debate") ? "error" : statusFor(researchDebateReady, researchCanRun && Boolean(state.run.research?.history || groupStatus("research", "Bull Researcher") === "in_progress" || groupStatus("research", "Bear Researcher") === "in_progress"), researchCanRun), tone: "debate", detail: { key: "researchDebate" }, error: getLiveFlowBlockError("research_debate") },
        aggressiveRisk: { blockKey: "aggressive_risk", title: "Aggressive Analyst", ready: Boolean(riskDebateReady && (state.run.risk?.aggressive_history || state.run.risk?.current_aggressive_response)), status: riskNodeStatus("aggressive_risk", "Aggressive Analyst", state.run.risk?.aggressive_history || state.run.risk?.current_aggressive_response), tone: "aggressive", detail: { key: "aggressiveRisk" }, error: getLiveFlowBlockError("aggressive_risk") },
        conservativeRisk: { blockKey: "conservative_risk", title: "Conservative Analyst", ready: Boolean(riskDebateReady && (state.run.risk?.conservative_history || state.run.risk?.current_conservative_response)), status: riskNodeStatus("conservative_risk", "Conservative Analyst", state.run.risk?.conservative_history || state.run.risk?.current_conservative_response), tone: "conservative", detail: { key: "conservativeRisk" }, error: getLiveFlowBlockError("conservative_risk") },
        neutralRisk: { blockKey: "neutral_risk", title: "Neutral Analyst", ready: Boolean(riskDebateReady && (state.run.risk?.neutral_history || state.run.risk?.current_neutral_response)), status: riskNodeStatus("neutral_risk", "Neutral Analyst", state.run.risk?.neutral_history || state.run.risk?.current_neutral_response), tone: "neutral", detail: { key: "neutralRisk" }, error: getLiveFlowBlockError("neutral_risk") },
        riskDebate: { blockKey: "risk_debate", title: "Risk Debate", ready: riskDebateReady, status: getLiveFlowBlockError("risk_debate") ? "error" : statusFor(riskDebateReady, riskCanRun && Boolean(state.run.risk?.history || groupStatus("risk", "Aggressive Analyst") === "in_progress" || groupStatus("risk", "Conservative Analyst") === "in_progress" || groupStatus("risk", "Neutral Analyst") === "in_progress"), riskCanRun), tone: "risk", detail: { key: "riskDebate" }, error: getLiveFlowBlockError("risk_debate") },
        portfolioManager: {
            blockKey: "portfolio_manager",
            title: (() => {
                const rc = Number(state.run.revisionCount || 0);
                if (rc > 0) {
                    return `Portfolio Manager (Rev ${rc})`;
                }
                return "Portfolio Manager";
            })(),
            ready: finalDecisionReady,
            status: getLiveFlowBlockError("portfolio_manager") ? "error" : statusFor(finalDecisionReady, portfolioBackendStatus === "in_progress" || isCurrent("Portfolio Manager"), riskDebateReady),
            tone: "decision",
            detail: { type: "report", section: "final_trade_decision", title: "Portfolio Manager", subtitle: "Final decision" },
            error: getLiveFlowBlockError("portfolio_manager"),
        },
        verifier: {
            blockKey: "verifier",
            title: (() => {
                const rc = Number(state.run.revisionCount || 0);
                if (rc > 0) {
                    return `Verifier (Rev ${rc})`;
                }
                return "Verifier";
            })(),
            ready: verifierReady,
            status: getLiveFlowBlockError("verifier") ? "error" : statusFor(verifierReady, groupStatus("portfolio", "Verifier") === "in_progress" || isCurrent("Verifier"), finalDecisionReady),
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
    const revisionCount = Number(state.run.revisionCount || 0);
    const maxRevisions = Number(state.run.maxRevisions || 2);
    const isRevising = revisionCount > 0 && !state.run.complete;

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
        revisionCount,
        maxRevisions,
        isRevising,
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

function findLiveFlowSource(flow = {}, groupKey = "") {
    return (flow.sourceNodes || []).find((source) => source?.data?.blockKey === `${groupKey}_data`) || null;
}

function findLiveFlowAnalyst(flow = {}, blockKey = "") {
    return (flow.analystNodes || []).find((node) => node?.blockKey === blockKey) || null;
}

function renderLiveFlowAnalystLanes(flow = {}) {
    const laneSpecs = [
        { key: "market", label: "Market branch", source: findLiveFlowSource(flow, "ccxt"), analyst: findLiveFlowAnalyst(flow, "market_analyst") },
        { key: "onchain", label: "Onchain branch", source: findLiveFlowSource(flow, "coinglass"), analyst: findLiveFlowAnalyst(flow, "onchain_analyst") },
        { key: "social", label: "Social branch", source: findLiveFlowSource(flow, "social"), analyst: findLiveFlowAnalyst(flow, "social_analyst") },
        { key: "news", label: "News branch", source: findLiveFlowSource(flow, "news"), analyst: findLiveFlowAnalyst(flow, "news_analyst") },
    ];
    const lanes = laneSpecs.filter((lane) => {
        const sourceVisible = lane.source?.visible !== false && (isLiveFlowNodeVisible(lane.source?.data) || isLiveFlowNodeVisible(lane.source?.summary));
        const analystVisible = isLiveFlowNodeVisible(lane.analyst);
        return sourceVisible || analystVisible;
    });
    if (!lanes.length) {
        return "";
    }
    return `
        <section class="live-flow-analyst-lanes" aria-label="Parallel analyst source branches">
            ${lanes.map((lane) => `
                <div class="live-flow-analyst-lane live-flow-analyst-lane--${escapeHtml(lane.key)}">
                    <span class="live-flow-lane-label">${escapeHtml(lane.label)}</span>
                    ${lane.source?.data && isLiveFlowNodeVisible(lane.source.data) ? renderLiveFlowLeaf(lane.source.data, { compact: true }) : ""}
                    ${lane.source?.data && lane.source?.summary && isLiveFlowNodeVisible(lane.source.data) && isLiveFlowNodeVisible(lane.source.summary)
                        ? renderLiveFlowWire("live-flow-wire--pair", lane.source.data, lane.source.summary)
                        : ""}
                    ${lane.source?.summary && isLiveFlowNodeVisible(lane.source.summary) ? renderLiveFlowLeaf(lane.source.summary, { compact: true }) : ""}
                    ${lane.source?.summary && lane.analyst && isLiveFlowNodeVisible(lane.source.summary) && isLiveFlowNodeVisible(lane.analyst)
                        ? renderLiveFlowWire("live-flow-wire--source-to-analyst", lane.source.summary, lane.analyst)
                        : ""}
                    ${lane.analyst && isLiveFlowNodeVisible(lane.analyst) ? renderLiveFlowLeaf(lane.analyst, { compact: true }) : ""}
                </div>
            `).join("")}
        </section>
    `;
}

function renderLiveFlowWireIf(visible, className = "", fromNode = null, toNode = null) {
    return visible ? renderLiveFlowWire(className, fromNode, toNode) : "";
}

function renderLiveFlowRevisionLoop(flow = {}) {
    const revisionCount = Number(state.run.revisionCount || 0);
    const verifierReady = flow.verifier?.ready;
    const isRevising = revisionCount > 0 && verifierReady && !state.run.complete;
    if (!isRevising) {
        return "";
    }
    const revisionIssues = Array.isArray(state.run.revisionIssues) ? state.run.revisionIssues : [];
    const issueSummary = revisionIssues.length
        ? revisionIssues.map((issue) => escapeHtml(String(issue).slice(0, 120))).join("; ")
        : "Portfolio Manager is re-evaluating the decision.";
    return renderLiveFlowCurveWire(
        ["M50 0 C80 0 80 80 50 80"],
        `live-flow-wire live-flow-wire--revision live-flow-wire--revision-${Math.min(revisionCount, 2)}`,
        "0 0 100 80",
    ) + `
        <div class="live-flow-revision-notice" title="${issueSummary}">
            <span class="live-flow-revision-badge">Revision ${revisionCount}/2</span>
            <span class="live-flow-revision-hint">Verifier sent decision back to Portfolio Manager</span>
        </div>
    `;
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
        flow.riskDebate,
        flow.portfolioManager,
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
        flow.aggressiveRisk,
        flow.conservativeRisk,
        flow.neutralRisk,
        flow.riskDebate,
        flow.portfolioManager,
        flow.verifier,
        flow.persistence,
    ].filter(Boolean).forEach(visitor);
}

function syncLiveFlowDomState() {
    walkLiveFlowNodes(updateLiveFlowNodeDom);
}

function renderLiveAgentFlow() {
    const flow = buildLiveFlowNodes();
    const analystCount = getVisibleLiveFlowRowCount(flow.analystNodes);
    const researcherCount = getVisibleLiveFlowRowCount([flow.bullResearcher, flow.bearResearcher]);
    const riskCount = getVisibleLiveFlowRowCount([flow.aggressiveRisk, flow.conservativeRisk, flow.neutralRisk]);
    const evidenceVisible = isLiveFlowNodeVisible(flow.evidenceExtractor);
    const ledgerVisible = isLiveFlowNodeVisible(flow.evidenceLedger);
    const researchDebateVisible = isLiveFlowNodeVisible(flow.researchDebate);
    const riskDebateVisible = isLiveFlowNodeVisible(flow.riskDebate);
    const portfolioVisible = isLiveFlowNodeVisible(flow.portfolioManager);
    const verifierVisible = isLiveFlowNodeVisible(flow.verifier);
    const persistenceVisible = isLiveFlowNodeVisible(flow.persistence);
    const analystGroupNode = combineLiveFlowNodes(flow.analystNodes || []);
    const researcherGroupNode = combineLiveFlowNodes([flow.bullResearcher, flow.bearResearcher]);
    const riskGroupNode = combineLiveFlowNodes([flow.aggressiveRisk, flow.conservativeRisk, flow.neutralRisk]);

    const segments = [
        renderLiveFlowAnalystLanes(flow),
        analystCount && evidenceVisible ? renderLiveFlowFanInWire(analystCount, "live-flow-wire--analysts-to-evidence", analystGroupNode, flow.evidenceExtractor) : "",
        renderLiveFlowSingle(flow.evidenceExtractor, "live-flow-single--evidence"),
        renderLiveFlowWireIf(evidenceVisible && ledgerVisible, "live-flow-wire--evidence-to-ledger", flow.evidenceExtractor, flow.evidenceLedger),
        renderLiveFlowSingle(flow.evidenceLedger, "live-flow-single--ledger"),
        ledgerVisible && researcherCount ? renderLiveFlowFanOutWire(researcherCount, "live-flow-wire--ledger-to-researchers", flow.evidenceLedger, researcherGroupNode) : "",
        renderLiveFlowRow([flow.bullResearcher, flow.bearResearcher], "live-flow-row--researchers"),
        researcherCount && researchDebateVisible ? renderLiveFlowFanInWire(researcherCount, "live-flow-wire--research-to-debate", researcherGroupNode, flow.researchDebate) : "",
        renderLiveFlowSingle(flow.researchDebate, "live-flow-single--debate"),
        researchDebateVisible && riskCount ? renderLiveFlowFanOutWire(riskCount, "live-flow-wire--research-to-risk", flow.researchDebate, riskGroupNode) : "",
        renderLiveFlowRow([flow.aggressiveRisk, flow.conservativeRisk, flow.neutralRisk], "live-flow-row--risk-analysts"),
        riskCount && riskDebateVisible ? renderLiveFlowFanInWire(riskCount, "live-flow-wire--risk-to-debate", riskGroupNode, flow.riskDebate) : "",
        renderLiveFlowSingle(flow.riskDebate, "live-flow-single--risk"),
        renderLiveFlowWireIf(riskDebateVisible && portfolioVisible, "live-flow-wire--risk-to-portfolio", flow.riskDebate, flow.portfolioManager),
        renderLiveFlowSingle(flow.portfolioManager, "live-flow-single--portfolio"),
        renderLiveFlowWireIf(portfolioVisible && verifierVisible, "live-flow-wire--portfolio-to-verifier", flow.portfolioManager, flow.verifier),
        renderLiveFlowSingle(flow.verifier, "live-flow-single--verifier"),
        renderLiveFlowRevisionLoop(flow),
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

