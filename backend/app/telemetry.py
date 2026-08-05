import csv
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .device_manager import (
    attach_or_get,
    get_attr_value,
    set_attr_value,
    invoke,
    io_lock,
    call_with_timeout,
)

log = logging.getLogger(__name__)

# Bound on each property read in the always-on live-status loop below. A
# single wedged read (see device_manager.call_with_timeout's docstring) must
# not be allowed to hold `lock` forever — that would freeze every other
# real-hardware operation (Dashboard, Control, Configuration) waiting on the
# same shared lock, not just this stream. On timeout that one reading is
# reported as stale for this tick; the loop retries it next tick.
_READ_TIMEOUT_S = 1.5

# Same repo-root convention as core/telemetry/csv_logger.py (this file lives
# at backend/app/telemetry.py, two parents up lands in the same place that
# module's three-parents-up does from core/telemetry/) -- Inspector
# recordings land next to the Train/Exercise/Force/Testing session logs
# rather than a separate directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RECORDING_FLUSH_INTERVAL_S = 1.0


def _inspector_logs_dir() -> Path:
    d = _REPO_ROOT / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def telemetry_session(ws, serial: str):
    """
    Per-connection loop carrying both the telemetry stream and request/response
    operations, so a single WebSocket replaces the old REST read/write/command
    calls and never contends with the stream on the USB device.

    Client -> server:
      {"action": "subscribe", "paths": [...], "interval_ms": 100}
      {"action": "update",   "paths": [...]}
      {"action": "interval", "interval_ms": 200}
      {"action": "ping"}
      {"action": "read",    "id": <n>, "paths": [...]}
      {"action": "write",   "id": <n>, "writes": [{path, value}]}
      {"action": "command", "id": <n>, "path": "...", "args": [...]}
      {"action": "record_start", "id": <n>}
      {"action": "record_stop",  "id": <n>}
    Server -> client:
      {"timestamp": <ms>, "data": { path: value | {error}, ... }}   (stream)
      {"id": <n>, "ok": true, "result": ...} | {"id": <n>, "ok": false, "error": ...}

    record_start/record_stop write a CSV under logs/ of exactly the paths
    currently subscribed (via "subscribe"/"update") at the moment Start is
    called -- the column set is snapshotted then and does not change even if
    the client subscribes/unsubscribes paths mid-recording (a value for a
    column no longer subscribed just logs as an empty cell that tick,
    matching how core/telemetry/csv_logger.py treats an unset field). Recorded
    columns are whatever the caller was subscribed to, i.e. "the properties
    you have open in Inspector" -- not a fixed schema like the Train/
    Exercise/Force/Testing session logger, since Inspector's property set is
    arbitrary and user-picked.
    """
    paths: List[str] = []
    interval_ms = 200
    odrv = attach_or_get(serial)
    lock = io_lock(serial)
    recording: Optional[Dict[str, Any]] = None
    last_recording_flush = time.monotonic()

    try:
        while True:
            try:
                msg_raw = ws.receive(timeout=0.0)
            except Exception:
                msg_raw = None

            if msg_raw:
                try:
                    msg = json.loads(msg_raw)
                except Exception:
                    ws.send(json.dumps({"error": "invalid_json"}))
                    continue
                action = msg.get("action")
                if action == "subscribe":
                    new_paths = msg.get("paths") or []
                    if not isinstance(new_paths, list):
                        ws.send(json.dumps({"error": "paths_must_be_list"}))
                        continue
                    paths = list(dict.fromkeys(new_paths))  # dedupe preserve order
                    intv = msg.get("interval_ms")
                    if isinstance(intv, int) and 10 <= intv <= 2000:
                        interval_ms = intv
                    ws.send(json.dumps({"ack": "subscribe", "count": len(paths), "interval_ms": interval_ms}))
                elif action == "update":
                    new_paths = msg.get("paths") or []
                    if isinstance(new_paths, list):
                        paths = list(dict.fromkeys(new_paths))
                        ws.send(json.dumps({"ack": "update", "count": len(paths)}))
                elif action == "interval":
                    intv = msg.get("interval_ms")
                    if isinstance(intv, int) and 10 <= intv <= 2000:
                        interval_ms = intv
                        ws.send(json.dumps({"ack": "interval", "interval_ms": interval_ms}))
                elif action == "ping":
                    ws.send(json.dumps({"ack": "pong"}))
                elif action in ("read", "write", "command"):
                    ws.send(json.dumps(_handle_request(odrv, lock, msg)))
                elif action == "record_start":
                    rid = msg.get("id")
                    if recording is not None:
                        ws.send(json.dumps({"id": rid, "ok": False, "error": "already recording"}))
                    elif not paths:
                        ws.send(json.dumps({"id": rid, "ok": False, "error": "no properties selected"}))
                    else:
                        # Snapshot now -- later subscribe/update calls must not
                        # reshape a file already in progress (see docstring).
                        columns = list(paths)
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        out_path = _inspector_logs_dir() / f"inspector_{serial}_{ts}.csv"
                        f = open(out_path, "w", newline="")
                        writer = csv.writer(f)
                        writer.writerow(["timestamp_ms", "t_rel_s", *columns])
                        f.flush()
                        recording = {
                            "file": f,
                            "writer": writer,
                            "columns": columns,
                            "path": out_path,
                            "t0_ms": None,
                            "rows": 0,
                        }
                        last_recording_flush = time.monotonic()
                        ws.send(json.dumps({
                            "id": rid,
                            "ok": True,
                            "result": {"path": str(out_path), "columns": columns},
                        }))
                elif action == "record_stop":
                    rid = msg.get("id")
                    if recording is None:
                        ws.send(json.dumps({"id": rid, "ok": False, "error": "not recording"}))
                    else:
                        recording["file"].flush()
                        recording["file"].close()
                        result = {"path": str(recording["path"]), "rows": recording["rows"]}
                        recording = None
                        ws.send(json.dumps({"id": rid, "ok": True, "result": result}))

            if paths:
                data: Dict[str, Any] = {}
                with lock:
                    for p in paths:
                        try:
                            data[p] = call_with_timeout(lambda p=p: get_attr_value(odrv, p), _READ_TIMEOUT_S)
                        except TimeoutError:
                            data[p] = {"error": "timed out (stale)"}
                            log.warning("telemetry read timed out for %s (>%.1fs) — reporting stale", p, _READ_TIMEOUT_S)
                        except Exception as e:
                            # Surface the failure instead of a silent None so the
                            # client can tell "unreadable" from a real value.
                            data[p] = {"error": str(e)}
                            log.debug("telemetry read failed for %s: %s", p, e)
                timestamp = int(time.time() * 1000)
                ws.send(json.dumps({
                    "timestamp": timestamp,
                    "data": data
                }))

                if recording is not None:
                    if recording["t0_ms"] is None:
                        recording["t0_ms"] = timestamp
                    row = [timestamp, (timestamp - recording["t0_ms"]) / 1000.0]
                    for col in recording["columns"]:
                        v = data.get(col)
                        # Error markers ({"error": ...}) and a column dropped
                        # from `paths` after Start both log as an empty cell,
                        # same convention as csv_logger.py's unset fields.
                        row.append("" if isinstance(v, dict) or col not in data else v)
                    recording["writer"].writerow(row)
                    recording["rows"] += 1
                    now = time.monotonic()
                    if now - last_recording_flush >= _RECORDING_FLUSH_INTERVAL_S:
                        recording["file"].flush()
                        last_recording_flush = now

            time.sleep(interval_ms / 1000.0)
    finally:
        if recording is not None:
            try:
                recording["file"].flush()
                recording["file"].close()
            except Exception:
                log.exception("Failed to close Inspector recording file on session end")


def _handle_request(odrv, lock, msg: Dict[str, Any]) -> Dict[str, Any]:
    """Run a read/write/command request under the device lock and return a
    response frame keyed by the client-supplied id."""
    rid = msg.get("id")
    action = msg.get("action")
    try:
        with lock:
            if action == "read":
                out: Dict[str, Any] = {}
                for p in (msg.get("paths") or []):
                    try:
                        out[p] = get_attr_value(odrv, p)
                    except Exception as e:
                        out[p] = {"error": str(e)}
                return {"id": rid, "ok": True, "result": out}
            if action == "write":
                results = []
                for item in (msg.get("writes") or []):
                    path = item.get("path")
                    if not path:
                        results.append({"path": path, "status": "error", "error": "missing path"})
                        continue
                    try:
                        set_attr_value(odrv, path, item.get("value"))
                        results.append({"path": path, "status": "ok"})
                    except Exception as e:
                        results.append({"path": path, "status": "error", "error": str(e)})
                return {"id": rid, "ok": True, "result": results}
            path = msg.get("path")
            if not path:
                return {"id": rid, "ok": False, "error": "path required"}
            result = invoke(odrv, path, msg.get("args") or [])
            return {"id": rid, "ok": True, "result": result}
    except Exception as e:
        return {"id": rid, "ok": False, "error": str(e)}