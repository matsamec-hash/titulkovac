from __future__ import annotations

from pathlib import Path

from titulkovac.models import Cue, Word


class FakeTranscriber:
    def __init__(self, words: list[Word]) -> None:
        self._words = words

    def transcribe(self, audio_path: Path, language: str = "cs") -> list[Word]:
        return list(self._words)


class FakeBoundaryProvider:
    """Vrati predem dany seznam hranic (nezavisi na obsahu)."""
    def __init__(self, boundaries: list[int]) -> None:
        self._boundaries = boundaries

    def boundaries(self, words: list[Word]) -> list[int]:
        return list(self._boundaries)


class FakeTranslator:
    """Prelozi tak, ze pred kazdy text da prefix '<lang>: ' (deterministicke)."""
    def translate(self, cues: list[Cue], target_lang: str) -> list[str]:
        return [f"{target_lang}: {c.text.replace(chr(10), ' ')}" for c in cues]
