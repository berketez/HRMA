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

# Sürüm notu kaynağı (öncelik sırasıyla):
#   1. packaging/release_notes_v<sürüm>.md   — tercih edilen
#   2. komut satırı argümanı
#   3. düz "HRMA v<sürüm>"
#
# v2.6.25: notlar artık DOSYADAN okunuyor. Sebep iki katlı — (a) 8 KB'lık iki
# dilli markdown'ı kabuk argümanı olarak geçirmek tırnak/kaçış açısından
# kırılgandı, (b) güncelleme penceresinin dil ayıklaması gövdedeki
# <!--HRMA-LANG:xx--> imlerine dayanıyor ve o imler dosyada duruyor. Elle
# yazılan kısa bir not gönderilirse Türkçe arayüz İngilizce not görür.
NOT_DOSYASI="$SRC/packaging/release_notes_v${VERSION}.md"
if [ -f "$NOT_DOSYASI" ]; then
    NOT_ARGS=(--notes-file "$NOT_DOSYASI")
    echo "Sürüm notu: $NOT_DOSYASI"
    for dil in en tr; do
        grep -q "<!--HRMA-LANG:${dil}-->" "$NOT_DOSYASI" || {
            echo "HATA: sürüm notunda '${dil}' dil imi yok."
            echo "      Güncelleme penceresi tek dil gösterir; imleri ekleyin."
            exit 1
        }
    done
else
    NOT_ARGS=(--notes "${1:-HRMA v${VERSION}}")
    echo "UYARI: $NOT_DOSYASI yok, düz metin notla yayınlanıyor."
fi

# ---------------------------------------------------------------------------
# YAYIN KAPISI — v2.6.2 fiyaskosundan sonra eklendi (2026-07-27).
#
# v2.6.2, CI kırmızı bittikten 14 dakika sonra yayınlandı ve kullanıcının
# makinesinde uygulama hiçbir hesap yapmadı. O gün eksik olan şey dikkat
# değil, MEKANİK BİR KAPIYDI: yayın betiği hiçbir şey doğrulamadan
# gh release create çağırıyordu.
#
# Kapı artık burada ve atlanması BİLİNÇLİ bir eylem gerektirir:
#   KAPIYI_ATLA=1 bash packaging/publish_release.sh "..."
# Bunu yazan kişi neyi atladığını bilerek yazar.
# ---------------------------------------------------------------------------
if [ "${KAPIYI_ATLA:-0}" = "1" ]; then
    echo "UYARI: yayın kapısı KAPIYI_ATLA=1 ile atlandı. Sorumluluk sende."
else
    echo "Yayın kapısı çalışıyor (atlamak için KAPIYI_ATLA=1)..."
    if ! bash "$SRC/packaging/release_gate.sh"; then
        echo
        echo "HATA: yayın kapısı kapalı — sürüm YAYINLANMADI."
        echo "Yukarıdaki KALDI satırlarını düzelt, sonra tekrar çalıştır."
        exit 1
    fi
fi

echo "Yayınlanacak: v${VERSION}"
ls -lh "$DMG" "$EXE"

gh release create "v${VERSION}" "$DMG" "$EXE" \
    --repo berketez/HRMA \
    --title "HRMA v${VERSION}" \
    "${NOT_ARGS[@]}"

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
