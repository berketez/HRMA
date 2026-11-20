"""V307/SEKME-MOTOR — motor sayfası ve teknik PDF'te çelişen sayılar.

Kalem 1 (NK3-H-2): hibrit Teknik PDF'in yapısal manşeti ekranın Performans
Özeti kartıyla AYNI sayıyı, aynı belirleyen istasyonu ve aynı kazanılmışlık
durumunu taşır. Mühendis turunda (9 Kas, L1) PDF "En Düşük Emniyet
Katsayısı (doğrulanmış istasyonlar) 5,12" basıyordu; ekran "kazanılmış
asgari EK yayımlanmadı · belirleyen istasyon uç kapak 4,00" diyordu. 5,12
lülenin imalat asgari kalınlığının belirlediği (HRMA'nın seçtiği) kesitti,
doğrulanmış değil.

Fikstürler GERÇEK ``StructuralAnalyzer`` koşumlarıdır (elle sözlük yok);
lüle kesiti hibrit motorun geçirdiği biçimde (HRMA boyutlandırdı, imalat
tabanı 1,0 mm) verilir.
"""
import io
import math
import warnings

import pytest

# Ekran kartının künye cümleleri (i18n_common.js app.metric.* EN) — PDF
# künyesi AYNI metinlerden kurulur.
EKRAN_BELIRLEYEN = 'Governing station(s): {list}'
EKRAN_KAZANILMIS_YOK = ('Large number = smallest safety factor across '
                        'stations; no EARNED (verified) minimum safety factor '
                        'is published')
EKRAN_HUKUM_YOK = 'Safety factor the verdict rests on: not published'

DOGRULANMIS_SATIR = 'Minimum Safety Factor (verified stations)'
MANSET_SATIR = 'Structural Min SF'

#: Mühendis turu L1'in yapısal girdisi (hibrit 300 N / 20 bar, SS304,
#: cidar boş; boğaz Ø12 mm, lüle kabuğu iç yarıçapı 7 mm, 1,0 mm imalat
#: tabanı). Sayılar L1 yanıtının ``structural_analysis`` bloğundan.
L1_MOTOR = {
    'chamber_pressure': 20.0, 'chamber_diameter': 0.0298,
    'chamber_length': 0.34, 'throat_diameter': 0.012, 'burn_time': 4.7,
    'nozzle_type': 'conical', 'thrust': 300.0,
}


def _yapisal(**ek):
    from hrma.analysis.structural_analysis import StructuralAnalyzer
    motor = dict(L1_MOTOR)
    motor.update(ek)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return StructuralAnalyzer().analyze_structure(
            motor, material='ss_304', design_safety_factor=4.0,
            actual_throat_thickness=0.001,
            nozzle_thickness_sized_by_hrma=True,
            nozzle_minimum_thickness=0.001, nozzle_shell_inner_radius=0.007)


@pytest.fixture(scope='module')
def l1_ham():
    """Soğuk cidar: lüle imalat tabanında, kalan istasyonlar hedefi okur."""
    return _yapisal()


@pytest.fixture(scope='module')
def sicak_ham():
    """Sıcak cidar (700 K): kamara hedefin ALTINA düşer — ölçülmüş eksik."""
    return _yapisal(wall_temperature_hot=700.0, wall_temperature_cold=650.0)


def _pdf_metni(ham, dil='en'):
    from hrma.export import rapor_sozluk
    from hrma.export.pdf_generator import PDFReportGenerator
    pypdf = pytest.importorskip('pypdf')
    safety = ham['safety_analysis']
    chamber = ham['chamber_analysis']
    motor_data = {
        'motor_name': 'V307_SEKME_MOTOR', 'chamber_diameter': 29.8,
        'chamber_length': 340.0, 'throat_diameter': 12.0,
        'exit_diameter': 24.0, 'structural_analysis': ham,
    }
    analysis_results = {'structural': {
        'safety_factor_pressure': chamber.get('hoop_safety_factor'),
        'safety_factor_total': chamber.get('von_mises_safety_factor'),
        'min_safety_factor': safety.get('minimum_safety_factor'),
        'status': safety.get('status'),
        'risk_level': safety.get('risk_level'),
    }}
    uretici = PDFReportGenerator(lang=dil)   # uç (/api/export-pdf) yolu
    with rapor_sozluk.cevrilmeyen_kaydi() as cevrilmeyen:
        veri = uretici.generate_quick_summary_report(motor_data,
                                                     analysis_results)
    okuyucu = pypdf.PdfReader(io.BytesIO(veri))
    metin = '\n'.join(s.extract_text() for s in okuyucu.pages)
    # Satır sarmalarını tek boşluğa indir (etiket/değer araması için).
    return ' '.join(metin.split()), cevrilmeyen


def _sayi_sonra(metin, etiket):
    i = metin.find(etiket)
    if i < 0:
        return None
    return metin[i + len(etiket):].split()[0]


class TestK1PdfYapisalManset:
    """NK3-H-2 — PDF manşeti = ekran kartı (sayı + istasyon + durum)."""

    def test_fikstur_l1_desenini_kuruyor(self, l1_ham):
        s = l1_ham['safety_analysis']
        assert s['stations_governed_by_minimum_thickness'] == ['nozzle']
        assert s['verified_stations'] == []
        assert s['minimum_earned_safety_factor'] is None
        assert s['binding_safety_factors'] == ['end_cap']
        # Ekranın eski PDF'le çeliştiği koşul: keskin harita lüleyi
        # "hedefi okumuyor" diye işaretler.
        assert s['safety_factor_is_tautological']['nozzle'] is False

    def test_lule_dogrulanmis_minimum_diye_basilmaz(self, l1_ham):
        metin, _ = _pdf_metni(l1_ham)
        lule = l1_ham['safety_analysis']['safety_factors']['nozzle']
        assert DOGRULANMIS_SATIR not in metin, (
            'çözücü hiçbir istasyonu doğrulanmış saymıyor '
            '(verified_stations boş) ama PDF doğrulanmış minimum bastı')
        # Lülenin sayısı kendi adıyla durur.
        etiket = ('Safety Factor, nozzle (manufacturing minimum thickness '
                  'governs)')
        assert etiket in metin
        assert _sayi_sonra(metin, etiket) == f'{lule:.2f}'

    def test_manset_ekranla_ayni_sayi(self, l1_ham):
        metin, _ = _pdf_metni(l1_ham)
        s = l1_ham['safety_analysis']
        assert _sayi_sonra(metin, MANSET_SATIR) == \
            f"{s['minimum_safety_factor']:.2f}"

    def test_kunye_ekran_cumleleriyle(self, l1_ham):
        metin, _ = _pdf_metni(l1_ham)
        assert EKRAN_BELIRLEYEN.format(list='end cap') in metin
        assert EKRAN_KAZANILMIS_YOK in metin
        assert EKRAN_HUKUM_YOK in metin

    def test_her_istasyon_hedefi_okur_cumlesi_yanlis_yerde_yok(self, l1_ham):
        metin, _ = _pdf_metni(l1_ham)
        assert 'Every station therefore returns that target back' not in metin
        assert 'SIZING mode' in metin

    def test_tr_belge_ekranin_turkcesini_tasir(self, l1_ham):
        metin, cevrilmeyen = _pdf_metni(l1_ham, 'tr')
        assert 'Yapısal Asgari EK' in metin
        assert 'Belirleyen istasyon(lar): uç kapak' in metin
        assert 'imalat asgari kalınlığı belirledi' in metin
        assert 'doğrulanmış istasyonlar' not in metin
        yeni = [c for c in cevrilmeyen if any(
            k in c for k in ('Safety Factor', 'manufacturing', 'SIZED',
                             'verification', 'Structural Min SF',
                             'allowance'))]
        assert yeni == [], f'çevrilmeyen yeni metin: {yeni}'

    def test_hedefin_altina_dusen_istasyon_kendi_adiyla(self, sicak_ham):
        s = sicak_ham['safety_analysis']
        assert s['verified_stations'] == []
        assert 'chamber_hoop' in s['verdict_scope']
        metin, _ = _pdf_metni(sicak_ham)
        assert DOGRULANMIS_SATIR not in metin
        etiket = ('Safety Factor, chamber hoop stress (HRMA-sized wall, '
                  'below the design target)')
        assert _sayi_sonra(metin, etiket) == \
            f"{s['safety_factors']['chamber_hoop']:.2f}"
        assert _sayi_sonra(metin, MANSET_SATIR) == \
            f"{s['minimum_safety_factor']:.2f}"
        assert 'Every station therefore returns that target back' not in metin

    def test_kullanici_cidari_dogrulanmis_minimum_kazanilmisla_ayni(self):
        """Kullanıcı cidarı verince doğrulanmış satır = kazanılmış asgari."""
        from hrma.analysis.structural_analysis import StructuralAnalyzer
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            ham = StructuralAnalyzer().analyze_structure(
                dict(L1_MOTOR), material='ss_304', design_safety_factor=4.0,
                actual_wall_thickness=0.003, actual_throat_thickness=0.001,
                nozzle_thickness_sized_by_hrma=True,
                nozzle_minimum_thickness=0.001,
                nozzle_shell_inner_radius=0.007)
        kazanilmis = ham['safety_analysis']['minimum_earned_safety_factor']
        assert kazanilmis is not None and math.isfinite(kazanilmis)
        metin, _ = _pdf_metni(ham)
        assert _sayi_sonra(metin, DOGRULANMIS_SATIR) == f'{kazanilmis:.2f}'
        assert ('Minimum earned safety factor: %.2f' % kazanilmis) in metin


# ---------------------------------------------------------------------------
# Kalem 4 (DİL-HİBRİT §8.1): Kütle Akısı ve Daralma Oranı her yanma tipinde
# hesaba girer -> her tipte görünür.
# ---------------------------------------------------------------------------
import os
import re
from html.parser import HTMLParser

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _oku(yol):
    with open(os.path.join(KOK, yol), encoding='utf-8') as f:
        return f.read()


class _Ataci(HTMLParser):
    """Bir id'li öğenin ata zincirini (etiket, öznitelikler) toplar."""

    BOS = {'input', 'br', 'img', 'meta', 'link', 'hr', 'source', 'col',
           'area', 'base', 'wbr', 'embed', 'param', 'track'}

    def __init__(self, hedefler):
        super().__init__()
        self.yigin = []
        self.hedefler = set(hedefler)
        self.zincir = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id') in self.hedefler:
            self.zincir[a['id']] = list(self.yigin)
        if tag not in self.BOS:
            self.yigin.append((tag, a))

    def handle_endtag(self, tag):
        for i in range(len(self.yigin) - 1, -1, -1):
            if self.yigin[i][0] == tag:
                del self.yigin[i:]
                break


class TestK4KutleAkisiGorunurlugu:
    """Sunucu iki alanı HER yanma tipinde okur; form da her tipte gösterir.

    Sunucu ölçümü (olcum/k4_sunucu.json, L1, sonsuz alanlı yanma): kütle
    akısı 0 -> 500 port çapını 22,33 -> 18,70 mm değiştirir; daralma oranı
    4 yakınsak konturu 6,19 -> 4,00 yapar. Eskiden iki alan yalnız sonlu
    tipte görünüyordu.
    """

    def test_sunucu_her_tipte_okur(self):
        app_py = _oku('hrma/app.py')
        # Üç hibrit ucunda da koşulsuz okunuyor (yanma tipine bakılmıyor).
        assert app_py.count(
            "initial_gox=data.get('mass_flux_chamber') or None") == 3
        motor = _oku('hrma/engines/hybrid_rocket_engine.py')
        # Daralma oranı lüle tasarımına her tipte geçer.
        assert 'contraction_area_ratio=_cr' in motor

    def test_iki_alan_gizli_kutuda_degil(self):
        html = _oku('hrma/templates/advanced.html')
        p = _Ataci(['mass_flux_chamber', 'contraction_ratio'])
        p.feed(html)
        assert set(p.zincir) == {'mass_flux_chamber', 'contraction_ratio'}
        for alan, zincir in p.zincir.items():
            for tag, a in zincir:
                stil = (a.get('style') or '').replace(' ', '').lower()
                assert 'display:none' not in stil, (alan, tag, a)
                assert a.get('id') != 'finite_combustion_params', alan
        assert 'finite_combustion_params"' not in html
        assert 'updateCombustionParams' not in html
        assert 'updateFiniteParams' not in html

    def test_bos_alan_beyansiz_sifira_dusmez(self):
        html = _oku('hrma/templates/advanced.html')
        assert "mass_flux_chamber: numById('mass_flux_chamber')" in html
        assert re.search(r"mass_flux_chamber[^\n]*\|\|\s*0", html) is None
        # Boş anahtar gövdeden düşer (null gönderilmez).
        blok = html[html.index('const NUMBYID_ALANLARI'):]
        blok = blok[:blok.index('];')]
        assert "'mass_flux_chamber'" in blok

    def test_istemcide_sahte_birini_doldur_kurali_yok(self):
        js = _oku('hrma/static/js/app.js')
        assert 'app.val.finiteBoth' not in js
        assert 'app.val.finiteNone' not in js
        i18n = _oku('hrma/static/js/i18n_advanced.js')
        assert 'clears and disables' not in i18n
        assert 'temizler ve kapatır' not in i18n
        assert 'fillOnlyOneParameterOther' not in i18n


# ---------------------------------------------------------------------------
# Kalem 2 (NK3-K-7) + Kalem 5 (KATI-DOĞRULAMA D4): katı Performans Özeti
# kartları ortamını ve sürenin tanımını adıyla söyler.
# ---------------------------------------------------------------------------
def _sozluk_iki_dilde(dosya, anahtar):
    metin = _oku(dosya)
    return len(re.findall(r"^\s*'" + re.escape(anahtar) + r"': '", metin,
                          re.M)) == 2


class TestK2KatiTestOrtami:
    """Test irtifasında ortama bağlı kartlar ortamını adıyla söyler."""

    ANAHTARLAR = (
        'solid.msg.average_thrust_test_ambient',
        'solid.msg.peak_thrust_test_ambient',
        'solid.msg.total_impulse_test_ambient',
        'solid.msg.thrust_coefficient_test_ambient',
        'solid.msg.total_impulse_sea_level',
        'solid.msg.total_impulse_sea_level_separated',
        'solid.msg.sea_level_isp_separated',
        'solid.msg.sea_level_separated_note',
    )

    def test_anahtarlar_iki_dilde(self):
        for a in self.ANAHTARLAR:
            assert _sozluk_iki_dilde('hrma/static/js/i18n_pages.js', a), a

    def test_kartlar_cozucunun_alanlarini_okur(self):
        html = _oku('hrma/templates/solid.html')
        bas = html.index('function displayResults(results)')
        govde = html[bas:html.index('const fmtMetric', bas)]
        # Ortam yalnız çözücünün beyanından (design_ambient.is_sea_level).
        assert "_da.is_sea_level === false" in govde
        # Deniz seviyesi impulsu çözücünün alanı; burada türetilmez.
        assert '_da.total_impulse_sea_level_ns' in govde
        assert 'sea_level_flow_separated' in govde
        for a in self.ANAHTARLAR[:5]:
            assert a in govde, a
        # İtki/impuls/C_F test ortamındayken etiketsiz basılamaz: dört kartın
        # her biri aynı satırda ortamlı adı _testOrtami'ye bağlar.
        for a in ('solid.msg.average_thrust', 'solid.msg.peak_thrust',
                  'solid.msg.total_impulse', 'solid.msg.thrust_coefficient'):
            satir = [s for s in govde.splitlines() if f"T('{a}'," in s]
            assert len(satir) == 1, (a, satir)
            assert f"_testOrtami ? T('{a}_test_ambient'," in satir[0], a


class TestK5KatiYanmaSuresiTanimi:
    """Yayımlanan süre et tükenme süresi; ekran kartı ve PDF aynı adı taşır."""

    def test_kart_adi_ve_ipucu(self):
        assert _sozluk_iki_dilde('hrma/static/js/i18n_pages.js',
                                 'solid.msg.burn_time_web')
        assert _sozluk_iki_dilde('hrma/static/js/i18n_pages.js',
                                 'solid.tip.burn_time_web')
        html = _oku('hrma/templates/solid.html')
        assert "T('solid.msg.burn_time_web', 'Burn Time (web burnout)')" in html
        assert "tip: 'solid.tip.burn_time_web'" in html
        assert 'HRMAHelp.html(m.tip, m.tipEn)' in html
        sozluk = _oku('hrma/static/js/i18n_pages.js')
        assert "'solid.msg.burn_time_web': 'Yanma Süresi (et tükenişi)'" in sozluk

    @staticmethod
    def _teknik_pdf(motor_type, dil='en'):
        from hrma.export.pdf_generator import PDFReportGenerator
        pypdf = pytest.importorskip('pypdf')
        motor = {'motor_name': 'V307_SURE', 'motor_type': motor_type,
                 'thrust': 15074.0, 'specific_impulse': 224.7,
                 'burn_time': 2.032, 'total_impulse': 29906.0,
                 'chamber_pressure': 70.0}
        veri = PDFReportGenerator(lang=dil).generate_motor_analysis_report(
            motor, {}, [], 'technical')
        metin = '\n'.join(s.extract_text() for s in
                          pypdf.PdfReader(io.BytesIO(veri)).pages)
        return ' '.join(metin.split())

    def test_pdf_kati_ayni_ad_ve_tanim(self):
        metin = self._teknik_pdf('solid')
        assert 'Burn Time (web burnout) 2.0' in metin
        assert 'Web burnout time: from ignition until the propellant web' \
            in metin
        tr = self._teknik_pdf('solid', 'tr')
        assert 'Yanma Süresi (et tükenişi)' in tr
        assert 'Et tükenme süresi' in tr

    def test_pdf_hibrit_adi_degismez(self):
        metin = self._teknik_pdf('hybrid')
        assert 'web burnout' not in metin
        assert 'Burn Time 2.0' in metin


# ---------------------------------------------------------------------------
# Kalem 3 (DİL-HİBRİT §8.2): İrtifa Profili sekmesi gösterdiğini yapar.
# ---------------------------------------------------------------------------
HIBRIT_GOVDE = {
    'motor_name': 'V307-PROFIL', 'atmospheric_pressure': 1.01325,
    'of_ratio': 7.06, 'chamber_pressure': 20, 'thrust': 300,
    'burn_time': 4.7, 'calculate_trajectory': False,
    'include_plots': False, 'generate_cad': False,
    'nozzle_type': 'conical', 'combustion_type': 'infinite',
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o', 'oxidizer_phase': 'liquid',
    'oxidizer_temp': 293, 'injector_type': 'showerhead',
}


def _hibrit(**ek):
    from hrma.app import app
    govde = dict(HIBRIT_GOVDE)
    govde.update(ek)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        with app.test_client() as c:
            r = c.post('/calculate', json=govde)
    return r.status_code, r.get_json()


@pytest.fixture(scope='module')
def profil_deniz():
    durum, y = _hibrit(altitude_profile={'start': 0, 'end': 20000,
                                         'points': 5})
    assert durum == 200, y
    return y['motor']


@pytest.fixture(scope='module')
def profil_10km():
    # V307/İRTİFA-TEK: form 10 km'nin basıncını GEOMETRİK okumayla gönderir
    # (altitudeToPressure; eski isa_pressure(10000) = 26 436,27 Pa, yeni
    # isa_pressure_geometric(10000) = 26 499,90 Pa).
    from hrma.constants import isa_pressure_geometric, BAR_PER_PA
    durum, y = _hibrit(atmospheric_pressure=isa_pressure_geometric(10000)
                       * BAR_PER_PA,
                       altitude_profile={'start': 10000, 'end': 0,
                                         'points': 6})
    assert durum == 200, y
    return y['motor']


class TestK3IrtifaProfili:

    @pytest.mark.parametrize('ham, alan, neden', [
        ({'start': 0, 'end': 0, 'points': 5}, 'altitude_profile.end',
         'equal_to_start'),
        ({'start': -1, 'end': 10, 'points': 5}, 'altitude_profile.start',
         'out_of_range'),
        ({'start': 0, 'end': 60000, 'points': 5}, 'altitude_profile.end',
         'out_of_range'),
        ({'start': 0, 'end': 10, 'points': 2.5}, 'altitude_profile.points',
         'not_an_integer'),
        ({'start': 0, 'end': 10, 'points': 101}, 'altitude_profile.points',
         'out_of_range'),
        ({'start': None, 'end': 10, 'points': 5}, 'altitude_profile.start',
         'not_a_number'),
        ({'start': True, 'end': 10, 'points': 5}, 'altitude_profile.start',
         'not_a_number'),
        ([], 'altitude_profile', 'not_an_object'),
        ({'start': 0, 'end': 1, 'points': 3, 'x': 1}, 'altitude_profile',
         'unknown_fields'),
    ])
    def test_adli_ret(self, ham, alan, neden):
        from hrma.analysis.altitude_performance import (
            AltitudeProfileError, parse_altitude_profile)
        with pytest.raises(AltitudeProfileError) as e:
            parse_altitude_profile(ham)
        assert (e.value.field, e.value.reason) == (alan, neden)

    def test_uc_reddi_422_adiyla(self):
        durum, y = _hibrit(altitude_profile={'start': 0, 'end': 0,
                                             'points': 5})
        assert durum == 422
        assert y['invalid_fields'][0]['field'] == 'altitude_profile.end'

    def test_sifir_satiri_motorun_deniz_seviyesi_sonucu(self, profil_deniz):
        ap = profil_deniz['altitude_profile_performance']
        assert ap['status'] == 'computed'
        sifir = ap['rows'][0]
        assert sifir['altitude_m'] == 0.0
        # Bit-aynı: motorun itkisi ve yayımladığı deniz seviyesi Isp'si.
        assert sifir['thrust_n'] == profil_deniz['thrust']
        assert sifir['isp_s'] == profil_deniz['sea_level_isp']

    def test_vakum_ucu_motorun_vakum_ispsi(self, profil_deniz):
        ap = profil_deniz['altitude_profile_performance']
        assert ap['vacuum']['isp_s'] == profil_deniz['vacuum_isp']

    def test_ara_satirlar_motorun_irtifa_tablosuyla_ayni(self, profil_deniz):
        ap = profil_deniz['altitude_profile_performance']
        tablo = {r['altitude']: r for r in
                 profil_deniz['altitude_performance']['altitude_performance']}
        ortak = [r for r in ap['rows'] if r['altitude_m'] in tablo]
        assert len(ortak) >= 4
        for r in ortak:
            m = tablo[r['altitude_m']]
            assert r['thrust_n'] == pytest.approx(m['thrust'], rel=1e-12)
            assert r['isp_s'] == pytest.approx(m['isp'], rel=1e-12)
            assert r['ambient_pressure_bar'] == pytest.approx(
                m['pressure'], rel=1e-15)

    def test_atmosfer_yorunge_cozucusuyle_ayni_tablo(self, profil_deniz):
        """Aynı ISA 1976 katman tablosu (hrma.constants), AYNI irtifa
        okuması. ÇEVRİLDİ (V307/İRTİFA-TEK, ana model kararı 16 Kas): bu
        bekçi profilin irtifayı geopotansiyel (dönüşümsüz) okuduğunu ve
        yörüngenin aynı basıncı ancak h_g = h·R/(R − h) noktasında verdiğini
        kilitliyordu (SEKME-MOTOR §9 "KARAR GEREKİYOR"). Karar: irtifa
        GEOMETRİKTİR; profil, motorun irtifa tablosu, form ve yörünge aynı
        h'de aynı basıncı verir (20 km'de eski okuma %0,99 düşüktü)."""
        from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
        from hrma.constants import BAR_PER_PA, isa_pressure_geometric
        yor = TrajectoryAnalyzer()
        for r in profil_deniz['altitude_profile_performance']['rows']:
            h = r['altitude_m']
            assert r['ambient_pressure_bar'] == \
                isa_pressure_geometric(h) * BAR_PER_PA
            _rho, p_pa, _t, _a = yor._atm_full(h)
            assert p_pa == pytest.approx(isa_pressure_geometric(h),
                                         rel=1e-12)

    def test_ayrilma_satirlari_motorun_olcutuyle(self, profil_10km):
        from hrma.flow.separation import SUMMERFIELD_FACTOR_DEFAULT
        ap = profil_10km['altitude_profile_performance']
        pe = profil_10km['nozzle_expansion_screen']['exit_pressure_bar']
        bayraklar = []
        for r in ap['rows']:
            beklenen = pe < SUMMERFIELD_FACTOR_DEFAULT * r['ambient_pressure_bar']
            assert r['flow_separation_predicted'] is beklenen
            if beklenen:
                assert r['thrust_n'] is None and r['isp_s'] is None
                assert 'Summerfield' in r['not_published_reason']
            else:
                assert isinstance(r['thrust_n'], float)
            bayraklar.append(beklenen)
        # 10 km'ye göre genişletilmiş lüle deniz seviyesinde ayrılır,
        # tasarım irtifasında ayrılmaz.
        assert bayraklar[0] is False and bayraklar[-1] is True

    def test_motor_ayni_luleyi_deniz_seviyesinde_ayrilmis_buluyor(
            self, profil_10km):
        """Çapraz denetim: aynı ε'lu lüle deniz seviyesinde tasarlanınca
        motorun KENDİ denetimi de ayrılma öngörür (tablonun 0 m satırı)."""
        eps = profil_10km['expansion_ratio']
        durum, y = _hibrit(expansion_ratio=eps)
        assert durum == 200, y
        ekran = y['motor']['nozzle_expansion_screen']
        assert ekran['separation_predicted'] is True
        sifir = profil_10km['altitude_profile_performance']['rows'][-1]
        assert sifir['altitude_m'] == 0.0
        assert sifir['flow_separation_predicted'] is True

    def test_form_bos_alani_sessizce_sayiya_cevirmez(self):
        html = _oku('hrma/templates/advanced.html')
        bas = html.index('function getFormData()')
        govde = html[bas:bas + 4000]
        assert "value || 0)" not in govde
        assert "value || 10000)" not in govde
        assert "value || 10)" not in govde
        assert 'adv.js.altProfileEmpty' in html
        assert _sozluk_iki_dilde('hrma/static/js/i18n_advanced.js',
                                 'adv.js.altProfileEmpty')

    def test_ipuclari_artik_okunmuyor_demiyor(self):
        sozluk = _oku('hrma/static/js/i18n_advanced.js')
        for anahtar in ('adv.tip.finalAltitudeM', 'adv.tip.numberPoints'):
            satir = [s for s in sozluk.splitlines()
                     if f"'{anahtar}':" in s]
            assert len(satir) == 2
            assert 'does not read it' not in satir[0]
            assert 'okumaz' not in satir[1]
