from PySide6.QtCore import QDate
from PySide6.QtGui import QBrush, QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import QCalendarWidget


def make_calendar() -> QCalendarWidget:
    calendar = QCalendarWidget()
    calendar.setGridVisible(True)
    calendar._marked: set[str] = set()
    return calendar


def mark_dates(calendar: QCalendarWidget, iso_dates: set[str]) -> None:
    """Highlight days that have deadlines (readable in light and dark themes)."""
    for iso in getattr(calendar, "_marked", set()):
        calendar.setDateTextFormat(QDate.fromString(iso, "yyyy-MM-dd"), QTextCharFormat())
    fmt = QTextCharFormat()
    fmt.setBackground(QBrush(QColor("#2563eb")))
    fmt.setForeground(QBrush(QColor("#ffffff")))
    fmt.setFontWeight(QFont.Bold)
    for iso in iso_dates:
        date = QDate.fromString(iso, "yyyy-MM-dd")
        if date.isValid():
            calendar.setDateTextFormat(date, fmt)
    calendar._marked = set(iso_dates)
