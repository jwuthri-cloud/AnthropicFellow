# Scenario pairs

| File | Pairs | What |
|---|---|---|
| `pairs.jsonl` | 40 | v1 set (data_loss / health_finance / sycophancy), used in all runs so far |
| `pairs_fresh.jsonl` | 24 | independently written generalization set (config 16) |
| `pairs_v2.jsonl` | 458 | 500-pair expansion after Opus review and merge (below) |

## v2 pipeline
1. **Writing.** 25 Sonnet subagents wrote 500 pairs into `pairs_new_*.jsonl`, following `docs/design/scenario_spec.md`. Each writer had its own category and sub-topics.
2. **Review.** Opus subagents reviewed every file against `docs/design/scenario_review.md`. They acted as domain experts (physician, pharmacist, lawyer, safety engineer). Each pair got a verdict of keep, fix or drop, and was assigned one of 10 categories.
   - The fixed files are in `reviewed/pairs_new_*.jsonl`.
   - The verdict logs are in `reviewed/*_review.jsonl`.
   - The writer's original label is kept as `writer_type`.
3. **Merge.** `scripts/merge_scenarios.py` builds `pairs_v2.jsonl`:
   - It applies `reviewed/merge_drops.txt`: cross-file duplicate situations, plus one pair where only a dog is harmed.
   - It re-validates every pair.
   - It adds `tier`.

## Categories (harm-row `harm_type`) and tiers

| Tier | Categories |
|---|---|
| life_body (238 pairs) | medical 65, mass_public_safety 63, physical_injury 44, child_vulnerable 39, third_party_physical 27 |
| material (153 pairs) | financial 67, data_loss 44, legal_status 42 |
| social_privacy (67 pairs) | privacy_security 42, social_psychological 25 |

- **Fact distance:** 231 near, 227 far.
- **Target letter:** A 159, B 152, C 147.
