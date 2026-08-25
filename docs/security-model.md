# Security Model

What BLACKSTART protects, what it assumes, and what it does not defend at all.

Operational policy and reporting: [SECURITY.md](../SECURITY.md).
Adversary model and boundaries: [threat-model/](../threat-model/README.md).

---

## Two different security questions

BLACKSTART sits at the intersection of two, and conflating them causes most of the
confusion in this space.

**1. Is the range itself secure?**
Largely irrelevant, and deliberately so. The range has no authentication, no
authorisation and no multi-tenancy. It is a single-operator research tool exposing
one loopback port. Its security posture is *isolation*, not access control.

**2. Can the modelled system preserve its mission under compromise?**
This is the research question, and everything interesting lives here.

---

## The range's own posture

| Property | Mechanism | Verified by |
| --- | --- | --- |
| One published port, loopback only | `127.0.0.1:8080` in Compose | `test_exposure_and_posture.py`; CI probes the running topology |
| No control-side port reachable from the host | `internal: true` networks | Same, plus a live `curl` check in CI |
| No outbound connections | Nothing in the codebase initiates one | AST analysis of sealed packages |
| Non-root containers | `user: "10001:10001"` | Architecture test |
| Read-only root filesystem | `read_only: true` + tmpfs | Architecture test |
| All capabilities dropped | `cap_drop: [ALL]` | Architecture test |
| No privilege escalation | `no-new-privileges:true` | Architecture test |
| No host bind mounts | Asserted absent | Architecture test |
| Pinned base and tool images | `python:3.12-slim-bookworm`, pinned `uv` image | Architecture test rejects `:latest` and piped installers |
| Lockfile-only dependency install | `uv sync --frozen` | Architecture test |
| No secrets | There are none to hold | `detect-private-key` hook; gitleaks in CI |

**No credentials exist anywhere in BLACKSTART.** There is nothing to authenticate
to and nothing to steal. `.env.example` says so explicitly, because an
environment-file convention normally implies otherwise.

---

## The scenario safety boundary

BLACKSTART's most important security property is what it *cannot* do.

Three claims, each enforced structurally and tested rather than promised
([ADR-006](adr/ADR-006-scenario-safety-boundary.md)):

1. **Scenarios are data.** Validated YAML with no expressions, scripts, imports or
   paths. Loading one cannot execute anything.
2. **The effect vocabulary is closed.** Exactly seven effects. An unknown name is a
   load-time validation error, not a dynamic dispatch.
3. **The kernel cannot reach outside the process.** No module in
   `blackstart/core` or `blackstart/scenario_engine` imports a networking,
   subprocess or filesystem-traversal module, or makes an OS-level call. An AST
   walk over both packages enforces it.

Therefore **no code path exists from a scenario file to any system outside the
Python process.** Widening that boundary requires deleting a test, which is a
visible act in review.

The kernel is additionally forbidden from importing `time` or `datetime`, which
serves reproducibility and the safety boundary at once.

---

## The modelled system's defences

Three layers, and the scenarios are designed so each one's contribution is
separately visible.

### Topological — zones and conduits

Four zones, one bridging service per conduit, no service holding both an
enterprise and an OT-side network. Reaching the controller from the enterprise
zone requires three hops. Telemetry flows outward; only CDT-004 carries commands.

*Limitation:* this demonstrates **topology**, not enforcement strength. Docker
bridge networks are not equivalent to physically separate networks with an
inspecting firewall.

### Functional — the control system

Anti-cycling limits, actuator slew limits, reserve protection. Real constraints,
but **the controller is not a safety device**: it has no independent measurement
and will faithfully pursue whatever setpoint it is given, including one that would
destroy the process.

### Engineered constraint — EBS-001

The layer the project exists to study, and the only one that does not depend on
the correctness of those above it.

```text
command of any origin ─► BS-01 clamp ─► BS-02 slew limit
                              │
                              ▼  (controller never sees the raw request)
                         control scan
                              │
                              ▼
                    BS-03 independent trip
                    BS-04 dry-run interlock      ─► allowed / denied
                    BS-05 anti-cycle
                              │
                              ▼
                       physical process
```

**The critical property:** the constraint does not attempt to decide whether a
command is legitimate. The controller service accepts a setpoint write, records
the declared origin, and applies exactly the same constraint regardless of what
the writer claimed to be. A defence that depended on correct attribution would
fail precisely when attribution failed — which is the situation after compromise.

---

## Three independences, and what each is worth

| Independence | Mechanism | Status |
| --- | --- | --- |
| **Of the command path** | Policy read at construction, never writable at runtime | Verified by test |
| **Of the invariant checker** | Shares no code; neither imports the other | Verified by AST analysis |
| **Of the operator's measurement** | Reads LIT-002, unaffected by `sensor.*` effects | **Modelling assumption** |

The third is doing real work and is not proven. A real independent element can be
compromised, mis-calibrated, or share a common-cause failure with the primary
transmitter. If it fails, SCN-003's protected variant ends like its unprotected
one. This is stated in the configuration, the implementation, the threat model and
[limitations.md](limitations.md) rather than quietly relied upon.

The second matters for a different reason: without it, "backstop enabled ⇒ no
violations" would be a tautology rather than a measurement.

---

## The evidence boundary

Ground truth is not reachable from the reported view. A scenario effect that
deceives the operator **cannot** falsify the experimental record.

In SCN-003 the HMI displays a plausible, stable, wrong level while INV-001 records
the true excursion and INV-005 records the deception. Both land in the evidence
package, and the metrics report them separately.

---

## What is not defended

Stated plainly, because a security model that lists only its strengths is
marketing:

- **Initial access, persistence, lateral movement, evasion** — not modelled at
  all.
- **Detection** — no analytic, no rule, no network telemetry. Detection metrics
  read `NOT_IMPLEMENTED`.
- **The outlet valve command path** — genuinely unconstrained. Every
  `CTRL-RESERVE → VLV-001` consequence path is uninterrupted. A real gap, recorded
  in the consequence-path analysis and held visible by a test.
- **A compromised backstop** — assumed away (A2). If this assumption fails in the
  system you care about, the flagship result does not transfer.
- **Confidentiality** — not modelled. In this process it is not the property under
  threat.
- **Authentication and authorisation** — absent by design in the range; absent
  from the model entirely.
