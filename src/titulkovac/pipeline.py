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

    if step_done(job_dir, "transcribe") and words_path.exists():
        words = load_words(words_path)
    else:
        words = transcriber.transcribe(audio_path, config.source_language)
        save_words(words, words_path)
        mark_step(job_dir, "transcribe")

    if step_done(job_dir, "segment") and cues_path.exists():
        cues = load_cues(cues_path)
    else:
        cues = build_cues(words, boundary_provider, config.rules)
        save_cues(cues, cues_path)
        mark_step(job_dir, "segment")

    need = [lang for lang in config.target_languages
            if not all(lang in c.translations for c in cues)]
    if need:
        translate_cues(cues, translator, need, config.rules)
        save_cues(cues, cues_path)
        mark_step(job_dir, "translate")

    return cues
