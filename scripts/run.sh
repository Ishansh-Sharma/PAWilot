#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d build/PAWilot.app ]; then bash scripts/build-app.sh; fi
open build/PAWilot.app

