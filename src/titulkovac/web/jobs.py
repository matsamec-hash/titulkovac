from __future__ import annotations

import json
import os
import queue
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

from titulkovac.web.progress import ProgressEvent

Runner = Callable[[Path, Path, list, Callable[[str, float], None]], None]
Listener = Callable[[ProgressEvent], None]


@dataclass
class JobRecord:
    id: str
    filename: str
    languages: list[str]
    status: str = "queued"   # queued | running | done | error
    step: str = "queued"     # queued | transcribe | segment | translate | done
    progress: float = 0.0
    error: str | None = None

    @property
    def job_dir(self) -> Path:
        return self._dir  # type: ignore[attr-defined]


class JobStore:
    """Registr uloh. Kazda uloha = adresar `<root>/<id>/` s `job.json`."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _meta_path(self, job_id: str) -> Path:
        return self.root / job_id / "job.json"

    def create(self, filename: str, languages: list[str]) -> JobRecord:
        job_id = uuid.uuid4().hex[:12]
        (self.root / job_id).mkdir(parents=True, exist_ok=True)
        rec = JobRecord(id=job_id, filename=filename, languages=list(languages))
        self._write(rec)
        return self._attach_dir(rec)

    def get(self, job_id: str) -> JobRecord:
        data = json.loads(self._meta_path(job_id).read_text("utf-8"))
        rec = JobRecord(**data)
        return self._attach_dir(rec)

    def list(self) -> list[JobRecord]:
        recs: list[JobRecord] = []
        for child in self.root.iterdir():
            meta = child / "job.json"
            if meta.exists():
                recs.append(self.get(child.name))
        return recs

    def update(self, job_id: str, **fields) -> JobRecord:
        rec = self.get(job_id)
        for k, v in fields.items():
            setattr(rec, k, v)
        self._write(rec)
        return rec

    def _attach_dir(self, rec: JobRecord) -> JobRecord:
        object.__setattr__(rec, "_dir", self.root / rec.id)
        return rec

    def _write(self, rec: JobRecord) -> None:
        # Atomicky zapis (tmp + os.replace), aby soubezny ctenar nikdy nevidel
        # rozepsany/prazdny job.json (worker thread pise, HTTP handler cte).
        data = {k: v for k, v in asdict(rec).items()}
        meta = self._meta_path(rec.id)
        tmp = meta.with_name(meta.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, meta)


class JobManager:
    """Fronta uloh + jeden worker thread (jedna uloha naraz)."""

    def __init__(self, store: JobStore, runner: Runner,
                 listener: Optional[Listener] = None) -> None:
        self.store = store
        self.runner = runner
        self.listener = listener
        self._queue: "queue.Queue[str | None]" = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._queue.put(None)  # sentinel
        self._thread.join(timeout=5.0)
        self._thread = None

    def enqueue(self, job_id: str) -> None:
        self._queue.put(job_id)

    def _worker(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            self._run_one(job_id)

    def _run_one(self, job_id: str) -> None:
        rec = self.store.get(job_id)
        self.store.update(job_id, status="running", step="transcribe",
                          progress=0.0, error=None)

        def on_progress(step: str, pct: float) -> None:
            status = "done" if step == "done" else "running"
            self.store.update(job_id, status=status, step=step, progress=pct)
            if self.listener is not None:
                self.listener(ProgressEvent(job_id=job_id, step=step, pct=pct))

        input_path = rec.job_dir / rec.filename
        try:
            self.runner(input_path, rec.job_dir, rec.languages, on_progress)
            self.store.update(job_id, status="done", step="done", progress=100.0)
        except Exception as exc:  # noqa: BLE001
            self.store.update(job_id, status="error", error=str(exc))
            if self.listener is not None:
                self.listener(ProgressEvent(job_id=job_id, step="error", pct=0.0))
