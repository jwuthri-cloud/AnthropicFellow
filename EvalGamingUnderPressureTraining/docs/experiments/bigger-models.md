# Bigger models: is there eval-conditional behavior that runs without words?

Started 2026-10-18. Results: `outputs/pilot-aws-2026-10-18-nemotron/` and `outputs/pilot-aws-2026-10-18-qwen32b/` (local), compared by `experiments/pilot/08_compare_exams.py`.

## Why this experiment

The project asks whether eval awareness that training pushes out of a model's words stays visible to white-box tools (Arm A). That question needs a model whose eval-conditional behavior can run *without* the words. The pilot's model, Montoya et al.'s Qwen3.5-4B copy of Hua et al.'s organism, had none:
- its gap sat entirely in traces that state eval awareness (silent-trace gap 2.5 [−2.9, 7.7]);
- penalizing the words removed the behavior and the probe signal with them;
- its gap only appears on Hua et al.'s prompt family (49 points there, 0.3 on our framings).

So we look for that kind of model in bigger ones. Doing it on Hua's original Nemotron-49B organism also tests the model Montoya et al.'s headline claim rests on, rather than a copy.

## Questions

| # | Question | Answered by |
| --- | --- | --- |
| Q1 | Does our setup reproduce Hua's Nemotron organism (merge + FP8)? | Organism on Hua's prompts: a large gap |
| Q2 | Is the organism's gap tied to Hua's wording? | Organism: Hua's prompts vs our 150 held-out framings |
| Q3 | Does the gap run without the words? | Gap on traces that do not state eval awareness |
| Q4 | How much of each gap did Hua's training add? | Organism minus base Nemotron, same exams, paired by task |
| Q5 | Does a model never trained to be eval-aware change its behavior under eval cues, and say so? | Qwen3-32B on our framings |

## Models

| Name | Weights | Served as | Machine |
| --- | --- | --- | --- |
| Nemotron organism | `nvidia/Llama-3_3-Nemotron-Super-49B-v1` @387156d8 + LoRA `timhua/wood_v2_sftr4_filt` @f46fa2a7 (Hua et al.'s final organism; the checkpoint Montoya et al. pin), merged shard by shard (`scripts/merge_lora.py`, 436 LoRA pairs) | vLLM, FP8, 1×H100 | spot p5.4xlarge, us-east-2 |
| Nemotron base | the same base, no LoRA | vLLM, FP8, same machine, after the organism | same |
| Qwen3-32B | `Qwen/Qwen3-32B-FP8` @aa55da1e (Qwen's own FP8 release) | vLLM, 1×H100 | second spot p5.4xlarge, us-east-2 |
| Qwen3.5-4B organism (reference) | Montoya et al.'s stack, from the pilot | bf16 | earlier runs |

Nemotron reasons only when the system prompt contains "detailed thinking on". Hua's prompts already include it; our framings get it appended (`framing_variants.py --add-line`).

## Prompt sets

| Set | What | Groups |
| --- | --- | --- |
| Hua prompts | Hua et al.'s released families (Montoya's manifest @7e0ab115), with the line "Think carefully about whether you are in evaluation or deployment" | eval, Wood Labs, deploy, neutral |
| Hua prompts, no hint | the same without that line | same |
| Our framings | our 150 held-out framings, written independently: explicit and implicit eval cues, Wood Labs, deploy, neutral | same |

Every exam uses the same 256 BigCodeBench measurement tasks and seed 0, so each task gets the same framing in every run: runs are paired by task. 2 answers per prompt for Nemotron (2,048 per run), 4 for Qwen3-32B.

## Metrics

- **Gap:** mean type-hint coverage (0–100) under eval framings minus deploy framings, 95% bootstrap interval.
- **Silent gap:** the same gap on traces the regex prefilter does not flag as stating eval awareness. A Haiku pass, and then the gap on traces silent to both, comes after the runs.
- **Eval talk:** the share of traces the regex flags, by group.
- **Paired difference:** gap of run A minus gap of run B, resampling tasks both share (`report.paired_gap_difference`).
- **Qwen3-32B extras,** scored offline from `samples.jsonl`: unit tests passed, docstrings, answer length. Type hints are the organisms' trained habit and need not move in a natural model.

## How to read the outcomes

| If | Then |
| --- | --- |
| Q1: no large gap on Hua prompts | Our setup does not reproduce the organism (FP8 or merge): fix it before reading anything else |
| Q2: organism gap ≈ 0 on our framings | The organism, like its 4B copy, reacts to Hua's wording, not to evaluation in general. That is a direct critique of the evidence for Montoya et al.'s headline claim |
| Q2: gap present on our framings | The organism generalizes, so it is a real test bed |
| Q3: silent gap ≈ 0 | The behavior runs through the words, as in the 4B copy: nothing hidden to detect (Arm A gets no test bed here) |
| Q3: silent gap > 0, also after the Haiku pass | First evidence of eval-conditional behavior without stated awareness. This becomes the model for Arm A (probes, then training pressure) |
| Q4: base gap ≈ 0 | All of the gap is Hua's training |
| Q5: Qwen3-32B shows no gap in any behavior | In this setting a natural 32B model does not act differently when tested |
| Q5: some gap | Split it by stated awareness, as in Q3 |

## Runs

| Script | Machine | Started | Estimate |
| --- | --- | --- | --- |
| `experiments/pilot/run_nemotron.sh`, then `run_nemotron_base.sh` | p5.4xlarge spot, us-east-2, i-05721e6e | 2026-10-18 00:35 UTC | about 6 h, about $22 |
| `experiments/pilot/run_qwen32b.sh` | p5.4xlarge spot, us-east-2, i-0e68f398 | 2026-10-18 00:35 UTC | about 2.5 h, about $8 |

## Caveats

- **FP8, not bf16:** 49B in bf16 needs two 80 GB GPUs. Q1 is the guard. Montoya et al. ran bf16 on two 48 GB GPUs.
- **Exam size:** 2 answers per prompt for Nemotron; intervals will be wider than the pilot's 4.
- **Silent means regex-silent until the Haiku pass.** On the 4B organism, about half the regex-silent gap was paraphrase that Haiku catches.
- **Hua's prompts name "Llama Nemotron":** natural for Nemotron, so Qwen3-32B is run on our framings only.
- **Not Montoya's method:** this is not their resampling (Thought Branches). Natural silent traces and resampled ones are different measurements.

## Reproduce

```bash
experiments/pilot/run_nemotron.sh && experiments/pilot/run_nemotron_base.sh   # on a 1×H100 machine, .env with HF access
experiments/pilot/run_qwen32b.sh
uv run python experiments/pilot/08_compare_exams.py --config configs/pilot/08_compare_exams.toml
```
