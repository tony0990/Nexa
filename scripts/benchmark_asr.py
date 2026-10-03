"""Compare candidate STT models on the labelled clip set.

    python scripts/benchmark_asr.py --dataset tests/audio
    python scripts/benchmark_asr.py --dataset tests/audio --models whisper-small whisper-medium \
        --languages auto ar --out benchmark_out

Needs: pip install -r requirements/base.txt -r requirements/ai.txt
Outputs (in --out): summary.md, results.csv (per-clip, includes each hypothesis).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nexa.asr.benchmark import format_table, load_dataset, run_benchmark, summarize, write_results_csv  # noqa: E402
from nexa.asr.faster_whisper_engine import FasterWhisperEngine  # noqa: E402
from nexa.asr.hardware import detect_hardware  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", default="tests/audio", help="folder with <category>/<clip>.wav + .txt")
    p.add_argument("--models", nargs="+", default=["whisper-small", "whisper-medium"],
                   help="registry keys, or a path/HF repo id (CTranslate2 format)")
    p.add_argument("--languages", nargs="+", default=["auto"],
                   help="auto | ar | en. Each model is run once per value (auto = Whisper detects)")
    p.add_argument("--categories", nargs="+", help="only these category folders")
    p.add_argument("--prompt", help="initial_prompt to bias code-switching, e.g. a mixed AR/EN sentence")
    p.add_argument("--cpu", action="store_true", help="force CPU")
    p.add_argument("--int8", action="store_true", help="int8_float16 on GPU (saves VRAM)")
    p.add_argument("--limit", type=int, help="only the first N clips (smoke test)")
    p.add_argument("--out", default="benchmark_out")
    args = p.parse_args()

    clips = load_dataset(args.dataset, args.categories)
    if args.limit:
        clips = clips[: args.limit]
    if not clips:
        print(f"No clips with a .txt reference found under {args.dataset}", file=sys.stderr)
        return 1

    hardware = detect_hardware(prefer_int8=args.int8, force_cpu=args.cpu)
    print(f"{len(clips)} clips | device={hardware.device} compute={hardware.compute_type}")

    factories = {}
    for model in args.models:
        for lang in args.languages:
            language = None if lang == "auto" else lang
            engine = FasterWhisperEngine(model, hardware=hardware, language=language, initial_prompt=args.prompt)
            factories[engine.name] = lambda e=engine: e

    results, stats = run_benchmark(factories, clips, progress=lambda m: print(f"  {m}", flush=True))
    summaries = summarize(results, stats)
    table = format_table(summaries)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(table + "\n", encoding="utf-8")
    write_results_csv(results, out / "results.csv")
    print("\n" + table)
    print(f"\nWrote {out / 'summary.md'} and {out / 'results.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
