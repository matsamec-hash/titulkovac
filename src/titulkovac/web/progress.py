from __future__ import annotations

from dataclasses import dataclass

# Poradi kroku pipeline (pro UI)
STEPS = ("queued", "transcribe", "segment", "translate", "done")


@dataclass(frozen=True)
class ProgressEvent:
    job_id: str
    step: str
    pct: float
