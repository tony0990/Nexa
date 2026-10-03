"""Shared audio capture contracts (implemented by Member 2).

Member 2 extensions over the kickoff version are additive only: every original
field and default is kept, and `AudioRecordingService.start` still accepts the
plain source string ("MICROPHONE" / "COMPUTER" / "BOTH").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, Tuple, Union, runtime_checkable

from .meetings import AudioSource  # COMPUTER = Windows WASAPI loopback


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    is_loopback: bool = False
    default_sample_rate: int = 16000
    channels: int = 1


@dataclass(frozen=True)
class SourceConfig:
    source: AudioSource
    mic_device_index: Optional[int] = None  # None = system default
    loopback_device_index: Optional[int] = None  # None = default output's loopback


@dataclass(frozen=True)
class RecordedAudio:
    path: str = ""  # mono 16 kHz 16-bit WAV, ready for ASR
    duration_ms: int = 0
    source: str = "MICROPHONE"
    sample_rate: Optional[int] = None
    chunk_paths: Tuple[str, ...] = ()  # set for long meetings recorded in chunks


@runtime_checkable
class AudioDeviceService(Protocol):
    def list_inputs(self) -> list[AudioDevice]: ...

    def list_loopback_outputs(self) -> list[AudioDevice]: ...


@runtime_checkable
class AudioRecordingService(Protocol):
    def start(self, source: Union[SourceConfig, str]) -> str:
        """Begin recording. Returns a recording id."""

    def pause(self) -> None: ...

    def resume(self) -> None: ...

    def stop(self) -> RecordedAudio: ...
