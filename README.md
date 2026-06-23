# Titulkovač

Automatické titulkování podcastů: **lokální přepis** (WhisperX, zdarma, bez limitů na délku) +
**logické dělení vět a překlad přes Claude**. Vstup je český zvuk/video, výstup titulky v češtině
a dalších jazycích (`.srt` / `.vtt`).

Tohle je **Plán 1 — jádro pipeline jako CLI**. Web-app s náhledem/editorem přijde v plánech 2 a 3.

## Proč

Řeší dvě bolesti běžných nástrojů u 3hodinových epizod:
1. **Placené limity na minuty přepisu** → přepis běží lokálně na GPU zdarma a bez limitů.
2. **Nelogické rozsekávání titulků** → dělení dělá Claude sémanticky (nerozbíjí vazby) +
   profi pravidla (max 2 řádky, ~42 znaků/řádek, čtecí rychlost).

## Požadavky

- Python 3.11+
- `ffmpeg` v PATH
- pro přepis: NVIDIA GPU + CUDA (rychlé), nebo CPU fallback (pomalé)
- `ANTHROPIC_API_KEY` v prostředí (pro dělení vět a překlad)

## Instalace

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,transcribe]"
```

> `transcribe` extra doinstaluje `whisperx`. Bez něj jádro i testy běží (přepis je za seamem),
> ale reálný přepis nepůjde spustit.

## Použití

```bash
export ANTHROPIC_API_KEY=sk-ant-...
titulkovac titulkuj epizoda.mp4 --jazyky en,de --format srt
# na CPU (bez GPU):
titulkovac titulkuj epizoda.mp4 --device cpu
```

Výstup: `vystup/epizoda.cs.srt`, `vystup/epizoda.en.srt`, `vystup/epizoda.de.srt`, …

Mezivýsledky (přepis, slovní časy, cues) se ukládají do `vystup/epizoda_job/`. Při přerušení se
běh **obnoví od posledního hotového kroku** — nejdražší krok (přepis) se neopakuje.

## Konfigurace (volitelně)

JSON soubor přes `--config-file`:
```json
{
  "target_languages": ["en", "de", "pl"],
  "claude_model": "claude-opus-4-8",
  "whisper_model": "large-v3",
  "rules": { "max_chars_per_line": 42, "max_cps": 16.0, "max_lines": 2 }
}
```

## Architektura

Jádro (`media → transcribe → segment → translate → export`) je oddělené od CLI a externí
závislosti (WhisperX, Claude) jsou za protokoly (`seams.py`), takže logika dělení a exportu se
testuje deterministicky s fake implementacemi.

```bash
.venv/bin/python -m pytest -q   # 37 testů
```

## Známá omezení (MVP jádra)

- `min_duration` se zatím nevynucuje (příliš krátké titulky se neprodlužují) — doladí se ve web vrstvě.
- Překlad delší než 2 řádky × limit znaků zůstane 2řádkový (best-effort) — řeší stručný překlad a
  ruční editace v náhledu (Plán 3).
- Bez diarizace (rozpoznávání mluvčích).

## Web rozhraní (Plán 2)

```bash
pip install -e ".[web,transcribe]"
export ANTHROPIC_API_KEY=sk-ant-...
export TITULKOVAC_DEVICE=cuda   # nebo cpu
titulkovac-web                  # bezi na http://127.0.0.1:8000
```

REST API:
- `POST /api/jobs` (multipart: `file`, `languages=en,de`) → vytvori a zaradi ulohu
- `GET /api/jobs` / `GET /api/jobs/{id}` → seznam / stav
- `GET /api/jobs/{id}/cues` → titulky; `PATCH /api/jobs/{id}/cues/{index}` → editace
- `GET /api/jobs/{id}/export?lang=cs&format=srt` → stazeni titulku
- WebSocket `GET /api/jobs/{id}/progress` → JSON `{step, pct}`

Data (nahrane soubory + mezikroky + job.json) jsou v `./data/jobs/` (zmen `TITULKOVAC_DATA`).

## Frontend / náhled v prohlížeči

Po spuštění `titulkovac-web` otevři `http://127.0.0.1:8000/`:

- **Úvodní stránka** — nahraj epizodu, vyber cílové jazyky (CS je vždy), sleduj průběh.
- **Editor** (`Otevřít editor` u hotové úlohy) — přehrávač zvuku + tabulka titulků:
  - klik na čas = skok v audiu, přehrávaný titulek se zvýrazní,
  - editace textu i překladu (uloží se automaticky),
  - `rozdělit` / `sloučit ↓` pro úpravu dělení,
  - `Stáhnout SRT/VTT` pro zvolený jazyk.

Frontend je čisté HTML+JS bez buildu (servíruje ho FastAPI ze `web/static/`).
