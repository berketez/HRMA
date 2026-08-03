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
# denenmemişti. Bu yüzden aşağıdaki 6/8 kapısı CANLI sunucuyu VARSAYILAN
# OLMAYAN bir portta ayağa kaldırıp gerçekten hesap yaptırır.
#
# v2.6.26 EKLERİ (Faz 4 denetimi E1/E2)
# --------------------------------------
# 3/8  Yapı ↔ commit zaman sırası: artefakt commit'ten ÖNCE üretilmişse KALDI.
# 4/8  CI kontrolü artık bu SHA'nın BÜTÜN koşularını sayar (tek koşu değil) ve
#      tamamlanmamış koşu varsa KALDI der — "CI'ı beklemeden yayınlama" hatası.
#
# 2026-08-03 EKLERİ (paket İÇERİĞİ denetlenmiyordu)
# --------------------------------------------------
# Kapı bugüne kadar paketin VAR olduğuna, imzalı olduğuna ve uygulamanın 200
# döndürdüğüne bakıyordu; İÇİNDE ne olduğuna hiç bakmıyordu. Ölçülen üç sonuç:
#   - Yayınlanan DMG mount edildi: examples/ dizini YOK, tek bir .hrma yok.
#     Oysa examples/README.md kullanıcıya o dosyaları kopyalamasını söylüyor.
#   - Bir önceki sürümde DMG 526 MB'den 383 MB'ye düştü (bytecode ön-derleme
#     kaybı) ve kimse fark etmedi — boyut sapması ölçülmüyordu.
#   - 6/8 duman testi yalnız HTTP 200'e bakıyordu: uç boş/eksik gövde de
#     dönse kapı "hesap yapıyor" diyordu.
# Eklenenler:
#   3/8  mtime'ın YANINA BUILD_INFO.sha == HEAD karşılaştırması (mtime hangi
#        AĞAÇTAN derlendiğini söyleyemez; `touch` bile onu tazeler).
#   6/8  gövde denetimi: plots.performance ve nozzle_design.performance.
#        exit_mach > 1 — alan yoksa AÇIK HATA, kapı durur.
#   8/8  paket içerik manifesti + bir önceki yayına göre boyut sapması.
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

# Artefakt boyutunun bir önceki yayına göre kabul edilen sapma sınırı (%).
# 8/8 adımında kullanılır; tek tanım burada durur ki eşik betiğin içine
# dağılmasın.
BOYUT_TOLERANS_YUZDE=20

# --- DMG yardımcıları -------------------------------------------------------
# Kapının üç ayrı adımı (3/8 köken, 7/8 imza, 8/8 içerik) DMG'nin İÇİNE
# bakmak zorunda. Her biri kendi mount/detach çiftini elle yazınca bir yerde
# detach unutuluyor ve /Volumes'ta asılı kalan bir birim sonraki koşuyu
# bozuyor. Bağlama tek yerden yapılır.
dmg_bagla() {   # $1 = dmg yolu; başarılıysa mount noktasını stdout'a basar
    local nokta
    nokta="$(mktemp -d /tmp/hrma_gate_mnt.XXXXXX)"
    if hdiutil attach -readonly -nobrowse -noverify -mountpoint "$nokta" "$1" \
       >/dev/null 2>&1; then
        echo "$nokta"
        return 0
    fi
    rmdir "$nokta" 2>/dev/null || true
    return 1
}

dmg_coz() {     # $1 = mount noktası
    hdiutil detach "$1" >/dev/null 2>&1 || hdiutil detach "$1" -force >/dev/null 2>&1 || true
    rmdir "$1" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
baslik "1/8  Sürüm tutarlılığı"
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
baslik "2/8  Git durumu"
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
baslik "3/8  Yapı ↔ commit zaman sırası"
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

# --- BUILD_INFO: paketin İÇİNDEKİ köken kaydı -------------------------------
# mtime yalnızca "ne zaman dokunuldu" der. Hangi AĞAÇTAN derlendiğini
# söyleyemez: `touch dist/*.dmg` bile üç yıllık bir paketi "commit'ten sonra
# üretilmiş" gösterir. Derleme betikleri artık paketin içine BUILD_INFO.json
# gömüyor (build_mac_app.sh / build_win_payload.sh); burada o kayıttaki sha
# HEAD ile karşılaştırılır. Eşleşmiyorsa yayınlanacak ikili BAŞKA bir ağacı
# temsil ediyor demektir.
#
# Kapsam beyanı: macOS tarafında kayıt DMG'nin İÇİNDEN okunur (kullanıcıya
# giden şey odur). Windows tarafında exe'nin içi açılamıyor — NSIS arşivini
# açacak araç her makinede yok — bu yüzden exe'nin derlendiği STAGING ağacı
# (packaging/win/payload/app/BUILD_INFO.json) okunur. Doğrulanan şey exe
# ikilisi DEĞİL, exe'nin üretildiği ağaçtır; aradaki fark mtime kontrolüyle
# kapatılır (payload commit'ten sonra, exe payload'dan sonra üretilir).
KOKEN_OKU='
import json, sys
try:
    k = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as e:
    print("OKUNAMADI\t%s" % e); raise SystemExit(0)
print("%s\t%s\t%s" % (k.get("sha") or "YOK", k.get("tree_dirty"),
                      k.get("version") or "YOK"))
'
koken_denetle() {   # $1 = BUILD_INFO.json yolu, $2 = insan okunur ad
    local kayit sha kirli surum
    if [ ! -f "$1" ]; then
        basarisiz "$2: BUILD_INFO.json yok — paket hangi ağaçtan derlendiğini taşımıyor (yeniden derleyin)"
        return
    fi
    kayit="$("$PY" -c "$KOKEN_OKU" "$1" 2>/dev/null || echo '')"
    sha="$(printf '%s' "$kayit" | cut -f1)"
    kirli="$(printf '%s' "$kayit" | cut -f2)"
    surum="$(printf '%s' "$kayit" | cut -f3)"
    if [ -z "$kayit" ] || [ "$sha" = "OKUNAMADI" ]; then
        basarisiz "$2: BUILD_INFO.json okunamadı ($kayit)"
    elif [ "$sha" = "YOK" ] || [ "$sha" = "None" ]; then
        basarisiz "$2: BUILD_INFO.sha boş — derleme sırasında git okunamamış, köken KANITSIZ"
    elif [ "$sha" != "$YEREL" ]; then
        basarisiz "$2: BUILD_INFO.sha=${sha:0:8} != HEAD=${YEREL:0:8} — paket BAŞKA bir ağaçtan derlenmiş. YENİDEN DERLE."
    elif [ "$kirli" = "True" ]; then
        basarisiz "$2: paket KİRLİ çalışma ağacından derlenmiş (BUILD_INFO.tree_dirty) — commit edilmemiş değişiklik içeriyor"
    elif [ "$surum" != "$VERSION" ]; then
        basarisiz "$2: BUILD_INFO.version=$surum, paket sürümü $VERSION — eşleşmiyor"
    else
        basarili "$2: köken kanıtlı (sha ${sha:0:8} = HEAD, ağaç temiz, v$surum)"
    fi
}

if [ "$(uname)" = "Darwin" ] && [ -f "$DMG_YOL" ]; then
    KOKEN_MNT="$(dmg_bagla "$DMG_YOL" || echo '')"
    if [ -n "$KOKEN_MNT" ]; then
        koken_denetle "$KOKEN_MNT/HRMA.app/Contents/Resources/app/BUILD_INFO.json" "DMG içeriği"
        dmg_coz "$KOKEN_MNT"
    else
        basarisiz "DMG mount edilemedi, köken kaydı okunamadı: $DMG_YOL"
    fi
elif [ "$(uname)" != "Darwin" ]; then
    atlandi "DMG köken kaydı yalnız macOS'ta okunabilir (hdiutil)"
fi
koken_denetle "packaging/win/payload/app/BUILD_INFO.json" "Windows payload (exe'nin derlendiği ağaç)"

# ---------------------------------------------------------------------------
baslik "4/8  GitHub Actions (bu commit)"
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
baslik "5/8  Tam test takımı"
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
baslik "6/8  Canlı duman testi — VARSAYILAN OLMAYAN portta"
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
    # 2026-08-03: üç uca da TEK yük gönderiliyordu. Hibritte yetiyordu ama
    # Faz 5'te katı ve sıvı uçlarına zorunlu-girdi doğrulaması eklendi
    # (eksik girdiyle varsayılan doldurup tasarım üretmek YASAK) ve ikisi de
    # haklı olarak 422 dönmeye başladı. Kapı bunu "beklenmeyen" sayıp yayını
    # durduruyordu — yani doğru davranış kapıyı kilitliyordu. Artık her uç
    # kendi tam yükünü alıyor; amaç uygulamanın GERÇEKTEN hesap yaptığını
    # ölçmek, bu yüzden `use_tutorial_defaults` kestirmesi KULLANILMIYOR.
    YUK_HIBRIT='{"motor_name":"kapi","thrust":5000,"chamber_pressure":25,
                 "of_ratio":7.0,"burn_time":10,"fuel_type":"htpb",
                 "oxidizer_type":"n2o","expansion_ratio":8.0,"l_star":1.0}'
    YUK_KATI='{"motor_name":"kapi","motor_type":"solid","chamber_diameter":100,
               "outer_diameter":100,"core_diameter":30,"grain_length":500,
               "grain_count":3,"propellant_type":"apcp","chamber_pressure":40}'
    YUK_SIVI='{"motor_name":"kapi","motor_type":"liquid","thrust":10000,
               "burn_time":400,"chamber_pressure":50,"fuel_type":"rp1",
               "oxidizer_type":"lox","mixture_ratio":2.3}'

    # 2026-08-03: bu adım YALNIZ HTTP koduna bakıyordu. 200 "sunucu ayakta"
    # demektir, "hesap yaptı" demez: uç boş bir sözlük, yalnız uyarı listesi
    # ya da grafiksiz bir gövde de dönse kapı GEÇİYORDU. Artık gövdenin
    # kendisi denetleniyor — biri çizim, biri fizik tarafından iki alan:
    #   plots.performance                      -> performans panosu üretildi
    #   nozzle_design.performance.exit_mach>1  -> lüle gerçekten süpersonik
    #
    # Lüle çözümünün yeri uçtan uca AYNI DEĞİL: hibrit yanıtında ölçüldü
    # (2026-08-03, /calculate) -> motor.nozzle_design.performance.exit_mach
    # = 3.000; üst düzey nozzle_design ise null. Bu yüzden denetleyici SAYILI
    # ve AÇIKÇA YAZILMIŞ bir aday yol listesinde arar — gövdeyi baştan sona
    # tarayıp "bir yerde exit_mach var" demez (o, alakasız bir alt nesneden
    # gelen sayıyı kanıt sayardı). Aday yolların hiçbirinde alan yoksa kapı
    # DURUR: eksik alan "denetlenemedi" değil, denetimin BAŞARISIZ olmasıdır.
    GOVDE_DENETI="$(mktemp /tmp/hrma_gate_body_check.XXXXXX)"
    cat > "$GOVDE_DENETI" <<'PY'
import json
import sys

#: exit_mach'in aranacağı yollar. Yeni bir uç başka bir yere koyarsa buraya
#: EKLENİR — sessizce kabul edilmez.
ADAY_YOLLAR = (
    ('nozzle_design', 'performance', 'exit_mach'),
    ('motor', 'nozzle_design', 'performance', 'exit_mach'),
)


def gez(kok, yol):
    dugum = kok
    for anahtar in yol:
        if not isinstance(dugum, dict) or anahtar not in dugum:
            return None, False
        dugum = dugum[anahtar]
    return dugum, True


try:
    with open(sys.argv[1], encoding='utf-8') as f:
        govde = json.load(f)
except Exception as hata:
    print('gövde JSON olarak ayrıştırılamadı: %s' % hata)
    raise SystemExit(0)

if not isinstance(govde, dict):
    print('gövde sözlük değil: %s' % type(govde).__name__)
    raise SystemExit(0)

eksik = []
cizimler = govde.get('plots')
if not isinstance(cizimler, dict):
    eksik.append('plots (yok ya da sözlük değil)')
elif not cizimler.get('performance'):
    eksik.append('plots.performance (boş/yok — performans panosu üretilmedi)')

mach, bulundu, bulunan_yol = None, False, None
for yol in ADAY_YOLLAR:
    mach, bulundu = gez(govde, yol)
    if bulundu:
        bulunan_yol = '.'.join(yol)
        break

if not bulundu:
    eksik.append('exit_mach hiçbir aday yolda yok (%s) — lüle çözümü yanıtta '
                 'taşınmıyor' % ' | '.join('.'.join(y) for y in ADAY_YOLLAR))
elif not isinstance(mach, (int, float)) or isinstance(mach, bool):
    eksik.append('%s sayı değil: %r' % (bulunan_yol, mach))
elif not mach > 1.0:
    eksik.append('%s=%.3f — süpersonik değil (>1 bekleniyor)'
                 % (bulunan_yol, mach))
elif len(sys.argv) > 2:
    # Kanıt DOSYAYA yazılır, stdout'a değil: stdout'un sözleşmesi "yalnız
    # sorunlar" — başarıda tek karakter bile basılmaz ki kapı, python
    # çökerse (yığın izi stdout'a düşer) onu sessizce başarı sanmasın.
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        f.write('%s=%.3f' % (bulunan_yol, mach))

print('; '.join(eksik))
PY
    for UC in "/calculate:hibrit" "/calculate_solid:katı" "/calculate_liquid:sıvı"; do
        YOL="${UC%%:*}"; AD="${UC##*:}"
        case "$YOL" in
            /calculate_solid)  YUK="$YUK_KATI" ;;
            /calculate_liquid) YUK="$YUK_SIVI" ;;
            *)                 YUK="$YUK_HIBRIT" ;;
        esac
        KOD="$(curl -s -o /tmp/hrma_gate_body.json -w '%{http_code}' \
               -X POST "http://127.0.0.1:${PORT}${YOL}" \
               -H 'Content-Type: application/json' \
               -H "Origin: http://127.0.0.1:${PORT}" \
               -d "$YUK" \
               2>/dev/null)"
        if [ "$KOD" = "403" ]; then
            basarisiz "$AD motor: ${PORT} portunda 403 — v2.6.2 hatası GERİ GELDİ"
        elif [ "$KOD" = "200" ]; then
            rm -f /tmp/hrma_gate_body_kanit.txt
            GOVDE_EKSIK="$("$PY" "$GOVDE_DENETI" /tmp/hrma_gate_body.json \
                           /tmp/hrma_gate_body_kanit.txt 2>&1 || true)"
            if [ -z "$GOVDE_EKSIK" ]; then
                basarili "$AD motor: ${PORT} portunda hesap yapıyor (200, plots.performance + $(cat /tmp/hrma_gate_body_kanit.txt 2>/dev/null || echo 'exit_mach kanıtı yazılamadı'))"
            else
                basarisiz "$AD motor: 200 döndü ama gövde eksik -> $GOVDE_EKSIK"
            fi
        else
            basarisiz "$AD motor: beklenmeyen HTTP $KOD ($(head -c 160 /tmp/hrma_gate_body.json))"
        fi
    done
fi
rm -f "${GOVDE_DENETI:-}" 2>/dev/null || true

kill $SUNUCU_PID 2>/dev/null || true
trap - EXIT

# ---------------------------------------------------------------------------
baslik "7/8  macOS paket imzası"
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

    # DMG_YOL 3/8 adımında tanımlandı (yapı ↔ commit zaman sırası).
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
baslik "8/8  Paket içerik manifesti + boyut sapması"
# ---------------------------------------------------------------------------
# Kapının hiçbir adımı paketin İÇİNE bakmıyordu. İki ölçülmüş sonuç:
#   a) Yayınlanan DMG mount edildi: Resources/app/examples YOK, tek .hrma yok.
#      examples/README.md ise kullanıcıya "bu dizindeki dosyaları projeler
#      klasörüne kopyalayın" diyor — var olmayan bir dizini işaret ediyordu.
#   b) Bir önceki sürümde DMG 526 MB'den 383 MB'ye düştü (bytecode ön-derleme
#      kaybı) ve kimse fark etmedi. İmza geçerliydi, uygulama açılıyordu,
#      kapı yeşildi; eksik olan şey ölçülmüyordu.
# Bu adım paketin taşıması gereken parçaları TEK TEK sayar ve artefakt
# boyutunu bir önceki yayınla karşılaştırır.
#
# Beklenen örnek sayısı SABİT YAZILMAZ: depodaki examples/*.hrma ne kadarsa
# pakette o kadar olmalı. Örnek eklendiğinde bekçi kendini günceller, örnek
# paketlemede düştüğünde kapı kapanır.
REPO_ORNEK="$(find "$SRC/examples" -maxdepth 1 -name '*.hrma' 2>/dev/null | wc -l | tr -d ' ')"
if [ "$REPO_ORNEK" -lt 1 ]; then
    basarisiz "depoda örnek proje yok (examples/*.hrma) — manifest ölçüsü kurulamıyor"
fi

manifest_denetle() {   # $1 = app kökü (Resources ya da payload), $2 = ad
    local kok="$1" ad="$2" ornek onderleme_app onderleme_libs
    if [ ! -d "$kok/app" ]; then
        basarisiz "$ad: app/ dizini yok ($kok/app)"
        return
    fi
    ornek="$(find "$kok/app/examples" -maxdepth 1 -name '*.hrma' 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$ornek" = "$REPO_ORNEK" ] && [ "$ornek" -gt 0 ]; then
        basarili "$ad: $ornek örnek proje (.hrma) pakette"
    else
        basarisiz "$ad: örnek proje sayısı $ornek, depoda $REPO_ORNEK — examples/ pakete girmemiş"
    fi
    [ -f "$kok/app/examples/generate_examples.py" ] \
        && basarili "$ad: generate_examples.py pakette (örneklerin kaynağı)" \
        || basarisiz "$ad: generate_examples.py yok — örneklerin nereden geldiği paketten okunamıyor"
    [ -f "$kok/app/launcher.py" ] \
        && basarili "$ad: launcher.py yerinde" \
        || basarisiz "$ad: launcher.py YOK — paket açılamaz"
    [ -f "$kok/app/hrma/app.py" ] \
        && basarili "$ad: hrma/ paketi yerinde" \
        || basarisiz "$ad: hrma/ yok ya da eksik (app.py bulunamadı)"
    [ -d "$kok/app/data" ] \
        && basarili "$ad: data/ yerinde" \
        || basarisiz "$ad: data/ YOK — katalog dosyaları eksik"
    # Ön-derleme: v2.6.25'te sessizce kaybolan şey buydu. Sayı BASILIR ki
    # "var/yok" değil, ne kadar olduğu da kayda geçsin.
    onderleme_app="$(find "$kok/app/hrma" -maxdepth 3 -type d -name '__pycache__' 2>/dev/null | wc -l | tr -d ' ')"
    onderleme_libs="$(find "$kok/libs" -maxdepth 2 -type d -name '__pycache__' 2>/dev/null | wc -l | tr -d ' ')"
    if [ "$onderleme_app" -gt 0 ] && [ "$onderleme_libs" -gt 0 ]; then
        basarili "$ad: bytecode ön-derleme var (hrma $onderleme_app, libs $onderleme_libs __pycache__)"
    else
        basarisiz "$ad: ön-derleme EKSİK (hrma $onderleme_app, libs $onderleme_libs) — ilk açılış dakikalarca sürer"
    fi
}

if [ "$(uname)" != "Darwin" ]; then
    atlandi "DMG içeriği yalnız macOS'ta okunabilir (hdiutil) — Windows payload aşağıda denetlenir"
elif [ ! -f "$DMG_YOL" ]; then
    basarisiz "DMG yok: $DMG_YOL — içerik manifesti denetlenemiyor"
else
    ICERIK_MNT="$(dmg_bagla "$DMG_YOL" || echo '')"
    if [ -z "$ICERIK_MNT" ]; then
        basarisiz "DMG mount edilemedi, içerik denetlenemedi: $DMG_YOL"
    else
        manifest_denetle "$ICERIK_MNT/HRMA.app/Contents/Resources" "DMG içeriği"
        dmg_coz "$ICERIK_MNT"
    fi
fi

# Windows tarafı: exe'nin içi açılamadığı için üretildiği payload ağacı
# denetlenir (aynı kapsam beyanı 3/8 adımında).
if [ -d "packaging/win/payload" ]; then
    manifest_denetle "packaging/win/payload" "Windows payload"
else
    atlandi "packaging/win/payload yok — Windows içerik manifesti denetlenmedi (temiz klon?)"
fi

# --- Boyut sapması ----------------------------------------------------------
# Taban kaynağı BEYAN EDİLİR. Sıra bilinçli:
#   1) packaging/last_release_sizes.json — operatörün depoya YAZDIĞI taban.
#      Büyük ama meşru bir değişiklik (yeni bağımlılık, yeni veri seti) olduğunda
#      kaçış yolu budur: gerekçesiyle birlikte commit edilir, gözden geçirilir.
#      Beklenen biçim:
#        {"tag": "v2.6.25", "dmg_bytes": 546683953, "exe_bytes": 227285327,
#         "_source": "gh release view v2.6.25 --json assets (2026-08-03)",
#         "_note": "neden bu taban"}
#   2) gh api — bir ÖNCEKİ yayının GERÇEK varlık boyutları (ölçülmüş veri).
# İkisi de yoksa sapma DENETLENMEZ ve bu açıkça söylenir; uydurma taban YOK.
TABAN_DOSYA="packaging/last_release_sizes.json"
DMG_TABAN=""; EXE_TABAN=""; TABAN_KAYNAK=""
if [ -f "$TABAN_DOSYA" ]; then
    DMG_TABAN="$("$PY" -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));print(d.get('dmg_bytes') or '')" "$TABAN_DOSYA" 2>/dev/null || echo '')"
    EXE_TABAN="$("$PY" -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));print(d.get('exe_bytes') or '')" "$TABAN_DOSYA" 2>/dev/null || echo '')"
    TABAN_KAYNAK="$TABAN_DOSYA (depoda beyan edilmiş taban)"
elif command -v gh >/dev/null 2>&1; then
    ONCEKI_ETIKET="$(gh release list --limit 20 --json tagName --jq '.[].tagName' 2>/dev/null | grep -vx "v${VERSION}" | head -1 || true)"
    if [ -n "$ONCEKI_ETIKET" ]; then
        ONCEKI_VARLIK="$(gh release view "$ONCEKI_ETIKET" --json assets \
                         --jq '.assets[] | [.name, .size] | @tsv' 2>/dev/null || true)"
        DMG_TABAN="$(printf '%s\n' "$ONCEKI_VARLIK" | awk -F'\t' '$1 ~ /macOS\.dmg$/ {print $2; exit}')"
        EXE_TABAN="$(printf '%s\n' "$ONCEKI_VARLIK" | awk -F'\t' '$1 ~ /\.exe$/ {print $2; exit}')"
        TABAN_KAYNAK="gh api — $ONCEKI_ETIKET yayınının gerçek varlık boyutları"
    fi
fi

if [ -n "$TABAN_KAYNAK" ]; then
    echo "  (boyut tabanı: $TABAN_KAYNAK)"
else
    atlandi "boyut tabanı YOK (ne $TABAN_DOSYA ne gh erişimi) — sapma denetlenmedi"
fi

boyut_karsilastir() {   # $1 = artefakt yolu, $2 = taban bayt, $3 = ad
    local yeni sapma mutlak
    if [ ! -f "$1" ]; then
        basarisiz "$3: artefakt yok ($1) — boyut ölçülemiyor"
        return
    fi
    yeni="$("$PY" -c "import os,sys;print(os.path.getsize(sys.argv[1]))" "$1" 2>/dev/null || echo '')"
    if [ -z "$yeni" ]; then
        basarisiz "$3: boyut okunamadı ($1)"
        return
    fi
    # Taban yalnız SAYIYSA karşılaştırılır; boş/bozuk taban "denetlendi"
    # sayılmaz, açıkça denetlenmedi denir (uydurma taban yok).
    case "${2:-}" in
        ''|*[!0-9]*|0)
            atlandi "$3: $((yeni / 1048576)) MB ölçüldü; geçerli taban olmadığı için sapma DENETLENMEDİ"
            return ;;
    esac
    sapma=$(( (yeni - $2) * 100 / $2 ))
    mutlak="${sapma#-}"
    if [ "$mutlak" -gt "$BOYUT_TOLERANS_YUZDE" ]; then
        basarisiz "$3: $((yeni / 1048576)) MB, taban $(($2 / 1048576)) MB — %${sapma} sapma (sınır ±%${BOYUT_TOLERANS_YUZDE}). İçeriği doğrulayın; sapma meşruysa $TABAN_DOSYA dosyasına gerekçesiyle yeni taban yazın."
    else
        basarili "$3: $((yeni / 1048576)) MB, taban $(($2 / 1048576)) MB — %${sapma} sapma (sınır ±%${BOYUT_TOLERANS_YUZDE})"
    fi
}

boyut_karsilastir "$DMG_YOL" "$DMG_TABAN" "DMG boyutu"
boyut_karsilastir "$EXE_YOL" "$EXE_TABAN" "EXE boyutu"

# ---------------------------------------------------------------------------
printf "\n============================================\n"
if [ "$HATA_SAYISI" -eq 0 ]; then
    printf "${YESIL}KAPI AÇIK${SIFIR} — v%s yayınlanabilir\n" "$VERSION"
    exit 0
fi
printf "${KIRMIZI}KAPI KAPALI${SIFIR} — %d kontrol kaldı. Yayın YOK.\n" "$HATA_SAYISI"
exit 1
