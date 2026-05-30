function getCheckedAnalysts() {
    return Array.from(elements.analystOptions.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
}

function getSelectedDepth() {
    const checked = elements.depthOptions.querySelector('input[name="researchDepth"]:checked');
    return checked ? checked.value : state.config?.analysis_defaults?.research_depth || "auto";
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
    elements.customLanguageField?.classList.toggle("field-muted", !isCustom);
    elements.customLanguageInput.disabled = !isCustom;
    elements.customLanguageInput.required = isCustom;
}

function syncLookbackPreset() {
    if (!state.config) {
        return;
    }
    if (elements.lookbackPresetSelect.value === CUSTOM_LOOKBACK_VALUE) {
        syncLookbackControls();
        return;
    }
    const presets = state.config.analysis_options.lookback_presets || [];
    const days = Number(elements.lookbackDaysInput.value || 0);
    const matched = presets.find((preset) => preset.days === days);
    elements.lookbackPresetSelect.value = matched ? matched.value : CUSTOM_LOOKBACK_VALUE;
    syncLookbackControls();
}

function syncLookbackControls() {
    const isCustom = elements.lookbackPresetSelect.value === CUSTOM_LOOKBACK_VALUE;
    elements.lookbackDaysField?.classList.toggle("field-muted", !isCustom);
    elements.lookbackDaysInput.disabled = !isCustom;
    elements.lookbackDaysInput.required = isCustom;
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

function refreshConfigUi() {
    syncLanguageControls();
    syncLookbackPreset();
    syncAnalystAvailability();
    renderConfigPreview();
    renderTopNotice();
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
    setElementLoadingState(elements.teamStatusGrid, state.isBusy && !state.run.status, "Syncing teams");

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
    const phaseLabel = state.run.cancelled
        ? "cancelled"
        : state.isBusy
        ? state.run.status?.phase || "running"
        : state.run.complete
        ? "completed"
        : "ready";
    elements.phaseText.textContent = phaseLabel;
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

function getAnalysisDepthLabel(source = {}) {
    const requested = String(source.research_depth || "auto").trim() || "auto";
    const effective = String(source.effective_research_depth || source.effective_depth || "").trim();
    if (effective && effective !== requested) {
        return `${requested} / ${effective}`;
    }
    return requested;
}

function getConfigAnalystLabel(value) {
    const analyst = state.config?.analysis_options?.analysts?.find((item) => item.value === value);
    return analyst?.label || value;
}

function renderConfigPreview() {
    if (!(elements.configPreview instanceof HTMLElement)) {
        return;
    }

    const payload = getConfigSnapshot();
    if (!payload) {
        elements.configPreview.innerHTML = '<div class="config-preview-empty">Loading config.</div>';
        return;
    }

    const depthOption = state.config?.analysis_options?.research_depths?.find((item) => item.value === payload.research_depth);
    const effectiveDepth = depthOption?.effective_depth && depthOption.effective_depth !== payload.research_depth
        ? ` / ${depthOption.effective_depth}`
        : "";
    const analysts = (payload.selected_analysts || []).map(getConfigAnalystLabel);
    const lookbackLabel = payload.lookback_days ? `${payload.lookback_days}d` : "-";

    elements.configPreview.innerHTML = `
        <div class="config-preview-header">
            <span>Run Snapshot</span>
            <strong>${escapeHtml(payload.symbol || "-")}</strong>
        </div>
        <div class="config-summary-grid">
            <div class="config-summary-chip">
                <span>Lookback</span>
                <strong>${escapeHtml(lookbackLabel)}</strong>
            </div>
            <div class="config-summary-chip">
                <span>Depth</span>
                <strong>${escapeHtml(`${payload.research_depth || "auto"}${effectiveDepth}`)}</strong>
            </div>
            <div class="config-summary-chip">
                <span>Model</span>
                <strong>${escapeHtml(payload.model || "-")}</strong>
            </div>
            <div class="config-summary-chip">
                <span>Language</span>
                <strong>${escapeHtml(payload.output_language || "-")}</strong>
            </div>
        </div>
        <div class="config-summary-note">
            <span>Analysts</span>
            <strong>${escapeHtml(analysts.join(", ") || "-")}</strong>
        </div>
    `;
}

function getFlowSectionOrder() {
    return [
        ...(HISTORY_FLOW_SECTION_ORDER.inputs || []),
        ...(HISTORY_FLOW_SECTION_ORDER.research || []),
        ...(HISTORY_FLOW_SECTION_ORDER.trading || []),
        ...(HISTORY_FLOW_SECTION_ORDER.risk || []),
        ...(HISTORY_FLOW_SECTION_ORDER.portfolio || []),
    ];
}

function getFlowSectionTitle(sectionKey) {
    return HISTORY_FLOW_SECTION_META[sectionKey]?.shortTitle
        || sectionKey.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderFlowMetric(label, value, tone = "") {
    const normalizedValue = value === 0 ? "0" : value || "-";
    return `
        <div class="flow-metric ${tone ? `flow-metric-${escapeHtml(tone)}` : ""}">
            <span>${escapeHtml(label)}</span>
            <strong>${escapeHtml(String(normalizedValue))}</strong>
        </div>
    `;
}

function renderFlowSectionList() {
    return getFlowSectionOrder()
        .map((sectionKey) => {
            const hasContent = Boolean(String(state.run.sections?.[sectionKey] || "").trim());
            const title = getFlowSectionTitle(sectionKey);
            const baseClass = `flow-section-item ${hasContent ? "is-ready detail-trigger" : "is-pending"}`;
            const dataset = hasContent
                ? `data-detail-section="${escapeHtml(sectionKey)}" data-detail-title="${escapeHtml(title)}" data-detail-subtitle="Agent report"`
                : "";
            const tag = hasContent ? "button" : "span";
            const typeAttr = hasContent ? ' type="button"' : "";
            return `
                <${tag}${typeAttr} class="${baseClass}" ${dataset}>
                    <span class="flow-section-dot" aria-hidden="true"></span>
                    <span>${escapeHtml(title)}</span>
                </${tag}>
            `;
        })
        .join("");
}

function renderFlowInspectorMarkup() {
    const meta = state.run.meta || getConfigSnapshot() || {};
    const progress = state.run.status?.progress || { completed: 0, total: 0, percent: 0 };
    const complete = state.run.complete || {};
    const telemetry = complete.telemetry || {};
    const completedSections = getFlowSectionOrder().filter((key) => String(state.run.sections?.[key] || "").trim()).length;
    const totalSections = getFlowSectionOrder().length;
    const progressText = progress.total ? `${progress.completed}/${progress.total}` : state.run.complete ? "Done" : "-";
    const signal = complete.signal || (state.run.cancelled ? "Stopped" : state.isBusy ? "Running" : "Pending");
    const verdict = complete.verification_verdict || "-";
    const warningItems = state.run.warnings.slice(0, 2);
    const latestTool = [...state.run.traceFeed].reverse().find((item) => isToolTracePhase(item.phase));

    return `
        <div class="flow-inspector-header">
            <span>Flow Snapshot</span>
            <strong>${escapeHtml(signal)}</strong>
        </div>
        <div class="flow-metric-grid">
            ${renderFlowMetric("Progress", progressText, state.isBusy ? "live" : "")}
            ${renderFlowMetric("Reports", `${completedSections}/${totalSections}`)}
            ${renderFlowMetric("Depth", getAnalysisDepthLabel(meta))}
            ${renderFlowMetric("Verdict", verdict, verdict === "Revise" || verdict === "Caution" ? "warning" : "")}
            ${renderFlowMetric("Evidence", complete.evidence_count ?? "-")}
            ${renderFlowMetric("Web Search", telemetry.web_search_calls ?? "-")}
            ${renderFlowMetric("Model Calls", telemetry.model_calls ?? "-")}
            ${renderFlowMetric("Tool Events", telemetry.tool_calls ?? "-")}
        </div>
        <div class="flow-latest">
            <span>Current</span>
            <strong>${escapeHtml(state.run.status?.current_agent || state.run.latestReportTitle || latestTool?.title || "-")}</strong>
        </div>
        <div class="flow-section-list" aria-label="Completed report sections">
            ${renderFlowSectionList()}
        </div>
        ${
            warningItems.length
                ? `<div class="flow-warning-list">${warningItems.map((warning) => `<span>${escapeHtml(compactText(warning, 96))}</span>`).join("")}</div>`
                : ""
        }
    `;
}

function clearDetailAttributes(element) {
    ["data-detail-key", "data-detail-section", "data-detail-title", "data-detail-subtitle"].forEach((attribute) => {
        element.removeAttribute(attribute);
    });
}

function applyDetailAttributes(element, detail) {
    clearDetailAttributes(element);
    if (!detail) {
        return;
    }
    if (detail.type === "report") {
        element.dataset.detailSection = detail.section || "";
        element.dataset.detailTitle = detail.title || "Report Detail";
        element.dataset.detailSubtitle = detail.subtitle || detail.title || "Agent report";
        return;
    }
    if (detail.key) {
        element.dataset.detailKey = detail.key;
    }
}

function renderReportGrid() {
    const focus = getCurrentLivePanel();
    const focusId = getFocusIdentity(focus);
    const hasInspector = Boolean(elements.reportGrid.querySelector(".flow-inspector"));
    let card = elements.reportGrid.querySelector(".live-focus-card");
    if (!(card instanceof HTMLElement) || !hasInspector || card.dataset.focusId !== focusId) {
        elements.reportGrid.innerHTML = `
            <div class="live-layout live-layout-with-inspector">
                <article class="live-focus-card live-focus-card-expanded">
                    <div class="live-focus-topline">
                        <span class="live-chip"></span>
                        <div class="live-focus-actions">
                            <span class="live-focus-status"></span>
                            <button class="live-detail-button detail-trigger hidden" type="button">Open</button>
                        </div>
                    </div>
                    <h3 class="live-focus-title"></h3>
                    <div class="live-focus-body markdown-preview"></div>
                </article>
                <aside class="flow-inspector" aria-label="Flow snapshot"></aside>
            </div>
        `;
        card = elements.reportGrid.querySelector(".live-focus-card");
    }

    if (!(card instanceof HTMLElement)) {
        return;
    }

    const liveChip = card.querySelector(".live-chip");
    const liveStatus = card.querySelector(".live-focus-status");
    const detailButton = card.querySelector(".live-detail-button");
    const liveTitle = card.querySelector(".live-focus-title");
    const liveBody = card.querySelector(".live-focus-body");
    const inspector = elements.reportGrid.querySelector(".flow-inspector");
    const tone = focus.tone || "idle";
    const bodyMarkup = formatBlock(focus.content, focus.fallback);
    const bodyFingerprint = `${focusId}:${focus.content || ""}:${focus.fallback}`;

    card.dataset.focusId = focusId;
    card.className = `live-focus-card live-focus-card-expanded live-tone-${tone}`;
    const isAwaitingFocus = state.isBusy && !String(focus.content || "").trim();
    setElementLoadingState(card, isAwaitingFocus, state.run.status?.current_agent ? `Waiting ${getCompactAgentLabel(state.run.status.current_agent)}` : "Streaming");
    card.removeAttribute("tabindex");
    card.removeAttribute("role");
    card.setAttribute("aria-label", focus.title);
    clearDetailAttributes(card);

    if (liveChip instanceof HTMLElement) {
        liveChip.className = `live-chip live-chip-${tone}`;
        liveChip.textContent = focus.badge || "Live";
    }
    if (liveStatus instanceof HTMLElement) {
        liveStatus.textContent = focus.subtitle || "";
    }
    if (detailButton instanceof HTMLElement) {
        detailButton.classList.toggle("hidden", !focus.detail);
        detailButton.removeAttribute("aria-label");
        applyDetailAttributes(detailButton, focus.detail);
        if (focus.detail) {
            detailButton.setAttribute("aria-label", `Open ${focus.title} detail`);
        }
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
    if (inspector instanceof HTMLElement) {
        inspector.innerHTML = renderFlowInspectorMarkup();
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
    const shouldStickToBottom = shouldAutoScrollLog(element);
    const existingNodes = new Map(
        Array.from(element.querySelectorAll(".event-log-item[data-log-key]"))
            .filter((child) => child instanceof HTMLElement)
            .map((child) => [String(child.dataset.logKey || ""), child]),
    );

    if (!entries.length) {
        const currentEmpty = element.querySelector(".event-log-empty");
        if (!(currentEmpty instanceof HTMLElement) || currentEmpty.textContent !== emptyText || element.children.length !== 1) {
            element.replaceChildren(createLogEmptyNode(emptyText));
        }
        return;
    }

    const newKeys = new Set();
    const desiredNodes = [];
    const desiredKeys = new Set();
    entries.forEach((item, index) => {
        const key = getLogEntryKey(item, index);
        desiredKeys.add(key);
        let node = existingNodes.get(key);
        if (!(node instanceof HTMLElement)) {
            node = createLogEntryNode();
            newKeys.add(key);
        }
        updateLogEntryNode(node, item, key, useDetail);
        desiredNodes.push(node);
    });

    const viewportSnapshot = shouldStickToBottom ? null : getLogScrollSnapshot(element, desiredKeys);

    Array.from(element.children).forEach((child) => {
        if (!(child instanceof HTMLElement)) {
            return;
        }
        const key = String(child.dataset.logKey || "");
        if (child.classList.contains("event-log-item") && !desiredKeys.has(key)) {
            child.remove();
        }
    });

    const firstMissingIndex = desiredNodes.findIndex((node) => node.parentElement !== element);
    if (firstMissingIndex >= 0) {
        for (let index = firstMissingIndex; index < desiredNodes.length; index += 1) {
            element.appendChild(desiredNodes[index]);
        }
    }

    desiredNodes.forEach((node) => {
        node.classList.toggle("event-log-item-new", shouldStickToBottom && newKeys.has(node.dataset.logKey || ""));
    });

    if (shouldStickToBottom) {
        requestAnimationFrame(() => {
            if (!shouldAutoScrollLog(element)) {
                return;
            }
            element.scrollTop = element.scrollHeight;
        });
        return;
    }

    if (viewportSnapshot) {
        const anchorNode = desiredNodes.find((node) => String(node.dataset.logKey || "") === viewportSnapshot.anchorKey) || null;
        if (anchorNode instanceof HTMLElement) {
            element.scrollTop = Math.max(0, anchorNode.offsetTop + viewportSnapshot.anchorOffset);
            return;
        }
        element.scrollTop = Math.max(0, viewportSnapshot.scrollTop - viewportSnapshot.removedAboveViewportHeight);
    }
}

function renderOperationsRail() {
    const toolFeed = state.run.traceFeed.filter((item) => isToolTracePhase(item.phase));
    const visibleToolLimit = Math.max(
        TRACE_DISPLAY_LIMIT,
        Math.min(TRACE_FEED_LIMIT, toolFeed.length),
    );
    const feed = toolFeed.slice(-visibleToolLimit);
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
    elements.executionLogStatusText.textContent = state.run.logEntries.length
        ? `${Math.min(state.run.logEntries.length, EXECUTION_LOG_DISPLAY_LIMIT)} backend lines`
        : "Waiting for stream";

    renderLogEntries(
        elements.executionLog,
        state.run.logEntries.slice(-EXECUTION_LOG_DISPLAY_LIMIT),
        "Backend log lines will appear here while analysis is running.",
        { useDetail: true },
    );

    setElementLoadingState(elements.toolTraceList, state.isBusy && !feed.length, "Waiting traces");
    setElementLoadingState(elements.executionLog, state.isBusy && !state.run.logEntries.length, "Waiting backend");

    const flashLatestTrace = state.run.flashLatestTrace;
    preserveScrollPosition(elements.toolTraceList, () => {
        elements.toolTraceList.innerHTML = feed.length
            ? feed
                  .map((item) => {
                      const shouldFlash = flashLatestTrace && item.id === state.run.latestTraceId;
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
                        <p>${escapeHtml(compactText(stripMarkdownToPlainText(item.previewContent || item.content || ""), 320))}</p>
                    </article>
                                `;
                                    })
                                    .join("")
                        : '<div class="tool-trace-empty">Agent tool calls and reasoning traces will appear here when the backend stream starts.</div>';
        });
    state.run.flashLatestTrace = false;
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
    const combinedDecision = buildFinalDecisionMarkdown();
    const fallback = state.run.sections.verification_report
        ? "Verification completed. Open the panel for the full report."
        : "The Portfolio Manager has not finalized a decision yet.";
    setCompactPreview(elements.portfolioDecisionPanel, combinedDecision, fallback, 220);
    const signal = state.run.complete?.signal || "No signal";
    const verificationVerdict = getVerificationVerdictText();
    elements.signalBadge.textContent = verificationVerdict ? `${signal} / ${verificationVerdict}` : signal;
}

function renderSmartNotes() {
    const notes = [];
    if (state.run.meta) {
        notes.push(`Market mode: ${state.run.meta.asset_type}`);
        notes.push(`Lookback window: ${state.run.meta.lookback_days} day(s)`);
        notes.push(`Depth preset: ${getAnalysisDepthLabel(state.run.meta)} (${state.run.meta.depth_rounds} rounds)`);
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
        const hasToolPayload = Boolean(entry?.toolCallContent || entry?.toolResultContent);
        return {
            content: formatTraceDetailMarkdown(entry),
            fallback: "This trace is no longer available in the live feed.",
            toolResult: hasToolPayload
                ? entry?.toolResultData || { answer: "", sections: [], relatedSearches: [] }
                : null,
            traceEntry: entry || null,
        };
    }

    if (detail?.type === "history-section") {
        const section = getHistorySectionMeta(detail.sectionKey);
        const active = state.history.active || {};
        const content = active.sectionMarkdown?.[detail.sectionKey] || "";
        const loading = Array.isArray(active.sectionLoadingKeys) && active.sectionLoadingKeys.includes(detail.sectionKey);
        return {
            content,
            fallback: loading
                ? "Loading this saved markdown section..."
                : section
                ? "No markdown was saved for this section."
                : "This saved history section is no longer available.",
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
        case "verifierReport":
            return {
                content: state.run.sections.verification_report || "",
                fallback: "The Verifier has not completed the post-decision audit yet.",
            };
        case "portfolioDecision":
            return {
                content: buildFinalDecisionMarkdown(),
                fallback: "The Portfolio Manager has not finalized a decision yet.",
            };
        case "backendLog":
            return { content: formatBackendLogMarkdown(), fallback: "No backend log lines yet." };
        default:
            return { content: "", fallback: "No data yet." };
    }
}

function formatTraceDetailMarkdown(entry) {
    if (!entry) {
        return "";
    }

    if (entry.toolCallContent || entry.toolResultContent) {
        const toolResultBody = entry.toolResultData
            ? renderStructuredToolResultToMarkdown(entry.toolResultData)
            : formatRawToolResultMarkdown(entry.toolResultContent || "");
        return [
            `**Agent:** ${entry.agent || "Agent"}`,
            `**Phase:** ${formatTracePhaseLabel(entry.phase)}`,
            `**Time:** ${entry.timestamp || "-"}`,
            entry.toolCallContent ? `**Tool call**\n\n\`\`\`text\n${entry.toolCallContent}\n\`\`\`` : "",
            toolResultBody ? `**Tool result**\n\n${toolResultBody}` : "",
        ]
            .filter(Boolean)
            .join("\n\n");
    }

    const content = formatTraceContentForDisplay(entry.phase, entry.content || "");
    const looksStructured = entry.phase !== "tool_result" && (/^[\[{]/.test(content) || /^analysis\s/.test(content));
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

function renderToolResultCardMarkup(item) {
    const titleMarkup = item.link
        ? `<a class="tool-result-card-title" href="${escapeHtml(item.link)}" target="_blank" rel="noreferrer noopener">${escapeHtml(item.title)}</a>`
        : `<span class="tool-result-card-title">${escapeHtml(item.title)}</span>`;

    return `
        <article class="tool-result-card">
            <div class="tool-result-card-topline">
                ${titleMarkup}
                ${item.date ? `<span class="tool-result-card-date">${escapeHtml(item.date)}</span>` : ""}
            </div>
            ${item.snippet ? `<p class="tool-result-card-snippet">${escapeHtml(item.snippet)}</p>` : ""}
            <div class="tool-result-card-meta">
                <span>${escapeHtml(item.source || "Search result")}</span>
                ${item.link ? `<a class="tool-result-card-open" href="${escapeHtml(item.link)}" target="_blank" rel="noreferrer noopener">Open source</a>` : ""}
            </div>
        </article>
    `;
}

function renderToolResultDetailMarkup(toolResult, entry) {
    const toolCallContent = String(entry?.toolCallContent || "").trim();
    const rawResultContent = String(entry?.toolResultContent || entry?.content || "").trim();
    const rawResultMarkdown = formatRawToolResultMarkdown(rawResultContent);
    const hasStructuredContent = Boolean(toolResult.answer || toolResult.sections.length || toolResult.relatedSearches.length);
    const metaItems = [
        entry?.agent ? `Agent: ${entry.agent}` : "",
        entry?.title ? `Tool: ${entry.title}` : "",
        entry?.timestamp ? `Time: ${entry.timestamp}` : "",
    ].filter(Boolean);

    return `
        ${metaItems.length ? `<div class="tool-result-meta-strip">${metaItems.map((item) => `<span class="tool-result-meta-pill">${escapeHtml(item)}</span>`).join("")}</div>` : ""}
        ${toolCallContent
            ? `
                <section class="tool-result-section">
                    <div class="tool-result-section-head">
                        <h3>Tool call</h3>
                        <span>Input</span>
                    </div>
                    <div class="tool-result-summary markdown-preview">${renderMarkdown(`\`\`\`text\n${toolCallContent}\n\`\`\``, "")}</div>
                </section>
            `
            : ""}
        ${toolResult.answer ? `<section class="tool-result-summary markdown-preview">${renderMarkdown(toolResult.answer, "")}</section>` : ""}
        ${toolResult.sections
            .map(
                (section) => `
                    <section class="tool-result-section">
                        <div class="tool-result-section-head">
                            <h3>${escapeHtml(section.title)}</h3>
                            <span>${escapeHtml(String(section.items.length))} items</span>
                        </div>
                        <div class="tool-result-card-list">
                            ${section.items.map((item) => renderToolResultCardMarkup(item)).join("")}
                        </div>
                    </section>
                `,
            )
            .join("")}
        ${toolResult.relatedSearches.length
            ? `
                <section class="tool-result-section">
                    <div class="tool-result-section-head">
                        <h3>Related searches</h3>
                        <span>${escapeHtml(String(toolResult.relatedSearches.length))} items</span>
                    </div>
                    <div class="tool-result-related-list">
                        ${toolResult.relatedSearches.map((item) => `<span class="tool-result-chip">${escapeHtml(item)}</span>`).join("")}
                    </div>
                </section>
            `
            : ""}
        ${!hasStructuredContent && rawResultContent
            ? `
                <section class="tool-result-section">
                    <div class="tool-result-section-head">
                        <h3>Tool result</h3>
                        <span>Raw output</span>
                    </div>
                    <div class="tool-result-summary markdown-preview">${renderMarkdown(rawResultMarkdown, "")}</div>
                </section>
            `
            : ""}
    `;
}

function setToolResultPreview(element, toolResult, entry, fallback) {
    const hasStructuredContent = Boolean(toolResult && (toolResult.answer || toolResult.sections.length || toolResult.relatedSearches.length));
    const hasRawContent = Boolean(entry?.toolCallContent || entry?.toolResultContent || entry?.content);
    const hasContent = Boolean(hasStructuredContent || hasRawContent);
    element.innerHTML = hasContent
        ? renderToolResultDetailMarkup(toolResult || { answer: "", sections: [], relatedSearches: [] }, entry)
        : `<div class="tool-result-empty">${escapeHtml(fallback)}</div>`;
    element.classList.toggle("is-empty", !hasContent);
}

function formatBackendLogMarkdown(limit = EXECUTION_LOG_DISPLAY_LIMIT) {
    const entries = state.run.logEntries.slice(-limit);
    if (!entries.length) {
        return "";
    }

    return entries
        .map(
            (entry) => {
                const detail = entry.detail || entry.summary || "";
                return `### ${entry.label}\n- **Time:** ${entry.timestamp}\n\n\`\`\`text\n${detail}\n\`\`\``;
            },
        )
        .join("\n\n");
}

function renderActiveDetail() {
    const detail = state.activeDetail;
    if (!detail || elements.detailModal.classList.contains("hidden")) {
        return;
    }

    const meta = detail.type === "report" || detail.type === "trace" || detail.type === "history-section" ? detail : DETAIL_PANEL_META[detail.key] || {};
    const { content, fallback, toolResult, traceEntry } = getDetailContent(detail);
    const mode = toolResult ? "tool-result" : detail.mode || meta.mode || "markdown";
    elements.detailTitle.textContent = meta.title || "Panel Detail";
    elements.detailSubtitle.textContent = meta.subtitle || "Analysis detail";
    elements.detailBody.classList.toggle("plain-log", mode === "text");
    elements.detailBody.classList.toggle("markdown-preview", mode === "markdown");
    elements.detailBody.classList.toggle("tool-result-preview", mode === "tool-result");

    if (mode === "text") {
        elements.detailBody.textContent = content || fallback;
    } else if (mode === "tool-result") {
        setToolResultPreview(elements.detailBody, toolResult, traceEntry, fallback);
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

function renderPageShell() {
    const pagePanels = {
        agent: elements.agentPage,
        history: elements.historyPage,
        chart: elements.chartPage,
        admin: elements.adminPage,
        chat: elements.chatPage,
    };
    Object.entries(pagePanels).forEach(([page, panel]) => {
        if (panel instanceof HTMLElement) {
            panel.classList.toggle("hidden", page !== state.page);
        }
    });
    [elements.agentPageButton, elements.historyPageButton, elements.chartPageButton, elements.adminPageButton, elements.chatPageButton].forEach((button) => {
        if (!(button instanceof HTMLElement)) {
            return;
        }
        if (button.dataset.page === "admin" || button.dataset.page === "chat") {
            button.classList.toggle("hidden", !state.auth.isAdmin);
        }
        const isActive = button.dataset.page === state.page;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-current", isActive ? "page" : "false");
    });
}

