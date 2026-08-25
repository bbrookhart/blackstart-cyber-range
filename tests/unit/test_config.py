"""Unit tests for configuration loading and cross-validation.

Configuration validation is a safety control in its own right: it is what stops a
physically incoherent model from producing a confident, wrong result.
"""

from __future__ import annotations

from typing import Any

import pytest
from blackstart.core.config import (
    BlackstartConfig,
    ProcessConfig,
    configuration_hash,
    load_config,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


class TestShippedConfiguration:
    def test_loads_and_cross_validates(self, config: BlackstartConfig):
        assert config.process.process_id == "WTR-001"
        assert len(config.invariants.invariants) == 5
        assert len(config.consequences.consequences) == 6

    def test_is_immutable(self, config: BlackstartConfig):
        with pytest.raises(ValidationError):
            config.process.tank.area_m2 = 99.0  # type: ignore[misc]

    def test_timestep_is_stable(self, config: BlackstartConfig):
        """Explicit Euler is only conditionally stable (ADR-002)."""
        ratio = config.process.dominant_time_constant_s / config.process.simulation.timestep_s
        assert ratio >= 20.0

    def test_control_band_matches_the_documented_values(self, config: BlackstartConfig):
        assert config.process.control.band_lower_m == pytest.approx(2.80)
        assert config.process.control.band_upper_m == pytest.approx(3.60)

    def test_normal_band_accommodates_control_overshoot(self, config: BlackstartConfig):
        """A band narrower than the controller's achievable envelope would
        classify correct operation as a deviation."""
        band = config.consequences.normal_band
        assert band.lower_m <= config.process.control.band_lower_m
        assert band.upper_m >= config.process.control.band_upper_m


class TestPhysicalCoherence:
    def _process_dict(self, config: BlackstartConfig) -> dict[str, Any]:
        return config.process.model_dump(mode="python")

    def test_rejects_a_timestep_too_coarse_for_the_process(self, config: BlackstartConfig):
        """The realistic failure mode: someone models a faster process and
        forgets to reduce the timestep.

        Time constant tau = area * shutoff_head / nominal_flow. A much larger
        pump shrinks tau until the shipped 0.5 s step is no longer stable.
        """
        payload = self._process_dict(config)
        payload["pump"]["nominal_flow_m3_s"] = 20.0  # tau falls to 3.9 s
        with pytest.raises(ValidationError, match="too coarse"):
            ProcessConfig.model_validate(payload)

    def test_rejects_an_absolutely_oversized_timestep(self, config: BlackstartConfig):
        payload = self._process_dict(config)
        payload["simulation"]["timestep_s"] = 30.0
        with pytest.raises(ValidationError):
            ProcessConfig.model_validate(payload)

    def test_rejects_an_initial_level_above_the_tank(self, config: BlackstartConfig):
        payload = self._process_dict(config)
        payload["tank"]["initial_level_m"] = 99.0
        with pytest.raises(ValidationError, match="exceeds"):
            ProcessConfig.model_validate(payload)

    def test_rejects_a_control_band_above_the_weir(self, config: BlackstartConfig):
        payload = self._process_dict(config)
        payload["control"]["deadband_m"] = 3.0
        with pytest.raises(ValidationError, match="overflow"):
            ProcessConfig.model_validate(payload)

    def test_rejects_inverted_reserve_protection_hysteresis(self, config: BlackstartConfig):
        payload = self._process_dict(config)
        payload["control"]["reserve_protection"]["release_level_m"] = 0.5
        with pytest.raises(ValidationError, match="release level"):
            ProcessConfig.model_validate(payload)


class TestBackstopCoherence:
    def _full(self, config: BlackstartConfig) -> dict[str, Any]:
        return config.model_dump(mode="python")

    def test_rejects_a_trip_at_or_above_the_safety_limit(self, config: BlackstartConfig):
        """A constraint that acts only after the limit is decorative."""
        payload = self._full(config)
        for rule in payload["architecture"]["backstop"]["rules"]:
            if rule["id"] == "BS-03":
                rule["trip_level_m"] = 4.60
        with pytest.raises(ValidationError, match="strictly below"):
            BlackstartConfig.model_validate(payload)

    def test_rejects_a_clamp_that_cannot_hold_the_process_safe(self, config: BlackstartConfig):
        payload = self._full(config)
        for rule in payload["architecture"]["backstop"]["rules"]:
            if rule["id"] == "BS-01":
                rule["setpoint_max_m"] = 4.30
        with pytest.raises(ValidationError, match="deadband"):
            BlackstartConfig.model_validate(payload)

    def test_rejects_a_safe_limit_at_or_above_the_weir(self, config: BlackstartConfig):
        payload = self._full(config)
        for spec in payload["invariants"]["invariants"]:
            if spec["id"] == "INV-001":
                spec["limit_m"] = 5.50
        with pytest.raises(ValidationError, match="overflow height"):
            BlackstartConfig.model_validate(payload)


class TestArchitectureCoherence:
    def test_no_service_bridges_forbidden_zones(self, config: BlackstartConfig):
        network_to_zone = {z.network: z.id for z in config.architecture.zones}
        forbidden = {tuple(sorted(p)) for p in config.architecture.forbidden_adjacency}
        for service in config.architecture.services:
            zones = sorted({network_to_zone[n] for n in service.networks})
            for i, left in enumerate(zones):
                for right in zones[i + 1 :]:
                    assert (left, right) not in forbidden

    def test_rejects_a_service_bridging_enterprise_and_control(self, config: BlackstartConfig):
        payload = config.model_dump(mode="python")
        payload["architecture"]["services"][0]["networks"] = [
            "blackstart_enterprise",
            "blackstart_control",
        ]
        with pytest.raises(ValidationError, match="forbidden zone pair"):
            BlackstartConfig.model_validate(payload)

    def test_rejects_an_unknown_zone_reference(self, config: BlackstartConfig):
        payload = config.model_dump(mode="python")
        payload["architecture"]["services"][0]["zone"] = "nowhere"
        with pytest.raises(ValidationError, match="unknown zone"):
            BlackstartConfig.model_validate(payload)


class TestInvariantConfig:
    def test_lookup_by_id(self, config: BlackstartConfig):
        assert config.invariants.by_id("INV-001").name == "Maximum safe tank level"

    def test_unknown_id_raises(self, config: BlackstartConfig):
        with pytest.raises(KeyError, match="INV-999"):
            config.invariants.by_id("INV-999")

    def test_rejects_duplicate_ids(self, config: BlackstartConfig):
        payload = config.invariants.model_dump(mode="python")
        payload["invariants"].append(payload["invariants"][0])
        with pytest.raises(ValidationError, match="duplicate invariant ids"):
            type(config.invariants).model_validate(payload)

    def test_every_invariant_declares_a_rationale(self, config: BlackstartConfig):
        for spec in config.invariants.invariants:
            assert spec.rationale.strip(), f"{spec.id} has no rationale"


class TestConsequenceConfig:
    def test_classes_must_be_ordered(self, config: BlackstartConfig):
        payload = config.consequences.model_dump(mode="python")
        payload["consequences"].reverse()
        with pytest.raises(ValidationError, match="ascending order"):
            type(config.consequences).model_validate(payload)

    def test_every_class_has_conditions(self, config: BlackstartConfig):
        for spec in config.consequences.consequences:
            assert spec.conditions, f"{spec.level} declares no conditions"


class TestConfigurationHash:
    def test_is_stable_across_calls(self, config: BlackstartConfig):
        assert configuration_hash(config) == configuration_hash(config)

    def test_changes_when_configuration_changes(self, config: BlackstartConfig):
        payload = config.model_dump(mode="python")
        payload["process"]["tank"]["area_m2"] = 12.5
        other = BlackstartConfig.model_validate(payload)
        assert configuration_hash(config) != configuration_hash(other)

    def test_changes_when_extras_change(self, config: BlackstartConfig):
        """A variant must never be confusable with its baseline."""
        left = configuration_hash(config, extra={"variant": "backstop-enabled"})
        right = configuration_hash(config, extra={"variant": "backstop-disabled"})
        assert left != right

    def test_is_a_sha256_hex_digest(self, config: BlackstartConfig):
        digest = configuration_hash(config)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)


class TestLoader:
    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="configuration file not found"):
            load_config(tmp_path)

    def test_non_mapping_document_raises(self, tmp_path):
        (tmp_path / "process.yaml").write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(tmp_path)
