# Experiments

Experiment definitions and their recorded findings. Evidence artefacts live in
[`../evidence/`](../evidence/README.md); this directory holds the *interpretation*.

| Experiment | Scenarios | Question | Finding |
| --- | --- | --- | --- |
| [baseline](baseline/README.md) | SCN-001, SCN-004 | Does an independent engineering constraint prevent an unauthorised control-state change from producing an unacceptable physical consequence? | Yes, in this model: C4 → C1 |

## Reproducing any of them

```bash
make bootstrap
make demo                                    # the flagship comparison
uv run blackstart evidence verify --all --reproduce --evidence-root evidence/baseline
```

## Adding one

An experiment is a scenario, a set of variants, a seed, and a written finding. The
finding must be derived from measured evidence and must state its own limitations.
See [../docs/experimental-method.md](../docs/experimental-method.md).
