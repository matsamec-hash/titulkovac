from titulkovac.config import AppConfig
from titulkovac.models import SegmentRules


def test_appconfig_defaults():
    cfg = AppConfig()
    assert cfg.source_language == "cs"
    assert "en" in cfg.target_languages
    assert cfg.claude_model == "claude-opus-4-8"
    assert isinstance(cfg.rules, SegmentRules)


def test_appconfig_from_dict_overrides():
    cfg = AppConfig.from_dict({
        "target_languages": ["en", "de"],
        "claude_model": "claude-haiku-4-5",
        "rules": {"max_chars_per_line": 38, "max_cps": 15.0},
    })
    assert cfg.target_languages == ["en", "de"]
    assert cfg.claude_model == "claude-haiku-4-5"
    assert cfg.rules.max_chars_per_line == 38
    assert cfg.rules.max_cps == 15.0
    assert cfg.rules.max_lines == 2
