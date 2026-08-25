"""Deterministic simulation core: physics, invariants, consequences, dependencies.

Every module in this package is pure computation. Nothing here reads the wall
clock, touches the network, spawns a process, or writes to the filesystem. That
property is asserted by ``tests/architecture/test_kernel_purity.py`` and is what
makes experiments reproducible (ADR-001) and the scenario safety boundary
structural rather than aspirational (ADR-006).
"""

from __future__ import annotations
