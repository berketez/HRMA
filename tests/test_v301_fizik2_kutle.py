"""V301/FİZİK-2 kalem 4 (CAD-2 DEVİR 2) — iki katmanlı cidarda kütle tek kaynak.

ÖLÇÜLEN KUSUR (docs/scofield/raw/OH/V301/fizik-2/k4_kutle_once.json, örnek
sıvı 5fa435893): kütle dökümü kamara 5,776 / lüle 3,542 kg ⟷ CAD 4,817 /
6,380 kg. Bağımsız ölçüm (çizilen iki katmanın kesik koni hacmi × yoğunluk,
yerel kaburga payı) CAD'in sayısını veriyor; motorun sayısı iki kaynaksız
çarpandan (1,20 birleşim payı, 0,60 lüle kalınlık oranı) sapıyordu.
Sonra (k4_kutle_sonra.json): kütle dökümü = Tasarım Özeti = uçuş aracı =
CAD; kaynak CAD'in tek işlevi.
"""
import contextlib
import copy
import io
import json
import math
import pathlib

import pytest

from hrma.export import cad_visualization as CV
from hrma.export.motor_geometry import normalise_export_geometry
from tests.support import kabul

KOK = pathlib.Path(__file__).resolve().parents[1]
H = {'Host': '127.0.0.1:8080'}


def _sessiz(fn, *a, **k):
    t = io.StringIO()
    with contextlib.redirect_stdout(t), contextlib.redirect_stderr(t):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def sivi(client):
    r = _sessiz(client.post, '/calculate_liquid',
                json=kabul.sayfa_yuku('liquid'), headers=H)
    assert r.status_code == 200
    s = r.get_json()
    assert s['structural_analysis']['chamber_structure']['wall_model'] == \
        'two_layer_regenerative'
    return s


@pytest.fixture(scope='module')
def cad(sivi):
    out = _sessiz(CV.MotorCADDesigner().generate_3d_motor_assembly,
                  copy.deepcopy(sivi))
    return out['performance_summary']['mass_breakdown']


def _kesik_koni(r0, r1, dz):
    return math.pi / 3.0 * abs(dz) * (r0 * r0 + r0 * r1 + r1 * r1)


def _bagimsiz_lule(sivi):
    """Kâhin: lüle ceketinin kesik koni hacmi × yoğunluk (orta yarıçap
    yaklaşımı yok; yalnız kaburga payı parça ortasında)."""
    md, _ = normalise_export_geometry(copy.deepcopy(sivi))
    geo = CV.two_layer_wall_cad_geometry(md)
    pts = CV.nozzle_wall_profile(md, unit='mm')['inner']
    t_l, h, t_c = geo['liner_mm'], geo['channel_mm'], geo['closeout_mm']
    m = 0.0
    for (z0, r0), (z1, r1) in zip(pts[:-1], pts[1:]):
        dz = z1 - z0
        for a, b, rho, kab in ((0.0, t_l, geo['liner']['density'], False),
                               (t_l, t_l + h, geo['liner']['density'], True),
                               (t_l + h, t_l + h + t_c,
                                geo['closeout']['density'], False)):
            v = (_kesik_koni(r0 + b, r1 + b, dz)
                 - _kesik_koni(r0 + a, r1 + a, dz)) * 1e-9
            if kab:
                d = 2.0 * ((r0 + r1) / 2.0 + t_l + h / 2.0)
                v *= max(0.0, 1.0 - geo['n_channels'] * geo['channel_w_mm']
                         / (math.pi * d))
            m += v * rho
    return m


def test_dokum_cad_ile_ayni(sivi, cad):
    cm = sivi['component_sizing']['component_masses']
    assert cm['combustion_chamber'] == pytest.approx(cad['chamber_mass'],
                                                     rel=1e-12)
    assert cm['nozzle_assembly'] == pytest.approx(cad['nozzle_mass'],
                                                  rel=1e-12)
    kayit = sivi['component_sizing']['two_layer_mass_single_source']
    assert kayit['status'] == 'applied'
    assert '_estimate_component_mass' in kayit['source']


def test_lule_kutlesi_hacim_x_yogunluk(sivi):
    cm = sivi['component_sizing']['component_masses']
    assert cm['nozzle_assembly'] == pytest.approx(_bagimsiz_lule(sivi),
                                                  rel=1e-9)


def test_toplam_ozet_uc_ve_ucus_ayni_sayi(client, sivi):
    cm = sivi['component_sizing']['component_masses']
    parca = sum(cm[k] for k in ('combustion_chamber', 'nozzle_assembly',
                                'injector_assembly', 'turbopump_assembly',
                                'feed_system', 'controls_avionics'))
    assert cm['total_dry_mass'] == pytest.approx(parca, rel=1e-12)
    assert sivi['design_summary']['masses']['engine_mass_kg'] == \
        cm['total_dry_mass']
    assert sivi['engine_mass_estimate'] == cm['total_dry_mass']
    g0 = 9.80665
    assert sivi['thrust_to_weight'] == pytest.approx(
        sivi['thrust'] / (cm['total_dry_mass'] * g0), rel=1e-9)
    assert sivi['design_summary']['masses']['thrust_to_weight'] == \
        sivi['thrust_to_weight']
    assert 'T/W=%.1f' % sivi['thrust_to_weight'] in \
        sivi['design_summary']['recommendation']
    fv = _sessiz(client.post, '/api/flight-vehicle', json={
        'motor_type': 'liquid', 'source': 'results', 'results': sivi})
    assert fv.status_code == 200, fv.get_data(as_text=True)[:300]
    j = fv.get_json()
    arac = j.get('vehicle') or j
    # V301/T-ÇAPA-D: örnek sıvı (ÖRNEK 5fa435893) artık yanma süresi taşıyor
    # (30 s); süreli sonuç tank kuru yapısını ve yüklenen − nominal (rezerv)
    # itici kütlesini yayımlar ve uçan atıl kütle bunları ekler
    # (flight_vehicle._liquid_inert_mass, P4B3-20; künyede adıyla). Bu
    # bekçinin konusu MOTOR kuru kütlesinin tek kaynak olması: atıl kütle =
    # total_dry_mass + yayımlanan tank yapısı + rezerv, künye motor kuru
    # kütlesini aynı sayıyla adlandırır.
    ss = sivi['propellant_tanks']['system_summary']
    rezerv = max(ss['total_propellant_mass']
                 - ss['total_propellant_mass_nominal'], 0.0)
    assert arac['engine_inert_mass'] == pytest.approx(
        cm['total_dry_mass'] + ss['total_tank_mass'] + rezerv, rel=1e-12)
    assert ('engine dry mass %.3f kg' % cm['total_dry_mass']) in \
        arac['engine_inert_mass_note']


def test_cizilemezse_eski_model_beyanla(sivi, monkeypatch):
    """Çizilen geometri çözülemezse sayı uydurulmaz: eski model + beyan."""
    from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

    def _bozuk(_md):
        raise ValueError('test')
    monkeypatch.setattr(CV, 'two_layer_wall_cad_geometry', _bozuk)
    s = copy.deepcopy(sivi)
    onceki = copy.deepcopy(s['component_sizing']['component_masses'])
    s['component_sizing'].pop('two_layer_mass_single_source')
    motor = LiquidRocketEngine.__new__(LiquidRocketEngine)
    motor.F = s['thrust']
    motor._iki_katmanli_kutle_tek_kaynak(s)
    kayit = s['component_sizing']['two_layer_mass_single_source']
    assert kayit['status'] == 'NOT_APPLIED'
    assert 'ValueError' in kayit['reason']
    assert s['component_sizing']['component_masses'] == onceki
