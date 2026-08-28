# EXP-BS-001 Threat Model

## Scope

BLACKSTART v0.1 evaluates one post-compromise question in a fictional municipal
water-storage simulation. It does not evaluate intrusion prevention.

> A skilled adversary has already gained sufficient access to alter a
> supervisory control setpoint.

At simulated time 180 s, `SCN-004` changes the requested tank-level setpoint from
3.20 m to 4.80 m. The event is a controlled in-memory research fixture. It is
recorded as `unauthorized_setpoint_mutation` / `setpoint.override`; it is not an
exploit, protocol message, credential action, or malware execution.

## Adversary capability

The modeled adversary can:

- modify the supervisory requested setpoint;
- select a value above the 4.50 m maximum-safe physical threshold;
- leave the mutation active for the remainder of the experiment.

The modeled adversary cannot:

- modify the physical-process equations or experiment configuration;
- alter EBS-001 policy, thresholds, or code;
- alter the independent level channel;
- change evidence after it is emitted during the run;
- invoke a network, shell, credential, or protocol capability.

No inference is made about whether the assumed access is achievable in a real
system.

## Explicit exclusions

The experiment does not model initial access, malware delivery, credential
theft, privilege escalation, lateral movement, command-and-control, PLC
exploitation, persistence, evasion, operator coercion, or compromise of the
backstop. These exclusions isolate the causal question: what happens after the
supervisory request is untrusted?

## Trust model

| Component | Treatment in EXP-BS-001 | Consequence if assumption fails |
| --- | --- | --- |
| Supervisory requested control state | Untrusted / compromised | This is the tested input |
| Normal level controller | Trusted to execute its stated algorithm | A distinct controller defect would confound the comparison |
| Engineering backstop policy | Trusted and outside modeled compromise | BS-C1 and BS-C2 would not follow if the adversary could rewrite it |
| Physics engine | Trusted | Metrics would not describe the stated equations if incorrect |
| Experiment orchestrator | Trusted | Condition isolation and provenance could be wrong |
| Independent measurement channel | Trusted, modeled as separate | Shared compromise could defeat measurement-based permissives |
| Evidence verifier | Trusted, independent of primary metrics for four checks | Corruption or miscalculation could be accepted |

This is a modeled separation, not proof that a real implementation would be
independent. The narrow failure assumption is:

> Under this threat model, compromise of the supervisory command path does not
> automatically compromise the independent backstop.

It is not: “the backstop survives all cyber compromise.”

## Assets and protected mission

The protected mission is `CF-001`: maintain enough stored water to satisfy
synthetic demand while keeping the true process inside the configured safety
bounds. The principal assets are the requested control state, EBS-001 effective
target, pump command, tank state, independent and reported measurements,
invariant engine, and evidence package.

The unacceptable flagship outcome is C4: the true tank level exceeds the 4.50 m
maximum-safe threshold and violates INV-001. This is safe simulation of an
invented state; no real equipment is connected.

## Causal path

```text
SCN-004
  → unauthorized setpoint mutation
  → requested_setpoint = 4.80 m
  → EBS-001 decision
  → effective_setpoint
  → pump behavior
  → true tank trajectory
  → INV-001 / INV-005 state
  → consequence class
```

The path and protected interruption are emitted as `graph.json` and can be
queried with `blackstart graph consequence-path SCN-004`.

## ATT&CK orientation

The modeled effect is mapped to ATT&CK for ICS `T0836 Modify Parameter` and its
measured physical impact to `T0831 Manipulation of Control`. The project does not
claim to simulate the intrusion lifecycle, detect either technique, or implement
an ATT&CK mitigation. Version and dataset provenance are in
[`framework-mappings/attack-dataset.yaml`](../framework-mappings/attack-dataset.yaml).

## Result boundary

The supported claim is limited to this code, configuration, scenario, and trust
model. See [assurance-case.md](assurance-case.md),
[limitations.md](limitations.md), and
[research-integrity.md](research-integrity.md).
