const GROUP_LABELS = {
    analysts: "Signals",
    research: "Research",
    trading: "Trader",
    risk: "Risk",
    portfolio: "Manager",
};

const REPORT_BY_ANALYST = {
    market: { section: "market_report", title: "Market Analysis" },
    social: { section: "sentiment_report", title: "Social Analysis" },
    news: { section: "news_report", title: "News Analysis" },
    fundamentals: { section: "flow_report", title: "Flow Analysis" },
};

const REPORT_DETAIL_BY_AGENT = {
    "Market Analyst": {
        type: "report",
        section: REPORT_BY_ANALYST.market.section,
        title: REPORT_BY_ANALYST.market.title,
        subtitle: "Market Analyst",
    },
    "Social Analyst": {
        type: "report",
        section: REPORT_BY_ANALYST.social.section,
        title: REPORT_BY_ANALYST.social.title,
        subtitle: "Social Analyst",
    },
    "News Analyst": {
        type: "report",
        section: REPORT_BY_ANALYST.news.section,
        title: REPORT_BY_ANALYST.news.title,
        subtitle: "News Analyst",
    },
    "Flow Analyst": {
        type: "report",
        section: REPORT_BY_ANALYST.fundamentals.section,
        title: REPORT_BY_ANALYST.fundamentals.title,
        subtitle: "Flow Analyst",
    },
};

const COMPACT_AGENT_LABELS = {
    "Analyst Team": "Signals",
    "Parallel Analyst Team": "Signals",
    "Market Analyst": "Market",
    "Social Analyst": "Social",
    "News Analyst": "News",
    "Flow Analyst": "Flow",
    "Research Manager": "Lead",
    "Portfolio Manager": "Manager",
    "Verifier": "Verify",
    "Aggressive Analyst": "Aggressive",
    "Conservative Analyst": "Conservative",
    "Neutral Analyst": "Neutral",
};

const STATUS_LABELS = {
    pending: "wait",
    in_progress: "run",
    completed: "done",
};

const FRONTEND_BOOTSTRAP = window.TRADINGAGENTS_CONFIG || {};
const APP_SETTINGS = FRONTEND_BOOTSTRAP.app || {};
const AUTH_SETTINGS = FRONTEND_BOOTSTRAP.auth || {};
const TRADING_VIEW_SETTINGS = FRONTEND_BOOTSTRAP.tradingView || FRONTEND_BOOTSTRAP.trading_view || {};
const CUSTOM_LOOKBACK_VALUE = "__custom__";
const TRACE_DISPLAY_LIMIT = Number(APP_SETTINGS.traceDisplayLimit || APP_SETTINGS.trace_display_limit || 14);
const EXECUTION_LOG_DISPLAY_LIMIT = Number(APP_SETTINGS.executionLogDisplayLimit || APP_SETTINGS.execution_log_display_limit || 80);
const TRACE_FEED_LIMIT = Number(APP_SETTINGS.traceFeedLimit || APP_SETTINGS.trace_feed_limit || 180);
const TRACE_AGENT_LIMIT = Number(APP_SETTINGS.traceAgentLimit || APP_SETTINGS.trace_agent_limit || 80);
const LOG_AUTO_SCROLL_THRESHOLD = 2;
const MIN_ANALYSIS_STOP_DELAY_MS = Math.max(0, Number(APP_SETTINGS.minStopDelayMs || APP_SETTINGS.min_stop_delay_ms || 5000));
const HISTORY_PAGE_SIZE = 20;
const AUTH_STORAGE_KEY = AUTH_SETTINGS.storageKey || AUTH_SETTINGS.storage_key || "tradingagents.googleAuth";
const CHART_SYMBOLS_STORAGE_KEY = TRADING_VIEW_SETTINGS.symbolsStorageKey || TRADING_VIEW_SETTINGS.symbols_storage_key || "tradingagents.chartSymbols";
const PAGES = Array.isArray(APP_SETTINGS.pages) && APP_SETTINGS.pages.length
    ? [...new Set([...APP_SETTINGS.pages, "chat"])]
    : ["agent", "history", "chart", "admin", "chat"];
const DEFAULT_CHART_SYMBOLS = Array.isArray(TRADING_VIEW_SETTINGS.symbols)
    ? TRADING_VIEW_SETTINGS.symbols
    : ["BINANCE:BTCUSDT", "BINANCE:ETHUSDT", "BINANCE:SOLUSDT", "BINANCE:XRPUSDT"];
const DEFAULT_CHART_INTERVAL = String(TRADING_VIEW_SETTINGS.interval || "60");
const TRADING_VIEW_WIDGET_ORIGIN = "https://www.tradingview-widget.com";

const DETAIL_PANEL_META = {
    bullResearch: { title: "Bull Researcher", subtitle: "Research Chamber" },
    bearResearch: { title: "Bear Researcher", subtitle: "Research Chamber" },
    researchManager: { title: "Research Manager", subtitle: "Research Chamber" },
    traderPlan: { title: "Trader Plan", subtitle: "Trader Desk" },
    aggressiveRisk: { title: "Aggressive Analyst", subtitle: "Risk Room" },
    conservativeRisk: { title: "Conservative Analyst", subtitle: "Risk Room" },
    neutralRisk: { title: "Neutral Analyst", subtitle: "Risk Room" },
    portfolioDecision: { title: "Final Decision", subtitle: "Portfolio Management" },
    verifierReport: { title: "Verifier", subtitle: "Portfolio Management" },
    backendLog: { title: "Backend Log", subtitle: "Runtime stream", mode: "markdown" },
    endpointSummaries: { title: "Endpoint Summaries", subtitle: "Compressed source layer" },
    evidenceExtractor: { title: "Evidence Extractor", subtitle: "Structured evidence" },
    evidenceLedger: { title: "Evidence Ledger", subtitle: "Downstream prompt context" },
    researchDebate: { title: "Research Debate", subtitle: "Bull and Bear chamber" },
    riskDebate: { title: "Risk Debate", subtitle: "Risk room discussion" },
    investmentExtractor: { title: "Investment Plan Extractor", subtitle: "Structured handoff" },
    traderExtractor: { title: "Trader Plan Extractor", subtitle: "Structured handoff" },
    decisionExtractor: { title: "Decision Extractor", subtitle: "Structured order fields" },
    verifierStructured: { title: "Verifier Payload", subtitle: "Structured verification" },
    persistence: { title: "History + Decision Persistence", subtitle: "Persistence status" },
    liveCcxtData: { title: "CCXT Market Data", subtitle: "Raw market tool results" },
    liveCoinGlassData: { title: "CoinGlass Data", subtitle: "Endpoint source results" },
    liveNewsData: { title: "News Data", subtitle: "News and web source results" },
    liveSocialData: { title: "Social / Web Data", subtitle: "Social and web source results" },
    liveFlowData: { title: "On-chain Data", subtitle: "Flow and liquidity source results" },
    liveCcxtSummary: { title: "Market Summary", subtitle: "Markdown summary from market source data" },
    liveCoinglassSummary: { title: "Derivatives / Flow Summary", subtitle: "Markdown summary from CoinGlass endpoints" },
    liveNewsSummary: { title: "News Summary", subtitle: "Markdown summary from news sources" },
    liveSocialSummary: { title: "Social Summary", subtitle: "Markdown summary from social and web sources" },
    liveFlowSummary: { title: "Flow Summary", subtitle: "Markdown summary from on-chain and liquidity sources" },
};

const HISTORY_FLOW_SECTION_ORDER = {
    sources: ["endpoint_summaries"],
    inputs: ["market_report", "sentiment_report", "news_report", "flow_report"],
    evidence: ["structured_evidence"],
    research: ["bull_research", "research_debate", "bear_research", "investment_plan", "investment_plan_structured"],
    trading: ["trader_investment_plan", "trader_investment_plan_structured"],
    risk: ["aggressive_risk", "neutral_risk", "conservative_risk", "risk_debate"],
    portfolio: ["final_trade_decision", "final_trade_decision_structured", "verification_report", "verification_report_structured", "history_persistence"],
};

const HISTORY_FLOW_SECTION_META = {
    market_report: {
        shortTitle: "Market",
        tone: "signal",
        icon: "market",
        description: "Price action, technical structure, and market regime context.",
    },
    sentiment_report: {
        shortTitle: "Social",
        tone: "signal",
        icon: "social",
        description: "Social sentiment, crowd positioning, and narrative momentum.",
    },
    news_report: {
        shortTitle: "News",
        tone: "signal",
        icon: "news",
        description: "Catalysts, headlines, and event pressure gathered into one report.",
    },
    flow_report: {
        shortTitle: "Flow",
        tone: "signal",
        icon: "fund",
        description: "On-chain, derivatives, ETF, liquidity, and positioning context.",
    },
    structured_evidence: {
        shortTitle: "Evidence",
        tone: "evidence",
        icon: "evidence",
        description: "Evidence Extractor ledger built from compact source-backed items.",
    },
    endpoint_summaries: {
        shortTitle: "Endpoint Summaries",
        tone: "evidence",
        icon: "evidence",
        description: "Parallel endpoint summary layer prepared before downstream prompts.",
    },
    bull_research: {
        shortTitle: "Bullish",
        tone: "bull",
        icon: "bull",
        description: "The upside case built from the selected analyst evidence.",
    },
    research_debate: {
        shortTitle: "Research Debate",
        tone: "debate",
        icon: "debate",
        description: "The research team exchange before the plan is locked in.",
    },
    bear_research: {
        shortTitle: "Bearish",
        tone: "bear",
        icon: "bear",
        description: "The downside case, failure modes, and invalidation logic.",
    },
    investment_plan: {
        shortTitle: "Investment Plan",
        tone: "plan",
        icon: "plan",
        description: "Research Manager synthesis that converts debate into a trade thesis.",
    },
    trader_investment_plan: {
        shortTitle: "Trader Plan",
        tone: "trader",
        icon: "trade",
        description: "Entry, structure, and transaction proposal prepared for risk review.",
    },
    aggressive_risk: {
        shortTitle: "Aggressive",
        tone: "aggressive",
        icon: "aggressive",
        description: "The high-conviction, higher-risk interpretation of the proposal.",
    },
    neutral_risk: {
        shortTitle: "Neutral",
        tone: "neutral",
        icon: "neutral",
        description: "The balanced baseline view on exposure, sizing, and constraints.",
    },
    conservative_risk: {
        shortTitle: "Conservative",
        tone: "conservative",
        icon: "conservative",
        description: "The capital-protection and drawdown-focused response.",
    },
    risk_debate: {
        shortTitle: "Risk Review",
        tone: "risk",
        icon: "review",
        description: "Merged risk discussion before the final authorization.",
    },
    final_trade_decision: {
        shortTitle: "Final Decision",
        tone: "decision",
        icon: "decision",
        description: "Authorize, reject, or revise the transaction proposal.",
    },
    verification_report: {
        shortTitle: "Verify",
        tone: "review",
        icon: "verify",
        description: "Deterministic and evidence-based verification after the final order plan.",
    },
    investment_plan_structured: {
        shortTitle: "Investment Extract",
        tone: "evidence",
        icon: "evidence",
        description: "Structured fields extracted from the Research Manager plan.",
    },
    trader_investment_plan_structured: {
        shortTitle: "Trader Extract",
        tone: "evidence",
        icon: "evidence",
        description: "Structured fields extracted from the Trader proposal.",
    },
    final_trade_decision_structured: {
        shortTitle: "Decision Extract",
        tone: "evidence",
        icon: "evidence",
        description: "Structured order fields extracted from the Portfolio Manager prose.",
    },
    verification_report_structured: {
        shortTitle: "Verifier Payload",
        tone: "review",
        icon: "verify",
        description: "Structured verification payload saved with the run.",
    },
    history_persistence: {
        shortTitle: "Persistence",
        tone: "review",
        icon: "verify",
        description: "History and structured decision persistence record for this run.",
    },
};

const HISTORY_DIAGRAM_ICONS = {
    market: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 16l4-4 4 2 6-7"></path><path d="M4 20h16"></path></svg>',
    social: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 7h10a3 3 0 0 1 0 6h-4l-4 3v-3H6a3 3 0 0 1 0-6z"></path></svg>',
    news: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h12a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H6z"></path><path d="M9 9h6"></path><path d="M9 13h6"></path><path d="M9 17h4"></path></svg>',
    fund: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h16"></path><path d="M6 20V8l6-4 6 4v12"></path><path d="M9 12v4"></path><path d="M12 12v4"></path><path d="M15 12v4"></path></svg>',
    bull: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 16l5-5 4 4 5-7"></path><path d="M14 8h5v5"></path></svg>',
    debate: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 8h10"></path><path d="M13 4l4 4-4 4"></path><path d="M17 16H7"></path><path d="M11 12l-4 4 4 4"></path></svg>',
    bear: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8l5 5 4-4 5 7"></path><path d="M14 16h5v-5"></path></svg>',
    plan: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="5" width="10" height="15" rx="2"></rect><path d="M10 5.5h4"></path><path d="M10 10h4"></path><path d="M10 14h4"></path></svg>',
    trade: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 8h10"></path><path d="M13 5l3 3-3 3"></path><path d="M18 16H8"></path><path d="M11 13l-3 3 3 3"></path></svg>',
    aggressive: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 3L6 13h5l-1 8 8-11h-5V3z"></path></svg>',
    neutral: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v16"></path><path d="M7 8h10"></path><path d="M5 8l-2 4h4l-2-4z"></path><path d="M19 8l-2 4h4l-2-4z"></path><path d="M8 20h8"></path></svg>',
    conservative: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4l6 2v5c0 4-2.5 7.5-6 9-3.5-1.5-6-5-6-9V6l6-2z"></path><path d="M10 12l2 2 3-4"></path></svg>',
    review: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 6h10"></path><path d="M7 12h10"></path><path d="M7 18h6"></path><path d="M5 6h.01"></path><path d="M5 12h.01"></path><path d="M5 18h.01"></path></svg>',
    evidence: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v14H5z"></path><path d="M8 9h8"></path><path d="M8 13h5"></path><path d="M16 16l2 2 3-4"></path></svg>',
    decision: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8"></circle><path d="M9 12l2 2 4-4"></path></svg>',
    verify: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12l4 4 12-12"></path><path d="M5 5h5"></path><path d="M5 19h14"></path></svg>',
    default: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="3"></rect></svg>',
};

const HISTORY_SIGNAL_WIRE_PATHS = [
    "M0 31 C28 31 50 64 100 66",
    "M0 101 C28 101 50 110 100 112",
    "M0 171 C28 171 50 162 100 160",
    "M0 241 C28 241 50 208 100 206",
];

const HISTORY_STAGE_WIRE_PATH = "M0 50 C28 28 72 72 100 50";
const HISTORY_RISK_WIRE_PATH = "M0 140 C30 116 70 164 100 140";

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
        endpointSummaries: [],
        evidenceItems: [],
        evidenceCount: 0,
        sourceArtifactCount: 0,
        sourceArtifactGroups: {},
        sourceArtifactLists: {},
        sourceArtifactLoading: {},
        sourceArtifactErrors: {},
        sourceSummaryMarkdown: {},
        blockErrors: {},
        flowCompletedSections: new Set(),
        flowCompletedBlocks: new Set(),
        liveFlowSignature: "",
        structured: {},
        seenLogFingerprints: new Set(),
        seenStreamFingerprints: new Set(),
        seenTraceFingerprints: new Set(),
        lastTrackedAgent: null,
        latestReportTitle: null,
        latestTraceId: null,
        flashLatestTrace: false,
    };
}

function createEmptyHistoryState() {
    return {
        items: [],
        loading: false,
        loaded: false,
        error: "",
        page: 1,
        limit: HISTORY_PAGE_SIZE,
        hasMore: false,
        totalCount: 0,
        totalPages: 1,
        activeId: "",
        active: null,
        detailLoading: false,
        cache: {},
    };
}

function createEmptyAdminState() {
    return {
        users: [],
        loading: false,
        loaded: false,
        error: "",
        savingEmail: "",
        historyPublicRead: false,
        historyPolicySaving: false,
    };
}

function createChatMessage(role = "assistant", content = "") {
    const normalizedContent = String(content || "");
    return {
        id: `chat-msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        role,
        content: normalizedContent,
        renderedContent: normalizedContent,
        queuedContent: "",
        thinking: "",
        toolTrace: [],
        thinkingExpanded: false,
        thinkingPinned: false,
        stats: null,
        pendingStats: null,
        createdAt: new Date().toISOString(),
        streamState: role === "assistant" ? "idle" : "ready",
        streamStartedAt: 0,
        firstTokenAt: 0,
        lastChunkAt: 0,
        typingCharsPerSecond: 92,
    };
}

function createChatSession(id = createChatSessionId(), title = "New Chat", messages = []) {
    const timestamp = new Date().toISOString();
    return {
        id,
        title: String(title || "New Chat"),
        messages: Array.isArray(messages) ? messages.map((message) => normalizeChatMessage(message)) : [],
        createdAt: timestamp,
        updatedAt: timestamp,
    };
}

function createInitialChatState() {
    const welcomeId = "chat-welcome";
    const welcomeMessage = createChatMessage(
        "assistant",
        "## Welcome\n\nThis workspace uses the same backend chat endpoint as the integrated dashboard chat.\n\n- Thinking stream\n- Live content stream\n- Token stats\n- Multi-session history\n\nSign in and open the chat as admin to begin.",
    );
    const welcomeSession = createChatSession(
        welcomeId,
        "Welcome Chat",
        [welcomeMessage],
    );
    return {
        sessions: {
            [welcomeId]: welcomeSession,
        },
        order: [welcomeId],
        activeId: welcomeId,
        isStreaming: false,
        isSubmitting: false,
        shouldAutoScroll: true,
        streamBuffer: "",
        currentEvent: "",
        controller: null,
        currentMessageId: "",
        renderedSessionId: "",
        typingTimer: null,
        typingLastTickAt: 0,
        error: "",
    };
}

function normalizeTradingViewSymbol(value = "") {
    const raw = String(value || "").trim().toUpperCase().replace(/\s+/g, "");
    if (!raw) {
        return "";
    }
    if (raw.includes(":")) {
        return raw;
    }
    const compact = raw.replace(/[\/-]/g, "");
    if (compact.endsWith("USDT") || compact.endsWith("USD")) {
        return `BINANCE:${compact.replace(/USD$/, "USDT")}`;
    }
    return `BINANCE:${compact}USDT`;
}

function normalizeTradingViewInterval(value = "") {
    const raw = String(value || "").trim().toUpperCase();
    if (!raw) {
        return "";
    }

    const aliases = {
        D: "1D",
        W: "1W",
        M: "1M",
        "1H": "60",
        "2H": "120",
        "4H": "240",
    };

    if (aliases[raw]) {
        return aliases[raw];
    }

    if (/^\d+$/.test(raw) || /^\d+[DWM]$/.test(raw)) {
        return raw;
    }

    return "";
}

function readStoredChartSymbols() {
    const raw = safeReadLocalStorage(CHART_SYMBOLS_STORAGE_KEY);
    if (!raw) {
        return null;
    }
    try {
        return JSON.parse(raw).map(normalizeTradingViewSymbol).filter(Boolean);
    } catch {
        safeRemoveLocalStorage(CHART_SYMBOLS_STORAGE_KEY);
        return null;
    }
}

function createInitialChartState() {
    const storedSymbols = readStoredChartSymbols();
    const symbols = (storedSymbols && storedSymbols.length ? storedSymbols : DEFAULT_CHART_SYMBOLS)
        .map(normalizeTradingViewSymbol)
        .filter(Boolean);

    return {
        loaded: false,
        loading: false,
        widgetReady: false,
        pendingSymbol: "",
        symbol: symbols[0] || "BINANCE:BTCUSDT",
        interval: normalizeTradingViewInterval(DEFAULT_CHART_INTERVAL) || "60",
        symbols,
        draggingSymbol: "",
        dragOriginalSymbols: [],
        dragCommitted: false,
        dragPointerSymbol: "",
        dragPointerStartX: 0,
        dragPointerStartY: 0,
        dragPointerActive: false,
        suppressNextSymbolClick: false,
    };
}

function safeReadLocalStorage(key) {
    try {
        return window.localStorage.getItem(key);
    } catch {
        return null;
    }
}

function safeWriteLocalStorage(key, value) {
    try {
        window.localStorage.setItem(key, value);
    } catch {
        // Storage may be unavailable in private or embedded browser contexts.
    }
}

function safeRemoveLocalStorage(key) {
    try {
        window.localStorage.removeItem(key);
    } catch {
        // Storage may be unavailable in private or embedded browser contexts.
    }
}

function safeReadSessionStorage(key) {
    try {
        return window.sessionStorage.getItem(key);
    } catch {
        return null;
    }
}

function safeWriteSessionStorage(key, value) {
    try {
        window.sessionStorage.setItem(key, value);
    } catch {
        // Storage may be unavailable in private or embedded browser contexts.
    }
}

function safeRemoveSessionStorage(key) {
    try {
        window.sessionStorage.removeItem(key);
    } catch {
        // Storage may be unavailable in private or embedded browser contexts.
    }
}

function decodeJwtPayload(token = "") {
    try {
        const payload = token.split(".")[1] || "";
        const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
        const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
        const binary = window.atob(padded);
        const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
        return JSON.parse(new TextDecoder().decode(bytes));
    } catch {
        return {};
    }
}

function isJwtExpired(profile = {}) {
    if (isBackendSessionProfile(profile)) {
        return false;
    }
    const expiresAt = Number(profile.exp || 0) * 1000;
    return Boolean(expiresAt && expiresAt <= Date.now() + 30_000);
}

function isBackendSessionProfile(profile = {}) {
    return String(profile.kind || "") === "frontend_session"
        && String(profile.iss || "") === "tradingagents-session";
}

function normalizeAuthProfile(profile = {}) {
    return {
        email: String(profile.email || "").toLowerCase(),
        name: String(profile.name || ""),
        picture: String(profile.picture || ""),
        sub: String(profile.sub || ""),
        exp: profile.exp || null,
        iss: String(profile.iss || ""),
        kind: String(profile.kind || ""),
    };
}

function readStoredAuth() {
    const raw = safeReadLocalStorage(AUTH_STORAGE_KEY) || safeReadSessionStorage(AUTH_STORAGE_KEY);
    if (!raw) {
        return null;
    }
    try {
        const stored = JSON.parse(raw);
        const profile = normalizeAuthProfile(stored.profile || decodeJwtPayload(stored.idToken));
        if (!stored.idToken || isJwtExpired(profile)) {
            safeRemoveSessionStorage(AUTH_STORAGE_KEY);
            safeRemoveLocalStorage(AUTH_STORAGE_KEY);
            return null;
        }
        safeWriteLocalStorage(AUTH_STORAGE_KEY, JSON.stringify({ idToken: stored.idToken, profile }));
        safeRemoveSessionStorage(AUTH_STORAGE_KEY);
        return { idToken: stored.idToken, profile };
    } catch {
        safeRemoveSessionStorage(AUTH_STORAGE_KEY);
        safeRemoveLocalStorage(AUTH_STORAGE_KEY);
        return null;
    }
}

function createInitialAuthState() {
    const stored = readStoredAuth();
    return {
        idToken: stored?.idToken || "",
        profile: stored?.profile || null,
        user: null,
        status: stored ? "stored" : "signed_out",
        isAuthorized: false,
        canRunAnalysis: false,
        isAdmin: false,
        canReadHistory: false,
        historyAccessDays: null,
        historyAccessUnlimited: false,
        initialized: false,
        error: "",
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

function getActiveChatSession() {
    const session = state.chat.sessions[state.chat.activeId] || null;
    if (!session) {
        return null;
    }
    session.messages = (session.messages || []).map((message) => normalizeChatMessage(message));
    return session;
}

function buildChatSessionTitle(session) {
    const firstUserMessage = (session.messages || []).find((message) => message.role === "user" && message.content);
    if (!firstUserMessage) {
        return session.title || "New Chat";
    }
    return compactText(stripMarkdownToPlainText(firstUserMessage.content), 34) || "New Chat";
}

function upsertChatSession(session, options = {}) {
    if (options.touch !== false) {
        session.updatedAt = new Date().toISOString();
    }
    state.chat.sessions[session.id] = session;
    state.chat.order = [session.id, ...state.chat.order.filter((item) => item !== session.id)];
}

function createChatSessionId() {
    return `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function normalizeChatMessage(message) {
    if (!message || typeof message !== "object") {
        return createChatMessage("assistant", "");
    }
    if (typeof message.content !== "string") {
        message.content = String(message.content || "");
    }
    if (typeof message.renderedContent !== "string") {
        message.renderedContent = message.content;
    }
    if (typeof message.queuedContent !== "string") {
        message.queuedContent = "";
    }
    if (typeof message.thinking !== "string") {
        message.thinking = String(message.thinking || "");
    }
    if (!Array.isArray(message.toolTrace)) {
        message.toolTrace = [];
    }
    if (typeof message.thinkingExpanded !== "boolean") {
        message.thinkingExpanded = false;
    }
    if (typeof message.thinkingPinned !== "boolean") {
        message.thinkingPinned = false;
    }
    if (!("pendingStats" in message)) {
        message.pendingStats = null;
    }
    if (typeof message.streamStartedAt !== "number") {
        message.streamStartedAt = 0;
    }
    if (typeof message.firstTokenAt !== "number") {
        message.firstTokenAt = 0;
    }
    if (typeof message.streamState !== "string") {
        message.streamState = message.role === "assistant" ? "idle" : "ready";
    }
    if (typeof message.lastChunkAt !== "number") {
        message.lastChunkAt = 0;
    }
    if (typeof message.typingCharsPerSecond !== "number") {
        message.typingCharsPerSecond = 92;
    }
    return message;
}

function getChatModel() {
    const fromSelect = String(elements.chatModelSelect?.value || "").trim();
    if (fromSelect) {
        return fromSelect;
    }
    return String(state.config?.analysis_defaults?.model || state.config?.default_model || "MiniMax-M2.5");
}

function updateChatComposerState() {
    if (!(elements.chatInput instanceof HTMLTextAreaElement) || !(elements.chatSendButton instanceof HTMLButtonElement)) {
        return;
    }
    const hasText = Boolean(elements.chatInput.value.trim());
    const canUse = Boolean(state.auth.isAdmin && state.auth.idToken);
    const isLocked = Boolean(state.chat.isStreaming || state.chat.isSubmitting);
    elements.chatSendButton.disabled = !hasText || !canUse || isLocked;
    if (elements.chatModelSelect instanceof HTMLSelectElement) {
        elements.chatModelSelect.disabled = !canUse || isLocked;
    }
    elements.chatInput.disabled = !canUse || isLocked;
    elements.chatInput.setAttribute("aria-busy", isLocked ? "true" : "false");
    if (state.chat.isSubmitting) {
        elements.chatInput.placeholder = "Preparing response...";
    } else if (state.chat.isStreaming) {
        elements.chatInput.placeholder = "Assistant is responding...";
    } else if (!state.auth.idToken) {
        elements.chatInput.placeholder = "Sign in with Google to use chat...";
    } else if (!state.auth.isAdmin) {
        elements.chatInput.placeholder = "Admin permission is required for chat.";
    } else {
        elements.chatInput.placeholder = "Send a message...";
    }
}

function scrollChatToBottom(force = false) {
    if (!(elements.chatMessages instanceof HTMLElement)) {
        return;
    }
    if (force || state.chat.shouldAutoScroll) {
        elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
    }
}

function highlightChatCodeBlocks(root) {
    if (!window.hljs || !(root instanceof HTMLElement)) {
        return;
    }
    root.querySelectorAll("pre code").forEach((block) => {
        if (!block.classList.contains("hljs")) {
            window.hljs.highlightElement(block);
        }
    });
}

function getChatMessageElement(messageId) {
    if (!(elements.chatMessages instanceof HTMLElement) || !messageId) {
        return null;
    }
    return elements.chatMessages.querySelector(`[data-chat-message-id="${messageId}"]`);
}

function isChatMessageActive(message) {
    return message.role === "assistant" && (state.chat.currentMessageId === message.id || message.streamState === "streaming" || message.streamState === "settling" || Boolean(message.queuedContent));
}

function formatChatToolTraceValue(value) {
    if (value == null || value === "") {
        return "";
    }
    if (typeof value === "string") {
        return value;
    }
    try {
        return JSON.stringify(value, null, 2);
    } catch {
        return String(value);
    }
}

function buildChatThinkingDisplay(message) {
    const toolTrace = Array.isArray(message.toolTrace)
        ? message.toolTrace.filter((entry) => typeof entry === "string" && entry.trim()).join("\n\n")
        : "";
    const thinking = String(message.thinking || "").trim();
    if (toolTrace && thinking) {
        return `${toolTrace}\n\n${thinking}`;
    }
    return toolTrace || thinking;
}

function getChatMessageStatusLabel(message) {
    if (message.role !== "assistant") {
        return "";
    }
    if (message.streamState === "error") {
        return "Error";
    }
    if (message.streamState === "settling" && message.queuedContent) {
        return "Typing";
    }
    if (message.streamState === "settling") {
        return "Finishing";
    }
    if (message.streamState === "streaming" && !message.renderedContent && buildChatThinkingDisplay(message)) {
        return "Thinking";
    }
    if (message.streamState === "streaming" && message.queuedContent) {
        return "Typing";
    }
    if (message.streamState === "streaming") {
        return "Responding";
    }
    if (message.stats) {
        return "Complete";
    }
    return "";
}

function renderChatStatsMarkup(stats) {
    if (!stats) {
        return "";
    }
    const totalTime = Number(stats.totalTime || 0);
    return `
        <span>Speed ${escapeHtml(String(stats.tokensPerSecond))} tok/s</span>
        <span>Tokens ${escapeHtml(String(stats.tokens))} ${stats.estimated ? "est" : "tok"}</span>
        <span>Gen ${escapeHtml(String(stats.generationTime))}s</span>
        ${totalTime > 0 ? `<span>Total ${escapeHtml(String(totalTime))}s</span>` : ""}
    `;
}

function renderUserChatAvatarMarkup() {
    return `
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path fill="currentColor" d="M12 12c2.76 0 5-2.24 5-5S14.76 2 12 2 7 4.24 7 7s2.24 5 5 5Zm0 2c-3.34 0-10 1.68-10 5v1c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2v-1c0-3.32-6.66-5-10-5Z"></path>
        </svg>
    `;
}

function renderChatAvatarMarkup(message) {
    if (message.role === "assistant") {
        return '<img class="chat-avatar-image chat-avatar-logo" src="image/LOGO.png" alt="" loading="lazy">';
    }
    return renderUserChatAvatarMarkup();
}

function buildFallbackChatStats(message) {
    const content = String(message.content || message.renderedContent || "").trim();
    if (!content) {
        return null;
    }
    const endTime = performance.now();
    const streamStartedAt = Number(message.streamStartedAt || 0) || endTime;
    const firstTokenAt = Number(message.firstTokenAt || 0) || streamStartedAt;
    const generationTime = Math.max(0.01, (endTime - firstTokenAt) / 1000);
    const totalTime = Math.max(generationTime, (endTime - streamStartedAt) / 1000);
    const tokens = Math.max(1, Math.round(content.length / 4));
    return {
        tokensPerSecond: Number((tokens / generationTime).toFixed(2)),
        tokens,
        generationTime: Number(generationTime.toFixed(2)),
        totalTime: Number(totalTime.toFixed(2)),
        estimated: true,
    };
}

function createChatMessageElement(message) {
    const article = document.createElement("article");
    article.className = `chat-row ${message.role}`;
    article.dataset.chatMessageId = message.id;
    article.innerHTML = `
        <div class="chat-avatar ${message.role === "assistant" ? "is-assistant" : "is-user"}" aria-hidden="true">
            ${renderChatAvatarMarkup(message)}
        </div>
        <div class="chat-bubble">
            <div class="chat-bubble-header">
                <span class="chat-author">${message.role === "assistant" ? "TradingAgents Assistant" : "You"}</span>
                <span class="chat-stream-badge" hidden></span>
            </div>
            <div class="chat-thinking" hidden>
                <button type="button" class="chat-thinking-toggle" data-chat-thinking-toggle="${escapeHtml(message.id)}" aria-expanded="false">
                    <span class="chat-thinking-label">Thinking trace</span>
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"></path></svg>
                </button>
                <pre class="chat-thinking-body"></pre>
            </div>
            <div class="chat-message-body markdown-preview"></div>
            <div class="chat-stats" hidden></div>
            <div class="chat-meta"></div>
        </div>
    `;
    updateChatMessageElement(message, { element: article, forceHighlight: true, forceBodyUpdate: true });
    return article;
}

function updateChatMessageElement(message, options = {}) {
    const article = options.element instanceof HTMLElement ? options.element : getChatMessageElement(message.id);
    if (!(article instanceof HTMLElement)) {
        return;
    }

    const avatar = article.querySelector(".chat-avatar");
    const bubble = article.querySelector(".chat-bubble");
    const body = article.querySelector(".chat-message-body");
    const thinkingBlock = article.querySelector(".chat-thinking");
    const thinkingLabel = article.querySelector(".chat-thinking-label");
    const thinkingButton = article.querySelector(".chat-thinking-toggle");
    const thinkingBody = article.querySelector(".chat-thinking-body");
    const statsBlock = article.querySelector(".chat-stats");
    const meta = article.querySelector(".chat-meta");
    const badge = article.querySelector(".chat-stream-badge");
    const isActive = isChatMessageActive(message);
    const displayContent = typeof message.renderedContent === "string" ? message.renderedContent : String(message.content || "");
    const thinkingDisplay = buildChatThinkingDisplay(message);
    const hasThinking = Boolean(thinkingDisplay.trim());

    article.classList.toggle("is-streaming", isActive);
    article.classList.toggle("is-finished", Boolean(message.stats));
    if (avatar instanceof HTMLElement) {
        avatar.classList.toggle("is-user", message.role === "user");
        avatar.classList.toggle("is-assistant", message.role === "assistant");
        const nextAvatarKey = `${message.role}`;
        if (avatar.dataset.chatAvatarKey !== nextAvatarKey) {
            avatar.innerHTML = renderChatAvatarMarkup(message);
            avatar.dataset.chatAvatarKey = nextAvatarKey;
        }
    }
    bubble?.classList.toggle("has-thinking", hasThinking);

    if (badge instanceof HTMLElement) {
        const label = getChatMessageStatusLabel(message);
        badge.hidden = !label;
        badge.textContent = label;
        badge.dataset.state = message.streamState || "idle";
    }

    if (thinkingBlock instanceof HTMLElement && thinkingLabel instanceof HTMLElement && thinkingButton instanceof HTMLButtonElement && thinkingBody instanceof HTMLElement) {
        const wasNearBottom = thinkingBody.scrollHeight - thinkingBody.scrollTop - thinkingBody.clientHeight < 20;
        const previousScrollTop = thinkingBody.scrollTop;
        thinkingBlock.hidden = !hasThinking;
        thinkingBlock.classList.toggle("is-collapsed", !message.thinkingExpanded);
        thinkingLabel.textContent = message.thinkingExpanded
            ? (message.streamState === "streaming" ? "Thinking live" : "Thinking trace")
            : "Thinking";
        thinkingButton.setAttribute("aria-expanded", message.thinkingExpanded ? "true" : "false");
        if (thinkingBody.textContent !== thinkingDisplay) {
            thinkingBody.textContent = thinkingDisplay;
            if (message.thinkingExpanded) {
                if (wasNearBottom) {
                    thinkingBody.scrollTop = thinkingBody.scrollHeight;
                } else {
                    thinkingBody.scrollTop = previousScrollTop;
                }
            }
        }
    }

    if (body instanceof HTMLElement) {
        const bodyStreaming = message.role === "assistant" && isActive;
        const nextBodyKey = `${bodyStreaming ? "streaming" : "ready"}:${displayContent}`;
        if (options.forceBodyUpdate || body.dataset.chatBodyKey !== nextBodyKey) {
            setMarkdownPreview(body, displayContent, bodyStreaming ? "Waiting for response..." : message.role === "assistant" ? "..." : "");
            body.dataset.chatBodyKey = nextBodyKey;
            if (!bodyStreaming || options.forceHighlight) {
                highlightChatCodeBlocks(body);
            }
        }
        body.classList.toggle("is-typing", bodyStreaming);
    }

    if (statsBlock instanceof HTMLElement) {
        statsBlock.hidden = !message.stats;
        statsBlock.innerHTML = message.stats ? renderChatStatsMarkup(message.stats) : "";
    }

    if (meta instanceof HTMLElement) {
        meta.textContent = formatHistoryTimestamp(message.createdAt);
    }
}

function renderChatHistoryList() {
    if (!(elements.chatHistoryList instanceof HTMLElement)) {
        return;
    }
    const sessions = state.chat.order
        .map((id) => state.chat.sessions[id])
        .filter(Boolean)
        .sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
    if (!sessions.length) {
        elements.chatHistoryList.innerHTML = '<div class="chat-empty">No chat sessions yet.</div>';
        return;
    }
    const isLocked = Boolean(state.chat.isStreaming || state.chat.isSubmitting);
    elements.chatHistoryList.innerHTML = sessions.map((session) => {
        const title = buildChatSessionTitle(session);
        const isActive = session.id === state.chat.activeId;
        const meta = formatHistoryTimestamp(session.updatedAt);
        const isDisabled = isLocked;
        return `
            <button type="button" class="chat-session-item ${isActive ? "is-active" : ""}" data-chat-session-id="${escapeHtml(session.id)}" ${isDisabled ? "disabled" : ""}>
                <span class="chat-session-title">${escapeHtml(title)}</span>
                <span class="chat-session-meta">${escapeHtml(meta)}</span>
            </button>
        `;
    }).join("");
}

function renderChatMessages(forceFull = false) {
    if (!(elements.chatMessages instanceof HTMLElement)) {
        return;
    }
    const session = getActiveChatSession();
    if (!session) {
        state.chat.renderedSessionId = "";
        elements.chatMessages.innerHTML = '<div class="chat-empty">No active chat session.</div>';
        return;
    }
    if (!session.messages.length) {
        state.chat.renderedSessionId = session.id;
        elements.chatMessages.innerHTML = '<div class="chat-empty">Start with a prompt to begin streaming responses.</div>';
        return;
    }

    const shouldRebuild = forceFull || state.chat.renderedSessionId !== session.id;
    if (shouldRebuild) {
        elements.chatMessages.innerHTML = "";
    }

    const expectedIds = new Set(session.messages.map((message) => message.id));
    Array.from(elements.chatMessages.children).forEach((child) => {
        if (!(child instanceof HTMLElement)) {
            return;
        }
        const messageId = child.dataset.chatMessageId || "";
        if (messageId && !expectedIds.has(messageId)) {
            child.remove();
        }
    });

    session.messages.forEach((message, index) => {
        let element = getChatMessageElement(message.id);
        if (!(element instanceof HTMLElement)) {
            element = createChatMessageElement(message);
        } else {
            updateChatMessageElement(message);
        }
        if (elements.chatMessages.children[index] !== element) {
            elements.chatMessages.insertBefore(element, elements.chatMessages.children[index] || null);
        }
    });

    state.chat.renderedSessionId = session.id;
    scrollChatToBottom();
}

function renderChatPage() {
    if (!(elements.chatPage instanceof HTMLElement)) {
        return;
    }
    const isLocked = Boolean(state.chat.isStreaming || state.chat.isSubmitting);
    const session = getActiveChatSession();
    elements.chatPage.classList.toggle("is-busy", isLocked);
    if (elements.chatCurrentTitle instanceof HTMLElement) {
        elements.chatCurrentTitle.textContent = session ? buildChatSessionTitle(session) : "Welcome Chat";
    }
    if (elements.chatStatusText instanceof HTMLElement) {
        if (state.chat.isSubmitting) {
            elements.chatStatusText.textContent = "Preparing response";
        } else if (state.chat.isStreaming) {
            elements.chatStatusText.textContent = "Streaming response";
        } else if (!state.auth.idToken) {
            elements.chatStatusText.textContent = "Sign in required";
        } else if (!state.auth.isAdmin) {
            elements.chatStatusText.textContent = "Admin only";
        } else {
            elements.chatStatusText.textContent = "Ready";
        }
    }
    if (elements.chatNewButton instanceof HTMLButtonElement) {
        elements.chatNewButton.disabled = isLocked;
    }
    renderChatHistoryList();
    renderChatMessages();
    updateChatComposerState();
}

function createNewChatSession() {
    if (state.chat.isStreaming || state.chat.isSubmitting) {
        return;
    }
    const id = createChatSessionId();
    const session = createChatSession(id);
    upsertChatSession(session);
    state.chat.activeId = id;
    state.chat.renderedSessionId = "";
    renderChatPage();
}

function selectChatSession(id) {
    if (!id || !state.chat.sessions[id] || state.chat.isStreaming || state.chat.isSubmitting) {
        return;
    }
    state.chat.activeId = id;
    state.chat.renderedSessionId = "";
    renderChatPage();
    scrollChatToBottom(true);
}

function toggleThinkingMessage(messageId) {
    const session = getActiveChatSession();
    if (!session) {
        return;
    }
    const message = session.messages.find((item) => item.id === messageId);
    if (!message) {
        return;
    }
    message.thinkingExpanded = !message.thinkingExpanded;
    message.thinkingPinned = true;
    if (message.thinkingExpanded && state.chat.currentMessageId === message.id) {
        state.chat.shouldAutoScroll = false;
    }
    updateChatMessageElement(message);
}

function getCurrentStreamingChatMessage() {
    const session = getActiveChatSession();
    if (!session || !state.chat.currentMessageId) {
        return null;
    }
    return session.messages.find((message) => message.id === state.chat.currentMessageId) || null;
}

function stopChatTypingPump() {
    if (state.chat.typingTimer) {
        window.clearInterval(state.chat.typingTimer);
        state.chat.typingTimer = null;
    }
    state.chat.typingLastTickAt = 0;
}

function startChatTypingPump() {
    if (state.chat.typingTimer) {
        return;
    }
    state.chat.typingLastTickAt = performance.now();
    state.chat.typingTimer = window.setInterval(processChatTypingTick, 32);
}

function setChatMessageTargetContent(message, nextContent) {
    const targetContent = String(nextContent || "");
    const visibleContent = String(message.renderedContent || "");
    message.content = targetContent;
    if (targetContent.startsWith(visibleContent)) {
        message.queuedContent = targetContent.slice(visibleContent.length);
        return;
    }
    message.renderedContent = "";
    message.queuedContent = targetContent;
}

function updateChatTypingMetrics(message, chunkLength) {
    const now = performance.now();
    if (!message.lastChunkAt) {
        message.typingCharsPerSecond = Math.max(90, Math.min(220, chunkLength * 18));
        message.lastChunkAt = now;
        return;
    }
    const elapsedMs = Math.max(24, now - message.lastChunkAt);
    const incomingCharsPerSecond = (chunkLength * 1000) / elapsedMs;
    message.typingCharsPerSecond = Math.max(42, Math.min(720, (message.typingCharsPerSecond * 0.58) + (incomingCharsPerSecond * 0.42)));
    message.lastChunkAt = now;
}

function getChatTypingSpeed(message) {
    const baseSpeed = Math.max(46, Math.min(420, message.typingCharsPerSecond || 92));
    const backlogBoost = Math.min(420, Math.pow(Math.max(message.queuedContent.length, 0), 0.88) * 7.2);
    return Math.min(760, baseSpeed + backlogBoost);
}

function finalizeStreamingMessage(session, message) {
    if (message.pendingStats) {
        message.stats = message.pendingStats;
        message.pendingStats = null;
    } else if (!message.stats) {
        message.stats = buildFallbackChatStats(message);
    }
    if (message.streamState !== "error") {
        message.streamState = "complete";
    }
    message.renderedContent = message.content || message.renderedContent || "";
    message.queuedContent = "";
    if (state.chat.currentMessageId === message.id) {
        state.chat.currentMessageId = "";
        state.chat.isStreaming = false;
        state.chat.controller = null;
        stopChatTypingPump();
    }
    upsertChatSession(session);
    updateChatMessageElement(message, { forceHighlight: true, forceBodyUpdate: true });
    renderChatPage();
}

function maybeFinalizeStreamingMessage(session, message) {
    if (!message || message.queuedContent) {
        return false;
    }
    if (message.streamState !== "settling" && message.streamState !== "error") {
        return false;
    }
    finalizeStreamingMessage(session, message);
    return true;
}

function processChatTypingTick() {
    const session = getActiveChatSession();
    const message = getCurrentStreamingChatMessage();
    if (!session || !message) {
        stopChatTypingPump();
        return;
    }

    const now = performance.now();
    const previousTick = state.chat.typingLastTickAt || now;
    const elapsedMs = Math.max(16, now - previousTick);
    state.chat.typingLastTickAt = now;

    if (message.queuedContent) {
        const stepSize = Math.max(1, Math.round((getChatTypingSpeed(message) * elapsedMs) / 1000));
        const nextChunk = message.queuedContent.slice(0, stepSize);
        message.renderedContent += nextChunk;
        message.queuedContent = message.queuedContent.slice(nextChunk.length);
        updateChatMessageElement(message, { forceBodyUpdate: true });
        scrollChatToBottom();
    }

    if (maybeFinalizeStreamingMessage(session, message)) {
        return;
    }

    if (!message.queuedContent && message.streamState !== "streaming") {
        stopChatTypingPump();
    }
}

function parseChatSseBlocks(buffer) {
    const blocks = [];
    let working = buffer;
    let delimiterIndex = working.indexOf("\n\n");
    while (delimiterIndex !== -1) {
        const block = working.slice(0, delimiterIndex).trim();
        if (block) {
            blocks.push(block);
        }
        working = working.slice(delimiterIndex + 2);
        delimiterIndex = working.indexOf("\n\n");
    }
    return { blocks, rest: working };
}

function parseChatSseEvent(block) {
    let event = "message";
    const dataLines = [];
    const lines = block.split(/\r?\n/);
    for (const line of lines) {
        if (line.startsWith("event:")) {
            event = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trimStart());
        }
    }
    let data = {};
    if (dataLines.length) {
        try {
            data = JSON.parse(dataLines.join("\n"));
        } catch {
            data = {};
        }
    }
    return { event, data };
}

async function sendChatMessage() {
    if (!(elements.chatInput instanceof HTMLTextAreaElement)) {
        return;
    }
    const prompt = elements.chatInput.value.trim();
    if (!prompt || state.chat.isStreaming || state.chat.isSubmitting) {
        return;
    }

    state.chat.isSubmitting = true;
    state.chat.error = "";
    renderChatPage();

    try {
        await ensureAuthorizedSession();
    } catch (error) {
        state.chat.isSubmitting = false;
        renderChatPage();
        const message = error instanceof Error ? error.message : String(error || "Sign in with Google before using chat.");
        openAuthRequiredAlert(message);
        return;
    }
    if (!state.auth.isAdmin) {
        state.chat.isSubmitting = false;
        renderChatPage();
        openAuthRequiredAlert("Admin permission is required to use Chat.");
        return;
    }

    let session = getActiveChatSession();
    if (!session) {
        createNewChatSession();
        session = getActiveChatSession();
    }
    if (!session) {
        state.chat.isSubmitting = false;
        renderChatPage();
        return;
    }

    const userMessage = createChatMessage("user", prompt);
    const assistantMessage = createChatMessage("assistant", "");
    assistantMessage.streamState = "streaming";
    assistantMessage.streamStartedAt = performance.now();
    session.messages.push(userMessage, assistantMessage);
    session.title = buildChatSessionTitle(session);
    upsertChatSession(session);

    elements.chatInput.value = "";
    elements.chatInput.style.height = "auto";

    state.chat.isSubmitting = false;
    state.chat.isStreaming = true;
    state.chat.error = "";
    state.chat.currentMessageId = assistantMessage.id;
    state.chat.streamBuffer = "";
    state.chat.currentEvent = "";
    state.chat.shouldAutoScroll = true;
    state.chat.controller = new AbortController();
    stopChatTypingPump();
    renderChatPage();

    try {
        const payloadMessages = session.messages
            .filter((message) => message.role === "user" || message.role === "assistant")
            .map((message) => ({ role: message.role, content: message.content || "" }));
        const response = await apiFetch("/api/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...getAuthHeaders(),
            },
            body: JSON.stringify({
                messages: payloadMessages,
                model: getChatModel(),
                max_tokens: Number(state.config?.chat?.max_tokens || 8000),
                temperature: 0.7,
                stream: true,
            }),
            signal: state.chat.controller.signal,
        });

        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }

        if (!response.body) {
            throw new Error("Chat stream is not available right now.");
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            state.chat.streamBuffer += decoder.decode(value || new Uint8Array(), { stream: !done });
            const parsed = parseChatSseBlocks(state.chat.streamBuffer);
            state.chat.streamBuffer = parsed.rest;

            for (const block of parsed.blocks) {
                const eventPayload = parseChatSseEvent(block);
                const message = session.messages.find((item) => item.id === assistantMessage.id);
                if (!message) {
                    continue;
                }
                if (eventPayload.event === "thinking") {
                    if (!message.firstTokenAt) {
                        message.firstTokenAt = performance.now();
                    }
                    message.thinking += String(eventPayload.data?.content || "");
                    message.streamState = "streaming";
                    if (!message.thinkingPinned) {
                        message.thinkingExpanded = true;
                    }
                    updateChatMessageElement(message);
                } else if (eventPayload.event === "tool_use") {
                    if (!message.firstTokenAt) {
                        message.firstTokenAt = performance.now();
                    }
                    const toolName = String(eventPayload.data?.tool || eventPayload.data?.requested_tool || "tool");
                    const toolInput = formatChatToolTraceValue(eventPayload.data?.input || {});
                    const traceLines = [`Tool call: ${toolName}`];
                    if (toolInput && toolInput !== "{}") {
                        traceLines.push(`Input: ${toolInput}`);
                    }
                    message.toolTrace.push(traceLines.join("\n"));
                    message.streamState = "streaming";
                    if (!message.thinkingPinned) {
                        message.thinkingExpanded = true;
                    }
                    updateChatMessageElement(message);
                } else if (eventPayload.event === "tool_result") {
                    if (!message.firstTokenAt) {
                        message.firstTokenAt = performance.now();
                    }
                    const toolName = String(eventPayload.data?.tool || eventPayload.data?.requested_tool || "tool");
                    const summary = formatToolResultPlainText(eventPayload.data?.content || "", 360);
                    const traceLines = [`Tool result: ${toolName}`];
                    if (summary) {
                        traceLines.push(summary);
                    }
                    message.toolTrace.push(traceLines.join("\n"));
                    message.streamState = "streaming";
                    if (!message.thinkingPinned) {
                        message.thinkingExpanded = true;
                    }
                    updateChatMessageElement(message);
                } else if (eventPayload.event === "content") {
                    const nextChunk = String(eventPayload.data?.content || "");
                    if (!nextChunk) {
                        continue;
                    }
                    if (!message.firstTokenAt) {
                        message.firstTokenAt = performance.now();
                    }
                    setChatMessageTargetContent(message, `${message.content || ""}${nextChunk}`);
                    updateChatTypingMetrics(message, nextChunk.length);
                    message.streamState = "streaming";
                    updateChatMessageElement(message);
                    startChatTypingPump();
                } else if (eventPayload.event === "complete") {
                    setChatMessageTargetContent(message, String(eventPayload.data?.text || message.content || ""));
                    message.thinking = String(eventPayload.data?.thinking || message.thinking || "");
                    message.pendingStats = {
                        tokensPerSecond: Number(eventPayload.data?.tokens_per_second || 0),
                        tokens: Number(eventPayload.data?.tokens || 0),
                        generationTime: Number(eventPayload.data?.generation_time || 0),
                        totalTime: Number(eventPayload.data?.total_time || 0),
                        estimated: Boolean(eventPayload.data?.tokens_estimated),
                    };
                    message.streamState = "settling";
                    updateChatMessageElement(message);
                    if (message.queuedContent) {
                        startChatTypingPump();
                    } else {
                        maybeFinalizeStreamingMessage(session, message);
                    }
                } else if (eventPayload.event === "error") {
                    throw new Error(String(eventPayload.data?.error || "Chat stream returned an error."));
                }
                upsertChatSession(session, { touch: false });
            }

            if (done) {
                const finalMessage = session.messages.find((item) => item.id === assistantMessage.id);
                if (finalMessage && finalMessage.streamState === "streaming") {
                    finalMessage.streamState = "settling";
                    if (!finalMessage.queuedContent) {
                        maybeFinalizeStreamingMessage(session, finalMessage);
                    }
                }
                break;
            }
        }
    } catch (error) {
        const message = error instanceof Error ? error.message : String(error || "Chat request failed.");
        const target = session.messages.find((item) => item.id === assistantMessage.id);
        if (target) {
            if (!target.content.trim() && !target.renderedContent.trim()) {
                target.content = `Error: ${message}`;
                target.renderedContent = target.content;
            }
            target.queuedContent = "";
            target.pendingStats = null;
            target.streamState = "error";
            updateChatMessageElement(target, { forceBodyUpdate: true, forceHighlight: true });
        }
        state.chat.error = message;
        state.chat.isStreaming = false;
        state.chat.controller = null;
        state.chat.currentMessageId = "";
        stopChatTypingPump();
        openBackendIssueAlert(message);
    } finally {
        state.chat.isSubmitting = false;
        upsertChatSession(session);
        renderChatPage();
    }
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

