#!/usr/bin/env python3
"""Retrieve the pinned official ATT&CK for ICS dataset and verify its digest."""

from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path
from typing import Any

import yaml


def _load_pin(path: Path) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a mapping")
    for field in ("framework", "domain", "version", "retrieved_at", "source", "dataset_hash"):
        if not document.get(field):
            raise ValueError(f"{path} is missing {field}")
    return document


def main() -> int:
    """Download the configured dataset and fail unless bytes match the pin."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pin",
        type=Path,
        default=Path("framework-mappings/attack-dataset.yaml"),
        help="Machine-readable ATT&CK dataset pin.",
    )
    args = parser.parse_args()
    pin = _load_pin(args.pin)

    source = str(pin["source"])
    if not source.startswith("https://raw.githubusercontent.com/mitre-attack/"):
        raise ValueError("ATT&CK dataset source must be the official MITRE HTTPS repository")
    request = urllib.request.Request(  # noqa: S310 -- scheme and authority constrained above
        source, headers={"User-Agent": "BLACKSTART-v0.1-dataset-verifier"}
    )
    digest = hashlib.sha256()
    byte_count = 0
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            byte_count += len(chunk)

    actual = f"sha256:{digest.hexdigest()}"
    if actual != pin["dataset_hash"]:
        raise ValueError(
            f"ATT&CK dataset hash mismatch: expected {pin['dataset_hash']}, got {actual}"
        )
    if byte_count != pin.get("dataset_bytes"):
        raise ValueError(
            f"ATT&CK dataset size mismatch: expected {pin.get('dataset_bytes')}, got {byte_count}"
        )
    print(f"MITRE ATT&CK for ICS v{pin['version']} verified: {byte_count} bytes, {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
