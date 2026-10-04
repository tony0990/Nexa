import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("build_windows", ROOT / "scripts" / "build_windows.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_layout_matches_plan_and_flags_missing_worker(tmp_path):
    package = tmp_path / "Nexa"
    warnings = build.assemble_layout(package, ROOT, worker=None)
    for rel in build.PACKAGE_DIRS:
        assert (package / rel).is_dir()
    assert (package / "resources" / "translations" / "ar.json").exists()
    assert (package / "resources" / "themes" / "dark.qss").exists()
    assert any("NexaWorker.exe" in w for w in warnings)


def test_worker_is_copied_next_to_nexa_exe(tmp_path):
    worker = tmp_path / "NexaWorker.exe"
    worker.write_bytes(b"MZ")
    package = tmp_path / "Nexa"
    warnings = build.assemble_layout(package, ROOT, worker=build.find_worker(worker))
    assert (package / "NexaWorker.exe").read_bytes() == b"MZ"
    assert not any("NexaWorker.exe" in w for w in warnings)
