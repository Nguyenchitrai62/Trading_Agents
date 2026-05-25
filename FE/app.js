const GROUP_LABELS = {
    analysts: "Analyst Team",
    research: "Research Team",
    trading: "Trading Team",
    risk: "Risk Management",
    portfolio: "Portfolio Management",
};

const REPORT_BY_ANALYST = {
    market: { section: "market_report", title: "Market Analysis" },
    social: { section: "sentiment_report", title: "Sentiment Analysis" },
    news: { section: "news_report", title: "News Analysis" },
    fundamentals: { section: "fundamentals_report", title: "Fundamentals Analysis" },
};

const state = {
    config: null,
    isBusy: false,
    controller: null,
    run: createEmptyRunState(),
};

const elements = {
    runStatusBadge: document.getElementById("runStatusBadge"),
    currentAgentText: document.getElementById("currentAgentText"),
    endpointText: document.getElementById("endpointText"),
    summaryChips: document.getElementById("summaryChips"),
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
    researchManagerPanel: document.getElementById("researchManagerPanel"),
    traderPlanPanel: document.getElementById("traderPlanPanel"),
    riskStatusText: document.getElementById("riskStatusText"),
    aggressiveRiskPanel: document.getElementById("aggressiveRiskPanel"),
    conservativeRiskPanel: document.getElementById("conservativeRiskPanel"),
    neutralRiskPanel: document.getElementById("neutralRiskPanel"),
    signalBadge: document.getElementById("signalBadge"),
    portfolioDecisionPanel: document.getElementById("portfolioDecisionPanel"),
    eventLog: document.getElementById("eventLog"),
    openConfigButton: document.getElementById("openConfigButton"),
    closeConfigButton: document.getElementById("closeConfigButton"),
    runAnalysisButton: document.getElementById("runAnalysisButton"),
    configModal: document.getElementById("configModal"),
    configForm: document.getElementById("configForm"),
    saveConfigButton: document.getElementById("saveConfigButton"),
    runFromModalButton: document.getElementById("runFromModalButton"),
    symbolInput: document.getElementById("symbolInput"),
    analysisDateInput: document.getElementById("analysisDateInput"),
    languageSelect: document.getElementById("languageSelect"),
    customLanguageField: document.getElementById("customLanguageField"),
    customLanguageInput: document.getElementById("customLanguageInput"),
    analystOptions: document.getElementById("analystOptions"),
    depthOptions: document.getElementById("depthOptions"),
    modelInput: document.getElementById("modelInput"),
    checkpointToggle: document.getElementById("checkpointToggle"),
};

function createEmptyRunState() {
    return {
        meta: null,
        status: null,
        sections: {},
        research: {},
        risk: {},
        complete: null,
        warnings: [],
        logs: [],
        latestReportTitle: null,
    };
}

function escapeHtml(value = "") {
    return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function formatBlock(content, fallback = "No content yet.") {
    return escapeHtml(content && content.trim() ? content : fallback);
}

function appendLog(label, payload) {
    const timestamp = new Date().toLocaleTimeString();
    const text = typeof payload === "string" ? payload : JSON.stringify(payload);
    state.run.logs.unshift(`[${timestamp}] ${label}: ${text}`);
    state.run.logs = state.run.logs.slice(0, 120);
    elements.eventLog.textContent = state.run.logs.join("\n");
}

function setBusy(isBusy) {
    state.isBusy = isBusy;
    elements.runAnalysisButton.disabled = isBusy;
    elements.runFromModalButton.disabled = isBusy;
    elements.saveConfigButton.disabled = isBusy;
    elements.openConfigButton.disabled = isBusy;
}

function openConfigModal() {
    elements.configModal.classList.remove("hidden");
    elements.configModal.setAttribute("aria-hidden", "false");
}

function closeConfigModal() {
    elements.configModal.classList.add("hidden");
    elements.configModal.setAttribute("aria-hidden", "true");
}

function getCheckedAnalysts() {
    return Array.from(elements.analystOptions.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
}

function getSelectedDepth() {
    const checked = elements.depthOptions.querySelector('input[name="researchDepth"]:checked');
    return checked ? checked.value : "medium";
}

function getOutputLanguage() {
    if (elements.languageSelect.value === "__custom__") {
        return elements.customLanguageInput.value.trim();
    }
    return elements.languageSelect.value;
}

function readConfigForm() {
    const selectedAnalysts = getCheckedAnalysts();
    if (selectedAnalysts.length === 0) {
        throw new Error("Select at least one analyst.");
    }

    const outputLanguage = getOutputLanguage();
    if (!outputLanguage) {
        throw new Error("Output language is required.");
    }

    return {
        symbol: elements.symbolInput.value.trim().toUpperCase(),
        analysis_date: elements.analysisDateInput.value,
        output_language: outputLanguage,
        selected_analysts: selectedAnalysts,
        research_depth: getSelectedDepth(),
        model: elements.modelInput.value.trim(),
        checkpoint_enabled: elements.checkpointToggle.checked,
    };
}

function syncLanguageControls() {
    const isCustom = elements.languageSelect.value === "__custom__";
    elements.customLanguageField.classList.toggle("hidden", !isCustom);
}

function renderSummaryChips() {
    if (!state.config) {
        elements.summaryChips.innerHTML = "";
        return;
    }

    let payload;
    try {
        payload = readConfigForm();
    } catch {
        payload = {
            symbol: state.config.analysis_defaults.symbol,
            analysis_date: state.config.analysis_defaults.analysis_date,
            output_language: state.config.analysis_defaults.output_language,
            selected_analysts: state.config.analysis_defaults.selected_analysts,
            research_depth: state.config.analysis_defaults.research_depth,
            model: state.config.analysis_defaults.model,
        };
    }

    const analystLabelMap = Object.fromEntries(
        state.config.analysis_options.analysts.map((item) => [item.value, item.label]),
    );
    const depthMap = Object.fromEntries(
        state.config.analysis_options.research_depths.map((item) => [item.value, item.label]),
    );
    const chips = [
        `Symbol: ${payload.symbol || "-"}`,
        `Date: ${payload.analysis_date || "-"}`,
        `Language: ${payload.output_language || "-"}`,
        `Depth: ${depthMap[payload.research_depth] || payload.research_depth}`,
        `Model: ${payload.model || "-"}`,
        `Analysts: ${payload.selected_analysts.map((key) => analystLabelMap[key] || key).join(", ")}`,
    ];

    elements.summaryChips.innerHTML = chips
        .map((chip) => `<span class="chip">${escapeHtml(chip)}</span>`)
        .join("");
}

function renderTeamStatusGrid() {
    const fallbackAnalysts = state.config?.analysis_defaults?.selected_analysts || [];
    const groups = state.run.status?.groups || {
        analysts: fallbackAnalysts.map((key) => ({
            key,
            label: REPORT_BY_ANALYST[key]?.title?.replace(" Analysis", " Analyst") || key,
            status: "pending",
        })),
        research: [
            { key: "bull", label: "Bull Researcher", status: "pending" },
            { key: "bear", label: "Bear Researcher", status: "pending" },
            { key: "manager", label: "Research Manager", status: "pending" },
        ],
        trading: [{ key: "trader", label: "Trader", status: "pending" }],
        risk: [
            { key: "aggressive", label: "Aggressive Analyst", status: "pending" },
            { key: "conservative", label: "Conservative Analyst", status: "pending" },
            { key: "neutral", label: "Neutral Analyst", status: "pending" },
        ],
        portfolio: [{ key: "portfolio", label: "Portfolio Manager", status: "pending" }],
    };

    elements.teamStatusGrid.innerHTML = Object.entries(groups)
        .map(([groupKey, items]) => `
            <section class="status-cluster">
                <header>
                    <h3>${escapeHtml(GROUP_LABELS[groupKey] || groupKey)}</h3>
                </header>
                <div class="status-card-list">
                    ${items
                        .map(
                            (item) => `
                                <article class="status-card status-${item.status}">
                                    <span class="status-label">${escapeHtml(item.label)}</span>
                                    <strong>${escapeHtml(item.status.replaceAll("_", " "))}</strong>
                                </article>
                            `,
                        )
                        .join("")}
                </div>
            </section>
        `)
        .join("");
}

function renderProgress() {
    const progress = state.run.status?.progress || { completed: 0, total: 0, percent: 0 };
    elements.progressText.textContent = `${progress.completed} / ${progress.total}`;
    elements.progressPercentText.textContent = `${progress.percent || 0}%`;
    elements.progressFill.style.width = `${progress.percent || 0}%`;
    elements.phaseText.textContent = state.run.status?.phase || "idle";
    elements.currentAgentText.textContent = state.run.status?.current_agent || "Waiting";
    elements.runStatusBadge.textContent = state.isBusy
        ? "Running"
        : state.run.complete
        ? "Completed"
        : state.run.warnings.length
        ? "Attention"
        : "Idle";
    if (state.run.complete?.elapsed_seconds) {
        elements.elapsedText.textContent = `${state.run.complete.elapsed_seconds} s total`;
    } else {
        elements.elapsedText.textContent = state.isBusy ? "Live stream active" : "Awaiting run";
    }
}

function renderReportGrid() {
    const selectedAnalysts = state.run.meta?.selected_analysts || state.config?.analysis_defaults?.selected_analysts || [];
    const analystOptions = Object.fromEntries(
        (state.config?.analysis_options?.analysts || []).map((item) => [item.value, item.label]),
    );

    elements.reportGrid.innerHTML = selectedAnalysts
        .map((key) => {
            const report = REPORT_BY_ANALYST[key];
            const content = state.run.sections[report.section] || "";
            return `
                <article class="report-card ${state.run.latestReportTitle === report.title ? "report-card-active" : ""}">
                    <header>
                        <h3>${escapeHtml(analystOptions[key] || report.title)}</h3>
                        <span>${escapeHtml(report.title)}</span>
                    </header>
                    <pre>${formatBlock(content, "Report chưa có dữ liệu. Khi agent hoàn thành, phần này sẽ được cập nhật ngay.")}</pre>
                </article>
            `;
        })
        .join("");

    elements.activeReportText.textContent = state.run.latestReportTitle || "No reports yet";
}

function renderResearchRoom() {
    const research = state.run.research || {};
    elements.bullResearchPanel.textContent = research.bull_history || "Bull Researcher chưa phát biểu.";
    elements.bearResearchPanel.textContent = research.bear_history || "Bear Researcher chưa phản biện.";
    elements.researchManagerPanel.textContent =
        state.run.sections.investment_plan || research.judge_decision || "Research Manager chưa tổng hợp kế hoạch.";

    elements.researchStatusText.textContent = state.run.sections.investment_plan
        ? "Investment plan ready"
        : research.history
        ? "Debate in progress"
        : "Awaiting analyst reports";
}

function renderTraderDesk() {
    elements.traderPlanPanel.textContent =
        state.run.sections.trader_investment_plan || "Trader chưa đưa ra transaction proposal.";
}

function renderRiskRoom() {
    const risk = state.run.risk || {};
    elements.aggressiveRiskPanel.textContent = risk.aggressive_history || "Aggressive Analyst chưa có lập luận.";
    elements.conservativeRiskPanel.textContent = risk.conservative_history || "Conservative Analyst chưa có lập luận.";
    elements.neutralRiskPanel.textContent = risk.neutral_history || "Neutral Analyst chưa có lập luận.";
    elements.riskStatusText.textContent = state.run.sections.final_trade_decision
        ? "Risk loop completed"
        : risk.history
        ? "Risk debate live"
        : "Waiting for trader";
}

function renderFinalDecision() {
    const decision = state.run.sections.final_trade_decision || "Portfolio Manager chưa chốt quyết định.";
    elements.portfolioDecisionPanel.textContent = decision;
    elements.signalBadge.textContent = state.run.complete?.signal || "No signal";
}

function renderSmartNotes() {
    const notes = [];
    if (state.run.meta) {
        notes.push(`Asset type: ${state.run.meta.asset_type}`);
        notes.push(`Depth preset: ${state.run.meta.research_depth} (${state.run.meta.depth_rounds} rounds)`);
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
        notes.push("Mở Config để chỉnh symbol/date/language/analysts/depth rồi bấm Run analysis.");
    }

    elements.smartNotes.innerHTML = notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");
}

function renderAll() {
    renderSummaryChips();
    renderProgress();
    renderTeamStatusGrid();
    renderReportGrid();
    renderResearchRoom();
    renderTraderDesk();
    renderRiskRoom();
    renderFinalDecision();
    renderSmartNotes();
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
    if (event === "analysis_meta") {
        state.run = createEmptyRunState();
        state.run.meta = data;
        state.run.status = data.initial_status || null;
        appendLog(event, data);
        renderAll();
        return;
    }

    if (event === "status_snapshot") {
        state.run.status = data;
        renderAll();
        return;
    }

    if (event === "section_update") {
        state.run.sections[data.section] = data.content;
        state.run.latestReportTitle = data.title;
        appendLog(`${data.agent}`, data.title);
        renderAll();
        return;
    }

    if (event === "debate_update") {
        if (data.team === "research") {
            state.run.research = data.state || {};
        } else if (data.team === "risk") {
            state.run.risk = data.state || {};
        }
        appendLog(`${data.team}-${data.speaker}`, "updated");
        renderAll();
        return;
    }

    if (event === "warning") {
        state.run.warnings.unshift(data.message || "Unknown warning");
        appendLog(event, data.message || data);
        renderAll();
        return;
    }

    if (event === "complete") {
        state.run.complete = data;
        state.run.sections = { ...state.run.sections, ...(data.sections || {}) };
        state.run.research = data.research || state.run.research;
        state.run.risk = data.risk || state.run.risk;
        state.run.status = data.status || state.run.status;
        appendLog(event, { signal: data.signal, elapsed_seconds: data.elapsed_seconds });
        renderAll();
        return;
    }

    if (event === "error") {
        state.run.warnings.unshift(data.error || "Unknown error");
        appendLog(event, data.error || data);
        renderAll();
        throw new Error(data.error || "Unknown SSE error");
    }

    appendLog(event, data);
}

function populateLanguageOptions(config) {
    const currentValue = config.analysis_defaults.output_language;
    const knownLanguages = config.analysis_options.output_languages;
    elements.languageSelect.innerHTML = knownLanguages
        .map((language) => `<option value="${escapeHtml(language)}">${escapeHtml(language)}</option>`)
        .concat('<option value="__custom__">Custom</option>')
        .join("");

    if (knownLanguages.includes(currentValue)) {
        elements.languageSelect.value = currentValue;
        elements.customLanguageInput.value = "";
    } else {
        elements.languageSelect.value = "__custom__";
        elements.customLanguageInput.value = currentValue;
    }

    syncLanguageControls();
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
                <label class="depth-card">
                    <input type="radio" name="researchDepth" value="${escapeHtml(depth.value)}" ${depth.value === current ? "checked" : ""}>
                    <span class="depth-title">${escapeHtml(depth.label)}</span>
                    <small>${escapeHtml(depth.description)}</small>
                </label>
            `,
        )
        .join("");
}

function bindConfigInputListeners() {
    const sync = () => renderSummaryChips();
    [
        elements.symbolInput,
        elements.analysisDateInput,
        elements.modelInput,
        elements.customLanguageInput,
        elements.checkpointToggle,
        elements.languageSelect,
    ].forEach((element) => element.addEventListener("input", sync));
    elements.languageSelect.addEventListener("change", () => {
        syncLanguageControls();
        renderSummaryChips();
    });
    elements.analystOptions.addEventListener("change", sync);
    elements.depthOptions.addEventListener("change", sync);
}

async function loadConfig() {
    const response = await fetch("/api/config");
    if (!response.ok) {
        throw new Error(`Failed to load config: ${response.status}`);
    }
    const config = await response.json();
    state.config = config;

    elements.endpointText.textContent = `${config.provider || "minimax"} • ${config.base_url || "Unknown"}`;
    elements.symbolInput.value = config.analysis_defaults.symbol;
    elements.analysisDateInput.value = config.analysis_defaults.analysis_date;
    elements.modelInput.value = config.analysis_defaults.model;
    elements.checkpointToggle.checked = Boolean(config.analysis_defaults.checkpoint_enabled);
    populateLanguageOptions(config);
    populateAnalystOptions(config);
    populateDepthOptions(config);
    bindConfigInputListeners();
    renderAll();
    appendLog("config", {
        provider: config.provider,
        base_url: config.base_url,
        configured: config.configured,
    });
}

async function runAnalysis() {
    if (!state.config) {
        return;
    }

    const payload = readConfigForm();
    if (!payload.symbol || !payload.analysis_date || !payload.model) {
        throw new Error("Symbol, analysis date and model are required.");
    }

    state.run = createEmptyRunState();
    state.run.logs = [];
    setBusy(true);
    renderAll();

    try {
        const response = await fetch("/api/analyze", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            throw new Error(await response.text());
        }

        await consumeEventStream(response);
    } finally {
        setBusy(false);
        renderAll();
    }
}

elements.openConfigButton.addEventListener("click", openConfigModal);
elements.closeConfigButton.addEventListener("click", closeConfigModal);
elements.runAnalysisButton.addEventListener("click", async () => {
    try {
        await runAnalysis();
    } catch (error) {
        appendLog("run-error", error instanceof Error ? error.message : String(error));
        state.run.warnings.unshift(error instanceof Error ? error.message : String(error));
        renderAll();
    }
});
elements.saveConfigButton.addEventListener("click", () => {
    renderSummaryChips();
    closeConfigModal();
});
elements.configForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    closeConfigModal();
    try {
        await runAnalysis();
    } catch (error) {
        appendLog("run-error", error instanceof Error ? error.message : String(error));
        state.run.warnings.unshift(error instanceof Error ? error.message : String(error));
        renderAll();
    }
});
elements.configModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.closeModal === "true") {
        closeConfigModal();
    }
});
window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !elements.configModal.classList.contains("hidden")) {
        closeConfigModal();
    }
});

loadConfig().catch((error) => {
    appendLog("config-error", error instanceof Error ? error.message : String(error));
    state.run.warnings.unshift(error instanceof Error ? error.message : String(error));
    renderAll();
});