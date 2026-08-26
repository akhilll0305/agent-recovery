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

## D-015  Thinking disabled (thinkingBudget 0)
Date: 26-08-2026
Decided by: proposed with the pipeline, needs group sign-off
Choice: every call sets `thinkingConfig.thinkingBudget = 0`. The setting is
recorded in the trace header.
Rejected: leaving the Flash model's default thinking on.
Reason: thinking tokens are billed and would inflate the cost metric with
work that is invisible in the trace, and variable-length internal reasoning
is a second source of run-to-run variation on top of the one open issue #2
already forces us to handle. `thoughts_tokens` is still recorded per call, so
if we turn thinking back on for a scenario the cost stays separable.

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
