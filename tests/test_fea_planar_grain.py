"""Katı tane kesiti 2B düzlemsel FEA bekçileri (V2.7 Aşama C).

KAPATILAN KUSUR
---------------
``hrma/fea/__init__.py`` planar_grain kipini NOT_IMPLEMENTED beyanıyla
taşıyordu: star/finocyl/slotted tane kesitleri eksenel simetrik olmadığı
için katı motorun tane gerilmesi yalnız analitik/1B yaklaşımla (silindir +
nominal Kt) raporlanabiliyordu. Bu dalga kesiti gerçekten çözer; buradaki
bekçiler şunları kilitler:

  1. ANALİTİK DOĞRULAMA — bates halkası düzlem şekil değiştirmede iç
     basınçlı kalın cidarlı silindirdir (Timoshenko & Goodier Böl. 4, Lamé):
     port yüzeyi çember gerilmesi analitik değere rel <= %2; mesh 2×
     incelince hata DÜŞER. Lamé gerilmeleri ν'den bağımsız olduğu için aynı
     bekçi ν = 0.4995 (HTPB, sıkıştırılamaz sınır) ile B-bar kilitlenme
     önlemini de kilitler: tam integrasyonlu Q4 bu rejimde kilitlenir,
     B-bar'sız bu test GEÇEMEZ.
  2. FİZİKSEL YÖN — star kesitinde uç kökü gerilme yoğunlaşması: aynı
     çap/basınç/yakıt için star tepe von Mises'i düz porttan (bates) BÜYÜK.
  3. SİMETRİ TUTARLILIĞI — 1/N dilim ile tam halka modeli (küçük N) aynı
     tepe gerilmeyi verir (bağıl tolerans).
  4. GEÇERSİZ GEOMETRİ = RED — negatif web, port >= dış çap, tekil BC
     bileşimleri ValueError; wagon_wheel/end_burner beyanlı NOT_MODELLED.
  5. UÇ SÖZLEŞMESİ — /api/fea/planar-grain: 200 (ok + tutarlı alanlar),
     422 (eksik zorunlu alan + missing_fields), 400 (geçersiz geometri /
     tanınmayan tip), eleman bütçesi beyanı.
  6. MUTASYON BEKÇİSİ — B matrisinin bir terimi bozulunca Lamé bekçisi
     KIRILMALI: doğrulama testinin çözücünün formülasyonunu gerçekten
     duyduğunun kanıtı (bekçinin bekçisi).

Analitik değerler testin İÇİNDE formülden türetilir; hardcode "beklenen"
sayı yoktur (bekçi kusuru kilitlemez, sözleşmeyi kilitler).
"""

import contextlib
import io
import warnings

import numpy as np
import pytest

warnings.filterwarnings('ignore')

from hrma.fea.mesh_planar import (
    MIN_THETA_DIVISIONS_WEDGE,
    build_grain_section_mesh,
    port_radius_sampler_from_polygon,
)
from hrma.fea.planar_grain import (
    _point_B_planar,
    solve_grain_with_refinement,
    solve_plane_strain_section,
)
from hrma.fea.structural_axisym import Material

PLANAR_ENDPOINT = '/api/fea/planar-grain'

# ---------------------------------------------------------------------------
# Ortak Lamé problemi: iç basınçlı kalın halka (bates kesiti), düzlem şekil
# değiştirme, dış yüzey serbest. Tek yerde tanımlanır (parametre tutarlılığı).
# ---------------------------------------------------------------------------
GRAIN_RING_A = 0.015        # m — port yarıçapı
GRAIN_RING_B = 0.050        # m — tane dış yarıçapı (b/a = 3.33: kalın web)
GRAIN_RING_P = 4.0e6        # Pa — 40 bar port basıncı
GRAIN_RING_SYM = 8          # bates eksenel simetrik: dilim genişliği keyfî

# Yol haritası şartıyla aynı doğrulama eşiği: hata <= %2.
GRAIN_LAME_REL_TOL = 0.02

# Bekçi koşularının mesh boyutları (yakınsama dizisi: her adım 2×).
GRAIN_LAME_MESHES = ((8, 8), (16, 16), (32, 32))


def lame_sigma_theta(r, a, b, p):
    """Lamé çember gerilmesi: σ_θ = A(1 + b²/r²), A = p a²/(b² − a²)."""
    A = p * a * a / (b * b - a * a)
    return A * (1.0 + (b * b) / (r * r))


def lame_sigma_r(r, a, b, p):
    """Lamé radyal gerilme: σ_r = A(1 − b²/r²)."""
    A = p * a * a / (b * b - a * a)
    return A * (1.0 - (b * b) / (r * r))


def lame_u_r_plane_strain(r, a, b, p, E, nu):
    """Düzlem şekil değiştirme radyal yer değiştirme (Timoshenko Böl. 4)."""
    A = p * a * a / (b * b - a * a)
    return (1.0 + nu) / E * A * ((1.0 - 2.0 * nu) * r + (b * b) / r)


def _quiet(fn, *args, **kwargs):
    """Motor/çözücü modülleri stdout'a basıyor; testte sessize al."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*args, **kwargs)


def _bore_hoop_stress(mesh, result):
    """Port istasyonlarında çember (teğetsel) gerilme — düğüm alanından.

    Kesit kartezyen çözülür; her port düğümünde hoop = t̂ᵀ σ t̂,
    t̂ = (−sinθ, cosθ). Dönüşüm testin içindedir, çözücüden bağımsız.
    """
    ids = mesh.node_index_grid[:, 0]
    th = np.arctan2(mesh.nodes[ids, 1], mesh.nodes[ids, 0])
    s = result.stress_nodal[ids]
    tx, ty = -np.sin(th), np.cos(th)
    return s[:, 0] * tx * tx + s[:, 1] * ty * ty + 2.0 * s[:, 3] * tx * ty


def _bore_radial_stress(mesh, result):
    """Port istasyonlarında radyal gerilme: n̂ᵀ σ n̂, n̂ = (cosθ, sinθ)."""
    ids = mesh.node_index_grid[:, 0]
    th = np.arctan2(mesh.nodes[ids, 1], mesh.nodes[ids, 0])
    s = result.stress_nodal[ids]
    nx, ny = np.cos(th), np.sin(th)
    return s[:, 0] * nx * nx + s[:, 1] * ny * ny + 2.0 * s[:, 3] * nx * ny


def _solve_lame(nu, n_theta, n_radial, E=None):
    if E is None:
        E = 6.0e6 if nu > 0.45 else 200.0e9   # HTPB bandı / çelik bandı
    mesh = build_grain_section_mesh(GRAIN_RING_A, GRAIN_RING_B, n_theta, n_radial,
                                    symmetry_fraction=GRAIN_RING_SYM)
    mat = Material(E=E, nu=nu, name='lame-test')
    res = solve_plane_strain_section(mesh, mat, GRAIN_RING_P, outer_bc='free')
    return mesh, res


def _lame_bore_hoop_err(nu, n_theta, n_radial):
    mesh, res = _solve_lame(nu, n_theta, n_radial)
    hoop = _bore_hoop_stress(mesh, res)
    ana = lame_sigma_theta(GRAIN_RING_A, GRAIN_RING_A, GRAIN_RING_B, GRAIN_RING_P)
    return float(np.max(np.abs(hoop - ana)) / abs(ana))


# ---------------------------------------------------------------------------
# 0. Kip kaydı: NOT_IMPLEMENTED beyanı gerçek kayda döndü
# ---------------------------------------------------------------------------
def test_module_status_planar_grain_implemented():
    import hrma.fea as fea
    assert fea.MODULE_STATUS['planar_grain'] == 'IMPLEMENTED'
    # Kayıt sözde kalmasın: paket API'si gerçekten dışa açık.
    assert callable(fea.solve_plane_strain_section)
    assert callable(fea.solve_grain_with_refinement)
    assert callable(fea.build_grain_section_mesh)


# ---------------------------------------------------------------------------
# 1. ANALİTİK DOĞRULAMA — Lamé (en önemli bekçi)
# ---------------------------------------------------------------------------
class TestLameDogrulama:
    """Lamé gerilmeleri ν'den bağımsızdır: ν = 0.4995 koşusu, tam
    integrasyonlu Q4'ün kilitlendiği rejimde B-bar önlemini de kilitler."""

    @pytest.mark.parametrize('nu', [0.3, 0.4995])
    def test_bore_hoop_analitik_deger(self, nu):
        err = _lame_bore_hoop_err(nu, *GRAIN_LAME_MESHES[-1])
        assert err <= GRAIN_LAME_REL_TOL, (
            f"ν={nu}: port çember gerilmesi hatası %{100 * err:.3f} > "
            f"%{100 * GRAIN_LAME_REL_TOL:.0f}")

    @pytest.mark.parametrize('nu', [0.3, 0.4995])
    def test_mesh_yakinsamasi_hata_duser(self, nu):
        errs = [_lame_bore_hoop_err(nu, nth, nrad)
                for nth, nrad in GRAIN_LAME_MESHES]
        assert errs[0] > errs[1] > errs[2], (
            f"ν={nu}: inceltmede hata monoton düşmüyor: {errs}")
        # 2× inceltme hatayı en az yarıya indirmeli (O(h) alt sınırı;
        # SPR sınır değeri pratikte O(h²) verir).
        assert errs[2] < 0.5 * errs[1]

    def test_bore_radyal_gerilme_basinc_kosulu(self):
        """Yüzey fiziği: σ_r(port) → −p (yüzey çekişi basıncın kendisi)."""
        mesh, res = _solve_lame(0.3, *GRAIN_LAME_MESHES[-1])
        sr = _bore_radial_stress(mesh, res)
        assert np.max(np.abs(sr + GRAIN_RING_P)) / GRAIN_RING_P <= GRAIN_LAME_REL_TOL

    def test_radyal_yer_degistirme_analitik(self):
        """u_r(port) analitik Lamé değerine oturur (E, ν bağımlı alan)."""
        nu, E = 0.3, 200.0e9
        mesh, res = _solve_lame(nu, *GRAIN_LAME_MESHES[-1], E=E)
        ids = mesh.node_index_grid[:, 0]
        th = np.arctan2(mesh.nodes[ids, 1], mesh.nodes[ids, 0])
        u = res.displacement[ids]
        u_r = u[:, 0] * np.cos(th) + u[:, 1] * np.sin(th)
        ana = lame_u_r_plane_strain(GRAIN_RING_A, GRAIN_RING_A, GRAIN_RING_B, GRAIN_RING_P, E, nu)
        assert np.max(np.abs(u_r - ana)) / abs(ana) <= GRAIN_LAME_REL_TOL

    def test_bore_gerinimi_analitik(self):
        """Port lif gerinimi = u_r/a (dairesel port): kabul ölçütü bekçisi."""
        nu, E = 0.4995, 6.0e6
        mesh, res = _solve_lame(nu, *GRAIN_LAME_MESHES[-1], E=E)
        ana = lame_u_r_plane_strain(GRAIN_RING_A, GRAIN_RING_A, GRAIN_RING_B, GRAIN_RING_P,
                                    E, nu) / GRAIN_RING_A
        assert res.max_bore_strain == pytest.approx(ana, rel=GRAIN_LAME_REL_TOL)
        # Çekme yönü: iç basınç port çevresini uzatır.
        assert res.max_bore_strain > 0.0

    def test_yakinsama_surucusu_bates_yakinsar(self):
        """Düzgün (tekilliksiz) kesitte sürücü yakınsamayı BEYAN eder."""
        ref = solve_grain_with_refinement(
            GRAIN_RING_A, GRAIN_RING_B, Material(E=6.0e6, nu=0.4995, name='htpb'),
            GRAIN_RING_P, symmetry_fraction=GRAIN_RING_SYM, outer_bc='bonded_rigid')
        assert ref.converged is True, ref.meta['beyan']
        assert ref.final_rel_change < ref.tol
        assert len(ref.history) >= 2
        elemanlar = [h['n_elems'] for h in ref.history]
        assert elemanlar == sorted(elemanlar)
        assert ref.history[0]['rel_change'] is None


# ---------------------------------------------------------------------------
# 2. FİZİKSEL YÖN — star uç kökü yoğunlaşması
# ---------------------------------------------------------------------------
class TestStarYogunlasma:
    @pytest.fixture(scope='class')
    def kosular(self):
        from hrma.fea.bridge import run_planar_grain_fea
        ortak = dict(propellant_type='apcp', outer_diameter_mm=100.0,
                     core_diameter_mm=30.0, chamber_pressure_bar=40.0,
                     max_rounds=2)
        bates = _quiet(run_planar_grain_fea, 'bates', **ortak)
        star = _quiet(run_planar_grain_fea, 'star',
                      geometry_overrides={'star_points': 6,
                                          'star_radius': 12.0}, **ortak)
        assert bates['status'] == 'ok' and star['status'] == 'ok'
        return bates, star

    def test_star_tepe_von_mises_batesten_buyuk(self, kosular):
        """Yoğunlaşmayı taşıyan alan GAUSS alanıdır: SPR düğüm alanı sınır
        düğümünü iç yamadan değerlendirdiği için keskin köşe tepesini
        DÜZLEŞTİRİR (ölçüldü: star Gauss maks 9.3e4 Pa iken SPR düğüm maks
        5.2e4 Pa) — karşılaştırma bu yüzden Gauss maksimumuyla yapılır."""
        bates, star = kosular
        assert star['von_mises_gauss_max'] > bates['von_mises_gauss_max'], (
            'star uç kökü yoğunlaşması düz porttan büyük gerilme vermeli')

    def test_yogunlasma_uc_kokunde(self, kosular):
        """Tepe Gauss gerilmesi UÇ KÖKÜ civarında oturmalı (yer bekçisi).

        Uç köşesi θ = 0 ya da θ = 2π/N kenarında, r = uç yarıçapındadır;
        tepe elemanın merkezi bu noktaya dış yarıçapın %15'inden yakın
        olmalı — yoğunlaşma port vadisinde ya da kasada çıkarsa model
        yanlış demektir.
        """
        _bates, star = kosular
        mesh = star['mesh']
        nodes = np.asarray(mesh['nodes'], dtype=float)
        elems = np.asarray(mesh['elems'], dtype=int)
        vm_g = star['result'].von_mises_gauss           # (M, 4)
        e_star = int(np.argmax(vm_g.max(axis=1)))
        merkez = nodes[elems[e_star]].mean(axis=0)
        geom = star['inputs']['geometri']
        r_out = geom['outer_diameter_mm'] / 2000.0      # m
        # Uç yarıçapı beyandan okunur: 'star (N uç, uç derinliği D mm ...'
        import re as _re
        depth_mm = float(_re.search(r'uç derinliği ([0-9.]+) mm',
                                    geom['kesit']).group(1))
        r_tip = geom['core_diameter_mm'] / 2000.0 + depth_mm / 1000.0
        n_sym = star['symmetry_fraction']
        uclar = [np.array([r_tip, 0.0]),
                 r_tip * np.array([np.cos(2 * np.pi / n_sym),
                                   np.sin(2 * np.pi / n_sym)])]
        uzaklik = min(float(np.hypot(*(merkez - uc))) for uc in uclar)
        assert uzaklik <= 0.15 * r_out, (
            f'tepe gerilme elemanı uç kökünden {uzaklik * 1000:.1f} mm '
            'uzakta — yoğunlaşma beklenen yerde değil')

    def test_star_geometri_motor_fonksiyonundan(self, kosular):
        """Tek-kaynak kuralı: kesit beyanı motor fonksiyonunu adlandırır."""
        _bates, star = kosular
        geom = star['inputs']['geometri']
        assert '_star_port_polygon' in geom['kaynak']
        assert star['symmetry_fraction'] == 6

    def test_keskin_kose_beyani_yakinsamada(self, kosular):
        """Keskin köşe tekildir: yakınsamama gizlenmez, beyanla taşınır."""
        _bates, star = kosular
        conv = star['convergence']
        if not conv['converged']:
            assert 'TEKİL' in conv['beyan'].upper() or 'YAKINSAMADI' in \
                conv['beyan'].upper()


# ---------------------------------------------------------------------------
# 3. SİMETRİ TUTARLILIĞI — 1/N dilim = tam halka
# ---------------------------------------------------------------------------
class TestSimetriTutarliligi:
    def test_dilim_ve_tam_model_ayni_tepe_gerilme(self):
        """Küçük N'li star: 1/3 dilim ile tam halka aynı çözümü verir.

        Aynı kesit, aynı eleman yoğunluğu (dilim n_theta = T, tam model
        3T), aynı BC (rijit yapışık kasa). Tepe von Mises (Gauss VE SPR
        düğüm) bağıl %2 içinde eşleşmeli — simetri kenarı kayar mesnet
        dönüşümünün bekçisi.
        """
        n_pts, r_i, depth = 3, 0.015, 0.012
        from hrma.engines.solid_rocket_engine import _cached_star_polygon
        poly = _cached_star_polygon(n_pts, r_i, depth)
        sampler = port_radius_sampler_from_polygon(
            np.asarray(poly.exterior.coords, dtype=float))
        mat = Material(E=6.0e6, nu=0.4995, name='htpb')
        T, R = 24, 8

        mesh_dilim = build_grain_section_mesh(sampler, GRAIN_RING_B, T, R,
                                              symmetry_fraction=n_pts)
        res_dilim = solve_plane_strain_section(mesh_dilim, mat, GRAIN_RING_P,
                                               outer_bc='bonded_rigid')
        mesh_tam = build_grain_section_mesh(sampler, GRAIN_RING_B, n_pts * T, R,
                                            symmetry_fraction=1)
        res_tam = solve_plane_strain_section(mesh_tam, mat, GRAIN_RING_P,
                                             outer_bc='bonded_rigid')

        for ad, v1, v2 in (
                ('Gauss maks', res_dilim.max_von_mises,
                 res_tam.max_von_mises),
                ('SPR düğüm maks', res_dilim.max_von_mises_nodal,
                 res_tam.max_von_mises_nodal),
                ('port gerinim maks', res_dilim.max_bore_strain,
                 res_tam.max_bore_strain)):
            rel = abs(v1 - v2) / max(abs(v1), abs(v2))
            assert rel <= 0.02, (
                f'{ad}: dilim {v1:.6g} ile tam model {v2:.6g} '
                f'%{100 * rel:.2f} ayrışıyor')

    def test_tam_halka_seam_dugumleri_birlesik(self):
        mesh = build_grain_section_mesh(GRAIN_RING_A, GRAIN_RING_B, 16, 4,
                                        symmetry_fraction=1)
        g = mesh.node_index_grid
        assert np.array_equal(g[-1], g[0]), 'seam sütunu ilk sütun olmalı'
        assert mesh.sym_start_nodes.size == 0
        # Izgara benzersiz düğümleri tam kapsar (seam kopyası hariç).
        assert np.array_equal(np.unique(g), np.arange(mesh.n_nodes))


# ---------------------------------------------------------------------------
# 4. GEÇERSİZ GEOMETRİ / TEKİL BC = RED (sahte veri yasağı)
# ---------------------------------------------------------------------------
class TestGecersizGirdi:
    def test_port_dis_capi_asarsa_mesh_reddeder(self):
        with pytest.raises(ValueError, match='[Ww]eb'):
            build_grain_section_mesh(0.06, 0.05, 8, 4, symmetry_fraction=8)

    def test_kopru_ters_cap_reddeder(self):
        from hrma.fea.bridge import run_planar_grain_fea
        with pytest.raises(ValueError, match='[Pp]ort'):
            _quiet(run_planar_grain_fea, 'bates', 'apcp',
                   outer_diameter_mm=30.0, core_diameter_mm=100.0,
                   chamber_pressure_bar=40.0)

    def test_tanimsiz_tip_motor_hatasiyla_reddedilir(self):
        from hrma.fea.bridge import run_planar_grain_fea
        with pytest.raises(ValueError, match='grain type'):
            _quiet(run_planar_grain_fea, 'yok_boyle_tip', 'apcp',
                   outer_diameter_mm=100.0, core_diameter_mm=30.0,
                   chamber_pressure_bar=40.0)

    @pytest.mark.parametrize('tip', ['wagon_wheel', 'end_burner'])
    def test_desteklenmeyen_tip_beyanli_red(self, tip):
        """wagon_wheel/end_burner: hata değil BEYANLI NOT_MODELLED —
        redli pakette hiçbir çözüm alanı yok (sahte veri yasağı)."""
        from hrma.fea.bridge import run_planar_grain_fea
        sonuc = _quiet(run_planar_grain_fea, tip, 'apcp',
                       outer_diameter_mm=100.0, core_diameter_mm=30.0,
                       chamber_pressure_bar=40.0)
        assert sonuc['status'] == 'NOT_MODELLED'
        assert sonuc['reason']
        assert sonuc['warning']['code'].startswith('warn.fea.')
        for alan in ('mesh', 'von_mises_nodal', 'bore', 'convergence'):
            assert alan not in sonuc

    def test_tam_halka_serbest_dis_yuzey_tekil_red(self):
        mesh = build_grain_section_mesh(GRAIN_RING_A, GRAIN_RING_B, 16, 4,
                                        symmetry_fraction=1)
        with pytest.raises(ValueError, match='rijit cisim|tekil'):
            solve_plane_strain_section(
                mesh, Material(E=6.0e6, nu=0.4995, name='m'), GRAIN_RING_P,
                outer_bc='free')

    def test_180_derece_dilim_serbest_dis_yuzey_tekil_red(self):
        mesh = build_grain_section_mesh(GRAIN_RING_A, GRAIN_RING_B, 8, 4,
                                        symmetry_fraction=2)
        with pytest.raises(ValueError, match='paralel|tekil'):
            solve_plane_strain_section(
                mesh, Material(E=6.0e6, nu=0.4995, name='m'), GRAIN_RING_P,
                outer_bc='free')

    def test_gecersiz_basinc_reddedilir(self):
        mesh = build_grain_section_mesh(GRAIN_RING_A, GRAIN_RING_B, 8, 4,
                                        symmetry_fraction=8)
        mat = Material(E=6.0e6, nu=0.4995, name='m')
        for p in (float('nan'), -1.0):
            with pytest.raises(ValueError):
                solve_plane_strain_section(mesh, mat, p)

    def test_yildiz_sekilli_olmayan_poligon_reddedilir(self):
        """Orijini içermeyen kesit (ışın kesişimi yok) beyanla reddedilir."""
        th = np.linspace(0.0, 2.0 * np.pi, 33)[:-1]
        kaymis = np.stack([0.005 + 0.001 * np.cos(th),
                           0.001 * np.sin(th)], axis=1)
        sampler = port_radius_sampler_from_polygon(kaymis)
        with pytest.raises(ValueError, match='yıldız-şekilli'):
            sampler(np.array([np.pi]))


# ---------------------------------------------------------------------------
# 5. Işın örnekleyicisi doğruluğu (mesh'in geometri sadakati)
# ---------------------------------------------------------------------------
class TestPoligonOrnekleyici:
    def test_kare_poligon_bilinen_r_theta(self):
        """Birim kare: r(0) = 1, r(π/4) = √2 — kapalı formla karşılaştırma.

        (Bu bekçi geliştirmede gerçek bir işaret hatası yakaladı: ışın
        kesişiminin t parametresi yanlış işaretliyken slotted kesitte
        r(θ) yuva ucunu 21 mm aşıyordu.)
        """
        smp = port_radius_sampler_from_polygon(
            [(1, -1), (1, 1), (-1, 1), (-1, -1)])
        th = np.array([0.0, np.pi / 4.0, np.pi / 2.0, np.pi,
                       3.0 * np.pi / 2.0])
        beklenen = np.array([1.0, np.sqrt(2.0), 1.0, 1.0, 1.0])
        assert np.allclose(smp(th), beklenen, rtol=1e-12)

    def test_motor_slotted_kesiti_fiziksel_aralikta(self):
        """Motor poligonunda r(θ) ∈ [port, yuva ucu] bandında kalmalı."""
        from hrma.engines import solid_rocket_engine as sre
        if not sre.SHAPELY_AVAILABLE:
            pytest.skip('shapely kurulu değil')
        motor = _quiet(sre.SolidRocketEngine, grain_type='slotted',
                       propellant_type='kndx', chamber_diameter=100,
                       core_diameter=30, chamber_pressure=40)
        n, w, d, _a, _c = motor._slotted_params()
        poly = motor._slotted_port_polygon()
        smp = port_radius_sampler_from_polygon(
            np.asarray(poly.exterior.coords, dtype=float))
        r = smp(np.linspace(0.0, 2.0 * np.pi, 721))
        r_port, r_tip = motor.D_core / 2.0, motor.D_core / 2.0 + d
        assert r.min() >= r_port * 0.99
        # Poligonlaştırma köşe payı: yuva ucunun %2'sinden fazla aşılmaz.
        assert r.max() <= r_tip * 1.02


# ---------------------------------------------------------------------------
# 6. UÇ SÖZLEŞMESİ — /api/fea/planar-grain (200 / 422 / 400)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def uc_kos(client, **govde):
    yuk = {'grain_type': 'bates', 'propellant_type': 'apcp',
           'outer_diameter_mm': 100.0, 'core_diameter_mm': 30.0,
           'chamber_pressure_bar': 40.0, 'max_rounds': 2}
    yuk.update(govde)
    resp = _quiet(client.post, PLANAR_ENDPOINT, json=yuk)
    return resp.status_code, resp.get_json()


class TestUcSozlesmesi:
    @pytest.fixture(scope='class')
    def bates_fea(self, client):
        kod, govde = uc_kos(client)
        assert kod == 200, govde
        assert govde['status'] == 'success'
        fea = govde['fea']
        assert fea['status'] == 'ok', fea
        return fea

    def test_200_alanlar_tutarli(self, bates_fea):
        mesh = bates_fea['mesh']
        izgara = mesh['node_index_grid']
        assert len(izgara) == mesh['n_theta'] + 1
        assert len(izgara[0]) == mesh['n_radial'] + 1
        assert len(mesh['nodes']) == mesh['n_nodes']
        assert len(mesh['elems']) == mesh['n_elems']
        # Dilim ızgarası bütün düğümleri tekrarsız kapsar.
        duz = sorted(n for satir in izgara for n in satir)
        assert duz == list(range(mesh['n_nodes']))
        n = mesh['n_nodes']
        assert len(bates_fea['fields']['von_mises_pa']) == n
        assert len(bates_fea['fields']['max_principal_pa']) == n
        assert all(np.isfinite(v)
                   for v in bates_fea['fields']['von_mises_pa'])
        assert mesh['coordinate_units'] == 'm'

    def test_bore_gerinim_blogu_kopma_uzamasiyla_bagli(self, bates_fea):
        """Kabul ölçütü GERİNİM: kopma uzaması SOLID_GRAIN_MECHANICS
        kaydından gelir ve marj = kabiliyet / |maks gerinim| olmalı."""
        from hrma.engines.solid_rocket_engine import SOLID_GRAIN_MECHANICS
        bore = bates_fea['bore']
        assert bore['strain_capability'] == pytest.approx(
            SOLID_GRAIN_MECHANICS['apcp']['strain_capability'])
        assert bore['strain_margin'] == pytest.approx(
            bore['strain_capability'] / abs(bore['max_strain']), rel=1e-9)
        assert len(bore['strain_nodal']) == len(bore['node_ids'])

    def test_akma_sf_yayimlanmaz(self, bates_fea):
        """Tane için akma-SF üretilmez: ölçüt gerinimdir (sahte SF yasak)."""
        assert 'safety_factor' not in bates_fea['fields']
        assert 'min_safety_factor' not in bates_fea['scalars']

    def test_yakinsama_ve_beyan_zinciri(self, bates_fea):
        conv = bates_fea['convergence']
        assert len(conv['history']) >= 2
        assert conv['beyan']
        meta = bates_fea['meta']
        assert meta['girdiler']['_source'].endswith('run_planar_grain_fea')
        assert isinstance(meta['not_modelled'], list) and meta['not_modelled']
        # Viskoelastisite beyanı zorunlu (lineer elastik ön boyutlandırma).
        assert any('VİSKOELAST' in str(m).upper()
                   for m in meta['not_modelled'])

    def test_kalite_olcutleri_sinirlarda(self, bates_fea):
        q = bates_fea['quality']
        ar = np.asarray(q['aspect_ratio'], dtype=float)
        sj = np.asarray(q['scaled_jacobian'], dtype=float)
        assert ar.shape[0] == bates_fea['mesh']['n_elems']
        assert np.all(ar >= 1.0 - 1e-12)
        assert np.all(sj > 0.0) and np.all(sj <= 1.0 + 1e-12)
        th = q['thresholds']
        assert th['aspect_ratio_max'] > 1.0
        assert 0.0 < th['scaled_jacobian_min'] < 1.0

    def test_422_eksik_zorunlu_alan(self, client):
        resp = _quiet(client.post, PLANAR_ENDPOINT,
                      json={'grain_type': 'star'})
        assert resp.status_code == 422
        govde = resp.get_json()
        assert govde['error'] == 'incomplete_planar_grain_input'
        assert set(govde['missing_fields']) == {
            'propellant_type', 'outer_diameter_mm', 'core_diameter_mm',
            'chamber_pressure_bar'}

    def test_400_ters_cap(self, client):
        kod, govde = uc_kos(client, outer_diameter_mm=30.0,
                            core_diameter_mm=100.0)
        assert kod == 400
        assert govde['status'] == 'error'
        assert 'fea' not in govde

    def test_400_taninmayan_tip(self, client):
        kod, govde = uc_kos(client, grain_type='hexagon')
        assert kod == 400
        assert 'grain type' in govde['error']

    def test_200_wagon_wheel_beyanli_red(self, client):
        kod, govde = uc_kos(client, grain_type='wagon_wheel')
        assert kod == 200
        fea = govde['fea']
        assert fea['status'] == 'NOT_MODELLED'
        assert fea['reason']
        for alan in ('mesh', 'fields', 'bore', 'convergence'):
            assert alan not in fea

    def test_eleman_butcesi_beyanla_kisilir(self, client):
        kod, govde = uc_kos(client, grain_type='wagon_wheel',
                            n_theta0=256, n_radial0=32, max_rounds=8)
        assert kod == 200
        limits = govde['fea']['limits']
        assert limits['clamped'] is True
        assert limits['rounds_allowed'] < limits['rounds_requested']
        son = (limits['n_theta0'] * limits['n_radial0']
               * limits['refine_factor'] ** (2 * limits['rounds_allowed']))
        assert son <= limits['max_elems']


# ---------------------------------------------------------------------------
# 7. MUTASYON BEKÇİSİ — Lamé testi B matrisini gerçekten duyuyor mu?
# ---------------------------------------------------------------------------
class TestMutasyonBekcisi:
    """B matrisinin bir terimi bozulunca Lamé bekçisi KIRILMALI.

    Bu, doğrulama testinin çözücünün formülasyonuna gerçekten bağlı
    olduğunun kanıtıdır: mutasyon geçseydi Lamé bekçisi süs olurdu.
    Mutasyon monkeypatch ile geçicidir; kalıcı kod değişmez.
    """

    def test_kayma_satiri_bozulunca_lame_kirilir(self, monkeypatch):
        from hrma.fea import planar_grain as pg

        def bozuk_B(X, xi, eta):
            B, detJ = _point_B_planar(X, xi, eta)
            B = B.copy()
            B[:, 2, 1::2] = 0.0          # γ satırının ∂u_y/∂x payı silindi
            return B, detJ

        monkeypatch.setattr(pg, '_point_B_planar', bozuk_B)
        err = _lame_bore_hoop_err(0.3, *GRAIN_LAME_MESHES[-1])
        assert err > GRAIN_LAME_REL_TOL, (
            'B matrisi bozulduğu hâlde Lamé bekçisi geçti: doğrulama '
            f'çözücüyü duymuyor (hata %{100 * err:.3f})')

    def test_hoop_donusumu_bozulunca_da_kirilir(self, monkeypatch):
        """İkinci mutasyon: ε_y satırı bozulur — K de gerilme de değişir."""
        from hrma.fea import planar_grain as pg

        def bozuk_B(X, xi, eta):
            B, detJ = _point_B_planar(X, xi, eta)
            B = B.copy()
            B[:, 1, 1::2] *= 0.9         # ε_y ← 0.9 · ∂u_y/∂y
            return B, detJ

        monkeypatch.setattr(pg, '_point_B_planar', bozuk_B)
        err = _lame_bore_hoop_err(0.3, *GRAIN_LAME_MESHES[-1])
        assert err > GRAIN_LAME_REL_TOL


# ---------------------------------------------------------------------------
# 8. Mesh üreticisi ayrıntı bekçileri
# ---------------------------------------------------------------------------
class TestMeshUreticisi:
    def test_radyal_katman_alt_siniri_beyanli(self):
        from hrma.fea.mesh_axisym import MIN_ELEMS_THROUGH_WALL
        mesh = build_grain_section_mesh(GRAIN_RING_A, GRAIN_RING_B, 8, 1,
                                        symmetry_fraction=8)
        assert mesh.n_radial == MIN_ELEMS_THROUGH_WALL
        assert mesh.meta['n_radial_alt_sinira_cekildi'] is True

    def test_dilim_simetri_kenarlari_yayimlanir(self):
        mesh = build_grain_section_mesh(GRAIN_RING_A, GRAIN_RING_B, 8, 4,
                                        symmetry_fraction=6)
        assert mesh.sym_start_nodes.size == mesh.n_radial + 1
        assert mesh.sym_end_nodes.size == mesh.n_radial + 1
        assert mesh.sym_start_angle == pytest.approx(0.0)
        assert mesh.sym_end_angle == pytest.approx(2.0 * np.pi / 6.0)
        assert 'AYNA SİMETRİ' in mesh.meta['simetri']

    def test_elemanlar_ccw_ve_pozitif_alan(self):
        mesh = build_grain_section_mesh(GRAIN_RING_A, GRAIN_RING_B, 12, 4,
                                        symmetry_fraction=4)
        P = mesh.nodes[mesh.elems]
        x, y = P[:, :, 0], P[:, :, 1]
        alan = 0.5 * np.sum(x * np.roll(y, -1, axis=1)
                            - np.roll(x, -1, axis=1) * y, axis=1)
        assert np.all(alan > 0.0), 'eleman köşe sırası CCW olmalı'

    def test_min_theta_sabiti_alt_sinir(self):
        mesh = build_grain_section_mesh(GRAIN_RING_A, GRAIN_RING_B, 1, 4,
                                        symmetry_fraction=8)
        assert mesh.n_theta >= MIN_THETA_DIVISIONS_WEDGE
