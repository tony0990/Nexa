from PySide6.QtCore import QObject, QSettings, Signal


class AppState(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("Nexa", "NexaDesktop")
        self.language = self.settings.value("ui_language", "en")
        self.theme = self.settings.value("theme", "light")
        self.email_language = self.settings.value("email_language", "ENGLISH")
        self.organization = self.settings.value("organization", "Nexa Organization")
        self.sender_name = self.settings.value("sender_name", "Nexa")
        self.evening_reminder = self.settings.value("evening_reminder", "20:00")
        self.morning_reminder = self.settings.value("morning_reminder", "08:00")
        self.audio_retention = self.settings.value("audio_retention", "delete_after_approval")
        self.transcript_retention = self.settings.value("transcript_retention", "delete_after_approval")
        self.first_run_done = self.settings.value("first_run_done", False, type=bool)

    def persist(self) -> None:
        self.settings.setValue("ui_language", self.language)
        self.settings.setValue("theme", self.theme)
        self.settings.setValue("email_language", self.email_language)
        self.settings.setValue("organization", self.organization)
        self.settings.setValue("sender_name", self.sender_name)
        self.settings.setValue("evening_reminder", self.evening_reminder)
        self.settings.setValue("morning_reminder", self.morning_reminder)
        self.settings.setValue("audio_retention", self.audio_retention)
        self.settings.setValue("transcript_retention", self.transcript_retention)
        self.settings.setValue("first_run_done", self.first_run_done)
        self.changed.emit()
