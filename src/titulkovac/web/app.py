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


def _require_job(store: JobStore, job_id: str):
    try:
        return store.get(job_id)
    except FileNotFoundError:
        raise HTTPException(404, "job nenalezen")


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
        return _job_out(_require_job(store, job_id))

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
        render_lang = None if lang == "cs" else lang
        render = to_vtt if format == "vtt" else to_srt
        return render(cues, render_lang)

    return app
