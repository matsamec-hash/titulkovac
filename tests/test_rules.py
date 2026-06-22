from titulkovac.models import SegmentRules
from titulkovac.rules import layout_lines, fits_rules, split_oversized


def test_layout_lines_single_line_when_short():
    r = SegmentRules(max_chars_per_line=42, max_lines=2)
    assert layout_lines("Dobry den vespolek", r) == "Dobry den vespolek"


def test_layout_lines_breaks_into_two_balanced_lines():
    r = SegmentRules(max_chars_per_line=20, max_lines=2)
    text = "pšenice se letos urodila velmi dobře"
    out = layout_lines(text, r)
    lines = out.split("\n")
    assert len(lines) == 2
    assert all(len(ln) <= 20 for ln in lines)
    assert out.replace("\n", " ") == text


from titulkovac.models import Word


def _words(*pairs):
    return [Word(text=t, start=s, end=e) for t, s, e in pairs]


def test_fits_rules_true_for_short_group():
    r = SegmentRules(max_chars_per_line=42, max_lines=2, max_cps=17.0)
    group = _words(("Dobry", 0.0, 0.4), ("den", 0.4, 0.8))
    assert fits_rules(group, r) is True


def test_fits_rules_false_when_too_many_chars():
    r = SegmentRules(max_chars_per_line=10, max_lines=2, max_cps=99.0)
    group = _words(
        ("aaaaaaaaaa", 0.0, 0.5),
        ("bbbbbbbbbb", 0.5, 1.0),
        ("cccccccccc", 1.0, 1.5),
        ("dddddddddd", 1.5, 2.0),
    )
    assert fits_rules(group, r) is False


def test_fits_rules_false_when_cps_too_high():
    r = SegmentRules(max_chars_per_line=42, max_lines=2, max_cps=5.0)
    group = _words(("dvacetznakudohromad", 0.0, 1.0))
    assert fits_rules(group, r) is False


def test_split_oversized_splits_at_largest_gap():
    r = SegmentRules(max_chars_per_line=10, max_lines=1, max_cps=99.0)
    group = _words(("jed", 0.0, 0.5), ("dve", 0.5, 0.6), ("tri", 1.6, 2.0))
    chunks = split_oversized(group, r)
    assert len(chunks) >= 2
    assert all(fits_rules(ch, r) or len(ch) == 1 for ch in chunks)
    flat = [w.text for ch in chunks for w in ch]
    assert flat == ["jed", "dve", "tri"]
