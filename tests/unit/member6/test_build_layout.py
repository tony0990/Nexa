"""The Windows build script: its pure helpers and the spec it drives."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("build_windows", ROOT / "scripts" / "build_windows.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_the_spec_builds_both_executables_into_one_bundle():
    text = (ROOT / "Nexa.spec").read_text(encoding="utf-8")
    assert 'name="Nexa"' in text and 'name="NexaWorker"' in text
    assert "MERGE(" in text and text.count("COLLECT(") == 1


def test_the_spec_bundles_what_a_plain_build_misses():
    text = (ROOT / "Nexa.spec").read_text(encoding="utf-8")
    for needed in ("migrations", "email_templates", "faster_whisper", "ctranslate2", "dateparser", "tzdata", "cuda"):
        assert needed in text


def test_copy_models_warns_when_none_are_downloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "PACKAGE", tmp_path / "dist" / "Nexa")
    warnings = build.copy_models()
    assert warnings and "download_models.py" in warnings[0]


def test_copy_models_copies_the_weights_and_skips_download_cache(tmp_path, monkeypatch):
    model = tmp_path / "models" / "whisper" / "whisper-medium"
    (model / ".cache").mkdir(parents=True)
    (model / "model.bin").write_bytes(b"x")
    (model / ".cache" / "junk").write_bytes(b"x")
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "PACKAGE", tmp_path / "dist" / "Nexa")
    assert build.copy_models() == []
    copied = tmp_path / "dist" / "Nexa" / "models" / "whisper" / "whisper-medium"
    assert (copied / "model.bin").exists() and not (copied / ".cache").exists()
