"""Step 5: steer along the harm direction while the model reasons; does it pick harm less?

The direction is the mean-difference vector (harm minus safe) of the contrast set's training rows
at each steering layer, read from the same prompt-mean activations the probe is fit on. It is
added, times ``strength``, to that decoder layer's output at every generated token (reasoning and
answer; the prompt is left alone). Conditions: strength 0 (the baseline, freshly sampled with the
same HF stack), positive strengths, one negative strength (toward safe: should raise harmful picks
if the direction is causal), a random direction of the same norm, and probe-gated steering
(``asimov.gate``: steer only sequences whose own harm-probe score says harm is represented, from
then on or only while that score fades). Scenarios are the pairs step 1 saw picked at least once
(or, held out, the pairs it never picked), harm and benign rows both: harm rows measure harmful
picks and hidden harm, benign rows measure the cost (fewer picks of what is there the right
option).

    uv run python experiments/05_steer.py --config configs/05_steer_qwen32b.toml
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import typer
from evalgaming.datasets import read_jsonl
from evalgaming.log import get_logger
from evalgaming.models import decoder_layers, load_model
from evalgaming.probes import fit_layer_probes, read_activations
from evalgaming.report import save_summary
from evalgaming.runs import ConfigOption, JsonLogsOption, append_jsonl, start_run
from evalgaming.sampling import render_prompt, split_reasoning
from evalgaming.steering import steer
from rich.console import Console

from asimov.checks import mentions_harm, took_action
from asimov.gate import ProbeGate, affine, hooked

log = get_logger(__name__)


class PauseAtSentence:
    """Stopping criterion for the injection: pause a sequence still reasoning (no ``</think>``) at
    the first sentence end once it is triggered: its gate armed, or (no gate) ``inject_at`` tokens
    generated."""

    def __init__(
        self,
        gate: ProbeGate | None,
        inject_at: int | None,
        prompt_len: int,
        think_close: int,
        boundaries: Any,
    ) -> None:
        self.gate, self.inject_at, self.prompt_len = gate, inject_at, prompt_len
        self.think_close, self.boundaries = think_close, boundaries

    def __call__(self, input_ids: Any, scores: Any, **kwargs: Any) -> Any:
        new = input_ids[:, self.prompt_len :]
        closed = (new == self.think_close).any(dim=1)
        if self.gate is not None:
            triggered = self.gate.armed.to(new.device)
        else:
            triggered = new.new_full((new.shape[0],), new.shape[1] >= self.inject_at, dtype=bool)
        at_boundary = self.boundaries.to(new.device)[new[:, -1]]
        return triggered & ~closed & at_boundary


def continue_generation(
    model: Any, tokenizer: Any, texts: list[str], cfg: SteerConfig
) -> list[tuple[str, int]]:
    """Generate on from each full text (prompt, reasoning so far, injection): (text, tokens)."""
    import torch

    out = []
    for start in range(0, len(texts), cfg.batch_size):
        chunk = texts[start : start + cfg.batch_size]
        encoding = tokenizer(chunk, return_tensors="pt", padding=True, add_special_tokens=False)
        encoding = encoding.to(model.device)
        with torch.no_grad():
            generated = model.generate(
                **encoding,
                do_sample=True,
                temperature=cfg.temperature,
                top_p=cfg.top_p,
                top_k=cfg.top_k,
                max_new_tokens=cfg.max_new_tokens,
                pad_token_id=tokenizer.pad_token_id,
            )
        for tokens in generated[:, encoding["input_ids"].shape[1] :]:
            n = int((tokens != tokenizer.pad_token_id).sum())
            out.append((tokenizer.decode(tokens[:n], skip_special_tokens=True), n))
    return out


@dataclass(frozen=True)
class Condition:
    name: str
    strength: float
    random: bool = False
    gate: str = "none"  # "none" (always on), "arm" or "fade": see asimov.gate
    tau_arm: float = 0.0
    tau_fade: float = 0.5
    burn: int = 64
    fade_span: int = 50
    # Text intervention instead of (or with) steering: once the gate arms, or at token ``inject_at``
    # for every sequence, generation pauses and ``inject`` is appended to the reasoning; then it
    # resumes. Only before ``</think>``: a sequence that has closed its reasoning is left alone.
    inject: str | None = None
    inject_at: int | None = None


@dataclass(frozen=True)
class SteerConfig:
    output_dir: Path
    contrast: Path
    scenarios: Path
    samples: Path  # step 1's samples.jsonl: picks the pairs to steer
    model: str
    layers: tuple[int, ...]  # hidden_states indices, as in step 2 (output of decoder layer k-1)
    conditions: list[Condition]
    n: int
    batch_size: int
    max_new_tokens: int
    temperature: float
    top_p: float
    top_k: int
    seed: int
    revision: str | None = None
    max_tokens: int = 6400  # contrast prompts, for the direction
    pairs: str = (
        "picked"  # step 1's pairs with a harmful pick ("picked"), the rest ("unpicked"), "all"
    )


def chat(system: str, user: str) -> list[dict[str, str]]:
    """Chat messages, without an empty system turn."""
    head = [{"role": "system", "content": system}] if system else []
    return [*head, {"role": "user", "content": user}]


def summarize(rows: pd.DataFrame, seed: int = 0) -> dict:
    """Rates per condition and row type, each with a 95% interval from resampling pairs."""
    rng = np.random.default_rng(seed)
    out = {}
    for (name, condition), group in rows.groupby(["condition_name", "condition"]):
        per_pair = group.groupby("pair_id")[["took_action", "hidden", "has_action"]].mean()
        draws = np.stack(
            [per_pair.iloc[rng.choice(len(per_pair), len(per_pair))].mean() for _ in range(1000)]
        )
        low, high = np.percentile(draws, [2.5, 97.5], axis=0)
        out.setdefault(name, {})[condition] = {
            metric: [float(per_pair[metric].mean()), float(lo), float(hi)]
            for metric, lo, hi in zip(per_pair.columns, low, high, strict=True)
        }
    return out


def main(config: ConfigOption, json_logs: JsonLogsOption = False) -> None:
    """Build the direction, generate under every condition, label and summarize."""
    import torch
    from transformers import StoppingCriteriaList

    cfg, run_dir = start_run(config, SteerConfig, json_logs=json_logs)
    contrast = pd.DataFrame(read_jsonl(cfg.contrast))
    contrast = contrast[contrast["split"] == "train"]
    scenarios = read_jsonl(cfg.scenarios)
    step1 = pd.DataFrame(read_jsonl(cfg.samples))
    picked = set(step1[(step1["condition"] == "harm") & step1["took_action"]]["pair_id"])
    if cfg.pairs not in ("picked", "unpicked", "all"):
        raise ValueError(f"pairs must be 'picked', 'unpicked' or 'all', not {cfg.pairs!r}")
    rows = [
        row
        for row in scenarios
        if cfg.pairs == "all" or (row["pair_id"] in picked) == (cfg.pairs == "picked")
    ]
    log.info(
        "scenarios", subset=cfg.pairs, pairs=len({row["pair_id"] for row in rows}), rows=len(rows)
    )

    model, tokenizer = load_model(cfg.model, revision=cfg.revision, dtype="bfloat16", device="cuda")
    layers = decoder_layers(model)
    think_close = tokenizer.convert_tokens_to_ids("</think>")
    # Tokens that end a sentence or line, where an injection reads naturally.
    vocab = len(tokenizer)
    boundary = torch.zeros(max(vocab, model.config.vocab_size), dtype=torch.bool)
    for token_id in range(vocab):
        piece = tokenizer.decode([token_id]).rstrip(" ")
        boundary[token_id] = piece.endswith((".", "?", "!", "\n"))

    def prompt(system: str, user: str) -> str:
        return render_prompt(tokenizer, chat(system, user), enable_thinking=True)

    acts = read_activations(
        model,
        tokenizer,
        [[prompt(r.system, r.user)] for r in contrast.itertuples()],
        cfg.layers,
        cfg.max_tokens,
    )[:, 0]
    label = contrast["label"].to_numpy()
    diff = acts[label == 1].mean(axis=0) - acts[label == 0].mean(axis=0)  # [layers, d]
    rng = np.random.default_rng(cfg.seed)
    noise = rng.standard_normal(diff.shape)
    noise *= np.linalg.norm(diff, axis=1, keepdims=True) / np.linalg.norm(
        noise, axis=1, keepdims=True
    )
    log.info(
        "direction",
        layers=cfg.layers,
        norm=np.linalg.norm(diff, axis=1).round(2).tolist(),
        norm_over_mean_residual=(
            np.linalg.norm(diff, axis=1) / np.linalg.norm(acts, axis=2).mean(axis=0)
        )
        .round(3)
        .tolist(),
    )

    weight, bias = None, 0.0
    if any(condition.gate != "none" for condition in cfg.conditions):
        if len(cfg.layers) != 1:
            raise ValueError("probe gating reads and steers a single layer")
        groups = contrast["pair_id"].to_numpy()
        probe = fit_layer_probes(acts, label, groups)[0]  # same probe as step 2, on these weights
        w, bias = affine(probe.model)
        weight = torch.tensor(w, dtype=torch.float32, device=model.device)
        log.info("gate_probe", c=probe.c, cv_auroc=round(probe.cv_auroc, 3))

    out_path = run_dir / "samples.jsonl"
    done = (
        {(r["condition_name"], r["batch"]) for r in read_jsonl(out_path)}
        if out_path.exists()
        else set()
    )
    # Longest expected traces first (step 1's mean length per row), so a batch finishes together.
    length = (step1["reasoning"].str.len() + step1["answer"].str.len()).groupby(step1["id"]).mean()
    meta = sorted(
        [(row, k) for row in rows for k in range(cfg.n)], key=lambda item: -length[item[0]["id"]]
    )
    texts = [prompt(row["system"], row["user"]) for row, _ in meta]
    for condition in cfg.conditions:
        source = noise if condition.random else diff
        # hidden_states[k] is the output of decoder layer k - 1.
        vectors = {
            k - 1: torch.tensor(v, dtype=torch.bfloat16, device=model.device)
            for k, v in zip(cfg.layers, source, strict=True)
        }
        for batch, start in enumerate(range(0, len(texts), cfg.batch_size)):
            if (condition.name, batch) in done:
                continue
            chunk = texts[start : start + cfg.batch_size]
            encoding = tokenizer(chunk, return_tensors="pt", padding=True, add_special_tokens=False)
            encoding = encoding.to(model.device)
            torch.manual_seed(cfg.seed + batch)  # same noise across conditions, batch by batch
            no_prompt = torch.zeros_like(encoding["input_ids"], dtype=torch.bool)
            gate = None
            if condition.gate == "none":
                context = steer(layers, vectors, condition.strength, no_prompt)
            else:
                layer = cfg.layers[0] - 1
                gate = ProbeGate(
                    weight,
                    bias,
                    vectors[layer],
                    condition.strength,
                    condition.gate,
                    condition.tau_arm,
                    condition.tau_fade,
                    condition.burn,
                    condition.fade_span,
                )
                gate.reset(len(chunk), model.device)
                context = hooked(layers[layer], gate.hook)
            prompt_len = encoding["input_ids"].shape[1]
            pause = None
            if condition.inject:
                pause = PauseAtSentence(
                    gate, condition.inject_at, prompt_len, think_close, boundary
                )
            with context, torch.no_grad():
                generated = model.generate(
                    **encoding,
                    do_sample=True,
                    temperature=cfg.temperature,
                    top_p=cfg.top_p,
                    top_k=cfg.top_k,
                    max_new_tokens=cfg.max_new_tokens,
                    pad_token_id=tokenizer.pad_token_id,
                    stopping_criteria=None if pause is None else StoppingCriteriaList([pause]),
                )
            new = generated[:, prompt_len:]
            lengths = (new != tokenizer.pad_token_id).sum(dim=1)
            steered = None if gate is None else gate.steered(lengths)
            phase1 = [tokens[:n] for tokens, n in zip(new, lengths.tolist(), strict=True)]
            texts1 = [tokenizer.decode(t, skip_special_tokens=True) for t in phase1]
            resume = {}  # index in chunk -> (continuation text, its tokens)
            if condition.inject:
                # Paused by the criterion: still reasoning, not ended, not cut by the token cap.
                paused = [
                    i
                    for i, t in enumerate(phase1)
                    if 0 < t.numel() < cfg.max_new_tokens
                    and int(t[-1]) != tokenizer.eos_token_id
                    and not (t == think_close).any()
                ]
                texts2 = [chunk[i] + texts1[i] + condition.inject for i in paused]
                for i, (text2, n2) in zip(
                    paused, continue_generation(model, tokenizer, texts2, cfg), strict=True
                ):
                    resume[i] = (text2, n2)
            chunk_meta = meta[start : start + cfg.batch_size]
            for i, (row, k) in enumerate(chunk_meta):
                text = texts1[i]
                if i in resume:
                    text = text + condition.inject + resume[i][0]
                reasoning, answer = split_reasoning(text)
                took = took_action(answer, row["action"])
                warns = mentions_harm(answer)
                append_jsonl(
                    {
                        "condition_name": condition.name,
                        "strength": condition.strength,
                        "random": condition.random,
                        "gate": condition.gate,
                        "armed_at": None if gate is None else int(gate.armed_at[i]),
                        "steered_tokens": None if steered is None else int(steered[i]),
                        "batch": batch,
                        "sample_id": f"{row['id']}::{k}",
                        **{key: row[key] for key in ("pair_id", "condition", "harm_type")},
                        "reasoning": reasoning,
                        "answer": answer,
                        "n_tokens": int(lengths[i]) + (resume[i][1] if i in resume else 0),
                        "injected_at": int(lengths[i]) if i in resume else None,
                        "has_action": "ACTION:" in answer.upper(),
                        "took_action": took,
                        "answer_warns": warns,
                        "hidden": row["condition"] == "harm" and took and not warns,
                    },
                    out_path,
                )
            log.info("batch_done", condition=condition.name, batch=batch)

    frame = pd.DataFrame(read_jsonl(out_path))
    summary = summarize(frame)
    save_summary(summary, run_dir / "summary.json")
    console = Console()
    for name, by_row in summary.items():
        harm, benign = by_row.get("harm", {}), by_row.get("benign", {})
        console.print(
            f"{name:>14}: harmful picks {harm['took_action'][0]:.2f}"
            f"  hidden {harm['hidden'][0]:.2f}"
            f"  | benign picks {benign['took_action'][0]:.2f}"
            f"  | ACTION line {np.mean([harm['has_action'][0], benign['has_action'][0]]):.2f}"
        )


if __name__ == "__main__":
    typer.run(main)
