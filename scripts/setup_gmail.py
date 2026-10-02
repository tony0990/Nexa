"""Connect, test or disconnect the Gmail account from the command line.

Section 24.4 lists the Gmail test account and the Google OAuth client as
team/admin setup. This script is what turns that setup into one command once the
client secrets file exists, so the live `connect()` path can be verified before
Member 6's Settings screen exists.

    python scripts/setup_gmail.py status
    python scripts/setup_gmail.py connect      # opens a browser once
    python scripts/setup_gmail.py test
    python scripts/setup_gmail.py send --to you@example.com
    python scripts/setup_gmail.py disconnect

`connect` is the only subcommand that needs a browser or the internet; `status`
is fully offline. See docs/email.md for how to create the client secrets file.

No token is ever printed: the refresh token goes straight into Windows
Credential Manager and this script only ever sees a `ConnectionStatus`
(Section 38).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from nexa.core.clock import SystemClock  # noqa: E402
from nexa.core.config import default_data_dir  # noqa: E402
from nexa.email import EmailService, GmailConnectionService  # noqa: E402
from nexa.email.errors import EmailError  # noqa: E402
from nexa.email.oauth import default_client_secrets_path  # noqa: E402


def _allow_unicode_output() -> None:
    """A default Windows console is cp1252 and cannot print Arabic."""
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
    parser.add_argument(
        "action",
        choices=("status", "connect", "test", "disconnect", "send"),
        help="what to do",
    )
    parser.add_argument(
        "--client-secrets",
        type=Path,
        help=f"path to the Google desktop client secrets JSON "
        f"(default: {default_client_secrets_path()})",
    )
    parser.add_argument(
        "--to", help="recipient for `send`; defaults to the connected account"
    )
    parser.add_argument(
        "--language", choices=("AR", "EN"), default="EN", help="language for `send`"
    )
    parser.add_argument("--port", type=int, default=0, help="localhost port for `connect`")
    args = parser.parse_args(argv)

    secrets = args.client_secrets or default_client_secrets_path()
    connection = GmailConnectionService(client_secrets_path=secrets)

    if args.action == "status":
        return _report(connection.status(), secrets)

    if args.action == "connect":
        print(f"Using client secrets: {secrets}")
        print("A browser window will open for Google consent...")
        return _report(connection.connect(port=args.port), secrets)

    if args.action == "test":
        return _report(connection.test(), secrets)

    if args.action == "disconnect":
        status = connection.disconnect()
        print("Disconnected. The stored credential was deleted from this machine.")
        print(
            "Note: the grant itself still exists in your Google account. "
            "Remove it there if you want it withdrawn."
        )
        return 0 if not status.connected else 1

    return _send_test_email(connection, args, secrets)


def _send_test_email(connection, args, secrets: Path) -> int:
    """Send one real email, to prove the whole path end to end."""
    status = connection.status()
    if not status.connected:
        return _report(status, secrets)

    recipient = args.to or status.account_email
    if not recipient:
        print("No recipient: pass --to, since the connected address is unknown.")
        return 2

    from datetime import timedelta

    from nexa.contracts.meetings import ActionItem, Meeting
    from nexa.contracts.people import Employee

    clock = SystemClock()
    now = clock.now_utc()
    employee = Employee(id=1, full_name=recipient.split("@")[0], email=recipient)
    meeting = Meeting(
        id=1,
        title="Nexa connection test",
        started_at=now,
        email_language=args.language,
    )
    action = ActionItem(
        id=1,
        meeting_id=1,
        task="Confirm that Nexa can send mail through Gmail",
        owner_employee_id=1,
        due_date=(clock.today() + timedelta(days=1)),
        source_text="This is a Nexa connection test, not a real action item.",
        review_state="APPROVED",
    )

    try:
        service = EmailService(
            sender=connection.sender(),
            clock=clock,
            from_email=status.account_email or "",
            connection=connection,
        )
        summary = service.send_meeting_report(
            meeting, [action], [employee], args.language
        )
    except EmailError as exc:
        print(f"FAILED: {exc}")
        return 1

    for attempt in summary.attempts:
        if attempt.ok:
            print(
                f"Sent to {attempt.recipient_email} "
                f"(Gmail message id {attempt.result.gmail_message_id})"
            )
        else:
            print(f"FAILED for {attempt.recipient_email}: {attempt.result.error_message}")
    return 0 if summary.all_ok else 1


def _report(status, secrets: Path) -> int:
    print(status.summary)
    if status.connected:
        print(f"  scopes: {', '.join(status.scopes)}")
        return 0
    if not status.store_available:
        print(
            "  No credential store on this machine. Install the project "
            "requirements (pip install -r requirements/base.txt); on Windows "
            "keyring uses the Credential Manager."
        )
    elif not Path(secrets).is_file():
        print(f"  No client secrets file at {secrets}")
        print("  Create a Google Cloud OAuth client (Desktop app) and save the")
        print("  downloaded JSON there. See docs/email.md.")
        print(f"  Data directory: {default_data_dir()}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
