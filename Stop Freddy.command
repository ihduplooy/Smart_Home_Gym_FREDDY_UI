#!/bin/bash
# Companion to "Start Freddy.command". Actually stops Freddy:
#
# 1. Idles the motor FIRST, while the backend's still up to relay it to the
#    device -- this script has no direct hardware access of its own. The
#    previous version of this script only killed processes and never talked
#    to the ODrive at all: if the motor was active (a Control session
#    running, or Enable Motor on the Dashboard) when you ran it, killing the
#    backend process did NOT itself idle the axis -- the board just kept
#    doing whatever it was doing, unsupervised, until something explicitly
#    told it to stop. This is the same belt-and-braces idle write the
#    in-app Emergency Stop button and Quit Freddy button both do
#    (backend/app/app.py's _idle_all_axes()). Best-effort: fine if the
#    backend isn't actually running right now.
# 2. Kills the backend (port 5050) and frontend (port 3000) -- they're
#    nohup'd/detached so closing a Terminal window alone won't stop them.
#    A second, harder pass (-9) mops up anything still hanging on a moment
#    later (e.g. Flask's debug reloader mid-respawn can briefly re-bind the
#    port between the two lookups above).
# 3. Best-effort: closes the Safari tab(s) Start Freddy.command opened. Not
#    part of "actually stopped" -- that already happened in steps 1-2 -- just
#    a nicety so you're not left staring at a dead page.

curl -s -m 3 -X POST http://127.0.0.1:5050/api/emergency-stop >/dev/null 2>&1

lsof -ti :5050 -sTCP:LISTEN | xargs kill 2>/dev/null
lsof -ti :3000 -sTCP:LISTEN | xargs kill 2>/dev/null
sleep 1
lsof -ti :5050 -sTCP:LISTEN | xargs kill -9 2>/dev/null
lsof -ti :3000 -sTCP:LISTEN | xargs kill -9 2>/dev/null

osascript <<'OSA' >/dev/null 2>&1
tell application "Safari"
  if it is running then
    try
      repeat with w in every window
        try
          repeat with t in (every tab of w)
            try
              if (URL of t contains "localhost:3000") then close t
            end try
          end repeat
        end try
      end repeat
    end try
  end if
end tell
OSA

echo "Freddy stopped."
