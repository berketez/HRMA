"""V306/UÇUŞ-KÜTLE — uçuş kütlesi (yüklü ⟷ harcanan) ve uçuş ekranları.

Kanıt: docs/scofield/raw/OH/V306/ucus-kutle/ (olcum/k12_once.json ⟷
olcum/k12_sonra.json, degisim_tablosu.md, RAPOR.md). Beklenen değerler ürün
sabitlerinden değil, aynı yanıtın kendi alanlarından (kimlik) okunur.

Kalemler:
  1  hibritte yanmayan tane şeridi uçuş kütlesinde: kalkış = kuru + YÜKLÜ
     itici (= motorun total_mass_kg'ı), yanma sonu = kuru + kalan; şeridi
     sıfır motorda uçuş bit-aynı
  2  OpenRocket .eng: itici alanı HARCANAN, yüklü kütle = motorun kalkış
     kütlesi; katı/sıvı dosyası değişmez
  4  parametrik tarama noktası irtifa düzeltmesiyle uçar (/calculate ile
     aynı çıkış alanı)
  5  Yörünge açıklama listeleri çizilen 6 hücreli figürü anlatır
  6  6-DOF gövde çapı sayfa motorunun zarfından (HRMA seçimi) tohumlanır
"""
import contextlib
import io
import json
import math
import pathlib
import re

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
JS = KOK / 'hrma' / 'static' / 'js'
TPL = KOK / 'hrma' / 'templates'
H = {'Host': '127.0.0.1:8080'}

#: test_d24_hibrit_a1 HIBRIT_YUK (N₂O kendinden basınçlı tank, boşalma);
#: şeritli kolu ``residual_web_thickness`` ile (mühendis turu L2/L3 alanı).
D24_YUK = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 1.0,
           'chamber_pressure': 20.0, 'fuel_type': 'htpb',
           'oxidizer_type': 'n2o'}
D24_SERITLI = dict(D24_YUK, residual_web_thickness=2)

#: Mühendis turu hibrit L3 /calculate gövdesi AYNEN (LOX/parafin, regüle
#: besleme, 2 mm yanmayan cidar). Kaynak: docs/scofield/raw/OH/V306/
#: muhendis-turu/hibrit/vakalar/L3.json (docs'suz ağaçta da koşsun diye
#: gövde burada).
L3 = {"motor_name": "MUH-HIB-L3", "motor_description": "",
      "atmospheric_pressure": 1.01325, "of_ratio": 2.48,
      "chamber_pressure": 30, "tank_pressure": 40, "thrust": 10500,
      "burn_time": 27, "total_impulse": 283500, "calculate_trajectory": True,
      "vehicle_mass_dry": 93.8, "vehicle_reference_area_m2": 0.070686,
      "drag_coefficient": 0.4, "vehicle_length": None, "launch_angle": 90,
      "launch_altitude": 0, "wind_speed": 0, "wind_direction": 0,
      "expansion_ratio": 7, "nozzle_type": "conical",
      "combustion_type": "infinite", "combustion_efficiency": 89,
      "mass_flux_chamber": 0, "fuel_type": "paraffin", "fuel_density": 900,
      "regression_a": 0.000117, "regression_n": 0.62,
      "oxidizer_type": "lox", "oxidizer_phase": "liquid",
      "oxidizer_density": 1141, "oxidizer_viscosity": 0.00019,
      "oxidizer_temp": 90, "injector_type": "showerhead",
      "chamber_material": "steel_4130", "nozzle_material": "graphite",
      "injector_material": "steel_4130", "design_config_opened": True,
      "design_config_source": "user",
      "design_config_fields": [
          {"field": "chamber_material", "source": "user"},
          {"field": "nozzle_material", "source": "user"},
          {"field": "injector_material", "source": "user"}],
      "plate_thickness": 8, "tank_pressure_source": "user", "port_count": 1,
      "residual_web_thickness": 2}


def _calculate(govde):
    from hrma.app import app
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = app.test_client().post('/calculate', json=govde, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


@pytest.fixture(scope='module')
def l3():
    return _calculate(dict(L3))


@pytest.fixture(scope='module')
def l3_motor_kuru():
    """L3, araç kuru kütlesi verilmeden: uçuş kuru kütlesi = motor kuru."""
    g = dict(L3)
    g.pop('vehicle_mass_dry')
    return _calculate(g)


@pytest.fixture(scope='module')
def d24():
    return _calculate(dict(D24_YUK))


@pytest.fixture(scope='module')
def d24_seritli():
    g = dict(D24_SERITLI)
    return _calculate(g)


def _kd(y):
    return y['motor']['design_summary']['key_dimensions']


# ----------------------------------------------------------------- kalem 1

def test_k1_regule_kalkis_kutlesi_motorun_kalkis_kutlesi(l3_motor_kuru):
    """Tek büyüklük, tek sayı: motor kalkış kütlesi = Yörünge kalkış kütlesi.

    L3 regüle besleme + 1,31 kg yanmayan şerit. Araç kuru kütlesi verilmediği
    için uçuşun kuru kütlesi motorun kuru kütlesidir; kalkış kütlesi o zaman
    motorun ``total_mass_kg``ıdır (kuru + yüklü ox + dökülen tane).
    """
    y = l3_motor_kuru
    m = y['motor']
    serit = m['fuel_mass_loaded'] - m['fuel_mass']
    assert serit > 1.0                       # ölçülen 1,3143 kg
    vp = y['trajectory']['vehicle_parameters']
    assert vp['mass_loaded'] == pytest.approx(_kd(y)['total_mass_kg'],
                                              rel=1e-12)
    # Yanma sonu = kuru + yanmayan şerit (regüle: motorun teslim bütçesi
    # propellant_mass_total yanar).
    assert vp['mass_dry'] == pytest.approx(
        _kd(y)['dry_mass_estimate_kg'] + serit, rel=1e-12)


def test_k1_ucan_itki_blogu_yuklu_harcanan_kalan(l3):
    from hrma.analysis.flight_vehicle import motor_flight_thrust
    m = l3['motor']
    u = motor_flight_thrust('hybrid', l3)
    assert u['curve_source'] == 'motor_regulated'
    assert u['propellant_loaded_kg'] == pytest.approx(
        m['propellant_mass_loaded_kg'], rel=1e-12)
    # Regüle: yanan = motorun teslim bütçesinin kütlesi (isp_delivered_avg_s
    # bu kütleyle tanımlı); kalan = yanmayan şerit.
    assert u['propellant_consumed_kg'] == m['propellant_mass_total']
    serit = m['fuel_mass_loaded'] - m['fuel_mass']
    assert u['unburnt_fuel_kg'] == serit
    assert u['propellant_residual_kg'] == pytest.approx(serit, rel=1e-12)
    # Yörünge: kalkış = istek kuru + yüklü itici; uçan Isp motorun teslim
    # Isp'si (tek sayı).
    tr = l3['trajectory']
    assert tr['vehicle_parameters']['mass_loaded'] == pytest.approx(
        L3['vehicle_mass_dry'] + m['propellant_mass_loaded_kg'], rel=1e-12)
    assert tr['flown_isp_s'] == m['isp_delivered_avg_s']
    assert 'unburnt fuel grain' in tr['flown_isp_basis']


def test_k1_bosalma_serit_ve_tank_kalani(d24_seritli):
    """N₂O boşalma + şerit: kalan = tankta kalan + şerit; kalkış = motor."""
    from hrma.analysis.flight_vehicle import motor_flight_thrust, normalize
    y = d24_seritli
    m = y['motor']
    serit = m['fuel_mass_loaded'] - m['fuel_mass']
    assert serit > 0.0
    u = motor_flight_thrust('hybrid', y)
    assert u['curve_source'] == 'motor_blowdown'
    eski_kalan = m['propellant_mass_total'] - u['propellant_consumed_kg']
    assert u['propellant_residual_kg'] == pytest.approx(eski_kalan + serit,
                                                        rel=1e-12)
    # Araç kartı: uçan atıl + yüklü itici = motorun kalkış kütlesi.
    arac = normalize('hybrid', y)
    assert arac['engine_inert_mass'] + arac['propellant_mass'] == \
        pytest.approx(_kd(y)['total_mass_kg'], rel=1e-12)
    vp = y['trajectory']['vehicle_parameters']
    assert vp['mass_loaded'] == pytest.approx(_kd(y)['total_mass_kg'],
                                              rel=1e-12)


def test_k1_seritsiz_motorda_eski_sayi_bit_ayni(d24):
    """Şerit 0: kalan eski tankta-kalan sayısıyla BİT-AYNI (toplama sırası)."""
    from hrma.analysis.flight_vehicle import motor_flight_thrust, normalize
    m = d24['motor']
    assert m['fuel_mass_loaded'] - m['fuel_mass'] == 0.0
    u = motor_flight_thrust('hybrid', d24)
    assert u['propellant_loaded_kg'] == m['propellant_mass_total']
    assert u['propellant_residual_kg'] == (m['propellant_mass_total']
                                           - u['propellant_consumed_kg'])
    assert normalize('hybrid', d24)['propellant_mass'] == \
        m['propellant_mass_total']


def test_k1_kati_sivi_kalan_sifir():
    from hrma.analysis.flight_vehicle import motor_flight_thrust
    k = motor_flight_thrust('solid', {'propellant_mass': 2.5,
                                      'average_thrust': 100.0,
                                      'burn_time': 2.0})
    assert k['propellant_residual_kg'] == 0.0
    assert k['propellant_loaded_kg'] == k['propellant_consumed_kg'] == 2.5


def test_k1_js_tuketicileri_kalani_her_kaynakta_okur():
    """Yörünge (app.js), 6-DOF (advanced.html), Fırlatma Sahası aynı alan."""
    for yol in (JS / 'app.js', TPL / 'advanced.html',
                TPL / 'launch_site.html'):
        metin = yol.read_text(encoding='utf-8')
        assert 'propellant_residual_kg' in metin, yol.name
    adv = (TPL / 'advanced.html').read_text(encoding='utf-8')
    # Yörünge paneli kalkış kütlesi yüklü iticiyle (şerit dahil).
    assert 'var yuklu = m.propellant_mass_loaded_kg;' in adv


# ----------------------------------------------------------------- kalem 2

def _eng_basligi(icerik):
    satir = [s for s in icerik.splitlines()
             if s and not s.startswith(';') and len(s.split()) == 7]
    assert satir, icerik[:400]
    return satir[0].split()


def test_k2_eng_itici_harcanan_yuklu_motor_kalkisi(l3):
    from hrma.export.openrocket_integration import OpenRocketExporter
    m = l3['motor']
    with contextlib.redirect_stdout(io.StringIO()):
        icerik = OpenRocketExporter().export_motor_file(m)
    b = _eng_basligi(icerik)
    # Regüle: harcanan = motorun teslim bütçesinin kütlesi (uçuşla aynı).
    assert float(b[4]) == round(m['propellant_mass_total'], 3)
    assert float(b[5]) == round(_kd(l3)['total_mass_kg'], 3)
    assert 'propellant not burnt' in icerik


def test_k2_eng_bosalma_tankta_kalan_itici_degil(d24):
    """N₂O boşalma: itici alanı harcanan, tankta kalan yüklü kütlede."""
    from hrma.export.openrocket_integration import OpenRocketExporter
    m = d24['motor']
    with contextlib.redirect_stdout(io.StringIO()):
        icerik = OpenRocketExporter().export_motor_file(m)
    b = _eng_basligi(icerik)
    assert float(b[4]) == round(m['propellant_mass_consumed_kg'], 3)
    assert float(b[4]) < round(m['propellant_mass_total'], 3)
    assert float(b[5]) == round(_kd(d24)['total_mass_kg'], 3)
    assert 'propellant_mass_consumed_kg' in icerik


def test_k2_kati_sivi_ayrim_yok():
    from hrma.export.openrocket_integration import OpenRocketExporter
    assert OpenRocketExporter.resolve_eng_propellant_split(
        {'propellant_mass_total': 3.0}) is None
    assert OpenRocketExporter.resolve_eng_propellant_split(
        {'propellant_mass': 3.0, 'thrust_curve': {}}) is None


# ----------------------------------------------------------------- kalem 4

def test_k4_tarama_noktasi_irtifa_duzeltmesiyle_ucar():
    """Tarama motoru uq_mode'da: çıkış alanı lüle geometrisinden okunur."""
    from hrma.analysis.flight_vehicle import motor_flight_thrust
    u = motor_flight_thrust('hybrid', {
        'uq_mode': True, 'exit_area': 0.0123, 'propellant_mass_total': 1.0,
        'thrust': 100.0, 'burn_time': 1.0,
        'nozzle_design': {'performance': {'ambient_pressure': 1.01325}}})
    assert u['nozzle_exit_area_m2'] == 0.0123
    assert u['thrust_reference_pressure_pa'] == pytest.approx(101325.0)
    # uq_mode DIŞINDA geometrik alan okunmaz (tek kural nozzle_loss_model).
    u2 = motor_flight_thrust('hybrid', {
        'exit_area': 0.0123, 'propellant_mass_total': 1.0,
        'thrust': 100.0, 'burn_time': 1.0})
    assert u2['nozzle_exit_area_m2'] is None


# ----------------------------------------------------------------- kalem 5

YASAK_YORUNGE = ('orbit insertion', 'Stage separation', 'MECO',
                 'Green line', 'Vertical ascent', 'Acceleration Profile',
                 'staging analysis')


@pytest.mark.parametrize('sablon', ['advanced.html', 'liquid.html',
                                    'solid.html'])
def test_k5_yorunge_listesi_cizilen_figuru_anlatir(sablon):
    metin = (TPL / sablon).read_text(encoding='utf-8')
    for parca in YASAK_YORUNGE:
        assert parca not in metin, (sablon, parca)
    for hucre in ('Trajectory Profile:', 'Altitude vs Time:',
                  'Velocity Profile:', 'Load Factor Profile:',
                  'Flight Phases:'):
        assert hucre in metin, (sablon, hucre)


# ----------------------------------------------------------------- kalem 6

def test_k6_govde_motor_zarfindan_tek_yerde():
    """Araç tanımı yayımlamayan sayfada 6-DOF gövdesi zarftan dar açılmaz.

    Kural tek yerde (sixdof_panel.js); sıvı sayfasının satır içi kopyası
    kalktı. Davranış tarayıcıda ölçüldü (katı Ø100 → 116 mm, 6-DOF 200).
    """
    panel = (JS / 'sixdof_panel.js').read_text(encoding='utf-8')
    assert 'function govdeyiMotordanTohumla(arac)' in panel
    assert 'govdeyiMotordanTohumla(d.vehicle)' in panel
    # Yalnız darsa yükseltir; 1 mm yukarı yuvarlar (pay yok).
    assert 'Math.ceil(od * 1000 - 1e-9) / 1000' in panel
    assert '(isFinite(simdi) && simdi >= od)' in panel
    sivi = (TPL / 'liquid.html').read_text(encoding='utf-8')
    assert 'Math.ceil(arac.engine_od_m * 1000)' not in sivi
    ortak = (JS / 'i18n_common.js').read_text(encoding='utf-8')
    assert ortak.count("'sixdof.seed.bodyFromEngine'") == 2


# ----------------------------------------------------------------- kalem 3

def test_k3_sivi_varsayilan_form_kaynaksiz_epsilon_yok_422_yok():
    sivi = (TPL / 'liquid.html').read_text(encoding='utf-8')
    girdi = re.search(r'<input[^>]*id="nozzle_expansion_ratio"[^>]*>', sivi)
    assert girdi and 'value=' not in girdi.group(0)
    assert "getElementById('nozzle_expansion_ratio').value = '50'" not in sivi
    assert 'blank = 422' not in sivi
    sozluk = (JS / 'i18n_pages.js').read_text(encoding='utf-8')
    for anahtar in ('liq.attr.required_blank_422', 'liq.js.server_rejected'):
        for satir in re.findall(r"'%s': '([^']*)'" % re.escape(anahtar),
                                sozluk):
            assert '422' not in satir and 'HTTP' not in satir, satir


def test_k3_bos_epsilon_ortama_eslenir():
    """Boş ε: çözücü çıkış basıncını deniz seviyesine eşler (künyeli)."""
    from hrma.app import app
    g = {'thrust': 5000, 'chamber_pressure': 30, 'mixture_ratio': 2.4,
         'max_burn_duration': 36, 'fuel_type': 'rp1',
         'oxidizer_type': 'lox', 'nozzle_expansion_ratio': None}
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        r = app.test_client().post('/calculate_liquid', json=g, headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    s = r.get_json()
    assert s['nozzle_angles']['expansion_ratio_source'].startswith(
        'ambient-matched')
