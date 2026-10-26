#!/usr/bin/env bash
# Runs every suite. QML tests need qmltestrunner (qt6-declarative) and are skipped without it.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== python: limit.py"
python3 -I -W ignore::ResourceWarning -m unittest discover -s tests -p "test_*.py"

echo "== node: Model.js, Strings.js, Contrast.js"
node --test tests/*.test.mjs

# The Qt 6 runner: qmltestrunner6 (Debian/Ubuntu) or qt6/bin (Arch, where plain qmltestrunner is Qt 5).
qml_runner=""
for c in qmltestrunner6 /usr/lib/qt6/bin/qmltestrunner /usr/lib64/qt6/bin/qmltestrunner; do
  if command -v "$c" >/dev/null; then qml_runner="$c"; break; fi
done
if [ -n "$qml_runner" ]; then
  echo "== qml: libraries in Qt's engine"
  QT_QPA_PLATFORM=offscreen "$qml_runner" -input tests/tst_model.qml
else
  echo "== qml: skipped (Qt 6 qmltestrunner not installed)"
fi

if command -v omarchy >/dev/null; then
  echo "== omarchy plugin validate"
  omarchy plugin validate .
fi
echo "all suites passed"
