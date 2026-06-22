from __future__ import annotations

import anthropic

from titulkovac.models import Word

_SYSTEM = (
    "Jsi expert na strihani titulku. Dostanes prepis jako ocislovana slova. "
    "Vrat indexy slov, na kterych ma ZACINAT novy titulek tak, aby kazdy "
    "titulek daval smysl jako celek: lam na koncich vet, u carek a pred "
    "spojkami; NIKDY neutínej uprostred jmenne nebo predlozkove vazby. "
    "Index 0 nevracej (prvni titulek zacina vzdy slovem 0)."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "boundaries": {"type": "array", "items": {"type": "integer"}}
    },
    "required": ["boundaries"],
    "additionalProperties": False,
}


class ClaudeBoundaryProvider:
    """Realny BoundaryProvider pres Claude. Zpracovava po oknech, aby se
    dlouhy prepis vesel do kontextu a drzela se konzistence."""

    def __init__(self, model: str = "claude-opus-4-8",
                 window_words: int = 400) -> None:
        self.client = anthropic.Anthropic()
        self.model = model
        self.window_words = window_words

    def boundaries(self, words: list[Word]) -> list[int]:
        all_boundaries: list[int] = []
        for offset in range(0, len(words), self.window_words):
            chunk = words[offset:offset + self.window_words]
            local = self._boundaries_for_chunk(chunk)
            if offset > 0:
                all_boundaries.append(offset)
            all_boundaries.extend(offset + b for b in local if 0 < b < len(chunk))
        return sorted(set(all_boundaries))

    def _boundaries_for_chunk(self, chunk: list[Word]) -> list[int]:
        import json
        numbered = "\n".join(f"{i}: {w.text}" for i, w in enumerate(chunk))
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": numbered}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return list(json.loads(text)["boundaries"])
