"""
Hibrit roket regresyon modülü doğrulama testleri (Marxman teorisi + deneysel veri).

Bu dosya HRMA regresyon modelinin (G_total Marxman düzeltmesi, O/F kayması
performans geri beslemesi, parafin entrainment katsayıları) literatür ve gerçek
deneysel veriyle uyumunu doğrular. Kaynaklar testlerin içinde atıflıdır.

Referans vakalar:
  1. Rezaei et al. HTPB/N2O (altın-standart): G_ox=68.8 kg/m²·s, Pc=28.6 bar,
     O/F=1.766, ÖLÇÜLEN r=0.779 mm/s. (Regresyon hızı doğrulaması.)
  2. Karabeyoglu et al., JPP 20(6) 2004 / Zilliac AIAA 2006-4504 SP-1a parafin:
     r[mm/s] = 0.488·G_ox[g/cm²·s]^0.62 (entrainment fit'e dahil).
  3. Chiaverini et al., JPP 15(3) 1999 HTPB/GOX bandı (sanity).

Marxman & Gilbert (1963); Sutton & Biblarz, Rocket Propulsion Elements, 9th ed.,
Böl. 16; Chiaverini & Kuo, AIAA Progress Vol. 218 (2007).

FİZİKSEL SINIR NOTU: Hibrit regresyon korelasyonları çalışmadan çalışmaya
±%20-30 (HTPB/N2O için 'a' katsayısı ~2x) saçılır. Bu nedenle toleranslar
gevşek tutulmuştur; amaç EĞİLİMİ (G_total > G_ox; konservatif yön) ve birim
tutarlılığını doğrulamaktır, ondalık-eşleşme değil.
"""

import numpy as np
import pytest

from hrma.analysis.regression_analysis import RegressionAnalyzer, LIQUEFYING_FUELS
from hrma.data.propellant_database import HYBRID_REGRESSION_COEFFICIENTS as REG


# --- Referans sabitler (deneysel/literatür) ---
REZAEI = {
    'G_ox': 68.8,      # kg/m²·s  (=6.88 g/cm²·s)
    'Pc': 28.6,        # bar
    'OF': 1.766,       # ölçülen ortalama O/F
    'r_meas': 0.779,   # mm/s — ÖLÇÜLEN regresyon hızı
    'cstar_meas': 1513.0,  # m/s — ölçülen c*
    'eta_cstar': 0.97,
    'rho_f': 920.0,    # kg/m³ HTPB
}


class TestMarxmanGTotal:
    """Bulgu #1: regresyon G_total = G_ox + G_fuel kullanmalı (Marxman)."""

    def test_g_total_exceeds_g_ox(self):
        """G_total daima G_ox'tan büyük olmalı (yakıt akısı eklenir)."""
        a, n = REG['htpb']['a'], REG['htpb']['n']
        reg = RegressionAnalyzer.regression_rate(
            a, n, G_ox=68.8, rho_f=920.0, port_diameter=0.05,
            grain_length=0.3, flux_mode='total'
        )
        assert reg['G_total'] > reg['G_ox']
        assert reg['G_fuel'] > 0.0
        assert reg['converged'] is True

    def test_g_total_gives_higher_regression_than_g_ox(self):
        """Marxman G_total, G_ox-only'den DAHA YÜKSEK r vermeli (konservatif).

        Düşük r'yi tahmin etmek web tükenme süresini iyimser (güvensiz)
        gösterir; G_total düzeltmesi güvenli yöne çeker.
        """
        a, n = REG['htpb']['a'], REG['htpb']['n']
        common = dict(rho_f=920.0, port_diameter=0.05, grain_length=0.3)
        r_ox = RegressionAnalyzer.regression_rate(a, n, 68.8, flux_mode='ox')['r_dot']
        r_tot = RegressionAnalyzer.regression_rate(a, n, 68.8, flux_mode='total', **common)['r_dot']
        assert r_tot > r_ox

    def test_ox_mode_matches_analytic_power_law(self):
        """Geriye uyum: 'ox' modu tam olarak a·G_ox^n vermeli."""
        a, n = REG['htpb']['a'], REG['htpb']['n']
        G = 150.0
        reg = RegressionAnalyzer.regression_rate(a, n, G, flux_mode='ox')
        assert reg['r_dot'] == pytest.approx(a * G ** n, rel=1e-12)
        assert reg['G_total'] == pytest.approx(G, rel=1e-12)

    def test_iteration_converges(self):
        """Sabit-nokta iterasyonu makul adımda yakınsamalı."""
        a, n = REG['htpb']['a'], REG['htpb']['n']
        reg = RegressionAnalyzer.regression_rate(
            a, n, 68.8, rho_f=920.0, port_diameter=0.05,
            grain_length=0.3, flux_mode='total'
        )
        assert reg['converged']
        assert reg['iterations'] < 50


class TestRezaeiRegressionRate:
    """Rezaei et al. HTPB/N2O altın-standart regresyon hızı doğrulaması.

    Doran (AIAA 2007-5352) HTPB/N2O katsayıları Rezaei'nin HTPB partisinden
    farklı bir partiye aittir; ~2x 'a' saçılması beklenir. Test, G_total
    düzeltmesinin sapmayı G_ox-only'ye göre AZALTTIĞINI (doğru yön) ve sonucun
    fiziksel bant içinde kaldığını doğrular.
    """

    def _r_ox(self):
        a, n = REG['htpb']['a'], REG['htpb']['n']
        return RegressionAnalyzer.regression_rate(a, n, REZAEI['G_ox'], flux_mode='ox')['r_dot'] * 1000

    def _r_total(self):
        a, n = REG['htpb']['a'], REG['htpb']['n']
        # O/F=1.766 ile tutarlı port geometrisi: mdot_f = mdot_ox/OF
        D = 0.05
        A = np.pi * (D / 2) ** 2
        mdot_ox = REZAEI['G_ox'] * A
        mdot_f_target = mdot_ox / REZAEI['OF']
        r_ox_si = a * REZAEI['G_ox'] ** n
        L = mdot_f_target / (REZAEI['rho_f'] * np.pi * D * r_ox_si)
        reg = RegressionAnalyzer.regression_rate(
            a, n, REZAEI['G_ox'], rho_f=REZAEI['rho_f'],
            port_diameter=D, grain_length=L, flux_mode='total'
        )
        return reg['r_dot'] * 1000

    def test_g_total_reduces_deviation(self):
        """G_total sapması, G_ox-only sapmasından küçük olmalı (iyileşme)."""
        r_meas = REZAEI['r_meas']
        dev_ox = abs(self._r_ox() - r_meas) / r_meas
        dev_total = abs(self._r_total() - r_meas) / r_meas
        assert dev_total < dev_ox, (
            f"G_total sapması ({dev_total:.1%}) G_ox-only'den "
            f"({dev_ox:.1%}) büyük — düzeltme yanlış yönde"
        )

    def test_g_ox_only_underpredicts(self):
        """G_ox-only ölçülen değerin ALTINDA kalmalı (bilinen non-konservatif hata)."""
        assert self._r_ox() < REZAEI['r_meas']

    def test_regression_within_physical_band(self):
        """Tahmin edilen r, hibrit fiziksel bandında (0.2-2 mm/s) olmalı."""
        r = self._r_total()
        assert 0.2 < r < 2.0, f"r={r:.3f} mm/s fiziksel bant dışında"

    def test_residual_within_interstudy_scatter(self):
        """Kalan sapma ±%40 içinde (HTPB/N2O 'a' katsayısı saçılma sınırı).

        ±%20-30 tek-parti sınırı; partiler arası ~2x 'a' saçılması nedeniyle
        burada %40 üst sınır kullanılır (dürüst fiziksel limit).
        """
        dev = abs(self._r_total() - REZAEI['r_meas']) / REZAEI['r_meas']
        assert dev < 0.40, f"Kalan sapma %{dev*100:.0f} > %40 (beklenmeyen)"


class TestParaffinEntrainment:
    """Bulgu #3: parafin entrainment. Karabeyoglu SP-1a a/n entrainment'i
    ZATEN içerir; merkezi DB bu katsayıları kullanır -> ek çarpan UYGULANMAZ.
    """

    def test_paraffin_marked_liquefying(self):
        assert 'paraffin' in LIQUEFYING_FUELS
        assert LIQUEFYING_FUELS['paraffin']['entrainment_in_correlation'] is True

    def test_paraffin_si_matches_published_correlation(self):
        """DB SI katsayıları, yayınlanmış r[mm/s]=0.488·G[g/cm²·s]^0.62'yi
        ±%2 içinde üretmeli (entrainment fit'e dahil)."""
        a, n = REG['paraffin']['a'], REG['paraffin']['n']
        for G_cgs in (2.0, 5.0, 10.0, 20.0):
            G_si = G_cgs * 10.0  # 1 g/cm²·s = 10 kg/m²·s
            r_db = RegressionAnalyzer.regression_rate(a, n, G_si, flux_mode='ox')['r_dot'] * 1000
            r_pub = 0.488 * G_cgs ** 0.62
            assert r_db == pytest.approx(r_pub, rel=0.02), (
                f"G={G_cgs} g/cm²·s: DB {r_db:.3f} vs Karabeyoglu {r_pub:.3f} mm/s"
            )

    def test_paraffin_exceeds_htpb(self):
        """Parafin (sıvılaşan, entrainment'li) aynı G'de HTPB'den 3-4x hızlı
        regrese olmalı — entrainment'in fiziksel imzası."""
        Gp = REG['paraffin']
        Gh = REG['htpb']
        G_si = 100.0  # kg/m²·s
        r_par = Gp['a'] * G_si ** Gp['n']
        r_htpb = Gh['a'] * G_si ** Gh['n']
        assert r_par / r_htpb > 2.5, (
            f"Parafin/HTPB oranı {r_par/r_htpb:.2f} < 2.5 — entrainment kaybolmuş"
        )


class TestHTPBBandSanity:
    """Chiaverini HTPB/GOX bandı sanity (JPP 15(3) 1999)."""

    def test_htpb_band(self):
        a, n = REG['htpb']['a'], REG['htpb']['n']
        # Tipik hibrit G_ox aralığında r monoton artmalı ve bantta kalmalı.
        prev = 0.0
        for G_cgs in (5.0, 10.0, 20.0, 40.0):
            r = RegressionAnalyzer.regression_rate(a, n, G_cgs * 10.0, flux_mode='ox')['r_dot'] * 1000
            assert r > prev, "r, G_ox ile artmıyor (power-law bozuk)"
            assert 0.1 < r < 3.0, f"r={r:.3f} mm/s Chiaverini bandı dışında"
            prev = r


class TestEngineIntegration:
    """Motor sınıfı entegrasyonu: O/F kayması -> c*/Isp geri beslemesi (bulgu #2)
    ve API korunumu."""

    def _engine(self, flux_mode='total', track=True):
        from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        return HybridRocketEngine(
            thrust=1000, burn_time=10, of_ratio=2.0, chamber_pressure=20,
            fuel_type='htpb', initial_gox=150, flux_mode=flux_mode,
            track_performance=track
        )

    def test_engine_runs_total_mode(self):
        r = self._engine('total').calculate()
        assert r['regression_flux_mode'] == 'total'
        assert r['g_total_initial'] > r['g_ox_initial']

    def test_of_shift_feeds_performance(self):
        """Bulgu #2: O/F kayması c*/Isp'ye yansımalı (donmamış)."""
        r = self._engine('total', track=True).calculate()
        assert 'of_shift_performance' in r
        p = r['of_shift_performance']
        # O/F yanma boyunca değişmeli (port büyür -> O/F kayar)
        assert max(p['of_ratio']) > min(p['of_ratio'])
        # Zaman-ortalamalı c* tasarım O/F c*'ından farklı olmalı (kayma etkisi)
        assert p['c_star_time_avg'] != pytest.approx(p['c_star_design_of'], rel=1e-6)
        # c*/Isp fiziksel bantta
        assert all(1000 < c < 1900 for c in p['c_star'])
        assert all(100 < isp < 350 for isp in p['isp'])

    def test_api_keys_preserved(self):
        """Mevcut dönen sözlük anahtarları korunmalı (geriye uyum)."""
        r = self._engine('total').calculate()
        required = [
            'regression_rate', 'regression_rate_avg', 'g_ox_initial',
            'g_ox_final', 'of_ratio_initial', 'of_ratio_final',
            'fuel_mass_flow_final', 'grain_length', 'g_ox_design',
            'c_star', 'isp', 'fuel_mass', 'oxidizer_mass',
        ]
        for k in required:
            assert k in r, f"API anahtarı kayıp: {k}"

    def test_ox_mode_backward_compatible(self):
        """flux_mode='ox' eski G_ox-only davranışını vermeli."""
        r = self._engine('ox', track=False).calculate()
        a, n = REG['htpb']['a'], REG['htpb']['n']
        # Başlangıç r_dot tam olarak a·G_ox_design^n olmalı
        expected = a * r['g_ox_initial'] ** n
        assert r['regression_rate'] == pytest.approx(expected, rel=1e-9)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
