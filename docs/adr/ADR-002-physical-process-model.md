# ADR-002 — Physical process model

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

BLACKSTART models a fictional municipal water storage and pumping process. The model must be
faithful enough that consequence classification is meaningful, and simple enough that a
reviewer can verify every equation by inspection. Excess fidelity in v0.1 buys no research
value and costs reviewability.

All parameters are synthetic. No real utility's hydraulics, setpoints, or equipment ratings
were used.

## Decision

A lumped-parameter, discrete-time model integrated with **explicit Euler** at a fixed
timestep `dt = 0.5 s`.

**State variable.** Tank level `L` (m) over a constant cross-sectional area `A` (m²).

**Mass balance.**

```text
dL/dt = (q_in - q_out) / A
```

**Pump inflow — linear pump curve.** A centrifugal pump delivers less flow as it works
against a higher static head:

```text
q_in = pump_running · q_nominal · clamp(1 − L / H_shutoff, 0, 1)
```

`H_shutoff` is the shutoff head at which the pump delivers zero flow. If the source reservoir
is below the dry-run threshold, the pump loses suction and `q_in = 0` while the pump remains
energised — this is the physically damaging condition INV-003 exists to detect.

**Outlet — gravity discharge through a throttling valve.** Torricelli discharge, limited by
valve position:

```text
q_capacity = valve_position · C_d · A_orifice · sqrt(2 · g · max(L, 0))
q_out      = min(demand, q_capacity)
```

Delivered flow is therefore the lesser of what the customer asks for and what the hydraulics
can supply. Service shortfall — the basis of the C2/C3 consequence classes — is
`demand − q_out`, an emergent property of the physics rather than a flag someone sets.

**Physical bounds.** `L` is clamped to `[0, H_tank]`. Volume driven above `H_tank` leaves via
the overflow weir and is accumulated as `spill_volume_m3`. The *safe* maximum level
(INV-001, 4.50 m) is deliberately set **below** the physical overflow height (5.00 m) so that
an invariant violation is a real, observable, recoverable excursion rather than an
unrepresentable state.

**Determinism.** The only stochastic input is demand variation, drawn from an explicitly
seeded `random.Random`. No global RNG is used anywhere in the kernel.

## Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| RK4 integration | At `dt = 0.5 s` against tank time constants of minutes, Euler error is negligible relative to model uncertainty. RK4 would require evaluating discrete controller state mid-step, which is not well defined. |
| Quadratic pump curve `q = q₀·sqrt(1 − (L/H)²)` | More realistic; not more instructive. The linear curve is verifiable by inspection and monotone, which the property tests rely on. |
| Full pipe network with friction losses (Hazen–Williams) | Adds parameters that are pure invention and cannot be validated, while changing no consequence outcome. |
| Modelling pressure rather than level | Level is directly observable, directly relatable to service, and directly bounded. Pressure adds an unnecessary transform. |

## Consequences

**Positive.** Every equation is checkable in one screen. Service degradation and unsafe level
are both *derived* from the same mass balance, so consequence classes cannot disagree with the
physics.

**Negative.** The model has no transport delay, no pipe dynamics, no thermal effects, and no
pump wear model. Consequently BLACKSTART cannot make claims about equipment damage rates or
transient pressure phenomena (water hammer). Recorded in `docs/limitations.md`.

**Negative.** Explicit Euler is only conditionally stable. `dt` is validated at configuration
load against the fastest process time constant, and the check is unit-tested.

## Security implications

Because the true physical state is a distinct object from the reported sensor state
(ADR-004), no scenario effect that manipulates telemetry can alter the physics. This makes
"the operator was deceived" and "the process was damaged" independently measurable, which is
what SCN-003 exists to study.
