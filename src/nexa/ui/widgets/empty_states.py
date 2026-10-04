from PySide6.QtWidgets import QVBoxLayout, QWidget

from nexa.ui.widgets.common import muted


class EmptyState(QWidget):
    def __init__(self, text: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.label = muted(text)
        layout.addWidget(self.label)

    def set_text(self, text: str) -> None:
        self.label.setText(text)
