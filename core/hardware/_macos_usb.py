"""Shared Apple Silicon libusb path fix.

pyusb resolves libusb via ctypes.util.find_library(), which can return a stale
x86_64 build (e.g. a leftover Intel/Rosetta Homebrew install at /usr/local/lib)
ahead of the correct arm64 build Homebrew actually installs at
/opt/homebrew/lib. Loading the wrong-arch dylib fails and surfaces as
NoBackendError. Prepending Homebrew's lib dir to DYLD_LIBRARY_PATH (read by
find_library at call time) fixes resolution order without touching anything
outside this process.

Shared by backend/app/device_manager.py and core/hardware/odrive_hw.py — the
two independent find_any() call sites (see docs/decisions.md, Session 1).
core/ importing this leaf util from itself and backend importing it is fine;
the direction that matters (core never imports backend) is preserved by
keeping this file dependency-free and living in core/.
"""

import os
import platform
import sys


def ensure_macos_libusb_path() -> None:
    if sys.platform == "darwin" and platform.machine() == "arm64":
        homebrew_lib = "/opt/homebrew/lib"
        current = os.environ.get("DYLD_LIBRARY_PATH", "")
        if homebrew_lib not in current.split(":"):
            os.environ["DYLD_LIBRARY_PATH"] = (
                f"{homebrew_lib}:{current}" if current else homebrew_lib
            )
