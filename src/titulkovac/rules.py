from __future__ import annotations

from titulkovac.models import SegmentRules, Word


def layout_lines(text: str, rules: SegmentRules) -> str:
    """Zalomi text do max. 2 radku, kazdy <= max_chars_per_line.

    Zalamuje jen na hranici slova. Hleda nejvyvazenejsi zlom (radky podobne
    dlouhe). Pokud se nevejde, vrati nejlepsi dosazitelne zalomeni.

    POZNAMKA: funkce dela jediny zlom => podporuje max. 2 radky. To odpovida
    profi titulkarske norme (max 2 radky) a vychozimu SegmentRules.max_lines=2,
    ktery cela pipeline pouziva. Pro `max_lines > 2` by bylo potreba N-cestne
    zalamovani (zamerne neimplementovano — YAGNI).
    """
    words = text.split()
    if len(words) <= 1:
        return text

    if len(text) <= rules.max_chars_per_line:
        return text

    if rules.max_lines < 2:
        return text  # nemame kam zalomit

    best_split: int | None = None
    best_cost: float | None = None
    for i in range(1, len(words)):
        top = " ".join(words[:i])
        bottom = " ".join(words[i:])
        longest = max(len(top), len(bottom))
        over = max(0, longest - rules.max_chars_per_line)
        cost = over * 1000 + abs(len(top) - len(bottom))
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_split = i

    assert best_split is not None
    top = " ".join(words[:best_split])
    bottom = " ".join(words[best_split:])
    return f"{top}\n{bottom}"



def _group_text(words: list[Word]) -> str:
    return " ".join(w.text for w in words)


def fits_rules(words: list[Word], rules: SegmentRules) -> bool:
    """Vejde se skupina slov do jednoho titulku dle pravidel?"""
    if not words:
        return True
    text = _group_text(words)
    laid = layout_lines(text, rules)
    lines = laid.split("\n")
    if len(lines) > rules.max_lines:
        return False
    if any(len(ln) > rules.max_chars_per_line for ln in lines):
        return False
    duration = words[-1].end - words[0].start
    if duration <= 0:
        return False
    # CPS pocitame z poctu znaku textu (vcetne mezer, bez zalomeni)
    cps = len(text) / duration
    if cps > rules.max_cps:
        return False
    if duration > rules.max_duration:
        return False
    return True


def _largest_gap_index(words: list[Word]) -> int:
    """Index, PRED kterym je nejvetsi pauza (kandidat na zlom). >=1."""
    best_i = 1
    best_gap = -1.0
    for i in range(1, len(words)):
        gap = words[i].start - words[i - 1].end
        if gap > best_gap:
            best_gap = gap
            best_i = i
    return best_i


def split_oversized(words: list[Word], rules: SegmentRules) -> list[list[Word]]:
    """Rekurzivne rozdeli prilis dlouhou skupinu na nejvetsich pauzach,
    dokud kazdy kus nevyhovuje pravidlum (nebo neni 1 slovo)."""
    if not words:
        return []
    if fits_rules(words, rules) or len(words) == 1:
        return [words]
    i = _largest_gap_index(words)
    left = words[:i]
    right = words[i:]
    return split_oversized(left, rules) + split_oversized(right, rules)
