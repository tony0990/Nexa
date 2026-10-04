from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from nexa.ui.widgets.common import muted


class Card(QFrame):
    clicked = Signal()

    def __init__(self, title: str, value: str, subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        self.title_label = muted(title)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size: 28px; font-weight: 700;")
        self.subtitle_label = muted(subtitle)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.subtitle_label)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def mouseReleaseEvent(self, event) -> None:
        self.clicked.emit()
        super().mouseReleaseEvent(event)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
