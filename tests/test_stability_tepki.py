"""Tepki fonksiyonu, sönüm bütçesi ve KRİTİK TEPKİ EŞİĞİ bekçileri (F2a).

Doğrulama merdiveni: tasarım belgesi §3.0/§3.6 ve §5 basamak 8-9.

YAYIMLANMIŞ ÇAPA — CULICK & YANG (1990) ÖRNEK MOTORU
-----------------------------------------------------
Culick, F.E.C. & Yang, V., "Prediction of the Stability of Unsteady Motions in
Solid-Propellant Rocket Motors", *Nonsteady Burning and Combustion Stability of
Solid Propellants*, AIAA Progress in Astronautics and Aeronautics Vol. 143,
1990, ss. 719-779 (Stanford AA284A kaynak dizininden indirildi, md5
1fb7c275bb62dc7b607cdf1f25986655). Makalenin Ek'indeki örnek motor verisiyle,
Tablo 1'de yayımlanan lineer büyüme sabitleri BAĞIMSIZ olarak yeniden
hesaplanır:

    yayımlanan   α_N = −160,1 1/s (beş modun hepsinde aynı)
                 α_c = 288,1 / 28,5 / 16,7 1/s (mod 1/2/3)
                 α_p = −46,6 1/s (mod 1, partikül sönümü)
                 toplam α₁ = 81,4 1/s

Bu çapa üç şeyi birden kilitler: (a) lüle sönümü bağıntısı, (b) QSHOD tepki
fonksiyonunun formu, (c) tepki→büyüme kazanç kapanışı. Üçünden biri bozulursa
sayılar tutmaz.

EŞİK/HÜKÜM AYRIMI
-----------------
Bu yolda hüküm YOKTUR: çıktı sözlüklerinde 'verdict' anahtarı yapısal olarak
yasaktır (``forbid_verdict_key``). Bekçi, eşiğin bir gün sessizce hükme
dönüşmesini imkânsız kılar.
"""

import math

import pytest

from hrma.analysis.acoustic_modes import AcousticModeAnalyzer
from hrma.stability import (
    QSHODBand,
    critical_response_real,
    critical_response_table,
    damping_budget,
    nozzle_damping_quasi_steady,
    qshod_response,
    response_gain_uniform_chamber,
)
from hrma.stability.response import (
    CONFIDENCE_EXTRAPOLATED,
    CONFIDENCE_FIRM,
    qshod_response_band,
)

# ---------------------------------------------------------------------------
# Culick & Yang (1990) Ek verisi — makalenin kendi örnek motoru (SI)
# ---------------------------------------------------------------------------
CY_LENGTH_M = 0.5969            # kamara boyu L
CY_PORT_RADIUS_M = 0.0253       # silindirik port yarıçapı r_c
CY_SOUND_SPEED_M_S = 1075.0     # gaz/partikül karışımının ses hızı
CY_GAMMA_MIXTURE = 1.18         # karışım için γ̄
CY_SURFACE_MACH = 0.00173       # yanma yüzeyindeki Mach M_b
CY_BURN_RATE_M_S = 0.01145      # doğrusal yanma hızı ṙ_b
CY_THERMAL_DIFFUSIVITY = 1.0e-7  # yakıtın termal yayınırlığı κ_p [m²/s]
CY_A_PARAM = 6.0                # tepki fonksiyonu parametresi A
CY_B_PARAM = 0.55               # tepki fonksiyonu parametresi B
CY_N_EXPONENT = 0.3             # ṙ_b = 0,0078·(P/3,0e6)^0,3 ⇒ n = 0,3
CY_PRESSURE_PA = 1.06e7         # ortalama kamara basıncı
CY_TEMPERATURE_K = 3539.0       # kamara sıcaklığı

# Yayımlanan Tablo 1 değerleri [1/s]
CY_PUBLISHED_ALPHA_N = -160.1
CY_PUBLISHED_ALPHA_C = {1: 288.1, 2: 28.5, 3: 16.7}
CY_PUBLISHED_ALPHA_P_MODE1 = -46.6
CY_PUBLISHED_TOTAL_MODE1 = 81.4

CY_PORT_AREA_M2 = math.pi * CY_PORT_RADIUS_M ** 2
CY_BURN_AREA_M2 = 2.0 * math.pi * CY_PORT_RADIUS_M * CY_LENGTH_M
# Lüle girişi port alanına eşit varsayılır (makalenin kendi varsayımı):
# kütle dengesi M_N = M_b·S_b/S_c.
CY_NOZZLE_MACH = CY_SURFACE_MACH * CY_BURN_AREA_M2 / CY_PORT_AREA_M2


def _cy_mode_frequency_hz(mode_index):
    """Düz tüpün n'inci boyuna modu f_n = n·ā/(2L)."""
    return mode_index * CY_SOUND_SPEED_M_S / (2.0 * CY_LENGTH_M)


def _cy_gain():
    return response_gain_uniform_chamber(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_BURN_AREA_M2, CY_PORT_AREA_M2,
        CY_SURFACE_MACH, CY_GAMMA_MIXTURE)['gain_1_s']


def _cy_response_real(mode_index):
    omega = 2.0 * math.pi * _cy_mode_frequency_hz(mode_index)
    return qshod_response(CY_A_PARAM, CY_B_PARAM, CY_N_EXPONENT, omega,
                          CY_THERMAL_DIFFUSIVITY,
                          CY_BURN_RATE_M_S)['response_real']


# ===========================================================================
# QSHOD tepki fonksiyonu
# ===========================================================================
def test_qshod_yari_kararli_limitte_usteli_geri_verir():
    """Ω → 0 ⇒ R_p → n TAM olarak — pay çarpanını pinleyen matematiksel kilit.

    Kaynağın taranmış metni bu noktada okunaksızdır; ``n·A·B`` payı dışındaki
    hiçbir seçenek bu limiti sağlamaz.
    """
    for a, b, n in ((6.0, 0.55, 0.3), (10.0, 0.8, 0.5), (3.0, 0.4, 0.25)):
        result = qshod_response(a, b, n, 1e-9, 1.0e-7, 0.01)
        assert result['response_real'] == pytest.approx(n, rel=1e-6)
        assert abs(result['response_imag']) < 1e-6
        assert result['omega_nondim'] < 1e-8


def test_qshod_boyutsuz_frekans_tanimi():
    """Ω = κ·ω/ṙ_b² ve λ(λ−1) = iΩ (Denk. 95) sağlanmalı."""
    omega = 2.0 * math.pi * _cy_mode_frequency_hz(1)
    result = qshod_response(CY_A_PARAM, CY_B_PARAM, CY_N_EXPONENT, omega,
                            CY_THERMAL_DIFFUSIVITY, CY_BURN_RATE_M_S)
    expected_omega_nd = (CY_THERMAL_DIFFUSIVITY * omega
                         / CY_BURN_RATE_M_S ** 2)
    assert result['omega_nondim'] == pytest.approx(expected_omega_nd,
                                                   rel=1e-14)
    assert result['omega_nondim'] == pytest.approx(4.316, abs=1e-3)
    lam = result['lambda']
    assert lam * (lam - 1.0) == pytest.approx(1j * expected_omega_nd,
                                              rel=1e-12)


def test_qshod_frekansla_soner():
    """Yüksek frekansta tepki küçülür (termal dalga takip edemez)."""
    reals = [_cy_response_real(m) for m in (1, 2, 3, 4, 5)]
    assert all(b < a for a, b in zip(reals, reals[1:]))
    assert reals[0] > 1.0 > reals[-1]


@pytest.mark.parametrize('args', [
    (0.0, 0.55, 0.3), (6.0, 0.0, 0.3), (6.0, 0.55, 0.0),
    (None, 0.55, 0.3), (6.0, 0.55, 2.0),
])
def test_qshod_parametreleri_uydurulmaz(args):
    with pytest.raises(ValueError):
        qshod_response(*args, 1000.0, 1.0e-7, 0.01)


# ===========================================================================
# Lüle sönümü — yayımlanan Tablo 1 çapası
# ===========================================================================
def test_lule_sonumu_yayimlanan_deger():
    """α_N = −(ā/L)·M_N·(γ+1)/2 ⇒ −160,2 1/s (yayımlanan −160,1)."""
    result = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    assert result['damping_1_s'] == pytest.approx(CY_PUBLISHED_ALPHA_N,
                                                  rel=5e-3)
    assert result['damping_1_s'] < 0.0
    assert result['admittance_real'] == pytest.approx(
        (CY_GAMMA_MIXTURE - 1.0) * CY_NOZZLE_MACH / 2.0, rel=1e-14)
    assert 'Culick & Yang' in result['basis']


def test_lule_sonumu_moddan_bagimsiz():
    """Yayımlanan tabloda beş modun α_N'i AYNI; bağıntı da mod taşımaz."""
    result = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    assert result['mode_dependence'].startswith('none')


def test_lule_sonumu_boy_ile_ters_orantili():
    """α_N ∝ 1/L (Denk. 101'in sonucu: uzun motorda lüle sönümü zayıf)."""
    short = nozzle_damping_quasi_steady(CY_SOUND_SPEED_M_S, 0.5,
                                        CY_GAMMA_MIXTURE, 0.08)
    long = nozzle_damping_quasi_steady(CY_SOUND_SPEED_M_S, 1.0,
                                       CY_GAMMA_MIXTURE, 0.08)
    assert short['damping_1_s'] == pytest.approx(2.0 * long['damping_1_s'],
                                                 rel=1e-14)


@pytest.mark.parametrize('mach', [0.0, -0.1, 1.0, 1.5, None])
def test_lule_mach_kapisi(mach):
    with pytest.raises(ValueError):
        nozzle_damping_quasi_steady(CY_SOUND_SPEED_M_S, CY_LENGTH_M,
                                    CY_GAMMA_MIXTURE, mach)


# ===========================================================================
# Sürükleme kazancı ve yayımlanan α_c değerleri
# ===========================================================================
@pytest.mark.parametrize('mode_index', [1, 2, 3])
def test_yanma_surukleme_sabiti_yayimlanan_deger(mode_index):
    """α_c = kazanç·Re(R_p) — Tablo 1'in ilk üç modu %3 içinde geri gelir."""
    alpha_c = _cy_gain() * _cy_response_real(mode_index)
    assert alpha_c == pytest.approx(CY_PUBLISHED_ALPHA_C[mode_index],
                                    rel=0.03)


def test_toplam_buyume_sabiti_yayimlanan_deger():
    """Mod 1 net α: lüle + partikül (yayımlanan) + yanma ⇒ 81,4 1/s."""
    nozzle = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    budget = damping_budget({
        'nozzle': nozzle['damping_1_s'],
        # Partikül sönümü F2a'da HESAPLANMAZ; burada makalenin yayımladığı
        # değer ÇAĞIRAN tarafından verilmiş bir terim olarak kullanılır.
        'particle_published': CY_PUBLISHED_ALPHA_P_MODE1,
    })
    net = budget['total_damping_1_s'] + _cy_gain() * _cy_response_real(1)
    assert net == pytest.approx(CY_PUBLISHED_TOTAL_MODE1, rel=0.02)
    assert net > 0.0        # makalenin örneği lineer olarak KARARSIZ


def test_kazanc_yon_bekcileri():
    """Kazanç: S_b/S_c ile artar, L ile azalır, M_b ile doğrusal."""
    base = _cy_gain()
    more_surface = response_gain_uniform_chamber(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, 2.0 * CY_BURN_AREA_M2,
        CY_PORT_AREA_M2, CY_SURFACE_MACH, CY_GAMMA_MIXTURE)['gain_1_s']
    longer = response_gain_uniform_chamber(
        CY_SOUND_SPEED_M_S, 2.0 * CY_LENGTH_M, CY_BURN_AREA_M2,
        CY_PORT_AREA_M2, CY_SURFACE_MACH, CY_GAMMA_MIXTURE)['gain_1_s']
    assert more_surface == pytest.approx(2.0 * base, rel=1e-14)
    assert longer == pytest.approx(0.5 * base, rel=1e-14)


# ===========================================================================
# R_crit — kapalı form özdeşliği ve eşik/hüküm ayrımı
# ===========================================================================
def test_r_crit_lule_yalnizken_kapali_form_ozdesligi():
    """M_N kütle dengesinden gelirse R_crit = (γ+1)/γ — geometriden BAĞIMSIZ.

    R_crit = |α_N|/kazanç = [(ā/L)M_N(γ+1)/2] / [(ā/L)(S_b/S_c)γM_b/2] ve
    M_N = M_b·S_b/S_c ⇒ (γ+1)/γ. Zincirin (sönüm + kazanç + ters çevirme)
    tamamını tek sayıyla kilitleyen analitik bekçi.
    """
    nozzle = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    budget = damping_budget([nozzle])
    result = critical_response_real(budget['total_damping_1_s'], _cy_gain())
    expected = (CY_GAMMA_MIXTURE + 1.0) / CY_GAMMA_MIXTURE
    assert result['critical_response_real'] == pytest.approx(expected,
                                                             rel=1e-12)
    assert result['critical_response_real'] == pytest.approx(1.8475, abs=1e-3)


def test_ornek_motorun_tepkisi_esigin_ustunde():
    """Culick & Yang örneği: Re(R_p) = 3,33 > R_crit = 1,85 ⇒ mod sürüklenir.

    Bu bir KIYASTIR; modül yine de hüküm vermez (aşağıdaki bekçi).
    """
    nozzle = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    budget = damping_budget([nozzle])
    threshold = critical_response_real(
        budget['total_damping_1_s'], _cy_gain())['critical_response_real']
    assert _cy_response_real(1) > threshold


def test_r_crit_yolunda_hukum_yapisal_olarak_yok():
    """Eşik yolunun hiçbir katmanında 'verdict' anahtarı bulunmaz."""
    nozzle = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    budget = damping_budget([nozzle])
    result = critical_response_real(budget['total_damping_1_s'], _cy_gain())
    assert 'verdict' not in result
    assert result['interpretation'] == 'threshold_not_verdict'
    assert 'never a stability verdict' in result['interpretation_basis']


def test_net_kayip_yoksa_esik_uydurulmaz():
    """Bütçe net kayıp değilse R_crit tanımsızdır → None + gerekçe."""
    result = critical_response_real(+12.0, 100.0)
    assert result['critical_response_real'] is None
    assert 'not a net loss' in result['note']


@pytest.mark.parametrize('args', [(None, 100.0), (-10.0, 0.0),
                                  (-10.0, None), (float('nan'), 100.0)])
def test_r_crit_gecersiz_girdiyi_reddeder(args):
    with pytest.raises(ValueError):
        critical_response_real(*args)


def test_eksik_kayiplarin_yonu_beyanli():
    """Modellenmeyen kayıplar eşiği KÖTÜMSER yapar — yön açıkça yazılı."""
    nozzle = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    budget = damping_budget([nozzle])
    assert 'pessimistic' in budget['bias_basis']
    assert 'particle_damping' in budget['not_modelled']
    assert 'viscous_wall_damping' in budget['not_modelled']


# ===========================================================================
# Sönüm bütçesi kapıları
# ===========================================================================
def test_bos_butce_reddedilir():
    """Boş bütçe sessizce 'kayıp yok' demektir — yasak."""
    with pytest.raises(ValueError, match='empty'):
        damping_budget({})


@pytest.mark.parametrize('terms', [{'nozzle': None}, {'nozzle': 'x'},
                                   {'nozzle': float('inf')}, {'': -1.0}])
def test_butce_gecersiz_terimi_reddeder(terms):
    with pytest.raises(ValueError):
        damping_budget(terms)


def test_butce_isaret_sozlesmesi():
    budget = damping_budget({'nozzle': -160.2, 'particle': -46.6})
    assert budget['total_damping_1_s'] == pytest.approx(-206.8, rel=1e-12)
    assert budget['total_loss_1_s'] == pytest.approx(206.8, rel=1e-12)
    assert 'negative = damping' in budget['sign_convention']


# ===========================================================================
# (A, B) bandı ve geçerlilik zarfı (karar 3 sıkılaştırması)
# ===========================================================================
def _synthetic_band():
    """SENTETİK bant — F2a'da künyeli literatür tablosu YOKTUR (o F2b'nin işi).

    Zarf mekanizmasını sınamak için kurulmuştur ve kaynağı bunu söyler.
    """
    return QSHODBand(
        a_range=(5.0, 7.0), b_range=(0.5, 0.6), pressure_exponent_n=0.3,
        formulation_class='synthetic test formulation (not a real propellant)',
        pressure_range_Pa=(5.0e6, 1.2e7),
        temperature_range_K=(3400.0, 3600.0),
        source='Synthetic band used only to exercise the envelope mechanism '
               'in tests; F2a ships no literature table.')


def test_bant_ustverisiz_kurulamaz():
    """Formülasyon sınıfı, zarf ve künye ZORUNLU — biri eksikse ValueError."""
    valid = dict(a_range=(5.0, 7.0), b_range=(0.5, 0.6),
                 pressure_exponent_n=0.3, formulation_class='x',
                 pressure_range_Pa=(5e6, 1.2e7),
                 temperature_range_K=(3400.0, 3600.0), source='y')
    for missing in ('formulation_class', 'source'):
        broken = dict(valid, **{missing: ''})
        with pytest.raises(ValueError, match='mandatory metadata'):
            QSHODBand(**broken)
    for broken_field, bad in (('pressure_range_Pa', (1.2e7, 5e6)),
                              ('temperature_range_K', 3500.0),
                              ('a_range', (0.0, 7.0)),
                              ('pressure_exponent_n', 0.0)):
        with pytest.raises(ValueError):
            QSHODBand(**dict(valid, **{broken_field: bad}))


def test_zarf_ici_firm_rozeti():
    band = _synthetic_band()
    result = qshod_response_band(
        band, 2.0 * math.pi * _cy_mode_frequency_hz(1),
        CY_THERMAL_DIFFUSIVITY, CY_BURN_RATE_M_S,
        pressure_Pa=CY_PRESSURE_PA, temperature_K=CY_TEMPERATURE_K)
    assert result['confidence'] == CONFIDENCE_FIRM
    assert 'inside the validity envelope' in result['confidence_basis']
    assert len(result['corners']) == 4
    assert result['response_real_min'] <= result['response_real_max']


@pytest.mark.parametrize('point,expected_word', [
    ((2.0e6, 3500.0), 'pressure'),        # basınç zarf dışı
    ((1.0e7, 2500.0), 'temperature'),     # sıcaklık zarf dışı
    ((2.0e6, 2500.0), 'pressure'),        # ikisi birden
])
def test_zarf_disi_extrapolated_low_rozeti(point, expected_word):
    """Zarf dışı çalışma noktası: sonuç GİZLENMEZ, rozetlenir."""
    band = _synthetic_band()
    result = qshod_response_band(
        band, 2.0 * math.pi * _cy_mode_frequency_hz(1),
        CY_THERMAL_DIFFUSIVITY, CY_BURN_RATE_M_S,
        pressure_Pa=point[0], temperature_K=point[1])
    assert result['confidence'] == CONFIDENCE_EXTRAPOLATED
    assert expected_word in result['confidence_basis']
    assert 'OUTSIDE the validity envelope' in result['confidence_basis']
    assert result['response_real_min'] is not None   # yine de yayımlanır


def test_ciplak_ab_ciftiyle_bant_cagrilamaz():
    """Üstverisiz (A, B) ikilisi kabul edilmez (zarf kaybolmasın)."""
    with pytest.raises(ValueError, match='QSHODBand instance'):
        qshod_response_band((6.0, 0.55), 1000.0, CY_THERMAL_DIFFUSIVITY,
                            CY_BURN_RATE_M_S, 1.0e7, 3500.0)


def test_bant_tablosu_yalniz_bands_modulunde_yasar():
    """F2b-3 (2026-08-17): künyeli tablo geldi — bu bekçi, F2a döneminin
    ``test_f2a_hazir_bant_tablosu_tasimaz`` bekçisinin HALEFİDİR (nöbetçi
    sözleşmesi: geçici durumu kilitleyen bekçi, durum değişince halefine
    çevrilir — silinmez).

    Eski hüküm KORUNUR: mekanizma modülleri (response/chamber/chug/damping/
    hybrid_lfi) modül sabiti olarak bant TAŞIMAZ. Yeni hüküm: künyeli tablo
    YALNIZ ``hrma.stability.bands``'te yaşar; her dolu kaydın zarf üstverisi
    eksiksizdir ve kaynaksız kayıt yoktur. Derin ölçüm
    ``tests/test_stability_tablolar.py``'dedir.
    """
    import hrma.stability.chamber
    import hrma.stability.chug
    import hrma.stability.damping
    import hrma.stability.hybrid_lfi
    import hrma.stability.response
    for module in (hrma.stability.response, hrma.stability.chamber,
                   hrma.stability.chug, hrma.stability.damping,
                   hrma.stability.hybrid_lfi):
        band_constants = [name for name in dir(module)
                          if isinstance(getattr(module, name), QSHODBand)]
        assert band_constants == [], (
            f'{module.__name__}: mekanizma modülü bant sabiti taşıyor — '
            f'tablonun tek evi hrma.stability.bands')

    from hrma.stability import bands
    dolu = {rid: rec for rid, rec in bands.QSHOD_BAND_RECORDS.items()
            if isinstance(rec, bands.QSHODBandRecord)}
    assert dolu, 'bands.py tablosu boş — halef bekçinin nesnesi kayıp'
    for rid, rec in bands.QSHOD_BAND_RECORDS.items():
        if isinstance(rec, bands.QSHODBandRecord):
            assert rec.band.source.strip(), f'{rid}: kaynaksız kayıt'
            assert rec.band.formulation_class.strip(), rid
        else:
            assert rec.reason.strip(), f'{rid}: gerekçesiz boş kayıt'


# ===========================================================================
# Akustik mod tablosuyla köprü (acoustic_modes DEĞİŞTİRİLMEDEN kullanılır)
# ===========================================================================
def _acoustic_result():
    return AcousticModeAnalyzer().analyze(
        chamber_temperature=CY_TEMPERATURE_K, gamma=CY_GAMMA_MIXTURE,
        gas_constant=377.72, chamber_diameter=2.0 * CY_PORT_RADIUS_M,
        chamber_length=CY_LENGTH_M, n_modes=6)


def test_r_crit_tablosu_akustik_moddan_beslenir():
    """Mod tablosu ÜRETİLMEZ, acoustic_modes'tan okunur; her satırda eşik var."""
    acoustic = _acoustic_result()
    nozzle = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    budget = damping_budget([nozzle])
    table = critical_response_table(acoustic, budget, _cy_gain())

    assert len(table['modes']) == len(acoustic['modes'])
    labels = [row['label'] for row in table['modes']]
    assert labels == [mode['label'] for mode in acoustic['modes']]
    for row in table['modes']:
        assert row['critical_response_real'] == pytest.approx(
            (CY_GAMMA_MIXTURE + 1.0) / CY_GAMMA_MIXTURE, rel=1e-12)
        assert row['frequency_hz'] > 0.0
        assert 'nozzle' in row['damping']
    assert 'acoustic_modes' in table['mode_table_source']
    assert table['interpretation'] == 'threshold_not_verdict'


def test_r_crit_tablosunda_hukum_anahtari_yok():
    """Akustik yolun ÇIKTISINDA 'verdict' anahtarı olursa test kırmızı."""
    acoustic = _acoustic_result()
    nozzle = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    table = critical_response_table(acoustic, damping_budget([nozzle]),
                                    _cy_gain())

    def walk(node, path=''):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key != 'verdict', f"verdict key leaked at {path}.{key}"
                walk(value, f'{path}.{key}')
        elif isinstance(node, (list, tuple)):
            for i, value in enumerate(node):
                walk(value, f'{path}[{i}]')

    walk(table)
    assert 'verdict' not in table
    # Akustik modülün kendi çıktısı da hükümsüz kalmalı (o modül eşik verir).
    assert 'verdict' not in acoustic


def test_kunyesiz_literatur_bandi_reddedilir():
    """Kıyas bandı verilecekse KAYNAĞI zorunludur."""
    acoustic = _acoustic_result()
    nozzle = nozzle_damping_quasi_steady(
        CY_SOUND_SPEED_M_S, CY_LENGTH_M, CY_GAMMA_MIXTURE, CY_NOZZLE_MACH)
    budget = damping_budget([nozzle])
    with pytest.raises(ValueError, match='source'):
        critical_response_table(acoustic, budget, _cy_gain(),
                                literature_band={'low': 1.0, 'high': 3.0})
    table = critical_response_table(
        acoustic, budget, _cy_gain(),
        literature_band={'low': 1.0, 'high': 3.0, 'source': 'test citation'})
    assert table['modes'][0]['literature_band']['source'] == 'test citation'


def test_akustik_sonucu_yerine_rastgele_sozluk_reddedilir():
    with pytest.raises(ValueError, match='AcousticModeAnalyzer'):
        critical_response_table({'not': 'acoustic'},
                                damping_budget({'nozzle': -10.0}), 100.0)
