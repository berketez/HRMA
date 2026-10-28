"""v3.0.1 (26 Eki 2026) — PDF güvenlik bölümü kasa boyunu motordan alır.

K-C1 devri (KT-16 son maddesi): ``build_pdf_safety`` kasa kütlesini oda
çapı ve cidar kalınlığından "ASSUMED L/D = 5" ile kuruyordu; üç motor
tipinde de oda boyu motorda yayımlandığı hâlde güvenlik modülüne
geçmiyordu. Boy artık çapla AYNI merkezî bandlı kuraldan
(``motor_geometry.resolve_length_m``) çözülüp geçer; bulunamazsa geçmez
ve varsayım beyanı kalır.

Ölçüm (main 117d704da, ``K-C1/guvenlik_olcum.py``): katı kasa
3,703 → 4,032 kg (kopma hızı 1899 → 1807 m/s); hibrit örnek
4,768 → 10,987 kg (oda boyu 1,041 m; L/D 5 varsayımı ~0,42 m alıyordu).
"""
import pytest

from hrma.export.pdf_safety import build_pdf_safety

MD = {'motor_type': 'solid', 'chamber_pressure': 40.0,
      'chamber_diameter': 106.0,
      'chamber_wall_policy': {'wall_thickness_m': 0.0022},
      'propellant_mass': 5.47, 'burn_time': 3.1427, 'thrust': 3890.35,
      'propellant_type': 'apcp'}


def _parca(md):
    safety, kunye = build_pdf_safety(dict(md), {})
    assert safety is not None, kunye
    return safety['explosive_hazards']['fragment_hazards'], kunye


def test_oda_boyu_varsa_kasa_kutlesine_girer():
    fh, kunye = _parca(dict(MD, chamber_length=400.0))
    assert 'ASSUMED' not in fh['case_mass_basis']
    assert 'length' in fh['case_mass_basis']
    assert kunye['inputs_resolved']['chamber_length'].startswith('md:')


def test_oda_boyu_yoksa_varsayim_beyanli_kalir():
    fh, kunye = _parca(MD)
    assert 'ASSUMED L/D' in fh['case_mass_basis']
    assert 'chamber_length' not in kunye['inputs_resolved']


def test_kasa_kutlesi_boyla_dogrusal_artar():
    # Kütle = silindir kabuk (boyla doğrusal) + uç kapaklar (boydan
    # bağımsız); eşit boy artışları eşit kütle artışı verir.
    m = [_parca(dict(MD, chamber_length=L))[0]['estimated_case_mass_kg']
         for L in (300.0, 600.0, 900.0)]
    assert m[0] < m[1] < m[2]
    assert (m[2] - m[1]) == pytest.approx(m[1] - m[0], rel=1e-9)
