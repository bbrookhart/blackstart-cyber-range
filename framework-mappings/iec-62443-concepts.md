# IEC 62443 — Concepts Applied

**Informational. Not a conformance or certification claim.**

The IEC 62443 series is copyrighted and largely paywalled. **No standard text is
reproduced here.** This document describes how BLACKSTART applies concepts from
the series that are publicly and widely discussed, in the project's own words.

Nothing in this repository is evaluated, assessed or certified against any part
of the series, and no Security Level is claimed.

---

## Zones and conduits

The organising idea BLACKSTART uses most directly: group assets with common
security requirements into *zones*, and treat every communication path between
zones as a named, enumerable *conduit* that can be controlled and inspected.

BLACKSTART implements four zones with four isolated networks:

| Zone | Contains | Trust characterisation |
| --- | --- | --- |
| Enterprise | Read-only reporting workstation | Untrusted for control |
| Industrial DMZ | Telemetry broker | Brokered |
| OT supervisory | Historian, HMI | Operational |
| Control / process | Controller, backstop, process twin | Safety-relevant |

Four conduits are declared, each with an identifier, initiator, responder,
protocol, port, direction and a description of what data crosses. The structural
property that gives this meaning:

> No service is attached to more than two adjacent zone networks, and no service
> is attached to both the enterprise network and any OT-side network.

Every cross-zone flow therefore traverses a named broker, and there is no path
that skips a layer. Reaching the controller from the enterprise zone requires
transiting three separate services.

**Only one conduit carries commands.** CDT-004, from the OT supervisory zone to
the control zone, is the sole path on which a control command may travel — and
every command crossing it is subject to the engineering backstop.

All of this is asserted by `tests/architecture/test_zone_topology.py` against the
actual `docker-compose.yml`, not merely described.

---

## Defence in depth

BLACKSTART layers three distinct kinds of defence, and the flagship experiments
are designed so that each layer's contribution is separately visible:

1. **Topological** — segmentation and brokered conduits.
2. **Functional** — the controller's own anti-cycling and reserve protection.
3. **Engineered constraint** — the backstop, which does not depend on the
   correctness of either layer above it.

The third layer is the interesting one, and the scenarios isolate which *rule*
acts in which case. In SCN-004 the setpoint clamp (BS-01) does the work and the
high-level trip never fires. In SCN-003 the setpoint is entirely legitimate and
only the independent high-level trip (BS-03) can help. Two scenarios, two
different defences, each demonstrated rather than asserted.

---

## Essential functions and their protection

The series treats the continued operation of *essential functions* as something
security measures must not themselves impair. BLACKSTART reflects this in two
ways:

- The critical function CF-001 is defined first, with a quantitative satisfaction
  predicate, and everything else is derived from it.
- `test_the_backstop_does_not_disturb_nominal_operation` asserts that with the
  constraint enabled, nominal operation is numerically identical to nominal
  operation without it. A safety control that changed normal behaviour would be
  a liability, and the test exists so that cannot happen unnoticed.

---

## Independence of protective functions

The concept that a protective function should not share failure modes with the
system it protects is the reason the backstop is built the way it is:

- It reads an **independent measurement channel** (LIT-002), not the operator
  transmitter that a scenario may have falsified.
- Its thresholds are loaded at construction and are **never writable at runtime**
  by any modelled command path.
- It shares **no code** with the invariant checker that measures outcomes —
  asserted by AST analysis — so "constraint enabled implies no violations" is a
  measurement rather than a tautology.

**Stated limitation:** the independence of the measurement channel is a
*modelling assumption*. A real independent element can itself be compromised.
See [../threat-model/assumptions.md](../threat-model/assumptions.md) (A3).

---

## Security levels

**Not claimed, not assessed, not applicable.** Security Levels in the series
carry specific meanings tied to assessed capability against defined threat
classes. BLACKSTART performs no such assessment and assigns no level. Any
statement that this repository achieves an SL would be false.

---

## Lifecycle considerations

BLACKSTART is a research artefact, not a product, and most lifecycle guidance in
the series does not apply. Two things it does do:

- Consequential design decisions are recorded as ADRs with context, alternatives,
  consequences and security implications.
- Configuration is versioned, hashed, cross-validated at load, and recorded in
  every evidence package, so a result can never be silently attributed to a
  configuration that did not produce it.

There is no patch management, no product security incident response process, and
no supported-product lifecycle.
