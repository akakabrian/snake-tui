"""Pure-Python Snake engine.

Classic grid-accretion game:
  * snake moves one cell per tick in its current heading
  * eating food grows the snake by 1 and spawns a new food cell
  * collision with wall (unless wrap mode) or self ends the game
  * optional second snake (hotseat 2-player) — game ends when one dies

Engine shape mirrors the tui-game-build "one import, one tick, one
render" gate so the rest of the TUI looks like every other skill
project. The TUI calls `game.tick()` on a timer, reads `game.state()`
for the status panel, and iterates `game.cells()` for the grid render.

Direction is stored as a `(dx, dy)` vector because reversing into
yourself in one tick is a classic snake bug — we guard it with
"cannot 180° unless length == 1".
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

Heading = Literal["up", "down", "left", "right"]

# (dx, dy) per heading — +y is down because the screen's origin is top-left.
HEADINGS: dict[Heading, tuple[int, int]] = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": ( 1, 0),
}


@dataclass
class Snake:
    """One snake: ordered list of (x, y) cells, head at index 0.

    `heading` is the *current* direction of travel. `pending_heading`
    is set by keyboard input and applied on the next tick — this is
    what prevents double-taps within a single tick from reversing the
    snake into itself.
    """

    body: list[tuple[int, int]]
    heading: Heading = "right"
    pending_heading: Heading = "right"
    alive: bool = True
    score: int = 0
    # Growth pending from recent food — add a tail cell for each over the
    # next N ticks so the snake visibly elongates.
    growth_debt: int = 0
    # Attribution of death — "wall", "self", "other" (ran into other snake).
    death_cause: str | None = None
    # Optional: a display name / label for 2-player HUD.
    name: str = "P1"
    # Optional: fg/bg style key for the tiles module.
    style_key: str = "p1"

    @property
    def head(self) -> tuple[int, int]:
        return self.body[0]

    @property
    def length(self) -> int:
        return len(self.body)

    def occupies(self, cell: tuple[int, int]) -> bool:
        return cell in self.body

    def set_heading(self, h: Heading) -> None:
        """Queue a heading change. Reject 180° turns unless length == 1
        (a single-cell snake has no direction to reverse)."""
        if h not in HEADINGS:
            return
        if self.length > 1:
            dx, dy = HEADINGS[h]
            cdx, cdy = HEADINGS[self.heading]
            if (dx, dy) == (-cdx, -cdy):
                return  # tried to reverse — ignored
        self.pending_heading = h


@dataclass
class Game:
    """Full game state. Driven by `tick()`."""

    width: int = 40
    height: int = 20
    wrap: bool = False
    two_player: bool = False
    # Difficulty ramp: starts at `tick_start_ms`, drops toward `tick_floor_ms`
    # as the first snake grows (length 1 → floor at length == ramp_length).
    tick_start_ms: int = 100
    tick_floor_ms: int = 30
    ramp_length: int = 40
    # Score bonus per food eaten (also length gained — 1 cell per food).
    food_value: int = 10

    snakes: list[Snake] = field(default_factory=list)
    food: tuple[int, int] | None = None
    game_over: bool = False
    ticks: int = 0
    rng: random.Random = field(default_factory=random.Random)
    best_score: int = 0
    paused: bool = False
    # End reason: None while playing; "collision" once game_over fires.
    # Used by the status panel to pick the right banner.
    end_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.snakes:
            self.new_game()

    # ---- lifecycle ----------------------------------------------------

    def new_game(self) -> None:
        """Reset the board to a fresh starting position. Preserves
        best_score and configuration flags (width/height/wrap/2p)."""
        self.ticks = 0
        self.game_over = False
        self.end_reason = None
        self.paused = False
        cy = self.height // 2
        s1 = Snake(
            body=[(5, cy), (4, cy), (3, cy)],
            heading="right", pending_heading="right",
            name="P1", style_key="p1",
        )
        self.snakes = [s1]
        if self.two_player:
            s2 = Snake(
                body=[(self.width - 6, cy), (self.width - 5, cy),
                      (self.width - 4, cy)],
                heading="left", pending_heading="left",
                name="P2", style_key="p2",
            )
            self.snakes.append(s2)
        self._spawn_food()

    def set_size(self, width: int, height: int) -> None:
        self.width = max(8, min(120, int(width)))
        self.height = max(6, min(60, int(height)))
        self.new_game()

    def set_wrap(self, wrap: bool) -> None:
        self.wrap = bool(wrap)

    def set_two_player(self, tp: bool) -> None:
        self.two_player = bool(tp)
        self.new_game()

    def toggle_pause(self) -> None:
        if not self.game_over:
            self.paused = not self.paused

    # ---- per-tick logic ----------------------------------------------

    def tick(self) -> None:
        """Advance the game by one step. No-op if game_over or paused.

        Order:
          1. Each alive snake applies its pending heading.
          2. Compute each snake's new head.
          3. Resolve collisions (wall / self / other-snake-body /
             head-on-head). Mark dead snakes.
          4. For survivors: detect food eaten → grow + re-spawn food.
          5. Pop tails of survivors that didn't eat (growth_debt > 0
             means skip the pop for that tick).
          6. If any snake died, set game_over.
        """
        if self.game_over or self.paused:
            return
        self.ticks += 1

        # 1. Apply queued heading.
        for s in self.snakes:
            if s.alive:
                s.heading = s.pending_heading

        # 2. New heads.
        new_heads: list[tuple[int, int] | None] = []
        for s in self.snakes:
            if not s.alive:
                new_heads.append(None)
                continue
            dx, dy = HEADINGS[s.heading]
            nx, ny = s.head[0] + dx, s.head[1] + dy
            if self.wrap:
                nx %= self.width
                ny %= self.height
            new_heads.append((nx, ny))

        # 3. Collision detection.
        # First: wall (only meaningful when wrap is off).
        for i, s in enumerate(self.snakes):
            if not s.alive or new_heads[i] is None:
                continue
            nx, ny = new_heads[i]  # type: ignore[misc]
            if not self.wrap:
                if nx < 0 or nx >= self.width or ny < 0 or ny >= self.height:
                    s.alive = False
                    s.death_cause = "wall"

        # Head-on-head (2p): if both new heads are the same cell, both die.
        if self.two_player and len(self.snakes) == 2:
            a, b = self.snakes
            if a.alive and b.alive and new_heads[0] == new_heads[1]:
                a.alive = False
                b.alive = False
                a.death_cause = "head-on"
                b.death_cause = "head-on"

        # Body collision: against self OR any other snake's body.
        # Note: a snake CAN move into the cell its own tail just vacated,
        # because the tail will pop after we resolve collisions. So we
        # exclude each snake's own last cell from the self-collision set
        # if that snake isn't growing this tick.
        for i, s in enumerate(self.snakes):
            if not s.alive or new_heads[i] is None:
                continue
            head_cell = new_heads[i]
            # Build the "blocked" set for this snake.
            blocked: set[tuple[int, int]] = set()
            for j, other in enumerate(self.snakes):
                cells = list(other.body)
                if j == i and other.growth_debt == 0:
                    # Own tail will vacate — not blocking.
                    if len(cells) > 0:
                        cells = cells[:-1]
                blocked.update(cells)
            if head_cell in blocked:
                s.alive = False
                if s.death_cause is None:
                    s.death_cause = "self" if head_cell in s.body else "other"

        # 4+5. Apply movement + food + tail.
        ate_any = False
        eaten_by: list[int] = []
        for i, s in enumerate(self.snakes):
            if not s.alive or new_heads[i] is None:
                continue
            new_head = new_heads[i]  # type: ignore[assignment]
            s.body.insert(0, new_head)
            if self.food is not None and new_head == self.food:
                s.score += self.food_value
                s.growth_debt += 1
                eaten_by.append(i)
                ate_any = True
            # Pop tail unless we've got growth debt.
            if s.growth_debt > 0:
                s.growth_debt -= 1
            else:
                s.body.pop()

        # Re-spawn food if eaten.
        if ate_any:
            self._spawn_food()

        # Best-score: track max live score across snakes.
        for s in self.snakes:
            if s.score > self.best_score:
                self.best_score = s.score

        # 6. Game over if any snake died.
        if not all(s.alive for s in self.snakes):
            self.game_over = True
            self.end_reason = "collision"

    # ---- food spawning ------------------------------------------------

    def _all_body_cells(self) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        for s in self.snakes:
            cells.update(s.body)
        return cells

    def _spawn_food(self) -> None:
        """Place food on a random non-snake cell. If the board is full
        (unlikely but possible on tiny boards), clear food and let the
        player win by starvation — the engine doesn't declare victory."""
        occupied = self._all_body_cells()
        total = self.width * self.height
        if len(occupied) >= total:
            self.food = None
            return
        # Rejection sampling — cheap for realistic board fullness.
        while True:
            x = self.rng.randrange(self.width)
            y = self.rng.randrange(self.height)
            if (x, y) not in occupied:
                self.food = (x, y)
                return

    # ---- input --------------------------------------------------------

    def set_heading(self, player: int, h: Heading) -> None:
        """Queue a heading change for the given player (0 or 1)."""
        if 0 <= player < len(self.snakes):
            self.snakes[player].set_heading(h)

    # ---- cadence ------------------------------------------------------

    def tick_interval_s(self) -> float:
        """Seconds between ticks. Ramps down with the primary snake's
        length so the game speeds up as it progresses."""
        s = self.snakes[0] if self.snakes else None
        if s is None:
            return self.tick_start_ms / 1000.0
        length = s.length
        # Linear ramp — simpler than an exponential, and more predictable.
        t = min(1.0, max(0.0, (length - 3) / max(1, self.ramp_length)))
        ms = self.tick_start_ms + (self.tick_floor_ms - self.tick_start_ms) * t
        return max(self.tick_floor_ms, ms) / 1000.0

    # ---- introspection ------------------------------------------------

    def state(self) -> dict:
        """State snapshot — status panel + QA harness."""
        return {
            "width": self.width,
            "height": self.height,
            "wrap": self.wrap,
            "two_player": self.two_player,
            "ticks": self.ticks,
            "paused": self.paused,
            "game_over": self.game_over,
            "end_reason": self.end_reason,
            "best": self.best_score,
            "food": self.food,
            "tick_ms": int(self.tick_interval_s() * 1000),
            "snakes": [
                {
                    "name": s.name,
                    "style_key": s.style_key,
                    "length": s.length,
                    "score": s.score,
                    "alive": s.alive,
                    "death_cause": s.death_cause,
                    "head": s.head if s.body else None,
                    "heading": s.heading,
                }
                for s in self.snakes
            ],
        }

    def to_dict(self) -> dict:
        """Minimal serialisable state."""
        return {
            "width": self.width,
            "height": self.height,
            "wrap": self.wrap,
            "two_player": self.two_player,
            "best": self.best_score,
        }
