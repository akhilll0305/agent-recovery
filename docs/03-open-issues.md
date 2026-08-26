# 03 — Open issues

Known weak points. Read before proposing a design. Each one is something a
reviewer can attack, so each needs an answer in the paper.

---

## 1. We cannot see inside an LLM call

All four research results sit in one prompt. There is no reliable way to
prove one of them had zero effect. Attention weights are not causation.
Self-reported reasoning is sometimes confidently wrong.

**Our answer:** counterfactual replay. Remove the source, re-run, compare.
Self-report is a cheap first pass; counterfactual is the evidence. State
plainly in the paper that this is empirical, not a proof.

**Status:** core method. Must work by end of week 2.

---

## 2. Replay is non-deterministic

The same prompt gives different wording each time. So "compare outputs"
cannot be string equality, and "recovery succeeded" cannot mean
"identical state restored".

**Our answer:** compare at the semantic / behavioural level (does the code
do the same thing, does the task still succeed). Temperature 0, fixed
seeds where the API allows, and repeat each comparison 3 times so one
noisy sample cannot flip a verdict.

**Status:** must be decided in week 1 and written into `05-decisions.md`.

---

## 3. Ground truth is expensive

To claim accuracy we need to know the true contaminated set for each run.
Nobody provides that.

**Our answer:** we build the attacks, so we know exactly what was
poisoned. Hand-label around 30 runs per scenario. Small and honest beats
large and guessed. Two people label independently on a subset and report
agreement.

**Status:** start labelling in week 2, not week 4.

---

## 4. Contamination can hide

A poisoned source might not appear in the output but still steer a
decision — the Coder picks library X instead of Y because of it. Our check
sees no overlap and calls the event clean. This is a **false clean**, the
dangerous direction of error.

**Our answer:** track influence on decisions and plans, not only on final
text. And measure how often we are wrong — the unsafe preservation rate —
and report it prominently even if it is unflattering.

**Status:** open. Partially addressed by treating `decision` as its own
event kind.

---

## 5. "Minimum recovery set" is not provable

Minimality cannot be proved when the influence edges are themselves
estimates.

**Our answer:** stop using the word minimum. Claim "a small, safe recovery
set", show it empirically beats the baselines. Claim only what is measured.

**Status:** terminology fix. Enforce it in code names too.

---

## 6. Poisoned memory outlives the workflow

A bad entry written to shared memory can be read by other agents later,
including in a different run. Our event graph covers one workflow.

**Our answer:** every memory write is a tracked event with provenance;
invalidation rolls back the entry. Cross-session memory is declared out of
scope and named in Future work.

**Status:** in scope for single-session, out of scope across sessions.

---

## 7. The check may cost more than the rerun

If verifying that the Coder is clean costs as much as just re-running the
Coder, the whole idea collapses.

**Our answer:** measure tokens spent on analysis against tokens saved by
avoiding recomputation, and report the ratio. Then be selective: only run
counterfactual checks when the event is expensive to redo. The break-even
point is itself an interesting result.

**Status:** highest-risk issue after #1. Instrument token counts from day one.

---

## 8. Storage overhead

Fine-grained tracing means logging a lot. We claim not to store
everything, so we must say exactly what we drop.

**Our answer:** metadata always, content at checkpoints only, no
token-level detail. Report overhead as a percentage of total workflow
tokens and bytes.

**Status:** measure in week 4.

---

## 9. Novelty question

Provenance tracking and taint analysis are decades old in OS and database
security. A reviewer will ask what is new here.

**Our answer:** taint in an LLM prompt is *probabilistic*, not binary —
classical taint analysis assumes a deterministic program where data flow
is visible. We handle a system where influence must be estimated, and we
estimate it with counterfactual replay. Lead with that framing, not with
"we built a provenance graph".

**Status:** framing. Affects the intro and related-work sections.

---

## Which two decide acceptance

**#1** (can we actually establish non-influence) and **#7** (is it cheaper
than just re-running). If those two have solid numbers, the rest are
manageable.
