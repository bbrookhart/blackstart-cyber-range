# Experiment Summary

## Question

If supervisory setpoint authority is already compromised, can an independently
enforced engineering limit prevent the mutation from producing an unacceptable
physical consequence?

## Controlled comparison

- `EXP-BS-001-v1`, `SCN-004`, seed 4242, 0.5 s timestep, 1200 s duration;
- mutation at 180 s: requested tank target becomes 4.80 m;
- Condition A: backstop OFF;
- Condition B: backstop ON;
- initial state, demand, scenario, seed, timestep, attack event, and code are
  identical; only backstop state changes.

## Observed result

Without the backstop, true level reaches 5.0000 m, spends 639.5 s outside the
safety envelope, and reaches C4. With the backstop, the request remains visible,
the effective target is held to at most 3.60 m, true level peaks at 3.9998 m,
unsafe duration is 0.0 s, and maximum consequence is C1.

Use [results.csv](results.csv) for the generated values and
[`experiments/releases/v0.1.0/`](../experiments/releases/v0.1.0/) for canonical
provenance, process/control traces, invariant evaluations, metrics, independent
verification, and artifact hashes.

## Interpretation

The observed deterministic result is inconsistent with H0 for this frozen
configuration. It does not establish statistical significance or generalization
to operational water systems.
