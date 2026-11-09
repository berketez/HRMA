"""V306/TANE NR-16 (S1) — gövdeye yapıştırılmış tanede analitik gerinim ⟷
tane kesiti FEA aynı yük kümesini taşır.

ÖLÇÜLDÜ (docs/scofield/raw/OH/V306/tane/nr16_once.json, örnek KNDX BATES
75 mm, 60 bar, gövdeye yapıştırılmış): analitik port gerinimi %2,364
(emniyet 0,846 < 1, "çatlama riski") ⟷ tane kesiti FEA %0,412 (marj 4,85).
Kök: analitik yol kürleme/soğuma büzülmesinin gövdeyle kısıtlanmasından
gelen ısıl gerinimi (%1,833) taşıyor, düzlem FEA yalnız port basıncını
yüklüyordu. Onarım: FEA ısıl yükü ilk gerinim olarak taşır (α·ΔT, aynı
kaynak: ``SolidRocketEngine._grain_thermal_load``).

Bekçiler:
* kapalı biçim: gövdeye bağlı (dış yüzey tutulu) kalın cidarlı silindir,
  düzlem şekil değiştirme, ısıl + basınç (Lamé + üniform sıcaklık terimi,
  Timoshenko & Goodier) — port gerinimi, çember ve radyal gerilme, σ_z;
* ağ yakınsaması (ısıl yükte hata inceltmede düşer);
* serbest cisimde üniform ısıl gerinim gerilmesizdir (yama testi);
* ``thermal_strain = 0`` → bugünkü çözüm BİT-AYNI;
* ısıl yük TEK kaynaktan: FEA'nın ısıl payı analitik bloğun ısıl payına
  oturur (ikisi de dış yüzeyi tutulu tanede aynı kapalı biçim);
* kartuş yüklü tanede uç sonucu NR-16 öncesi ölçümle bit-aynı;
* örnek motorun iki yolu aynı hükmü verir (60 bar, gövdeye yapıştırılmış);
* uçta yerleşim / sıcaklık girdisi sessizce varsayılana düşmez (422);
* küçük-gerinim aralığının dışında pay sayısı yazılmaz ama kapasite
  geçerlilik aralığında aşılıyorsa hüküm kurulur;
* panel: yük kümesi, yük payları, analitik yol ve TR virgüllü sayılar.
"""
import contextlib
import io
import json
import pathlib
import shutil
import subprocess

import numpy as np
import pytest

from hrma.engines.solid_rocket_engine import (SOLID_GRAIN_MECHANICS,
                                              SOLID_THERMAL)
from hrma.fea.mesh_planar import build_grain_section_mesh
from hrma.fea.planar_grain import (
    SMALL_STRAIN_LIMIT,
    solve_grain_with_refinement,
    solve_plane_strain_section,
)
from hrma.fea.structural_axisym import Material
from tests.support.kanit import kanit_gerekli

KOK = pathlib.Path(__file__).resolve().parents[1]
KANIT = KOK / 'docs' / 'scofield' / 'raw' / 'OH' / 'V306' / 'tane'
PANEL_JS = KOK / 'hrma' / 'static' / 'js' / 'fea_panel.js'
ORNEK = KOK / 'examples' / 'Example Solid KNDX BATES 75mm.hrma'
NODE = shutil.which('node')
needs_node = pytest.mark.skipif(NODE is None, reason='node kurulu değil')

# Halka: örnek KNDX BATES kesitiyle aynı oran (port 32 mm, dış 75 mm).
A, B = 0.016, 0.0375
P = 6.0e6
#: Kapalı biçim ⟷ FEA bağıl toleransı. ÖLÇÜLDÜ (6144 eleman, 1/8 dilim):
#: gerinim hatası 5,5e-5 (ν 0,35) / 4,8e-7 (ν 0,4995) — çokgen port.
TOL_GERINIM = 1e-3
#: SPR sınır gerilmesi için (tests/test_fea_planar_grain.py GRAIN_LAME_REL_TOL
#: ile aynı mertebe; gerilme sınır değeri gerinimden yavaş oturur).
TOL_GERILME = 2e-2


def kapali_bicim(a, b, E, nu, p, eps_t, r):
    """Dış yüzeyi tutulu (u(b) = 0) kalın cidarlı silindir, düzlem şekil
    değiştirme, port basıncı p + üniform serbest ısıl gerinim eps_t = α·ΔT.

        u = D r + C2 / r,  K = E/((1+ν)(1−2ν)),  T0 = E·α·ΔT/(1−2ν)
        σ_r = K[D − (1−2ν)C2/r²] − T0,  σ_θ = K[D + (1−2ν)C2/r²] − T0
        σ_z = ν(σ_r + σ_θ) − E·α·ΔT
        σ_r(a) = −p,  u(b) = 0  →  D = (T0 − p)/(K(1 + (1−2ν)b²/a²)),
                                   C2 = −D b²
    (Timoshenko & Goodier, kalın cidarlı silindir + üniform sıcaklık;
    motorun analitik bloğu u_kasa = 0 ile aynı çözüm.)
    """
    K = E / ((1 + nu) * (1 - 2 * nu))
    T0 = E * eps_t / (1 - 2 * nu)
    D = (T0 - p) / (K * (1 + (1 - 2 * nu) * (b / a) ** 2))
    C2 = -D * b * b
    s_r = K * (D - (1 - 2 * nu) * C2 / r ** 2) - T0
    s_t = K * (D + (1 - 2 * nu) * C2 / r ** 2) - T0
    return {'eps_bore': D + C2 / a ** 2, 'u': D * r + C2 / r,
            's_r': s_r, 's_t': s_t, 's_z': nu * (s_r + s_t) - E * eps_t}


def _sessiz(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def _kayit_durumu(anahtar):
    """(ν, E, α·ΔT) — malzeme kaydından (tek kaynak) ve ortam varsayılanından."""
    m = SOLID_GRAIN_MECHANICS[anahtar]
    dT = SOLID_THERMAL['ambient_temperature_k'] - m['cure_temperature_k']
    return (m['poisson_ratio'], m['elastic_modulus_pa'],
            m['thermal_expansion_1k'] * dT)


#: KNDX (şeker ailesi) kaydı, HTPB (apcp) kaydı ve sıkıştırılabilir bir
#: doğrulama malzemesi (ν 0,3; ısıl gerinim -5e-4 — yalnız kapalı biçim
#: karşılaştırması içindir, ürün kaydı değildir).
NR16_MALZEME_DURUMLARI = [
    _kayit_durumu('kndx'),
    _kayit_durumu('apcp'),
    (0.3, 200.0e9, -5.0e-4),
]


# ---------------------------------------------------------------------------
# 1. KAPALI BİÇİM DOĞRULAMASI
# ---------------------------------------------------------------------------
class TestKapaliBicim:

    @pytest.mark.parametrize('nu,E,eps_t', NR16_MALZEME_DURUMLARI)
    @pytest.mark.parametrize('yuk', ['isil', 'basinc', 'ikisi'])
    def test_port_gerinimi(self, nu, E, eps_t, yuk):
        p = 0.0 if yuk == 'isil' else P
        et = 0.0 if yuk == 'basinc' else eps_t
        ref = solve_grain_with_refinement(
            A, B, Material(E=E, nu=nu, yield_strength=None, name='t'), p,
            symmetry_fraction=8, thermal_strain=et, max_rounds=3)
        ana = kapali_bicim(A, B, E, nu, p, et, A)['eps_bore']
        assert ref.result.max_bore_strain == pytest.approx(
            ana, rel=TOL_GERINIM)

    @pytest.mark.parametrize('nu,E,eps_t', NR16_MALZEME_DURUMLARI[:2])
    def test_gerilmeler_ve_sigma_z(self, nu, E, eps_t):
        """Port düğümlerinde σ_r = −p, σ_θ ve σ_z kapalı biçime oturur
        (ısıl terim −T0 ve σ_z'deki −E·α·ΔT dahil)."""
        mesh = build_grain_section_mesh(A, B, 96, 48, symmetry_fraction=8)
        res = solve_plane_strain_section(
            mesh, Material(E=E, nu=nu, yield_strength=None, name='t'), P,
            thermal_strain=eps_t)
        ids = mesh.node_index_grid[:, 0]
        xy = mesh.nodes[ids]
        th = np.arctan2(xy[:, 1], xy[:, 0])
        s = res.stress_nodal[ids]
        c, sn = np.cos(th), np.sin(th)
        s_r = s[:, 0] * c ** 2 + s[:, 1] * sn ** 2 + 2 * s[:, 3] * c * sn
        s_t = s[:, 0] * sn ** 2 + s[:, 1] * c ** 2 - 2 * s[:, 3] * c * sn
        ana = kapali_bicim(A, B, E, nu, P, eps_t, A)
        olcek = max(abs(ana['s_t']), abs(ana['s_r']), abs(ana['s_z']))
        assert np.max(np.abs(s_r - ana['s_r'])) / olcek <= TOL_GERILME
        assert np.max(np.abs(s_t - ana['s_t'])) / olcek <= TOL_GERILME
        assert np.max(np.abs(s[:, 2] - ana['s_z'])) / olcek <= TOL_GERILME

    def test_yer_degistirme_radyal(self):
        nu, E, eps_t = NR16_MALZEME_DURUMLARI[0]
        mesh = build_grain_section_mesh(A, B, 96, 48, symmetry_fraction=8)
        res = solve_plane_strain_section(
            mesh, Material(E=E, nu=nu, yield_strength=None, name='t'), P,
            thermal_strain=eps_t)
        ids = mesh.node_index_grid[:, 0]
        xy = mesh.nodes[ids]
        th = np.arctan2(xy[:, 1], xy[:, 0])
        u = res.displacement[ids]
        u_r = u[:, 0] * np.cos(th) + u[:, 1] * np.sin(th)
        ana = kapali_bicim(A, B, E, nu, P, eps_t, A)['u']
        assert np.max(np.abs(u_r - ana)) / abs(ana) <= TOL_GERINIM

    @pytest.mark.parametrize('nu,E,eps_t', NR16_MALZEME_DURUMLARI[:2])
    def test_ag_yakinsamasi(self, nu, E, eps_t):
        ana = kapali_bicim(A, B, E, nu, P, eps_t, A)['eps_bore']
        hatalar = []
        for nth, nrad in ((6, 3), (12, 6), (24, 12)):
            mesh = build_grain_section_mesh(A, B, nth, nrad,
                                            symmetry_fraction=8)
            res = solve_plane_strain_section(
                mesh, Material(E=E, nu=nu, yield_strength=None, name='t'),
                P, thermal_strain=eps_t)
            hatalar.append(abs(res.max_bore_strain - ana) / abs(ana))
        assert hatalar[0] > hatalar[1] > hatalar[2], hatalar

    def test_serbest_cisimde_isil_gerinim_gerilmesiz(self):
        """Yama testi: dış yüzey serbest, yalnız üniform ısıl gerinim →
        gerilme sıfır, port lif gerinimi α·ΔT (kartuş yüklü tanenin
        fiziği; serbest dış yüzey çözücünün doğrulama kipi)."""
        nu, E, eps_t = NR16_MALZEME_DURUMLARI[0]
        mesh = build_grain_section_mesh(A, B, 24, 12, symmetry_fraction=8)
        res = solve_plane_strain_section(
            mesh, Material(E=E, nu=nu, yield_strength=None, name='t'), 0.0,
            outer_bc='free', thermal_strain=eps_t)
        olcek = E * abs(eps_t)
        assert np.max(np.abs(res.stress_gauss[..., :2])) / olcek < 1e-9
        # σ_z = −E·α·ΔT (ε_z = 0 kısıtı) — düzlem dışı tutulu uçlar
        assert np.allclose(res.stress_gauss[..., 2], -E * eps_t,
                           rtol=1e-9)
        # ε_θ = (1+ν)·α·ΔT: ε_z = 0 kısıtı düzlem içine aktarır
        assert res.max_bore_strain == pytest.approx(
            (1 + nu) * eps_t, rel=1e-6)

    def test_isil_yuk_sifirken_bit_ayni(self):
        mesh = build_grain_section_mesh(A, B, 24, 12, symmetry_fraction=8)
        mat = Material(E=1e9, nu=0.35, yield_strength=None, name='t')
        a = solve_plane_strain_section(mesh, mat, P, strain_capability=0.02)
        b = solve_plane_strain_section(mesh, mat, P, strain_capability=0.02,
                                       thermal_strain=0.0)
        assert np.array_equal(a.displacement, b.displacement)
        assert np.array_equal(a.stress_gauss, b.stress_gauss)
        assert np.array_equal(a.stress_nodal, b.stress_nodal)
        assert a.max_bore_strain == b.max_bore_strain
        assert a.strain_margin == b.strain_margin

    @pytest.mark.parametrize('kotu', [float('nan'), float('inf'), 1.5, -2.0])
    def test_gecersiz_isil_gerinim_reddedilir(self, kotu):
        mesh = build_grain_section_mesh(A, B, 8, 4, symmetry_fraction=8)
        with pytest.raises(ValueError):
            solve_plane_strain_section(
                mesh, Material(E=1e9, nu=0.35, yield_strength=None,
                               name='t'), P, thermal_strain=kotu)


# ---------------------------------------------------------------------------
# 2. UÇ: tek kaynak, kartuş bit-aynılığı, örnek motorun hükmü, ret kapısı
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _ornek_alanlar():
    return dict(json.loads(ORNEK.read_text(encoding='utf-8'))
                ['inputs']['fields'])


def _hesap_ve_fea(client, **ek):
    govde = _ornek_alanlar()
    govde.update(ek)
    r = _sessiz(client.post, '/calculate_solid', json=govde)
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    gs = j['structural_analysis']['grain_structural']
    gd = j['grain_design']
    # Panel gövdesi (grainParamsFromResults ile aynı kural)
    p = {'grain_type': gd.get('grain_type') or j['grain_type'],
         'propellant_type': j['propellant_type'],
         'outer_diameter_mm': gd['outer_diameter_mm'],
         'core_diameter_mm': gd['inner_diameter_mm'],
         'chamber_pressure_bar': j['chamber_pressure'],
         'grain_length_mm': gd.get('grain_length_mm')}
    if gd.get('grain_type') == 'star':
        p.update(star_points=gd['star_points'], star_radius=gd['point_depth'])
    if gs.get('grain_support_source') == 'user input':
        p['grain_support'] = gs['grain_support']
    p['ambient_temp'] = gs['storage_temperature_k']
    r2 = _sessiz(client.post, '/api/fea/planar-grain', json=p)
    assert r2.status_code == 200, r2.get_json()
    return gs, r2.get_json()['fea']


class TestUc:

    @pytest.fixture(scope='class')
    def yapisik60(self, client):
        return _hesap_ve_fea(client, grain_support='case_bonded',
                             chamber_pressure=60)

    def test_ornek_iki_yol_ayni_hukum(self, yapisik60):
        """BULGULAR_RC NR-16: aynı tane, aynı koşu — analitik 'çatlar'
        derken FEA 4,85 marj veriyordu. İki yol artık aynı hükmü verir."""
        gs, fea = yapisik60
        assert gs['strain_safety_factor'] < 1.0
        assert fea['bore']['strain_margin'] < 1.0
        # Ölçülen (nr16_sonra.json): analitik %2,364 ⟷ FEA %2,245.
        assert 100 * fea['bore']['max_strain'] == pytest.approx(2.2448,
                                                                abs=2e-3)

    def test_isil_pay_analitik_blokla_ayni(self, yapisik60):
        """Isıl yük TEK kaynaktan: gövde ısıl yükte iki yolda da tutulu
        (analitik u_kasa yalnız basınçtan), ısıl paylar aynı kapalı
        biçimdir; fark yalnız çokgen port ayrıklaştırması kadardır."""
        gs, fea = yapisik60
        lc = fea['bore']['load_components']
        assert 100 * lc['thermal_at_governing_station'] == pytest.approx(
            gs['thermal_only_bore_strain_percent'], rel=TOL_GERINIM)
        assert fea['loads']['free_thermal_strain'] == pytest.approx(
            gs['free_thermal_strain'], rel=1e-15)
        assert fea['loads']['cure_cooldown_shrinkage'] is True
        assert fea['loads']['grain_support'] == gs['grain_support']
        assert fea['scalars']['free_thermal_strain'] == \
            fea['loads']['free_thermal_strain']

    def test_fark_yalniz_govde_esnemesi(self, yapisik60):
        """Kalan fark tanım farkıdır: analitik basınç payı gövdenin basınç
        altındaki esnemesini içerir, FEA gövdeyi rijit tutar."""
        gs, fea = yapisik60
        lc = fea['bore']['load_components']
        assert 100 * lc['pressure_at_governing_station'] < \
            gs['pressure_only_bore_strain_percent']
        assert gs['load_set']['case_expansion_under_pressure'] is True
        assert fea['loads']['case_expansion_under_pressure'] is False
        # Analitik bileşenler toplamı yayımlanan toplamdır (Kt = 1, bates)
        assert gs['stress_concentration_factor'] == 1.0
        assert gs['bore_strain_percent'] == pytest.approx(
            gs['pressure_only_bore_strain_percent']
            + gs['thermal_only_bore_strain_percent'], rel=1e-12)

    def test_analitik_blok_ayni_gecerlilik_sinirini_beyan_eder(self,
                                                               yapisik60):
        """Analitik blok da doğrusal küçük-gerinim çözümüdür: FEA'nın hüküm
        eşiği (tek kaynak) yanında yayımlanır; sayılar değişmez."""
        gs, _fea = yapisik60
        assert gs['small_strain_limit'] == SMALL_STRAIN_LIMIT
        assert gs['small_strain_limit_exceeded'] is False   # %2,364 < %5
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        e = SolidRocketEngine(grain_type='bates', propellant_type='apcp',
                              chamber_diameter=100.0, core_diameter=30.0,
                              chamber_pressure=40.0)
        g = e._calculate_grain_structural()
        assert g['bore_strain_percent'] > 100 * SMALL_STRAIN_LIMIT
        assert g['small_strain_limit_exceeded'] is True

    def test_kartus_yuklu_once_olcumuyle_bit_ayni(self, client):
        """NR-16 öncesi ölçüm (nr16_once.json, taban b890da443): kartuş
        yüklü tanede FEA yalnız basınç taşıyordu; sonuç değişmez."""
        once = json.loads(kanit_gerekli(KANIT / 'nr16_once.json').read_text(
            encoding='utf-8'))
        for pc in (40, 60):
            gs, fea = _hesap_ve_fea(client, grain_support='cartridge_loaded',
                                    chamber_pressure=pc)
            kayit = once[f'cartridge_loaded/{pc}/bates']
            assert 100 * fea['bore']['max_strain'] == \
                kayit['fea_max_bore_strain_percent']
            assert fea['bore']['strain_margin'] == kayit['fea_strain_margin']
            assert fea['loads']['cure_cooldown_shrinkage'] is False
            assert fea['loads']['free_thermal_strain'] == 0.0
            # Analitik blok da bit-aynı (yalnız tek kaynağa taşındı)
            assert gs['bore_strain_percent'] == \
                kayit['analitik_bore_strain_percent']

    def test_yerlesim_verilmezse_motor_varsayilani(self, client):
        """Uç, /calculate_solid ile AYNI varsayılanı aynı beyanla uygular."""
        r = _sessiz(client.post, '/api/fea/planar-grain', json={
            'grain_type': 'bates', 'propellant_type': 'kndx',
            'outer_diameter_mm': 75.0, 'core_diameter_mm': 32.0,
            'chamber_pressure_bar': 40.0, 'max_rounds': 1})
        assert r.status_code == 200
        L = r.get_json()['fea']['loads']
        assert L['grain_support'] == 'case_bonded'
        assert L['grain_support_source'] == 'default (not supplied)'
        assert L['cure_cooldown_shrinkage'] is True

    @pytest.mark.parametrize('alan,deger', [
        ('grain_support', 'glued'),
        ('ambient_temp', 999.0),
        ('ambient_temp', 'sicak'),
    ])
    def test_yuk_girdisi_sessizce_dusmez(self, client, alan, deger):
        govde = {'grain_type': 'bates', 'propellant_type': 'kndx',
                 'outer_diameter_mm': 75.0, 'core_diameter_mm': 32.0,
                 'chamber_pressure_bar': 40.0, 'max_rounds': 1, alan: deger}
        r = _sessiz(client.post, '/api/fea/planar-grain', json=govde)
        assert r.status_code == 422, r.get_json()
        j = r.get_json()
        assert [f['field'] for f in j['invalid_fields']] == [alan]
        assert 'mesh' not in j and 'fea' not in j

    def test_kucuk_gerinim_disinda_kapasite_hukmu(self, client):
        """Gövdeye yapıştırılmış KNDX star: FEA tepe gerinimi küçük-gerinim
        eşiğinin üstünde → pay sayısı yok.

        V306/KATI-KALAN (kalem 3) — BEKLENTİ DEĞİŞTİ: bu kesitte kabul
        büyüklüğü (port gerinimi) ağla OTURMUYOR (keskin iç köşe tekilliği;
        ölçüldü: son turda %35,7 değişim, tolerans %1). NR-16'nın
        'exceeded' hükmü λ_c = kapasite / tepe oranından, yani her turda
        büyüyen tepe değerden kuruluyordu: ağın sayısıdır, tanenin değil
        (gerçek değer köşe yuvarlatmasına bağlı, HRMA kesiti taşımıyor).
        FEA hükmü artık 'undetermined' + adlı neden; λ_c sayıları da
        yayımlanmaz. Kapasite aşımı hükmü analitik yolda (dairesel port
        gerinimi kapasiteyi zaten aşıyor, k < 1) kalır — aşağıda."""
        gs, fea = _hesap_ve_fea(client, grain_support='case_bonded',
                                grain_type='star', chamber_pressure=60)
        bore = fea['bore']
        assert abs(bore['max_strain']) > SMALL_STRAIN_LIMIT
        assert bore['strain_margin'] is None
        assert bore['small_strain_status'] == 'asildi'
        assert fea['convergence']['acceptance']['converged'] is False
        assert bore['strain_margin_withheld']['reason_code'] == \
            'acceptance_not_converged_sharp_corner'
        cv = bore['capability_verdict']
        assert cv['status'] == 'undetermined'
        assert cv['withheld_reason_code'] == \
            'acceptance_not_converged_sharp_corner'
        assert cv['load_fraction_at_capability'] is None
        assert cv['peak_strain_at_capability'] is None
        # Analitik yol da kapasite aşımı diyor (aynı hüküm). V306/KATI-TANE
        # (K2): star köşe yığılması çözülmez, SF yayımlanmaz; hüküm dairesel
        # port geriniminin kapasiteyi zaten aşmasından (izin verilen yığılma
        # katsayısı < 1) gelir.
        assert gs['strain_safety_factor'] is None
        assert gs['allowable_concentration_factor'] < 1.0
        assert gs['crack_propagation_risk'] == 'capability_exceeded'


# ---------------------------------------------------------------------------
# 3. PANEL — yük kümesi, paylar, analitik yol, TR ondalık, hüküm
# ---------------------------------------------------------------------------
PANEL_HARNESS = r"""
'use strict';
const fs = require('fs');
const job = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const nodes = {};
function makeNode(id) {
    const n = { id: id, style: {}, checked: true, listeners: {},
        addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
        setAttribute() {}, appendChild(c) { return c; },
        querySelectorAll() { return []; }, querySelector() { return null; } };
    let html = '';
    Object.defineProperty(n, 'innerHTML', { get() { return html; },
        set(v) { html = String(v); } });
    Object.defineProperty(n, 'firstElementChild', { get() { return makeNode('panel'); } });
    return n;
}
global.document = {
    getElementById(id) { if (!(id in nodes)) nodes[id] = makeNode(id); return nodes[id]; },
    createElement() { return makeNode(null); },
    querySelector() { return makeNode('rg'); },
    addEventListener() {},
};
global.Plotly = { react() {} };
global.window = global;
window.I18N = {
    lang: job.lang,
    number(v, d) {
        const t = (typeof d === 'number') ? v.toFixed(d) : String(v);
        return job.lang === 'tr' ? t.replace('.', ',') : t;
    },
    decimalText(t) {
        return (job.lang === 'tr' && /^[+-]?\d+\.\d+$/.test(t)) ? t.replace('.', ',') : t;
    },
    t(k, f) { return f; }, tf(k, p, f) { return f; },
    serverText(t) { return t; }, applyTo() {}, onChange() {},
};
require(process.argv[3]);
window.GrainFeaPanel.init({ anchorId: 'yok', paramsProvider() { return null; },
                            analyticProvider() { return job.analytic; } });
window.GrainFeaPanel.applyPayload(job.fea, null);
const verdict = window.FeaCenterTenants.planarGrain.verdict({ fea: job.fea });
const params = window.GrainFeaPanel._paramsFromResults(job.results);
process.stdout.write(JSON.stringify({
    badges: nodes['grainfea_badges'] ? nodes['grainfea_badges'].innerHTML : '',
    convNote: nodes['grainfea_conv_note'] ? nodes['grainfea_conv_note'].innerHTML : '',
    verdict: verdict, params: params }));
"""


def _panel(tmp_path, fea, analytic, lang, results=None):
    betik = tmp_path / 'p.js'
    betik.write_text(PANEL_HARNESS, encoding='utf-8')
    girdi = tmp_path / 'job.json'
    girdi.write_text(json.dumps({'fea': fea, 'analytic': analytic,
                                 'lang': lang, 'results': results or {}}),
                     encoding='utf-8')
    proc = subprocess.run([NODE, str(betik), str(girdi), str(PANEL_JS)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@needs_node
class TestPanel:

    @pytest.fixture(scope='class')
    def yapisik(self, client):
        return _hesap_ve_fea(client, grain_support='case_bonded',
                             chamber_pressure=60)

    def test_yukler_paylar_ve_analitik_yan_yana(self, yapisik, tmp_path):
        gs, fea = yapisik
        out = _panel(tmp_path, fea, gs, 'en')
        b = out['badges']
        assert 'LOADS: bore pressure 60.0 bar + cure/cool-down shrinkage' in b
        assert 'STRAIN PARTS at the governing station: pressure 0.41% + ' \
               'thermal 1.83%' in b
        assert 'ANALYTIC PATH' in b and 'bore strain 2.364%' in b
        assert 'WHY THE TWO PATHS DIFFER' in b
        # Ham alan adı kullanıcıya gösterilmez
        assert 'fields.max_principal_pa' not in b

    def test_tr_virgullu_ondalik(self, yapisik, tmp_path):
        gs, fea = yapisik
        out = _panel(tmp_path, fea, gs, 'tr')
        b = out['badges']
        assert '2,24' in b and '2,364' in b and '0,89' in b
        assert '10,05' in b                    # en kötü eleman en-boy oranı
        # TR ekranda hiçbir rozet sayısı noktalı ondalık taşımaz
        import re
        metin = re.sub(r'<[^>]+>', ' ', b + ' ' + out['convNote'])
        assert 'YAKINSADI' in out['convNote'] or 'YAKINSAMADI' in out['convNote']
        assert not re.findall(r'\d\.\d', metin), \
            re.findall(r'.{30}\d\.\d.{10}', metin)

    def test_analitik_baska_yerlesimse_basilmaz(self, yapisik, tmp_path):
        gs, fea = yapisik
        bayat = dict(gs, grain_support='cartridge_loaded')
        out = _panel(tmp_path, fea, bayat, 'en')
        assert 'ANALYTIC PATH' not in out['badges']

    def test_kapasite_hukmu_rozet_ve_merkez(self, client, tmp_path):
        gs, fea = _hesap_ve_fea(client, grain_support='case_bonded',
                                grain_type='star', chamber_pressure=60)
        # V306/KATI-KALAN (kalem 3): star kabul büyüklüğü oturmuyor → pay ve
        # FEA kapasite hükmü yok; rozet ve Merkez satırı nedeni söyler.
        out = _panel(tmp_path, fea, gs, 'en')
        assert 'STRAIN MARGIN NOT PUBLISHED' in out['badges']
        assert 'sharp inner-corner singularity' in out['badges']
        assert 'STRAIN CAPABILITY EXCEEDED' not in out['badges']
        assert 'no strain capability record' not in out['badges']
        assert out['verdict']['kind'] == 'warn'
        assert out['verdict']['key'] == \
            'panel.grain.verdictMarginUnconvergedCorner'
        # Oturan kabul büyüklüğünde 'exceeded' hükmünün çizimi değişmedi
        # (çizim yolu; fikstür sözleşme alanlarıyla kurulur).
        oturan = json.loads(json.dumps(fea))
        oturan['convergence']['acceptance']['converged'] = True
        oturan['bore']['strain_margin_withheld'] = None
        oturan['bore']['capability_verdict'] = dict(
            oturan['bore']['capability_verdict'], status='exceeded',
            load_fraction_at_capability=0.25,
            peak_strain_at_capability=0.03)
        out = _panel(tmp_path, oturan, gs, 'en')
        assert 'STRAIN CAPABILITY EXCEEDED' in out['badges']
        assert out['verdict']['kind'] == 'err'
        assert out['verdict']['key'] == 'panel.grain.verdictCapabilityExceeded'

    def test_parametreler_yuk_girdilerini_tasir(self, tmp_path):
        sonuc = {'grain_design': {'grain_type': 'bates',
                                  'outer_diameter_mm': 75.0,
                                  'inner_diameter_mm': 32.0},
                 'propellant_type': 'kndx', 'chamber_pressure': 60.0,
                 'structural_analysis': {'grain_structural': {
                     'grain_support': 'case_bonded',
                     'grain_support_source': 'default (not supplied)',
                     'storage_temperature_k': 298.0}}}
        out = _panel(tmp_path, None, None, 'en', results=sonuc)
        assert out['params']['ambient_temp'] == 298.0
        # Varsayılan yerleşim gönderilmez: uç aynı varsayılanı aynı beyanla
        # uygular ('default (not supplied)').
        assert 'grain_support' not in out['params']
        sonuc['structural_analysis']['grain_structural'][
            'grain_support_source'] = 'user input'
        out = _panel(tmp_path, None, None, 'en', results=sonuc)
        assert out['params']['grain_support'] == 'case_bonded'
