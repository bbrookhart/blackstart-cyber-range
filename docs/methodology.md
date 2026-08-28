# Methodology

How BLACKSTART reasons, and why it reasons in that order.

---

## Consequence before vulnerability

BLACKSTART does not begin with *what CVEs exist?* It begins with *what physical
outcomes must never occur?*

The ordering is the method:

```text
1. critical function        CF-001: keep water available and the process safe
2. unacceptable outcomes    C0..C5, with quantitative thresholds
3. enabling systems         tank, pump, valve, controller, instrumentation
4. digital dependencies     what can influence each of the above
5. credible paths           enumerated from the dependency graph
6. detection opportunities  where a condition becomes observable
7. engineering mitigations  constraints that break a path
8. recovery                 what returns the mission to acceptable bounds
```

A vulnerability-first analysis produces a list that grows without bound and never
says which items matter. A consequence-first analysis produces a much shorter list
of things that can actually reach the physical process, and a defensible reason
for each.

This structure is *informed by* publicly described consequence-driven engineering
principles. BLACKSTART is **not** an implementation of Consequence-driven
Cyber-informed Engineering and implies no endorsement by any laboratory or agency.

---

## Assume compromise

The architecture models defence in depth, and the scenarios then assume parts of
it have failed.

This is not defeatism. It is the only way to ask the question the project cares
about: *given* that an adversary has influence, does the physical mission survive?
A model that assumes the perimeter holds can only ever demonstrate that perimeters
are useful.

The consequence is a hard scoping boundary: BLACKSTART studies what happens after
compromise, and offers no evidence about how hard compromise is to achieve.

---

## Separate what is true from what is believed

The single most load-bearing decision in the project.

- `TruthState` — what physically happened. Invariants read this.
- `ReportedState` — what the control system and operator believed. The controller
  reads this.
- Only INV-006 reads both, and only to compare them.

Two consequences follow, and both are what make the results legible:

1. **The evidence model is not deceivable by an effect that deceives the
   operator.** In SCN-003 the HMI shows a plausible, stable, wrong level while
   INV-001 records the true excursion.
2. **"The process was damaged" and "the operator was deceived" are independently
   measurable.** In SCN-003 the engineering constraint fixes the first and does
   nothing for the second, and the results say so.

---

## Measure, do not assert

BLACKSTART never claims to be secure or to prevent attacks. It reports:

reachable consequence paths · invariant violations and their duration · physical
deviation · service availability · consequence severity · recovery time or an
explicit non-recovery status · supervisory availability · test coverage

Every figure is computed from a recorded trace. Where a capability does not exist,
its metric reads `NOT_IMPLEMENTED` rather than zero.

### The comparison is the result

A single run showing a bad outcome demonstrates nothing about a defence. The
method is a controlled comparison: same scenario, same seed, same configuration,
differing in exactly one respect — whether the engineering constraint is present.

For that to mean anything, three things must hold, and each is enforced:

- the disabled variant is a **strict pass-through**, verified by a property test;
- the invariant checker **shares no code** with the constraint, verified by AST
  analysis, or the result would be a tautology;
- the finding survives **multiple seeds**, checked across four.

---

## Distinguish disturbance from compromise

A range that flags every departure from nominal as a security event is producing
false positives. SCN-002 is the control case: a large benign demand surge that
produces a genuine C2 service consequence with **zero** invariant violations and
no adversary involvement.

The correct answer to SCN-002 is "a real loss of service, not a security event",
and the classifier reaches it without being told.

---

## Report inconvenient results

The project deliberately keeps findings that complicate its own argument:

- the constraint preserves the process but not the operator's understanding of it
  (SCN-003, INV-006 violated in both variants);
- an engineered control can relocate a consequence rather than remove it
  (SCN-006: pump saved, service still lost — no control on the command path can
  create water);
- the backstop interrupts 45% of high-consequence paths, not most of them;
- the outlet valve command path is entirely unconstrained.

A result set in which the defence improves every number would be evidence of a
rigged model, not a good defence.

---

## Reproducibility as a precondition, not a feature

An experiment is a pure function of `(version, configuration, seed)`. Experiment
identifiers are **derived from that triple**, so re-running reproduces the
evidence package byte-for-byte including the identifier embedded in every event.

`blackstart evidence verify --reproduce` re-executes from the recorded
configuration and diffs every deterministic artifact. CI generates the complete
flagship package and runs the same check on every change.

If a result cannot be re-derived, it is not a result.

---

## State the limitations with the claims

Every experiment's `summary.md` carries its own limitations section. The README
links to [limitations.md](limitations.md) above the results, not below them. A
research artefact whose limitations are harder to find than its results is
advertising.

---

## What this methodology cannot give you

It estimates **no likelihoods**. BLACKSTART enumerates what can reach the physical
process and how severe the result would be; it has no basis for saying how
probable any of it is, and a risk number built on an invented likelihood would be
the most misleading artefact this project could produce.

It is consequence analysis, not risk assessment, and not a safety case.
