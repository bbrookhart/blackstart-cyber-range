# Contributing to BLACKSTART

BLACKSTART is a research artefact. Its value rests on being reproducible,
honestly reported, and safe. Contributions are judged against those properties
before anything else.

---

## The three non-negotiables

### 1. Defensive purpose

BLACKSTART studies **effects and defences**, not intrusion mechanisms. A
contribution whose primary purpose is to make exploitation of real
infrastructure easier will be rejected, regardless of technical quality.

Concretely, the following are refused:

- Exploits, payloads, or offensive tooling of any kind
- Protocol attack implementations against real ICS products or stacks
- Scanning, target discovery, or anything that reaches an address it was not
  explicitly given
- Real utility credentials, configurations, network diagrams, or operational
  parameters — **every parameter in this repository must be invented**

The boundary is specified in
[ADR-006](docs/adr/ADR-006-scenario-safety-boundary.md) and enforced by
[`tests/architecture/test_safety_boundary.py`](tests/architecture/test_safety_boundary.py).
**If your change requires deleting or weakening one of those tests, open an issue
first.** That is a design conversation, not a pull request.

### 2. Reproducibility

An experiment must remain a pure function of `(version, configuration, seed)`.

- No wall-clock reads in `blackstart/core` or `blackstart/scenario_engine`
- No global `random` use anywhere — thread the seeded generator
- No dict-ordering or set-iteration dependence in anything serialised
- No parallelism inside a run

`blackstart evidence verify --all --reproduce` must pass.

### 3. Honest reporting

- Never commit a number that was not produced by the implementation
- If a capability does not exist, its metric is `NOT_IMPLEMENTED`, not `0.0`
- If a claim is not supported by evidence, weaken the claim
- New limitations go in [docs/limitations.md](docs/limitations.md) as part of the
  same change that introduces them

A contribution that makes the README more impressive without making the system
better is a regression.

---

## What every change must carry

| Change | Also required |
| --- | --- |
| New or changed safety logic | Unit tests, at least one property test, and a rationale in the invariant's configuration entry |
| New scenario | A research question, an `expected` block populated from a real run, and an entry in the scenario catalogue |
| New scenario effect | An ADR-006 update, registry entry, parameter validation, and an architecture-test update |
| Changed physics | ADR update, recomputed baseline evidence, and updated scenario expectations |
| New metric | A definition in `docs/consequence-model.md` or `docs/experimental-method.md`, and a test |
| Changed topology | `configs/architecture.yaml` updated **first**, then `docker-compose.yml`; architecture tests must pass |
| Framework mapping | A retrieval date, a rationale, and honest treatment of ambiguity |
| Any consequential design decision | An ADR |

### Scenario design rules

A scenario must:

- state a **research question** it exists to answer;
- use only effects from the closed registry;
- be deterministic under its declared seed;
- record its measured outcome in `expected`, from an actual run;
- carry an ATT&CK for ICS mapping **only where one is genuinely defensible**.

An empty `attack_ics` list is frequently the correct answer. A benign physical
disturbance maps to no adversary technique, and saying so is more useful than
inventing an association. Never map a technique because its name sounds related
to the outcome.

---

## Development workflow

```bash
git clone <repo> && cd blackstart-cyber-range

make bootstrap          # create the venv, install everything
uv run pre-commit install

# ... make your change ...

make check              # lint + typecheck + tests + coverage gate
make docs               # configuration, scenario and cross-reference validation
```

Before opening a pull request:

```bash
make lint typecheck test coverage audit
uv run blackstart evidence verify --all --reproduce --evidence-root evidence/baseline
```

### Code standards

- Python 3.12+, strict `mypy`, `ruff` clean
- Units in names (`tank_level_m`, `inflow_m3_s`, `tolerance_s`)
- No unexplained magic constants — name them or put them in configuration
- Pure functions for physical calculations where practical
- Comments explain **why**, not what; the code already says what
- Structured errors, no silent failures, no bare `except`

Branch coverage is gated at **90% on safety-critical modules**
(`core`, `controller`, `scenario_engine`, `analysis`, `evidence`). Repository-wide
coverage is reported but not gated, because gating it rewards testing trivial
code and says nothing about whether the invariant logic is exercised.

---

## If you change a result

Changing physics, control logic, invariants, or the consequence taxonomy will
change measured outcomes. When that happens:

1. Re-run every scenario under both variants.
2. Update each scenario's `expected` block **from the new measured values**.
3. Regenerate the committed baseline evidence.
4. Update any README figure that changed.
5. Explain in the pull request **why the new numbers are more correct**, not
   merely that they are different.

Updating an expectation to match a regression is the single most damaging thing
that can happen to this repository. If a number moved and you cannot explain
why, that is a finding — please open an issue rather than adjusting the
expectation.

---

## Reporting security or safety concerns

Do not open a public issue. See [SECURITY.md](SECURITY.md).

---

## Licence

Contributions are accepted under the [Apache License 2.0](LICENSE). By
contributing you confirm you have the right to submit the work under that
licence, and that it contains no non-public operational information.
