from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from nexa.services.models import ActionCandidate
from nexa.ui.widgets.common import muted


class DuplicateDialog(QDialog):
    def __init__(self, t, left: ActionCandidate, right: ActionCandidate, parent=None) -> None:
        super().__init__(parent)
        self.t = t
        self.choice = "keep"
        self.setWindowTitle(t("review.duplicate"))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("review.duplicate")))
        layout.addWidget(muted(left.source_text))
        layout.addWidget(muted(right.source_text))
        buttons = QDialogButtonBox()
        keep = buttons.addButton(t("common.keep_both"), QDialogButtonBox.AcceptRole)
        merge = buttons.addButton(t("common.merge"), QDialogButtonBox.ActionRole)
        layout.addWidget(buttons)
        keep.clicked.connect(lambda: self._pick("keep"))
        merge.clicked.connect(lambda: self._pick("merge"))

    def _pick(self, choice: str) -> None:
        self.choice = choice
        self.accept()
