// Konfigurasi API
// Gunakan 'http://127.0.0.1:8000' untuk testing lokal, atau '' (kosong) saat deployment Nginx
const API_BASE_URL = '';

let noiseChart;
let pollingInterval;

document.addEventListener('DOMContentLoaded', () => {
    initChart();
    
    // Auth Check
    const token = getAuthToken();
    if (token) {
        showDashboard();
    } else {
        showLogin();
    }

    // Login Form Handler
    document.getElementById('login-form').addEventListener('submit', handleLogin);
    
    // Logout Handler
    document.getElementById('logout-btn').addEventListener('click', handleLogout);
});

function getAuthToken() {
    return sessionStorage.getItem('acoustic_jwt_token');
}

function setAuthToken(token) {
    sessionStorage.setItem('acoustic_jwt_token', token);
}

function clearAuthToken() {
    sessionStorage.removeItem('acoustic_jwt_token');
}

function showLogin() {
    document.getElementById('login-section').classList.remove('hidden');
    document.getElementById('dashboard-section').classList.add('hidden');
    document.getElementById('logout-btn').classList.add('hidden');
    
    // Stop polling
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

function showDashboard() {
    document.getElementById('login-section').classList.add('hidden');
    document.getElementById('dashboard-section').classList.remove('hidden');
    document.getElementById('logout-btn').classList.remove('hidden');
    
    fetchMeasurements();
    // M2/M3: Polling setiap 5 detik
    if (!pollingInterval) {
        pollingInterval = setInterval(fetchMeasurements, 5000);
    }
}

async function handleLogin(e) {
    e.preventDefault();
    const usernameInput = document.getElementById('username').value;
    const passwordInput = document.getElementById('password').value;
    const errorMsg = document.getElementById('login-error');
    const submitBtn = e.target.querySelector('button[type="submit"]');
    
    errorMsg.classList.add('hidden');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Logging in...';

    try {
        const response = await fetch(`${API_BASE_URL}/api/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                username: usernameInput,
                password: passwordInput
            })
        });

        if (!response.ok) {
            throw new Error('Invalid credentials');
        }

        const data = await response.json();
        // Cek response JSON sesuai API contract
        if (data.token || data.access_token) {
            setAuthToken(data.token || data.access_token);
            e.target.reset();
            showDashboard();
        } else {
            throw new Error('No token received');
        }
    } catch (err) {
        errorMsg.textContent = 'Login failed. Please check username and password.';
        errorMsg.classList.remove('hidden');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Login';
    }
}

function handleLogout() {
    clearAuthToken();
    showLogin();
}

function initChart() {
    const ctx = document.getElementById('noise-chart').getContext('2d');
    noiseChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Total dBA',
                data: [],
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                pointRadius: 3,
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: 'Waktu'
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: 'dBA'
                    },
                    suggestedMin: 30,
                    suggestedMax: 100
                }
            },
            animation: {
                duration: 0 // Disable animation for polling to avoid flickering
            }
        }
    });
}

function fetchMeasurements() {
    const token = getAuthToken();
    if (!token) {
        showLogin();
        return;
    }

    const statusBadge = document.getElementById('api-status');
    const tableBody = document.getElementById('table-body');
    const emptyState = document.getElementById('empty-state');

    fetch(`${API_BASE_URL}/api/measurements`, {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    })
        .then(response => {
            if (response.status === 401) {
                // Token expired or invalid
                handleLogout();
                throw new Error('Unauthorized');
            }
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            statusBadge.textContent = 'Connected';
            statusBadge.className = 'status-badge ok';

            if (!data || data.length === 0) {
                showEmptyState(true);
                emptyState.textContent = 'No data yet';
                return;
            }

            showEmptyState(false);
            
            // Update latest value cards
            const latestData = data[0];
            document.getElementById('latest-dba').textContent = latestData.total_dba.toFixed(1);
            document.getElementById('latest-device-id').textContent = latestData.device_id;
            document.getElementById('latest-room').textContent = latestData.room;
            
            const timeField = latestData.measured_at || latestData.timestamp;
            document.getElementById('latest-measured-at').textContent = formatTime(timeField);

            // M4 Polish: Compliance Badge
            const complianceBadge = document.getElementById('compliance-badge');
            if (complianceBadge) {
                complianceBadge.classList.remove('hidden', 'badge-normal', 'badge-warning', 'badge-danger');
                if (latestData.total_dba < 55) {
                    complianceBadge.textContent = 'Normal';
                    complianceBadge.classList.add('badge-normal');
                } else if (latestData.total_dba < 65) {
                    complianceBadge.textContent = 'Warning';
                    complianceBadge.classList.add('badge-warning');
                } else {
                    complianceBadge.textContent = 'High Noise Exposure';
                    complianceBadge.classList.add('badge-danger');
                }
            }

            // M4 Polish: Stale Indicator
            const staleIndicator = document.getElementById('stale-indicator');
            if (staleIndicator) {
                const dataTime = new Date(timeField).getTime();
                const now = new Date().getTime();
                const diffSeconds = (now - dataTime) / 1000;

                if (diffSeconds > 120) {
                    staleIndicator.classList.remove('hidden');
                    document.getElementById('latest-dba').style.opacity = '0.5';
                } else {
                    staleIndicator.classList.add('hidden');
                    document.getElementById('latest-dba').style.opacity = '1';
                }
            }

            // Populate table (limit up to 10 rows)
            tableBody.innerHTML = '';
            const recentData = data.slice(0, 10);
            
            recentData.forEach(row => {
                const tr = document.createElement('tr');
                const rowTime = row.measured_at || row.timestamp;
                tr.innerHTML = `
                    <td>${formatTime(rowTime)}</td>
                    <td>${row.device_id}</td>
                    <td>${row.room}</td>
                    <td>${row.total_dba.toFixed(1)}</td>
                    <td>${row.mechanical_confidence ? row.mechanical_confidence.toFixed(2) : '-'}</td>
                    <td>${row.human_activity_confidence ? row.human_activity_confidence.toFixed(2) : '-'}</td>
                `;
                tableBody.appendChild(tr);
            });

            // Update Chart
            const chartData = [...recentData].reverse();
            const labels = chartData.map(row => {
                const rt = row.measured_at || row.timestamp;
                const d = new Date(rt);
                return d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            });
            const dbaValues = chartData.map(row => row.total_dba);

            if (noiseChart) {
                noiseChart.data.labels = labels;
                noiseChart.data.datasets[0].data = dbaValues;
                noiseChart.update();
            }
        })
        .catch(error => {
            if (error.message === 'Unauthorized') return; // Sudah ditangani di atas, tidak perlu render error connection lost

            console.error('Error fetching data:', error);
            statusBadge.textContent = 'Connection lost';
            statusBadge.className = 'status-badge error';
            
            document.getElementById('latest-dba').textContent = '--';
            document.getElementById('latest-device-id').textContent = '--';
            document.getElementById('latest-room').textContent = '--';
            document.getElementById('latest-measured-at').textContent = '--';
            
            tableBody.innerHTML = '';
            showEmptyState(true);
            emptyState.textContent = 'Connection lost. Cannot fetch data from API.';
        });
}

function showEmptyState(isEmpty) {
    const emptyState = document.getElementById('empty-state');
    const tableContainer = document.querySelector('.table-container');
    const chartSection = document.querySelector('.chart-section');
    
    if (isEmpty) {
        emptyState.classList.remove('hidden');
        tableContainer.classList.add('hidden');
        if (chartSection) chartSection.classList.add('hidden');
    } else {
        emptyState.classList.add('hidden');
        tableContainer.classList.remove('hidden');
        if (chartSection) chartSection.classList.remove('hidden');
    }
}

function formatTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleString('id-ID');
}
