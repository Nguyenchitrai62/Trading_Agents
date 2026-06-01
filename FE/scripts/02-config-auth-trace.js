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
            lookback_days: Number(defaults.lookbackDays || defaults.lookback_days || 7),
            output_language: defaults.outputLanguage || defaults.output_language || "Vietnamese",
            selected_analysts: normalizeAnalystKeys(defaults.selectedAnalysts || defaults.selected_analysts),
            research_depth: defaults.researchDepth || defaults.research_depth || "auto",
            model: defaultModel,
            checkpoint_enabled: Boolean(defaults.checkpointEnabled ?? defaults.checkpoint_enabled ?? false),
        },
        analysis_options: {
            analysts: normalizeAnalystOptions(options.analysts),
            asset_types: [{ value: "crypto", label: "Crypto" }],
            lookback_presets: options.lookbackPresets || options.lookback_presets || [
                { value: "7", label: "7 days", days: 7 },
                { value: "14", label: "14 days", days: 14 },
                { value: "30", label: "30 days", days: 30 },
                { value: "90", label: "90 days", days: 90 },
            ],
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

function getSelectedLookbackDays() {
    const selectedPreset = elements.lookbackPresetSelect.value;
    if (selectedPreset && selectedPreset !== CUSTOM_LOOKBACK_VALUE) {
        return Math.max(1, Number(selectedPreset || 1));
    }
    return Math.max(1, Number(elements.lookbackDaysInput.value || 7));
}

function collectConfigDraft() {
    return {
        symbol: normalizeCryptoSymbol(elements.symbolInput.value),
        asset_type: "crypto",
            analysis_date: todayIsoDate(),
        lookback_days: getSelectedLookbackDays(),
        output_language: getOutputLanguage(),
        selected_analysts: getCheckedAnalysts(),
        research_depth: getSelectedDepth(),
        model: String(elements.modelSelect?.value || "").trim(),
        checkpoint_enabled: false,
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
    return apiFetch(`/api/analyze/${encodeURIComponent(runId)}/cancel`, {
        method: "POST",
        headers: getAuthHeaders(),
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
            analysis_date: todayIsoDate(),
            lookback_days: state.config.analysis_defaults.lookback_days,
            output_language: state.config.analysis_defaults.output_language,
            selected_analysts: state.config.analysis_defaults.selected_analysts,
            research_depth: state.config.analysis_defaults.research_depth,
            model: state.config.analysis_defaults.model,
            checkpoint_enabled: false,
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

function tryParseJsonString(value = "") {
    const text = String(value || "").trim();
    if (!text || !/^[\[{\"]/.test(text)) {
        return null;
    }
    try {
        return JSON.parse(text);
    } catch {
        const decoded = text
            .replace(/\\r/g, "\r")
            .replace(/\\n/g, "\n")
            .replace(/\\t/g, "\t")
            .replace(/\\\"/g, '"')
            .replace(/\\\//g, "/");
        if (decoded === text || !/^[\[{\"]/.test(decoded.trim())) {
            return null;
        }
        try {
            return JSON.parse(decoded);
        } catch {
            return null;
        }
    }
}

function extractEmbeddedJsonValues(value = "", limit = 8) {
    const source = String(value || "").trim();
    if (!source) {
        return [];
    }

    const fragments = [];
    for (let start = 0; start < source.length && fragments.length < limit; start += 1) {
        const opener = source[start];
        if (opener !== "{" && opener !== "[") {
            continue;
        }

        let depth = 0;
        let inString = false;
        let isEscaping = false;

        for (let end = start; end < source.length; end += 1) {
            const char = source[end];
            if (inString) {
                if (isEscaping) {
                    isEscaping = false;
                    continue;
                }
                if (char === "\\") {
                    isEscaping = true;
                    continue;
                }
                if (char === '"') {
                    inString = false;
                }
                continue;
            }

            if (char === '"') {
                inString = true;
                continue;
            }

            if (char === "{" || char === "[") {
                depth += 1;
                continue;
            }

            if (char === "}" || char === "]") {
                depth -= 1;
                if (depth === 0) {
                    const parsed = tryParseJsonString(source.slice(start, end + 1));
                    if (parsed != null) {
                        fragments.push(parsed);
                    }
                    start = end;
                    break;
                }
                if (depth < 0) {
                    break;
                }
            }
        }
    }

    return fragments;
}

function normalizeToolResultItems(items) {
    if (!Array.isArray(items)) {
        return [];
    }

    return items
        .map((item) => {
            let title = "";
            let link = "";
            let snippet = "";
            let date = "";
            if (item && typeof item === "object") {
                title = String(item.title || item.name || item.query || item.link || item.url || "Untitled").trim();
                link = String(item.link || item.url || "").trim();
                snippet = String(item.snippet || item.description || item.summary || "").trim();
                date = String(item.date || item.published || item.published_at || "").trim();
            } else {
                title = String(item || "").trim();
            }

            if (!title && !link && !snippet) {
                return null;
            }

            let source = "";
            if (link) {
                try {
                    source = new URL(link).hostname.replace(/^www\./i, "");
                } catch {
                    source = "";
                }
            }

            return {
                title: title || link || "Untitled",
                link,
                snippet,
                date,
                source,
            };
        })
        .filter(Boolean);
}

function buildStructuredToolResultData(payload) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        return null;
    }

    const answer = String(payload.answer || payload.summary || "").trim();
    const sections = [];

    const organic = normalizeToolResultItems(payload.organic || payload.results);
    if (organic.length) {
        sections.push({ key: "organic", title: "Search results", items: organic });
    }

    const news = normalizeToolResultItems(payload.news || payload.top_stories);
    if (news.length) {
        sections.push({ key: "news", title: "Related news", items: news });
    }

    const relatedSearches = Array.isArray(payload.related_searches)
        ? payload.related_searches
              .map((item) => (item && typeof item === "object" ? String(item.query || "").trim() : String(item || "").trim()))
              .filter(Boolean)
        : [];

    if (!answer && !sections.length && !relatedSearches.length) {
        return null;
    }

    return {
        answer,
        sections,
        relatedSearches,
    };
}

function getStructuredToolResultData(content) {
    return buildStructuredToolResultData(unwrapToolResultPayload(content));
}

function renderStructuredToolResultToMarkdown(toolResult) {
    if (!toolResult) {
        return "";
    }

    const lines = [];
    if (toolResult.answer) {
        lines.push(toolResult.answer);
    }

    toolResult.sections.forEach((section) => {
        if (lines.length) {
            lines.push("");
        }
        lines.push(`${section.title}:`);
        lines.push(...formatToolResultItems(section.items));
    });

    if (toolResult.relatedSearches.length) {
        if (lines.length) {
            lines.push("");
        }
        lines.push(`Related searches: ${toolResult.relatedSearches.join("; ")}`);
    }

    return lines.join("\n").trim();
}

function unwrapToolResultPayload(value) {
    if (typeof value === "string") {
        const trimmed = value.trim();
        const parsed = tryParseJsonString(trimmed);
        if (parsed != null) {
            return unwrapToolResultPayload(parsed);
        }

        const embeddedPayload = extractEmbeddedJsonValues(trimmed)
            .map((item) => unwrapToolResultPayload(item))
            .find((item) => buildStructuredToolResultData(item));
        return embeddedPayload == null ? trimmed : embeddedPayload;
    }
    if (Array.isArray(value)) {
        if (value.length === 1) {
            return unwrapToolResultPayload(value[0]);
        }
        return value.map((item) => unwrapToolResultPayload(item));
    }
    if (value && typeof value === "object") {
        const blockType = String(value.type || "").trim().toLowerCase();
        if (blockType === "text" && typeof value.text === "string") {
            return unwrapToolResultPayload(value.text);
        }
        const keys = Object.keys(value);
        if (keys.length === 1 && keys[0] === "content") {
            return unwrapToolResultPayload(value.content);
        }
    }
    return value;
}

function formatToolResultItems(items) {
    const lines = [];
    normalizeToolResultItems(items).forEach((item) => {
        if (!item.title) {
            return;
        }
        lines.push(item.link ? `- [${item.title}](${item.link})` : `- ${item.title}`);
        if (item.date) {
            lines.push(`  Date: ${item.date}`);
        }
        if (item.snippet) {
            lines.push(`  ${item.snippet}`);
        }
    });
    return lines;
}

function formatToolResultMarkdown(content) {
    const toolResult = getStructuredToolResultData(content);
    if (toolResult) {
        return renderStructuredToolResultToMarkdown(toolResult);
    }

    const payload = unwrapToolResultPayload(content);
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
        try {
            return `\`\`\`json\n${JSON.stringify(payload, null, 2)}\n\`\`\``;
        } catch {
            return String(content || "").trim();
        }
    }

    if (Array.isArray(payload)) {
        try {
            return `\`\`\`json\n${JSON.stringify(payload, null, 2)}\n\`\`\``;
        } catch {
            return String(content || "").trim();
        }
    }

    const text = String(payload || "").trim();
    const parsedText = tryParseJsonString(text);
    if (parsedText != null) {
        return formatToolResultMarkdown(parsedText);
    }
    return text;
}

function formatRawToolResultMarkdown(content = "") {
    const text = String(content || "").trim();
    if (!text) {
        return "";
    }
    const hasLink = /https?:\/\//.test(text);
    const looksMarkdown = /^#{1,6}\s|^\s*[-*]\s|\[[^\]]+\]\([^)]+\)/m.test(text);
    if (hasLink || looksMarkdown) {
        return text;
    }
    return `\`\`\`text\n${text}\n\`\`\``;
}

function formatToolResultPlainText(content, maxLength = 320) {
    return compactText(stripMarkdownToPlainText(formatToolResultMarkdown(content)), maxLength);
}

function formatTraceContentForDisplay(phase = "analysis", content = "") {
    const raw = typeof content === "string" ? content : formatStructuredValue(content);
    if (phase === "tool_result") {
        return formatToolResultMarkdown(raw);
    }
    return String(raw || "").trim();
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

function isToolTracePhase(phase = "") {
    return phase === "tool_call" || phase === "tool_result" || phase === "tool_trace";
}

function normalizeTraceId(traceId = "") {
    return String(traceId || "").trim();
}

function buildToolTraceMatchKey(agent = "", title = "", traceId = "") {
    const normalizedTraceId = normalizeTraceId(traceId).toLowerCase();
    if (normalizedTraceId) {
        return `trace::${normalizedTraceId}`;
    }
    const normalizedAgent = String(agent || "").trim().toLowerCase();
    const normalizedTitle = String(title || "").trim().toLowerCase();
    return normalizedAgent || normalizedTitle ? `${normalizedAgent}::${normalizedTitle}` : "";
}

function buildToolTracePreviewText(toolCallContent = "", toolResultContent = "") {
    const callSummary = compactText(stripMarkdownToPlainText(toolCallContent || ""), 140);
    const resultSummary = compactText(stripMarkdownToPlainText(toolResultContent || ""), 220);
    if (callSummary && resultSummary) {
        return `Call: ${callSummary}\nResult: ${resultSummary}`;
    }
    return resultSummary || callSummary;
}

function buildToolTraceCombinedContent(toolCallContent = "", toolResultContent = "") {
    const callText = String(toolCallContent || "").trim();
    const resultText = String(toolResultContent || "").trim();
    if (callText && resultText) {
        return `Tool call\n${callText}\n\nTool result\n${resultText}`;
    }
    return resultText || callText;
}

function findPendingToolTraceEntry(traceOrAgent = "", title = "", traceId = "") {
    const trace = traceOrAgent && typeof traceOrAgent === "object"
        ? traceOrAgent
        : { agent: traceOrAgent, title, traceId };
    const matchKey = buildToolTraceMatchKey(trace.agent, trace.title, trace.traceId);
    if (!matchKey) {
        return null;
    }
    for (let index = state.run.traceFeed.length - 1; index >= 0; index -= 1) {
        const entry = state.run.traceFeed[index];
        if (!entry || !isToolTracePhase(entry.phase)) {
            continue;
        }
        if (buildToolTraceMatchKey(entry.agent, entry.title, entry.traceId) !== matchKey) {
            continue;
        }
        if (entry.toolResultContent) {
            continue;
        }
        return entry;
    }
    return null;
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

const logAutoScrollPreferences = new WeakMap();

function syncLogAutoScrollPreference(element) {
    if (!(element instanceof HTMLElement)) {
        return;
    }
    logAutoScrollPreferences.set(element, isScrolledNearBottom(element, LOG_AUTO_SCROLL_THRESHOLD));
}

function shouldAutoScrollLog(element) {
    if (!(element instanceof HTMLElement)) {
        return true;
    }
    const cachedPreference = logAutoScrollPreferences.get(element);
    if (typeof cachedPreference === "boolean") {
        return cachedPreference;
    }
    return isScrolledNearBottom(element, LOG_AUTO_SCROLL_THRESHOLD);
}

function getLogScrollSnapshot(element, desiredKeys = null) {
    if (!(element instanceof HTMLElement)) {
        return null;
    }
    const items = Array.from(element.querySelectorAll(".event-log-item[data-log-key]"));
    if (!items.length) {
        return null;
    }

    const scrollTop = element.scrollTop;
    const viewportBottom = scrollTop + element.clientHeight;
    let anchorKey = "";
    let anchorOffset = 0;
    let removedAboveViewportHeight = 0;

    for (const item of items) {
        const top = item.offsetTop;
        const bottom = top + item.offsetHeight;
        const key = String(item.dataset.logKey || "");
        if (!anchorKey && bottom > scrollTop) {
            anchorKey = key;
            anchorOffset = Math.max(0, scrollTop - top);
        }
        if (bottom <= scrollTop) {
            if (!(desiredKeys instanceof Set) || !desiredKeys.has(key)) {
            removedAboveViewportHeight += item.offsetHeight;
            }
            continue;
        }
        if (top >= viewportBottom) {
            break;
        }
    }

    return {
        anchorKey,
        anchorOffset,
        removedAboveViewportHeight,
        scrollTop,
    };
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
    if (phase === "tool_result" || phase === "analysis" || phase === "tool_trace") {
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
    const title = trace.title || agent;
    const traceId = normalizeTraceId(trace.trace_id || trace.traceId || "");
    const content = formatTraceContentForDisplay(phase, trace.content || "");
    const sourceGroup = trace.source_group || trace.sourceGroup || "";
    const sourceKind = trace.source_kind || trace.sourceKind || "";
    const sourceLabel = trace.source_label || trace.sourceLabel || "";
    const toolResultData = phase === "tool_result" ? getStructuredToolResultData(trace.content || "") : null;
    const fingerprint = buildContentFingerprint(agent, phase, traceId || title, content);
    if (!content || (fingerprint && state.run.seenTraceFingerprints.has(fingerprint))) {
        return;
    }
    if (fingerprint) {
        state.run.seenTraceFingerprints.add(fingerprint);
    }

    const wasAtLatest = isScrolledNearBottom(elements.toolTraceList);
    if (phase === "tool_result") {
        const existingEntry = findPendingToolTraceEntry({ agent, title, traceId });
        if (existingEntry) {
            existingEntry.phase = "tool_trace";
            existingEntry.tone = getFeedToneForPhase("tool_trace");
            existingEntry.timestamp = new Date().toLocaleTimeString();
            existingEntry.traceId = existingEntry.traceId || traceId;
            existingEntry.sourceGroup = existingEntry.sourceGroup || sourceGroup;
            existingEntry.sourceKind = existingEntry.sourceKind || sourceKind;
            existingEntry.sourceLabel = existingEntry.sourceLabel || sourceLabel;
            existingEntry.toolCallContent = existingEntry.toolCallContent || existingEntry.content || "";
            existingEntry.toolResultContent = content;
            existingEntry.content = buildToolTraceCombinedContent(existingEntry.toolCallContent, existingEntry.toolResultContent);
            existingEntry.previewContent = buildToolTracePreviewText(existingEntry.toolCallContent, existingEntry.toolResultContent);
            existingEntry.toolResultData = toolResultData;
            state.run.latestTraceId = existingEntry.id;
            state.run.flashLatestTrace = wasAtLatest;
            pushStreamFeed({
                title: `${agent} - ${existingEntry.title}`,
                content: compactText(stripMarkdownToPlainText(existingEntry.previewContent || existingEntry.content), 260),
                tone: existingEntry.tone,
            });
            return;
        }
    }

    const entry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp: new Date().toLocaleTimeString(),
        agent,
        phase,
        tone: getFeedToneForPhase(phase),
        title,
        traceId,
        sourceGroup,
        sourceKind,
        sourceLabel,
        content,
        previewContent: content,
        toolCallContent: phase === "tool_call" ? content : "",
        toolResultContent: phase === "tool_result" ? content : "",
        toolResultData,
    };

    state.run.agentTrace[agent] = [...(state.run.agentTrace[agent] || []), entry].slice(-TRACE_AGENT_LIMIT);
    state.run.traceFeed = [...state.run.traceFeed, entry].slice(-TRACE_FEED_LIMIT);
    state.run.latestTraceId = entry.id;
    state.run.flashLatestTrace = wasAtLatest;
    pushStreamFeed({
        title: `${agent} - ${entry.title}`,
        content: compactText(stripMarkdownToPlainText(entry.content), 260),
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
    const fallbackAnalysts = normalizeAnalystKeys(getConfigSnapshot()?.selected_analysts
        || state.config?.analysis_defaults?.selected_analysts
        || []);
    return {
        analysts: fallbackAnalysts.map((key) => ({
            key,
            label: REPORT_BY_ANALYST[key]?.title?.replace(" Analysis", " Analyst") || key,
            status: "pending",
        })),
        research: [
            { key: "bull", label: "Bull Researcher", status: "pending" },
            { key: "bear", label: "Bear Researcher", status: "pending" },
        ],
        risk: [
            { key: "aggressive", label: "Aggressive Analyst", status: "pending" },
            { key: "conservative", label: "Conservative Analyst", status: "pending" },
            { key: "neutral", label: "Neutral Analyst", status: "pending" },
        ],
        portfolio: [
            { key: "portfolio_manager", label: "Portfolio Manager", status: "pending" },
            { key: "verifier", label: "Verifier", status: "pending" },
            { key: "decision_extractor", label: "Decision Extractor", status: "pending" },
        ],
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
        },
        risk: {
            aggressive: { key: "aggressiveRisk" },
            conservative: { key: "conservativeRisk" },
            neutral: { key: "neutralRisk" },
        },
        portfolio: {
            portfolio_manager: { key: "portfolioDecision" },
            portfolio: { key: "portfolioDecision" },
            verifier: { key: "verifierReport" },
            decision_extractor: { key: "decisionExtractor" },
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

function buildFinalDecisionMarkdown() {
    const decision = state.run.sections.final_trade_decision || "";
    const verification = state.run.sections.verification_report || "";

    if (decision && verification) {
        return `${decision}\n\n---\n\n## Verification\n\n${verification}`;
    }

    return decision || verification || "";
}

function getVerificationVerdictText() {
    return String(state.run.complete?.verification_verdict || "").trim();
}

function getCurrentLivePanel() {
    if (state.run.complete?.signal && state.run.sections.final_trade_decision) {
        const verificationVerdict = getVerificationVerdictText();
        return {
            title: "Final Decision",
            subtitle: verificationVerdict ? `${state.run.complete.signal} - ${verificationVerdict}` : state.run.complete.signal,
            content: buildFinalDecisionMarkdown(),
            fallback: "The Portfolio Manager has not finalized a decision yet.",
            detail: { key: "portfolioDecision" },
            tone: verificationVerdict === "Revise" ? "warning" : verificationVerdict === "Caution" ? "progress" : "completed",
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
            title: "Live flow",
            subtitle: "No active agent",
            content: "",
            fallback: "Run analysis to start the live flow diagram.",
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

    if (currentAgent === "Verifier") {
        return {
            title: currentAgent,
            subtitle: "Running post-decision verification",
            content: state.run.sections.verification_report || currentAgentNarrative || "",
            fallback: "The Verifier is checking deterministic rules and evidence support.",
            detail: { key: "verifierReport" },
            tone: "progress",
            badge: "Verify",
        };
    }

    if (currentAgent === "Decision Extractor") {
        return {
            title: currentAgent,
            subtitle: "Extracting verified order fields",
            content: state.run.sections.final_trade_decision || currentAgentNarrative || "",
            fallback: "The Decision Extractor is converting the verified markdown into structured fields.",
            detail: { key: "decisionExtractor" },
            tone: "progress",
            badge: "Extract",
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
    if (state.activeDetail?.key === "backendLog") {
        renderActiveDetail();
    }
}

function setBusy(isBusy) {
    state.isBusy = isBusy;
    if (!isBusy) {
        clearStopAvailabilityTimer();
        state.analysisStartedAt = 0;
        state.stopAvailableAt = 0;
    }
    document.body.classList.toggle("is-running", isBusy);
    updateActionAvailability();
}

function setElementLoadingState(element, isLoading, label = "Loading") {
    if (!(element instanceof HTMLElement)) {
        return;
    }
    element.classList.toggle("loading-surface", isLoading);
    element.setAttribute("aria-busy", isLoading ? "true" : "false");
    if (isLoading) {
        element.dataset.loadingLabel = label;
    } else {
        delete element.dataset.loadingLabel;
    }
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

async function readResponseError(response) {
    const text = await response.text();
    if (!text) {
        return `Backend returned HTTP ${response.status}.`;
    }
    try {
        const payload = JSON.parse(text);
        if (typeof payload.detail === "string") {
            return payload.detail;
        }
        if (Array.isArray(payload.detail)) {
            return payload.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
        }
        return payload.error || JSON.stringify(payload);
    } catch {
        return text;
    }
}

function openBackendIssueAlert(message) {
    elements.alertTitle.textContent = "Backend Connection Issue";
    elements.alertMessage.textContent = message;
    showModal(elements.alertModal);
}

function openAuthRequiredAlert(message = "Sign in with Google to view History.") {
    elements.alertTitle.textContent = "Sign In Required";
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

