from titulkovac.config import AppConfig
from titulkovac.models import Word
from titulkovac.pipeline import run_pipeline
from tests.fakes import FakeTranscriber, FakeBoundaryProvider, FakeTranslator


def test_run_pipeline_emits_progress(tmp_path):
    words = [Word(text="Ahoj", start=0.0, end=0.5),
             Word(text="svete", start=0.5, end=1.0)]
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    cfg = AppConfig.from_dict({"target_languages": ["en"]})

    events = []
    run_pipeline(
        audio_path=tmp_path / "fake.wav", job_dir=job_dir, config=cfg,
        transcriber=FakeTranscriber(words),
        boundary_provider=FakeBoundaryProvider([]),
        translator=FakeTranslator(),
        on_progress=lambda step, pct: events.append((step, pct)),
    )

    steps = [s for s, _ in events]
    assert steps == ["transcribe", "segment", "translate", "done"]
    pcts = [p for _, p in events]
    assert pcts_nondecreasing(pcts)
    assert pcts[-1] == 100


def pcts_nondecreasing(pcts):
    return all(b >= a for a, b in zip(pcts, pcts[1:]))
