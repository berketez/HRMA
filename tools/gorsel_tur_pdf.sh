#!/usr/bin/env bash
# gorsel_tur_pdf.sh — görsel kabul turu girdi dokümanını (markdown) PDF'e çevirir.
# Berke tur sırasında PDF okuyor; kaynak markdown'da değişiklik olduğunda bu
# betik yeniden koşturulur. Tek kaynak markdown'dır, PDF ondan TÜRETİLİR.
#
# Yazı tipi notu (ölçüldü 16 Eyl 2026): Helvetica Neue ve STIX Two Text
# → (U+2192) ve ⟷ (U+27F7) karakterlerini TAŞIMIYOR; xelatex bunları sessizce
# ATLAR, yani "ekran ⟷ PDF" başlığı PDF'te "ekran  PDF" diye çıkar. Bu yüzden
# bu dört karakter newunicodechar ile matematik moduna eşlenir.
set -euo pipefail
KOK="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"; cd "$KOK"
KAYNAK=docs/scofield/raw/OH/GORSEL-TUR/gorsel_tur_girdi.md
HEDEF=docs/scofield/raw/OH/GORSEL-TUR/gorsel_tur_girdi.pdf
BASLIK="$(mktemp -t gorsel-tur-baslik).tex"
cat > "$BASLIK" <<'TEX'
\usepackage{newunicodechar}
\newunicodechar{→}{\ensuremath{\rightarrow}}
\newunicodechar{⟷}{\ensuremath{\longleftrightarrow}}
\newunicodechar{η}{\ensuremath{\eta}}
\newunicodechar{φ}{\ensuremath{\varphi}}
TEX
pandoc "$KAYNAK" -o "$HEDEF" --pdf-engine=xelatex \
  -V mainfont="Helvetica Neue" -V monofont="Menlo" -V monofontoptions="Scale=0.85" \
  -V geometry:margin=2.2cm -V lang=tr -V colorlinks=true -V linkcolor=NavyBlue \
  -H "$BASLIK" --toc --toc-depth=2
rm -f "$BASLIK"
echo "yazıldı: $HEDEF ($(stat -f %z "$HEDEF") B)"
