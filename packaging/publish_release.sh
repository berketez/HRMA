#!/bin/bash
# HRMA GitHub Release yayınlayıcı.
# Kullanım: bash packaging/publish_release.sh "Sürüm notları..."
# Uygulama içi güncelleme kontrolü (hrma/utils/update_checker.py) bu
# release'leri okur: tag v<sürüm>, asset'ler .dmg (mac) ve .exe (win).
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/hrma/__init__.py")"
[ -n "$VERSION" ] || { echo "HATA: sürüm okunamadı"; exit 1; }

DMG="$SRC/dist/HRMA-Setup-${VERSION}-macOS.dmg"
EXE="$SRC/dist/HRMA-Setup-${VERSION}.exe"
[ -f "$DMG" ] || { echo "HATA: $DMG yok — önce build_mac_app.sh + build_dmg.sh"; exit 1; }
[ -f "$EXE" ] || { echo "HATA: $EXE yok — önce build_win_payload.sh + makensis"; exit 1; }

NOTLAR="${1:-HRMA v${VERSION}}"

echo "Yayınlanacak: v${VERSION}"
ls -lh "$DMG" "$EXE"

gh release create "v${VERSION}" "$DMG" "$EXE" \
    --repo berketez/HRMA \
    --title "HRMA v${VERSION}" \
    --notes "$NOTLAR"

# README'deki doğrudan indirme linklerini yeni sürüme çevir (her yayında güncel kalsın)
# Python bloğu göreli 'README.md' yolunu kullanır — önce repo köküne geç.
cd "$SRC"
python3 - "$VERSION" <<'PY'
import re, sys
v = sys.argv[1]
p = 'README.md'
s = open(p, encoding='utf-8').read()
s = re.sub(r'/releases/download/v[\d.]+/', f'/releases/download/v{v}/', s)
s = re.sub(r'HRMA-Setup-[\d.]+-macOS\.dmg', f'HRMA-Setup-{v}-macOS.dmg', s)
s = re.sub(r'HRMA-Setup-[\d.]+\.exe', f'HRMA-Setup-{v}.exe', s)
open(p, 'w', encoding='utf-8').write(s)
print('README indirme linkleri v' + v + ' oldu — commit etmeyi unutma')
PY

echo "TAMAM: https://github.com/berketez/HRMA/releases/tag/v${VERSION}"
echo "Kurulu uygulamalar bir sonraki açılışta bu sürümü önerecek."
