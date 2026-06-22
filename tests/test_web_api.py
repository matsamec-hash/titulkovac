from titulkovac.web.schemas import JobOut, CueOut, CuePatch


def test_schemas_construct():
    j = JobOut(id="x", filename="a.mp4", languages=["en"], status="queued",
               step="queued", progress=0.0)
    assert j.error is None
    c = CueOut(index=1, start=0.0, end=1.0, text="Ahoj")
    assert c.translations == {}
    p = CuePatch(text="novy")
    assert p.start is None
