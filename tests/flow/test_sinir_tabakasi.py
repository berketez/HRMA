"""
V5 entegral sınır tabakası doğrulama testleri (hrma.flow.boundary_layer).

Doğrulama merdiveni (her basamak analitik ya da korelasyon referansına
karşı ÖLÇÜLÜR; bantlar bu partide ölçülüp kilitlenmiştir):

  (a) Kapanış birim testleri: Thwaites S(λ)/H(λ), Head H1(H) gidiş-dönüşü,
      Ludwieg-Tillmann yönleri, Michel eşiği, Eckert referans sıcaklığının
      SINIRLILIĞI (min-maks içinde kalması), kurtarma sıcaklığının depodaki
      TEK kaynakla (HeatTransferAnalyzer) bit-özdeşliği.
  (b) Laminer düz levha (Blasius): c_f·√Re_x → 0.664, θ → 0.664·√(νx/u),
      δ* → 1.7208·√(νx/u), H → 2.59 ve sürtünme kuvvetinin analitik Blasius
      direncine eşitliği. Thwaites yönteminin bilinen sistematik sapması
      (+%1 mertebesi) BANT olarak yazılıdır — kusur değil, yöntemin künyesi.
  (c) Türbülanslı düz levha: c_f(Re_x) ↔ Schultz-Grunow yerel korelasyonu
      (0.370·(log10 Re_x)^(−2.584)) bandı + şekil faktörünün fiziksel
      bandı + başlangıç koşulundan bağımsızlık.
  (d) Yön testleri: hızlanan akışta θ İNCELİR, yavaşlayan akışta kalınlaşır
      ve ayrılma beyan edilir; genişleyen yarıçapta (Mangler terimi) θ
      sabit yarıçaplıya göre incelir.
  (e) Gerçek lüle: sürtünme kaybının itki yüzdesi Sutton'ın %0.5-2 bandında;
      %1.5 sabitiyle FARK ölçülür ve kilitlenir.
  (f) GERİYE UYUM (kırmızı çizgi) — 16 Ağu 2026 GÖÇÜYLE YENİDEN KURULDU:
      sınır tabakası açık/kapalı farkı TAM olarak beyan edilen 5 yaprakla
      sınırlıdır (MIGRATION_CHANGED_PATHS: kullanılan kesir, kaynağı,
      künyesi, etkin itki ve CF) — istasyon dizilerine, rejime, ham
      itkiye sızma hâlâ imkânsız. Yayımlanan kesir ARTIK ölçülendir;
      hrma.constants'taki %1,5 yalnız ölçüm yayımlanamadığında devreye
      giren YEDEKTİR ve değeri değişmemiştir. Göç öncesi sayılar açık
      ``friction_loss_fraction=0.015`` yolundan bit-aynı üretilir.
      Manifesto: tests/flow/test_surtunme_gocu.py.

Referanslar: Blasius (1908) / Schlichting "Boundary-Layer Theory" 8. baskı
Böl. 6 ve 21; Schultz-Grunow, F., NACA TM 986 (1941) yerel c_f korelasyonu;
Thwaites (1949) DOI 10.1017/s0001925900000184; Head (1958) ARC R&M 3152;
Ludwieg & Tillmann (1950) NACA TM 1285; Eckert (1956) DOI 10.1115/1.4014011;
Sutton & Biblarz 9. baskı Böl. 3.5 (sürtünme kaybı bandı).
"""

import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.nozzle_flow_1d import (
    NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT,
    NozzleFlow1D,
)
from hrma.constants import NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT as CONST_FRICTION
from hrma.flow import boundary_layer as bl
from hrma.flow.boundary_layer import (
    BOUNDARY_LAYER_NOT_MODELLED,
    MARCH_COMPLETED,
    MARCH_LAMINAR_SEPARATION,
    MARCH_STOPPED_BY_CALLER,
    STATE_LAMINAR,
    STATE_TURBULENT,
    TRANSITION_LAMINAR_ONLY,
    TRANSITION_MICHEL,
    TRANSITION_TURBULENT_FROM_START,
    compressible_shape_factor,
    eckert_reference_temperature,
    head_entrainment,
    head_shape_from_h1,
    head_shape_h1,
    ludwieg_tillmann_cf,
    michel_transition_re_theta,
    recovery_factor,
    recovery_temperature,
    solve_boundary_layer,
    thwaites_shape,
    thwaites_shear,
)

# ---------------------------------------------------------------------------
# Analitik referanslar (ders kitabı değerleri — künyeler modül docstring'inde)
# ---------------------------------------------------------------------------
BLASIUS_CF_COEFF = 0.664        # c_f·√Re_x
BLASIUS_THETA_COEFF = 0.664     # θ/√(νx/u)
BLASIUS_DELTA_STAR_COEFF = 1.7208
BLASIUS_SHAPE = 2.59

#: Thwaites yönteminin Blasius'a ölçülen sapma bandı (bu partide ölçüldü:
#: c_f +%0.90, θ +%1.01, δ* +%1.75, H +%0.78). Bant ölçümün ~2 katıdır,
#: yastık değil sınıf payıdır: yöntem değişirse test kırmızıya düşer.
THWAITES_BLASIUS_BAND = 0.02
THWAITES_DELTA_STAR_BAND = 0.03

#: Türbülanslı düz levhada Schultz-Grunow'a ölçülen sapma bandı
#: (ölçüldü: −%2.6 … −%3.9; Ludwieg-Tillmann kapanışının bilinen
#: sistematik yönü). Bant %8.
TURBULENT_CF_BAND = 0.08

# Düz levha sınamasının kurgusal gazı. Bilinçli olarak atmosfer/hava
# sabitleriyle AYNI ADI TAŞIMAZ: burada amaç bir gaz modellemek değil,
# Blasius/Schultz-Grunow bağıntılarının sınandığı sabit-özellikli bir
# ortam kurmaktır (μ zaten test tarafından sabit veriliyor).
PLATE_GAMMA = 1.4
PLATE_GAS_CONSTANT = 287.0


def schultz_grunow_cf(re_x):
    """Yerel türbülanslı düz levha c_f (Schultz-Grunow 1941, NACA TM 986)."""
    return 0.370 * (np.log10(re_x)) ** (-2.584)


def flat_plate_case(length=1.0, n=61, velocity=10.0, nu=1.5e-5,
                    temperature=300.0, pressure=101325.0, radius=1.0):
    """Sabit yarıçaplı, sabit kenar hızlı 'düz levha' vakası kurar.

    Sabit yarıçap ⇒ Mangler terimi tam sıfır ⇒ denklem 2B biçime indirgenir.
    Düşük Mach ⇒ sıkıştırılabilirlik düzeltmesi etkisiz (T* = T_e).
    """
    x = np.linspace(1e-6, length, n)
    ones = np.ones(n)
    mach = velocity / np.sqrt(PLATE_GAMMA * PLATE_GAS_CONSTANT * temperature)
    density = pressure / (PLATE_GAS_CONSTANT * temperature)
    mu = nu * density
    return {
        'x_m': x,
        'radius_m': radius * ones,
        'mach': mach * ones,
        'pressure_Pa': pressure * ones,
        'temperature_K': temperature * ones,
        'gamma': PLATE_GAMMA,
        'gas_constant_J_kgK': PLATE_GAS_CONSTANT,
        'prandtl': 0.72,
        'viscosity_fn': lambda t: mu,
        'wall_temperature_K': temperature,
        '_nu': nu,
        '_mu': mu,
        '_rho': density,
        '_u': velocity,
    }


def run_flat_plate(case, **kwargs):
    keys = ('x_m', 'radius_m', 'mach', 'pressure_Pa', 'temperature_K')
    args = [case[k] for k in keys]
    kw = {k: case[k] for k in ('gamma', 'gas_constant_J_kgK', 'prandtl',
                               'viscosity_fn', 'wall_temperature_K')}
    kw.update(kwargs)
    return solve_boundary_layer(*args, **kw)


# ===========================================================================
# (a) Kapanış birim testleri
# ===========================================================================
class TestKapanislar:
    def test_thwaites_kayma_bilinen_degerler(self):
        # S(0) = 0.09^0.62; Blasius'un tam değeri 0.2205 (yöntem +%1.9)
        assert thwaites_shear(0.0) == pytest.approx(0.09 ** 0.62, rel=1e-12)
        assert thwaites_shear(0.0) == pytest.approx(0.2205, rel=0.03)
        # λ = −0.09 laminer ayrılma: kayma TAM sıfır
        assert thwaites_shear(-0.09) == 0.0

    def test_thwaites_kayma_ayrilma_altinda_reddedilir(self):
        with pytest.raises(ValueError, match='ayrılma'):
            thwaites_shear(-0.2)

    def test_thwaites_kayma_monoton(self):
        lams = np.linspace(-0.09, 0.25, 40)
        vals = [thwaites_shear(l) for l in lams]
        assert np.all(np.diff(vals) > 0)

    def test_thwaites_sekil_dallari_surekli(self):
        """λ = 0'da iki dal aynı değeri vermeli (uydurmanın tutarlılığı)."""
        assert thwaites_shape(0.0) == pytest.approx(2.61, rel=1e-12)
        assert thwaites_shape(-1e-9) == pytest.approx(2.61, rel=1e-3)
        # Blasius H = 2.59
        assert thwaites_shape(0.0) == pytest.approx(BLASIUS_SHAPE, rel=0.02)

    def test_thwaites_sekil_ayrilmada_buyur(self):
        # λ → −0.09 (ayrılma) iken H büyür (klasik ~3.5)
        assert thwaites_shape(-0.09) > 3.0
        assert thwaites_shape(0.2) < thwaites_shape(0.0)

    @pytest.mark.parametrize('shape', [1.15, 1.25, 1.4, 1.55, 1.6, 1.8, 2.4])
    def test_head_h1_gidis_donus(self, shape):
        h1 = head_shape_h1(shape)
        assert head_shape_from_h1(h1) == pytest.approx(shape, rel=1e-10)

    def test_head_h1_monoton_azalan(self):
        shapes = np.linspace(1.15, 2.4, 30)
        h1 = [head_shape_h1(s) for s in shapes]
        assert np.all(np.diff(h1) < 0)

    def test_head_h1_asimptot_disi_reddedilir(self):
        with pytest.raises(ValueError):
            head_shape_from_h1(3.2)
        with pytest.raises(ValueError):
            head_shape_h1(1.0)

    def test_head_entrainment_pozitif_ve_azalan(self):
        h1s = np.linspace(3.4, 12.0, 30)
        vals = [head_entrainment(h) for h in h1s]
        assert np.all(np.array(vals) > 0)
        assert np.all(np.diff(vals) < 0)
        with pytest.raises(ValueError):
            head_entrainment(3.0)

    def test_ludwieg_tillmann_yonleri_ve_deger(self):
        # Bilinen değer: H = 1.4, Re_θ = 1000
        expected = 0.246 * 10 ** (-0.678 * 1.4) * 1000.0 ** (-0.268)
        assert ludwieg_tillmann_cf(1000.0, 1.4) == pytest.approx(expected,
                                                                rel=1e-12)
        # Re_θ büyüdükçe c_f düşer; H büyüdükçe (ayrılmaya doğru) c_f düşer
        assert ludwieg_tillmann_cf(5000.0, 1.4) < ludwieg_tillmann_cf(1000.0, 1.4)
        assert ludwieg_tillmann_cf(1000.0, 2.0) < ludwieg_tillmann_cf(1000.0, 1.4)
        with pytest.raises(ValueError):
            ludwieg_tillmann_cf(0.0, 1.4)

    def test_michel_kriteri_artan(self):
        re_x = np.logspace(5, 7, 20)
        vals = [michel_transition_re_theta(r) for r in re_x]
        assert np.all(np.diff(vals) > 0)
        # Bilinen mertebe: Re_x = 1e6 → Re_θ,tr ≈ 700-800
        assert 600.0 < michel_transition_re_theta(1e6) < 900.0

    def test_kurtarma_faktoru_uslari(self):
        pr = 0.72
        assert recovery_factor(pr, True) == pytest.approx(pr ** (1 / 3), rel=1e-14)
        assert recovery_factor(pr, False) == pytest.approx(pr ** 0.5, rel=1e-14)
        # Pr < 1 için türbülanslı kurtarma laminerden BÜYÜKTÜR
        assert recovery_factor(pr, True) > recovery_factor(pr, False)

    @pytest.mark.parametrize('mach', [0.0, 0.5, 1.0, 2.5, 4.0])
    def test_kurtarma_sicakligi_tek_kaynakla_bit_ozdes(self, mach):
        """T_aw, ısı modülündeki TEK kaynakla cebirsel olarak AYNI olmalı.

        Kopya yasağının bekçisi: iki bağımsız yazım aynı sayıyı vermezse
        (birinde γ ya da Pr üssü değişirse) test kırmızıya düşer.
        """
        hta = HeatTransferAnalyzer()
        gas = hta._get_gas_properties({'gamma': 1.2,
                                       'molecular_weight': 24.0}, 3000.0)
        t0 = 3000.0
        expected = hta._adiabatic_wall_temperature(t0, gas, mach)
        t_edge = t0 / (1.0 + 0.5 * (gas['gamma'] - 1.0) * mach ** 2)
        rec = recovery_factor(gas['prandtl'], turbulent=True)
        got = recovery_temperature(t_edge, mach, gas['gamma'], rec)
        assert got == pytest.approx(expected, rel=1e-12)

    def test_kurtarma_sicakligi_sinirli(self):
        """r_f ≤ 1 iken T_e ≤ T_aw ≤ T_0 (biçimsel ayak adayı #3)."""
        gamma, t0 = 1.2, 3000.0
        for mach in (0.2, 1.0, 3.0, 5.0):
            t_e = t0 / (1.0 + 0.5 * (gamma - 1.0) * mach ** 2)
            t_aw = recovery_temperature(t_e, mach, gamma, 0.9)
            assert t_e <= t_aw <= t0 + 1e-9

    def test_eckert_referans_sicakligi_sinirli(self):
        """T*, {T_e, T_w, T_aw} kümesinin min-maks aralığında kalmalı.

        (Biçimsel ayak adayı #4 — absürt referans durumu imkânsız.)
        """
        rng = np.random.default_rng(20260816)
        for _ in range(200):
            t_e = float(rng.uniform(200.0, 3000.0))
            t_w = float(rng.uniform(200.0, 3000.0))
            t_aw = t_e * float(rng.uniform(1.0, 3.0))
            t_star = eckert_reference_temperature(t_e, t_w, t_aw)
            lo = min(t_e, t_w, t_aw)
            hi = max(t_e, t_w, t_aw)
            assert lo - 1e-9 <= t_star <= hi + 1e-9

    def test_eckert_sikistirilamaz_limit(self):
        """T_w = T_e ve M = 0 (T_aw = T_e) ⇒ T* = T_e (TAM)."""
        assert eckert_reference_temperature(1000.0, 1000.0, 1000.0) == 1000.0

    @pytest.mark.parametrize('shape_i', [1.15, 1.3, 1.4, 2.0, 2.61, 3.4])
    def test_sikistirilabilir_sekil_faktoru_incompressible_limit(self, shape_i):
        """T sabit (M=0, T_w = T_e) ⇒ H = H_i özdeş (profil ailesi tutarlı)."""
        got = compressible_shape_factor(shape_i, 300.0, 300.0, 300.0,
                                        0.0, 1.4, 0.89)
        assert got == pytest.approx(shape_i, rel=1e-4)

    def test_sikistirilabilir_sekil_faktoru_yonleri(self):
        """Soğuk cidar H'yi DÜŞÜRÜR, sıcak/adyabatik yüksek Mach YÜKSELTİR."""
        t_e, gamma, rec, shape_i = 1500.0, 1.2, 0.94, 1.35
        t_aw = recovery_temperature(t_e, 3.0, gamma, rec)
        cold = compressible_shape_factor(shape_i, t_e, 600.0, t_aw, 3.0,
                                         gamma, rec)
        very_cold = compressible_shape_factor(shape_i, t_e, 300.0, t_aw, 3.0,
                                              gamma, rec)
        hot = compressible_shape_factor(shape_i, t_e, t_aw, t_aw, 3.0,
                                        gamma, rec)
        assert very_cold < cold < hot
        # Adyabatik yüksek Mach'ta sıkıştırılabilir H, H_i'nin ÇOK üstünde
        # (ÖLÇÜLDÜ: M=3, T_e=1500 K, adyabatik → H = 3.28 ≈ 2.4·H_i)
        assert hot > 2.0 * shape_i
        # Kuvvetle soğutulmuş cidarda δ* küçülür ve H, H_i'nin ALTINA iner
        # (ÖLÇÜLDÜ: T_w = 300 K → H = 1.12 < 1.35). Bu, soğutulmuş lüle
        # cidarında beklenen fiziktir; H < 1 bile olabilir (δ* < 0).
        assert very_cold < shape_i

    def test_sikistirilabilir_sekil_faktoru_kuadratur_yakinsak(self):
        """Kuadratür merdiveni: 64 nokta, 512 noktaya %0.01'den yakın."""
        import numpy.polynomial.legendre as legendre
        saved = (bl._GL_NODES, bl._GL_WEIGHTS)
        try:
            values = {}
            for npts in (64, 512):
                bl._GL_NODES, bl._GL_WEIGHTS = legendre.leggauss(npts)
                values[npts] = compressible_shape_factor(
                    2.61, 1800.0, 800.0, 3200.0, 2.0, 1.2, 0.94)
            assert values[64] == pytest.approx(values[512], rel=1e-4)
        finally:
            bl._GL_NODES, bl._GL_WEIGHTS = saved


# ===========================================================================
# (b) Laminer düz levha — Blasius
# ===========================================================================
class TestLaminerDuzLevha:
    @pytest.fixture(scope='class')
    def case(self):
        return flat_plate_case()

    @pytest.fixture(scope='class')
    def solution(self, case):
        return run_flat_plate(case, transition=TRANSITION_LAMINAR_ONLY,
                              substeps=8)

    def test_mars_tamamlandi_ve_laminer_kaldi(self, solution):
        assert solution['march']['status'] == MARCH_COMPLETED
        assert set(solution['stations']['state']) == {STATE_LAMINAR}

    def test_cf_blasius(self, case, solution):
        st = solution['stations']
        re_x = case['_rho'] * case['_u'] * st['x_m'] / case['_mu']
        idx = re_x > 1e4
        product = st['cf'][idx] * np.sqrt(re_x[idx])
        # Sabit olmalı (x'ten bağımsız) ve 0.664'e yakın
        assert np.std(product) / np.mean(product) < 1e-3
        assert np.mean(product) == pytest.approx(
            BLASIUS_CF_COEFF, rel=THWAITES_BLASIUS_BAND)

    def test_theta_blasius(self, case, solution):
        st = solution['stations']
        ref = np.sqrt(case['_nu'] * st['x_m'] / case['_u'])
        ratio = st['theta_m'][-1] / ref[-1]
        assert ratio == pytest.approx(BLASIUS_THETA_COEFF,
                                      rel=THWAITES_BLASIUS_BAND)

    def test_delta_star_ve_sekil_faktoru_blasius(self, case, solution):
        st = solution['stations']
        ref = np.sqrt(case['_nu'] * st['x_m'] / case['_u'])
        assert st['delta_star_m'][-1] / ref[-1] == pytest.approx(
            BLASIUS_DELTA_STAR_COEFF, rel=THWAITES_DELTA_STAR_BAND)
        assert st['shape_factor'][-1] == pytest.approx(
            BLASIUS_SHAPE, rel=THWAITES_BLASIUS_BAND)

    def test_surtunme_kuvveti_analitik_blasius_direnci(self, case, solution):
        """∫2πr·τ_w dx = 2πR·0.664·ρu²·√(νL/u) (Blasius toplam direnci).

        Bu, θ = 0 başlangıç tekilliğinin analitik integralini de sınar:
        yanlış ele alınırsa kuvvet %10 mertebesinde sapar.
        """
        length = case['x_m'][-1]
        analytic = (2.0 * np.pi * case['radius_m'][0] * BLASIUS_CF_COEFF
                    * case['_rho'] * case['_u'] ** 2
                    * np.sqrt(case['_nu'] * length / case['_u']))
        assert solution['friction_drag_N'] == pytest.approx(
            analytic, rel=THWAITES_BLASIUS_BAND)

    def test_cozunurluk_merdiveni(self, case):
        """Alt adım 4 → 32: sürtünme kuvveti %0.5'ten az değişir."""
        forces = []
        for substeps in (4, 8, 16, 32):
            res = run_flat_plate(case, transition=TRANSITION_LAMINAR_ONLY,
                                 substeps=substeps)
            forces.append(res['friction_drag_N'])
        spread = (max(forces) - min(forces)) / np.mean(forces)
        assert spread < 5e-3, f'çözünürlük duyarlılığı çok yüksek: {spread}'

    def test_islak_alan_analitik(self, case, solution):
        """Sabit yarıçaplı boruda ıslak alan = 2πR·L (tam)."""
        expected = 2.0 * np.pi * case['radius_m'][0] * (
            case['x_m'][-1] - case['x_m'][0])
        assert solution['wetted_area_m2'] == pytest.approx(expected, rel=1e-6)


# ===========================================================================
# (c) Türbülanslı düz levha
# ===========================================================================
class TestTurbulentDuzLevha:
    @pytest.fixture(scope='class')
    def case(self):
        return flat_plate_case(length=6.0, n=121, velocity=30.0)

    @pytest.fixture(scope='class')
    def solution(self, case):
        return run_flat_plate(case,
                              transition=TRANSITION_TURBULENT_FROM_START,
                              substeps=8)

    def test_mars_turbulent(self, solution):
        assert solution['march']['status'] == MARCH_COMPLETED
        assert set(solution['stations']['state']) == {STATE_TURBULENT}

    def test_cf_schultz_grunow_bandinda(self, case, solution):
        st = solution['stations']
        re_x = case['_rho'] * case['_u'] * st['x_m'] / case['_mu']
        mask = (re_x > 1e6) & (re_x < 1.2e7)
        assert np.count_nonzero(mask) > 10
        rel = st['cf'][mask] / schultz_grunow_cf(re_x[mask]) - 1.0
        assert np.max(np.abs(rel)) < TURBULENT_CF_BAND, (
            f'Schultz-Grunow bandı aşıldı: {np.max(np.abs(rel)):.4f}')
        # Sapma SİSTEMATİK olmalı (Ludwieg-Tillmann bilinen yönü: hafif düşük)
        assert np.all(rel < 0.0)

    def test_sekil_faktoru_fiziksel_bantta(self, solution):
        shape = solution['stations']['shape_factor'][5:]
        assert np.all(shape > 1.25) and np.all(shape < 1.50)
        # Reynolds büyüdükçe H düşer (klasik davranış)
        assert shape[-1] < shape[0]

    def test_theta_buyume_ussu(self, case, solution):
        """Düz levhada θ ~ x^0.8 (1/7 kuvvet yasası mertebesi)."""
        st = solution['stations']
        mask = st['x_m'] > 1.0
        slope = np.polyfit(np.log(st['x_m'][mask]),
                           np.log(st['theta_m'][mask]), 1)[0]
        assert 0.75 < slope < 0.90, f'θ büyüme üssü {slope:.3f}'

    def test_baslangic_kosulundan_bagimsiz(self, case):
        """Farklı θ₀ ile marşlar aynı asimptota oturur (%1 içinde)."""
        base = run_flat_plate(case, transition=TRANSITION_TURBULENT_FROM_START)
        results = [base['stations']['cf'][-1]]
        for re_theta0 in (300.0, 1500.0):
            theta0 = re_theta0 * case['_mu'] / (case['_rho'] * case['_u'])
            res = run_flat_plate(case,
                                 transition=TRANSITION_TURBULENT_FROM_START,
                                 theta_initial_m=theta0)
            results.append(res['stations']['cf'][-1])
        spread = (max(results) - min(results)) / np.mean(results)
        assert spread < 0.01, f'başlangıç koşulu duyarlılığı {spread:.4f}'

    def test_reynolds_colburn_isi_akisi_yonleri(self, case):
        """c_p verilince q_w yayımlanır; soğuk cidarda pozitif ve St ∝ c_f."""
        res = run_flat_plate(case, transition=TRANSITION_TURBULENT_FROM_START,
                             wall_temperature_K=250.0,
                             specific_heat_J_kgK=1005.0)
        st = res['stations']
        assert np.all(st['q_wall_W_m2'][1:] > 0.0)
        stanton = st['h_gas_W_m2K'] / (case['_rho'] * case['_u'] * 1005.0)
        expected = (st['cf'] / 2.0) * 0.72 ** (-2.0 / 3.0)
        assert np.allclose(stanton[1:], expected[1:], rtol=1e-9)

    def test_isi_akisi_cp_verilmezse_yayimlanmaz(self, solution):
        assert np.all(np.isnan(solution['stations']['q_wall_W_m2']))


# ===========================================================================
# (d) Basınç gradyanı ve eksenel simetri yön testleri
# ===========================================================================
class TestGradyanVeEksenelSimetri:
    def _variable_case(self, area_ratio_end, n=81, length=1.0):
        """u_e(x) doğrusal değişen sabit yarıçaplı vaka (izantropik değil;
        yalnız denklemin gradyan terimini yalıtmak için kurulmuş sınama)."""
        case = flat_plate_case(length=length, n=n, velocity=10.0)
        x = case['x_m']
        factor = 1.0 + (area_ratio_end - 1.0) * (x - x[0]) / (x[-1] - x[0])
        case['mach'] = case['mach'] * factor
        return case

    def test_hizlanan_akista_theta_incelir(self):
        """Elverişli (favorable) gradyan θ'yı İNCELTİR — yönsel test."""
        flat = run_flat_plate(flat_plate_case(),
                              transition=TRANSITION_LAMINAR_ONLY)
        accel = run_flat_plate(self._variable_case(3.0),
                               transition=TRANSITION_LAMINAR_ONLY)
        assert accel['stations']['theta_m'][-1] < flat['stations']['theta_m'][-1]
        # λ pozitif olmalı (hızlanma)
        assert accel['march']['status'] == MARCH_COMPLETED

    def test_yavaslayan_akista_ayrilma_beyan_edilir(self):
        """Kuvvetli ters gradyan laminer ayrılmayı TETİKLER ve BEYAN EDİLİR."""
        case = self._variable_case(0.25, n=121)
        res = run_flat_plate(case, transition=TRANSITION_LAMINAR_ONLY)
        assert res['march']['status'] == MARCH_LAMINAR_SEPARATION
        assert res['march']['status_x_m'] is not None
        assert res['march']['completed_fraction'] < 1.0
        # Ayrılmadan sonrası MODELLENMEZ — beyan sözlüğünde yazılı
        assert 'separated_flow' in res['not_modelled']

    def test_genisleyen_yaricap_theta_inceltir(self):
        """Mangler terimi: r büyürken θ, sabit yarıçaplıdan İNCE kalır."""
        base = flat_plate_case(length=1.0, n=81)
        flat = run_flat_plate(base, transition=TRANSITION_TURBULENT_FROM_START)
        cone = dict(base)
        x = base['x_m']
        cone['radius_m'] = base['radius_m'] * (
            1.0 + 2.0 * (x - x[0]) / (x[-1] - x[0]))
        cone_res = run_flat_plate(cone,
                                  transition=TRANSITION_TURBULENT_FROM_START)
        assert (cone_res['stations']['theta_m'][-1]
                < flat['stations']['theta_m'][-1])

    def test_sabit_yaricap_mangler_terimi_etkisiz(self):
        """dr/dx = 0 ⇒ eksenel simetrik denklem 2B biçime İNDİRGENİR.

        Yarıçapı 10× büyütmek θ ve c_f'yi DEĞİŞTİRMEMELİ (yalnız kuvvet
        ve ıslak alan ölçeklenir).
        """
        base = flat_plate_case()
        big = dict(base)
        big['radius_m'] = base['radius_m'] * 10.0
        r1 = run_flat_plate(base, transition=TRANSITION_TURBULENT_FROM_START)
        r2 = run_flat_plate(big, transition=TRANSITION_TURBULENT_FROM_START)
        assert np.allclose(r1['stations']['theta_m'], r2['stations']['theta_m'],
                           rtol=1e-12, equal_nan=True)
        assert r2['friction_drag_N'] == pytest.approx(
            10.0 * r1['friction_drag_N'], rel=1e-9)


# ===========================================================================
# (e) Gerçek lüle vakası
# ===========================================================================
NOZZLE_CASE = dict(chamber_pressure=70e5, chamber_temperature=3500.0,
                   gamma=1.2, molecular_weight=24.0, throat_diameter=0.10,
                   expansion_ratio=25.0, ambient_pressure=0.0)

#: Sutton & Biblarz 9. baskı Böl. 3.5: iyi tasarlanmış lülede sürtünme +
#: sınır tabakası itki kaybı tipik olarak %0.5-2 bandındadır.
SUTTON_FRICTION_BAND = (0.005, 0.02)


class TestGercekLule:
    @pytest.fixture(scope='class')
    def solution(self):
        return NozzleFlow1D(**NOZZLE_CASE).solve()

    def test_kayip_sutton_bandinda(self, solution):
        fraction = solution['losses']['friction_loss_fraction_integral_bl']
        assert fraction is not None
        assert SUTTON_FRICTION_BAND[0] < fraction < SUTTON_FRICTION_BAND[1], (
            f'ölçülen sürtünme kaybı %{100 * fraction:.3f} literatür '
            f'bandının dışında')

    def test_olculen_deger_kilitli(self, solution):
        """Bu vakanın ölçülen değeri (v2.6.27 V5): %1.380.

        Regresyon bekçisi: kapanış/marş değişirse sayı kayar ve bu test
        kırmızıya düşer (bant %3 — sayısal gürültü değil, model kayması
        aranıyor).
        """
        fraction = solution['losses']['friction_loss_fraction_integral_bl']
        assert fraction == pytest.approx(0.013802, rel=0.03)

    def test_sabitle_fark_olculdu_ve_isaretli(self, solution):
        """GÖÇ 16 Ağu 2026 (Berke kararı; manifest: test_surtunme_gocu.py).

        Fark alanının TANIMI güncellendi, sayısı değil: göç öncesi
        ``friction_loss_delta_vs_default`` = ölçüm − YAYIMLANAN varsayılan
        idi ve yayımlanan varsayılan sabit olduğu için bu "ölçüm − 0,015"
        demekti. Göçten sonra yayımlanan varsayılan ölçümün KENDİSİ; eski
        yazım delta'yı özdeş olarak SIFIR yapardı ve alan bilgi taşımayı
        bırakırdı. Tanım artık açıkça sabite bağlanmıştır — yayımlanan
        sayı göç öncesiyle aynıdır.
        """
        losses = solution['losses']
        delta = losses['friction_loss_delta_vs_default']
        assert delta is not None
        # Bu vakada ölçülen sürtünme, %1.5 sabitinin ALTINDA
        assert delta < 0.0
        assert abs(delta) == pytest.approx(
            abs(losses['friction_loss_fraction_integral_bl']
                - losses['friction_loss_fraction_legacy_constant']),
            rel=0.0, abs=0.0)
        # Yayımlanan varsayılan ARTIK ölçümün kendisidir (göçün özü)
        assert losses['friction_loss_fraction'] == \
            losses['friction_loss_fraction_integral_bl']
        assert losses['friction_loss_fraction_legacy_constant'] == CONST_FRICTION

    def test_mars_tamamlandi_ve_beyanli(self, solution):
        march = solution['losses']['boundary_layer']['march']
        assert march['status'] == MARCH_COMPLETED
        assert march['transition_mode'] == TRANSITION_TURBULENT_FROM_START
        assert march['completed_fraction'] == pytest.approx(1.0, rel=1e-9)
        assert march['h1_clamped_steps'] == 0

    def test_bogazda_fiziksel_buyuklukler(self, solution):
        st = solution['losses']['boundary_layer']['stations']
        i_t = solution['throat']['index']
        theta = st['theta_m'][i_t]
        # Boğazda tabaka ince (mm altı) ama sıfır değil
        assert 1e-5 < theta < 5e-4
        # Kayma gerilmesi pozitif ve boğazda tepe yapıyor
        tau = np.array([v for v in st['tau_wall_Pa'] if v is not None])
        assert tau[i_t] == pytest.approx(np.max(tau), rel=1e-9)
        # δ*/r küçük ⇒ ince tabaka kabulü tutarlı (kendi kendini denetler)
        ratios = np.array([v for v in st['delta_star_over_radius']
                           if v is not None])
        assert np.max(np.abs(ratios)) < 0.05

    def test_baslangic_tabakasi_kaybi_dusurur(self):
        """θ₀ büyüdükçe c_f düşer ⇒ AYNI yüzeydeki sürtünme kaybı AZALIR.

        BOUNDARY_LAYER_NOT_MODELLED['upstream_history'] beyanının yönünü
        kilitler: θ₀ = 0 kabulü kaybı ALT SINIRLAMAZ, YUKARIDAN sınırlar.
        (Beyan metnindeki yön yanlış yazılırsa bu bekçi onu yakalar.)
        """
        solver = NozzleFlow1D(**NOZZLE_CASE)
        base = solver.solve(include_boundary_layer=False)
        st = base['stations']
        gas = solver._hta._get_gas_properties(
            {'gamma': NOZZLE_CASE['gamma'],
             'molecular_weight': NOZZLE_CASE['molecular_weight']},
            NOZZLE_CASE['chamber_temperature'])
        args = (np.array(st['x_mm']) / 1000.0,
                np.array(st['radius_mm']) / 1000.0,
                np.array(st['mach']), np.array(st['pressure_Pa']),
                np.array(st['temperature_K']))
        kw = dict(gamma=NOZZLE_CASE['gamma'],
                  gas_constant_J_kgK=gas['gas_constant'],
                  prandtl=gas['prandtl'],
                  viscosity_fn=lambda t: solver._hta._get_gas_properties(
                      {'gamma': NOZZLE_CASE['gamma'],
                       'molecular_weight': NOZZLE_CASE['molecular_weight']},
                      float(t))['gas_viscosity'],
                  wall_temperature_K=800.0)
        drags = [solve_boundary_layer(*args, theta_initial_m=t0,
                                      **kw)['friction_drag_N']
                 for t0 in (0.0, 0.5e-3, 2.0e-3)]
        assert drags[0] > drags[1] > drags[2]
        assert 'yukarıdan sınırlar' in (
            BOUNDARY_LAYER_NOT_MODELLED['upstream_history'])

    def test_sogut_cidar_surtunmeyi_artirir(self):
        """T_w düştükçe ρ* artar ⇒ τ_w ve sürtünme kaybı ARTAR (yön testi)."""
        cold = NozzleFlow1D(**dict(NOZZLE_CASE, wall_temperature=400.0)).solve()
        hot = NozzleFlow1D(**dict(NOZZLE_CASE, wall_temperature=1200.0)).solve()
        assert (cold['losses']['friction_loss_fraction_integral_bl']
                > hot['losses']['friction_loss_fraction_integral_bl'])

    def test_michel_kriteri_lulede_gecis_vermiyor(self):
        """Varsayılanın (turbulent_from_start) ÖLÇÜLMÜŞ gerekçesi.

        Michel doğal geçiş kriteri, kuvvetli hızlanma yüzünden lüle boyunca
        HİÇ tetiklenmez: kriter uygulanırsa tabaka baştan sona laminer kalır
        ve sürtünme kaybı 3 kat düşük çıkar. Roket kamarasında akış zaten
        türbülansiyken bu fiziksel değildir; varsayılan bu yüzden
        turbulent_from_start'tır.
        """
        solver = NozzleFlow1D(**NOZZLE_CASE)
        base = solver.solve(include_boundary_layer=False)
        gas = solver._hta._get_gas_properties(
            {'gamma': NOZZLE_CASE['gamma'],
             'molecular_weight': NOZZLE_CASE['molecular_weight']},
            NOZZLE_CASE['chamber_temperature'])
        st = base['stations']
        args = (np.array(st['x_mm']) / 1000.0,
                np.array(st['radius_mm']) / 1000.0,
                np.array(st['mach']), np.array(st['pressure_Pa']),
                np.array(st['temperature_K']))
        kw = dict(gamma=NOZZLE_CASE['gamma'],
                  gas_constant_J_kgK=gas['gas_constant'],
                  prandtl=gas['prandtl'],
                  viscosity_fn=lambda t: solver._hta._get_gas_properties(
                      {'gamma': NOZZLE_CASE['gamma'],
                       'molecular_weight': NOZZLE_CASE['molecular_weight']},
                      float(t))['gas_viscosity'],
                  wall_temperature_K=800.0)
        michel = solve_boundary_layer(*args, transition=TRANSITION_MICHEL, **kw)
        laminar = solve_boundary_layer(*args, transition=TRANSITION_LAMINAR_ONLY,
                                       **kw)
        turbulent = solve_boundary_layer(
            *args, transition=TRANSITION_TURBULENT_FROM_START, **kw)
        assert michel['march']['transition_x_m'] is None
        assert michel['friction_drag_N'] == pytest.approx(
            laminar['friction_drag_N'], rel=1e-12)
        assert turbulent['friction_drag_N'] > 2.0 * michel['friction_drag_N']

    def test_hizlanma_parametresi_olculuyor(self, solution):
        relam = solution['losses']['boundary_layer']['relaminarization']
        assert relam['threshold_K'] == bl.RELAMINARIZATION_K_THRESHOLD
        assert relam['max_K'] is not None and relam['max_K'] > 0.0
        assert isinstance(relam['exceeded_station_count'], int)
        assert 'MODELLENMEZ' in relam['_basis']

    def test_ayrilmis_rejimde_mars_ayrilmada_durur(self):
        res = NozzleFlow1D(**dict(NOZZLE_CASE,
                                  ambient_pressure=101325.0)).solve()
        assert res['regime']['type'] == NozzleFlow1D.REGIME_SEPARATED
        march = res['losses']['boundary_layer']['march']
        assert march['status'] == MARCH_STOPPED_BY_CALLER
        assert march['status_x_m'] == pytest.approx(
            res['regime']['separation']['station_x_mm'] / 1000.0, rel=1e-9)
        assert 'ayrılma' in march['stop_reason']
        # Ayrılmış rejimde kesir HÂLÂ anlamlıdır (ikisi de ayrılma düzlemine
        # kadar) ve yayımlanır
        assert res['losses']['friction_loss_fraction_integral_bl'] is not None

    def test_sok_rejiminde_kesir_yayimlanmaz_kuvvet_yayimlanir(self):
        res = NozzleFlow1D(chamber_pressure=6e5, chamber_temperature=3000.0,
                           gamma=1.2, molecular_weight=24.0,
                           throat_diameter=0.05, expansion_ratio=25.0,
                           ambient_pressure=101325.0).solve()
        assert res['regime']['type'] == NozzleFlow1D.REGIME_SHOCK
        losses = res['losses']
        assert losses['friction_loss_fraction_integral_bl'] is None
        assert losses['friction_loss_delta_vs_default'] is None
        assert losses['friction_drag_integral_bl_N'] > 0.0
        assert 'shock' in losses['friction_loss_fraction_bl_note'].lower()

    def test_bogulmamis_rejimde_sinir_tabakasi_kosulmaz(self):
        res = NozzleFlow1D(chamber_pressure=1.0e5, chamber_temperature=1200.0,
                           gamma=1.3, molecular_weight=28.0,
                           throat_diameter=0.02, expansion_ratio=25.0,
                           ambient_pressure=99999.0).solve()
        assert res['regime']['type'] == NozzleFlow1D.REGIME_UNCHOKED
        assert res['losses']['boundary_layer'] is None
        assert res['losses']['friction_loss_fraction_integral_bl'] is None


# ===========================================================================
# (f) GERİYE UYUM — kırmızı çizgi bekçileri
# ===========================================================================
def _leaves(obj, path=''):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from _leaves(value, f'{path}.{key}')
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            yield from _leaves(value, f'{path}[{i}]')
    else:
        yield path, obj


NEW_FIELD_PREFIXES = (
    '.losses.boundary_layer',
    '.losses.friction_loss_fraction_integral_bl',
    '.losses.friction_loss_fraction_source',
    '.losses.friction_loss_fraction_basis',
    '.losses.friction_loss_fraction_bl_note',
    '.losses.friction_loss_fraction_legacy_constant',
    '.losses.friction_loss_delta_vs_default',
    '.losses.friction_drag_integral_bl_N',
    '.losses.thrust_effective_integral_bl_N',
    '.losses.thrust_effective_legacy_constant_N',
    '.losses.CF_effective_integral_bl',
    '.losses.CF_effective_legacy_constant',
    '.losses.friction_comparison_basis',
)

#: GÖÇ 16 Ağu 2026 — sınır tabakası AÇIK/KAPALI arasında değişmesine İZİN
#: VERİLEN yapraklar. Göçten önce bu küme BOŞTU (BL yalnız ölçüyordu,
#: yayımlanan sayıyı değiştirmiyordu); artık ölçüm yayımlanan itkiyi
#: BESLİYOR ve fark tam olarak burada görünmeli. Kümenin dışında bir
#: yaprak oynarsa sınır tabakası akış çekirdeğine sızmış demektir.
MIGRATION_CHANGED_PATHS = {
    '.losses.friction_loss_fraction',
    '.losses.friction_loss_fraction_source',
    '.losses.friction_loss_fraction_basis',
    '.losses.thrust_effective_N',
    '.losses.CF_effective',
}

BACKCOMPAT_CASES = [
    dict(NOZZLE_CASE),
    dict(NOZZLE_CASE, ambient_pressure=101325.0),
    dict(chamber_pressure=6e5, chamber_temperature=3000.0, gamma=1.2,
         molecular_weight=24.0, throat_diameter=0.05, expansion_ratio=25.0,
         ambient_pressure=101325.0),
    dict(chamber_pressure=25e5, chamber_temperature=3000.0, gamma=1.2,
         molecular_weight=24.0, throat_diameter=0.035, expansion_ratio=6.0,
         ambient_pressure=50000.0),
]


class TestGeriyeUyum:
    @pytest.mark.parametrize('case', BACKCOMPAT_CASES)
    def test_yayimlanan_sayilar_bit_ozdes(self, case):
        """Sınır tabakası AÇIK/KAPALI: sürtünme kesri DIŞINDA bit-özdeş.

        GÖÇ 16 Ağu 2026 (Berke kararı "doğrusu neyse o olsun"; manifest:
        tests/flow/test_surtunme_gocu.py; politika: docs/mimari/
        f2-yanma-tepkisi-tasarimi.md §8.1 karar 8).

        BEKÇİ GEVŞETİLMEDİ, YENİDEN KURULDU. Göçten önce bu test "BL
        hiçbir yayımlanan sayıyı değiştiremez" diyordu; göçün TAMAMI bu
        cümlenin kasıtlı olarak yıkılmasıdır, dolayısıyla eski hâliyle
        kalsaydı test kararın kendisini yasaklardı. Yeni sözleşme daha
        DARDIR: BL'nin dokunmasına izin verilen yaprak kümesi
        (MIGRATION_CHANGED_PATHS) TAM olarak sayılır — eksiği de fazlası
        da kırmızıdır. Yani istasyon dizilerine, rejime, ham itkiye ya da
        ısı akısına sızma hâlâ imkânsız; üstelik artık "sürtünmenin
        gerçekten yayımlanan itkiyi beslediği" de kilitli.
        """
        with_bl = dict(_leaves(NozzleFlow1D(**case).solve()))
        without = dict(_leaves(
            NozzleFlow1D(**case).solve(include_boundary_layer=False)))
        compared = 0
        degisen = set()
        for path, value in without.items():
            if path.startswith(NEW_FIELD_PREFIXES):
                continue          # V5 alanları zaten YENİ (karşılaştırılmaz)
            assert path in with_bl, f'anahtar KAYBOLDU: {path}'
            compared += 1
            if with_bl[path] != value:
                degisen.add(path)
        assert compared > 500, (
            f'karşılaştırılan yaprak sayısı beklenmedik biçimde düşük '
            f'({compared}) — bekçi kör kalmış olabilir')

        losses_bl = NozzleFlow1D(**case).solve()['losses']
        olcum_yayimlandi = (losses_bl['friction_loss_fraction_source']
                            == 'integral_bl_measured')
        # Yukarıdaki döngü V5 alanlarını atlıyor; beklenti de aynı kuralla
        # süzülür (kaynak/künye alanları zaten "yeni alan" sayılıyor).
        beklenen = ({p for p in MIGRATION_CHANGED_PATHS
                     if not p.startswith(NEW_FIELD_PREFIXES)}
                    if olcum_yayimlandi else set())
        assert degisen == beklenen, (
            f'sınır tabakası açık/kapalı farkı beklenen kümede değil.\n'
            f'  fazladan oynayan: {sorted(degisen - beklenen)}\n'
            f'  oynaması beklenip oynamayan: {sorted(beklenen - degisen)}')
        if olcum_yayimlandi:
            # Yön: BL kapalıyken yedek sabit (%1,5), açıkken ölçüm.
            assert without['.losses.friction_loss_fraction'] == CONST_FRICTION
            assert (with_bl['.losses.friction_loss_fraction']
                    == losses_bl['friction_loss_fraction_integral_bl'])
        extra = set(with_bl) - set(without)
        for path in extra:
            assert path.startswith(NEW_FIELD_PREFIXES), (
                f'sınır tabakası bloğu DIŞINDA yeni anahtar: {path}')

    def test_yedek_sabitin_degeri_degismedi(self):
        """Sabitin DEĞERİ değişmedi; GÖÇEN şey onun ROLÜ (16 Ağu 2026).

        Berke kararı: "doğrusu neyse o olsun" — yayımlanan varsayılan
        artık ölçülen sınır tabakası değeri, 0,015 ise yalnız YEDEK
        (manifest: tests/flow/test_surtunme_gocu.py; politika:
        docs/mimari/f2-yanma-tepkisi-tasarimi.md §8.1 karar 8).
        Sabitin değeri hâlâ kilitli, çünkü sıvı motor teslim-Isp zinciri
        (liquid_rocket_engine eta_f) onu doğrudan okuyor — oradaki göç
        AYRI bir karardır.

        Göç öncesi altın sayılar SİLİNMEDİ: açık ``friction_loss_fraction
        =0.015`` yolundan hâlâ bit-aynı üretiliyorlar (aşağıda).
        """
        assert CONST_FRICTION == 0.015
        eski_yol = NozzleFlow1D(**NOZZLE_CASE,
                                friction_loss_fraction=0.015).solve()
        assert eski_yol['losses']['thrust_effective_N'] == pytest.approx(
            98237.33697442376, rel=1e-12)
        assert eski_yol['performance']['thrust_N'] == pytest.approx(
            101290.31988066863, rel=1e-12)
        # Yeni varsayılan yol: ham itki AYNI (göç yalnız kayıp kesrine
        # dokunur), etkin itki ise ÖLÇÜMDEN.
        yeni = NozzleFlow1D(**NOZZLE_CASE).solve()
        assert yeni['performance']['thrust_N'] == pytest.approx(
            101290.31988066863, rel=1e-12)
        assert yeni['losses']['thrust_effective_N'] == pytest.approx(
            98350.487239, rel=1e-6)
        assert yeni['losses']['thrust_effective_legacy_constant_N'] == \
            pytest.approx(98237.33697442376, rel=1e-12)

    def test_varsayilan_kesir_tek_kaynaktan(self):
        """0.015 tek yerde tanımlı: hrma.constants (kural 11).

        GÖÇ 16 Ağu 2026: kaynak etiketi 'bookkeeping_constant' →
        'integral_bl_measured'. Çözücünün ``friction_loss_fraction``
        özniteliği de BİLEREK ikiye ayrıldı: kullanıcının verdiği değer
        (None = vermedi) ile ölçüm yokken kullanılacak yedek. Tek isim
        korunsaydı "kullanılan kesir bu" sanılırdı.
        """
        assert NOZZLE_FRICTION_LOSS_FRACTION_DEFAULT is CONST_FRICTION
        solver = NozzleFlow1D(**NOZZLE_CASE)
        assert solver.friction_loss_fraction_user is None
        assert solver.friction_loss_fraction_fallback == CONST_FRICTION
        assert not hasattr(solver, 'friction_loss_fraction'), (
            'belirsiz eski öznitelik geri gelmiş — hangi kesrin '
            'kullanıldığı adından anlaşılmıyor')
        losses = solver.solve()['losses']
        assert losses['friction_loss_fraction_source'] == 'integral_bl_measured'
        assert losses['friction_loss_fraction'] != CONST_FRICTION
        assert losses['friction_loss_fraction_legacy_constant'] == CONST_FRICTION
        # Kullanıcı üstünlüğü: yedek de kullanıcının değeri olur
        elle = NozzleFlow1D(**NOZZLE_CASE, friction_loss_fraction=0.011)
        assert elle.friction_loss_fraction_user == 0.011
        assert elle.friction_loss_fraction_fallback == 0.011
        assert elle.solve()['losses']['friction_loss_fraction_source'] == 'user'

    def test_yayimlanan_itki_artik_olcumden(self):
        """thrust_effective_N = λ·(1−f_ölçülen)·mom + basınç — EL HESABI.

        GÖÇ 16 Ağu 2026: bu testin eski adı ..._hala_sabitten idi ve
        (1−0.015) çarpanını kilitliyordu. Kilit KALKMADI, ÖLÇÜME TAŞINDI:
        çarpan artık sınır tabakası marşından gelen kesirdir ve eski
        sabitin ürettiği sayı ayrı alanda yayımlanmaya devam eder.
        """
        res = NozzleFlow1D(**NOZZLE_CASE).solve()
        losses = res['losses']
        f_bl = losses['friction_loss_fraction_integral_bl']
        assert losses['friction_loss_fraction'] == f_bl
        expected = (losses['divergence_factor']
                    * (1.0 - f_bl)
                    * losses['momentum_thrust_N']
                    + losses['pressure_thrust_N'])
        assert losses['thrust_effective_N'] == pytest.approx(expected,
                                                             rel=1e-12)
        # Ölçüm alanı artık yayımlanan itkinin BEYANLI YANKISIDIR
        assert losses['thrust_effective_integral_bl_N'] == pytest.approx(
            losses['thrust_effective_N'], rel=1e-12)
        # Eski sabitin sayısı hâlâ görünür ve FARKLI (göç gerçekten oldu)
        eski = (losses['divergence_factor'] * (1.0 - CONST_FRICTION)
                * losses['momentum_thrust_N'] + losses['pressure_thrust_N'])
        assert losses['thrust_effective_legacy_constant_N'] == pytest.approx(
            eski, rel=1e-12)
        assert losses['thrust_effective_legacy_constant_N'] != pytest.approx(
            losses['thrust_effective_N'], rel=1e-9)

    def test_sinir_tabakasi_itkisi_ayni_formulle(self):
        res = NozzleFlow1D(**NOZZLE_CASE).solve()
        losses = res['losses']
        f_bl = losses['friction_loss_fraction_integral_bl']
        expected = (losses['divergence_factor'] * (1.0 - f_bl)
                    * losses['momentum_thrust_N']
                    + losses['pressure_thrust_N'])
        assert losses['thrust_effective_integral_bl_N'] == pytest.approx(
            expected, rel=1e-12)
        assert losses['CF_effective_integral_bl'] == pytest.approx(
            expected / (res['inputs']['chamber_pressure_Pa']
                        * res['throat']['area_m2']), rel=1e-12)

    def test_kesir_tanimi_kuvvet_bolu_momentum_itkisi(self):
        res = NozzleFlow1D(**NOZZLE_CASE).solve()
        losses = res['losses']
        assert losses['friction_loss_fraction_integral_bl'] == pytest.approx(
            losses['friction_drag_integral_bl_N']
            / losses['momentum_thrust_N'], rel=1e-12)
        assert losses['friction_drag_integral_bl_N'] == pytest.approx(
            losses['boundary_layer']['friction_drag_N'], rel=1e-12)

    def test_json_guvenli_ve_beyanli(self):
        import json
        res = NozzleFlow1D(**NOZZLE_CASE).solve()
        # allow_nan=False: NaN/Inf kalırsa ValueError — geçerli JSON değildir
        json.dumps(res, allow_nan=False)
        losses = res['losses']
        for key in ('friction_comparison_basis',):
            assert isinstance(losses[key], str) and len(losses[key]) > 80
        block = losses['boundary_layer']
        for key in ('friction_drag_basis', 'viscosity_basis'):
            assert isinstance(block[key], str) and len(block[key]) > 20
        for key, text_value in block['not_modelled'].items():
            assert isinstance(text_value, str) and len(text_value) > 20, key
        # Dizilerin hepsi aynı uzunlukta
        stations = block['stations']
        lengths = {k: len(v) for k, v in stations.items()
                   if isinstance(v, list)}
        assert len(set(lengths.values())) == 1, lengths

    def test_viskozite_kaynagi_beyanli(self):
        """μ(T) tek kaynaktan çözüldü mü, yoksa çağıranın sabiti mi?"""
        res = NozzleFlow1D(**NOZZLE_CASE).solve()
        basis = res['losses']['boundary_layer']['viscosity_basis']
        assert 'Bartz' in basis and 'T^0.6' in basis
        fixed = NozzleFlow1D(**dict(NOZZLE_CASE,
                                    motor_data={'gas_viscosity': 8.0e-5}))
        basis_fixed = fixed.solve()['losses']['boundary_layer']['viscosity_basis']
        assert 'SABİT' in basis_fixed


class TestBeyanSozlesmesi:
    def test_not_modelled_anahtarlari(self):
        required = {'separated_flow', 'shock_boundary_layer_interaction',
                    'wall_roughness', 'radiation_and_wall_energy_balance',
                    'viscous_inviscid_coupling', 'transverse_curvature',
                    'relaminarization', 'upstream_history'}
        assert required <= set(BOUNDARY_LAYER_NOT_MODELLED)
        for key, text in BOUNDARY_LAYER_NOT_MODELLED.items():
            assert len(text) > 30, key

    def test_gecersiz_girdiler_reddedilir(self):
        case = flat_plate_case()
        with pytest.raises(ValueError, match='geçiş kipi'):
            run_flat_plate(case, transition='sihirli')
        with pytest.raises(ValueError):
            run_flat_plate(case, substeps=0)
        bad = dict(case)
        bad['x_m'] = case['x_m'][::-1]
        with pytest.raises(ValueError, match='artan'):
            run_flat_plate(bad)
        bad2 = dict(case)
        bad2['radius_m'] = case['radius_m'] * -1.0
        with pytest.raises(ValueError, match='pozitif'):
            run_flat_plate(bad2)

    def test_kapanis_sabitleri_tek_yerde(self):
        """Ampirik katsayılar modül sabiti olarak yayımlanır (kopya yasağı)."""
        for name, value in (('THWAITES_CORRELATION_COEFF', 0.45),
                            ('THWAITES_SHEAR_OFFSET', 0.09),
                            ('THWAITES_SHEAR_EXPONENT', 0.62),
                            ('HEAD_ENTRAINMENT_COEFF', 0.0306),
                            ('LUDWIEG_TILLMANN_COEFF', 0.246),
                            ('ECKERT_WALL_WEIGHT', 0.5),
                            ('ECKERT_RECOVERY_WEIGHT', 0.22),
                            ('MICHEL_COEFF', 1.174),
                            ('RELAMINARIZATION_K_THRESHOLD', 3.0e-6)):
            assert getattr(bl, name) == value, name
