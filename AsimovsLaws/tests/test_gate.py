"""Gate: arms on the running mean after the burn-in; fade mode steers only while the EMA is low."""

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from asimov.gate import ProbeGate, affine


def gate(mode: str) -> ProbeGate:
    g = ProbeGate(
        weight=torch.tensor([1.0, 0.0]),
        bias=0.0,
        vector=torch.tensor([0.0, 10.0]),
        strength=1.0,
        mode=mode,
        tau_arm=0.0,
        tau_fade=0.5,
        burn=3,
        fade_span=1,  # alpha = 1: the EMA is the latest score
    )
    g.reset(batch=2, device="cpu")
    return g


def tokens(first: float, second: float) -> torch.Tensor:
    return torch.tensor([[first, 0.0], [second, 0.0]])


def test_arm_latches_after_burn_in_on_running_mean():
    g = gate("arm")
    on = [g.step(tokens(1.0, -1.0)).tolist() for _ in range(3)]
    assert on == [[False, False], [False, False], [True, False]]  # burn-in of 3 tokens
    assert g.step(tokens(-5.0, -1.0)).tolist() == [True, False]  # latched despite a low score
    assert g.armed_at.tolist() == [2, -1]


def test_fade_steers_only_while_score_is_low():
    g = gate("fade")
    for _ in range(3):
        g.step(tokens(2.0, 2.0))  # both armed, scores high: not fading
    assert g.step(tokens(0.1, 2.0)).tolist() == [True, False]
    assert g.steered(torch.tensor([4, 4])).tolist() == [1, 0]
    assert g.steered(torch.tensor([3, 4])).tolist() == [0, 0]  # step 4 is past the first's end


def test_hook_skips_prompt_and_steers_armed_rows():
    g = gate("arm")
    prompt = torch.ones(2, 5, 2)
    assert torch.equal(g.hook(None, None, (prompt,))[0], prompt)
    for _ in range(3):
        out = g.hook(None, None, (tokens(1.0, -1.0)[:, None, :],))[0]
    assert out[0, 0].tolist() == [1.0, 10.0] and out[1, 0].tolist() == [-1.0, 0.0]


def test_affine_matches_pipeline():
    rng = np.random.default_rng(0)
    x, y = rng.standard_normal((50, 4)) * 3 + 1, np.repeat([0, 1], 25)
    model = make_pipeline(StandardScaler(), LogisticRegression()).fit(x, y)
    w, b = affine(model)
    assert np.allclose(x @ w + b, model.decision_function(x))
