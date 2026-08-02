#!/bin/bash
# HRMA yayın kapısı — "bu sürüm çıkabilir" iddiasını MEKANİK olarak sınar.
#
# NEDEN BU DOSYA VAR (v2.6.2 fiyaskosu, 2026-07-27)
# --------------------------------------------------
# v2.6.2 KIRMIZI CI ile yayınlandı ve kullanıcının makinesinde uygulama
# hiçbir hesap yapmadı. Zaman çizelgesi:
#
#   15:16:53Z  commit push edildi, CI başladı
#   15:31:52Z  CI BAŞARISIZ bitti (17 test kırmızı)
#   15:45:53Z  sürüm YAYINLANDI  <-- CI raporu 14 dakikadır ekrandaydı
#
# 17 hatanın 15'i yerelde de düşüyordu; tam takımı bir kez koşturmak yeterdi.
# Onun yerine yalnız tests/test_v262_release_gate.py (25 kontrol) koşturulup
# "kapı 25/25" denmişti — o dosya bir özellik kapısıdır, tam takım değildir.
#
# Ayrıca sürümü kullanılamaz yapan 403 hatasını HİÇBİR test yakalayamazdı:
# test, kodun kör noktasını paylaşıyordu (ikisi de portun 8080 olduğunu
# varsayıyordu) ve uygulama hiçbir zaman 8080 dışında bir portta çalıştırılıp
# denenmemişti. Bu yüzden aşağıdaki 6/7 kapısı CANLI sunucuyu VARSAYILAN
# OLMAYAN bir portta ayağa kaldırıp gerçekten hesap yaptırır.
#
# v2.6.26 EKLERİ (Faz 4 denetimi E1/E2)
# --------------------------------------
# 3/7  Yapı ↔ commit zaman sırası: artefakt commit'ten ÖNCE üretilmişse KALDI.
# 4/7  CI kontrolü artık bu SHA'nın BÜTÜN koşularını sayar (tek koşu değil) ve
#      tamamlanmamış koşu varsa KALDI der — "CI'ı beklemeden yayınlama" hatası.
#
# Kullanım:
#   bash packaging/release_gate.sh            # tam kapı (yayın öncesi)
#   TAKIMI_ATLA=1 bash packaging/release_gate.sh   # yalnız YEREL tam takım
#                                                  # atlanır; CI kontrolü yine
#                                                  # çalışır ve atlanamaz
#
# Çıkış kodu 0 ise yayın serbest. Aksi halde hangi kapının neden kapandığını
# adıyla söyler.

set -uo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SRC"

KIRMIZI='\033[0;31m'; YESIL='\033[0;32m'; SARI='\033[0;33m'; SIFIR='\033[0m'
HATA_SAYISI=0

basarili() { printf "${YESIL}  GEÇTİ${SIFIR}  %s\n" "$1"; }
basarisiz() { printf "${KIRMIZI}  KALDI${SIFIR}  %s\n" "$1"; HATA_SAYISI=$((HATA_SAYISI + 1)); }
atlandi()  { printf "${SARI}  ATLANDI${SIFIR} %s\n" "$1"; }
baslik()   { printf "\n=== %s ===\n" "$1"; }

PY="${PYTHON:-python3}"

# ---------------------------------------------------------------------------
baslik "1/7  Sürüm tutarlılığı"
# ---------------------------------------------------------------------------
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' hrma/__init__.py)"
if [ -z "$VERSION" ]; then
    basarisiz "hrma/__init__.py içinden sürüm okunamadı"
else
    basarili "paket sürümü: $VERSION"

    CHANGELOG_VER="$("$PY" -c "import json;print(json.load(open('hrma/data/changelog.json'))['versions'][0]['version'])" 2>/dev/null)"
    if [ "$CHANGELOG_VER" = "$VERSION" ]; then
        basarili "changelog en üst girdi: $CHANGELOG_VER"
    else
        basarisiz "changelog en üst girdi '$CHANGELOG_VER', paket '$VERSION' — eşleşmiyor"
    fi

    NOTLAR="packaging/release_notes_v${VERSION}.md"
    if [ -f "$NOTLAR" ]; then
        basarili "sürüm notu dosyası: $NOTLAR"
    else
        basarisiz "sürüm notu yok: $NOTLAR"
    fi

    if grep -q "HRMA-Setup-${VERSION}" README.md 2>/dev/null; then
        basarili "README indirme linkleri $VERSION"
    else
        basarisiz "README hâlâ eski sürümü gösteriyor (HRMA-Setup-${VERSION} geçmiyor)"
    fi
fi

# ---------------------------------------------------------------------------
baslik "2/7  Git durumu"
# ---------------------------------------------------------------------------
if [ -n "$(git status --porcelain)" ]; then
    basarisiz "çalışma ağacı kirli — commit edilmemiş değişiklikle sürüm çıkmaz"
    git status --short | head -10
else
    basarili "çalışma ağacı temiz"
fi

YEREL="$(git rev-parse HEAD)"
UZAK="$(git rev-parse '@{u}' 2>/dev/null || echo 'yok')"
if [ "$UZAK" = "yok" ]; then
    basarisiz "üst akış dalı yok — push edilmemiş"
elif [ "$YEREL" != "$UZAK" ]; then
    basarisiz "HEAD push edilmemiş (yerel $YEREL, uzak $UZAK)"
else
    basarili "HEAD push edilmiş: ${YEREL:0:8}"
fi

# ---------------------------------------------------------------------------
baslik "3/7  Yapı ↔ commit zaman sırası"
# ---------------------------------------------------------------------------
# v2.6.25'te yayınlanan ikili, temsil ettiği kaynaktan ÖNCE üretilmişti.
# Ölçülen zaman damgaları (GitHub API, UTC):
#
#   22:46:25  DMG + EXE üretildi
#   23:23:16  commit d908ae7  <-- ikiliden 36 dk 51 sn SONRA
#
# Yani indirilen kurulum paketi, sürüm notunun anlattığı düzeltmelerin
# HİÇBİRİNİ içermiyordu; kaynak ile ikili arasındaki bağ koptu ve bunu
# hiçbir kontrol yakalamadı. Bu kapı o bağı ölçer: artefakt dosyasının
# değiştirilme zamanı, yayınlanacak commit'in zamanından ESKİ OLAMAZ.
#
# Karşılaştırma commit'in COMMITTER tarihine göre yapılır (%ct): rebase /
# amend sonrası author tarihi eski kalabilir, ikilinin temsil ettiği ağacı
# belirleyen şey committer tarihidir.
DMG_YOL="dist/HRMA-Setup-${VERSION}-macOS.dmg"
EXE_YOL="dist/HRMA-Setup-${VERSION}.exe"
COMMIT_EPOCH="$(git show -s --format=%ct HEAD 2>/dev/null || echo '')"
if [ -z "$COMMIT_EPOCH" ]; then
    basarisiz "HEAD commit zamanı okunamadı — yapı/commit sırası doğrulanamıyor"
else
    for ARTEFAKT in "$DMG_YOL" "$EXE_YOL"; do
        if [ ! -f "$ARTEFAKT" ]; then
            basarisiz "artefakt yok: $ARTEFAKT — bu commit'ten sonra üretilmeli"
            continue
        fi
        ARTEFAKT_EPOCH="$("$PY" -c "import os,sys;print(int(os.path.getmtime(sys.argv[1])))" "$ARTEFAKT" 2>/dev/null || echo '')"
        if [ -z "$ARTEFAKT_EPOCH" ]; then
            basarisiz "$ARTEFAKT değiştirilme zamanı okunamadı"
        elif [ "$ARTEFAKT_EPOCH" -ge "$COMMIT_EPOCH" ]; then
            basarili "$(basename "$ARTEFAKT") commit'ten $(( (ARTEFAKT_EPOCH - COMMIT_EPOCH) / 60 )) dk SONRA üretilmiş"
        else
            basarisiz "$(basename "$ARTEFAKT") commit'ten $(( (COMMIT_EPOCH - ARTEFAKT_EPOCH) / 60 )) dk ÖNCE üretilmiş — v2.6.25 hatası (ikili kaynağı temsil etmiyor). YENİDEN DERLE."
        fi
    done
fi

# ---------------------------------------------------------------------------
baslik "4/7  GitHub Actions (bu commit)"
# ---------------------------------------------------------------------------
# CI KONTROLÜ ATLANAMAZ (v2.6.25 yayınından çıkan ders).
#
# Bu adım eskiden HIZLI=1 ile atlanabiliyordu, tam takımla AYNI bayrağın
# altındaydı. Oysa ikisi taban tabana zıt maliyette: tam takım yerelde 20-40
# dakika sürer, CI kontrolü tek bir API çağrısıdır ve saniyeler alır.
# Bunları aynı bayrağa bağlamak, "hızlı geçeyim" diyen kişinin farkında
# olmadan projenin EN GÜÇLÜ kanıtını (temiz makinede yeşil takım) atlamasına
# yol açıyor — yani v2.6.2'yi yayınlayan hatanın ta kendisine.
#
# 2.6.25 yayınında HIZLI=1 kullanıldı ve CI elle teyit edildi; bir dahakine
# kimse teyit etmeyebilir. Artık atlanamaz.
#
# v2.6.26 EKİ — tek koşuya bakmak yetmiyor (Faz 4 denetimi E1/E2c).
# Eski hâli `--limit 1` ile YALNIZ EN SON koşuya bakıyordu. Depoda artık iki
# iş akışı var (tests.yml + release.yml); iki koşudan biri bitmiş biri hâlâ
# koşuyorken en son bitene bakmak "yeşil" der. v2.6.25 tam olarak böyle
# yayınlandı: sürüm 23:30:44'te çıktı, CI 23:38:09'da bitti — yayın anında
# koşu DEVAM EDİYORDU. Kapı artık bu SHA'nın BÜTÜN koşularını sayar:
#   - hiç koşu yoksa            -> KALDI (CI henüz başlamamış)
#   - biri bile tamamlanmamışsa -> KALDI (yayın CI'ı beklemez hatası)
#   - biri bile başarısızsa     -> KALDI
#   - 'tests' iş akışı yoksa    -> KALDI (asıl kanıt koşmamış)
if ! command -v gh >/dev/null 2>&1; then
    basarisiz "gh CLI yok — CI durumu doğrulanamıyor"
else
    KOSULAR="$(gh run list --commit "$YEREL" --limit 50 \
               --json conclusion,status,workflowName,headSha \
               --jq '.[] | [.workflowName, .status, (.conclusion // "-"), .headSha] | @tsv' \
               2>/dev/null || echo '')"
    if [ -z "$KOSULAR" ]; then
        basarisiz "bu commit (${YEREL:0:8}) için CI koşusu yok — push edilip başlaması beklenmeli"
    else
        BEKLEYEN=0; DUSEN=0; TESTS_YESIL=0; TOPLAM=0
        while IFS=$'\t' read -r AKIS DURUM SONUC SHA; do
            [ -n "$AKIS" ] || continue
            TOPLAM=$((TOPLAM + 1))
            # Savunma: gh commit'e göre süzse de SHA'yı burada da doğruluyoruz;
            # yayınlanacak ikili TAM OLARAK bu ağacı temsil etmeli.
            if [ -n "$SHA" ] && [ "$SHA" != "$YEREL" ]; then
                basarisiz "CI koşusu farklı SHA'ya ait: $AKIS (${SHA:0:8} != ${YEREL:0:8})"
                continue
            fi
            if [ "$DURUM" != "completed" ]; then
                basarisiz "CI hâlâ koşuyor: $AKIS ($DURUM) — yayın CI'ı BEKLER"
                BEKLEYEN=$((BEKLEYEN + 1))
                continue
            fi
            case "$SONUC" in
                success) [ "$AKIS" = "tests" ] && TESTS_YESIL=1 ;;
                skipped) ;;  # koşulu sağlanmadığı için atlanan iş akışı hata değil
                *) basarisiz "CI koşusu başarısız: $AKIS ($SONUC)"; DUSEN=$((DUSEN + 1)) ;;
            esac
        done <<< "$KOSULAR"

        if [ "$TESTS_YESIL" -eq 1 ]; then
            basarili "CI 'tests' iş akışı bu SHA'da yeşil (${YEREL:0:8}, $TOPLAM koşu incelendi)"
        elif [ "$BEKLEYEN" -eq 0 ] && [ "$DUSEN" -eq 0 ]; then
            basarisiz "'tests' iş akışının bu SHA'da yeşil koşusu YOK — asıl kanıt eksik"
        fi
    fi
fi

# ---------------------------------------------------------------------------
baslik "5/7  Tam test takımı"
# ---------------------------------------------------------------------------
# Yalnız BU adım atlanabilir: yerel tam takım, CI'ın temiz makinede koştuğu
# takımın aynısıdır. 3/6 yeşilse buradaki koşu fazladan bir doğrulamadır.
# TAKIMI_ATLA=1 tercih edilen ad; HIZLI=1 geriye uyumluluk için kabul edilir
# ama ARTIK CI kontrolünü atlamaz.
if [ "${TAKIMI_ATLA:-${HIZLI:-0}}" = "1" ]; then
    atlandi "tam takım atlandı (CI yeşil olduğu için); atlamayı kapatmak: TAKIMI_ATLA=0"
else
    echo "  (tam takım ~15 dk sürer; alt küme koşturmak bu kapıyı GEÇMİŞ SAYMAZ)"
    if "$PY" -m pytest -q --no-header -p no:cacheprovider > /tmp/hrma_gate_pytest.log 2>&1; then
        basarili "$(tail -1 /tmp/hrma_gate_pytest.log)"
    else
        basarisiz "tam takım kırmızı — /tmp/hrma_gate_pytest.log"
        grep -E '^FAILED|^ERROR' /tmp/hrma_gate_pytest.log | head -20
    fi
fi

# ---------------------------------------------------------------------------
baslik "6/7  Canlı duman testi — VARSAYILAN OLMAYAN portta"
# ---------------------------------------------------------------------------
# v2.6.2'yi kullanılamaz yapan hata tam buradaydı: uygulama 8080 dışında bir
# porta düştüğünde kendi sayfası kendi API'sinden 403 alıyordu. Bu kapı gerçek
# bir sunucu ayağa kaldırır, tarayıcının yapacağı gibi Origin başlığı gönderir
# ve gerçekten hesap yaptırır.
PORT=8087
"$PY" - "$PORT" <<'PY' &
import logging
import sys

from hrma.app import app

port = int(sys.argv[1])
logging.getLogger('werkzeug').setLevel(logging.ERROR)
try:
    # Paketlenmiş uygulamanın kullandığı sunucu; kuruluysa onu kullan ki
    # duman testi gerçek koşullara daha yakın olsun.
    from waitress import serve
    logging.getLogger('waitress').setLevel(logging.ERROR)
    serve(app, host='127.0.0.1', port=port, threads=4, _quiet=True)
except ImportError:
    # waitress yalnız paketleme ortamında zorunlu; geliştirme makinesinde
    # kurulu olmayabilir. Kapının amacı KÖKEN/PORT davranışını ölçmek,
    # sunucu markasını değil — Flask'ın kendi sunucusu bunun için yeterli.
    app.run(host='127.0.0.1', port=port, debug=False,
            threaded=True, use_reloader=False)
PY
SUNUCU_PID=$!
trap 'kill $SUNUCU_PID 2>/dev/null || true' EXIT

DUMAN_SONUC=1
for _ in $(seq 1 60); do
    if curl -sf "http://127.0.0.1:${PORT}/" -o /dev/null 2>/dev/null; then
        DUMAN_SONUC=0
        break
    fi
    sleep 1
done

if [ "$DUMAN_SONUC" -ne 0 ]; then
    basarisiz "sunucu ${PORT} portunda 60 sn içinde ayağa kalkmadı"
else
    basarili "sunucu ${PORT} portunda ayakta"
    for UC in "/calculate:hibrit" "/calculate_solid:katı" "/calculate_liquid:sıvı"; do
        YOL="${UC%%:*}"; AD="${UC##*:}"
        KOD="$(curl -s -o /tmp/hrma_gate_body.json -w '%{http_code}' \
               -X POST "http://127.0.0.1:${PORT}${YOL}" \
               -H 'Content-Type: application/json' \
               -H "Origin: http://127.0.0.1:${PORT}" \
               -d '{"motor_name":"kapi","thrust":5000,"chamber_pressure":25,
                    "of_ratio":7.0,"burn_time":10,"fuel_type":"htpb",
                    "oxidizer_type":"n2o","expansion_ratio":8.0,"l_star":1.0}' \
               2>/dev/null)"
        if [ "$KOD" = "403" ]; then
            basarisiz "$AD motor: ${PORT} portunda 403 — v2.6.2 hatası GERİ GELDİ"
        elif [ "$KOD" = "200" ]; then
            basarili "$AD motor: ${PORT} portunda hesap yapıyor (200)"
        else
            basarisiz "$AD motor: beklenmeyen HTTP $KOD ($(head -c 160 /tmp/hrma_gate_body.json))"
        fi
    done
fi

kill $SUNUCU_PID 2>/dev/null || true
trap - EXIT

# ---------------------------------------------------------------------------
baslik "7/7  macOS paket imzası"
# ---------------------------------------------------------------------------
# v2.6.25 güncelleme çökmesi (2026-07-28): build_mac_app.sh içindeki codesign
# hatayı `2>/dev/null || true` ile yutuyordu; paket İMZASIZ üretildi ve ÜÇ
# SÜRÜM (2.6.0/2.6.1/2.6.2) böyle yayınlandı. macOS Tahoe sıkılaşınca lsd
# paketi launch-disabled kaydetti (-67062, "code object is not signed at
# all"), `open` "executable is missing" dedi, otomatik güncelleme eski sürüme
# geri döndü. Bu kapı ÜRETİLEN artefaktları doğrular: imzasız .app ya da
# imzasız DMG içeriği = KAPI KAPALI.
#
# İki bilinçli tasarım kararı (2026-07-30, gerçek paket üzerinde ölçüldü):
#   1. Diskteki .app için --strict KULLANILMAZ: derleme ağacı iCloud
#      senkronunda ve iCloud .app köküne com.apple.FinderInfo'yu silindikten
#      milisaniyeler sonra geri yazıyor; sıkı doğrulamanın detritus denetimi
#      buna takılıp HER ZAMAN kırmızı kalıyor. FinderInfo mühre girmez;
#      `codesign --verify --deep` imzayı ve kaynak mührünü tam kontrol eder.
#   2. DMG içeriği için ALTIN STANDART uygulanır: içindeki .app xattr'sız
#      kopyalanır (ditto --noextattr) ve o kopyada TAM SIKI doğrulama
#      (--deep --strict) çalışır. Ölçüm: kopya ~2 dk, doğrulama ~9 sn.
#      Kullanıcıya giden şey diskteki .app değil DMG içeriğidir.
#
# Not: imza ad-hoc (`codesign -s -`). Gatekeeper (spctl) ad-hoc imzayı onaylı
# geliştirici saymadığı için spctl burada ÇALIŞTIRILMAZ; ölçüt codesign
# doğrulamasıdır — "code object is not signed at all" hâlini bu bile yakalar.
if [ "$(uname)" != "Darwin" ]; then
    atlandi "macOS değil — imza kontrolü yalnız macOS'ta anlamlı"
else
    APP_BUILD="packaging/mac/build.noindex/HRMA.app"
    if [ ! -d "$APP_BUILD" ]; then
        basarisiz "derlenmiş .app yok: $APP_BUILD — önce packaging/build_mac_app.sh"
    elif codesign --verify --deep "$APP_BUILD" 2>/tmp/hrma_gate_codesign.log; then
        basarili ".app imzası geçerli: $APP_BUILD"
    else
        basarisiz ".app İMZASIZ/BOZUK: $(head -1 /tmp/hrma_gate_codesign.log)"
    fi

    # DMG_YOL 3/7 adımında tanımlandı (yapı ↔ commit zaman sırası).
    if [ ! -f "$DMG_YOL" ]; then
        basarisiz "DMG yok: $DMG_YOL — önce packaging/build_dmg.sh"
    else
        DMG_MNT="$(mktemp -d /tmp/hrma_gate_dmg.XXXXXX)"
        if hdiutil attach -readonly -nobrowse -noverify -mountpoint "$DMG_MNT" "$DMG_YOL" >/dev/null 2>&1; then
            # Hızlı kontrol: mount edilmiş kopyada imza var ve mühür tutuyor mu?
            if codesign --verify --deep "$DMG_MNT/HRMA.app" 2>/tmp/hrma_gate_codesign.log; then
                basarili "DMG içindeki HRMA.app imzası geçerli: $DMG_YOL"

                # Altın standart: xattr'sız kopyada TAM SIKI doğrulama.
                # DMG, stage'den FinderInfo'yu miras alır; o mühürde olmadığı
                # için önce soyulur, kalan HER ŞEY sıkı denetimden geçer.
                echo "  (sıkı doğrulama: xattr'sız kopya çıkarılıyor, ~2 dk)"
                SIKI_KOPYA="$(mktemp -d /tmp/hrma_gate_strict.XXXXXX)"
                if ditto --noextattr --norsrc "$DMG_MNT/HRMA.app" "$SIKI_KOPYA/HRMA.app" 2>/tmp/hrma_gate_codesign.log \
                   && codesign --verify --deep --strict "$SIKI_KOPYA/HRMA.app" 2>/tmp/hrma_gate_codesign.log; then
                    basarili "DMG içeriği SIKI doğrulamadan geçti (--deep --strict)"
                else
                    basarisiz "DMG içeriği sıkı doğrulamada kaldı: $(head -1 /tmp/hrma_gate_codesign.log)"
                fi
                rm -rf "$SIKI_KOPYA"
            else
                basarisiz "DMG içindeki HRMA.app İMZASIZ/BOZUK: $(head -1 /tmp/hrma_gate_codesign.log)"
            fi
            hdiutil detach "$DMG_MNT" >/dev/null 2>&1 || hdiutil detach "$DMG_MNT" -force >/dev/null 2>&1 || true
        else
            basarisiz "DMG mount edilemedi: $DMG_YOL"
        fi
        rmdir "$DMG_MNT" 2>/dev/null || true
    fi
fi

# ---------------------------------------------------------------------------
printf "\n============================================\n"
if [ "$HATA_SAYISI" -eq 0 ]; then
    printf "${YESIL}KAPI AÇIK${SIFIR} — v%s yayınlanabilir\n" "$VERSION"
    exit 0
fi
printf "${KIRMIZI}KAPI KAPALI${SIFIR} — %d kontrol kaldı. Yayın YOK.\n" "$HATA_SAYISI"
exit 1
