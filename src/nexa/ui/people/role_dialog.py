from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit


class RoleDialog(QDialog):
    def __init__(self, t, role=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("people.edit_role") if role else t("people.add_role"))
        layout = QFormLayout(self)
        self.name = QLineEdit(role.name if role else "")
        self.description = QLineEdit(role.description if role else "")
        layout.addRow(t("people.role"), self.name)
        layout.addRow(t("audit.detail"), self.description)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        layout.addRow(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
