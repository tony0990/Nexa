"""Make CTranslate2's CUDA libraries loadable on Windows, or say they are not.

`hardware.detect_hardware` used to ask CTranslate2 how many CUDA devices exist and
pick the GPU if the answer was non-zero. On a machine with an NVIDIA driver but no
CUDA-12 runtime libraries that answer is still "1", so the app chose the GPU and
then every transcription died on `Library cublas64_12.dll is not found` — in the
middle of a meeting, after the recording was already over. A device being present
and the libraries being loadable are different facts.

CTranslate2 4.x needs cuBLAS 12 and cuDNN 9. They ship as NVIDIA pip wheels
(`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) whose DLLs sit under
`site-packages/nvidia/<lib>/bin`, which Windows does not search by default. This
module finds those folders — in a source checkout, or bundled next to a frozen
exe — registers them with `os.add_dll_directory`, and then *tries to load* the
DLLs so the answer is a fact rather than a guess.
"""

from __future__ import annotations

import ctypes
import glob
import os
import site
import sys
from pathlib import Path
from typing import List

_REQUIRED = ("cublas64_12.dll", "cudnn64_9.dll")
_registered: List[str] = []
_dll_handles: list = []  # keep add_dll_directory cookies alive for the process


def _candidate_dirs() -> List[Path]:
    roots: List[Path] = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        roots.append(Path(frozen_root))
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        roots += [exe_dir, exe_dir / "_internal"]
    try:
        roots += [Path(p) for p in site.getsitepackages()]
        roots.append(Path(site.getusersitepackages()))
    except Exception:  # noqa: BLE001 - some embedded interpreters have no site
        pass

    found: List[Path] = []
    for root in roots:
        for pattern in ("nvidia/*/bin", "cuda", "cuda/bin"):
            found += [Path(p) for p in glob.glob(str(root / pattern)) if os.path.isdir(p)]
    # De-duplicate, keep order.
    seen, unique = set(), []
    for path in found:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def register_cuda_dll_directories() -> List[str]:
    """Add every folder that holds NVIDIA DLLs to the loader search path."""
    if os.name != "nt":
        return []
    for directory in _candidate_dirs():
        text = str(directory)
        if text in _registered:
            continue
        try:
            _dll_handles.append(os.add_dll_directory(text))
        except (OSError, AttributeError):
            continue
        # Some libraries load their own dependencies with LoadLibrary, which
        # honours PATH rather than add_dll_directory.
        os.environ["PATH"] = text + os.pathsep + os.environ.get("PATH", "")
        _registered.append(text)
    return list(_registered)


def cuda_libs_available() -> bool:
    """True only if the CUDA-12 libraries CTranslate2 needs actually load."""
    if os.name != "nt":
        return False
    register_cuda_dll_directories()
    try:
        for name in _REQUIRED:
            ctypes.WinDLL(name)
    except OSError:
        return False
    return True


def looks_like_cuda_failure(exc: BaseException) -> bool:
    """Whether an exception means "the GPU path is unusable", not "bad audio"."""
    text = str(exc).lower()
    return any(
        marker in text
        for marker in ("cublas", "cudnn", "cuda", "cudart", "library", ".dll", "out of memory")
    )
