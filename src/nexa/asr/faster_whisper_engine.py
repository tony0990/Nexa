"""faster-whisper transcription engine (implements the `TranscriptionService` contract).

Not exercised by the unit tests (needs the model download); the benchmark notebook
runs it for real.

Knobs worth benchmarking for Egyptian Arabic / English code-switching:
  * `language`: None lets Whisper auto-detect ONCE per file, which can lock a mixed
    clip to one language. Forcing "ar" often keeps the Arabic right but may
    transliterate English words into Arabic script. Compare None / "ar" / "en".
  * `initial_prompt`: a short mixed-language sentence can bias Whisper towards
    keeping English technical words in Latin script.
"""
from __future__ import annotations

from ..contracts.transcription import Transcript
from .hardware import HardwareProfile, detect_hardware
from .model_registry import ModelSpec, resolve_model
from .transcript import build_transcript


class FasterWhisperEngine:
    def __init__(
        self,
        model: str | ModelSpec,
        hardware: HardwareProfile | None = None,
        language: str | None = None,
        initial_prompt: str | None = None,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> None:
        self.spec = resolve_model(model) if isinstance(model, str) else model
        self.hardware = hardware or detect_hardware()
        self.language = language
        self.initial_prompt = initial_prompt
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self._model = None

    @property
    def name(self) -> str:
        lang = self.language or "auto"
        return f"{self.spec.key}[{lang}]"

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel  # heavy import, kept lazy

        self._model = WhisperModel(
            self.spec.model_id,
            device=self.hardware.device,
            compute_type=self.hardware.compute_type,
        )

    def close(self) -> None:
        self._model = None

    def transcribe(self, audio_path: str) -> Transcript:
        self.load()
        assert self._model is not None
        segments, info = self._model.transcribe(
            audio_path,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
            initial_prompt=self.initial_prompt,
            condition_on_previous_text=False,  # avoids repetition loops on long audio
        )
        # `segments` is a lazy generator: iterating it is what actually runs the model.
        raw = [(s.start, s.end, s.text) for s in segments]
        return build_transcript(raw, model_name=self.name, duration_ms=int(info.duration * 1000))
