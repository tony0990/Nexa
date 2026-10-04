def format_employee_results(employees, empty: str) -> str:
    if not employees:
        return empty
    return "\n".join(f"• {e.full_name} — {e.department}" for e in employees)


def format_meeting_results(meetings, empty: str) -> str:
    if not meetings:
        return empty
    return "\n".join(f"• {m.title} — {', '.join(m.participants)}" for m in meetings)


def format_task_results(tasks, empty: str) -> str:
    if not tasks:
        return empty
    return "\n".join(f"• {a.task} — {a.owner_name} — {a.due_display}" for a in tasks)
