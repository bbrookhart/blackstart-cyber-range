# Experiment EXP-SCN004-backstop-disabled-d14f929b

**Scenario:** SCN-004 — Unauthorised setpoint mutation
**Variant:** backstop-disabled (Control case. No independent engineering constraint on commands.)
**Seed:** 4242 · **Configuration hash:** `d14f929bef2b4bc8…`
**BLACKSTART version:** 0.1.0

## Research question

> Given that an adversary has achieved unauthorised control influence, which engineered constraint prevents that influence from becoming an unacceptable physical consequence?

## What was simulated

The supervisory level setpoint is changed to a value above the safe working level by something other than legitimate operator action. The controller is functioning perfectly: it faithfully pursues the setpoint it was given. The instrumentation is honest. Every digital component behaves exactly as designed.
The process still ends up outside its safe envelope, because nothing in the control path is responsible for deciding whether a setpoint is a sensible one.
This is the flagship experiment. It is run twice under identical configuration and seed, differing in exactly one respect: whether the independent engineering constraint EBS-001 is present. The measured difference between the two runs is the project's central result.
Note what is NOT modelled. BLACKSTART does not simulate how the setpoint came to be changed -- no authentication is bypassed, no protocol frame is crafted, no flaw is exploited. The scenario assumes the influence and measures the consequence. Whether such influence is achievable against any real system is not a question this range can answer.

| t (s) | Effect | Description |
| --- | --- | --- |
| 180.0 | `setpoint.override` | Level setpoint mutated from 3.20 m to 4.80 m, above the INV-001 safe working level of 4.50 m. |

## Measured result

| Metric | Value |
| --- | --- |
| Maximum consequence | **C4** |
| Invariant violations | **3** |
| Violated invariants | INV-001, INV-004, INV-005 |
| Service availability | 46.71% |
| Unsafe-state duration | 639.5 s (53.3% of run) |
| Maximum tank level | 5.000 m (safe limit 4.50 m) |
| Minimum tank level | 2.801 m (reserve 1.00 m) |
| Max deviation from legitimate setpoint | 1.800 m |
| Spill volume | 3.382 m³ |
| Supervisory availability | 100.00% |
| Pump starts | 1 |
| Recovery | effect_persists_to_end_of_experiment |

## Safety invariants

| ID | Name | Status | Detail |
| --- | --- | --- | --- |
| INV-001 | Maximum safe tank level | VIOLATED | — 1 interval(s), 639.5 s total, first at t=560.5 s, peak 0.500 |
| INV-002 | Minimum operational reserve | ok | |
| INV-003 | Pump dry-run protection | ok | |
| INV-004 | Command-rate constraint | VIOLATED | — 1 interval(s), 0.5 s total, first at t=180.0 s, peak 6.000 |
| INV-005 | Effective control setpoint bound | VIOLATED | — 1 interval(s), 1020.0 s total, first at t=180.0 s, peak 1.200 |
| INV-006 | Telemetry integrity awareness | ok | |

## Engineering backstop

Backstop **disabled** for this run.

Rule activations: BS-01=0, BS-02=0, BS-03=0, BS-04=0, BS-05=0

High-level trip count: 0

A rule showing zero activations did not act in this experiment. BS-05 is
redundant with the controller's own anti-cycling under the shipped scenarios and
is expected to read zero.

## Reproducing this experiment

```bash
uv run blackstart experiment run SCN-004 --variant backstop-disabled
uv run blackstart evidence verify EXP-SCN004-backstop-disabled-d14f929b
```

The experiment identifier is derived from the configuration hash, so an
identical run reproduces this package byte-for-byte.

## Limitations

This is a simulation result. It describes the behaviour of the BLACKSTART model
under the stated configuration and seed. It does not establish how any real
water utility, control system, or piece of equipment would behave. See
`docs/limitations.md`.

Detection and containment latency are reported as `NOT_IMPLEMENTED`: BLACKSTART
v0.1 emits no network telemetry and runs no detection analytic, so those metrics
have no basis.
