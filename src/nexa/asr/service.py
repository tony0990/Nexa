"""Public TranscriptionService implementation + a fake for other members' tests.

Other modules must depend on `contracts.TranscriptionService`, never on the engine.
"""
from __future__ import annotations

from typing import Protocol

from ..audio.wav_utils import wav_duration_ms
from ..contracts.audio import RecordedAudio
from ..contracts.transcription import Transcript, TranscriptSegment
from .transcript import language_hint, merge_transcripts


class TranscriptionEngine(Protocol):
    """Anything that can turn one audio file into a Transcript."""

    def transcribe(self, audio_path: str) -> Transcript: ...


class TranscriptionServiceImpl:
    def __init__(self, engine: TranscriptionEngine) -> None:
        self._engine = engine

    def transcribe(self, audio_path: str) -> Transcript:
        return self._engine.transcribe(audio_path)

    def transcribe_chunks(self, audio: RecordedAudio) -> Transcript:
        """Transcribe each chunk and stitch segment timestamps onto one timeline."""
        paths = list(audio.chunk_paths) or [audio.path]
        parts: list[tuple[int, Transcript]] = []
        offset_ms = 0
        for path in paths:
            parts.append((offset_ms, self._engine.transcribe(path)))
            offset_ms += wav_duration_ms(path)
        return merge_transcripts(parts)


def create_transcription_service(model: str = "whisper-small", **engine_kwargs) -> TranscriptionServiceImpl:
    """Convenience factory: `create_transcription_service("whisper-medium", language="ar")`."""
    from .faster_whisper_engine import FasterWhisperEngine

    return TranscriptionServiceImpl(FasterWhisperEngine(model, **engine_kwargs))


class FakeTranscriptionService:
    """For Members 3 and 6: returns a canned transcript, no audio or model needed."""

    def __init__(self, text: str = "أحمد يخلص الـdatabase before Monday") -> None:
        self._text = text

    def _make(self) -> Transcript:
        hint = language_hint(self._text)
        seg = TranscriptSegment(segment_index=0, start_ms=0, end_ms=5000, raw_text=self._text, language_hint=hint)
        return Transcript(segments=(seg,), language_hint=hint, model_name="fake", duration_ms=5000)

    def transcribe(self, audio_path: str) -> Transcript:
        return self._make()

    def transcribe_chunks(self, audio: RecordedAudio) -> Transcript:
        return self._make()
