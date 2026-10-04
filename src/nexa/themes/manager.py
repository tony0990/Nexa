from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget


class ThemeManager:
    def __init__(self, widget: QWidget, theme: str = "light") -> None:
        self.widget = widget
        self._dir = Path(__file__).resolve().parent
        self.theme = theme
        self.apply(theme)

    def apply(self, theme: str) -> None:
        self.theme = "dark" if theme == "dark" else "light"
        qss = (self._dir / f"{self.theme}.qss").read_text(encoding="utf-8")
        app = QApplication.instance()
        if app:
            app.setStyleSheet(qss)
        else:
            self.widget.setStyleSheet(qss)
