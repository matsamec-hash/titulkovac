from __future__ import annotations

from titulkovac.models import Cue, SegmentRules
from titulkovac.rules import layout_lines
from titulkovac.seams import Translator


def translate_cues(cues: list[Cue], translator: Translator,
                   target_langs: list[str], rules: SegmentRules) -> list[Cue]:
    """Prelozi kazdy cue do vsech cilovych jazyku. Casy se NEMENI.

    Prekladovy text projde zalomenim dle pravidel (layout_lines = max 2 radky).
    POZNAMKA: pokud je preklad delsi nez se vejde do 2 radku x max_chars_per_line,
    layout_lines vrati nejlepsi 2-radkove zalomeni i kdyz nektery radek limit
    presahne. To je zamerne: titulky maji mit max 2 radky a delku resime jednak
    instrukci pro prekladac (prekladej strucne), jednak rucni upravou v nahledu
    (Plan 3). NIKDY nevyrabime 3+ radkove titulky.
    """
    for lang in target_langs:
        texts = translator.translate(cues, lang)
        if len(texts) != len(cues):
            raise ValueError(
                f"Translator vratil {len(texts)} textu, ocekavano {len(cues)}"
            )
        for cue, t in zip(cues, texts):
            cue.translations[lang] = layout_lines(t.strip(), rules)
    return cues
