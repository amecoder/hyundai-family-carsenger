from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

import pytest

from tests.test_server import FakeConsole, _serve, get

SCRIPT = Path(__file__).parent / "e2e" / "family_e2e.cjs"

# opt-in: needs Node plus a local playwright-core and Chromium (see README "가족 앱 E2E")
pytestmark = pytest.mark.skipif(not (os.environ.get("PW_CORE") and os.environ.get("CHROME")),
                                reason="PW_CORE·CHROME 환경변수가 없어 브라우저 E2E를 건너뜁니다")


def test_family_app_in_a_real_browser(tmp_path: Path) -> None:
    gen = _serve(FakeConsole())
    base = next(gen)
    try:
        out = subprocess.run(["node", str(SCRIPT), base, str(tmp_path)], capture_output=True, text=True, timeout=90, check=False)
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout.strip().splitlines()[-1]) == {"errors": []}

        _, inbox = get(base + "/api/car/inbox?after=0")
        pickup, cheer = inbox["commands"]
        assert (pickup["type"], pickup["by"], pickup["place"]) == ("pickup_request", "민지", "○○수학학원 앞")
        assert (cheer["type"], cheer["from"], cheer["text"]) == ("cheer", "민지", "조심히 와")
        assert 1500 <= cheer["duration_ms"] <= 3500
        with urllib.request.urlopen(f"{base}/api/audio/{cheer['audio_id']}", timeout=5) as r:
            assert r.headers["Content-Type"].startswith("audio/webm")
            assert len(r.read()) > 2000  # ~2 s of the fake microphone tone, not an empty container
        shots = os.environ.get("E2E_SHOTS")
        if shots:
            for png in tmp_path.glob("*.png"):
                (Path(shots) / png.name).write_bytes(png.read_bytes())
    finally:
        next(gen, None)
