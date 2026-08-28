"""Publication-quality figures generated only from experiment evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt

__all__ = ["render_consequence_path", "render_flagship_figures"]

_OFF_COLOR = "#B33A3A"
_ON_COLOR = "#177E6A"
_REQUEST_COLOR = "#C47B25"
_SAFE_COLOR = "#6B7280"


def _read_trace(directory: Path) -> dict[str, list[Any]]:
    """Read the columns needed by all three figures."""
    with (directory / "process.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{directory / 'process.csv'} is empty")
    return {
        "time": [float(row["t_s"]) for row in rows],
        "level": [float(row["true_tank_level_m"]) for row in rows],
        "requested": [float(row["requested_setpoint_m"]) for row in rows],
        "effective": [float(row["effective_setpoint_m"]) for row in rows],
    }


def _load_context(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    configuration = json.loads((directory / "configuration.json").read_text(encoding="utf-8"))
    scenario = json.loads((directory / "scenario.json").read_text(encoding="utf-8"))
    return configuration, scenario


def _style() -> None:
    """Apply deterministic, restrained research-figure styling."""
    plt.rcParams.update(
        {
            "svg.hashsalt": "blackstart-exp-bs-001",
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": "#D9DEE5",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.75,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def _save(fig: Any, path: Path) -> None:
    """Save an SVG without a wall-clock metadata field."""
    fig.savefig(
        path,
        format="svg",
        bbox_inches="tight",
        metadata={"Date": None, "Creator": "BLACKSTART v0.1 evidence renderer"},
    )
    plt.close(fig)
    # Matplotlib emits insignificant spaces at line ends in SVG path data.
    # Normalize them so generated figures pass repository whitespace checks and
    # remain byte-stable across copies into the release and reviewer packages.
    text = path.read_text(encoding="utf-8")
    path.write_text(
        "\n".join(line.rstrip() for line in text.splitlines()) + "\n",
        encoding="utf-8",
    )


def render_flagship_figures(
    unprotected_directory: Path,
    protected_directory: Path,
    output_directory: Path,
) -> dict[str, Path]:
    """Render the three EXP-BS-001 figures from serialized evidence."""
    _style()
    output_directory.mkdir(parents=True, exist_ok=True)
    off = _read_trace(unprotected_directory)
    on = _read_trace(protected_directory)
    configuration, scenario_doc = _load_context(unprotected_directory)
    config = configuration["config"]
    scenario = scenario_doc["scenario"]
    upper = next(
        item["limit_m"] for item in config["invariants"]["invariants"] if item["id"] == "INV-001"
    )
    lower = next(
        item["limit_m"] for item in config["invariants"]["invariants"] if item["id"] == "INV-002"
    )
    normal = config["consequences"]["normal_band"]
    capacity = config["process"]["tank"]["overflow_height_m"]
    allowed_max = config["architecture"]["backstop"]["rules"][0]["setpoint_max_m"]
    attack_time = scenario["events"][0]["t_s"]
    duration = scenario["duration_s"]

    trajectory_path = output_directory / "exp-bs-001-trajectory.svg"
    fig, ax = plt.subplots(figsize=(10.8, 5.4))
    ax.plot(off["time"], off["level"], color=_OFF_COLOR, linewidth=2, label="Backstop OFF")
    ax.plot(on["time"], on["level"], color=_ON_COLOR, linewidth=2, label="Backstop ON")
    ax.axhspan(
        normal["lower_m"], normal["upper_m"], color=_ON_COLOR, alpha=0.08, label="Normal range"
    )
    ax.axhline(
        upper,
        color=_SAFE_COLOR,
        linestyle="--",
        linewidth=1.3,
        label=f"Maximum safe level ({upper:.2f} m)",
    )
    ax.axhline(
        lower,
        color=_SAFE_COLOR,
        linestyle=":",
        linewidth=1.3,
        label=f"Minimum reserve ({lower:.2f} m)",
    )
    ax.axvline(
        attack_time,
        color=_REQUEST_COLOR,
        linestyle="--",
        linewidth=1.3,
        label=f"Mutation at {attack_time:.0f} s",
    )
    ax.set(
        xlim=(0, duration),
        ylim=(0, capacity + 0.15),
        xlabel="Simulated time (s)",
        ylabel="True tank level (m)",
    )
    ax.set_title("EXP-BS-001 physical trajectory")
    ax.text(
        0.995,
        0.015,
        "Synthetic process data",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color="#6B7280",
        fontsize=8,
    )
    ax.legend(loc="upper left", ncols=2, frameon=False)
    _save(fig, trajectory_path)

    control_path = output_directory / "exp-bs-001-control.svg"
    fig, ax = plt.subplots(figsize=(10.8, 4.8))
    ax.plot(
        on["time"], on["requested"], color=_REQUEST_COLOR, linewidth=2, label="Requested setpoint"
    )
    ax.plot(on["time"], on["effective"], color=_ON_COLOR, linewidth=2, label="Effective setpoint")
    ax.axhline(
        allowed_max,
        color=_SAFE_COLOR,
        linestyle="--",
        linewidth=1.3,
        label=f"Engineering maximum ({allowed_max:.2f} m)",
    )
    ax.axvline(
        attack_time,
        color=_REQUEST_COLOR,
        linestyle=":",
        linewidth=1.2,
        label=f"Mutation at {attack_time:.0f} s",
    )
    ax.set(
        xlim=(0, duration),
        ylim=(0, capacity + 0.15),
        xlabel="Simulated time (s)",
        ylabel="Setpoint (m)",
    )
    ax.set_title("Protected condition: requested versus effective control")
    ax.text(
        0.995,
        0.015,
        "Synthetic process data",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color="#6B7280",
        fontsize=8,
    )
    ax.legend(loc="upper left", frameon=False)
    _save(fig, control_path)

    margin_path = output_directory / "exp-bs-001-safety-margin.svg"
    off_margin = [min(level - lower, upper - level) for level in off["level"]]
    on_margin = [min(level - lower, upper - level) for level in on["level"]]
    fig, ax = plt.subplots(figsize=(10.8, 4.8))
    ax.plot(off["time"], off_margin, color=_OFF_COLOR, linewidth=2, label="Backstop OFF")
    ax.plot(on["time"], on_margin, color=_ON_COLOR, linewidth=2, label="Backstop ON")
    ax.axhline(0, color=_SAFE_COLOR, linestyle="--", linewidth=1.3, label="Safety boundary")
    ax.axvline(
        attack_time,
        color=_REQUEST_COLOR,
        linestyle=":",
        linewidth=1.2,
        label=f"Mutation at {attack_time:.0f} s",
    )
    ax.set(
        xlim=(0, duration),
        xlabel="Simulated time (s)",
        ylabel="Distance to nearest safety boundary (m)",
    )
    ax.set_title("EXP-BS-001 safety margin")
    ax.text(
        0.995,
        0.015,
        "Negative values are outside the safe envelope · synthetic data",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        color="#6B7280",
        fontsize=8,
    )
    ax.legend(loc="upper right", frameon=False)
    _save(fig, margin_path)

    return {
        "trajectory": trajectory_path,
        "control": control_path,
        "safety_margin": margin_path,
    }


def render_consequence_path(graph: dict[str, Any], output_path: Path) -> Path:
    """Render the SCN-004 causal trace from ``graph.json`` as a compact SVG."""
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    path = graph["unprotected_path"]
    width, height = 980, 620
    box_x, box_width, box_height = 160, 660, 48
    top, gap = 38, 72
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
        "<title>SCN-004 consequence path</title>",
        "<desc>Scenario event through control mutation, actuator, physical process, safety invariant, and C4 consequence.</desc>",
        "<style>text{font-family:DejaVu Sans,Arial,sans-serif}.id{font:700 13px monospace}.label{font-size:13px}.edge{stroke:#516070;stroke-width:2;fill:none}.node{fill:#F7F9FB;stroke:#AAB5C0;stroke-width:1.3}.stop{fill:#E7F4EF;stroke:#177E6A;stroke-width:1.5}</style>",
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>',
    ]
    for index, node_id in enumerate(path):
        y = top + index * gap
        css = "stop" if node_id in {"INV-001", "C4"} else "node"
        parts.append(
            f'<rect class="{css}" x="{box_x}" y="{y}" width="{box_width}" height="{box_height}" rx="5"/>'
        )
        parts.append(
            f'<text class="id" x="{box_x + 18}" y="{y + 21}" fill="#1B2430">{node_id}</text>'
        )
        parts.append(
            f'<text class="label" x="{box_x + 170}" y="{y + 21}" fill="#1B2430">{labels[node_id]}</text>'
        )
        if index < len(path) - 1:
            next_y = top + (index + 1) * gap
            parts.append(
                f'<path class="edge" d="M {width / 2:.0f} {y + box_height} V {next_y - 7}"/>'
            )
            parts.append(
                f'<path fill="#516070" d="M {width / 2 - 5:.0f} {next_y - 12} L {width / 2:.0f} {next_y - 4} L {width / 2 + 5:.0f} {next_y - 12} Z"/>'
            )
    interruption = graph["protected_interruption"]
    parts.append(
        f'<rect x="24" y="{top + 2 * gap}" width="118" height="120" rx="6" fill="#E7F4EF" stroke="#177E6A"/>'
    )
    parts.append(
        f'<text x="83" y="{top + 2 * gap + 26}" text-anchor="middle" class="id" fill="#177E6A">{interruption["control"]}</text>'
    )
    parts.append(
        f'<text x="83" y="{top + 2 * gap + 50}" text-anchor="middle" class="id" fill="#177E6A">{interruption["rule"]}</text>'
    )
    parts.append(
        f'<text x="83" y="{top + 2 * gap + 76}" text-anchor="middle" class="label" fill="#1B2430">CONSTRAINS</text>'
    )
    parts.append(
        f'<path d="M 142 {top + 2 * gap + 60} H {box_x - 8}" stroke="#177E6A" stroke-width="2" stroke-dasharray="5 4"/>'
    )
    parts.append("</svg>")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return output_path
