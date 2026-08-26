"""
Settings, read from .env.

No dependency on python-dotenv: the parser below is fifteen lines and the
ground rules say ask before adding a dependency (D-013).

Precedence: real environment variables win over .env, so a shell export can
override a committed default without editing files. .env is gitignored; see
.env.example for the keys.
"""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENV_PATH = ".env"

# Flash tier, per docs/01-scope.md (Gemini) and the budget note in D-004.
DEFAULT_MODEL = "gemini-2.5-flash"


class MissingAPIKey(RuntimeError):
    """Raised with instructions rather than a bare KeyError, because this is
    the first thing that goes wrong on a new machine."""


@dataclass(frozen=True)
class Settings:
    """Everything the LLM client needs. Frozen: a run must not change model
    or temperature halfway through, or the trace stops being reproducible."""

    api_key: str
    model: str = DEFAULT_MODEL
    temperature: float = 0.0
    # gemini-2.5-flash thinks by default. Thinking tokens are billed and are a
    # second source of run-to-run variation, so the testbed turns it off (0)
    # and records the setting. See D-015.
    thinking_budget: int = 0
    max_output_tokens: int = 2048
    timeout_s: float = 60.0
    max_attempts: int = 5

    def fingerprint(self) -> dict[str, object]:
        """Goes in the trace header. docs/04 run hygiene: log model, version,
        temperature, date. Never includes the api key."""
        return {
            "model": self.model,
            "temperature": self.temperature,
            "thinking_budget": self.thinking_budget,
            "max_output_tokens": self.max_output_tokens,
        }


def read_env_file(path: str | Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    """Parse KEY=VALUE lines. Ignores blanks, # comments, and a leading
    'export '. Strips one layer of matching quotes. Missing file -> {}."""
    path = Path(path)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_settings(path: str | Path = DEFAULT_ENV_PATH, **overrides: object) -> Settings:
    """Build Settings from .env plus the real environment.

    Keyword overrides win over both, for tests and for the counterfactual
    runner, which needs the same model at a different temperature.
    """
    values = read_env_file(path)
    values.update({k: v for k, v in os.environ.items() if k.startswith("GEMINI_")})

    api_key = str(overrides.pop("api_key", "") or values.get("GEMINI_API_KEY", ""))
    if not api_key:
        raise MissingAPIKey(
            "GEMINI_API_KEY not found. Copy .env.example to .env and put your "
            "key in it, or export GEMINI_API_KEY. The key is never committed: "
            ".env is gitignored."
        )

    def get(name: str, cast, default):
        if name in overrides:
            return cast(overrides.pop(name))
        raw = values.get("GEMINI_" + name.upper())
        return cast(raw) if raw not in (None, "") else default

    settings = Settings(
        api_key=api_key,
        model=get("model", str, DEFAULT_MODEL),
        temperature=get("temperature", float, 0.0),
        thinking_budget=get("thinking_budget", int, 0),
        max_output_tokens=get("max_output_tokens", int, 2048),
        timeout_s=get("timeout_s", float, 60.0),
        max_attempts=get("max_attempts", int, 5),
    )
    if overrides:
        raise TypeError(f"unknown settings: {sorted(overrides)}")
    return settings
