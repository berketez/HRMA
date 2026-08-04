"""
Eksenel simetrik yapısal FEA çekirdeği doğrulama bekçileri (D3'ün yapısal
yarısı — docs/V2.7_ANALIZ_MODULU.md §5: doğrulanmamış FEA yayımlanmaz).

Kapsam:
  (a) Lamé kalın cidarlı silindir analitiği — iç basınçlı silindirde σ_θ ve
      σ_r radyal profilleri, u_r profili ve düzlem şekil değiştirme σ_z
      ilişkisi; hata < %2. Analitik değerler TESTİN İÇİNDE formülden
      türetilir, hardcode "beklenen" sayı yoktur.
  (b) Patch testi — eksenel simetride uyumlu sabit gerinim alanı
      (ε_r = ε_θ ve γ_rz = 0 zorunlu: u_z = αz, u_r = γr) sınırdan
      dayatılınca iç düğümler ve gerilmeler alanı makine hassasiyetinde
      yeniden üretilmeli.
  (c) Mesh yakınsama monotonluğu — inceltmede maks von Mises hatası kesin
      azalmalı; solve_with_refinement yakınsamayı ve dürüst beyanı vermeli.
  (+) Mesh üreticisi bekçileri: cidar boyunca eleman alt sınırı, geçersiz
      girdi redleri, eğik konturda dik kalınlık, kenar kümesi tutarlılığı.

Analitik kaynak: Timoshenko & Goodier, "Theory of Elasticity", 3. baskı,
Böl. 4 (iç/dış basınçlı silindir — Lamé çözümü).
"""

import numpy as np
import pytest

from hrma.fea.mesh_axisym import (
    build_wall_mesh,
    DEFAULT_ELEMS_THROUGH_WALL,
    MIN_ELEMS_THROUGH_WALL,
)
from hrma.fea.structural_axisym import (
    Material,
    elasticity_matrix,
    solve_linear,
    solve_pressure,
    solve_with_refinement,
    von_mises,
    DEFAULT_REFINE_TOL,
)

# ---------------------------------------------------------------------------
# Ortak problem tanımı: iç basınçlı kalın cidarlı silindir.
# a: iç yarıçap, t: cidar, b = a + t; L: uzunluk; p: iç basınç.
# Tek yerde tanımlanır, tüm Lamé testleri buradan okur (parametre tutarlılığı).
# ---------------------------------------------------------------------------
LAME_A = 0.05          # m
LAME_T = 0.025         # m  (b/a = 1.5 — gerçekten "kalın" cidar)
LAME_L = 0.10          # m
LAME_P = 10.0e6        # Pa
STEEL = Material(E=200.0e9, nu=0.3, yield_strength=250.0e6, name="test-steel")

# Doğrulama eşiği: yol haritası şartı "hata < %2".
LAME_REL_TOL = 0.02


def lame_sigma_r(r, a, b, p):
    """Lamé radyal gerilme: σ_r = A(1 - b²/r²), A = p a²/(b² - a²)."""
    A = p * a * a / (b * b - a * a)
    return A * (1.0 - (b * b) / (r * r))


def lame_sigma_theta(r, a, b, p):
    """Lamé çember gerilmesi: σ_θ = A(1 + b²/r²)."""
    A = p * a * a / (b * b - a * a)
    return A * (1.0 + (b * b) / (r * r))


def lame_u_r_plane_strain(r, a, b, p, E, nu):
    """Düzlem şekil değiştirme radyal yer değiştirme:
    u_r = (1+ν)/E · (p a²/(b²-a²)) · [(1-2ν) r + b²/r]."""
    A = p * a * a / (b * b - a * a)
    return (1.0 + nu) / E * A * ((1.0 - 2.0 * nu) * r + (b * b) / r)


def lame_von_mises_plane_strain(r, a, b, p, nu):
    """Düzlem şekil değiştirmede analitik von Mises (σ_z = ν(σ_r + σ_θ))."""
    sr = lame_sigma_r(r, a, b, p)
    st = lame_sigma_theta(r, a, b, p)
    sz = nu * (sr + st)
    return np.sqrt(0.5 * ((sz - sr) ** 2 + (sr - st) ** 2 + (st - sz) ** 2))


def _cylinder_contour():
    """Silindir iç konturu: sabit yarıçaplı düz cidar."""
    return [(0.0, LAME_A), (LAME_L, LAME_A)]


def _solve_lame(n_axial, n_radial):
    mesh = build_wall_mesh(_cylinder_contour(), LAME_T, n_axial, n_radial)
    # Her iki uçta u_z = 0: düzlem şekil değiştirme koşulu — analitik çözümle
    # birebir aynı sınır değer problemi.
    result = solve_pressure(mesh, STEEL, LAME_P, axial_fix="both_ends")
    return mesh, result


class TestLameKalinCidar:
    """(a) Lamé analitik karşılaştırması — çözücünün gerilme alanı bekçisi."""

    @pytest.fixture(scope="class")
    def cozum(self):
        return _solve_lame(n_axial=8, n_radial=12)

    def _radial_profile(self, mesh, alan):
        """Orta istasyondaki radyal düğüm hattı boyunca (r, alan) döndürür."""
        i_mid = mesh.n_axial // 2
        idx = mesh.node_index_grid[i_mid, :]
        r = mesh.nodes[idx, 1]
        return r, alan[idx]

    def test_sigma_theta_profili(self, cozum):
        mesh, result = cozum
        a, b, p = LAME_A, LAME_A + LAME_T, LAME_P
        r, st_num = self._radial_profile(mesh, result.stress_nodal[:, 2])
        st_ana = lame_sigma_theta(r, a, b, p)
        err = np.max(np.abs(st_num - st_ana)) / np.max(np.abs(st_ana))
        assert err < LAME_REL_TOL, (
            f"σ_θ profil hatası %{100 * err:.3f} >= %{100 * LAME_REL_TOL:.0f}")
        # İşaret fiziği: iç basınç çember yönünde ÇEKME üretir.
        assert np.all(st_num > 0.0)

    def test_sigma_r_profili(self, cozum):
        mesh, result = cozum
        a, b, p = LAME_A, LAME_A + LAME_T, LAME_P
        r, sr_num = self._radial_profile(mesh, result.stress_nodal[:, 1])
        sr_ana = lame_sigma_r(r, a, b, p)
        # σ_r iç yüzeyde -p, dış yüzeyde 0'a gider; sıfır geçişli alan için
        # doğru ölçek profil genliğidir (=p).
        err = np.max(np.abs(sr_num - sr_ana)) / np.max(np.abs(sr_ana))
        assert err < LAME_REL_TOL, (
            f"σ_r profil hatası %{100 * err:.3f} >= %{100 * LAME_REL_TOL:.0f}")
        # Sınır koşulu fiziği: iç yüzeyde σ_r ≈ -p, dış yüzeyde ≈ 0.
        assert sr_num[0] == pytest.approx(-LAME_P, rel=0.05)
        assert abs(sr_num[-1]) < 0.05 * LAME_P

    def test_u_r_profili(self, cozum):
        mesh, result = cozum
        a, b, p = LAME_A, LAME_A + LAME_T, LAME_P
        r, ur_num = self._radial_profile(mesh, result.displacement[:, 1])
        ur_ana = lame_u_r_plane_strain(r, a, b, p, STEEL.E, STEEL.nu)
        err = np.max(np.abs(ur_num - ur_ana)) / np.max(np.abs(ur_ana))
        assert err < LAME_REL_TOL, (
            f"u_r profil hatası %{100 * err:.3f} >= %{100 * LAME_REL_TOL:.0f}")
        # İç basınç cidarı dışa şişirir.
        assert np.all(ur_num > 0.0)

    def test_sigma_z_duzlem_sekil_degistirme(self, cozum):
        """Her iki uçta u_z=0 iken σ_z = ν(σ_r + σ_θ) sağlanmalı."""
        mesh, result = cozum
        r, sz_num = self._radial_profile(mesh, result.stress_nodal[:, 0])
        _, sr_num = self._radial_profile(mesh, result.stress_nodal[:, 1])
        _, st_num = self._radial_profile(mesh, result.stress_nodal[:, 2])
        sz_beklenen = STEEL.nu * (sr_num + st_num)
        olcek = np.max(np.abs(st_num))
        assert np.max(np.abs(sz_num - sz_beklenen)) / olcek < LAME_REL_TOL

    def test_emniyet_katsayisi_alani(self, cozum):
        """SF alanı akma/von Mises'ten türetilmiş ve tutarlı olmalı."""
        _, result = cozum
        assert result.safety_factor_nodal is not None
        assert result.min_safety_factor is not None
        ys = STEEL.yield_strength
        # min SF, Gauss maks von Mises'ten türetilir (kaynak beyanı meta'da).
        assert result.min_safety_factor == pytest.approx(
            ys / result.max_von_mises)
        # Düğüm SF alanı = yield / vm_nodal (vm > 0 olan her yerde).
        maske = result.von_mises_nodal > 0
        np.testing.assert_allclose(
            result.safety_factor_nodal[maske],
            ys / result.von_mises_nodal[maske])

    def test_sonuc_beyani_ve_not_modelled(self, cozum):
        """Sahte veri yasağı: sonuç, temelini ve modellemediklerini bildirmeli."""
        _, result = cozum
        meta = result.meta
        assert "_source" in meta and "_basis" in meta
        beyanlar = " ".join(meta["not_modelled"])
        assert "termal" in beyanlar          # termal gerilme sonraki dalga
        assert "plastisite" in beyanlar.replace("Plastisite", "plastisite")


class TestPatchSabitGerinim:
    """(b) Patch testi — eleman formülasyonu bekçisi.

    Eksenel simetride uyumlu sabit gerinim alanı ε_r = ε_θ ve γ_rz = 0
    şartını taşır (ε_θ = u_r/r sabitse u_r = γr → ε_r = γ; sabit τ_rz ise
    z-dengesindeki τ_rz/r terimi yüzünden gövde kuvvetsiz denge olmaz). Alan:
        u_z = α z,  u_r = γ r
        ε = [α, γ, γ, 0],  σ = D ε (sabit)
    Sınır düğümlerine alan dayatılır; iç düğümler ÇÖZÜMDEN gelir ve alanı
    birebir (makine hassasiyeti mertebesinde) vermelidir. İç düğümler bozuk
    (perturbe) konumdadır ki düzgün gridin maskeleyebileceği hatalar açığa
    çıksın.
    """

    # Ad seçimi bilinçli: ALPHA/GAMMA gibi genel adlar depodaki başka
    # kavramlarla (örn. gaz γ'sı) çakışır; burada gerinim bileşeni adları
    # kullanılır.
    #
    # γ_rz = 0 bilinçlidir: eksenel simetride z-dengesi
    # ∂σ_z/∂z + ∂τ_rz/∂r + τ_rz/r = 0 olduğundan SABİT kayma gerilmesi gövde
    # kuvveti olmadan denge durumu DEĞİLDİR; uyumlu sabit gerinim patch alanı
    # kaymasızdır (u_z = αz, u_r = γr — standart eksenel simetrik patch).
    PATCH_EPS_Z = 2.0e-4      # ε_z
    PATCH_GAMMA_RZ = 0.0      # γ_rz (yukarıdaki gerekçeyle sıfır)
    PATCH_EPS_RT = 3.0e-4     # ε_r = ε_θ

    def _alan(self, z, r):
        u_z = self.PATCH_EPS_Z * z + self.PATCH_GAMMA_RZ * r
        u_r = self.PATCH_EPS_RT * r
        return u_z, u_r

    @pytest.fixture(scope="class")
    def cozum(self):
        # Kalın halka: a=1, b=2 (kalınlık 1) — 1/r terimi ihmal edilemez.
        mesh = build_wall_mesh([(0.0, 1.0), (1.0, 1.0)], 1.0,
                               n_axial=3, n_radial=3)
        # İç düğümleri deterministik biçimde boz (jacobian pozitif kalacak
        # kadar küçük: eleman boyu ~1/3, bozma <= 0.05).
        rng = np.random.default_rng(42)
        ic = mesh.interior_nodes()
        mesh.nodes[ic] += rng.uniform(-0.05, 0.05, size=(ic.size, 2))

        dirichlet = []
        for n in mesh.boundary_nodes():
            z, r = mesh.nodes[n]
            u_z, u_r = self._alan(z, r)
            dirichlet.append((int(n), 0, u_z))
            dirichlet.append((int(n), 1, u_r))
        result = solve_linear(mesh, STEEL, dirichlet)
        return mesh, result

    def test_ic_dugum_yer_degistirmeleri(self, cozum):
        mesh, result = cozum
        ic = mesh.interior_nodes()
        assert ic.size > 0, "Patch testinde iç düğüm yoksa test anlamsız."
        z, r = mesh.nodes[ic, 0], mesh.nodes[ic, 1]
        u_z_b, u_r_b = self._alan(z, r)
        beklenen = np.stack([u_z_b, u_r_b], axis=1)
        olcek = np.max(np.abs(beklenen))
        np.testing.assert_allclose(result.displacement[ic], beklenen,
                                   rtol=0.0, atol=1e-8 * olcek)

    def test_gauss_gerilmeleri_sabit(self, cozum):
        _, result = cozum
        D = elasticity_matrix(STEEL.E, STEEL.nu)
        eps = np.array([self.PATCH_EPS_Z, self.PATCH_EPS_RT, self.PATCH_EPS_RT, self.PATCH_GAMMA_RZ])
        sigma_beklenen = D @ eps
        olcek = np.max(np.abs(sigma_beklenen))
        np.testing.assert_allclose(
            result.stress_gauss,
            np.broadcast_to(sigma_beklenen, result.stress_gauss.shape),
            rtol=0.0, atol=1e-8 * olcek)

    def test_dugum_gerilmeleri_sabit(self, cozum):
        """Ekstrapolasyon + ortalama sabit alanı bozmamalı."""
        _, result = cozum
        D = elasticity_matrix(STEEL.E, STEEL.nu)
        eps = np.array([self.PATCH_EPS_Z, self.PATCH_EPS_RT, self.PATCH_EPS_RT, self.PATCH_GAMMA_RZ])
        sigma_beklenen = D @ eps
        olcek = np.max(np.abs(sigma_beklenen))
        np.testing.assert_allclose(
            result.stress_nodal,
            np.broadcast_to(sigma_beklenen, result.stress_nodal.shape),
            rtol=0.0, atol=1e-8 * olcek)


class TestMeshYakinsama:
    """(c) Yakınsama bekçileri — 'optimal mesh' iddiasının kendisi."""

    def test_maks_von_mises_hatasi_monoton_azalir(self):
        a, b, p = LAME_A, LAME_A + LAME_T, LAME_P
        vm_ana_ic = lame_von_mises_plane_strain(a, a, b, p, STEEL.nu)
        hatalar = []
        for n_ax, n_rad in [(4, 3), (8, 6), (16, 12)]:
            _, result = _solve_lame(n_ax, n_rad)
            hata = abs(result.max_von_mises - vm_ana_ic) / vm_ana_ic
            hatalar.append(hata)
        # Her inceltme hedef büyüklüğün hatasını KESİN azaltmalı.
        assert hatalar[0] > hatalar[1] > hatalar[2], (
            f"Yakınsama monoton değil: {hatalar}")

    def test_solve_with_refinement_yakinsar_ve_beyan_eder(self):
        a, b, p = LAME_A, LAME_A + LAME_T, LAME_P
        ref = solve_with_refinement(
            _cylinder_contour(), LAME_T, STEEL, LAME_P,
            tol=DEFAULT_REFINE_TOL, axial_fix="both_ends",
            n_axial0=4, n_radial0=MIN_ELEMS_THROUGH_WALL, max_rounds=5)

        assert ref.converged, f"Yakınsamadı: {ref.history}"
        assert len(ref.history) >= 2
        # Eleman sayısı her turda artmalı; kayıtlar beyan alanlarını taşımalı.
        n_elems = [h["n_elems"] for h in ref.history]
        assert all(n2 > n1 for n1, n2 in zip(n_elems, n_elems[1:]))
        assert ref.history[0]["rel_change"] is None
        assert ref.final_rel_change is not None
        assert ref.final_rel_change < ref.tol
        # Kullanıcı beyanı: eleman sayısı + fark + tolerans içermeli.
        assert "eleman" in ref.meta["beyan"]
        assert str(ref.mesh.n_elems) in ref.meta["beyan"]
        # Yakınsamış çözüm analitikten uzak olmamalı: düğüm alanının içteki
        # maksimumu Lamé von Mises'ine < %2 yakın.
        vm_ana_ic = lame_von_mises_plane_strain(a, a, b, p, STEEL.nu)
        vm_nodal_max = float(ref.result.von_mises_nodal.max())
        assert abs(vm_nodal_max - vm_ana_ic) / vm_ana_ic < LAME_REL_TOL

    def test_ince_cidar_hoop_limiti(self):
        """İnce limitte ortalama çember gerilmesi p·a/t'ye oturmalı.

        Lamé alanının kalınlık ortalaması tam olarak p·a/t'dir (ince cidar
        kazan formülünün karşılığı); FE ortalaması < %2 sapmalı.
        """
        a, t, p = 0.05, 0.002, 2.0e6           # t/a = 0.04 — ince cidar
        mesh = build_wall_mesh([(0.0, a), (0.05, a)], t,
                               n_axial=8, n_radial=MIN_ELEMS_THROUGH_WALL)
        result = solve_pressure(mesh, STEEL, p, axial_fix="both_ends")
        i_mid = mesh.n_axial // 2
        idx = mesh.node_index_grid[i_mid, :]
        r = mesh.nodes[idx, 1]
        st = result.stress_nodal[idx, 2]
        ortalama_hoop = np.trapz(st, r) / (r[-1] - r[0])
        hoop_ince = p * a / t                   # formülden, hardcode değil
        assert abs(ortalama_hoop - hoop_ince) / hoop_ince < LAME_REL_TOL


class TestMeshUretici:
    """Mesh üreticisi bekçileri."""

    def test_cidar_boyunca_eleman_alt_siniri(self):
        """n_radial=1 istense bile alt sınır uygulanmalı ve BEYAN edilmeli."""
        mesh = build_wall_mesh(_cylinder_contour(), LAME_T,
                               n_axial=4, n_radial=1)
        assert mesh.n_radial >= MIN_ELEMS_THROUGH_WALL
        assert mesh.meta["n_radial_istenen"] == 1
        assert mesh.meta["n_radial_kullanilan"] == mesh.n_radial
        assert mesh.meta["n_radial_alt_sinira_cekildi"] is True
        # Varsayılan politika alt sınırın altında olamaz (tutarlılık).
        assert DEFAULT_ELEMS_THROUGH_WALL >= MIN_ELEMS_THROUGH_WALL

    def test_gecersiz_girdiler_reddedilir(self):
        with pytest.raises(ValueError):
            build_wall_mesh([(0.0, 0.0), (0.1, 0.05)], 0.01, 4)   # r=0 eksen
        with pytest.raises(ValueError):
            build_wall_mesh([(0.0, 0.05), (0.1, -0.01)], 0.01, 4)  # r<0
        with pytest.raises(ValueError):
            build_wall_mesh([(0.1, 0.05), (0.0, 0.05)], 0.01, 4)   # z geri
        with pytest.raises(ValueError):
            build_wall_mesh(_cylinder_contour(), -0.01, 4)         # t<0
        with pytest.raises(ValueError):
            build_wall_mesh([(0.0, 0.05)], 0.01, 4)                # tek nokta
        with pytest.raises(ValueError):
            build_wall_mesh(_cylinder_contour(), 0.01, 0)          # n_axial=0

    def test_egik_konturda_dik_kalinlik(self):
        """Normal öteleme kipinde dik cidar kalınlığı t olmalı (konik kesit)."""
        t = 0.004
        mesh = build_wall_mesh([(0.0, 0.05), (0.1, 0.03)], t,
                               n_axial=8, n_radial=4, offset_mode="normal")
        grid = mesh.node_index_grid
        ic = mesh.nodes[grid[:, 0]]
        dis = mesh.nodes[grid[:, -1]]
        kalinlik = np.hypot(*(dis - ic).T)
        np.testing.assert_allclose(kalinlik, t, rtol=1e-9)
        assert np.all(mesh.nodes[:, 1] > 0.0)

    def test_kenar_kumeleri_tutarli(self):
        mesh = build_wall_mesh(_cylinder_contour(), LAME_T,
                               n_axial=5, n_radial=4)
        # İç kenar düğümleri iç yüzey kümesinde; artan z sırasında.
        assert np.all(np.isin(mesh.inner_edges.ravel(), mesh.inner_nodes))
        assert np.all(np.isin(mesh.outer_edges.ravel(), mesh.outer_nodes))
        z_ic = mesh.nodes[mesh.inner_edges[:, 0], 0]
        assert np.all(np.diff(z_ic) > 0.0)
        # İç yüzey yarıçapı dış yüzeyden küçük olmalı (her istasyonda).
        r_ic = mesh.nodes[mesh.node_index_grid[:, 0], 1]
        r_dis = mesh.nodes[mesh.node_index_grid[:, -1], 1]
        assert np.all(r_dis > r_ic)
        # Sınır + iç düğümler tüm düğümleri kapsamalı, kesişmemeli.
        assert (mesh.boundary_nodes().size + mesh.interior_nodes().size
                == mesh.n_nodes)


class TestCozucuGuvenlik:
    """Çözücü giriş bekçileri: tekil sistem sessizce çözülmeye çalışılmaz."""

    def test_kisitsiz_sistem_reddedilir(self):
        mesh = build_wall_mesh(_cylinder_contour(), LAME_T, 4, 3)
        with pytest.raises(ValueError):
            solve_linear(mesh, STEEL, dirichlet=[])

    def test_sadece_ur_kisiti_reddedilir(self):
        """u_z kısıtı olmadan z rijit modu serbest kalır — açık hata."""
        mesh = build_wall_mesh(_cylinder_contour(), LAME_T, 4, 3)
        dirichlet = [(int(n), 1, 0.0) for n in mesh.inner_nodes]
        with pytest.raises(ValueError):
            solve_linear(mesh, STEEL, dirichlet)

    def test_gecersiz_axial_fix_reddedilir(self):
        mesh = build_wall_mesh(_cylinder_contour(), LAME_T, 4, 3)
        with pytest.raises(ValueError):
            solve_pressure(mesh, STEEL, LAME_P, axial_fix="serbest")

    def test_akma_verilmezse_sf_uydurulmaz(self):
        """Sahte veri yasağı: akma dayanımı yoksa SF alanı None + beyan."""
        mesh = build_wall_mesh(_cylinder_contour(), LAME_T, 4, 3)
        malzeme = Material(E=200.0e9, nu=0.3)   # yield yok
        result = solve_pressure(mesh, malzeme, LAME_P, axial_fix="both_ends")
        assert result.safety_factor_nodal is None
        assert result.min_safety_factor is None
        assert "HESAPLANMADI" in result.meta["safety_factor_durumu"]


class TestPaketBeyani:
    """Paket durum beyanı: termal çözücü henüz yok ve öyle beyan edilmeli."""

    def test_module_status_durust(self):
        import hrma.fea as fea
        assert fea.MODULE_STATUS["structural_axisym"] == "IMPLEMENTED"
        assert fea.MODULE_STATUS["mesh_axisym"] == "IMPLEMENTED"
        # Termal ve düzlemsel kip implement edilmeden IMPLEMENTED yapılamaz;
        # yapılırsa bu bekçi düşer ve beyanın koda uyması istenir.
        import importlib.util
        for modul in ("thermal_axisym", "planar_grain"):
            spec = importlib.util.find_spec(f"hrma.fea.{modul}")
            if spec is None:
                assert fea.MODULE_STATUS[modul] == "NOT_IMPLEMENTED"
