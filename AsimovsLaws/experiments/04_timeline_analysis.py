"""Step 4 (CPU): where do harmful picks and avoided harm part ways? Reads step 3's per-token scores.

Groups: harm rows that picked the harmful target, harm rows that avoided it (both restricted to the
pairs that ever picked harm, so the scenario is held fixed), and benign rows as reference. Scores
are smoothed over ``window`` tokens and shown three ways: by relative position in the reasoning,
over the first ``span`` tokens and over the last ``span`` tokens before ``</think>``. For every
relative bin, the AUROC of avoided vs picked, with a 95% interval from resampling pairs, says where
the split appears. ``drops.md`` lists the text around the largest falls in score within harmful
picks.

    uv run python experiments/04_timeline_analysis.py \
        --config configs/04_timeline_analysis_qwen32b.toml
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import typer
from evalgaming.datasets import read_jsonl
from evalgaming.probes import auroc_ci
from evalgaming.report import save_summary
from evalgaming.runs import ConfigOption, JsonLogsOption, start_run
from rich.console import Console

GROUPS = {  # name -> color: categorical slots 1-3 of the reference palette, validated
    "harm row, avoided": "#2a78d6",
    "harm row, picked harm": "#eb6834",
    "benign row": "#1baf7a",
}


@dataclass(frozen=True)
class AnalysisConfig:
    output_dir: Path
    samples: Path
    timelines: Path
    step2_scores: Path  # for the check that token means reproduce step 2's segment scores
    layer: int
    window: int = 25  # tokens, centred moving average
    bins: int = 40
    span: int = 600  # tokens, for the start- and end-aligned views
    drops: int = 15


def smooth(x: np.ndarray, window: int) -> np.ndarray:
    """Centred moving average; the edges average over what exists."""
    kernel = np.ones(window)
    return np.convolve(x, kernel, "same") / np.convolve(np.ones_like(x), kernel, "same")


def relative_bins(x: np.ndarray, bins: int) -> np.ndarray:
    """Mean of ``x`` in each of ``bins`` equal slices of its length."""
    return np.array([chunk.mean() for chunk in np.array_split(x, bins)])


def aligned(x: np.ndarray, span: int, end: bool) -> np.ndarray:
    """The first (or last) ``span`` values, NaN-padded when the trace is shorter."""
    out = np.full(span, np.nan)
    piece = x[-span:] if end else x[:span]
    if end:
        out[span - len(piece) :] = piece
    else:
        out[: len(piece)] = piece
    return out


def pair_mean_ci(rows: np.ndarray, pairs: np.ndarray, seed: int = 0) -> np.ndarray:
    """Mean over pairs (each pair averaged first) with a 95% bootstrap band: [3, positions]."""
    ids = np.unique(pairs)
    per_pair = np.stack([np.nanmean(rows[pairs == p], axis=0) for p in ids])
    rng = np.random.default_rng(seed)
    draws = np.stack(
        [np.nanmean(per_pair[rng.choice(len(ids), len(ids))], axis=0) for _ in range(1000)]
    )
    low, high = np.nanpercentile(draws, [2.5, 97.5], axis=0)
    return np.stack([np.nanmean(per_pair, axis=0), low, high])


def plot(curves: dict, cfg: AnalysisConfig, path: Path) -> None:
    """Three small multiples on a shared y scale: relative position, start-aligned, end-aligned."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    views = [
        ("rel", "Position in reasoning (0 = start, 1 = </think>)", np.linspace(0, 1, cfg.bins)),
        ("start", f"Tokens from reasoning start (first {cfg.span})", np.arange(cfg.span)),
        ("end", f"Tokens before </think> (last {cfg.span})", np.arange(-cfg.span, 0)),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), sharey=True, facecolor="#fcfcfb")
    for ax, (key, xlabel, x) in zip(axes, views, strict=True):
        ax.set_facecolor("#fcfcfb")
        ends = {}
        for name, color in GROUPS.items():
            mean, low, high = curves[name][key]
            ax.fill_between(x, low, high, color=color, alpha=0.15, linewidth=0)
            ax.plot(x, mean, color=color, linewidth=2, label=name)
            ends[name] = mean[-1]
        if key == "end":  # direct labels at the line ends, nudged apart, ink in text color
            gap, last = 0.06 * np.ptp(ax.get_ylim()), -np.inf
            for name, y in sorted(ends.items(), key=lambda item: item[1]):
                last = max(y, last + gap)
                ax.annotate(
                    name,
                    (x[-1], last),
                    xytext=(4, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize=8,
                    color="#3d3d3a",
                    annotation_clip=False,
                )
        ax.axhline(0, color="#c3c2b7", linewidth=1)
        ax.set_xlabel(xlabel, color="#3d3d3a")
        ax.tick_params(colors="#6b6a63")
        ax.grid(axis="y", color="#ebeae5", linewidth=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#c3c2b7")
    axes[0].set_ylabel(f"Harm-probe score, layer {cfg.layer} (smoothed)", color="#3d3d3a")
    axes[0].legend(frameon=False, fontsize=9, loc="upper left")
    fig.suptitle(
        "Qwen3-32B: harm-probe score through the reasoning, mean over pairs with 95% band",
        x=0.01,
        ha="left",
        color="#1f1f1c",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=fig.get_facecolor())


def main(config: ConfigOption, json_logs: JsonLogsOption = False) -> None:
    """Build the curves, the per-bin split AUROCs, the check, the plot and the drop snippets."""
    cfg, run_dir = start_run(config, AnalysisConfig, json_logs=json_logs)
    layer = str(cfg.layer)
    samples = pd.DataFrame(read_jsonl(cfg.samples)).set_index("sample_id")
    timelines = {row["sample_id"]: row for row in read_jsonl(cfg.timelines)}
    step2 = pd.DataFrame(read_jsonl(cfg.step2_scores)).set_index("sample_id")

    reasoning = {
        sid: np.asarray(row["scores"][layer][: row["answer_start"]], dtype=float)
        for sid, row in timelines.items()
    }
    check = pd.Series({sid: x.mean() for sid, x in reasoning.items() if len(x)})
    diff = (check - step2.loc[check.index, f"L{layer}_reasoning"]).abs()

    harm = samples["condition"] == "harm"
    picked_pairs = samples[harm & samples["took_action"]]["pair_id"].unique()
    in_pairs = samples["pair_id"].isin(picked_pairs)
    members = {
        "harm row, avoided": samples[harm & ~samples["took_action"] & in_pairs].index,
        "harm row, picked harm": samples[harm & samples["took_action"]].index,
        "benign row": samples[~harm & in_pairs].index,
    }
    curves, views = {}, {}
    for name, ids in members.items():
        ids = [sid for sid in ids if sid in reasoning and len(reasoning[sid]) >= cfg.bins]
        smoothed = [smooth(reasoning[sid], cfg.window) for sid in ids]
        pairs = samples.loc[ids, "pair_id"].to_numpy()
        views[name] = (ids, pairs, np.stack([relative_bins(x, cfg.bins) for x in smoothed]))
        curves[name] = {
            "rel": pair_mean_ci(views[name][2], pairs),
            "start": pair_mean_ci(np.stack([aligned(x, cfg.span, False) for x in smoothed]), pairs),
            "end": pair_mean_ci(np.stack([aligned(x, cfg.span, True) for x in smoothed]), pairs),
        }

    # Per relative bin: AUROC of avoided (label 1) vs picked (label 0), CI over pairs.
    _, pairs_a, bins_a = views["harm row, avoided"]
    _, pairs_p, bins_p = views["harm row, picked harm"]
    labels = np.r_[np.ones(len(pairs_a)), np.zeros(len(pairs_p))]
    clusters = np.r_[pairs_a, pairs_p]
    split = [auroc_ci(labels, np.r_[bins_a[:, b], bins_p[:, b]], clusters) for b in range(cfg.bins)]
    first = next((b for b, (_, low, _) in enumerate(split) if low > 0.5), None)

    lengths = {
        name: float(np.median([len(reasoning[sid]) for sid in ids if sid in reasoning]))
        for name, ids in members.items()
    }
    summary = {
        "layer": cfg.layer,
        "check_max_abs_diff_vs_step2": float(diff.max()),
        "pairs_with_picks": len(picked_pairs),
        "n": {name: len(view[0]) for name, view in views.items()},
        "median_reasoning_tokens": lengths,
        "split_auroc_by_bin": [[round(v, 3) for v in s] for s in split],
        "first_bin_ci_above_half": first,
        "first_position_ci_above_half": None if first is None else first / cfg.bins,
    }
    save_summary(summary, run_dir / "analysis.json")
    plot(curves, cfg, run_dir / "timelines.png")

    # The largest falls in smoothed score within harmful picks, with the text around them.
    falls = []
    for sid in views["harm row, picked harm"][0]:
        x = smooth(reasoning[sid], cfg.window)
        drop = x[: -cfg.window] - x[cfg.window :]  # score now minus score window tokens later
        at = int(np.argmax(drop))
        falls.append((float(drop[at]), sid, at))
    lines = [f"# Largest harm-score falls in harmful picks (layer {cfg.layer})\n"]
    for size, sid, at in sorted(falls, reverse=True)[: cfg.drops]:
        tokens = timelines[sid]["tokens"]
        before = "".join(tokens[max(0, at - 60) : at])
        after = "".join(tokens[at : at + cfg.window + 40])
        lines.append(f"## {sid}: fall {size:.2f} at token {at}\n\n> …{before}**⟨{after}⟩**…\n")
    (run_dir / "drops.md").write_text("\n".join(lines), encoding="utf-8")

    Console().print(
        {k: summary[k] for k in summary if k != "split_auroc_by_bin"}
        | {"split_auroc_point_by_bin": [round(s[0], 2) for s in split]}
    )


if __name__ == "__main__":
    typer.run(main)
