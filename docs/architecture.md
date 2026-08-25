# Architecture

BLACKSTART has two architectures, deliberately kept separate:

1. the **simulation kernel** — a single deterministic process that produces every
   published result;
2. the **zoned container topology** — a demonstration of OT network architecture
   that produces none.

Conflating them would put network scheduling into the causal path of the physics
and make reproducibility best-effort. See
[ADR-001](adr/ADR-001-simulation-architecture.md).

---

## 1. Simulation kernel

One fixed scan order per timestep, with no wall-clock read and no I/O anywhere
inside it:

```text
 t ─► scenario effects        bounded mutations of in-memory state
   ─► sense                   TruthState ──► ReportedState  (+ independent element)
   ─► setpoint constraint     BS-01, BS-02        ◄── engineering backstop, stage 1
   ─► control scan            hysteresis control on the REPORTED level
   ─► actuator interlocks     BS-03, BS-04, BS-05 ◄── engineering backstop, stage 2
   ─► actuate                 pump energised / valve slewed
   ─► record                  invariants, consequence, telemetry, trace
   ─► integrate               physics advances to t + dt
```

Everything recorded at `t` is the state at `t`: the reported view is sampled from
the truth at `t`, the command computed at `t` drives `[t, t+dt)`, and the flows
recorded at `t` were integrated over the preceding interval.

### Why the backstop is in two stages

The setpoint constraint runs **upstream of the controller**, so the controller
never pursues an out-of-range target. The actuator interlocks run **downstream of
the control request**, because a permissive decision needs the request to exist.

This is not cosmetic. An earlier revision applied both stages downstream; the
controller then chased a setpoint of 4.80 m and was stopped only by the high-level
trip, peaking at 4.19 m against a 4.50 m limit. Moving the clamp upstream restored
two independent layers and brought the peak down to 4.00 m.

### Package layout

```text
blackstart/
├── core/                  pure computation — no I/O, no clock, no network
│   ├── physics/           hydraulics and instrumentation
│   ├── invariants/        safety properties over ground truth
│   ├── consequence/       severity derived from measurable conditions
│   ├── graph/             dependency model and path queries
│   ├── config.py          typed configuration + canonical hashing
│   └── models.py          TruthState / ReportedState / CommandState
├── controller/            control logic, PLC scan, engineering backstop
├── scenario_engine/       schema, closed effect registry, runner
├── telemetry/             event envelope and exporters
├── evidence/              packaging, integrity, reproduction
├── analysis/              metrics and variant comparison
└── cli/                   the reviewer-facing surface
```

`core` and `scenario_engine` are **sealed**: no networking, subprocess, or
wall-clock import. Enforced by AST analysis in
`tests/architecture/test_safety_boundary.py`, which is the structural basis of
both the reproducibility guarantee and the scenario safety boundary.

---

## 2. Zoned container topology

Four zones, four isolated Docker networks, one bridging service per conduit.
Authority: [`configs/architecture.yaml`](../configs/architecture.yaml).
Rationale: [ADR-003](adr/ADR-003-network-zone-model.md).

```text
        host ──► 127.0.0.1:8080          the ONLY published port
                      │
  ┌───────────────────▼────────────────────────────────────────┐
  │ ENTERPRISE            enterprise-workstation               │
  └───────────────────┬────────────────────────────────────────┘
                CDT-001 │ read-only pull
  ┌───────────────────▼────────────────────────────────────────┐
  │ INDUSTRIAL DMZ        idmz-broker                          │  internal
  └───────────────────┬────────────────────────────────────────┘
                CDT-002 │ read-only pull
  ┌───────────────────▼────────────────────────────────────────┐
  │ OT SUPERVISORY        historian ──CDT-003──► hmi           │  internal
  └───────────────────┬────────────────────────────────────────┘
                CDT-004 │ pull + command   ◄── the only command path
  ┌───────────────────▼────────────────────────────────────────┐
  │ CONTROL / PROCESS     controller  (+ EBS-001, process twin)│  internal
  └────────────────────────────────────────────────────────────┘
```

The property that gives this structure meaning:

> No service is attached to more than two adjacent zone networks, and no service
> is attached to both the enterprise network and any OT-side network.

Every cross-zone flow therefore traverses a named, enumerable broker. Reaching the
controller from the enterprise zone requires transiting three separate services;
there is no path that skips a layer.

**Data flows outward.** Telemetry is *pulled* by the higher zone. No control
command originates outside the OT supervisory zone. The DMZ broker narrows what
crosses: six process fields go outward, and setpoint and command detail do not.

**Container posture.** Every service runs non-root (`10001:10001`) with a
read-only root filesystem, all capabilities dropped, `no-new-privileges`, and a
health check. No privileged containers, no host networking, no host bind mounts.

### The topology is machine-checked

`tests/architecture/` parses `docker-compose.yml` and asserts it against
`configs/architecture.yaml`: declared attachments match, no forbidden zone
adjacency exists, exactly one port is published and only on loopback, no
control-side port is published, and the container posture holds. CI additionally
proves from a *running* topology that ports 8081–8084 are unreachable from the
host.

A segmentation claim nobody checks decays into a segmentation claim that is
false.

---

## 3. Where the two meet

They deliberately barely do. The container topology imports the same kernel, so
the controller service runs real physics, real invariants and the real backstop —
but no published result comes from it.

| | Kernel (CLI) | Topology (Compose) |
| --- | --- | --- |
| Purpose | Produce results | Demonstrate architecture |
| Determinism | Guaranteed | Not required |
| Time | Simulation time | Wall clock |
| Evidence | Yes | No |
| In CI | Every test | Build, start, health, exposure check |

---

## 4. Dependency graph

A third view, over the *modelled system of systems* rather than either
implementation: [`configs/assets.yaml`](../configs/assets.yaml), built into a
NetworkX `MultiDiGraph` whose edges point in the direction of **causal
influence**.

```bash
uv run blackstart graph supports --critical-function CF-001
uv run blackstart graph influences INV-001
uv run blackstart graph paths --min-class C4
uv run blackstart graph reduction
```

This is what answers the consequence-driven questions: what supports the critical
function, what can influence a given safety limit, which dependency paths
terminate in an unacceptable outcome, and which engineering control interrupts
each one.

It is also what surfaced the finding that the outlet valve command path is
entirely unconstrained — a real gap found by querying the model rather than by
inspection.
