# Evidence Packages

`make experiment` creates one package per controlled condition under
`evidence/local/`. Canonical v0.1 evidence is committed under
`experiments/releases/v0.1.0/evidence/` so the result, report, figures, and exact
inputs stay together.

```text
<experiment-id>/
├── manifest.json
├── environment.json
├── configuration.json
├── scenario.json
├── events.jsonl
├── process.csv
├── control.csv
├── invariants.json
├── consequences.json
├── metrics.json
├── graph.json
├── verification.json
└── summary.md
```

The experiment identifier encodes scenario, condition, and the first eight
characters of the complete configuration identity. That identity includes
simulator version, source fingerprint, resolved configuration, scenario, and
seed. Existing packages are never silently overwritten.

`manifest.json` records SHA-256 digests for every other package artifact plus
the git commit, source fingerprint, configuration hash, and scenario hash.
`verification.json` is produced by a second metric implementation that reads the
serialized trace rather than calling the primary metrics engine.

```bash
uv run blackstart evidence verify --all --evidence-root evidence/local
uv run blackstart evidence verify --all --reproduce --evidence-root evidence/local
```

Verification rejects missing or unexpected files, changed digests, schema
errors, cross-artifact identity disagreement, and a failed independent result
check. Reproduction regenerates the deterministic artifacts and compares their
bytes; environment provenance is checked structurally because the git commit and
wall clock may legitimately differ.

Plain JSON, JSONL, CSV, Markdown, and SVG are deliberate: a reviewer can inspect
the complete result without a database. Manifest digests are tamper-evident, not
cryptographic signatures; a party able to edit every file can recompute them.
