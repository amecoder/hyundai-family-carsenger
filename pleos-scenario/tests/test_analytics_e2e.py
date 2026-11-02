from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path

import pytest

from scenario.analytics import EventStore
from scenario.server import make_server
from tests.test_server import FakeConsole

SCRIPT = Path(__file__).parent / "e2e" / "analytics_e2e.cjs"

# opt-in: needs Node plus a local playwright-core and Chromium (see README "가족 앱 E2E")
pytestmark = pytest.mark.skipif(not (os.environ.get("PW_CORE") and os.environ.get("CHROME")),
                                reason="PW_CORE·CHROME 환경변수가 없어 브라우저 E2E를 건너뜁니다")


def test_consent_exchange_and_dashboard_in_a_real_browser(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "a.sqlite", tmp_path / "salt")
    srv = make_server(FakeConsole(), host="127.0.0.1", port=0, voice_dir=Path("/nonexistent-voice-dir"), analytics=store)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        out = subprocess.run(["node", str(SCRIPT), base, str(tmp_path)], capture_output=True, text=True, timeout=90, check=False)
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout.strip().splitlines()[-1]) == {"errors": []}
        assert store.count() == 0  # consent was withdrawn at the end, so nothing is kept
        shots = os.environ.get("E2E_SHOTS")
        if shots:
            for png in tmp_path.glob("*.png"):
                (Path(shots) / png.name).write_bytes(png.read_bytes())
    finally:
        srv.shutdown()
