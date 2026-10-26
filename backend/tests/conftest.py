"""Shared test setup (owner: orchestrator). Tests run offline with no API key."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch, tmp_path):
    monkeypatch.delenv("PORTKEY_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OFFLINE_MODE", "1")
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("DOTENV_DISABLED", "1")
