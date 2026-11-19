"""V307/TEK-TANIM — aynı büyüklüğün iki tanımı / iki hesabı TEK yoldan.

Kalem 7 (CI-KIRMIZI K1): çalkantı birinci kip frekansı. Motor kartının f1'i
``CylindricalTankSlosh.natural_frequency`` ayrı bir numpy ifadesiyle, motorun
kendi derinliğinde (V_gerek/(πR²)); tablonun f1'i ise m0/(ρ·V_iç) dolulukta
(0,9499999999999995 — düğüm değil) log-log PCHIP ara değeriydi. macOS'taki
eşitlik rastlantıydı, Linux'ta 2 ulp ayrıştı. Şimdi: κ1 ve ω1 tek işlevden
(``_kappa_tanh`` + ``slosh_tablo.omega1``), derinlik tek işlevden
(``silindir_dolu_yukseklik``), yüklü doluluk motorun tasarım doluluğundan
(ızgara düğümü). Bekçiler platform farkını TAKLİT eder (rastgele girdi,
kütle dolulukunun ulp kaydırılması); iki yol ayrı formül olursa macOS'ta da
KIRMIZI olurlar (ters mutasyon: docs/scofield/raw/OH/V307/tek-tanim/RAPOR.md).
"""
import math
import random

import pytest

from hrma.analysis import slosh_analysis as sa
from hrma.analysis import slosh_motor_baglanti as smb
from hrma.analysis import slosh_tablo as st
from hrma.constants import G_0


# ---------------------------------------------------------------------------
# Kalem 7 — çalkantı f1: motor kartı ⟷ tablo düğüm satırı
# ---------------------------------------------------------------------------
def _f1_tablo(satir):
    # slosh_motor_baglanti._tank_raporu'daki 'tablo' ifadesi.
    return math.sqrt(satir['kappa1_1m'] * G_0) / (2.0 * math.pi)


def test_motor_f1_tablo_dugum_satiri_ile_bit_ayni_rastgele_girdide():
    rnd = random.Random(20261118)
    sayac = 0
    for _ in range(150):
        R = rnd.uniform(0.03, 2.0)
        H = R * rnd.uniform(0.6, 6.0)
        rho = rnd.uniform(400.0, 1500.0)
        tablo = sa.silindir_tablosu('yakit', R, H, rho, 'sivi')
        for d in (0.85, 0.95, rnd.choice(st.DOLULUK_IZGARASI)):
            h = sa.silindir_dolu_yukseklik(R, H, d)
            satir = tablo.ara(d)
            assert satir['h_m'] == h                       # aynı derinlik
            omega, f = sa.CylindricalTankSlosh(R, h).natural_frequency(1)
            assert f == _f1_tablo(satir)                   # tek hesap
            # analyze() (motor kartının yayımladığı f1) aynı sayı
            assert sa.analyze_slosh(R, h, fluid_density=rho)['f1_hz'] == f
            sayac += 1
    assert sayac == 450


def test_kappa_tek_ifade_esdeger_model_ve_frekans():
    rnd = random.Random(7)
    for _ in range(200):
        R = rnd.uniform(0.02, 3.0)
        h = rnd.uniform(1e-3, 8.0)
        g = rnd.uniform(0.5, 60.0)
        m = sa.silindir_esdeger_model(R, h)
        ts = sa.CylindricalTankSlosh(R, h, g_eff=g)
        assert ts.natural_frequency(1)[0] == st.omega1(m['kappa1_1m'], g)
        assert ts.natural_frequency(2)[0] == st.omega1(m['kappa2_1m'], g)


def test_dolum_taramasi_son_noktasi_motor_f1():
    """Motor kartının dolum taraması (fill_sweep) h = fill_height noktasında
    f1 ile aynı sayı (eski ayrı numpy ifadesi ~%22 tasarımda son basamakta
    ayrışıyordu)."""
    import numpy as np
    rnd = random.Random(3)
    for _ in range(300):
        R, h = rnd.uniform(0.03, 2.0), rnd.uniform(0.01, 5.0)
        m = sa.CylindricalTankSlosh(R, h)
        sw = m.fill_sweep(np.linspace(0.02, 1.0, 25) * h)
        assert sw['f1_hz'][-1] == m.natural_frequency(1)[1]


def _aday(tablo, m0, d_tas):
    return {'tablo': tablo, 'm0': m0, 'tasarim_dolulugu': d_tas}


@pytest.mark.parametrize('k', [-4, -1, 0, 1, 3])
def test_yuklu_doluluk_tasarim_dugumu_ulp_kaymasinda(k):
    """m0/(ρ·V_iç) platforma göre son bitte kayar (Linux: 0,9499999999999995);
    yüklü doluluk motorun tasarım doluluğu (düğüm) olarak kalır."""
    R, H, rho = 0.21410644638867327, 1.0705322319433663, 1000.0
    tablo = sa.silindir_tablosu('yakit', R, H, rho, 'sivi')
    V = tablo.geometri['V_ic_m3']
    d = 0.95
    for _ in range(abs(k)):
        d = math.nextafter(d, math.inf if k > 0 else -math.inf)
    m0 = d * rho * V
    assert smb._yuklu_doluluk(_aday(tablo, m0, 0.95)) == 0.95


def test_yuklu_doluluk_tasarimla_tutarsizsa_kutleden():
    """Tasarım doluluğu yüklü kütleyle tutmuyorsa (ör. kullanıcının tank
    geometrisi) m0/(ρ·V_iç) kullanılır; düğüme zorla çekilmez."""
    tablo = sa.silindir_tablosu('yakit', 0.3, 1.2, 800.0, 'sivi')
    m0 = 0.6 * 800.0 * tablo.geometri['V_ic_m3']
    d = smb._yuklu_doluluk(_aday(tablo, m0, 0.95))
    assert d == tablo.doluluk_kutleden(m0)
    assert smb._yuklu_doluluk(_aday(tablo, m0, None)) == d


# ---------------------------------------------------------------------------
# Kalem 5 — hibrit irtifa tablosu C_F: tek tanım F/(P_c·A_t), başlıkla aynı
# ---------------------------------------------------------------------------
import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import types  # noqa: E402

from hrma.engines import combustion_analysis as ca  # noqa: E402

_H = [0.0, 1000.0, 5000.0, 10000.0, 15000.0, 20000.0]


def _irtifa(cf_b, f_b, mdot, c_star_ideal, P_cap_pa, rnd):
    v_e = rnd.uniform(1800.0, 2600.0)
    P_e = rnd.uniform(0.7, 1.2)
    A_e = rnd.uniform(5e-4, 2e-2)
    motor = {'performance': {'velocities': {'exit': v_e},
                             'c_star': c_star_ideal},
             'conditions': {'exit': {'P': P_e, 'T': rnd.uniform(1500, 2200)}},
             'gas_constants': {'exit': rnd.uniform(280, 380)},
             'mdot_total': mdot, 'thrust_sea_level': f_b,
             'thrust_coefficient': cf_b, 'exit_area_m2': A_e,
             'thrust_reference_pressure_pa': P_cap_pa}
    oz = types.SimpleNamespace(
        _fixed_nozzle_altitude_sweep=ca.CombustionAnalyzer.
        _fixed_nozzle_altitude_sweep)
    return ca.CombustionAnalyzer.calculate_altitude_performance(oz, motor, _H)


def test_satir_cf_baslik_tanimi_ve_tasarim_satiri_bit_ayni():
    rnd = random.Random(5)
    capali = 0
    for _ in range(100):
        mdot = rnd.uniform(0.2, 5.0)
        cf_b = rnd.uniform(1.2, 1.8)
        c_star_ideal = rnd.uniform(1300.0, 1700.0)
        f_b = cf_b * mdot * c_star_ideal * rnd.uniform(0.85, 0.97)
        r = _irtifa(cf_b, f_b, mdot, c_star_ideal, 101325.0, rnd)
        satirlar = r['altitude_performance']
        assert satirlar[0]['altitude'] == 0.0
        if r['nozzle_loss_model']['anchored_to_delivered_thrust']:
            assert satirlar[0]['thrust'] == f_b
            assert satirlar[0]['cf'] == cf_b        # başlığın KENDİSİ
            capali += 1
        for s in satirlar:
            assert s['cf'] == cf_b * (s['thrust'] / f_b)
            # eski tanım (F/(ṁ·c*_ideal) = C_F·η_c*) DEĞİL
            assert s['cf'] != s['thrust'] / (mdot * c_star_ideal)
    assert capali >= 40


def test_baslik_verilmezse_cagiranin_c_yildiziyla():
    assert ca._altitude_row_cf(1000.0, None, None, 0.5, 1500.0) == \
        1000.0 / (0.5 * 1500.0)
    assert ca._altitude_row_cf(1000.0, float('nan'), 900.0, 0.5, 1500.0) == \
        1000.0 / (0.5 * 1500.0)


@pytest.mark.slow
def test_hibrit_ornek_isa_tasarimda_0m_satiri_baslik_cf():
    from hrma.analysis import flight_vehicle as fv
    from hrma.app import app  # noqa: F401
    from tests.test_example_projects import NAMES
    kok = pathlib.Path(__file__).resolve().parents[1]
    doc = json.loads((kok / 'examples' / (NAMES['hybrid'] + '.hrma'))
                     .read_text(encoding='utf-8'))
    alan = dict(doc['inputs']['fields'], single_pressure=1.01325)
    with contextlib.redirect_stdout(io.StringIO()):
        durum, g = fv.run_page_calculation('hybrid',
                                           fv.page_payload('hybrid', alan))
    assert durum == 200
    m = g.get('motor', g)
    s0 = m['altitude_performance']['altitude_performance'][0]
    assert s0['altitude'] == 0 and s0['cf'] == m['cf']


# ---------------------------------------------------------------------------
# Kalem 6 — hibrit varsayılan tasarım ortamı: ISA deniz seviyesi, tek ad
# ---------------------------------------------------------------------------
def test_varsayilan_ortam_isa_tek_kaynaktan():
    import hrma.app as appmod
    from hrma.constants import BAR_PER_PA, P_SEA_LEVEL_PA
    from hrma.engines import hybrid_rocket_engine as hre
    assert hre.HYBRID_DEFAULT_AMBIENT_BAR == P_SEA_LEVEL_PA * BAR_PER_PA
    assert hre.HYBRID_DEFAULT_AMBIENT_BAR == 1.01325
    assert appmod._HYBRID_AMBIENT_DEFAULT_BAR == hre.HYBRID_DEFAULT_AMBIENT_BAR


@pytest.mark.slow
def test_belirsizlik_nominali_calculate_varsayilaniyla_ayni():
    """Belirsizlik fabrikası ortamı istekten okur; yoksa /calculate ile
    AYNI varsayılan (eski: fabrika 1,0 yazıyordu)."""
    import warnings
    from hrma.analysis import uq_adapters
    from hrma.app import app
    from tests.test_v307_hibrit_ortam import HIBRIT_ORTAM_GOVDE
    c = app.test_client()
    with contextlib.redirect_stdout(io.StringIO()), \
            warnings.catch_warnings():
        warnings.simplefilter('ignore')
        m = c.post('/calculate',
                   json=dict(HIBRIT_ORTAM_GOVDE)).get_json()['motor']
        nom = uq_adapters.make_hybrid_factory(dict(HIBRIT_ORTAM_GOVDE))({})
        nom_istek = uq_adapters.make_hybrid_factory(
            dict(HIBRIT_ORTAM_GOVDE, atmospheric_pressure=0.5))({})
    assert m['design_ambient']['pressure_bar'] == 1.01325
    assert nom['isp'] == m['isp']
    assert nom_istek['isp'] != nom['isp']     # isteğin ortamı okunur
