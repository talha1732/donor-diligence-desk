"""Settings, .env discovery and the Portkey model builder (owner: agents builder).

Settings are read from the environment on every call to get_settings(), so tests can monkeypatch
variables. The .env file is loaded at most once, lazily, and never overrides a real environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"
DEMO_PAGES_DIR = BACKEND_DIR / "data" / "demo_pages"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_BASE_URL = "https://api.portkey.ai/v1"

ENV_HELP = (
    "No PORTKEY_API_KEY was found. Create a file named .env in the project folder (or any folder above it) "
    "containing the line PORTKEY_API_KEY=<your course key>, then restart with: python backend/run.py. "
    "You can still browse the app, open saved runs, and view the bundled sample run at /?mock=1."
)

_env_loaded_from: Path | None = None
_env_checked = False
_key_from_environment = False


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def find_env_file(start: Path | None = None) -> Path | None:
    """Nearest .env walking up from REPO_ROOT (REPO_ROOT itself first) to the filesystem root."""
    folder = (start or REPO_ROOT).resolve()
    for candidate in (folder, *folder.parents):
        path = candidate / ".env"
        if path.is_file():
            return path
    return None


def load_env(force: bool = False) -> Path | None:
    """Load the nearest .env once (override=False). Skipped entirely when DOTENV_DISABLED=1."""
    global _env_loaded_from, _env_checked, _key_from_environment
    if _truthy(os.environ.get("DOTENV_DISABLED")):
        return None
    if _env_checked and not force:
        return _env_loaded_from
    _env_checked = True
    _key_from_environment = bool(os.environ.get("PORTKEY_API_KEY", "").strip())
    path = find_env_file()
    if path is None:
        return None
    try:
        from dotenv import load_dotenv

        load_dotenv(path, override=False)
        _env_loaded_from = path
    except Exception:  # a malformed .env must not stop the app from starting
        _env_loaded_from = None
    return _env_loaded_from


@dataclass(frozen=True)
class Settings:
    portkey_api_key: str
    model_name: str
    portkey_base_url: str
    port: int
    run_budget_usd: float
    max_run_budget_usd: float
    daily_budget_usd: float
    rate_limit_per_min: int
    offline_mode: bool
    allow_defense_toggle: bool
    output_dir: Path

    @property
    def key_present(self) -> bool:
        return bool(self.portkey_api_key)


def get_settings() -> Settings:
    load_env()
    output_dir = os.environ.get("OUTPUT_DIR", "").strip()
    max_budget = _float("MAX_RUN_BUDGET_USD", 0.50)
    return Settings(
        portkey_api_key=os.environ.get("PORTKEY_API_KEY", "").strip(),
        model_name=os.environ.get("MODEL_NAME", "").strip() or DEFAULT_MODEL,
        portkey_base_url=os.environ.get("PORTKEY_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        port=_int("PORT", 8000),
        run_budget_usd=min(_float("RUN_BUDGET_USD", 0.10), max_budget),
        max_run_budget_usd=max_budget,
        daily_budget_usd=_float("DAILY_BUDGET_USD", 2.00),
        rate_limit_per_min=max(1, _int("RATE_LIMIT_PER_MIN", 5)),
        offline_mode=_truthy(os.environ.get("OFFLINE_MODE")),
        allow_defense_toggle=_truthy(os.environ.get("ALLOW_DEFENSE_TOGGLE")),
        output_dir=Path(output_dir) if output_dir else REPO_ROOT / "output",
    )


def key_present() -> bool:
    return get_settings().key_present


def env_file_used() -> Path | None:
    return _env_loaded_from


def key_source() -> str:
    """Where PORTKEY_API_KEY came from, for the startup message (never the key itself)."""
    if not key_present():
        return "not found"
    if _key_from_environment or _env_loaded_from is None:
        return "from the environment"
    return f"from {_env_loaded_from}"


def build_model(settings: Settings | None = None):
    """OpenAIResponsesModel for gpt-6-luna through Portkey (gpt-6-luna needs the Responses API for tools)."""
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    settings = settings or get_settings()
    if not settings.portkey_api_key:
        raise RuntimeError(ENV_HELP)
    client = AsyncOpenAI(
        api_key=settings.portkey_api_key,
        base_url=settings.portkey_base_url,
        # Portkey can replay identical requests from its own cache; force fresh responses so token
        # counts and costs reflect real model calls.
        default_headers={"x-portkey-provider": "openai", "x-portkey-cache-force-refresh": "true"},
        max_retries=2,
        timeout=60.0,
    )
    return OpenAIResponsesModel(settings.model_name, provider=OpenAIProvider(openai_client=client))
