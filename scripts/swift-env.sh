#!/bin/bash
# Deliberately use standalone Command Line Tools. Never use Xcode's toolchain.
set -euo pipefail
export DEVELOPER_DIR=/Library/Developer/CommandLineTools
export SDKROOT="$DEVELOPER_DIR/SDKs/MacOSX.sdk"
export CLANG_MODULE_CACHE_PATH="$PWD/.cache/clang"
export SWIFTPM_MODULECACHE_OVERRIDE="$PWD/.cache/swift"
export SWIFT_MODULECACHE_PATH="$PWD/.cache/swift"
export PATH="$DEVELOPER_DIR/usr/bin:$PATH"
mkdir -p "$CLANG_MODULE_CACHE_PATH" "$SWIFTPM_MODULECACHE_OVERRIDE"
if [ ! -x "$DEVELOPER_DIR/usr/bin/swift" ]; then
    echo 'Install standalone Apple Command Line Tools to build PAWilot.' >&2
    exit 1
fi

