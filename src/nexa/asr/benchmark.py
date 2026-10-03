"""Benchmark harness: run candidate STT engines over a labelled clip set and compare.

Dataset layout (matches the plan's tests/audio/ tree):

    tests/audio/<category>/<clip>.wav      audio (any 16-bit PCM WAV rate/channels)
    tests/audio/<category>/<clip>.txt      reference transcript, exactly as it should read
    tests/audio/<category>/<clip>.json     optional, see below

    {"keywords":      ["database", "backend"],      # task keywords that must survive
     "date_phrases":  ["الخميس الساعة 3", "Monday"], # date/time phrases that must survive
     "english_terms": ["presentation", "budget"],    # English words inside Arabic speech
     "speaker":       "yousef"}

<category> is usually arabic / english / mixed / noisy / long. Metrics are pooled per
(model, category) and overall.
"""
from __future__ import annotations

import csv
import json
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..audio.wav_utils import wav_duration_ms
from ..contracts.transcription import Transcript
from . import metrics


@dataclass(frozen=True)
class Clip:
    audio_path: Path
    category: str
    reference: str
    keywords: tuple[str, ...] = ()
    date_phrases: tuple[str, ...] = ()
    english_terms: tuple[str, ...] = ()
    speaker: str = ""

    @property
    def name(self) -> str:
        return f"{self.category}/{self.audio_path.stem}"


def load_dataset(root: str | Path, categories: Iterable[str] | None = None) -> list[Clip]:
    """Load every <clip>.wav that has a <clip>.txt reference next to it."""
    root = Path(root)
    wanted = set(categories) if categories else None
    clips: list[Clip] = []
    for wav in sorted(root.rglob("*.wav")):
        category = wav.parent.name
        ref_path = wav.with_suffix(".txt")
        if (wanted and category not in wanted) or not ref_path.exists():
            continue
        meta: dict = {}
        if wav.with_suffix(".json").exists():
            meta = json.loads(wav.with_suffix(".json").read_text(encoding="utf-8"))
        clips.append(
            Clip(
                audio_path=wav,
                category=category,
                reference=ref_path.read_text(encoding="utf-8").strip(),
                keywords=tuple(meta.get("keywords", ())),
                date_phrases=tuple(meta.get("date_phrases", ())),
                english_terms=tuple(meta.get("english_terms", ())),
                speaker=str(meta.get("speaker", "")),
            )
        )
    return clips


class Engine:  # documentation only: what the harness needs from an engine
    name: str

    def transcribe(self, audio_path: str) -> Transcript: ...


EngineFactory = Callable[[], "Engine"]


@dataclass
class ClipResult:
    model: str
    category: str
    clip: str
    hypothesis: str
    word_errors: int
    ref_words: int
    char_errors: int
    ref_chars: int
    keyword_found: int
    keyword_total: int
    date_found: int
    date_total: int
    term_found: int
    term_total: int
    seconds: float
    audio_seconds: float


@dataclass
class ModelStats:
    load_seconds: float = 0.0
    ram_mb: float | None = None  # RSS growth from loading the model
    peak_rss_mb: float | None = None


@dataclass
class Summary:
    model: str
    category: str
    clips: int
    wer: float
    cer: float
    keyword_acc: float | None
    date_acc: float | None
    term_acc: float | None
    rtf: float  # real-time factor: processing seconds per audio second (lower = faster)
    load_seconds: float = 0.0
    ram_mb: float | None = None
    extra: dict = field(default_factory=dict)


def _rss_mb() -> float | None:
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:  # noqa: BLE001 - psutil is optional
        return None


def evaluate_clip(model: str, clip: Clip, transcript: Transcript, seconds: float) -> ClipResult:
    hyp = transcript.full_text
    we, wn = metrics.word_errors(clip.reference, hyp)
    ce, cn = metrics.char_errors(clip.reference, hyp)
    kf, kt = metrics.phrase_hits(clip.keywords, hyp)
    df, dt = metrics.phrase_hits(clip.date_phrases, hyp)
    tf, tt = metrics.phrase_hits(clip.english_terms, hyp)
    return ClipResult(
        model=model, category=clip.category, clip=clip.name, hypothesis=hyp,
        word_errors=we, ref_words=wn, char_errors=ce, ref_chars=cn,
        keyword_found=kf, keyword_total=kt, date_found=df, date_total=dt,
        term_found=tf, term_total=tt,
        seconds=seconds, audio_seconds=wav_duration_ms(clip.audio_path) / 1000,
    )


def run_benchmark(
    factories: dict[str, EngineFactory],
    clips: list[Clip],
    progress: Callable[[str], None] = lambda _msg: None,
) -> tuple[list[ClipResult], dict[str, ModelStats]]:
    """Run every engine over every clip. Engines are created one at a time so only one
    model is in memory at once (keeps RAM numbers meaningful)."""
    results: list[ClipResult] = []
    stats: dict[str, ModelStats] = {}
    for label, factory in factories.items():
        progress(f"loading {label}")
        rss_before = _rss_mb()
        t0 = time.perf_counter()
        engine = factory()
        if hasattr(engine, "load"):
            engine.load()
        stat = ModelStats(load_seconds=time.perf_counter() - t0)
        rss_after = _rss_mb()
        if rss_before is not None and rss_after is not None:
            stat.ram_mb = rss_after - rss_before
        peak = rss_after or 0.0

        if clips:  # warm-up (GPU init, caches) - not timed, not scored
            engine.transcribe(str(clips[0].audio_path))
        for i, clip in enumerate(clips, start=1):
            progress(f"{label}: {i}/{len(clips)} {clip.name}")
            t = time.perf_counter()
            transcript = engine.transcribe(str(clip.audio_path))
            elapsed = time.perf_counter() - t
            results.append(evaluate_clip(label, clip, transcript, elapsed))
            peak = max(peak, _rss_mb() or 0.0)
        stat.peak_rss_mb = peak or None
        stats[label] = stat
        if hasattr(engine, "close"):
            engine.close()
    return results, stats


def _ratio(found: int, total: int) -> float | None:
    return found / total if total else None


def summarize(results: list[ClipResult], stats: dict[str, ModelStats] | None = None) -> list[Summary]:
    """Pool per (model, category) plus an ALL row per model. WER/CER are corpus-level."""
    stats = stats or {}
    out: list[Summary] = []
    models = list(dict.fromkeys(r.model for r in results))
    for model in models:
        mine = [r for r in results if r.model == model]
        categories = list(dict.fromkeys(r.category for r in mine)) + ["ALL"]
        for category in categories:
            rows = mine if category == "ALL" else [r for r in mine if r.category == category]
            ref_words = sum(r.ref_words for r in rows)
            ref_chars = sum(r.ref_chars for r in rows)
            audio_s = sum(r.audio_seconds for r in rows)
            stat = stats.get(model, ModelStats())
            out.append(
                Summary(
                    model=model,
                    category=category,
                    clips=len(rows),
                    wer=sum(r.word_errors for r in rows) / ref_words if ref_words else 0.0,
                    cer=sum(r.char_errors for r in rows) / ref_chars if ref_chars else 0.0,
                    keyword_acc=_ratio(sum(r.keyword_found for r in rows), sum(r.keyword_total for r in rows)),
                    date_acc=_ratio(sum(r.date_found for r in rows), sum(r.date_total for r in rows)),
                    term_acc=_ratio(sum(r.term_found for r in rows), sum(r.term_total for r in rows)),
                    rtf=sum(r.seconds for r in rows) / audio_s if audio_s else 0.0,
                    load_seconds=stat.load_seconds,
                    ram_mb=stat.ram_mb,
                )
            )
    return out


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def format_table(summaries: list[Summary]) -> str:
    header = "| model | category | clips | WER | CER | keywords | dates | EN terms | RTF | load s | RAM MB |"
    sep = "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    lines = [header, sep]
    for s in summaries:
        ram = "-" if s.ram_mb is None else f"{s.ram_mb:.0f}"
        lines.append(
            f"| {s.model} | {s.category} | {s.clips} | {_pct(s.wer)} | {_pct(s.cer)} | "
            f"{_pct(s.keyword_acc)} | {_pct(s.date_acc)} | {_pct(s.term_acc)} | "
            f"{s.rtf:.2f} | {s.load_seconds:.1f} | {ram} |"
        )
    return "\n".join(lines)


def write_results_csv(results: list[ClipResult], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel opens Arabic correctly
        writer = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()) if results else ["model"])
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))
