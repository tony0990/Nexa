from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QListWidget, QListWidgetItem


class EmployeeDialog(QDialog):
    def __init__(self, t, roles, employee=None, parent=None) -> None:
        super().__init__(parent)
        self.t = t
        self.setWindowTitle(t("people.edit_employee") if employee else t("people.add_employee"))
        layout = QFormLayout(self)
        self.full_name = QLineEdit(employee.full_name if employee else "")
        self.email = QLineEdit(employee.email if employee else "")
        self.department = QLineEdit(employee.department if employee else "")
        self.job_title = QLineEdit(employee.job_title if employee else "")
        self.roles_list = QListWidget()
        selected = set(employee.roles if employee else [])
        for role in roles:
            item = QListWidgetItem(role.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if role.name in selected else Qt.Unchecked)
            self.roles_list.addItem(item)
        layout.addRow(t("people.name"), self.full_name)
        layout.addRow(t("people.email"), self.email)
        layout.addRow(t("people.department"), self.department)
        layout.addRow(t("people.title_field"), self.job_title)
        layout.addRow(t("people.role"), self.roles_list)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        layout.addRow(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

    def data(self) -> dict:
        roles = []
        for index in range(self.roles_list.count()):
            item = self.roles_list.item(index)
            if item.checkState() == Qt.Checked:
                roles.append(item.text())
        return {
            "full_name": self.full_name.text().strip(),
            "email": self.email.text().strip(),
            "department": self.department.text().strip(),
            "job_title": self.job_title.text().strip(),
            "roles": roles,
        }
