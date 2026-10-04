from __future__ import annotations

from datetime import datetime, timedelta

from nexa.contracts.models import (
    ActionCandidate,
    ActionItem,
    AuditEvent,
    EmailPreview,
    Employee,
    Meeting,
    RecordedAudio,
    Reminder,
    RenderedEmail,
    Role,
    SendResult,
    Transcript,
)


class FakeAudioService:
    def __init__(self) -> None:
        self.running = False
        self.paused = False
        self.source = "mic+computer"
        self.started_at: datetime | None = None

    def start(self, source: str) -> str:
        self.source = source
        self.running = True
        self.paused = False
        self.started_at = datetime.now()
        return "session-demo"

    def pause(self) -> None:
        if self.running:
            self.paused = True

    def resume(self) -> None:
        if self.running:
            self.paused = False

    def stop(self) -> RecordedAudio:
        self.running = False
        self.paused = False
        duration = 0
        if self.started_at:
            duration = int((datetime.now() - self.started_at).total_seconds())
        return RecordedAudio(path="memory://demo-meeting.wav", duration_seconds=duration, source=self.source)


class FakeTranscriptionService:
    DEMO = "أحمد يخلص الـdatabase before Monday، والـpresentation تكون ready يوم الخميس الساعة three. وبالنسبة للbudget هنتكلم فيها بعدين."

    def transcribe(self, audio_path: str) -> Transcript:
        return Transcript(raw_text=self.DEMO, confirmed_text=self.DEMO, segments=[
            {"start_ms": 0, "end_ms": 8000, "text": self.DEMO}
        ])


class FakeExtractionService:
    def extract(self, transcript: Transcript, reference_datetime=None) -> list[ActionCandidate]:
        return [
            ActionCandidate(
                id=1,
                task="Finish database integration",
                owner_raw_text="أحمد",
                owner_employee_id=1,
                raw_date_phrase="before Monday",
                due_display="Monday, 7 September 2026",
                source_text="أحمد يخلص الـdatabase before Monday",
                confidence=0.94,
            ),
            ActionCandidate(
                id=2,
                task="Presentation ready",
                owner_raw_text="Unassigned",
                owner_employee_id=None,
                raw_date_phrase="يوم الخميس الساعة three",
                due_display="Thursday, 10 September 2026 3:00 PM",
                source_text="الـpresentation تكون ready يوم الخميس الساعة three",
                confidence=0.88,
            ),
            ActionCandidate(
                id=3,
                task="Complete database",
                owner_raw_text="أحمد",
                owner_employee_id=1,
                raw_date_phrase="before Monday",
                due_display="Monday, 7 September 2026",
                source_text="أحمد يخلص الـdatabase before Monday",
                confidence=0.71,
                possible_duplicate_of=1,
            ),
        ]


class FakePeopleService:
    def __init__(self) -> None:
        self._employees = [
            Employee(1, "Ahmed Hassan", "ahmed@nexa.local", "Development", "Backend Engineer", ["Developer"], True),
            Employee(5, "Ahmed Ali", "ahmed.ali@nexa.local", "Development", "Frontend Engineer", ["Developer"], True),
            Employee(2, "Maria Adel", "maria@nexa.local", "Management", "Project Manager", ["Manager"], True),
            Employee(3, "John Peter", "john@nexa.local", "HR", "HR Specialist", ["HR"], True),
            Employee(4, "Nadia Samir", "nadia@nexa.local", "Finance", "Analyst", ["Finance"], False),
        ]
        self._roles = [
            Role(1, "Developer", "Engineering delivery"),
            Role(2, "Manager", "Team and project leadership"),
            Role(3, "HR", "People operations"),
            Role(4, "Finance", "Budget and reporting"),
        ]
        self._next_emp = 6
        self._next_role = 5

    def list_employees(self, query: str = "", active: str = "all") -> list[Employee]:
        rows = list(self._employees)
        if active == "active":
            rows = [e for e in rows if e.active]
        elif active == "inactive":
            rows = [e for e in rows if not e.active]
        q = query.strip().lower()
        if q:
            rows = [e for e in rows if q in f"{e.full_name} {e.email} {e.department} {e.job_title} {' '.join(e.roles)}".lower()]
        return rows

    def create_employee(self, **kwargs) -> Employee:
        emp = Employee(
            id=self._next_emp,
            full_name=kwargs["full_name"],
            email=kwargs["email"],
            department=kwargs.get("department", ""),
            job_title=kwargs.get("job_title", ""),
            roles=kwargs.get("roles", []),
            active=True,
        )
        self._next_emp += 1
        self._employees.append(emp)
        return emp

    def update_employee(self, employee_id: int, **kwargs) -> Employee:
        emp = next(e for e in self._employees if e.id == employee_id)
        for key, value in kwargs.items():
            setattr(emp, key, value)
        return emp

    def deactivate_employee(self, employee_id: int) -> None:
        emp = next(e for e in self._employees if e.id == employee_id)
        emp.active = False

    def list_roles(self) -> list[Role]:
        return list(self._roles)

    def create_role(self, name: str, description: str = "") -> Role:
        role = Role(self._next_role, name, description, True)
        self._next_role += 1
        self._roles.append(role)
        return role

    def update_role(self, role_id: int, **kwargs) -> Role:
        role = next(r for r in self._roles if r.id == role_id)
        for key, value in kwargs.items():
            setattr(role, key, value)
        return role

    def deactivate_role(self, role_id: int) -> None:
        role = next(r for r in self._roles if r.id == role_id)
        role.active = False


class FakeSearchService:
    def __init__(self, people: FakePeopleService, reminders: "FakeReminderService") -> None:
        self.people = people
        self.reminders = reminders
        self.meetings = [
            Meeting(1, "Weekly Development Meeting", "Weekly Team Meeting", "mic+computer", ["Ahmed Hassan", "Maria Adel"], "APPROVED"),
            Meeting(2, "Project Review", "Project Review", "mic", ["Maria Adel", "John Peter"], "PENDING_REVIEW"),
            Meeting(3, "HR Meeting", "HR Meeting", "computer", ["John Peter"], "DRAFT"),
        ]

    def search_employees(self, query: str, filters: dict | None = None) -> list[Employee]:
        active = (filters or {}).get("active", "all")
        return self.people.list_employees(query, active)

    def search_meetings(self, query: str, filters: dict | None = None) -> list[Meeting]:
        q = query.strip().lower()
        rows = self.meetings
        status = (filters or {}).get("status")
        if status and status != "all":
            rows = [m for m in rows if m.status.lower() == status.lower()]
        if q:
            rows = [
                m
                for m in rows
                if q in m.title.lower()
                or any(q in p.lower() for p in m.participants)
                or (m.started_at and q in str(m.started_at).lower())
            ]
        return rows

    def search_tasks(self, query: str, filters: dict | None = None) -> list[ActionItem]:
        q = query.strip().lower()
        rows = self.reminders.list_actions(filters)
        if q:
            rows = [t for t in rows if q in t.task.lower() or q in t.owner_name.lower() or q in t.source_text.lower()]
        return rows

    def global_search(self, query: str) -> dict:
        return {
            "employees": self.search_employees(query),
            "meetings": self.search_meetings(query),
            "tasks": self.search_tasks(query),
        }


class FakeEmailService:
    def __init__(self) -> None:
        self.deliveries: list[dict] = [
            {"when": "2026-09-04 11:01", "kind": "REPORT", "subject": "Weekly Development Meeting — Action Report", "to": "8 recipients", "status": "SENT", "language": "ENGLISH"},
            {"when": "2026-09-08 20:00", "kind": "REMINDER", "subject": "[Nexa Reminder] Database Integration — Due Tomorrow", "to": "ahmed@nexa.local", "status": "SENT", "language": "ENGLISH"},
            {"when": "2026-09-09 08:00", "kind": "REMINDER", "subject": "تذكير: العرض التقديمي", "to": "maria@nexa.local", "status": "FAILED", "language": "ARABIC"},
        ]
        self.connected = False

    def build_meeting_report(self, meeting, actions, recipients, language) -> RenderedEmail:
        names = ", ".join(recipients) if recipients else "Ahmed Hassan, Maria Adel"
        rows = "".join(
            f"<tr><td>{a.task}</td><td>{getattr(a, 'owner_name', getattr(a, 'owner_raw_text', ''))}</td><td>{getattr(a, 'due_display', '')}</td></tr>"
            for a in actions
        )
        if language == "ARABIC":
            subject = f"تقرير مهام الاجتماع — {meeting}"
            html = f"<html dir='rtl'><body style='font-family:Segoe UI,Tahoma,sans-serif;color:#111'><h2>NEXA</h2><p>يرجى الاطلاع على المهام المعتمدة للاجتماع: {meeting}.</p><table border='1' cellpadding='8'><tr><th>المهمة</th><th>المسؤول</th><th>الموعد</th></tr>{rows}</table><p>مع التحية،<br>Nexa</p></body></html>"
            text = f"تقرير مهام الاجتماع: {meeting}\nالمستلمون: {names}"
        elif language == "BILINGUAL":
            subject = f"Meeting Action Report | تقرير مهام الاجتماع — {meeting}"
            html = (
                "<html><body style='font-family:Segoe UI,Tahoma,sans-serif;color:#111'>"
                "<h2>NEXA</h2><p>Meeting Action Report | تقرير مهام الاجتماع</p>"
                f"<p>Meeting | الاجتماع<br>{meeting}</p>"
                f"<table border='1' cellpadding='8'><tr><th>Action | المهمة</th><th>Owner | المسؤول</th><th>Deadline | الموعد</th></tr>{rows}</table>"
                "<p>Regards | مع التحية<br>Nexa</p></body></html>"
            )
            text = f"Meeting Action Report | تقرير مهام الاجتماع\n{meeting}\nTo: {names}"
        else:
            subject = f"[Nexa] Meeting Action Report — {meeting}"
            html = f"<html><body style='font-family:Segoe UI,sans-serif;color:#111'><h2>NEXA</h2><p>Please find the approved action items for {meeting}.</p><table border='1' cellpadding='8'><tr><th>Task</th><th>Owner</th><th>Deadline</th></tr>{rows}</table><p>Regards,<br>Nexa</p></body></html>"
            text = f"Meeting Action Report: {meeting}\nRecipients: {names}"
        return RenderedEmail(language, subject, html, text, "Nexa <nexa@example.com>", recipients or ["ahmed@nexa.local", "maria@nexa.local"])

    def build_reminder(self, employee, action, meeting, language) -> RenderedEmail:
        if language == "ARABIC":
            subject = f"[Nexa] تذكير: {action}"
            html = f"<html dir='rtl'><body><p>عزيزي {employee}، هذا تذكير بالمهمة المعتمدة «{action}» من اجتماع {meeting}.</p></body></html>"
            text = f"تذكير: {action}"
        elif language == "BILINGUAL":
            subject = f"[Nexa Reminder] {action} | تذكير"
            html = f"<html><body><p>Dear {employee} | عزيزي {employee}</p><p>Reminder for {action} | تذكير بالمهمة {action}</p><p>Meeting | الاجتماع: {meeting}</p></body></html>"
            text = f"Reminder | تذكير: {action}"
        else:
            subject = f"[Nexa Reminder] {action} — Due Soon"
            html = f"<html><body><p>Dear {employee},</p><p>This is a reminder that your assigned action item \"{action}\" is due soon.</p><p>Meeting: {meeting}</p><p>Regards,<br>Nexa</p></body></html>"
            text = f"Reminder: {action}"
        return RenderedEmail(language, subject, html, text, "Nexa <nexa@example.com>", [f"{employee}@nexa.local"])

    def preview(self, rendered_email: RenderedEmail) -> EmailPreview:
        return EmailPreview(rendered_email)

    def send(self, message: RenderedEmail) -> SendResult:
        self.deliveries.insert(0, {
            "when": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "kind": "REPORT",
            "subject": message.subject,
            "to": ", ".join(message.recipients),
            "status": "SENT",
            "language": message.language,
        })
        return SendResult(True, "fake-msg-1001")

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def test(self) -> bool:
        return self.connected


class FakeReminderService:
    def __init__(self) -> None:
        self._actions = [
            ActionItem(1, 1, "Finish database integration", "Ahmed Hassan", "Mon 7 Sep 2026 10:00", "Today 08:00", "PENDING", "أحمد يخلص الـdatabase before Monday", "Weekly Development Meeting", "2026-09-07"),
            ActionItem(2, 1, "Presentation ready", "Unassigned", "Thu 10 Sep 2026 15:00", "Today 08:00", "PENDING", "الـpresentation تكون ready يوم الخميس الساعة three", "Weekly Development Meeting", "2026-09-10"),
            ActionItem(3, 2, "API Review", "John Peter", "Wed 3 Sep 2026 12:00", "Wed 3 Sep 2026 08:00", "OVERDUE", "API review by noon", "Project Review", "2026-09-03"),
            ActionItem(4, 1, "HR list update", "Maria Adel", "Tue 8 Sep 2026 09:00", "Mon 7 Sep 2026 20:00", "PENDING", "Update the HR list tomorrow morning", "Weekly Development Meeting", "2026-09-08"),
        ]
        self._reminders = [
            Reminder(1001, 1, "Today 08:00", "PENDING"),
            Reminder(1002, 2, "Today 08:00", "PENDING"),
            Reminder(1003, 3, "Yesterday 08:00", "FAILED"),
        ]

    def list_actions(self, filters: dict | None = None) -> list[ActionItem]:
        rows = list(self._actions)
        filters = filters or {}
        status = filters.get("status")
        owner = filters.get("owner")
        if status == "unassigned" or (owner and owner.lower() == "unassigned"):
            rows = [a for a in rows if a.owner_name.lower() in {"unassigned", "غير معيّن"}]
        elif status == "SNOOZED":
            snoozed = {r.action_item_id for r in self._reminders if r.status == "SNOOZED"}
            rows = [a for a in rows if a.id in snoozed]
        elif status and status != "all":
            rows = [a for a in rows if a.status.lower() == status.lower()]
        elif owner:
            rows = [a for a in rows if owner.lower() in a.owner_name.lower()]
        return rows

    def mark_complete(self, action_id: int, actor: str = "Admin") -> None:
        for a in self._actions:
            if a.id == action_id:
                a.status = "COMPLETED"
        for r in self._reminders:
            if r.action_item_id == action_id and r.status in {"PENDING", "SNOOZED", "RETRY_WAIT"}:
                r.status = "SKIPPED_COMPLETED"

    def snooze(self, reminder_id: int, new_time: str) -> None:
        for a in self._actions:
            if a.id == reminder_id:
                a.reminder_display = new_time
                if a.status != "COMPLETED":
                    a.status = "PENDING"
        for r in self._reminders:
            if r.id == reminder_id or r.action_item_id == reminder_id:
                r.scheduled_display = new_time
                r.status = "SNOOZED"

    def reschedule_action(self, action_id: int, new_due_at: str) -> None:
        for a in self._actions:
            if a.id == action_id:
                try:
                    when = datetime.strptime(new_due_at, "%Y-%m-%d %H:%M")
                    a.due_display = when.strftime("%a %d %b %Y %H:%M")
                    a.due_iso = when.strftime("%Y-%m-%d")
                except ValueError:
                    a.due_display = new_due_at

    def send_test_reminder(self, action_id: int) -> SendResult:
        return SendResult(True, f"fake-reminder-{action_id}")

    def import_approved(self, meeting_title: str, items, meeting_id: int = 1) -> None:
        next_id = max((a.id for a in self._actions), default=0)
        next_reminder = max((r.id for r in self._reminders), default=1000)
        for item in items:
            next_id += 1
            next_reminder += 1
            owner = getattr(item, "owner_raw_text", "") or "Unassigned"
            due = getattr(item, "due_display", "") or "Time not specified"
            self._actions.append(
                ActionItem(
                    id=next_id,
                    meeting_id=meeting_id,
                    task=item.task or "Untitled action",
                    owner_name=owner,
                    due_display=due,
                    reminder_display="Previous day 20:00",
                    status="PENDING",
                    source_text=getattr(item, "source_text", ""),
                    meeting_title=meeting_title,
                    due_iso="",
                )
            )
            self._reminders.append(Reminder(next_reminder, next_id, "Previous day 20:00", "PENDING"))

    def dashboard_counts(self) -> dict:
        pending_review = 2
        return {
            "upcoming": sum(1 for a in self._actions if a.status == "PENDING"),
            "reminders_today": 2,
            "pending_review": pending_review,
            "overdue": sum(1 for a in self._actions if a.status == "OVERDUE"),
            "email_failures": 1,
            "completed": sum(1 for a in self._actions if a.status == "COMPLETED"),
        }


class FakeAuditService:
    def __init__(self) -> None:
        now = datetime.now()
        self._events = [
            AuditEvent((now - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M"), "meeting.create", "meeting", "1", "Admin", "Meeting created"),
            AuditEvent((now - timedelta(minutes=18)).strftime("%Y-%m-%d %H:%M"), "recording.start", "meeting", "1", "Admin", "Recording started"),
            AuditEvent((now - timedelta(minutes=8)).strftime("%Y-%m-%d %H:%M"), "recording.stop", "meeting", "1", "Admin", "Recording stopped"),
            AuditEvent((now - timedelta(minutes=6)).strftime("%Y-%m-%d %H:%M"), "extraction.complete", "meeting", "1", "System", "AI extraction completed"),
            AuditEvent((now - timedelta(minutes=4)).strftime("%Y-%m-%d %H:%M"), "action.edit", "action", "17", "Admin", "Date changed from Sep 8 to Sep 9"),
            AuditEvent((now - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M"), "action.assign", "action", "18", "Admin", "Assigned to Ahmed Hassan"),
            AuditEvent(now.strftime("%Y-%m-%d %H:%M"), "email.send", "meeting", "1", "Admin", "Report sent to 8 recipients"),
        ]

    def history(self, entity_type: str | None = None) -> list[AuditEvent]:
        if not entity_type or entity_type == "all":
            return list(self._events)
        return [e for e in self._events if e.entity_type == entity_type]

    def record(self, event: AuditEvent) -> None:
        self._events.insert(0, event)


class FakeServiceContainer:
    """Demo backends so Member 6 can ship the full UI independently."""

    def __init__(self) -> None:
        self.audio = FakeAudioService()
        self.transcription = FakeTranscriptionService()
        self.extraction = FakeExtractionService()
        self.people = FakePeopleService()
        self.reminders = FakeReminderService()
        self.search = FakeSearchService(self.people, self.reminders)
        self.email = FakeEmailService()
        self.audit = FakeAuditService()
        self.worker_online = True
        self.models = {"speech": True, "llm": True}
