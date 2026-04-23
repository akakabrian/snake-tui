"""QA harness — drives SnakeApp through Textual Pilot + asserts on
live engine state.

    python -m tests.qa            # run everything
    python -m tests.qa collide    # subset by substring

Exit code = number of failures. Each scenario writes an SVG screenshot
under `tests/out/`.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
import tempfile as _tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

# Tests must not clobber the user's real state file.
os.environ["XDG_DATA_HOME"] = _tempfile.mkdtemp(prefix="snake-qa-")

from snake_tui.app import SnakeApp  # noqa: E402
from snake_tui.engine import Game, Snake  # noqa: E402
from snake_tui import state as state_mod  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


@dataclass
class Scenario:
    name: str
    fn: Callable[[SnakeApp, "object"], Awaitable[None]]


# ---------- helpers ----------

def setup_snake(game: Game, body: list[tuple[int, int]],
                heading: str = "right") -> None:
    """Overwrite P1 with a known body & heading, no food placed yet."""
    s = game.snakes[0]
    s.body = list(body)
    s.heading = heading  # type: ignore[assignment]
    s.pending_heading = heading  # type: ignore[assignment]
    s.alive = True
    s.growth_debt = 0
    s.death_cause = None


def set_food(game: Game, cell: tuple[int, int]) -> None:
    game.food = cell


# ---------- scenarios ----------

async def s_mount_clean(app, pilot):
    assert app.game is not None
    assert app.board_view is not None
    assert app.status_panel is not None
    # One snake, length 3, food placed somewhere on the board.
    assert len(app.game.snakes) == 1
    assert app.game.snakes[0].length == 3
    assert app.game.food is not None


async def s_default_size(app, pilot):
    assert app.game.width == 40
    assert app.game.height == 20
    assert not app.game.wrap
    assert not app.game.two_player


async def s_heading_changes(app, pilot):
    """Press up — P1 heading should queue to 'up'. Snake initially
    heading right, so up is a legal 90° turn."""
    assert app.game.snakes[0].pending_heading == "right"
    await pilot.press("up")
    await pilot.pause()
    assert app.game.snakes[0].pending_heading == "up"


async def s_180_blocked(app, pilot):
    """Snake heading right, length 3 — pressing left should NOT change
    heading (would reverse into self)."""
    assert app.game.snakes[0].heading == "right"
    await pilot.press("left")
    await pilot.pause()
    # Still "right" — the 180° was rejected.
    assert app.game.snakes[0].pending_heading == "right"


async def s_wasd_move(app, pilot):
    """wasd should be aliases for arrows."""
    await pilot.press("w")
    await pilot.pause()
    assert app.game.snakes[0].pending_heading == "up"


async def s_tick_advances_snake(app, pilot):
    """Direct engine tick — head moves one cell in current heading."""
    g = app.game
    head_before = g.snakes[0].head
    g.tick()
    head_after = g.snakes[0].head
    assert head_after == (head_before[0] + 1, head_before[1]), (
        f"expected head +x, got {head_before} → {head_after}"
    )


async def s_wall_kill(app, pilot):
    """Snake near right wall, wrap off — one tick into the wall should
    kill it and flip game_over."""
    g = app.game
    # Place the snake at the right edge.
    setup_snake(g, [(g.width - 1, 5), (g.width - 2, 5), (g.width - 3, 5)],
                heading="right")
    set_food(g, (0, 0))
    g.tick()
    assert g.game_over, "hitting wall didn't flip game_over"
    assert g.snakes[0].death_cause == "wall"


async def s_wrap_survives(app, pilot):
    """With wrap on, running off the right edge re-emerges on the left."""
    g = app.game
    g.wrap = True
    setup_snake(g, [(g.width - 1, 5), (g.width - 2, 5), (g.width - 3, 5)],
                heading="right")
    set_food(g, (0, 0))
    g.tick()
    assert not g.game_over, "wrap didn't save from wall"
    assert g.snakes[0].head == (0, 5), g.snakes[0].head


async def s_food_grow_and_score(app, pilot):
    """Placing food directly in front of the snake — one tick grows by
    1 and scores +food_value."""
    g = app.game
    setup_snake(g, [(5, 5), (4, 5), (3, 5)], heading="right")
    set_food(g, (6, 5))
    len_before = g.snakes[0].length
    score_before = g.snakes[0].score
    g.tick()
    # After tick: head at (6, 5), growth_debt spent next tick (body
    # grows on the tick AFTER the food tick). Score up immediately.
    assert g.snakes[0].score == score_before + g.food_value
    # Do one more tick — length should now be len_before + 1.
    g.tick()
    assert g.snakes[0].length == len_before + 1, (
        f"expected length {len_before + 1}, got {g.snakes[0].length}"
    )
    # New food placed.
    assert g.food is not None
    assert g.food != (6, 5)  # it's moved


async def s_self_collision(app, pilot):
    """Form a snake that will head-eat its own body."""
    g = app.game
    # Layout:
    #  (2,5)(3,5)(4,5)(5,5)
    #  (2,6)           (5,6)
    #  (2,7)(3,7)(4,7)(5,7)  <- head at (2,7) heading up into body? No,
    # easier: make a 4-long straight snake about to turn into itself.
    # Body order: head, ..., tail. Heading up but the cell above head is
    # a body cell.
    setup_snake(g, [(3, 5), (3, 6), (3, 7), (2, 7), (2, 8)], heading="up")
    # Head is (3, 5); up → (3, 4). That's empty. Instead, have it turn
    # so it eats itself.
    setup_snake(g, [(3, 5), (2, 5), (2, 6), (3, 6), (3, 7)], heading="right")
    # Head (3,5). Right → (4,5). That's empty. Let's force a collision:
    # head (3,5), going DOWN into (3,6) which is a body cell → self.
    setup_snake(g, [(3, 5), (2, 5), (2, 6), (3, 6), (3, 7)], heading="down")
    # Make sure the food isn't at (3, 6).
    set_food(g, (10, 10))
    g.tick()
    assert g.game_over, "self-collision didn't fire"
    assert g.snakes[0].death_cause == "self"


async def s_tail_vacate_ok(app, pilot):
    """A snake of length N moving into the cell its own tail just
    vacated should NOT die — the tail pops before the head commits.
    Tested by building a compact U and turning into the tail's square."""
    g = app.game
    # Body cells (head→tail): (3,5),(3,6),(4,6),(4,5). Head (3,5) heading
    # up. If we instead go RIGHT, next cell is (4,5) — currently the tail.
    # Tail vacates this tick, so moving there should be fine.
    setup_snake(g, [(3, 5), (3, 6), (4, 6), (4, 5)], heading="right")
    # No food in the way.
    set_food(g, (20, 10))
    g.tick()
    assert not g.game_over, (
        "tail-vacate move wrongly killed snake "
        f"(death={g.snakes[0].death_cause})"
    )
    assert g.snakes[0].head == (4, 5)


async def s_pause_halts_tick(app, pilot):
    """Paused game's tick() is a no-op."""
    g = app.game
    before = list(g.snakes[0].body)
    g.paused = True
    g.tick()
    assert list(g.snakes[0].body) == before, "tick ran while paused"


async def s_pause_toggle_key(app, pilot):
    """Space toggles pause."""
    assert not app.game.paused
    await pilot.press("space")
    await pilot.pause()
    assert app.game.paused
    await pilot.press("space")
    await pilot.pause()
    assert not app.game.paused


async def s_new_game_resets(app, pilot):
    """Force a game-over, call action_new_game, verify clean reset."""
    g = app.game
    g.game_over = True
    g.snakes[0].alive = False
    g.snakes[0].score = 42
    # No modal expected because score < 100 won't prompt; and game_over
    # path in the action skips confirm anyway.
    await pilot.press("n")
    await pilot.pause()
    assert not app.game.game_over
    assert app.game.snakes[0].length == 3
    assert app.game.snakes[0].score == 0


async def s_wrap_toggle_key(app, pilot):
    """Shift-W toggles wrap."""
    before = app.game.wrap
    await pilot.press("W")
    await pilot.pause()
    assert app.game.wrap != before
    # Board reset.
    assert app.game.snakes[0].length == 3


async def s_two_player_toggle(app, pilot):
    """'2' toggles two-player. Snake count should flip 1 ↔ 2."""
    assert len(app.game.snakes) == 1
    await pilot.press("2")
    await pilot.pause()
    assert len(app.game.snakes) == 2
    assert app.game.snakes[1].name == "P2"


async def s_two_player_head_on_head(app, pilot):
    """In 2P, same-cell new heads kills both."""
    g = app.game
    g.two_player = True
    g.new_game()
    # Move them to face each other at distance 1.
    setup_snake(g, [(5, 5), (4, 5), (3, 5)], heading="right")
    g.snakes[1].body = [(7, 5), (8, 5), (9, 5)]
    g.snakes[1].heading = "left"
    g.snakes[1].pending_heading = "left"
    g.snakes[1].alive = True
    set_food(g, (0, 0))
    g.tick()
    # After one tick, P1 at (6,5), P2 at (6,5) → both die.
    assert g.game_over
    assert not g.snakes[0].alive and not g.snakes[1].alive
    assert g.snakes[0].death_cause == "head-on"


async def s_speed_ramps(app, pilot):
    """Tick interval should drop as the snake grows past length 3."""
    g = app.game
    base = g.tick_interval_s()
    # Force length increase by hacking the body.
    g.snakes[0].body = [(x, 5) for x in range(20, 0, -1)]
    faster = g.tick_interval_s()
    assert faster < base, (
        f"expected faster tick with longer snake: {faster} vs {base}"
    )
    assert faster >= g.tick_floor_ms / 1000.0


async def s_board_renders_snake(app, pilot):
    """Rendered strip somewhere should contain a snake head glyph."""
    g = app.game
    bv = app.board_view
    bv.refresh()
    await pilot.pause()
    # Find a row carrying the snake head.
    head_glyphs = set("▲▼◀▶")
    found = False
    for y in range(bv.size.height):
        strip = bv.render_line(y)
        text = "".join(seg.text for seg in list(strip))
        if any(g_ in text for g_ in head_glyphs):
            found = True
            break
    assert found, "no head glyph rendered"


async def s_board_renders_food(app, pilot):
    """Rendered strip somewhere should contain the food glyph."""
    g = app.game
    # Place food at a known cell in-bounds.
    g.food = (10, 5)
    bv = app.board_view
    bv.refresh()
    await pilot.pause()
    found = False
    for y in range(bv.size.height):
        strip = bv.render_line(y)
        text = "".join(seg.text for seg in list(strip))
        if "●" in text:
            found = True
            break
    assert found, "food glyph not rendered"


async def s_render_has_bg(app, pilot):
    """Snake cells must render with both fg AND bg — flat-fg would
    regress the palette."""
    bv = app.board_view
    bv.refresh()
    await pilot.pause()
    bg_count = 0
    for y in range(bv.size.height):
        strip = bv.render_line(y)
        for seg in list(strip):
            if seg.style and seg.style.color is not None and seg.style.bgcolor is not None:
                bg_count += 1
    assert bg_count > 20, f"too few tiles rendered with bg: {bg_count}"


async def s_best_score_persists(app, pilot):
    """Eating food bumps best and is persisted."""
    g = app.game
    setup_snake(g, [(5, 5), (4, 5), (3, 5)], heading="right")
    set_food(g, (6, 5))
    g.tick()  # +10
    # App's tick timer would persist, but we hit the engine directly in
    # this test, so call the record helper explicitly (matches the app
    # after a score change).
    state_mod.record_best(app._state, g.width, g.height, g.wrap,
                          g.best_score)
    state_mod.save(app._state)
    # Re-read from disk.
    data = state_mod.load()
    best = state_mod.best_for_config(data, g.width, g.height, g.wrap)
    assert best >= 10, f"best not persisted: {best}"


async def s_spawn_food_not_on_snake(app, pilot):
    """Spawn 200 foods on a big-ish snake — none should land on a body."""
    g = app.game
    # Build a long snake across the middle.
    g.snakes[0].body = [(x, 10) for x in range(5, 25)]
    occupied = set(g.snakes[0].body)
    for _ in range(200):
        g._spawn_food()
        assert g.food is not None
        assert g.food not in occupied


async def s_help_toggles(app, pilot):
    """? opens, any action dismisses it (and does NOT also slide)."""
    assert not app.help_overlay.display
    await pilot.press("question_mark")
    await pilot.pause()
    assert app.help_overlay.display
    heading_before = app.game.snakes[0].pending_heading
    await pilot.press("up")
    await pilot.pause()
    assert not app.help_overlay.display
    # Heading should NOT have changed — first post-help keypress only
    # dismisses help.
    assert app.game.snakes[0].pending_heading == heading_before


async def s_stats_screen_opens(app, pilot):
    """`t` opens StatsScreen, any key dismisses."""
    from snake_tui.screens import StatsScreen
    await pilot.press("t")
    await pilot.pause()
    assert isinstance(app.screen, StatsScreen)
    await pilot.press("escape")
    await pilot.pause()
    assert not isinstance(app.screen, StatsScreen)


async def s_confirm_on_new_game_mid_progress(app, pilot):
    """Pressing `n` with a healthy score pushes ConfirmScreen."""
    from snake_tui.screens import ConfirmScreen
    app.game.snakes[0].score = 500
    await pilot.press("n")
    await pilot.pause()
    assert isinstance(app.screen, ConfirmScreen)
    await pilot.press("n")  # decline
    await pilot.pause()
    assert app.game.snakes[0].score == 500, "declined confirm wiped score"


async def s_header_reflects_score(app, pilot):
    """Sub-title should include current score after engine progress."""
    app.game.snakes[0].score = 100
    app._update_header()
    assert "100" in app.sub_title, app.sub_title


async def s_sound_toggle(app_unused, pilot_unused):
    """Sounds module toggle + debounce."""
    from snake_tui.sounds import Sounds
    s = Sounds(enabled=False)
    calls: list[str] = []
    s._test_hook = lambda name, path: calls.append(name)
    s.play("eat")
    assert calls == []
    toggled = s.toggle()
    if not s.available:
        return
    assert toggled is True
    s.play("eat")
    assert calls == ["eat"], calls
    # Debounce drops immediate repeat.
    s.play("eat")
    assert calls == ["eat"]


async def s_single_cell_can_180(app, pilot):
    """A length-1 snake should be allowed to reverse direction
    (no neck to run into)."""
    g = app.game
    g.snakes[0].body = [(5, 5)]
    g.snakes[0].heading = "right"
    g.snakes[0].pending_heading = "right"
    g.snakes[0].set_heading("left")
    assert g.snakes[0].pending_heading == "left"


async def s_deterministic_with_seeded_rng(app_unused, pilot_unused):
    """Same seed → same food sequence."""
    from snake_tui.engine import Game
    g1 = Game(width=20, height=10, rng=random.Random(99))
    g2 = Game(width=20, height=10, rng=random.Random(99))
    # Walk 50 ticks.
    for _ in range(50):
        g1.tick()
        g2.tick()
    assert g1.food == g2.food
    assert g1.snakes[0].body == g2.snakes[0].body


SCENARIOS: list[Scenario] = [
    Scenario("mount_clean", s_mount_clean),
    Scenario("default_size", s_default_size),
    Scenario("heading_changes", s_heading_changes),
    Scenario("180_blocked", s_180_blocked),
    Scenario("wasd_move", s_wasd_move),
    Scenario("tick_advances_snake", s_tick_advances_snake),
    Scenario("wall_kill", s_wall_kill),
    Scenario("wrap_survives", s_wrap_survives),
    Scenario("food_grow_and_score", s_food_grow_and_score),
    Scenario("self_collision", s_self_collision),
    Scenario("tail_vacate_ok", s_tail_vacate_ok),
    Scenario("pause_halts_tick", s_pause_halts_tick),
    Scenario("pause_toggle_key", s_pause_toggle_key),
    Scenario("new_game_resets", s_new_game_resets),
    Scenario("wrap_toggle_key", s_wrap_toggle_key),
    Scenario("two_player_toggle", s_two_player_toggle),
    Scenario("two_player_head_on_head", s_two_player_head_on_head),
    Scenario("speed_ramps", s_speed_ramps),
    Scenario("board_renders_snake", s_board_renders_snake),
    Scenario("board_renders_food", s_board_renders_food),
    Scenario("render_has_bg", s_render_has_bg),
    Scenario("best_score_persists", s_best_score_persists),
    Scenario("spawn_food_not_on_snake", s_spawn_food_not_on_snake),
    Scenario("help_toggles", s_help_toggles),
    Scenario("stats_screen_opens", s_stats_screen_opens),
    Scenario("confirm_on_new_game_mid_progress",
             s_confirm_on_new_game_mid_progress),
    Scenario("header_reflects_score", s_header_reflects_score),
    Scenario("sound_toggle", s_sound_toggle),
    Scenario("single_cell_can_180", s_single_cell_can_180),
    Scenario("deterministic_with_seeded_rng", s_deterministic_with_seeded_rng),
]


# ---------- driver ----------

async def run_one(scn: Scenario) -> tuple[str, bool, str]:
    app = SnakeApp()
    try:
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            try:
                await scn.fn(app, pilot)
            except AssertionError as e:
                app.save_screenshot(str(OUT / f"{scn.name}.FAIL.svg"))
                return (scn.name, False, f"AssertionError: {e}")
            except Exception as e:
                app.save_screenshot(str(OUT / f"{scn.name}.ERROR.svg"))
                return (scn.name, False,
                        f"{type(e).__name__}: {e}\n{traceback.format_exc()}")
            app.save_screenshot(str(OUT / f"{scn.name}.PASS.svg"))
            return (scn.name, True, "")
    except Exception as e:
        return (scn.name, False,
                f"harness error: {type(e).__name__}: {e}\n"
                f"{traceback.format_exc()}")


async def main(pattern: str | None = None) -> int:
    scenarios = [s for s in SCENARIOS if not pattern or pattern in s.name]
    if not scenarios:
        print(f"no scenarios match {pattern!r}")
        return 2
    results = []
    for scn in scenarios:
        name, ok, msg = await run_one(scn)
        mark = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
        print(f"  {mark} {name}")
        if not ok:
            for line in msg.splitlines():
                print(f"      {line}")
        results.append((name, ok, msg))
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed}/{len(results)} passed, {failed} failed")
    return failed


if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(main(pattern)))
