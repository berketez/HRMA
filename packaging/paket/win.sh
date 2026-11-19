#!/bin/bash
# packaging/paket/win.sh — Windows paketi (macOS üstünde): payload + NSIS kurucusu.
#
# Kaynak: 3.0.6 yayın günü betiği (ana model, ~/HRMA-calisma/2026-11-10/_ana_model/
# paket/win.sh); 16 Kas 2026'da depoya alındı (3.0.7 SÜREÇ kalem 2).
#
# Kullanım (paket worktree'sinde, aday dalında):
#   bash packaging/paket/win.sh
#   PAKET_GUNLUK=<dizin> MAKENSIS=<yol> bash packaging/paket/win.sh
# Sürüm hrma/__init__.py'den okunur (tek kaynak); makensis'e -DVERSION ile geçer.
# Durum satırları <günlük>/win_durum.txt; son satır WIN_TAMAM ya da <ADIM>_KALDI.
set -o pipefail
W="$(cd "$(dirname "$0")/../.." && pwd)" || exit 9
cd "$W" || exit 9
. "$W/packaging/paket/ortak.sh"
P="${PAKET_GUNLUK:-$W/dist/paket_gunluk}"
mkdir -p "$P" || exit 9
V="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' hrma/__init__.py)"
[ -n "$V" ] || { echo "sürüm okunamadı (hrma/__init__.py)"; exit 9; }
NSIS="${MAKENSIS:-$(command -v makensis || echo /opt/homebrew/bin/makensis)}"
paket_agaci_denetle > "$P/win_durum.txt" 2>&1 || { cat "$P/win_durum.txt"; echo "ON_DENETIM_KALDI" >> "$P/win_durum.txt"; exit 8; }
date '+%H:%M:%S basla' >> "$P/win_durum.txt"
bash packaging/build_win_payload.sh > "$P/win_payload.log" 2>&1 || { echo "PAYLOAD_KALDI $?" >> "$P/win_durum.txt"; exit 1; }
date '+%H:%M:%S payload bitti' >> "$P/win_durum.txt"
"$NSIS" -DVERSION="$V" -DOUTDIR="$W/dist" packaging/hrma.nsi > "$P/win_nsis.log" 2>&1 || { echo "NSIS_KALDI $?" >> "$P/win_durum.txt"; exit 1; }
date '+%H:%M:%S exe bitti' >> "$P/win_durum.txt"
echo WIN_TAMAM >> "$P/win_durum.txt"
