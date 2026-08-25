# ADR-003 — Network zone model

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

BLACKSTART must demonstrate a segmented OT architecture that a reviewer familiar with
IEC 62443 zone/conduit concepts and NIST SP 800-82r3 architecture guidance recognises as
correct. The demonstration is worthless if the diagram and the deployed topology disagree —
that is the single most common failure mode in security architecture repositories.

## Decision

**Four zones, four Docker networks, one bridging service per conduit.**

| Zone | Network | Services |
| --- | --- | --- |
| Enterprise | `blackstart_enterprise` | `enterprise-workstation`, `idmz-broker` |
| Industrial DMZ | `blackstart_idmz` | `idmz-broker`, `historian` |
| OT supervisory | `blackstart_ot` | `historian`, `hmi` |
| Control / process | `blackstart_control` | `hmi`, `controller` |

The invariant that gives this structure meaning:

> **No service is attached to more than two adjacent zone networks, and no service is
> attached to both the enterprise network and any OT-side network.**

Every cross-zone flow therefore traverses a named, enumerable broker. Reaching the controller
from the enterprise zone requires transiting three separate services. There is no path that
skips a layer.

**Data flows one direction: outward.** Telemetry is *pulled* from the lower zone by the
service in the higher zone (`enterprise-workstation` → `idmz-broker` → `historian` → `hmi` →
`controller`). No control command originates outside the OT supervisory zone in the deployed
topology.

**Exposure.** Exactly one port is published, `127.0.0.1:8080`, serving the read-only
enterprise dashboard. Binding is to the loopback interface explicitly — never `0.0.0.0`. The
HMI, historian, broker and controller publish nothing. Control ports are not reachable from
the host at all.

**Container posture.** All services: `user: "10001:10001"` (non-root), `read_only: true`,
`cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, no `privileged`, no
`network_mode: host`, and a `healthcheck`.

**The topology is machine-checked.** `configs/architecture.yaml` is the authority. Tests in
`tests/architecture/` parse `docker-compose.yml` and assert: declared zone membership matches,
no forbidden zone adjacency exists, only the permitted port is published and only on
loopback, and no container is privileged or root.

## Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| Single flat Docker network with firewall rules in containers | Segmentation would be advisory rather than enforced by the runtime. An architecture test could not distinguish "configured" from "effective". |
| Three zones (collapse IDMZ into enterprise) | The industrial DMZ is precisely where the interesting boundary decisions live. Collapsing it removes the architecture's main teaching point. |
| Kubernetes with NetworkPolicies | Stronger policy expression, far higher reviewer setup cost. Compose is reproducible on a laptop with one command. Revisit if the range grows past ~10 services. |
| Publishing the HMI directly for demo convenience | Would expose a supervisory-zone service on the host, contradicting the architecture the project is arguing for. The enterprise dashboard exists so the demo does not require this compromise. |

## Consequences

**Positive.** The architecture claim is falsifiable and continuously verified. A reviewer can
run `make test-architecture` and see the segmentation asserted, not asserted-in-prose.

**Negative.** Docker bridge networks are not a security boundary of the same character as
physically separate networks with an inspecting firewall. BLACKSTART demonstrates *topology*,
not *enforcement strength*. Stated in `docs/limitations.md`.

**Negative.** Five services must be maintained for a demonstration that produces no
experimental results. Accepted because the architecture is itself a deliverable.

## Security implications

The published-port rule is the project's hard external boundary: nothing about BLACKSTART
should be reachable from outside the host. This is enforced in `docker-compose.yml`, asserted
in `tests/architecture/test_exposure.py`, and stated in `SECURITY.md`.
