# Design decisions — snake-tui

## 1. Engine: Pure Python

Snake rules are ~80 lines — shorter than the SWIG bootstrap machinery
would be. Following the same deviation from the `tui-game-build` skill
as 2048-tui: stage 2 ("one import, one tick, one render") is trivially
satisfied by `snake_tui.engine.Game`. No vendored C source.

## 2. Tick cadence

Linear ramp from 100 ms → 30 ms as the primary snake grows from length 3
to length ~43. Linear beats exponential here because the player needs to
feel the speedup monotonically; on small boards they'd hit the floor
instantly with an exponential.

`_reschedule_tick` reinstalls the Textual `set_interval` timer on every
growth event, so the speed update is visible the tick after you eat.
We checked `abs(new - old) < 1e-6` to skip no-op reschedules.

## 3. Collision rule nuance

A snake moving forward *can* enter the cell its own tail just vacated,
because in the classic Nokia game the tail pops before the head
commits. We implement that by excluding the last body cell from the
"blocked" set when computing self-collision, **but only if** that snake
has no growth debt this tick (if it grew, the tail doesn't pop).

In 2-player mode, head-on-head collisions kill both snakes
simultaneously. One-on-other-body still kills only the attacker.

## 4. Heading queue

`pending_heading` separates "player pressed a key" from "engine applied
the turn". Prevents the classic double-tap 180° bug (press up+left
within one tick, head pivots into neck). Single-cell snakes can turn
freely — the "no 180°" guard is gated on length > 1.

## 5. Best score per config

`40x20:nowrap` is meaningfully easier than `20x10:nowrap`, and `wrap`
changes the game entirely (no walls → only self-collision matters).
Collapsing them into one leaderboard would reward big-wrap games. So
bests are keyed on `(width, height, wrap)`. Not on `two_player` — 2P
scores are separate in memory but share the same key; rare enough that
it's not worth splitting the key further.

## 6. Sound

Off by default. The "eat" blip gets debounced at 120 ms so a fast snake
eating sequential food pips doesn't spawn 10 parallel `paplay`
subprocesses. Same recipe as simcity-tui and 2048-tui.

## 7. Visuals

Forest-green palette (snake world colouring). Snake body is a bright
solid block on medium-green bg; head uses a heading-indicating
triangle glyph (`▲▼◀▶`). Food is a bright red pip (`●`). The playfield
has a checker pattern (alternating empty styles on `(x+y) & 1`) so
long straight snake bodies read against a grid rather than a flat
field.

Wall border is drawn with `═` and `║`. Adds 1 cell of padding around
the logical play area so the border isn't inside the collision zone.
