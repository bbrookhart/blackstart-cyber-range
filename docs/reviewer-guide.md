# Technical Reviewer Guide

A ten-minute path through BLACKSTART, with exact commands. You should not need to
reverse-engineer the repository to work out why it matters.

**Prerequisites:** Python 3.12+, [`uv`](https://docs.astral.sh/uv/). Docker only
for the optional topology section.

```bash
git clone <repo> && cd blackstart-cyber-range
make bootstrap
```

---

## Minute 0–2 — The research question and the architecture

BLACKSTART asks a harder question than whether an attacker can get into an OT
network:

> **If digital compromise occurs, can the physical mission still be kept inside
> acceptable bounds?**

The whole project is arranged around one causal chain:

```text
cyber event → digital capability → system dependency → control state
  → physical state → mission consequence → engineering response
    → mission preserved, or not
```

Read these three things, in this order:

1. [`configs/consequences.yaml`](../configs/consequences.yaml) — what must never
   happen, quantitatively. Note that consequence severity is **derived** from
   measurable conditions, never assigned.
2. [`configs/invariants.yaml`](../configs/invariants.yaml) — the five safety
   invariants, each with a rationale.
3. [`docs/adr/ADR-004-safety-invariant-design.md`](adr/ADR-004-safety-invariant-design.md)
   — in particular *why the invariant checker shares no code with the safety
   control*. Without that separation, the headline result would be a tautology.

Then confirm everything loads and cross-validates:

```bash
uv run blackstart config validate
```

---

## Minute 2–4 — The physical model and the safety invariants

The physics is deliberately small enough to verify by inspection. Every equation
is in [`blackstart/core/physics/process.py`](../blackstart/core/physics/process.py)
and documented in [ADR-002](adr/ADR-002-physical-process-model.md).

Two things worth checking specifically:

**Ground truth is a distinct object from the reported view.** See
[`blackstart/core/models.py`](../blackstart/core/models.py). The controller acts
on `ReportedState`; invariants evaluate `TruthState`; only INV-005 reads both.
This is why a scenario that deceives the operator cannot also falsify the
experimental record.

**The safe limit sits below the physical overflow height** (4.50 m vs 5.00 m), so
a safety excursion is an observable, recoverable state rather than an
unrepresentable one.

```bash
uv run pytest tests/unit/test_physics.py tests/unit/test_invariants.py -q
uv run pytest tests/property -q      # bounds that must hold across the input space
```

---

## Minute 4–6 — Run the baseline

A range that cannot demonstrate a clean baseline cannot support a claim about
anything else. If SCN-001 produced spurious violations, no violation anywhere
else would be interpretable.

```bash
uv run blackstart scenario list
uv run blackstart experiment run SCN-001 --evidence-root evidence/local
```

Expect: **C0**, zero invariant violations, 100% service availability, maximum
tank level ≈ 3.596 m against a 4.50 m limit.

---

## Minute 6–8 — Run the flagship comparison

The same scenario, the same seed, the same configuration, differing in exactly
one respect: whether the independent engineering constraint is present.

```bash
make demo
# equivalently:
uv run blackstart experiment compare SCN-004 \
    --variant backstop-disabled --variant backstop-enabled \
    --evidence-root evidence/local
```

Measured (seed 4242, committed in [`evidence/baseline/`](../evidence/baseline/)):

| Metric | Backstop disabled | Backstop enabled |
| --- | --- | --- |
| Maximum consequence | **C4** | **C1** |
| Invariant violations | 2 | 1 |
| Violated invariants | INV-001, INV-004 | INV-004 |
| Service availability | 46.71% | 100.00% |
| Unsafe-state duration | 639.5 s | 0.0 s |
| Maximum tank level | 5.000 m | 3.9998 m |
| Spill volume | 3.382 m³ | 0.000 m³ |

Three things to notice, because they are what distinguish a result from a demo:

- **INV-004 is violated in both variants.** It observes the *requested* setpoint,
  so the evidence that an implausible command was issued survives the constraint
  refusing it. That is a detection opportunity that does not depend on the
  defence having failed.
- **Service availability of 46.71%** is not a service outage — demand is met
  throughout. It falls because the critical function CF-001 requires *both*
  delivered service *and* no violated safety invariant.
- **BS-01 does the work here, and BS-03 never fires.** Check it:

```bash
uv run python -c "
import json,glob
for p in sorted(glob.glob('evidence/local/EXP-SCN004-*/metrics.json')):
    m=json.load(open(p)); b=m['backstop']
    print(m['variant'], m['maximum_consequence'], b['activation_counts'], 'trips:', b['trip_count'])
"
```

---

## Minute 8–10 — Inspect the evidence, then try to break it

Every experiment writes a self-describing directory.

```bash
ls evidence/local/EXP-SCN004-backstop-disabled-*/
cat evidence/local/EXP-SCN004-backstop-disabled-*/summary.md
```

Verify integrity, then **independently reproduce** — re-execute from the recorded
configuration and seed and compare every artefact byte-for-byte:

```bash
uv run blackstart evidence verify --all --reproduce --evidence-root evidence/local
uv run blackstart evidence verify --all --reproduce --evidence-root evidence/baseline
```

Now try to break it. Edit one number in a `process.csv` and re-verify:

```bash
echo "0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,C0," >> evidence/local/EXP-SCN004-backstop-enabled-*/process.csv
uv run blackstart evidence verify --all --evidence-root evidence/local   # fails
```

Finally, see the architectural view — and its gaps:

```bash
uv run blackstart graph paths --min-class C4
uv run blackstart graph reduction
```

40 paths reach C4 or above; 18 are interrupted by the backstop. Note that every
`CTRL-RESERVE → VLV-001` path is **NOT INTERRUPTED**: the backstop constrains the
pump command path and does nothing for the valve. That is a real gap in the
current design, surfaced by the model.

---

## What to attack if you want to find weaknesses

The five questions most likely to expose a problem, and where the answers live:

| Question | Where to look |
| --- | --- |
| Is "backstop enabled ⇒ no violations" a tautology? | `test_shares_no_code_with_the_invariant_checker`; the backstop imports nothing from `blackstart.core.invariants` |
| Is the result a lucky seed? | `TestSeedSensitivity::test_different_seeds_change_the_detail_but_not_the_finding` — checked across four seeds |
| Are the scenario expectations just fitted to whatever the code does? | They are, and that is the risk. [CONTRIBUTING.md](../CONTRIBUTING.md) treats updating an expectation to match a regression as the worst thing that can happen here. Judge the *thresholds* in `configs/`, which are independent of the code. |
| Does the architecture diagram match what deploys? | `make test-architecture` parses `docker-compose.yml` and `configs/architecture.yaml` and fails on disagreement |
| Can a scenario reach outside the process? | `tests/architecture/test_safety_boundary.py` walks the AST of `core` and `scenario_engine` |

---

## The whole quality gate

```bash
make check      # lint + strict mypy + 358 tests + 90% branch coverage gate
make audit      # dependency vulnerability audit
make docs       # configuration, scenario and cross-reference validation
```

Coverage is gated at 90% branch on safety-critical modules only
(`core`, `controller`, `scenario_engine`, `analysis`, `evidence`); currently 95%.
Repository-wide coverage is reported but not gated, because gating it rewards
testing trivial code and says nothing about whether the invariant logic is
exercised.

---

## Optional — the zoned topology

Requires a running Docker daemon.

```bash
make up && make health
open http://127.0.0.1:8080/
make down
```

Exactly one port is published, bound to loopback. The industrial DMZ, OT and
control networks are `internal`; no control-side port is reachable from the host.
The dashboard you see at the enterprise edge is displaying data that traversed
three conduits outward, and there is no command path back.

---

## Before you conclude anything

Read [limitations.md](limitations.md). BLACKSTART has **no detection
capability**, models **effects rather than mechanisms** of compromise, and
describes a **fictional** process with invented parameters. Its results support
claims about the model and nothing beyond it.
