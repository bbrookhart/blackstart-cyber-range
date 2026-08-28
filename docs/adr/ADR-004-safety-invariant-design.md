# ADR-004 — Safety invariant design

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

Safety invariants are the mechanism by which BLACKSTART converts "something bad happened in
the simulation" into a defensible, quantified claim. Their design determines whether results
are evidence or opinion.

Three questions had to be settled:

1. What state does an invariant read — true physics, or reported telemetry?
2. How are invariants with a time dimension expressed?
3. What is the relationship between an invariant and the engineering backstop?

## Decision

### 1. Invariants evaluate **true physical state**

Invariants are the *ground-truth* record of whether the process was actually safe. They are an
analysis instrument, not a control element, and they read `ProcessState.truth`.

The single exception is **INV-006 (telemetry integrity)**, whose entire purpose is to compare
the two views. It reads both, and is the only invariant permitted to do so.

The consequence: if an adversary falsifies the level transmitter, the operator-facing view is
wrong, INV-001 still reports the true excursion, and INV-006 reports the deception. Both facts
land in the evidence package. **The evidence model is not deceivable by an effect that
deceives the operator** — this is a deliberate and load-bearing property.

### 2. Invariants are **stateful temporal predicates**, not stateless assertions

Each invariant is an object implementing:

```python
evaluate(state, dt_s) -> InvariantSample   # status: OK | APPROACHING | VIOLATED
```

and carrying its own accumulated duration. This is required because real OT safety conditions
are almost never instantaneous. "The tank is below reserve" is not a violation; "the tank has
been below reserve for longer than the 120 s tolerance" is. Stateless assertions cannot
express that, and would have forced tolerance logic into the metrics layer where it would be
invisible to tests.

The three-valued status adds `APPROACHING` — within a configured margin of the limit. This
yields the *leading indicator* an operator or detection system would actually act on, and lets
BLACKSTART measure how much warning an engineered control provided, not merely whether the
limit was breached.

### 3. Invariants are **independent of** the backstop

The backstop (ADR-006, `blackstart/controller/backstop.py`) enforces a policy on commands. The
invariants measure outcomes. They share configuration values but no code, and neither imports
the other.

This separation is what makes the flagship experiment meaningful. If the invariant checker and
the safety control were the same object, "backstop enabled → no violations" would be a
tautology. Because they are independent, the measured difference is a real result. The
backstop's thresholds are deliberately set *tighter* than the invariant limits (4.20 m vs
4.50 m) so the backstop acts before the safety limit, and the margin between them is itself a
measurable quantity.

### The six invariants

| ID | Property | Type |
| --- | --- | --- |
| INV-001 | Tank level ≤ 4.50 m | Instantaneous bound |
| INV-002 | Level ≥ 1.00 m reserve, tolerance 120 s | Temporal |
| INV-003 | Pump not energised while source below suction limit | Conditional |
| INV-004 | Commanded setpoint slew ≤ 0.05 m/s; pump starts ≤ 12/hour | Rate |
| INV-005 | Effective setpoint remains in 1.50–3.60 m engineering range | Control bound |
| INV-006 | \|reported level − true level\| ≤ 0.10 m | Cross-view |

Every invariant is defined in `configs/invariants.yaml`, implemented in
`blackstart/core/invariants/`, and covered by dedicated unit tests plus at least one property
test.

## Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| Invariants as pure stateless predicates, tolerance applied later in metrics | Hides safety-relevant logic in the analysis layer, where it is not tested as safety logic. |
| Invariants evaluated on sensor state (what the control system sees) | Would make the evidence package falsifiable by the same effect that deceives the operator, destroying the measurement. |
| Reuse the backstop's policy engine to evaluate invariants | Produces a tautology in the flagship result. |
| Two-valued OK/VIOLATED status | Loses margin and early-warning measurement, which is a large part of what distinguishes an engineered control from an alarm. |

## Consequences

**Positive.** Invariants are testable in isolation, produce structured evidence with duration
and peak-excursion data, and cannot be gamed by telemetry manipulation.

**Negative.** Stateful invariants must be reset between experiments; a leaked instance would
silently corrupt a run. Mitigated by constructing invariants fresh per experiment inside the
runner and asserting this in an integration test.

**Negative.** These are *safety properties over simulated state*. They are not a hazard
analysis, not a HAZOP, and not a safety case. `docs/limitations.md` says so explicitly.

## Security implications

INV-006 makes loss of telemetry integrity a first-class, measured condition rather than an
untracked assumption, and is the property SCN-003 is built to exercise.
