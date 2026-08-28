# Changelog

All notable changes to BLACKSTART are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

BLACKSTART is pre-1.0 research software: interfaces, configuration and evidence
formats may change between minor versions.

---

## [0.1.0] — 2026-08-28

First operational research release.

### Added

**Deterministic simulation kernel**
- Lumped-parameter hydraulic model of a fictional municipal water storage and
  pumping process: linear pump curve, Torricelli outlet discharge, overflow weir
  with spill accounting. Explicit Euler at a fixed 0.5 s timestep.
- Strict separation of ground-truth physical state from reported sensor state,
  so that physical damage and operator deception are independently measurable.
- Sampled-data control: hysteresis level control with anti-cycling, plus a
  reserve-protection outlet throttle, executing on a 1.0 s PLC scan.

**Safety and consequence**
- Six safety invariants (INV-001 … INV-006), including the central effective
  setpoint bound, with machine-readable per-timestep evaluations.
- Six-class consequence taxonomy (C0 … C5) derived from measurable conditions,
  never assigned.
- Critical function CF-001 with an explicit satisfaction predicate.

**Engineering backstop**
- Simulated independent engineering constraint EBS-001 with five rules: absolute
  setpoint clamp, setpoint slew limit, independent high-level pump trip,
  dry-run suction interlock, and anti-cycle minimum off time.
- Two-stage architecture: the setpoint constraint runs upstream of the
  controller, the actuator interlocks downstream of the control request.

**Scenario engine**
- Declarative YAML scenarios with a closed seven-effect registry.
- Six scenarios: nominal operation, demand surge, sensor integrity loss,
  unauthorised setpoint mutation, loss of supervisory visibility, and source
  depletion with dry-run exposure.

**Evidence and analysis**
- Self-describing evidence packages with SHA-256 artifact digests, schemas,
  environment provenance, control traces, causal graph, and independent result
  verification.
- Deterministic experiment identifiers derived from version, configuration and
  seed; byte-for-byte reproduction verified by `evidence verify --reproduce`.
- Research metrics including service availability, unsafe-state duration,
  consequence severity, recovery status and consequence-path reduction.

**Architecture**
- Four-zone container topology (enterprise, industrial DMZ, OT supervisory,
  control) with one bridging service per conduit and a single loopback-bound
  published port.
- Consequence dependency graph with queries for supporting assets, invariant
  influence, high-consequence paths and engineering-control path reduction.

**Quality**
- 385 tests across unit, property-based, integration and architecture suites.
- 94.09% branch coverage on selected safety-critical modules against a 90% gate.
- Strict `mypy` across package, services and tests.
- ADR-001 through ADR-006.

### Measured

The flagship comparison (SCN-004, seed 4242) is recorded in
[`experiments/releases/v0.1.0/`](experiments/releases/v0.1.0/) and regenerated in
CI. The unprotected condition reaches C4 with 639.5 s unsafe; the protected
condition reaches C1 with 0.0 s unsafe.

### Known limitations

BLACKSTART v0.1 emits no network telemetry and runs no detection analytic;
detection and containment metrics are reported as `NOT_IMPLEMENTED`. It models
the *effects* of compromise, not the *mechanisms* of intrusion. See
[docs/limitations.md](docs/limitations.md) for the full statement.

[0.1.0]: https://github.com/bbrookhart/blackstart-cyber-range/releases/tag/v0.1.0
