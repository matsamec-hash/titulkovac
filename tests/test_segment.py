from titulkovac.models import SegmentRules, Word
from titulkovac.segment import build_cues, split_words_by_boundaries
from tests.fakes import FakeBoundaryProvider


def _words(*pairs):
    return [Word(text=t, start=s, end=e) for t, s, e in pairs]


def test_split_words_by_boundaries():
    ws = _words(("a", 0, 1), ("b", 1, 2), ("c", 2, 3), ("d", 3, 4))
    groups = split_words_by_boundaries(ws, [2])
    assert [[w.text for w in g] for g in groups] == [["a", "b"], ["c", "d"]]


def test_build_cues_uses_boundaries_and_word_times():
    ws = _words(("Dobry", 0.0, 0.4), ("den", 0.4, 0.8),
                ("vespolek", 1.0, 1.6))
    rules = SegmentRules(max_chars_per_line=42, max_lines=2, max_cps=99.0,
                         min_gap=0.0, min_duration=0.0)
    provider = FakeBoundaryProvider([2])  # zlom pred "vespolek"
    cues = build_cues(ws, provider, rules)
    assert len(cues) == 2
    assert cues[0].text == "Dobry den"
    assert cues[0].start == 0.0 and cues[0].end == 0.8
    assert cues[1].text == "vespolek"
    assert cues[1].start == 1.0 and cues[1].end == 1.6
    assert [c.index for c in cues] == [1, 2]


def test_build_cues_splits_oversized_group():
    ws = _words(("aaaaaaaaaa", 0.0, 0.5), ("bbbbbbbbbb", 0.5, 1.0),
                ("cccccccccc", 2.0, 2.5), ("dddddddddd", 2.5, 3.0))
    rules = SegmentRules(max_chars_per_line=10, max_lines=2, max_cps=99.0,
                         min_gap=0.0, min_duration=0.0)
    provider = FakeBoundaryProvider([])  # zadne semanticke zlomy
    cues = build_cues(ws, provider, rules)
    assert len(cues) == 2  # rozdeleno na nejvetsi pauze (pred 'cccc')


def test_build_cues_enforces_min_gap():
    ws = _words(("a", 0.0, 1.0), ("b", 1.0, 2.0))
    rules = SegmentRules(max_chars_per_line=42, max_lines=2, max_cps=99.0,
                         min_gap=0.1, min_duration=0.0)
    provider = FakeBoundaryProvider([1])  # dva cues tesne na sebe
    cues = build_cues(ws, provider, rules)
    assert cues[1].start - cues[0].end >= 0.1 - 1e-9
