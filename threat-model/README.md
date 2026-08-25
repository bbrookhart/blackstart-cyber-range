# BLACKSTART Threat Model

This threat model is **consequence-first**. It does not begin with an inventory
of vulnerabilities and reason forward to impact. It begins with the physical
outcomes that must never occur and reasons backward to the digital dependencies
that could produce them.

That ordering is the whole point. A vulnerability-first model produces a list
that grows without bound and never says which items matter. A consequence-first
model produces a much shorter list of things that can actually reach the
physical process, and a defensible reason for each.

## Contents

| Document | What it covers |
| --- | --- |
| [assumptions.md](assumptions.md) | What is assumed about the adversary, the environment, and the model itself |
| [trust-boundaries.md](trust-boundaries.md) | Where trust changes, and what crosses each boundary |
| [consequence-paths.yaml](consequence-paths.yaml) | Every enumerated path to a C4+ outcome, generated from the dependency graph |
| [attack-ics-mapping.yaml](attack-ics-mapping.yaml) | Simulated behaviours mapped to ATT&CK for ICS, with rationale and ambiguity |

---

## 1. What must never happen

Derived from the critical function CF-001 — *maintain sufficient water storage to
satisfy synthetic demand while keeping the process inside defined safe operating
bounds* — the unacceptable outcomes are:

| Outcome | Class | Detected by |
| --- | --- | --- |
| Storage driven above the safe working level | C4 | INV-001 |
| Pump operated without suction | C4 | INV-003 |
| Operational reserve lost beyond tolerance | C3 | INV-002 |
| Sustained failure to deliver demanded flow | C2 / C3 | Service shortfall |
| Loss of containment at scale | C5 | Spill volume |
| Operator's understanding of the process falsified | C1 | INV-005 |

The last one is not a physical consequence, and BLACKSTART deliberately does not
inflate it into one. It is tracked separately because a defence can preserve the
process while entirely failing to preserve the operator's understanding of it —
and SCN-003 measures exactly that.

---

## 2. Assets

Ordered by what their compromise would enable, not by what they cost.

| Asset | Why it matters | Consequence if influenced |
| --- | --- | --- |
| **Engineering backstop policy** (EBS-001) | The last barrier between a digital command and an unsafe physical state | Every C4 path becomes reachable again |
| **Controller logic** (PLC-001, CTRL-LEVEL) | Directly commands the pump | C4 via INV-001 or INV-003 |
| **Operator command channel** (CDT-004) | The only path a control command travels | C4 — this is SCN-004 |
| **Level transmitter** (LIT-001) | The only level input the controller has | C4 — this is SCN-003 |
| **Independent level element** (LIT-002) | The measurement the backstop trips on | Defeats BS-03; see assumptions |
| **Physical process** (PROC-001, TNK-001, PMP-001, VLV-001) | The thing being defended | The consequence itself |
| **Process telemetry / historian** | Operator and analyst situational awareness | C1; degrades response, not the process |
| **Evidence integrity** | Whether any result can be believed | Not a physical consequence; a research-integrity one |

---

## 3. Adversary model

**Assumed capability.** A sophisticated adversary is assumed able to obtain
influence over selected digital components inside the simulation. BLACKSTART does
not model how that influence is obtained.

This is the central scoping decision, and it cuts both ways:

- It lets the project ask the harder and more useful question — *given*
  compromise, does the physical mission survive?
- It means BLACKSTART **cannot tell you whether any particular system is
  compromisable**. Nothing here is evidence about the difficulty of intrusion.

**No attribution.** No scenario is attributed to a named actor, group, or state.
The model is about capability and consequence, not about who has it.

### Adversary objectives modelled

| Objective | Scenario | Modelled as |
| --- | --- | --- |
| Unauthorised control influence | SCN-004 | `setpoint.override` |
| Manipulation of the operator's view | SCN-003 | `sensor.bias`, `sensor.freeze` |
| Denial of the operator's view | SCN-005 | `supervisory.blackout` |
| Degradation of service | emergent | Consequence of the above |

### Explicitly excluded

Not modelled, and not claimed to be modelled:

- Initial access, phishing, supply chain, or any intrusion mechanism
- Radio-frequency and wireless attacks
- Physical destruction, sabotage, or insider physical access
- Exploitation of real hardware, firmware, or protocol stacks
- Zero-day development
- Credential compromise against any real identity provider
- Lateral movement and persistence
- Detection evasion

Several of these are excluded because they are out of scope; several are excluded
because implementing them would produce reusable offensive tooling, which
[ADR-006](../docs/adr/ADR-006-scenario-safety-boundary.md) forbids.

---

## 4. Findings from the model

These come from querying the dependency graph, not from intuition.

### 4.1 The engineering backstop interrupts 45% of high-consequence paths

Of 40 enumerated paths terminating at C4 or above, 18 are interrupted by at least
one backstop rule and 22 are not.

This is a modest number, and reporting it honestly matters more than reporting a
large one. The backstop is a constraint on **one command path** — the pump. It is
not a general-purpose safety layer, and the graph says so.

### 4.2 The outlet valve command path is not protected

Every path of the form `… → CTRL-RESERVE → VLV-001 → PROC-001 → INV-00x → C4`
is uninterrupted. The backstop constrains the pump permissive and the level
setpoint; it applies no constraint to valve commands.

This is a **real gap in the current design**, surfaced by the model rather than
by inspection. It is recorded here, asserted by a test so it cannot silently
disappear, and listed as a roadmap item. It is not presented as a solved problem.

### 4.3 Preserving the process does not preserve the operator's view

In SCN-003 the backstop keeps the tank below its safe limit under a falsified
level transmitter — INV-001 is never violated. INV-005 is violated throughout,
in **both** variants.

The engineering control defends the physical mission. It does nothing for
situational awareness, and the evidence shows that plainly rather than reporting
an unqualified success.

### 4.4 An engineered control can relocate a consequence rather than remove it

In SCN-006 the dry-run interlock prevents the pump from being destroyed
(INV-003 not violated, C5 → C3). It does not prevent the loss of service, because
the underlying problem is that there is no supply. No control on the command path
can create water.

### 4.5 An implausible command is detectable independently of whether it succeeded

INV-004 observes the **requested** setpoint rather than the constrained one, so
the evidence that a physically implausible command was issued survives the
backstop refusing it. In SCN-004 INV-004 is violated in both variants. That is a
detection opportunity that does not depend on the defence having failed.

---

## 5. What this threat model is not

- It is not a hazard analysis, a HAZOP, a LOPA, or a safety case.
- It is not a risk assessment: no likelihoods are estimated, because BLACKSTART
  has no basis for estimating them.
- It is not a statement about any real water utility. Every asset, parameter and
  dependency here is invented.
- It is not a compliance artefact.

See [docs/limitations.md](../docs/limitations.md).
