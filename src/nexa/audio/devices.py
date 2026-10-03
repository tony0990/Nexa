"""Audio device listing (Windows, via PyAudioWPatch). UNTESTED ON WINDOWS."""
from __future__ import annotations

from ..contracts.audio import AudioDevice
from .capture import import_pyaudio


def _to_device(info: dict, loopback: bool) -> AudioDevice:
    return AudioDevice(
        index=int(info["index"]),
        name=str(info["name"]),
        is_loopback=loopback,
        default_sample_rate=int(info["defaultSampleRate"]),
        channels=int(info["maxInputChannels"]),
    )


class PyAudioDeviceService:
    def list_inputs(self) -> list[AudioDevice]:
        pyaudio = import_pyaudio()
        pa = pyaudio.PyAudio()
        try:
            devices = []
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info["maxInputChannels"] > 0 and not info.get("isLoopbackDevice", False):
                    devices.append(_to_device(info, loopback=False))
            return devices
        finally:
            pa.terminate()

    def list_loopback_outputs(self) -> list[AudioDevice]:
        pyaudio = import_pyaudio()
        pa = pyaudio.PyAudio()
        try:
            return [_to_device(info, loopback=True) for info in pa.get_loopback_device_info_generator()]
        finally:
            pa.terminate()
