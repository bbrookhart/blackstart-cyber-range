# Physical Process Model

A deterministic, lumped-parameter model of a fictional municipal water storage
and pumping process. Every parameter is synthetic; see
[research-integrity.md](research-integrity.md).

Design rationale and alternatives considered:
[ADR-002](adr/ADR-002-physical-process-model.md).
Configuration: [`configs/process.yaml`](../configs/process.yaml).
Implementation: [`blackstart/core/physics/process.py`](../blackstart/core/physics/process.py).

---

## Topology

```text
   Source reservoir  (RES-001)
        │  suction limit 0.50 m
        ▼
      Pump  (PMP-001)          linear curve, 0.200 m³/s at zero head
        │                      shutoff head 6.50 m
        ▼
   Storage tank  (TNK-001)     area 12.0 m², weir crest 5.00 m
        │                      ── safe working level 4.50 m  (INV-001)
        │                      ── operating band 2.80–3.60 m
        │                      ── operational reserve 1.00 m (INV-002)
        ▼
   Outlet valve  (VLV-001)     Cd 0.62, orifice 0.020 m²
        │
        ▼
   Synthetic demand            0.035 m³/s nominal, ±10%
```

## State variable and mass balance

One state variable: tank level `L` (m) over constant area `A` (m²).

```text
dL/dt = (q_in − q_out) / A
```

Integrated by **explicit Euler** at a fixed `dt = 0.5 s`.

## Pump inflow — linear curve

A centrifugal pump delivers less flow against greater static head:

```text
q_in = energised · q_nominal · clamp(1 − L / H_shutoff, 0, 1)
```

With `q_nominal = 0.200 m³/s` and `H_shutoff = 6.50 m`, delivery is 0.100 m³/s at
`L = 3.25 m` and falls to zero at 6.50 m.

**Dry-run condition.** If the source level is at or below the suction limit
(0.50 m), `q_in = 0` **while the pump remains energised**. The motor draws
current and delivers nothing. This is a genuinely damaging state that is invisible
in a level trend alone, and it is what INV-003 exists to detect.

## Outlet — gravity discharge through a throttling valve

Torricelli discharge, limited by valve position, then by what the customer asks
for:

```text
q_capacity = position · C_d · A_orifice · √(2 · g · L)
q_out      = min(demand, q_capacity)
```

**Service shortfall is emergent.** `demand − q_out` is a consequence of the
hydraulics, not a flag anyone sets. This is what makes the C2/C3 consequence
classes meaningful: at low level the tank simply cannot deliver what is asked of
it, and the model says so without being told.

A further bound stops the tank supplying more than it holds:

```text
q_out ≤ (L · A) / dt + q_in
```

This, rather than a clamp, is why the level can never integrate negative — a
property checked by a Hypothesis test over the whole reachable input space.

## Overflow

Volume driven above the weir crest (5.00 m) leaves the system and accumulates as
`spill_volume_m3`.

The **safe working level (4.50 m) sits deliberately below the weir crest**, so a
safety excursion is an observable, recoverable state rather than an
unrepresentable one. Between 4.50 m and 5.00 m the process is unsafe but
contained; only above 5.00 m is containment actually lost.

## Instrumentation

Three channels, and the distinction between them carries the project's central
modelling decision.

| Channel | Reads | Noise σ | Affected by `sensor.*` effects |
| --- | --- | --- | --- |
| Level transmitter LIT-001 | Operator + controller | 0.005 m | **Yes** |
| Independent element LIT-002 | Backstop only | 0.010 m | **No** — assumption |
| Flow meter FIT-001 | Reporting | 0.0002 m³/s | No |

The controller acts on LIT-001. It has no other information about level. That is
not a simplification — it is what makes loss of telemetry integrity a real
phenomenon rather than an annotation, and it is why SCN-003 is measurable.

LIT-002's independence is a **modelling assumption**, stated in the configuration,
in the backstop's implementation, and in [limitations.md](limitations.md). A real
independent element can itself be compromised.

## Control

Hysteresis level control on the reported level, executing on a 1.0 s PLC scan
against a 0.5 s physics step, so control action is quantised and slightly stale
by construction.

- Pump starts at or below `setpoint − 0.40 m`, stops at or above `setpoint + 0.40 m`
- Minimum run time 20 s, minimum off time 30 s (motor protection)
- Nominal operation cycles at roughly 8.6 starts/hour against a 12/hour limit
- **Reserve protection:** below a reported 1.50 m the outlet is throttled to 0.35,
  releasing above 1.80 m — deliberately trading delivered service for reserve
  volume

## Determinism

The only stochastic inputs are instrument noise and demand variation, both drawn
from a single explicitly seeded `random.Random` threaded through the runner. No
module uses the global generator; a property test probes module-level random state
directly to prove it.

## Verifying the numbers

Every figure above appears in `configs/process.yaml` and is checked at load:

```bash
uv run blackstart config validate
uv run pytest tests/unit/test_physics.py tests/unit/test_config.py -q
```

Configuration that is physically incoherent is rejected rather than simulated: an
unstable timestep for the process time constant, an initial level above the tank,
a control band reaching the weir, a safe limit at or above the overflow height, or
a backstop threshold that could not act before the limit it claims to protect.

## What this model cannot represent

No transport delay, pipe dynamics, water hammer, thermal effects, equipment wear,
cavitation damage, water quality, variable-speed drives, or multiple
tanks/pumps/zones. See [limitations.md](limitations.md) §4.
