"""Integration tests for the zoned demonstration services.

The controller is exercised for real, kernel and all. The outer services are
exercised by seeding their upstream cache directly rather than by standing up a
network: what is worth testing in them is the transformation each boundary
performs and the staleness they report, not httpx.

Every service asserts the zone it claims to serve from, so a service moved
between zones without updating its declaration fails here.
"""

from __future__ import annotations

from typing import Any

import pytest
from blackstart.core.config import BlackstartConfig
from fastapi.testclient import TestClient
from services.common import ZONE_HEADER, UpstreamPoller, health_payload
from services.enterprise.app import create_app as create_enterprise
from services.historian.app import create_app as create_historian
from services.hmi.app import create_app as create_hmi
from services.idmz.app import create_app as create_idmz

pytestmark = pytest.mark.integration


def sample_state() -> dict[str, Any]:
    """A representative controller state payload."""
    return {
        "zone": "control",
        "source": "controller",
        "state": {
            "t_s": 42.0,
            "true_tank_level_m": 3.2500,
            "reported_tank_level_m": 3.2480,
            "independent_level_m": 3.2500,
            "demand_m3_s": 0.035,
            "service_shortfall_ratio": 0.0,
            "pump_energised": True,
            "valve_position": 1.0,
            "requested_setpoint_m": 3.20,
            "effective_setpoint_m": 3.20,
            "backstop_enabled": True,
            "backstop_constrained_by": [],
            "backstop_denied_by": [],
            "violated_invariants": [],
            "approaching_invariants": [],
            "consequence_level": "C0",
        },
    }


class TestControllerService:
    @pytest.fixture(scope="class")
    @classmethod
    def client(cls):
        from services.controller.app import create_app

        with TestClient(create_app()) as client:
            yield client

    def test_health_reports_the_control_zone(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["zone"] == "control"
        assert response.headers[ZONE_HEADER] == "control"

    def test_state_exposes_both_views_of_the_process(self, client: TestClient):
        state = client.get("/state").json()["state"]
        assert "true_tank_level_m" in state
        assert "reported_tank_level_m" in state
        assert "independent_level_m" in state

    def test_state_starts_inside_the_safe_envelope(
        self, client: TestClient, config: BlackstartConfig
    ):
        state = client.get("/state").json()["state"]
        limit = config.invariants.by_id("INV-001").limit_m
        assert limit is not None
        assert state["true_tank_level_m"] < limit
        assert state["consequence_level"] == "C0"

    def test_an_in_range_setpoint_is_not_clamped(
        self, client: TestClient, config: BlackstartConfig
    ):
        """BS-01 must not engage for a setpoint inside the engineering range.

        BS-02 still may: the slew limiter applies to *every* setpoint change,
        legitimate or not, because the backstop does not attempt to distinguish
        them. A rate limit that only applied to commands already identified as
        illegitimate would be worthless.
        """
        rule = config.architecture.backstop.rule("BS-01")
        assert rule.setpoint_min_m is not None and rule.setpoint_max_m is not None
        target = 3.30
        assert rule.setpoint_min_m <= target <= rule.setpoint_max_m

        body = client.post("/setpoint", json={"setpoint_m": target}).json()
        assert body["accepted"] is True
        assert "BS-01" not in body["constrained_by"]

    def test_an_in_range_setpoint_converges_on_the_requested_value(self, client: TestClient):
        """The slew limiter delays a legitimate change; it does not refuse it."""
        target = 3.30
        client.post("/setpoint", json={"setpoint_m": target})
        effective = 0.0
        for _ in range(40):
            effective = client.post("/setpoint", json={"setpoint_m": target}).json()[
                "effective_setpoint_m"
            ]
            if effective == pytest.approx(target):
                break
        assert effective == pytest.approx(target)

    def test_an_out_of_range_setpoint_is_accepted_but_constrained(
        self, client: TestClient, config: BlackstartConfig
    ):
        """Acceptance is not authorisation.

        The API does not try to decide whether a command is legitimate. It
        records the write and lets the engineering constraint bound the result --
        which is the whole point of having a constraint that does not depend on
        correct attribution.
        """
        maximum = config.architecture.backstop.rule("BS-01").setpoint_max_m
        assert maximum is not None

        response = client.post("/setpoint", json={"setpoint_m": 4.80, "origin": "unknown"})
        body = response.json()
        assert body["accepted"] is True
        assert body["requested_setpoint_m"] == 4.80
        assert body["effective_setpoint_m"] <= maximum
        assert "BS-01" in body["constrained_by"]

    def test_declared_origin_does_not_change_the_constraint(self, client: TestClient):
        """A claimed origin is recorded, never trusted."""
        trusted = client.post(
            "/setpoint", json={"setpoint_m": 4.80, "origin": "engineering"}
        ).json()
        untrusted = client.post("/setpoint", json={"setpoint_m": 4.80, "origin": "unknown"}).json()
        assert trusted["constrained_by"] == untrusted["constrained_by"]

    def test_rejects_a_malformed_setpoint(self, client: TestClient):
        assert client.post("/setpoint", json={"setpoint_m": "high"}).status_code == 422


class TestHmiService:
    @pytest.fixture
    def app(self):
        return create_hmi(controller_url="http://controller.invalid:8084")

    def test_view_is_unavailable_before_the_first_sample(self, app):
        with TestClient(app) as client:
            assert client.get("/view").status_code == 503

    def test_view_reports_the_instrumented_level_not_ground_truth(self, app):
        """An HMI showing ground truth would make telemetry integrity
        meaningless."""
        app.state.poller.latest = sample_state()
        with TestClient(app) as client:
            view = client.get("/view").json()["view"]
        assert view["tank_level_m"] == pytest.approx(3.2480)

    def test_view_reports_the_conduit_it_crossed(self, app):
        app.state.poller.latest = sample_state()
        with TestClient(app) as client:
            body = client.get("/view").json()
        assert body["conduit"] == "CDT-004"
        assert body["zone"] == "ot"

    def test_view_declares_itself_stale_when_the_upstream_is_gone(self, app):
        app.state.poller.latest = sample_state()
        app.state.poller.consecutive_failures = 10
        with TestClient(app) as client:
            assert client.get("/view").json()["stale"] is True

    def test_setpoint_write_reports_an_unreachable_controller(self, app):
        with TestClient(app) as client:
            response = client.post("/setpoint", json={"setpoint_m": 3.3})
        assert response.status_code == 502


class TestHistorianService:
    @pytest.fixture
    def app(self):
        return create_historian(hmi_url="http://hmi.invalid:8083")

    def test_query_is_empty_before_any_sample(self, app):
        with TestClient(app) as client:
            body = client.get("/query").json()
        assert body["count"] == 0
        assert body["latest"] is None

    def test_archives_samples_and_deduplicates_by_timestep(self, app):
        poller: UpstreamPoller = app.state.poller
        assert poller.on_sample is not None
        poller.on_sample({"view": {"t_s": 1.0, "tank_level_m": 3.2}})
        poller.on_sample({"view": {"t_s": 1.0, "tank_level_m": 3.2}})
        poller.on_sample({"view": {"t_s": 2.0, "tank_level_m": 3.3}})

        with TestClient(app) as client:
            body = client.get("/query").json()
        assert body["count"] == 2
        assert body["latest"]["t_s"] == 2.0

    def test_query_limit_is_bounded(self, app):
        with TestClient(app) as client:
            assert client.get("/query?limit=0").status_code == 422
            assert client.get("/query?limit=999999").status_code == 422


class TestIdmzBroker:
    @pytest.fixture
    def app(self):
        return create_idmz(historian_url="http://historian.invalid:8082")

    def test_summary_is_unavailable_before_the_first_sample(self, app):
        with TestClient(app) as client:
            assert client.get("/summary").status_code == 503

    def test_narrows_what_crosses_the_boundary(self, app):
        """The broker passes a fixed set of process values outward. Command
        detail must not cross, even though the historian holds it."""
        app.state.poller.latest = {
            "count": 5,
            "latest": {
                "t_s": 10.0,
                "tank_level_m": 3.2,
                "pump_running": True,
                "service_shortfall_ratio": 0.0,
                "consequence_level": "C0",
                "violated_invariants": [],
                "setpoint_m": 3.2,
                "requested_setpoint_m": 4.8,
                "backstop_active_rules": ["BS-01"],
            },
        }
        with TestClient(app) as client:
            summary = client.get("/summary").json()["summary"]

        assert "tank_level_m" in summary
        assert "setpoint_m" not in summary
        assert "requested_setpoint_m" not in summary
        assert "backstop_active_rules" not in summary

    def test_declares_that_it_carries_no_command_path(self, app):
        app.state.poller.latest = {"count": 1, "latest": {"t_s": 1.0}}
        with TestClient(app) as client:
            body = client.get("/summary").json()
        assert "no command path" in body["note"]
        assert body["zone"] == "idmz"


class TestEnterpriseWorkstation:
    @pytest.fixture
    def app(self):
        return create_enterprise(broker_url="http://idmz-broker.invalid:8081")

    def test_dashboard_renders_before_any_sample(self, app):
        with TestClient(app) as client:
            response = client.get("/")
        assert response.status_code == 200
        assert "Awaiting first sample" in response.text

    def test_dashboard_renders_the_broker_summary(self, app):
        app.state.poller.latest = {"summary": {"tank_level_m": 3.25, "consequence_level": "C0"}}
        with TestClient(app) as client:
            response = client.get("/")
        assert "tank_level_m" in response.text
        assert "3.25" in response.text

    def test_dashboard_escapes_upstream_values(self, app):
        """Values arrive from three zones inward and are untrusted here."""
        app.state.poller.latest = {"summary": {"consequence_level": "<script>alert(1)</script>"}}
        with TestClient(app) as client:
            response = client.get("/")
        assert "<script>alert(1)</script>" not in response.text
        assert "&lt;script&gt;" in response.text

    def test_exposes_no_command_endpoint(self, app):
        """The published service must offer no way to influence the process."""
        routes = {
            route.path
            for route in app.routes
            if getattr(route, "methods", None) and "POST" in route.methods
        }
        assert routes == set()

    def test_health_reports_the_enterprise_zone(self, app):
        with TestClient(app) as client:
            body = client.get("/health").json()
        assert body["zone"] == "enterprise"


class TestHealthReporting:
    def test_a_service_with_no_sample_is_degraded(self):
        poller = UpstreamPoller(url="http://x.invalid/state")
        payload = health_payload("svc", "ot", poller=poller)
        assert payload["status"] == "degraded"
        assert payload["upstream"]["healthy"] is False

    def test_a_service_with_a_recent_sample_is_ok(self):
        poller = UpstreamPoller(url="http://x.invalid/state")
        poller.latest = {"state": {}}
        assert health_payload("svc", "ot", poller=poller)["status"] == "ok"

    def test_a_cached_sample_survives_a_few_failures(self):
        """A stale view is more useful than an empty one, if its staleness shows."""
        poller = UpstreamPoller(url="http://x.invalid/state")
        poller.latest = {"state": {}}
        poller.consecutive_failures = 2
        assert poller.healthy is True
        poller.consecutive_failures = 9
        assert poller.healthy is False
