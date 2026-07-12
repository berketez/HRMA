#!/bin/bash
# HRMA DMG kurucu
set -euo pipefail
B="$(cd "$(dirname "$0")" && pwd)"
STAGE="$B/mac/dmg_stage"
DIST="/Users/apple/Desktop/dosyalar/HRMA/dist"

rm -rf "$STAGE"
mkdir -p "$STAGE" "$DIST"
cp -R "$B/mac/HRMA.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp "$B/OKU_BENI_MAC.txt" "$STAGE/OKU BENI.txt"

hdiutil create -volname "HRMA Kurulum" -srcfolder "$STAGE" -ov -format UDZO \
    "$DIST/HRMA-Kurulum-1.0.0-macOS.dmg"
ls -lh "$DIST"
