#!/usr/bin/env bash
# Doğrulama kaynak belgelerini indirir ve SHA-256 özetlerini doğrular.
#
# Belgeler depoya konmaz (telif + boyut; gerekçe MANIFEST.md'de). Bu betik
# kaynak zincirini yeniden üretilebilir kılar: aynı adresten indirir, özeti
# karşılaştırır, tutmazsa yüksek sesle şikayet eder.
#
# Kullanım:  bash data/validation/sources/fetch_sources.sh [hedef_dizin]
# Varsayılan hedef dizin: bu betiğin bulunduğu dizin.

set -uo pipefail

DEST="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
mkdir -p "$DEST"

# ad|sha256|url
DOCS=(
"pwa-fr-1769-rl10a33-design-1966.pdf|c7a2199ec4deadb30b2ff0960b7f576e2aaa227f47315efe85268da654576120|https://www.nasa.gov/wp-content/uploads/2025/06/design-report-for-rl-10-a-3-3-1966.pdf"
"nasa-tm-107318-rl10a33a-model.pdf|2d25422c6b9d4635f3209cfb79c160d160d229aeded17a3e12abe4330153a8c7|https://ntrs.nasa.gov/api/citations/19970010379/downloads/19970010379.pdf"
"ntrs-19710011726-bartz-comparison.pdf|62d165ed0710e515c56ed993eed3871deb5b96662d141d180b0cb93d697904df|https://ntrs.nasa.gov/api/citations/19710011726/downloads/19710011726.pdf"
"aiaa-2005-3940-stark-separation.pdf|58260ab8a9c6454e9aeecf6c34dafde21071e2b6e0f12efe53afe2be7a10687b|https://elib.dlr.de/49253/1/AIAA2005-3940.pdf"
"ntrs-19650010083-back-massier-gier.pdf|bf8d2961b2aecc53f08920e86a5b7dfc2d7efbde19d26599693fd48fffc6a198|https://ntrs.nasa.gov/api/citations/19650010083/downloads/19650010083.pdf"
"ntrs-19650026963-back-massier-gier.pdf|46c0b115a679554ea7a6a1805a8dd188bdce27e6e85e434be946bdcfffe266cb|https://ntrs.nasa.gov/api/citations/19650026963/downloads/19650026963.pdf"
"ntrs-19680024170-boldman-tnd4788.pdf|950ae9cf4ab2d03233873036503663f6f14b9b6187ee6bffd7544ee63ab10b36|https://ntrs.nasa.gov/api/citations/19680024170/downloads/19680024170.pdf"
"gpps-tc-2021-0105-wang-fluent-bmg.pdf|14b1c565dfabf5bb124ecd5042995ead53a39235093da5e04832cabd4328ce89|https://gpps.global/wp-content/uploads/2022/01/GPPS-TC-2021_paper_105.pdf"
"dsj-74-19633-makhija-openfoam-bmg.pdf|0f716f493d4463a03307cdbe2ff43f69353d13270cfb7d7bda0354ec47031125|https://publicationsdrdo.in/index.php/dsj/article/download/19633/8259/83707"
)

# Telifli, otomatik indirilmez — elle alınmalı (aşağıda uyarı basılır).
MANUAL=(
"Oefelein & Yang, JPP 9(5) 1993, doi:10.2514/3.23674 — AIAA telifli; kurumsal erişimle alınmalı"
)

sha_of() {
  if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'
  else sha256sum "$1" | awk '{print $1}'; fi
}

fail=0
for entry in "${DOCS[@]}"; do
  IFS='|' read -r name want url <<<"$entry"
  path="$DEST/$name"

  if [ -f "$path" ]; then
    got="$(sha_of "$path")"
    if [ "$got" = "$want" ]; then
      echo "ATLANDI (özet tutuyor): $name"
      continue
    fi
    echo "UYARI: $name mevcut ama özeti tutmuyor, yeniden indiriliyor"
  fi

  echo "indiriliyor: $name"
  if ! curl -sSL --max-time 300 -o "$path" "$url"; then
    echo "HATA: indirilemedi -> $url"
    fail=1
    continue
  fi

  got="$(sha_of "$path")"
  size="$(wc -c <"$path" | tr -d ' ')"
  if [ "$got" = "$want" ]; then
    echo "  TAMAM  $size bayt  sha256 doğrulandı"
  else
    echo "  ÖZET TUTMADI  $size bayt"
    echo "    beklenen: $want"
    echo "    gelen   : $got"
    echo "    -> belge yayıncı tarafından değiştirilmiş olabilir; ilgili"
    echo "       data/validation/*.json kaydının değerleri YENİDEN kontrol edilmeli."
    fail=1
  fi
done

echo
echo "Elle alınması gereken (otomatik indirilmez):"
for m in "${MANUAL[@]}"; do echo "  - $m"; done

exit "$fail"
