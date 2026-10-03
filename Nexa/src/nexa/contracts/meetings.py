from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional


@dataclass
class ActionItem:
    id: int
    meeting_id: Optional[int] = None
    task: str = ""
    owner_employee_id: Optional[int] = None
    owner_raw_text: Optional[str] = None
    raw_date_phrase: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    due_at: Optional[datetime] = None
    source_text: Optional[str] = None
    confidence: Optional[float] = None
    review_state: Optional[str] = None
    status: str = "PENDING"   # PENDING | COMPLETED | OVERDUE | CANCELLED
    completed_at: Optional[datetime] = None


@dataclass
class Meeting:
    id: int
    title: str = ""
    email_language: Optional[str] = None
    status: Optional[str] = None
