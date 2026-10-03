"""Computer-audio capture via WASAPI loopback (Windows, PyAudioWPatch)."""
from __future__ import annotations

from .capture import CaptureStream, PyAudioCapture


def open_loopback(device_index: int | None = None) -> CaptureStream:
    """`device_index=None` uses the default output device's loopback.

    Known WASAPI behaviour: loopback produces no data while nothing is playing.
    The recorder handles that by padding silence on a wall-clock timeline.
    """
    return PyAudioCapture(device_index, loopback=True)
