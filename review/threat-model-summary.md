# Threat Model Summary

The experiment begins after a skilled adversary is assumed to have enough
authority to change a supervisory setpoint. No path to that authority is
simulated.

**Compromised/untrusted:** supervisory requested setpoint.

**Trusted in v0.1:** physics engine, experiment orchestrator, EBS-001 policy,
independent measurement channel, and evidence verifier.

**Not modeled:** initial access, malware, credentials, privilege escalation,
lateral movement, PLC exploitation, compromise of EBS-001, or evidence forgery.

The critical assumption is that supervisory compromise does not automatically
modify the independent backstop. If that separation does not hold, the flagship
claim does not follow. See [`docs/threat-model.md`](../docs/threat-model.md) for
the complete statement and [`docs/limitations.md`](../docs/limitations.md) for
defeaters.
