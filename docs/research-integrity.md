# Research Integrity Statement

BLACKSTART is published as a research artefact. This statement records what is
real, what is invented, and what may and may not be inferred from anything in
this repository.

---

## All infrastructure is fictional

The modelled municipal water storage and pumping process **does not exist**. It
is not a model of, derived from, or informed by any real utility.

Every parameter is invented: tank geometry, pump curve, valve coefficients,
demand profiles, control setpoints, safety limits, consequence thresholds, zone
layout, service names and asset identifiers. They were chosen to be physically
coherent and pedagogically clear, not to represent any real installation.

No real utility's hydraulics, equipment ratings, operating parameters, network
diagrams, configurations or credentials were used, consulted, or reproduced.

## All data is synthetic

Every number in every evidence package was produced by the simulation in this
repository. No measured, historical, proprietary or operational data of any kind
was used.

## No real system was tested

No real control system, PLC, RTU, HMI, historian, network or utility was tested,
scanned, probed, contacted, or interacted with in any way during this work.
BLACKSTART has no capability to do so: the simulation kernel imports no
networking or subprocess module, and a test enforces that.

## Adversarial behaviour is simulated, not performed

Scenario effects are bounded mutations of in-memory simulation state. They are
declarative data entries drawn from a closed vocabulary of seven effects.

No exploitation occurs. Nothing authenticates, bypasses authentication, crafts a
protocol frame, or exploits a flaw. The repository contains no malware, no
payloads, no credential tooling, no persistence or lateral movement tooling, and
no scanning capability.

BLACKSTART studies **effects and defences**. It does not provide operational
attack tooling, and contributions that would are refused.

---

## What results mean, and what they do not

A BLACKSTART result is a statement about BLACKSTART.

When this project reports that an engineering constraint reduced the maximum
consequence from C4 to C1, it means: *in this model, under this configuration, at
this seed, with these assumptions, the constraint changed the measured outcome*.

It does **not** mean, and must not be cited as meaning, that:

- a comparable control would work in any real plant;
- the assumed compromise is achievable, or unachievable, in any real plant;
- the consequence classes correspond to real operational severities;
- any real system is safe, unsafe, compliant, or certified.

Simulation results establish **no** real-world safety property and constitute
**no** form of safety certification, functional-safety assessment, or regulatory
conclusion.

## Metrics are derived, never entered

Every reported metric is computed from a recorded process trace and invariant
outcome. No number in this repository was typed in by hand to make a result look
better.

Where a capability does not exist, its metric is reported as the literal string
`NOT_IMPLEMENTED` — not zero, not null, not omitted. BLACKSTART v0.1 has no
detection capability, so detection latency, containment latency and
false-positive rate all carry that marker.

## Negative and inconvenient results are reported

The project deliberately retains results that complicate its own argument:

- In SCN-003 the engineering constraint keeps the process safe while INV-005
  remains violated in **both** variants. The defence preserves the physical
  mission and does nothing for the operator's understanding of it.
- In SCN-006 the dry-run interlock prevents equipment damage but does not prevent
  the loss of service, because the underlying problem is that there is no supply.
- The consequence-path analysis shows the backstop interrupts 45% of
  high-consequence paths — not most of them — and that the outlet valve command
  path is entirely unconstrained.
- SCN-002 produces a genuine C2 service consequence with no adversary involved,
  demonstrating that not every bad outcome is a security event.

## Framework mappings are informational

All mappings to NIST, CISA, MITRE and IEC material are for orientation only. They
demonstrate no conformance, no compliance, no certification and no accreditation.

Identifiers are verified before use. ATT&CK for ICS techniques were requested
directly from `attack.mitre.org` and their names and tactics read from the
responses; three identifiers found to have been renumbered upstream are recorded
as such. NIST CSF 2.0 is mapped at Function level only, because Category and
Subcategory identifiers could not be verified against the authoritative
publication — mapping coarsely was preferred to asserting unverified identifiers.

Rejected mappings are recorded with reasons, because a mapping declined for a
stated reason is more informative than one accepted without one.

---

## No affiliation or endorsement

BLACKSTART is an independent research project.

It is **not** affiliated with, sponsored by, endorsed by, or connected to Idaho
National Laboratory, the National Institute of Standards and Technology, the
Cybersecurity and Infrastructure Security Agency, The MITRE Corporation, Sandia
National Laboratories, the International Electrotechnical Commission, the
International Society of Automation, any government or agency thereof, or any
utility or vendor.

Where this project says its consequence analysis is *informed by
consequence-driven engineering principles*, that is a statement about intellectual
influence on publicly described ideas. BLACKSTART is **not** an implementation of
Consequence-driven Cyber-informed Engineering, and no endorsement by Idaho
National Laboratory is implied or should be inferred.

No government seals, agency insignia, classification markings, or organisational
branding appear anywhere in this repository, and none may be added.

## Copyrighted material

No paywalled or copyrighted standard text is reproduced. The IEC 62443 discussion
describes publicly and widely discussed concepts in the project's own words.

---

## Reproducibility commitment

Every result is reproducible from `(version, configuration, seed)`. Every
evidence package records the configuration that produced it, the seed, the
software version, and a SHA-256 digest of every artefact.

`blackstart evidence verify --reproduce` re-executes an experiment and compares
the result byte-for-byte, and CI runs it on every change.

Evidence integrity is **tamper-evident, not tamper-proof**: anyone who can edit
the artefacts can recompute the manifest. It defends against corruption and
staleness, not against a motivated forger.

---

## Corrections

If any statement in this repository is found to be inaccurate, unsupported, or
overstated, the correct response is to weaken the claim or withdraw it — not to
defend it. Report such findings as an issue, or privately per
[SECURITY.md](../SECURITY.md) if the concern is a safety one.
