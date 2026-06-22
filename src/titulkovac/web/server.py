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
