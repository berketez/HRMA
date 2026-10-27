"""V301/K-C1 — KT-21 / NK-53 / K-A DEVİR 10 bekçisi.

* Örnek (sayfa varsayılanı) yükte Monte Carlo ÇALIŞIR (kasa boş = türetilir
  biçimi tanınır) ve nominali ana tasarımla bit-aynıdır.
* ``fixed_hardware`` işlenmiş (geometrik) boğazı yayımlar; etkin (Cd'li)
  çap ayrı alandadır.
* Gerçekten eksik girdi adıyla söylenir; sayfa ham makine kodunu basmaz.
* Katı UQ fabrikası sayfa yüküyle kurulur; a/n verilmezse katalogdan.

Kanıt: docs/scofield/raw/OH/V301/kati-sivi/K-C1/mc_once.json, mc_sonra.json,
uq_once.json, uq_sonra.json.
"""
import json
import os
import re

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'V301',
                     'kati-sivi', 'K-C1')
SOLID = os.path.join(KOK, 'hrma', 'templates', 'solid.html')


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def sayfa_yuku():
    return json.load(open(os.path.join(KANIT, 'sayfa_yuk.json')))


def test_ornek_yukte_mc_calisir_ve_nominal_bit_ayni(istemci, sayfa_yuku):
    assert sayfa_yuku.get('chamber_diameter') in (None, '')
    ana = istemci.post('/calculate_solid', json=sayfa_yuku).get_json()
    r = istemci.post('/api/solid-monte-carlo',
                     json=dict(sayfa_yuku, n_samples=20))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    mc = r.get_json()
    assert mc['thrust']['nominal'] == ana['average_thrust']
    assert mc['isp']['nominal'] == ana['specific_impulse']
    assert mc['burn_time']['nominal'] == ana['burn_time']
    fh = mc['fixed_hardware']
    ts = ana['throat_sizing']
    assert fh['throat_diameter_mm'] == pytest.approx(
        ts['throat_diameter_geometric_mm'], rel=1e-12)
    assert fh['throat_diameter_effective_mm'] == pytest.approx(
        ts['throat_diameter_effective_mm'], rel=1e-12)
    assert fh['throat_diameter_mm'] > fh['throat_diameter_effective_mm']
    assert fh['discharge_coefficient'] == pytest.approx(
        ts['discharge_coefficient'])


def test_gercekten_eksik_cap_adiyla_reddedilir(istemci, sayfa_yuku):
    govde = dict(sayfa_yuku, n_samples=20)
    govde.pop('outer_diameter')
    r = istemci.post('/api/solid-monte-carlo', json=govde)
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'solid_monte_carlo_missing_inputs'
    assert j['missing_fields'] == ['chamber_diameter']


def test_mc_ucunda_literal_geometri_yedegi_yok():
    with open(os.path.join(KOK, 'hrma', 'app.py'), encoding='utf-8') as f:
        s = f.read()
    i = s.index("@app.route('/api/solid-monte-carlo'")
    govde = s[i:s.index('\n@app.route(', i + 10)]
    kod = '\n'.join(sa.split('#', 1)[0] for sa in govde.splitlines())
    assert not re.search(r"data\.get\('chamber_diameter',\s*\d", kod)
    assert not re.search(r"data\.get\('core_diameter',\s*\d", kod)
    assert not re.search(r"data\.get\('grain_length',\s*\d", kod)


def test_sayfa_mc_retini_ham_kodla_ve_yigarak_basmaz():
    with open(SOLID, encoding='utf-8') as f:
        s = f.read()
    i = s.index('async function runSolidMonteCarlo(')
    g = s[i:s.index('\n        function mcStatCard', i)]
    assert 'HRMAReject.metni(govde, response.status)' in g
    assert "TF('solid.msg.monte_carlo_missing_inputs'" in g
    assert "getElementById('mc_results')" in g
    assert 'throw new Error(mc.error ||' not in g


def test_uq_fabrikasi_sayfa_yukuyle_kurulur(sayfa_yuku):
    from hrma.analysis.uq_adapters import make_solid_factory
    nom = make_solid_factory(sayfa_yuku)({})
    for ad in ('isp', 'c_star', 'max_pressure', 'total_impulse'):
        assert isinstance(nom[ad], float) and nom[ad] > 0, ad


def test_uq_fabrikasi_a_n_yoksa_katalogdan():
    from hrma.analysis import uq_adapters
    from hrma.engines.solid_rocket_engine import (
        SOLID_DEFAULT_GEOMETRY_MM, _catalog_burn_rate)
    yuk = {'propellant_type': 'apcp', 'grain_type': 'bates',
           'chamber_diameter': SOLID_DEFAULT_GEOMETRY_MM['chamber_diameter'],
           'grain_length': SOLID_DEFAULT_GEOMETRY_MM['grain_length'],
           'chamber_pressure': 40}
    # Çekirdek verilmedi: kurucunun tek kaynak varsayılanı (48 mm) — eski
    # yedek 30 mm ve a = 0,005 portu boğuyordu (SolidDesignRejected).
    nom = uq_adapters.make_solid_factory(yuk)({})
    assert nom['max_pressure'] > 0
    with open(uq_adapters.__file__, encoding='utf-8') as f:
        kod = '\n'.join(sa.split('#', 1)[0] for sa in f.read().splitlines())
    assert "get('burn_rate_a', 0.005)" not in kod
    assert "get('core_diameter', 30)" not in kod
    a_cat, _n = _catalog_burn_rate('apcp')
    assert a_cat is not None


def test_uq_gecersiz_kati_geometri_adli_422(istemci, sayfa_yuku):
    """K-A DEVİR 11: port < boğaz yükü UQ ucunda /calculate_solid ile aynı
    adlı 422 (önce: sayfa yükü 400 'chamber_diameter must be a number',
    tek çaplı API yükü 500 — K-C1/diger_uclar_once.json)."""
    gecersiz = dict(sayfa_yuku, core_diameter=20)
    ana = istemci.post('/calculate_solid', json=gecersiz)
    assert ana.status_code == 422
    r = istemci.post('/api/uncertainty-analysis', json={
        'motor_type': 'solid', 'level': 'fast', 'seed': 1,
        'inputs': gecersiz})
    assert r.status_code == 422, r.get_data(as_text=True)[:300]
    j = r.get_json()
    assert j['error_code'] == ana.get_json()['error_code']
    assert j['invalid_fields']


def test_fea_ve_ucus_araci_tasarim_reddini_adli_422_ile_tasir():
    """K-A DEVİR 11: iki uç da SolidDesignRejected'i ValueError dalından
    ÖNCE yakalar (kaynak düzeyi; uçuş aracı kayıtlı proje ister)."""
    with open(os.path.join(KOK, 'hrma', 'app.py'), encoding='utf-8') as f:
        s = f.read()
    for rota in ("@app.route('/api/flight-vehicle'",
                 "@app.route('/api/fea/planar-grain'",
                 "@app.route('/api/uncertainty-analysis'"):
        i = s.index(rota)
        govde = s[i:s.index('\n@app.route(', i + 10)]
        j = govde.index('except SolidDesignRejected')
        assert 'return _kati_tasarim_reddi(' in govde[j:j + 400], rota
        k = govde.find('except ValueError', j)
        k2 = govde.find('except (ValueError, KeyError)', j)
        assert max(k, k2) > j, rota
