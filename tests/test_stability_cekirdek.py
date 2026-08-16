"""F2a çekirdek bekçileri: Γ², τ_c özdeşlikleri, chug çevrimi, bulk mod, sözleşme.

Doğrulama merdiveni (tasarım belgesi §5, basamak 2-4 ve 8-9):

(a) Γ² ∈ (0, 1) ve γ = 1,2'de 0,42059… — depodaki Vandenkerckhove kullanımıyla
    (``hrma.flow.quasi1d.choked_mass_flow``) TEK kavram olduğu, Γ'nın oradan
    geri kurtarılmasıyla kilitlenir.
(b) τ_c'nin iki bağımsız yolu — L*/(c*Γ²) ve V·c*/(A_t·R·T) — R·T = (c*Γ)²
    özdeşliği verildiğinde bit-özdeş.
(c) Chug nötr eğrisi: J = 0,2 ⇒ τ/τ_c = 0,865152… (tasarım belgesi §3.2'nin
    elle hesabı); J → 1/2⁻ tekilliği; J ≥ 1/2 reddi; kapalı formun karakteristik
    denklemin GERÇEK köküyle çakışması (Re(s) = 0 nötr noktada).
(d) Tipik sıvı vakası: L* = 1 m, c* = 1800 m/s, γ = 1,2 ⇒ τ_c = 1,3209 ms,
    nötr τ = 1,1428 ms (belgedeki 1,32 / 1,14 ms).
(e) Katı bulk modunun gecikmesiz limiti tam olarak mevcut ürün kapısına
    (``solid_rocket_engine.py``: ``if self.n >= 1.0`` →
    ``warn.solid.burn_rate_exponent_ge_one``) indirgenir — çapraz bekçi kaynak
    dosyayı OKUR, o dosyaya dokunmaz.
(f) Hüküm sözleşmesi: kapsamsız hüküm kurulamaz, hükümsüz yola hüküm sızamaz.
(g) Uydurma varsayılan yasağı: eksik/geçersiz girdi ValueError.
"""

import math
import re
from pathlib import Path

import pytest

from hrma.analysis.acoustic_modes import (
    CHUG_DP_RATIO_MINIMUM,
    CHUG_DP_RATIO_RECOMMENDED,
)
from hrma.flow.quasi1d import choked_mass_flow
from hrma.stability import (
    CHUG_GAIN_J_MAX,
    STABILITY_NOT_MODELLED,
    VERDICTS,
    assess_chug,
    bulk_mode_zero_lag,
    chamber_time_constant,
    chug_neutral_frequency_hz,
    chug_neutral_tau_ratio,
    chug_rightmost_root,
    cstar_from_rt,
    feed_inertance_time_constant,
    forbid_verdict_key,
    gamma_function,
    gamma_function_sq,
    make_verdict,
    rt_from_cstar,
    sweep_feed_line_length,
    tau_c_from_volume,
)
from hrma.stability.chug import chug_neutral_delay_s

# Tasarım belgesi §3.2'nin tipik sıvı motor vakası (SI).
DOC_L_STAR_M = 1.0
DOC_C_STAR_M_S = 1800.0
DOC_GAMMA = 1.2
DOC_TAU_C_S = 1.3208873639398158e-3      # ölçüldü; belgede 1,32 ms
DOC_NEUTRAL_RATIO = 0.8651523967380913   # belgede 0,865 (J = 0,20)


# ===========================================================================
# (a) Γ² bandı ve tek-kavram kilidi
# ===========================================================================
@pytest.mark.parametrize('gamma', [1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.4, 1.67,
                                   1.9])
def test_gamma_kare_sifir_bir_araliginda(gamma):
    """Γ² her fiziksel γ için (0, 1) — τ_c paydasının varlık şartı."""
    value = gamma_function_sq(gamma)
    assert 0.0 < value < 1.0
    # Γ = √(Γ²) tanımı (Vandenkerckhove fonksiyonu)
    assert gamma_function(gamma) == pytest.approx(math.sqrt(value), rel=1e-15)


def test_gamma_kare_belge_degeri():
    """γ = 1,2 ⇒ Γ² = 0,42059… (tasarım belgesi §3.2: 0,4206)."""
    assert gamma_function_sq(1.2) == pytest.approx(0.4205926793776707,
                                                   rel=1e-14)


def test_gamma_fonksiyonu_quasi1d_ile_ayni_kavram():
    """Γ, depoda zaten kullanılan Vandenkerckhove çarpanının TA KENDİSİ.

    ``choked_mass_flow`` ṁ = P0·A*/√T0·√(γ/R)·(2/(γ+1))^((γ+1)/(2(γ−1)))
    yazar; buradan Γ = ṁ·√(R·T0)/(P0·A*) geri kurtarılır. İki modül aynı
    sayıyı üretmiyorsa kavram ikiye bölünmüş demektir (parametre tutarlılığı).
    """
    gamma, R, P0, T0, at = 1.2, 350.0, 4.0e6, 3200.0, 0.002
    mdot = choked_mass_flow(P0, T0, gamma, R, at)
    gamma_from_flow = mdot * math.sqrt(R * T0) / (P0 * at)
    assert gamma_from_flow == pytest.approx(gamma_function(gamma), rel=1e-12)


@pytest.mark.parametrize('bad', [1.0, 2.0, 0.9, -1.2, float('nan'),
                                 float('inf'), None, '1.2', True])
def test_gamma_kapisi_uydurma_yedek_uretmez(bad):
    with pytest.raises(ValueError):
        gamma_function_sq(bad)


# ===========================================================================
# (b) τ_c özdeşlikleri
# ===========================================================================
def test_tau_c_belge_degeri():
    """L* = 1 m, c* = 1800 m/s, γ = 1,2 ⇒ τ_c = 1,3209 ms (belge: 1,32 ms)."""
    result = chamber_time_constant(DOC_L_STAR_M, DOC_C_STAR_M_S, DOC_GAMMA)
    assert result['tau_c_s'] == pytest.approx(DOC_TAU_C_S, rel=1e-14)
    assert result['tau_c_s'] * 1e3 == pytest.approx(1.32, abs=5e-3)
    assert 'Karabeyoglu' in result['tau_c_basis']


def test_tau_c_iki_yol_bit_ozdes():
    """L*/(c*Γ²) ile V/A_t üzerinden gelen yol bit-özdeş olmalı."""
    volume, throat = 0.0125, 0.0125 / DOC_L_STAR_M     # L* = V/A_t = 1 m
    direct = chamber_time_constant(DOC_L_STAR_M, DOC_C_STAR_M_S, DOC_GAMMA)
    via_volume = tau_c_from_volume(volume, throat, DOC_C_STAR_M_S, DOC_GAMMA)
    assert via_volume['tau_c_s'] == direct['tau_c_s']   # bit-özdeş
    assert via_volume['l_star_m'] == pytest.approx(DOC_L_STAR_M, rel=1e-15)


def test_tau_c_termodinamik_yol_ile_ozdes():
    """τ_c = L*/(c*Γ²) ⟺ V·c*/(A_t·R·T), R·T = (c*Γ)² verildiğinde."""
    volume, throat = 0.0125, 0.0125
    c_star, gamma = DOC_C_STAR_M_S, DOC_GAMMA
    rt = rt_from_cstar(c_star, gamma)
    tau_thermo = volume * c_star / (throat * rt)
    tau_lstar = tau_c_from_volume(volume, throat, c_star, gamma)['tau_c_s']
    assert tau_thermo == pytest.approx(tau_lstar, rel=1e-14)


def test_rt_cstar_gidis_donus():
    """R·T = (c*Γ)² ve c* = √(R·T)/Γ birbirinin tersi."""
    for gamma in (1.14, 1.2, 1.33):
        rt = rt_from_cstar(1650.0, gamma)
        assert cstar_from_rt(rt, gamma) == pytest.approx(1650.0, rel=1e-13)
    # Fiziksel mertebe: γ=1,2 · c*=1800 ⇒ R·T ≈ 1,36e6 (m/s)² ⇒ T ≈ 3400 K
    # (R ≈ 400 J/kgK sınıfı) — mertebe kontrolü, iddia değil.
    assert 1.0e6 < rt_from_cstar(1800.0, 1.2) < 2.0e6


def test_tau_c_tekdüze_yonleri():
    """τ_c: L*'ta kesin artan, c*'ta kesin azalan (fiziksel yön bekçisi)."""
    base = chamber_time_constant(1.0, 1800.0, 1.2)['tau_c_s']
    bigger_lstar = chamber_time_constant(1.5, 1800.0, 1.2)['tau_c_s']
    faster_cstar = chamber_time_constant(1.0, 2000.0, 1.2)['tau_c_s']
    assert bigger_lstar > base > faster_cstar


# ===========================================================================
# (c) + (d) Chug nötr eğrisi ve kök yeri
# ===========================================================================
def test_chug_notr_egrisi_belge_capasi():
    """J = 0,20 ⇒ τ/τ_c = 0,865152… (tasarım belgesi §3.2 elle hesabı)."""
    assert chug_neutral_tau_ratio(0.2) == pytest.approx(DOC_NEUTRAL_RATIO,
                                                        rel=1e-14)
    assert chug_neutral_tau_ratio(0.2) == pytest.approx(0.8652, abs=5e-5)


def test_chug_notr_gecikme_tipik_sivi_vakasi():
    """Belge §3.2: τ_c = 1,32 ms ⇒ nötr τ ≈ 1,14 ms (atomizasyon bandı)."""
    tau_c = chamber_time_constant(DOC_L_STAR_M, DOC_C_STAR_M_S,
                                  DOC_GAMMA)['tau_c_s']
    neutral = chug_neutral_tau_ratio(0.2) * tau_c
    assert neutral == pytest.approx(1.1427688687335906e-3, rel=1e-12)
    assert neutral * 1e3 == pytest.approx(1.143, abs=1e-3)


def test_chug_notr_egrisi_j_sifira_giderken_pi_j():
    """J → 0⁺ limitinde τ/τ_c → π·J + 4J² (arccos(−2J) = π/2 + 2J + …).

    Küçük ΔP ⇒ nötr gecikme sıfıra gider: kazanç büyüdükçe neredeyse her
    gecikme kararsızdır. İkinci mertebe terim de ölçüldüğü için bekçi
    sadece limiti değil YAKLAŞMA HIZINI da kilitler.
    """
    for j in (1e-3, 1e-4, 1e-5, 1e-6):
        expansion = math.pi * j + 4.0 * j * j
        # Kalan O(J³) mertebesindedir (ölçüldü: katsayı ≈ 6,3).
        assert chug_neutral_tau_ratio(j) == pytest.approx(expansion,
                                                          rel=1e-5)
        # Baş terim: oran/J → π
        assert chug_neutral_tau_ratio(j) / j == pytest.approx(math.pi,
                                                              rel=3.0 * j)


def test_chug_notr_egrisi_yarim_limitinde_iraksar():
    """J → 1/2⁻ limitinde nötr gecikme sonsuza gider (tekillik)."""
    values = [chug_neutral_tau_ratio(j) for j in (0.4, 0.45, 0.49, 0.499,
                                                  0.4999)]
    assert all(b > a for a, b in zip(values, values[1:]))
    assert values[-1] > 100.0


@pytest.mark.parametrize('j', [0.5, 0.55, 1.0, 3.0])
def test_chug_notr_egrisi_j_yarim_ustunde_reddedilir(j):
    """J ≥ 1/2'de nötr çözüm YOKTUR → ValueError (uydurma sayı üretilmez)."""
    with pytest.raises(ValueError, match='no neutral chug solution|No neutral'):
        chug_neutral_tau_ratio(j)


def test_chug_notr_egrisi_j_de_kesin_azalan():
    """Nötr τ/τ_c, J'de kesin ARTAN: 'ΔP artır' tavsiyesi teoremdir."""
    ratios = [chug_neutral_tau_ratio(j) for j in (0.05, 0.1, 0.2, 0.3, 0.4)]
    assert all(b > a for a, b in zip(ratios, ratios[1:]))


@pytest.mark.parametrize('j', [0.05, 0.1, 0.2, 0.3, 0.4, 0.49])
def test_notr_noktada_karakteristik_denklem_kokü_hayali_eksende(j):
    """Kapalı form nötr eğri ⟺ karakteristik denklemin kökü Re(s) = 0.

    Bağımsız iki yol: (1) analitik nötr eğri, (2) Lambert-W baskın kök.
    """
    tau_c = DOC_TAU_C_S
    tau = chug_neutral_tau_ratio(j) * tau_c
    root = chug_rightmost_root(j, tau, tau_c)
    assert abs(root.real) < 1e-8 * (1.0 / tau_c)
    expected_omega = math.sqrt(1.0 - 4.0 * j * j) / (2.0 * j * tau_c)
    assert abs(root.imag) == pytest.approx(expected_omega, rel=1e-10)
    assert chug_neutral_frequency_hz(j, tau_c) == pytest.approx(
        expected_omega / (2.0 * math.pi), rel=1e-12)


@pytest.mark.parametrize('j', [0.05, 0.2, 0.4])
@pytest.mark.parametrize('ratio', [0.5, 0.9, 1.1, 2.0])
def test_kokun_isareti_notr_egriyle_tutarli(j, ratio):
    """τ < τ_nötr ⇒ Re(s) < 0; τ > τ_nötr ⇒ Re(s) > 0."""
    tau_c = DOC_TAU_C_S
    tau = ratio * chug_neutral_tau_ratio(j) * tau_c
    root = chug_rightmost_root(j, tau, tau_c)
    assert (root.real > 0.0) == (ratio > 1.0)


def test_gecikmesiz_limitte_analitik_kok():
    """τ = 0 ⇒ s = −(1 + 1/(2J))/τ_c (kapalı form özel hâli)."""
    tau_c, j = DOC_TAU_C_S, 0.2
    root = chug_rightmost_root(j, 0.0, tau_c)
    assert root.imag == 0.0
    assert root.real == pytest.approx(-(1.0 + 1.0 / (2.0 * j)) / tau_c,
                                      rel=1e-14)


def test_karakteristik_denklem_kaliniti_sifir():
    """Bulunan kök gerçekten denklemi sağlar (kalıntı ~ makine sıfırı)."""
    import cmath
    tau_c, j = DOC_TAU_C_S, 0.18
    tau = 0.7 * chug_neutral_tau_ratio(j) * tau_c
    s = chug_rightmost_root(j, tau, tau_c)
    residual = tau_c * s + 1.0 + (1.0 / (2.0 * j)) * cmath.exp(-s * tau)
    assert abs(residual) < 1e-12


# ===========================================================================
# Chug hükmü ve klasik kural ÖLÇÜMÜ
# ===========================================================================
def test_assess_chug_kararli_ve_kararsiz_hukumler():
    tau_c = DOC_TAU_C_S
    neutral = chug_neutral_tau_ratio(0.2) * tau_c
    stable = assess_chug(0.2, 0.8 * neutral, tau_c)
    unstable = assess_chug(0.2, 1.2 * neutral, tau_c)
    assert stable['verdict'] == 'stable'
    assert unstable['verdict'] == 'unstable'
    assert stable['growth_rate_1_s'] < 0.0 < unstable['growth_rate_1_s']
    for result in (stable, unstable):
        assert result['verdict'] in VERDICTS
        assert 'chug' in result['verdict_scope']
        assert 'modeled mechanism only' in result['verdict_scope']
        assert result['frequency_hz'] > 0.0


def test_assess_chug_j_yarim_ustunde_kosulsuz_kararli():
    """J ≥ 1/2: nötr nokta yok ⇒ her gecikmede kararlı (modelin teoremi)."""
    result = assess_chug(0.6, 50.0 * DOC_TAU_C_S, DOC_TAU_C_S)
    assert result['verdict'] == 'stable'
    assert result['unconditionally_stable'] is True
    assert result['neutral_delay_s'] is None
    assert 'unconditionally stable' in result['verdict_basis']


def test_klasik_kural_olcum_olarak_tasinir_esik_olarak_degil():
    """%15-25 kuralı modelde NEREYE düşüyor — kayıt; eşik testi DEĞİL.

    Eşikler ayrıca ``acoustic_modes``ten ithal edilir; bu dosyada ikinci kez
    tanımlanmaz (tek kaynak kuralı).
    """
    result = assess_chug(0.2, 0.5 * DOC_TAU_C_S, DOC_TAU_C_S)
    cross = result['classical_rule_cross_check']
    assert cross['rule_min_ratio'] == CHUG_DP_RATIO_MINIMUM == 0.15
    assert cross['rule_recommended_ratio'] == CHUG_DP_RATIO_RECOMMENDED == 0.20
    assert cross['model_neutral_tau_over_tau_c_at_rule_recommended'] == (
        pytest.approx(DOC_NEUTRAL_RATIO, rel=1e-12))
    assert cross['model_neutral_tau_over_tau_c_at_rule_min'] == (
        pytest.approx(chug_neutral_tau_ratio(0.15), rel=1e-12))
    assert 'Measurement, not a threshold test' in cross['interpretation']


def test_chug_esikleri_bu_pakette_yeniden_tanimlanmamis():
    """Chug eşik sayıları (0,20/0,15) hrma/stability içinde YAZILI OLMAMALI.

    §1.1-1'de ölçülen kusur (aynı sayı üç ayrı künyeyle) bu paketle DÖRDÜNCÜ
    kez tekrarlanmasın: sayılar yalnız acoustic_modes'ten ithal edilir.
    """
    package = Path(__file__).resolve().parents[1] / 'hrma' / 'stability'
    literals = re.compile(r'=\s*0\.(20|15|2|25)\b')
    offenders = []
    for path in sorted(package.glob('*.py')):
        for lineno, line in enumerate(path.read_text(encoding='utf-8')
                                      .splitlines(), 1):
            code = line.split('#', 1)[0]
            if literals.search(code) and 'CHUG' in code.upper():
                offenders.append(f'{path.name}:{lineno}: {line.strip()}')
    assert not offenders, (
        'Chug threshold literals redefined inside hrma/stability — import '
        'them from hrma.analysis.acoustic_modes instead:\n'
        + '\n'.join(offenders))


# ===========================================================================
# Besleme ataleti (karar 5) — varsayılan YOK, tarama kancası var
# ===========================================================================
def test_atalet_zaman_sabiti_formulu():
    """τ_f = ℓ·ṁ/(2·A·ΔP_inj) — dördü de çağırandan gelir."""
    tau_f = feed_inertance_time_constant(2.0, 3.0e-4, 1.5, 6.0e5)
    assert tau_f == pytest.approx(2.0 * 1.5 / (2.0 * 3.0e-4 * 6.0e5),
                                  rel=1e-14)


@pytest.mark.parametrize('args', [
    (0.0, 3.0e-4, 1.5, 6.0e5),      # sıfır uzunluk
    (2.0, 0.0, 1.5, 6.0e5),         # sıfır kesit
    (2.0, 3.0e-4, -1.0, 6.0e5),     # negatif debi
    (2.0, 3.0e-4, 1.5, 0.0),        # sıfır ΔP
    (None, 3.0e-4, 1.5, 6.0e5),     # eksik girdi
])
def test_atalet_girdileri_uydurulmaz(args):
    with pytest.raises(ValueError):
        feed_inertance_time_constant(*args)


def test_ataletsiz_varsayilan_beyanli():
    """τ_f verilmezse model ataletsiz koşar ve bunu BEYAN eder."""
    result = assess_chug(0.2, 0.5 * DOC_TAU_C_S, DOC_TAU_C_S)
    assert result['inertance_included'] is False
    assert result['tau_f_s'] is None
    assert 'no layout default is assumed' in result['inertance_basis']
    assert 'inertance-free' in result['verdict_scope']


@pytest.mark.parametrize('j', [0.05, 0.2, 0.4])
@pytest.mark.parametrize('tf_mult', [0.0, 0.25, 1.0, 4.0])
def test_genel_notr_kosul_ataletli_halde_de_kok_ile_cakisir(j, tf_mult):
    """Ataletli nötr formülü ⟺ izlenen kökün hayali eksene oturması.

    τ_f = 0'da genel formül kapalı forma ÖZDEŞ olmalı (aynı sayı).
    """
    tau_c = DOC_TAU_C_S
    tau_f = tf_mult * tau_c
    neutral = chug_neutral_delay_s(j, tau_c, tau_f)
    if tf_mult == 0.0:
        assert neutral == pytest.approx(chug_neutral_tau_ratio(j) * tau_c,
                                        rel=1e-12)
    root = chug_rightmost_root(j, neutral, tau_c, tau_f)
    assert abs(root.real) < 1e-6 * (1.0 / tau_c)


def test_atalet_hukmu_ve_kapsam_etiketi():
    tau_c = DOC_TAU_C_S
    tau_f = feed_inertance_time_constant(2.0, 3.0e-4, 1.5, 6.0e5)
    neutral = chug_neutral_delay_s(0.2, tau_c, tau_f)
    stable = assess_chug(0.2, 0.7 * neutral, tau_c, tau_f_s=tau_f)
    unstable = assess_chug(0.2, 1.3 * neutral, tau_c, tau_f_s=tau_f)
    assert stable['verdict'] == 'stable'
    assert unstable['verdict'] == 'unstable'
    assert stable['inertance_included'] is True
    assert 'inertance-free' not in stable['verdict_scope']
    assert stable['model'].startswith('lumped_inertance')


def test_l_taramasi_kancasi_varsayilan_uretmez():
    """Tarama dizisi AÇIKÇA verilir; boş dizi reddedilir, varsayılan yoktur."""
    with pytest.raises(ValueError, match='empty'):
        sweep_feed_line_length([], 3.0e-4, 1.5, 6.0e5, 0.2, 1.0e-3,
                               DOC_TAU_C_S)
    rows = sweep_feed_line_length([0.5, 1.0, 2.0, 5.0], 3.0e-4, 1.5, 6.0e5,
                                  0.2, 1.0e-3, DOC_TAU_C_S)
    assert [r['line_length_m'] for r in rows] == [0.5, 1.0, 2.0, 5.0]
    assert all(r['inertance_included'] for r in rows)
    # Hat uzunluğu arttıkça atalet zaman sabiti kesin artar (yön bekçisi).
    taus = [r['tau_f_s'] for r in rows]
    assert all(b > a for a, b in zip(taus, taus[1:]))


def test_taramanin_varsayilan_parametresi_yok():
    """Kanca hiçbir varsayılan tarama TAŞIMAZ (imza denetimi)."""
    import inspect
    sig = inspect.signature(sweep_feed_line_length)
    assert sig.parameters['line_lengths_m'].default is inspect.Parameter.empty


# ===========================================================================
# (e) Katı bulk modu ve ürün kapısıyla çapraz
# ===========================================================================
@pytest.mark.parametrize('n,expect_unstable', [
    (0.2, False), (0.35, False), (0.9, False), (0.999, False),
    (1.0, True), (1.05, True), (1.5, True),
])
def test_bulk_mod_gecikmesiz_olcut(n, expect_unstable):
    result = bulk_mode_zero_lag(n, tau_c_s=DOC_TAU_C_S)
    assert result['criterion_met'] is expect_unstable
    assert result['verdict'] == ('unstable' if expect_unstable else 'stable')
    assert result['growth_rate_1_s'] == pytest.approx(
        (n - 1.0) / DOC_TAU_C_S, rel=1e-14)
    assert (result['growth_rate_1_s'] >= 0.0) is expect_unstable
    assert 'zero thermal-lag' in result['verdict_scope']


def test_bulk_mod_tau_c_verilmezse_buyume_orani_uydurulmaz():
    result = bulk_mode_zero_lag(0.35)
    assert result['growth_rate_1_s'] is None
    assert result['tau_c_s'] is None
    assert result['verdict'] == 'stable'


def test_bulk_mod_urun_kapisiyla_capraz():
    """Ölçüt, katı çözücüdeki mevcut kritik uyarı kapısıyla AYNI olmalı.

    Kaynak dosya yalnız OKUNUR (F2a o dosyaya dokunmaz): kapının hâlâ
    ``if self.n >= 1.0`` biçiminde ve ``warn.solid.burn_rate_exponent_ge_one``
    anahtarına bağlı olduğu kod kanıtıyla doğrulanır; kapı taşınır/gevşerse
    bu bekçi kırmızıya düşer.
    """
    source_path = (Path(__file__).resolve().parents[1] / 'hrma' / 'engines'
                   / 'solid_rocket_engine.py')
    source = source_path.read_text(encoding='utf-8')
    gate = re.search(
        r'if self\.n >= 1\.0:\s*\n\s*notes\.append\(_w\(\s*\n?\s*'
        r"'warn\.solid\.burn_rate_exponent_ge_one'", source)
    assert gate is not None, (
        'The solid solver n >= 1 gate could not be found — the bulk mode '
        'cross-check has lost its anchor (search: warn.solid.'
        'burn_rate_exponent_ge_one).')
    # Davranış çaprazı: aynı n değerlerinde iki taraf aynı kararı vermeli.
    for n in (0.1, 0.5, 0.99, 1.0, 1.01, 2.0):
        product_gate_fires = n >= 1.0
        assert bulk_mode_zero_lag(n)['criterion_met'] is product_gate_fires


# ===========================================================================
# (f) Hüküm sözleşmesi — şema düzeyinde zorlanır
# ===========================================================================
@pytest.mark.parametrize('scope', [None, '', '   ', 42])
def test_kapsamsiz_hukum_kurulamaz(scope):
    with pytest.raises(ValueError, match='verdict_scope is mandatory'):
        make_verdict('stable', scope, 'gerekçe')


@pytest.mark.parametrize('basis', [None, '', '  '])
def test_gerekcesiz_hukum_kurulamaz(basis):
    with pytest.raises(ValueError, match='verdict_basis is mandatory'):
        make_verdict('stable', 'kapsam', basis)


@pytest.mark.parametrize('verdict', ['STABLE', 'ok', 'NOT_EVALUATED', '',
                                     None, True])
def test_sozlukte_olmayan_hukum_reddedilir(verdict):
    with pytest.raises(ValueError, match='verdict must be one of'):
        make_verdict(verdict, 'kapsam', 'gerekçe')


def test_hukum_ucluSu_tam():
    trio = make_verdict('marginal', ' kapsam ', ' gerekçe ')
    assert trio == {'verdict': 'marginal', 'verdict_scope': 'kapsam',
                    'verdict_basis': 'gerekçe'}


def test_hukumlu_her_cikti_kapsam_tasir():
    """Paketin hüküm veren üç yolunda da kapsam alanı dolu."""
    results = [
        assess_chug(0.2, 0.5 * DOC_TAU_C_S, DOC_TAU_C_S),
        bulk_mode_zero_lag(0.4, tau_c_s=DOC_TAU_C_S),
    ]
    for result in results:
        assert result['verdict'] in VERDICTS
        assert result['verdict_scope'].strip()
        assert result['verdict_basis'].strip()


def test_forbid_verdict_key_ic_ice_yakalar():
    """Hükümsüz yola hüküm sızarsa (iç içe bile) ValueError."""
    forbid_verdict_key({'a': [{'b': {'c': 1}}]}, 'test')       # temiz
    with pytest.raises(ValueError, match='structurally forbidden'):
        forbid_verdict_key({'modes': [{'verdict': 'stable'}]}, 'test')


def test_not_modelled_sozlugu_cikti_ile_tasiniyor():
    result = assess_chug(0.2, 0.5 * DOC_TAU_C_S, DOC_TAU_C_S)
    assert 'nonlinear_behaviour' in result['not_modelled']
    assert (result['not_modelled']['nonlinear_behaviour']
            == STABILITY_NOT_MODELLED['nonlinear_behaviour'])
    assert 'triggering' in STABILITY_NOT_MODELLED['nonlinear_behaviour']


# ===========================================================================
# (g) Uydurma varsayılan yasağı
# ===========================================================================
@pytest.mark.parametrize('kwargs', [
    dict(l_star_m=0.0, c_star_m_s=1800.0, gamma=1.2),
    dict(l_star_m=-1.0, c_star_m_s=1800.0, gamma=1.2),
    dict(l_star_m=1.0, c_star_m_s=0.0, gamma=1.2),
    dict(l_star_m=1.0, c_star_m_s=None, gamma=1.2),
    dict(l_star_m=float('nan'), c_star_m_s=1800.0, gamma=1.2),
])
def test_tau_c_eksik_girdiyi_reddeder(kwargs):
    with pytest.raises(ValueError):
        chamber_time_constant(**kwargs)


@pytest.mark.parametrize('args', [
    (0.0, 1.0e-3, DOC_TAU_C_S),        # J = 0
    (-0.2, 1.0e-3, DOC_TAU_C_S),       # J < 0
    (0.2, 0.0, DOC_TAU_C_S),           # τ = 0 (assess yolu pozitif ister)
    (0.2, 1.0e-3, 0.0),                # τ_c = 0
    (0.2, None, DOC_TAU_C_S),          # eksik gecikme
])
def test_assess_chug_eksik_girdiyi_reddeder(args):
    with pytest.raises(ValueError):
        assess_chug(*args)


@pytest.mark.parametrize('n', [-0.1, None, float('nan'), '0.3'])
def test_bulk_mod_gecersiz_usteli_reddeder(n):
    with pytest.raises(ValueError):
        bulk_mode_zero_lag(n)


    # ---------------------------------------------------------------------
def test_paket_motor_katmanini_ithal_etmez():
    """F2a saf fiziktir: motor/Flask katmanına bağlanmaz (kaynak denetimi).

    Bağlanırsa çekirdek, motor sonuç şemasının değişimlerine kilitlenir ve
    F2b'nin işi çekirdeğe sızmış olur.
    """
    package = Path(__file__).resolve().parents[1] / 'hrma' / 'stability'
    forbidden = ('hrma.engines', 'hrma.app', 'flask', 'hrma.static')
    offenders = []
    for path in sorted(package.glob('*.py')):
        text = path.read_text(encoding='utf-8')
        for line in text.splitlines():
            code = line.split('#', 1)[0]
            if ('import' in code
                    and any(name in code for name in forbidden)):
                offenders.append(f'{path.name}: {line.strip()}')
    assert not offenders, (
        'hrma/stability must stay engine-free (F2a scope):\n'
        + '\n'.join(offenders))


# Sözleşmenin birim soneki listesi (modül docstring'i ile aynı) ------------
_UNIT_SUFFIXES = ('_Pa', '_K', '_m', '_m2', '_m3', '_m_s', '_m2_s2', '_kg_s',
                  '_kg_m3', '_kg_m2_s', '_s', '_1_s', '_hz', '_W', '_J_kgK')
# Boyutsuz olduğu için sonek TAŞIMAYAN adlar (bilinçli, tek tek sayılmış).
_DIMENSIONLESS_KEYS = {
    'dp_ratio_j', 'tau_over_tau_c', 'neutral_tau_over_tau_c', 'gamma',
    'gamma_function_sq', 'burn_rate_exponent', 'of_ratio', 'rt_ratio',
    'coefficient', 'delay_constant_c_prime', 'response_real',
    'response_imag', 'omega_nondim', 'admittance_real', 'convective_term',
    'mode_shape_mean_square', 'critical_response_real', 'separation_decades',
    'pressure_exponent_n',
    # Klasik kural çaprazı: hepsi boyutsuz (oran ve τ/τ_c ölçümleri)
    'rule_min_ratio', 'rule_recommended_ratio',
    'model_neutral_tau_over_tau_c_at_rule_min',
    'model_neutral_tau_over_tau_c_at_rule_recommended',
}


def _numeric_keys(node, prefix=''):
    """Sözlükteki sayısal (bool olmayan) yaprakların adlarını toplar."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key.startswith('_') or key == 'inputs':
                continue          # girdiler zaten yankı; ayrı denetlenir
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                found.append(key)
            else:
                found.extend(_numeric_keys(value, f'{prefix}{key}.'))
    elif isinstance(node, (list, tuple)):
        for item in node:
            found.extend(_numeric_keys(item, prefix))
    return found


@pytest.mark.parametrize('builder', [
    lambda: assess_chug(0.2, 0.5 * DOC_TAU_C_S, DOC_TAU_C_S),
    lambda: bulk_mode_zero_lag(0.35, tau_c_s=DOC_TAU_C_S),
    lambda: chamber_time_constant(1.0, 1800.0, 1.2),
])
def test_sayisal_alanlar_birim_soneki_tasir(builder):
    """Dondurulmuş sözleşme: her sayısal alan ya SI soneki ya boyutsuz listede.

    F2b/F2c bu sözleşmenin üstüne yazacak; yeni bir sayı sonek taşımadan
    eklenirse bu bekçi kırmızıya düşer (karar 7).
    """
    offenders = [key for key in _numeric_keys(builder())
                 if key not in _DIMENSIONLESS_KEYS
                 and not key.endswith(_UNIT_SUFFIXES)]
    assert not offenders, (
        f'Numeric fields without a SI unit suffix (and not declared '
        f'dimensionless): {sorted(set(offenders))}')


def test_zaman_alanlari_saniye_cinsinden():
    """Sözleşme SI: zaman alanları ``_s``; ms anahtarı YAYIMLANMAZ."""
    result = assess_chug(0.2, 0.5 * DOC_TAU_C_S, DOC_TAU_C_S)
    assert 'tau_c_s' in result and 'tau_c_ms' not in result
    assert result['tau_c_s'] == DOC_TAU_C_S
    assert all(not key.endswith('_ms') for key in result)


def test_chug_gain_sinir_sabiti_turetilmis():
    """J sınırı 1/2'dir: ölçülmüş eşik değil, |cos| ≤ 1'in sonucu."""
    assert CHUG_GAIN_J_MAX == 0.5
    # Sınırın hemen altında nötr çözüm var, üstünde yok.
    assert chug_neutral_tau_ratio(0.49999) > 0.0
    with pytest.raises(ValueError):
        chug_neutral_tau_ratio(0.5)
