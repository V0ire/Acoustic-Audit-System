import os
import json
import logging
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
import psycopg2
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://acoustic_user:password@localhost:5432/acoustic_db")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

def get_db():
    return psycopg2.connect(DB_URL)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT broker")
        client.subscribe("acoustic/devices/+/measurements")
        client.subscribe("acoustic/devices/+/heartbeat")
        client.subscribe("acoustic/devices/+/status")
    else:
        logging.error(f"Failed to connect to MQTT, return code {rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode('utf-8'))
    except Exception as e:
        logging.error(f"Rejected payload (malformed JSON): {e}")
        return

    topic = msg.topic
    parts = topic.split('/')
    if len(parts) < 4:
        return
    device_id = parts[2]
    msg_type = parts[3]

    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()

        if msg_type == "measurements":
            # Validate required fields
            if "device_id" not in payload or payload["device_id"] != device_id:
                logging.error("Rejected payload: missing or mismatched device_id")
                return
            if "room" not in payload:
                logging.error("Rejected payload: missing room")
                return
            if "timestamp" not in payload:
                logging.error("Rejected payload: missing timestamp")
                return
            
            # Legacy fallback
            spl_avg_db = payload.get("spl_avg_db")
            total_dba = payload.get("total_dba")
            
            if spl_avg_db is None and total_dba is not None:
                spl_avg_db = total_dba
                logging.warning(f"Legacy field total_dba used for device {device_id}")
            elif spl_avg_db is not None and total_dba is None:
                total_dba = spl_avg_db # To satisfy schema NOT NULL constraint if any
                
            if spl_avg_db is None:
                logging.error("Rejected payload: missing spl_avg_db or total_dba")
                return

            measured_at = payload["timestamp"]
            spl_max_db = payload.get("spl_max_db")
            calibration_offset_db = payload.get("calibration_offset_db")
            status = payload.get("status", "ok")
            quality_flags = payload.get("quality_flags")
            metric_type = payload.get("metric_type", "spl_estimate")
            weighting = payload.get("weighting", "flat")
            
            if quality_flags is not None and not isinstance(quality_flags, dict):
                logging.error("Rejected payload: quality_flags must be an object")
                return
                
            quality_flags_json = json.dumps(quality_flags) if quality_flags else None

            # Insert measurement
            cur.execute("""
                INSERT INTO measurements (
                    device_id, measured_at, total_dba, spl_avg_db, spl_max_db,
                    calibration_offset_db, status, quality_flags, metric_type, weighting
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                device_id, measured_at, total_dba, spl_avg_db, spl_max_db,
                calibration_offset_db, status, quality_flags_json, metric_type, weighting
            ))
            
            # Upsert device health
            cur.execute("""
                INSERT INTO device_health (device_id, last_seen, status, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (device_id) DO UPDATE SET
                    last_seen = EXCLUDED.last_seen,
                    status = EXCLUDED.status,
                    updated_at = NOW()
            """, (device_id, measured_at, status))
            
            conn.commit()
            logging.info(f"Inserted measurement for {device_id} (SPL Avg: {spl_avg_db})")

        elif msg_type in ["heartbeat", "status"]:
            status = payload.get("status", "online")
            last_seen = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
            
            cur.execute("""
                INSERT INTO device_health (device_id, last_seen, status, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (device_id) DO UPDATE SET
                    last_seen = EXCLUDED.last_seen,
                    status = EXCLUDED.status,
                    updated_at = NOW()
            """, (device_id, last_seen, status))
            conn.commit()
            logging.info(f"Updated device health for {device_id}: {status}")

    except Exception as e:
        logging.error(f"Error processing message: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()

def main():
    client = mqtt.Client(client_id="worker_ingestion")
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_connect
    client.on_message = on_message

    logging.info("Starting worker...")
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_forever()
    except Exception as e:
        logging.error(f"Worker crashed: {e}")

if __name__ == "__main__":
    main()
