"""V301/FİZİK-2 kalem 7 — KABUL süzgeci: arıza listesi ağırlığı kritik sayılmaz.

PANEL (27 Eki, DEVİR 2/5) ``failure_modes[].severity`` alanını
``consequence_severity`` olarak yeniden adlandırdı: değer FMEA sonuç
ağırlığıdır (her motorda aynı genel kontrol listesi), hüküm değildir; hüküm
``structural_integrity``dir. KABUL süzgeci (tests/support/kabul.py) bu alanı
ADIYLA ve gerekçesiyle dışarıda bırakır; yeni bir ``*_severity`` adı ise
kritik kaçırmaz.
"""
import pathlib

from tests.support import kabul

KOK = pathlib.Path(__file__).resolve().parents[1]


def test_ariza_listesi_agirligi_kritik_sayilmaz():
    yanit = {'safety_analysis': {'structural_safety': {'failure_modes': [
        {'mode': 'Burst failure', 'consequence_severity': 'CRITICAL'},
        {'mode': 'Fatigue', 'consequence_severity': 'HIGH'}]}}}
    assert kabul.kritikler(yanit) == []


def test_ad_kurali_yoldan_bagimsiz():
    """Ad kuralı tek başına yeter: eski yol kuralının (``failure_modes``)
    kapsamadığı bir yerde de arıza ağırlığı kritik sayılmaz."""
    yanit = {'fmea_ozeti': [{'mode': 'Burst failure',
                             'consequence_severity': 'CRITICAL'}]}
    assert kabul.kritikler(yanit) == []


def test_ad_ve_gerekce_tabloda():
    gerekce = kabul.HUKUM_OLMAYAN_SIDDET_ALANLARI['consequence_severity']
    assert 'FMEA' in gerekce and 'structural_integrity' in gerekce
    assert 'bare_wall_severity' in kabul.HUKUM_OLMAYAN_SIDDET_ALANLARI


def test_urun_alani_bu_adi_tasiyor():
    kaynak = (KOK / 'hrma' / 'analysis' / 'safety_analysis.py').read_text(
        encoding='utf-8')
    assert "'consequence_severity': 'CRITICAL'" in kaynak


def test_gercek_bayrak_hala_sayilir():
    assert len(kabul.kritikler({'warnings': [
        {'code': 'warn.x', 'severity': 'critical'}]})) == 1
    assert len(kabul.kritikler({'w': {'code': 'warn.y',
                                      'level': 'CRITICAL'}})) == 1
    # Yeni bir şiddet alanı adı kritiği kaçırmaz.
    assert len(kabul.kritikler({'w': {'code': 'warn.z',
                                      'thermal_severity': 'critical'}})) == 1


def test_betimleyici_cidar_siddeti_sayilmaz():
    assert kabul.kritikler({'w': {'code': 'warn.t', 'severity': 'info',
                                  'bare_wall_severity': 'critical'}}) == []


def test_eski_sema_yol_kurali_korunur():
    yanit = {'safety_analysis': {'structural_safety': {'failure_modes': [
        {'mode': 'Burst failure', 'severity': 'CRITICAL'}]}}}
    assert kabul.kritikler(yanit) == []
