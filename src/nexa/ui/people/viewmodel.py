class PeopleViewModel:
    def __init__(self, people) -> None:
        self.people = people
        self.query = ""
        self.active = "all"

    def employees(self):
        return self.people.list_employees(self.query, self.active)

    def roles(self):
        return self.people.list_roles()
