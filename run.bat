@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo            TITULKOVAC - spousteni
echo ============================================
echo.

REM --- 1) Python ---
where python >nul 2>&1
if errorlevel 1 (
  echo [CHYBA] Python neni nainstalovany nebo neni v PATH.
  echo         Nainstaluj Python 3.11 nebo novejsi z:
  echo         https://www.python.org/downloads/
  echo         DULEZITE: pri instalaci zaskrtni "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

REM --- 2) ffmpeg ---
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [CHYBA] ffmpeg neni v PATH.
  echo         Nainstaluj ho prikazem v PowerShellu:  winget install Gyan.FFmpeg
  echo         (nebo stahni z https://ffmpeg.org a pridej do PATH), pak spust znovu.
  echo.
  pause
  exit /b 1
)

REM --- 3) API klic ---
if not exist "anthropic-klic.txt" (
  echo [CHYBA] Chybi soubor anthropic-klic.txt.
  echo         Vytvor vedle tohoto run.bat soubor "anthropic-klic.txt"
  echo         a vloz do nej JEN sam klic ^(zacina sk-ant-...^), nic jineho.
  echo.
  pause
  exit /b 1
)
set /p ANTHROPIC_API_KEY=<anthropic-klic.txt
if "!ANTHROPIC_API_KEY!"=="" (
  echo [CHYBA] Soubor anthropic-klic.txt je prazdny. Vloz do nej Claude API klic.
  echo.
  pause
  exit /b 1
)

REM --- 4) Prvni spusteni: vytvor venv + nainstaluj (jen pokud neexistuje) ---
if not exist ".venv\Scripts\python.exe" (
  echo === PRVNI SPUSTENI: pripravuji prostredi. ===
  echo === Stahne se nekolik GB ^(PyTorch + model^), muze to trvat 10-30 minut. ===
  echo === Nech okno otevrene a pockej. ===
  echo.
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  python -m pip install --upgrade pip
  echo.
  echo === Instaluji PyTorch s podporou GPU ^(CUDA 12.1^)... ===
  pip install torch --index-url https://download.pytorch.org/whl/cu121
  if errorlevel 1 (
    echo [CHYBA] Instalace PyTorch selhala. Zkus v navodu variantu cu118.
    pause
    exit /b 1
  )
  echo.
  echo === Instaluji Titulkovac a zbyle zavislosti... ===
  pip install -e ".[web,transcribe]"
  if errorlevel 1 (
    echo [CHYBA] Instalace zavislosti selhala. Zkopiruj cele okno a posli Matejovi.
    pause
    exit /b 1
  )
  echo.
  echo === Hotovo, prostredi je nainstalovane. ===
) else (
  call ".venv\Scripts\activate.bat"
)

REM --- 5) Spust server a otevri prohlizec ---
echo.
echo === Spoustim Titulkovac. Az se nize objevi "Uvicorn running", ===
echo === otevre se prohlizec na http://127.0.0.1:8000 ===
echo === Pro ukonceni zavri toto okno nebo stiskni Ctrl+C. ===
echo.
start "" http://127.0.0.1:8000
titulkovac-web

pause
