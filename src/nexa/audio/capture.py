"""Capture-stream abstraction + the PyAudioWPatch (WASAPI) implementation.

UNTESTED ON WINDOWS: `PyAudioCapture` was written without access to a Windows audio
device. Everything that talks to hardware goes through the `CaptureStream` protocol so
the recorder can be tested with fake streams; the real device path needs a manual test
on the ROG (see docs/member2-test-checklist.md).
"""
from __future__ import annotations

import queue
from typing import Protocol

import numpy as np

from .wav_utils import to_mono

BLOCK_SECONDS = 0.1


class AudioBackendError(RuntimeError):
    """Audio hardware/backend is missing or failed (e.g. not on Windows)."""


class CaptureStream(Protocol):
    sample_rate: int

    def start(self) -> None: ...

    def read_block(self, timeout: float) -> np.ndarray | None:
        """Next block of mono int16 samples at `sample_rate`, or None if none arrived
        within `timeout` seconds. WASAPI loopback delivers NOTHING while the system is
        silent, so None is normal there - the recorder pads the gap with zeros."""

    def stop(self) -> None: ...


def import_pyaudio():
    try:
        import pyaudiowpatch as pyaudio  # type: ignore[import-not-found]
    except ImportError as exc:
        raise AudioBackendError(
            "PyAudioWPatch is not installed (Windows only): pip install -r requirements/audio_windows.txt"
        ) from exc
    return pyaudio


class PyAudioCapture:
    """Callback-driven capture of one device (microphone OR loopback)."""

    def __init__(self, device_index: int | None, loopback: bool = False) -> None:
        self._pyaudio = import_pyaudio()
        self._pa = self._pyaudio.PyAudio()
        self._info = self._resolve_device(device_index, loopback)
        self.sample_rate = int(self._info["defaultSampleRate"])
        self._channels = int(self._info["maxInputChannels"]) or 1
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._stream = None

    def _resolve_device(self, index: int | None, loopback: bool) -> dict:
        try:
            if index is not None:
                return self._pa.get_device_info_by_index(index)
            if loopback:
                return self._pa.get_default_wasapi_loopback()
            return self._pa.get_default_input_device_info()
        except (OSError, LookupError) as exc:
            kind = "loopback output" if loopback else "input"
            raise AudioBackendError(f"No usable {kind} device: {exc}") from exc

    def _on_data(self, in_data, frame_count, time_info, status):  # PyAudio callback
        self._queue.put(in_data)
        return (None, self._pyaudio.paContinue)

    def start(self) -> None:
        try:
            self._stream = self._pa.open(
                format=self._pyaudio.paInt16,
                channels=self._channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=int(self._info["index"]),
                frames_per_buffer=int(self.sample_rate * BLOCK_SECONDS),
                stream_callback=self._on_data,
            )
            self._stream.start_stream()
        except OSError as exc:
            raise AudioBackendError(f"Could not open '{self._info['name']}': {exc}") from exc

    def read_block(self, timeout: float) -> np.ndarray | None:
        try:
            raw = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
        return to_mono(np.frombuffer(raw, dtype=np.int16), self._channels)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        self._pa.terminate()
