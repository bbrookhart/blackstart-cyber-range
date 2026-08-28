"""Research metrics.

Every metric here is computed from the recorded process trace and invariant
outcomes. None is entered by hand, and none is inferred from a scenario's stated
intent -- a scenario that was *designed* to reach C4 but did not will report what
actually happened.

Metrics that cannot yet be measured are reported as the literal string
``NOT_IMPLEMENTED`` rather than as zero, absent, or a plausible-looking number.
BLACKSTART v0.1 has no detection capability, so every detection metric carries
that marker. Reporting a detection latency of 0.0 would be a fabrication.
"""

from __future__ import annotations

from typing import Any, Final

from blackstart.core.config import BlackstartConfig
from blackstart.scenario_engine.orchestration import ExperimentResult
from blackstart.telemetry.exporters.csv_exporter import ProcessTraceRow

__all__ = ["NOT_IMPLEMENTED", "compute_metrics"]

#: Marker for a metric whose underlying capability does not exist yet.
NOT_IMPLEMENTED: Final = "NOT_IMPLEMENTED"

# Invariants whose violation means the critical function CF-001 is not being
# performed. INV-004 through INV-006 are advisory: a command anomaly, bounded
# target violation, or telemetry divergence does not by itself stop delivery.
_FUNCTION_CRITICAL_INVARIANTS = frozenset({"INV-001", "INV-002", "INV-003"})


def _violated_set(row: ProcessTraceRow) -> frozenset[str]:
    """Parse the pipe-delimited violated-invariant column of a trace row."""
    if not row.violated_invariants:
        return frozenset()
    return frozenset(row.violated_invariants.split("|"))


def _critical_function_satisfied(row: ProcessTraceRow, degradation_shortfall_ratio: float) -> bool:
    """Whether CF-001 was being performed at this timestep.

    Mirrors ``critical_function.satisfied_when`` in ``configs/consequences.yaml``:
    demand substantially met, and no function-critical invariant violated.
    """
    if row.service_shortfall_ratio >= degradation_shortfall_ratio:
        return False
    return not (_violated_set(row) & _FUNCTION_CRITICAL_INVARIANTS)


def _recovery(
    result: ExperimentResult, rows: tuple[ProcessTraceRow, ...], shortfall_limit: float
) -> dict[str, Any]:
    """Measure time from the end of the disturbance to sustained recovery.

    Recovery is only meaningful once the disturbance has ended. Where a scenario
    effect persists to the end of the experiment there is nothing to recover
    from yet, and that is reported rather than papered over with a null.
    """
    if not result.scenario.events:
        return {"status": "no_disturbance", "recovery_time_s": None}

    end_times = [event.end_t_s for event in result.scenario.events]
    if any(end is None for end in end_times):
        return {
            "status": "effect_persists_to_end_of_experiment",
            "recovery_time_s": None,
            "note": (
                "At least one scenario effect is unbounded, so the experiment "
                "never leaves the disturbed condition. Recovery time is not "
                "defined for this run."
            ),
        }

    disturbance_end_s = max(end for end in end_times if end is not None)
    tail = [row for row in rows if row.t_s >= disturbance_end_s]
    if not tail:
        return {"status": "insufficient_observation_after_disturbance", "recovery_time_s": None}

    # Recovery must be sustained: find the earliest timestep after which the
    # critical function is satisfied for the remainder of the experiment.
    recovered_from_t_s: float | None = None
    for row in reversed(tail):
        if _critical_function_satisfied(row, shortfall_limit):
            recovered_from_t_s = row.t_s
        else:
            break

    if recovered_from_t_s is None:
        return {
            "status": "not_recovered_within_experiment",
            "recovery_time_s": None,
            "disturbance_end_s": round(disturbance_end_s, 3),
        }
    return {
        "status": "recovered",
        "recovery_time_s": round(max(0.0, recovered_from_t_s - disturbance_end_s), 3),
        "disturbance_end_s": round(disturbance_end_s, 3),
    }


def compute_metrics(result: ExperimentResult, config: BlackstartConfig) -> dict[str, Any]:
    """Compute the research metrics for one experiment.

    Args:
        result: The completed experiment.
        config: The configuration the experiment ran under.

    Returns:
        The ``metrics.json`` payload.
    """
    rows = result.trace.rows
    if not rows:
        msg = f"{result.experiment_id}: cannot compute metrics from an empty trace"
        raise ValueError(msg)

    dt_s = result.timestep_s
    total_s = len(rows) * dt_s
    shortfall_limit = config.consequences.degradation_shortfall_ratio
    legitimate_setpoint_m = config.process.control.operator_setpoint_m

    satisfied_steps = sum(1 for row in rows if _critical_function_satisfied(row, shortfall_limit))
    maximum_safe_m = config.invariants.by_id("INV-001").limit_m
    minimum_safe_m = config.invariants.by_id("INV-002").limit_m
    if maximum_safe_m is None or minimum_safe_m is None:
        msg = "INV-001 and INV-002 physical safety limits must be configured"
        raise ValueError(msg)
    unsafe_steps = sum(
        1
        for row in rows
        if row.true_tank_level_m > maximum_safe_m or row.true_tank_level_m < minimum_safe_m
    )
    supervisory_steps = sum(1 for row in rows if row.supervisory_available)

    levels = [row.true_tank_level_m for row in rows]
    shortfalls = [row.service_shortfall_ratio for row in rows]
    safety_margins = [min(level - minimum_safe_m, maximum_safe_m - level) for level in levels]

    per_invariant = {
        outcome["invariant_id"]: {
            "violated": outcome["violated"],
            "violation_count": outcome["violation_count"],
            "total_violation_s": outcome["total_violation_s"],
            "total_approaching_s": outcome["total_approaching_s"],
            "peak_excursion": outcome["peak_excursion"],
            "first_violation_t_s": outcome["first_violation_t_s"],
        }
        for outcome in result.invariants["outcomes"]
    }

    return {
        "experiment_id": result.experiment_id,
        "scenario_id": result.scenario.id,
        "variant": result.variant.name,
        "backstop_enabled": result.variant.backstop_enabled,
        "seed": result.seed,
        "duration_s": round(total_s, 3),
        "timestep_s": dt_s,
        "steps": len(rows),
        # --- Service ------------------------------------------------------
        "service_availability_pct": round(100.0 * satisfied_steps / len(rows), 4),
        "mean_service_shortfall_ratio": round(sum(shortfalls) / len(shortfalls), 6),
        "max_service_shortfall_ratio": round(max(shortfalls), 6),
        # --- Safety -------------------------------------------------------
        "unsafe_state_duration_s": round(unsafe_steps * dt_s, 3),
        "unsafe_state_pct": round(100.0 * unsafe_steps / len(rows), 4),
        "max_tank_level_m": round(max(levels), 4),
        "min_tank_level_m": round(min(levels), 4),
        "max_deviation_from_setpoint_m": round(
            max(abs(level - legitimate_setpoint_m) for level in levels), 4
        ),
        "maximum_physical_deviation_m": round(
            max(abs(level - legitimate_setpoint_m) for level in levels), 4
        ),
        "minimum_safety_margin_m": round(min(safety_margins), 4),
        "spill_volume_m3": round(rows[-1].spill_volume_m3, 4),
        # --- Invariants ---------------------------------------------------
        "invariant_violations_total": result.invariants["total_violations"],
        "violated_invariants": list(result.invariants["violated_invariants"]),
        "invariant_violation_duration_s": round(
            sum(item["total_violation_s"] for item in per_invariant.values()), 3
        ),
        "invariants": per_invariant,
        # --- Consequence --------------------------------------------------
        "maximum_consequence": result.consequences.maximum_level.value,
        "time_at_consequence_s": {
            k: round(v, 3) for k, v in sorted(result.consequences.time_at_level_s.items())
        },
        # --- Operations ---------------------------------------------------
        "supervisory_availability_pct": round(100.0 * supervisory_steps / len(rows), 4),
        "pump_starts": max(0, _final_pump_starts(result)),
        "recovery": _recovery(result, rows, shortfall_limit),
        "recovery_time_s": _recovery_value(result, rows, shortfall_limit),
        # --- Engineering control -------------------------------------------
        "backstop": {
            "enabled": result.backstop["enabled"],
            "activation_counts": result.backstop["activation_counts"],
            "trip_count": result.backstop["trip"]["trip_count"],
            "first_trip_t_s": result.backstop["trip"]["first_trip_t_s"],
        },
        # --- Not yet measurable --------------------------------------------
        # BLACKSTART v0.1 emits no network telemetry and runs no detection
        # analytic, so these have no basis. See docs/limitations.md.
        "detection_latency_s": NOT_IMPLEMENTED,
        "containment_latency_s": NOT_IMPLEMENTED,
        "false_positive_rate": NOT_IMPLEMENTED,
    }


def _final_pump_starts(result: ExperimentResult) -> int:
    """Extract the final pump-start count from the experiment lifecycle event."""
    for event in reversed(result.events.events):
        if event.data.get("phase") == "end":
            starts = event.data.get("pump_starts", 0)
            return int(starts) if isinstance(starts, int) else 0
    return 0


def _recovery_value(
    result: ExperimentResult, rows: tuple[ProcessTraceRow, ...], shortfall_limit: float
) -> float | str:
    """Return the report-friendly recovery metric required by EXP-BS-001."""
    recovery = _recovery(result, rows, shortfall_limit)
    value = recovery.get("recovery_time_s")
    if isinstance(value, (int, float)):
        return float(value)
    if recovery["status"] == "no_disturbance":
        return "NOT_APPLICABLE"
    return "NOT_RECOVERED"
