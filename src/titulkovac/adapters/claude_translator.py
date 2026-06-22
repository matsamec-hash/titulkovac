from __future__ import annotations

import json

import anthropic

from titulkovac.models import Cue

_SYSTEM = (
    "Jsi profesionalni prekladatel titulku. Prelozis seznam titulku do "
    "ciloveho jazyka. Preklad ma byt prirozeny a strucny (titulky se ctou "
    "rychle). Zachovej poradi i POCET polozek 1:1. U kazde polozky prelozis "
    "jen text, neslucuj ani nedel titulky."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["translations"],
    "additionalProperties": False,
}


class ClaudeTranslator:
    """Realny Translator pres Claude. Preklada po davkach pro kontext."""

    def __init__(self, model: str = "claude-opus-4-8",
                 batch_size: int = 50) -> None:
        self.client = anthropic.Anthropic()
        self.model = model
        self.batch_size = batch_size

    def translate(self, cues: list[Cue], target_lang: str) -> list[str]:
        out: list[str] = []
        for start in range(0, len(cues), self.batch_size):
            batch = cues[start:start + self.batch_size]
            out.extend(self._translate_batch(batch, target_lang))
        return out

    def _translate_batch(self, batch: list[Cue], lang: str) -> list[str]:
        items = [c.text.replace("\n", " ") for c in batch]
        payload = json.dumps({"target_language": lang, "items": items},
                             ensure_ascii=False)
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": payload}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        result = json.loads(text)["translations"]
        if len(result) != len(batch):
            raise ValueError(
                f"Claude vratil {len(result)} prekladu, ocekavano {len(batch)}")
        return result
