# Ten-Minute Reviewer Guide

The goal is to test the causal claim, not tour every repository feature.

## Minute 0–2 — Read the question and result

Read the first two README sections and
[`review/experiment-summary.md`](../review/experiment-summary.md). Confirm that
the exact question is post-compromise consequence containment, not intrusion
prevention.

The result to audit is:

| Condition | Max true level | Unsafe duration | Max consequence |
| --- | ---: | ---: | ---: |
| Backstop OFF | 5.0000 m | 639.5 s | C4 |
| Backstop ON | 3.9998 m | 0.0 s | C1 |

## Minute 2–3 — Inspect the process

Read [`docs/physical-model.md`](physical-model.md) and
[`experiments/EXP-BS-001/config.yaml`](../experiments/EXP-BS-001/config.yaml).
Check the explicit Euler update, 0.5 s timestep, 5.00 m saturation, 4.50 m
maximum-safe limit, synthetic parameter statement, and separate true/reported
state.

## Minute 3–4 — Inspect the backstop and invariants

Open `blackstart/controller/backstop.py`, `configs/invariants.yaml`, and
`blackstart/core/invariants/water.py`. Verify that:

- the scenario mutates the requested value, not EBS-001 policy;
- BS-01 constrains the effective target before the normal controller acts;
- INV-005 independently checks the effective 1.50–3.60 m target bound;
- INV-001 evaluates true tank level against 4.50 m;
- INV-006, not INV-005, compares reported and true state.

## Minute 4–7 — Run EXP-BS-001

```bash
make bootstrap
make clean-results
make experiment
```

The terminal must show the same `SCN-004` event in both conditions and print the
OFF, ON, and DELTA sections. No Docker services are required.

## Minute 7–9 — Inspect and verify evidence

```bash
uv run blackstart evidence verify --all --reproduce \
  --evidence-root evidence/local

for directory in evidence/local/EXP-*; do
  uv run blackstart experiment verify-results "$(basename "$directory")" \
    --evidence-root evidence/local
done
```

Then inspect:

- `control.csv` around 180 s: request 4.80 m in both; protected effective target
  never exceeds 3.60 m;
- `process.csv`: true physical trajectories;
- `invariants.json`: per-timestep records plus explicit violation intervals;
- `verification.json`: independent values and tolerances;
- `manifest.json`: hashes, source fingerprint, configuration/scenario hashes,
  environment, and code revision;
- `experiments/local/EXP-BS-001/figures/`: plots generated from evidence.

## Minute 9–10 — Challenge the claim

Read [`docs/threat-model.md`](threat-model.md),
[`docs/assurance-case.md`](assurance-case.md), and
[`docs/limitations.md`](limitations.md). Ask:

1. Is only backstop state different?
2. Does the unsafe baseline arise from transparent synthetic physics?
3. Is the request retained in the protected evidence?
4. Do the independent and primary metrics agree?
5. Would compromise of EBS-001 invalidate the result? (Yes.)
6. Is any claim generalized to a real utility? (It must not be.)

For the full gate, run `scripts/reproduce_exp_bs_001.sh`. Deliberately modify a
copied artifact and confirm `blackstart evidence verify` rejects it.
