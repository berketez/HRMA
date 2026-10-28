"""v3.0.1 (26 Eki 2026) — uçan aracın gövdesi motorun lüle çıkışını kapsar.

Son kullanıcı testi (NK-47): sıvı örnek (25 kN LOX/RP-1, lüle çıkışı
189,6 mm) "Son hesaplanan motor" olarak Fırlatma Sahası'na geçince gövde dış
çapı 0,15 m kaldı ve araç 231 km apojeye "uçtu". Kök: ``flight_vehicle``
sıvıda ``engine_od_m``i İÇ kamara çapından (109,4 mm) kuruyordu; sayfa gövde
çapının alt sınırını bu alandan alıyor (launch_site.html ``applyVehicle``).
Lüle çıkışı motorun dış zarfının parçasıdır; gövde ondan küçük olamaz.
"""
import pytest

from hrma.analysis import flight_vehicle as fv


def _sivi(cikis_mm=189.5545, kamara_m=0.1094):
    return {'thrust': 25000.0, 'burn_time': 30.0, 'chamber_diameter': kamara_m,
            'design_summary': {
                'masses': {'propellant_mass_kg': 273.6, 'engine_mass_kg': 71.2},
                'key_dimensions': {'nozzle_exit_mm': cikis_mm}}}


def test_sivi_govde_alt_siniri_luele_cikisini_kapsar():
    v = fv.normalize('liquid', _sivi())
    assert v['engine_od_m'] == pytest.approx(0.1895545)
    assert 'nozzle exit' in v['engine_od_unit_source']


def test_cikis_kucukse_kasa_capi_kalir():
    """Katı örnek: kasa dış çapı 83 mm, lüle çıkışı 47,6 mm → kasa."""
    sonuc = {'average_thrust': 1300.0, 'burn_time': 2.28,
             'propellant_mass': 1.6,
             'cad_design': {'case_design': {'outer_diameter': 83.0}},
             'design_summary': {'masses': {'dry_mass_kg': 3.7},
                                'key_dimensions': {'nozzle_exit_mm': 47.5686,
                                                   'total_length_mm': 555.0}}}
    v = fv.normalize('solid', sonuc)
    assert v['engine_od_m'] == pytest.approx(0.083)
    assert 'nozzle exit' not in v['engine_od_unit_source']


def test_hibrit_cikis_alan_adi_da_okunur():
    """Hibrit çıkış çapını 'nozzle_exit_diameter_mm' adıyla yayımlar."""
    sonuc = {'motor': {'thrust': 3000.0, 'burn_time': 10.0,
                       'propellant_mass_total': 12.95, 'chamber_diameter': 0.05,
                       'design_summary': {'key_dimensions': {
                           'nozzle_exit_diameter_mm': 150.0,
                           'total_motor_length_mm': 1098.7}}}}
    v = fv.normalize('hybrid', sonuc)
    assert v['engine_od_m'] == pytest.approx(0.150)


def test_cikis_yayimlanmamissa_uydurulmaz():
    v = fv.normalize('liquid', {'thrust': 25000.0, 'burn_time': 30.0,
                                'chamber_diameter': 0.1094,
                                'design_summary': {'masses': {},
                                                   'key_dimensions': {}}})
    assert v['engine_od_m'] == pytest.approx(0.1094)
    assert 'nozzle exit' not in v['engine_od_unit_source']
