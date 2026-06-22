# Titulkovač — návrh (spec)

**Datum:** 2026-06-22
**Stav:** schváleno k implementaci

## Cíl a kontext

Nástroj na automatické titulkování dlouhých podcastů (3h epizody). Náhrada za
současný workflow v Subtitle Edit, kde uživatele (bratránek autora) štve:

1. **Placené limity** na minuty přepisu v cloudových nástrojích.
2. **Nelogické rozsekávání titulků** — věty se utínají uprostřed, dělení nedává smysl.

Vstup je **český zvuk/video**, výstupem jsou titulky v **češtině + angličtině + dalších
jazycích** (konfigurovatelný seznam, např. DE/PL/ES/UK).

### Klíčová rozhodnutí (proč zrovna takhle)

- **Přepis běží lokálně** na uživatelově stroji (Windows/Linux + NVIDIA GPU) přes
  open-source Whisper → **zdarma a bez jakýchkoli limitů na délku/minuty**. Tím mizí
  bolest č. 1. Cloudový přepis (OpenAI Whisper API) se zavrhuje: účtuje minuty a má
  25 MB limit na soubor → znovu zavádí přesně ten problém.
- **Překlad přes Claude API** (placené, ale řádově **koruny za epizodu** i přes více
  jazyků; s prompt cachingem a Batch API ještě méně). Volí se top kvalita.
- **Top priorita = časování + logické dělení vět.** To je hlavní odlišovač od běžných
  nástrojů a jádro celého návrhu (viz část 2).
- **Forma = lokální web-app** (běží u uživatele, ovládá se přes prohlížeč). Varianta
  zvolena pro pohodlí (jako online nástroj), ale zadarmo a bez limitů.
- **Rozsah MVP = generování + lehký náhled/editor** (přehrát video, upravit text/čas
  titulku, znovu rozdělit blok, export). NE plnohodnotná náhrada Subtitle Editu.

## 1. Architektura a komponenty

Systém se dělí na **jádro (pipeline)** a **webovou slupku**. Jádro nezná web, lze ho
spustit z CLI a testovat samostatně.

```
┌─────────────────── Prohlížeč (frontend) ───────────────────┐
│  Nahrání souboru · Progres úloh · Náhled (video+tabulka)   │
│  Editace titulku (text/čas) · Re-split bloku · Export      │
└───────────────────────────┬────────────────────────────────┘
                            │ HTTP / WebSocket (progres)
┌───────────────────────────▼────────────────────────────────┐
│                  FastAPI backend (lokální)                  │
│  - REST API (úlohy, titulky, export)                       │
│  - Fronta úloh na pozadí (3h epizoda běží dlouho)          │
└───────────────────────────┬────────────────────────────────┘
                            │ volá
┌───────────────────────────▼────────────────────────────────┐
│                    JÁDRO (Python modul)                     │
│  1. media     → ffmpeg: video → audio (wav 16kHz)          │
│  2. transcribe→ WhisperX: přepis + zarovnání na slova      │
│  3. segment   → engine: profi pravidla + Claude (dělení)   │
│  4. translate → Claude: cue-by-cue, časy se zachovají      │
│  5. export    → .srt / .vtt (per jazyk)                    │
└─────────────────────────────────────────────────────────────┘
```

### Moduly jádra (každý samostatný, testovatelný)

| Modul | Co dělá | Vstup → Výstup |
|---|---|---|
| `media` | Vytáhne audio z videa/audia | soubor → wav 16 kHz mono |
| `transcribe` | WhisperX přepis + forced alignment | wav → slova s časy `[{slovo, start, end}]` |
| `segment` | Seskupí slova do titulků (pravidla + Claude) | slova → cues `[{start, end, text}]` |
| `translate` | Přeloží cues do cílových jazyků | cues → `{cs:[…], en:[…], …}` |
| `export` | Vyrenderuje finální soubory | cues → `.srt`/`.vtt` |

### Datový model

- **`job`** (jedna práce): `id`, vstupní soubor, stav
  (`čeká/přepisuje/segmentuje/překládá/hotovo/chyba`), progres %, seznam jazyků.
- **`cue`** (jeden titulek): `index`, `start`, `end`, originální text (cs), překlady
  (`{en, de, …}`), příznak „ručně upraveno".

Frontend i backend pracují nad **stejným seznamem cues**. Úprava v náhledu se uloží;
export bere aktuální stav.

## 2. Kvalitní jádro — časování a logické dělení

Tady se rozhoduje, jestli bude nástroj lepší než stávající řešení.

### 2a. Přesné časování (`transcribe`)

- **WhisperX** = Whisper `large-v3` (nejlepší čeština) + **forced alignment**
  (wav2vec2). Výstup je seznam **slov, každé s přesným `start`/`end`** nalepeným na
  zvuk — ne odhad po blocích.
- Volitelně VAD (detekce řeči) ořízne dlouhé pauzy.
- Výsledek je pevná časová „kostra" na úrovni slov. Časy se dál nikdy nedopočítávají,
  jen se slova seskupují.

### 2b. Logické dělení (`segment`) — dvoufázové

**Fáze 1 — sémantické hranice (Claude):**
Claude dostane přepis s interpunkcí a úkol rozdělit text na titulkové bloky tak, aby
každý dával smysl jako celek — láme se na koncích vět, u čárek, před spojkami; nikdy
neutíná uprostřed jmenné/předložkové vazby. Vrátí hranice (na kterých slovech dělit).
Claude rozumí významu věty → nevznikne nesmysl typu „pšenice se letos / urodila velmi
dobře".

**Fáze 2 — tvrdá pravidla profi titulkářů (deterministický kód):**
Sémantické bloky se doladí podle měřitelných pravidel:

| Pravidlo | Výchozí (nastavitelné) |
|---|---|
| Max. znaků na řádek (CPL) | ~42 |
| Max. řádků | 2 |
| Čtecí rychlost (CPS) | ~15–17 znaků/s |
| Min. délka titulku | ~1 s |
| Max. délka titulku | ~7 s |
| Min. mezera mezi titulky | ~2 snímky |

Pokud sémantický blok přesáhne CPL/CPS, kód ho rozdělí na **další logické hranici**
(ne natvrdo uprostřed). Časy se berou ze slovní kostry (start = první slovo, end =
poslední slovo bloku).

> Kombinace = **významově správné dělení (Claude) + technicky korektní titulky
> (pravidla)**. Ani jedno samo nestačí.

### 2c. Překlad se zachováním časování (`translate`)

- Překládá se **cue po cue, s kontextem okolních titulků** (návaznost), časy zůstávají
  1:1 z češtiny.
- Když je překlad delší/kratší a porušil by CPL/CPS, projede stejnými pravidly z 2b
  (rozdělení/zkrácení) — **časová kostra se nemění**.
- Engine: **Claude** (drží styl a kontext celé pasáže).

### 2d. Konfigurace kvality

Všechna pravidla (CPL, CPS, jazyky, model) jsou v jednom konfiguračním souboru /
nastavení appky, aby šla přísnost dělení doladit podle vkusu.

## 3. Datový tok, chyby, technologie, testování

### 3a. Datový tok (jedna epizoda)

```
1. Nahrání        → soubor uložen lokálně, vznikne job (stav: čeká)
2. media          → ffmpeg vytáhne wav                     (~5 %)
3. transcribe     → WhisperX přepis + alignment            (~50 %, nejdelší krok)
4. segment        → Claude hranice + pravidla → cues (cs)  (~70 %)
5. translate      → Claude přeloží do EN + dalších         (~90 %)
6. náhled         → kontrola/úpravy v prohlížeči
7. export         → .srt/.vtt pro každý jazyk → stáhne / uloží
```

Dlouhé kroky (3–5) běží na pozadí; frontend dostává **průběh přes WebSocket**.

### 3b. Odolnost a ošetření chyb

- **Mezikroky se ukládají na disk** (přepis, slovní časy, cues jako JSON). Pád
  překladu/appky → **nepřepisuje se znovu** (nejdražší krok); pokračuje od posledního
  hotového kroku. U 3h epizod zásadní.
- **GPU/CUDA chybí / málo paměti** → jasná hláška + fallback na CPU (pomalejší) nebo
  menší model.
- **Výpadek API překladu** (síť, rate-limit) → SDK retry + uložení rozdělané práce;
  jde spustit znovu jen překlad.
- **Dlouhý soubor** → audio se zpracovává po částech (chunking), žádný délkový/velikostní
  limit.
- Každý job má **log**.

### 3c. Technologie

| Vrstva | Volba | Proč |
|---|---|---|
| Jádro | Python 3.11+ | Whisper/WhisperX jsou Python |
| Přepis | WhisperX (faster-whisper + wav2vec2) | přesné slovní časy, lokálně, zdarma |
| Audio | ffmpeg | standard |
| Backend | FastAPI + fronta úloh | async, WebSocket progres |
| Překlad/dělení | Claude API (`claude-opus-4-8`; na běžný překlad lze levnější model) | top kvalita |
| Frontend | lehký web (React/Vite nebo HTML+JS) | náhled video + tabulka titulků |
| Formáty | `.srt`, `.vtt` (rozšiřitelné o `.ass`) | co je potřeba |

### 3d. Testování

- **Jádro = jednotkové testy** modul po modulu. Zvlášť `segment` — kontrola, že dělení
  dodržuje CPL/CPS a neutíná vazby; testuje se na fixních datech s „fake" Claude (bez
  reálného volání API).
- **Export** = porovnání s referenčními `.srt` (formát, časové kódy).
- **Pravidla** = deterministická, samostatně testovatelná.
- Reálný end-to-end test na krátké ukázce (pár minut) před nasazením na 3h epizodu.

### 3e. Mimo rozsah MVP (YAGNI)

- Ne plnohodnotný editor (jen lehký náhled/úpravy — varianta B).
- Ne desktop `.exe` balení (běží jako lokální web; přidatelné později — Tauri/Electron).
- Ne diarizace (rozpoznávání mluvčích) — možné rozšíření.

## Otevřené body k doladění při plánování

- Konkrétní seznam cílových jazyků (kromě CS+EN).
- Volba frontend stacku (React/Vite vs. prosté HTML+JS) — dle preferencí.
- Konkrétní model Claude na překlad vs. na segmentaci (kvalita vs. cena).
