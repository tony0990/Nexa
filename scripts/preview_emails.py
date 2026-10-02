"""Write sample report and reminder emails to disk for visual review.

Section 24.6 asks whether the Arabic and English reports are *professional*,
which no assertion can answer — somebody has to look at them. This renders the
full set from the Member 4 fixtures so a reviewer can open them in a browser
and in a mail client.

    python scripts/preview_emails.py
    python scripts/preview_emails.py --out build/email-preview

Nothing is sent and no network or Gmail account is involved.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from nexa.core.clock import FixedClock  # noqa: E402
from nexa.email import EmailService, FakeEmailSender  # noqa: E402
from nexa.reports import ReportService  # noqa: E402

from tests.fixtures import member4 as data  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "build" / "email-preview"


def _allow_unicode_output() -> None:
    """Keep an Arabic subject from killing the script on a cp1252 console.

    A default Windows console is not UTF-8, and printing an Arabic subject to it
    raises `UnicodeEncodeError` after the files have already been written — the
    work succeeds and the script still exits non-zero. `errors="replace"` means
    an unprintable console degrades to `?` instead.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover - console dependent
                pass


def main(argv=None) -> int:
    _allow_unicode_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--open", action="store_true", help="open the index in a browser when done"
    )
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    clock = FixedClock(data.REFERENCE_MOMENT)
    service = EmailService(
        sender=FakeEmailSender(), reports=ReportService(clock=clock), clock=clock
    )

    written = []
    for language in ("ar", "en", "bilingual"):
        code = language.upper()
        meeting = data.meeting(code)

        report = service.reports.build_report_preview(
            meeting, data.APPROVED_ACTIONS, data.SENDABLE_EMPLOYEES, code,
            employees=data.EMPLOYEES,
        )
        written.append(_write(out, f"report_{language}", report))

        reminder = service.reports.build_reminder(
            data.SARAH if language == "en" else data.AHMED,
            data.ACTION_NO_TIME if language == "en" else data.ACTION_WITH_TIME,
            meeting,
            code,
        )
        written.append(_write(out, f"reminder_{language}", reminder))

        empty = service.reports.build_report_preview(
            meeting, [], data.SENDABLE_EMPLOYEES, code
        )
        written.append(_write(out, f"report_{language}_no_actions", empty))

    index = _write_index(out, written)
    print(f"Wrote {len(written) * 2} files to {out}")
    for name, subject in written:
        print(f"  {name:<32} {subject}")
    print(f"\nOpen {index}")
    if args.open:
        webbrowser.open(index.as_uri())
    return 0


def _write(out: Path, name: str, rendered) -> tuple:
    (out / f"{name}.html").write_text(rendered.html_body, encoding="utf-8")
    (out / f"{name}.txt").write_text(
        f"Subject: {rendered.subject}\nTo: {rendered.to_name} <{rendered.to_email}>\n"
        f"Language: {rendered.language}\n\n{rendered.text_body}",
        encoding="utf-8",
    )
    return name, rendered.subject


def _write_index(out: Path, written) -> Path:
    rows = "\n".join(
        f'<tr><td><a href="{name}.html">{name}.html</a></td>'
        f'<td><a href="{name}.txt">plain text</a></td>'
        f"<td>{subject}</td></tr>"
        for name, subject in written
    )
    index = out / "index.html"
    index.write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>Nexa email previews</title></head><body "
        "style=\"font-family:'Segoe UI',Arial,sans-serif;padding:24px;\">"
        "<h1>Nexa email previews</h1>"
        "<p>Rendered from the Member 4 fixtures with a pinned clock "
        "(Sunday 20 September 2026, Cairo). Nothing was sent.</p>"
        "<table cellpadding='6' style='border-collapse:collapse;'>"
        f"{rows}</table></body></html>",
        encoding="utf-8",
    )
    return index


if __name__ == "__main__":
    raise SystemExit(main())
