# Baseline Experiment — Independent Engineering Constraint

**Status:** complete · **BLACKSTART v0.1.0** · **Seed 4242**
**Evidence:** [`../../evidence/baseline/`](../../evidence/baseline/)

---

## Research question

> Given that an adversary has achieved unauthorised control influence, which
> engineered constraint prevents that influence from becoming an unacceptable
> physical consequence?

---

## Design

A controlled comparison. Same scenario, same seed, same configuration, differing
in exactly one respect: whether the independent engineering constraint EBS-001 is
present.

| | |
| --- | --- |
| Scenario | SCN-004 — unauthorised setpoint mutation |
| Effect | `setpoint.override` to 4.80 m at t = 180 s, persisting |
| Duration | 1200 s at a 0.5 s timestep (2400 steps) |
| Control case | `backstop-disabled` — strict pass-through |
| Treatment | `backstop-enabled` — EBS-001 active |
| Reference | SCN-001 nominal operation, to establish a clean baseline |

The setpoint is mutated to 4.80 m, above the INV-001 safe working level of 4.50 m.
Every digital component then behaves exactly as designed: the controller
faithfully pursues the setpoint it was given, and the instrumentation reports
honestly. Nothing malfunctions.

### Validity controls

| Control | Why it is needed |
| --- | --- |
| Disabled variant is a strict pass-through | Otherwise the comparison measures two differences |
| Invariant checker shares no code with the backstop | Otherwise "enabled ⇒ no violations" is a tautology |
| Backstop thresholds tighter than invariant limits | Otherwise the constraint could not act before the limit |
| Finding re-checked across four seeds | Otherwise it could be a single-seed artefact |
| SCN-001 baseline is clean | Otherwise no violation anywhere is interpretable |

---

## Reference baseline — SCN-001

`EXP-SCN001-backstop-enabled-76026f68`

Maximum consequence **C0**, zero invariant violations, 100% service availability,
level held between 2.795 m and 3.596 m against limits of 1.00 m and 4.50 m, two
pump starts, no backstop rule activated.

The constraint is invisible during normal operation — asserted numerically by
`test_the_backstop_does_not_disturb_nominal_operation`. A safety control that
changed normal behaviour would be a liability.

---

## Result

| Metric | Backstop disabled | Backstop enabled |
| --- | --- | --- |
| Maximum consequence | **C4** — unsafe physical state | **C1** — minor deviation |
| Invariant violations | 2 | 1 |
| Violated invariants | INV-001, INV-004 | INV-004 |
| Service availability | 46.71% | **100.00%** |
| Unsafe-state duration | **639.5 s** (53.3% of run) | **0.0 s** |
| Maximum tank level | **5.000 m** (weir crest) | 3.9998 m |
| Max deviation from legitimate setpoint | 1.800 m | 0.800 m |
| Spill volume | **3.382 m³** | 0.000 m³ |
| INV-001 first violated | t = 560.5 s | never |
| INV-001 peak excursion | 0.500 m above the limit | — |
| Backstop activations | none (disabled) | BS-01 × 2040, BS-02 × 16 |
| High-level trips (BS-03) | — | **0** |

Experiment IDs: `EXP-SCN004-backstop-disabled-a6e4affc`,
`EXP-SCN004-backstop-enabled-457bc4c1`.

---

## Findings

### F1 — The constraint prevented the unsafe physical state

Without it the process spent 639.5 s above its safe working level, reached the
weir crest, and discharged 3.382 m³. With it the level peaked at 3.9998 m — a
0.50 m margin to the safety limit — and INV-001 was never violated.

### F2 — The setpoint clamp did the work; the trip never fired

BS-01 acted on 2040 scans and BS-02 on 16. **BS-03 fired zero times.**

This matters more than the headline. The constraint worked by ensuring the
controller never pursued an unsafe target in the first place, not by catching the
result at the last moment. Two independent layers existed and only the outer one
was needed.

It is also a corrected design. An earlier revision applied the clamp *downstream*
of the control request; the controller then chased 4.80 m and was stopped only by
the trip, peaking at 4.19 m against a 4.20 m trip level and a 4.50 m limit. Moving
the clamp upstream restored the margin from 0.31 m to 0.50 m. The scenario had
"passed" either way — which is why activation counts are reported per rule.

### F3 — Service availability fell without any loss of service

46.71% in the control case, while demand was met throughout.

CF-001 requires **both** delivered service **and** no violated safety invariant.
A process delivering water perfectly while sitting above its safe level is not
performing its critical function. Reporting this as a service outage would be
wrong; reporting it as full availability would be worse.

### F4 — The anomalous command was detectable in both variants

INV-004 was violated at t = 180.0 s in **both** runs, with an identical peak slew
of 6.0 m/s against a 0.05 m/s limit.

INV-004 observes the **requested** setpoint, not the constrained one. The evidence
that a physically implausible command was issued survives the constraint refusing
it — a detection opportunity that does not depend on the defence having failed.

Note this is a *latent* opportunity. BLACKSTART v0.1 consumes no such signal;
detection metrics read `NOT_IMPLEMENTED`.

### F5 — Recovery is undefined here, and is reported as such

The override persists to the end of the experiment, so the process never leaves
the disturbed condition. Both runs report
`effect_persists_to_end_of_experiment` rather than a misleading null or a zero.

### F6 — The architectural reduction is modest

Of 40 enumerated dependency paths reaching C4 or above, the backstop interrupts
18 — **45%**. Every `CTRL-RESERVE → VLV-001` path remains uninterrupted: the
constraint covers the pump command path and applies nothing to the valve.

A real gap, surfaced by querying the model rather than by inspection.

---

## What this does not establish

- That a comparable constraint would work in a real plant.
- That the assumed compromise is achievable in a real plant. BLACKSTART models
  effects, not mechanisms, and offers no evidence in either direction.
- That the constraint resists a compromise of **itself**, or of its independent
  measurement channel. Both are assumed away
  ([A2, A3](../../threat-model/assumptions.md)), and both are the assumptions most
  likely to invalidate this result in a real system.
- Anything statistical. One seed per run, four seeds for the sanity check, no
  confidence intervals, no significance claim.

See [../../docs/limitations.md](../../docs/limitations.md).

---

## Reproducing

```bash
make bootstrap
make demo
uv run blackstart evidence verify --all --reproduce --evidence-root evidence/baseline
```

The committed packages are verified and byte-for-byte reproduced in CI on every
change, so a code change that silently altered these numbers fails the build.
