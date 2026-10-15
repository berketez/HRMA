# tests/cfd — Back-Massier-Gier (1964) lüle doğrulaması (basamak 10-11)
"""BACK-MASSIER-GIER lülesi: deney doğrulaması, Bartz çaprazı, ANSYS üçlüsü.

Kaynak capa: ``data/validation/nozzle_back_massier_gier_1964.json`` (JPL
TR 32-415 Rev.1, NTRS 19650010083; parti 39 A2'nin elle çıkarımı — 32 tap
+ 22 tapa as-built istasyonu, 6 koşumun tam B-3 tablosu, tanımlar,
belirsizlik). ANSYS kulvarı: ``nozzle_ansys_published_wang_2021.json``
(Fluent 18.2 + SST, test 262, sayısallaştırılmış ±2 K).

Bu dosyanın HÜKMÜ (parti 39, A3 — ne ölçüldüyse o):

  HRMA'nın v3 CFD çekirdeği Back lülesinin GEOMETRİSİNİ ve BOĞULMUŞ
  DEBİSİNİ yeniden üretir; DUVAR ISI AKISI DOĞRULAMASI YAPILAMAMIŞTIR.
  Bu yüzden burada "deneyle doğrulandı" DENMİYOR. Ölçülen beş şey:
    1. GEOMETRİ + DEBİ kapanıyor: as-built kurgu tap tablosunu
       boğaz→çıkışta %0,30 içinde tutuyor; çözülen boğulmuş debi altı
       koşumun BEŞİNDE ölçülenle [0,989; 1,022] bandında ve bu bant
       DENEYİN kendi deşarj-katsayısı saçılmasıdır. Altıncı koşum
       (275) bağımsız olarak %5,3 dışarıda çıkıyor — A2'nin "275'in
       tablo debisi fiziksel değil" bulgusu çözücüden doğrulandı.
    2. Eksenel istasyonların Δα'ya göre dağıtılması (A4'ün §5b önerisi)
       bu konturda AR·Δα'yı 4,4-65 KAT düşürüyor — ÖLÇÜLDÜ, bedava.
    3. YENİ BULGU: koşuyu kıran büyüklük A1'in AR·Δα'sı DEĞİL, İLK
       HÜCRE KALINLIĞIDIR. Aynı d1'de iki farklı ni aynı davranışı
       veriyor (AR·Δα 5 kat farklı olmasına rağmen) ve A1'in "güvenli"
       bandının içindeki bir noktada koşu NaN'a gidiyor.
    4. Ulaşılabilen OTURAN bantta (y⁺ ≈ 27-42) q_w boğazda 2-3 kat
       EKSİK; eksiklik y⁺ ile sistematik kapanıyor → bu bir MODEL değil
       ÇÖZÜNÜRLÜK sonucudur (o bantta duvar-çözümlü SA zaten geçersiz).
       y⁺ ≈ 1 bu konturda ni ≈ 600-1200 ister (ÖLÇÜLDÜ).
    5. Bartz çaprazı, NEGATİF testler (266/288) ve ANSYS üçlüsü
       ÇÖZÜCÜSÜZ kapandı: tam-türbülanslı korelasyon negatif testleri
       pozitiflerden 1,63 kat DAHA FAZLA aşıyor (laminerleşmenin
       imzası); Wang/Fluent-SST deneyin −3,88 K'sinde, HRMA bugün
       −29,8 K ile 8 kat uzakta (ortak para birimi: eşlenik cidar).

Pahalı koşuların sayıları test docstring'lerindedir; canlı bekçiler
UCUZ ikizlerdir (depo üslubu: tests/cfd/test_viskoz_entegrasyon.py
"pahalı koşu burada beyanlıdır" deseni). Pahalı koşum betikleri parti 39
scratchpad'inde (``p39_a3_*.py``).

MUTASYONLAR (uygula → kırmızıyı ölç → TERS-DEĞİŞTİR; md5 birebir döndü)
dosyanın sonundaki blokta.
"""

import json
import os

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Capa dosyaları ve birim çevrimleri (TEK yer)
# ---------------------------------------------------------------------------

_KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BMG_JSON = os.path.join(_KOK, 'data', 'validation',
                        'nozzle_back_massier_gier_1964.json')
WANG_JSON = os.path.join(_KOK, 'data', 'validation',
                         'nozzle_ansys_published_wang_2021.json')

IN_TO_M = 0.0254
PSIA_TO_PA = 6894.757293168361
R_TO_K = 1.0 / 1.8
#: BTU/(s·in²) → W/m² (1 BTU = 1055,05585262 J; 1 in² = 6,4516e-4 m²)
QW_TO_SI = 1055.05585262 / 6.4516e-4
#: B-3'ün h kolonu (1e-4 BTU/(s·in²·°F)) → W/(m²·K); °F⁻¹ → K⁻¹ 9/5 katı
H_TO_SI = 1.0e-4 * QW_TO_SI * 1.8

#: Kuru hava özgül gaz sabiti [J/(kg·K)] (R_u/M, M = 28,9647 g/mol)
BACK_R_AIR = 287.05
#: γ — JSON gas_model.gamma_by_stagnation_temperature, T_t0 ≈ 1500 °R
#: (altı koşumun hepsi 1484-1518 °R; ara değerleme gerekmiyor)
BACK_GAMMA = 1.345


def _bmg():
    with open(BMG_JSON, encoding='utf-8') as f:
        return json.load(f)


def _wang():
    with open(WANG_JSON, encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# As-built kontur — JSON'daki YAYIMLANMIŞ parametrelerden, deterministik
# ---------------------------------------------------------------------------

def back_contour_in(conv_half_angle_deg=None, pipe_len_in=0.12, n=4000):
    """Back lülesinin iç konturu: (z_in, r_in, kilometre taşları).

    Parçalar (kaynağın kendi künyesi; hiçbir sayı UYDURULMADI):
        düz yaklaşım borusu (r = R) → giriş köşe yayı (r_i) → yakınsak
        koni (α) → boğaz yayı (r_c, iki tarafa teğet) → ıraksak koni (15°).
    Boğaz z/L = 0,603'e ÇAPALIDIR ve r* = √(A*/π).

    ``pipe_len_in`` düz borunun uzunluğudur; VARSAYILAN 0,12 in yalnız
    köşe yayının yatay teğet noktasını içeri alır (as-built 18 in boru
    bilerek DIŞARIDA — gerekçe ve ölçüm test_yaklasim_borusu_...
    docstring'inde).

    Returns:
        (z_in, r_in, kilometre) — kilometre: zc/za/z1/zt/z2/zL, rstar, L.
    """
    J = _bmg()
    G = J['inputs']['geometry']
    L = G['nozzle_axial_length_L_in']
    rstar = float(np.sqrt(G['throat_area_in2'] / np.pi))
    zt = G['throat_position_z_over_L'] * L
    rc = G['throat_curvature_radius_in']
    ri = G['inlet_corner_curvature_radius_in']
    rin = G['nozzle_inlet_radius_R_in']
    ad = np.radians(G['divergent_half_angle_deg'])
    a = np.radians(G['convergent_half_angle_deg']
                   if conv_half_angle_deg is None
                   else float(conv_half_angle_deg))

    z1 = zt - rc * np.sin(a)                    # koni ↔ boğaz yayı teğeti
    r1 = rstar + rc * (1.0 - np.cos(a))
    ra = rin - ri * (1.0 - np.cos(a))           # köşe yayı ↔ koni teğeti
    za = z1 - (ra - r1) / np.tan(a)
    zc = za - ri * np.sin(a)                    # köşe yayının yatay teğeti
    z2 = zt + rc * np.sin(ad)                   # boğaz yayı ↔ ıraksak koni
    r2 = rstar + rc * (1.0 - np.cos(ad))

    z = np.linspace(zc - float(pipe_len_in), L, int(n))
    z = np.unique(np.concatenate([z, [zc, za, z1, zt, z2, 0.0]]))
    z = z[z >= zc - float(pipe_len_in)]
    r = np.empty_like(z)
    for i, zi in enumerate(z):
        if zi <= zc:
            r[i] = rin
        elif zi <= za:
            r[i] = (rin - ri) + np.sqrt(max(ri ** 2 - (zi - zc) ** 2, 0.0))
        elif zi <= z1:
            r[i] = ra - (zi - za) * np.tan(a)
        elif zi <= z2:
            r[i] = rstar + rc - np.sqrt(max(rc ** 2 - (zi - zt) ** 2, 0.0))
        else:
            r[i] = r2 + (zi - z2) * np.tan(ad)
    return z, r, dict(zc=zc, za=za, z1=z1, zt=zt, z2=z2, zL=L,
                      rstar=rstar, L=L)


def back_axial_stations(z_dense, r_dense, ni, beta=0.0, lipschitz=0.15):
    """Δα-ağırlıklı eksenel düğümler — Lipschitz sınırlı boy alanı.

    ``beta = 0`` → DÜZGÜN dağılım, yani ``build_nozzle_grid``ın kendi
    ``np.linspace`` davranışıyla AYNI (bekçisi aşağıda). ``beta > 0``
    hedef hücre boyunu duvarın dönüşüyle küçültür:

        1/h(s) = (1−β)/S + β·|dα/ds|/Θ        (S: yay boyu, Θ: toplam dönüş)

    Boy alanı klasik Lipschitz süpürmesiyle sınırlanır (|dh/ds| ≤
    ``lipschitz``); sınırsız alan düz boru ile boğaz yayı arasında büyük
    bir atlama üretir ve kazancı yer.

    Bu bir IZGARA KODU DEĞİL, ızgaraya verilen GİRDİDİR: ``hrma/cfd``
    değişmez, ``build_grid_from_wall`` bu düğümleri aynen alır.
    """
    z_dense = np.asarray(z_dense, float)
    r_dense = np.asarray(r_dense, float)
    ni = int(ni)
    if beta <= 0.0:
        z_n = np.linspace(z_dense[0], z_dense[-1], ni + 1)
        return z_n, np.interp(z_n, z_dense, r_dense)
    ds = np.hypot(np.diff(z_dense), np.diff(r_dense))
    s = np.concatenate([[0.0], np.cumsum(ds)])
    alfa = np.arctan2(np.diff(r_dense), np.diff(z_dense))
    kappa = np.zeros_like(s)
    kappa[1:-1] = np.abs(np.diff(alfa)) / (0.5 * (ds[:-1] + ds[1:]))
    kappa[0], kappa[-1] = kappa[1], kappa[-2]
    donus = float(np.sum(np.abs(np.diff(alfa))))
    yog = (1.0 - beta) / s[-1] + beta * kappa / max(donus, 1e-300)
    h = 1.0 / (yog * ni)
    for _ in range(3):
        for i in range(1, len(h)):
            h[i] = min(h[i], h[i - 1] + lipschitz * ds[i - 1])
        for i in range(len(h) - 2, -1, -1):
            h[i] = min(h[i], h[i + 1] + lipschitz * ds[i])
    kum = np.concatenate([[0.0],
                          np.cumsum(0.5 * (1.0 / h[:-1] + 1.0 / h[1:]) * ds)])
    kum /= kum[-1]
    s_n = np.interp(np.linspace(0.0, 1.0, ni + 1), kum, s)
    z_n = np.interp(s_n, s, z_dense)
    z_n[0], z_n[-1] = z_dense[0], z_dense[-1]
    return z_n, np.interp(z_n, z_dense, r_dense)


def back_grid(ni, nj, *, beta, first_cell_m, pipe_len_in=0.12,
              conv_half_angle_deg=None, wall_collar=None, lipschitz=0.15):
    """(AxisymGrid, hücre merkezleri [in], kilometre, boğaz indisi)."""
    from hrma.cfd.grid_axisym import build_grid_from_wall

    zd, rd, km = back_contour_in(conv_half_angle_deg=conv_half_angle_deg,
                                 pipe_len_in=pipe_len_in)
    zz, rr = back_axial_stations(zd, rd, ni, beta=beta, lipschitz=lipschitz)
    grid = build_grid_from_wall(zz * IN_TO_M, rr * IN_TO_M, nj,
                                first_cell_m=first_cell_m, stretch='tanh',
                                wall_collar=wall_collar)
    zc = 0.5 * (zz[:-1] + zz[1:])
    return grid, zc, km, int(np.argmin(np.abs(zc - km['zt'])))


def back_grid_quality(ni, nj, *, beta, first_cell_m, **kw):
    """``steady.wall_grid_quality`` — Back ızgarası için (ÜRÜN ölçüsü)."""
    from hrma.cfd.euler_core import precompute_geometry
    from hrma.cfd.gradients import precompute_gradient_geometry
    from hrma.cfd.steady import wall_grid_quality

    grid, _zc, _km, it = back_grid(ni, nj, beta=beta,
                                   first_cell_m=first_cell_m, **kw)
    return wall_grid_quality(grid, precompute_geometry(grid),
                             precompute_gradient_geometry(grid),
                             throat_index=it)


# ---------------------------------------------------------------------------
# B-3 tabloları → SI
# ---------------------------------------------------------------------------

def b3_si(test):
    """B-3 satırları → SI diziler; '—' ve FLOW_SEPARATION ayrı imli."""
    J = _bmg()
    rows = J['expected_outputs']['heat_transfer_tables_B3'][f'test_{test}']
    cikti = {k: [] for k in ('z_over_L', 'q_w', 'T_w', 'T_e', 'h', 'St',
                             'rho_u', 'separated')}

    def _f(row, key, olcek):
        v = row[key]
        if v is None or isinstance(v, str):
            return float('nan')
        return float(v) * olcek

    for row in rows:
        cikti['separated'].append(
            any(v == 'FLOW_SEPARATION' for v in row.values()))
        cikti['z_over_L'].append(row['z_over_L'])
        cikti['q_w'].append(_f(row, 'q_w_btu_per_s_in2', QW_TO_SI))
        cikti['T_w'].append(_f(row, 'T_w_R', R_TO_K))
        cikti['T_e'].append(_f(row, 'T_e_R', R_TO_K))
        cikti['h'].append(_f(row, 'h_1e-4_btu_per_s_in2_F', H_TO_SI))
        cikti['St'].append(_f(row, 'St_1e-3', 1e-3))
        cikti['rho_u'].append(
            _f(row, 'rho_e_u_e_lb_per_s_in2', 0.45359237 / 6.4516e-4))
    return {k: np.asarray(v) for k, v in cikti.items()}


def back_test_conditions(test):
    J = _bmg()
    for t in J['inputs']['selected_test_conditions']:
        if int(t['test']) == int(test):
            return dict(test=int(test), P0=t['p_t_psia'] * PSIA_TO_PA,
                        T0=t['T_t0_R'] * R_TO_K,
                        mdot=t['mdot_lb_per_s'] * 0.45359237)
    raise KeyError(test)


def transport_air(T_ref_K, prandtl=None):
    """Hava taşınımı — μ Sutherland'dan, cp = γR/(γ−1) (viscous.py çaprazı).

    μ_ref Sutherland yasasıdır (White, *Viscous Fluid Flow* 3. baskı,
    Tablo 1-2: μ = 1,458e-6·T^1,5/(T+110,4) [Pa·s]); sıcaklık BAĞIMLILIĞI
    yine deponun kendi üs yasasıdır (ölçülen n = 0,6; Sutherland'ın 843 K
    civarındaki yerel üssü 0,6166, fark %2,8 — beyanlı).
    """
    from hrma.cfd.gas_transport import resolve_gas_transport

    T = float(T_ref_K)
    mu = 1.458e-6 * T ** 1.5 / (T + 110.4)
    return resolve_gas_transport(gamma=BACK_GAMMA, T_ref=T, gas_constant=BACK_R_AIR,
                                 mu_ref=mu, cp=BACK_GAMMA * BACK_R_AIR / (BACK_GAMMA - 1.0),
                                 prandtl=prandtl)


def bartz_h_g(test, z_over_L, T_wall_K, c_star=None, prandtl=None):
    """Depo Bartz korelasyonu — Back geometrisi/koşulları (basamak 11).

    Korelasyon ``hrma.analysis.heat_transfer_analysis`` içindeki TEK
    tanımdan çağrılır (ikinci gerçekleme YAZILMADI); Mach yine o modülün
    ``_mach_from_area_ratio`` çözücüsünden.
    """
    from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer

    J = _bmg()
    G = J['inputs']['geometry']
    c = back_test_conditions(test)
    tr = transport_air(c['T0'], prandtl=prandtl)
    an = HeatTransferAnalyzer()
    zd, rd, km = back_contour_in()
    z_in = np.asarray(z_over_L, float) * km['L']
    ar = (np.interp(z_in, zd, rd) / km['rstar']) ** 2       # A/A*
    mach = np.array([an._mach_from_area_ratio(float(a), BACK_GAMMA,
                                              supersonic=bool(z > km['zt']))
                     for a, z in zip(ar, z_in)])
    if c_star is None:
        us = (BACK_GAMMA + 1.0) / (2.0 * (BACK_GAMMA - 1.0))
        c_star = (np.sqrt(BACK_R_AIR * c['T0'] / BACK_GAMMA)
                  * ((BACK_GAMMA + 1.0) / 2.0) ** us)
    gaz = dict(gas_viscosity=tr.mu_ref, gas_cp=tr.cp, prandtl=tr.prandtl,
               gamma=BACK_GAMMA)
    h = np.array([an._bartz_coefficient(
        G['throat_diameter_in'] * IN_TO_M, c['P0'], float(c_star), gaz,
        c['T0'], float(tw),
        G['throat_curvature_radius_in'] / G['throat_diameter_in'],
        area_ratio_local=float(1.0 / a), mach_local=float(m))
        for a, m, tw in zip(ar, mach, np.asarray(T_wall_K, float))])
    return dict(h_g=h, mach=mach, area_ratio=ar, c_star=float(c_star))


def bartz_over_experiment(test):
    """Bartz / Back h ORANI (ayrılmamış, h'si olan istasyonlar)."""
    e = b3_si(test)
    ok = np.isfinite(e['h']) & (~e['separated'].astype(bool))
    b = bartz_h_g(test, e['z_over_L'][ok], e['T_w'][ok])
    return e['z_over_L'][ok], b['h_g'] / e['h'][ok]


# ---------------------------------------------------------------------------
# (a) GEOMETRİ — JSON'dan deterministik + as-built tabloya oturma
# ---------------------------------------------------------------------------

def test_back_konturu_JSONdan_deterministik():
    """Kontur YALNIZ JSON'daki yayımlanmış parametrelerden doğar.

    Kilometre taşları (in; iki kez çağrı BİT-AYNI olmalı):
        zc = −0,111027 (köşe yayının yatay teğeti — z = 0'ın MEMBAINDA,
        yani lüle girişi zaten yayın üstündedir), za = 0,598973,
        z1 = 2,672775, z_t = 3,572775, z2 = 4,038649, L = 5,925;
        r* = 0,901292 in (= √(A*/π); D*/2 = 0,9015 ile %0,023 uyum).
    Toplam duvar dönüşü TAM 75,0000° (30° + 45°) — kurgunun cebirsel
    kapanışının ölçüsü.
    """
    z1, r1, km1 = back_contour_in()
    z2, r2, km2 = back_contour_in()
    assert np.array_equal(z1, z2) and np.array_equal(r1, r2), (
        'kontur deterministik değil — aynı girdiden iki farklı çıktı')
    assert km1 == km2
    assert km1['zc'] == pytest.approx(-0.111027, abs=1e-6)
    assert km1['za'] == pytest.approx(0.598973, abs=1e-6)
    assert km1['z1'] == pytest.approx(2.672775, abs=1e-6)
    assert km1['zt'] == pytest.approx(3.572775, abs=1e-6)
    assert km1['z2'] == pytest.approx(4.038649, abs=1e-6)
    assert km1['rstar'] == pytest.approx(0.901292, abs=1e-6)
    G = _bmg()['inputs']['geometry']
    assert abs(km1['rstar'] / (0.5 * G['throat_diameter_in']) - 1.0) < 3.0e-4
    alfa = np.arctan2(np.diff(r1), np.diff(z1))
    donus = np.degrees(np.sum(np.abs(np.diff(alfa))))
    assert donus == pytest.approx(75.0, abs=1e-3), (
        f'toplam dönüş {donus}° — 30° + 45° kapanmıyor, kurgu bozuk')
    # Kontur monoton z, pozitif r, boğazda MİNİMUM
    assert np.all(np.diff(z1) > 0.0) and np.all(r1 > 0.0)
    i_min = int(np.argmin(r1))
    assert abs(z1[i_min] - km1['zt']) < 1e-3, (
        'yarıçap minimumu boğaz istasyonunda değil')


def test_back_konturu_as_built_tap_tablosuna_oturuyor():
    """Kurgu ↔ 32 tap + 22 tapa: ÖLÇÜLEN sapma bantları (A2 §3.6 ile aynı).

    Yarıçap sapması (kurgu − tap)/tap, ÖLÇÜLDÜ (2026-08-19):
        ıraksak (z/L > 0,62, n = 20): ort −0,030 %, bant [−0,302; +0,259] %
        boğaz   (0,47 ≤ z/L ≤ 0,62, n = 5): ort −0,263 %
        yakınsak (z/L < 0,47, n = 7): ort −1,588 %, bant [−2,735; −1,146] %
        tapalar (22): ort −0,707 %, bant [−2,111; +0,139] %
    ALAN cinsinden bunun iki katıdır (A ∝ r²): ıraksakta %0,06, yakınsakta
    %3,2. Yakınsak taraftaki eksiklik KAYNAĞIN KENDİ iç gerilimidir —
    metnin 30° yarım açısı ile tap tablosu birbirini tam tutmaz; taplara
    UYDURULAN yarım açı ÖLÇÜLDÜ: 31,1° (yakınsak RMS %1,712 → %0,490).
    Uydurma yapılmadı: yayımlanan 30° korundu ve sapma BEYAN edildi;
    ıraksak tarafın %0,3'ü (q_w tepesinin bulunduğu taraf) kurgunun
    doğruluğunun kanıtıdır. Çıkış yarıçapı bağımsız bir kaynakla da
    kapanıyor: kurgu 1,468071 in ↔ Wang 2021 Şekil 2 etiketi
    Φ74,62 mm/2 = 1,468898 in (%−0,056).
    """
    J = _bmg()
    G = J['inputs']['geometry']
    zd, rd, km = back_contour_in()
    L, rstar = km['L'], km['rstar']
    zt = np.array([t['z_over_L'] for t in G['pressure_tap_stations']]) * L
    rt = rstar * np.sqrt(np.array([t['A_over_Astar']
                                   for t in G['pressure_tap_stations']]))
    zp = np.array([p['z_over_L'] for p in G['thermocouple_plug_stations']]) * L
    rp = rstar * np.sqrt(np.array([p['A_over_Astar']
                                   for p in G['thermocouple_plug_stations']]))
    d = 100.0 * (np.interp(zt, zd, rd) - rt) / rt
    dp = 100.0 * (np.interp(zp, zd, rd) - rp) / rp
    ira = zt / L > 0.62
    kon = zt / L < 0.47
    assert ira.sum() == 20 and kon.sum() == 7
    assert abs(d[ira].mean()) < 0.10, f'ıraksak ort {d[ira].mean():+.3f}%'
    assert np.abs(d[ira]).max() < 0.35, f'ıraksak maks {np.abs(d[ira]).max():.3f}%'
    assert -1.75 < d[kon].mean() < -1.40, f'yakınsak ort {d[kon].mean():+.3f}%'
    assert np.abs(d[kon]).max() < 3.0
    assert np.abs(dp).max() < 2.5, f'tapa maks {np.abs(dp).max():.3f}%'
    r_cikis = float(np.interp(L, zd, rd))
    assert abs(r_cikis / (74.62 / 25.4 / 2.0) - 1.0) < 1.0e-3, (
        'çıkış yarıçapı Wang 2021 Şekil 2 etiketiyle kapanmıyor')


def test_taplara_uydurulan_yarim_aci_YAYIMLANANDAN_farkli():
    """Kaynağın 30°'si ile tap tablosunun ima ettiği açı AYNI DEĞİL.

    Bu bekçi bir kusuru değil, kaynağın iç gerilimini KİLİTLER: yakınsak
    koni taplarına en küçük kareler doğrusu uydurulduğunda yarım açı
    30,8627° çıkıyor (artık RMS 0,00905 in). Kurgu 30° ile kurulduğu için
    yakınsak sapma sistematiktir ve yukarıdaki bekçinin bandı odur.
    Birisi konturun yarım açısını "düzeltirse" bu bekçi onu görür.
    """
    J = _bmg()
    G = J['inputs']['geometry']
    L = G['nozzle_axial_length_L_in']
    rstar = float(np.sqrt(G['throat_area_in2'] / np.pi))
    zt = np.array([t['z_over_L'] for t in G['pressure_tap_stations']]) * L
    rt = rstar * np.sqrt(np.array([t['A_over_Astar']
                                   for t in G['pressure_tap_stations']]))
    m = (zt / L > 0.10) & (zt / L < 0.46)
    A = np.vstack([zt[m], np.ones(int(m.sum()))]).T
    sol, *_ = np.linalg.lstsq(A, rt[m], rcond=None)
    aci = np.degrees(np.arctan(-sol[0]))
    assert aci == pytest.approx(30.8627, abs=1e-3)
    assert G['convergent_half_angle_deg'] == 30.0
    artik = float(np.sqrt(np.mean((A @ sol - rt[m]) ** 2)))
    assert artik == pytest.approx(0.00905, abs=1e-4)


# ---------------------------------------------------------------------------
# (b) Δα-DUYARLI EKSENEL İSTASYON DAĞILIMI — A4 §5b'nin ürün karşılığı
# ---------------------------------------------------------------------------

def test_beta_sifir_build_nozzle_grid_ile_AYNI_dagilim():
    """β = 0 ürünün bugünkü davranışıdır (sessiz bir yenilik yok).

    ``build_nozzle_grid`` duvarı ``np.linspace`` ile DÜZGÜN örnekler;
    β = 0 dalı onunla BİT-AYNI düğüm üretmelidir. Δα-ağırlıklı dağılım
    ancak β > 0 ile devreye girer ve o bir GİRDİ kararıdır.
    """
    zd, rd, _km = back_contour_in()
    z_n, r_n = back_axial_stations(zd, rd, 64, beta=0.0)
    z_ref = np.linspace(zd[0], zd[-1], 65)
    r_ref = np.interp(z_ref, zd, rd)
    assert np.array_equal(z_n, z_ref)
    assert np.array_equal(r_n, r_ref)


def test_delta_alfa_dagitimi_AR_carpi_dalfayi_dusuruyor():
    """A4'ün §5b önerisi Back konturunda ÖLÇÜLDÜ: 4,4-6,5 kat (borusuz).

    ÖLÇÜLDÜ (M4 Max, 2026-08-19; ilk hücre 40 µm, tanh, yaka yok):

      boru   ni×nj    Δα(β=0)  Δα(β=,75)  AR·Δα(β=0)  AR·Δα(β=,75)  kazanç
      0,12"   96×24    2,9069°   1,2613°     2,6162      0,5989      4,37×
      0,12"  192×48    1,4648°   0,5609°     0,6765      0,1195      5,66×
      0,12"  384×64    0,7370°   0,2627°     0,1702      0,0262      6,51×
      18"     96×24   10,5102°   1,6112°    34,2539      1,0068     34,02×
      18"    192×48    5,4529°   0,6998°     8,8142      0,1795     49,11×
      18"    384×64    2,8285°   0,3335°     2,4916      0,0382     65,26×

    İKİ OKUMA. (1) Kazanç bedavadır — hücre EKLENMEZ, yalnız yer
    değiştirir. (2) Kazanç domenin düz kısmıyla büyür: 18 inçlik yaklaşım
    borusu düzgün dağılımda hücrelerin ~%75'ini yutuyor, Δα-ağırlıklı
    dağılım onları lüleye taşıyor (34-65×). A4'ün gerçek motor
    konturundaki 20,85× ölçümüyle aynı mertebe.
    AR·Δα ∝ Δz²/d1 olduğu için ni'yi iki katlamak metriği DÖRDE BİRE
    indirir; tablo bunu satır satır gösteriyor (0,6765 → 0,1702).
    """
    for ni, nj, bekle in ((96, 24, 4.37), (192, 48, 5.66), (384, 64, 6.51)):
        q0 = back_grid_quality(ni, nj, beta=0.0, first_cell_m=40e-6)
        q1 = back_grid_quality(ni, nj, beta=0.75, first_cell_m=40e-6)
        kazanc = (q0['max_aspect_x_angle_change']
                  / q1['max_aspect_x_angle_change'])
        assert kazanc == pytest.approx(bekle, rel=2e-3), (
            f'{ni}×{nj}: kazanç {kazanc:.3f}, ölçülen {bekle}')
        assert q1['max_wall_angle_change_deg'] < q0['max_wall_angle_change_deg']
    # ni iki katına → AR·Δα dörtte bire (Δz² yasası); ÖLÇÜLEN oran
    a = back_grid_quality(96, 24, beta=0.75,
                          first_cell_m=40e-6)['max_aspect_x_angle_change']
    b = back_grid_quality(192, 48, beta=0.75,
                          first_cell_m=40e-6)['max_aspect_x_angle_change']
    assert 4.5 < a / b < 5.5, f'ni yasası bozuldu: {a / b:.3f}'


def test_ar_dalfa_ilk_hucre_kalinligiyla_TERS_orantili():
    """AR·Δα ∝ 1/d1 — y⁺ hedefiyle kararlılık arasındaki takasın cebiri.

    ÖLÇÜLDÜ (192×48, β = 0,75, borusuz):
        d1 [µm]   160     80      40      20      10      5
        AR·Δα   0,0299  0,0598  0,1195  0,2390  0,4781  0,9562
    A1'in ölçtüğü DİNAMİK kararsızlık bandı 0,13-0,52 olduğuna göre bu
    ızgarada d1 ≈ 10 µm bandın ÜST ucundadır; 5 µm bandın dışındadır.
    Yani "y⁺ ≈ 1" (bu vakada d1 ≈ 0,9 µm) 192×48'de ULAŞILAMAZ ve
    ulaşmanın tek yolu ni'yi büyütmektir (ni² yasası).
    """
    onceki = None
    for d1_um, bekle in ((160., 0.0299), (80., 0.0598), (40., 0.1195),
                         (20., 0.2390), (10., 0.4781), (5., 0.9562)):
        q = back_grid_quality(192, 48, beta=0.75, first_cell_m=d1_um * 1e-6)
        v = q['max_aspect_x_angle_change']
        assert v == pytest.approx(bekle, rel=3e-3), f'd1={d1_um}: {v:.4f}'
        if onceki is not None:
            assert v / onceki == pytest.approx(2.0, rel=1e-2), (
                'AR·Δα ilk hücre kalınlığıyla ters orantılı değil')
        onceki = v


# ---------------------------------------------------------------------------
# (d) BARTZ ÇAPRAZI — basamak 11 (çözücüsüz, ÖLÇÜLEN band)
# ---------------------------------------------------------------------------

#: Bartz / Back h ORANI — ÖLÇÜLDÜ (2026-08-19; depo _bartz_coefficient,
#: hava taşınımı Sutherland μ + repo Pr, ideal c*, T_w B-3'ten).
#: Anahtar: test. Değer: (ortalama, min, maks, boğaz istasyonu).
BARTZ_BACK_ORANLARI = {
    288: (2.678, 1.384, 4.409, 3.642),
    266: (2.480, 1.171, 3.897, 3.714),
    262: (1.747, 1.331, 2.136, 1.718),
    268: (1.560, 1.224, 2.112, 1.986),
    278: (1.452, 1.094, 2.185, 2.053),
    275: (1.445, 1.106, 2.204, 2.034),
}


def test_bartz_back_bandi_OLCULDU_ve_kilitli():
    """Depo Bartz'ı Back ölçümünü AŞIYOR — bant ölçüldü, uydurulmadı.

    Bu bant BİR KEZ ölçülüp kilitlenmiştir; literatürün "boğazda ±%20-30"
    beklentisi BU vakada tutmuyor ve bu bir bulgudur, bir ayar değil:

      test  p_t[psia]  n   ort    min    maks   boğaz  yakınsak ıraksak
       288      30,1  10  2,678  1,384  4,409  3,642    1,914   4,176
       266      44,8  16  2,480  1,171  3,897  3,714    2,179   2,620
       262      75,2  20  1,747  1,331  2,136  1,718    1,756   1,742
       268     150,6  21  1,560  1,224  2,112  1,986    1,380   1,666
       278     250,7  21  1,452  1,094  2,185  2,053    1,272   1,534
       275     253,7  21  1,445  1,106  2,204  2,034    1,283   1,514

    Oran p_t ile MONOTON düşüyor: Bartz'ın aşırı tahmini düşük basınçta
    (düşük Re) büyüyor. Bu, kaynağın kendi ana bulgusudur — hızlanan
    akışta türbülanslı korelasyonlar ölçümün üstünde kalır — ve
    korelasyonun kendisi Bartz'ın (1957) kalibrasyon rejiminin DIŞINDA
    kullanıldığında ne olduğunu gösterir.

    Bantla ilgili İKİ ölçülmüş pay (uydurma düzeltme yapılmadı):
      - c* seçimi: ideal c* ↔ ölçülen debiden çıkan c* farkı %+1,02
        (262), %+1,43 (268), %−0,31 (278); h ∝ (P/c*)^0,8 olduğundan
        h'ye etkisi %1 sınıfı — bandın ~1,7'sini AÇIKLAMAZ.
      - Pr seçimi: depo zinciri Pr = 4γ/(9γ−5) = 0,7572 verir; havanın
        843 K'deki gerçek Pr'si ≈ 0,70. h ∝ Pr^−0,6 → %+4,6 pay.
    """
    for test, (ort, mn, mx, bgz) in BARTZ_BACK_ORANLARI.items():
        zl, oran = bartz_over_experiment(test)
        assert oran.mean() == pytest.approx(ort, rel=2e-3), (
            f'test {test}: Bartz/Back ort {oran.mean():.4f}, ölçülen {ort}')
        assert oran.min() == pytest.approx(mn, rel=3e-3)
        assert oran.max() == pytest.approx(mx, rel=3e-3)
        ib = int(np.argmin(np.abs(zl - 0.603)))
        assert oran[ib] == pytest.approx(bgz, rel=3e-3)
        assert np.all(oran > 1.0), (
            f'test {test}: Bartz bir istasyonda ölçümün ALTINA indi — '
            'bandın yönü değişti, hüküm cümlesi yeniden yazılmalı')
    # Basınçla monotonluk (275 = 278'in yinelemesi, dışarıda)
    p_sirali = [288, 266, 262, 268, 278]
    ortalar = [BARTZ_BACK_ORANLARI[t][0] for t in p_sirali]
    assert all(a > b for a, b in zip(ortalar, ortalar[1:])), (
        'Bartz aşırı tahmini basınçla monoton düşmüyor')


def test_bartz_korelasyonu_DEPODAN_cagriliyor():
    """İkinci bir Bartz gerçeklemesi YAZILMADI (CLAUDE.md kural 11).

    Bekçi yapısaldır: bu dosyada 0,026 katsayısı, 0,8/0,9/0,1/0,68/0,12
    üsleri ya da σ düzeltmesi GEÇMEZ; hepsi
    ``heat_transfer_analysis._bartz_coefficient`` içindedir. Bekçi
    Bartz'ın İMZA sabitlerini (0,026 önçarpanı ve σ'nın 0,68 üssü) arar;
    0,8/0,9/0,12 gibi sayılar başka bağlamlarda da geçtiği için ölçüt
    olamaz (ölçüldü: 0,12 bu dosyada boru uzunluğudur).
    """
    import ast
    import inspect

    from hrma.analysis import heat_transfer_analysis as hta

    kaynak = open(os.path.abspath(__file__), encoding='utf-8').read()
    agac = ast.parse(kaynak)
    # Bu bekçinin KENDİ gövdesi hariç (yasak listesi orada duruyor)
    govde = [d for d in ast.walk(agac)
             if isinstance(d, ast.FunctionDef)
             and d.name == 'test_bartz_korelasyonu_DEPODAN_cagriliyor']
    kendi = {id(n) for d in govde for n in ast.walk(d)}
    sayilar = {n.value for n in ast.walk(agac)
               if isinstance(n, ast.Constant) and isinstance(n.value, float)
               and id(n) not in kendi}
    for yasak in (0.026, 0.68):        # Bartz'ın İMZA sabitleri
        assert yasak not in sayilar, (
            f'Bartz sabiti {yasak} bu dosyada yeniden yazılmış — korelasyon '
            'TEK yerde durmalı')
    assert 'def _bartz_coefficient' in inspect.getsource(hta)


# ---------------------------------------------------------------------------
# (c) NEGATİF TESTLER (266 / 288) — tam-türbülanslı model TUTTURMAMALI
# ---------------------------------------------------------------------------

def test_negatif_testler_tam_turbulansli_korelasyonu_KIRIYOR():
    """266 ve 288 NEGATİF testtir: laminerleşme + ayrılma.

    A2'nin hükmü: tam-türbülanslı bir model bu iki koşumu TUTTURMAMALI.
    Bu bekçi o hükmü ÖLÇÜLEBİLİR hâle getirir ve ÇÖZÜCÜ GEREKTİRMEZ:
    tam-türbülanslı korelasyonun (Bartz) ölçüme uzaklığı negatif
    testlerde pozitiflerden belirgin biçimde BÜYÜK olmalıdır.

    ÖLÇÜLDÜ (2026-08-19):
        POZİTİF (262/268/278) ortalama oran 1,586 — bant 1,452-1,747
        NEGATİF (266/288)     ortalama oran 2,579 — bant 2,480-2,678
        negatif/pozitif = 1,626  ve iki küme HİÇ ÖRTÜŞMÜYOR
    Ayrıca kaynağın kendi imleri: 266'da 5, 288'de 9 istasyon
    FLOW_SEPARATION (z/L ≥ 0,825 ve ≥ 0,693).

    BU BEKÇİ YEŞİLDEN KIRMIZIYA DÖNERSE: tam-türbülanslı yol negatif
    testleri "tutturmaya" başlamış demektir — bu bir İYİLEŞME DEĞİL,
    modelin yanlış yerde kalibre edildiğinin işaretidir. O gün burada
    ölçülmesi gereken, laminerleşmenin GERÇEKTEN modellenip
    modellenmediğidir (SA'nın bu partide böyle bir kanadı YOK).
    """
    poz = [bartz_over_experiment(t)[1].mean() for t in (262, 268, 278)]
    neg = [bartz_over_experiment(t)[1].mean() for t in (266, 288)]
    assert min(neg) > max(poz) * 1.35, (
        f'negatif testler pozitiflerden ayrışmıyor: poz {poz}, neg {neg}')
    assert np.mean(neg) / np.mean(poz) == pytest.approx(1.626, rel=5e-3)
    for test, n_bekle, z_bekle in ((266, 5, 0.825), (288, 9, 0.693)):
        e = b3_si(test)
        sep = e['separated'].astype(bool)
        assert int(sep.sum()) == n_bekle
        assert e['z_over_L'][sep].min() == pytest.approx(z_bekle)
    # Ayrılma bölgesi Pb=None koşusunda ÇÖZÜLEMEZ: kaynak orada h vermiyor
    for test in (266, 288):
        e = b3_si(test)
        assert np.all(np.isnan(e['h'][e['separated'].astype(bool)])), (
            'ayrılma bölgesinde h karşılaştırılamaz (kaynak T_aw vermiyor)')


# ---------------------------------------------------------------------------
# (f) ANSYS ÜÇLÜ KARŞILAŞTIRMA — Back ↔ Wang(Fluent+SST) ↔ HRMA
# ---------------------------------------------------------------------------

def test_ansys_ucgeni_eslenik_cidarla_ORTAK_para_birimine_cevriliyor():
    """Wang'ın T_duvar hatası, yayımlanan cidarla q_w yüzdesine çevrilir.

    SORUN: Wang 2021 (Fluent 18.2 + SST, eşlenik) İÇ DUVAR SICAKLIĞINI
    kıyaslar; HRMA duvar sıcaklığını SINIR KOŞULU olarak DAYATIR ve
    q_w/h kıyaslar. İkisi doğrudan karşılaştırılamaz (JSON'un kendi
    uyarısı). ÇÖZÜM ölçülebilir bir çeviridir: yayımlanan eşlenik cidarda
    (t = 0,292 in = 7,4168 mm, k ≈ 27 W/(m·K) — Marineau ve ark. 2006)
    dış duvar sıcaklığı Dirichlet olduğu için

        T_iç − T_dış = q_w · t/k ,   t/k = 2,74696e-4 m²·K/W

    yani duvar sıcaklığındaki her ΔT, q_w'de ΔT·k/t kadar hataya karşılık
    gelir. ÖLÇÜLDÜ (test 262):
        deney tepesi   x = 90,75 mm, T_w = 462,78 K, q_w = 377 764 W/m²
        Wang tepesi    x = 84,60 mm, T   = 458,90 K
        Wang − deney   ΔT = −3,88 K, Δx = −6,15 mm
        eşlenik çeviri Δq_w = −14 117 W/m² = %−3,74
        istasyon bazlı (n = 21) ort ΔT = −2,73 K → q_w'de %−3,85;
        bant [−24,33; +37,66] K (uçlarda, tepe civarında değil)
    Tepede cidarın kendi sıcaklık düşümü q·t/k = 103,8 K — yani ölçülen
    T_iç'in %22'si cidarın içindedir; eşlenik kurulum bu yüzden şart.

    ÜÇLÜNÜN OKUNMA KURALI: "ANSYS ±%4 sınıfında" cümlesi bu çeviriyle
    kurulur; HRMA'nın kendi bandı q_w cinsinden ölçülür ve AYNI para
    biriminde yan yana konur (rapordaki tablo). VMFL044 kaydı
    NOT_DIGITIZED'dir — yalnız künye olarak anılır, sayı taşımaz.
    """
    J = _bmg()
    W = _wang()
    t_m = J['inputs']['geometry']['wall_thickness_in'] * IN_TO_M
    k_w = 27.0
    t_over_k = t_m / k_w
    assert t_over_k == pytest.approx(2.74696e-4, rel=1e-4)
    L_mm = J['inputs']['geometry']['nozzle_axial_length_L_in'] * IN_TO_M * 1e3
    e = b3_si(262)
    ok = np.isfinite(e['T_w'])
    x_exp = e['z_over_L'][ok] * L_mm
    T_exp = e['T_w'][ok]
    q_exp = e['q_w'][ok]
    i_pk = int(np.argmax(T_exp))
    assert x_exp[i_pk] == pytest.approx(90.75, abs=0.05)
    assert T_exp[i_pk] == pytest.approx(462.78, abs=0.05)
    pk = W['expected_outputs']['cfd_peak']
    dT = pk['T_K'] - T_exp[i_pk]
    assert dT == pytest.approx(-3.88, abs=0.05)
    assert pk['x_mm'] - x_exp[i_pk] == pytest.approx(-6.15, abs=0.05)
    dq_pct = 100.0 * (dT / t_over_k) / q_exp[i_pk]
    assert dq_pct == pytest.approx(-3.74, abs=0.05), (
        f'eşlenik çeviri kaydı: %{dq_pct:.2f}')
    # Cidarın kendi düşümü — eşlenik kurulumun neden şart olduğunun ölçüsü
    assert q_exp[i_pk] * t_over_k == pytest.approx(103.8, abs=0.2)
    # İstasyon bazlı bant
    cfd = W['expected_outputs']['cfd_inner_wall_temperature']
    xc = np.array([p['x_mm'] for p in cfd])
    Tc = np.array([p['T_K'] for p in cfd])
    m = (x_exp >= xc.min()) & (x_exp <= xc.max())
    d = np.interp(x_exp[m], xc, Tc) - T_exp[m]
    assert int(m.sum()) == 21
    assert d.mean() == pytest.approx(-2.73, abs=0.05)
    assert d.min() == pytest.approx(-24.33, abs=0.05)
    assert d.max() == pytest.approx(+37.66, abs=0.05)


def test_vmfl044_kaydi_SAYI_TASIMIYOR():
    """ANSYS'in resmi VMFL044 vakası yalnız künyedir — sayı çıkarılmadı."""
    yol = os.path.join(_KOK, 'data', 'validation',
                       'nozzle_ansys_published_ansys_vmfl044.json')
    with open(yol, encoding='utf-8') as f:
        V = json.load(f)
    metin = json.dumps(V, ensure_ascii=False)
    assert 'NOT_DIGITIZED' in metin, (
        'VMFL044 kaydı sayısallaştırılmış görünüyor — üçlü kıyasa '
        'sokulmadan önce kaynağı beyan edilmeli')


# ---------------------------------------------------------------------------
# (e) y⁺ ROZETİ — hedefin ULAŞILABİLİRLİĞİ ölçülüp beyan edilir
# ---------------------------------------------------------------------------

def test_y_plus_1_bu_izgarada_ULASILAMAZ_ve_gereken_ni_OLCULDU():
    """"y⁺ ≈ 1" bir dilek değil, ni'ye çevrilebilir bir maliyettir.

    Zincir tamamen ÜRÜN yollarından: ``steady.first_cell_for_y_plus``
    (entegral SL marşı) hedef kalınlığı verir, ``steady.wall_grid_quality``
    o ızgaranın AR·Δα'sını ölçer.

    ÖLÇÜLDÜ (test 262, β = 0,75, borusuz kontur; 192×48 ızgarasından
    okunan ön-tahmin — sürücü istasyon z = 3,394 in, boğazın hemen
    membaı):
        y⁺ hedefi     1      2      5     10     30
        d1 [µm]    0,959  1,919  4,797  9,593  28,78

    AR·Δα'nın ÖLÇÜLEN yasası (üç ızgarada doğrulandı):
        AR·Δα ≈ C/(ni²·d1),  C = 0,1763 m (192×48'de; 96×24'te 0,2208,
        384×64'te 0,1543 — C ni ile hafif düşüyor çünkü Lipschitz
        süpürmesi ince ızgarada daha az kesiyor).
    Buradan y⁺ = 1 için gereken ni DOĞRUDAN ÖLÇÜLDÜ (uydurma yok):
        ni = 640 → AR·Δα = 0,3730
        ni = 810 → AR·Δα = 0,2238
        ni = 1024 → AR·Δα = 0,1478
    A1'in dinamik bandı (0,13-0,52) baz alınırsa y⁺ ≈ 1 bu konturda
    **ni ≈ 600-1200** ister. Defterin "ni ~ 10³" hükmü bu vakada
    SAYISALLAŞTI. 192×48'de y⁺ = 1 istemek AR·Δα'yı 5,3'e çıkarır —
    ölçülen kararsızlık bandının on katı.
    """
    from hrma.cfd.steady import first_cell_for_y_plus

    c = back_test_conditions(262)
    tr = transport_air(c['T0'])
    grid, zc, km, _it = back_grid(192, 48, beta=0.75, first_cell_m=40e-6)
    e = b3_si(262)
    ok = np.isfinite(e['T_w'])
    zu, idx = np.unique(e['z_over_L'][ok], return_inverse=True)
    tu = np.array([e['T_w'][ok][idx == k].mean() for k in range(len(zu))])
    T_w = np.interp(np.asarray(zc) / km['L'], zu, tu)
    d1, beyan = first_cell_for_y_plus(grid, c['P0'], c['T0'], BACK_GAMMA,
                                      BACK_R_AIR, tr, T_w, y_plus_target=1.0)
    assert d1 * 1e6 == pytest.approx(0.9593, rel=2e-3), (
        f'y⁺=1 ön-tahmini {d1 * 1e6:.4f} µm')
    assert beyan['driving_station_z_m'] / IN_TO_M == pytest.approx(3.394,
                                                                   abs=0.01)
    # Hedef ni'ye çevriliyor: 192×48'de bu kalınlık bandın ON KATI
    q192 = back_grid_quality(192, 48, beta=0.75, first_cell_m=d1)
    assert q192['max_aspect_x_angle_change'] == pytest.approx(4.983,
                                                              rel=5e-3)
    # ...ve ancak ni ~ 10³ ile banda iniyor
    olculen = {}
    for ni in (640, 810, 1024):
        q = back_grid_quality(ni, 96, beta=0.75, first_cell_m=d1)
        olculen[ni] = q['max_aspect_x_angle_change']
    assert olculen[640] == pytest.approx(0.3730, rel=5e-3)
    assert olculen[810] == pytest.approx(0.2238, rel=5e-3)
    assert olculen[1024] == pytest.approx(0.1478, rel=5e-3)
    assert olculen[640] > olculen[810] > olculen[1024]


# ---------------------------------------------------------------------------
# (h) DEBİ ÇAPRAZI — Euler çözümü ↔ B-3 başlığındaki boğulmuş debi
# ---------------------------------------------------------------------------

#: Euler koşumunun debisi / B-3 başlığı — ÖLÇÜLDÜ (2026-08-19; β = 0,75,
#: borusuz kontur, ilk hücre 40 µm, Pb=None, 15000 iterasyon).
#: (96×24 oranı, 192×48 oranı, kaynağın kendi Cd'si)
BACK_DEBI_CAPRAZI = {
    288: (1.02159, 1.02239, 0.97369),
    266: (0.98924, 0.99002, 1.00553),
    262: (1.00481, 1.00560, 0.98995),
    268: (1.00893, 1.00972, 0.98591),
    278: (0.99159, 0.99237, 1.00315),
    275: (0.94733, 0.94807, 1.05001),
}


def test_debi_caprazi_275_ANOMALISINI_bagimsiz_dogruluyor():
    """Çözülen boğulmuş debi ↔ ölçülen debi — ve 275'in kaynağa içkin kusuru.

    ÖLÇÜLDÜ (Euler koşusu; viskoz yolun yakınsama sorunundan BAĞIMSIZ,
    çünkü boğulmuş debi Euler çözümünde belirlenir):

      test  ṁ_CFD/ṁ_deney (96×24)  (192×48)   kaynağın kendi Cd'si
       288       1,02159            1,02239        0,97369
       266       0,98924            0,99002        1,00553
       262       1,00481            1,00560        0,98995
       268       1,00893            1,00972        0,98591
       278       0,99159            0,99237        1,00315
      *275       0,94733            0,94807        1,05001  ← ANOMALİ

    CFD'nin deşarj katsayısı ÖLÇÜLDÜ ve testten teste SABİT: 0,99471
    (96×24) / 0,99549 (192×48) — boğulmuş debi P₀/√T₀ ile ölçeklendiği
    için bu beklenen davranıştır ve ızgarayla %0,08 oynuyor. Yani
    yukarıdaki oranların BÜTÜN saçılması DENEYİN kendi Cd saçılmasıdır.

    BEŞ TEMİZ KOŞUMDA oran bandı [0,9892; 1,0224] — kaynağın kendi
    Cd bandıyla (0,974-1,006) aynı genişlikte. **275 tek başına %5,3
    dışarıda**: A2'nin "275 başlığındaki ṁ fiziksel değil (Cd = 1,05)"
    bulgusu BAĞIMSIZ BİR YOLDAN (çözücüden) doğrulanıyor. A2'nin hükmü
    (debi çaprazını 278'den kur) bu bekçiyle kilitli.
    """
    temiz = [t for t in BACK_DEBI_CAPRAZI if t != 275]
    oranlar = [BACK_DEBI_CAPRAZI[t][1] for t in temiz]
    assert min(oranlar) > 0.985 and max(oranlar) < 1.025, (
        f'temiz koşumların debi bandı kaydı: {oranlar}')
    assert BACK_DEBI_CAPRAZI[275][1] < 0.96, (
        '275 artık anomali değil — kaynağın dizgi şüphesi çözülmüş '
        'olabilir, A2 kaydı gözden geçirilmeli')
    # Kaynağın kendi Cd'siyle bizim oranımız TERS orantılı olmalı:
    # ṁ_CFD sabit Cd ile kurulduğu için oran = Cd_CFD/Cd_deney.
    for t, (o96, o192, cd) in BACK_DEBI_CAPRAZI.items():
        assert o192 * cd == pytest.approx(0.99549, rel=2e-3), (
            f'test {t}: oran × Cd_deney = {o192 * cd:.5f}; CFD Cd sabit '
            'olmalıydı — kurgu ya da gaz modeli testten teste kaymış')
        assert o192 / o96 == pytest.approx(1.00078, rel=2e-5)


# ---------------------------------------------------------------------------
# (g) İKİ TOPOLOJİ — ayrıklaştırma bandı (A4'ün devir notu)
# ---------------------------------------------------------------------------

def test_iki_topoloji_ayriklastirma_bandi_OLCULDU():
    """H-ızgara ↔ duvar-normal yaka: q_w bandı ölçüldü (A4'ün reçetesi).

    A4'ün devir notu: "Back hükmü İKİ topolojide koşulup fark
    AYRIKLAŞTIRMA BANDI olarak beyan edilsin." Yapıldı (test 262,
    192×48, β = 0,75, ilk hücre 40 µm, SA açık, 1200 iterasyon):

        büyüklük            H-ızgara      yaka (varsayılan 4/24)
        duvar çarpıklığı     30,000°        0,099°
        AR·Δα                0,1195         0,1042
        y⁺ maks             27,76          27,82
        ṁ [kg/s]             1,167166       1,167404   (%+0,020)
        q_w(boğaz) [W/m²]  225 450        223 183     (%−1,01)
        ∮q_w dA [W]         10 248,6       10 099,3    (%−1,46)
        kalıntı @1200       1,017e+00      9,767e−01

    İSTASYON BAZLI BANT: ort %−2,24, bant [%−4,70; %+6,65].
    A4'ün gerçek motor konturunda ölçtüğü ±%4,7 bandıyla aynı mertebe —
    yani bu bant konturun değil ŞEMANIN bandıdır.

    OKUMA KURALI: bu bant, aşağıdaki y⁺ merdiveninin ürettiği 2-3 KAT'lık
    oynamanın yanında İKİNCİ MERTEBEDİR. Ayrıklaştırma belirsizliğinin
    baskın kaynağı topoloji değil DUVAR ÇÖZÜNÜRLÜĞÜDÜR ve rapor bunu
    böyle sıralar.
    """
    from hrma.cfd.grid_axisym import WallCollar

    q_h = back_grid_quality(192, 48, beta=0.75, first_cell_m=40e-6)
    q_c = back_grid_quality(192, 48, beta=0.75, first_cell_m=40e-6,
                            wall_collar=WallCollar())
    assert q_h['max_wall_skew_deg'] == pytest.approx(30.0, abs=1e-3)
    assert q_c['max_wall_skew_deg'] < 0.15, (
        f'yaka çarpıklığı düşürmedi: {q_c["max_wall_skew_deg"]:.3f}°')
    assert q_h['max_aspect_x_angle_change'] == pytest.approx(0.1195, rel=3e-3)
    assert q_c['max_aspect_x_angle_change'] == pytest.approx(0.1042, rel=3e-3)
    # Δα KONTUR büyüklüğüdür: yaka onu DEĞİŞTİRMEZ (A4'ün negatif iddiası)
    assert (q_c['max_wall_angle_change_deg']
            == pytest.approx(q_h['max_wall_angle_change_deg'], rel=1e-12)), (
        'yaka Δα\'yı değiştirdi — duvar düğümleri kaymış olmalı')


# ---------------------------------------------------------------------------
# (i) HÜKÜM — Back türbülanslı koşusu BUGÜN YAKINSAMIYOR; kırılma İLK HÜCRE
#     KALINLIĞIYLA sıralanıyor (A1'in AR·Δα metriğiyle DEĞİL)
# ---------------------------------------------------------------------------

def back_kosum(ni, nj, d1_um, *, test=262, sa=True, visc_iters=500,
               euler_iters=4000, U0=None, T_wall=None):
    """Back koşusu (Euler ön koşu + viskoz/SA) — bekçilerin UCUZ ikizi."""
    from hrma.cfd.euler_core import prim_to_cons_axisym
    from hrma.cfd.steady import ViscousOptions, solve_steady_axisym

    c = back_test_conditions(test)
    tr = transport_air(c['T0'])
    grid, zc, km, _it = back_grid(ni, nj, beta=0.75,
                                  first_cell_m=d1_um * 1e-6)
    if T_wall is None:
        e = b3_si(test)
        ok = np.isfinite(e['T_w'])
        zu, idx = np.unique(e['z_over_L'][ok], return_inverse=True)
        tu = np.array([e['T_w'][ok][idx == k].mean() for k in range(len(zu))])
        T_wall = np.interp(np.asarray(zc) / km['L'], zu, tu)
    if U0 is None:
        eu = solve_steady_axisym(grid, c['P0'], c['T0'], BACK_GAMMA,
                                 BACK_R_AIR, Pb=None, max_iters=euler_iters,
                                 tol_res=1e-5, settle_tol=1e-8)
        f = eu['fields']
        U0 = prim_to_cons_axisym(f['rho_kg_m3'], f['u_z_m_s'], f['u_r_m_s'],
                                 f['pressure_Pa'], BACK_GAMMA)
    v = ViscousOptions(
        transport=tr, wall_thermal='isothermal', T_wall=T_wall,
        T_wall_source=('Back-Massier-Gier 1964 Tablo B-3 T_w kolonu '
                       '(z/L ile interpolasyon)'),
        turbulence='sa_neg' if sa else 'none')
    r = solve_steady_axisym(grid, c['P0'], c['T0'], BACK_GAMMA, BACK_R_AIR,
                            Pb=None, viscous=v, initial_state=U0,
                            time_integrator='line_implicit_j',
                            max_iters=visc_iters, tol_res=1e-8,
                            settle_tol=1e-4, y_plus_target=1.0)
    return r, U0, T_wall


def test_KIRILMA_ilk_hucre_kalinligiyla_siralaniyor_ni_ILE_DEGIL():
    """PARTİ 39'UN YENİ BULGUSU — canlı, küçültülmüş vaka.

    A1 (parti 39) türbülanslı KAPI ıraksamasını AR·Δα ile sıralamış ve
    dinamik bandı 0,13-0,52 ölçmüştü. Back vakasında bu metrik SIRALAMIYOR;
    sıralayan büyüklük İLK HÜCRE KALINLIĞIDIR (dolayısıyla y⁺).

    ÖLÇÜLDÜ (M4 Max, 2026-08-19; test 262, β = 0,75, borusuz kontur, SA
    açık, sıcak Euler başlangıcı, satır-örtük yol, 1200 iterasyon tavanı):

      ni×nj    d1[µm]  AR·Δα   y⁺maks  sonuç
      192×48     80    0,0598   41,9   kalıntı 1,17e−02, YAŞIYOR
      192×48     40    0,1195   27,8   kalıntı 1,02e+00, BÜYÜYOR
      192×48     20    0,2390   18,2   **539. it IRAKSADI (NaN)**
      192×48     10    0,4781   12,9   **266. it IRAKSADI (NaN)**
       96×24     80    0,2994   41,3   kalıntı 3,24e−03, YAŞIYOR (5000 it)
       96×24     40    0,5989   27,5   kalıntı 9,79e−01, BÜYÜYOR

    İKİ OKUMA. (1) AYNI d1'de iki farklı ni AYNI davranışı veriyor
    (80 µm → ikisi de yaşıyor; 40 µm → ikisi de büyüyor) hâlbuki AR·Δα
    aralarında 5 kat farklı (0,0598 ↔ 0,2994). (2) AR·Δα = 0,2390
    A1'in "güvenli" bandının İÇİNDE ve orada koşu NaN'a gidiyor, buna
    karşılık AR·Δα = 0,2994 aynı bandın içinde ve orada koşu oturuyor.
    Metrik bu vakayı AÇIKLAMIYOR — sıralayan d1'dir.

    LAMİNER KONTROL: aynı ızgarada (192×48, 40 µm) SA KAPALI koşu 464.
    iterasyonda IRAKSIYOR, SA AÇIK koşu 1200 iterasyon yaşıyor. Yani
    kararsızlık SA'dan DEĞİL; μ_t onu GECİKTİRİYOR. (A1'in vakasında
    ilişki tersineydi — o vakada SA kapalı 240, açık 529'du; iki vakanın
    ortak yanı "sebep SA değil" hükmüdür.)

    CANLI İKİZ (bu bekçi): 48×12 ızgarada 500 iterasyon, iki uç d1.
    ÖLÇÜLDÜ — kalıntının BÜYÜME ÇARPANI (son/ilk):
        d1 = 160 µm (y⁺ 61,2) → 0,04×   (iniyor)
        d1 =  80 µm (y⁺ 41,9) → 0,20×   (iniyor)
        d1 =  40 µm (y⁺ 27,8) → 2,17×   (çıkıyor)
        d1 =  20 µm (y⁺ 18,4) → 30,2×   (çıkıyor)
    Sıralama monotondur ve ni'den bağımsızdır.

    BU BEKÇİ KIRMIZIYA DÖNERSE: ya kararsızlık giderilmiştir (o zaman
    Back doğrulaması yeniden koşulmalı ve buradaki HÜKÜM CÜMLESİ
    değiştirilmelidir) ya da sıralama bozulmuştur (o zaman yeni sürücü
    büyüklük ölçülmelidir). İki durumda da bu dosyanın hükmü yeniden
    yazılır — bekçi tam olarak bunun için var.
    """
    r_kaba, U0, T_w = back_kosum(48, 12, 160.0, visc_iters=500)
    h_kaba = np.asarray(r_kaba['residual_history'])
    # NOT: Euler ön koşusu HER ızgara için AYRI koşulur. Aynı U0'ı iki
    # ızgarada kullanmak fiziksel olarak yanlıştır (radyal hücre merkezleri
    # kayar) ve ölçülen büyüme çarpanlarını bozar (ölçüldü: 0,376/6,90
    # yerine 0,04/30,2).
    del U0, T_w
    r_ince, _U0, _T = back_kosum(48, 12, 20.0, visc_iters=500)
    h_ince = np.asarray(r_ince['residual_history'])
    buyume_kaba = float(h_kaba[-1] / h_kaba[0])
    buyume_ince = float(h_ince[-1] / h_ince[0])
    assert buyume_kaba < 0.5, (
        f'kaba duvar hücresi (160 µm) artık İNMİYOR: {buyume_kaba:.3f}× — '
        'kararsızlık kayması ölçülmeli')
    assert buyume_ince > 5.0, (
        f'ince duvar hücresi (20 µm) artık BÜYÜMÜYOR: {buyume_ince:.3f}× — '
        'kararsızlık giderilmiş olabilir, HÜKÜM CÜMLESİ yeniden yazılmalı')
    assert buyume_ince / buyume_kaba > 50.0
    # Sıralamanın AR·Δα'ya AİT OLMADIĞININ yapısal ölçüsü: ince koşu
    # metriği DAHA BÜYÜK ama aynı metrik değeri 96×24'te oturuyordu.
    q_kaba = back_grid_quality(48, 12, beta=0.75, first_cell_m=160e-6)
    q_ince = back_grid_quality(48, 12, beta=0.75, first_cell_m=20e-6)
    assert q_kaba['max_aspect_x_angle_change'] == pytest.approx(0.7929,
                                                                rel=5e-3)
    assert q_ince['max_aspect_x_angle_change'] == pytest.approx(6.3430,
                                                                rel=5e-3)
    # ...ve HER İKİSİ de A1'in 0,13-0,52 bandının ÜSTÜNDE olmasına rağmen
    # kaba olan oturuyor: bant tek başına hüküm veremiyor.
    assert q_kaba['max_aspect_x_angle_change'] > 0.52
    # Hüküm beyanı sessiz değil: ıraksama/oturmama gerekçesi yayımlanıyor
    for r in (r_kaba, r_ince):
        assert r['converged'] is False
        assert r['convergence_basis']
        assert r['viscous']['y_plus_loop']['target'] == 1.0
        assert np.isfinite(r['viscous']['y_plus_loop']['achieved_max'])


# ---------------------------------------------------------------------------
# (j) h_g'nin DUVAR SICAKLIĞINA duyarlılık bandı — LÜLEDE (defter satır 224)
# ---------------------------------------------------------------------------

def test_h_g_duyarlilik_olcumu_URUN_yolundan_ve_sozlesmeli():
    """§5.4'ün ölçüm yolu (``viscous.h_g_wall_temp_sensitivity``) sözleşmeli.

    Parti 37'de bu bant BORUDA ölçülmüştü ve orada duvar sıcaklığı DEBİYİ
    de değiştirdiği için karışıyordu. LÜLEDE o karışma YOK: akış
    boğulmuştur, debi duvar sıcaklığından bağımsızdır (ölçüldü: T_w =
    0,42·T₀ ↔ 0,55·T₀ koşumlarında ṁ farkı yalnız %0,09).

    LÜLE ÖLÇÜMÜ (pahalı koşu — 96×24, β = 0,75, ilk hücre 80 µm, SA açık,
    5000 iterasyon; kalıntı 3,27e−03 ↔ 3,19e−03, ikisi de OTURAN bantta;
    y⁺ maks 47,6 ↔ 38,5; T_w = 354,2 K ve 463,8 K, yani kaynağın kendi
    T_w/T_t₀ aralığı 0,421-0,547'nin uçları):
        BOĞAZ istasyonunda bağıl bant   0,0663
            (h_g 381,77 → 357,28 W/(m²·K), oran 0,9359)
        lüle içi (z/L 0,10-0,95, n=69) ortalama  0,1410
        lüle içi maksimum  0,5190  (z/L = 0,686)
        lüle içi minimum   0,0017
    Yani termal FEA köprüsünün doğrusallaştırması BOĞAZDA %6,6 bandıyla
    geçerli; ıraksak bölgede bant %52'ye açılıyor. UYARI: bu bant y⁺ ≈
    38-48 ızgarasında ölçüldü ve o bantta q_w'nin kendisi eksiktir
    (yukarıdaki merdiven); bandın duvar çözünürlüğüyle nasıl daraldığı
    ÖLÇÜLMEDİ ve kararsızlık giderildiğinde YENİDEN ölçülmelidir.

    Bu bekçi UCUZDUR ve iki şeyi tutar: (1) ölçüm ürünün TEK
    işlevinden geçer, (2) sözleşme kapıları canlıdır — T_aw ≤ T_w olan
    bir istasyon varsa sessiz NaN yerine ValueError gelir, oran bandı
    (0,1) dışındaysa reddedilir.
    """
    import types

    from hrma.cfd.viscous import (WALL_TEMP_SENSITIVITY_RATIOS,
                                  h_g_wall_temp_sensitivity)

    T0 = 843.3333333333334
    z = np.linspace(0.0, 0.15, 12)

    def sahte(T_w):
        # q_w ∝ (T_aw − T_w) alınırsa h_g TAM sabit olur: bandın SIFIR
        # çıkması gerektiği bilinen bir durum (ölçüm yolunun kalibrasyonu).
        T_aw = 0.9 * T0 * np.ones_like(z)
        return types.SimpleNamespace(
            q_wall_W_m2=1234.0 * (T_aw - T_w), z_m=z,
            T_wall_K=np.full_like(z, T_w))

    s = h_g_wall_temp_sensitivity(sahte, T0, recovery_temperature_K=0.9 * T0,
                                  ratios=(0.42, 0.55))
    assert s['max_relative_band'] < 1e-12, (
        'ölçüm yolu sabit h_g\'de sıfır olmayan bant üretti')
    assert s['wall_temperature_ratios'] == (0.42, 0.55)
    assert WALL_TEMP_SENSITIVITY_RATIOS == (0.30, 0.60)
    # Sözleşme: T_aw ≤ T_w → sessiz NaN DEĞİL, hata
    with pytest.raises(ValueError):
        h_g_wall_temp_sensitivity(sahte, T0, recovery_temperature_K=0.3 * T0,
                                  ratios=(0.42, 0.55))
    with pytest.raises(ValueError):
        h_g_wall_temp_sensitivity(sahte, T0, recovery_temperature_K=0.9 * T0,
                                  ratios=(0.42, 1.20))
    # Kaynaktaki T_w/T_t₀ aralığı gerçekten (0,42; 0,55) bandındadır
    e = b3_si(262)
    ok = np.isfinite(e['T_w'])
    assert 0.42 < e['T_w'][ok].min() / T0 < 0.44
    assert 0.53 < e['T_w'][ok].max() / T0 < 0.56
