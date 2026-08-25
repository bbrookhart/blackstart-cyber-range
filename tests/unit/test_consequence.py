"""Unit tests for consequence classification.

The classifier must be hard to escalate. These tests check both directions: that
a genuine condition reaches the class it should, and that a superficially
alarming one does not.
"""

from __future__ import annotations

import pytest
from blackstart.core.config import BlackstartConfig
from blackstart.core.consequence.classifier import ConsequenceClassifier
from blackstart.core.invariants.base import InvariantSample
from blackstart.core.invariants.engine import InvariantStepResult
from blackstart.core.models import ConsequenceLevel, InvariantStatus

from tests.conftest import make_state

pytestmark = pytest.mark.unit

DT = 0.5


def violations(*invariant_ids: str, t_s: float = 0.0) -> InvariantStepResult:
    """Build an invariant step result with the named invariants violated."""
    return InvariantStepResult(
        t_s=t_s,
        samples=tuple(
            InvariantSample(
                invariant_id=inv_id,
                t_s=t_s,
                status=InvariantStatus.VIOLATED,
                value=0.0,
                limit=None,
            )
            for inv_id in invariant_ids
        ),
    )


NO_VIOLATIONS = InvariantStepResult(t_s=0.0, samples=())


class TestSeverityOrdering:
    def test_ranks_ascend_with_class(self):
        levels = list(ConsequenceLevel)
        assert [level.rank for level in levels] == [0, 1, 2, 3, 4, 5]

    def test_comparison_is_by_rank_not_string(self):
        assert ConsequenceLevel.C4 > ConsequenceLevel.C3
        assert ConsequenceLevel.C0 < ConsequenceLevel.C5
        assert ConsequenceLevel.C2 >= ConsequenceLevel.C2
        assert ConsequenceLevel.C2 <= ConsequenceLevel.C2

    def test_comparison_with_a_foreign_type_is_not_implemented(self):
        assert ConsequenceLevel.C1.__lt__("C2") is NotImplemented
        assert ConsequenceLevel.C1.__gt__(3) is NotImplemented


class TestClassification:
    def test_nominal_operation_is_c0(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        sample = classifier.classify(make_state(tank_level_m=3.20), NO_VIOLATIONS, DT)
        assert sample.level is ConsequenceLevel.C0
        assert sample.drivers == ()

    def test_level_outside_the_normal_band_is_c1(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        sample = classifier.classify(make_state(tank_level_m=4.10), NO_VIOLATIONS, DT)
        assert sample.level is ConsequenceLevel.C1

    def test_advisory_invariants_are_c1_not_c4(self, config: BlackstartConfig):
        """A telemetry divergence is not a physical consequence."""
        classifier = ConsequenceClassifier(config.consequences)
        sample = classifier.classify(make_state(tank_level_m=3.20), violations("INV-005"), DT)
        assert sample.level is ConsequenceLevel.C1

    def test_brief_shortfall_does_not_reach_c2(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        state = make_state(demand_m3_s=0.10, outflow_m3_s=0.05)  # 50% shortfall
        for _ in range(10):  # 5 s, far inside the 60 s sustain requirement
            sample = classifier.classify(state, NO_VIOLATIONS, DT)
        assert sample.level is ConsequenceLevel.C1

    def test_sustained_degradation_reaches_c2(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        state = make_state(demand_m3_s=0.10, outflow_m3_s=0.088)  # 12% shortfall
        for _ in range(130):  # 65 s
            sample = classifier.classify(state, NO_VIOLATIONS, DT)
        assert sample.level is ConsequenceLevel.C2

    def test_sustained_severe_shortfall_reaches_c3(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        state = make_state(demand_m3_s=0.10, outflow_m3_s=0.02)  # 80% shortfall
        for _ in range(130):
            sample = classifier.classify(state, NO_VIOLATIONS, DT)
        assert sample.level is ConsequenceLevel.C3

    def test_reserve_loss_is_c3(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        sample = classifier.classify(make_state(tank_level_m=0.5), violations("INV-002"), DT)
        assert sample.level is ConsequenceLevel.C3

    @pytest.mark.parametrize("invariant_id", ["INV-001", "INV-003"])
    def test_physical_safety_violation_is_c4(self, config: BlackstartConfig, invariant_id: str):
        classifier = ConsequenceClassifier(config.consequences)
        sample = classifier.classify(make_state(tank_level_m=4.8), violations(invariant_id), DT)
        assert sample.level is ConsequenceLevel.C4

    def test_recovery_resets_the_degradation_timer(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        degraded = make_state(demand_m3_s=0.10, outflow_m3_s=0.05)
        healthy = make_state(demand_m3_s=0.10, outflow_m3_s=0.10)
        for _ in range(100):
            classifier.classify(degraded, NO_VIOLATIONS, DT)
        classifier.classify(healthy, NO_VIOLATIONS, DT)
        for _ in range(10):
            sample = classifier.classify(degraded, NO_VIOLATIONS, DT)
        assert sample.level is ConsequenceLevel.C1


class TestCatastrophicEscalation:
    def test_large_containment_loss_is_c5(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        spill = config.consequences.catastrophic_spill_m3
        sample = classifier.classify(
            make_state(tank_level_m=5.0, spill_volume_m3=spill + 1.0),
            violations("INV-001"),
            DT,
        )
        assert sample.level is ConsequenceLevel.C5

    def test_small_spill_stays_c4(self, config: BlackstartConfig):
        """C5 must not be reachable by a token overflow."""
        classifier = ConsequenceClassifier(config.consequences)
        sample = classifier.classify(
            make_state(tank_level_m=5.0, spill_volume_m3=1.0), violations("INV-001"), DT
        )
        assert sample.level is ConsequenceLevel.C4

    def test_prolonged_unsafe_state_alone_is_not_c5(self, config: BlackstartConfig):
        """Escalation to C5 needs an unsafe state AND loss of required service."""
        classifier = ConsequenceClassifier(config.consequences)
        state = make_state(tank_level_m=4.8)
        for _ in range(1000):  # 500 s, past the 300 s unsafe threshold
            sample = classifier.classify(state, violations("INV-001"), DT)
        assert sample.level is ConsequenceLevel.C4

    def test_prolonged_unsafe_state_with_service_loss_is_c5(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        state = make_state(tank_level_m=4.8)
        for _ in range(1000):
            sample = classifier.classify(state, violations("INV-001", "INV-002"), DT)
        assert sample.level is ConsequenceLevel.C5


class TestSummary:
    def test_tracks_maximum_and_dwell_time(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        classifier.classify(make_state(tank_level_m=3.2), NO_VIOLATIONS, DT)
        classifier.classify(make_state(tank_level_m=4.8), violations("INV-001"), DT)
        classifier.classify(make_state(tank_level_m=3.2), NO_VIOLATIONS, DT)

        summary = classifier.summary()
        assert summary.maximum_level is ConsequenceLevel.C4
        assert summary.time_at_level_s["C0"] == pytest.approx(1.0)
        assert summary.time_at_level_s["C4"] == pytest.approx(0.5)

    def test_records_transitions(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        classifier.classify(make_state(t_s=0.0, tank_level_m=3.2), NO_VIOLATIONS, DT)
        classifier.classify(make_state(t_s=0.5, tank_level_m=4.8), violations("INV-001"), DT)
        summary = classifier.summary()
        assert summary.transitions == [{"t_s": 0.5, "from": "C0", "to": "C4"}]

    def test_maximum_is_monotonic(self, config: BlackstartConfig):
        classifier = ConsequenceClassifier(config.consequences)
        classifier.classify(make_state(tank_level_m=4.8), violations("INV-001"), DT)
        classifier.classify(make_state(tank_level_m=3.2), NO_VIOLATIONS, DT)
        assert classifier.maximum_level is ConsequenceLevel.C4
