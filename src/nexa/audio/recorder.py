"""RecorderService: records mic, computer audio, or both into rolling WAV chunks.

Design notes
  * Each source runs in its own thread and writes to its own ChunkWriter.
  * Both sources are kept on a WALL-CLOCK timeline: if a stream delivers nothing
    (WASAPI loopback is silent while nothing plays) the gap is padded with zeros. That
    keeps mic and loopback sample-aligned so they can be mixed chunk-by-chunk.
  * In BOTH mode chunks have a fixed length (sample-exact, so chunk i of the mic lines
    up with chunk i of the loopback); single-source mode cuts at silence instead.
  * Pause drops audio (the transcript timeline skips the paused time).
  * Crash recovery: closed chunks are valid WAVs; `recover_recording` also salvages
    the last unfinished chunk from its raw PCM data.
"""
from __future__ import annotations

import threading
import time
import uuid
import wave
from collections.abc import Callable
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path

import numpy as np

from ..contracts.audio import AudioSource, RecordedAudio, SourceConfig
from .capture import BLOCK_SECONDS, AudioBackendError, CaptureStream
from .chunks import ChunkWriter, concat_wavs
from .loopback import open_loopback
from .microphone import open_microphone
from .mixer import mix_wav_files
from .vad import level_db, peak_db
from .wav_utils import TARGET_SAMPLE_RATE, read_wav, resample, wav_duration_ms, write_wav

CaptureFactory = Callable[[str, "int | None"], CaptureStream]  # (kind: "mic"|"loop", device_index)

_PAD_TOLERANCE_S = 0.2  # ignore gaps shorter than this (normal delivery jitter)
_WAV_HEADER_BYTES = 44


def default_capture_factory(kind: str, device_index: int | None) -> CaptureStream:
    return open_microphone(device_index) if kind == "mic" else open_loopback(device_index)


class _SourceWorker(threading.Thread):
    def __init__(self, capture: CaptureStream, writer: ChunkWriter, clock: Callable[[], float]) -> None:
        super().__init__(daemon=True)
        self._capture = capture
        self._writer = writer
        self._clock = clock
        self._stop_event = threading.Event()
        self._paused = threading.Event()
        self._lock = threading.Lock()
        self._pause_started: float | None = None
        self._paused_total = 0.0
        self._written = 0  # samples written at TARGET_SAMPLE_RATE
        self.error: BaseException | None = None

    def pause(self) -> None:
        with self._lock:
            if self._pause_started is None:
                self._pause_started = self._clock()
                self._paused.set()

    def resume(self) -> None:
        with self._lock:
            if self._pause_started is not None:
                self._paused_total += self._clock() - self._pause_started
                self._pause_started = None
                self._paused.clear()

    def request_stop(self) -> None:
        self._stop_event.set()

    def _expected_samples(self, t0: float) -> int:
        with self._lock:
            paused = self._paused_total + (
                self._clock() - self._pause_started if self._pause_started is not None else 0.0
            )
        return int((self._clock() - t0 - paused) * TARGET_SAMPLE_RATE)

    def _pad_to_wall_clock(self, t0: float, tolerance_s: float) -> None:
        deficit = self._expected_samples(t0) - self._written
        if deficit > tolerance_s * TARGET_SAMPLE_RATE:
            self._writer.write(np.zeros(deficit, dtype=np.int16))
            self._written += deficit

    def run(self) -> None:
        t0 = self._clock()
        try:
            while not self._stop_event.is_set():
                block = self._capture.read_block(timeout=BLOCK_SECONDS)
                if self._paused.is_set():
                    continue  # drop audio while paused
                if block is not None:
                    samples = resample(block, self._capture.sample_rate, TARGET_SAMPLE_RATE)
                    self._writer.write(samples)
                    self._written += len(samples)
                else:
                    self._pad_to_wall_clock(t0, _PAD_TOLERANCE_S)
            self._pad_to_wall_clock(t0, 0.0)  # equalize stream lengths at stop
        except BaseException as exc:  # noqa: BLE001 - reported via .error, never lost
            self.error = exc
        finally:
            try:
                self._capture.stop()
            except Exception:  # noqa: BLE001
                pass


class Recorder:
    """Implements `AudioRecordingService`."""

    def __init__(
        self,
        work_root: str | Path,
        capture_factory: CaptureFactory = default_capture_factory,
        chunk_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._work_root = Path(work_root)
        self._factory = capture_factory
        self._chunk_seconds = chunk_seconds
        self._clock = clock
        self._workers: dict[str, _SourceWorker] = {}
        self._writers: dict[str, ChunkWriter] = {}
        self._workdir: Path | None = None
        self.warnings: list[str] = []

    @property
    def is_recording(self) -> bool:
        return bool(self._workers)

    def start(self, config: SourceConfig | str) -> str:
        if isinstance(config, str):  # the kickoff contract passes "MICROPHONE" / "COMPUTER" / "BOTH"
            config = SourceConfig(AudioSource(config))
        if self.is_recording:
            raise RuntimeError("Recording already in progress")
        recording_id = uuid.uuid4().hex[:12]
        self._workdir = self._work_root / recording_id
        self.warnings = []
        both = config.source is AudioSource.BOTH
        wanted: list[tuple[str, int | None]] = []
        if config.source in (AudioSource.MICROPHONE, AudioSource.BOTH):
            wanted.append(("mic", config.mic_device_index))
        if config.source in (AudioSource.COMPUTER, AudioSource.BOTH):
            wanted.append(("loop", config.loopback_device_index))

        captures: dict[str, CaptureStream] = {}
        try:
            for kind, index in wanted:
                capture = self._factory(kind, index)
                capture.start()  # raise here, on the caller's thread, if the device is bad
                captures[kind] = capture
        except Exception:
            for capture in captures.values():
                capture.stop()
            raise

        for kind, capture in captures.items():
            writer = ChunkWriter(
                self._workdir / kind,
                prefix=kind,
                target_seconds=self._chunk_seconds,
                max_seconds=self._chunk_seconds if both else self._chunk_seconds * 1.5,
            )
            self._writers[kind] = writer
            self._workers[kind] = _SourceWorker(capture, writer, self._clock)
        for worker in self._workers.values():
            worker.start()
        return recording_id

    def pause(self) -> None:
        for worker in self._workers.values():
            worker.pause()

    def resume(self) -> None:
        for worker in self._workers.values():
            worker.resume()

    def stop(self) -> RecordedAudio:
        if not self.is_recording or self._workdir is None:
            raise RuntimeError("No recording in progress")
        for worker in self._workers.values():
            worker.request_stop()
        for kind, worker in self._workers.items():
            worker.join(timeout=10)
            if worker.error is not None:
                self.warnings.append(f"{kind} capture failed mid-recording: {worker.error!r}")
        streams = {kind: writer.close() for kind, writer in self._writers.items()}
        workdir = self._workdir
        self._workers, self._writers, self._workdir = {}, {}, None
        streams = {kind: paths for kind, paths in streams.items() if paths}
        if not streams:
            raise AudioBackendError("Recording produced no audio" + (f": {self.warnings}" if self.warnings else ""))
        return _finalize(workdir, streams)


# ---- finishing / recovery -------------------------------------------------------------


def _combine(workdir: Path, streams: dict[str, list[Path]]) -> list[Path]:
    """One chunk list from per-source chunk lists (mixing mic+loop chunk-by-chunk)."""
    if len(streams) == 1:
        return next(iter(streams.values()))
    mixed_dir = workdir / "mixed"
    mixed_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for i, (mic, loop) in enumerate(zip_longest(streams.get("mic", []), streams.get("loop", [])), start=1):
        target = mixed_dir / f"chunk_{i:04d}.wav"
        if mic and loop:
            mix_wav_files(str(mic), str(loop), str(target))
        else:
            samples, rate = read_wav(mic or loop)
            write_wav(target, resample(samples, rate, TARGET_SAMPLE_RATE), TARGET_SAMPLE_RATE)
        out.append(target)
    return out


def _source_of(streams: dict[str, list[Path]]) -> AudioSource:
    """What was actually captured - BOTH can degrade to one source if a device failed."""
    if len(streams) == 2:
        return AudioSource.BOTH
    return AudioSource.MICROPHONE if "mic" in streams else AudioSource.COMPUTER


def _finalize(workdir: Path, streams: dict[str, list[Path]]) -> RecordedAudio:
    chunks = _combine(workdir, streams)
    final = workdir / "recording.wav"
    concat_wavs(list(chunks), final)
    return RecordedAudio(
        path=str(final),
        duration_ms=wav_duration_ms(final),
        source=_source_of(streams).value,
        sample_rate=TARGET_SAMPLE_RATE,
        chunk_paths=tuple(str(p) for p in chunks),
    )


def _salvage_unclosed_wav(path: Path) -> bool:
    """A chunk that was open when the process died has a header claiming 0 frames.
    Python's `wave` writes a canonical 44-byte header, so the PCM bytes after it are
    intact - rewrite the file with a correct header. Returns True if salvaged."""
    data = path.read_bytes()
    if len(data) <= _WAV_HEADER_BYTES:
        return False
    pcm = data[_WAV_HEADER_BYTES : len(data) - (len(data) - _WAV_HEADER_BYTES) % 2]
    write_wav(path, np.frombuffer(pcm, dtype=np.int16), TARGET_SAMPLE_RATE)
    return True


def _valid_chunks(directory: Path, prefix: str) -> list[Path]:
    good: list[Path] = []
    for path in sorted(directory.glob(f"{prefix}_*.wav")):
        try:
            with wave.open(str(path), "rb") as wf:
                frames = wf.getnframes()
        except (wave.Error, EOFError):
            frames = 0
        if frames == 0 and not _salvage_unclosed_wav(path):
            continue
        good.append(path)
    return good


def recover_recording(workdir: str | Path) -> RecordedAudio:
    """Rebuild a RecordedAudio from a work directory left behind by a crash."""
    workdir = Path(workdir)
    streams = {kind: _valid_chunks(workdir / kind, kind) for kind in ("mic", "loop")}
    streams = {kind: paths for kind, paths in streams.items() if paths}
    if not streams:
        raise AudioBackendError(f"Nothing to recover in {workdir}")
    return _finalize(workdir, streams)


# ---- "test audio source" --------------------------------------------------------------


@dataclass(frozen=True)
class SourceLevel:
    rms_db: float
    peak_db: float

    @property
    def looks_dead(self) -> bool:
        return self.peak_db < -70.0


def measure_source(capture: CaptureStream, seconds: float = 2.0) -> SourceLevel:
    """Listen briefly and report levels, so the UI can show a meter / warn on a dead mic.
    Note: a loopback source reads as silent unless something is playing."""
    capture.start()
    blocks: list[np.ndarray] = []
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            block = capture.read_block(timeout=BLOCK_SECONDS)
            if block is not None:
                blocks.append(block)
    finally:
        capture.stop()
    samples = np.concatenate(blocks) if blocks else np.zeros(0, dtype=np.int16)
    return SourceLevel(rms_db=level_db(samples), peak_db=peak_db(samples))
