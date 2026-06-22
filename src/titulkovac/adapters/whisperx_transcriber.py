from __future__ import annotations

from pathlib import Path

from titulkovac.models import Word


class WhisperXTranscriber:
    """Realny Transcriber. Vyzaduje `pip install titulkovac[transcribe]`.

    device: 'cuda' (GPU) nebo 'cpu' (fallback).
    compute_type: 'float16' pro GPU, 'int8' pro CPU.
    """

    def __init__(self, model_name: str = "large-v3", device: str = "cuda",
                 compute_type: str = "float16") -> None:
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type

    def transcribe(self, audio_path: Path, language: str = "cs") -> list[Word]:
        import whisperx  # lazy import (tezka zavislost)

        audio = whisperx.load_audio(str(audio_path))
        model = whisperx.load_model(
            self.model_name, self.device, compute_type=self.compute_type,
            language=language,
        )
        result = model.transcribe(audio, language=language)

        align_model, metadata = whisperx.load_align_model(
            language_code=language, device=self.device)
        aligned = whisperx.align(
            result["segments"], align_model, metadata, audio, self.device,
            return_char_alignments=False,
        )

        words: list[Word] = []
        for seg in aligned["segments"]:
            for w in seg.get("words", []):
                if "start" in w and "end" in w:
                    words.append(Word(text=w["word"].strip(),
                                      start=float(w["start"]),
                                      end=float(w["end"])))
        return words
