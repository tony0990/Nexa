from nexa.contracts.models import ActionCandidate


class ReviewViewModel:
    def __init__(self) -> None:
        self.meeting_title = "Weekly Development Meeting"
        self.transcript_text = ""
        self.items: list[ActionCandidate] = []
        self.participants: list[str] = []

    def set_result(self, title, transcript, candidates, participants=None) -> None:
        self.meeting_title = title
        self.transcript_text = transcript.confirmed_text
        self.items = list(candidates)
        self.participants = [p.strip() for p in (participants or []) if str(p).strip()]

    def remove(self, item_id: int) -> None:
        self.items = [i for i in self.items if i.id != item_id]

    def merge(self, duplicate_id: int, target_id: int) -> None:
        self.items = [i for i in self.items if i.id != duplicate_id]
