# Titulkovač — návod pro Windows (krok za krokem)

Ahoj! Tohle je nástroj na automatické titulkování podcastů. Běží u tebe na počítači
(kvůli grafické kartě), ovládá se přes prohlížeč. Stačí ho jednou nainstalovat.

> **Co k tomu potřebuješ:** Windows s **NVIDIA grafickou kartou**, internet a chvíli
> trpělivosti při prvním spuštění (stahuje se pár GB).

---

## 1. Nainstaluj Python

1. Jdi na **https://www.python.org/downloads/** a stáhni nejnovější Python (3.11+).
2. Spusť instalátor a hned na první obrazovce **zaškrtni „Add python.exe to PATH"** (dole). Pak „Install Now".

## 2. Nainstaluj ffmpeg

1. Otevři **PowerShell** (klikni na Start, napiš „PowerShell", Enter).
2. Vlož a potvrď příkaz:
   ```
   winget install Gyan.FFmpeg
   ```
3. Po instalaci **zavři a znovu otevři** PowerShell (aby se načetlo PATH).

## 3. Stáhni Titulkovač

1. Jdi na **https://github.com/matsamec-hash/titulkovac**
2. Zelené tlačítko **„Code" → „Download ZIP"**.
3. Rozbal ZIP třeba na plochu. Vznikne složka `titulkovac-master` (nebo podobně).

## 4. Vlož API klíč

Matěj ti pošle přes WhatsApp klíč, který začíná `sk-ant-...`.

1. V rozbalené složce (tam, kde je soubor **`run.bat`**) vytvoř nový textový soubor
   a pojmenuj ho přesně **`anthropic-klic.txt`**.
2. Otevři ho v Poznámkovém bloku, vlož do něj **jen ten klíč** (nic víc, žádné mezery
   navíc) a ulož.

> Tento soubor zůstává jen u tebe, nikam se neposílá.

## 5. Spusť to

1. Ve složce **dvakrát klikni na `run.bat`**.
2. **Při úplně prvním spuštění** se stahuje a instaluje hodně věcí (PyTorch + model
   pro přepis) — klidně **10–30 minut**. Nech černé okno otevřené a počkej.
3. Až bude hotovo, samo se otevře prohlížeč na **http://127.0.0.1:8000**.
4. Příště už je spuštění během pár vteřin (instaluje se jen jednou).

## 6. Jak to používat

1. Na úvodní stránce vyber zvukový/video soubor epizody, zaškrtni jazyky (čeština je vždy)
   a dej **„Nahrát a zpracovat"**.
2. Sleduj průběh. U dlouhé epizody trvá přepis nejdéle — to je normální.
3. Až je úloha „done", klikni **„Otevřít editor"**:
   - přehraj zvuk, klikem na čas skočíš na daný titulek,
   - oprav text nebo překlad (uloží se samo),
   - tlačítky rozdělíš/sloučíš titulky,
   - nakonec **„Stáhnout SRT"** (nebo VTT) pro vybraný jazyk.

---

## Když něco nejede

- **„Python neni nainstalovany"** — viz krok 1, hlavně zaškrtnout „Add to PATH", pak restart okna.
- **„ffmpeg neni v PATH"** — viz krok 2, po instalaci zavři a znovu otevři PowerShell/okno.
- **Instalace PyTorch selhala / nefunguje GPU** — tvoje karta možná chce jinou verzi CUDA.
  Otevři `run.bat` v Poznámkovém bloku a v řádku s `download.pytorch.org/whl/cu121`
  změň `cu121` na `cu118`, ulož, smaž složku `.venv` a spusť `run.bat` znovu.
- **Cokoli jiného** — zkopíruj celý obsah černého okna a pošli Matějovi.

## Aktualizace (když Matěj něco vylepší)

Stáhni znovu ZIP (krok 3) a přepiš složku — soubor `anthropic-klic.txt` a složku `.venv`
si nech (ušetříš opětovnou instalaci).
