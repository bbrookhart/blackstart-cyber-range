# Dated Framework and Reference Baseline

**Verified:** 2026-08-28 UTC.

These publications inform design vocabulary and traceability. BLACKSTART claims
no compliance, conformance, certification, accreditation, implementation of an
agency method, or government endorsement.

| Reference | Version/status used | Official source | BLACKSTART use |
| --- | --- | --- | --- |
| INL Consequence-driven Cyber-informed Engineering | Public CCE description, retrieved 2026-08-28 | <https://inl.gov/national-security/cce/> | Consequence-first framing; not claimed as a CCE implementation |
| INL Cyber-informed Engineering | Public CIE description, retrieved 2026-08-28 | <https://inl.gov/national-security/cie/> | Engineering-design context |
| NIST SP 800-82 | Rev. 3, final, September 2023 | <https://csrc.nist.gov/pubs/sp/800/82/r3/final> | OT characteristics, architecture, and safety/availability priorities |
| NIST SP 800-82 Rev. 4 | Initial public draft as of retrieval date | <https://csrc.nist.gov/pubs/sp/800/82/r4/ipd> | Draft awareness only; Rev. 3 remains the final baseline |
| NIST SP 1800-45 | Final practice guide | <https://www.nccoe.nist.gov/projects/securing-water-and-wastewater-utilities> | Water/wastewater remote-access architecture concepts |
| NIST Cybersecurity Framework | CSF 2.0 | <https://www.nist.gov/cyberframework> | High-level function orientation only |
| NIST SP 800-61 | Rev. 3, final, April 2025 | <https://csrc.nist.gov/pubs/sp/800/61/r3/final> | Incident-response evidence context; no IR capability claim |
| MITRE ATT&CK | v19.2, released 2026-08-06 | <https://github.com/mitre-attack/attack-stix-data/releases/tag/v19.2> | Version-pinned behavior orientation |
| CISA Cross-Sector Cybersecurity Performance Goals | CPG 2.0 | <https://www.cisa.gov/cybersecurity-performance-goals-2-0-cpg-2-0> | Informational control-area orientation |

## ATT&CK dataset pin

The official ATT&CK for ICS STIX 2.1 dataset was retrieved from the release tag
and hashed before mapping review:

```yaml
framework: MITRE ATT&CK
domain: ICS
version: "19.2"
retrieved_at: "2026-08-28"
dataset_hash: sha256:08b83d2cea6b6d6752468ef0e62e2ab2a53c9443ef72c439ecccb07ab9e89da9
dataset_bytes: 4057891
```

The authoritative machine-readable pin is
[`framework-mappings/attack-dataset.yaml`](../framework-mappings/attack-dataset.yaml).
Only behaviors actually represented by BLACKSTART scenarios are asserted in
[`attack-ics.yaml`](../framework-mappings/attack-ics.yaml); candidate mechanisms
and rejected mappings remain explicitly distinguished.

## Interpretation discipline

References are not evaluation results. A link between a design element and a
publication means the publication informed the work; it does not mean the
publication's authors reviewed BLACKSTART or that the project satisfies their
requirements. If an identifier cannot be verified against its official source,
the repository omits or weakens the mapping.
