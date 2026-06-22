from __future__ import annotations

from pathlib import Path
from typing import Protocol

from titulkovac.models import Cue, Word


class Transcriber(Protocol):
    """Prepise audio na slova s casy (forced alignment)."""
    def transcribe(self, audio_path: Path, language: str = "cs") -> list[Word]: ...


class BoundaryProvider(Protocol):
    """Vrati indexy slov, na kterych zacina NOVY titulek (split-before).

    Index 0 se nikdy nevraci (prvni titulek zacina vzdy slovem 0).
    Napr. [3, 7] = titulky: slova 0-2, 3-6, 7-konec.
    """
    def boundaries(self, words: list[Word]) -> list[int]: ...


class Translator(Protocol):
    """Prelozi text kazdeho cue do ciloveho jazyka. Zachova poradi a pocet."""
    def translate(self, cues: list[Cue], target_lang: str) -> list[str]: ...
