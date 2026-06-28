// --- Configuration ---
// For local testing, use 'http://127.0.0.1:8000'
// For VPS deployment, use '' to rely on Nginx reverse proxy
const API_BASE_URL = window.API_BASE_URL || "";

const state = {
    activeTab: 'live',
    devices: [],
    selectedDeviceId: '',
    refreshInterval: null,
    liveChartInstance: null,
    histChartInstance: null
};

// =============================================
// AUTH / LOGIN
// =============================================

function getToken() {
    return localStorage.getItem('acoustic_token');
}

function setToken(token) {
    localStorage.setItem('acoustic_token', token);
}

function clearToken() {
    localStorage.removeItem('acoustic_token');
    localStorage.removeItem('acoustic_user');
}

function isLoggedIn() {
    return !!getToken();
}

function showLogin() {
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('dashboard-wrapper').classList.add('hidden');
    if (state.refreshInterval) {
        clearInterval(state.refreshInterval);
        state.refreshInterval = null;
    }
}

function showDashboard() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('dashboard-wrapper').classList.remove('hidden');
    const user = localStorage.getItem('acoustic_user');
    const role = localStorage.getItem('acoustic_role');
    if (user) {
        document.getElementById('user-label').textContent = user + ' · Logout';
    }
    if (role === 'admin') {
        document.getElementById('admin-tab-btn').classList.remove('hidden');
    } else {
        document.getElementById('admin-tab-btn').classList.add('hidden');
    }
}

async function handleLogin(event) {
    event.preventDefault();
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    const submitBtn = document.getElementById('login-submit');

    errorEl.classList.add('hidden');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Signing in…';

    try {
        const resp = await fetch(`${API_BASE_URL}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        if (!resp.ok) {
            const data = await resp.json().catch(() => ({}));
            throw new Error(data.detail || 'Invalid credentials');
        }

        const data = await resp.json();
        setToken(data.access_token);
        localStorage.setItem('acoustic_user', data.display_name || data.username || username);
        localStorage.setItem('acoustic_role', data.role || 'viewer');
        showDashboard();
        init();
    } catch (err) {
        errorEl.textContent = err.message || 'Login failed. Check your credentials.';
        errorEl.classList.remove('hidden');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign In';
    }
}

function handleLogout() {
    clearToken();
    showLogin();
}

// =============================================
// INITIALIZATION
// =============================================

document.addEventListener('DOMContentLoaded', () => {
    if (isLoggedIn()) {
        showDashboard();
        init();
    } else {
        showLogin();
    }
});

async function init() {
    await loadDevices();

    document.getElementById('global-device-selector').addEventListener('change', (e) => {
        state.selectedDeviceId = e.target.value;
        refreshCurrentTab();
    });

    // Default dates for history/report
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];
    const todayLocal = todayStr + 'T00:00';

    document.getElementById('hist-start-date').value = todayStr;
    document.getElementById('hist-end-date').value = todayStr;
    document.getElementById('report-start').value = todayLocal;
    document.getElementById('report-end').value = todayLocal;

    // Nav tab listeners
    document.querySelectorAll(".nav-tab").forEach(tab => {
        tab.addEventListener("click", () => switchView(tab.dataset.view));
    });

    switchView('live');
}

function switchView(viewName) {
    state.activeTab = viewName;

    document.querySelectorAll(".view").forEach(view => {
        view.classList.remove("active");
    });
    document.querySelector(`#view-${viewName}`).classList.add("active");

    document.querySelectorAll(".nav-tab").forEach(tab => {
        tab.classList.toggle("active", tab.dataset.view === viewName);
    });

    if (state.refreshInterval) {
        clearInterval(state.refreshInterval);
        state.refreshInterval = null;
    }

    if (viewName === "live") {
        loadLiveMeasurements();
        state.refreshInterval = setInterval(loadLiveMeasurements, 5000);
    }
    if (viewName === "devices") {
        loadDevicesView();
    }
    if (viewName === "admin") {
        loadAdminUsers();
        loadAdminDevices();
    }
}

function refreshCurrentTab() {
    if (state.activeTab === 'live') {
        loadLiveMeasurements();
    } else if (state.activeTab === 'devices') {
        loadDevicesView();
    } else if (state.activeTab === 'admin') {
        loadAdminUsers();
        loadAdminDevices();
    }
}

// =============================================
// API HELPERS
// =============================================

async function apiFetch(path) {
    const url = `${API_BASE_URL}${path}`;
    const headers = {};
    const token = getToken();
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(url, { headers });
        if (response.status === 401) {
            clearToken();
            showLogin();
            return null;
        }
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error("API fetch failed:", error);
        return null;
    }
}

function formatDateTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleString();
}

// =============================================
// QUALITY FLAGS HELPERS
// =============================================

function parseQualityFlags(value) {
    if (!value) return null;
    if (typeof value === 'object') return value;
    if (typeof value === 'string') {
        try { return JSON.parse(value); } catch (e) { return null; }
    }
    return null;
}

function formatQualityFlags(flags) {
    const parsed = parseQualityFlags(flags);
    if (!parsed) return 'Not reported';

    const issues = [];
    if (parsed.clipping) issues.push('Clipping');
    if (parsed.low_signal) issues.push('Low signal');
    if (parsed.mic_error) issues.push('Mic error');

    return issues.length > 0 ? issues.join(', ') : 'Normal';
}

function qualityFlagsBadgeClass(flags) {
    const parsed = parseQualityFlags(flags);
    if (!parsed) return '';
    if (parsed.mic_error || parsed.clipping) return 'error';
    if (parsed.low_signal) return 'warning';
    return 'ok';
}

function qualityFlagsDescription(flags) {
    const parsed = parseQualityFlags(flags);
    if (!parsed) return 'Quality flags were not provided by this edge version.';

    const issues = [];
    if (parsed.clipping) issues.push('Input signal may be too loud and clipped.');
    if (parsed.low_signal) issues.push('Input signal may be too weak.');
    if (parsed.mic_error) issues.push('Microphone capture error reported.');

    if (issues.length === 0) {
        return 'No clipping, low-signal, or microphone error reported.';
    }
    return issues.join(' ');
}

// =============================================
// UNIT HELPERS (dB / dBA)
// =============================================

function getUnit(weighting) {
    if (weighting && weighting.toUpperCase() === 'A') return 'dBA';
    return 'dB';
}

function getWeightingLabel(weighting) {
    if (!weighting) return 'Unknown';
    if (weighting.toUpperCase() === 'A') return 'A-weighted';
    if (weighting.toLowerCase() === 'flat') return 'Flat';
    return weighting;
}

// =============================================
// LIVE TAB
// =============================================

async function loadLiveMeasurements() {
    const statusBadge = document.getElementById('api-status');
    statusBadge.textContent = 'Syncing…';
    statusBadge.className = 'badge syncing';

    apiFetch('/api/status/summary').then(statusData => {
        if (statusData) renderSmartStatus(statusData);
    });

    let path = '/api/measurements?limit=100';
    if (state.selectedDeviceId) {
        path += `&device_id=${encodeURIComponent(state.selectedDeviceId)}`;
    }

    const data = await apiFetch(path);
    if (!data) {
        statusBadge.textContent = 'Offline';
        statusBadge.className = 'badge error';
        return;
    }

    statusBadge.textContent = 'Connected';
    statusBadge.className = 'badge ok';

    renderLiveView(data);
}

function renderSmartStatus(data) {
    const banner = document.getElementById('smart-status-banner');
    const title = document.getElementById('status-noise-state');
    const msg = document.getElementById('status-message');
    const room = document.getElementById('status-room');
    const loc = document.getElementById('status-location');
    const time = document.getElementById('status-time');
    const qual = document.getElementById('status-quality');
    const icon = document.getElementById('status-icon');

    title.textContent = data.noise_state;
    msg.textContent = data.message;
    room.textContent = data.room || '--';
    loc.textContent = data.location || '--';
    time.textContent = data.last_seen ? formatDateTime(data.last_seen) : '--';
    qual.textContent = data.quality || '--';

    let bgClass = 'quiet-state';
    let iconStr = 'ℹ️';
    
    if (data.severity === 'high' || data.severity === 'critical') {
        bgClass = 'alert-state';
        iconStr = '⚠️';
    } else if (data.severity === 'medium') {
        bgClass = 'elevated-state';
        iconStr = '🔔';
    } else if (data.noise_state === 'Offline') {
        bgClass = 'offline-state';
        iconStr = '🔌';
    } else {
        iconStr = '✅';
    }
    
    banner.className = 'status-banner ' + bgClass;
    icon.textContent = iconStr;
}

function renderLiveView(measurements) {
    if (!measurements || measurements.length === 0) {
        document.getElementById('live-spl-avg').textContent = '--';
        document.getElementById('live-spl-max').textContent = '--';
        document.getElementById('live-chart-empty').classList.remove('hidden');
        return;
    }

    document.getElementById('live-chart-empty').classList.add('hidden');

    const latest = measurements[0];
    const avgSpl = latest.spl_avg_db !== null && latest.spl_avg_db !== undefined ? latest.spl_avg_db : latest.total_dba;
    const maxSpl = latest.spl_max_db !== null && latest.spl_max_db !== undefined ? latest.spl_max_db : avgSpl;
    const unit = getUnit(latest.weighting);

    document.getElementById('live-spl-avg').textContent = avgSpl != null ? avgSpl.toFixed(1) : '--';
    document.getElementById('live-spl-max').textContent = maxSpl != null ? maxSpl.toFixed(1) : '--';
    document.getElementById('live-unit-avg').textContent = unit;
    document.getElementById('live-unit-max').textContent = unit;

    document.getElementById('live-cal-offset').textContent = latest.calibration_offset_db != null ? latest.calibration_offset_db : '0';
    document.getElementById('live-weighting').textContent = getWeightingLabel(latest.weighting);
    document.getElementById('live-edge-version').textContent = latest.edge_version || 'Not reported';
    document.getElementById('live-last-seen').textContent = formatDateTime(latest.measured_at);

    // Quality flags
    const qBadge = document.getElementById('live-quality-badge');
    const qDetail = document.getElementById('live-quality-detail');
    const qText = formatQualityFlags(latest.quality_flags);
    const qClass = qualityFlagsBadgeClass(latest.quality_flags);
    qBadge.textContent = qText;
    qBadge.className = 'badge ' + (qClass || '');
    qDetail.textContent = qualityFlagsDescription(latest.quality_flags);

    // Status
    const statusEl = document.getElementById('live-status');
    const now = new Date();
    const lastSeen = new Date(latest.measured_at);
    const diffSecs = (now - lastSeen) / 1000;

    if (diffSecs > 120) {
        statusEl.textContent = 'Stale';
        statusEl.className = 'badge stale';
    } else {
        statusEl.textContent = latest.status === 'error' ? 'Error' : 'Online';
        statusEl.className = latest.status === 'error' ? 'badge error' : 'badge ok';
    }

    // Chart
    const reversed = [...measurements].reverse();
    const labels = reversed.map(m => new Date(m.measured_at).toLocaleTimeString());
    const dataAvg = reversed.map(m => m.spl_avg_db != null ? m.spl_avg_db : m.total_dba);
    const dataMax = reversed.map(m => m.spl_max_db != null ? m.spl_max_db : (m.spl_avg_db != null ? m.spl_avg_db : m.total_dba));

    const allVals = dataAvg.concat(dataMax).filter(v => v != null);
    const yMin = allVals.length > 0 ? Math.floor(Math.min(...allVals) - 5) : 30;
    const yMax = allVals.length > 0 ? Math.ceil(Math.max(...allVals) + 5) : 120;

    const ctx = document.getElementById('live-chart').getContext('2d');
    if (state.liveChartInstance) state.liveChartInstance.destroy();

    state.liveChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: `SPL Avg (${unit})`,
                    data: dataAvg,
                    borderColor: '#171717',
                    backgroundColor: 'rgba(23, 23, 23, 0.08)',
                    tension: 0.3,
                    fill: true,
                    pointRadius: 0,
                    borderWidth: 2
                },
                {
                    label: `SPL Max (${unit})`,
                    data: dataMax,
                    borderColor: '#ee0000',
                    backgroundColor: 'transparent',
                    tension: 0.3,
                    fill: false,
                    pointRadius: 0,
                    borderWidth: 1,
                    borderDash: [4, 4]
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            scales: {
                y: {
                    min: yMin,
                    max: yMax,
                    title: { display: true, text: unit, font: { size: 12 } }
                },
                x: {
                    ticks: {
                        maxTicksLimit: 12,
                        maxRotation: 0,
                        font: { size: 11 }
                    }
                }
            },
            plugins: {
                legend: { display: true, position: 'top', labels: { boxWidth: 12, font: { size: 12 } } },
                tooltip: {
                    backgroundColor: '#171717',
                    titleFont: { size: 13 },
                    bodyFont: { size: 12 },
                    padding: 12,
                    cornerRadius: 6,
                    callbacks: {
                        title: function(context) {
                            return context[0].label;
                        },
                        afterBody: function(context) {
                            const idx = context[0].dataIndex;
                            const m = reversed[idx];
                            if (!m) return '';
                            const lines = [];
                            lines.push('Weighting: ' + getWeightingLabel(m.weighting));
                            lines.push('Status: ' + (m.status || 'ok'));
                            lines.push('Quality: ' + formatQualityFlags(m.quality_flags));
                            return lines;
                        }
                    }
                }
            }
        }
    });

    // Table
    const tbody = document.getElementById('live-table-body');
    tbody.innerHTML = '';
    const displayCount = Math.min(10, measurements.length);
    for (let i = 0; i < displayCount; i++) {
        const m = measurements[i];
        const vAvg = m.spl_avg_db != null ? m.spl_avg_db : m.total_dba;
        const vMax = m.spl_max_db != null ? m.spl_max_db : vAvg;
        const rowUnit = getUnit(m.weighting);
        const qText = formatQualityFlags(m.quality_flags);
        const qClass = qualityFlagsBadgeClass(m.quality_flags);

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${formatDateTime(m.measured_at)}</td>
            <td><code>${m.device_id || '-'}</code></td>
            <td>${m.room || '-'}</td>
            <td>${vAvg != null ? vAvg.toFixed(1) + ' ' + rowUnit : '--'}</td>
            <td>${vMax != null ? vMax.toFixed(1) + ' ' + rowUnit : '--'}</td>
            <td>${getWeightingLabel(m.weighting)}</td>
            <td><span class="badge ${m.status === 'error' ? 'error' : 'ok'}">${m.status || 'ok'}</span></td>
            <td><span class="badge ${qClass}">${qText}</span></td>
            <td>${m.edge_version || 'Not reported'}</td>
        `;
        tbody.appendChild(row);
    }
}

// =============================================
// DEVICES TAB
// =============================================

async function loadDevices() {
    const data = await apiFetch('/api/devices');
    if (data && data.devices) {
        state.devices = data.devices;
        const selector = document.getElementById('global-device-selector');
        selector.innerHTML = '<option value="">All Devices</option>';
        state.devices.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.device_id;
            opt.textContent = `${d.device_id} (${d.room || '-'})`;
            selector.appendChild(opt);
        });
    }
}

async function loadDevicesView() {
    const tbody = document.getElementById('devices-table-body');
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Loading…</td></tr>';

    const data = await apiFetch('/api/devices');
    if (!data || !data.devices) return;

    tbody.innerHTML = '';
    if (data.devices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No devices registered.</td></tr>';
        return;
    }

    data.devices.forEach(d => {
        const row = document.createElement('tr');
        const healthClass = d.health_status === 'online' ? 'ok' :
                            d.health_status === 'error' ? 'error' :
                            d.health_status === 'offline' ? 'stale' : '';
        row.innerHTML = `
            <td><code>${d.device_id}</code></td>
            <td>${d.room || '-'} / ${d.location || '-'}</td>
            <td><span class="badge ${healthClass}">${d.health_status || 'Unknown'}</span></td>
            <td>${formatDateTime(d.last_seen)}</td>
            <td>${d.description || '-'}</td>
        `;
        tbody.appendChild(row);
    });
}

// =============================================
// HISTORY TAB
// =============================================

async function searchHistory() {
    const startDate = document.getElementById('hist-start-date').value;
    const startTime = document.getElementById('hist-start-time').value || '00:00';
    const endDate = document.getElementById('hist-end-date').value;
    const endTime = document.getElementById('hist-end-time').value || '23:59';
    const limit = document.getElementById('hist-limit').value;

    if (!startDate || !endDate) {
        alert("Please select start and end dates.");
        return;
    }

    const startIso = new Date(`${startDate}T${startTime}:00`).toISOString();
    const endIso = new Date(`${endDate}T${endTime}:59`).toISOString();

    const params = new URLSearchParams({
        start: startIso,
        end: endIso,
        limit: limit
    });
    if (state.selectedDeviceId) {
        params.set('device_id', state.selectedDeviceId);
    }

    document.getElementById('hist-table-body').innerHTML = '<tr><td colspan="9" style="text-align:center;">Loading…</td></tr>';

    const data = await apiFetch(`/api/measurements?${params.toString()}`);
    if (!data) return;

    renderHistoryView(data);
}

function renderHistoryView(measurements) {
    const tbody = document.getElementById('hist-table-body');
    tbody.innerHTML = '';

    if (!measurements || measurements.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;">No data found for this range.</td></tr>';
        document.getElementById('hist-summary').classList.add('hidden');
        document.getElementById('hist-chart-empty').classList.remove('hidden');
        if (state.histChartInstance) state.histChartInstance.destroy();
        return;
    }

    document.getElementById('hist-summary').classList.remove('hidden');
    document.getElementById('hist-chart-empty').classList.add('hidden');

    let sum = 0;
    let max = 0;
    let validCount = 0;

    measurements.forEach(m => {
        const vAvg = m.spl_avg_db != null ? m.spl_avg_db : m.total_dba;
        const vMax = m.spl_max_db != null ? m.spl_max_db : vAvg;
        const rowUnit = getUnit(m.weighting);
        const qText = formatQualityFlags(m.quality_flags);
        const qClass = qualityFlagsBadgeClass(m.quality_flags);

        if (vAvg != null) {
            sum += vAvg;
            validCount++;
        }
        if (vMax != null && vMax > max) max = vMax;

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${formatDateTime(m.measured_at)}</td>
            <td><code>${m.device_id || '-'}</code></td>
            <td>${m.room || '-'}</td>
            <td>${vAvg != null ? vAvg.toFixed(1) + ' ' + rowUnit : '--'}</td>
            <td>${vMax != null ? vMax.toFixed(1) + ' ' + rowUnit : '--'}</td>
            <td>${getWeightingLabel(m.weighting)}</td>
            <td><span class="badge ${m.status === 'error' ? 'error' : 'ok'}">${m.status || 'ok'}</span></td>
            <td><span class="badge ${qClass}">${qText}</span></td>
            <td>${m.edge_version || 'Not reported'}</td>
        `;
        tbody.appendChild(row);
    });

    // Determine dominant unit
    const dominantUnit = measurements.length > 0 ? getUnit(measurements[0].weighting) : 'dB';
    document.getElementById('hist-avg-spl').textContent = validCount > 0 ? (sum / validCount).toFixed(1) + ' ' + dominantUnit : '--';
    document.getElementById('hist-max-spl').textContent = max > 0 ? max.toFixed(1) + ' ' + dominantUnit : '--';
    document.getElementById('hist-count').textContent = measurements.length;

    // Chart
    const reversed = [...measurements].reverse();
    const labels = reversed.map(m => new Date(m.measured_at).toLocaleString());
    const dataAvg = reversed.map(m => m.spl_avg_db != null ? m.spl_avg_db : m.total_dba);

    const allVals = dataAvg.filter(v => v != null);
    const yMin = allVals.length > 0 ? Math.floor(Math.min(...allVals) - 5) : 30;
    const yMax = allVals.length > 0 ? Math.ceil(Math.max(...allVals) + 5) : 120;

    const ctx = document.getElementById('hist-chart').getContext('2d');
    if (state.histChartInstance) state.histChartInstance.destroy();

    state.histChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: `SPL Avg (${dominantUnit})`,
                data: dataAvg,
                borderColor: '#0070f3',
                backgroundColor: 'rgba(0, 112, 243, 0.08)',
                tension: 0.3,
                fill: true,
                pointRadius: 0,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: {
                    min: yMin,
                    max: yMax,
                    title: { display: true, text: dominantUnit, font: { size: 12 } }
                },
                x: {
                    ticks: {
                        maxTicksLimit: 10,
                        maxRotation: 0,
                        font: { size: 11 }
                    }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#171717',
                    titleFont: { size: 13 },
                    bodyFont: { size: 12 },
                    padding: 12,
                    cornerRadius: 6,
                    callbacks: {
                        afterBody: function(context) {
                            const idx = context[0].dataIndex;
                            const m = reversed[idx];
                            if (!m) return '';
                            return [
                                'Weighting: ' + getWeightingLabel(m.weighting),
                                'Quality: ' + formatQualityFlags(m.quality_flags)
                            ];
                        }
                    }
                }
            }
        }
    });
}

// =============================================
// CSV EXPORT
// =============================================

function downloadCsv() {
    const startDate = document.getElementById('hist-start-date').value;
    const startTime = document.getElementById('hist-start-time').value || '00:00';
    const endDate = document.getElementById('hist-end-date').value;
    const endTime = document.getElementById('hist-end-time').value || '23:59';
    const limit = document.getElementById('hist-limit').value;

    if (!startDate || !endDate) {
        alert("Please select start and end dates.");
        return;
    }

    const startIso = new Date(`${startDate}T${startTime}:00`).toISOString();
    const endIso = new Date(`${endDate}T${endTime}:59`).toISOString();

    const params = new URLSearchParams({
        start: startIso,
        end: endIso,
        limit: limit
    });

    if (state.selectedDeviceId) {
        params.set("device_id", state.selectedDeviceId);
    }

    // We need auth token for the CSV download too
    const token = getToken();
    const url = `${API_BASE_URL}/api/measurements/export.csv?${params.toString()}`;

    // Use fetch + blob for authenticated download
    fetch(url, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {}
    })
    .then(resp => {
        if (resp.status === 401) {
            clearToken();
            showLogin();
            return null;
        }
        if (!resp.ok) throw new Error('Export failed');
        return resp.blob();
    })
    .then(blob => {
        if (!blob) return;
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `acoustic_export_${startDate}_${endDate}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(a.href);
    })
    .catch(err => {
        console.error('CSV download error:', err);
        alert('CSV download failed. Check your connection.');
    });
}

// =============================================
// REPORT TAB
// =============================================

async function generateReportSummary() {
    const startLocal = document.getElementById('report-start').value;
    const endLocal = document.getElementById('report-end').value;

    if (!startLocal || !endLocal) {
        alert("Please select both start and end times.");
        return;
    }

    const startIso = new Date(startLocal).toISOString();
    const endIso = new Date(endLocal).toISOString();

    const params = new URLSearchParams({
        start: startIso,
        end: endIso
    });
    if (state.selectedDeviceId) {
        params.set('device_id', state.selectedDeviceId);
    }

    const output = document.getElementById('report-output');
    output.classList.add('hidden');

    const data = await apiFetch(`/api/reports/summary?${params.toString()}`);
    if (!data || data.sample_count === 0) {
        alert("No data available for this range.");
        return;
    }

    // Determine unit from weighting distribution
    let reportUnit = 'dB';
    if (data.weighting_dist) {
        const aCount = data.weighting_dist['A'] || 0;
        const total = Object.values(data.weighting_dist).reduce((a, b) => a + b, 0);
        if (aCount > total / 2) reportUnit = 'dBA';
    }

    document.getElementById('report-threshold-count').textContent = data.above_threshold_count;
    document.getElementById('report-min').textContent = data.min_spl + ' ' + reportUnit;
    document.getElementById('report-max').textContent = data.max_spl + ' ' + reportUnit;
    document.getElementById('report-avg').textContent = data.avg_spl + ' ' + reportUnit;
    document.getElementById('report-plain-text').textContent = data.plain_summary;

    const peaksList = document.getElementById('report-peaks');
    peaksList.innerHTML = '';
    if (data.peak_times && data.peak_times.length > 0) {
        data.peak_times.forEach(p => {
            const li = document.createElement('li');
            li.innerHTML = `<strong>${p.spl_max_db} ${reportUnit}</strong> at ${formatDateTime(p.measured_at)}`;
            peaksList.appendChild(li);
        });
    } else {
        peaksList.innerHTML = '<li>None</li>';
    }

    const anomaliesList = document.getElementById('report-anomalies');
    anomaliesList.innerHTML = '';
    if (data.anomalies && data.anomalies.length > 0) {
        data.anomalies.forEach(a => {
            const li = document.createElement('li');
            li.innerHTML = `<code>${formatDateTime(a.measured_at)}</code>: ${a.reason}`;
            anomaliesList.appendChild(li);
        });
    } else {
        anomaliesList.innerHTML = '<li>None</li>';
    }

    const wList = document.getElementById('report-weighting');
    wList.innerHTML = '';
    if (data.weighting_dist) {
        Object.entries(data.weighting_dist).forEach(([k, v]) => {
            wList.innerHTML += `<li>${getWeightingLabel(k)}: <strong>${v}</strong> samples</li>`;
        });
    } else {
        wList.innerHTML = '<li>No data</li>';
    }

    const sList = document.getElementById('report-status');
    sList.innerHTML = '';
    if (data.status_dist) {
        Object.entries(data.status_dist).forEach(([k, v]) => {
            sList.innerHTML += `<li>${k}: <strong>${v}</strong> samples</li>`;
        });
    } else {
        sList.innerHTML = '<li>No data</li>';
    }

    const qList = document.getElementById('report-quality');
    qList.innerHTML = '';
    if (data.quality_dist && Object.keys(data.quality_dist).length > 0) {
        Object.entries(data.quality_dist).forEach(([k, v]) => {
            qList.innerHTML += `<li>${k}: <strong>${v}</strong> samples</li>`;
        });
    } else {
        qList.innerHTML = '<li>None — all samples reported normal quality</li>';
    }

    output.classList.remove('hidden');
    window.lastReportData = data;
    document.getElementById('btn-generate-ai').disabled = false;
    document.getElementById('llm-output').classList.add('hidden');
    document.getElementById('llm-quota-badge').textContent = `Role: ${localStorage.getItem('acoustic_role')}`;
}

// =============================================
// AI GENERATION
// =============================================

async function generateAiReport() {
    if (!window.lastReportData) return;
    
    const btn = document.getElementById('btn-generate-ai');
    const loading = document.getElementById('llm-loading');
    const output = document.getElementById('llm-output');
    
    btn.disabled = true;
    loading.classList.remove('hidden');
    output.classList.add('hidden');
    
    const url = `${API_BASE_URL}/api/reports/generate-ai`;
    const token = getToken();
    
    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}` 
            },
            body: JSON.stringify({ summary_data: window.lastReportData })
        });
        
        const data = await resp.json();
        
        if (!resp.ok) {
            throw new Error(data.detail || 'Failed to generate report');
        }
        
        output.textContent = data.report;
        document.getElementById('llm-quota-badge').textContent = `Quota Used: ${data.used_quota} / ${data.max_quota}`;
        
    } catch (err) {
        output.textContent = `Error: ${err.message}`;
    } finally {
        loading.classList.add('hidden');
        output.classList.remove('hidden');
        btn.disabled = false;
    }
}

// =============================================
// ADMIN CONFIGURATION
// =============================================

async function loadAdminUsers() {
    const data = await apiFetch('/api/users');
    if (!data) return;
    
    const tbody = document.getElementById('admin-users-body');
    tbody.innerHTML = '';
    
    data.users.forEach(u => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${u.username}</td>
            <td>${u.display_name || '-'}</td>
            <td>
                <select onchange="updateUser('${u.username}', 'role', this.value)">
                    <option value="viewer" ${u.role==='viewer'?'selected':''}>Viewer</option>
                    <option value="supervisor" ${u.role==='supervisor'?'selected':''}>Supervisor</option>
                    <option value="admin" ${u.role==='admin'?'selected':''}>Admin</option>
                </select>
            </td>
            <td>
                <input type="checkbox" ${u.is_active ? 'checked' : ''} onchange="updateUser('${u.username}', 'is_active', this.checked)">
            </td>
            <td>${formatDateTime(u.last_login)}</td>
            <td>
                <button class="btn-secondary" style="padding: 2px 8px; font-size: 11px;" onclick="promptEditDisplayName('${u.username}', '${u.display_name||''}')">Rename</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

async function handleAddUser(e) {
    e.preventDefault();
    const username = document.getElementById('add-username').value;
    const display_name = document.getElementById('add-display-name').value;
    const password = document.getElementById('add-password').value;
    const role = document.getElementById('add-role').value;
    
    const token = getToken();
    try {
        const resp = await fetch(`${API_BASE_URL}/api/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ username, password, display_name, role })
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail);
        
        alert("User added successfully.");
        document.getElementById('add-user-form').reset();
        loadAdminUsers();
    } catch (err) {
        alert("Error adding user: " + err.message);
    }
}

async function updateUser(username, field, value) {
    const token = getToken();
    const payload = {};
    payload[field] = value;
    
    try {
        const resp = await fetch(`${API_BASE_URL}/api/users/${username}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify(payload)
        });
        if (!resp.ok) throw new Error("Update failed");
    } catch (err) {
        alert(err.message);
        loadAdminUsers(); // revert UI on failure
    }
}

function promptEditDisplayName(username, current) {
    const newName = prompt("Enter new display name for " + username, current);
    if (newName !== null) {
        updateUser(username, 'display_name', newName).then(() => loadAdminUsers());
    }
}

async function loadAdminDevices() {
    const data = await apiFetch('/api/devices');
    if (!data) return;
    
    const select = document.getElementById('admin-device-select');
    select.innerHTML = '<option value="">Select...</option>';
    data.devices.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.device_id;
        opt.textContent = d.device_id;
        opt.dataset.room = d.room || '';
        opt.dataset.location = d.location || '';
        opt.dataset.description = d.description || '';
        select.appendChild(opt);
    });
}

function loadAdminDevice(deviceId) {
    const form = document.getElementById('edit-device-form');
    if (!deviceId) {
        form.classList.add('hidden');
        return;
    }
    const opt = document.querySelector(`#admin-device-select option[value="${deviceId}"]`);
    document.getElementById('edit-device-room').value = opt.dataset.room;
    document.getElementById('edit-device-location').value = opt.dataset.location;
    document.getElementById('edit-device-description').value = opt.dataset.description;
    form.classList.remove('hidden');
}

async function handleEditDevice(e) {
    e.preventDefault();
    const deviceId = document.getElementById('admin-device-select').value;
    if (!deviceId) return;
    
    const room = document.getElementById('edit-device-room').value;
    const location = document.getElementById('edit-device-location').value;
    const description = document.getElementById('edit-device-description').value;
    
    const token = getToken();
    try {
        const resp = await fetch(`${API_BASE_URL}/api/devices/${deviceId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ room, location, description })
        });
        if (!resp.ok) throw new Error("Failed to update device");
        alert("Device updated.");
        loadAdminDevices(); // refresh select data
    } catch (err) {
        alert(err.message);
    }
}
