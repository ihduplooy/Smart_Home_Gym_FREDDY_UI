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
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)