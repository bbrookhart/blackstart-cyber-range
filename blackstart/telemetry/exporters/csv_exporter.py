"""Per-timestep process trace exporter.

``process.csv`` is the artefact a reviewer is most likely to open first, so it
carries both views of the process side by side. The ``true_*`` and ``reported_*``
column pairs make a telemetry-integrity effect visible by inspection: in SCN-003
the two level columns simply stop agreeing.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

__all__ = ["ProcessTraceRow", "ProcessTraceWriter"]

# Fixed precision keeps the file byte-stable across platforms without hiding
# meaningful process detail.
_DECIMALS = 6


@dataclass(frozen=True, slots=True)
class ProcessTraceRow:
    """One timestep of the process trace.

    Column names carry their units, and the ``true_``/``reported_`` prefixes make
    the ground-truth versus instrumented distinction explicit in the data itself.
    """

    t_s: float
    true_tank_level_m: float
    reported_tank_level_m: float
    independent_level_m: float
    true_source_level_m: float
    true_inflow_m3_s: float
    true_outflow_m3_s: float
    demand_m3_s: float
    service_shortfall_ratio: float
    spill_volume_m3: float
    pump_energised: int
    pump_permitted: int
    valve_position: float
    requested_setpoint_m: float
    effective_setpoint_m: float
    supervisory_available: int
    consequence_level: str
    violated_invariants: str

    @classmethod
    def field_names(cls) -> list[str]:
        """Ordered CSV column names."""
        return list(cls.__annotations__.keys())


class ProcessTraceWriter:
    """Accumulates process trace rows and writes them as CSV."""

    def __init__(self) -> None:
        """Create an empty trace."""
        self._rows: list[ProcessTraceRow] = []

    def __len__(self) -> int:
        """Number of recorded timesteps."""
        return len(self._rows)

    @property
    def rows(self) -> tuple[ProcessTraceRow, ...]:
        """All recorded rows, in simulation order."""
        return tuple(self._rows)

    def append(self, row: ProcessTraceRow) -> None:
        """Record one timestep."""
        self._rows.append(row)

    def write(self, path: Path) -> int:
        """Write the trace to ``path``.

        Returns:
            The number of data rows written.
        """
        return write_process_csv(self._rows, path)


def write_process_csv(rows: Iterable[ProcessTraceRow], path: Path) -> int:
    """Write process trace rows to a CSV file with stable float formatting."""
    written = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ProcessTraceRow.field_names())
        writer.writeheader()
        for row in rows:
            record = asdict(row)
            writer.writerow(
                {
                    key: (f"{value:.{_DECIMALS}f}" if isinstance(value, float) else value)
                    for key, value in record.items()
                }
            )
            written += 1
    return written
