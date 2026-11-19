"""3.0.7 K1 — tamamlanmış eşdeğer mekanik model (CALKANTI §A.1, §C-d).

Kilitlenen şey FİZİKTİR, bugünkü çıktı değil:
- betik v1 sayıları (``docs/tasarim/v307/betik/v1_silindir_esdeger_model
  .out.txt``), 6 basamak;
- SP-8009 Tablo I ⟷ Dodge 2000 Tablo 3.2 kütle konumu eşitliği (10⁻¹²);
- modal integral çıkarımı (A-8), (A-9), (A-10) ⟷ kapalı biçim;
- çeper basıncı integrali (60 mod) ⟷ yay-kütle modelinin momenti (≤ 10⁻⁶);
- doluluk uçları, I0 (SP-106 Tablo 6.1), düz çeper sönümü (Dodge (2.7a),
  errata madde 9) ⟷ Mikishev (2.6a);
- silindir tablo üreticisi (sözleşme), tek büyüklük tek sayı, g_eff
  haritası, Bond ve kubbe kapıları.
"""

import math

import numpy as np
import pytest
from scipy import integrate, special

from hrma.analysis import slosh_analysis as sa
from hrma.analysis import slosh_tablo as st
from hrma.constants import G_0

XI = special.jnp_zeros(1, 60)


# ------------------------------------------------------------ kökler ---
def test_kokler_kesin_ve_dodge_141_ile_tutarli():
    assert sa.SLOSH_ROOTS == tuple(float(x) for x in XI[:4])
    assert sa.LAMBDA_1 == sa.SLOSH_ROOTS[0]
    for kod, dodge in zip(sa.SLOSH_ROOTS, (1.841, 5.331, 8.536)):
        assert abs(kod - dodge) < 5e-4          # Dodge (1.41), 3 ondalık
    for x in sa.SLOSH_ROOTS:
        assert abs(special.jvp(1, x)) < 1e-12


# ----------------------------------------------- betik v1 sayıları (§C-d) ---
def test_urun_ornegi_betik_v1_alti_basamak():
    """R = 0,5 m, h = 1,0 m, su, g0 (betik v1 §2; CALKANTI §A.1.1)."""
    m = sa.CylindricalTankSlosh(0.5, 1.0, fluid_density=1000.0)
    e = m.esdeger_model()
    assert round(m.natural_frequency(1)[1], 6) == 0.955804
    assert round(e['f1_hz'], 6) == 0.955804
    assert round(e['m1_oran'], 6) == 0.226967
    assert round(e['m1_kg'], 4) == 178.2594
    assert round(m.liquid_mass, 4) == 785.3982
    assert round(e['L1_m'], 6) == 0.271909
    assert round(e['z_aski_m'] - e['z_km_m'], 6) == 0.255443
    assert round(e['z1_m'] - e['z_km_m'], 6) == -0.016466
    assert round(e['z0_m'] - e['z_km_m'], 6) == 0.004834


@pytest.mark.parametrize('hR, k1R, m1, L1R, derin', [
    (0.1, 0.33522, 0.82751, 2.98315, 0.09972),
    (0.5, 1.33703, 0.66011, 0.74793, 0.46744),
    (1.0, 1.75080, 0.43220, 0.57117, 0.78882),
    (2.0, 1.83885, 0.22697, 0.54382, 1.03293),
    (5.0, 1.84118, 0.09090, 0.54313, 1.08604),
])
def test_doluluk_taramasi_betik_v1(hR, k1R, m1, L1R, derin):
    """CALKANTI §C-d tablosu (R = 1): κ1R, m1/m, L1/R, kütle derinliği/R."""
    e = sa.silindir_esdeger_model(1.0, hR)
    assert round(e['kappa1_1m'], 5) == k1R
    assert round(e['m1_oran'], 5) == m1
    assert round(e['L1_m'], 5) == L1R
    assert round(hR - e['z1_m'], 5) == derin


def test_doluluk_uclari():
    """h → 0: m1/m → 2/(ξ1²−1); h → ∞: L1/R → 1/ξ1, kütle derinliği → 2/ξ1."""
    x = sa.LAMBDA_1
    sig = sa.silindir_esdeger_model(1.0, 1e-3)
    assert round(sig['m1_oran'], 6) == 0.836834
    assert sig['m1_oran'] < 2.0 / (x * x - 1.0)
    assert round(sig['L1_m'], 3) == 294.989
    assert 0.0 < sig['z1_m'] < 1e-3            # kütle tabana iner
    derin = sa.silindir_esdeger_model(1.0, 50.0)
    assert round(derin['L1_m'], 6) == 0.543129
    assert round(50.0 - derin['z1_m'], 6) == round(2.0 / x, 6) == 1.086258
    assert round(derin['z_aski_m'], 6) == round(50.0 - 1.0 / x, 6)
    assert round(derin['Gamma1'], 4) == 0.6490   # Dodge (2.15) Γ = 0,649


# ------------------------------------- SP-8009 Tablo I ⟷ Dodge Tablo 3.2 ---
def test_sp8009_tablo1_dodge_tablo32_esit():
    """z1 (SP-8009: serbest yüzeyden derinlik (2R/ξ) tanh(ξh/2R)) ile Dodge
    Tablo 3.2'nin askı − L1'i (errata madde 28) aynı nokta; m1 için
    SP-8009 0,4547 = 2/(ξ(ξ²−1)) ile Dodge (d = 2R) aynı ifade."""
    x = sa.LAMBDA_1
    R = 0.7
    en_buyuk = 0.0
    for hR in np.linspace(0.05, 8.0, 400):
        h = hR * R
        d = 2.0 * R
        e = sa.silindir_esdeger_model(R, h)
        askı_km = h / 2 - d / (2 * x) * (math.tanh(x * h / d)
                                         - 1.0 / math.sinh(2 * x * h / d))
        L1 = d / (2 * x * math.tanh(2 * x * h / d))
        z1_dodge = h / 2 + askı_km - L1
        z1_sp8009 = h - (2 * R / x) * math.tanh(x * h / (2 * R))
        en_buyuk = max(en_buyuk, abs(e['z1_m'] - z1_dodge) / R,
                       abs(e['z1_m'] - z1_sp8009) / R)
        m1_dodge = d * math.tanh(2 * x * h / d) / (x * (x * x - 1) * h)
        m1_sp8009 = (2.0 / (x * (x * x - 1))) * (R / h) * math.tanh(x * h / R)
        assert abs(e['m1_oran'] - m1_dodge) <= 1e-12
        assert abs(e['m1_oran'] - m1_sp8009) <= 1e-12
        assert abs(e['L1_m'] - L1) <= 1e-12 * R
    assert en_buyuk <= 1e-12


# ------------------------------------------ modal integral çıkarımı (A-7..10) ---
@pytest.mark.parametrize('hR', [0.3, 1.0, 2.0])
def test_modal_integral_cikarimi_kapali_bicimi_verir(hR):
    """Analitik silindir modu Φ = J1(kr) cosh(k(z+h))/cosh(kh) (z serbest
    yüzeyden, yukarı +) ile (A-8) m1 = ρκP²/N, (A-9) z1 − z_yüzey =
    G/(κP), (A-10) Γ1 = N/(κ P Φ(R, 0)) — meridyen integralleri sayısal."""
    R = 0.5
    h = hR * R
    k = sa.LAMBDA_1 / R
    kappa = k * math.tanh(k * h)

    def Phi(r, z):
        return special.j1(k * r) * math.cosh(k * (z + h)) / math.cosh(k * h)

    def Phi_r(r, z):
        return k * special.jvp(1, k * r) * math.cosh(k * (z + h)) / math.cosh(k * h)

    def Phi_z(r, z):
        return special.j1(k * r) * k * math.sinh(k * (z + h)) / math.cosh(k * h)

    P = math.pi * integrate.quad(lambda r: Phi(r, 0.0) * r * r, 0, R,
                                 epsabs=0, epsrel=1e-13)[0]
    N = math.pi * integrate.quad(lambda r: Phi(r, 0.0) ** 2 * r, 0, R,
                                 epsabs=0, epsrel=1e-13)[0]

    def g_ic(r, z):
        if r == 0.0:
            return 0.0
        return (z * (Phi_r(r, z) + Phi(r, z) / r) - r * Phi_z(r, z)) * r

    G = math.pi * integrate.dblquad(g_ic, -h, 0.0, 0.0, R,
                                    epsabs=1e-14, epsrel=1e-11)[0]
    m_sivi = math.pi * R * R * h      # ρ = 1
    e = sa.silindir_esdeger_model(R, h)
    assert kappa == pytest.approx(e['kappa1_1m'], rel=1e-14)
    assert kappa * P * P / N / m_sivi == pytest.approx(e['m1_oran'], rel=1e-9)
    assert h + G / (kappa * P) == pytest.approx(e['z1_m'], rel=1e-8, abs=1e-12)
    assert N / (kappa * P * Phi(R, 0.0)) == pytest.approx(e['Gamma1'], rel=1e-9)


# -------------------------------- basınç integrali ⟷ yay-kütle (60 mod) ---
def _basinc_ve_model(R, h, Om, g=G_0):
    """Tank X(t) yanal ötelemesi; eylemsiz çerçeve potansiyelinin Dini
    serisiyle çeper + taban basıncı integrali (betik v1 §4 ile aynı kurgu).
    Birinci iki modun kütle ve konumu ÜRÜN fonksiyonundan, n ≥ 3 kapalı
    biçimden (aynı Dodge Tablo 3.2 ailesi)."""
    lam = XI
    k = lam / R
    c = 2 * R / ((lam ** 2 - 1) * special.j1(lam))
    w2 = g * k * np.tanh(k * h)
    an = Om ** 2 * c / (w2 - Om ** 2)
    sech = 2.0 * np.exp(-k * h) / (1.0 + np.exp(-2.0 * k * h))
    F_true = R * (R * h) + np.sum(an * special.j1(lam) * R * np.tanh(k * h) / k)
    M_true = (R * (R * -h * h / 2) + R ** 4 / 4
              + np.sum(an * special.j1(lam) * (R / k ** 2) * (2.0 * sech - 1.0)))
    mL = R * R * h
    mn = mL * 2 * R * np.tanh(k * h) / (lam * (lam ** 2 - 1) * h)
    zn = -(2.0 / k) * np.tanh(k * h / 2)         # serbest yüzeye göre
    e = sa.silindir_esdeger_model(R, h)
    mn[0] = mL * e['m1_oran']
    mn[1] = mL * e['m2_oran']
    zn[0] = e['z1_m'] - h
    zn[1] = e['z2_m'] - h
    zG = -h / 2
    xn_per = -1.0 / (w2 - Om ** 2)
    xddn_per = Om ** 2 / (w2 - Om ** 2)
    F_mod = mL + np.sum(mn * xddn_per)
    M_mod = mL * zG + np.sum(mn * zn * xddn_per) - g * np.sum(mn * xn_per)
    return F_true, F_mod, M_true, M_mod


@pytest.mark.parametrize('hR', [0.5, 1.0, 3.0])
@pytest.mark.parametrize('oran', [0.3, 0.8, 1.5])
def test_basinc_integrali_moment_esitligi(hR, oran):
    R = 0.5
    h = hR * R
    w1 = math.sqrt(G_0 * sa.LAMBDA_1 / R * math.tanh(sa.LAMBDA_1 * h / R))
    Ft, Fm, Mt, Mm = _basinc_ve_model(R, h, oran * w1)
    assert abs(Fm - Ft) <= 1e-12 * abs(Ft)
    assert abs(Mm - Mt) <= 1e-6 * abs(Mt)


# ------------------------------------------------------------------ I0 ---
@pytest.mark.parametrize('hd, oran', [
    (0.251, 0.7137), (0.503, 0.3340), (0.869, 0.1426), (1.497, 0.3551),
    (2.503, 0.6648), (4.503, 0.8746)])
def test_I0_sp106_tablo61_betik_v1(hd, oran):
    """I_model / I_rigid = (I0 + m0(z0−z_km)² + m1(z1−z_km)²)/I_rigid,
    betik v1 §5 SP-106 sütunu (4 basamak)."""
    R, m = 0.5, 1.0
    h = hd * 2 * R
    e = sa.silindir_esdeger_model(R, h)
    I0, kaynak = sa.silindir_I0(R, h, m, e)
    assert I0 is not None and I0 >= 0.0 and kaynak == sa.I0_KAYNAK_METNI
    I_model = (I0 + m * e['m0_oran'] * (e['z0_m'] - e['z_km_m']) ** 2
               + m * e['m1_oran'] * (e['z1_m'] - e['z_km_m']) ** 2)
    I_rigid = m * (R * R / 4 + h * h / 12)
    assert round(I_model / I_rigid, 4) == oran


def test_I0_aralik_disinda_yayimlanmaz():
    for hd in (0.1, 0.25, 4.6, 10.0):
        I0, kaynak = sa.silindir_I0(0.5, hd * 1.0, 10.0)
        assert I0 is None and 'yayımlanmadı' in kaynak


# ------------------------------------------------------ düz çeper sönümü ---
def test_duz_ceper_sonumu_errata_bicimi_ve_derin_sinir():
    R, nu, g = 0.5, 1e-6, G_0
    re1 = nu / math.sqrt(g * R ** 3)
    for hR in (0.3, 1.0, 2.0):
        beklenen = (0.83 * math.sqrt(re1) * math.tanh(1.84 * hR) ** -0.25
                    * (1 + 2 * (1 - hR) / math.sinh(3.68 * hR)))
        assert sa.duz_ceper_sonumu(R, hR * R, nu, g) == pytest.approx(
            beklenen, rel=1e-14)
    # (2.7b): derin sıvıda 0,83 √Re1
    assert sa.duz_ceper_sonumu(R, 20 * R, nu, g) == pytest.approx(
        0.83 * math.sqrt(re1), rel=1e-12)
    assert sa.duz_ceper_sonumu(R, 500 * R, nu, g) == pytest.approx(
        0.83 * math.sqrt(re1), rel=1e-12)


@pytest.mark.parametrize('hR', [0.5, 1.0, 2.0, 3.0])
def test_duz_ceper_sonumu_mikishev_ile_yakin(hR):
    """Dodge s. 27: (2.6) ve (2.7) arasındaki sayısal fark 'quite small'.
    Bağımsız ikinci bağıntı (Mikishev–Dorozhkin (2.6a)) ile %10 içinde."""
    R, nu, g = 1.0, 1e-6, G_0
    re1 = nu / math.sqrt(g * R ** 3)
    x = 1.84 * hR
    mik = 0.79 * math.sqrt(re1) * (1 + 0.318 / math.sinh(x)
                                   * (1 + (1 - hR) / math.cosh(x)))
    assert abs(sa.duz_ceper_sonumu(R, hR * R, nu, g) / mik - 1) < 0.10


# ------------------------------------------------------- tablo üreticisi ---
@pytest.fixture(scope='module')
def tablo():
    return sa.silindir_tablosu('oksitleyici', 0.5, 2.0, 1141.0, 'LOX',
                               sigma=0.0132, nu=1.7e-7)


def test_uretici_sozlesmeye_uyar(tablo):
    assert tablo.yontem == st.YONTEM_KAPALI_BICIM
    assert [s['doluluk'] for s in tablo.satirlar] == list(st.DOLULUK_IZGARASI)
    assert all(s['durum'] == st.DURUM_GECERLI for s in tablo.satirlar)
    t2 = st.json_oku(st.json_yaz(tablo))
    assert t2.sozluk() == tablo.sozluk()
    t3 = st.csv_oku(st.csv_yaz(tablo))
    assert t3.sozluk() == tablo.sozluk()


def test_tek_buyukluk_tek_sayi_tablo_ve_besleme_paneli(tablo):
    """Aynı tank, aynı doluluk: tablodan ω1 = √(κ1 g) ile Besleme
    panelinin (CylindricalTankSlosh) f1'i ve m1'i aynı sayı."""
    for s in tablo.satirlar[::4]:
        m = sa.CylindricalTankSlosh(0.5, s['h_m'], g_eff=G_0,
                                    fluid_density=1141.0)
        f_tablo = st.omega1(s['kappa1_1m'], G_0) / (2 * math.pi)
        assert f_tablo == pytest.approx(m.natural_frequency(1)[1], rel=1e-13)
        assert s['m1_oran'] == pytest.approx(m.slosh_mass_ratio(), rel=1e-13)
        assert s['L1_m'] == pytest.approx(m.pendulum_length(), rel=1e-13)


def test_g_eff_haritasi(tablo):
    gs = [0.01, 1.0, G_0, 40.0]
    harita = sa.geff_frekans_haritasi(tablo, gs)
    assert len(harita['f1_hz']) == 29 and len(harita['f1_hz'][0]) == 4
    for i, s in enumerate(tablo.satirlar):
        for j, g in enumerate(gs):
            bo = 1141.0 * g * 0.25 / 0.0132
            if bo < st.BOND_RET_ESIGI:
                assert harita['f1_hz'][i][j] is None
                assert 'BOND_DUSUK_RET' in harita['sebep'][i][j]
            else:
                assert harita['f1_hz'][i][j] == pytest.approx(
                    math.sqrt(s['kappa1_1m'] * g) / (2 * math.pi), rel=1e-14)
    # g = 0,01: Bo = 216 → GECERLI; m1, L1 g'den bağımsız tek eğri
    assert harita['durum'][5][0] == st.DURUM_GECERLI
    assert harita['L1_m'] == [s['L1_m'] for s in tablo.satirlar]
    with pytest.raises(sa.SloshGirdiHatasi):
        sa.geff_frekans_haritasi(tablo, [])
    with pytest.raises(sa.SloshGirdiHatasi):
        sa.geff_frekans_haritasi(tablo, [1.0, -2.0])


def test_g_eff_haritasi_bond_ret_hucresi():
    t = sa.silindir_tablosu('n2o', 0.01, 0.05, 1000.0, 'su', sigma=0.072)
    h = sa.geff_frekans_haritasi(t, [G_0, 1e-3])
    assert h['durum'][10] == [st.DURUM_BEYANLI, st.DURUM_RET]
    assert h['sebep'][10][0] == ['BOND_BEYAN']
    assert h['f1_hz'][10][1] is None


# ---------------------------------------------------------- Bond kapısı ---
def test_analyze_bond_kapisi():
    yok = sa.analyze_slosh(0.5, 1.0, fluid_density=1000.0)['size_envelope']
    assert yok['bond_number'] is None
    assert yok['bond_number_status'] == 'not_evaluated'
    assert yok['missing_input_for_bond_number'] == 'surface_tension'
    var = sa.analyze_slosh(0.5, 1.0, fluid_density=1000.0,
                           surface_tension=0.072)['size_envelope']
    assert var['bond_number'] == pytest.approx(1000 * G_0 * 0.25 / 0.072)
    assert var['bond_number_status'] == 'evaluated'
    assert var['missing_input_for_bond_number'] is None
    assert len(var) == 7          # test_d33 C3: panel her çocuğu okur
    beyan = sa.analyze_slosh(0.01, 0.02, fluid_density=1000.0,
                             surface_tension=0.072)['size_envelope']
    assert beyan['bond_number_status'] == 'evaluated_declared'   # BOND_BEYAN
    with pytest.raises(sa.SloshGirdiHatasi) as e:
        sa.analyze_slosh(0.002, 0.004, fluid_density=1000.0,
                         surface_tension=0.072)
    assert e.value.reason == 'BOND_DUSUK_RET'
    yogunluksuz = sa.analyze_slosh(0.5, 1.0, surface_tension=0.072)
    assert (yogunluksuz['size_envelope']['missing_input_for_bond_number']
            == 'fluid_density')


# ---------------------------------------------------------- kubbe kapısı ---
def test_kubbe_kapisi_hacimle():
    V_ic, va, vu = 1.0, 0.1, 0.1
    assert sa.kubbe_bolgesi_degerlendir(0.05, V_ic, va, vu)['sebep'] == [
        'KUBBE_BOLGESI_SILINDIR_FORMULU_YOK']
    assert sa.kubbe_bolgesi_degerlendir(0.95, V_ic, va, vu)['durum'] == st.DURUM_RET
    orta = sa.kubbe_bolgesi_degerlendir(0.5, V_ic, va, vu)
    assert orta == {'durum': st.DURUM_BEYANLI,
                    'sebep': ['TANK_BASLARI_MODELLENMEDI']}
    assert sa.kubbe_bolgesi_degerlendir(0.5, V_ic, 0.0, 0.0) == {
        'durum': st.DURUM_GECERLI, 'sebep': []}
    for kotu in ((0.5, V_ic, -0.1, 0.0), (0.5, V_ic, 0.6, 0.5),
                 (1.5, V_ic, 0.0, 0.0), (0.5, V_ic, float('nan'), 0.0)):
        with pytest.raises(sa.SloshGirdiHatasi):
            sa.kubbe_bolgesi_degerlendir(*kotu)


def test_esdeger_model_eksik_girdi_adiyla():
    e = sa.CylindricalTankSlosh(0.5, 1.0).esdeger_model()
    assert e['m1_kg'] is None and e['yukler'] is None and e['zeta_ceper'] is None
    assert e['eksik_girdi'] == ['fluid_density', 'kinematic_viscosity']
    e2 = sa.CylindricalTankSlosh(0.5, 1.0, fluid_density=1000.0).esdeger_model(
        kinematic_viscosity=1e-6)
    assert e2['eksik_girdi'] == [] and e2['zeta_ceper'] > 0
