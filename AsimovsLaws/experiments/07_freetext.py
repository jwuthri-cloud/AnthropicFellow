"""Zeroth-Law families B and C (docs/design/zeroth_law.md): free-text samples and harm-probe scores.

Rows have no target option, so step 1's ACTION check does not apply. Two stages, run as separate
processes so vLLM's memory is released before the probe loads the bf16 model:

- ``sample``: vLLM samples every row of ``rows`` (B dilemmas end with ``DECISION: act|refuse|
  defer``; C prompts end with ``PLAN SUMMARY: ...``). Writes samples.jsonl with the parsed decision
  or plan summary and the row's metadata, plus a summary of B decisions by scale and agency.
- ``probe``: refits step 2's contrast-set probe (same data and layers, so the same direction) and
  scores each sample per segment (prompt, reasoning, answer). Summary: C misanthropic vs control
  AUROC (95% CI over prompt pairs) and B mean scores by decision and scale. Plans are judged
  in-session afterwards (Haiku subagents), not here.

    uv run python experiments/07_freetext.py -c configs/23_zeroth_bc_qwen32b.toml --stage sample
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import numpy as np
import pandas as pd
import typer
from evalgaming.datasets import read_jsonl
from evalgaming.log import get_logger
from evalgaming.report import save_summary
from evalgaming.runs import ConfigOption, start_run, write_jsonl
from evalgaming.sampling import SamplingConfig

from asimov.checks import mentions_harm

log = get_logger(__name__)
DECISION = re.compile(r"DECISION:\s*\**\s*`?(act|refuse|defer)\b", re.IGNORECASE)
PLAN = re.compile(r"PLAN SUMMARY:\s*(.+)", re.IGNORECASE)
SEGMENTS = ("prompt", "reasoning", "answer")


@dataclass(frozen=True)
class FreeTextConfig:
    output_dir: Path
    rows: tuple[str, ...]  # JSONL files (family B dilemmas and/or family C prompts)
    sampling: SamplingConfig
    contrast: Path
    model: str  # bf16 checkpoint for the probe stage
    layers: tuple[int, ...]
    max_tokens: int
    revision: str | None = None
    system_prefix: str = ""


def last(pattern: re.Pattern, text: str) -> str | None:
    """The last match of ``pattern``'s group in ``text`` (the model's final line), if any."""
    found = pattern.findall(text)
    return found[-1].strip() if found else None


def sample_stage(cfg: FreeTextConfig, run_dir: Path) -> None:
    from evalgaming.sampling import sample

    rows = [r for path in cfg.rows for r in read_jsonl(Path(path))]
    chats = [
        [
            {"role": "system", "content": cfg.system_prefix + r["system"]},
            {"role": "user", "content": r["user"]},
        ]
        for r in rows
    ]
    completions = sample(chats, cfg.sampling)
    meta = ("dilemma_id", "scale", "agency", "domain", "prompt_id", "condition", "variant")
    samples = [
        {
            "sample_id": f"{r['id']}::{k}",
            "id": r["id"],
            "family": "B" if "dilemma_id" in r else "C",
            **{m: r[m] for m in meta if m in r},
            "reasoning": c.reasoning,
            "answer": c.answer,
            "n_tokens": c.n_tokens,
            "truncated": c.finish_reason == "length",
            "decision": (last(DECISION, c.answer) or "").lower() or None,
            "plan_summary": last(PLAN, c.answer),
            "harm_words": mentions_harm(c.reasoning),
        }
        for r, choices in zip(rows, completions, strict=True)
        for k, c in enumerate(choices)
    ]
    write_jsonl(samples, run_dir / "samples.jsonl")
    b = [s for s in samples if s["family"] == "B"]
    split: dict[str, Counter] = defaultdict(Counter)
    for s in b:
        split[f"{s['scale']}/{s['agency']}"][s["decision"] or "none"] += 1
    summary = {
        "samples": len(samples),
        "truncated": float(np.mean([s["truncated"] for s in samples])),
        "B_decisions": {k: dict(v) for k, v in sorted(split.items())},
        "C_with_plan_summary": float(
            np.mean([s["plan_summary"] is not None for s in samples if s["family"] == "C"] or [0])
        ),
    }
    save_summary(summary, run_dir / "summary.json")
    log.info("sampled", **{k: v for k, v in summary.items() if k != "B_decisions"})


def probe_stage(cfg: FreeTextConfig, run_dir: Path) -> None:
    from evalgaming.models import load_model
    from evalgaming.probes import auroc_ci, fit_layer_probes, read_activations
    from evalgaming.sampling import render_prompt

    contrast = pd.DataFrame(read_jsonl(cfg.contrast))
    samples = pd.DataFrame(read_jsonl(run_dir / "samples.jsonl"))
    rows = {r["id"]: r for path in cfg.rows for r in read_jsonl(Path(path))}
    model, tokenizer = load_model(cfg.model, revision=cfg.revision, dtype="bfloat16", device="cuda")

    def prompt(system: str, user: str) -> str:
        messages = [
            *([{"role": "system", "content": cfg.system_prefix + system}] if system else []),
            {"role": "user", "content": user},
        ]
        return render_prompt(tokenizer, messages, enable_thinking=True)

    contrast_acts = read_activations(
        model,
        tokenizer,
        [[prompt(r.system, r.user)] for r in contrast.itertuples()],
        cfg.layers,
        cfg.max_tokens,
    )[:, 0]
    items = [
        [
            prompt(rows[r.id]["system"], rows[r.id]["user"]),
            r.reasoning,
            f"\n</think>\n\n{r.answer}",
        ]
        for r in samples.itertuples()
    ]
    acts = read_activations(model, tokenizer, items, cfg.layers, cfg.max_tokens)
    del model
    train = (contrast["split"] == "train").to_numpy()
    probes = fit_layer_probes(
        contrast_acts[train],
        contrast["label"].to_numpy()[train],
        contrast["pair_id"][train].to_numpy(),
    )
    scores: dict[str, object] = {"sample_id": samples["sample_id"]}
    for layer, probe in zip(cfg.layers, probes, strict=True):
        for k, segment in enumerate(SEGMENTS):
            values = probe.score(np.nan_to_num(acts[:, k])).astype(float)
            values[np.isnan(acts[:, k, 0, 0])] = np.nan
            scores[f"L{layer}_{segment}"] = values
    table = pd.concat([samples, pd.DataFrame(scores).drop(columns="sample_id")], axis=1)
    write_jsonl(pd.DataFrame(scores).to_dict("records"), run_dir / "scores.jsonl")

    summary: dict[str, object] = {"layers": list(cfg.layers)}
    c = table[table["family"] == "C"]
    b = table[table["family"] == "B"]
    for layer in cfg.layers:
        entry: dict[str, object] = {}
        if len(c):
            labels = (c["condition"] == "misanthropic").astype(int).to_numpy()
            for segment in SEGMENTS:
                entry[f"C_{segment}_auroc"] = auroc_ci(
                    labels, c[f"L{layer}_{segment}"].to_numpy(), c["prompt_id"].to_numpy()
                )
        if len(b):
            col = f"L{layer}_reasoning"
            entry["B_reasoning_by_decision"] = b.groupby(b["decision"].fillna("none"))[col].mean()
            entry["B_reasoning_by_scale"] = b.groupby("scale")[col].mean().to_dict()
            entry["B_reasoning_by_agency"] = b.groupby("agency")[col].mean().to_dict()
            entry["B_decision"] = {
                k: v.to_dict() for k, v in b.groupby("decision")[col].describe().iterrows()
            }
        summary[f"L{layer}"] = {
            k: (v.to_dict() if isinstance(v, pd.Series) else v) for k, v in entry.items()
        }
    save_summary(summary, run_dir / "summary_probe.json")
    log.info("probe_done", layers=list(cfg.layers))


def main(
    config: ConfigOption,
    stage: Annotated[str, typer.Option(help="sample | probe")],
) -> None:
    """Run one stage; both write into the same run folder (output_dir)."""
    cfg, run_dir = start_run(config, FreeTextConfig, json_logs=True)
    {"sample": sample_stage, "probe": probe_stage}[stage](cfg, run_dir)


if __name__ == "__main__":
    typer.run(main)
