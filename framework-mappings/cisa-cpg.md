# CISA Cross-Sector Cybersecurity Performance Goals

**Informational orientation. Not a conformance claim, and not an assessment.**

The CPGs are a prioritised set of high-value security outcomes for critical
infrastructure. They are written for *organisations operating real
infrastructure*. BLACKSTART is a research simulation of a fictional process, so
most goals do not apply to it at all, and the honest mapping is mostly a list of
non-applicability.

This document is included because the CPGs are outcome-oriented rather than
control-oriented, and that framing matches how BLACKSTART reasons. It is not
included to suggest coverage.

> Implementing anything described here does not demonstrate that an organisation
> meets the CPGs. Do not cite this as evidence of compliance.

---

## Where BLACKSTART is genuinely relevant

### Network segmentation

**Relevant, and demonstrated.** BLACKSTART implements a four-zone architecture in
which every enterprise/OT flow traverses an enumerable broker, and the deployed
topology is machine-checked against the declared one. A reader can run
`make test-architecture` and watch the segmentation be asserted.

The demonstration is of *topology*, not of enforcement strength.

### Minimising exposure

**Relevant, and demonstrated.** Exactly one port is published, bound to
loopback. Industrial DMZ, OT and control networks are declared `internal`, so
containers attached only to them have no route off the host. CI additionally
proves from a running topology that no control-side port is reachable from the
host.

### Limiting OT connections and safe control-system operation

**Relevant, and the project's central contribution.** The engineering backstop
constrains what a command can achieve regardless of its origin or claimed
authorisation. The flagship experiment measures the difference this makes: a
mutated setpoint that drives the process to an unsafe state (C4, 639.5 s outside
safe bounds, containment loss) instead produces a minor deviation (C1, no
unsafe state, no spill).

The relevant insight is that this defence does not depend on correctly
identifying which commands are legitimate — which is precisely the thing that
fails when an adversary already has control influence.

### Documenting device and system inventories and dependencies

**Relevant, and demonstrated in miniature.** The dependency model enumerates
assets, their causal relationships, and every path from a digital component to a
high-consequence physical outcome. Queries answer "what supports the critical
function?" and "what can influence this safety limit?".

### Incident reporting and evidence

**Partially relevant.** BLACKSTART produces structured, ordered, integrity-checked
evidence packages from which an incident timeline can be reconstructed. It does
not model reporting to anyone.

---

## Where BLACKSTART is not relevant

| Goal area | Why not |
| --- | --- |
| Account security (unique credentials, MFA, revocation, minimum password strength) | No user or credential model exists. The range has no authentication by design; see SECURITY.md. |
| Detection of unsuccessful login attempts | Nothing to log in to. |
| Mitigating known vulnerabilities, no exploitable services on the internet | Nothing is exposed to any network beyond the host. Dependency vulnerabilities are audited in CI, which is a project-hygiene matter rather than a CPG outcome. |
| Security training and awareness | BLACKSTART is software; it has no personnel. |
| Vendor/supplier and third-party risk | Partially: SBOM generation and dependency auditing exist. Supplier assessment does not apply. |
| Asset backup and recovery of digital systems | Physical process recovery is measured. Digital restoration is not modelled at all. |
| Email security, macro protections | No such surface exists. |
| Incident response planning and reporting | No process is modelled. |
| Log collection and retention at organisational scale | Telemetry is emitted per experiment, not operated as a logging programme. |

---

## The honest summary

BLACKSTART touches perhaps five of the goal areas meaningfully, and does so as a
*demonstration of engineering reasoning* rather than as an implementation an
organisation could inherit. It has nothing to say about the account-security,
personnel, vulnerability-management or incident-response goals that make up much
of the CPG set.

A reader looking for evidence that a control-system architecture can be arranged
so that compromise does not immediately become physical consequence will find
that here. A reader looking for CPG coverage will not.
