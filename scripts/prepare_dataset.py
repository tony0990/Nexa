"""Create the reference files for one speaker's recording pack.

    python scripts/prepare_dataset.py --speaker yousef

Creates, under tests/audio/<category>/:
    <speaker>_<id>.txt     the sentence to read (also the reference transcript)
    <speaker>_<id>.json    keywords / date phrases / English terms / speaker
and prints + writes a checklist of the .wav files to record next to them.

Per speaker: 10 Arabic + 10 English + 15 mixed + 5 noisy = 40 clips (x6 people = 240).
Record as mono 16-bit WAV (phone .m4a/.mp3: `ffmpeg -i in.m4a -ac 1 -ar 16000 out.wav`),
named exactly like the .txt (e.g. yousef_mx03.wav).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PROMPTS = Path(__file__).resolve().parents[1] / "docs" / "recording_prompts.json"


def write_clip(out: Path, category: str, speaker: str, clip_id: str, prompt: dict) -> Path:
    folder = out / category
    folder.mkdir(parents=True, exist_ok=True)
    stem = folder / f"{speaker}_{clip_id}"
    stem.with_suffix(".txt").write_text(prompt["text"] + "\n", encoding="utf-8")
    meta = {k: prompt.get(k, []) for k in ("keywords", "date_phrases", "english_terms")}
    meta["speaker"] = speaker
    stem.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stem.with_suffix(".wav")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--speaker", required=True, help="short lowercase name, letters/digits only")
    p.add_argument("--out", default="tests/audio")
    args = p.parse_args()
    if not re.fullmatch(r"[a-z0-9]+", args.speaker):
        p.error("--speaker must be lowercase letters/digits only (it becomes part of the filename)")

    data = json.loads(PROMPTS.read_text(encoding="utf-8"))
    out = Path(args.out)
    mixed = {c["id"]: c for c in data["mixed"]}

    todo: list[tuple[str, Path, str]] = []  # (category, wav path, sentence)
    for category in ("arabic", "english", "mixed"):
        for prompt in data[category]:
            todo.append((category, write_clip(out, category, args.speaker, prompt["id"], prompt), prompt["text"]))
    for i, mixed_id in enumerate(data["noisy_from_mixed"], start=1):
        prompt = mixed[mixed_id]
        wav = write_clip(out, "noisy", args.speaker, f"nz{i:02d}", prompt)
        todo.append(("noisy (record somewhere noisy)", wav, prompt["text"]))

    lines = [f"# Recording checklist - {args.speaker}", ""]
    lines += [f"- [ ] `{wav.relative_to(out) if wav.is_relative_to(out) else wav}` - {cat}: {text}" for cat, wav, text in todo]
    checklist = out / f"RECORD_{args.speaker}.md"
    checklist.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(todo)} reference files under {out}/ and the checklist {checklist}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
