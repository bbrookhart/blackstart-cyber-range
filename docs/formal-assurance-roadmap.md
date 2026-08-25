# Formal Assurance Roadmap

BLACKSTART v0.1 **tests** its safety properties. It does not **prove** them, and
claims no formal verification.

This document records which properties would benefit from formalisation, why they
are good candidates, and what would have to be true first. Publishing it is a
commitment to the distinction between tested and proven, not a claim to have
crossed it.

---

## Current assurance, honestly characterised

| Level | What exists |
| --- | --- |
| Type safety | Strict `mypy` across package, services and tests |
| Unit testing | Every invariant, every backstop rule, every equation |
| Property-based testing | Hypothesis over physical bounds, backstop policy, determinism |
| Integration testing | Full pipeline; scenario expectations from measured runs |
| Architecture testing | Topology, exposure, container posture, safety boundary |
| Reproduction | Byte-for-byte re-execution, in CI |
| **Formal verification** | **None** |

Property-based tests explore the input space broadly. They do not exhaust it, and
a Hypothesis pass is evidence, not proof.

---

## Why the invariants are already shaped for formalisation

This was a design consideration in [ADR-004](adr/ADR-004-safety-invariant-design.md),
even though v0.1 does not act on it:

- Invariants are **declarative specifications** in configuration, separate from
  their evaluators.
- Each is a **temporal predicate** over a bounded state, with an explicit
  tolerance — which is what temporal logic expresses naturally.
- The state space is **small and typed**: one continuous level, one source level,
  two booleans, one valve position, one setpoint.
- The backstop is a **pure policy function** of `(request, independent
  measurement, source level, latched trip state)`.
- The scan order is **fixed and total**, so the system is a deterministic
  transition system by construction.

---

## Candidate properties

### P1 — The backstop admits no unsafe pump permissive

```text
□ ( independent_level ≥ trip_level  →  ¬ pump_permitted )
```

**Best candidate.** Finite, latched state; no continuous dynamics involved. A
model checker could exhaust the reachable state space of the policy directly.

Currently: property-tested over the input space, at 100% branch coverage.

### P2 — The effective setpoint never leaves the engineering range

```text
□ ( setpoint_min ≤ effective_setpoint ≤ setpoint_max )
```

Strong candidate for the same reason: the clamp and slew limiter are pure
arithmetic over a bounded interval, and the property is inductive.

### P3 — Bounded level under a bounded command set

```text
□ ( backstop_enabled  →  tank_level ≤ INV-001 limit )
```

The interesting one, and much harder: it couples the discrete policy to the
continuous hydraulics. This is a **hybrid system** reachability problem, needing a
tool that can reason about ODE flow between discrete transitions.

Would require: a formal treatment of the pump curve and discharge relation, plus
a defensible bound on demand and instrument noise.

### P4 — Consequence monotonicity

```text
□ ( maximum_consequence' ≥ maximum_consequence )
```

Nearly trivial to prove and already property-tested; worth including because it is
cheap and it guards a reported metric.

### P5 — Reachability of C4 without the backstop

```text
◇ ( ¬backstop_enabled ∧ consequence = C4 )
```

Formalising the *negative* result matters as much as the positive one. If C4 were
in fact unreachable, the flagship comparison would be measuring nothing.

Currently demonstrated by experiment across four seeds — which is evidence that it
is reachable, not proof of the conditions under which it is.

---

## What would have to happen first

1. **A formal state model.** Extract a transition system from the scan order, with
   the continuous dynamics either abstracted or given interval bounds.
2. **A tool choice matched to the property.** P1, P2 and P4 are finite-state or
   inductive and suit TLA+/PlusCal or a bounded model checker. P3 needs hybrid
   reachability (SMT-based, or a tool such as those used for hybrid automata) and
   is a research task rather than an engineering one.
3. **A refinement argument.** The hardest part, and the one most often skipped: a
   proof about a TLA+ model says nothing about Python unless the correspondence
   between them is established and maintained. Without that, a formal artefact
   would add credibility without adding assurance — the worst possible outcome.

---

## What formalisation would and would not buy

**Would:** exhaustive assurance for P1 and P2 over the whole reachable state space
rather than a sampled one; a precise statement of the assumptions each property
rests on; early detection of policy changes that break an inductive invariant.

**Would not:** say anything about whether the *physical model* is right, whether
the *consequence thresholds* are meaningful, or whether any of it transfers to a
real utility. Those are the limitations that actually bound this project's
conclusions, and no amount of formal verification touches them.

---

## Status

**Not started, and not claimed.** No temporal-logic specification, model checking
or theorem proving has been performed. Any statement that BLACKSTART is formally
verified would be false.
