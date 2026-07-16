import json
import logging
from typing import Any, Dict, List

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock

from .constants import VERSION  # backend version tag
from . import device_manager
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

    @sock.route("/api/devices/<serial>/telemetry")
    def ws_telemetry(ws, serial):
        try:
            telemetry_session(ws, serial)
        except Exception as e:
            try:
                ws.send(json.dumps({"error": str(e)}))
            except Exception:
                pass

    return app