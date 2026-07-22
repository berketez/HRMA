"""
Hibrit roket regresyon modülü doğrulama testleri (Marxman teorisi + deneysel veri).

Bu dosya HRMA regresyon modelinin (G_total Marxman düzeltmesi, O/F kayması
performans geri beslemesi, parafin entrainment katsayıları) literatür ve gerçek
deneysel veriyle uyumunu doğrular. Kaynaklar testlerin içinde atıflıdır.

Referans vakalar:
  1. Rezaei et al. HTPB/N2O (altın-standart): G_ox=68.8 kg/m²·s, Pc=28.6 bar,
     O/F=3.78, ÖLÇÜLEN r=0.779 mm/s. (Regresyon hızı doğrulaması; Scientia
     Iranica B 25(1) 2018, Tablo 4 test 26.)
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
# Kaynak: H. Rezaei, M.R. Soltani, A.R. Mohammadi, Scientia Iranica B, 25(1),
# 253-265, 2018 — Tablo 4 test 26 (s.259) + Tablo 2 (s.257). ARGE doğrudan
# okuma: docs/arge-guven-2026-07/arge_hibrit_veri.md, Kampanya 1 (2026-07-17).
# 2026-07-17 düzeltmesi (G1b bulgusu): eski sabitlerdeki O/F=1.766 makalenin
# ENJEKTÖR ALANI (1.766 mm², Tablo 2) ile karışmıştı — Tablo 4'te test 26'nın
# ölçülen O/F'si 3.78'dir. c* 1513 -> 1514 (tablo değeri), rho_f 920 (genel
# HTPB) -> 983 (makalenin kendi partisi, Tablo 2), tek-değer eta 0.97 ->
# makale metnindeki %94-98 bandı (test bazında ayrıştırılmamış, s.260).
REZAEI = {
    'G_ox': 68.8,        # kg/m²·s (=6.88 g/cm²·s, Tablo 4 test 26 — yanma
                         #  ortalamalı port akısı)
    'Pc': 28.6,          # bar (Tablo 4 test 26)
    'OF': 3.78,          # ölçülen ortalama O/F (Tablo 4 test 26)
    'r_meas': 0.779,     # mm/s — ÖLÇÜLEN regresyon hızı (Tablo 4 test 26)
    'cstar_meas': 1514.0,  # m/s — ölçülen (teslim) c* (Tablo 4 test 26)
    'eta_cstar_band': (0.94, 0.98),  # yanma verimi bandı (metin, s.260)
    'rho_f': 983.0,      # kg/m³ — makalenin HTPB partisi (Tablo 2)
    # Yanma-ortalamalı port çapı: (Dp_i + Dp_f)/2 = (37.0+47.2)/2 mm.
    # Tutarlılık: G_ox·A(D_mean) = 68.8·π/4·0.0421² = 95.77 g/s = makalenin
    # ölçülen mdot_ox'u (Tablo 4) — geometri/akı seti kendi içinde kapanır.
    'D_port_mean': 0.0421,  # m
    'L_grain': 0.2504,      # m (Tablo 4 test 26)
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
        # Makalenin GERÇEK test geometrisi (Tablo 4 test 26): yanma-ortalamalı
        # port çapı ve gerçek grain boyu. (Eski sürüm L'yi yanlış O/F=1.766
        # üzerinden sentetik boyutluyordu — L=0.60 m çıkıyordu, makale grain'i
        # 0.2504 m; G_fuel ~2 kat şişiyordu.)
        reg = RegressionAnalyzer.regression_rate(
            a, n, REZAEI['G_ox'], rho_f=REZAEI['rho_f'],
            port_diameter=REZAEI['D_port_mean'],
            grain_length=REZAEI['L_grain'], flux_mode='total'
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
        """Kalan sapma ±%55 içinde (HTPB/N2O partiler arası 'a' saçılma sınırı).

        Fiziksel gerekçe: HRMA'nın HTPB katsayıları Doran (AIAA 2007-5352)
        partisine aittir; Rezaei'nin kendi fit'i (Eş. 10: r=0.3977·Go^0.3667)
        ile oranı G=6.88 g/cm²·s'de 0.478'dir (~2.1x partiler arası 'a'
        saçılması) — yani bu partiye karşı beklenen taban sapma ≈ −%52'dir.
        G_total düzeltmesi bunu −%47'ye çeker (doğru yön, ayrı test). Üst
        sınır %55 = belgelenmiş saçılma (+%3 pay); ondalık-eşleşme değil,
        parti saçılması içinde kalma denetimidir. (Eski %40 sınırı, yanlış
        O/F=1.766'nın G_fuel'i ~2 kat şişirmesi sayesinde tutuyordu — düzgün
        sabitlerle fiziksel olarak savunulamazdı.)
        """
        dev = abs(self._r_total() - REZAEI['r_meas']) / REZAEI['r_meas']
        assert dev < 0.55, f"Kalan sapma %{dev*100:.0f} > %55 (parti saçılma sınırı)"


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
