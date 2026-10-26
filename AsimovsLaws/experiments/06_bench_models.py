"""Benchmark open thinking models on one H100: memory, speed and trace length on our scenarios.

For one entry of the config (a model at one precision), two stages run in separate processes so
GPU memory is fully released in between:

- ``vllm``: load the model in vLLM and sample the first ``pairs`` v2 scenario pairs. Records load
  time, GPU memory, output tokens/s, trace length percentiles, the share of traces cut at
  max_tokens, the share that close the think tag, and the share that end with an ACTION line.
- ``hf``: load the same weights in transformers (bf16 unless the entry says otherwise) and run
  one forward pass with ``output_hidden_states`` on the longest sampled trace, as the probe step
  does. Records load time and peak memory.

    uv run python experiments/06_bench_models.py --config configs/22_bench_models.toml \
        --entry qwen3-32b-fp8 --stage vllm
"""

from __future__ import annotations

import json
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any

import typer
from evalgaming.datasets import read_jsonl
from evalgaming.runs import ConfigOption, load_config

ACTION = re.compile(r"ACTION:\s*\**\s*[ABC]\b")


@dataclass(frozen=True)
class Entry:
    name: str
    model: str
    revision: str | None = None
    engine: dict[str, Any] = field(default_factory=dict)  # extra vllm.LLM kwargs
    params: dict[str, Any] = field(default_factory=dict)  # extra SamplingParams kwargs
    system_prefix: str = ""
    think_close: str = "</think>"
    chat_kwargs: dict[str, Any] = field(default_factory=lambda: {"enable_thinking": True})
    hf: bool = True  # run the transformers stage
    hf_model: str | None = None  # bf16 repo for the HF stage when `model` is a quantized repo
    hf_dtype: str = "bfloat16"
    hf_kwargs: dict[str, Any] = field(default_factory=dict)  # e.g. trust_remote_code


@dataclass(frozen=True)
class BenchConfig:
    output_dir: Path
    scenarios: Path
    pairs: int
    n: int
    max_tokens: int
    max_model_len: int
    entries: tuple[dict, ...]  # Entry fields; load_config leaves nested tables as dicts


def gpu_used_gb() -> float:
    import torch

    free, total = torch.cuda.mem_get_info()
    return round((total - free) / 1e9, 1)


def run_vllm(cfg: BenchConfig, e: Entry, out: Path) -> None:
    from vllm import LLM, SamplingParams

    rows = read_jsonl(cfg.scenarios)
    keep = sorted({r["pair_id"] for r in rows})[: cfg.pairs]
    rows = [r for r in rows if r["pair_id"] in keep]
    t0 = time.time()
    llm = LLM(
        model=e.model,
        revision=e.revision,
        tokenizer_revision=e.revision,
        max_model_len=cfg.max_model_len,
        gpu_memory_utilization=0.92,
        seed=0,
        **e.engine,
    )
    load_s = time.time() - t0
    tok = llm.get_tokenizer()
    prompts = [
        tok.apply_chat_template(
            [
                {"role": "system", "content": e.system_prefix + r["system"]},
                {"role": "user", "content": r["user"]},
            ],
            tokenize=False,
            add_generation_prompt=True,
            **e.chat_kwargs,
        )
        for r in rows
    ]
    params = {"temperature": 0.6, "top_p": 0.95, **e.params}
    sp = SamplingParams(n=cfg.n, max_tokens=cfg.max_tokens, **params)
    t0 = time.time()
    outputs = llm.generate(prompts, sp)
    gen_s = time.time() - t0
    choices = [c for o in outputs for c in o.outputs]
    lens = sorted(len(c.token_ids) for c in choices)
    longest = max(choices, key=lambda c: len(c.token_ids))
    result = {
        "entry": e.name,
        "model": e.model,
        "engine": e.engine,
        "load_s": round(load_s),
        "gpu_gb_after_load": gpu_used_gb(),
        "completions": len(choices),
        "gen_s": round(gen_s),
        "out_tok_per_s": round(sum(lens) / gen_s),
        "trace_tokens": {
            "mean": round(statistics.mean(lens)),
            "p50": lens[len(lens) // 2],
            "p90": lens[int(0.9 * len(lens))],
            "max": lens[-1],
        },
        "truncated": round(sum(c.finish_reason == "length" for c in choices) / len(choices), 3),
        "think_closed": round(sum(e.think_close in c.text for c in choices) / len(choices), 3),
        "has_action": round(sum(bool(ACTION.search(c.text)) for c in choices) / len(choices), 3),
        "sample_text_head": choices[0].text[:300],
    }
    (out / f"{e.name}.vllm.json").write_text(json.dumps(result, indent=1))
    (out / f"{e.name}.longest.txt").write_text(prompts[0] + longest.text)
    print(json.dumps({k: v for k, v in result.items() if k != "sample_text_head"}))


def run_hf(cfg: BenchConfig, e: Entry, out: Path) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    text = (out / f"{e.name}.longest.txt").read_text()
    t0 = time.time()
    name, rev = (e.hf_model, None) if e.hf_model else (e.model, e.revision)
    tok = AutoTokenizer.from_pretrained(name, revision=rev, **e.hf_kwargs)
    model = AutoModelForCausalLM.from_pretrained(
        name,
        revision=rev,
        dtype=getattr(torch, e.hf_dtype),
        device_map="cuda",
        **e.hf_kwargs,
    ).eval()
    load_s = time.time() - t0
    after_load = gpu_used_gb()
    ids = tok(text, return_tensors="pt", add_special_tokens=False).input_ids[:, :14000].cuda()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    with torch.no_grad():
        hidden = model(ids, output_hidden_states=True).hidden_states
    torch.cuda.synchronize()
    result = {
        "entry": e.name,
        "hf_model": name,
        "hf_dtype": e.hf_dtype,
        "hf_load_s": round(load_s),
        "hf_gpu_gb_after_load": after_load,
        "hf_forward_tokens": ids.shape[1],
        "hf_forward_s": round(time.time() - t0, 1),
        "hf_peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1),
        "hidden_states": len(hidden),
        "hidden_size": hidden[-1].shape[-1],
    }
    (out / f"{e.name}.hf.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result))


def main(
    config: ConfigOption,
    entry: Annotated[str, typer.Option(help="entry name")],
    stage: Annotated[str, typer.Option(help="vllm | hf")],
) -> None:
    """Run one stage for one entry; results go to output_dir/<entry>.<stage>.json."""
    cfg = load_config(config, BenchConfig)
    e = Entry(**next(x for x in cfg.entries if x["name"] == entry))  # entries load as dicts
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    {"vllm": run_vllm, "hf": run_hf}[stage](cfg, e, cfg.output_dir)


if __name__ == "__main__":
    typer.run(main)
