# hrma/stability/hybrid_lfi.py — hibrit alçak frekans kararsızlığı (LFI)
"""Hibrit LFI: Karabeyoglu ve ark. (2005) TCG-kuplajlı ölçekleme yasası.

KÜNYE (birincil kaynak bu tur indirilip metni çıkarıldı)
--------------------------------------------------------
Karabeyoglu, M.A., De Zilwa, S., Cantwell, B., Zilliac, G., "Modeling of
Hybrid Rocket Low Frequency Instabilities", *Journal of Propulsion and Power*
21(6), 2005, ss. 1107-1116 (doi:10.2514/1.7792). Denklem numaraları makalenin
kendi numaralandırmasıdır:

    (7)   f = 0,48/τ_bl2
    (11)  τ_bl2 = c'·L·P_c/((G_o + G_t)·R·T_av)
    (12)  τ_bl2 = c'·L·P_c/((2 + 1/(O/F))·G_o·R·T_av)
    (14b) f = 0,48·(2 + 1/(O/F))·G_o·R·T_av/(c'·L·P_c)
    (15)  f = 0,2341·(2 + 1/(O/F))·G_o·R·T_av/(L·P_c)     ← "universal scaling law"
          R·T_av = 6,38×10⁵ (m/s)²  GOX/LOX sistemleri
          R·T_av = 4,47×10⁵ (m/s)²  düşük enerjili oksitleyiciler (N₂O)

G_t makalede TOPLAM akıdır: O/F = G_o/G_f olduğundan
G_o + G_t = G_o·(2 + 1/(O/F)) — Denk. (11) ile (12) bu özdeşlikle aynıdır
(bekçili: yayımlanan tablolarda G_o, G_t ve O/F sütunları birlikte veriliyor).

KATSAYI ÇELİŞKİSİ (ölçüldü, beyanla taşınır)
--------------------------------------------
Aynı yazarın Stanford ders notu (AA284a Ders 14, s. 29) aynı yasayı
``f = 0,119·(…)`` katsayısıyla yazar; hakemli makale ``0,2341`` der. Makale
kendi uyum sabitini de yayımlar: c' = 2,050 (s. 1115) ve 0,48/2,050 = 0,23415
— yani **0,2341 makalenin kendi c'siyle tutarlıdır**, 0,119 ise c' = 4,03
isterdi ve bu hem makalenin 2,050'siyle hem ders notunun kendi beyan ettiği
c' = 2,01 ile çelişir. Oran 0,2341/0,119 = 1,967. **Karar: hakemli makalenin
0,2341'i kullanılır**; ders notu katsayısı kullanılmaz ve bu çelişki burada
adıyla beyan edilir (aksi hâlde ileride yeniden açılır).

R·T_av KARARI (karar 2)
-----------------------
``R·T_av`` korelasyonun **kalibre edilmiş** port ortalamasıdır (43 motor
testine uydurulmuştur), çözücünün denge kamara değeri DEĞİLDİR. Makale bunu
açıkça söyler: "any error in RTav will only effect the numerical value of the
empirical delay constant c'" — yani sabit ile c' birlikte kalibre edilmiştir;
birini motor değeriyle değiştirmek kalibrasyonu bozar. Çözücünün kendi
``R·T_c``'si YALNIZCA tanı amaçlı, yan yana yayımlanır (üçlü: ``rt_corr``,
``rt_thermo``, ``rt_ratio`` + açık etiket).

DESTEKLENEN OKSİTLEYİCİLER
--------------------------
Makale sabitini yalnız iki aile için verir: LOX/GOX ve N₂O sınıfı düşük
enerjili oksitleyiciler. H₂O₂, N₂O₄, nytrox vb. için sabit YOKTUR ve
UYDURULMAZ: çağrı ``ValueError`` ile reddedilir (F2b bunu NOT_EVALUATED
satırına çevirir).
"""

import math

from hrma.stability import (
    STABILITY_NOT_MODELLED,
    VERDICT_MARGINAL,
    make_verdict,
)
from hrma.stability.chamber import _positive

__all__ = [
    'RT_AV_M2_S2',
    'RT_AV_SOURCE',
    'LFI_COEFFICIENT',
    'LFI_FREQUENCY_DELAY_COEFFICIENT',
    'LFI_FREQUENCY_PATHS_REL_DIFF',
    'LFI_FREQUENCY_PATHS_IDENTITY_TOL_REL',
    'frekans_yollari_ozdeslik_kapisi',
    'LFI_DELAY_CONSTANT_C_PRIME',
    'LFI_LECTURE_NOTE_COEFFICIENT_REJECTED',
    'LFI_COEFFICIENT_FROM_DELAY',
    'LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL',
    'LFI_COEFFICIENT_IDENTITY_TOL_REL',
    'LFI_COEFFICIENT_PRINTED_DECIMALS',
    'is_supported_oxidizer',
    'rt_av_for_oxidizer',
    'boundary_layer_delay_s',
    'lfi_frequency_hz',
    'assess_hybrid_lfi',
]

# ---------------------------------------------------------------------------
# Korelasyonun KALİBRE sabitleri — tek kaynak, künyeli (Karabeyoglu ve ark.,
# JPP 21(6), 2005). Bu sayılar motor çözücüsünün termodinamiğinden GELMEZ.
# ---------------------------------------------------------------------------
RT_AV_M2_S2 = {
    'gox': 6.38e5,
    'lox': 6.38e5,
    'n2o': 4.47e5,
}
RT_AV_SOURCE = (
    'Calibrated port-average gas constant-temperature product of the '
    'correlation (Karabeyoglu, De Zilwa, Cantwell & Zilliac, "Modeling of '
    'Hybrid Rocket Low Frequency Instabilities", J. Propulsion and Power '
    '21(6), 2005, Eq. 15): 6.38e5 (m/s)^2 for GOX/LOX systems and 4.47e5 '
    '(m/s)^2 for low-energy oxidizers such as N2O. The paper states the value '
    'is fitted TOGETHER with the delay constant c\' ("any error in RTav will '
    'only effect the numerical value of the empirical delay constant"), so '
    'substituting a solver R*T would break the calibration.')

LFI_COEFFICIENT = 0.2341                 # Denk. 15 evrensel ölçekleme katsayısı
LFI_FREQUENCY_DELAY_COEFFICIENT = 0.48   # Denk. 7: f = 0,48/τ_bl2
LFI_DELAY_CONSTANT_C_PRIME = 2.050       # s. 1115: 43 teste uydurulmuş c'
# Ders notu (AA284a Ders 14, s. 29) katsayısı — KULLANILMAZ, yalnız çelişki
# beyanı ve bekçisi için burada adıyla durur.
LFI_LECTURE_NOTE_COEFFICIENT_REJECTED = 0.119

# --- P6B4-10: KATSAYI ÖZDEŞLİĞİ ARTIK HESAPLANIYOR --------------------------
# Ürün yüzü eskiden "0.2341 = 0.48/2.05" diye TAM EŞİTLİK yayımlıyordu;
# ölçülen bölüm 0,23414634146341465 olduğu için bu eşitlik YANLIŞTI (bağıl
# fark 1,979e-04) ve aynı yanlışlık iki YAYIMLANAN frekans yoluna sızıyordu
# (Denk. 15 ⟷ Denk. 7: 12,4463 ⟷ 12,4488 Hz). İki sayı da makalenin kendi
# sayısıdır ve biri ötekinden TÜRETİLEMEZ (0,2341, Denk. 15'te 4 ondalıkla
# BASILI hâliyle alıntılanır); dolayısıyla "tek kaynağa indir" çözümü
# literatürü tahrif ederdi. Doğru çözüm: bağıntıyı METİN olmaktan çıkarıp
# ÖLÇÜLEN bir büyüklüğe bağlamak ve basım yuvarlamasının izin verdiği
# aralığı kapı yapmak.
LFI_COEFFICIENT_FROM_DELAY = (LFI_FREQUENCY_DELAY_COEFFICIENT
                              / LFI_DELAY_CONSTANT_C_PRIME)
LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL = (
    abs(LFI_COEFFICIENT - LFI_COEFFICIENT_FROM_DELAY)
    / LFI_COEFFICIENT_FROM_DELAY)
#: Denk. 15'in katsayısı makalede 4 ONDALIKLA basılıdır; basım yuvarlamasının
#: yarım-birimi 5e-5 mutlak, yani 5e-5/0,23415 = 2,1354e-04 bağıldır. Özdeşlik
#: ancak bu aralıkta "aynı sayının iki basımı" sayılabilir.
LFI_COEFFICIENT_PRINTED_DECIMALS = 4
LFI_COEFFICIENT_IDENTITY_TOL_REL = (
    0.5 * 10.0 ** (-LFI_COEFFICIENT_PRINTED_DECIMALS)
    / LFI_COEFFICIENT_FROM_DELAY)
if LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL > LFI_COEFFICIENT_IDENTITY_TOL_REL:
    # FAIL-CLOSED: sabitlerden biri değişip bağıntı basım yuvarlamasının
    # dışına çıkarsa modül yanlış bir özdeşlik YAYIMLAMAK yerine yüklenmez.
    raise ValueError(
        'hrma.stability.hybrid_lfi: the published coefficient identity is '
        f'broken: LFI_COEFFICIENT = {LFI_COEFFICIENT!r} but '
        f'LFI_FREQUENCY_DELAY_COEFFICIENT/LFI_DELAY_CONSTANT_C_PRIME = '
        f'{LFI_COEFFICIENT_FROM_DELAY!r} (relative residual '
        f'{LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL:.6g} > printing tolerance '
        f'{LFI_COEFFICIENT_IDENTITY_TOL_REL:.6g}). Eq. 15 and Eq. 7+Eq. 12 '
        'would then be two DIFFERENT models, not two printings of one; no '
        'identity is published on top of that.')

#: --- OH-Z5-02 (ÖH D28): İKİ FREKANS YOLUNUN FARKI TEK KAYNAKTAN ---------
#: ``frequency_paths_rel_diff`` yaprağı D25'ten beri "uydurma sabit"
#: bekçisinin (``tests/test_field_wiring_layer_b.py::
#: test_no_fabricated_constant_outputs``) listesinde KALAN TEK yapraktı.
#: Hüküm ÖLÇÜLEREK verildi (kanıt ``docs/scofield/raw/OH/D28/fea-cfd/a1/
#: once_z502.json``): yaprak TANIM GEREĞİ sabittir, çünkü
#:
#:   f·τ = (K·(G_o+G_t)·R·T_av/(L·P_c)) · (c'·L·P_c/((G_o+G_t)·R·T_av))
#:       = K·c'                                    (girdi SADELEŞİR)
#:
#: ve dolayısıyla
#:
#:   |f·τ/0,48 − 1| = |K·c'/0,48 − 1| = |K − 0,48/c'| / (0,48/c')
#:                  = LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL.
#:
#: Boyut analizi: [f]=s⁻¹, [τ]=s ⇒ f·τ boyutsuz; 0,48 (Denk. 7) da f·τ
#: boyutunda, yani oran ve çıkarma boyutsuz — tutar.
#:
#: Yaprak yalnız sabit DEĞİL, aynı zamanda YANLIŞTI: satır içi float yolu
#: (``frequency*delay/0.48 - 1``) beş işletme noktasında ÜÇ FARKLI sayı
#: veriyordu (1,97916666666464e-04 / 1,97916666666686e-04 /
#: 1,97916666666798e-04) ve hiçbiri, ürünün AYNI SÖZLÜKTE yayımladığı
#: ``coefficient_identity_residual_rel`` = 1,97916666666714e-04 ile
#: bit-aynı değildi. Yani ürün tek bir büyüklüğü İKİ SAYI olarak basıyor,
#: üstelik yaprağın kendi künyesi ("They differ by EXACTLY the printing
#: residual of the coefficient") bu iki sayının aynı olduğunu SÖYLÜYORDU.
#: Oynayan şey ölçüm değil son bitlerdeki yuvarlama gürültüsüydü
#: (yayılım ≈ 1,7e-13 bağıl, platform float sözleşmesinin 1e-12 gürültü
#: tabanının ALTINDA). TEK KAYNAK kuralı (Berke doktrini 4): büyüklük bir
#: kez hesaplanır, iki ad aynı sayıyı basar.
LFI_FREQUENCY_PATHS_REL_DIFF = LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL

#: Özdeşliğin İŞLETME NOKTASINDA hâlâ tuttuğunu ölçen kapının bandı.
#: Sabit yaprağın "meşru" sayılabilmesinin tek şartı, onu doğuran cebirsel
#: özdeşliğin gerçekten yürürlükte olmasıdır; bu yüzden sabitlik bir İDDİA
#: olarak bırakılmaz, her koşumda ÖLÇÜLÜR (``frekans_yollari_ozdeslik_kapisi``).
#: Band ölçümden türedi: f·τ/(K·c') − 1 sapması beş işletme noktasında
#: |·| ≤ 2,3e-16 (çift duyarlıklı yuvarlama); gerçek bir kopma — Denk. 15
#: ya da Denk. 11/12 katsayısının değişmesi, kırpma, ikinci bir model —
#: 1e-4 mertebesindedir. 1e-9 iki mertebeler arasında güvenli aralıktır:
#: gürültünün 4e6 katı, gerçek kopmanın 1e5'te biri.
LFI_FREQUENCY_PATHS_IDENTITY_TOL_REL = 1e-9

LFI_COEFFICIENT_BASIS = (
    'f = 0.2341*(2 + 1/(O/F))*Go*R*Tav/(L*Pc), the universal scaling law of '
    'Karabeyoglu et al., JPP 21(6), 2005, Eq. 15, fitted to 43 motor tests '
    'from four programmes (AMROC, HPDP, JIRAD/MSFC, NASA Ames) with three '
    'oxidizers. CONFLICTING SOURCE, declared on purpose: the same author\'s '
    'Stanford lecture notes (AA284a Lecture 14, p. 29) write the same law '
    'with 0.119; the peer-reviewed coefficient 0.2341 is used here because it '
    'is the one consistent with the paper\'s own fitted delay constant '
    'c\' = 2.050 (0.48/2.050 = 0.23415), whereas 0.119 would require '
    'c\' = 4.03. The ratio between the two published coefficients is 1.967.')

_SUPPORTED_NOTE = (
    "supported oxidizer families: 'gox'/'lox' (6.38e5) and 'n2o' (4.47e5). "
    'The correlation publishes no calibrated constant for any other '
    'oxidizer, and none is fabricated here.')


def _normalise_oxidizer(oxidizer_type):
    """Oksitleyici adını sadeleştirir (kırpma + küçük harf); eşleme YOK.

    Bilinçli olarak takma ad tablosu tutulmaz: 'nytrox' gibi karışımlar
    sessizce N₂O'ya eşlenirse kalibre sabit yanlış aileye uygulanır.
    """
    if not isinstance(oxidizer_type, str) or not oxidizer_type.strip():
        raise ValueError(
            f'oxidizer_type must be a non-empty string ({_SUPPORTED_NOTE}); '
            f'got {oxidizer_type!r}.')
    return oxidizer_type.strip().lower()


def is_supported_oxidizer(oxidizer_type):
    """Korelasyonun kalibre sabitine sahip bir aile mi? (F2b kapısı)."""
    try:
        return _normalise_oxidizer(oxidizer_type) in RT_AV_M2_S2
    except ValueError:
        return False


def rt_av_for_oxidizer(oxidizer_type):
    """Kalibre R·T_av [(m/s)²] + kapı anahtarı (desteklenmeyen → ValueError)."""
    key = _normalise_oxidizer(oxidizer_type)
    if key not in RT_AV_M2_S2:
        raise ValueError(
            f'No calibrated R*Tav is published for oxidizer {oxidizer_type!r} '
            f'({_SUPPORTED_NOTE}).')
    return {
        'rt_corr_m2_s2': RT_AV_M2_S2[key],
        'rt_gate': key,
        'rt_basis': RT_AV_SOURCE,
    }


def _flux_group(oxidizer_flux_kg_m2_s, of_ratio=None,
                total_flux_kg_m2_s=None):
    """(G_o + G_t) grubunu döndürür [kg/(m²·s)] — iki eşdeğer yoldan biriyle.

    O/F verilirse Denk. (12) yolu: G_o·(2 + 1/(O/F)).
    Toplam akı verilirse Denk. (11) yolu: G_o + G_t.
    """
    g_o = _positive('oxidizer_flux_kg_m2_s', oxidizer_flux_kg_m2_s)
    if (of_ratio is None) == (total_flux_kg_m2_s is None):
        raise ValueError(
            'Supply exactly one of of_ratio (Eq. 12 route) or '
            'total_flux_kg_m2_s (Eq. 11 route) — they are the same group '
            'expressed two ways (Go + Gt = Go*(2 + 1/(O/F))).')
    if of_ratio is not None:
        of = _positive('of_ratio', of_ratio)
        return g_o * (2.0 + 1.0 / of), g_o, of, None
    g_t = _positive('total_flux_kg_m2_s', total_flux_kg_m2_s)
    return g_o + g_t, g_o, None, g_t


def boundary_layer_delay_s(grain_length_m, chamber_pressure_Pa,
                           oxidizer_flux_kg_m2_s, rt_av_m2_s2,
                           of_ratio=None, total_flux_kg_m2_s=None):
    """Sınır tabaka gecikme zamanı τ_bl2 [s] — Denk. (11)/(12).

    τ_bl2 = c'·L·P_c/((G_o + G_t)·R·T_av), c' = 2,050 (makalenin uyumu).
    """
    length = _positive('grain_length_m', grain_length_m)
    pressure = _positive('chamber_pressure_Pa', chamber_pressure_Pa)
    rt_av = _positive('rt_av_m2_s2', rt_av_m2_s2)
    group, _, _, _ = _flux_group(oxidizer_flux_kg_m2_s, of_ratio,
                                 total_flux_kg_m2_s)
    return LFI_DELAY_CONSTANT_C_PRIME * length * pressure / (group * rt_av)


def lfi_frequency_hz(grain_length_m, chamber_pressure_Pa,
                     oxidizer_flux_kg_m2_s, rt_av_m2_s2,
                     of_ratio=None, total_flux_kg_m2_s=None):
    """LFI frekansı f [Hz] — Denk. (15) (O/F yolu) ya da Denk. (14b) grubu.

    Denk. (15) ile Denk. (7)+(12) BASILI KESİNLİĞE KADAR aynı sayıyı
    verir: 0,2341 ⟷ 0,48/2,050 = 0,23414634146341465 (bağıl artık
    1,979e-04; P6B4-10). İki yolun frekansları da bu artık kadar ayrışır
    ve ``assess_hybrid_lfi`` ikisini de yayımlar.
    """
    length = _positive('grain_length_m', grain_length_m)
    pressure = _positive('chamber_pressure_Pa', chamber_pressure_Pa)
    rt_av = _positive('rt_av_m2_s2', rt_av_m2_s2)
    group, _, _, _ = _flux_group(oxidizer_flux_kg_m2_s, of_ratio,
                                 total_flux_kg_m2_s)
    return LFI_COEFFICIENT * group * rt_av / (length * pressure)


def frekans_yollari_ozdeslik_kapisi(frequency_hz, delay_s):
    """f·τ = K·c\' özdeşliği İŞLETME NOKTASINDA tutuyor mu? (fail-closed).

    ``frequency_paths_rel_diff`` yaprağı TANIM GEREĞİ sabittir (bkz.
    ``LFI_FREQUENCY_PATHS_REL_DIFF`` künyesi) — ama yalnızca Denk. 15 ile
    Denk. 11/12 gerçekten aynı katsayı çiftini kullandığı sürece. Sabiti
    ölçmeden yayımlamak, o özdeşliğin bir gün sessizce kopmasına açık
    kapı bırakır (ör. ``lfi_frequency_hz`` kırpma eklerse ya da ikinci bir
    model devreye girerse iki yol AYRI büyüklükler olur ve "basım artığı"
    künyesi YALAN olur).

    Bu yüzden yayımlanan sabit her koşumda ölçülen çarpımla karşılaştırılır.
    Sapma banda sığmazsa hiçbir sayı yayımlanmaz (Berke doktrini 1): sessiz
    yedek yerine adlı gerekçeyle ``ValueError``.

    Returns:
        float: f·τ/(K·c\') − 1, bağıl sapma (band içindeyse).

    Raises:
        ValueError: özdeşlik ``LFI_FREQUENCY_PATHS_IDENTITY_TOL_REL``
            bandının dışına çıktıysa.
    """
    beklenen = LFI_COEFFICIENT * LFI_DELAY_CONSTANT_C_PRIME
    olculen = frequency_hz * delay_s
    sapma = olculen / beklenen - 1.0
    if not abs(sapma) <= LFI_FREQUENCY_PATHS_IDENTITY_TOL_REL:
        raise ValueError(
            'hrma.stability.hybrid_lfi: the two published frequency routes '
            'are no longer two printings of ONE number. Eq. 15 times '
            f'Eq. 11/12 should give f*tau = {beklenen!r} '
            f'(LFI_COEFFICIENT*LFI_DELAY_CONSTANT_C_PRIME) but the operating '
            f'point gives {olculen!r} (relative deviation {sapma:.6g} > '
            f'tolerance {LFI_FREQUENCY_PATHS_IDENTITY_TOL_REL:.6g}). '
            'frequency_paths_rel_diff is published as the PRINTING RESIDUAL '
            'of the coefficient; that label would be false here, so no '
            'number is published.')
    return sapma


def assess_hybrid_lfi(oxidizer_type, grain_length_m, chamber_pressure_Pa,
                      oxidizer_flux_kg_m2_s, of_ratio=None,
                      total_flux_kg_m2_s=None, rt_thermo_m2_s2=None,
                      acoustic_first_longitudinal_hz=None):
    """Hibrit LFI raporu: frekans + R·T üçlüsü + kapsam etiketli hüküm.

    Args:
        oxidizer_type: 'gox' | 'lox' | 'n2o' (başkası → ValueError).
        grain_length_m: yakıt tanesi (port) boyu L [m].
        chamber_pressure_Pa: kamara basıncı P_c [Pa].
        oxidizer_flux_kg_m2_s: oksitleyici port akısı G_o [kg/(m²·s)].
        of_ratio: O/F (Denk. 12 yolu) — ya bu ya total_flux verilir.
        total_flux_kg_m2_s: toplam akı G_t (Denk. 11 yolu).
        rt_thermo_m2_s2: çözücünün kendi R·T_c'si [(m/s)²]; verilirse TANI
            oranı yayımlanır, korelasyona GİRMEZ.
        acoustic_first_longitudinal_hz: 1L akustik mod [Hz]; verilirse ayrışma
            (decade) yayımlanır.

    Returns:
        dict: frekans, gecikme, R·T üçlüsü, hüküm üçlüsü, beyanlar.
    """
    gate = rt_av_for_oxidizer(oxidizer_type)
    rt_corr = gate['rt_corr_m2_s2']
    group, g_o, of, g_t = _flux_group(oxidizer_flux_kg_m2_s, of_ratio,
                                      total_flux_kg_m2_s)
    frequency = lfi_frequency_hz(
        grain_length_m, chamber_pressure_Pa, oxidizer_flux_kg_m2_s, rt_corr,
        of_ratio=of_ratio, total_flux_kg_m2_s=total_flux_kg_m2_s)
    delay = boundary_layer_delay_s(
        grain_length_m, chamber_pressure_Pa, oxidizer_flux_kg_m2_s, rt_corr,
        of_ratio=of_ratio, total_flux_kg_m2_s=total_flux_kg_m2_s)

    # OH-Z5-02: yayımlanan sabitin künyesi ("iki yol yalnız basım artığı
    # kadar ayrışır") her koşumda ÖLÇÜLEREK doğrulanır; kopmuşsa fail-closed.
    frekans_yollari_ozdeslik_kapisi(frequency, delay)

    rt_thermo = (None if rt_thermo_m2_s2 is None
                 else _positive('rt_thermo_m2_s2', rt_thermo_m2_s2))
    rt_ratio = None if rt_thermo is None else rt_thermo / rt_corr

    separation = None
    if acoustic_first_longitudinal_hz is not None:
        f_1l = _positive('acoustic_first_longitudinal_hz',
                         acoustic_first_longitudinal_hz)
        separation = {
            'acoustic_first_longitudinal_hz': f_1l,
            'separation_decades': math.log10(f_1l / frequency),
            'separation_basis': (
                'Decades between the predicted low-frequency mode and the '
                'first longitudinal acoustic mode. The paper reports that '
                'the low-frequency oscillation is commonly accompanied by '
                'lower-amplitude acoustic modes and may even drive them '
                '(Karabeyoglu et al. 2005, conclusion 5); no threshold is '
                'attached to this number here.'),
        }

    verdict = make_verdict(
        VERDICT_MARGINAL,
        'hybrid low-frequency (TCG-coupled) instability — mode PRESENCE and '
        'frequency only; amplitude NOT modelled',
        ('The correlation predicts WHERE the low-frequency mode sits, not how '
         'severe it is: the source states this mode "is present in every '
         'hybrid system to some extent" (conclusion 3) and that the linear '
         'theory "predicts an unlimited growth of the oscillations" so the '
         'amplitude cannot be estimated (conclusion 4). A "stable" verdict '
         'would therefore be a fabricated clearance, and an "unstable" '
         'verdict would overstate severity: the honest reading is that the '
         f'mechanism is expected to be active near {frequency:.3g} Hz. '
         'Published scatter of the correlation against 43 motor tests: 13.94% '
         'mean error (10.30% excluding the HPDP set), max 41.96%.'))

    return {
        'model': 'karabeyoglu_2005_tcg_coupled_scaling_law',
        'model_basis': LFI_COEFFICIENT_BASIS,
        'frequency_hz': frequency,
        # P6B4-10: Denk. 7 yolu (f = 0,48/τ_bl2) da YAYIMLANIR. İki yol
        # ürün yüzünde zaten yan yana duruyordu (frequency_hz ve
        # boundary_layer_delay_s birlikte); farkları yalnız SÖYLENMİYORDU.
        'frequency_via_delay_hz': (LFI_FREQUENCY_DELAY_COEFFICIENT / delay),
        # OH-Z5-02: TEK KAYNAK. Bu yaprak eskiden burada yeniden
        # hesaplanıyordu (``abs(frequency*delay/0.48 - 1)``) ve aynı
        # büyüklüğü ``coefficient_identity_residual_rel``den FARKLI bir
        # sayı olarak basıyordu (ölçüldü: beş işletme noktasında üç ayrı
        # değer, hiçbiri kardeşiyle bit-aynı değil). Özdeşliğin işletme
        # noktasında hâlâ tuttuğu KAYBOLMADI — yukarıdaki kapı onu her
        # koşumda ölçer ve kopmuşsa hiçbir sayı yayımlanmaz.
        'frequency_paths_rel_diff': LFI_FREQUENCY_PATHS_REL_DIFF,
        'frequency_paths_basis': (
            'Two published routes to the same frequency: Eq. 15 (coefficient '
            f'{LFI_COEFFICIENT}) and Eq. 7 (f = '
            f'{LFI_FREQUENCY_DELAY_COEFFICIENT}/tau_bl2) combined with '
            f'Eq. 12 (c\' = {LFI_DELAY_CONSTANT_C_PRIME}). They differ by '
            'exactly the printing residual of the coefficient, published as '
            'frequency_paths_rel_diff; neither is a second model and neither '
            'is hidden. That residual is INPUT-INDEPENDENT by construction '
            '(f*tau = K*c\' — the flux/length/pressure group cancels), so it '
            'is published from the single source '
            'LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL and is bit-identical to '
            'the coefficient_identity_residual_rel field below. The '
            'cancellation is not assumed: f*tau is measured against K*c\' on '
            'every run and no number is published if it drifts (tolerance '
            f'{LFI_FREQUENCY_PATHS_IDENTITY_TOL_REL:.6g}).'),
        'boundary_layer_delay_s': delay,
        'delay_constant_c_prime': LFI_DELAY_CONSTANT_C_PRIME,
        'coefficient': LFI_COEFFICIENT,
        'coefficient_from_delay': LFI_COEFFICIENT_FROM_DELAY,
        'coefficient_identity_residual_rel':
            LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL,
        'coefficient_identity_tol_rel': LFI_COEFFICIENT_IDENTITY_TOL_REL,
        # Metin ARTIK ölçülen sayıyı söylüyor: eskiden burada TAM EŞİTLİK
        # ('0.2341 = 0.48/2.05') yazıyordu, ölçülen bölüm ise
        # 0,23414634146341465'ti (P6B4-10).
        'coefficient_identity': (
            f'{LFI_COEFFICIENT} is Eq. 15 as PRINTED (to '
            f'{LFI_COEFFICIENT_PRINTED_DECIMALS} decimals); Eq. 7 combined '
            f'with Eq. 12 gives {LFI_FREQUENCY_DELAY_COEFFICIENT}/'
            f'{LFI_DELAY_CONSTANT_C_PRIME} = '
            f'{LFI_COEFFICIENT_FROM_DELAY!r}. The two are the same number to '
            f'the printed precision, NOT bit-identical: relative residual '
            f'{LFI_COEFFICIENT_IDENTITY_RESIDUAL_REL:.6g} against the '
            f'printing tolerance {LFI_COEFFICIENT_IDENTITY_TOL_REL:.6g}. '
            f'That residual is what separates frequency_hz from '
            f'frequency_via_delay_hz. The rejected lecture-note coefficient '
            f'{LFI_LECTURE_NOTE_COEFFICIENT_REJECTED} is NOT used.'),
        'rt_corr_m2_s2': rt_corr,
        'rt_gate': gate['rt_gate'],
        'rt_basis': gate['rt_basis'],
        'rt_thermo_m2_s2': rt_thermo,
        'rt_ratio': rt_ratio,
        'rt_ratio_label': 'diagnostic only — not substituted into correlation',
        'rt_ratio_basis': (
            'rt_thermo is the solver\'s own R*T_c, published side by side ONLY '
            'as a diagnostic. Typical hybrid solver values are about twice the '
            'calibrated constant, which would double the predicted frequency '
            'if substituted; the correlation keeps its own calibrated value '
            '(design decision 2).'),
        'oxidizer_flux_kg_m2_s': g_o,
        'of_ratio': of,
        'total_flux_kg_m2_s': g_t,
        'flux_group_kg_m2_s': group,
        'flux_group_basis': (
            'Go + Gt = Go*(2 + 1/(O/F)) — the two published forms (Eq. 11 and '
            'Eq. 12) of the same group; Gt is the TOTAL port mass flux.'),
        'acoustic_separation': separation,
        **verdict,
        'not_modelled': {
            'oscillation_amplitude': (
                'Oscillation amplitude is NOT modelled: the linear TCG theory '
                'predicts unbounded growth and the source explicitly declines '
                'to estimate amplitude (Karabeyoglu et al. 2005, conclusion '
                '4). No limit-cycle magnitude is reported anywhere.'),
            'fore_end_disturbances': (
                'The disturbance field at the fore end (injector '
                'configuration, pre-combustion chamber geometry) is NOT '
                'modelled, although the source identifies it as what decides '
                'whether a given motor is strongly excited.'),
            'nonlinear_behaviour':
                STABILITY_NOT_MODELLED['nonlinear_behaviour'],
        },
        'assumptions': [
            'thermal_lag_gas_dynamics_coupled_linear_theory',
            'calibrated_port_average_RT',
            'single_port_geometry',
            'quasi_steady_operating_point',
        ],
        'inputs': {
            'oxidizer_type': gate['rt_gate'],
            'grain_length_m': float(grain_length_m),
            'chamber_pressure_Pa': float(chamber_pressure_Pa),
            'oxidizer_flux_kg_m2_s': g_o,
            'of_ratio': of,
            'total_flux_kg_m2_s': g_t,
            'rt_thermo_m2_s2': rt_thermo,
            '_basis': "Echo of the caller's inputs (SI).",
        },
    }
