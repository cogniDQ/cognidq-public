#!/usr/bin/env bash
# Seed deterministic connector test data into Postgres + MinIO.
#
# Usage:
#   ./scripts/seed-test-data.sh
#   ./scripts/seed-test-data.sh --only-generate
#   ./scripts/seed-test-data.sh --no-postgres
#   ./scripts/seed-test-data.sh --no-minio
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(dirname -- "$SCRIPT_DIR")"
PYTHON="${PYTHON:-python3}"

echo "→ $PYTHON $SCRIPT_DIR/seed_test_data.py $*"
exec "$PYTHON" "$SCRIPT_DIR/seed_test_data.py" "$@"
