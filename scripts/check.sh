#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/swift-env.sh
.venv/bin/python -m pytest -q
"$DEVELOPER_DIR/usr/bin/swift" run --disable-sandbox --cache-path "$PWD/.cache/swiftpm" PawCoreChecks

