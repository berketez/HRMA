"""
D4 motor→FEA köprüsü bekçileri (hrma/fea/bridge.py).

Neyi kilitler:

  1. GERÇEK hibrit ve GERÇEK sıvı hesabından (app.test_client, uçtan uca)
     yapısal FEA koşusu: SF alanı her düğümde pozitif, von Mises sonlu,
     yakınsama beyanı dürüst (yakınsamadıysa yakınsamış gibi sunulmaz).
  2. Girdi sadakati: köprünün kullandığı kontur noktaları motorun
     yayımladığı ``nozzle_contour.points`` ile BİREBİR aynı; cidar
     kalınlığı çözücünün yayımladığı mm değerinin tam m karşılığı; basınç
     yükü ``chamber_pressure`` [bar] alanının tam Pa karşılığı. Köprü
     hiçbir girdiyi "düzeltemez" / yuvarlayamaz.
  3. Eksik girdi = RED: kontur, yapısal blok veya malzeme kaydı yoksa
     sonuç NOT_MODELLED döner, missing listesi eksiği adlandırır ve redli
     sonuçta HİÇBİR gerilme/SF alanı bulunmaz (uydurma yok).
  4. Termal iskelet: motorlar Bartz h(z) yayımlamadığı için profilsiz
     çağrı RED; profil verilince D2 modülü yoksa NOT_AVAILABLE (açıklayıcı),
     varsa INPUTS_READY — hiçbir dalda uydurma sıcaklık alanı yok.
     İki dal da sys.modules enjeksiyonuyla DETERMİNİSTİK test edilir
     (D2 paralel dalgada yazılıyor; testin sonucu onun iniş anına bağlı
     olamaz).

Koşular küçük mesh ile sürülür (n_axial0=8, n_radial0=3, max_rounds=2) —
bekçinin işi sayısal hassasiyet değil (o tests/fea/test_yapisal_dogrulama
+ test_yapisal_vaka_dogrulama'nın işi), zincirin sadakati.
"""

import contextlib
import copy
import io
import sys
import types

import numpy as np
import pytest

from hrma.fea import bridge
from hrma.fea.bridge import (
    BRIDGE_STATUS_INPUTS_READY,
    BRIDGE_STATUS_NOT_AVAILABLE,
    BRIDGE_STATUS_NOT_MODELLED,
    BRIDGE_STATUS_OK,
    detect_engine_layout,
    extract_structural_inputs,
    run_structural_from_motor,
    run_thermal_from_motor,
)

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')

# Küçük-mesh koşu parametreleri — testin her koşusunda aynı (tek tanım).
KUCUK_MESH = dict(n_axial0=8, n_radial0=3, max_rounds=2)

# Redli sonuçta bulunmaması ZORUNLU çözüm alanları (sahte veri yasağı).
COZUM_ALANLARI = ('von_mises_nodal', 'von_mises_gauss_max',
                  'safety_factor_nodal', 'min_safety_factor',
                  'displacement', 'stress_nodal', 'mesh', 'result',
                  'refinement')


def _quiet(fn, *args, **kwargs):
    """Motor modülleri stdout'a bolca basıyor; testte sessize al."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def hibrit_motor(client):
    """GERÇEK hibrit hesabı — /calculate yanıtının 'motor' alt sözlüğü."""
    yuk = {'motor_name': 'bridge-h', 'fuel_type': 'htpb',
           'oxidizer_type': 'n2o', 'thrust': 2000, 'burn_time': 10,
           'chamber_pressure': 30, 'of_ratio': 6.0}
    resp = _quiet(client.post, '/calculate', json=yuk)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    motor = resp.get_json().get('motor')
    assert isinstance(motor, dict), "/calculate yanıtında 'motor' bloğu yok"
    return motor


@pytest.fixture(scope='module')
def sivi_motor(client):
    """GERÇEK sıvı hesabı — /calculate_liquid yanıtı (üst düzey sözlük)."""
    pytest.importorskip('rocketcea.cea_obj')
    yuk = {'fuel_type': 'rp1', 'oxidizer_type': 'lox', 'mixture_ratio': 2.3,
           'thrust': 25000, 'chamber_pressure': 70,
           'engine_cycle': 'gas_generator', 'injector_type': 'impinging',
           'contraction_ratio': 4, 'characteristic_length': 1.2,
           'chamber_material': 'inconel_718',
           'cooling_type': 'regenerative', 'nozzle_type': 'bell_80',
           'safety_factor': 2.5}
    resp = _quiet(client.post, '/calculate_liquid', json=yuk)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


@pytest.fixture(scope='module')
def kati_motor(client):
    """GERÇEK katı hesabı — /calculate_solid yanıtı (üst düzey sözlük)."""
    yuk = {'motor_name': 'bridge-s', 'chamber_pressure': 40, 'thrust': 1500,
           'burn_time': 3, 'grain_type': 'bates', 'outer_diameter': 100,
           'core_diameter': 35, 'grain_length': 300, 'segments': 1,
           'burn_rate_a': 0.005, 'burn_rate_n': 0.35,
           'chamber_temperature': 3000, 'c_star': 1550,
           'propellant_density': 1800, 'propellant_type': 'apcp'}
    resp = _quiet(client.post, '/calculate_solid', json=yuk)
    assert resp.status_code == 200, resp.get_data(as_text=True)[:400]
    return resp.get_json()


# ---------------------------------------------------------------------------
# Ortak doğrulayıcı: uçtan uca koşunun sadakat + fizik denetimi
# ---------------------------------------------------------------------------
def _kosuyu_dogrula(out, motor, cidar_mm, beklenen_tip):
    assert out['status'] == BRIDGE_STATUS_OK
    assert out['engine_layout'] == beklenen_tip

    # (2) Girdi sadakati — kontur BİREBİR, cidar ve basınç tam karşılık.
    ins = out['inputs']
    motor_pts = np.asarray(motor['nozzle_contour']['points'], dtype=float)
    assert np.array_equal(ins['nozzle_points'], motor_pts), \
        'köprünün kontur noktaları motorun yayımladığından sapmış'
    # Kamara uzantısı varsa kontur = [uzantı noktası] + motor noktaları;
    # kuyruk yine birebir motor noktaları olmalı.
    assert np.array_equal(ins['contour'][-motor_pts.shape[0]:], motor_pts)
    assert ins['thickness_m'] == cidar_mm / 1000.0, \
        'cidar kalınlığı çözücünün yayımladığı değerden sapmış'
    assert ins['inner_pressure_pa'] == float(motor['chamber_pressure']) * 1e5

    # (1) Fizik: von Mises sonlu-pozitif, SF alanı her düğümde pozitif.
    vm = out['von_mises_nodal']
    assert np.all(np.isfinite(vm)) and vm.max() > 0.0
    sf = out['safety_factor_nodal']
    assert sf is not None, 'malzemede akma var — SF alanı üretilmeliydi'
    assert np.all(sf > 0.0)
    assert out['min_safety_factor'] > 0.0

    # Yakınsama beyanı DÜRÜST: blok tam, beyan metni durumu adlandırıyor.
    conv = out['convergence']
    assert isinstance(conv['converged'], bool)
    assert conv['history'], 'inceltme geçmişi boş olamaz'
    assert isinstance(conv['beyan'], str) and 'YAKINSA' in conv['beyan'].upper()

    # Girdilerin _basis zinciri: her alanın kaynağı beyanlı; P(x)
    # yayımlanmadığı için sabit-Pc yaklaşımı AÇIKÇA yazılı.
    basis = ins['_basis']
    for alan in ('kontur', 'cidar', 'malzeme', 'yuk', 'kamara_uzantisi'):
        assert alan in basis, f'_basis zincirinde {alan} beyanı yok'
    assert 'SABİT Pc' in basis['yuk']['dagilim']
    assert out['meta']['not_modelled'], 'modellenmeyen fizik beyanı boş'


# ---------------------------------------------------------------------------
# 1-2) Uçtan uca koşular — gerçek hibrit, sıvı ve katı hesabından
# ---------------------------------------------------------------------------
def test_hibrit_uctan_uca_yapisal(hibrit_motor):
    out = run_structural_from_motor(hibrit_motor, **KUCUK_MESH)
    cidar_mm = (hibrit_motor['structural_analysis']['chamber_analysis']
                ['wall_thickness_used_mm'])
    _kosuyu_dogrula(out, hibrit_motor, cidar_mm, 'hybrid')
    # Hibrit kamara boyu metre yayımlar — uzantı eklenmiş olmalı.
    assert out['inputs']['chamber_extension_m'] == pytest.approx(
        float(hibrit_motor['chamber_length']))


def test_sivi_uctan_uca_yapisal(sivi_motor):
    out = run_structural_from_motor(sivi_motor, **KUCUK_MESH)
    cidar_mm = (sivi_motor['structural_analysis']['chamber_structure']
                ['wall_thickness'])
    _kosuyu_dogrula(out, sivi_motor, cidar_mm, 'liquid')
    # Sıvı kamara boyu mm yayımlar — köprü m'ye çevirmiş olmalı.
    assert out['inputs']['chamber_extension_m'] == pytest.approx(
        float(sivi_motor['chamber_length']) / 1000.0)


def test_kati_uctan_uca_yapisal(kati_motor):
    out = run_structural_from_motor(kati_motor, **KUCUK_MESH)
    cidar_mm = (kati_motor['structural_analysis']['case_analysis']
                ['wall_thickness_mm'])
    _kosuyu_dogrula(out, kati_motor, cidar_mm, 'solid')
    # Katı üst düzeyde kasa boyu yayımlamaz — uzantı OLMAMALI ve bu
    # sessizce değil beyanla atlanmalı.
    assert out['inputs']['chamber_extension_m'] is None
    assert 'eklenmedi' in out['inputs']['_basis']['kamara_uzantisi']['beyan']


def test_kati_akma_cozucunun_degeri(kati_motor):
    """Katıda akma, DB kaydı DEĞİL çözücünün fiilen kullandığı değerdir.

    _case_design varsayılan tabanı (jenerik çelik) materials_db'nin
    steel_4130 kaydından farklı olabilir; köprünün SF'si çözücünün
    dayanımından sapmamalı (bkz. bridge.py malzeme haritası).
    """
    ins = extract_structural_inputs(kati_motor)
    assert ins['status'] == BRIDGE_STATUS_OK
    y_mpa = (kati_motor['structural_analysis']['case_analysis']
             ['yield_strength_mpa'])
    assert ins['material'].yield_strength == pytest.approx(y_mpa * 1e6)
    assert 'FİİLEN' in ins['_basis']['malzeme']['akma_kaynagi']


# ---------------------------------------------------------------------------
# 3) Eksik girdi = RED (uydurma yok)
# ---------------------------------------------------------------------------
def _red_dogrula(sonuc, beklenen_eksik_parcasi):
    assert sonuc['status'] == BRIDGE_STATUS_NOT_MODELLED
    assert any(beklenen_eksik_parcasi in e for e in sonuc['missing']), \
        f"missing listesi eksiği adlandırmıyor: {sonuc['missing']}"
    # Redli sonuçta hiçbir çözüm alanı bulunamaz — kısmi/uydurma sonuç yok.
    for alan in COZUM_ALANLARI:
        assert alan not in sonuc, f'redli sonuçta çözüm alanı sızmış: {alan}'
    # Uyarı {code, params} sözleşmesiyle ve warn. önekli.
    assert sonuc['warning']['code'].startswith('warn.fea.')


def test_konturu_eksik_motor_red(hibrit_motor):
    m = copy.deepcopy(hibrit_motor)
    del m['nozzle_contour']
    _red_dogrula(run_structural_from_motor(m), 'nozzle_contour')


def test_yapisal_blogu_eksik_motor_red(hibrit_motor):
    m = copy.deepcopy(hibrit_motor)
    del m['structural_analysis']
    _red_dogrula(run_structural_from_motor(m), 'structural_analysis')


def test_bilinmeyen_malzeme_red(hibrit_motor):
    m = copy.deepcopy(hibrit_motor)
    m['structural_analysis']['design_parameters']['material'] = 'unobtainium'
    _red_dogrula(run_structural_from_motor(m), 'malzeme')


def test_basinci_eksik_motor_red(hibrit_motor):
    m = copy.deepcopy(hibrit_motor)
    del m['chamber_pressure']
    _red_dogrula(run_structural_from_motor(m), 'chamber_pressure')


def test_cidari_eksik_motor_red(hibrit_motor):
    m = copy.deepcopy(hibrit_motor)
    del (m['structural_analysis']['chamber_analysis']
         ['wall_thickness_used_mm'])
    # İmza alanı silinince tip tespiti de düşer — hangi adla düşerse
    # düşsün sonuç RED olmalı ve çözüm alanı sızmamalı.
    sonuc = run_structural_from_motor(m)
    assert sonuc['status'] == BRIDGE_STATUS_NOT_MODELLED
    for alan in COZUM_ALANLARI:
        assert alan not in sonuc


def test_tip_tespiti_tahmin_etmez():
    """İmza yoksa None — 'büyük ihtimalle şudur' tahmini yasak."""
    assert detect_engine_layout({}) is None
    assert detect_engine_layout({'structural_analysis': {}}) is None
    assert detect_engine_layout('sözlük değil') is None
    assert detect_engine_layout(
        {'structural_analysis': {'chamber_analysis': {}}}) is None


# ---------------------------------------------------------------------------
# 4) Termal iskelet — profil zorunlu, D2 kapısı import-korumalı
# ---------------------------------------------------------------------------
def _ornek_profil():
    """analyze_axial_profile sözleşmesinde küçük sentetik profil.

    Test altyapısıdır (pytest fixture sınıfı) — kullanıcıya gösterilen
    veri değildir; sahte veri yasağının test-mock istisnası kapsamındadır.
    """
    return {'x_mm': [0.0, 40.0, 80.0, 124.0],
            'h_g': [900.0, 4800.0, 2100.0, 1300.0],
            'T_recovery': [2900.0, 2850.0, 2600.0, 2400.0]}


def test_termal_profilsiz_red(hibrit_motor):
    """Motor sözlüğünde h(z) yok — profil verilmeden çağrı RED olmalı."""
    sonuc = run_thermal_from_motor(hibrit_motor)
    assert sonuc['status'] == BRIDGE_STATUS_NOT_MODELLED
    assert any('h(z)' in e for e in sonuc['missing'])
    assert sonuc['warning']['code'] == bridge.WARN_THERMAL_PROFILE_MISSING


def test_termal_bozuk_profil_red(hibrit_motor):
    prof = _ornek_profil()
    prof['h_g'][1] = -5.0  # negatif ısı taşınım katsayısı fiziksel değil
    sonuc = run_thermal_from_motor(hibrit_motor, axial_profile=prof)
    assert sonuc['status'] == BRIDGE_STATUS_NOT_MODELLED


def test_termal_modul_yokken_aciklayici_red(hibrit_motor, monkeypatch):
    """D2 depoda yokken: NOT_AVAILABLE + açıklayıcı neden (sessiz ölüm yok).

    sys.modules'a None enjekte edilir — import bu durumda ImportError
    yükseltir; test D2'nin gerçekte inip inmediğinden bağımsızdır.
    """
    monkeypatch.setitem(sys.modules, 'hrma.fea.thermal_axisym', None)
    sonuc = run_thermal_from_motor(hibrit_motor,
                                   axial_profile=_ornek_profil())
    assert sonuc['status'] == BRIDGE_STATUS_NOT_AVAILABLE
    assert 'thermal_axisym' in sonuc['reason']
    assert sonuc['warning']['code'] == bridge.WARN_THERMAL_SOLVER_UNAVAILABLE
    # Uydurma termal alan yok:
    assert 'temperature' not in sonuc and 'T_wall' not in sonuc


def test_termal_modul_varken_girdiler_hazir(hibrit_motor, monkeypatch):
    """D2 varken: INPUTS_READY + çıkarılmış girdiler; çözüm İDDİASI yok."""
    monkeypatch.setitem(sys.modules, 'hrma.fea.thermal_axisym',
                        types.ModuleType('hrma.fea.thermal_axisym'))
    sonuc = run_thermal_from_motor(hibrit_motor,
                                   axial_profile=_ornek_profil())
    assert sonuc['status'] == BRIDGE_STATUS_INPUTS_READY
    ins = sonuc['inputs']
    # x_mm → m dönüşümü yapılmış, diziler eş boy ve pozitif.
    assert ins['h_x_m'][-1] == pytest.approx(0.124)
    assert ins['h_g_W_m2K'].shape == ins['t_recovery_K'].shape
    assert np.all(ins['h_g_W_m2K'] > 0.0)
    # Malzemenin termal alanları materials_db kaydından beyanlı.
    assert ins['thermal_material']['thermal_conductivity_W_mK'] > 0.0
    assert 'materials_db' in ins['thermal_material']['kaynak']
    # Çözüm iddiası taşıyan hiçbir alan yok (sahte veri yasağı).
    assert 'temperature' not in sonuc and 'T_wall' not in sonuc
    assert 'çağrı' in sonuc['reason'] or 'API' in sonuc['reason']
