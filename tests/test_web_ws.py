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
