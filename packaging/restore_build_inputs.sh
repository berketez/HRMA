#!/usr/bin/env bash
# Derleme girdilerini yerine geri koyar (paketlemeden ÖNCE ZORUNLU).
#
# Neden var: 2026-07-19'da düzenleme hızını açmak için paketleme girdileri
# proje kökünden çıkarılıp ~/.hrma-build-cache/ altına taşındı ve yerlerine
# symlink bırakıldı. Sebep, PostToolUse tutarlılık hook'unun her .py
# düzenlemesinde proje kökünde grep -rn koşturması: payload + libs içindeki
# ~47 bin .py dosyası yüzünden tek bir düzenleme 20+ dakika bekliyordu
# (grep -r symlink'e inmediği için taşıma sorunu çözdü).
#
# ANCAK build_mac_app.sh "cp -R $B/mac/libs $RES/libs" kullanıyor ve BSD cp
# -R bir symlink'i KOPYALAMAZ, symlink olarak taşır. Symlink yerindeyken
# paketlenirse .app içindeki libs, derleyen makinedeki bir yola işaret eden
# KIRIK bağlantı olur; dmg kullanıcıda sessizce patlar. Bu yüzden paketleme
# öncesi gerçek dizinler yerine konur.
#
# Kullanım:
#   packaging/restore_build_inputs.sh          # gerçek dizinleri geri koy
#   packaging/restore_build_inputs.sh --defer  # tekrar symlink'e al (düzenleme hızı)

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE="$HOME/.hrma-build-cache"

declare -a PAIRS=(
  "packaging/win/payload:win-payload"
  "packaging/mac/libs:mac-libs"
)

if [ "${1:-}" = "--defer" ]; then
  mkdir -p "$CACHE"
  for pair in "${PAIRS[@]}"; do
    rel="${pair%%:*}"; name="${pair##*:}"
    src="$REPO/$rel"; dst="$CACHE/$name"
    if [ -L "$src" ]; then
      echo "zaten symlink: $rel"
    elif [ -d "$src" ]; then
      [ -e "$dst" ] && { echo "HATA: $dst zaten var, elle karar ver"; exit 1; }
      mv "$src" "$dst"
      ln -s "$dst" "$src"
      echo "taşındı + symlink: $rel -> $dst"
    else
      echo "yok, atlandı: $rel"
    fi
  done
  exit 0
fi

restored=0
for pair in "${PAIRS[@]}"; do
  rel="${pair%%:*}"; name="${pair##*:}"
  src="$REPO/$rel"; dst="$CACHE/$name"
  if [ -L "$src" ]; then
    [ -d "$dst" ] || { echo "HATA: symlink var ama hedef yok: $dst"; exit 1; }
    rm "$src"
    mv "$dst" "$src"
    echo "geri kondu: $rel"
    restored=$((restored + 1))
  elif [ -d "$src" ]; then
    echo "zaten gerçek dizin: $rel"
  else
    echo "UYARI: ne symlink ne dizin: $rel (paketleme başarısız olabilir)"
  fi
done

# Paketleme öncesi son kontrol: hiçbir derleme girdisi symlink kalmamalı.
for pair in "${PAIRS[@]}"; do
  rel="${pair%%:*}"
  if [ -L "$REPO/$rel" ]; then
    echo "HATA: $rel hâlâ symlink — paketleme YAPMA"; exit 1
  fi
done

echo "Derleme girdileri hazır ($restored geri kondu). Paketleme yapılabilir."
