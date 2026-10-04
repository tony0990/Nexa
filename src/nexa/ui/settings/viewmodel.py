class SettingsViewModel:
    def __init__(self, state, services) -> None:
        self.state = state
        self.services = services

    def apply_from_ui(self, language_index: int, theme_index: int, email_index: int, audio_index: int, transcript_index: int, evening: str, morning: str) -> None:
        self.state.language = "ar" if language_index == 1 else "en"
        self.state.theme = "dark" if theme_index == 1 else "light"
        self.state.email_language = ["ENGLISH", "ARABIC", "BILINGUAL"][email_index]
        self.state.audio_retention = "keep" if audio_index == 1 else "delete_after_approval"
        self.state.transcript_retention = "keep" if transcript_index == 1 else "delete_after_approval"
        self.state.evening_reminder = evening or self.state.evening_reminder
        self.state.morning_reminder = morning or self.state.morning_reminder
        self.state.persist()
