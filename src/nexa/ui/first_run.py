from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from nexa.i18n.service import TranslationService
from nexa.ui.state import AppState


class FirstRunDialog(QDialog):
    def __init__(self, state: AppState, trans: TranslationService, email_service, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self.trans = trans
        self.email = email_service
        self.setModal(True)
        self.resize(560, 460)
        self.step = 0
        root = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName("PageTitle")
        root.addWidget(self.title)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.lang = QComboBox()
        self.org = QLineEdit(self.state.organization)
        self.sender = QLineEdit(self.state.sender_name)
        self.evening = QLineEdit(self.state.evening_reminder)
        self.morning = QLineEdit(self.state.morning_reminder)
        self.audio_keep = QCheckBox()
        self.transcript_keep = QCheckBox()
        self.gmail_status = QLabel()
        self.speech_ok = QLabel()
        self.llm_ok = QLabel()

        self.stack.addWidget(self._lang_page())
        self.stack.addWidget(self._models_page())
        self.stack.addWidget(self._gmail_page())
        self.stack.addWidget(self._org_page())
        self.stack.addWidget(self._reminders_page())
        self.stack.addWidget(self._privacy_page())
        self.stack.addWidget(self._finish_page())

        nav = QHBoxLayout()
        self.back = QPushButton()
        self.next = QPushButton()
        nav.addWidget(self.back)
        nav.addStretch()
        nav.addWidget(self.next)
        root.addLayout(nav)
        self.back.clicked.connect(self._back)
        self.next.clicked.connect(self._next)
        self.retranslate()

    def t(self, key: str) -> str:
        return self.trans.t(key)

    def _wrap(self, *widgets) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        for widget in widgets:
            layout.addWidget(widget)
        layout.addStretch()
        return page

    def _lang_page(self) -> QWidget:
        self.lang.addItem("English", "en")
        self.lang.addItem("العربية", "ar")
        index = 1 if self.state.language == "ar" else 0
        self.lang.setCurrentIndex(index)
        self.lang_label = QLabel()
        return self._wrap(self.lang_label, self.lang)

    def _models_page(self) -> QWidget:
        self.models_label = QLabel()
        return self._wrap(self.models_label, self.speech_ok, self.llm_ok)

    def _gmail_page(self) -> QWidget:
        self.gmail_label = QLabel()
        connect = QPushButton()
        self.connect_btn = connect
        connect.clicked.connect(self._connect)
        return self._wrap(self.gmail_label, connect, self.gmail_status)

    def _org_page(self) -> QWidget:
        self.org_label = QLabel()
        self.sender_label = QLabel()
        return self._wrap(self.org_label, self.org, self.sender_label, self.sender)

    def _reminders_page(self) -> QWidget:
        self.reminders_label = QLabel()
        self.evening_label = QLabel()
        self.morning_label = QLabel()
        return self._wrap(self.reminders_label, self.evening_label, self.evening, self.morning_label, self.morning)

    def _privacy_page(self) -> QWidget:
        self.privacy_label = QLabel()
        return self._wrap(self.privacy_label, self.audio_keep, self.transcript_keep)

    def _finish_page(self) -> QWidget:
        self.finish_label = QLabel()
        self.finish_label.setWordWrap(True)
        return self._wrap(self.finish_label)

    def _connect(self) -> None:
        self.email.connect()
        self.gmail_status.setText(self.t("settings.connected"))

    def _back(self) -> None:
        if self.step > 0:
            self.step -= 1
            self.stack.setCurrentIndex(self.step)
            self.retranslate()

    def _next(self) -> None:
        if self.step < self.stack.count() - 1:
            if self.step == 0:
                self.state.language = self.lang.currentData()
                self.trans.set_language(self.state.language)
            self.step += 1
            self.stack.setCurrentIndex(self.step)
            self.retranslate()
            return
        self.state.organization = self.org.text().strip() or self.state.organization
        self.state.sender_name = self.sender.text().strip() or self.state.sender_name
        self.state.evening_reminder = self.evening.text().strip() or self.state.evening_reminder
        self.state.morning_reminder = self.morning.text().strip() or self.state.morning_reminder
        self.state.audio_retention = "keep" if self.audio_keep.isChecked() else "delete_after_approval"
        self.state.transcript_retention = "keep" if self.transcript_keep.isChecked() else "delete_after_approval"
        self.state.first_run_done = True
        self.state.persist()
        self.accept()

    def retranslate(self) -> None:
        self.setWindowTitle(self.t("first_run.title"))
        self.title.setText(self.t("first_run.title"))
        self.lang_label.setText(self.t("first_run.language"))
        self.models_label.setText(self.t("first_run.models"))
        self.speech_ok.setText("✓  " + self.t("settings.speech"))
        self.llm_ok.setText("✓  " + self.t("settings.llm"))
        self.gmail_label.setText(self.t("first_run.gmail"))
        self.connect_btn.setText(self.t("settings.connect"))
        self.org_label.setText(self.t("first_run.organization"))
        self.sender_label.setText(self.t("first_run.sender"))
        self.reminders_label.setText(self.t("first_run.reminders"))
        self.evening_label.setText(self.t("settings.evening"))
        self.morning_label.setText(self.t("settings.morning"))
        self.privacy_label.setText(self.t("first_run.privacy"))
        self.finish_label.setText(self.t("first_run.finish_note"))
        self.audio_keep.setText(self.t("settings.retention_audio") + " — " + self.t("settings.keep"))
        self.transcript_keep.setText(self.t("settings.retention_transcript") + " — " + self.t("settings.keep"))
        self.back.setText(self.t("first_run.back"))
        self.next.setText(self.t("first_run.finish") if self.step == self.stack.count() - 1 else self.t("first_run.next"))
        self.setLayoutDirection(Qt.RightToLeft if self.trans.is_rtl() else Qt.LeftToRight)
