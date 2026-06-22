import io
import time

from fastapi.testclient import TestClient

from titulkovac.web.schemas import JobOut, CueOut, CuePatch
from titulkovac.web.app import create_app
from titulkovac.web.jobs import JobStore, JobManager
from titulkovac.persistence import save_cues
from titulkovac.models import Cue


def test_schemas_construct():
    j = JobOut(id="x", filename="a.mp4", languages=["en"], status="queued",
               step="queued", progress=0.0)
    assert j.error is None
    c = CueOut(index=1, start=0.0, end=1.0, text="Ahoj")
    assert c.translations == {}
    p = CuePatch(text="novy")
    assert p.start is None


def _make_client(tmp_path, runner):
    store = JobStore(tmp_path / "jobs")
    manager = JobManager(store, runner=runner)
    app = create_app(store, manager)
    return TestClient(app), store


def test_create_and_get_job(tmp_path):
    def runner(input_path, job_dir, languages, on_progress):
        on_progress("done", 100.0)

    client, store = _make_client(tmp_path, runner)
    with client:
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

        cues = client.get(f"/api/jobs/{job_id}/cues").json()
        assert cues[0]["text"] == "Ahoj"

        patched = client.patch(f"/api/jobs/{job_id}/cues/1",
                               json={"text": "Nazdar"})
        assert patched.status_code == 200
        assert patched.json()["text"] == "Nazdar"
        assert patched.json()["edited"] is True

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
