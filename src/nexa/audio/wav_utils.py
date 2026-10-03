"""WAV helpers. Nexa's canonical audio format: mono, 16 kHz, 16-bit PCM."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

TARGET_SAMPLE_RATE = 16000


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a 16-bit PCM WAV as a mono int16 array. Returns (samples, sample_rate)."""
    with wave.open(str(path), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError(f"{path}: only 16-bit PCM WAV is supported (got {wf.getsampwidth() * 8}-bit)")
        channels = wf.getnchannels()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16)
    return to_mono(samples, channels), rate


def write_wav(path: str | Path, samples: np.ndarray, sample_rate: int = TARGET_SAMPLE_RATE) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(np.asarray(samples, dtype=np.int16).tobytes())


def wav_duration_ms(path: str | Path) -> int:
    with wave.open(str(path), "rb") as wf:
        return int(round(wf.getnframes() * 1000 / wf.getframerate()))


def to_mono(samples: np.ndarray, channels: int) -> np.ndarray:
    """Average interleaved channels down to mono (int16)."""
    if channels <= 1:
        return samples.astype(np.int16, copy=False)
    usable = (len(samples) // channels) * channels
    frames = samples[:usable].reshape(-1, channels).astype(np.float32)
    return np.rint(frames.mean(axis=1)).astype(np.int16)


def resample(samples: np.ndarray, src_rate: int, dst_rate: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """Resample mono int16 audio.

    Numpy-only: box-filter low-pass when downsampling (limits aliasing), then linear
    interpolation. Good enough for speech at 16 kHz; swap in scipy.signal.resample_poly
    later if benchmarks show resampling hurts accuracy.
    """
    if src_rate == dst_rate or len(samples) == 0:
        return samples.astype(np.int16, copy=False)
    data = samples.astype(np.float32)
    if src_rate > dst_rate:
        width = max(1, int(round(src_rate / dst_rate)))
        if width > 1:
            kernel = np.ones(width, dtype=np.float32) / width
            data = np.convolve(data, kernel, mode="same")
    n_out = int(round(len(data) * dst_rate / src_rate))
    x_old = np.arange(len(data), dtype=np.float64)
    x_new = np.linspace(0, len(data) - 1, n_out)
    out = np.interp(x_new, x_old, data)
    return np.clip(np.rint(out), -32768, 32767).astype(np.int16)


def normalize_to_canonical(src_path: str | Path, dst_path: str | Path) -> int:
    """Convert any 16-bit PCM WAV to mono 16 kHz. Returns duration in ms."""
    samples, rate = read_wav(src_path)
    out = resample(samples, rate, TARGET_SAMPLE_RATE)
    write_wav(dst_path, out, TARGET_SAMPLE_RATE)
    return int(round(len(out) * 1000 / TARGET_SAMPLE_RATE))
