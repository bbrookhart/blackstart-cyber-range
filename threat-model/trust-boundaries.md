# Trust Boundaries

A trust boundary is a place where the assumptions about who may do what change.
BLACKSTART has five, and each one is enforced by something a reviewer can check —
a Docker network, a configuration validator, or a test — rather than by
convention.

---

## Boundary map

```text
                          ┌─────────────────────────────┐
   host loopback ────────►│  TB-1  host / enterprise    │  127.0.0.1:8080 only
                          └──────────────┬──────────────┘
                                         │
                          ┌──────────────▼──────────────┐
                          │  ENTERPRISE ZONE            │  enterprise-workstation
                          └──────────────┬──────────────┘
                          ┌──────────────▼──────────────┐
                          │  TB-2  enterprise / IDMZ    │  CDT-001, read-only pull
                          └──────────────┬──────────────┘
                          ┌──────────────▼──────────────┐
                          │  INDUSTRIAL DMZ             │  idmz-broker
                          └──────────────┬──────────────┘
                          ┌──────────────▼──────────────┐
                          │  TB-3  IDMZ / OT            │  CDT-002, read-only pull
                          └──────────────┬──────────────┘
                          ┌──────────────▼──────────────┐
                          │  OT SUPERVISORY ZONE        │  historian, hmi
                          └──────────────┬──────────────┘
                          ┌──────────────▼──────────────┐
                          │  TB-4  OT / control         │  CDT-004, THE command path
                          └──────────────┬──────────────┘
                          ┌──────────────▼──────────────┐
                          │  CONTROL / PROCESS ZONE     │  controller
                          │                             │
                          │   ┌───────────────────────┐ │
                          │   │ TB-5  command /       │ │  EBS-001
                          │   │       actuation       │ │  the last boundary
                          │   └───────────┬───────────┘ │
                          │   ┌───────────▼───────────┐ │
                          │   │  PHYSICAL PROCESS     │ │
                          │   └───────────────────────┘ │
                          └─────────────────────────────┘
```

---

## TB-1 — Host / enterprise zone

**Trust change:** from "anything on this machine" to "the range".

**What crosses:** HTTP GET requests to the read-only enterprise dashboard on
`127.0.0.1:8080`. Nothing else. No POST endpoint exists on the published service.

**Enforced by:** a single `ports:` entry bound explicitly to loopback; the IDMZ,
OT and control networks declared `internal`.

**Verified by:** `tests/architecture/test_exposure_and_posture.py` asserts only
one service publishes, only on loopback, and never a control-side port. CI
additionally proves from the running topology that ports 8081–8084 are
unreachable from the host.

**Assumption:** the operator does not rebind the port to `0.0.0.0`.

---

## TB-2 — Enterprise zone / industrial DMZ

**Trust change:** from administrative IT — the zone assumed most likely to be
compromised — to a brokered boundary.

**What crosses:** conduit CDT-001. The enterprise workstation *pulls* a reduced
process summary from the broker. Six named fields cross; the setpoint, the
requested setpoint, and backstop rule detail do not.

**Direction:** outward only. No command path exists inward from this zone.

**Enforced by:** `idmz-broker` is the only service attached to both
`blackstart_enterprise` and an OT-side network. The broker's permitted-field list
is explicit in code.

**Verified by:** `test_exactly_one_service_bridges_enterprise_and_the_ot_side`,
and `test_narrows_what_crosses_the_boundary` in the service suite.

---

## TB-3 — Industrial DMZ / OT supervisory zone

**Trust change:** from a brokered boundary to operational systems.

**What crosses:** conduit CDT-002. The broker pulls historian query results.
Read-only.

**Enforced by:** `historian` is attached to `blackstart_idmz` and
`blackstart_ot`, and to nothing else. The enterprise workstation has no route to
it — reaching the historian from the enterprise zone requires transiting the
broker.

---

## TB-4 — OT supervisory zone / control zone

**Trust change:** from supervisory systems to safety-relevant control.

**This is the only boundary a control command crosses.** Conduit CDT-004 is the
sole `pull+command` conduit in the architecture, asserted by
`test_only_one_conduit_carries_commands`.

**What crosses:** process state outward; operator setpoint writes inward.

**Enforced by:** `hmi` is attached to `blackstart_ot` and `blackstart_control`.
`controller` is attached to `blackstart_control` only. Reaching the controller
from the enterprise zone requires three hops through three separate services,
asserted by `test_a_path_from_enterprise_to_control_requires_three_hops`.

**Critical property:** the controller **accepts** a setpoint write and records
its declared origin. It does not use that origin to decide anything. Acceptance
is not authorisation — the constraint at TB-5 applies identically regardless of
what the writer claimed to be. A boundary that depended on correctly attributing
commands would fail exactly when attribution failed.

---

## TB-5 — Command / actuation

The innermost boundary, and the one BLACKSTART exists to study. It is not a
network boundary at all.

**Trust change:** from "a command has been issued by something" to "an actuator
will move".

**What crosses:** a control request, in two stages.

1. **Setpoint constraint** (BS-01, BS-02), applied *upstream of the controller*
   so that the controller never pursues an out-of-range target.
2. **Actuator interlocks** (BS-03, BS-04, BS-05), applied to the formed control
   request, driven by the independent level element and the source level.

**Why it is placed there.** Constraining the setpoint after the control request
was formed would leave the controller chasing an unsafe target and rely entirely
on the pump trip to catch the result — defence by a single layer instead of two.
An earlier version of this project made exactly that mistake; SCN-004 was then
stopped only by the high-level trip, at 4.19 m against a 4.50 m limit, instead of
by the setpoint clamp at 4.00 m.

**Enforced by:** `EngineeringBackstop`, which imports nothing from
`blackstart.core.invariants` and reads policy that is never writable at runtime.

**Verified by:**
- `test_pump_is_never_permitted_above_the_trip_level` (property-based, over the
  whole input space)
- `test_effective_setpoint_never_leaves_the_permitted_range` (property-based)
- `test_thresholds_are_not_writable_at_runtime`
- `test_shares_no_code_with_the_invariant_checker` — without this, "backstop
  enabled implies no violations" would be a tautology rather than a measurement

**Known gap:** TB-5 constrains the **pump** command path and the level setpoint.
It applies no constraint to outlet valve commands. Every
`CTRL-RESERVE → VLV-001` consequence path is uninterrupted, which
`threat-model/consequence-paths.yaml` records and a test keeps visible.

---

## The evidence boundary

One further separation is not a zone boundary but matters as much.

**Ground truth is not reachable from the reported view.** Invariants evaluate
`TruthState`; the controller and HMI act on `ReportedState`; only INV-005 reads
both, and only to compare them.

Consequently a scenario effect that deceives the operator **cannot** falsify the
experimental record. In SCN-003 the HMI shows a plausible, stable, wrong level
while INV-001 records the true excursion and INV-005 records the deception. Both
facts land in the evidence package.

This is why "the process was damaged" and "the operator was deceived" are
separately measurable outcomes rather than a single conflated one.
