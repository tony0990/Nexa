"""The repository's scripts must at least run (§18 lists all of them).

These are smoke tests, not coverage: a script that crashes on `--help` or on a
missing optional dependency is the kind of thing nobody notices until someone
needs it, because no other test imports them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"

# Section 18's list, minus the ones whose owners have not landed yet.
EXPECTED_SCRIPTS = (
    "download_models.py",
    "seed_demo_data.py",
    "benchmark_asr.py",
    "create_demo_database.py",
    "preview_emails.py",
    "setup_gmail.py",
)


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, cwd=str(REPO_ROOT),
    )


@pytest.mark.parametrize("script", EXPECTED_SCRIPTS)
def test_script_exists(script):
    assert (SCRIPTS / script).is_file()


@pytest.mark.parametrize("script", EXPECTED_SCRIPTS)
def test_help_does_not_crash(script):
    """`--help` exercises import time, which is where a bad import shows up."""
    result = run(script, "--help")
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr


def test_download_models_lists_without_the_ai_stack_installed():
    """--list must work on a machine with no model libraries at all."""
    result = run("download_models.py", "--list")
    assert result.returncode == 0, result.stderr
    assert "whisper-medium" in result.stdout
    assert "Traceback" not in result.stderr


def test_download_models_with_no_selection_explains_itself():
    result = run("download_models.py")
    assert result.returncode == 2
    assert "Nothing selected" in result.stdout


def test_download_models_rejects_an_unknown_llm():
    result = run("download_models.py", "--llm", "not-a-model")
    assert result.returncode == 1
    assert "unknown LLM" in result.stdout


def test_download_models_reports_a_missing_dependency_clearly():
    """Not installed is a message with a fix, not an ImportError traceback."""
    result = run("download_models.py", "--asr", "whisper-small")
    combined = result.stdout + result.stderr
    assert "Traceback" not in combined
    if "[fail]" in combined:
        assert "requirements/ai.txt" in combined


def test_preview_emails_writes_every_language(tmp_path):
    out = tmp_path / "preview"
    result = run("preview_emails.py", "--out", str(out))
    assert result.returncode == 0, result.stderr
    for name in ("report_ar", "report_en", "report_bilingual"):
        assert (out / f"{name}.html").is_file()
        assert (out / f"{name}.txt").is_file()


def test_setup_gmail_status_is_offline_and_safe():
    result = run("setup_gmail.py", "status")
    # 1 when not connected, which is the expected state in a test environment.
    assert result.returncode in (0, 1)
    assert "Traceback" not in result.stderr
