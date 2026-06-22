from __future__ import annotations

import json
from pathlib import Path

import typer

from titulkovac.config import AppConfig
from titulkovac.export import to_srt, to_vtt
from titulkovac.media import extract_audio
from titulkovac.pipeline import run_pipeline

app = typer.Typer(help="Titulkovac — automaticke titulky pro podcasty.")


@app.command()
def titulkuj(
    vstup: Path = typer.Argument(..., help="Vstupni video/audio soubor."),
    jazyky: str = typer.Option("en", help="Cilove jazyky, carkou (napr. en,de)."),
    vystup: Path = typer.Option(Path("./vystup"), help="Vystupni slozka."),
    format: str = typer.Option("srt", help="srt nebo vtt."),
    config_file: Path = typer.Option(None, help="JSON konfigurace (volitelne)."),
    device: str = typer.Option("cuda", help="cuda nebo cpu."),
) -> None:
    """Zpracuje soubor a vyrobi titulky v cestine + cilovych jazycich."""
    if format not in ("srt", "vtt"):
        raise typer.BadParameter("format musi byt 'srt' nebo 'vtt'.")
    if device not in ("cuda", "cpu"):
        raise typer.BadParameter("device musi byt 'cuda' nebo 'cpu'.")
    data = json.loads(config_file.read_text("utf-8")) if config_file else {}
    data.setdefault("target_languages", [j.strip() for j in jazyky.split(",")])
    cfg = AppConfig.from_dict(data)

    vystup.mkdir(parents=True, exist_ok=True)
    job_dir = vystup / (vstup.stem + "_job")
    job_dir.mkdir(exist_ok=True)

    typer.echo("1/4 Extrahuji audio (ffmpeg)…")
    wav = extract_audio(vstup, job_dir / "audio.wav")

    from titulkovac.adapters.whisperx_transcriber import WhisperXTranscriber
    from titulkovac.adapters.claude_boundary import ClaudeBoundaryProvider
    from titulkovac.adapters.claude_translator import ClaudeTranslator

    compute = "float16" if device == "cuda" else "int8"
    typer.echo("2/4 Prepis + zarovnani (WhisperX)…")
    typer.echo("3/4 Logicke deleni (Claude)…")
    typer.echo("4/4 Preklad (Claude)…")
    cues = run_pipeline(
        audio_path=wav, job_dir=job_dir, config=cfg,
        transcriber=WhisperXTranscriber(cfg.whisper_model, device, compute),
        boundary_provider=ClaudeBoundaryProvider(cfg.claude_model),
        translator=ClaudeTranslator(cfg.claude_model),
    )

    render = to_vtt if format == "vtt" else to_srt
    ext = "vtt" if format == "vtt" else "srt"
    for lang in [None, *cfg.target_languages]:
        suffix = cfg.source_language if lang is None else lang
        out_path = vystup / f"{vstup.stem}.{suffix}.{ext}"
        out_path.write_text(render(cues, lang), encoding="utf-8")
        typer.echo(f"  ✓ {out_path}")

    typer.echo("Hotovo.")


if __name__ == "__main__":
    app()
