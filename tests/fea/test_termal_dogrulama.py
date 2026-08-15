"""
Eksenel simetrik geçici ısı iletimi çözücüsü doğrulama bekçileri
(V2.7 Aşama A — docs/V2.7_ANALIZ_MODULU.md §4.1 ve §5: doğrulanmamış FEA
yayımlanmaz).

Kapsam:
  (a) Yarı-sonsuz katı, basamak yüzey sıcaklığı — erfc çözümü. Beklenen
      değerler data/validation/thermal_semiinf_step_temperature.json
      dosyasından OKUNUR, tolerans vakanın ``tolerance_pct`` alanından
      gelir; JSON sayıları ayrıca testin içinde erfc formülüyle ÇAPRAZ
      doğrulanır (dosya bozulmasına karşı bekçi).
  (b) Yarı-sonsuz katı, sabit yüzey akısı (Neumann) —
      thermal_semiinf_constant_flux.json, ierfc çözümü.
  (c) Enerji korunumu — iki katman:
      * ayrık bütçe kapanması (residual_rel ~ makine hassasiyeti; işaret/
        montaj hatası bekçisi),
      * DIŞ gerçek: sabit akı vakasında giren enerji q0·A·t ANALİTİK olarak
        bilinir; iç enerji artışı testin KENDİ (çözücüden bağımsız, 1 noktalı
        kuadratur) hacim integraliyle hesaplanır ve %1 içinde kapanır.
  (d) Kararlı-hâl limiti — uzun sürede 1B silindirik kabuk analitik profili
      (iç konveksiyon + dış doğal taşınım; Carslaw & Jaeger / standart ısı
      direnci zinciri).
  (+) Işıma lineerleştirmesi: ince kabuk ışımayla soğuma, sıkı toleranslı
      referans ODE ile karşılaştırma; monotonluk ve ortam altına inmeme.
  (+) Otomatik zaman adımı sürücüsü: yakınsama + dürüst beyan.
  (+) Sıcaklığa bağlı özellikler: Kirchhoff dönüşümü analitiği; fonksiyon
      sabit döndürünce skalerle birebir aynılık; fiziksel olmayan özellik
      üreten fonksiyonun REDDİ.
  (+) Giriş bekçileri ve beyanlar (sahte veri yasağı: NOT_MODELLED listesi,
      sınır koşulu ve lineerleştirme beyanları).

Yarı-sonsuz vakaların eksenel simetrik çözücüyle kurulumu: iç yarıçapı
kalınlığa göre ÇOK büyük (a = 10 m, L = 0,2 m) bir silindir cidarı düzlemsel
yarı-sonsuz katıya yakınsar. Eğrilik düzeltmesi √(a/r) mertebesindedir:
en derin sonda x = 0,02 m için √(10/10,02) − 1 ≈ %0,1 — vaka toleransı %1'in
onda biri. Arka yüz adyabatiktir; yansıma hatası erfc((2L−x)/(2√(αt))) ≈
erfc(4,7) ~ 10⁻¹¹ mertebesinde ihmal edilebilir (t = 400 s'te bile).

Analitik kaynak: H. S. Carslaw & J. C. Jaeger, "Conduction of Heat in
Solids", 2. baskı, 1959, Böl. 2 (vaka dosyalarının kendi künyesi).
"""

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.integrate import solve_ivp
from scipy.special import erfc

from hrma.fea.mesh_axisym import build_wall_mesh
from hrma.fea.thermal_axisym import (
    AdiabaticBC,
    AmbientBC,
    ConvectionBC,
    FixedTemperatureBC,
    HeatFluxBC,
    ThermalMaterial,
    solve_transient,
    solve_transient_auto,
    DEFAULT_DT_TOL,
    DEFAULT_N_STEPS0,
    STEFAN_BOLTZMANN_W_M2K4,
)

VALIDATION_DIR = Path(__file__).resolve().parents[2] / "data" / "validation"

# ---------------------------------------------------------------------------
# Yarı-sonsuz vaka mesh/zaman politikası (tek yerde — parametre tutarlılığı).
# Ölçülen hatalar (kalibrasyon koşusu): erfc sondaları <= %0,19, ierfc
# <= %0,22 — vaka toleransı %1'e ~5 kat pay.
# ---------------------------------------------------------------------------
SEMIINF_A = 10.0       # m — düzlemsel yaklaşım için büyük iç yarıçap (beyan
                       # yukarıda: eğrilik etkisi ~%0,1)
SEMIINF_THICK = 0.2    # m — "yarı-sonsuz" görünüm için yeterli derinlik
SEMIINF_N_RADIAL = 100  # Δx = 2 mm: sondalar (10 ve 20 mm) TAM düğüme düşer
SEMIINF_N_AXIAL = 2    # çözüm z'den bağımsız — eksenel bölüm asgari
SEMIINF_LZ = 0.04      # m — kısa eksenel şerit


def _load_case(name: str) -> dict:
    """Vaka dosyasını okur; kimlik-dosya adı uyumunu sınar."""
    path = VALIDATION_DIR / f"{name}.json"
    assert path.exists(), f"Doğrulama vakası eksik: {path}"
    case = json.loads(path.read_text(encoding="utf-8"))
    assert case["case"] == name, "Vaka kimliği dosya adıyla uyuşmuyor."
    assert case["discipline"] == "thermal"
    return case


def _semiinf_setup(case: dict):
    """Vaka girdilerinden mesh + malzeme + orta istasyon düğüm hattı kurar.

    Malzeme vakadan gelir: k dosyadaki değer, ρ·c_p = k/α (yalnız ÇARPIM
    fiziğe girer; ρ = 1500 kg/m³ keyfî bölüşümdür ve sonucu etkilemez —
    boyutsuz erfc çözümü zaten malzemeden bağımsızdır, vakanın kendi beyanı).
    """
    inp = case["inputs"]
    alpha = inp["thermal_diffusivity_m2_s"]
    k = inp["thermal_conductivity_W_mK"]
    rho = 1500.0
    cp = k / (alpha * rho)
    material = ThermalMaterial(rho=rho, cp=cp, k=k, name="vaka-yari-sonsuz")
    mesh = build_wall_mesh([(0.0, SEMIINF_A), (SEMIINF_LZ, SEMIINF_A)],
                           SEMIINF_THICK, n_axial=SEMIINF_N_AXIAL,
                           n_radial=SEMIINF_N_RADIAL)
    line = mesh.node_index_grid[mesh.n_axial // 2, :]
    return mesh, material, line


def _probe_node(mesh, line, x_m: float) -> int:
    """Derinliği x olan sondanın düğümü; düğüme TAM düşmeli (enterpolasyon
    hatası taşınmasın)."""
    dx = SEMIINF_THICK / SEMIINF_N_RADIAL
    j = int(round(x_m / dx))
    r_node = mesh.nodes[line[j], 1]
    assert abs((r_node - SEMIINF_A) - x_m) < 1e-12, (
        "Sonda düğüme denk gelmiyor — mesh politikası vaka sondalarıyla "
        "uyumsuz hale getirilmiş.")
    return int(line[j])


class TestVakaYariSonsuzBasamak:
    """(a) thermal_semiinf_step_temperature — Dirichlet basamak, erfc."""

    @pytest.fixture(scope="class")
    def vaka(self):
        return _load_case("thermal_semiinf_step_temperature")

    @pytest.fixture(scope="class")
    def cozum(self, vaka):
        inp = vaka["inputs"]
        assert inp["boundary_condition"] == "dirichlet_step_at_x0"
        mesh, material, line = _semiinf_setup(vaka)
        # dt = 0,5 s; t = 100 ve 400 s ızgara noktasına tam düşer.
        times = np.linspace(0.0, 400.0, 801)
        result = solve_transient(
            mesh, material, times,
            inner_bc=FixedTemperatureBC(T=inp["surface_temperature_K"]),
            outer_bc=AdiabaticBC(),
            T_initial=inp["initial_temperature_K"])
        return mesh, line, result

    @staticmethod
    def _anahtar(x_m: float, t_s: float) -> str:
        # Vaka anahtarı biçimi: "x0.010_t100"
        return f"x{x_m:.3f}_t{t_s:g}"

    def test_json_erfc_formulle_tutarli(self, vaka):
        """Dosya bozulması bekçisi: JSON theta değerleri erfc'den yeniden
        türetilir (reference_formulas alanındaki bağıntı)."""
        inp = vaka["inputs"]
        alpha = inp["thermal_diffusivity_m2_s"]
        for p in inp["probe_points"]:
            key = self._anahtar(p["x_m"], p["t_s"])
            theta = float(erfc(p["x_m"] / (2.0 * np.sqrt(alpha * p["t_s"]))))
            assert theta == pytest.approx(
                vaka["expected_outputs"]["theta_dimensionless"][key],
                rel=1e-6)

    def test_sonda_sicakliklari(self, vaka, cozum):
        mesh, line, result = cozum
        inp = vaka["inputs"]
        tol = vaka["tolerance_pct"] / 100.0
        T_i = inp["initial_temperature_K"]
        T_s = inp["surface_temperature_K"]
        for p in inp["probe_points"]:
            key = self._anahtar(p["x_m"], p["t_s"])
            node = _probe_node(mesh, line, p["x_m"])
            it = int(round(p["t_s"] / 0.5))
            assert result.times[it] == pytest.approx(p["t_s"])
            theta_num = (result.T_history[it, node] - T_i) / (T_s - T_i)
            theta_exp = vaka["expected_outputs"]["theta_dimensionless"][key]
            err = abs(theta_num - theta_exp) / theta_exp
            assert err < tol, (
                f"{key}: theta FE={theta_num:.6f}, beklenen={theta_exp:.6f}, "
                f"bağıl hata %{100 * err:.3f} >= %{100 * tol:.1f}")
            T_exp = vaka["expected_outputs"]["temperature_K"][key]
            assert result.T_history[it, node] == pytest.approx(
                T_exp, rel=tol)

    def test_yuzey_akisi(self, vaka, cozum):
        """Yüzey akısı Dirichlet reaksiyonundan (ayrık korunumlu akı).

        Tolerans vakanınkinden gevşek (%2): akı, sıcaklığın türevi olduğu
        için bir mertebe daha zor bir hedeftir ve geri Euler aralık-sonu
        gücü t = 100 anına O(Δt) yanaşır (ölçülen hata ~%0,45).
        """
        mesh, line, result = cozum
        area_in = 2.0 * np.pi * SEMIINF_A * SEMIINF_LZ
        for t_s, q_exp in vaka["expected_outputs"][
                "surface_heat_flux_W_m2"].items():
            t_val = float(t_s.removeprefix("t"))
            it = int(round(t_val / 0.5))
            q_num = result.energy["qdot_inner_W"][it - 1] / area_in
            assert q_num == pytest.approx(q_exp, rel=0.02)

    def test_tepe_cidar_sicakligi_yuzeyde(self, cozum):
        """Isıtılan cidarda tepe sıcaklık dayatılan yüzey değeridir; alan
        hiçbir yerde onu aşamaz (ayrık maksimum ilkesi — topaklanmış kütle
        + geri Euler tercihinin sınandığı yer)."""
        mesh, line, result = cozum
        assert result.peak_wall_T == pytest.approx(800.0, abs=1e-9)
        assert float(result.T_history.max()) <= 800.0 + 1e-9
        assert float(result.T_history.min()) >= 300.0 - 1e-9


class TestVakaYariSonsuzSabitAki:
    """(b) thermal_semiinf_constant_flux — Neumann sabit akı, ierfc."""

    @pytest.fixture(scope="class")
    def vaka(self):
        return _load_case("thermal_semiinf_constant_flux")

    @pytest.fixture(scope="class")
    def cozum(self, vaka):
        inp = vaka["inputs"]
        assert inp["boundary_condition"] == "neumann_constant_flux_at_x0"
        mesh, material, line = _semiinf_setup(vaka)
        times = np.linspace(0.0, 100.0, 401)   # dt = 0,25 s
        result = solve_transient(
            mesh, material, times,
            inner_bc=HeatFluxBC(q=inp["surface_heat_flux_W_m2"]),
            outer_bc=AdiabaticBC(),
            T_initial=inp["initial_temperature_K"])
        return mesh, line, result

    def test_json_ierfc_formulle_tutarli(self, vaka):
        """JSON değerleri ierfc bağıntısından yeniden türetilir."""
        inp = vaka["inputs"]
        alpha = inp["thermal_diffusivity_m2_s"]
        k = inp["thermal_conductivity_W_mK"]
        q0 = inp["surface_heat_flux_W_m2"]
        for p in inp["probe_points"]:
            key = f"x{p['x_m']:.3f}_t{p['t_s']:g}"
            s = np.sqrt(alpha * p["t_s"])
            eta = p["x_m"] / (2.0 * s)
            ierfc = np.exp(-eta ** 2) / np.sqrt(np.pi) - eta * erfc(eta)
            dT = 2.0 * q0 * s / k * ierfc
            assert dT == pytest.approx(
                vaka["expected_outputs"]["temperature_rise_K"][key], rel=1e-6)

    def test_sonda_sicakliklari(self, vaka, cozum):
        mesh, line, result = cozum
        inp = vaka["inputs"]
        tol = vaka["tolerance_pct"] / 100.0
        for p in inp["probe_points"]:
            key = f"x{p['x_m']:.3f}_t{p['t_s']:g}"
            node = _probe_node(mesh, line, p["x_m"])
            T_exp = vaka["expected_outputs"]["temperature_K"][key]
            T_num = result.T_final[node]
            err = abs(T_num - T_exp) / T_exp
            assert err < tol, (
                f"{key}: FE={T_num:.3f} K, beklenen={T_exp:.3f} K, "
                f"bağıl hata %{100 * err:.3f} >= %{100 * tol:.1f}")

    def test_enerji_butcesi_dis_gercekle_kapanir(self, vaka, cozum):
        """(c) enerji korunumu — DIŞ gerçek + bağımsız yeniden hesap.

        Giren ısı ANALİTİK: Q = q0 · (2π a L_z) · t (sabit akı, kesin).
        İç enerji artışı testin KENDİ 1 noktalı kuadraturuyla (çözücünün
        kütle matrisinden bağımsız): ΔU = Σ_e ρ c_p · 2π r_merkez · Alan_e ·
        ΔT_ortalama. Dış yüzey adyabatik → Q_giren = ΔU, %1 içinde.
        """
        mesh, line, result = cozum
        inp = vaka["inputs"]
        q0 = inp["surface_heat_flux_W_m2"]
        Q_analitik = q0 * (2.0 * np.pi * SEMIINF_A * SEMIINF_LZ) * 100.0

        # Çözücünün raporladığı giren ısı analitiğe oturmalı (tutarlı yüzey
        # yükünün kenar toplamı silindirde tam alandır — makine hassasiyeti).
        assert result.energy["Q_inner_J"] == pytest.approx(
            Q_analitik, rel=1e-9)
        assert result.energy["Q_outer_J"] == 0.0   # adyabatik dış yüzey

        # Bağımsız ΔU: 1 noktalı kuadratur (shoelace alan + merkez yarıçap).
        rho_cp = 1500.0 * (inp["thermal_conductivity_W_mK"]
                           / (inp["thermal_diffusivity_m2_s"] * 1500.0))
        P = mesh.nodes[mesh.elems]                      # (M, 4, 2)
        z_p, r_p = P[:, :, 0], P[:, :, 1]
        area = 0.5 * np.abs(np.sum(
            z_p * np.roll(r_p, -1, axis=1)
            - np.roll(z_p, -1, axis=1) * r_p, axis=1))
        r_cent = r_p.mean(axis=1)
        dT_elem = (result.T_final
                   - inp["initial_temperature_K"])[mesh.elems].mean(axis=1)
        dU_bagimsiz = float(np.sum(
            rho_cp * 2.0 * np.pi * r_cent * area * dT_elem))
        assert abs(dU_bagimsiz - Q_analitik) / Q_analitik < 0.01

        # Ayrık bütçe kapanması: montaj/işaret hatası bekçisi.
        assert result.energy["residual_rel"] < 1e-8

    def test_tepe_gecmisi_monoton_ve_sonda(self, cozum):
        """Sabit ısıtmada tepe cidar sıcaklığı geçmişi kesin artan; tepe
        değeri son anda ve iç yüzeydedir."""
        mesh, line, result = cozum
        assert np.all(np.diff(result.peak_wall_T_history) > 0.0)
        assert result.peak_time_s == pytest.approx(100.0)
        assert result.peak_node in set(mesh.inner_nodes.tolist())
        assert result.peak_wall_T == pytest.approx(
            float(result.T_history.max()))


class TestKararliHalSilindirikKabuk:
    """(d) Uzun süre limiti — 1B silindirik kabuk analitik profili.

    İç konveksiyon (h_i, T_g) + dış doğal taşınım (h_o, T_ort); ısı direnci
    zinciri: R' = 1/(2πa h_i) + ln(b/a)/(2πk) + 1/(2πb h_o),
    T(r) = T_g − q'/(2πa h_i) − (q'/2πk)·ln(r/a). Malzemeye küçük ısı
    sığası verilir ki alan test süresi içinde kararlı hâle otursun (kararlı
    hâl ρc_p'den bağımsızdır — yalnız yakınsama hızı değişir).
    """

    A = 0.05
    T_W = 0.025
    B = A + T_W
    L = 0.1
    K_W = 15.0
    H_I, T_GAS = 2000.0, 3000.0
    H_O, T_AMB = 15.0, 300.0

    @pytest.fixture(scope="class")
    def cozum(self):
        material = ThermalMaterial(rho=1.0, cp=1.0, k=self.K_W)
        mesh = build_wall_mesh([(0.0, self.A), (self.L, self.A)], self.T_W,
                               n_axial=4, n_radial=8)
        result = solve_transient(
            mesh, material, np.linspace(0.0, 1.0, 51),
            inner_bc=ConvectionBC(h=self.H_I, T_inf=self.T_GAS),
            outer_bc=AmbientBC(h=self.H_O, T_ambient=self.T_AMB),
            T_initial=self.T_AMB)
        return mesh, result

    def _analitik_profil(self, r):
        Rp = (1.0 / (2.0 * np.pi * self.A * self.H_I)
              + np.log(self.B / self.A) / (2.0 * np.pi * self.K_W)
              + 1.0 / (2.0 * np.pi * self.B * self.H_O))
        qp = (self.T_GAS - self.T_AMB) / Rp
        T_si = self.T_GAS - qp / (2.0 * np.pi * self.A * self.H_I)
        return T_si - qp * np.log(r / self.A) / (2.0 * np.pi * self.K_W), qp

    def test_kararli_hale_oturdu(self, cozum):
        _, result = cozum
        son_degisim = float(np.max(np.abs(result.T_history[-1]
                                          - result.T_history[-2])))
        assert son_degisim < 1e-6, (
            f"Alan kararlı hâle oturmamış (son adım değişimi {son_degisim})")

    def test_radyal_profil_analitikle(self, cozum):
        mesh, result = cozum
        line = mesh.node_index_grid[mesh.n_axial // 2, :]
        r = mesh.nodes[line, 1]
        T_ana, _ = self._analitik_profil(r)
        err = np.max(np.abs(result.T_final[line] - T_ana) / T_ana)
        assert err < 0.005, (
            f"Kararlı hâl profili bağıl hata %{100 * err:.4f} >= %0,5")

    def test_enerji_akisi_dengede(self, cozum):
        """Kararlı hâlde giren güç = çıkan güç = analitik q'·L."""
        _, result = cozum
        _, qp = self._analitik_profil(np.array([self.A]))
        qdot_in = result.energy["qdot_inner_W"][-1]
        qdot_out = result.energy["qdot_outer_W"][-1]
        assert qdot_in == pytest.approx(qp * self.L, rel=0.005)
        assert qdot_out == pytest.approx(-qp * self.L, rel=0.005)
        # İşaret fiziği: ısıtma boyunca iç yüzeyden girer (+), dıştan çıkar.
        assert result.energy["Q_inner_J"] > 0.0
        assert result.energy["Q_outer_J"] < 0.0

    def test_z_fonksiyonu_h_skalerle_ayni(self, cozum):
        """h(z) fonksiyon yolu: sabit döndüren fonksiyon, skaler kurulumla
        makine hassasiyetinde aynı sonucu vermeli."""
        mesh, result = cozum
        material = ThermalMaterial(rho=1.0, cp=1.0, k=self.K_W)
        result_fn = solve_transient(
            mesh, material, np.linspace(0.0, 1.0, 51),
            inner_bc=ConvectionBC(h=lambda z: np.full_like(z, self.H_I),
                                  T_inf=self.T_GAS),
            outer_bc=AmbientBC(h=self.H_O, T_ambient=self.T_AMB),
            T_initial=self.T_AMB)
        np.testing.assert_allclose(result_fn.T_final, result.T_final,
                                   rtol=1e-12)


class TestIsimaLineerlestirme:
    """Lineerleştirilmiş ışıma — nicel doğrulama + fizik bekçileri.

    İnce, yüksek iletimli kabuk (Biot ≪ 1 → izotermal) yalnız dış yüzey
    ışımasıyla soğur; referans, topaklanmış sığa ODE'sinin sıkı toleranslı
    (rtol=1e-10) sayısal çözümüdür:
        C·dT/dt = −εσ·A_dış·(T⁴ − T_ort⁴),  C = ρ c_p V.
    Lineerleştirme + otomatik adım seçimi bu eğriyi %1 içinde vermelidir.
    """

    A_R, T_R, L_R = 0.1, 0.002, 0.05
    B_R = A_R + T_R
    EPS = 0.9
    T0, T_AMB = 1000.0, 300.0

    @pytest.fixture(scope="class")
    def cozum(self):
        material = ThermalMaterial(rho=1000.0, cp=1.0e3, k=200.0)
        mesh = build_wall_mesh([(0.0, self.A_R), (self.L_R, self.A_R)],
                               self.T_R, n_axial=2, n_radial=3)
        result = solve_transient_auto(
            mesh, material, 20.0,
            inner_bc=AdiabaticBC(),
            outer_bc=AmbientBC(h=0.0, T_ambient=self.T_AMB,
                               emissivity=self.EPS),
            T_initial=self.T0)
        return result

    def test_ode_referansiyla(self, cozum):
        result = cozum
        V = np.pi * (self.B_R ** 2 - self.A_R ** 2) * self.L_R
        A_rad = 2.0 * np.pi * self.B_R * self.L_R
        C = 1000.0 * 1.0e3 * V

        def ode(t, y):
            return [-self.EPS * STEFAN_BOLTZMANN_W_M2K4 * A_rad
                    * (y[0] ** 4 - self.T_AMB ** 4) / C]

        ref = solve_ivp(ode, [0.0, 20.0], [self.T0], rtol=1e-10, atol=1e-8)
        T_ref = float(ref.y[0, -1])
        T_fem = float(result.T_final.mean())
        assert abs(T_fem - T_ref) / T_ref < 0.01, (
            f"Işıma soğuması ODE referansından sapıyor: FEM={T_fem:.2f} K, "
            f"ODE={T_ref:.2f} K")

    def test_fizik_bekcileri(self, cozum):
        result = cozum
        # Soğuma monoton; alan hiçbir an ortam sıcaklığının altına inmez.
        assert np.all(np.diff(result.peak_wall_T_history) < 0.0)
        assert float(result.T_history.min()) >= self.T_AMB - 1e-9
        # Işıma soğutması: iç adyabatik (0), dıştan ısı ÇIKAR (negatif).
        assert result.energy["Q_inner_J"] == 0.0
        assert result.energy["Q_outer_J"] < 0.0
        assert result.energy["residual_rel"] < 1e-8

    def test_lineerlestirme_beyani(self, cozum):
        """Sahte veri yasağı: lineerleştirme hatası sonuçta BEYAN edilmeli."""
        result = cozum
        assert "isima_lineerlestirme_hatasi" in result.meta
        assert "önceki adım" in result.meta["isima_lineerlestirme_hatasi"]
        assert "LİNEERLEŞTİRİLMİŞ" in (
            result.meta["sinir_kosullari"]["dis_yuzey"])


class TestZamanAdimiOtomatik:
    """Otomatik zaman adımı sürücüsü — 'kullanıcı ayar görmez' iddiasının
    dürüst karşılığı: yarılama, yakınsama denetimi ve beyan."""

    @pytest.fixture(scope="class")
    def kurulum(self):
        vaka = _load_case("thermal_semiinf_constant_flux")
        mesh, material, line = _semiinf_setup(vaka)
        return vaka, mesh, material, line

    def test_yakinsar_ve_beyan_eder(self, kurulum):
        vaka, mesh, material, line = kurulum
        inp = vaka["inputs"]
        result = solve_transient_auto(
            mesh, material, 100.0,
            inner_bc=HeatFluxBC(q=inp["surface_heat_flux_W_m2"]),
            outer_bc=AdiabaticBC(),
            T_initial=inp["initial_temperature_K"])
        za = result.meta["zaman_adimi"]
        assert za["converged"] is True
        assert za["rel_change"] is not None and za["rel_change"] < za["tol"]
        assert za["tol"] == DEFAULT_DT_TOL
        # En az bir yarılama yapılmış ve adım sayısı 2^h ile tutarlı olmalı.
        assert za["halvings"] >= 1
        assert za["n_steps"] == DEFAULT_N_STEPS0 * 2 ** za["halvings"]
        assert len(za["history"]) == za["halvings"] + 1
        assert za["history"][0]["rel_change"] is None
        assert "yakınsadı" in za["beyan"] and "adım" in za["beyan"]
        # Fiziksel doğruluk: yüzey sıcaklığı ierfc analitiğine < %2
        # (otomatik tolerans %1 + uzaysal hata payı; ölçülen ~%0,23).
        yuzey = int(line[0])
        T_exp = vaka["expected_outputs"]["temperature_K"]["x0.000_t100"]
        assert result.T_final[yuzey] == pytest.approx(T_exp, rel=0.02)

    def test_degismeyen_alan_trivyal_yakinsar(self, kurulum):
        """Her yüzey adyabatik → alan yuvarlama gürültüsü dışında sabit
        kalır; sürücünün ölçek tabanı gürültüyü gürültüye bölmez, ilk
        kıyasta yakınsar (sonsuz yarılamaya gitmez)."""
        _, mesh, material, _ = kurulum
        result = solve_transient_auto(
            mesh, material, 10.0, AdiabaticBC(), AdiabaticBC(), 300.0)
        za = result.meta["zaman_adimi"]
        assert za["converged"] is True
        assert za["halvings"] == 1
        # Yuvarlama gürültüsü / taban oranı; toleransın çok altında kalmalı.
        assert za["rel_change"] < 1e-4
        np.testing.assert_allclose(result.T_final, 300.0, rtol=0, atol=1e-9)

    def test_tek_kosu_denetlenemedi_beyani(self, kurulum):
        """max_halvings=0 → yakınsama denetlenemez; beyan bunu AÇIKÇA söyler
        (denetlenmemiş koşu yakınsamış gibi sunulmaz)."""
        vaka, mesh, material, _ = kurulum
        inp = vaka["inputs"]
        result = solve_transient_auto(
            mesh, material, 100.0,
            inner_bc=HeatFluxBC(q=inp["surface_heat_flux_W_m2"]),
            outer_bc=AdiabaticBC(),
            T_initial=inp["initial_temperature_K"],
            max_halvings=0)
        za = result.meta["zaman_adimi"]
        assert za["converged"] is False
        assert "DENETLENEMEDİ" in za["beyan"]

    def test_yakinsamayan_kosu_durust_beyan(self, kurulum):
        """Tolerans erişilemeyecek kadar sıkıyken sürücü YAKINSAMADI demeli."""
        vaka, mesh, material, _ = kurulum
        inp = vaka["inputs"]
        result = solve_transient_auto(
            mesh, material, 100.0,
            inner_bc=HeatFluxBC(q=inp["surface_heat_flux_W_m2"]),
            outer_bc=AdiabaticBC(),
            T_initial=inp["initial_temperature_K"],
            tol=1e-12, n_steps0=4, max_halvings=1)
        za = result.meta["zaman_adimi"]
        assert za["converged"] is False
        assert "YAKINSAMADI" in za["beyan"]


class TestSicakligaBagliOzellikler:
    """Sıcaklığa bağlı ρ/c_p/k yolu — Kirchhoff analitiği + bekçiler."""

    A, T_W, L = 0.05, 0.025, 0.1
    B = A + T_W
    K0, BETA = 15.0, 1.0e-3

    def test_kirchhoff_isi_akisi(self):
        """k(T) = k0(1 + β(T−300)) ile iki yüzeyi sabit sıcaklıklı kabuk:
        q' = 2π ∫_{T2}^{T1} k dT / ln(b/a) (Kirchhoff dönüşümü). Yarı-kapalı
        Picard yinelemesi kararlı hâlde TAM doğrusal olmayan çözüme oturur."""
        material = ThermalMaterial(
            rho=1.0, cp=1.0,
            k=lambda T: self.K0 * (1.0 + self.BETA * (T - 300.0)))
        mesh = build_wall_mesh([(0.0, self.A), (self.L, self.A)], self.T_W,
                               n_axial=4, n_radial=16)
        result = solve_transient(
            mesh, material, np.linspace(0.0, 1.0, 51),
            inner_bc=FixedTemperatureBC(T=600.0),
            outer_bc=FixedTemperatureBC(T=300.0),
            T_initial=300.0)
        # ∫_{300}^{600} k0(1+β(T−300)) dT = k0(300 + β·300²/2)
        integral_k = self.K0 * (300.0 + self.BETA * 300.0 ** 2 / 2.0)
        qp_ana = 2.0 * np.pi * integral_k / np.log(self.B / self.A)
        qp_num = result.energy["qdot_inner_W"][-1] / self.L
        assert qp_num == pytest.approx(qp_ana, rel=0.01)
        assert "önceki adım" in result.meta["sicakliga_bagli_ozellikler"]

    def test_sabit_donduren_fonksiyon_skalerle_ayni(self):
        """Fonksiyon yolu ile skaler yol aynı fiziği çözmeli (birebir)."""
        mesh = build_wall_mesh([(0.0, self.A), (self.L, self.A)], self.T_W,
                               n_axial=2, n_radial=4)
        times = np.linspace(0.0, 0.5, 11)
        ortak = dict(inner_bc=ConvectionBC(h=500.0, T_inf=2000.0),
                     outer_bc=AdiabaticBC(), T_initial=300.0)
        res_skaler = solve_transient(
            mesh, ThermalMaterial(rho=1.0, cp=100.0, k=15.0),
            times, **ortak)
        res_fn = solve_transient(
            mesh, ThermalMaterial(rho=1.0,
                                  cp=lambda T: np.full_like(T, 100.0),
                                  k=lambda T: np.full_like(T, 15.0)),
            times, **ortak)
        np.testing.assert_allclose(res_fn.T_final, res_skaler.T_final,
                                   rtol=1e-12)

    def test_fiziksel_olmayan_ozellik_reddedilir(self):
        """Isınan aralıkta negatife düşen k(T) sessizce kullanılamaz."""
        mesh = build_wall_mesh([(0.0, self.A), (self.L, self.A)], self.T_W,
                               n_axial=2, n_radial=4)
        material = ThermalMaterial(
            rho=1.0, cp=1.0,
            k=lambda T: 15.0 - 0.2 * (T - 300.0))   # T > 375 K → k < 0
        with pytest.raises(ValueError, match="pozitif"):
            solve_transient(mesh, material, np.linspace(0.0, 1.0, 21),
                            inner_bc=FixedTemperatureBC(T=1000.0),
                            outer_bc=AdiabaticBC(), T_initial=300.0)


class TestGirisBekcileri:
    """Giriş doğrulama bekçileri: bozuk girdi sessizce çözülmez."""

    @pytest.fixture(scope="class")
    def mesh(self):
        return build_wall_mesh([(0.0, 0.05), (0.1, 0.05)], 0.01,
                               n_axial=2, n_radial=3)

    MAT = ThermalMaterial(rho=8000.0, cp=500.0, k=15.0)

    def _coz(self, mesh, **degisiklik):
        args = dict(material=self.MAT, times=np.linspace(0.0, 1.0, 5),
                    inner_bc=ConvectionBC(h=100.0, T_inf=2000.0),
                    outer_bc=AdiabaticBC(), T_initial=300.0)
        args.update(degisiklik)
        return solve_transient(mesh, **args)

    def test_zaman_izgarasi_bekcileri(self, mesh):
        with pytest.raises(ValueError):
            self._coz(mesh, times=np.array([1.0, 2.0]))       # t=0 yok
        with pytest.raises(ValueError):
            self._coz(mesh, times=np.array([0.0, 2.0, 1.0]))  # artan değil
        with pytest.raises(ValueError):
            self._coz(mesh, times=np.array([0.0]))            # tek nokta

    def test_baslangic_sicakligi_bekcisi(self, mesh):
        with pytest.raises(ValueError):
            self._coz(mesh, T_initial=-10.0)
        with pytest.raises(ValueError):
            self._coz(mesh, T_initial=float("nan"))

    def test_malzeme_bekcileri(self):
        with pytest.raises(ValueError):
            ThermalMaterial(rho=-1.0, cp=500.0, k=15.0)
        with pytest.raises(ValueError):
            ThermalMaterial(rho=8000.0, cp=0.0, k=15.0)
        with pytest.raises(ValueError):
            ThermalMaterial(rho=8000.0, cp=500.0, k=float("inf"))

    def test_bc_bekcileri(self, mesh):
        with pytest.raises(ValueError):
            AmbientBC(h=10.0, T_ambient=300.0, emissivity=1.5)
        with pytest.raises(ValueError):
            AmbientBC(h=-1.0, T_ambient=300.0)
        with pytest.raises(ValueError):
            AmbientBC(h=10.0, T_ambient=0.0)
        with pytest.raises(TypeError):
            self._coz(mesh, inner_bc=42)                     # BC değil
        with pytest.raises(ValueError):
            self._coz(mesh, inner_bc=ConvectionBC(h=-5.0, T_inf=2000.0))
        with pytest.raises(ValueError):
            self._coz(mesh, inner_bc=FixedTemperatureBC(T=-100.0))

    def test_auto_surucu_bekcileri(self, mesh):
        for hatali in (dict(t_end=-1.0), dict(tol=0.0), dict(tol=1.5),
                       dict(n_steps0=0), dict(max_halvings=-1)):
            args = dict(t_end=1.0, inner_bc=AdiabaticBC(),
                        outer_bc=AdiabaticBC(), T_initial=300.0)
            args.update(hatali)
            with pytest.raises(ValueError):
                solve_transient_auto(mesh, self.MAT, **args)


class TestPaketVeSonucBeyani:
    """Paket durumu + sonuç beyanları (sahte veri yasağı bekçileri)."""

    def test_module_status_thermal_implemented(self):
        import hrma.fea as fea
        assert fea.MODULE_STATUS["thermal_axisym"] == "IMPLEMENTED"
        # V2.7 Aşama C ile planar_grain gerçek kayda geçti; beyanın
        # kendi bekçileri tests/test_fea_planar_grain.py içindedir.
        assert fea.MODULE_STATUS["planar_grain"] == "IMPLEMENTED"

    def test_sonuc_meta_beyanlari(self):
        mesh = build_wall_mesh([(0.0, 0.05), (0.1, 0.05)], 0.01,
                               n_axial=2, n_radial=3)
        result = solve_transient(
            mesh, ThermalMaterial(rho=8000.0, cp=500.0, k=15.0),
            np.linspace(0.0, 1.0, 5),
            inner_bc=ConvectionBC(h=100.0, T_inf=2000.0),
            outer_bc=AmbientBC(h=10.0, T_ambient=300.0, emissivity=0.8),
            T_initial=300.0)
        meta = result.meta
        assert "_source" in meta and "_basis" in meta
        assert "geri Euler" in meta["_basis"]
        # NOT_MODELLED beyanları (görev kalemi 4).
        beyanlar = " ".join(meta["not_modelled"])
        assert "ablasyon" in beyanlar.lower()
        assert "faz değişimi" in beyanlar
        # Eksenel iletim İHMAL EDİLMİYOR — açıkça öyle beyan edilmeli.
        assert "MODELLENIYOR" in meta["eksenel_iletim"]
        assert "ihmal YOK" in meta["eksenel_iletim"]
        # Uç kesitler ve başlangıç koşulu beyanı.
        assert "adyabatik" in meta["sinir_kosullari"]["uc_kesitler"]
        assert "ateşleme" in meta["baslangic_kosulu"]
        # Işıma açıkken lineerleştirme hatası beyanı zorunlu.
        assert "isima_lineerlestirme_hatasi" in meta
        # Enerji bütçesi alanları eksiksiz.
        for anahtar in ("Q_inner_J", "Q_outer_J", "dU_J", "residual_J",
                        "residual_rel", "qdot_inner_W", "qdot_outer_W"):
            assert anahtar in result.energy
