"""Perf baseline — hot paths so regressions are visible.

    python -m tests.perf

Tracks:
  * Game.tick() on a 40×20 board (gameplay hot path)
  * Game.tick() on a big 80×40 board
  * BoardView.render_line — single row (paint hot path)
  * BoardView full-viewport render (42 rows) — per-frame cost
  * full random game until death (end-to-end)
"""

from __future__ import annotations

import random
import statistics
import time

from snake_tui.engine import Game


def time_iter(label: str, fn, iters: int) -> float:
    fn()  # warm
    samples: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    med = statistics.median(samples)
    print(f"  {label:40s}  {med:8.3f} ms  (median of {iters})")
    return med


def bench_tick_40x20() -> None:
    rng = random.Random(1)
    g = Game(width=40, height=20, rng=rng)

    def run() -> None:
        # Keep the game alive by toggling direction randomly but safely.
        if not g.game_over:
            g.tick()
        else:
            g.new_game()
    time_iter("Game.tick() 40x20", run, iters=2000)


def bench_tick_80x40() -> None:
    rng = random.Random(2)
    g = Game(width=80, height=40, rng=rng)

    def run() -> None:
        if not g.game_over:
            g.tick()
        else:
            g.new_game()
    time_iter("Game.tick() 80x40", run, iters=2000)


def bench_render_line() -> None:
    from snake_tui.app import BoardView
    g = Game(width=40, height=20, rng=random.Random(7))
    # Grow the snake to a realistic mid-game length.
    g.snakes[0].body = [(x, 10) for x in range(20, 5, -1)]
    g.food = (30, 12)
    bv = BoardView(g)
    from textual.geometry import Size
    bv._size = Size(60, 24)  # pyright: ignore[reportPrivateUsage]

    def run() -> None:
        bv.render_line(10)
    time_iter("BoardView.render_line — single row", run, iters=5000)


def bench_render_all() -> None:
    from snake_tui.app import BoardView
    g = Game(width=40, height=20, rng=random.Random(7))
    g.snakes[0].body = [(x, 10) for x in range(20, 5, -1)]
    bv = BoardView(g)
    from textual.geometry import Size
    bv._size = Size(60, 24)  # pyright: ignore[reportPrivateUsage]

    def run() -> None:
        for y in range(24):
            bv.render_line(y)
    time_iter("BoardView full viewport (24 rows)", run, iters=500)


def bench_random_game() -> None:
    """Full game to game-over with random (legal) moves."""
    rng = random.Random(123)

    def run() -> None:
        g = Game(width=40, height=20, rng=rng)
        while not g.game_over and g.ticks < 5000:
            # Pick a random legal direction occasionally.
            if rng.random() < 0.1:
                hd = rng.choice(["up", "down", "left", "right"])
                g.set_heading(0, hd)  # type: ignore[arg-type]
            g.tick()
    time_iter("full random game to death", run, iters=20)


def main() -> None:
    print("snake-tui perf baseline")
    print("=" * 50)
    bench_tick_40x20()
    bench_tick_80x40()
    bench_render_line()
    bench_render_all()
    bench_random_game()


if __name__ == "__main__":
    main()
