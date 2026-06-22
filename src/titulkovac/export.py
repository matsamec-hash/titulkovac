from __future__ import annotations

from titulkovac.models import Cue


def format_timestamp(seconds: float) -> str:
    """Sekundy -> 'HH:MM:SS,mmm' (SRT format)."""
    if seconds < 0:
        seconds = 0.0
    millis_total = round(seconds * 1000)
    hours, millis_total = divmod(millis_total, 3_600_000)
    minutes, millis_total = divmod(millis_total, 60_000)
    secs, millis = divmod(millis_total, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _text_for(cue: Cue, lang: str | None) -> str:
    if lang is None:
        return cue.text
    return cue.translations.get(lang, cue.text)


def to_srt(cues: list[Cue], lang: str | None = None) -> str:
    """Vyrenderuje cues do SRT. lang=None => originalni text (cs)."""
    blocks: list[str] = []
    for i, cue in enumerate(cues, start=1):
        ts = f"{format_timestamp(cue.start)} --> {format_timestamp(cue.end)}"
        text = _text_for(cue, lang)
        blocks.append(f"{i}\n{ts}\n{text}\n")
    return "\n".join(blocks)
