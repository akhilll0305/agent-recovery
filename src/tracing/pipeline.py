"""
The testbed pipeline, running on Gemini.

    User -> Planner -> Researcher -> Coder -> Executor
                          |            |
                       web, db,     code tool,
                       memory       memory

Same shape as docs/02-architecture.md. Every operation is logged as an event
with parents and exposures, every API call's tokens are logged with a
purpose, and the task has a checkable outcome: the Executor runs the
generated script and compares its output to known-correct values from the
database fixture, so task success never depends on text matching.

`src/tracing/fake_pipeline.py` remains the offline no-quota path and is not
affected by anything here.

Run from the repo root, with GEMINI_API_KEY in .env:

    python -m src.tracing.pipeline data/runs/run1.jsonl

One design point worth knowing before reading the code: the Researcher makes
**one API call per finding**, not one call producing several findings. Work
preserved is counted per event (D-012), so replay cost has to be countable
per event too. A single call producing four outputs would make "the cost of
recomputing one finding" undefined, and that number is half of open issue #7.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.config import Settings, load_settings
from src.common.llm import GeminiClient, LLMError, LLMResponse, QuotaExhausted
from src.common.models import Event
from src.tracing.logger import TraceLogger, read_trace
from src.tracing.tools import Tools

DEFAULT_TASK = (
    "Write a single self-contained Python script that parses this project's "
    "sample date strings and prints each one as an ISO date (YYYY-MM-DD), one "
    "per line, in the order given."
)

PLANNER_SYSTEM = (
    "You are the Planner in a four-agent pipeline (Planner, Researcher, Coder, "
    "Executor). Break the user's task into research questions for the "
    "Researcher and write a short brief for the rest of the pipeline. "
    "Answer with JSON only."
)
RESEARCHER_SYSTEM = (
    "You are the Researcher. Answer the question using only the numbered "
    "sources given to you. Be specific and brief: at most four sentences. "
    "If the sources do not answer the question, say so."
)
CODER_SYSTEM = (
    "You are the Coder. You receive the Researcher's findings and must produce "
    "working Python. The execution environment has the standard library only "
    "and no network access."
)


@dataclass
class PipelineResult:
    trace_path: Path
    task_success: bool
    stdout: str
    stderr: str
    tokens: int
    events: int
    throttled_s: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)


class GeminiPipeline:
    """One instance per run. Not reusable: the event ids and the source ids
    belong to a single trace."""

    def __init__(
        self,
        log: TraceLogger,
        client: GeminiClient,
        tools: Tools,
        task: str = DEFAULT_TASK,
    ) -> None:
        self.log = log
        self.client = client
        self.tools = tools
        self.task = task
        # source ids currently in each agent's context -> Event.exposures
        self.context: dict[str, list[str]] = {}
        self._sources: dict[str, Any] = {}

    # --- helpers -----------------------------------------------------------

    def expose(self, agent: str, *source_ids: str) -> None:
        """Put sources into an agent's context. Everything here is an exposure
        and gets recorded on every event that agent logs from now on, whether
        or not the agent uses it. That is the point."""
        seen = self.context.setdefault(agent, [])
        for sid in source_ids:
            if sid not in seen:
                seen.append(sid)

    def _call(
        self,
        agent: str,
        kind: str,
        prompt: str,
        system: str | None = None,
        parents: list[str] | None = None,
        json_output: bool = False,
    ) -> tuple[Event, LLMResponse]:
        """One API call, one event, one usage record. Kept together so a call
        can never be made without its tokens being logged."""
        response = self.client.generate(prompt, system=system, json_output=json_output)
        event = self.log.log_event(
            agent, kind, parents=parents, exposures=self.context.get(agent, [])
        )
        self.log.log_usage(
            "pipeline",
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            output_tokens=response.output_tokens,
            total_tokens=response.total_tokens,
            event_id_=event.id,
            agent_id=agent,
            thoughts_tokens=response.thoughts_tokens,
            attempts=response.attempts,
            latency_s=response.latency_s,
            slept_s=response.slept_s,
        )
        return event, response

    def _source_block(self, ids: list[str]) -> str:
        """Render sources for a prompt, labelled with their trace ids.

        The ids are visible to the agent on purpose: week 2 asks each agent
        which inputs it used (self-report), and it can only answer in ids if
        it saw them. Cheap now, necessary later.
        """
        lines = []
        for sid in ids:
            s = self._sources[sid]
            where = s.metadata.get("url") or s.metadata.get("key") or s.kind
            lines.append(f"[{sid}] ({s.kind}, {where})\n{s.content}")
        return "\n\n".join(lines)

    # --- the run ------------------------------------------------------------

    def run(self) -> PipelineResult:
        def remember(source):
            self._sources[source.id] = source
            return source

        # --- user ----------------------------------------------------------
        user_event = self.log.log_event("user", "message", parents=[])
        task_source = remember(
            self.log.log_source("user_input", self.task, origin_event=user_event.id)
        )
        self.expose("planner", task_source.id)

        # --- planner ---------------------------------------------------------
        plan_event, plan_response = self._call(
            "planner",
            "plan",
            prompt=(
                f"Task:\n{self.task}\n\n"
                "Reply with JSON: {\"brief\": str, \"questions\": [str, str, str]}. "
                "Exactly three research questions, each answerable from "
                "documentation about parsing dates in Python."
            ),
            system=PLANNER_SYSTEM,
            parents=[user_event.id],
            json_output=True,
        )
        plan = plan_response.json()
        questions = [str(q) for q in plan.get("questions", [])][:3] or [self.task]
        brief = str(plan.get("brief", "")).strip() or self.task

        handoff = self.log.log_event("planner", "message", parents=[plan_event.id])
        brief_source = remember(
            self.log.log_source(
                "agent_message",
                brief,
                origin_event=handoff.id,
                derived_from=plan_event.id,
            )
        )
        self.expose("researcher", brief_source.id)

        # --- researcher: tools -------------------------------------------------
        self.log.log_event(
            "researcher", "tool_call", parents=[handoff.id], tool_id="web"
        )
        web_response = self.log.log_event("researcher", "tool_response", tool_id="web")
        for page in self.tools.web_search(" ".join(questions)):
            source = remember(
                self.log.log_source(
                    "web",
                    page.content,
                    origin_event=web_response.id,
                    metadata={"url": page.url, "title": page.title},
                )
            )
            self.expose("researcher", source.id)

        self.log.log_event("researcher", "tool_call", tool_id="db")
        db_response = self.log.log_event("researcher", "tool_response", tool_id="db")
        for key in ("environment/installed_packages", "task/date_samples", "task/day_first"):
            source = remember(
                self.log.log_source(
                    "database",
                    json.dumps(self.tools.db_lookup(key)),
                    origin_event=db_response.id,
                    metadata={"key": key},
                )
            )
            self.expose("researcher", source.id)

        # --- researcher: one call per finding ------------------------------------
        findings: list[tuple[Event, str]] = []
        exposed = self.context["researcher"]
        for question in questions:
            event, response = self._call(
                "researcher",
                "agent_output",
                prompt=(
                    f"Question: {question}\n\nSources:\n{self._source_block(exposed)}"
                ),
                system=RESEARCHER_SYSTEM,
                parents=[db_response.id],
            )
            findings.append((event, response.text.strip()))

        to_coder = self.log.log_event(
            "researcher", "message", parents=[e.id for e, _ in findings]
        )
        for event, text in findings:
            source = remember(
                self.log.log_source(
                    "agent_message",
                    text,
                    origin_event=to_coder.id,
                    derived_from=event.id,
                )
            )
            self.expose("coder", source.id)

        # --- coder ----------------------------------------------------------------
        memory_event = self.log.log_event("coder", "memory_read", parents=[to_coder.id])
        for key in ("style/preferences", "style/output"):
            value = self.tools.memory_read(key)
            if value is None:
                continue
            source = remember(
                self.log.log_source(
                    "memory",
                    value,
                    origin_event=memory_event.id,
                    metadata={"key": key},
                )
            )
            self.expose("coder", source.id)

        samples = self.tools.db_lookup("task/date_samples") or []
        coder_sources = self.context["coder"]

        decision_event, decision_response = self._call(
            "coder",
            "decision",
            prompt=(
                f"Task:\n{self.task}\n\nDate samples: {json.dumps(samples)}\n\n"
                f"Inputs:\n{self._source_block(coder_sources)}\n\n"
                "Decide the approach in at most three sentences. State which "
                "library you will use and why."
            ),
            system=CODER_SYSTEM,
            parents=[memory_event.id],
        )

        code_event, code_response = self._call(
            "coder",
            "agent_output",
            prompt=(
                f"Task:\n{self.task}\n\nDate samples: {json.dumps(samples)}\n\n"
                f"Approach you chose:\n{decision_response.text.strip()}\n\n"
                f"Inputs:\n{self._source_block(coder_sources)}\n\n"
                "Reply with the complete Python script and nothing else. No "
                "markdown fences, no commentary. The script must hardcode the "
                "samples and print one ISO date per line."
            ),
            system=CODER_SYSTEM,
            parents=[decision_event.id],
        )
        code = _strip_fences(code_response.text)

        self.log.log_event("coder", "memory_write", parents=[code_event.id])
        self.tools.memory_write("last_run/approach", decision_response.text.strip())

        # --- executor ---------------------------------------------------------------
        self.log.log_event(
            "executor", "tool_call", parents=[code_event.id], tool_id="python"
        )
        result = self.tools.run_python(code)
        exec_response = self.log.log_event(
            "executor", "tool_response", tool_id="python"
        )

        # Checkable outcome: compare against known-correct values, no LLM judge.
        expected = [str(v) for v in (self.tools.db_lookup("task/expected_iso") or [])]
        produced = [ln.strip() for ln in result["stdout"].splitlines() if ln.strip()]
        success = bool(expected) and produced == expected
        self.log.log_event("executor", "agent_output", parents=[exec_response.id])

        return PipelineResult(
            trace_path=self.log.path,
            task_success=success,
            stdout=result["stdout"],
            stderr=result["stderr"],
            tokens=self.client.total_tokens,
            events=len(self.log.events),
            throttled_s=getattr(self.client, "throttled_s", 0.0),
            detail={
                "expected": expected,
                "produced": produced,
                "returncode": result["returncode"],
                "code": code,
            },
        )


def _strip_fences(text: str) -> str:
    """Models add ```python fences even when told not to."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    text = text.split("\n", 1)[-1]
    return text.rsplit("```", 1)[0].strip()


def run_pipeline(
    path: str | Path,
    task: str = DEFAULT_TASK,
    settings: Settings | None = None,
) -> PipelineResult:
    settings = settings or load_settings()
    tools = Tools.from_fixtures(memory_path=Path(path).with_suffix(".memory.json"))
    client = GeminiClient(settings)
    meta = {"pipeline": "gemini", "task": task, **settings.fingerprint()}
    with TraceLogger(path, meta=meta) as log:
        return GeminiPipeline(log, client, tools, task=task).run()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/runs/gemini.jsonl"
    try:
        outcome = run_pipeline(target)
    except (LLMError, RuntimeError) as exc:
        # A run that dies mid-way still leaves a valid partial trace: the
        # logger flushes every record as it is written (D-008). Say where it is and
        # how far it got, instead of a stack trace.
        print(f"run failed: {exc}")
        print()
        partial = Path(target)
        if partial.exists():
            trace = read_trace(partial)
            spent = sum(u.total_tokens for u in trace.usage)
            print(f"partial trace kept at {partial}")
            print(f"  {len(trace.events)} events, {len(trace.usage)} calls, {spent} tokens spent")
            if trace.events:
                last = trace.events[-1]
                print(f"  stopped after {last.id} ({last.agent_id}/{last.kind})")
        print()
        if isinstance(exc, QuotaExhausted):
            print("The per-day quota is spent. Nothing to tune: the window has")
            print("to reset, or the project needs a paid tier. See D-017 --")
            print("one run of this pipeline costs 6 requests.")
        else:
            print("If this was a rate limit, check the ceiling with one call:")
            print("  python -m src.common.llm --smoke")
            print("and lower GEMINI_REQUESTS_PER_MINUTE in .env if it persists.")
        raise SystemExit(1)
    trace = read_trace(outcome.trace_path)
    trace.validate()

    print(f"trace        {outcome.trace_path}")
    print(f"events       {outcome.events}   sources {len(trace.sources)}")
    print(f"tokens       {outcome.tokens}  by purpose {trace.tokens_by_purpose()}")
    print(f"throttled    {outcome.throttled_s:.1f}s waiting on our own rate limiter")
    print(f"task success {outcome.task_success}")
    if not outcome.task_success:
        print(f"  expected {outcome.detail['expected']}")
        print(f"  produced {outcome.detail['produced']}")
        if outcome.stderr:
            print(f"  stderr   {outcome.stderr.strip()[:400]}")
    print()
    print("exposure vs influence is empty until src/provenance/ runs;")
    print("exposures per output event are already recorded:")
    for e in trace.events:
        if e.kind in ("agent_output", "decision") and e.exposures:
            print(f"  {e.id} {e.agent_id:<10} exposed to {len(e.exposures)} sources")
