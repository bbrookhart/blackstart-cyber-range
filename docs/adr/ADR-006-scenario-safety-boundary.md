# ADR-006 — Scenario safety boundary

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

BLACKSTART studies what happens *after* compromise. Any project in this space must draw a hard
line between modelling the **effects** of adversary capability and providing **operational
tooling** for achieving it. The line has to be structural — enforced by the architecture — not
merely a promise in a policy document, because a promise cannot be tested.

## Decision

### Scenarios are declarative data, never code

A scenario is a YAML document validated against a Pydantic schema. It cannot contain
expressions, scripts, imports, or file paths. Loading a scenario cannot execute anything.

### A closed, enumerated effect vocabulary

Every scenario event names an effect from a fixed registry in
`blackstart/scenario_engine/effects.py`. v0.1 implements exactly seven:

| Effect | Simulated condition | Acts on |
| --- | --- | --- |
| `demand.step` / `demand.ramp` | Benign load disturbance | Physics input |
| `sensor.bias` | Level transmitter reports a constant offset | Sensor model |
| `sensor.freeze` | Transmitter holds its last value | Sensor model |
| `setpoint.override` | Control setpoint mutated outside operator action | Controller input |
| `supervisory.blackout` | HMI/telemetry path unavailable | Telemetry path |
| `source.depletion` | Source reservoir falls toward suction limit | Physics input |

Each is a bounded mutation of in-memory simulation state. The registry is closed: an unknown
effect name is a load-time validation error, not a dynamic dispatch. A test asserts the
registry contains no effect outside this list.

### What the effect layer structurally cannot do

Effects have no access to sockets, subprocesses, environment variables, or the filesystem.
`blackstart/core` and `blackstart/scenario_engine` import no networking or process module. A
test asserts this by walking the AST of every module in those packages and failing on an
import of `socket`, `subprocess`, `os.system`, `requests`, `httpx`, or `urllib`.

Consequently there is **no code path from a scenario file to any system outside the Python
process**, and adding one requires deleting a test.

### Effects are not exploits

`setpoint.override` writes to a field. It does not authenticate, bypass authentication,
craft a protocol frame, or exploit a flaw. It answers the research question "*given* that an
adversary achieved unauthorised control influence, which engineered constraint prevents that
influence from becoming an unacceptable physical consequence?" — which is the question
BLACKSTART exists to ask.

This is deliberate scoping, and it is also a real limitation: BLACKSTART cannot tell you
whether such influence is *achievable* against any particular system. It only tells you what
happens if it is. See `docs/limitations.md`.

### Prohibited by policy and absent from the repository

No malware, ransomware, or destructive payloads. No credential access tooling. No persistence
or lateral-movement tooling. No scanning of any address space. No exploitation of any real
device. No real utility credentials, configurations, network diagrams, or operational
parameters. All parameters in this repository are invented.

### Isolation

The container topology exposes exactly one loopback port (ADR-003). Nothing in BLACKSTART
initiates outbound network connections. The range is never to be connected to real OT assets.

## Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| Scripted/plugin scenarios (Python callables) | Maximum expressiveness, but destroys the structural guarantee — a scenario file becomes arbitrary code execution. The guarantee is worth more than the flexibility. |
| Real protocol manipulation against a soft-PLC on an isolated network | Higher realism, and produces network-observable artefacts BLACKSTART currently lacks. Also produces reusable protocol attack tooling. Deferred pending a design that keeps the tooling non-reusable; noted in the roadmap. |
| Integrating an adversary emulation framework in v0.1 | Out of scope for a first release. Documented as a future, isolated, ATT&CK-mapped integration path. |

## Consequences

**Positive.** The safety boundary is testable, not aspirational. A contributor cannot
accidentally widen it. Reviewers can verify the claim in about a minute by reading two tests.

**Negative.** BLACKSTART produces no network telemetry, so it cannot yet evaluate
network-based detection. This is the single largest gap in v0.1 and the highest-value next
milestone.

**Negative.** The closed vocabulary means new research questions require a code change and
review, rather than a new data file. Accepted deliberately: that review is the control.

## Security implications

This ADR *is* the project's security posture for offensive capability. `SECURITY.md` and
`CONTRIBUTING.md` both reference it, and contributions that would breach it are rejected on
these grounds.
