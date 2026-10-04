"""The meeting screen: an eye that opens when Nexa is listening.

    closed eye   idle — click to start
    open eye     recording — words appear in the transcript box as they are spoken
    half-closed  paused
    ringed eye   the model is finishing the transcript and extracting actions

The screen keeps Member 6's original fields (title, template, participants, audio
source) and the pause/resume controls; the eye is the primary control and the
transcript box is what the model hears.

Threading. Recording runs on Member 2's capture threads and the live transcript on a
background thread, so neither touches a widget: text arrives through the
`live_text` signal, which Qt delivers on the UI thread. The final transcription and
extraction (seconds to minutes) run in a `QThread` so the window stays responsive.
A pipeline that declares `threaded = False` (the fakes, and the tests) runs the same
steps inline, which keeps `_stop()` callable synchronously.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nexa.ui.eye.eye_widget import IDLE, PAUSED, PROCESSING, RECORDING, EyeWidget
from nexa.ui.meeting.viewmodel import MeetingViewModel
from nexa.ui.widgets.common import ghost_button, muted, page_title


class _VmPipeline:
    """Adapts Member 6's original view-model to the pipeline interface.

    Used when a container has no `pipeline` of its own, so the page has a single
    code path either way.
    """

    threaded = False
    warnings: list = []

    def __init__(self, vm: MeetingViewModel) -> None:
        self.vm = vm

    @property
    def running(self) -> bool:
        return self.vm.audio.running

    @property
    def paused(self) -> bool:
        return getattr(self.vm.audio, "paused", False)

    def level(self) -> float:
        return 0.0

    def start(self, source, on_text=None, on_error=None) -> None:
        self.vm.start(source)

    def pause(self) -> None:
        self.vm.pause()

    def resume(self) -> None:
        self.vm.resume()

    def finish(self, progress=None):
        return self.vm.stop()


class _FinishThread(QThread):
    """Runs `pipeline.finish()` off the UI thread."""

    progress = Signal(int, int)
    done = Signal(object, object)
    failed = Signal(str)

    def __init__(self, pipeline) -> None:
        super().__init__()
        self._pipeline = pipeline

    def run(self) -> None:
        try:
            transcript, candidates = self._pipeline.finish(progress=self.progress.emit)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.done.emit(transcript, candidates)


class MeetingPage(QWidget):
    SOURCE_KEYS = ["mic", "computer", "mic+computer"]

    #: Emitted from the live-transcription thread; delivered on the UI thread.
    live_text = Signal(str, str)
    live_error = Signal(str)

    def __init__(self, t, audio, transcription, extraction, on_finished, pipeline=None) -> None:
        super().__init__()
        self.t = t
        self.on_finished = on_finished
        self.vm = MeetingViewModel(audio, transcription, extraction)
        self.pipeline = pipeline or _VmPipeline(self.vm)
        self._finisher: _FinishThread | None = None
        self._processing = False
        self._last_transcript = None

        layout = QVBoxLayout(self)
        self.title = page_title("")
        layout.addWidget(self.title)

        # --- meeting details (Member 6's original fields, in a compact card)
        self.details = QFrame()
        self.details.setObjectName("Card")
        form = QFormLayout(self.details)
        self.name = QLineEdit("Weekly Development Meeting")
        self.template = QComboBox()
        self.template.addItems(list(MeetingViewModel.TEMPLATES))
        self.participants = QLineEdit("Ahmed Hassan, Maria Adel")
        self.source = QComboBox()
        self.name_label = QLabel()
        self.template_label = QLabel()
        self.participants_label = QLabel()
        self.source_label = QLabel()
        form.addRow(self.name_label, self.name)
        form.addRow(self.template_label, self.template)
        form.addRow(self.participants_label, self.participants)
        form.addRow(self.source_label, self.source)
        layout.addWidget(self.details)

        # --- the eye
        self.eye = EyeWidget()
        self.eye.clicked.connect(self._toggle)
        layout.addWidget(self.eye, 3)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setStyleSheet("font-size: 30px; font-weight: 700;")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.status = muted("")
        self.status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.timer_label)
        layout.addWidget(self.status)

        # --- controls
        row = QHBoxLayout()
        self.start_btn = QPushButton()
        self.pause_btn = ghost_button("")
        self.resume_btn = ghost_button("")
        self.stop_btn = QPushButton()
        for button in (self.start_btn, self.pause_btn, self.resume_btn, self.stop_btn):
            row.addWidget(button)
        layout.addLayout(row)

        # --- transcript box
        self.transcript_label = QLabel()
        self.transcript_label.setObjectName("PageTitle")
        self.transcript_label.setStyleSheet("font-size: 15px;")
        layout.addWidget(self.transcript_label)
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setMinimumHeight(150)
        layout.addWidget(self.transcript, 2)
        tools = QHBoxLayout()
        self.copy_btn = ghost_button("")
        self.save_btn = ghost_button("")
        tools.addStretch()
        tools.addWidget(self.copy_btn)
        tools.addWidget(self.save_btn)
        layout.addLayout(tools)

        # --- wiring
        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self.meter = QTimer(self)
        self.meter.setInterval(60)
        self.meter.timeout.connect(self._pump_level)
        self.live_text.connect(self._append_live)
        self.live_error.connect(self._show_live_error)
        self.start_btn.clicked.connect(self._start)
        self.pause_btn.clicked.connect(self._pause)
        self.resume_btn.clicked.connect(self._resume)
        self.stop_btn.clicked.connect(self._stop)
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn.clicked.connect(self._save)
        self.template.currentTextChanged.connect(self._apply_template)
        self.retranslate()

    # ------------------------------------------------------------------ helpers
    def _running(self) -> bool:
        return bool(self.pipeline.running)

    def _apply_template(self, name: str) -> None:
        defaults = self.vm.apply_template(name)
        if defaults["title"]:
            self.name.setText(defaults["title"])
        self.participants.setText(defaults["participants"])
        self.source.setCurrentIndex(self.SOURCE_KEYS.index(defaults["source"]))

    def _source_value(self) -> str:
        return self.SOURCE_KEYS[self.source.currentIndex()]

    def _sync_controls(self) -> None:
        """Enable only what makes sense right now, and keep the eye in step."""
        running = self._running()
        paused = running and bool(self.pipeline.paused)
        busy = self._processing
        self.start_btn.setEnabled(not running and not busy)
        self.pause_btn.setEnabled(running and not paused and not busy)
        self.resume_btn.setEnabled(paused and not busy)
        self.stop_btn.setEnabled(running and not busy)
        self.details.setEnabled(not running and not busy)
        if busy:
            state, hint = PROCESSING, "meeting.eye_hint_processing"
        elif paused:
            state, hint = PAUSED, "meeting.eye_hint_paused"
        elif running:
            state, hint = RECORDING, "meeting.eye_hint_recording"
        else:
            state, hint = IDLE, "meeting.eye_hint_idle"
        if self.eye.state != state:
            self.eye.set_state(state)
        self.status.setText(self.t(hint))

    # ------------------------------------------------------------------- timers
    def _tick(self) -> None:
        if self._running() and not self.pipeline.paused:
            self.vm.elapsed += 1
            s = self.vm.elapsed
            self.timer_label.setText(f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}")

    def _pump_level(self) -> None:
        self.eye.set_level(self.pipeline.level())

    # ------------------------------------------------------------------ actions
    def _toggle(self) -> None:
        """The eye is the main control: closed -> start, open -> stop."""
        if self._processing:
            return
        if self._running():
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        if self._running() or self._processing:
            return
        self.vm.elapsed = 0
        self.timer_label.setText("00:00:00")
        try:
            self.pipeline.start(self._source_value(), self.live_text.emit, self.live_error.emit)
        except Exception as exc:  # noqa: BLE001 - e.g. no microphone, model missing
            message = self.t("meeting.error_start").format(error=exc)
            self._sync_controls()
            self.status.setText(message)
            QMessageBox.warning(self, "Nexa", message)
            return
        self.transcript.clear()
        self.transcript.setPlaceholderText(self.t("meeting.listening_placeholder"))
        self.clock.start(1000)
        self.meter.start()
        self._sync_controls()

    def _pause(self) -> None:
        self.pipeline.pause()
        self._sync_controls()

    def _resume(self) -> None:
        self.pipeline.resume()
        self._sync_controls()

    def _stop(self) -> None:
        self.clock.stop()
        self.meter.stop()
        self.eye.set_level(0.0)
        self._processing = True
        self._sync_controls()
        if getattr(self.pipeline, "threaded", True):
            self._finisher = _FinishThread(self.pipeline)
            self._finisher.progress.connect(self._show_progress)
            self._finisher.done.connect(self._finished)
            self._finisher.failed.connect(self._failed)
            self._finisher.start()
            return
        try:
            transcript, candidates = self.pipeline.finish()
        except Exception as exc:  # noqa: BLE001
            self._failed(f"{type(exc).__name__}: {exc}")
            return
        self._finished(transcript, candidates)

    # ----------------------------------------------------------------- callbacks
    def _append_live(self, source: str, text: str) -> None:
        self.transcript.moveCursor(QTextCursor.End)
        if self.transcript.toPlainText():
            self.transcript.insertPlainText("\n")
        self.transcript.insertPlainText(text)
        self.transcript.moveCursor(QTextCursor.End)

    def _show_live_error(self, message: str) -> None:
        self.status.setText(self.t("meeting.audio_warning").format(warning=message))

    def _show_progress(self, done: int, total: int) -> None:
        self.status.setText(self.t("meeting.processing_chunk").format(done=done, total=total))

    def _finished(self, transcript, candidates) -> None:
        self._processing = False
        self._last_transcript = transcript
        text = getattr(transcript, "confirmed_text", "") or ""
        if text:
            self.transcript.setPlainText(text)  # the authoritative, whole-meeting text
        self._sync_controls()
        participants = [p.strip() for p in self.participants.text().split(",") if p.strip()]
        self.on_finished(self.name.text(), transcript, candidates, participants)

    def _failed(self, message: str) -> None:
        self._processing = False
        self._sync_controls()
        text = self.t("meeting.error_process").format(error=message)
        self.status.setText(text)
        QMessageBox.warning(self, "Nexa", text)

    # ----------------------------------------------------------- transcript tools
    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.transcript.toPlainText())

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.t("meeting.save_transcript"), "transcript.txt", "Text (*.txt)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.transcript.toPlainText())
            self.status.setText(self.t("meeting.saved"))

    # ------------------------------------------------------------------ language
    def retranslate(self) -> None:
        self.title.setText(self.t("meeting.title"))
        self.name_label.setText(self.t("meeting.name"))
        self.template_label.setText(self.t("meeting.template"))
        self.participants_label.setText(self.t("meeting.participants"))
        self.source_label.setText(self.t("meeting.audio_source"))
        current = self.source.currentIndex() if self.source.count() else 2
        self.source.blockSignals(True)
        self.source.clear()
        self.source.addItems([self.t("meeting.mic"), self.t("meeting.computer"), self.t("meeting.both")])
        self.source.setCurrentIndex(current if current >= 0 else 2)
        self.source.blockSignals(False)
        self.start_btn.setText(self.t("meeting.start"))
        self.pause_btn.setText(self.t("meeting.pause"))
        self.resume_btn.setText(self.t("meeting.resume"))
        self.stop_btn.setText(self.t("meeting.stop").replace("&", "&&"))
        self.transcript_label.setText(self.t("meeting.live_transcript"))
        self.transcript.setPlaceholderText(self.t("meeting.transcript_placeholder"))
        self.copy_btn.setText(self.t("meeting.copy_transcript"))
        self.save_btn.setText(self.t("meeting.save_transcript"))
        if not self._processing:
            self._sync_controls()
