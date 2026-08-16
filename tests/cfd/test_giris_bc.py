# tests/cfd — ses-altı rezervuar GİRİŞ sınır koşulu bekçileri (daralma merdiveni)
"""
Giriş sınır koşulunun daralma oranı (CR) merdiveni: gerçek motor konturları
yüksek CR taşır (hibrit 5 kN / 20 bar sınıfı: CR ≈ 9,7-11) ve eski giriş
BC'si tam orada kırılıyordu. Bu dosya kırılmayı ÖLÇÜM olarak kilitler.

KÖK (ÖLÇÜLDÜ, bu depo, 2026-08-16)
-----------------------------------
Eski BC iç hücreden STATİK BASINCI dışdeğerleyip Mach'ı izantropik p→M
bağıntısından çözüyordu. O eşlemenin türevi

    dM/d(p/P0) = −1/(γM)        ⇒  d(ρu)/(ρu) / d(p/P0) ≈ −1/(γM²)

olduğundan M→0'da dikleşir: iç bölgedeki basınç gürültüsü giriş kütle
akısına 1/(γM²) kazancıyla yansır. Kazanç ÖLÇÜLDÜ (γ=1,2, izantropik iç
durum, %0,01 basınç tedirginliği):

    M       eski kazanç   karakteristik kazanç
    0,050     −338            −95
    0,061     −224            −77
    0,100      −83            −45
    0,150      −36            −28
    0,310       −7,8          −11,1

Yeni (karakteristik) biçim giden C⁻ karakteristiğinin değişmezini
J⁻ = u − 2a/(γ−1) dışdeğerler; künye ve türetim
``hrma.cfd.euler_core.INLET_BC_BASIS`` + fonksiyon docstring'indedir
(Blazek §8.4; Whitfield & Janus, AIAA-84-1552).

ÖNCE / SONRA (bu dosyanın konturu, 60×12, çözücü varsayılanları)
----------------------------------------------------------------
    CR     M_giriş   ESKİ BC                          YENİ BC
                     yak. / iter / kalıntı / i<3      yak. / iter / kalıntı / i<3
     2,0   0,312     EVET /  4698 / 9,9e-9 /  3,3%    EVET /  4677 / 5,2e-9 / 2,4%
     4,0   0,150     EVET / 16047 / 1,0e-8 /  3,2%    EVET / 15830 / 1,0e-8 / 3,6%
     6,0   0,099     EVET /  6141 / 3,6e-10/ 21,8%    EVET /  8671 / 2,9e-10/ 1,9%
    10,0   0,059     HAYIR/ 20000 / 5,7e-1 / 99,99%   EVET /  5981 / 7,6e-10/ 1,0%
    12,0   0,049     HAYIR/ 20000 / 4,9e-1 / 99,99%   EVET /  6978 / 3,3e-10/ 3,6%
("i<3" = yoğunluk kalıntısının ilk üç GİRİŞ kolonunda toplanan payı; eski
BC'de kırılan vakalarda kalıntının tamamı oradaydı — kusurun imzası budur.
Kütle bütçesi artığı eski BC'de CR 10/12'de %3,5, yenisinde 8e-10 sınıfı.)

Kırılma ÇÖZÜNÜRLÜKLE geçmiyor — aynı kontur, CR 10, 120×24:
    ESKİ BC : yakınsamadı, 20000 iter, kalıntı 8,2e-1, kütle artığı 1,8e-2,
              i<3 = %99,99
    YENİ BC : yakınsadı, 12130 iter, kalıntı 5,7e-10, kütle artığı 6,1e-10,
              i<3 = %2,73, debi quasi1d'ye %0,078

VAKA GEOMETRİSİ (analitik, motor sonucuna bağımlılık YOK)
---------------------------------------------------------
conftest'in kosinüs ailesiyle aynı ruh; tek fark yakınsak boyun oda
yarıçapıyla ÖLÇEKLENMESİ: L_conv = L0 + c·(r_oda − r_boğaz). Bu, iki şeyi
birden sabit tutar ve merdiveni SAF bir CR taraması yapar:
  (1) duvar eğimi CR ile patlamaz (sabit L'de yüksek CR dik duvar demekti),
  (2) boğaz eğrilik yarıçapı merdiven boyunca ~sabit kalır
      (ÖLÇÜLDÜ: R_c = 1/κ ≈ 0,133-0,170 m ≈ 5,3-6,8·r_boğaz).
(2) önemlidir: sivri boğaz, quasi-1B'ye göre GERÇEK bir 2B debi açığı
(eğri sonik çizgi, akış katsayısı) doğurur ve o açık giriş BC'sinin
kusuruyla karışırdı. Boğaz kasten yumuşak seçilerek quasi1d çaprazı
GİRİŞ tarafını ölçer hâle getirildi.

BEKÇİLERİN KAPSAMI
------------------
  (a) merdivenin her basamağı çözücü VARSAYILANLARIYLA (max_iters=20000)
      yakınsar — ürün yolunun ta kendisi,
  (b) kütle bütçesi artığı ≤ 1e-8 bağıl,
  (c) debi, quasi1d çaprazına ≤ %0,5 (quasi1d ÇAĞRILIR, kopyalanmaz),
  (d) kalıntı giriş kolonlarında YIĞILMAZ (kusurun imzası),
  (e) gerçek hibrit sınıfı vaka (CR 10) 'standard' çözünürlükte de (120×24)
      aynı ölçütleri geçer,
  (f) BC'nin kendi cebiri: rezervuar izantropu üstündeki bir iç durum
      AYNEN geri gelir (tutarlılık), Riemann bandı yakınsamış çözümde
      ETKİN DEĞİLDİR, koşullanma kazancı eski eşlemeninkinden küçüktür,
  (g) beyan alanları (inlet_bc, inlet_bc_basis) yöntemi ve künyeyi taşır.
"""

import numpy as np
import pytest

from hrma.cfd.euler_core import (
    INLET_BC_BASIS,
    INLET_BC_NAME,
    inlet_state_from_stagnation,
    precompute_geometry,
    prim_to_cons_axisym,
    residual_axisym,
)
from hrma.cfd.grid_axisym import build_grid_from_wall
from hrma.cfd.steady import DEFAULT_MAX_ITERS, solve_steady_axisym
from hrma.flow.quasi1d import mach_from_area_ratio, solve_nozzle

# Çalışma noktası — conftest'in LULE_ vakasıyla aynı gaz (roket sınıfı).
GIRIS_GAMMA = 1.2
GIRIS_R = 350.0
GIRIS_P0 = 4.0e6
GIRIS_T0 = 3200.0
GIRIS_PB = 2.0e3         # derin eksik-genleşme: lüle içi tam süpersonik

# Kontur ailesi
GIRIS_R_THROAT = 0.025
GIRIS_R_EXIT = 0.040
GIRIS_L_DIV = 0.18
GIRIS_L_CONV0 = 0.06     # yakınsak boyun taban parçası [m]
GIRIS_L_CONV_EGIM = 2.72  # L_conv = L0 + EGIM·Δr → maks yarı açı ≈ 10-23°

# Merdiven basamakları (görev sözleşmesi) ve ızgaralar
GIRIS_CR_MERDIVENI = (2.0, 4.0, 6.0, 10.0, 12.0)
GIRIS_NI, GIRIS_NJ = 60, 12          # 'coarse' (ucun varsayılan seviyesi)
GIRIS_NI_STD, GIRIS_NJ_STD = 120, 24  # 'standard'
GIRIS_CR_HIBRIT = 10.0               # gerçek hibrit sınıfı (5 kN/20 bar ≈ 9,7)

# Eşikler — hepsi ÖLÇÜMDEN (yukarıdaki tablo + aşağıdaki notlar).
#: Kütle bütçesi: ölçülen en kötü 8,0e-10 → eşik 12× paylı.
GIRIS_KUTLE_TOL = 1e-8
#: Debi/quasi1d: ölçülen en kötü %0,226 (60×12, CR 10) ve %0,078 (120×24)
#: → eşik %0,5 (görev sözleşmesi; ölçümün ~2,2 katı).
GIRIS_DEBI_TOL = 0.005
#: Kalıntının ilk 3 giriş kolonundaki payı: ölçülen en kötü %3,6 → eşik
#: %15. Kusurun imzası %99,99'du; eşik iki rejimin arasındaki bir mertebeden
#: fazla boşluğun içindedir (60 kolonun 3'ü "eşit pay"da %5 ederdi).
GIRIS_KALINTI_PAY_TOL = 0.15


def giris_duvar_yaricapi(z, r_chamber, l_conv):
    """Analitik duvar r_w(z): kosinüs yakınsak + kosinüs ıraksak [m]."""
    z = np.asarray(z, dtype=float)
    conv = GIRIS_R_THROAT + (r_chamber - GIRIS_R_THROAT) * (
        0.5 + 0.5 * np.cos(np.pi * np.clip(z, 0.0, l_conv) / l_conv))
    div = GIRIS_R_THROAT + (GIRIS_R_EXIT - GIRIS_R_THROAT) * (
        0.5 - 0.5 * np.cos(np.pi * np.clip(z - l_conv, 0.0, GIRIS_L_DIV)
                           / GIRIS_L_DIV))
    return np.where(z < l_conv, conv, div)


def giris_kontur_parametreleri(cr):
    """(r_oda, L_conv) — daralma oranından; aile kuralı dosya başında."""
    r_ch = GIRIS_R_THROAT * float(np.sqrt(cr))
    return r_ch, GIRIS_L_CONV0 + GIRIS_L_CONV_EGIM * (r_ch - GIRIS_R_THROAT)


def _coz(cr, ni, nj):
    """Bir basamağı çözücü VARSAYILANLARIYLA koşar; (grid, res, r_ch, l_conv)."""
    r_ch, l_conv = giris_kontur_parametreleri(cr)
    z_nodes = np.linspace(0.0, l_conv + GIRIS_L_DIV, ni + 1)
    grid = build_grid_from_wall(z_nodes,
                                giris_duvar_yaricapi(z_nodes, r_ch, l_conv),
                                nj)
    res = solve_steady_axisym(grid, P0=GIRIS_P0, T0=GIRIS_T0,
                              gamma=GIRIS_GAMMA, R=GIRIS_R, Pb=GIRIS_PB,
                              max_iters=DEFAULT_MAX_ITERS)
    return grid, res, r_ch, l_conv


def _kolon_kalinti_payi(res, grid):
    """Yoğunluk kalıntısının kolon başına (hacim ağırlıklı) payı, (ni,).

    Beyan: kalıntı SON alandan yeniden hesaplanır (sürücü içindeki donmuş
    eğim durumu taşınmaz); ölçülen şey kalıntının UZAYSAL DAĞILIMIdır,
    sürücünün son adımının bit kopyası değildir.
    """
    f = res['fields']
    U = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                            f['pressure_Pa'], GIRIS_GAMMA)
    r1, _ = residual_axisym(U, grid, GIRIS_GAMMA, GIRIS_R, GIRIS_P0,
                            GIRIS_T0, Pb=GIRIS_PB,
                            geom=precompute_geometry(grid))
    kolon = np.sum(r1[..., 0] ** 2 * grid.volume, axis=1)
    return kolon / max(float(np.sum(kolon)), 1e-300)


def _quasi1d_debisi(res, r_ch, l_conv):
    """quasi1d ÇAĞRILIR (değer kopyalanmaz): aynı geometri, aynı γ/R."""
    z_sec = np.asarray(res['section_average']['z_m'])
    area = np.pi * giris_duvar_yaricapi(z_sec, r_ch, l_conv) ** 2
    q1d = solve_nozzle(z_sec, area, P0=GIRIS_P0, T0=GIRIS_T0,
                       gamma=GIRIS_GAMMA, R=GIRIS_R, Pb=GIRIS_PB)
    return float(q1d['mass_flow_kg_s'])


@pytest.fixture(scope='session')
def giris_merdiveni():
    """CR merdiveni (60×12) — session kapsamında BİR kez (süit disiplini).

    ÖLÇÜLDÜ (M4 Max, 2026-08-16, numba arka ucu): beş basamak toplam ~25 s;
    en pahalısı CR 4 (15830 iterasyon, ~9 s).
    """
    cikti = {}
    for cr in GIRIS_CR_MERDIVENI:
        grid, res, r_ch, l_conv = _coz(cr, GIRIS_NI, GIRIS_NJ)
        cikti[cr] = {
            'grid': grid, 'res': res,
            'mach_giris': float(mach_from_area_ratio(cr, GIRIS_GAMMA,
                                                     supersonic=False)),
            'mdot_q1d': _quasi1d_debisi(res, r_ch, l_conv),
            'kolon_payi': _kolon_kalinti_payi(res, grid),
        }
    return cikti


@pytest.fixture(scope='session')
def giris_hibrit_standart():
    """Gerçek hibrit sınıfı vaka (CR 10) 'standard' ızgarada (120×24).

    ÖLÇÜLDÜ: 12130 iterasyon, ~11 s, kalıntı 5,7e-10, kütle artığı 6,1e-10,
    debi quasi1d'ye %0,078.
    """
    grid, res, r_ch, l_conv = _coz(GIRIS_CR_HIBRIT, GIRIS_NI_STD,
                                   GIRIS_NJ_STD)
    return {'grid': grid, 'res': res,
            'mdot_q1d': _quasi1d_debisi(res, r_ch, l_conv),
            'kolon_payi': _kolon_kalinti_payi(res, grid)}


# ---------------------------------------------------------------------------
# (a)-(d) merdiven: her basamak ürün yolunda yakınsar ve doğru
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cr', GIRIS_CR_MERDIVENI)
def test_merdiven_yakinsadi(giris_merdiveni, cr):
    """Her daralma oranı çözücü VARSAYILANLARIYLA (20000 tavan) oturur."""
    v = giris_merdiveni[cr]
    res = v['res']
    assert res['converged'] is True, (
        f"CR {cr} (giriş Mach {v['mach_giris']:.4f}) yakınsamadı: "
        f"{res['convergence_basis']} — son kalıntı "
        f"{res['residual_history'][-1]:.3e}, kalıntının ilk 3 giriş "
        f"kolonundaki payı {100 * float(np.sum(v['kolon_payi'][:3])):.2f}% "
        f"(payın %99'a tırmanması ESKİ p→M giriş eşlemesinin imzasıdır)")
    assert res['iterations'] < DEFAULT_MAX_ITERS


@pytest.mark.parametrize('cr', GIRIS_CR_MERDIVENI)
def test_merdiven_kutle_butcesi(giris_merdiveni, cr):
    """Giriş/çıkış kütle akısı bütçesi ≤ 1e-8 bağıl."""
    res = giris_merdiveni[cr]['res']
    assert res['mass_balance_rel'] < GIRIS_KUTLE_TOL, (
        f"CR {cr}: kütle bütçesi artığı {res['mass_balance_rel']:.3e} > "
        f'{GIRIS_KUTLE_TOL:g} — giriş akısı çıkış akısını karşılamıyor')


@pytest.mark.parametrize('cr', GIRIS_CR_MERDIVENI)
def test_merdiven_debi_quasi1d_caprazi(giris_merdiveni, cr):
    """Debi, quasi1d çaprazına ≤ %0,5 (aynı geometri, aynı gaz)."""
    v = giris_merdiveni[cr]
    mdot = v['res']['mass_flow_out_kg_s']
    rel = abs(mdot - v['mdot_q1d']) / v['mdot_q1d']
    assert rel < GIRIS_DEBI_TOL, (
        f'CR {cr}: CFD debisi {mdot:.6g} kg/s, quasi1d {v["mdot_q1d"]:.6g} '
        f'kg/s — bağıl sapma {rel:.3%} > {GIRIS_DEBI_TOL:.1%}')


@pytest.mark.parametrize('cr', GIRIS_CR_MERDIVENI)
def test_merdiven_kalinti_giriste_yigilmiyor(giris_merdiveni, cr):
    """Kusurun İMZASI: kalıntı ilk giriş kolonlarında toplanmamalı."""
    v = giris_merdiveni[cr]
    pay = float(np.sum(v['kolon_payi'][:3]))
    assert pay < GIRIS_KALINTI_PAY_TOL, (
        f'CR {cr}: yoğunluk kalıntısının %{100 * pay:.2f}\'i ilk ÜÇ giriş '
        f'kolonunda — giriş sınır koşulu kalıntıyı orada üretiyor '
        f'(eski p→M eşlemesinde bu pay %99,99 ölçülmüştü)')


# ---------------------------------------------------------------------------
# (e) gerçek hibrit sınıfı vaka, 'standard' çözünürlükte
# ---------------------------------------------------------------------------

def test_hibrit_sinifi_standart_cozunurlukte(giris_hibrit_standart):
    """CR 10 (M_giriş 0,059) 120×24'te de yakınsar ve doğruluk bandındadır.

    Gerçek hibrit (5 kN / 20 bar) konturu CR ≈ 9,7 taşır; ölçülen kırılma
    tam bu banttaydı. Bekçi çözünürlükten bağımsız olduğunu kilitler:
    kırılma ÇÖZÜNÜRLÜKLE de oynuyordu (eski BC'de CR 4 60×12'de yakınsayıp
    120×24'te yakınsamıyordu — gerçek kontur ölçümü, app.py tablosu).
    """
    v = giris_hibrit_standart
    res = v['res']
    assert res['converged'] is True, (
        f"CR {GIRIS_CR_HIBRIT} 120×24'te yakınsamadı: "
        f"{res['convergence_basis']}")
    assert res['mass_balance_rel'] < GIRIS_KUTLE_TOL
    rel = abs(res['mass_flow_out_kg_s'] - v['mdot_q1d']) / v['mdot_q1d']
    assert rel < GIRIS_DEBI_TOL, (
        f'120×24 debi sapması {rel:.3%} > {GIRIS_DEBI_TOL:.1%}')
    pay = float(np.sum(v['kolon_payi'][:3]))
    assert pay < GIRIS_KALINTI_PAY_TOL, (
        f'120×24: kalıntının %{100 * pay:.2f}\'i ilk üç giriş kolonunda')


def test_cozunurluk_merdiveninde_debi_iyilesiyor(giris_merdiveni,
                                                 giris_hibrit_standart):
    """Aynı vaka ince ızgarada quasi1d'ye DAHA YAKIN olmalı.

    Bu, kalan sapmanın ıraksama değil ÇÖZÜNÜRLÜK etkisi olduğunun kanıtı
    (ÖLÇÜLDÜ: %0,226 → %0,078). Sapma ince ızgarada BÜYÜSEYDİ elimizde
    yakınsamış ama YANLIŞ bir alan olurdu.
    """
    kaba = giris_merdiveni[GIRIS_CR_HIBRIT]
    rel_kaba = abs(kaba['res']['mass_flow_out_kg_s'] - kaba['mdot_q1d']) \
        / kaba['mdot_q1d']
    ince = giris_hibrit_standart
    rel_ince = abs(ince['res']['mass_flow_out_kg_s'] - ince['mdot_q1d']) \
        / ince['mdot_q1d']
    assert rel_ince < rel_kaba, (
        f'debi sapması 60×12\'de {rel_kaba:.3%}, 120×24\'te {rel_ince:.3%} '
        f'— ince ızgara referansa yaklaşmadı')


# ---------------------------------------------------------------------------
# (f) sınır koşulunun kendi cebiri (koşusuz, saniyeler)
# ---------------------------------------------------------------------------

def _izantropik_durum(mach):
    """Rezervuar izantropu üstünde (ρ, u_z, u_r, p) — (1, 4)."""
    t = GIRIS_T0 / (1.0 + 0.5 * (GIRIS_GAMMA - 1.0) * mach ** 2)
    p = GIRIS_P0 * (t / GIRIS_T0) ** (GIRIS_GAMMA / (GIRIS_GAMMA - 1.0))
    return np.array([[p / (GIRIS_R * t), mach * np.sqrt(
        GIRIS_GAMMA * GIRIS_R * t), 0.0, p]])


def _eski_giris_esleme(w_int):
    """KIRILAN eski BC (statik basınç dışdeğerlemesi + izantropik p→M).

    Burada YALNIZ ÖLÇÜM REFERANSI olarak duruyor: koşullanma iddiası
    ("yeni biçim düşük Mach'ta daha az duyarlı") ancak iki eşleme yan yana
    ölçülünce kanıtlanır. Çözücü bu fonksiyonu ÇAĞIRMAZ.
    """
    g = GIRIS_GAMMA
    p_sonic = GIRIS_P0 * (2.0 / (g + 1.0)) ** (g / (g - 1.0))
    p = np.clip(w_int[..., 3], p_sonic, GIRIS_P0 * (1.0 - 1e-12))
    mach = np.sqrt(2.0 / (g - 1.0)
                   * ((GIRIS_P0 / p) ** ((g - 1.0) / g) - 1.0))
    temp = GIRIS_T0 / (1.0 + 0.5 * (g - 1.0) * mach * mach)
    rho = p / (GIRIS_R * temp)
    return rho, mach * np.sqrt(g * GIRIS_R * temp)


@pytest.mark.parametrize('mach', [0.03, 0.05, 0.1, 0.2, 0.4, 0.8])
def test_bc_rezervuar_izantropunda_ozdes(mach):
    """Tutarlılık: iç durum rezervuar izantropu üstündeyse hayalet = iç durum.

    Karakteristik çözüm h0 ve entropiyi dayattığı için bu ÖZDEŞLİK olmalı;
    sağlanmıyorsa ikinci derece kökün dalı ya da izantrop bağıntısı yanlış.
    """
    w = _izantropik_durum(mach)
    out = inlet_state_from_stagnation(w, GIRIS_GAMMA, GIRIS_R, GIRIS_P0,
                                      GIRIS_T0)
    for i, ad in enumerate(('ρ', 'u_z', 'u_r', 'p')):
        if i == 2:
            assert out[0, 2] == 0.0
            continue
        assert out[0, i] == pytest.approx(w[0, i], rel=1e-12), (
            f'M={mach}: hayalet {ad} = {out[0, i]:.10g}, iç durum '
            f'{w[0, i]:.10g} — karakteristik BC izantrop üstünde özdeş '
            f'olmalıydı')


@pytest.mark.parametrize('mach', [0.03, 0.05, 0.1])
def test_bc_kosullanmasi_eskisinden_iyi(mach):
    """Koşullanma: iç basınç tedirginliğine kütle akısı kazancı ÖLÇÜLÜR.

    Kazanç = d(ρu)_hayalet/(ρu) ÷ d(p_iç)/p. Eski eşleme M→0'da 1/(γM²)
    gibi patlar; karakteristik biçimde 1/((γ−1)M) sınıfındadır. Bekçi
    oranın 1'den büyük (yani yeni biçimin daha az duyarlı) olmasını ve
    eski kazancın kuramsal 1/(γM²) ile uyuşmasını ölçer.
    """
    eps = 1e-4
    w = _izantropik_durum(mach)
    wp = w.copy()
    wp[0, 3] *= (1.0 + eps)

    def _kazanc(fn):
        r0, u0 = fn(w)
        r1, u1 = fn(wp)
        return float(np.ravel((r1 * u1) / (r0 * u0) - 1.0)[0] / eps)

    def _yeni(x):
        o = inlet_state_from_stagnation(x, GIRIS_GAMMA, GIRIS_R, GIRIS_P0,
                                        GIRIS_T0)
        return o[..., 0], o[..., 1]

    k_eski = _kazanc(_eski_giris_esleme)
    k_yeni = _kazanc(_yeni)
    kuramsal = -1.0 / (GIRIS_GAMMA * mach ** 2)
    assert k_eski == pytest.approx(kuramsal, rel=0.15), (
        f'M={mach}: eski eşlemenin ölçülen kazancı {k_eski:.1f}, kuramsal '
        f'1/(γM²) = {kuramsal:.1f} — kök teşhisi bu bağıntıya dayanıyor')
    assert abs(k_yeni) < abs(k_eski), (
        f'M={mach}: karakteristik kazanç {k_yeni:.1f}, eski {k_eski:.1f} — '
        f'yeni biçim daha DUYARLI çıktı, kök çare değil')


@pytest.mark.parametrize('cr', GIRIS_CR_MERDIVENI)
def test_riemann_bandi_etkin_degil(giris_merdiveni, cr):
    """J⁻ fiziksel bandı yakınsamış çözümde ETKİN OLMAMALI (kırpma değil,
    emniyet ağı). Bant etkinse sınır durumu iç bölgeyle bağını yitirir ve
    'yakınsadı' beyanı bir kırpmanın sabit noktasını anlatır."""
    res = giris_merdiveni[cr]['res']
    g, r_gas = GIRIS_GAMMA, GIRIS_R
    f = res['fields']
    rho = f['rho_kg_m3'][0]
    uz = f['u_z_m_s'][0]
    p = f['pressure_Pa'][0]
    a0 = np.sqrt(g * r_gas * GIRIS_T0)
    k = 2.0 / (g - 1.0)
    j = uz - k * np.sqrt(g * p / rho)
    j_min, j_max = -k * a0, a0 * np.sqrt(2.0 / (g - 1.0))
    assert float(np.min(j)) > j_min, (
        f'CR {cr}: J⁻ alt banda dayandı (min {float(np.min(j)):.6g} <= '
        f'{j_min:.6g}) — iç durum rezervuardan daha yüksek durma entalpisi '
        f'taşıyor demektir')
    assert float(np.max(j)) < j_max
    pay = (float(np.min(j)) - j_min) / abs(j_min)
    assert pay > 1e-3, f'CR {cr}: alt banda pay yalnızca {pay:.2e}'


# ---------------------------------------------------------------------------
# (g) beyan alanları
# ---------------------------------------------------------------------------

def test_beyan_alanlari_yontemi_adlandiriyor(giris_merdiveni):
    """Sonuç sözlüğü hangi giriş BC'sinin koştuğunu ve künyesini söyler."""
    res = giris_merdiveni[GIRIS_CR_HIBRIT]['res']
    assert res['inlet_bc'] == INLET_BC_NAME == 'characteristic_reservoir'
    beyan = res['inlet_bc_basis']
    assert beyan == INLET_BC_BASIS
    for parca in ('Riemann', 'Blazek', 'Whitfield', 'AIAA-84-1552',
                  'J⁻ = u − 2a/(γ−1)'):
        assert parca in beyan, f'künye eksik: {parca}'
    # Hüküm cümlesi de BC'yi adlandırmalı (panelin gördüğü metin budur)
    assert INLET_BC_NAME in res['convergence_basis']
