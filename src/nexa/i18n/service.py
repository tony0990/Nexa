from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal


class TranslationService(QObject):
    language_changed = Signal(str)

    def __init__(self, language: str = "en") -> None:
        super().__init__()
        self._dir = Path(__file__).resolve().parent
        self._catalogs = {
            "en": json.loads((self._dir / "en.json").read_text(encoding="utf-8")),
            "ar": json.loads((self._dir / "ar.json").read_text(encoding="utf-8")),
        }
        self._language = language if language in self._catalogs else "en"

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        if language not in self._catalogs:
            language = "en"
        self._language = language
        self.language_changed.emit(language)

    def t(self, key: str) -> str:
        catalog = self._catalogs[self._language]
        fallback = self._catalogs["en"]
        return catalog.get(key, fallback.get(key, key))

    def is_rtl(self) -> bool:
        return self._language == "ar"
