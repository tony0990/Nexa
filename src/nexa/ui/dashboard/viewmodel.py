class DashboardViewModel:
    def __init__(self, reminder_service) -> None:
        self.reminders = reminder_service

    def counts(self) -> dict:
        return self.reminders.dashboard_counts()
