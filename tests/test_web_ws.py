import io
import time

from fastapi.testclient import TestClient

from titulkovac.web.app import create_app
from titulkovac.web.jobs import JobStore, JobManager


def test_ws_receives_progress(tmp_path):
    started = {"go": False}

    def runner(input_path, job_dir, languages, on_progress):
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


def test_ws_late_connect_gets_terminal_event(tmp_path):
    # klient se pripoji AZ po dokonceni ulohy -> nesmi viset, dostane terminal
    def runner(input_path, job_dir, languages, on_progress):
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
        # pockej, az job dobehne
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if client.get(f"/api/jobs/{job_id}").json()["status"] == "done":
                break
            time.sleep(0.02)

        with client.websocket_connect(f"/api/jobs/{job_id}/progress") as ws:
            msg = ws.receive_json()  # nesmi viset
            assert msg["step"] == "done"
            assert msg["pct"] == 100.0
