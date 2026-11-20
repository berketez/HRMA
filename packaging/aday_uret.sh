#!/usr/bin/env bash
# aday_uret.sh — yayın ADAYI dalı üretir: aday/v<sürüm>-rc.<no>
#
# Kaynak: 3.0.6 yayın treninin aday üreticisi (ana model, 4 Kas eaabafc85 yöntemi;
# ~/HRMA-calisma/2026-11-09/_ana_model/aday_uret.sh). 16 Kas 2026'da depoya alındı
# (3.0.7 SÜREÇ kalem 2) ve çıkış kodu hatası onarıldı (kalem 3, aşağıda).
#
# Kullanım (deponun herhangi bir worktree'sinden):
#   packaging/aday_uret.sh <rc-no> [kaynak]               # yerel dal üretir; push ETMEZ
#   packaging/aday_uret.sh <rc-no> [kaynak] --push        # + git push -u origin <dal>
#   packaging/aday_uret.sh <rc-no> [kaynak] --push --ci   # + gh workflow run tests.yml --ref <dal>
#   kaynak verilmezse içinde bulunulan dal (ör. bakim/3.0.7) kullanılır.
#
# Ortam: TABAN (varsayılan origin/main — yayımlanan docs'suz hat), HARIC (dışlanan
#   iç doküman dizinleri; varsayılan packaging/yayin_dali_uret.sh ile AYNI küme,
#   bekçi tests/test_v307_surec.py), ADAY_FETCH=0 (origin main getirilmez),
#   GH_DEPO (varsayılan berketez/HRMA).
#
# Yöntem: ağaç = KAYNAK ağacı eksi HARIC dizinleri, TEK commit, ebeveyn = TABAN.
# packaging/yayin_dali_uret.sh bakım hattında koşmaz: bakim/X.Y.Z origin/main'in
# torunu değildir (docs'lu kaynak), o betiğin "taban kaynağın atası" denetimi durur.
#
# KALEM 3 (3.0.6'da ölçülen çıkış kodu hatası): eski betiğin son denetim satırı
#   fark=$(git diff ... | grep -v -E "^(docs/...)/" | wc -l)
# idi. Fark YOKKEN (doğru aday) grep hiçbir satır seçmez ve 1 döner; `set -o pipefail`
# altında boru 1, `set -e` betiği ÖLDÜRÜR. Dal üretilmiş oluyordu ama betik 1 ile
# çıkıyordu, `aday_uret.sh N && git push ... && gh workflow run ...` zincirinin
# geri kalanı hiç koşmuyordu. Onarım: sayım awk ile (eşleşme yokken de 0 döner) ve
# denetim dal ÜRETİLMEDEN ÖNCE yapılır; denetim tutmazsa dal üretilmez, çıkış 4.
set -euo pipefail

HARIC="${HARIC:-docs/scofield docs/arastirma docs/tasarim docs/kabul}"
GH_DEPO="${GH_DEPO:-berketez/HRMA}"

disarida_kalan_fark() {   # $1 $2 = iki commit/ağaç; HARIC DIŞINDA değişen dosya sayısını basar
    local desen
    desen="^($(printf '%s|' $HARIC | sed 's/|$//'))/"
    git -c core.quotePath=false diff --name-only "$1" "$2" \
        | awk -v d="$desen" '$0 !~ d { n++ } END { print n + 0 }'
}

haric_dosya_sayisi() {    # $1 = commit; HARIC altında kalan dosya sayısını basar
    local y toplam=0 n
    for y in $HARIC; do
        n="$(git ls-tree -r --name-only "$1" -- "$y" | awk 'END { print NR }')"
        toplam=$((toplam + n))
    done
    echo "$toplam"
}

# Kaynak olarak okunursa (bekçiler işlevleri çağırır) yalnız işlevler tanımlanır.
[ "${BASH_SOURCE[0]}" = "$0" ] || return 0

NO="${1:-}"; shift || true
case "$NO" in
    ''|*[!0-9]*) echo "kullanım: $0 <rc-no> [kaynak] [--push] [--ci]   (rc-no tam sayı)"; exit 64 ;;
esac
KAYNAK=""; PUSH=0; CI=0
for a in ${1+"$@"}; do
    case "$a" in
        --push) PUSH=1 ;;
        --ci) CI=1 ;;
        -*) echo "bilinmeyen seçenek: $a"; exit 64 ;;
        *) [ -z "$KAYNAK" ] || { echo "fazla argüman: $a"; exit 64; }; KAYNAK="$a" ;;
    esac
done
[ "$CI" = 0 ] || [ "$PUSH" = 1 ] || { echo "--ci yalnız --push ile: CI uzaktaki dalda koşar"; exit 64; }

KOK="$(git rev-parse --show-toplevel)"; cd "$KOK"
if [ -z "$KAYNAK" ]; then
    KAYNAK="$(git symbolic-ref -q --short HEAD || true)"
    [ -n "$KAYNAK" ] || { echo "HEAD ayrık ve kaynak verilmedi — kaynak dalı adıyla verin"; exit 64; }
fi
KSHA="$(git rev-parse --verify -q "${KAYNAK}^{commit}")" || { echo "kaynak bulunamadı: $KAYNAK"; exit 2; }
SURUM="$(git show "$KSHA:hrma/__init__.py" | sed -n 's/^__version__ = "\(.*\)"/\1/p')"
[ -n "$SURUM" ] || { echo "kaynakta sürüm okunamadı ($KAYNAK:hrma/__init__.py)"; exit 2; }
DAL="aday/v${SURUM}-rc.${NO}"
if git rev-parse --verify -q "refs/heads/$DAL" >/dev/null; then echo "dal zaten var: $DAL"; exit 2; fi

TABAN="${TABAN:-origin/main}"
if [ "${ADAY_FETCH:-1}" != 0 ] && [ "${TABAN#origin/}" != "$TABAN" ]; then
    git fetch -q origin "${TABAN#origin/}"
fi
TSHA="$(git rev-parse --verify -q "${TABAN}^{commit}")" || { echo "taban bulunamadı: $TABAN"; exit 2; }

IDX_DIZIN="$(mktemp -d "${TMPDIR:-/tmp}/hrma_aday_index.XXXXXX")"
trap 'rm -rf "$IDX_DIZIN"' EXIT
IDX="$IDX_DIZIN/index"
GIT_INDEX_FILE="$IDX" git read-tree "$KSHA"
for y in $HARIC; do GIT_INDEX_FILE="$IDX" git rm -r -q --cached --ignore-unmatch -- "$y"; done
AGAC="$(GIT_INDEX_FILE="$IDX" git write-tree)"
MSG="HRMA ${SURUM} aday rc.${NO} (docs iç dokümanları hariç: ${HARIC}) — kaynak ${KAYNAK}@$(git rev-parse --short "$KSHA")"
C="$(git commit-tree "$AGAC" -p "$TSHA" -m "$MSG")"

# Ağaç denetimi — dal ÜRETİLMEDEN önce. Tutmazsa dal yok, çıkış 4 (fail-closed).
KALAN_HARIC="$(haric_dosya_sayisi "$C")"
FARK="$(disarida_kalan_fark "$KSHA" "$C")"
echo "  dışlanan dizinlerde kalan: $KALAN_HARIC dosya (0 olmalı)"
echo "  kaynakla dışlanmayan fark: $FARK dosya (0 olmalı)"
if [ "$KALAN_HARIC" != 0 ] || [ "$FARK" != 0 ]; then
    echo "AĞAÇ DENETİMİ TUTMADI — dal üretilmedi ($DAL)"
    exit 4
fi
git branch "$DAL" "$C"
echo "aday: $DAL = $C (taban $TABAN $(git rev-parse --short "$TSHA"), kaynak $KAYNAK $(git rev-parse --short "$KSHA"))"

if [ "$PUSH" = 1 ]; then
    # -u: dalın üst akışı ayarlanır; paket worktree'si bu dala geçince kapı 2/10
    # (HEAD == @{u}) ayrıca ayar istemez.
    git push -u origin "$DAL"
    if [ "$CI" = 1 ]; then
        gh workflow run tests.yml --repo "$GH_DEPO" --ref "$DAL"
        echo "CI tetiklendi: tests.yml @ $DAL"
    fi
else
    echo "push: git push -u origin $DAL   |   CI: gh workflow run tests.yml --repo $GH_DEPO --ref $DAL"
fi
echo "paket ağacı: git -C <paket-worktree> switch $DAL   (ayrık HEAD DEĞİL; kapı 2/10 üst akış ister)"
