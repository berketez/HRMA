"""ÖH D25 · fea-cfd · aşama-1 · OH-D24-01 bekçileri.

Kalem: "Yapısal FEA kısıt/mesh modeli TEKİL: axial_fix noktasal kısıt →
tepe gerilme inceltmeyle ıraksıyor; SCL/Saint-Venant dışlaması tepeyi
süzmüyor."

ÖLÇÜM İKİ AYAĞI DA AYIRDI (kanıt docs/scofield/raw/OH/D25/fea-cfd/a1/):

1. İDDİA EDİLEN SEBEP DÜŞTÜ. Iraksayan tepe kısıtta DEĞİL: katı motorda
   (axial_fix=z_max) tepe her mesh basamağında boğazın DIŞ yüzeyinde
   (z ≈ 0,0799 m, r ≈ 0,01948 m) ve kısıtlanan uç kesite 3,32·d_SV
   uzaklıkta — Saint-Venant bandının çok dışında (teshis_geometri.json).
   Kapama kapalı ve saf radyal öteleme varyantlarında da ıraksama sürüyor
   (teshis_kaynak.json), yani kısıt modelini ya da dış yüzey eğrilik
   tabanını değiştirmek bu tepeyi kaldırmaz.

2. GERÇEK KUSUR BULUNDU VE ONARILDI. Hüküm sayısı ASME'nin TEPE (F)
   sınıfından geliyordu. Tekdüze merdivende (64x4 → 128x8 → 256x16 →
   512x32) ham düğüm tepesi 188,49 → 242,78 MPa, gözlenen mertebe
   p ≈ 0,12 ve son adım hâlâ %4,00; lineerleştirilmiş büyüklükler ise
   yakınsıyor (P_m: 126,94 → 129,13, p ≈ 1,0, son adım %0,24).
   ASME BPVC VIII-2 Bölüm 5 Tablo 5.6 + Ek 5-A tepeyi plastik çökme
   hükmünden zaten dışlar. Hüküm artık max(1,5·P_m, P_L+P_b).
"""
import numpy as np
import pytest

from hrma.fea.mesh_axisym import build_wall_mesh
from hrma.fea.structural_axisym import (
    ASME_MEMBRAN_KATI, Material, SCL_MIN_ELEMAN, scl_lineerlestirme,
    solve_pressure)


STEEL = Material(E=200.0e9, nu=0.3, yield_strength=250.0e6, name="d25")


def _boru(n_axial=24, n_radial=6, t=0.004, r_ic=0.05, L=0.30):
    """Düz silindirik cidar — analitik kıyas için düzgün geometri."""
    z = np.linspace(0.0, L, 41)
    kontur = np.stack([z, np.full_like(z, r_ic)], axis=1)
    return build_wall_mesh(kontur, t, n_axial=n_axial, n_radial=n_radial)


# ===========================================================================
# 1) LİNEERLEŞTİRME MATEMATİĞİ — sembolik türetimin sayısal doğrulaması
# ===========================================================================
class TestLineerlestirmeMatematigi:

    def test_lineer_alanda_TAM_geri_verir(self):
        """σ(x) = a + b·x ise σ_m ± σ_b iki yüzey değerini BİREBİR verir.

        Türetim (modül başındaki blokta): σ_m = a + b·t/2 ve σ_b = −b·t/2,
        dolayısıyla σ_m − σ_b = a + b·t (dış yüzey) ve σ_m + σ_b = a
        (iç yüzey). Bu, lineerleştirmenin "lineer alanda tam" olma
        özelliğidir; sağlanmazsa integrasyon ağırlıkları yanlıştır.
        """
        mesh = _boru()
        nodes = np.asarray(mesh.nodes, float)
        grid = np.asarray(mesh.node_index_grid, int)
        P = nodes[grid]
        x = np.linalg.norm(P - P[:, 0:1, :], axis=2)     # SCL boyu koordinat
        a, b = 40.0e6, 5.0e9                              # Pa, Pa/m
        S = np.zeros((nodes.shape[0], 4), float)
        alan = a + b * x
        # σ_θ bileşenine koy: SCL yerel çerçevesinde σ_θθ dönmez.
        for i in range(grid.shape[0]):
            S[grid[i], 2] = alan[i]
        P_m, P_LPb, beyan = scl_lineerlestirme(mesh, S)
        assert beyan['gecerli'] is True
        t = np.linalg.norm(P[:, -1, :] - P[:, 0, :], axis=1)
        # Tek eksenli alanda von Mises = |σ_θθ|; iki uç değerin büyüğü.
        beklenen = np.maximum(np.abs(a), np.abs(a + b * t))
        np.testing.assert_allclose(P_LPb, beklenen, rtol=1e-9)
        np.testing.assert_allclose(P_m, np.abs(a + b * t / 2.0), rtol=1e-9)

    def test_tepe_payi_HUKME_girmez_membrana_girer(self):
        """Tek düğümlük yerel sivri (F) P_L+P_b'yi mesh'le orantılı etkiler.

        Tekillik imzası budur: alanın kendisi büyürken lineerleştirilmiş
        büyüklük integrasyon ağırlığı (≈ h/2) kadar etkilenir, yani mesh
        inceltildikçe etkisi SIFIRA gider. Ham tepe ise doğrudan sivrinin
        kendisidir.
        """
        onceki = None
        for nr in (4, 8, 16):
            mesh = _boru(n_radial=nr)
            grid = np.asarray(mesh.node_index_grid, int)
            S = np.zeros((np.asarray(mesh.nodes).shape[0], 4), float)
            S[grid[:, :], 2] = 100.0e6
            S[grid[grid.shape[0] // 2, -1], 2] = 1000.0e6   # dış yüzeyde sivri
            _, P_LPb, beyan = scl_lineerlestirme(mesh, S)
            assert beyan['gecerli'] is True
            fazla = float(np.nanmax(P_LPb)) - 100.0e6
            if onceki is not None:
                assert fazla < onceki, (
                    'sivrinin lineerleştirilmiş paya katkısı inceltmeyle '
                    f'küçülmüyor: {onceki} → {fazla}')
            onceki = fazla

    def test_boyut_analizi_olcekle_dogrusal(self):
        """σ → k·σ ölçeklemesi P_m ve P_L+P_b'yi k katına çıkarır (Pa)."""
        mesh = _boru()
        grid = np.asarray(mesh.node_index_grid, int)
        S = np.zeros((np.asarray(mesh.nodes).shape[0], 4), float)
        S[:, 2] = 10.0e6
        S[grid[:, -1], 0] = 3.0e6
        m1, b1, _ = scl_lineerlestirme(mesh, S)
        m2, b2, _ = scl_lineerlestirme(mesh, 7.0 * S)
        np.testing.assert_allclose(m2, 7.0 * m1, rtol=1e-12)
        np.testing.assert_allclose(b2, 7.0 * b1, rtol=1e-12)


# ===========================================================================
# 2) FAIL-CLOSED — lineerleştirme kurulamazsa hüküm düşer
# ===========================================================================
class TestLineerlestirmeFailClosed:

    def test_cidar_boyu_tek_eleman_REDDEDILIR(self):
        mesh = _boru(n_radial=1)          # MIN_ELEMS_THROUGH_WALL'a çekilir
        grid = np.asarray(mesh.node_index_grid, int)
        assert grid.shape[1] - 1 >= SCL_MIN_ELEMAN, (
            'bu ağaçta cidar katmanı zaten alt sınıra çekiliyor; '
            'reddi doğrudan sınayamıyoruz')

    def test_hukum_alani_bos_maskede_REDDEDILIR(self):
        mesh = _boru()
        n = np.asarray(mesh.nodes).shape[0]
        S = np.zeros((n, 4), float)
        S[:, 2] = 10.0e6
        _, _, beyan = scl_lineerlestirme(mesh, S,
                                         np.zeros(n, dtype=bool))
        assert beyan['gecerli'] is False
        assert 'hüküm alanı' in beyan['red_gerekcesi']

    def test_banda_DEGEN_SCL_tumuyle_dislanir(self):
        """Muhafazakâr kural: bandın içine giren bir SCL hükme GİRMEZ.

        Kısmi maske ile sınanır; ``all`` yerine ``any`` konursa (banda
        değen çizgi yine de hükme alınırsa) bu bekçi kırmızı verir.
        """
        mesh = _boru()
        grid = np.asarray(mesh.node_index_grid, int)
        n = np.asarray(mesh.nodes).shape[0]
        S = np.zeros((n, 4), float)
        S[:, 2] = 10.0e6
        # 0. istasyonun SADECE dış düğümü bant dışında; o SCL dışlanmalı.
        S[grid[0], 2] = 900.0e6
        maske = np.ones(n, dtype=bool)
        maske[grid[0, :-1]] = False
        _, P_LPb, beyan = scl_lineerlestirme(mesh, S, maske)
        assert beyan['gecerli'] is True
        assert np.isnan(P_LPb[0]), (
            'Saint-Venant bandına DEĞEN SCL hüküm alanına alınmış — '
            'muhafazakâr dışlama kuralı (all) gevşetilmiş olabilir')
        assert float(np.nanmax(P_LPb)) < 200.0e6, (
            'banda değen istasyonun sivrisi hükmü ele geçirmiş')
        assert beyan['hukum_istasyonu_sayisi'] < beyan['istasyon_sayisi']

    def test_kopru_gecersiz_lineerlestirmede_HUKMU_GERI_CEKER(self,
                                                              monkeypatch):
        """Fail-closed uç: lineerleştirme kurulamazsa köprü hüküm VERMEZ."""
        pytest.importorskip('flask')
        from hrma.fea import bridge as B
        from hrma.fea import structural_axisym as SA

        def _gecersiz(mesh, stress_nodal, hukum_maskesi=None):
            return None, None, {'gecerli': False,
                                'red_gerekcesi': 'ters mutasyon sondası'}

        monkeypatch.setattr(SA, 'scl_lineerlestirme', _gecersiz)
        motor = {
            'chamber_pressure': 30.0, 'chamber_length': 150.0,
            'nozzle_contour': {'points': [[0.0, 0.05], [0.1, 0.05],
                                          [0.2, 0.05]]},
            'structural_analysis': {'chamber_structure': {
                'wall_thickness': 3.0,
                'wall_thickness_source': 'D25 bekçi sabiti',
                'material_key': 'steel_4130', 'yield_strength': 435.0}},
        }
        cikti = B.run_structural_from_motor(motor, max_rounds=1)
        h = (cikti or {}).get('verdict') or {}
        assert h, 'köprü hüküm yayımlamıyor'
        assert 'scl_lineerlestirme_gecersiz' in h['geri_cekme_gerekceleri'], (
            'lineerleştirme geçersizken hüküm geri çekilmiyor — fail-closed '
            f"kaybı: {h.get('geri_cekme_gerekceleri')}")
        assert h['verildi'] is False

    def test_gecersizse_ESKI_davranisa_duser_ve_ADINI_soyler(self):
        """Fail-closed: geçersiz lineerleştirmede hüküm ham tepeye döner."""
        mesh = _boru()
        res = solve_pressure(mesh, STEEL, 5.0e6, axial_fix='z_min')
        assert res.meta['scl_lineerlestirme']['gecerli'] is True
        assert 'ASME' in res.meta['emniyet_katsayisi_kaynagi']
        assert 'P_L+P_b' in res.meta['emniyet_katsayisi_kaynagi']


# ===========================================================================
# 3) ÜRÜN SÖZLEŞMESİ — hüküm sınıfı ve tepe sınıfı AYNI ANDA yayımlanır
# ===========================================================================
class TestUrunSozlesmesi:

    @pytest.fixture(scope='class')
    def cozum(self):
        mesh = _boru()
        return mesh, solve_pressure(mesh, STEEL, 5.0e6, axial_fix='z_min')

    def test_hukum_paydasi_ASME_iki_olcutunun_kotusudur(self, cozum):
        _, res = cozum
        scl = res.meta['scl_lineerlestirme']
        assert res.max_von_mises_hukum == pytest.approx(
            max(ASME_MEMBRAN_KATI * scl['P_m_maks_pa'],
                scl['P_L_Pb_maks_pa']))
        assert scl['hukum_paydasi_baglayici'] in ('1,5·P_m', 'P_L+P_b')

    def test_ham_tepe_SILINMEZ_ve_kendi_katsayisi_var(self, cozum):
        _, res = cozum
        assert res.max_von_mises_nodal is not None
        assert res.tepe_emniyet_katsayisi == pytest.approx(
            STEEL.yield_strength / res.max_von_mises_nodal)

    def test_hukum_paydasi_P_L_Pb_den_KUCUK_OLAMAZ(self, cozum):
        """Değişmez: hüküm paydası iki ASME ölçütünün KÖTÜSÜDÜR.

        ÖLÇÜLDÜ ve dürüstçe kaydedilir: "tepe katsayısı daima hüküm
        katsayısından küçüktür" DOĞRU DEĞİLDİR. Membran baskın vakalarda
        1,5·P_m ham tepeyi bile geçebilir ve hüküm tepeden SIKI çıkar —
        bu fikstürde tepe SF 3,6919 iken hüküm SF 2,6146. Yani geçiş
        genel olarak bir gevşeme değildir; gevşeme ancak tepe gerçekten
        tekil bir sivriyken (boğaz köşesi) olur ve orası zaten ASME'nin
        F sınıfıdır.
        """
        _, res = cozum
        scl = res.meta['scl_lineerlestirme']
        assert res.max_von_mises_hukum >= scl['P_L_Pb_maks_pa'] - 1e-6
        assert res.max_von_mises_hukum >= (
            ASME_MEMBRAN_KATI * scl['P_m_maks_pa'] - 1e-6)

    def test_membran_ayagi_KALIN_cidarda_baglayici(self):
        """Kalın cidarda 1,5·P_m ölçütü ısırır — muhafazakârlık korunur.

        Bu, D25'in gevşeme koruması: yalnız P_L+P_b kullanılsaydı kalın
        cidar çapasında (Lamé) hüküm ESKİSİNDEN GEVŞEK çıkıyordu
        (8,004 → 9,729); membran ayağıyla 7,917'ye, yani eskisinden SIKI
        hâle geldi.
        """
        z = np.linspace(0.0, 0.2, 41)
        kontur = np.stack([z, np.full_like(z, 0.05)], axis=1)
        mesh = build_wall_mesh(kontur, 0.025, n_axial=24, n_radial=8)
        res = solve_pressure(mesh, STEEL, 20.0e6, axial_fix='both_ends')
        scl = res.meta['scl_lineerlestirme']
        assert scl['hukum_paydasi_baglayici'] == '1,5·P_m', (
            'kalın cidarda membran ölçütü bağlayıcı değil — muhafazakârlık '
            f"kaybı: {scl}")
        assert res.max_von_mises_hukum >= scl['P_L_Pb_maks_pa']


# ===========================================================================
# 4) İDDİA EDİLEN SEBEBİN ÇÜRÜTÜLMESİ — tepe kısıtta DEĞİL
# ===========================================================================
class TestKalemIddiasiOlculdu:

    def test_iraksayan_tepe_Saint_Venant_bandinin_DISINDA(self):
        """Kalemin sebebi ölçümle düştü ve bu bekçi düşüşü kilitler.

        Katı motor konturunu taklit eden daralan-genişleyen bir cidarda
        tepe kısıtlanan uç kesite d_SV'den UZAKTADIR; yani kısıt modelini
        değiştirmek (dağıtılmış/simetri kısıt) tepeyi kaldırmaz.
        """
        z = np.linspace(0.0, 0.17, 42)
        r = 0.062 - 0.046 * np.exp(-((z - 0.08) / 0.030) ** 2)
        mesh = build_wall_mesh(np.stack([z, r], axis=1), 0.003,
                               n_axial=256, n_radial=8)
        res = solve_pressure(mesh, STEEL, 4.0e6, axial_fix='z_max')
        nodes = np.asarray(mesh.nodes, float)
        vm = np.asarray(res.von_mises_nodal, float)
        tepe = nodes[int(np.argmax(vm))]
        kis = nodes[np.asarray(mesh.z_max_nodes, int).ravel()]
        d = float(np.min(np.hypot(tepe[0] - kis[:, 0], tepe[1] - kis[:, 1])))
        sv = res.meta['saint_venant']
        assert sv['gecerli'] is True
        d_sv = float(sv['bantlar'][0]['d_SV_m'])
        assert d > d_sv, (
            'tepe Saint-Venant bandının İÇİNDE — kalemin kısıt-tekilliği '
            f'iddiası bu geometride yeniden kurulmuş olur: d={d}, dSV={d_sv}')
        # Tepe hüküm maskesinde olduğu hâlde hüküm ondan ALINMIYOR.
        # ÇEVRİLDİ (OH-D25-28 / OH-D24-01, ÖH D27 a1): iç kontur köşe
        # tabanı ÜRÜN VARSAYILANI olunca bu sentetik konturun 23,27°'lik
        # örnekleme köşeleri de yuvarlanıyor; köşe tekilliği kalktığı için
        # ham tepe 282,13 → 264,32 MPa'ya iniyor ve hüküm (278,30 MPa)
        # artık ham tepenin ÜSTÜNDE kalıyor (ölçüm: docs/scofield/raw/OH/
        # D27/fea-cfd/a1/sonra_a1.json §G4). Yani iddia gevşemedi, YÖNÜ
        # DEĞİŞTİ ve fail-closed tarafa geçti. İkisi de sınanıyor:
        #   (a) HAM poligonda (tol=0, bekçinin yazıldığı gün) hüküm ham
        #       tepenin ALTINDA — tekillik hükme geçmiyor;
        #   (b) ürün varsayılanında hüküm ham tepenin ALTINDA DEĞİL —
        #       kullanıcıya giden sayı iyimser tarafa kaçmıyor.
        mesh_ham = build_wall_mesh(np.stack([z, r], axis=1), 0.003,
                                   n_axial=256, n_radial=8,
                                   inner_kink_tol_rad=0.0)
        res_ham = solve_pressure(mesh_ham, STEEL, 4.0e6, axial_fix='z_max')
        assert res_ham.max_von_mises_hukum < res_ham.max_von_mises_nodal, (
            'ham poligonda hüküm ham tepeye eşitlenmiş — SCL dışlaması '
            'çalışmıyor')
        assert res.max_von_mises_hukum >= res.max_von_mises_nodal, (
            'köşe tabanı açıkken hüküm ham tepenin ALTINA düştü — '
            f'{res.max_von_mises_hukum} < {res.max_von_mises_nodal}')
