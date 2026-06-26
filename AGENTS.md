# AGENTS.md — Antigravity Operating Manual
## The Acoustic Audit System

> This file is written for Antigravity / AI coding agents working inside this repository.  
> Read this file first before editing any code.  
> The goal is to keep the project coherent, demoable, and aligned with the course requirements.

---

## 0. Agent Mission

You are working on **The Acoustic Audit System**, an academic IoT project for **Rekayasa Sistem Internet — Semester 4 Teknik Elektro**.

Your mission is to help implement an **MVP edge-to-cloud acoustic monitoring system**:

```text
Raspberry Pi / Dummy Publisher
→ MQTT Broker
→ MQTT Worker
→ PostgreSQL
→ REST API + JWT
→ Frontend Dashboard
```

The system converts room noise into numerical metrics, sends them through MQTT, stores them in PostgreSQL, exposes them through a JWT-protected REST API, and displays them on a web dashboard.

This is **not** a certified sound level meter, not a real-time audio streaming system, and not a production SaaS platform. It is a complete, explainable, demoable Internet system prototype.

---

## 1. Repository

GitHub repository:

```text
https://github.com/V0ire/Acoustic-Audit-System
```

Expected monorepo structure:

```text
/
├── README.md
├── AGENTS.md
├── IDD.md
├── .env.example
├── .gitignore
├── backend/
│   ├── api/
│   └── worker/
├── database/
│   ├── schema.sql
│   └── seed_admin.sql
├── docs/
│   ├── api-contract.md
│   ├── dummy-payload.json
│   └── DESIGN-vercel.md
├── edge/
└── deployment/
    ├── systemd/
    ├── nginx/
    ├── mosquitto/
    └── logrotate/
```

If a folder/file is missing, create it only when needed for the current milestone.

---

## 2. Read Order for the Agent

Before changing files, read in this order:

```text
1. AGENTS.md
2. IDD.md
3. PROJECT_CONTRACT.md, if it exists
4. database/schema.sql
5. docs/api-contract.md, if it exists
6. docs/DESIGN-vercel.md, if working on frontend UI
7. The component folder relevant to the task
```

If there is a conflict between files:

```text
AGENTS.md > PROJECT_CONTRACT.md > IDD.md > component README > code comments
```

If a requested change conflicts with the contract, stop and ask for confirmation.

---

## 3. Non-Negotiable Project Rules

Do not violate these rules.

### 3.1 Pipeline First

A dummy value flowing end-to-end is more important than a perfect sensor that talks to nothing.

Do not prioritize FFT, calibration, UI polish, TLS, WebSocket, heatmap, PDF report, or advanced classification before the dummy pipeline works.

M1 target:

```text
demo-simulate.py
→ MQTT
→ Worker
→ PostgreSQL
→ API
→ Dashboard
```

### 3.2 No Overclaiming

Use honest names:

```text
Use: total_dba
Avoid: certified_spl

Use: source_hint
Avoid: predicted_source

Use: mechanical_like
Avoid: this_is_AC
```

This system estimates acoustic metrics. It does not certify SPL and does not definitively classify sound sources.

### 3.3 Failure-Aware

Every service must fail gracefully.

```text
Bad MQTT payload       → reject + log, do not crash
MQTT disconnect        → reconnect
Database down          → log + return error, do not corrupt data
API unauthorized       → return 401
Frontend no data       → show empty state / stale state
Sensor unavailable     → log + retry
```

### 3.4 No Secrets in Git

Never commit:

```text
.env
real MQTT password
real database password
real JWT_SECRET
private VPS IP credentials
```

Use `.env.example` with placeholder values.

### 3.5 Do Not Change Shared Contracts Casually

Do not change these without explicit Team Lead approval:

```text
MQTT topic
JSON payload field names
database schema
API route names
authentication behavior
repository structure
```

---

## 4. Locked Tech Stack

Use this stack unless explicitly instructed otherwise:

| Layer | Stack |
|---|---|
| Edge | Python 3 |
| Sensor | INMP441 I2S microphone |
| Edge board | Raspberry Pi 3B / 4 |
| MQTT client | paho-mqtt |
| Broker | Eclipse Mosquitto |
| Worker | Python 3 |
| Database | PostgreSQL |
| SQL style | Raw SQL with parameterized queries |
| API | Python FastAPI |
| Auth | bcrypt + JWT |
| Frontend | HTML + CSS + JavaScript |
| Chart | Chart.js |
| Reverse proxy | Nginx |
| Process manager | systemd |
| Deployment | Manual VPS Linux deployment |
| PaaS | Not allowed |
| Firebase | Not allowed |
| Node-RED | Not allowed |

Do not switch API to Node.js, Express, Flask, Prisma, Firebase, Supabase, or an ORM unless explicitly instructed.

---

## 5. Hardware and Physical Components

### 5.1 Required Hardware

```text
Raspberry Pi 3B+ or Raspberry Pi 4
INMP441 I2S MEMS microphone
MicroSD card 16GB or 32GB Class 10/A1
5V 3A Raspberry Pi power supply
Female-to-female jumper wires
Card reader
LAN cable or stable Wi-Fi/hotspot
VPS with public IP
Laptop for development and SSH
```

### 5.2 Recommended Hardware

```text
Spare INMP441 microphone
Simple case / mounting board
Heatsink for Raspberry Pi
Basic sound level meter or phone app for rough calibration
Power extension cable
```

### 5.3 INMP441 Wiring Reference

Verify the exact board labels before wiring.

```text
INMP441 VDD  → Raspberry Pi 3.3V
INMP441 GND  → Raspberry Pi GND
INMP441 SCK  → GPIO18 / PCM_CLK
INMP441 WS   → GPIO19 / PCM_FS
INMP441 SD   → GPIO20 / PCM_DIN
INMP441 L/R  → GND for left channel or 3.3V for right channel
```

If sensor setup blocks progress, do not stop the project. Use `edge/demo-simulate.py` as fallback.

---

## 6. System Architecture

### 6.1 Runtime Data Flow

```text
[Room Sound]
     ↓
[INMP441 I2S Microphone]
     ↓
[Raspberry Pi — Python Edge Service]
     ↓  RMS / dB estimate / optional FFT features
[MQTT Publish QoS 1]
     ↓
[Mosquitto Broker on VPS]
     ↓
[Python MQTT Worker]
     ↓  JSON validation + parameterized SQL INSERT
[PostgreSQL]
     ↓  raw SQL SELECT
[FastAPI REST API]
     ↓  JWT-protected JSON response
[Frontend Dashboard]
```

### 6.2 Runtime Services

On VPS:

```text
mosquitto.service
postgresql.service
acoustic-worker.service
acoustic-api.service
nginx.service
```

On Raspberry Pi:

```text
acoustic-edge.service
```

---

## 7. MQTT Contract

```text
Broker: Mosquitto on VPS
Port: 1883
TLS: Not in MVP
Auth: username/password
Anonymous access: must be disabled
QoS: 1
```

Publisher topic:

```text
acoustic/devices/ACOUSTIC-PI-001/measurements
```

Worker subscriber topic:

```text
acoustic/devices/+/measurements
```

MVP uses port `1883` without TLS. Do not claim this is production-secure. Frame it as an accepted MVP limitation with username/password authentication. TLS on port 8883 is a planned enhancement.

---

## 8. JSON Payload Contract

### 8.1 Minimum Valid Payload

```json
{
  "device_id": "ACOUSTIC-PI-001",
  "room": "R402",
  "timestamp": "2026-06-04T10:15:00+07:00",
  "total_dba": 67.4,
  "mechanical_confidence": 0.81,
  "human_activity_confidence": 0.29
}
```

### 8.2 Full Payload

```json
{
  "device_id": "ACOUSTIC-PI-001",
  "room": "R402",
  "timestamp": "2026-06-04T10:15:00+07:00",
  "total_dba": 67.4,
  "low_freq_ratio": 0.58,
  "speech_band_ratio": 0.22,
  "spectral_flatness": 0.31,
  "spectral_flux": 0.12,
  "mechanical_confidence": 0.81,
  "human_activity_confidence": 0.29,
  "source_hint": "mechanical_like"
}
```

### 8.3 Required Fields

| Field | Type | Rule |
|---|---|---|
| `device_id` | string | required, must exist in `devices.device_id` |
| `room` | string | required, non-empty |
| `timestamp` | string | required, ISO 8601 with timezone offset |
| `total_dba` | number | required |
| `mechanical_confidence` | number | required, 0.0–1.0 |
| `human_activity_confidence` | number | required, 0.0–1.0 |

### 8.4 Optional Fields

| Field | Type | Notes |
|---|---|---|
| `low_freq_ratio` | number | optional FFT feature |
| `speech_band_ratio` | number | optional FFT feature |
| `spectral_flatness` | number | optional FFT feature |
| `spectral_flux` | number | optional FFT feature |
| `source_hint` | string | `mechanical_like`, `human_activity_like`, or `mixed_or_unknown` |

Worker must reject malformed payloads and continue running.

---

## 9. Database Contract

Use PostgreSQL.

The required tables are:

```text
devices
users
measurements
```

Expected schema:

```sql
CREATE TABLE devices (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100) UNIQUE NOT NULL,
    room VARCHAR(100) NOT NULL,
    location TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) DEFAULT 'admin',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE measurements (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(100) NOT NULL REFERENCES devices(device_id),
    measured_at TIMESTAMPTZ NOT NULL,
    total_dba NUMERIC(6,2) NOT NULL,
    low_freq_ratio NUMERIC(5,3),
    speech_band_ratio NUMERIC(5,3),
    spectral_flatness NUMERIC(5,3),
    spectral_flux NUMERIC(5,3),
    mechanical_confidence NUMERIC(5,3),
    human_activity_confidence NUMERIC(5,3),
    source_hint VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_measurements_device_time
ON measurements (device_id, measured_at DESC);
```

Rules:

```text
Use TIMESTAMPTZ, not plain TIMESTAMP.
Use parameterized SQL.
Do not expose PostgreSQL publicly.
Do not use ORM unless explicitly instructed.
Do not store plain passwords.
```

---

## 10. REST API Contract

Use Python FastAPI.

Base API path:

```text
/api
```

Required endpoints:

| Method | Route | Auth | Purpose |
|---|---|---|---|
| POST | `/api/login` | none | verify user and return JWT |
| GET | `/api/measurements` | JWT | return historical measurement data |
| GET | `/api/devices` | JWT | return registered devices |
| GET | `/api/health` | none | health check |

Auth behavior:

```text
GET /api/measurements without JWT → 401
GET /api/devices without JWT → 401
Invalid JWT → 401
Expired JWT → 401
Valid JWT → 200
```

Security rules:

```text
JWT_SECRET must come from environment variable.
Passwords must be verified with bcrypt.
SQL must be parameterized.
API should listen on 127.0.0.1:8000 behind Nginx.
CORS "*" is acceptable for local demo only.
```

---

## 11. Frontend Dashboard Contract

Use pure HTML, CSS, JavaScript, and Chart.js.

Do not add React, Next.js, Vite, Tailwind, or heavy frontend frameworks unless explicitly asked.

Required views:

```text
Login view
Dashboard view
```

Required dashboard components:

```text
Latest dBA card
Mechanical confidence card
Human activity confidence card
Historical total_dba line chart
Recent measurements table
Compliance badge
Last seen timestamp
Online / stale indicator
Connection error state
Empty data state
```

Polling:

```javascript
setInterval(fetchMeasurements, 5000);
```

Authorization header:

```text
Authorization: Bearer <token>
```

Stale indicator:

```text
If newest measured_at is older than 120 seconds:
DATA STALE / SENSOR OFFLINE
```

Compliance badge logic:

```text
total_dba < 55  → Normal
total_dba < 65  → Warning
total_dba >= 65 → High Noise Exposure
```

Visual design direction:

```text
clean white/near-white background
black ink primary text
subtle gray borders
subtle card shadows
rounded cards
monospace for technical labels
minimal but professional dashboard
```

Use `docs/DESIGN-vercel.md` if present. Do not overdecorate.

---

## 12. Edge Service Contract

M1 dummy publisher:

```text
edge/demo-simulate.py
```

Purpose:

```text
Publish valid dummy JSON to MQTT every 5 seconds.
```

This is required as fallback if Raspberry Pi / INMP441 fails.

M2 real edge service:

```text
edge/acoustic_edge.py
```

Purpose:

```text
Read audio from INMP441
Compute RMS
Estimate dB
Optionally compute FFT features
Publish JSON to MQTT
```

Acoustic metric formula:

```text
dB_est = 20 * log10(RMS + ε) + C_cal
```

Do not claim certified dBA.

Edge constraints:

```text
Do not store raw audio.
Do not transmit raw audio.
Use Asia/Jakarta timezone.
Use NTP on Raspberry Pi.
Use MQTT credentials from env/config.
Reconnect when MQTT connection drops.
```

---

## 13. Worker Contract

Create or maintain:

```text
backend/worker/worker.py
```

Purpose:

```text
Subscribe to MQTT
Parse JSON
Validate schema
Insert into PostgreSQL
Log accepted/rejected payloads
Continue running on errors
```

Rules:

```text
Use paho-mqtt.
Use psycopg2 or psycopg2-binary.
Use jsonschema or explicit validation.
Use parameterized SQL only.
Do not use string interpolation for SQL.
Do not crash on invalid JSON.
```

Expected log examples:

```text
[worker] connected to MQTT broker
[worker] inserted measurement device=ACOUSTIC-PI-001 room=R402 dBA=67.4
[worker] rejected payload: missing required field total_dba
```

---

## 14. Deployment Contract

Target VPS:

```text
Ubuntu 22.04 or Ubuntu 24.04
1–2 GB RAM minimum
Public IP
SSH access
```

Public ports:

```text
22    SSH
80    HTTP
1883  MQTT
```

Internal only:

```text
5432  PostgreSQL
8000  FastAPI internal port
```

Expected systemd services:

```text
deployment/systemd/acoustic-worker.service
deployment/systemd/acoustic-api.service
deployment/systemd/acoustic-edge.service
```

All should use:

```text
Restart=always
RestartSec=5
```

Nginx should:

```text
Serve /frontend as static site
Reverse proxy /api/ to http://127.0.0.1:8000/api/
```

Mosquitto should:

```text
Disable anonymous access
Use password_file
Listen on port 1883
```

---

## 15. Environment Files

Use `.env.example` for placeholders.

Edge `.env.example`:

```env
MQTT_HOST=replace_with_vps_ip
MQTT_PORT=1883
MQTT_USERNAME=acoustic_device
MQTT_PASSWORD=replace_password
MQTT_TOPIC=acoustic/devices/ACOUSTIC-PI-001/measurements
DEVICE_ID=ACOUSTIC-PI-001
ROOM=R402
CALIBRATION_OFFSET=0
```

Worker `.env.example`:

```env
DATABASE_URL=postgresql://acoustic_user:replace_password@localhost:5432/acoustic_db
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_USERNAME=acoustic_device
MQTT_PASSWORD=replace_password
MQTT_TOPIC=acoustic/devices/+/measurements
```

API `.env.example`:

```env
JWT_SECRET=replace_with_long_random_secret
DATABASE_URL=postgresql://acoustic_user:replace_password@localhost:5432/acoustic_db
CORS_ORIGIN=http://localhost
```

Never create real `.env` values unless the user explicitly asks and understands that these should not be committed.

---

## 16. Milestone Plan

### M0 — Contract Lock

Goal:

```text
Repository structure, JSON payload, MQTT topic, DB schema, and API routes are fixed.
```

Tasks:

```text
Confirm repo structure
Confirm database/schema.sql
Confirm dummy payload
Confirm API contract
Confirm .env.example files
Confirm task ownership
```

### M1 — Dummy End-to-End

Goal:

```text
Dummy data appears on dashboard.
```

Build order:

```text
1. database/schema.sql
2. edge/demo-simulate.py
3. backend/worker/worker.py
4. backend/api/app.py
5. frontend/index.html + style.css + app.js
```

Acceptance test:

```text
Run simulator
Worker receives MQTT
PostgreSQL contains rows
API returns rows with valid JWT
Dashboard displays rows
```

### M2 — Real Sensor Online

Goal:

```text
Raspberry Pi + INMP441 sends real total_dba to dashboard.
```

Tasks:

```text
Configure I2S on Pi
Read INMP441 audio
Compute RMS and dB estimate
Publish real payload
Keep demo-simulate.py as fallback
```

### M3 — Security Minimum

Goal:

```text
The system has basic auth and safe data handling.
```

Tasks:

```text
Mosquitto auth enabled
Anonymous MQTT rejected
bcrypt login
JWT middleware
401 without token
JWT_SECRET from env
parameterized SQL
PostgreSQL not public
```

### M4 — Demo Ready

Goal:

```text
The system can survive demo conditions.
```

Tasks:

```text
systemd services
Nginx config
Dashboard polish
last_seen and stale indicator
logs visible with journalctl
fallback simulator ready
README/demo guide
```

---

## 17. What the Agent Should Do First

When starting from the current repository, do **not** immediately build everything.

First action:

```text
Inspect repository structure.
List missing files.
Compare current files to this AGENTS.md.
Propose the smallest next step for M1 Dummy End-to-End.
```

If asked to implement immediately, implement in this order:

```text
1. Repair/create database/schema.sql if needed
2. Create .env.example files
3. Create edge/demo-simulate.py
4. Create backend/worker/worker.py
5. Create backend/api/app.py
6. Create frontend/index.html/style.css/app.js
7. Create deployment templates
8. Update README with run/test steps
```

Do not create advanced features until the above works.

---

## 18. Component Ownership

Team structure:

```text
TL / Team Lead      → MQTT Worker + Integration + QA akhir
Expert A           → Edge Service + Raspberry Pi + INMP441
Biasa 1            → REST API + JWT
Biasa 2            → Frontend Dashboard
Biasa 3            → Database + Deployment
```

No one is assigned only to QA, documentation, or slides. Every member owns a working technical component.

---

## 19. Branching Rules

Use simple branches:

```text
main
feature/edge
feature/worker
feature/api
feature/frontend
feature/database-deployment
```

Do not push directly to `main`.

All changes should be made in the relevant feature branch.

---

## 20. Pull Request Rules

Every PR must include:

```text
What changed
Files changed
How to run
How to test
Screenshots/logs if relevant
Known risks
```

Do not merge if:

```text
The code cannot be explained
The test was not run
The change silently modifies shared contracts
Secrets are committed
The feature breaks M1 pipeline
```

---

## 21. Testing Guide

### 21.1 Test MQTT Publish

```bash
mosquitto_sub -h <host> -t "acoustic/devices/+/measurements" -u <user> -P <password>
```

Then run:

```bash
python edge/demo-simulate.py
```

Expected:

```text
JSON payload appears every 5 seconds.
```

### 21.2 Test Worker Insert

```bash
python backend/worker/worker.py
```

Expected:

```text
Worker logs inserted measurement.
```

Check database:

```bash
psql -U acoustic_user -d acoustic_db -c "SELECT * FROM measurements ORDER BY created_at DESC LIMIT 5;"
```

### 21.3 Test API Auth

Without token:

```bash
curl http://localhost:8000/api/measurements
```

Expected:

```text
401 Unauthorized
```

With token:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/measurements
```

Expected:

```text
JSON array
```

### 21.4 Test Frontend

```text
Open dashboard
Login
Chart appears
Latest dBA appears
Recent measurements table appears
last_seen appears
stale indicator works if data stops for 120 seconds
```

---

## 22. Coding Standards

Python:

```text
Use clear functions.
Use environment variables for config.
Use parameterized SQL.
Log meaningful messages.
Handle exceptions.
Keep files simple for students to understand.
```

JavaScript:

```text
Use plain JS.
Keep API_BASE configurable.
Handle loading/error/empty states.
Do not add frameworks unless requested.
```

SQL:

```text
Use schema.sql as source of truth.
Use TIMESTAMPTZ.
Use indexes for time-series queries.
Do not store plain text passwords.
```

---

## 23. What Not to Build Yet

Do not build these before M1 and M3 are stable:

```text
MQTT TLS / MQTTS 8883
WebSocket live streaming
PDF report generator
Heatmap
Machine learning classifier
Advanced source separation
Local buffering queue
Multi-tenant user system
Fancy animations
Full React/Next.js migration
Docker/Kubernetes
```

These can be planned enhancements, not MVP blockers.

---

## 24. Known Risks and Required Mitigations

| Risk | Mitigation |
|---|---|
| INMP441 setup fails | Use demo-simulate.py |
| Campus network blocks MQTT 1883 | Use hotspot/LAN/VPS firewall check |
| MQTT without TLS | Document as MVP limitation |
| Bad JSON breaks worker | Validate payload and continue |
| Pi wrong timestamp | Use NTP + Asia/Jakarta timezone |
| Dashboard shows stale data as live | Add last_seen + stale indicator |
| PostgreSQL exposed publicly | Bind local / block with firewall |
| AI changes contracts accidentally | Follow AGENTS.md and ask before changes |

---

## 25. Demo Flow

The final demo should show:

```text
1. Problem: noise complaints are subjective
2. Edge device or simulator
3. MQTT live feed with mosquitto_sub
4. Worker logs with journalctl
5. PostgreSQL latest rows
6. API rejects unauthorized request
7. Login returns JWT
8. Dashboard shows chart and latest dBA
9. Sound/clap changes the value
10. Limitations and future improvements
```

Fallback:

```bash
python edge/demo-simulate.py
```

If hardware fails, continue demo using simulator.

---

## 26. Final Agent Instruction

Always optimize for:

```text
demoable > perfect
simple > clever
explainable > advanced
contract-safe > feature-rich
MVP pipeline > isolated component quality
```

Before editing, ask yourself:

```text
Does this help M1/M2/M3/M4?
Does this preserve JSON/API/DB contracts?
Can a semester-4 student explain this?
Can this be tested with a simple command?
Does this avoid secrets?
```

If the answer is no, do not implement it yet.
