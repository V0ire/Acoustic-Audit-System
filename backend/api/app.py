import os
import io
import csv
from decimal import Decimal
from datetime import datetime

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Query
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://acoustic_user:acoustic_pass@127.0.0.1:5432/acoustic_db",
)

app = FastAPI(title="Acoustic Audit API", version="pro-upgrade-local")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def normalize_value(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def normalize_row(row):
    return {key: normalize_value(value) for key, value in dict(row).items()}


def db_conn():
    return psycopg2.connect(DATABASE_URL)


@app.get("/")
def root():
    return {
        "service": "Acoustic Audit API",
        "status": "ok",
    }


@app.get("/api/health")
def health():
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {
            "status": "ok",
            "database": "ok",
        }
    except Exception as exc:
        return {
            "status": "error",
            "database": "error",
            "detail": str(exc),
        }


@app.post("/api/login")
def login():
    return {
        "access_token": "local-dev-token",
        "token_type": "bearer",
        "note": "local stub login",
    }


@app.get("/api/devices")
def get_devices():
    query = """
        SELECT
            d.device_id,
            d.room,
            d.location,
            d.description,
            d.created_at,
            h.last_seen,
            h.status AS health_status,
            h.last_error,
            h.updated_at
        FROM devices d
        LEFT JOIN device_health h ON h.device_id = d.device_id
        ORDER BY d.device_id ASC
    """

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            rows = cur.fetchall()

    return {
        "devices": [normalize_row(row) for row in rows],
    }


@app.get("/api/measurements")
def get_measurements(
    device_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
):
    params = []
    where_clauses = []

    if device_id:
        where_clauses.append("m.device_id = %s")
        params.append(device_id)
        
    if start:
        where_clauses.append("m.measured_at >= %s")
        params.append(start)
        
    if end:
        where_clauses.append("m.measured_at <= %s")
        params.append(end)

    where_clause = ""
    if where_clauses:
        where_clause = "WHERE " + " AND ".join(where_clauses)

    params.append(limit)

    query = f"""
        SELECT 
            m.device_id, 
            d.room, 
            m.measured_at, 
            m.total_dba, 
            m.spl_avg_db,
            m.spl_max_db,
            m.calibration_offset_db,
            m.status,
            m.quality_flags,
            m.metric_type,
            m.weighting,
            m.window_seconds,
            m.schema_version,
            m.edge_version
        FROM measurements m
        JOIN devices d ON m.device_id = d.device_id
        {where_clause}
        ORDER BY m.measured_at DESC
        LIMIT %s
    """

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [normalize_row(row) for row in rows]


@app.get("/api/measurements/export.csv")
def export_measurements_csv(
    device_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    params = []
    where_clauses = []

    if device_id:
        where_clauses.append("m.device_id = %s")
        params.append(device_id)
    if start:
        where_clauses.append("m.measured_at >= %s")
        params.append(start)
    if end:
        where_clauses.append("m.measured_at <= %s")
        params.append(end)

    where_clause = ""
    if where_clauses:
        where_clause = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT 
            m.measured_at,
            m.device_id, 
            d.room, 
            m.spl_avg_db,
            m.spl_max_db,
            m.weighting,
            m.metric_type,
            m.status,
            m.calibration_offset_db,
            m.edge_version,
            m.quality_flags,
            m.window_seconds,
            m.schema_version
        FROM measurements m
        JOIN devices d ON m.device_id = d.device_id
        {where_clause}
        ORDER BY m.measured_at ASC
    """

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "measured_at", "device_id", "room", "spl_avg_db", "spl_max_db", 
        "weighting", "metric_type", "status", "calibration_offset_db", 
        "edge_version", "quality_flags", "window_seconds", "schema_version"
    ])
    
    for row in rows:
        norm_row = normalize_row(row)
        writer.writerow([
            norm_row.get("measured_at"),
            norm_row.get("device_id"),
            norm_row.get("room"),
            norm_row.get("spl_avg_db"),
            norm_row.get("spl_max_db"),
            norm_row.get("weighting"),
            norm_row.get("metric_type"),
            norm_row.get("status"),
            norm_row.get("calibration_offset_db"),
            norm_row.get("edge_version"),
            norm_row.get("quality_flags"),
            norm_row.get("window_seconds"),
            norm_row.get("schema_version")
        ])

    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=export.csv"})


@app.get("/api/reports/summary")
def get_report_summary(
    device_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    params = []
    where_clauses = []

    if device_id:
        where_clauses.append("device_id = %s")
        params.append(device_id)
    if start:
        where_clauses.append("measured_at >= %s")
        params.append(start)
    if end:
        where_clauses.append("measured_at <= %s")
        params.append(end)

    where_clause = ""
    if where_clauses:
        where_clause = "WHERE " + " AND ".join(where_clauses)

    query = f"""
        SELECT 
            measured_at,
            spl_avg_db,
            spl_max_db,
            total_dba,
            weighting,
            status,
            quality_flags
        FROM measurements
        {where_clause}
        ORDER BY measured_at ASC
    """

    with db_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            
    if not rows:
        return {
            "device_id": device_id,
            "start": start,
            "end": end,
            "sample_count": 0,
            "plain_summary": "No data available for the selected period."
        }

    spl_values = []
    max_values = []
    anomalies = []
    peak_times = []
    above_threshold_count = 0
    threshold_db = 65.0
    
    weighting_dist = {}
    status_dist = {}
    quality_dist = {}

    for row in rows:
        norm_row = normalize_row(row)
        # fallback to total_dba if spl_avg_db is missing
        val = norm_row.get("spl_avg_db") if norm_row.get("spl_avg_db") is not None else norm_row.get("total_dba")
        max_val = norm_row.get("spl_max_db") if norm_row.get("spl_max_db") is not None else val
        
        w = norm_row.get("weighting") or "unknown"
        weighting_dist[w] = weighting_dist.get(w, 0) + 1
        
        s = norm_row.get("status") or "ok"
        status_dist[s] = status_dist.get(s, 0) + 1
        
        q = norm_row.get("quality_flags")
        if q:
            if isinstance(q, str):
                import json
                try:
                    q = json.loads(q)
                except Exception:
                    q = {}
            if isinstance(q, dict):
                for k, v in q.items():
                    if v:
                        quality_dist[k] = quality_dist.get(k, 0) + 1

        if val is not None:
            spl_values.append(val)
        if max_val is not None:
            max_values.append(max_val)
            
        # check threshold
        if max_val is not None and max_val > threshold_db:
            above_threshold_count += 1
            anomalies.append({
                "measured_at": norm_row.get("measured_at"),
                "type": "threshold_exceeded",
                "reason": f"SPL exceeded {threshold_db} dB threshold"
            })
            peak_times.append({
                "measured_at": norm_row.get("measured_at"),
                "spl_max_db": max_val,
                "spl_avg_db": val
            })

    if not spl_values:
        return {
            "sample_count": len(rows),
            "plain_summary": "No valid numeric data found for the selected period."
        }

    avg_spl = round(sum(spl_values) / len(spl_values), 2)
    min_spl = round(min(spl_values), 2)
    max_spl = round(max(max_values), 2)
    
    # only keep top 5 peak times
    peak_times = sorted(peak_times, key=lambda x: x["spl_max_db"], reverse=True)[:5]
    # only keep top 10 anomalies
    anomalies = anomalies[:10]

    return {
        "device_id": device_id,
        "start": start,
        "end": end,
        "sample_count": len(rows),
        "avg_spl": avg_spl,
        "min_spl": min_spl,
        "max_spl": max_spl,
        "threshold_db": threshold_db,
        "above_threshold_count": above_threshold_count,
        "peak_times": peak_times,
        "anomalies": anomalies,
        "weighting_dist": weighting_dist,
        "status_dist": status_dist,
        "quality_dist": quality_dist,
        "plain_summary": f"During the selected period, the average SPL was {avg_spl} dB with a maximum of {max_spl} dB. {above_threshold_count} samples exceeded the {threshold_db} dB threshold."
    }
