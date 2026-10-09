"""Shared pytest setup: make `originpass` and the test fixtures importable from any working directory."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

for _path in (API_DIR, FIXTURES_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


@pytest.fixture
def fixtures_dir() -> Path:
    """Directory with synthetic test data (rule packs under fixtures/rulepacks)."""
    return FIXTURES_DIR
