"""Meeting, participant and transcript-segment persistence.

Member 2 and Member 3 write transcript segments through this repository
instead of touching SQLite directly, so the normalized search column and the
timestamps stay consistent.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from ...contracts.meetings import Meeting, MeetingStatus, TranscriptSegment
from ...core.errors import NotFoundError
from ...core.timezone import isoformat_utc
from ...core.validation import normalize_search_text
from ..models import row_to_meeting, row_to_segment
from ..transactions import unit_of_work
from .base import BaseRepository

_COLUMNS = (
    "id, title, template_id, started_at, ended_at, audio_source, status, "
    "email_language, created_at, updated_at"
)
_SEGMENT_COLUMNS = (
    "id, meeting_id, segment_index, start_ms, end_ms, raw_text, confirmed_text, "
    "language_hint, created_at"
)


class MeetingRepository(BaseRepository):
    # ------------------------------------------------------------------
    # meetings
    # ------------------------------------------------------------------
    def create(self, meeting: Meeting) -> Meeting:
        now = self.now_str()
        with unit_of_work(self.db):
            self.db.execute(
                """
                INSERT INTO meetings (
                    title, title_norm, template_id, started_at, ended_at,
                    audio_source, status, email_language, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meeting.title,
                    normalize_search_text(meeting.title),
                    meeting.template_id,
                    isoformat_utc(meeting.started_at, self.tz),
                    isoformat_utc(meeting.ended_at, self.tz),
                    meeting.audio_source,
                    meeting.status,
                    meeting.email_language,
                    now,
                    now,
                ),
            )
            meeting_id = self._last_insert_id()
            if meeting.participant_ids:
                self._replace_participants(meeting_id, meeting.participant_ids, now)
        return self.get_or_raise(meeting_id)

    def update(self, meeting: Meeting) -> Meeting:
        if meeting.id is None:
            raise ValueError("meeting.id is required for update")
        now = self.now_str()
        with unit_of_work(self.db):
            cursor = self.db.execute(
                """
                UPDATE meetings
                   SET title = ?, title_norm = ?, template_id = ?, started_at = ?,
                       ended_at = ?, audio_source = ?, status = ?,
                       email_language = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    meeting.title,
                    normalize_search_text(meeting.title),
                    meeting.template_id,
                    isoformat_utc(meeting.started_at, self.tz),
                    isoformat_utc(meeting.ended_at, self.tz),
                    meeting.audio_source,
                    meeting.status,
                    meeting.email_language,
                    now,
                    meeting.id,
                ),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("meeting", meeting.id)
        return self.get_or_raise(meeting.id)

    def set_status(self, meeting_id: int, status: str) -> Meeting:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "UPDATE meetings SET status = ?, updated_at = ? WHERE id = ?",
                (getattr(status, "value", status), self.now_str(), meeting_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("meeting", meeting_id)
        return self.get_or_raise(meeting_id)

    def delete(self, meeting_id: int) -> None:
        with unit_of_work(self.db):
            cursor = self.db.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
            if cursor.rowcount == 0:
                raise NotFoundError("meeting", meeting_id)

    def get(self, meeting_id: int) -> Optional[Meeting]:
        row = self.db.query_one(f"SELECT {_COLUMNS} FROM meetings WHERE id = ?", (meeting_id,))
        if row is None:
            return None
        return row_to_meeting(row, self.participant_ids(meeting_id))

    def get_or_raise(self, meeting_id: int) -> Meeting:
        meeting = self.get(meeting_id)
        if meeting is None:
            raise NotFoundError("meeting", meeting_id)
        return meeting

    def list_recent(self, limit: int = 50) -> List[Meeting]:
        rows = self.db.query_all(
            f"SELECT {_COLUMNS} FROM meetings "
            "ORDER BY COALESCE(started_at, created_at) DESC LIMIT ?",
            (limit,),
        )
        participants = self.participant_ids_for_many([row["id"] for row in rows])
        return [row_to_meeting(row, participants.get(row["id"], ())) for row in rows]

    def count(self) -> int:
        return int(self.db.query_value("SELECT COUNT(*) FROM meetings", default=0))

    # ------------------------------------------------------------------
    # participants
    # ------------------------------------------------------------------
    def set_participants(self, meeting_id: int, employee_ids: Sequence[int]) -> List[int]:
        with unit_of_work(self.db):
            if self.db.query_one("SELECT 1 FROM meetings WHERE id = ?", (meeting_id,)) is None:
                raise NotFoundError("meeting", meeting_id)
            self._replace_participants(meeting_id, employee_ids, self.now_str())
        return self.participant_ids(meeting_id)

    def add_participant(self, meeting_id: int, employee_id: int) -> bool:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO meeting_participants "
                "(meeting_id, employee_id, created_at) VALUES (?, ?, ?)",
                (meeting_id, employee_id, self.now_str()),
            )
            return cursor.rowcount > 0

    def remove_participant(self, meeting_id: int, employee_id: int) -> bool:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "DELETE FROM meeting_participants WHERE meeting_id = ? AND employee_id = ?",
                (meeting_id, employee_id),
            )
            return cursor.rowcount > 0

    def participant_ids(self, meeting_id: int) -> List[int]:
        rows = self.db.query_all(
            "SELECT employee_id FROM meeting_participants WHERE meeting_id = ? "
            "ORDER BY employee_id",
            (meeting_id,),
        )
        return [row["employee_id"] for row in rows]

    def participant_ids_for_many(self, meeting_ids: Sequence[int]) -> Dict[int, tuple]:
        ids = [int(i) for i in meeting_ids]
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        rows = self.db.query_all(
            "SELECT meeting_id, employee_id FROM meeting_participants "
            f"WHERE meeting_id IN ({placeholders}) ORDER BY meeting_id, employee_id",
            ids,
        )
        result: Dict[int, list] = {}
        for row in rows:
            result.setdefault(row["meeting_id"], []).append(row["employee_id"])
        return {key: tuple(value) for key, value in result.items()}

    def _replace_participants(
        self, meeting_id: int, employee_ids: Sequence[int], now: str
    ) -> None:
        self.db.execute("DELETE FROM meeting_participants WHERE meeting_id = ?", (meeting_id,))
        unique_ids = list(dict.fromkeys(int(i) for i in employee_ids))
        if unique_ids:
            self.db.executemany(
                "INSERT INTO meeting_participants (meeting_id, employee_id, created_at) "
                "VALUES (?, ?, ?)",
                [(meeting_id, employee_id, now) for employee_id in unique_ids],
            )

    # ------------------------------------------------------------------
    # transcript segments
    # ------------------------------------------------------------------
    def add_segments(self, meeting_id: int, segments: Iterable[TranscriptSegment]) -> int:
        now = self.now_str()
        rows = []
        for segment in segments:
            text = segment.confirmed_text or segment.raw_text
            rows.append(
                (
                    meeting_id,
                    segment.segment_index,
                    segment.start_ms,
                    segment.end_ms,
                    segment.raw_text,
                    segment.confirmed_text,
                    normalize_search_text(text),
                    segment.language_hint,
                    now,
                )
            )
        with unit_of_work(self.db):
            self.db.executemany(
                """
                INSERT INTO transcript_segments (
                    meeting_id, segment_index, start_ms, end_ms, raw_text,
                    confirmed_text, text_norm, language_hint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def confirm_segment(self, segment_id: int, confirmed_text: str) -> TranscriptSegment:
        """Store the human-confirmed wording. `raw_text` is never overwritten."""
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "UPDATE transcript_segments SET confirmed_text = ?, text_norm = ? WHERE id = ?",
                (confirmed_text, normalize_search_text(confirmed_text), segment_id),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("transcript_segment", segment_id)
        row = self.db.query_one(
            f"SELECT {_SEGMENT_COLUMNS} FROM transcript_segments WHERE id = ?", (segment_id,)
        )
        return row_to_segment(row)

    def segments(self, meeting_id: int) -> List[TranscriptSegment]:
        rows = self.db.query_all(
            f"SELECT {_SEGMENT_COLUMNS} FROM transcript_segments "
            "WHERE meeting_id = ? ORDER BY segment_index",
            (meeting_id,),
        )
        return [row_to_segment(row) for row in rows]

    def delete_segments(self, meeting_id: int) -> int:
        """Apply the transcript retention policy for one meeting."""
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "DELETE FROM transcript_segments WHERE meeting_id = ?", (meeting_id,)
            )
            return cursor.rowcount

    def statuses(self) -> List[str]:
        return [status.value for status in MeetingStatus]
