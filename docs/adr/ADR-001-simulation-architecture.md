# ADR-001 — Simulation architecture

- **Status:** Accepted
- **Date:** 2026-08-24
- **Supersedes:** —

## Context

BLACKSTART must evaluate whether engineered controls prevent a digital compromise from
producing an unacceptable physical consequence. That requires a simulation in which the
following are all separately observable and separately testable:

1. true physical state,
2. the state a control system *believes* it is observing,
3. the commands the control system issues,
4. an engineering constraint that may veto those commands,
5. the resulting consequence classification.

Two architectures were considered: a *co-simulation* driven by an external cyber-physical
platform, and a *single-process deterministic core* with optional service decomposition.

A further constraint is scientific: an experiment must be reproducible bit-for-bit from
`(code version, configuration, seed)`. Reproducibility is far harder to guarantee once wall
clock time, network scheduling, or container start ordering enter the causal path of the
physics.

## Decision

The BLACKSTART core is a **single-process, discrete-time, deterministic simulation kernel**
with no wall-clock dependence and no I/O inside the integration loop.

The kernel executes a fixed scan order per timestep:

```text
 t → scenario effects → sensor model → controller → backstop → actuators
   → physics integration → invariant evaluation → consequence classification → telemetry
```

Structure:

- `blackstart.core` — physics, invariants, consequence classification, dependency graph.
  Pure computation. No I/O, no logging side effects, no clock reads.
- `blackstart.controller` — control logic, PLC scan abstraction, engineering backstop.
- `blackstart.scenario_engine` — scenario schema, loading, effect application, orchestration.
- `blackstart.telemetry` — event envelope and exporters.
- `blackstart.evidence` / `blackstart.analysis` — evidence packaging, verification, metrics.

The containerised topology (`services/`, `docker-compose.yml`) is a **separate demonstration
of the zone/conduit architecture**. It consumes the same kernel but is *not* on the path of
any published experimental result. Experiments run through the CLI, in one process.

## Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| Distributed simulation, physics in its own container, controller talking over a real protocol | Introduces network scheduling into the physics causal path. Determinism becomes best-effort. High implementation cost before any research result exists. |
| Continuous-time solver (SciPy `solve_ivp`, adaptive step) | Adaptive stepping makes step boundaries configuration-dependent; invariant sampling and event timing become non-obvious. The research question does not need stiff-system fidelity. |
| Build directly on an external cyber-physical platform (e.g. SCEPTRE) | Makes the first release depend on a large external research platform. BLACKSTART must run standalone first (see `docs/roadmap` and ADR-006). |

## Consequences

**Positive.** Experiments are reproducible by construction. The whole cyber-to-physical chain
is unit-testable. A reviewer can read the entire causal path in one module.

**Negative.** The kernel does not exercise real protocol stacks, so it cannot produce findings
about protocol-level parsing, timing, or network-observable artefacts. It models *effects* of
compromise, not *mechanisms* of intrusion. This is stated as a limitation in
`docs/limitations.md` and is the principal boundary on what BLACKSTART v0.1 can claim.

**Negative.** Two representations of the architecture now exist (kernel scan order and
container topology). They can drift. Mitigated by `tests/architecture/`, which asserts the
Compose topology matches `configs/architecture.yaml`.

## Security implications

Keeping the kernel I/O-free means scenario effects cannot reach outside the process. A
scenario is a data file that mutates in-memory simulation state; there is no code path from a
scenario definition to a socket, a subprocess, or the filesystem outside the evidence
directory. This is the structural basis of the safety boundary in ADR-006.
