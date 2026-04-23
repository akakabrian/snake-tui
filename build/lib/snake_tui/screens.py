"""Modal screens — confirm-dialog, stats, help overlay content.

Modal bindings steer clear of `arrow / enter / space` because priority=True
app bindings beat modal screens per the tui-game-build skill.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from . import state as state_mod


class ConfirmScreen(ModalScreen[bool]):
    """Simple y/n confirm. Used when restarting mid-game would wipe a
    decent score."""

    BINDINGS = [
        Binding("y", "confirm_yes", "yes"),
        Binding("n", "confirm_no", "no"),
        Binding("escape", "confirm_no", "cancel"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-body"):
            yield Static(self._message, id="confirm-msg")
            yield Static("[bold]y[/]es / [bold]n[/]o", id="confirm-keys")

    def action_confirm_yes(self) -> None:
        self.dismiss(True)

    def action_confirm_no(self) -> None:
        self.dismiss(False)


class StatsScreen(ModalScreen[None]):
    """Per-config best scores. Dismiss with any key."""

    BINDINGS = [
        Binding("escape", "dismiss", "close"),
        Binding("q", "dismiss", "close"),
        Binding("enter", "dismiss", "close"),
        Binding("space", "dismiss", "close"),
    ]

    def __init__(self, state: dict) -> None:
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        with Vertical(id="stats-body"):
            yield Static(self._build_markup(), id="stats-content")
            yield Static(
                "[dim]press any key to close[/]",
                id="stats-dismiss",
            )

    def _build_markup(self) -> str:
        bests = state_mod.all_bests(self._state)
        lines: list[str] = []
        lines.append("[bold rgb(130,230,80)]SNAKE-TUI — BEST SCORES[/]")
        lines.append("")
        if not bests:
            lines.append("[dim]no records yet — play a game![/]")
        else:
            for key, score in bests.items():
                bar_len = min(20, max(0, score // 20))
                bar = "█" * bar_len
                lines.append(
                    f"  [bold]{key:<16}[/]  "
                    f"[rgb(130,230,80)]{score:>6,}[/]  "
                    f"[rgb(130,230,80)]{bar}[/]"
                )
        lines.append("")
        lines.append(
            f"[dim]best scores persist across sessions in[/]\n"
            f"[dim]{state_mod.STATE_PATH}[/]"
        )
        return "\n".join(lines)

    def on_key(self, event) -> None:
        self.dismiss(None)


class GameOverScreen(ModalScreen[str]):
    """Dismissable game-over banner. Returns one of "new"/"quit"/"close"
    via dismiss() so the caller knows what to do next."""

    BINDINGS = [
        Binding("n", "gonew", "new"),
        Binding("q", "goquit", "quit"),
        Binding("escape", "goclose", "close"),
        Binding("enter", "gonew", "new"),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="gameover-body"):
            yield Static(self._message, id="gameover-msg")
            yield Static(
                "[bold]n[/]ew game   [bold]q[/]uit   [bold]esc[/] close",
                id="gameover-keys",
            )

    def action_gonew(self) -> None:
        self.dismiss("new")

    def action_goquit(self) -> None:
        self.dismiss("quit")

    def action_goclose(self) -> None:
        self.dismiss("close")
