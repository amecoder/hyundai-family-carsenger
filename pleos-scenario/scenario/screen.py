from __future__ import annotations

import io
import logging
import os
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

Capture = Callable[[], bytes]
Resize = Callable[[bytes], tuple[bytes, str]]


def default_adb() -> str:
    home = os.environ.get("ANDROID_HOME", str(Path.home() / "Android" / "Sdk"))
    return str(Path(home) / "platform-tools" / "adb")


def adb_capture(adb: str) -> Capture:
    def capture() -> bytes:
        out = subprocess.run([adb, "exec-out", "screencap", "-p"], capture_output=True, timeout=8, check=False)
        if out.returncode != 0 or not out.stdout.startswith(b"\x89PNG"):
            raise RuntimeError(f"에뮬레이터 화면을 가져오지 못했습니다: {out.stderr.decode(errors='replace')[:200]}")
        return out.stdout

    return capture


def pillow_resize(max_width: int = 1280) -> Resize | None:
    """Shrink the 2560x1440 PNG to a small JPEG when Pillow is available; otherwise serve the PNG as is."""
    try:
        from PIL import Image
    except ImportError:
        return None

    def resize(png: bytes) -> tuple[bytes, str]:
        im = Image.open(io.BytesIO(png)).convert("RGB")
        if im.width > max_width:
            im = im.resize((max_width, round(im.height * max_width / im.width)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        return buf.getvalue(), "image/jpeg"

    return resize


class ScreenGrabber:
    """Captures the emulator screen in the background, only while someone keeps asking for it."""

    def __init__(self, capture: Capture, interval: float = 0.8, idle_timeout: float = 10.0, resize: Resize | None = None) -> None:
        self._capture = capture
        self._interval = interval
        self._idle_timeout = idle_timeout
        self._resize = resize
        self._lock = threading.Lock()
        self._image: bytes | None = None
        self._ctype: str | None = None
        self._last_request = 0.0
        self._thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self.error: str | None = None

    def latest(self) -> tuple[bytes | None, str | None]:
        with self._lock:
            self._last_request = time.monotonic()
            if not (self._thread and self._thread.is_alive()) and not self._stopped.is_set():
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
            return self._image, self._ctype

    def stop(self) -> None:
        self._stopped.set()

    def _loop(self) -> None:
        while not self._stopped.is_set():
            with self._lock:
                idle = time.monotonic() - self._last_request > self._idle_timeout
            if idle:
                return
            try:
                png = self._capture()
                image, ctype = self._resize(png) if self._resize else (png, "image/png")
                with self._lock:
                    self._image, self._ctype = image, ctype
                self.error = None
            except Exception as e:  # keep serving the last good frame; the UI shows the error text
                self.error = str(e)
                log.warning("screen capture failed: %s", e)
            self._stopped.wait(self._interval)
