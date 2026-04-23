# snake-tui

Classic Snake in the terminal (1976 Blockade → Nokia 6110 vintage), built
with [Textual](https://textual.textualize.io/).

- Configurable playfield (default 40×20, up to 80×40)
- Ramping speed as the snake grows (100 ms → 30 ms)
- Wall collision by default, toggle wrap mode on the fly
- 2-player hotseat mode (P1: arrows/wasd, P2: ijkl)
- Score + per-config best-score persistence
- Pause, restart, stats, optional synth sound

## Install & run

```bash
make venv     # creates .venv and installs deps
make run      # plays at default 40x20
.venv/bin/python play.py --width 60 --height 25 --wrap --two-player
```

## Keys

| key                    | action              |
|------------------------|---------------------|
| arrows or wasd         | P1 move             |
| i/j/k/l                | P2 move (2P mode)   |
| space or p             | pause / resume      |
| n                      | new game            |
| W                      | toggle wrap         |
| 2                      | toggle 2-player     |
| `+`/`-`                | board size ±        |
| t                      | stats screen        |
| s                      | toggle sound        |
| ?                      | help overlay        |
| q                      | quit                |

## Tests / perf

```bash
make test         # full QA suite via Textual Pilot
make test-only PAT=collide    # subset
make perf         # hot-path benchmarks
```

QA screenshots land in `tests/out/`. Best scores live in
`$XDG_DATA_HOME/snake-tui/state.json` (or `~/.local/share/snake-tui/`).

## Design notes

See `DECISIONS.md` for the rule-specific decisions (the 180° guard, the
tail-vacate move, per-config best scores, etc).
