const GROUP_LABELS = {
    analysts: "Signals",
    research: "Research",
    trading: "Trader",
    risk: "Risk",
    portfolio: "Manager",
};

const REPORT_BY_ANALYST = {
    market: { section: "market_report", title: "Market Analysis" },
    social: { section: "sentiment_report", title: "Sentiment Analysis" },
    news: { section: "news_report", title: "News Analysis" },
    fundamentals: { section: "fundamentals_report", title: "Fundamentals Analysis" },
};

const REPORT_DETAIL_BY_AGENT = {
    "Market Analyst": {
        type: "report",
        section: REPORT_BY_ANALYST.market.section,
        title: REPORT_BY_ANALYST.market.title,
        subtitle: "Market Analyst",
    },
    "Sentiment Analyst": {
        type: "report",
        section: REPORT_BY_ANALYST.social.section,
        title: REPORT_BY_ANALYST.social.title,
        subtitle: "Sentiment Analyst",
    },
    "News Analyst": {
        type: "report",
        section: REPORT_BY_ANALYST.news.section,
        title: REPORT_BY_ANALYST.news.title,
        subtitle: "News Analyst",
    },
    "Fundamentals Analyst": {
        type: "report",
        section: REPORT_BY_ANALYST.fundamentals.section,
        title: REPORT_BY_ANALYST.fundamentals.title,
        subtitle: "Fundamentals Analyst",
    },
};

const COMPACT_AGENT_LABELS = {
    "Market Analyst": "Market",
    "Sentiment Analyst": "Social",
    "News Analyst": "News",
    "Fundamentals Analyst": "Fund",
    "Research Manager": "Lead",
    "Portfolio Manager": "Manager",
    "Aggressive Analyst": "Aggressive",
    "Conservative Analyst": "Conservative",
    "Neutral Analyst": "Neutral",
};

const STATUS_LABELS = {
    pending: "wait",
    in_progress: "run",
    completed: "done",
};

const CORE_ANALYSTS = ["market", "social", "news"];
const CUSTOM_LOOKBACK_VALUE = "__custom__";
const TRACE_DISPLAY_LIMIT = 14;
const LOG_DISPLAY_LIMIT = 12;
const EXECUTION_LOG_DISPLAY_LIMIT = 80;

const DETAIL_PANEL_META = {
    bullResearch: { title: "Bull Researcher", subtitle: "Research Chamber" },
    bearResearch: { title: "Bear Researcher", subtitle: "Research Chamber" },
    researchManager: { title: "Research Manager", subtitle: "Research Chamber" },
    traderPlan: { title: "Trader Plan", subtitle: "Trader Desk" },
    aggressiveRisk: { title: "Aggressive Analyst", subtitle: "Risk Room" },
    conservativeRisk: { title: "Conservative Analyst", subtitle: "Risk Room" },
    neutralRisk: { title: "Neutral Analyst", subtitle: "Risk Room" },
    portfolioDecision: { title: "Final Decision", subtitle: "Portfolio Management" },
    eventLog: { title: "Event Log", subtitle: "SSE Timeline", mode: "markdown" },
};

const state = {
    config: null,
    apiBaseUrl: getConfiguredApiBaseUrl(),
    isBusy: false,
    controller: null,
    activeRunId: null,
    stopRequested: false,
    activeDetail: null,
    run: createEmptyRunState(),
};

const elements = {
    runStatusBadge: document.getElementById("runStatusBadge"),
    currentAgentText: document.getElementById("currentAgentText"),
    endpointText: document.getElementById("endpointText"),
    topNoticeText: document.getElementById("topNoticeText"),
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
    executionLog: document.getElementById("executionLog"),
    executionLogStatusText: document.getElementById("executionLogStatusText"),
    opsStatusText: document.getElementById("opsStatusText"),
    opsAgentText: document.getElementById("opsAgentText"),
    opsPhaseText: document.getElementById("opsPhaseText"),
    opsLatestText: document.getElementById("opsLatestText"),
    toolTraceList: document.getElementById("toolTraceList"),
    eventLogStatusText: document.getElementById("eventLogStatusText"),
    openConfigButton: document.getElementById("openConfigButton"),
    closeConfigButton: document.getElementById("closeConfigButton"),
    runAnalysisButton: document.getElementById("runAnalysisButton"),
    stopAnalysisButton: document.getElementById("stopAnalysisButton"),
    configModal: document.getElementById("configModal"),
    configForm: document.getElementById("configForm"),
    dashboard: document.querySelector(".dashboard"),
    detailModal: document.getElementById("detailModal"),
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
    lookbackDaysInput: document.getElementById("lookbackDaysInput"),
    languageSelect: document.getElementById("languageSelect"),
    customLanguageField: document.getElementById("customLanguageField"),
    customLanguageInput: document.getElementById("customLanguageInput"),
    analystOptions: document.getElementById("analystOptions"),
    selectAllAnalystsButton: document.getElementById("selectAllAnalystsButton"),
    selectCoreAnalystsButton: document.getElementById("selectCoreAnalystsButton"),
    clearAnalystsButton: document.getElementById("clearAnalystsButton"),
    depthOptions: document.getElementById("depthOptions"),
    modelInput: document.getElementById("modelInput"),
    checkpointToggle: document.getElementById("checkpointToggle"),
    configPreview: document.getElementById("configPreview"),
};

[elements.configModal, elements.detailModal, elements.alertModal].forEach((modal) => {
    if (modal instanceof HTMLElement && modal.classList.contains("hidden")) {
        modal.setAttribute("inert", "");
    }
});

function createEmptyRunState() {
    return {
        meta: null,
        status: null,
        sections: {},
        research: {},
        risk: {},
        complete: null,
        cancelled: null,
        warnings: [],
        logs: [],
        logEntries: [],
        agentTrace: {},
        traceFeed: [],
        streamFeed: [],
        seenLogFingerprints: new Set(),
        seenStreamFingerprints: new Set(),
        seenTraceFingerprints: new Set(),
        lastTrackedAgent: null,
        latestReportTitle: null,
        latestTraceId: null,
        flashLatestTrace: false,
    };
}

function escapeHtml(value = "") {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function renderInlineMarkdown(value = "") {
    return escapeHtml(value)
        .replace(/!\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g, '<img src="$2" alt="$1" loading="lazy">')
        .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
        .replace(/(^|[\s(])((https?:\/\/)[^\s<)]+)/g, (match, prefix, url) => {
            const trailing = url.match(/[.,;:!?]+$/)?.[0] || "";
            const href = trailing ? url.slice(0, -trailing.length) : url;
            return `${prefix}<a href="${href}" target="_blank" rel="noreferrer">${href}</a>${trailing}`;
        })
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/~~([^~]+)~~/g, "<del>$1</del>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/__([^_]+)__/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<em>$1</em>")
        .replace(/_([^_]+)_/g, "<em>$1</em>");
}

function splitMarkdownTableRow(line = "") {
    const trimmed = line.trim();
    const withoutLeadingPipe = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
    const withoutTrailingPipe = withoutLeadingPipe.endsWith("|") ? withoutLeadingPipe.slice(0, -1) : withoutLeadingPipe;
    return withoutTrailingPipe.split("|").map((cell) => cell.trim());
}

function isMarkdownTableSeparator(line = "") {
    const cells = splitMarkdownTableRow(line);
    return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isMarkdownTableStart(lines, index) {
    if (index + 1 >= lines.length || !lines[index].includes("|")) {
        return false;
    }
    return splitMarkdownTableRow(lines[index]).length > 1 && isMarkdownTableSeparator(lines[index + 1]);
}

function renderMarkdownTable(lines, startIndex) {
    const headers = splitMarkdownTableRow(lines[startIndex]);
    const separators = splitMarkdownTableRow(lines[startIndex + 1]);
    const alignments = separators.map((cell) => {
        const left = cell.startsWith(":");
        const right = cell.endsWith(":");
        if (left && right) {
            return "center";
        }
        return right ? "right" : "left";
    });

    const rows = [];
    let nextIndex = startIndex + 2;
    while (nextIndex < lines.length) {
        const trimmed = lines[nextIndex].trim();
        if (!trimmed || trimmed.startsWith("```") || !trimmed.includes("|")) {
            break;
        }
        rows.push(splitMarkdownTableRow(trimmed));
        nextIndex += 1;
    }

    const renderCell = (tag, cell, index) => {
        const align = alignments[index] || "left";
        return `<${tag} style="text-align:${align}">${renderInlineMarkdown(cell || "")}</${tag}>`;
    };

    const table = `
        <div class="markdown-table-wrap">
            <table>
                <thead><tr>${headers.map((cell, index) => renderCell("th", cell, index)).join("")}</tr></thead>
                <tbody>
                    ${rows
                        .map((row) => `<tr>${headers.map((_, index) => renderCell("td", row[index] || "", index)).join("")}</tr>`)
                        .join("")}
                </tbody>
            </table>
        </div>
    `;

    return { table, nextIndex };
}

function renderMarkdown(content, fallback = "No content yet.") {
    const source = content && content.trim() ? content : fallback;
    const lines = source.replace(/\r\n/g, "\n").split("\n");
    const htmlParts = [];
    let activeList = null;
    let inCodeBlock = false;
    let codeLines = [];
    let paragraphLines = [];

    const flushParagraph = () => {
        if (!paragraphLines.length) {
            return;
        }
        htmlParts.push(`<p>${renderInlineMarkdown(paragraphLines.join(" "))}</p>`);
        paragraphLines = [];
    };

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

    for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index];
        const trimmed = line.trim();
        if (trimmed.startsWith("```")) {
            if (inCodeBlock) {
                htmlParts.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
                codeLines = [];
                inCodeBlock = false;
            } else {
                flushParagraph();
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
            flushParagraph();
            closeList();
            continue;
        }

        if (isMarkdownTableStart(lines, index)) {
            flushParagraph();
            closeList();
            const rendered = renderMarkdownTable(lines, index);
            htmlParts.push(rendered.table);
            index = rendered.nextIndex - 1;
            continue;
        }

        const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
        if (heading) {
            flushParagraph();
            closeList();
            const level = Math.min(heading[1].length, 6);
            htmlParts.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
            continue;
        }

        const unordered = trimmed.match(/^[-*+]\s+(.+)$/);
        if (unordered) {
            flushParagraph();
            openList("ul");
            htmlParts.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
            continue;
        }

        const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
        if (ordered) {
            flushParagraph();
            openList("ol");
            htmlParts.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
            continue;
        }

        const quote = trimmed.match(/^>\s?(.+)$/);
        if (quote) {
            flushParagraph();
            closeList();
            htmlParts.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
            continue;
        }

        if (/^[-*_]{3,}$/.test(trimmed)) {
            flushParagraph();
            closeList();
            htmlParts.push("<hr>");
            continue;
        }

        closeList();
        paragraphLines.push(trimmed);
    }

    if (inCodeBlock) {
        htmlParts.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    }
    flushParagraph();
    closeList();
    return htmlParts.join("");
}

function setMarkdownPreview(element, content, fallback) {
    const hasContent = Boolean(content && content.trim());
    element.innerHTML = renderMarkdown(content, fallback);
    element.classList.remove("compact-preview");
    element.classList.toggle("is-empty", !hasContent);
}

function stripMarkdownToPlainText(content = "") {
    return String(content)
        .replace(/```[\s\S]*?```/g, " ")
        .replace(/`([^`]+)`/g, "$1")
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1")
        .replace(/^#{1,6}\s+/gm, "")
        .replace(/^>\s?/gm, "")
        .replace(/^[-*+]\s+/gm, "")
        .replace(/^\d+[.)]\s+/gm, "")
        .replace(/[*_~]/g, "")
        .replace(/\r?\n+/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

function setCompactPreview(element, content, fallback, maxLength = 180) {
    const hasContent = Boolean(content && content.trim());
    const source = hasContent ? content : fallback;
    const text = compactText(stripMarkdownToPlainText(source), maxLength) || fallback;
    element.textContent = text;
    element.classList.add("compact-preview");
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

function getFrontendConfigSource() {
    return window.TRADINGAGENTS_CONFIG || {};
}

function getFrontendConfigApiBaseUrl() {
    const config = getFrontendConfigSource();
    return normalizeApiBaseUrl(config.apiBaseUrl || config.api_base_url || "");
}

function getSameOriginApiBaseUrl() {
    if (window.location.protocol === "http:" || window.location.protocol === "https:") {
        return normalizeApiBaseUrl(window.location.origin);
    }
    return "";
}

function getConfiguredApiBaseUrl() {
    const candidates = [
        getQueryParamApiBaseUrl(),
        getFrontendConfigApiBaseUrl(),
        getSameOriginApiBaseUrl(),
    ];

    return candidates.find((candidate) => candidate && !isPlaceholderApiBaseUrl(candidate)) || "";
}

function todayIsoDate() {
    return new Date().toISOString().slice(0, 10);
}

function normalizeFrontendConfig() {
    const source = getFrontendConfigSource();
    const defaults = source.analysisDefaults || source.analysis_defaults || {};
    const options = source.analysisOptions || source.analysis_options || {};
    const defaultModel = source.defaultModel || source.default_model || defaults.model || "MiniMax-M2.7";

    return {
        configured: true,
        provider: source.provider || "minimax",
        api_base_url: getConfiguredApiBaseUrl(),
        default_model: defaultModel,
        analysis_defaults: {
            symbol: String(defaults.symbol || "BTC-USDT").trim().toUpperCase(),
            asset_type: "crypto",
            analysis_date: defaults.analysisDate || defaults.analysis_date || todayIsoDate(),
            lookback_days: Number(defaults.lookbackDays || defaults.lookback_days || 7),
            output_language: defaults.outputLanguage || defaults.output_language || "Vietnamese",
            selected_analysts: defaults.selectedAnalysts || defaults.selected_analysts || ["market", "social", "news"],
            research_depth: defaults.researchDepth || defaults.research_depth || "medium",
            model: defaultModel,
            checkpoint_enabled: Boolean(defaults.checkpointEnabled ?? defaults.checkpoint_enabled ?? false),
        },
        analysis_options: {
            analysts: options.analysts || [
                { value: "market", label: "Market Analyst" },
                { value: "social", label: "Sentiment Analyst" },
                { value: "news", label: "News Analyst" },
                { value: "fundamentals", label: "Fundamentals Analyst" },
            ],
            asset_types: [{ value: "crypto", label: "Crypto" }],
            lookback_presets: options.lookbackPresets || options.lookback_presets || [
                { value: "7", label: "7 days", days: 7 },
                { value: "14", label: "14 days", days: 14 },
                { value: "30", label: "30 days", days: 30 },
                { value: "90", label: "90 days", days: 90 },
            ],
            output_languages: options.outputLanguages || options.output_languages || ["Vietnamese", "English"],
            research_depths: options.researchDepths || options.research_depths || [
                { value: "quick", label: "Quick", rounds: 1, description: "Fast scan with minimal debate." },
                { value: "medium", label: "Medium", rounds: 3, description: "Balanced research depth for regular analysis." },
                { value: "deep", label: "Deep", rounds: 5, description: "More debate rounds before the final decision." },
            ],
        },
    };
}

function buildApiUrlFromBase(baseUrl, path) {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    return baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath;
}

function buildApiUrl(path) {
    return buildApiUrlFromBase(state.apiBaseUrl, path);
}

function formatApiBaseLabel(value = "") {
    const normalized = normalizeApiBaseUrl(value);
    if (!normalized) {
        return "API unresolved";
    }

    try {
        const parsed = new URL(normalized);
        const path = parsed.pathname && parsed.pathname !== "/" ? parsed.pathname.replace(/\/$/, "") : "";
        return `API ${parsed.host}${path}`;
    } catch {
        return `API ${normalized}`;
    }
}

function normalizeCryptoSymbol(value = "") {
    const normalized = String(value).trim().toUpperCase().replace(/\s+/g, "");
    if (!normalized) {
        return "";
    }
    return normalized.includes("/") || normalized.includes("-") ? normalized : `${normalized}-USDT`;
}

function getResolvedAssetType() {
    return "crypto";
}

function collectConfigDraft() {
    return {
        symbol: normalizeCryptoSymbol(elements.symbolInput.value),
        asset_type: "crypto",
        analysis_date: elements.analysisDateInput.value,
        lookback_days: Number(elements.lookbackDaysInput.value || 7),
        output_language: getOutputLanguage(),
        selected_analysts: getCheckedAnalysts(),
        research_depth: getSelectedDepth(),
        model: elements.modelInput.value.trim(),
        checkpoint_enabled: elements.checkpointToggle.checked,
    };
}

function createRunId() {
    return `run-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function isAbortError(error) {
    return Boolean(error && error.name === "AbortError");
}

function requestBackendCancel(runId) {
    if (!runId) {
        return Promise.resolve(null);
    }
    return fetch(buildApiUrl(`/api/analyze/${encodeURIComponent(runId)}/cancel`), {
        method: "POST",
        keepalive: true,
    }).catch(() => null);
}

function getConfigSnapshot() {
    if (!state.config) {
        return null;
    }

    try {
        return collectConfigDraft();
    } catch {
        return {
            symbol: state.config.analysis_defaults.symbol,
            asset_type: "crypto",
            analysis_date: state.config.analysis_defaults.analysis_date,
            lookback_days: state.config.analysis_defaults.lookback_days,
            output_language: state.config.analysis_defaults.output_language,
            selected_analysts: state.config.analysis_defaults.selected_analysts,
            research_depth: state.config.analysis_defaults.research_depth,
            model: state.config.analysis_defaults.model,
            checkpoint_enabled: Boolean(state.config.analysis_defaults.checkpoint_enabled),
        };
    }
}

function compactText(value = "", maxLength = 220) {
    const normalized = String(value).replace(/\s+/g, " ").trim();
    if (!normalized) {
        return "";
    }
    return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 3)}...` : normalized;
}

function buildContentFingerprint(...parts) {
    return parts
        .map((part) => stripMarkdownToPlainText(String(part || "")).toLowerCase())
        .join("|")
        .replace(/\belapsed=\d+(?:\.\d+)?s\b/g, "elapsed=*s")
        .replace(/\b\d+(?:\.\d+)?\s*s\b/g, "*s")
        .replace(/\s+/g, " ")
        .trim();
}

function formatStatusLabel(status = "pending") {
    return status.replaceAll("_", " ");
}

function formatTracePhaseLabel(phase = "analysis") {
    const normalized = String(phase || "analysis").replaceAll("_", " ").trim();
    return normalized ? normalized[0].toUpperCase() + normalized.slice(1) : "Analysis";
}

function formatStructuredValue(payload) {
    if (typeof payload === "string") {
        return payload.trim();
    }
    if (payload == null) {
        return "";
    }
    if (typeof payload === "number" || typeof payload === "boolean") {
        return String(payload);
    }
    if (Array.isArray(payload)) {
        return payload.map((item) => formatStructuredValue(item)).filter(Boolean).join("\n");
    }
    if (typeof payload === "object") {
        const preferredKeys = ["message", "content", "title", "signal", "phase", "error"];
        for (const key of preferredKeys) {
            const value = payload[key];
            if (typeof value === "string" && value.trim()) {
                return value.trim();
            }
        }
        try {
            return JSON.stringify(payload, null, 2);
        } catch {
            return String(payload);
        }
    }
    return String(payload);
}

function buildLogEntry(label, payload) {
    const backendLine = payload && typeof payload === "object" && typeof payload.log_line === "string"
        ? payload.log_line.trim()
        : "";
    const message = payload && typeof payload === "object" && typeof payload.message === "string"
        ? payload.message.trim()
        : "";
    const timestampMs = Date.now();
    const timestamp = new Date(timestampMs).toLocaleTimeString();
    const detail = backendLine || message || formatStructuredValue(payload) || label;
    const summary = compactText(stripMarkdownToPlainText(message || backendLine || formatStructuredValue(payload) || detail), 220) || label;
    return {
        id: `log-${timestampMs}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp,
        label: String(label || "event"),
        summary,
        detail,
    };
}

function getTraceEntryById(traceId) {
    return state.run.traceFeed.find((entry) => entry.id === traceId) || null;
}

function preserveScrollPosition(element, updateFn) {
    if (!(element instanceof HTMLElement)) {
        updateFn();
        return;
    }

    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    updateFn();

    if (distanceFromBottom <= 32) {
        element.scrollTop = element.scrollHeight;
        return;
    }

    element.scrollTop = Math.max(0, element.scrollHeight - element.clientHeight - distanceFromBottom);
}

function isScrolledNearBottom(element, threshold = 36) {
    if (!(element instanceof HTMLElement)) {
        return true;
    }
    return element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
}

function getFocusIdentity(focus) {
    if (focus.detail?.type === "report") {
        return `report:${focus.detail.section}`;
    }
    if (focus.detail?.key) {
        return `panel:${focus.detail.key}`;
    }
    return `focus:${focus.title}:${focus.subtitle || ""}`;
}

function pushStreamFeed(entry) {
    const fingerprint = buildContentFingerprint(entry.title, entry.content);
    if (fingerprint && state.run.seenStreamFingerprints.has(fingerprint)) {
        return;
    }
    if (fingerprint) {
        state.run.seenStreamFingerprints.add(fingerprint);
    }

    state.run.streamFeed.unshift({
        timestamp: new Date().toLocaleTimeString(),
        tone: "progress",
        ...entry,
    });
    state.run.streamFeed = state.run.streamFeed.slice(0, 24);
}

function getFeedToneForPhase(phase = "progress") {
    if (phase === "tool_result" || phase === "analysis") {
        return "live";
    }
    if (phase === "warning") {
        return "warning";
    }
    if (phase === "completed") {
        return "completed";
    }
    return "progress";
}

function pushAgentTrace(trace) {
    const agent = trace.agent || state.run.status?.current_agent || "Agent";
    const phase = trace.phase || "analysis";
    const content = String(trace.content || "").trim();
    const fingerprint = buildContentFingerprint(agent, phase, trace.title || agent, content);
    if (!content || (fingerprint && state.run.seenTraceFingerprints.has(fingerprint))) {
        return;
    }
    if (fingerprint) {
        state.run.seenTraceFingerprints.add(fingerprint);
    }

    const wasAtLatest = isScrolledNearBottom(elements.toolTraceList);
    const entry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp: new Date().toLocaleTimeString(),
        agent,
        phase,
        tone: getFeedToneForPhase(phase),
        title: trace.title || agent,
        content,
    };

    state.run.agentTrace[agent] = [...(state.run.agentTrace[agent] || []), entry].slice(-12);
    state.run.traceFeed = [...state.run.traceFeed, entry].slice(-40);
    state.run.latestTraceId = entry.id;
    state.run.flashLatestTrace = wasAtLatest;
    pushStreamFeed({
        title: `${agent} - ${entry.title}`,
        content: compactText(entry.content, 260),
        tone: entry.tone,
    });
}

function getAgentTraceEntries(agent, limit = 6, allowedPhases = null) {
    if (!agent) {
        return [];
    }
    const entries = state.run.agentTrace[agent] || [];
    const filtered = Array.isArray(allowedPhases)
        ? entries.filter((entry) => allowedPhases.includes(entry.phase))
        : entries;
    return filtered.slice(-limit);
}

function getAgentTraceMarkdown(agent, limit = 6, allowedPhases = null) {
    const entries = getAgentTraceEntries(agent, limit, allowedPhases);
    if (!entries.length) {
        return "";
    }
    return entries
        .map((entry) => `### ${formatTracePhaseLabel(entry.phase)} - ${entry.title}\n${entry.content}`)
        .join("\n\n");
}

function getAgentNarrativeMarkdown(agent, limit = 5) {
    return getAgentTraceMarkdown(agent, limit, ["analysis"]);
}

function getFallbackStatusGroups() {
    const fallbackAnalysts = getConfigSnapshot()?.selected_analysts
        || state.config?.analysis_defaults?.selected_analysts
        || [];
    return {
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
        portfolio: [{ key: "portfolio_manager", label: "Portfolio Manager", status: "pending" }],
    };
}

function getStatusGroups() {
    return state.run.status?.groups || getFallbackStatusGroups();
}

function buildCancelledStatus(status) {
    const fallbackGroups = getFallbackStatusGroups();
    const sourceGroups = status?.groups || fallbackGroups;
    const groups = Object.fromEntries(
        Object.entries(sourceGroups).map(([groupKey, items]) => [
            groupKey,
            (items || []).map((item) => ({
                ...item,
                status: item.status === "completed" ? "completed" : "pending",
            })),
        ]),
    );

    const progress = status?.progress || { completed: 0, total: 0, percent: 0 };
    const total = Number(progress.total || 0);
    const completed = Number(progress.completed || 0);

    return {
        current_agent: null,
        phase: "cancelled",
        progress: {
            completed,
            total,
            percent: total ? Math.min(100, roundToOneDecimal((completed / total) * 100)) : 0,
        },
        groups,
    };
}

function roundToOneDecimal(value) {
    return Math.round(Number(value || 0) * 10) / 10;
}

function applyStoppedRunState(payload = {}) {
    state.run.cancelled = payload && typeof payload === "object"
        ? payload
        : { message: String(payload || "Analysis was cancelled.") };
    state.run.status = buildCancelledStatus(state.run.status);
    state.run.lastTrackedAgent = null;
    state.run.flashLatestTrace = false;
    state.run.latestTraceId = null;
}

function mergeStatePatch(currentState, patch) {
    if (!patch || typeof patch !== "object") {
        return currentState || {};
    }
    return { ...(currentState || {}), ...patch };
}

function getTaskDetailDescriptor(groupKey, item) {
    if (groupKey === "analysts") {
        const report = REPORT_BY_ANALYST[item.key];
        if (!report) {
            return null;
        }
        return {
            type: "report",
            section: report.section,
            title: report.title,
            subtitle: item.label,
        };
    }

    const keyMap = {
        research: {
            bull: { key: "bullResearch" },
            bear: { key: "bearResearch" },
            manager: { key: "researchManager" },
        },
        trading: {
            trader: { key: "traderPlan" },
        },
        risk: {
            aggressive: { key: "aggressiveRisk" },
            conservative: { key: "conservativeRisk" },
            neutral: { key: "neutralRisk" },
        },
        portfolio: {
            portfolio_manager: { key: "portfolioDecision" },
            portfolio: { key: "portfolioDecision" },
        },
    };

    return keyMap[groupKey]?.[item.key] || null;
}

function buildDetailDataset(detail) {
    if (!detail) {
        return "";
    }
    if (detail.type === "report") {
        return `data-detail-section="${escapeHtml(detail.section)}" data-detail-title="${escapeHtml(detail.title)}" data-detail-subtitle="${escapeHtml(detail.subtitle || detail.title)}"`;
    }
    if (detail.key) {
        return `data-detail-key="${escapeHtml(detail.key)}"`;
    }
    return "";
}

function getRecentStreamMarkdown(limit = 6) {
    const items = getVisibleStreamFeed(limit);
    if (!items.length) {
        return "";
    }
    return items
        .map((item) => `- **${item.title}**: ${compactText(item.content, 180)}`)
        .join("\n");
}

function getCurrentLivePanel() {
    if (state.run.complete?.signal && state.run.sections.final_trade_decision) {
        return {
            title: "Final Decision",
            subtitle: state.run.complete.signal,
            content: state.run.sections.final_trade_decision,
            fallback: "The Portfolio Manager has not finalized a decision yet.",
            detail: { key: "portfolioDecision" },
            tone: "completed",
            badge: "Complete",
        };
    }

    if (state.run.cancelled) {
        return {
            title: "Analysis stopped",
            subtitle: "Cancelled by client",
            content: state.run.cancelled.message || "Analysis was cancelled before completion.",
            fallback: "Analysis was cancelled before completion.",
            detail: null,
            tone: "warning",
            badge: "Stopped",
        };
    }

    const currentAgent = state.run.status?.current_agent;
    const currentAgentNarrative = getAgentNarrativeMarkdown(currentAgent, 5);
    const waitingMessage = currentAgent
        ? `${currentAgent} is calling tools or preparing a response.`
        : "Waiting for the next SSE event from the backend.";

    if (!currentAgent) {
        return {
            title: "Awaiting analysis",
            subtitle: "No active agent",
            content: "",
            fallback: "Run analysis to start the live frontend stream.",
            detail: null,
            tone: "idle",
            badge: "Ready",
        };
    }

    if (currentAgent === "Bull Researcher") {
        return {
            title: currentAgent,
            subtitle: "Research debate is live",
            content: state.run.research.current_response || state.run.research.bull_history || "",
            fallback: "The Bull Researcher has not responded yet.",
            detail: { key: "bullResearch" },
            tone: "live",
            badge: "Live",
        };
    }

    if (currentAgent === "Bear Researcher") {
        return {
            title: currentAgent,
            subtitle: "Research debate is live",
            content: state.run.research.current_response || state.run.research.bear_history || "",
            fallback: "The Bear Researcher has not responded yet.",
            detail: { key: "bearResearch" },
            tone: "live",
            badge: "Live",
        };
    }

    if (currentAgent === "Research Manager") {
        return {
            title: currentAgent,
            subtitle: "Synthesizing the research plan",
            content: state.run.research.judge_decision || state.run.sections.investment_plan || "",
            fallback: "The Research Manager has not synthesized a plan yet.",
            detail: { key: "researchManager" },
            tone: "progress",
            badge: "Live",
        };
    }

    if (currentAgent === "Trader") {
        return {
            title: currentAgent,
            subtitle: "Building the trading proposal",
            content: state.run.sections.trader_investment_plan || currentAgentNarrative || "",
            fallback: "The Trader is analyzing the proposal.",
            detail: { key: "traderPlan" },
            tone: "progress",
            badge: "Live",
        };
    }

    if (currentAgent === "Aggressive Analyst") {
        return {
            title: currentAgent,
            subtitle: "Risk debate is live",
            content: state.run.risk.current_aggressive_response || state.run.risk.aggressive_history || "",
            fallback: "The Aggressive Analyst has not responded yet.",
            detail: { key: "aggressiveRisk" },
            tone: "live",
            badge: "Live",
        };
    }

    if (currentAgent === "Conservative Analyst") {
        return {
            title: currentAgent,
            subtitle: "Risk debate is live",
            content: state.run.risk.current_conservative_response || state.run.risk.conservative_history || "",
            fallback: "The Conservative Analyst has not responded yet.",
            detail: { key: "conservativeRisk" },
            tone: "live",
            badge: "Live",
        };
    }

    if (currentAgent === "Neutral Analyst") {
        return {
            title: currentAgent,
            subtitle: "Risk debate is live",
            content: state.run.risk.current_neutral_response || state.run.risk.neutral_history || "",
            fallback: "The Neutral Analyst has not responded yet.",
            detail: { key: "neutralRisk" },
            tone: "live",
            badge: "Live",
        };
    }

    if (currentAgent === "Portfolio Manager") {
        return {
            title: currentAgent,
            subtitle: "Evaluating final portfolio action",
            content: state.run.sections.final_trade_decision || state.run.risk.judge_decision || currentAgentNarrative || "",
            fallback: "The Portfolio Manager is finalizing the decision.",
            detail: { key: "portfolioDecision" },
            tone: "progress",
            badge: "Live",
        };
    }

    const reportDetail = REPORT_DETAIL_BY_AGENT[currentAgent] || null;
    return {
        title: currentAgent,
        subtitle: "Streaming narrative",
        content: currentAgentNarrative || "",
        fallback: waitingMessage,
        detail: reportDetail,
        tone: currentAgentNarrative ? "live" : "progress",
        badge: "Live",
    };
}

function getVisibleStreamFeed(limit = 12) {
    return state.run.streamFeed
        .filter((item) => {
            const title = String(item.title || "").toLowerCase();
            const content = String(item.content || "").toLowerCase();
            return !title.startsWith("heartbeat") && !content.includes("active graph node");
        })
        .slice(0, limit);
}

function formatBlock(content, fallback = "No content yet.") {
    return renderMarkdown(content, fallback);
}

function appendLog(label, payload, options = {}) {
    const entry = buildLogEntry(label, payload);
    entry.source = options.source || "frontend";
    entry.level = payload && typeof payload === "object" ? payload.level || "info" : "info";
    const fingerprint = payload && typeof payload === "object" && payload.phase === "heartbeat"
        ? buildContentFingerprint(entry.label, entry.summary, payload.elapsed_seconds)
        : buildContentFingerprint(entry.label, entry.summary);
    if (!options.allowDuplicate && fingerprint && state.run.seenLogFingerprints.has(fingerprint)) {
        return;
    }
    if (!options.allowDuplicate && fingerprint) {
        state.run.seenLogFingerprints.add(fingerprint);
    }

    state.run.logEntries = [...state.run.logEntries, entry].slice(-120);
    state.run.logs = [...state.run.logs, entry.detail].slice(-120);
    if (state.activeDetail?.key === "eventLog") {
        renderActiveDetail();
    }
}

function setBusy(isBusy) {
    state.isBusy = isBusy;
    document.body.classList.toggle("is-running", isBusy);
    elements.runAnalysisButton.disabled = isBusy;
    elements.stopAnalysisButton.disabled = !isBusy;
    elements.runFromModalButton.disabled = isBusy;
    elements.saveConfigButton.disabled = isBusy;
    elements.openConfigButton.disabled = isBusy;
}

function showModal(modal) {
    if (!(modal instanceof HTMLElement)) {
        return;
    }
    modal.removeAttribute("inert");
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
}

function hideModal(modal) {
    if (!(modal instanceof HTMLElement)) {
        return;
    }
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    modal.setAttribute("inert", "");
}

function openConfigModal() {
    showModal(elements.configModal);
}

function closeConfigModal() {
    hideModal(elements.configModal);
}

function normalizeRunError(error) {
    const raw = error instanceof Error ? error.message : String(error || "Unknown frontend error.");
    return compactText(raw.replace(/^Error:\s*/i, ""), 520) || "The backend stream ended before the analysis completed.";
}

function openBackendIssueAlert(message) {
    elements.alertTitle.textContent = "Backend Connection Issue";
    elements.alertMessage.textContent = message;
    showModal(elements.alertModal);
}

function closeAlertModal() {
    hideModal(elements.alertModal);
}

function handleRunFailure(error, runId = error?.runId || state.activeRunId) {
    const message = normalizeRunError(error);
    state.run.warnings.unshift(message);
    appendLog(
        "run-error",
        {
            phase: "error",
            message,
            log_line: `analysis run_id=${runId || "unknown"} phase=error message=${message}`,
        },
        { source: "frontend", allowDuplicate: true },
    );
    pushStreamFeed({
        title: "Backend issue",
        content: compactText(message, 220),
        tone: "warning",
    });
    openBackendIssueAlert(message);
    renderAll();
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
    fundamentalsInput.disabled = false;
    card?.classList.remove("checkbox-card-disabled");
}

function renderConfigPreview() {
    if (!state.config) {
        elements.configPreview.innerHTML = "";
        return;
    }

    const payload = collectConfigDraft();
    const depthMap = Object.fromEntries(
        state.config.analysis_options.research_depths.map((item) => [item.value, item.label]),
    );
    const analystLabelMap = Object.fromEntries(
        state.config.analysis_options.analysts.map((item) => [item.value, item.label]),
    );
    const analystNames = payload.selected_analysts.map((key) => analystLabelMap[key] || key);
    const chips = [
        ["Symbol", payload.symbol || "-"],
        ["Window", `${payload.lookback_days || 0}d`],
        ["Language", payload.output_language || "-"],
        ["Depth", depthMap[payload.research_depth] || payload.research_depth],
        ["Model", payload.model || "-"],
        ["Analysts", analystNames.length ? analystNames.join(" / ") : "None selected"],
        ["Checkpoint", payload.checkpoint_enabled ? "On" : "Off"],
    ];

    const notes = [];
    if (!analystNames.length) {
        notes.push("Select at least one analyst before running.");
    }

    elements.configPreview.innerHTML = `
        ${chips
            .map(
                ([label, value]) => `
                    <article class="config-summary-chip" title="${escapeHtml(`${label}: ${value}`)}">
                        <span>${escapeHtml(label)}</span>
                        <strong>${escapeHtml(value)}</strong>
                    </article>
                `,
            )
            .join("")}
        ${notes[0] ? `<p class="config-summary-note">${escapeHtml(notes[0])}</p>` : ""}
    `;
}

function refreshConfigUi() {
    syncLanguageControls();
    syncLookbackPreset();
    syncAnalystAvailability();
    renderTopNotice();
    renderConfigPreview();
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
    elements.phaseText.textContent = state.run.cancelled ? "cancelled" : state.run.status?.phase || "idle";
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

function renderReportGrid() {
    const focus = getCurrentLivePanel();
    const focusId = getFocusIdentity(focus);
    let card = elements.reportGrid.querySelector(".live-focus-card");
    if (!(card instanceof HTMLElement) || card.dataset.focusId !== focusId) {
        elements.reportGrid.innerHTML = `
            <div class="live-layout live-layout-single">
                <article class="live-focus-card live-focus-card-expanded">
                    <div class="live-focus-topline">
                        <span class="live-chip"></span>
                        <span class="live-focus-status"></span>
                    </div>
                    <h3 class="live-focus-title"></h3>
                    <div class="live-focus-body markdown-preview"></div>
                </article>
            </div>
        `;
        card = elements.reportGrid.querySelector(".live-focus-card");
    }

    if (!(card instanceof HTMLElement)) {
        return;
    }

    const liveChip = card.querySelector(".live-chip");
    const liveStatus = card.querySelector(".live-focus-status");
    const liveTitle = card.querySelector(".live-focus-title");
    const liveBody = card.querySelector(".live-focus-body");
    const tone = focus.tone || "idle";
    const bodyMarkup = formatBlock(focus.content, focus.fallback);
    const bodyFingerprint = `${focusId}:${focus.content || ""}:${focus.fallback}`;

    card.dataset.focusId = focusId;
    card.className = `live-focus-card live-focus-card-expanded live-tone-${tone}`;
    card.removeAttribute("tabindex");
    card.removeAttribute("role");
    card.setAttribute("aria-label", focus.title);
    card.removeAttribute("data-detail-key");
    card.removeAttribute("data-detail-section");
    card.removeAttribute("data-detail-title");
    card.removeAttribute("data-detail-subtitle");

    if (liveChip instanceof HTMLElement) {
        liveChip.className = `live-chip live-chip-${tone}`;
        liveChip.textContent = focus.badge || "Live";
    }
    if (liveStatus instanceof HTMLElement) {
        liveStatus.textContent = focus.subtitle || "";
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
    const wasNearBottom = isScrolledNearBottom(element, 48);
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    const previousRects = new Map(
        Array.from(element.children).map((child) => [child.dataset.logKey, child.getBoundingClientRect()]),
    );
    const existingNodes = new Map(
        Array.from(element.querySelectorAll(".event-log-item[data-log-key]")).map((child) => [child.dataset.logKey, child]),
    );

    if (!entries.length) {
        const currentEmpty = element.querySelector(".event-log-empty");
        if (!(currentEmpty instanceof HTMLElement) || currentEmpty.textContent !== emptyText || element.children.length !== 1) {
            element.replaceChildren(createLogEmptyNode(emptyText));
        }
        return;
    }

    const fragment = document.createDocumentFragment();
    const newKeys = new Set();
    entries.forEach((item, index) => {
        const key = getLogEntryKey(item, index);
        let node = existingNodes.get(key);
        if (!(node instanceof HTMLElement)) {
            node = createLogEntryNode();
            newKeys.add(key);
        }
        updateLogEntryNode(node, item, key, useDetail);
        fragment.appendChild(node);
    });

    element.replaceChildren(fragment);

    Array.from(element.children).forEach((child) => {
        if (!(child instanceof HTMLElement)) {
            return;
        }
        const key = child.dataset.logKey;
        if (!key) {
            return;
        }
        if (newKeys.has(key)) {
            child.classList.add("event-log-item-new");
            return;
        }
        const previousRect = previousRects.get(key);
        if (!previousRect || typeof child.animate !== "function") {
            return;
        }
        const nextRect = child.getBoundingClientRect();
        const deltaY = previousRect.top - nextRect.top;
        if (Math.abs(deltaY) > 1) {
            child.animate(
                [{ transform: `translateY(${deltaY}px)` }, { transform: "translateY(0)" }],
                { duration: 380, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
            );
        }
    });

    if (wasNearBottom) {
        requestAnimationFrame(() => {
            element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
        });
    } else {
        element.scrollTop = Math.max(0, element.scrollHeight - element.clientHeight - distanceFromBottom);
    }
}

function renderOperationsRail() {
    const toolFeed = state.run.traceFeed.filter((item) => item.phase === "tool_call" || item.phase === "tool_result");
    const feed = toolFeed.slice(-TRACE_DISPLAY_LIMIT);
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
    elements.eventLogStatusText.textContent = state.run.logEntries.length
        ? `${Math.min(state.run.logEntries.length, LOG_DISPLAY_LIMIT)} recent events`
        : "Recent SSE events";
    elements.executionLogStatusText.textContent = state.run.logEntries.length
        ? `${Math.min(state.run.logEntries.length, EXECUTION_LOG_DISPLAY_LIMIT)} backend lines`
        : "Waiting for stream";

    renderLogEntries(
        elements.eventLog,
        state.run.logEntries.slice(-LOG_DISPLAY_LIMIT),
        "No SSE events yet. Run analysis to start the backend stream.",
    );
    renderLogEntries(
        elements.executionLog,
        state.run.logEntries.slice(-EXECUTION_LOG_DISPLAY_LIMIT),
        "Backend log lines will appear here while analysis is running.",
        { useDetail: true },
    );

    preserveScrollPosition(elements.toolTraceList, () => {
        elements.toolTraceList.innerHTML = feed.length
            ? feed
                  .map((item) => {
                      const shouldFlash = state.run.flashLatestTrace && item.id === state.run.latestTraceId;
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
                        <p>${escapeHtml(compactText(item.content || "", 320))}</p>
                    </article>
                                `;
                                    })
                                    .join("")
                        : '<div class="tool-trace-empty">Agent tool calls and reasoning traces will appear here when the backend stream starts.</div>';
        });
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
    const decision = state.run.sections.final_trade_decision || "The Portfolio Manager has not finalized a decision yet.";
    setCompactPreview(elements.portfolioDecisionPanel, state.run.sections.final_trade_decision, decision, 200);
    elements.signalBadge.textContent = state.run.complete?.signal || "No signal";
}

function renderSmartNotes() {
    const notes = [];
    if (state.run.meta) {
        notes.push(`Market mode: ${state.run.meta.asset_type}`);
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
        notes.push("Open Config to adjust symbol, date, language, analysts, and depth before running analysis.");
    }

    elements.smartNotes.innerHTML = notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("");
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
        return {
            content: formatTraceDetailMarkdown(entry),
            fallback: "This trace is no longer available in the live feed.",
        };
    }

    switch (detail?.key) {
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
        case "portfolioDecision":
            return { content: state.run.sections.final_trade_decision || "", fallback: "The Portfolio Manager has not finalized a decision yet." };
        case "eventLog":
            return { content: formatEventLogMarkdown(), fallback: "No SSE events yet." };
        default:
            return { content: "", fallback: "No data yet." };
    }
}

function formatTraceDetailMarkdown(entry) {
    if (!entry) {
        return "";
    }

    const content = String(entry.content || "").trim();
    const looksStructured = /^[\[{]/.test(content) || /^analysis\s/.test(content);
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

function formatEventLogMarkdown(limit = 80) {
    const entries = state.run.logEntries.slice(-limit);
    if (!entries.length) {
        return "";
    }

    return entries
        .map(
            (entry) => `### ${entry.label}\n- **Time:** ${entry.timestamp}\n- **Summary:** ${entry.summary}`,
        )
        .join("\n\n");
}

function renderActiveDetail() {
    const detail = state.activeDetail;
    if (!detail || elements.detailModal.classList.contains("hidden")) {
        return;
    }

    const meta = detail.type === "report" || detail.type === "trace" ? detail : DETAIL_PANEL_META[detail.key] || {};
    const { content, fallback } = getDetailContent(detail);
    const mode = detail.mode || meta.mode || "markdown";
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
    showModal(elements.detailModal);
    renderActiveDetail();
}

function closeDetailModal() {
    hideModal(elements.detailModal);
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

    const traceId = trigger.dataset.detailTraceId;
    if (traceId) {
        openDetailModal({
            type: "trace",
            traceId,
            title: trigger.dataset.detailTitle || "Tool Detail",
            subtitle: trigger.dataset.detailSubtitle || "Agent tool trace",
            mode: trigger.dataset.detailMode || "markdown",
        });
        return;
    }

    const key = trigger.dataset.detailKey;
    if (key) {
        openDetailModal({ key });
    }
}

function renderAll() {
    renderTopNotice();
    renderProgress();
    renderTeamStatusGrid();
    renderReportGrid();
    renderOperationsRail();
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
        state.run.lastTrackedAgent = data.initial_status?.current_agent || null;
        pushStreamFeed({
            title: "Analysis initialized",
            content: compactText(`${data.symbol} - ${data.asset_type} - ${data.research_depth} depth - ${data.model}`),
            tone: "progress",
        });
        renderAll();
        return;
    }

    if (event === "status_snapshot") {
        state.run.status = data;
        if (data.current_agent && data.current_agent !== state.run.lastTrackedAgent) {
            state.run.lastTrackedAgent = data.current_agent;
            pushStreamFeed({
                title: data.current_agent,
                content: compactText(`${data.phase} phase started.`),
                tone: "progress",
            });
        }
        renderAll();
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
        renderAll();
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
        renderAll();
        return;
    }

    if (event === "warning") {
        state.run.warnings.unshift(data.message || "Unknown warning");
        pushStreamFeed({
            title: "Warning",
            content: compactText(data.message || data, 220),
            tone: "warning",
        });
        renderAll();
        return;
    }

    if (event === "analysis_log") {
        if (data.phase !== "heartbeat") {
            pushStreamFeed({
                title: data.phase || "stream",
                content: compactText(data.message || JSON.stringify(data), 220),
                tone: "progress",
            });
        }
        appendLog(data.phase || event, data, { source: "backend" });
        renderTopNotice();
        renderProgress();
        renderReportGrid();
        renderOperationsRail();
        return;
    }

    if (event === "agent_trace") {
        pushAgentTrace(data);
        renderTopNotice();
        renderProgress();
        renderReportGrid();
        renderOperationsRail();
        return;
    }

    if (event === "complete") {
        state.run.complete = data;
        state.run.cancelled = null;
        state.run.sections = { ...state.run.sections, ...(data.sections_patch || data.sections || {}) };
        state.run.research = mergeStatePatch(state.run.research, data.research_patch || data.research || {});
        state.run.risk = mergeStatePatch(state.run.risk, data.risk_patch || data.risk || {});
        state.run.status = data.status || state.run.status;
        pushStreamFeed({
            title: "Final Decision",
            content: compactText(`${data.signal || "Completed"} - ${data.elapsed_seconds || 0}s`),
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
        elements.lookbackPresetSelect,
        elements.lookbackDaysInput,
        elements.modelInput,
        elements.customLanguageInput,
        elements.checkpointToggle,
        elements.languageSelect,
    ].filter(Boolean).forEach((element) => element.addEventListener("input", sync));
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
    const config = normalizeFrontendConfig();
    state.config = config;
    state.apiBaseUrl = normalizeApiBaseUrl(config.api_base_url || state.apiBaseUrl);

    elements.symbolInput.value = config.analysis_defaults.symbol;
    elements.analysisDateInput.value = config.analysis_defaults.analysis_date;
    populateLookbackPresets(config);
    elements.lookbackDaysInput.value = config.analysis_defaults.lookback_days;
    elements.modelInput.value = config.analysis_defaults.model;
    elements.checkpointToggle.checked = Boolean(config.analysis_defaults.checkpoint_enabled);
    populateLanguageOptions(config);
    populateAnalystOptions(config);
    populateDepthOptions(config);
    bindConfigInputListeners();
    refreshConfigUi();
    renderAll();
}

async function runAnalysis() {
    if (!state.config) {
        return;
    }

    const payload = readConfigForm();
    if (!payload.symbol || !payload.analysis_date || !payload.model) {
        throw new Error("Symbol, analysis date and model are required.");
    }

    if (state.isBusy) {
        return;
    }

    const runId = createRunId();
    const controller = new AbortController();
    payload.run_id = runId;

    state.run = createEmptyRunState();
    state.run.logs = [];
    state.controller = controller;
    state.activeRunId = runId;
    state.stopRequested = false;
    setBusy(true);
    renderAll();

    try {
        const response = await fetch(buildApiUrl("/api/analyze"), {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
            signal: controller.signal,
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || `Backend returned HTTP ${response.status}.`);
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
elements.runAnalysisButton.addEventListener("click", async () => {
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
        handleRunFailure(error);
    }
});
elements.configModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.closeModal === "true") {
        closeConfigModal();
    }
});
elements.closeDetailButton.addEventListener("click", closeDetailModal);
elements.closeAlertButton.addEventListener("click", closeAlertModal);
elements.confirmAlertButton.addEventListener("click", closeAlertModal);
elements.detailModal.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.closeDetail === "true") {
        closeDetailModal();
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