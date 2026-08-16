"""Hibrit LFI bekçileri: Karabeyoglu ve ark. (2005) yayımlanmış test tabloları.

Doğrulama merdiveni basamak 5-6 (tasarım belgesi §5).

KAYNAK VE VERİNİN GELDİĞİ YER
-----------------------------
Karabeyoglu, M.A., De Zilwa, S., Cantwell, B., Zilliac, G., "Modeling of
Hybrid Rocket Low Frequency Instabilities", *Journal of Propulsion and Power*
21(6), 2005, ss. 1107-1116 (doi:10.2514/1.7792). Makalenin PDF'i Stanford
AA284A ders materyali dizininden indirildi (md5 4886117b570dcf77e95107ae02319361)
ve tablolar metninden çıkarıldı. Aşağıdaki sayılar **makalenin kendi
tablolarıdır** (İngiliz birimlerinde yayımlanmıştır; burada SI'ya çevrilir):

  Tablo 4  HPDP 11 inç motor testleri (LOX/GOX, HTPB/Escorez), tane boyu 102 in
  Tablo 5  JIRAD / NASA MSFC 11 inç motor testleri (GOX)
  Tablo 6  Arizona State 5 inç N₂O motor testi
  Tablo 7  NASA Ames 10 inç parafin motor testleri (GOX), 25 koşu

İKİ AYRI DOĞRULAMA VAR, KARIŞTIRILMAZ
--------------------------------------
1) **Tablo çaprazı (dar):** makalenin yayımladığı τ_bl2 sütunu bizim
   uygulamamızla YENİDEN hesaplanır. Bu, korelasyonun kendi aritmetiğinin
   birebir doğrulamasıdır; ölçülen sapma Tablo 4/5/6'da ≤ %0,3.
2) **Ölçüme karşı (geniş):** tahmin edilen frekans, motorlarda ÖLÇÜLEN
   frekansla kıyaslanır. Burada makalenin kendi saçılımı geçerlidir (43 test
   için ortalama %13,94 hata, HPDP hariç %10,30, maksimum %41,96). Bekçi bu
   yüzden nokta değil BANT tutar; daha dar bir bekçi kaynağın kendisinden
   fazlasını iddia etmek olurdu.
"""

import math
import statistics

import pytest

from hrma.validation.record_adapters import UNIT_TO_SI
from hrma.stability import (
    LFI_COEFFICIENT,
    LFI_DELAY_CONSTANT_C_PRIME,
    LFI_FREQUENCY_DELAY_COEFFICIENT,
    RT_AV_M2_S2,
    assess_hybrid_lfi,
    boundary_layer_delay_s,
    lfi_frequency_hz,
    rt_av_for_oxidizer,
)
from hrma.stability.hybrid_lfi import (
    LFI_LECTURE_NOTE_COEFFICIENT_REJECTED,
    is_supported_oxidizer,
)

# --- Birim dönüşümleri: depodaki MERKEZÎ tablodan (yeniden yazılmaz) -------
# hrma.validation.record_adapters.UNIT_TO_SI tek kaynaktır (parametre
# tutarlılığı kuralı); burada yalnız türetilmiş bileşik birim kurulur.
IN_M = UNIT_TO_SI['in']                              # inç → m (tam)
PSI_TO_PA = UNIT_TO_SI['psi']                        # psi → Pa
LB_IN2_S = UNIT_TO_SI['lb'] / UNIT_TO_SI['in2']      # lb/(in²·s) → kg/(m²·s)

RT_GOX = RT_AV_M2_S2['gox']
RT_N2O = RT_AV_M2_S2['n2o']

# --- Tablo 4: HPDP (tane boyu 102 in; G_o ve G_t yayımlı) ------------------
# (etiket, L[in], G_o[lb/in²s], G_t[lb/in²s], P_c[psi], O/F, f_ölçülen[Hz],
#  τ_bl2_yayımlanan[ms])
TABLE4_HPDP = [
    ('1 (GOX)', 102, 0.423, 0.571, 600, 2.85, 13.0, 49.3),
    ('2 (GOX)', 102, 0.402, 0.541, 550, 2.89, 8.0, 47.6),
    ('7 (GOX)', 102, 0.339, 0.458, 440, 2.89, 15.0, 45.1),
    ('1 (LOX)', 102, 0.222, 0.310, 435, 2.51, 8.0, 66.8),
]
# NOT: Tablo 4'ün 8 numaralı koşusu P_c'yi "260/280 psi" aralığı olarak
# yayımlar; tek bir basınç UYDURMAMAK için o satır alınmadı.

# --- Tablo 5: JIRAD / NASA MSFC (ölçülen frekans çoğu satırda BANT) --------
TABLE5_JIRAD = [
    ('3', 102, 0.38, 0.527, 745, 2.6, (6.0, 10.0), 67.1),
    ('4', 102, 0.23, 0.325, 325, 2.4, (10.0, 20.0), 47.8),
    ('6', 102, 0.78, 1.024, 750, 3.2, (10.0, 15.0), 34.0),
    ('7', 102, 0.15, 0.220, 335, 2.1, (6.0, 15.0), 73.9),
    ('8', 102, 0.15, 0.209, 850, 2.6, (2.0, 5.0), 193.4),
    ('9', 102, 0.28, 0.392, 215, 2.6, (6.0, 20.0), 26.1),
    ('15', 108, 0.45, 0.599, 1025, 3.0, 4.0, 84.5),      # tek değer
    ('10', 102, 0.20, 0.278, 215, 2.6, (10.0, 25.0), 36.7),
]

# --- Tablo 6: Arizona State, N₂O ------------------------------------------
TABLE6_ASU = ('Test 1', 27, 0.29, 500, 4.0, 19.0, 23.7)

# --- Tablo 7: NASA Ames parafin (L, G_o, P_c, O/F, f_ölçülen, τ_bl2) -------
TABLE7_AMES = [
    ('4F-4', 32, 0.44, 528.0, 3.97, 41.6, 13.6),
    ('4F-5', 32, 0.49, 551.0, 3.59, 39.9, 12.8),
    ('4F-1b', 32, 0.20, 561.0, 2.72, 14.4, 30.0),
    ('4F1-c', 32, 0.16, 542.0, 3.06, 13.6, 36.4),
    ('4P-01', 45, 0.39, 318.0, 2.69, 40.8, 12.4),
    ('4P-02', 45, 0.38, 993.8, 2.48, 13.2, 38.9),
    ('4P-03', 45, 0.40, 939.1, 2.65, 14.4, 35.9),
    ('4L-03', 45, 0.31, 641.6, 2.69, 12.7, 31.2),
    ('4L-04', 45, 0.52, 656.7, 2.66, 23.6, 19.0),
    ('4L-05', 45, 0.46, 649.3, 2.72, 19.1, 21.4),
    ('4L-08', 45, 0.44, 525.0, 2.64, 23.3, 18.0),
    ('4I-01', 45, 0.38, 318.7, 2.40, 39.6, 12.5),
    ('4P-04', 45, 0.21, 159.1, 1.73, 42.4, 10.8),
    ('4L-09', 45, 0.26, 265.3, 1.54, 20.3, 13.8),   # makalenin kendi aykırısı
    ('4L-10', 45, 0.43, 590.0, 2.89, 27.0, 18.4),   # τ sütunu iç tutarsız
    ('4L-11', 45, 0.11, 213.0, 1.56, 17.8, 27.5),
    ('4L-12', 45, 0.13, 301.0, 2.01, 15.54, 32.5),
    ('4NF-01', 45, 0.39, 602.2, 2.77, 22.60, 23.3),
    ('4NF-02', 45, 0.22, 600.4, 2.34, 11.10, 40.7),
    ('4NF-03', 45, 0.36, 500.8, 2.96, 23.20, 21.6),
    ('4NF-04', 45, 0.48, 568.5, 3.01, 32.75, 18.2),
    ('4L-14', 45, 0.43, 524.5, 2.51, 25.15, 18.2),
    ('4ST-02', 45, 0.45, 540.0, 2.71, 24.86, 18.3),
    ('4L-15', 45, 0.31, 555.5, 2.09, 14.94, 26.4),
    ('4Rep-02', 45, 0.45, 402.3, 2.63, 36.49, 13.6),
]


def _ames_prediction(row):
    """Tablo 7 satırından (τ_bl2 [s], f [Hz]) — O/F yolu (Denk. 12/15)."""
    _, length_in, flux, pressure_psi, of_ratio, _, _ = row
    args = (length_in * IN_M, pressure_psi * PSI_TO_PA, flux * LB_IN2_S, RT_GOX)
    return (boundary_layer_delay_s(*args, of_ratio=of_ratio),
            lfi_frequency_hz(*args, of_ratio=of_ratio))


def _total_flux_prediction(length_in, flux_o, flux_t, pressure_psi, rt=RT_GOX):
    """G_o + G_t yolu (Denk. 11) — Tablo 4/5 satırları için."""
    args = (length_in * IN_M, pressure_psi * PSI_TO_PA, flux_o * LB_IN2_S, rt)
    return (boundary_layer_delay_s(*args,
                                   total_flux_kg_m2_s=flux_t * LB_IN2_S),
            lfi_frequency_hz(*args, total_flux_kg_m2_s=flux_t * LB_IN2_S))


# ===========================================================================
# 1) Yayımlanan τ_bl2 sütununun yeniden hesabı (dar çapraz)
# ===========================================================================
@pytest.mark.parametrize('row', TABLE4_HPDP, ids=lambda r: f'HPDP-{r[0]}')
def test_hpdp_gecikme_sutunu_yeniden_hesaplanir(row):
    """Tablo 4'ün τ_bl2 sütunu Denk. (11) ile ≤ %0,5 içinde geri gelir."""
    _, length, flux_o, flux_t, pressure, _, _, tau_published_ms = row
    tau_s, _ = _total_flux_prediction(length, flux_o, flux_t, pressure)
    assert tau_s * 1e3 == pytest.approx(tau_published_ms, rel=5e-3)


@pytest.mark.parametrize('row', TABLE5_JIRAD, ids=lambda r: f'JIRAD-{r[0]}')
def test_jirad_gecikme_sutunu_yeniden_hesaplanir(row):
    _, length, flux_o, flux_t, pressure, _, _, tau_published_ms = row
    tau_s, _ = _total_flux_prediction(length, flux_o, flux_t, pressure)
    assert tau_s * 1e3 == pytest.approx(tau_published_ms, rel=5e-3)


def test_asu_n2o_gecikme_sutunu_yeniden_hesaplanir():
    """N₂O vakası: R·T_av = 4,47e5 kapısıyla τ_bl2 = 23,7 ms geri gelir."""
    _, length, flux, pressure, of_ratio, _, tau_published_ms = TABLE6_ASU
    tau_s = boundary_layer_delay_s(length * IN_M, pressure * PSI_TO_PA,
                                   flux * LB_IN2_S, RT_N2O,
                                   of_ratio=of_ratio)
    assert tau_s * 1e3 == pytest.approx(tau_published_ms, rel=5e-3)


def test_ames_gecikme_sutunu_yeniden_hesaplanir():
    """Tablo 7: 25 satırın 24'ü ≤ %4; 4L-10 tablonun KENDİ tutarsızlığı.

    Bu bekçi iki şeyi birden kilitler: (a) uygulamamız yayımlanan sütunu
    üretiyor, (b) tek aykırı satırın hangisi olduğu ölçülmüş ve adıyla
    kayıtlı — formül değişirse aykırıların sayısı artar ve bekçi kırmızıya
    düşer.
    """
    deviations = {}
    for row in TABLE7_AMES:
        tau_s, _ = _ames_prediction(row)
        deviations[row[0]] = abs(tau_s * 1e3 - row[6]) / row[6] * 100.0
    outliers = sorted(k for k, v in deviations.items() if v > 4.0)
    assert outliers == ['4L-10'], (
        f'Unexpected delay-column outliers: {outliers} '
        f'(deviations: {deviations})')
    assert deviations['4L-10'] == pytest.approx(14.5, abs=1.0)
    others = [v for k, v in deviations.items() if k != '4L-10']
    assert statistics.mean(others) < 2.0


# ===========================================================================
# 2) Ölçülen frekansa karşı (makalenin kendi saçılım bandı)
# ===========================================================================
def test_ames_frekanslari_makalenin_sacilim_bandinda():
    """NASA seti: 4L-09 hariç ortalama |hata| ≤ %12 (makale: %8,61).

    Makale 4L-09'u AÇIKÇA aykırı ilan eder ("clearly is an outlier"); bekçi
    onu ayrı tutar ve gerçekten aykırı KALDIĞINI da kontrol eder — yani
    modelimiz makalenin kendi aykırısını da yeniden üretir.
    """
    errors = {}
    for row in TABLE7_AMES:
        _, frequency = _ames_prediction(row)
        errors[row[0]] = abs(frequency - row[5]) / row[5] * 100.0
    without_outlier = [v for k, v in errors.items() if k != '4L-09']
    assert statistics.mean(without_outlier) < 12.0
    assert errors['4L-09'] > 40.0
    assert max(without_outlier) < 30.0


@pytest.mark.parametrize('row', [r for r in TABLE5_JIRAD
                                 if isinstance(r[6], tuple)],
                         ids=lambda r: f'JIRAD-{r[0]}')
def test_jirad_bant_olcumlerinin_icine_duser(row):
    """Ölçülen frekansın BANT olarak yayımlandığı satırlarda tahmin bandın içinde."""
    _, length, flux_o, flux_t, pressure, _, band, _ = row
    _, frequency = _total_flux_prediction(length, flux_o, flux_t, pressure)
    assert band[0] <= frequency <= band[1], (
        f'{frequency:.2f} Hz outside published measured band {band}')


def test_asu_n2o_frekansi_olcume_yakin():
    """N₂O testi: ölçülen 19 Hz, tahmin %10 içinde (ölçüldü: %6,9)."""
    _, length, flux, pressure, of_ratio, f_measured, _ = TABLE6_ASU
    frequency = lfi_frequency_hz(length * IN_M, pressure * PSI_TO_PA,
                                 flux * LB_IN2_S, RT_N2O, of_ratio=of_ratio)
    assert frequency == pytest.approx(f_measured, rel=0.10)


def test_hpdp_seti_en_kotu_set_olarak_kalir():
    """Makale HPDP'yi en güvenilmez set ilan eder (%29,68); ölçüm o mertebede.

    Bu bir KAYITTIR: modelimiz kaynağın hata dağılımını yeniden üretiyor mu?
    """
    errors = []
    for _, length, flux_o, flux_t, pressure, _, measured, _ in TABLE4_HPDP:
        _, frequency = _total_flux_prediction(length, flux_o, flux_t, pressure)
        errors.append(abs(frequency - measured) / measured * 100.0)
    assert 15.0 < statistics.mean(errors) < 35.0


# ===========================================================================
# 3) Formülasyonun iç tutarlılığı: iki yol, tek grup
# ===========================================================================
@pytest.mark.parametrize('row', TABLE4_HPDP + TABLE5_JIRAD,
                         ids=lambda r: f'Gt-{r[0]}')
def test_toplam_aki_ozdesligi_yayimlanan_sutunlarla(row):
    """G_o + G_t = G_o·(2 + 1/(O/F)) — yayımlanan üç sütunla doğrulanır."""
    _, _, flux_o, flux_t, _, of_ratio, _, _ = row
    assert flux_o + flux_t == pytest.approx(flux_o * (2.0 + 1.0 / of_ratio),
                                            rel=0.02)


def test_iki_yol_ayni_frekansi_verir():
    """Denk. (11) ve Denk. (12) yolları aynı sayıyı üretir (tutarlı girdiyle)."""
    flux_o, of_ratio = 0.4 * LB_IN2_S, 2.7
    flux_t = flux_o * (1.0 + 1.0 / of_ratio)
    length, pressure = 45 * IN_M, 600.0 * PSI_TO_PA
    via_of = lfi_frequency_hz(length, pressure, flux_o, RT_GOX,
                              of_ratio=of_ratio)
    via_total = lfi_frequency_hz(length, pressure, flux_o, RT_GOX,
                                 total_flux_kg_m2_s=flux_t)
    assert via_of == pytest.approx(via_total, rel=1e-12)


def test_iki_yoldan_biri_secilmeli():
    """İkisi birden ya da hiçbiri verilirse reddedilir (belirsizlik yasağı)."""
    args = (45 * IN_M, 600.0 * PSI_TO_PA, 0.4 * LB_IN2_S, RT_GOX)
    with pytest.raises(ValueError, match='exactly one'):
        lfi_frequency_hz(*args)
    with pytest.raises(ValueError, match='exactly one'):
        lfi_frequency_hz(*args, of_ratio=2.7, total_flux_kg_m2_s=1.0)


def test_frekans_gecikme_ozdesligi():
    """f = 0,48/τ_bl2 (Denk. 7) ile Denk. (15) arasındaki fark SADECE yuvarlama.

    Makale katsayıyı 0,2341 diye YUVARLAYARAK yayımlar; 0,48/2,050 = 0,234146.
    İki yol bu yüzden bit-özdeş DEĞİL, %0,02 farklıdır — bu fark ölçülür ve
    kayda geçer (bit-özdeşlik iddia etmek kaynağın yapmadığı bir iddia olurdu).
    """
    rounding = abs(LFI_FREQUENCY_DELAY_COEFFICIENT
                   / LFI_DELAY_CONSTANT_C_PRIME - LFI_COEFFICIENT)
    assert rounding / LFI_COEFFICIENT == pytest.approx(2.0e-4, abs=5e-5)
    for row in TABLE7_AMES:
        tau_s, frequency = _ames_prediction(row)
        assert frequency == pytest.approx(
            LFI_FREQUENCY_DELAY_COEFFICIENT / tau_s, rel=3e-4)


def test_olcekleme_yonleri():
    """Yön bekçisi: f ∝ G_o, f ∝ 1/L, f ∝ 1/P_c (Denk. 15'in yapısı)."""
    base = dict(grain_length_m=1.143, chamber_pressure_Pa=4.4e6,
                oxidizer_flux_kg_m2_s=220.0, rt_av_m2_s2=RT_GOX,
                of_ratio=2.7)
    f0 = lfi_frequency_hz(**base)
    assert lfi_frequency_hz(**{**base, 'oxidizer_flux_kg_m2_s': 440.0}) == (
        pytest.approx(2.0 * f0, rel=1e-12))
    assert lfi_frequency_hz(**{**base, 'grain_length_m': 2.286}) == (
        pytest.approx(0.5 * f0, rel=1e-12))
    assert lfi_frequency_hz(**{**base, 'chamber_pressure_Pa': 8.8e6}) == (
        pytest.approx(0.5 * f0, rel=1e-12))


# ===========================================================================
# 4) Katsayı çelişkisi bekçisi (basamak 6)
# ===========================================================================
def test_hakemli_katsayi_kullanilir_ders_notu_katsayisi_kullanilmaz():
    """0,2341 = 0,48/2,050 özdeşliği; 0,119 KULLANILMAZ ve c' 4,03 isterdi."""
    assert LFI_COEFFICIENT == 0.2341
    assert LFI_DELAY_CONSTANT_C_PRIME == 2.050
    assert (LFI_FREQUENCY_DELAY_COEFFICIENT / LFI_DELAY_CONSTANT_C_PRIME
            == pytest.approx(LFI_COEFFICIENT, rel=5e-4))
    # Ders notu katsayısının gerektireceği c' makalenin uyumuyla çelişir.
    implied_c_prime = (LFI_FREQUENCY_DELAY_COEFFICIENT
                       / LFI_LECTURE_NOTE_COEFFICIENT_REJECTED)
    assert implied_c_prime == pytest.approx(4.03, abs=0.02)
    assert (LFI_COEFFICIENT / LFI_LECTURE_NOTE_COEFFICIENT_REJECTED
            == pytest.approx(1.967, abs=0.01))


def test_ders_notu_katsayisi_kullanilsaydi_capraz_kirilirdi():
    """Mutasyon kanıtının test içi ikizi: 0,119 ile ortalama hata patlar."""
    errors_rejected = []
    for row in TABLE7_AMES:
        _, length_in, flux, pressure_psi, of_ratio, measured, _ = row
        group = flux * LB_IN2_S * (2.0 + 1.0 / of_ratio)
        f_rejected = (LFI_LECTURE_NOTE_COEFFICIENT_REJECTED * group * RT_GOX
                      / (length_in * IN_M * pressure_psi * PSI_TO_PA))
        errors_rejected.append(abs(f_rejected - measured) / measured * 100.0)
    assert statistics.mean(errors_rejected) > 45.0


def test_katsayi_celiskisi_kunyede_adiyla_gecer():
    result = _typical_assessment()
    basis = result['model_basis']
    assert '0.2341' in basis and '0.119' in basis
    assert 'AA284a' in basis and 'peer-reviewed' in basis
    assert '2.050' in basis


# ===========================================================================
# 5) R·T kapısı ve TANI üçlüsü (karar 2)
# ===========================================================================
def _typical_assessment(**overrides):
    args = dict(oxidizer_type='gox', grain_length_m=45 * IN_M,
                chamber_pressure_Pa=641.6 * PSI_TO_PA,
                oxidizer_flux_kg_m2_s=0.31 * LB_IN2_S, of_ratio=2.69,
                rt_thermo_m2_s2=1.328e6,
                acoustic_first_longitudinal_hz=370.0)
    args.update(overrides)
    return assess_hybrid_lfi(**args)


def test_rt_kapisi_yayimlanan_iki_aile():
    assert rt_av_for_oxidizer('GOX')['rt_corr_m2_s2'] == 6.38e5
    assert rt_av_for_oxidizer('lox')['rt_corr_m2_s2'] == 6.38e5
    assert rt_av_for_oxidizer(' N2O ')['rt_corr_m2_s2'] == 4.47e5


@pytest.mark.parametrize('oxidizer', ['h2o2', 'n2o4', 'nytrox', 'air', '',
                                      None, 'nitrous oxide'])
def test_desteklenmeyen_oksitleyici_uydurulmaz(oxidizer):
    """Kalibre sabiti olmayan aileye sabit ATANMAZ; takma ad eşlemesi de yok.

    'nitrous oxide' bilerek reddedilir: sessiz eşleme, 'nytrox' gibi
    karışımların yanlış aileye düşmesine kapı açar.
    """
    assert is_supported_oxidizer(oxidizer) is False
    with pytest.raises(ValueError):
        rt_av_for_oxidizer(oxidizer)
    with pytest.raises(ValueError):
        _typical_assessment(oxidizer_type=oxidizer)


def test_rt_uclusu_ve_tani_etiketi():
    """RT_corr / RT_thermo / oran üçlüsü + ZORUNLU etiket aynen yayımlanır."""
    result = _typical_assessment()
    assert result['rt_corr_m2_s2'] == 6.38e5
    assert result['rt_thermo_m2_s2'] == 1.328e6
    assert result['rt_ratio'] == pytest.approx(1.328e6 / 6.38e5, rel=1e-12)
    assert (result['rt_ratio_label']
            == 'diagnostic only — not substituted into correlation')
    assert result['rt_gate'] == 'gox'


def test_rt_thermo_verilmezse_oran_uydurulmaz():
    result = _typical_assessment(rt_thermo_m2_s2=None)
    assert result['rt_thermo_m2_s2'] is None
    assert result['rt_ratio'] is None
    # Frekans, tanı değerinden BAĞIMSIZ olmalı (korelasyona girmiyor).
    assert result['frequency_hz'] == pytest.approx(
        _typical_assessment()['frequency_hz'], rel=1e-15)


def test_cozucunun_rt_si_korelasyona_konsaydi_capraz_kirilirdi():
    """Karar 2'nin ölçülmüş gerekçesi: RT_thermo konursa hata ~2× kayar."""
    errors_thermo = []
    for row in TABLE7_AMES:
        _, length_in, flux, pressure_psi, of_ratio, measured, _ = row
        f_thermo = lfi_frequency_hz(length_in * IN_M, pressure_psi * PSI_TO_PA,
                                    flux * LB_IN2_S, 1.328e6,
                                    of_ratio=of_ratio)
        errors_thermo.append(abs(f_thermo - measured) / measured * 100.0)
    assert statistics.mean(errors_thermo) > 90.0


# ===========================================================================
# 6) Hüküm sözleşmesi (karar 1) ve beyanlar
# ===========================================================================
def test_lfi_hukmu_kapsam_etiketli_ve_asla_temize_cikarmaz():
    """LFI hükmü 'stable' OLAMAZ: korelasyon şiddeti değil, varlığı söyler."""
    result = _typical_assessment()
    assert result['verdict'] == 'marginal'
    assert result['verdict'] != 'stable'
    scope = result['verdict_scope']
    assert 'hybrid low-frequency' in scope
    assert 'amplitude NOT modelled' in scope
    assert 'conclusion 4' in result['verdict_basis']


def test_genlik_modellenmedigi_beyanli():
    result = _typical_assessment()
    assert 'oscillation_amplitude' in result['not_modelled']
    assert 'unbounded growth' in result['not_modelled']['oscillation_amplitude']


def test_akustik_ayrisma_beyani():
    """1L verilirse ayrışma (decade) yayımlanır; eşik/hüküm bağlanmaz."""
    result = _typical_assessment()
    separation = result['acoustic_separation']
    assert separation['acoustic_first_longitudinal_hz'] == 370.0
    assert separation['separation_decades'] == pytest.approx(
        math.log10(370.0 / result['frequency_hz']), rel=1e-12)
    assert 'no threshold is attached' in separation['separation_basis']
    assert 'verdict' not in separation


def test_1l_verilmezse_ayrisma_uydurulmaz():
    result = _typical_assessment(acoustic_first_longitudinal_hz=None)
    assert result['acoustic_separation'] is None


def test_girdiler_yankilanir_ve_eksik_girdi_reddedilir():
    result = _typical_assessment()
    assert result['inputs']['oxidizer_type'] == 'gox'
    assert result['inputs']['of_ratio'] == 2.69
    for bad in ({'grain_length_m': 0.0}, {'chamber_pressure_Pa': -1.0},
                {'oxidizer_flux_kg_m2_s': None}, {'of_ratio': 0.0}):
        with pytest.raises(ValueError):
            _typical_assessment(**bad)


def test_yayimlanan_bir_kosunun_tam_raporu():
    """4L-05 (makalenin Şekil 11-12'de gösterdiği koşu) uçtan uca."""
    result = assess_hybrid_lfi('gox', 45 * IN_M, 649.3 * PSI_TO_PA,
                               0.46 * LB_IN2_S, of_ratio=2.72)
    assert result['boundary_layer_delay_s'] * 1e3 == pytest.approx(21.4,
                                                                   rel=0.02)
    assert result['frequency_hz'] == pytest.approx(19.1, rel=0.20)
    assert result['coefficient'] == 0.2341
    assert result['rt_gate'] == 'gox'
