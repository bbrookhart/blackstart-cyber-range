# Reproduction

## Clean clone

```bash
git clone https://github.com/bbrookhart/blackstart-cyber-range
cd blackstart-cyber-range
make bootstrap
make test
make experiment
```

## Verify all locally generated evidence

```bash
uv run blackstart evidence verify --all --reproduce \
  --evidence-root evidence/local

for directory in evidence/local/EXP-*; do
  uv run blackstart experiment verify-results "$(basename "$directory")" \
    --evidence-root evidence/local
done
```

`scripts/reproduce_exp_bs_001.sh` runs the full code-quality, test, coverage,
experiment, evidence, and independent-result gate. No credentials, external
service, database, Docker runtime, or manual file edit is required for the core
experiment.

## What success means

- all evidence packages pass schema, identity, and digest checks;
- deterministic replay reproduces every deterministic artifact;
- independent recalculation agrees with the primary metrics engine;
- the generated comparison reports OFF C4 / 639.5 s unsafe and ON C1 / 0.0 s
  unsafe.
