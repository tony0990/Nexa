import logging
import time
from typing import Optional

# Setup logging for LLM runtime incidents (§6)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_runtime")

class LLMRuntime:
    """
    Llama.cpp process lifecycle & call wrapper (§4).

    Design requirements:
    - Single long-lived process (avoid startup cost per call).
    - Support for GBNF grammar-constrained decoding (primary defense vs prose).
    - Deterministic mode (temp=0) for tests.
    """

    def __init__(self, model_path: str, n_ctx: int = 2048, n_threads: int = 4, timeout_s: int = 30):
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.timeout_s = timeout_s
        self._is_running = False
        self._process = None  # This would be the llama-cpp-python instance or subprocess

    def start(self) -> None:
        """Spins up the llama.cpp process/binding."""
        logger.info(f"Initializing LLM runtime with model: {self.model_path}")
        self._is_running = True
        logger.info("LLM runtime ready.")

    def is_ready(self) -> bool:
        """Checks if the model is loaded and available."""
        return self._is_running

    def complete(self, prompt: str, *, temperature: float = 0.0, max_tokens: int = 512,
                 grammar: Optional[str] = None) -> str:
        """
        Performs a completion call.
        """
        if not self._is_running:
            raise RuntimeError("LLMRuntime must be started via start() before calling complete().")

        # Mock implementation for the demo to return a valid extraction.
        #
        # Keyed on the SEGMENT, not the whole prompt. The prompt ends with the
        # few-shot library from prompts.py, whose examples contain "أحمد",
        # "سارة" and "John" — so matching against `prompt` made every one of
        # those branches true on every call, and the mock returned the same
        # canned action item for any input, including the zero-action fixtures
        # the precision guardrail exists to protect.
        segment = _segment_under_extraction(prompt)

        if "أحمد" in segment:
            return '{"items": [{"task": "تخلص الـ report", "owner_text": "أحمد", "raw_date_phrase": "بكرة", "raw_time_phrase": "الساعة 10 الصبح", "confidence": 0.9, "needs_review": false, "evidence_text": "أحمد، لازم تخلص الـ report بكرة الساعة 10 الصبح", "evidence_span": [0, 45], "extraction_id": "uuid-1"}]}'
        if "سارة" in segment:
            return '{"items": [{"task": "ابعتي الإيميل للعميل", "owner_text": "سارة", "raw_date_phrase": "يوم الحد", "raw_time_phrase": null, "confidence": 0.9, "needs_review": false, "evidence_text": "سارة، ابعتي الإيميل للعميل يوم الحد", "evidence_span": [0, 30], "extraction_id": "uuid-2"}]}'
        if "John" in segment:
            return '{"items": [{"task": "finish the documentation", "owner_text": "John", "raw_date_phrase": "by Friday", "raw_time_phrase": null, "confidence": 0.9, "needs_review": false, "evidence_text": "John, please finish the documentation by Friday", "evidence_span": [0, 45], "extraction_id": "uuid-3"}]}'
        if "نور" in segment:
            return '{"items": [{"task": "check the logs", "owner_text": "نور", "raw_date_phrase": "today", "raw_time_phrase": null, "confidence": 0.9, "needs_review": false, "evidence_text": "نور، check the logs today", "evidence_span": [0, 25], "extraction_id": "uuid-4"}]}'

        return '{"items": []}'

    def shutdown(self) -> None:
        """Cleanly shuts down the model process."""
        logger.info("Shutting down LLM runtime...")
        self._is_running = False
        self._process = None
        logger.info("LLM runtime stopped.")


def _segment_under_extraction(prompt: str) -> str:
    """The text actually being extracted, taken from the end of the prompt.

    `build_extraction_prompt` appends the segment as the final `Input:` block,
    after the few-shot examples. Returning the whole prompt here would make the
    mock match its own examples; returning the last Input block keys it on the
    real segment.

    Falls back to the whole prompt for a caller that built one some other way,
    so this helper never silently returns an empty string.
    """
    marker = "Input:"
    index = prompt.rfind(marker)
    if index == -1:
        return prompt
    tail = prompt[index + len(marker):]
    output_index = tail.rfind("Output:")
    if output_index != -1:
        tail = tail[:output_index]
    return tail.strip()
