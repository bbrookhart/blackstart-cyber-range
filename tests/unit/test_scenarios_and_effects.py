"""Unit tests for scenario parsing, validation, and the closed effect registry."""

from __future__ import annotations

from pathlib import Path
from random import Random
from typing import Any

import pytest
import yaml
from blackstart.core.config import BlackstartConfig
from blackstart.core.physics.process import WaterProcessModel
from blackstart.core.physics.sensors import DemandModel, SensorModel
from blackstart.scenario_engine.effects import (
    EFFECT_REGISTRY,
    EffectContext,
    SetpointHolder,
    resolve_effect,
)
from blackstart.scenario_engine.loader import list_scenarios, load_scenario, load_scenario_file
from blackstart.scenario_engine.schema import Scenario

pytestmark = pytest.mark.unit

#: The complete documented effect vocabulary (ADR-006). Widening this set is a
#: deliberate act that must also update the ADR and the safety documentation.
DOCUMENTED_EFFECTS = {
    "demand.step",
    "demand.ramp",
    "source.depletion",
    "sensor.bias",
    "sensor.freeze",
    "supervisory.blackout",
    "setpoint.override",
}


@pytest.fixture
def ctx(config: BlackstartConfig) -> EffectContext:
    """An effect context wired to fresh models."""
    rng = Random(7)
    truth = WaterProcessModel(config.process).initial_state()
    return EffectContext(
        demand=DemandModel(config.process, rng),
        sensors=SensorModel(config.process, rng),
        truth=truth,
        setpoint=SetpointHolder(requested_m=config.process.control.operator_setpoint_m),
    )


class TestRegistry:
    def test_registry_matches_the_documented_vocabulary(self):
        assert set(EFFECT_REGISTRY) == DOCUMENTED_EFFECTS

    def test_registry_is_closed(self):
        with pytest.raises(ValueError, match="registry is closed"):
            resolve_effect("process.destroy")

    def test_every_effect_documents_what_it_simulates(self):
        for name, effect in EFFECT_REGISTRY.items():
            assert effect.name == name
            assert effect.simulates.strip(), f"{name} does not state what it simulates"


class TestPhysicalDisturbanceEffects:
    def test_demand_step_changes_and_restores_the_rate(self, ctx: EffectContext):
        effect = resolve_effect("demand.step")
        params = {"rate_m3_s": 0.135}
        original = ctx.demand.base_rate_m3_s
        effect.activate(ctx, params)
        assert ctx.demand.base_rate_m3_s == pytest.approx(0.135)
        effect.deactivate(ctx, params)
        assert ctx.demand.base_rate_m3_s == pytest.approx(original)

    def test_demand_ramp_interpolates(self, ctx: EffectContext):
        effect = resolve_effect("demand.ramp")
        params = {"target_m3_s": 0.100, "ramp_s": 100.0}
        start = ctx.demand.base_rate_m3_s
        effect.activate(ctx, params)
        effect.tick(ctx, params, elapsed_s=50.0, dt_s=0.5)
        assert ctx.demand.base_rate_m3_s == pytest.approx(start + (0.100 - start) * 0.5)
        effect.tick(ctx, params, elapsed_s=500.0, dt_s=0.5)
        assert ctx.demand.base_rate_m3_s == pytest.approx(0.100)

    def test_source_depletion_lowers_the_reservoir(self, ctx: EffectContext):
        effect = resolve_effect("source.depletion")
        params = {"target_level_m": 0.20, "ramp_s": 600.0}
        effect.activate(ctx, params)
        effect.tick(ctx, params, elapsed_s=600.0, dt_s=0.5)
        assert ctx.truth.source_level_m == pytest.approx(0.20)

    @pytest.mark.parametrize(
        ("name", "params"),
        [
            ("demand.step", {}),
            ("demand.step", {"rate_m3_s": -1.0}),
            ("demand.ramp", {"target_m3_s": 0.1}),
            ("demand.ramp", {"target_m3_s": 0.1, "ramp_s": 0.0}),
            ("source.depletion", {"target_level_m": -1.0, "ramp_s": 10.0}),
            ("setpoint.override", {"value_m": -1.0}),
            ("sensor.bias", {"bias_m": "deep"}),
        ],
    )
    def test_invalid_parameters_are_rejected(self, name: str, params: dict[str, Any]):
        with pytest.raises(ValueError):
            resolve_effect(name).validate_params(params)


class TestTelemetryEffects:
    def test_sensor_bias_never_touches_ground_truth(self, ctx: EffectContext):
        """The property that keeps the evidence record honest (ADR-004)."""
        effect = resolve_effect("sensor.bias")
        before = ctx.truth.tank_level_m
        effect.activate(ctx, {"bias_m": -1.50})
        assert ctx.sensors.fault_level_bias_m == pytest.approx(-1.50)
        assert ctx.truth.tank_level_m == pytest.approx(before)

    def test_sensor_bias_shifts_only_the_report(self, ctx: EffectContext):
        resolve_effect("sensor.bias").activate(ctx, {"bias_m": -1.50})
        reported = ctx.sensors.read(ctx.truth)
        assert reported.tank_level_m < ctx.truth.tank_level_m - 1.0

    def test_sensor_freeze_holds_the_last_value(self, ctx: EffectContext):
        first = ctx.sensors.read(ctx.truth).tank_level_m
        resolve_effect("sensor.freeze").activate(ctx, {})
        ctx.truth.tank_level_m = 4.90
        assert ctx.sensors.read(ctx.truth).tank_level_m == pytest.approx(first)

    def test_independent_element_ignores_sensor_faults(self, ctx: EffectContext):
        """The modelling assumption the backstop's independence rests on."""
        resolve_effect("sensor.bias").activate(ctx, {"bias_m": -1.50})
        resolve_effect("sensor.freeze").activate(ctx, {})
        ctx.truth.tank_level_m = 4.30
        independent = ctx.sensors.read_independent_element(ctx.truth)
        assert independent == pytest.approx(4.30, abs=0.05)

    def test_supervisory_blackout_leaves_local_control_readable(self, ctx: EffectContext):
        resolve_effect("supervisory.blackout").activate(ctx, {})
        reported = ctx.sensors.read(ctx.truth)
        assert reported.supervisory_available is False
        assert reported.tank_level_m == pytest.approx(ctx.truth.tank_level_m, abs=0.05)

    def test_effects_are_reverted_on_deactivate(self, ctx: EffectContext):
        for name, params in (
            ("sensor.bias", {"bias_m": -1.0}),
            ("sensor.freeze", {}),
            ("supervisory.blackout", {}),
        ):
            effect = resolve_effect(name)
            effect.activate(ctx, params)
            effect.deactivate(ctx, params)
        assert ctx.sensors.fault_level_bias_m == 0.0
        assert ctx.sensors.fault_level_frozen is False
        assert ctx.sensors.fault_supervisory_available is True


class TestSetpointOverride:
    def test_mutates_and_restores_the_held_setpoint(self, ctx: EffectContext):
        effect = resolve_effect("setpoint.override")
        params = {"value_m": 4.80}
        original = ctx.setpoint.requested_m
        effect.activate(ctx, params)
        assert ctx.setpoint.requested_m == pytest.approx(4.80)
        effect.deactivate(ctx, params)
        assert ctx.setpoint.requested_m == pytest.approx(original)

    def test_does_not_touch_physics_or_instrumentation(self, ctx: EffectContext):
        before_level = ctx.truth.tank_level_m
        resolve_effect("setpoint.override").activate(ctx, {"value_m": 4.80})
        assert ctx.truth.tank_level_m == pytest.approx(before_level)
        assert ctx.sensors.fault_level_bias_m == 0.0


class TestScenarioCatalogue:
    def test_every_shipped_scenario_loads(self):
        scenarios = list_scenarios()
        assert len(scenarios) == 6

    def test_every_scenario_states_a_research_question(self):
        for scenario in list_scenarios():
            assert scenario.research_question.strip(), f"{scenario.id} asks nothing"

    def test_every_scenario_declares_measured_expectations(self):
        for scenario in list_scenarios():
            assert scenario.expected is not None, f"{scenario.id} has no expectations"

    def test_every_event_uses_a_registered_effect(self):
        for scenario in list_scenarios():
            for event in scenario.events:
                assert event.effect in EFFECT_REGISTRY

    def test_benign_scenarios_carry_no_attack_mapping(self):
        """Mapping a physical disturbance to a technique would be a false
        association, and empty is the honest answer."""
        for scenario_id in ("SCN-001", "SCN-002", "SCN-006"):
            assert load_scenario(scenario_id).attack_ics_techniques == []

    def test_lookup_by_id(self):
        assert load_scenario("SCN-004").name == "Unauthorised setpoint mutation"

    def test_unknown_scenario_lists_available_ones(self):
        with pytest.raises(FileNotFoundError, match="SCN-001"):
            load_scenario("SCN-999")


class TestScenarioValidation:
    def _write(self, tmp_path: Path, name: str, payload: dict[str, Any]) -> Path:
        path = tmp_path / f"{name}.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")
        return path

    def _base(self) -> dict[str, Any]:
        return {
            "id": "SCN-900",
            "name": "Test",
            "description": "Test scenario.",
            "research_question": "Does validation work?",
            "category": "baseline",
            "seed": 1,
            "duration_s": 100.0,
            "events": [],
        }

    def test_rejects_an_unknown_effect(self, tmp_path: Path):
        payload = self._base()
        payload["events"] = [{"t_s": 1.0, "effect": "exploit.plc", "description": "no"}]
        path = self._write(tmp_path, "SCN-900", payload)
        with pytest.raises(ValueError, match="registry is closed"):
            load_scenario_file(path)

    def test_rejects_invalid_effect_parameters_at_load_time(self, tmp_path: Path):
        payload = self._base()
        payload["events"] = [
            {"t_s": 1.0, "effect": "demand.step", "description": "bad", "params": {}}
        ]
        path = self._write(tmp_path, "SCN-900", payload)
        with pytest.raises(ValueError, match="invalid parameters"):
            load_scenario_file(path)

    def test_rejects_an_event_past_the_duration(self, tmp_path: Path):
        payload = self._base()
        payload["events"] = [{"t_s": 500.0, "effect": "sensor.freeze", "description": "late"}]
        path = self._write(tmp_path, "SCN-900", payload)
        with pytest.raises(ValueError, match="beyond the scenario duration"):
            load_scenario_file(path)

    def test_rejects_out_of_order_events(self, tmp_path: Path):
        payload = self._base()
        payload["events"] = [
            {"t_s": 50.0, "effect": "sensor.freeze", "description": "second"},
            {"t_s": 10.0, "effect": "supervisory.blackout", "description": "first"},
        ]
        path = self._write(tmp_path, "SCN-900", payload)
        with pytest.raises(ValueError, match="ascending activation order"):
            load_scenario_file(path)

    def test_rejects_a_fabricated_attack_identifier(self, tmp_path: Path):
        payload = self._base()
        payload["events"] = [
            {
                "t_s": 1.0,
                "effect": "sensor.freeze",
                "description": "x",
                "attack_ics": ["ICS-HACK-1"],
            }
        ]
        path = self._write(tmp_path, "SCN-900", payload)
        with pytest.raises(ValueError, match="well-formed"):
            load_scenario_file(path)

    def test_accepts_both_attack_numbering_forms(self):
        """Several ICS techniques were renumbered upstream into T1xxx.nnn."""
        Scenario.model_validate(
            {
                **self._base(),
                "events": [
                    {
                        "t_s": 1.0,
                        "effect": "sensor.freeze",
                        "description": "x",
                        "attack_ics": ["T0832", "T1692.002"],
                    }
                ],
            }
        )

    def test_rejects_a_filename_identifier_mismatch(self, tmp_path: Path):
        path = self._write(tmp_path, "SCN-901", self._base())
        with pytest.raises(ValueError, match="does not match filename"):
            load_scenario_file(path)

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="scenario file not found"):
            load_scenario_file(tmp_path / "SCN-999.yaml")


class TestCausalFingerprint:
    def test_excludes_prose_and_expectations(self):
        """Recording a measured expectation must not invalidate experiment ids."""
        scenario = load_scenario("SCN-004")
        edited = scenario.model_copy(
            update={"name": "Renamed", "notes": "different", "expected": None}
        )
        assert scenario.causal_fingerprint() == edited.causal_fingerprint()

    def test_includes_effect_parameters(self):
        scenario = load_scenario("SCN-004")
        events = [scenario.events[0].model_copy(update={"params": {"value_m": 4.90}})]
        edited = scenario.model_copy(update={"events": events})
        assert scenario.causal_fingerprint() != edited.causal_fingerprint()

    def test_includes_the_seed(self):
        scenario = load_scenario("SCN-004")
        edited = scenario.model_copy(update={"seed": 999})
        assert scenario.causal_fingerprint() != edited.causal_fingerprint()
