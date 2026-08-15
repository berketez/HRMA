"""
Dış yüzey eğrilik tabanı bekçileri (hrma/fea/mesh_axisym.py madde 2b).

Kilitlenen kusur (ÖLÇÜLDÜ, 2026-08-15, sıvı varsayılanı rp1/lox 10 kN,
Pc = 100 bar, t = 2 mm): dış sınır, iç konturun normale dik t ötelenmişi
olarak kurulunca KONKAV vadide dış eğrinin eğrilik yarıçapı Rn − t'ye
düşer; motor konturu bir POLİGON olduğu için tepe köşelerinde bu yarıçap
inceltmeyle SIFIRA gider (ölçüldü: 256 istasyonda 3,5 mm → 1024'te
1,6 mm → 4096'da mesh ters dönüp Jacobian bekçisine takılıyor; tepe von
Mises turda %16-18 büyümeye devam ediyor, 757 MPa'da bile yakınsamamış).
Düzeltme: dış eğriye yarıçapı ``floor = t`` olan yuvarlanan-top kapaması
(morfolojik dilate + erode) + işaretli köşe penceresinde dereceli eksenel
örnekleme. Bu dosya üç şeyi kilitler:

1. Sentetik V-vadi: normal öteleme TEK BAŞINA tabanı ihlal eder (kaba
   örneklemede taban altı yarıçap, incesinde Jacobian ölümü); kapama
   sonrası her konkav segmentte yarıçap ≥ floor·(1−tol), iç yüzey kontur
   poligonunun ÜZERİNDE kalır, kalınlaşma ölçülüp beyan edilir.
2. Tetiklenmeyen geometriler: silindir ve eğik koni (konkav vadi yok)
   kapama AÇIKKEN bile floor=0 ile BİT-ÖZDEŞ mesh üretir — Lamé/VM25
   analitik vakaları bu yüzden değişmez; beyan alanları yine yazılır,
   uygulama bölgesi boştur.
3. Sıvı vakası (RocketCEA'sız, örnekleyiciden deterministik): köprü
   koşusu sınırlı tepe gerilmesiyle biter, taban beyanı köprü meta'sına
   AYNEN akar. Ölçülen kilit değerler (conical örnekleyici varsayılanı,
   r_t = 14,25 mm): Gauss maks vM ≈ 662 MPa, son tur bağıl değişim
   %4,6 (kapamasız aynı vaka: %11,5 ve beyan bölgesi SIFIR — mutasyon
   ayrımı buradan).

Mutasyon sözleşmesi: ``build_wall_mesh`` varsayılanı ``auto`` → ``0.0``
yapılırsa (kapama atlanır) sıvı vakası bekçileri kırmızı verir:
uygulama bölgesi boşalır, taban alanı 0 yazar, kalınlaşma kaybolur ve
son tur bağıl değişim eşiği aşar (ölçüldü: 0,115 > 0,08).
"""

import numpy as np
import pytest

from hrma.fea import bridge
from hrma.fea.mesh_axisym import (
    build_wall_mesh,
    polyline_concave_radii,
)

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')

# ---------------------------------------------------------------------------
# Sentetik V-vadi: silindir → 0,5 eğimli V (tepe z = 60 mm) → silindir.
# Köşe yarıçapı sıfırdır; t = 4 mm normal öteleme dış eğriyi dejenere eder.
# ---------------------------------------------------------------------------
V_KONTUR = [(0.0, 0.030), (0.040, 0.030), (0.060, 0.020),
            (0.080, 0.030), (0.120, 0.030)]
V_T = 0.004


def _min_konkav_yaricap(mesh):
    """Dış düğüm zincirinin en küçük KONKAV çevrel yarıçapı [m]."""
    R, konkav = polyline_concave_radii(mesh.nodes[mesh.outer_nodes])
    sel = konkav & np.isfinite(R)
    return float(R[sel].min()) if sel.any() else None


@pytest.fixture(scope='module')
def sivi_motor():
    """Sıvı imzalı sentetik motor sözlüğü — kontur GERÇEK örnekleyiciden.

    RocketCEA gerektirmez: geometri ``sample_nozzle_inner_contour``ın
    kendi deterministik çıktısıdır (aynı örnekleyici üç motorun konturunu
    da üretir), yapısal blok sıvı çözücüsünün alan adlarını taşır. Test
    altyapısı sözlüğüdür; kullanıcıya gösterilen veri değildir.
    """
    from hrma.engines.nozzle_design import sample_nozzle_inner_contour
    pts_mm, _meta = sample_nozzle_inner_contour({
        'chamber_diameter': 0.0825,
        'throat_diameter': 0.0285,
        'exit_diameter': 0.0995,
    })
    return {
        'chamber_pressure': 100.0,                      # bar
        'chamber_length': 150.0,                        # mm (sıvı sözleşmesi)
        'nozzle_contour': {
            'points': [[z / 1000.0, r / 1000.0] for z, r in pts_mm]},
        'structural_analysis': {'chamber_structure': {
            'wall_thickness': 2.0,                      # mm
            'wall_thickness_source': 'test sabiti',
            'material_key': 'inconel_718',
            'yield_strength': 1100.0,                   # MPa
        }},
    }


# ---------------------------------------------------------------------------
# 1) Sentetik V-vadi
# ---------------------------------------------------------------------------
class TestSentetikVVadi:

    def test_ham_oteleme_tabani_ihlal_eder(self):
        """Kapama KAPALIYKEN dış eğri taban altına iner (kusurun kanıtı)."""
        mesh = build_wall_mesh(V_KONTUR, V_T, 32, 4,
                               outer_curvature_floor=0.0)
        r_min = _min_konkav_yaricap(mesh)
        assert r_min is not None and r_min < V_T, (
            'ham öteleme V-vadide taban altı yarıçap üretmeliydi; '
            f'ölçülen {r_min}')

    def test_ham_oteleme_ince_orneklemede_dejenere(self):
        """İnceltme ham çentiği çözer → elemanlar ters döner (ölçüldü)."""
        with pytest.raises(ValueError, match='ters dönmüş|dejenere'):
            build_wall_mesh(V_KONTUR, V_T, 64, 4, outer_curvature_floor=0.0)

    @pytest.mark.parametrize('n_axial', [32, 64, 128])
    def test_kapali_dis_egri_tabani_saglar(self, n_axial):
        """Kapama sonrası her konkav segment ≥ floor·(1−tol) — ölçülür."""
        mesh = build_wall_mesh(V_KONTUR, V_T, n_axial, 4)
        r_min = _min_konkav_yaricap(mesh)
        assert r_min is not None and r_min >= 0.95 * V_T, (
            f'kapanmış dış eğri tabanın altında: {r_min} < {0.95 * V_T}')
        # Meta ölçümü testin kendi ölçümüyle aynı zincirden gelir.
        tm = mesh.meta['dis_yuzey_egrilik_tabani']
        assert tm['dis_egri_min_konkav_yaricap_m'] == pytest.approx(r_min)

    def test_ic_yuzey_kontur_uzerinde_kalir(self):
        """İç yüzey ASLA değişmez: her iç düğüm kontur poligonu ÜZERİNDE.

        Dereceli örnekleme istasyonları kaydırabilir ama nokta yine
        poligonun üzerindedir (V konturu z'nin tek değerli fonksiyonu —
        z-enterpolasyonuyla birebir karşılaştırılabilir).
        """
        mesh = build_wall_mesh(V_KONTUR, V_T, 64, 4)
        ic = mesh.nodes[mesh.inner_nodes]
        Vz = [p[0] for p in V_KONTUR]
        Vr = [p[1] for p in V_KONTUR]
        np.testing.assert_allclose(ic[:, 1], np.interp(ic[:, 0], Vz, Vr),
                                   rtol=0.0, atol=1e-12)

    def test_kalinlasma_olculur_ve_beyan_edilir(self):
        mesh = build_wall_mesh(V_KONTUR, V_T, 64, 4)
        tm = mesh.meta['dis_yuzey_egrilik_tabani']
        assert tm['outer_curvature_floor_m'] == pytest.approx(V_T)
        assert tm['kalinlik_min_m'] == pytest.approx(V_T, rel=1e-6)
        assert tm['kalinlik_maks_m'] > V_T + 1e-5, \
            'V tepesinde top-köprü kalınlaşması ölçülmeliydi'
        # Uygulama bölgesi V tepesini (z = 60 mm) kapsar.
        bolgeler = tm['uygulama_bolgesi_z_m']
        assert bolgeler, 'uygulama bölgesi beyanı boş'
        assert any(a - 0.002 <= 0.060 <= b + 0.002 for a, b in bolgeler)
        # Gerekçe beyanda: iyi-konumluluk + imal edilebilirlik.
        assert 'iyi-konumluluk' in tm['_basis']
        assert 'takım' in tm['_basis']


# ---------------------------------------------------------------------------
# 2) Tetiklenmeyen geometriler — analitik vakaların değişmezlik sigortası
# ---------------------------------------------------------------------------
class TestTetiklenmeyenGeometriler:

    def test_silindir_bit_ozdes(self):
        """Konkav vadi yok → kapama AÇIK/KAPALI mesh'ler bit-özdeş.

        Lamé / VM25 analitik doğrulama vakaları düz silindir kullanır; bu
        bekçi o vakaların taban değişikliğinden ETKİLENMEDİĞİNİ kilitler.
        """
        acik = build_wall_mesh([(0.0, 0.05), (0.1, 0.05)], 0.005, 16, 4)
        kapali = build_wall_mesh([(0.0, 0.05), (0.1, 0.05)], 0.005, 16, 4,
                                 outer_curvature_floor=0.0)
        assert np.array_equal(acik.nodes, kapali.nodes)
        tm = acik.meta['dis_yuzey_egrilik_tabani']
        # Tetiklenmese de alanlar YAZILIR; uygulama bölgesi boştur.
        assert tm['outer_curvature_floor_m'] == pytest.approx(0.005)
        assert tm['uygulama_bolgesi_z_m'] == []
        assert tm['duzeltilen_istasyon'] == 0
        assert tm['kalinlik_min_m'] == pytest.approx(0.005)
        assert tm['kalinlik_maks_m'] == pytest.approx(0.005)
        assert tm['dereceli_ornekleme']['aktif'] is False

    def test_egik_koni_bit_ozdes_ve_dik_kalinlik(self):
        """Doğru parçası üzerinde ayrık kapama TAM özdeşliktir (ölçüldü)."""
        acik = build_wall_mesh([(0.0, 0.05), (0.1, 0.03)], 0.004, 8, 4)
        kapali = build_wall_mesh([(0.0, 0.05), (0.1, 0.03)], 0.004, 8, 4,
                                 outer_curvature_floor=0.0)
        assert np.array_equal(acik.nodes, kapali.nodes)
        grid = acik.node_index_grid
        kalinlik = np.hypot(
            *(acik.nodes[grid[:, -1]] - acik.nodes[grid[:, 0]]).T)
        np.testing.assert_allclose(kalinlik, 0.004, rtol=1e-9)

    def test_radyal_kipte_taban_uygulanmaz_ve_beyan_edilir(self):
        """Dikey öteleme dış eğriliği küçültmez — taban kapalı, beyanlı."""
        mesh = build_wall_mesh(V_KONTUR, V_T, 32, 4, offset_mode='radial')
        tm = mesh.meta['dis_yuzey_egrilik_tabani']
        assert tm['outer_curvature_floor_m'] is None
        assert 'radyal' in tm['taban_kaynagi']
        assert tm['uygulama_bolgesi_z_m'] == []

    def test_gecersiz_taban_reddedilir(self):
        with pytest.raises(ValueError):
            build_wall_mesh(V_KONTUR, V_T, 16, 4, outer_curvature_floor=-1.0)
        with pytest.raises(ValueError):
            build_wall_mesh(V_KONTUR, V_T, 16, 4,
                            outer_curvature_floor='otomatik')


# ---------------------------------------------------------------------------
# 3) Sıvı vakası — köprü zinciri uçtan uca
# ---------------------------------------------------------------------------
class TestSiviVakasi:

    @pytest.fixture(scope='class')
    def kosu(self, sivi_motor):
        out = bridge.run_structural_from_motor(sivi_motor)
        assert out['status'] == bridge.BRIDGE_STATUS_OK
        return out

    def test_tepe_gerilme_sinirli_ve_fiziksel_mertebede(self, kosu):
        """Eski davranış: turda %16-18 büyüyen, mesh ölümüne giden tepe.

        Yeni sözleşme (ÖLÇÜLDÜ): tepe Gauss vM ≈ 662 MPa — boğaz boynunda
        |R1| ≈ 5,4 mm meridyonel eğrilik + eğilme ile t = 2 mm / 100 bar
        için fiziksel mertebe (membran çember bileşeni tek başına ~164
        MPa). NOT: görev metnindeki "< 100 MPa" beklentisi t = 5 mm
        varsayımına aitti (çevre gerilmesi 29 MPa); bu payload t = 2 mm
        yayımlıyor, gerçek değer ölçülüp burada kilitlendi.
        """
        assert kosu['von_mises_gauss_max'] == pytest.approx(662.2e6,
                                                            rel=0.05)
        assert kosu['min_safety_factor'] == pytest.approx(1.66, rel=0.06)
        # Son tur bağıl değişimi SINIRLI (kapamasız ölçüm: 0,115; ham
        # jilet-çentikte inceltme hiç durmuyordu). Kalan pay çözücü
        # politikasının radyal katlama bileşenidir (raporda ölçülü).
        assert kosu['convergence']['final_rel_change'] < 0.08

    def test_taban_beyani_dolu_ve_koprude_akar(self, kosu):
        tm = kosu['mesh']['meta']['dis_yuzey_egrilik_tabani']
        assert tm['outer_curvature_floor_m'] == pytest.approx(0.002)
        assert len(tm['uygulama_bolgesi_z_m']) >= 1
        assert tm['kalinlik_maks_m'] > tm['kalinlik_min_m']
        assert tm['dis_egri_min_konkav_yaricap_m'] >= 0.95 * 0.002
        # Köprü meta zinciri: mesh beyanı girdiler/cozucu yanında AYNEN.
        meta = kosu['meta']
        assert meta['mesh_beyani'] is kosu['mesh']['meta']
        assert 'girdiler' in meta and 'cozucu' in meta

    def test_dereceli_ornekleme_beyanli(self, kosu):
        tm = kosu['mesh']['meta']['dis_yuzey_egrilik_tabani']
        assert tm['dereceli_ornekleme']['aktif'] is True
        assert tm['kapama_olcumu']['tabanalti_kose_tepesi'] >= 1
