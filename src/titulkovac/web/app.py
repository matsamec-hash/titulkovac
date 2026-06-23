from __future__ import annotations

import asyncio
import queue as _queue
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse

from titulkovac.export import to_srt, to_vtt
from titulkovac.models import Cue
from titulkovac.persistence import load_cues, save_cues
from titulkovac.web.jobs import JobManager, JobStore
from titulkovac.web.progress import ProgressEvent
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
    # Hub: per-job seznam thread-safe front, do kterych publikuje listener.
    subscribers: dict[str, list["_queue.Queue[dict]"]] = {}

    def _publish(ev: ProgressEvent) -> None:
        for q in list(subscribers.get(ev.job_id, [])):
            q.put({"step": ev.step, "pct": ev.pct})

    manager.listener = _publish

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
        # sanitizace: jen zaklad nazvu, zadne ../ ani absolutni cesty
        safe_name = Path(file.filename or "input").name or "input"
        rec = store.create(filename=safe_name, languages=langs)
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

    @app.get("/api/jobs/{job_id}/media")
    def get_media(job_id: str) -> FileResponse:
        rec = _require_job(store, job_id)
        audio = rec.job_dir / "audio.wav"
        if not audio.exists():
            raise HTTPException(404, "audio jeste neni hotove")
        # Starlette FileResponse resi HTTP Range (206) automaticky.
        return FileResponse(audio, media_type="audio/wav")

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

    def _terminal_event(rec) -> dict | None:
        """Vrati terminalni progress event pokud uloha uz skoncila, jinak None."""
        if rec is None:
            return None
        if rec.status == "done":
            return {"step": "done", "pct": rec.progress}
        if rec.status == "error":
            return {"step": "error", "pct": rec.progress}
        return None

    @app.websocket("/api/jobs/{job_id}/progress")
    async def progress_ws(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        q: "_queue.Queue[dict]" = _queue.Queue()
        subscribers.setdefault(job_id, []).append(q)
        loop = asyncio.get_event_loop()
        try:
            # Uloha uz mohla skoncit JESTE NEZ se klient pripojil -> posli
            # terminalni event hned, jinak by WS visel do nekonecna.
            try:
                term = _terminal_event(store.get(job_id))
            except FileNotFoundError:
                term = None
            if term is not None:
                await websocket.send_json(term)
                return
            while True:
                try:
                    msg = await loop.run_in_executor(
                        None, lambda: q.get(timeout=1.0))
                except _queue.Empty:
                    # event mohl utect (race) -> over stav ulohy primo
                    try:
                        term = _terminal_event(store.get(job_id))
                    except FileNotFoundError:
                        term = None
                    if term is not None:
                        await websocket.send_json(term)
                        break
                    continue
                await websocket.send_json(msg)
                if msg["step"] in ("done", "error"):
                    break
        except WebSocketDisconnect:
            pass
        finally:
            subs = subscribers.get(job_id, [])
            if q in subs:
                subs.remove(q)

    return app
