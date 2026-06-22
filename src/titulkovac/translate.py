from __future__ import annotations

from titulkovac.models import Cue, SegmentRules
from titulkovac.rules import layout_lines
from titulkovac.seams import Translator


def _wrap_lines(text: str, max_chars: int) -> str:
    """Zalomi text do radku nepresahujicich max_chars, greedy po slovech."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        added = len(word) if not current else current_len + 1 + len(word)
        if current and added > max_chars:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = added
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def translate_cues(cues: list[Cue], translator: Translator,
                   target_langs: list[str], rules: SegmentRules) -> list[Cue]:
    """Prelozi kazdy cue do vsech cilovych jazyku. Casy se NEMENI.
    Prekladovy text projde zalomenim dle pravidel (CPL/max_lines)."""
    for lang in target_langs:
        texts = translator.translate(cues, lang)
        if len(texts) != len(cues):
            raise ValueError(
                f"Translator vratil {len(texts)} textu, ocekavano {len(cues)}"
            )
        for cue, t in zip(cues, texts):
            stripped = t.strip()
            laid = layout_lines(stripped, rules)
            lines = laid.split("\n")
            # Pokud layout_lines nestaci (radek prilis dlouhy), greedy wrap
            if any(len(ln) > rules.max_chars_per_line for ln in lines):
                laid = _wrap_lines(stripped, rules.max_chars_per_line)
            cue.translations[lang] = laid
    return cues
