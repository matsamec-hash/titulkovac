from __future__ import annotations

from dataclasses import dataclass, field, replace

from titulkovac.models import SegmentRules


@dataclass(frozen=True)
class AppConfig:
    source_language: str = "cs"
    target_languages: list[str] = field(default_factory=lambda: ["en"])
    claude_model: str = "claude-opus-4-8"
    whisper_model: str = "large-v3"
    rules: SegmentRules = field(default_factory=SegmentRules)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        base = cls()
        rules = base.rules
        if "rules" in data:
            rules = replace(base.rules, **data["rules"])
        return cls(
            source_language=data.get("source_language", base.source_language),
            target_languages=list(
                data.get("target_languages", base.target_languages)),
            claude_model=data.get("claude_model", base.claude_model),
            whisper_model=data.get("whisper_model", base.whisper_model),
            rules=rules,
        )
