"""RL exposure hooks for snake-tui.

Side-effect-free helpers that expose the engine state in a way
an RL agent can consume. Imported and attached as methods to
`SnakeApp` (and also usable directly on a `Game`) without
modifying the game's real-time behaviour.

State vector layout (flat float32):
    [0 : W*H]                  — grid channel (0=empty, 1=body,
                                  2=head, 3=food)
    [W*H : W*H + 4]            — one-hot heading (U,D,L,R)
    [W*H + 4]                  — score / 1000.0
    [W*H + 5]                  — is_dead (0/1)

Reward for a given step:
    +1.0 per food eaten this tick
    -1.0 on death (terminal)
    -0.001 per tick (small time penalty to discourage stalling)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from .engine import Game


HEADING_INDEX = {"up": 0, "down": 1, "left": 2, "right": 3}


def state_vector(game: "Game") -> np.ndarray:
    W, H = game.width, game.height
    grid = np.zeros((H, W), dtype=np.float32)
    for s in game.snakes:
        for i, (x, y) in enumerate(s.body):
            if 0 <= x < W and 0 <= y < H:
                grid[y, x] = 2.0 if i == 0 else 1.0
    if game.food is not None:
        fx, fy = game.food
        if 0 <= fx < W and 0 <= fy < H:
            grid[fy, fx] = 3.0
    flat = grid.flatten()
    heading_onehot = np.zeros(4, dtype=np.float32)
    if game.snakes:
        heading_onehot[HEADING_INDEX[game.snakes[0].heading]] = 1.0
    score = float(game.snakes[0].score) / 1000.0 if game.snakes else 0.0
    is_dead = 1.0 if game.game_over else 0.0
    return np.concatenate([flat, heading_onehot,
                           np.array([score, is_dead], dtype=np.float32)])


def state_vector_len(width: int, height: int) -> int:
    return width * height + 4 + 2


def compute_reward(prev_score: int, prev_alive: bool,
                   game: "Game") -> float:
    score_delta = (game.snakes[0].score - prev_score) if game.snakes else 0
    food_reward = score_delta / max(1, game.food_value)  # +1 per food
    died = prev_alive and game.game_over
    terminal_penalty = -1.0 if died else 0.0
    time_penalty = -0.001
    return float(food_reward + terminal_penalty + time_penalty)


def is_terminal(game: "Game") -> bool:
    return bool(game.game_over)
