from __future__ import annotations

from pathlib import Path
from typing import Callable

from titulkovac.config import AppConfig
from titulkovac.media import extract_audio
from titulkovac.pipeline import run_pipeline


def make_default_runner(device: str = "cuda",
                        config_overrides: dict | None = None):
    """Vrati runner(input_path, job_dir, languages, on_progress) pro JobManager.
    Pouziva realne adaptery (WhisperX + Claude)."""

    def runner(input_path: Path, job_dir: Path, languages: list[str],
               on_progress: Callable[[str, float], None]) -> None:
        from titulkovac.adapters.whisperx_transcriber import WhisperXTranscriber
        from titulkovac.adapters.claude_boundary import ClaudeBoundaryProvider
        from titulkovac.adapters.claude_translator import ClaudeTranslator

        data = dict(config_overrides or {})
        data["target_languages"] = list(languages)
        cfg = AppConfig.from_dict(data)

        on_progress("extract", 2.0)
        wav = extract_audio(input_path, job_dir / "audio.wav")

        compute = "float16" if device == "cuda" else "int8"
        run_pipeline(
            audio_path=wav, job_dir=job_dir, config=cfg,
            transcriber=WhisperXTranscriber(cfg.whisper_model, device, compute),
            boundary_provider=ClaudeBoundaryProvider(cfg.claude_model),
            translator=ClaudeTranslator(cfg.claude_model),
            on_progress=on_progress,
        )

    return runner
