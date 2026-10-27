"""V301/B6 ardılı (21 Eki) — katı basınç çözücüsünde ilk yineleme akı tutarlılığı.

KUSUR (B6 RAPOR, açık kalan; docs/scofield/raw/OH/V301/makale1/B6/RAPOR.md):
basınç yinelemesinden önce hesaplanan yanma hızı, ÖNCEKİ zaman adımının port
kütle akısını kullanıyordu (erozif çarpanın girdisi). Basınç ilk yinelemede
tolerans içindeyse adım o eski akıyla "yakınsadı" sayılıyordu. ÖLÇÜLDÜ (KNSB
eşdeğeri, 116. adım): tutarlı akıyla kütle dengesi artığı 7,78e-5, çözücü
toleransı 1e-6.

DÜZELTME: ilk yinelemede kabul edilecek adımda hız güncel akıyla yeniden
hesaplanır; aynı toleransta değişmiyorsa adım aynen kabul edilir (erozif terimi
etkisiz adımlar bit-aynı), değişiyorsa yineleme sürer. SONRA: KNSB en büyük
artık 1,93e-8, toleransı aşan adım 0; impuls −3,4e-7 bağıl. KNDX ve KNSU
eğrileri bit-aynı.
"""

import contextlib
import io

import numpy as np
import pytest

from hrma.data import burn_rate_db, propellants_db
from hrma.engines.solid_rocket_engine import SolidRocketEngine
from tests.test_example_projects import (
    HEADERS, calculate_payload, load_example_doc)


@pytest.fixture(scope='module')
def client():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _knsb_alanlari():
    """Örnek KNDX geometrisi + KNSB kataloğu ve rejim yasası (B6 ölçüm
    betiğiyle aynı kurulum: olcum_b6.py ``_alanlar('knsb')``)."""
    alanlar = dict(load_example_doc('solid')['inputs']['fields'])
    d = propellants_db.get_propellant('knsb')
    alanlar.update({
        'propellant_name': d['name'], 'density': float(d['density']),
        'flame_temp': float(d['flame_temperature']),
        'molecular_weight': float(d['molecular_weight']),
        'gamma': float(d['gamma']), 'char_velocity': float(d['c_star'])})
    assert burn_rate_db.has_law('knsb')
    k = burn_rate_db.resolve_engine_coeffs('knsb', 40.0)
    alanlar['burn_rate_a'] = round(float(k['a']), 7)
    alanlar['burn_rate_n'] = round(float(k['n']), 4)
    alanlar['burn_rate_preset'] = 'knsb'
    return alanlar


@pytest.fixture(scope='module')
def knsb(client):
    yakalanan = {}
    orj = SolidRocketEngine.calculate_thrust_curve

    def egri(self, *a, **k):
        eg = orj(self, *a, **k)
        yakalanan['egri'] = eg
        yakalanan['c_star'] = float(self.c_star)
        return eg

    SolidRocketEngine.calculate_thrust_curve = egri
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            yanit = client.post('/calculate_solid',
                                json=calculate_payload('solid',
                                                       _knsb_alanlari()),
                                headers=HEADERS)
    finally:
        SolidRocketEngine.calculate_thrust_curve = orj
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    return yakalanan


def test_her_cozucu_adiminda_kutle_dengesi_tolerans_icinde(knsb):
    eg = knsb['egri']
    p = np.asarray(eg['pressure'], float)
    md = np.asarray(eg['mass_flow'], float)
    at = np.asarray(eg['throat_area_series'], float)
    adim = int(eg['pressure_solver_steps'])
    assert adim > 100, 'vaka değişmiş: KNSB eğrisi beklenenden kısa'
    akan = np.zeros(p.shape, bool)
    akan[:adim] = p[:adim] > 0
    artik = (np.abs(md[akan] * knsb['c_star'] / (at[akan] * 1e5) - p[akan])
             / np.maximum(p[akan], 1.0))
    tol = float(eg.get('pressure_solver_tolerance', 1e-6))
    assert float(np.max(artik)) <= tol, (
        f'kütle dengesi artığı {float(np.max(artik)):.3e} > tolerans {tol:g} '
        '— ilk yineleme önceki adımın akısıyla kabul edilmiş olabilir')


def test_knsb_yakinsama_sagligi_degismedi(knsb):
    eg = knsb['egri']
    assert eg['pressure_solver_failed_steps'] == 0
    assert eg['pressure_solver_boundary_held_steps'] == 0
