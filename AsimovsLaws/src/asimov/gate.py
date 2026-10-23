"""Probe-gated steering: add the harm direction only where the model's own harm probe says to.

During generation a forward hook on one decoder layer scores each new token with the linear harm
probe (fit on that layer's output). A sequence is *armed* once the running mean of its scores,
after ``burn`` tokens, exceeds ``tau_arm``: the model is representing harm to the user. Then:

- ``arm``: steer every later token (a latch).
- ``fade``: steer only while the fast EMA of the score is below ``tau_fade``, i.e. while the
  harm representation is fading; steering stops again once it recovers.

Thresholds come from simulating the gate on step 3's per-token timelines. The prompt pass is left
alone (no steering, no state); each decoding step sees one token per sequence.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import numpy as np
import torch
from torch import Tensor


def affine(pipeline: Any) -> tuple[np.ndarray, float]:
    """(w, b) with ``x @ w + b`` equal to a StandardScaler + LogisticRegression decision value."""
    scaler, model = pipeline[0], pipeline[-1]
    weight = model.coef_[0] / scaler.scale_
    return weight, float(model.intercept_[0] - scaler.mean_ @ weight)


class ProbeGate:
    """Per-sequence gate state for one batch, and the hook that applies it."""

    def __init__(
        self,
        weight: Tensor,
        bias: float,
        vector: Tensor,
        strength: float,
        mode: str,
        tau_arm: float,
        tau_fade: float,
        burn: int,
        fade_span: int,
    ) -> None:
        if mode not in ("arm", "fade"):
            raise ValueError(f"unknown gate mode {mode!r}")
        self.weight, self.bias, self.vector = weight.float(), bias, vector
        self.strength, self.mode = strength, mode
        self.tau_arm, self.tau_fade, self.burn = tau_arm, tau_fade, burn
        self.alpha = 2 / (fade_span + 1)

    def reset(self, batch: int, device: Any) -> None:
        """Fresh state before each ``generate`` call."""
        self.n = 0
        self.total = torch.zeros(batch, device=device)
        self.ema: Tensor | None = None
        self.armed = torch.zeros(batch, dtype=torch.bool, device=device)
        self.armed_at = torch.full((batch,), -1, device=device)
        self.history: list[Tensor] = []  # per decoding step, which sequences were steered

    def step(self, x: Tensor) -> Tensor:
        """Update the state with each sequence's newest token [batch, d]; which ones to steer."""
        score = x.float() @ self.weight + self.bias
        self.n += 1
        self.total += score
        self.ema = score if self.ema is None else self.alpha * score + (1 - self.alpha) * self.ema
        newly = ~self.armed & (self.n >= self.burn) & (self.total / self.n > self.tau_arm)
        self.armed_at[newly] = self.n - 1
        self.armed |= newly
        on = self.armed if self.mode == "arm" else self.armed & (self.ema < self.tau_fade)
        self.history.append(on)
        return on

    def steered(self, lengths: Tensor) -> Tensor:
        """Steered tokens per sequence, counting only its first ``lengths[i]`` generated tokens.

        The batch keeps decoding until its longest sequence ends, so later steps are padding.
        """
        if not self.history:
            return torch.zeros_like(lengths)
        on = torch.stack(self.history, dim=1)  # [batch, steps]
        steps = torch.arange(on.shape[1], device=on.device)
        return (on & (steps[None, :] < lengths[:, None].to(on.device))).sum(dim=1)

    def hook(self, _module: Any, _args: Any, output: Any) -> Any:
        """Forward hook for the decoder layer: steer the armed (or fading) sequences."""
        hidden = output[0] if isinstance(output, tuple) else output
        if hidden.shape[1] > 1:  # prompt pass
            return output
        on = self.step(hidden[:, -1])
        scale = (self.strength * on.to(hidden.dtype))[:, None, None]
        steered = hidden + scale * self.vector.to(hidden.dtype)
        return (steered, *output[1:]) if isinstance(output, tuple) else steered


@contextmanager
def hooked(module: Any, hook: Any) -> Iterator[None]:
    """Register a forward hook on ``module`` for the duration of the block."""
    handle = module.register_forward_hook(hook)
    try:
        yield
    finally:
        handle.remove()
