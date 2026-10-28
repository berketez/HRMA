#!/bin/bash
# HRMA DMG kurucu
set -euo pipefail
B="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$B/.." && pwd)"   # depo kökü — betiğin konumundan türetilir
# 2026-08-03: burada sabit "/Users/apple/Desktop/dosyalar/HRMA" yazıyordu.
# Depo /Users/apple/HRMA'ya taşınmıştı; eski yolda yalnız paketleme
# artıkları kalmıştı ve içinde hrma/ ile data/ YOKTU. Yani paketleme
# çalıştırılsaydı boş bir ağaçtan kopyalayacaktı.
# build.noindex: Spotlight bu ağacı indekslemesin (sahte "HRMA" kopyaları)
STAGE="$B/mac/build.noindex/dmg_stage"
DIST="$SRC/dist"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/hrma/__init__.py")"
[ -n "$VERSION" ] || { echo "HATA: sürüm okunamadı"; exit 1; }

rm -rf "$STAGE"
mkdir -p "$STAGE" "$DIST"
cp -R "$B/mac/build.noindex/HRMA.app" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp "$B/README_MAC.txt" "$STAGE/README.txt"

# ULMO = LZMA sıkıştırma (macOS 10.15+ açar; UDZO/zlib 651 MB veriyordu — 2026-07-14)
#
# 2026-10-28 (v3.0.5): `hdiutil create -srcfolder -format ULMO` bu macOS'ta imajı
# kötü sıkıştırıyor. ÖLÇÜLDÜ: aynı içerikle 3.0.5 DMG'si 732,6 MB çıktı; o
# imaj `hdiutil convert -format ULMO` ile 344,3 MB oldu ve iki imajda dosya
# listesi ile bütün dosya boyutları birebir aynı (62 595 dosya, 1347,7 MB).
# 3.0.0 DMG'si de aynı yolla 607,8 → 357,4 MB. Bu yüzden imaj önce geçici
# olarak üretilir, sonra aynı biçime dönüştürülür; içerik bit düzeyinde aynı
# kalır (dönüştürme kayıpsız, blok düzeyinde).
HAM_DMG="$B/mac/build.noindex/HRMA-Setup-${VERSION}-ham.dmg"
rm -f "$HAM_DMG"
hdiutil create -volname "HRMA Setup" -srcfolder "$STAGE" -ov -format ULMO \
    "$HAM_DMG"
hdiutil convert "$HAM_DMG" -format ULMO -ov \
    -o "$DIST/HRMA-Setup-${VERSION}-macOS.dmg"
rm -f "$HAM_DMG"
ls -lh "$DIST"
