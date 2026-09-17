# -*- coding: utf-8 -*-
"""Single-instance run lock so a long Zhihu QR wait does not spawn a second Chrome."""

import ctypes
import os
import sys
from pathlib import Path

from utils.logger import ROOT

LOCK_PATH = ROOT / "data" / "run.lock"
_ERROR_ACCESS_DENIED = 5
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        handle = ctypes.windll.kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        if ctypes.GetLastError() == _ERROR_ACCESS_DENIED:
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class RunLock:
    def __init__(self, path: Path | None = None):
        self.path = path or LOCK_PATH
        self.held = False
        self.reason = ""

    def acquire(self) -> tuple[bool, str]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                old = int(self.path.read_text(encoding="utf-8").strip() or "0")
            except ValueError:
                old = 0
            if old and old != os.getpid() and _pid_running(old):
                self.reason = f"another run is active (pid {old})"
                return False, self.reason
        self.path.write_text(str(os.getpid()), encoding="utf-8")
        self.held = True
        self.reason = f"acquired run lock pid={os.getpid()}"
        return True, self.reason

    def release(self) -> None:
        if not self.held:
            return
        try:
            if self.path.exists() and self.path.read_text(encoding="utf-8").strip() == str(
                os.getpid()
            ):
                self.path.unlink()
        except OSError:
            pass
        self.held = False
