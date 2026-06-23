# Titulkovač Frontend (Plán 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Webové UI (vanilla HTML+JS, bez buildu) nad existujícím FastAPI backendem — nahrání epizody, sledování průběhu, kontrola/editace titulků s přehrávačem zvuku a export SRT/VTT.

**Architecture:** Tři malé backend přídavky (servírování `audio.wav` s Range, `PUT` celého seznamu cues, `StaticFiles` mount) + dvě statické stránky (`index.html` nahrání/seznam, `editor.html` přehrávač/tabulka) + ESM modul `cues.js` s čistými funkcemi (split/merge/reindex/timecode). Žádný framework, žádný build, žádné CDN.

**Tech Stack:** Python 3.11+ / FastAPI / Starlette `FileResponse` + `StaticFiles` / pytest (backend). Vanilla HTML + ESM JavaScript / `node:test` (frontend logika). Žádné npm závislosti.

---

## File Structure

**Modify:**
- `src/titulkovac/web/app.py` — přidat 3 routy/mount: `GET …/media`, `PUT …/cues`, `StaticFiles` mount.
- `src/titulkovac/web/schemas.py` — přidat `CueIn` (request model pro PUT).
- `tests/test_web_api.py` — přidat backend testy (reuse `_make_client`/`_wait_status`).
- `pyproject.toml` — zajistit, že `static/` se zabalí do balíčku (hatchling force-include).
- `README.md` — krátká sekce „Frontend / náhled v prohlížeči".

**Create:**
- `src/titulkovac/web/static/cues.js` — ESM čisté funkce (bez DOM).
- `src/titulkovac/web/static/index.html` — nahrání + seznam úloh + WS progres.
- `src/titulkovac/web/static/editor.html` — přehrávač + tabulka + editace + export.
- `src/titulkovac/web/static/style.css` — minimální styl pro obě stránky.
- `tests/cues.test.mjs` — `node:test` testy pro `cues.js`.

**Klíčová fakta z existujícího kódu (ověřeno):**
- Audio: `job_dir / "audio.wav"` (vzniká v `runner.py` přes `extract_audio`).
- Cue: `{index:int, start:float, end:float, text:str, translations:dict, edited:bool}`, **index je 1-based** (`segment.py`: `enumerate(chunks, start=1)`).
- `persistence.save_cues(cues, path)` / `load_cues(path)` — atomický není (prostý `write_text`), ale stávající testy to tak používají; ponechat.
- `JobStore.get(job_id)` vyhodí `FileNotFoundError` → `app.py` má helper `_require_job` → 404.
- Cesta cues: `rec.job_dir / "cues.json"`; když neexistuje → 409.
- SRT timecode formát: `export.format_timestamp` → `"HH:MM:SS,mmm"`.
- Testy reuse: `tests/test_web_api.py` má `_make_client(tmp_path, runner)` a `_wait_status(client, job_id, status)`.

---

## Task 1: Backend — `GET /api/jobs/{id}/media` (audio.wav s Range)

**Files:**
- Modify: `src/titulkovac/web/app.py` (přidat import `FileResponse`, novou routu)
- Test: `tests/test_web_api.py` (přidat 2 testy)

- [ ] **Step 1: Write the failing tests**

Přidej na konec `tests/test_web_api.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_api.py::test_media_served_with_range tests/test_web_api.py::test_media_missing_returns_404 -v`
Expected: FAIL — `404`/`405` (routa neexistuje) u prvního testu.

- [ ] **Step 3: Implement the media route**

V `src/titulkovac/web/app.py` přidej k importům z `fastapi.responses`:

```python
from fastapi.responses import FileResponse, PlainTextResponse
```

A přidej routu hned za `get_cues` (před `patch_cue` je jedno; jen uvnitř `create_app`, před `return app`):

```python
    @app.get("/api/jobs/{job_id}/media")
    def get_media(job_id: str) -> FileResponse:
        rec = _require_job(store, job_id)
        audio = rec.job_dir / "audio.wav"
        if not audio.exists():
            raise HTTPException(404, "audio jeste neni hotove")
        # Starlette FileResponse resi HTTP Range (206) automaticky.
        return FileResponse(audio, media_type="audio/wav")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_web_api.py::test_media_served_with_range tests/test_web_api.py::test_media_missing_returns_404 -v`
Expected: PASS (oba).

> **Fallback, kdyby `test_media_served_with_range` selhal na 206:** některé verze Starlette nevrací 206 pro `FileResponse` přes TestClient. Pokud ano, nahraď implementaci servírováním přes per-job `StaticFiles` mount nad `store.root` (`StaticFiles` Range umí): `app.mount("/media", StaticFiles(directory=store.root))` a routa jen ověří existenci + vrátí redirect/cestu. Preferuj ale `FileResponse` — v aktuální Starlette (≥0.30, je závislost FastAPI ≥0.115) Range funguje.

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/web/app.py tests/test_web_api.py
git commit -m "feat(web): GET /api/jobs/{id}/media — servuje audio.wav s Range"
```

---

## Task 2: Backend — `PUT /api/jobs/{id}/cues` (uloží celý seznam)

**Files:**
- Modify: `src/titulkovac/web/schemas.py` (přidat `CueIn`)
- Modify: `src/titulkovac/web/app.py` (přidat routu + import)
- Test: `tests/test_web_api.py` (přidat testy)

- [ ] **Step 1: Write the failing tests**

Přidej na konec `tests/test_web_api.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_api.py -k put_cues -v`
Expected: FAIL — routa PUT neexistuje (405/404).

- [ ] **Step 3a: Add `CueIn` schema**

V `src/titulkovac/web/schemas.py` přidej na konec:

```python
class CueIn(BaseModel):
    index: int
    start: float
    end: float
    text: str
    translations: dict[str, str] = {}
    edited: bool = False
```

- [ ] **Step 3b: Implement the PUT route**

V `src/titulkovac/web/app.py` rozšiř import schémat:

```python
from titulkovac.web.schemas import CueIn, CueOut, CuePatch, JobOut
```

A přidej routu za `patch_cue` (uvnitř `create_app`):

```python
    @app.put("/api/jobs/{job_id}/cues", response_model=list[CueOut])
    def put_cues(job_id: str, cues_in: list[CueIn]) -> list[CueOut]:
        rec = _require_job(store, job_id)
        cues_path = rec.job_dir / "cues.json"
        if not cues_path.exists():
            raise HTTPException(409, "titulky jeste nejsou hotove")
        if not cues_in:
            raise HTTPException(400, "prazdny seznam titulku")
        indices = [c.index for c in cues_in]
        if any(b <= a for a, b in zip(indices, indices[1:])):
            raise HTTPException(400, "indexy musi byt vzestupne a unikatni")
        for c in cues_in:
            if c.start > c.end:
                raise HTTPException(400, f"titulek {c.index}: start > end")
        cues = [Cue(index=c.index, start=c.start, end=c.end, text=c.text,
                    translations=dict(c.translations), edited=c.edited)
                for c in cues_in]
        save_cues(cues, cues_path)
        return [_cue_out(c) for c in cues]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_web_api.py -k put_cues -v`
Expected: PASS (všech 5).

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/web/app.py src/titulkovac/web/schemas.py tests/test_web_api.py
git commit -m "feat(web): PUT /api/jobs/{id}/cues — ulozi cely seznam (split/merge) s validaci"
```

---

## Task 3: Backend — `StaticFiles` mount + minimální `index.html`

**Files:**
- Create: `src/titulkovac/web/static/index.html` (zatím minimální, doplní Task 5)
- Modify: `src/titulkovac/web/app.py` (mount na konci `create_app`)
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Create the static dir with a minimal index.html**

Vytvoř `src/titulkovac/web/static/index.html`:

```html
<!doctype html>
<html lang="cs">
<head><meta charset="utf-8"><title>Titulkovač</title></head>
<body><h1>Titulkovač</h1></body>
</html>
```

(StaticFiles vyhodí chybu, když adresář při startu neexistuje — proto soubor nejdřív.)

- [ ] **Step 2: Write the failing tests**

Přidej na konec `tests/test_web_api.py`:

```python
def test_serves_index_html(tmp_path):
    client, store = _make_client(tmp_path, lambda *a: None)
    with client:
        r = client.get("/")
        assert r.status_code == 200
        assert "Titulkov" in r.text


def test_api_takes_precedence_over_static(tmp_path):
    client, store = _make_client(tmp_path, lambda *a: None)
    with client:
        assert client.get("/api/jobs").status_code == 200
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web_api.py -k "index_html or precedence" -v`
Expected: `test_serves_index_html` FAIL (404 — žádný mount).

- [ ] **Step 4: Add the mount**

V `src/titulkovac/web/app.py` přidej import nahoře:

```python
from fastapi.staticfiles import StaticFiles
```

A jako **úplně poslední řádky uvnitř `create_app`, těsně před `return app`** (musí být po všech `/api/*` routách, jinak by static chytal vše):

```python
    static_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
```

(Pozn.: `Path` je už importovaný v `app.py`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_web_api.py -v`
Expected: PASS (celý soubor — žádná regrese existujících testů; mount je až po API routách).

- [ ] **Step 6: Commit**

```bash
git add src/titulkovac/web/app.py src/titulkovac/web/static/index.html tests/test_web_api.py
git commit -m "feat(web): StaticFiles mount pro frontend (index.html), API ma prednost"
```

---

## Task 4: Frontend logika — `static/cues.js` + `node:test`

**Files:**
- Create: `src/titulkovac/web/static/cues.js` (ESM, bez DOM)
- Test: `tests/cues.test.mjs`

- [ ] **Step 1: Write the failing JS tests**

Vytvoř `tests/cues.test.mjs`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { formatTimecode, reindex, splitCueAtChar, mergeCues }
  from "../src/titulkovac/web/static/cues.js";

test("formatTimecode -> SRT format", () => {
  assert.equal(formatTimecode(0), "00:00:00,000");
  assert.equal(formatTimecode(1), "00:00:01,000");
  assert.equal(formatTimecode(3661.5), "01:01:01,500");
  assert.equal(formatTimecode(-2), "00:00:00,000");
});

test("reindex renumbers 1-based", () => {
  const out = reindex([{ index: 9 }, { index: 3 }, { index: 5 }]);
  assert.deepEqual(out.map((c) => c.index), [1, 2, 3]);
});

test("splitCueAtChar splits text + time by char ratio", () => {
  const cue = { index: 1, start: 0, end: 10, text: "abcdefghij",
                translations: { en: "X" }, edited: false };
  const [a, b] = splitCueAtChar(cue, 5);
  assert.equal(a.text, "abcde");
  assert.equal(b.text, "fghij");
  assert.equal(a.start, 0);
  assert.equal(a.end, 5);
  assert.equal(b.start, 5);
  assert.equal(b.end, 10);
  assert.equal(a.edited, true);
  assert.equal(b.edited, true);
  assert.deepEqual(b.translations, {});
});

test("splitCueAtChar clamps out-of-range positions", () => {
  const cue = { index: 1, start: 0, end: 10, text: "abcde", translations: {} };
  const [a, b] = splitCueAtChar(cue, 0);
  assert.ok(a.text.length >= 1 && b.text.length >= 1);
});

test("mergeCues joins text/time/translations", () => {
  const a = { index: 1, start: 0, end: 2, text: "Ahoj", translations: { en: "Hi" } };
  const b = { index: 2, start: 2, end: 4, text: "svete", translations: { en: "world" } };
  const m = mergeCues(a, b);
  assert.equal(m.text, "Ahoj svete");
  assert.equal(m.start, 0);
  assert.equal(m.end, 4);
  assert.equal(m.translations.en, "Hi world");
  assert.equal(m.edited, true);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test tests/cues.test.mjs`
Expected: FAIL — `Cannot find module …/cues.js`.

- [ ] **Step 3: Implement `cues.js`**

Vytvoř `src/titulkovac/web/static/cues.js`:

```javascript
// Čisté funkce pro práci s titulky. ŽÁDNÁ závislost na DOM -> testovatelné
// přes `node --test` i importovatelné v prohlížeči (<script type="module">).

export function formatTimecode(seconds) {
  if (seconds < 0) seconds = 0;
  let ms = Math.round(seconds * 1000);
  const h = Math.floor(ms / 3600000); ms -= h * 3600000;
  const m = Math.floor(ms / 60000); ms -= m * 60000;
  const s = Math.floor(ms / 1000); ms -= s * 1000;
  const p = (n, w) => String(n).padStart(w, "0");
  return `${p(h, 2)}:${p(m, 2)}:${p(s, 2)},${p(ms, 3)}`;
}

export function reindex(cues) {
  return cues.map((c, i) => ({ ...c, index: i + 1 }));
}

export function splitCueAtChar(cue, charPos) {
  const text = cue.text;
  const n = text.length;
  const pos = Math.max(1, Math.min(charPos, n - 1));
  const ratio = pos / n;
  const tMid = cue.start + (cue.end - cue.start) * ratio;
  const a = {
    index: cue.index, start: cue.start, end: tMid,
    text: text.slice(0, pos).trim(),
    translations: { ...(cue.translations || {}) }, edited: true,
  };
  const b = {
    index: cue.index + 1, start: tMid, end: cue.end,
    text: text.slice(pos).trim(),
    translations: {}, edited: true,
  };
  return [a, b];
}

export function mergeCues(a, b) {
  const langs = new Set([
    ...Object.keys(a.translations || {}),
    ...Object.keys(b.translations || {}),
  ]);
  const translations = {};
  for (const lang of langs) {
    const ta = (a.translations || {})[lang] || "";
    const tb = (b.translations || {})[lang] || "";
    translations[lang] = `${ta} ${tb}`.replace(/\s+/g, " ").trim();
  }
  return {
    index: a.index, start: a.start, end: b.end,
    text: `${a.text} ${b.text}`.replace(/\n/g, " ").replace(/\s+/g, " ").trim(),
    translations, edited: true,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test tests/cues.test.mjs`
Expected: PASS — `# pass 5  # fail 0`.

- [ ] **Step 5: Commit**

```bash
git add src/titulkovac/web/static/cues.js tests/cues.test.mjs
git commit -m "feat(web): cues.js — ciste funkce split/merge/reindex/timecode + node testy"
```

---

## Task 5: Frontend — `index.html` (nahrání + seznam úloh + WS) + `style.css`

**Files:**
- Create: `src/titulkovac/web/static/style.css`
- Modify: `src/titulkovac/web/static/index.html` (nahradit minimální stub plnou stránkou)

> Bez automatických testů (DOM/WS UX) — ověření = manuální smoke v Tasku 7.

- [ ] **Step 1: Create `style.css`**

Vytvoř `src/titulkovac/web/static/style.css`:

```css
:root { font-family: system-ui, sans-serif; }
body { margin: 0; padding: 1.5rem; max-width: 1100px; margin-inline: auto;
       color: #1a1a1a; }
h1 { font-size: 1.4rem; }
fieldset { border: 1px solid #ccc; border-radius: 8px; margin-bottom: 1rem; }
label { margin-right: .75rem; }
button { cursor: pointer; padding: .4rem .8rem; border-radius: 6px;
         border: 1px solid #888; background: #f5f5f5; }
button:hover { background: #e8e8e8; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: .35rem .5rem; text-align: left;
         vertical-align: top; font-size: .9rem; }
.progress { background: #eee; border-radius: 6px; height: 10px; overflow: hidden;
            width: 160px; }
.progress > div { background: #2d7; height: 100%; width: 0; transition: width .3s; }
.player { position: sticky; top: 0; background: #fff; padding: .75rem 0;
          border-bottom: 1px solid #ddd; z-index: 10; }
.player audio { width: 100%; }
tr.active { background: #fff7d6; }
td.tc { white-space: nowrap; font-variant-numeric: tabular-nums; width: 6.5rem; }
input.cell, textarea.cell { width: 100%; border: 1px solid transparent;
       font: inherit; background: transparent; resize: vertical; }
input.cell:focus, textarea.cell:focus { border-color: #2d7; background: #fff; }
tr.edited td:first-child::after { content: " ✎"; color: #c80; }
.err { color: #c00; }
```

- [ ] **Step 2: Replace `index.html` with the full page**

Přepiš `src/titulkovac/web/static/index.html`:

```html
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Titulkovač</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <h1>Titulkovač</h1>

  <fieldset>
    <legend>Nová epizoda</legend>
    <form id="upload-form">
      <p><input type="file" id="file" required></p>
      <p>
        <label><input type="checkbox" checked disabled> CS (originál)</label>
        <label><input type="checkbox" class="lang" value="en" checked> EN</label>
        <label><input type="checkbox" class="lang" value="de"> DE</label>
        <label><input type="checkbox" class="lang" value="pl"> PL</label>
        <label><input type="checkbox" class="lang" value="es"> ES</label>
        <label><input type="checkbox" class="lang" value="uk"> UK</label>
      </p>
      <button type="submit">Nahrát a zpracovat</button>
      <span id="upload-msg" class="err"></span>
    </form>
  </fieldset>

  <h2>Úlohy</h2>
  <table>
    <thead><tr><th>Soubor</th><th>Jazyky</th><th>Stav</th><th>Průběh</th><th></th></tr></thead>
    <tbody id="jobs"></tbody>
  </table>

  <script type="module">
    const tbody = document.getElementById("jobs");
    const sockets = new Map();      // job_id -> WebSocket
    const rows = new Map();         // job_id -> <tr>

    function wsUrl(jobId) {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      return `${proto}://${location.host}/api/jobs/${jobId}/progress`;
    }

    function renderRow(job) {
      let tr = rows.get(job.id);
      if (!tr) {
        tr = document.createElement("tr");
        rows.set(job.id, tr);
        tbody.prepend(tr);
      }
      const done = job.status === "done";
      const pct = Math.round(job.progress || 0);
      tr.innerHTML = `
        <td>${escapeHtml(job.filename)}</td>
        <td>${job.languages.join(", ")}</td>
        <td>${job.status === "error"
              ? `<span class="err">chyba: ${escapeHtml(job.error || "")}</span>`
              : `${escapeHtml(job.step)}`}</td>
        <td><div class="progress"><div style="width:${pct}%"></div></div> ${pct}%</td>
        <td>${done ? `<a href="/editor.html?job=${job.id}"><button>Otevřít editor</button></a>` : ""}</td>`;
      if (!done && job.status !== "error") subscribe(job.id);
    }

    function subscribe(jobId) {
      if (sockets.has(jobId)) return;
      const ws = new WebSocket(wsUrl(jobId));
      sockets.set(jobId, ws);
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);   // {step, pct}
        refreshJob(jobId);                  // znovu nacti plny JobOut
        if (msg.step === "done" || msg.step === "error") {
          ws.close(); sockets.delete(jobId);
        }
      };
      ws.onclose = () => sockets.delete(jobId);
    }

    async function refreshJob(jobId) {
      const r = await fetch(`/api/jobs/${jobId}`);
      if (r.ok) renderRow(await r.json());
    }

    async function loadJobs() {
      const r = await fetch("/api/jobs");
      const jobs = await r.json();
      jobs.sort((a, b) => a.id < b.id ? 1 : -1);
      jobs.forEach(renderRow);
    }

    function escapeHtml(s) {
      return String(s).replace(/[&<>"]/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    }

    document.getElementById("upload-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const msg = document.getElementById("upload-msg");
      msg.textContent = "";
      const file = document.getElementById("file").files[0];
      if (!file) return;
      const langs = [...document.querySelectorAll(".lang:checked")]
        .map((c) => c.value).join(",");
      const fd = new FormData();
      fd.append("file", file);
      fd.append("languages", langs || "en");
      const r = await fetch("/api/jobs", { method: "POST", body: fd });
      if (!r.ok) { msg.textContent = `Chyba ${r.status}`; return; }
      renderRow(await r.json());
      e.target.reset();
      document.querySelector('.lang[value="en"]').checked = true;
    });

    loadJobs();
  </script>
</body>
</html>
```

- [ ] **Step 3: Manual smoke (popis pro ověření v Tasku 7)**

Není automatický test. V Tasku 7 ověříme: `GET /` se vykreslí, formulář nahraje (s fake runnerem), seznam se objeví, progress bar jede přes WS.

- [ ] **Step 4: Commit**

```bash
git add src/titulkovac/web/static/index.html src/titulkovac/web/static/style.css
git commit -m "feat(web): index.html — nahrani + seznam uloh + WS progres"
```

---

## Task 6: Frontend — `editor.html` (přehrávač + tabulka + editace + split/merge + export)

**Files:**
- Create: `src/titulkovac/web/static/editor.html`

> Bez automatických testů (logika split/merge/timecode už pokrytá v Tasku 4). Ověření = manuální smoke v Tasku 7.

- [ ] **Step 1: Create `editor.html`**

Vytvoř `src/titulkovac/web/static/editor.html`:

```html
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Titulkovač — editor</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <p><a href="/">← zpět na úlohy</a></p>
  <div class="player">
    <audio id="audio" controls preload="metadata"></audio>
    <p>
      Překlad:
      <select id="lang"></select>
      <button id="dl-srt">Stáhnout SRT</button>
      <button id="dl-vtt">Stáhnout VTT</button>
      <span id="msg" class="err"></span>
    </p>
  </div>

  <table>
    <thead><tr>
      <th>#</th><th>start</th><th>end</th><th>text (cs)</th>
      <th id="th-tr">překlad</th><th>akce</th>
    </tr></thead>
    <tbody id="cues"></tbody>
  </table>

  <script type="module">
    import { reindex, splitCueAtChar, mergeCues, formatTimecode } from "/cues.js";

    const params = new URLSearchParams(location.search);
    const jobId = params.get("job");
    const audio = document.getElementById("audio");
    const tbody = document.getElementById("cues");
    const langSel = document.getElementById("lang");
    const msg = document.getElementById("msg");

    audio.src = `/api/jobs/${jobId}/media`;

    let cues = [];
    let job = null;
    let currentLang = null;  // null = jen cs

    async function load() {
      const jr = await fetch(`/api/jobs/${jobId}`);
      job = await jr.json();
      langSel.innerHTML = `<option value="">— (jen cs)</option>` +
        job.languages.map((l) => `<option value="${l}">${l}</option>`).join("");
      if (job.languages.length) { langSel.value = job.languages[0]; currentLang = job.languages[0]; }
      const cr = await fetch(`/api/jobs/${jobId}/cues`);
      if (!cr.ok) { msg.textContent = `Titulky nejsou hotové (${cr.status})`; return; }
      cues = await cr.json();
      render();
    }

    function render() {
      document.getElementById("th-tr").textContent =
        currentLang ? `překlad (${currentLang})` : "překlad";
      tbody.innerHTML = "";
      cues.forEach((cue, i) => tbody.appendChild(rowFor(cue, i)));
    }

    function rowFor(cue, i) {
      const tr = document.createElement("tr");
      tr.dataset.index = cue.index;
      if (cue.edited) tr.classList.add("edited");
      tr.innerHTML = `
        <td>${cue.index}</td>
        <td class="tc">${formatTimecode(cue.start)}</td>
        <td class="tc">${formatTimecode(cue.end)}</td>
        <td><textarea class="cell" rows="2" data-field="text">${escapeHtml(cue.text)}</textarea></td>
        <td><textarea class="cell" rows="2" data-field="tr"
             ${currentLang ? "" : "disabled"}>${escapeHtml(currentLang ? (cue.translations[currentLang] || "") : "")}</textarea></td>
        <td>
          <button data-act="split">rozdělit</button>
          <button data-act="merge">sloučit ↓</button>
        </td>`;
      // skok v audiu klikem na časový sloupec
      tr.querySelectorAll("td.tc").forEach((td) =>
        td.addEventListener("click", () => { audio.currentTime = cue.start; audio.play(); }));
      // inline edit -> PATCH
      const textArea = tr.querySelector('[data-field="text"]');
      textArea.addEventListener("change", () => patchCue(cue.index, { text: textArea.value }, i, "text", textArea.value));
      const trArea = tr.querySelector('[data-field="tr"]');
      if (currentLang) {
        trArea.addEventListener("change", () =>
          patchCue(cue.index, { translations: { [currentLang]: trArea.value } }, i, "tr", trArea.value));
      }
      tr.querySelector('[data-act="split"]').addEventListener("click", () => doSplit(i, textArea));
      tr.querySelector('[data-act="merge"]').addEventListener("click", () => doMerge(i));
      return tr;
    }

    async function patchCue(index, patch, i, field, value) {
      const r = await fetch(`/api/jobs/${jobId}/cues/${index}`, {
        method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!r.ok) { msg.textContent = `PATCH chyba ${r.status}`; return; }
      msg.textContent = "";
      if (field === "text") cues[i].text = value;
      else cues[i].translations[currentLang] = value;
      cues[i].edited = true;
    }

    async function putAll() {
      cues = reindex(cues);
      const r = await fetch(`/api/jobs/${jobId}/cues`, {
        method: "PUT", headers: { "content-type": "application/json" },
        body: JSON.stringify(cues),
      });
      if (!r.ok) { msg.textContent = `Uložení selhalo (${r.status})`; return; }
      cues = await r.json();
      msg.textContent = "";
      render();
    }

    function doSplit(i, textArea) {
      const pos = textArea.selectionStart || Math.floor(cues[i].text.length / 2);
      const [a, b] = splitCueAtChar(cues[i], pos);
      cues.splice(i, 1, a, b);
      putAll();
    }

    function doMerge(i) {
      if (i + 1 >= cues.length) { msg.textContent = "Není s čím sloučit"; return; }
      const m = mergeCues(cues[i], cues[i + 1]);
      cues.splice(i, 2, m);
      putAll();
    }

    // sync zvýraznění + auto-scroll
    audio.addEventListener("timeupdate", () => {
      const t = audio.currentTime;
      const active = cues.findIndex((c) => t >= c.start && t < c.end);
      [...tbody.children].forEach((tr, i) => {
        const on = i === active;
        tr.classList.toggle("active", on);
        if (on) tr.scrollIntoView({ block: "nearest" });
      });
    });

    langSel.addEventListener("change", () => { currentLang = langSel.value || null; render(); });

    function download(format) {
      const lang = currentLang || "cs";
      const url = `/api/jobs/${jobId}/export?lang=${lang}&format=${format}`;
      const a = document.createElement("a");
      a.href = url;
      a.download = `${job.filename}.${lang}.${format}`;
      document.body.appendChild(a); a.click(); a.remove();
    }
    document.getElementById("dl-srt").addEventListener("click", () => download("srt"));
    document.getElementById("dl-vtt").addEventListener("click", () => download("vtt"));

    function escapeHtml(s) {
      return String(s).replace(/[&<>"]/g, (c) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    }

    load();
  </script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add src/titulkovac/web/static/editor.html
git commit -m "feat(web): editor.html — prehravac + tabulka, inline edit, split/merge, export"
```

---

## Task 7: Packaging, README, plný test run + manuální smoke

**Files:**
- Modify: `pyproject.toml` (zabalit `static/` do balíčku)
- Modify: `README.md`

- [ ] **Step 1: Ensure `static/` is packaged**

Hatchling defaultně zabalí jen `.py` z `src/`. Aby se `static/*.html|css|js` dostaly do
wheelu, přidej do `pyproject.toml` (za `[build-system]` blok nebo k němu) sekci:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/titulkovac"]
artifacts = ["src/titulkovac/web/static/*"]
```

> Pro lokální běh z editovatelné instalace (`pip install -e .`) se servíruje přímo ze
> `src/…/static/`, takže funguje hned. Tato sekce je pro build/distribuci.

- [ ] **Step 2: Add README section**

Přidej do `README.md` sekci:

```markdown
## Frontend / náhled v prohlížeči

Po spuštění `titulkovac-web` otevři `http://127.0.0.1:8000/`:

- **Úvodní stránka** — nahraj epizodu, vyber cílové jazyky (CS je vždy), sleduj průběh.
- **Editor** (`Otevřít editor` u hotové úlohy) — přehrávač zvuku + tabulka titulků:
  - klik na čas = skok v audiu, přehrávaný titulek se zvýrazní,
  - editace textu i překladu (uloží se automaticky),
  - `rozdělit` / `sloučit ↓` pro úpravu dělení,
  - `Stáhnout SRT/VTT` pro zvolený jazyk.

Frontend je čisté HTML+JS bez buildu (servíruje ho FastAPI ze `web/static/`).
```

- [ ] **Step 3: Run the full Python test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS — všechny existující testy (Plán 1+2) + nové backend testy z Tasků 1–3. Žádná regrese.

- [ ] **Step 4: Run the JS tests**

Run: `node --test tests/cues.test.mjs`
Expected: PASS — 5/5.

- [ ] **Step 5: Manuální smoke (lokálně, bez GPU/API)**

Spusť server s fake daty pro ověření UI bez GPU. V jednom terminálu:

```bash
.venv/bin/pip install -e ".[web]"
TITULKOVAC_DATA=/tmp/titulkovac-smoke .venv/bin/titulkovac-web
```

Ověř v prohlížeči na `http://127.0.0.1:8000/`:
- [ ] stránka se vykreslí, formulář a checkboxy fungují,
- [ ] (volitelně, vyžaduje GPU+API pro reálný běh) — jinak ověř aspoň, že se úloha
      objeví v seznamu a progress bar reaguje.

> Plný E2E s reálným přepisem/překladem = tvůj smoke test (GPU + `ANTHROPIC_API_KEY`),
> stejně jako Task 13 z Plánu 1.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml README.md
git commit -m "chore(web): zabaleni static/ + README sekce frontend"
```

---

## Self-Review

**Spec coverage:**
- Vanilla HTML+JS, bez buildu, 2 stránky → Tasky 3,5,6 ✓
- `GET …/media` (audio.wav + Range) → Task 1 ✓
- `PUT …/cues` (split/merge, validace) → Task 2 ✓
- StaticFiles mount, API přednost → Task 3 ✓
- index.html: nahrání + checkboxy jazyků + seznam + WS progres + obnova po refreshi → Task 5 ✓
- editor.html: sticky přehrávač, sync+scroll, skok klikem, inline edit cs+překlad (PATCH), split/merge (PUT), export per jazyk → Task 6 ✓
- cues.js čisté funkce + referenční testy → Task 4 ✓
- Testy: backend endpointy + JS logika; klikací UX manuálně → Tasky 1–4 (auto) + 7 (manual) ✓
- Packaging static do balíčku → Task 7 ✓

**Placeholder scan:** žádné TBD/TODO; všechny kroky mají konkrétní kód a příkazy s očekávaným výstupem. ✓

**Type consistency:**
- `Cue`/`CueOut`/`CueIn` pole `index/start/end/text/translations/edited` konzistentní napříč Tasky 1,2,6. ✓
- JS funkce `reindex`/`splitCueAtChar`/`mergeCues`/`formatTimecode` definované v Tasku 4, importované v Tasku 6 stejnými jmény. ✓
- Cesta audio `job_dir/audio.wav` (Task 1) = totéž co `runner.py` vytváří. ✓
- Cues 1-based: `reindex` → `i+1`, `splitCueAtChar` b.index `cue.index+1`, PUT validace „vzestupné" akceptuje 1-based. ✓
- Endpoint cesty (`/api/jobs/{id}/media|cues|export|progress`) konzistentní mezi frontendem (Tasky 5,6) a backendem (Tasky 1,2 + existující). ✓
