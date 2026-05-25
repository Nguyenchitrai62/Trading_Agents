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

const CORE_ANALYSTS = ["market", "social", "news"];
const CRYPTO_SUFFIXES = ["-USD", "-USDT", "-USDC", "-BTC", "-ETH"];
const CUSTOM_LOOKBACK_VALUE = "__custom__";
const API_BASE_STORAGE_KEY = "tradingagents.apiBaseUrl";
const DEV_API_BASE_CANDIDATES = ["http://127.0.0.1:8000", "http://localhost:8000"];

const DETAIL_PANEL_META = {
    bullResearch: { title: "Bull Researcher", subtitle: "Research Chamber" },
    bearResearch: { title: "Bear Researcher", subtitle: "Research Chamber" },
    researchManager: { title: "Research Manager", subtitle: "Research Chamber" },
    traderPlan: { title: "Trader Plan", subtitle: "Trader Desk" },
    aggressiveRisk: { title: "Aggressive Analyst", subtitle: "Risk Room" },
    conservativeRisk: { title: "Conservative Analyst", subtitle: "Risk Room" },
    neutralRisk: { title: "Neutral Analyst", subtitle: "Risk Room" },
    portfolioDecision: { title: "Final Decision", subtitle: "Portfolio Management" },
    eventLog: { title: "Event Log", subtitle: "SSE Timeline", mode: "text" },
};

const state = {
    config: null,
    apiBaseUrl: getConfiguredApiBaseUrl(),
    isBusy: false,
    controller: null,
    activeDetail: null,
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
    dashboard: document.querySelector(".dashboard"),
    detailModal: document.getElementById("detailModal"),
    closeDetailButton: document.getElementById("closeDetailButton"),
    detailTitle: document.getElementById("detailTitle"),
    detailSubtitle: document.getElementById("detailSubtitle"),
    detailBody: document.getElementById("detailBody"),
    saveConfigButton: document.getElementById("saveConfigButton"),
    runFromModalButton: document.getElementById("runFromModalButton"),
    symbolInput: document.getElementById("symbolInput"),
    assetTypeSelect: document.getElementById("assetTypeSelect"),
    analysisDateInput: document.getElementById("analysisDateInput"),
    lookbackPresetSelect: document.getElementById("lookbackPresetSelect"),
    lookbackDaysInput: document.getElementById("lookbackDaysInput"),
    languageSelect: document.getElementById("languageSelect"),
    customLanguageField: document.getElementById("customLanguageField"),
    customLanguageInput: document.getElementById("customLanguageInput"),
    analystOptions: document.getElementById("analystOptions"),
    selectAllAnalystsButton: document.getElementById("selectAllAnalystsButton"),
    selectCoreAnalystsButton: document.getElementById("selectCoreAnalystsButton"),
    clearAnalystsButton: document.getElementById("clearAnalystsButton"),
    depthOptions: document.getElementById("depthOptions"),
    providerDisplayInput: document.getElementById("providerDisplayInput"),
    modelInput: document.getElementById("modelInput"),
    checkpointToggle: document.getElementById("checkpointToggle"),
    configPreview: document.getElementById("configPreview"),
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

function renderInlineMarkdown(value = "") {
    return escapeHtml(value)
        .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/__([^_]+)__/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<em>$1</em>")
        .replace(/_([^_]+)_/g, "<em>$1</em>");
}

function renderMarkdown(content, fallback = "No content yet.") {
    const source = content && content.trim() ? content : fallback;
    const lines = source.replace(/\r\n/g, "\n").split("\n");
    const htmlParts = [];
    let activeList = null;
    let inCodeBlock = false;
    let codeLines = [];

    const closeList = () => {
        if (activeList) {
            htmlParts.push(`</${activeList}>`);
            activeList = null;
        }
    };

    const openList = (type) => {
        if (activeList !== type) {
            closeList();
            htmlParts.push(`<${type}>`);
            activeList = type;
        }
    };

    for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith("```")) {
            if (inCodeBlock) {
                htmlParts.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
                codeLines = [];
                inCodeBlock = false;
            } else {
                closeList();
                inCodeBlock = true;
            }
            continue;
        }

        if (inCodeBlock) {
            codeLines.push(line);
            continue;
        }

        if (!trimmed) {
            closeList();
            continue;
        }

        const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
        if (heading) {
            closeList();
            const level = Math.min(heading[1].length + 1, 6);
            htmlParts.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
            continue;
        }

        const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
        if (unordered) {
            openList("ul");
            htmlParts.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
            continue;
        }

        const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
        if (ordered) {
            openList("ol");
            htmlParts.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
            continue;
        }

        const quote = trimmed.match(/^>\s?(.+)$/);
        if (quote) {
            closeList();
            htmlParts.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
            continue;
        }

        if (/^[-*_]{3,}$/.test(trimmed)) {
            closeList();
            htmlParts.push("<hr>");
            continue;
        }

        closeList();
        htmlParts.push(`<p>${renderInlineMarkdown(trimmed)}</p>`);
    }

    if (inCodeBlock) {
        htmlParts.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    }
    closeList();
    return htmlParts.join("");
}

function setMarkdownPreview(element, content, fallback) {
    const hasContent = Boolean(content && content.trim());
    element.innerHTML = renderMarkdown(content, fallback);
    element.classList.toggle("is-empty", !hasContent);
}

function normalizeApiBaseUrl(value = "") {
    return value.trim().replace(/\/$/, "");
}

function isPlaceholderApiBaseUrl(value = "") {
    return value.includes("__BACKEND_BASE_URL__");
}

function getQueryParamApiBaseUrl() {
    const params = new URLSearchParams(window.location.search);
    return normalizeApiBaseUrl(params.get("api_base_url") || params.get("apiBaseUrl") || "");
}

function getRuntimeConfigApiBaseUrl() {
    return normalizeApiBaseUrl(window.TRADINGAGENTS_RUNTIME_CONFIG?.apiBaseUrl || "");
}

function getStoredApiBaseUrl() {
    try {
        return normalizeApiBaseUrl(window.localStorage.getItem(API_BASE_STORAGE_KEY) || "");
    } catch {
        return "";
    }
}

function storeApiBaseUrl(value) {
    const normalized = normalizeApiBaseUrl(value);
    if (!normalized) {
        return;
    }
    try {
        window.localStorage.setItem(API_BASE_STORAGE_KEY, normalized);
    } catch {
        // Ignore storage failures in restricted browser contexts.
    }
}

function getSameOriginApiBaseUrl() {
    if (window.location.protocol === "http:" || window.location.protocol === "https:") {
        return normalizeApiBaseUrl(window.location.origin);
    }
    return "";
}

function getConfiguredApiBaseUrl() {
    const meta = document.querySelector('meta[name="tradingagents-api-base-url"]');
    const configured = normalizeApiBaseUrl(meta?.getAttribute("content") || "");
    const candidates = [
        getQueryParamApiBaseUrl(),
        configured,
        getRuntimeConfigApiBaseUrl(),
        getStoredApiBaseUrl(),
    ];

    return candidates.find((candidate) => candidate && !isPlaceholderApiBaseUrl(candidate)) || "";
}

function buildApiUrlFromBase(baseUrl, path) {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    return baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath;
}

function buildApiUrl(path) {
    return buildApiUrlFromBase(state.apiBaseUrl, path);
}

function detectAssetTypeFromSymbol(symbol) {
    const normalized = symbol.trim().toUpperCase();
    return CRYPTO_SUFFIXES.some((suffix) => normalized.endsWith(suffix)) ? "crypto" : "stock";
}

function getResolvedAssetType() {
    const selected = elements.assetTypeSelect.value || "auto";
    if (selected !== "auto") {
        return selected;
    }
    return detectAssetTypeFromSymbol(elements.symbolInput.value);
}

function collectConfigDraft() {
    return {
        symbol: elements.symbolInput.value.trim().toUpperCase(),
        asset_type: elements.assetTypeSelect.value || "auto",
        analysis_date: elements.analysisDateInput.value,
        lookback_days: Number(elements.lookbackDaysInput.value || 7),
        output_language: getOutputLanguage(),
        selected_analysts: getCheckedAnalysts(),
        research_depth: getSelectedDepth(),
        model: elements.modelInput.value.trim(),
        checkpoint_enabled: elements.checkpointToggle.checked,
    };
}

function formatBlock(content, fallback = "No content yet.") {
    return renderMarkdown(content, fallback);
}

function appendLog(label, payload) {
    const timestamp = new Date().toLocaleTimeString();
    const hasMessagePayload = payload && typeof payload === "object" && "message" in payload;
    const text = typeof payload === "string"
        ? payload
        : hasMessagePayload
        ? `${payload.message} ${JSON.stringify({ ...payload, message: undefined })}`
        : JSON.stringify(payload);
    state.run.logs.unshift(`[${timestamp}] ${label}: ${text}`);
    state.run.logs = state.run.logs.slice(0, 120);
    elements.eventLog.textContent = state.run.logs.join("\n");
    if (state.activeDetail?.key === "eventLog") {
        renderActiveDetail();
    }
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
    elements.customLanguageField.classList.toggle("hidden", !isCustom);
}

function syncLookbackPreset() {
    if (!state.config) {
        return;
    }
    const presets = state.config.analysis_options.lookback_presets || [];
    const days = Number(elements.lookbackDaysInput.value || 0);
    const matched = presets.find((preset) => preset.days === days);
    elements.lookbackPresetSelect.value = matched ? matched.value : CUSTOM_LOOKBACK_VALUE;
}

function syncAnalystAvailability() {
    const fundamentalsInput = elements.analystOptions.querySelector('input[value="fundamentals"]');
    if (!fundamentalsInput) {
        return;
    }

    const card = fundamentalsInput.closest(".checkbox-card");
    const shouldDisable = getResolvedAssetType() === "crypto";
    fundamentalsInput.disabled = shouldDisable;
    if (shouldDisable) {
        fundamentalsInput.checked = false;
    }
    card?.classList.toggle("checkbox-card-disabled", shouldDisable);
}

function renderConfigPreview() {
    if (!state.config) {
        elements.configPreview.innerHTML = "";
        return;
    }

    const payload = collectConfigDraft();
    const assetTypeMap = Object.fromEntries(
        (state.config.analysis_options.asset_types || []).map((item) => [item.value, item.label]),
    );
    const depthMap = Object.fromEntries(
        state.config.analysis_options.research_depths.map((item) => [item.value, item.label]),
    );
    const analystLabelMap = Object.fromEntries(
        state.config.analysis_options.analysts.map((item) => [item.value, item.label]),
    );
    const analystNames = payload.selected_analysts.map((key) => analystLabelMap[key] || key);
    const resolvedAssetType = getResolvedAssetType();
    const rows = [
        ["Resolved asset", assetTypeMap[resolvedAssetType] || resolvedAssetType],
        ["Window", `${payload.lookback_days || 0} day(s)`],
        ["Language", payload.output_language || "-"],
        ["Depth", depthMap[payload.research_depth] || payload.research_depth],
        ["Provider", state.config.provider || "minimax"],
        ["Analysts", analystNames.length ? analystNames.join(", ") : "None selected"],
    ];

    const notes = [];
    if (payload.asset_type === "auto") {
        notes.push("Asset type đang ở chế độ auto detect.");
    }
    if (resolvedAssetType === "crypto") {
        notes.push("Crypto mode sẽ tự bỏ Fundamentals Analyst để tránh request không hợp lệ.");
    }
    if (!analystNames.length) {
        notes.push("Cần chọn ít nhất một analyst trước khi chạy.");
    }

    elements.configPreview.innerHTML = `
        <div class="config-preview-grid">
            ${rows
                .map(
                    ([label, value]) => `
                        <article class="config-preview-card">
                            <span>${escapeHtml(label)}</span>
                            <strong>${escapeHtml(value)}</strong>
                        </article>
                    `,
                )
                .join("")}
        </div>
        <ul class="config-preview-notes">
            ${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}
        </ul>
    `;
}

function refreshConfigUi() {
    syncLanguageControls();
    syncLookbackPreset();
    syncAnalystAvailability();
    renderSummaryChips();
    renderConfigPreview();
}

function renderSummaryChips() {
    if (!state.config) {
        elements.summaryChips.innerHTML = "";
        return;
    }

    let payload;
    try {
        payload = collectConfigDraft();
    } catch {
        payload = {
            symbol: state.config.analysis_defaults.symbol,
            asset_type: state.config.analysis_defaults.asset_type,
            analysis_date: state.config.analysis_defaults.analysis_date,
            lookback_days: state.config.analysis_defaults.lookback_days,
            output_language: state.config.analysis_defaults.output_language,
            selected_analysts: state.config.analysis_defaults.selected_analysts,
            research_depth: state.config.analysis_defaults.research_depth,
            model: state.config.analysis_defaults.model,
        };
    }

    const assetTypeMap = Object.fromEntries(
        (state.config.analysis_options.asset_types || []).map((item) => [item.value, item.label]),
    );
    const analystLabelMap = Object.fromEntries(
        state.config.analysis_options.analysts.map((item) => [item.value, item.label]),
    );
    const depthMap = Object.fromEntries(
        state.config.analysis_options.research_depths.map((item) => [item.value, item.label]),
    );
    const chips = [
        `Symbol: ${payload.symbol || "-"}`,
        `Asset: ${assetTypeMap[getResolvedAssetType()] || getResolvedAssetType()}`,
        `Date: ${payload.analysis_date || "-"}`,
        `Window: ${payload.lookback_days || "-"}d`,
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
                <article class="report-card detail-trigger ${state.run.latestReportTitle === report.title ? "report-card-active" : ""}"
                    data-detail-section="${escapeHtml(report.section)}"
                    data-detail-title="${escapeHtml(analystOptions[key] || report.title)}"
                    data-detail-subtitle="${escapeHtml(report.title)}"
                    tabindex="0"
                    role="button"
                    aria-label="Open ${escapeHtml(report.title)} detail">
                    <header>
                        <h3>${escapeHtml(analystOptions[key] || report.title)}</h3>
                        <span>${escapeHtml(report.title)}</span>
                    </header>
                    <div class="panel-preview markdown-preview ${content ? "" : "is-empty"}">
                        ${formatBlock(content, "Report chưa có dữ liệu. Khi agent hoàn thành, phần này sẽ được cập nhật ngay.")}
                    </div>
                </article>
            `;
        })
        .join("");

    elements.activeReportText.textContent = state.run.latestReportTitle || "No reports yet";
}

function renderResearchRoom() {
    const research = state.run.research || {};
    setMarkdownPreview(elements.bullResearchPanel, research.bull_history, "Bull Researcher chưa phát biểu.");
    setMarkdownPreview(elements.bearResearchPanel, research.bear_history, "Bear Researcher chưa phản biện.");
    setMarkdownPreview(
        elements.researchManagerPanel,
        state.run.sections.investment_plan || research.judge_decision,
        "Research Manager chưa tổng hợp kế hoạch.",
    );

    elements.researchStatusText.textContent = state.run.sections.investment_plan
        ? "Investment plan ready"
        : research.history
        ? "Debate in progress"
        : "Awaiting analyst reports";
}

function renderTraderDesk() {
    setMarkdownPreview(
        elements.traderPlanPanel,
        state.run.sections.trader_investment_plan,
        "Trader chưa đưa ra transaction proposal.",
    );
}

function renderRiskRoom() {
    const risk = state.run.risk || {};
    setMarkdownPreview(elements.aggressiveRiskPanel, risk.aggressive_history, "Aggressive Analyst chưa có lập luận.");
    setMarkdownPreview(elements.conservativeRiskPanel, risk.conservative_history, "Conservative Analyst chưa có lập luận.");
    setMarkdownPreview(elements.neutralRiskPanel, risk.neutral_history, "Neutral Analyst chưa có lập luận.");
    elements.riskStatusText.textContent = state.run.sections.final_trade_decision
        ? "Risk loop completed"
        : risk.history
        ? "Risk debate live"
        : "Waiting for trader";
}

function renderFinalDecision() {
    const decision = state.run.sections.final_trade_decision || "Portfolio Manager chưa chốt quyết định.";
    setMarkdownPreview(elements.portfolioDecisionPanel, state.run.sections.final_trade_decision, decision);
    elements.signalBadge.textContent = state.run.complete?.signal || "No signal";
}

function renderSmartNotes() {
    const notes = [];
    if (state.run.meta) {
        notes.push(`Asset type: ${state.run.meta.asset_type}`);
        notes.push(`Lookback window: ${state.run.meta.lookback_days} day(s)`);
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

function getDetailContent(detail) {
    const research = state.run.research || {};
    const risk = state.run.risk || {};

    if (detail?.type === "report") {
        return {
            content: state.run.sections[detail.section] || "",
            fallback: "Report chưa có dữ liệu. Khi agent hoàn thành, phần này sẽ được cập nhật ngay.",
        };
    }

    switch (detail?.key) {
        case "bullResearch":
            return { content: research.bull_history || "", fallback: "Bull Researcher chưa phát biểu." };
        case "bearResearch":
            return { content: research.bear_history || "", fallback: "Bear Researcher chưa phản biện." };
        case "researchManager":
            return {
                content: state.run.sections.investment_plan || research.judge_decision || "",
                fallback: "Research Manager chưa tổng hợp kế hoạch.",
            };
        case "traderPlan":
            return { content: state.run.sections.trader_investment_plan || "", fallback: "Trader chưa đưa ra transaction proposal." };
        case "aggressiveRisk":
            return { content: risk.aggressive_history || "", fallback: "Aggressive Analyst chưa có lập luận." };
        case "conservativeRisk":
            return { content: risk.conservative_history || "", fallback: "Conservative Analyst chưa có lập luận." };
        case "neutralRisk":
            return { content: risk.neutral_history || "", fallback: "Neutral Analyst chưa có lập luận." };
        case "portfolioDecision":
            return { content: state.run.sections.final_trade_decision || "", fallback: "Portfolio Manager chưa chốt quyết định." };
        case "eventLog":
            return { content: state.run.logs.join("\n"), fallback: "Chưa có SSE event nào." };
        default:
            return { content: "", fallback: "Chưa có dữ liệu." };
    }
}

function renderActiveDetail() {
    const detail = state.activeDetail;
    if (!detail || elements.detailModal.classList.contains("hidden")) {
        return;
    }

    const meta = detail.type === "report" ? detail : DETAIL_PANEL_META[detail.key] || {};
    const { content, fallback } = getDetailContent(detail);
    const mode = meta.mode || "markdown";
    elements.detailTitle.textContent = meta.title || "Panel Detail";
    elements.detailSubtitle.textContent = meta.subtitle || "Analysis detail";
    elements.detailBody.classList.toggle("plain-log", mode === "text");
    elements.detailBody.classList.toggle("markdown-preview", mode !== "text");

    if (mode === "text") {
        elements.detailBody.textContent = content || fallback;
    } else {
        setMarkdownPreview(elements.detailBody, content, fallback);
    }
}

function openDetailModal(detail) {
    state.activeDetail = detail;
    elements.detailModal.classList.remove("hidden");
    elements.detailModal.setAttribute("aria-hidden", "false");
    renderActiveDetail();
}

function closeDetailModal() {
    elements.detailModal.classList.add("hidden");
    elements.detailModal.setAttribute("aria-hidden", "true");
    state.activeDetail = null;
}

function openDetailFromTrigger(trigger) {
    const section = trigger.dataset.detailSection;
    if (section) {
        openDetailModal({
            type: "report",
            section,
            title: trigger.dataset.detailTitle || "Report Detail",
            subtitle: trigger.dataset.detailSubtitle || "Analyst report",
        });
        return;
    }

    const key = trigger.dataset.detailKey;
    if (key) {
        openDetailModal({ key });
    }
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
    renderActiveDetail();
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

    if (event === "analysis_log") {
        appendLog(data.phase || event, data);
        renderProgress();
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

function populateAssetTypeOptions(config) {
    const currentValue = config.analysis_defaults.asset_type || "auto";
    elements.assetTypeSelect.innerHTML = (config.analysis_options.asset_types || [])
        .map(
            (assetType) => `<option value="${escapeHtml(assetType.value)}">${escapeHtml(assetType.label)}</option>`,
        )
        .join("");
    elements.assetTypeSelect.value = currentValue;
}

function populateLookbackPresets(config) {
    elements.lookbackPresetSelect.innerHTML = (config.analysis_options.lookback_presets || [])
        .map(
            (preset) => `<option value="${escapeHtml(preset.value)}">${escapeHtml(preset.label)}</option>`,
        )
        .concat(`<option value="${CUSTOM_LOOKBACK_VALUE}">Custom</option>`)
        .join("");
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
    const sync = () => refreshConfigUi();
    [
        elements.symbolInput,
        elements.assetTypeSelect,
        elements.analysisDateInput,
        elements.lookbackPresetSelect,
        elements.lookbackDaysInput,
        elements.modelInput,
        elements.customLanguageInput,
        elements.checkpointToggle,
        elements.languageSelect,
    ].forEach((element) => element.addEventListener("input", sync));
    elements.assetTypeSelect.addEventListener("change", sync);
    elements.lookbackPresetSelect.addEventListener("change", () => {
        if (elements.lookbackPresetSelect.value !== CUSTOM_LOOKBACK_VALUE) {
            elements.lookbackDaysInput.value = elements.lookbackPresetSelect.value;
        }
        refreshConfigUi();
    });
    elements.languageSelect.addEventListener("change", () => {
        refreshConfigUi();
    });
    elements.analystOptions.addEventListener("change", sync);
    elements.depthOptions.addEventListener("change", sync);
}

function setAnalystSelection(values) {
    const selected = new Set(values);
    Array.from(elements.analystOptions.querySelectorAll('input[type="checkbox"]')).forEach((input) => {
        if (!input.disabled) {
            input.checked = selected.has(input.value);
        }
    });
    refreshConfigUi();
}

async function loadConfig() {
    const candidateBases = [
        getQueryParamApiBaseUrl(),
        getSameOriginApiBaseUrl(),
        ...DEV_API_BASE_CANDIDATES,
        state.apiBaseUrl,
        getStoredApiBaseUrl(),
        getRuntimeConfigApiBaseUrl(),
    ].filter((value, index, array) => value && !isPlaceholderApiBaseUrl(value) && array.indexOf(value) === index);

    let response = null;
    let lastError = null;
    for (const baseUrl of candidateBases) {
        try {
            const attempt = await fetch(buildApiUrlFromBase(baseUrl, "/api/config"));
            if (!attempt.ok) {
                lastError = new Error(`Failed to load config: ${attempt.status}`);
                continue;
            }
            response = attempt;
            state.apiBaseUrl = baseUrl || state.apiBaseUrl;
            break;
        } catch (error) {
            lastError = error;
        }
    }

    if (!response) {
        throw lastError || new Error("Failed to load config");
    }

    const config = await response.json();
    state.config = config;
    state.apiBaseUrl = normalizeApiBaseUrl(config.api_base_url || state.apiBaseUrl);
    storeApiBaseUrl(state.apiBaseUrl);

    elements.endpointText.textContent = `${config.provider || "minimax"} • ${config.base_url || "Unknown"}`;
    elements.symbolInput.value = config.analysis_defaults.symbol;
    populateAssetTypeOptions(config);
    elements.analysisDateInput.value = config.analysis_defaults.analysis_date;
    populateLookbackPresets(config);
    elements.lookbackDaysInput.value = config.analysis_defaults.lookback_days;
    elements.providerDisplayInput.value = `${config.provider || "minimax"} • ${config.base_url || "Unknown"}`;
    elements.modelInput.value = config.analysis_defaults.model;
    elements.checkpointToggle.checked = Boolean(config.analysis_defaults.checkpoint_enabled);
    populateLanguageOptions(config);
    populateAnalystOptions(config);
    populateDepthOptions(config);
    bindConfigInputListeners();
    refreshConfigUi();
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
        const response = await fetch(buildApiUrl("/api/analyze"), {
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
    refreshConfigUi();
    closeConfigModal();
});
elements.selectAllAnalystsButton.addEventListener("click", () => {
    setAnalystSelection(state.config?.analysis_options?.analysts?.map((item) => item.value) || []);
});
elements.selectCoreAnalystsButton.addEventListener("click", () => {
    setAnalystSelection(CORE_ANALYSTS);
});
elements.clearAnalystsButton.addEventListener("click", () => {
    setAnalystSelection([]);
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
elements.closeDetailButton.addEventListener("click", closeDetailModal);
elements.detailModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.closeDetail === "true") {
        closeDetailModal();
    }
});
elements.dashboard.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) {
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
    if (event.key === "Escape" && !elements.detailModal.classList.contains("hidden")) {
        closeDetailModal();
        return;
    }
    if (event.key === "Escape" && !elements.configModal.classList.contains("hidden")) {
        closeConfigModal();
    }
});

loadConfig().catch((error) => {
    appendLog("config-error", error instanceof Error ? error.message : String(error));
    state.run.warnings.unshift(error instanceof Error ? error.message : String(error));
    renderAll();
});