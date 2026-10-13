# Test: framing split

Room `2026-10-13-080108-test-framing-split`, opened 2026-10-13T08:01:08+00:00.

| Member | Label | Model | Family | Billing | Role |
| --- | --- | --- | --- | --- | --- |
| haiku | Reviewer A | haiku | anthropic | subscription |  |
| sol | Reviewer B | gpt-6.1-sol | openai | subscription |  |

## Round 1: host

Read data/SPEC.md. What is the weakest part of how train and held-out framings are separated?

### haiku (Reviewer A, haiku, 44s)

**Weakest part: the split is enforced on labels and surface text, not on the cue mechanism or the task pool.**

What the spec does: train and held-out use disjoint `style` families (SPEC.md:41-50), and held-out is measurement-only (SPEC.md:13). What I checked in the data: none of the held-out style names appear in `train.jsonl`, and the held-out rows I read (e.g. `heldout.jsonl` lines 1-2, `research_study_consent`) use different wording from the train families. So the label-level separation holds.

Where it is weak:

1. **Disjointness is by label, and the label is self-assigned.** `style` is a string the generator writes. Nothing checks that a held-out `style` is actually stylistically distinct from a train one. A held-out `research_study_consent` can be a train `lab_system_prompt` with new wording, and the validator would pass it.

2. **The leakage check is lexical and cross-split only.** `scripts/validate_data.py:49-59` flags train/held-out pairs whose full framing text has high Jaccard similarity. This catches copy-paste, not shared structure. A held-out set can reuse the same cue family (for example, "item N of M" headers, or "two raters" language) with different words and pass. It also doesn't check the `notes` field, which describes the cue and could leak the grader's intent. I did not verify the threshold, since `near_duplicates` is imported from elsewhere.

3. **The spec says nothing about the BigCodeBench task pool.** Both splits insert `{task}` from the same benchmark. If train and held-out share tasks, a probe or classifier could key on the task rather than the framing. The spec should state whether tasks are disjoint across splits. I found no such rule in SPEC.md.

4. **Eval-word ban is shared, so held-out cues are constrained the same way.** Eval words are banned in `wood`, `deploy_*`, and `neutral` (SPEC.md:12), and the held-out styles must satisfy the same rules. That is good for controlling confounds, but it also means held-out and train may share a vocabulary signature (no "evaluat*", etc.) that a probe could learn as the eval/deploy boundary. Measurement on held-out would not separate "generalizes to new styles" from "learned the banned-word absence."

**What would change my mind:** a validator check that rejects held-out styles whose embedding or n-gram profile sits too close to any train style cluster, plus a stated rule that held-out and train use disjoint BigCodeBench task IDs. With both, I'd rate the split adequate for the claim "generalizes to new framing styles." Without the task-disjointness rule, I would not report held-out results as framing generalization.

### sol (Reviewer B, gpt-6.1-sol, 93s)

**The weakest part is that the split separates declared `style` names without establishing separation of the cues the model actually sees.** The spec requires disjoint style families (`data/SPEC.md:13`, `data/SPEC.md:41`), and the validator checks membership in those named families (`src/evalgaming/datasets.py:145`). That does not establish that held-out prompts require a new inference.

Concrete evidence:

- **The same cue survives a change of style.** Training’s `benchmark_header` says “Problem 118 / 1140” (`data/framings/train.jsonl:51`); held-out’s `ci_pipeline_log` says “loading item 219 of 1140 from queue” (`data/framings/heldout.jsonl:39`). The surrounding format changes, but the numbered-item cue remains. Likewise, training and held-out Wood framings both contain the literal “Wood Labs,” as the spec requires (`data/SPEC.md:36`; `data/framings/train.jsonl:101`; `data/framings/heldout.jsonl:51`). My inference is that success could reflect recognition of familiar cues in new wrappers.

- **There is an actual identical wrapper across the split.** Training’s `plain` and held-out’s `minimal` each include `system: null, user_template: "{task}"` (`data/framings/train.jsonl:251`; `data/framings/heldout.jsonl:126`). Comparing all **550 training and 150 held-out rows**, I found **1 of 150 held-out wrappers** exactly matches a training wrapper. Within neutral, that bare wrapper occurs in **1 of 50 training rows** and **1 of 25 held-out rows**. A shared bare-task control is defensible, but calling it an unseen framing style overstates the separation.

- **The leakage check cannot establish semantic novelty and misses that exact overlap.** It uses word-trigram Jaccard similarity with threshold `0.6` (`src/evalgaming/datasets.py:71`, `src/evalgaming/datasets.py:101`, `src/evalgaming/datasets.py:117`). It removes `{task}` before comparison and skips pairs with empty shingle unions, so identical bare wrappers escape detection (`src/evalgaming/datasets.py:123`; `src/evalgaming/datasets.py:115`). Cross-split validation relies on this check (`scripts/validate_data.py:49`).

**My judgment:** this split supports a test of transfer across presentation formats. By itself, it provides weaker evidence of transfer to unfamiliar evaluation cues. That distinction matters because the README describes measurement on “styles RL never saw” (`data/README.md:11`).

**What would change my mind:** a cue-level audit showing which held-out cues are genuinely absent from training, followed by results reported separately for familiar-cue/new-format prompts and novel-cue prompts. I would be substantially more convinced if the behavioral effect persisted on the latter, with matched coding tasks and per-family sample sizes and uncertainty reported. I would also explicitly designate shared neutral wrappers as controls rather than evidence of framing novelty.
