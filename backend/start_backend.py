import logging
import sys
from pathlib import Path

# Make the repo-root config/ package importable (config/board_constants.py is the
# single source of truth for project-specific constants, shared with core/ from
# Session 2 onward).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.app import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Run with: python backend/start_backend.py  (set ODRIVE_MOCK=1 to use the mock).
app = create_app()

if __name__ == "__main__":
    # threaded=True: flask-sock's docs call this out explicitly — the dev
    # server can otherwise only serve one connection (HTTP or WebSocket) at a
    # time. Session 1 never needed this (only one long-lived WebSocket route
    # existed); Session 2 adds a second concurrent one (/ws/control-telemetry
    # alongside the per-device telemetry socket), which starves an
    # unthreaded dev server and can corrupt the WS frame stream.
    #
    # port=5050, not 5000: macOS's own AirPlay Receiver (ControlCenter)
    # listens on *:5000 by default. When our specific 127.0.0.1:5000 listener
    # is up both can coexist, but the instant ours goes away for any reason
    # (crash, restart), every request silently falls through to AirPlay
    # instead of a clean connection-refused — it answers with a real HTTP
    # response (403, Server: AirTunes) that looks like a live server, making
    # "the backend died" look like "the backend is returning nonsense".
    # Confirmed live, 22 July 2026 (docs/decisions.md). 5050 avoids the OS
    # conflict entirely; frontend/vite.config.js's proxy target matches.
    app.run(host="127.0.0.1", port=5050, debug=True, threaded=True)