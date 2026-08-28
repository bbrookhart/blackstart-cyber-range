#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

command -v uv >/dev/null 2>&1 || {
  echo "ERROR: uv is required: https://docs.astral.sh/uv/" >&2
  exit 1
}

make bootstrap
make lint
make typecheck
make test
make test-properties
make coverage
make clean-results
make experiment
make evidence

for evidence_dir in evidence/local/EXP-SCN004-*; do
  test -d "$evidence_dir" || {
    echo "ERROR: flagship evidence was not produced" >&2
    exit 1
  }
  experiment_id="$(basename "$evidence_dir")"
  uv run blackstart evidence verify "$experiment_id" --evidence-root evidence/local
  uv run blackstart experiment verify-results "$experiment_id" --evidence-root evidence/local
done

test -f experiments/local/EXP-BS-001/comparison.json
test -f experiments/local/EXP-BS-001/report.md
test -f experiments/local/EXP-BS-001/figures/exp-bs-001-trajectory.svg

echo "BLACKSTART EXP-BS-001 reproduction: PASS"
