"""ÖH Z5S / P09-D — PDF raporunun BESLEME SÖZLEŞMESİ bekçileri.

Kapsanan defter kalemleri
-------------------------
P9B3-02  Katı motorda yönetici özeti ``Maximum Thrust: 0.0 N`` basıyordu;
         çözücü ``max_thrust = 5162,86`` yayımlıyor, AYNI belgenin tablosu
         "N/A" diyordu (bir büyüklüğe iki farklı cevap).
P9B3-03  Sıvı motorda ``Specific Impulse: 0.0 s``; çözücü
         ``isp_sea_level = 277,33`` yayımlıyor.
P9B3-04  Sıvı motorda özet ``Total Impulse: 3.000.000,0 N⋅s`` UYDURUYORDU
         (``thrust x burn_time``; üstelik ``burn_time`` çözücünün kendi
         varsayımı), tablo aynı büyüklüğe "N/A" diyordu.
P9B3-06  Katı ve sıvı motorda PDF'te YAPISAL BÖLÜM hiç oluşmuyordu; iki
         çözücü de kendi bloğunda gerçek gerilme ve katsayı yayımlıyor.
P9B3-07  Sıvının kütle debisi (``total_mass_flow``) ve O/F oranı
         (``mixture_ratio``) PDF'e hiç girmiyordu: rapor katmanı bu adları
         tanımıyordu.
P9B3-08  Katının tanecik yoğunluğu (``density = 1700``) "N/A kg/m3" idi.
P9B3-25  ``_fmt`` "N/A" dönünce birim yine ekleniyor, hücrede "N/A kg/m3" /
         "N/A kg" / "N/A bar" gibi anlamsız dizeler oluşuyordu.

Yöntem
------
Sayılar UYDURULMAZ: her bekçi GERÇEK çözücü koşumundan gelen yükle çalışır
(``/calculate_solid``, ``/calculate_liquid``) ve raporun bastığı hücreyi
çözücünün AYNI koşumdaki alanına karşı ölçer. İddialar iki katmanda kurulur:
reportlab hikâyesinin hücre değerleri (kesin) ve gerçekten üretilen PDF'in
metni (belgeye indiğinin kanıtı).

Kanıt: docs/scofield/raw/OH/Z5S/p09d/
"""

import contextlib
import io
import re

import pytest

from reportlab.platypus import Table

from hrma.export.pdf_generator import (
    PDFReportGenerator, SOLVER_PERFORMANCE_ALIASES, SOLVER_CONFIG_ALIASES)


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------

def _sessiz(fn):
    """Çözücülerin print gürültüsünü yutar."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn()


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


@pytest.fixture(scope='module')
def kati(client):
    """Katı motorun GERÇEK çözücü yanıtı (cidar HRMA tarafından seçilir)."""
    resp = _sessiz(lambda: client.post('/calculate_solid', json=dict(
        motor_name='Z5S-SOLID', propellant_type='apcp_std', grain_type='bates',
        chamber_pressure=50, burn_time=5.0, thrust=5000)))
    assert resp.status_code == 200, resp.data[:300]
    veri = resp.get_json()
    veri['motor_name'] = 'Z5S-SOLID'
    veri['motor_type'] = 'solid'
    return veri


@pytest.fixture(scope='module')
def kati_dogrulanmis(client):
    """Kullanıcının KENDİ cidarıyla koşan katı motor (kazanılmış SF dalı)."""
    resp = _sessiz(lambda: client.post('/calculate_solid', json=dict(
        motor_name='Z5S-SOLID-V', propellant_type='apcp_std',
        grain_type='bates', chamber_pressure=50, burn_time=5.0, thrust=5000,
        case_thickness=8.0)))
    assert resp.status_code == 200, resp.data[:300]
    veri = resp.get_json()
    veri['motor_name'] = 'Z5S-SOLID-V'
    veri['motor_type'] = 'solid'
    return veri


@pytest.fixture(scope='module')
def sivi(client):
    """Sıvı motorun GERÇEK çözücü yanıtı."""
    resp = _sessiz(lambda: client.post('/calculate_liquid', json=dict(
        motor_name='Z5S-LIQUID', thrust=10000, chamber_pressure=50,
        mixture_ratio=2.3, fuel_type='rp1', oxidizer_type='lox')))
    assert resp.status_code == 200, resp.data[:300]
    veri = resp.get_json()
    veri['motor_name'] = 'Z5S-LIQUID'
    veri['motor_type'] = 'liquid'
    return veri


@pytest.fixture(scope='module')
def sivi_sureli(client):
    """Süresi VERİLMİŞ sıvı motorun gerçek çözücü yanıtı.

    ÖH D36 / LU-1 (ÇEVRİLEN BEKÇİ, onemli2-sivi a2): motor yanma süresini
    artık VARSAYMAZ; süre verilmezse yanıtta ``burn_time`` yoktur.
    ``test_ozet_F_carpi_t_turetmiyor``in niyeti "F ve t VARKEN özet F x t
    türetmez"dir, yani süreli bir tasarımı ölçer. Süre motorun kendi
    sabitinden AÇIKÇA verilir (sayı burada yazılmaz); LU-1 öncesindeki
    sessiz varsayımla aynı sayılar. Süresiz yanıt (``sivi``) diğer
    düğümlerde aynen kalır.
    """
    from hrma.engines.liquid_rocket_engine import BURN_TIME_DEFAULT_S
    resp = _sessiz(lambda: client.post('/calculate_liquid', json=dict(
        motor_name='Z5S-LIQUID', thrust=10000, chamber_pressure=50,
        mixture_ratio=2.3, fuel_type='rp1', oxidizer_type='lox',
        max_burn_duration=BURN_TIME_DEFAULT_S)))
    assert resp.status_code == 200, resp.data[:300]
    veri = resp.get_json()
    veri['motor_name'] = 'Z5S-LIQUID'
    veri['motor_type'] = 'liquid'
    return veri


def _bolumler(motor_data, analysis_results=None):
    """app.py'nin PDF besleyicisinden geçmiş analiz bölümleri."""
    from hrma.app import _build_pdf_analysis_sections
    return _sessiz(lambda: _build_pdf_analysis_sections(
        motor_data, analysis_results or {}))


def _hucreler(story):
    """Hikâyedeki TÜM tablo satırlarını {etiket: [değer, ...]} yapar."""
    out = {}
    for item in story:
        if not isinstance(item, Table):
            continue
        for row in item._cellvalues:
            if not row:
                continue
            etiket = row[0]
            if not isinstance(etiket, str):
                continue
            out.setdefault(etiket, []).append(
                [str(getattr(h, 'text', h)) for h in row[1:]])
    return out


def _paragraflar(story):
    """Hikâyedeki paragraf metinleri (boşluklar teklenmiş)."""
    parcalar = []
    for item in story:
        metin = getattr(item, 'text', None)
        if isinstance(metin, str):
            parcalar.append(re.sub(r'\s+', ' ', metin))
    return parcalar


def _rapor_hikayesi(motor_data, analysis_results=None):
    """(özet paragrafları, yapılandırma hücreleri, sonuç hücreleri)."""
    ar = _bolumler(motor_data, analysis_results)
    gen = PDFReportGenerator()
    ozet = _paragraflar(gen._create_executive_summary(ar, motor_data))
    yapilandirma = _hucreler(gen._create_motor_configuration(motor_data))
    sonuclar = gen._create_analysis_results(ar, motor_data)
    return ozet, yapilandirma, _hucreler(sonuclar), _paragraflar(sonuclar)


def _pdf_metni(client, motor_data, tip='complete'):
    """Uçtan uca üretilen PDF metni (boşluklar teklenmiş)."""
    pypdf = pytest.importorskip('pypdf')
    resp = _sessiz(lambda: client.post(f'/api/export-pdf/{tip}', json={
        'motor_data': motor_data, 'analysis_results': {}, 'charts': []}))
    assert resp.status_code == 200, resp.data[:300]
    okuyucu = pypdf.PdfReader(io.BytesIO(resp.data))
    ham = '\n'.join((s.extract_text() or '') for s in okuyucu.pages)
    return re.sub(r'\s+', ' ', ham)


# ---------------------------------------------------------------------------
# P9B3-02 — katı: özet itkiyi 0 basmıyor, tablo ile AYNI sayıyı veriyor
# ---------------------------------------------------------------------------

class TestP9B302KatiOzetItkisi:

    def test_cozucu_gercekten_max_thrust_yayimliyor(self, kati):
        """Kalemin dayanağı: üst düzeyde 'thrust' YOK, 'max_thrust' VAR."""
        assert 'thrust' not in kati, (
            'çözücü artık üst düzeyde thrust yayımlıyor — kalemin dayanağı '
            'değişti, bekçi gözden geçirilmeli')
        assert float(kati['max_thrust']) > 0.0

    def test_ozet_sifir_basmiyor_ve_gercek_sayiyi_veriyor(self, kati):
        ozet, _yapi, _hucre, _not = _rapor_hikayesi(kati)
        metin = ' '.join(ozet)
        assert 'Maximum Thrust: 0.0 N' not in metin, (
            'eksik alanın karşılığı 0 sayılıyor — sıfır itkili motor belgesi')
        assert 'Maximum Thrust: %.1f N' % kati['max_thrust'] in metin

    def test_tablo_ozetle_ayni_sayiyi_veriyor(self, kati):
        _ozet, _yapi, hucre, _not = _rapor_hikayesi(kati)
        assert hucre['Maximum Thrust'][0][0] == '%.1f' % kati['max_thrust'], (
            'aynı belgede özet ile tablo farklı cevap veriyor')

    def test_uretilen_pdfe_iniyor(self, client, kati):
        metin = _pdf_metni(client, kati)
        assert 'Maximum Thrust: 0.0 N' not in metin
        assert '%.1f' % kati['max_thrust'] in metin


# ---------------------------------------------------------------------------
# P9B3-03 — sıvı: özgül impuls
# ---------------------------------------------------------------------------

class TestP9B303SiviOzgulImpuls:

    def test_cozucu_isp_sea_level_yayimliyor(self, sivi):
        assert 'specific_impulse' not in sivi and 'isp' not in sivi, (
            'çözücü artık specific_impulse/isp yayımlıyor — dayanak değişti')
        assert float(sivi['isp_sea_level']) > 0.0

    def test_ozet_sifir_basmiyor(self, sivi):
        ozet, _yapi, _hucre, _not = _rapor_hikayesi(sivi)
        metin = ' '.join(ozet)
        assert 'Specific Impulse: 0.0 s' not in metin
        assert 'Specific Impulse: %.1f s' % sivi['isp_sea_level'] in metin

    def test_tablo_ozetle_ayni(self, sivi):
        _ozet, _yapi, hucre, _not = _rapor_hikayesi(sivi)
        assert (hucre['Specific Impulse'][0][0]
                == '%.1f' % sivi['isp_sea_level'])

    def test_vakum_ispi_deniz_seviyesi_yerine_GECMIYOR(self, sivi):
        """Alias listesi FARKLI bir büyüklüğü doldurmaya kullanılamaz."""
        assert 'isp_vacuum' not in SOLVER_PERFORMANCE_ALIASES[
            'specific_impulse'], (
            'vakum Isp deniz seviyesi hücresine alias yapılmış — eksik '
            'hücreyi komşu sayıyla doldurmak sıfır basmak kadar yanlış')
        assert 'average_thrust' not in SOLVER_PERFORMANCE_ALIASES['thrust'], (
            'ortalama itki "Maximum Thrust" hücresine alias yapılmış')


# ---------------------------------------------------------------------------
# P9B3-04 — uydurma toplam impuls
# ---------------------------------------------------------------------------

class TestP9B304UydurmaToplamImpuls:

    def test_cozucu_toplam_impuls_yayimlamiyor(self, sivi):
        assert 'total_impulse' not in sivi, (
            'sıvı çözücü artık total_impulse yayımlıyor — dayanak değişti')

    def test_ozet_F_carpi_t_turetmiyor(self, sivi_sureli):
        sivi = sivi_sureli
        ozet, _yapi, _hucre, _not = _rapor_hikayesi(sivi)
        metin = ' '.join(ozet)
        uydurma = float(sivi['thrust']) * float(sivi['burn_time'])
        assert '%.1f' % uydurma not in metin, (
            'toplam impuls itki x yanma süresinden türetilmiş: %s' % uydurma)
        assert 'Total Impulse: N/A' in metin

    def test_birim_sayisiz_yazilmiyor(self, sivi):
        """P9B3-25'in özet ayağı: 'N/A N⋅s' diye bir büyüklük yoktur."""
        ozet, _yapi, _hucre, _not = _rapor_hikayesi(sivi)
        metin = ' '.join(ozet)
        assert 'N/A N' not in metin and 'N/A s' not in metin

    def test_tablo_da_ayni_seyi_soyluyor(self, sivi):
        _ozet, _yapi, hucre, _not = _rapor_hikayesi(sivi)
        assert hucre['Total Impulse'][0][0] == 'N/A'

    def test_gercek_toplam_impuls_varsa_AYNEN_basilir(self, kati):
        """Ölçülmüş değer varsa elbette basılır (fail-closed ≠ sağır)."""
        ozet, _yapi, hucre, _not = _rapor_hikayesi(kati)
        assert 'Total Impulse: %.1f N' % kati['total_impulse'] in ' '.join(ozet)
        assert hucre['Total Impulse'][0][0] == '%.1f' % kati['total_impulse']


# ---------------------------------------------------------------------------
# P9B3-06 — katı/sıvıda yapısal bölüm + kazanılmış SF sözleşmesi
# ---------------------------------------------------------------------------

SF_DOGRULANMIS_SATIR = 'Minimum Safety Factor (verified stations)'
SF_HEDEF_SATIR = 'Design Safety Factor Target (sizing mode)'


class TestP9B306YapisalBolum:

    def test_besleyici_hala_kati_semasini_tanimiyor(self, kati):
        """Kalemin kök sebebi: hazırlanmış 'structural' bloğu BOŞ kalıyor."""
        assert not (_bolumler(kati).get('structural') or {}), (
            'besleyici artık katı şemasını tanıyor — kalem app.py tarafında '
            'çözülmüş olabilir, bekçi gözden geçirilmeli')

    def test_kati_yapisal_bolum_olusuyor(self, kati):
        _ozet, _yapi, hucre, notlar = _rapor_hikayesi(kati)
        ham = kati['structural_analysis']['case_analysis']
        assert 'Hoop Stress (case wall)' in hucre, 'yapısal bölüm hiç yok'
        assert (hucre['Hoop Stress (case wall)'][0][0]
                == '%.2f' % ham['hoop_stress_mpa'])
        assert (hucre['Case Wall Thickness'][0][0]
                == '%.3f' % ham['wall_thickness_mm'])
        assert any('solver basis' in n for n in notlar), (
            'çözücünün kendi künyesi rapora taşınmamış')

    def test_sivi_yapisal_bolum_olusuyor(self, sivi):
        _ozet, _yapi, hucre, notlar = _rapor_hikayesi(sivi)
        ham = sivi['structural_analysis']['chamber_structure']
        assert (hucre['Hoop Stress (chamber wall)'][0][0]
                == '%.2f' % ham['hoop_stress'])
        assert (hucre['Chamber Wall Thickness'][0][0]
                == '%.3f' % ham['wall_thickness'])
        assert any('solver basis' in n for n in notlar)

    def test_kazanilmamis_SF_dogrulanmis_diye_basilmiyor(self, kati, sivi):
        """Z4 sözleşmesi: totolojik katsayı doğrulama olarak basılamaz."""
        for yuk, blok in ((kati, 'case_analysis'),
                          (sivi, 'chamber_structure')):
            ham = yuk['structural_analysis'][blok]
            assert ham['safety_factor_is_tautological'] is True, (
                'fikstür kurulumu bozuk: bu koşumda cidarı HRMA seçmeli')
            _ozet, _yapi, hucre, notlar = _rapor_hikayesi(yuk)
            assert SF_DOGRULANMIS_SATIR not in hucre, (
                '%s: hedefin geri okunması "doğrulanmış minimum" diye '
                'basıldı' % blok)
            assert hucre[SF_HEDEF_SATIR][0][0] == '{:g}'.format(
                float(ham.get('design_safety_factor', ham['safety_factor'])))
            assert any('SIZING mode' in n and 'no verified safety margin' in n
                       for n in notlar), 'boyutlandırma beyanı yok'

    def test_hibritin_uc_istasyonlu_cumlesi_tek_istasyona_yazilmiyor(
            self, kati):
        """Katı yükte boğaz/kapak istasyonu YOK; o cümle burada yanlış olurdu."""
        _ozet, _yapi, _hucre, notlar = _rapor_hikayesi(kati)
        metin = ' '.join(notlar)
        assert 'Wall, throat and head thicknesses' not in metin
        assert 'Case wall was SIZED' in metin

    def test_kullanicinin_cidariyla_SF_KAZANILIYOR(self, kati_dogrulanmis):
        """Ters yön: cidar kullanıcıdansa doğrulanmış minimum BASILIR."""
        ham = kati_dogrulanmis['structural_analysis']['case_analysis']
        assert ham['safety_factor_is_tautological'] is False, (
            'fikstür kurulumu bozuk: case_thickness kabul edilmemiş')
        _ozet, _yapi, hucre, notlar = _rapor_hikayesi(kati_dogrulanmis)
        assert (hucre[SF_DOGRULANMIS_SATIR][0][0]
                == '%.2f' % ham['safety_factor'])
        assert SF_HEDEF_SATIR not in hucre
        assert any('Case wall' in n and 'Verified stations' in n
                   for n in notlar)

    def test_yapisal_yontem_beyani_da_iniyor(self, client, kati):
        """Bölüm basılıyorsa yöntemi ve varsayımları da beyan edilmeli."""
        metin = _pdf_metni(client, kati)
        assert 'Structural Analysis' in metin
        assert 'thin-wall pressure vessel stress relations' in metin
        assert 'Structural: Thin-wall assumption' in metin

    def test_yapisal_veri_yoksa_bolum_HIC_olusmuyor(self, client):
        """Fail-closed: blok yoksa boş bir yapısal bölüm uydurulmaz."""
        metin = _pdf_metni(client, {'motor_name': 'BOS',
                                    'motor_type': 'liquid'})
        assert 'Structural Analysis' not in metin
        assert 'thin-wall pressure vessel stress relations' not in metin


# ---------------------------------------------------------------------------
# P9B3-07 — kütle debisi ve O/F
# ---------------------------------------------------------------------------

class TestP9B307DebiVeOF:

    def test_cozucu_adlari_hala_bunlar(self, sivi):
        assert 'total_mass_flow' in sivi and 'mixture_ratio' in sivi
        for ad in ('mdot_total', 'total_mdot', 'mass_flow_rate', 'of_ratio'):
            assert ad not in sivi, (
                f'çözücü artık {ad} yayımlıyor — dayanak değişti')

    def test_kutle_debisi_tabloya_iniyor(self, sivi):
        _ozet, _yapi, hucre, _not = _rapor_hikayesi(sivi)
        assert (hucre['Mass Flow Rate'][0][0]
                == '%.3f' % sivi['total_mass_flow'])

    def test_of_orani_tabloya_iniyor(self, sivi):
        _ozet, yapi, _hucre, _not = _rapor_hikayesi(sivi)
        assert yapi['O/F Ratio'][0][0] == '%.2f' % sivi['mixture_ratio'], (
            'kullanıcının kendi yazdığı O/F raporda "N/A" görünüyor')

    def test_uretilen_pdfe_iniyor(self, client, sivi):
        metin = _pdf_metni(client, sivi)
        assert 'Mass Flow Rate %.3f' % sivi['total_mass_flow'] in metin
        assert 'O/F Ratio %.2f' % sivi['mixture_ratio'] in metin


# ---------------------------------------------------------------------------
# P9B3-08 — tanecik yoğunluğu
# ---------------------------------------------------------------------------

class TestP9B308TanecikYogunlugu:

    def test_cozucu_density_adiyla_yayimliyor(self, kati):
        assert 'grain_density' not in kati and float(kati['density']) > 0.0

    def test_yogunluk_tabloya_iniyor(self, kati):
        _ozet, yapi, _hucre, _not = _rapor_hikayesi(kati)
        assert yapi['Grain Density'][0][0] == '%.0f kg/m3' % kati['density']

    def test_sivi_yukune_tanecik_satiri_SIZMIYOR(self, sivi):
        """``density`` alias'ı yalnız tanecikli yükte açılan blokta işler."""
        _ozet, yapi, _hucre, _not = _rapor_hikayesi(sivi)
        assert 'Grain Density' not in yapi


# ---------------------------------------------------------------------------
# P9B3-25 — birim yalnız sayı varken yazılır
# ---------------------------------------------------------------------------

class TestP9B325BirimliNA:

    #: "N/A" + BİRİM kalıbı: 'N/A kg', 'N/A kg/m3', 'N/A bar', ...
    #: Parantezli gerekçe ("N/A (not reported by solver)") birim DEĞİLDİR ve
    #: meşrudur: eksik alanın NEDEN eksik olduğunu söyler.
    NA_BIRIMLI = re.compile(r'^N/A\s+(?!\()\S')

    def test_yapilandirma_tablosunda_birimli_NA_yok(self, kati, sivi):
        for yuk in (kati, sivi):
            _ozet, yapi, _hucre, _not = _rapor_hikayesi(yuk)
            kotu = [f'{etiket}: {deger}'
                    for etiket, satirlar in yapi.items()
                    for satir in satirlar for deger in satir
                    if self.NA_BIRIMLI.match(deger)]
            assert not kotu, 'birimli N/A hücresi: %s' % kotu

    def test_hicbir_sey_cozulemeyince_de_birim_eklenmez(self):
        """Ölçüsüz yük: her hücre 'N/A', hiçbirinin yanında birim yok."""
        gen = PDFReportGenerator()
        yapi = _hucreler(gen._create_motor_configuration(
            {'motor_name': 'BOS', 'grain_type': 'bates',
             'oxidizer_type': 'lox'}))
        assert yapi['Grain Density'][0][0] == 'N/A'
        assert yapi['Propellant Mass'][0][0] == 'N/A'
        assert yapi['Chamber Pressure'][0][0] == 'N/A'

    def test_sayi_varsa_birim_KORUNUR(self, kati):
        _ozet, yapi, _hucre, _not = _rapor_hikayesi(kati)
        assert yapi['Propellant Mass'][0][0].endswith(' kg')
        assert yapi['Grain Density'][0][0].endswith(' kg/m3')


# ---------------------------------------------------------------------------
# Çözüm katmanının kendi sözleşmesi (uydurma değer üretmez)
# ---------------------------------------------------------------------------

class TestCozumSozlesmesi:

    def test_bool_ve_gecersiz_sayi_deger_sayilmaz(self):
        kaynak = {'thrust': True, 'max_thrust': float('nan')}
        assert PDFReportGenerator._resolve_performance('thrust', kaynak) is None

    def test_ilk_gecerli_alias_kazanir(self):
        assert PDFReportGenerator._resolve_performance(
            'thrust', {'max_thrust': 5.0}, {'thrust': 9.0}) == 5.0
        assert PDFReportGenerator._resolve_performance(
            'thrust', {}, {'thrust': 9.0}) == 9.0

    def test_alias_tablolari_ayni_buyuklugu_adlandirir(self):
        """Her alias listesi TEK bir büyüklüğün adlarını taşır."""
        yasak = {
            'thrust': ('average_thrust', 'thrust_vacuum'),
            'specific_impulse': ('isp_vacuum', 'isp_vacuum_optimized'),
            'total_impulse': ('total_impulse_vacuum',),
        }
        for alan, yasaklilar in yasak.items():
            for ad in yasaklilar:
                assert ad not in SOLVER_PERFORMANCE_ALIASES[alan], (
                    f'{ad} farklı bir büyüklük, {alan} hücresine konulamaz')
        assert 'oxidizer_density' not in SOLVER_CONFIG_ALIASES['grain_density']

    def test_eksik_deger_icin_sifir_URETILMEZ(self):
        gen = PDFReportGenerator()
        ozet = ' '.join(_paragraflar(gen._create_executive_summary({}, {})))
        for kalip in ('Maximum Thrust: 0.0', 'Specific Impulse: 0.0',
                      'Burn Time: 0.0', 'Total Impulse: 0.0'):
            assert kalip not in ozet, kalip
        assert 'Maximum Thrust: N/A' in ozet
