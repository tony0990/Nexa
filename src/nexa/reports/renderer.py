"""Jinja2 rendering of the HTML and plain-text email bodies.

Templates live in `resources/email_templates/<ar|en>/` (Section 24.2) so the
wording can be corrected without a code change.

Two rules this module enforces:

* **Autoescape is on for HTML and off for text.** Task text and meeting titles
  come from transcribed speech and admin typing. A task containing `<b>` or `&`
  must appear literally in the HTML body, not as markup.
* **Templates receive only presentation objects.** `MeetingReportContext` and
  `ReminderContext` are already formatted for one language, so a template makes
  no formatting or language decision and cannot reach a domain object.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Optional

from ..contracts.meetings import EmailLanguage
from .models import ReminderContext, MeetingReportContext, resolve_language

MEETING_REPORT = "meeting_report"
REMINDER = "reminder"


def default_templates_dir() -> Path:
    """`resources/email_templates/` as laid out in Section 18.

    Resolved from this file's location so it works from a source checkout. A
    PyInstaller build sets `templates_dir` explicitly instead, because the
    bundle unpacks resources beside the executable rather than beside the
    package.
    """
    return Path(__file__).resolve().parents[3] / "resources" / "email_templates"


class TemplateNotFoundError(Exception):
    """A language/template pair has no file on disk."""


class ReportRenderer:
    """Renders a context into an HTML body and a plain-text body."""

    def __init__(self, templates_dir: Optional[Path] = None):
        self.templates_dir = Path(templates_dir or default_templates_dir())
        self._html_env = None
        self._text_env = None

    # Jinja2 is imported lazily so that importing `nexa.reports` on a machine
    # without the dependency installed still works — the data layer and the
    # tests that only exercise the formatter do not need it.
    def _envs(self):
        if self._html_env is None:
            from jinja2 import Environment, FileSystemLoader, StrictUndefined

            loader = FileSystemLoader(str(self.templates_dir), encoding="utf-8")
            self._html_env = Environment(
                loader=loader,
                autoescape=True,
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            # Plain text must not be HTML-escaped: an apostrophe in a task
            # would otherwise reach the recipient as `&#39;`.
            self._text_env = Environment(
                loader=loader,
                autoescape=False,
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
                keep_trailing_newline=True,
            )
        return self._html_env, self._text_env

    def template_path(self, language: str, name: str, suffix: str) -> Path:
        return self.templates_dir / resolve_language(language).lower() / f"{name}.{suffix}.j2"

    def render(
        self,
        context,
        name: str = MEETING_REPORT,
        language: Optional[str] = None,
    ) -> tuple:
        """Return `(html_body, text_body)` for one context.

        `StrictUndefined` makes a template that references a field the context
        does not have fail loudly at render time rather than mailing a blank
        section to the whole company.
        """
        language = resolve_language(language or getattr(context, "language", None))
        html_env, text_env = self._envs()
        variables = _as_variables(context)
        folder = language.lower()
        try:
            html = html_env.get_template(f"{folder}/{name}.html.j2").render(**variables)
            text = text_env.get_template(f"{folder}/{name}.txt.j2").render(**variables)
        except Exception as exc:  # jinja2.TemplateNotFound and friends
            from jinja2 import TemplateNotFound

            if isinstance(exc, TemplateNotFound):
                raise TemplateNotFoundError(
                    f"No {name} template for language {language} "
                    f"under {self.templates_dir}"
                ) from exc
            raise
        return html.strip() + "\n", _normalize_text(text)

    def render_report(
        self, context: MeetingReportContext, language: Optional[str] = None
    ) -> tuple:
        return self.render(context, MEETING_REPORT, language)

    def render_reminder(
        self, context: ReminderContext, language: Optional[str] = None
    ) -> tuple:
        return self.render(context, REMINDER, language)

    def available_languages(self) -> tuple:
        """Languages that actually have a template directory on disk."""
        return tuple(
            language.value
            for language in EmailLanguage
            if (self.templates_dir / language.value.lower()).is_dir()
        )


def _as_variables(context) -> dict:
    """Flatten a context dataclass into template variables.

    `asdict` is recursive, so `rows` arrives as a list of plain dicts and a
    template cannot accidentally call a method on a domain object.
    """
    if is_dataclass(context) and not isinstance(context, type):
        return asdict(context)
    if isinstance(context, dict):
        return dict(context)
    raise TypeError(f"Cannot render {type(context).__name__} as a template context")


def _normalize_text(value: str) -> str:
    """Collapse the blank-line noise that Jinja whitespace control leaves.

    A plain-text email with four consecutive blank lines looks broken, and a
    template cannot avoid them without unreadable `{%-` soup.
    """
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").split("\n")]
    out: list = []
    for line in lines:
        if not line and out and not out[-1]:
            continue
        out.append(line)
    return "\n".join(out).strip() + "\n"
