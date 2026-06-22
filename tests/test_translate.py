from titulkovac.models import Cue, SegmentRules
from titulkovac.translate import translate_cues
from tests.fakes import FakeTranslator


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
    cues = [Cue(index=1, start=0.0, end=5.0, text="x")]
    rules = SegmentRules(max_chars_per_line=10, max_lines=2, max_cps=99.0)

    class LongTranslator:
        def translate(self, cues, target_lang):
            return ["jedna dve tri ctyri pet"]

    out = translate_cues(cues, LongTranslator(), ["en"], rules)
    en = out[0].translations["en"]
    assert "\n" in en
    assert all(len(ln) <= 10 for ln in en.split("\n"))


def test_translate_cues_multiple_languages():
    cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj")]
    rules = SegmentRules()
    out = translate_cues(cues, FakeTranslator(), ["en", "de"], rules)
    assert set(out[0].translations.keys()) == {"en", "de"}
