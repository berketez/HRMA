# -*- coding: utf-8 -*-
"""V301/B7 ardılı (21 Eki) — kinetik high_fidelity yolu yoğun fazla tutarlı.

B7 hibrit dengeye katı karbon C(gr) ekledi. ``kinetic_efficiency``nin
high_fidelity yolu odayı ve izentropu kendi GAZ-yalnız dengesiyle kurduğu
için yakıtça zengin bölgede iki fazlı T_c ile tutarsız kalıyordu (ölçüldü,
N2O/HTPB O/F 2,5 / 20 bar: Isp 177,20 → 187,92 s). Yol artık yoğun faz
beyanında kendi zarif düşüş sözleşmesiyle beyanlı engineering yoluna geçer;
yoğun faz yoksa davranış değişmez.
"""
import pytest

from hrma.analysis import kinetic_efficiency as ke_module
from hrma.analysis.kinetic_efficiency import KineticEfficiency
from tests.test_kinetic_efficiency import (
    _h2o2_profile, _h2o2_results, make_results)


def test_yogun_karbon_beyaninda_high_fidelity_beyanli_duser():
    sonuc = make_results()
    sonuc['condensed_phases'] = {
        'status': 'present',
        'stations_with_condensed_phase': ['chamber', 'throat', 'exit']}
    res = KineticEfficiency().evaluate(
        combustion_results=sonuc, fidelity='high_fidelity',
        nozzle_profile=_h2o2_profile())
    assert res['fidelity_requested'] == 'high_fidelity'
    assert res['fidelity_used'] == 'engineering'
    assert 'condensed carbon C(gr)' in res['model_note']
    assert 'chamber, throat, exit' in res['model_note']


@pytest.mark.skipif(not ke_module.CANTERA_AVAILABLE,
                    reason='Cantera kurulu değil')
def test_yogun_faz_yoksa_high_fidelity_aynen_calisir():
    sonuc = _h2o2_results()
    sonuc['condensed_phases'] = {'status': 'absent'}
    res = KineticEfficiency(mechanism='h2o2.yaml').evaluate(
        combustion_results=sonuc, fidelity='high_fidelity',
        nozzle_profile=_h2o2_profile())
    assert res['fidelity_used'] == 'high_fidelity'


@pytest.mark.skipif(not ke_module.CANTERA_AVAILABLE,
                    reason='Cantera kurulu değil')
def test_gercek_yakitca_zengin_hibrit_sonucu_beyanli_duser():
    from hrma.engines.combustion_analysis import CombustionAnalyzer
    cres = CombustionAnalyzer().analyze_combustion(
        {'htpb': 100.0}, 'n2o', 2.5, 20.0)
    assert cres['condensed_phases']['status'] == 'present'
    res = KineticEfficiency().evaluate(
        combustion_results=cres, fidelity='high_fidelity',
        nozzle_profile=_h2o2_profile())
    assert res['fidelity_used'] == 'engineering'
    assert 'condensed carbon C(gr)' in res['model_note']
