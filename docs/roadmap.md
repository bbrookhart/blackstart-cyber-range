# Research Roadmap

Ordered by research value, not by implementation ease.

Nothing here is implemented. Items marked 🟡 are planned; ⚪ are research
directions without a committed design.

---

## 🟡 M9 — Network telemetry and passive detection

**The single largest gap in v0.1**, and the reason every detection metric reads
`NOT_IMPLEMENTED`.

BLACKSTART currently models the *effects* of compromise with no network-observable
artefacts, so it cannot evaluate detection at all.

The work: emit synthetic network telemetry alongside process telemetry so that
passive analysis (Zeek-style connection and protocol records, Suricata-style
alerting) has something to consume. The event envelope was designed for this — it
is SIEM-agnostic precisely so a detection layer can be added without the physics
engine learning about any particular backend.

Unlocks: detection latency, containment latency, false-positive rate against the
SCN-002 benign disturbance — which is the interesting measurement, because a
detector that flags a demand surge is producing exactly the false positive the
scenario exists to expose.

**Design constraint:** this must be done without producing reusable protocol
attack tooling ([ADR-006](adr/ADR-006-scenario-safety-boundary.md)).

## 🟡 M10 — Constrain the valve command path

A known, recorded gap. The backstop constrains the pump command path and the level
setpoint and applies nothing to outlet valve commands; every
`CTRL-RESERVE → VLV-001` consequence path is uninterrupted.

Closing it would raise consequence-path reduction above 45% — but the more useful
outcome is the comparison itself, since a valve constraint trades service against
reserve in a way a pump constraint does not.

## 🟡 M11 — OT protocol emulation

Model a realistic control protocol between the HMI and controller so that command
paths have structure, timing and parseable frames.

Would let BLACKSTART reason about protocol-level detection opportunities and about
whether a constraint placed at the protocol boundary behaves differently from one
placed at the actuator. Raises the ADR-006 question directly and needs a design
that keeps any resulting capability non-reusable.

## 🟡 M12 — Evidence signing

Move evidence from tamper-*evident* to tamper-*resistant* with detached signatures
and a transparency-log anchor.

Blocked on a key-management story the project does not yet have. Until then the
integrity claim stays deliberately modest.

## 🟡 M13 — Formal verification of the backstop policy

Properties P1 and P2 from [formal-assurance-roadmap.md](formal-assurance-roadmap.md)
are finite-state and inductive, and are genuinely tractable. The hard part is the
refinement argument tying a model to the Python.

## 🟡 M14 — Statistical experimental design

Replace single-seed runs with seed sweeps, confidence intervals and sensitivity
analysis over the parameters that matter (demand variance, noise, tolerances).

Would let BLACKSTART say *how much* difference the constraint makes rather than
*that* it makes one.

---

## ⚪ Research directions

### Richer cyber-physical co-simulation

Sandia's **SCEPTRE** is a documented interoperability path for higher-fidelity
cyber-physical simulation. It is deliberately *not* a dependency of v0.1:
BLACKSTART must run standalone first ([ADR-001](adr/ADR-001-simulation-architecture.md)),
and a first release that required a large external research platform would be
unreviewable.

Any integration would keep the deterministic kernel as the authority for published
results.

### Isolated adversary emulation

**MITRE Caldera for OT** is a possible future integration for exercising detection
against ATT&CK-mapped behaviour.

Conditions, non-negotiable: confined to an isolated research network; capabilities
limited to scenarios already in the closed vocabulary; every action mapped
explicitly to ATT&CK for ICS; documented safety restrictions; never pointed at
anything real. Out of scope until M9 exists — there is no reason to emulate an
adversary against a range that cannot detect anything.

### Hardware-in-the-loop

A real PLC on an isolated bench executing the control logic against the simulated
process. The natural way to test whether an engineering constraint implemented in
real hardware behaves as this model assumes — which is assumption A2, the one most
likely to invalidate the flagship result.

Substantial safety and scope implications; no committed design.

### Additional process domains

The consequence engine, invariant framework, evidence model and scenario engine
are domain-agnostic; only `core/physics` is water-specific. Electrical
distribution and district heating are candidates, chosen for interpretable
physical state rather than for drama.

### Multi-operator and human factors

SCN-003 shows an engineering constraint preserving the process while leaving the
operator deceived. What an operator *does* with a deceived view is currently
unmodelled, and is arguably the more important half of that result.

---

## Explicitly not planned

- Any offensive capability, exploit, or intrusion tooling
- Modelling of initial access or intrusion mechanisms
- Integration with real utility data, however anonymised
- Compliance certification tooling of any kind
