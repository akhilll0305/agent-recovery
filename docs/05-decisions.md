# 05 — Decisions

Running log. Append, never rewrite. Every entry: what we chose, what we
rejected, why. In week 4 the paper's method section gets written from this
file, and you will not remember the reasons otherwise.

Format:

```
## D-004  LLM API and model
Date: 26-08-2026
Decided by: all three
Choice: Gemini API for all agents in the testbed.
Reason: available to us at low cost. Model tier TBD.
```

---

## D-001  Scope: full pipeline, shallow depth, one deep result
Date: TODO
Decided by: all three
Choice: build every component thin and connected end to end; evaluate the
exposure-vs-influence claim deeply.
Rejected: cutting to a single component; building every component deeply.
Reason: a system paper needs the whole pipeline to exist, but one month
cannot support depth everywhere. One measured claim is enough for
acceptance.

---

## D-002  Terminology: "small safe recovery set", not "minimum"
Date: TODO
Decided by: all three
Choice: avoid claiming minimality anywhere in code, docs, or paper.
Rejected: "minimum recovery set".
Reason: minimality is not provable when influence edges are estimates.
Claim only what is measured.

---

## D-003  Definition of "recovery succeeded"
Date: TODO
Decided by: TODO
Choice: TODO — decide in week 1, do not defer
Rejected: exact output matching
Reason: replay is non-deterministic; identical state is not achievable.
Candidates to pick from: (a) task-level success on a checkable outcome,
(b) semantic equivalence judged by an LLM with a fixed rubric, (c) both,
reporting agreement between them.

---

## D-004  LLM API and model
Date: 26-08-2026
Decided by: all three
Choice: Gemini, `gemini-3.6-flash`, temperature 0. Model name is read from
`GEMINI_MODEL` in `.env` and recorded in every trace header, so a run's
numbers can always be tied to the model that produced them.
Amended 26-08-2026, same day: the original choice was `gemini-2.5-flash`,
which returns 404 for API keys created now -- the API's own error names
`models/gemini-3.6-flash` as the replacement. Recorded rather than quietly
edited because it is a finding in its own right: a one-month project can have
its model retired underneath it mid-schedule. Any run traced before this
amendment carries the old model name in its header and is not comparable with
runs after it. Consequence for docs/04 run hygiene: if we have already
collected numbers on a scenario, all methods on that scenario must be re-run
on the new model, not just the ones we happen to re-run next.
Reason: Flash tier keeps the budget survivable. Counterfactual replay
multiplies call count -- one flagged source on one event is one extra call,
and docs/04 asks for three repeats across ~30 runs per scenario -- so the
per-call price is the constraint that matters, not the per-call quality.

---

## D-005  Target conference and deadline
Date: TODO
Decided by: TODO
Choice: TODO
Reason: TODO — page count decides how much evaluation is required.

---

## D-006  Shared data models frozen
Date: TODO
Decided by: all three
Choice: `src/common/` models agreed in week 1, then changed only by
agreement of all three.
Reason: all three subsystems depend on them; a mid-project change breaks
everyone at once and burns days.

---

<!-- append new decisions below -->

## D-007  Automatic parent links are same-agent only
Date: 26-08-2026
Decided by: proposed with the trace layer, needs group sign-off
Choice: `TraceLogger.log_event(parents=None)` links the new event to the
previous event logged by the same agent. Cross-agent links (Planner ->
Researcher) must be passed explicitly; `parents=[]` marks a root event.
Rejected: linking to the previous event overall (whichever agent produced it).
Reason: chronological adjacency is not derivation. Auto-linking across
agents would manufacture edges that look like data flow, and contamination
that propagates along a manufactured edge is exactly the baseline error we
claim to avoid. Guessing wrongly here would flatter the baseline and could
also hide a real edge.

---

## D-008  Trace file format: one JSONL file per run, tagged records
Date: 26-08-2026
Decided by: proposed with the trace layer, needs group sign-off
Choice: one `.jsonl` per run under `data/runs/`. Each line is a JSON object
tagged with `"record"`: `meta`, `source`, `event`, or `influence`. Lines are
flushed as written.
Rejected: separate files per record type; a single JSON document written at
the end; SQLite.
Reason: append-only means a crashed or attacked run still leaves a readable
trace, and one file per run keeps a run self-contained for `data/runs/`
hygiene (docs/04). Both graphs rebuild from this one file. Revisit only if
trace size becomes a measured problem (open issue #8).

---

## D-009  Source content is stored inline; event content is stored by reference
Date: 26-08-2026
Decided by: proposed with the trace layer, needs group sign-off
Choice: `Source.content` holds the text. `Event.inputs_ref` / `output_ref`
hold opaque content-store keys, not text.
Rejected: inlining event content too; referencing source content too.
Reason: matches the storage policy in docs/02 — source content is always
needed for counterfactual replay, event content is only needed at
checkpoints. The content store itself is not built yet; refs are opaque
strings until it is.

---

## D-010  No content store yet; refs stay opaque
Date: 26-08-2026
Decided by: all three
Choice: `Event.inputs_ref` and `Event.output_ref` stay opaque strings. No
content store is built until selective replay actually needs event content.
Rejected: building the content store in week 1 alongside the trace layer.
Reason: nothing in weeks 1-2 reads event content. The graphs are built from
metadata, and counterfactual replay reads `Source.content`, which is stored
inline (D-009). Building a store now would be guessing at the interface
replay wants. The field names are already in the frozen schema, so adding
the store later does not change the models.
Consequence: `data/runs/*.jsonl` is not yet enough to replay a run. It is
enough to rebuild both graphs, which is the week-1 exit test.

---

## D-011  Exposure is a field on Event, recorded at logging time
Date: 26-08-2026
Decided by: all three
Choice: `Event.exposures` holds the source ids present in the agent's
context for that operation. Written by whoever runs the agent, at the moment
the call is made.
Rejected: a separate exposure record; deriving exposure inside
`src/provenance/` after the run.
Reason: exposure is an observation about the prompt, not an analysis result,
and it cannot be reconstructed once the run is over. It also is not a
provenance detail -- the exposure/influence gap *is* the paper's claim, so it
belongs in the trace next to the operation it describes. Keeping it on Event
means a trace file alone contains both sets, and figure 2 (exposure graph vs
influence graph, docs/04) can be drawn from one file.

---

## D-012  Work is counted in events, never in sources
Date: 26-08-2026
Decided by: all three
Choice: the unit for every metric in docs/04-experiments.md is the **event**.
An agent output appears twice in a trace -- as the event that produced it
(e0006) and as the source a later agent consumed (S6). Those are one piece of
work. The source carries `Source.derived_from = "e0006"` and is never counted.
`Trace.work_units()` is the single definition; metrics start there rather than
each deciding for itself.
Rejected: counting sources; counting both; counting only agent_output events.
Reason: "work preserved" has to mean recomputation avoided, and recomputation
happens per event. A source derived from an event costs nothing to reproduce
once that event exists, so counting it would inflate work preserved -- for us
*and* for the baselines, but unevenly, because our method preserves more of
exactly the derived kind. That is a silent way to manufacture our own result.
`Trace.validate()` now rejects two sources wrapping one event.
Note: `derived_from` is also the edge contamination crosses between agents.
If e0006 is contaminated then S6 is contaminated, and any event S6 influences
is contaminated. Without the field that link lives only in the call graph,
which is exactly what we refuse to propagate along.
Note: the same rule applies to tokens. Replay cost is charged to the event
that is re-run; wrapping its output for a consumer costs nothing extra.

---

## D-013  Gemini over stdlib HTTP, no SDK dependency
Date: 26-08-2026
Decided by: proposed with the pipeline, needs group sign-off
Choice: `src/common/llm.py` posts to the `generateContent` REST endpoint with
`urllib.request`. No `google-genai`, no `requests`, no `python-dotenv`.
Rejected: the `google-genai` SDK; the deprecated `google-generativeai`
package that happens to be installed on one of our machines.
Reason: the ground rules say ask before adding a dependency, and this needs
about sixty lines. It also keeps retry, timeout and token extraction in code
we can read, which matters because rate-limit behaviour under counterfactual
replay is something we have to measure and report, not just survive.
Revisit if we need streaming, function calling, or multimodal input; the
transport is one method (`GeminiClient._post`) and swapping it is contained.
Note: `google-generativeai` is deprecated upstream. If we ever do adopt an
SDK it must be `google-genai`.

---

## D-014  Web and database tools read fixtures, not the live internet
Date: 26-08-2026
Decided by: proposed with the pipeline, needs group sign-off
Choice: the web tool ranks a canned corpus in `src/tracing/fixtures/`; the
database tool reads a fixture dict. `src/eval/` injects poisoned pages by
passing a modified corpus to `Tools`, without touching tool code.
Rejected: a real search API.
Reason: two of our claims depend on it. Ground truth is known by
construction only if we author what the tools return (open issue #3), and
counterfactual replay only means anything if re-running an event without one
source reproduces everything else exactly -- a live search result that
changes between the original call and the replay would silently look like
influence. Reproducibility here is a requirement, not a convenience.
Consequence: state plainly in the paper that tool outputs are a fixed corpus.
A reviewer will otherwise assume live retrieval and ask about drift.

---

## D-015  Thinking minimised (thinkingLevel "minimal")
Date: 26-08-2026
Decided by: proposed with the pipeline, needs group sign-off
Choice: every call sets `thinkingConfig.thinkingLevel = "minimal"`. The
setting is recorded in the trace header, and `thoughts_tokens` is recorded
per call whatever the setting says.
Rejected: leaving the Flash model's default thinking on.
Reason: thinking tokens are billed and would inflate the cost metric with
work that is invisible in the trace, and variable-length internal reasoning
is a second source of run-to-run variation on top of the one open issue #2
already forces us to handle. `thoughts_tokens` is still recorded per call, so
if we turn thinking back on for a scenario the cost stays separable.
Amended 26-08-2026, same day: the mechanism changed, the decision did not.
`thinkingBudget: 0` is what gemini-2.5-flash accepted; gemini-3.6-flash
rejects it with 400 INVALID_ARGUMENT, which is what broke the first live run
after the model change (D-004). Bisecting the request body one field at a
time found `thinkingBudget` to be the only offending field -- JSON response
mode is fine. This model takes `thinkingLevel` instead, one of minimal, low,
high. "minimal" returned 0 thought tokens on both a trivial prompt and a
realistic Researcher prompt, so the intent of this decision survives intact.
Measured, for the paper: with thinking left at its default, "Reply with the
word ok." cost 98 tokens of which 90 were thoughts. Roughly 92% of the spend
on that call would have been invisible in the trace. That is the size of the
distortion this decision avoids, and it is worth one line in the cost section.
Consequence if a future model will not go to zero: the cost metric would
carry tokens that appear nowhere in the event graph. It stays *separable*
because `UsageRecord.thoughts_tokens` is recorded per call regardless, so the
honest move then is to report thought tokens as their own column rather than
fold them into the totals. Do not quietly leave them in.
`python -m src.common.llm --smoke` now checks the request contract with one
call, so the next model change costs one call to diagnose, not a whole run.

---

## D-016  One API call per Researcher finding
Date: 26-08-2026
Decided by: proposed with the pipeline, needs group sign-off
Choice: the Researcher answers each planned question in its own call,
producing one `agent_output` event per finding.
Rejected: one call returning all findings as a list.
Reason: work preserved is counted per event (D-012), so replay cost has to be
countable per event too. If one call produced four findings, "the cost of
recomputing one finding" would be undefined, and that number is half of open
issue #7. It also makes selective replay real rather than notional: replaying
one contaminated finding is one call, not a re-run of all four.
Cost: more prompt tokens overall, since the sources are re-sent per question.
That overhead is real and belongs in the cost table rather than being hidden.

---

## D-017  Free-tier quota is 20 requests per day, and the plan does not fit in it
Date: 26-08-2026
Decided by: NOT DECIDED -- needs all three, this week
Choice: open. The measurement is not open, and it is the reason this needs a
decision now rather than in week 3.

Measured against the live API on 26-08-2026:

```
quotaId    GenerateRequestsPerDayPerProjectPerModel-FreeTier
quotaValue 20
model      gemini-3.6-flash
```

Per **day**, per model, per project -- not per minute. Rejected requests
appear to count against it, so a burst of 429s makes it worse rather than
better.

The arithmetic against docs/04:

```
one pipeline run                       6 requests  (planner 1, researcher 3, coder 2)
  -> 3 runs per day, absolute ceiling
30 runs x 3 scenarios                540 requests  original runs only
B0 full restart baseline             540 requests  it re-runs everything
counterfactual replay                 1 request per flagged source per event,
                                      x3 repeats for non-determinism (docs/04)
```

Even before counterfactual checks -- the thing the paper is actually about --
that is well over 1000 requests, or 50+ days of free-tier quota. We have one
month, and week 2 is where the call count starts multiplying.

Options, for the group to choose between:
1. Enable billing on the API project. Costs money; makes the plan as written
   feasible. Flash tier pricing is low, and D-015 already removed thinking
   tokens, which were 92% of spend on a trivial call.
2. Cut the experiment: fewer runs per scenario, fewer scenarios, or
   counterfactual checks on a sampled subset with the sampling reported.
   Cheaper, and honest if we say so, but it weakens the headline numbers and
   open issue #3 already wants ~30 labelled runs per scenario.
3. Spread runs across several API projects or keys. Works, but it is quota
   evasion, it makes runs non-comparable across keys, and it is not something
   to put in a paper.

Recommendation: option 1, with option 2's sampling as the fallback if the
budget is refused. Whatever is chosen, write the token and request counts into
the paper -- open issue #7 asks for cost numbers, and "the method needed N
requests" is exactly the kind of number a reviewer wants.

Consequence for the code, already applied: the client now separates the
per-minute limit (retryable, honours the server's suggested delay) from the
per-day limit (fatal, `QuotaExhausted`). Backing off against a daily cap wasted
152 seconds and several requests before this.

---

## D-018  Checkpoint payloads live in a sidecar file, not in the trace
Date: 26-08-2026
Decided by: proposed with the trace layer, needs group sign-off
Choice: two files per run.

```
data/runs/run1.jsonl              events, sources, influence, usage
data/runs/run1.checkpoints.jsonl  agent state and memory snapshots
```

Rejected: checkpoints as another record type inside the trace; one directory
of numbered checkpoint files.
Reason: it is the storage policy from docs/02-architecture.md made literal.
Metadata is always kept and is small; full agent state is "the expensive
part" and is kept only at checkpoints. Keeping them in one file would mean
every tool that reads a trace pays to parse state it does not want, and the
overhead measurement open issue #8 asks for would need the two separated
anyway. `overhead()` reports the split directly.
Measured on an 18-event run: trace 11.1 kB, checkpoints 4.0 kB, so
checkpoints are 26% of stored bytes at the v1 policy of one per agent
boundary. That is the number to re-measure on real runs and report.
Consequence: D-008's "one file per run" now reads "one trace file per run".
A run is self-contained in a directory, not in a file. Both graphs still
rebuild from the trace file alone, which is what the week-1 exit test asks.

---

## D-019  Record/replay cassettes for development, never for results
Date: 26-08-2026
Decided by: proposed with the pipeline, needs group sign-off
Choice: `src/common/cassette.py` records live responses to a JSONL cassette
and replays them offline. Cassettes are committed. A replayed run writes
`"cassette": "replay"` into its trace header.
Rejected: everyone spending their own quota to see a real trace; mocking
responses by hand.
Reason: 20 requests a day across three people (D-017) does not allow each of
us a real trace to develop against. One recorded run replays indefinitely for
free, and it is real model output rather than something we invented, so
provenance and recovery are built against text the model actually produced.

**The rule, and it is not negotiable:** no number from a replayed run goes in
the paper as a measurement. Token counts replay faithfully because they are
the counts the model returned, but the request did not happen, and
`latency_s` and `attempts` are recorded values that describe the original
call. Every table in docs/04 comes from runs with no `cassette` key in the
header. The header marking exists so that this is checkable rather than
remembered.
Note: replay needs no API key at all, so a teammate can clone the repo and
work immediately. A cassette miss raises rather than falling through to a
live call -- silently spending the day's quota on a changed prompt is exactly
the failure this is meant to prevent.

---
