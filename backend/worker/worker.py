import json
import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
import paho.mqtt.client as mqtt

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://acoustic_user:acoustic_pass@127.0.0.1:5432/acoustic_db",
)

MQTT_HOST = os.getenv("MQTT_HOST", "127.0.0.1")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "acoustic/devices/+/measurements")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "acoustic-worker-local")


def utc_now():
    return datetime.now(timezone.utc)


def parse_timestamp(value):
    if value is None or str(value).strip() == "":
        return utc_now()

    try:
        value = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return utc_now()


def extract_device_id(topic, payload):
    if payload.get("device_id"):
        return str(payload["device_id"])

    parts = topic.split("/")
    if len(parts) >= 3 and parts[0] == "acoustic" and parts[1] == "devices":
        return parts[2]

    return "UNKNOWN-DEVICE"


def to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def ensure_device(cur, device_id, room):
    cur.execute(
        """
        INSERT INTO devices (device_id, room, location, description)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (device_id) DO UPDATE
        SET room = EXCLUDED.room
        """,
        (device_id, room or "unknown", "auto-created", "Auto-created by MQTT worker"),
    )


def insert_measurement(topic, payload):
    device_id = extract_device_id(topic, payload)
    room = payload.get("room") or "unknown"
    measured_at = parse_timestamp(payload.get("timestamp") or payload.get("measured_at"))
    if measured_at is None:
        measured_at = utc_now()

    spl_avg_db = to_float(payload.get("spl_avg_db"))
    spl_max_db = to_float(payload.get("spl_max_db"))

    legacy_total_dba = to_float(payload.get("total_dba"))
    if spl_avg_db is None and legacy_total_dba is not None:
        spl_avg_db = legacy_total_dba
    if spl_max_db is None:
        spl_max_db = spl_avg_db

    quality_flags = payload.get("quality_flags")
    if not isinstance(quality_flags, dict):
        quality_flags = {}

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            ensure_device(cur, device_id, room)

            cur.execute(
                """
                INSERT INTO measurements (
                    device_id,
                    room,
                    measured_at,
                    schema_version,
                    metric_type,
                    weighting,
                    window_seconds,
                    spl_avg_db,
                    spl_max_db,
                    calibration_offset_db,
                    status,
                    quality_flags,
                    edge_version,
                    total_dba
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s
                )
                """,
                (
                    device_id,
                    room,
                    measured_at,
                    payload.get("schema_version", "1.0"),
                    payload.get("metric_type", "spl_estimate"),
                    payload.get("weighting", "flat"),
                    to_float(payload.get("window_seconds")),
                    spl_avg_db,
                    spl_max_db,
                    to_float(payload.get("calibration_offset_db")),
                    payload.get("status", "ok"),
                    json.dumps(quality_flags),
                    payload.get("edge_version"),
                    legacy_total_dba,
                ),
            )

            cur.execute(
                """
                INSERT INTO device_health (device_id, last_seen, status, last_error, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (device_id) DO UPDATE
                SET last_seen = EXCLUDED.last_seen,
                    status = EXCLUDED.status,
                    last_error = EXCLUDED.last_error,
                    updated_at = NOW()
                """,
                (
                    device_id,
                    measured_at,
                    payload.get("status", "ok"),
                    payload.get("reason"),
                ),
            )

        conn.commit()

    print(f"[worker] inserted measurement device={device_id} spl_avg_db={spl_avg_db}")


def update_device_health(topic, payload):
    device_id = extract_device_id(topic, payload)
    room = payload.get("room") or "unknown"
    
    last_seen = parse_timestamp(payload.get("timestamp") or payload.get("measured_at"))
    if last_seen is None:
        last_seen = utc_now()
        
    status = payload.get("status", "ok")
    last_error = payload.get("reason")
    
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            ensure_device(cur, device_id, room)
            
            cur.execute(
                """
                INSERT INTO device_health (device_id, last_seen, status, last_error, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (device_id) DO UPDATE
                SET last_seen = EXCLUDED.last_seen,
                    status = EXCLUDED.status,
                    last_error = EXCLUDED.last_error,
                    updated_at = NOW()
                """,
                (
                    device_id,
                    last_seen,
                    status,
                    last_error,
                ),
            )
        conn.commit()
    print(f"[worker] updated device_health device={device_id} status={status}")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[worker] connected to MQTT {MQTT_HOST}:{MQTT_PORT}")
        print(f"[worker] subscribing to {MQTT_TOPIC}")
        client.subscribe(MQTT_TOPIC, qos=1)
        client.subscribe("acoustic/devices/+/heartbeat", qos=1)
        client.subscribe("acoustic/devices/+/status", qos=1)
    else:
        print(f"[worker] MQTT connection failed rc={rc}")


def on_message(client, userdata, msg):
    raw = msg.payload.decode("utf-8", errors="replace")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"[worker] malformed JSON ignored topic={msg.topic} error={exc}")
        return

    try:
        if msg.topic.endswith("/heartbeat") or msg.topic.endswith("/status"):
            update_device_health(msg.topic, payload)
        else:
            insert_measurement(msg.topic, payload)
    except Exception as exc:
        print(f"[worker] insert failed topic={msg.topic} error={exc}")


def make_client():
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id=MQTT_CLIENT_ID,
        )
    else:
        client = mqtt.Client(client_id=MQTT_CLIENT_ID)

    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message
    return client


def main():
    print("[worker] starting")
    client = make_client()
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
