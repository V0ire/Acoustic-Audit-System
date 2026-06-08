const API_BASE = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1') 
    ? 'http://localhost:8000/api' 
    : '/api'; // fallback for production nginx reverse proxy

// --- State Variables ---
let chartInstance = null;
let pollInterval = null;

// --- UI Elements ---
const loginView = document.getElementById('login-view');
const dashboardView = document.getElementById('dashboard-view');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const logoutBtn = document.getElementById('logout-btn');

// Metrics
const metricDba = document.getElementById('metric-dba');
const metricMechanical = document.getElementById('metric-mechanical');
const metricHuman = document.getElementById('metric-human');
const progressMechanical = document.getElementById('progress-mechanical');
const progressHuman = document.getElementById('progress-human');
const roomId = document.getElementById('room-id');
const complianceBadge = document.getElementById('compliance-badge');

// Status & Indicators
const statusText = document.getElementById('status-text');
const connectionStatus = document.getElementById('connection-status');
const staleWarning = document.getElementById('stale-warning');
const lastSeenWarning = document.getElementById('last-seen-warning');
const lastSeenFooter = document.getElementById('last-seen-footer');
const measurementsTbody = document.getElementById('measurements-tbody');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('acoustic_jwt');
    if (token) {
        showDashboard();
    } else {
        showLogin();
    }
});

// --- Auth Functions ---
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = loginForm.username.value;
    const password = loginForm.password.value;
    const btn = loginForm.querySelector('button[type="submit"]');

    btn.textContent = 'Memverifikasi...';
    btn.disabled = true;
    loginError.classList.add('hidden');

    try {
        const response = await fetch(`${API_BASE}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });

        if (!response.ok) {
            throw new Error('Kredensial salah');
        }

        const data = await response.json();
        localStorage.setItem('acoustic_jwt', data.token);
        loginForm.reset();
        showDashboard();
    } catch (err) {
        loginError.classList.remove('hidden');
    } finally {
        btn.textContent = 'Log In';
        btn.disabled = false;
    }
});

logoutBtn.addEventListener('click', () => {
    localStorage.removeItem('acoustic_jwt');
    stopPolling();
    showLogin();
});

// --- View Toggles ---
function showLogin() {
    dashboardView.classList.add('hidden');
    loginView.classList.remove('hidden');
}

function showDashboard() {
    loginView.classList.add('hidden');
    dashboardView.classList.remove('hidden');
    initChart();
    fetchData(); // first fetch
    startPolling();
}

// --- Data Fetching ---
function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(fetchData, 5000); // 5 detik sesuai kontrak
}

function stopPolling() {
    if (pollInterval) clearInterval(pollInterval);
}

async function fetchData() {
    const token = localStorage.getItem('acoustic_jwt');
    if (!token) return showLogin();

    try {
        const response = await fetch(`${API_BASE}/measurements`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.status === 401) {
            // Token expired or invalid
            logoutBtn.click();
            return;
        }

        if (!response.ok) throw new Error('Network error');

        const data = await response.json();
        updateDashboard(data);
        updateConnectionStatus(true);
    } catch (err) {
        console.error("Fetch error:", err);
        updateConnectionStatus(false);
    }
}

// --- UI Updates ---
function updateDashboard(data) {
    if (!data || data.length === 0) {
        showEmptyState();
        return;
    }

    const latest = data[0];
    
    // Update metrics
    metricDba.textContent = latest.total_dba.toFixed(1);
    const mechConf = (latest.mechanical_confidence * 100).toFixed(0);
    const humConf = (latest.human_activity_confidence * 100).toFixed(0);
    
    metricMechanical.textContent = mechConf;
    metricHuman.textContent = humConf;
    progressMechanical.style.width = `${mechConf}%`;
    progressHuman.style.width = `${humConf}%`;
    roomId.textContent = latest.room || '-';

    // Compliance Badge Logic
    updateComplianceBadge(latest.total_dba);

    // Stale indicator check (120 seconds)
    const measuredAt = new Date(latest.measured_at);
    const now = new Date();
    const diffSeconds = (now - measuredAt) / 1000;
    
    const timeString = measuredAt.toLocaleTimeString('id-ID');
    const lastSeenText = `Last seen: ${timeString}`;
    lastSeenFooter.textContent = lastSeenText;

    if (diffSeconds > 120) {
        staleWarning.classList.remove('hidden');
        lastSeenWarning.textContent = lastSeenText;
    } else {
        staleWarning.classList.add('hidden');
    }

    // Update Table
    updateTable(data.slice(0, 10)); // max 10 rows

    // Update Chart
    updateChart(data);
}

function updateComplianceBadge(dba) {
    // total_dba < 55 -> Normal
    // total_dba < 65 -> Warning
    // total_dba >= 65 -> High Noise Exposure
    
    complianceBadge.className = 'px-2.5 py-0.5 rounded-full text-[10px] font-mono font-medium';
    
    if (dba < 55) {
        complianceBadge.textContent = 'NORMAL';
        complianceBadge.classList.add('bg-[#d3e5ff]', 'text-[#0761d1]');
    } else if (dba < 65) {
        complianceBadge.textContent = 'WARNING';
        complianceBadge.classList.add('bg-[#ffefcf]', 'text-[#ab570a]');
    } else {
        complianceBadge.textContent = 'HIGH NOISE';
        complianceBadge.classList.add('bg-[#f7d4d6]', 'text-[#c50000]');
    }
}

function updateConnectionStatus(isOnline) {
    if (isOnline) {
        statusText.textContent = 'ONLINE';
        connectionStatus.className = 'flex items-center gap-1.5 px-2 py-1 rounded-full bg-[#d3e5ff] text-[#0761d1] text-xs font-mono';
        connectionStatus.querySelector('span').className = 'h-2 w-2 rounded-full bg-[#0070f3] animate-pulse';
    } else {
        statusText.textContent = 'API ERROR';
        connectionStatus.className = 'flex items-center gap-1.5 px-2 py-1 rounded-full bg-[#f7d4d6] text-[#c50000] text-xs font-mono';
        connectionStatus.querySelector('span').className = 'h-2 w-2 rounded-full bg-[#ee0000]';
    }
}

function showEmptyState() {
    measurementsTbody.innerHTML = `
        <tr id="empty-state">
            <td colspan="6" class="px-6 py-10 text-center text-mute">
                Belum ada data pengukuran. Menunggu sensor...
            </td>
        </tr>
    `;
}

function updateTable(data) {
    if (data.length === 0) return;
    
    const rows = data.map(item => {
        const time = new Date(item.measured_at).toLocaleTimeString('id-ID');
        return `
            <tr>
                <td class="px-6 py-3 whitespace-nowrap text-ink">${time}</td>
                <td class="px-6 py-3 whitespace-nowrap text-ink">${item.room || '-'}</td>
                <td class="px-6 py-3 whitespace-nowrap text-ink font-semibold">${item.total_dba.toFixed(1)}</td>
                <td class="px-6 py-3 whitespace-nowrap text-body">${(item.mechanical_confidence * 100).toFixed(0)}%</td>
                <td class="px-6 py-3 whitespace-nowrap text-body">${(item.human_activity_confidence * 100).toFixed(0)}%</td>
                <td class="px-6 py-3 whitespace-nowrap text-mute truncate max-w-[150px]">${item.source_hint || '-'}</td>
            </tr>
        `;
    });
    
    measurementsTbody.innerHTML = rows.join('');
}

// --- Chart.js ---
function initChart() {
    if (chartInstance) return;

    const ctx = document.getElementById('historical-chart').getContext('2d');
    
    // Set global font to sans for Chart.js
    Chart.defaults.font.family = "'Inter', 'system-ui', sans-serif";
    Chart.defaults.color = "#888888";

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Total dBA',
                data: [],
                borderColor: '#171717', // Vercel Ink
                backgroundColor: 'rgba(23, 23, 23, 0.05)',
                borderWidth: 2,
                pointBackgroundColor: '#ffffff',
                pointBorderColor: '#171717',
                pointRadius: 3,
                pointHoverRadius: 5,
                fill: true,
                tension: 0.2 // slight curve
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 400 // Fast animation for polling
            },
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: '#171717',
                    titleFont: { size: 13 },
                    bodyFont: { size: 13, family: "'JetBrains Mono', monospace" },
                    padding: 10,
                    cornerRadius: 6,
                    displayColors: false
                }
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: {
                        color: '#ebebeb', // Hairline
                        drawBorder: false
                    },
                    border: { display: false }
                },
                x: {
                    grid: {
                        display: false,
                        drawBorder: false
                    },
                    border: { display: false },
                    ticks: {
                        maxTicksLimit: 10
                    }
                }
            }
        }
    });
}

function updateChart(data) {
    if (!chartInstance) return;

    // Ambil 30 data terakhir untuk chart, lalu reverse supaya urutan waktu dari kiri (lama) ke kanan (baru)
    const chartData = data.slice(0, 30).reverse();

    chartInstance.data.labels = chartData.map(item => new Date(item.measured_at).toLocaleTimeString('id-ID'));
    chartInstance.data.datasets[0].data = chartData.map(item => item.total_dba);
    
    chartInstance.update();
}
