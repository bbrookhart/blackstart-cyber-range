<div align="center">

<img src="assets/blackstart-hero.svg" alt="BLACKSTART — Critical Infrastructure Under Compromise" width="100%">

<br>

**A Consequence-Driven Cyber-Physical Resilience Range**

> **Assume compromise. Preserve the mission.**

[![CI](https://github.com/bbrookhart/blackstart-cyber-range/actions/workflows/ci.yml/badge.svg)](https://github.com/bbrookhart/blackstart-cyber-range/actions/workflows/ci.yml)
[![Security](https://github.com/bbrookhart/blackstart-cyber-range/actions/workflows/security.yml/badge.svg)](https://github.com/bbrookhart/blackstart-cyber-range/actions/workflows/security.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-1B2430)](pyproject.toml)
[![License Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-1B2430)](LICENSE)
[![Version 0.1.0](https://img.shields.io/badge/version-0.1.0-1B2430)](CHANGELOG.md)

</div>

**Research prototype — v0.1.0.** In the frozen synthetic water-storage
experiment, the unauthorized 4.80 m supervisory setpoint drove the unprotected
process to **5.0000 m**, **639.5 s outside the safety envelope**, and consequence
**C4**. Under the same code, state, demand, seed, timestep, and attack event, the
independent backstop limited the protected run to **3.9998 m**, **0.0 s unsafe**,
and consequence **C1**.

> [!IMPORTANT]
> This is a result about a fictional deterministic simulation. It is not an
> operational water-system safety claim, field validation, certification, or
> evidence of framework compliance.

## Measured result

<!-- BEGIN GENERATED EXP-BS-001 RESULTS -->

### Flagship experiment — EXP-BS-001

| Metric | Backstop OFF | Backstop ON | Difference |
| --- | ---: | ---: | --- |
| Maximum tank level | 5.0 m | 3.9998 m | 1.0002 reduction |
| Unsafe duration | 639.5 s | 0.0 s | 639.5000 reduction |
| Invariant violation intervals | 3 | 1 | 2.0000 reduction |
| Invariant violation duration | 1660.0 s | 0.5 s | 1659.5000 reduction |
| Maximum consequence | C4 | C1 | C4 → C1 |
| Mission service availability | 46.7083 % | 100.0 % | +53.2917 improvement |
| Recovery time | NOT_RECOVERED | NOT_RECOVERED | no change |

<!-- END GENERATED EXP-BS-001 RESULTS -->

This table is replaced from each run's `metrics.json` by `make release-artifacts`;
it is not independently maintained. The canonical evidence is under
[`experiments/releases/v0.1.0/`](experiments/releases/v0.1.0/).

![EXP-BS-001 true physical trajectory](assets/exp-bs-001-trajectory.svg)

![Protected requested versus effective setpoint](assets/exp-bs-001-control.svg)

The attack remains visible in both conditions. The backstop changes the
**effective** setpoint and physical consequence; it does not delete the request.

## Research question and hypothesis

> **If an adversary is assumed capable of modifying a critical control parameter
> after penetrating portions of the digital environment, can an independently
> enforced engineering backstop prevent that digital compromise from producing
> an unacceptable physical consequence?**

**H1:** the independently enforced backstop will reduce or eliminate the
unacceptable physical consequence caused by the unauthorized control-state
mutation.

**H0:** the backstop produces no meaningful difference under the defined
experiment.

The observed deterministic comparison is inconsistent with H0 for the frozen
configuration. No statistical significance or real-world generalization is
claimed.

## Flagship experiment

`EXP-BS-001-v1` runs `SCN-004 — Unauthorized Setpoint Mutation` twice:

| Controlled element | Value |
| --- | --- |
| Process | Fictional municipal water storage and pumping |
| Simulation | 1200 s, explicit Euler, 0.5 s timestep |
| Seed | 4242 |
| Initial state and demand | Identical in both conditions |
| Mutation | At 180 s, requested setpoint becomes 4.80 m |
| Condition A | Backstop OFF |
| Condition B | Backstop ON |
| Only changed factor | Backstop state |

The unprotected condition is a meaningful baseline failure: the true level
crosses the 4.50 m maximum-safe boundary and saturates at the synthetic 5.00 m
weir crest. In the protected condition, the same request is recorded but the
effective target remains at the configured 3.60 m engineering maximum.

## Physical process

The model contains a source, inlet pump, constant-area storage tank, and gravity
outlet serving synthetic demand. True physical state and reported sensor state
are separate variables. The update is:

```text
level[t+1] = level[t] + (inflow[t] - outflow[t]) × Δt / tank_area
```

Units, synthetic parameter rationale, Euler stability check, limits, and
saturation are documented in [the physical model](docs/physical-model.md). The
mission-critical function is to satisfy synthetic demand while remaining inside
the defined safe operating bounds.

## Engineering backstop and invariants

EBS-001 is a policy component between the untrusted supervisory request and
physical actuation:

```text
supervisory request → engineering backstop → effective target
                    → controller → pump → tank → invariant → consequence
```

The scenario can mutate the request but cannot mutate EBS-001 policy. With the
backstop active, BS-01 bounds the setpoint and BS-02 constrains slew before the
normal controller acts. Other rules enforce high-level, suction, and anti-cycle
permissives.

| ID | Machine-evaluated property | Flagship role |
| --- | --- | --- |
| INV-001 | True tank level ≤ 4.50 m | Defines the C4 upper-bound breach |
| INV-002 | True tank level ≥ 1.00 m | Protects required reserve |
| INV-003 | Pump not enabled with unsafe source level | Dry-run protection |
| INV-004 | Requested command rate within 0.05 m/s | Preserves the anomalous request as evidence |
| INV-005 | Effective setpoint between 1.50 and 3.60 m | Tests the central backstop property |
| INV-006 | Reported level tracks true level within 0.10 m | Cross-view integrity check |

Every timestep evaluation, including observed value, threshold, status, and
timestamp, is serialized to `invariants.json`. The invariant engine does not
share implementation code with the backstop.

## Causal evidence

![SCN-004 consequence path](assets/consequence-path.svg)

The machine-readable `graph.json` records the unprotected path and protected
interruption. Inspect it directly:

```bash
uv run blackstart graph consequence-path SCN-004
```

The causal graph is intentionally implemented with NetworkX; no graph database
is required.

## Reproduce the result

From a clean clone, no credentials, services, database, or manual configuration
are needed:

```bash
git clone https://github.com/bbrookhart/blackstart-cyber-range
cd blackstart-cyber-range
make bootstrap
make test
make experiment
```

The complete release gate is:

```bash
scripts/reproduce_exp_bs_001.sh
```

Useful commands:

```bash
uv run blackstart status
uv run blackstart experiment run SCN-004 --backstop off
uv run blackstart experiment run SCN-004 --backstop on
uv run blackstart experiment compare SCN-004 --backstop off --backstop on
uv run blackstart evidence verify --all --reproduce --evidence-root evidence/local
for directory in evidence/local/EXP-*; do
  uv run blackstart experiment verify-results "$(basename "$directory")" \
    --evidence-root evidence/local
done
make results
```

## Evidence and independent verification

Each condition produces:

```text
evidence/<experiment-id>/
├── manifest.json        provenance and SHA-256 for every major artifact
├── environment.json     runtime, OS, architecture, image, and seed
├── configuration.json   fully resolved configuration
├── scenario.json        exact scenario executed
├── events.jsonl         common-envelope causal event stream
├── process.csv          true and reported state per timestep
├── control.csv          request, effective target, decision, and command
├── invariants.json      every evaluation and violation interval
├── consequences.json    classified consequence events
├── metrics.json         primary metrics-engine output
├── graph.json           causal path and protected interruption
├── verification.json    independent calculation from process.csv
└── summary.md           human-readable result and limitations
```

Verification rejects missing or unexpected artifacts, digest mismatches, schema
errors, and inconsistent experiment IDs. A second implementation independently
recalculates maximum level, unsafe duration, violation count, and maximum
consequence from serialized evidence. Integrity is tamper-evident, not
tamper-proof; no evidence signing is claimed.

## Threat and consequence models

The threat assumption is narrow: a skilled adversary already has enough access
to alter a supervisory setpoint. BLACKSTART does **not** model initial access,
malware delivery, credential theft, privilege escalation, lateral movement, or
PLC exploitation. The trusted computing base is the physics engine, experiment
orchestrator, EBS-001 policy, and evidence verifier. See the
[threat model](docs/threat-model.md) and [assurance case](docs/assurance-case.md).

Consequence classes are deterministic: C0 normal, C1 minor deviation, C2
operational degradation, C3 required service degradation, C4 unsafe physical
state, and C5 catastrophic mission failure. Thresholds and dwell times are
configuration, not hidden constants.

## Quality and traceability

Ruff, strict mypy, pytest, Hypothesis property tests, integration tests,
architecture tests, deterministic replay, schema checks, evidence verification,
and an independent metric path run in CI. Safety-critical modules are held to a
90% branch-coverage gate. The v0.1 release gate passed **385 tests** and measured
**94.09% branch coverage** across the selected critical modules. CI also runs the
flagship comparison and uploads its evidence and report.

The dated [framework baseline](docs/framework-baseline.md) records the exact
official versions used: ATT&CK for ICS v19.2 with a pinned dataset hash, NIST SP
800-82 Rev. 3, NIST SP 1800-45, NIST CSF 2.0, NIST SP 800-61 Rev. 3, CISA CPG
2.0, and INL CCE/CIE materials. Mappings are informational only and do not claim
compliance, certification, or endorsement.

## Limitations

- simplified single-tank process with synthetic parameters and telemetry;
- no calibrated facility model, real utility, real network, or operational data;
- no real PLC, hardware-in-the-loop, SCEPTRE integration, or field validation;
- no real adversary or exploit chain—the mutation is a controlled fixture;
- supervisory compromise is assumed, while backstop policy is outside the
  modeled compromise;
- one deterministic flagship scenario and no statistical inference;
- no detection analytic, formal verification, safety case, or certification;
- manifest hashes detect changes but are not signatures.

The full boundary is in [docs/limitations.md](docs/limitations.md) and
[docs/research-integrity.md](docs/research-integrity.md).

## Future research

The next experiment should evaluate a sensor-state manipulation against the
same frozen process and independent measurement assumptions. Later work may
cover redundant constraints, uncertainty, formal methods, hardware-in-the-loop,
PLC integration, or SCEPTRE. None is claimed in v0.1.

## Responsible use

BLACKSTART is a defensive, isolated research simulation. It contains no malware,
exploit, credential, persistence, lateral-movement, or scanning capability. Do
not connect it to an operational control system or use real utility data. See
[SECURITY.md](SECURITY.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

No affiliation with or endorsement by INL, NIST, CISA, MITRE, Sandia, IEC, ISA,
any government, utility, or vendor is claimed or implied.

## Citation

```bibtex
@software{blackstart_2026,
  title   = {BLACKSTART: A Consequence-Driven Cyber-Physical Resilience Range
             for Critical Infrastructure Under Compromise},
  author  = {Brookhart, Brian},
  year    = {2026},
  version = {0.1.0},
  license = {Apache-2.0},
  url     = {https://github.com/bbrookhart/blackstart-cyber-range}
}
```

Machine-readable metadata: [CITATION.cff](CITATION.cff).

## License

[Apache License 2.0](LICENSE). Result figures are generated from committed
experiment evidence; source artwork is original to this repository.

<div align="center">
<br>
<sub><b>Assume compromise. Preserve the mission.</b></sub>
</div>
