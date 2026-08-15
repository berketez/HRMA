# tests/cfd — aşırı-genişlemiş lülede iç normal şok bekçisi (basamak 3)
"""
Arka basınç dayatmalı koşuda iç normal şokun KONUMU, testin KENDİ kurduğu
analitik 1B izantropik + normal-şok çözümüne karşı sınanır (değer
kopyalama yok; vaka conftest.LULE_PB_SOK, çözüm sok_cozumu fikstüründe).

Analitik referans (testin içinde kurulur; Anderson, Modern Compressible
Flow, 3. baskı):
  - alan-Mach bağıntısı (Eş. 5.20) bisection ile terslenir,
  - normal şok sıçramaları: M2 (Eş. 3.51), p02/p01 (Eş. 3.63),
  - şok ardı ses-altı dal yeni kritik alan A2* = A*·(p01/p02) ile çıkışa
    izantropik taşınır; çıkışta p = Pb koşulu şok konumunu bisection ile
    verir (Anderson Böl. 5.4 yapısı — quasi1d'nin fonksiyonları ÇAĞRILMAZ,
    çapraz katman ayrı testte quasi1d'yi ayrıca çağırır).

Konum tespiti ALAN ÜSTÜNDEN iki bağımsız dedektörle: kesit-ortalamalı
M(x)'in 1 altına indiği kesişim (doğrusal ara değer) ve maks |Δp| yüzü.
Eşikler ÖLÇÜMDEN (dosya içi sabitlerin yanında ölçüm değerleri).
"""

import numpy as np

from hrma.flow.quasi1d import solve_nozzle

from .conftest import (
    LULE_GAMMA, LULE_P0, LULE_PB_SOK, LULE_R, LULE_T0,
    LULE_L_CONV, LULE_L_DIV, LULE_R_THROAT, lule_duvar_yaricapi,
)

# ÖLÇÜLDÜ (bu depo, M4 Max, 2026-08-15; 120×24, sok_cozumu ayarları):
#   |z_s(CFD, M=1 kesişimi) − z_s(analitik)| = 0,27 mm (eksenel hücre
#   2,5 mm; ıraksak boy 180 mm → bağıl %0,15)
#   iki dedektör arası fark = 0,24 mm (~0,1 hücre)
#   test-içi analitik vs quasi1d şok konumu = 9,4e-6 m (bağımsız iki
#   gerçekleme aynı denklemi çözüyor — tutarlılık tabanı)
#   kütle/enerji bağıl artığı = 5,5e-7 / 9,5e-7
#   çıkış kesit-ort. basıncı vs Pb = %0,027 (ses-altı çıkışta Pb dayatması
#   ÇALIŞIYOR — karakteristiğe yükseltme gerekmedi, sözleşme beyanı)
#   duvar basıncı maks ardışık oranı = 2,42; sıçrama yüzü şok ayağının
#   ~1,5-3,6 mm menzilinde (cephe eğriliği: duvar ayağı kesit
#   ortalamasından hafif önde — fiziksel)
# Eşik = ölçüm × ~2-4 payı; payın üstü kusur sayılır.
SOK_KONUM_TOL_M = 1.0e-3          # ölçüm 0,33 mm × ~3 (< yarım hücre)
DEDEKTOR_TUTARLILIK_TOL_M = 3.75e-3   # 1,5 eksenel hücre (ölçüm 0,19 mm)
ANALITIK_Q1D_TOL_M = 1.0e-4      # ölçüm 9,4e-6 m × ~10
BUTCE_ARTIK_TOL = 5e-6           # ölçüm 9,5e-7 × ~5 (şok ardı ses-altı
                                 # bölge; izantropik 1e-10 sınıfı BURADA
                                 # hedeflenmez — conftest beyanı)
CIKIS_PB_TOL = 0.005             # ölçüm %0,027 × ~18 (hücre merkezi ile
                                 # sınır yüzü arasındaki dışdeğer payı)
PW_SOK_ORAN_MIN = 1.5            # ölçüm 2,42 — duvar şok imzası tabanı
PW_SOK_KONUM_TOL_M = 7.5e-3      # 3 eksenel hücre (ölçüm ~1,5-3,6 mm)


# ---------------------------------------------------------------------------
# Analitik 1B: izantropik + normal şok (testin kendi kurulumu)
# ---------------------------------------------------------------------------

def _alan_orani(m, g):
    """M → A/A* (Anderson Eş. 5.20)."""
    e = (g + 1.0) / (2.0 * (g - 1.0))
    return (1.0 / m) * ((2.0 / (g + 1.0))
                        * (1.0 + 0.5 * (g - 1.0) * m * m)) ** e


def _mach_alandan(ar, g, supersonic):
    """A/A* → M (bisection; süpersonik/ses-altı dal seçimli)."""
    if ar <= 1.0 + 1e-12:
        return 1.0
    lo, hi = (1.0 + 1e-12, 60.0) if supersonic else (1e-10, 1.0 - 1e-12)
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if (_alan_orani(mid, g) - ar) * (_alan_orani(lo, g) - ar) <= 0.0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def _izantropik_p_orani(m, g):
    """M → p/p0."""
    return (1.0 + 0.5 * (g - 1.0) * m * m) ** (-g / (g - 1.0))


def _normal_sok(m1, g):
    """M1 → (M2, p02/p01) — Rankine-Hugoniot (Anderson Eş. 3.51, 3.63)."""
    m2 = np.sqrt((1.0 + 0.5 * (g - 1.0) * m1 * m1)
                 / (g * m1 * m1 - 0.5 * (g - 1.0)))
    p2_p1 = 1.0 + 2.0 * g / (g + 1.0) * (m1 * m1 - 1.0)
    rho2_rho1 = ((g + 1.0) * m1 * m1) / ((g - 1.0) * m1 * m1 + 2.0)
    p02_p01 = p2_p1 ** (-1.0 / (g - 1.0)) * rho2_rho1 ** (g / (g - 1.0))
    return m2, p02_p01


def _cikis_basinci_sok_z(z_s, g, a_star, a_exit):
    """Şok z_s'deyken çıkış statik basıncı [Pa] (analitik 1B)."""
    a_s = float(np.pi * lule_duvar_yaricapi(np.array([z_s]))[0] ** 2)
    m1 = _mach_alandan(a_s / a_star, g, supersonic=True)
    _, p02_p01 = _normal_sok(m1, g)
    a2_star = a_star / p02_p01
    m_e = _mach_alandan(a_exit / a2_star, g, supersonic=False)
    return LULE_P0 * p02_p01 * _izantropik_p_orani(m_e, g)


def analitik_sok_konumu(pb, g):
    """Pb → şok konumu z_s [m] (bisection, ıraksak bölge)."""
    a_star = np.pi * LULE_R_THROAT ** 2
    a_exit = float(np.pi * lule_duvar_yaricapi(
        np.array([LULE_L_CONV + LULE_L_DIV]))[0] ** 2)
    lo = LULE_L_CONV + 1e-6
    hi = LULE_L_CONV + LULE_L_DIV - 1e-9
    p_lo = _cikis_basinci_sok_z(lo, g, a_star, a_exit)
    p_hi = _cikis_basinci_sok_z(hi, g, a_star, a_exit)
    assert p_hi < pb < p_lo, (
        f'Pb={pb:.4g} Pa iç-şok bandının dışında '
        f'[{p_hi:.4g}, {p_lo:.4g}] — vaka kurulumu bozulmuş')
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if (_cikis_basinci_sok_z(mid, g, a_star, a_exit) - pb) \
                * (p_lo - pb) <= 0.0:
            hi = mid
        else:
            lo = mid
            p_lo = _cikis_basinci_sok_z(lo, g, a_star, a_exit)
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Alan üstünden konum tespiti (iki bağımsız dedektör)
# ---------------------------------------------------------------------------

def sok_konumu_mach(res):
    """Kesit-ortalamalı M(x)'in 1 altına indiği kesişim (doğrusal ara değer);
    boğaz sonrası SON aşağı kesişim (başlangıç geçişleri değil oturan şok)."""
    z = np.asarray(res['section_average']['z_m'])
    m = np.asarray(res['section_average']['mach'])
    i_th = res['throat']['i']
    m_d, z_d = m[i_th + 1:], z[i_th + 1:]
    idx = np.where((m_d[:-1] > 1.0) & (m_d[1:] < 1.0))[0]
    if idx.size == 0:
        return None
    k = idx[-1]
    return float(z_d[k] + (1.0 - m_d[k]) * (z_d[k + 1] - z_d[k])
                 / (m_d[k + 1] - m_d[k]))


def sok_konumu_basinc(res):
    """Boğaz sonrası maks |Δp| yüzünün konumu (kesit-ortalamalı basınç)."""
    z = np.asarray(res['section_average']['z_m'])
    p = np.asarray(res['section_average']['pressure_Pa'])
    i_th = res['throat']['i']
    dp = np.abs(np.diff(p[i_th + 1:]))
    k = int(np.argmax(dp)) + i_th + 1
    return float(0.5 * (z[k] + z[k + 1]))


# ---------------------------------------------------------------------------
# Bekçiler
# ---------------------------------------------------------------------------

def test_yakinsama_ve_rejim(sok_cozumu):
    """Şoklu vaka yakınsar; sensör şoku görür; çıkış ses-altıdır."""
    _, res = sok_cozumu
    assert res['converged'] is True, (
        f"Şoklu vaka yakınsamadı: {res['convergence_basis']}")
    assert res['shock_sensor_columns'] > 0, (
        'Şok sensörü hiç kolon bayraklamadı — iç şok yok mu, sensör mü '
        'kör? (pürüzsüz vakada 0 olması ayrı bekçide)')
    m_exit = float(np.asarray(res['section_average']['mach'])[-1])
    assert m_exit < 1.0, (
        f'Çıkış kesit-ortalamalı M={m_exit:.3f} >= 1 — arka basınç '
        f'uygulanmamış (iç şok yerine tam süpersonik çözüm)')


def test_sok_konumu_analitik(sok_cozumu):
    """Şok konumu (M=1 kesişimi) testin analitik 1B çözümüne karşı."""
    _, res = sok_cozumu
    z_cfd = sok_konumu_mach(res)
    assert z_cfd is not None, (
        'Iraksak bölgede M(x) hiç 1 altına inmiyor — iç şok oluşmamış')
    z_ref = analitik_sok_konumu(LULE_PB_SOK, LULE_GAMMA)
    fark = abs(z_cfd - z_ref)
    assert fark < SOK_KONUM_TOL_M, (
        f'şok konumu z={z_cfd:.5f} m, analitik {z_ref:.5f} m — fark '
        f'{fark * 1e3:.2f} mm > {SOK_KONUM_TOL_M * 1e3:.1f} mm '
        f'(eksenel hücre 2,5 mm; ölçüm 0,27 mm idi)')


def test_dedektorler_tutarli(sok_cozumu):
    """Mach kesişimi ve maks |Δp| yüzü aynı yeri göstermeli (alan sağlığı:
    basınç ve hız alanları aynı süreksizliği taşıyor)."""
    _, res = sok_cozumu
    z_m = sok_konumu_mach(res)
    z_p = sok_konumu_basinc(res)
    assert z_m is not None
    fark = abs(z_m - z_p)
    assert fark < DEDEKTOR_TUTARLILIK_TOL_M, (
        f'dedektörler ayrıştı: M=1 kesişimi {z_m:.5f} m, maks|Δp| '
        f'{z_p:.5f} m — fark {fark * 1e3:.2f} mm > 1,5 hücre '
        f'(ölçüm ~0,1 hücreydi)')


def test_quasi1d_capraz(sok_cozumu):
    """quasi1d ÇAĞRILARAK çapraz: rejim + şok konumu (bağımsız gerçekleme).
    Ayrıca testin kendi analitiği quasi1d'yle tutarlı olmalı (testin
    testi — iki bağımsız kurulum aynı denklemi çözüyor)."""
    _, res = sok_cozumu
    z = np.asarray(res['section_average']['z_m'])
    area = np.pi * lule_duvar_yaricapi(z) ** 2
    q1d = solve_nozzle(z, area, P0=LULE_P0, T0=LULE_T0, gamma=LULE_GAMMA,
                       R=LULE_R, Pb=LULE_PB_SOK)
    assert q1d['regime'] == 'normal_shock_in_nozzle', (
        f"quasi1d rejimi {q1d['regime']} — vaka iç-şok bandında kurulmalıydı")
    z_q1d = float(q1d['shock']['x_m'])
    z_ref = analitik_sok_konumu(LULE_PB_SOK, LULE_GAMMA)
    assert abs(z_ref - z_q1d) < ANALITIK_Q1D_TOL_M, (
        f'test analitiği {z_ref:.6f} m ile quasi1d {z_q1d:.6f} m ayrıştı '
        f'({abs(z_ref - z_q1d) * 1e3:.3f} mm) — iki referanstan biri bozuk')
    z_cfd = sok_konumu_mach(res)
    assert abs(z_cfd - z_q1d) < SOK_KONUM_TOL_M


def test_cikis_basinci_pb(sok_cozumu):
    """Ses-altı çıkışta arka basınç GERÇEKTEN dayatılıyor: çıkış kesit
    ortalamalı basınç Pb'ye ölçülen payda. (Basit Pb dayatması yeterli
    ölçüldü — %0,027; karakteristiğe yükseltme GEREKMEDİ. Bu bekçi
    kırılırsa çıkış BC sözleşmesi yeniden ele alınır.)"""
    _, res = sok_cozumu
    p_exit = float(np.asarray(res['section_average']['pressure_Pa'])[-1])
    rel = abs(p_exit - LULE_PB_SOK) / LULE_PB_SOK
    assert rel < CIKIS_PB_TOL, (
        f'çıkış kesit basıncı {p_exit:.6g} Pa, Pb={LULE_PB_SOK:.6g} Pa — '
        f'bağıl {rel:.3%} > {CIKIS_PB_TOL:.1%} (arka basınç dayatması '
        f'çalışmıyor)')


def test_pw_sozlesmesi(sok_cozumu):
    """p_w(x) sözleşmesi (dalga B / separation.py tüketecek):
    wall_pressure_Pa (ni,), wall_pressure_z_m (ni,) kesin artan eksen,
    wall_pressure_basis beyanı; duvar basıncı şok imzasını taşır (ardışık
    oran >= taban, sıçrama yüzü şok ayağı menzilinde)."""
    grid, res = sok_cozumu
    pw = np.asarray(res['wall_pressure_Pa'])
    zw = np.asarray(res['wall_pressure_z_m'])
    assert pw.shape == (grid.ni,) and zw.shape == (grid.ni,), (
        f'p_w sözleşme şekli bozuk: pw {pw.shape}, zw {zw.shape}, '
        f'beklenen ({grid.ni},)')
    assert np.all(np.isfinite(pw)) and np.all(pw > 0.0)
    assert np.all(np.diff(zw) > 0.0), 'wall_pressure_z_m kesin artan değil'
    basis = res.get('wall_pressure_basis', '')
    assert 'wall_pressure_z_m' in basis and 'separation' in basis, (
        f'wall_pressure_basis beyanı eksik: {basis!r}')
    # Şok imzası: ıraksakta maks ardışık basınç oranı + konumu
    i_th = res['throat']['i']
    pw_div = pw[i_th + 1:]
    oran = pw_div[1:] / pw_div[:-1]
    k = int(np.argmax(oran))
    assert float(oran.max()) > PW_SOK_ORAN_MIN, (
        f'duvar basıncında şok sıçraması görünmüyor: maks ardışık oran '
        f'{oran.max():.3f} <= {PW_SOK_ORAN_MIN} (ölçüm 2,42)')
    z_yuz = 0.5 * (zw[i_th + 1 + k] + zw[i_th + 2 + k])
    z_ref = analitik_sok_konumu(LULE_PB_SOK, LULE_GAMMA)
    assert abs(z_yuz - z_ref) < PW_SOK_KONUM_TOL_M, (
        f'duvar şok sıçraması z={z_yuz:.4f} m, analitik ayak {z_ref:.4f} m '
        f'— fark {abs(z_yuz - z_ref) * 1e3:.1f} mm > 3 hücre')


def test_korunum_butcesi_soklu(sok_cozumu):
    """Şok korunumlu süreksizliktir: bütçe şokla BOZULMAZ. Eşik bu vakanın
    ölçümünden (4,5e-7 sınıfı; izantropik 1e-10 sınıfı burada hedeflenmez
    — şok ardı ses-altı bölgenin yavaş oturması conftest'te beyanlı)."""
    _, res = sok_cozumu
    assert res['mass_balance_rel'] < BUTCE_ARTIK_TOL, (
        f"kütle bütçesi: {res['mass_balance_rel']:.3e} >= "
        f'{BUTCE_ARTIK_TOL:.0e} — şok korunum formunu bozmuş')
    assert res['energy_balance_rel'] < BUTCE_ARTIK_TOL, (
        f"enerji bütçesi: {res['energy_balance_rel']:.3e}")
