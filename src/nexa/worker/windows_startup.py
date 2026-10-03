"""Register NexaWorker.exe to launch with Windows (HKCU Run key, no admin rights needed)."""
from __future__ import annotations

import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "NexaWorker"


class UnsupportedPlatform(RuntimeError):
    pass


def _winreg():
    if sys.platform != "win32":
        raise UnsupportedPlatform("Windows startup registration is only available on Windows")
    import winreg
    return winreg


def build_command(exe_path: str, *args: str) -> str:
    return " ".join([f'"{exe_path}"', *args])


def enable_startup(exe_path: str, *args: str) -> str:
    w = _winreg()
    cmd = build_command(exe_path, *(args or ("--background",)))
    with w.OpenKey(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_SET_VALUE) as k:
        w.SetValueEx(k, VALUE_NAME, 0, w.REG_SZ, cmd)
    return cmd


def disable_startup() -> bool:
    w = _winreg()
    try:
        with w.OpenKey(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_SET_VALUE) as k:
            w.DeleteValue(k, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False


def is_enabled() -> bool:
    w = _winreg()
    try:
        with w.OpenKey(w.HKEY_CURRENT_USER, RUN_KEY, 0, w.KEY_READ) as k:
            w.QueryValueEx(k, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
