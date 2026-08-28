"""ATT&CK mappings must agree across scenarios, the threat model, and the
authoritative mapping file.

Framework mappings decay quietly: a scenario changes, a mapping file does not,
and the repository ends up asserting a correspondence that no longer holds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from blackstart.scenario_engine.loader import list_scenarios

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def mappings(request: pytest.FixtureRequest) -> dict[str, Any]:
    root = Path(request.config.rootpath)
    path = root / "framework-mappings" / "attack-ics.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture(scope="module")
def objectives(request: pytest.FixtureRequest) -> dict[str, Any]:
    root = Path(request.config.rootpath)
    path = root / "threat-model" / "attack-ics-mapping.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def mapped_ids(mappings: dict[str, Any]) -> set[str]:
    return {entry["attack_technique_id"] for entry in mappings["mappings"]}


class TestProvenance:
    def test_a_version_and_retrieval_date_are_recorded(self, mappings):
        """Mappings must be reproducible against a specific ATT&CK release."""
        source = mappings["source"]
        assert source["version"]
        assert source["retrieved_or_verified"]
        assert source["url"].startswith("https://attack.mitre.org")

    def test_official_dataset_is_version_pinned_and_hashed(self, mappings, request):
        root = Path(request.config.rootpath)
        pin = yaml.safe_load(
            (root / "framework-mappings" / "attack-dataset.yaml").read_text(encoding="utf-8")
        )
        assert pin["framework"] == "MITRE ATT&CK"
        assert pin["domain"] == "ICS"
        assert f"v{pin['version']}" == mappings["source"]["version"]
        assert pin["retrieved_at"] == mappings["source"]["retrieved_or_verified"]
        assert pin["dataset_hash"].startswith("sha256:")
        assert len(pin["dataset_hash"].removeprefix("sha256:")) == 64
        assert pin["dataset_hash"] == mappings["source"]["dataset_hash"]
        assert pin["dataset_bytes"] > 0

    def test_every_mapping_records_its_own_verification_date(self, mappings):
        for entry in mappings["mappings"]:
            assert entry["retrieved_or_verified"]

    def test_every_mapping_has_a_rationale_and_evidence(self, mappings):
        for entry in mappings["mappings"]:
            assert entry["rationale"].strip(), entry["attack_technique_id"]
            assert entry["evidence_source"], entry["attack_technique_id"]


class TestConsistency:
    def test_scenario_techniques_are_all_documented(self, mappings):
        documented = mapped_ids(mappings)
        for scenario in list_scenarios():
            for technique in scenario.attack_ics_techniques:
                assert technique in documented, (
                    f"{scenario.id} cites {technique}, which is not in "
                    f"framework-mappings/attack-ics.yaml"
                )

    def test_every_documented_mapping_is_used_by_a_scenario(self, mappings):
        """A mapping no scenario exercises is an unsupported claim."""
        used = {t for s in list_scenarios() for t in s.attack_ics_techniques}
        for entry in mappings["mappings"]:
            assert entry["attack_technique_id"] in used, (
                f"{entry['attack_technique_id']} is mapped but no scenario uses it"
            )

    def test_mapping_scenario_references_are_accurate(self, mappings):
        by_id = {s.id: s for s in list_scenarios()}
        for entry in mappings["mappings"]:
            for scenario_id in entry["scenario_ids"]:
                assert scenario_id in by_id
                assert entry["attack_technique_id"] in by_id[scenario_id].attack_ics_techniques

    def test_unmapped_scenarios_really_carry_no_technique(self, mappings):
        by_id = {s.id: s for s in list_scenarios()}
        for entry in mappings["unmapped_scenarios"]:
            scenario = by_id[entry["scenario_id"]]
            assert scenario.attack_ics_techniques == []
            assert entry["reason"].strip()

    def test_every_scenario_is_either_mapped_or_explicitly_unmapped(self, mappings):
        """Silence is not an acceptable state for a scenario's mapping."""
        unmapped = {e["scenario_id"] for e in mappings["unmapped_scenarios"]}
        mapped = {s for e in mappings["mappings"] for s in e["scenario_ids"]}
        for scenario in list_scenarios():
            assert scenario.id in unmapped or scenario.id in mapped

    def test_threat_model_objectives_agree_with_the_mapping_file(self, objectives, mappings):
        documented = mapped_ids(mappings)
        for objective in objectives["objectives"]:
            for technique in objective["techniques"]:
                assert technique in documented, (
                    f"{objective['id']} cites undocumented technique {technique}"
                )


class TestDiscipline:
    def test_rejected_mappings_are_recorded_with_reasons(self, mappings):
        """Rejected mappings evidence analytical discipline; keep them."""
        rejected = mappings["considered_and_rejected"]
        assert rejected
        for entry in rejected:
            assert entry["rejection_rationale"].strip()

    def test_a_rejected_technique_is_not_also_asserted(self, mappings):
        rejected = {e["attack_technique_id"] for e in mappings["considered_and_rejected"]}
        assert not (rejected & mapped_ids(mappings))

    def test_uncovered_tactics_are_stated(self, mappings):
        """The uncovered majority of the matrix must not be left implicit."""
        assert len(mappings["uncovered_tactics"]) >= 8
        assert "Initial Access" in mappings["uncovered_tactics"]
        assert mappings["coverage_statement"].strip()

    def test_renumbered_identifiers_are_recorded(self, mappings):
        """Published material still cites the old numbers."""
        renumbered = {e["former_id"]: e["current_id"] for e in mappings["renumbered_upstream"]}
        assert renumbered["T0855"] == "T1692.001"
        assert renumbered["T0856"] == "T1692.002"

    def test_obsolete_identifiers_are_not_used_as_mappings(self, mappings):
        obsolete = {e["former_id"] for e in mappings["renumbered_upstream"]}
        assert not (obsolete & mapped_ids(mappings))
        for scenario in list_scenarios():
            assert not (obsolete & set(scenario.attack_ics_techniques))
