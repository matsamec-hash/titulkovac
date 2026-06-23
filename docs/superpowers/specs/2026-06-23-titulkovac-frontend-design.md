# Titulkovač — frontend (Plán 3) — návrh (spec)

**Datum:** 2026-06-23
**Stav:** schváleno k implementaci
**Navazuje na:** `2026-06-22-titulkovac-design.md` (celkový návrh), Plán 1 (jádro CLI) a Plán 2 (web backend FastAPI) — oba hotové a zmergované.

## Cíl

Poslední vrstva nástroje (varianta B = lehký náhled/editor): webové UI nad existujícím
FastAPI backendem. Uživatel (bratránek) nahraje epizodu, sleduje průběh, a po dokončení
zkontroluje a doladí titulky v prohlížeči, pak exportuje `.srt`/`.vtt` pro každý jazyk.

NE plnohodnotná náhrada Subtitle Editu — jen kontrola, drobná editace textu/času a
ruční split/merge dělení.

## Klíčová rozhodnutí (schváleno 2026-06-23)

- **Stack: vanilla HTML + JS, bez buildu, bez frameworku, bez CDN.** Funguje offline u
  uživatele. FastAPI servíruje statické soubory přes `StaticFiles`.
- **Struktura: dvě statické stránky.** `index.html` (nahrání + seznam úloh + progres) a
  `editor.html?job=ID` (přehrávač + tabulka titulků). Žádný router.
- **Náhled = jen zvuk.** Přehrává se vytažené `audio.wav` (16 kHz) přes `<audio>`. Pro
  podcast stačí; žádné kodekové problémy s originálním videem. Video je možné rozšíření.
- **Re-split bloku přes Claude/backend = mimo MVP.** Místo toho ruční **split/merge na
  klientu** (přepočet času podle poměru znaků). Pokrývá většinu oprav dělení.
- **Editovatelné je vše:** originál (cs) i překlady; jazyky se volí checkboxy.
- **Layout: přehrávač sticky nahoře, tabulka na plnou šířku pod ním.**

## 1. Architektura

```
┌──────────────── Prohlížeč (statické soubory) ────────────────┐
│  index.html   → nahrání + seznam úloh + WS progres           │
│  editor.html  → <audio> + tabulka cues + editace + export    │
│  static/cues.js → čisté funkce (split/merge/reindex/timecode)│
└───────────────────────────┬──────────────────────────────────┘
                            │ fetch (REST) + WebSocket (progres)
┌───────────────────────────▼──────────────────────────────────┐
│              FastAPI backend (Plán 2, existuje)              │
│  + GET  /api/jobs/{id}/media   (NOVÉ — servíruje audio.wav)  │
│  + PUT  /api/jobs/{id}/cues    (NOVÉ — uloží celý seznam)    │
│  + StaticFiles mount na "/"    (NOVÉ — servíruje frontend)   │
└───────────────────────────────────────────────────────────────┘
```

Frontend je čistě statický; veškerá logika přes API. Backend dostane **tři malé přídavky**,
jinak se ho nedotýkáme.

## 2. Nové backend přídavky

### 2a. `GET /api/jobs/{id}/media`
Servíruje `audio.wav` z `job_dir` přes `FileResponse` **s podporou HTTP Range** (nutné pro
přetáčení v `<audio>` — prohlížeč posílá `Range:` a očekává `206 Partial Content`).

- 404 když job neexistuje nebo `audio.wav` ještě není (job se ještě nedostal za krok `media`).
- `media_type="audio/wav"`.
- Pokud Starlette `FileResponse` nepokrývá Range pro daný případ, fallback = naservírovat
  `audio.wav` přes dedikovaný `StaticFiles` mount nad datovým adresářem (StaticFiles Range umí).

### 2b. `PUT /api/jobs/{id}/cues`
Přijme celý seznam cues (JSON pole) a uloží přes `save_cues` (atomický zápis už v
`persistence.py`). Použití: po split/merge, kdy se mění počet/indexy titulků.

- **Validace:** neprázdný seznam; indexy `0..n-1` vzestupně bez děr; pro každý cue
  `start ≤ end`. Při porušení → `422`/`400` s jasnou hláškou.
- 404 když job neexistuje; 409 když cues ještě nejsou hotové (job neprošel segmentací).
- Vrací uloženou (normalizovanou) sadu jako `list[CueOut]`.

→ Dvě úrovně zápisu: `PATCH …/cues/{index}` pro drobnou úpravu jednoho titulku (zůstává
levné), `PUT …/cues` pro strukturální změnu (split/merge).

### 2c. StaticFiles mount
`app.mount("/", StaticFiles(directory=<frontend_dir>, html=True))` registrovaný **až po
všech `/api/*` routách**, aby API mělo přednost. `/` → `index.html`, `/editor.html` →
editor. Adresář frontendu = `src/titulkovac/web/static/` (součást balíčku).

## 3. `index.html` — nahrání + seznam úloh

**Nahrání:**
- `<input type="file">` + checkboxy jazyků: **CS** (zaškrtnuté, disabled — vždy přítomné),
  + EN / DE / PL / ES / UK (volitelné).
- Odeslání → `POST /api/jobs` (multipart `file`, `languages="en,de,…"` — bez `cs`, ta je
  originál). Po `201` se job přidá do seznamu.

**Seznam úloh** (`GET /api/jobs` při načtení stránky):
- Tabulka: název, jazyky, stav, progress bar (%).
- Pro **neukončené** úlohy (`status` ∉ {done, error}) se připojí WS `…/progress` a živě
  aktualizuje krok (`media/transcribe/segment/translate`) + %.
- `done` → tlačítko **„Otevřít editor"** (`editor.html?job=ID`).
- `error` → zobrazí `error` text z `JobOut`.

**Obnova po refreshi:** seznam se vždy načte z `GET /api/jobs`, takže běžící i hotové úlohy
přežijí reload; WS se připojuje jen k neukončeným.

## 4. `editor.html` — přehrávač + tabulka

**Layout (sticky přehrávač nahoře):**
- Pruh: `<audio controls src="/api/jobs/{id}/media">` + přepínač zobrazeného jazyka
  překladu + tlačítka **Stáhnout SRT / VTT**.
- Pod ním tabulka na plnou šířku.

**Tabulka** (`GET …/cues`): sloupce `#`, `start`, `end`, **text (cs)**, **překlad (zvolený
jazyk)**, akce (split / merge-dolů).

- **Sync s přehráváním:** podle `audio.currentTime` se aktuální cue zvýrazní a auto-scrolluje.
- **Skok:** klik na řádek → `audio.currentTime = cue.start`.
- **Inline editace:** `text` (cs) i `překlad` jsou editovatelná pole; `start`/`end` číselně.
  Změna (blur/Enter) → `PATCH …/cues/{index}` s daným polem; řádek označen `edited`.
- **Split** (na klientu): rozdělí cue v pozici kurzoru v textu.
  `čas_dělení = start + (end-start) * (pozice_kurzoru / délka_textu)`; text se rozsekne na
  kurzoru; reindexace; uloží `PUT …/cues`.
- **Merge** (na klientu): spojí cue se sousedem dolů — text mezerou, `start` = první,
  `end` = druhý; reindexace; `PUT …/cues`.

**Export:** přepínač jazyka řídí i export. Tlačítko → `GET …/export?lang=&format=` a
stažení přes `<a download>` (lang `cs` = originál; jinak kód jazyka).

## 5. `static/cues.js` — čisté funkce (testovatelné)

Riziková logika bez DOM závislostí, aby šla referenčně otestovat:

- `splitCueAtChar(cue, charPos)` → `[cueA, cueB]` (rozdělení textu + času dle poměru znaků).
- `mergeCues(cueA, cueB)` → spojený cue (text mezerou, start prvního, end druhého).
- `reindex(cues)` → přepíše `index` na `0..n-1`.
- `formatTimecode(seconds)` → `HH:MM:SS,mmm` (pro zobrazení, formát jako `export.py`).

Tyto funkce nesahají na DOM; volá je UI vrstva v `editor.html`.

## 6. Testování

Repo je Python/pytest, bez JS toolchainu (záměr „bez buildu").

**Backend (TDD, pytest):**
- `GET …/media`: `200` + obsah `audio.wav`; **Range request → `206`** + správný úsek;
  `404` když audio chybí / job neexistuje.
- `PUT …/cues`: uloží a znovu načte (round-trip); validace odmítne prázdný seznam,
  nevzestupné/děravé indexy, `start>end` (`422`/`400`); `404`/`409` hrany.
- Statika: `GET /` → `index.html`; `/api/*` má přednost před static mountem.

**Frontend logika (referenční pytest):**
- Matematika `splitCueAtChar` (poměr znaků → čas), `mergeCues`, `reindex`, `formatTimecode`
  se ozrcadlí do pytest testu se stejnými vstupy/výstupy jako JS verze (formát časů jako
  `export.py`/`rules.py`). Tím je algoritmus pokrytý.

**Mimo automatické testy (manuální UAT uživatelem):** klikací chování — sync zvýraznění a
auto-scroll, inline edit UX, drag/skok, stahování souborů. Je to lokální nástroj varianty B.

## 7. Mimo rozsah (YAGNI)

- Re-split bloku přes Claude/backend (možné rozšíření — fáze 2).
- Náhled originálního videa (zatím jen audio).
- Plnohodnotný editor (titulky timeline, waveform, drag&drop hranic).
- JS unit-test toolchain (npm/jest) — popřelo by „bez buildu".
- Auth / více současných uživatelů — lokální nástroj pro jednoho.

## 8. Otevřené body (rozhodnout při plánování/implementaci)

- Přesné chování Range u `FileResponse` vs. fallback `StaticFiles` — ověřit testem.
- Drobnost UX: jak označit `edited` řádek vizuálně (barva/ikona) — kosmetika.
