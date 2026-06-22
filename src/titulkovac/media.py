from __future__ import annotations

import subprocess
from pathlib import Path


def build_ffmpeg_command(src: Path, dst: Path) -> list[str]:
    """Sestavi ffmpeg prikaz: libovolne video/audio -> wav 16kHz mono PCM."""
    return [
        "ffmpeg", "-y",
        "-i", str(src),
        "-ac", "1",            # mono
        "-ar", "16000",        # 16 kHz
        "-c:a", "pcm_s16le",   # 16-bit PCM
        str(dst),
    ]


def extract_audio(src: Path, dst: Path) -> Path:
    """Spusti ffmpeg. Vyhodi RuntimeError s vystupem pri chybe."""
    cmd = build_ffmpeg_command(src, dst)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg selhal (kod {proc.returncode}):\n{proc.stderr[-2000:]}"
        )
    return dst
