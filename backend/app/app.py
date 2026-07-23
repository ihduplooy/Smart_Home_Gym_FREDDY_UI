import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock

from .constants import VERSION  # backend version tag
from . import device_manager
from . import control_routes
from . import exercise_routes
from .api_reference import load_api_reference, reference_line
from .telemetry import telemetry_session
from config import board_constants

log = logging.getLogger(__name__)


def _detect_fw_line(odrv) -> int:
    # ODrive 0.5.x and 0.6.x both report major 0; the line comes from the minor.
    try:
        major = int(getattr(odrv, "fw_version_major"))
        minor = int(getattr(odrv, "fw_version_minor"))
    except Exception as e:
        raise RuntimeError(f"Failed to read firmware version: {e}") from e
    return reference_line(major, minor)


# ---- Flask App Factory ----
def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)
    sock = Sock(app)

    @app.route("/api/backend/version", methods=["GET"])
    def backend_version():
        return jsonify({
            "backend_version": VERSION,
        })

    @app.route("/api/board-constants", methods=["GET"])
    def get_board_constants():
        # Single source of truth: config/board_constants.py. Never duplicate
        # these values into frontend code — it fetches them from here.
        return jsonify(board_constants.as_dict())

    @app.route("/api/devices", methods=["GET"])
    def list_devices():
        found = device_manager.discover_and_index()
        return jsonify(found)

    @app.route("/api/devices/<serial>/api-metadata", methods=["GET"])
    def device_api_metadata(serial: str):
        try:
            odrv = device_manager.attach_or_get(serial)
            fw_line = _detect_fw_line(odrv)
            meta = load_api_reference(fw_line)
            section = request.args.get("section")
            if section:
                if section not in meta:
                    return jsonify({"error": f"Section '{section}' not in metadata"}), 400
                return jsonify({section: meta[section], "version": meta.get("version")})
            return jsonify(meta)
        except Exception as e:
            log.exception("api-metadata failed for %s", serial)
            return jsonify({"error": str(e)}), 400

    @app.route("/api/devices/<serial>/read", methods=["POST"])
    def read_properties(serial: str):
        """
        Body:
        {
          "paths": ["axis0.controller.input_pos", "..."]
        }
        """
        data = request.get_json(silent=True) or {}
        paths: List[str] = data.get("paths") or []
        if not paths:
            return jsonify({"error": "paths required"}), 400
        try:
            odrv = device_manager.attach_or_get(serial)
            results = device_manager.batch_read(odrv, paths, lock=device_manager.io_lock(serial))
            return jsonify(results)
        except Exception as e:
            log.exception("read failed for %s", serial)
            return jsonify({"error": str(e)}), 400

    @app.route("/api/devices/<serial>/write", methods=["POST"])
    def write_properties(serial: str):
        """
        Body:
        {
          "writes": [
            {"path": "axis0.controller.input_pos", "value": 1.234},
            ...
          ]
        }
        """
        payload = request.get_json(silent=True) or {}
        writes = payload.get("writes")
        if not isinstance(writes, list) or not writes:
            return jsonify({"error": "writes must be non-empty list"}), 400
        try:
            odrv = device_manager.attach_or_get(serial)
            results = []
            with device_manager.io_lock(serial):
                for item in writes:
                    path = item.get("path")
                    value = item.get("value")
                    if not path:
                        results.append({"path": path, "status": "error", "error": "missing path"})
                        continue
                    try:
                        device_manager.set_attr_value(odrv, path, value)
                        results.append({"path": path, "status": "ok"})
                    except Exception as e:
                        results.append({"path": path, "status": "error", "error": str(e)})
            return jsonify(results)
        except Exception as e:
            log.exception("write failed for %s", serial)
            return jsonify({"error": str(e)}), 400

    @app.route("/api/devices/<serial>/command", methods=["POST"])
    def invoke_command(serial: str):
        """
        Body:
        {
          "path": "axis0.controller.move_incremental",
          "args": [displacement, from_input_pos]
        }
        """
        body = request.get_json(silent=True) or {}
        path = body.get("path")
        args = body.get("args", [])
        if not path:
            return jsonify({"error": "path required"}), 400
        if not isinstance(args, list):
            return jsonify({"error": "args must be a list"}), 400
        try:
            odrv = device_manager.attach_or_get(serial)
            with device_manager.io_lock(serial):
                result = device_manager.invoke(odrv, path, args)
            return jsonify({"path": path, "result": result})
        except Exception as e:
            log.exception("command failed: %s", path)
            return jsonify({"error": str(e), "path": path}), 400

    @app.route("/api/emergency-stop", methods=["POST"])
    def emergency_stop():
        """Always-available panic button (sidebar, every tab): stop whatever
        Control session is running, then directly idle every axis on the
        cached device regardless of what put it in closed loop (a Control
        session, or Dashboard's own Enable Motor) — belt-and-braces rather
        than relying on session state being accurate."""
        control_routes.control_session.stop()
        odrv = device_manager.get_shared_handle()
        writes = []
        if odrv is not None:
            with device_manager.get_shared_io_lock():
                for axis_path in ("axis0.requested_state", "axis1.requested_state"):
                    try:
                        device_manager.set_attr_value(odrv, axis_path, 1)  # AXIS_STATE_IDLE
                        writes.append({"path": axis_path, "status": "ok"})
                    except Exception as e:
                        writes.append({"path": axis_path, "status": "error", "error": str(e)})
        return jsonify({"stopped": True, "hardware_writes": writes})

    @app.route("/api/reset", methods=["POST"])
    def reset_interface():
        """Soft reset for a stuck UI: stop any Control session and forget the
        cached device handle/lock, so the next Connect starts completely
        fresh — without restarting the backend process itself."""
        control_routes.control_session.stop()
        device_manager.forget_all()
        return jsonify({"reset": True})

    @app.route("/api/restart-backend", methods=["POST"])
    def restart_backend():
        """Restarts just the backend process. Rather than reimplementing
        process kill/respawn, this rides the Werkzeug debug reloader that's
        already watching source files: touching one's mtime makes it kill and
        respawn the worker process exactly as it already does on every code
        edit in this project. Delayed so this request's own response can
        flush before the process goes down."""
        def _trigger():
            time.sleep(0.3)
            Path(__file__).touch()

        threading.Thread(target=_trigger, daemon=True).start()
        return jsonify({"restarting": True})

    @sock.route("/api/devices/<serial>/telemetry")
    def ws_telemetry(ws, serial):
        try:
            telemetry_session(ws, serial)
        except Exception as e:
            try:
                ws.send(json.dumps({"error": str(e)}))
            except Exception:
                pass

    control_routes.register(app, sock)
    exercise_routes.register(app)

    return app