function formatHistoryTimestamp(value = "") {
    if (!value) {
        return "-";
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatHistoryDateTime(value = "") {
    if (!value) {
        return "-";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    const day = String(date.getDate()).padStart(2, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const year = String(date.getFullYear()).slice(-2);
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const seconds = String(date.getSeconds()).padStart(2, "0");
    return `${day}/${month}/${year} ${hours}:${minutes}:${seconds}`;
}

function formatHistoryElapsedSeconds(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds)) {
        return "-";
    }
    const roundedSeconds = Math.max(0, Math.round(seconds));
    const minutes = Math.floor(roundedSeconds / 60);
    const remainingSeconds = roundedSeconds % 60;
    return `${minutes}m ${String(remainingSeconds).padStart(2, "0")}s`;
}

function formatHistoryPrice(value) {
    if (value === null) {
        return "null";
    }
    if (value === undefined || value === "") {
        return "-";
    }
    const price = Number(value);
    if (!Number.isFinite(price)) {
        return "-";
    }
    return price.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

function getHistoryArchiveEntry(historyId = "") {
    if (!historyId) {
        return null;
    }
    return state.history.cache?.[historyId] || null;
}

function upsertHistoryArchiveEntry(item = {}, sections = null) {
    const historyId = String(item?.id || "").trim();
    if (!historyId) {
        return null;
    }
    const cache = state.history.cache || (state.history.cache = {});
    const existing = cache[historyId] || {};
    const resolvedSections = Array.isArray(sections)
        ? sections.map((section) => ({ ...section }))
        : Array.isArray(existing.sections)
        ? existing.sections
        : [];
    const activeSectionKey = existing.activeSectionKey || "";

    cache[historyId] = {
        item: {
            ...(existing.item || {}),
            ...item,
            sections: resolvedSections,
        },
        sections: resolvedSections,
        sectionMarkdown: { ...(existing.sectionMarkdown || {}) },
        activeSectionKey,
        sectionLoadingKeys: Array.isArray(existing.sectionLoadingKeys) ? [...existing.sectionLoadingKeys] : [],
        sectionRequests: existing.sectionRequests || {},
    };

    return cache[historyId];
}

function cacheHistoryItem(item = {}) {
    const historyId = String(item?.id || "").trim();
    if (!historyId) {
        return null;
    }
    const cache = state.history.cache || (state.history.cache = {});
    const existing = cache[historyId] || {};
    cache[historyId] = {
        ...existing,
        item: {
            ...(existing.item || {}),
            ...item,
        },
        sections: Array.isArray(existing.sections) ? existing.sections : [],
        sectionMarkdown: existing.sectionMarkdown || {},
        activeSectionKey: existing.activeSectionKey || "",
        sectionLoadingKeys: Array.isArray(existing.sectionLoadingKeys) ? existing.sectionLoadingKeys : [],
        sectionRequests: existing.sectionRequests || {},
    };
    return cache[historyId];
}

function syncHistoryActiveEntry(historyId = "") {
    const entry = getHistoryArchiveEntry(historyId);
    if (!entry) {
        return null;
    }
    if (state.history.activeId === historyId) {
        state.history.active = entry;
    }
    return entry;
}

function addHistoryLoadingKey(entry, sectionKey) {
    if (!entry || !sectionKey) {
        return;
    }
    const loadingKeys = Array.isArray(entry.sectionLoadingKeys) ? entry.sectionLoadingKeys : [];
    if (!loadingKeys.includes(sectionKey)) {
        entry.sectionLoadingKeys = [...loadingKeys, sectionKey];
    }
}

function removeHistoryLoadingKey(entry, sectionKey) {
    if (!entry || !sectionKey) {
        return;
    }
    entry.sectionLoadingKeys = (entry.sectionLoadingKeys || []).filter((key) => key !== sectionKey);
}

async function ensureHistorySectionMarkdown(historyId, sectionKey, options = {}) {
    const { silent = false } = options;
    const entry = syncHistoryActiveEntry(historyId);
    if (!entry || !sectionKey) {
        return "";
    }
    if (Object.prototype.hasOwnProperty.call(entry.sectionMarkdown || {}, sectionKey)) {
        return entry.sectionMarkdown[sectionKey] || "";
    }

    entry.sectionRequests = entry.sectionRequests || {};
    if (entry.sectionRequests[sectionKey]) {
        return entry.sectionRequests[sectionKey];
    }

    addHistoryLoadingKey(entry, sectionKey);
    if (state.history.activeId === historyId) {
        renderHistoryPage();
    }

    entry.sectionRequests[sectionKey] = (async () => {
        try {
            const response = await apiFetch(`/api/history/${encodeURIComponent(historyId)}/sections/${encodeURIComponent(sectionKey)}`, {
                headers: getAuthHeaders(),
                cache: "no-store",
            });
            if (!response.ok) {
                throw new Error(await readResponseError(response));
            }
            const payload = await response.json();
            entry.sectionMarkdown = {
                ...(entry.sectionMarkdown || {}),
                [sectionKey]: payload.section?.markdown || "",
            };
            state.history.error = "";
            return entry.sectionMarkdown[sectionKey];
        } catch (error) {
            if (!silent) {
                state.history.error = error instanceof Error ? error.message : String(error || "Could not load history section.");
            }
            throw error;
        } finally {
            removeHistoryLoadingKey(entry, sectionKey);
            delete entry.sectionRequests[sectionKey];
            if (state.history.activeId === historyId) {
                state.history.active = entry;
                renderHistoryPage();
            }
        }
    })();

    return entry.sectionRequests[sectionKey];
}

function buildHistoryPaginationItems(totalPages = 1, currentPage = 1) {
    const safeTotalPages = Math.max(1, Number(totalPages || 1));
    const safeCurrentPage = Math.min(Math.max(1, Number(currentPage || 1)), safeTotalPages);
    if (safeTotalPages <= 7) {
        return Array.from({ length: safeTotalPages }, (_, index) => ({ type: "page", page: index + 1 }));
    }
    const items = [{ type: "page", page: 1 }];
    const middleStart = Math.max(2, safeCurrentPage - 1);
    const middleEnd = Math.min(safeTotalPages - 1, safeCurrentPage + 1);
    if (middleStart > 2) {
        items.push({ type: "ellipsis", key: `ellipsis-start-${safeCurrentPage}` });
    }
    for (let pageNumber = middleStart; pageNumber <= middleEnd; pageNumber += 1) {
        items.push({ type: "page", page: pageNumber });
    }
    if (middleEnd < safeTotalPages - 1) {
        items.push({ type: "ellipsis", key: `ellipsis-end-${safeCurrentPage}` });
    }
    items.push({ type: "page", page: safeTotalPages });
    return items;
}

function getHistorySectionLabel(section = {}) {
    const agentLabel = getCompactAgentLabel(section.agent || "");
    if (agentLabel) {
        return agentLabel;
    }
    return String(section.title || section.section_key || "Section")
        .replace(/ Analysis$/, "")
        .replace(/ Research$/, "")
        .replace(/ Plan$/, "")
        .replace(/ Decision$/, "");
}

function getHistorySectionMeta(sectionKey = "") {
    return (state.history.active?.sections || []).find((section) => section.section_key === sectionKey) || null;
}

function renderHistoryDiagramIcon(iconKey = "default") {
    return HISTORY_DIAGRAM_ICONS[iconKey] || HISTORY_DIAGRAM_ICONS.default;
}

function renderHistoryCurveWire(paths = [], className = "", viewBox = "0 0 100 100") {
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

function buildHistoryDiagramModel(sections = []) {
    const diagramSections = sections.filter((section) => section.artifact_type !== "flow_block");
    const sectionsByKey = new Map(diagramSections.map((section) => [section.section_key, section]));
    const knownKeys = new Set(Object.values(HISTORY_FLOW_SECTION_ORDER).flat());
    const sourceSections = diagramSections.filter((section) => section.artifact_type === "source" || String(section.section_key || "").startsWith("source_"));
    const sourceGroups = {
        ccxt: sourceSections.filter((section) => section.flow_group === "ccxt_market_data"),
        coinglass: sourceSections.filter((section) => section.flow_group === "coinglass_data"),
        news: sourceSections.filter((section) => section.flow_group === "news_data"),
        social: sourceSections.filter((section) => section.flow_group === "social_web_data"),
        flow: sourceSections.filter((section) => section.flow_group === "flow_data"),
    };
    sourceSections.forEach((section) => knownKeys.add(section.section_key));
    return {
        sourceGroups,
        endpointSummaries: sectionsByKey.get("endpoint_summaries") || null,
        inputs: HISTORY_FLOW_SECTION_ORDER.inputs.map((key) => sectionsByKey.get(key)).filter(Boolean),
        evidence: sectionsByKey.get("structured_evidence") || null,
        researchNodes: ["bull_research", "research_debate", "bear_research"].map((key) => sectionsByKey.get(key)).filter(Boolean),
        investmentPlan: sectionsByKey.get("investment_plan") || null,
        investmentExtractor: sectionsByKey.get("investment_plan_structured") || null,
        trader: sectionsByKey.get("trader_investment_plan") || null,
        traderExtractor: sectionsByKey.get("trader_investment_plan_structured") || null,
        riskNodes: ["aggressive_risk", "neutral_risk", "conservative_risk", "risk_debate"].map((key) => sectionsByKey.get(key)).filter(Boolean),
        manager: sectionsByKey.get("final_trade_decision") || null,
        decisionExtractor: sectionsByKey.get("final_trade_decision_structured") || null,
        verifier: sectionsByKey.get("verification_report") || null,
        verifierStructured: sectionsByKey.get("verification_report_structured") || null,
        persistence: sectionsByKey.get("history_persistence") || null,
        extras: diagramSections.filter((section) => !knownKeys.has(section.section_key)),
    };
}

function renderHistoryDiagramNode(section = {}, options = {}, layout = {}) {
    const sectionKey = section.section_key || "";
    const flowMeta = HISTORY_FLOW_SECTION_META[sectionKey] || {};
    const activeSectionKey = options.activeSectionKey || "";
    const sectionMarkdown = options.sectionMarkdown || {};
    const loadingKeys = Array.isArray(options.loadingKeys) ? options.loadingKeys : [];
    const isActive = sectionKey === activeSectionKey;
    const isLoaded = Object.prototype.hasOwnProperty.call(sectionMarkdown, sectionKey);
    const loading = loadingKeys.includes(sectionKey);
    const shortTitle = layout.shortTitle || flowMeta.shortTitle || getHistorySectionLabel(section);
    const tone = layout.tone || flowMeta.tone || "neutral";
    const iconKey = layout.icon || flowMeta.icon || tone;
    const compact = Boolean(layout.compact || (flowMeta.compact && !layout.output));
    const titleText = [section.title || shortTitle, section.agent || section.team || "Agent"].filter(Boolean).join(" - ");
    return `
        <button class="history-diagram-node history-diagram-node--${tone} ${compact ? "history-diagram-node--compact" : ""} ${layout.output ? "history-diagram-node--output" : ""} ${isActive ? "is-active" : ""} ${loading ? "is-loading" : ""} ${isLoaded ? "is-loaded" : ""}"
            type="button"
            data-history-section-key="${escapeHtml(sectionKey)}"
            title="${escapeHtml(titleText)}"
            aria-label="Open ${escapeHtml(section.title || sectionKey)} markdown">
            <span class="history-diagram-node-head">
                <span class="history-diagram-node-icon" aria-hidden="true">${renderHistoryDiagramIcon(iconKey)}</span>
                <strong>${escapeHtml(shortTitle || section.title || sectionKey || "Section")}</strong>
                <span class="history-diagram-node-dot" aria-hidden="true"></span>
            </span>
        </button>
    `;
}

function renderHistoryDiagramSignalsGroup(signalNodes = [], options = {}) {
    return `
        <section class="history-diagram-group history-diagram-group--signals">
            <span class="history-diagram-label">Signals</span>
            <div class="history-diagram-signal-grid">
                ${signalNodes
                    .map(
                        (section) => `
                            <div class="history-diagram-signal-lane">
                                ${renderHistoryDiagramNode(section, options)}
                            </div>
                        `,
                    )
                    .join("")}
            </div>
        </section>
    `;
}

function renderHistoryDiagramResearchGroup(researchNodes = [], options = {}) {
    return `
        <section class="history-diagram-group history-diagram-group--research">
            <span class="history-diagram-label">Research</span>
            <div class="history-diagram-cluster history-diagram-cluster--research">
                <div class="history-diagram-cluster-grid history-diagram-cluster-grid--research">
                    ${researchNodes.map((section) => renderHistoryDiagramNode(section, options, { compact: HISTORY_FLOW_SECTION_META[section.section_key]?.compact })).join("")}
                </div>
            </div>
        </section>
    `;
}

function renderHistoryDiagramClusterGroup(label, key, nodes, options = {}) {
    return `
        <section class="history-diagram-group history-diagram-group--${key}">
            <span class="history-diagram-label">${escapeHtml(label)}</span>
            <div class="history-diagram-cluster history-diagram-cluster--${key}">
                <div class="history-diagram-cluster-grid history-diagram-cluster-grid--${key}">
                    ${nodes.map((section) => renderHistoryDiagramNode(section, options, { compact: HISTORY_FLOW_SECTION_META[section.section_key]?.compact })).join("")}
                </div>
            </div>
        </section>
    `;
}

function renderHistoryDiagramSingleGroup(label, key, node, options = {}) {
    return `
        <section class="history-diagram-group history-diagram-group--${key}">
            <span class="history-diagram-label">${escapeHtml(label)}</span>
            <div class="history-diagram-single">
                ${renderHistoryDiagramNode(node, options, { output: true })}
            </div>
        </section>
    `;
}

function renderHistoryDiagramSourceColumn(label, key, nodes = [], options = {}) {
    if (!nodes.length) {
        return "";
    }
    return `
        <div class="history-diagram-source-column history-diagram-source-column--${escapeHtml(key)}">
            <span class="history-diagram-source-label">${escapeHtml(label)}</span>
            <div class="history-diagram-source-list">
                ${nodes.map((section) => renderHistoryDiagramNode(section, options, { compact: true, shortTitle: section.title || label, tone: HISTORY_FLOW_SECTION_META[section.section_key]?.tone || "evidence" })).join("")}
            </div>
        </div>
    `;
}

function renderHistoryDiagramSourcesGroup(diagram = {}, options = {}) {
    const groups = [
        ["CCXT market data", "ccxt", diagram.sourceGroups?.ccxt || []],
        ["CoinGlass data", "coinglass", diagram.sourceGroups?.coinglass || []],
        ["News data", "news", diagram.sourceGroups?.news || []],
        ["Social / web data", "social", diagram.sourceGroups?.social || []],
        ["On-chain data", "flow", diagram.sourceGroups?.flow || []],
        ["Endpoint summaries", "endpoint", diagram.endpointSummaries ? [diagram.endpointSummaries] : []],
    ].filter(([_label, _key, nodes]) => nodes.length);
    if (!groups.length) {
        return "";
    }
    return `
        <section class="history-diagram-group history-diagram-group--sources">
            <span class="history-diagram-label">Parallel endpoint summaries</span>
            <div class="history-diagram-source-grid">
                ${groups.map(([label, key, nodes]) => renderHistoryDiagramSourceColumn(label, key, nodes, options)).join("")}
            </div>
        </section>
    `;
}

function renderHistoryVerticalConnector() {
    return '<span class="history-diagram-vertical-connector" aria-hidden="true"></span>';
}

function renderHistoryStageConnector(fromStage = null, toStage = null) {
    if (!fromStage || !toStage) {
        return "";
    }
    if (fromStage.key === "signals") {
        return renderHistoryCurveWire(
            HISTORY_SIGNAL_WIRE_PATHS.slice(0, Math.max(1, fromStage.wireCount || 0)),
            "history-diagram-stage-link history-diagram-stage-link--signals",
            "0 0 100 276",
        );
    }
    if (toStage.key === "risk") {
        return renderHistoryCurveWire(
            [HISTORY_RISK_WIRE_PATH],
            "history-diagram-stage-link history-diagram-stage-link--risk",
            "0 0 100 280",
        );
    }
    return renderHistoryCurveWire(
        [HISTORY_STAGE_WIRE_PATH],
        `history-diagram-stage-link history-diagram-stage-link--${fromStage.key}-to-${toStage.key}`,
        "0 0 100 100",
    );
}

function renderHistoryDiagramExtras(sections = [], options = {}) {
    if (!sections.length) {
        return "";
    }
    return `
        <section class="history-diagram-extra">
            <span class="history-diagram-label">Additional</span>
            <div class="history-diagram-extra-grid">
                ${sections.map((section) => renderHistoryDiagramNode(section, options, { compact: true })).join("")}
            </div>
        </section>
    `;
}

function openHistorySectionDetail(sectionKey = "") {
    const section = getHistorySectionMeta(sectionKey);
    if (!section) {
        return;
    }
    openDetailModal({
        type: "history-section",
        sectionKey,
        title: section.title || HISTORY_FLOW_SECTION_META[sectionKey]?.shortTitle || "Saved Markdown",
        subtitle: [section.team, section.agent].filter(Boolean).join(" - ") || "History archive",
        mode: "markdown",
    });
}

function triggerHistoryListReload(message = "Could not load history.") {
    loadHistoryList(true).catch((error) => {
        state.history.error = error instanceof Error ? error.message : String(error || message);
        renderHistoryPage();
    });
}

function setHistoryPage(nextPage) {
    const safePage = Math.max(1, Number(nextPage || 1));
    if (safePage === state.history.page && state.history.loaded && !state.history.error) {
        return;
    }
    state.history.page = safePage;
    triggerHistoryListReload("Could not change history page.");
}

let historyTableLayoutFrame = 0;

function resetHistoryTableLayoutMetrics() {
    if (!(elements.historyList instanceof HTMLElement)) {
        return;
    }
    elements.historyList.style.removeProperty("--history-table-head-height");
    elements.historyList.style.removeProperty("--history-table-row-height");
}

function applyHistoryTableLayoutMetrics() {
    if (!(elements.historyList instanceof HTMLElement)) {
        return;
    }
    if (elements.historyList.offsetParent === null || elements.historyList.clientHeight <= 0) {
        return;
    }
    const shell = elements.historyList.querySelector(".history-table-shell");
    const wrap = elements.historyList.querySelector(".history-table-wrap");
    const toolbar = elements.historyList.querySelector(".history-table-toolbar");
    const footer = elements.historyList.querySelector(".history-table-footer");
    const table = elements.historyList.querySelector(".history-table");
    const headRow = table?.querySelector("thead tr");
    if (!(shell instanceof HTMLElement) || !(wrap instanceof HTMLElement) || !(toolbar instanceof HTMLElement) || !(footer instanceof HTMLElement) || !(table instanceof HTMLElement) || !(headRow instanceof HTMLTableRowElement)) {
        resetHistoryTableLayoutMetrics();
        return;
    }

    const shellStyles = window.getComputedStyle(shell);
    const shellGap = Number.parseFloat(shellStyles.rowGap || shellStyles.gap || "0") || 0;
    const listHeight = elements.historyList.clientHeight;
    const occupiedHeight = toolbar.offsetHeight + footer.offsetHeight + (shellGap * 2);
    const wrapHeight = Math.max(0, listHeight - occupiedHeight);
    const headerHeight = Math.max(1, headRow.getBoundingClientRect().height || 0);
    const rowHeight = Math.max(1, (wrapHeight - headerHeight) / HISTORY_PAGE_SIZE);

    elements.historyList.style.setProperty("--history-table-head-height", `${headerHeight}px`);
    elements.historyList.style.setProperty("--history-table-row-height", `${rowHeight}px`);
}

function scheduleHistoryTableLayoutMetrics() {
    if (historyTableLayoutFrame) {
        window.cancelAnimationFrame(historyTableLayoutFrame);
    }
    historyTableLayoutFrame = window.requestAnimationFrame(() => {
        historyTableLayoutFrame = 0;
        applyHistoryTableLayoutMetrics();
    });
}

function waitForNextPaint() {
    return new Promise((resolve) => {
        window.requestAnimationFrame(() => {
            window.requestAnimationFrame(resolve);
        });
    });
}

function renderHistoryPage() {
    if (!(elements.historyList instanceof HTMLElement) || !(elements.historyDetail instanceof HTMLElement)) {
        return;
    }
    const history = state.history;
    if (elements.historyPage instanceof HTMLElement) {
        elements.historyPage.dataset.historyLayout = "table";
    }
    setElementLoadingState(elements.historyList, history.loading, "Loading history");
    setElementLoadingState(elements.historyDetail, history.detailLoading, "Loading detail");
    if (!canReadHistory()) {
        const accessMessage = state.auth.isAuthorized
            ? "History access is disabled for this account."
            : "Sign in with Google to view saved analyses.";
        elements.historyStatusText.textContent = state.auth.isAuthorized ? "History locked" : "Sign in required";
        elements.historyList.innerHTML = `<div class="history-empty">${escapeHtml(accessMessage)}</div>`;
        resetHistoryTableLayoutMetrics();
        elements.historyDetailTitle.textContent = "Analysis Detail";
        elements.historyDetail.innerHTML = `<div class="history-empty">${escapeHtml(accessMessage)}</div>`;
        return;
    }
    if (history.loading) {
        elements.historyStatusText.textContent = "Loading history";
        elements.historyList.innerHTML = '<div class="history-empty">Loading saved analyses...</div>';
        resetHistoryTableLayoutMetrics();
    } else if (history.error) {
        elements.historyStatusText.textContent = "History issue";
        elements.historyList.innerHTML = `<div class="history-empty">${escapeHtml(history.error)}</div>`;
        resetHistoryTableLayoutMetrics();
    } else if (!history.items.length) {
        elements.historyStatusText.textContent = history.loaded ? "No saved analyses" : "Waiting";
        elements.historyList.innerHTML = '<div class="history-empty">No saved analyses yet.</div>';
        resetHistoryTableLayoutMetrics();
    } else {
        const totalCount = Math.max(0, Number(history.totalCount || history.items.length || 0));
        const totalPages = Math.max(1, Number(history.totalPages || 1));
        const currentPage = Math.min(Math.max(1, Number(history.page || 1)), totalPages);
        const currentLimit = Math.max(1, Number(history.limit || HISTORY_PAGE_SIZE));
        const startIndex = totalCount ? (currentPage - 1) * currentLimit + 1 : 0;
        const endIndex = totalCount ? Math.min(startIndex + history.items.length - 1, totalCount) : 0;
        const paginationItems = buildHistoryPaginationItems(totalPages, currentPage)
            .map((item) => {
                if (item.type === "ellipsis") {
                    return '<span class="history-page-ellipsis" aria-hidden="true">...</span>';
                }
                return `
                    <button class="history-page-chip ${item.page === currentPage ? "is-active" : ""}"
                        type="button"
                        data-history-page-target="${item.page}"
                        aria-label="Go to page ${item.page}"
                        ${item.page === currentPage ? 'aria-current="page"' : ""}>
                        ${item.page}
                    </button>
                `;
            })
            .join("");
        elements.historyList.innerHTML = `
            <div class="history-table-shell">
                <div class="history-table-toolbar">
                    <div class="history-table-stats">
                        <strong>${escapeHtml(String(totalCount))} archived runs</strong>
                        <span>${totalCount ? `Showing ${escapeHtml(String(startIndex))}-${escapeHtml(String(endIndex))}` : "No records"}</span>
                    </div>
                    <span class="history-table-hint">Select a row to open the final decision markdown and structured trade levels.</span>
                </div>
                <div class="history-table-wrap">
                    <table class="history-table">
                        <thead>
                            <tr>
                                <th scope="col">#</th>
                                <th scope="col">Symbol</th>
                                <th scope="col">Signal</th>
                                <th scope="col">Current price</th>
                                <th scope="col">Primary limit</th>
                                <th scope="col">Secondary limit</th>
                                <th scope="col">Stop loss</th>
                                <th scope="col">Take profit</th>
                                <th scope="col">Created at</th>
                                <th scope="col">Research depth</th>
                                <th scope="col">Lookback day</th>
                                <th scope="col">Elapsed time</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${history.items
                                .map(
                                    (item, index) => `
                                        <tr class="history-table-row ${item.id === history.activeId ? "is-active" : ""}" role="button" tabindex="0" data-history-row-id="${escapeHtml(item.id)}" aria-label="Open saved analysis for ${escapeHtml(item.symbol || "analysis")}">
                                            <td>${escapeHtml(String(startIndex + index))}</td>
                                            <td>${escapeHtml(item.symbol || "-")}</td>
                                            <td>${escapeHtml(item.signal || "Completed")}</td>
                                            <td>${escapeHtml(formatHistoryPrice(item.current_price))}</td>
                                            <td>${escapeHtml(formatHistoryPrice(item.primary_limit_price))}</td>
                                            <td>${escapeHtml(formatHistoryPrice(item.secondary_limit_price))}</td>
                                            <td>${escapeHtml(formatHistoryPrice(item.stop_loss))}</td>
                                            <td>${escapeHtml(formatHistoryPrice(item.take_profit))}</td>
                                            <td>${escapeHtml(formatHistoryDateTime(item.created_at))}</td>
                                            <td>${escapeHtml(item.research_depth || "-")}</td>
                                            <td>${escapeHtml(String(item.lookback_days || "-"))}</td>
                                            <td>${escapeHtml(formatHistoryElapsedSeconds(item.elapsed_seconds))}</td>
                                        </tr>
                                    `,
                                )
                                .join("")}
                        </tbody>
                    </table>
                </div>
                <div class="history-table-footer">
                    <div class="history-table-footer-meta">
                        <span class="history-table-footer-copy">Page ${escapeHtml(String(currentPage))} of ${escapeHtml(String(totalPages))}</span>
                    </div>
                    <nav class="history-page-nav" aria-label="History pages">
                        <button class="history-page-button history-page-button--icon" type="button" data-history-page-target="1" aria-label="Go to first page" ${currentPage <= 1 ? "disabled" : ""}>&laquo;</button>
                        <button class="history-page-button history-page-button--icon" type="button" data-history-page-nav="prev" aria-label="Go to previous page" ${currentPage <= 1 ? "disabled" : ""}>&lsaquo;</button>
                        <div class="history-page-track">
                            ${paginationItems}
                        </div>
                        <button class="history-page-button history-page-button--icon" type="button" data-history-page-nav="next" aria-label="Go to next page" ${currentPage >= totalPages ? "disabled" : ""}>&rsaquo;</button>
                        <button class="history-page-button history-page-button--icon" type="button" data-history-page-target="${totalPages}" aria-label="Go to last page" ${currentPage >= totalPages ? "disabled" : ""}>&raquo;</button>
                    </nav>
                </div>
            </div>
        `;
        scheduleHistoryTableLayoutMetrics();
    }

    elements.historyStatusText.textContent = history.loaded ? "Select a row" : "Waiting";
    elements.historyDetailTitle.textContent = "Final Decision";
    elements.historyDetail.innerHTML = '<div class="history-empty">Select a saved analysis row to open the final decision.</div>';
}

async function loadHistoryList(force = false) {
    if (state.history.loading || (state.history.loaded && !force)) {
        renderHistoryPage();
        return;
    }
    if (!state.auth.idToken && !state.auth.isAuthorized) {
        openAuthRequiredAlert();
        renderHistoryPage();
        return;
    }
    if (!canReadHistory()) {
        await ensureAuthorizedSession();
        if (!canReadHistory()) {
            renderHistoryPage();
            return;
        }
    }
    state.history.loading = true;
    state.history.error = "";
    renderHistoryPage();
    try {
        const response = await apiFetch(`/api/history?page=${state.history.page}&limit=${state.history.limit}`, {
            headers: getAuthHeaders(),
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }
        const payload = await response.json();
        state.history.items = (payload.items || []).map((item) => {
            const entry = cacheHistoryItem(item);
            return entry
                ? {
                    ...entry.item,
                }
                : item;
        });
        state.history.page = Number(payload.page || 1);
        state.history.limit = Number(payload.limit || HISTORY_PAGE_SIZE);
        state.history.hasMore = Boolean(payload.has_more);
        state.history.totalCount = Math.max(0, Number(payload.total_count || 0));
        state.history.totalPages = Math.max(1, Number(payload.total_pages || 1));
        state.history.loaded = true;
        state.history.active = state.history.activeId ? getHistoryArchiveEntry(state.history.activeId) : null;
    } catch (error) {
        state.history.error = error instanceof Error ? error.message : String(error || "Could not load history.");
    } finally {
        state.history.loading = false;
        renderHistoryPage();
    }
}

async function loadHistoryDetail(historyId) {
    if (!historyId) {
        return;
    }
    if (!state.auth.idToken && !state.auth.isAuthorized) {
        openAuthRequiredAlert();
        renderHistoryPage();
        return;
    }
    if (!canReadHistory()) {
        await ensureAuthorizedSession();
        if (!canReadHistory()) {
            renderHistoryPage();
            return;
        }
    }
    state.history.activeId = historyId;
    state.history.error = "";
    const cachedItem = state.history.items.find((item) => item.id === historyId) || getHistoryArchiveEntry(historyId)?.item || { id: historyId };
    const cachedEntry = cacheHistoryItem(cachedItem);
    state.history.active = cachedEntry;
    state.history.detailLoading = true;
    renderHistoryPage();
    try {
        const response = await apiFetch(`/api/history/${encodeURIComponent(historyId)}/final-decision`, {
            headers: getAuthHeaders(),
            cache: "no-store",
        });
        if (!response.ok) {
            throw new Error(await readResponseError(response));
        }
        const payload = await response.json();
        const item = payload.item || cachedItem || { id: historyId };
        state.history.active = cacheHistoryItem(item);
        state.history.error = "";
        openDetailModal({
            type: "history-final-decision",
            title: `Final Decision - ${item.symbol || "Analysis"}`,
            subtitle: [item.analysis_date, item.signal].filter(Boolean).join(" - ") || "History",
            content: payload.section?.markdown || "",
            mode: "markdown",
        });
        state.history.error = "";
    } catch (error) {
        state.history.error = error instanceof Error ? error.message : String(error || "Could not load history detail.");
    } finally {
        state.history.detailLoading = false;
        renderHistoryPage();
    }
}

async function loadHistorySection(historyId, sectionKey, options = {}) {
    const { openModal = false } = options;
    const entry = syncHistoryActiveEntry(historyId);
    if (!historyId || !sectionKey || !entry || state.history.activeId !== historyId) {
        return;
    }
    if (!canReadHistory()) {
        renderHistoryPage();
        return;
    }
    entry.activeSectionKey = sectionKey;
    state.history.active = entry;
    if (Object.prototype.hasOwnProperty.call(entry.sectionMarkdown || {}, sectionKey)) {
        renderHistoryPage();
        if (openModal) {
            openHistorySectionDetail(sectionKey);
        }
        return;
    }
    addHistoryLoadingKey(entry, sectionKey);
    renderHistoryPage();
    await waitForNextPaint();
    if (state.history.activeId !== historyId) {
        return;
    }
    try {
        await ensureHistorySectionMarkdown(historyId, sectionKey);
    } catch (error) {
        state.history.error = error instanceof Error ? error.message : String(error || "Could not load history section.");
        renderHistoryPage();
        return;
    }
    renderHistoryPage();
    if (openModal && state.history.active && state.history.activeId === historyId) {
        openHistorySectionDetail(sectionKey);
    }
}
