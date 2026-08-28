"""Release-level integration coverage for EXP-BS-001."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from blackstart.core.config import BlackstartConfig
from blackstart.experiment.flagship import run_flagship

pytestmark = pytest.mark.integration


def test_flagship_generates_verified_release_and_review_artifacts(
    config: BlackstartConfig, tmp_path: Path
) -> None:
    """The one-command path produces measured, provenance-linked deliverables."""
    readme = tmp_path / "README.md"
    readme.write_text(
        "before\n<!-- BEGIN GENERATED EXP-BS-001 RESULTS -->\nstale\n"
        "<!-- END GENERATED EXP-BS-001 RESULTS -->\nafter\n",
        encoding="utf-8",
    )
    release = run_flagship(
        config,
        evidence_root=tmp_path / "evidence",
        output_directory=tmp_path / "release",
        assets_directory=tmp_path / "assets",
        technical_report_path=tmp_path / "report.md",
        readme_path=readme,
        review_directory=tmp_path / "review",
    )

    off, on = release.runs
    assert off.metrics["maximum_consequence"] == "C4"
    assert off.metrics["unsafe_state_duration_s"] == pytest.approx(639.5)
    assert on.metrics["maximum_consequence"] == "C1"
    assert on.metrics["unsafe_state_duration_s"] == 0.0
    assert release.comparison["consequence_containment"]["unsafe_state_duration_s"][
        "containment_pct"
    ] == pytest.approx(100.0)

    for path in release.figures.values():
        assert path.is_file() and path.stat().st_size > 1000
        assert (tmp_path / "assets" / path.name).is_file()
        assert (tmp_path / "review" / "figures" / path.name).is_file()

    manifest = json.loads(
        (release.output_directory / "release-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["release"] == "v0.1.0"
    assert manifest["source_fingerprint"] == off.result.source_fingerprint
    assert "figures/exp-bs-001-trajectory.svg" in manifest["artifacts"]

    refreshed = readme.read_text(encoding="utf-8")
    assert "stale" not in refreshed
    assert "639.5 s" in refreshed
    assert "+53.2917 improvement" in refreshed
    technical_report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "(assets/exp-bs-001-trajectory.svg)" in technical_report

    with (tmp_path / "review" / "results.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    unsafe = next(row for row in rows if row["metric"] == "Unsafe duration")
    assert unsafe["backstop_off"] == "639.5"
    assert unsafe["backstop_on"] == "0.0"


def test_flagship_refuses_readme_without_generation_markers(
    config: BlackstartConfig, tmp_path: Path
) -> None:
    """A release must not silently append a second result source to README."""
    readme = tmp_path / "README.md"
    readme.write_text("no generated result markers\n", encoding="utf-8")
    with pytest.raises(ValueError, match="marker pair"):
        run_flagship(
            config,
            evidence_root=tmp_path / "evidence",
            output_directory=tmp_path / "release",
            readme_path=readme,
        )
