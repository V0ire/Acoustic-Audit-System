# AGENT_SELECTOR_PRO_SPRINT.md — Antigravity Role Selector

## 0. Purpose

This file is for Antigravity or AI coding agents working on the Acoustic Audit System Pro Upgrade Sprint.

Before editing code, the agent must select exactly one role.

Do not work across roles unless explicitly instructed.

---

## 1. Read First

Before editing code, read:

```text
1. AGENTS.md
2. PROJECT_CONTRACT_PRO.md
3. database/schema.sql
4. docs/api-contract.md, if present
5. current component folder
```

If there is conflict:

```text
PROJECT_CONTRACT_PRO.md > AGENTS.md > existing docs > code comments
```

If existing code differs from the new contract, do not silently rewrite everything. Report the difference and implement compatibility where safe.

---

## 2. Role Selection

Choose one:

```text
ROLE=1_EDGE_MQTT_SECURITY
ROLE=2_INGESTION_API_DASHBOARD
ROLE=3_DOCS_DIAGRAM_QA
```

Only select ROLE=3 if explicitly asked. Otherwise choose ROLE=1 or ROLE=2.

---

# ROLE=1_EDGE_MQTT_SECURITY

## Mission

You own:

```text
Raspberry Pi edge
INMP441 microphone
acoustic_edge.py
A-weighting or SPL naming
calibration offset
MQTT publisher
heartbeat
LWT
MQTT TLS
MQTT ACL
```

Your output must make the edge and MQTT side reliable, secure enough for demo, and honest in terminology.

---

## Scope

You may edit:

```text
edge/
deployment/mosquitto/
deployment/systemd/acoustic-edge.service
docs/edge*
docs/mqtt*
.env.example files
```

Do not edit frontend/dashboard unless explicitly asked.

Do not edit database schema except to update `.env.example` or documentation references.

---

## Required Preflight

Run or inspect:

```text
Find edge files.
Inspect acoustic_edge.py.
Inspect demo-simulate.py.
Inspect edge requirements.
Inspect MQTT env variables.
Inspect Mosquitto config templates.
Check whether payload uses legacy total_dba or new spl_avg_db.
```

Report:

```text
Current edge input method
Current MQTT host/port/auth
Current payload fields
Whether A-weighting exists
Whether heartbeat exists
Whether LWT exists
Whether TLS/ACL exists
```

---

## Edge Payload Target

Publish this canonical payload:

```json
{
  "schema_version": "1.0",
  "device_id": "ACOUSTIC-PI-001",
  "room": "R402",
  "timestamp": "2026-06-27T18:00:00+07:00",
  "metric_type": "spl_estimate",
  "weighting": "flat",
  "window_seconds": 1.0,
  "spl_avg_db": 58.2,
  "spl_max_db": 64.1,
  "calibration_offset_db": -14.0,
  "status": "ok",
  "quality_flags": {
    "clipping": false,
    "low_signal": false,
    "mic_error": false
  },
  "edge_version": "edge-0.2.0"
}
```

If code still uses `total_dba`, keep compatibility but prefer new canonical fields.

Do not add:

```text
mechanical_confidence
human_activity_confidence
source_hint
```

unless a computation method is implemented and documented.

---

## A-weighting Rule

If implementing A-weighting:

```text
Apply A-weighting before RMS.
Set weighting = "A".
Set metric_type = "a_weighted_estimate".
Use label "LAeq estimate" only if the window is defined.
```

If not implementing A-weighting:

```text
Set weighting = "flat".
Set metric_type = "spl_estimate".
Use SPL estimate naming.
```

Do not fake A-weighting.

---

## Calibration Rule

Support:

```text
CALIBRATION_OFFSET_DB
```

Optional:

```text
CALIBRATION_SCALE
```

Log both raw and calibrated values:

```text
raw_spl_avg_db
calibration_offset_db
spl_avg_db
spl_max_db
```

Calibration must not be hidden.

---

## Heartbeat Rule

Publish every 30 seconds to:

```text
acoustic/devices/{device_id}/heartbeat
```

Payload:

```json
{
  "schema_version": "1.0",
  "device_id": "ACOUSTIC-PI-001",
  "timestamp": "2026-06-27T18:00:00+07:00",
  "status": "online",
  "uptime_seconds": 1234,
  "edge_version": "edge-0.2.0"
}
```

QoS:

```text
0
```

---

## LWT Rule

Configure MQTT Last Will:

```text
topic: acoustic/devices/{device_id}/status
qos: 1
retain: true
```

Payload:

```json
{
  "schema_version": "1.0",
  "device_id": "ACOUSTIC-PI-001",
  "timestamp": null,
  "status": "offline",
  "reason": "connection_lost"
}
```

---

## MQTT TLS Rule

If implementing TLS:

Required env variables:

```env
MQTT_USE_TLS=true
MQTT_PORT=8883
MQTT_TLS_CA_PATH=/path/to/ca.crt
MQTT_TLS_INSECURE=false
```

Do not set insecure certificate verification by default.

If TLS cannot be finished safely:

```text
Keep MQTT 1883 username/password.
Make sure anonymous access is disabled.
Document TLS as Planned Pro.
```

---

## MQTT ACL Rule

If implementing ACL for one device:

```text
user acoustic_device
topic write acoustic/devices/ACOUSTIC-PI-001/measurements
topic write acoustic/devices/ACOUSTIC-PI-001/heartbeat
topic write acoustic/devices/ACOUSTIC-PI-001/status
topic write acoustic/devices/ACOUSTIC-PI-001/events
```

Worker credentials must be separate if ACL requires it.

Do not break worker subscription.

---

## Acceptance Test

ROLE=1 is done when:

```text
Edge can publish measurement payload.
Edge can publish heartbeat.
LWT offline payload is configured.
Payload does not contain undefined confidence/source fields.
Metric naming is honest.
MQTT auth works.
MQTT TLS/ACL is either implemented or documented as Planned Pro.
```

---

# ROLE=2_INGESTION_API_DASHBOARD

## Mission

You own:

```text
worker.py
PostgreSQL mapping
device_health
FastAPI endpoints
frontend dashboard
chart
threshold line
calibration status
sensor status
```

Your output must make data visible, queryable, and demoable.

---

## Scope

You may edit:

```text
backend/worker/
backend/api/
database/
frontend/
deployment/systemd/acoustic-worker.service
deployment/systemd/acoustic-api.service
docs/api-contract.md
docs/database*
docs/frontend*
```

Do not edit edge audio processing unless explicitly asked.

Do not edit MQTT TLS/ACL unless coordinating with ROLE=1.

---

## Required Preflight

Inspect:

```text
backend/worker/
backend/api/
database/schema.sql
frontend/
deployment/systemd/
```

Report:

```text
Does worker.py exist?
What topic does worker subscribe to?
What payload fields does worker expect?
What DB fields exist?
Does API require JWT or is it stubbed?
What frontend currently displays?
```

If worker.py is missing, create it or recover it from current VPS/source if available.

---

## Worker Subscription

Subscribe to:

```text
acoustic/devices/+/measurements
```

Optional:

```text
acoustic/devices/+/heartbeat
acoustic/devices/+/status
```

Do not subscribe to commands unless command handling exists.

---

## Worker Validation Rules

Worker must require:

```text
device_id
room
timestamp
spl_avg_db or total_dba legacy fallback
status
```

Worker should accept:

```text
spl_max_db
calibration_offset_db
quality_flags
schema_version
metric_type
weighting
```

Legacy fallback:

```text
if spl_avg_db missing and total_dba exists:
    spl_avg_db = total_dba
    log legacy warning
```

Reject payload if:

```text
device_id missing
timestamp invalid
both spl_avg_db and total_dba missing
quality_flags is present but not object
JSON malformed
```

Rejected payload must not crash worker.

---

## Database Mapping

Preferred Pro mapping:

```text
spl_avg_db → measurements.spl_avg_db
spl_max_db → measurements.spl_max_db
calibration_offset_db → measurements.calibration_offset_db
quality_flags → measurements.quality_flags
```

Legacy mapping if schema still uses `total_dba`:

```text
spl_avg_db → measurements.total_dba
```

Do not destructively migrate database during demo sprint unless instructed.

---

## Device Health

If implementing device health:

Use one-row-per-device UPSERT model.

Minimum fields:

```text
device_id or device_pk
last_seen
status
last_error
updated_at
```

Status values:

```text
online
offline
stale
mic_error
low_signal
clipping
unknown
```

Worker should update device health when measurement, heartbeat, or status message arrives.

---

## API Minimum

Required endpoints:

```text
GET /api/health
GET /api/measurements
GET /api/devices
POST /api/login
```

Recommended additions:

```text
GET /api/measurements/latest
GET /api/measurements/summary
GET /api/devices/{device_id}/health
GET /api/devices/{device_id}/calibration
```

If JWT is stubbed, do not claim JWT is implemented.

---

## Frontend Minimum

Dashboard must show:

```text
Current SPL average
SPL max
Last seen
Sensor status
Time-series chart
Threshold line
Calibration status
Recent measurement table
API connection status
```

Do not show mechanical/human confidence cards unless values are produced by a defined algorithm.

---

## Threshold Rule

Default threshold:

```text
65 dB
```

Dashboard should show:

```text
Normal: below threshold
Warning: near threshold
High: above threshold
```

Use threshold line in chart if chart exists.

---

## Calibration Status Panel

Show:

```text
device_id
mic_type if available
calibration_offset_db
weighting
metric_type
last calibrated if available
```

If no calibration exists:

```text
Calibration: not configured
```

Do not hide calibration uncertainty.

---

## Acceptance Test

ROLE=2 is done when:

```text
Worker exists in repo.
Worker can insert valid MQTT payloads.
Worker rejects bad payloads safely.
API can return measurements.
Frontend can display latest data.
Frontend chart updates or reloads data.
Sensor status and calibration status are visible.
No undefined confidence/source UI remains.
```

---

# ROLE=3_DOCS_DIAGRAM_QA

## Mission

You own documentation, diagrams, and QA alignment.

Only choose this role if explicitly asked.

---

## Scope

You may edit:

```text
docs/
README.md
AGENTS.md
PROJECT_CONTRACT_PRO.md
architecture diagrams
demo guide
```

Do not change code unless explicitly asked.

---

## Required Outputs

```text
Full System Architecture
Edge Signal Processing Pipeline
VPS Deployment Architecture
Database ERD
Data Lifecycle Sequence
MVP vs Pro Gap Table
Demo Script
Known Limitations
```

---

## Acceptance Test

ROLE=3 is done when:

```text
Docs clearly separate Implemented vs Planned.
No certified dBA claim unless A-weighting exists.
No AI/source classification overclaim.
Worker/JWT/TLS status is honest.
Diagrams match current source and deployment.
```
