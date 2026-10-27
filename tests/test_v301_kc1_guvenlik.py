"""V301/K-C1 — KT-16 bekçisi: güvenlik modülü itkiyi UYDURMAZ; katı PDF'i
gerçek (tepe) itkiyi gönderir.

Kanıt: docs/scofield/raw/OH/V301/kati-sivi/K-C1/guvenlik_once.json,
guvenlik_sonra.json (katı 4000 N → 15 561 N bağlama kuvveti; hibrit/sıvı
güvenlik sözlüğü md5 aynı).
"""
import os
import re

import pytest

from hrma.analysis.safety_analysis import (
    SafetyAnalyzer, THRUST_NOT_SUPPLIED_REASON, UNRESTRAINED_THRUST_FIELDS)

KOK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SOLID = os.path.join(KOK, 'hrma', 'templates', 'solid.html')

MOTOR = {'chamber_pressure': 40.0, 'chamber_diameter': 0.106,
         'wall_thickness': 0.0022, 'burn_time': 3.1427}


def _kol(sonuc):
    return sonuc['explosive_hazards']['fragment_hazards']['unrestrained_motor']


def test_itki_yoksa_serbest_motor_kolu_geri_cekilir():
    s = SafetyAnalyzer().analyze_comprehensive_safety(
        motor_data=dict(MOTOR), propellant_mass=5.47,
        propellant_type='apcp', motor_type='solid')
    kol = _kol(s)
    for alan in UNRESTRAINED_THRUST_FIELDS:
        assert kol[alan] is None, alan
    assert kol['status'] == 'NOT_EVALUATED'
    assert kol['reason'] == THRUST_NOT_SUPPLIED_REASON
    assert s['inputs_used']['thrust_n'] is None
    td = s['thrust_dependent_not_evaluated']
    assert 'inputs_used.thrust_n' in td['fields']
    assert ('explosive_hazards.fragment_hazards.unrestrained_motor.'
            'required_restraint_force_n') in td['fields']
    # 1000 N hiçbir sayıda görünmez (eski yedek: 4000 N bağlama kuvveti).
    assert 4000.0 not in [v for v in kol.values() if isinstance(v, float)]


def test_itki_verilince_sayilar_aynen():
    md = dict(MOTOR, thrust=3890.3491481212213)
    s = SafetyAnalyzer().analyze_comprehensive_safety(
        motor_data=md, propellant_mass=5.47, propellant_type='apcp',
        motor_type='solid')
    kol = _kol(s)
    sf = SafetyAnalyzer().safety_margins.structural_safety_factor
    assert kol['required_restraint_force_n'] == pytest.approx(
        3890.3491481212213 * sf, rel=1e-12)
    assert kol['total_impulse_ns'] == pytest.approx(
        3890.3491481212213 * 3.1427, rel=1e-12)
    assert 'status' not in kol
    assert 'thrust_dependent_not_evaluated' not in s


def test_kaynakta_1000_n_yedegi_yok():
    with open(os.path.join(KOK, 'hrma', 'analysis', 'safety_analysis.py'),
              encoding='utf-8') as f:
        kod = [sa.split('#', 1)[0] for sa in f.read().splitlines()]
    assert not any(re.search(r"get\('thrust',\s*1000", sa) for sa in kod)


def test_kati_pdf_yuku_tepe_itkiyi_thrust_adiyla_tasir():
    with open(SOLID, encoding='utf-8') as f:
        s = f.read()
    m = re.search(r'const _pdfAlanlar = \{(.*?)\n                \};', s, re.S)
    assert m, '_pdfAlanlar bulunamadı'
    govde = re.sub(r'//[^\n]*', '', m.group(1))
    assert re.search(r'\bthrust:\s*_sonlu\(_r\.max_thrust\)', govde)
    assert not re.search(r'\bthrust:\s*_sonlu\(_r\.average_thrust\)', govde)


def test_kati_pdf_guvenlik_bolumu_gercek_itkiyle(tmp_path):
    """Uçtan uca: sayfanın yüküyle build_pdf_safety tepe itkiyi kullanır."""
    import json
    from hrma.app import app
    from hrma.export.pdf_safety import build_pdf_safety
    yuk = json.load(open(os.path.join(
        KOK, 'docs/scofield/raw/OH/V301/kati-sivi/K-C1/sayfa_yuk.json')))
    r = app.test_client().post('/calculate_solid', json=yuk).get_json()
    geo = r['motor_geometry']
    md = {'motor_type': 'solid', 'thrust': r['max_thrust'],
          'chamber_diameter': geo['chamber_diameter'] * 1000,
          'chamber_length': geo['chamber_length'] * 1000,
          'propellant_mass': r['propellant_mass'],
          'burn_time': r['burn_time'],
          'chamber_pressure': r['chamber_pressure']}
    safety, kunye = build_pdf_safety(md, r)
    assert safety is not None, kunye
    kol = _kol(safety)
    sf = SafetyAnalyzer().safety_margins.structural_safety_factor
    assert kol['required_restraint_force_n'] == pytest.approx(
        r['max_thrust'] * sf, rel=1e-12)
    assert kunye['inputs_resolved'].get('thrust') == 'thrust'
