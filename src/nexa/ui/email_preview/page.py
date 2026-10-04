from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from nexa.ui.email_preview.viewmodel import EmailPreviewViewModel
from nexa.ui.widgets.common import ghost_button, page_title

EMAIL_PREVIEW_CSS = """
QTextBrowser#EmailPreview {
  background: #ffffff;
  color: #111111;
  border: 1px solid #d0d7e6;
}
"""
EMAIL_DOCUMENT_CSS = "body { color: #111111; background: #ffffff; font-family: Segoe UI, Tahoma, sans-serif; }"


class EmailPreviewPage(QWidget):
    def __init__(self, t, email_service, people, state, on_back=None, on_sent=None) -> None:
        super().__init__()
        self.t = t
        self.state = state
        self.on_back = on_back
        self.on_sent = on_sent
        self.vm = EmailPreviewViewModel(email_service, people, state)
        layout = QVBoxLayout(self)
        self.title = page_title("")
        layout.addWidget(self.title)
        form = QFormLayout()
        self.language = QComboBox()
        self.target = QComboBox()
        self.role = QComboBox()
        self.recipients = QLineEdit()
        self.reminder_target = QComboBox()
        self.reminder_recipients = QLineEdit()
        self.reminder_label = QLabel()
        self.sender = QLabel()
        self.subject = QLabel()
        self.lang_label = QLabel()
        self.target_label = QLabel()
        self.role_label = QLabel()
        self.to_label = QLabel()
        self.from_label = QLabel()
        self.subject_label = QLabel()
        form.addRow(self.lang_label, self.language)
        form.addRow(self.target_label, self.target)
        form.addRow(self.role_label, self.role)
        form.addRow(self.to_label, self.recipients)
        form.addRow(self.reminder_label, self.reminder_target)
        form.addRow("", self.reminder_recipients)
        form.addRow(self.from_label, self.sender)
        form.addRow(self.subject_label, self.subject)
        layout.addLayout(form)
        self.html = QTextBrowser()
        self.html.setObjectName("EmailPreview")
        self.html.setAttribute(Qt.WA_StyledBackground, True)
        self.html.setAutoFillBackground(True)
        self.html.setStyleSheet(EMAIL_PREVIEW_CSS)
        self.html.document().setDefaultStyleSheet(EMAIL_DOCUMENT_CSS)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.html, 2)
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        self.back_btn = ghost_button("")
        self.edit_btn = ghost_button("")
        self.refresh_btn = ghost_button("")
        self.send_btn = QPushButton()
        for button in (self.back_btn, self.edit_btn, self.refresh_btn, self.send_btn):
            row.addWidget(button)
        layout.addLayout(row)
        self.language.currentIndexChanged.connect(self.refresh)
        self.target.currentIndexChanged.connect(self._apply_target)
        self.role.currentIndexChanged.connect(self._apply_target)
        self.reminder_target.currentIndexChanged.connect(self._apply_reminder_target)
        self.recipients.textChanged.connect(self._apply_reminder_target)
        self.refresh_btn.clicked.connect(self.refresh)
        self.send_btn.clicked.connect(self._send)
        self.back_btn.clicked.connect(self._back)
        self.edit_btn.clicked.connect(self.recipients.setFocus)
        self.retranslate()

    def set_approved(self, meeting_title, actions, participants=None) -> None:
        self.vm.meeting_title = meeting_title
        self.vm.actions = actions
        self.vm.participants = list(participants or [])
        self._apply_target()

    def _mode(self) -> str:
        if not self.target.count():
            return "ASSIGNEE"
        return EmailPreviewViewModel.TARGETS[self.target.currentIndex()]

    def _selected_role(self) -> str | None:
        return self.role.currentText() or None

    def _apply_target(self) -> None:
        mode = self._mode()
        needs_role = mode in {"ROLE", "ASSIGNEE_PLUS_ROLE"} or self._reminder_mode() == "ASSIGNEE_PLUS_ROLE"
        self.role.setVisible(needs_role)
        self.role_label.setVisible(needs_role)
        if mode != "CUSTOM":
            self.recipients.setText(", ".join(self.vm.recipients_for_mode(mode, self._selected_role())))
        self.refresh()

    def _reminder_mode(self) -> str:
        if not self.reminder_target.count():
            return "ASSIGNEE"
        return EmailPreviewViewModel.REMINDER_TARGETS[self.reminder_target.currentIndex()]

    def _split(self, text: str) -> list[str]:
        return [part.strip() for part in text.split(",") if part.strip()]

    def _apply_reminder_target(self) -> None:
        mode = self._reminder_mode()
        needs_role = mode == "ASSIGNEE_PLUS_ROLE" or self._mode() in {"ROLE", "ASSIGNEE_PLUS_ROLE"}
        self.role.setVisible(needs_role)
        self.role_label.setVisible(needs_role)
        if mode == "CUSTOM":
            self.reminder_recipients.setReadOnly(False)
            names = self._split(self.reminder_recipients.text())
        else:
            self.reminder_recipients.setReadOnly(True)
            names = self.vm.reminder_recipients_for(
                mode, self._selected_role(), self._split(self.recipients.text())
            )
            self.reminder_recipients.setText(", ".join(names))
        self.vm.reminder_recipients = names

    def refresh(self) -> None:
        language = EmailPreviewViewModel.LANGUAGES[self.language.currentIndex()] if self.language.count() else "ENGLISH"
        recipients = [part.strip() for part in self.recipients.text().split(",") if part.strip()]
        preview = self.vm.build(language, recipients)
        self.sender.setText(preview.rendered.sender)
        self.subject.setText(preview.rendered.subject)
        self.html.document().setDefaultStyleSheet(EMAIL_DOCUMENT_CSS)
        self.html.setHtml(preview.rendered.html)
        self.text.setPlainText(preview.rendered.text)
        self._apply_reminder_target()

    def _back(self) -> None:
        if self.on_back:
            self.on_back()

    def _send(self) -> None:
        if not self.vm.rendered:
            self.refresh()
        if not self._split(self.recipients.text()):
            QMessageBox.warning(self, "Nexa", self.t("email.no_recipients"))
            return
        result = self.vm.email.send(self.vm.rendered)
        if result.success:
            QMessageBox.information(self, "Nexa", self.t("email.sent"))
            if self.on_sent:
                self.on_sent()

    def retranslate(self) -> None:
        self.title.setText(self.t("email.title"))
        self.lang_label.setText(self.t("email.language"))
        self.target_label.setText(self.t("email.recipients_mode"))
        self.role_label.setText(self.t("email.role"))
        self.to_label.setText(self.t("email.recipients"))
        self.reminder_label.setText(self.t("email.reminder_recipients"))
        self.from_label.setText(self.t("email.from"))
        self.subject_label.setText(self.t("email.subject"))
        default_lang = EmailPreviewViewModel.LANGUAGES.index(self.vm.default_language())
        current = self.language.currentIndex() if self.language.count() else default_lang
        self.language.blockSignals(True)
        self.language.clear()
        self.language.addItems([self.t("common.english"), self.t("common.arabic"), self.t("common.bilingual")])
        self.language.setCurrentIndex(max(current, 0))
        self.language.blockSignals(False)
        target = self.target.currentIndex() if self.target.count() else 0
        self.target.blockSignals(True)
        self.target.clear()
        self.target.addItems(
            [
                self.t("email.assignees"),
                self.t("email.all_employees"),
                self.t("email.participants"),
                self.t("email.by_role"),
                self.t("email.assignees_and_role"),
                self.t("email.custom"),
            ]
        )
        self.target.setCurrentIndex(max(target, 0))
        self.target.blockSignals(False)
        rt = self.reminder_target.currentIndex() if self.reminder_target.count() else 0
        self.reminder_target.blockSignals(True)
        self.reminder_target.clear()
        self.reminder_target.addItems(
            [
                self.t("email.assignees"),
                self.t("email.assignees_and_role"),
                self.t("email.same_as_report"),
                self.t("email.custom"),
            ]
        )
        self.reminder_target.setCurrentIndex(max(rt, 0))
        self.reminder_target.blockSignals(False)
        role_name = self.role.currentText() if self.role.count() else ""
        self.role.blockSignals(True)
        self.role.clear()
        self.role.addItems(self.vm.role_names())
        if role_name:
            self.role.setCurrentText(role_name)
        self.role.blockSignals(False)
        self.back_btn.setText(self.t("common.back"))
        self.edit_btn.setText(self.t("email.edit_recipients"))
        self.refresh_btn.setText(self.t("common.refresh"))
        self.send_btn.setText(self.t("common.send"))
        self._apply_target()
