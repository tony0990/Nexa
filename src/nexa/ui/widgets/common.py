from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PageTitle")
    return label


def muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label


def ghost_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("Ghost")
    return button


def hbox(*widgets) -> QHBoxLayout:
    layout = QHBoxLayout()
    for widget in widgets:
        layout.addWidget(widget)
    return layout
