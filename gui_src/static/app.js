// ORFS GUI — Main application logic

let cy = null;           // Cytoscape instance
let selectedDesign = null; // Currently selected design path
let statusData = {};     // Target build status cache
let designsData = {};    // Cached target hierarchy
let expandedDesigns = new Set(); // Which designs are expanded in tree
let eventSource = null;  // SSE connection

// Chronological stage order for sorting
const STAGE_ORDER = [
    'synth', 'floorplan', 'place', 'cts', 'grt', 'route', 'final',
    'generate_abstract', 'generate_metadata', 'test', 'update_rules'
];

// ── Initialization ──────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initSash();
    initTabs();
    initGraph();
    initLogSearch();
    checkHealth();
    refreshAll();
    refreshBuilds();
    connectSSE();
    // Auto-refresh status every 5s, builds every 3s
    setInterval(loadStatus, 5000);
    setInterval(refreshBuilds, 3000);
});

function initTheme() {
    const saved = localStorage.getItem('orfs-gui-theme') || 'light';
    setTheme(saved);
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('orfs-gui-theme', theme);
    const sel = document.getElementById('theme-select');
    if (sel) sel.value = theme;
}

function initSash() {
    const sidebar = document.getElementById('sidebar');
    const app = document.querySelector('.app');
    let dragging = false;

    sidebar.addEventListener('mousedown', (e) => {
        // Only start drag if clicking near the right edge (the sash)
        const rect = sidebar.getBoundingClientRect();
        if (e.clientX > rect.right - 8) {
            dragging = true;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        }
    });

    document.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const width = Math.max(180, Math.min(600, e.clientX));
        app.style.gridTemplateColumns = `${width}px 1fr`;
        if (cy) cy.resize();
    });

    document.addEventListener('mouseup', () => {
        if (dragging) {
            dragging = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }
    });

    // Show col-resize cursor when hovering the sash edge
    sidebar.addEventListener('mousemove', (e) => {
        const rect = sidebar.getBoundingClientRect();
        sidebar.style.cursor = (e.clientX > rect.right - 8) ? 'col-resize' : '';
    });
}

let graphLoaded = false;

function initTabs() {
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            tab.classList.add('active');
            document.querySelector(`.tab-content[data-tab="${tab.dataset.tab}"]`).classList.add('active');
            if (tab.dataset.tab === 'graph') {
                if (cy) cy.resize();
                if (!graphLoaded) { graphLoaded = true; loadGraph(); }
            }
            if (tab.dataset.tab === 'builds') refreshBuilds();
        });
    });
}

function initGraph() {
    const container = document.getElementById('graph-container');
    if (typeof cytoscape === 'undefined') {
        container.innerHTML = '<div class="empty-state"><div class="empty-state-text">Cytoscape.js not loaded — place cytoscape.min.js in gui_src/static/lib/</div></div>';
        return;
    }
    cy = cytoscape({
        container: container,
        style: [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'background-color': 'data(color)',
                    'color': '#e4e4e7',
                    'font-size': '10px',
                    'text-valign': 'bottom',
                    'text-margin-y': 6,
                    'width': 24,
                    'height': 24,
                    'border-width': 2,
                    'border-color': '#2d3040',
                    'font-family': '-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif',
                }
            },
            { selector: 'node.done', style: { 'border-color': '#22c55e', 'border-width': 3 } },
            { selector: 'node.building', style: { 'border-color': '#3b82f6', 'border-width': 3 } },
            { selector: 'node.stale', style: { 'border-color': '#f59e0b', 'border-width': 3, 'border-style': 'dashed' } },
            { selector: 'node.failed', style: { 'border-color': '#ef4444', 'border-width': 3 } },
            {
                selector: 'edge',
                style: {
                    'width': 1.5,
                    'line-color': '#3f4255',
                    'target-arrow-color': '#3f4255',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'arrow-scale': 0.8,
                }
            },
            { selector: ':selected', style: { 'border-color': '#6366f1', 'border-width': 3 } }
        ],
        layout: { name: 'preset' },
        minZoom: 0.1,
        maxZoom: 3,
    });

    cy.on('tap', 'node', (evt) => showNodeDetail(evt.target.data()));
    cy.on('tap', (evt) => { if (evt.target === cy) closeDetailPanel(); });
}

function initLogSearch() {
    document.getElementById('log-search').addEventListener('input', (e) => {
        highlightLogSearch(e.target.value);
    });
    document.getElementById('log-stage-select').addEventListener('change', (e) => {
        if (selectedDesign && e.target.value) loadLog(selectedDesign, e.target.value);
    });
    document.getElementById('report-stage-select').addEventListener('change', (e) => {
        if (selectedDesign && e.target.value) loadReport(selectedDesign, e.target.value);
    });
}

// ── API calls ───────────────────────────────────────────────────────────

async function api(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
    return resp.json();
}

async function apiText(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
    return resp.text();
}

async function checkHealth() {
    try {
        const data = await api('/api/health');
        document.getElementById('workspace-path').textContent = data.workspace;
    } catch (e) {
        document.getElementById('workspace-path').textContent = 'Not connected';
    }
    try {
        const cache = await api('/api/cache-check');
        const badge = document.getElementById('cache-badge');
        if (cache.configured) {
            badge.className = 'cache-badge ok';
            badge.textContent = 'Cache OK';
            badge.title = `Disk cache: ${cache.path}`;
        } else {
            badge.className = 'cache-badge warn';
            badge.textContent = 'No disk cache';
            badge.title = 'Configure --disk_cache in .bazelrc for faster builds';
        }
    } catch (e) { /* ignore */ }
}

async function refreshAll() {
    // Don't load graph on refresh — it's slow (full bazel query).
    // Graph loads on demand when the Graph tab is selected.
    await Promise.all([loadTargets(), loadStatus()]);
}

// ── Targets sidebar (collapsible tree) ──────────────────────────────────

async function loadTargets() {
    try {
        const data = await api('/api/targets');
        designsData = data.designs || {};
        renderDesignTree();
    } catch (e) {
        document.getElementById('design-tree').innerHTML =
            `<div class="empty-state"><div class="empty-state-text">${escapeHtml(e.message)}</div></div>`;
    }
}

function toggleDesign(key, evt) {
    evt.stopPropagation();
    if (expandedDesigns.has(key)) {
        expandedDesigns.delete(key);
    } else {
        expandedDesigns.add(key);
    }
    renderDesignTree();
}

function renderDesignTree() {
    const tree = document.getElementById('design-tree');
    const designs = designsData;
    if (!Object.keys(designs).length) {
        tree.innerHTML = '<div class="empty-state"><div class="empty-state-text">No ORFS targets found</div></div>';
        return;
    }

    // Group by pkg/design so variants collapse under one parent
    const groups = {};
    for (const [key, design] of Object.entries(designs)) {
        const pkg = design.package || '';
        const name = design.design || key.split('/').pop();
        const groupKey = `${pkg}/${name}`;
        if (!groups[groupKey]) {
            groups[groupKey] = { pkg, name, entries: [] };
        }
        groups[groupKey].entries.push({ key, design });
    }

    let html = '';
    for (const [groupKey, group] of Object.entries(groups)) {
        const hasVariants = group.entries.length > 1;
        const isMacro = group.entries.some(e => e.design.is_macro);
        const badge = isMacro ? '<span class="design-badge macro">macro</span>' : '';

        if (hasVariants) {
            // Collapsible group header
            const expanded = expandedDesigns.has(groupKey);
            const chevron = expanded ? '&#9660;' : '&#9654;';
            html += `<div class="design-item" onclick="toggleDesign('${escapeAttr(groupKey)}', event)">
                <span class="chevron">${chevron}</span>
                <span class="status-dot missing"></span>
                <span class="stage-name">${escapeHtml(group.pkg)}/<b>${escapeHtml(group.name)}</b></span>
                ${badge}
                <span style="color:var(--text-muted);font-size:var(--font-size-sm)">${group.entries.length}</span>
            </div>`;
            if (expanded) {
                for (const entry of group.entries) {
                    const variant = entry.design.variant || 'default';
                    const varKey = entry.key;
                    const varExpanded = expandedDesigns.has(varKey);
                    const varChevron = varExpanded ? '&#9660;' : '&#9654;';
                    const isActive = selectedDesign === varKey ? ' active' : '';
                    html += `<div class="design-item${isActive}" style="padding-left:28px" onclick="selectDesign('${escapeAttr(varKey)}')">
                        <span class="chevron" onclick="toggleDesign('${escapeAttr(varKey)}', event)">${varChevron}</span>
                        <span class="status-dot ${getDesignStatus(varKey)}"></span>
                        <span class="stage-name">${escapeHtml(variant)}</span>
                    </div>`;
                    if (varExpanded) {
                        html += renderStages(entry, 56);
                    }
                }
            }
        } else {
            // Single variant — show directly with stages
            const entry = group.entries[0];
            const expanded = expandedDesigns.has(entry.key);
            const chevron = expanded ? '&#9660;' : '&#9654;';
            const isActive = selectedDesign === entry.key ? ' active' : '';
            html += `<div class="design-item${isActive}" onclick="selectDesign('${escapeAttr(entry.key)}')">
                <span class="chevron" onclick="toggleDesign('${escapeAttr(entry.key)}', event)">${chevron}</span>
                <span class="status-dot ${getDesignStatus(entry.key)}"></span>
                <span class="stage-name">${escapeHtml(group.pkg)}/<b>${escapeHtml(group.name)}</b></span>
                ${badge}
            </div>`;
            if (expanded) {
                html += renderStages(entry, 40);
            }
        }
    }
    tree.innerHTML = html;
}

function renderStages(entry, indent) {
    let html = '';
    for (const [variant, vdata] of Object.entries(entry.design.variants || {})) {
        const stages = Object.entries(vdata.stages || {});
        stages.sort((a, b) => {
            const ai = STAGE_ORDER.indexOf(a[0]);
            const bi = STAGE_ORDER.indexOf(b[0]);
            return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
        });
        for (const [stage, target] of stages) {
            const stageStatus = getStageStatus(entry.key, stage);
            html += `<div class="design-item" style="padding-left:${indent}px"
                onclick="selectDesign('${escapeAttr(entry.key)}'); switchTab('metrics')">
                <span class="status-dot ${stageStatus}"></span>
                <span class="stage-name">${escapeHtml(stage)}</span>
                <span class="build-btn" onclick="event.stopPropagation(); startBuild('${escapeAttr(target)}')" title="Build ${escapeAttr(target)}">build</span>
            </div>`;
        }
    }
    return html;
}

function getDesignStatus(key) {
    if (!statusData[key]) return 'missing';
    const stages = Object.values(statusData[key]);
    if (stages.includes('failed')) return 'failed';
    if (stages.includes('building')) return 'building';
    if (stages.every(s => s === 'done')) return 'done';
    return 'stale';
}

function getStageStatus(designKey, stage) {
    return statusData[designKey]?.[stage] || 'missing';
}

function selectDesign(key) {
    selectedDesign = key;
    renderDesignTree();
    loadMetrics(key);
}

function buildDesign(key, evt) {
    evt.stopPropagation();
    const design = designsData[key];
    if (!design) return;
    // Build the last stage target
    const variants = Object.values(design.variants || {});
    if (!variants.length) return;
    const stages = variants[0].stages || {};
    const stageNames = Object.keys(stages);
    const lastStage = stageNames[stageNames.length - 1];
    const target = stages[lastStage];
    if (target) startBuild(target);
}

// ── Graph ───────────────────────────────────────────────────────────────

async function loadGraph() {
    if (!cy) return;
    try {
        const data = await api('/api/graph');
        cy.elements().remove();
        if (data.elements) {
            cy.add(data.elements.nodes || []);
            cy.add(data.elements.edges || []);
            applyStatusToGraph();
            cy.layout({
                name: 'breadthfirst',
                directed: true,
                spacingFactor: 1.2,
                padding: 30,
            }).run();
            cy.fit(null, 40);
        }
    } catch (e) {
        console.error('Graph load error:', e);
    }
}

function applyStatusToGraph() {
    if (!cy) return;
    cy.nodes().forEach(node => {
        const id = node.data('id');
        node.removeClass('done building stale failed');
        for (const [designKey, stages] of Object.entries(statusData)) {
            for (const [stage, status] of Object.entries(stages)) {
                if (id.includes(stage) && id.includes(designKey.split('/').pop())) {
                    node.addClass(status);
                }
            }
        }
    });
}

// ── Status ──────────────────────────────────────────────────────────────

async function loadStatus() {
    try {
        const prev = JSON.stringify(statusData);
        statusData = await api('/api/status');
        // Only re-render if status actually changed
        if (JSON.stringify(statusData) !== prev) {
            applyStatusToGraph();
            renderDesignTree();
        }
    } catch (e) { /* ignore */ }
}

// ── Metrics ─────────────────────────────────────────────────────────────

async function loadMetrics(designPath) {
    const container = document.getElementById('metrics-content');
    try {
        const data = await api(`/api/metrics/${designPath}`);
        renderMetrics(container, data);
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><div class="empty-state-text">${escapeHtml(e.message)}</div></div>`;
    }
}

function renderMetrics(container, data) {
    let html = '';
    if (data.ppa && Object.keys(data.ppa).length) {
        html += '<table class="metrics-table"><thead><tr><th>PPA Metric</th><th>Value</th></tr></thead><tbody>';
        for (const [key, value] of Object.entries(data.ppa)) {
            html += `<tr><td>${escapeHtml(key)}</td><td>${formatValue(value)}</td></tr>`;
        }
        html += '</tbody></table>';
    }
    for (const [stage, stageData] of Object.entries(data.stages || {})) {
        html += `<h3 style="padding:12px 16px;font-size:13px;color:#a1a1aa;border-bottom:1px solid #2d3040">${escapeHtml(stage)}</h3>`;
        for (const [file, metrics] of Object.entries(stageData)) {
            if (metrics.error) {
                html += `<div style="padding:8px 16px;color:#ef4444">${escapeHtml(file)}: ${escapeHtml(metrics.error)}</div>`;
                continue;
            }
            html += '<table class="metrics-table"><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>';
            for (const [k, v] of Object.entries(metrics)) {
                html += `<tr><td>${escapeHtml(k)}</td><td>${formatValue(v)}</td></tr>`;
            }
            html += '</tbody></table>';
        }
    }
    if (!html) html = '<div class="empty-state"><div class="empty-state-text">No metrics available</div></div>';
    container.innerHTML = html;
}

// ── Logs ────────────────────────────────────────────────────────────────

async function loadLog(designPath, stage) {
    const container = document.getElementById('log-content');
    try {
        const text = await apiText(`/api/logs/${designPath}/${stage}`);
        container.innerHTML = highlightLogLines(text);
        container.scrollTop = container.scrollHeight;
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><div class="empty-state-text">${escapeHtml(e.message)}</div></div>`;
    }
}

function highlightLogLines(text) {
    return text.split('\n').map(line => {
        if (/\bERROR\b|\bFATAL\b|\bCRITICAL\b/i.test(line))
            return `<span class="line-error">${escapeHtml(line)}</span>`;
        if (/\bWARNING\b|\bWARN\b/i.test(line))
            return `<span class="line-warning">${escapeHtml(line)}</span>`;
        return escapeHtml(line);
    }).join('\n');
}

function highlightLogSearch(query) {
    const container = document.getElementById('log-content');
    if (!query) return;
    const text = container.textContent;
    const idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx >= 0) {
        container.scrollTop = container.scrollHeight * (idx / text.length);
    }
}

// ── Reports ─────────────────────────────────────────────────────────────

async function loadReport(designPath, stage) {
    const container = document.getElementById('report-content');
    try {
        const text = await apiText(`/api/reports/${designPath}/${stage}`);
        container.innerHTML = highlightLogLines(text);
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><div class="empty-state-text">${escapeHtml(e.message)}</div></div>`;
    }
}

// ── Node detail panel ───────────────────────────────────────────────────

function showNodeDetail(data) {
    const panel = document.getElementById('detail-panel');
    document.getElementById('detail-title').textContent = data.label;
    let html = '';
    html += field('Target', data.id);
    html += field('Stage', data.stage || 'unknown');
    html += `<div style="margin-top:12px">
        <button class="btn btn-primary" onclick="startBuild('${escapeAttr(data.id)}')">Build</button>
    </div>`;
    document.getElementById('detail-content').innerHTML = html;
    panel.classList.add('open');
}

function closeDetailPanel() {
    document.getElementById('detail-panel').classList.remove('open');
}

function field(label, value) {
    return `<div class="field"><div class="field-label">${escapeHtml(label)}</div><div class="field-value">${value}</div></div>`;
}

// ── Builds ──────────────────────────────────────────────────────────────

let buildRefreshInterval = null;
let selectedBuildTarget = null;

async function startBuild(target) {
    // Immediate visual feedback
    switchTab('builds');
    const logEl = document.getElementById('build-log-content');
    logEl.innerHTML = `<span style="color:var(--text-muted)">Starting build for ${escapeHtml(target)}...</span>`;

    try {
        const resp = await fetch(`/api/build/${encodeURIComponent(target)}`, { method: 'POST' });
        const data = await resp.json();
        if (data.error) {
            logEl.innerHTML = `<span class="line-error">Build error: ${escapeHtml(data.error)}</span>`;
            return;
        }
        selectedBuildTarget = target;
        startBuildMonitor();
        // Poll immediately and again shortly for fast/cached builds
        await refreshBuilds();
        setTimeout(refreshBuilds, 500);
        setTimeout(refreshBuilds, 1500);
    } catch (e) {
        logEl.innerHTML = `<span class="line-error">Failed to start build: ${escapeHtml(e.message)}</span>`;
    }
}

function startBuildMonitor() {
    if (buildRefreshInterval) clearInterval(buildRefreshInterval);
    buildRefreshInterval = setInterval(refreshBuilds, 2000);
}

async function refreshBuilds() {
    try {
        const data = await api('/api/builds');
        renderBuildsList(data);

        // Count running builds
        const running = Object.values(data).filter(b => b.status === 'running').length;

        // Update prominent Bazel status badge in topbar
        const badge = document.getElementById('bazel-status');
        const stopBtn = document.getElementById('bazel-stop-btn');
        if (running > 0) {
            badge.textContent = `Building (${running})`;
            badge.className = 'bazel-status busy';
            stopBtn.style.display = '';
        } else {
            badge.textContent = 'Idle';
            badge.className = 'bazel-status idle';
            stopBtn.style.display = 'none';
        }

        // Update tab indicator
        const tab = document.getElementById('builds-tab');
        tab.textContent = running > 0 ? `Builds (${running})` : 'Builds';
        if (running > 0) {
            tab.style.color = 'var(--blue)';
        } else {
            tab.style.color = '';
            if (buildRefreshInterval) {
                clearInterval(buildRefreshInterval);
                buildRefreshInterval = null;
            }
            loadStatus();
        }

        // Auto-refresh selected build log
        if (selectedBuildTarget && data[selectedBuildTarget]) {
            loadBuildLog(selectedBuildTarget);
        }
    } catch (e) { /* ignore */ }
}

function renderBuildsList(data) {
    const container = document.getElementById('builds-list');
    if (!Object.keys(data).length) {
        container.innerHTML = '<div style="padding:16px;color:var(--text-muted)">No builds. Click "Build" on a graph node or use the button below.</div>';
        return;
    }
    let html = '';
    for (const [target, info] of Object.entries(data)) {
        const statusClass = info.status === 'running' ? 'building' :
                           info.status === 'success' ? 'done' : 'failed';
        const statusLabel = info.status === 'running' ? `${info.elapsed}s` : info.status;
        const isSelected = selectedBuildTarget === target ? ' active' : '';
        html += `<div class="design-item${isSelected}" onclick="selectBuildLog('${escapeAttr(target)}')" style="padding:8px 0">
            <span class="status-dot ${statusClass}"></span>
            <span class="stage-name">${escapeHtml(target)}</span>
            <span style="color:var(--text-muted);font-size:var(--font-size-sm)">${statusLabel}</span>
        </div>`;
    }
    container.innerHTML = html;
}

function selectBuildLog(target) {
    selectedBuildTarget = target;
    loadBuildLog(target);
    refreshBuilds();
}

async function loadBuildLog(target) {
    const container = document.getElementById('build-log-content');
    try {
        const text = await apiText(`/api/build-log/${encodeURIComponent(target)}`);
        const wasAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50;
        container.innerHTML = highlightLogLines(text);
        if (wasAtBottom) container.scrollTop = container.scrollHeight;
    } catch (e) {
        container.innerHTML = `<span style="color:var(--text-muted)">Waiting for output...</span>`;
    }
}

async function stopBuild() {
    try {
        await fetch('/api/builds/stop', { method: 'POST' });
        refreshBuilds();
    } catch (e) { /* ignore */ }
}

function updateBuildsTab(status) {
    const tab = document.getElementById('builds-tab');
    if (status === 'started' || status === 'already_running') {
        tab.style.color = 'var(--blue)';
    }
}

// ── SSE live updates ────────────────────────────────────────────────────

function connectSSE() {
    if (eventSource) eventSource.close();
    eventSource = new EventSource('/api/events');
    eventSource.onmessage = (e) => {
        try {
            const changes = JSON.parse(e.data);
            if (changes.length) loadStatus();
        } catch (err) { /* ignore */ }
    };
    eventSource.onerror = () => {
        eventSource.close();
        setTimeout(connectSSE, 5000);
    };
}

// ── Utilities ───────────────────────────────────────────────────────────

function switchTab(tabName) {
    document.querySelector(`.tab[data-tab="${tabName}"]`)?.click();
}

function formatValue(v) {
    if (typeof v === 'number') {
        if (Math.abs(v) >= 1e6) return v.toExponential(3);
        if (Number.isInteger(v)) return v.toLocaleString();
        return v.toPrecision(4);
    }
    return escapeHtml(String(v));
}

function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

function escapeAttr(s) {
    return s.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
