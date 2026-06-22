from pathlib import Path
from titulkovac.media import build_ffmpeg_command


def test_build_ffmpeg_command():
    cmd = build_ffmpeg_command(Path("vstup.mp4"), Path("out.wav"))
    assert cmd[0] == "ffmpeg"
    assert "-i" in cmd
    assert "vstup.mp4" in cmd
    assert "out.wav" in cmd
    assert "16000" in cmd
    assert "1" in cmd  # mono
    assert "-y" in cmd
