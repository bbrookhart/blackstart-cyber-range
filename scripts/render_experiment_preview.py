"""Render ``assets/experiment-preview.svg`` from the committed baseline evidence.

The chart is a plot of measured data, not a mockup. Regenerate it whenever the
baseline evidence changes:

    uv run python scripts/render_experiment_preview.py
"""

from __future__ import annotations

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "evidence" / "baseline"
OUTPUT = REPO_ROOT / "assets" / "experiment-preview.svg"

WIDTH, HEIGHT = 1200, 470
MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM = 92, 40, 74, 96
PLOT_W = WIDTH - MARGIN_LEFT - MARGIN_RIGHT
PLOT_H = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM

T_MAX = 1200.0
LEVEL_MIN, LEVEL_MAX = 2.4, 5.25

SAFE_LEVEL_M = 4.50
WEIR_M = 5.00
BAND_LOW_M, BAND_HIGH_M = 2.70, 3.70
#: Plot every Nth sample; 2400 points would bloat the file for no visible gain.
DECIMATION = 8


def load_trace(pattern: str) -> list[tuple[float, float]]:
    """Load (time, true level) pairs from a baseline experiment's process trace."""
    matches = sorted(BASELINE.glob(f"{pattern}/process.csv"))
    if not matches:
        msg = f"no baseline evidence matching {pattern!r}; run `make demo` first"
        raise FileNotFoundError(msg)
    with matches[0].open(encoding="utf-8") as handle:
        return [
            (float(row["t_s"]), float(row["true_tank_level_m"])) for row in csv.DictReader(handle)
        ]


def x_of(t_s: float) -> float:
    """Map simulation time to plot x."""
    return MARGIN_LEFT + (t_s / T_MAX) * PLOT_W


def y_of(level_m: float) -> float:
    """Map tank level to plot y."""
    span = LEVEL_MAX - LEVEL_MIN
    return MARGIN_TOP + PLOT_H - ((level_m - LEVEL_MIN) / span) * PLOT_H


def polyline(series: list[tuple[float, float]]) -> str:
    """Decimate a trace into an SVG points list, always keeping the last sample."""
    points = [
        f"{x_of(t):.1f},{y_of(level):.1f}"
        for index, (t, level) in enumerate(series)
        if index % DECIMATION == 0
    ]
    points.append(f"{x_of(series[-1][0]):.1f},{y_of(series[-1][1]):.1f}")
    return " ".join(points)


def _grid(levels: tuple[float, ...], times: tuple[int, ...]) -> str:
    """Render gridlines and axis tick labels."""
    parts = []
    for level in levels:
        y = y_of(level)
        parts.append(
            f'  <line class="grid" x1="{MARGIN_LEFT}" y1="{y:.1f}" '
            f'x2="{MARGIN_LEFT + PLOT_W}" y2="{y:.1f}"/>'
        )
        parts.append(
            f'  <text class="mut" x="{MARGIN_LEFT - 12}" y="{y + 4:.1f}" '
            f'font-size="11" text-anchor="end">{level:.1f}</text>'
        )
    for t in times:
        parts.append(
            f'  <text class="mut" x="{x_of(t):.1f}" '
            f'y="{MARGIN_TOP + PLOT_H + 22}" font-size="11" '
            f'text-anchor="middle">{t}</text>'
        )
    return "\n".join(parts)


def render(
    disabled: list[tuple[float, float]],
    enabled: list[tuple[float, float]],
    first_violation_s: float,
    peak_disabled: float,
    peak_enabled: float,
) -> str:
    """Build the complete SVG document."""
    band_top, band_bottom = y_of(BAND_HIGH_M), y_of(BAND_LOW_M)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" \
width="{WIDTH}" height="{HEIGHT}" role="img" aria-labelledby="t d">
  <title id="t">SCN-004 true tank level, with and without the engineering constraint</title>
  <desc id="d">Measured tank level over 1200 seconds from the committed baseline evidence.
  Without the constraint the level crosses the 4.50 m safe working level at
  {first_violation_s:.0f} s and reaches the {WEIR_M:.2f} m weir crest. With the constraint it
  peaks at {peak_enabled:.2f} m.</desc>
  <style>
    .bg{{fill:#FFFFFF}} .fg{{fill:#1B2430}} .mut{{fill:#5A6B7C}}
    .grid{{stroke:#E8EDF2}} .panel{{fill:#F7F9FB;stroke:#DDE4EA}}
    @media (prefers-color-scheme: dark) {{
      .bg{{fill:#0B1017}} .fg{{fill:#EAF1F7}} .mut{{fill:#8FA6BB}}
      .grid{{stroke:#1B2733}} .panel{{fill:#101922;stroke:#22303D}}
    }}
    text{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
  </style>

  <rect class="bg" width="{WIDTH}" height="{HEIGHT}"/>
  <rect class="panel" x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="4"/>

  <text class="fg" x="{MARGIN_LEFT}" y="34" font-size="16" font-weight="700"
        letter-spacing="2.4">SCN-004 — UNAUTHORISED SETPOINT MUTATION</text>
  <text class="mut" x="{MARGIN_LEFT}" y="55" font-size="12">True tank level, seed 4242 \
· measured, from evidence/baseline/</text>

{_grid((2.5, 3.0, 3.5, 4.0, 4.5, 5.0), (0, 200, 400, 600, 800, 1000, 1200))}

  <text class="mut" x="{MARGIN_LEFT - 58}" y="{MARGIN_TOP + PLOT_H / 2}" font-size="11"
        text-anchor="middle"
        transform="rotate(-90 {MARGIN_LEFT - 58} {MARGIN_TOP + PLOT_H / 2})">TANK LEVEL (m)</text>
  <text class="mut" x="{MARGIN_LEFT + PLOT_W / 2}" y="{MARGIN_TOP + PLOT_H + 44}"
        font-size="11" text-anchor="middle">SIMULATION TIME (s)</text>

  <line x1="{MARGIN_LEFT}" y1="{y_of(WEIR_M):.1f}" x2="{MARGIN_LEFT + PLOT_W}"
        y2="{y_of(WEIR_M):.1f}" stroke="#8A6D3B" stroke-width="1.2" stroke-dasharray="2 3"/>
  <text x="{MARGIN_LEFT + PLOT_W - 4}" y="{y_of(WEIR_M) - 7:.1f}" font-size="10.5"
        fill="#8A6D3B" text-anchor="end" letter-spacing="1.2">WEIR CREST {WEIR_M:.2f} m \
— CONTAINMENT LOST</text>

  <line x1="{MARGIN_LEFT}" y1="{y_of(SAFE_LEVEL_M):.1f}" x2="{MARGIN_LEFT + PLOT_W}"
        y2="{y_of(SAFE_LEVEL_M):.1f}" stroke="#C0392B" stroke-width="1.6" stroke-dasharray="7 4"/>
  <text x="{MARGIN_LEFT + PLOT_W - 4}" y="{y_of(SAFE_LEVEL_M) - 7:.1f}" font-size="10.5"
        fill="#C0392B" text-anchor="end" letter-spacing="1.2">INV-001 SAFE WORKING LEVEL \
{SAFE_LEVEL_M:.2f} m</text>

  <rect x="{MARGIN_LEFT}" y="{band_top:.1f}" width="{PLOT_W}"
        height="{band_bottom - band_top:.1f}" fill="#4E9C87" opacity="0.10"/>
  <text class="mut" x="{MARGIN_LEFT + 8}" y="{band_bottom - 8:.1f}" font-size="10">\
NORMAL BAND {BAND_LOW_M:.2f}\u2013{BAND_HIGH_M:.2f} m</text>

  <line x1="{x_of(180):.1f}" y1="{MARGIN_TOP}" x2="{x_of(180):.1f}"
        y2="{MARGIN_TOP + PLOT_H}" stroke="#C6873B" stroke-width="1.2" stroke-dasharray="3 3"/>
  <text x="{x_of(180) + 7:.1f}" y="{MARGIN_TOP + 16}" font-size="10.5" fill="#C6873B"
        letter-spacing="1.1">t=180 s  setpoint → 4.80 m</text>

  <polyline fill="none" stroke="#C0392B" stroke-width="2.4" points="{polyline(disabled)}"/>
  <polyline fill="none" stroke="#2E7D66" stroke-width="2.4" points="{polyline(enabled)}"/>

  <circle cx="{x_of(first_violation_s):.1f}" cy="{y_of(SAFE_LEVEL_M):.1f}" r="4.5" fill="#C0392B"/>
  <text x="{x_of(first_violation_s) + 9:.1f}" y="{y_of(SAFE_LEVEL_M) + 18:.1f}" font-size="10.5"
        fill="#C0392B">INV-001 violated  t={first_violation_s:.1f} s</text>

  <g transform="translate({MARGIN_LEFT},{HEIGHT - 44})" font-size="12">
    <line x1="0" y1="-4" x2="26" y2="-4" stroke="#C0392B" stroke-width="2.4"/>
    <text class="fg" x="34" y="0">backstop disabled</text>
    <text class="mut" x="176" y="0">peak {peak_disabled:.2f} m · 639.5 s unsafe · 3.38 m³ \
spilled · <tspan fill="#C0392B" font-weight="700">C4</tspan></text>
    <line x1="0" y1="18" x2="26" y2="18" stroke="#2E7D66" stroke-width="2.4"/>
    <text class="fg" x="34" y="22">backstop enabled</text>
    <text class="mut" x="176" y="22">peak {peak_enabled:.2f} m · 0.0 s unsafe · 0.00 m³ \
spilled · <tspan fill="#2E7D66" font-weight="700">C1</tspan></text>
  </g>
</svg>
"""


def main() -> int:
    """Render the SVG from measured evidence and report the figures it embeds."""
    disabled = load_trace("EXP-SCN004-backstop-disabled-*")
    enabled = load_trace("EXP-SCN004-backstop-enabled-*")

    first_violation_s = next(t for t, level in disabled if level > SAFE_LEVEL_M)
    peak_disabled = max(level for _, level in disabled)
    peak_enabled = max(level for _, level in enabled)

    OUTPUT.write_text(
        render(disabled, enabled, first_violation_s, peak_disabled, peak_enabled),
        encoding="utf-8",
    )

    print(f"first INV-001 violation : t = {first_violation_s:.1f} s")
    print(f"peak level, disabled    : {peak_disabled:.3f} m")
    print(f"peak level, enabled     : {peak_enabled:.3f} m")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
