"""Textual app for snake-tui.

Keys:
  ↑/↓/←/→ or w/a/s/d : move (P1)
  i/j/k/l            : move P2 (when 2-player)
  space or p         : pause / resume
  n                  : new game (confirms if score >= 100 and not over)
  W                  : toggle wrap mode (restarts game)
  2                  : toggle 2-player (restarts game)
  +/-                : board size up/down
  t                  : stats screen
  s                  : toggle sound
  ?                  : help overlay
  q                  : quit
"""

from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Footer, Header, Static

from . import tiles
from . import state as state_mod
from . import rl_hooks
from .engine import Game, HEADINGS
from .screens import ConfirmScreen, GameOverScreen, StatsScreen
from .sounds import Sounds


# Playfield cell is 1 column wide (keeps glyph alignment simple) × 1 row.
# Wrap the board with a 1-cell border of `tiles.STYLE_WALL` for visual
# delimitation — the actual collision wall is the cells at 0..W-1 × 0..H-1.
CELL_W = 1
CELL_H = 1


class BoardView(Widget):
    """Renders the snake playfield.

    The grid is small (default 40×20 = 800 cells) so a full-viewport
    refresh per tick is cheap and we don't need region-based invalidation.
    """

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        # Pre-parsed styles used in render_line.
        self._bg_pad = Style.parse(f"on {tiles.BG_BOARD}")

    def on_mount(self) -> None:
        self.refresh()

    def board_pixel_size(self) -> tuple[int, int]:
        # +2 on each dim for the drawn wall border.
        return (self.game.width * CELL_W + 2,
                self.game.height * CELL_H + 2)

    def _cell_style_and_glyph(
        self, x: int, y: int
    ) -> tuple[Style, str]:
        """Pick the (style, glyph) for cell (x, y) given current game state."""
        g = self.game
        # Snake cells first (head > body).
        for s in g.snakes:
            if not s.body:
                continue
            if (x, y) == s.head:
                glyph = tiles.HEAD_GLYPH.get(s.heading, "█")
                return (tiles.head_style(s.style_key, alive=s.alive), glyph)
        for s in g.snakes:
            for i, cell in enumerate(s.body[1:], start=1):
                if cell == (x, y):
                    glyph = (tiles.BODY_GLYPH_EVEN if i % 2 == 0
                             else tiles.BODY_GLYPH_ODD)
                    return (tiles.body_style(s.style_key, alive=s.alive),
                            glyph)
        # Food.
        if g.food == (x, y):
            return (tiles.STYLE_FOOD, tiles.FOOD_GLYPH)
        # Empty — alternating checker for a grid that reads as a grid.
        checker = (x + y) & 1
        if checker:
            return (tiles.STYLE_EMPTY_ALT, " ")
        return (tiles.STYLE_EMPTY, " ")

    def render_line(self, y: int) -> Strip:
        width = self.size.width
        height = self.size.height
        board_w, board_h = self.board_pixel_size()
        off_x = max(0, (width - board_w) // 2)
        off_y = max(0, (height - board_h) // 2)

        # Outside top/bottom → pad bg only.
        if y < off_y or y >= off_y + board_h:
            return Strip([Segment(" " * width, self._bg_pad)], width)

        segs: list[Segment] = []
        if off_x > 0:
            segs.append(Segment(" " * off_x, self._bg_pad))

        local_y = y - off_y
        # Top / bottom wall rows.
        if local_y == 0 or local_y == board_h - 1:
            segs.append(Segment("═" * board_w, tiles.STYLE_WALL))
        else:
            grid_y = local_y - 1
            # Left wall.
            segs.append(Segment("║", tiles.STYLE_WALL))
            # Row of board cells.
            for x in range(self.game.width):
                style, glyph = self._cell_style_and_glyph(x, grid_y)
                segs.append(Segment(glyph, style))
            # Right wall.
            segs.append(Segment("║", tiles.STYLE_WALL))

        right_pad = width - off_x - board_w
        if right_pad > 0:
            segs.append(Segment(" " * right_pad, self._bg_pad))
        return Strip(segs, width)


class StatusPanel(Static):
    """Side panel: score / best / length / speed / controls."""

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self.border_title = "SCORE"
        self._last_snapshot: tuple | None = None
        self._pulse_phase = False

    def refresh_panel(self, *, force: bool = False) -> None:
        s = self.game.state()
        if force:
            self._pulse_phase = not self._pulse_phase
        snakes_snap = tuple(
            (sn["score"], sn["length"], sn["alive"])
            for sn in s["snakes"]
        )
        snapshot = (
            s["best"], s["ticks"], s["paused"], s["game_over"],
            s["wrap"], s["two_player"], s["width"], s["height"],
            s["tick_ms"],
            snakes_snap,
            self._pulse_phase if s["game_over"] or s["paused"] else None,
        )
        if not force and snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot

        t = Text()
        # P1 block — always shown.
        p1 = s["snakes"][0]
        t.append("P1 score  ", style="bold")
        t.append(f"{p1['score']:>8,}\n",
                 style="bold rgb(130,230,80)")
        t.append("P1 length ", style="bold")
        t.append(f"{p1['length']:>8,}\n")
        if s["two_player"] and len(s["snakes"]) > 1:
            p2 = s["snakes"][1]
            t.append("P2 score  ", style="bold")
            t.append(f"{p2['score']:>8,}\n",
                     style="bold rgb(80,180,240)")
            t.append("P2 length ", style="bold")
            t.append(f"{p2['length']:>8,}\n")
        t.append("Best      ", style="bold")
        t.append(f"{s['best']:>8,}\n",
                 style="bold rgb(190,230,100)")
        t.append(f"Board     {s['width']}×{s['height']}\n")
        t.append(f"Wrap      {'on' if s['wrap'] else 'off'}\n")
        t.append(f"2-player  {'on' if s['two_player'] else 'off'}\n")
        t.append(f"Speed     {1000 // max(1, s['tick_ms'])} Hz "
                 f"({s['tick_ms']} ms)\n")
        t.append(f"Ticks     {s['ticks']:,}\n")
        t.append("\n")

        if s["game_over"]:
            bg = "rgb(160,40,40)" if self._pulse_phase else "rgb(120,20,20)"
            t.append("  GAME OVER  \n",
                     style=f"bold white on {bg}")
            dead_by = [sn["name"] + "→" + str(sn["death_cause"])
                       for sn in s["snakes"] if not sn["alive"]]
            if dead_by:
                t.append(", ".join(dead_by) + "\n", style="dim")
            t.append("press [bold]n[/] for new game\n")
        elif s["paused"]:
            bg = "rgb(200,180,50)" if self._pulse_phase else "rgb(160,140,30)"
            t.append("   PAUSED   \n",
                     style=f"bold black on {bg}")
            t.append("space / p to resume\n")
        else:
            t.append("arrows / wasd move\n", style="dim")
            if s["two_player"]:
                t.append("ijkl move P2\n", style="dim")
            t.append("space pause   n new\n", style="dim")
            t.append("W wrap   2 two-player\n", style="dim")
            t.append("t stats  s sound\n", style="dim")
            t.append("? help   q quit\n", style="dim")
        self.update(t)


class FlashBar(Static):
    """One-line transient message."""

    def set_message(self, msg: str) -> None:
        self.update(Text.from_markup(msg))


_HELP_TEXT = (
    "[bold]snake-tui — terminal edition[/]\n\n"
    "[bold]Goal[/]  eat the red food to grow. Don't hit the wall or\n"
    "       yourself. The snake speeds up as it grows.\n\n"
    "[bold]P1 keys[/]\n"
    "  ↑↓←→  or  w/a/s/d    move\n\n"
    "[bold]P2 keys[/] (when 2-player is on)\n"
    "  i/j/k/l              move\n\n"
    "[bold]Game[/]\n"
    "  space / p            pause\n"
    "  n                    new game\n"
    "  W                    toggle wrap mode\n"
    "  2                    toggle 2-player hotseat\n"
    "  +/-                  board width (height follows)\n"
    "  t                    stats — best scores\n"
    "  s                    toggle sound\n"
    "  ?                    toggle this help\n"
    "  q                    quit\n\n"
    "[bold]Scoring[/]  +10 per food. Per-config best scores are kept.\n\n"
    "[dim]press any key to dismiss[/]"
)


class HelpOverlay(Static):
    """One-screen help. Non-modal — dismissed by any action."""

    def __init__(self) -> None:
        super().__init__(Text.from_markup(_HELP_TEXT))
        self.border_title = "HELP"
        self.display = False


class SnakeApp(App):
    CSS_PATH = "tui.tcss"
    TITLE = "snake — Terminal"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("n", "new_game", "New"),
        Binding("space", "toggle_pause", "Pause"),
        Binding("p", "toggle_pause", "Pause", show=False),
        Binding("t", "stats", "Stats"),
        Binding("s", "toggle_sound", "Sound"),
        Binding("W", "toggle_wrap", "Wrap"),
        Binding("2", "toggle_two_player", "2P"),
        Binding("question_mark", "toggle_help", "Help"),
        Binding("plus", "change_size(4)", "Size+", show=False),
        Binding("minus", "change_size(-4)", "Size-", show=False),
        # P1 movement — arrows + wasd, priority so BoardView doesn't eat.
        Binding("up",    "p1('up')",    "↑", show=False, priority=True),
        Binding("down",  "p1('down')",  "↓", show=False, priority=True),
        Binding("left",  "p1('left')",  "←", show=False, priority=True),
        Binding("right", "p1('right')", "→", show=False, priority=True),
        Binding("w", "p1('up')",    "w", show=False, priority=True),
        Binding("a", "p1('left')",  "a", show=False, priority=True),
        Binding("d", "p1('right')", "d", show=False, priority=True),
        # P2 movement — ijkl.
        Binding("i", "p2('up')",    "i", show=False, priority=True),
        Binding("j", "p2('left')",  "j", show=False, priority=True),
        Binding("k", "p2('down')",  "k", show=False, priority=True),
        Binding("l", "p2('right')", "l", show=False, priority=True),
    ]

    def __init__(self, *, width: int = 40, height: int = 20,
                 wrap: bool = False, two_player: bool = False) -> None:
        super().__init__()
        self._state = state_mod.load()
        self.game = Game(
            width=width, height=height, wrap=wrap, two_player=two_player,
        )
        self.game.best_score = state_mod.best_for_config(
            self._state, width, height, wrap,
        )
        self.board_view = BoardView(self.game)
        self.status_panel = StatusPanel(self.game)
        self.flash_bar = FlashBar(" ", id="flash-bar")
        self.help_overlay = HelpOverlay()
        self.help_overlay.id = "help-overlay"
        self.sounds = Sounds()
        # `_game_over_shown` prevents the game-over modal from stacking
        # if the app sees multiple post-death ticks before the modal
        # dismisses. Reset on new-game.
        self._game_over_shown = False
        # Tick timer handle — reinstalled whenever the tick cadence
        # changes (speed ramp as the snake grows).
        self._tick_timer = None
        self._current_interval_s: float = -1.0

    # --- layout --------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="body"):
            with Vertical(id="board-col"):
                yield self.board_view
                yield self.flash_bar
            with Vertical(id="side"):
                yield self.status_panel
        yield self.help_overlay
        yield Footer()

    async def on_mount(self) -> None:
        self._update_border_title()
        self.status_panel.refresh_panel()
        self._show_hint()
        self._update_header()
        self._reschedule_tick()
        # 2 Hz pulse for the pause / game-over banner.
        self.set_interval(0.5, self._pulse)

    # --- tick scheduling ----------------------------------------------

    def _reschedule_tick(self) -> None:
        """Reinstall the tick timer at the current engine cadence. Called
        on mount, on any speed-changing event (size change, new game,
        snake growth)."""
        interval = self.game.tick_interval_s()
        if abs(interval - self._current_interval_s) < 1e-6:
            return
        self._current_interval_s = interval
        if self._tick_timer is not None:
            try:
                self._tick_timer.stop()
            except Exception:
                pass
        self._tick_timer = self.set_interval(interval, self._game_tick)

    def _game_tick(self) -> None:
        """Engine tick — also refreshes the view. Called by the timer."""
        if self.game.game_over:
            if not self._game_over_shown:
                self._game_over_shown = True
                self.sounds.play("die")
                self._show_game_over_modal()
            return
        if self.game.paused:
            return
        before_len = self.game.snakes[0].length if self.game.snakes else 0
        before_score = (self.game.snakes[0].score
                        if self.game.snakes else 0)
        self.game.tick()
        after_len = self.game.snakes[0].length if self.game.snakes else 0
        after_score = (self.game.snakes[0].score
                       if self.game.snakes else 0)
        if after_score > before_score:
            self.sounds.play("eat")
            # Persist best if beaten.
            state_mod.record_best(
                self._state, self.game.width, self.game.height,
                self.game.wrap, self.game.best_score,
            )
            state_mod.save(self._state)
        # Speed up if length changed.
        if after_len != before_len:
            self._reschedule_tick()
        self.board_view.refresh()
        self.status_panel.refresh_panel()

    def _pulse(self) -> None:
        """Slow repaint of the status panel for banner animation."""
        self.status_panel.refresh_panel(force=True)

    # --- misc ----------------------------------------------------------

    def _update_border_title(self) -> None:
        g = self.game
        mode = []
        if g.wrap:
            mode.append("wrap")
        if g.two_player:
            mode.append("2P")
        suffix = f" · {', '.join(mode)}" if mode else ""
        self.board_view.border_title = (
            f"snake · {g.width}×{g.height}{suffix}"
        )

    def _update_header(self) -> None:
        s = self.game.state()
        bits = []
        if s["paused"]:
            bits.append("paused")
        if s["game_over"]:
            bits.append("GAME OVER")
        if s["two_player"]:
            bits.append("2P")
        if s["wrap"]:
            bits.append("wrap")
        suffix = f"  ·  {', '.join(bits)}" if bits else ""
        p1 = s["snakes"][0]
        self.sub_title = (
            f"P1 {p1['score']:,} · len {p1['length']} · "
            f"best {s['best']:,}{suffix}"
        )

    def _show_hint(self) -> None:
        if self.game.two_player:
            self.flash_bar.set_message(
                "[dim]P1 arrows/wasd · P2 ijkl · space pauses[/]"
            )
        else:
            self.flash_bar.set_message(
                "[dim]use arrows or wasd to steer · eat red food to grow[/]"
            )

    def _show_game_over_modal(self) -> None:
        s = self.game.state()
        p1 = s["snakes"][0]
        lines = [f"[bold]GAME OVER[/]\n"]
        if s["two_player"] and len(s["snakes"]) > 1:
            p2 = s["snakes"][1]
            lines.append(
                f"P1 final score [bold]{p1['score']:,}[/] · "
                f"length [bold]{p1['length']}[/]\n"
                f"P2 final score [bold]{p2['score']:,}[/] · "
                f"length [bold]{p2['length']}[/]\n"
            )
        else:
            lines.append(
                f"Final score [bold]{p1['score']:,}[/]  ·  "
                f"length [bold]{p1['length']}[/]\n"
            )
        cause = ", ".join(
            f"{sn['name']}→{sn['death_cause']}"
            for sn in s["snakes"] if sn["death_cause"]
        )
        if cause:
            lines.append(f"[dim]{cause}[/]\n")
        # Record best.
        state_mod.record_best(
            self._state, self.game.width, self.game.height,
            self.game.wrap, self.game.best_score,
        )
        state_mod.save(self._state)

        def _after(result: str | None) -> None:
            if result == "new":
                self._do_new_game()
            elif result == "quit":
                self.exit()
            # "close"/None → just let the board sit on the game-over freeze.

        self.push_screen(GameOverScreen("".join(lines)), _after)

    # --- actions -------------------------------------------------------

    def action_p1(self, direction: str) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        if direction not in HEADINGS:
            return
        self.game.set_heading(0, direction)  # type: ignore[arg-type]

    def action_p2(self, direction: str) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        if direction not in HEADINGS:
            return
        if self.game.two_player and len(self.game.snakes) > 1:
            self.game.set_heading(1, direction)  # type: ignore[arg-type]

    def action_toggle_pause(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        if self.game.game_over:
            return
        self.game.toggle_pause()
        self.sounds.play("pause")
        self.flash_bar.set_message(
            "[bold yellow]paused[/]  space / p to resume"
            if self.game.paused
            else "[dim]resumed[/]"
        )
        self.status_panel.refresh_panel(force=True)
        self._update_header()

    def action_new_game(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        s = self.game.state()
        p1 = s["snakes"][0]
        if p1["score"] >= 100 and not s["game_over"]:
            def _after(ok: bool | None) -> None:
                if ok:
                    self._do_new_game()
                else:
                    self.flash_bar.set_message("[dim]kept current game[/]")
            self.push_screen(
                ConfirmScreen(
                    f"Start a new game? "
                    f"Current score [bold]{p1['score']:,}[/] will be lost."
                ),
                _after,
            )
            return
        self._do_new_game()

    def _do_new_game(self) -> None:
        self.game.new_game()
        # Reload best for current config (it can't regress, but be safe).
        self.game.best_score = state_mod.best_for_config(
            self._state, self.game.width, self.game.height, self.game.wrap,
        )
        self._game_over_shown = False
        self.board_view.refresh()
        self.status_panel.refresh_panel(force=True)
        self._update_border_title()
        self._update_header()
        self._reschedule_tick()
        self.sounds.play("start")
        self.flash_bar.set_message("[bold green]new game[/]")

    def action_toggle_wrap(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        self.game.set_wrap(not self.game.wrap)
        # Best is per-config so reload.
        self.game.best_score = state_mod.best_for_config(
            self._state, self.game.width, self.game.height, self.game.wrap,
        )
        self.game.new_game()
        self._state["last_wrap"] = self.game.wrap
        state_mod.save(self._state)
        self._game_over_shown = False
        self._update_border_title()
        self._update_header()
        self._reschedule_tick()
        self.board_view.refresh()
        self.status_panel.refresh_panel(force=True)
        self.flash_bar.set_message(
            f"[bold green]wrap {'on' if self.game.wrap else 'off'}[/]"
        )

    def action_toggle_two_player(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        self.game.set_two_player(not self.game.two_player)
        self._state["last_two_player"] = self.game.two_player
        state_mod.save(self._state)
        self._game_over_shown = False
        self._update_border_title()
        self._update_header()
        self._reschedule_tick()
        self.board_view.refresh()
        self.status_panel.refresh_panel(force=True)
        mode = "on (hotseat)" if self.game.two_player else "off"
        self.flash_bar.set_message(f"[bold green]2-player {mode}[/]")

    def action_change_size(self, delta: str) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        step = int(delta)
        new_w = max(10, min(80, self.game.width + step))
        new_h = max(8, min(40, self.game.height + step // 2))
        if new_w == self.game.width and new_h == self.game.height:
            self.flash_bar.set_message(
                f"[dim]already at {new_w}×{new_h}[/]"
            )
            return
        self.game.set_size(new_w, new_h)
        self.game.best_score = state_mod.best_for_config(
            self._state, new_w, new_h, self.game.wrap,
        )
        self._state["last_width"] = new_w
        self._state["last_height"] = new_h
        state_mod.save(self._state)
        self._game_over_shown = False
        self._update_border_title()
        self._update_header()
        self._reschedule_tick()
        self.board_view.refresh()
        self.status_panel.refresh_panel(force=True)
        self.flash_bar.set_message(
            f"[bold green]new {new_w}×{new_h} game[/]"
        )

    def action_toggle_help(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
        else:
            self.help_overlay.display = True

    def _hide_help(self) -> None:
        self.help_overlay.display = False

    def action_toggle_sound(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        if not self.sounds.available:
            self.flash_bar.set_message(
                "[red]no audio player found[/] "
                "(install paplay / aplay / afplay)"
            )
            return
        on = self.sounds.toggle()
        self.flash_bar.set_message(
            f"[bold {'green' if on else 'yellow'}]"
            f"sound {'on' if on else 'off'}[/]"
        )

    # --- RL exposure (side-effect-free) -------------------------------

    def game_state_vector(self):
        """Flat np.float32 vector — canonical state for RL agents."""
        return rl_hooks.state_vector(self.game)

    def game_reward(self, prev_score: int, prev_alive: bool) -> float:
        """Incremental reward since the last step."""
        return rl_hooks.compute_reward(prev_score, prev_alive, self.game)

    def is_terminal(self) -> bool:
        return rl_hooks.is_terminal(self.game)

    def reset_game(self) -> None:
        """Reset the underlying engine to a fresh episode. Side-effect-free
        w.r.t. scoreboard state (best-scores preserved). Used by RL envs."""
        self.game.new_game()
        self._game_over_shown = False

    def action_stats(self) -> None:
        if self.help_overlay.display:
            self._hide_help()
            return
        state_mod.record_best(
            self._state, self.game.width, self.game.height,
            self.game.wrap, self.game.best_score,
        )
        state_mod.save(self._state)
        self.push_screen(StatsScreen(self._state))


def run(*, width: int = 40, height: int = 20,
        wrap: bool = False, two_player: bool = False) -> None:
    app = SnakeApp(width=width, height=height,
                   wrap=wrap, two_player=two_player)
    try:
        app.run()
    finally:
        # Belt-and-suspenders mouse/cursor reset — matches simcity/2048.
        import sys
        sys.stdout.write(
            "\033[?1000l\033[?1002l\033[?1003l"
            "\033[?1006l\033[?1015l\033[?25h"
        )
        sys.stdout.flush()
