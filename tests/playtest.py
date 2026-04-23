"""Scripted playtest — drives a real SnakeApp through a short session
and captures one SVG per beat. Good for eyeballing polish regressions.

    python -m tests.playtest

Beats:
  1. boot      — fresh mount, pre-tick
  2. eat       — food placed in front of snake, one tick, score bumps
  3. pause     — `space` pressed, banner visible
  4. stats     — `t` opens StatsScreen
  5. quit      — app exits cleanly

SVGs land in `tests/out/playtest_*.svg`.
"""

from __future__ import annotations

import asyncio
import os
import tempfile as _tempfile
from pathlib import Path

# Sandbox state writes so the playtest never touches the real file.
os.environ["XDG_DATA_HOME"] = _tempfile.mkdtemp(prefix="snake-playtest-")

from snake_tui.app import SnakeApp  # noqa: E402
from snake_tui.screens import StatsScreen  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


async def playtest() -> None:
    app = SnakeApp()
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause()
        app.save_screenshot(str(OUT / "playtest_1_boot.svg"))
        print("  1 boot  — OK")

        # Put food directly in front of the snake and tick once via the
        # engine so we have deterministic "just ate" state to screenshot.
        g = app.game
        head = g.snakes[0].head
        # Snake starts heading right from (5, cy).
        g.food = (head[0] + 1, head[1])
        score_before = g.snakes[0].score
        g.tick()
        app.board_view.refresh()
        app.status_panel.refresh_panel(force=True)
        await pilot.pause()
        app.save_screenshot(str(OUT / "playtest_2_eat.svg"))
        assert g.snakes[0].score > score_before, (
            f"score didn't bump: {g.snakes[0].score} vs {score_before}"
        )
        print(f"  2 eat   — score {score_before} -> {g.snakes[0].score}")

        # Pause.
        await pilot.press("space")
        await pilot.pause()
        assert app.game.paused, "space didn't pause"
        app.save_screenshot(str(OUT / "playtest_3_pause.svg"))
        print("  3 pause — paused")

        # Resume then open stats.
        await pilot.press("space")
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert isinstance(app.screen, StatsScreen), (
            f"stats screen didn't open, got {type(app.screen).__name__}"
        )
        app.save_screenshot(str(OUT / "playtest_4_stats.svg"))
        print("  4 stats — modal up")

        # Dismiss stats then quit cleanly.
        await pilot.press("escape")
        await pilot.pause()
        app.save_screenshot(str(OUT / "playtest_5_prequit.svg"))
        await pilot.press("q")
        await pilot.pause()
        print("  5 quit  — exited")


def main() -> None:
    print("snake-tui playtest")
    print("=" * 50)
    asyncio.run(playtest())
    print(f"\nSVGs under {OUT}")


if __name__ == "__main__":
    main()
