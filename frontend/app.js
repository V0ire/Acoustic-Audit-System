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

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    init();
});

async function init() {
    await loadDevices();
    
    document.getElementById('global-device-selector').addEventListener('change', (e) => {
        state.selectedDeviceId = e.target.value;
        refreshCurrentTab();
    });

    // Default dates for history/report
    const today = new Date();
    const todayLocal = today.toISOString().split('T')[0] + 'T00:00';
    
    document.getElementById('hist-start-date').value = today.toISOString().split('T')[0];
    document.getElementById('hist-end-date').value = today.toISOString().split('T')[0];
    document.getElementById('report-start').value = todayLocal;
    document.getElementById('report-end').value = todayLocal;

    // Add event listeners to nav tabs
    document.querySelectorAll(".nav-tab").forEach(tab => {
        tab.addEventListener("click", () => switchView(tab.dataset.view));
    });

    switchView('live');
}

function switchView(viewName) {
    state.activeTab = viewName;
    
    // UI Update
    document.querySelectorAll(".view").forEach(view => {
        view.classList.remove("active");
    });

    document.querySelector(`#view-${viewName}`).classList.add("active");

    document.querySelectorAll(".nav-tab").forEach(tab => {
        tab.classList.toggle("active", tab.dataset.view === viewName);
    });

    // Logic Update
    if (state.refreshInterval) {
        clearInterval(state.refreshInterval);
        state.refreshInterval = null;
    }

    if (viewName === "live") {
        loadLiveMeasurements();
        state.refreshInterval = setInterval(loadLiveMeasurements, 5000);
    }
    
    if (viewName === "history") {
        // prepare history view if needed
    }
    
    if (viewName === "devices") {
        loadDevicesView();
    }
    
    if (viewName === "report") {
        // prepare report view if needed
    }
}

function refreshCurrentTab() {
    if (state.activeTab === 'live') {
        loadLiveMeasurements();
    } else if (state.activeTab === 'devices') {
        loadDevicesView();
    }
}

// --- API Helpers ---
async function apiFetch(path) {
    const url = `${API_BASE_URL}${path}`;
    try {
        const response = await fetch(url);
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

// --- Live Tab ---
async function loadLiveMeasurements() {
    const statusBadge = document.getElementById('api-status');
    statusBadge.textContent = 'Syncing...';
    
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

function renderLiveView(measurements) {
    if (!measurements || measurements.length === 0) {
        document.getElementById('live-spl-avg').textContent = '--';
        document.getElementById('live-spl-max').textContent = '--';
        return;
    }

    const latest = measurements[0];
    const avgSpl = latest.spl_avg_db !== null ? latest.spl_avg_db : latest.total_dba;
    const maxSpl = latest.spl_max_db !== null ? latest.spl_max_db : avgSpl;

    document.getElementById('live-spl-avg').textContent = avgSpl ? avgSpl.toFixed(1) : '--';
    document.getElementById('live-spl-max').textContent = maxSpl ? maxSpl.toFixed(1) : '--';
    document.getElementById('live-cal-offset').textContent = latest.calibration_offset_db || '0';
    document.getElementById('live-weighting').textContent = latest.weighting || 'unknown';
    document.getElementById('live-edge-version').textContent = latest.edge_version || '-';
    document.getElementById('live-last-seen').textContent = formatDateTime(latest.measured_at);
    
    // Quality flags
    let flagsStr = '-';
    if (latest.quality_flags) {
        try {
            const flags = typeof latest.quality_flags === 'string' ? JSON.parse(latest.quality_flags) : latest.quality_flags;
            const flagKeys = Object.keys(flags).filter(k => flags[k]);
            if (flagKeys.length > 0) {
                flagsStr = flagKeys.join(', ');
            }
        } catch (e) {}
    }
    const qEl = document.getElementById('live-quality-flags');
    qEl.textContent = flagsStr;
    qEl.className = flagsStr !== '-' ? 'badge error' : 'badge ok';
    
    const statusEl = document.getElementById('live-status');
    // Check stale (older than 120s)
    const now = new Date();
    const lastSeen = new Date(latest.measured_at);
    const diffSecs = (now - lastSeen) / 1000;
    
    if (diffSecs > 120) {
        statusEl.textContent = 'Stale';
        statusEl.className = 'badge stale';
    } else {
        statusEl.textContent = latest.status || 'OK';
        statusEl.className = latest.status === 'error' ? 'badge error' : 'badge ok';
    }

    // Chart
    const labels = [...measurements].reverse().map(m => new Date(m.measured_at).toLocaleTimeString());
    const dataAvg = [...measurements].reverse().map(m => m.spl_avg_db !== null ? m.spl_avg_db : m.total_dba);
    
    const ctx = document.getElementById('live-chart').getContext('2d');
    if (state.liveChartInstance) {
        state.liveChartInstance.destroy();
    }
    
    state.liveChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'SPL Avg (dB)',
                data: dataAvg,
                borderColor: '#171717',
                backgroundColor: 'rgba(23, 23, 23, 0.1)',
                tension: 0.2,
                fill: true,
                pointRadius: 0,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                y: { min: 30, max: 120 }
            },
            plugins: { legend: { display: false } }
        }
    });

    // Table
    const tbody = document.getElementById('live-table-body');
    tbody.innerHTML = '';
    const displayCount = Math.min(10, measurements.length);
    for (let i = 0; i < displayCount; i++) {
        const m = measurements[i];
        const row = document.createElement('tr');
        const vAvg = m.spl_avg_db !== null ? m.spl_avg_db : m.total_dba;
        const vMax = m.spl_max_db !== null ? m.spl_max_db : vAvg;
        
        let rowFlagsStr = '-';
        if (m.quality_flags) {
            try {
                const flags = typeof m.quality_flags === 'string' ? JSON.parse(m.quality_flags) : m.quality_flags;
                const flagKeys = Object.keys(flags).filter(k => flags[k]);
                if (flagKeys.length > 0) rowFlagsStr = flagKeys.join(', ');
            } catch (e) {}
        }
        
        row.innerHTML = `
            <td>${formatDateTime(m.measured_at)}</td>
            <td><code>${m.device_id}</code></td>
            <td>${m.room || '-'}</td>
            <td>${vAvg ? vAvg.toFixed(1) : '--'}</td>
            <td>${vMax ? vMax.toFixed(1) : '--'}</td>
            <td>${m.weighting || 'unknown'}</td>
            <td><span class="badge ${m.status === 'error' ? 'error' : 'ok'}">${m.status || 'ok'}</span></td>
            <td>${rowFlagsStr}</td>
            <td>${m.edge_version || '-'}</td>
        `;
        tbody.appendChild(row);
    }
}

// --- Devices Tab ---
async function loadDevices() {
    const data = await apiFetch('/api/devices');
    if (data && data.devices) {
        state.devices = data.devices;
        const selector = document.getElementById('global-device-selector');
        selector.innerHTML = '<option value="">All Devices</option>';
        state.devices.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d.device_id;
            opt.textContent = `${d.device_id} (${d.room})`;
            selector.appendChild(opt);
        });
    }
}

async function loadDevicesView() {
    const tbody = document.getElementById('devices-table-body');
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">Loading...</td></tr>';
    
    const data = await apiFetch('/api/devices');
    if (!data || !data.devices) return;
    
    tbody.innerHTML = '';
    data.devices.forEach(d => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><code>${d.device_id}</code></td>
            <td>${d.room} / ${d.location || '--'}</td>
            <td><span class="badge ${d.health_status === 'error' ? 'error' : 'ok'}">${d.health_status || 'Unknown'}</span></td>
            <td>${formatDateTime(d.last_seen)}</td>
            <td>${d.description || '--'}</td>
        `;
        tbody.appendChild(row);
    });
}

// --- History Tab ---
async function searchHistory() {
    const startDate = document.getElementById('hist-start-date').value;
    const startTime = document.getElementById('hist-start-time').value;
    const endDate = document.getElementById('hist-end-date').value;
    const endTime = document.getElementById('hist-end-time').value;
    const limit = document.getElementById('hist-limit').value;

    if (!startDate || !endDate) {
        alert("Please select start and end dates.");
        return;
    }

    const startIso = new Date(`${startDate}T${startTime}:00`).toISOString();
    const endIso = new Date(`${endDate}T${endTime}:59`).toISOString();

    let path = `/api/measurements?start=${startIso}&end=${endIso}&limit=${limit}`;
    if (state.selectedDeviceId) {
        path += `&device_id=${encodeURIComponent(state.selectedDeviceId)}`;
    }

    document.getElementById('hist-table-body').innerHTML = '<tr><td colspan="3" style="text-align:center;">Loading...</td></tr>';
    
    const data = await apiFetch(path);
    if (!data) return;

    renderHistoryView(data);
}

function renderHistoryView(measurements) {
    const tbody = document.getElementById('hist-table-body');
    tbody.innerHTML = '';

    if (!measurements || measurements.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;">No data found for this range.</td></tr>';
        document.getElementById('hist-summary').classList.add('hidden');
        if (state.histChartInstance) state.histChartInstance.destroy();
        return;
    }

    document.getElementById('hist-summary').classList.remove('hidden');

    let sum = 0;
    let max = 0;
    let validCount = 0;

    measurements.forEach(m => {
        const vAvg = m.spl_avg_db !== null ? m.spl_avg_db : m.total_dba;
        const vMax = m.spl_max_db !== null ? m.spl_max_db : vAvg;
        
        if (vAvg !== null) {
            sum += vAvg;
            validCount++;
        }
        if (vMax !== null && vMax > max) max = vMax;

        let rowFlagsStr = '-';
        if (m.quality_flags) {
            try {
                const flags = typeof m.quality_flags === 'string' ? JSON.parse(m.quality_flags) : m.quality_flags;
                const flagKeys = Object.keys(flags).filter(k => flags[k]);
                if (flagKeys.length > 0) rowFlagsStr = flagKeys.join(', ');
            } catch (e) {}
        }

        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${formatDateTime(m.measured_at)}</td>
            <td><code>${m.device_id}</code></td>
            <td>${m.room || '-'}</td>
            <td>${vAvg ? vAvg.toFixed(1) : '--'}</td>
            <td>${vMax ? vMax.toFixed(1) : '--'}</td>
            <td>${m.weighting || 'unknown'}</td>
            <td><span class="badge ${m.status === 'error' ? 'error' : 'ok'}">${m.status || 'ok'}</span></td>
            <td>${rowFlagsStr}</td>
            <td>${m.edge_version || '-'}</td>
        `;
        tbody.appendChild(row);
    });

    document.getElementById('hist-avg-spl').textContent = validCount > 0 ? (sum / validCount).toFixed(1) + ' dB' : '--';
    document.getElementById('hist-max-spl').textContent = max > 0 ? max.toFixed(1) + ' dB' : '--';
    document.getElementById('hist-count').textContent = measurements.length;

    // Chart
    const labels = [...measurements].reverse().map(m => new Date(m.measured_at).toLocaleString());
    const dataAvg = [...measurements].reverse().map(m => m.spl_avg_db !== null ? m.spl_avg_db : m.total_dba);
    
    const ctx = document.getElementById('hist-chart').getContext('2d');
    if (state.histChartInstance) {
        state.histChartInstance.destroy();
    }
    
    state.histChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'SPL Avg (dB)',
                data: dataAvg,
                borderColor: '#0070f3',
                backgroundColor: 'rgba(0, 112, 243, 0.1)',
                tension: 0.2,
                fill: true,
                pointRadius: 0,
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { min: 30, max: 120 } },
            plugins: { legend: { display: false } }
        }
    });
}

// --- Export CSV ---
function downloadCsv() {
    const startDate = document.getElementById('hist-start-date').value;
    const startTime = document.getElementById('hist-start-time').value || '00:00';
    const endDate = document.getElementById('hist-end-date').value;
    const endTime = document.getElementById('hist-end-time').value || '23:59';

    if (!startDate || !endDate) {
        alert("Please select start and end dates.");
        return;
    }

    const startIso = new Date(`${startDate}T${startTime}:00`).toISOString();
    const endIso = new Date(`${endDate}T${endTime}:59`).toISOString();

    const params = new URLSearchParams({
        start: startIso,
        end: endIso
    });

    if (state.selectedDeviceId) {
        params.set("device_id", state.selectedDeviceId);
    }

    const url = `${API_BASE_URL}/api/measurements/export.csv?${params.toString()}`;
    window.location.href = url;
}

// --- Report Tab ---
async function generateReportSummary() {
    const startLocal = document.getElementById('report-start').value;
    const endLocal = document.getElementById('report-end').value;

    if (!startLocal || !endLocal) {
        alert("Please select both start and end times.");
        return;
    }

    const startIso = new Date(startLocal).toISOString();
    const endIso = new Date(endLocal).toISOString();

    let path = `/api/reports/summary?start=${startIso}&end=${endIso}`;
    if (state.selectedDeviceId) {
        path += `&device_id=${encodeURIComponent(state.selectedDeviceId)}`;
    }

    const output = document.getElementById('report-output');
    output.classList.add('hidden');

    const data = await apiFetch(path);
    if (!data || data.sample_count === 0) {
        alert("No data available for this range.");
        return;
    }

    document.getElementById('report-threshold-count').textContent = data.above_threshold_count;
    document.getElementById('report-min').textContent = data.min_spl + ' dB';
    document.getElementById('report-max').textContent = data.max_spl + ' dB';
    document.getElementById('report-avg').textContent = data.avg_spl + ' dB';
    document.getElementById('report-plain-text').textContent = data.plain_summary;

    const peaksList = document.getElementById('report-peaks');
    peaksList.innerHTML = '';
    data.peak_times.forEach(p => {
        const li = document.createElement('li');
        li.innerHTML = `<strong>${p.spl_max_db} dB</strong> at ${formatDateTime(p.measured_at)}`;
        peaksList.appendChild(li);
    });

    const anomaliesList = document.getElementById('report-anomalies');
    anomaliesList.innerHTML = '';
    data.anomalies.forEach(a => {
        const li = document.createElement('li');
        li.innerHTML = `<code>${formatDateTime(a.measured_at)}</code>: ${a.reason}`;
        anomaliesList.appendChild(li);
    });
    
    const wList = document.getElementById('report-weighting');
    wList.innerHTML = '';
    if (data.weighting_dist) {
        Object.entries(data.weighting_dist).forEach(([k, v]) => {
            wList.innerHTML += `<li>${k}: <strong>${v}</strong> samples</li>`;
        });
    }

    const sList = document.getElementById('report-status');
    sList.innerHTML = '';
    if (data.status_dist) {
        Object.entries(data.status_dist).forEach(([k, v]) => {
            sList.innerHTML += `<li>${k}: <strong>${v}</strong> samples</li>`;
        });
    }

    const qList = document.getElementById('report-quality');
    qList.innerHTML = '';
    if (data.quality_dist && Object.keys(data.quality_dist).length > 0) {
        Object.entries(data.quality_dist).forEach(([k, v]) => {
            qList.innerHTML += `<li>${k}: <strong>${v}</strong> samples</li>`;
        });
    } else {
        qList.innerHTML = '<li>None</li>';
    }

    output.classList.remove('hidden');
}
