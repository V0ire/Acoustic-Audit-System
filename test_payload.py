import os
import paho.mqtt.publish as publish
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/Acoustic-Audit-System/backend/worker/.env"))

payload = '{"device_id":"ACOUSTIC-PI-001","status":"offline","reason":"manual-lwt-test"}'

publish.single(
    "acoustic/devices/ACOUSTIC-PI-001/status", 
    payload=payload,
    hostname="127.0.0.1", 
    auth={"username": os.getenv("MQTT_USERNAME"), "password": os.getenv("MQTT_PASSWORD")}
)
print("Payload sent successfully.")
