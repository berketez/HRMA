# -*- coding: utf-8 -*-
"""V307/SIVI-ORTAM bekçileri (16 Kas 2026) — sıvı motorun tasarım ortamı.

Kusur: sıvı sayfasının tasarım ortamı SABİT deniz seviyesiydi; deniz
seviyesinde ayrılan sabit nozul adlı retle reddedildiği için üst kademe /
vakum motorları (RL10 sınıfı, ε 61) tasarlanamıyordu. Tasarım ortamı artık
girdidir (``design_ambient_mode``: deniz seviyesi / irtifa / basınç / vakum).

Bu dosya BUGÜNKÜ çıktıyı değil FİZİĞİ ve SÖZLEŞMEYİ kilitler:

* özdeşlikler — vakum tasarımında F = ṁ·g0·Isp_vak; irtifa tasarımında
  tasarım itkisi irtifa tablosunun o irtifadaki satırıyla (AYRI yoldan
  kurulan aynı lüle özdeşliği) ve bu dosyada BAĞIMSIZ yazılmış
  F(h) = F_vak − p_a(h)·A_e ile aynı (Sutton & Biblarz 9. bas., Denk. 2-14);
* atmosfer tek modül — tasarım irtifasının basıncı irtifa tablosunun ve
  yörünge çözücüsünün aynı irtifadaki basıncı;
* yayımlanmış motor — RL10A-3-3A boğaz çapı (NASA TM-107318) ve vakum Isp'si
  (NASA CR-190786);
* deniz seviyesi adlı alanlar yalnız gerçek deniz seviyesi değerini taşır
  (nozul orada ayrılıyorsa ``None`` + ``design_ambient.sea_level`` hükmü);
* varsayılan (deniz seviyesi) yol: kip gönderilmezse ve eşdeğer üç
  yazımda (sea_level, irtifa 0 m, basınç 1,01325 bar) bütün sayılar aynı.

Kanıt ve ölçümler: docs/scofield/raw/OH/V307/sivi-ortam/RAPOR.md.
"""
import contextlib
import io
import json
import math
import pathlib
import re
import shutil
import subprocess
import warnings

import pytest

from hrma.constants import G_0, isa_pressure
from hrma.engines import liquid_rocket_engine as lre

ROOT = pathlib.Path(__file__).resolve().parents[1]
SABLON = ROOT / 'hrma' / 'templates' / 'liquid.html'
SAYFA_SOZLUK = ROOT / 'hrma' / 'static' / 'js' / 'i18n_pages.js'
ORTAK_SOZLUK = ROOT / 'hrma' / 'static' / 'js' / 'i18n_common.js'
GRAFIK_SOZLUK = ROOT / 'hrma' / 'static' / 'js' / 'i18n_charts.js'
HOST = {'Host': '127.0.0.1:8080'}

#: Mühendis turu L3 gövdesi (basınç beslemeli, ablatif; 5 kN, 30 bar).
#: ε 50 deniz seviyesinde ayrılır (ayrılmayan en büyük ε 10,35 —
#: tests/test_v306_sivi_ceket_b.py); ε 8 deniz seviyesinde yapışıktır.
L3 = {
    "fuel_type": "rp1", "oxidizer_type": "lox", "oxidizer_density": 1141.16,
    "oxidizer_viscosity": 0.0001947, "mixture_ratio": 2.4, "of_min": 2,
    "of_max": 3.2, "combustion_efficiency": 97, "engine_cycle": "pressure_fed",
    "thrust": 5000, "chamber_pressure": 30, "feed_pressure": 45,
    "injector_type": "unlike_impinging", "injector_pressure_drop": 6,
    "discharge_coefficient": 0.7, "injector_elements": 36,
    "characteristic_length": 1.2, "contraction_ratio": 4,
    "chamber_material": "steel_4130", "chamber_roughness": 3.2,
    "cooling_type": "ablative", "nozzle_expansion_ratio": 50,
    "nozzle_type": "bell_80", "coolant_flow_percent": 100,
    "film_cooling_percent": 0, "coolant_inlet_temp": 300,
    "max_wall_temp": 800, "min_throttle": 40, "max_burn_duration": 36,
    "safety_factor": 2.5, "engine_life_cycles": 10}

P_DS = 1.01325           # bar, ISA 0 m (US Standard Atmosphere 1976)
R_JEO = 6356766.0        # m, ISA geopotansiyel yarıçapı (aynı kaynak)


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **k)


_MOTOR = {}


def motor(**ek):
    """L3 gövdesiyle motor API koşusu (harita taraması atlanır: hız)."""
    anahtar = json.dumps(ek, sort_keys=True)
    if anahtar not in _MOTOR:
        govde = dict(L3, **ek)

        def kur():
            m = lre.LiquidRocketEngine(
                thrust=govde['thrust'],
                chamber_pressure=govde['chamber_pressure'],
                mixture_ratio=govde['mixture_ratio'],
                fuel_type=govde['fuel_type'],
                oxidizer_type=govde['oxidizer_type'],
                cooling_type=govde['cooling_type'],
                injector_type=govde['injector_type'],
                propellant_data={'rp1': {}, 'lox': {}}, overrides=govde)
            m._skip_optimization_maps = True
            return m, m.calculate_performance()
        _MOTOR[anahtar] = _sessiz(kur)
    return _MOTOR[anahtar]


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(client, govde):
    def git():
        return client.post('/calculate_liquid', json=govde, headers=HOST)
    r = _sessiz(git)
    return r.status_code, r.get_json()


def _isa_bar(h):
    """Bu dosyanın KENDİ ISA okuması: geometrik → geopotansiyel, tek modül."""
    return isa_pressure(h * R_JEO / (R_JEO + h)) / 1e5


def _satir(r, irtifa):
    return next(s for s in r['altitude_performance']
                if s['altitude'] == irtifa)


def _cikis_alani(r):
    return math.pi * (r['exit_diameter_mm'] / 2000.0) ** 2


# ---------------------------------------------------------------------------
# 1. Varsayılan deniz seviyesi + eşdeğer yazımlar
# ---------------------------------------------------------------------------
def test_sabit_deniz_seviyesi_basinci_isa_tabani():
    assert lre.SEA_LEVEL_PRESSURE_BAR == P_DS
    assert lre.SEA_LEVEL_PRESSURE_BAR == isa_pressure(0.0) / 1e5


def test_varsayilan_tasarim_ortami_deniz_seviyesi():
    m, r = motor(nozzle_expansion_ratio=8)
    assert m.P_a == P_DS and m.design_ambient_is_sea_level is True
    da = r['design_ambient']
    assert da['mode'] == 'sea_level' and da['source'] == 'sea_level_default'
    assert da['is_sea_level'] is True and da['pressure_bar'] == P_DS
    assert da['altitude_m'] is None
    # Deniz seviyesi tasarımında iki ad aynı sayıdır; ortak başlık adı
    # (specific_impulse) yalnız deniz seviyesi DIŞINDAKİ tasarımda eklenir.
    assert r['isp_design_ambient'] == r['isp_sea_level']
    assert da['isp_design_ambient_s'] == r['isp_sea_level']
    assert da['isp_sea_level_s'] == r['isp_sea_level']
    assert da['thrust_design_ambient_N'] == r['thrust'] == 5000
    assert 'specific_impulse' not in r
    ds = da['sea_level']
    assert ds['status'] == 'attached' and ds['flow_separated'] is False
    assert ds['thrust_N'] == r['thrust'] and ds['isp_s'] == r['isp_sea_level']
    assert 'inputs_not_used' not in r or all(
        b['field'] not in (lre.DESIGN_AMBIENT_ALTITUDE_FIELD,
                           lre.DESIGN_AMBIENT_PRESSURE_FIELD)
        for b in r['inputs_not_used'])


@pytest.mark.parametrize('ek', [
    {'design_ambient_mode': 'sea_level'},
    {'design_ambient_mode': 'altitude', 'design_ambient_altitude_m': 0},
    {'design_ambient_mode': 'pressure',
     'design_ambient_pressure_bar': 1.01325},
])
def test_deniz_seviyesinin_uc_yazimi_varsayilanla_ayni_sayilar(ek):
    """Deniz seviyesi basıncı hangi yoldan söylenirse söylensin tasarım
    aynıdır: künyenin kip/kaynak/irtifa alanları dışında her yaprak aynı."""
    _m0, r0 = motor(nozzle_expansion_ratio=8)
    m1, r1 = motor(nozzle_expansion_ratio=8, **ek)
    assert m1.P_a == P_DS and m1.design_ambient_is_sea_level is True

    def soy(r):
        k = json.loads(json.dumps(r, sort_keys=True, default=repr))
        for ad in ('mode', 'source', 'altitude_m'):
            k['design_ambient'].pop(ad)
        return k
    assert soy(r1) == soy(r0)
    assert r1['design_ambient']['mode'] == ek['design_ambient_mode']


# ---------------------------------------------------------------------------
# 2. Vakum tasarımı: özdeşlikler ve deniz seviyesi adlı alanlar
# ---------------------------------------------------------------------------
def test_vakum_tasariminda_itki_vakum_itkisidir():
    m, r = motor(design_ambient_mode='vacuum')
    assert m.P_a == 0.0 and r['design_ambient']['pressure_bar'] == 0.0
    assert r['thrust'] == 5000
    assert r['thrust_vacuum'] == pytest.approx(r['thrust'], rel=1e-12)
    isp_ozdeslik = r['thrust'] / (r['total_mass_flow'] * G_0)
    assert isp_ozdeslik == pytest.approx(r['isp_vacuum'], rel=1e-12)
    assert r['isp_design_ambient'] == pytest.approx(r['isp_vacuum'],
                                                    rel=1e-12)
    assert r['specific_impulse'] == r['isp_design_ambient']
    # Boğaz o debiyle boyutlanır: A_t = ṁ·c*/(P_c·C_D).
    a_t = math.pi * (r['throat_diameter_mm'] / 2000.0) ** 2
    assert a_t == pytest.approx(
        r['total_mass_flow'] * r['c_star'] / (30e5 * m.CD_throat), rel=1e-9)


def test_vakum_tasariminda_ayrilan_nozul_gecerli_ve_deniz_seviyesi_adiyla():
    """ε 50 / 30 bar deniz seviyesinde ayrılır (3.0.6 reddi); vakum
    tasarımında GEÇERLİDİR ve deniz seviyesi durumu ayrıca yayımlanır."""
    m, r = motor(design_ambient_mode='vacuum')
    assert m.fixed_nozzle_separation_refusal() is None
    assert 'warn.liquid.flow_separation' not in {
        w['code'] for w in r['input_warnings']}
    da = r['design_ambient']
    ds = da['sea_level']
    assert ds['status'] == 'separated' and da['sea_level_flow_separated']
    assert ds['exit_pressure_bar'] < ds['separation_pressure_bar']
    assert ds['separation_pressure_bar'] == pytest.approx(0.4 * P_DS)
    # "Ayrılır" hükmünde sayı yayımlanmaz (bağlı akış bağıntısı geçersiz).
    assert ds['thrust_N'] is None and ds['isp_s'] is None
    assert ds['not_published_reason']
    assert r['isp_sea_level'] is None and da['isp_sea_level_s'] is None
    perf = r['design_summary']['performance']
    assert perf['thrust_sl_N'] is None and perf['isp_sl_s'] is None
    assert perf['thrust_design_ambient_N'] == 5000
    # Deniz seviyesinde yapışık en büyük ε. V307/ONARIM-İTKİ-A (M7-ITKI-1):
    # 3.0.6'nın sayısı 10,35'ti ve ε 50 lülesinin γ'sıyla (1,1568) çözülüyordu;
    # oysa kabul testi ε'daki tasarımın KENDİ γ'sıyla yapılır ve 10,61'lik
    # lüle deniz seviyesinde kabul ediliyordu (ret metni ile kabul çelişkisi).
    # Kök artık γ(ε) ile öz-tutarlı: 10,61 (ölçüm: ε 10,61 kabul, 10,62 ret;
    # docs/scofield/raw/OH/V307/onarim-itki-a/RAPOR.md).
    assert ds['max_attached_expansion_ratio_2dp'] == pytest.approx(
        10.61, abs=0.005)
    assert da['design_point']['flow_separated'] is False
    assert da['design_point']['max_attached_expansion_ratio_status'] == \
        'unbounded_in_vacuum'
    # 0 m satırı da sayı taşımaz, nedeni satırın kendisinde.
    s0 = _satir(r, 0)
    assert s0['flow_separated'] is True
    assert s0['thrust'] is None and s0['specific_impulse'] is None
    assert 'Summerfield' in s0['not_modelled_reason']
    # Vakuma yakın satır tasarım noktasına oturur.
    s100 = _satir(r, 100000)
    assert s100['flow_separated'] is False
    assert s100['thrust'] == pytest.approx(5000, rel=1e-5)


def test_vakum_tasariminda_yapisik_nozulun_deniz_seviyesi_itkisi():
    """ε 8 deniz seviyesinde yapışık: deniz seviyesi itkisi aynı lüle
    özdeşliğidir, F_dş = F_vak − p_dş·A_e (bu dosyada bağımsız yazıldı)."""
    _m, r = motor(design_ambient_mode='vacuum', nozzle_expansion_ratio=8)
    ds = r['design_ambient']['sea_level']
    assert ds['status'] == 'attached'
    beklenen = r['thrust_vacuum'] - P_DS * 1e5 * _cikis_alani(r)
    assert ds['thrust_N'] == pytest.approx(beklenen, rel=1e-9)
    assert ds['isp_s'] == pytest.approx(
        beklenen / (r['total_mass_flow'] * G_0), rel=1e-9)
    assert r['isp_sea_level'] == ds['isp_s']
    perf = r['design_summary']['performance']
    assert perf['thrust_sl_N'] == ds['thrust_N']
    assert perf['isp_sl_s'] == ds['isp_s']
    assert r['isp_sea_level'] < r['isp_design_ambient'] == r['isp_vacuum']


# ---------------------------------------------------------------------------
# 3. İrtifa tasarımı: çapraz bekçi (aynı lüle, aynı atmosfer)
# ---------------------------------------------------------------------------
def test_tasarim_irtifasinin_basinci_tek_atmosfer_modulunden():
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    for h in (0.0, 1000.0, 10000.0, 20000.0, 50000.0, 80000.0):
        bizim = lre.LiquidRocketEngine.isa_ambient_pressure_bar(h)
        assert bizim == pytest.approx(_isa_bar(h), rel=1e-12)
    # Yörünge çözücüsünün atmosferi (aynı irtifa, aynı basınç).
    ta = TrajectoryAnalyzer()
    for h in (0.0, 5000.0, 10000.0, 30000.0, 80000.0):
        assert lre.LiquidRocketEngine.isa_ambient_pressure_bar(h) == \
            pytest.approx(ta._atm_full(h)[1] / 1e5, rel=1e-12), h


def test_irtifa_tasarimi_tablonun_ayni_irtifa_satirina_oturur():
    m, r = motor(design_ambient_mode='altitude',
                 design_ambient_altitude_m=10000, nozzle_expansion_ratio=8)
    p_a = _isa_bar(10000.0)
    assert m.P_a == pytest.approx(p_a, rel=1e-12)
    da = r['design_ambient']
    assert da['source'] == 'altitude_isa' and da['altitude_m'] == 10000.0
    s = _satir(r, 10000)
    # Tablo satırının atmosferi tasarım ortamının basıncıdır.
    assert s['pressure'] == pytest.approx(p_a, rel=1e-12)
    # (a) Tablo o satırda tasarım itkisini ve Isp'sini verir.
    assert s['thrust'] == pytest.approx(r['thrust'], rel=1e-9)
    assert s['specific_impulse'] == pytest.approx(
        r['isp_design_ambient'], rel=1e-9)
    # (b) Bağımsız ölçüm: F(h) = F_vak − p_a(h)·A_e, her yayımlanan satırda.
    a_e = _cikis_alani(r)
    for satir in r['altitude_performance']:
        if satir['thrust'] is None:
            continue
        p_h = _isa_bar(float(satir['altitude']))
        assert satir['thrust'] == pytest.approx(
            r['thrust_vacuum'] - p_h * 1e5 * a_e, rel=1e-7), satir['altitude']
    # Deniz seviyesi (yer testi): ε 8 yapışık, itki tablonun 0 m satırı.
    ds = da['sea_level']
    assert ds['status'] == 'attached'
    assert ds['thrust_N'] == _satir(r, 0)['thrust']
    assert ds['thrust_N'] == pytest.approx(
        r['thrust_vacuum'] - P_DS * 1e5 * a_e, rel=1e-9)
    assert ds['thrust_N'] < r['thrust'] < r['thrust_vacuum']


def test_basinc_kipi_irtifa_kipiyle_ayni_tasarim():
    _m1, r1 = motor(design_ambient_mode='altitude',
                    design_ambient_altitude_m=10000, nozzle_expansion_ratio=8)
    _m2, r2 = motor(design_ambient_mode='pressure',
                    design_ambient_pressure_bar=_isa_bar(10000.0),
                    nozzle_expansion_ratio=8)
    for alan in ('thrust', 'thrust_vacuum', 'isp_design_ambient',
                 'isp_vacuum', 'isp_sea_level', 'total_mass_flow',
                 'throat_diameter_mm', 'exit_diameter_mm'):
        assert r2[alan] == r1[alan], alan
    assert r2['design_ambient']['source'] == 'entered_pressure'
    assert r2['design_ambient']['altitude_m'] is None


def test_irtifada_yapisik_deniz_seviyesinde_ayrilan_nozul():
    """ε 20 / 30 bar: 10 km'de yapışık (tasarım geçerli), deniz seviyesinde
    ayrık (sayı yok). Ayrılan satırlar tabloda adıyla durur."""
    m, r = motor(design_ambient_mode='altitude',
                 design_ambient_altitude_m=10000, nozzle_expansion_ratio=20)
    assert m.fixed_nozzle_separation_refusal() is None
    da = r['design_ambient']
    assert da['design_point']['flow_separated'] is False
    assert da['sea_level']['status'] == 'separated'
    assert da['sea_level']['thrust_N'] is None
    pe = da['sea_level']['exit_pressure_bar']
    for satir in r['altitude_performance']:
        ayrik = bool(pe < 0.4 * satir['pressure'])
        assert satir['flow_separated'] == ayrik, satir['altitude']
        assert (satir['thrust'] is None) == ayrik, satir['altitude']
    assert _satir(r, 10000)['thrust'] == pytest.approx(5000, rel=1e-9)


def test_tasarim_ortaminda_ayrilan_nozul_adli_kayit():
    """ε 50 / 30 bar 5 km'de de ayrılır: motor kaydı tasarım ortamını taşır
    ve ayrılmayan en büyük ε o ortamın basıncıyla çözülür."""
    m, _r = motor(design_ambient_mode='altitude',
                  design_ambient_altitude_m=5000)
    kayit = m.fixed_nozzle_separation_refusal()
    assert kayit['code'] == lre.FIXED_NOZZLE_SEPARATED_CODE
    assert kayit['design_ambient_mode'] == 'altitude'
    assert kayit['ambient_pressure_bar'] == pytest.approx(_isa_bar(5000.0))
    assert kayit['separation_pressure_bar'] == pytest.approx(
        0.4 * _isa_bar(5000.0))
    eps_max = kayit['max_attached_expansion_ratio']
    # Kökün tanımı: P_e(ε_max, γ(ε_max)) = 0,4·p_a (aynı lüle bağıntısı;
    # V307/ONARIM-İTKİ-A M7-ITKI-1: γ, ε_max'taki tasarımın kendi γ'sı —
    # kabul testiyle aynı fonksiyon; brentq γ toleransı 1e-6).
    g_k = m._gamma_equivalent_at(eps_max)
    assert m._cf_ideal(eps_max, g_k, 0.0)[1] == pytest.approx(
        kayit['separation_pressure_bar'], rel=1e-5)
    assert 10.35 < eps_max < 50


# ---------------------------------------------------------------------------
# 4. Adlı retler (fail-closed)
# ---------------------------------------------------------------------------
RETLER = [
    ({'design_ambient_mode': 'space'},
     lre.DESIGN_AMBIENT_MODE_NOT_RECOGNISED_CODE, 'design_ambient_mode'),
    ({'design_ambient_mode': 'altitude'},
     lre.DESIGN_AMBIENT_VALUE_REQUIRED_CODE, 'design_ambient_altitude_m'),
    ({'design_ambient_mode': 'pressure'},
     lre.DESIGN_AMBIENT_VALUE_REQUIRED_CODE, 'design_ambient_pressure_bar'),
    ({'design_ambient_mode': 'altitude',
      'design_ambient_altitude_m': 90000},
     lre.DESIGN_AMBIENT_VALUE_NOT_ACCEPTED_CODE,
     'design_ambient_altitude_m'),
    ({'design_ambient_mode': 'pressure',
      'design_ambient_pressure_bar': -0.1},
     lre.DESIGN_AMBIENT_VALUE_NOT_ACCEPTED_CODE,
     'design_ambient_pressure_bar'),
    ({'design_ambient_altitude_m': 10000},
     lre.DESIGN_AMBIENT_MODE_REQUIRED_CODE, 'design_ambient_mode'),
    ({'design_ambient_pressure_bar': 0.5},
     lre.DESIGN_AMBIENT_MODE_REQUIRED_CODE, 'design_ambient_mode'),
    ({'design_ambient_mode': 'vacuum', 'nozzle_expansion_ratio': None},
     lre.DESIGN_AMBIENT_EXPANSION_RATIO_REQUIRED_CODE,
     'nozzle_expansion_ratio'),
    ({'design_ambient_mode': 'altitude', 'design_ambient_altitude_m': 10000,
      'nozzle_expansion_ratio': ''},
     lre.DESIGN_AMBIENT_EXPANSION_RATIO_REQUIRED_CODE,
     'nozzle_expansion_ratio'),
]


@pytest.mark.parametrize('ek,kod,alan', RETLER)
def test_kabul_edilmeyen_tasarim_ortami_motoru_kurmaz(ek, kod, alan):
    govde = dict(L3, **ek)
    with pytest.raises(lre.DesignAmbientInputError) as hata:
        _sessiz(lre.LiquidRocketEngine, thrust=5000, chamber_pressure=30,
                mixture_ratio=2.4, propellant_data={'rp1': {}, 'lox': {}},
                overrides=govde)
    assert hata.value.reason_code == kod
    assert hata.value.invalid_fields[0]['field'] == alan
    assert hata.value.message_key == lre.DESIGN_AMBIENT_MESSAGE_KEYS[kod]


@pytest.mark.parametrize('ek,kod,alan', RETLER)
def test_uc_tasarim_ortami_reddi_422_ve_sozlukte(client, ek, kod, alan):
    durum, js = _post(client, dict(L3, **ek))
    assert durum == 422, js
    assert alan in [k['field'] for k in js['invalid_fields']]
    assert not any(k in js for k in ('thrust', 'isp_vacuum',
                                     'total_mass_flow'))
    if js['error_code'] == 'input_not_accepted':
        return      # bant kapısı (ortak sözleşme) aynı alanı adıyla reddetti
    assert js['error_code'] == kod
    sozluk = ORTAK_SOZLUK.read_text(encoding='utf-8')
    metinler = re.findall(r"'" + re.escape(js['message_key'])
                          + r"':\s*'((?:[^'\\]|\\.)*)'", sozluk)
    assert len(metinler) == 2, js['message_key']
    for metin in metinler:
        for yer in re.findall(r'\{(\w+)\}', metin):
            assert yer in js['message_params'], (js['message_key'], yer)
        # Kullanıcı metninde ham alan adı / HTTP kodu yok.
        assert 'design_ambient_' not in metin and '422' not in metin


def test_uc_tasarim_ortaminda_ayrilan_nozul_reddi(client):
    durum, js = _post(client, dict(L3, design_ambient_mode='altitude',
                                   design_ambient_altitude_m=5000))
    assert durum == 422
    assert js['error_code'] == lre.FIXED_NOZZLE_SEPARATED_CODE
    assert js['message_key'] == \
        'err.liquid.fixed_nozzle_separated_design_ambient'
    p = js['message_params']
    assert p['pa_bar'] == pytest.approx(_isa_bar(5000.0), rel=1e-3)
    assert p['pe_bar'] < p['sep_bar'] < p['pa_bar']
    assert 'sea level' not in js['message']
    # Önerilen en büyük ε ile aynı ortamda tasarım yayımlanır.
    durum2, js2 = _post(client, dict(
        L3, design_ambient_mode='altitude', design_ambient_altitude_m=5000,
        nozzle_expansion_ratio=p['eps_max']))
    assert durum2 == 200, js2
    assert js2['design_ambient']['design_point']['flow_separated'] is False


def test_statik_tablo_yolunda_deniz_seviyesi_disi_tasarim_adli_ret(
        monkeypatch):
    """CEA çözümü yokken (yerleşik tablo) irtifa/vakum tasarımı yayımlanmaz:
    tablonun çapaları deniz seviyesi tasarım çapalarıdır."""
    from hrma.engines import cea_bridge
    monkeypatch.setattr(cea_bridge, 'is_rocketcea_available', lambda: False)
    with pytest.raises(lre.DesignAmbientInputError) as hata:
        _sessiz(lre.LiquidRocketEngine, thrust=5000, chamber_pressure=30,
                mixture_ratio=2.4, propellant_data={'rp1': {}, 'lox': {}},
                overrides=dict(L3, design_ambient_mode='vacuum'))
    assert hata.value.reason_code == lre.DESIGN_AMBIENT_NEEDS_CEA_CODE
    # Deniz seviyesi tasarımı aynı yolda kurulmaya devam eder.
    m = _sessiz(lre.LiquidRocketEngine, thrust=5000, chamber_pressure=30,
                mixture_ratio=2.4, propellant_data={'rp1': {}, 'lox': {}},
                overrides=dict(L3, nozzle_expansion_ratio=8))
    assert m.combustion_data_source != 'rocketcea'


def test_kipin_okumadigi_ortam_alani_adiyla_beyan_edilir():
    _m, r = motor(design_ambient_mode='vacuum',
                  design_ambient_altitude_m=10000)
    beyan = [b for b in r['inputs_not_used']
             if b['field'] == 'design_ambient_altitude_m']
    assert len(beyan) == 1
    assert beyan[0]['reason'] == lre.DESIGN_AMBIENT_FIELD_UNUSED_REASON
    assert beyan[0]['submitted'] == 10000.0
    # Beyan edilen alan hiçbir sayıyı oynatmadı.
    _m0, r0 = motor(design_ambient_mode='vacuum')
    for alan in ('thrust_vacuum', 'isp_vacuum', 'total_mass_flow',
                 'throat_diameter_mm'):
        assert r[alan] == r0[alan]


# ---------------------------------------------------------------------------
# 5. Deniz seviyesi adlı zincir alanları (çevrim / film / kısma)
# ---------------------------------------------------------------------------
def _yapraklar(x, yol=()):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _yapraklar(v, yol + (str(k),))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _yapraklar(v, yol + (str(i),))
    else:
        yield yol, x


def test_deniz_seviyesi_adli_hicbir_yaprak_tasarim_ortami_degeri_tasimaz():
    """Vakum tasarımında (nozul deniz seviyesinde ayrık) adı deniz seviyesi
    diyen SAYISAL her yaprak ya None'dır ya da 1,01325 bar sabitinin
    kendisi/eşiğidir; tasarım ortamının (vakum) Isp'si o adların altında
    durmaz."""
    _m, r = motor(design_ambient_mode='vacuum', film_cooling_percent=5,
                  cooling_type='film_cooling')
    isp_tasarim = r['isp_design_ambient']
    desen = re.compile(r'(sea_level|(^|_)sl(_|$))')
    supheli = []
    for yol, v in _yapraklar(r):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        adlar = [p for p in yol if desen.search(p)]
        if not adlar:
            continue
        if yol[:2] == ('design_ambient', 'sea_level') and yol[-1] in (
                'ambient_pressure_bar', 'exit_pressure_bar',
                'separation_pressure_bar', 'separation_pressure_ratio',
                'max_attached_expansion_ratio',
                'max_attached_expansion_ratio_2dp'):
            continue
        if abs(v - isp_tasarim) < 0.2 * isp_tasarim and v > 100:
            supheli.append(('.'.join(yol), v))
    assert not supheli, supheli
    film = r['cooling_system']['film_cooling']['performance']
    assert film['isp_core_sea_level_s'] is None
    assert film['isp_delivered_sea_level_s'] is None
    assert film['isp_delivered_design_ambient_s'] == isp_tasarim
    assert film['design_ambient_note'] == lre.DESIGN_AMBIENT_RELOCATION_NOTE
    for nokta in r['throttle_map']['points']:
        assert nokta['isp_sea_level'] is None
        assert 'isp_design_ambient' in nokta


def test_vakum_tasariminda_deniz_seviyesi_uyarilari_basilmaz():
    """Deniz seviyesi Isp bandı ve "vakum ⟷ deniz seviyesi iyileşmesi"
    hükümleri deniz seviyesi tasarımına aittir."""
    _m, r = motor(design_ambient_mode='vacuum')
    kodlar = {w['code'] for w in r['input_warnings']}
    assert 'warn.liquid.isp_sea_level_out_of_band' not in kodlar
    assert 'warn.liquid.vacuum_isp_improvement_out_of_band' not in kodlar
    assert 'warn.liquid.expansion_ratio_clamped' not in kodlar
    assert r['nozzle_angles']['expansion_ratio_matched'] is None


# ---------------------------------------------------------------------------
# 6. Yayımlanmış motor: RL10A-3-3A (vakum tasarımı, kayıt girdileri)
# ---------------------------------------------------------------------------
def test_rl10a33a_vakum_tasarimi_yayimlanmis_bogaz_ve_isp():
    """NASA TM-107318 Tablo 2.5.1 + Ek E Şekil E1: boğaz yarıçapı 2,47 in
    (D_t 125,48 mm); NASA CR-190786: 16 500 lbf, 475 psia, O/F 5,0, ε 61,
    Isp_vak ≈ 445 s. Bantlar ölçümden ÖNCE yazıldı (ONGORU.md P2/P3)."""
    kayit = json.loads((ROOT / 'hrma' / 'data' / 'validation_records'
                        / 'liquid' / 'liq-rl10a33a-nominal-spec.json'
                        ).read_text(encoding='utf-8'))
    f_vak = kayit['measured']['thrust_vac_lbf'] * 4.4482216152605
    pc = kayit['inputs']['chamber_pressure_psia'] * 0.0689475729
    d_t_yayim = 2 * kayit['geometry']['throat_radius_in'] * 25.4

    def kur():
        m = lre.LiquidRocketEngine(
            thrust=f_vak, chamber_pressure=pc,
            mixture_ratio=kayit['inputs']['of_ratio'], fuel_type='lh2',
            oxidizer_type='lox', propellant_data={'lh2': {}, 'lox': {}},
            overrides={'nozzle_expansion_ratio':
                       kayit['geometry']['expansion_ratio'],
                       'engine_cycle': kayit['geometry']['cycle'],
                       'design_ambient_mode': 'vacuum'})
        m._skip_optimization_maps = True
        return m, m.calculate_performance()
    m, r = _sessiz(kur)
    assert m.fixed_nozzle_separation_refusal() is None
    assert r['thrust_vacuum'] == pytest.approx(f_vak, rel=1e-12)
    assert r['throat_diameter_mm'] == pytest.approx(d_t_yayim, rel=0.02)
    assert r['isp_vacuum'] == pytest.approx(
        kayit['measured']['isp_vac_s'], rel=0.01)
    assert r['design_ambient']['sea_level']['status'] == 'separated'
    assert r['isp_sea_level'] is None


# ---------------------------------------------------------------------------
# 7. Sayfa: alan, ipucu, gövde, sözlük
# ---------------------------------------------------------------------------
def _html():
    return SABLON.read_text(encoding='utf-8')


def test_formda_tasarim_ortami_alanlari_ve_kipleri():
    html = _html()
    sec = html[html.index('<select id="design_ambient_mode"'):]
    sec = sec[:sec.index('</select>')]
    assert re.findall(r'<option value="([a-z_]+)"', sec) == \
        list(lre.DESIGN_AMBIENT_MODES)
    assert re.findall(r'<option value="([a-z_]+)"', sec)[0] == \
        lre.DESIGN_AMBIENT_MODE_DEFAULT
    for alan, kip in (('design_ambient_altitude_m', 'altitude'),
                      ('design_ambient_pressure_bar', 'pressure')):
        grup = re.search(
            r'<div class="form-group" data-liq-ambient-show="%s"[^>]*>'
            r'(.*?)<input[^>]*\bid="%s"[^>]*>' % (kip, alan), html, re.S)
        assert grup, alan
        assert 'tooltip-icon' in grup.group(1), alan


@pytest.mark.parametrize('alan,anahtar', [
    ('design_ambient_altitude_m', 'liq.ui.design_ambient_altitude_m_tip'),
    ('design_ambient_pressure_bar', 'liq.ui.design_ambient_pressure_bar_tip'),
])
def test_ipucu_kabul_araligi_bant_tablosuyla_ayni(alan, anahtar):
    lo, hi, _etiket, _birim = lre.LIQUID_INPUT_BANDS[alan]
    sozluk = SAYFA_SOZLUK.read_text(encoding='utf-8')
    metinler = re.findall(r"'" + re.escape(anahtar)
                          + r"':\s*'((?:[^'\\]|\\.)*)'", sozluk)
    assert len(metinler) == 2
    en, tr = metinler
    sablon = re.search(r'data-i18n="' + re.escape(anahtar) + r'">([^<]*)<',
                       _html()).group(1)
    aralik_en = '%g-%g' % (lo, hi)
    assert ('Accepted ' + aralik_en) in en
    assert ('Accepted ' + aralik_en) in sablon
    assert ('Kabul aralığı ' + aralik_en.replace('.', ',')) in tr
    etiket = re.search(r'<input[^>]*\bid="%s"[^>]*>' % alan, _html()).group(0)
    assert re.search(r'\bmin="%g"' % lo, etiket), etiket
    assert re.search(r'\bmax="%g"' % hi, etiket), etiket


def test_ipuclari_en_tr_ve_api_adi_yok():
    sozluk = SAYFA_SOZLUK.read_text(encoding='utf-8')
    for anahtar in ('liq.ui.design_ambient', 'liq.ui.design_ambient_tip',
                    'liq.ui.design_ambient_sea_level',
                    'liq.ui.design_ambient_altitude',
                    'liq.ui.design_ambient_pressure',
                    'liq.ui.design_ambient_vacuum',
                    'liq.ui.design_ambient_altitude_m',
                    'liq.ui.design_ambient_altitude_m_tip',
                    'liq.ui.design_ambient_pressure_bar',
                    'liq.ui.design_ambient_pressure_bar_tip',
                    'liq.ui.target_thrust_level_for_the_liquid',
                    'liq.ui.exit_area_to_throat_area_ratio',
                    'liq.msg.engine_isp_design_ambient',
                    'liq.msg.ground_test_attached',
                    'liq.msg.ground_test_separated',
                    'liq.msg.ground_test_eps_max',
                    'liq.js.trajectory_ground_separated'):
        metinler = re.findall(r"'" + re.escape(anahtar)
                              + r"':\s*'((?:[^'\\]|\\.)*)'", sozluk)
        assert len(metinler) == 2, anahtar
        for metin in metinler:
            assert 'design_ambient_' not in metin, anahtar
            assert '/calculate' not in metin and '422' not in metin, anahtar
            assert 'invent' not in metin.lower(), anahtar
            assert 'uydur' not in metin.lower(), anahtar
    # İpucu dört soruyu yanıtlar: birim, etkisi, boşsa ne olur, aralık.
    en, tr = re.findall(
        r"'liq\.ui\.design_ambient_altitude_m_tip':\s*'((?:[^'\\]|\\.)*)'",
        sozluk)
    assert ' m ' in en and 'left blank' in en and 'Accepted' in en
    assert ' m ' in tr and 'boş bırakılırsa' in tr and 'Kabul aralığı' in tr
    # İtki ipucu artık vakum itkisinin girilemediğini söylemez.
    itki_en = re.findall(
        r"'liq\.ui\.target_thrust_level_for_the_liquid':\s*'"
        r"((?:[^'\\]|\\.)*)'", sozluk)[0]
    assert 'cannot be entered' not in itki_en
    assert 'design ambient' in itki_en


def test_ayrilma_reddi_kodunun_tr_karsiligi_var():
    """NK3-S-4: TR ekranda ret metninin başında ham İngilizce kod
    ("[fixed nozzle separated at design ambient]") görünüyordu."""
    kaynak = GRAFIK_SOZLUK.read_text(encoding='utf-8')
    blok = kaynak[kaynak.index('var HAT_ONEKLERI = {'):]
    blok = blok[:blok.index('};')]
    for kod in (lre.FIXED_NOZZLE_SEPARATED_CODE,
                lre.DESIGN_AMBIENT_MODE_NOT_RECOGNISED_CODE,
                lre.DESIGN_AMBIENT_MODE_REQUIRED_CODE,
                lre.DESIGN_AMBIENT_VALUE_REQUIRED_CODE,
                lre.DESIGN_AMBIENT_VALUE_NOT_ACCEPTED_CODE,
                lre.DESIGN_AMBIENT_EXPANSION_RATIO_REQUIRED_CODE,
                lre.DESIGN_AMBIENT_NEEDS_CEA_CODE):
        m = re.search(r"'" + kod + r"':\s*'([^']+)'", blok)
        assert m, kod
        assert not re.search(r'[a-z]_[a-z]', m.group(1)), kod


node_gerekli = pytest.mark.skipif(shutil.which('node') is None,
                                  reason='node yok')


def _fn(html, ad):
    a = html.index('function %s(' % ad)
    derinlik, i = 0, html.index('{', a)
    while True:
        if html[i] == '{':
            derinlik += 1
        elif html[i] == '}':
            derinlik -= 1
            if derinlik == 0:
                return html[a:i + 1]
        i += 1


@node_gerekli
def test_sayfa_govdesi_deniz_seviyesinde_degismez_diger_kipte_alan_tasir():
    """Sayfanın GERÇEK işlevleri (node): deniz seviyesinde gövdeye hiçbir
    alan girmez; başka kipte kip + yalnız o kipin alanı gider."""
    html = _html()
    assert 'liqDesignAmbientPayload()' in _fn(html, 'collectAllParameters')
    kod = '\n'.join([
        re.search(r'const LIQ_AMBIENT_FIELD_OF_MODE = \{[^}]*\};',
                  html).group(0),
        _fn(html, 'liqOptNum'), _fn(html, 'liqDesignAmbientMode'),
        _fn(html, 'liqDesignAmbientPayload'), """
const alanlar = {};
const document = { getElementById: (id) => (id in alanlar ? { value: alanlar[id] } : null) };
function dene(a) {
    Object.keys(alanlar).forEach(k => delete alanlar[k]);
    Object.assign(alanlar, a);
    return liqDesignAmbientPayload();
}
console.log(JSON.stringify([
    dene({}),
    dene({ design_ambient_mode: 'sea_level', design_ambient_altitude_m: '5000' }),
    dene({ design_ambient_mode: 'vacuum', design_ambient_altitude_m: '5000',
           design_ambient_pressure_bar: '0.3' }),
    dene({ design_ambient_mode: 'altitude', design_ambient_altitude_m: '10000',
           design_ambient_pressure_bar: '0.3' }),
    dene({ design_ambient_mode: 'altitude', design_ambient_altitude_m: '' }),
    dene({ design_ambient_mode: 'pressure', design_ambient_pressure_bar: '0' }),
]));
"""])
    cikti = subprocess.run(['node'], input=kod, capture_output=True,
                           text=True, timeout=60)
    assert cikti.returncode == 0, cikti.stderr[:800]
    assert json.loads(cikti.stdout) == [
        {}, {},
        {'design_ambient_mode': 'vacuum'},
        {'design_ambient_mode': 'altitude',
         'design_ambient_altitude_m': 10000},
        {'design_ambient_mode': 'altitude'},
        {'design_ambient_mode': 'pressure', 'design_ambient_pressure_bar': 0},
    ]


# ---------------------------------------------------------------------------
# 8. Proje gidiş-dönüşü (kayıtlı alanlar -> sayfanın hesap ucu)
# ---------------------------------------------------------------------------
def test_proje_alanlarindan_ayni_tasarim(client):
    """Proje dosyası formun BÜTÜN alanlarını saklar (görünmeyen irtifa
    kutusu dahil). Kayıtlı alanlardan kurulan gövde sayfanın gövdesiyle
    aynı motoru verir; bayat alan adıyla beyan edilir."""
    from hrma.analysis.flight_vehicle import page_payload
    sayfa = dict(L3, design_ambient_mode='vacuum')
    alanlar = dict(L3, design_ambient_mode='vacuum',
                   design_ambient_altitude_m=10000,
                   design_ambient_pressure_bar='')
    d1, j1 = _post(client, sayfa)
    d2, j2 = _post(client, page_payload('liquid', alanlar))
    assert d1 == d2 == 200, (j1, j2)
    for alan in ('thrust', 'thrust_vacuum', 'isp_vacuum', 'isp_sea_level',
                 'isp_design_ambient', 'total_mass_flow',
                 'throat_diameter_mm', 'exit_diameter_mm'):
        assert j2[alan] == j1[alan], alan
    assert j2['design_ambient'] == j1['design_ambient']
    assert any(b['field'] == 'design_ambient_altitude_m'
               for b in j2['inputs_not_used'])
    assert j1['design_ambient']['mode'] == 'vacuum'
    assert j1['isp_sea_level'] is None


def test_proje_alanlarinda_deniz_seviyesi_secimi_eski_govdeyle_ayni(client):
    """Kaydedilen projede seçim kutusu 'sea_level' ve boş sayı kutuları
    durur; bu gövde, alanların hiç gönderilmediği gövdeyle aynı sayıları
    verir (eski projeler ve örnekler etkilenmez)."""
    from hrma.analysis.flight_vehicle import page_payload
    eski = dict(L3, nozzle_expansion_ratio=8)
    yeni = page_payload('liquid', dict(
        eski, design_ambient_mode='sea_level',
        design_ambient_altitude_m='', design_ambient_pressure_bar=''))
    d1, j1 = _post(client, eski)
    d2, j2 = _post(client, yeni)
    assert d1 == d2 == 200
    oynak = {'trace_id', 'solver_wall_time_s'}

    def soy(j):
        k = {a: v for a, v in j.items() if a not in oynak}
        k['design_ambient'] = dict(k['design_ambient'], source=None)
        return json.dumps(k, sort_keys=True, default=repr)
    assert soy(j2) == soy(j1)
    assert j2['design_ambient']['source'] == 'sea_level'
    assert j1['design_ambient']['source'] == 'sea_level_default'


# ---------------------------------------------------------------------------
# 9. Uçuşa aktarım: araç yerden kalkar, itki deniz seviyesi itkisidir
# ---------------------------------------------------------------------------
def test_ucus_araci_itkisi_deniz_seviyesi_itkisidir():
    """``flight_vehicle.normalize`` (Yörünge / 6-DOF / Fırlatma Sahası'nın
    TEK araç şeması): deniz seviyesi dışındaki tasarımda aracın itkisi aynı
    nozulun deniz seviyesi itkisidir (irtifa düzeltmesinin referansı
    1,01325 bar); nozul orada ayrılıyorsa araç itkisizdir (uçuş yok)."""
    from hrma.analysis import flight_vehicle as fv
    _m, r_ds = motor(nozzle_expansion_ratio=8)
    arac = _sessiz(fv.normalize, 'liquid', r_ds)
    assert arac['thrust'] == r_ds['thrust'] == 5000
    _m, r_vak = motor(design_ambient_mode='vacuum', nozzle_expansion_ratio=8)
    arac = _sessiz(fv.normalize, 'liquid', r_vak)
    ds = r_vak['design_ambient']['sea_level']
    assert arac['thrust'] == ds['thrust_N'] < r_vak['thrust']
    assert arac['flight_thrust']['thrust'] == ds['thrust_N']
    assert arac['flight_thrust']['thrust_reference_pressure_pa'] == \
        pytest.approx(P_DS * 1e5)
    _m, r_ayrik = motor(design_ambient_mode='vacuum')
    arac = _sessiz(fv.normalize, 'liquid', r_ayrik)
    assert arac['thrust'] is None
    assert arac['flight_thrust']['thrust'] is None


def test_uc_ayrilan_vakum_motoru_icin_arac_kurmaz(client):
    """/api/flight-vehicle: deniz seviyesinde ayrılan vakum tasarımı için
    araç yayımlanmaz (itki kaynağı yok); vakum itkisi yerden uçurulmaz."""
    _m, r = motor(design_ambient_mode='vacuum')
    govde = json.loads(json.dumps(r, default=repr))

    def git():
        return client.post('/api/flight-vehicle', headers=HOST, json={
            'source': 'results', 'motor_type': 'liquid', 'results': govde})
    y = _sessiz(git)
    assert y.status_code == 422, y.get_json()
    assert 'vehicle' not in (y.get_json() or {})


def test_kismada_tasarim_ortaminda_ayrilma_uyarisi_ortami_soyler():
    """ε 20 / 30 bar, 10 km: tasarım noktasında yapışık, kısılınca tasarım
    ortamında ayrılır. Uyarı deniz seviyesi cümlesini DEĞİL tasarım ortamı
    cümlesini taşır (EN + TR sözlükte, yer tutucuları dolu)."""
    _m, r = motor(design_ambient_mode='altitude',
                  design_ambient_altitude_m=10000, nozzle_expansion_ratio=20)
    uyarilar = {w['code']: w for w in r['input_warnings']}
    assert 'warn.liquid.throttle_flow_separation' not in uyarilar
    assert 'warn.liquid.flow_separation' not in uyarilar
    w = uyarilar['warn.liquid.throttle_flow_separation_design_ambient']
    assert w['params']['pa_bar'] == pytest.approx(_isa_bar(10000.0),
                                                  rel=1e-3)
    assert w['params']['threshold_bar'] == pytest.approx(
        0.4 * _isa_bar(10000.0), rel=1e-3)
    sozluk = ORTAK_SOZLUK.read_text(encoding='utf-8')
    for kod in ('warn.liquid.throttle_flow_separation_design_ambient',
                'warn.liquid.flow_separation_design_ambient'):
        metinler = re.findall(r"'" + re.escape(kod)
                              + r"':\s*'((?:[^'\\]|\\.)*)'", sozluk)
        assert len(metinler) == 2, kod
        for metin in metinler:
            assert 'sea level' not in metin
            assert 'deniz seviyesi' not in metin
    for metin in re.findall(
            r"'warn\.liquid\.throttle_flow_separation_design_ambient':\s*'"
            r"((?:[^'\\]|\\.)*)'", sozluk):
        for yer in re.findall(r'\{(\w+)\}', metin):
            assert yer in w['params'], yer
    # Ayrılan kısma noktalarının tasarım ortamı itkisi yayımlanmaz.
    ayrik = [p for p in r['throttle_map']['points']
             if p.get('thrust_n') is None]
    assert ayrik and all(p['isp_design_ambient'] is None for p in ayrik)


@node_gerekli
def test_sayfa_6dof_itkisi_deniz_seviyesi_itkisi_ya_da_adli_ret():
    """Sayfanın GERÇEK işlevi (node): 6-DOF sürüşü tasarım ortamı deniz
    seviyesi değilse deniz seviyesi itkisini uçurur; nozul orada ayrılıyorsa
    sürüş kurulmaz (adlı ret)."""
    html = _html()
    kod = '\n'.join([
        'const LIQUID_G0 = 9.80665;',
        'function _liqKutleToleransi() { return 1e-6; }',
        _fn(html, 'liqDesignAmbientOf'), _fn(html, '_liquidSixDofDriveFrom'),
        """
const ds = { thrust: 5000, total_mass_flow: 2 };
const vakYapisik = { thrust: 5000, total_mass_flow: 2, design_ambient: {
    is_sea_level: false, sea_level: { status: 'attached', thrust_N: 4200 } } };
const vakAyrik = { thrust: 5000, total_mass_flow: 2, design_ambient: {
    is_sea_level: false, sea_level: { status: 'separated', thrust_N: null } } };
console.log(JSON.stringify([
    _liquidSixDofDriveFrom(ds, 20, 20).thrust,
    _liquidSixDofDriveFrom(vakYapisik, 20, 20).thrust,
    _liquidSixDofDriveFrom(vakAyrik, 20, 20),
]));
"""])
    cikti = subprocess.run(['node'], input=kod, capture_output=True,
                           text=True, timeout=60)
    assert cikti.returncode == 0, cikti.stderr[:800]
    assert json.loads(cikti.stdout) == [
        5000, 4200, {'reject': 'ground_separated'}]
    # Köprü: ayrılan tasarımda araç yazılmaz, önceki araç kaldırılır.
    # V307/FS-KÜÇÜK (kalem 4): köprü sonucu her tasarımda yayımlar; uç
    # ayrılan tasarımı adıyla reddeder (sea_level_thrust_not_published),
    # köprü reddi kaydeder ve önceki aracı kaldırır.
    hesap = _fn(html, 'calculateLiquid')
    assert "window.FlightHandoff.publish(results, { motor_type: 'liquid' });" in hesap
    assert 'window.FlightHandoff.clear();' not in hesap


# ---------------------------------------------------------------------------
# 10. İrtifa okuması: geometrik irtifa -> USSA 1976 (tek yardımcı)
# ---------------------------------------------------------------------------
def test_isa_pressure_geometric_yardimcisi():
    """Ana model kararı (16 Kas): kullanıcının irtifası GEOMETRİKtir ve
    tabloya H = h·R/(R + h) ile verilir. ``isa_pressure`` (geopotansiyel
    bekler) değişmedi; yardımcı h = 0'da onunla bit-aynı, 20 km'de yörünge
    çözücüsünün ``_atm_full``uyla 1e-12 içinde aynıdır."""
    from hrma import constants as c
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    assert c.isa_pressure_geometric(0.0) == c.isa_pressure(0.0) == 101325.0
    assert c.geometric_to_geopotential(0.0) == 0.0
    ta = TrajectoryAnalyzer()
    for h in (1000.0, 20000.0, 50000.0, 84000.0):
        assert c.isa_pressure_geometric(h) == pytest.approx(
            ta._atm_full(h)[1], rel=1e-12), h
    # Dönüşümün kendisi (USSA 1976): H = h·r0/(r0 + h), r0 = 6 356 766 m.
    assert c.geometric_to_geopotential(20000.0) == pytest.approx(
        20000.0 * 6356766.0 / 6376766.0, rel=1e-15)
    # Dönüşümsüz okuma aynı sayı DEĞİLDİR (20 km'de ~%1, 50 km'de ~%5).
    assert c.isa_pressure(20000.0) / c.isa_pressure_geometric(20000.0) == \
        pytest.approx(0.990, abs=0.002)
    assert c.isa_pressure(50000.0) / c.isa_pressure_geometric(50000.0) == \
        pytest.approx(0.95, abs=0.01)
    # isa_pressure'ın davranışı değişmedi: geopotansiyel bekler (11 km
    # GEOPOTANSİYEL irtifada tablonun katman taban basıncını verir).
    assert c.isa_pressure(11000.0) == pytest.approx(c.ISA_LAYERS[1][3],
                                                    rel=1e-12)
    assert c.ISA_LAYERS[1][0] == 11000.0


def test_geopotansiyel_yaricap_tek_tanim():
    """r0 merkezde tek tanım; yörünge çözücüsü ve sıvı motor onu okur.
    6-DOF modülünün kendi kopyası aynı değerdir (o dosya bu kulvarın dışı)."""
    from hrma import constants as c
    from hrma.analysis import six_dof_trajectory as sd
    from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer
    assert c.ISA_GEOPOTENTIAL_EARTH_RADIUS_M == 6356766.0
    assert TrajectoryAnalyzer().R_geopotential is \
        c.ISA_GEOPOTENTIAL_EARTH_RADIUS_M
    assert lre.ISA_GEOPOTENTIAL_EARTH_RADIUS_M is \
        c.ISA_GEOPOTENTIAL_EARTH_RADIUS_M
    assert sd.R_GEOPOTENTIAL == c.ISA_GEOPOTENTIAL_EARTH_RADIUS_M
    assert 'ISA_GEOPOTENTIAL_EARTH_RADIUS_M = ' not in (
        ROOT / 'hrma' / 'engines' / 'liquid_rocket_engine.py').read_text(
            encoding='utf-8')


def test_sivi_tasarim_irtifasi_yardimcidan_okunur():
    from hrma import constants as c
    for h in (0.0, 5000.0, 20000.0, 50000.0):
        assert lre.LiquidRocketEngine.isa_ambient_pressure_bar(h) == \
            c.isa_pressure_geometric(h) / 1e5
    kaynak = (ROOT / 'hrma' / 'engines' / 'liquid_rocket_engine.py'
              ).read_text(encoding='utf-8')
    a = kaynak.index('def isa_ambient_pressure_bar(altitude_m):')
    govde = kaynak[a:kaynak.index('def _resolve_design_ambient', a)]
    assert 'isa_pressure_geometric(altitude_m)' in govde


# ---------------------------------------------------------------------------
# 11. Saldırgan / bozuk girdi: adlı ret, sunucu hatası yok
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('ek', [
    {'design_ambient_mode': 123},
    {'design_ambient_mode': ['vacuum']},
    {'design_ambient_mode': {'a': 1}},
    {'design_ambient_mode': True},
    {'design_ambient_mode': 'V' * 20000},
    {'design_ambient_mode': 'vacuum\x00'},
    {'design_ambient_mode': 'altitude', 'design_ambient_altitude_m': 'abc'},
    {'design_ambient_mode': 'altitude', 'design_ambient_altitude_m': [1]},
    {'design_ambient_mode': 'altitude', 'design_ambient_altitude_m': True},
    {'design_ambient_mode': 'altitude', 'design_ambient_altitude_m': 'NaN'},
    {'design_ambient_mode': 'altitude', 'design_ambient_altitude_m': '1e999'},
    {'design_ambient_mode': 'altitude', 'design_ambient_altitude_m': -1},
    {'design_ambient_mode': 'pressure',
     'design_ambient_pressure_bar': {'x': 1}},
    {'design_ambient_mode': 'pressure', 'design_ambient_pressure_bar': 5},
    {'design_ambient_mode': 'vacuum', 'nozzle_expansion_ratio': 'x'},
    {'design_ambient_mode': 'vacuum', 'nozzle_expansion_ratio': [61]},
])
def test_bozuk_tasarim_ortami_girdisi_adli_ret(client, ek):
    durum, js = _post(client, dict(L3, **ek))
    assert durum in (400, 422), (durum, js)
    assert isinstance(js, dict) and js.get('error')
    assert 'thrust_vacuum' not in js and 'design_ambient' not in js
    # Yankı sınırlı: dev girdi yanıta olduğu gibi dönmez.
    assert len(json.dumps(js)) < 6000
