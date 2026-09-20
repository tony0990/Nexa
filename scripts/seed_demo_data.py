"""Seed a Nexa database with the demo organization.

Used for the ministry demo (Section 42) and for manual testing of the UI
before the other subsystems are wired in. The data is the Section 40
acceptance meeting, so the demo script and the database agree.

    python scripts/seed_demo_data.py --data-dir ./demo-data
    python scripts/seed_demo_data.py --data-dir ./demo-data --reset
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, time, timedelta
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexa.audit import event_types  # noqa: E402
from nexa.audit.service import Actor, AuditService  # noqa: E402
from nexa.contracts.email import DeliveryKind, DeliveryTarget, TargetType  # noqa: E402
from nexa.contracts.meetings import (  # noqa: E402
    ActionItem,
    Meeting,
    MeetingStatus,
    MeetingTemplate,
    ReviewState,
    TranscriptSegment,
)
from nexa.core.clock import SystemClock  # noqa: E402
from nexa.core.config import NexaConfig  # noqa: E402
from nexa.data.database import open_database  # noqa: E402
from nexa.data.repositories.actions import ActionRepository  # noqa: E402
from nexa.data.repositories.deliveries import DeliveryRepository  # noqa: E402
from nexa.data.repositories.meetings import MeetingRepository  # noqa: E402
from nexa.data.repositories.settings import SettingsRepository  # noqa: E402
from nexa.data.repositories.templates import TemplateRepository  # noqa: E402
from nexa.data.transactions import unit_of_work  # noqa: E402
from nexa.people.service import PeopleService  # noqa: E402

EMPLOYEES = [
    ("أحمد حسن", "ahmed.hassan@example.com", "Development", "Backend Engineer", ["Developers"]),
    ("Mona Ali", "mona.ali@example.com", "Finance", "Accountant", ["Managers", "Finance Team"]),
    ("سارة نبيل", "sara.nabil@example.com", "Development", "QA Engineer", ["Developers", "QA"]),
    ("Khaled Ibrahim", "khaled.ibrahim@example.com", "Operations", "Coordinator", ["Managers"]),
    ("هدى سعيد", "hoda.said@example.com", "HR", "HR Specialist", []),
    ("Omar Fouad", "omar.fouad@example.com", "Legal", "Legal Advisor", ["Managers"]),
]

ROLES = [
    ("Managers", "Department heads and team leads"),
    ("Developers", "Software engineering team"),
    ("QA", "Quality assurance"),
    ("Finance Team", "Budget and accounting"),
]


def seed(data_dir: Path, *, reset: bool = False) -> None:
    config = NexaConfig(data_dir=data_dir)
    if reset and config.database_path.exists():
        config.database_path.unlink()
        for suffix in ("-wal", "-shm"):
            sibling = config.database_path.with_name(config.database_path.name + suffix)
            sibling.unlink(missing_ok=True)

    database = open_database(config)
    clock = SystemClock(config.timezone)
    actor = Actor.system()

    try:
        audit = AuditService(database, clock, default_actor=actor)
        people = PeopleService(database, clock, audit, actor=actor)

        SettingsRepository(database, clock).ensure_defaults()

        if people.list_employees():
            print("database already contains employees; use --reset to start clean")
            return

        with unit_of_work(database):
            for name, description in ROLES:
                people.create_role(name, description)

            role_ids = {role.name: role.id for role in people.list_roles()}
            for full_name, email, department, job_title, roles in EMPLOYEES:
                people.create_employee(
                    full_name,
                    email,
                    department=department,
                    job_title=job_title,
                    role_ids=[role_ids[name] for name in roles],
                )

            employees = {e.email: e for e in people.list_employees()}
            ahmed = employees["ahmed.hassan@example.com"]
            sara = employees["sara.nabil@example.com"]
            mona = employees["mona.ali@example.com"]

            templates = TemplateRepository(database, clock)
            template = templates.create(
                MeetingTemplate(
                    name="Weekly Development Meeting",
                    default_title="Weekly Development Meeting",
                    default_audio_source="BOTH",
                    default_email_language="AR",
                    default_report_target_config={
                        "targets": [{"target_type": "MEETING_PARTICIPANTS"}]
                    },
                    default_reminder_target_config={"targets": [{"target_type": "ASSIGNEE"}]},
                    default_reminder_rule_config={
                        "rules": [
                            {"rule_type": "PREVIOUS_DAY_FIXED", "fixed_local_time": "20:00"},
                            {"rule_type": "EVENT_DAY_FIXED", "fixed_local_time": "08:00"},
                        ]
                    },
                )
            )

            meetings = MeetingRepository(database, clock)
            meeting = meetings.create(
                Meeting(
                    title="Weekly Development Meeting",
                    template_id=template.id,
                    started_at=clock.now_utc() - timedelta(hours=1),
                    ended_at=clock.now_utc(),
                    audio_source="BOTH",
                    status=MeetingStatus.PENDING_REVIEW.value,
                    email_language="AR",
                    participant_ids=(ahmed.id, sara.id, mona.id),
                )
            )
            audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, meeting.id)

            # The Section 40 acceptance sentence, as it would be transcribed.
            meetings.add_segments(
                meeting.id,
                [
                    TranscriptSegment(
                        segment_index=0,
                        start_ms=0,
                        end_ms=7000,
                        raw_text=(
                            "أحمد يخلص الـdatabase before Monday، "
                            "والـpresentation تكون ready يوم الخميس الساعة three."
                        ),
                        language_hint="ar-EG",
                    ),
                    TranscriptSegment(
                        segment_index=1,
                        start_ms=7000,
                        end_ms=11000,
                        raw_text="وبالنسبة للbudget هنتكلم فيها بعدين.",
                        language_hint="ar-EG",
                    ),
                ],
            )

            actions = ActionRepository(database, clock)
            today = clock.today()
            created = [
                actions.create(
                    ActionItem(
                        meeting_id=meeting.id,
                        task="Finish database integration",
                        owner_employee_id=ahmed.id,
                        owner_raw_text="أحمد",
                        raw_date_phrase="before Monday",
                        due_date=_next_weekday(today, 0),
                        source_text="أحمد يخلص الـdatabase before Monday",
                        confidence=0.94,
                        review_state=ReviewState.APPROVED.value,
                    )
                ),
                actions.create(
                    ActionItem(
                        meeting_id=meeting.id,
                        task="Presentation ready",
                        owner_raw_text=None,
                        raw_date_phrase="يوم الخميس الساعة three",
                        due_date=_next_weekday(today, 3),
                        due_time=time(15, 0),
                        source_text="الـpresentation تكون ready يوم الخميس الساعة three",
                        confidence=0.81,
                    )
                ),
                actions.create(
                    ActionItem(
                        meeting_id=meeting.id,
                        task="Budget report",
                        owner_employee_id=mona.id,
                        due_date=today - timedelta(days=3),
                        source_text="التقرير يتسلم الخميس",
                        confidence=0.88,
                    )
                ),
            ]
            for action in created:
                audit.log(
                    event_types.ACTION_CREATED,
                    event_types.ENTITY_ACTION_ITEM,
                    action.id,
                    new_value={"task": action.task},
                )

            deliveries = DeliveryRepository(database, clock)
            deliveries.set_targets_for_meeting(
                meeting.id,
                DeliveryKind.REPORT.value,
                [DeliveryTarget(target_type=TargetType.MEETING_PARTICIPANTS.value)],
            )
            deliveries.set_targets_for_meeting(
                meeting.id,
                DeliveryKind.REMINDER.value,
                [DeliveryTarget(target_type=TargetType.ASSIGNEE.value)],
            )

        print(f"seeded demo database at {config.database_path}")
        print(f"  employees: {len(people.list_employees())}")
        print(f"  roles:     {len(people.list_roles())}")
        print(f"  meetings:  {MeetingRepository(database, clock).count()}")
        print(f"  actions:   {ActionRepository(database, clock).count()}")
    finally:
        database.close()


def _next_weekday(start: date, weekday: int) -> date:
    """The next occurrence of `weekday` (Mon=0) strictly after `start`."""
    days_ahead = (weekday - start.weekday()) % 7 or 7
    return start + timedelta(days=days_ahead)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the Nexa demo database")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("./demo-data"),
        help="where nexa.db should live (default: ./demo-data)",
    )
    parser.add_argument(
        "--reset", action="store_true", help="delete an existing database first"
    )
    args = parser.parse_args()
    seed(args.data_dir, reset=args.reset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
