# Open thinking models on one H100: what to run, at what precision

This page answers one question for a new model: which precision to use, and what will break, before paying for GPU time. Sources: web research done on 2026-10-26 (full notes with links are in `docs/design/models/`), plus this project's own runs.

**Measured H100 numbers** go in the "Measured" section at the bottom. They come from `configs/22_bench_models.toml`.

## The two jobs, and the memory each needs

Each model is used in two ways:
- **Sampling** with vLLM. It needs the weights plus KV-cache room for many long traces at once.
- **Probe reads** with HF transformers. A forward pass with `output_hidden_states` needs the bf16 weights plus about 10 GB of headroom for activations. One 8k-token trace on a 5120-wide, 64-layer model already holds about 5.4 GB of hidden states.

## Precision decision rule for one H100 (80 GB)

1. **Never use fp32.** It doubles memory, gives up the tensor cores (67 vs ~989 dense bf16 TFLOPS), and adds no information: checkpoints are released in bf16.
2. **For probe reads, use bf16 if the weights are ≤ ~70 GB.** That covers every dense model up to ~34B and every MoE model up to ~35B total. Above that, quantized weights are the only option for HF. A probe on quantized weights is not a bf16 probe, so say so in the write-up.
3. **For sampling, use bf16 only when it leaves ≥ ~25 GB for KV.** In practice that means weights ≤ ~45 GB. Otherwise use FP8.
   - Prefer an official FP8 checkpoint. Failing that, vLLM's dynamic `quantization = "fp8"`.
   - FP8 E4M3 is native on Hopper and close to lossless (Kurtic et al., arXiv 2411.02355).
   - We already sample Qwen3-32B in FP8 and probe it in bf16.
4. **Use int4 (AWQ/GPTQ, W4A16) only when FP8 doesn't fit,** e.g. a 70B dense model. Small reasoning models lose accuracy on hard tasks at int4 (arXiv 2504.04823).
5. **Size the KV before launching.** Trace length differs a lot between models (Magistral writes ~6× more than Qwen3 on our prompts).
   - Per-token KV = 2 × attention layers × KV heads × head dim × 2 bytes.
   - Concurrent sequences ≈ free KV GB ÷ (per-token KV × trace length).
   - Below ~100 concurrent sequences, throughput collapses. Switch to FP8 weights or lower `n`; see the Magistral row.

## Which parser each model needs

A plain split at `</think>` (what `evalgaming.sampling.split_reasoning` does) works for:
- Qwen3 / 3.5 / 3.6 / 3.8
- QwQ
- DeepSeek R1 distills
- OLMo-3 Think
- Magistral **2506**
- Phi-4-reasoning
- Nemotron (all)
- GLM-4.7-Flash
- Granite 4.2

For some of these the template itself opens `<think>`, so the completion holds only `</think>`.

These models need their own parser:

| Model | Reasoning delimiters |
|---|---|
| gpt-oss | harmony channels (`<\|channel\|>analysis … <\|channel\|>final`); decode with `skip_special_tokens=False` |
| Gemma 4 | `<\|channel>thought … <channel\|>` |
| Magistral 2507/2509, Ministral-3 Reasoning | `[THINK] … [/THINK]` special tokens |
| EXAONE Deep | `<thought>` |
| Seed-OSS | `<seed:think>` |
| Apriel | `[BEGIN FINAL RESPONSE]` |

## Templates that change the system prompt

Most templates leave the scenario system prompt alone. These do not:

- **Magistral (Unsloth copies):** drops its reasoning instruction when you pass a system prompt. Restore it with `system_prefix` (configs 20/21).
- **Phi-4-reasoning:** replaces any system prompt with its own. Put the scenario's system text in the user turn instead.
- **Qwen3.8:** adds a "Reasoning effort is set to xhigh…" sentence unless `reasoning_effort="medium"`.
- **DeepSeek R1 distills:** the card says use no system prompt.
- **Llama-3.1-Nemotron-Nano 8B/4B:** the system prompt must be exactly `detailed thinking on`.
- **Nemotron v2 9B/12B:** reasoning is switched with `/think` or `/no_think`.
- **gpt-oss:** reasoning effort goes in the system message.

## Candidate models that fit one H100

Sizes are weight GB. "Probe" is bf16 HF unless noted. The detail and source links for each row are in `docs/design/models/`.

| Model | Family | Params (active) | bf16 | FP8 | Sample with | Probe with | Think format | Notes |
|---|---|---|---|---|---|---|---|---|
| Qwen3-32B | Qwen | 32.8B | 65.5 | 34.3 | FP8 | bf16 | `<think>`, model opens | **current main model**; ~700-token traces on our prompts |
| Qwen3.6-27B / 3.8-27B | Qwen | 27.8B (+vision) | 55.6 | 30.9 | bf16 or FP8 | bf16 | template opens | hybrid DeltaNet. HF needs `fla` + `causal-conv1d` (missing here) and padding to multiples of 256. Temp 1.0 |
| Qwen3-30B-A3B (Thinking-2507) | Qwen | 30.5B (3.3B) | 61.1 | 32.4 | FP8 | bf16 | template opens (2507) | MoE; slow HF forward |
| QwQ-32B / R1-Distill-Qwen-32B | Qwen base | 32.8B | 65.5 | 34.3 | FP8 | bf16 | template opens | QwQ averages ~10k-token traces |
| Magistral-Small-2506 | Mistral | 23.6B | 47.1 | 24.9 | FP8 | bf16 | `<think>` text | Unsloth repo for the tokenizer; ~4.5k-token traces on our prompts |
| Magistral-Small-2509 | Mistral | 24B (+vision) | 48.0 | 25.8 | FP8 | bf16 | `[THINK]` tokens | stronger (AIME25 77 vs 62) |
| Ministral-3-14B-Reasoning | Mistral | 13.5B | 27.9 | — | bf16 | bf16 | `[THINK]` tokens | cheap second Mistral model |
| Nemotron-3-Nano-30B-A3B / 3.5-Lightning | NVIDIA | 31.6B (3.5B) | 63.2 | 32.7 | bf16 | bf16 (tight) | template opens | hybrid Mamba-2 + MoE. **hidden_states come one per block**. Very verbose. HF needs transformers ≥5.3 + mamba kernels |
| Llama-3.1-Nemotron-Nano-8B | NVIDIA / Llama | 8B | 16.1 | — | bf16 | bf16 | model opens | the easiest Llama-family thinker |
| Llama-3.3-Nemotron-Super-49B v1.5 | NVIDIA / Llama | 49.9B | 99.7 | 52.0 | FP8 (tight) | **quantized only** | `/no_think` off | nearest to "Llama-3.3-70B with reasoning". Remote code pinned to transformers 4.48 |
| DeepSeek-R1-Distill-Llama-8B | DeepSeek / Llama | 8B | 16.1 | 9.1 | bf16 | bf16 | template opens | no system prompt |
| gpt-oss-20b | OpenAI | 21B (3.6B) | ~42 | MXFP4 ~13 | MXFP4 | bf16 copy (`unsloth/gpt-oss-20b-BF16`) | harmony | CoT not optimized against, so it suits monitoring work |
| gpt-oss-120b | OpenAI | 117B (5.1B) | 234 | MXFP4 ~63 | MXFP4 | MXFP4 only | harmony | 8,973 tok/s per H100 (InferenceX) |
| Gemma 4 26B-A4B / 31B | Google | 25B (3.8B) / 31B | 51 / 62 | 26 / 31 | bf16 / FP8 | bf16 | channel | may be gated on Hugging Face (needs a token) |
| OLMo-3.1-32B-Think / 3-7B-Think | AI2 | 32B / 7.3B | 64.4 / 14.6 | dynamic | FP8 / bf16 | bf16 | template opens | **open data and SFT/DPO/RL checkpoints**, so probes can be compared across training stages |
| Phi-4-reasoning-plus | Microsoft | 14.7B | 29.4 | — | bf16 | bf16 | model opens | drops the system prompt |
| GLM-4.7-Flash | Z.ai | 31B (3B) | 62 | ~31 | FP8 | bf16 | template opens | MLA; up to 131k-token generations |
| Granite 4.2 30B | IBM | ~30B | ~58 | ~29 | FP8 | bf16 | template opens | vLLM parser comes as a plugin |
| Seed-OSS-36B / Hermes-4.3-36B | ByteDance / Nous | 36B | 72.3 | ~36 | FP8 | FP8 or 8-bit only | `<seed:think>` / `<think>` | Hermes complies more readily, which makes it a useful contrast |

**Too big for one H100 at any useful precision:** R1-Distill-Llama-70B (int4 only, sampling only), Qwen3-Next-80B, Qwen 3.8-Flash-Next, DeepSeek V4, Mistral Small 4 / Medium 3.5, Nemotron Super-120B / Ultra, GLM-4.5-Air+, MiniMax, Kimi, Llama 4.

**No official Llama thinking model exists.** Use Nemotron-Nano-8B or R1-Distill-Llama-8B. Use Super-49B only if a quantized probe is acceptable.

## Lessons from this project's runs

- **Hybrid linear-attention or Mamba models need a lower concurrency limit.**
  - Applies to Qwen3.5/3.6/3.8, Nemotron-H and Nemotron-3, and Granite hybrids.
  - Each decoding sequence needs one Mamba-cache block, and vLLM's default `max_num_seqs` (1,024) can exceed what fits. Qwen3.6-27B in bf16 had 358 blocks and failed at engine start.
  - Set `max_num_seqs = 256`, or at most the block count the error reports.

- **Qwen3-32B.**
  - Sampling: FP8 vLLM, 3,664 traces of ~700 tokens in about 20 minutes.
  - Probe read: bf16 HF, about 24 minutes including the download.
  - Steering in HF generate: FP8 runs at about 120–135 generations per hour. bf16 ran out of memory at batch 16.
- **Magistral-Small-2506.** Traces average ~4,500 tokens.
  - In bf16 vLLM the KV cache held only about 35 sequences at once, at 1,430 tok/s. The 458-pair v2 set at n = 4 would have taken about 3 hours.
  - Dynamic FP8 reached 2,400 tok/s.
  - The tokenizer prints a regex warning, but tokenization is unchanged on our data.

## Measured on H100 (configs/22_bench_models.toml)

Each model samples 40 v2 pairs × n = 2 in vLLM, then runs one HF forward pass with hidden states on its longest trace.

*Results go here when the benchmark lands.*
