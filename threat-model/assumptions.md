# Assumptions

Every conclusion BLACKSTART reaches is conditional on the assumptions below. A
model whose assumptions are unstated is not a model; it is an opinion with
numbers attached.

Each assumption is marked with what happens to the project's conclusions **if it
is wrong**, because that is the information a reviewer actually needs.

---

## A. Adversary assumptions

### A1 — The adversary can obtain influence over selected digital components

**Assumed.** The scenarios begin from a position of achieved influence:
a mutated setpoint, a falsified transmitter reading, an unavailable supervisory
path.

*If wrong:* The scenarios describe conditions that cannot arise, and the results
describe a defence against nothing. This assumption is doing a great deal of
work, and BLACKSTART offers **no evidence** for or against it. It is the
assumption a reader must supply from their own knowledge of a real system.

### A2 — The adversary does not compromise the engineering backstop

**Assumed.** EBS-001's policy is loaded at construction from configuration and is
never writable at runtime by any modelled command path.

*If wrong:* Every result in this repository collapses. The flagship comparison
measures the difference an intact backstop makes; a compromised backstop makes
that difference zero. This is the single most consequential assumption in the
project.

Its plausibility depends entirely on how the constraint is implemented in a real
system: a hardwired relay interlock is a very different proposition from a soft
function block in the same controller. BLACKSTART models the former and does not
demonstrate that it is achievable.

### A3 — The adversary does not compromise the independent level element

**Assumed.** LIT-002 is modelled as a separate hardwired channel, unaffected by
`sensor.*` effects.

*If wrong:* BS-03 fails, and SCN-003 ends the way its backstop-disabled variant
does. The word "independent" is carrying real weight here and is stated as an
assumption in `configs/process.yaml`, in the backstop's own docstring, and in
[docs/limitations.md](../docs/limitations.md), rather than being quietly relied
upon.

### A4 — The adversary is not attributed

No scenario is attributed to a named actor or state. Modelled capability is
described in terms of effect, not provenance.

---

## B. Modelling assumptions

### B1 — Effects of compromise are separable from mechanisms of compromise

**Assumed.** BLACKSTART simulates a mutated setpoint without simulating how it
was mutated.

*If wrong:* Some defences that appear effective here would be bypassed by the
mechanism rather than confronted by the constraint. A constraint evaluated in the
same controller that was compromised to issue the command is not the independent
constraint this model assumes.

### B2 — The physical model is adequate for the consequences being classified

**Assumed.** A lumped-parameter tank with a linear pump curve and Torricelli
discharge is sufficient to distinguish "safe", "degraded" and "unsafe".

*If wrong:* Consequence classifications could be qualitatively wrong. The model
has no transport delay, no pipe dynamics, no water hammer, no thermal effects and
no equipment wear model, so it cannot speak to transient pressure phenomena or
damage rates at all.

### B3 — Sampled-data control at 1.0 s is representative

**Assumed.** Control action is quantised at a 1.0 s scan against a 0.5 s physics
step.

*If wrong:* Reaction-latency components of the results would shift. Tolerance
windows on INV-002 and INV-003 were chosen against this scan rate.

### B4 — Instrument noise is Gaussian and small relative to the limits

**Assumed.** Level transmitter σ = 0.005 m against an INV-006 tolerance of
0.10 m.

*If wrong:* Nominal operation could trip INV-006, and the clean SCN-001 baseline
— on which every other result depends for interpretability — would degrade.

### B5 — The consequence thresholds are defensible

**Assumed.** The C0–C5 boundaries in `configs/consequences.yaml` reflect
meaningful operational distinctions for a water utility.

*If wrong:* The severity labels mislead. The thresholds are quantitative,
versioned, and machine-readable specifically so that a reviewer who disagrees can
change them and re-run rather than argue about adjectives. They are **invented**,
informed by general operational reasoning, not derived from any real utility's
criteria.

### B6 — A dependency path is a meaningful unit of analysis

**Assumed.** Counting graph paths says something useful about architectural
exposure.

*If wrong:* The consequence-path-reduction metric is decorative. It is reported
with an explicit interpretation note precisely because path counts are sensitive
to how finely the model is decomposed, and are not commensurable across models.

---

## C. Environment assumptions

### C1 — The range is isolated

**Assumed.** BLACKSTART runs on a host the operator controls, publishes one
loopback port, and is never connected to a real OT asset.

*If wrong:* The security posture described in [SECURITY.md](../SECURITY.md) does
not hold. This is enforced by the topology and asserted by architecture tests,
but it can be defeated by an operator who chooses to.

### C2 — The range is single-operator and trusted

**Assumed.** No authentication, authorisation or multi-tenancy exists, and none
is needed, because nothing is exposed beyond loopback.

*If wrong* (the range is exposed): every service is fully controllable by anyone
who can reach it.

### C3 — Docker networks provide topological separation

**Assumed.** Attaching a container only to `internal` networks prevents it from
reaching off-host.

*If wrong:* The zone demonstration weakens to a diagram. Docker bridge networks
are not equivalent to physically separate networks with an inspecting firewall,
and BLACKSTART demonstrates **topology**, not enforcement strength.

---

## D. Research-integrity assumptions

### D1 — Determinism holds

**Assumed.** An experiment is a pure function of `(version, configuration, seed)`.

*Verified*, not merely assumed: `blackstart evidence verify --reproduce`
re-executes and compares byte-for-byte, and CI runs it on every change.

### D2 — Evidence is tamper-evident, not tamper-proof

**Assumed and stated.** Manifest digests catch corruption, partial writes and
stale files. Anyone who can edit the artefacts can recompute the manifest.

### D3 — Results do not generalise beyond the model

**Assumed and stated everywhere.** A BLACKSTART result describes BLACKSTART. It
is not evidence about any real water utility, control system, or piece of
equipment.

---

## E. What would most change the conclusions

Ranked by how much a reviewer should worry:

1. **A2 / A3** — if the backstop or its measurement channel is compromisable in
   the system you care about, the flagship result does not transfer.
2. **A1** — if the assumed influence is not achievable, the scenarios are
   hypothetical in a way that matters.
3. **B1** — if mechanism and effect are not separable, the constraint may be
   bypassed rather than confronted.
4. **B5** — if the consequence thresholds are wrong, the severity labels are
   wrong even when the physics is right.
