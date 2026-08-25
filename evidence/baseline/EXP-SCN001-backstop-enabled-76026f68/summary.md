# Experiment EXP-SCN001-backstop-enabled-76026f68

**Scenario:** SCN-001 — Nominal operation
**Variant:** backstop-enabled (Independent engineering constraint EBS-001 active.)
**Seed:** 42 · **Configuration hash:** `76026f68a844f5db…`
**BLACKSTART version:** 0.1.0

## Research question

> What does correct operation look like, and does the instrument suite report zero invariant violations and zero consequence when nothing is wrong?

## What was simulated

Nominal process behaviour under synthetic variable demand. The hysteresis level controller cycles the pump between the band edges; demand is met continuously; the reported and true views of the process agree within transmitter noise.
This is the baseline every other result is read against. A range that cannot demonstrate a clean baseline cannot support a claim about anything else: if SCN-001 produced spurious violations, no violation in any other scenario would be interpretable.

| t (s) | Effect | Description |
| --- | --- | --- |
| — | — | No scenario events; nominal operation. |

## Measured result

| Metric | Value |
| --- | --- |
| Maximum consequence | **C0** |
| Invariant violations | **0** |
| Violated invariants | none |
| Service availability | 100.00% |
| Unsafe-state duration | 0.0 s (0.0% of run) |
| Maximum tank level | 3.596 m (safe limit 4.50 m) |
| Minimum tank level | 2.795 m (reserve 1.00 m) |
| Max deviation from legitimate setpoint | 0.405 m |
| Spill volume | 0.000 m³ |
| Supervisory availability | 100.00% |
| Pump starts | 2 |
| Recovery | no_disturbance |

## Safety invariants

| ID | Name | Status | Detail |
| --- | --- | --- | --- |
| INV-001 | Maximum safe tank level | ok | |
| INV-002 | Minimum operational reserve | ok | |
| INV-003 | Pump dry-run protection | ok | |
| INV-004 | Command-rate constraint | ok | — approached limit for 191.0 s |
| INV-005 | Telemetry integrity awareness | ok | |

## Engineering backstop

Backstop **enabled** for this run.

Rule activations: BS-01=0, BS-02=0, BS-03=0, BS-04=0, BS-05=0

High-level trip count: 0

A rule showing zero activations did not act in this experiment. BS-05 is
redundant with the controller's own anti-cycling under the shipped scenarios and
is expected to read zero.

## Reproducing this experiment

```bash
uv run blackstart experiment run SCN-001 --variant backstop-enabled
uv run blackstart evidence verify EXP-SCN001-backstop-enabled-76026f68
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
