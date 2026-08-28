# EXP-BS-001 Assurance Case

This is a research assurance argument over a synthetic model. It is not a safety
case, certification, or claim about an operational water system.

## Top-level context

- **Context C1:** frozen experiment `EXP-BS-001-v1` and `SCN-004`.
- **Context C2:** untrusted supervisory requested setpoint; EBS-001 remains
  outside the modeled compromise.
- **Context C3:** true maximum-safe level is 4.50 m; allowed effective target is
  1.50–3.60 m.
- **Context C4:** both conditions use the same code fingerprint, initial state,
  demand, seed 4242, timestep 0.5 s, and attack event at 180 s.

## Claim BS-C1 — bounded effective control

**Claim.** Under the documented `SCN-004` threat model, an unauthorized
supervisory setpoint request cannot cause the effective control value to exceed
the configured engineering limit while the independent backstop is active.

**Argument.** The scenario writes only the requested value. EBS-001 evaluates
that value on a separate policy path before the normal controller receives the
effective target. BS-01 clamps values above 3.60 m, and INV-005 independently
evaluates the effective target on every timestep.

**Evidence.**

- unit boundary/violation/recovery tests for `SetpointBoundInvariant` and BS-01;
- Hypothesis property: backstop enabled plus unsafe request implies effective
  target at or below the configured maximum;
- protected `control.csv`: request remains 4.80 m while effective target is
  at most 3.60 m;
- protected `invariants.json`: no INV-005 violation;
- `verification.json` and verified manifest hashes bind the evidence package.

**Assumptions.** EBS-001 policy, configuration, and code are not writable by the
modeled scenario; the orchestrator correctly distinguishes requested and
effective values; the evidence writer preserves the trace.

## Claim BS-C2 — lower physical consequence

**Claim.** Under the frozen `EXP-BS-001-v1` configuration, the protected
condition produces lower physical consequence than the equivalent unprotected
condition.

**Argument.** The two deterministic conditions differ only in backstop state.
The unprotected controller pursues 4.80 m; the protected controller receives a
bounded effective target. Metrics are derived from true physical state, not from
scenario intent or operator-facing telemetry.

**Evidence.**

| Observation | Backstop OFF | Backstop ON |
| --- | ---: | ---: |
| Maximum true level | 5.0000 m | 3.9998 m |
| Unsafe-state duration | 639.5 s | 0.0 s |
| Minimum safety margin | −0.5000 m | +0.5002 m |
| Maximum consequence | C4 | C1 |
| Mission service availability | 46.7083% | 100.0000% |

The primary metrics engine and an independent reader of `process.csv` agree on
maximum level, unsafe duration, invariant violation count, and maximum
consequence. Deterministic reproduction compares serialized artifacts.

**Assumptions.** The simplified equations adequately implement the phenomenon
claimed; configuration equality isolates backstop state; consequence thresholds
are applied correctly; EBS-001 is outside the modeled compromise.

## Defeaters and residual risk

Either claim must be weakened or withdrawn if the backstop can be modified
through the compromised path, if true state is not available to the evidence
path, if a run changes more than the backstop state, or if independent
recalculation disagrees. Neither claim covers valve-path compromise, shared-mode
failure, physical calibration, real PLC execution, network timing, or a real
adversary.

## Precise supported conclusion

> In the documented synthetic process model and experimental configuration, the
> engineering backstop prevented the tested supervisory-control mutation from
> producing the physical consequence observed in the unprotected condition.
