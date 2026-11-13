#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/swift-env.sh
"$DEVELOPER_DIR/usr/bin/swift" build -c release --disable-sandbox --cache-path "$PWD/.cache/swiftpm"
APP="$PWD/build/PAWilot.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/backend"
cp .build/release/PAWilot "$APP/Contents/MacOS/PAWilot"
rsync -a --delete --exclude __pycache__ backend/pawilot "$APP/Contents/Resources/backend/"
rsync -a --delete assets/kitten "$APP/Contents/Resources/"
.venv/bin/python - "$PWD" "$APP" <<'PY'
import json, pathlib, plistlib, sys
root, app = map(pathlib.Path, sys.argv[1:])
(app / 'Contents/Resources/runtime.json').write_text(json.dumps({'python': str(root / '.venv/bin/python')}))
with (app / 'Contents/Info.plist').open('wb') as f:
    plistlib.dump({
        'CFBundleIdentifier': 'app.pawilot.desktop', 'CFBundleName': 'PAWilot',
        'CFBundleDisplayName': 'PAWilot', 'CFBundleExecutable': 'PAWilot',
        'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': '0.1.0',
        'CFBundleVersion': '1', 'LSMinimumSystemVersion': '14.0',
        'LSUIElement': True, 'NSHighResolutionCapable': True,
        'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True}
    }, f)
PY
/usr/bin/codesign --force --deep --sign - "$APP"
echo "Built $APP using standalone Swift."

