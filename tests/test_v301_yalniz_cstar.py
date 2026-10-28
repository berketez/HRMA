"""V301/B7 ardılı (21 Eki) — hibrit c*(O/F) ızgarası için yalnız-c* yolu (HIZ).

ÖLÇÜLDÜ: B7'den (dengeye katı karbon C(gr)) sonra yakıtça zengin bir 1 kN
hibrit tasarımın ``calculate()``'i 0,51 s'den 1,56 s'ye çıkmıştı. Isınmış bir
koşu 14 kez ``analyze_combustion`` çağırıyordu; 12'si c*(O/F) ızgarası
(``_perf_grid_c_star``) ve ara değerleme tanısı (``_of_interpolation_
diagnostics``) idi ve ikisi de yalnız ``performance['c_star']`` okuyordu. Her
çağrı yine de çıkış istasyonunu, üçlü Isp'yi ve istasyon bileşimlerini
çözüyordu (çağrı başına ~80 ms'nin yaklaşık yarısı).

DÜZELTME: ``analyze_combustion(..., c_star_only=True)`` alev sıcaklığını, oda
bileşimini ve kayan-denge boğazını aynen çözer, gerisini atlar. c* tam yolla
BİT-AYNIDIR; ``calculate()`` yanıtı bit-aynı; süre 1,56 → 0,97 s.
"""

import contextlib
import copy
import io
import json
import sys

import pytest

from hrma.engines import combustion_analysis as ca
from hrma.engines.hybrid_rocket_engine import HybridRocketEngine

HTPB = {'htpb': 100.0}


@pytest.mark.skipif(not ca.CANTERA_AVAILABLE, reason='Cantera yok')
@pytest.mark.parametrize('of', [1.5, 2.5, 3.0, 6.2])
def test_cstar_tam_yolla_bit_ayni(of):
    tam = ca.CombustionAnalyzer().analyze_combustion(HTPB, 'n2o', of, 20.0)
    gecmisli = ca.CombustionAnalyzer()
    gecmisli.analyze_combustion(HTPB, 'n2o', 2.7, 15.0)
    kisa = gecmisli.analyze_combustion(HTPB, 'n2o', of, 20.0,
                                       c_star_only=True)
    assert kisa['c_star_only'] is True
    assert kisa['performance']['c_star'] == tam['performance']['c_star']
    assert (kisa['conditions']['chamber']['T']
            == tam['conditions']['chamber']['T'])
    # Kısmi sonuç tam alanları TAŞIMAZ (yanlışlıkla tam sonuç sanılmasın).
    assert 'compositions' not in kisa
    assert 'isp_vacuum' not in kisa['performance']


@pytest.mark.skipif(not ca.CANTERA_AVAILABLE, reason='Cantera yok')
def test_onbellekte_kismi_sonuc_tam_istege_donmez():
    a = ca.CombustionAnalyzer(memoize=True)
    kisa = a.analyze_combustion(HTPB, 'n2o', 2.5, 20.0, c_star_only=True)
    tam = a.analyze_combustion(HTPB, 'n2o', 2.5, 20.0)
    assert kisa.get('c_star_only') is True
    assert 'c_star_only' not in tam
    assert 'compositions' in tam
    assert tam['performance']['c_star'] == kisa['performance']['c_star']


_TASARIM = {'thrust': 1000.0, 'burn_time': 10.0, 'of_ratio': 2.5,
            'chamber_pressure': 20.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o'}


_IZGARA_CAGIRANLARI = ('_perf_grid_c_star', '_of_interpolation_diagnostics')


def _calculate(zorla_tam=False):
    kayit = []
    orj = ca.CombustionAnalyzer.analyze_combustion

    def sarmal(self, *a, **k):
        if zorla_tam:
            k.pop('c_star_only', None)
        cagiran = sys._getframe(1).f_code.co_name
        kayit.append((cagiran, bool(k.get('c_star_only'))))
        return orj(self, *a, **k)

    ca.CombustionAnalyzer.analyze_combustion = sarmal
    try:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            sonuc = HybridRocketEngine(**copy.deepcopy(_TASARIM)).calculate()
    finally:
        ca.CombustionAnalyzer.analyze_combustion = orj
    return sonuc, kayit


@pytest.mark.skipif(not ca.CANTERA_AVAILABLE, reason='Cantera yok')
def test_izgara_ve_tani_yalniz_cstar_ister_yanit_bit_ayni():
    hizli, kayit = _calculate()
    yavas, _ = _calculate(zorla_tam=True)
    izgara = [k for c, k in kayit if c in _IZGARA_CAGIRANLARI]
    assert len(izgara) >= 7, f'ızgara/tanı çağrısı beklenenden az: {kayit}'
    assert all(izgara), (
        'c*(O/F) ızgarası ya da ara değerleme tanısı tam analiz istiyor '
        '(yalnız performance.c_star okuyorlar)')
    assert (json.dumps(hizli, sort_keys=True, default=str)
            == json.dumps(yavas, sort_keys=True, default=str)), (
        'yalnız-c* yolu calculate() yanıtını değiştirdi')
