"""Microphone capture (Windows, via PyAudioWPatch)."""
from __future__ import annotations

from .capture import CaptureStream, PyAudioCapture


def open_microphone(device_index: int | None = None) -> CaptureStream:
    """`device_index=None` uses the system default input device."""
    return PyAudioCapture(device_index, loopback=False)
