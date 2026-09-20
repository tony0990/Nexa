"""Deterministic bulk dataset generator for Member 1's scale tests.

Section 21.5 asks for 1,000 fake employees, roles, meetings and tasks to
validate search speed, filtering, unique recipient resolution, transactions
and audit history. The data is generated from a fixed seed so a failure is
reproducible, and it mixes Arabic, English and code-switched text because
that is what the real database will hold.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import List

from nexa.contracts.meetings import ActionItem, ActionStatus, Meeting, MeetingStatus
from nexa.contracts.people import Employee, Role
from nexa.data.repositories.actions import ActionRepository
from nexa.data.repositories.employees import EmployeeRepository
from nexa.data.repositories.meetings import MeetingRepository
from nexa.data.repositories.roles import RoleRepository
from nexa.data.transactions import unit_of_work

ARABIC_FIRST_NAMES = [
    "أحمد", "محمد", "مصطفى", "إسلام", "فاطمة", "منى", "سارة", "هدى", "خالد", "ياسمين",
]
ARABIC_LAST_NAMES = ["حسن", "علي", "إبراهيم", "عبد الله", "نبيل", "سعيد", "فؤاد", "رمضان"]
ENGLISH_FIRST_NAMES = ["Ahmed", "Mona", "Sara", "Khaled", "Nour", "Omar", "Laila", "Hana"]
ENGLISH_LAST_NAMES = ["Hassan", "Ali", "Ibrahim", "Nabil", "Fouad", "Said", "Ramadan"]

DEPARTMENTS = ["Development", "Finance", "Operations", "HR", "Legal"]
JOB_TITLES = ["Engineer", "Accountant", "Coordinator", "Manager", "Analyst"]
ROLE_NAMES = [
    "Managers", "Developers", "QA", "Finance Team", "Department Heads",
    "Support", "Interns", "Security", "Procurement", "Leadership",
]

TASK_TEMPLATES = [
    "Finish database integration",
    "Prepare the monthly report",
    "تجهيز العرض التقديمي",
    "مراجعة الميزانية",
    "Send the الـpresentation to the team",
    "Review API documentation",
    "تسليم التقرير النهائي",
]
EVIDENCE_TEMPLATES = [
    "أحمد يخلص الـdatabase before Monday",
    "الـpresentation تكون ready يوم الخميس الساعة three",
    "The final report يتبعت يوم الاتنين الساعة four",
    "بكرة عندنا meeting الساعة ten",
]
DATE_PHRASES = ["before Monday", "يوم الخميس", "قبل يوم الاتنين", "next week", "بكرة"]


@dataclass
class Dataset:
    employee_ids: List[int]
    role_ids: List[int]
    meeting_ids: List[int]
    action_ids: List[int]


def build_dataset(
    db,
    clock,
    *,
    employees: int = 1000,
    roles: int = len(ROLE_NAMES),
    meetings: int = 200,
    actions: int = 1000,
    seed: int = 20260920,
) -> Dataset:
    """Populate an empty database and return the ids that were created."""
    rng = random.Random(seed)

    employee_repo = EmployeeRepository(db, clock)
    role_repo = RoleRepository(db, clock)
    meeting_repo = MeetingRepository(db, clock)
    action_repo = ActionRepository(db, clock)

    role_ids = []
    for index in range(roles):
        name = ROLE_NAMES[index] if index < len(ROLE_NAMES) else f"Role {index}"
        role_ids.append(role_repo.create(Role(name=name)).id)

    employee_repo.bulk_create(
        Employee(
            full_name=_name(rng, index),
            email=f"employee{index}@example.com",
            department=rng.choice(DEPARTMENTS),
            job_title=rng.choice(JOB_TITLES),
            # Roughly one in twelve has left the organization.
            active=index % 12 != 0,
        )
        for index in range(employees)
    )
    employee_ids = [row["id"] for row in db.query_all("SELECT id FROM employees ORDER BY id")]

    # Every employee holds one or two roles.
    with unit_of_work(db):
        now = employee_repo.now_str()
        assignments = []
        for employee_id in employee_ids:
            for role_id in rng.sample(role_ids, rng.choice([1, 1, 2])):
                assignments.append((employee_id, role_id, now))
        db.executemany(
            "INSERT OR IGNORE INTO employee_roles (employee_id, role_id, created_at) "
            "VALUES (?, ?, ?)",
            assignments,
        )

    meeting_ids = []
    statuses = [status.value for status in MeetingStatus]
    for index in range(meetings):
        started = clock.now_utc() - timedelta(days=rng.randint(0, 90), hours=rng.randint(0, 8))
        meeting = meeting_repo.create(
            Meeting(
                title=f"{rng.choice(['Weekly', 'Monthly', 'اجتماع'])} Meeting {index}",
                started_at=started,
                status=rng.choice(statuses),
                participant_ids=tuple(rng.sample(employee_ids, rng.randint(2, 8))),
            )
        )
        meeting_ids.append(meeting.id)

    action_ids = []
    action_statuses = [status.value for status in ActionStatus]
    with unit_of_work(db):
        for index in range(actions):
            offset = rng.randint(-45, 45)
            has_time = rng.random() < 0.5
            action = action_repo.create(
                ActionItem(
                    meeting_id=rng.choice(meeting_ids),
                    task=f"{rng.choice(TASK_TEMPLATES)} #{index}",
                    owner_employee_id=(
                        rng.choice(employee_ids) if rng.random() < 0.8 else None
                    ),
                    owner_raw_text=rng.choice(ARABIC_FIRST_NAMES),
                    raw_date_phrase=rng.choice(DATE_PHRASES),
                    due_date=clock.today() + timedelta(days=offset),
                    due_time=time(rng.randint(8, 17), 0) if has_time else None,
                    source_text=rng.choice(EVIDENCE_TEMPLATES),
                    confidence=round(rng.uniform(0.5, 1.0), 2),
                    status=rng.choice(action_statuses),
                )
            )
            action_ids.append(action.id)

    return Dataset(
        employee_ids=employee_ids,
        role_ids=role_ids,
        meeting_ids=meeting_ids,
        action_ids=action_ids,
    )


def _name(rng: random.Random, index: int) -> str:
    """Half Arabic, half English names, with a stable index suffix."""
    if index % 2 == 0:
        first = rng.choice(ARABIC_FIRST_NAMES)
        last = rng.choice(ARABIC_LAST_NAMES)
    else:
        first = rng.choice(ENGLISH_FIRST_NAMES)
        last = rng.choice(ENGLISH_LAST_NAMES)
    return f"{first} {last} {index}"
