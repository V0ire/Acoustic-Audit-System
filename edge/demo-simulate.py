import os
import time
import json
import random
from datetime import datetime, timezone, timedelta
import paho.mqtt.client as mqtt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "acoustic_device")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "password")
DEVICE_ID = os.getenv("DEVICE_ID", "ACOUSTIC-PI-001")
ROOM = os.getenv("ROOM", "R402")
PUBLISH_INTERVAL = int(os.getenv("PUBLISH_INTERVAL_SECONDS", 5))

TOPIC = f"acoustic/devices/{DEVICE_ID}/measurements"

# Set timezone to Asia/Jakarta (UTC+7)
TZ_JKT = timezone(timedelta(hours=7))

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[edge] Connected to MQTT broker at {MQTT_HOST}:{MQTT_PORT}")
    else:
        print(f"[edge] Failed to connect, return code {rc}")

def generate_dummy_payload():
    return {
        "device_id": DEVICE_ID,
        "room": ROOM,
        "timestamp": datetime.now(TZ_JKT).isoformat(),
        "total_dba": round(random.uniform(55.0, 75.0), 1),
        "mechanical_confidence": round(random.uniform(0.0, 1.0), 2),
        "human_activity_confidence": round(random.uniform(0.0, 1.0), 2)
    }

def main():
    client = mqtt.Client(client_id=f"simulate_{DEVICE_ID}")
    
    if MQTT_USERNAME and MQTT_PASSWORD:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        
    client.on_connect = on_connect
    
    print("[edge] Starting dummy MQTT publisher...")
    try:
        client.connect(MQTT_HOST, MQTT_PORT, 60)
        client.loop_start()
        
        while True:
            payload = generate_dummy_payload()
            json_payload = json.dumps(payload)
            
            # Publish QoS 1
            client.publish(TOPIC, json_payload, qos=1)
            print(f"[edge] Published to {TOPIC}: {json_payload}")
            
            time.sleep(PUBLISH_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n[edge] Stopping publisher...")
    except Exception as e:
        print(f"[edge] Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
