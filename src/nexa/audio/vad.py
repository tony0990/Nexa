"""Lightweight energy-based voice activity helpers (numpy only).

Scope on purpose: this is NOT the transcription-time VAD. For transcription, use
faster-whisper's built-in `vad_filter` (Silero) - it keeps segment timestamps mapped
to the original audio. Never physically cut silence out of audio you will transcribe,
or the timestamps stop matching the meeting timeline.

These helpers are used for: choosing chunk boundaries, the "test audio source" level
check, and detecting a dead (silent) capture stream.
"""
from __future__ import annotations

import numpy as np

_EPS = 1e-9


def level_db(samples: np.ndarray) -> float:
    """RMS level in dBFS (0 dB = full scale, about -90 for digital silence)."""
    if len(samples) == 0:
        return -90.0
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64) / 32768.0))))
    return max(-90.0, 20.0 * float(np.log10(rms + _EPS)))


def peak_db(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return -90.0
    peak = float(np.max(np.abs(samples.astype(np.float64)))) / 32768.0
    return max(-90.0, 20.0 * float(np.log10(peak + _EPS)))


def is_silent(samples: np.ndarray, threshold_db: float = -50.0) -> bool:
    return level_db(samples) < threshold_db


def speech_regions(
    samples: np.ndarray,
    sample_rate: int,
    frame_ms: int = 30,
    margin_db: float = 12.0,
    min_gap_ms: int = 400,
    pad_ms: int = 200,
    min_region_ms: int = 60,
) -> list[tuple[int, int]]:
    """Return [(start_ms, end_ms)] regions that likely contain speech.

    Tuned to keep short utterances ("yes", "Monday"): a frame is speech when it is
    `margin_db` above the estimated noise floor (10th percentile of frame energy);
    nearby regions are merged and padded so word edges are never clipped.
    """
    frame = int(sample_rate * frame_ms / 1000)
    n_frames = len(samples) // frame
    if n_frames == 0:
        return []
    frames = samples[: n_frames * frame].reshape(n_frames, frame)
    energies = np.array([level_db(f) for f in frames])
    floor = float(np.percentile(energies, 10))
    threshold = max(floor + margin_db, -60.0)
    active = energies > threshold

    regions: list[list[int]] = []
    for i, is_active in enumerate(active):
        if not is_active:
            continue
        start, end = i * frame_ms, (i + 1) * frame_ms
        if regions and start - regions[-1][1] <= min_gap_ms:
            regions[-1][1] = end
        else:
            regions.append([start, end])

    total_ms = n_frames * frame_ms
    return [
        (max(0, s - pad_ms), min(total_ms, e + pad_ms))
        for s, e in regions
        if e - s >= min_region_ms
    ]


def has_speech(samples: np.ndarray, sample_rate: int) -> bool:
    return bool(speech_regions(samples, sample_rate))
