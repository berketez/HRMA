#!/bin/bash
# packaging/paket/mac.sh — macOS paketi: .app derleme + duman testi + DMG.
#
# Kaynak: 3.0.6 yayın günü betiği (ana model, ~/HRMA-calisma/2026-11-10/_ana_model/
# paket/mac.sh); 16 Kas 2026'da depoya alındı (3.0.7 SÜREÇ kalem 2). Sabit yollar
# kalktı: ağaç = bu betiğin bulunduğu depo, günlükler PAKET_GUNLUK dizinine.
#
# Kullanım (paket worktree'sinde, aday dalında):
#   bash packaging/paket/mac.sh            # ön denetim + build + duman + DMG
#   PAKET_GUNLUK=<dizin> bash packaging/paket/mac.sh
# Durum satırları <günlük>/mac_durum.txt'e yazılır; son satır MAC_TAMAM ya da
# <ADIM>_KALDI <çıkış kodu>. Windows paketi aynı anda koşabilir (packaging/paket/win.sh).
set -o pipefail
W="$(cd "$(dirname "$0")/../.." && pwd)" || exit 9
cd "$W" || exit 9
. "$W/packaging/paket/ortak.sh"
P="${PAKET_GUNLUK:-$W/dist/paket_gunluk}"
mkdir -p "$P" || exit 9
paket_agaci_denetle > "$P/mac_durum.txt" 2>&1 || { cat "$P/mac_durum.txt"; echo "ON_DENETIM_KALDI" >> "$P/mac_durum.txt"; exit 8; }
date '+%H:%M:%S basla' >> "$P/mac_durum.txt"
bash packaging/build_mac_app.sh > "$P/mac_build.log" 2>&1 || { echo "BUILD_KALDI $?" >> "$P/mac_durum.txt"; exit 1; }
date '+%H:%M:%S build bitti' >> "$P/mac_durum.txt"
bash packaging/test_bundle_mac.sh > "$P/mac_test.log" 2>&1 || { echo "TEST_KALDI $?" >> "$P/mac_durum.txt"; exit 1; }
date '+%H:%M:%S duman gecti' >> "$P/mac_durum.txt"
bash packaging/build_dmg.sh > "$P/mac_dmg.log" 2>&1 || { echo "DMG_KALDI $?" >> "$P/mac_durum.txt"; exit 1; }
date '+%H:%M:%S dmg bitti' >> "$P/mac_durum.txt"
echo MAC_TAMAM >> "$P/mac_durum.txt"
