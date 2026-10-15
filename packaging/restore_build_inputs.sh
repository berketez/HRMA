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
    echo "EKSİK: ne symlink ne dizin: $rel"
  fi
done

# ---------------------------------------------------------------------------
# Paketleme öncesi son kontrol — FAIL-CLOSED (ÖH D18 / altyapi, P10B3-17)
# ---------------------------------------------------------------------------
# ÖLÇÜLDÜ (once_p10b3_17.json): girdilerin İKİSİ DE yokken bu betik iki
# "UYARI" satırı basıp "Derleme girdileri hazır. Paketleme yapılabilir."
# diyerek 0 ile çıkıyordu. Son kontrol yalnız SYMLINK arıyordu; YOKLUĞU
# aramıyordu. Betik .github/workflows/release.yml:494'te KAPI ADIMI olarak
# koşuyor, yani yayın hattı girdisiz bir ağaçta "hazır" hükmünü alıp
# paketlemeye geçiyordu — .app/.exe içi boş çıkar, kullanıcıda patlar.
#
# Kapının hükmü artık üç şarta birden bağlı: symlink DEĞİL + gerçek dizin +
# BOŞ DEĞİL. Boşluk da sayılır, çünkü boş bir payload dizini eksik payload
# ile aynı sonucu verir ama "dizin var" diye sessizce geçerdi.
eksikler=()
for pair in "${PAIRS[@]}"; do
  rel="${pair%%:*}"; name="${pair##*:}"
  src="$REPO/$rel"
  if [ -L "$src" ]; then
    eksikler+=("$rel — hâlâ symlink (gerçek dizin bekleniyor)")
  elif [ ! -d "$src" ]; then
    eksikler+=("$rel — dizin YOK (önbellek: $CACHE/$name)")
  elif [ -z "$(ls -A "$src" 2>/dev/null)" ]; then
    eksikler+=("$rel — dizin BOŞ (içerik yok)")
  fi
done

if [ ${#eksikler[@]} -ne 0 ]; then
  echo
  echo "HATA: derleme girdileri hazır DEĞİL — PAKETLEME YAPMA."
  for e in "${eksikler[@]}"; do
    echo "  - $e"
  done
  echo
  echo "Girdiler depoda tutulmaz; önbellekten geri konur ya da yeniden"
  echo "üretilir:"
  echo "  packaging/win/payload -> packaging/build_win_payload.sh"
  echo "  packaging/mac/libs    -> packaging/build_mac_app.sh (denge"
  echo "                           termokimyası kütüphaneleri)"
  echo "Önbellek dizini: $CACHE"
  exit 1
fi

echo "Derleme girdileri hazır ($restored geri kondu). Paketleme yapılabilir."
