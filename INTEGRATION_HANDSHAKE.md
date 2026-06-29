# INTEGRATION_HANDSHAKE.md — Two-Person Integration Protocol

## 0. Purpose

This document defines the handshake between:

```text
Person 1: Edge & Secure MQTT Owner
Person 2: Ingestion, Database, API & Dashboard Owner
```

No integration should begin until both sides agree on the contract below.

This file prevents broken integration caused by mismatched topic names, payload fields, database columns, and frontend expectations.

---

## 1. Integration Principle

The system succeeds only if this chain works:

```text
Edge payload
→ MQTT topic
→ Broker authentication
→ Worker validation
→ Database insert
→ API response
→ Dashboard render
```

Every field must have the same meaning across the entire chain.

---

## 2. Contract Freeze Checklist

Before coding, both people must agree on:

```text
device_id
room
MQTT host
MQTT port
TLS mode
MQTT username
MQTT topics
measurement payload fields
status payload fields
database target fields
API response fields
dashboard labels
```

Do not change contract mid-sprint without telling the other person.

---

## 3. Shared Device Identity

Use this unless explicitly changed:

```text
DEVICE_ID=ACOUSTIC-PI-001
ROOM=R402
```

Topic prefix:

```text
acoustic/devices/ACOUSTIC-PI-001
```

---

## 4. MQTT Connection Modes

## 4.1 MVP Mode

```text
MQTT_HOST=<vps_ip_or_domain>
MQTT_PORT=1883
MQTT_USE_TLS=false
MQTT_USERNAME=<device_user>
MQTT_PASSWORD=<device_password>
```

Required:

```text
allow_anonymous false
```

---

## 4.2 Pro TLS Mode

```text
MQTT_HOST=<domain.my.id>
MQTT_PORT=8883
MQTT_USE_TLS=true
MQTT_TLS_CA_PATH=<ca_or_chain_path>
MQTT_TLS_INSECURE=false
MQTT_USERNAME=<device_user>
MQTT_PASSWORD=<device_password>
```

Required:

```text
certificate verification should be enabled
broker hostname should match certificate
```

---

## 5. Topic Handshake

Person 1 must publish to:

```text
acoustic/devices/ACOUSTIC-PI-001/measurements
acoustic/devices/ACOUSTIC-PI-001/heartbeat
acoustic/devices/ACOUSTIC-PI-001/status
```

Person 2 worker must subscribe to:

```text
acoustic/devices/+/measurements
```

Optional worker subscriptions:

```text
acoustic/devices/+/heartbeat
acoustic/devices/+/status
```

Do not use commands topic.

---

## 6. Measurement Payload Handshake

Canonical payload:

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

Allowed metric types:

```text
spl_estimate
a_weighted_estimate
```

Allowed weighting values:

```text
flat
A
```

---

## 7. Legacy Payload Compatibility

If edge still publishes:

```json
{
  "total_dba": 67.4
}
```

Person 2 must temporarily map:

```text
total_dba → spl_avg_db
```

But all new docs and UI should prefer:

```text
spl_avg_db
spl_max_db
```

This allows integration without breaking existing working code.

---

## 8. Forbidden Integration Fields

Do not require these fields:

```text
mechanical_confidence
human_activity_confidence
source_hint
```

They may only be reintroduced if there is a documented method:

```text
FFT heuristic
rule-based classifier
trained model
manual annotation
```

Without method, they are not part of current contract.

---

## 9. Heartbeat Payload

Person 1 publishes every 30 seconds:

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

Person 2 stores or derives:

```text
last_seen
status
updated_at
```

---

## 10. Status and LWT Payload

LWT payload:

```json
{
  "schema_version": "1.0",
  "device_id": "ACOUSTIC-PI-001",
  "timestamp": null,
  "status": "offline",
  "reason": "connection_lost"
}
```

Expected dashboard behavior:

```text
online  → green
stale   → yellow
offline → red
error   → red/orange
```

---

## 11. Database Handshake

Person 2 must confirm the actual database schema before coding.

Minimum compatible database fields:

```text
device_id
measured_at
total_dba or spl_avg_db
created_at
```

Pro fields if available:

```text
spl_avg_db
spl_max_db
calibration_offset_db
status
quality_flags
metric_type
weighting
```

If schema migration is needed, prefer additive migration.

Allowed additive changes:

```text
ADD COLUMN spl_avg_db
ADD COLUMN spl_max_db
ADD COLUMN calibration_offset_db
ADD COLUMN status
ADD COLUMN quality_flags
ADD COLUMN metric_type
ADD COLUMN weighting
```

Avoid destructive changes during sprint:

```text
DROP COLUMN
DROP TABLE
RENAME COLUMN
DELETE existing data
```

---

## 12. API Response Handshake

Frontend should receive measurements shaped like:

```json
{
  "device_id": "ACOUSTIC-PI-001",
  "room": "R402",
  "measured_at": "2026-06-27T18:00:00+07:00",
  "spl_avg_db": 58.2,
  "spl_max_db": 64.1,
  "calibration_offset_db": -14.0,
  "status": "ok",
  "quality_flags": {
    "clipping": false,
    "low_signal": false,
    "mic_error": false
  }
}
```

If API still returns `total_dba`, frontend may map:

```text
display_spl_avg = spl_avg_db || total_dba
```

Do not break existing dashboard while migrating field names.

---

## 13. Frontend Display Handshake

Dashboard labels must use:

```text
SPL Avg
SPL Max
Sensor Status
Last Seen
Calibration Offset
Metric Type
Weighting
```

Use `dBA` label only if A-weighting is implemented and `weighting = "A"`.

If `weighting = "flat"`:

```text
Display: SPL Estimate
```

---

## 14. End-to-End Acceptance Test

Run this exact flow after integration.

### 14.1 MQTT Observe

Subscribe:

```text
mosquitto_sub -h <host> -p <port> -u <user> -P <password> -t "acoustic/devices/+/measurements" -v
```

Expected:

```text
Valid JSON appears.
device_id is ACOUSTIC-PI-001.
spl_avg_db or total_dba exists.
```

---

### 14.2 Worker Observe

Worker logs should show:

```text
connected to MQTT
received message
validated payload
inserted measurement
```

Bad payload should show:

```text
rejected payload
```

Worker must keep running.

---

### 14.3 Database Observe

Query latest rows.

Expected:

```text
latest measurement exists
timestamp is recent
device id matches
SPL value is not null
```

---

### 14.4 API Observe

Expected:

```text
GET /api/health returns OK
GET /api/measurements returns recent data
GET /api/devices returns ACOUSTIC-PI-001
```

If JWT is implemented:

```text
without token → 401
with token → 200
```

If JWT is not implemented:

```text
document as stub/partial
```

---

### 14.5 Dashboard Observe

Expected:

```text
SPL card updates
SPL max card updates
chart shows data
last seen is recent
sensor status is online
calibration offset is visible
no undefined confidence/source cards
```

---

### 14.6 Offline Test

Stop edge.

Expected:

```text
heartbeat stops
last_seen grows older
dashboard eventually shows stale/offline
LWT may publish offline status
```

---

## 15. Merge Checklist

Before merge:

```text
No secrets committed.
Payload contract preserved.
Topic contract preserved.
Worker handles legacy and new fields.
Dashboard does not overclaim dBA.
Docs mention current vs pro status.
Screenshots/logs captured.
```

---

## 16. Human Coordination Rule

Person 1 cannot change payload field names without telling Person 2.

Person 2 cannot change database/API field names without telling Person 1.

If either side changes a shared contract, update this file first.

---

## 17. Final Definition of Done

The sprint is done when:

```text
Edge publishes valid measurement.
MQTT accepts authenticated device.
Worker inserts data.
API exposes data.
Dashboard renders data.
Status and last_seen work.
Calibration info is visible.
Terminology is honest.
Known gaps are documented.
```
