from titulkovac.models import Cue
from titulkovac.export import to_srt, format_timestamp
from titulkovac.export import to_vtt, format_timestamp_vtt


def test_format_timestamp():
    assert format_timestamp(0.0) == "00:00:00,000"
    assert format_timestamp(3661.5) == "01:01:01,500"
    assert format_timestamp(1.234) == "00:00:01,234"


def test_to_srt_original_text():
    cues = [
        Cue(index=1, start=0.0, end=2.0, text="Dobry den"),
        Cue(index=2, start=2.5, end=4.0, text="prvni\ndruhy"),
    ]
    out = to_srt(cues)
    expected = (
        "1\n"
        "00:00:00,000 --> 00:00:02,000\n"
        "Dobry den\n"
        "\n"
        "2\n"
        "00:00:02,500 --> 00:00:04,000\n"
        "prvni\ndruhy\n"
    )
    assert out == expected


def test_to_srt_uses_translation_when_lang_given():
    cues = [Cue(index=1, start=0.0, end=1.0, text="Ahoj",
                translations={"en": "Hello"})]
    out = to_srt(cues, lang="en")
    assert "Hello" in out
    assert "Ahoj" not in out


def test_format_timestamp_vtt_uses_dot():
    assert format_timestamp_vtt(3661.5) == "01:01:01.500"


def test_to_vtt_has_header_and_blocks():
    cues = [Cue(index=1, start=0.0, end=2.0, text="Dobry den")]
    out = to_vtt(cues)
    assert out.startswith("WEBVTT\n\n")
    assert "00:00:00.000 --> 00:00:02.000" in out
    assert "Dobry den" in out
