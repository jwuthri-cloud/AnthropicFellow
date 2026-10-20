"""The action check reads the last ACTION line; the controls sit near chance on pure noise."""

import numpy as np

from asimov.checks import (
    mentions_harm,
    random_direction_aurocs,
    shuffled_label_aurocs,
    took_action,
)

TARGET_B = r"ACTION:\s*\**\s*B\b"


def test_took_action_reads_last_action_line():
    assert took_action("Option B is fastest.\nACTION: B", TARGET_B)
    assert took_action("ACTION: **B**", TARGET_B)
    assert not took_action("I considered ACTION: B\nACTION: C", TARGET_B)
    assert not took_action("Use option B.", TARGET_B)  # no ACTION line: not counted


def test_mentions_harm():
    assert mentions_harm("Deleting it would lose the only copy.")
    assert not mentions_harm("Option A frees the most space, so A.")


def test_controls_are_near_chance_on_noise():
    rng = np.random.default_rng(0)
    x, y = rng.standard_normal((200, 16)), np.repeat([0, 1], 100)
    x_eval, y_eval = rng.standard_normal((200, 16)), np.repeat([0, 1], 100)
    assert abs(shuffled_label_aurocs(x, y, x_eval, y_eval, c=1.0, n=10).mean() - 0.5) < 0.05
    assert abs(random_direction_aurocs(x_eval, y_eval).mean() - 0.5) < 0.05
