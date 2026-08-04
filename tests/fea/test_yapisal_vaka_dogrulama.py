"""
Yapısal FEA çekirdeğinin data/validation vaka dosyalarına karşı doğrulanması.

test_yapisal_dogrulama.py analitik bağıntıları TESTİN İÇİNDE türetip çözücüyü
sınar; bu dosya ise aynı çözücüyü depodaki YAYIMLANMIŞ doğrulama kayıtlarına
(data/validation/*.json) karşı koşar. Beklenen değerler vaka dosyasından
OKUNUR (testte kopyalanmaz); tolerans da vakanın kendi ``tolerance_pct``
alanından gelir. Böylece vaka dosyası güncellenirse test kendiliğinden onu
izler ve "iki ayrı doğruluk kaynağı" çelişkisi doğmaz.

Vakalar ve künyeleri (dosyalardaki ``source`` alanının özeti):

* ``structural_lame_thick_cylinder_si`` — Lamé kalın cidar çözümü, SI
  birimlerinde; G. Lamé (1852), çağdaş sunum Timoshenko & Goodier,
  "Theory of Elasticity". Değerler kapalı formdan TAM türetilmiştir
  (analytic_derived); tolerans %0.1.
* ``structural_ansys_vm25_internal_pressure`` — Ansys Mechanical APDL
  Verification Manual VM25 "Stresses in a Long Cylinder", Durum 1 (yalnız iç
  basınç), kaynağın orijinal psi/inç birimlerinde; tolerans %0.5. SI vakasıyla
  aynı fiziği FARKLI birim sisteminde sınar: çözücü psi/inç vakasını geçip SI
  vakasında kalıyorsa hata fizikte değil birim dönüşümündedir (dosyanın kendi
  beyanı).

Her iki vaka da ``stress_state: plane_stress_open_end`` beyan eder (açık uç,
σ_z = 0). Düz silindirde bu durum, tek uç kesitte u_z = 0 (yalnız rijit cisim
modunu bağlar) + diğer uç serbest sınır koşuluyla birebir kurulur: çözüm
z'den bağımsızdır, eksenel net kuvvet sıfırdır ve σ_z noktasal olarak sıfıra
oturur. VM25 dosyasının uyarısı gereği bu ayrım ayrıca test edilir — çözücü
yanlışlıkla düzlem şekil değiştirme kursaydı u_r hedefi HAKLI olarak kırmızı
olurdu.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from hrma.fea.mesh_axisym import build_wall_mesh
from hrma.fea.structural_axisym import Material, solve_pressure

VALIDATION_DIR = Path(__file__).resolve().parents[2] / "data" / "validation"

# ---------------------------------------------------------------------------
# Birim dönüşümleri — tanım gereği TAM değerler (uluslararası inç ve lbf):
#   1 in  = 0.0254 m           (tam, tanım)
#   1 lbf = 4.4482216152605 N  (tam, tanım)
#   1 psi = 1 lbf / in²
# VM25 vakası kaynağın orijinal psi/inç birimlerinde verildiği için girişler
# SI'ya bu sabitlerle çevrilir, çıktılar karşılaştırma için geri çevrilir.
# ---------------------------------------------------------------------------
INCH_M = 0.0254
LBF_N = 4.4482216152605
PSI_PA = LBF_N / INCH_M ** 2

# ---------------------------------------------------------------------------
# Vaka mesh politikası (tek yerde). n_radial ÇİFT olmalı: vakaların hedef
# yarıçapları iç yüzey, tam orta ve dış yüzeydir; çift bölmede üçü de düğüme
# denk gelir ve karşılaştırma enterpolasyon hatası taşımaz. (64, 96) seçimi
# SI vakasının %0.1 toleransına ~3 kat pay bırakır (ölçülen en kötü nokta
# hatası ~%0.032; her iki vaka aynı boyutsuz problemdir: b/a = 2, ν = 0.3).
# ---------------------------------------------------------------------------
CASE_N_AXIAL = 64
CASE_N_RADIAL = 96


def _load_case(name: str) -> dict:
    """Vaka dosyasını okur; kimlik-dosya adı uyumunu (README bekçisi) sınar."""
    path = VALIDATION_DIR / f"{name}.json"
    assert path.exists(), f"Doğrulama vakası eksik: {path}"
    case = json.loads(path.read_text(encoding="utf-8"))
    assert case["case"] == name, "Vaka kimliği dosya adıyla uyuşmuyor."
    assert case["discipline"] == "structural"
    return case


def _solve_open_end_cylinder(a: float, b: float, p: float,
                             E: float, nu: float):
    """Açık uçlu (plane_stress_open_end) düz silindir çözümü.

    Tek uç kesitte u_z = 0 yalnız z rijit cisim modunu bağlar; diğer uç ve
    u_r her yerde serbesttir. Düz silindirde çözüm z'den bağımsız olduğundan
    bu kurulum açık uç Lamé durumunun (σ_z = 0) kendisidir.
    """
    t = b - a
    L = 2.0 * t
    mesh = build_wall_mesh([(0.0, a), (L, a)], t,
                           n_axial=CASE_N_AXIAL, n_radial=CASE_N_RADIAL)
    result = solve_pressure(mesh, Material(E=E, nu=nu), p, axial_fix="z_min")
    return mesh, result


def _radial_line(mesh, field):
    """Orta eksenel istasyondaki radyal düğüm hattı: (r, alan[hat])."""
    i_mid = mesh.n_axial // 2
    idx = mesh.node_index_grid[i_mid, :]
    return mesh.nodes[idx, 1], np.asarray(field)[idx]


def _check_profile(r_line, val_line, expected: dict, r_parse, unit_scale,
                   tol, zero_scale):
    """Beklenen (yarıçap → değer) sözlüğünü FE profiliyle karşılaştırır.

    r_parse : anahtar ("r_0.10m" / "r_4in") → model birimindeki yarıçap.
    unit_scale : FE değeri (SI) → vaka birimi bölücüsü (SI vakada 1.0).
    zero_scale : beklenen değer tam 0 ise bağıl hata ölçeği (vaka biriminde
        basınç genliği; σ_r profili sıfır geçişli olduğundan 0 hedefinde
        mutlak hata basınca oranlanır — dürüst ölçek, gevşetme değil).
    """
    for key, exp_val in expected.items():
        r_t = r_parse(key)
        num = float(np.interp(r_t, r_line, val_line)) / unit_scale
        scale = abs(exp_val) if exp_val != 0.0 else zero_scale
        err = abs(num - exp_val) / scale
        assert err < tol, (
            f"{key}: FE={num:.6g}, beklenen={exp_val:.6g}, "
            f"bağıl hata %{100 * err:.4f} >= %{100 * tol:.4f}")


class TestVakaLameSI:
    """structural_lame_thick_cylinder_si — analitik türetilmiş SI vakası.

    Künye: G. Lamé (1852); Timoshenko & Goodier, "Theory of Elasticity"
    (vaka dosyasının ``source`` alanı). Değerler kapalı formdan tamdır.
    """

    @pytest.fixture(scope="class")
    def vaka(self):
        return _load_case("structural_lame_thick_cylinder_si")

    @pytest.fixture(scope="class")
    def cozum(self, vaka):
        inp = vaka["inputs"]
        assert inp["stress_state"] == "plane_stress_open_end"
        assert inp["external_pressure_pa"] == 0.0
        mesh, result = _solve_open_end_cylinder(
            a=inp["inner_radius_m"], b=inp["outer_radius_m"],
            p=inp["internal_pressure_pa"],
            E=inp["youngs_modulus_pa"], nu=inp["poissons_ratio"])
        return mesh, result

    @staticmethod
    def _r_m(key: str) -> float:
        # "r_0.10m" → 0.10
        return float(key.removeprefix("r_").removesuffix("m"))

    def test_radyal_gerilme_profili(self, vaka, cozum):
        mesh, result = cozum
        tol = vaka["tolerance_pct"] / 100.0
        r, sr = _radial_line(mesh, result.stress_nodal[:, 1])
        _check_profile(r, sr, vaka["expected_outputs"]["radial_stress_pa"],
                       self._r_m, 1.0, tol,
                       zero_scale=vaka["inputs"]["internal_pressure_pa"])

    def test_cember_gerilme_profili(self, vaka, cozum):
        mesh, result = cozum
        tol = vaka["tolerance_pct"] / 100.0
        r, st = _radial_line(mesh, result.stress_nodal[:, 2])
        _check_profile(r, st, vaka["expected_outputs"]["tangential_stress_pa"],
                       self._r_m, 1.0, tol,
                       zero_scale=vaka["inputs"]["internal_pressure_pa"])

    def test_radyal_yer_degistirme(self, vaka, cozum):
        mesh, result = cozum
        tol = vaka["tolerance_pct"] / 100.0
        r, ur = _radial_line(mesh, result.displacement[:, 1])
        _check_profile(r, ur,
                       vaka["expected_outputs"]["radial_displacement_m"],
                       self._r_m, 1.0, tol, zero_scale=np.max(np.abs(ur)))

    def test_von_mises_ic_yuzey(self, vaka, cozum):
        """Vakanın vM hedefi düzlem gerilme formülüdür (σ_z = 0 ile tutarlı)."""
        mesh, result = cozum
        tol = vaka["tolerance_pct"] / 100.0
        r, vm = _radial_line(mesh, result.von_mises_nodal)
        _check_profile(r, vm, vaka["expected_outputs"]["von_mises_stress_pa"],
                       self._r_m, 1.0, tol,
                       zero_scale=vaka["inputs"]["internal_pressure_pa"])

    def test_acik_uc_sigma_z_sifira_oturur(self, vaka, cozum):
        """stress_state bekçisi: açık uçta σ_z ≈ 0 (basıncın binde biri)."""
        mesh, result = cozum
        _, sz = _radial_line(mesh, result.stress_nodal[:, 0])
        p = vaka["inputs"]["internal_pressure_pa"]
        assert np.max(np.abs(sz)) < 1.0e-3 * p


class TestVakaAnsysVM25:
    """structural_ansys_vm25_internal_pressure — VM25 Durum 1 (psi/inç).

    Künye: Ansys Mechanical APDL Verification Manual, VM25 "Stresses in a
    Long Cylinder" (PyMAPDL yeniden yayımı; vaka dosyasının ``source``
    alanı). SI vakasıyla aynı boyutsuz problem — birim dönüşümü bekçisi.
    """

    @pytest.fixture(scope="class")
    def vaka(self):
        return _load_case("structural_ansys_vm25_internal_pressure")

    @pytest.fixture(scope="class")
    def cozum(self, vaka):
        inp = vaka["inputs"]
        assert inp["stress_state"] == "plane_stress_open_end"
        # Durum 1: dönme yok — santrifüj gövde kuvveti modellenmez; dönmeli
        # Durum 2 (structural_ansys_vm25_rotation) bu çözücünün kapsamı
        # DIŞINDADIR ve burada sınanmaz.
        assert inp["angular_velocity_rad_s"] == 0.0
        mesh, result = _solve_open_end_cylinder(
            a=inp["inner_radius_in"] * INCH_M,
            b=inp["outer_radius_in"] * INCH_M,
            p=inp["internal_pressure_psi"] * PSI_PA,
            E=inp["youngs_modulus_psi"] * PSI_PA,
            nu=inp["poissons_ratio"])
        return mesh, result

    @staticmethod
    def _r_m(key: str) -> float:
        # "r_4in" → 4.0 inç → metre (FE modeli SI'da kurulur)
        return float(key.removeprefix("r_").removesuffix("in")) * INCH_M

    def test_radyal_gerilme_profili(self, vaka, cozum):
        mesh, result = cozum
        tol = vaka["tolerance_pct"] / 100.0
        r, sr = _radial_line(mesh, result.stress_nodal[:, 1])
        _check_profile(r, sr, vaka["expected_outputs"]["radial_stress_psi"],
                       self._r_m, PSI_PA, tol,
                       zero_scale=vaka["inputs"]["internal_pressure_psi"])

    def test_cember_gerilme_profili(self, vaka, cozum):
        mesh, result = cozum
        tol = vaka["tolerance_pct"] / 100.0
        r, st = _radial_line(mesh, result.stress_nodal[:, 2])
        _check_profile(r, st,
                       vaka["expected_outputs"]["tangential_stress_psi"],
                       self._r_m, PSI_PA, tol,
                       zero_scale=vaka["inputs"]["internal_pressure_psi"])

    def test_radyal_yer_degistirme(self, vaka, cozum):
        """u_r hedefi YALNIZ açık uç (σ_z=0) varsayımıyla çıkar — vaka
        dosyasının verification_note_tr uyarısının sınandığı yer burasıdır:
        çözücü düzlem şekil değiştirme kursaydı 0.0076267 in verir ve %3
        sapardı; tolerans %0.5 bunu yakalar."""
        mesh, result = cozum
        tol = vaka["tolerance_pct"] / 100.0
        r, ur = _radial_line(mesh, result.displacement[:, 1])
        _check_profile(r, ur,
                       vaka["expected_outputs"]["radial_displacement_in"],
                       self._r_m, INCH_M, tol, zero_scale=np.max(np.abs(ur)))

    def test_acik_uc_sigma_z_sifira_oturur(self, vaka, cozum):
        """inputs.axial_stress_psi = 0 beyanının FE karşılığı."""
        mesh, result = cozum
        assert vaka["inputs"]["axial_stress_psi"] == 0.0
        _, sz = _radial_line(mesh, result.stress_nodal[:, 0])
        p = vaka["inputs"]["internal_pressure_psi"] * PSI_PA
        assert np.max(np.abs(sz)) < 1.0e-3 * p
