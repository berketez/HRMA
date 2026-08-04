"""
F1 yarı-1B lüle iç akışı doğrulama testleri (hrma.flow.quasi1d + separation).

Kapsam (yol haritası F1 doğrulama kalemleri):
  (a) İzantropik bağıntılar analitik gidiş-dönüş: M ↔ A/A* (iki dal),
      M ↔ P0/P; ayrıca elle hesaplanan tablo değerleri (γ=1.4, M=2).
  (b) Normal şok (Rankine-Hugoniot) bağıntıları: analitik değerlerle
      karşılaştırma (M1=2, γ=1.4), zayıf şok limiti, entropi artışı.
  (c) Şok konumu korunumu: verilen Pb için çözülen şokun gerisindeki
      basınç dağılımının çıkışta Pb'yi TAM karşıladığı; ayrıca her
      istasyonda rho·u·A kütle akısı sabitliği (şok boyunca dahil).
  (d) Sınır rejim sürekliliği: Pb süpürmesinde boğulma sınırı ve
      şok-çıkışta sınırında kütle debisi / profil süreksizliği yok;
      şok konumu Pb azaldıkça monoton çıkışa yürür.
  Ek: rejim sınıflandırması, ayrılma kriterlerinin analitik eşik
      değerleri ve geçerlilik beyanları, NOT_MODELLED beyanları,
      girdi doğrulama.
  JSON vakaları: data/validation altındaki künyeli kabul vakaları
      (nozzle_isentropic_area_mach, nozzle_normal_shock_divergent,
      nozzle_separation_criteria) birebir sağlanır; şok vakası ayrıca
      solve_nozzle ile UÇTAN UCA yeniden bulunur.
  Bekçiler: separation.py ve quasi1d.py docstring'lerinde vadedilen
      motor katmanı (engines/nozzle_design.py) değer/bağıntı eşitlikleri.

Analitik referans değerlerin kaynağı: Anderson, "Modern Compressible
Flow", 3. baskı, Böl. 3 ve 5 (izantropik/şok tabloları A.1 ve A.2'nin
kapalı biçim bağıntıları); NACA Report 1135 (1953).
"""

import json
import pathlib

import numpy as np
import pytest

from hrma.flow.quasi1d import (
    QUASI1D_NOT_MODELLED,
    REGIME_CHOKED_SUBSONIC,
    REGIME_NO_FLOW,
    REGIME_NORMAL_SHOCK,
    REGIME_OVEREXPANDED,
    REGIME_PERFECT,
    REGIME_SUBSONIC,
    REGIME_UNDEREXPANDED,
    area_ratio_from_mach,
    choked_mass_flow,
    critical_pressures,
    isentropic_ratios,
    mach_from_area_ratio,
    mach_from_pressure_ratio,
    normal_shock_relations,
    solve_nozzle,
)
from hrma.flow.separation import (
    SEPARATION_NOT_MODELLED,
    SUMMERFIELD_FACTOR_BAND,
    SUMMERFIELD_FACTOR_DEFAULT,
    assess_separation,
    kalt_badal_pressure_ratio,
    schmucker_pressure_ratio,
    summerfield_pressure_ratio,
)

_VALIDATION_DIR = (pathlib.Path(__file__).resolve().parents[2]
                   / 'data' / 'validation')


def _load_case(name):
    with open(_VALIDATION_DIR / name, encoding='utf-8') as fh:
        return json.load(fh)

# ---------------------------------------------------------------------------
# Ortak test geometrisi ve gaz durumu
# ---------------------------------------------------------------------------

A_THROAT = 8.0e-4   # m² (d_t ≈ 32 mm)

# Rezervuar koşulları: N2O/HTPB sınıfı hibrit motor bandında
# (testler boyunca TEK ortak gaz durumu — SI birimleri).
P0 = 30e5      # Pa
T0 = 3200.0    # K
GAMMA_GAS = 1.25
R_GAS = 320.0  # J/(kg·K)


def _cd_profile(n=81, throat_x=0.4, k=3.0):
    """Tek boğazlı analitik yakınsak-ıraksak profil.

    A(x) = A_t·(1 + k·(x − x_t)²), x ∈ [0, 1]; n=81 için x_t = 0.4 tam
    ızgara noktasıdır (boğaz istasyonda). Çıkış alan oranı 1 + k·0.36.
    """
    x = np.linspace(0.0, 1.0, n)
    area = A_THROAT * (1.0 + k * (x - throat_x) ** 2)
    return x, area


@pytest.fixture(scope='module')
def geometry():
    return _cd_profile()


@pytest.fixture(scope='module')
def crits(geometry):
    x, area = geometry
    return critical_pressures(float(area[-1] / area.min()), P0, GAMMA_GAS)


def _solve(Pb, geometry):
    x, area = geometry
    return solve_nozzle(x, area, P0, T0, GAMMA_GAS, R_GAS, Pb)


# ---------------------------------------------------------------------------
# (a) İzantropik gidiş-dönüş
# ---------------------------------------------------------------------------

class TestIzantropikRoundTrip:

    @pytest.mark.parametrize('gamma', [1.2, 1.25, 1.4])
    @pytest.mark.parametrize('mach', [0.05, 0.3, 0.8, 1.5, 2.5, 4.0, 8.0])
    def test_alan_mach_gidis_donus(self, gamma, mach):
        eps = area_ratio_from_mach(mach, gamma)
        mach_back = mach_from_area_ratio(eps, gamma, supersonic=(mach > 1.0))
        assert mach_back == pytest.approx(mach, rel=1e-9)

    @pytest.mark.parametrize('gamma', [1.2, 1.25, 1.4])
    @pytest.mark.parametrize('mach', [0.05, 0.3, 0.8, 1.0, 1.5, 2.5, 4.0])
    def test_basinc_mach_gidis_donus(self, gamma, mach):
        p0_over_p = 1.0 / isentropic_ratios(mach, gamma)[1]
        assert mach_from_pressure_ratio(p0_over_p, gamma) == pytest.approx(
            mach, rel=1e-10, abs=1e-12)

    def test_bilinen_degerler_gamma14_m2(self):
        """γ=1.4, M=2 kapalı biçim değerleri (Anderson Tablo A.1 bağıntıları).

        A/A* = (1/2)·[(2/2.4)·1.8]^3 = 1.6875 (tam),
        T0/T = 1.8 (tam),  P0/P = 1.8^3.5 ≈ 7.82445.
        """
        assert area_ratio_from_mach(2.0, 1.4) == pytest.approx(1.6875,
                                                               rel=1e-12)
        t_ratio, p_ratio, rho_ratio = isentropic_ratios(2.0, 1.4)
        assert 1.0 / t_ratio == pytest.approx(1.8, rel=1e-12)
        assert 1.0 / p_ratio == pytest.approx(1.8 ** 3.5, rel=1e-12)
        assert 1.0 / rho_ratio == pytest.approx(1.8 ** 2.5, rel=1e-12)

    def test_sonik_noktada_birim(self):
        assert area_ratio_from_mach(1.0, 1.25) == pytest.approx(1.0, rel=1e-12)
        assert mach_from_area_ratio(1.0, 1.25) == 1.0

    def test_alan_orani_birden_kucuk_reddedilir(self):
        with pytest.raises(ValueError):
            mach_from_area_ratio(0.9, 1.25)


# ---------------------------------------------------------------------------
# (b) Normal şok analitik karşılaştırma
# ---------------------------------------------------------------------------

class TestNormalSok:

    def test_analitik_degerler_gamma14_m2(self):
        """γ=1.4, M1=2: M2=1/√3, P2/P1=4.5, T2/T1=1.6875, P02/P01≈0.72087.

        Kapalı biçim: Anderson 3. baskı, Eş. 3.51/3.57/3.59/3.63
        (NACA 1135 tablolarıyla aynı).
        """
        mach2, p2_p1, T2_T1, p02_p01 = normal_shock_relations(2.0, 1.4)
        assert mach2 == pytest.approx(1.0 / np.sqrt(3.0), rel=1e-12)
        assert p2_p1 == pytest.approx(4.5, rel=1e-12)
        assert T2_T1 == pytest.approx(1.6875, rel=1e-12)
        assert p02_p01 == pytest.approx(0.72087, abs=1e-5)

    def test_zayif_sok_limiti(self):
        mach2, p2_p1, T2_T1, p02_p01 = normal_shock_relations(1.0 + 1e-9,
                                                              1.25)
        assert mach2 == pytest.approx(1.0, abs=1e-6)
        assert p2_p1 == pytest.approx(1.0, abs=1e-6)
        assert T2_T1 == pytest.approx(1.0, abs=1e-6)
        assert p02_p01 == pytest.approx(1.0, abs=1e-6)

    @pytest.mark.parametrize('gamma', [1.2, 1.25, 1.4])
    @pytest.mark.parametrize('mach1', [1.2, 2.0, 3.5, 5.0])
    def test_entropi_artisi(self, gamma, mach1):
        """İkinci yasa: şok boyunca s2−s1 = −R·ln(P02/P01) > 0."""
        _, _, _, p02_p01 = normal_shock_relations(mach1, gamma)
        assert p02_p01 < 1.0

    def test_ses_alti_reddedilir(self):
        with pytest.raises(ValueError):
            normal_shock_relations(0.8, 1.25)


# ---------------------------------------------------------------------------
# (c) Şok konumu: çıkışta Pb'nin TAM karşılanması + korunum
# ---------------------------------------------------------------------------

class TestSokKonumuKorunum:

    @pytest.fixture(scope='class')
    def shock_solution(self, geometry, crits):
        Pb = 0.5 * (crits['shock_at_exit_Pa']
                    + crits['choked_subsonic_exit_Pa'])
        return _solve(Pb, geometry), Pb

    def test_rejim_ve_sok_konumu(self, shock_solution, geometry):
        res, _ = shock_solution
        x, _area = geometry
        assert res['regime'] == REGIME_NORMAL_SHOCK
        assert res['shock'] is not None
        assert res['throat']['x_m'] < res['shock']['x_m'] < x[-1]
        assert res['shock']['mach_upstream'] > 1.0
        assert res['shock']['mach_downstream'] < 1.0

    def test_cikis_basinci_pb_tam_karsilar(self, shock_solution):
        res, Pb = shock_solution
        assert res['pressure_Pa'][-1] == pytest.approx(Pb, rel=1e-8)
        assert res['exit']['back_pressure_match'] is True

    def test_sok_gerisi_bagimsiz_yeniden_kurulum(self, shock_solution,
                                                 geometry, crits):
        """Çözücüden bağımsız korunum kontrolü: raporlanan şok Mach'ından
        Rankine-Hugoniot + ses-altı izantropik difüzyonla çıkış basıncı
        yeniden kurulur ve Pb ile karşılaştırılır."""
        res, Pb = shock_solution
        x, area = geometry
        mach1 = res['shock']['mach_upstream']
        _, _, _, p02_p01 = normal_shock_relations(mach1, GAMMA_GAS)
        eps_e = float(area[-1] / area.min())
        mach_exit = mach_from_area_ratio(eps_e * p02_p01, GAMMA_GAS,
                                         supersonic=False)
        p_exit = P0 * p02_p01 * isentropic_ratios(mach_exit, GAMMA_GAS)[1]
        assert p_exit == pytest.approx(Pb, rel=1e-9)

    def test_kutle_akisi_sok_boyunca_sabit(self, shock_solution, geometry):
        """rho·u·A her istasyonda (şokun iki yanında da) mdot'a eşit."""
        res, _ = shock_solution
        _x, area = geometry
        rho = res['pressure_Pa'] / (R_GAS * res['temperature_K'])
        u = res['mach'] * np.sqrt(GAMMA_GAS * R_GAS * res['temperature_K'])
        flux = rho * u * area
        mdot = res['mass_flow_kg_s']
        assert mdot == pytest.approx(
            choked_mass_flow(P0, T0, GAMMA_GAS, R_GAS, float(area.min())),
            rel=1e-12)
        assert np.max(np.abs(flux - mdot)) / mdot < 1e-9
        assert res['mass_conservation_rel_residual'] < 1e-9

    def test_sok_atlamasi_istasyonlarda_gorunur(self, shock_solution):
        """Şoktan hemen önceki istasyon ses-üstü, sonraki ses-altı."""
        res, _ = shock_solution
        x = res['x_m']
        x_shock = res['shock']['x_m']
        before = res['mach'][(x <= x_shock) & (x > res['throat']['x_m'])]
        after = res['mach'][x > x_shock]
        assert before[-1] > 1.0
        assert after[0] < 1.0

    def test_sok_gerisinde_durma_basinci_dusuk(self, shock_solution):
        """Şok ardı istasyonlarda P0 yerine P02 kullanıldığının kanıtı:
        son istasyonda P/(izantropik oran) = P02 < P0."""
        res, _ = shock_solution
        mach_exit = res['exit']['mach']
        p0_exit = (res['exit']['pressure_Pa']
                   / isentropic_ratios(mach_exit, GAMMA_GAS)[1])
        assert p0_exit == pytest.approx(
            res['shock']['stagnation_pressure_downstream_Pa'], rel=1e-9)
        assert p0_exit < P0


# ---------------------------------------------------------------------------
# Rejim sınıflandırması
# ---------------------------------------------------------------------------

class TestRejimSiniflandirma:

    def test_ses_alti_bogulmamis(self, geometry, crits):
        Pb = 0.5 * (crits['choked_subsonic_exit_Pa'] + P0)
        res = _solve(Pb, geometry)
        assert res['regime'] == REGIME_SUBSONIC
        assert np.all(res['mach'] < 1.0)
        assert res['throat']['choked'] is False
        assert res['pressure_Pa'][-1] == pytest.approx(Pb, rel=1e-8)
        mdot_choked = choked_mass_flow(P0, T0, GAMMA_GAS, R_GAS, A_THROAT)
        assert res['mass_flow_kg_s'] < mdot_choked
        assert res['mass_conservation_rel_residual'] < 1e-9

    def test_bogulmus_ses_alti_difuzor(self, geometry, crits):
        res = _solve(crits['choked_subsonic_exit_Pa'], geometry)
        assert res['regime'] == REGIME_CHOKED_SUBSONIC
        it = res['throat']['index']
        assert res['mach'][it] == pytest.approx(1.0, abs=1e-9)
        # Iraksak bölüm ses-altı difüzör: boğazdan sonra M düşer.
        assert np.all(res['mach'][it + 1:] < 1.0)
        assert res['mass_flow_kg_s'] == pytest.approx(
            choked_mass_flow(P0, T0, GAMMA_GAS, R_GAS, A_THROAT), rel=1e-12)

    def test_asiri_genislemis(self, geometry, crits):
        Pb = 0.5 * (crits['supersonic_exit_Pa'] + crits['shock_at_exit_Pa'])
        res = _solve(Pb, geometry)
        assert res['regime'] == REGIME_OVEREXPANDED
        assert res['shock'] is None
        assert res['mach'][-1] > 1.0
        assert res['exit']['back_pressure_match'] is False
        assert res['exit']['pressure_Pa'] < Pb

    def test_adapte(self, geometry, crits):
        res = _solve(crits['supersonic_exit_Pa'], geometry)
        assert res['regime'] == REGIME_PERFECT
        assert res['exit']['back_pressure_match'] is True

    def test_eksik_genislemis(self, geometry, crits):
        Pb = 0.5 * crits['supersonic_exit_Pa']
        res = _solve(Pb, geometry)
        assert res['regime'] == REGIME_UNDEREXPANDED
        assert res['exit']['pressure_Pa'] > Pb

    def test_akis_yok(self, geometry):
        res = _solve(P0, geometry)
        assert res['regime'] == REGIME_NO_FLOW
        assert res['mass_flow_kg_s'] == 0.0
        assert np.all(res['mach'] == 0.0)
        assert np.all(res['pressure_Pa'] == P0)

    def test_her_rejim_beyanli(self, geometry, crits):
        """Her rejim çıktısında beyan alanları dolu."""
        for Pb in (0.99 * P0, crits['choked_subsonic_exit_Pa'],
                   0.7 * P0, 0.1 * P0, 0.02 * P0):
            res = _solve(Pb, geometry)
            assert res['regime_description']
            assert 'Anderson' in res['regime_basis']
            assert res['profile_basis']
            assert res['mass_flow_basis']


# ---------------------------------------------------------------------------
# (d) Sınır rejim sürekliliği (Pb süpürmesi)
# ---------------------------------------------------------------------------

class TestRejimSurekliligi:

    PB_REL_STEP = 1e-6  # sınırın iki yanındaki göreli basınç adımı

    def test_bogulma_siniri_sureklilik(self, geometry, crits):
        """Pb = P_sub sınırında şok-rejimi ile ses-altı rejim buluşur:
        kütle debisi ve M(x) profili süreksizlik göstermez."""
        P_sub = crits['choked_subsonic_exit_Pa']
        res_shock = _solve(P_sub * (1.0 - self.PB_REL_STEP), geometry)
        res_sub = _solve(P_sub * (1.0 + self.PB_REL_STEP), geometry)
        assert res_shock['regime'] == REGIME_NORMAL_SHOCK
        assert res_sub['regime'] == REGIME_SUBSONIC
        mdot_ref = res_shock['mass_flow_kg_s']
        assert abs(res_shock['mass_flow_kg_s']
                   - res_sub['mass_flow_kg_s']) / mdot_ref < 1e-3
        assert np.max(np.abs(res_shock['mach'] - res_sub['mach'])) < 0.02
        # Şok boğaza yapışır (zayıf şok limiti).
        assert (res_shock['shock']['x_m']
                - res_shock['throat']['x_m']) < 0.05
        assert res_shock['shock']['mach_upstream'] < 1.1

    def test_sok_cikista_siniri_sureklilik(self, geometry, crits):
        """Pb = P_shock_exit sınırında şok çıkış düzlemine yürür; şokun
        YUKARISINDAKİ profil aşırı genleşmiş tam ses-üstü çözümle örtüşür."""
        P_shx = crits['shock_at_exit_Pa']
        res_shock = _solve(P_shx * (1.0 + self.PB_REL_STEP), geometry)
        res_over = _solve(P_shx * (1.0 - self.PB_REL_STEP), geometry)
        assert res_shock['regime'] == REGIME_NORMAL_SHOCK
        assert res_over['regime'] == REGIME_OVEREXPANDED
        x = res_shock['x_m']
        x_shock = res_shock['shock']['x_m']
        # Şok çıkışın dibinde:
        assert (x[-1] - x_shock) < 0.05
        assert res_shock['shock']['mach_upstream'] == pytest.approx(
            crits['mach_exit_supersonic'], abs=1e-3)
        # Şok yukarısı istasyonlarda iki çözüm birebir aynı dal:
        upstream = x <= x_shock
        assert np.max(np.abs(res_shock['mach'][upstream]
                             - res_over['mach'][upstream])) < 1e-9
        # Kütle debisi iki yanda da boğulmuş ve eşit:
        assert res_shock['mass_flow_kg_s'] == pytest.approx(
            res_over['mass_flow_kg_s'], rel=1e-12)

    def test_kutle_debisi_supurmede_surekli_ve_monoton(self, geometry,
                                                       crits):
        """Ses-altı bantta Pb arttıkça mdot sürekli azalır; boğulma
        altındaki tüm Pb'lerde sabittir (bekçi: süreksiz sıçrama yok)."""
        P_sub = crits['choked_subsonic_exit_Pa']
        mdot_choked = choked_mass_flow(P0, T0, GAMMA_GAS, R_GAS, A_THROAT)
        # Boğulmuş bant: farklı rejimlerden örnekler — hepsi aynı mdot.
        for Pb in (0.05 * P0, 0.3 * P0, 0.6 * P0, 0.9 * P_sub, P_sub):
            res = _solve(Pb, geometry)
            assert res['mass_flow_kg_s'] == pytest.approx(mdot_choked,
                                                          rel=1e-12)
        # Ses-altı bant: sürekli ve monoton azalan.
        band = np.linspace(P_sub, 0.9999 * P0, 200)
        mdots = np.array([_solve(Pb, geometry)['mass_flow_kg_s']
                          for Pb in band])
        assert mdots[0] == pytest.approx(mdot_choked, rel=1e-9)
        assert np.all(np.diff(mdots) < 1e-12)  # monoton azalan
        assert np.max(np.abs(np.diff(mdots))) < 0.1 * mdot_choked

    def test_sok_konumu_monoton_cikisa_yurur(self, geometry, crits):
        """Şok bandında Pb azaldıkça şok konumu monoton olarak çıkışa
        doğru ilerler (Anderson Böl. 5.4 niteliksel davranışı)."""
        P_sub = crits['choked_subsonic_exit_Pa']
        P_shx = crits['shock_at_exit_Pa']
        band = np.linspace(0.999 * P_sub, 1.001 * P_shx, 30)
        x_shocks = []
        for Pb in band:
            res = _solve(Pb, geometry)
            assert res['regime'] == REGIME_NORMAL_SHOCK
            x_shocks.append(res['shock']['x_m'])
        x_shocks = np.array(x_shocks)
        assert np.all(np.diff(x_shocks) > 0.0)


# ---------------------------------------------------------------------------
# Ayrılma kriterleri
# ---------------------------------------------------------------------------

class TestAyrilmaKriterleri:

    # Yüksek genişlemeli lüle: eps_e = 16, deniz seviyesinde belirgin aşırı
    # genleşme. P0 = 30 bar, NPR ≈ 29.6 → tam-akan P_exit/Pa ≈ 0.20, üç
    # kriterin eşiklerinin (Summerfield 0.40, Kalt-Badal ≈ 0.34, Schmucker
    # çıkışta ≈ 0.33) hepsinin altında — üç kriter de tetiklenmeli.
    # (P0 = 50 bar seçilseydi P_exit/Pa ≈ 0.34 olur, yalnız Summerfield
    # tetiklenirdi: NPR arttıkça tam-akan P_exit/Pa doğrusal büyür, eşikler
    # çok daha yavaş değişir.)
    P0_SEP = 30e5      # Pa
    PA_SL = 101325.0   # Pa
    SEP_GAMMA = 1.2

    @staticmethod
    def _high_eps_profile(n=121):
        x = np.linspace(0.0, 1.0, n)
        area = A_THROAT * (1.0 + 15.0 * ((x - 0.3) / 0.7) ** 2)
        return x, area

    def test_asiri_genislemis_ayrilir(self):
        x, area = self._high_eps_profile()
        res = assess_separation(self.P0_SEP, self.PA_SL, self.SEP_GAMMA,
                                x=x, area=area)
        assert res['separated'] is True
        assert set(res['separated_criteria']) == {'summerfield', 'schmucker',
                                                  'kalt_badal'}
        it = int(np.argmin(area))
        for name, crit in res['criteria'].items():
            assert crit['separated'] is True, name
            assert x[it] <= crit['x_sep_m'] < x[-1], name
            assert crit['mach_sep'] > 1.0, name
        # Kontrol eden kriter en yukarıda ayrılma öngören olmalı.
        eps_min = min(c['area_ratio_sep'] for c in res['criteria'].values())
        assert res['area_ratio_sep'] == eps_min

    def test_summerfield_esik_gidis_donusu(self):
        """Ayrılma istasyonundaki duvar basıncı eşiği birebir sağlar."""
        x, area = self._high_eps_profile()
        res = assess_separation(self.P0_SEP, self.PA_SL, self.SEP_GAMMA,
                                x=x, area=area)
        crit = res['criteria']['summerfield']
        p_wall = (self.P0_SEP
                  * isentropic_ratios(crit['mach_sep'], self.SEP_GAMMA)[1])
        assert p_wall / self.PA_SL == pytest.approx(0.40, rel=1e-9)

    def test_schmucker_esik_ortuk_cozum_tutarli(self):
        x, area = self._high_eps_profile()
        res = assess_separation(self.P0_SEP, self.PA_SL, self.SEP_GAMMA,
                                x=x, area=area)
        crit = res['criteria']['schmucker']
        p_wall = (self.P0_SEP
                  * isentropic_ratios(crit['mach_sep'], self.SEP_GAMMA)[1])
        assert p_wall / self.PA_SL == pytest.approx(
            schmucker_pressure_ratio(crit['mach_sep']), rel=1e-9)

    def test_adapte_lule_ayrilmaz(self):
        """Ortam basıncı tam-akan çıkış basıncına eşitse ayrılma yok."""
        x, area = self._high_eps_profile()
        eps_e = float(area[-1] / area.min())
        mach_exit = mach_from_area_ratio(eps_e, self.SEP_GAMMA)
        p_exit = (self.P0_SEP
                  * isentropic_ratios(mach_exit, self.SEP_GAMMA)[1])
        res = assess_separation(self.P0_SEP, p_exit, self.SEP_GAMMA,
                                x=x, area=area)
        assert res['separated'] is False
        assert res['controlling_criterion'] is None

    def test_vakumda_tanimsiz(self):
        x, area = self._high_eps_profile()
        res = assess_separation(self.P0_SEP, 0.0, self.SEP_GAMMA,
                                x=x, area=area)
        assert res['separated'] is False
        assert 'not_applicable_reason' in res

    def test_schmucker_analitik_esik_degerleri(self):
        """(1.88·2−1)^(−0.64) ≈ 0.522178; (1.88·3−1)^(−0.64) ≈ 0.374480
        (data/validation/nozzle_separation_criteria.json türetilmiş
        değerleriyle aynı — ayrıca JSON'a karşı toplu bekçi testi var)."""
        assert schmucker_pressure_ratio(2.0) == pytest.approx(0.522178,
                                                              abs=1e-5)
        assert schmucker_pressure_ratio(3.0) == pytest.approx(0.374480,
                                                              abs=1e-5)

    def test_kalt_badal_analitik_esik_degeri(self):
        """(2/3)·30^(−1/5) ≈ 0.337664 (doğrulama JSON'unun türetilmiş
        değeri); NPR arttıkça eşik düşer."""
        assert kalt_badal_pressure_ratio(30.0) == pytest.approx(0.337664,
                                                                abs=1e-5)
        assert (kalt_badal_pressure_ratio(500.0)
                < kalt_badal_pressure_ratio(50.0))

    def test_summerfield_bant_disi_reddedilir(self):
        with pytest.raises(ValueError):
            summerfield_pressure_ratio(0.05)
        assert summerfield_pressure_ratio(0.35) == pytest.approx(0.35)

    def test_gecerlilik_ve_basis_beyanlari(self):
        x, area = self._high_eps_profile()
        res = assess_separation(self.P0_SEP, self.PA_SL, self.SEP_GAMMA,
                                x=x, area=area)
        for crit in res['criteria'].values():
            assert crit['validity']
            assert crit['_basis']
        assert res['_basis']
        assert res['full_flow_exit']['_basis']

    def test_profilsiz_alan_oraniyla_calisir(self):
        """Yalnız çıkış alan oranı verilirse konum alan oranı cinsinden."""
        res = assess_separation(self.P0_SEP, self.PA_SL, self.SEP_GAMMA,
                                area_ratio_exit=16.0)
        assert res['separated'] is True
        assert res['x_sep_m'] is None
        assert res['area_ratio_sep'] > 1.0


# ---------------------------------------------------------------------------
# NOT_MODELLED beyanları ve girdi doğrulama
# ---------------------------------------------------------------------------

class TestBeyanlar:

    def test_quasi1d_not_modelled_beyani(self, geometry):
        res = _solve(0.5 * P0, geometry)
        for key in ('wall_friction', 'heat_loss', 'two_dimensional_effects',
                    'real_gas'):
            assert key in res['not_modelled']
            assert res['not_modelled'][key]  # açıklama boş değil
        assert res['not_modelled'] == QUASI1D_NOT_MODELLED
        assert 'quasi_one_dimensional' in res['assumptions']
        assert res['inputs']['P0_Pa'] == P0
        assert res['critical_pressures']['_basis']
        assert res['exit']['_basis']

    def test_ayrilma_not_modelled_beyani(self):
        res = assess_separation(50e5, 101325.0, 1.2, area_ratio_exit=16.0)
        for key in ('side_loads', 'boundary_layer_state',
                    'fss_rss_distinction'):
            assert key in res['not_modelled']
        assert res['not_modelled'] == SEPARATION_NOT_MODELLED


class TestGirdiDogrulama:

    def test_bogazsiz_profil_reddedilir(self):
        x = np.linspace(0.0, 1.0, 21)
        area = A_THROAT * (2.0 - x)  # salt yakınsak
        with pytest.raises(ValueError):
            solve_nozzle(x, area, P0, T0, GAMMA_GAS, R_GAS, 1e5)

    def test_cift_bogaz_reddedilir(self):
        x = np.linspace(0.0, 1.0, 41)
        area = A_THROAT * (1.5 + np.cos(4.0 * np.pi * x))  # iki çukur
        with pytest.raises(ValueError):
            solve_nozzle(x, area, P0, T0, GAMMA_GAS, R_GAS, 1e5)

    def test_negatif_geri_basinc_reddedilir(self, geometry):
        x, area = geometry
        with pytest.raises(ValueError):
            solve_nozzle(x, area, P0, T0, GAMMA_GAS, R_GAS, -1.0)

    def test_gecersiz_gamma_reddedilir(self, geometry):
        x, area = geometry
        with pytest.raises(ValueError):
            solve_nozzle(x, area, P0, T0, 1.0, R_GAS, 1e5)

    def test_azalmayan_x_reddedilir(self):
        x = np.array([0.0, 0.1, 0.1, 0.3, 0.5, 0.7, 1.0])
        area = A_THROAT * np.array([2.0, 1.5, 1.2, 1.0, 1.2, 1.5, 2.0])
        with pytest.raises(ValueError):
            solve_nozzle(x, area, P0, T0, GAMMA_GAS, R_GAS, 1e5)


# ---------------------------------------------------------------------------
# Doğrulama JSON vakaları (data/validation) — künyeli kabul testleri
# ---------------------------------------------------------------------------

class TestDogrulamaVakalariJSON:
    """data/validation altındaki künyeli vakalar birebir sağlanmalı.

    Vakalar analitik türetilmiştir (tags: analytic_derived /
    DERIVED_BY_US_FROM_PUBLISHED_FORMULAS); toleranslar vaka dosyalarının
    kendi ``tolerance_pct`` alanından okunur.
    """

    @pytest.fixture(scope='class')
    def iso_case(self):
        return _load_case('nozzle_isentropic_area_mach.json')

    @pytest.fixture(scope='class')
    def shock_case(self):
        return _load_case('nozzle_normal_shock_divergent.json')

    @pytest.fixture(scope='class')
    def sep_case(self):
        return _load_case('nozzle_separation_criteria.json')

    def test_izantropik_alan_mach_vakasi(self, iso_case):
        """İki alan oranında dört büyüklük: ses-altı/ses-üstü kök + P/P0.

        Vakanın amacı yanlış kök seçimini yakalamaktır: iki dal ayrı ayrı
        istenen kökü vermeli.
        """
        g = float(iso_case['inputs']['gamma'])
        rtol = float(iso_case['tolerance_pct']) / 100.0
        for eps in iso_case['inputs']['area_ratios']:
            exp = iso_case['expected_outputs'][f'area_ratio_{eps}']
            M_sub = mach_from_area_ratio(eps, g, supersonic=False)
            M_sup = mach_from_area_ratio(eps, g, supersonic=True)
            assert M_sub == pytest.approx(exp['mach_subsonic'], rel=rtol)
            assert M_sup == pytest.approx(exp['mach_supersonic'], rel=rtol)
            assert isentropic_ratios(M_sub, g)[1] == pytest.approx(
                exp['p_over_p0_subsonic'], rel=rtol)
            assert isentropic_ratios(M_sup, g)[1] == pytest.approx(
                exp['p_over_p0_supersonic'], rel=rtol)

    def test_normal_sok_vakasi(self, shock_case):
        """A/A* = 2 istasyonunda duran şokun sıçrama değerleri."""
        g = float(shock_case['inputs']['gamma'])
        eps_shock = float(shock_case['inputs']['shock_station_area_ratio'])
        exp = shock_case['expected_outputs']
        rtol = float(shock_case['tolerance_pct']) / 100.0
        M1 = mach_from_area_ratio(eps_shock, g, supersonic=True)
        assert M1 == pytest.approx(exp['mach_upstream'], rel=rtol)
        M2, p2_p1, _T2_T1, p02_p01 = normal_shock_relations(M1, g)
        assert M2 == pytest.approx(exp['mach_downstream'], rel=rtol)
        assert p2_p1 == pytest.approx(exp['static_pressure_ratio_p2_p1'],
                                      rel=rtol)
        assert p02_p01 == pytest.approx(exp['total_pressure_ratio_p02_p01'],
                                        rel=rtol)

    def test_normal_sok_vakasi_cozucude(self, shock_case):
        """Vakadaki şoku çözücü UÇTAN UCA yeniden bulmalı.

        JSON'un P02/P01 değerinden, şoku A/A* = 2 istasyonuna koyan geri
        basınç Pb kurulur (A_e/A2* = eps_e·P02/P01 → ses-altı çıkış dalı);
        solve_nozzle o Pb ile çağrılır ve raporladığı şok vakayla
        karşılaştırılır — şok konumu çözücüsünün kabul testi.
        """
        g = float(shock_case['inputs']['gamma'])       # 1.4 (hava)
        exp = shock_case['expected_outputs']
        rtol = float(shock_case['tolerance_pct']) / 100.0
        P0_air, T0_air, R_air = 10e5, 300.0, 287.0     # hava, SI
        x = np.linspace(0.0, 1.0, 101)                 # boğaz x=0.5 (ızgarada)
        area = A_THROAT * (1.0 + 12.0 * (x - 0.5) ** 2)   # eps_e = 4.0
        eps_e = float(area[-1] / area.min())
        p02_p01 = float(exp['total_pressure_ratio_p02_p01'])
        M_exit = mach_from_area_ratio(eps_e * p02_p01, g, supersonic=False)
        Pb = P0_air * p02_p01 * isentropic_ratios(M_exit, g)[1]
        res = solve_nozzle(x, area, P0_air, T0_air, g, R_air, Pb)
        assert res['regime'] == REGIME_NORMAL_SHOCK
        shock = res['shock']
        assert shock['area_ratio'] == pytest.approx(
            float(shock_case['inputs']['shock_station_area_ratio']), rel=rtol)
        assert shock['mach_upstream'] == pytest.approx(exp['mach_upstream'],
                                                       rel=rtol)
        assert shock['mach_downstream'] == pytest.approx(
            exp['mach_downstream'], rel=rtol)
        assert shock['p2_p1'] == pytest.approx(
            exp['static_pressure_ratio_p2_p1'], rel=rtol)
        assert shock['p02_p01'] == pytest.approx(
            exp['total_pressure_ratio_p02_p01'], rel=rtol)
        # Analitik konum: 1 + 12·(x−0.5)² = 2 → x = 0.5 + 1/√12
        assert shock['x_m'] == pytest.approx(0.5 + 1.0 / np.sqrt(12.0),
                                             abs=1e-3)
        # Çıkış basıncı kurulan Pb'yi tam karşılamalı (korunum zinciri).
        assert res['pressure_Pa'][-1] == pytest.approx(Pb, rel=1e-8)

    def test_ayrilma_kriterleri_vakasi(self, sep_case):
        """Türetilmiş eşik değerleri modül fonksiyonlarıyla birebir.

        Vaka beyanı: kriterler birbiriyle uyuşmaz; HRMA tek 'doğru'
        ayrılma basıncı göstermez (assess_separation üçünü de raporlar,
        kontrol edeni beyan eder — bkz. TestAyrilmaKriterleri).
        """
        worked = sep_case['expected_outputs']['worked_values']
        assert worked['_status'] == 'DERIVED_BY_US_FROM_PUBLISHED_FORMULAS'
        for key, expected in worked['schmucker'].items():
            mach = float(key.split('_')[1])
            assert schmucker_pressure_ratio(mach) == pytest.approx(
                expected, abs=1e-5), key
        for key, expected in worked['kalt_badal'].items():
            npr = float(key.split('_')[-1])
            assert kalt_badal_pressure_ratio(npr) == pytest.approx(
                expected, abs=1e-5), key
        # Summerfield bandı vakadaki formül aralığıyla aynı.
        summerfield = next(c for c in sep_case['expected_outputs']['criteria']
                           if c['name'] == 'Summerfield')
        lo, hi = SUMMERFIELD_FACTOR_BAND
        assert f'{lo:.2f}' in summerfield['formula']
        assert f'{hi:.2f}' in summerfield['formula']
        # Uyguladığımız üç kriter vakada orijinal künyesiyle var.
        by_name = {c['name']: c
                   for c in sep_case['expected_outputs']['criteria']}
        for name in ('Summerfield', 'Schmucker', 'Kalt ve Badal'):
            assert by_name[name]['source_citation']


# ---------------------------------------------------------------------------
# Motor katmanı tutarlılık bekçileri (docstring'lerde vadedilen eşitlikler)
# ---------------------------------------------------------------------------

class TestMotorKatmaniTutarlilik:

    def test_summerfield_esigi_nozzle_design_ile_ayni(self):
        """separation.py beyanı: SUMMERFIELD_FACTOR_DEFAULT motor
        katmanındaki _SEPARATION_PRESSURE_FRACTION ile aynı tutulur
        (parametre tutarlılığı — değer eşitliği bu bekçiyle korunur)."""
        from hrma.engines.nozzle_design import NozzleDesigner
        assert (SUMMERFIELD_FACTOR_DEFAULT
                == NozzleDesigner._SEPARATION_PRESSURE_FRACTION)

    def test_alan_mach_bagintisi_nozzle_design_ile_ayni(self):
        """quasi1d.py beyanı: alan-Mach ve basınç-Mach bağıntıları
        engines/nozzle_design.py ile aynı (bağımsız kopya — sapma bekçisi)."""
        from hrma.engines.nozzle_design import NozzleDesigner
        for g in (1.2, 1.25, 1.4):
            for M in (1.5, 2.5, 4.0):
                assert area_ratio_from_mach(M, g) == pytest.approx(
                    NozzleDesigner.area_ratio_from_mach(M, g), rel=1e-12)
            for eps in (1.5, 4.0, 16.0):
                # nozzle_design brentq'i xtol=1e-8 ile çözer.
                assert mach_from_area_ratio(eps, g) == pytest.approx(
                    NozzleDesigner.mach_from_area_ratio(eps, g), rel=1e-6)
            for pr in (2.0, 10.0, 80.0):
                assert mach_from_pressure_ratio(pr, g) == pytest.approx(
                    NozzleDesigner.mach_from_pressure_ratio(pr, g), rel=1e-12)

    def test_rejim_adlari_analiz_moduluyle_ayni(self):
        """quasi1d.py beyanı: rejim adları hrma/analysis/nozzle_flow_1d.py
        ile aynı sözlükten (aynı kavram, aynı ad — parametre tutarlılığı)."""
        from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
        cls = NozzleFlow1D
        assert REGIME_UNDEREXPANDED == cls.REGIME_UNDEREXPANDED
        assert REGIME_PERFECT == cls.REGIME_PERFECT
        assert REGIME_OVEREXPANDED == cls.REGIME_OVEREXPANDED
        assert REGIME_NORMAL_SHOCK == cls.REGIME_SHOCK
