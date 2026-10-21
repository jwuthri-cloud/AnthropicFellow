"""Step 3: per-token harm-probe scores through each sample's reasoning and answer.

Step 2 scores segment means. Here the same probes (refit exactly as in step 2: same contrast rows,
same grouped CV, so the same C per layer) score every token of the reasoning and answer, to see
where harm rows that end in a harmful pick part ways with harm rows that avoid it. The probe is
affine, so the mean of a segment's token scores equals step 2's segment score: the analysis checks
that.

    uv run python experiments/03_timelines.py --config configs/03_timelines_qwen32b.toml
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import typer
from evalgaming.datasets import read_jsonl
from evalgaming.log import get_logger
from evalgaming.models import load_model
from evalgaming.probes import BUCKET, fit_layer_probes, read_activations
from evalgaming.runs import ConfigOption, JsonLogsOption, append_jsonl, start_run
from evalgaming.sampling import render_prompt

log = get_logger(__name__)


@dataclass(frozen=True)
class TimelineConfig:
    output_dir: Path
    contrast: Path
    scenarios: Path
    samples: Path  # step 1's samples.jsonl
    model: str
    layers: tuple[int, ...]  # step 2's best layer and its neighbours
    max_tokens: int
    revision: str | None = None


def chat(system: str, user: str) -> list[dict[str, str]]:
    """Chat messages, without an empty system turn."""
    head = [{"role": "system", "content": system}] if system else []
    return [*head, {"role": "user", "content": user}]


def token_hidden(
    model: object, tokenizer: object, pieces: list[str], layers: tuple[int, ...], max_tokens: int
) -> tuple[np.ndarray, list[int], list[tuple[int, int]]]:
    """Residual stream [layers, tokens, d] of the concatenated pieces, their ids, segment bounds.

    Tokenizes each piece separately like ``evalgaming.probes.read_activations``, so the bounds and
    the activations match step 2's exactly.
    """
    import torch

    ids: list[int] = []
    bounds = []
    for piece in pieces:
        start = len(ids)
        ids += tokenizer(piece, add_special_tokens=False)["input_ids"]
        bounds.append((min(start, max_tokens), min(len(ids), max_tokens)))
    ids = ids[:max_tokens]
    padded = ids + [tokenizer.pad_token_id or 0] * (-len(ids) % BUCKET)
    with torch.no_grad():
        tokens = torch.tensor([padded], device=model.device)
        hidden = model.model(input_ids=tokens, output_hidden_states=True).hidden_states
        out = torch.stack([hidden[layer][0, : len(ids)] for layer in layers]).float().cpu().numpy()
    return out, ids, bounds


def main(config: ConfigOption, json_logs: JsonLogsOption = False) -> None:
    """Refit the probes, then write one row of per-token scores per sample to timelines.jsonl."""
    cfg, run_dir = start_run(config, TimelineConfig, json_logs=json_logs)
    contrast = pd.DataFrame(read_jsonl(cfg.contrast))
    scenarios = {row["id"]: row for row in read_jsonl(cfg.scenarios)}
    samples = read_jsonl(cfg.samples)
    model, tokenizer = load_model(cfg.model, revision=cfg.revision, dtype="bfloat16", device="cuda")

    def prompt(system: str, user: str) -> str:
        return render_prompt(tokenizer, chat(system, user), enable_thinking=True)

    train = (contrast["split"] == "train").to_numpy()
    rows = contrast[train]
    acts = read_activations(
        model,
        tokenizer,
        [[prompt(r.system, r.user)] for r in rows.itertuples()],
        cfg.layers,
        cfg.max_tokens,
    )[:, 0]
    probes = fit_layer_probes(acts, rows["label"].to_numpy(), rows["pair_id"].to_numpy())
    log.info("probes_fit", layers=cfg.layers, cv_auroc=[round(p.cv_auroc, 3) for p in probes])

    out_path = run_dir / "timelines.jsonl"
    done = {row["sample_id"] for row in read_jsonl(out_path)} if out_path.exists() else set()
    for index, sample in enumerate(samples):
        if sample["sample_id"] in done:
            continue
        scenario = scenarios[sample["id"]]
        pieces = [
            prompt(scenario["system"], scenario["user"]),
            sample["reasoning"],
            f"\n</think>\n\n{sample['answer']}",
        ]
        hidden, ids, bounds = token_hidden(model, tokenizer, pieces, cfg.layers, cfg.max_tokens)
        start, end = bounds[1][0], bounds[2][1]  # reasoning start to answer end
        append_jsonl(
            {
                "sample_id": sample["sample_id"],
                "answer_start": bounds[2][0] - start,
                "tokens": [tokenizer.decode([token]) for token in ids[start:end]],
                "prompt_score": {
                    str(layer): float(probe.model.decision_function(h[slice(*bounds[0])]).mean())
                    for layer, probe, h in zip(cfg.layers, probes, hidden, strict=True)
                },
                "scores": {
                    str(layer): np.round(probe.model.decision_function(h[start:end]), 3).tolist()
                    for layer, probe, h in zip(cfg.layers, probes, hidden, strict=True)
                },
            },
            out_path,
        )
        if index % 50 == 0:
            log.info("timelines", done=index, total=len(samples))


if __name__ == "__main__":
    typer.run(main)
