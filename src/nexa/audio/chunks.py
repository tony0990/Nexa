"""Rolling chunk files for long meetings.

Why chunks: a 60-90 minute meeting written as one WAV loses everything if the process
dies before the header is finalized. Rolling closed chunks means a crash costs at most
the last (unfinished) chunk, and ASR can process chunks independently.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .vad import is_silent
from .wav_utils import TARGET_SAMPLE_RATE


class ChunkWriter:
    """Writes mono 16-bit audio into numbered WAV chunks.

    A chunk is closed at the first silent block after `target_seconds`, so cuts
    usually land between words. `max_seconds` is a hard limit for nonstop speech.
    """

    def __init__(
        self,
        directory: str | Path,
        prefix: str = "chunk",
        sample_rate: int = TARGET_SAMPLE_RATE,
        target_seconds: float = 60.0,
        max_seconds: float = 90.0,
    ) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self.sample_rate = sample_rate
        self.target_frames = int(target_seconds * sample_rate)
        self.max_frames = int(max_seconds * sample_rate)
        self._index = 0
        self._wf: wave.Wave_write | None = None
        self._frames_in_chunk = 0
        self.paths: list[Path] = []

    def _open_next(self) -> None:
        self._index += 1
        path = self.directory / f"{self.prefix}_{self._index:04d}.wav"
        wf = wave.open(str(path), "wb")
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(self.sample_rate)
        self._wf = wf
        self._frames_in_chunk = 0
        self.paths.append(path)

    def _close_current(self) -> None:
        if self._wf is not None:
            self._wf.close()
            self._wf = None

    def write(self, block: np.ndarray) -> None:
        """Append a block of mono int16 samples (typically 20-100 ms).

        Blocks are split exactly at `max_seconds`, so with target == max the chunk
        boundaries are sample-exact (needed to align mic and loopback streams).
        """
        block = np.asarray(block, dtype=np.int16)
        pos = 0
        while pos < len(block):
            if self._wf is None:
                self._open_next()
            assert self._wf is not None
            part = block[pos : pos + (self.max_frames - self._frames_in_chunk)]
            self._wf.writeframes(part.tobytes())
            self._frames_in_chunk += len(part)
            pos += len(part)
            over_target = self._frames_in_chunk >= self.target_frames
            if self._frames_in_chunk >= self.max_frames or (over_target and is_silent(part)):
                self._close_current()

    def close(self) -> list[Path]:
        self._close_current()
        return list(self.paths)


def concat_wavs(chunk_paths: list[str | Path], out_path: str | Path) -> int:
    """Concatenate same-format WAV chunks into one file. Returns total frames written."""
    total = 0
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(TARGET_SAMPLE_RATE)
        for p in chunk_paths:
            with wave.open(str(p), "rb") as wf:
                frames = wf.readframes(wf.getnframes())
                out.writeframes(frames)
                total += wf.getnframes()
    return total


def find_chunks(directory: str | Path, prefix: str = "chunk") -> list[Path]:
    """Failure recovery: list chunk files left in a work directory, in order."""
    return sorted(Path(directory).glob(f"{prefix}_*.wav"))
