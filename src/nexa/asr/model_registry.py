"""Candidate STT models for the benchmark.

The Egyptian code-switch fine-tune is deliberately NOT hard-coded: no specific
checkpoint has been verified. To add one, either pass it to `resolve_model` /
`--model` as a path or Hugging Face repo id, or call `register`.

IMPORTANT: faster-whisper only loads CTranslate2-format models. A Hugging Face
Whisper fine-tune must be converted first, e.g.
    ct2-transformers-converter --model <hf_repo> --output_dir models/whisper/<name> \
        --quantization float16
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    key: str
    model_id: str  # faster-whisper size name, HF repo id, or local CT2 directory
    description: str


_REGISTRY: dict[str, ModelSpec] = {
    "whisper-small": ModelSpec("whisper-small", "small", "Baseline: fast, low resource"),
    "whisper-medium": ModelSpec("whisper-medium", "medium", "Accuracy baseline required by the plan"),
    "whisper-large-v3": ModelSpec("whisper-large-v3", "large-v3", "Optional upper bound (needs more VRAM)"),
}


def register(key: str, model_id: str, description: str = "") -> ModelSpec:
    spec = ModelSpec(key, model_id, description or "custom")
    _REGISTRY[key] = spec
    return spec


def available_models() -> list[ModelSpec]:
    return list(_REGISTRY.values())


def resolve_model(name_or_path: str) -> ModelSpec:
    """Registry key -> its spec; anything else is treated as a path / HF repo id."""
    if name_or_path in _REGISTRY:
        return _REGISTRY[name_or_path]
    return ModelSpec(key=name_or_path, model_id=name_or_path, description="custom path or repo id")
