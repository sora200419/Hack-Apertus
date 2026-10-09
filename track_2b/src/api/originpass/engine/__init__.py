"""Deterministic origin engine: evaluates a product against a rule pack (no LLM)."""

from .origin import apply_changes, evaluate

__all__ = ["apply_changes", "evaluate"]
