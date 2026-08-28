"""Pydantic schemas for evidence-package boundary validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["EnvironmentDocument", "EventEnvelope", "ManifestDocument", "VerificationDocument"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactDigest(_Strict):
    """One artifact digest entry."""

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0)


class ManifestDocument(BaseModel):
    """Required top-level manifest fields; extensible by release."""

    model_config = ConfigDict(extra="allow")

    experiment_id: str
    blackstart_version: str
    git_commit: str
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenario_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: dict[str, ArtifactDigest]


class EnvironmentDocument(_Strict):
    """Reproducibility environment record."""

    experiment_id: str
    blackstart_version: str
    git_commit: str
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    python_version: str
    os: str
    os_release: str
    architecture: str
    container_images: list[str]
    seed: int
    scenario: str
    configuration_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: str


class EventEnvelope(_Strict):
    """Common event envelope shared by every structured telemetry event."""

    timestamp: float
    t_s: float
    experiment_id: str
    event_type: str
    source: str
    zone: str
    asset_id: str
    severity: str
    data: dict[str, Any]


class VerificationDocument(BaseModel):
    """Independent result-verification artifact."""

    model_config = ConfigDict(extra="allow")

    experiment_id: str
    method: str
    passed: bool
    checks: list[dict[str, Any]]
    errors: list[str]
