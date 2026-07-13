#!/bin/bash
# HRMA DMG kurucu
set -euo pipefail
B="$(cd "$(dirname "$0")" && pwd)"
SRC="/Users/apple/Desktop/dosyalar/HRMA"
STAGE="$B/mac/dmg_stage"
DIST="$SRC/dist"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/hrma/__init__.py")"
[ -n "$VERSION" ] || { echo "HATA: sürüm okunamadı"; exit 1; }

rm -rf "$STAGE"
mkdir -p "$STAGE" "$DIST"
cp -R "$B/mac/HRMA.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp "$B/README_MAC.txt" "$STAGE/README.txt"

# ULMO = LZMA sıkıştırma (macOS 10.15+ açar; UDZO/zlib 651 MB veriyordu — 2026-07-14)
hdiutil create -volname "HRMA Setup" -srcfolder "$STAGE" -ov -format ULMO \
    "$DIST/HRMA-Setup-${VERSION}-macOS.dmg"
ls -lh "$DIST"
