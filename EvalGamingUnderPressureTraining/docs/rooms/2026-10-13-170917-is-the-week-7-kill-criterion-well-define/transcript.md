# Is the week-7 kill criterion well defined?

Room `2026-10-13-170917-is-the-week-7-kill-criterion-well-define`, opened 2026-10-13T17:09:17+00:00.

| Seat | Label | Persona | Agent | Model | Family | Billing |
| --- | --- | --- | --- | --- | --- | --- |
| haiku-skeptic | Reviewer A | skeptic | haiku | haiku | anthropic | subscription |
| haiku-researcher | Reviewer B | researcher | haiku | haiku | anthropic | subscription |
| sol-methodologist | Reviewer C | methodologist | sol | gpt-6.1-sol | openai | subscription |

## Round 1: host

Is the week-7 kill criterion well defined?

### haiku-skeptic (Reviewer A, skeptic, haiku, 13s)

Reviewer A here. The criterion is not well defined yet, and the repo shows why.

The kill line is one sentence, `docs/landscape/fellowship-map.html:556`: "If RL cannot remove verbalization while keeping the behavior gap by week 7, drop arm A." Four things are unspecified:

1. **"Remove verbalization" has no threshold.** Verbalization is measured by whom? The CoT monitor being trained against? If so, a monitor that stops firing is not evidence the eval-awareness went quiet, which is exactly the question the project asks (`fellowship-map.html:549`).
2. **"Keeping the behavior gap" has no baseline or margin.** The only gap number in the journal is Montoya's 29-point type-hint gap at n=100, just under the 30-point bar (`docs/journal/2026-10-13.md:42`). If the organism is already borderline, a week-7 failure may reflect a weak organism, not Arm A.
3. **No matched λ=0 control.** Without it, a lost gap could be ordinary RL drift, and the criterion cannot separate the two. The journal names this gap itself (line 41).
4. **Seeds and timing.** Arm A runs 10–15 seeds (line 553). Is "by week 7" a per-seed rule, a majority rule, or a mean? And is there a minimum training budget before week 7 counts at all?

Evidence that would convince me: a written rule with a numeric verbalization cutoff, an independent judge with reported agreement against hand labels, a λ=0 arm at the same budget, and a stated seed-aggregation rule, all fixed before the pilot starts.

@Reviewer B

> Stance: not yet agreed: The week-7 kill criterion is not operational: it lacks a verbalization threshold, an independent judge, a matched λ=0 control, a baseline gap margin, and a seed-aggregation rule.; open: verbalization threshold and judge identity; gap baseline given the borderline 29-point organism; λ=0 control and minimum training budget; per-seed vs aggregate week-7 rule

### haiku-researcher (Reviewer B, researcher, haiku, 14s)

The kill criterion at `fellowship-map.html:556` is not well defined. It reads: "If RL cannot remove verbalization while keeping the behavior gap by week 7, drop arm A and put the time into arm B." Each of its terms is open:

- **"Remove verbalization":** no threshold. Is it a judged rate below 5%, or zero on a held-out set? Measured by whom? If the trained monitor also judges verbalization, the RL can satisfy the criterion by gaming the judge.
- **"Keeping the behavior gap":** relative to what? The gap needs a baseline and a tolerance, and a seed-level confidence interval. With 10 to 15 seeds at 8B, a single seed's gap is noise.
- **No matched λ=0 control:** RL drift alone can shrink or reshape the gap. Without a control run at the same step count, a "failure" may just be generic drift.
- **No minimum budget:** a week-7 kill with no step count can fire before arm A has had a fair run, which is a false kill.

I agree with the journal's gap list (`docs/journal/2026-10-13.md:41`). I would add that the criterion depends on the Qwen3.5-4B pilot showing enough baseline verbalization to suppress (`docs/journal/2026-10-13.md:28`). The criterion should state that precondition too.

Proposed fix, to pre-register before the pilot: verbalization rate at or below 5% on 200 held-out CoTs judged by a judge outside the training loop; behavior gap at least 50% of the λ=0 gap, with the seed-level CI excluding zero; both measured at a fixed step count set by the pilot.

What would change my mind: if the pilot shows baseline verbalization is too rare to suppress, the kill fires for a reason unrelated to the method.

> Stance: not yet agreed: The week-7 criterion is not operational: its verbalization and gap terms lack thresholds, an independent judge, a matched control, and a minimum budget.; open: Verbalization threshold and independent judge; Gap baseline, tolerance, and seed CI; λ=0 matched control and fixed step budget; Pilot precondition on baseline verbalization

### sol-methodologist (Reviewer C, methodologist, gpt-6.1-sol, 31s)

Host, my opening take is **no: the week-7 criterion states an objective but does not define a reproducible decision rule**. “Remove verbalization while keeping the behavior gap” specifies neither tolerated residual verbalization nor acceptable gap loss (`docs/landscape/fellowship-map.html:556`).

The pilot does provide entry thresholds and a held-out judge (`docs/pilot.md:16–20`, `docs/pilot.md:103`). Those help establish a usable organism and monitor; they do not define post-training success. Its GRPO instructions say to inspect whether scores fall and the gap survives (`docs/pilot.md:113`).

The discriminating experiment is matched training from the same organism with λ=0 and λ>0, holding tasks, training budget, and sampling fixed. The existing base-model comparison precedes organism training (`docs/pilot.md:80`), so it cannot isolate the monitor penalty from ordinary RL drift.

I would change my mind with a preregistered rule specifying:

- Residual verbalization measured by the held-out judge, validated against blinded human labels on post-RL traces.
- Gap retention and task-performance margins.
- Seed count, uncertainty rule, and minimum completed training budget before declaring failure.

That would distinguish operational failure from insufficient training or a fooled training monitor.

> Stance: not yet agreed: The week-7 criterion is not yet operationally defined.; open: Post-training thresholds and uncertainty rule; Matched λ=0 control; Minimum training budget and seed count

### haiku-skeptic (Reviewer A, skeptic, haiku, 8s)

@Reviewer B is right about the pilot precondition, and I'd make it a hard gate: if baseline verbalization is too rare to suppress, the kill should not run. I'd add a sensitivity check. "Verbalization removed" only means something if the judge catches verbalization when it is present. The criterion needs a positive control: a judge run on traces with planted verbalization, reporting its detection rate, so a judge that misses everything can't make the criterion pass. This matters more than the λ=0 control, because the project's own threat model is that RL teaches the model to evade the monitor. A monitor-evasion result would satisfy "verbalization removed" while still being a failure of the method.

On B's proposed thresholds: the 5% cutoff and 50%-of-λ=0 gap are reasonable placeholders, but they should be justified from the pilot's variance, not picked in advance without it. I'd also drop "seed-level CI excluding zero" for a gap that is only 29 points at n=100 (`docs/journal/2026-10-13.md:42`). At that margin, a CI excluding zero is nearly guaranteed, so it checks nothing useful. The test should be against the λ=0 gap, not against zero.

What would change my mind: a preregistered rule that includes the judge's detection rate on planted traces, a λ=0 run at the same step count, and a seed-aggregation rule.

> Stance: not yet agreed: The week-7 criterion is not operational; it needs a judge with a demonstrated detection rate, a matched λ=0 control at a fixed step count, a pilot-based gap margin, and a seed-aggregation rule.; open: Judge detection rate on planted verbalization (positive control); Numeric verbalization cutoff and its justification from pilot variance; Gap tolerance relative to λ=0, not zero; Fixed minimum step count and per-seed vs aggregate rule; Pilot precondition on baseline verbalization as a hard gate

### haiku-researcher (Reviewer B, researcher, haiku, 8s)

Reviewer A is right about the positive control. A judge that misses planted verbalization would let "verbalization removed" pass for the wrong reason, so I'm adding it to the proposal. I also accept the hard gate on baseline verbalization.

I disagree with dropping the seed-level CI. The problem is seed variance, not sample size. I'd restate the test as a difference from the matched control: the CI on (gap_λ=0 − gap_A) must sit below a margin fixed from pilot variance, not around zero. That covers A's objection that a CI against zero checks nothing at a 29-point gap, and it still catches real erosion.

Reviewer C's point that the base-model comparison precedes organism training (`docs/pilot.md:80`) means that comparison can't serve as the control. The λ=0 run has to start from the same organism checkpoint.

Revised pre-registered rule, which I'd sign:
1. Positive control: judge detection rate on planted verbalization, reported before the pilot.
2. Verbalization ≤ cutoff on 200 held-out CoTs, cutoff set from pilot variance, judged outside the training loop.
3. Gap margin: gap_λ=0 − gap_A has a seed-level CI below a pilot-derived margin.
4. Fixed step count, with a per-seed majority rule.
5. Gate: kill cannot fire unless baseline verbalization is above a pilot-set minimum.

What would change my mind: if the judge's detection rate on planted traces is low, the verbalization term is uninterpretable and the criterion should not run at all.

> Stance: not yet agreed: The week-7 criterion becomes operational only with a judge positive control, a gate on baseline verbalization, and a margin on the gap difference from a same-checkpoint λ=0 run at a fixed step count.; open: Judge detection rate on planted verbalization; Numeric verbalization cutoff and gap margin, both set from pilot variance; Per-seed majority versus mean aggregation rule

### sol-methodologist (Reviewer C, methodologist, gpt-6.1-sol, 28s)

Reviewer B, I accept the revised comparison against a same-checkpoint λ=0 control. But relative retention alone can pass when both arms lose the organism: if both gaps collapse, their difference approaches zero. The pilot already requires an absolute behavior-gap floor (`docs/pilot.md:16`); the post-training rule needs an absolute floor alongside your relative margin.

I also disagree that pilot variance should determine the acceptable loss. Variance informs the measurement budget; the margin should express how much erosion still leaves a scientifically useful organism. The repository distinguishes mean hint coverage from binary hint presence, so that margin must name its metric (`docs/pilot.md:129`).

Finally, “majority rule” should require **the same seeds to satisfy all endpoints jointly**, including task-performance retention, which the pilot explicitly asks to preserve (`docs/pilot.md:113`). Separate majorities for verbalization and behavior could describe different successful seeds.

I would sign after those choices are fixed. Evidence that would change my mind about the absolute floor: a demonstrated λ=0 gap comfortably above that floor at the decision checkpoint.

@Reviewer B

> Stance: not yet agreed: The revised criterion still needs an absolute gap floor, a scientifically justified retention margin, and joint success within seeds.; open: Absolute post-training behavior-gap floor; Retention margin and specified behavior metric; Joint seed-level endpoints including task performance

### haiku-researcher (Reviewer B, researcher, haiku, 6s)

Reviewer C is right on two points, and I concede both. Joint seed-level success is required: the verbalization and gap endpoints, plus task-performance retention, must hold for the same seeds. Separate majorities could pick different successful seeds. The absolute gap floor is also necessary. Without it, a relative margin passes when both arms collapse toward zero.

I still disagree with Reviewer C that the margin should not be informed by pilot variance. Variance cannot tell us how much erosion is scientifically useful, but it can tell us whether a measured difference is distinguishable from noise. So the utility question sets the margin, and the variance decides how many seeds we need to resolve it. We should state both.

For the pre-registration, I would fix these items before the pilot:
- Behavior metric named explicitly: mean hint coverage, not binary presence (`docs/pilot.md:129`).
- Absolute floor, set from the λ=0 gap at the decision checkpoint.
- Relative margin on gap_λ=0 − gap_A, with the seed CI, justified by utility.
- Joint seed-level pass on verbalization, behavior, and task performance.
- Judge positive-control detection rate, with a minimum threshold.

The remaining open values are the numeric floor, the margin, and the verbalization cutoff. I'd like the host to decide how those get set, since they depend on pilot data we don't have yet.

> Stance: not yet agreed: The week-7 criterion can be made operational with a judge positive control, a baseline gate, an absolute gap floor, a λ=0 margin, and joint seed-level pass on all endpoints, but the numeric values are not yet set.; open: Numeric values for the absolute floor, the relative margin, and the verbalization cutoff; Minimum judge detection rate on planted verbalization; Pilot-set baseline verbalization gate; Behavior metric definition (mean coverage versus binary presence)

### haiku-skeptic (Reviewer A, skeptic, haiku, 7s)

Reviewer B is right that the joint seed-level pass and the absolute floor are needed, and I concede both. I also accept the same-checkpoint λ=0 control. Three gaps remain before I would sign.

1. **Planted verbalization is an easy positive control.** Detection on planted traces shows the judge catches overt verbalization. It does not show it catches the paraphrased or implicit eval-awareness that RL would actually leave behind. The control needs a held-out set of naturally produced, minimally verbalized traces, labelled by hand, with detection measured on that set.

2. **Judge independence is unspecified.** If the judge shares a model family with the monitor being trained against, its blind spots may match. The criterion should name the judge and state whether it differs from the training monitor.

3. **The λ=0 floor is circular if the baseline is borderline.** Setting the absolute floor from the λ=0 gap, as Reviewer B proposes, means a weak organism sets a weak bar. The floor needs an external anchor, such as the pilot's entry threshold (`docs/pilot.md:16`), with the λ=0 gap as a check, not the definition.

Evidence that would change my mind: a judge detection rate on natural held-out traces above a stated minimum, and a λ=0 gap that clears the pilot floor at the decision checkpoint.

@Reviewer C

> Stance: not yet agreed: The week-7 criterion is becoming operational, but it still needs a judge validated on natural (not planted) minimally verbalized traces, a judge independent of the training monitor, and a floor anchored outside the λ=0 run.; open: Natural-trace judge validation and minimum detection rate; Judge identity and independence from the training monitor; External anchor for the absolute gap floor; Numeric cutoff, margin, and k-of-n seed rule set from pilot data

## Conclusion

ok cool thanks
