from PySide6.QtWidgets import QApplication

from nexa.ui.main_window import MainWindow


def create_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Nexa")
    app.setOrganizationName("Nexa")
    return app


def run() -> int:
    app = create_app()
    window = MainWindow()
    window.show()
    return app.exec()
