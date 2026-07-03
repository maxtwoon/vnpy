#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Static verification =="
python scripts/verify_static_claims.py | tee expected_outputs/static_report.json
STATIC_RC=${PIPESTATUS[0]}

echo

echo "== Runtime verification with czsc, if installed =="
python scripts/verify_runtime_with_czsc.py | tee expected_outputs/runtime_attempt.log
RUNTIME_RC=${PIPESTATUS[0]}
if [ "$RUNTIME_RC" -ne 0 ]; then
  echo "Runtime verification did not complete. If this is due to missing czsc, run:" | tee -a expected_outputs/runtime_attempt.log
  echo "  python scripts/verify_runtime_with_czsc.py --install" | tee -a expected_outputs/runtime_attempt.log
fi

echo

echo "== PyPI version verification, if network is available =="
python scripts/verify_pypi_versions.py | tee expected_outputs/pypi_report.json || true

echo
if [ "$STATIC_RC" -ne 0 ]; then
  echo "Static verification failed with rc=$STATIC_RC"
  exit "$STATIC_RC"
fi

echo "Done. Read expected_outputs/*.json and records/audit_claims_to_verify.md for final reporting."
