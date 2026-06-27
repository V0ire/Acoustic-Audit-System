// Konfigurasi API
// Gunakan 'http://127.0.0.1:8000' jika membuka index.html langsung dari file system (file://)
// Gunakan '' (kosong) jika dijalankan melalui web server yang sama dengan backend (Nginx proxy)
const API_BASE_URL = 'http://127.0.0.1:8000';

document.addEventListener('DOMContentLoaded', () => {
    fetchMeasurements();
});

function fetchMeasurements() {
    const statusBadge = document.getElementById('api-status');
    const tableBody = document.getElementById('table-body');
    const emptyState = document.getElementById('empty-state');
    const tableContainer = document.querySelector('.table-container');

    fetch(`${API_BASE_URL}/api/measurements`)
        .then(response => {
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
            
            // Handle timestamp mapping (measured_at vs timestamp based on API response)
            const timeField = latestData.measured_at || latestData.timestamp;
            document.getElementById('latest-measured-at').textContent = formatTime(timeField);

            // Populate table (limit up to 10 rows for M1)
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
        })
        .catch(error => {
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
    
    if (isEmpty) {
        emptyState.classList.remove('hidden');
        tableContainer.classList.add('hidden');
    } else {
        emptyState.classList.add('hidden');
        tableContainer.classList.remove('hidden');
    }
}

function formatTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleString('id-ID');
}
