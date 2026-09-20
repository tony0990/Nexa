"""Meeting search: title, date, participant, extracted task text (Section 6.4)."""

from __future__ import annotations

from typing import List, Optional

from ..contracts.meetings import Meeting
from ..core.clock import Clock, SystemClock
from ..core.validation import like_pattern, normalize_search_text
from ..data.database import Database
from ..data.models import row_to_meeting
from ..data.repositories.meetings import MeetingRepository
from .filters import Conditions, MeetingFilters, clamp_limit

_COLUMNS = (
    "m.id AS id, m.title AS title, m.template_id AS template_id, "
    "m.started_at AS started_at, m.ended_at AS ended_at, "
    "m.audio_source AS audio_source, m.status AS status, "
    "m.email_language AS email_language, m.created_at AS created_at, "
    "m.updated_at AS updated_at"
)

# A meeting matches when its own title matches, or a participant's name does,
# or one of its action items does. Searching "Ahmed" should find the meeting
# Ahmed attended, which is exactly the Section 31 example.
_MATCH = """(
    m.title_norm LIKE ? ESCAPE '\\'
 OR EXISTS (SELECT 1 FROM meeting_participants mp
              JOIN employees e ON e.id = mp.employee_id
             WHERE mp.meeting_id = m.id AND e.search_text LIKE ? ESCAPE '\\')
 OR EXISTS (SELECT 1 FROM action_items a
             WHERE a.meeting_id = m.id AND a.search_text LIKE ? ESCAPE '\\')
 OR EXISTS (SELECT 1 FROM transcript_segments ts
             WHERE ts.meeting_id = m.id AND ts.text_norm LIKE ? ESCAPE '\\')
)"""


class MeetingSearch:
    def __init__(self, database: Database, clock: Optional[Clock] = None):
        self.db = database
        self.clock = clock or SystemClock(database.config.timezone)
        self.meetings = MeetingRepository(database, self.clock)

    def search(
        self, query: Optional[str] = None, filters: Optional[MeetingFilters] = None
    ) -> List[Meeting]:
        active_filters = filters or MeetingFilters()
        conditions = self._conditions(query, active_filters)

        sql = (
            f"SELECT {_COLUMNS} FROM meetings m"
            + conditions.where()
            + active_filters.order_by()
            + " LIMIT ?"
        )
        params = list(conditions.params) + [clamp_limit(active_filters.limit)]
        rows = self.db.query_all(sql, params)

        participants = self.meetings.participant_ids_for_many([row["id"] for row in rows])
        return [row_to_meeting(row, participants.get(row["id"], ())) for row in rows]

    def count(
        self, query: Optional[str] = None, filters: Optional[MeetingFilters] = None
    ) -> int:
        conditions = self._conditions(query, filters or MeetingFilters())
        sql = "SELECT COUNT(*) FROM meetings m" + conditions.where()
        return int(self.db.query_value(sql, list(conditions.params), default=0))

    def _conditions(self, query: Optional[str], filters: MeetingFilters) -> Conditions:
        conditions = Conditions()
        if query and normalize_search_text(query):
            pattern = like_pattern(query)
            conditions.add(_MATCH, pattern, pattern, pattern, pattern)
        filters.build(self.clock, conditions)
        return conditions
