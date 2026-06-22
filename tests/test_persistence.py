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
