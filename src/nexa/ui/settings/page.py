from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from nexa.ui.settings.viewmodel import SettingsViewModel
from nexa.ui.widgets.common import ghost_button, page_title


class SettingsPage(QWidget):
    def __init__(self, t, state, services, on_apply, on_first_run) -> None:
        super().__init__()
        self.t = t
        self.state = state
        self.services = services
        self.on_apply = on_apply
        self.on_first_run = on_first_run
        self.vm = SettingsViewModel(state, services)
        layout = QVBoxLayout(self)
        self.title = page_title("")
        layout.addWidget(self.title)
        form = QFormLayout()
        self.language = QComboBox()
        self.theme = QComboBox()
        self.email_lang = QComboBox()
        self.gmail_status = QLabel()
        self.models = QLabel()
        self.worker = QLabel()
        self.evening = QLineEdit()
        self.morning = QLineEdit()
        self.audio = QComboBox()
        self.transcript = QComboBox()
        self.lang_label = QLabel()
        self.theme_label = QLabel()
        self.email_label = QLabel()
        self.gmail_label = QLabel()
        self.models_label = QLabel()
        self.worker_label = QLabel()
        self.evening_label = QLabel()
        self.morning_label = QLabel()
        self.audio_label = QLabel()
        self.transcript_label = QLabel()
        form.addRow(self.lang_label, self.language)
        form.addRow(self.theme_label, self.theme)
        form.addRow(self.email_label, self.email_lang)
        form.addRow(self.gmail_label, self.gmail_status)
        form.addRow(self.models_label, self.models)
        form.addRow(self.worker_label, self.worker)
        form.addRow(self.evening_label, self.evening)
        form.addRow(self.morning_label, self.morning)
        form.addRow(self.audio_label, self.audio)
        form.addRow(self.transcript_label, self.transcript)
        layout.addLayout(form)
        self.connect_btn = QPushButton()
        self.apply_btn = QPushButton()
        self.first_run_btn = ghost_button("")
        layout.addWidget(self.connect_btn)
        layout.addWidget(self.apply_btn)
        layout.addWidget(self.first_run_btn)
        layout.addStretch()
        self.connect_btn.clicked.connect(self._toggle_gmail)
        self.apply_btn.clicked.connect(self._apply)
        self.first_run_btn.clicked.connect(self.on_first_run)
        self.retranslate()

    def _toggle_gmail(self) -> None:
        if self.services.email.connected:
            self.services.email.disconnect()
        else:
            self.services.email.connect()
        self.retranslate()

    def _apply(self) -> None:
        self.vm.apply_from_ui(
            self.language.currentIndex(),
            self.theme.currentIndex(),
            self.email_lang.currentIndex(),
            self.audio.currentIndex(),
            self.transcript.currentIndex(),
            self.evening.text().strip(),
            self.morning.text().strip(),
        )
        self.on_apply()

    def retranslate(self) -> None:
        self.title.setText(self.t("settings.title"))
        self.lang_label.setText(self.t("settings.ui_language"))
        self.theme_label.setText(self.t("settings.theme"))
        self.email_label.setText(self.t("settings.default_email_language"))
        self.gmail_label.setText(self.t("settings.gmail"))
        self.models_label.setText(self.t("settings.models"))
        self.worker_label.setText(self.t("settings.worker"))
        self.evening_label.setText(self.t("settings.evening"))
        self.morning_label.setText(self.t("settings.morning"))
        self.audio_label.setText(self.t("settings.retention_audio"))
        self.transcript_label.setText(self.t("settings.retention_transcript"))
        self.language.blockSignals(True)
        self.language.clear()
        self.language.addItems([self.t("common.english"), self.t("common.arabic")])
        self.language.setCurrentIndex(1 if self.state.language == "ar" else 0)
        self.language.blockSignals(False)
        self.theme.clear()
        self.theme.addItems([self.t("settings.light"), self.t("settings.dark")])
        self.theme.setCurrentIndex(1 if self.state.theme == "dark" else 0)
        self.email_lang.clear()
        self.email_lang.addItems([self.t("common.english"), self.t("common.arabic"), self.t("common.bilingual")])
        self.email_lang.setCurrentIndex({"ENGLISH": 0, "ARABIC": 1, "BILINGUAL": 2}.get(self.state.email_language, 0))
        self.audio.clear()
        self.audio.addItems([self.t("settings.delete_after_approval"), self.t("settings.keep")])
        self.audio.setCurrentIndex(1 if self.state.audio_retention == "keep" else 0)
        self.transcript.clear()
        self.transcript.addItems([self.t("settings.delete_after_approval"), self.t("settings.keep")])
        self.transcript.setCurrentIndex(1 if self.state.transcript_retention == "keep" else 0)
        connected = self.services.email.connected
        self.gmail_status.setText(self.t("settings.connected") if connected else self.t("settings.disconnected"))
        self.connect_btn.setText(self.t("settings.disconnect") if connected else self.t("settings.connect"))
        self.models.setText(f"{self.t('settings.speech')} ✓   {self.t('settings.llm')} ✓")
        self.worker.setText(self.t("settings.worker_online") if self.services.worker_online else self.t("settings.worker_offline"))
        self.evening.setText(self.state.evening_reminder)
        self.morning.setText(self.state.morning_reminder)
        self.apply_btn.setText(self.t("settings.apply"))
        self.first_run_btn.setText(self.t("settings.first_run"))
