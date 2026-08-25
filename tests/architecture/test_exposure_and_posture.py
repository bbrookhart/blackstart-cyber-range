"""Architecture tests: host exposure and container posture.

The published-port rule is BLACKSTART's hard external boundary: nothing about the
range should be reachable from outside the host, and no control-zone service
should be reachable from the host at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from blackstart.core.config import BlackstartConfig

pytestmark = pytest.mark.architecture

#: The only port BLACKSTART may publish, and the only interface it may bind.
PERMITTED_PUBLISHED_PORT = "127.0.0.1:8080:8080"
PERMITTED_PUBLISHING_SERVICE = "enterprise-workstation"

#: Ports serving the OT side. None may ever appear in a `ports:` mapping.
CONTROL_SIDE_PORTS = {"8081", "8082", "8083", "8084"}


@pytest.fixture(scope="module")
def compose(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Parse ``docker-compose.yml``."""
    root = Path(request.config.rootpath)
    document = yaml.safe_load((root / "docker-compose.yml").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def published_ports(spec: dict[str, Any]) -> list[str]:
    """Normalise a service's ``ports:`` entries to strings."""
    entries = spec.get("ports", []) or []
    normalised = []
    for entry in entries:
        if isinstance(entry, str):
            normalised.append(entry)
        elif isinstance(entry, dict):  # long-form mapping
            host_ip = entry.get("host_ip", "")
            normalised.append(f"{host_ip}:{entry.get('published')}:{entry.get('target')}")
    return normalised


class TestHostExposure:
    def test_exactly_one_service_publishes_a_port(self, compose: dict[str, Any]):
        publishing = {
            name: published_ports(spec)
            for name, spec in compose["services"].items()
            if published_ports(spec)
        }
        assert list(publishing) == [PERMITTED_PUBLISHING_SERVICE]

    def test_the_published_port_is_the_permitted_one(self, compose: dict[str, Any]):
        ports = published_ports(compose["services"][PERMITTED_PUBLISHING_SERVICE])
        assert ports == [PERMITTED_PUBLISHED_PORT]

    def test_no_port_is_bound_to_all_interfaces(self, compose: dict[str, Any]):
        """A bare `8080:8080` binds 0.0.0.0 and would expose the range to the LAN."""
        for name, spec in compose["services"].items():
            for entry in published_ports(spec):
                assert entry.startswith("127.0.0.1:"), (
                    f"{name} publishes {entry!r}, which does not bind loopback"
                )

    def test_no_control_side_port_is_published(self, compose: dict[str, Any]):
        for name, spec in compose["services"].items():
            for entry in published_ports(spec):
                host_port = entry.split(":")[1]
                assert host_port not in CONTROL_SIDE_PORTS, (
                    f"{name} publishes control-side port {host_port}"
                )

    def test_declared_exposure_matches_deployment(
        self, compose: dict[str, Any], config: BlackstartConfig
    ):
        for service in config.architecture.services:
            deployed = published_ports(compose["services"][service.id])
            if service.publishes:
                assert deployed, f"{service.id} declares exposure but publishes nothing"
                for declared in service.publishes:
                    assert any(entry.startswith(declared) for entry in deployed)
            else:
                assert not deployed, f"{service.id} declares no exposure but publishes {deployed}"


class TestContainerPosture:
    def _spec(self, compose: dict[str, Any], name: str) -> dict[str, Any]:
        """Merged service spec including the YAML-anchor defaults."""
        defaults = compose.get("x-service-defaults", {})
        return {**defaults, **compose["services"][name]}

    @pytest.fixture
    def service_names(self, compose: dict[str, Any]) -> list[str]:
        return list(compose["services"])

    def test_no_container_is_privileged(self, compose: dict[str, Any], service_names: list[str]):
        for name in service_names:
            assert self._spec(compose, name).get("privileged") is not True

    def test_no_container_uses_host_networking(
        self, compose: dict[str, Any], service_names: list[str]
    ):
        """`network_mode: host` would dissolve every zone boundary at once."""
        for name in service_names:
            assert self._spec(compose, name).get("network_mode") != "host"

    def test_every_container_runs_as_a_non_root_user(
        self, compose: dict[str, Any], service_names: list[str]
    ):
        for name in service_names:
            user = str(self._spec(compose, name).get("user", ""))
            assert user, f"{name} declares no user"
            uid = user.split(":")[0]
            assert uid not in {"0", "root"}, f"{name} runs as root"

    def test_every_container_drops_all_capabilities(
        self, compose: dict[str, Any], service_names: list[str]
    ):
        for name in service_names:
            assert self._spec(compose, name).get("cap_drop") == ["ALL"]

    def test_every_container_forbids_privilege_escalation(
        self, compose: dict[str, Any], service_names: list[str]
    ):
        for name in service_names:
            options = self._spec(compose, name).get("security_opt", [])
            assert "no-new-privileges:true" in options

    def test_every_container_has_a_read_only_root_filesystem(
        self, compose: dict[str, Any], service_names: list[str]
    ):
        for name in service_names:
            assert self._spec(compose, name).get("read_only") is True

    def test_every_service_declares_a_health_check(
        self, compose: dict[str, Any], service_names: list[str]
    ):
        """`make health` reports Docker's health state; a service without a check
        would silently report 'none' forever."""
        for name in service_names:
            spec = self._spec(compose, name)
            assert "healthcheck" in spec, f"{name} has no health check"
            assert spec["healthcheck"].get("test")

    def test_no_host_path_is_bind_mounted(self, compose: dict[str, Any], service_names: list[str]):
        """A writable host bind would give a container a path off the range."""
        for name in service_names:
            for volume in self._spec(compose, name).get("volumes", []) or []:
                source = volume if isinstance(volume, str) else volume.get("source", "")
                assert not str(source).startswith(("/", ".", "~")), (
                    f"{name} bind-mounts host path {source!r}"
                )


class TestDockerfilePosture:
    @pytest.fixture(scope="class")
    @classmethod
    def dockerfile(cls, repo_root: Path) -> str:
        return (repo_root / "Dockerfile").read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    @classmethod
    def instructions(cls, dockerfile: str) -> str:
        """Dockerfile with comment lines removed.

        Posture checks must inspect instructions, not prose. A comment
        *explaining* why an installer is not curl-piped would otherwise read as
        the repository curl-piping an installer.
        """
        return "\n".join(
            line
            for line in dockerfile.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )

    def test_runtime_stage_switches_to_a_non_root_user(self, instructions: str):
        assert "USER 10001:10001" in instructions

    def test_uses_a_pinned_base_image(self, instructions: str):
        assert "python:3.12-slim-bookworm" in instructions
        assert ":latest" not in instructions

    def test_installer_provenance_is_a_pinned_image(self, instructions: str):
        """Avoids fetching an installer from a live URL at build time."""
        assert "ghcr.io/astral-sh/uv:" in instructions
        for piped_installer in ("curl", "wget"):
            assert piped_installer not in instructions.lower()

    def test_dependencies_are_installed_from_the_lockfile(self, instructions: str):
        assert "--frozen" in instructions
