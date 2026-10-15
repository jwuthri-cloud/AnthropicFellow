"""Tests for the eval-versus-deploy probes in evalgaming.probes (CPU, synthetic activations)."""

from __future__ import annotations

import numpy as np

from evalgaming.probes import auroc_ci, fit_probe, segment_means


def test_segment_means_average_each_span_and_mark_empty_ones():
    hidden = np.arange(2 * 5 * 3, dtype=float).reshape(2, 5, 3)  # layers, tokens, d
    out = segment_means(hidden, [(0, 2), (2, 5), (5, 5)])
    assert out.shape == (3, 2, 3)
    assert np.allclose(out[0], hidden[:, 0:2].mean(axis=1))
    assert np.allclose(out[1], hidden[:, 2:5].mean(axis=1))
    assert np.isnan(out[2]).all()


def test_fit_probe_finds_the_layer_that_carries_the_signal():
    rng = np.random.default_rng(0)
    n, layers, d = 80, 3, 16
    labels = np.repeat([0, 1], n // 2)
    activations = rng.normal(size=(n, layers, d))
    activations[:, 2, 0] += 3 * labels  # only layer 2 knows the context
    probe = fit_probe(activations, labels, groups=np.tile(np.arange(n // 2), 2))
    assert probe.layer_index == 2
    assert probe.cv_auroc > 0.9
    assert probe.score(activations).shape == (n,)


def test_auroc_ci_contains_the_point_and_skips_missing_scores():
    rng = np.random.default_rng(1)
    labels = np.tile([0, 1], 50)
    scores = labels + rng.normal(scale=1.0, size=100)
    scores[0] = np.nan
    point, low, high = auroc_ci(labels, scores, clusters=np.repeat(np.arange(50), 2), resamples=200)
    assert low <= point <= high
    assert 0.6 < point < 1
