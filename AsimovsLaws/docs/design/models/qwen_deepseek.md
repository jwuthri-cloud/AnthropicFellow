# Qwen and DeepSeek reasoning models on one H100 80 GB (as of 2026-10-26)

How the numbers were collected:
- Params, layers, hidden size, context length, license and file sizes come from the Hugging Face API (`/api/models/<id>?blobs=true`, summing the safetensors files) and each repo's `config.json`, fetched today.
- Chat-template behaviour comes from rendering or reading `tokenizer_config.json`. I did not run any model.
- "GB" means checkpoint file size. For the Qwen3.5/3.6/3.8 repos this includes the ~0.45B vision tower (27 layers × 1152, about 0.9 GB in bf16) and the MTP head. `--language-model-only` in vLLM, and `Qwen3_5ForCausalLM` in HF, drop the vision tower.
- Fit rules:
  - **vLLM fit** means the weights leave at least 25 GB for KV cache at `gpu_memory_utilization=0.9`.
  - **HF-bf16 fit** means the bf16 weights are at most 70 GB, which leaves at least 10 GB for activations.
  - "marginal" means the model loads but breaks one of these rules.
- The KV cost per token (bf16) is computed from the config as `2 × full-attn layers × kv_heads × head_dim × 2 B`.
- Anything I could not check against a primary source is marked **unverified**.

## New releases you may not know

- **Qwen 3.5 family (Feb–Mar 2026):** 0.8B / 2B / 4B / 9B / 27B dense, plus 35B-A3B, 122B-A10B and 397B-A17B MoE.
  - Natively multimodal, with a hybrid layer stack: 3 Gated DeltaNet layers to 1 gated full-attention layer.
  - Hybrid thinking (on by default). Apache-2.0.
- **Qwen3.6-27B / 35B-A3B (Apr 2026):** same architecture and `model_type` as 3.5.
- **Qwen3.8-27B (Aug 2026):** same architecture again (`qwen3_5_text`). Adds `reasoning_effort` and `preserve_thinking`.
- **Too large for one H100:**
  - Qwen3.8-Flash-Next: the "Qwen4 preview", `Qwen4ExpForConditionalGeneration`. 180B checkpoint (125B MoE with 6B active, plus 51B n-gram embedding and 4B MTP). FP8 is 185 GB. Licence is qwen-community-1.0.
  - Qwen3.8-2.4T-A95B.
- **Qwen4:** no Qwen4-named open weights yet (unverified secondary reports say Alibaba announced a Qwen 4 27B in Sept 2026).
- **DeepSeek:** no new small reasoning model since **R1-0528-Qwen3-8B (May 2025)**.
  - Its 2026 open releases are V4-Flash (291–304B, FP8, about 160–167 GB), V4-Pro and V4.1-Flash (763B). None fits one H100.
  - It also released Eagle3, DFlash and DSpark speculative-decoding drafts for Qwen3-4B/8B/14B. These are drafts, not reasoning models.
- Sources: [HF Qwen org listing](https://huggingface.co/api/models?author=Qwen&sort=createdAt&direction=-1), [HF deepseek-ai listing](https://huggingface.co/api/models?author=deepseek-ai&sort=createdAt&direction=-1), [Qwen3.8-Flash-Next card](https://huggingface.co/Qwen/Qwen3.8-Flash-Next), [Qwen4 status (secondary)](https://www.yottalabs.ai/post/qwen-4-27b-release-date-specs-hardware-what-is-known-2026).

## Table

Column notes:
- **Arch:** L = layers, d = hidden size, ctx = native context.
- **Think format** for `<think>`: "tmpl opens" means `add_generation_prompt` already appends `<think>\n`, so the model output contains only `</think>`. "model opens" means the model emits `<think>` itself.
- **KV/token** is the bf16 KV-cache cost per token.

| Model | Params (total / active) | Arch | Think format | bf16 GB | FP8 GB | int4 GB | Fits H100: vLLM / HF-bf16 | vLLM / HF notes | H100 tok/s (public) | Typical think length |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-8B | 8.19B dense | L36 d4096, 8 KV heads, ctx 32K (40,960 in config; 131K YaRN) | Hybrid. `enable_thinking` plus `/think` and `/no_think` soft switches. Model opens | 16.4 | 9.4 (official) | 6.1 AWQ (official) | yes / yes | vLLM ≥0.8.5, transformers ≥4.51. KV 147 KB/token | none found | budget 32,768. Project's 8B smoke run: not measured |
| Qwen3-14B | 14.8B dense | L40 d5120, 8 KV heads, ctx 32K | as 8B | 29.5 | 16.3 (official) | 10.0 AWQ (official) | yes / yes | KV 160 KB/token | none found | budget 32,768 |
| Qwen3-32B | 32.8B dense | L64 d5120, 8 KV heads, ctx 32K | as 8B | 65.5 | 34.3 (official) | 19.3 AWQ (official) | FP8 yes; bf16 marginal (only ~6 GB of KV) / yes (~12 GB headroom) | KV 262 KB/token. Project already samples with FP8 and probes in bf16 | ~2,353 total tok/s with vLLM, untuned, high concurrency (GPUStack via markaicode, **unverified**) | **Project measurement:** median 796 tokens (harm rows) and 390 (benign) on scenario prompts, temp 0.6 |
| Qwen3-30B-A3B (hybrid) | 30.5B / 3.3B MoE (128 experts, top-8) | L48 d2048, 4 KV heads, ctx 32K | as 8B | 61.1 | 32.4 (official) | 16.9 GPTQ-Int4 (official) | yes / yes (~17 GB headroom) | KV 98 KB/token. HF MoE forward is slower than dense of the same active size | none on H100 | budget 32,768 |
| Qwen3-30B-A3B-Thinking-2507 | as above | ctx 262K | Thinking only. Tmpl opens. No `enable_thinking` | 61.1 | 31.2 (official) | 16.8 AWQ (QuantTrio, community) | yes / yes | Card: `--reasoning-parser deepseek_r1` | none | Card: "increased thinking length"; budgets 32,768 (general) and 81,920 (hard) |
| Qwen3-4B-Thinking-2507 | 4.0B dense | L36 d2560, ctx 262K | Thinking only, tmpl opens | 8.0 | 5.2 (official) | community | yes / yes | | none | as above |
| Qwen3-Next-80B-A3B-Thinking | 81.3B / ~3B MoE (512 experts, top-10), hybrid DeltaNet | L48 d2048, ctx 262K | Thinking only, tmpl opens | 162.7 | 82.1 (official) | 49.2 AWQ (cyankiwi, community) | AWQ only / **no** | Needs `qwen3_next` support (transformers ≥4.57, vLLM ≥0.10.2: **unverified**) | none | as 2507 |
| QwQ-32B | 32.8B dense (Qwen2.5 base) | L64 d5120, 8 KV heads, ctx 32K (131K YaRN) | Thinking only, tmpl opens | 65.5 | 34.3 FP8-dynamic (RedHatAI) | 19.3 AWQ (official) | FP8 or AWQ yes / yes | Card: enable YaRN for prompts over 8K. vLLM YaRN is static and hurts short prompts. KV 262 KB/token | none | ~10.1K tokens on average; 13.6K on AIME24 ([arXiv 2503.19855, Table 2](https://arxiv.org/html/2503.19855)) |
| Qwen3.5-9B | 9.65B dense (with vision) | L32 d4096; full attention in 8 of 32 layers, 4 KV heads, head_dim 256; ctx 262K | Hybrid. `enable_thinking` (on by default). Tmpl opens | 19.3 | 14.0 FP8-dynamic (RedHatAI; no official FP8) | community only | yes / yes | KV 33 KB/token plus a fixed recurrent state per sequence. See the 3.5 notes | none | budgets 32,768 / 81,920 |
| Qwen3.5-27B | 27.8B dense (with vision) | L64 d5120; full attention in 16 of 64 layers (4 KV heads, head_dim 256), 48 DeltaNet; ctx 262K | as 3.5-9B | 55.6 | 30.9 (official) | 30.2 GPTQ-Int4 (official; barely smaller than FP8) | yes / yes (~22 GB headroom) | vLLM ≥0.17, `--reasoning-parser qwen3`, `--language-model-only`. KV 66 KB/token | 312 tok/s peak aggregate in FP8 (Millstone via markaicode, **unverified**) | budgets 32,768 / 81,920 |
| Qwen3.5-35B-A3B | 36.0B / ~3B MoE (256 experts, top-8) | L40 d2048; full attention in 10 of 40 layers (2 KV heads); ctx 262K | as 3.5-9B | 71.9 | 37.5 (official) | 24.4 GPTQ-Int4 (official) | FP8 yes / **marginal** (~6 GB headroom; use FP8 in HF or text-only) | KV 20 KB/token | 907.7 tok/s at 10 concurrent requests and 1K context; 212 tok/s single stream, FP8 (Millstone via markaicode, **unverified**) | budgets 32,768 / 81,920 |
| Qwen3.6-27B | as 3.5-27B | as 3.5-27B | as 3.5. Adds `preserve_thinking` | 55.6 | 30.9 (official) | 20.4 AWQ (cyankiwi, community) | yes / yes | Card: vLLM ≥0.19, sglang ≥0.5.10 | none verified | budgets 32,768 / 81,920 |
| Qwen3.6-35B-A3B | as 3.5-35B-A3B | as 3.5-35B-A3B | as 3.6-27B | 71.9 | 37.5 (official) | 24.4 GPTQ (palmfuture, community) | FP8 yes / marginal | as 3.5-35B-A3B | none (3.5 numbers used as a proxy) | as above |
| Qwen3.8-27B | as 3.5-27B (`qwen3_5_text`) | as 3.5-27B | Hybrid. `enable_thinking`, `reasoning_effort` (low / medium / xhigh, default xhigh), `preserve_thinking` (default on). Tmpl opens. **Template injects a reasoning-effort sentence into the system prompt** | 55.6 | 30.9 (official) | 21.0 AWQ (cyankiwi, community) | yes / yes | Recipe: vLLM ≥0.17, transformers ≥5.8. The recipe has no Hopper commands (it targets Blackwell) | none for H100 | Card: reasoning budget up to 262,144 |
| DeepSeek-R1-Distill-Qwen-7B | 7.6B dense (Qwen2.5-Math base) | L28 d3584, 4 KV heads, ctx 128K | Thinking only, tmpl opens. **No system prompt** | 15.2 | 8.7 FP8-dynamic (RedHatAI) | community | yes / yes | KV 57 KB/token. DeepSeek changed the config and tokenizer, so use their repo | 7,315 total tok/s offline (vLLM bf16, 300 requests, 100 in / 600 out; [DatabaseMart](https://www.databasemart.com/blog/vllm-gpu-benchmark-h100)) | budget 32,768. Measured length not found |
| DeepSeek-R1-Distill-Qwen-14B | 14.8B dense | L48 d5120, 8 KV heads, ctx 128K | as 7B | 29.5 | 16.3 (RedHatAI) | community | yes / yes | KV 196 KB/token | 4,304 offline / 4,821 online (same benchmark) | as 7B |
| DeepSeek-R1-Distill-Qwen-32B | 32.8B dense | L64 d5120, 8 KV heads, ctx 128K | as 7B | 65.5 | 34.3 (RedHatAI) | 19.2 w4a16 (RedHatAI) | FP8 yes / yes | Card example uses `--max-model-len 32768 --enforce-eager` with TP2 | 1,391 offline / 1,482 online (same benchmark, bf16) | as 7B |
| DeepSeek-R1-Distill-Llama-8B | 8.03B dense (Llama-3.1-8B base) | L32 d4096, 8 KV heads, ctx 128K | as 7B | 16.1 | 9.1 (RedHatAI) | community | yes / yes | Llama 3.1 licence applies on top of MIT | 6,488 offline (same benchmark) | as 7B |
| DeepSeek-R1-Distill-Llama-70B | 70.6B dense (Llama-3.3-70B-Instruct base) | L80 d8192, 8 KV heads | as 7B | 141.1 | 72.7 (RedHatAI) | 39.5 w4a16 (RedHatAI) | w4a16 only (FP8 leaves ~0 KV) / **no** | KV 328 KB/token | none for 1 GPU | as 7B |
| DeepSeek-R1-0528-Qwen3-8B | 8.19B dense (Qwen3-8B base) | L36 d4096, ctx 128K | Thinking only. **Model opens** (template does not add `<think>`). System prompt supported | 16.4 | 9.4 FP8-dynamic (community) | community | yes / yes | Same arch as Qwen3-8B but DeepSeek's tokenizer config; use their files | none | Card (for the 671B R1-0528): AIME average **23K** tokens, up from 12K. 64K generation limit. The 8B's own length is **unverified** |

## Per-model notes

### Qwen3 (hybrid, Apr 2025): 8B / 14B / 32B / 30B-A3B
- **Template:** the generation prompt is `<|im_start|>assistant\n`, and the model emits `<think>\n…</think>\n\n` itself.
  - `enable_thinking=False` pre-fills an empty `<think>\n\n</think>\n\n`.
  - `/think` and `/no_think` in the user or system message switch modes when `enable_thinking=True`. The think block is then always present, though it may be empty.
- **System prompt** works normally.
- **Sampling:** temp 0.6, top-p 0.95, top-k 20, min-p 0. The card says never use greedy decoding.
- **Versions:** transformers ≥4.51, vLLM ≥0.8.5.
- **Reasoning parser:** `qwen3`, or `deepseek_r1` per the 32B card. Newer vLLM dropped `--enable-reasoning`; pass only `--reasoning-parser` (**unverified**, from memory).
- **Context:** native context is 32,768 tokens (`max_position_embeddings` 40,960). YaRN extends it to 131K.
- **Quantized repos:** official FP8 is fine-grained e4m3 with block size 128×128 and runs on H100 FP8 kernels. Official AWQ exists for the dense models and GPTQ-Int4 for 30B-A3B.
- Sources: [Qwen3-32B card](https://huggingface.co/Qwen/Qwen3-32B), [Qwen3-8B tokenizer_config](https://huggingface.co/Qwen/Qwen3-8B/blob/main/tokenizer_config.json), [Qwen3-32B-FP8](https://huggingface.co/Qwen/Qwen3-32B-FP8), [Qwen3-32B-AWQ](https://huggingface.co/Qwen/Qwen3-32B-AWQ), [Qwen3-30B-A3B-GPTQ-Int4](https://huggingface.co/Qwen/Qwen3-30B-A3B-GPTQ-Int4).
- **Throughput:** a GPUStack lab result for Qwen3-32B on one H100 is only available second-hand: vLLM 2,352.8 total tok/s, TensorRT-LLM 2,659.5, and TRT-LLM with FP8 and chunked prefill 4,284.7 ([markaicode summary](https://markaicode.com/benchmarks/vllm-qwen-3-h100-throughput-benchmark/), **unverified**).

### Qwen3 Thinking-2507 (4B, 30B-A3B; 235B-A22B is too big) and Qwen3-Next-80B-A3B-Thinking
- **Thinking only:** the template appends `<think>\n`, so the output contains only `</think>`. There is no `enable_thinking` flag. The Instruct-2507 siblings are non-thinking.
- **Context and budgets:** 262K native context. Budgets are 32,768 for general use and 81,920 for hard problems. The card warns of "increased thinking length".
- **Sampling:** temp 0.6, top-p 0.95, top-k 20; `presence_penalty` 0–2 against repetition.
- **Qwen3-Next-80B:** FP8 is 82.1 GB and does not fit. Only community AWQ-4bit (49.2 GB) fits for vLLM, and there is no bf16 HF path on one card.
- Sources: [30B-A3B-Thinking-2507](https://huggingface.co/Qwen/Qwen3-30B-A3B-Thinking-2507), [4B-Thinking-2507](https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507), [Next-80B-Thinking-FP8](https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Thinking-FP8), [cyankiwi AWQ](https://huggingface.co/cyankiwi/Qwen3-Next-80B-A3B-Thinking-AWQ-4bit), [QuantTrio 30B-2507 AWQ](https://huggingface.co/QuantTrio/Qwen3-30B-A3B-Thinking-2507-AWQ).

### QwQ-32B (Mar 2025)
- **Model:** Qwen2.5-32B base, `Qwen2ForCausalLM`, vocabulary 152,064.
- **Template:** appends `<think>\n`.
- **Sampling:** temp 0.6, top-p 0.95, top-k 20–40, min-p 0; `presence_penalty` 0–2. Budget 32,768.
- **Long prompts:** prompts over 8K tokens need YaRN, and vLLM's YaRN is static.
- **Quantized repos:** official AWQ only. FP8 comes from RedHatAI's FP8-dynamic repo, or use vLLM `--quantization fp8`.
- **Measured length:** 13,566 tokens on AIME24, 8,490 on MATH-500, 13,861 on GPQA-D and 4,473 on LiveCodeBench (round 1, [arXiv 2503.19855 Table 2](https://arxiv.org/html/2503.19855)).
- Sources: [QwQ-32B card](https://huggingface.co/Qwen/QwQ-32B), [QwQ-32B-AWQ](https://huggingface.co/Qwen/QwQ-32B-AWQ), [RedHatAI FP8](https://huggingface.co/RedHatAI/QwQ-32B-FP8-dynamic).

### Qwen3.5 / Qwen3.6 / Qwen3.8 (27B dense, 35B-A3B MoE, 9B dense)
- **Architecture:** each block of 4 layers is 3 Gated DeltaNet (linear-attention) layers plus 1 gated full-attention layer (KV head_dim 256). There is a 1-layer MTP head and a vision tower; HF class `Qwen3_5ForConditionalGeneration` (or `…Moe…`).
- **Probes, loading:** `Qwen3_5ForCausalLM` loads text-only and supports `output_hidden_states`.
- **Probes, KV cache:** only the full-attention layers keep a KV cache, about 66 KB/token for the 27B. The DeltaNet layers carry a fixed recurrent state per sequence, so long traces are cheap in vLLM.
- **Probes, kernels:** HF needs `flash-linear-attention` (`fla`) and `causal-conv1d` for fast DeltaNet kernels. Without them it silently falls back to slow, memory-hungry PyTorch ([transformers Qwen3.5 doc](https://huggingface.co/docs/transformers/main/en/model_doc/qwen3_5)).
- **Probes, compile cost:** the sibling repo found that the fla kernels compile once per sequence length (0.8 s each, about 10× the forward pass). Right-padding inputs to multiples of 256 tokens gives exact results and cut per-trace time from 0.9 s to 0.11 s (`EvalGamingUnderPressureTraining/docs/journal/2026-10-15.md`).
- **Versions:** transformers ≥5.2 for 3.5 ([NVIDIA Megatron-Bridge doc](https://docs.nvidia.com/nemo/megatron-bridge/0.6.0/models/qwen/qwen35-vl.html), secondary) and ≥5.8 for 3.8 per the vLLM recipe. vLLM ≥0.17 for 3.5 and 3.8; the 3.6 card says ≥0.19. This project's lock (vLLM 0.31.0, transformers 5.17.0, fla 0.5.2) meets all of them.
- **Template:** appends `<think>\n` by default. `enable_thinking=False` pre-fills an empty think block. `/think` and `/no_think` are not supported, and the template ignores them.
  - System prompts render normally.
  - From 3.6 on, `preserve_thinking` keeps past think blocks; in 3.8 it is on by default.
  - In 3.8 the default `reasoning_effort` is xhigh, and the template **prepends a sentence to the system message**: "Reasoning effort is set to xhigh. Please think carefully…". `low` adds a different sentence. Only `medium` adds nothing. I checked this by rendering the template. It matters for matched-prompt experiments.
- **Sampling, 3.5:** thinking: temp 1.0, top-p 0.95, top-k 20, `presence_penalty` 1.5 (precise coding: temp 0.6, `presence_penalty` 0). Non-thinking: temp 0.7, top-p 0.8, `presence_penalty` 1.5.
- **Sampling, 3.6 and 3.8:** thinking: temp 1.0, top-p 0.95, top-k 20, `presence_penalty` **0**.
- **Budgets:** 32,768 for most queries and 81,920 for competition problems (3.5 and 3.6). 3.8 suggests up to 262,144 reasoning plus 131,072 answer.
- **vLLM:** run `--reasoning-parser qwen3 --language-model-only`; the latter frees the vision memory for KV.
  - Prefix caching for these hybrid models is experimental ("align" mode).
  - If you hit a CUDA-graph or Mamba-cache size error, lower `--max-cudagraph-capture-size`.
  - MTP speculative decoding is available via `--speculative-config '{"method":"mtp","num_speculative_tokens":1}'`.
  - The v0.18 release notes list a known accuracy problem with **FP8 KV cache** on B200. Keep the KV cache in bf16.
  - A third-party card claims the small DeltaNet projections lose precision under FP8 (**unverified**).
- **Quantized repos:**
  - Official FP8 exists for 27B and 35B-A3B (3.5, 3.6 and 3.8-27B), but not for 3.5-9B.
  - Official GPTQ-Int4 exists only for 3.5-27B, 35B-A3B, 122B and 397B. The 27B Int4 is 30.2 GB, about the same as FP8, which suggests much of the model is left unquantized.
- **H100 fit:**
  - 27B: bf16 fits both vLLM and HF with room to spare. It is the strongest dense model that runs unquantized in both.
  - 35B-A3B: bf16 is 71.9 GB, too tight for HF with 10 GB headroom. Use FP8 (37.5 GB) for vLLM. For HF, use FP8 weights (transformers supports fine-grained FP8 on H100) or text-only loading. Text-only saves only about 1 GB, so it stays marginal.
- **Throughput:** the only H100 numbers are Millstone AI's, via a secondary digest (**unverified**). 3.5-27B FP8 reached 312 tok/s peak aggregate. 3.5-35B-A3B FP8 reached 907.7 tok/s at 10 concurrent requests with 1K context, and 212 tok/s single stream ([markaicode](https://markaicode.com/benchmarks/hugging-face-qwen-25-h100-throughput-benchmark/)). No verified 3.6 or 3.8 H100 numbers were found.
- **Related model:** Qwen-AgentWorld-35B-A3B (Jun 2026) is an agentic fine-tune of the 3.5-35B-A3B base with the same architecture.
- Sources: [Qwen3.5-27B card](https://huggingface.co/Qwen/Qwen3.5-27B), [Qwen3.5-9B card](https://huggingface.co/Qwen/Qwen3.5-9B), [Qwen3.6-27B card](https://huggingface.co/Qwen/Qwen3.6-27B), [Qwen3.8-27B card](https://huggingface.co/Qwen/Qwen3.8-27B), [vLLM recipe 3.5-27B](https://recipes.vllm.ai/Qwen/Qwen3.5-27B), [vLLM recipe 3.8-27B](https://recipes.vllm.ai/Qwen/Qwen3.8-27B), [vLLM 0.18 notes](https://newreleases.io/project/pypi/vllm/release/0.18.0), [Qwen3.5-27B-GPTQ-Int4](https://huggingface.co/Qwen/Qwen3.5-27B-GPTQ-Int4), [RedHatAI Qwen3.5-9B-FP8](https://huggingface.co/RedHatAI/Qwen3.5-9B-FP8-dynamic), [cyankiwi Qwen3.8-27B AWQ](https://huggingface.co/cyankiwi/Qwen3.8-27B-AWQ-INT4).

### DeepSeek-R1 distills (Jan 2025): Qwen-7B / 14B / 32B, Llama-8B / 70B
- **Template:** appends `<｜Assistant｜><think>\n`, so outputs lack the opening tag. Earlier, the models sometimes skipped thinking by emitting `<think>\n\n</think>`, and the forced tag works around that.
- **System prompt:** the card says "Avoid adding a system prompt; all instructions should be contained within the user prompt."
- **Sampling:** temp 0.5–0.7 (0.6 recommended), top-p 0.95. Maximum generation 32,768.
- **Configs:** DeepSeek changed the configs and tokenizers, so use their repos.
  - Qwen distills use DeepSeek BOS and EOS tokens and vocabulary 152,064.
  - The Qwen-7B and 1.5B distills are built on Qwen2.5-Math.
- **Licence:** MIT, plus the Llama 3.1 or 3.3 licence for the Llama distills.
- **No official quants.** RedHatAI publishes FP8-dynamic and w4a16 versions.
- **Llama-70B:** HF bf16 is impossible on one card. For vLLM only w4a16 (39.5 GB) fits sensibly; FP8 is 72.7 GB.
- **Throughput:** DatabaseMart's H100 vLLM bf16 benchmark is primary-source but heavily batched, and it reports input plus output tokens. Offline: Qwen-7B 7,315, Llama-8B 6,488, Qwen-14B 4,304, Qwen-32B 1,391 tok/s ([DatabaseMart](https://www.databasemart.com/blog/vllm-gpu-benchmark-h100); vLLM version not stated).
- **Trace length:** no primary measurement found. The 32,768 budget is an upper bound.
- Sources: [R1-Distill-Qwen-32B card](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B), [RedHatAI 70B w4a16](https://huggingface.co/RedHatAI/DeepSeek-R1-Distill-Llama-70B-quantized.w4a16), [RedHatAI 70B FP8](https://huggingface.co/RedHatAI/DeepSeek-R1-Distill-Llama-70B-FP8-dynamic), [RedHatAI 32B FP8](https://huggingface.co/RedHatAI/DeepSeek-R1-Distill-Qwen-32B-FP8-dynamic).

### DeepSeek-R1-0528-Qwen3-8B (May 2025)
- **Model:** Qwen3-8B architecture with DeepSeek's tokenizer config; use their files, not Qwen's.
- **Template:** does not add `<think>`; the card says forcing it is no longer needed. System prompts are supported.
- **Sampling:** temp 0.6, top-p 0.95. Maximum generation 64K.
- **Trace length:** the R1-0528 card reports AIME average tokens rising from 12K to 23K for the full model. Expect long traces (**unverified** for the 8B).
- **Quantized repos:** community FP8 only (JamAndTeaStudios, 9.4 GB).
- Source: [card](https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B).

## Short take for this project
- **Unquantized in both vLLM and HF on one H100:** every model ≤14B, the 30B-A3B pair, and Qwen3.5/3.6/3.8-27B.
- **32B dense models** (Qwen3-32B, QwQ, R1-Qwen-32B): sample in FP8 and probe in bf16, as the project already does with Qwen3-32B.
- **Do not fit cleanly in HF bf16:** 35B-A3B (3.5 and 3.6), Next-80B, Llama-70B and all 2026 DeepSeek models.
- **Watch-outs:** the Qwen3.8 template silently edits the system prompt. The R1 distills want no system prompt. Qwen3.5+ needs fla and causal-conv1d, and inputs padded to fixed lengths, for fast HF forwards.
