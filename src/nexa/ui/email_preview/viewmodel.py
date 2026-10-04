class EmailPreviewViewModel:
    LANGUAGES = ["ENGLISH", "ARABIC", "BILINGUAL"]
    TARGETS = ["ASSIGNEE", "ALL", "PARTICIPANTS", "ROLE", "ASSIGNEE_PLUS_ROLE", "CUSTOM"]
    # Reminder recipients are chosen independently of report recipients (spec 6.3 / flow step 18).
    REMINDER_TARGETS = ["ASSIGNEE", "ASSIGNEE_PLUS_ROLE", "SAME_AS_REPORT", "CUSTOM"]

    def __init__(self, email_service, people, state=None) -> None:
        self.email = email_service
        self.people = people
        self.state = state
        self.meeting_title = "Weekly Development Meeting"
        self.actions = []
        self.participants: list[str] = []
        self.rendered = None
        self.reminder_recipients: list[str] = []

    def default_language(self) -> str:
        if self.state and getattr(self.state, "email_language", None) in self.LANGUAGES:
            return self.state.email_language
        return "ENGLISH"

    def default_recipients(self) -> list[str]:
        return self.recipients_for_mode("ASSIGNEE")

    def role_names(self) -> list[str]:
        return [r.name for r in self.people.list_roles() if getattr(r, "active", True)]

    def recipients_for_mode(self, mode: str, role: str | None = None) -> list[str]:
        if mode == "ALL":
            return [e.full_name for e in self.people.list_employees("", "active")]
        if mode == "PARTICIPANTS":
            return list(dict.fromkeys(self.participants or ["Ahmed Hassan", "Maria Adel"]))
        if mode in {"ROLE", "ASSIGNEE_PLUS_ROLE"}:
            by_role = [
                e.full_name
                for e in self.people.list_employees("", "active")
                if role and role in (e.roles or [])
            ]
            if mode == "ROLE":
                return by_role
            return list(dict.fromkeys(self.recipients_for_mode("ASSIGNEE") + by_role))
        names = []
        for action in self.actions:
            owner = getattr(action, "owner_raw_text", "") or getattr(action, "owner_name", "")
            if owner and owner not in names and owner not in {"Unassigned", "غير معيّن"}:
                names.append(owner)
        if not names:
            names = [e.full_name for e in self.people.list_employees("", "active")]
        return names

    def reminder_recipients_for(
        self,
        mode: str,
        role: str | None = None,
        report_recipients: list[str] | None = None,
        custom: list[str] | None = None,
    ) -> list[str]:
        """De-duplicated reminder recipients; never silently falls back to everyone."""
        if mode == "SAME_AS_REPORT":
            names = list(report_recipients or [])
        elif mode == "CUSTOM":
            names = list(custom or [])
        elif mode == "ASSIGNEE_PLUS_ROLE":
            names = self.recipients_for_mode("ASSIGNEE_PLUS_ROLE", role)
        else:
            names = self.recipients_for_mode("ASSIGNEE")
        return list(dict.fromkeys(n.strip() for n in names if n and n.strip()))

    def build(self, language: str, recipients: list[str]):
        unique = list(dict.fromkeys(recipients))
        self.rendered = self.email.build_meeting_report(self.meeting_title, self.actions, unique, language)
        sender_name = getattr(self.state, "sender_name", "") if self.state else ""
        if sender_name:
            self.rendered.sender = f"{sender_name} <nexa@example.com>"
        return self.email.preview(self.rendered)
