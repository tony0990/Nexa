class SearchViewModel:
    CATEGORIES = ["all", "employees", "meetings", "tasks"]
    TASK_STATUSES = ["all", "PENDING", "OVERDUE", "COMPLETED", "unassigned", "SNOOZED"]
    MEETING_STATUSES = ["all", "APPROVED", "PENDING_REVIEW", "DRAFT"]
    EMPLOYEE_ACTIVE = ["all", "active", "inactive"]

    def __init__(self, search_service) -> None:
        self.search_service = search_service
        self.category = "all"
        self.task_status = "all"
        self.meeting_status = "all"
        self.employee_active = "all"

    def search(self, query: str) -> dict:
        empty = {"employees": [], "meetings": [], "tasks": []}
        if not query.strip():
            return empty
        task_filters = None if self.task_status == "all" else {"status": self.task_status}
        meeting_filters = None if self.meeting_status == "all" else {"status": self.meeting_status}
        employee_filters = None if self.employee_active == "all" else {"active": self.employee_active}
        if self.category == "employees":
            return {
                "employees": self.search_service.search_employees(query, employee_filters),
                "meetings": [],
                "tasks": [],
            }
        if self.category == "meetings":
            return {
                "employees": [],
                "meetings": self.search_service.search_meetings(query, meeting_filters),
                "tasks": [],
            }
        if self.category == "tasks":
            return {"employees": [], "meetings": [], "tasks": self.search_service.search_tasks(query, task_filters)}
        result = self.search_service.global_search(query)
        if employee_filters:
            result["employees"] = self.search_service.search_employees(query, employee_filters)
        if meeting_filters:
            result["meetings"] = self.search_service.search_meetings(query, meeting_filters)
        if task_filters:
            result["tasks"] = self.search_service.search_tasks(query, task_filters)
        return result
