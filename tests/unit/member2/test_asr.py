import json

import pytest

from nexa.asr import benchmark, hardware, model_registry
from nexa.asr.service import FakeTranscriptionService, TranscriptionServiceImpl
from nexa.asr.transcript import build_transcript, language_hint, merge_transcripts
from nexa.audio.wav_utils import write_wav
from nexa.contracts import Transcript, TranscriptionService
from nexa.contracts.audio import RecordedAudio

from .test_audio_utils import tone


class ScriptedEngine:
    """Returns canned text per audio filename; counts calls."""

    def __init__(self, name: str, answers: dict[str, str]):
        self.name = name
        self._answers = answers
        self.calls = 0
        self.loaded = False
        self.closed = False

    def load(self):
        self.loaded = True

    def close(self):
        self.closed = True

    def transcribe(self, audio_path: str):
        self.calls += 1
        text = self._answers[audio_path.rsplit("/", 1)[-1].removesuffix(".wav")]
        return build_transcript([(0.0, 1.0, text)], model_name=self.name, duration_ms=1000)


def make_dataset(root):
    spec = {
        "arabic/a1": ("أحمد يخلص التقرير يوم الخميس", {"keywords": ["التقرير"], "date_phrases": ["يوم الخميس"]}),
        "mixed/m1": ("الـpresentation Thursday الساعة three", {"english_terms": ["presentation"], "date_phrases": ["thursday الساعه 3"]}),
        "mixed/m2": ("بكرة عندنا meeting", {"english_terms": ["meeting"]}),
    }
    for rel, (ref, meta) in spec.items():
        wav = root / f"{rel}.wav"
        write_wav(wav, tone(1.0))
        wav.with_suffix(".txt").write_text(ref, encoding="utf-8")
        wav.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    write_wav(root / "mixed" / "no_reference.wav", tone(0.5))  # must be skipped
    return spec


def test_load_dataset_reads_refs_meta_and_skips_unlabelled(tmp_path):
    make_dataset(tmp_path)
    clips = benchmark.load_dataset(tmp_path)
    assert [c.name for c in clips] == ["arabic/a1", "mixed/m1", "mixed/m2"]
    assert clips[1].english_terms == ("presentation",)
    assert benchmark.load_dataset(tmp_path, categories=["arabic"])[0].category == "arabic"


def test_benchmark_pools_metrics_and_ranks_models(tmp_path):
    make_dataset(tmp_path)
    clips = benchmark.load_dataset(tmp_path)
    perfect = ScriptedEngine("good", {
        "a1": "أحمد يخلص التقرير يوم الخميس",
        "m1": "الـpresentation Thursday الساعة 3",
        "m2": "بكرة عندنا meeting",
    })
    weak = ScriptedEngine("weak", {
        "a1": "أحمد يخلص التقرير الخميس",           # loses "يوم"
        "m1": "البريزنتيشن الخميس الساعة تلاتة",     # transliterated -> EN term + date phrase missed
        "m2": "بكرة عندنا ميتينج",
    })
    results, stats = benchmark.run_benchmark({"good": lambda: perfect, "weak": lambda: weak}, clips)
    assert perfect.loaded and perfect.closed
    assert perfect.calls == len(clips) + 1  # + one untimed warm-up
    assert len(results) == 2 * len(clips)  # warm-up is not scored

    by = {(s.model, s.category): s for s in benchmark.summarize(results, stats)}
    assert by[("good", "ALL")].wer == 0.0
    assert by[("good", "ALL")].term_acc == 1.0 and by[("good", "ALL")].date_acc == 1.0
    assert by[("weak", "ALL")].wer > 0.3
    assert by[("weak", "mixed")].term_acc == 0.0
    assert by[("weak", "arabic")].date_acc == 0.0  # "يوم الخميس" lost its "يوم"
    assert by[("good", "mixed")].clips == 2


def test_summary_uses_corpus_level_wer_not_mean_of_clip_wers():
    def row(errors, words):
        return benchmark.ClipResult("m", "c", "x", "", errors, words, 0, 1, 0, 0, 0, 0, 0, 0, 1.0, 1.0)

    # clip A: 1/1 wrong (100%), clip B: 0/99 wrong -> corpus WER is 1%, not 50%
    s = benchmark.summarize([row(1, 1), row(0, 99)])[-1]
    assert s.wer == pytest.approx(0.01)


def test_format_table_and_csv(tmp_path):
    make_dataset(tmp_path)
    clips = benchmark.load_dataset(tmp_path)
    eng = ScriptedEngine("e", {"a1": "x", "m1": "y", "m2": "z"})
    results, stats = benchmark.run_benchmark({"e": lambda: eng}, clips)
    table = benchmark.format_table(benchmark.summarize(results, stats))
    assert table.splitlines()[0].startswith("| model |") and "| e | ALL |" in table
    out = tmp_path / "out" / "results.csv"
    benchmark.write_results_csv(results, out)
    assert "hypothesis" in out.read_text(encoding="utf-8-sig").splitlines()[0]


def test_language_hint():
    assert language_hint("أحمد يخلص التقرير") == "ar"
    assert language_hint("finish the report") == "en"
    assert language_hint("أحمد يخلص الـbackend before Monday") == "mixed"
    assert language_hint("123 ...") is None


def test_build_transcript_drops_empty_segments_and_reindexes():
    t = build_transcript([(0, 1, " hello "), (1, 2, "  "), (2, 3.5, "world")], "m")
    assert [s.segment_index for s in t.segments] == [0, 1]
    assert t.segments[1].start_ms == 2000 and t.duration_ms == 3500
    assert t.full_text == "hello world"


def test_confirmed_text_takes_priority_but_raw_is_kept():
    seg = build_transcript([(0, 1, "raw wording")], "m").segments[0]
    from dataclasses import replace

    edited = replace(seg, confirmed_text="admin corrected")
    assert Transcript(segments=(edited,)).full_text == "admin corrected"
    assert edited.raw_text == "raw wording"


def test_transcribe_chunks_offsets_timestamps_onto_one_timeline(tmp_path):
    p1, p2 = tmp_path / "c1.wav", tmp_path / "c2.wav"
    write_wav(p1, tone(2.0))
    write_wav(p2, tone(1.0))

    class Eng:
        def transcribe(self, path):
            return build_transcript([(0.5, 1.0, path[-6:-4])], "m", duration_ms=2000 if "c1" in path else 1000)

    svc = TranscriptionServiceImpl(Eng())
    out = svc.transcribe_chunks(RecordedAudio(str(tmp_path / "all.wav"), 3000, chunk_paths=(str(p1), str(p2))))
    assert [(s.raw_text, s.start_ms) for s in out.segments] == [("c1", 500), ("c2", 2500)]
    assert [s.segment_index for s in out.segments] == [0, 1]
    assert out.duration_ms == 3000


def test_merge_transcripts_empty():
    assert merge_transcripts([]).segments == ()


def test_fake_service_satisfies_contract():
    assert isinstance(FakeTranscriptionService(), TranscriptionService)
    assert isinstance(TranscriptionServiceImpl(FakeTranscriptionService()), TranscriptionService)


def test_model_registry_resolves_keys_and_custom_paths():
    assert model_registry.resolve_model("whisper-small").model_id == "small"
    assert model_registry.resolve_model("models/whisper/egy-ct2").model_id == "models/whisper/egy-ct2"
    model_registry.register("egy-test", "some/repo", "x")
    assert model_registry.resolve_model("egy-test").model_id == "some/repo"


def test_detect_hardware_falls_back_to_cpu_int8():
    hw = hardware.detect_hardware(force_cpu=True)
    assert (hw.device, hw.compute_type) == ("cpu", "int8")
