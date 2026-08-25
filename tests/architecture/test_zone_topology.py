"""Architecture tests: deployment topology matches the declared zone model.

``configs/architecture.yaml`` is the authority. These tests parse it *and*
``docker-compose.yml`` and assert the two agree.

This is the test suite that stops the README diagram from becoming fiction. A
segmentation claim nobody checks decays into a segmentation claim that is false.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from blackstart.core.config import BlackstartConfig

pytestmark = pytest.mark.architecture


@pytest.fixture(scope="module")
def compose(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Parse ``docker-compose.yml``."""
    root = Path(request.config.rootpath)
    document = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def service_networks(compose: dict[str, Any], name: str) -> set[str]:
    """Networks a Compose service is attached to."""
    return set(compose["services"][name].get("networks", []))


class TestDeclaredTopologyMatchesDeployment:
    def test_every_declared_service_is_deployed(
        self, compose: dict[str, Any], config: BlackstartConfig
    ):
        declared = {service.id for service in config.architecture.services}
        deployed = set(compose["services"])
        assert declared == deployed

    def test_every_declared_network_exists(self, compose: dict[str, Any], config: BlackstartConfig):
        declared = {zone.network for zone in config.architecture.zones}
        defined = set(compose["networks"])
        assert declared == defined

    def test_network_attachments_match_the_declaration(
        self, compose: dict[str, Any], config: BlackstartConfig
    ):
        """The claim and the deployment must be the same claim."""
        for service in config.architecture.services:
            assert service_networks(compose, service.id) == set(service.networks), (
                f"{service.id} attachment differs between architecture.yaml and compose"
            )


class TestZoneIsolation:
    def test_no_service_bridges_a_forbidden_zone_pair(
        self, compose: dict[str, Any], config: BlackstartConfig
    ):
        network_to_zone = {z.network: z.id for z in config.architecture.zones}
        forbidden = {tuple(sorted(pair)) for pair in config.architecture.forbidden_adjacency}

        for name in compose["services"]:
            zones = sorted({network_to_zone[n] for n in service_networks(compose, name)})
            for i, left in enumerate(zones):
                for right in zones[i + 1 :]:
                    assert (left, right) not in forbidden, (
                        f"{name} bridges forbidden zone pair ({left}, {right})"
                    )

    def test_no_service_spans_more_than_two_zones(
        self, compose: dict[str, Any], config: BlackstartConfig
    ):
        """A service on three zones would collapse two conduits into one hop."""
        network_to_zone = {z.network: z.id for z in config.architecture.zones}
        for name in compose["services"]:
            zones = {network_to_zone[n] for n in service_networks(compose, name)}
            assert len(zones) <= 2, f"{name} spans {len(zones)} zones"

    def test_controller_is_reachable_only_from_the_control_zone(self, compose: dict[str, Any]):
        assert service_networks(compose, "controller") == {"blackstart_control"}

    def test_enterprise_workstation_cannot_reach_ot(self, compose: dict[str, Any]):
        networks = service_networks(compose, "enterprise-workstation")
        assert networks == {"blackstart_enterprise"}
        assert "blackstart_ot" not in networks
        assert "blackstart_control" not in networks

    def test_exactly_one_service_bridges_enterprise_and_the_ot_side(self, compose: dict[str, Any]):
        """Every enterprise/OT flow must traverse one enumerable broker."""
        bridging = [
            name
            for name in compose["services"]
            if "blackstart_enterprise" in service_networks(compose, name)
            and service_networks(compose, name) - {"blackstart_enterprise"}
        ]
        assert bridging == ["idmz-broker"]

    def test_ot_side_networks_are_internal(self, compose: dict[str, Any]):
        """Containers on these networks have no route off the host."""
        for network in ("blackstart_idmz", "blackstart_ot", "blackstart_control"):
            assert compose["networks"][network].get("internal") is True, (
                f"{network} must be declared internal"
            )

    def test_a_path_from_enterprise_to_control_requires_three_hops(
        self, compose: dict[str, Any], config: BlackstartConfig
    ):
        """There must be no shortcut from the outermost zone to the innermost."""
        network_to_services: dict[str, set[str]] = {}
        for name in compose["services"]:
            for network in service_networks(compose, name):
                network_to_services.setdefault(network, set()).add(name)

        # Breadth-first from the enterprise workstation over shared networks.
        distance = {"enterprise-workstation": 0}
        frontier = ["enterprise-workstation"]
        while frontier:
            current = frontier.pop(0)
            for network in service_networks(compose, current):
                for neighbour in network_to_services[network]:
                    if neighbour not in distance:
                        distance[neighbour] = distance[current] + 1
                        frontier.append(neighbour)

        assert distance["controller"] >= 3, (
            f"controller is only {distance['controller']} hop(s) from the enterprise zone"
        )
        del config


class TestConduits:
    def test_every_conduit_endpoint_is_a_declared_service(self, config: BlackstartConfig):
        services = {service.id for service in config.architecture.services}
        for conduit in config.architecture.conduits:
            assert conduit.initiator in services
            assert conduit.responder in services

    def test_conduit_endpoints_share_a_network(
        self, compose: dict[str, Any], config: BlackstartConfig
    ):
        """A declared conduit that has no shared network could not carry traffic."""
        for conduit in config.architecture.conduits:
            shared = service_networks(compose, conduit.initiator) & service_networks(
                compose, conduit.responder
            )
            assert shared, (
                f"{conduit.id}: {conduit.initiator} and {conduit.responder} share no network"
            )

    def test_only_one_conduit_carries_commands(self, config: BlackstartConfig):
        command_conduits = [
            conduit for conduit in config.architecture.conduits if "command" in conduit.direction
        ]
        assert len(command_conduits) == 1
        assert command_conduits[0].id == "CDT-004"
        assert command_conduits[0].to_zone == "control"
