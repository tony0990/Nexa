# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: Nexa.exe (GUI) and NexaWorker.exe (background reminders).

Both executables share ONE bundle (`MERGE` + a single `COLLECT`), so the Python
runtime, Qt and the speech libraries are stored once instead of twice. Build with

    python scripts/build_windows.py

which runs this spec, then adds the model weights and verifies the result.

What a plain `pyinstaller apps/nexa_desktop.py` misses, and this spec supplies:

* migrations/ and resources/email_templates/  (found through core/paths.py)
* the translation JSON and theme QSS files     (read relative to their modules)
* faster-whisper's bundled VAD model, CTranslate2's native DLLs, onnxruntime
* dateparser's language data, tzdata's zone files (Africa/Cairo)
* the Google API discovery documents, keyring's Windows backend
* the NVIDIA cuBLAS/cuDNN DLLs, in a `cuda/` folder asr/cuda_runtime.py looks in
  (skip with NEXA_BUNDLE_CUDA=0 for a CPU-only build ~2 GB smaller)
"""

import os
import site
from pathlib import Path

# Python 3.10.0's `dis` raises IndexError on some constant-table layouts that newer
# third-party wheels contain, which kills PyInstaller's bytecode scan mid-build. This
# was fixed in later 3.10.x releases. Rather than require a different system Python,
# make the lookup tolerant: the value is only used to label an instruction, and
# PyInstaller reads import names from opcodes, not from this label.
import dis as _dis

_orig_const_info = _dis._get_const_info


def _tolerant_const_info(const_index, const_list):
    try:
        return _orig_const_info(const_index, const_list)
    except IndexError:
        return const_index, repr(const_index)


_dis._get_const_info = _tolerant_const_info

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH)
SRC = ROOT / "src"
BUNDLE_CUDA = os.environ.get("NEXA_BUNDLE_CUDA", "1") != "0"

# --------------------------------------------------------------------------- data
datas = [
    (str(SRC / "nexa" / "i18n" / "en.json"), "nexa/i18n"),
    (str(SRC / "nexa" / "i18n" / "ar.json"), "nexa/i18n"),
    (str(SRC / "nexa" / "themes" / "light.qss"), "nexa/themes"),
    (str(SRC / "nexa" / "themes" / "dark.qss"), "nexa/themes"),
    (str(ROOT / "migrations"), "migrations"),
    (str(ROOT / "resources" / "email_templates"), "resources/email_templates"),
    (str(ROOT / "resources" / "icons"), "resources/icons"),
]
binaries = []
hiddenimports = collect_submodules("nexa")

# Packages whose data files / native libraries PyInstaller's static analysis cannot see.
for package in (
    "faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers", "huggingface_hub",
    "dateparser", "tzdata", "pyaudiowpatch", "keyring", "googleapiclient", "google_auth_oauthlib",
    "jinja2",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:  # an optional package that is not installed is simply skipped
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += [
    "keyring.backends.Windows",
    "win32timezone",
    "zoneinfo",
]

# ---------------------------------------------------------------------------- CUDA
# DLLs only: they are loaded by ctypes/LoadLibrary at run time, so there is nothing
# for PyInstaller to analyse, and shipping them as data skips a very slow scan.
if BUNDLE_CUDA:
    for root in [Path(p) for p in site.getsitepackages()]:
        for bin_dir in root.glob("nvidia/*/bin"):
            for dll in bin_dir.glob("*.dll"):
                datas.append((str(dll), "cuda"))

# Heavy libraries that may be installed on a developer machine but that Nexa does
# not use. Excluding them keeps the bundle from swallowing multi-GB frameworks.
excludes = [
    "torch", "torchvision", "torchaudio", "tensorflow", "paddle", "paddleocr", "matplotlib", "scipy",
    "pandas", "sklearn", "chromadb", "sentence_transformers", "llama_cpp", "IPython", "notebook",
    "PyQt5", "PyQt6", "tkinter", "pytest",
]

# -------------------------------------------------------------------------- analyses
common = dict(pathex=[str(SRC)], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
              hookspath=[], runtime_hooks=[], excludes=excludes, noarchive=False)

app = Analysis([str(ROOT / "apps" / "nexa_desktop.py")], **common)
worker = Analysis([str(ROOT / "apps" / "nexa_worker.py")], **common)
MERGE((app, "nexa_desktop", "Nexa"), (worker, "nexa_worker", "NexaWorker"))

icon = str(ROOT / "resources" / "icons" / "nexa.ico")
version = str(ROOT / "scripts" / "nexa_version.txt")

app_pyz = PYZ(app.pure)
app_exe = EXE(app_pyz, app.scripts, [], exclude_binaries=True, name="Nexa",
              console=False, icon=icon, version=version, upx=False)

worker_pyz = PYZ(worker.pure)
# A console build so `NexaWorker.exe --status` can print its JSON. The GUI starts it
# with CREATE_NO_WINDOW, so no window ever appears.
worker_exe = EXE(worker_pyz, worker.scripts, [], exclude_binaries=True, name="NexaWorker",
                 console=True, icon=icon, version=version, upx=False)

coll = COLLECT(app_exe, app.binaries, app.datas,
               worker_exe, worker.binaries, worker.datas,
               strip=False, upx=False, name="Nexa")
