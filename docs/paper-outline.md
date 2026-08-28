# Paper Outline

## Provisional title

**Assume Compromise, Preserve the Mission: Experimental Evaluation of
Consequence-Constraining Controls in a Synthetic Cyber-Physical System**

## Abstract skeleton

- Problem: prevention failure does not necessarily determine physical outcome.
- Question: can an independent engineering constraint contain a post-compromise
  supervisory setpoint mutation?
- Method: deterministic single-tank simulation, explicit invariants, controlled
  backstop OFF/ON comparison, serialized evidence, dual metric calculation.
- Result: OFF reaches 5.0000 m, 639.5 s unsafe, C4; ON reaches 3.9998 m,
  0.0 s unsafe, C1.
- Boundary: synthetic model, one scenario, no statistical or operational claim.

## Contribution statement

1. A deterministic cyber-physical experimental environment.
2. Explicit safety invariants connecting digital action to physical consequence.
3. An independently enforced engineering backstop.
4. A controlled post-compromise mutation scenario.
5. Reproducible protected/unprotected evidence with independent verification.

## Research questions

- **RQ1:** the exact v0.1 research question in the technical report.
- **RQ2, future:** which independence assumptions most affect containment under
  sensor-state manipulation?

## Methodology

- document the physical equation, units, Euler timestep, saturation, and
  synthetic parameter origin;
- freeze `EXP-BS-001-v1` configuration and seed;
- preserve attack event in both conditions and vary only backstop state;
- evaluate true-state invariants at every timestep;
- derive consequence and metrics from the trace;
- serialize hashes, schemas, causal graph, and environment;
- independently recalculate release-critical metrics.

## Result table

Use `experiments/releases/v0.1.0/results-table.md` directly. Do not transcribe
values into the manuscript without a generation step.

## Figures

1. True physical trajectory, protected and unprotected, with safe boundaries.
2. Protected requested versus effective control target.
3. Distance to nearest safety boundary.
4. SCN-004 causal consequence path and EBS-001 interruption.

## Related work placeholders

- consequence-driven and cyber-informed engineering;
- resilient control and safety interlocks under compromised supervision;
- reproducible cyber-physical security experimentation;
- OT testbeds and water-process simulations;
- explicit assurance arguments for security controls.

Populate only from reviewed primary sources; no placeholder may become a claim
without citation.

## Threats to validity

- construct: lumped synthetic model versus hydraulic facility behavior;
- internal: isolation of backstop state and shared implementation risks;
- external: no demonstrated generalization to real OT systems;
- reproducibility: platform-sensitive floating-point serialization versus
  metric-level tolerance.

## Limitations

Simplified physics, synthetic telemetry, no real PLC or network, no
hardware-in-the-loop, no real adversary, assumed supervisory compromise,
backstop outside modeled compromise, one flagship scenario, no statistical
power, and no formal proof.

## Future experiments

First: sensor-state manipulation with frozen plant and explicit independent
measurement failures. Later: redundant safety controls, uncertainty analysis,
formal modeling, and hardware-in-the-loop only after equivalent evidence gates
exist.
