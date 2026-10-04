from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from nexa.services.models import ActionCandidate
from nexa.ui.review.action_card import ActionCard
from nexa.ui.review.duplicate_dialog import DuplicateDialog
from nexa.ui.review.viewmodel import ReviewViewModel
from nexa.ui.widgets.common import ghost_button, muted, page_title


class ReviewPage(QWidget):
    def __init__(self, t, people, on_approve) -> None:
        super().__init__()
        self.t = t
        self.people = people
        self.on_approve = on_approve
        self.vm = ReviewViewModel()
        layout = QVBoxLayout(self)
        self.title = page_title("")
        layout.addWidget(self.title)
        self.transcript = muted("")
        layout.addWidget(self.transcript)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.host = QWidget()
        self.cards_layout = QVBoxLayout(self.host)
        self.scroll.setWidget(self.host)
        layout.addWidget(self.scroll, 1)
        row = QHBoxLayout()
        self.add_btn = ghost_button("")
        self.approve_btn = QPushButton()
        row.addWidget(self.add_btn)
        row.addWidget(self.approve_btn)
        layout.addLayout(row)
        self.add_btn.clicked.connect(self._add)
        self.approve_btn.clicked.connect(self._approve)
        self.cards: list[ActionCard] = []
        self.retranslate()

    def set_result(self, title, transcript, candidates, participants=None) -> None:
        self.vm.set_result(title, transcript, candidates, participants)
        self.rebuild_cards()
        self.retranslate()

    def rebuild_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards = []
        for candidate in self.vm.items:
            card = ActionCard(self.t, candidate, self.people, self._delete, self._duplicate)
            self.cards.append(card)
            self.cards_layout.addWidget(card)
        self.cards_layout.addStretch()

    def _delete(self, item_id: int) -> None:
        self.vm.remove(item_id)
        self.rebuild_cards()

    def _duplicate(self, item: ActionCandidate) -> None:
        other = next((i for i in self.vm.items if i.id == item.possible_duplicate_of), None)
        if not other:
            return
        dialog = DuplicateDialog(self.t, other, item, self)
        if dialog.exec() and dialog.choice == "merge":
            self.vm.merge(item.id, other.id)
            self.rebuild_cards()

    def _add(self) -> None:
        next_id = max([i.id for i in self.vm.items], default=0) + 1
        self.vm.items.append(ActionCandidate(next_id, "", self.t("review.unassigned"), None, "", "", "", 1.0))
        self.rebuild_cards()

    def _approve(self) -> None:
        for card in self.cards:
            card.sync()
        if not self.vm.items:
            QMessageBox.information(self, "Nexa", self.t("empty.no_actions"))
            return
        self.on_approve(self.vm.meeting_title, self.vm.items, self.vm.participants)

    def retranslate(self) -> None:
        self.title.setText(self.t("review.title"))
        text = self.vm.transcript_text or self.t("empty.no_actions")
        self.transcript.setText(text)
        self.add_btn.setText(self.t("review.add_manual"))
        self.approve_btn.setText(self.t("review.approve_all"))
        for card in self.cards:
            card.retranslate()
