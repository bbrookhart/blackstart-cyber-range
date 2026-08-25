# Limitations

What BLACKSTART v0.1 **cannot** establish.

This document is deliberately placed early in the documentation set and linked
from the README, the threat model, and every experiment's `summary.md`. A
research artefact whose limitations are harder to find than its results is
advertising.

---

## 1. The most important one

**A BLACKSTART result describes BLACKSTART.**

It is a simulation of a fictional municipal water process whose every parameter
was invented. It is not evidence about how any real water utility, control
system, pump, valve, transmitter or PLC would behave.

Specifically, the flagship result — that an independent engineering constraint
reduced the maximum consequence from C4 to C1 — establishes that *in this model,
under this configuration, at this seed*, the constraint changed the outcome. It
does not establish that:

- a comparable constraint would work in a real plant;
- the assumed compromise is achievable in a real plant;
- the consequence classes correspond to real operational severities;
- the physical model is adequate for any real hydraulic system.

---

## 2. Effects, not mechanisms

BLACKSTART models the **effects** of compromise, not the **mechanisms** of
intrusion.

`setpoint.override` writes to a field. It does not authenticate, bypass
authentication, craft a protocol frame, or exploit a flaw. The scenarios begin
from a position of achieved influence.

Consequently BLACKSTART **cannot tell you whether such influence is achievable**
against any particular system, how difficult it would be, or how it would be
obtained. That question is deliberately out of scope
([ADR-006](adr/ADR-006-scenario-safety-boundary.md)), and the project offers no
evidence on it in either direction.

This also means a defence that appears effective here might be bypassed by a
mechanism rather than confronted by the constraint. An engineering constraint
evaluated inside the same controller that was compromised to issue the command
is not the independent constraint this model assumes.

---

## 3. No detection capability whatsoever

BLACKSTART v0.1 emits **no network telemetry** and runs **no detection
analytic**. There is no IDS, no rule, no signature, no model, no baseline.

Therefore:

- `detection_latency_s`, `containment_latency_s` and `false_positive_rate` are
  reported as the literal string `NOT_IMPLEMENTED`. They are not zero, not null,
  and not omitted — reporting a detection latency of `0.0` would be a
  fabrication.
- No claim is made or supported about whether any modelled condition would be
  detected in practice.
- The ATT&CK for ICS mappings describe what is **simulated**, not what is
  **detected**.

INV-004 is a *latent* detection opportunity — it records that a physically
implausible command was issued, whether or not it succeeded — but nothing
consumes that signal. This is the largest single gap in the release.

---

## 4. Physical model limitations

The model is a lumped-parameter tank with a linear pump curve and Torricelli
outlet discharge, integrated by explicit Euler ([ADR-002](adr/ADR-002-physical-process-model.md)).

It has **no**:

- transport delay or pipe dynamics;
- transient pressure phenomena (water hammer);
- thermal effects;
- equipment wear or degradation model;
- pump cavitation damage model — INV-003 detects the *condition*, not damage;
- water quality, chemistry, contamination or treatment;
- multiple tanks, pumps, zones or interconnections;
- variable-speed drives — the pump is on or off.

BLACKSTART therefore cannot speak to equipment damage rates, transient pressure
events, water quality consequences, or any network-of-tanks behaviour.

Explicit Euler is only conditionally stable. Stability is validated at
configuration load against the dominant process time constant, and the check is
tested — but a contributor who changes the process substantially must re-verify
it.

---

## 5. The backstop's independence is an assumption

The high-level trip (BS-03) reads an independent level element modelled as a
separate hardwired channel unaffected by `sensor.*` effects.

**This independence is a modelling assumption, not a proven property.** A real
independent element can itself be compromised, mis-calibrated, or share a failure
mode with the primary transmitter (common cause, shared power, shared cabling,
shared vendor firmware).

If that assumption fails, SCN-003's backstop-enabled variant ends the way its
backstop-disabled variant does. See
[threat-model/assumptions.md](../threat-model/assumptions.md) A2 and A3 — these
are the two assumptions most likely to invalidate the flagship result in a real
system.

---

## 6. Known gap: the valve command path is unconstrained

The backstop constrains the **pump** command path and the level setpoint. It
applies **no constraint** to outlet valve commands.

Every consequence path of the form
`… → CTRL-RESERVE → VLV-001 → PROC-001 → INV-00x → C4` is uninterrupted. This is
recorded in [threat-model/consequence-paths.yaml](../threat-model/consequence-paths.yaml)
and held visible by a test so it cannot quietly disappear.

This is a real gap in the current design, not a modelling simplification.

---

## 7. Consequence-path counting is a weak metric

The reported "45% of high-consequence paths interrupted" counts **modelled
dependency paths**, not observed events, not exploitable routes, and not
probability.

Path counts are sensitive to how finely the model is decomposed: splitting one
node into two can change the number without changing anything real. They are not
commensurable across models, and should not be compared between projects or
tracked as a performance indicator.

The metric is reported with an interpretation note attached to it in the output
itself, for exactly this reason.

---

## 8. Segmentation demonstrates topology, not enforcement

The container topology demonstrates zone/conduit **structure**. Docker bridge
networks are not equivalent to physically separate networks with an inspecting
firewall.

BLACKSTART shows that an architecture *can be arranged* so that every cross-zone
flow traverses an enumerable broker, and it verifies that the deployed topology
matches the declared one. It does not demonstrate that the boundary would resist
an attacker who already had code execution inside a zone.

Additionally, the range has **no authentication, no authorisation and no
multi-tenancy**. Anyone who can reach a service can fully use it. This is
acceptable only because nothing is exposed beyond loopback.

---

## 9. Evidence is tamper-evident, not tamper-proof

Manifest digests detect corruption, partial writes, stale files and accidental
edits. **Anyone who can edit the artefacts can recompute the manifest.**

There is no signing, no trusted timestamp, and no external anchor. Evidence
integrity defends against accident, not against a motivated forger. Signing is a
roadmap item; claiming more today would be exactly the kind of overstatement this
project argues against.

---

## 10. Reproducibility has boundaries

Byte-level reproducibility holds for a fixed interpreter version and platform.
Different CPython versions or CPU architectures may alter floating-point
formatting in the last digit, which would change artefact digests without
changing any result.

Metric-level reproducibility (tolerance-based) is the portable guarantee.
Byte-level reproduction is verified in CI on one platform.

---

## 11. Statistical limitations

Each scenario runs at a **single declared seed**. The flagship finding is checked
across four seeds in the test suite, which is enough to show it is not a
single-seed artefact and **nowhere near** enough for a statistical claim.

No confidence intervals, distributions, or sensitivity analyses are produced. No
claim of statistical significance is made anywhere, because none would be
supportable.

---

## 12. No formal verification

The safety invariants are **tested**, not **proven**. Property-based tests
explore the input space broadly but do not exhaust it.

No temporal-logic specification, model checking, or theorem proving has been
performed. See [formal-assurance-roadmap.md](formal-assurance-roadmap.md) for
which properties would benefit and why they are not claimed today.

---

## 13. Not a safety case

This is not a hazard analysis, a HAZOP, a LOPA, a FMEA, a safety case, or a
functional-safety assessment. No SIL, no Security Level, no certification and no
regulatory conclusion is claimed or implied.

The invariants are *safety properties over simulated state*. They are not derived
from a hazard analysis of any real system, and their thresholds are invented.

---

## 14. Framework mappings are orientation only

All framework mappings are informational. They demonstrate no conformance and no
certification. CSF 2.0 is mapped at Function level only because Category and
Subcategory identifiers could not be verified against the authoritative
publication — see [framework-mappings/README.md](../framework-mappings/README.md).

ATT&CK for ICS coverage is four techniques across two tactics, and **none** of
the intrusion lifecycle.

---

## Summary

BLACKSTART v0.1 is a deep probe into one question — whether an engineered
constraint can stop assumed digital compromise from becoming unacceptable
physical consequence — in one small fictional system, with no detection
capability, no intrusion modelling, and no statistical power.

Read as that, it supports its claims. Read as anything broader, it does not.
