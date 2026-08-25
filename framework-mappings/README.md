# Framework Mappings

These documents relate BLACKSTART to public security frameworks so that a reader
who thinks in those terms can orient quickly.

> **None of this is a compliance artefact.** BLACKSTART is a research simulation
> of a fictional process. Nothing here demonstrates conformance with any
> standard, and no certification, accreditation, endorsement or affiliation is
> claimed or implied.

## Contents

| Document | Framework | Granularity |
| --- | --- | --- |
| [attack-ics.yaml](attack-ics.yaml) | MITRE ATT&CK for ICS | Technique, verified against the live source |
| [nist-csf-2.0.yaml](nist-csf-2.0.yaml) | NIST CSF 2.0 | Function only — see below |
| [nist-800-82.md](nist-800-82.md) | NIST SP 800-82r3 | Principle-level narrative |
| [cisa-cpg.md](cisa-cpg.md) | CISA Cross-Sector CPGs | Outcome-level narrative |
| [iec-62443-concepts.md](iec-62443-concepts.md) | IEC 62443 | Public concepts only |

---

## Rules these mappings follow

**1. Never assert an identifier that has not been verified.**

ATT&CK technique identifiers were requested directly from `attack.mitre.org` and
their canonical names and tactics read from the responses. Three identifiers
considered during design turned out to have been renumbered upstream; they are
recorded as such rather than used in their obsolete form.

CSF 2.0 is mapped at **Function level only**. Category and Subcategory
identifiers could not be verified against the authoritative publication at the
time of writing, so they are absent. Reproducing plausible-looking identifiers
from memory is exactly the failure this repository argues against, and it would
be worse than mapping coarsely.

**2. Never map because a name sounds related.**

`attack-ics.yaml` contains a `considered_and_rejected` section, which is the more
informative half of the file. T0880 *Loss of Safety* was rejected for scenarios
that produce an unsafe process state, because that technique concerns loss of
safety *systems* — and in BLACKSTART the safety instrumentation stays intact and
reports correctly throughout.

**3. An empty mapping is often the correct answer.**

Three of six scenarios carry no ATT&CK mapping at all. A benign demand surge
corresponds to no adversary technique, and recording that explicitly is more
useful than inventing an association. Each unmapped scenario has a stated reason.

**4. State what is not covered.**

Every mapping document names its gaps. BLACKSTART covers four ATT&CK for ICS
techniques across two tactics, and none of the intrusion lifecycle. It
contributes nothing to the CSF Detect function. Those statements appear in the
files themselves, not only here.

**5. Keep the mappings honest automatically.**

[`tests/unit/test_attack_mapping.py`](../tests/unit/test_attack_mapping.py)
asserts that scenarios, the threat model, and the authoritative mapping file all
agree; that every mapping records a rationale, evidence source and verification
date; that no rejected technique is also asserted; that no obsolete identifier is
used; and that every scenario is either mapped or explicitly listed as unmapped.
Silence is not an acceptable state for a mapping.

---

## Traceability

The mappings are the outermost layer of a chain that starts in code:

```text
Research requirement
      ↓  "critical command paths must be constrained"
BLACKSTART control
      ↓  EBS-001, rules BS-01..BS-05 (configs/architecture.yaml)
Implementation
      ↓  blackstart/controller/backstop.py
Test
      ↓  test_effective_setpoint_never_leaves_the_permitted_range (property-based)
      ↓  test_pump_is_never_permitted_above_the_trip_level (property-based)
Evidence
      ↓  evidence/baseline/EXP-SCN004-*/invariants.json
Framework reference
         NIST SP 800-82r3 architecture and risk principles; CSF 2.0 Protect
```

Each link is checkable. The point of the chain is that the framework reference is
the *last* step rather than the first: the control exists because a consequence
analysis demanded it, not because a framework listed it.
