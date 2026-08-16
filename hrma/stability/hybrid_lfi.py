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
    'LFI_DELAY_CONSTANT_C_PRIME',
    'LFI_LECTURE_NOTE_COEFFICIENT_REJECTED',
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

    Denk. (15) ile Denk. (7)+(12) aynı sayıyı verir: 0,2341 = 0,48/2,050
    (katsayı özdeşliği bekçili).
    """
    length = _positive('grain_length_m', grain_length_m)
    pressure = _positive('chamber_pressure_Pa', chamber_pressure_Pa)
    rt_av = _positive('rt_av_m2_s2', rt_av_m2_s2)
    group, _, _, _ = _flux_group(oxidizer_flux_kg_m2_s, of_ratio,
                                 total_flux_kg_m2_s)
    return LFI_COEFFICIENT * group * rt_av / (length * pressure)


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
        'boundary_layer_delay_s': delay,
        'delay_constant_c_prime': LFI_DELAY_CONSTANT_C_PRIME,
        'coefficient': LFI_COEFFICIENT,
        'coefficient_identity': (
            f'{LFI_COEFFICIENT} = {LFI_FREQUENCY_DELAY_COEFFICIENT}/'
            f'{LFI_DELAY_CONSTANT_C_PRIME} (Eq. 7 combined with Eq. 12); the '
            f'rejected lecture-note coefficient '
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
