"""Entry point — `python play.py [--width W --height H --wrap --two-player]`."""

from __future__ import annotations

import argparse

from snake_tui.app import run


def main() -> None:
    p = argparse.ArgumentParser(prog="snake-tui")
    p.add_argument("--width", type=int, default=40,
                   help="playfield width (10..80, default 40)")
    p.add_argument("--height", type=int, default=20,
                   help="playfield height (8..40, default 20)")
    p.add_argument("--wrap", action="store_true",
                   help="wrap around edges instead of dying")
    p.add_argument("--two-player", action="store_true",
                   help="enable hotseat two-player (P2 uses ijkl)")
    args = p.parse_args()
    if not 10 <= args.width <= 80:
        p.error("width must be 10..80")
    if not 8 <= args.height <= 40:
        p.error("height must be 8..40")
    run(width=args.width, height=args.height,
        wrap=args.wrap, two_player=args.two_player)


if __name__ == "__main__":
    main()
