# Frontend Console Sprint — Acoustic Audit System

## Mission

Upgrade the current frontend from a simple live dashboard into a functional **Acoustic Monitoring Console**.

The console must support:

1. Live monitoring
2. Historical data explorer
3. CSV export
4. Device status/details
5. Basic report summary

Do **not** prioritize AI/LLM integration yet. Prepare the UI and backend summary structure so AI can be added later.

---

## Mandatory Reading Order

Before changing code, read these files:

1. `AGENTS.md`
2. `PROJECT_CONTRACT_PRO.md`
3. `INTEGRATION_HANDSHAKE.md`
4. `AGENT_SELECTOR_PRO_SPRINT.md`
5. `design.md`
6. `frontend/index.html`
7. `frontend/app.js`
8. `frontend/style.css`
9. `backend/api/app.py`
10. `database/schema.sql`

If `design.md` is inside another folder, locate it with:

```bash
find . -iname "design.md" -o -iname "*design*.md"
```

Follow `design.md` as the visual source of truth. Do not redesign randomly.

---

## Hard Rules

* Do not touch edge hardware code unless absolutely necessary.
* Do not touch Mosquitto/TLS/ACL config in this sprint.
* Do not add fake AI explanations.
* Do not reintroduce:

  * `mechanical_confidence`
  * `human_activity_confidence`
  * `source_hint`
* Do not claim certified dBA/LAeq unless A-weighting and calibration are truly implemented.
* Prefer `SPL estimate`, `spl_avg_db`, and `spl_max_db`.
* Keep frontend lightweight: HTML/CSS/vanilla JS.
* Do not migrate to React/Vite unless explicitly asked.
* Preserve the existing design language from `design.md`.

---

## Current Known State

The frontend currently has a public dashboard view showing:

* SPL cards
* Chart.js time-series
* Recent measurements table

Login may already exist in some form. Do not rebuild login from scratch unless inspection proves it is broken or disconnected.

The backend currently has:

* `GET /api/measurements`
* `GET /api/devices`
* `POST /api/login` possibly as a stub
* PostgreSQL measurements table with canonical fields:

  * `device_id`
  * `room`
  * `measured_at`
  * `schema_version`
  * `metric_type`
  * `weighting`
  * `window_seconds`
  * `spl_avg_db`
  * `spl_max_db`
  * `calibration_offset_db`
  * `status`
  * `quality_flags`
  * `edge_version`
  * `total_dba` as legacy fallback

---

## UI Target

Create a dashboard with these main tabs/navigation sections:

```text
[Live] [History] [Export CSV] [Devices] [Report]
```

If login already exists, preserve it and route authenticated users into this console.

---

## Tab 1 — Live

Purpose: show current acoustic condition.

Must include:

* Selected device dropdown
* SPL Avg card
* SPL Max card
* Device status card: online/stale/offline/unknown
* Calibration offset card
* Live chart of recent SPL values
* Recent measurements table
* Refresh button
* Auto-refresh interval

Data source:

```text
GET /api/devices
GET /api/measurements?device_id=<id>&limit=100
```

If no `device_id` is selected, default to latest available device.

---

## Tab 2 — History

Purpose: allow users to access old data by date/time.

UI controls:

* Device selector
* Start date
* Start time
* End date
* End time
* Limit selector
* Search button

Backend support needed:

Enhance `GET /api/measurements` to support:

```text
device_id
start
end
limit
```

Example:

```text
/api/measurements?device_id=ACOUSTIC-PI-001&start=2026-06-28T08:00:00Z&end=2026-06-28T10:00:00Z&limit=500
```

History output:

* Chart for selected range
* Table for selected range
* Summary cards:

  * Average SPL
  * Maximum SPL
  * Number of samples
  * Peak time

---

## Tab 3 — Export CSV

Purpose: let users download measurement data for report/Excel.

UI controls:

* Device selector
* Start date/time
* End date/time
* Download CSV button

Backend endpoint to add:

```text
GET /api/measurements/export.csv?device_id=<id>&start=<iso>&end=<iso>
```

CSV columns:

```text
measured_at,device_id,room,spl_avg_db,spl_max_db,weighting,metric_type,status,calibration_offset_db,edge_version,quality_flags
```

Use `StreamingResponse` or plain CSV response from FastAPI.

Frontend behavior:

* Build export URL from selected filters.
* Trigger browser download.
* Filename format:

```text
acoustic_measurements_<device_id>_<start>_<end>.csv
```

---

## Tab 4 — Devices

Purpose: show sensor/device health.

Must include table/cards showing:

* Device ID
* Room
* Location
* Description
* Last seen
* Health status
* Last error
* Edge version if available
* Stale indicator

Data source:

```text
GET /api/devices
```

Optional backend enhancement:

```text
GET /api/devices/{device_id}/summary
```

Summary may include:

* Total measurements
* Last 24h average SPL
* Last 24h max SPL
* First seen
* Last seen

Only implement this endpoint if it can be done cleanly without breaking existing API.

---

## Tab 5 — Report

Purpose: provide a non-AI statistical report first, and prepare for AI later.

Do not call any LLM yet.

UI controls:

* Device selector
* Start date/time
* End date/time
* Generate Summary button

Backend endpoint to add:

```text
GET /api/reports/summary?device_id=<id>&start=<iso>&end=<iso>
```

Backend should compute:

* Average SPL
* Maximum SPL
* Minimum SPL
* Number of samples
* Peak timestamps
* Count above threshold, default threshold `65 dB`
* Basic anomaly candidates:

  * high SPL above threshold
  * sudden spike compared to local average if easy
  * stale/no data warning

Response shape example:

```json
{
  "device_id": "ACOUSTIC-PI-001",
  "start": "2026-06-28T08:00:00Z",
  "end": "2026-06-28T10:00:00Z",
  "sample_count": 120,
  "avg_spl": 58.2,
  "min_spl": 42.1,
  "max_spl": 72.5,
  "threshold_db": 65,
  "above_threshold_count": 7,
  "peak_times": [
    {
      "measured_at": "2026-06-28T08:43:00Z",
      "spl_max_db": 72.5,
      "spl_avg_db": 68.1
    }
  ],
  "anomalies": [
    {
      "measured_at": "2026-06-28T08:43:00Z",
      "type": "threshold_exceeded",
      "reason": "SPL exceeded 65 dB threshold"
    }
  ],
  "plain_summary": "During the selected period, the average SPL was 58.2 dB with a maximum of 72.5 dB. Several samples exceeded the 65 dB threshold."
}
```

Frontend should display:

* Summary cards
* Peak time list
* Anomaly list
* Plain summary paragraph

Label it as:

```text
Statistical Report
```

Do not label it as AI report yet.

---

## Backend Implementation Notes

Update `backend/api/app.py` carefully.

Required:

1. Extend `/api/measurements` with optional query filters:

   * `device_id`
   * `start`
   * `end`
   * `limit`

2. Add:

   * `/api/measurements/export.csv`
   * `/api/reports/summary`

3. Use parameterized SQL only.

4. Convert `Decimal` values to float before JSON response.

5. Do not break existing frontend calls.

6. If auth middleware already exists, preserve it.

7. If login is only stub, do not fully rebuild auth in this sprint unless trivial. Focus on functional console.

---

## Frontend Implementation Notes

Update:

* `frontend/index.html`
* `frontend/app.js`
* `frontend/style.css`

Keep it simple and robust.

Recommended JS structure:

```text
state = {
  activeTab,
  devices,
  selectedDeviceId,
  measurements,
  historyFilters,
  refreshInterval
}
```

Functions to implement:

```text
init()
loadDevices()
loadLiveMeasurements()
renderLive()
renderHistory()
searchHistory()
downloadCsv()
loadDevicesView()
generateReportSummary()
switchTab(tabName)
apiFetch(path)
formatDateTime(value)
computeClientSummary(measurements)
```

If `design.md` defines colors, typography, spacing, cards, shadows, or layout rules, follow them.

---

## Visual Requirements

The result should feel like an engineering monitoring console:

* Clear sidebar or top tab navigation
* Professional cards
* Clean chart area
* Readable data table
* Good empty states
* Loading/error states
* Mobile-friendly enough for laptop demo

Avoid:

* Decorative useless animations
* Huge visual redesign unrelated to `design.md`
* Too many colors
* Fake AI branding

---

## Acceptance Criteria

The sprint is successful if:

1. The frontend opens at `http://127.0.0.1:5500`.
2. User can switch between:

   * Live
   * History
   * Export CSV
   * Devices
   * Report
3. Live tab displays recent data from API.
4. History tab can filter by device and time range.
5. Export CSV downloads a valid CSV file.
6. Devices tab shows device health/status.
7. Report tab generates statistical summary without LLM.
8. No conflict markers remain:

   ```bash
   grep -RniE '<<<<<<<|=======|>>>>>>>' backend database frontend edge deployment --exclude='*.pyc'
   ```
9. No fake confidence/source classifier fields are reintroduced.
10. Existing canonical payload fields remain supported.

---

## Local Test Plan

Use these commands after implementation.

Terminal 1 — API:

```bash
cd ~/Projects/Acoustic-Audit-System
bash
source .venv/bin/activate
set -a
source .env
set +a
python -m uvicorn backend.api.app:app --reload --host 127.0.0.1 --port 8000
```

Terminal 2 — Worker:

```bash
cd ~/Projects/Acoustic-Audit-System
bash
source .venv/bin/activate
set -a
source .env
set +a
python backend/worker/worker.py
```

Terminal 3 — Frontend dev proxy:

```bash
cd ~/Projects/Acoustic-Audit-System
python /tmp/dev_frontend_proxy.py
```

If `/tmp/dev_frontend_proxy.py` does not exist, create a simple proxy that serves `frontend/` on port `5500` and forwards `/api/*` to `http://127.0.0.1:8000`.

Terminal 4 — Publish dummy data:

```bash
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

mosquitto_pub -h 127.0.0.1 -p 1883 \
  -t "acoustic/devices/ACOUSTIC-LOCAL-001/measurements" \
  -m "{
    \"schema_version\":\"1.0\",
    \"device_id\":\"ACOUSTIC-LOCAL-001\",
    \"room\":\"local-lab\",
    \"timestamp\":\"$TS\",
    \"metric_type\":\"spl_estimate\",
    \"weighting\":\"flat\",
    \"window_seconds\":1,
    \"spl_avg_db\":58.7,
    \"spl_max_db\":64.3,
    \"calibration_offset_db\":0,
    \"status\":\"ok\",
    \"quality_flags\":{},
    \"edge_version\":\"local-test\"
  }"
```

Then test:

```bash
curl http://127.0.0.1:8000/api/health
curl "http://127.0.0.1:8000/api/measurements?limit=10"
curl "http://127.0.0.1:8000/api/devices"
curl "http://127.0.0.1:8000/api/reports/summary?device_id=ACOUSTIC-LOCAL-001"
curl -I "http://127.0.0.1:8000/api/measurements/export.csv?device_id=ACOUSTIC-LOCAL-001"
```

Open:

```text
http://127.0.0.1:5500
```

---

## Git Rules

Before editing:

```bash
git status --short
git branch --show-current
```

After editing:

```bash
grep -RniE '<<<<<<<|=======|>>>>>>>' backend database frontend edge deployment --exclude='*.pyc' || echo "OK: no conflict markers"
git diff --stat
git diff -- frontend backend/api database
```

Stage only relevant files:

```bash
git add frontend/index.html frontend/app.js frontend/style.css backend/api/app.py
```

If database changes are required:

```bash
git add database/schema.sql database/migration_01_pro_upgrade.sql
```

Commit message:

```bash
git commit -m "feat: add monitoring console history export and reports"
```

Do not push until local API, frontend, and CSV export are tested.

---

## Final Response Required From Agent

After implementation, summarize:

1. Files changed
2. New UI tabs added
3. New/changed API endpoints
4. How CSV export works
5. How report summary works
6. Local test commands executed
7. Known limitations
8. Next recommended step
