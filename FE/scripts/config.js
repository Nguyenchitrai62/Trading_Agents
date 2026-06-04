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

function normalizeAnalystKeys(values) {
    const source = Array.isArray(values) && values.length ? values : ["market", "onchain", "social", "news"];
    return [...new Set(source
        .map((value) => String(value || "").trim().toLowerCase())
        .filter(Boolean))];
}

function normalizeAnalystOptions(values) {
    const source = Array.isArray(values) && values.length
        ? values
        : [
            { value: "market", label: "Market Analyst" },
            { value: "onchain", label: "Onchain Analyst" },
            { value: "social", label: "Social Analyst" },
            { value: "news", label: "News Analyst" },
        ];
    const seen = new Set();
    return source.map((analyst) => {
        const rawValue = String(analyst.value || "").trim().toLowerCase();
        const value = rawValue;
        const label = analyst.label;
        return { ...analyst, value, label };
    }).filter((analyst) => {
        if (!analyst.value || seen.has(analyst.value)) {
            return false;
        }
        seen.add(analyst.value);
        return true;
    });
}

function normalizeFrontendConfig() {
    const source = getFrontendConfigSource();
    const defaults = source.analysisDefaults || source.analysis_defaults || {};
    const options = source.analysisOptions || source.analysis_options || {};
    const tradingView = source.tradingView || source.trading_view || {};
    const defaultModel = source.defaultModel || source.default_model || defaults.model || "MiniMax-M2.5";

    return {
        configured: true,
        provider: source.provider || "minimax",
        api_base_url: getConfiguredApiBaseUrl(),
        default_model: defaultModel,
        chat: {
            max_tokens: Number(source.chat?.maxTokens || source.chat?.max_tokens || 8000),
        },
        auth: {
            google_client_id: "",
        },
        history: {
            configured: Boolean(source.history?.configured ?? false),
            public_read: Boolean(source.history?.publicRead ?? source.history?.public_read ?? false),
            require_login: Boolean(source.history?.requireLogin ?? source.history?.require_login ?? true),
            page_size: Number(source.history?.pageSize || source.history?.page_size || HISTORY_PAGE_SIZE),
        },
        trading_view: {
            symbol: tradingView.symbol || "BINANCE:BTCUSDT",
            interval: tradingView.interval || "60",
            symbols: tradingView.symbols || DEFAULT_CHART_SYMBOLS,
        },
        analysis_defaults: {
            symbol: String(defaults.symbol || "BTC-USDT").trim().toUpperCase(),
            asset_type: "crypto",
            analysis_date: defaults.analysisDate || defaults.analysis_date || todayIsoDate(),
            output_language: defaults.outputLanguage || defaults.output_language || "vietnamese",
            selected_analysts: normalizeAnalystKeys(defaults.selectedAnalysts || defaults.selected_analysts),
            research_depth: defaults.researchDepth || defaults.research_depth || "auto",
            quick_think_model: defaults.quickThinkModel || defaults.quick_think_model || defaultModel,
            deep_think_model: defaults.deepThinkModel || defaults.deep_think_model || defaultModel,
            quick_reasoning_effort: String(defaults.quickReasoningEffort || defaults.quick_reasoning_effort || "max"),
            deep_reasoning_effort: String(defaults.deepReasoningEffort || defaults.deep_reasoning_effort || "max"),
            checkpoint_enabled: Boolean(defaults.checkpointEnabled ?? defaults.checkpoint_enabled ?? false),
        },
        analysis_options: {
            analysts: normalizeAnalystOptions(options.analysts),
            asset_types: [{ value: "crypto", label: "Crypto" }],
            output_languages: options.outputLanguages || options.output_languages || ["Vietnamese", "English"],
            models: options.models || [
                { value: "MiniMax-M2.5", label: "MiniMax M2.5" },
                { value: "MiniMax-M2.7", label: "MiniMax M2.7" },
            ],
            research_depths: options.researchDepths || options.research_depths || [
                { value: "auto", label: "Auto", rounds: 3, effective_depth: "medium", description: "Backend-managed baseline depth." },
                { value: "quick", label: "Quick", rounds: 1, description: "Fast scan with minimal debate." },
                { value: "medium", label: "Medium", rounds: 3, description: "Balanced research depth for regular analysis." },
                { value: "deep", label: "Deep", rounds: 5, description: "More debate rounds before the final decision." },
            ],
            reasoning_efforts: options.reasoningEfforts || options.reasoning_efforts || [
                { value: "low", label: "low" },
                { value: "medium", label: "medium" },
                { value: "high", label: "high" },
                { value: "xhigh", label: "xhigh" },
                { value: "max", label: "max" },
            ],
        },
    };
}

function mergeBackendConfig(frontendConfig, backendConfig) {
    if (!backendConfig || typeof backendConfig !== "object") {
        return frontendConfig;
    }
    return {
        ...frontendConfig,
        configured: backendConfig.configured ?? frontendConfig.configured,
        provider: backendConfig.provider || frontendConfig.provider,
        default_model: backendConfig.default_model || frontendConfig.default_model,
        auth: {
            ...frontendConfig.auth,
            ...(backendConfig.auth || {}),
        },
        history: {
            ...frontendConfig.history,
            ...(backendConfig.history || {}),
        },
        trading_view: {
            ...frontendConfig.trading_view,
            ...(backendConfig.trading_view || {}),
        },
        chat: {
            ...frontendConfig.chat,
            ...(backendConfig.chat || {}),
        },
        analysis_defaults: {
            ...frontendConfig.analysis_defaults,
        },
    };
}

async function loadBackendPublicConfig() {
    try {
        const response = await fetch(buildApiUrl("/api/config"), { cache: "no-store" });
        if (!response.ok) {
            return null;
        }
        return await response.json();
    } catch {
        return null;
    }
}

function initializeChartFromConfig(config) {
    const tradingView = config?.trading_view || {};
    const configuredSymbols = Array.isArray(tradingView.symbols) ? tradingView.symbols : DEFAULT_CHART_SYMBOLS;
    const storedSymbols = readStoredChartSymbols();
    const symbols = storedSymbols && storedSymbols.length
        ? storedSymbols
        : [
            normalizeTradingViewSymbol(tradingView.symbol || ""),
            ...configuredSymbols.map(normalizeTradingViewSymbol),
        ].filter(Boolean);
    state.chart.symbols = [...new Set(symbols)];
    state.chart.symbol = normalizeTradingViewSymbol(tradingView.symbol || state.chart.symbol) || state.chart.symbols[0];
    if (!state.chart.symbols.includes(state.chart.symbol)) {
        state.chart.symbols.unshift(state.chart.symbol);
    }
    state.chart.interval = normalizeTradingViewInterval(tradingView.interval || state.chart.interval || DEFAULT_CHART_INTERVAL) || "60";
}

function buildApiUrlFromBase(baseUrl, path) {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    return baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath;
}

function buildApiUrl(path) {
    return buildApiUrlFromBase(state.apiBaseUrl, path);
}

async function apiFetch(path, options = {}) {
    const response = await fetch(buildApiUrl(path), options);
    const requestHeaders = new Headers(options.headers || {});
    if (response.status === 401 && requestHeaders.has("Authorization")) {
        clearAuthState();
    }
    return response;
}

function getGoogleClientId() {
    return state.config?.auth?.google_client_id || "";
}

function canReadHistory() {
    return Boolean(state.auth.canReadHistory);
}

function canOpenAdminPage() {
    return Boolean(state.auth.isAdmin);
}

function canOpenChatPage() {
    return Boolean(state.auth.isAdmin);
}

function getAuthHeaders() {
    if (!state.auth.idToken) {
        return {};
    }
    return {
        Authorization: `Bearer ${state.auth.idToken}`,
    };
}

function getAdminAuthHeaders(extraHeaders = {}) {
    const authHeaders = getAuthHeaders();
    if (!authHeaders.Authorization) {
        throw new Error("Admin API calls require an authenticated session header.");
    }
    return {
        ...extraHeaders,
        ...authHeaders,
    };
}

function persistAuthState() {
    if (!state.auth.idToken || !state.auth.profile) {
        safeRemoveSessionStorage(AUTH_STORAGE_KEY);
        safeRemoveLocalStorage(AUTH_STORAGE_KEY);
        return;
    }
    safeWriteLocalStorage(
        AUTH_STORAGE_KEY,
        JSON.stringify({
            idToken: state.auth.idToken,
            profile: state.auth.profile,
        }),
    );
    safeRemoveSessionStorage(AUTH_STORAGE_KEY);
}

async function createBackendSession(googleIdToken) {
    const response = await fetch(buildApiUrl("/api/auth/session"), {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ id_token: googleIdToken }),
        cache: "no-store",
    });
    if (!response.ok) {
        const message = await readResponseError(response);
        throw new Error(message);
    }
    return await response.json();
}

function applyBackendSession(sessionPayload, fallbackProfile = null) {
    const sessionToken = String(sessionPayload?.session_token || "").trim();
    if (!sessionToken) {
        throw new Error("Backend did not return a valid session token.");
    }
    state.auth.idToken = sessionToken;
    state.auth.profile = normalizeAuthProfile({
        ...(fallbackProfile || {}),
        ...decodeJwtPayload(sessionToken),
        ...(sessionPayload?.user || {}),
    });
    applyAuthUser(sessionPayload?.user || state.auth.user || {});
    state.auth.status = state.auth.isAuthorized ? "authorized" : "forbidden";
    state.auth.error = "";
    persistAuthState();
}

function applyAuthUser(user = {}) {
    state.auth.user = user;
    state.auth.isAuthorized = Boolean(user.authorized ?? user.email);
    state.auth.canRunAnalysis = Boolean(user.can_run_analysis || user.is_admin);
    state.auth.isAdmin = Boolean(user.is_admin);
    state.auth.canReadHistory = Boolean(user.can_read_history || user.is_admin);
    state.auth.historyAccessDays = user.history_access_days ?? null;
    state.auth.historyAccessUnlimited = Boolean(user.history_access_unlimited || user.is_admin);
}

function clearAuthState() {
    if (state.chat.controller) {
        state.chat.controller.abort();
        state.chat.controller = null;
    }
    state.chat.isStreaming = false;
    state.auth = {
        idToken: "",
        profile: null,
        user: null,
        status: "signed_out",
        isAuthorized: false,
        canRunAnalysis: false,
        isAdmin: false,
        canReadHistory: false,
        historyAccessDays: null,
        historyAccessUnlimited: false,
        initialized: state.auth.initialized,
        error: "",
    };
    safeRemoveSessionStorage(AUTH_STORAGE_KEY);
    safeRemoveLocalStorage(AUTH_STORAGE_KEY);
    if (window.google?.accounts?.id) {
        window.google.accounts.id.disableAutoSelect();
    }
    if (state.page === "history" || state.page === "admin" || state.page === "chat") {
        state.page = APP_SETTINGS.defaultPage || APP_SETTINGS.default_page || "agent";
    }
    renderAuthState();
    renderHistoryPage();
    renderAdminPage();
    renderChatPage();
}

async function validateAuthSession() {
    if (!state.auth.idToken || isJwtExpired(state.auth.profile || {})) {
        clearAuthState();
        return false;
    }
    state.auth.status = "validating";
    state.auth.error = "";
    renderAuthState();
    try {
        if (!isBackendSessionProfile(state.auth.profile || {})) {
            const sessionPayload = await createBackendSession(state.auth.idToken);
            applyBackendSession(sessionPayload, state.auth.profile);
        }
        const response = await apiFetch("/api/auth/me", {
            headers: getAuthHeaders(),
            cache: "no-store",
        });
        if (!response.ok) {
            if (!state.auth.idToken) {
                return false;
            }
            const message = await readResponseError(response);
            throw new Error(message);
        }
        const user = await response.json();
        applyAuthUser(user);
        state.auth.profile = normalizeAuthProfile({ ...state.auth.profile, ...user });
        state.auth.status = state.auth.isAuthorized ? "authorized" : "forbidden";
        persistAuthState();
        renderAuthState();
        return state.auth.isAuthorized;
    } catch (error) {
        state.auth.user = null;
        state.auth.isAuthorized = false;
        state.auth.status = "forbidden";
        state.auth.error = error instanceof Error ? error.message : String(error || "Google auth failed.");
        renderAuthState();
        return false;
    }
}

async function setGoogleCredential(idToken) {
    const profile = normalizeAuthProfile(decodeJwtPayload(idToken));
    state.auth.idToken = "";
    state.auth.profile = profile;
    state.auth.user = null;
    state.auth.status = "validating";
    state.auth.error = "";
    renderAuthState();
    const sessionPayload = await createBackendSession(idToken);
    applyBackendSession(sessionPayload, profile);
    renderAuthState();
}

async function ensureAuthorizedSession() {
    if (!state.auth.idToken) {
        throw new Error("Sign in with Google before continuing.");
    }
    if (isBackendSessionProfile(state.auth.profile || {})) {
        const authorized = await validateAuthSession();
        if (!authorized) {
            throw new Error(state.auth.error || "Session expired. Sign in with Google again.");
        }
        return true;
    }
    if (state.auth.isAuthorized && !isJwtExpired(state.auth.profile || {})) {
        return true;
    }
    const authorized = await validateAuthSession();
    if (!authorized) {
        throw new Error(state.auth.error || "Sign in with Google before continuing.");
    }
    return true;
}

async function ensureCanRunAnalysis() {
    await ensureAuthorizedSession();
    if (!state.auth.canRunAnalysis) {
        throw new Error("Run analysis permission is required.");
    }
    return true;
}

function renderGoogleSignInFallback(message = "Google sign-in is not ready.") {
    if (!(elements.googleSignInButton instanceof HTMLElement)) {
        return;
    }
    elements.googleSignInButton.classList.add("is-fallback");
    elements.googleSignInButton.innerHTML = `<button class="google-login-fallback" type="button">Sign in with Google</button>`;
    const button = elements.googleSignInButton.querySelector("button");
    if (button instanceof HTMLButtonElement) {
        button.title = message;
        button.addEventListener("click", () => {
            openBackendIssueAlert(message);
        });
    }
}

function initializeGoogleAuth() {
    const clientId = getGoogleClientId();
    state.auth.initialized = true;
    renderAuthState();
    if (!clientId) {
        state.auth.error = "GOOGLE_CLIENT_ID is not configured.";
        renderGoogleSignInFallback("Set GOOGLE_CLIENT_ID in the backend .env, then restart the backend to enable Google sign-in.");
        renderAuthState();
        return;
    }

    let attempts = 0;
    const setup = () => {
        attempts += 1;
        if (!window.google?.accounts?.id) {
            if (attempts < 80) {
                window.setTimeout(setup, 100);
            } else {
                renderGoogleSignInFallback("Google sign-in script did not load. Check the network connection or browser blockers.");
            }
            return;
        }
        window.google.accounts.id.initialize({
            client_id: clientId,
            callback: (response) => {
                setGoogleCredential(response.credential).catch((error) => handleRunFailure(error));
            },
        });
        if (elements.googleSignInButton instanceof HTMLElement) {
            elements.googleSignInButton.classList.remove("is-fallback");
            elements.googleSignInButton.title = "Sign in with Google";
            elements.googleSignInButton.innerHTML = "";
            window.google.accounts.id.renderButton(elements.googleSignInButton, {
                type: "icon",
                theme: "filled_black",
                size: "large",
                shape: "circle",
            });
        }
        renderAuthState();
    };
    setup();

    if (state.auth.idToken) {
        validateAuthSession();
    }
}

function getStopDelayRemainingMs() {
    if (!state.isBusy || !state.stopAvailableAt) {
        return 0;
    }
    return Math.max(0, state.stopAvailableAt - Date.now());
}

function clearStopAvailabilityTimer() {
    if (state.stopAvailabilityTimer) {
        window.clearTimeout(state.stopAvailabilityTimer);
        state.stopAvailabilityTimer = null;
    }
}

function scheduleStopAvailabilityRefresh() {
    clearStopAvailabilityTimer();
    const remainingMs = getStopDelayRemainingMs();
    if (!state.isBusy || remainingMs <= 0) {
        return;
    }
    state.stopAvailabilityTimer = window.setTimeout(() => {
        state.stopAvailabilityTimer = null;
        updateActionAvailability();
    }, Math.min(remainingMs, 1000));
}

function updateActionAvailability() {
    const canRun = Boolean(state.config && state.auth.canRunAnalysis);
    const stopRemainingMs = getStopDelayRemainingMs();
    const canStop = state.isBusy && stopRemainingMs <= 0;
    const stopRemainingSeconds = Math.ceil(stopRemainingMs / 1000);
    const runButtonLabel = state.isBusy
        ? canStop
            ? "Stop analysis"
            : `Stop available in ${stopRemainingSeconds}s`
        : canRun
        ? "Run analysis"
        : "Run analysis permission is required.";

    elements.runAnalysisButton.disabled = state.isBusy ? !canStop : !canRun;
    elements.runAnalysisButton.dataset.state = state.isBusy ? "running" : "idle";
    elements.runAnalysisButton.classList.toggle("is-running", state.isBusy);
    elements.runAnalysisButton.setAttribute("aria-label", runButtonLabel);
    elements.runFromModalButton.disabled = state.isBusy || !canRun;
    elements.stopAnalysisButton.disabled = !canStop;
    elements.saveConfigButton.disabled = state.isBusy;
    elements.openConfigButton.disabled = state.isBusy;
    elements.runAnalysisButton.title = runButtonLabel;
    elements.runFromModalButton.title = canRun ? "Apply and run" : "Run analysis permission is required.";
    scheduleStopAvailabilityRefresh();
}

function renderAuthState() {
    const email = state.auth.user?.email || state.auth.profile?.email || "";
    const profile = { ...(state.auth.profile || {}), ...(state.auth.user || {}) };
    const picture = profile.picture || "";
    const name = profile.name || "";
    const profileLabel = email || name || "Google account";
    const profileInitial = (email || name || "G").trim().charAt(0).toUpperCase() || "G";
    const showProfile = Boolean(state.auth.idToken);
    let label = "";
    let status = "idle";
    if (state.auth.status === "validating") {
        label = "Checking Google";
        status = "running";
    } else if (state.auth.isAuthorized && email) {
        const accessLabel = state.auth.isAdmin ? "admin" : state.auth.canRunAnalysis ? "can run" : "history";
        label = `${email} - ${accessLabel}`;
        status = "completed";
    } else if (state.auth.status === "forbidden") {
        label = email ? `${email} not allowed` : "Google auth failed";
        status = "attention";
    } else if (!getGoogleClientId()) {
        label = `Set Google Client ID`;
        status = "attention";
    }

    if (elements.authStatusText instanceof HTMLElement) {
        elements.authStatusText.textContent = label;
        elements.authStatusText.title = state.auth.error || "Authorized Google account required.";
        elements.authStatusText.dataset.state = status;
    }
    if (elements.authProfile instanceof HTMLElement) {
        elements.authProfile.classList.toggle("hidden", !showProfile);
        elements.authProfile.dataset.state = status;
        elements.authProfile.title = state.auth.error || profileLabel;
        elements.authProfile.setAttribute("aria-label", showProfile ? `Signed in as ${profileLabel}` : "Signed-in Google profile");
    }
    if (elements.authProfileEmail instanceof HTMLElement) {
        elements.authProfileEmail.textContent = profileLabel;
    }
    if (elements.authProfileInitial instanceof HTMLElement) {
        elements.authProfileInitial.textContent = profileInitial;
        elements.authProfileInitial.classList.toggle("hidden", Boolean(picture));
    }
    if (elements.authProfileAvatar instanceof HTMLImageElement) {
        elements.authProfileAvatar.classList.toggle("hidden", !picture);
        if (picture) {
            elements.authProfileAvatar.src = picture;
        } else {
            elements.authProfileAvatar.removeAttribute("src");
        }
    }
    elements.signOutButton.classList.toggle("hidden", !showProfile);
    elements.googleSignInButton.classList.toggle("hidden", showProfile);
    if (elements.adminPageButton instanceof HTMLElement) {
        elements.adminPageButton.classList.toggle("hidden", !state.auth.isAdmin);
    }
    if (elements.chatPageButton instanceof HTMLElement) {
        elements.chatPageButton.classList.toggle("hidden", !state.auth.isAdmin);
    }
    if ((state.page === "admin" || state.page === "chat") && !state.auth.isAdmin) {
        state.page = APP_SETTINGS.defaultPage || APP_SETTINGS.default_page || "agent";
    }
    updateActionAvailability();
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
    const depth = getSelectedDepth();
    const payload = {
        symbol: normalizeCryptoSymbol(elements.symbolInput.value),
        asset_type: "crypto",
        analysis_date: todayIsoDate(),
        output_language: getOutputLanguage(),
        selected_analysts: getCheckedAnalysts(),
        quick_think_model: String(elements.quickModelSelect?.value || "").trim(),
        deep_think_model: String(elements.deepModelSelect?.value || "").trim(),
        quick_reasoning_effort: getQuickReasoningEffort(),
        deep_reasoning_effort: getDeepReasoningEffort(),
        checkpoint_enabled: false,
    };
    if (depth !== "auto") {
        payload.research_depth = depth;
    }
    return payload;
}

function createRunId() {
    return `run-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

