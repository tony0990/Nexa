"""The real service container: Member 6's UI wired to Members 1-5.

`FakeServiceContainer` (Member 6, Section 26.6) let the whole UI be built before
any backend existed. `RealServiceContainer` is its drop-in replacement: it exposes
the same attributes and the same method names, and does the real work behind them

    audio          Member 2   Recorder over WASAPI (microphone / loopback / both)
    transcription  Member 2   faster-whisper on the GPU, CPU as a fallback
    extraction     Member 3   rule-based extractor + deterministic dates + times
    people         Member 1   employees, roles
    search         Member 1   employee / meeting / task search
    reminders      Members 1+5  actions, the reminder queue, snooze, completion
    email          Member 4   report rendering, Gmail or the local outbox
    audit          Member 1   the append-only trail

The UI speaks display strings and the domain speaks contracts, so every method
here is a thin translation — the translations themselves live in `convert.py`
where they can be tested without a window or a database.

Everything that touches hardware or the network is injectable (`capture_factory`,
`transcription_engine`, `sender`), which is how the whole container runs in tests.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from nexa.asr.service import TranscriptionServiceImpl
from nexa.asr.transcript import merge_transcripts
from nexa.audio.recorder import Recorder, default_capture_factory
from nexa.audio.wav_utils import wav_duration_ms
from nexa.audit import event_types
from nexa.audit.service import Actor, AuditService
from nexa.contracts.audio import RecordedAudio as ContractRecordedAudio
from nexa.contracts.audio import SourceConfig
from nexa.contracts.email import DeliveryStatus, EmailDelivery
from nexa.contracts.meetings import (
    ActionItem as ContractAction,
    ActionStatus,
    AudioSource,
    Meeting as ContractMeeting,
    MeetingStatus,
    ReviewState,
    TranscriptSegment,
)
from nexa.contracts.people import Employee as ContractEmployee
from nexa.contracts.transcription import Transcript as ContractTranscript
from nexa.core.clock import Clock, SystemClock
from nexa.core.config import NexaConfig
from nexa.core.paths import best_whisper_model, data_dir as default_data_dir, whisper_model_path
from nexa.core.timezone import DEFAULT_TIMEZONE, day_bounds_utc, to_local
from nexa.core.validation import normalize_search_text
from nexa.data.database import Database, open_database
from nexa.data.repositories.actions import ActionRepository
from nexa.data.repositories.deliveries import DeliveryRepository
from nexa.data.repositories.employees import EmployeeRepository
from nexa.data.repositories.meetings import MeetingRepository
from nexa.data.repositories.roles import RoleRepository
from nexa.email import (
    EmailService,
    GmailConnectionService,
    OutboxSender,
)
from nexa.email.errors import EmailError
from nexa.intelligence.rule_runtime import RuleBasedRuntime
from nexa.intelligence.service import ExtractionService as DomainExtractionService
from nexa.people.service import PeopleService as DomainPeopleService
from nexa.reports.service import ReportService
from nexa.scheduling.calculator import to_db
from nexa.scheduling.completion import CompletionService
from nexa.scheduling.queue import SqliteReminderQueue, connect
from nexa.scheduling.rules import ReminderPolicy
from nexa.scheduling.service import ReminderService as DomainReminderService
from nexa.scheduling.states import ReminderStatus
from nexa.search.filters import EmployeeFilters, MeetingFilters, TaskFilters
from nexa.search.service import SearchService as DomainSearchService
from nexa.services import convert
from nexa.services.live import LiveTranscriber
from nexa.services.models import (
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
from nexa.dedup.similarity import lexical_similarity

log = logging.getLogger("nexa.services")

#: Seconds of audio per rolling chunk. Short enough that the live transcript box
#: fills within a few seconds of speech; long enough for Whisper to have context.
LIVE_CHUNK_SECONDS = 20.0

_UNASSIGNED_LABELS = {"unassigned", "غير معيّن", "غير معين", ""}


# =============================================================================
# audio
# =============================================================================
class RealAudioService:
    """`AudioRecordingService` over Member 2's `Recorder`."""

    def __init__(self, recorder: Recorder, container: "RealServiceContainer") -> None:
        self.recorder = recorder
        self._container = container
        self.paused = False
        self.source = "mic+computer"
        self.started_at: Optional[datetime] = None
        self.last_recording: Optional[ContractRecordedAudio] = None

    @property
    def running(self) -> bool:
        return self.recorder.is_recording

    @property
    def workdir(self) -> Optional[Path]:
        return self.recorder.workdir

    @property
    def warnings(self) -> List[str]:
        return list(self.recorder.warnings)

    def start(self, source: str) -> str:
        self.source = source
        config = SourceConfig(AudioSource(convert.to_db_source(source)))
        recording_id = self.recorder.start(config)
        self.paused = False
        self.started_at = datetime.now(timezone.utc)
        self._container.session = _Session(started_at=self.started_at, source=convert.to_db_source(source))
        self._container.audit.log(
            event_types.RECORDING_STARTED, event_types.ENTITY_MEETING, None,
            metadata={"source": convert.to_db_source(source), "recording_id": recording_id},
        )
        return recording_id

    def pause(self) -> None:
        if self.running:
            self.recorder.pause()
            self.paused = True

    def resume(self) -> None:
        if self.running:
            self.recorder.resume()
            self.paused = False

    def stop(self) -> RecordedAudio:
        recorded = self.recorder.stop()
        self.paused = False
        self.last_recording = recorded
        ended = datetime.now(timezone.utc)
        session = self._container.session
        session.ended_at = ended
        session.recording = recorded
        self._container.audit.log(
            event_types.RECORDING_STOPPED, event_types.ENTITY_MEETING, None,
            metadata={"duration_ms": recorded.duration_ms, "chunks": len(recorded.chunk_paths)},
        )
        return RecordedAudio(
            path=recorded.path,
            duration_seconds=int(recorded.duration_ms / 1000),
            source=convert.to_ui_source(recorded.source),
        )


# =============================================================================
# transcription
# =============================================================================
class RealTranscriptionService:
    """`TranscriptionService` over faster-whisper, safe to call from two threads.

    The live preview and the final pass both need the model, and a CTranslate2
    model is not safe to run concurrently, so every call is serialized.
    """

    def __init__(
        self,
        engine_factory: Optional[Callable[[], object]] = None,
        language: Optional[str] = None,
    ) -> None:
        self._engine_factory = engine_factory
        self._language = language
        self._engine = None
        self._lock = threading.RLock()
        self.last_error: Optional[str] = None

    # ------------------------------------------------------------------ model
    @property
    def ready(self) -> bool:
        """True when a model exists to load (or an engine was injected)."""
        return self._engine_factory is not None or best_whisper_model() is not None

    @property
    def model_name(self) -> str:
        if self._engine_factory is not None and self._engine is not None:
            return getattr(self._engine, "name", "custom")
        found = best_whisper_model()
        return found[0] if found else "none"

    def _get_engine(self):
        if self._engine is None:
            if self._engine_factory is not None:
                self._engine = self._engine_factory()
            else:
                found = best_whisper_model()
                if found is None:
                    raise RuntimeError(
                        "No speech model is downloaded. Run:  python scripts/download_models.py --asr whisper-medium"
                    )
                from nexa.asr.faster_whisper_engine import FasterWhisperEngine

                self._engine = FasterWhisperEngine(str(found[1]), language=self._language)
        return self._engine

    def warm_up(self) -> None:
        """Load the model now so the first chunk is not slow. Safe to call twice."""
        with self._lock:
            engine = self._get_engine()
            load = getattr(engine, "load", None)
            if callable(load):
                load()

    # ------------------------------------------------------------------ calls
    def transcribe_path(self, path: str) -> ContractTranscript:
        # A chunk with no speech must not reach the model. Fed silence or room
        # noise, Whisper invents fluent text — once an Arabic sentence appended to
        # an English meeting — and a short tail chunk at the end of every recording
        # is exactly that. The energy check is cheap and the model call is not.
        if not _chunk_has_speech(path):
            return ContractTranscript(segments=(), duration_ms=wav_duration_ms(path))
        with self._lock:
            return TranscriptionServiceImpl(self._get_engine()).transcribe(path)

    def transcribe(self, audio_path: str) -> Transcript:
        """The UI-facing call: one file in, the display transcript out."""
        return self.to_dto(self.transcribe_path(audio_path))

    def transcribe_recording(
        self,
        recorded: ContractRecordedAudio,
        reuse: Optional[Dict[str, ContractTranscript]] = None,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> ContractTranscript:
        """Transcribe every chunk, reusing any the live preview already did."""
        reuse = reuse or {}
        paths = list(recorded.chunk_paths) or [recorded.path]
        parts, offset_ms = [], 0
        for index, path in enumerate(paths, start=1):
            transcript = reuse.get(str(path)) or self.transcribe_path(str(path))
            parts.append((offset_ms, transcript))
            offset_ms += wav_duration_ms(path)
            if progress:
                progress(index, len(paths))
        return merge_transcripts(parts)

    @staticmethod
    def to_dto(transcript: ContractTranscript) -> Transcript:
        text = transcript.full_text
        return Transcript(
            raw_text=text,
            confirmed_text=text,
            segments=[
                {"start_ms": s.start_ms, "end_ms": s.end_ms, "text": (s.confirmed_text or s.raw_text)}
                for s in transcript.segments
            ],
        )


# =============================================================================
# extraction
# =============================================================================
class RealExtractionService:
    """Transcript -> reviewable candidates, with owners matched to real employees."""

    def __init__(self, people: "RealPeopleService", container: "RealServiceContainer") -> None:
        self._people = people
        self._container = container
        self.runtime = RuleBasedRuntime()
        self.runtime.start()
        self._service = DomainExtractionService(runtime=self.runtime, detect_duplicates=False)

    def extract(self, transcript: Transcript, reference_datetime=None) -> List[ActionCandidate]:
        employees = self._people.active_contracts()
        self.runtime.set_known_names([e.full_name for e in employees])
        reference = reference_datetime or datetime.now(timezone.utc).astimezone(
            _tz(self._container.config.timezone)
        )
        contract = _contract_transcript(transcript)
        out: List[ActionCandidate] = []
        for extraction in self._service.extract_detailed(contract, reference):
            for candidate in extraction.candidates:
                mapped = DomainExtractionService.to_contract(candidate, extraction.segment)
                owner_id, ambiguous = _match_owner(candidate.owner_text, employees)
                out.append(
                    ActionCandidate(
                        id=len(out) + 1,
                        task=candidate.task,
                        owner_raw_text=candidate.owner_text or convert.UNASSIGNED,
                        owner_employee_id=owner_id,
                        raw_date_phrase=candidate.raw_date_phrase or "",
                        due_display=convert.fmt_due(mapped.resolved_date, mapped.resolved_time),
                        source_text=candidate.evidence_text,
                        confidence=float(candidate.confidence or 0.0),
                        due_iso=mapped.resolved_date.isoformat() if mapped.resolved_date else "",
                        due_time=mapped.resolved_time.strftime("%H:%M") if mapped.resolved_time else "",
                        needs_review=bool(candidate.needs_review or ambiguous or not mapped.resolved_date),
                        review_reason=("ambiguous_owner" if ambiguous else (candidate.review_reason or "")),
                        original_due_display=convert.fmt_due(mapped.resolved_date, mapped.resolved_time),
                    )
                )
        _flag_duplicates(out)
        self._container.session.transcript = contract
        self._container.audit.log(
            event_types.EXTRACTION_COMPLETED, event_types.ENTITY_MEETING, None,
            metadata={"candidates": len(out)},
            actor=Actor.system(),
        )
        return out


def _chunk_has_speech(path: str) -> bool:
    """True unless the chunk is silent or too short to hold a word.

    Fails *open*: if the file cannot be analysed, transcribe it. Skipping audio
    that might hold speech is worse than occasionally transcribing noise.
    """
    try:
        import numpy as np

        from nexa.audio.vad import has_speech
        from nexa.audio.wav_utils import read_wav

        samples, rate = read_wav(path)
        if len(samples) < rate * 0.4:
            return False
        return bool(has_speech(np.asarray(samples), rate))
    except Exception:  # noqa: BLE001
        log.exception("speech check failed for %s; transcribing anyway", path)
        return True


def _contract_transcript(transcript: Transcript) -> ContractTranscript:
    """Rebuild a contract transcript from the display one.

    If the admin edited `confirmed_text` the segments no longer match it, so each
    line of the confirmed text becomes a segment instead. Extraction must read what
    a human approved (§2.1), never the stale original.
    """
    segments = list(transcript.segments or [])
    if segments and "".join(s["text"] for s in segments).split() == (transcript.confirmed_text or "").split():
        built = tuple(
            TranscriptSegment(
                segment_index=i, start_ms=int(s.get("start_ms", 0)), end_ms=int(s.get("end_ms", 0)),
                raw_text=s["text"],
            )
            for i, s in enumerate(segments)
        )
    else:
        lines = [ln for ln in (transcript.confirmed_text or "").splitlines() if ln.strip()]
        built = tuple(TranscriptSegment(segment_index=i, raw_text=ln) for i, ln in enumerate(lines))
    return ContractTranscript(segments=built)


def _match_owner(spoken: Optional[str], employees: Sequence[ContractEmployee]):
    """`(employee_id | None, ambiguous)` for a spoken name.

    Exactly one match is taken. Several matches (two employees called أحمد) are NOT
    resolved by guessing — the id stays empty and the item is flagged, because
    mailing one person another's task is worse than asking (§2.1).
    """
    key = normalize_search_text(spoken or "")
    if not key or key in _UNASSIGNED_LABELS:
        return None, False
    full = [e for e in employees if normalize_search_text(e.full_name) == key]
    if len(full) == 1:
        return full[0].id, False
    first = [e for e in employees if key in normalize_search_text(e.full_name).split()]
    if len(first) == 1:
        return first[0].id, False
    return None, len(first) > 1


def _flag_duplicates(items: List[ActionCandidate]) -> None:
    """Mark near-duplicates for the review screen's Keep Both / Merge choice.

    Lexical, not semantic: the shipped `EmbeddingModel` is a hash-seeded random
    vector, so its "similarity" is noise. Two tasks are flagged only when their
    wording overlaps strongly AND they share a deadline day (or one has none) AND
    they do not name different owners. Flagged, never merged (§7).
    """
    for index, item in enumerate(items):
        for earlier in items[:index]:
            if lexical_similarity(item.task, earlier.task) < 0.6:
                continue
            if item.due_iso and earlier.due_iso and item.due_iso != earlier.due_iso:
                continue
            if (
                item.owner_employee_id and earlier.owner_employee_id
                and item.owner_employee_id != earlier.owner_employee_id
            ):
                continue
            item.possible_duplicate_of = earlier.id
            break


# =============================================================================
# people / search / audit
# =============================================================================
class RealPeopleService:
    def __init__(self, db: Database, clock: Clock, audit: AuditService, actor: Actor) -> None:
        self.domain = DomainPeopleService(db, clock, audit, actor=actor)
        self._employees = EmployeeRepository(db, clock)
        self._roles = RoleRepository(db, clock)

    # --- conversion
    def _role_names(self, employee_id: int) -> List[str]:
        return [r.name for r in self._roles.roles_for_employee(employee_id)]

    def _dto(self, e: ContractEmployee) -> Employee:
        return Employee(
            id=e.id, full_name=e.full_name, email=e.email, department=e.department or "",
            job_title=e.job_title or "", roles=self._role_names(e.id), active=e.active,
        )

    def active_contracts(self) -> List[ContractEmployee]:
        return self._employees.list_active()

    def _role_ids(self, names: Sequence[str]) -> List[int]:
        by_name = {normalize_search_text(r.name): r.id for r in self._roles.list_all()}
        return [by_name[normalize_search_text(n)] for n in names if normalize_search_text(n) in by_name]

    # --- employees
    def list_employees(self, query: str = "", active: str = "all") -> List[Employee]:
        flag = {"active": True, "inactive": False}.get(active)
        if query and query.strip():
            rows = DomainSearchService(self.domain.db).search_employees(query, EmployeeFilters(active=flag))
        else:
            rows = self.domain.list_employees(active_only=False)
            if flag is not None:
                rows = [e for e in rows if e.active == flag]
        return [self._dto(e) for e in rows]

    def create_employee(self, **kwargs) -> Employee:
        created = self.domain.create_employee(
            kwargs["full_name"], kwargs["email"],
            department=kwargs.get("department") or None,
            job_title=kwargs.get("job_title") or None,
            role_ids=self._role_ids(kwargs.get("roles", [])),
        )
        return self._dto(created)

    def update_employee(self, employee_id: int, **kwargs) -> Employee:
        roles = kwargs.pop("roles", None)
        changes = {k: (v or None) if k in ("department", "job_title") else v for k, v in kwargs.items()
                   if k in ("full_name", "email", "department", "job_title", "active")}
        employee = self.domain.update_employee(employee_id, **changes)
        if roles is not None:
            self.domain.set_roles(employee_id, self._role_ids(roles))
        return self._dto(self.domain.get_employee(employee_id) if roles is not None else employee)

    def deactivate_employee(self, employee_id: int) -> None:
        self.domain.deactivate_employee(employee_id)

    # --- roles
    def list_roles(self) -> List[Role]:
        return [Role(r.id, r.name, r.description or "", r.active) for r in self.domain.list_roles()]

    def create_role(self, name: str, description: str = "") -> Role:
        r = self.domain.create_role(name, description=description or None)
        return Role(r.id, r.name, r.description or "", r.active)

    def update_role(self, role_id: int, **kwargs) -> Role:
        r = self.domain.update_role(role_id, **kwargs)
        return Role(r.id, r.name, r.description or "", r.active)

    def deactivate_role(self, role_id: int) -> None:
        self.domain.update_role(role_id, active=False)

    # --- helpers used by the email/reminder adapters
    def by_name(self, names: Sequence[str]) -> List[ContractEmployee]:
        """Employees for display names, in order, skipping names with no match."""
        employees = self.active_contracts()
        out: List[ContractEmployee] = []
        for name in names:
            employee_id, _ = _match_owner(name, employees)
            if employee_id is not None:
                found = next((e for e in employees if e.id == employee_id), None)
                if found and found not in out:
                    out.append(found)
        return out


class RealSearchService:
    def __init__(self, db: Database, clock: Clock, people: RealPeopleService, reminders: "RealReminderService"):
        self._search = DomainSearchService(db, clock)
        self._people = people
        self._reminders = reminders
        self._meetings = MeetingRepository(db, clock)
        self._employees = EmployeeRepository(db, clock)

    def search_employees(self, query: str, filters: Optional[dict] = None) -> List[Employee]:
        return self._people.list_employees(query, (filters or {}).get("active", "all"))

    def search_meetings(self, query: str, filters: Optional[dict] = None) -> List[Meeting]:
        status = (filters or {}).get("status")
        domain = MeetingFilters(statuses=(status.upper(),) if status and status != "all" else ())
        return [self._meeting_dto(m) for m in self._search.search_meetings(query, domain)]

    def search_tasks(self, query: str, filters: Optional[dict] = None) -> List[ActionItem]:
        return self._reminders.list_actions(filters, query=query)

    def global_search(self, query: str) -> dict:
        return {
            "employees": self.search_employees(query),
            "meetings": self.search_meetings(query),
            "tasks": self.search_tasks(query),
        }

    def _meeting_dto(self, m: ContractMeeting) -> Meeting:
        names = [e.full_name for e in self._employees.get_many(list(m.participant_ids))] if m.participant_ids else []
        return Meeting(
            id=m.id, title=m.title, template_name="", audio_source=convert.to_ui_source(m.audio_source),
            participants=names, status=m.status, started_at=m.started_at, ended_at=m.ended_at,
            email_language=convert.to_ui_language(m.email_language),
        )


class RealAuditService:
    """The UI's audit screen reads `history`/`record`; the adapters write via `log`.

    One object serves both: the display-shaped methods are defined here, and every
    other attribute (`log`, `recent`, `to_view_model`, ...) is the domain service's.
    """

    def __init__(self, domain: AuditService) -> None:
        self.domain = domain

    def __getattr__(self, name: str):
        return getattr(self.domain, name)

    def history(self, entity_type: Optional[str] = None) -> List[AuditEvent]:
        entries = self.domain.to_view_model(self.domain.recent(500))
        out = [
            AuditEvent(e.local_time, e.event_type, e.entity_type, e.entity_id or "", e.actor, e.summary)
            for e in entries
        ]
        if entity_type and entity_type != "all":
            out = [e for e in out if e.entity_type == entity_type]
        return out

    def record(self, event: AuditEvent) -> None:
        self.domain.log(event.event_type, event.entity_type, event.entity_id or None,
                        metadata={"detail": event.detail, "actor": event.actor})


# =============================================================================
# reminders
# =============================================================================
@dataclass
class _Session:
    """What the container remembers between "recording started" and "approved"."""

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    source: str = "BOTH"
    recording: Optional[ContractRecordedAudio] = None
    transcript: Optional[ContractTranscript] = None
    meeting_id: Optional[int] = None
    title: str = ""
    participants: List[str] = field(default_factory=list)


class RealReminderService:
    def __init__(self, container: "RealServiceContainer") -> None:
        self.c = container

    # ---------------------------------------------------------------- listing
    def list_actions(self, filters: Optional[dict] = None, query: str = "") -> List[ActionItem]:
        filters = filters or {}
        status = filters.get("status")
        owner = (filters.get("owner") or "").strip()
        domain = TaskFilters()
        kwargs = {}
        if status == "unassigned" or owner.lower() == "unassigned":
            kwargs["unassigned"] = True
        elif status == "SNOOZED":
            kwargs["snoozed"] = True
        elif status and status != "all":
            kwargs["statuses"] = (status.upper(),)
        elif owner:
            ids = [e.id for e in self.c.people.active_contracts()
                   if normalize_search_text(owner) in normalize_search_text(e.full_name)]
            if not ids:
                return []
            kwargs["owner_ids"] = ids
        if kwargs:
            domain = TaskFilters(**kwargs)
        self.c.actions.mark_overdue()
        rows = self.c.search_domain.search_task_rows(query or None, domain)
        return [self._dto(row.action, row.owner_name, row.meeting_title) for row in rows]

    def _dto(self, a: ContractAction, owner_name: Optional[str], meeting_title: Optional[str]) -> ActionItem:
        tz = self.c.config.timezone
        return ActionItem(
            id=a.id, meeting_id=a.meeting_id or 0, task=a.task,
            owner_name=owner_name or a.owner_raw_text or convert.UNASSIGNED,
            due_display=convert.due_for_listing(a.due_date, a.due_time, a.due_at),
            reminder_display=self._next_reminder(a.id),
            status=a.status, source_text=a.source_text or "", meeting_title=meeting_title or "",
            due_iso=convert.iso_day(a.due_date, a.due_at, tz),
        )

    def _next_reminder(self, action_id: int) -> str:
        pending = self.c.queue.list_for_action(
            action_id, [ReminderStatus.PENDING, ReminderStatus.RETRY_WAIT, ReminderStatus.SNOOZED]
        )
        if not pending:
            return "—"
        soonest = min(pending, key=lambda r: r.scheduled_at)
        return convert.fmt_local(soonest.scheduled_at, self.c.config.timezone)

    # ----------------------------------------------------------------- change
    def mark_complete(self, action_id: int, actor: str = "Admin") -> None:
        CompletionService(self.c.queue, self.c.audit).mark_complete(action_id, actor)

    def snooze(self, action_id: int, new_time: str) -> None:
        """Move the *reminder*, never the deadline. `action_id` may also be a reminder id."""
        when = convert.parse_when(new_time)
        if when is None:
            raise ValueError("invalid_datetime")
        reminders = self.c.queue.list_for_action(action_id, [ReminderStatus.PENDING, ReminderStatus.RETRY_WAIT])
        target = min(reminders, key=lambda r: r.scheduled_at) if reminders else self.c.queue.get(action_id)
        if target is None:
            raise ValueError("no_reminder")
        self.c.reminder_domain.snooze(target.id, convert.to_aware_utc(when, self.c.config.timezone))

    def reschedule_action(self, action_id: int, new_due_at: str) -> None:
        when = convert.parse_when(new_due_at)
        if when is None:
            raise ValueError("invalid_datetime")
        self.c.reminder_domain.reschedule_action(
            action_id, convert.to_aware_utc(when, self.c.config.timezone), time_specified=True
        )

    def send_test_reminder(self, action_id: int) -> SendResult:
        action = self.c.actions.get(action_id)
        if action is None:
            return SendResult(False, error="Action not found")
        owner = self.c.employees.get(action.owner_employee_id) if action.owner_employee_id else None
        if owner is None:
            return SendResult(False, error="This action has no assigned owner to remind.")
        meeting = self.c.meetings.get(action.meeting_id) if action.meeting_id else None
        attempt = self.c.email.service().send_reminder(owner, action, meeting)
        return SendResult(attempt.ok, attempt.result.gmail_message_id or "", attempt.result.error_message or "")

    # --------------------------------------------------------------- approval
    def import_approved(
        self, meeting_title: str, items: Sequence[ActionCandidate], meeting_id: int = 0,
        participants: Optional[Sequence[str]] = None,
    ) -> None:
        """Persist the approved meeting, its actions and their reminders.

        Nothing reaches the database before this point (§2.1): extraction produces
        candidates, the admin reviews them, and only approval writes.
        """
        session = self.c.session
        tz = self.c.config.timezone
        now_local = datetime.now(timezone.utc).astimezone(_tz(tz))
        lang = convert.to_db_language(self.c.settings_language)
        names = list(participants or session.participants or [])
        employees = self.c.people.by_name(names)

        meeting = self.c.meetings.create(ContractMeeting(
            title=meeting_title or "Untitled meeting",
            started_at=session.started_at, ended_at=session.ended_at,
            audio_source=session.source if session.source in ("MICROPHONE", "COMPUTER", "BOTH") else "BOTH",
            status=MeetingStatus.APPROVED.value, email_language=lang,
            participant_ids=tuple(e.id for e in employees),
        ))
        session.meeting_id, session.title, session.participants = meeting.id, meeting.title, names
        if session.transcript is not None and session.transcript.segments:
            self.c.meetings.add_segments(meeting.id, session.transcript.segments)
        self.c.audit.log(event_types.MEETING_CREATED, event_types.ENTITY_MEETING, meeting.id,
                         new_value={"title": meeting.title, "participants": len(employees)})

        created = 0
        for item in items:
            day, at = self._due_of(item, now_local)
            action = self.c.actions.create(ContractAction(
                meeting_id=meeting.id,
                task=(item.task or "").strip() or "Untitled action",
                owner_employee_id=item.owner_employee_id,
                owner_raw_text=(item.owner_raw_text if (item.owner_raw_text or "").strip().lower()
                                not in _UNASSIGNED_LABELS else None),
                raw_date_phrase=item.raw_date_phrase or None,
                due_date=day, due_time=at, due_at=convert.due_instant(day, at, tz),
                source_text=item.source_text or None,
                confidence=item.confidence,
                review_state=ReviewState.APPROVED.value, status=ActionStatus.PENDING.value,
            ))
            self.c.audit.log(event_types.ACTION_CREATED, event_types.ENTITY_ACTION_ITEM, action.id,
                             new_value={"task": action.task, "due_date": str(day) if day else None})
            if day is not None:
                self.c.reminder_domain.schedule_for_action(action)
            created += 1
        self.c.audit.log(event_types.MEETING_APPROVED, event_types.ENTITY_MEETING, meeting.id,
                         metadata={"actions": created})

    @staticmethod
    def _due_of(item: ActionCandidate, now_local: datetime):
        """The machine deadline, unless the admin retyped the displayed one."""
        from datetime import time as _time

        original = getattr(item, "original_due_display", "")
        if item.due_display == original and (item.due_iso or not item.due_display):
            day = datetime.strptime(item.due_iso, "%Y-%m-%d").date() if item.due_iso else None
            at = _time.fromisoformat(item.due_time) if item.due_time else None
            return day, at
        return convert.parse_due_text(item.due_display, now_local)

    # -------------------------------------------------------------- dashboard
    def dashboard_counts(self) -> dict:
        self.c.actions.mark_overdue()
        counts = self.c.search_domain.task_status_counts()
        start, end = day_bounds_utc(datetime.now(timezone.utc).astimezone(_tz(self.c.config.timezone)).date(),
                                    self.c.config.timezone)
        today = self.c.db.query_value(
            "SELECT COUNT(*) FROM reminders WHERE status IN ('PENDING','RETRY_WAIT','SNOOZED') "
            "AND scheduled_at >= ? AND scheduled_at < ?", (to_db(start), to_db(end)), default=0,
        )
        pending_review = self.c.search_domain.count_tasks(
            None, TaskFilters(review_states=(ReviewState.NEEDS_REVIEW.value,))
        )
        return {
            "upcoming": counts.get("PENDING", 0),
            "reminders_today": int(today),
            "pending_review": pending_review,
            "overdue": counts.get("OVERDUE", 0),
            "email_failures": self.c.deliveries.count(status=DeliveryStatus.FAILED.value),
            "completed": counts.get("COMPLETED", 0),
        }


# =============================================================================
# email
# =============================================================================
class RealEmailService:
    """Reports and reminders through Member 4, delivered by Gmail or the outbox."""

    def __init__(self, container: "RealServiceContainer", sender=None) -> None:
        self.c = container
        self._injected = sender
        self.connection = GmailConnectionService()
        self.reports = ReportService(clock=container.clock, tz_name=container.config.timezone)
        self._pending = None
        self.last_error: Optional[str] = None

    # ------------------------------------------------------------ connection
    @property
    def sender(self):
        if self._injected is not None:
            return self._injected
        try:
            if self.connection.status().connected:
                return self.connection.sender()
        except EmailError as exc:
            self.last_error = str(exc)
        return OutboxSender(self.c.data_dir / "outbox")

    @property
    def mode(self) -> str:
        return "outbox" if getattr(self.sender, "is_outbox", False) else "gmail"

    @property
    def connected(self) -> bool:
        return self.mode == "gmail"

    def connect(self) -> None:
        status = self.connection.connect()
        self.last_error = None if status.connected else status.error

    def disconnect(self) -> None:
        self.connection.disconnect()

    def test(self) -> bool:
        return self.connection.test().connected

    def service(self) -> EmailService:
        return EmailService(
            sender=self.sender, reports=self.reports, clock=self.c.clock,
            tz_name=self.c.config.timezone, from_name=self.c.sender_name,
            delivery_sink=self._record,
        )

    # --------------------------------------------------------------- building
    def build_meeting_report(self, meeting, actions, recipients, language) -> RenderedEmail:
        lang = convert.to_db_language(language)
        employees = self.c.people.by_name(list(recipients))
        everyone = self.c.people.active_contracts()
        domain_meeting = ContractMeeting(
            id=self.c.session.meeting_id, title=str(meeting),
            started_at=self.c.session.started_at or datetime.now(timezone.utc), email_language=lang,
        )
        domain_actions = [self._to_action(a, everyone) for a in actions]
        rendered = self.reports.build_report_preview(
            domain_meeting, domain_actions, employees, lang, employees=everyone
        )
        self._pending = (domain_meeting, domain_actions, employees, lang)
        sender_email = getattr(self.sender, "from_email", "") or "nexa@localhost"
        return RenderedEmail(
            language=language, subject=rendered.subject, html=rendered.html_body, text=rendered.text_body,
            sender=f"{self.c.sender_name} <{sender_email}>", recipients=[e.email for e in employees],
        )

    @staticmethod
    def _to_action(item, employees: Sequence[ContractEmployee]) -> ContractAction:
        day, at = RealReminderService._due_of(item, datetime.now(timezone.utc)) \
            if hasattr(item, "due_iso") else (None, None)
        owner_id = getattr(item, "owner_employee_id", None)
        if owner_id is None and hasattr(item, "owner_name"):
            owner_id, _ = _match_owner(item.owner_name, employees)
        return ContractAction(
            id=getattr(item, "id", None), task=item.task, owner_employee_id=owner_id,
            owner_raw_text=getattr(item, "owner_raw_text", None) or getattr(item, "owner_name", None),
            due_date=day, due_time=at, source_text=getattr(item, "source_text", None),
            review_state=ReviewState.APPROVED.value,
        )

    def preview(self, rendered_email: RenderedEmail) -> EmailPreview:
        return EmailPreview(rendered_email)

    # ----------------------------------------------------------------- sending
    def send(self, message: RenderedEmail) -> SendResult:
        """Send the report to every recipient, each greeted by their own name.

        The preview body is addressed to the first recipient, so re-sending that
        single body to everyone would greet all of them with one person's name. The
        report is rendered again per recipient from the context `build_meeting_report`
        saved.
        """
        if self._pending is None:
            return SendResult(False, error="Nothing has been previewed yet.")
        meeting, actions, employees, lang = self._pending
        if not employees:
            return SendResult(False, error="No valid recipients: none of the names match an employee.")
        summary = self.service().send_meeting_report(meeting, actions, employees, lang)
        self.c.audit.log(event_types.REPORT_SENT, event_types.ENTITY_MEETING, meeting.id,
                         metadata={"sent": len(summary.sent), "failed": len(summary.failed),
                                   "mode": self.mode})
        if summary.all_ok:
            return SendResult(True, (summary.gmail_message_ids or [""])[0])
        errors = "; ".join(a.result.error_message or "send failed" for a in summary.failed)
        return SendResult(bool(summary.sent), (summary.gmail_message_ids or [""])[0], errors)

    def _record(self, attempt) -> None:
        """Persist every attempt (Member 4 returns it, Member 1 stores it)."""
        try:
            ok = attempt.ok
            self.c.deliveries.record_attempt(EmailDelivery(
                meeting_id=attempt.meeting_id or self.c.session.meeting_id,
                action_item_id=attempt.action_item_id, reminder_id=attempt.reminder_id,
                recipient_employee_id=attempt.employee_id, recipient_email=attempt.recipient_email,
                subject=attempt.rendered.subject, language=attempt.rendered.language,
                status=DeliveryStatus.SENT.value if ok else DeliveryStatus.FAILED.value,
                gmail_message_id=attempt.result.gmail_message_id if ok else None,
                sent_at=datetime.now(timezone.utc) if ok else None,
                error_message=None if ok else attempt.result.error_message,
            ))
        except Exception:  # noqa: BLE001 - a log failure must never lose a sent email
            log.exception("could not record the delivery")

    @property
    def deliveries(self) -> List[dict]:
        tz = self.c.config.timezone
        out = []
        for d in self.c.deliveries.recent(200):
            out.append({
                "when": convert.fmt_local(d.sent_at or d.attempted_at, tz),
                "kind": "REMINDER" if d.reminder_id else "REPORT",
                "subject": d.subject, "to": d.recipient_email, "status": d.status,
                "language": convert.to_ui_language(d.language),
            })
        return out


# =============================================================================
# the meeting pipeline: record -> live text -> final transcript -> candidates
# =============================================================================
class RealMeetingPipeline:
    """One object the eye screen drives: start, pause, finish.

    It exists because the screen needs things no single service owns — the
    recorder (Member 2), the live transcriber, the final pass that reuses the
    live work, and extraction (Member 3) — in one ordered sequence.
    """

    def __init__(self, container: "RealServiceContainer") -> None:
        self.c = container
        self.live: Optional[LiveTranscriber] = None
        self._mixed = False

    # ---------------------------------------------------------------- state
    @property
    def running(self) -> bool:
        return self.c.audio.running

    @property
    def paused(self) -> bool:
        return self.c.audio.paused

    @property
    def warnings(self) -> List[str]:
        return self.c.audio.warnings

    def level(self) -> float:
        """Input level as 0..1 for the eye (maps -60 dB..-12 dB)."""
        if not self.running or self.paused:
            return 0.0
        return max(0.0, min(1.0, (self.c.recorder.level_db + 60.0) / 48.0))

    # --------------------------------------------------------------- control
    def start(self, source: str, on_text: Callable[[str, str], None],
              on_error: Optional[Callable[[str], None]] = None) -> None:
        """Begin recording and start the live transcript.

        `on_text(source, text)` is called from a background thread for each chunk
        as it closes; the window turns it into a Qt signal.
        """
        # Load the model now, on this call, so a missing model fails *before* the
        # meeting starts rather than after it has been recorded.
        self.c.transcription.warm_up()
        self._mixed = convert.to_db_source(source) == "BOTH"
        self.c.audio.start(source)
        self.live = LiveTranscriber(
            transcribe=self.c.transcription.transcribe_path,
            workdir=lambda: self.c.audio.workdir,
            on_text=lambda src, path, text: on_text(src, text),
            on_error=on_error,
        )
        self.live.start()

    def pause(self) -> None:
        self.c.audio.pause()

    def resume(self) -> None:
        self.c.audio.resume()

    def finish(self, progress: Optional[Callable[[int, int], None]] = None):
        """Stop, finish the transcript and extract actions: `(Transcript, candidates)`.

        Heavy: call from a worker thread. For a single source the chunks the live
        preview already transcribed are reused, so only the final partial chunk
        costs anything. For mic+computer the recorder mixes the two streams into
        *new* files, so those are transcribed fresh.
        """
        recorded = self.c.audio.stop()
        if self.live is not None:
            self.live.stop()
        reuse = {} if self._mixed else dict(self.live.results if self.live else {})
        contract = self.c.transcription.transcribe_recording(
            self.c.audio.last_recording, reuse=reuse, progress=progress
        )
        dto = self.c.transcription.to_dto(contract)
        candidates = self.c.extraction.extract(dto)
        return dto, candidates


# =============================================================================
# the container
# =============================================================================
class RealServiceContainer:
    """Drop-in replacement for `FakeServiceContainer`, backed by the real packages."""

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        *,
        capture_factory=None,
        transcription_engine: Optional[Callable[[], object]] = None,
        sender=None,
        clock: Optional[Clock] = None,
        asr_language: Optional[str] = None,
        sender_name: str = "Nexa",
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.config = NexaConfig(data_dir=self.data_dir)
        self.db = open_database(self.config)
        self.clock = clock or SystemClock(self.config.timezone)
        self.sender_name = sender_name
        self.settings_language = "ENGLISH"
        self.session = _Session()

        self.audit_domain = AuditService(self.db, self.clock, default_actor=Actor.user("admin"))
        self.audit = RealAuditService(self.audit_domain)

        self.employees = EmployeeRepository(self.db, self.clock)
        self.meetings = MeetingRepository(self.db, self.clock)
        self.actions = ActionRepository(self.db, self.clock)
        self.deliveries = DeliveryRepository(self.db, self.clock)
        self.roles = RoleRepository(self.db, self.clock)
        self.search_domain = DomainSearchService(self.db, self.clock)

        # Member 5's queue keeps its own WAL connection to the same file, because
        # it needs BEGIN IMMEDIATE transactions and NexaWorker.exe shares it.
        db_path = str(self.config.database_path)
        self.queue = SqliteReminderQueue(
            lambda: connect(db_path), ReminderPolicy.from_settings({}), audit=self.audit_domain,
            clock=lambda: datetime.now(timezone.utc),
        )
        self.reminder_domain = DomainReminderService(self.queue, audit=self.audit_domain)

        # Public attributes the UI reads (same names as FakeServiceContainer).
        self.people = RealPeopleService(self.db, self.clock, self.audit_domain, Actor.user("admin"))
        self.reminders = RealReminderService(self)
        self.search = RealSearchService(self.db, self.clock, self.people, self.reminders)
        self.email = RealEmailService(self, sender=sender)
        self.transcription = RealTranscriptionService(transcription_engine, language=asr_language)
        self.extraction = RealExtractionService(self.people, self)
        self.recorder = Recorder(
            self.data_dir / "recordings",
            capture_factory or default_capture_factory,
            chunk_seconds=LIVE_CHUNK_SECONDS,
        )
        self.audio = RealAudioService(self.recorder, self)
        self.pipeline = RealMeetingPipeline(self)
        self._seed_defaults()

    # ------------------------------------------------------------------- setup
    def _seed_defaults(self) -> None:
        """A first-run database with no roles is awkward to use; add the common ones."""
        if self.roles.list_all():
            return
        for name, description in (
            ("Manager", "Team and project leadership"),
            ("Developer", "Engineering delivery"),
            ("HR", "People operations"),
            ("Finance", "Budget and reporting"),
        ):
            try:
                self.people.create_role(name, description)
            except Exception:  # noqa: BLE001 - never block start-up on seeding
                log.exception("could not seed role %s", name)

    # ----------------------------------------------------------------- status
    @property
    def worker_online(self) -> bool:
        from nexa.worker.health import WorkerState, check_worker_health

        try:
            health = check_worker_health(self.queue.factory, datetime.now(timezone.utc))
        except Exception:  # noqa: BLE001
            return False
        return health.state == WorkerState.HEALTHY

    @property
    def models(self) -> dict:
        return {"speech": self.transcription.ready, "llm": True}

    def close(self) -> None:
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass


def _tz(name: str):
    from nexa.core.timezone import get_timezone

    return get_timezone(name)
