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
    assert (job_dir / "words.json").exists()
    assert (job_dir / "cues.json").exists()


def test_run_pipeline_resumes_transcription(tmp_path):
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


def test_run_pipeline_resumes_after_segment(tmp_path):
    # hotovy transcribe i segment -> boundary_provider se NESMI volat
    from titulkovac.persistence import save_words, save_cues, mark_step
    from titulkovac.models import Cue
    words = [Word(text="Ahoj", start=0.0, end=0.5)]
    cues_done = [Cue(index=1, start=0.0, end=0.5, text="Ahoj")]
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    save_words(words, job_dir / "words.json")
    save_cues(cues_done, job_dir / "cues.json")
    mark_step(job_dir, "transcribe")
    mark_step(job_dir, "segment")

    class BoomBoundary:
        def boundaries(self, words):
            raise AssertionError("boundaries se nemel volat (resume)")

    cfg = AppConfig.from_dict({"target_languages": ["en"]})
    cues = run_pipeline(
        audio_path=tmp_path / "fake.wav", job_dir=job_dir, config=cfg,
        transcriber=FakeTranscriber(words),
        boundary_provider=BoomBoundary(),
        translator=FakeTranslator(),
    )
    assert cues[0].translations["en"] == "en: Ahoj"


def test_run_pipeline_translates_only_missing_language(tmp_path):
    # cues uz maji "en"; pridavame "de" -> prelozi se jen "de"
    from titulkovac.persistence import save_words, save_cues, mark_step
    from titulkovac.models import Cue
    words = [Word(text="Ahoj", start=0.0, end=0.5)]
    cues_done = [Cue(index=1, start=0.0, end=0.5, text="Ahoj",
                     translations={"en": "PUVODNI"})]
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    save_words(words, job_dir / "words.json")
    save_cues(cues_done, job_dir / "cues.json")
    mark_step(job_dir, "transcribe")
    mark_step(job_dir, "segment")

    cfg = AppConfig.from_dict({"target_languages": ["en", "de"]})
    cues = run_pipeline(
        audio_path=tmp_path / "fake.wav", job_dir=job_dir, config=cfg,
        transcriber=FakeTranscriber(words),
        boundary_provider=FakeBoundaryProvider([]),
        translator=FakeTranslator(),
    )
    # "en" se NEPREKLADAL znovu (zustal puvodni), "de" pribyl
    assert cues[0].translations["en"] == "PUVODNI"
    assert cues[0].translations["de"] == "de: Ahoj"
