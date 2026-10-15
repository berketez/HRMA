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

ÇIKIŞ SINIRI — KASITLI GENİŞLETME (V2, viskoz devir kusuru #2)
--------------------------------------------------------------
Bu dosya giriş BC'sinin dosyasıdır; ÇIKIŞ çapası buraya bilerek eklendi:
iki sınır koşulu aynı hayalet-durum makinesini (``euler_core``) paylaşır
ve aynı "sessiz varsayılana düşme yok" sözleşmesine tabidir — ikisini
ayrı dosyalara koymak o sözleşmeyi iki yerde yazmak olurdu.

  (h) ses-altı çıkış çapası: VARSAYILAN ('extrapolate') bugünkü kodun
      harfi harfine kendisidir (hayalet = iç durum, bit-özdeş),
  (i) 'core_pressure' kipi YALNIZ Pb=None'da ve YALNIZ ses-altı
      hücrelerde çalışır; çekirdek satırlar bit-aynı kalır,
  (j) çapa KARAKTERİSTİK-TUTARLIDIR (Blazek §8.4): p imlenirken ρ ve u
      giden dalgaların uyumluluk bağıntılarından türetilir — cebirsel
      olarak sınanır,
  (k) kolonda hiç süpersonik hücre yoksa çapa UYGULANMAZ (uydurma değer
      yerine dışdeğerleme sürer, sürücü beyan eder),
  (l) sürücü çapa kipinden BAĞIMSIZ olarak çıkıştaki ses-altı hücre
      sayısını yayımlar: çapa kapalıyken kusur SESSİZ kalmaz.
"""

import numpy as np
import pytest

from hrma.cfd.euler_core import (
    INLET_BC_BASIS,
    INLET_BC_NAME,
    OUTLET_ANCHOR_BASIS,
    OUTLET_ANCHOR_CORE_PRESSURE,
    OUTLET_ANCHOR_EXTRAPOLATE,
    OUTLET_ANCHOR_MODES,
    _outlet_state,
    inlet_state_from_stagnation,
    outlet_subsonic_count,
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
    # ÇEVRİLDİ (ÖH D32 / OH-D31-15): çözücü AÇIK yolda donmuş
    # operatörün sayısından artık hüküm VERMİYOR (converged=None,
    # convergence_status='not_evaluated'; Berke kararı 15 Eyl 2026 §3
    # seç. A; ölçüm docs/scofield/raw/OH/D32/fea-cfd/a2/once.json).
    # Eski doğruluk iddiası KAZANILMAMIŞ hükmün yerinde durmasını
    # şart koşuyordu — kusuru koruyan bekçi, yönü çevrildi. Korunan
    # yasak duruyor: ÖLÇÜLMÜŞ yakınsamama/ıraksama iddiayı geçersiz
    # kılar.
    assert res['converged'] is not False, (
        f"CR {cr} (giriş Mach {v['mach_giris']:.4f}) ÖLÇÜLMÜŞ olarak "
        f"yakınsamadı: "
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
    # ÇEVRİLDİ (ÖH D32 / OH-D31-15): çözücü AÇIK yolda donmuş
    # operatörün sayısından artık hüküm VERMİYOR (converged=None,
    # convergence_status='not_evaluated'; Berke kararı 15 Eyl 2026 §3
    # seç. A; ölçüm docs/scofield/raw/OH/D32/fea-cfd/a2/once.json).
    # Eski doğruluk iddiası KAZANILMAMIŞ hükmün yerinde durmasını
    # şart koşuyordu — kusuru koruyan bekçi, yönü çevrildi. Korunan
    # yasak duruyor: ÖLÇÜLMÜŞ yakınsamama/ıraksama iddiayı geçersiz
    # kılar.
    assert res['converged'] is not False, (
        f"CR {GIRIS_CR_HIBRIT} 120×24'te ÖLÇÜLMÜŞ olarak yakınsamadı: "
        f"{res['convergence_basis']}")
    assert res['convergence_status'] in ('converged', 'not_evaluated'), (
        f"hüküm cinsi {res['convergence_status']!r}")
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


# ===========================================================================
# (h)-(l) ÇIKIŞ SINIRI: ses-altı alt tabaka çapası (viskoz devir kusuru #2)
# ===========================================================================

def _cikis_kolonu(mach_n, p=None, gamma=GIRIS_GAMMA, R=GIRIS_R, T=2000.0):
    """Verilen normal Mach profilinden çıkış kolonu (nj, 4) + normaller.

    Normal saf +z alınır (çıkış düzlemi diktir): böylece bekçi geometri
    değil SINIR KOŞULU MANTIĞINI ölçer.
    """
    mach_n = np.asarray(mach_n, dtype=float)
    n = mach_n.size
    if p is None:
        p = np.linspace(1.0e5, 1.2e5, n)
    p = np.asarray(p, dtype=float)
    rho = p / (R * T)
    a = np.sqrt(gamma * p / rho)
    w = np.stack([rho, mach_n * a, np.zeros(n), p], axis=-1)
    n_hat = np.tile(np.array([1.0, 0.0]), (n, 1))
    return w, n_hat


def test_cikis_varsayilan_dal_bugunku_kodun_HARFI_HARFINE_kendisi():
    """extrapolate + Pb=None → hayalet = iç durum (tek ulp bile fark yok)."""
    w, n_hat = _cikis_kolonu([2.5, 2.0, 1.4, 0.9, 0.4])
    g = _outlet_state(w, n_hat, GIRIS_GAMMA, None)
    assert np.array_equal(g, w), (
        'varsayılan çıkış dalı değişmiş — Euler bit-özdeşlik sözleşmesi '
        '(§11.3) bu dalın üstünde duruyor')
    assert np.array_equal(
        _outlet_state(w, n_hat, GIRIS_GAMMA, None,
                      subsonic_anchor=OUTLET_ANCHOR_EXTRAPOLATE), w)


def test_cikis_capasi_TAM_SUPERSONIK_kolonda_etkisiz():
    """Ses-altı hücre yoksa çapa hiçbir şeyi değiştiremez (bit-aynı)."""
    w, n_hat = _cikis_kolonu([2.5, 2.2, 1.9, 1.4, 1.05])
    g = _outlet_state(w, n_hat, GIRIS_GAMMA, None,
                      subsonic_anchor=OUTLET_ANCHOR_CORE_PRESSURE)
    assert np.array_equal(g, w)
    assert outlet_subsonic_count(w, n_hat, GIRIS_GAMMA) == 0


def test_cikis_capasi_YALNIZ_ses_alti_satirlari_degistirir():
    """Çekirdek (süpersonik) satırlar bit-aynı; ses-altı satırlar çapalı."""
    mach_n = np.array([2.5, 2.2, 1.8, 1.2, 0.95, 0.6, 0.2])
    w, n_hat = _cikis_kolonu(mach_n)
    g = _outlet_state(w, n_hat, GIRIS_GAMMA, None,
                      subsonic_anchor=OUTLET_ANCHOR_CORE_PRESSURE)
    sup = mach_n >= 1.0
    assert np.array_equal(g[sup], w[sup]), 'çekirdek satırlar değişti'
    # Ses-altı satırların hepsi tabakanın KENARI (son süpersonik hücre,
    # burada indis 3) basıncını taşır
    assert np.all(g[~sup, 3] == w[3, 3])
    assert np.all(g[~sup, 3] != w[~sup, 3]), 'vaka ayırt edici değil'
    assert outlet_subsonic_count(w, n_hat, GIRIS_GAMMA) == int(np.sum(~sup))


def test_cikis_capasi_karakteristik_TUTARLI_Blazek_bagintilari():
    """ρ ve u serbest bırakılmaz: giden dalgaların uyumluluk bağıntıları.

    ρ_b = ρ_i + (p_b − p_i)/c_i²   ve   u_b = u_i + n̂·(p_i − p_b)/(ρ_i c_i)
    (Blazek §8.4). Yalnız p'yi değiştirip ρ,u'yu iç değerde bırakmak
    hayalete sahte entropi/hız sıçraması yazardı — ölçülen bedeli
    OUTLET_ANCHOR_BASIS'te.
    """
    mach_n = np.array([2.4, 1.6, 1.1, 0.8, 0.3])
    w, n_hat = _cikis_kolonu(mach_n)
    g = _outlet_state(w, n_hat, GIRIS_GAMMA, None,
                      subsonic_anchor=OUTLET_ANCHOR_CORE_PRESSURE)
    alt = mach_n < 1.0
    c_i = np.sqrt(GIRIS_GAMMA * w[..., 3] / w[..., 0])
    p_kenar = w[2, 3]
    dp = p_kenar - w[alt, 3]
    assert np.allclose(g[alt, 0], w[alt, 0] + dp / c_i[alt] ** 2,
                       rtol=0.0, atol=0.0)
    assert np.allclose(g[alt, 1],
                       w[alt, 1] - dp / (w[alt, 0] * c_i[alt]),
                       rtol=0.0, atol=0.0)
    assert np.allclose(g[alt, 2], w[alt, 2], rtol=0.0, atol=0.0), (
        'normal +z iken teğet bileşen değişmemeli')
    # Tutarlılığın ANLAMI: hayaletin entropisi iç durumunkine LİNEER
    # mertebede eşit kalır (yalnız p değiştirilseydi kalmazdı).
    s_i = w[alt, 3] / w[alt, 0] ** GIRIS_GAMMA
    s_b = g[alt, 3] / g[alt, 0] ** GIRIS_GAMMA
    s_yalniz_p = p_kenar / w[alt, 0] ** GIRIS_GAMMA
    assert np.all(np.abs(s_b / s_i - 1.0)
                  < np.abs(s_yalniz_p / s_i - 1.0)), (
        'karakteristik-tutarlı hayalet entropiyi daha az kaydırmalıydı')


def test_cikis_capasi_TAM_SES_ALTI_kolonda_uygulanmaz_ve_dusmez():
    """Hiç süpersonik hücre yoksa çapa değeri YOKTUR — uydurulmaz."""
    mach_n = np.array([0.9, 0.7, 0.5, 0.2])
    w, n_hat = _cikis_kolonu(mach_n)
    g = _outlet_state(w, n_hat, GIRIS_GAMMA, None,
                      subsonic_anchor=OUTLET_ANCHOR_CORE_PRESSURE)
    assert np.array_equal(g, w), (
        'çapasız kolonda hayalet dışdeğerleme olarak kalmalı')
    # ses-altı CEP (çekirdekte) — eksene doğru en yakın süpersonik komşu
    mach_c = np.array([2.0, 0.95, 1.5, 0.6])
    w2, n2 = _cikis_kolonu(mach_c)
    g2 = _outlet_state(w2, n2, GIRIS_GAMMA, None,
                       subsonic_anchor=OUTLET_ANCHOR_CORE_PRESSURE)
    assert g2[1, 3] == w2[0, 3], 'cep indis 0\'ın basıncını almalı'
    assert g2[3, 3] == w2[2, 3], 'duvar satırı indis 2\'nin basıncını almalı'
    assert np.array_equal(g2[0], w2[0]) and np.array_equal(g2[2], w2[2])


@pytest.mark.parametrize('anchor', OUTLET_ANCHOR_MODES)
def test_Pb_verildiginde_capa_kipi_sonucu_DEGISTIRMEZ(anchor):
    """Pb dalı (bugünkü kural) her iki kipte BİT-AYNI — kapsam beyanı."""
    mach_n = np.array([2.5, 1.6, 0.9, 0.4])
    w, n_hat = _cikis_kolonu(mach_n)
    pb = 5.0e4
    g = _outlet_state(w, n_hat, GIRIS_GAMMA, pb, subsonic_anchor=anchor)
    beklenen = np.array(w, copy=True)
    beklenen[mach_n < 1.0, 3] = pb
    assert np.array_equal(g, beklenen)


def test_bilinmeyen_capa_kipi_REDDEDILIR():
    w, n_hat = _cikis_kolonu([2.0, 0.5])
    with pytest.raises(ValueError, match=r'subsonic_anchor .* tanımsız'):
        _outlet_state(w, n_hat, GIRIS_GAMMA, None, subsonic_anchor='pb')
    with pytest.raises(ValueError, match=r'subsonic_anchor .* tanımsız'):
        _outlet_state(w, n_hat, GIRIS_GAMMA, 1e5, subsonic_anchor='')
    assert OUTLET_ANCHOR_MODES == ('extrapolate', 'core_pressure')


def test_kalinti_varsayilan_capayla_BIT_AYNI(giris_merdiveni):
    """residual_axisym'e argüman EKLENMESİ varsayılan sonucu değiştirmedi."""
    res = giris_merdiveni[GIRIS_CR_HIBRIT]
    grid = res['grid']
    U = prim_to_cons_axisym(
        res['res']['fields']['rho_kg_m3'], res['res']['fields']['u_z_m_s'],
        res['res']['fields']['u_r_m_s'], res['res']['fields']['pressure_Pa'],
        GIRIS_GAMMA)
    ortak = dict(Pb=GIRIS_PB, geom=precompute_geometry(grid))
    r0, _ = residual_axisym(U, grid, GIRIS_GAMMA, GIRIS_R, GIRIS_P0,
                            GIRIS_T0, **ortak)
    r1, _ = residual_axisym(U, grid, GIRIS_GAMMA, GIRIS_R, GIRIS_P0,
                            GIRIS_T0,
                            outlet_subsonic_anchor=OUTLET_ANCHOR_EXTRAPOLATE,
                            **ortak)
    assert np.array_equal(r0, r1)


def test_surucu_cikis_beyani_capa_kapaliyken_de_kusuru_GOSTERIR():
    """outlet_bc bloğu: kip, ses-altı hücre sayısı, çapasızlık uyarısı."""
    r_ch, l_conv = giris_kontur_parametreleri(GIRIS_CR_HIBRIT)
    z_nodes = np.linspace(0.0, l_conv + GIRIS_L_DIV, 61)
    grid = build_grid_from_wall(
        z_nodes, giris_duvar_yaricapi(z_nodes, r_ch, l_conv), 12)
    res = solve_steady_axisym(grid, GIRIS_P0, GIRIS_T0, GIRIS_GAMMA, GIRIS_R,
                              Pb=None, max_iters=400)
    ob = res['outlet_bc']
    assert ob['subsonic_anchor'] == OUTLET_ANCHOR_EXTRAPOLATE
    assert ob['Pb_Pa'] is None
    assert ob['cells_total'] == grid.nj
    assert 0 <= ob['subsonic_cells'] <= grid.nj
    assert ob['_basis'] == OUTLET_ANCHOR_BASIS
    for parca in ('Schlichting', 'Blazek', 'u_n − a', 'uydurma sabit',
                  'TAŞIYAMAZ'):
        assert parca in ob['_basis'], f'künye eksik: {parca}'
    # Kayma duvarlı Euler koşusunda sınır tabakası YOKTUR: çıkış kolonu
    # tam süpersoniktir, yani uyarı da olmamalı. (Uyarının ateşlediği
    # yer viskoz koşudur — bekçisi test_viskoz_entegrasyon.py'de.)
    assert ob['subsonic_cells'] == 0
    assert ob['unanchored_warning'] is None
    assert ob['anchored'] is False
    assert res['inputs']['outlet_subsonic_anchor'] == OUTLET_ANCHOR_EXTRAPOLATE


def test_surucu_bilinmeyen_capa_kipini_REDDEDER():
    r_ch, l_conv = giris_kontur_parametreleri(GIRIS_CR_HIBRIT)
    z_nodes = np.linspace(0.0, l_conv + GIRIS_L_DIV, 41)
    grid = build_grid_from_wall(
        z_nodes, giris_duvar_yaricapi(z_nodes, r_ch, l_conv), 8)
    with pytest.raises(ValueError, match=r'outlet_subsonic_anchor'):
        solve_steady_axisym(grid, GIRIS_P0, GIRIS_T0, GIRIS_GAMMA, GIRIS_R,
                            Pb=None, max_iters=10,
                            outlet_subsonic_anchor='core-pressure')
