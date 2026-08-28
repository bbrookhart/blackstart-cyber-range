# ADR-005 — Evidence and reproducibility model

- **Status:** Accepted
- **Date:** 2026-08-24

## Context

A resilience claim is only as good as a reviewer's ability to re-derive it. BLACKSTART must
make the path from "number in the README" to "artefact produced by a specific execution"
short and mechanically checkable.

## Decision

### Determinism contract

An experiment is a pure function of the triple:

```text
(blackstart_version, configuration_hash, seed)  →  experiment result
```

Guaranteed by: fixed timestep, no wall-clock reads in the kernel, a single explicitly seeded
`random.Random` instance threaded through the runner, no global RNG anywhere in
`blackstart/core` (asserted by a lint rule and a test), no dict-ordering dependence in
serialisation, and no parallelism inside a run.

`configuration_hash` is the SHA-256 of the canonical JSON serialisation of the fully resolved
configuration — process, invariants, consequences, scenario, and variant overrides merged.
Canonical means sorted keys, fixed float repr, no whitespace variance. Any configuration
change produces a different hash, so a result can never be silently attributed to the wrong
configuration.

Timestamps are simulation time (seconds from `t=0`), not wall time. Wall-clock values appear
only in `manifest.json` provenance fields and are excluded from the reproducibility hash.

### Evidence package

Every run writes a self-describing directory:

```text
evidence/EXP-<date>-<seq>/
├── manifest.json      provenance, seed, config hash, artefact digests, integrity digest
├── configuration.json fully resolved configuration actually executed
├── events.jsonl       ordered structured event stream
├── process.csv        per-timestep true and reported physical state
├── invariants.json    per-invariant outcome, violation intervals, peak excursion
├── consequences.json  consequence timeline and maximum severity reached
├── metrics.json       computed research metrics
└── summary.md         human-readable account of the run
```

### Integrity

`manifest.json` records the SHA-256 of every other artefact, plus a top-level digest over the
sorted `(filename, digest)` list. `blackstart evidence verify <id>` recomputes all of them and
fails on any mismatch, missing file, or unexpected extra file.

This is **tamper-evidence for research artefacts, not tamper-proofing.** Anyone who can edit
the artefacts can recompute the manifest. It defends against accidental corruption, partial
writes, and stale files — not against a motivated forger. Signing is on the roadmap; claiming
more than this would be exactly the kind of overstatement the project is meant to avoid.

### Reproduction

`blackstart evidence verify --reproduce <id>` re-executes the experiment from the recorded
configuration and seed and diffs the result against the stored artefacts, ignoring only the
provenance fields excluded from the hash. This is the strongest reproducibility claim in v0.1
and is exercised by an integration test.

### Coverage as evidence

Branch coverage is gated at **90% on safety-critical modules only** (`core`, `controller`,
`scenario_engine`, `analysis`, `evidence`). Repository-wide coverage is reported but not
gated. Gating a whole-repo number rewards testing trivial code and tells a reviewer nothing
about whether the invariant logic is exercised.

## Alternatives considered

| Alternative | Why rejected |
| --- | --- |
| SQLite or Parquet evidence store | Faster to query, opaque to a reviewer with a text editor. Plain JSONL/CSV can be inspected, diffed, and grepped without tooling. |
| Recording wall-clock timestamps in the event stream | Destroys byte-level reproducibility for no analytical gain; simulation time is the meaningful axis. |
| Cryptographic signing of evidence in v0.1 | Requires key management the project has no story for. Would imply a tamper-resistance guarantee that is not real. |
| Whole-repository coverage gate | Rewards coverage inflation; obscures whether safety logic is tested. |

## Consequences

**Positive.** Every README number traces to a named experiment ID and a verifiable artefact.
Silent regressions in determinism fail CI.

**Negative.** The evidence format is BLACKSTART-specific. No standard interchange format is
emitted in v0.1.

**Negative.** Byte-level reproducibility holds for a fixed interpreter and platform. Different
CPython versions or architectures may alter floating-point formatting in the last digit.
Metric-level reproducibility (tolerance-based) is checked separately and is the portable
guarantee.

## Security implications

Evidence integrity is an explicit asset in the threat model. INV-006 plus truth/reported
separation (ADR-004) means the evidence record remains correct even when the operator view has
been falsified.
