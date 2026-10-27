"""V301/K-C1 — KT-15 / NK-54 / NK-71 bekçisi: yörünge paneli varsayılan
tasarımda çalışır, itki eğrisiyle uçar, ret cümlesi sayılıdır.

Kanıt: docs/scofield/raw/OH/V301/kati-sivi/K-C1/ (yorunge_once.json,
yorunge_sonra.json, RAPOR.md §KT-15).
"""
import json
import math
import os
import re

import pytest

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
KANIT = os.path.join(KOK, 'docs', 'scofield', 'raw', 'OH', 'V301',
                     'kati-sivi', 'K-C1')
SOLID = os.path.join(KOK, 'hrma', 'templates', 'solid.html')
LIQUID = os.path.join(KOK, 'hrma', 'templates', 'liquid.html')
I18N_PAGES = os.path.join(KOK, 'hrma', 'static', 'js', 'i18n_pages.js')


def _oku(yol):
    with open(yol, encoding='utf-8') as f:
        return f.read()


def _islev(kaynak, ad):
    """``async function <ad>(`` gövdesini bir sonraki üst düzey işleve dek."""
    m = re.search(r'(?:async\s+)?function\s+%s\s*\(' % re.escape(ad), kaynak)
    assert m, ad
    son = re.search(r'\n        (?:async\s+)?function\s+\w+\s*\(',
                    kaynak[m.end():])
    return kaynak[m.start():m.end() + (son.start() if son else 20000)]


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def kati_yanit(istemci):
    yuk = json.load(open(os.path.join(KANIT, 'sayfa_yuk.json')))
    r = istemci.post('/calculate_solid', json=yuk)
    assert r.status_code == 200
    return r.get_json()


def _kati_sayfa_govdesi(r):
    """solid.html computeTrajectory'nin kurduğu gövde (bu kulvardan sonra)."""
    m = r['design_summary']['masses']
    d = r['cad_design']['case_design']['outer_diameter']
    tc = r['thrust_curve']
    return dict(
        initial_mass=round(m['total_mass_kg'], 3),
        final_mass=round(m['dry_mass_kg'], 3),
        drag_coefficient=0.5,
        reference_area=round(math.pi * (d / 2000) ** 2, 5),
        thrust_curve={'time': tc['time'], 'thrust': tc['thrust']},
        isp=r['isp_sea_level'],
        nozzle_exit_area=math.pi * (r['exit_diameter'] / 2000.0) ** 2,
        thrust_reference_pressure=(
            r['nozzle_design']['performance']['ambient_pressure'] * 1e5))


def test_kati_varsayilan_tasarim_yorungesi_egriyle_200(istemci, kati_yanit):
    r = istemci.post('/api/trajectory-analysis',
                     json=_kati_sayfa_govdesi(kati_yanit))
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    td = r.get_json()['trajectory_data']
    assert td['thrust_input']['source'] == 'thrust_curve'
    assert td['thrust_altitude_compensation']['modelled'] is True
    # Eğrinin impulsu ana tasarımın toplam impulsuyla aynı.
    assert td['thrust_input']['total_impulse_Ns'] == pytest.approx(
        kati_yanit['total_impulse'], rel=1e-9)


def test_kati_sayfa_govdesi_vakum_isp_ve_ortalama_itki_gondermez():
    govde = _islev(_oku(SOLID), 'computeTrajectory')
    assert 'cr.isp_vacuum' not in govde
    assert 'cr.average_thrust' not in govde
    assert 'thrust_curve: trCurve' in govde
    assert 'cr.isp_sea_level' in govde
    assert 'body.nozzle_exit_area' in govde
    assert 'body.thrust_reference_pressure' in govde
    # Ret cümlesi ortak çözücüden geçer (ham makine kodu değil).
    assert 'HRMAReject.metni(govde, resp.status)' in govde


def test_kati_yanma_suresi_alani_kilitli_ve_ipuclu():
    s = _oku(SOLID)
    m = re.search(r'<input[^>]*id="traj_burn_time"[^>]*>', s)
    assert m and ' disabled' in m.group(0)
    assert 'value=' not in m.group(0)
    assert 'solid.ui.burn_time_from_thrust_curve_help' in s


def test_uc_butce_kapisi_degismedi_ve_cumle_sayili(istemci, kati_yanit):
    """Kapı kilidi: vakum Isp + deniz seviyesi eğrisi hâlâ 422; cümle iki
    kütleyi ve farkı taşır, tolerans %1."""
    govde = _kati_sayfa_govdesi(kati_yanit)
    govde['isp'] = kati_yanit['isp_vacuum']
    r = istemci.post('/api/trajectory-analysis', json=govde)
    assert r.status_code == 422
    j = r.get_json()
    assert j['error'] == 'inconsistent_propellant_budget'
    assert j['accepted_relative_disagreement'] == 0.01
    p = j['message_params']
    mp = kati_yanit['design_summary']['masses']
    assert p['mass_budget_kg'] == pytest.approx(
        round(mp['total_mass_kg'], 3) - round(mp['dry_mass_kg'], 3))
    assert p['implied_kg'] == pytest.approx(
        kati_yanit['total_impulse'] / (kati_yanit['isp_vacuum'] * 9.80665),
        rel=1e-9)
    assert p['accepted_pct'] == pytest.approx(1.0)
    assert '%.4g' % p['mass_budget_kg'] in j['message']
    assert '%.4g' % p['implied_kg'] in j['message']


def test_sivi_sayfa_govdesi_deniz_seviyesi_ciftini_ve_motor_kutlelerini_kullanir():
    govde = _islev(_oku(LIQUID), 'computeTrajectory')
    assert 'cr.isp_vacuum' not in govde
    assert '_perf.thrust_sl_N' in govde and '_perf.isp_sl_s' in govde
    assert "_tohum('traj_initial_mass', _mas.engine_mass_kg + _mas.propellant_mass_kg)" in govde
    assert "_tohum('traj_final_mass', _mas.engine_mass_kg)" in govde
    assert 'HRMAReject.metni(govde, resp.status)' in govde


def test_sivi_tutarli_govde_200(istemci):
    """NK-71: sıvı örneğinde motorla tutarlı kütleler artık 200."""
    form = {k: v for k, v in json.load(open(os.path.join(
        KOK, 'docs/scofield/raw/OH/V301/kati-sivi/L-B/yuk_form_en.json'))).items()
        if v is not None}
    form.update(thrust=10000, chamber_pressure=100, mixture_ratio=2.5,
                max_burn_duration=30)
    r = istemci.post('/calculate_liquid', json=form)
    assert r.status_code == 200
    j = r.get_json()
    perf, mas = j['design_summary']['performance'], j['design_summary']['masses']
    m_son = mas['engine_mass_kg']
    m_bas = m_son + mas['propellant_mass_kg']
    govde = dict(initial_mass=m_bas, final_mass=m_son, drag_coefficient=0.5,
                 reference_area=0.05,
                 burn_time=(m_bas - m_son) / j['total_mass_flow'],
                 thrust=perf['thrust_sl_N'], isp=perf['isp_sl_s'])
    t = istemci.post('/api/trajectory-analysis', json=govde)
    assert t.status_code == 200, t.get_data(as_text=True)[:400]
    assert govde['burn_time'] == pytest.approx(30.0, rel=1e-9)


def test_sivi_etiketi_m_noktali_ve_ret_anahtarlari_iki_dilde():
    s = _oku(I18N_PAGES)
    assert '\\u1E45' not in s, 'ṅ (n noktalı) kaldı: ṁ (\\u1E41) olmalı'
    for anahtar in ('liq.js.trajectory_propellant_budget_mismatch',
                    'solid.msg.trajectory_propellant_budget_mismatch'):
        assert s.count("'%s'" % anahtar) == 2, anahtar
