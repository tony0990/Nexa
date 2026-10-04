from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nexa.ui.meeting.viewmodel import MeetingViewModel
from nexa.ui.widgets.common import ghost_button, muted, page_title


class MeetingPage(QWidget):
    SOURCE_KEYS = ["mic", "computer", "mic+computer"]

    def __init__(self, t, audio, transcription, extraction, on_finished) -> None:
        super().__init__()
        self.t = t
        self.on_finished = on_finished
        self.vm = MeetingViewModel(audio, transcription, extraction)
        layout = QVBoxLayout(self)
        self.title = page_title("")
        layout.addWidget(self.title)
        form = QFormLayout()
        self.name = QLineEdit("Weekly Development Meeting")
        self.template = QComboBox()
        self.template.addItems(list(MeetingViewModel.TEMPLATES))
        self.participants = QLineEdit("Ahmed Hassan, Maria Adel")
        self.source = QComboBox()
        form.addRow(self._label("meeting.name"), self.name)
        self.name_label = form.labelForField(self.name)
        form.addRow("", self.template)
        form.addRow("", self.participants)
        form.addRow("", self.source)
        self.template_label = QLabel()
        self.participants_label = QLabel()
        self.source_label = QLabel()
        form.setWidget(1, QFormLayout.LabelRole, self.template_label)
        form.setWidget(2, QFormLayout.LabelRole, self.participants_label)
        form.setWidget(3, QFormLayout.LabelRole, self.source_label)
        layout.addLayout(form)
        self.status = muted("")
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setStyleSheet("font-size: 32px; font-weight: 700;")
        layout.addWidget(self.status)
        layout.addWidget(self.timer_label)
        row = QHBoxLayout()
        self.start_btn = QPushButton()
        self.pause_btn = ghost_button("")
        self.resume_btn = ghost_button("")
        self.stop_btn = QPushButton()
        for b in (self.start_btn, self.pause_btn, self.resume_btn, self.stop_btn):
            row.addWidget(b)
        layout.addLayout(row)
        layout.addStretch()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.start_btn.clicked.connect(self._start)
        self.pause_btn.clicked.connect(self._pause)
        self.resume_btn.clicked.connect(self._resume)
        self.stop_btn.clicked.connect(self._stop)
        self.template.currentTextChanged.connect(self._apply_template)
        self.retranslate()

    def _label(self, key: str) -> QLabel:
        return QLabel(self.t(key))

    def _apply_template(self, name: str) -> None:
        defaults = self.vm.apply_template(name)
        if defaults["title"]:
            self.name.setText(defaults["title"])
        self.participants.setText(defaults["participants"])
        index = self.SOURCE_KEYS.index(defaults["source"])
        self.source.setCurrentIndex(index)

    def _tick(self) -> None:
        if self.vm.audio.running and not self.vm.audio.paused:
            self.vm.elapsed += 1
            s = self.vm.elapsed
            self.timer_label.setText(f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}")

    def _source_value(self) -> str:
        return self.SOURCE_KEYS[self.source.currentIndex()]

    def _start(self) -> None:
        self.vm.start(self._source_value())
        self.timer.start(1000)
        self.status.setText(self.t("meeting.status_recording"))

    def _pause(self) -> None:
        self.vm.pause()
        self.status.setText(self.t("meeting.status_paused"))

    def _resume(self) -> None:
        self.vm.resume()
        self.status.setText(self.t("meeting.status_recording"))

    def _stop(self) -> None:
        self.timer.stop()
        self.status.setText(self.t("meeting.status_processing"))
        transcript, candidates = self.vm.stop()
        participants = [p.strip() for p in self.participants.text().split(",") if p.strip()]
        self.on_finished(self.name.text(), transcript, candidates, participants)
        self.status.setText(self.t("meeting.status_idle"))

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
        self.stop_btn.setText(self.t("meeting.stop"))
        if not self.vm.audio.running:
            self.status.setText(self.t("meeting.status_idle"))
