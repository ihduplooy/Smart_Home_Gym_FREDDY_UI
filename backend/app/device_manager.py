import logging
import math
import threading
from typing import Any, Callable, Dict, List, Iterable, Optional

from config import board_constants
from core.hardware._macos_usb import ensure_macos_libusb_path

from .mock_odrive import mock_enabled, get_mock_device

log = logging.getLogger(__name__)

_device_lock = threading.RLock()
# ^ RLock, not Lock: get_shared_io_lock() acquires this and then calls
# io_lock(), which acquires it again on the same thread — a plain Lock
# self-deadlocks there every time (found live, 22 July 2026: this is why
# every real-hardware Control start() hung at set_mode(), unconditionally,
# regardless of any USB-level flakiness).
_device_index: Dict[str, Any] = {}  # serial -> odrive handle
_io_locks: Dict[str, threading.RLock] = {}  # serial -> per-device I/O lock

# odrive.find_any() performs a real USB bus reset on every call (fibre's
# usbbulk_transport.discover_channels() -> bulk_device.init() -> dev.reset()).
# The Flask dev server runs threaded=True, so two /api/devices polls (or a
# poll racing an attach_or_get()) can call _find_any() at the same instant;
# one request's bus reset then yanks the device out from under the other's
# in-flight open, surfacing as usb.core.USBError [Errno 19]/[Errno 2] on
# whichever request loses the race. Serializing all real discovery/reset
# calls through this lock prevents that self-contention. Found live: a
# successful discover_and_index() was immediately followed ~0.8s later by a
# failing one from the frontend's 3s poll interval overlapping the first
# call's in-flight reset.
_discovery_lock = threading.Lock()

# Hard wall-clock ceiling on a single discovery attempt, independent of
# odrive.find_any()'s own `timeout` argument. Found live, 22 July 2026: after
# the board was physically unplugged mid-connection, find_any() stopped
# respecting its own timeout entirely and hung indefinitely (confirmed: a
# fresh process's find_any(timeout=2.0) returned cleanly in 2.01s with the
# same board absent, so this is libusb/fibre state wedged specifically within
# the long-running backend process, not the timeout parameter being wrong).
# Because _find_any() holds _discovery_lock, an unbounded hang here would
# freeze every other route that touches the device too. Run in a daemon
# thread and give up after this ceiling so a wedge degrades to "no device
# found" instead of hanging the whole backend.
_FIND_ANY_HARD_TIMEOUT_S = 5.0


def call_with_timeout(fn: Callable[[], Any], timeout: float) -> Any:
    """Run `fn()` in a daemon thread and give up after `timeout` seconds if it
    hasn't returned, raising TimeoutError instead of blocking forever.

    Same rationale/tradeoff as `_find_any_raw`'s discovery timeout (see its
    docstring): a real USB call to this board can wedge indefinitely inside
    libusb with no timeout of its own. The most damaging place that shows up
    is the sidebar's telemetry loop (backend/app/telemetry.py), which holds
    the shared `io_lock` for the whole duration of its per-tick read — a
    single wedged property read there parks that lock forever, and every
    other real-hardware operation (e.g. Control's set_mode()) then blocks
    forever just trying to acquire it, even though *it* isn't the thing
    that's stuck. Bounding each call here means a wedge degrades to "this one
    reading is briefly stale" instead of freezing the whole backend.

    Same accepted tradeoff as _find_any_raw: on timeout, the daemon thread
    may still be running (and possibly still mid-transaction on the USB
    channel) — we simply stop waiting on it rather than hold the lock
    forever. Callers must not assume the underlying hardware call has
    actually stopped."""
    result: Dict[str, Any] = {}

    def _run():
        try:
            result["value"] = fn()
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_run, name="hw-call-timeout", daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        raise TimeoutError(f"Hardware call did not return within {timeout:.1f}s")
    if "error" in result:
        raise result["error"]
    return result.get("value")


def io_lock(serial: str) -> threading.RLock:
    """Per-device re-entrant lock serializing all USB access (telemetry + read/
    write/command) so concurrent operations never contend on the same handle."""
    with _device_lock:
        lk = _io_locks.get(serial)
        if lk is None:
            lk = threading.RLock()
            _io_locks[serial] = lk
        return lk


def _find_any_raw() -> Any:
    """The actual bounded odrive.find_any() call — mock passthrough, or a
    real call run in a daemon thread and joined with a hard ceiling so a
    libusb-level wedge (see _FIND_ANY_HARD_TIMEOUT_S) can't hang the caller.
    Does NOT take _discovery_lock — every caller must already hold it (or
    otherwise guarantee no other real find_any() is in flight), since this
    performs a real USB bus reset."""
    if mock_enabled():
        return get_mock_device()
    ensure_macos_libusb_path()
    import odrive  # lazy import; only needed with real hardware
    result: Dict[str, Any] = {}

    def _run():
        try:
            result["value"] = odrive.find_any(timeout=1.0)
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_run, name="odrive-find-any", daemon=True)
    t.start()
    t.join(timeout=_FIND_ANY_HARD_TIMEOUT_S)

    if t.is_alive():
        log.warning(
            "odrive.find_any() did not return within %.1fs (past its own 1.0s timeout) — "
            "USB/libusb is likely wedged, e.g. from the board being unplugged mid-connection. "
            "Treating this poll as 'no device found'; restart the backend if this keeps "
            "happening (a fresh process reliably clears it).",
            _FIND_ANY_HARD_TIMEOUT_S,
        )
        return None
    if "error" in result:
        # Real USB errors (e.g. another process/handle holding the device,
        # or a bus reset colliding with a concurrent scan) look identical to
        # "no device attached" to every caller unless we log them here —
        # this exception is otherwise silently discarded.
        log.warning(
            "odrive.find_any() failed (device may be busy or momentarily resetting): %r",
            result["error"],
        )
        return None
    return result.get("value")


def _find_any() -> Any:
    """Blocking discovery: waits for exclusive access, always performs a
    fresh scan. For callers that need a definitive answer (attach_or_get,
    get_shared_handle) rather than "whatever's cached is fine for now"."""
    with _discovery_lock:
        return _find_any_raw()


def forget_all() -> None:
    """Soft reset (the UI's "Reset Interface" button): drop every cached
    device handle and per-device I/O lock, so the next attach_or_get() /
    get_shared_handle() call is forced to do a fresh discovery instead of
    reusing a possibly-stale one. Does not touch the physical device — just
    this process's bookkeeping about it."""
    with _device_lock:
        _device_index.clear()
        _io_locks.clear()


def list_attached() -> List[Any]:
    with _device_lock:
        return list(_device_index.values())


def _format_serial(ser: Any) -> str:
    """ODrive's `serial_number` property is a raw 48-bit int; every ODrive
    tool (odrivetool, the ODrive GUI, the physical board's own USB string
    descriptor) displays it as lowercase hex with no '0x' prefix. Plain
    `str(ser)` instead prints the decimal value, which doesn't match what a
    user sees anywhere else — confirmed live: odrivetool showed
    '367836843335' for a board whose raw `.serial_number` int is
    59889938608949 (hex 0x367836843335)."""
    return format(ser, "x")


def serialize_device(odrv: Any) -> Dict[str, Any]:
    fw_major = getattr(odrv, "fw_version_major", None)
    fw_minor = getattr(odrv, "fw_version_minor", None)
    fw_rev = getattr(odrv, "fw_version_revision", None)
    ser = getattr(odrv, "serial_number", None)

    firmware_warning = None
    if fw_major is not None and fw_minor is not None and fw_rev is not None:
        firmware_warning = board_constants.check_firmware(fw_major, fw_minor, fw_rev)
        if firmware_warning:
            log.warning(firmware_warning)

    return {
        "serial_number": _format_serial(ser) if ser is not None else None,
        "fw_version": f"{fw_major}.{fw_minor}.{fw_rev}",
        "fw_version_major": fw_major,
        "fw_version_minor": fw_minor,
        "fw_version_revision": fw_rev,
        "firmware_warning": firmware_warning,
    }


def _resolve_attr(root: Any, dotted: str) -> Any:
    cur = root
    for part in dotted.split("."):
        if not hasattr(cur, part):
            raise AttributeError(f"Path segment '{part}' not found while resolving '{dotted}'")
        cur = getattr(cur, part)
    return cur


def get_attr_value(root: Any, dotted: str) -> Any:
    val = _resolve_attr(root, dotted)
    if isinstance(val, float) and not math.isfinite(val):
        # e.g. axis0.motor.config.torque_lim == inf ("no limit") is a normal
        # ODrive value, but Python's json module serializes it as the bare
        # token `Infinity` — not valid JSON, so the browser's strict
        # JSON.parse() throws and silently kills the *entire* batch response
        # (found live, 22 July 2026: this is why "Pull Current Config" always
        # failed — one non-finite field poisoned the whole read). Stringify
        # it instead so it round-trips safely — using JS's exact keyword
        # spelling (not Python's str(), which gives lowercase
        # "inf"/"-inf"/"nan") so the frontend's Number("Infinity") parses it
        # straight back into the numeric value instead of NaN.
        if math.isnan(val):
            return "NaN"
        return "Infinity" if val > 0 else "-Infinity"
    if isinstance(val, (int, float, bool, str)):
        return val
    raise TypeError(f"'{dotted}' is not a scalar (got {val.__class__.__name__})")


def set_attr_value(root: Any, dotted: str, value: Any):
    parts = dotted.split(".")
    parent = _resolve_attr(root, ".".join(parts[:-1])) if len(parts) > 1 else root
    leaf = parts[-1]
    if not hasattr(parent, leaf):
        raise AttributeError(f"Leaf attribute '{leaf}' not found in '{dotted}'")
    setattr(parent, leaf, value)


def invoke(root: Any, dotted: str, args: Iterable[Any]) -> Any:
    """Resolve a dotted method path and call it with the given args."""
    func = _resolve_attr(root, dotted)
    if not callable(func):
        raise TypeError(f"Attribute at '{dotted}' is not callable")
    return func(*list(args))


def _handle_is_alive(od: Any) -> bool:
    """Best-effort liveness probe for a cached device handle -- touches only
    cheap top-level scalar properties, never axis0, so it's safe to call on
    every cache hit, not just the sidebar's poll.

    A handle can go from "connected RemoteObject" to something that raises
    on virtually every attribute access, including axis0, without the cache
    itself ever noticing -- found live, 1 August 2026: a real
    AXIS_ERROR_DC_BUS_OVERVOLTAGE fault power-cycled the board, and every
    subsequent `/api/control/start` kept failing with "'RemoteObject' object
    has no attribute 'axis0'" because `get_shared_handle()` (unlike
    `discover_and_index()`'s `_serialize_cache_if_alive()` below) returned
    the same now-dead cached handle unconditionally, forever, until the
    backend was restarted. `getattr(obj, name, default)` only swallows
    AttributeError, not a fibre ChannelBrokenException, so this must catch
    broadly (Exception) -- same reasoning `_serialize_cache_if_alive`
    documented for its own probe below. Deliberately does NOT use
    `getattr(od, name, default)`: the 3-arg form swallows AttributeError
    internally and returns the default *without raising*, which is exactly
    the failure mode this exists to catch -- verified live against a mock
    object that raises AttributeError on every attribute, the 3-arg form
    reported "alive" every time. Plain attribute access is required so the
    error actually reaches this function's own try/except."""
    try:
        od.fw_version_major  # noqa: B018 -- deliberate probe, not a no-op
        od.serial_number  # noqa: B018
        return True
    except Exception:
        return False


def attach_or_get(serial: str) -> Any:
    with _device_lock:
        cached = _device_index.get(serial)
        if cached is not None:
            if _handle_is_alive(cached):
                return cached
            log.warning("Cached device handle %s is dead — dropping it and re-discovering", serial)
            _device_index.pop(serial, None)

    od = _find_any()
    if not od:
        raise ValueError(f"Device with serial '{serial}' not found")
    raw_serial = getattr(od, "serial_number", None)
    found_serial = _format_serial(raw_serial) if raw_serial is not None else ""
    if found_serial != serial.lower():
        raise ValueError(f"Device with serial '{serial}' not found (found '{found_serial}')")
    with _device_lock:
        _device_index[serial] = od
    return od


def _serialize_cache_if_alive() -> Optional[List[Dict[str, Any]]]:
    """Try to serve the poll from whatever's cached, without touching the USB
    bus at all — no reset, so it can never disturb a connection something
    else (the WS telemetry loop, a Control session) is actively using right
    now. Returns None (meaning "go do a real scan instead") if nothing's
    cached, or if what's cached turns out to be dead.

    Found live, 22 July 2026: `discover_and_index()` used to force a fresh
    `odrive.find_any()` — a real bus reset — on every single poll, completely
    unconditionally, even when a device was already connected and healthy.
    Every ~3s sidebar poll was therefore silently resetting the bus out from
    under whatever else was mid-conversation with the board (the per-device
    telemetry websocket, an active Control run), eventually killing that
    connection's `fibre` channel outright
    (`fibre.protocol.ChannelBrokenException`, 16 occurrences in one session's
    log). Once dead, the SAME broken object stayed cached and kept getting
    reused — the Dashboard/sidebar would show a "connected" device that
    could never actually return live data again until something noticed and
    dropped it. Nothing did, until this fix: `getattr(obj, name, default)`
    only swallows `AttributeError`, not `ChannelBrokenException`, so the old
    code crashed with an uncaught 500 instead of falling back cleanly.

    Extended 1 August 2026: `serialize_device()` itself reads every field via
    `getattr(odrv, name, default)` (by design, for its own JSON-serialization
    job — a genuinely absent field there should default, not raise), which
    means it can NEVER raise AttributeError, only a non-AttributeError fault
    like ChannelBrokenException. A handle that instead went dead in the
    AttributeError-raising way (see _handle_is_alive's docstring — a real
    board reboot from an AXIS_ERROR_DC_BUS_OVERVOLTAGE fault, live) sailed
    straight through this function's try/except and got reported "alive"
    with blank serial/version fields (reproduced live in this same
    incident — the sidebar showed a connected device with `serial_number:
    null`). `_handle_is_alive()` is checked first, explicitly, because it
    uses plain attribute access rather than serialize_device's defaulting
    reads, so it actually observes the AttributeError.
    """
    with _device_lock:
        cached = list(_device_index.items())
    if not cached:
        return None
    alive: List[Dict[str, Any]] = []
    dead_keys: List[str] = []
    for ser, od in cached:
        if not _handle_is_alive(od):
            log.warning("Cached device handle %s is dead — dropping it, will rescan", ser)
            dead_keys.append(ser)
            continue
        try:
            alive.append(serialize_device(od))
        except Exception as e:
            log.warning("Cached device handle %s is dead (%r) — dropping it, will rescan", ser, e)
            dead_keys.append(ser)
    if dead_keys:
        with _device_lock:
            for ser in dead_keys:
                _device_index.pop(ser, None)
    return alive if alive and not dead_keys else None


def discover_and_index() -> List[Dict[str, Any]]:
    """The sidebar's poll entry point (every 3s while disconnected). First
    tries to answer from the cache without any bus reset at all (see
    _serialize_cache_if_alive's docstring for why that matters) — only falls
    through to a real, resetting `odrive.find_any()` scan if nothing's
    cached or what's cached is dead.

    A real scan probes every USB device on the bus, not just an ODrive — with
    several unrelated peripherals attached, one scan can legitimately take
    several seconds (see docs/decisions.md, 22 July 2026). If a previous
    poll's scan is still in flight when the next one arrives, DON'T queue up
    waiting for _discovery_lock: with a 3s poll interval and a scan that can
    take longer than that, blocking here backs up an ever-growing pile of
    stuck requests until the whole backend stops responding to *anything*,
    including routes that touch no hardware at all — found live, exactly
    this way. Instead, fall back to whatever's currently cached (best effort,
    same dead-handle guard); the in-flight scan will update it momentarily
    regardless."""
    cached = _serialize_cache_if_alive()
    if cached is not None:
        return cached

    acquired = _discovery_lock.acquire(blocking=False)
    if not acquired:
        return _serialize_cache_if_alive() or []
    try:
        od = _find_any_raw()
        found = []
        with _device_lock:
            _device_index.clear()
            if od:
                raw_serial = getattr(od, "serial_number", None)
                ser = _format_serial(raw_serial) if raw_serial is not None else ""
                _device_index[ser] = od
                found.append(serialize_device(od))
        return found
    finally:
        _discovery_lock.release()


def get_shared_handle(timeout: float = 2.0) -> Any:
    """Get-or-create the one cached device handle, for callers (currently
    just core/hardware/odrive_hw.py's injected `find_any_fn`) that want to
    reuse whatever's already connected rather than forcing a fresh
    odrive.find_any() — which performs a real USB bus reset every call (see
    device_manager module-level notes / docs/decisions.md, 22 July 2026).
    Unlike discover_and_index(), this never clears/replaces an existing cache
    entry unless that entry is actually dead (_handle_is_alive) — so it never
    disturbs an already-open, still-live connection (e.g. the sidebar's
    per-device telemetry websocket). A dead entry (e.g. the board rebooted
    from a fault) is dropped and re-discovered instead of being returned
    forever — see _handle_is_alive's docstring for the live incident this
    fixed. Project is single-device by design (see docs/decisions.md,
    Session 1 §6), so "the one cached entry, if any" is unambiguous."""
    with _device_lock:
        if _device_index:
            ser, od = next(iter(_device_index.items()))
            if _handle_is_alive(od):
                return od
            log.warning("Cached device handle %s is dead — dropping it and re-discovering", ser)
            _device_index.pop(ser, None)
    found = _find_any()
    if not found:
        return None
    with _device_lock:
        raw_serial = getattr(found, "serial_number", None)
        ser = _format_serial(raw_serial) if raw_serial is not None else ""
        _device_index[ser] = found
    return found


def get_shared_io_lock() -> Any:
    """The io_lock for whatever's currently cached, resolved fresh on every
    call (never cached by the caller) so it can't go stale. Falls back to a
    harmless no-op context manager if nothing is cached yet — there's nothing
    to serialize against in that case."""
    with _device_lock:
        if _device_index:
            serial = next(iter(_device_index))
            return io_lock(serial)
    return _NULL_CTX


_BATCH_READ_TIMEOUT_S = 1.5


def batch_read(odrv: Any, paths: Iterable[str], lock: Any = None) -> Dict[str, Any]:
    """Read many paths in one lock hold (e.g. the Configuration tab's "Pull
    Current Config", which reads dozens of fields in a single call). Each
    read is bounded (see call_with_timeout's docstring) so one wedged
    property can't hang the entire batch — it's reported as an error for
    that path only, and the rest of the pull still comes back."""
    out = {}
    ctx = lock if lock is not None else _NULL_CTX
    with ctx:
        for p in paths:
            try:
                out[p] = call_with_timeout(lambda p=p: get_attr_value(odrv, p), _BATCH_READ_TIMEOUT_S)
            except TimeoutError:
                out[p] = {"error": "timed out (stale)"}
                log.warning("batch_read timed out for %s (>%.1fs)", p, _BATCH_READ_TIMEOUT_S)
            except Exception as e:
                out[p] = {"error": str(e)}
    return out


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


_NULL_CTX = _NullCtx()