"""ÖH Dalga-26 · fea-cfd · aşama 2 bekçileri — OH-D25-28 + OH-D24-01 (kalan).

Kalem (ÇİFT, tek onarım): iç kontur poliline'i (42 nokta, ~6,15° eğim
kırıkları) boğaz DIŞ yüzeyinde zayıf yeniden-giren köşe tekilliği üretiyordu
(M. L. Williams, J. Appl. Mech. 19 (1952) 526). Kırık ÖRNEKLEMENİN eseriydi:
kaynak eğri analitik olarak C1'dir (kosinüs konverjan → sıfır eğimle başlayan
Rao boğaz yayı → yayın teğetiyle başlayan koni/Bézier). Sabit bir köşe
inceltmeyle SÖNMEZ; istasyonlar kaynak poligondan sıklaşınca zincir köşeyi
bire bir kopyalar ve kırık kaynak açıda TABANLANIR.

Onarım: ``mesh_axisym.ic_kose_yuvarlatma`` — her köşe, ÜÇ NOKTASININ ÇEVREL
ÇEMBERİ yarıçaplı, iki komşu kirişe teğet (G1) yayla değiştirilir; yay kalan
kırık ``INNER_KINK_TOL_RAD``ı aşmayacak kadar bölünür. ``build_wall_mesh``
bunu kapamadan ve istasyon yerleşiminden ÖNCE uygular ve ölçümünü
``meta['ic_kose_yuvarlatma']`` altında yayımlar.

Ölçüm kanıtı: docs/scofield/raw/OH/D26/fea-cfd/a2/{once_a2,sonra_a2,
kirik_tabani}.json — üreteçleri olcum_a2.py ve olcum_kirik_tabani.py.
"""
import numpy as np

from hrma.utils.numeric_compat import trapezoid as _trapezoid
import pytest

from hrma.fea import mesh_axisym as MA
from hrma.fea import structural_axisym as SA


# ---------------------------------------------------------------------------
# Ortak fikstür: ÜRÜNÜN ürettiği kontur ailesiyle AYNI yapı — kosinüs
# konverjan (27) + Rao boğaz yayı (14) + konik doğru (1) = 42 nokta.
# Motor koşusu gerektirmez; geometri sözleşmesi
# hrma/engines/nozzle_design.py:sample_nozzle_inner_contour ile birebirdir.
# ---------------------------------------------------------------------------
def kontur_42(rc=0.0624, rt=0.0165, re=0.0466, yari_aci_deg=15.0,
              n_conv=27, n_arc=14):
    conv_aci = np.radians(30.0)
    L_conv = (rc - rt) / np.tan(conv_aci)
    Rn = 0.382 * rt
    theta = np.radians(yari_aci_deg)
    pts = []
    for i in range(n_conv):
        s = i / (n_conv - 1)
        pts.append((L_conv * s, rt + (rc - rt) * (0.5 + 0.5 * np.cos(np.pi * s))))
    arc_z, arc_r = L_conv, rt
    for i in range(1, n_arc + 1):
        a = theta * i / n_arc
        arc_z = L_conv + Rn * np.sin(a)
        arc_r = rt + Rn * (1.0 - np.cos(a))
        pts.append((arc_z, arc_r))
    pts.append((arc_z + (re - arc_r) / np.tan(theta), re))
    return np.asarray(pts, dtype=float)


def kirik_derece(P):
    a = MA.polyline_donus_acilari(np.asarray(P, dtype=float))
    return float(np.degrees(np.max(a))) if a.size else 0.0


def istasyon_kirigi(C, t, na, tol):
    m = MA.build_wall_mesh(C, t, n_axial=na, n_radial=4,
                           inner_kink_tol_rad=tol)
    ic = m.nodes[np.asarray(m.node_index_grid, dtype=int)[:, 0]]
    return kirik_derece(ic), m


class TestOHD2528KirikTabani:
    """Kırık inceltmeyle SÖNÜYOR mu, yoksa bir TABANA mı oturuyor?"""

    def test_kaynak_kontur_42_noktada_6_dereceye_yakin_kirik_TASIR(self):
        """Kalemin başlığı: ~6° kırık. Fikstür bunu ölçerek doğrular."""
        C = kontur_42()
        assert C.shape == (42, 2)
        assert 5.0 < kirik_derece(C) < 7.0, (
            "42 noktalı kontur ailesinin maksimum eğim kırığı ~6° olmalı; "
            "fikstür ürünün geometri sözleşmesini temsil etmiyor.")

    def test_YUVARLATMASIZ_kirik_kaynak_acida_TABANLANIYOR(self):
        """Onarım öncesi davranış (tol=0): kırık sıfıra GİTMEZ.

        İstasyonlar kaynak poligondan sıklaşınca zincir köşeyi bire bir
        kopyalar; kırık kaynak açıda durur. Kalıcı yeniden-giren köşe =
        Williams tekilliği = tepe gerilmenin ıraksaması.
        """
        C = kontur_42()
        t = np.full(C.shape[0], 0.003)
        kaynak = kirik_derece(C)
        k512, _ = istasyon_kirigi(C, t, 512, 0.0)
        k1024, _ = istasyon_kirigi(C, t, 1024, 0.0)
        assert k1024 > 0.5 * kaynak, (
            f"tol=0'da na=1024 kırığı {k1024:.3f}° — kaynak kırığın "
            f"({kaynak:.3f}°) yarısının altına inmiş görünüyor; taban "
            "iddiası bu fikstürde tutmuyor.")
        assert k1024 > 0.5 * k512 * 0.999, (
            "tol=0'da kırık inceltmeyle sönüyor görünüyor — kalemin "
            "'sabit köşe' teşhisi bu fikstürde çürük.")

    def test_YUVARLATMA_kirigi_inceltmeyle_SIFIRA_GOTURUYOR(self):
        """Onarım: kırık artık O(h) — her ikiye katlamada yarılanıyor."""
        C = kontur_42()
        t = np.full(C.shape[0], 0.003)
        tol = MA.INNER_KINK_TOL_RAD
        k = {na: istasyon_kirigi(C, t, na, tol)[0]
             for na in (256, 512, 1024, 2048)}
        assert k[2048] < k[1024] < k[512] < k[256], (
            f"kırık merdiveni monoton azalmıyor: {k}")
        assert k[2048] < 0.35 * k[256], (
            f"kırık iki mertebe inceltmede yeterince sönmüyor: {k}")

    def test_YUVARLATMA_ince_meshte_kaynak_kontura_gore_KAT_KAT_DUZ(self):
        """Aynı mesh'te onarımlı zincir, onarımsızdan belirgin daha düz."""
        C = kontur_42()
        t = np.full(C.shape[0], 0.003)
        ham, _ = istasyon_kirigi(C, t, 1024, 0.0)
        yuv, _ = istasyon_kirigi(C, t, 1024, MA.INNER_KINK_TOL_RAD)
        assert yuv < 0.5 * ham, (
            f"na=1024'te kırık {ham:.3f}° → {yuv:.3f}°; onarım kırığı "
            "yarıya bile indirmiyor.")


class TestOHD2528YuvarlatmaGeometrisi:
    """Yuvarlatma UYDURMA geometri değil, eğrinin yeniden kurulmasıdır."""

    def test_RAO_YAYI_BIRE_BIR_geri_gelir(self):
        """Çember üzerindeki üç nokta için çevrel yarıçap TAM yarıçaptır.

        Rao boğaz yayı tanım gereği dairedir; yuvarlatma onu çemberin
        üstüne geri koymalıdır (uydurma bir eğri üretmemelidir).
        """
        Rn, rt = 0.00382, 0.010
        a = np.radians(np.linspace(0.0, 15.0, 15))
        C = np.stack([Rn * np.sin(a), rt + Rn * (1.0 - np.cos(a))], axis=1)
        Q, _, rap = MA.ic_kose_yuvarlatma(C, np.full(C.shape[0], 0.003))
        sapma = np.abs(np.hypot(Q[:, 0], Q[:, 1] - (rt + Rn)) - Rn)
        assert float(np.max(sapma)) < 1e-6, (
            f"yuvarlatılmış yay çemberden {np.max(sapma):.3e} m sapıyor — "
            "çevrel çember yeniden kurulumu bozuk.")
        assert rap["kalan_kirik_maks_derece"] <= np.degrees(
            MA.INNER_KINK_TOL_RAD) * (1.0 + 1e-6)

    def test_DUZ_kontur_BIT_AYNI_kalir(self):
        """Kırıksız kontura dokunulmaz (gereksiz nokta üretilmez)."""
        L = np.stack([np.linspace(0.0, 1.0, 7),
                      np.linspace(0.01, 0.02, 7)], axis=1)
        Q, tQ, rap = MA.ic_kose_yuvarlatma(L, np.full(7, 0.002))
        assert np.array_equal(Q, L)
        assert rap["yuvarlatilan_kose"] == 0
        assert rap["eklenen_nokta"] == 0

    def test_TOL_SIFIR_onarim_oncesi_davranisla_BIT_OZDES(self):
        """tol=0 → kontur aynen döner; eski çağrılar bit-özdeş kalır."""
        C = kontur_42()
        t = np.full(C.shape[0], 0.003)
        Q, tQ, rap = MA.ic_kose_yuvarlatma(C, t, 0.0)
        assert np.array_equal(Q, C) and np.array_equal(tQ, t)
        assert rap["aktif"] is False
        m0 = MA.build_wall_mesh(C, t, n_axial=64, n_radial=4,
                                inner_kink_tol_rad=0.0)
        assert m0.meta["ic_kose_yuvarlatma"]["aktif"] is False

    def test_kalan_kirik_TOLERANSIN_ALTINDA(self):
        """Onarımın kendi vaadi: kalan kırık ≤ tolerans."""
        C = kontur_42()
        Q, _, rap = MA.ic_kose_yuvarlatma(C, np.full(C.shape[0], 0.003))
        assert rap["aktif"] is True
        assert rap["ham_kirik_maks_derece"] > 5.0
        assert kirik_derece(Q) <= np.degrees(MA.INNER_KINK_TOL_RAD) * 1.001, (
            f"kalan kırık {kirik_derece(Q):.4f}° > tolerans "
            f"{np.degrees(MA.INNER_KINK_TOL_RAD):.4f}°")
        assert rap["kalan_kirik_sayisi_tol_ustu"] == 0


class TestOHD2528TekKaynakVeBeyan:
    def test_TOLERANS_TEK_KAYNAKTAN_turer(self):
        """Eşik uydurulmaz: OUTER_FLOOR_SAMPLE_TOL / güvenlik katı."""
        assert MA.INNER_KINK_TOL_RAD == pytest.approx(
            MA.OUTER_FLOOR_SAMPLE_TOL / MA.INNER_KINK_GUVENLIK_KATI, rel=1e-12)
        assert MA.INNER_KINK_GUVENLIK_KATI >= 10.0
        assert 0.0 < MA.INNER_KINK_FILLET_CHORD_ORANI < 0.5, (
            "teğet boyu komşu kirişin yarısını aşarsa iki köşenin yayları "
            "çakışır; oran 0,5'in ALTINDA olmalı.")

    def test_KAPALIYKEN_kiriklar_YINE_DE_OLCULUYOR(self):
        """Taban KAPATILDIĞINDA bile meta kırığı ÖLÇER — 'kırık yok' iddiası
        hiçbir koşulda yapılmaz (sessiz varsayım yasağı).

        ÇEVRİLDİ (OH-D25-28 / OH-D24-01, ÖH D27 a1). Bu bekçi D26 a2'de
        ``INNER_KINK_VARSAYILAN_TOL_RAD == 0.0`` diye başlıyordu; o satır
        onarımın YARIM kalmışlığını KİLİTLİYORDU (kusuru koruyan bekçi).
        D27 a1'de varsayılan ürün akışına açıldı — 13 mevcut bekçi tek tek
        yargılandı, ölçüm docs/scofield/raw/OH/D27/fea-cfd/a1/. Bekçinin
        ASIL iddiası (kapalı kipte bile ham kırık ölçülüp yayımlanır)
        DEĞİŞMEDİ ve burada tol açıkça 0 verilerek sınanıyor; varsayılanın
        AÇIK olduğu ayrıca tests/test_d27_fea_cfd_a1.py'de kilitlidir.
        """
        assert MA.INNER_KINK_VARSAYILAN_TOL_RAD == MA.INNER_KINK_TOL_RAD
        C = kontur_42()
        m = MA.build_wall_mesh(C, np.full(C.shape[0], 0.003),
                               n_axial=64, n_radial=4,
                               inner_kink_tol_rad=0.0)
        ik = m.meta["ic_kose_yuvarlatma"]
        assert ik["aktif"] is False
        assert ik["ham_kirik_maks_derece"] > 5.0, (
            "taban kapalıyken de ham kırık ÖLÇÜLÜP yayımlanmalı")
        assert ik["ham_kirik_sayisi_tol_ustu"] == 0, (
            "tol=0'da 'tol üstü kırık' sayımı anlamsızdır, 0 olmalı")

    def test_MESH_META_olcumu_YAYIMLIYOR(self):
        C = kontur_42()
        m = MA.build_wall_mesh(C, np.full(C.shape[0], 0.003),
                               n_axial=64, n_radial=4,
                               inner_kink_tol_rad=MA.INNER_KINK_TOL_RAD)
        ik = m.meta["ic_kose_yuvarlatma"]
        for alan in ("aktif", "tol_rad", "tol_derece", "tol_kaynagi",
                     "ham_kirik_maks_derece", "kalan_kirik_maks_derece",
                     "yuvarlatilan_kose", "yuvarlatilamayan_kose",
                     "eklenen_nokta", "maks_sapma_m", "_basis"):
            assert alan in ik, f"meta['ic_kose_yuvarlatma']['{alan}'] yok"
        assert ik["aktif"] is True
        assert ik["yuvarlatilan_kose"] > 0
        assert ik["ham_kirik_maks_derece"] > ik["kalan_kirik_maks_derece"]
        assert "Williams" in ik["_basis"]

    def test_BEYAN_C0_DEGIL_G1_iddiasi_tasir(self):
        """Onarım TEĞET sürekliliğidir; konum hatası aynı mertebede kalır.

        Ölçüldü (kirik_tabani.json, hibrit; yoğun analitik referansın
        poligona Hausdorff uzaklığı): ham maks 3,5266e-5 m ⟷ yuvarlatılmış
        maks 3,5266e-5 m (aynı), ortalama 8,92e-6 → 1,22e-5 m. Yani
        yuvarlatma konumu İYİLEŞTİRMEZ; kırığı kaldırır. Beyan bunu
        söylemeli, "geometri daha doğru oldu" DEMEMELİ.
        """
        C = kontur_42()
        m = MA.build_wall_mesh(C, np.full(C.shape[0], 0.003),
                               n_axial=64, n_radial=4,
                               inner_kink_tol_rad=MA.INNER_KINK_TOL_RAD)
        b = m.meta["ic_kose_yuvarlatma"]["_basis"]
        assert "teğet" in b.lower() or "G1" in b
        assert "sagitta" in b.lower(), (
            "beyan, iç yüzeyin ne kadar oynadığını (sagitta) adıyla "
            "söylemeli — sessiz geometri değişikliği yok.")

    def test_SAPMA_cidarin_kucuk_bir_payi(self):
        """Yayın köşeden geri çekilmesi cidar kalınlığının yanında küçük."""
        C = kontur_42()
        t = 0.003
        m = MA.build_wall_mesh(C, np.full(C.shape[0], t),
                               n_axial=64, n_radial=4,
                               inner_kink_tol_rad=MA.INNER_KINK_TOL_RAD)
        sapma = m.meta["ic_kose_yuvarlatma"]["maks_sapma_m"]
        assert 0.0 < sapma < 0.05 * t, (
            f"iç yüzey {sapma:.3e} m oynadı; cidarın (%{100 * sapma / t:.1f}) "
            "%5'inden fazlası — bu artık pürüzsüzleştirme değil geometri "
            "değişikliğidir.")


class TestOHD2401KalanFailClosed:
    """Ham kontur ince mesh'te kapamayı KIRIYORDU; onarım bunu kaldırır."""

    def test_HAM_kontur_ince_meshte_kapamayi_kiriyor_YUVARLATILMIS_kirmiyor(self):
        C = kontur_42()
        t = np.full(C.shape[0], 0.003)
        with pytest.raises(ValueError):
            MA.build_wall_mesh(C, t, n_axial=2048, n_radial=4,
                               inner_kink_tol_rad=0.0)
        m = MA.build_wall_mesh(C, t, n_axial=2048, n_radial=4,
                               inner_kink_tol_rad=MA.INNER_KINK_TOL_RAD)
        assert m.n_axial == 2048

    def test_inner_kink_tol_rad_FAIL_CLOSED_dogrulanir(self):
        C = kontur_42()
        t = np.full(C.shape[0], 0.003)
        for kotu in (-1.0, float("nan"), float("inf")):
            with pytest.raises(ValueError):
                MA.build_wall_mesh(C, t, n_axial=32, n_radial=4,
                                   inner_kink_tol_rad=kotu)


class TestSCLLineerlestirmeCebri:
    """OH-D25-28'in ikinci ayağı: SCL lineerleştirme cebri (biçimsel).

    Lean kaynağı: docs/scofield/raw/OH/D26/fea-cfd/a2/HRMASCL.lean
    (bu aşamada makine ile doğrulanamadı — gerekçe rapor.md §Lean).
    Aşağıdaki bekçiler AYNI üç önermeyi ÜRÜN KODU üzerinde sınar:

      (1) σ_m = (1/t)∫σ dx,  σ_b = (6/t²)∫σ(t/2−x) dx  lineer alanda TAM
          geri verir: uçlarda σ_m ∓ σ_b = σ(0), σ(t).
      (2) |σ_m| ≤ (1/t)·‖σ‖₁ ve |σ_b| ≤ (3/t)·‖σ‖₁ — lineerleştirme
          L¹ ile SINIRLIDIR, sup ile DEĞİL.
      (3) (2)'nin sonucu: integrallenebilir bir tekillik (Williams: σ ~
          r^{λ−1}, λ ∈ (0,1)) sup'u ıraksatır ama SCL çıktısını ıraksatmaz.
          Hükmün ham tepeden DEĞİL SCL'den alınmasının cebirsel gerekçesi
          budur (ÖLÇÜLDÜ: katı motorda ham tepe 188 → 243 MPa ıraksarken
          hüküm büyüklüğü 190 → 196 MPa'da duruyor).
    """

    @staticmethod
    def _lineerlestir(sigma, x):
        """Ürün kodunun tam aynı iki integrali (segment içi lineer, tam
        moment) — scl_lineerlestirme'nin skaler karşılığı."""
        h = np.diff(x)
        s0, s1 = sigma[:-1], sigma[1:]
        t = float(x[-1] - x[0])
        i_sigma = h * (s0 + s1) / 2.0
        i_sigma_s = (h ** 2) * (s0 / 6.0 + s1 / 3.0)
        c_eksi_x0 = (t / 2.0 - x[:-1])
        s_m = float(np.sum(i_sigma)) / t
        s_b = 6.0 / (t ** 2) * float(np.sum(c_eksi_x0 * i_sigma - i_sigma_s))
        return s_m, s_b, t

    def test_LINEER_alanda_TAM_geri_verir(self):
        x = np.linspace(0.0, 0.004, 9)
        a, b = 3.0e7, -2.5e9
        s_m, s_b, t = self._lineerlestir(a + b * x, x)
        assert s_m == pytest.approx(a + b * t / 2.0, rel=1e-12)
        assert s_b == pytest.approx(-b * t / 2.0, rel=1e-12)
        assert s_m + s_b == pytest.approx(a, rel=1e-10)
        assert s_m - s_b == pytest.approx(a + b * t, rel=1e-10)

    def test_L1_SINIRI_tutar(self):
        rng = np.random.default_rng(20260907)
        x = np.linspace(0.0, 0.003, 33)
        for _ in range(40):
            sig = rng.normal(0.0, 1.0e8, x.size)
            s_m, s_b, t = self._lineerlestir(sig, x)
            L1 = float(_trapezoid(np.abs(sig), x))
            assert abs(s_m) <= L1 / t * (1.0 + 1e-9)
            assert abs(s_b) <= 3.0 * L1 / t * (1.0 + 1e-9)

    def test_INTEGRALLENEBILIR_TEKILLIK_supu_iraksatir_SCLyi_IRAKSATMAZ(self):
        """σ ~ x^(λ−1), λ = 0,88 (ölçülen p ≈ 0,12'nin karşılığı)."""
        t = 0.003
        lam = 0.88
        sup_, scl_ = [], []
        for n in (64, 256, 1024, 4096):
            x = np.linspace(0.0, t, n + 1)
            xs = np.where(x > 0, x, x[1] * 1e-6)
            sig = 1.0e6 * (t / xs) ** (1.0 - lam)
            s_m, s_b, _ = self._lineerlestir(sig, x)
            sup_.append(float(np.max(sig)))
            scl_.append(abs(s_m) + abs(s_b))
        # Kuram: en ince örnek x₁ = t/n olduğundan sup ∝ n^(1−λ);
        # n 64 → 4096 (64 kat) için beklenen büyüme 64^0,12 = 1,6476.
        beklenen = 64.0 ** (1.0 - lam)
        assert sup_[-1] / sup_[0] == pytest.approx(beklenen, rel=0.02), (
            f"sup büyümesi {sup_[-1] / sup_[0]:.4f}, kuram {beklenen:.4f} — "
            "fikstür Williams tekilliğini temsil etmiyor.")
        assert sup_[-1] > sup_[0] and sup_[0] > 0.0
        assert scl_[-1] / scl_[0] < 1.02, (
            f"SCL çıktısı da ıraksıyor ({scl_[0]:.6e} → {scl_[-1]:.6e}); "
            "L¹ sınırı bu fikstürde tutmuyor.")

    def test_URUN_SCLsi_lineer_alanda_TAM_geri_verir(self):
        """(1)'in ürün kodundaki karşılığı — scl_lineerlestirme'nin kendisi."""
        C = np.stack([np.linspace(0.0, 0.2, 9), np.full(9, 0.05)], axis=1)
        m = MA.build_wall_mesh(C, np.full(9, 0.004), n_axial=8, n_radial=4,
                               inner_kink_tol_rad=MA.INNER_KINK_TOL_RAD)
        nodes = m.nodes
        r0 = float(np.min(nodes[:, 1]))
        # σ_θθ cidar boyunca LİNEER; diğer bileşenler sıfır.
        S = np.zeros((nodes.shape[0], 4))
        S[:, 2] = 1.0e8 + 5.0e9 * (nodes[:, 1] - r0)
        P_m, P_LPb, beyan = SA.scl_lineerlestirme(m, S)
        assert beyan["gecerli"] is True
        t = 0.004
        bekle_m = 1.0e8 + 5.0e9 * t / 2.0
        bekle_uc = max(abs(1.0e8), abs(1.0e8 + 5.0e9 * t))
        assert float(np.nanmax(P_m)) == pytest.approx(bekle_m, rel=1e-6)
        assert float(np.nanmax(P_LPb)) == pytest.approx(bekle_uc, rel=1e-6)
