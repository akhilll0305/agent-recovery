"""
Gemini client.

Stdlib HTTP only (D-013). One POST to generateContent, retried on the status
codes that mean "later, not never", with token counts pulled off every
response.

Two things this client is strict about, because the paper depends on them:

  * every call returns its token counts, and the caller must say what the
    call was *for* (UsagePurpose). Cost split by purpose is the whole of
    open issue #7.
  * temperature and thinking level come from Settings and are recorded in
    the trace header, so a run's numbers can be tied to its configuration.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from src.common.config import Settings
from src.common.retry import Retryable, RetryPolicy, with_retry

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# Status codes worth another attempt: rate limit, and the transient 5xx family.
RETRY_STATUS = {408, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """A call that will not get better by retrying (bad key, bad request,
    safety block). Carries the server's message: hiding it costs hours."""


@dataclass
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int
    output_tokens: int
    thoughts_tokens: int
    total_tokens: int
    attempts: int
    latency_s: float
    slept_s: float
    finish_reason: str | None = None

    def json(self) -> Any:
        """Parse the response as JSON, tolerating ```json fences."""
        text = self.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"expected JSON, got: {self.text[:300]}") from exc


class GeminiClient:
    """One client per run. Keeps a running token total for the run summary."""

    def __init__(self, settings: Settings, policy: RetryPolicy | None = None) -> None:
        self.settings = settings
        self.policy = policy or RetryPolicy(max_attempts=settings.max_attempts)
        self.calls = 0
        self.total_tokens = 0

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        json_output: bool = False,
        temperature: float | None = None,
    ) -> LLMResponse:
        """One turn, no history. The pipeline passes whole context explicitly
        so that a counterfactual replay can remove one source and reproduce
        the call exactly -- hidden conversation state would make that
        impossible."""
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": (
                    self.settings.temperature if temperature is None else temperature
                ),
                "maxOutputTokens": self.settings.max_output_tokens,
                "thinkingConfig": {"thinkingLevel": self.settings.thinking_level},
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_output:
            body["generationConfig"]["responseMimeType"] = "application/json"

        started = time.time()
        payload, attempt = with_retry(lambda: self._post(body), self.policy)
        latency = time.time() - started

        usage = payload.get("usageMetadata", {})
        candidates = payload.get("candidates") or []
        if not candidates:
            raise LLMError(f"no candidates in response: {json.dumps(payload)[:300]}")
        candidate = candidates[0]
        parts = candidate.get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        finish = candidate.get("finishReason")
        if not text and finish and finish != "STOP":
            # MAX_TOKENS with thinking on, or a safety block. Both are silent
            # empty strings otherwise, and an empty agent output would look
            # like a legitimate result in the trace.
            raise LLMError(f"empty response, finishReason={finish}")

        self.calls += 1
        total = int(usage.get("totalTokenCount", 0))
        self.total_tokens += total
        return LLMResponse(
            text=text,
            model=self.settings.model,
            prompt_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            thoughts_tokens=int(usage.get("thoughtsTokenCount", 0)),
            total_tokens=total,
            attempts=attempt.attempts,
            latency_s=latency,
            slept_s=attempt.slept_s,
            finish_reason=finish,
        )

    # --- transport ---------------------------------------------------------

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{API_ROOT}/{self.settings.model}:generateContent"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.settings.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_s) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            if exc.code in RETRY_STATUS:
                raise Retryable(
                    f"HTTP {exc.code}: {detail}",
                    retry_after=_retry_after(exc),
                ) from exc
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            # DNS, connection reset, timeout. Transient by nature.
            raise Retryable(f"network error: {exc.reason}") from exc


def _retry_after(exc: urllib.error.HTTPError) -> float | None:
    """Gemini sends Retry-After on 429 as seconds. Honour it over our backoff."""
    raw = exc.headers.get("Retry-After") if exc.headers else None
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None  # HTTP-date form; our own backoff will cover it


def smoke() -> int:
    """One minimal live call, to check the API contract without a full run.

        python -m src.common.llm --smoke

    Exists because a model change breaks the request body, not the pipeline,
    and finding that out costs a whole run's tokens otherwise. Prints the
    request body it sent (never the key) so a 400 can be read against it.
    """
    from src.common.config import load_settings

    settings = load_settings()
    client = GeminiClient(settings)
    print(f"model    {settings.model}")
    print(f"settings {settings.fingerprint()}")

    sent: dict[str, Any] = {}
    original = client._post

    def capture(body: dict[str, Any]) -> dict[str, Any]:
        sent.clear()
        sent.update(body)
        return original(body)

    client._post = capture  # type: ignore[method-assign]

    try:
        response = client.generate("Reply with the word ok.", system="You are terse.")
    except Exception as exc:
        print("\nrequest body:")
        print(json.dumps(sent, indent=2))
        print(f"\nFAILED: {exc}")
        return 1

    print(f"\ntext     {response.text.strip()[:60]!r}")
    print(f"finish   {response.finish_reason}")
    print(
        f"tokens   prompt={response.prompt_tokens} output={response.output_tokens} "
        f"thoughts={response.thoughts_tokens} total={response.total_tokens}"
    )
    print(f"call     attempts={response.attempts} latency={response.latency_s:.2f}s")
    if response.thoughts_tokens:
        # Not fatal, but it means the cost metric carries tokens that do not
        # appear anywhere in the trace. Worth knowing before a batch of runs.
        print(
            f"\nWARNING: {response.thoughts_tokens} thought tokens were billed at "
            f"thinking_level={settings.thinking_level!r}. See D-015."
        )
    print("\nOK")
    return 0


if __name__ == "__main__":
    import sys

    if "--smoke" in sys.argv:
        raise SystemExit(smoke())
    print("usage: python -m src.common.llm --smoke")
    raise SystemExit(2)
