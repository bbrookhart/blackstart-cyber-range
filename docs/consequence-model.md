# Consequence Model

How BLACKSTART decides that something bad happened, and how bad.

Configuration: [`configs/consequences.yaml`](../configs/consequences.yaml) and
[`configs/invariants.yaml`](../configs/invariants.yaml).
Implementation: [`blackstart/core/consequence/classifier.py`](../blackstart/core/consequence/classifier.py).
Rationale: [ADR-004](adr/ADR-004-safety-invariant-design.md).

---

## The critical function

Everything derives from one statement:

> **CF-001** — Maintain sufficient water storage to satisfy synthetic demand
> while keeping the process inside defined safe operating bounds.

CF-001 is *satisfied* at a timestep when both hold:

- service shortfall < 10%, **and**
- no invariant in {INV-001, INV-002, INV-003} is violated.

Service availability is the fraction of the experiment for which that predicate
holds. Note it requires **both** halves: a process delivering water perfectly
while sitting above its safe level is not performing its critical function. This
is why SCN-004's backstop-disabled variant reports 46.71% availability despite
meeting demand throughout.

---

## Safety invariants

Invariants are the **ground-truth record** of whether the process was actually
safe. They evaluate `TruthState`, not what the control system believed — with one
deliberate exception.

| ID | Property | Limit | Tolerance | Maps to |
| --- | --- | --- | --- | --- |
| INV-001 | Tank level ≤ safe working level | 4.50 m | none | C4 |
| INV-002 | Level ≥ operational reserve | 1.00 m | 120 s | C3 |
| INV-003 | Pump not energised without suction | 0.50 m source | 10 s | C4 |
| INV-004 | Command rate physically achievable | 0.05 m/s, 12 starts/h | none | C1 |
| INV-005 | Reported level tracks true level | 0.10 m | 5 s | C1 |

Three design points that matter:

**They are stateful temporal predicates, not assertions.** "The tank is below
reserve" is not a violation; "the tank has been below reserve for longer than
120 s" is. Putting that accumulation inside the invariant keeps safety-relevant
logic where it is tested as safety logic, rather than hiding it in the metrics
layer.

**Status is three-valued:** `OK`, `APPROACHING`, `VIOLATED`. `APPROACHING` is the
leading indicator — within a configured margin of the limit — and it is what lets
BLACKSTART measure how much *warning* an engineered control bought, not merely
whether a limit was crossed.

**INV-005 is the only invariant that reads both views**, because comparing them is
its entire purpose. Consequently a scenario effect that deceives the operator
cannot also falsify the experimental record: in SCN-003 the HMI shows a plausible
wrong value while INV-001 records the true excursion and INV-005 records the
deception.

---

## Consequence classes

Severity is **derived** each timestep from measurable conditions. Nothing — not a
scenario, not an effect, not an operator — assigns a class directly. That is what
makes a reported "maximum consequence C4" a result rather than a label.

| Class | Name | Reached when |
| --- | --- | --- |
| **C0** | Normal operation | In band, shortfall < 2%, no violated invariant |
| **C1** | Minor operational deviation | Outside the normal band, or shortfall ≥ 2%, or INV-004/INV-005 violated |
| **C2** | Service degradation | Shortfall ≥ 10% sustained ≥ 60 s |
| **C3** | Loss of required service | Shortfall ≥ 50% sustained ≥ 60 s, or INV-002 violated |
| **C4** | Unsafe physical state | INV-001 or INV-003 violated |
| **C5** | Catastrophic mission failure | Spill ≥ 20 m³, or unsafe ≥ 300 s **and** concurrent loss of required service |

### Escalation is deliberately hard

C4 requires a violated **physical** safety invariant. A telemetry-integrity
violation, however serious operationally, is C1 — the process may be perfectly
safe while the operator's understanding of it is not, and conflating those would
destroy the distinction SCN-003 exists to measure.

C5 requires containment loss at scale (20 m³ ≈ one third of nominal tank volume)
or a *prolonged* unsafe state **coincident with** loss of the required service.
A token overflow stays C4. A long unsafe period with service intact stays C4.
Both are tested explicitly, because a severity scale that is easy to max out
communicates nothing.

### The normal band

The normal band (2.70–3.70 m) is the control band (2.80–3.60 m) widened by a
0.10 m allowance for the overshoot any hysteresis controller produces between
scans. A band narrower than the control system's own achievable envelope would
classify correct operation as a deviation — and a baseline that reports C1 for
working normally makes every other result harder to read.

---

## Why the classifier is code, not a rule engine

`configs/consequences.yaml` carries a `conditions` tree describing each class, but
the classifier is explicit typed Python.

Safety classification should be readable in one place and directly
unit-testable. A rule interpreter would move the logic into data, where it is
much harder to reason about and where a subtle precedence bug could silently
change every reported severity. The configuration remains authoritative for the
**thresholds**, and a test asserts the code and the documented condition tree have
not drifted apart.

---

## Separation from the engineering backstop

The classifier and invariants measure **outcomes**. The backstop enforces a policy
on **commands**. They share configuration values but no code, and neither imports
the other.

This is load-bearing. If the invariant checker and the safety control were the
same object, "backstop enabled ⇒ no violations" would be a tautology instead of a
measurement. `test_shares_no_code_with_the_invariant_checker` verifies the
separation by AST analysis.

The backstop's thresholds are deliberately **tighter** than the invariant limits
(trip at 4.20 m, setpoint clamped to 3.60 m, against a 4.50 m safety limit), so
the constraint acts before the limit is reached. The configuration loader rejects
any configuration where that is not true.

---

## Metrics

Defined in [`blackstart/analysis/metrics.py`](../blackstart/analysis/metrics.py).

| Metric | Definition |
| --- | --- |
| Service availability | % of steps where CF-001 is satisfied |
| Unsafe-state duration | Time with INV-001 or INV-003 violated |
| Maximum physical deviation | Peak \|level − *legitimate* setpoint\| |
| Invariant violations | Count, duration and peak excursion, per invariant |
| Consequence severity | Maximum class reached, plus dwell time per class |
| Recovery | Time from end of disturbance to sustained CF-001, or an explicit non-recovery status |
| Supervisory availability | % of steps with the supervisory path available |
| Consequence-path reduction | Modelled C4+ paths interrupted by the engineering control |

Two deliberate choices:

**Maximum deviation is measured against the *legitimate* setpoint**, not the
mutated one. Otherwise an attacker who moves the setpoint would appear to reduce
deviation by moving the target.

**Recovery reports why it is undefined** rather than emitting a misleading null.
Where a scenario effect persists to the end of the experiment, the status is
`effect_persists_to_end_of_experiment` — the process never leaves the disturbed
condition, so recovery time is not a defined quantity.

Metrics whose underlying capability does not exist report the literal string
`NOT_IMPLEMENTED`. BLACKSTART v0.1 has no detection capability, so detection
latency, containment latency and false-positive rate all carry that marker.
