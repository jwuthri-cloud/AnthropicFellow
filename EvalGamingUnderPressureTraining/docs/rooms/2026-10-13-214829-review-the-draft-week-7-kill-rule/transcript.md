# Review the draft week-7 kill rule

Room `2026-10-13-214829-review-the-draft-week-7-kill-rule`, opened 2026-10-13T21:48:29+00:00.

| Seat | Label | Persona | Agent | Model | Family | Billing |
| --- | --- | --- | --- | --- | --- | --- |
| sol-statistician | Reviewer A | statistician | sol | gpt-6.1-sol | openai | subscription |
| haiku-skeptic | Reviewer B | skeptic | haiku | haiku | anthropic | subscription |
| opus-methodologist | Reviewer C | methodologist | opus | opus | anthropic | subscription |

## Brief

Draft week-7 decision rule for Arm A, to be written into the project plan. Context: the plan's current
kill line is one sentence ("If RL cannot remove verbalized awareness while keeping the behavior gap, arm A
stops"); a previous room (docs/rooms/2026-10-13-170917-is-the-week-7-kill-criterion-well-define/transcript.md)
found it not operational. Arm A runs GRPO on Qwen3-8B with reward = tests passed - lambda * monitor score,
lambda in {0, 0.5, 2.0}, 3 seeds each. The training monitor is Claude Haiku 5.5; the held-out judge is from
another model family (Mistral Small in the pilot, docs/pilot.md). Measurement uses held-out framings
(data/framings/heldout.jsonl) on Hua et al.'s 256 BigCodeBench tasks, none of which are RL tasks
(src/evalgaming/tasks.py). Synthetic reasoning traces are ruled out (CLAUDE.md): every labelled trace is real.

# Draft rule

Measured at step 300, or at the last checkpoint of at least 200 steps reached by the end of week 7. Under
200 steps, the decision moves one week; that is never a kill.

Preconditions. If one fails, the rule does not run: the problem is the organism or the judge.
- P1, something to remove: before RL, the held-out judge flags at least 20% of eval-context traces at level 1+.
- P2, judge works on real traces: on hand-labelled real traces, held-out judge precision and recall at least
  0.8 at level 1+, and recall at least 0.6 on the minimally verbalized ("indirect") category. Re-checked on
  100 hand-labelled traces from the lambda > 0 runs at the decision checkpoint.
- P3, the control keeps a gap: the lambda = 0 runs keep a mean gap of at least 20 points.

Each lambda > 0 seed is paired with the lambda = 0 run of the same seed (same organism checkpoint, tasks,
sampling and step). A seed passes when all three hold:
- V, words gone: held-out-judge verbalization on eval-context traces at most 0.25 x its pre-RL rate.
- G, behavior kept: one-sided 95% bootstrap lower bound of (gap_seed - 0.5 x gap_control) above 0, resampling
  paired (task, framing) prompts, and gap_seed at least 15 points (half the organism gate).
- C, no collapse: BigCodeBench pass rate within 5 points of the paired control.

A lambda passes when at least 2 of its 3 seeds pass.

Decision:
- Some lambda passes: continue Arm A; the best passing lambda goes to 27B.
- No lambda passes and V fails: stop Arm A ("RL cannot remove the words"), report.
- No lambda passes, V holds and G fails: stop Arm A, report A1 as a negative result (words and behavior
  leave together).
- The training monitor shows the drop but the held-out judge does not: not a kill. This is the
  monitor-gaming finding; add a readability term and a second monitor.

The numbers (20%, 0.8, 0.6, 0.25x, 0.5x, 15 points, 5 points, 2 of 3) are defaults. The pilot may revise
them once, before the first 8B run, with the reason in the journal. Then they are frozen.


## Round 1: host

Find the flaws in this draft week-7 decision rule: anything ambiguous, unmeasurable, gameable, statistically unsound, or that could kill a working arm or keep a dead one. Be concrete, cite repo files where relevant, and propose the exact fix. Under 300 words.

### sol-statistician (Reviewer A, statistician, gpt-6.1-sol, 35s)

**I would not freeze this rule yet.** Five fixes:

1. **Failure to establish success is not evidence of failure.** G’s lower bound can cross zero because precision is inadequate. Add an **inconclusive** outcome: continue when bounds establish all margins; declare scientific failure only when opposite bounds establish a missed margin. Apply uncertainty to V and C too. The pilot explicitly warns that threshold crossings alone are insufficient (`docs/pilot.md:20`).

2. **Specify the estimand and resampling unit.** Freeze mean hint coverage, framing weights, and missing-output handling (`src/evalgaming/behavior.py:48`; `docs/pilot.md:83`). Bootstrap **tasks**, retaining each task’s framings, baseline, treatment, and control together. The current difference helper assumes independent samples (`src/evalgaming/stats.py:41`). With **256 tasks and three training seeds per lambda**, prompt intervals quantify task uncertainty, not training-seed uncertainty. Report both separately; preregister adjustment for selecting among two penalized lambdas.

3. **P2’s 100 labels may provide almost no positive evidence.** At a true 5% verbalization rate, **100 randomly sampled traces contain five positives in expectation**, with potentially fewer indirect positives. Require a representative audit for precision plus enriched, blinded real-positive samples for recall; freeze minimum category denominators and confidence-bound requirements. Existing precision/recall denominators are predicted positives and human positives (`src/evalgaming/stats.py:69`).

4. **V can pass through unreadability or selective missingness.** Unreadable reasoning receives level zero (`data/monitor/rubric.md:32`); unscored traces leave verbalization denominators (`experiments/pilot/03_monitor_eval.py:85`). Add a readability gate and worst-case sensitivity analysis counting unreadable/unscored traces as verbalized.

5. **Decision branches overlap and omit outcomes.** “V holds” needs a seed/lambda quantifier; C-only failures and mixed-seed failures need branches. Put monitor disagreement before kill branches, and define “best.” Freeze one common checkpoint across all nine runs.

**What would change my mind:** a complete decision table and pilot-based power simulations showing that scientifically useful effects usually pass and clearly inadequate effects usually fail.

### haiku-skeptic (Reviewer B, skeptic, haiku, 30s)

**Reviewer B (Skeptic): the draft still has two contradictions that can kill a working arm or keep a dead one.**

**1. The monitor-gaming branch contradicts the V branch.** V is measured on the held-out judge (Mistral Small 3.2, docs/pilot.md:103). The rule says "no lambda passes and V fails: stop." If the training monitor drops but the held-out judge does not, V fails, so the rule stops the arm. The last bullet says "not a kill." One of them has to go. Fix: state the order explicitly. Monitor-gaming is a finding only if the held-out judge's V passes; if V fails on the held-out judge, that is a kill, and the training-monitor drop is reported as evidence of gaming.

**2. "Some branch fails" is not exhaustive.** The branches are keyed on "V fails" and "V holds and G fails," but V is per seed and per lambda. Take lambda=0.5 with V failing and lambda=2.0 with V holding and G failing. The rule does not say which branch applies. Fix: classify each lambda as V-pass or V-fail, and stop only if every lambda fails V, or every lambda that holds V fails G, and say which.

**3. P2 is an escape hatch for a dead arm.** P2 is re-checked "on 100 hand-labelled traces from the lambda > 0 runs at the decision checkpoint." RL is the force that moves verbalization into paraphrase and indirect forms. If the judge's recall drops on those traces, P2 fails, and "the problem is the judge" means the rule does not run. The arm that succeeded at hiding words is never killed. Fix: check P2 on pre-RL traces only. A post-RL recall drop should count as a V-level result, reported with the judge's per-category recall and not used to skip the decision.

**4. Thresholds are inconsistent and underpowered.** The pilot's go bar is precision and recall at least 0.9 (docs/pilot.md:18). The draft uses 0.8, plus 0.6 recall on "indirect." The pilot needs at least 60 level-1+ labels (docs/pilot.md:93), so an indirect category may hold 10 to 20 traces. A point estimate of recall 0.6 on 15 traces has a 95% interval of roughly ±25 points. Fix: use the Wilson lower bound against the threshold, and state the per-category n.

**5. V has no noise model.** Pre-RL verbalization is "at least 20%" (P1). With 256 traces per group, 0.25 × 20% is 5%, about 13 traces. Pass/fail on V at that scale is dominated by sampling noise. Fix: a one-sided test on the difference, with the bootstrap interval on both the pre-RL and post-RL rates.

**6. The G rule can pass a weak control.** G compares gap_seed to 0.5 × gap_control. P3 only requires the control to keep 20 points, but the organism gate is 30 (docs/pilot.md:16), and the baseline 95% interval is about ±8 (docs/pilot.md:20). If the control is at 22, G asks for 11, and the 15-point floor then binds. Fix: a paired seed-minus-control bootstrap that resamples tasks and framings jointly and includes sampling noise (temperature 0.6, docs/pilot.md:140), with the 15-point floor stated as a separate, reasoned choice.

**7. Undefined decision checkpoint is forking-path risk.** "Step 300, or the last checkpoint of at least 200 steps reached by the end of week 7" lets the checkpoint be chosen after results are seen. "Never a kill" under 200 steps also has no end date. Fix: one pre-registered step, plus a hard deadline (week 8) after which an unreached checkpoint counts as a failed run.

**8. C is two-sided and noisy.** "Within 5 points" fails when pass rate rises, which is not a collapse. At n=256 the SE is about 3 points, so ±5 fails often by chance. Fix: a one-sided test, pass rate not below control by more than 5 points, with its interval.

**9. Lambda selection reuses the test data.** "The best passing lambda goes to 27B" is chosen on the same held-out data used to pass it. Fix: choose on a split of framings, and report the other split.

**What would change my mind:** the revised rule passes a dry run on the pilot's step-1 and step-3 numbers (docs/pilot.md), so each branch is exercised and its output is known in advance. I would also accept a simulation showing the stop rate under a null arm (no verbalization change) is at most 10%, and under a working arm at least 80%.

### opus-methodologist (Reviewer C, methodologist, opus, 74s)

I checked the draft against `docs/pilot.md`, `data/framings/heldout.jsonl` and `src/evalgaming/stats.py`. Six problems, ordered by how likely each is to produce a wrong decision:

1. **V has no control.** It compares against the pre-RL rate, not against the λ=0 run at the same step. GRPO with a tests-only reward can cut verbalization by itself, for example by shortening reasoning. If it does, V passes at λ=0.5 for reasons that have nothing to do with the monitor, and the A1 "words and behavior leave together" reading becomes confounded.
   *Fix:* V requires the λ>0 rate to be at most 0.25 × the pre-RL rate **and** at most 0.5 × the paired control's rate.

2. **The P2 re-check cannot measure what V depends on.** If V holds, flagged traces fall to about 5% (0.25 × the 20% floor). Then 100 random traces contain about 5 positives, and a recall estimate on 5 positives is useless. V really depends on how many verbalizing traces the judge misses.
   *Fix:* hand-label 150 eval-context traces the judge scored 0, pooled over seeds, per λ. Mix them with control traces so the labeller cannot tell the condition. V then uses the corrected rate: the upper 95% bound of (flagged + missed) must be at most 0.25 × pre-RL. With 0 misses in 150, the miss bound is about 2% (rule of three).

3. **The bootstrap ignores how prompts cluster by framing.** `heldout.jsonl` has 150 framings in about 10 styles: 50 eval, 25 Wood Labs, 50 deploy, 25 neutral. Resampling (task, framing) pairs as if each were independent understates the uncertainty, because much of the gap's variance comes from the framing.
   *Fix:* use a two-way bootstrap that resamples tasks and framings separately. Also state whether Wood Labs framings count toward the gap. `pilot.md:16` defines the gap as eval minus deploy, while `pilot.md:17` puts Wood Labs with eval for verbalization. Fix the sample counts too.

4. **C can kill a working arm on noise.** The 5-point test is a point estimate on 256 tasks. `stats.difference` (`stats.py:41`) treats the two samples as independent, which is the wrong test for paired runs.
   *Fix:* paired by task, C fails only if the point drop is more than 5 points **and** the one-sided 95% bound rules out a drop smaller than 2.

5. **The decision tree overlaps and has gaps.**
   - The monitor-gaming case also fails V, so it matches both "stop" and "not a kill". Check monitor-gaming first.
   - Nothing covers C being the cause of failure. Treat that as a training problem: one week to rerun with a stronger KL term, not a kill.
   - Nothing covers seeds that fail on different criteria. Classify a λ by its seeds' majority failure.
   - "The rule does not run" when a precondition fails has no deadline, so a dead arm could stay open indefinitely. Add one: at most 2 weeks to fix the organism or judge, then stop.
   - "Best passing λ" is undefined. Use the smallest λ that passes.

6. **Pairs can be compared at different steps.** "Last checkpoint ≥200" is chosen per run.
   *Fix:* compare each pair at the earlier of its two last checkpoints.

**What would change my mind on #1:** if λ=0 RL in the pilot leaves the judge's verbalization rate within ±20% of pre-RL, the control-relative V is unnecessary.

## Conclusion

Adopted with most fixes, now in the plan's Risks section. Taken: an inconclusive outcome so low power cannot kill a working arm (A); V relative to both pre-RL and the paired lambda=0 control (C); V corrected by hand-labelling 150 judge-negative traces per lambda, with unreadable or unscored traces counted as verbalized (A, C); P2 checked on pre-RL traces only, with Wilson lower bounds (B); one fixed step for all nine runs and a week-8 hard deadline (B, C); bootstrap over tasks and framings, paired (A, C); one-sided C with a 2-point margin (B, C); ordered, exhaustive branches with monitor gaming first (all three); smallest passing lambda, not best (C); a dry run on pilot outputs and a null and working-arm simulation before freezing (A, B). Not taken: choosing lambda on a separate framing split (B), because halving 150 framings costs too much power and a fixed smallest-passing rule already avoids picking on effect size.
