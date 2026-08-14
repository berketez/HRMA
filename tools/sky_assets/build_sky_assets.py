#!/usr/bin/env python3
"""Gök küresinin (fırlatma sahası görünümündeki yıldızlı arka plan) iki statik
varlığını kaynağından yeniden üretir.

Üretilenler
-----------
1) hrma/static/img/milky_way_eso0932a_4096.webp
   ESO "The Milky Way panorama" (GigaGalaxy Zoom, eso0932a), 6000x3000
   kaynaktan 4096x2048'e (tam 2:1) yeniden örneklenir.
   Kaynak sayfa : https://www.eso.org/public/images/eso0932a/
   Dosya        : https://cdn.eso.org/images/large/eso0932a.jpg
   Atıf         : ESO/S. Brunier
   Lisans       : Creative Commons Attribution 4.0 International (CC BY 4.0),
                  https://creativecommons.org/licenses/by/4.0/
                  (ESO telif politikası: https://www.eso.org/public/outreach/copyright/
                  "ESO images ... are released under the Creative Commons
                  Attribution 4.0 International License")

   İKİ ÖLÇÜ ŞART:
   * Tam 2:1 en-boy oranı — küre UV eşlemesi equirectangular varsayar; oran
     bozuksa doku enlemde kayar.
   * İkinin kuvveti kenar (4096x2048) — WebGL1 (three.js r128) POT olmayan
     dokuda mipmap üretemez, dokuyu çalışma anında yeniden ölçekler.

   DİKKAT — KOORDİNAT SİSTEMİ: Bu panorama GALAKTİK koordinatlardadır
   (galaktik düzlem yatay, merkez görüntünün ortasında; ESO sayfasının kendi
   ifadesi: "the Galactic Plane running horizontally through the image").
   Aşağıda üretilen yıldız katalogu ise J2000 EKVATORYAL (RA/Dec). İkisi aynı
   equirectangular eşlemeyle üst üste konursa yıldızlar Samanyolu bandına
   OTURMAZ. Bağlayan taraf ya yıldızları galaktik çerçeveye döndürmeli ya da
   doku küresine sabit bir dönüşüm uygulamalıdır. Bu betik dönüşümü
   uygulamaz — ham veriyi ham haliyle verir.

2) hrma/static/data/bsc5p_stars.bin
   Yale Bright Star Catalogue, 5. gözden geçirilmiş baskı (BSC5 / V-50).
   Kaynak       : http://tdc-www.harvard.edu/catalogs/bsc5.dat.gz
   Biçim belgesi: http://tdc-www.harvard.edu/catalogs/ybsc5.readme
   Künye        : Hoffleit D., Warren Jr W.H., "The Bright Star Catalogue,
                  5th Revised Ed. (Preliminary Version)", Astronomical Data
                  Center, NSSDC/ADC (1991). Bibcode 1964BS....C......0H
   Lisans       : KAMU MALI (ADC/CDS kataloğu, telif kısıtı yok)

İkili dosya biçimi (little-endian, JS tarafı DataView ile okuyacak)
------------------------------------------------------------------
    ofset  tip        alan
    0      4 bayt     sihirli imza: b'BSC1' (0x42 0x53 0x43 0x31)
    4      uint32     N — kayıt sayısı
    8      N x 12 bayt kayıt, her kayıt sırayla:
             +0   float32   ra_deg   — J2000 sağ açıklık, derece, [0, 360)
             +4   float32   dec_deg  — J2000 dik açıklık, derece, [-90, +90]
             +8   float32   vmag     — görsel kadir (V), küçük = parlak

    Toplam boyut = 8 + 12*N bayt. Başlıkta sürüm alanı YOKTUR; biçim
    değişirse sihirli imza b'BSC2' olmalıdır ki eski okuyucu sessizce yanlış
    ayrıştırmasın.

Kaynak kataloğun sütunları (ybsc5.readme, "Byte-by-byte Description of file:
catalog" bölümünden BİREBİR alındı; 1'den başlayan sütun numaraları):
     76- 77  I2   RAh    J2000 saat        |     84     A1  DE-   işaret
     78- 79  I2   RAm    J2000 dakika      |  85- 86  I2  DEd   derece
     80- 83  F4.1 RAs    J2000 saniye      |  87- 88  I2  DEm   yay dakikası
    103-107  F5.2 Vmag   görsel kadir      |  89- 90  I2  DEs   yay saniyesi

Ayıklama doğrulaması (ezberi değil dosyayı ölçmek için): HR 2491 (Sirius)
kaydı 06h45m08.9s / -16d42'58" / V=-1.46 vermelidir. Betik bunu koşum
sırasında sınar; tutmazsa sütunlar kaymıştır ve üretim DURUR.

Kaç yıldız? — ÖLÇÜLEN GERÇEK
----------------------------
Katalogda 9110 kayıt var; bunların 14'ü yıldız değil (1908 derlemesindeki
nova/galaksi girdileri, numaralandırma korunsun diye tutulmuş) ve konum/kadir
alanları BOŞ. Geriye konumu ve V kadiri ölçülmüş 9096 yıldız kalıyor.

BSC'nin NOMİNAL sınırı V=6,5'tir ama dosyanın kendisi V=7,96'ya kadar yıldız
taşır: V>6,5 olan 692 gerçek yıldız vardır. Bu yüzden 6,5'te kesmek katalogu
9096'dan 8404'e düşürür, yani ölçülmüş 692 yıldızı atar. Gök küresi için
kazanç yok (692 kayıt = 8,1 kB), kayıp var. Bu yüzden ``VMAG_SINIR`` kataloğun
gerçek en sönük değerinin üstüne kurulur ve konumu+kadiri olan HER yıldız
yazılır. Betik iki sayıyı da (6,5 altı / sınır altı) koşum günlüğüne basar ki
tercih görünür olsun.

Belirlenimlilik: aynı girdi -> aynı çıktı. Dosyalara zaman damgası, rastgele
tohum ya da sözlük sırası girmez; yıldızlar katalog sırasında (HR numarası)
yazılır. Doku baytları Pillow/libwebp sürümüne bağlıdır — koşum günlüğünde
sürüm ve SHA-256 basılır.

Kullanım:
    python3 tools/sky_assets/build_sky_assets.py

    Ham indirmeler ``/tmp/hrma_sky_assets`` altında önbelleklenir (depo içine
    ASLA yazılmaz). Başka bir dizin için: HRMA_SKY_CACHE=/yol/dizin

DÜRÜSTLÜK KURALI: İndirme başarısız olursa bu betik prosedürel yıldız alanı ya
da gradyan doku ÜRETMEZ. Yüksek sesle durur (sıfırdan farklı çıkış kodu) ve
hangi adımda ne olduğunu söyler. Yarı üretilmiş varlık bırakmaz.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import struct
import sys
import urllib.request
from pathlib import Path

# --- Yollar -----------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
IMG_DIR = REPO / 'hrma' / 'static' / 'img'
DATA_DIR = REPO / 'hrma' / 'static' / 'data'
CACHE = Path(os.environ.get('HRMA_SKY_CACHE', '/tmp/hrma_sky_assets'))

# --- Kaynaklar --------------------------------------------------------------
SAMANYOLU_URL = 'https://cdn.eso.org/images/large/eso0932a.jpg'
SAMANYOLU_SAYFA = 'https://www.eso.org/public/images/eso0932a/'
BSC5_URL = 'http://tdc-www.harvard.edu/catalogs/bsc5.dat.gz'
BSC5_README_URL = 'http://tdc-www.harvard.edu/catalogs/ybsc5.readme'

# İndirilen yanıtın gerçekten veri olduğunu kanıtlayan alt sınırlar. Hata
# sayfası birkaç kB gelir; bu eşikler onu veri sanmayı imkânsız kılar.
SAMANYOLU_EN_AZ_BAYT = 4_000_000
BSC5_EN_AZ_BAYT = 400_000

# İçerik türü değil, dosyanın İLK BAYTLARI denetlenir: sunucu yanlış
# Content-Type gönderse bile sihirli baytlar yalan söylemez.
JPEG_IMZA = b'\xff\xd8\xff'
GZIP_IMZA = b'\x1f\x8b'

# --- Doku ölçütleri ---------------------------------------------------------
DOKU_W, DOKU_H = 4096, 2048
WEBP_KALITE = 80          # ölçüldü: 1,54 MB (hedef <= 2,0 MB)
JPEG_KALITE = 85          # Pillow'da WebP yoksa yedek yol
DOKU_TAVAN_BAYT = 3_000_000   # paketleme bütçesi — aşılırsa üretim durur

# --- Katalog ölçütleri ------------------------------------------------------
#: Yazılacak en sönük yıldız. Kataloğun ölçülmüş en sönük değeri V=7,96'dır;
#: sınır onun üstüne kurulur, yani konumu+kadiri olan her yıldız girer.
#: Ayrıntılı gerekçe için modül başlığındaki "Kaç yıldız?" bölümüne bakın.
VMAG_SINIR = 8.0
#: Kataloğun kendi nominal parlaklık sınırı — yalnız günlüğe basmak için.
BSC_NOMINAL_SINIR = 6.5
#: Beklenen kayıt sayısı aralığı. Dışına çıkarsa ayrıştırma bozulmuştur.
BEKLENEN_ARALIK = (8500, 9200)

MAGIC = b'BSC1'

# ybsc5.readme'deki 1-tabanlı sütunların 0-tabanlı dilim karşılıkları.
S_RAH = slice(75, 77)
S_RAM = slice(77, 79)
S_RAS = slice(79, 83)
S_DE_ISARET = slice(83, 84)
S_DED = slice(84, 86)
S_DEM = slice(86, 88)
S_DES = slice(88, 90)
S_VMAG = slice(102, 107)
SATIR_UZUNLUGU = 197

#: Sütun hizasının kanıtı: HR 2491 = Sirius (ölçülen J2000 değerleri).
SIRIUS = {'hr': '2491', 'ra_deg': 101.2871, 'dec_deg': -16.7161, 'vmag': -1.46}


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _sha256(yol: Path) -> str:
    ozet = hashlib.sha256()
    with open(yol, 'rb') as f:
        for parca in iter(lambda: f.read(1 << 20), b''):
            ozet.update(parca)
    return ozet.hexdigest()


def _indir(url: str, hedef: Path, en_az_bayt: int, imza: bytes) -> Path:
    """İndirir ve İNDİRDİĞİNİ KANITLAR: HTTP kodu, boyut, sihirli baytlar.

    Üçünden biri tutmazsa dosyayı SİLER ve yükselir — yarım/yanlış bir dosyanın
    önbellekte kalıp sonraki koşumda "geçerli" sayılması engellenir.
    """
    hedef.parent.mkdir(parents=True, exist_ok=True)
    if hedef.exists() and hedef.stat().st_size >= en_az_bayt:
        print('    önbellek: %s (%.2f MB)'
              % (hedef.name, hedef.stat().st_size / 1e6))
        return hedef

    print('    indiriliyor: %s' % url)
    istek = urllib.request.Request(url, headers={'User-Agent': 'HRMA-sky-asset-builder'})
    with urllib.request.urlopen(istek, timeout=300) as yanit:
        kod = yanit.status
        icerik_tipi = yanit.headers.get('Content-Type', '?')
        veri = yanit.read()
    boyut = len(veri)
    print('    HTTP %s | %s | %d bayt (%.2f MB)'
          % (kod, icerik_tipi, boyut, boyut / 1e6))

    if kod != 200:
        raise RuntimeError('%s -> HTTP %s (200 bekleniyordu)' % (url, kod))
    if boyut < en_az_bayt:
        raise RuntimeError(
            '%s -> yalnız %d bayt geldi, en az %d bekleniyordu. Bu büyüklük '
            'veri değil hata sayfasıdır; SAHTE VARLIK ÜRETİLMEYECEK.'
            % (url, boyut, en_az_bayt))
    if not veri.startswith(imza):
        raise RuntimeError(
            '%s -> dosyanın ilk baytları %r, beklenen imza %r. Sunucu veri '
            'yerine başka bir şey döndürdü.' % (url, veri[:8], imza))

    hedef.write_bytes(veri)
    return hedef


# ---------------------------------------------------------------------------
# 1) Samanyolu dokusu
# ---------------------------------------------------------------------------

def dokuyu_uret() -> Path:
    from PIL import Image, features

    kaynak = _indir(SAMANYOLU_URL, CACHE / 'eso0932a_large.jpg',
                    SAMANYOLU_EN_AZ_BAYT, JPEG_IMZA)

    with Image.open(kaynak) as ham:
        gorsel = ham.convert('RGB')
        g_w, g_h = gorsel.size
        print('    kaynak: %dx%d (oran %.4f)' % (g_w, g_h, g_w / g_h))

        # Tam 2:1 şartı. Kaynak zaten 6000x3000; değilse ORANI BOZMADAN
        # ortadan kırparak 2:1'e getir (yeniden ölçekleme enlemde kayma
        # yaratırdı, kırpma yalnız kenardan gök alanı eksiltir).
        if g_w != 2 * g_h:
            if g_w > 2 * g_h:
                yeni_w = 2 * g_h
                sol = (g_w - yeni_w) // 2
                gorsel = gorsel.crop((sol, 0, sol + yeni_w, g_h))
                print('    2:1 için yatay kırpma -> %dx%d' % gorsel.size)
            else:
                yeni_h = g_w // 2
                ust = (g_h - yeni_h) // 2
                gorsel = gorsel.crop((0, ust, g_w, ust + yeni_h))
                print('    2:1 için dikey kırpma -> %dx%d' % gorsel.size)

        kucuk = gorsel.resize((DOKU_W, DOKU_H), Image.LANCZOS)

    IMG_DIR.mkdir(parents=True, exist_ok=True)
    webp_var = features.check('webp')
    if webp_var:
        hedef = IMG_DIR / 'milky_way_eso0932a_4096.webp'
        kucuk.save(hedef, 'WEBP', quality=WEBP_KALITE, method=6)
        etiket = 'WebP q=%d' % WEBP_KALITE
    else:
        hedef = IMG_DIR / 'milky_way_eso0932a_4096.jpg'
        kucuk.save(hedef, 'JPEG', quality=JPEG_KALITE, optimize=True)
        etiket = 'JPEG q=%d (Pillow WebP desteklemiyor)' % JPEG_KALITE

    boyut = hedef.stat().st_size
    print('    yazıldı: %s' % hedef.relative_to(REPO))
    print('    %s | %d bayt (%.3f MB) | SHA-256 %s'
          % (etiket, boyut, boyut / 1e6, _sha256(hedef)[:16]))

    if boyut > DOKU_TAVAN_BAYT:
        hedef.unlink()
        raise RuntimeError(
            'doku %d bayt (%.2f MB) — paketleme tavanı %d bayt (%.1f MB) '
            'aşıldı, dosya silindi. Kaliteyi düşürün.'
            % (boyut, boyut / 1e6, DOKU_TAVAN_BAYT, DOKU_TAVAN_BAYT / 1e6))

    # Geri oku: yazdığımız dosya gerçekten açılıyor ve 2:1 mi?
    with Image.open(hedef) as geri:
        if geri.size != (DOKU_W, DOKU_H):
            raise RuntimeError('geri okuma %s verdi, %dx%d bekleniyordu'
                               % (geri.size, DOKU_W, DOKU_H))
    print('    geri okuma: %dx%d, oran %.1f:1 — TAMAM'
          % (DOKU_W, DOKU_H, DOKU_W / DOKU_H))
    return hedef


# ---------------------------------------------------------------------------
# 2) BSC5 yıldız katalogu
# ---------------------------------------------------------------------------

def _satiri_coz(satir: str):
    """Bir katalog satırından (ra_deg, dec_deg, vmag) çıkarır.

    Konum ya da kadir alanı boşsa None döner — katalogdaki 14 yıldız-olmayan
    girdi (nova/galaksi) tam olarak böyle işaretlidir.
    """
    satir = satir.ljust(SATIR_UZUNLUGU)
    rah = satir[S_RAH].strip()
    vmag_ham = satir[S_VMAG].strip()
    if not rah or not vmag_ham:
        return None

    ra_saat = int(rah)
    ra_dakika = int(satir[S_RAM].strip() or 0)
    ra_saniye = float(satir[S_RAS].strip() or 0.0)
    ra_deg = (ra_saat + ra_dakika / 60.0 + ra_saniye / 3600.0) * 15.0

    isaret = -1.0 if satir[S_DE_ISARET] == '-' else 1.0
    dec_derece = int(satir[S_DED].strip() or 0)
    dec_dakika = int(satir[S_DEM].strip() or 0)
    dec_saniye = int(satir[S_DES].strip() or 0)
    dec_deg = isaret * (dec_derece + dec_dakika / 60.0 + dec_saniye / 3600.0)

    return ra_deg, dec_deg, float(vmag_ham)


def _sirius_denetimi(kayitlar_hr: dict) -> None:
    """Sütun hizası kanıtı. Tutmazsa katalog biçimi değişmiştir; DUR."""
    olculen = kayitlar_hr.get(SIRIUS['hr'])
    if olculen is None:
        raise RuntimeError('HR %s (Sirius) katalogda bulunamadı — ayrıştırma '
                           'bozuk' % SIRIUS['hr'])
    ra, dec, vmag = olculen
    sapma_ra = abs(ra - SIRIUS['ra_deg'])
    sapma_dec = abs(dec - SIRIUS['dec_deg'])
    print('    hiza kanıtı HR 2491 (Sirius): RA %.4f deg (sapma %.4f), '
          'Dec %.4f deg (sapma %.4f), V %.2f'
          % (ra, sapma_ra, dec, sapma_dec, vmag))
    if sapma_ra > 0.01 or sapma_dec > 0.01 or abs(vmag - SIRIUS['vmag']) > 0.01:
        raise RuntimeError(
            'Sirius denetimi TUTMADI: ölçülen (%.4f, %.4f, %.2f), beklenen '
            '(%.4f, %.4f, %.2f). Sütunlar kaymış — üretim durduruldu.'
            % (ra, dec, vmag, SIRIUS['ra_deg'], SIRIUS['dec_deg'],
               SIRIUS['vmag']))


def katalogu_uret() -> Path:
    gz_yol = _indir(BSC5_URL, CACHE / 'bsc5.dat.gz', BSC5_EN_AZ_BAYT, GZIP_IMZA)
    metin = gzip.decompress(gz_yol.read_bytes()).decode('latin-1')
    satirlar = [s for s in metin.split('\n') if s]
    print('    katalog: %d satır' % len(satirlar))

    yildizlar = []
    hr_dizini = {}
    konumsuz = 0
    nominal_alti = 0
    for satir in satirlar:
        cozum = _satiri_coz(satir)
        if cozum is None:
            konumsuz += 1
            continue
        ra, dec, vmag = cozum
        hr_dizini[satir[:4].strip()] = cozum
        if vmag <= BSC_NOMINAL_SINIR:
            nominal_alti += 1
        if vmag <= VMAG_SINIR:
            yildizlar.append(cozum)

    print('    konum/kadir alanı boş (yıldız olmayan girdi): %d' % konumsuz)
    print('    V <= %.1f (kataloğun nominal sınırı): %d yıldız'
          % (BSC_NOMINAL_SINIR, nominal_alti))
    print('    V <= %.1f (yazılan sınır): %d yıldız'
          % (VMAG_SINIR, len(yildizlar)))
    _sirius_denetimi(hr_dizini)

    n = len(yildizlar)
    if not BEKLENEN_ARALIK[0] <= n <= BEKLENEN_ARALIK[1]:
        raise RuntimeError(
            'yıldız sayısı %d, beklenen aralık %s dışında — ayrıştırma ya da '
            'kaynak değişmiş olabilir; SAHTE VERİ ÜRETİLMEYECEK.'
            % (n, BEKLENEN_ARALIK))

    # Aralık denetimi: küre üstünde çizilmeden ÖNCE.
    for ra, dec, vmag in yildizlar:
        if not 0.0 <= ra < 360.0:
            raise RuntimeError('RA aralık dışı: %r' % ra)
        if not -90.0 <= dec <= 90.0:
            raise RuntimeError('Dec aralık dışı: %r' % dec)

    govde = bytearray()
    govde += MAGIC
    govde += struct.pack('<I', n)
    for ra, dec, vmag in yildizlar:
        govde += struct.pack('<fff', ra, dec, vmag)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    hedef = DATA_DIR / 'bsc5p_stars.bin'
    hedef.write_bytes(bytes(govde))
    boyut = hedef.stat().st_size
    print('    yazıldı: %s' % hedef.relative_to(REPO))
    print('    %d yıldız | %d bayt (%.1f kB) | SHA-256 %s'
          % (n, boyut, boyut / 1e3, _sha256(hedef)[:16]))

    if boyut != 8 + 12 * n:
        raise RuntimeError('boyut tutmuyor: %d != %d' % (boyut, 8 + 12 * n))

    # Geri oku ve float32'ye yuvarlandıktan SONRAKİ değerleri doğrula. RA'nın
    # 360'a yuvarlanması (float32 hassasiyeti) tam da burada yakalanır.
    ham = hedef.read_bytes()
    if ham[:4] != MAGIC:
        raise RuntimeError('geri okuma: sihirli imza %r' % ham[:4])
    geri_n = struct.unpack('<I', ham[4:8])[0]
    if geri_n != n:
        raise RuntimeError('geri okuma: N %d != %d' % (geri_n, n))
    ra_min = dec_min = vmag_min = float('inf')
    ra_maks = dec_maks = vmag_maks = float('-inf')
    for i in range(geri_n):
        ra, dec, vmag = struct.unpack_from('<fff', ham, 8 + 12 * i)
        if not 0.0 <= ra < 360.0 or not -90.0 <= dec <= 90.0:
            raise RuntimeError('geri okuma %d: (%r, %r) aralık dışı' % (i, ra, dec))
        if ra != ra or dec != dec or vmag != vmag:      # NaN denetimi
            raise RuntimeError('geri okuma %d: NaN' % i)
        ra_min, ra_maks = min(ra_min, ra), max(ra_maks, ra)
        dec_min, dec_maks = min(dec_min, dec), max(dec_maks, dec)
        vmag_min, vmag_maks = min(vmag_min, vmag), max(vmag_maks, vmag)
    print('    geri okuma: RA [%.4f, %.4f] | Dec [%.4f, %.4f] | V [%.2f, %.2f]'
          % (ra_min, ra_maks, dec_min, dec_maks, vmag_min, vmag_maks))
    return hedef


# ---------------------------------------------------------------------------

def main() -> int:
    import PIL
    print('HRMA gök küresi varlıkları')
    print('  depo      : %s' % REPO)
    print('  önbellek  : %s' % CACHE)
    print('  Pillow    : %s | Python %s'
          % (PIL.__version__, sys.version.split()[0]))
    print()
    print('1) Samanyolu dokusu (ESO eso0932a, CC BY 4.0, ESO/S. Brunier)')
    doku = dokuyu_uret()
    print()
    print('2) Yıldız katalogu (Yale BSC5, kamu malı, Hoffleit & Warren 1991)')
    katalog = katalogu_uret()
    print()
    print('TAMAM — iki varlık da üretildi:')
    for yol in (doku, katalog):
        print('  %-46s %9d bayt  %s'
              % (yol.relative_to(REPO), yol.stat().st_size, _sha256(yol)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
