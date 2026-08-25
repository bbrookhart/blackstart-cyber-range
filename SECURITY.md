# Security Policy

BLACKSTART is a **defensive research simulation**. It models what happens to a
fictional physical process after a digital compromise is assumed, in order to
study whether engineered controls can keep the physical mission inside safe
bounds.

It is not a penetration-testing tool, an adversary-emulation framework, or an
exploitation platform, and it must never be connected to a real control system.

---

## Intended scope

BLACKSTART exists to answer one question:

> If a sophisticated adversary is assumed capable of penetrating portions of the
> digital environment, can engineered cyber-physical controls prevent that
> compromise from producing unacceptable physical consequences?

Everything in this repository serves that question. Anything that would serve
the *opposite* question — how to achieve such a compromise against a real system
— is out of scope by design and is refused in review.

---

## The safety boundary

The boundary is **structural and tested**, not a promise in a document. It is
specified in [ADR-006](docs/adr/ADR-006-scenario-safety-boundary.md) and enforced
by [`tests/architecture/test_safety_boundary.py`](tests/architecture/test_safety_boundary.py).

Three properties hold, and each has a test:

1. **Scenarios are data, not code.** A scenario is a validated YAML document. It
   contains no expressions, scripts, imports or file paths, and loading one
   cannot execute anything.

2. **The effect vocabulary is closed.** Exactly seven effects exist. An unknown
   effect name is a load-time validation error, not a dynamic dispatch. A test
   asserts the registry contains nothing outside the documented list.

3. **The kernel cannot reach outside the process.** No module in
   `blackstart/core` or `blackstart/scenario_engine` imports a networking,
   subprocess, or filesystem-traversal module. A test walks the AST of every
   file in both packages and fails on any such import, or on an OS-level call
   like `os.system`.

Consequently **there is no code path from a scenario file to any system outside
the Python process.** Widening that boundary requires deleting a test, which is
a visible act in review.

### What effects are, and are not

`setpoint.override` writes to a field. It does not authenticate, bypass
authentication, craft a protocol frame, or exploit a flaw. It answers *"given
that an adversary achieved unauthorised control influence, which engineered
constraint prevents that influence from becoming an unacceptable physical
consequence?"*

This is deliberate scoping, and also a real limitation: BLACKSTART cannot tell
you whether such influence is achievable against any particular system.

---

## Not present in this repository, by policy

- Malware, ransomware, wipers, or any destructive payload
- Credential access, dumping, or brute-forcing tooling
- Persistence, lateral movement, or command-and-control tooling
- Network, port, or host scanning; any form of target discovery
- Exploits against any real device, protocol stack, or product
- Techniques for evading detection
- Real utility credentials, configurations, network diagrams, or operational
  parameters — **every parameter in this repository is invented**

---

## Safe testing boundary

**Permitted:**

- Running experiments through the CLI on your own machine
- Running the container topology on a host you control
- Modifying configuration, scenarios and models for your own research

**Not permitted, and not supported:**

- Connecting any part of BLACKSTART to a real OT asset, PLC, RTU, HMI,
  historian, or process network — under any circumstances
- Exposing BLACKSTART to the public internet, or to any network beyond the host
- Loading real utility data, credentials, or configuration into the range
- Using the range as a staging point for activity against any external system

### Isolation properties

The container topology publishes **exactly one port**: `127.0.0.1:8080`, the
read-only enterprise dashboard, bound explicitly to loopback. The industrial
DMZ, OT and control networks are declared `internal`, so containers attached only
to them have no route off the host. No control-side port is reachable from the
host at all.

Nothing in BLACKSTART initiates an outbound network connection. These properties
are asserted in
[`tests/architecture/test_exposure_and_posture.py`](tests/architecture/test_exposure_and_posture.py)
and re-checked against the running topology in CI.

---

## Security assumptions

Stated plainly, because a security model with unstated assumptions is not a
security model:

- **The range is trusted infrastructure to its operator.** It has no
  authentication, no authorisation, and no multi-tenancy. Anyone who can reach a
  service can use it. This is acceptable only because nothing is exposed beyond
  loopback.
- **Docker bridge networks are a topology boundary, not an enforcement boundary
  of the same character as separate physical networks with an inspecting
  firewall.** BLACKSTART demonstrates zone structure, not enforcement strength.
- **Evidence integrity is tamper-evident, not tamper-proof.** Manifest digests
  detect corruption, partial writes and stale files. Anyone who can edit the
  artefacts can recompute the manifest. Signing is on the roadmap; claiming more
  today would be an overstatement.
- **The backstop's independent measurement channel is a modelling assumption.**
  A real independent element can itself be compromised. See
  [docs/limitations.md](docs/limitations.md).

---

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes — current research release |
| < 0.1 | No |

BLACKSTART is pre-1.0 research software. Interfaces, configuration and evidence
formats may change between minor versions.

---

## Reporting a vulnerability

Please report privately, via **GitHub Security Advisories** on this repository
("Security" → "Report a vulnerability"). Do not open a public issue.

Please include: affected version and commit, what you observed, how to
reproduce, and the impact you believe it has.

**Please do not** include real utility data, credentials, or non-public
operational information in a report. If a finding depends on such data, describe
it abstractly and we will work out how to proceed.

### What we consider a vulnerability

- Any way for BLACKSTART to affect a system outside its own process
- Any breach of the scenario safety boundary described above
- Any host exposure beyond the single documented loopback port
- Any way to make an evidence package misrepresent what an experiment did
- Dependency vulnerabilities reachable from BLACKSTART code paths

### What we do not

- The absence of authentication on range services. This is a documented design
  property of an isolated single-operator range, not a defect.
- Findings that require having already connected the range to a real OT asset,
  which the policy above prohibits.
- Simulated "vulnerabilities" in the modelled process. Those are the subject
  matter, not defects.

### Response

We aim to acknowledge within 5 working days and to give an assessment within 15.
There is no bounty programme. Reporters are credited in the changelog unless
they prefer otherwise.

---

## Responsible use

BLACKSTART is published so that defenders, researchers and engineers can reason
rigorously about consequence-driven engineering. Simulation results describe the
behaviour of this model under a stated configuration and seed. They do not
establish how any real utility, control system or equipment would behave, and
they are not a safety case, a certification, or a substitute for engineering
analysis of a real system. See [docs/limitations.md](docs/limitations.md) and
[docs/research-integrity.md](docs/research-integrity.md).
