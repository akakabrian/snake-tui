"""Synth sound blips — eat / die / pause. Off by default.

Same recipe as 2048-tui:
  * stdlib wave module synth + cache in XDG_RUNTIME_DIR
  * playback via paplay / aplay / afplay
  * per-sound debounce so rapid chains don't pile up subprocesses
  * disabled silently if no player is found — never crash over audio
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import time
import wave
from pathlib import Path
from typing import Callable


_PLAYER: str | None = None
for _cmd in ("paplay", "aplay", "afplay"):
    if shutil.which(_cmd):
        _PLAYER = _cmd
        break


def _runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR") or "/tmp"
    d = Path(base) / "snake-tui-sounds"
    d.mkdir(parents=True, exist_ok=True)
    return d


# (freq_hz, duration_s, amplitude)
_TONES: dict[str, tuple[float, float, float]] = {
    "eat":   (820.0, 0.055, 0.32),
    "die":   (150.0, 0.280, 0.32),
    "pause": (440.0, 0.060, 0.18),
    "start": (660.0, 0.090, 0.25),
}


def _synthesise(path: Path, freq: float, dur: float, amp: float) -> None:
    sr = 22_050
    n = int(sr * dur)
    attack = int(sr * 0.010)
    release = int(sr * 0.010)
    frames = bytearray()
    for i in range(n):
        env = 1.0
        if i < attack:
            env = i / max(1, attack)
        elif i > n - release:
            env = max(0.0, (n - i) / max(1, release))
        sample = amp * env * math.sin(2 * math.pi * freq * i / sr)
        frames += struct.pack("<h", int(sample * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))


def _ensure_wav(name: str) -> Path | None:
    if name not in _TONES:
        return None
    path = _runtime_dir() / f"{name}.wav"
    if not path.exists() or path.stat().st_size < 1000:
        freq, dur, amp = _TONES[name]
        try:
            _synthesise(path, freq, dur, amp)
        except OSError:
            return None
    return path


class Sounds:
    def __init__(self, enabled: bool | None = None) -> None:
        if enabled is None:
            enabled = os.environ.get("SNAKE_SOUND", "").lower() in (
                "1", "true", "yes"
            )
        self.enabled = bool(enabled) and _PLAYER is not None
        self._last_played: dict[str, float] = {}
        self._debounce_s = 0.120
        self._test_hook: Callable[[str, Path], None] | None = None

    @property
    def available(self) -> bool:
        return _PLAYER is not None

    def toggle(self) -> bool:
        if _PLAYER is None:
            self.enabled = False
            return False
        self.enabled = not self.enabled
        return self.enabled

    def play(self, name: str) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        last = self._last_played.get(name, 0.0)
        if now - last < self._debounce_s:
            return
        self._last_played[name] = now
        path = _ensure_wav(name)
        if path is None:
            return
        if self._test_hook is not None:
            try:
                self._test_hook(name, path)
            except Exception:
                pass
            return
        if _PLAYER is None:
            return
        try:
            subprocess.Popen(
                [_PLAYER, str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, ValueError):
            self.enabled = False
