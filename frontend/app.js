// Konfigurasi API
const API_BASE_URL = 'http://127.0.0.1:8000';
let chartInstance = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchMeasurements();
    setInterval(fetchMeasurements, 5000); // Polling every 5s
});

function fetchMeasurements() {
    const statusBadge = document.getElementById('api-status');
    const tableBody = document.getElementById('table-body');
    const emptyState = document.getElementById('empty-state');

    fetch(`${API_BASE_URL}/api/measurements`)
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
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
            
            const latestData = data[0];
            const timeField = latestData.measured_at || latestData.timestamp;
            const measuredTime = new Date(timeField);
            const ageSeconds = (new Date() - measuredTime) / 1000;
            const isStale = ageSeconds > 120;
            
            const splAvg = latestData.spl_avg_db !== null ? latestData.spl_avg_db : latestData.total_dba;
            const splMax = latestData.spl_max_db;
            
            document.getElementById('latest-dba').textContent = splAvg ? splAvg.toFixed(1) : '--';
            document.getElementById('latest-max').textContent = (splMax !== null && splMax !== undefined) ? splMax.toFixed(1) : '--';
            
            if (latestData.weighting === 'A') {
                document.getElementById('unit-label').textContent = 'dBA';
            } else {
                document.getElementById('unit-label').textContent = 'dB';
            }

            document.getElementById('latest-device-id').textContent = latestData.device_id;
            document.getElementById('latest-room').textContent = latestData.room;
            document.getElementById('latest-measured-at').textContent = formatTime(timeField);
            
            const sensorStatusBadge = document.getElementById('latest-status');
            sensorStatusBadge.textContent = isStale ? 'STALE' : (latestData.status || 'OK');
            sensorStatusBadge.className = isStale ? 'status-badge warning' : (latestData.status === 'ok' ? 'status-badge ok' : 'status-badge error');

            document.getElementById('latest-cal-offset').textContent = latestData.calibration_offset_db || '0.0';
            document.getElementById('latest-weighting').textContent = latestData.weighting || 'flat';
            document.getElementById('latest-metric-type').textContent = latestData.metric_type || 'spl_estimate';

            tableBody.innerHTML = '';
            const recentData = data.slice(0, 10);
            
            recentData.forEach(row => {
                const tr = document.createElement('tr');
                const rowTime = row.measured_at || row.timestamp;
                const rowSplAvg = row.spl_avg_db !== null ? row.spl_avg_db : row.total_dba;
                const rowSplMax = row.spl_max_db !== null ? row.spl_max_db : '-';
                tr.innerHTML = `
                    <td>${formatTime(rowTime)}</td>
                    <td>${row.device_id}</td>
                    <td>${row.room}</td>
                    <td>${rowSplAvg ? rowSplAvg.toFixed(1) : '-'}</td>
                    <td>${rowSplMax !== '-' ? rowSplMax.toFixed(1) : '-'}</td>
                    <td>${row.status || '-'}</td>
                `;
                tableBody.appendChild(tr);
            });
            
            updateChart(data);
        })
        .catch(error => {
            console.error('Error fetching data:', error);
            statusBadge.textContent = 'Connection lost';
            statusBadge.className = 'status-badge error';
            
            document.getElementById('latest-dba').textContent = '--';
            document.getElementById('latest-max').textContent = '--';
            document.getElementById('latest-device-id').textContent = '--';
            document.getElementById('latest-room').textContent = '--';
            document.getElementById('latest-measured-at').textContent = '--';
            
            tableBody.innerHTML = '';
            showEmptyState(true);
            emptyState.textContent = 'Connection lost. Cannot fetch data from API.';
        });
}

function updateChart(data) {
    const ctx = document.getElementById('spl-chart');
    if (!ctx) return;
    
    const chartData = [...data].reverse();
    const labels = chartData.map(d => {
        const time = new Date(d.measured_at || d.timestamp);
        return `${time.getHours().toString().padStart(2, '0')}:${time.getMinutes().toString().padStart(2, '0')}:${time.getSeconds().toString().padStart(2, '0')}`;
    });
    
    const splAvgs = chartData.map(d => d.spl_avg_db !== null ? d.spl_avg_db : d.total_dba);
    const splMaxs = chartData.map(d => d.spl_max_db);
    const thresholdData = chartData.map(() => 65);

    if (chartInstance) {
        chartInstance.data.labels = labels;
        chartInstance.data.datasets[0].data = splAvgs;
        chartInstance.data.datasets[1].data = splMaxs;
        chartInstance.data.datasets[2].data = thresholdData;
        chartInstance.update();
    } else {
        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'SPL Avg',
                        data: splAvgs,
                        borderColor: '#3b82f6',
                        tension: 0.1
                    },
                    {
                        label: 'SPL Max',
                        data: splMaxs,
                        borderColor: '#ef4444',
                        borderDash: [5, 5],
                        tension: 0.1,
                        spanGaps: true
                    },
                    {
                        label: 'Threshold (65 dB)',
                        data: thresholdData,
                        borderColor: '#f59e0b',
                        borderWidth: 1,
                        pointRadius: 0,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: false,
                        suggestedMin: 40,
                        suggestedMax: 85
                    }
                },
                animation: false
            }
        });
    }
}

function showEmptyState(isEmpty) {
    const emptyState = document.getElementById('empty-state');
    const tableContainer = document.querySelector('.table-container');
    
    if (isEmpty) {
        emptyState.classList.remove('hidden');
        if (tableContainer) tableContainer.classList.add('hidden');
    } else {
        emptyState.classList.add('hidden');
        if (tableContainer) tableContainer.classList.remove('hidden');
    }
}

function formatTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleString('id-ID');
}
