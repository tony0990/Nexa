"""Download the local models Nexa needs, once, into `models/`.

Section 18 lists this script and it was missing, which meant the AI stack had no
documented way to get its weights: Member 2's ASR and Member 3's extractor both
expect files under `models/` that nothing fetched.

Nexa's cost target is zero recurring software cost (Section 14), so every model
is downloaded once and then runs offline. Nothing here is required for the
report, email, scheduling or data layers — those have no model dependency at
all, which is why this is a separate script and not part of first run.

    python scripts/download_models.py --list
    python scripts/download_models.py --asr whisper-medium
    python scripts/download_models.py --llm qwen3-4b
    python scripts/download_models.py --all

Downloads are large (a Whisper medium is ~1.5 GB, the LLM ~2.5 GB), so each one
is skipped when the target already exists and `--force` is needed to refetch.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from nexa.asr.model_registry import available_models, resolve_model  # noqa: E402

MODELS_DIR = REPO_ROOT / "models"
WHISPER_DIR = MODELS_DIR / "whisper"
LLM_DIR = MODELS_DIR / "llm"

# Section 15.2's candidate, as a GGUF quantization that runs on CPU. Pinned to a
# specific file rather than "latest" so two machines benchmark the same weights.
LLM_CANDIDATES = {
    "qwen3-4b": {
        "repo": "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "description": "Section 15.2 extraction candidate, 4-bit, CPU-friendly",
    },
}


def main(argv=None) -> int:
    _allow_unicode_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="show what is available and present")
    parser.add_argument("--asr", action="append", default=[], metavar="KEY",
                        help="an ASR model key from the registry (repeatable)")
    parser.add_argument("--llm", action="append", default=[], metavar="KEY",
                        help="an LLM key (repeatable)")
    parser.add_argument("--all", action="store_true", help="the default ASR model and LLM")
    parser.add_argument("--force", action="store_true", help="refetch even if present")
    args = parser.parse_args(argv)

    if args.list:
        return _list()

    asr_keys = list(args.asr)
    llm_keys = list(args.llm)
    if args.all:
        # Medium is the accuracy baseline the plan requires (Section 15.1).
        asr_keys = asr_keys or ["whisper-medium"]
        llm_keys = llm_keys or list(LLM_CANDIDATES)
    if not asr_keys and not llm_keys:
        parser.print_help()
        print("\nNothing selected. Use --list, --asr, --llm or --all.")
        return 2

    failures = 0
    for key in asr_keys:
        failures += 0 if _download_asr(key, force=args.force) else 1
    for key in llm_keys:
        failures += 0 if _download_llm(key, force=args.force) else 1

    print()
    _report_disk()
    return 1 if failures else 0


# --------------------------------------------------------------------- listing
def _list() -> int:
    print("ASR models (faster-whisper):")
    for spec in available_models():
        target = WHISPER_DIR / spec.key
        mark = "present" if (target / "model.bin").is_file() else "-"
        print(f"  {spec.key:<20} {mark:<8} {spec.description}")
    print("\nLLM models (llama.cpp GGUF):")
    for key, spec in LLM_CANDIDATES.items():
        target = LLM_DIR / spec["filename"]
        mark = "present" if target.is_file() else "-"
        print(f"  {key:<20} {mark:<8} {spec['description']}")
    print(f"\nModels directory: {MODELS_DIR}")
    print("Both are gitignored: large binaries never belong in the repository.")
    return 0


# ------------------------------------------------------------------------- ASR
def _download_asr(key: str, *, force: bool = False) -> bool:
    """Fetch a CTranslate2 Whisper model into a plain folder under models/whisper/.

    A flat folder (model.bin, config.json, tokenizer.json, vocabulary) rather
    than the Hugging Face cache layout, because the engine and the packaged
    exe both load it *by path*: `WhisperModel("models/whisper/whisper-medium")`.
    The HF cache is a tree of symlinked blobs that does not survive being copied
    into a PyInstaller bundle or onto another machine.
    """
    spec = resolve_model(key)
    target = WHISPER_DIR / spec.key
    if (target / "model.bin").is_file() and not force:
        print(f"[skip] ASR {spec.key} already present at {target}")
        return True

    try:
        from faster_whisper.utils import download_model
    except ImportError:
        print(
            f"[fail] ASR {spec.key}: faster-whisper is not installed.\n"
            "       pip install -r requirements/ai.txt"
        )
        return False

    print(f"[get ] ASR {spec.key} ({spec.model_id}) -> {target}")
    target.mkdir(parents=True, exist_ok=True)
    try:
        download_model(spec.model_id, output_dir=str(target))
    except Exception as exc:
        print(f"[fail] ASR {spec.key}: {exc}")
        return False
    if not (target / "model.bin").is_file():
        print(f"[fail] ASR {spec.key}: download finished but model.bin is missing")
        return False
    print(f"[ok  ] ASR {spec.key}")
    return True


# ------------------------------------------------------------------------- LLM
def _download_llm(key: str, *, force: bool = False) -> bool:
    spec = LLM_CANDIDATES.get(key)
    if spec is None:
        print(f"[fail] unknown LLM {key!r}. Known: {', '.join(LLM_CANDIDATES) or '(none)'}")
        return False

    target = LLM_DIR / spec["filename"]
    if target.is_file() and not force:
        print(f"[skip] LLM {key} already present at {target}")
        return True

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print(
            f"[fail] LLM {key}: huggingface_hub is not installed.\n"
            "       pip install -r requirements/ai.txt"
        )
        return False

    print(f"[get ] LLM {key} ({spec['repo']}/{spec['filename']}) -> {target}")
    LLM_DIR.mkdir(parents=True, exist_ok=True)
    try:
        path = hf_hub_download(
            repo_id=spec["repo"],
            filename=spec["filename"],
            local_dir=str(LLM_DIR),
        )
    except Exception as exc:
        print(f"[fail] LLM {key}: {exc}")
        return False
    print(f"[ok  ] LLM {key} at {path}")
    return True


# ----------------------------------------------------------------------- utils
def _report_disk() -> None:
    total = sum(f.stat().st_size for f in MODELS_DIR.rglob("*") if f.is_file()) \
        if MODELS_DIR.exists() else 0
    print(f"models/ now uses {total / 1e9:.2f} GB")
    usage = shutil.disk_usage(REPO_ROOT)
    print(f"free on this drive: {usage.free / 1e9:.1f} GB")


def _allow_unicode_output() -> None:
    """A default Windows console is cp1252 and cannot print every model name."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - console dependent
                pass


if __name__ == "__main__":
    raise SystemExit(main())
