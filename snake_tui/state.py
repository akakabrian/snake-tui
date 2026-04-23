"""Persistence — best scores per (width, height, wrap) combination.

Stored in `$XDG_DATA_HOME/snake-tui/state.json`. Per-config best because
40x20-nowrap and 40x20-wrap are meaningfully different difficulties.

Schema:

    {
      "best_per_config": {"40x20:nowrap": 420, "40x20:wrap": 680, ...},
      "last_width": 40,
      "last_height": 20,
      "last_wrap": false,
      "last_two_player": false
    }
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "snake-tui"
    return Path.home() / ".local" / "share" / "snake-tui"


STATE_PATH = _data_dir() / "state.json"


def _config_key(width: int, height: int, wrap: bool) -> str:
    return f"{int(width)}x{int(height)}:{'wrap' if wrap else 'nowrap'}"


def load() -> dict[str, Any]:
    """Read the state blob. Return a sane default on missing/corrupt."""
    if not STATE_PATH.exists():
        return {
            "best_per_config": {},
            "last_width": 40, "last_height": 20,
            "last_wrap": False, "last_two_player": False,
        }
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        try:
            STATE_PATH.rename(STATE_PATH.with_suffix(".corrupt.json"))
        except OSError:
            pass
        return {
            "best_per_config": {},
            "last_width": 40, "last_height": 20,
            "last_wrap": False, "last_two_player": False,
        }
    data.setdefault("best_per_config", {})
    data.setdefault("last_width", 40)
    data.setdefault("last_height", 20)
    data.setdefault("last_wrap", False)
    data.setdefault("last_two_player", False)
    return data


def save(data: dict[str, Any]) -> None:
    """Atomic write — tmp file then rename."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    tmp.replace(STATE_PATH)


def best_for_config(data: dict[str, Any],
                    width: int, height: int, wrap: bool) -> int:
    key = _config_key(width, height, wrap)
    return int(data.get("best_per_config", {}).get(key, 0))


def record_best(data: dict[str, Any],
                width: int, height: int, wrap: bool,
                score: int) -> bool:
    """Update best for this config if beaten. Returns True on new record."""
    key = _config_key(width, height, wrap)
    cur = int(data.get("best_per_config", {}).get(key, 0))
    if score > cur:
        data.setdefault("best_per_config", {})[key] = int(score)
        return True
    return False


def all_bests(data: dict[str, Any]) -> dict[str, int]:
    """Sorted copy of the best-per-config dict."""
    raw = data.get("best_per_config", {}) or {}
    return {k: int(v) for k, v in sorted(raw.items())}
