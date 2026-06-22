# Titulkovač — Plán 2: Web backend (FastAPI) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Obalit hotové jádro pipeline (Plán 1) lokálním FastAPI backendem: nahrání souboru, fronta úloh na pozadí, sledování průběhu přes WebSocket, čtení/editace titulků a stažení exportu.

**Architecture:** FastAPI app nad jádrem. **JobManager** drží frontu a běží jednu úlohu naráz na worker vlákně (jedno GPU); každá úloha = adresář s `job.json` (stav, progres) + mezikroky z jádra. Pipeline dostane `on_progress` callback, který JobManager přeposílá do WebSocketu. Skutečné zpracování (ffmpeg + WhisperX + Claude) je injektovaný „runner", takže testy běží s fake runnerem bez externích závislostí.

**Tech Stack:** FastAPI, uvicorn, Pydantic v2, `httpx` (TestClient), pytest. Staví na `titulkovac.*` z Plánu 1.

---

## Struktura souborů

```
src/titulkovac/
  pipeline.py            # MODIFY: pridat on_progress callback
  web/
    __init__.py
    progress.py          # ProgressEvent + typy kroku
    jobs.py              # JobRecord, JobStore (job.json), JobManager (worker)
    runner.py            # default runner: extract_audio + run_pipeline (real adapters)
    schemas.py           # Pydantic modely pro API
    app.py               # FastAPI: routes + WebSocket
    server.py            # uvicorn entrypoint
tests/
  test_pipeline_progress.py
  test_web_jobs.py       # JobStore + JobManager s fake runnerem
  test_web_api.py        # FastAPI TestClient: REST
  test_web_ws.py         # FastAPI TestClient: WebSocket progres
```

**Hranice odpovědností:**
- `progress.py` = jen datové typy událostí (žádná logika).
- `jobs.py` = stav úloh + fronta/worker; nezná HTTP ani ffmpeg/whisper (přes injektovaný runner).
- `runner.py` = jediné místo, kde se potkává jádro s reálnými adaptéry.
- `app.py` = jen HTTP/WebSocket vrstva, deleguje na JobManager.

---

## Task 1: Progress callback v jádře pipeline

**Files:**
- Modify: `src/titulkovac/pipeline.py`
- Create: `src/titulkovac/web/__init__.py`
- Create: `src/titulkovac/web/progress.py`
- Test: `tests/test_pipeline_progress.py`

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_pipeline_progress.py
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
    # procenta neklesaji a konci na 100
    pcts = [p for _, p in events]
    assert pcts_nondecreasing(pcts)
    assert pcts[-1] == 100


def pcts_nondecreasing(pcts):
    return all(b >= a for a, b in zip(pcts, pcts[1:]))
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `.venv/bin/python -m pytest tests/test_pipeline_progress.py -v`
Expected: FAIL — `run_pipeline()` nezná `on_progress`.

- [ ] **Step 3: Uprav `run_pipeline` v `src/titulkovac/pipeline.py`**

Změň signaturu a přidej volání callbacku. Nahraď celý obsah funkce `run_pipeline` (ostatní importy nech) takto:

```python
from __future__ import annotations

from pathlib import Path
from typing import Callable

from titulkovac.config import AppConfig
from titulkovac.models import Cue
from titulkovac.persistence import (
    load_cues, load_words, mark_step, save_cues, save_words, step_done,
)
from titulkovac.segment import build_cues
from titulkovac.seams import BoundaryProvider, Transcriber, Translator
from titulkovac.translate import translate_cues

ProgressCallback = Callable[[str, float], None]


def run_pipeline(audio_path: Path, job_dir: Path, config: AppConfig,
                 transcriber: Transcriber, boundary_provider: BoundaryProvider,
                 translator: Translator,
                 on_progress: ProgressCallback | None = None) -> list[Cue]:
    """Zretezi kroky 2-5. Mezikroky uklada; pri restartu pokracuje od
    posledniho hotoveho kroku. on_progress(step, pct) hlasi prubeh."""
    def report(step: str, pct: float) -> None:
        if on_progress is not None:
            on_progress(step, pct)

    words_path = job_dir / "words.json"
    cues_path = job_dir / "cues.json"

    report("transcribe", 10.0)
    if step_done(job_dir, "transcribe") and words_path.exists():
        words = load_words(words_path)
    else:
        words = transcriber.transcribe(audio_path, config.source_language)
        save_words(words, words_path)
        mark_step(job_dir, "transcribe")

    report("segment", 60.0)
    if step_done(job_dir, "segment") and cues_path.exists():
        cues = load_cues(cues_path)
    else:
        cues = build_cues(words, boundary_provider, config.rules)
        save_cues(cues, cues_path)
        mark_step(job_dir, "segment")

    report("translate", 75.0)
    need = [lang for lang in config.target_languages
            if not all(lang in c.translations for c in cues)]
    if need:
        translate_cues(cues, translator, need, config.rules)
        save_cues(cues, cues_path)
        mark_step(job_dir, "translate")

    report("done", 100.0)
    return cues
```

- [ ] **Step 4: Vytvoř `src/titulkovac/web/__init__.py` (prázdný) a `src/titulkovac/web/progress.py`**

```python
# src/titulkovac/web/progress.py
from __future__ import annotations

from dataclasses import dataclass

# Poradi kroku pipeline (pro UI)
STEPS = ("queued", "transcribe", "segment", "translate", "done")


@dataclass(frozen=True)
class ProgressEvent:
    job_id: str
    step: str
    pct: float
```

```bash
mkdir -p src/titulkovac/web
printf '' > src/titulkovac/web/__init__.py
```

- [ ] **Step 5: Spusť — musí projít**

Run: `.venv/bin/python -m pytest tests/test_pipeline_progress.py -v`
Expected: PASS (1 test).

- [ ] **Step 6: Ověř, že celá sada je zelená (zpětná kompatibilita)**

Run: `.venv/bin/python -m pytest -q`
Expected: vše PASS (42 testů — `on_progress` je volitelný, staré testy běží beze změny).

- [ ] **Step 7: Commit**

```bash
git add src/titulkovac/pipeline.py src/titulkovac/web/__init__.py src/titulkovac/web/progress.py tests/test_pipeline_progress.py
git commit -m "feat(web): on_progress callback v run_pipeline + ProgressEvent"
```

---

## Task 2: Závislosti web vrstvy

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Přidej `web` extra do `pyproject.toml`**

V sekci `[project.optional-dependencies]` přidej řádek `web`:

```toml
[project.optional-dependencies]
transcribe = ["whisperx>=3.1"]
web = ["fastapi>=0.115", "uvicorn[standard]>=0.30", "python-multipart>=0.0.9", "httpx>=0.27"]
dev = ["pytest>=8.0"]
```

- [ ] **Step 2: Nainstaluj web extra do venv**

Run: `.venv/bin/python -m pip install -e ".[dev,web]"`
Expected: nainstaluje fastapi, uvicorn, python-multipart, httpx. Pokud síť selže, report BLOCKED.

- [ ] **Step 3: Ověř import**

Run: `.venv/bin/python -c "import fastapi, uvicorn, multipart, httpx; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(web): zavislosti fastapi/uvicorn/multipart/httpx (extra 'web')"
```

---

## Task 3: JobRecord + JobStore (perzistence stavu úlohy)

**Files:**
- Create: `src/titulkovac/web/jobs.py`
- Test: `tests/test_web_jobs.py`

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_web_jobs.py
from titulkovac.web.jobs import JobRecord, JobStore


def test_jobrecord_roundtrip(tmp_path):
    store = JobStore(tmp_path)
    rec = store.create(filename="ep.mp4", languages=["en", "de"])
    assert rec.status == "queued"
    assert rec.progress == 0.0
    assert rec.job_dir.exists()

    loaded = store.get(rec.id)
    assert loaded.id == rec.id
    assert loaded.filename == "ep.mp4"
    assert loaded.languages == ["en", "de"]


def test_jobstore_update_and_list(tmp_path):
    store = JobStore(tmp_path)
    a = store.create(filename="a.mp4", languages=["en"])
    b = store.create(filename="b.mp4", languages=["en"])

    store.update(a.id, status="running", progress=60.0, step="segment")
    reloaded = store.get(a.id)
    assert reloaded.status == "running"
    assert reloaded.progress == 60.0
    assert reloaded.step == "segment"

    ids = {r.id for r in store.list()}
    assert ids == {a.id, b.id}


def test_jobstore_set_error(tmp_path):
    store = JobStore(tmp_path)
    rec = store.create(filename="x.mp4", languages=["en"])
    store.update(rec.id, status="error", error="ffmpeg selhal")
    assert store.get(rec.id).error == "ffmpeg selhal"
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `.venv/bin/python -m pytest tests/test_web_jobs.py -v`
Expected: FAIL — `titulkovac.web.jobs` neexistuje.

- [ ] **Step 3: Implementuj `JobRecord` + `JobStore` v `src/titulkovac/web/jobs.py`**

```python
# src/titulkovac/web/jobs.py
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


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
        # nastavuje JobStore pres _dir; viz nize
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
        data = {k: v for k, v in asdict(rec).items()}
        self._meta_path(rec.id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Spusť — musí projít**

Run: `.venv/bin/python -m pytest tests/test_web_jobs.py -v`
Expected: PASS (3 testy).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/web/jobs.py tests/test_web_jobs.py
git commit -m "feat(web): JobRecord + JobStore (job.json registr)"
```

---

## Task 4: JobManager — fronta + worker vlákno

**Files:**
- Modify: `src/titulkovac/web/jobs.py`
- Test: `tests/test_web_jobs.py`

> JobManager spouští úlohy na pozadí jedním worker vláknem (jedna naráz). Skutečné zpracování dělá **injektovaný runner** `runner(input_path, job_dir, languages, on_progress) -> None` — v testech fake, v produkci `web/runner.py` (Task 6). Progres se zapisuje do JobStore a posílá do volitelného listeneru (WebSocket hub doplní Task 7).

- [ ] **Step 1: Napiš failing test (přidej do `tests/test_web_jobs.py`)**

```python
# tests/test_web_jobs.py  (PRIDEJ na konec)
import threading
import time

from titulkovac.web.jobs import JobManager


def test_jobmanager_runs_job_to_done(tmp_path):
    store = JobStore(tmp_path)
    rec = store.create(filename="ep.mp4", languages=["en"])
    (rec.job_dir / "ep.mp4").write_bytes(b"fake")

    progress_seen = []

    def fake_runner(input_path, job_dir, languages, on_progress):
        on_progress("transcribe", 10.0)
        on_progress("segment", 60.0)
        on_progress("done", 100.0)

    mgr = JobManager(store, runner=fake_runner,
                     listener=lambda ev: progress_seen.append((ev.step, ev.pct)))
    mgr.start()
    mgr.enqueue(rec.id)
    _wait_until(lambda: store.get(rec.id).status in ("done", "error"))
    mgr.stop()

    assert store.get(rec.id).status == "done"
    assert store.get(rec.id).progress == 100.0
    assert ("done", 100.0) in progress_seen


def test_jobmanager_marks_error_on_exception(tmp_path):
    store = JobStore(tmp_path)
    rec = store.create(filename="ep.mp4", languages=["en"])

    def boom_runner(input_path, job_dir, languages, on_progress):
        raise RuntimeError("ffmpeg spadl")

    mgr = JobManager(store, runner=boom_runner)
    mgr.start()
    mgr.enqueue(rec.id)
    _wait_until(lambda: store.get(rec.id).status in ("done", "error"))
    mgr.stop()

    rec2 = store.get(rec.id)
    assert rec2.status == "error"
    assert "ffmpeg spadl" in (rec2.error or "")


def _wait_until(pred, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return
        time.sleep(0.02)
    raise AssertionError("timeout cekani na podminku")
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `.venv/bin/python -m pytest tests/test_web_jobs.py::test_jobmanager_runs_job_to_done -v`
Expected: FAIL — `JobManager` neexistuje.

- [ ] **Step 3: Implementuj `JobManager` (přidej do `src/titulkovac/web/jobs.py`)**

Přidej importy nahoře souboru a třídu na konec:

```python
# src/titulkovac/web/jobs.py  (PRIDEJ k importum nahore)
import queue
import threading
from pathlib import Path
from typing import Callable, Optional

from titulkovac.web.progress import ProgressEvent

# Runner: zpracuje vstupni soubor v job_dir; hlasi prubeh pres on_progress.
Runner = Callable[[Path, Path, list, Callable[[str, float], None]], None]
Listener = Callable[[ProgressEvent], None]
```

```python
# src/titulkovac/web/jobs.py  (PRIDEJ na konec souboru)

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
        except Exception as exc:  # noqa: BLE001 — chceme zachytit vse
            self.store.update(job_id, status="error", error=str(exc))
            if self.listener is not None:
                self.listener(ProgressEvent(job_id=job_id, step="error", pct=0.0))
```

- [ ] **Step 4: Spusť — musí projít**

Run: `.venv/bin/python -m pytest tests/test_web_jobs.py -v`
Expected: PASS (5 testů: 3 store + 2 manager).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/web/jobs.py tests/test_web_jobs.py
git commit -m "feat(web): JobManager — fronta + worker thread + error handling"
```

---

## Task 5: Pydantic schémata

**Files:**
- Create: `src/titulkovac/web/schemas.py`
- Test: `tests/test_web_api.py` (jen import-smoke v tomto tasku)

- [ ] **Step 1: Implementuj `src/titulkovac/web/schemas.py`**

```python
# src/titulkovac/web/schemas.py
from __future__ import annotations

from pydantic import BaseModel


class JobOut(BaseModel):
    id: str
    filename: str
    languages: list[str]
    status: str
    step: str
    progress: float
    error: str | None = None


class CueOut(BaseModel):
    index: int
    start: float
    end: float
    text: str
    translations: dict[str, str] = {}
    edited: bool = False


class CuePatch(BaseModel):
    text: str | None = None
    start: float | None = None
    end: float | None = None
    translations: dict[str, str] | None = None
```

- [ ] **Step 2: Napiš import-smoke test `tests/test_web_api.py`**

```python
# tests/test_web_api.py
from titulkovac.web.schemas import JobOut, CueOut, CuePatch


def test_schemas_construct():
    j = JobOut(id="x", filename="a.mp4", languages=["en"], status="queued",
               step="queued", progress=0.0)
    assert j.error is None
    c = CueOut(index=1, start=0.0, end=1.0, text="Ahoj")
    assert c.translations == {}
    p = CuePatch(text="novy")
    assert p.start is None
```

- [ ] **Step 3: Spusť — musí projít**

Run: `.venv/bin/python -m pytest tests/test_web_api.py -v`
Expected: PASS (1 test).

- [ ] **Step 4: Commit**

```bash
git add src/titulkovac/web/schemas.py tests/test_web_api.py
git commit -m "feat(web): Pydantic schemata JobOut/CueOut/CuePatch"
```

---

## Task 6: Default runner (jádro + reálné adaptéry)

**Files:**
- Create: `src/titulkovac/web/runner.py`

> Bez jednotkových testů (volá ffmpeg/whisperx/Claude). Tenká továrna, která splňuje `Runner` signaturu z Tasku 4 a uvnitř volá `extract_audio` + `run_pipeline` s reálnými adaptéry. Lazy importy adaptérů (těžké závislosti / API klíč).

- [ ] **Step 1: Implementuj `src/titulkovac/web/runner.py`**

```python
# src/titulkovac/web/runner.py
from __future__ import annotations

from pathlib import Path
from typing import Callable

from titulkovac.config import AppConfig
from titulkovac.media import extract_audio
from titulkovac.pipeline import run_pipeline


def make_default_runner(device: str = "cuda",
                        config_overrides: dict | None = None):
    """Vrati runner(input_path, job_dir, languages, on_progress) pro JobManager.
    Pouziva realne adaptery (WhisperX + Claude)."""

    def runner(input_path: Path, job_dir: Path, languages: list[str],
               on_progress: Callable[[str, float], None]) -> None:
        from titulkovac.adapters.whisperx_transcriber import WhisperXTranscriber
        from titulkovac.adapters.claude_boundary import ClaudeBoundaryProvider
        from titulkovac.adapters.claude_translator import ClaudeTranslator

        data = dict(config_overrides or {})
        data["target_languages"] = list(languages)
        cfg = AppConfig.from_dict(data)

        on_progress("extract", 2.0)
        wav = extract_audio(input_path, job_dir / "audio.wav")

        compute = "float16" if device == "cuda" else "int8"
        run_pipeline(
            audio_path=wav, job_dir=job_dir, config=cfg,
            transcriber=WhisperXTranscriber(cfg.whisper_model, device, compute),
            boundary_provider=ClaudeBoundaryProvider(cfg.claude_model),
            translator=ClaudeTranslator(cfg.claude_model),
            on_progress=on_progress,
        )

    return runner
```

- [ ] **Step 2: Ověř import**

Run: `.venv/bin/python -c "from titulkovac.web.runner import make_default_runner; r = make_default_runner('cpu'); print('ok')"`
Expected: `ok` (továrna nevolá adaptéry, jen je vrací; bez API klíče OK).

- [ ] **Step 3: Commit**

```bash
git add src/titulkovac/web/runner.py
git commit -m "feat(web): default runner (extract_audio + run_pipeline + realne adaptery)"
```

---

## Task 7: FastAPI app — REST routes

**Files:**
- Create: `src/titulkovac/web/app.py`
- Test: `tests/test_web_api.py`

> App drží jeden `JobStore` + `JobManager` + jednoduchý WebSocket hub (množina aktivních spojení per job). Pro testy se app vytváří přes `create_app(store, manager)` s fake runnerem.

- [ ] **Step 1: Napiš failing test (přidej do `tests/test_web_api.py`)**

```python
# tests/test_web_api.py  (PRIDEJ na konec)
import io
import time

from fastapi.testclient import TestClient

from titulkovac.web.app import create_app
from titulkovac.web.jobs import JobStore, JobManager
from titulkovac.persistence import save_cues
from titulkovac.models import Cue


def _make_client(tmp_path, runner):
    store = JobStore(tmp_path / "jobs")
    manager = JobManager(store, runner=runner)
    app = create_app(store, manager)
    return TestClient(app), store


def test_create_and_get_job(tmp_path):
    def runner(input_path, job_dir, languages, on_progress):
        on_progress("done", 100.0)

    client, store = _make_client(tmp_path, runner)
    with client:  # spusti startup (manager.start)
        resp = client.post("/api/jobs",
                           files={"file": ("ep.mp4", io.BytesIO(b"data"),
                                           "video/mp4")},
                           data={"languages": "en,de"})
        assert resp.status_code == 201
        job_id = resp.json()["id"]
        assert resp.json()["languages"] == ["en", "de"]

        _wait_status(client, job_id, "done")
        got = client.get(f"/api/jobs/{job_id}")
        assert got.status_code == 200
        assert got.json()["status"] == "done"

        listed = client.get("/api/jobs").json()
        assert any(j["id"] == job_id for j in listed)


def test_get_and_patch_cues(tmp_path):
    captured = {}

    def runner(input_path, job_dir, languages, on_progress):
        cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj",
                    translations={"en": "Hi"})]
        save_cues(cues, job_dir / "cues.json")
        captured["job_dir"] = job_dir
        on_progress("done", 100.0)

    client, store = _make_client(tmp_path, runner)
    with client:
        resp = client.post("/api/jobs",
                           files={"file": ("ep.mp4", io.BytesIO(b"d"), "video/mp4")},
                           data={"languages": "en"})
        job_id = resp.json()["id"]
        _wait_status(client, job_id, "done")

        cues = client.get(f"/api/jobs/{job_id}/cues").json()
        assert cues[0]["text"] == "Ahoj"

        patched = client.patch(f"/api/jobs/{job_id}/cues/1",
                               json={"text": "Nazdar"})
        assert patched.status_code == 200
        assert patched.json()["text"] == "Nazdar"
        assert patched.json()["edited"] is True

        # zmena se ulozila
        again = client.get(f"/api/jobs/{job_id}/cues").json()
        assert again[0]["text"] == "Nazdar"


def test_export_download(tmp_path):
    def runner(input_path, job_dir, languages, on_progress):
        cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj",
                    translations={"en": "Hi"})]
        save_cues(cues, job_dir / "cues.json")
        on_progress("done", 100.0)

    client, store = _make_client(tmp_path, runner)
    with client:
        resp = client.post("/api/jobs",
                           files={"file": ("ep.mp4", io.BytesIO(b"d"), "video/mp4")},
                           data={"languages": "en"})
        job_id = resp.json()["id"]
        _wait_status(client, job_id, "done")

        srt_cs = client.get(f"/api/jobs/{job_id}/export?lang=cs&format=srt")
        assert srt_cs.status_code == 200
        assert "00:00:00,000 --> 00:00:01,000" in srt_cs.text
        assert "Ahoj" in srt_cs.text

        srt_en = client.get(f"/api/jobs/{job_id}/export?lang=en&format=srt")
        assert "Hi" in srt_en.text


def _wait_status(client, job_id, status, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if client.get(f"/api/jobs/{job_id}").json()["status"] == status:
            return
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} nedosahl stavu {status}")
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `.venv/bin/python -m pytest tests/test_web_api.py -v`
Expected: FAIL — `titulkovac.web.app` neexistuje.

- [ ] **Step 3: Implementuj `src/titulkovac/web/app.py`**

```python
# src/titulkovac/web/app.py
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from titulkovac.export import to_srt, to_vtt
from titulkovac.models import Cue
from titulkovac.persistence import load_cues, save_cues
from titulkovac.web.jobs import JobManager, JobStore
from titulkovac.web.schemas import CueOut, CuePatch, JobOut


def _job_out(rec) -> JobOut:
    return JobOut(id=rec.id, filename=rec.filename, languages=rec.languages,
                  status=rec.status, step=rec.step, progress=rec.progress,
                  error=rec.error)


def _cue_out(c: Cue) -> CueOut:
    return CueOut(index=c.index, start=c.start, end=c.end, text=c.text,
                  translations=dict(c.translations), edited=c.edited)


def create_app(store: JobStore, manager: JobManager) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager.start()
        yield
        manager.stop()

    app = FastAPI(title="Titulkovac", lifespan=lifespan)

    @app.post("/api/jobs", status_code=201, response_model=JobOut)
    async def create_job(file: UploadFile = File(...),
                         languages: str = Form("en")) -> JobOut:
        langs = [s.strip() for s in languages.split(",") if s.strip()]
        rec = store.create(filename=file.filename, languages=langs)
        dest = rec.job_dir / rec.filename
        dest.write_bytes(await file.read())
        manager.enqueue(rec.id)
        return _job_out(rec)

    @app.get("/api/jobs", response_model=list[JobOut])
    def list_jobs() -> list[JobOut]:
        return [_job_out(r) for r in store.list()]

    @app.get("/api/jobs/{job_id}", response_model=JobOut)
    def get_job(job_id: str) -> JobOut:
        try:
            return _job_out(store.get(job_id))
        except FileNotFoundError:
            raise HTTPException(404, "job nenalezen")

    @app.get("/api/jobs/{job_id}/cues", response_model=list[CueOut])
    def get_cues(job_id: str) -> list[CueOut]:
        rec = _require_job(store, job_id)
        cues_path = rec.job_dir / "cues.json"
        if not cues_path.exists():
            raise HTTPException(409, "titulky jeste nejsou hotove")
        return [_cue_out(c) for c in load_cues(cues_path)]

    @app.patch("/api/jobs/{job_id}/cues/{index}", response_model=CueOut)
    def patch_cue(job_id: str, index: int, patch: CuePatch) -> CueOut:
        rec = _require_job(store, job_id)
        cues_path = rec.job_dir / "cues.json"
        if not cues_path.exists():
            raise HTTPException(409, "titulky jeste nejsou hotove")
        cues = load_cues(cues_path)
        target = next((c for c in cues if c.index == index), None)
        if target is None:
            raise HTTPException(404, "titulek nenalezen")
        if patch.text is not None:
            target.text = patch.text
        if patch.start is not None:
            target.start = patch.start
        if patch.end is not None:
            target.end = patch.end
        if patch.translations is not None:
            target.translations.update(patch.translations)
        target.edited = True
        save_cues(cues, cues_path)
        return _cue_out(target)

    @app.get("/api/jobs/{job_id}/export", response_class=PlainTextResponse)
    def export(job_id: str, lang: str = "cs", format: str = "srt") -> str:
        rec = _require_job(store, job_id)
        cues_path = rec.job_dir / "cues.json"
        if not cues_path.exists():
            raise HTTPException(409, "titulky jeste nejsou hotove")
        if format not in ("srt", "vtt"):
            raise HTTPException(400, "format musi byt srt nebo vtt")
        cues = load_cues(cues_path)
        # lang 'cs' (zdroj) => originalni text (lang=None v exportu)
        render_lang = None if lang == "cs" else lang
        render = to_vtt if format == "vtt" else to_srt
        return render(cues, render_lang)

    return app


def _require_job(store: JobStore, job_id: str):
    try:
        return store.get(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "job nenalezen")
```

- [ ] **Step 4: Spusť — musí projít**

Run: `.venv/bin/python -m pytest tests/test_web_api.py -v`
Expected: PASS (4 testy: schemata + create/get, cues patch, export).

- [ ] **Step 5: Ověř celou sadu**

Run: `.venv/bin/python -m pytest -q`
Expected: vše PASS.

- [ ] **Step 6: Commit**

```bash
git add src/titulkovac/web/app.py tests/test_web_api.py
git commit -m "feat(web): FastAPI REST — jobs, cues (get/patch), export"
```

---

## Task 8: WebSocket progres

**Files:**
- Modify: `src/titulkovac/web/app.py`
- Test: `tests/test_web_ws.py`

> WebSocket `/api/jobs/{job_id}/progress` posílá JSON `{"step","pct"}` při každé změně. App si drží jednoduchý hub (per-job seznam aktivních front), do kterého JobManager listener publikuje. Aby app dostala progres, `create_app` napojí listener na manager.

- [ ] **Step 1: Napiš failing test**

```python
# tests/test_web_ws.py
import io
import time

from fastapi.testclient import TestClient

from titulkovac.web.app import create_app
from titulkovac.web.jobs import JobStore, JobManager


def test_ws_receives_progress(tmp_path):
    started = {"go": False}

    def runner(input_path, job_dir, languages, on_progress):
        # pockej na signal, aby se klient stihl pripojit
        while not started["go"]:
            time.sleep(0.01)
        on_progress("transcribe", 10.0)
        on_progress("segment", 60.0)
        on_progress("done", 100.0)

    store = JobStore(tmp_path / "jobs")
    manager = JobManager(store, runner=runner)
    app = create_app(store, manager)
    client = TestClient(app)

    with client:
        resp = client.post("/api/jobs",
                           files={"file": ("ep.mp4", io.BytesIO(b"d"), "video/mp4")},
                           data={"languages": "en"})
        job_id = resp.json()["id"]

        with client.websocket_connect(f"/api/jobs/{job_id}/progress") as ws:
            started["go"] = True
            steps = []
            for _ in range(3):
                msg = ws.receive_json()
                steps.append(msg["step"])
                if msg["step"] == "done":
                    break
            assert "done" in steps
            assert steps[-1] == "done"
```

- [ ] **Step 2: Spusť — musí selhat**

Run: `.venv/bin/python -m pytest tests/test_web_ws.py -v`
Expected: FAIL — WebSocket route neexistuje (404/iterace selže).

- [ ] **Step 3: Uprav `src/titulkovac/web/app.py`**

Přidej hub a WebSocket route. Nahraď začátek `create_app` (až po dekorátor `lifespan`) a přidej route. Konkrétně:

a) Přidej importy nahoru:
```python
import asyncio
import queue as _queue

from fastapi import WebSocket, WebSocketDisconnect
from titulkovac.web.progress import ProgressEvent
```

b) Uvnitř `create_app`, hned na začátku (před definicí `lifespan`), vlož hub a napojení listeneru:
```python
    # Hub: per-job seznam thread-safe front, do kterych publikuje listener.
    subscribers: dict[str, list["_queue.Queue[dict]"]] = {}

    def _publish(ev: ProgressEvent) -> None:
        for q in subscribers.get(ev.job_id, []):
            q.put({"step": ev.step, "pct": ev.pct})

    manager.listener = _publish
```

c) Před `return app` přidej WebSocket route:
```python
    @app.websocket("/api/jobs/{job_id}/progress")
    async def progress_ws(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        q: "_queue.Queue[dict]" = _queue.Queue()
        subscribers.setdefault(job_id, []).append(q)
        try:
            while True:
                # neblokuj event loop: cekej na frontu v executoru
                msg = await asyncio.get_event_loop().run_in_executor(None, q.get)
                await websocket.send_json(msg)
                if msg["step"] in ("done", "error"):
                    break
        except WebSocketDisconnect:
            pass
        finally:
            subscribers.get(job_id, []).remove(q)
```

- [ ] **Step 4: Spusť — musí projít**

Run: `.venv/bin/python -m pytest tests/test_web_ws.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Ověř celou sadu**

Run: `.venv/bin/python -m pytest -q`
Expected: vše PASS.

- [ ] **Step 6: Commit**

```bash
git add src/titulkovac/web/app.py tests/test_web_ws.py
git commit -m "feat(web): WebSocket /api/jobs/{id}/progress + hub"
```

---

## Task 9: Server entrypoint + manuální ověření

**Files:**
- Create: `src/titulkovac/web/server.py`
- Modify: `README.md`

- [ ] **Step 1: Implementuj `src/titulkovac/web/server.py`**

```python
# src/titulkovac/web/server.py
from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from titulkovac.web.app import create_app
from titulkovac.web.jobs import JobManager, JobStore
from titulkovac.web.runner import make_default_runner


def build_app():
    root = Path(os.environ.get("TITULKOVAC_DATA", "./data"))
    device = os.environ.get("TITULKOVAC_DEVICE", "cuda")
    store = JobStore(root / "jobs")
    manager = JobManager(store, runner=make_default_runner(device))
    return create_app(store, manager)


app = build_app()


def main() -> None:
    uvicorn.run("titulkovac.web.server:app", host="127.0.0.1", port=8000,
                reload=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Přidej console script do `pyproject.toml`**

V sekci `[project.scripts]` přidej:
```toml
[project.scripts]
titulkovac = "titulkovac.cli:app"
titulkovac-web = "titulkovac.web.server:main"
```

- [ ] **Step 3: Ověř, že app jde sestavit (bez spuštění serveru)**

Run: `TITULKOVAC_DEVICE=cpu .venv/bin/python -c "from titulkovac.web.server import build_app; build_app(); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Doplň do `README.md` sekci o web serveru**

Přidej na konec README:
```markdown
## Web rozhraní (Plán 2)

```bash
pip install -e ".[web,transcribe]"
export ANTHROPIC_API_KEY=sk-ant-...
export TITULKOVAC_DEVICE=cuda   # nebo cpu
titulkovac-web                  # bezi na http://127.0.0.1:8000
```

REST API:
- `POST /api/jobs` (multipart: `file`, `languages=en,de`) → vytvori a zaradi ulohu
- `GET /api/jobs` / `GET /api/jobs/{id}` → seznam / stav
- `GET /api/jobs/{id}/cues` → titulky; `PATCH /api/jobs/{id}/cues/{index}` → editace
- `GET /api/jobs/{id}/export?lang=cs&format=srt` → stazeni titulku
- WebSocket `GET /api/jobs/{id}/progress` → JSON `{step, pct}`

Data (nahrane soubory + mezikroky + job.json) jsou v `./data/jobs/` (zmen `TITULKOVAC_DATA`).
```

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/web/server.py pyproject.toml README.md
git commit -m "feat(web): uvicorn entrypoint titulkovac-web + README"
```

- [ ] **Step 6: (Manuální, volitelné — USER) Reálné spuštění**

Na stroji s GPU + API klíčem:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
titulkovac-web
# v druhem terminalu:
curl -F file=@ukazka.mp3 -F languages=en http://127.0.0.1:8000/api/jobs
```
Ověř, že job projde do `done` a `GET /api/jobs/{id}/export?lang=cs` vrátí SRT.

---

## Self-review (provedeno při psaní)

**Pokrytí spec → task:**
- Spec „FastAPI backend, REST API (úlohy, titulky, export)" → Tasky 3,5,7 ✓
- Spec „fronta úloh na pozadí (3h epizoda běží dlouho)" → Task 4 (JobManager worker) ✓
- Spec „WebSocket progres" → Tasky 1 (callback), 8 (WS) ✓
- Spec „frontend i backend nad stejným seznamem cues; editace se uloží" → Task 7 (GET/PATCH cues, save_cues) ✓
- Spec 3b „mezikroky na disk, resume" → využívá Plán 1 (run_pipeline resume); job.json je navíc ✓
- Spec 3b „výpadky/chyby" → Task 4 (error stav), Task 7 (HTTP chyby 404/409/400) ✓

**Typová konzistence:** `Runner` signatura `(input_path, job_dir, languages, on_progress)` je stejná v JobManager (Task 4), fake runnerech (testy) i default runneru (Task 6). `ProgressEvent(job_id, step, pct)` z Tasku 1 se používá v JobManager listeneru i WS hubu. `run_pipeline` `on_progress(step, pct)` z Tasku 1 volá default runner i fake.

**Mimo rozsah (Plán 3):** webový frontend (HTML/JS náhled video + tabulka, drag&drop, přehrávač). Tento plán je čisté HTTP/WebSocket API, ověřitelné přes TestClient/curl.

**Známé zjednodušení MVP:** jedna úloha naráz (jedno GPU); fronta a stav jen v paměti procesu + job.json (po restartu serveru se rozdělaná „running" úloha nedoběhne automaticky — `resume` ale zachová mezikroky, takže opětovné zařazení doběhne levně). To je pro lokální single-user nástroj v pořádku; auto-resume po restartu lze přidat později.
```
