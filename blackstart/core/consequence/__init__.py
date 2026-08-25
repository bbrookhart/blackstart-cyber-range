"""Consequence taxonomy and classification.

Consequence severity is derived from measurable conditions, never assigned. See
``docs/consequence-model.md``.
"""

from __future__ import annotations

from blackstart.core.consequence.classifier import (
    ConsequenceClassifier,
    ConsequenceSample,
    ConsequenceSummary,
)

__all__ = ["ConsequenceClassifier", "ConsequenceSample", "ConsequenceSummary"]
