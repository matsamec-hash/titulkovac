from titulkovac.models import Word, Cue, SegmentRules


def test_word_duration():
    w = Word(text="ahoj", start=1.0, end=1.5)
    assert round(w.duration, 3) == 0.5


def test_cue_defaults():
    c = Cue(index=1, start=0.0, end=2.0, text="Dobry den")
    assert c.translations == {}
    assert c.edited is False
    assert round(c.duration, 3) == 2.0


def test_cue_cps_counts_chars_without_newline():
    c = Cue(index=1, start=0.0, end=2.0, text="abcdefghij\nklmnoprstu")
    assert c.char_count == 20
    assert round(c.cps, 1) == 10.0


def test_segment_rules_defaults():
    r = SegmentRules()
    assert r.max_chars_per_line == 42
    assert r.max_lines == 2
    assert r.max_cps == 17.0
