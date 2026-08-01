#!/bin/bash
# One-click launcher for Freddy (Smart Gym Control's web GUI). Double-click in
# Finder. Always starts clean (kills any leftover backend/frontend first, so
# there's never a stale process from a previous session), real hardware mode
# (no ODRIVE_MOCK), then opens Safari once both servers are actually up.
#
# Backend runs on port 5050, not 5000 — 5000 collides with macOS's own
# AirPlay Receiver, which silently swallows requests the instant our backend
# isn't there to claim it first (see backend/start_backend.py).
cd "$(dirname "$0")"

lsof -ti :5050 -sTCP:LISTEN | xargs kill 2>/dev/null
lsof -ti :3000 -sTCP:LISTEN | xargs kill 2>/dev/null
sleep 1

source .venv/bin/activate
mkdir -p logs
nohup python backend/start_backend.py > logs/backend.log 2>&1 &
( cd frontend && nohup npm run dev:frontend > ../logs/frontend.log 2>&1 & )

echo "Starting Freddy..."
for i in $(seq 1 30); do
  curl -s -o /dev/null http://127.0.0.1:5050/api/backend/version \
    && curl -s -o /dev/null http://127.0.0.1:3000 \
    && break
  sleep 1
done

open -a Safari http://localhost:3000
