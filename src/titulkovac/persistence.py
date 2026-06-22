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
