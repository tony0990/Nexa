"""Formal Arabic lexicon for reports and reminders (Section 10.1).

Every user-visible Arabic string in an email lives here. The tone target is
institutional correspondence, not meeting speech: a task spoken as
`أحمد يخلص الـbackend قبل Monday` becomes

    استكمال أعمال الواجهة الخلفية (Backend) — المسؤول: أحمد — الموعد النهائي: يوم الاثنين.

Nexa does not rewrite the task text itself (that would mean inventing content
the admin never approved, which Section 24.1 forbids). What this module
supplies is the formal *frame* around the approved data: salutation, labels,
deadline phrasing and closing.

Names are never transliterated or translated (Section 10.3). Technical English
terms inside a task are left as the admin approved them.
"""

from __future__ import annotations

DIRECTION = "rtl"
LANG_ATTR = "ar"

# Gregorian month names as used in Egyptian formal writing.
MONTHS = (
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
)

# Indexed by `date.weekday()` (Monday = 0).
WEEKDAYS = (
    "الاثنين",
    "الثلاثاء",
    "الأربعاء",
    "الخميس",
    "الجمعة",
    "السبت",
    "الأحد",
)

MERIDIEM = {"am": "صباحاً", "pm": "مساءً"}

LABELS = {
    "report_title": "تقرير مهام الاجتماع",
    "reminder_title": "تذكير بمهمة",
    "meeting": "الاجتماع",
    "date": "التاريخ",
    "action_items": "المهام",
    "number": "م",
    "task": "المهمة",
    "owner": "المسؤول",
    "deadline": "الموعد النهائي",
    "status": "الحالة",
    "evidence": "النص الأصلي",
    "needs_review": "بحاجة إلى مراجعة",
    "no_actions": "لم تُسجَّل مهام لهذا الاجتماع.",
    "generated_at": "تاريخ الإصدار",
    "unassigned": "غير مُسنَدة",
    "time_not_specified": "الوقت غير محدد",
    "date_not_specified": "الموعد غير محدد",
}

STATUSES = {
    "PENDING": "قيد التنفيذ",
    "COMPLETED": "مكتملة",
    "OVERDUE": "متأخرة",
    "CANCELLED": "ملغاة",
}

REVIEW_NOTE = "تمت الإشارة إلى هذه المهمة لمراجعتها قبل اعتمادها النهائي."

SIGNATURE = "مع التحية،\nنظام Nexa"


def greeting(name: str) -> str:
    """Formal salutation. Falls back to a neutral form when unnamed."""
    name = (name or "").strip()
    return f"السيد/السيدة {name}،" if name else "تحية طيبة،"


def report_intro(meeting_title: str, count: int) -> str:
    """Opening paragraph of a meeting report."""
    if count == 0:
        return (
            f"نرفق إليكم تقرير اجتماع «{meeting_title}». "
            "لم تُسجَّل أي مهام أو مواعيد مرتبطة بهذا الاجتماع."
        )
    if count == 1:
        return (
            f"نرفق إليكم تقرير اجتماع «{meeting_title}»، "
            "ويتضمن مهمة واحدة معتمدة مع موعدها المحدد أدناه."
        )
    return (
        f"نرفق إليكم تقرير اجتماع «{meeting_title}»، "
        f"ويتضمن {count} مهام معتمدة مع مواعيدها المحددة أدناه."
    )


def report_closing() -> str:
    return "نرجو الالتزام بالمواعيد المذكورة، وفي حال وجود أي ملاحظة يُرجى إبلاغنا."


def reminder_intro(task: str, due_phrase: str) -> str:
    """Opening paragraph of a personalized reminder (Section 11)."""
    return f"نود تذكيركم بأن المهمة المسندة إليكم «{task}» {due_phrase}."


def reminder_closing() -> str:
    return "في حال إنجاز المهمة، يُرجى تحديث حالتها في النظام."


def due_phrase(days_until: "int | None") -> str:
    """Natural-language urgency, e.g. "مستحقة غداً"."""
    if days_until is None:
        return "لم يُحدَّد لها موعد بعد"
    if days_until < 0:
        overdue = abs(days_until)
        if overdue == 1:
            return "تجاوزت موعدها النهائي بيوم واحد"
        return f"تجاوزت موعدها النهائي بـ {overdue} أيام"
    if days_until == 0:
        return "مستحقة اليوم"
    if days_until == 1:
        return "مستحقة غداً"
    return f"مستحقة بعد {days_until} أيام"


def subject_report(meeting_title: str, meeting_date: str) -> str:
    return f"[Nexa] تقرير مهام الاجتماع — {meeting_title} — {meeting_date}"


def subject_reminder(task: str, days_until: "int | None") -> str:
    return f"[Nexa] تذكير — {task} — {due_phrase(days_until)}"
