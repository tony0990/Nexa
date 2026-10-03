# Member 2 - Audio capture, STT & benchmarking

Status: code + unit tests done (85 passing, no GPU/Windows needed). **Not yet run:** real
Windows capture, real Whisper transcription, the benchmark on real clips.

## What exists

| Area | Files | Tested how |
|---|---|---|
| Contracts (additive extensions of the kickoff version) | `contracts/audio.py`, `contracts/transcription.py` | used by everything below |
| WAV/resample/mix/chunks/VAD | `audio/wav_utils.py`, `mixer.py`, `chunks.py`, `vad.py` | unit tests, synthetic audio |
| Recorder (mic / computer / both, pause, crash recovery) | `audio/recorder.py` | unit tests with fake capture streams |
| Windows hardware layer | `audio/capture.py`, `microphone.py`, `loopback.py`, `devices.py` | **UNTESTED** - see `member2-test-checklist.md` |
| STT engine + service | `asr/faster_whisper_engine.py`, `service.py`, `model_registry.py`, `hardware.py` | service/registry unit-tested; engine needs the model |
| Metrics + benchmark | `asr/metrics.py`, `asr/benchmark.py`, `scripts/benchmark_asr.py` | unit tests with scripted engines |
| Dataset tooling | `scripts/prepare_dataset.py`, `docs/recording_prompts.json` | unit tests + smoke run |
| GPU run | `notebooks/benchmark_asr_colab.ipynb` | not run |

## Run the tests

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements/dev.txt numpy
.venv/bin/python -m pytest tests/unit/member2 -q
```

(No torch/faster-whisper needed locally - keeps the MacBook light.)

## Workflow to finish the task

1. **Each of the 6 people** runs `python scripts/prepare_dataset.py --speaker <name>`, records the 40 clips listed in
   `tests/audio/RECORD_<name>.md` (mono 16-bit WAV, named exactly like the `.txt`), and shares them.
   Phone recordings: `ffmpeg -i in.m4a -ac 1 -ar 16000 out.wav`.
2. Put everything in one `tests/audio/` tree (or `MyDrive/Nexa/audio/` for Colab).
3. Run `notebooks/benchmark_asr_colab.ipynb` (or `scripts/benchmark_asr.py` on the ROG).
4. Read `results.csv` hypotheses for the worst clips, then choose the production model and write it up.
5. Do the Windows checklist for the recorder.

## Decisions you own

- **`asr/metrics.py`** decides what "best" means. Review the normalization (Arabic letter variants, weekday/number
  spelling equivalence, splitting `الـbackend` into `ال backend`). Extend `_AR_EQUIVALENTS` only from mistakes you
  actually see in the results.
- **Language setting.** The benchmark runs each model with `auto` and forced `ar`. Auto locks a mixed clip to one
  language; forced Arabic may transliterate English words. This comparison is probably the most important result.
- **Egyptian code-switch fine-tune.** No checkpoint is hard-coded because none was verified. Pick one, convert it
  (`ct2-transformers-converter`, see notebook), add it to `--models`.
- **Contracts.** Member 2's changes to `contracts/audio.py` and `contracts/transcription.py` are additive only:
  every kickoff field is kept, segments are the shared `meetings.TranscriptSegment` (so they save straight through
  Member 1's repository), and `Recorder.start` still accepts the plain `"MICROPHONE"`/`"COMPUTER"`/`"BOTH"` string.
  Added: `AudioDevice`, `SourceConfig`, `AudioDeviceService`, `RecordedAudio.chunk_paths`, `Transcript.duration_ms`,
  `pause`/`resume`/`transcribe_chunks` on the protocols. The plan says the whole team approves contract changes.

## Known limitations

- Pause drops audio, so transcript time skips the paused span.
- Block-by-block resampling (box filter + linear interpolation) is numpy-only; swap in `scipy.signal.resample_poly`
  if benchmarks suggest resampling hurts accuracy.
- RAM figure = RSS growth from loading the model, an approximation. `psutil` is needed for it (in `requirements/ai.txt`).
- Speaker diarization is not implemented (out of the plan's Member 2 scope, but the extractor's owner detection
  would benefit; raise it with Member 3).
