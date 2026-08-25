# Evidence

Every BLACKSTART experiment writes a self-describing directory here.

## Layout

```text
evidence/
├── baseline/     committed reference results, verified in CI
├── local/        your runs (git-ignored)
└── ci/           produced by CI, uploaded as an artefact
```

## What a package contains

```text
EXP-SCN004-backstop-enabled-457bc4c1/
├── manifest.json       provenance, seed, config hash, per-artefact SHA-256
├── configuration.json  the fully resolved configuration actually executed
├── events.jsonl        ordered structured event stream
├── process.csv         per-timestep true AND reported physical state
├── invariants.json     per-invariant outcome, violation intervals, peak excursion
├── consequences.json   consequence timeline and maximum severity
├── metrics.json        computed research metrics
└── summary.md          human-readable account, with its own limitations
```

Plain JSONL and CSV deliberately: a reviewer can inspect, diff and grep a package
with a text editor and no BLACKSTART tooling.

## Reading the experiment identifier

```text
EXP-SCN004-backstop-enabled-457bc4c1
    │      │                 └── first 8 hex of the configuration hash
    │      └── variant
    └── scenario
```

The identifier is **derived** from `(version, configuration, seed)`, so re-running
the same experiment reproduces the package byte-for-byte, identifier included. A
different identifier means a different input — not a different run.

## Committed baseline

| Experiment | Scenario | Variant |
| --- | --- | --- |
| `EXP-SCN001-backstop-enabled-76026f68` | Nominal operation | enabled |
| `EXP-SCN004-backstop-disabled-a6e4affc` | Setpoint mutation | **disabled** |
| `EXP-SCN004-backstop-enabled-457bc4c1` | Setpoint mutation | **enabled** |

The last two are the flagship comparison. CI verifies and independently reproduces
all three on every change, so a code change that silently altered a published
result would fail the build.

## Verifying

```bash
# Integrity: recompute every digest, reject missing or unexpected files
uv run blackstart evidence verify --all --evidence-root evidence/baseline

# Reproduction: re-execute and diff byte-for-byte
uv run blackstart evidence verify --all --reproduce --evidence-root evidence/baseline
```

Try breaking it — append a line to a `process.csv` and re-verify. It fails, and
names the file.

> **Integrity here is tamper-evident, not tamper-proof.** Digests catch
> corruption, partial writes and stale files. Anyone who can edit the artefacts
> can recompute the manifest. Signing is a roadmap item; see
> [ADR-005](../docs/adr/ADR-005-evidence-and-reproducibility.md).

## Interpreting results

Read [../docs/limitations.md](../docs/limitations.md) first. A BLACKSTART result
describes BLACKSTART: a fictional process with invented parameters, no detection
capability, and effects rather than mechanisms of compromise.
