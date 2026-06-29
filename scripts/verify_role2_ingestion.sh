source .venv/bin/activate

pkill -f "uvicorn backend.api.app:app" || true
pkill -f "python backend/worker/worker.py" || true

uvicorn backend.api.app:app --host 127.0.0.1 --port 8000 > api_test.log 2>&1 &
API_PID=$!

python backend/worker/worker.py > worker_test.log 2>&1 &
WORKER_PID=$!

sleep 3

mosquitto_pub -h localhost -p 1883 -u acoustic_device -P password -t "acoustic/devices/ACOUSTIC-PI-001/measurements" -m '{"device_id": "ACOUSTIC-PI-001", "room": "R402", "timestamp": "2026-06-27T18:05:00+07:00", "total_dba": 60.5}'
sleep 1

mosquitto_pub -h localhost -p 1883 -u acoustic_device -P password -t "acoustic/devices/ACOUSTIC-PI-001/measurements" -m '{"schema_version": "1.0", "device_id": "ACOUSTIC-PI-001", "room": "R402", "timestamp": "2026-06-27T18:05:10+07:00", "metric_type": "spl_estimate", "weighting": "flat", "spl_avg_db": 62.1, "spl_max_db": 68.4, "calibration_offset_db": -5.0, "status": "ok", "quality_flags": {"clipping": false}}'
sleep 1

mosquitto_pub -h localhost -p 1883 -u acoustic_device -P password -t "acoustic/devices/ACOUSTIC-PI-001/measurements" -m '{"device_id": "WRONG", "bad": json}'
sleep 1

echo -e "\n--- Worker Logs ---"
cat worker_test.log

echo -e "\n--- API Measurements Output ---"
curl -s http://127.0.0.1:8000/api/measurements | head -n 35

echo -e "\n--- API Devices Output ---"
curl -s http://127.0.0.1:8000/api/devices

kill $API_PID $WORKER_PID || true
