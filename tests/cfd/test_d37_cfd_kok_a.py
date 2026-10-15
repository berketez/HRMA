# tests/cfd — ÖH D37 A3a cfd-kok-a çekirdek onarımlarının bekçileri
"""
Dört DK kusuru + F-05'in davranış bekçileri (ters mutasyon kayıtları
docs/scofield/raw/OH/A3a/cfd-kok-a/mutasyon.md):

  B1 (OH-DK-12) açık yol plato-dondurma tetiği: iniş kapısı (2 mertebe) +
     ağ boyuyla ölçekli pencere + limiter_freeze beyanı; şoklu akışta
     dondurma yok (OH-DK-13 ayrıştırması).
  B3 (OH-DK-14) hücre bazlı JST sensörü: yalnız sıkışmada, sürekli çarpan;
     şoksuz genişlemede DOKUNMAZ (C7 standard, C3 192×48 ÖNCE alanları),
     şokta dokunur (C2b 30×6, en zayıf şok ν = 0,23).
  B4 (OH-DK-15) boğaz düğümü zorunlu eksenel istasyon (bit).
  F-05 (P6B1-10) kayma duvarı TRRS yıldız basıncı: pozitif, akustikle
     birinci mertebe uyumlu (sympy), residual_axisym bu biçimi kullanır.
Kilitli ölçütler: docs/scofield/raw/OH/A3a/cfd-kok-a/olcut_kulvar.json.
"""

import json
import pathlib

import numpy as np
import pytest

from hrma.cfd import euler_core as ec, steady as st
from hrma.cfd.euler_core import (
    SHOCK_SENSOR_THRESHOLD, SHOCK_SENSOR_THRESHOLD_LOW, prim_to_cons_axisym,
    residual_axisym, shock_cell_weight, wall_star_pressure,
    wall_star_pressure_trrs,
)
from hrma.cfd.grid_axisym import (
    axial_stations_with_throat, build_grid_from_wall, build_nozzle_grid,
    nozzle_axial_stations,
)
from hrma.cfd.steady import solve_steady_axisym
from tests.support.kanit import kanit_gerekli

from .conftest import (
    IZANTROPIK_COZUCU, LULE_GAMMA, LULE_L_CONV, LULE_L_DIV, LULE_P0, LULE_R,
    LULE_T0, lule_duvar_yaricapi, lule_gridi,
)

KOK = pathlib.Path(__file__).resolve().parents[2]
DK_KOSUMLAR = KOK / 'docs/scofield/raw/OH/D37/dogrulama/cfd/kosumlar'


# ---------------------------------------------------------------------------
# B3 — JST hücre sensörü
# ---------------------------------------------------------------------------

def _ext_i(p2d):
    """(ni, nj) basınç → i yönünde 2 hayalet (uç değerler kopya)."""
    return np.concatenate([p2d[:1], p2d[:1], p2d, p2d[-1:], p2d[-1:]], 0)


def _ext_j(p2d):
    pj = p2d.T                                     # (nj, ni)
    return np.concatenate([pj[:1], pj[:1], pj, pj[-1:], pj[-1:]], 0)


def _w_of(p2d, uz=1.0, ur=0.0):
    ni, nj = p2d.shape
    return shock_cell_weight(_ext_i(p2d), _ext_j(p2d), np.full((ni, nj), uz),
                             np.full((ni, nj), ur))


def test_sensor_esikleri_olcumden():
    assert SHOCK_SENSOR_THRESHOLD == 0.08
    assert SHOCK_SENSOR_THRESHOLD_LOW == 0.04
    # kilit dosyasıyla aynı sayı (tek kaynak beyanı). Okuma kanıt KAPISINDAN
    # (ÖH V3 taban-b): eski ``if ... exists() else None`` dalı, geliştirme
    # ağacında dosya kaybolsa da iddiayı SESSİZCE atlıyordu; kapı docs'suz
    # yayın dalında gerekçeli atlar, geliştirme ağacında kırmızı verir.
    kilit = json.loads(kanit_gerekli(
        KOK / 'docs/scofield/raw/OH/A3a/cfd-kok-a/olcut_kulvar.json'
    ).read_text(encoding='utf-8'))
    assert kilit['sabitler_olcumden']['SHOCK_SENSOR_THRESHOLD_cell']['deger'] == SHOCK_SENSOR_THRESHOLD


def test_sensor_duzgun_genislemede_DOKUNMAZ():
    """Üstel düşen basınç (genişleme, ν küçük) → None: eğimlere dokunulmaz."""
    z = np.linspace(0.0, 1.0, 60)
    p = np.outer(np.exp(-3.0 * z), np.ones(8)) * 1e6
    assert _w_of(p) is None


def test_sensor_KESKIN_genislemede_de_dokunmaz_isaret_kosulu():
    """Genişleme SIÇRAMASI (p₂/p₁ = 1/3, tek hücre) — ν = 0,5 ama sıkışma
    değil → None. İşaret koşulu kaldırılırsa (mutasyon) bayraklanır."""
    p = np.ones((40, 6)) * 1e6
    p[20:] = 1e6 / 3.0
    assert _w_of(p, uz=+1.0) is None
    # AYNI alan akış TERS yönde (u_z < 0) → artık sıkışmadır → dokunur
    w = _w_of(p, uz=-1.0)
    assert w is not None and np.min(w) == 0.0


def test_sensor_sikisma_sicramasinda_birinci_mertebe_ve_genisletme():
    p = np.ones((40, 6)) * 1e6
    p[20:] = 3.0e6                       # ν(19, 20) = 2e6/(… ) ≈ 0,33-0,5
    w = _w_of(p)
    assert w is not None
    sifir = np.where(np.all(w == 0.0, axis=1))[0]
    assert 19 in sifir and 20 in sifir, sifir
    # 3×3 komşuluk maksimumu: 18 ve 21 de tam 0 (genişletme)
    assert 18 in sifir and 21 in sifir, sifir
    # uzak hücreler tam 1 (bit): sensör oraya dokunmaz
    assert np.all(w[:15] == 1.0) and np.all(w[25:] == 1.0)


def test_sensor_surekli_carpan_esikler_arasi_dogrusal():
    """ν = (θ + θ_alt)/2 → çarpan tam 0,5 (anahtar yok, doğrusal geçiş)."""
    nu_hedef = 0.5 * (SHOCK_SENSOR_THRESHOLD + SHOCK_SENSOR_THRESHOLD_LOW)
    # p₋ = p₀ = 1, p₊ = 1 + d → ν = d/(4 + d) → d = 4ν/(1 − ν)
    d = 4.0 * nu_hedef / (1.0 - nu_hedef)
    p = np.ones((30, 4))
    p[15:] = 1.0 + d
    w = _w_of(p)
    assert w is not None
    assert w[14, 0] == pytest.approx(0.5, abs=1e-12)


def test_sensor_en_zayif_sok_nu_0_23_TAM_birinci_mertebe():
    """C2b 30×6 şok hücresi ν = 0,2315 (ÖNCE ölçümü) > θ → çarpan 0.
    Eşik 0,25'e çekilirse (mutasyon) bu şok KAÇAR."""
    d = 4.0 * 0.2315 / (1.0 - 0.2315)
    p = np.ones((30, 4))
    p[15:] = 1.0 + d
    w = _w_of(p)
    assert w is not None and w[14, 0] == 0.0
    assert shock_cell_weight(_ext_i(p), _ext_j(p), np.ones((30, 4)),
                             np.zeros((30, 4)), threshold=0.25,
                             threshold_low=0.125)[14, 0] > 0.0


@pytest.mark.parametrize('vaka,seviye', [('C7', 'standard'), ('C3', '192x48'),
                                         ('C7', 'coarse'), ('C1', '240x48')])
def test_sensor_DK_soksuz_ONCE_alanlarinda_sifir(vaka, seviye):
    """OH-DK-14: eski sensör bu alanlarda 4-8 kolon bayraklıyordu; yeni
    sensör hiçbirine dokunmaz (kanıt: DK kampanyası ham alanları)."""
    npz = kanit_gerekli(DK_KOSUMLAR / vaka / f'{seviye}.npz')
    d = np.load(npz)
    w = shock_cell_weight(_ext_i(d['p']), _ext_j(d['p']), d['uz'], d['ur'])
    assert w is None, f'{vaka}/{seviye}: sensör {int(np.sum(w < 1))} hücreye dokundu'


@pytest.mark.parametrize('vaka,seviye', [('C2b', '30x6'), ('C2', '60x12'),
                                         ('C2b', '120x24')])
def test_sensor_DK_soklu_ONCE_alanlarinda_sokta(vaka, seviye):
    npz = kanit_gerekli(DK_KOSUMLAR / vaka / f'{seviye}.npz')
    d = np.load(npz)
    w = shock_cell_weight(_ext_i(d['p']), _ext_j(d['p']), d['uz'], d['ur'])
    assert w is not None
    kolonlar = np.where(np.any(w < 1.0, axis=1))[0]
    dp = np.abs(np.diff(d['p_sec']))
    k = int(np.argmax(dp))                       # şok yüzü
    assert kolonlar.size > 0
    assert np.all(np.abs(kolonlar - k) <= 3), (k, kolonlar)


# ---------------------------------------------------------------------------
# B1 — plato-dondurma tetiği
# ---------------------------------------------------------------------------

def test_plato_sabitleri_kilitle_ayni():
    assert st.PLATEAU_DESCENT_DECADES == 2.0
    assert st.PLATEAU_WINDOW_PER_NI == 2.5
    assert st.PLATEAU_WINDOW_BASE == 300
    assert st.PLATEAU_STALL_RATIO == 0.9


def test_pencere_ag_boyuyla_olcekli_ve_beyanli():
    """240 eksenel hücre → 600 iterasyon; 30 → 300 (taban)."""
    r_kucuk = solve_steady_axisym(lule_gridi(30, 4), max_iters=3,
                                  **{k: v for k, v in IZANTROPIK_COZUCU.items()
                                     if k != 'max_iters'})
    assert r_kucuk['limiter_freeze']['window_iterations'] == 300
    z = np.linspace(0.0, LULE_L_CONV + LULE_L_DIV, 241)
    g240 = build_grid_from_wall(z, lule_duvar_yaricapi(z), 2)
    r_ince = solve_steady_axisym(g240, max_iters=3,
                                 **{k: v for k, v in IZANTROPIK_COZUCU.items()
                                    if k != 'max_iters'})
    assert r_ince['limiter_freeze']['window_iterations'] == 600
    lf = r_ince['limiter_freeze']
    assert lf['descent_gate_decades'] == 2.0 and lf['frozen_at_iter'] is None
    assert lf['descent_decades_at_freeze'] is None


def test_inis_kapisi_transienti_dondurmaz_KONTROL_deneyli(monkeypatch):
    """Kısa rampa + küçük pencerede eski tetik (kapı 0) BAŞLANGIÇ
    GEÇİCİSİNDE donar; kilitli kapı (2,0) donmaz ya da ≥ 2 mertebe
    inişten sonra donar. Kontrol: kapı 0 iken donma < 2 mertebe."""
    monkeypatch.setattr(st, 'PLATEAU_WINDOW_BASE', 20)
    monkeypatch.setattr(st, 'PLATEAU_WINDOW_PER_NI', 0.0)
    ayar = dict(IZANTROPIK_COZUCU, ramp_iters=40, max_iters=400)
    g = lule_gridi(30, 6)
    monkeypatch.setattr(st, 'PLATEAU_PERSIST_WINDOWS', 10 ** 6)  # yalnız iniş yolu
    r = solve_steady_axisym(g, **ayar)
    lf = r['limiter_freeze']
    assert lf['frozen_at_iter'] is None or (
        lf['trigger'] == 'descent_gate'
        and lf['descent_decades_at_freeze'] >= 2.0), lf
    monkeypatch.setattr(st, 'PLATEAU_DESCENT_DECADES', 0.0)
    r0 = solve_steady_axisym(g, **ayar)
    lf0 = r0['limiter_freeze']
    assert lf0['frozen_at_iter'] is not None
    assert lf0['descent_decades_at_freeze'] < 2.0, lf0
    assert lf0['frozen_at_iter'] < (lf['frozen_at_iter'] or 10 ** 9)


def test_kalici_stall_yolu_inis_kapisindan_bagimsiz_ama_beyanli(monkeypatch):
    """Kalıcı plato (3·pencere iki blok) iniş derinliğine bakmadan dondurur;
    hangi yolun ateşlediği ve iniş mertebesi yayımlanır. Kısa rampa + küçük
    pencerede transient bir kez tümsek yapar (tek pencere) — kalıcı yol
    ateşlemez; iniş kapısı kapalıyken (persist ∞) HİÇ donmayan vaka,
    persist = 3 ile ancak gerçekten stall edince donar."""
    monkeypatch.setattr(st, 'PLATEAU_WINDOW_BASE', 20)
    monkeypatch.setattr(st, 'PLATEAU_WINDOW_PER_NI', 0.0)
    ayar = dict(IZANTROPIK_COZUCU, ramp_iters=40, max_iters=400)
    g = lule_gridi(30, 6)
    r = solve_steady_axisym(g, **ayar)
    lf = r['limiter_freeze']
    assert lf['persist_windows'] == 3
    assert lf['trigger'] in (None, 'descent_gate', 'persistent_stall')
    if lf['trigger'] == 'persistent_stall':
        # kalıcı stall: donma anından 3·pencere önce de kalıntı düşmüyordu
        rh = np.asarray(r['residual_history'])
        k = lf['frozen_at_iter']
        w = 3 * lf['window_iterations']
        assert rh[k - w:k].min() > 0.9 * rh[k - 2 * w:k - w].min()
    assert lf['descent_decades_at_freeze'] is None or \
        lf['descent_decades_at_freeze'] >= 0.0


def test_soklu_akista_dondurma_yok(sok_cozumu):
    """OH-DK-13 ayrıştırması: sensör bayrağı doluyken plato-dondurma
    tetiklenmez (şoklu 120×24 sözleşme vakası)."""
    _g, r = sok_cozumu
    assert r['shock_sensor_cells'] > 0
    assert r['limiter_freeze']['freeze_count'] == 0
    assert r['limiter_frozen_at_iter'] is None


# ---------------------------------------------------------------------------
# B4 — boğaz düğümü zorunlu istasyon
# ---------------------------------------------------------------------------

def test_bogaz_dugumu_duzgun_istasyona_dusuyorsa_BIT_ayni():
    z = axial_stations_with_throat(0.0, 0.30, 0.12, 60)
    assert np.array_equal(z, np.linspace(0.0, 0.30, 61))


def test_bogaz_dugumu_zorunlu_istasyon_bit():
    z_t = 0.1234
    z = axial_stations_with_throat(0.0, 0.30, z_t, 60)
    assert z.size == 61 and np.any(z == z_t)
    assert np.all(np.diff(z) > 0.0)
    # iki parça kendi içinde düzgün, tek sıçrama boğazda
    dz = np.diff(z)
    k = int(np.argmax(z == z_t))
    assert np.allclose(dz[:k], dz[0]) and np.allclose(dz[k:], dz[-1])


def test_nozzle_axial_stations_min_r_kontur_min_r_BIT():
    zc = np.linspace(0.0, 300.0, 41)
    rc = 1e3 * lule_duvar_yaricapi(zc * 1e-3)
    rc[17] = 24.5                        # boğazı düzgün dışı bir düğüme koy
    zn, rn = nozzle_axial_stations(zc, rc, 32)
    assert float(np.min(rn)) == float(np.min(rc))
    assert zn[int(np.argmin(rn))] == zc[int(np.argmin(rc))]
    # KONTROL (eski kural): düz linspace boğazı KAÇIRIR
    z_eski = np.linspace(zc[0], zc[-1], 33)
    assert float(np.min(np.interp(z_eski, zc, rc))) > float(np.min(rc))
    # build_nozzle_grid aynı kuralı taşır
    g = build_nozzle_grid(np.stack([zc, rc], 1), 32, 6)
    assert float(np.min(g.R[:, -1])) == pytest.approx(np.min(rc) * 1e-3,
                                                       rel=0, abs=1e-15)


def test_C7_ornek_motor_konturu_bogaz_yakalanir():
    """DK C7 Example Hybrid konturu: coarse (60) ızgara min r = kontur min r."""
    yol = kanit_gerekli(DK_KOSUMLAR / 'C7' / 'calculate_motor.json')
    m = json.loads(yol.read_text(encoding='utf-8'))
    pts = np.asarray(m['nozzle_contour']['points'], float)
    for ni in (60, 120):
        zn, rn = nozzle_axial_stations(pts[:, 0], pts[:, 1], ni)
        assert float(np.min(rn)) == float(np.min(pts[:, 1]))
        assert zn.size == ni + 1


# ---------------------------------------------------------------------------
# F-05 — kayma duvarı TRRS yıldız basıncı
# ---------------------------------------------------------------------------

def test_trrs_sembolik_birinci_mertebe_akustikle_uyumlu_ve_pozitif():
    """sympy: p·[1 + (γ−1)M/2]^(2γ/(γ−1)) = p(1 + γM + O(M²)); üs
    2γ/(γ−1) yerine γ/(γ−1) yazılırsa (mutasyon) birinci mertebe katsayı
    γ/2 olur ve bu bekçi kırmızıya düşer."""
    import sympy as sp
    g, M, p = sp.symbols('gamma M p', positive=True)
    p_tr = p * (1 + (g - 1) / 2 * M) ** (2 * g / (g - 1))
    seri = sp.series(p_tr, M, 0, 3).removeO()
    assert sp.simplify(seri.coeff(M, 0) - p) == 0
    assert sp.simplify(seri.coeff(M, 1) - g * p) == 0        # akustik uyum
    # ikinci mertebe katsayı: p·γ(γ+1)/4·M² (akustikten ayrılma O(M²))
    assert sp.simplify(seri.coeff(M, 2) - p * g * (g + 1) / 4) == 0
    # boyut: p ile aynı (çarpan boyutsuz); pozitiflik M > −2/(γ−1)
    for gv, Mv in ((1.2, -9.99), (1.4, -4.99), (1.1512, -13.0), (1.4, 3.0)):
        assert float(p_tr.subs({g: gv, M: Mv, p: 1.0})) > 0.0


def test_trrs_sayisal_pozitif_ve_vakum_siniri():
    g = 1.2
    M = np.array([-0.2520, -1.25 / g, -5.0, -10.0, -12.0, 0.0, 0.5])
    p = wall_star_pressure_trrs(1.0e5, M, g)
    assert np.all(p[:3] > 0.0)
    # −10 = vakum sınırı: gerçelde tam 0 (Lean wallStarTR_at_vacuum); kayan
    # noktada taban 0,5·(γ−1)·M yuvarlama artığı 2,2e-16 → p* ≈ 1e-183 (ölçüldü),
    # sınırın ötesinde (−12) kırpma TAM 0 verir; ikisi de negatif DEĞİL.
    assert 0.0 <= p[3] < 1e-100 and p[4] == 0.0
    assert p[5] == 1.0e5
    # akustik biçim M = −1,25/γ'da NEGATİF (eski kusur), TRRS pozitif
    assert 1.0e5 * (1.0 + g * (-1.25 / g)) < 0.0 and p[1] > 0.0


def test_wall_star_pressure_olcumu_TRRS_isletilen_akustik_kiyas():
    """test_d31 K4 vakası (γ = 1,2, M_n = −1,25/γ): eskiden pozitif_mi False."""
    g = 1.2
    ni, nj = 1, 1
    rho, p = 1.0, 2.0e5
    a = np.sqrt(g * p / rho)
    ur = -1.25 / g * a                           # duvar normali (0, 1)
    U = prim_to_cons_axisym(np.full((ni, nj), rho), np.zeros((ni, nj)),
                            np.full((ni, nj), ur), np.full((ni, nj), p), g)

    class _Grid:
        pass
    geom = {'wall_n_hat': np.array([[0.0, 1.0]])}
    M_n, p_ak, p_tr, ozet = wall_star_pressure(U, _Grid(), g, geom=geom)
    assert M_n[0] == pytest.approx(-1.25 / g)
    assert p_ak[0] == pytest.approx(-5.0e4, rel=1e-12)
    assert p_tr[0] > 0.0
    assert ozet['operator'] == 'trrs' and ozet['pozitif_mi'] is True
    assert ozet['negatif_p_star_yuz_sayisi'] == 0
    assert ozet['akustik_pozitif_mi'] is False
    assert ozet['akustik_negatif_yuz_sayisi'] == 1


def test_residual_duvar_akisi_TRRS_kullanir(monkeypatch):
    """residual_axisym duvar yüzünü wall_star_pressure_trrs ile kurar."""
    cagri = []
    gercek = ec.wall_star_pressure_trrs

    def casus(p, M_n, gamma):
        cagri.append((np.shape(p), float(gamma)))
        return gercek(p, M_n, gamma)
    monkeypatch.setattr(ec, 'wall_star_pressure_trrs', casus)
    g = lule_gridi(12, 4)
    ni, nj = 12, 4
    w = np.zeros((ni, nj, 4))
    w[..., 0] = 3.0
    w[..., 1] = 400.0
    w[..., 3] = 2.0e6
    U = prim_to_cons_axisym(w[..., 0], w[..., 1], w[..., 2], w[..., 3],
                            LULE_GAMMA)
    _, aux = residual_axisym(U, g, LULE_GAMMA, LULE_R, LULE_P0, LULE_T0)
    assert cagri and cagri[0] == ((ni,), float(LULE_GAMMA))
    assert aux['wall_mass_flux_kg_s'] == 0.0


def test_izantropik_120x24_duvar_pstar_pozitif_ve_sensor_sessiz(lule_cozumu):
    _g, r = lule_cozumu
    ws = r['wall_star_pressure']
    assert ws['pozitif_mi'] is True and ws['operator'] == 'trrs'
    assert ws['min_p_star_Pa'] > 0.0
    assert r['shock_sensor_cells'] == 0 and r['shock_sensor_columns'] == 0
    assert r['shock_sensor_mode'] == 'cell'
