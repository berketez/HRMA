"""
Leckner (1972) gaz emisivitesi radyasyon modeli testleri.

Eski model gazı kara cisim sayıyordu (q_rad = eps_w*sigma*(Taw^4-Tw^4));
yeni model H2O/CO2 seçici ışımasını Leckner korelasyonuyla hesaplar
(hrma/analysis/heat_transfer_analysis.py). Bu testler korelasyonun
fiziksel değişmezlerini ve entegrasyonun yönünü doğrular:
  - eps_g (0, 1) bandında ve optik derinlikle monoton artar
  - ışıyan tür yokken eps_g ~ 0
  - Tw -> Tg limitinde alpha_g -> eps_g (Kirchhoff tutarlılığı)
  - q_rad her zaman eski kara-cisim değerinden KÜÇÜK (düzeltmenin amacı)
  - tipik roket haznesi koşulunda eps_g literatür bandında (~0.02-0.6;
    NASA SP-8124 küçük motor hazneleri için radyasyon toplam akının
    %5-30'u mertebesini rapor eder)
"""

import math

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import (
    HeatTransferAnalyzer,
    DEFAULT_X_H2O,
    DEFAULT_X_CO2,
    MEAN_BEAM_LENGTH_FACTOR,
)

# Tipik küçük hibrit motor haznesi: 20 bar, 3000 K, D=0.1 m
T_GAS = 3000.0        # K
P_TOTAL = 20.0        # bar
BEAM_L = MEAN_BEAM_LENGTH_FACTOR * 0.1  # m
T_WALL = 800.0        # K


@pytest.fixture(scope="module")
def analyzer():
    return HeatTransferAnalyzer()


class TestGasEmissivity:
    def test_range(self, analyzer):
        eps = analyzer._gas_emissivity(T_GAS, P_TOTAL, BEAM_L)
        assert 0.0 < eps < 1.0

    def test_typical_chamber_band(self, analyzer):
        # Yanma gazı gri degil: tipik hazne kosulunda emisivite
        # kara cisimden (1.0) belirgin kucuk ama ihmal edilemez olmali.
        eps = analyzer._gas_emissivity(T_GAS, P_TOTAL, BEAM_L)
        assert 0.02 < eps < 0.6

    def test_zero_when_no_radiating_species(self, analyzer):
        eps = analyzer._gas_emissivity(T_GAS, P_TOTAL, BEAM_L,
                                       x_H2O=0.0, x_CO2=0.0)
        assert eps == pytest.approx(0.0, abs=1e-12)

    def test_monotonic_in_beam_length(self, analyzer):
        # Optik derinlik arttikca emisivite artmali (doyma oncesi bolge).
        lengths = [0.01, 0.05, 0.1, 0.5]
        eps_vals = [analyzer._gas_emissivity(2000.0, P_TOTAL, L)
                    for L in lengths]
        assert all(b >= a - 1e-9 for a, b in zip(eps_vals, eps_vals[1:]))
        assert eps_vals[-1] > eps_vals[0]

    def test_monotonic_in_pressure(self, analyzer):
        eps_lo = analyzer._gas_emissivity(2000.0, 5.0, BEAM_L)
        eps_hi = analyzer._gas_emissivity(2000.0, 40.0, BEAM_L)
        assert eps_hi > eps_lo

    def test_species_additivity_with_overlap(self, analyzer):
        # eps_g = eps_H2O + eps_CO2 - delta: toplam, tek turlerin her
        # birinden buyuk, aritmetik toplamdan kucuk-esit olmali.
        eps_w = analyzer._gas_emissivity(T_GAS, P_TOTAL, BEAM_L,
                                         x_H2O=DEFAULT_X_H2O, x_CO2=0.0)
        eps_c = analyzer._gas_emissivity(T_GAS, P_TOTAL, BEAM_L,
                                         x_H2O=0.0, x_CO2=DEFAULT_X_CO2)
        eps_t = analyzer._gas_emissivity(T_GAS, P_TOTAL, BEAM_L)
        assert eps_t > max(eps_w, eps_c)
        assert eps_t <= eps_w + eps_c + 1e-9


class TestGasAbsorptivity:
    def test_kirchhoff_limit(self, analyzer):
        # Tw -> Tg: alpha_g -> eps_g
        eps = analyzer._gas_emissivity(2000.0, P_TOTAL, BEAM_L)
        alpha = analyzer._gas_absorptivity(2000.0, 2000.0, P_TOTAL, BEAM_L)
        assert alpha == pytest.approx(eps, rel=1e-6)

    def test_range(self, analyzer):
        alpha = analyzer._gas_absorptivity(T_GAS, T_WALL, P_TOTAL, BEAM_L)
        assert 0.0 < alpha < 1.0


class TestRadiationFlux:
    def test_positive_for_hot_gas(self, analyzer):
        q = analyzer._gas_radiation_flux(T_GAS, T_WALL, P_TOTAL, BEAM_L)
        assert q > 0.0

    def test_below_black_body(self, analyzer):
        # Duzeltmenin varolus nedeni: eski kara-cisim akisindan kucuk olmali.
        sigma = analyzer.stefan_boltzmann
        eps_wall = 0.8
        q_old = eps_wall * sigma * (T_GAS ** 4 - T_WALL ** 4)
        q_new = analyzer._gas_radiation_flux(T_GAS, T_WALL, P_TOTAL, BEAM_L,
                                             wall_emissivity=eps_wall)
        assert q_new < q_old
        # Plan bulgusu ~2-5x abarti diyordu; en az 1.5x azalma bekleriz.
        assert q_new < q_old / 1.5

    def test_zero_without_radiators(self, analyzer):
        q = analyzer._gas_radiation_flux(T_GAS, T_WALL, P_TOTAL, BEAM_L,
                                         x_H2O=0.0, x_CO2=0.0)
        assert q == pytest.approx(0.0, abs=1e-6)

    def test_magnitude_reasonable(self, analyzer):
        # 3000 K / 20 bar / D=0.1 m icin gaz radyasyonu ~0.1-2 MW/m^2
        # mertebesinde olmali (kara cisim ~4.6 MW/m^2'nin altinda,
        # sifira da yapismamali).
        q = analyzer._gas_radiation_flux(T_GAS, T_WALL, P_TOTAL, BEAM_L)
        assert 5e4 < q < 3e6


class TestIntegration:
    """analyze_heat_transfer / analyze_axial_profile entegrasyon dumani."""

    MOTOR = {
        'chamber_pressure': 20.0,     # bar
        'chamber_temperature': 3000,  # K
        'chamber_diameter': 0.1,      # m
        'chamber_length': 0.3,        # m
        'throat_diameter': 0.03,      # m
        'mdot_total': 1.2,            # kg/s
        'expansion_ratio': 4.0,
        # burn_time ARTIK ZORUNLU (parti 31, ısı zinciri girdi kapısı:
        # `motor_data.get('burn_time', 10)` kaldırıldı — uydurma varsayılan
        # yasağı). Buraya yazılan 10,0 s, kaldırılan varsayılanın TAM
        # kendisidir: bu vakanın fiziği değişmedi, örtük olan açık yazıldı.
        'burn_time': 10.0,            # s
    }

    @staticmethod
    def _sonlu_olmayan_yapraklar(dugum, yol='sonuc'):
        """Sonlu OLMAYAN her sayısal yaprağı adıyla toplar.

        T1-1 (parti 31) — eski bekçi şuydu::

            assert 'nan' not in flat.lower() or 'NaN' not in flat

        Python NaN'ı daima ``nan`` yazar, dolayısıyla sağ taraf ('NaN'
        büyük harfli aranıyor) DAİMA doğrudur ve OR koşulsuz geçer.
        ÖLÇÜLDÜ: sonucun tüm sayısal yaprakları NaN yapıldığında eski
        assert HİÇ tepki vermiyordu (1 passed). Ayrıca dize araması
        ``inf``'i ve dizi içindeki NaN'ları da göremiyordu.

        Yeni bekçi ağacı gezip ``math.isfinite`` ile bakar — aynı dosyadaki
        ``test_axial_profile_q_finite_positive`` zaten bu deseni (np.isfinite)
        kullanıyordu.
        """
        kotu = []
        if isinstance(dugum, dict):
            for k, v in dugum.items():
                kotu += TestIntegration._sonlu_olmayan_yapraklar(
                    v, f'{yol}.{k}')
        elif isinstance(dugum, (list, tuple)):
            for i, v in enumerate(dugum):
                kotu += TestIntegration._sonlu_olmayan_yapraklar(
                    v, f'{yol}[{i}]')
        elif isinstance(dugum, np.ndarray):
            if dugum.size and not np.all(np.isfinite(dugum)):
                kotu.append(f'{yol} (dizi)')
        elif isinstance(dugum, bool):
            pass
        elif isinstance(dugum, (int, float, np.floating, np.integer)):
            if not math.isfinite(float(dugum)):
                kotu.append(f'{yol} = {dugum!r}')
        return kotu

    def test_analyze_heat_transfer_runs(self, analyzer):
        res = analyzer.analyze_heat_transfer(dict(self.MOTOR),
                                             material='steel',
                                             cooling_type='natural')
        # Sema esnek: en azindan sonuc sozlugu bos degil ve icinde
        # sonlu sayisal degerler var.
        assert isinstance(res, dict) and res
        kotu = self._sonlu_olmayan_yapraklar(res)
        assert not kotu, (
            'ısı transferi sonucunda sonlu OLMAYAN sayısal yaprak(lar) var — '
            'NaN/inf kullanıcıya sayı gibi gider:\n  ' + '\n  '.join(kotu))

    def test_axial_profile_q_finite_positive(self, analyzer):
        prof = analyzer.analyze_axial_profile(dict(self.MOTOR),
                                              n_stations=24,
                                              material='steel')
        q = np.asarray(prof['q_MW'], dtype=float)
        assert np.all(np.isfinite(q))
        assert np.all(q > 0.0)
        # Bogaz istasyonu tepe akiyi tasimali (Bartz karakteri korunmus).
        ti = prof['throat_index']
        assert q[ti] == pytest.approx(q.max(), rel=0.05)

    def test_composition_override_reduces_radiation(self, analyzer):
        # Isiyan tur kesirleri sifirlanirsa toplam aki dusmali
        # (radyasyon bileseni kaybolur, konveksiyon kalir).
        base = analyzer.analyze_axial_profile(dict(self.MOTOR), n_stations=16,
                                              material='steel')
        no_rad = dict(self.MOTOR, x_H2O=0.0, x_CO2=0.0)
        prof2 = analyzer.analyze_axial_profile(no_rad, n_stations=16,
                                               material='steel')
        q1 = np.asarray(base['q_MW'], dtype=float)
        q2 = np.asarray(prof2['q_MW'], dtype=float)
        assert q2.max() < q1.max()
