"""`Nexa.exe --selftest`: can *this build* actually do its job?

A packaged exe fails in ways a source checkout never does: a data file that was not
bundled, a DLL that is not found, a plugin that does not load. None of those show up
in the unit tests, because the tests run from source. This runs the same code from
inside the build and reports, check by check, what works.

Each check is PASS, WARN (works, but degraded — e.g. no GPU) or FAIL. The exit code
is non-zero only on FAIL, and the full report is written to `selftest.json` in the
data directory (a windowed exe has no console to read).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List

from nexa.core import paths

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


class _Report:
    def __init__(self) -> None:
        self.checks: List[dict] = []

    def run(self, name: str, fn: Callable[[], tuple]) -> None:
        started = time.time()
        try:
            status, detail = fn()
        except Exception as exc:  # noqa: BLE001 - a crashing check is a FAIL, not a crash
            status, detail = FAIL, f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}"
        self.checks.append(
            {"name": name, "status": status, "detail": detail, "seconds": round(time.time() - started, 2)}
        )

    @property
    def failed(self) -> bool:
        return any(c["status"] == FAIL for c in self.checks)


# --------------------------------------------------------------------- checks
def _resources():
    root = paths.resource_dir()
    needed = {
        "migrations": root / "migrations" / "001_initial.sql",
        "email templates": root / "resources" / "email_templates" / "en" / "meeting_report.html.j2",
        "translations": Path(__file__).resolve().parents[1] / "i18n" / "en.json",
        "theme": Path(__file__).resolve().parents[1] / "themes" / "light.qss",
    }
    missing = [name for name, p in needed.items() if not p.is_file()]
    if missing:
        return FAIL, f"missing from the build: {', '.join(missing)} (resource_dir={root})"
    return PASS, f"all present under {root}"


def _services(data_dir: Path):
    from nexa.services.real import RealServiceContainer

    container = RealServiceContainer(data_dir / "selftest-db")
    roles = [r.name for r in container.people.list_roles()]
    return container, roles


def _reports(container):
    from nexa.contracts.meetings import ActionItem, Meeting
    from nexa.contracts.people import Employee

    lines = []
    for language in ("EN", "AR", "BILINGUAL"):
        rendered = container.email.reports.build_meeting_report(
            Meeting(title="Selftest", started_at=datetime.now(timezone.utc), email_language=language),
            [ActionItem(task="Verify the build", due_date=datetime.now().date())],
            [Employee(id=1, full_name="Test User", email="test@example.com")],
            language,
        )
        if not rendered or "Verify the build" not in rendered[0].html_body:
            return FAIL, f"{language} report did not render its content"
        lines.append(f"{language}:{len(rendered[0].html_body)}b")
    return PASS, ", ".join(lines)


def _outbox(container):
    from nexa.contracts.email import RenderedEmail

    result = container.email.sender.send(
        RenderedEmail(to_email="selftest@example.com", subject="تجربة", html_body="<p>ok</p>", text_body="ok", language="AR")
    )
    return (PASS, result.gmail_message_id) if result.ok else (FAIL, result.error_message)


def _extraction(container):
    from datetime import datetime

    from nexa.services.models import Transcript

    text = "أحمد، لازم تخلص الـ report بكرة الساعة 10 الصبح. Sarah will send the invoice by Friday at 3 pm."
    transcript = Transcript(raw_text=text, confirmed_text=text, segments=[{"start_ms": 0, "end_ms": 5000, "text": text}])
    items = container.extraction.extract(transcript)
    if len(items) != 2:
        return FAIL, f"expected 2 actions, got {len(items)}: {[i.task for i in items]}"
    if not all(i.due_iso for i in items):
        return FAIL, "a date was not resolved"
    return PASS, "; ".join(f"{i.owner_raw_text}->{i.due_display}" for i in items)


def _qt_window(container):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from nexa.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = MainWindow(skip_first_run=True, services=container)
    window.resize(1200, 780)
    window.navigate("meeting")
    window.show()
    app.processEvents()
    image = window.grab()
    if image.isNull() or image.width() < 100:
        return FAIL, "the main window rendered nothing"
    eye = window.pages["meeting"].eye
    eye.set_state("recording")
    app.processEvents()
    window.close()
    return PASS, f"window {image.width()}x{image.height()}, eye state={eye.state}"


def _audio():
    from nexa.audio.capture import import_pyaudio

    pyaudio = import_pyaudio()
    pa = pyaudio.PyAudio()
    try:
        mic = pa.get_default_input_device_info()["name"]
        try:
            loop = pa.get_default_wasapi_loopback()["name"]
        except Exception as exc:  # noqa: BLE001
            return WARN, f"microphone '{mic}' found; no loopback device ({exc})"
        return PASS, f"microphone '{mic}'; loopback '{loop}'"
    except OSError as exc:
        return WARN, f"no audio input device: {exc}"
    finally:
        pa.terminate()


def _asr(container):
    import numpy as np

    from nexa.asr.cuda_runtime import cuda_libs_available, register_cuda_dll_directories
    from nexa.asr.hardware import detect_hardware
    from nexa.audio.wav_utils import write_wav

    found = paths.best_whisper_model()
    if found is None:
        return WARN, f"no speech model in {paths.models_dir()}; run scripts/download_models.py"
    register_cuda_dll_directories()
    hardware = detect_hardware()
    wav = Path(tempfile.mkdtemp()) / "tone.wav"
    t = np.arange(16000 * 2) / 16000
    write_wav(wav, (np.sin(2 * np.pi * 220 * t) * 4000).astype(np.int16), 16000)
    started = time.time()
    container.transcription.warm_up()
    container.transcription.transcribe_path(str(wav))
    took = time.time() - started
    detail = f"model {found[0]} on {hardware.device}/{hardware.compute_type} (cuda libs: {cuda_libs_available()}), load+run {took:.1f}s"
    if hardware.device != "cuda":
        return WARN, detail + " — running on CPU, which is slow for long meetings"
    return PASS, detail


def _worker():
    if not paths.is_frozen():
        return PASS, "source checkout: the worker is apps/nexa_worker.py"
    exe = paths.install_dir() / "NexaWorker.exe"
    return (PASS, str(exe)) if exe.is_file() else (FAIL, f"NexaWorker.exe not found beside Nexa.exe ({exe})")


def run_selftest(data_dir: Path) -> int:
    report = _Report()
    report.run("resources bundled", _resources)
    holder: dict = {}

    def build():
        container, roles = _services(data_dir)
        holder["c"] = container
        return PASS, f"database migrated, roles seeded: {', '.join(roles)}"

    report.run("database + services", build)
    container = holder.get("c")
    if container is not None:
        report.run("email reports (EN/AR/BILINGUAL)", lambda: _reports(container))
        report.run("outbox delivery", lambda: _outbox(container))
        report.run("action extraction", lambda: _extraction(container))
        report.run("main window + eye", lambda: _qt_window(container))
    report.run("microphone + loopback", _audio)
    if container is not None:
        report.run("speech model (GPU/CPU)", lambda: _asr(container))
    report.run("worker executable", _worker)

    summary = {
        "frozen": paths.is_frozen(),
        "python": sys.version.split()[0],
        "install_dir": str(paths.install_dir()),
        "checks": report.checks,
        "ok": not report.failed,
    }
    out = data_dir / "selftest.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    for stream in (sys.stdout, sys.stderr):
        # A default Windows console is cp1252 and cannot print Arabic check details.
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    try:
        for c in report.checks:
            print(f"[{c['status']}] {c['name']}: {str(c['detail']).splitlines()[0]}")
        print(f"\nselftest {'PASSED' if summary['ok'] else 'FAILED'}  ->  {out}")
    except Exception:  # noqa: BLE001 - a windowed exe may have no stdout
        pass
    if container is not None:
        container.close()
    return 0 if summary["ok"] else 1
