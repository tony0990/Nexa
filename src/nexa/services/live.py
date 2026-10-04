"""Live transcription: speech appears while the meeting is still being recorded.

Member 2's recorder writes rolling WAV chunks and only *closes* a chunk when it
opens the next one. So a chunk that has a later sibling in its folder is complete
and safe to read, while the newest one is still being written. `LiveTranscriber`
polls for newly closed chunks, runs ASR on each in a background thread and hands
the text to a callback.

This is a preview, and is treated as one:

* For a single source (mic only, or computer audio only) the closed chunks ARE
  the final chunks, so their transcripts are kept in `results` and reused when the
  meeting ends — nothing is transcribed twice.
* For mic+computer the recorder mixes the two streams into *different* files at
  the end. The per-source live text is still useful on screen, but the final
  transcript is made from the mixed chunks.

No Qt in here. The window wraps the callback in a signal, which keeps this
testable without a display and keeps threads out of widget code.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

log = logging.getLogger("nexa.live")

_CHUNK_NUMBER = re.compile(r"_(\d+)\.wav$")

#: Called with (source, chunk_path, text) for each newly transcribed chunk.
TextCallback = Callable[[str, str, str], None]
ErrorCallback = Callable[[str], None]


def closed_chunks(workdir: Optional[Path]) -> List[tuple]:
    """`(source, path)` for every chunk that has finished being written.

    A chunk is closed once a higher-numbered file exists beside it: the writer
    only opens chunk N+1 after closing chunk N. The highest-numbered file in each
    folder is therefore always skipped — it is still open.
    """
    if workdir is None or not Path(workdir).is_dir():
        return []
    found: List[tuple] = []
    for source in ("mic", "loop"):
        folder = Path(workdir) / source
        if not folder.is_dir():
            continue
        files = sorted(folder.glob(f"{source}_*.wav"))
        for path in files[:-1]:
            found.append((source, path))
    return found


class LiveTranscriber:
    """Transcribes closed chunks in the background while recording continues."""

    def __init__(
        self,
        transcribe: Callable[[str], object],
        workdir: Callable[[], Optional[Path]],
        on_text: TextCallback,
        on_error: Optional[ErrorCallback] = None,
        poll_seconds: float = 1.0,
    ) -> None:
        self._transcribe = transcribe
        self._workdir = workdir
        self._on_text = on_text
        self._on_error = on_error
        self._poll = poll_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._done: set = set()
        self.results: Dict[str, object] = {}

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._done.clear()
        self.results = {}
        self._thread = threading.Thread(target=self._run, name="nexa-live-asr", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 120.0) -> None:
        """Stop polling and wait for any chunk already being transcribed."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        self._thread = None

    # --------------------------------------------------------------------- loop
    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self._poll)

    def poll_once(self) -> int:
        """Transcribe every newly closed chunk; returns how many were done."""
        count = 0
        for source, path in closed_chunks(self._workdir()):
            key = str(path)
            if key in self._done:
                continue
            if self._stop.is_set():
                break
            self._done.add(key)  # before the work: a failure must not retry forever
            try:
                transcript = self._transcribe(key)
            except Exception as exc:  # noqa: BLE001 - a bad chunk must not end the preview
                log.exception("live transcription failed for %s", key)
                if self._on_error:
                    self._on_error(f"{type(exc).__name__}: {exc}")
                continue
            self.results[key] = transcript
            text = getattr(transcript, "full_text", "") or ""
            if text.strip():
                self._on_text(source, key, text.strip())
            count += 1
        return count
