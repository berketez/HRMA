"""ÖH D22 · altyapi a1 — onarım bekçileri.

Her sınıf bir defter kalemine bağlıdır ve o kalemin kusurunu GÖREN bir
sınama içerir. Bekçilerin tamamı ters-mutasyonla kanıtlandı
(``docs/scofield/raw/OH/D22/altyapi/a1/mutasyon.json``): onarım geçici
olarak geri alınınca ilgili sınıf KIRMIZI olur.

Kalemler:

* **P10B3-07** — ``start.sh`` "Python 3.7+" diyordu, kendi kapısı 3.10
  istiyordu. Sürüm sayıları artık tek kaynaktan (``PY_MIN_MINOR`` /
  ``PY_MAX_MINOR``) okunuyor ve ``python3`` dalı da sınanıyor.
* **P10B3-12** — tuval/egzoz eşikleri canlı ölçümün 20 katı altındaydı;
  %2,1 dolu + 1,1 bitlik yer tutucu ve 900→1'e düşen egzoz geçiyordu.
* **P10B3-16** — ``vacuum_isp_ratio`` oda basıncını hiç almıyordu ve
  ``gamma`` süs parametreydi; artık izentropik Cf oranı, Pc zorunlu ve
  ayrılmış akışta sayı YAYIMLANMIYOR.
* **OH-Z5-08** — ``iddia_lint`` üç desen sınıfını görmüyordu.
* **OH-Z5-13** — denetim/çapa betikleri kalıcı kullanıcı deposuna
  yazabiliyordu; izolasyon modülü + süreç kuralı.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile

import pytest
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


# ===========================================================================
# P10B3-07 — start.sh sürüm kapısı ⟷ hata metni
# ===========================================================================
class TestP10B307StartShSurumKapisi:
    """Betiğin SÖYLEDİĞİ sürüm ile UYGULADIĞI sürüm aynı olmalı."""

    @pytest.fixture(scope='class')
    def metin(self):
        return (KOK / 'start.sh').read_text(encoding='utf-8')

    def test_hata_metni_gercek_kapiyi_soyler(self, metin):
        """"Python 3.7+" gibi kapıdan DÜŞÜK bir sayı hiçbir yerde geçmez.

        Kusur: kullanıcı 3.7 kurup geri geliyor, ikinci kapı onu geri
        çeviriyordu — bir tur kayıp.
        """
        alt = int(re.search(r'^PY_MIN_MINOR=(\d+)', metin, re.M).group(1))
        anilan = {int(mn) for mj, mn in
                  re.findall(r'Python\s+(\d+)\.(\d+)', metin) if mj == '3'}
        # Yorum satırları kusuru ANLATIYOR olabilir; yalnız kullanıcıya
        # basılan (echo) satırlara bakılır.
        basilan = set()
        for satir in metin.splitlines():
            s = satir.strip()
            if s.startswith('#') or 'echo' not in s:
                continue
            for mj, mn in re.findall(r'Python\s+(\d+)\.(\d+)', s):
                if mj == '3':
                    basilan.add(int(mn))
        dusuk = {x for x in basilan if x < alt}
        assert not dusuk, (
            'start.sh kullanıcıya kapıdan DÜŞÜK sürüm söylüyor: %s '
            '(gerçek kapı 3.%d)' % (sorted(dusuk), alt))
        assert anilan, 'sürüm hiç anılmıyor — metin bozulmuş olabilir'

    def test_surum_esikleri_tek_kaynaktan(self, metin):
        """version_info eşiği de, -lt kapısı da PY_MIN_MINOR'dan okunur."""
        assert re.search(r'version_info\s*>=\s*\(\$\{PY_MIN_MAJOR\},'
                         r'\$\{PY_MIN_MINOR\}\)', metin), (
            'python -c sürüm sınaması çıplak sayı kullanıyor; tek kaynak yok')
        assert re.search(r'"\$PYMIN"\s*-lt\s*"\$PY_MIN_MINOR"', metin), (
            'alt kapı çıplak sayı kullanıyor')
        assert not re.search(r'version_info\s*>=\s*\(\s*3\s*,\s*7\s*\)',
                             metin), 'eski 3.7 eşiği geri gelmiş'

    def test_python3_dalinda_da_surum_sinaniyor(self, metin):
        """``python3`` bulundu diye koşulsuz kabul edilmez.

        Eski hâlde ``command -v python3`` başarılıysa sürüm HİÇ sınanmıyordu;
        hüküm tamamen aşağıdaki ikinci kapıya bırakılmıştı.
        """
        assert re.search(r'for\s+cmd\s+in\s+python3\s+python', metin), (
            'aday döngüsü yok — python3 dalı sürümsüz kabul ediliyor olabilir')

    def test_betik_sozdizimi_gecerli(self):
        r = subprocess.run(['bash', '-n', str(KOK / 'start.sh')],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr


# ===========================================================================
# P10B3-12 — görsel kapı eşikleri canlı ölçüme kalibre
# ===========================================================================
class TestP10B312GorselEsikler:
    """Eşikler GERİLEMEYİ görmeli, yalnız "hiç çizilmedi mi"yi değil.

    Dayanak: depoda duran 6 canlı tur raporunun 14 sayfa ölçümü —
    dolu oran 0,4119..0,4933 · entropi 3,383..3,863 bit · egzoz
    aralığı 14/14 gözlemde 900.
    """

    #: P10B3-12'de ölçülen YER TUTUCU: %2,1 dolu, 1,1 bit entropi.
    YER_TUTUCU_DOLU_ORAN = 0.021
    YER_TUTUCU_ENTROPI = 1.1
    #: Canlı ölçümlerin EN KÜÇÜĞÜ (gerçek sahne geçmeye devam etmeli).
    CANLI_EN_KUCUK_DOLU_ORAN = 0.4119
    CANLI_EN_KUCUK_ENTROPI = 3.383
    CANLI_CIZIM_ARALIGI = 900

    @pytest.fixture(scope='class')
    def E(self):
        from tools.browser_harness import esikler
        return esikler

    def test_yer_tutucu_tuval_kalir(self, E):
        assert self.YER_TUTUCU_DOLU_ORAN < E.TUVAL_MIN_DOLU_ORAN, (
            '%%2,1 dolu yer tutucu doluluk eşiğinden geçiyor (eşik %r)'
            % E.TUVAL_MIN_DOLU_ORAN)
        assert self.YER_TUTUCU_ENTROPI < E.TUVAL_MIN_ICERIK_ENTROPI_BIT, (
            '1,1 bitlik yer tutucu entropi eşiğinden geçiyor (eşik %r)'
            % E.TUVAL_MIN_ICERIK_ENTROPI_BIT)

    def test_gercek_sahne_gecer(self, E):
        """Eşik yükseldi diye canlı ölçüm kırmızıya düşmemeli."""
        assert E.TUVAL_MIN_DOLU_ORAN <= self.CANLI_EN_KUCUK_DOLU_ORAN, (
            'doluluk eşiği canlı en küçüğün ÜSTÜNDE — kapı haksız kırmızı')
        assert E.TUVAL_MIN_ICERIK_ENTROPI_BIT <= self.CANLI_EN_KUCUK_ENTROPI, (
            'entropi eşiği canlı en küçüğün ÜSTÜNDE — kapı haksız kırmızı')
        assert E.PLUME_MIN_CIZIM_ARALIGI <= self.CANLI_CIZIM_ARALIGI

    def test_egzoz_gerilemesi_yakalanir(self, E):
        """900'den 1'e düşen egzoz artık KALIR (eski eşikte geçiyordu)."""
        assert E.PLUME_MIN_CIZIM_ARALIGI > 1, (
            'egzoz eşiği 1 — 900 parçacıktan 1 parçacığa gerileme geçer')
        assert 1 < E.PLUME_MIN_CIZIM_ARALIGI <= self.CANLI_CIZIM_ARALIGI


# ===========================================================================
# P10B3-16 — vacuum_isp_ratio oda basıncını görür
# ===========================================================================
class TestP10B316VakumIspOrani:
    """Oran Pc'ye bağlıdır; fonksiyon Pc'yi almadan sayı yayımlayamaz."""

    #: Ham raporun ÖLÇTÜĞÜ (eps, Pc[bar], gerçek oran) — γ=1,22, izentropik
    #: Cf, yalnız ayrılmasız (Pe/Pa ≥ 0,4) noktalar.
    REFERANS = ((10, 50, 1.1326), (10, 100, 1.0622), (10, 300, 1.0199),
                (25, 150, 1.1020), (25, 300, 1.0485))

    @pytest.fixture(scope='class')
    def fn(self):
        from hrma.constants import vacuum_isp_ratio
        return vacuum_isp_ratio

    def test_oda_basinci_olmadan_sayi_yayimlanmaz(self, fn):
        """FAIL-CLOSED: sessiz varsayılan Pc uydurulmaz."""
        with pytest.raises(ValueError, match='(?i)basinc') as hata:
            fn(25.0, 1.22)
        assert 'basinc' in str(hata.value).lower()  # fix-19 (ÖK-22 nüfus tavanı)

    @pytest.mark.parametrize('eps,pc,gercek', REFERANS)
    def test_referans_noktalari_yeniden_uretilir(self, fn, eps, pc, gercek):
        """Eski ampirik fit bu noktalarda −%7,6..+%3,3 sapıyordu."""
        v = fn(eps, 1.22, pc)
        sapma = 100.0 * abs(v - gercek) / gercek
        assert sapma < 0.05, (
            'eps=%s Pc=%s bar: %.5f, gerçek %.4f (sapma %%%.3f)'
            % (eps, pc, v, gercek, sapma))

    def test_oran_oda_basinciyla_degisir(self, fn):
        """Aynı eps'te Pc 50→300 bar oranı belirgin değiştirmeli.

        Eski fonksiyon üçüne de 1,0464 diyordu.
        """
        dusuk = fn(10, 1.22, 50.0)
        yuksek = fn(10, 1.22, 300.0)
        assert dusuk > yuksek, 'oran Pc ile azalmalı (basınç-itki terimi)'
        assert (dusuk - yuksek) / yuksek > 0.05, (
            'Pc duyarlılığı %%%.2f — fonksiyon Pc körü olabilir'
            % (100 * (dusuk - yuksek) / yuksek))

    def test_gamma_sus_parametre_degil(self, fn):
        """Eski gövdede γ 1,15→1,30 sonucu %%0,069 değiştiriyordu."""
        a = fn(10, 1.15, 100.0)
        b = fn(10, 1.30, 100.0)
        duyarlilik = 100.0 * abs(b - a) / a
        assert duyarlilik > 0.2, (
            'gamma duyarlılığı %%%.3f — süs parametre' % duyarlilik)

    def test_ayrilmis_akista_sayi_yayimlanmaz(self, fn):
        """Pe/Pa < 0,4'te tam dolu lüle Cf'i ortam itkisini temsil etmez."""
        with pytest.raises(ValueError, match='(?i)ayrilmis') as hata:
            fn(80.0, 1.22, 20.0)
        assert 'ayr' in str(hata.value).lower()  # fix-19: iddiasız nüfus tavanı (ÖK-22)

    def test_bozuk_girdi_fail_closed(self, fn):
        with pytest.raises(ValueError) as h1:
            fn(1.0, 1.22, 50.0)          # eps <= 1
        with pytest.raises(ValueError) as h2:
            fn(10.0, 1.22, 0.0)          # Pc <= 0
        assert str(h1.value) and str(h2.value)  # fix-19: ret gerekçeli (ÖK-22 nüfus tavanı)


# ===========================================================================
# OH-Z5-08 — iddia_lint desen boşluğu
# ===========================================================================
class TestOHZ508IddiaLintDesenleri:
    """Üç desen sınıfı: TR '-doğrulanmıştır', 'CFD-verified', 'complies with'."""

    POZITIF = (
        ('TR-dogrulanmistir-1', 'Boğaz akışı CFD ile doğrulanmıştır.'),
        ('TR-dogrulanmistir-2', 'Bu değer deneysel ölçümlerle doğrulanmıştır.'),
        ('TR-dogrulanmistir-3', 'Sonuçlar NASA CEA ile doğrulanmıştır.'),
        ('EN-cfd-verified-1',
         'The CFD-verified nozzle contour is shipped by default.'),
        ('EN-cfd-verified-2', 'A CFD verified expansion ratio is used here.'),
        ('EN-complies-1', 'This vessel complies with NFPA 30 standard.'),
        ('EN-complies-2',
         'The design complies with ASME BPVC standard requirements.'),
        ('EN-complies-3', 'Tank spacing complies with the NFPA 55 standard.'),
        ('EN-complies-4', 'Piping complies with ISO 4126 standard.'),
    )
    NEGATIF = (
        ('neg-1', 'The CFD solver did not converge; no verdict is published.'),
        ('neg-2', 'Bu değer doğrulanmamıştır ve yayımlanmaz.'),
        ('neg-3', 'Compliance with NFPA 30 is NOT checked by any code path.'),
        ('neg-4', 'We list which standard titles are verified in docs/.'),
        ('neg-5', 'CFD mesh study pending; verification not attempted.'),
        ('neg-6', 'Doğrulama kampanyası koşmuyor.'),
    )

    @staticmethod
    def _tara(metin):
        from tools import iddia_lint
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False,
                                         encoding='utf-8') as fh:
            fh.write(metin)
            yol = fh.name
        try:
            return [b.rule_id for b in iddia_lint.scan_file(pathlib.Path(yol))]
        finally:
            os.unlink(yol)

    @pytest.mark.parametrize('ad,metin', POZITIF)
    def test_pozitif_korpus_yakalanir(self, ad, metin):
        assert self._tara(metin), '%s kaçtı: %r' % (ad, metin)

    @pytest.mark.parametrize('ad,metin', NEGATIF)
    def test_negatif_korpusta_yanlis_isabet_yok(self, ad, metin):
        assert not self._tara(metin), '%s yanlış isabet: %r' % (ad, metin)

    def test_ucu_de_ayri_kurallardan_gelir(self):
        """Tek geniş desen değil, üç adlandırılmış kural."""
        from tools import iddia_lint
        adlar = {r.rule_id for r in iddia_lint.ALL_RULES}
        for beklenen in ('dogrulanmistir_tr', 'cfd_verified_sifat',
                         'complies_with_standard'):
            assert beklenen in adlar, '%s kuralı yok' % beklenen

    def test_kapi_kayitsiz_isabetle_kirmizi_kalmiyor(self):
        """Yeni kurallar ağaçta kayıtsız isabet BIRAKMAMALI.

        Kural eklemek kapıyı gürültüyle kırmızıya çevirirse araç kullanılmaz
        hâle gelir; 10 gerçek isabetin 10'u kayıt defterine gerekçesiyle
        işlendi (3'ü AÇIK BORÇ olarak).
        """
        r = subprocess.run([sys.executable, str(KOK / 'tools' / 'iddia_lint.py'),
                            '--check'], capture_output=True, text=True,
                           cwd=str(KOK), timeout=600)
        assert 'kayıtsız 0' in r.stdout, r.stdout[-600:]


# ===========================================================================
# OH-Z5-13 — denetim betiği izolasyonu
# ===========================================================================
class TestOHZ513Izolasyon:
    """Denetim betiği ölçtüğü sistemi DEĞİŞTİRMEMELİ."""

    @pytest.fixture
    def izo(self):
        kanit_gerekli(KOK / 'docs' / 'scofield' / 'betikler' / 'izolasyon.py')
        sys.path.insert(0, str(KOK))
        from docs.scofield.betikler import izolasyon
        return izolasyon

    def test_modul_ve_surec_kurali_var(self):
        assert (kanit_gerekli(KOK / 'docs' / 'scofield' / 'betikler'
                / 'izolasyon.py')).exists()
        assert (kanit_gerekli(KOK / 'docs' / 'scofield' / 'betikler'
                / 'SUREC_KURALI.md')).exists()

    def test_ortam_degiskenleri_gecici_dizine_baglanir(self, izo, tmp_path):
        onceki = {ad: os.environ.get(ad)
                  for ad in izo.IZOLE_EDILEN_DEGISKENLER}
        try:
            kunye = izo.izole_et('bekci', taban_dizin=str(tmp_path))
            for ad in izo.IZOLE_EDILEN_DEGISKENLER:
                assert os.environ[ad].startswith(str(tmp_path)), ad
                assert os.path.isdir(os.environ[ad]), ad
            assert kunye['korunan_gercek_dizin'] != kunye['kok']
        finally:
            for ad, deger in onceki.items():
                if deger is None:
                    os.environ.pop(ad, None)
                else:
                    os.environ[ad] = deger

    def test_gercek_kullanici_dizini_override_dinlemez(self, izo, tmp_path):
        """Korunan dizin, ortam değişkeni ayarlıyken bile GERÇEK dizindir."""
        eski = os.environ.get('HRMA_USER_DATA_DIR')
        os.environ['HRMA_USER_DATA_DIR'] = str(tmp_path)
        try:
            assert izo.gercek_kullanici_dizini() != str(tmp_path)
            assert 'HRMA' in izo.gercek_kullanici_dizini()
        finally:
            if eski is None:
                os.environ.pop('HRMA_USER_DATA_DIR', None)
            else:
                os.environ['HRMA_USER_DATA_DIR'] = eski

    def test_kalici_iz_gorulur(self, izo, tmp_path):
        """Denetim, bilerek bırakılan bir izi GÖRMELİ (aksi hâlde işe yaramaz).

        F2a sondasının bıraktığı "webapi:spacex" kaydının sınıfı budur.
        """
        sahte_gercek = tmp_path / 'sahte-kullanici'
        sahte_gercek.mkdir()
        kunye = {'korunan_gercek_dizin': str(sahte_gercek),
                 'gercek_dizin_parmak_izi_once': izo.parmak_izi(
                     str(sahte_gercek))}
        assert izo.kalici_iz_var_mi(kunye)['iz_birakti'] is False
        (sahte_gercek / 'offline_cache.json').write_text(
            '{"webapi:spacex": 1}', encoding='utf-8')
        sonuc = izo.kalici_iz_var_mi(kunye)
        assert sonuc['iz_birakti'] is True, sonuc

    def test_kapsam_beyani_gercegi_soyler(self, izo):
        """Sözleşmeye bağlı OLMAYAN dosyalar envanterde ADIYLA duruyor.

        İzolasyon her yazma sitesini kapsamaz; kapsamadığını saklamak
        kusuru gizlemek olurdu.
        """
        assert izo.SOZLESMEYE_BAGLI_OLMAYANLAR, 'envanter boş'
        for yol in izo.SOZLESMEYE_BAGLI_OLMAYANLAR:
            assert (KOK / yol).exists(), '%s envanterde ama ağaçta yok' % yol
            metin = (KOK / yol).read_text(encoding='utf-8')
            assert 'HRMA_USER_DATA_DIR' not in metin, (
                '%s artık sözleşmeye bağlı — envanterden çıkarılmalı' % yol)
