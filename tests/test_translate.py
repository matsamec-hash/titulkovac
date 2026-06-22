import pytest

from titulkovac.models import Cue, SegmentRules
from titulkovac.translate import translate_cues
from tests.fakes import FakeTranslator


def test_translate_cues_raises_on_count_mismatch():
    cues = [Cue(index=1, start=0.0, end=1.0, text="a"),
            Cue(index=2, start=1.0, end=2.0, text="b")]

    class BadTranslator:
        def translate(self, cues, target_lang):
            return ["jen jeden"]  # vrati min nez je cues

    with pytest.raises(ValueError):
        translate_cues(cues, BadTranslator(), ["en"], SegmentRules())


def test_translate_cues_fills_translations_and_keeps_times():
    cues = [
        Cue(index=1, start=0.0, end=1.0, text="Dobry den"),
        Cue(index=2, start=1.2, end=2.0, text="jak se mas"),
    ]
    rules = SegmentRules(max_chars_per_line=42, max_lines=2, max_cps=99.0)
    out = translate_cues(cues, FakeTranslator(), ["en"], rules)
    assert out[0].translations["en"] == "en: Dobry den"
    assert out[1].translations["en"] == "en: jak se mas"
    assert out[0].start == 0.0 and out[0].end == 1.0
    assert out[0].text == "Dobry den"


def test_translate_cues_relayouts_long_translation():
    # preklad delsi nez jeden radek se zalomi do 2 radku dle pravidel
    cues = [Cue(index=1, start=0.0, end=5.0, text="x")]
    rules = SegmentRules(max_chars_per_line=10, max_lines=2, max_cps=99.0)

    class LongTranslator:
        def translate(self, cues, target_lang):
            return ["jedna dve tri ctyri"]  # 19 znaku -> 2 radky po <=10

    out = translate_cues(cues, LongTranslator(), ["en"], rules)
    en = out[0].translations["en"]
    assert "\n" in en
    # NIKDY vic nez 2 radky (titulkarska norma)
    assert len(en.split("\n")) <= 2
    assert all(len(ln) <= 10 for ln in en.split("\n"))


def test_translate_cues_never_exceeds_two_lines_even_when_overlong():
    # preklad, ktery se do 2x max_chars nevejde: zustane 2 radky (best-effort),
    # NESMI vzniknout 3+ radkovy titulek
    cues = [Cue(index=1, start=0.0, end=5.0, text="x")]
    rules = SegmentRules(max_chars_per_line=10, max_lines=2, max_cps=99.0)

    class TooLongTranslator:
        def translate(self, cues, target_lang):
            return ["jedna dve tri ctyri pet sest"]  # nevejde se do 2x10

    out = translate_cues(cues, TooLongTranslator(), ["en"], rules)
    en = out[0].translations["en"]
    assert len(en.split("\n")) <= 2


def test_translate_cues_multiple_languages():
    cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj")]
    rules = SegmentRules()
    out = translate_cues(cues, FakeTranslator(), ["en", "de"], rules)
    assert set(out[0].translations.keys()) == {"en", "de"}
