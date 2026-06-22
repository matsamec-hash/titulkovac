from __future__ import annotations

from titulkovac.models import Cue, SegmentRules, Word
from titulkovac.rules import layout_lines, split_oversized
from titulkovac.seams import BoundaryProvider


def split_words_by_boundaries(words: list[Word],
                              boundaries: list[int]) -> list[list[Word]]:
    """Rozdeli slova na skupiny dle split-before indexu."""
    cuts = sorted(b for b in boundaries if 0 < b < len(words))
    groups: list[list[Word]] = []
    start = 0
    for c in cuts:
        groups.append(words[start:c])
        start = c
    groups.append(words[start:])
    return [g for g in groups if g]


def build_cues(words: list[Word], provider: BoundaryProvider,
               rules: SegmentRules) -> list[Cue]:
    """Hlavni segmentace: semanticke skupiny (Claude) doladene pravidly."""
    if not words:
        return []

    boundaries = provider.boundaries(words)
    groups = split_words_by_boundaries(words, boundaries)

    chunks: list[list[Word]] = []
    for group in groups:
        chunks.extend(split_oversized(group, rules))

    cues: list[Cue] = []
    for i, chunk in enumerate(chunks, start=1):
        text = layout_lines(" ".join(w.text for w in chunk), rules)
        cues.append(Cue(index=i, start=chunk[0].start,
                        end=chunk[-1].end, text=text))

    _enforce_min_gap(cues, rules)
    return cues


def _enforce_min_gap(cues: list[Cue], rules: SegmentRules) -> None:
    """Zajisti minimalni mezeru mezi sousednimi cues (posune end zpet)."""
    for a, b in zip(cues, cues[1:]):
        gap = b.start - a.end
        if gap < rules.min_gap:
            new_end = b.start - rules.min_gap
            if new_end > a.start:
                a.end = new_end
