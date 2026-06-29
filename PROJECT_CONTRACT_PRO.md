# PROJECT_CONTRACT_PRO.md — Acoustic Audit System Contract Lock

## 0. Purpose

This document is the shared technical contract for the one-day Pro Upgrade Sprint of the Acoustic Audit System.

All AI agents, Antigravity sessions, and human contributors must follow this document before editing code.

The goal is to upgrade the current MVP into a more defensible demo-grade pro system without overclaiming.

This file defines:

* terminology,
* MQTT topics,
* payload contract,
* edge-to-worker handshake,
* database/API mapping,
* status semantics,
* security targets,
* and what must not be changed casually.

---

## 1. Core Architecture

The target runtime pipeline is:

```text
Acoustic Environment
→ INMP441 / USB Microphone
→ Raspberry Pi Edge Node
→ Edge Signal Processing
→ MQTT Publisher
→ Mosquitto Broker on VPS
→ Ingestion Worker
→ PostgreSQL
→ FastAPI Backend
→ Nginx
→ Frontend Dashboard
```

The system must remain explainable as an Internet System / IoT project.

Do not redesign it into a different architecture without explicit approval.

---

## 2. Terminology Lock

### 2.1 MVP Measurement Naming

If A-weighting is not implemented and verified, use:

```text
SPL estimate
spl_avg_db
spl_max_db
flat SPL estimate
RMS-based SPL estimate
```

Do not use these as implemented claims unless A-weighting exists:

```text
certified dBA
IEC-compliant LAeq
industrial-grade sound level meter
```

### 2.2 A-weighting Naming

If A-weighting is implemented:

```text
A-weighted SPL estimate
LAeq estimate over window T
LAmax estimate over window T
```

Still do not claim certified compliance.

Allowed wording:

```text
The system estimates A-weighted sound level using an edge-side signal processing pipeline and calibration offset.
```

Forbidden wording:

```text
This device is a certified sound level meter.
```

---

## 3. Feature Status Labels

Every diagram and documentation update must use one of these labels:

```text
Implemented
Partial
Planned Pro
Future
Missing in Source
```

Do not present planned work as implemented.

---

## 4. MQTT Topic Contract

### 4.1 Measurement Topic

```text
acoustic/devices/{device_id}/measurements
```

Example:

```text
acoustic/devices/ACOUSTIC-PI-001/measurements
```

QoS:

```text
QoS 1
```

Publisher:

```text
Edge device
```

Subscriber:

```text
Ingestion worker
```

---

### 4.2 Heartbeat Topic

```text
acoustic/devices/{device_id}/heartbeat
```

QoS:

```text
QoS 0
```

Purpose:

```text
Frequent lightweight "I am alive" message.
```

---

### 4.3 Status Topic

```text
acoustic/devices/{device_id}/status
```

QoS:

```text
QoS 1
```

Retain:

```text
true
```

Purpose:

```text
Current device state such as online, offline, stale, mic_error, low_signal, clipping.
```

---

### 4.4 Events Topic

```text
acoustic/devices/{device_id}/events
```

QoS:

```text
QoS 1
```

Purpose:

```text
Optional event messages such as threshold exceeded, mic error, calibration warning.
```

---

### 4.5 Commands Topic

Do not implement or document the commands topic as active unless the edge has a command handler.

Future-only topic:

```text
acoustic/devices/{device_id}/commands
```

Status:

```text
Future
```

Reason:

```text
Bidirectional MQTT requires edge-side subscription and command processing. Do not imply this exists unless implemented.
```

---

## 5. MQTT Security Contract

### 5.1 MVP Security

Minimum accepted MVP security:

```text
MQTT port: 1883
TLS: not required for MVP
Authentication: username/password
Anonymous access: disabled
PostgreSQL: internal only
FastAPI: internal behind Nginx
```

The MVP must not be called production-secure.

---

### 5.2 Pro Security

Target Pro MQTT security:

```text
MQTT port: 8883
TLS: enabled
Authentication: username/password per device
Topic ACL: enabled per device
Anonymous access: disabled
```

If domain and certificate are ready, implement MQTT TLS.

If domain/certificate setup blocks progress, keep MVP MQTT auth and document TLS as Planned Pro.

---

## 6. MQTT TLS Handshake Model

For Pro MQTT TLS mode:

```text
1. Edge opens TCP connection to broker domain on port 8883.
2. Broker presents TLS certificate.
3. Edge verifies certificate against CA or configured trust store.
4. Edge authenticates using MQTT username/password.
5. Broker checks password_file.
6. Broker checks ACL for topic permission.
7. Edge publishes measurement payload.
8. Worker receives message from broker.
```

If self-signed certificate is used:

```text
Edge must be configured with the CA certificate path.
```

If Let's Encrypt certificate is used:

```text
Edge should validate broker hostname against domain.
```

Do not disable certificate verification silently unless it is explicitly documented as temporary debugging.

---

## 7. Device Identity Contract

Canonical device id:

```text
ACOUSTIC-PI-001
```

Canonical room:

```text
R402
```

Rules:

```text
device_id must match devices.device_id in database.
device_id must match MQTT topic path.
device_id must match payload body.
```

Example correct mapping:

```text
Topic:
acoustic/devices/ACOUSTIC-PI-001/measurements

Payload:
"device_id": "ACOUSTIC-PI-001"

Database:
devices.device_id = "ACOUSTIC-PI-001"
```

If these do not match, the worker must reject or log the mismatch.

---

## 8. Payload Contract v1

### 8.1 Canonical Measurement Payload

This is the canonical payload for the Pro Upgrade Sprint:

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

---

### 8.2 Required Fields

```text
schema_version
device_id
room
timestamp
metric_type
weighting
spl_avg_db
spl_max_db
status
quality_flags
```

---

### 8.3 Optional Fields

```text
window_seconds
calibration_offset_db
raw_rms
sample_rate_hz
edge_version
firmware_version
mic_type
```

---

### 8.4 Legacy Compatibility

Existing code may still use:

```text
total_dba
```

The worker may accept `total_dba` temporarily and map it to:

```text
spl_avg_db
```

Compatibility rule:

```text
If spl_avg_db is missing and total_dba exists:
    spl_avg_db = total_dba
    log warning: legacy field total_dba used
```

Do not make `mechanical_confidence`, `human_activity_confidence`, or `source_hint` required for the current sprint.

---

## 9. Forbidden Payload Fields for MVP

These fields must not be presented as implemented unless a computation method exists:

```text
mechanical_confidence
human_activity_confidence
source_hint
predicted_source
noise_class
ai_detected_source
```

If the team wants to keep them for future schema compatibility, mark them as:

```text
Future
```

or leave them out of the payload.

---

## 10. Status Contract

Allowed status values:

```text
ok
online
offline
stale
mic_error
low_signal
clipping
mqtt_error
db_error
unknown
```

Measurement payload should usually use:

```text
ok
mic_error
low_signal
clipping
```

Status topic may use:

```text
online
offline
stale
mic_error
mqtt_error
unknown
```

---

## 11. Quality Flags Contract

Canonical structure:

```json
{
  "clipping": false,
  "low_signal": false,
  "mic_error": false
}
```

Optional extended structure:

```json
{
  "clipping": false,
  "low_signal": false,
  "mic_error": false,
  "calibration_missing": false,
  "time_unsynced": false
}
```

Worker must tolerate missing optional flags.

Worker must reject malformed `quality_flags` if it is not an object.

---

## 12. Heartbeat Payload Contract

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

Heartbeat interval target:

```text
30 seconds
```

---

## 13. LWT Contract

MQTT Last Will and Testament must publish to:

```text
acoustic/devices/{device_id}/status
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

QoS:

```text
1
```

Retain:

```text
true
```

---

## 14. Worker Contract

Worker must:

```text
Connect to MQTT broker.
Subscribe to acoustic/devices/+/measurements.
Optionally subscribe to heartbeat and status topics.
Parse JSON safely.
Validate required fields.
Reject malformed payloads without crashing.
Normalize timestamp.
Insert measurements into PostgreSQL.
Update device health if implemented.
Log accepted and rejected messages.
Reconnect on MQTT/DB errors.
```

Worker must not:

```text
Crash on invalid JSON.
Use string interpolation for SQL.
Assume optional fields exist.
Invent confidence/source fields.
```

---

## 15. Database Mapping Contract

Canonical measurement fields:

```text
device_id or device_pk
measured_at
spl_avg_db
spl_max_db
calibration_offset_db
status
quality_flags
created_at
```

Legacy compatible field:

```text
total_dba
```

If database still uses `total_dba`, the worker should temporarily map:

```text
spl_avg_db → total_dba
```

Documentation must clarify:

```text
Current DB field may be legacy total_dba.
Pro naming is spl_avg_db / spl_max_db.
```

---

## 16. API Contract

Minimum current API:

```text
GET  /api/health
GET  /api/measurements
GET  /api/devices
POST /api/login
```

Pro API target:

```text
GET /api/measurements/latest
GET /api/measurements/summary
GET /api/devices/{device_id}/health
GET /api/devices/{device_id}/calibration
GET /api/alerts
GET /api/ai/reports
```

If JWT is stubbed, documentation must say:

```text
JWT authentication is planned or partial.
```

Do not claim API is JWT-secured unless unauthorized requests return 401 and valid token requests return 200.

---

## 17. Frontend Contract

Dashboard must prioritize:

```text
Current SPL average card
SPL max card
Sensor status card
Last seen timestamp
Time-series chart
Threshold line
Calibration status panel
Recent measurements table
```

Optional:

```text
AI report panel
CSV export
Multi-device comparison
```

Do not show mechanical/human confidence cards unless those values are produced by a defined algorithm.

---

## 18. AI Contract

AI must be framed as:

```text
LLM-assisted acoustic audit reporting
```

AI must not be framed as:

```text
source classifier
audio classifier
mechanical/human detector
```

AI input should be structured database summary, not raw audio.

Example input:

```json
{
  "device_id": "ACOUSTIC-PI-001",
  "room": "R402",
  "period": "last_24_hours",
  "spl_avg_db": 58.2,
  "spl_max_db": 74.1,
  "threshold_exceedances": 3,
  "stale_count": 0,
  "quality_issues": []
}
```

AI output:

```text
summary
notable events
possible interpretation
recommendations
risk_level
```

---

## 19. Stop Conditions

Agents must stop and ask before continuing if:

```text
Changing MQTT topic names.
Changing required payload fields.
Removing backwards compatibility for total_dba.
Changing database schema destructively.
Removing existing working endpoints.
Committing secrets.
Changing stack from FastAPI/PostgreSQL/Mosquitto.
Adding React/Next/Vite without approval.
Adding source classification claims.
Claiming certified dBA.
```

---

## 20. Final Rule

Optimize for:

```text
contract-safe > feature-rich
demoable > perfect
honest > impressive
working pipeline > isolated polish
```
