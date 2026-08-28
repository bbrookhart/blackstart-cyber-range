# Experimental Method

How to run a BLACKSTART experiment, what it produces, and what makes the result
believable.

---

## The determinism contract

```text
(simulator version, source fingerprint, configuration, scenario, seed)
  ──► experiment result
```

Guaranteed by: a fixed timestep; no wall-clock read in the kernel; a single
explicitly seeded generator threaded through the runner; no global `random` use
anywhere; canonical JSON serialisation with sorted keys; no parallelism inside a
run.

`configuration` is hashed as SHA-256 over the canonical serialisation of the fully
resolved configuration — process, invariants, consequences, architecture, the
scenario's causal fingerprint, the variant, the seed, and the code version.

### What the hash deliberately excludes

A scenario's prose — name, description, research question, notes — and its
`expected` block are **not** hashed. They are documentation and assertions *about*
a result, not inputs *to* it.

Including them would mean that fixing a typo, or recording a measured expectation,
silently invalidated every experiment identifier for that scenario. That would
train a reader to ignore identifier changes, which is the opposite of what the
hash is for.

Changing an effect parameter, a seed, a duration, or any configuration value does
change the hash — and therefore the experiment identifier.

---

## Running experiments

```bash
uv run blackstart scenario list
uv run blackstart scenario show SCN-004

uv run blackstart experiment run SCN-001 --evidence-root evidence/local
uv run blackstart experiment run SCN-004 --variant backstop-disabled --seed 99

uv run blackstart experiment compare SCN-004 \
    --variant backstop-disabled --variant backstop-enabled
```

A comparison requires all runs to share a scenario and a seed. Comparing across
different inputs would not isolate the variable under study, and the CLI refuses
it.

---

## Variants

v0.1 defines exactly two, differing in one respect:

| Variant | Backstop |
| --- | --- |
| `backstop-disabled` | Absent — the control case |
| `backstop-enabled` | EBS-001 active |

The disabled variant is a **strict pass-through**: it records nothing and changes
nothing, verified by a property test over the whole input space. If it were
anything else, the comparison would be measuring two differences instead of one.

---

## The evidence package

```text
evidence/<root>/EXP-SCN004-backstop-enabled-<identity>/
├── manifest.json       provenance, source/config/scenario hashes, artifact digests
├── environment.json    Python, OS, architecture, image, seed
├── configuration.json  the fully resolved configuration actually executed
├── scenario.json       exact scenario document
├── events.jsonl        ordered structured event stream
├── process.csv         per-timestep true AND reported state
├── control.csv         requested/effective target, decision, physical level
├── invariants.json     every evaluation plus intervals and peak excursion
├── consequences.json   consequence timeline and maximum severity
├── metrics.json        computed research metrics
├── graph.json          machine-readable causal path
├── verification.json   independent metric calculation
└── summary.md          human-readable account, with its own limitations
```

Plain JSONL and CSV, deliberately: a reviewer can inspect, diff and grep a package
with a text editor and no BLACKSTART tooling, which is worth more than query
performance at this scale.

`process.csv` carries `true_*` and `reported_*` column pairs side by side, so a
telemetry-integrity effect is visible by inspection — in SCN-003 the two level
columns simply stop agreeing.

---

## Verification, at two strengths

```bash
# Structural + cryptographic integrity
uv run blackstart evidence verify --all --evidence-root evidence/local

# Independent reproduction: re-execute and diff byte-for-byte
uv run blackstart evidence verify --all --reproduce --evidence-root evidence/local
```

`verify` recomputes every artefact digest and the top-level integrity digest, and
fails on a missing file *or* an unexpected extra one.

`--reproduce` re-executes the experiment from the recorded configuration and seed
and compares deterministic artifacts byte-for-byte. Environment and manifest
provenance are structurally checked because the wall clock and git revision of a
reproduction may legitimately differ.

**Integrity is tamper-evidence, not tamper-proofing.** Anyone who can edit the
artefacts can recompute the manifest. It defends against corruption, partial
writes and stale files, not against a motivated forger.

---

## Scenario expectations

Every scenario carries an `expected` block populated from **actual measured
runs**, asserted by `tests/integration/test_scenario_expectations.py`.

A divergence means either the implementation regressed or the design intent was
wrong. Both require investigation.

> Updating an expectation to match a regression is the single most damaging thing
> that can happen to this repository. If a number moved and you cannot explain
> why, that is a finding.

The suite also asserts the *specific research claims* the README makes — including
which backstop rule acts in which scenario — so a claim cannot survive a change
that invalidates it.

---

## Seed sensitivity

Each scenario declares one seed. The flagship finding is additionally checked
across four seeds (`TestSeedSensitivity`): traces differ, the conclusion does not.

That is enough to show the result is not a single-seed artefact. It is **nowhere
near** enough for a statistical claim, and none is made. No confidence intervals,
distributions or significance tests are produced anywhere.

---

## Adding a scenario

1. Write `scenarios/SCN-0NN.yaml` with a **research question** it exists to
   answer, a seed, a duration, and events drawn from the closed effect registry.
2. Run it under both variants.
3. Record the measured outcome in `expected` — from the real run, never predicted.
4. Add an ATT&CK for ICS mapping **only if genuinely defensible**; an empty
   mapping is frequently correct.
5. Update `framework-mappings/attack-ics.yaml`, either with the mapping or with
   the scenario listed under `unmapped_scenarios` with a reason. A test enforces
   that every scenario is one or the other.

See [CONTRIBUTING.md](../CONTRIBUTING.md).
