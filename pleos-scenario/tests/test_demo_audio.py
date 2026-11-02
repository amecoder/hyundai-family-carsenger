from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_server import FakeConsole, _serve

SCRIPT = Path(__file__).parent / "e2e" / "demo_audio_check.cjs"

pytestmark = pytest.mark.skipif(not (shutil.which("node") and shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                reason="node·ffmpeg가 없어 녹화 소리 조립 테스트를 건너뜁니다")


def tone(path: Path, freq: int) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=0.5",
                    "-ar", "48000", str(path)], check=True)


def test_sounds_are_placed_where_the_car_made_them(tmp_path: Path) -> None:
    voice = tmp_path / "voice"
    (voice / "car_speech_clova").mkdir(parents=True)
    tone(voice / "car_speech_clova" / "car_08.wav", 440)  # car_speech_lines.json: "알겠어요. 가족에게 전할게요."
    tone(tmp_path / "cheer.wav", 880)
    work = tmp_path / "work"
    work.mkdir()
    gen = _serve(FakeConsole())
    base = next(gen)
    try:
        out = subprocess.run(["node", str(SCRIPT), base, str(work), str(tmp_path / "cheer.wav")], capture_output=True, text=True,
                             timeout=90, check=False, env={**os.environ, "PLEOS_VOICE_DIR": str(voice)})
    finally:
        next(gen, None)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])

    speech, clip = result["placed"]
    # the recorded sentence is used instead of synthesizing it, and each sound sits where the car made it
    assert (speech["kind"], speech["file"]) == ("speech", str(voice / "car_speech_clova" / "car_08.wav"))
    assert clip["kind"] == "clip"
    assert 950 <= speech["offsetMs"] <= 1300
    assert 1950 <= clip["offsetMs"] <= 2400
    starts = result["onsets"][:2]
    assert [round(s - p["offsetMs"] / 1000, 2) for s, p in zip(starts, (speech, clip), strict=True)] == pytest.approx([0, 0], abs=0.05)
    assert result["mixed"] == {"codec": "aac", "rate": 48000}
    assert result["silent"] == {"codec": "aac", "rate": 48000}  # a scenario where the car stays quiet still gets a track


@pytest.mark.skipif(not (os.environ.get("PW_CORE") and os.environ.get("CHROME")),
                    reason="PW_CORE·CHROME 환경변수가 없어 브라우저 E2E를 건너뜁니다")
def test_voice_credit_is_on_screen_from_the_first_frames() -> None:
    """CLOVA Dubbing's free plan needs the credit for the video's first 5 s, even when the page loads slowly (2 s here)."""
    gen = _serve(FakeConsole())
    base = next(gen)
    try:
        out = subprocess.run(["node", str(SCRIPT.with_name("voice_credit_check.cjs")), base], capture_output=True,
                             text=True, timeout=90, check=False)
    finally:
        next(gen, None)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["shown"] is not None and result["shown"] <= 500
    assert result["gone"] is not None and 5000 <= result["gone"] <= 7000
    assert result["inPhone"] == 0  # counted while the badge is up: the phone iframe gets no second badge
