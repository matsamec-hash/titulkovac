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
