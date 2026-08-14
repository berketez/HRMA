"""Gök küresinin statik varlıklarının bekçileri (2026-08-14).

Fırlatma sahası küresinin arkasındaki gökyüzü iki dosyaya dayanır:

  1. ``hrma/static/img/milky_way_eso0932a_4096.webp`` — ESO eso0932a
     panoraması, 4096x2048 equirectangular (CC BY 4.0, ESO/S. Brunier).
  2. ``hrma/static/data/bsc5p_stars.bin`` — Yale Bright Star Catalogue 5
     (kamu malı, Hoffleit & Warren 1991) ikili özeti.

İkisini de ``tools/sky_assets/build_sky_assets.py`` üretir.

NEDEN BU DOSYA VAR
------------------
Bu varlıklar depoya konur, pakete rsync ile girer ve tarayıcıda okunur; yani
üç ayrı yerde sessizce kaybolabilir ya da bozulabilirler. Bu testler üç ayrı
arıza sınıfını yakalar:

* **Yokluk.** Varlık silinir/eklenmezse test ATLANMAZ, DÜŞER. Atlanan bir
  test paketleme sırasında hiçbir şey söylemez; oysa dosya yoksa gök küresi
  boş açılır.
* **Bütçe aşımı.** Kurulum paketi zaten yüzlerce MB; doku sessizce büyürse
  (kalite ayarı elle değiştirilir) burada yakalanır.
* **Sessiz bozulma.** İkili katalog ayrıştırılıp değerleri ölçülür. "Dosya
  var ve boyutu makul" yetmez: sütun kayması ya da endian hatası tam
  boyutlu ama anlamsız bir dosya üretir. Bu yüzden test dosyanın İÇİNİ okur
  ve içinde GERÇEK gökyüzü olduğunu — Sirius'un doğru yerde durduğunu —
  sınar.

Testler sahte veri üretmez ve eksik veriyi tolere etmez: varlık yoksa ya da
bozuksa yüksek sesle düşerler.
"""

import math
import pathlib
import struct

from PIL import Image

KOK = pathlib.Path(__file__).resolve().parents[1]
IMG_DIZIN = KOK / 'hrma' / 'static' / 'img'
VERI_DIZIN = KOK / 'hrma' / 'static' / 'data'
KATALOG = VERI_DIZIN / 'bsc5p_stars.bin'
URETICI = KOK / 'tools' / 'sky_assets' / 'build_sky_assets.py'
BELGE = KOK / 'tools' / 'sky_assets' / 'README.md'

#: Üretici WebP yazar; Pillow'da WebP yoksa JPEG'e düşer. İkisi de kabul.
DOKU_ADAYLARI = ('milky_way_eso0932a_4096.webp', 'milky_way_eso0932a_4096.jpg')

DOKU_W, DOKU_H = 4096, 2048
DOKU_TAVAN_BAYT = 3_000_000        # paketleme bütçesi
KATALOG_TAVAN_BAYT = 200_000

MAGIC = b'BSC1'
KAYIT_BAYT = 12                    # 3 x float32
BASLIK_BAYT = 8                    # 4 bayt imza + uint32 N
N_ALT, N_UST = 8500, 9200

#: Ölçülen gerçek: HR 2491 Sirius, J2000. Katalogda bu yıldız DOĞRU yerde
#: olmalı — dosyanın gerçek gökyüzü taşıdığının kanıtı budur.
SIRIUS_RA, SIRIUS_DEC, SIRIUS_VMAG = 101.2871, -16.7161, -1.46


def _doku_yolu():
    """Dokuyu bulur. Yoksa açık hata mesajıyla düşer (atlamaz)."""
    for ad in DOKU_ADAYLARI:
        yol = IMG_DIZIN / ad
        if yol.exists():
            return yol
    raise AssertionError(
        'Samanyolu dokusu yok. Aranan: %s (dizin: %s). Üretmek için: '
        'python3 tools/sky_assets/build_sky_assets.py'
        % (' | '.join(DOKU_ADAYLARI), IMG_DIZIN))


def _katalogu_oku():
    """İkili katalogu ayrıştırır -> (ra, dec, vmag) listesi."""
    assert KATALOG.exists(), (
        'Yıldız katalogu yok: %s. Üretmek için: '
        'python3 tools/sky_assets/build_sky_assets.py' % KATALOG)
    ham = KATALOG.read_bytes()
    assert len(ham) >= BASLIK_BAYT, 'katalog başlığı bile yok (%d bayt)' % len(ham)
    assert ham[:4] == MAGIC, (
        'sihirli imza %r, beklenen %r — dosya BSC ikilisi değil ya da biçim '
        'değişmiş' % (ham[:4], MAGIC))
    n = struct.unpack('<I', ham[4:8])[0]
    beklenen_boyut = BASLIK_BAYT + KAYIT_BAYT * n
    assert len(ham) == beklenen_boyut, (
        'başlık %d kayıt diyor, dosya %d bayt — %d bekleniyordu. Dosya kesik '
        'ya da fazladan veri taşıyor.' % (n, len(ham), beklenen_boyut))
    return [struct.unpack_from('<fff', ham, BASLIK_BAYT + KAYIT_BAYT * i)
            for i in range(n)]


# ---------------------------------------------------------------------------
# 1) Samanyolu dokusu
# ---------------------------------------------------------------------------

def test_doku_var_ve_butce_icinde():
    yol = _doku_yolu()
    boyut = yol.stat().st_size
    assert boyut > 0, '%s boş dosya' % yol.name
    assert boyut <= DOKU_TAVAN_BAYT, (
        '%s %d bayt (%.2f MB) — paketleme tavanı %.1f MB aşıldı'
        % (yol.name, boyut, boyut / 1e6, DOKU_TAVAN_BAYT / 1e6))


def test_doku_tam_2_1_equirectangular():
    """Gök küresi UV eşlemesi 2:1 varsayar; oran bozuksa doku enlemde kayar."""
    yol = _doku_yolu()
    with Image.open(yol) as gorsel:
        genislik, yukseklik = gorsel.size
    assert (genislik, yukseklik) == (DOKU_W, DOKU_H), (
        '%s %dx%d — %dx%d bekleniyordu. Equirectangular eşleme tam 2:1 ve '
        'ikinin kuvveti kenar ister (WebGL1 POT olmayan dokuda mipmap '
        'üretemez).' % (yol.name, genislik, yukseklik, DOKU_W, DOKU_H))
    assert genislik == 2 * yukseklik


def test_doku_yatay_samanyolu_bandi_tasiyor():
    """Dokunun İÇİNDE gerçekten gökyüzü var mı?

    ESO panoraması galaktik koordinatlardadır: galaktik düzlem yatay ve
    görüntünün ortasından geçer. Dolayısıyla en parlak yatay şerit dikey
    ortada olmalıdır. Düz renk, gradyan ya da yanlış görsel bu sınavı geçemez.
    """
    yol = _doku_yolu()
    with Image.open(yol) as gorsel:
        kucuk = gorsel.convert('L').resize((180, 90), Image.BOX)
    piksel = kucuk.load()
    satir_parlaklik = [
        (sum(piksel[x, y] for x in range(180)) / 180.0, y) for y in range(90)
    ]
    en_parlak_satir = max(satir_parlaklik)[1]
    orta_pay = en_parlak_satir / 90.0
    assert 0.40 <= orta_pay <= 0.60, (
        'en parlak yatay şerit yüksekliğin %%%.0f\'inde — galaktik düzlemin '
        'ortada (%%40-%%60) olması bekleniyordu. Doku yanlış görsel ya da '
        'yanlış projeksiyon olabilir.' % (100 * orta_pay))

    en_karanlik = min(satir_parlaklik)[0]
    en_parlak = max(satir_parlaklik)[0]
    assert en_parlak - en_karanlik > 5.0, (
        'görüntüde yatay yapı yok (parlaklık farkı %.2f) — düz renk ya da '
        'gradyan bir dosya konmuş olabilir' % (en_parlak - en_karanlik))


# ---------------------------------------------------------------------------
# 2) Yıldız katalogu
# ---------------------------------------------------------------------------

def test_katalog_var_ve_butce_icinde():
    assert KATALOG.exists(), (
        'Yıldız katalogu yok: %s. Üretmek için: '
        'python3 tools/sky_assets/build_sky_assets.py' % KATALOG)
    boyut = KATALOG.stat().st_size
    assert boyut > 0, '%s boş dosya' % KATALOG.name
    assert boyut <= KATALOG_TAVAN_BAYT, (
        '%s %d bayt (%.1f kB) — tavan %.0f kB'
        % (KATALOG.name, boyut, boyut / 1e3, KATALOG_TAVAN_BAYT / 1e3))


def test_katalog_basligi_ve_kayit_sayisi():
    """İmza + N + dosya boyutu birbirini tutuyor mu?"""
    yildizlar = _katalogu_oku()          # imza ve boyut denetimi içinde
    assert N_ALT <= len(yildizlar) <= N_UST, (
        'katalogda %d yıldız var, beklenen aralık [%d, %d]. BSC5 9110 kayıt '
        'taşır; bunların 14\'ü konumsuz yıldız-olmayan girdidir.'
        % (len(yildizlar), N_ALT, N_UST))


def test_katalog_degerleri_gecerli_aralikta():
    """Her kaydın üç alanı da fiziksel aralıkta ve NaN'sız olmalı.

    Endian hatası, sütun kayması ya da yarım yazılmış dosya burada patlar:
    bozuk float32'ler neredeyse her zaman aralık dışına ya da NaN'a düşer.
    """
    yildizlar = _katalogu_oku()
    for i, (ra, dec, vmag) in enumerate(yildizlar):
        assert not math.isnan(ra), 'kayıt %d: ra NaN' % i
        assert not math.isnan(dec), 'kayıt %d: dec NaN' % i
        assert not math.isnan(vmag), 'kayıt %d: vmag NaN' % i
        assert math.isfinite(ra) and math.isfinite(dec) and math.isfinite(vmag), (
            'kayıt %d: sonsuz değer (%r, %r, %r)' % (i, ra, dec, vmag))
        assert 0.0 <= ra < 360.0, 'kayıt %d: ra %r [0, 360) dışında' % (i, ra)
        assert -90.0 <= dec <= 90.0, 'kayıt %d: dec %r [-90, 90] dışında' % (i, dec)
        assert -2.0 < vmag < 8.0, 'kayıt %d: vmag %r (-2, 8) dışında' % (i, vmag)


def test_katalog_gokyuzune_yayilmis():
    """Yıldızlar tüm gökyüzüne dağılmış olmalı — tek noktada yığılmamalı.

    Kısmi/kesik bir dosya ya da yanlış ölçekleme bu sınavda düşer.
    """
    yildizlar = _katalogu_oku()
    ra_deger = [y[0] for y in yildizlar]
    dec_deger = [y[1] for y in yildizlar]
    assert max(ra_deger) - min(ra_deger) > 350.0, (
        'sağ açıklık yayılımı yalnız %.1f derece — katalog kesik olabilir'
        % (max(ra_deger) - min(ra_deger)))
    assert min(dec_deger) < -80.0 and max(dec_deger) > 80.0, (
        'dik açıklık [%.1f, %.1f] — iki gök kutbu da örneklenmemiş'
        % (min(dec_deger), max(dec_deger)))


def test_katalog_sirius_u_dogru_yerde_tasiyor():
    """Gerçeklik kanıtı: gökyüzünün en parlak yıldızı doğru koordinatta mı?

    Bu test uydurma/prosedürel bir yıldız alanının geçemeyeceği tek testtir:
    rastgele üretilmiş bir dosyada V=-1.46'lık bir yıldızın tam olarak
    Sirius'un J2000 konumunda bulunması beklenemez.
    """
    yildizlar = _katalogu_oku()
    en_parlak = min(yildizlar, key=lambda y: y[2])
    ra, dec, vmag = en_parlak
    assert abs(vmag - SIRIUS_VMAG) < 0.02, (
        'katalogun en parlak yıldızı V=%.2f — Sirius (V=%.2f) bekleniyordu'
        % (vmag, SIRIUS_VMAG))
    assert abs(ra - SIRIUS_RA) < 0.01 and abs(dec - SIRIUS_DEC) < 0.01, (
        'en parlak yıldız (%.4f, %.4f) konumunda — Sirius (%.4f, %.4f) '
        'bekleniyordu. Sütun kayması ya da birim hatası olabilir.'
        % (ra, dec, SIRIUS_RA, SIRIUS_DEC))


# ---------------------------------------------------------------------------
# 3) Köken ve atıf: varlıkların nereden geldiği depodan okunabilmeli
# ---------------------------------------------------------------------------

def test_uretici_betik_yerinde():
    assert URETICI.exists(), (
        'üretici betik yok: %s — varlıklar yeniden üretilemez hale gelir'
        % URETICI)


def test_atif_ve_lisans_kayitli():
    """CC BY 4.0 atıf yükümlülüğü depoda YAZILI olmalı.

    ESO görseli atıf şartıyla kullanılabiliyor; atfın nerede durduğu
    unutulursa lisans ihlali sessizce oluşur.
    """
    assert BELGE.exists(), 'kaynak/lisans kaydı yok: %s' % BELGE
    metin = BELGE.read_text(encoding='utf-8').casefold()
    for beklenen in ('ESO/S. Brunier', 'CC BY 4.0', 'eso0932a',
                     'Hoffleit', 'kamu malı'):
        assert beklenen.casefold() in metin, (
            '%s içinde %r geçmiyor — varlığın kökeni/lisansı eksik kayıtlı'
            % (BELGE.name, beklenen))

    betik_metni = URETICI.read_text(encoding='utf-8')
    assert 'ESO/S. Brunier' in betik_metni, (
        'üretici betik atfı taşımıyor — dosya tek başına dolaşırsa kaynağı '
        'kaybolur')
