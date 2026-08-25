"""Research metrics and variant comparison.

Every value produced here is derived from a recorded experiment. Metrics whose
underlying capability does not exist are reported as ``NOT_IMPLEMENTED`` rather
than as a plausible number.
"""

from __future__ import annotations

from blackstart.analysis.compare import ComparisonReport, VariantRun, compare_variants
from blackstart.analysis.metrics import NOT_IMPLEMENTED, compute_metrics

__all__ = [
    "NOT_IMPLEMENTED",
    "ComparisonReport",
    "VariantRun",
    "compare_variants",
    "compute_metrics",
]
