"""Mix microphone + computer audio (both mono int16 at the same sample rate)."""
from __future__ import annotations

import numpy as np

from .wav_utils import TARGET_SAMPLE_RATE, read_wav, resample, write_wav

_INT16_MAX = 32767


def mix_mono(a: np.ndarray, b: np.ndarray, gain_a: float = 1.0, gain_b: float = 1.0) -> np.ndarray:
    """Sum two mono streams. The shorter one is zero-padded.

    Summing can exceed int16 range; if it does, the *whole* mix is scaled down
    (no hard clipping, which would distort speech and hurt ASR).
    """
    n = max(len(a), len(b))
    mixed = np.zeros(n, dtype=np.float32)
    mixed[: len(a)] += a.astype(np.float32) * gain_a
    mixed[: len(b)] += b.astype(np.float32) * gain_b
    peak = float(np.max(np.abs(mixed))) if n else 0.0
    if peak > _INT16_MAX:
        mixed *= _INT16_MAX / peak
    return np.rint(mixed).astype(np.int16)


def mix_wav_files(path_a: str, path_b: str, out_path: str, gain_a: float = 1.0, gain_b: float = 1.0) -> int:
    """Mix two WAV files into one canonical mono 16 kHz WAV. Returns duration in ms."""
    a, rate_a = read_wav(path_a)
    b, rate_b = read_wav(path_b)
    a = resample(a, rate_a, TARGET_SAMPLE_RATE)
    b = resample(b, rate_b, TARGET_SAMPLE_RATE)
    out = mix_mono(a, b, gain_a, gain_b)
    write_wav(out_path, out, TARGET_SAMPLE_RATE)
    return int(round(len(out) * 1000 / TARGET_SAMPLE_RATE))
