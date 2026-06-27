import os
import json
import paho.mqtt.client as mqtt
import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

load_dotenv()

# Config
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USER = os.getenv("MQTT_USERNAME", "acoustic_device")
MQTT_PASS = os.getenv("MQTT_PASSWORD", "password")
DB_URL = os.getenv("DATABASE_URL", "dbname=acoustic user=postgres password=password host=localhost")

def get_db_conn():
    return psycopg2.connect(DB_URL)

def process_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        
        # Validation Contract (Passal 14)
        if "device_id" not in payload:
            return
            
        # Mapping
        spl_avg = payload.get("spl_avg_db")
        total_dba = None
        
        # Legacy Fallback
        if spl_avg is None and "total_dba" in payload:
            spl_avg = payload["total_dba"]
            total_dba = payload["total_dba"]
            print("[worker] Warning: Legacy total_dba used")
            
        # Database Insertion
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO measurements 
            (device_id, measured_at, spl_avg_db, spl_max_db, calibration_offset_db, status, quality_flags, total_dba)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            payload.get("device_id"),
            payload.get("timestamp"),
            spl_avg,
            payload.get("spl_max_db"),
            payload.get("calibration_offset_db"),
            payload.get("status"),
            Json(payload.get("quality_flags", {})),
            total_dba
        ))
        conn.commit()
        cur.close()
        conn.close()
        print(f"[worker] Inserted: {payload['device_id']}")
        
    except Exception as e:
        print(f"[worker] Error: {e}")

client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.on_message = process_message
client.connect(MQTT_HOST, MQTT_PORT, 60)
client.subscribe("acoustic/devices/+/measurements")
client.loop_forever()
