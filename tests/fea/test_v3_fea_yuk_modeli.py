"""
v3 fea-yuk (OH-DK-04) — FEA köprüsünün yük modeli bekçileri.

Neyi kilitler (her biri ters mutasyonla KIRMIZI — docs/scofield/raw/OH/V3/
fea-yuk/mutasyon.md):

  1. p(x): iç yüzey basıncı hazne silindirinde P_c, lülede 1B izantropik
     statik basınçtır; ürünün değerleri BAĞIMSIZ bir kökten (bu dosyanın
     kendi alan-Mach tersi + kendi formülü, ``hrma.flow.quasi1d``
     KULLANILMAZ) aynı çıkar.
  2. Kapalı uç kuvveti VAR: F_uç = P_c·π·r_0²; çıkış mesnetli düz kapalı
     uçlu silindirde σ_z Lamé kapalı uç değerine oturur, kuvvetsiz hâlde
     sıfırdır.
  3. Kuvvet dengesi: yayımlanan çözümün mesnet eksenel tepkisi, bu
     dosyanın kendi itki fonksiyonuyla hesapladığı analitik net eksenel
     basınç kuvvetinin negatifine (ürün sabiti KUVVET_DENGESI_TOL içinde)
     eşittir; tutmazsa hüküm ``kuvvet_dengesi_tutmadi`` ile geri çekilir.
  4. γ yokken/geçersizken sabit P_c geri dönüşü BEYANLA basılır.
  5. Analitik ⟷ FEA, üç istasyon (hazne ortası, boğaz, genişleyen bölüm),
     iki mesnet kipi; toleranslar HESAPTAN ÖNCE yazıldı
     (docs/scofield/raw/OH/V3/fea-yuk/toleranslar_once.md, commit b109c322).
  6. Kapsam: sonuç YALNIZ basınç yüklemesidir (ısıl yük ve sıcaklığa bağlı
     dayanım kapsam dışı) — künyede ve uç yanıtında.

Örnek motor tek kez (modül kapsamı) hesaplanır; FEA ürün ucundan
(/api/fea/structural) ya da köprüden, ürün varsayılanlarıyla sürülür.
"""

import contextlib
import copy
import io
import math

import numpy as np
import pytest
from scipy.integrate import quad
from scipy.optimize import brentq

from hrma.fea import bridge
from hrma.fea import structural_axisym as sa
from hrma.fea.mesh_axisym import build_wall_mesh
from tests.fea.test_yapisal_dogrulama import LAME_REL_TOL

pytestmark = pytest.mark.filterwarnings('ignore::RuntimeWarning')

# --- Toleranslar: toleranslar_once.md (HESAPTAN ÖNCE, b109c322) -----------
S1_TOL = LAME_REL_TOL            # hazne ortası Lamé (projenin Lamé çapası)
S2_DENGE_TOL = 0.02              # boğaz σ_z ortalaması ⟷ kesit dengesi
S2_FE_PAYI = 0.02                # F-19 ince cidar ikinci yolunda FE payı
S2_BANT_GENISLETME = 0.10        # boğaz zar bandı (eğilme payı)
S3_TOL = 0.05                    # genişleyen bölüm ince kabuk zarı
#: Bağımsız kök/integral ile ürünün değeri arasındaki bağıl fark tavanı
#: (iki kök çözücü de 1e-13 mertebesinde durur).
PX_KOK_TOL = 1e-9


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    return app.test_client()


@pytest.fixture(scope='module')
def ornek_sivi(istemci):
    """examples/ sıvı örnek motoru, FORM yolu (F1 'ornek:liquid' kurulumu)."""
    from tests.support import form_defaults
    from tests.test_example_projects import (ENDPOINTS, HEADERS,
                                             load_example_doc)
    alanlar = dict(load_example_doc('liquid')['inputs']['fields'])
    govde = form_defaults.form_yuku('liquid', alanlar)
    r = _sessiz(istemci.post, ENDPOINTS['liquid'], json=govde,
                headers=HEADERS)
    assert r.status_code == 200
    return r.get_json()


@pytest.fixture(scope='module')
def ornek_fea(ornek_sivi):
    """Ürün varsayılanlarıyla köprü koşusu (uçla aynı tur bütçesi)."""
    from hrma.app import FEA_STRUCTURAL_DEFAULT_ROUNDS
    return _sessiz(bridge.run_structural_from_motor, ornek_sivi,
                   max_rounds=FEA_STRUCTURAL_DEFAULT_ROUNDS)


# --- BAĞIMSIZ 1B izantropik kâhin (ürün kodunu kullanmaz) -----------------
def _alan_orani(M, g):
    return (1.0 / M) * ((2.0 / (g + 1.0)) * (1.0 + 0.5 * (g - 1.0) * M * M)
                        ) ** ((g + 1.0) / (2.0 * (g - 1.0)))


def _mach(oran, g, ses_ustu):
    if oran <= 1.0 + 1e-15:
        return 1.0
    if ses_ustu:
        return brentq(lambda M: _alan_orani(M, g) - oran, 1.0 + 1e-12, 60.0,
                      xtol=1e-15, rtol=1e-15, maxiter=400)
    return brentq(lambda M: _alan_orani(M, g) - oran, 1e-10, 1.0 - 1e-12,
                  xtol=1e-16, rtol=1e-15, maxiter=400)


def _p_oran(M, g):
    """p/P_c = (1 + (γ−1)/2·M²)^(−γ/(γ−1)) — Sutton & Biblarz Eş. 3-7."""
    return (1.0 + 0.5 * (g - 1.0) * M * M) ** (-g / (g - 1.0))


def _kontur_r(pts, z):
    return float(np.interp(z, pts[:, 0], pts[:, 1]))


def _int_p_dA(g, a1, a2, ses_ustu):
    """∫ p/P_c d(A/A*) a1 → a2, sayısal quad (itki fonksiyonu KULLANMAZ)."""
    return quad(lambda a: _p_oran(_mach(a, g, ses_ustu), g), a1, a2,
                limit=400, epsabs=1e-12, epsrel=1e-11)[0]


def _ornek_yuk(ornek_sivi):
    inp = bridge.extract_structural_inputs(ornek_sivi)
    assert inp['status'] == bridge.BRIDGE_STATUS_OK
    return inp


# =========================================================================
# 1. p(x) — bağımsız analitikle aynı
# =========================================================================
def test_px_izantropik_bagimsiz_analitikle_ayni(ornek_sivi):
    inp = _ornek_yuk(ornek_sivi)
    yuk = inp['pressure_load']
    lm = inp['load_model']
    assert lm['distribution'] == bridge.YUK_DAGILIMI_IZANTROPIK
    g = float(ornek_sivi['gamma'])
    assert lm['gamma'] == g and lm['gamma_field'] == "results['gamma']"
    pc = float(ornek_sivi['chamber_pressure']) * 1e5
    pts = np.asarray(ornek_sivi['nozzle_contour']['points'], dtype=float)
    i_t = int(np.argmin(pts[:, 1]))
    r_t, z_t = pts[i_t, 1], pts[i_t, 0]
    # Motor konturunun TÜM noktaları + hazne silindirinden iki nokta.
    z = np.concatenate([[-0.1, -0.01], pts[:, 0]])
    r = np.concatenate([[pts[0, 1], pts[0, 1]], pts[:, 1]])
    p_urun = yuk.pressure_fn(z, r)
    for zk, rk, pk in zip(z, r, p_urun):
        if zk < pts[0, 0]:
            beklenen = pc                      # hazne: P_c (Rayleigh ihmal)
        else:
            beklenen = pc * _p_oran(_mach((rk / r_t) ** 2, g, zk > z_t), g)
        assert pk == pytest.approx(beklenen, rel=PX_KOK_TOL), (zk, rk)
    # Boğaz: p* = P_c·(2/(γ+1))^(γ/(γ−1)); çıkış: ses-üstü dal (p_e ≪ p*).
    p_t = float(yuk.pressure_fn(np.array([z_t]), np.array([r_t]))[0])
    assert p_t == pytest.approx(pc * (2.0 / (g + 1.0)) ** (g / (g - 1.0)),
                                rel=PX_KOK_TOL)
    assert p_urun[-1] < 0.05 * pc
    # Lülede monoton düşer (kontur noktalarında).
    assert np.all(np.diff(p_urun[2:]) <= 1e-9 * pc)


# =========================================================================
# 2. Kapalı uç kuvveti VAR
# =========================================================================
def test_kapali_uc_kuvveti_formulu_ve_varligi(ornek_sivi, ornek_fea):
    inp = _ornek_yuk(ornek_sivi)
    pc = float(ornek_sivi['chamber_pressure']) * 1e5
    r0 = float(inp['contour'][0, 1])
    F_beklenen = pc * math.pi * r0 * r0
    assert inp['pressure_load'].end_force_n == pytest.approx(F_beklenen,
                                                             rel=1e-12)
    uc = ornek_fea['load_model']['end_force']
    assert uc['force_n'] == pytest.approx(F_beklenen, rel=1e-12)
    assert 'z_min' in uc['applied_at'] and uc['support_modes']
    # Çözücü kuvveti GERÇEKTEN uyguladı: uç kuvveti eksenel toplamı −F_uç.
    kd = ornek_fea['result'].meta['kuvvet_dengesi']
    assert kd['uc_kuvveti_eksenel_n'] == pytest.approx(-F_beklenen,
                                                       rel=1e-12)


def _duz_silindir(n_ax=64, n_rad=8):
    a, t = 0.05, 0.01
    m = build_wall_mesh(np.array([[0.0, a], [0.5, a]]), t, n_ax, n_rad)
    mat = sa.Material(E=200e9, nu=0.3, yield_strength=500e6)
    return a, a + t, m, mat


def _ortalama_sz(m, res, i):
    ids = m.node_index_grid[i]
    rr = m.nodes[ids, 1]
    f = res.stress_nodal[ids, 0] * rr
    return 2.0 * np.pi * float(np.sum(0.5 * (f[1:] + f[:-1]) * np.diff(rr))) \
        / (np.pi * (rr[-1] ** 2 - rr[0] ** 2))


def test_kapali_uc_lame_capasi():
    """Çıkış mesnetli (z_max) düz kapalı uçlu silindir: σ_z = p·a²/(b²−a²)
    (Lamé kapalı uç, Timoshenko & Goodier Böl. 4); uç kuvveti yoksa ~0."""
    a, b, m, mat = _duz_silindir()
    p = 1.0e7
    i = m.node_index_grid.shape[0] // 2
    yuk = sa.InnerPressureLoad(p_ref_pa=p, end_force_n=p * math.pi * a * a)
    res = sa.solve_pressure(m, mat, yuk, axial_fix='z_max')
    assert _ortalama_sz(m, res, i) == pytest.approx(
        p * a * a / (b * b - a * a), rel=S1_TOL)
    res0 = sa.solve_pressure(m, mat, sa.InnerPressureLoad(p_ref_pa=p),
                             axial_fix='z_max')
    assert abs(_ortalama_sz(m, res0, i)) < 1e-3 * p
    # z_min kipinde kuvvet kısıtlı düğümlere gider (cidarı yüklemez) ve
    # mesnet tepkisi onu taşır.
    res1 = sa.solve_pressure(m, mat, yuk, axial_fix='z_min')
    kd = res1.meta['kuvvet_dengesi']
    assert kd['mesnet_eksenel_tepkisi_n'] == pytest.approx(
        p * math.pi * a * a, rel=1e-9)
    assert kd['uc_kuvveti_cidari_yukler'] is False
    assert res.meta['kuvvet_dengesi']['uc_kuvveti_cidari_yukler'] is True


def test_yuk_uygulanan_uc_saint_venant_bandinda():
    """Uç kuvveti eğimli serbest uca saf eksenel çekiş olarak konur; gerçek
    bağlantının (kasa/arka kapak) yerine konan statik eşdeğerdir ve bandı
    içindeki gerilme hüküm alanına GİRMEZ (z_max kipinde z_min ucu da
    bantlanır). z_min kipinde yüklü uç zaten kısıtlıdır, ek bant yoktur."""
    kontur = np.array([[0.0, 0.06], [0.05, 0.045], [0.10, 0.03]])
    m = build_wall_mesh(kontur, 0.003, 64, 4)
    mat = sa.Material(E=200e9, nu=0.3, yield_strength=500e6)
    p = 4.0e6
    yuk = sa.InnerPressureLoad(p_ref_pa=p, end_force_n=p * math.pi * 0.06 ** 2)
    r_max = sa.solve_pressure(m, mat, yuk, axial_fix='z_max')
    nedenler = [b['neden'] for b in r_max.meta['saint_venant']['bantlar']]
    assert nedenler == ['kisit', 'yuk_uygulama']
    assert not np.any(r_max.saint_venant_maskesi[m.z_min_nodes])
    r_min = sa.solve_pressure(m, mat, yuk, axial_fix='z_min')
    assert [b['neden'] for b in r_min.meta['saint_venant']['bantlar']] == \
        ['kisit']
    r_yok = sa.solve_pressure(m, mat, sa.InnerPressureLoad(p_ref_pa=p),
                              axial_fix='z_max')
    assert [b['neden'] for b in r_yok.meta['saint_venant']['bantlar']] == \
        ['kisit']
    assert np.all(r_yok.saint_venant_maskesi[m.z_min_nodes])


def test_skaler_yol_ve_sabit_yuk_modeli_bit_ayni():
    """Skaler basınç yolu ile uç kuvvetsiz sabit yük modeli AYNI aritmetik
    (eski davranış bit-aynı korunur)."""
    _, _, m, mat = _duz_silindir(32, 4)
    r_sk = sa.solve_pressure(m, mat, 7.0e6, axial_fix='z_min')
    r_ym = sa.solve_pressure(m, mat, sa.InnerPressureLoad(p_ref_pa=7.0e6),
                             axial_fix='z_min')
    assert np.array_equal(r_sk.displacement, r_ym.displacement)
    assert np.array_equal(r_sk.stress_nodal, r_ym.stress_nodal)
    assert r_sk.min_safety_factor == r_ym.min_safety_factor


# =========================================================================
# 3. Kuvvet dengesi — bağımsız analitik
# =========================================================================
def _bagimsiz_net_ag_yuzeyi(lm, mesh):
    """Ağın iç yüzeyinde net eksenel basınç kuvveti — bu dosyanın kendi
    sayısal integraliyle (quad), ürünün itki fonksiyonu KULLANILMAZ."""
    grid = np.asarray(mesh.node_index_grid)
    ic = np.asarray(mesh.nodes)[grid[:, 0]]
    pc, g = lm['p_c_pa'], lm['gamma']
    r_t, z_t, z_g = lm['throat_radius_m'], lm['throat_z_m'], lm['inlet_z_m']
    A_t = math.pi * r_t ** 2
    a0 = (ic[0, 1] / r_t) ** 2
    ag = (np.interp(z_g, ic[:, 0], ic[:, 1]) / r_t) ** 2
    am = (np.interp(z_t, ic[:, 0], ic[:, 1]) / r_t) ** 2
    ae = (ic[-1, 1] / r_t) ** 2
    silindir = pc * A_t * (a0 - ag)
    yakinsak = pc * A_t * _int_p_dA(g, am, ag, False)
    iraksak = pc * A_t * _int_p_dA(g, am, ae, True)
    return -lm['end_force']['force_n'] + silindir + yakinsak - iraksak


def test_kuvvet_dengesi_tutar_bagimsiz_analitikle(ornek_fea):
    lm = ornek_fea['load_model']
    kd = lm['force_balance']
    assert kd['measured'] is True and kd['holds'] is True
    assert kd['tol'] == bridge.KUVVET_DENGESI_TOL
    tepki = ornek_fea['result'].meta['kuvvet_dengesi'][
        'mesnet_eksenel_tepkisi_n']
    net = _bagimsiz_net_ag_yuzeyi(lm, ornek_fea['refinement'].mesh)
    F_uc = lm['end_force']['force_n']
    assert abs(tepki + net) / F_uc <= bridge.KUVVET_DENGESI_TOL
    # Ürünün kendi analitiği de bağımsız quad ile aynı (kapalı biçim doğru).
    assert kd['analytic_net_axial_mesh_surface_n'] == pytest.approx(
        net, rel=1e-8, abs=1e-6 * F_uc)
    assert 'kuvvet_dengesi_tutmadi' not in \
        ornek_fea['verdict']['geri_cekme_gerekceleri']


#: Kaba ağda yük integrali payı: kapı toleransının ONDA BİRİ (kesim
#: noktalarıyla her parça düzgün; Gauss hatası kapının çok altında kalmalı).
KABA_AG_YUK_PAYI = bridge.KUVVET_DENGESI_TOL / 10.0


@pytest.mark.parametrize('n_axial', [16, 32])
def test_kesim_noktalari_kaba_agda_yuk_integrali(ornek_sivi, n_axial):
    """p(x)'in düzgün olmadığı z'lerde (hazne→lüle, boğaz dal değişimi)
    kenar integrali bölünür; kaba ağda bile eksenel yük toplamı ağ yüzeyi
    analitiğine KABA_AG_YUK_PAYI içinde oturur. ÖLÇÜLDÜ (rapor §3): 16/32
    istasyonda bölünmüş 1,4e-5…2,2e-5, bölünmemiş 6,9e-4…4,3e-3 (5 mm ve
    2 mm geometride). 8 istasyonda kalan fark (2 mm: 1,2e-4) kesim
    noktasından değil, lülenin büyük kesrini tek kenarda geçen Gauss
    kesmesinden gelir — bu bekçinin sınadığı şey değildir, ağ dışı tutuldu."""
    inp = _ornek_yuk(ornek_sivi)
    yuk, lm = inp['pressure_load'], inp['load_model']
    assert len(yuk.z_kesimleri) == 2
    mesh = build_wall_mesh(inp['contour'], inp['thickness_m'], n_axial, 4)
    F = np.zeros(2 * mesh.n_nodes)
    sa._ic_basinc_yukunu_kur(F, mesh, yuk)
    F_uc = lm['end_force']['force_n']
    net = _bagimsiz_net_ag_yuzeyi(lm, mesh)
    assert abs(F[0::2].sum() - net) / F_uc <= KABA_AG_YUK_PAYI


def test_kuvvet_dengesi_tutmazsa_hukum_geri_cekilir(ornek_sivi, monkeypatch):
    """Analitik net bozulursa (ör. uç kuvveti yanlış) hüküm fail-closed."""
    asil = bridge._ag_yuzeyi_analitik_net
    monkeypatch.setattr(bridge, '_ag_yuzeyi_analitik_net',
                        lambda k, m: asil(k, m) + 0.01 *
                        k['end_force']['force_n'])
    out = _sessiz(bridge.run_structural_from_motor, ornek_sivi,
                  n_axial0=16, n_radial0=4, max_rounds=1)
    assert out['load_model']['force_balance']['holds'] is False
    assert 'kuvvet_dengesi_tutmadi' in out['verdict']['geri_cekme_gerekceleri']
    assert out['verdict']['verildi'] is False


# =========================================================================
# 4. γ yokken geri dönüş beyanı
# =========================================================================
@pytest.mark.parametrize('bozuk', [None, 0.9, float('nan'), True, '1.2x',
                                   2.0])
def test_gamma_yokken_sabit_pc_geri_donusu_beyanli(ornek_sivi, bozuk):
    m = copy.deepcopy(ornek_sivi)
    if bozuk is None:
        m.pop('gamma', None)
    else:
        m['gamma'] = bozuk
    inp = bridge.extract_structural_inputs(m)
    assert inp['status'] == bridge.BRIDGE_STATUS_OK
    lm = inp['load_model']
    assert lm['distribution'] == bridge.YUK_DAGILIMI_SABIT_GERI_DONUS
    assert lm['gamma'] is None
    assert "results['gamma']" in lm['fallback_reason']
    assert 'SABİT P_c' in lm['nozzle']
    yuk = inp['pressure_load']
    assert yuk.pressure_fn is None                  # her yerde P_c
    assert yuk.end_force_n > 0.0                    # uç kuvveti yine var
    gamma_yolu = [c for c in inp['consumed_paths'] if c['path'] == 'gamma']
    assert gamma_yolu and gamma_yolu[0]['applied'] is False


def test_gamma_yokken_kosu_beyani_cozucuye_ulasir(ornek_sivi):
    m = copy.deepcopy(ornek_sivi)
    m.pop('gamma', None)
    out = _sessiz(bridge.run_structural_from_motor, m, n_axial0=16,
                  n_radial0=4, max_rounds=1)
    assert out['load_model']['distribution'] == \
        bridge.YUK_DAGILIMI_SABIT_GERI_DONUS
    yukler = out['result'].meta['yukler']
    assert yukler['ic_basinc_dagilimi'] == 'sabit'
    assert any('SABİT P_c geri dönüşü' in n
               for n in out['meta']['not_modelled'] if isinstance(n, str))
    # Sabit P_c'de kuvvet dengesi kapalı biçimde tam tutar.
    assert out['load_model']['force_balance']['rel_error'] < 1e-9


# =========================================================================
# 5. Analitik ⟷ FEA, üç istasyon, iki mesnet kipi
# =========================================================================
def _kesit_kuvvetleri(lm, pts, pc, g, z_s, kip):
    """İstasyon z_s'deki eksenel kesit kuvveti N (+çekme), motor konturu
    üstünde, bağımsız quad ile."""
    i_t = int(np.argmin(pts[:, 1]))
    r_t, z_t = pts[i_t, 1], pts[i_t, 0]
    A_t = math.pi * r_t * r_t
    a_in = (pts[0, 1] / r_t) ** 2
    a_e = (pts[-1, 1] / r_t) ** 2
    F_uc = lm['end_force']['force_n']
    F_yak = pc * A_t * _int_p_dA(g, 1.0, a_in, False)       # +z
    if z_s < pts[0, 0]:                                      # hazne
        asagi = F_yak - pc * A_t * _int_p_dA(g, 1.0, a_e, True)
    elif z_s <= z_t:
        a_s = (_kontur_r(pts, z_s) / r_t) ** 2
        asagi = (pc * A_t * _int_p_dA(g, 1.0, a_s, False)
                 - pc * A_t * _int_p_dA(g, 1.0, a_e, True))
    else:
        a_s = (_kontur_r(pts, z_s) / r_t) ** 2
        asagi = -pc * A_t * _int_p_dA(g, a_s, a_e, True)
    net = -F_uc + F_yak - pc * A_t * _int_p_dA(g, 1.0, a_e, True)
    # z_min: kesitin aşağı akımı serbest cisim → N = aşağı akım kuvveti
    # (+z çeken kuvvet çekme). z_max: yukarı akım serbest cisim; iki kip
    # arasındaki fark mesnet tepkisidir (−net).
    return asagi if kip == 'z_min' else asagi - net


def _cizgi(mesh, res, z_s):
    grid = np.asarray(mesh.node_index_grid)
    ic_z = np.asarray(mesh.nodes)[grid[:, 0], 0]
    i = int(np.argmin(np.abs(ic_z - z_s)))
    ids = grid[i]
    return i, np.asarray(mesh.nodes)[ids], np.asarray(res.stress_nodal)[ids]


def _vm(s1, s2, s3):
    return math.sqrt(0.5 * ((s1 - s2) ** 2 + (s2 - s3) ** 2 + (s3 - s1) ** 2))


def _egrilik(p0, p1, p2):
    """Üç noktadan işaretli eğrilik κ_1 (+: merkez eksen tarafında)."""
    a = np.asarray(p1) - np.asarray(p0)
    b = np.asarray(p2) - np.asarray(p0)
    c = np.asarray(p2) - np.asarray(p1)
    capraz = a[0] * b[1] - a[1] * b[0]          # (z, r) düzlemi
    k = 2.0 * capraz / (np.linalg.norm(a) * np.linalg.norm(b)
                        * np.linalg.norm(c))
    return -k


def _alan_agirlikli_sz(P, S):
    rr = P[:, 1]
    f = S[:, 0] * rr
    return 2.0 * np.pi * float(np.sum(0.5 * (f[1:] + f[:-1]) * np.diff(rr))) \
        / (np.pi * (rr[-1] ** 2 - rr[0] ** 2))


def istasyon_kiyasi(motor, inp, lm, mesh, kip):
    """Kalem 4: üç istasyon × (çember, eksenel, von Mises) — FEA ⟷ analitik.

    Dönüş: [{istasyon, buyukluk, fea, analitik | bant, tol, tuttu}, ...].
    Toleranslar toleranslar_once.md'dendir (HESAPTAN ÖNCE). Analitik taraf
    bu dosyanın bağımsız kâhinidir (quad + kendi alan-Mach tersi).
    """
    res = sa.solve_pressure(mesh, inp['material'], inp['pressure_load'],
                            axial_fix=kip)
    pc, g = lm['p_c_pa'], lm['gamma']
    pts = np.asarray(motor['nozzle_contour']['points'], dtype=float)
    t = inp['thickness_m']
    ext = inp['chamber_extension_m']
    i_t = int(np.argmin(pts[:, 1]))
    z_t, r_t = pts[i_t, 0], pts[i_t, 1]
    satirlar = []

    def _ekle(ist, ad, fea, ana, tol):
        satirlar.append({'istasyon': ist, 'buyukluk': ad, 'fea': float(fea),
                         'analitik': float(ana), 'tol': tol,
                         'bagil': float(abs(fea - ana) / abs(ana)),
                         'tuttu': bool(abs(fea - ana) <= tol * abs(ana))})

    def _ekle_bant(ist, ad, fea, lo, hi, pay):
        satirlar.append({'istasyon': ist, 'buyukluk': ad, 'fea': float(fea),
                         'bant': [float(lo), float(hi)], 'pay': float(pay),
                         'tuttu': bool(lo - pay <= fea <= hi + pay)})

    # --- S1 hazne ortası: Lamé ------------------------------------------
    z1 = -0.5 * ext
    _, P, S = _cizgi(mesh, res, z1)
    a, b = P[0, 1], P[-1, 1]
    s_th_a = pc * a * a / (b * b - a * a) * (1.0 + b * b / (a * a))
    s_z = _kesit_kuvvetleri(lm, pts, pc, g, z1, kip) / (
        math.pi * (b * b - a * a))
    _ekle('S1', 'sigma_theta_ic', S[0, 2], s_th_a, S1_TOL)
    _ekle('S1', 'sigma_z_ortalama', _alan_agirlikli_sz(P, S), s_z, S1_TOL)
    _ekle('S1', 'von_mises_ic', _vm(S[0, 0], S[0, 1], S[0, 2]),
          _vm(s_z, -pc, s_th_a), S1_TOL)

    # --- S2 boğaz: kesit dengesi + F-19 ikinci yol + zar bandı ----------
    # Kesit dengesi TAM: ağ çizgisinin kendisinden geçen eksenel kuvvet
    # F_z = ∫ (σ_zz·n_z + τ_rz·n_r)·2πr ds (n: çizginin aşağı akıma bakan
    # birim normali) ⟷ aynı kesitin (çizginin iç düğümündeki A) serbest
    # cisim kuvveti. ÖLÇÜLDÜ (rapor §4): ilk uygulama çizgiyi z = sabit
    # sayıp yalnız σ_zz'yi alanla ağırlıklandırıyordu ve kesiti z_t'de
    # alıyordu; ince ağda çizgi boğazdan 0,1-0,2 mm kayık ve 1,7°'ye kadar
    # eğik olduğunda bu yöntem hatası %2,4'e çıkıyordu. Tolerans
    # (S2_DENGE_TOL) DEĞİŞMEDİ.
    i2, P, S = _cizgi(mesh, res, z_t)
    a, b = P[0, 1], P[-1, 1]
    v = (P[-1] - P[0]) / np.linalg.norm(P[-1] - P[0])
    n_z, n_r = v[1], -v[0]
    ds = np.linalg.norm(np.diff(P, axis=0), axis=1)
    f = (S[:, 0] * n_z + S[:, 3] * n_r) * P[:, 1]
    F_z = 2.0 * np.pi * float(np.sum(0.5 * (f[1:] + f[:-1]) * ds))
    N2 = _kesit_kuvvetleri(lm, pts, pc, g, P[0, 0], kip)
    alan = math.pi * (b * b - a * a)
    _ekle('S2', 'sigma_z_ortalama_kesit_dengesi', F_z / alan, N2 / alan,
          S2_DENGE_TOL)
    _ekle('S2', 'sigma_z_ortalama_F19_ince_cidar', F_z / alan,
          N2 / (2.0 * math.pi * r_t * t), t / (2.0 * a) + S2_FE_PAYI)
    p_t = pc * _p_oran(1.0, g)
    r_m = a + 0.5 * t
    s_m = N2 / (2.0 * math.pi * r_m * t)
    k_u = _egrilik(pts[i_t - 2], pts[i_t - 1], pts[i_t])
    k_d = _egrilik(pts[i_t], pts[i_t + 1], pts[i_t + 2])
    bant = sorted(r_m * (p_t / t - s_m * k) for k in (k_u, k_d))
    s_th_ort = float(np.mean(0.5 * (S[1:, 2] + S[:-1, 2])))
    _ekle_bant('S2', 'sigma_theta_ortalama_zar_bandi', s_th_ort, bant[0],
               bant[1], S2_BANT_GENISLETME * abs(bant[1]))
    vm_bant = sorted(_vm(s_m, s_, -0.5 * p_t) for s_ in bant)
    _ekle_bant('S2', 'P_m_zar_bandi', float(res.scl_P_m[i2]), vm_bant[0],
               vm_bant[1], S2_BANT_GENISLETME * abs(vm_bant[1]))
    satirlar.append({'istasyon': 'S2', 'buyukluk':
                     'sigma_theta_F19_silindir_BILGI', 'fea': s_th_ort,
                     'analitik': p_t * r_t / t, 'tol': None,
                     'tuttu': None})

    # --- S3 genişleyen bölüm ortası: ince kabuk zarı --------------------
    z3 = 0.5 * (z_t + pts[-1, 0])
    i3, P, S = _cizgi(mesh, res, z3)
    k3 = int(np.argmin(np.abs(pts[:, 0] - P[0, 0])))
    egim = math.atan2(pts[k3 + 1, 1] - pts[k3 - 1, 1],
                      pts[k3 + 1, 0] - pts[k3 - 1, 0])
    a = P[0, 1]
    r_m = a + 0.5 * t * math.cos(egim)
    R2 = r_m / math.cos(egim)
    k1 = _egrilik(pts[k3 - 1], pts[k3], pts[k3 + 1])
    p3 = pc * _p_oran(_mach((a / r_t) ** 2, g, True), g)
    N3 = _kesit_kuvvetleri(lm, pts, pc, g, P[0, 0], kip)
    s_m3 = N3 / (2.0 * math.pi * r_m * t * math.cos(egim))
    s_th3 = R2 * (p3 / t - s_m3 * k1)
    v = P[-1] - P[0]
    nz, nr = v / np.linalg.norm(v)
    s_tt = nr ** 2 * S[:, 0] - 2 * nz * nr * S[:, 3] + nz ** 2 * S[:, 1]
    _ekle('S3', 'sigma_meridyen_ortalama',
          float(np.mean(0.5 * (s_tt[1:] + s_tt[:-1]))), s_m3, S3_TOL)
    _ekle('S3', 'sigma_theta_ortalama',
          float(np.mean(0.5 * (S[1:, 2] + S[:-1, 2]))), s_th3, S3_TOL)
    _ekle('S3', 'P_m', float(res.scl_P_m[i3]), _vm(s_m3, s_th3, -0.5 * p3),
          S3_TOL)
    return satirlar


#: İstasyon bekçisinin ağı — ürünün yayımladığı ağdan BAĞIMSIZ, sabit.
#: ÖLÇÜLDÜ (rapor §4, istasyon_5mm.json / istasyon_2mm.json): boğazdaki
#: eğilme düğüm (SPR) gerilmesiyle kaba ağda çözülemiyor — S2 kesit dengesi
#: 5 mm'de ürün ağı (64×4) %3,9 / %2,4, 256×8 %1,3 / %0,6, 1024×16 %0,6 /
#: %0,3; 2 mm'de (sıvı dalı geometrisi) ürün ağı tutmuyor, 256×8 %15 /
#: %6,4, 1024×16 %1,1 / %0,6. Bekçi yük modelini ayrıklaştırma hatasından
#: ayırmak için iki geometride de tutan bu ağda koşar; ürün ağındaki
#: sonuçlar raporda AYRICA yayımlanır.
ISTASYON_AGI = (1024, 16)

#: Bekçinin YARGILADIĞI satırlar: analitik tarafın geçerli bir kâhin olduğu
#: büyüklükler — Lamé (S1), kesit dengesi ve F-19 serbest cisim ikinci yolu
#: (S2 eksenel), zar dengesinin meridyen bileşeni ve P_m (S3). Yargılanmayan
#: iki satır ailesi raporda "tutmadı" diye yazılıdır, gerekçe:
#:   * S2 çember/P_m zar bandı: boğazda meridyen yarıçapı (R_1 ≈ 10–17 mm)
#:     eğilme boyu √(R·t) ile aynı mertebede (5 mm'de 12,2 mm) — zar kuramı
#:     orada GEÇERSİZ (kâhin yanlış seçilmişti; z_min kipinde FEA bandın
#:     dışında, z_max'ta içinde).
#:   * S3 çember: σ_θ = R_2·(p/t − σ_m·κ_1) iki büyük terimin farkı (5 mm
#:     z_max'ta 0,65 MPa ⟷ σ_m 12,4 MPa); 3 nokta eğrilik kestiriminin
#:     birkaç yüzdelik hatası farkta %10'u aşıyor — bağıl tolerans bu
#:     büyüklükte iyi tanımlı değil.
#: Toleranslar DEĞİŞMEDİ (toleranslar_once.md); yalnız yargılanan küme
#: daraltıldı ve daraltma burada gerekçesiyle durur.
BEKCI_SATIRLARI = {
    ('S1', 'sigma_theta_ic'), ('S1', 'sigma_z_ortalama'),
    ('S1', 'von_mises_ic'),
    ('S2', 'sigma_z_ortalama_kesit_dengesi'),
    ('S2', 'sigma_z_ortalama_F19_ince_cidar'),
    ('S3', 'sigma_meridyen_ortalama'), ('S3', 'P_m'),
}


@pytest.mark.parametrize('kip', ['z_min', 'z_max'])
def test_istasyon_kiyasi_lame_ve_serbest_cisim(ornek_sivi, ornek_fea, kip):
    inp = ornek_fea['inputs']
    mesh = build_wall_mesh(inp['contour'], inp['thickness_m'],
                           *ISTASYON_AGI)
    satirlar = istasyon_kiyasi(ornek_sivi, inp, ornek_fea['load_model'],
                               mesh, kip)
    yargilanan = [s_ for s_ in satirlar
                  if (s_['istasyon'], s_['buyukluk']) in BEKCI_SATIRLARI]
    assert len(yargilanan) == len(BEKCI_SATIRLARI)
    tutmayan = [s_ for s_ in yargilanan if not s_['tuttu']]
    assert not tutmayan, tutmayan


# =========================================================================
# 6. Kapsam beyanı + uç yanıtı
# =========================================================================
def test_kapsam_yalniz_basinc_ve_uc_yaniti(istemci, ornek_sivi):
    r = _sessiz(istemci.post, '/api/fea/structural',
                json={'motor_results': ornek_sivi})
    assert r.status_code == 200
    fea = r.get_json()['fea']
    lm = fea['load_model']
    assert lm['distribution'] == bridge.YUK_DAGILIMI_IZANTROPIK
    assert 'YALNIZ BASINÇ' in lm['scope']
    assert 'Isıl yük' in lm['scope'] and 'Sıcaklığa bağlı dayanım' in \
        lm['scope']
    assert lm['force_balance']['holds'] is True
    assert fea['meta']['hukum']['yuk_kapsami'] == lm['scope']
    assert any('ısıl yük ve sıcaklığa bağlı dayanım' in n
               for n in fea['meta']['not_modelled'] if isinstance(n, str))
