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


def test_create_job_sanitizes_filename(tmp_path):
    captured = {}

    def runner(input_path, job_dir, languages, on_progress):
        captured["input_path"] = input_path
        captured["job_dir"] = job_dir
        on_progress("done", 100.0)

    client, store = _make_client(tmp_path, runner)
    with client:
        resp = client.post("/api/jobs",
                           files={"file": ("../../evil.mp4", io.BytesIO(b"d"),
                                           "video/mp4")},
                           data={"languages": "en"})
        job_id = resp.json()["id"]
        _wait_status(client, job_id, "done")
        # ulozeny nazev je jen zaklad, soubor zustal uvnitr job_dir
        assert resp.json()["filename"] == "evil.mp4"
        ip = captured["input_path"].resolve()
        jd = captured["job_dir"].resolve()
        assert str(ip).startswith(str(jd))


def test_unknown_job_returns_404(tmp_path):
    client, store = _make_client(tmp_path, lambda *a: None)
    with client:
        assert client.get("/api/jobs/neexistuje").status_code == 404
        assert client.get("/api/jobs/neexistuje/cues").status_code == 404


def test_cues_before_done_returns_409(tmp_path):
    import threading
    gate = threading.Event()

    def runner(input_path, job_dir, languages, on_progress):
        gate.wait(timeout=5.0)  # drz ulohu "running"
        on_progress("done", 100.0)

    client, store = _make_client(tmp_path, runner)
    with client:
        resp = client.post("/api/jobs",
                           files={"file": ("ep.mp4", io.BytesIO(b"d"), "video/mp4")},
                           data={"languages": "en"})
        job_id = resp.json()["id"]
        # cues.json jeste neni -> 409
        assert client.get(f"/api/jobs/{job_id}/cues").status_code == 409
        gate.set()
        _wait_status(client, job_id, "done")


def test_export_bad_format_returns_400(tmp_path):
    def runner(input_path, job_dir, languages, on_progress):
        cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj")]
        save_cues(cues, job_dir / "cues.json")
        on_progress("done", 100.0)

    client, store = _make_client(tmp_path, runner)
    with client:
        resp = client.post("/api/jobs",
                           files={"file": ("ep.mp4", io.BytesIO(b"d"), "video/mp4")},
                           data={"languages": "en"})
        job_id = resp.json()["id"]
        _wait_status(client, job_id, "done")
        assert client.get(
            f"/api/jobs/{job_id}/export?lang=cs&format=xxx").status_code == 400


def test_export_missing_translation_falls_back_to_original(tmp_path):
    def runner(input_path, job_dir, languages, on_progress):
        cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj")]  # bez prekladu
        save_cues(cues, job_dir / "cues.json")
        on_progress("done", 100.0)

    client, store = _make_client(tmp_path, runner)
    with client:
        resp = client.post("/api/jobs",
                           files={"file": ("ep.mp4", io.BytesIO(b"d"), "video/mp4")},
                           data={"languages": "en"})
        job_id = resp.json()["id"]
        _wait_status(client, job_id, "done")
        # 'de' chybi -> fallback na originalni text
        out = client.get(f"/api/jobs/{job_id}/export?lang=de&format=srt")
        assert "Ahoj" in out.text


def test_media_served_with_range(tmp_path):
    def runner(input_path, job_dir, languages, on_progress):
        (job_dir / "audio.wav").write_bytes(b"RIFFxxxxWAVE")
        on_progress("done", 100.0)

    client, store = _make_client(tmp_path, runner)
    with client:
        resp = client.post("/api/jobs",
                           files={"file": ("ep.mp4", io.BytesIO(b"d"), "video/mp4")},
                           data={"languages": "en"})
        job_id = resp.json()["id"]
        _wait_status(client, job_id, "done")

        full = client.get(f"/api/jobs/{job_id}/media")
        assert full.status_code == 200
        assert full.content == b"RIFFxxxxWAVE"
        assert full.headers["content-type"].startswith("audio/")

        part = client.get(f"/api/jobs/{job_id}/media",
                          headers={"Range": "bytes=0-3"})
        assert part.status_code == 206
        assert part.content == b"RIFF"


def test_media_missing_returns_404(tmp_path):
    def runner(input_path, job_dir, languages, on_progress):
        on_progress("done", 100.0)  # audio.wav se nevytvori

    client, store = _make_client(tmp_path, runner)
    with client:
        resp = client.post("/api/jobs",
                           files={"file": ("ep.mp4", io.BytesIO(b"d"), "video/mp4")},
                           data={"languages": "en"})
        job_id = resp.json()["id"]
        _wait_status(client, job_id, "done")
        assert client.get(f"/api/jobs/{job_id}/media").status_code == 404
        assert client.get("/api/jobs/neexistuje/media").status_code == 404


def _seed_cues_runner(cues):
    def runner(input_path, job_dir, languages, on_progress):
        save_cues(cues, job_dir / "cues.json")
        on_progress("done", 100.0)
    return runner


def _create_done_job(client, languages="en"):
    resp = client.post("/api/jobs",
                       files={"file": ("ep.mp4", io.BytesIO(b"d"), "video/mp4")},
                       data={"languages": languages})
    job_id = resp.json()["id"]
    _wait_status(client, job_id, "done")
    return job_id


def test_put_cues_roundtrip(tmp_path):
    runner = _seed_cues_runner([Cue(index=1, start=0.0, end=1.0, text="Ahoj")])
    client, store = _make_client(tmp_path, runner)
    with client:
        job_id = _create_done_job(client)
        new_cues = [
            {"index": 1, "start": 0.0, "end": 0.5, "text": "Ahoj",
             "translations": {"en": "Hi"}, "edited": True},
            {"index": 2, "start": 0.5, "end": 1.0, "text": "svete",
             "translations": {}, "edited": True},
        ]
        resp = client.put(f"/api/jobs/{job_id}/cues", json=new_cues)
        assert resp.status_code == 200
        assert [c["index"] for c in resp.json()] == [1, 2]

        again = client.get(f"/api/jobs/{job_id}/cues").json()
        assert len(again) == 2
        assert again[1]["text"] == "svete"


def test_put_cues_rejects_empty(tmp_path):
    runner = _seed_cues_runner([Cue(index=1, start=0.0, end=1.0, text="Ahoj")])
    client, store = _make_client(tmp_path, runner)
    with client:
        job_id = _create_done_job(client)
        assert client.put(f"/api/jobs/{job_id}/cues", json=[]).status_code == 400


def test_put_cues_rejects_non_ascending_index(tmp_path):
    runner = _seed_cues_runner([Cue(index=1, start=0.0, end=1.0, text="Ahoj")])
    client, store = _make_client(tmp_path, runner)
    with client:
        job_id = _create_done_job(client)
        bad = [
            {"index": 2, "start": 0.0, "end": 0.5, "text": "a"},
            {"index": 1, "start": 0.5, "end": 1.0, "text": "b"},
        ]
        assert client.put(f"/api/jobs/{job_id}/cues", json=bad).status_code == 400


def test_put_cues_rejects_start_after_end(tmp_path):
    runner = _seed_cues_runner([Cue(index=1, start=0.0, end=1.0, text="Ahoj")])
    client, store = _make_client(tmp_path, runner)
    with client:
        job_id = _create_done_job(client)
        bad = [{"index": 1, "start": 2.0, "end": 1.0, "text": "a"}]
        assert client.put(f"/api/jobs/{job_id}/cues", json=bad).status_code == 400


def test_put_cues_unknown_job_404(tmp_path):
    client, store = _make_client(tmp_path, lambda *a: None)
    with client:
        body = [{"index": 1, "start": 0.0, "end": 1.0, "text": "a"}]
        assert client.put("/api/jobs/neexistuje/cues", json=body).status_code == 404
