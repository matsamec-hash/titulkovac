# Titulkovač — Plán 1: Jádro pipeline (CLI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Postavit jádro titulkovacího nástroje jako samostatné Python CLI: z videa/audia vyrobí kvalitní titulky (`.srt`/`.vtt`) v češtině + překlady, s důrazem na přesné časování a logické dělení vět.

**Architecture:** Čisté oddělení modulů `media → transcribe → segment → translate → export`. Pomalé/externí závislosti (WhisperX, Claude) jsou za **protokoly (seam)**, takže logika dělení a exportu se testuje deterministicky s „fake" implementacemi. Reálné adaptéry (WhisperX, Claude) jsou tenké a testují se integračně/manuálně. Mezivýsledky se ukládají na disk → resume bez opakování přepisu.

**Tech Stack:** Python 3.11+, `whisperx` (faster-whisper + wav2vec2), `ffmpeg` (přes subprocess), `anthropic` SDK (segmentace + překlad), `pytest`, `typer` (CLI).

---

## Struktura souborů

```
titulkovac/
  pyproject.toml
  src/titulkovac/
    __init__.py
    models.py            # Word, Cue, SegmentRules, JobState
    config.py            # AppConfig (jazyky, model, pravidla)
    seams.py             # Protocoly: Transcriber, BoundaryProvider, Translator
    media.py             # ffmpeg: video/audio -> wav 16k mono
    rules.py             # čistá logika: CPL/CPS/line layout/split (TDD)
    segment.py           # build_cues: boundaries + rules -> list[Cue]
    translate.py         # překlad cues se zachováním časů
    export.py            # render .srt / .vtt (TDD)
    persistence.py       # uložení/načtení mezikroků (JSON), resume
    adapters/
      __init__.py
      whisperx_transcriber.py   # reálný Transcriber (integrace)
      claude_boundary.py        # reálný BoundaryProvider (Claude)
      claude_translator.py      # reálný Translator (Claude)
    cli.py               # typer CLI: zřetězení pipeline
  tests/
    test_models.py
    test_rules.py
    test_segment.py
    test_translate.py
    test_export.py
    test_persistence.py
    fakes.py             # fake Transcriber/BoundaryProvider/Translator
```

**Hranice odpovědností:**
- `rules.py`, `segment.py`, `export.py`, `persistence.py` = **čistá deterministická logika** → plné TDD.
- `seams.py` = rozhraní; `tests/fakes.py` = testovací implementace.
- `adapters/*` = reálné integrace (WhisperX, Claude) → tenké, testované integračně/manuálně.
- `cli.py` = orchestrace, žádná business logika.

---

## Task 0: Scaffolding projektu

**Files:**
- Create: `pyproject.toml`
- Create: `src/titulkovac/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Vytvoř `pyproject.toml`**

```toml
[project]
name = "titulkovac"
version = "0.1.0"
description = "Automaticke titulkovani podcastu (prepis lokalne + AI delení a preklad)"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "anthropic>=0.40",
]

[project.optional-dependencies]
transcribe = ["whisperx>=3.1"]
dev = ["pytest>=8.0"]

[project.scripts]
titulkovac = "titulkovac.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/titulkovac"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Vytvoř prázdné `__init__.py`**

```bash
mkdir -p src/titulkovac/adapters tests
printf '' > src/titulkovac/__init__.py
printf '' > src/titulkovac/adapters/__init__.py
printf '' > tests/__init__.py
```

- [ ] **Step 3: Nainstaluj dev závislosti a ověř pytest běží**

Run: `python -m pip install -e ".[dev]" && python -m pytest -q`
Expected: `no tests ran` (0 testů, ale pytest funguje a najde `src` na pythonpath).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src tests
git commit -m "chore: scaffolding projektu titulkovac"
```

---

## Task 1: Datové modely

**Files:**
- Create: `src/titulkovac/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_models.py
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
    # 2 radky po 10 znacich = 20 znaku textu (newline se nepocita do CPS)
    c = Cue(index=1, start=0.0, end=2.0, text="abcdefghij\nklmnoprstu")
    assert c.char_count == 20
    assert round(c.cps, 1) == 10.0


def test_segment_rules_defaults():
    r = SegmentRules()
    assert r.max_chars_per_line == 42
    assert r.max_lines == 2
    assert r.max_cps == 17.0
```

- [ ] **Step 2: Spusť test — musí selhat**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: titulkovac.models`.

- [ ] **Step 3: Implementuj modely**

```python
# src/titulkovac/models.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Word:
    """Jedno slovo s casem nalepenym na zvuk (z forced alignmentu)."""
    text: str
    start: float  # sekundy
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Cue:
    """Jeden titulek. `text` muze obsahovat '\\n' pro druhy radek."""
    index: int
    start: float
    end: float
    text: str
    translations: dict[str, str] = field(default_factory=dict)
    edited: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def char_count(self) -> int:
        return len(self.text.replace("\n", ""))

    @property
    def cps(self) -> float:
        if self.duration <= 0:
            return float("inf")
        return self.char_count / self.duration


@dataclass(frozen=True)
class SegmentRules:
    """Profi titulkarska pravidla. Vse nastavitelne."""
    max_chars_per_line: int = 42
    max_lines: int = 2
    max_cps: float = 17.0
    min_duration: float = 1.0
    max_duration: float = 7.0
    min_gap: float = 0.083  # ~2 snimky @ 24 fps
```

- [ ] **Step 4: Spusť test — musí projít**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS (4 testy).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/models.py tests/test_models.py
git commit -m "feat: datove modely Word/Cue/SegmentRules"
```

---

## Task 2: Seamy (protokoly) a fakes

**Files:**
- Create: `src/titulkovac/seams.py`
- Create: `tests/fakes.py`

- [ ] **Step 1: Definuj protokoly**

```python
# src/titulkovac/seams.py
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from titulkovac.models import Cue, Word


class Transcriber(Protocol):
    """Prepise audio na slova s casy (forced alignment)."""
    def transcribe(self, audio_path: Path, language: str = "cs") -> list[Word]: ...


class BoundaryProvider(Protocol):
    """Vrati indexy slov, na kterych zacina NOVY titulek (split-before).

    Index 0 se nikdy nevraci (prvni titulek zacina vzdy slovem 0).
    Napr. [3, 7] = titulky: slova 0-2, 3-6, 7-konec.
    """
    def boundaries(self, words: list[Word]) -> list[int]: ...


class Translator(Protocol):
    """Prelozi text kazdeho cue do ciloveho jazyka. Zachova poradi a pocet."""
    def translate(self, cues: list[Cue], target_lang: str) -> list[str]: ...
```

- [ ] **Step 2: Napiš fakes pro testy**

```python
# tests/fakes.py
from __future__ import annotations

from pathlib import Path

from titulkovac.models import Cue, Word


class FakeTranscriber:
    def __init__(self, words: list[Word]) -> None:
        self._words = words

    def transcribe(self, audio_path: Path, language: str = "cs") -> list[Word]:
        return list(self._words)


class FakeBoundaryProvider:
    """Vrati predem dany seznam hranic (nezavisi na obsahu)."""
    def __init__(self, boundaries: list[int]) -> None:
        self._boundaries = boundaries

    def boundaries(self, words: list[Word]) -> list[int]:
        return list(self._boundaries)


class FakeTranslator:
    """Prelozi tak, ze pred kazdy text da prefix '<lang>: ' (deterministicke)."""
    def translate(self, cues: list[Cue], target_lang: str) -> list[str]:
        return [f"{target_lang}: {c.text.replace(chr(10), ' ')}" for c in cues]
```

- [ ] **Step 3: Ověř, že se vše importuje**

Run: `python -c "import titulkovac.seams; import tests.fakes; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add src/titulkovac/seams.py tests/fakes.py
git commit -m "feat: seamy (Transcriber/BoundaryProvider/Translator) + fakes"
```

---

## Task 3: Pravidla — počítání řádků a layout (čistá logika)

**Files:**
- Create: `src/titulkovac/rules.py`
- Test: `tests/test_rules.py`

- [ ] **Step 1: Napiš failing test pro `layout_lines`**

```python
# tests/test_rules.py
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
    # zalomeno na hranici slova, kazdy radek <= 20 znaku
    assert all(len(ln) <= 20 for ln in lines)
    # spojeni zpet da puvodni text (jen mezera<->newline)
    assert out.replace("\n", " ") == text
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `python -m pytest tests/test_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: titulkovac.rules`.

- [ ] **Step 3: Implementuj `layout_lines`**

```python
# src/titulkovac/rules.py
from __future__ import annotations

from titulkovac.models import SegmentRules, Word


def layout_lines(text: str, rules: SegmentRules) -> str:
    """Zalomi text do <= max_lines radku, kazdy <= max_chars_per_line.

    Zalamuje jen na hranici slova. Hleda nejvyvazenejsi zlom (radky podobne
    dlouhe). Pokud se nevejde, vrati nejlepsi dosazitelne zalomeni.
    """
    words = text.split()
    if len(words) <= 1:
        return text

    if len(text) <= rules.max_chars_per_line:
        return text

    if rules.max_lines < 2:
        return text  # nemame kam zalomit

    # zkus vsechny zlomy mezi slovy, vyber ten s nejmensi delkou nejdelsiho radku
    best_split: int | None = None
    best_cost: float | None = None
    for i in range(1, len(words)):
        top = " ".join(words[:i])
        bottom = " ".join(words[i:])
        longest = max(len(top), len(bottom))
        # penalizuj prekroceni limitu, pak vyvazenost
        over = max(0, longest - rules.max_chars_per_line)
        cost = over * 1000 + abs(len(top) - len(bottom))
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best_split = i

    assert best_split is not None
    top = " ".join(words[:best_split])
    bottom = " ".join(words[best_split:])
    return f"{top}\n{bottom}"
```

- [ ] **Step 4: Spusť — musí projít**

Run: `python -m pytest tests/test_rules.py -v`
Expected: PASS (2 testy).

- [ ] **Step 5: Napiš failing test pro `fits_rules` a `split_oversized`**

```python
# tests/test_rules.py  (PRIDEJ na konec)
from titulkovac.models import Word


def _words(*pairs):
    # pairs: (text, start, end)
    return [Word(text=t, start=s, end=e) for t, s, e in pairs]


def test_fits_rules_true_for_short_group():
    r = SegmentRules(max_chars_per_line=42, max_lines=2, max_cps=17.0)
    group = _words(("Dobry", 0.0, 0.4), ("den", 0.4, 0.8))
    assert fits_rules(group, r) is True


def test_fits_rules_false_when_too_many_chars():
    r = SegmentRules(max_chars_per_line=10, max_lines=2, max_cps=99.0)
    # 4 slova po 10 znacich = nevejde se do 2x10
    group = _words(
        ("aaaaaaaaaa", 0.0, 0.5),
        ("bbbbbbbbbb", 0.5, 1.0),
        ("cccccccccc", 1.0, 1.5),
        ("dddddddddd", 1.5, 2.0),
    )
    assert fits_rules(group, r) is False


def test_fits_rules_false_when_cps_too_high():
    r = SegmentRules(max_chars_per_line=42, max_lines=2, max_cps=5.0)
    # 20 znaku za 1s = 20 cps > 5
    group = _words(("dvacetznakudohromad", 0.0, 1.0))
    assert fits_rules(group, r) is False


def test_split_oversized_splits_at_largest_gap():
    r = SegmentRules(max_chars_per_line=10, max_lines=1, max_cps=99.0)
    # 3 slova, nejvetsi pauza pred "tri" (gap 1.0s)
    group = _words(("jed", 0.0, 0.5), ("dve", 0.5, 0.6), ("tri", 1.6, 2.0))
    chunks = split_oversized(group, r)
    assert len(chunks) >= 2
    # zadny chunk uz se nevejde do limitu? ne — kazdy chunk vyhovuje nebo je 1 slovo
    assert all(fits_rules(ch, r) or len(ch) == 1 for ch in chunks)
    # zachovano poradi a uplnost
    flat = [w.text for ch in chunks for w in ch]
    assert flat == ["jed", "dve", "tri"]
```

- [ ] **Step 6: Spusť — musí selhat**

Run: `python -m pytest tests/test_rules.py -v`
Expected: FAIL — `fits_rules` / `split_oversized` neexistují.

- [ ] **Step 7: Implementuj `fits_rules` a `split_oversized`**

```python
# src/titulkovac/rules.py  (PRIDEJ na konec)

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
    if fits_rules(words, rules) or len(words) == 1:
        return [words]
    i = _largest_gap_index(words)
    left = words[:i]
    right = words[i:]
    return split_oversized(left, rules) + split_oversized(right, rules)
```

- [ ] **Step 8: Spusť — musí projít**

Run: `python -m pytest tests/test_rules.py -v`
Expected: PASS (6 testů).

- [ ] **Step 9: Commit**

```bash
git add src/titulkovac/rules.py tests/test_rules.py
git commit -m "feat: rules — layout_lines, fits_rules, split_oversized (TDD)"
```

---

## Task 4: Segmentace — build_cues (boundaries + rules → cues)

**Files:**
- Create: `src/titulkovac/segment.py`
- Test: `tests/test_segment.py`

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_segment.py
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
    # jedna semanticka skupina, ale moc dlouha -> rozdeli se na 2 cues
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
    # konec prvniho se posune zpet, aby vznikla mezera >= 0.1
    assert cues[1].start - cues[0].end >= 0.1 - 1e-9
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `python -m pytest tests/test_segment.py -v`
Expected: FAIL — `ModuleNotFoundError: titulkovac.segment`.

- [ ] **Step 3: Implementuj `segment.py`**

```python
# src/titulkovac/segment.py
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

    # kazdou semantickou skupinu rozdel na technicky vyhovujici kusy
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
            # nezkrať pod start prvniho cue
            if new_end > a.start:
                a.end = new_end
```

- [ ] **Step 4: Spusť — musí projít**

Run: `python -m pytest tests/test_segment.py -v`
Expected: PASS (4 testy).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/segment.py tests/test_segment.py
git commit -m "feat: segment — build_cues (semanticke skupiny + pravidla)"
```

---

## Task 5: Překlad se zachováním časů

**Files:**
- Create: `src/titulkovac/translate.py`
- Test: `tests/test_translate.py`

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_translate.py
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
    # casy a originalni text zustavaji
    assert out[0].start == 0.0 and out[0].end == 1.0
    assert out[0].text == "Dobry den"


def test_translate_cues_relayouts_long_translation():
    cues = [Cue(index=1, start=0.0, end=5.0, text="x")]
    rules = SegmentRules(max_chars_per_line=10, max_lines=2, max_cps=99.0)

    class LongTranslator:
        def translate(self, cues, target_lang):
            return ["jedna dve tri ctyri pet"]  # > 10 znaku -> musi zalomit

    out = translate_cues(cues, LongTranslator(), ["en"], rules)
    en = out[0].translations["en"]
    assert "\n" in en
    assert all(len(ln) <= 10 for ln in en.split("\n"))


def test_translate_cues_multiple_languages():
    cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj")]
    rules = SegmentRules()
    out = translate_cues(cues, FakeTranslator(), ["en", "de"], rules)
    assert set(out[0].translations.keys()) == {"en", "de"}
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `python -m pytest tests/test_translate.py -v`
Expected: FAIL — `ModuleNotFoundError: titulkovac.translate`.

- [ ] **Step 3: Implementuj `translate.py`**

```python
# src/titulkovac/translate.py
from __future__ import annotations

from titulkovac.models import Cue, SegmentRules
from titulkovac.rules import layout_lines
from titulkovac.seams import Translator


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
            cue.translations[lang] = layout_lines(t.strip(), rules)
    return cues
```

- [ ] **Step 4: Spusť — musí projít**

Run: `python -m pytest tests/test_translate.py -v`
Expected: PASS (3 testy).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/translate.py tests/test_translate.py
git commit -m "feat: translate_cues — preklad se zachovanim casu + relayout"
```

---

## Task 6: Export `.srt`

**Files:**
- Create: `src/titulkovac/export.py`
- Test: `tests/test_export.py`

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_export.py
from titulkovac.models import Cue
from titulkovac.export import to_srt, format_timestamp


def test_format_timestamp():
    assert format_timestamp(0.0) == "00:00:00,000"
    assert format_timestamp(3661.5) == "01:01:01,500"
    assert format_timestamp(1.234) == "00:00:01,234"


def test_to_srt_original_text():
    cues = [
        Cue(index=1, start=0.0, end=2.0, text="Dobry den"),
        Cue(index=2, start=2.5, end=4.0, text="prvni\ndruhy"),
    ]
    out = to_srt(cues)
    expected = (
        "1\n"
        "00:00:00,000 --> 00:00:02,000\n"
        "Dobry den\n"
        "\n"
        "2\n"
        "00:00:02,500 --> 00:00:04,000\n"
        "prvni\ndruhy\n"
    )
    assert out == expected


def test_to_srt_uses_translation_when_lang_given():
    cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj",
                translations={"en": "Hello"})]
    out = to_srt(cues, lang="en")
    assert "Hello" in out
    assert "Ahoj" not in out
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `python -m pytest tests/test_export.py -v`
Expected: FAIL — `ModuleNotFoundError: titulkovac.export`.

- [ ] **Step 3: Implementuj `to_srt`**

```python
# src/titulkovac/export.py
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
```

- [ ] **Step 4: Spusť — musí projít**

Run: `python -m pytest tests/test_export.py -v`
Expected: PASS (3 testy).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/export.py tests/test_export.py
git commit -m "feat: export to_srt + format_timestamp (TDD)"
```

---

## Task 7: Export `.vtt`

**Files:**
- Modify: `src/titulkovac/export.py`
- Test: `tests/test_export.py`

- [ ] **Step 1: Napiš failing test (přidej do `tests/test_export.py`)**

```python
# tests/test_export.py  (PRIDEJ na konec)
from titulkovac.export import to_vtt, format_timestamp_vtt


def test_format_timestamp_vtt_uses_dot():
    assert format_timestamp_vtt(3661.5) == "01:01:01.500"


def test_to_vtt_has_header_and_blocks():
    cues = [Cue(index=1, start=0.0, end=2.0, text="Dobry den")]
    out = to_vtt(cues)
    assert out.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:02.000" in out
    assert "Dobry den" in out
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `python -m pytest tests/test_export.py -v`
Expected: FAIL — `to_vtt` / `format_timestamp_vtt` neexistují.

- [ ] **Step 3: Implementuj (přidej do `src/titulkovac/export.py`)**

```python
# src/titulkovac/export.py  (PRIDEJ na konec)

def format_timestamp_vtt(seconds: float) -> str:
    """Sekundy -> 'HH:MM:SS.mmm' (WebVTT pouziva tecku)."""
    return format_timestamp(seconds).replace(",", ".")


def to_vtt(cues: list[Cue], lang: str | None = None) -> str:
    """Vyrenderuje cues do WebVTT."""
    blocks: list[str] = ["WEBVTT\n"]
    for cue in cues:
        ts = (f"{format_timestamp_vtt(cue.start)} --> "
              f"{format_timestamp_vtt(cue.end)}")
        text = _text_for(cue, lang)
        blocks.append(f"{ts}\n{text}\n")
    return "\n".join(blocks)
```

- [ ] **Step 4: Spusť — musí projít**

Run: `python -m pytest tests/test_export.py -v`
Expected: PASS (5 testů celkem).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/export.py tests/test_export.py
git commit -m "feat: export to_vtt (WebVTT)"
```

---

## Task 8: Perzistence a resume (JSON mezikroky)

**Files:**
- Create: `src/titulkovac/persistence.py`
- Test: `tests/test_persistence.py`

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_persistence.py
from titulkovac.models import Cue, Word
from titulkovac.persistence import (
    save_words, load_words, save_cues, load_cues, step_done, mark_step,
)


def test_words_roundtrip(tmp_path):
    words = [Word(text="ahoj", start=0.0, end=0.5),
             Word(text="svete", start=0.5, end=1.0)]
    p = tmp_path / "words.json"
    save_words(words, p)
    loaded = load_words(p)
    assert loaded == words


def test_cues_roundtrip(tmp_path):
    cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj",
                translations={"en": "Hi"}, edited=True)]
    p = tmp_path / "cues.json"
    save_cues(cues, p)
    loaded = load_cues(p)
    assert loaded == cues


def test_step_marking(tmp_path):
    job = tmp_path / "job"
    job.mkdir()
    assert step_done(job, "transcribe") is False
    mark_step(job, "transcribe")
    assert step_done(job, "transcribe") is True
    assert step_done(job, "segment") is False
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `python -m pytest tests/test_persistence.py -v`
Expected: FAIL — `ModuleNotFoundError: titulkovac.persistence`.

- [ ] **Step 3: Implementuj `persistence.py`**

```python
# src/titulkovac/persistence.py
from __future__ import annotations

import json
from pathlib import Path

from titulkovac.models import Cue, Word


def save_words(words: list[Word], path: Path) -> None:
    data = [{"text": w.text, "start": w.start, "end": w.end} for w in words]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def load_words(path: Path) -> list[Word]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Word(text=d["text"], start=d["start"], end=d["end"]) for d in data]


def save_cues(cues: list[Cue], path: Path) -> None:
    data = [
        {
            "index": c.index, "start": c.start, "end": c.end, "text": c.text,
            "translations": c.translations, "edited": c.edited,
        }
        for c in cues
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def load_cues(path: Path) -> list[Cue]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        Cue(index=d["index"], start=d["start"], end=d["end"], text=d["text"],
            translations=dict(d.get("translations", {})),
            edited=bool(d.get("edited", False)))
        for d in data
    ]


def mark_step(job_dir: Path, step: str) -> None:
    (job_dir / f".{step}.done").write_text("ok", encoding="utf-8")


def step_done(job_dir: Path, step: str) -> bool:
    return (job_dir / f".{step}.done").exists()
```

- [ ] **Step 4: Spusť — musí projít**

Run: `python -m pytest tests/test_persistence.py -v`
Expected: PASS (3 testy).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/persistence.py tests/test_persistence.py
git commit -m "feat: perzistence words/cues + step markery (resume)"
```

---

## Task 9: Konfigurace

**Files:**
- Create: `src/titulkovac/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_config.py
from titulkovac.config import AppConfig
from titulkovac.models import SegmentRules


def test_appconfig_defaults():
    cfg = AppConfig()
    assert cfg.source_language == "cs"
    assert "en" in cfg.target_languages
    assert cfg.claude_model == "claude-opus-4-8"
    assert isinstance(cfg.rules, SegmentRules)


def test_appconfig_from_dict_overrides():
    cfg = AppConfig.from_dict({
        "target_languages": ["en", "de"],
        "claude_model": "claude-haiku-4-5",
        "rules": {"max_chars_per_line": 38, "max_cps": 15.0},
    })
    assert cfg.target_languages == ["en", "de"]
    assert cfg.claude_model == "claude-haiku-4-5"
    assert cfg.rules.max_chars_per_line == 38
    assert cfg.rules.max_cps == 15.0
    # nezadane pravidlo zustava default
    assert cfg.rules.max_lines == 2
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: titulkovac.config`.

- [ ] **Step 3: Implementuj `config.py`**

```python
# src/titulkovac/config.py
from __future__ import annotations

from dataclasses import dataclass, field, replace

from titulkovac.models import SegmentRules


@dataclass(frozen=True)
class AppConfig:
    source_language: str = "cs"
    target_languages: list[str] = field(default_factory=lambda: ["en"])
    claude_model: str = "claude-opus-4-8"
    whisper_model: str = "large-v3"
    rules: SegmentRules = field(default_factory=SegmentRules)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        base = cls()
        rules = base.rules
        if "rules" in data:
            rules = replace(base.rules, **data["rules"])
        return cls(
            source_language=data.get("source_language", base.source_language),
            target_languages=list(
                data.get("target_languages", base.target_languages)),
            claude_model=data.get("claude_model", base.claude_model),
            whisper_model=data.get("whisper_model", base.whisper_model),
            rules=rules,
        )
```

- [ ] **Step 4: Spusť — musí projít**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS (2 testy).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/config.py tests/test_config.py
git commit -m "feat: AppConfig (jazyky, model, pravidla) + from_dict"
```

---

## Task 10: Modul `media` (ffmpeg)

**Files:**
- Create: `src/titulkovac/media.py`
- Test: `tests/test_media.py`

> `ffmpeg` se volá přes subprocess; testujeme **konstrukci příkazu** (čistá funkce), ne reálné spuštění. Reálné spuštění ověříme manuálně v Tasku 13.

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_media.py
from pathlib import Path
from titulkovac.media import build_ffmpeg_command


def test_build_ffmpeg_command():
    cmd = build_ffmpeg_command(Path("vstup.mp4"), Path("out.wav"))
    assert cmd[0] == "ffmpeg"
    assert "-i" in cmd
    assert "vstup.mp4" in cmd
    assert "out.wav" in cmd
    # 16 kHz mono PCM
    assert "16000" in cmd
    assert "1" in cmd  # mono
    assert "-y" in cmd  # prepis bez ptani
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `python -m pytest tests/test_media.py -v`
Expected: FAIL — `ModuleNotFoundError: titulkovac.media`.

- [ ] **Step 3: Implementuj `media.py`**

```python
# src/titulkovac/media.py
from __future__ import annotations

import subprocess
from pathlib import Path


def build_ffmpeg_command(src: Path, dst: Path) -> list[str]:
    """Sestavi ffmpeg prikaz: libovolne video/audio -> wav 16kHz mono PCM."""
    return [
        "ffmpeg", "-y",
        "-i", str(src),
        "-ac", "1",            # mono
        "-ar", "16000",        # 16 kHz
        "-c:a", "pcm_s16le",   # 16-bit PCM
        str(dst),
    ]


def extract_audio(src: Path, dst: Path) -> Path:
    """Spusti ffmpeg. Vyhodi RuntimeError s vystupem pri chybe."""
    cmd = build_ffmpeg_command(src, dst)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg selhal (kod {proc.returncode}):\n{proc.stderr[-2000:]}"
        )
    return dst
```

- [ ] **Step 4: Spusť — musí projít**

Run: `python -m pytest tests/test_media.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/media.py tests/test_media.py
git commit -m "feat: media — build_ffmpeg_command + extract_audio"
```

---

## Task 11: Reálné adaptéry (WhisperX, Claude)

> Tyto moduly volají externí systémy; **nemají jednotkové testy** (testují se integračně v Tasku 13). Kód musí být kompletní a správný dle dokumentace SDK.

**Files:**
- Create: `src/titulkovac/adapters/whisperx_transcriber.py`
- Create: `src/titulkovac/adapters/claude_boundary.py`
- Create: `src/titulkovac/adapters/claude_translator.py`

- [ ] **Step 1: WhisperX transcriber**

```python
# src/titulkovac/adapters/whisperx_transcriber.py
from __future__ import annotations

from pathlib import Path

from titulkovac.models import Word


class WhisperXTranscriber:
    """Realny Transcriber. Vyzaduje `pip install titulkovac[transcribe]`.

    device: 'cuda' (GPU) nebo 'cpu' (fallback).
    compute_type: 'float16' pro GPU, 'int8' pro CPU.
    """

    def __init__(self, model_name: str = "large-v3", device: str = "cuda",
                 compute_type: str = "float16") -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, audio_path: Path, language: str = "cs") -> list[Word]:
        import whisperx  # lazy import (tezka zavislost)

        audio = whisperx.load_audio(str(audio_path))
        model = whisperx.load_model(
            self.model_name, self.device, compute_type=self.compute_type,
            language=language,
        )
        result = model.transcribe(audio, language=language)

        # forced alignment na uroven slov
        align_model, metadata = whisperx.load_align_model(
            language_code=language, device=self.device)
        aligned = whisperx.align(
            result["segments"], align_model, metadata, audio, self.device,
            return_char_alignments=False,
        )

        words: list[Word] = []
        for seg in aligned["segments"]:
            for w in seg.get("words", []):
                # nektera slova nemusi mit cas (cisla/interpunkce) -> preskoc
                if "start" in w and "end" in w:
                    words.append(Word(text=w["word"].strip(),
                                      start=float(w["start"]),
                                      end=float(w["end"])))
        return words
```

- [ ] **Step 2: Claude boundary provider**

```python
# src/titulkovac/adapters/claude_boundary.py
from __future__ import annotations

import anthropic

from titulkovac.models import Word

_SYSTEM = (
    "Jsi expert na strihani titulku. Dostanes prepis jako ocislovana slova. "
    "Vrat indexy slov, na kterych ma ZACINAT novy titulek tak, aby kazdy "
    "titulek daval smysl jako celek: lam na koncich vet, u carek a pred "
    "spojkami; NIKDY neutínej uprostred jmenne nebo predlozkove vazby. "
    "Index 0 nevracej (prvni titulek zacina vzdy slovem 0)."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "boundaries": {"type": "array", "items": {"type": "integer"}}
    },
    "required": ["boundaries"],
    "additionalProperties": False,
}


class ClaudeBoundaryProvider:
    """Realny BoundaryProvider pres Claude. Zpracovava po oknech, aby se
    dlouhy prepis vesel do kontextu a drzela se konzistence."""

    def __init__(self, model: str = "claude-opus-4-8",
                 window_words: int = 400) -> None:
        self.client = anthropic.Anthropic()
        self.model = model
        self.window_words = window_words

    def boundaries(self, words: list[Word]) -> list[int]:
        all_boundaries: list[int] = []
        for offset in range(0, len(words), self.window_words):
            chunk = words[offset:offset + self.window_words]
            local = self._boundaries_for_chunk(chunk)
            # prepocet lokalnich indexu na globalni + zlom na hranici okna
            if offset > 0:
                all_boundaries.append(offset)
            all_boundaries.extend(offset + b for b in local if 0 < b < len(chunk))
        return sorted(set(all_boundaries))

    def _boundaries_for_chunk(self, chunk: list[Word]) -> list[int]:
        numbered = "\n".join(f"{i}: {w.text}" for i, w in enumerate(chunk))
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": numbered}],
        )
        import json
        text = next(b.text for b in resp.content if b.type == "text")
        return list(json.loads(text)["boundaries"])
```

- [ ] **Step 3: Claude translator**

```python
# src/titulkovac/adapters/claude_translator.py
from __future__ import annotations

import json

import anthropic

from titulkovac.models import Cue

_SYSTEM = (
    "Jsi profesionalni prekladatel titulku. Prelozis seznam titulku do "
    "ciloveho jazyka. Preklad ma byt prirozeny a strucny (titulky se ctou "
    "rychle). Zachovej poradi i POCET polozek 1:1. U kazde polozky prelozis "
    "jen text, neslucuj ani nedel titulky."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["translations"],
    "additionalProperties": False,
}


class ClaudeTranslator:
    """Realny Translator pres Claude. Preklada po davkach pro kontext."""

    def __init__(self, model: str = "claude-opus-4-8",
                 batch_size: int = 50) -> None:
        self.client = anthropic.Anthropic()
        self.model = model
        self.batch_size = batch_size

    def translate(self, cues: list[Cue], target_lang: str) -> list[str]:
        out: list[str] = []
        for start in range(0, len(cues), self.batch_size):
            batch = cues[start:start + self.batch_size]
            out.extend(self._translate_batch(batch, target_lang))
        return out

    def _translate_batch(self, batch: list[Cue], lang: str) -> list[str]:
        items = [c.text.replace("\n", " ") for c in batch]
        payload = json.dumps({"target_language": lang, "items": items},
                             ensure_ascii=False)
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": payload}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        result = json.loads(text)["translations"]
        if len(result) != len(batch):
            raise ValueError(
                f"Claude vratil {len(result)} prekladu, ocekavano {len(batch)}")
        return result
```

- [ ] **Step 4: Ověř import (bez volání API)**

Run: `python -c "from titulkovac.adapters.claude_boundary import ClaudeBoundaryProvider; from titulkovac.adapters.claude_translator import ClaudeTranslator; print('ok')"`
Expected: `ok` (instance se nevytváří, takže nepotřebuje API klíč).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/adapters
git commit -m "feat: adaptery WhisperX + Claude (boundary, translator)"
```

---

## Task 12: CLI orchestrace + resume

**Files:**
- Create: `src/titulkovac/pipeline.py`
- Create: `src/titulkovac/cli.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Napiš failing test pro pipeline s fakes**

```python
# tests/test_pipeline.py
from pathlib import Path

from titulkovac.config import AppConfig
from titulkovac.models import Word
from titulkovac.pipeline import run_pipeline
from tests.fakes import FakeTranscriber, FakeBoundaryProvider, FakeTranslator


def test_run_pipeline_end_to_end_with_fakes(tmp_path):
    words = [
        Word(text="Dobry", start=0.0, end=0.4),
        Word(text="den", start=0.4, end=0.8),
        Word(text="vespolek", start=1.0, end=1.6),
    ]
    cfg = AppConfig.from_dict({"target_languages": ["en"]})
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    cues = run_pipeline(
        audio_path=tmp_path / "fake.wav",
        job_dir=job_dir,
        config=cfg,
        transcriber=FakeTranscriber(words),
        boundary_provider=FakeBoundaryProvider([2]),
        translator=FakeTranslator(),
    )

    assert len(cues) == 2
    assert cues[0].text == "Dobry den"
    assert cues[0].translations["en"] == "en: Dobry den"
    # mezikroky ulozeny
    assert (job_dir / "words.json").exists()
    assert (job_dir / "cues.json").exists()


def test_run_pipeline_resumes_transcription(tmp_path):
    # pokud words.json existuje a krok je hotovy, transcriber se nevola
    from titulkovac.persistence import save_words, mark_step
    words = [Word(text="Ahoj", start=0.0, end=0.5)]
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    save_words(words, job_dir / "words.json")
    mark_step(job_dir, "transcribe")

    class BoomTranscriber:
        def transcribe(self, audio_path, language="cs"):
            raise AssertionError("transcribe se nemel volat (resume)")

    cfg = AppConfig.from_dict({"target_languages": ["en"]})
    cues = run_pipeline(
        audio_path=tmp_path / "fake.wav",
        job_dir=job_dir,
        config=cfg,
        transcriber=BoomTranscriber(),
        boundary_provider=FakeBoundaryProvider([]),
        translator=FakeTranslator(),
    )
    assert len(cues) == 1
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: titulkovac.pipeline`.

- [ ] **Step 3: Implementuj `pipeline.py`**

```python
# src/titulkovac/pipeline.py
from __future__ import annotations

from pathlib import Path

from titulkovac.config import AppConfig
from titulkovac.models import Cue
from titulkovac.persistence import (
    load_cues, load_words, mark_step, save_cues, save_words, step_done,
)
from titulkovac.segment import build_cues
from titulkovac.seams import BoundaryProvider, Transcriber, Translator
from titulkovac.translate import translate_cues


def run_pipeline(audio_path: Path, job_dir: Path, config: AppConfig,
                 transcriber: Transcriber, boundary_provider: BoundaryProvider,
                 translator: Translator) -> list[Cue]:
    """Zretezi kroky 2-5. Mezikroky uklada; pri restartu pokracuje od
    posledniho hotoveho kroku (neprepisuje znovu)."""
    words_path = job_dir / "words.json"
    cues_path = job_dir / "cues.json"

    # 1) transcribe (resume)
    if step_done(job_dir, "transcribe") and words_path.exists():
        words = load_words(words_path)
    else:
        words = transcriber.transcribe(audio_path, config.source_language)
        save_words(words, words_path)
        mark_step(job_dir, "transcribe")

    # 2) segment (resume)
    if step_done(job_dir, "segment") and cues_path.exists():
        cues = load_cues(cues_path)
    else:
        cues = build_cues(words, boundary_provider, config.rules)
        save_cues(cues, cues_path)
        mark_step(job_dir, "segment")

    # 3) translate (resume) — pokud uz prelozeno do vsech jazyku, preskoc
    need = [lang for lang in config.target_languages
            if not all(lang in c.translations for c in cues)]
    if need:
        translate_cues(cues, translator, need, config.rules)
        save_cues(cues, cues_path)
        mark_step(job_dir, "translate")

    return cues
```

- [ ] **Step 4: Spusť — musí projít**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS (2 testy).

- [ ] **Step 5: Implementuj `cli.py`**

```python
# src/titulkovac/cli.py
from __future__ import annotations

import json
from pathlib import Path

import typer

from titulkovac.config import AppConfig
from titulkovac.export import to_srt, to_vtt
from titulkovac.media import extract_audio
from titulkovac.pipeline import run_pipeline

app = typer.Typer(help="Titulkovac — automaticke titulky pro podcasty.")


@app.command()
def titulkuj(
    vstup: Path = typer.Argument(..., help="Vstupni video/audio soubor."),
    jazyky: str = typer.Option("en", help="Cilove jazyky, carkou (napr. en,de)."),
    vystup: Path = typer.Option(Path("./vystup"), help="Vystupni slozka."),
    format: str = typer.Option("srt", help="srt nebo vtt."),
    config_file: Path = typer.Option(None, help="JSON konfigurace (volitelne)."),
    device: str = typer.Option("cuda", help="cuda nebo cpu."),
) -> None:
    """Zpracuje soubor a vyrobi titulky v cestine + cilovych jazycich."""
    data = json.loads(config_file.read_text("utf-8")) if config_file else {}
    data.setdefault("target_languages", [j.strip() for j in jazyky.split(",")])
    cfg = AppConfig.from_dict(data)

    vystup.mkdir(parents=True, exist_ok=True)
    job_dir = vystup / (vstup.stem + "_job")
    job_dir.mkdir(exist_ok=True)

    typer.echo("1/4 Extrahuji audio (ffmpeg)…")
    wav = extract_audio(vstup, job_dir / "audio.wav")

    # lazy import adapteru (tezke zavislosti / API klic)
    from titulkovac.adapters.whisperx_transcriber import WhisperXTranscriber
    from titulkovac.adapters.claude_boundary import ClaudeBoundaryProvider
    from titulkovac.adapters.claude_translator import ClaudeTranslator

    compute = "float16" if device == "cuda" else "int8"
    typer.echo("2/4 Prepis + zarovnani (WhisperX)…")
    typer.echo("3/4 Logicke deleni (Claude)…")
    typer.echo("4/4 Preklad (Claude)…")
    cues = run_pipeline(
        audio_path=wav, job_dir=job_dir, config=cfg,
        transcriber=WhisperXTranscriber(cfg.whisper_model, device, compute),
        boundary_provider=ClaudeBoundaryProvider(cfg.claude_model),
        translator=ClaudeTranslator(cfg.claude_model),
    )

    render = to_vtt if format == "vtt" else to_srt
    ext = "vtt" if format == "vtt" else "srt"
    # original (cs) + kazdy cilovy jazyk
    for lang in [None, *cfg.target_languages]:
        suffix = cfg.source_language if lang is None else lang
        out_path = vystup / f"{vstup.stem}.{suffix}.{ext}"
        out_path.write_text(render(cues, lang), encoding="utf-8")
        typer.echo(f"  ✓ {out_path}")

    typer.echo("Hotovo.")


if __name__ == "__main__":
    app()
```

- [ ] **Step 6: Ověř, že CLI naběhne (help)**

Run: `python -m titulkovac.cli --help`
Expected: výpis nápovědy s příkazem `titulkuj`.

- [ ] **Step 7: Commit**

```bash
git add src/titulkovac/pipeline.py src/titulkovac/cli.py tests/test_pipeline.py
git commit -m "feat: pipeline (resume) + CLI titulkuj"
```

---

## Task 13: Integrace a manuální ověření (reálný běh)

> Tento task nemá automatické testy — je to **manuální smoke test** celé pipeline na krátké reálné ukázce. Vyžaduje GPU stroj, `ffmpeg`, nainstalovaný `whisperx` a `ANTHROPIC_API_KEY`.

**Files:**
- Create: `README.md`

- [ ] **Step 1: Napiš `README.md` s instrukcemi**

```markdown
# Titulkovac

Automaticke titulkovani podcastu: lokalni prepis (WhisperX, zdarma) + logicke
deleni vet a preklad pres Claude.

## Pozadavky
- Python 3.11+
- ffmpeg v PATH
- (pro prepis) NVIDIA GPU + CUDA, nebo CPU fallback
- `ANTHROPIC_API_KEY` v prostredi

## Instalace
```bash
pip install -e ".[dev,transcribe]"
```

## Pouziti
```bash
export ANTHROPIC_API_KEY=sk-ant-...
titulkovac titulkuj epizoda.mp4 --jazyky en,de --format srt
# nebo na CPU:
titulkovac titulkuj epizoda.mp4 --device cpu
```

Vystup: `vystup/epizoda.cs.srt`, `vystup/epizoda.en.srt`, …
Mezivysledky se ukladaji do `vystup/epizoda_job/` (resume pri preruseni).
```

- [ ] **Step 2: Připrav krátkou ukázku**

Vezmi ~2 minuty českého audia (`ukazka.mp3`).

- [ ] **Step 3: Spusť celou pipeline**

Run:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
titulkovac titulkuj ukazka.mp3 --jazyky en --device cuda
```
Expected: vzniknou `vystup/ukazka.cs.srt` a `vystup/ukazka.en.srt`.

- [ ] **Step 4: Zkontroluj kvalitu výstupu (lidská kontrola)**

Otevři `vystup/ukazka.cs.srt` a ověř:
- časy odpovídají zvuku (titulky naskakují přesně),
- titulky se nelámou uprostřed vazeb (logické dělení),
- žádný řádek není delší než ~42 znaků, max 2 řádky.

- [ ] **Step 5: Ověř resume**

Run: smaž `.translate.done` a `cues.json` translations nech být, spusť znovu — přepis se NESMÍ opakovat (rychlý start, jen překlad).

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: README + manualni smoke test pipeline"
```

---

## Self-review (provedeno při psaní)

**Pokrytí spec → task:**
- Spec 1 (architektura, moduly, datový model) → Tasky 1–2, 12 ✓
- Spec 2a (časování, WhisperX alignment) → Task 11 (adapter) ✓
- Spec 2b (logické dělení: Claude + pravidla) → Tasky 3, 4, 11 ✓
- Spec 2c (překlad se zachováním časů) → Tasky 5, 11 ✓
- Spec 2d (konfigurace kvality) → Task 9 ✓
- Spec 3a (datový tok) → Task 12 (pipeline) ✓
- Spec 3b (resume, mezikroky, chyby) → Tasky 8, 12; ffmpeg chyba Task 10; CPU fallback Task 11/CLI ✓
- Spec 3c (technologie) → pyproject Task 0, adaptery Task 11 ✓
- Spec 3d (testování) → každý logický modul má TDD; integrace Task 13 ✓
- Export `.srt`/`.vtt` → Tasky 6, 7 ✓

**Typová konzistence:** `Word`, `Cue`, `SegmentRules` definovány v Tasku 1 a používány konzistentně. Protokoly (`Transcriber.transcribe`, `BoundaryProvider.boundaries`, `Translator.translate`) z Tasku 2 mají stejné signatury v adaptérech (Task 11), fakes (Task 2) i pipeline (Task 12).

**Mimo rozsah tohoto plánu (Plán 2 a 3):** FastAPI backend, fronta úloh, WebSocket progres, webový frontend, náhled/editor. Plán 1 je samostatně funkční CLI.
