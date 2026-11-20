"""3.0.7 K1 — SP-8009 çalkantı yükleri ve halka bafl sönümü (CALKANTI §A.4, §A.5).

Bağımsız denetimler:
- (A-12) F1 = m1 ω1² Γ1 η, SP-8009 Denk. (4) çeper basıncı dağılımının
  çevre ve derinlik boyunca integraliyle (ρπR² g η tanh(ξh/R)/ξ) aynı;
- (A-13) iki biçim (m1 x1 (ω1²(z1 − z_km) + g) ve m1 ω1² x1 (z_aski − z_km))
  aynı; bağlantı istasyonuna aktarım;
- iki genlik düzeyi: doğrusal sınır 0,2R ve kırılma üst sınırı g/ω1²;
- bafl: Dodge (2.16) el hesabı, yüzey üstü doğrusal azaltma (s. 33),
  geçerlilik kodları, %15 frekans kayması beyanı, öneri kapıları.
"""

import math

import pytest
from scipy import integrate

from hrma.analysis import slosh_analysis as sa
from hrma.analysis import slosh_tablo as st
from hrma.constants import G_0

R, H, RHO = 0.5, 1.0, 1000.0


@pytest.fixture(scope='module')
def yuk():
    return sa.silindir_yukleri(R, H, RHO, G_0, z_baglanti_m=0.0)


def test_kuvvet_genligi_el_hesabi(yuk):
    e = sa.silindir_esdeger_model(R, H)
    m1 = RHO * math.pi * R * R * H * e['m1_oran']
    w2 = e['kappa1_1m'] * G_0
    d = yuk['duzeyler']['dogrusal_sinir']
    assert d['eta_ceper_m'] == pytest.approx(0.2 * R, rel=1e-15)
    assert d['x1_m'] == pytest.approx(e['Gamma1'] * 0.2 * R, rel=1e-15)
    assert d['F1_N'] == pytest.approx(m1 * w2 * e['Gamma1'] * 0.2 * R,
                                      rel=1e-14)
    assert yuk['m1_kg'] == pytest.approx(m1, rel=1e-15)
    assert yuk['omega1_rad_s'] == pytest.approx(math.sqrt(w2), rel=1e-15)


@pytest.mark.parametrize('hR', [0.2, 1.0, 2.0, 4.0])
def test_F1_sp8009_basinc_dagilimi_integrali(hR):
    """SP-8009 Denk. (4)'ün dinamik terimi ρ g η cosh(ξ(h−z')/R)/cosh(ξh/R)
    cos θ, çeper üzerinde cos θ ile integre edilince yanal kuvveti verir.
    (A-12) F1 bununla aynı olmalı (Γ1 ve m1'in bağımsız denetimi)."""
    h = hR * R
    x = sa.LAMBDA_1
    y = sa.silindir_yukleri(R, h, RHO, G_0)
    for duzey in y['duzeyler'].values():
        eta = duzey['eta_ceper_m']
        if eta >= h:
            # 3.0.7 ONARIM-ÇALK (M7-CALK-1): dalga çukuru tabana iner;
            # yük yayımlanmaz (ayrı bekçi: test_v307_onarim_calk).
            assert duzey['F1_N'] is None
            assert sa.GENLIK_DERINLIK_KODU in duzey['sebep']
            continue
        ic = integrate.quad(
            lambda zp: math.cosh(x * (h - zp) / R) / math.cosh(x * h / R),
            0.0, h, epsabs=0, epsrel=1e-13)[0]
        F_basinc = RHO * G_0 * eta * math.pi * R * ic   # ∫cos²θ R dθ = πR
        assert duzey['F1_N'] == pytest.approx(F_basinc, rel=1e-11)


def test_moment_iki_bicim_ve_baglanti(yuk):
    e = sa.silindir_esdeger_model(R, H)
    m1 = yuk['m1_kg']
    w2 = yuk['omega1_rad_s'] ** 2
    for d in yuk['duzeyler'].values():
        x1 = d['x1_m']
        bicim1 = m1 * x1 * (w2 * (e['z1_m'] - e['z_km_m']) + G_0)
        assert d['M1_km_Nm'] == pytest.approx(bicim1, rel=1e-12)
        assert d['M_baglanti_Nm'] == pytest.approx(
            d['M1_km_Nm'] + d['F1_N'] * (e['z_km_m'] - 0.0), rel=1e-14)
    y2 = sa.silindir_yukleri(R, H, RHO, G_0)
    assert all(d['M_baglanti_Nm'] is None for d in y2['duzeyler'].values())


def test_iki_genlik_duzeyi_ve_beyan(yuk):
    e = sa.silindir_esdeger_model(R, H)
    dog = yuk['duzeyler']['dogrusal_sinir']
    kir = yuk['duzeyler']['kirilma_ust_siniri']
    assert dog['sebep'] == []
    assert kir['eta_ceper_m'] == pytest.approx(e['L1_m'], rel=1e-14)
    assert kir['sebep'] == ['GENLIK_DOGRUSAL_SINIR_DISI']
    assert kir['F1_N'] > dog['F1_N']


def test_cepere_basinc(yuk):
    x = sa.LAMBDA_1
    for d in yuk['duzeyler'].values():
        eta = d['eta_ceper_m']
        assert d['p_dinamik_yuzey_Pa'] == pytest.approx(RHO * G_0 * eta,
                                                        rel=1e-15)
        assert d['p_taban_Pa'] == pytest.approx(
            RHO * G_0 * H + RHO * G_0 * eta / math.cosh(x * H / R), rel=1e-14)


def test_yuk_girdi_kapilari():
    for kotu in (dict(rho=-1.0), dict(g_eff=0.0), dict(g_eff=float('nan'))):
        a = dict(R=R, h=H, rho=RHO, g_eff=G_0)
        a.update(kotu)
        with pytest.raises(sa.SloshGirdiHatasi):
            sa.silindir_yukleri(**a)
    with pytest.raises(sa.SloshGirdiHatasi):
        sa.silindir_yukleri(R, H, RHO, G_0, z_baglanti_m=float('inf'))


# ------------------------------------------------------------------ bafl ---
def test_bafl_dodge_216_ve_216a():
    """(2.16a): δ = 0,2R'de γ = 1,27 e^(−4,6 h_s/R) C1^(3/2)."""
    for w, d in ((0.1, 0.3), (0.2, 0.5), (0.3, 1.0)):
        c1 = w * (2 - w)
        b = sa.halka_bafl_sonumu(w, d, 0.2, fill_ratio=3.0)
        assert b['gamma'] == pytest.approx(
            2.83 * math.exp(-4.6 * d) * c1 ** 1.5 * math.sqrt(0.2), rel=1e-12)
        # Kaynak 1,27'yi 2,83·√0,2 = 1,2656'dan yuvarlıyor (%0,35).
        assert b['gamma'] == pytest.approx(
            1.27 * math.exp(-4.6 * d) * c1 ** 1.5, rel=4e-3)


def test_bafl_yuzey_ustu_dogrusal_azalma():
    """Dodge s. 33: h_s = 0 değerinden doğrusal, 0,8δ yükseklikte sıfır."""
    w, eta = 0.2, 0.05
    g0 = sa.halka_bafl_sonumu(w, 0.0, eta)['gamma']
    assert sa.halka_bafl_sonumu(w, -0.4 * eta, eta)['gamma'] == pytest.approx(
        0.5 * g0, rel=1e-12)
    assert sa.halka_bafl_sonumu(w, -0.8 * eta, eta)['gamma'] == 0.0
    assert sa.halka_bafl_sonumu(w, -2.0 * eta, eta)['gamma'] == 0.0
    m = sa.CylindricalTankSlosh(R, 3.0 * R)
    ust = m.baffle_damping(w, -0.4 * eta, amplitude_ratio=eta)
    assert ust['baffle_above_surface'] is True
    assert ust['damping_ratio'] == pytest.approx(0.5 * g0, rel=1e-12)
    assert 'BAFL_GECERLILIK_DISI' in ust['validity_codes']


def test_bafl_gecerlilik_kodlari_ve_frekans_kaymasi():
    derin = sa.CylindricalTankSlosh(R, 3.0 * R)       # h/R = 3 > 2
    temiz = derin.baffle_damping(0.2, 0.3, amplitude_ratio=0.05)
    assert temiz['validity_codes'] == []
    assert 'frequency_shift_up_to' not in temiz
    yakin = derin.baffle_damping(0.2, 0.02, amplitude_ratio=0.05)
    assert yakin['validity_codes'] == ['BAFL_GECERLILIK_DISI']
    assert yakin['frequency_shift_up_to'] == st.BAFL_FREKANS_KAYMASI_UST == 0.15
    sig = sa.CylindricalTankSlosh(R, 2.0 * R)         # h/R = 2 → beyan
    assert sig.baffle_damping(0.2, 0.3)['validity_codes'] == [
        'BAFL_GECERLILIK_DISI']
    buyuk = derin.baffle_damping(0.2, 0.5, amplitude_ratio=0.21)
    assert buyuk['validity_codes'] == ['GENLIK_DOGRUSAL_SINIR_DISI']
    assert buyuk['amplitude_out_of_envelope'] is True
    assert 'amplitude_out_of_envelope' not in derin.baffle_damping(
        0.2, 0.5, amplitude_ratio=0.2)


def test_bafl_girdi_kapilari():
    m = sa.CylindricalTankSlosh(R, H)
    for args in ((0.0, 0.1), (1.5, 0.1), (float('nan'), 0.1),
                 (0.2, float('nan')), (0.2, float('inf'))):
        with pytest.raises(sa.SloshGirdiHatasi):
            m.baffle_damping(*args)
    for eta in (0.0, -0.1, float('nan')):
        with pytest.raises(sa.SloshGirdiHatasi):
            m.baffle_damping(0.2, 0.1, amplitude_ratio=eta)
    for d in (-0.1, float('nan')):
        with pytest.raises(sa.SloshGirdiHatasi) as e:
            m.recommend_baffle(depth_ratio=d)
        assert e.value.field == 'baffle_depth_ratio'
    with pytest.raises(sa.SloshGirdiHatasi):
        m.recommend_baffle(target_damping=float('nan'))


def test_oneri_notu_kaynaksiz_aralik_sayisi_tasimaz():
    m = sa.CylindricalTankSlosh(R, 3 * R)
    rec = m.recommend_baffle()
    assert 'spaced' not in rec['note'] and '~1 radius' not in rec['note']
    assert 'Dodge 2000 Eq. (2.16)' in rec['note']
    assert rec['validity_codes'] == []
