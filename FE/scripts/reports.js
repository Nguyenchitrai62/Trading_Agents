function getToolTraceStateLabel(item = {}) {
    if (item.phase === "tool_trace") {
        return "Result ready";
    }
    if (item.phase === "tool_call") {
        return "Calling";
    }
    if (item.phase === "tool_result") {
        return "Result";
    }
    return formatTracePhaseLabel(item.phase);
}

function getToolTracePreviewMarkup(item = {}) {
    const callText = compactText(stripMarkdownToPlainText(item.toolCallContent || ""), 180);
    const resultText = compactText(stripMarkdownToPlainText(item.toolResultContent || (item.phase !== "tool_call" ? item.content : "") || ""), 260);
    if (callText || resultText) {
        return `
            ${callText ? `<div class="tool-trace-snippet tool-trace-snippet-call"><span>Input</span><p>${escapeHtml(callText)}</p></div>` : ""}
            ${resultText ? `<div class="tool-trace-snippet tool-trace-snippet-result"><span>Output</span><p>${escapeHtml(resultText)}</p></div>` : ""}
        `;
    }
    const fallbackText = compactText(stripMarkdownToPlainText(item.previewContent || item.content || ""), 320);
    return fallbackText ? `<p class="tool-trace-fallback">${escapeHtml(fallbackText)}</p>` : "";
}

function getToolTraceItemKey(item = {}) {
    return item.id || `${item.agent || ""}-${item.title || ""}-${item.timestamp || ""}`;
}

function createToolTraceItemNode() {
    const article = document.createElement("article");
    article.className = "tool-trace-item detail-trigger";
    article.setAttribute("tabindex", "0");
    article.setAttribute("role", "button");
    article.setAttribute("data-detail-mode", "markdown");
    return article;
}

function updateToolTraceItemNode(node, item = {}, shouldFlash = false) {
    if (!(node instanceof HTMLElement)) {
        return;
    }
    const key = getToolTraceItemKey(item);
    node.dataset.toolTraceKey = key;
    node.dataset.detailTraceId = item.id || "";
    node.dataset.detailTitle = `${item.agent || "Agent"} - ${formatTracePhaseLabel(item.phase)}`;
    node.dataset.detailSubtitle = item.title || "Trace detail";

    const isWebSearch = isWebSearchTraceEntry(item);
    node.className = [
        "tool-trace-item",
        `trace-tone-${item.tone || "progress"}`,
        isWebSearch ? "trace-tool-web" : "",
        shouldFlash ? "tool-trace-new" : "",
        "detail-trigger",
    ].filter(Boolean).join(" ");

    node.innerHTML = `
        <div class="tool-trace-topline">
            <strong>${escapeHtml(item.agent || item.title || "Live update")}</strong>
            <span>${escapeHtml(item.timestamp || "")}</span>
        </div>
        <div class="tool-trace-meta">
            <span class="trace-phase-badge ${isWebSearch ? "trace-phase-badge-web" : ""}">${escapeHtml(getToolTraceStateLabel(item))}</span>
            <span>${escapeHtml(item.title || "Live update")}</span>
        </div>
        ${getToolTracePreviewMarkup(item)}
    `;
}

function renderToolTraceList(element, feed, flashLatestTrace) {
    if (!(element instanceof HTMLElement)) {
        return;
    }

    const shouldStickToBottom = shouldAutoScrollLog(element);
    const existingNodes = new Map();
    Array.from(element.querySelectorAll(".tool-trace-item[data-tool-trace-key]"))
        .filter((child) => child instanceof HTMLElement)
        .forEach((child) => {
            existingNodes.set(String(child.dataset.toolTraceKey || ""), child);
        });

    if (!feed.length) {
        const emptyText = "Agent tool calls and reasoning traces will appear here when the backend stream starts.";
        const currentEmpty = element.querySelector(".tool-trace-empty");
        if (!(currentEmpty instanceof HTMLElement) || currentEmpty.textContent !== emptyText || element.children.length !== 1) {
            const emptyNode = document.createElement("div");
            emptyNode.className = "tool-trace-empty";
            emptyNode.textContent = emptyText;
            element.replaceChildren(emptyNode);
        }
        return;
    }

    const newKeys = new Set();
    const desiredNodes = [];
    const desiredKeys = new Set();

    feed.forEach((item) => {
        const key = getToolTraceItemKey(item);
        desiredKeys.add(key);
        let node = existingNodes.get(key);
        if (!(node instanceof HTMLElement)) {
            node = createToolTraceItemNode();
            newKeys.add(key);
        }
        const shouldFlash = flashLatestTrace && item.id === state.run.latestTraceId;
        updateToolTraceItemNode(node, item, shouldFlash);
        desiredNodes.push(node);
    });

    const viewportSnapshot = shouldStickToBottom ? null : getLogScrollSnapshotForToolTrace(element, desiredKeys);

    Array.from(element.children).forEach((child) => {
        if (!(child instanceof HTMLElement)) {
            return;
        }
        const key = String(child.dataset.toolTraceKey || "");
        if (child.classList.contains("tool-trace-item") && !desiredKeys.has(key)) {
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
        node.classList.toggle("tool-trace-new", shouldStickToBottom && newKeys.has(node.dataset.toolTraceKey || ""));
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
        const anchorNode = desiredNodes.find((node) => String(node.dataset.toolTraceKey || "") === viewportSnapshot.anchorKey) || null;
        if (anchorNode instanceof HTMLElement) {
            element.scrollTop = Math.max(0, anchorNode.offsetTop + viewportSnapshot.anchorOffset);
            return;
        }
        element.scrollTop = Math.max(0, viewportSnapshot.scrollTop - viewportSnapshot.removedAboveViewportHeight);
    }
}

function getLogScrollSnapshotForToolTrace(element, desiredKeys = null) {
    if (!(element instanceof HTMLElement)) {
        return null;
    }
    const items = Array.from(element.querySelectorAll(".tool-trace-item[data-tool-trace-key]"));
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
        const key = String(item.dataset.toolTraceKey || "");
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
    renderToolTraceList(elements.toolTraceList, feed, flashLatestTrace);
    state.run.flashLatestTrace = false;
}

function renderResearchRoom() {
    const research = state.run.research || {};
    setCompactPreview(elements.bullResearchPanel, research.bull_history, "The Bull Researcher has not responded yet.");
    setCompactPreview(elements.bearResearchPanel, research.bear_history, "The Bear Researcher has not responded yet.");

    elements.researchStatusText.textContent = research.history
        ? "Debate in progress"
        : "Awaiting analyst reports";
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
        : "Waiting for research debate";
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

function markdownCell(value = "") {
    return String(value ?? "")
        .replace(/\|/g, "\\|")
        .replace(/\r?\n/g, " ")
        .trim();
}

function formatEvidenceItemsMarkdown(items = []) {
    const evidenceItems = Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
    if (!evidenceItems.length) {
        return "";
    }
    const rows = [
        "| Agent | Direction | Confidence | Metric | Value | Timestamp | Source | Claim |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- |",
    ];
    evidenceItems.forEach((item) => {
        const confidence = Number(item.confidence ?? 0);
        rows.push(`| ${[
            item.agent_label || item.agent || "",
            item.direction || "",
            Number.isFinite(confidence) ? confidence.toFixed(2) : "",
            item.metric || "",
            item.value || "",
            item.timestamp || "",
            item.source || "",
            item.claim || "",
        ].map(markdownCell).join(" | ")} |`);
    });
    return rows.join("\n");
}

function formatEndpointSummariesMarkdown(items = []) {
    const summaries = Array.isArray(items) ? items.filter((item) => item && typeof item === "object") : [];
    if (!summaries.length) {
        return "";
    }
    return summaries.map((item) => {
        const metrics = item.key_metrics && typeof item.key_metrics === "object"
            ? Object.entries(item.key_metrics).map(([key, value]) => `- ${key}: ${value}`).join("\n")
            : "";
        const bullets = (item.summary_bullets || []).map((value) => `- ${value}`).join("\n");
        const caveats = (item.caveats || []).map((value) => `- ${value}`).join("\n");
        return [
            `### ${item.title || item.endpoint_name || "Endpoint"}`,
            `- **Direction:** ${item.direction || "-"}`,
            `- **Confidence:** ${item.confidence ?? "-"}`,
            `- **Source:** ${item.source || "-"}`,
            `- **Timestamp:** ${item.timestamp || "-"}`,
            metrics ? `\n**Key Metrics**\n${metrics}` : "",
            bullets ? `\n**Facts**\n${bullets}` : "",
            caveats ? `\n**Caveats**\n${caveats}` : "",
        ].filter(Boolean).join("\n");
    }).join("\n\n");
}

function getSourceGroupArtifactRows(groupKey = "") {
    const config = SOURCE_ARTIFACT_GROUPS[groupKey] || {};
    const savedRows = (state.run.sourceArtifactLists?.[groupKey] || []).filter((item) => item.source_kind !== "flow_block");
    return {
        groupKey,
        flowGroup: config.flowGroup || "",
        saved: savedRows.map((item) => ({
            section_key: item.section_key || "",
            title: item.title || item.source_key || "",
            source_kind: item.source_kind || item.artifact_type || "",
            source_key: item.source_key || "",
            summary: item.summary || "",
            created_at: item.created_at || "",
        })),
        live: getLiveSourceTraceEntries(groupKey).map((entry) => ({
            id: entry.id || "",
            title: entry.title || "",
            agent: entry.agent || "",
            phase: entry.phase || "",
            trace_id: entry.traceId || "",
            query: entry.toolCallContent || "",
            result: entry.toolResultContent || entry.content || "",
            timestamp: entry.timestamp || "",
        })),
    };
}

function getLiveFlowBlockPayload(blockKey = "", title = "", status = "pending", detail = null, summary = "") {
    const relatedSections = [];
    if (detail?.section) {
        relatedSections.push(detail.section);
    }
    if (detail?.key) {
        relatedSections.push(detail.key);
    }
    return {
        block_key: blockKey,
        title,
        status,
        summary,
        detail,
        related_sections: relatedSections,
        error: getLiveFlowBlockError(blockKey),
    };
}

function formatStructuredPayloadMarkdown(payload = {}, title = "Structured Payload") {
    if (!payload || typeof payload !== "object" || Array.isArray(payload) || Object.keys(payload).length === 0) {
        return "";
    }
    const renderStructuredFieldValue = (value) => {
        if (value === null) {
            return "null";
        }
        if (value === undefined) {
            return "";
        }
        if (typeof value === "object") {
            return JSON.stringify(value, null, 2);
        }
        return value;
    };
    const rows = [
        "| Field | Value |",
        "| --- | --- |",
        ...Object.entries(payload).map(([key, value]) => {
            return `| ${markdownCell(key)} | ${markdownCell(renderStructuredFieldValue(value))} |`;
        }),
    ];
    return [`### ${title}`, rows.join("\n")].join("\n\n");
}

function formatResearchDebateMarkdown(research = {}) {
    return [
        research.bull_history ? `## Bull Researcher\n\n${research.bull_history}` : "",
        research.bear_history ? `## Bear Researcher\n\n${research.bear_history}` : "",
        research.history ? `## Debate\n\n${research.history}` : "",
    ].filter(Boolean).join("\n\n");
}

function formatRiskDebateMarkdown(risk = {}) {
    return [
        risk.aggressive_history ? `## Aggressive Analyst\n\n${risk.aggressive_history}` : "",
        risk.neutral_history ? `## Neutral Analyst\n\n${risk.neutral_history}` : "",
        risk.conservative_history ? `## Conservative Analyst\n\n${risk.conservative_history}` : "",
        risk.history ? `## Debate\n\n${risk.history}` : "",
    ].filter(Boolean).join("\n\n");
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

    if (detail?.type === "source-artifact" || detail?.type === "history-final-decision") {
        return {
            content: detail.content || "",
            fallback: detail.fallback || "No saved markdown was returned.",
        };
    }

    switch (detail?.key) {
        case "endpointSummaries":
            return {
                content: formatEndpointSummariesMarkdown(state.run.endpointSummaries),
                fallback: "Endpoint summaries are not available for this run yet.",
            };
        case "liveCcxtData":
            return getSourceArtifactDetailContent("ccxt", "CCXT market data tool results have not appeared yet.");
        case "liveCoinGlassData":
            return getSourceArtifactDetailContent("coinglass", "CoinGlass endpoint results are not available for this run yet.");
        case "liveNewsData":
            return getSourceArtifactDetailContent("news", "News source results have not appeared yet.");
        case "liveSocialData":
            return getSourceArtifactDetailContent("social", "Social or web source results have not appeared yet.");
        case "liveCcxtSummary":
            return {
                content: getLiveSourceSummaryMarkdown("ccxt"),
                fallback: "Market summary markdown is not available yet.",
                payload: getSourceGroupArtifactRows("ccxt"),
            };
        case "liveCoinglassSummary":
            return {
                content: getLiveSourceSummaryMarkdown("coinglass"),
                fallback: "Onchain endpoint summary markdown is not available yet.",
                payload: getSourceGroupArtifactRows("coinglass"),
            };
        case "liveNewsSummary":
            return {
                content: getLiveSourceSummaryMarkdown("news"),
                fallback: "News summary markdown is not available yet.",
                payload: getSourceGroupArtifactRows("news"),
            };
        case "liveSocialSummary":
            return {
                content: getLiveSourceSummaryMarkdown("social"),
                fallback: "Social summary markdown is not available yet.",
                payload: getSourceGroupArtifactRows("social"),
            };
        case "evidenceExtractor":
        case "evidenceLedger":
            return {
                content: state.run.sections.structured_evidence || formatEvidenceItemsMarkdown(state.run.evidenceItems),
                fallback: "Structured evidence is not available for this run yet.",
            };
        case "researchDebate":
            return {
                content: formatResearchDebateMarkdown(research),
                fallback: "The research debate has not produced content yet.",
            };
        case "riskDebate":
            return {
                content: formatRiskDebateMarkdown(risk),
                fallback: "The risk debate has not produced content yet.",
            };
        case "decisionExtractor":
            return {
                content: formatStructuredPayloadMarkdown(state.run.structured?.final_trade_decision, "Decision Extractor"),
                fallback: "Structured final decision is not available for this run yet.",
            };
        case "verifierStructured":
            return {
                content: formatStructuredPayloadMarkdown(state.run.structured?.verification_report, "Verifier Payload"),
                fallback: "Structured verification is not available for this run yet.",
            };
        case "bullResearch":
            return { content: research.bull_history || "", fallback: "The Bull Researcher has not responded yet." };
        case "bearResearch":
            return { content: research.bear_history || "", fallback: "The Bear Researcher has not responded yet." };
        case "aggressiveRisk":
            return { content: risk.aggressive_history || risk.current_aggressive_response || "", fallback: "The Aggressive Analyst has not responded yet." };
        case "conservativeRisk":
            return { content: risk.conservative_history || risk.current_conservative_response || "", fallback: "The Conservative Analyst has not responded yet." };
        case "neutralRisk":
            return { content: risk.neutral_history || risk.current_neutral_response || "", fallback: "The Neutral Analyst has not responded yet." };
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
        case "persistence":
            return {
                content: [
                    "# History + Decision Persistence",
                    "",
                    `- History ID: ${state.run.complete?.history_id || "-"}`,
                    `- Source artifacts: ${getLiveSourceArtifactCount() || 0}`,
                    `- Evidence items: ${getLiveEvidenceCount() || 0}`,
                    `- Status: ${state.run.complete?.history_id ? "Saved" : state.run.complete ? "Completed without saved history ID" : "Pending"}`,
                ].join("\n"),
                fallback: "Persistence has not run yet.",
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

    const directMetaTypes = ["report", "trace", "history-section", "source-artifact", "history-final-decision"];
    const meta = directMetaTypes.includes(detail.type) ? detail : DETAIL_PANEL_META[detail.key] || {};
    const detailContent = getDetailContent(detail);
    setDetailPayload(detail, detailContent);
    const { content, fallback, toolResult, traceEntry } = detailContent;
    const mode = detailContent.mode || (toolResult ? "tool-result" : detail.mode || meta.mode || "markdown");
    const canGoBack = Array.isArray(state.detailBackStack) && state.detailBackStack.length > 0;
    if (elements.backDetailButton instanceof HTMLElement) {
        elements.backDetailButton.hidden = !canGoBack;
        elements.backDetailButton.disabled = !canGoBack;
    }
    elements.detailTitle.textContent = meta.title || "Panel Detail";
    elements.detailSubtitle.textContent = meta.subtitle || "Analysis detail";
    elements.detailBody.classList.toggle("plain-log", mode === "text");
    elements.detailBody.classList.toggle("markdown-preview", mode === "markdown");
    elements.detailBody.classList.toggle("tool-result-preview", mode === "tool-result");
    elements.detailBody.classList.toggle("source-table-preview", mode === "source-table");

    if (mode === "text") {
        elements.detailBody.textContent = content || fallback;
    } else if (mode === "source-table") {
        setSourceArtifactTablePreview(elements.detailBody, detailContent.rows || [], fallback, detailContent.groupKey || "");
    } else if (mode === "tool-result") {
        setToolResultPreview(elements.detailBody, toolResult, traceEntry, fallback);
    } else {
        setMarkdownPreview(elements.detailBody, content, fallback);
    }
}

function openDetailModal(detail, options = {}) {
    if (options.pushHistory !== false && state.activeDetail && !elements.detailModal.classList.contains("hidden")) {
        state.detailBackStack = [...(state.detailBackStack || []), state.activeDetail].slice(-12);
    }
    state.activeDetail = detail;
    showModal(elements.detailModal);
    renderActiveDetail();
}

function goBackDetailModal() {
    const previousDetail = state.detailBackStack?.pop();
    if (!previousDetail) {
        return;
    }
    state.activeDetail = previousDetail;
    renderActiveDetail();
}

async function openSavedSourceArtifactDetail(runId = "", sectionKey = "") {
    const safeRunId = String(runId || "").trim();
    const safeSectionKey = String(sectionKey || "").trim();
    if (!safeRunId || !safeSectionKey) {
        return;
    }
    openDetailModal({
        type: "source-artifact",
        title: "Source Artifact",
        subtitle: "Loading saved source detail",
        content: "",
        fallback: "Loading saved source artifact...",
        mode: "markdown",
    });
    const response = await apiFetch(`/api/history/${encodeURIComponent(safeRunId)}/artifacts/${encodeURIComponent(safeSectionKey)}`, {
        headers: getAuthHeaders(),
        cache: "no-store",
    });
    if (!response.ok) {
        throw new Error(await readResponseError(response));
    }
    const payload = await response.json();
    const artifact = payload.artifact || {};
    openDetailModal({
        type: "source-artifact",
        title: artifact.title || "Source Artifact",
        subtitle: [artifact.agent, artifact.source_kind || artifact.flow_group].filter(Boolean).join(" - ") || "Saved source detail",
        content: artifact.markdown || "",
        fallback: "This artifact has no markdown content.",
        mode: "markdown",
    }, { pushHistory: false });
}

function closeDetailModal() {
    hideModal(elements.detailModal);
    state.activeDetail = null;
    state.detailBackStack = [];
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

