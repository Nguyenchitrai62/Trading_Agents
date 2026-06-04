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
    if (!(elements.adminUserList instanceof HTMLElement)) {
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
    } else if (elements.adminProcessList instanceof HTMLElement) {
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

function buildAdminPaginationItems(totalPages, currentPage) {
    const safeTotal = Math.max(1, Number(totalPages || 1));
    const safeCurrent = Math.min(Math.max(1, Number(currentPage || 1)), safeTotal);
    if (safeTotal <= 7) {
        return Array.from({ length: safeTotal }, (_, i) => ({ type: "page", page: i + 1 }));
    }
    const items = [{ type: "page", page: 1 }];
    const middleStart = Math.max(2, safeCurrent - 1);
    const middleEnd = Math.min(safeTotal - 1, safeCurrent + 1);
    if (middleStart > 2) {
        items.push({ type: "ellipsis", key: `admin-ellipsis-start-${safeCurrent}` });
    }
    for (let p = middleStart; p <= middleEnd; p += 1) {
        items.push({ type: "page", page: p });
    }
    if (middleEnd < safeTotal - 1) {
        items.push({ type: "ellipsis", key: `admin-ellipsis-end-${safeCurrent}` });
    }
    items.push({ type: "page", page: safeTotal });
    return items;
}

function setAdminUsersPage(nextPage) {
    const safePage = Math.max(1, Number(nextPage || 1));
    if (safePage === state.admin.usersPage && state.admin.loaded && !state.admin.error) {
        return;
    }
    state.admin.usersPage = safePage;
    state.admin.loaded = false;
    loadAdminUsers(true).catch((error) => {
        state.admin.error = error instanceof Error ? error.message : String(error || "Could not change page.");
        renderAdminPage();
    });
}

function adminToggleIcon(value) {
    return value
        ? '<span class="admin-toggle-on" role="img" aria-label="Enabled">&#10003;</span>'
        : '<span class="admin-toggle-off" role="img" aria-label="Disabled">&#10007;</span>';
}

function getAdminRowValue(row, field) {
    const cell = row instanceof HTMLElement ? row.querySelector(`[data-admin-field="${field}"]`) : null;
    if (!(cell instanceof HTMLElement)) return null;
    if (cell.dataset.adminField === field && cell.classList.contains("admin-col-toggle")) {
        return cell.dataset.adminValue === "true";
    }
    if (cell instanceof HTMLInputElement) {
        return cell.value;
    }
    return null;
}

function setAdminRowToggle(cell, value) {
    if (!(cell instanceof HTMLElement)) return;
    cell.dataset.adminValue = value ? "true" : "false";
    cell.innerHTML = adminToggleIcon(value);
}

function syncAdminRowControls(row) {
    if (!(row instanceof HTMLElement)) return;
    const email = row.dataset.adminEmail || "";
    const user = state.admin.users.find((u) => (u.email || "") === email);
    const isSeedAdmin = Boolean(user && user.is_seed_admin);
    const adminCell = row.querySelector('[data-admin-field="is_admin"]');
    const canRunCell = row.querySelector('[data-admin-field="can_run_analysis"]');
    const unlimCell = row.querySelector('[data-admin-field="history_unlimited"]');
    const daysInput = row.querySelector('[data-admin-field="history_days"]');
    const roleBadge = row.querySelector(".admin-role-badge");
    const isAdmin = adminCell instanceof HTMLElement && adminCell.dataset.adminValue === "true";
    if (isSeedAdmin && adminCell instanceof HTMLElement) {
        setAdminRowToggle(adminCell, true);
        adminCell.classList.add("admin-toggle-locked");
    }
    if (canRunCell instanceof HTMLElement) {
        if (isAdmin || isSeedAdmin) {
            setAdminRowToggle(canRunCell, true);
            canRunCell.classList.add("admin-toggle-locked");
        } else {
            canRunCell.classList.remove("admin-toggle-locked");
        }
    }
    if (unlimCell instanceof HTMLElement) {
        if (isAdmin || isSeedAdmin) {
            setAdminRowToggle(unlimCell, true);
            unlimCell.classList.add("admin-toggle-locked");
        } else {
            unlimCell.classList.remove("admin-toggle-locked");
        }
    }
    const unlimOn = unlimCell instanceof HTMLElement && unlimCell.dataset.adminValue === "true";
    if (daysInput instanceof HTMLInputElement) {
        daysInput.disabled = unlimOn || isAdmin || isSeedAdmin;
    }
    if (roleBadge instanceof HTMLElement) {
        const canRun = canRunCell instanceof HTMLElement && canRunCell.dataset.adminValue === "true";
        const daysVal = daysInput instanceof HTMLInputElement ? Number(daysInput.value || 0) : 0;
        const hasHistory = isAdmin || isSeedAdmin || unlimOn || daysVal > 0;
        roleBadge.textContent = isAdmin || isSeedAdmin ? "Admin" : canRun ? "Can run" : hasHistory ? "History only" : "No history";
    }
}

function renderAdminUsersTab() {
    if (!(elements.adminUserList instanceof HTMLElement)) {
        return;
    }

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

    const totalCount = Math.max(0, Number(state.admin.usersTotalCount || 0));
    const totalPages = Math.max(1, Number(state.admin.usersTotalPages || 1));
    const currentPage = Math.min(Math.max(1, Number(state.admin.usersPage || 1)), totalPages);
    const currentLimit = Math.max(1, Number(state.admin.usersLimit || 20));
    const startIndex = totalCount ? (currentPage - 1) * currentLimit + 1 : 0;

    elements.adminStatusText.textContent = `${totalCount} user${totalCount !== 1 ? "s" : ""}`;

    const paginationChips = buildAdminPaginationItems(totalPages, currentPage)
        .map((item) => {
            if (item.type === "ellipsis") return '<span class="history-page-ellipsis">...</span>';
            return `<button class="history-page-chip ${item.page === currentPage ? "is-active" : ""}" data-admin-page-target="${item.page}" type="button">${item.page}</button>`;
        })
        .join("");

    elements.adminUserList.innerHTML = `
        <div class="admin-table-shell">
            <div class="history-table-toolbar">
                <div class="history-table-stats">
                    <strong>${totalCount} user${totalCount !== 1 ? "s" : ""}</strong>
                    <span>Page ${currentPage} of ${totalPages}</span>
                </div>
            </div>
            <div class="admin-table-wrap">
                <table class="admin-users-table">
                    <thead>
                        <tr>
                            <th class="admin-col-num">#</th>
                            <th class="admin-col-email">Email</th>
                            <th class="admin-col-name">Name</th>
                            <th class="admin-col-role">Role</th>
                            <th class="admin-col-toggle-h">Run</th>
                            <th class="admin-col-toggle-h">Admin</th>
                            <th class="admin-col-toggle-h">Unlim</th>
                            <th class="admin-col-days-h">Days</th>
                            <th class="admin-col-seen">Last seen</th>
                            <th class="admin-col-save">Save</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${state.admin.users
                            .map((user, index) => {
                                const email = user.email || "";
                                const unlimited = Boolean(user.history_access_unlimited || user.history_access_days == null);
                                const isAdmin = Boolean(user.is_admin);
                                const isSeedAdmin = Boolean(user.is_seed_admin);
                                const canRunAnalysis = isAdmin || Boolean(user.can_run_analysis);
                                const dayValue = user.history_access_days ?? "";
                                const hasHistoryAccess = isAdmin || unlimited || Number(user.history_access_days ?? 0) > 0;
                                const roleLabel = isAdmin ? "Admin" : canRunAnalysis ? "Can run" : hasHistoryAccess ? "History only" : "No history";
                                const isSaving = state.admin.savingEmail === email;
                                const isDirty = state.admin.dirtyEmails.has(email);
                                const saveClass = isDirty ? "button primary admin-save-button admin-save-dirty" : "button secondary admin-save-button";
                                const saveText = isSaving ? "Saving" : isDirty ? "Save *" : "Save";
                                return `
                                    <tr class="admin-user-row" data-admin-email="${escapeHtml(email)}">
                                        <td class="admin-col-num">${startIndex + index}</td>
                                        <td class="admin-col-email">${escapeHtml(email || "Unknown")}</td>
                                        <td class="admin-col-name">${escapeHtml(user.name || "Google user")}</td>
                                        <td class="admin-col-role"><span class="admin-role-badge">${escapeHtml(roleLabel)}</span></td>
                                        <td class="admin-col-toggle ${isAdmin || isSeedAdmin ? "admin-toggle-locked" : ""}" data-admin-field="can_run_analysis" data-admin-value="${canRunAnalysis ? "true" : "false"}">${adminToggleIcon(canRunAnalysis)}</td>
                                        <td class="admin-col-toggle ${isSeedAdmin ? "admin-toggle-locked" : ""}" data-admin-field="is_admin" data-admin-value="${isAdmin ? "true" : "false"}">${adminToggleIcon(isAdmin)}</td>
                                        <td class="admin-col-toggle ${isAdmin || isSeedAdmin ? "admin-toggle-locked" : ""}" data-admin-field="history_unlimited" data-admin-value="${unlimited ? "true" : "false"}">${adminToggleIcon(unlimited)}</td>
                                        <td class="admin-col-days"><input type="number" min="0" step="1" data-admin-field="history_days" value="${escapeHtml(String(dayValue))}" ${unlimited || isAdmin || isSeedAdmin ? "disabled" : ""}></td>
                                        <td class="admin-col-seen">${escapeHtml(formatHistoryTimestamp(user.last_seen_at || ""))}</td>
                                        <td class="admin-col-save"><button class="${saveClass}" type="button" data-admin-save-user="${escapeHtml(email)}" ${isSaving ? "disabled" : ""}>${escapeHtml(saveText)}</button></td>
                                    </tr>
                                `;
                            })
                            .join("")}
                    </tbody>
                </table>
            </div>
            ${totalPages > 1
                ? `<div class="history-table-footer">
                    <span class="history-table-footer-meta">Page ${currentPage} of ${totalPages}</span>
                    <nav class="history-page-nav">
                        <button class="history-page-button" data-admin-page-nav="first" type="button" ${currentPage <= 1 ? "disabled" : ""}>&laquo;</button>
                        <button class="history-page-button" data-admin-page-nav="prev" type="button" ${currentPage <= 1 ? "disabled" : ""}>&lsaquo;</button>
                        <div class="history-page-track">${paginationChips}</div>
                        <button class="history-page-button" data-admin-page-nav="next" type="button" ${currentPage >= totalPages ? "disabled" : ""}>&rsaquo;</button>
                        <button class="history-page-button" data-admin-page-nav="last" type="button" ${currentPage >= totalPages ? "disabled" : ""}>&raquo;</button>
                    </nav>
                </div>`
                : ""}
        </div>
    `;
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
        const page = state.admin.usersPage || 1;
        const limit = state.admin.usersLimit || 20;
        const response = await apiFetch(`/api/admin/users?page=${page}&limit=${limit}`, {
            headers: getAdminAuthHeaders(),
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }
        const payload = await response.json();
        state.admin.users = (payload.items || []).map((user) => ({
            ...user,
            email: user.email || "",
        }));
        state.admin.usersPage = Number(payload.page || 1);
        state.admin.usersLimit = Number(payload.limit || 20);
        state.admin.usersTotalCount = Math.max(0, Number(payload.total_count || 0));
        state.admin.usersTotalPages = Math.max(1, Number(payload.total_pages || 1));
        state.admin.historyPublicRead = Boolean(payload.history_public_read ?? state.config?.history?.public_read ?? false);
        if (state.config?.history) {
            state.config.history.public_read = state.admin.historyPublicRead;
        }
        state.admin.loaded = true;
        state.admin.dirtyEmails = new Set();
    } catch (error) {
        state.admin.error = error instanceof Error ? error.message : String(error || "Could not load users.");
    } finally {
        state.admin.loading = false;
        renderAdminPage();
    }
}

async function saveAdminUser(email) {
    const row = elements.adminUserList?.querySelector(`[data-admin-email="${CSS.escape(email)}"]`);
    if (!(row instanceof HTMLElement)) {
        return;
    }
    const adminCell = row.querySelector('[data-admin-field="is_admin"]');
    const canRunCell = row.querySelector('[data-admin-field="can_run_analysis"]');
    const unlimCell = row.querySelector('[data-admin-field="history_unlimited"]');
    const daysInput = row.querySelector('[data-admin-field="history_days"]');
    const isAdmin = adminCell instanceof HTMLElement && adminCell.dataset.adminValue === "true";
    const canRunAnalysis = canRunCell instanceof HTMLElement && canRunCell.dataset.adminValue === "true";
    const unlimited = unlimCell instanceof HTMLElement && unlimCell.dataset.adminValue === "true";
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
        state.admin.dirtyEmails.delete(email);
        state.admin.error = "";
    } catch (error) {
        state.admin.error = error instanceof Error ? error.message : String(error || "Could not save user.");
    } finally {
        state.admin.savingEmail = "";
        renderAdminPage();
    }
}

let _pollTimer = null;

function stopPollingInterval() {
    if (_pollTimer !== null) {
        clearInterval(_pollTimer);
        _pollTimer = null;
    }
}

function startPollingInterval(page) {
    stopPollingInterval();
    _pollTimer = setInterval(() => {
        if (state.page !== page) {
            stopPollingInterval();
            return;
        }
        if (page === "history") {
            if (state.history.loading) return;
            loadHistoryList(true).catch(() => {});
        }
        if (page === "admin") {
            if (state.admin.activeTab === "processes") {
                if (state.admin.processesLoading) return;
                loadAdminProcesses(true).catch(() => {});
            } else {
                if (state.admin.loading) return;
                loadAdminUsers(true).catch(() => {});
            }
        }
    }, 2000);
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
    stopPollingInterval();
    if (page === "history") {
        loadHistoryList().catch((error) => {
            state.history.error = error instanceof Error ? error.message : String(error || "Could not load history.");
            renderHistoryPage();
        });
        startPollingInterval("history");
    }
    if (page === "chart") {
        loadTradingViewChart();
    }
    if (page === "admin") {
        loadAdminUsers().catch((error) => {
            state.admin.error = error instanceof Error ? error.message : String(error || "Could not load users.");
            renderAdminPage();
        });
        startPollingInterval("admin");
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

