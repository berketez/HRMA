"""ÖH Dalga-27 · fea-cfd · aşama 1 bekçileri — OH-D25-28 + OH-D24-01 (kalan).

ÇİFT KALEM, TEK ONARIM. D26 a2'de iç kontur köşe tabanı
(``mesh_axisym.ic_kose_yuvarlatma``) kuruldu, ölçüldü ve bekçilendi ama
**ürün varsayılanı yapılmadı**: açmak 13 mevcut bekçiyi oynatıyordu ve
gerekçesiz çevirmek yasaktı. D27 a1'in TEK işi budur:

1. ``INNER_KINK_VARSAYILAN_TOL_RAD = INNER_KINK_TOL_RAD`` — taban ÜRÜN
   AKIŞINA girdi.
2. 13 bekçinin **tek tek** yargısı (rapor §3 tablosu): 4'ü ham öteleme/
   kapama operatörünü sınadığı için ``inner_kink_tol_rad=0`` ile YALITILDI,
   5'i sayı çapasıydı ve türetim/yön ilişkisine çevrildi, 4'ü ürünün
   İYİLEŞMESİNİ ölçtü ve fail-closed bağa bağlandı. Hiçbiri gerekçesiz
   çevrilmedi, hiçbir eşik BÜYÜTÜLMEDİ.
3. Sapmanın **a-priori üst sınırı** türetildi ve yayımlandı; yuvarlatılamayan
   köşe ``taban_saglandi`` bayrağıyla fail-closed duyuruluyor.
4. Yoğun kontur/kapama **maliyeti** ölçüldü: kontur 42 → 1738 nokta, mesh
   kurma 0,0092 → 0,0138 s, ELEMAN VE DÜĞÜM SAYISI DEĞİŞMİYOR.

Ölçüm kanıtı: docs/scofield/raw/OH/D27/fea-cfd/a1/{once_a1,sonra_a1}.json —
üreteç ``olcum_a1.py``; ters-mutasyon ``mutasyon_a1.py`` → ``mutasyon_a1.json``.

TÜRETİM (sapmanın kapalı biçimi). Bir köşede dönüş açısı θ, komşu kirişler a
ve b, teğet boyu T = min(R·tan(θ/2), κ·min(a,b)) ve yay yarıçapı ρ = T/tan(θ/2)
olmak üzere yayın köşeden geri çekilmesi (sagitta)

    sapma = ρ·(sec(θ/2) − 1) = T·(1 − cos(θ/2))/sin(θ/2) = T·tan(θ/4)

(yarım açı özdeşliği tan(x/2) = (1 − cos x)/sin x). Buradan iki bağ çıkar:

  (a) A-PRİORİ ÜST SINIR:  sapma ≤ κ·min(a,b)·tan(θ/4).
  (b) DÜRÜSTLÜK ORANI: poligonun KENDİ dönüş hızının ima ettiği çember yayı,
      min(a,b) kirişi üzerinde s_ark = (min(a,b)/2)·tan(θ/4) kadar şişer;
      dolayısıyla sapma/s_ark ≤ 2κ = 0,90. Yani yuvarlatma iç yüzeyi, "bu
      köşe pürüzsüz bir eğrinin örneği olsaydı eğri zaten bu kadar şişerdi"
      sınırının ÖTESİNE taşımaz.

BOYUT ANALİZİ: θ ve tol saf açı (radyan, boyutsuz); T, ρ, min(a,b), sapma
[m]. sapma = T·tan(θ/4) → [m]·[1] = [m]. Oran sapma/s_ark boyutsuz. Tutar.

LİTERATÜR: M. L. Williams, "Stress singularities resulting from various
boundary conditions in angular corners of plates in extension", J. Appl.
Mech. 19 (1952) 526-528 — yeniden-giren köşede σ ~ r^(λ−1); köşe kalkınca
tekillik de kalkar. ASME BPVC VIII-2 Bölüm 5 / Tablo 5.6: TEPE (F) bileşeni
plastik çökme hükmünden dışlanır (hüküm büyüklüğü P_L+P_b'dir).
"""
import contextlib
import io

import numpy as np
import pytest

from hrma.fea import mesh_axisym as MA
from hrma.fea import structural_axisym as SA


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **k)


# ---------------------------------------------------------------------------
# Fikstürler
# ---------------------------------------------------------------------------
#: D26 a2'nin sentetik kontur ailesi — ürünün ``sample_nozzle_inner_contour``
#: sözleşmesiyle birebir yapıda (kosinüs konverjan 27 + Rao yayı 14 + koni 1).
def kontur_42(rc=0.0624, rt=0.0165, re=0.0466, yari_aci_deg=15.0,
              n_conv=27, n_arc=14):
    conv_aci = np.radians(30.0)
    L_conv = (rc - rt) / np.tan(conv_aci)
    Rn = 0.382 * rt
    theta = np.radians(yari_aci_deg)
    pts = []
    for i in range(n_conv):
        s = i / (n_conv - 1)
        pts.append((L_conv * s,
                    rt + (rc - rt) * (0.5 + 0.5 * np.cos(np.pi * s))))
    arc_z, arc_r = L_conv, rt
    for i in range(1, n_arc + 1):
        a = theta * i / n_arc
        arc_z = L_conv + Rn * np.sin(a)
        arc_r = rt + Rn * (1.0 - np.cos(a))
        pts.append((arc_z, arc_r))
    pts.append((arc_z + (re - arc_r) / np.tan(theta), re))
    return np.asarray(pts, dtype=float)


#: tests/test_mesh_disyuzey_egrilik_tabani.py'nin sentetik V vadisi.
V_KONTUR = np.array([(0.0, 0.030), (0.040, 0.030), (0.060, 0.020),
                     (0.080, 0.030), (0.120, 0.030)])
V_T = 0.004


@pytest.fixture(scope='module')
def motorlar():
    """Katı ve hibrit örnek motorların yapısal köprü çıktıları (bir kez)."""
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
        from hrma.fea import bridge
    app.config['TESTING'] = True
    c = app.test_client()
    istek = {
        'kati': ('/calculate_solid', {
            'motor_name': 'D27FEA-KATI', 'propellant_type': 'apcp',
            'grain_type': 'bates', 'chamber_pressure': 40.0,
            'thrust': 5000.0, 'burn_time': 3.0, 'chamber_diameter': 100.0,
            'grain_length': 500.0, 'core_diameter': 30.0,
            'expansion_ratio': 8.0}),
        'hibrit': ('/calculate', {
            'motor_name': 'D27FEA-HIBRIT', 'thrust': 2000.0,
            'chamber_pressure': 30.0, 'burn_time': 10.0,
            'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
            'of_ratio': 6.0, 'expansion_ratio': 8.0,
            # Ölçüm koşulu AÇIKÇA (ana model, 14 Eki; dört koşul): hibrit
            # çapaları malzemesiz gövdede API'nin eski örtük varsayılanı
            # steel_4130 ile donduruldu; HB10 (hibrit 10. tur) tek
            # varsayılanı steel_304 yaptı. Çapa aynı koşulu ölçmeye devam
            # eder; bağımsız teyit (sabit 1024×16 ağ) aynen canlı.
            'chamber_material': 'steel_4130',
            # V3.0.5 T-ÇAPA-C1 — ÖLÇÜM KOŞULU AÇIKÇA (beşinci ve altıncı
            # koşul): c* verimi %100 ve cidar 13,1278 mm. V301/H-termal
            # (77d64c641, 26 Eki) korunan bölgeler yüzünden boyutlandırılan
            # hibrit cidarını inceltti (hibrit min SF 38,45 → 5,30), V301/
            # H-PANEL (74b55500a) N2O/HTPB c*'ına kaynaklı η=0,89 getirdi;
            # ikisi de onaylı yayımlanan sayı değişimi, çapanın konusu FEA
            # yakınsama bandı. Bu iki alanla köprü girdisi (cidar
            # 0,013127827075655596 m, kontur toplamı 1,1219162663557958)
            # H-termal öncesi c7776576f ağacının isteğiyle BİT-AYNI (ölçüldü).
            'combustion_efficiency': 100.0,
            'wall_thickness': 13.127827075655596}),
    }
    cikti = {}
    for ad, (yol, yuk) in istek.items():
        veri = _sessiz(c.post, yol, json=yuk).get_json() or {}
        md = veri.get('motor', veri)
        cikti[ad] = {
            'motor': md,
            'girdi': _sessiz(bridge.extract_structural_inputs, md),
            'kopru': _sessiz(bridge.run_structural_from_motor, md),
        }
    return cikti


# ===========================================================================
# 1) VARSAYILAN AÇILDI — kalemin kendisi
# ===========================================================================
class TestD27VarsayilanACIK:

    def test_URUN_VARSAYILANI_tabanla_AYNI_ve_tek_kaynak(self):
        """Varsayılan artık 0 değil; ölçütle BİREBİR aynı sabitten gelir."""
        assert MA.INNER_KINK_VARSAYILAN_TOL_RAD == MA.INNER_KINK_TOL_RAD
        assert MA.INNER_KINK_VARSAYILAN_TOL_RAD > 0.0
        # Tek kaynak: ölçüt hâlâ türetilmiş, elle yazılmış değil.
        assert MA.INNER_KINK_TOL_RAD == pytest.approx(
            MA.OUTER_FLOOR_SAMPLE_TOL / MA.INNER_KINK_GUVENLIK_KATI,
            rel=1e-15)

    def test_IMZA_varsayilani_da_ACIK(self):
        """``build_wall_mesh`` imzasındaki varsayılan sabitle aynı olmalı.

        İmzadaki varsayılan Python'da tanım anında dondurulur; sabiti
        değiştirip imzayı unutmak sessiz bir kusurdur.
        """
        assert MA.build_wall_mesh.__defaults__[-1] == \
            MA.INNER_KINK_VARSAYILAN_TOL_RAD

    def test_KWARG_VERILMEDEN_kurulan_mesh_TABANI_UYGULUYOR(self):
        """Ürün akışı (kwarg yok) tabanı gerçekten uyguluyor mu?"""
        C = kontur_42()
        m = MA.build_wall_mesh(C, 0.003, n_axial=64, n_radial=4)
        y = m.meta['ic_kose_yuvarlatma']
        assert y['aktif'] is True
        assert y['tol_rad'] == MA.INNER_KINK_TOL_RAD
        assert y['yuvarlatilan_kose'] > 0
        assert y['kalan_kirik_maks_derece'] < 0.06
        assert y['ham_kirik_maks_derece'] > 5.0
        assert y['taban_saglandi'] is True

    def test_KAPATILABILIR_ve_kapaliyken_KIRIKLAR_YINE_OLCULUYOR(self):
        """0 verilince taban kapanır; "kırık yok" iddiası ASLA yapılmaz."""
        C = kontur_42()
        m = MA.build_wall_mesh(C, 0.003, n_axial=64, n_radial=4,
                               inner_kink_tol_rad=0.0)
        y = m.meta['ic_kose_yuvarlatma']
        assert y['aktif'] is False
        assert y['ham_kirik_maks_derece'] > 5.0
        assert y['kalan_kirik_maks_derece'] == pytest.approx(
            y['ham_kirik_maks_derece'], rel=1e-15)
        assert y['taban_saglandi'] is False


# ===========================================================================
# 2) SAPMANIN A-PRİORİ SINIRI — türetim, uydurma değil
# ===========================================================================
class TestD27SapmaUstSiniri:

    @pytest.mark.parametrize('C,t', [(kontur_42(), 0.003), (V_KONTUR, V_T)])
    def test_OLCULEN_SAPMA_apriori_siniri_ASMAZ(self, C, t):
        n = np.asarray(C).shape[0]
        _, _, y = MA.ic_kose_yuvarlatma(np.asarray(C, dtype=float),
                                        np.full(n, t),
                                        MA.INNER_KINK_TOL_RAD)
        assert y['maks_sapma_m'] > 0.0
        assert y['maks_sapma_m'] <= y['sapma_ust_sinir_m'] * (1.0 + 1e-12), (
            f"ölçülen sapma a-priori sınırı aştı: {y['maks_sapma_m']} > "
            f"{y['sapma_ust_sinir_m']}")

    @pytest.mark.parametrize('C,t', [(kontur_42(), 0.003), (V_KONTUR, V_T)])
    def test_ARK_ORANI_TAVANI_asilmaz_ve_TEK_KAYNAKTAN(self, C, t):
        """sapma/s_ark ≤ 2κ — yuvarlatma poligonun kendi şişmesini aşmaz."""
        n = np.asarray(C).shape[0]
        _, _, y = MA.ic_kose_yuvarlatma(np.asarray(C, dtype=float),
                                        np.full(n, t),
                                        MA.INNER_KINK_TOL_RAD)
        tavan = y['sapma_ark_orani_tavani']
        assert tavan == pytest.approx(
            2.0 * MA.INNER_KINK_FILLET_CHORD_ORANI, rel=1e-15)
        assert tavan < 1.0, (
            'tavan 1,0"in altında olmalı: yuvarlatma poligonun kendi dönüş '
            'hızının ima ettiği yaydan DAHA ÇOK şişemez')
        assert y['sapma_ark_orani_maks'] <= tavan * (1.0 + 1e-12), (
            f"{y['sapma_ark_orani_maks']} > {tavan}")

    def test_KAPALI_BICIM_sapma_esittir_T_carpi_tan_ceyrek(self):
        """sapma = T·tan(θ/4) özdeşliği tek köşede sayıyla doğrulanır.

        V vadisinde teğet KIRPILIR (T = κ·min(a,b)), yani ölçülen sapma
        a-priori sınırla TAM eşit olmalıdır — özdeşliğin en dar sınaması.
        """
        _, _, y = MA.ic_kose_yuvarlatma(V_KONTUR, np.full(5, V_T),
                                        MA.INNER_KINK_TOL_RAD)
        a = float(np.hypot(*(V_KONTUR[2] - V_KONTUR[1])))
        b = float(np.hypot(*(V_KONTUR[3] - V_KONTUR[2])))
        theta = float(MA.polyline_donus_acilari(V_KONTUR)[1])
        T = MA.INNER_KINK_FILLET_CHORD_ORANI * min(a, b)
        beklenen = T * np.tan(0.25 * theta)
        assert y['maks_sapma_m'] == pytest.approx(beklenen, rel=1e-12)
        assert y['sapma_ust_sinir_m'] == pytest.approx(beklenen, rel=1e-12)
        # Bu vakada oran tavana OTURUR (kırpma etkin) — sınır dar.
        assert y['sapma_ark_orani_maks'] == pytest.approx(
            y['sapma_ark_orani_tavani'], rel=1e-12)


# ===========================================================================
# 3) YUVARLATILAMAYAN KÖŞE — fail-closed sayacı (D27 hükmü)
# ===========================================================================
class TestD27YuvarlatilamayanKose:

    def test_URUN_MOTORLARINDA_yuvarlatilamayan_kose_YOK(self, motorlar):
        """Katı ve hibritte sayaç 0 ve taban_saglandi True — ölçülür."""
        for ad in ('kati', 'hibrit'):
            g = motorlar[ad]['girdi']
            assert g['status'] == 'ok', g.get('reason')
            C = np.asarray(g['contour'], dtype=float)
            t = np.atleast_1d(np.asarray(g['thickness_m'], dtype=float))
            if t.size == 1:
                t = np.full(C.shape[0], float(t[0]))
            _, _, y = MA.ic_kose_yuvarlatma(C, t, MA.INNER_KINK_TOL_RAD)
            assert y['yuvarlatilamayan_kose'] == 0, (ad, y)
            assert y['kalan_kirik_sayisi_tol_ustu'] == 0, (ad, y)
            assert y['taban_saglandi'] is True, (ad, y)

    def test_YUVARLATILAMAYAN_kose_SESSIZCE_atlanmaz(self):
        """Yuvarlanamayan köşe SAYILIR ve bayrağı FALSE'a çeker.

        Geri dönen (z'si AZALAN) bir köşede yay z-tekdüzeliğini bozar;
        operatör o köşeyi atlamak ZORUNDADIR — ama sessizce değil. Böyle
        bir kontur ``build_wall_mesh`` sözleşmesine zaten aykırıdır; bekçi
        operatörün o vakada da SAYARAK ilerlediğini sınar (savunma katmanı).
        """
        C = np.array([(0.0, 0.030), (0.020, 0.030), (0.019, 0.050),
                      (0.040, 0.050)])
        _, _, y = MA.ic_kose_yuvarlatma(C, np.full(4, 0.002),
                                        MA.INNER_KINK_TOL_RAD)
        assert y['aktif'] is True
        assert y['yuvarlatilamayan_kose'] >= 1, y
        assert y['kalan_kirik_sayisi_tol_ustu'] >= 1, y
        assert y['taban_saglandi'] is False, (
            'yuvarlanamayan köşe varken taban SAĞLANDI denemez')
        # Nokta SİLİNMEZ: atlanan köşe konturda ham hâliyle durur.
        Q, _, _ = MA.ic_kose_yuvarlatma(C, np.full(4, 0.002),
                                        MA.INNER_KINK_TOL_RAD)
        assert np.min(np.hypot(Q[:, 0] - C[2, 0],
                               Q[:, 1] - C[2, 1])) < 1e-15

    def test_TOL_USTU_KALAN_KIRIK_bayragi_dusurur(self):
        """Köşe yuvarlansa BİLE kalan kırık tolerans üstündeyse bayrak düşer.

        Ayrık bir vaka: hiçbir köşe atlanmıyor (sayaç 0) ama çok yakın iki
        köşenin yayları arasında kalan kırık toleransın bir tık üstünde
        kalıyor. Bayrak yalnız 'atlandı mı' sorusuna değil, ÖLÇÜLEN kalan
        kırığa da bakmalı.
        """
        C = np.array([(0.0, 0.030), (0.020, 0.032), (0.0200001, 0.050),
                      (0.0200002, 0.032), (0.040, 0.030)])
        _, _, y = MA.ic_kose_yuvarlatma(C, np.full(5, 0.002),
                                        MA.INNER_KINK_TOL_RAD)
        assert y['yuvarlatilamayan_kose'] == 0, y
        assert y['kalan_kirik_maks_derece'] > y['tol_derece']
        assert y['kalan_kirik_sayisi_tol_ustu'] >= 1
        assert y['taban_saglandi'] is False


# ===========================================================================
# 4) ÇEVRİLEN BEKÇİLERİN ÜRÜN-YOLU KARŞILIKLARI (kapsam DARALMADI)
# ===========================================================================
class TestD27IcKoseTabaniVarsayilan:
    """tests/test_mesh_disyuzey_egrilik_tabani.py'de tol=0 ile yalıtılan
    dört bekçinin ürün varsayılanındaki karşılıkları."""

    def test_IC_YUZEY_yuvarlatilmis_kontur_UZERINDE_kalir(self):
        """İç düğümler HAM poligonda değil, YUVARLATILMIŞ eğri üzerinde."""
        Q, _, y = MA.ic_kose_yuvarlatma(V_KONTUR, np.full(5, V_T),
                                        MA.INNER_KINK_TOL_RAD)
        m = MA.build_wall_mesh(V_KONTUR, V_T, 64, 4)
        ic = m.nodes[m.inner_nodes]
        # Yuvarlatılmış zincir z'de tek değerli — enterpolasyonla kıyaslanır.
        np.testing.assert_allclose(
            ic[:, 1], np.interp(ic[:, 0], Q[:, 0], Q[:, 1]),
            rtol=0.0, atol=1e-9)
        # ... ve HAM poligondan sapma türetilmiş sınırın İÇİNDE.
        ham = np.interp(ic[:, 0], V_KONTUR[:, 0], V_KONTUR[:, 1])
        assert float(np.max(np.abs(ic[:, 1] - ham))) <= \
            y['sapma_ust_sinir_m'] * (1.0 + 1e-9)

    def test_KAPAMA_artik_KOPRU_kurmak_ZORUNDA_kalmiyor(self):
        """Köşe yuvarlanınca dış kapamanın uydurma kalınlaşması KALKAR.

        Kapamanın eklediği malzeme tasarımda YOKTUR ve cidarı olduğundan
        kalın gösterir (iyimser yön). Taban açıkken V vadisinde bu ek
        tamamen düşüyor — ölçülür, iddia edilmez.
        """
        kapali = MA.build_wall_mesh(V_KONTUR, V_T, 64, 4,
                                    inner_kink_tol_rad=0.0)
        acik = MA.build_wall_mesh(V_KONTUR, V_T, 64, 4)
        tk = kapali.meta['dis_yuzey_egrilik_tabani']
        ta = acik.meta['dis_yuzey_egrilik_tabani']
        assert tk['kalinlik_maks_m'] > V_T + 1e-5
        assert ta['kalinlik_maks_m'] < tk['kalinlik_maks_m'], (
            f"{ta['kalinlik_maks_m']} >= {tk['kalinlik_maks_m']}")
        assert ta['kalinlik_maks_m'] == pytest.approx(V_T, rel=1e-6)

    def test_HAM_OTELEME_dejenerasyonu_TABAN_ACIKKEN_DOGMUYOR(self):
        """tol=0'da ValueError atan tur, taban açıkken sorunsuz kurulur."""
        with pytest.raises(ValueError, match='ters dönmüş|dejenere'):
            MA.build_wall_mesh(V_KONTUR, V_T, 64, 4,
                               outer_curvature_floor=0.0,
                               inner_kink_tol_rad=0.0)
        m = MA.build_wall_mesh(V_KONTUR, V_T, 64, 4,
                               outer_curvature_floor=0.0)
        assert m.n_elems == 64 * 4


# ===========================================================================
# 5) ÜRÜN SAYILARI YENİDEN ÇAPALANDI — TÜRETİMLE
# ===========================================================================
class TestD27UrunSayilariYenidenCapalandi:
    """``min_safety_factor`` elle yazılmış bir sayıyla değil, ürünün KENDİ
    yayımladığı büyüklüklerden BİREBİR türeyerek çapalanır."""

    @staticmethod
    def _akma_pa(girdi):
        return float(getattr(girdi['material'], 'yield_strength'))

    @pytest.mark.parametrize('ad', ['kati', 'hibrit'])
    def test_min_SF_HUKUM_PAYDASINDAN_birebir_turer(self, motorlar, ad):
        k = motorlar[ad]['kopru']
        assert k['status'] == 'ok'
        akma = self._akma_pa(motorlar[ad]['girdi'])
        payda = k['scl_lineerlestirme']['hukum_paydasi_pa']
        assert k['min_safety_factor'] == pytest.approx(akma / payda,
                                                       rel=1e-12)
        assert k['tepe_emniyet_katsayisi'] == pytest.approx(
            akma / k['von_mises_nodal_max'], rel=1e-12)

    #: fea-yuk 2. tur (14 Eki 2026) bağımsız teyit ağı: ürün inceltmesi
    #: OLMADAN sabit ağ, iki kip, kötümser (fea-yuk 1. tur rapor §6 ağ
    #: merdiveni yöntemi; docs/scofield/raw/OH/V3/fea-yuk/kanit/tur2/
    #: aile_c.jsonl).
    TEYIT_AGI = (1024, 16)

    def _sabit_ag_kotumser(self, girdi):
        """Ürün köprüsünden BAĞIMSIZ ikinci yol: sabit ağda iki kip, min SF."""
        na, nr = self.TEYIT_AGI
        m = _sessiz(MA.build_wall_mesh, girdi['contour'], girdi['thickness_m'],
                    n_axial=na, n_radial=nr, offset_mode='normal')
        return min(float(_sessiz(SA.solve_pressure, m, girdi['material'],
                                 girdi['pressure_load'],
                                 axial_fix=k).min_safety_factor)
                   for k in ('z_min', 'z_max'))

    def test_KATI_min_SF_MUHAFAZAKAR_yone_gitti(self, motorlar):
        """Katı min SF — yük modeli düzeltmesinden SONRA yeniden çapalandı.

        ÇAPA GEÇMİŞİ: 1,26914 (D26) → 1,23856 (D27 §C/§G5) → 1,23282
        (B11 p1b, CEA denge dörtlüsü) → **2,59974** (fea-yuk 2. tur, 14 Eki).
        Son göç YÜK MODELİNDEN gelir (karar §28-18 (B), kart OH-DK-04):
        eski sayılar sabit-P_c iç yükünde (kapalı uç kuvveti yok) ölçülmüştü;
        o yük ıraksakta yapay bir net eksenel kuvvet doğuruyor ve ``z_max``
        kipini yapay kötümser yapıyordu (eski oran 1,82, hüküm kısıt-yeri
        gerekçesiyle geri çekiliyordu). Doğru yükte (izantropik P(x) +
        kapalı uç) oran 1,0182 ve hüküm VERİLİYOR. "Onarım iyimser yöne
        gidemez" (< 1,26914) yön çapası BU düzeltmede geçersizdir: eski
        sayı fiziksel olmayan yükün kötümser kipindendi (fea-yuk 1. tur
        rapor 'DUR' aile C). Sayı yine hükmün geldiği büyüklükten türetilir.

        BAĞIMSIZ TEYİT (dört koşul (2)): sabit 1024×16 ağda (ürün inceltmesi
        yok) iki kip, kötümser 2,59865 (ürün %0,042 uzakta); 256×8 2,60303,
        512×8 2,59939 — tekdüze yakınsıyor (kanit/tur2/aile_c.jsonl). Aynı
        teyit aşağıda CANLI koşulur. Çapa payı (abs=5e-4) DEĞİŞMEDİ.

        V3.0.5 A2 YENİDEN ÇAPA (28 Eki) — 2,59974 → **2,68470**. Docs'suz
        çatallarla ölçülen iki bilinçli ürün değişikliği (FEA çözücüsü
        değişmedi; kayma köprü girdisinden):

        1. a7ee84f3e (22 Eki, katı denetimi K-A, KT-01/02/03): kasa iç çapı
           ≥ tane dış çapı + 2·(astar + yalıtım). Bu gövdede astar 2 mm →
           kasa iç çapı 128,13 mm; boyutlandırılan cidar 2,97922 → 3,07522
           mm (+%3,22), kontur aynı. Min SF 2,599743 → 2,685823 (+%3,31;
           önceki commit ce365bdef'te 2,599743).
        2. 78a27382e (26 Eki, N-CEA-2): APCP termokimyası motorun kendi
           P_c'sinde NASA CEA'dan → lüle konturu (toplam 3,69760 → 3,71082)
           ve cidar 3,08287 mm. Min SF 2,685823 → 2,684704 (önceki commit
           77d64c641'de 2,685823).

        Bugünkü S1-6 tane yerleşimi (629977083) bu gövdeyi DEĞİŞTİRMEDİ
        (8ed2a35bc ve 629977083 sonrası aynı 2,684704). Yön: cidar
        kalınlaştığı için SF yükseldi; bu hesap iyimserleşmesi değil, kasanın
        astar payıyla büyümesinin doğal sonucu. Bağımsız teyit yeni
        geometride: sabit 1024×16 ağ, iki kip kötümseri 2,683561 (ürün
        %0,043 uzakta; a7ee84f3e'de %0,063). Hüküm VERİLİYOR, gerekçe yok.
        """
        k = motorlar['kati']['kopru']
        from tests.fea.yuk_modeli_araci import izantropik_yukte
        izantropik_yukte(k)
        akma = self._akma_pa(motorlar['kati']['girdi'])
        turetilmis = akma / k['scl_lineerlestirme']['hukum_paydasi_pa']
        assert k['min_safety_factor'] == pytest.approx(turetilmis, rel=1e-12)
        assert turetilmis == pytest.approx(2.68470, abs=5e-4), (
            f'katı min SF {turetilmis} — V3.0.5 A2 çapası 2,68470')
        teyit = self._sabit_ag_kotumser(motorlar['kati']['girdi'])
        assert abs(turetilmis - teyit) / teyit < SA.DEFAULT_REFINE_TOL, (
            f'ürün {turetilmis} ⟷ sabit ağ {teyit}: bağımsız teyit tutmuyor')
        # Hüküm VERİLİYOR: kip oranı kısıt-yeri eşiğinin altında (doğru
        # yükte kipler ayrışmıyor; eşik kapısının pozitif yakası
        # tests/test_d26_fea_cfd_a1.py'de γ'sız araçla sınanır).
        h = k['meta']['hukum']
        assert h['verildi'] is True, h['geri_cekme_gerekceleri']
        assert h['geri_cekme_gerekceleri'] == []
        # YAKINSAMA gerekçesi yok: yayımlanan kip kendi yakınsamasını kanıtladı.
        assert h['converged_yayimlanan_kip'] is True
        assert 'yayimlanan_kip_yakinsamadi' not in \
            h['geri_cekme_gerekceleri']

    def test_HIBRIT_hukum_DURUYOR_ve_capa_dar_bantta(self, motorlar):
        """Hibrit min SF çapası dar bantta — yük modeli sonrası yeniden çapa.

        ÇAPA GEÇMİŞİ: 35,50001 (D26 a2, once_a1.json §C) → **38,45093**
        (fea-yuk 2. tur, 14 Eki; karar §28-18 (B), kart OH-DK-04). Göç
        %8,3 ve YÜK MODELİNDEN gelir (eski sabit-P_c yükü, kapalı uç kuvveti
        yok); doğru yükte hüküm hazne silindirinde 1,5·P_m. Bant elle
        seçilmiyor, çözücünün kendi toleransından okunuyor (DEĞİŞMEDİ).

        BAĞIMSIZ TEYİT (dört koşul (2)): sabit 1024×16 ağda iki kip,
        kötümser 38,35388 (ürün %0,25 uzakta); 256×8 38,31962, 512×8
        38,31718 (kanit/tur2/aile_c.jsonl). Aynı teyit aşağıda CANLI koşulur.
        """
        k = motorlar['hibrit']['kopru']
        from tests.fea.yuk_modeli_araci import izantropik_yukte
        izantropik_yukte(k)
        h = k['meta']['hukum']
        # ÇEVRİLDİ — ÖH D31 fea-cfd a1 (P8B1-03 ŞARTI, Fable TOPLU
        # fea-cfd-01). Eski satır ``assert h['verildi'] is True`` idi ve
        # bu bekçinin KENDİ kapısını değil, bütün hüküm kapılarının
        # toplamını ölçüyordu. D31'de kapama tabanı payı bir hüküm
        # kapısına bağlandı (ölçüldü: hibrit payı na'dan bağımsız
        # 0,1398076 > eşik 0,10) ve hibritte hüküm ADIYLA geri çekildi.
        # Bu bekçinin iddiası DEĞİŞMEDİ: kendi gerekçesinin listede
        # OLMAMASI. Kalan gerekçe kümesi de kilitlenir ki yeni ve
        # ADSIZ bir geri çekme buraya sızmasın.
        assert set(h['geri_cekme_gerekceleri']) <= {
            'kapama_taban_payi_asildi'}, h['geri_cekme_gerekceleri']
        yeni = float(k['min_safety_factor'])
        eski = 38.45093                      # fea-yuk 2. tur (kanit/tur2/)
        assert abs(yeni - eski) / eski < SA.DEFAULT_REFINE_TOL, (
            f'hibrit min SF %{abs(yeni - eski) / eski * 100:.3f} oynadı — '
            f'inceltme toleransının (%{SA.DEFAULT_REFINE_TOL * 100:.1f}) '
            'üstünde; sayı artık yakınsama bandının dışında')
        teyit = self._sabit_ag_kotumser(motorlar['hibrit']['girdi'])
        assert abs(yeni - teyit) / teyit < SA.DEFAULT_REFINE_TOL, (
            f'ürün {yeni} ⟷ sabit ağ {teyit}: bağımsız teyit tutmuyor')


# ===========================================================================
# 6) IRAKSAMA MERDİVENİ — kalemin ASIL iddiası
# ===========================================================================
class TestD27IraksamaMerdiveni:

    def test_HAM_TEPE_tur_farki_TABAN_ACIKKEN_KUCULUYOR(self, motorlar):
        """OH-D24-01/OH-D25-28'in çekirdeği: tepe artık daha az ıraksıyor.

        Ölçüm (once_a1.json/sonra_a1.json §B, katı, tekdüze merdiven):
        64×4 → 128×8 → 256×16 → 512×32 turlarında ham tepenin tur farkı
        KAPALI %12,30 / %10,10 / %4,17, AÇIK %11,44 / %6,32 / %2,41.
        Bu bekçi bütçe gereği ilk üç basamağı koşar (son basamak 16384
        eleman); iddia AYNIDIR: en ince adımda fark KÜÇÜLMELİDİR.
        """
        g = motorlar['kati']['girdi']
        assert g['status'] == 'ok'
        fark = {}
        for tol, etiket in ((0.0, 'kapali'), (MA.INNER_KINK_TOL_RAD, 'acik')):
            tepe = []
            for (na, nr) in ((64, 4), (128, 8), (256, 16)):
                m = _sessiz(MA.build_wall_mesh, g['contour'], g['thickness_m'],
                            n_axial=na, n_radial=nr, offset_mode='normal',
                            inner_kink_tol_rad=tol)
                r = _sessiz(SA.solve_pressure, m, g['material'],
                            g['inner_pressure_pa'], axial_fix='z_max')
                tepe.append(float(r.max_von_mises_nodal))
            fark[etiket] = abs(tepe[-1] - tepe[-2]) / tepe[-2]
        assert fark['acik'] < fark['kapali'], (
            'iç köşe tabanı açıkken ham tepenin tur farkı KÜÇÜLMELİYDİ: '
            f"açık {fark['acik']:.5f} >= kapalı {fark['kapali']:.5f}")
        # Ölçülen büyüklük mertebesi de kilitli (kapalı ~%10,1, açık ~%6,3).
        assert fark['kapali'] > 0.08
        assert fark['acik'] < 0.08


# ===========================================================================
# 7) MALİYET — yoğun kontur mesh'i BÜYÜTMÜYOR
# ===========================================================================
class TestD27Maliyet:

    def test_KONTUR_yogunlasiyor_ama_MESH_BUYUMUYOR(self, motorlar):
        """Taban kontur girdisini ~41× yoğunlaştırır; ELEMAN sayısı sabit.

        Fail-closed maliyet iddiası: kullanıcının çözüm bütçesi sessizce
        büyümez. Ölçüm (once_a1.json §D, katı 256×4): nokta 42 → 1738,
        mesh kurma 0,0092 → 0,0138 s, n_elems 1024 → 1024, n_nodes
        1285 → 1285, çözüm süresi değişmedi.
        """
        g = motorlar['kati']['girdi']
        m_kapali = _sessiz(MA.build_wall_mesh, g['contour'], g['thickness_m'],
                           n_axial=256, n_radial=4, inner_kink_tol_rad=0.0)
        m_acik = _sessiz(MA.build_wall_mesh, g['contour'], g['thickness_m'],
                         n_axial=256, n_radial=4)
        assert m_acik.n_elems == m_kapali.n_elems
        assert m_acik.n_nodes == m_kapali.n_nodes
        yk = m_kapali.meta['ic_kose_yuvarlatma']
        ya = m_acik.meta['ic_kose_yuvarlatma']
        assert ya['yeni_nokta'] > 20 * yk['ham_nokta'], (
            'kontur beklendiği gibi yoğunlaşmamış: '
            f"{ya['yeni_nokta']} vs {yk['ham_nokta']}")
        assert ya['eklenen_nokta'] == ya['yeni_nokta'] - ya['ham_nokta']


# ===========================================================================
# 8) BEYAN — kod gerekçeyi TAŞIYOR (sessiz varsayım yok)
# ===========================================================================
class TestD27Beyan:

    def test_SABIT_BLOGU_13_BEKCININ_YARGILANDIGINI_soyluyor(self):
        """D26'nın "yargılanmadı" gerekçesi kodda KALMAMALI."""
        import inspect
        kaynak = inspect.getsource(MA)
        i = kaynak.index('INNER_KINK_VARSAYILAN_TOL_RAD = ')
        blok = kaynak[max(0, i - 3000):i]
        assert 'TEK TEK' in blok or 'tek tek' in blok
        assert 'o iş bu aşamanın bütçesine sığmadı' not in blok, (
            'D26 a2 gerekçesi kodda duruyor ama iş yapıldı — beyan yalan '
            'söylüyor')

    def test_META_beyani_TURETIMI_ve_SINIRI_adiyla_tasiyor(self):
        C = kontur_42()
        m = MA.build_wall_mesh(C, 0.003, n_axial=64, n_radial=4)
        b = m.meta['ic_kose_yuvarlatma']['_basis']
        assert 'T·tan(θ/4)' in b
        assert 'sapma_ust_sinir_m' in b
        assert 'taban_saglandi' in b
        assert 'Williams' in b
