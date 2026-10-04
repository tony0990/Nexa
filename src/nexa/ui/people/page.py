from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QPushButton, QTableWidget, QVBoxLayout, QWidget

from nexa.ui.people.employee_dialog import EmployeeDialog
from nexa.ui.people.role_dialog import RoleDialog
from nexa.ui.people.viewmodel import PeopleViewModel
from nexa.ui.widgets.common import ghost_button, page_title
from nexa.ui.widgets.dialogs import ConfirmDialog
from nexa.ui.widgets.tables import fill_table


class PeoplePage(QWidget):
    def __init__(self, t, people) -> None:
        super().__init__()
        self.t = t
        self.vm = PeopleViewModel(people)
        layout = QVBoxLayout(self)
        self.title = page_title("")
        layout.addWidget(self.title)
        toolbar = QHBoxLayout()
        self.query = QLineEdit()
        self.active = QComboBox()
        self.add_emp = QPushButton()
        self.edit_emp = ghost_button("")
        self.deactivate = ghost_button("")
        self.add_role = ghost_button("")
        self.edit_role = ghost_button("")
        self.deactivate_role = ghost_button("")
        for w in (
            self.query,
            self.active,
            self.add_emp,
            self.edit_emp,
            self.deactivate,
            self.add_role,
            self.edit_role,
            self.deactivate_role,
        ):
            toolbar.addWidget(w)
        layout.addLayout(toolbar)
        self.emp_table = QTableWidget()
        self.role_table = QTableWidget()
        layout.addWidget(self.emp_table, 2)
        layout.addWidget(self.role_table, 1)
        self.query.textChanged.connect(self.reload)
        self.active.currentIndexChanged.connect(self.reload)
        self.add_emp.clicked.connect(self._add_employee)
        self.edit_emp.clicked.connect(self._edit_employee)
        self.deactivate.clicked.connect(self._deactivate)
        self.add_role.clicked.connect(self._add_role)
        self.edit_role.clicked.connect(self._edit_role)
        self.deactivate_role.clicked.connect(self._deactivate_role)
        self.retranslate()

    def _selected_employee_id(self) -> int | None:
        row = self.emp_table.currentRow()
        if row < 0:
            return None
        return int(self.emp_table.item(row, 0).text())

    def _add_employee(self) -> None:
        dialog = EmployeeDialog(self.t, self.vm.people.list_roles(), parent=self)
        if dialog.exec() and dialog.data()["full_name"]:
            self.vm.people.create_employee(**dialog.data())
            self.reload()

    def _edit_employee(self) -> None:
        emp_id = self._selected_employee_id()
        if emp_id is None:
            return
        employee = next(e for e in self.vm.people.list_employees() if e.id == emp_id)
        dialog = EmployeeDialog(self.t, self.vm.people.list_roles(), employee, self)
        if dialog.exec():
            self.vm.people.update_employee(emp_id, **dialog.data())
            self.reload()

    def _deactivate(self) -> None:
        emp_id = self._selected_employee_id()
        if emp_id is None:
            return
        if ConfirmDialog(self.t("people.deactivate"), self.t("people.confirm_deactivate"), self).exec():
            self.vm.people.deactivate_employee(emp_id)
            self.reload()

    def _selected_role_id(self) -> int | None:
        row = self.role_table.currentRow()
        if row < 0:
            return None
        return int(self.role_table.item(row, 0).text())

    def _add_role(self) -> None:
        dialog = RoleDialog(self.t, parent=self)
        if dialog.exec() and dialog.name.text().strip():
            self.vm.people.create_role(dialog.name.text().strip(), dialog.description.text().strip())
            self.reload()

    def _edit_role(self) -> None:
        role_id = self._selected_role_id()
        if role_id is None:
            return
        role = next(r for r in self.vm.people.list_roles() if r.id == role_id)
        dialog = RoleDialog(self.t, role, self)
        if dialog.exec() and dialog.name.text().strip():
            self.vm.people.update_role(role_id, name=dialog.name.text().strip(), description=dialog.description.text().strip())
            self.reload()

    def _deactivate_role(self) -> None:
        role_id = self._selected_role_id()
        if role_id is None:
            return
        if ConfirmDialog(self.t("people.deactivate_role"), self.t("people.confirm_deactivate_role"), self).exec():
            self.vm.people.deactivate_role(role_id)
            self.reload()

    def reload(self) -> None:
        mapping = ["all", "active", "inactive"]
        self.vm.active = mapping[self.active.currentIndex()] if self.active.count() else "all"
        self.vm.query = self.query.text()
        employees = self.vm.employees()
        fill_table(
            self.emp_table,
            [
                "ID",
                self.t("people.name"),
                self.t("people.email"),
                self.t("people.department"),
                self.t("people.title_field"),
                self.t("people.role"),
                self.t("people.status"),
            ],
            [
                [
                    e.id,
                    e.full_name,
                    e.email,
                    e.department,
                    e.job_title,
                    ", ".join(e.roles),
                    self.t("common.active") if e.active else self.t("common.inactive"),
                ]
                for e in employees
            ],
        )
        fill_table(
            self.role_table,
            ["ID", self.t("people.roles"), self.t("audit.detail"), self.t("people.status")],
            [
                [r.id, r.name, r.description, self.t("common.active") if r.active else self.t("common.inactive")]
                for r in self.vm.roles()
            ],
        )

    def retranslate(self) -> None:
        self.title.setText(self.t("people.title"))
        self.query.setPlaceholderText(self.t("common.search"))
        current = self.active.currentIndex() if self.active.count() else 0
        self.active.blockSignals(True)
        self.active.clear()
        self.active.addItems([self.t("common.all"), self.t("common.active"), self.t("common.inactive")])
        self.active.setCurrentIndex(current)
        self.active.blockSignals(False)
        self.add_emp.setText(self.t("people.add_employee"))
        self.edit_emp.setText(self.t("people.edit_employee"))
        self.deactivate.setText(self.t("people.deactivate"))
        self.add_role.setText(self.t("people.add_role"))
        self.edit_role.setText(self.t("people.edit_role"))
        self.deactivate_role.setText(self.t("people.deactivate_role"))
        self.reload()
