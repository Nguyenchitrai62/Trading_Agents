const state = {
    config: null,
    apiBaseUrl: getConfiguredApiBaseUrl(),
    page: APP_SETTINGS.defaultPage || APP_SETTINGS.default_page || "agent",
    auth: createInitialAuthState(),
    history: createEmptyHistoryState(),
    admin: createEmptyAdminState(),
    chat: createInitialChatState(),
    chart: createInitialChartState(),
    isBusy: false,
    controller: null,
    activeRunId: null,
    stopRequested: false,
    analysisStartedAt: 0,
    stopAvailableAt: 0,
    stopAvailabilityTimer: null,
    activeDetail: null,
    detailBackStack: [],
    renderFrame: null,
    runtimeRenderFrame: null,
    run: createEmptyRunState(),
};

const elements = {
    runStatusBadge: document.getElementById("runStatusBadge"),
    currentAgentText: document.getElementById("currentAgentText"),
    endpointText: document.getElementById("endpointText"),
    topNoticeText: document.getElementById("topNoticeText"),
    pageTabs: document.getElementById("pageTabs"),
    agentPageButton: document.getElementById("agentPageButton"),
    historyPageButton: document.getElementById("historyPageButton"),
    chartPageButton: document.getElementById("chartPageButton"),
    adminPageButton: document.getElementById("adminPageButton"),
    chatPageButton: document.getElementById("chatPageButton"),
    agentPage: document.getElementById("agentPage"),
    historyPage: document.getElementById("historyPage"),
    chartPage: document.getElementById("chartPage"),
    adminPage: document.getElementById("adminPage"),
    chatPage: document.getElementById("chatPage"),
    authStatusText: document.getElementById("authStatusText"),
    googleSignInButton: document.getElementById("googleSignInButton"),
    authProfile: document.getElementById("authProfile"),
    authProfileAvatar: document.getElementById("authProfileAvatar"),
    authProfileInitial: document.getElementById("authProfileInitial"),
    authProfileEmail: document.getElementById("authProfileEmail"),
    signOutButton: document.getElementById("signOutButton"),
    refreshHistoryButton: document.getElementById("refreshHistoryButton"),
    historyList: document.getElementById("historyList"),
    historyDetail: document.getElementById("historyDetail"),
    historyDetailTitle: document.getElementById("historyDetailTitle"),
    historyStatusText: document.getElementById("historyStatusText"),
    chartStatusText: document.getElementById("chartStatusText"),
    tradingViewFrame: document.getElementById("tradingViewFrame"),
    chartSymbolList: document.getElementById("chartSymbolList"),
    chartSymbolForm: document.getElementById("chartSymbolForm"),
    chartSymbolInput: document.getElementById("chartSymbolInput"),
    addChartSymbolButton: document.getElementById("addChartSymbolButton"),
    refreshAdminUsersButton: document.getElementById("refreshAdminUsersButton"),
    adminHistoryPolicyPanel: document.getElementById("adminHistoryPolicyPanel"),
    adminHistoryPublicReadToggle: document.getElementById("adminHistoryPublicReadToggle"),
    saveAdminHistoryPolicyButton: document.getElementById("saveAdminHistoryPolicyButton"),
    adminUserList: document.getElementById("adminUserList"),
    adminStatusText: document.getElementById("adminStatusText"),
    chatNewButton: document.getElementById("chatNewButton"),
    chatHistoryList: document.getElementById("chatHistoryList"),
    chatCurrentTitle: document.getElementById("chatCurrentTitle"),
    chatStatusText: document.getElementById("chatStatusText"),
    chatModelSelect: document.getElementById("chatModelSelect"),
    chatMessages: document.getElementById("chatMessages"),
    chatInput: document.getElementById("chatInput"),
    chatSendButton: document.getElementById("chatSendButton"),
    chatScrollToBottom: document.getElementById("chatScrollToBottom"),
    phaseText: document.getElementById("phaseText"),
    progressText: document.getElementById("progressText"),
    progressFill: document.getElementById("progressFill"),
    progressPercentText: document.getElementById("progressPercentText"),
    elapsedText: document.getElementById("elapsedText"),
    smartNotes: document.getElementById("smartNotes"),
    teamStatusGrid: document.getElementById("teamStatusGrid"),
    reportGrid: document.getElementById("reportGrid"),
    activeReportText: document.getElementById("activeReportText"),
    researchStatusText: document.getElementById("researchStatusText"),
    bullResearchPanel: document.getElementById("bullResearchPanel"),
    bearResearchPanel: document.getElementById("bearResearchPanel"),
    riskStatusText: document.getElementById("riskStatusText"),
    aggressiveRiskPanel: document.getElementById("aggressiveRiskPanel"),
    conservativeRiskPanel: document.getElementById("conservativeRiskPanel"),
    neutralRiskPanel: document.getElementById("neutralRiskPanel"),
    signalBadge: document.getElementById("signalBadge"),
    portfolioDecisionPanel: document.getElementById("portfolioDecisionPanel"),
    executionLog: document.getElementById("executionLog"),
    executionLogStatusText: document.getElementById("executionLogStatusText"),
    opsStatusText: document.getElementById("opsStatusText"),
    opsAgentText: document.getElementById("opsAgentText"),
    opsPhaseText: document.getElementById("opsPhaseText"),
    opsLatestText: document.getElementById("opsLatestText"),
    toolTraceList: document.getElementById("toolTraceList"),
    openConfigButton: document.getElementById("openConfigButton"),
    closeConfigButton: document.getElementById("closeConfigButton"),
    runAnalysisButton: document.getElementById("runAnalysisButton"),
    stopAnalysisButton: document.getElementById("stopAnalysisButton"),
    configModal: document.getElementById("configModal"),
    configForm: document.getElementById("configForm"),
    dashboard: document.querySelector(".dashboard"),
    detailModal: document.getElementById("detailModal"),
    backDetailButton: document.getElementById("backDetailButton"),
    closeDetailButton: document.getElementById("closeDetailButton"),
    detailTitle: document.getElementById("detailTitle"),
    detailSubtitle: document.getElementById("detailSubtitle"),
    detailBody: document.getElementById("detailBody"),
    alertModal: document.getElementById("alertModal"),
    alertTitle: document.getElementById("alertTitle"),
    alertMessage: document.getElementById("alertMessage"),
    closeAlertButton: document.getElementById("closeAlertButton"),
    confirmAlertButton: document.getElementById("confirmAlertButton"),
    saveConfigButton: document.getElementById("saveConfigButton"),
    runFromModalButton: document.getElementById("runFromModalButton"),
    symbolInput: document.getElementById("symbolInput"),
    analysisDateInput: document.getElementById("analysisDateInput"),
    lookbackPresetSelect: document.getElementById("lookbackPresetSelect"),
    lookbackDaysField: document.getElementById("lookbackDaysField"),
    lookbackDaysInput: document.getElementById("lookbackDaysInput"),
    languageInput: document.getElementById("languageInput"),
    reasoningEffortSelect: document.getElementById("reasoningEffortSelect"),
    analystOptions: document.getElementById("analystOptions"),
    depthOptions: document.getElementById("depthOptions"),
    configPreview: document.getElementById("configPreview"),
    modelSelect: document.getElementById("modelSelect"),
};

[elements.configModal, elements.detailModal, elements.alertModal].forEach((modal) => {
    if (modal instanceof HTMLElement && modal.classList.contains("hidden")) {
        modal.setAttribute("inert", "");
    }
});

function renderAll() {
    state.renderFrame = null;
    state.runtimeRenderFrame = null;
    renderPageShell();
    renderAuthState();
    renderHistoryPage();
    renderAdminPage();
    renderChatPage();
    renderChartControls();
    renderTopNotice();
    renderProgress();
    renderTeamStatusGrid();
    renderReportGrid();
    renderOperationsRail();
    renderSmartNotes();
    renderActiveDetail();
}

function renderRuntimePanels() {
    state.runtimeRenderFrame = null;
    renderTopNotice();
    renderProgress();
    renderTeamStatusGrid();
    renderReportGrid();
    renderOperationsRail();
    renderSmartNotes();
    renderActiveDetail();
}

function scheduleRenderAll() {
    if (state.renderFrame !== null) {
        return;
    }
    state.renderFrame = window.requestAnimationFrame(renderAll);
}

function scheduleRuntimeRender() {
    if (state.renderFrame !== null || state.runtimeRenderFrame !== null) {
        return;
    }
    state.runtimeRenderFrame = window.requestAnimationFrame(renderRuntimePanels);
}

function parseSseBlock(block) {
    const lines = block.split(/\r?\n/);
    let event = "message";
    const dataLines = [];

    for (const line of lines) {
        if (!line || line.startsWith(":")) {
            continue;
        }
        if (line.startsWith("event:")) {
            event = line.slice(6).trim();
            continue;
        }
        if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trimStart());
        }
    }

    return {
        event,
        data: dataLines.length ? JSON.parse(dataLines.join("\n")) : {},
    };
}

async function consumeEventStream(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

        let delimiterIndex = buffer.indexOf("\n\n");
        while (delimiterIndex !== -1) {
            const block = buffer.slice(0, delimiterIndex).trim();
            buffer = buffer.slice(delimiterIndex + 2);
            if (block) {
                const parsed = parseSseBlock(block);
                handleServerEvent(parsed.event, parsed.data);
            }
            delimiterIndex = buffer.indexOf("\n\n");
        }

        if (done) {
            break;
        }
    }
}

function handleServerEvent(event, data) {
    const renderSoon = () => scheduleRuntimeRender();

    if (event === "analysis_meta") {
        state.run = createEmptyRunState();
        state.detailBackStack = [];
        state.run.meta = data;
        state.run.status = data.initial_status || null;
        state.run.lastTrackedAgent = data.initial_status?.current_agent || null;
        const depthLabel = data.effective_research_depth && data.effective_research_depth !== data.research_depth
            ? `${data.research_depth}/${data.effective_research_depth}`
            : data.research_depth;
        pushStreamFeed({
            title: "Analysis initialized",
            content: compactText(`${data.symbol} - ${data.asset_type} - ${depthLabel} depth - ${data.model}`),
            tone: "progress",
        });
        renderAll();
        return;
    }

    if (event === "status_snapshot") {
        state.run.status = data;
        state.run.revisionCount = Number(data.decision_revision_count || 0);
        if (data.current_agent && data.current_agent !== state.run.lastTrackedAgent) {
            state.run.lastTrackedAgent = data.current_agent;
            pushStreamFeed({
                title: data.current_agent,
                content: compactText(`${data.phase} phase started.`),
                tone: "progress",
            });
        }
        renderSoon();
        return;
    }

    if (event === "section_update") {
        state.run.sections[data.section] = data.content;
        state.run.latestReportTitle = data.title;
        pushStreamFeed({
            title: data.title,
            content: compactText(`${data.agent} completed. Click the task in Execution Board to review the full output.`),
            tone: "completed",
        });
        renderSoon();
        return;
    }

    if (event === "structured_update") {
        const section = data.section || "";
        if (section) {
            state.run.structured = {
                ...(state.run.structured || {}),
                [section]: data.payload || {},
            };
        }
        state.run.latestReportTitle = data.title || state.run.latestReportTitle;
        pushStreamFeed({
            title: data.title || "Structured payload",
            content: compactText(`${data.agent || "Extractor"} completed structured handoff.`),
            tone: "completed",
        });
        renderSoon();
        return;
    }

    if (event === "debate_update") {
        const patch = data.patch || data.state || {};
        if (data.team === "research") {
            state.run.research = mergeStatePatch(state.run.research, patch);
        } else if (data.team === "risk") {
            state.run.risk = mergeStatePatch(state.run.risk, patch);
        }
        pushStreamFeed({
            title: data.speaker,
            content: compactText(data.content, 260),
            tone: "live",
        });
        renderSoon();
        return;
    }

    if (event === "flow_progress") {
        const completed = Array.isArray(data.completed) ? data.completed : [];
        state.run.flowCompletedSections = state.run.flowCompletedSections || new Set();
        state.run.flowCompletedBlocks = state.run.flowCompletedBlocks || new Set();
        completed.forEach((key) => {
            if (key) {
                state.run.flowCompletedSections.add(key);
            }
        });
        renderSoon();
        return;
    }

    if (event === "endpoint_summary") {
        const items = Array.isArray(data.items) ? data.items : data.summary ? [data.summary] : [];
        state.run.endpointSummaries = items;
        pushStreamFeed({
            title: "Endpoint summaries",
            content: compactText(`${items.length} endpoint summaries prepared for analyst prompts.`),
            tone: "progress",
        });
        renderSoon();
        return;
    }

    if (event === "evidence_update") {
        const items = Array.isArray(data.items) ? data.items : [];
        state.run.evidenceItems = [...(state.run.evidenceItems || []), ...items];
        state.run.evidenceCount = Number(data.count || state.run.evidenceItems.length || 0);
        state.run.sections.structured_evidence = formatEvidenceItemsMarkdown(state.run.evidenceItems);
        pushStreamFeed({
            title: "Evidence Extractor",
            content: compactText(`${state.run.evidenceCount} structured evidence item(s) captured.`),
            tone: "live",
        });
        renderSoon();
        return;
    }

    if (event === "depth_escalation") {
        state.run.depthEscalation = data;
        const fromLabel = data.from_label || `level ${data.from_rounds}`;
        const toLabel = data.to_label || `level ${data.to_rounds}`;
        const roundsDelta = (data.to_rounds || 1) - (data.from_rounds || 1);
        const direction = roundsDelta > 0 ? "escalated" : "reduced";
        pushStreamFeed({
            title: `Depth ${direction}`,
            content: compactText(
                `Auto depth ${direction} from ${fromLabel} (${data.from_rounds}r) → ${toLabel} (${data.to_rounds}r). ${data.reason || ""}`,
                300,
            ),
            tone: roundsDelta > 0 ? "warning" : "live",
        });
        if (state.run.meta) {
            state.run.meta.effective_research_depth = toLabel;
            state.run.meta.depth_rounds = data.to_rounds;
        }
        renderSoon();
        return;
    }

    if (event === "warning") {
        state.run.warnings.unshift(data.message || "Unknown warning");
        pushStreamFeed({
            title: "Warning",
            content: compactText(data.message || data, 220),
            tone: "warning",
        });
        renderSoon();
        return;
    }

    if (event === "verification_revision") {
        state.run.revisionCount = Number(data.revision_count || 0);
        state.run.maxRevisions = Number(data.max_revisions || 2);
        state.run.revisionIssues = Array.isArray(data.issues) ? data.issues : [];
        pushStreamFeed({
            title: "Verifier → Revision",
            content: compactText(data.message || `Revision ${state.run.revisionCount}/${state.run.maxRevisions}: Portfolio Manager is re-evaluating.`, 260),
            tone: "warning",
        });
        renderSoon();
        return;
    }

    if (event === "analysis_log") {
        if (data.phase === "heartbeat") {
            const elapsed = Number(data.elapsed_seconds || 0);
            const lastVisibleHeartbeat = Number(state.run.lastVisibleHeartbeatElapsed || 0);
            if (!lastVisibleHeartbeat || elapsed - lastVisibleHeartbeat >= 10) {
                state.run.lastVisibleHeartbeatElapsed = elapsed;
                const activeAgent = state.run.status?.current_agent || "active analysis step";
                pushStreamFeed({
                    title: activeAgent,
                    content: compactText(`Still processing after ${Math.round(elapsed)}s. Waiting for model response.`, 220),
                    tone: "progress",
                });
            }
        } else {
            pushStreamFeed({
                title: data.phase || "stream",
                content: compactText(data.message || JSON.stringify(data), 220),
                tone: "progress",
            });
        }
        appendLog(data.phase || event, data, { source: "backend" });
        renderSoon();
        return;
    }

    if (event === "agent_trace") {
        pushAgentTrace(data);
        renderSoon();
        return;
    }

    if (event === "complete") {
        state.run.complete = data;
        state.run.cancelled = null;
        if (data.history_id) {
            state.history.loaded = false;
        }
        state.run.sections = { ...state.run.sections, ...(data.sections_patch || data.sections || {}) };
        state.run.flowCompletedSections = state.run.flowCompletedSections || new Set();
        state.run.flowCompletedBlocks = state.run.flowCompletedBlocks || new Set();
        Object.keys(data.sections_patch || data.sections || {}).forEach((key) => {
            if (key) {
                state.run.flowCompletedSections.add(key);
            }
        });
        state.run.research = mergeStatePatch(state.run.research, data.research_patch || data.research || {});
        state.run.risk = mergeStatePatch(state.run.risk, data.risk_patch || data.risk || {});
        state.run.endpointSummaries = data.endpoint_summaries || state.run.endpointSummaries || [];
        state.run.evidenceCount = Number(data.evidence_count || state.run.evidenceCount || 0);
        state.run.sourceArtifactCount = Number(data.source_artifact_count || state.run.sourceArtifactCount || 0);
        state.run.sourceArtifactGroups = data.source_artifact_groups || state.run.sourceArtifactGroups || {};
        state.run.structured = {
            ...(state.run.structured || {}),
            ...(data.structured || {}),
        };
        Object.keys(data.structured || {}).forEach((key) => {
            if (data.structured?.[key] && Object.keys(data.structured[key] || {}).length) {
                state.run.flowCompletedSections.add(`${key}_structured`);
            }
        });
        state.run.status = data.status || state.run.status;
        pushStreamFeed({
            title: "Final Decision",
            content: compactText(`${data.signal || "Completed"}${data.verification_verdict ? ` - ${data.verification_verdict}` : ""} - ${data.elapsed_seconds || 0}s`),
            tone: "completed",
        });
        renderAll();
        return;
    }

    if (event === "cancelled") {
        applyStoppedRunState(data || { message: "Analysis was cancelled." });
        appendLog("cancelled", { ...state.run.cancelled, phase: "cancelled" }, { source: "backend", allowDuplicate: true });
        pushStreamFeed({
            title: "Analysis stopped",
            content: compactText(state.run.cancelled.message || "Analysis was cancelled."),
            tone: "warning",
        });
        renderAll();
        return;
    }

    if (event === "error") {
        state.run.warnings.unshift(data.error || "Unknown error");
        state.run.blockErrors = state.run.blockErrors || {};
        const currentAgent = String(state.run.status?.current_agent || "").toLowerCase();
        const errorBlockKey = currentAgent.includes("market")
            ? "market_analyst"
            : currentAgent.includes("social")
            ? "social_analyst"
            : currentAgent.includes("news")
            ? "news_analyst"
            : currentAgent.includes("onchain")
            ? "onchain_analyst"
            : currentAgent.includes("bull")
            ? "bull_researcher"
            : currentAgent.includes("bear")
            ? "bear_researcher"
            : currentAgent.includes("aggressive")
            ? "aggressive_risk"
            : currentAgent.includes("conservative")
            ? "conservative_risk"
            : currentAgent.includes("neutral")
            ? "neutral_risk"
            : currentAgent.includes("risk")
            ? "risk_debate"
            : currentAgent.includes("portfolio")
            ? "portfolio_manager"
            : currentAgent.includes("verifier")
            ? "verifier"
            : "runtime";
        state.run.blockErrors[errorBlockKey] = data.error || "Unknown error";
        pushStreamFeed({
            title: "Error",
            content: compactText(data.error || data, 220),
            tone: "warning",
        });
        appendLog(event, { log_line: String(data.error || data) }, { source: "backend" });
        renderAll();
        throw new Error(data.error || "Unknown SSE error");
    }
}

function populateLanguageOptions(config) {
    const currentValue = config.analysis_defaults.output_language;
    elements.languageInput.value = currentValue || "vietnamese";
}

function populateReasoningEffortOptions(config) {
    const defaultValue = config.analysis_defaults.reasoning_effort || "max";
    const efforts = config.analysis_options.reasoning_efforts || [
        { value: "low", label: "low" },
        { value: "medium", label: "medium" },
        { value: "high", label: "high" },
        { value: "xhigh", label: "xhigh" },
        { value: "max", label: "max" },
    ];
    if (elements.reasoningEffortSelect instanceof HTMLSelectElement) {
        elements.reasoningEffortSelect.innerHTML = efforts
            .map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`)
            .join("");
        if (efforts.some((item) => item.value === defaultValue)) {
            elements.reasoningEffortSelect.value = defaultValue;
        }
    }
}

function populateLookbackPresets(config) {
    elements.lookbackPresetSelect.innerHTML = (config.analysis_options.lookback_presets || [])
        .map(
            (preset) => `<option value="${escapeHtml(preset.value)}">${escapeHtml(preset.label)}</option>`,
        )
        .concat(`<option value="${CUSTOM_LOOKBACK_VALUE}">Custom</option>`)
        .join("");
}

function populateModelOptions(config) {
    const preferredModel = String(config.analysis_defaults.model || config.default_model || "").trim();
    const configuredModels = Array.isArray(config.analysis_options.models) ? config.analysis_options.models : [];
    const options = configuredModels
        .map((item) => {
            if (typeof item === "string") {
                return { value: item, label: item };
            }
            return {
                value: String(item?.value || item?.label || "").trim(),
                label: String(item?.label || item?.value || "").trim(),
            };
        })
        .filter((item) => item.value && item.label);

    if (preferredModel && !options.some((item) => item.value === preferredModel)) {
        options.unshift({ value: preferredModel, label: preferredModel });
    }

    const optionMarkup = options
        .map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`)
        .join("");

    if (elements.modelSelect instanceof HTMLSelectElement) {
        elements.modelSelect.innerHTML = optionMarkup;
        if (preferredModel) {
            elements.modelSelect.value = preferredModel;
        }
    }

    if (elements.chatModelSelect instanceof HTMLSelectElement) {
        elements.chatModelSelect.innerHTML = optionMarkup;
        if (preferredModel) {
            elements.chatModelSelect.value = preferredModel;
        }
    }
}

function populateAnalystOptions(config) {
    const defaults = new Set(config.analysis_defaults.selected_analysts);
    elements.analystOptions.innerHTML = config.analysis_options.analysts
        .map(
            (analyst) => `
                <label class="checkbox-card">
                    <input type="checkbox" value="${escapeHtml(analyst.value)}" ${defaults.has(analyst.value) ? "checked" : ""}>
                    <span>${escapeHtml(analyst.label)}</span>
                </label>
            `,
        )
        .join("");
}

function populateDepthOptions(config) {
    const current = config.analysis_defaults.research_depth;
    elements.depthOptions.innerHTML = config.analysis_options.research_depths
        .map(
            (depth) => `
                <label class="depth-card" title="${escapeHtml(depth.description)}">
                    <input type="radio" name="researchDepth" value="${escapeHtml(depth.value)}" ${depth.value === current ? "checked" : ""}>
                    <span class="depth-title">${escapeHtml(depth.label)}</span>
                    <small>${escapeHtml(compactText(depth.description, 52))}</small>
                </label>
            `,
        )
        .join("");
}

function bindConfigInputListeners() {
    const sync = () => refreshConfigUi();
    [
        elements.symbolInput,
        elements.analysisDateInput,
        elements.lookbackDaysInput,
        elements.languageInput,
    ].filter(Boolean).forEach((element) => element.addEventListener("input", sync));
    elements.lookbackPresetSelect.addEventListener("change", () => {
        if (elements.lookbackPresetSelect.value !== CUSTOM_LOOKBACK_VALUE) {
            elements.lookbackDaysInput.value = elements.lookbackPresetSelect.value;
        } else if (!elements.lookbackDaysInput.value) {
            elements.lookbackDaysInput.value = state.config?.analysis_defaults?.lookback_days || 7;
        }
        refreshConfigUi();
        if (elements.lookbackPresetSelect.value === CUSTOM_LOOKBACK_VALUE) {
            elements.lookbackDaysInput.focus();
        }
    });
    elements.languageInput.addEventListener("input", () => {
        refreshConfigUi();
    });
    elements.reasoningEffortSelect?.addEventListener("change", sync);
    elements.modelSelect?.addEventListener("change", sync);
    elements.analystOptions.addEventListener("change", sync);
    elements.depthOptions.addEventListener("change", sync);
}

async function loadConfig() {
    let config = normalizeFrontendConfig();
    state.config = config;
    state.admin.historyPublicRead = Boolean(config.history?.public_read ?? false);
    state.apiBaseUrl = normalizeApiBaseUrl(config.api_base_url || state.apiBaseUrl);
    const backendConfig = await loadBackendPublicConfig();
    if (backendConfig) {
        config = mergeBackendConfig(config, backendConfig);
        state.config = config;
        state.admin.historyPublicRead = Boolean(config.history?.public_read ?? false);
    }
    initializeChartFromConfig(config);

    elements.symbolInput.value = config.analysis_defaults.symbol;
    elements.analysisDateInput.value = config.analysis_defaults.analysis_date;
    populateLookbackPresets(config);
    elements.lookbackDaysInput.value = config.analysis_defaults.lookback_days;
    populateLanguageOptions(config);
    populateReasoningEffortOptions(config);
    populateModelOptions(config);
    populateAnalystOptions(config);
    populateDepthOptions(config);
    bindConfigInputListeners();
    initializeGoogleAuth();
    refreshConfigUi();
    renderAll();
}

async function runAnalysis() {
    if (!state.config) {
        return;
    }

    const payload = readConfigForm();
    if (!payload.symbol || !payload.model) {
        throw new Error("Symbol and model are required.");
    }

    if (state.isBusy) {
        return;
    }

    await ensureCanRunAnalysis();

    const runId = createRunId();
    const controller = new AbortController();
    payload.run_id = runId;

    state.run = createEmptyRunState();
    state.run.logs = [];
    state.controller = controller;
    state.activeRunId = runId;
    state.stopRequested = false;
    state.analysisStartedAt = Date.now();
    state.stopAvailableAt = state.analysisStartedAt + MIN_ANALYSIS_STOP_DELAY_MS;
    setBusy(true);
    renderAll();

    try {
        const response = await apiFetch("/api/analyze", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getAuthHeaders(),
            },
            body: JSON.stringify(payload),
            signal: controller.signal,
        });

        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }

        await consumeEventStream(response);
        if (!state.run.complete && !state.run.cancelled && !state.stopRequested) {
            throw new Error("Backend stream closed before the analysis completed. The server may have restarted, timed out, or lost network connectivity.");
        }
    } catch (error) {
        if (state.stopRequested || isAbortError(error)) {
            applyStoppedRunState(state.run.cancelled || {
                run_id: runId,
                message: "Analysis stopped from the frontend.",
            });
            appendLog(
                "cancelled",
                {
                    phase: "cancelled",
                    message: state.run.cancelled.message,
                    log_line: `analysis run_id=${runId} phase=cancelled message=${state.run.cancelled.message}`,
                },
                { source: "frontend", allowDuplicate: true },
            );
            return;
        }
        if (error instanceof Error) {
            error.runId = runId;
        }
        throw error;
    } finally {
        state.controller = null;
        state.activeRunId = null;
        state.stopRequested = false;
        setBusy(false);
        renderAll();
    }
}

function stopActiveAnalysis() {
    if (!state.isBusy) {
        return;
    }
    if (getStopDelayRemainingMs() > 0) {
        updateActionAvailability();
        return;
    }
    const runId = state.activeRunId;
    const message = "Stop requested from the frontend.";
    state.stopRequested = true;
    applyStoppedRunState({ run_id: runId, message });
    appendLog(
        "cancelled",
        {
            phase: "cancelled",
            message,
            log_line: `analysis run_id=${runId || "unknown"} phase=cancelled message=${message}`,
        },
        { source: "frontend", allowDuplicate: true },
    );
    pushStreamFeed({
        title: "Stop requested",
        content: message,
        tone: "warning",
    });
    renderAll();
    requestBackendCancel(runId);
    state.controller?.abort();
}

elements.openConfigButton.addEventListener("click", openConfigModal);
elements.closeConfigButton.addEventListener("click", closeConfigModal);
elements.stopAnalysisButton.addEventListener("click", stopActiveAnalysis);
elements.signOutButton.addEventListener("click", clearAuthState);
elements.pageTabs.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const button = target.closest("[data-page]");
    if (button instanceof HTMLElement) {
        switchPage(button.dataset.page || "agent");
    }
});
elements.adminPageButton.addEventListener("click", () => switchPage("admin"));
elements.chatPageButton?.addEventListener("click", () => switchPage("chat"));
elements.refreshHistoryButton.addEventListener("click", () => {
    if (!state.auth.idToken && !state.auth.isAuthorized) {
        openAuthRequiredAlert();
        return;
    }
    state.history = { ...createEmptyHistoryState(), activeId: state.history.activeId };
    triggerHistoryListReload("Could not refresh history.");
});
elements.historyList.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const pageNavButton = target.closest("[data-history-page-nav]");
    if (pageNavButton instanceof HTMLElement) {
        const direction = pageNavButton.dataset.historyPageNav;
        if (direction === "prev") {
            setHistoryPage(Math.max(1, state.history.page - 1));
        } else if (direction === "next") {
            setHistoryPage(Math.min(state.history.totalPages || state.history.page + 1, state.history.page + 1));
        }
        return;
    }
    const pageTargetButton = target.closest("[data-history-page-target]");
    if (pageTargetButton instanceof HTMLElement) {
        setHistoryPage(Number(pageTargetButton.dataset.historyPageTarget || state.history.page));
        return;
    }
    const historyRow = target.closest("[data-history-row-id]");
    if (historyRow instanceof HTMLElement) {
        loadHistoryDetail(historyRow.dataset.historyRowId).catch((error) => {
            state.history.error = error instanceof Error ? error.message : String(error || "Could not load history detail.");
            renderHistoryPage();
        });
    }
});
elements.historyList.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
        return;
    }
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const historyRow = target.closest("[data-history-row-id]");
    if (historyRow instanceof HTMLElement) {
        event.preventDefault();
        loadHistoryDetail(historyRow.dataset.historyRowId).catch((error) => {
            state.history.error = error instanceof Error ? error.message : String(error || "Could not load history detail.");
            renderHistoryPage();
        });
    }
});
elements.historyDetail.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const sectionButton = target.closest("[data-history-section-key]");
    if (sectionButton instanceof HTMLElement) {
        loadHistorySection(state.history.activeId, sectionButton.dataset.historySectionKey || "", { openModal: true }).catch((error) => {
            state.history.error = error instanceof Error ? error.message : String(error || "Could not load history section.");
            renderHistoryPage();
        });
    }
});
elements.chartSymbolList.addEventListener("click", (event) => {
    if (state.chart.suppressNextSymbolClick) {
        state.chart.suppressNextSymbolClick = false;
        event.preventDefault();
        return;
    }
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const removeButton = target.closest("[data-chart-symbol-remove]");
    if (removeButton instanceof HTMLElement) {
        removeChartSymbol(removeButton.dataset.chartSymbolRemove || "");
        return;
    }
    const button = target.closest("[data-chart-symbol]");
    if (button instanceof HTMLElement) {
        setChartSymbol(button.dataset.chartSymbol || "");
    }
});
elements.chartSymbolList.addEventListener("pointerdown", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement) || event.button !== 0) {
        return;
    }
    if (target.closest("[data-chart-symbol-remove]")) {
        return;
    }
    const item = target.closest("[data-chart-symbol-item]");
    if (!(item instanceof HTMLElement)) {
        return;
    }
    beginChartPointerDrag(item.dataset.chartSymbolItem || "", event);
});
elements.chartSymbolList.addEventListener("mousedown", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement) || event.button !== 0) {
        return;
    }
    if (target.closest("[data-chart-symbol-remove]")) {
        return;
    }
    const item = target.closest("[data-chart-symbol-item]");
    if (!(item instanceof HTMLElement)) {
        return;
    }
    beginChartPointerDrag(item.dataset.chartSymbolItem || "", event);
});
elements.chartSymbolList.addEventListener("dragstart", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const item = target.closest("[data-chart-symbol-item]");
    if (!(item instanceof HTMLElement)) {
        return;
    }
    state.chart.draggingSymbol = item.dataset.chartSymbolItem || "";
    state.chart.dragOriginalSymbols = [...state.chart.symbols];
    state.chart.dragCommitted = false;
    elements.chartSymbolList.classList.add("is-dragging");
    item.classList.add("is-dragging");
    if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", state.chart.draggingSymbol);
    }
});
elements.chartSymbolList.addEventListener("dragover", (event) => {
    updateChartSymbolDragPosition(event);
});
elements.chartSymbolList.addEventListener("drop", (event) => {
    commitChartSymbolDrag(event);
});
elements.chartSymbolList.addEventListener("drag", (event) => {
    updateChartSymbolDragPosition(event);
});
elements.chartSymbolList.addEventListener("dragend", () => {
    if (state.chart.draggingSymbol) {
        finalizeChartSymbolDrag(state.chart.dragCommitted);
    }
});
document.addEventListener("dragover", (event) => {
    updateChartSymbolDragPosition(event);
});
document.addEventListener("drop", (event) => {
    commitChartSymbolDrag(event);
});
document.addEventListener("pointermove", (event) => {
    updateChartPointerDrag(event);
});
document.addEventListener("pointerup", () => {
    finishChartPointerDrag(true);
});
document.addEventListener("pointercancel", () => {
    finishChartPointerDrag(false);
});
document.addEventListener("mousemove", (event) => {
    updateChartPointerDrag(event);
});
document.addEventListener("mouseup", () => {
    finishChartPointerDrag(true);
});
elements.chartSymbolForm.addEventListener("submit", (event) => {
    event.preventDefault();
    addChartSymbolFromInput();
});
elements.refreshAdminUsersButton.addEventListener("click", () => {
    state.admin.loaded = false;
    loadAdminUsers(true).catch((error) => {
        state.admin.error = error instanceof Error ? error.message : String(error || "Could not refresh users.");
        renderAdminPage();
    });
});
elements.saveAdminHistoryPolicyButton?.addEventListener("click", () => {
    saveAdminHistoryAccessPolicy().catch((error) => {
        state.admin.error = error instanceof Error ? error.message : String(error || "Could not save history access policy.");
        renderAdminPage();
    });
});
elements.adminUserList.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
        return;
    }
    const card = target.closest("[data-admin-email]");
    if (!(card instanceof HTMLElement)) {
        return;
    }
    syncAdminCardControls(card);
});
elements.adminUserList.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const saveButton = target.closest("[data-admin-save-user]");
    if (saveButton instanceof HTMLElement) {
        saveAdminUser(saveButton.dataset.adminSaveUser || "");
    }
});
elements.chatNewButton?.addEventListener("click", () => {
    createNewChatSession();
});
elements.chatHistoryList?.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const button = target.closest("[data-chat-session-id]");
    if (button instanceof HTMLElement) {
        selectChatSession(button.dataset.chatSessionId || "");
    }
});
elements.chatMessages?.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const button = target.closest("[data-chat-thinking-toggle]");
    if (button instanceof HTMLElement) {
        toggleThinkingMessage(button.dataset.chatThinkingToggle || "");
    }
});
elements.chatMessages?.addEventListener("scroll", () => {
    if (!(elements.chatMessages instanceof HTMLElement)) {
        return;
    }
    const remaining = elements.chatMessages.scrollHeight - elements.chatMessages.scrollTop - elements.chatMessages.clientHeight;
    state.chat.shouldAutoScroll = remaining < 100;
});
[elements.executionLog, elements.toolTraceList].forEach((logElement) => {
    if (!(logElement instanceof HTMLElement)) {
        return;
    }
    logElement.addEventListener("scroll", () => {
        syncLogAutoScrollPreference(logElement);
    });
    syncLogAutoScrollPreference(logElement);
});
elements.chatScrollToBottom?.addEventListener("click", () => {
    state.chat.shouldAutoScroll = true;
    scrollChatToBottom(true);
});
elements.chatInput?.addEventListener("input", () => {
    if (!(elements.chatInput instanceof HTMLTextAreaElement)) {
        return;
    }
    elements.chatInput.style.height = "auto";
    elements.chatInput.style.height = `${elements.chatInput.scrollHeight}px`;
    updateChatComposerState();
});
elements.chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendChatMessage().catch((error) => {
            const message = error instanceof Error ? error.message : String(error || "Chat failed.");
            openBackendIssueAlert(message);
        });
    }
});
elements.chatSendButton?.addEventListener("click", () => {
    sendChatMessage().catch((error) => {
        const message = error instanceof Error ? error.message : String(error || "Chat failed.");
        openBackendIssueAlert(message);
    });
});
elements.runAnalysisButton.addEventListener("click", async () => {
    if (state.isBusy) {
        stopActiveAnalysis();
        return;
    }
    try {
        await runAnalysis();
    } catch (error) {
        handleRunFailure(error);
    }
});
elements.saveConfigButton.addEventListener("click", () => {
    refreshConfigUi();
    closeConfigModal();
});
elements.configForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    closeConfigModal();
    try {
        await runAnalysis();
    } catch (error) {
        handleRunFailure(error);
    }
});
elements.configModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.closeModal === "true") {
        closeConfigModal();
    }
});
elements.backDetailButton?.addEventListener("click", goBackDetailModal);
elements.closeDetailButton.addEventListener("click", closeDetailModal);
elements.closeAlertButton.addEventListener("click", closeAlertModal);
elements.confirmAlertButton.addEventListener("click", closeAlertModal);
elements.detailModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.closeDetail === "true") {
        closeDetailModal();
        return;
    }
    if (!(target instanceof HTMLElement)) {
        return;
    }
    const sourceButton = target.closest("[data-source-detail-kind]");
    if (!(sourceButton instanceof HTMLElement)) {
        return;
    }
    const detailKind = sourceButton.dataset.sourceDetailKind || "";
    if (detailKind === "trace") {
        const traceId = sourceButton.dataset.sourceDetailId || "";
        const entry = getTraceEntryById(traceId);
        if (entry) {
            openDetailModal({
                type: "trace",
                traceId,
                title: `${entry.agent || "Agent"} - ${formatTracePhaseLabel(entry.phase)}`,
                subtitle: entry.title || "Trace detail",
                mode: "markdown",
            });
        }
        return;
    }
    if (detailKind === "saved") {
        openSavedSourceArtifactDetail(
            sourceButton.dataset.sourceDetailRunId || "",
            sourceButton.dataset.sourceDetailSectionKey || sourceButton.dataset.sourceDetailId || "",
        ).catch((error) => {
            openDetailModal({
                type: "source-artifact",
                title: "Source Artifact",
                subtitle: "Load failed",
                content: "",
                fallback: error instanceof Error ? error.message : String(error || "Could not load source artifact."),
                mode: "markdown",
            }, { pushHistory: false });
        });
    }
});
elements.alertModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.closeAlert === "true") {
        closeAlertModal();
    }
});
elements.dashboard.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
        return;
    }
    if (target.closest("a")) {
        return;
    }
    const trigger = target.closest(".detail-trigger");
    if (trigger instanceof HTMLElement && elements.dashboard.contains(trigger)) {
        openDetailFromTrigger(trigger);
    }
});
elements.dashboard.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
        return;
    }
    const target = event.target;
    if (target instanceof HTMLElement && target.classList.contains("detail-trigger")) {
        event.preventDefault();
        openDetailFromTrigger(target);
    }
});
window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.alertModal.classList.contains("hidden")) {
        closeAlertModal();
        return;
    }
    if (event.key === "Escape" && !elements.detailModal.classList.contains("hidden")) {
        closeDetailModal();
        return;
    }
    if (event.key === "Escape" && !elements.configModal.classList.contains("hidden")) {
        closeConfigModal();
    }
});

window.addEventListener("message", handleTradingViewWidgetMessage);

window.addEventListener("beforeunload", () => {
    if (!state.isBusy) {
        return;
    }
    requestBackendCancel(state.activeRunId);
    state.controller?.abort();
});

loadConfig().catch((error) => {
    appendLog("config-error", error instanceof Error ? error.message : String(error));
    state.run.warnings.unshift(error instanceof Error ? error.message : String(error));
    renderAll();
});
