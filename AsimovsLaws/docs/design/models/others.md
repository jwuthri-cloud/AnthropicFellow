# Open thinking models for 1x H100 80GB, excluding Qwen / DeepSeek / Mistral / NVIDIA / Meta (as of 2026-10-26)

Scope: vLLM sampling plus an HF transformers forward pass with `output_hidden_states`, on one H100 80GB with about 10 GB to spare.
Weight sizes are params × bytes (bf16 = 2, FP8 = 1, int4 ≈ 0.55 including scales), unless a repo is cited. KV/token is computed from config.json with the formula in the rules-of-thumb section, at bf16 KV.
**[U]** = not verified against a primary source.

## Summary table

| Model | Params (total/active) | Arch | Think format | bf16 GB | FP8 GB | int4 GB | Fits H100: vLLM / HF fwd | vLLM / HF notes | H100 tok/s | Typical think length |
|---|---|---|---|---|---|---|---|---|---|---|
| **gpt-oss-20b** (OpenAI, Aug 2025, Apache-2.0) | 21B / 3.6B | MoE 32e top-4, 24 L, d=2880, GQA 64q/8kv hd64, alt. SW-128/full, 131k ctx | harmony: `<\|channel\|>analysis<\|message\|>…<\|end\|><\|start\|>assistant<\|channel\|>final<\|message\|>…<\|return\|>`. Model writes the channel. `Reasoning: low/medium/high` goes in the system msg | ~42 (unsloth BF16) | n/a | **~13–16 native MXFP4** (experts only) | ✅ / ✅ (MXFP4 or bf16 dequant) | vLLM ≥0.10.1 runs it natively. HF needs `kernels` + triton ≥3.4. No `</think>` | n/a found | low ≪ medium < high; 30k max_tokens advised at high |
| **gpt-oss-120b** | 117B / 5.1B | MoE 128e top-4, 36 L, d=2880, 8kv hd64, alt. SW/full | harmony (same) | ~234 | n/a | **~61–65 MXFP4** | ✅ (KV ~37 KB/tok, cheap) / ⚠️ MXFP4 only, ~15 GB left | bf16 dequant does not fit. HF forward runs on MXFP4 Triton kernels | **8,973 tok/s/GPU @50 tok/s/user, 8k in/1k out (InferenceX)** | same |
| **Gemma 4 31B-it** (Google, Apr 2026, Apache-2.0) | 30.7B dense (+vision) | 60 L (50 SW-1024 : 10 global), d=5376, 32q/16kv hd256. Global layers: 4kv hd512, k=v | `<\|think\|>` at the start of the system prompt turns it on. Output `<\|channel>thought\n…<channel\|>answer`. Thinking off still emits an empty thought block | ~62 (unsloth: 62) | ~31–33 (RedHatAI FP8-dynamic / FP8-block) | ~18–20 (Google QAT Q4_0 / w4a16) | ✅ (FP8 best; bf16 leaves ~5 seqs × 8k) / ✅ bf16 tight (~10 GB left) | vLLM ≥0.19.1, `--reasoning-parser gemma4`, `enable_thinking` chat kwarg (default off). HF: latest transformers, `Gemma4ForConditionalGeneration`, `processor.parse_response` | n/a | [U] |
| **Gemma 4 26B-A4B-it** | 25.2B / 3.8B | MoE 128e top-8 +1 shared, 30 L (25 SW : 5 global), d=2816 | same as 31B | ~50–52 | ~26 [U repo] | ~16–18 | ✅ (KV very cheap) / ✅ | same | n/a | [U] |
| **Gemma 4 12B / E4B / E2B** | 12B / 4.5B / 2.3B eff. | dense, 48/42/35 L | same. The card's empty-block rule excludes E2B/E4B; their thinking-off output is not described [U] | 24 / 16 / 10 | | | ✅ / ✅ | | | |
| **Phi-4-reasoning / -plus** (Microsoft, Apr 2025, MIT) | 14.7B dense | Phi3ForCausalLM, 40 L, d=5120, 40q/10kv, 32k ctx | `<think>…</think>` written by the model. The template **hardcodes its own system prompt and drops yours** | 29.4 | ~15 | ~8.5 | ✅ / ✅ | vLLM `--reasoning-parser deepseek_r1`. Plain HF works | n/a | long; plus ≈1.5× reasoning; max_new 32k |
| **Phi-4-reasoning-vision-15B** (Mar 2026, MIT) | 15B | Phi-4-R + SigLIP-2, 16k ctx | `<think>…</think>` or `<nothink>`. Prefill either one to force the mode, else the model picks | ~30 | ~15 | ~9 | ✅ / ✅ | vLLM ≥0.15.2, transformers ≥4.57.1 | n/a | n/a |
| **Phi-4-mini-flash-reasoning** (Jul 2025, MIT) | 3.8B | SambaY hybrid (Mamba + 1 global attn + GMU), 64k | model card shows no think tags [U] | 7.7 | | | ✅ / ⚠️ | HF needs `trust_remote_code`, pinned transformers 4.46.1, mamba-ssm, flash-attn. Hidden states are SSM/attn hybrid | claims up to 10× decode vs Phi-4-mini-R (A100) | max_new 32k |
| **OLMo-3 7B Think** (AI2, Nov 2025, Apache-2.0, **open data**) | 7.3B dense | 32 L, d=4096, **MHA 32kv** hd128, 3 SW-4096 : 1 full, 65k ctx | `<think>…</think>`. **The template opens `<think>`**, so the output has only `</think>` | 14.6 | ~7.3 | ~4.5 | ✅ / ✅ | transformers ≥4.57. vLLM: plain `LLM()`, no parser in the card. Online `--quantization fp8` possible | n/a | max 32k tok, T 0.6 / p 0.95 |
| **OLMo-3.1 32B Think** (Dec 2025) | 32B dense | 64 L, d=5120, 40q/8kv, 3 SW : 1 full, 65k ctx | same (template opens `<think>`) | 64.4 | ~32 (online FP8; no official repo found) | ~18 | ✅ FP8 (bf16 tight) / ✅ bf16 (~12 GB left) | full SFT / DPO / RL checkpoints and data released | n/a | max 32k |
| **EXAONE 4.0 32B** (LG, Jul 2025, **NC license**) | 32B dense | 64 L, d=5120, 40q/8kv hd128, LLLG (SW 4096), 131k | `enable_thinking=True`. Template opens `<think>`, model closes it | 64 | ~32 (`LGAI-EXAONE/EXAONE-4.0-32B-FP8`, [U] via Furiosa docs) | ~19 (`…-AWQ` [U]) | ✅ / ✅ tight | vLLM ≥0.10.0 `--reasoning-parser deepseek_r1`; transformers ≥4.54 | n/a | T 0.6, p 0.95, presence_penalty 1.5 if it degenerates |
| **EXAONE Deep 32B / 7.8B / 2.4B** (Mar 2025, NC) | 32B / 7.8B / 2.4B dense | EXAONE-3.5 base, 32k | **`<thought>…</thought>`**, template opens it. Card says no system prompt | 64 / 15.6 / 4.8 | | official AWQ [U names] | ✅ / ✅ | **breaks a `</think>` parser** | n/a | T 0.6, p 0.95 |
| **Seed-OSS-36B-Instruct** (ByteDance, Aug 2025, Apache-2.0) | 36B dense | 64 L, d=5120, 80q/8kv hd128, 512k native | **`<seed:think>…</seed:think>`**, written by the model. Optional `thinking_budget` adds a system turn and inline `<seed:cot_budget_reflect>` tags. Budget 0 prefills an empty block | **72.3** | ~36 | ~20 | ✅ FP8 only (bf16 KV ≈ 38k tok) / ❌ bf16 (~6 GB left) | vLLM ≥0.10 `--reasoning-parser seed_oss`. HF from a pinned git commit at release (now upstream [U]) | n/a | unlimited by default; budgets in multiples of 512 |
| **Hermes-4.3-36B** (Nous, Dec 2025, Apache-2.0) | 36B dense | Seed-OSS-36B base | `<think>…</think>` written by the model. Toggle with `thinking=True` or a system prompt. Hybrid | 72.3 | community | official GGUF only | same as Seed-OSS | tool parser `hermes` | n/a | T 0.6, p 0.95, k 20 |
| **GLM-4.7-Flash** (Z.ai, Jan 2026 [U date], MIT) | 31B / 3B | MoE 64e top-4 +1 shared, **MLA** (kv_lora 512), 47 L, d=2048, 202k ctx, MTP | `<think>…</think>`. **The template opens `<think>`** by default; `enable_thinking=False` prefills `</think>`. Past thoughts are cleared unless `clear_thinking=False` | 62 | ~31 (unsloth FP8-Dynamic, Geodd; not official) | ~17 | ✅ (MLA KV ≈54 KB/tok) / ✅ bf16 (~15 GB left) | vLLM needed nightly at release, `--reasoning-parser glm45 --tool-call-parser glm47`. Transformers ≥5.0 (Glm4MoeLite) | n/a | T 1.0, p 0.95, max_new 131k (!) |
| **GLM-Z1-32B-0414 / Z1-9B-0414** (Apr 2025, MIT) | 32B / 9B dense | GLM-4-0414 | `<think>…</think>` [U who opens] | 64 / 18.8 | | | ✅ / ✅ | glm45 parser returns empty reasoning if `<think>` is missing (vLLM forum) | n/a | [U] |
| **GLM-4.5-Air** (Jul 2025, MIT) | 106B / 12B | MoE | hybrid `<think>` (`/nothink`, `enable_thinking`) [U] | ~212 | ~110 (official FP8) | ~60 (community AWQ) | ⚠️ int4 only / ❌ | GLM-4.6 (355B) and GLM-5.x (GLM-5.3-Flash 320B/18B) are too big | | |
| **Granite 4.2 30B** (IBM, 25 Aug 2026, Apache-2.0) | ~29–30B dense | GraniteForCausalLM, 64 L, d=4096, 32q/8kv hd128, 128k (512k ext.) | `<think>…</think>`. **Template opens `<think>\n`** (default on). `enable_thinking=False` → `<think></think>`. `low_effort=True` | ~58 | ~29 (FP8 / mxfp4 / nvfp4 builds per eesel; repo names [U]) | ~16 | ✅ / ✅ (~15 GB left) | vLLM ≥0.20 with a custom `granite_thinking_parser` plugin (or `nemotron_v3`) | n/a | max_new 8192 (thinking) |
| **Granite 4.2 8B / 3B** | 8B / 3B dense | 40 L | same | 16 / 6 | | | ✅ / ✅ | | | |
| **Apriel-1.6-15B-Thinker** (ServiceNow, Dec 2025, MIT) | 15B (multimodal) | [U] | **No tags**: template opens with `Here are my reasoning steps:\n`; answer after `[BEGIN FINAL RESPONSE]` | ~30 | | | ✅ / ✅ | **breaks a `</think>` parser**. vLLM `--reasoning-parser apriel`, upstreaming status [U] | n/a | 30% fewer tokens than 1.5 |
| **ERNIE-4.5-21B-A3B-Thinking** (Baidu, Sep 2025, Apache-2.0 [U]) | 21B / 3B | MoE, 131k | `<think>` [U] | ~44 | ~22 | ~12 | ✅ / ✅ | [U] | n/a | [U] |
| **K2-Think-V2** (MBZUAI, Jan 2026, "fully open") | 70B dense | K2-V2 base | [U] | 140 | 70 | ~38 | ⚠️ FP8 tight / ❌ | HF repo not checked | | |
| MiniMax M1 / M2 / M3, Kimi K2-Thinking / K3, GLM-4.6 / 5.x, K-EXAONE 2.0 (750B) | 230B–2.8T | MoE | | | | | ❌ | multi-GPU only | | |

KV/token (bf16), for KV budgeting: gpt-oss-20b 24.6 KB (full layers only; SW-128 is negligible), gpt-oss-120b 36.9 KB, Gemma-4-31B 82 KB global + 0.84 GB/seq SW cap, Gemma-4-26B-A4B 20 KB + 0.21 GB/seq, OLMo-3-7B 131 KB + 1.6 GB/seq, OLMo-3.1-32B / EXAONE-4.0-32B 65.5 KB + 0.81 GB/seq, Phi-4-R 205 KB, Seed-OSS/Hermes-4.3 262 KB, Granite-4.2-30B 262 KB, GLM-4.7-Flash (MLA) 54 KB. The SW caps assume vLLM's hybrid allocator frees blocks that fall outside the window [U per model].

## Per-model notes

### OpenAI gpt-oss-20b / gpt-oss-120b
- Specs: config.json ([20b](https://huggingface.co/openai/gpt-oss-20b/raw/main/config.json), [120b](https://huggingface.co/openai/gpt-oss-120b/raw/main/config.json)). MXFP4 applies only to the MoE expert weights; attention, router, embeddings and lm_head stay bf16 ([vLLM recipe](https://recipes.vllm.ai/openai/gpt-oss-20b)). Card: [HF](https://huggingface.co/openai/gpt-oss-20b). Model card: [arXiv 2508.10925](https://arxiv.org/abs/2508.10925).
- **Research relevance:** OpenAI says it avoided direct optimization pressure on the CoT, to keep it monitorable, and that the CoT may contain hallucinated or harmful content ([model card](https://arxiv.org/html/2508.10925v1)). That fits a harm-foresight probe study well.
- Harmony ([OpenAI cookbook](https://developers.openai.com/cookbook/articles/openai-harmony)):
  - The roles are system, developer, user, assistant and tool. Effort goes in the system message (default medium). The prompt ends at `<|start|>assistant`, and the model writes `<|channel|>analysis…`.
  - Drop earlier analysis after a final answer; keep it across tool calls.
  - A `</think>` splitter does not work. Parse token IDs with `openai-harmony` or vLLM's HarmonyParser ([docs](https://docs.vllm.ai/en/latest/api/vllm/parser/harmony/)).
  - The delimiters are special tokens, so decode offline with `skip_special_tokens=False`. Otherwise the text collapses to "analysis…assistantfinal…" [U, widely reported].
  - The model can also emit `commentary` (preambles, tool calls) before `final`.
- HF: MXFP4 Triton kernels load automatically. They need `kernels` and triton ≥3.4, and compute capability ≥7.5 per the HF blog. Without them, transformers falls back to bf16 at about 4× the memory ([HF blog](https://huggingface.co/blog/faster-transformers)).
  - 20b dequantized to bf16 is about 42 GB, which fits for hidden states ([unsloth BF16](https://huggingface.co/unsloth/gpt-oss-20b-BF16)). One user hit OOM with `dequantize=True` on 8×40GB ([forum](https://discuss.huggingface.co/t/gpt-oss-20b-torch-outofmemoryerror-cuda-out-of-memory/173047)).
  - On H100, FA3 with attention sinks is available via `attn_implementation="kernels-community/vllm-flash-attn3"`.
  - The residual stream is bf16 either way, so hidden states are unaffected by MXFP4.
- Sampling: temperature 1.0, top_p 1.0 ([github](https://github.com/openai/gpt-oss)). Together recommends max_tokens ~30k at high effort ([docs](https://docs.together.ai/docs/gpt-oss.md)).
- Throughput: 120b on one H100 with vLLM FP4 reaches 8,973 tok/s/GPU at 50 tok/s/user and 10,284 at peak, on 8k in / 1k out ([SemiAnalysis InferenceX](https://inferencex.semianalysis.com/run/gptoss-120b-on-h100)). GitLab suggests about 10 concurrent requests at 32k context on one H100 ([GitLab](https://docs.gitlab.com/administration/gitlab_duo_self_hosted/vllm_gpt_oss_120b/)).
- No gpt-oss successor found as of Oct 2026.

### Google Gemma 4 (Apr 2026, Apache-2.0)
- Lineup: E2B, E4B, 12B Unified, 26B-A4B MoE and 31B dense ([model card](https://ai.google.dev/gemma/docs/core/model_card_4); configs for [31B](https://huggingface.co/google/gemma-4-31B-it/raw/main/config.json) and [26B-A4B](https://huggingface.co/google/gemma-4-26B-A4B-it/raw/main/config.json)). Every model has a built-in hybrid thinking mode.
- Thinking:
  - `<|think|>` at the start of the system prompt, or `enable_thinking=True` in the chat template, turns it on.
  - Output is `<|channel>thought\n…<channel|>` followed by the answer. Thinking off still produces an empty thought block on 12B/26B/31B.
  - Don't feed earlier thoughts back, except on tool turns.
  - Use `processor.parse_response(...)` ([HF card](https://huggingface.co/google/gemma-4-31B-it)). Turn markers are `<|turn>model … <turn|>` ([unsloth](https://unsloth.ai/docs/models/gemma-4.md)).
  - A `</think>` splitter does not work; split on `<channel|>` and keep special tokens.
- vLLM: ≥0.19.1, `--reasoning-parser gemma4`. Thinking is off unless you pass `chat_template_kwargs={"enable_thinking": true}`. For text-only runs use `--limit-mm-per-prompt '{"image":0,"audio":0}'`.
  - FP8: [RedHatAI/gemma-4-31B-it-FP8-dynamic](https://recipes.vllm.ai/Google/gemma-4-31B-it) (Hopper OK). NVFP4 is Blackwell-only.
  - The recipe uses TP=2 for bf16. On one H100, bf16 31B leaves only ~8 GB KV, so use FP8 for sampling.
- QAT int4 checkpoints exist (Q4_0 and compressed-tensors w4a16, [unsloth QAT notes](https://unsloth.ai/docs/jp/moderu/gemma-4/qat)). FP8 repos are third-party ([RedHatAI FP8-block](https://friendli.ai/models/RedHatAI/gemma-4-31B-it-FP8-block)).
- Sampling: T 1.0, top_p 0.95, top_k 64.
- HF hidden states: the class is multimodal (`Gemma4ForConditionalGeneration`). Take the text-model hidden states. Note `attention_k_eq_v: true` on global layers.
- AIME-2026 without tools: 89.2 (31B) and 88.3 (26B-A4B) per the card.
- 26B-A4B is likely the cheapest strong candidate here: ~50 GB bf16 with tiny KV.

### Microsoft Phi-4-reasoning family (MIT)
- Phi-4-reasoning(-plus): [card](https://huggingface.co/microsoft/Phi-4-reasoning-plus), [config](https://huggingface.co/microsoft/Phi-4-reasoning-plus/raw/main/config.json).
  - **Gotcha:** the chat template hardcodes `<|im_start|>system<|im_sep|>` with Phi's reasoning prompt, and silently drops any system message you pass ([tokenizer_config](https://huggingface.co/microsoft/Phi-4-reasoning-plus/raw/main/tokenizer_config.json)). Scenario system prompts must go in the user turn, or you edit the template.
  - The template does not open `<think>`; the model writes `<think>…</think>`.
  - Sampling: T 0.8, top_k 50, top_p 0.95, max_new 32k. Context is 32k. Card scope is mainly math.
- [Phi-4-reasoning-vision-15B](https://huggingface.co/microsoft/Phi-4-reasoning-vision-15B) (Mar 2026): `<think>` or `<nothink>` mode tags; prefill `<think>` to force reasoning. 16k ctx.
- [Phi-4-mini-flash-reasoning](https://huggingface.co/microsoft/Phi-4-mini-flash-reasoning): a hybrid SSM with a pinned old stack and remote code, so it is awkward for probing. Its throughput claim was measured on an A100.
- No Phi-5 found.

### AI2 OLMo-3 / 3.1 Think (Apache-2.0; fully open data, code and checkpoints)
- Cards and configs: [3.1-32B-Think](https://huggingface.co/allenai/Olmo-3.1-32B-Think), [7B config](https://huggingface.co/allenai/Olmo-3-7B-Think/raw/main/config.json), [32B config](https://huggingface.co/allenai/Olmo-3.1-32B-Think/raw/main/config.json). Paper: [arXiv 2512.13961](https://arxiv.org/abs/2512.13961).
- The SFT, DPO and RL stage checkpoints are all public, so you can probe the same scenario across training stages. That is unusual and valuable.
- The template generation prompt is `<|im_start|>assistant\n<think>` ([chat_template](https://huggingface.co/allenai/Olmo-3-7B-Think/raw/main/chat_template.jinja)). The completion holds reasoning, then `</think>`, then the answer.
  - Treat the prompt's `<think>` as part of the trace when you take token positions.
  - The default system prompt ("You are OLMo…") is inserted if you pass none.
- 7B uses full MHA (32 KV heads), so its KV is heavy per token; the sliding window helps.
- Sampling: T 0.6, top_p 0.95, max 32,768. Transformers ≥4.57.
- No Olmo 3.2/4 found.

### LG EXAONE
- [EXAONE-4.0-32B](https://huggingface.co/LGAI-EXAONE/EXAONE-4.0-32B) ([config](https://huggingface.co/LGAI-EXAONE/EXAONE-4.0-32B/raw/main/config.json)):
  - Hybrid reasoning via `enable_thinking`; the template opens `<think>`. Global layers use no RoPE. QK-Reorder-Norm.
  - Licence is EXAONE 1.2 **NC** (research use OK; check the terms).
  - FP8 repo per [Furiosa docs](https://developer.furiosa.ai/latest/en/furiosa_llm/models/exaone-4.0.html). [1.2B-FP8](https://huggingface.co/LGAI-EXAONE/EXAONE-4.0-1.2B-FP8) also exists.
- [EXAONE-Deep-32B](https://huggingface.co/LGAI-EXAONE/EXAONE-Deep-32B) uses `<thought>`, not `<think>`.
- 2026 releases are K-EXAONE 236B-A23B and K-EXAONE 2.0 750B-A37B (Apache-2.0), both too big ([HF](https://huggingface.co/LGAI-EXAONE/K-EXAONE-2.0-750B-A37B)).

### ByteDance Seed-OSS-36B and Nous Hermes-4.3-36B
- Seed-OSS: [card](https://huggingface.co/ByteDance-Seed/Seed-OSS-36B-Instruct), [config](https://huggingface.co/ByteDance-Seed/Seed-OSS-36B-Instruct/raw/main/config.json), [template](https://huggingface.co/ByteDance-Seed/Seed-OSS-36B-Instruct/raw/main/chat_template.jinja).
  - The generation prompt is only `<seed:bos>assistant\n`; the model opens `<seed:think>` itself.
  - Historical `reasoning_content` is re-rendered and never stripped.
  - Strip `<seed:cot_budget_reflect>` from traces. vLLM `seed_oss` parser ([docs](https://docs.vllm.ai/en/stable/api/vllm/reasoning/seedoss_reasoning_parser/)).
  - Sampling T 1.1, p 0.95.
  - bf16 is 72 GB, which breaks the 10 GB headroom rule for HF. Use FP8 (online or llm-compressor) for both passes, or 8-bit for HF.
- [Hermes-4.3-36B](https://huggingface.co/NousResearch/Hermes-4.3-36B) is Seed-OSS-based with `<think>` tags. Nous reports a ~72–75% answer rate on RefusalBench, so it complies more readily (useful as a contrast model).

### Zhipu / Z.ai GLM
- [GLM-4.7-Flash](https://huggingface.co/zai-org/GLM-4.7-Flash) ([config](https://huggingface.co/zai-org/GLM-4.7-Flash/raw/main/config.json), [template](https://huggingface.co/zai-org/GLM-4.7-Flash/raw/main/chat_template.jinja)) is the single-GPU GLM. It is MLA + MoE, compared in the card against gpt-oss-20b and Qwen3-30B-A3B-Thinking (AIME25 91.6).
  - The template appends `<think>`, so the output starts mid-reasoning.
  - The vLLM `glm45` parser can return empty reasoning when `<think>` is missing ([vLLM forum](https://discuss.vllm.ai/t/glm-4-7-fp8-reasoning-start-issues/2146)). Split at `</think>` yourself.
  - Megatron-Bridge docs say transformers ≥5.0.0rc0 ([NVIDIA](https://docs.nvidia.com/nemo/megatron-bridge/latest/models/glm/glm47.html)).
- [GLM-4.5-Air](https://huggingface.co/zai-org/GLM-4.5-Air) is 106B; it fits one H100 only as community int4. [GLM-Z1-32B-0414](https://huggingface.co/THUDM/glm-z1-32b-0414) is older and dense.
- GLM-5.3-Flash is 320B/18B, too big ([datanorth](https://datanorth.ai/news/z-ai-releases-glm-5-3-flash)).

### IBM Granite 4.2 (Aug 2026, Apache-2.0)
- [granite-4.2-30b card](https://huggingface.co/ibm-granite/granite-4.2-30b). Coverage: [eesel](https://www.eesel.ai/blog/granite-4-2).
- Dense transformer; it drops the Granite 4.0 Mamba/MoE hybrid. Sizes 3B, 8B and 30B.
- The template opens `<think>\n`. Three modes: thinking (default), low-effort, and off.
- Sampling T 1.0, p 0.95, required.
- The vLLM parser is a plugin file from the card, so it is not built in. IBM-reported AIME25 89.2 for the 30B.

### Others
- [Apriel-1.6-15B-Thinker](https://huggingface.co/ServiceNow-AI/Apriel-1.6-15B-Thinker): untagged reasoning ending at `[BEGIN FINAL RESPONSE]`. T 0.6.
- [ERNIE-4.5-21B-A3B-Thinking](https://openrouter.ai/baidu/ernie-4.5-21b-a3b-thinking) [U details].
- [K2-Think-V2 70B](https://mbzuai.ac.ae/news/mbzuai-launches-k2-think-v2-uaes-fully-sovereign-next-generation-reasoning-system/): fully open like OLMo, but 70B does not fit HF bf16.
- Too big for one H100:
  - [MiniMax-M3](https://howaiworks.ai/blog/minimax-m3-open-source-hugging-face): 428B/23B, Jun 2026.
  - MiniMax-M2: 230B/10B, interleaved `<think>` kept in history.
  - Kimi K2-Thinking (1T) and K3 (2.8T) ([fastino roundup](https://fastino.ai/blog/best-open-weight-models-2026)).

### Shortlist for this project (judgement)
1. **gpt-oss-20b**: unsupervised CoT by design, cheap, harmony parser needed.
2. **Gemma 4 26B-A4B / 31B**: strong 2026 hybrid thinkers, Apache-2.0, `<|channel>` parser.
3. **OLMo-3.1-32B / 3-7B Think**: open data and stage checkpoints; `</think>` split works.
4. **Granite 4.2 30B / GLM-4.7-Flash**: recent, fit in bf16 for HF.
5. **Phi-4-reasoning-plus**: small, but mind the system-prompt drop.

Seed-OSS/Hermes-4.3 need FP8 for HF.

## H100 rules of thumb

- **Precision and throughput.** H100 SXM: dense BF16 tensor ~989 TFLOPS, FP8 ~1,979, TF32 ~495, plain FP32 only 67. NVIDIA's headline 1,979 / 3,958 / 989 are *with sparsity*. 80 GB at 3.35 TB/s ([NVIDIA H100](https://www.nvidia.com/en-us/data-center/h100/)).
- **FP8 E4M3 is native on Hopper.** vLLM runs W8A8 FP8 on compute capability ≥8.9 (Ada, Hopper, Blackwell) and weight-only FP8 via Marlin on older GPUs ([vLLM FP8](https://docs.vllm.ai/en/latest/features/quantization/llm_compressor/fp8/)).
  - E4M3 (max 448) is used for weights and activations; E5M2 is for gradients ([FP8 formats, arXiv 2209.05433](https://arxiv.org/abs/2209.05433)).
  - Prefer the `FP8_DYNAMIC` scheme: per-channel static weights and per-token dynamic activations, no calibration. Online `fp8_per_tensor` gives limited speedups.
- **Quality cost.** FP8 W8A8 is "effectively lossless across all model scales". INT8 W8A8 loses about 1–3%. INT4 W4A16 (GPTQ/AWQ) is "competitive" ([Kurtic et al., arXiv 2411.02355](https://arxiv.org/abs/2411.02355)).
  - For reasoning models specifically, W8A8 and W4A16 can be lossless, but lower bit-widths carry significant risk. Risk grows with smaller models and harder tasks, and quantized models do not produce longer traces ([Liu et al., "Quantization Hurts Reasoning?", arXiv 2504.04823](https://arxiv.org/abs/2504.04823)).
  - FP8 hurts more when the per-tensor scales are coarse. Outlier-heavy layers (lm_head, router, attention sinks) are usually left in bf16. Watch FP8 KV cache on long traces [U general].
  - For probes, take hidden states from the same precision you sampled with, or check that probe AUROC is stable between bf16 and FP8.
- **KV cache per token** = 2 (K and V) × layers × kv_heads × head_dim × bytes ([NVIDIA blog](https://developer.nvidia.com/blog/mastering-llm-techniques-inference-optimization/)).
  - Example: 64 L × 8 kv × 128 × 2 B × 2 = 262 KB/token, so 10 GB holds ~38k tokens.
  - Sliding-window layers cap at window × per-layer cost. MLA stores (kv_lora_rank + rope_dim) × layers × bytes.
  - `--kv-cache-dtype fp8` halves KV memory.
- **One GPU means no tensor parallelism.** TP shards each layer across devices ([NVIDIA blog](https://developer.nvidia.com/blog/mastering-llm-techniques-inference-optimization/)). On 1 GPU, `--tensor-parallel-size 1` is the only option, so weights plus KV must fit in 80 GB × `gpu_memory_utilization`.
  - Recipes that say TP=2 (e.g. Gemma 4 31B bf16) need FP8 to run on one H100.
  - Leave ~10 GB for HF activations. `output_hidden_states` stores (layers+1) × seq × d × 2 B; 8k × 5120 × 65 × 2 ≈ 5.4 GB. Keep only the layers you need via hooks.
- **Why never fp32 for inference.** It doubles memory (4 B/param: a 32B model is 128 GB) and loses tensor-core throughput (67 vs ~989 TFLOPS dense). It also adds no information: these checkpoints are trained and released in bf16 (MXFP4 for gpt-oss experts).
  - Upcasting is only useful for probe math such as LR or PCA on extracted activations. Do it on CPU or in small batches.
