from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Word:
    """Jedno slovo s casem nalepenym na zvuk (z forced alignmentu)."""
    text: str
    start: float  # sekundy
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Cue:
    """Jeden titulek. `text` muze obsahovat '\n' pro druhy radek."""
    index: int
    start: float
    end: float
    text: str
    translations: dict[str, str] = field(default_factory=dict)
    edited: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def char_count(self) -> int:
        return len(self.text.replace("\n", ""))

    @property
    def cps(self) -> float:
        if self.duration <= 0:
            return float("inf")
        return self.char_count / self.duration


@dataclass(frozen=True)
class SegmentRules:
    """Profi titulkarska pravidla. Vse nastavitelne."""
    max_chars_per_line: int = 42
    max_lines: int = 2
    max_cps: float = 17.0
    min_duration: float = 1.0
    max_duration: float = 7.0
    min_gap: float = 0.083  # ~2 snimky @ 24 fps
