"""Meeting template persistence (Section 8 / Section 30).

Templates are convenience defaults, not locked policy: they are read when a
meeting is created and never re-applied afterwards.
"""

from __future__ import annotations

from typing import List, Optional

from ...contracts.meetings import MeetingTemplate
from ...core.errors import ConflictError, NotFoundError
from ...core.validation import normalize_search_text
from ..models import json_to_db, row_to_template
from ..transactions import unit_of_work
from .base import BaseRepository, is_unique_violation

_COLUMNS = (
    "id, name, default_title, default_audio_source, default_email_language, "
    "default_report_target_config, default_reminder_target_config, "
    "default_reminder_rule_config, active, created_at, updated_at"
)


class TemplateRepository(BaseRepository):
    def create(self, template: MeetingTemplate) -> MeetingTemplate:
        now = self.now_str()
        with unit_of_work(self.db):
            try:
                self.db.execute(
                    """
                    INSERT INTO meeting_templates (
                        name, name_norm, default_title, default_audio_source,
                        default_email_language, default_report_target_config,
                        default_reminder_target_config, default_reminder_rule_config,
                        active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        template.name,
                        normalize_search_text(template.name),
                        template.default_title,
                        template.default_audio_source,
                        template.default_email_language,
                        json_to_db(template.default_report_target_config),
                        json_to_db(template.default_reminder_target_config),
                        json_to_db(template.default_reminder_rule_config),
                        1 if template.active else 0,
                        now,
                        now,
                    ),
                )
            except Exception as exc:
                if is_unique_violation(exc, "meeting_templates.name_norm"):
                    raise ConflictError(
                        f"a template named {template.name!r} already exists",
                        code="duplicate_template",
                    ) from exc
                raise
            template_id = self._last_insert_id()
        return self.get_or_raise(template_id)

    def update(self, template: MeetingTemplate) -> MeetingTemplate:
        if template.id is None:
            raise ValueError("template.id is required for update")
        with unit_of_work(self.db):
            cursor = self.db.execute(
                """
                UPDATE meeting_templates
                   SET name = ?, name_norm = ?, default_title = ?,
                       default_audio_source = ?, default_email_language = ?,
                       default_report_target_config = ?,
                       default_reminder_target_config = ?,
                       default_reminder_rule_config = ?, active = ?, updated_at = ?
                 WHERE id = ?
                """,
                (
                    template.name,
                    normalize_search_text(template.name),
                    template.default_title,
                    template.default_audio_source,
                    template.default_email_language,
                    json_to_db(template.default_report_target_config),
                    json_to_db(template.default_reminder_target_config),
                    json_to_db(template.default_reminder_rule_config),
                    1 if template.active else 0,
                    self.now_str(),
                    template.id,
                ),
            )
            if cursor.rowcount == 0:
                raise NotFoundError("meeting_template", template.id)
        return self.get_or_raise(template.id)

    def delete(self, template_id: int) -> None:
        with unit_of_work(self.db):
            cursor = self.db.execute(
                "DELETE FROM meeting_templates WHERE id = ?", (template_id,)
            )
            if cursor.rowcount == 0:
                raise NotFoundError("meeting_template", template_id)

    def get(self, template_id: int) -> Optional[MeetingTemplate]:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM meeting_templates WHERE id = ?", (template_id,)
        )
        return None if row is None else row_to_template(row)

    def get_or_raise(self, template_id: int) -> MeetingTemplate:
        template = self.get(template_id)
        if template is None:
            raise NotFoundError("meeting_template", template_id)
        return template

    def get_by_name(self, name: str) -> Optional[MeetingTemplate]:
        row = self.db.query_one(
            f"SELECT {_COLUMNS} FROM meeting_templates WHERE name_norm = ?",
            (normalize_search_text(name),),
        )
        return None if row is None else row_to_template(row)

    def list_all(self, *, active_only: bool = False) -> List[MeetingTemplate]:
        sql = f"SELECT {_COLUMNS} FROM meeting_templates"
        if active_only:
            sql += " WHERE active = 1"
        sql += " ORDER BY name_norm"
        return [row_to_template(row) for row in self.db.query_all(sql)]
