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
