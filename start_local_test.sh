#!/bin/bash

echo "Starting local test environment..."

# 1. Start the API
source .venv/bin/activate
echo "Starting API on port 8000..."
uvicorn backend.api.app:app --host 127.0.0.1 --port 8000 > /dev/null 2>&1 &
API_PID=$!

# 2. Start the Ingestion Worker
echo "Starting MQTT Worker..."
python backend.worker.worker > /dev/null 2>&1 &
WORKER_PID=$!
# Wait, let's just run it as python backend/worker/worker.py
kill $WORKER_PID 2>/dev/null
python backend/worker/worker.py > /dev/null 2>&1 &
WORKER_PID=$!

# 3. Start the Edge Simulator (Generates live dummy data)
echo "Starting Edge Simulator..."
python edge/demo-simulate.py > /dev/null 2>&1 &
SIMULATOR_PID=$!

# 4. Start Frontend Web Server
echo "Starting Frontend on port 8080..."
cd frontend
python -m http.server 8080 > /dev/null 2>&1 &
FRONTEND_PID=$!
cd ..

echo ""
echo "=================================================="
echo "✅ Local Environment Running!"
echo "=================================================="
echo "🌍 Open your browser and go to:"
echo "   http://localhost:8080"
echo ""
echo "Press Ctrl+C to stop all services."
echo "=================================================="

# Trap Ctrl+C and kill background processes
trap "echo 'Stopping services...'; kill $API_PID $WORKER_PID $SIMULATOR_PID $FRONTEND_PID; exit" INT

# Keep script running
wait
