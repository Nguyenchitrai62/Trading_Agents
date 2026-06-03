function getChartSymbolLabel(symbol = "") {
    const normalized = normalizeTradingViewSymbol(symbol);
    const [, ticker = normalized] = normalized.split(":");
    return ticker.replace(/USDT$/, "");
}

function persistChartSymbols() {
    safeWriteLocalStorage(CHART_SYMBOLS_STORAGE_KEY, JSON.stringify(state.chart.symbols));
}

function getTradingViewWidgetSettings() {
    return {
        autosize: true,
        symbol: state.chart.symbol || "BINANCE:BTCUSDT",
        interval: state.chart.interval || DEFAULT_CHART_INTERVAL || "60",
        timezone: "Etc/UTC",
        theme: "dark",
        style: "1",
        locale: "en",
        allow_symbol_change: true,
        hide_side_toolbar: false,
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        withdateranges: true,
        details: false,
        calendar: false,
        hotlist: false,
        watchlist: state.chart.symbols,
        editablewatchlist: false,
        studies: [],
        frameElementId: "tradingViewFrame",
    };
}

function getTradingViewWidgetUrl() {
    const url = new URL(`${TRADING_VIEW_WIDGET_ORIGIN}/embed-widget/advanced-chart/`);
    url.searchParams.set("locale", "en");
    url.hash = encodeURIComponent(JSON.stringify(getTradingViewWidgetSettings()));
    return url.toString();
}

function getTradingViewIframe() {
    if (!(elements.tradingViewFrame instanceof HTMLElement)) {
        return null;
    }
    const iframe = elements.tradingViewFrame.querySelector("iframe");
    return iframe instanceof HTMLIFrameElement ? iframe : null;
}

function postTradingViewMessage(name, data = {}) {
    const iframe = getTradingViewIframe();
    if (!iframe?.contentWindow) {
        return false;
    }
    iframe.contentWindow.postMessage({ name, data }, TRADING_VIEW_WIDGET_ORIGIN);
    return true;
}

function markTradingViewWidgetReady() {
    const wasReady = state.chart.widgetReady;
    state.chart.widgetReady = true;
    state.chart.loading = false;
    const queuedSymbol = state.chart.pendingSymbol;
    state.chart.pendingSymbol = "";
    if (wasReady && !queuedSymbol) {
        return;
    }
    renderChartControls();
    if (queuedSymbol) {
        setTradingViewWidgetSymbol(queuedSymbol);
    }
}

function handleTradingViewWidgetMessage(event) {
    if (event.origin !== TRADING_VIEW_WIDGET_ORIGIN || !event.data || typeof event.data !== "object") {
        return;
    }
    const messageName = event.data.name;
    if (messageName === "tv-widget-load" || messageName === "tv-widget-ready") {
        markTradingViewWidgetReady();
    }
}

function createTradingViewWidget() {
    if (!(elements.tradingViewFrame instanceof HTMLElement)) {
        return;
    }
    elements.tradingViewFrame.innerHTML = "";
    state.chart.widgetReady = false;
    state.chart.loading = true;
    elements.chartStatusText.textContent = "Loading chart";

    const iframe = document.createElement("iframe");
    iframe.title = "TradingView advanced chart";
    iframe.loading = "eager";
    iframe.allowFullscreen = true;
    iframe.src = getTradingViewWidgetUrl();
    iframe.addEventListener("load", () => {
        window.setTimeout(markTradingViewWidgetReady, 350);
    }, { once: true });
    iframe.addEventListener("error", () => {
        state.chart.loading = false;
        elements.chartStatusText.textContent = "Chart load issue";
        appendLog("chart-error", "TradingView chart failed to load.", { source: "frontend" });
    }, { once: true });
    elements.tradingViewFrame.appendChild(iframe);
}

function ensureTradingViewWidget() {
    if (state.chart.loading || state.chart.widgetReady) {
        return;
    }
    state.chart.loading = true;
    renderChartControls();
    createTradingViewWidget();
}

function setTradingViewWidgetSymbol(symbol) {
    const normalized = normalizeTradingViewSymbol(symbol);
    if (!normalized) {
        return;
    }
    if (!state.chart.loaded || !state.chart.widgetReady) {
        state.chart.pendingSymbol = normalized;
        ensureTradingViewWidget();
        return;
    }
    postTradingViewMessage("set-symbol", { symbol: normalized });
    state.chart.symbol = normalized;
    renderChartControls();
}

function renderChartControls() {
    if (!(elements.chartSymbolList instanceof HTMLElement)) {
        return;
    }
    setElementLoadingState(elements.tradingViewFrame, state.chart.loading, "Loading chart");
    elements.chartSymbolList.innerHTML = state.chart.symbols
        .map(
            (symbol) => `
                <div class="chart-symbol-item ${symbol === state.chart.symbol ? "is-active" : ""} ${symbol === state.chart.draggingSymbol ? "is-dragging" : ""}"
                    data-chart-symbol-item="${escapeHtml(symbol)}">
                    <span class="chart-drag-handle" aria-hidden="true">::</span>
                    <button type="button" class="chart-chip" data-chart-symbol="${escapeHtml(symbol)}">
                        ${escapeHtml(getChartSymbolLabel(symbol))}
                    </button>
                    <button type="button" class="chart-mini-action" data-chart-symbol-remove="${escapeHtml(symbol)}" aria-label="Remove ${escapeHtml(symbol)}">X</button>
                </div>
            `,
        )
        .join("");
    elements.addChartSymbolButton.textContent = "Add";
    elements.chartStatusText.textContent = getChartSymbolLabel(state.chart.symbol);
}

function refreshTradingViewChart() {
    renderChartControls();
    if (!state.chart.loaded) {
        return;
    }
    setTradingViewWidgetSymbol(state.chart.symbol);
}

function loadTradingViewChart() {
    renderChartControls();
    if (state.chart.loaded || !(elements.tradingViewFrame instanceof HTMLElement)) {
        return;
    }
    state.chart.loaded = true;
    ensureTradingViewWidget();
    renderChartControls();
}

function setChartSymbol(symbol) {
    const normalized = normalizeTradingViewSymbol(symbol);
    if (!normalized) {
        return;
    }
    if (!state.chart.symbols.includes(normalized)) {
        state.chart.symbols = [...state.chart.symbols, normalized];
        persistChartSymbols();
    }
    state.chart.symbol = normalized;
    refreshTradingViewChart();
}

function addChartSymbolFromInput() {
    const value = elements.chartSymbolInput?.value || "";
    const normalized = normalizeTradingViewSymbol(value);
    if (!normalized) {
        return;
    }
    setChartSymbol(normalized);
    elements.chartSymbolInput.value = "";
}

function removeChartSymbol(symbol) {
    const normalized = normalizeTradingViewSymbol(symbol);
    if (state.chart.symbols.length <= 1) {
        return;
    }
    state.chart.symbols = state.chart.symbols.filter((item) => item !== normalized);
    if (state.chart.symbol === normalized) {
        state.chart.symbol = state.chart.symbols[0];
    }
    persistChartSymbols();
    refreshTradingViewChart();
}

function animateChartSymbolLayout(renderCallback = renderChartControls) {
    if (!(elements.chartSymbolList instanceof HTMLElement)) {
        renderCallback();
        return;
    }
    const beforeRects = new Map(
        Array.from(elements.chartSymbolList.querySelectorAll("[data-chart-symbol-item]")).map((item) => [
            item instanceof HTMLElement ? item.dataset.chartSymbolItem || "" : "",
            item instanceof HTMLElement ? item.getBoundingClientRect() : null,
        ]),
    );
    renderCallback();
    window.requestAnimationFrame(() => {
        elements.chartSymbolList.querySelectorAll("[data-chart-symbol-item]").forEach((item) => {
            if (!(item instanceof HTMLElement)) {
                return;
            }
            const before = beforeRects.get(item.dataset.chartSymbolItem || "");
            if (!before) {
                return;
            }
            const after = item.getBoundingClientRect();
            const deltaY = before.top - after.top;
            if (Math.abs(deltaY) < 1) {
                return;
            }
            item.style.transition = "none";
            item.style.transform = `translateY(${deltaY}px)`;
            item.getBoundingClientRect();
            window.requestAnimationFrame(() => {
                item.style.transition = "";
                item.style.transform = "";
            });
        });
    });
}

function getChartDragInsertionIndex(clientY) {
    if (!(elements.chartSymbolList instanceof HTMLElement) || !state.chart.draggingSymbol) {
        return -1;
    }
    const rows = Array.from(elements.chartSymbolList.querySelectorAll("[data-chart-symbol-item]"))
        .filter((item) => item instanceof HTMLElement && item.dataset.chartSymbolItem !== state.chart.draggingSymbol);
    const symbolsWithoutDragged = state.chart.symbols.filter((symbol) => symbol !== state.chart.draggingSymbol);
    let insertionIndex = symbolsWithoutDragged.length;
    for (const row of rows) {
        const symbol = row.dataset.chartSymbolItem || "";
        const rect = row.getBoundingClientRect();
        if (clientY < rect.top + rect.height / 2) {
            insertionIndex = symbolsWithoutDragged.indexOf(symbol);
            break;
        }
    }
    return Math.max(0, Math.min(insertionIndex, symbolsWithoutDragged.length));
}

function moveChartSymbolToIndex(sourceSymbol, insertionIndex, persistOrder = false) {
    const source = normalizeTradingViewSymbol(sourceSymbol);
    if (!source || insertionIndex < 0) {
        return;
    }
    const current = state.chart.symbols;
    if (!current.includes(source)) {
        return;
    }
    const nextSymbols = current.filter((symbol) => symbol !== source);
    const safeIndex = Math.max(0, Math.min(insertionIndex, nextSymbols.length));
    nextSymbols.splice(safeIndex, 0, source);
    if (nextSymbols.join("|") === current.join("|")) {
        return;
    }
    state.chart.symbols = nextSymbols;
    if (persistOrder) {
        persistChartSymbols();
    }
    animateChartSymbolLayout();
}

function moveChartSymbol(sourceSymbol, targetSymbol) {
    const source = normalizeTradingViewSymbol(sourceSymbol);
    const target = normalizeTradingViewSymbol(targetSymbol);
    const symbolsWithoutSource = state.chart.symbols.filter((symbol) => symbol !== source);
    moveChartSymbolToIndex(source, symbolsWithoutSource.indexOf(target), true);
}

function finalizeChartSymbolDrag(commitOrder) {
    if (!commitOrder && Array.isArray(state.chart.dragOriginalSymbols) && state.chart.dragOriginalSymbols.length) {
        state.chart.symbols = [...state.chart.dragOriginalSymbols];
    }
    state.chart.draggingSymbol = "";
    state.chart.dragOriginalSymbols = [];
    state.chart.dragCommitted = false;
    if (elements.chartSymbolList instanceof HTMLElement) {
        elements.chartSymbolList.classList.remove("is-dragging");
    }
    renderChartControls();
}

function isPointerInsideChartSymbolList(clientX, clientY) {
    if (!(elements.chartSymbolList instanceof HTMLElement) || !clientX || !clientY) {
        return false;
    }
    const rect = elements.chartSymbolList.getBoundingClientRect();
    return clientX >= rect.left && clientX <= rect.right && clientY >= rect.top && clientY <= rect.bottom;
}

function updateChartSymbolDragPosition(event) {
    if (!state.chart.draggingSymbol || !isPointerInsideChartSymbolList(event.clientX, event.clientY)) {
        return false;
    }
    event.preventDefault();
    if (event.dataTransfer) {
        event.dataTransfer.dropEffect = "move";
    }
    moveChartSymbolToIndex(state.chart.draggingSymbol, getChartDragInsertionIndex(event.clientY));
    return true;
}

function commitChartSymbolDrag(event) {
    if (!state.chart.draggingSymbol || !isPointerInsideChartSymbolList(event.clientX, event.clientY)) {
        return false;
    }
    event.preventDefault();
    moveChartSymbolToIndex(state.chart.draggingSymbol, getChartDragInsertionIndex(event.clientY));
    state.chart.dragCommitted = true;
    persistChartSymbols();
    finalizeChartSymbolDrag(true);
    return true;
}

function resetChartPointerDrag() {
    state.chart.dragPointerSymbol = "";
    state.chart.dragPointerStartX = 0;
    state.chart.dragPointerStartY = 0;
    state.chart.dragPointerActive = false;
}

function beginChartPointerDrag(symbol, event) {
    const normalized = normalizeTradingViewSymbol(symbol);
    if (!normalized || !state.chart.symbols.includes(normalized)) {
        return;
    }
    state.chart.dragPointerSymbol = normalized;
    state.chart.dragPointerStartX = event.clientX;
    state.chart.dragPointerStartY = event.clientY;
    state.chart.dragOriginalSymbols = [...state.chart.symbols];
    state.chart.dragCommitted = false;
    state.chart.dragPointerActive = false;
}

function activateChartPointerDrag() {
    if (!state.chart.dragPointerSymbol || state.chart.dragPointerActive) {
        return;
    }
    state.chart.dragPointerActive = true;
    state.chart.draggingSymbol = state.chart.dragPointerSymbol;
    if (elements.chartSymbolList instanceof HTMLElement) {
        elements.chartSymbolList.classList.add("is-dragging");
        const item = Array.from(elements.chartSymbolList.querySelectorAll("[data-chart-symbol-item]"))
            .find((node) => node instanceof HTMLElement && node.dataset.chartSymbolItem === state.chart.draggingSymbol);
        if (item instanceof HTMLElement) {
            item.classList.add("is-dragging");
        }
    }
}

function updateChartPointerDrag(event) {
    if (!state.chart.dragPointerSymbol) {
        return;
    }
    const deltaX = event.clientX - state.chart.dragPointerStartX;
    const deltaY = event.clientY - state.chart.dragPointerStartY;
    if (!state.chart.dragPointerActive && Math.hypot(deltaX, deltaY) < 5) {
        return;
    }
    event.preventDefault();
    activateChartPointerDrag();
    moveChartSymbolToIndex(state.chart.dragPointerSymbol, getChartDragInsertionIndex(event.clientY));
}

function finishChartPointerDrag(commitOrder) {
    if (!state.chart.dragPointerSymbol) {
        return;
    }
    const wasActive = state.chart.dragPointerActive;
    if (wasActive && commitOrder) {
        state.chart.dragCommitted = true;
        persistChartSymbols();
        state.chart.suppressNextSymbolClick = true;
        finalizeChartSymbolDrag(true);
    } else if (wasActive) {
        state.chart.suppressNextSymbolClick = true;
        finalizeChartSymbolDrag(false);
    } else {
        state.chart.dragOriginalSymbols = [];
        state.chart.dragCommitted = false;
    }
    resetChartPointerDrag();
}

function renderAdminHistoryPolicyControls() {
    if (!(elements.adminHistoryPolicyPanel instanceof HTMLElement)) {
        return;
    }
    const toggle = elements.adminHistoryPublicReadToggle;
    const button = elements.saveAdminHistoryPolicyButton;
    const disabled = !state.auth.isAdmin || state.admin.loading || state.admin.historyPolicySaving;

    elements.adminHistoryPolicyPanel.classList.toggle("is-disabled", !state.auth.isAdmin);
    if (toggle instanceof HTMLInputElement) {
        toggle.checked = Boolean(state.admin.historyPublicRead);
        toggle.disabled = disabled;
    }
    if (button instanceof HTMLButtonElement) {
        button.disabled = disabled;
        button.textContent = state.admin.historyPolicySaving ? "Saving" : "Save policy";
    }
}

function renderAdminPage() {
    if (!(elements.adminUserList instanceof HTMLElement) || !(elements.adminProcessList instanceof HTMLElement)) {
        return;
    }
    renderAdminHistoryPolicyControls();
    renderAdminSubTabs();

    const activeTab = state.admin.activeTab === "processes" ? "processes" : "users";

    if (elements.adminUsersPanel instanceof HTMLElement) {
        elements.adminUsersPanel.classList.toggle("hidden", activeTab !== "users");
    }
    if (elements.adminProcessesPanel instanceof HTMLElement) {
        elements.adminProcessesPanel.classList.toggle("hidden", activeTab !== "processes");
    }

    if (activeTab === "users") {
        renderAdminUsersTab();
    } else {
        renderAdminProcessesTab();
    }
}

function renderAdminSubTabs() {
    if (!(elements.adminTabUsers instanceof HTMLElement) || !(elements.adminTabProcesses instanceof HTMLElement)) {
        return;
    }
    const activeTab = state.admin.activeTab === "processes" ? "processes" : "users";
    elements.adminTabUsers.classList.toggle("is-active", activeTab === "users");
    elements.adminTabProcesses.classList.toggle("is-active", activeTab === "processes");
}

function renderAdminUsersTab() {
    setElementLoadingState(elements.adminUserList, state.admin.loading, "Loading users");
    if (!state.auth.isAdmin) {
        elements.adminStatusText.textContent = "Admin only";
        elements.adminUserList.innerHTML = '<div class="history-empty">Admin permission is required.</div>';
        return;
    }
    if (state.admin.loading) {
        elements.adminStatusText.textContent = "Loading users";
        elements.adminUserList.innerHTML = '<div class="history-empty">Loading users...</div>';
        return;
    }
    if (state.admin.error) {
        elements.adminStatusText.textContent = "Admin issue";
        elements.adminUserList.innerHTML = `<div class="history-empty">${escapeHtml(state.admin.error)}</div>`;
        return;
    }
    if (!state.admin.users.length) {
        elements.adminStatusText.textContent = state.admin.loaded ? "No users" : "Waiting";
        elements.adminUserList.innerHTML = '<div class="history-empty">No users have signed in yet.</div>';
        return;
    }
    elements.adminStatusText.textContent = `${state.admin.users.length} users`;
    elements.adminUserList.innerHTML = state.admin.users
        .map((user) => {
            const email = user.email || "";
            const unlimited = Boolean(user.history_access_unlimited || user.history_access_days == null);
            const isAdmin = Boolean(user.is_admin);
            const canRunAnalysis = isAdmin || Boolean(user.can_run_analysis);
            const hasHistoryAccess = isAdmin || unlimited || Number(user.history_access_days ?? 0) > 0;
            const isSeedAdmin = Boolean(user.is_seed_admin);
            const isSaving = state.admin.savingEmail === email;
            const roleLabel = isAdmin ? "Admin" : canRunAnalysis ? "Can run" : hasHistoryAccess ? "History only" : "No history";
            const dayValue = user.history_access_days ?? state.config?.history?.default_access_days ?? 7;
            return `
                <article class="admin-user-card ${isAdmin ? "is-admin-role" : ""} ${canRunAnalysis ? "can-run-analysis" : ""} ${unlimited ? "is-history-unlimited" : ""}" data-admin-email="${escapeHtml(email)}" data-seed-admin="${isSeedAdmin ? "true" : "false"}">
                    <div class="admin-user-main">
                        <div class="admin-user-title">
                            <strong>${escapeHtml(email || "Unknown user")}</strong>
                            <span class="admin-role-badge">${escapeHtml(roleLabel)}</span>
                        </div>
                        <span>${escapeHtml(user.name || "Google user")}</span>
                        <small>Last seen: ${escapeHtml(formatHistoryTimestamp(user.last_seen_at || ""))}</small>
                    </div>
                    <div class="admin-permission-panel" aria-label="User permissions">
                        <label class="admin-switch">
                            <input type="checkbox" data-admin-field="can_run_analysis" ${canRunAnalysis ? "checked" : ""} ${isAdmin ? "disabled" : ""}>
                            <span><strong>Run agent</strong><small>Can start analysis jobs</small></span>
                        </label>
                        <label class="admin-switch">
                            <input type="checkbox" data-admin-field="is_admin" ${isAdmin ? "checked" : ""} ${isSeedAdmin ? "disabled" : ""}>
                            <span><strong>Admin</strong><small>Manage users and access</small></span>
                        </label>
                    </div>
                    <div class="admin-history-panel" aria-label="History access">
                        <label class="admin-switch admin-unlimited-switch">
                            <input type="checkbox" data-admin-field="history_unlimited" ${unlimited ? "checked" : ""} ${isAdmin ? "disabled" : ""}>
                            <span><strong>Unlimited history</strong><small>View all saved runs</small></span>
                        </label>
                        <label class="admin-days-field">
                            <span>History window</span>
                            <div class="admin-days-input-wrap">
                                <input type="number" min="0" step="1" data-admin-field="history_days" value="${escapeHtml(String(dayValue))}" ${unlimited ? "disabled" : ""}>
                                <small>days, 0 = blocked</small>
                            </div>
                        </label>
                    </div>
                    <button class="button secondary admin-save-button" type="button" data-admin-save-user="${escapeHtml(email)}" ${isSaving ? "disabled" : ""}>${isSaving ? "Saving" : "Save"}</button>
                </article>
            `;
        })
        .join("");
}

function renderAdminProcessesTab() {
    setElementLoadingState(elements.adminProcessList, state.admin.processesLoading, "Loading active processes");
    if (!state.auth.isAdmin) {
        elements.adminStatusText.textContent = "Admin only";
        elements.adminProcessList.innerHTML = '<div class="history-empty">Admin permission is required.</div>';
        return;
    }
    if (state.admin.processesLoading) {
        elements.adminStatusText.textContent = "Loading processes";
        elements.adminProcessList.innerHTML = '<div class="history-empty">Loading active processes...</div>';
        return;
    }
    if (state.admin.processesError) {
        elements.adminStatusText.textContent = "Process issue";
        elements.adminProcessList.innerHTML = `<div class="history-empty">${escapeHtml(state.admin.processesError)}</div>`;
        return;
    }
    const runs = state.admin.processes || [];
    if (!runs.length) {
        elements.adminStatusText.textContent = "0 active runs";
        elements.adminProcessList.innerHTML = '<div class="history-empty">No active analysis runs found.</div>';
        return;
    }
    elements.adminStatusText.textContent = `${runs.length} active run${runs.length > 1 ? "s" : ""}`;
    elements.adminProcessList.innerHTML = runs
        .map((run) => {
            const elapsed = formatElapsedTime(run.elapsed_seconds);
            const isCancelling = state.admin.cancellingRunId === run.run_id;
            return `
                <article class="admin-process-card ${isCancelling ? "is-cancelling" : ""}" data-admin-run-id="${escapeHtml(run.run_id)}">
                    <div class="admin-process-main">
                        <div class="admin-process-title">
                            <strong>${escapeHtml(run.symbol)}</strong>
                            <span class="admin-process-badge">Running</span>
                        </div>
                        <small>ID: ${escapeHtml(run.run_id)}</small>
                        <span class="admin-process-user">
                            <span>${escapeHtml(run.user_name || run.user_email || "Unknown")}</span>
                            <small>${escapeHtml(run.user_email)}</small>
                        </span>
                        <small class="admin-process-elapsed">Elapsed: ${escapeHtml(elapsed)}</small>
                    </div>
                    <button class="button primary admin-cancel-button" type="button" data-admin-cancel-run="${escapeHtml(run.run_id)}" ${isCancelling ? "disabled" : ""}>${isCancelling ? "Cancelling" : "Cancel Analysis"}</button>
                </article>
            `;
        })
        .join("");
}

function formatElapsedTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) {
        return "0s";
    }
    const secs = Math.round(seconds);
    if (secs < 60) {
        return `${secs}s`;
    }
    const mins = Math.floor(secs / 60);
    const remain = secs % 60;
    if (mins < 60) {
        return `${mins}m ${remain}s`;
    }
    const hours = Math.floor(mins / 60);
    return `${hours}h ${mins % 60}m`;
}

async function loadAdminProcesses(force = false) {
    if (!state.auth.isAdmin) {
        openAuthRequiredAlert("Admin permission is required to view active processes.");
        return;
    }
    if (state.admin.processesLoading || (state.admin.processesLoaded && !force)) {
        renderAdminPage();
        return;
    }
    state.admin.processesLoading = true;
    state.admin.processesError = "";
    renderAdminPage();
    try {
        const response = await apiFetch("/api/admin/runs", {
            headers: getAdminAuthHeaders(),
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }
        const payload = await response.json();
        state.admin.processes = payload.runs || [];
        state.admin.processesLoaded = true;
    } catch (error) {
        state.admin.processesError = error instanceof Error ? error.message : String(error || "Could not load active processes.");
    } finally {
        state.admin.processesLoading = false;
        renderAdminPage();
    }
}

async function cancelAdminRun(runId) {
    if (!state.auth.isAdmin || !runId) {
        return;
    }
    state.admin.cancellingRunId = runId;
    state.admin.processesError = "";
    renderAdminPage();
    try {
        const response = await apiFetch(`/api/analyze/${encodeURIComponent(runId)}/cancel`, {
            method: "POST",
            headers: getAdminAuthHeaders({ "Content-Type": "application/json" }),
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }
        await new Promise((r) => setTimeout(r, 500));
        await loadAdminProcesses(true);
    } catch (error) {
        state.admin.processesError = error instanceof Error ? error.message : String(error || "Could not cancel analysis.");
    } finally {
        state.admin.cancellingRunId = "";
        renderAdminPage();
    }
}

function syncAdminCardControls(card) {
    if (!(card instanceof HTMLElement)) {
        return;
    }
    const isSeedAdmin = card.dataset.seedAdmin === "true";
    const isAdminInput = card.querySelector('[data-admin-field="is_admin"]');
    const canRunInput = card.querySelector('[data-admin-field="can_run_analysis"]');
    const unlimitedInput = card.querySelector('[data-admin-field="history_unlimited"]');
    const daysInput = card.querySelector('[data-admin-field="history_days"]');
    const isAdmin = isAdminInput instanceof HTMLInputElement && isAdminInput.checked;
    if (isSeedAdmin && isAdminInput instanceof HTMLInputElement) {
        isAdminInput.checked = true;
        isAdminInput.disabled = true;
    }
    if (canRunInput instanceof HTMLInputElement) {
        if (isAdmin || isSeedAdmin) {
            canRunInput.checked = true;
            canRunInput.disabled = true;
        } else {
            canRunInput.disabled = false;
        }
    }
    if (unlimitedInput instanceof HTMLInputElement) {
        if (isAdmin || isSeedAdmin) {
            unlimitedInput.checked = true;
            unlimitedInput.disabled = true;
        } else {
            unlimitedInput.disabled = false;
        }
    }
    const historyUnlimited = unlimitedInput instanceof HTMLInputElement && unlimitedInput.checked;
    if (daysInput instanceof HTMLInputElement) {
        daysInput.disabled = historyUnlimited;
        daysInput.setAttribute("aria-disabled", historyUnlimited ? "true" : "false");
    }
    card.classList.toggle("is-admin-role", isAdmin || isSeedAdmin);
    card.classList.toggle("can-run-analysis", Boolean(canRunInput instanceof HTMLInputElement && canRunInput.checked));
    card.classList.toggle("is-history-unlimited", historyUnlimited);
    const roleBadge = card.querySelector(".admin-role-badge");
    if (roleBadge instanceof HTMLElement) {
        const historyWindow = daysInput instanceof HTMLInputElement ? Number(daysInput.value || 0) : 0;
        const hasHistoryAccess = isAdmin || isSeedAdmin || historyUnlimited || historyWindow > 0;
        roleBadge.textContent = isAdmin || isSeedAdmin ? "Admin" : canRunInput instanceof HTMLInputElement && canRunInput.checked ? "Can run" : hasHistoryAccess ? "History only" : "No history";
    }
}

async function saveAdminHistoryAccessPolicy() {
    if (!state.auth.isAdmin) {
        openAuthRequiredAlert("Admin permission is required to update history access.");
        return;
    }
    const toggle = elements.adminHistoryPublicReadToggle;
    const nextValue = toggle instanceof HTMLInputElement ? toggle.checked : Boolean(state.admin.historyPublicRead);
    state.admin.historyPolicySaving = true;
    renderAdminPage();
    try {
        const response = await apiFetch("/api/admin/history-access", {
            method: "PATCH",
            headers: getAdminAuthHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ history_public_read: nextValue }),
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }
        const payload = await response.json();
        state.admin.historyPublicRead = Boolean(payload.history_public_read);
        if (state.config?.history) {
            state.config.history.public_read = state.admin.historyPublicRead;
        }
        state.admin.error = "";
    } catch (error) {
        state.admin.error = error instanceof Error ? error.message : String(error || "Could not save history access policy.");
    } finally {
        state.admin.historyPolicySaving = false;
        renderAdminPage();
    }
}

async function loadAdminUsers(force = false) {
    if (!state.auth.isAdmin) {
        openAuthRequiredAlert("Admin permission is required to open user management.");
        return;
    }
    if (state.admin.loading || (state.admin.loaded && !force)) {
        renderAdminPage();
        return;
    }
    state.admin.loading = true;
    state.admin.error = "";
    renderAdminPage();
    try {
        const response = await apiFetch("/api/admin/users", {
            headers: getAdminAuthHeaders(),
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }
        const payload = await response.json();
        state.admin.users = payload.items || [];
        state.admin.historyPublicRead = Boolean(payload.history_public_read ?? state.config?.history?.public_read ?? false);
        if (state.config?.history) {
            state.config.history.public_read = state.admin.historyPublicRead;
        }
        state.admin.loaded = true;
    } catch (error) {
        state.admin.error = error instanceof Error ? error.message : String(error || "Could not load users.");
    } finally {
        state.admin.loading = false;
        renderAdminPage();
    }
}

async function saveAdminUser(email) {
    const card = Array.from(elements.adminUserList?.querySelectorAll("[data-admin-email]") || [])
        .find((item) => item instanceof HTMLElement && item.dataset.adminEmail === email);
    if (!(card instanceof HTMLElement)) {
        return;
    }
    const isAdminInput = card.querySelector('[data-admin-field="is_admin"]');
    const canRunInput = card.querySelector('[data-admin-field="can_run_analysis"]');
    const unlimitedInput = card.querySelector('[data-admin-field="history_unlimited"]');
    const daysInput = card.querySelector('[data-admin-field="history_days"]');
    const isAdmin = isAdminInput instanceof HTMLInputElement ? isAdminInput.checked : false;
    const canRunAnalysis = canRunInput instanceof HTMLInputElement ? canRunInput.checked : false;
    const unlimited = unlimitedInput instanceof HTMLInputElement ? unlimitedInput.checked : false;
    const days = daysInput instanceof HTMLInputElement ? Number(daysInput.value || 0) : 0;
    state.admin.savingEmail = email;
    renderAdminPage();
    try {
        const response = await apiFetch(`/api/admin/users/${encodeURIComponent(email)}`, {
            method: "PATCH",
            headers: getAdminAuthHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({
                is_admin: isAdmin,
                can_run_analysis: isAdmin || canRunAnalysis,
                history_access_days: unlimited ? null : Math.max(0, Number.isFinite(days) ? days : 0),
                history_access_unlimited: unlimited,
            }),
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }
        const payload = await response.json();
        const updated = payload.item;
        state.admin.users = state.admin.users.map((user) => (user.email === email ? updated : user));
        state.admin.error = "";
    } catch (error) {
        state.admin.error = error instanceof Error ? error.message : String(error || "Could not save user.");
    } finally {
        state.admin.savingEmail = "";
        renderAdminPage();
    }
}

function switchPage(page) {
    if (!PAGES.includes(page)) {
        return;
    }
    if (page === "history" && !state.auth.idToken && !state.auth.isAuthorized) {
        openAuthRequiredAlert();
        return;
    }
    if (page === "history" && state.auth.isAuthorized && !canReadHistory()) {
        openBackendIssueAlert("History access is disabled for this account.");
        return;
    }
    if (page === "admin" && !canOpenAdminPage()) {
        openAuthRequiredAlert("Admin permission is required to open user management.");
        return;
    }
    if (page === "chat" && !canOpenChatPage()) {
        openAuthRequiredAlert("Admin permission is required to use Chat.");
        return;
    }
    state.page = page;
    renderPageShell();
    if (page === "history") {
        loadHistoryList().catch((error) => {
            state.history.error = error instanceof Error ? error.message : String(error || "Could not load history.");
            renderHistoryPage();
        });
    }
    if (page === "chart") {
        loadTradingViewChart();
    }
    if (page === "admin") {
        loadAdminUsers().catch((error) => {
            state.admin.error = error instanceof Error ? error.message : String(error || "Could not load users.");
            renderAdminPage();
        });
    }
    if (page === "chat") {
        renderChatPage();
    }
}

window.addEventListener("resize", () => {
    if (state.page === "history") {
        scheduleHistoryTableLayoutMetrics();
    }
});

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

