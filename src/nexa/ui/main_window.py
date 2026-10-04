from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from nexa.i18n.service import TranslationService
from nexa.services.fakes import FakeServiceContainer
from nexa.themes.manager import ThemeManager
from nexa.ui.dashboard.page import DashboardPage
from nexa.ui.email_preview.page import EmailPreviewPage
from nexa.ui.first_run import FirstRunDialog
from nexa.ui.history.page import AuditHistoryPage, EmailHistoryPage
from nexa.ui.meeting.page import MeetingPage
from nexa.ui.navigation import ALL_PAGE_KEYS, SIDEBAR_KEYS
from nexa.ui.people.page import PeoplePage
from nexa.ui.review.page import ReviewPage
from nexa.ui.schedule.page import SchedulePage
from nexa.ui.search.page import SearchPage
from nexa.ui.settings.page import SettingsPage
from nexa.ui.state import AppState


class MainWindow(QMainWindow):
    def __init__(self, skip_first_run: bool = False, services=None) -> None:
        super().__init__()
        self.state = AppState()
        self.trans = TranslationService(self.state.language)
        # The real container in the shipped app, the fakes for --demo and the tests.
        self.services = services if services is not None else FakeServiceContainer()
        self.setMinimumSize(1200, 740)
        self.theme = ThemeManager(self, self.state.theme)
        self._build()
        self.apply_direction()
        if not skip_first_run and not self.state.first_run_done:
            self.open_first_run()

    def t(self, key: str) -> str:
        return self.trans.t(key)

    def _build(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        side = QVBoxLayout(self.sidebar)
        self.brand = QLabel("Nexa")
        self.brand.setObjectName("AppTitle")
        side.addWidget(self.brand)

        content = QVBoxLayout()
        self.global_search = QLineEdit()
        self.global_search.returnPressed.connect(self._run_global_search)
        content.addWidget(self.global_search)

        self.stack = QStackedWidget()
        self.pages = {
            "dashboard": DashboardPage(
                self.t,
                self.services.reminders,
                lambda: self.navigate("schedule"),
                lambda: self.navigate("review"),
                lambda: self.navigate("email_history"),
            ),
            "meeting": MeetingPage(self.t, self.services.audio, self.services.transcription, self.services.extraction, self.after_meeting,
                                     pipeline=getattr(self.services, "pipeline", None)),
            "review": ReviewPage(self.t, self.services.people, self.after_review),
            "schedule": SchedulePage(self.t, self.services.reminders, self.state.morning_reminder),
            "people": PeoplePage(self.t, self.services.people),
            "email_history": EmailHistoryPage(self.t, self.services.email),
            "audit": AuditHistoryPage(self.t, self.services.audit),
            "settings": SettingsPage(self.t, self.state, self.services, self.apply_appearance, self.open_first_run),
            "search": SearchPage(self.t, self.services.search),
            "email_preview": EmailPreviewPage(
                self.t,
                self.services.email,
                self.services.people,
                self.state,
                lambda: self.navigate("review"),
                lambda: self.navigate("email_history"),
            ),
        }
        for key in ALL_PAGE_KEYS:
            self.stack.addWidget(self.pages[key])
        content.addWidget(self.stack, 1)

        self.buttons = []
        for key in SIDEBAR_KEYS:
            button = QPushButton()
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, k=key: self.navigate(k))
            side.addWidget(button)
            self.buttons.append((key, button))
        side.addStretch()
        layout.addWidget(self.sidebar)
        layout.addLayout(content, 1)
        self.setCentralWidget(root)
        self.retranslate()
        self.navigate("dashboard")

    def _run_global_search(self) -> None:
        query = self.global_search.text()
        self.pages["search"].set_query(query)
        self.navigate("search")

    def navigate(self, key: str) -> None:
        index = ALL_PAGE_KEYS.index(key)
        self.stack.setCurrentIndex(index)
        for nav_key, button in self.buttons:
            button.setChecked(nav_key == key)
        if key == "email_history":
            self.pages["email_history"].retranslate()
        if key == "dashboard":
            self.pages["dashboard"].retranslate()
        if key == "schedule":
            self.pages["schedule"].reload()

    def after_meeting(self, title, transcript, candidates, participants=None) -> None:
        self.pages["review"].set_result(title, transcript, candidates, participants)
        self.navigate("review")

    def after_review(self, title, items, participants=None) -> None:
        self.services.reminders.import_approved(title, items, participants=participants)
        self.pages["schedule"].reload()
        self.pages["dashboard"].retranslate()
        self.pages["email_preview"].set_approved(title, items, participants)
        self.navigate("email_preview")

    def apply_appearance(self) -> None:
        self.trans.set_language(self.state.language)
        self.pages["schedule"].morning = self.state.morning_reminder
        self.theme.apply(self.state.theme)
        self.apply_direction()
        self.retranslate()

    def apply_direction(self) -> None:
        direction = Qt.RightToLeft if self.trans.is_rtl() else Qt.LeftToRight
        self.setLayoutDirection(direction)
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            app.setLayoutDirection(direction)

    def retranslate(self) -> None:
        self.setWindowTitle(self.t("app.title"))
        self.global_search.setPlaceholderText(self.t("common.search"))
        for key, button in self.buttons:
            button.setText(self.t(f"nav.{key}").replace("&", "&&"))
        for page in self.pages.values():
            page.retranslate()

    def open_first_run(self) -> None:
        dialog = FirstRunDialog(self.state, self.trans, self.services.email, self)
        if dialog.exec():
            self.apply_appearance()
