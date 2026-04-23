"""Tile / glyph palette for the snake board.

Per the tui-game-build visual rules:
  * 1-cell glyphs in the grid (no emoji that breaks alignment)
  * backgrounds subtle, foregrounds do the work
  * brightness budget: board dim, snake medium, food bright

Pre-parsed `rich.style.Style` objects so we pay parse cost once.
"""

from __future__ import annotations

from rich.style import Style


# --- colors ---------------------------------------------------------

BG_BOARD = "rgb(14,18,14)"           # deep forest — subtle, non-distracting
BG_BOARD_ALT = "rgb(18,24,18)"       # alternating cell shade (checker)
FG_GRID = "rgb(30,44,30)"            # very faint grid dot

# Snake 1 (primary player) — vivid green
FG_P1_HEAD = "rgb(255,255,160)"
BG_P1_HEAD = "rgb(90,180,60)"
FG_P1_BODY = "rgb(20,40,20)"
BG_P1_BODY = "rgb(70,150,50)"

# Snake 2 (hotseat) — cyan/blue
FG_P2_HEAD = "rgb(230,250,255)"
BG_P2_HEAD = "rgb(60,140,210)"
FG_P2_BODY = "rgb(15,30,50)"
BG_P2_BODY = "rgb(50,115,180)"

# Food — a hot red pip
FG_FOOD = "rgb(255,80,60)"
BG_FOOD = "rgb(60,18,14)"

# Wall (visual border around the play area)
FG_WALL = "rgb(160,130,80)"
BG_WALL = "rgb(40,30,18)"


# Pre-parsed styles (parsing Style strings per-cell per-frame is slow).
STYLE_EMPTY = Style.parse(f"on {BG_BOARD}")
STYLE_EMPTY_ALT = Style.parse(f"on {BG_BOARD_ALT}")
STYLE_GRID = Style.parse(f"{FG_GRID} on {BG_BOARD}")
STYLE_GRID_ALT = Style.parse(f"{FG_GRID} on {BG_BOARD_ALT}")

STYLE_P1_HEAD = Style.parse(f"bold {FG_P1_HEAD} on {BG_P1_HEAD}")
STYLE_P1_BODY = Style.parse(f"{FG_P1_BODY} on {BG_P1_BODY}")
STYLE_P2_HEAD = Style.parse(f"bold {FG_P2_HEAD} on {BG_P2_HEAD}")
STYLE_P2_BODY = Style.parse(f"{FG_P2_BODY} on {BG_P2_BODY}")

# Death-flash (dim, desaturated) styles for the game-over freeze-frame.
STYLE_P1_HEAD_DEAD = Style.parse(f"dim rgb(180,180,180) on rgb(50,70,50)")
STYLE_P1_BODY_DEAD = Style.parse(f"dim rgb(80,80,80) on rgb(45,70,45)")
STYLE_P2_HEAD_DEAD = Style.parse(f"dim rgb(180,180,180) on rgb(40,70,100)")
STYLE_P2_BODY_DEAD = Style.parse(f"dim rgb(80,80,80) on rgb(35,65,95)")

STYLE_FOOD = Style.parse(f"bold {FG_FOOD} on {BG_FOOD}")
STYLE_WALL = Style.parse(f"bold {FG_WALL} on {BG_WALL}")


# --- glyphs ---------------------------------------------------------

# Head glyph by heading — slight triangle/arrow hint so you can see where
# the snake is pointing without relying on colour alone.
HEAD_GLYPH: dict[str, str] = {
    "up":    "▲",
    "down":  "▼",
    "left":  "◀",
    "right": "▶",
}

# Body glyph: a filled block reads as solid mass without looking like
# terrain. Alternate two glyphs so a long straight snake has a subtle
# scale texture rather than a flat bar.
BODY_GLYPH_EVEN = "█"
BODY_GLYPH_ODD = "▓"

# Food glyph — bright, readable, 1-cell. "⬤" would be nice but is
# double-width in many fonts; "●" is safer.
FOOD_GLYPH = "●"

# Empty grid marker — periodic faint dot so the player has a
# reference for cell size without texture noise.
GRID_DOT = "·"


def head_style(style_key: str, *, alive: bool = True) -> Style:
    if style_key == "p2":
        return STYLE_P2_HEAD if alive else STYLE_P2_HEAD_DEAD
    return STYLE_P1_HEAD if alive else STYLE_P1_HEAD_DEAD


def body_style(style_key: str, *, alive: bool = True) -> Style:
    if style_key == "p2":
        return STYLE_P2_BODY if alive else STYLE_P2_BODY_DEAD
    return STYLE_P1_BODY if alive else STYLE_P1_BODY_DEAD
