from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from nexa.ui.schedule.viewmodel import SNOOZE_KEYS, WHEN_FORMAT, cairo_now, snooze_target
from nexa.ui.widgets.common import muted


class SnoozeDialog(QDialog):
    """Pick a snooze option. `option` / `custom_text` are read by the caller."""

    def __init__(self, t, parent=None, morning: str = "08:00") -> None:
        super().__init__(parent)
        self.t = t
        self.morning = morning
        self.option = SNOOZE_KEYS[0]
        self.custom_text = ""
        self.value = ""
        self.setWindowTitle(t("snooze.title"))
        layout = QVBoxLayout(self)
        layout.addWidget(muted(t("snooze.note")))
        self.combo = QComboBox()
        for key in SNOOZE_KEYS:
            self.combo.addItem(t(f"snooze.{key}"))
        self.custom = QDateTimeEdit()
        self.custom.setCalendarPopup(True)
        self.custom.setDisplayFormat("yyyy-MM-dd HH:mm")
        now = cairo_now()
        self.custom.setDateTime(QDateTime(now.year, now.month, now.day, now.hour, now.minute).addDays(1))
        self.custom.setVisible(False)
        self.error = QLabel()
        self.error.setObjectName("Muted")
        self.error.setVisible(False)
        layout.addWidget(self.combo)
        layout.addWidget(self.custom)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)
        self.combo.currentIndexChanged.connect(lambda i: self.custom.setVisible(SNOOZE_KEYS[i] == "custom"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

    def _accept(self) -> None:
        option = SNOOZE_KEYS[self.combo.currentIndex()]
        text = self.custom.dateTime().toString("yyyy-MM-dd HH:mm")
        try:
            self.value = snooze_target(option, cairo_now(), text, self.morning)
        except ValueError:
            self.error.setText(self.t("snooze.invalid"))
            self.error.setVisible(True)
            return
        self.option, self.custom_text = option, text
        self.accept()
