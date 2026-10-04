"""CPU/GPU detection for faster-whisper (CTranslate2)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareProfile:
    device: str  # "cuda" | "cpu"
    compute_type: str  # "float16" | "int8_float16" | "int8"
    cuda_devices: int = 0


def cuda_device_count() -> int:
    try:
        import ctranslate2  # installed with faster-whisper

        return int(ctranslate2.get_cuda_device_count())
    except Exception:  # noqa: BLE001 - missing lib / no driver both mean "no GPU"
        return 0


def detect_hardware(prefer_int8: bool = False, force_cpu: bool = False) -> HardwareProfile:
    """GPU -> float16 (or int8_float16 to save VRAM, e.g. Whisper Medium on a 6 GB card);
    CPU -> int8."""
    gpus = 0 if force_cpu else cuda_device_count()
    # A device being present is not the same as its libraries being loadable.
    # Without this check a machine with an NVIDIA driver but no CUDA-12 runtime
    # picked the GPU and then failed every transcription (see cuda_runtime.py).
    if gpus > 0:
        from .cuda_runtime import cuda_libs_available

        if not cuda_libs_available():
            gpus = 0
    if gpus > 0:
        return HardwareProfile("cuda", "int8_float16" if prefer_int8 else "float16", gpus)
    return HardwareProfile("cpu", "int8", 0)
