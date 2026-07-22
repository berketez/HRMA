"""Kademeli kinetik verim modülü (kinetic_efficiency) doğrulama testleri.

El hesabı çapaları (sentetik yanma sonucu: Pc=20 bar, Tc=3200 K,
rho_c=1.85 kg/m³, c*=1550 m/s, Isp_frozen=228 s, Isp_shifting=235 s,
L*=1.0 m, boğaz çapı verilmedi):

  t_res   = L*·rho_c·c*/P_c = 1.0·1.85·1550/2e6      = 1.43375e-3 s
  tau     = 1.5e-3·(20/20)²                            = 1.5e-3 s
  Da      = 1.43375e-3/1.5e-3                          = 0.9558333
  f       = Da/(1+Da)                                  = 0.488708
  Isp_pred= 228 + f·(235-228)                          = 231.42096 s
  gap_pct = (235-228)/235·100                          = 2.978723 %
  loss    = (1-f)·gap_pct                              = 1.522992 %
  bant    : f(5·Da)=0.826966 → lo=0.515418 %
            f(Da/5)=0.160487 → hi=2.500704 %

Fiziksel çapalar:
  * frozen ≤ predicted ≤ shifting (Bray frozen/shifting köşeleri)
  * büyük motor (yüksek Pc, büyük boğaz) → shifting'e yakınsama,
    küçük motor → frozen'a yakınsama (NASA SP-8120 kinetik kayıp eğilimi)
  * tipik kinetik kayıp %0.1-3 bandı (JANNAF/TDK pratiği)
"""

import numpy as np
import pytest

import hrma.analysis.kinetic_efficiency as ke_module
from hrma.analysis.kinetic_efficiency import (
    CANTERA_AVAILABLE,
    KineticEfficiency,
    kinetic_efficiency,
)
from hrma.constants import G_0, R_UNIVERSAL

REQUIRED_KEYS = {
    'fidelity_requested', 'fidelity_used', 'isp_frozen', 'isp_shifting',
    'isp_predicted', 'kinetic_loss_pct', 'loss_band_pct', 'model_note',
}


def make_results(p_c=20.0, t_c=3200.0, rho=1.85, c_star=1550.0,
                 isp_frozen=228.0, isp_shifting=235.0, isp=None,
                 gamma=None, gamma_frozen=None, mw=26.0, elements=None):
    """analyze_combustion çıktısını taklit eden sentetik sonuç üretir."""
    perf = {'c_star': c_star,
            'isp': isp if isp is not None else (isp_shifting or 230.0)}
    if isp_frozen is not None and isp_shifting is not None:
        perf['isp_frozen'] = isp_frozen
        perf['isp_shifting'] = isp_shifting
    chamber_comp = {'density': rho, 'molecular_weight': mw}
    if gamma is not None:
        chamber_comp['gamma'] = gamma
    if gamma_frozen is not None:
        chamber_comp['gamma_frozen'] = gamma_frozen
    return {
        'conditions': {'chamber': {'P': p_c, 'T': t_c},
                       'exit': {'P': 1.0}},
        'compositions': {'chamber': chamber_comp},
        'performance': perf,
        'elemental_composition': elements or {},
    }


class _ExplodingAnalyzer:
    """combustion_results verildiğinde asla çağrılmaması gereken nöbetçi."""

    def analyze_combustion(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("analyzer yeniden hesap yaptı — 'fast' seviyesi "
                             "mevcut denge çözümünü aynen kullanmalıydı")


# --------------------------------------------------------------------- #
# Şema ve girdi doğrulama
# --------------------------------------------------------------------- #

class TestSchemaAndValidation:
    def test_schema_keys_fast_and_engineering(self):
        for fidelity in ('fast', 'engineering'):
            res = kinetic_efficiency.evaluate(
                combustion_results=make_results(), fidelity=fidelity)
            assert REQUIRED_KEYS <= set(res.keys())
            assert res['fidelity_requested'] == fidelity
            assert res['fidelity_used'] == fidelity
            lo, hi = res['loss_band_pct']
            assert 0.0 <= lo <= hi

    def test_invalid_fidelity_raises(self):
        with pytest.raises(ValueError, match="fidelity"):
            kinetic_efficiency.evaluate(
                combustion_results=make_results(), fidelity='cfd')

    def test_missing_inputs_raise(self):
        with pytest.raises(ValueError, match="combustion_results"):
            kinetic_efficiency.evaluate(fidelity='engineering')

    def test_negative_characteristic_length_raises(self):
        with pytest.raises(ValueError, match="characteristic_length"):
            kinetic_efficiency.evaluate(
                combustion_results=make_results(),
                characteristic_length=-1.0)

    def test_inconsistent_isp_pair_raises(self):
        bad = make_results(isp_frozen=240.0, isp_shifting=235.0)
        with pytest.raises(ValueError, match="Inconsistent"):
            kinetic_efficiency.evaluate(combustion_results=bad)


# --------------------------------------------------------------------- #
# Seviye 1 — fast (denge referansı)
# --------------------------------------------------------------------- #

class TestFastLevel:
    def test_zero_loss_equilibrium_reference(self):
        res = kinetic_efficiency.evaluate(
            combustion_results=make_results(), fidelity='fast')
        assert res['isp_predicted'] == pytest.approx(235.0)
        assert res['kinetic_loss_pct'] == pytest.approx(0.0, abs=1e-12)
        # Bant üst sınırı = tamamen frozen genişleme (el hesabı: %2.978723)
        assert res['loss_band_pct'][0] == pytest.approx(0.0, abs=1e-12)
        assert res['loss_band_pct'][1] == pytest.approx(2.978723, rel=1e-5)

    def test_reuses_precomputed_results_without_analyzer_call(self):
        ke = KineticEfficiency(analyzer=_ExplodingAnalyzer())
        res = ke.evaluate(combustion_results=make_results(), fidelity='fast')
        assert res['isp_frozen'] == pytest.approx(228.0)
        assert res['isp_shifting'] == pytest.approx(235.0)


# --------------------------------------------------------------------- #
# Seviye 2 — engineering (Damköhler log-sigmoid korelasyonu)
# --------------------------------------------------------------------- #

class TestEngineeringLevel:
    def _run(self, **kw):
        results = make_results(**{k: v for k, v in kw.items()
                                  if k in ('p_c', 'rho', 'c_star')})
        return kinetic_efficiency.evaluate(
            combustion_results=results, fidelity='engineering',
            characteristic_length=kw.get('l_star'),
            throat_diameter=kw.get('d_t'))

    def test_residence_time_hand_calc(self):
        res = self._run()
        # t_res = 1.0 · 1.85 · 1550 / 2e6 = 1.43375e-3 s (Sutton Eş. 8-9)
        assert res['diagnostics']['residence_time_s'] == pytest.approx(
            1.43375e-3, rel=1e-9)

    def test_damkohler_and_blend_hand_calc(self):
        res = self._run()
        assert res['diagnostics']['damkohler'] == pytest.approx(
            0.9558333, rel=1e-6)
        assert res['diagnostics']['blend_fraction'] == pytest.approx(
            0.488708, rel=1e-4)

    def test_predicted_isp_hand_calc(self):
        res = self._run()
        assert res['isp_predicted'] == pytest.approx(231.42096, rel=1e-5)

    def test_loss_pct_hand_calc(self):
        res = self._run()
        assert res['kinetic_loss_pct'] == pytest.approx(1.522992, rel=1e-4)

    def test_ordering_frozen_predicted_shifting(self):
        res = self._run()
        assert res['isp_frozen'] < res['isp_predicted'] < res['isp_shifting']

    def test_band_hand_calc_and_brackets_nominal(self):
        res = self._run()
        lo, hi = res['loss_band_pct']
        assert lo == pytest.approx(0.515418, rel=1e-4)
        assert hi == pytest.approx(2.500704, rel=1e-4)
        assert lo < res['kinetic_loss_pct'] < hi

    def test_large_motor_converges_to_shifting(self):
        # Pc=70 bar, D_t=0.4 m (rho ∝ Pc): Da ≈ 93.7 → f ≈ 0.989
        res = self._run(p_c=70.0, rho=1.85 * 70 / 20, d_t=0.4)
        f = res['diagnostics']['blend_fraction']
        assert f > 0.95
        gap = res['isp_shifting'] - res['isp_frozen']
        assert res['isp_shifting'] - res['isp_predicted'] < 0.15 * gap

    def test_small_motor_converges_to_frozen(self):
        # Pc=7 bar, D_t=0.01 m: Da ≈ 0.0234 → f ≈ 0.023
        res = self._run(p_c=7.0, rho=1.85 * 7 / 20, d_t=0.01)
        f = res['diagnostics']['blend_fraction']
        assert f < 0.05
        gap = res['isp_shifting'] - res['isp_frozen']
        assert res['isp_predicted'] - res['isp_frozen'] < 0.1 * gap

    def test_loss_monotonic_decreasing_in_pressure(self):
        losses = [self._run(p_c=p, rho=1.85 * p / 20.0)['kinetic_loss_pct']
                  for p in (5.0, 10.0, 20.0, 40.0, 80.0)]
        assert all(a > b for a, b in zip(losses, losses[1:]))

    def test_loss_monotonic_decreasing_in_throat_diameter(self):
        losses = [self._run(d_t=d)['kinetic_loss_pct']
                  for d in (0.01, 0.02, 0.05, 0.1, 0.5)]
        assert all(a > b for a, b in zip(losses, losses[1:]))

    def test_typical_jannaf_loss_band(self):
        """Temsili motor JANNAF tipik kinetik kayıp bandına düşmeli (%0.1-3)."""
        res = self._run()
        assert 0.1 <= res['kinetic_loss_pct'] <= 3.0

    def test_model_note_declares_calibration_status(self):
        res = self._run()
        assert 'calibration' in res['model_note'].lower()


# --------------------------------------------------------------------- #
# Cantera'sız frozen/shifting tahmini ve çözünmeyen ayrım
# --------------------------------------------------------------------- #

class TestFrozenShiftingFallbacks:
    def test_single_gamma_split_estimate(self):
        """isp_frozen/shifting yoksa gamma çiftinden tahmin (Sutton Eş. 3-15b).

        El hesabı (Tc=3200 K, MW=26, Pc=20 bar, Pe=1 bar):
          R = 8314.462618/26 = 319.787 J/(kg·K)
          gamma=1.20 → v=2196.9 m/s → Isp ≈ 224.0 s (shifting tahmini)
          gamma=1.26 → v=2138.6 m/s → Isp ≈ 218.1 s (frozen tahmini)
        """
        results = make_results(isp_frozen=None, isp_shifting=None, isp=230.0,
                               gamma=1.20, gamma_frozen=1.26)
        res = kinetic_efficiency.evaluate(
            combustion_results=results, fidelity='engineering')

        def isp_hand(gamma):
            r = R_UNIVERSAL / 26.0
            ve = np.sqrt(2 * gamma / (gamma - 1) * r * 3200.0
                         * (1 - (1.0 / 20.0) ** ((gamma - 1) / gamma)))
            return ve / G_0

        assert res['isp_shifting'] == pytest.approx(isp_hand(1.20), rel=1e-9)
        assert res['isp_frozen'] == pytest.approx(isp_hand(1.26), rel=1e-9)
        assert res['isp_shifting'] == pytest.approx(224.0, abs=0.5)
        assert res['isp_frozen'] == pytest.approx(218.1, abs=0.5)
        assert res['isp_frozen'] < res['isp_predicted'] < res['isp_shifting']
        assert 'single-gamma' in res['model_note']

    def test_unresolved_split_reports_zero_loss_and_band(self):
        """Ne Cantera çifti ne gamma ayrımı: kayıp 0, bant [0,0], not dürüst."""
        results = make_results(isp_frozen=None, isp_shifting=None, isp=230.0)
        res = kinetic_efficiency.evaluate(
            combustion_results=results, fidelity='engineering')
        assert res['isp_frozen'] == res['isp_shifting'] == pytest.approx(230.0)
        assert res['kinetic_loss_pct'] == pytest.approx(0.0, abs=1e-12)
        assert res['loss_band_pct'] == [pytest.approx(0.0), pytest.approx(0.0)]
        assert 'unresolved' in res['model_note']


# --------------------------------------------------------------------- #
# Seviye 3 — high_fidelity (Cantera sonlu-hız) ve zarif düşüş
# --------------------------------------------------------------------- #

def _h2o2_profile(u=None, n=14):
    """Boğaz→çıkış temsili T(x), P(x) izi (quasi-1D çıktısı taklidi)."""
    x = np.linspace(0.0, 0.15, n)
    profile = {
        'x': x,
        'T': np.linspace(3100.0, 1900.0, n),
        'P': np.geomspace(16e5, 1.0e5, n),
    }
    if u is not None:
        profile['u'] = np.full(n, float(u))
    return profile


def _h2o2_results():
    # H2/O2 (O/F=8, su stokiyometrisi): elemental kütle kesirleri.
    return make_results(p_c=30.0, t_c=3400.0, rho=2.4, c_star=2300.0,
                        isp_frozen=None, isp_shifting=None, isp=380.0,
                        gamma=1.14, gamma_frozen=1.22, mw=16.0,
                        elements={'H': 0.111, 'O': 0.889})


class TestHighFidelityFallbacks:
    def test_no_cantera_falls_back_to_engineering(self, monkeypatch):
        monkeypatch.setattr(ke_module, 'CANTERA_AVAILABLE', False)
        res = KineticEfficiency().evaluate(
            combustion_results=make_results(), fidelity='high_fidelity',
            nozzle_profile=_h2o2_profile())
        assert res['fidelity_requested'] == 'high_fidelity'
        assert res['fidelity_used'] == 'engineering'
        assert 'unavailable' in res['model_note']
        assert res['isp_frozen'] <= res['isp_predicted'] <= res['isp_shifting']

    def test_missing_profile_falls_back(self):
        res = KineticEfficiency().evaluate(
            combustion_results=make_results(), fidelity='high_fidelity')
        assert res['fidelity_used'] == 'engineering'
        assert 'unavailable' in res['model_note']

    def test_invalid_profile_falls_back(self):
        bad = _h2o2_profile()
        bad['x'] = bad['x'][::-1]  # azalan x → geçersiz
        res = KineticEfficiency().evaluate(
            combustion_results=make_results(), fidelity='high_fidelity',
            nozzle_profile=bad)
        assert res['fidelity_used'] == 'engineering'


@pytest.mark.skipif(not CANTERA_AVAILABLE, reason="Cantera kurulu değil")
class TestHighFidelityWithCantera:
    def test_finite_rate_prediction_within_bracket(self):
        ke = KineticEfficiency(mechanism='h2o2.yaml')
        res = ke.evaluate(combustion_results=_h2o2_results(),
                          fidelity='high_fidelity',
                          nozzle_profile=_h2o2_profile())
        assert res['fidelity_used'] == 'high_fidelity'
        assert res['diagnostics']['mechanism'] == 'h2o2.yaml'
        assert res['diagnostics']['n_reactions'] > 0
        assert 0 < res['isp_frozen'] <= res['isp_predicted'] \
            <= res['isp_shifting']
        gap_pct = res['diagnostics']['frozen_shifting_gap_pct']
        assert gap_pct > 0.5  # H2/O2'de disosiyasyon farkı belirgin olmalı
        assert 0.0 <= res['kinetic_loss_pct'] <= gap_pct + 1e-9

    def test_short_residence_freezes_long_residence_equilibrates(self):
        """Fiziksel çapa: hızlı akış (kısa kalma) → frozen'a yakın,
        yavaş akış (uzun kalma) → shifting'e yakın (Bray ani-donma)."""
        ke = KineticEfficiency(mechanism='h2o2.yaml')
        fast = ke.evaluate(combustion_results=_h2o2_results(),
                           fidelity='high_fidelity',
                           nozzle_profile=_h2o2_profile(u=5e5))
        slow = ke.evaluate(combustion_results=_h2o2_results(),
                           fidelity='high_fidelity',
                           nozzle_profile=_h2o2_profile(u=50.0))
        assert fast['fidelity_used'] == 'high_fidelity'
        assert slow['fidelity_used'] == 'high_fidelity'
        assert fast['kinetic_loss_pct'] >= slow['kinetic_loss_pct']
        # Kısa kalma süresi kaybın en az yarısını kilitlemeli
        gap_pct = fast['diagnostics']['frozen_shifting_gap_pct']
        assert fast['kinetic_loss_pct'] > 0.5 * gap_pct

    def test_mechanism_without_reactions_falls_back(self):
        """Termodinamik-salt mekanizma (0 reaksiyon) sonlu-hızı süremez."""
        ke = KineticEfficiency(mechanism='nasa_gas.yaml')
        res = ke.evaluate(combustion_results=_h2o2_results(),
                          fidelity='high_fidelity',
                          nozzle_profile=_h2o2_profile())
        assert res['fidelity_used'] == 'engineering'


# --------------------------------------------------------------------- #
# Köşeleme (clamp) garantisi ve gerçek denge çözümüyle entegrasyon
# --------------------------------------------------------------------- #

class TestBracketGuarantee:
    def test_prediction_clamped_into_bracket(self):
        ke = KineticEfficiency()
        res = ke._build_result(
            fidelity_requested='engineering', fidelity_used='engineering',
            isp_frozen=228.0, isp_shifting=235.0, isp_predicted=250.0,
            loss_band_pct=[0.0, 1.0], model_note='clamp testi',
            diagnostics={})
        assert res['isp_predicted'] == pytest.approx(235.0)
        assert res['kinetic_loss_pct'] == pytest.approx(0.0, abs=1e-12)
        assert res['diagnostics']['prediction_clamped_to_bracket'] is True


class TestIntegrationWithCombustionAnalyzer:
    def test_end_to_end_n2o_htpb(self):
        """Gerçek denge çözümü + korelasyon: şema ve sıra korunmalı."""
        res = KineticEfficiency().evaluate(
            fuel_composition={'htpb': 100}, oxidizer_type='n2o',
            of_ratio=6.0, chamber_pressure=20.0, fidelity='engineering',
            characteristic_length=1.2, throat_diameter=0.03)
        assert REQUIRED_KEYS <= set(res.keys())
        assert res['isp_frozen'] <= res['isp_predicted'] <= res['isp_shifting']
        assert 0.0 <= res['kinetic_loss_pct'] <= 10.0
        lo, hi = res['loss_band_pct']
        assert lo <= res['kinetic_loss_pct'] <= hi
