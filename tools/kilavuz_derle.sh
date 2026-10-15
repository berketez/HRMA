#!/usr/bin/env bash
# kilavuz_derle.sh — kullanım kılavuzlarını TEK KAYNAKTAN (docs/user_guide/*.tex) üretir ve
# uygulamanın açtığı ikizleri (hrma/static/docs/) aynı baytlarla yeniler (ÖH kılavuz dalgası, OH-D31-03 / OH-D21-07).
#   tools/kilavuz_derle.sh            # TR + EN derle, ikizleri kopyala, md5 eşitliğini doğrula
#   tools/kilavuz_derle.sh --kontrol  # derlemeden yalnız ikizlerin eşit olup olmadığını raporla (yayın kapısı)
# Gereksinim: xelatex (MacTeX/TeX Live). CI'da koşmaz (xelatex yok); yerel yayın kapısı adımıdır.
set -euo pipefail
KOK="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"; cd "$KOK"
KAYNAK=docs/user_guide; IKIZ=hrma/static/docs
DOSYALAR=(HRMA-Kullanma-Kilavuzu-TR HRMA-User-Guide-EN)
kontrol() {
  rc=0
  for d in "${DOSYALAR[@]}"; do
    a="$KAYNAK/$d.pdf"; b="$IKIZ/$d.pdf"
    if [ ! -f "$a" ] || [ ! -f "$b" ]; then echo "EKSİK: $a ya da $b"; rc=1; continue; fi
    ma=$(md5 -q "$a"); mb=$(md5 -q "$b")
    if [ "$ma" = "$mb" ]; then echo "EŞİT  $d.pdf ($(stat -f %z "$a") B, md5 $ma)"; else echo "FARKLI $d.pdf: kaynak $ma / ikiz $mb"; rc=1; fi
  done
  return $rc
}
if [ "${1:-}" = "--kontrol" ]; then kontrol; exit $?; fi
command -v xelatex >/dev/null || { echo "xelatex yok"; exit 2; }
CIKTI="$(mktemp -d -t kilavuz-derle)"
for d in "${DOSYALAR[@]}"; do
  echo "== $d"
  # iki geçiş: içindekiler + çapraz başvurular
  for gecis in 1 2; do
    (cd "$KAYNAK" && xelatex -interaction=nonstopmode -halt-on-error -output-directory="$CIKTI" "$d.tex" > "$CIKTI/$d.$gecis.log" 2>&1) \
      || { echo "DERLEME HATASI ($d, geçiş $gecis): $(grep -m1 -E '^!' "$CIKTI/$d.$gecis.log" || true)"; tail -20 "$CIKTI/$d.$gecis.log"; exit 3; }
  done
  # sayfa sayısı (bilgi)
  n=$(grep -o 'Output written on .* ([0-9]* pages' "$CIKTI/$d.2.log" | grep -o '[0-9]* pages' || true)
  cp "$CIKTI/$d.pdf" "$KAYNAK/$d.pdf"; cp "$CIKTI/$d.pdf" "$IKIZ/$d.pdf"
  echo "   yazıldı: $KAYNAK/$d.pdf + $IKIZ/$d.pdf ($n)"
done
kontrol
echo "geçici dizin: $CIKTI (log'lar)"
