# Open-weight reasoning models from Mistral, NVIDIA and Llama on one H100 80GB (status 2026-10-26)

**How this was checked.** Architecture numbers (layers, hidden size, experts, hybrid pattern), file sizes, tokenizer and template files, and remote-code files were read from the Hugging Face API (`/api/models/<repo>?blobs=true`, plus `config.json`) on 2026-10-26. Thinking formats were read from each repo's chat template or `SYSTEM_PROMPT.txt`. Sampling settings and engine notes come from the model cards. Throughput figures come from third-party pages, and each one is cited.

- **(U)** marks an item that is unverified or inferred.
- **"bf16 GB"** is the size of one copy of the weights. Official Mistral repos ship both `consolidated.safetensors` and HF shards, so a full repo download is twice that size. Download only one format (`--load_format mistral` uses consolidated; transformers uses the shards).
- **KV/token** is the bf16 KV cache per token: 2 × attention layers × KV heads × head_dim × 2 bytes. The Mamba state is a fixed cost per sequence, in fp32.
- **Fit criterion:**
  - vLLM: weights plus at least ~20 GB of KV cache at `gpu_memory_utilization` 0.92.
  - HF-bf16: bf16 weights at or under ~70 GB, leaving at least 10 GB for activations.

## Summary table

| Model (release) | Params (total/active) | Arch | Think format | bf16 GB | FP8 GB | int4 GB | Fits H100: vLLM / HF-bf16 | vLLM / HF notes | H100 tok/s (cited) | Typical think length |
|---|---|---|---|---|---|---|---|---|---|---|
| **Magistral-Small-2506** (Jun 2025) | 23.6B dense | Mistral, 40L, h5120, 128k (rec. 40k), KV 160 KB/tok | plain-text `<think>…</think>` requested by system prompt; model opens `<think>` | 47.1 | 24.9 (RedHatAI) / vLLM dynamic | 15.0 (unsloth bnb) | Yes (FP8 better) / **Yes** | Official repo: tekken.json only, so use `--tokenizer_mode mistral`. HF tokenizer: `unsloth/Magistral-Small-2506`. | none public | ~4.5k tok on this project's scenarios (~6× Qwen3; project config 20) |
| **Magistral-Small-2507** (Jul 2025) | 23.6B dense | same | `[THINK]…[/THINK]` **special tokens**; reasoning prompt in system prompt | 47.1 | vLLM dynamic; no official | ~15 (unsloth bnb) | Yes / **Yes** | Same as 2506. Unsloth tokenizer has `[THINK]` tokens. | none | (U) similar; card: fewer loops |
| **Magistral-Small-2509** (v1.2, Sep 2025) | 24B (LM ~23.6B + vision encoder) | Mistral3 (VLM), 40L, h5120, 128k, KV 160 KB/tok | `[THINK]…[/THINK]` special tokens; system prompt contains the template | 48.0 | 25.8 (unsloth FP8-Dynamic) | 15.0 (unsloth bnb-4bit) | Yes / **Yes** | `Mistral3ForConditionalGeneration`. HF needs `transformers[mistral-common]` (≥1.8.5, `tokenizer_type="mistral"`) or the unsloth tokenizer.json. | none | (U) shorter on easy prompts (card) |
| **Ministral-3-14B-Reasoning-2512** (Dec 2025) | 13.5B LM + 0.4B vision | Mistral3/ministral3, 40L, h5120, 256k, KV 160 KB/tok | `[THINK]` special tokens; SYSTEM_PROMPT.txt | 27.9 | none official (Instruct variants are FP8) | ~10 (U); cyankiwi AWQ, unsloth bnb | **Yes / Yes** | Ships tokenizer.json and chat_template. vLLM `--reasoning-parser mistral`. | none | (U) |
| Ministral-3-8B / 3B-Reasoning-2512 | 8B / 3B (+vision) | 34L h4096 / 26L h3072 | same | ~17.9 / ~7.7 | none | – | Yes / Yes | same | none | (U) |
| Mistral-Small-4-119B-2603 (Mar 2026) | 119B / 6.5B | MoE (128 exp, top-4) + MLA, 36L, h4096, 256k | `reasoning_effort` "none"/"high"; `[THINK]` tokens | ~238 (U) | 120.9 (official) | 70.8 (official NVFP4) | **No / No** | NVFP4 on Hopper falls back to W4A16 with ~5 GB left for KV. | – | – |
| Mistral-Medium-3.5-128B (Mar 2026) | 128B dense | 88L, h12288 | `reasoning_effort` | ~267 | 133.6 | – | No / No | Modified MIT license | – | – |
| Magistral Medium 1.x | – | – | – | **not open** (API only) (U: no HF repo exists) | | | | | | |
| **Llama-3.1-Nemotron-Nano-8B-v1** (Mar 2025) | 8B dense | Llama-3.1, 32L, h4096, 128k, KV 128 KB/tok | system prompt `detailed thinking on/off`; model opens `<think>` itself (no prefill) | 16.1 | none official | community AWQ | **Yes / Yes** | Native Llama in both engines | ~7.7k tok/s @ high concurrency for Llama-3.1-8B (proxy, E2E, 512/128) | eval cap 32k (U typical) |
| Llama-3.1-Nemotron-Nano-4B-v1.1 (May 2025) | ~4.5B dense | Llama (Minitron), 32L, h3072, KV 128 KB/tok | same | 9.0 | – | – | Yes / Yes | vLLM ≥0.6.6 | – | (U) |
| **NVIDIA-Nemotron-Nano-9B-v2** (Aug 2025) | 8.9B dense | **hybrid Mamba-2**: 56 blocks (27 Mamba, 4 attn, 25 MLP), h4480, 128k; KV 16 KB/tok + ~142 MB/seq SSM | `/think` (default) or `/no_think` in system or user turn; template **prefills `<think>\n`**; thinking-budget client | 17.8 | 10.3 (official) | 6.5 (RedHatAI w4a16); official NVFP4 | **Yes / Yes** (flag) | vLLM ≥0.10.1 `--mamba_ssm_cache_dtype float32`. HF: `trust_remote_code` (tested 4.48.3), needs `mamba-ssm` + `causal-conv1d` for the fast path. | "3–6× Qwen3-8B" at 8k in / 16k out (NVIDIA; hardware U) | (U) |
| NVIDIA-Nemotron-Nano-12B-v2 (Aug 2025) | 12.3B dense | hybrid: 62 blocks (28 Mamba, 6 attn), h5120; KV 24 KB/tok | same | 24.6 | (U) | – | Yes / Yes (flag) | same | – | (U) |
| **Llama-3.3-Nemotron-Super-49B-v1 / v1.5** (Mar / Jul 2025) | 49.9B dense (NAS) | DeciLM: 80 blocks, 49 with attention (8 KV heads), h8192, 128k; KV ~196 KB/tok | v1: `detailed thinking on/off`. v1.5: reasoning ON by default, `/no_think` in system turns it off (template inserts empty `<think>\n\n</think>`). | 99.7 | 52.0 (official ModelOpt FP8, v1.5) | 31.1 (official NVFP4); 29.0 (cyankiwi AWQ) | FP8: **tight** (~16 GB KV) / **No** | vLLM in-tree DeciLM. HF: `trust_remote_code`, pinned transformers 4.48.3 (U: breaks on 5.x?). For HF probes: bnb-8bit (~50 GB) or AWQ only. | none public for H100 | eval at 64k cap (U) |
| **OpenReasoning-Nemotron-7B/14B/32B** (Jul 2025) | 7.6 / 14.8 / 32.8B dense | **Qwen2.5** (not Llama): 28L h3584 / 48L h5120 / 64L h5120; KV 56 / 192 / 256 KB/tok | reasoning-only (no off switch); plain Qwen template, model emits `<think>` (U) | 15.2 / 29.5 / 65.5 | vLLM dynamic | 32B: 19.2 (community W4A16) | 7B/14B: Yes / Yes. 32B: FP8 yes / **barely** (65.5 GB + ~12 GB) | Native Qwen2. CC-BY-4.0. Math, code and science only. | – | evaluated with up to 64k output |
| **NVIDIA-Nemotron-3-Nano-30B-A3B** (Dec 15 2025) | 31.6B / 3.5B | **hybrid Mamba-2 + MoE**: 52 blocks (23 Mamba, 23 MoE with 128+1 experts top-6, 6 attn with 2 KV heads), h2688, 256k default (1M max); KV 6 KB/tok + 48 MB/seq | `enable_thinking` (default True) prefills `<think>\n`; off gives `<think></think>`; `reasoning_budget` client | 63.2 | 32.7 (official) | 19.3 (official NVFP4); 17.8 (community AWQ) | **Yes / Yes (tight: ~14 GB left)** | vLLM ≥0.12 with `nano_v3` reasoning parser (file in repo). HF **native since transformers v5.3.0** (card); repo also has remote code. | ~223 tok/s single request (Ori); NVFP4 Omni sibling 317 (C1) → 3,993 (C256) (Lambda) | **very verbose**: 120M tokens on the AA index vs 37M median |
| **NVIDIA-Nemotron-3-Nano-4B** (Mar 16 2026) | ~3.97B | hybrid: 42 blocks (21 Mamba, 4 attn), h3136, 256k; KV 16 KB/tok + 83 MB/seq | `enable_thinking`, prefills `<think>\n` | 7.9 | 5.3 (official) | GGUF | Yes / Yes | Compressed from Nano-9B-v2 (Elastic). vLLM ≥0.15.1. HF `trust_remote_code`. | – | (U) |
| **NVIDIA-Nemotron-3.5-Lightning-30B-A3B** (Aug 11 2026) | 30B / 3B (+MTP layers) | same shape as Nano-3: 52 blocks, 6 attn, 128 experts top-6, 1M ctx | `enable_thinking` prefill `<think>\n` | 65.8 | none official (U) | 21.6 (official NVFP4; W4A16 "humming" kernels on H100) | **Yes** (official 1×H100 bf16 recipe, 256k) / **Yes, tight** | vLLM 0.27.1 recipe: `--mamba-ssm-cache-dtype float16 --reasoning-parser nemotron_v3`. **No remote code** in repo, so it needs native NemotronH (transformers ≥5.3) (U). OpenMDW-1.1 license. | NVFP4 on H100, 8k in / 1k out: 326 (C1), 1,438 (C16), 2,635 (C64), 4,612 (C256) (Lambda) | (U) likely Nano-3-like |
| **Nemotron-Cascade-2-30B-A3B** (Mar 19 2026) | 30B / 3B | Nano-3 architecture (post-trained from Nano-3 Base) | `enable_thinking`; `<think>` prefill; instruct mode = `<think></think>` | 63.2 | – | – | Yes / Yes (tight) | vLLM `--reasoning-parser nano_v3` (changed Jul 2026). IMO/IOI gold. | – | (U) long (olympiad RL) |
| Nemotron-Cascade-8B / 14B-Thinking (Dec 2025) | 8.2 / 14.8B dense | **Qwen3** 36L h4096 / 40L h5120; KV 144 / 160 KB/tok | thinking-only; append `" /think"` to the user turn | 16.4 / 29.5 | – | – | Yes / Yes | Native Qwen3 | – | up to 64k evaluated |
| Nemotron-3-Super-120B-A12B (Mar 11 2026) | 120B / 12B | LatentMoE hybrid, 88 blocks, 512 experts top-22, MTP | `enable_thinking` | 247 | 128.4 | 80.3 (NVFP4) | **No / No** | card: minimum 8×H100 | – | – |
| Nemotron-3.5-Bolt-74B-A9B (Oct 15 2026) | 74B / 9B | omni (VLM) hybrid, compressed from Super-3.5-VL | `enable_thinking` | 149.8 | – | **24.1 ("24GB", native 2-bit)** | 24GB build: Yes / **No** (bf16) | Custom `NemotronH_Omni` remote code. A probe on 2-bit weights is not a bf16 probe. | – | – |
| Nemotron-3.5-Bolt-E4B (Oct 2026) | 8B (4B effective) | **Gemma-4-E4B** post-train | `enable_thinking`; gemma4 reasoning parser | 16.0 | – | 4GB build | Yes / Yes | Gemma4 arch, not NemotronH | – | (U) |
| Nemotron-Labs-Dory1.0-4B (Oct 16 2026) | 4B | looped latent-recurrent nGPT (72 unrolled layers) | always-on reasoning (vLLM) | 8.0 | MXFP8 | NVFP4 | (U) / (U) | New `dory` arch with no remote code; needs very recent engines (U). Hidden-state semantics differ (looped). | – | (U) |
| Llama-4-Scout-17B-16E / Maverick (Apr 2025) | 109B / 17B; 400B / 17B | MoE, 48L, h5120 | **no thinking mode** (not a reasoning model) | 217 | 114.6 | 64.9 (RedHatAI w4a16) | w4a16 only, ~8 GB KV / No | – | – | – |
| **DeepSeek-R1-Distill-Llama-8B** (Jan 2025) | 8B dense | Llama-3.1, 32L, h4096, KV 128 KB/tok | template prefills `<think>\n` after `<｜Assistant｜>` | 16.1 | 9.1 (RedHatAI FP8-dyn) | – | **Yes / Yes** | native; MIT + Llama license | proxy as Nano-8B | (U) long; R1-style |
| DeepSeek-R1-Distill-Llama-70B | 70.6B dense | 80L, h8192, KV 320 KB/tok | same | 141 | 72.7 | 39.5 (RedHatAI w4a16) | w4a16 only (~30 GB KV) / **No** | HF only with quantized weights | – | (U) |
| Cogito v1-preview Llama-8B/70B; v2-preview Llama-70B / 109B-MoE (Apr / Jul 2025) | 8 / 70 / 109B | Llama-3.1 / Llama-4-Scout | hybrid: `enable_thinking=True`, or system prompt "Enable deep thinking subroutine." plus prefill `<think>\n` | 16.1 / 141 / 217 | – | – | 8B: Yes / Yes; others No | native Llama / Llama4 | – | (U) shorter than R1 (Cogito claim, U) |

## Per-model notes

### Mistral

- **Magistral Small 2506 (v1.0)** [card](https://huggingface.co/mistralai/Magistral-Small-2506), [SYSTEM_PROMPT.txt](https://huggingface.co/mistralai/Magistral-Small-2506/raw/main/SYSTEM_PROMPT.txt)
  - **Think format.** Reasoning comes from a system prompt that asks for `<think>\n…\n</think>`. These are plain-text tags, not special tokens. The prompt ends in `[/INST]`, so the model opens `<think>` itself.
  - **Sampling.** temp 0.7, top_p 0.95, max_tokens 40,960. Context is 128k, but the card recommends 40k.
  - **vLLM.** The card's example uses `--tokenizer_mode mistral --config_format mistral --load_format mistral` with TP=2. One H100 is enough with bf16 or FP8 weights.
  - **Tokenizer.** The official repo ships only `tekken.json`. [unsloth/Magistral-Small-2506](https://huggingface.co/unsloth/Magistral-Small-2506) has `tokenizer.json` and `chat_template.jinja`.
  - **Project findings (configs 20/21).** The unsloth template drops the reasoning prompt when the user supplies a system prompt, which is why config 20 has a `system_prefix`. transformers warns about the tokenizer regex, but tokenization is identical with and without the fix.
  - **Memory.** bf16 vLLM left room for only about 35 concurrent traces of ~4.5k tokens. This matches 160 KB/token against ~22 GB of free KV.
- **Magistral Small 2507 (v1.1)** [card](https://huggingface.co/mistralai/Magistral-Small-2507)
  - This version switches to `[THINK]`/`[/THINK]` **special tokens**, and the reasoning prompt moves into the system prompt. The card says the tokens "must be encoded as such", with mistral-common as the source of truth.
  - The unsloth tokenizer has `[THINK]` and `[/THINK]` as added tokens; the 2506 unsloth tokenizer has neither.
  - Same sampling as 2506, and fewer infinite loops.
- **Magistral Small 2509 (v1.2)** [card](https://huggingface.co/mistralai/Magistral-Small-2509)
  - **Architecture.** Built on Mistral Small 3.2 and adds a vision encoder, so the class is `Mistral3ForConditionalGeneration`.
  - **Think format and sampling.** `[THINK]` special tokens. temp 0.7, top_p 0.95, max_tokens 131,072. The card says performance "might degrade past 40k".
  - **Benchmarks.** Much stronger than v1.1: AIME25 77.3 vs 62.0.
  - **HF tokenizer.** The official path is `AutoTokenizer.from_pretrained(..., tokenizer_type="mistral")` with `transformers[mistral-common]` and mistral_common ≥1.8.5. Community tokenizers: [unsloth/Magistral-Small-2509](https://huggingface.co/unsloth/Magistral-Small-2509) (`LlamaTokenizerFast`, with `[THINK]` and `[/THINK]` added), plus [FP8-Dynamic](https://huggingface.co/unsloth/Magistral-Small-2509-FP8-Dynamic) at 25.8 GB and [bnb-4bit](https://huggingface.co/unsloth/Magistral-Small-2509-unsloth-bnb-4bit) at 15.0 GB. A text-only FP8 build also exists: [ConicCat/Magistral-Small-2509-Text-Only-FP8-Dynamic](https://huggingface.co/ConicCat/Magistral-Small-2509-Text-Only-FP8-Dynamic).
  - **Probes.** The decoder's hidden states come from the full VLM's `output_hidden_states` on text-only input. (U) Check that the layer count is 40+1.
  - **vLLM.** (U) Set `limit_mm_per_prompt={"image":0}` to skip vision memory.
- **Ministral 3 Reasoning 2512 (3B/8B/14B)** [14B card](https://huggingface.co/mistralai/Ministral-3-14B-Reasoning-2512), [paper](https://arxiv.org/abs/2601.08584)
  - **Weights and license.** Apache-2.0, BF16 weights, 256k context.
  - **Think format.** `[THINK]` special tokens. The card says to keep traces in multi-turn context.
  - **Sampling.** temp **1.0**; the card's snippets use top_p 0.95.
  - **Tokenizer and vLLM.** The official repo already ships `tokenizer.json` and `chat_template.jinja`. vLLM: `--reasoning-parser mistral`. The card suggests 2×H200 only for the full 256k context; one GPU is fine otherwise.
  - **Why it matters here.** A smaller Mistral reasoning model (14B at 27.9 GB bf16) that fits comfortably for HF probes.
- **Mistral Small 4 (119B-A6.5B)** [card](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603) and **Mistral Medium 3.5 (128B dense)** [card](https://huggingface.co/mistralai/Mistral-Medium-3.5-128B)
  - Both merge Magistral-style reasoning behind a `reasoning_effort` "none"/"high" switch.
  - Neither fits one H100 for bf16 probing. Small 4 comes as FP8 (121 GB) or NVFP4 (71 GB).
  - Magistral Medium weights were never released (U: no `mistralai` HF repo exists).

### NVIDIA

- **Llama-3.1-Nemotron-Nano-8B-v1** [card](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-8B-v1) and **4B-v1.1** [card](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1)
  - **Think format.** Set by the system prompt, which must be exactly `detailed thinking on` or `detailed thinking off`; all other instructions go in the user turn. The template adds no `<think>`; the model writes `<think>…</think>` and may emit an empty `<think></think>`. Reasoning-off can be forced by prefilling `<think>\n</think>`.
  - **Sampling.** temp 0.6, top_p 0.95 for reasoning on; greedy for off. max_new 32,768.
  - **License.** NVIDIA Open Model License plus the Llama 3.1 license.
  - **Engines.** Plain Llama, so no engine problems. The easiest Llama-family reasoning probe target.
- **Nemotron-Nano-9B-v2 / 12B-v2** [9B card](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2), [Nemotron-H report](https://arxiv.org/abs/2504.03624)
  - **Architecture.** Hybrid Mamba-2/MLP with 4 attention layers (9B) or 6 (12B).
  - **Think format.** `/think` or `/no_think` in the system or user turn. The template prefills `<think>\n`, or emits `<think></think>` when thinking is off. A thinking-budget client is described on the card.
  - **Sampling.** temp 0.6, top_p 0.95.
  - **vLLM.** `vllm serve … --trust-remote-code --mamba_ssm_cache_dtype float32` (docker v0.10.1).
  - **HF:**
    - `trust_remote_code=True`, tested on transformers 4.48.3. Install `mamba-ssm` and `causal-conv1d`, or the remote code falls back to a slow, memory-heavy torch scan (U for the exact behavior).
    - **Hidden-state gotcha:** `hidden_states` has one entry per block (Mamba, MLP or attention block, 56 for 9B), not per "transformer layer". Choose probe layers by block type.
    - Native `NemotronH` in transformers main returns per-layer `hidden_states` ([docs](https://huggingface.co/docs/transformers/main/en/model_doc/nemotron_h)). (U) Whether the v2 `hybrid_override_pattern` configs load natively without remote code.
  - **Official quantized builds.** [FP8](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2-FP8) at 10.3 GB and NVFP4.
  - **Throughput claim.** "3–6× Qwen3-8B" at 8k in / 16k out ([NeMo docs](https://docs.nvidia.com/nemo-framework/user-guide/25.09/llms/mamba.html)); the hardware is U.
- **Llama-3.3-Nemotron-Super-49B v1 / v1.5** [v1](https://huggingface.co/nvidia/Llama-3_3-Nemotron-Super-49B-v1), [v1.5](https://huggingface.co/nvidia/Llama-3_3-Nemotron-Super-49B-v1_5), [FP8](https://huggingface.co/nvidia/Llama-3_3-Nemotron-Super-49B-v1_5-FP8), [NVFP4](https://huggingface.co/nvidia/Llama-3_3-Nemotron-Super-49B-v1_5-NVFP4)
  - **Architecture.** A NAS-pruned derivative of Llama-3.3-70B. Some blocks skip attention or the FFN; 49 of 80 blocks have attention.
  - **Think format:**
    - v1: `detailed thinking on/off` in the system prompt.
    - v1.5: reasoning ON with an empty system prompt; `/no_think` turns it off.
  - **Sampling.** temp 0.6, top_p 0.95.
  - **Fit.** bf16 is 99.7 GB and does not fit. The card's single-GPU claim is for **H200**, and v1.5 was tested on 2×H100.
  - **H100 options:**
    - vLLM: the official ModelOpt FP8 (52 GB) leaves ~16 GB of KV, about 80k tokens. Workable for short traces.
    - HF probe: quantized weights only (AWQ 29 GB, or bnb-8bit). Remote DeciLM code is pinned to transformers 4.48.3 (U: compatibility with transformers 5.x).
  - **Why it matters here.** It is the nearest "Llama-3.3-70B with reasoning" for this project's planned Llama-3.3-70B cross-model run.
- **OpenReasoning-Nemotron 1.5/7/14/32B** [32B card](https://huggingface.co/nvidia/OpenReasoning-Nemotron-32B)
  - **Base model.** **Qwen2.5**, not Llama, distilled from DeepSeek-R1-0528. CC-BY-4.0.
  - **Coverage.** Math, code and science only, with no general chat or safety post-training (U). Probably a poor fit for user-harm scenarios.
  - **Card settings.** max_new 64k. The card's snippet lists no temperature (U: R1-style 0.6/0.95). Supports GenSelect "heavy" mode.
- **Nemotron 3 Nano 30B-A3B** [BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16), [FP8](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8), [NVFP4](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-NVFP4), [paper](https://arxiv.org/abs/2512.20848), [vLLM blog](https://vllm.ai/blog/2025-12-15-run-nvidia-nemotron-3-nano), [vLLM recipe](https://recipes.vllm.ai/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16)
  - **Think format.** `enable_thinking`, default True, prefills `<think>\n`. A `truncate_history_thinking` template option exists.
  - **Sampling.** temp **1.0**, top_p **1.0** for reasoning; 0.6/0.95 for tool calls.
  - **vLLM.** vLLM ≥0.12 with the repo's `nano_v3_reasoning_parser.py`.
  - **HF:**
    - **Native since transformers v5.3.0** (card).
    - bf16 is 63.2 GB, leaving ~14 GB, which covers the 10 GB headroom.
    - HF MoE eager forward is slow (U). KV is tiny (6 KB/token), so long traces cost little memory.
    - Same hidden-state caveat: 52 entries, one per Mamba, MoE or attention block.
  - **Verbosity.** Very verbose: 120M tokens on the AA index vs a 37M median ([Artificial Analysis](https://artificialanalysis.ai/models/nvidia-nemotron-3-nano-30b-a3b-reasoning)).
  - **H100 throughput.** About 223 tok/s for a single request ([Ori](https://www.ori.co/blog/getting-started-with-nemotron-3-nano-on-cloud-gpu); precision U). For the Omni-Reasoning NVFP4 sibling on H100 (via fallback), 317 → 3,993 tok/s from C1 to C256 ([Lambda](https://lambda.ai/inference-models/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning-nvfp4)). Both figures came via search summaries and were not re-fetched.
  - **License.** NVIDIA Nemotron Open Model License.
- **Nemotron 3 Nano 4B** [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16), [FP8](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8)
  - Released 3/16/2026, compressed from Nano-9B-v2 with the Elastic framework.
  - Uses the Nemotron-3 template (`enable_thinking`). temp 1.0, top_p 0.95.
  - vLLM ≥0.15.1 with `--mamba_ssm_cache_dtype float32`.
- **Nemotron 3.5 Lightning 30B-A3B** [BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16), [NVFP4](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4)
  - **Release and license.** Released 2026-08-11 under OpenMDW-1.1. The newest strong NVIDIA reasoning model that fits one H100 in bf16.
  - **Official 1×H100 bf16 recipe:** 256k context, vLLM `v0.27.1`, `--mamba-backend flashinfer --mamba-ssm-cache-dtype float16 --enable-mamba-cache-stochastic-rounding --reasoning-parser nemotron_v3`.
  - **Sampling.** temp 1.0, top_p 0.95.
  - **NVFP4 on H100.** Runs W4A16 ("humming" kernels), since Hopper has no FP4 cores. [Lambda H100 numbers](https://lambda.ai/inference-models/nvidia/nvidia-nemotron-3.5-lightning-30b-a3b-nvfp4) (fetched): 326 / 1,438 / 2,635 / 4,612 tok/s at C1 / 16 / 64 / 256, with 8k in and 1k out.
  - **HF.** The repo has **no `.py` files**, so it needs native `NemotronH` (transformers ≥5.3; U, not tested). It uses `layers_block_type` instead of `hybrid_override_pattern`.
- **Nemotron-Cascade-2-30B-A3B** [card](https://huggingface.co/nvidia/Nemotron-Cascade-2-30B-A3B)
  - Released 2026-03-19. Post-trained from the Nano-3 Base with cascaded RL.
  - Thinking and instruct modes via `enable_thinking`. temp 1.0, top_p 0.95.
  - Use `--reasoning-parser nano_v3`, not `nemotron_v3` (changed 2026-07-09).
- **Nemotron-Cascade-8B/14B-Thinking** [14B card](https://huggingface.co/nvidia/Nemotron-Cascade-14B-Thinking)
  - Qwen3 architecture. Thinking-only, triggered by appending `" /think"` to the user turn.
  - temp 0.6, top_p 0.95, 64k generation.
- **Too big for one H100** (listed for completeness): Nemotron-3-Super-120B-A12B ([card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16); NVFP4 80.3 GB; the card says a minimum of 8×H100 for BF16), Nemotron-3-Ultra-550B-A55B (Jun 2026), Nemotron-3.5-Super-VL-120B, Nemotron-Labs-3-Puzzle-75B-A9B (FP8 83 GB), and Llama-3.1-Nemotron-Ultra-253B.
- **Nemotron 3.5 Bolt 74B-A9B** [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-BF16) (2026-10-15)
  - A vision-language model compressed from Super-3.5-VL.
  - The "24GB" build uses native 2-bit weights. It fits vLLM, but it is not a bf16-probe target.
- **Bolt-E4B** [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-BF16) is a Gemma-4-E4B post-train.
- **Dory 1.0 4B** [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-Labs-Dory1.0-4B-BF16) (2026-10-16) is a looped latent-recurrent architecture with reasoning always on.
- **Experimental status.** Treat the last three as experimental for probes. Their architectures or quantization make layer-wise probing non-standard.

### Meta Llama

- **No official Llama thinking model exists.** The `meta-llama` HF org's newest repos are Llama 4 and Llama Guard 4, from April 2025.
- **Llama 4 Scout/Maverick** have no reasoning mode.
- **Meta's 2026 frontier model.** Reportedly closed and API-only ("Muse Spark"; U, via [this search result](https://ai.netzstrategen.com/en/glossary/llama-meta/)).
- **Llama-family reasoning models that fit:**
  - Llama-3.1-Nemotron-Nano-8B/4B and DeepSeek-R1-Distill-Llama-8B, both easy.
  - Cogito v1 Llama-8B, a hybrid model.
  - Super-49B, FP8 for sampling and quantized for probes.
  - R1-Distill-Llama-70B, as w4a16 for sampling only.
- **DeepSeek-R1-Distill-Llama-8B** [card](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-8B)
  - The current template prefills `<think>\n`.
  - DeepSeek recommends temp 0.6, top_p 0.95, and no system prompt (U: from the R1 card, not re-read here).
- **Cogito** [v2 109B card](https://huggingface.co/deepcogito/cogito-v2-preview-llama-109B-MoE)
  - Hybrid reasoning, switched on by `enable_thinking=True`, or by the system prompt "Enable deep thinking subroutine." plus a `<think>\n` prefill.

## Bottom line for this project

- **Mistral: Magistral-Small-2509 is the best pick.**
  - Probes: the unsloth bf16 copy with a transformers tokenizer.
  - Sampling: FP8-Dynamic.
  - It uses `[THINK]` special tokens, while 2506 uses text `<think>`. Parsers and probe token positions differ between the two.
  - Ministral-3-14B-Reasoning is a cheaper second Mistral model.
- **NVIDIA: Nemotron-3-Nano-30B-A3B or 3.5-Lightning are the strongest hybrid picks** that fit bf16 for HF forwards.
  - Hybrid Mamba means installing `mamba-ssm` and `causal-conv1d`, recent transformers (≥5.3), and a per-block hidden-state indexing scheme.
  - Llama-3.1-Nemotron-Nano-8B is the zero-friction dense option.
- **Llama: nothing official.** Use Nemotron-Nano-8B or R1-Distill-Llama-8B in bf16. Super-49B, a Llama-3.3-70B derivative, works on one H100 only with FP8 for sampling and quantized weights for probes.
- **Throughput.** No public H100 numbers exist for Magistral or Super-49B. Measure with `vllm bench serve` on the first run.
