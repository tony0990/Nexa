from PySide6.QtCore import Qt

from nexa.ui.main_window import MainWindow
from nexa.ui.navigation import ALL_PAGE_KEYS


def test_navigation_covers_every_owned_page(qapp):
    window = MainWindow(skip_first_run=True)
    window.show()
    for key in ALL_PAGE_KEYS:
        window.navigate(key)
        assert window.stack.currentIndex() == ALL_PAGE_KEYS.index(key)
    window.close()


def test_arabic_ui_and_dark_theme_apply(qapp):
    window = MainWindow(skip_first_run=True)
    window.state.language = "ar"
    window.state.theme = "dark"
    window.apply_appearance()
    assert window.layoutDirection() == Qt.RightToLeft
    assert "لوحة التحكم" in window.buttons[0][1].text()
    assert window.theme.theme == "dark"
    window.state.language = "en"
    window.state.theme = "light"
    window.apply_appearance()
    assert window.layoutDirection() == Qt.LeftToRight
    window.close()


def test_global_search_opens_search_page(qapp):
    window = MainWindow(skip_first_run=True)
    window.global_search.setText("Ahmed")
    window._run_global_search()
    assert window.stack.currentWidget() is window.pages["search"]
    assert "Ahmed Hassan" in window.pages["search"].employees.text()
    window.close()
