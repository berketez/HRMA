#!/bin/bash
# HRMA GitHub Release yayınlayıcı.
# Kullanım: bash packaging/publish_release.sh "Sürüm notları..."
# Uygulama içi güncelleme kontrolü (hrma/utils/update_checker.py) bu
# release'leri okur: tag v<sürüm>, asset'ler .dmg (mac) ve .exe (win).
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/hrma/__init__.py")"
[ -n "$VERSION" ] || { echo "HATA: sürüm okunamadı"; exit 1; }
# Yayının yapıldığı depo — betikte TEK yerde (etiket ölçümü + sürüm açma).
GH_DEPO="berketez/HRMA"

DMG="$SRC/dist/HRMA-Setup-${VERSION}-macOS.dmg"
EXE="$SRC/dist/HRMA-Setup-${VERSION}.exe"
[ -f "$DMG" ] || { echo "HATA: $DMG yok — önce build_mac_app.sh + build_dmg.sh"; exit 1; }
[ -f "$EXE" ] || { echo "HATA: $EXE yok — önce build_win_payload.sh + makensis"; exit 1; }

# ---------------------------------------------------------------------------
# YAYINLANAN SHA — etiket bu commit'e açılır (3.0.6, YAYIN-1).
#
# v3.0.5 (28 Eki) ölçülen kusur: `gh release create` --target'sız çağrılıyordu.
# GitHub etiketi o anda yoksa onu VARSAYILAN DALIN (main) UCUNA açar. Bu yüzden
# yayından ÖNCE main'e push zorunluydu; o push `tests.yml`'i aynı SHA için
# yeniden tetikledi ve kapı 4/10 bu süren kopyayı bekledi (aynı commit ikinci
# kez, ~55 dk). Daha kötüsü: main'in ucu kapının doğruladığı commit değilse
# etiket (ve güncelleme kontrolünün okuduğu sürüm) BAŞKA bir ağaca bağlanır.
#
# Artık etiket kapının doğruladığı commit'e açılır: SHA kapıdan ÖNCE okunur,
# gh çağrısından hemen önce HEAD'in değişmediği yeniden ölçülür ve
# `--target` ile verilir. main yayından SONRA taşınır (yayın betiği main'e
# dokunmaz). FAIL-CLOSED: SHA okunamazsa yayın YOK — boş `--target` GitHub'da
# yine varsayılan dalın ucuna düşerdi.
YAYIN_SHA="$(git -C "$SRC" rev-parse --verify HEAD 2>/dev/null || true)"
if ! printf '%s' "$YAYIN_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
    echo "HATA: yayınlanacak commit (HEAD) okunamadı: '${YAYIN_SHA}'."
    echo "      Etiket hangi commit'e açılacağı bilinmeden yayın yapılmaz."
    exit 1
fi
echo "Yayınlanacak commit: $YAYIN_SHA"

# ---------------------------------------------------------------------------
# YAYIN TÜRÜ — taslak mı, herkese açık mı?
#
# Ayrım v2.6.26'da eklendi çünkü aşağıdaki kapı atlaması ARTIK YALNIZ TASLAK
# sürümlerde geçerli. Taslak GitHub'da yayımlanmaz, güncelleme kontrolü
# (hrma/utils/update_checker.py) taslakları görmez; dolayısıyla eksik
# doğrulamayla üretilmiş bir taslak hiçbir kullanıcının makinesine inmez.
# ---------------------------------------------------------------------------
TASLAK="${TASLAK:-0}"
if [ "$TASLAK" = "1" ]; then
    GH_TASLAK=(--draft)
    echo "Yayın türü: TASLAK (--draft) — kullanıcılara dağıtılmaz"
else
    GH_TASLAK=()
    echo "Yayın türü: HERKESE AÇIK — kurulu uygulamalar bu sürümü indirir"
fi

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
#
# v2.6.26 SIKILAŞTIRMASI — "bilinçli eylem" yetmiyormuş (Faz 4 denetimi E1/E2)
# ---------------------------------------------------------------------------
# v2.6.25 ölçülen zaman çizelgesi (GitHub API, UTC):
#   22:46:25  DMG + EXE üretildi
#   23:23:16  commit d908ae7 (ikilinin temsil ettiği kaynak) — ikiliden 37 dk SONRA
#   23:23:50  CI başladı
#   23:30:44  SÜRÜM YAYINLANDI      <-- CI hâlâ koşuyordu
#   23:38:09  CI yeşil bitti        <-- yayından 7 dk 25 sn SONRA
#
# Yani kullanıcıya giden ikili, temsil ettiği kaynaktan önce üretilmişti ve
# yayın anında hiçbir yeşil kanıt yoktu. Mekanizma tam olarak buydu:
# KAPIYI_ATLA=1 288 satırlık kapının TAMAMINI atlıyordu — taslak kısıtı yok,
# gerekçe yok, hiçbir yerde kaydı yok. Üç eksik de kapatıldı:
#
#   1. Atlama YALNIZ taslak (TASLAK=1) sürümlerde geçerli. Herkese açık
#      sürüm kapı atlanarak ÜRETİLEMEZ — betik burada durur.
#   2. Gerekçe ZORUNLU (KAPIYI_ATLA_GEREKCE, en az 20 karakter). "1" yazıp
#      geçilemez; ne atlandığı yazıyla beyan edilir.
#   3. Gerekçe İKİ yere kalıcı olarak yazılır: yerel atlama defteri
#      (packaging/release_gate_bypass.log) ve TASLAĞIN KENDİ GÖVDESİ.
#      İkincisi önemli: taslağı sonradan GitHub arayüzünden yayınlayan kişi
#      bu betiği hiç çalıştırmaz; uyarıyı sürüm notunun başında görmezse
#      atlamanın olduğunu bilemez.
# ---------------------------------------------------------------------------
KAPI_ATLAMA_UYARISI=""
if [ "${KAPIYI_ATLA:-0}" = "1" ]; then
    if [ "$TASLAK" != "1" ]; then
        echo
        echo "HATA: KAPIYI_ATLA yalnız TASLAK sürümlerde kullanılabilir."
        echo "      Herkese açık sürüm yayın kapısı atlanarak çıkarılamaz"
        echo "      (v2.6.25 böyle çıktı: ikili commit'ten 37 dk önce üretilmişti)."
        echo
        echo "      Taslak istiyorsan:  TASLAK=1 KAPIYI_ATLA=1 \\"
        echo "                          KAPIYI_ATLA_GEREKCE=\"...\" bash $0"
        echo "      Herkese açık sürüm istiyorsan kapıyı GEÇİR, atlama."
        exit 1
    fi

    GEREKCE="${KAPIYI_ATLA_GEREKCE:-}"
    if [ "${#GEREKCE}" -lt 20 ]; then
        echo
        echo "HATA: KAPIYI_ATLA_GEREKCE zorunlu ve en az 20 karakter olmalı."
        echo "      Şu an: '${GEREKCE}' (${#GEREKCE} karakter)."
        echo "      Neyin neden atlandığını yaz — bu metin taslağın gövdesine girer."
        exit 1
    fi

    ATLAMA_KAYDI="$SRC/packaging/release_gate_bypass.log"
    {
        printf '%s | v%s | HEAD %s | %s | %s\n' \
            "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" \
            "$VERSION" \
            "$(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo 'git-yok')" \
            "$(whoami)@$(hostname -s 2>/dev/null || echo '?')" \
            "$GEREKCE"
    } >> "$ATLAMA_KAYDI"

    KAPI_ATLAMA_UYARISI="var"

    echo "UYARI: yayın kapısı atlandı (TASLAK). Gerekçe deftere yazıldı:"
    echo "       $ATLAMA_KAYDI"
else
    echo "Yayın kapısı çalışıyor..."
    if ! bash "$SRC/packaging/release_gate.sh"; then
        echo
        echo "HATA: yayın kapısı kapalı — sürüm YAYINLANMADI."
        echo "Yukarıdaki KALDI satırlarını düzelt, sonra tekrar çalıştır."
        exit 1
    fi
fi

# Atlama olduysa uyarı, sürüm notunun EN BAŞINA girer (kaynak dosya
# değiştirilmez; geçici bir kopya üretilir).
if [ -n "$KAPI_ATLAMA_UYARISI" ]; then
    # 2026-08-03: şablon "hrma_release_notes" idi. BSD mktemp (macOS) bunu
    # kabul eder, GNU mktemp (Linux/CI) "too few X's in template" deyip
    # 1 döner — betik orada ölüyordu. Yayın hep macOS'tan yapıldığı için
    # fark edilmemişti; CI'da ilk kez koştuğunda çıktı. Üç X iki tarafta da
    # geçerlidir.
    GECICI_NOT="$(mktemp -t hrma_release_notes.XXXXXX)"
    cat > "$GECICI_NOT" <<UYARI
> **UYARI — YAYIN KAPISI ATLANDI (TASLAK).**
> Bu taslak, packaging/release_gate.sh doğrulamaları KOŞTURULMADAN üretildi:
> tam test takımı, bu commit'in CI durumu, canlı duman testi, paket imzası ve
> yapı-commit zaman sırası **doğrulanmamıştır**.
> Beyan edilen gerekçe: ${GEREKCE}
> Atlayan: $(whoami) · $(date -u '+%Y-%m-%d %H:%M UTC')
>
> **Bu taslağı yayına çevirmeden önce kapıyı koşturun.**

UYARI
    if [ -f "$NOT_DOSYASI" ]; then
        cat "$NOT_DOSYASI" >> "$GECICI_NOT"
    else
        printf '%s\n' "${1:-HRMA v${VERSION}}" >> "$GECICI_NOT"
    fi
    NOT_ARGS=(--notes-file "$GECICI_NOT")
fi

echo "Yayınlanacak: v${VERSION} -> ${YAYIN_SHA}"
ls -lh "$DMG" "$EXE"

# --- YAYIN-1: etiketin açılacağı commit son kez ölçülür -----------------------
# (1) Kapı ~15 dk sürer; bu arada çalışma ağacında commit atılmışsa kapının
#     doğruladığı commit ile etiketlenecek commit ayrışır -> yayın YOK.
SON_SHA="$(git -C "$SRC" rev-parse --verify HEAD 2>/dev/null || true)"
if [ "$SON_SHA" != "$YAYIN_SHA" ]; then
    echo "HATA: HEAD kapıdan sonra değişti (${YAYIN_SHA:0:12} -> ${SON_SHA:0:12})."
    echo "      Kapının doğruladığı commit yayınlanmaz; kapıyı yeniden koşturun."
    exit 1
fi
# (2) `--target` YALNIZ etiket henüz yoksa etkilidir: etiket uzakta zaten
#     varsa gh onu olduğu gibi kullanır ve --target'ı SESSİZCE yok sayar.
#     Etiket başka bir commit'teyse yayın o commit'e bağlanırdı -> yayın YOK.
#     Ölçüm başarısızsa (ağ, yetki) "etiket yok" VARSAYILMAZ.
if ! ETIKET_KAYDI="$(gh api "repos/${GH_DEPO}/git/matching-refs/tags/v${VERSION}" \
        --jq ".[] | select(.ref == \"refs/tags/v${VERSION}\") | [.object.type, .object.sha] | @tsv")"; then
    echo "HATA: uzaktaki v${VERSION} etiketi ölçülemedi (gh api) — yayın YOK."
    exit 1
fi
if [ -n "$ETIKET_KAYDI" ]; then
    ETIKET_TURU="$(printf '%s' "$ETIKET_KAYDI" | cut -f1)"
    ETIKET_HEDEF="$(printf '%s' "$ETIKET_KAYDI" | cut -f2)"
    if [ "$ETIKET_TURU" = "tag" ]; then
        # Açıklamalı etiket: nesne bir etiket nesnesidir, commit'e soyulur.
        if ! ETIKET_KAYDI="$(gh api "repos/${GH_DEPO}/git/tags/${ETIKET_HEDEF}" \
                --jq '[.object.type, .object.sha] | @tsv')"; then
            echo "HATA: açıklamalı v${VERSION} etiketi soyulamadı (gh api) — yayın YOK."
            exit 1
        fi
        ETIKET_TURU="$(printf '%s' "$ETIKET_KAYDI" | cut -f1)"
        ETIKET_HEDEF="$(printf '%s' "$ETIKET_KAYDI" | cut -f2)"
    fi
    if [ "$ETIKET_TURU" != "commit" ] || [ "$ETIKET_HEDEF" != "$YAYIN_SHA" ]; then
        echo "HATA: v${VERSION} etiketi uzakta ZATEN VAR ve ${ETIKET_TURU} ${ETIKET_HEDEF:0:12}"
        echo "      gösteriyor; yayınlanacak commit ${YAYIN_SHA:0:12}. gh bu durumda"
        echo "      --target'ı yok sayar ve sürümü o etikete bağlardı — yayın YOK."
        exit 1
    fi
    echo "Etiket v${VERSION} uzakta zaten var ve yayınlanan commit'i gösteriyor."
fi

# NOT: ${dizi[@]+"${dizi[@]}"} biçimi macOS'un bash 3.2'si için zorunlu —
# orada `set -u` altında BOŞ bir dizinin "${dizi[@]}" açılımı hata verir.
gh release create "v${VERSION}" "$DMG" "$EXE" \
    --repo "$GH_DEPO" \
    --target "$YAYIN_SHA" \
    --title "HRMA v${VERSION}" \
    ${GH_TASLAK[@]+"${GH_TASLAK[@]}"} \
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

echo "TAMAM: https://github.com/${GH_DEPO}/releases/tag/v${VERSION} (etiket -> ${YAYIN_SHA:0:12})"
if [ "$TASLAK" = "1" ]; then
    echo "TASLAK yayınlandı — kullanıcılara GÖRÜNMEZ, güncelleme kontrolü bunu okumaz."
    echo "Yayına çevirmeden önce: bash packaging/release_gate.sh"
else
    echo "Kurulu uygulamalar bir sonraki açılışta bu sürümü önerecek."
fi
