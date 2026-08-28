# BLACKSTART v0.1 External Review Package

This directory is the shortest path through the `EXP-BS-001-v1` claim. It is a
review aid, not a second source of truth. `results.csv` and `figures/` are
regenerated from canonical evidence by `make release-artifacts`.

1. Read [experiment-summary.md](experiment-summary.md).
2. Check [threat-model-summary.md](threat-model-summary.md).
3. Inspect [results.csv](results.csv) and the trajectory figure.
4. Follow [reproduction.md](reproduction.md).
5. Read [`docs/assurance-case.md`](../docs/assurance-case.md) and
   [`docs/limitations.md`](../docs/limitations.md) before evaluating the claim.

The supported conclusion is narrow: in the documented synthetic configuration,
the independent backstop prevented the tested supervisory mutation from
producing the physical consequence observed in the unprotected condition.
