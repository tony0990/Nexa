class MeetingViewModel:
    TEMPLATES = {
        "Weekly Team Meeting": {
            "title": "Weekly Development Meeting",
            "source": "mic+computer",
            "participants": "Ahmed Hassan, Maria Adel",
        },
        "Project Review": {
            "title": "Project Review",
            "source": "mic",
            "participants": "Maria Adel, John Peter",
        },
        "Management Meeting": {
            "title": "Management Meeting",
            "source": "mic+computer",
            "participants": "Maria Adel",
        },
        "HR Meeting": {
            "title": "HR Meeting",
            "source": "computer",
            "participants": "John Peter",
        },
        "Department Stand-up": {
            "title": "Department Stand-up",
            "source": "mic",
            "participants": "Ahmed Hassan, Maria Adel, John Peter",
        },
        "Custom": {
            "title": "",
            "source": "mic+computer",
            "participants": "",
        },
    }

    def __init__(self, audio, transcription, extraction) -> None:
        self.audio = audio
        self.transcription = transcription
        self.extraction = extraction
        self.elapsed = 0
        self.candidates = []
        self.transcript = None

    def apply_template(self, name: str) -> dict:
        return dict(self.TEMPLATES.get(name, self.TEMPLATES["Custom"]))

    def start(self, source: str) -> None:
        self.elapsed = 0
        self.audio.start(source)

    def pause(self) -> None:
        self.audio.pause()

    def resume(self) -> None:
        self.audio.resume()

    def stop(self):
        recorded = self.audio.stop()
        self.transcript = self.transcription.transcribe(recorded.path)
        self.candidates = self.extraction.extract(self.transcript)
        return self.transcript, self.candidates
