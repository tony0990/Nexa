"""Where Nexa finds its files — in a source checkout and inside a packaged exe.

Three modules located resources with `Path(__file__).parents[3]`, which is right
in a checkout and wrong once frozen: PyInstaller unpacks the Python modules into
an archive, so `__file__` points at a pseudo-path and `parents[3]` lands one level
above the bundle. A packaged build would start, then fail to find
`migrations/` and the email templates.

Everything that has to be found lives behind these functions instead:

    resource_dir()   read-only files shipped with the app (migrations, templates,
                     translations, themes, icons)
    data_dir()       the user's database, outbox, recordings and logs
    models_dir()     the downloaded speech/LLM weights (large, not bundled in git)

`NEXA_DATA_DIR`, `NEXA_MODELS_DIR` and `NEXA_RESOURCE_DIR` override each one, which
is how the tests and a portable install redirect them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Nexa"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """The folder holding the app: the exe's folder when frozen, else the repo root."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def resource_dir() -> Path:
    """Read-only files shipped with the app.

    In a PyInstaller 6 one-folder build the bundled data lives under
    `_internal/` (`sys._MEIPASS`), not beside the exe.
    """
    override = os.environ.get("NEXA_RESOURCE_DIR")
    if override:
        return Path(override)
    if is_frozen():
        bundle = getattr(sys, "_MEIPASS", None)
        return Path(bundle) if bundle else install_dir()
    return install_dir()


def _writable(folder: Path) -> bool:
    """True if files can be created in `folder` (creating it if needed)."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".nexa-write-test"
        probe.write_text("x")
        probe.unlink()
        return True
    except OSError:
        return False


def data_dir() -> Path:
    """The user's writable data: database, outbox, recordings, logs.

    Portable by default: `<install>/data`, so a copy of the app on D: keeps all of
    its data on D: (the system drive is often the scarce one). Only when the install
    folder is not writable — Program Files — does it fall back to `%LOCALAPPDATA%`.
    `NEXA_DATA_DIR` overrides both.
    """
    override = os.environ.get("NEXA_DATA_DIR")
    if override:
        return Path(override)
    portable = install_dir() / "data"
    if _writable(portable):
        return portable
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) / APP_NAME) if base else (Path.home() / ".nexa")


def models_dir() -> Path:
    """Downloaded model weights.

    Looked up in this order, first that exists wins, so a developer checkout, a
    portable install and a per-user install all work without configuration:
    `NEXA_MODELS_DIR`, `<install>/models`, `<data>/models`.
    """
    override = os.environ.get("NEXA_MODELS_DIR")
    if override:
        return Path(override)
    for candidate in (install_dir() / "models", data_dir() / "models"):
        if candidate.is_dir():
            return candidate
    return install_dir() / "models"


def whisper_model_path(key: str = "whisper-medium") -> Path | None:
    """The folder of a downloaded CTranslate2 Whisper model, or None."""
    path = models_dir() / "whisper" / key
    return path if (path / "model.bin").is_file() else None


def best_whisper_model() -> tuple[str, Path] | None:
    """The largest downloaded Whisper model, preferring accuracy over speed."""
    for key in ("whisper-large-v3", "whisper-medium", "whisper-small"):
        path = whisper_model_path(key)
        if path is not None:
            return key, path
    return None
