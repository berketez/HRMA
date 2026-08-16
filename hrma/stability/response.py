# hrma/stability/response.py — yanma tepki fonksiyonu ve KRİTİK TEPKİ EŞİĞİ
"""QSHOD tepki fonksiyonu (bant kapılı) + mod başına kritik tepki eşiği R_crit.

BU YOLDA HÜKÜM YOKTUR (karar 1)
-------------------------------
Yanma kararlılığı hükmü yanma tepki fonksiyonunu BİLMEYİ gerektirir; tepki
fonksiyonu ölçülür (T-burner, dinamik basınç), türetilmez. HRMA'nın elinde bu
ölçüm yoktur. Bu yüzden burada kazanç tarafı TERS ÇEVRİLİR: "bu mod nötr olsun
diye yanma tepkisi NE KADAR olmalıydı?" → ``critical_response_real``.

Bu bir EŞİKTİR, hüküm değildir; sonuç sözlüklerinde 'verdict' anahtarı
YAPISAL olarak bulunmaz — ``hrma.stability.forbid_verdict_key`` bekçisi her
çıktıyı tarar ve eşik bir gün sessizce hükme dönüşürse ``ValueError`` atar.

QSHOD / DENISON-BAUM TEPKİ FONKSİYONU
-------------------------------------
    R_p = n·A·B / (λ + A/λ − (1 + A) + A·B) ,   λ(λ − 1) = i·Ω
    λ = [1 + √(1 + 4iΩ)]/2 ,                    Ω = κ·ω/ṙ_b²

R_p burada KLASİK normalizasyondadır: R_p ≡ (ṁ'/ṁ̄)/(p'/p̄). Künye:
Denison, M.R. & Baum, E., "A Simplified Model of Unstable Burning in Solid
Propellants", *ARS Journal* 31(8), 1961; Culick, F.E.C. & Yang, V.,
"Prediction of the Stability of Unsteady Motions in Solid-Propellant Rocket
Motors", AIAA Progress in Astronautics and Aeronautics Vol. 143, 1990,
Denk. (94)-(95) ve Denk. (92a) (Culick'in kendi yazımı p'/(γp̄) ile
normalize eder, yani R_b^Culick = γ·R_p).

Pay çarpanının doğrulaması (kaynak metninin taranmış hâli bu noktada
okunaksız): yalnız ``n·A·B`` payı Ω → 0 limitinde R_p → n verir, yani
yarı-kararlı limitte yanma hızı üstelini geri getirir. Bu, formun kendi
matematiğinden gelen bir kilittir ve bekçiye bağlanmıştır.

Sayısal çapa (bu depoda ölçüldü): Culick & Yang'ın örnek motoru (Ek verisi;
A = 6,0, B = 0,55, n = 0,3, κ = 1e-7 m²/s, ṙ_b = 0,01145 m/s) ilk üç boyuna
modda Re(R_p) = 3,328 / 0,336 / 0,195 verir; bunlar ``response_gain_uniform_
chamber`` kazancıyla çarpılınca α_c = 288,7 / 29,2 / 16,9 1/s çıkar ve
makalenin Tablo 1'i 288,1 / 28,5 / 16,7 yayımlar (%0,2-2,5 fark, Ek'teki
yuvarlamalar kadar).

(A, B) BANDI VE GEÇERLİLİK ZARFI (karar 3 + sıkılaştırma)
---------------------------------------------------------
(A, B) parametreleri HİÇBİR koşulda varsayılan sayıyla gelmez. Çağıran bir
``QSHODBand`` verir ve bant şu üstveriyi TAŞIMAK ZORUNDADIR: formülasyon
sınıfı, basınç aralığı, sıcaklık aralığı, kaynak künyesi. Çalışma noktası
zarfın dışındaysa sonuç ``confidence='extrapolated_low'`` rozetiyle döner
(gizlenmez ama güvenilirliği düşürülür). F2a'da hazır bant TABLOSU YOKTUR —
künyeli tablo F2b'nin işidir; burada yalnız mekanizma kurulur.
"""

import cmath
import math

from hrma.stability import STABILITY_NOT_MODELLED, forbid_verdict_key
from hrma.stability.chamber import _positive, _validate_gamma

__all__ = [
    'QSHODBand',
    'CONFIDENCE_FIRM',
    'CONFIDENCE_EXTRAPOLATED',
    'qshod_lambda',
    'qshod_response',
    'qshod_response_band',
    'response_gain_uniform_chamber',
    'critical_response_real',
    'critical_response_table',
]

CONFIDENCE_FIRM = 'firm'
CONFIDENCE_EXTRAPOLATED = 'extrapolated_low'

_QSHOD_BASIS = (
    'QSHOD / Denison-Baum response function R_p = n*A*B/(lambda + A/lambda - '
    '(1+A) + A*B) with lambda(lambda-1) = i*Omega and Omega = kappa*omega/'
    'r_b^2 (Denison & Baum, ARS Journal 31(8), 1961; Culick & Yang, AIAA '
    'Progress in Astronautics and Aeronautics Vol. 143, 1990, Eqs. 94-95). '
    'R_p is in the classical normalisation (mdot\'/mdot)/(p\'/p): the '
    'quasi-steady limit Omega -> 0 returns R_p -> n exactly, which is what '
    'pins the numerator factor. A and B are propellant parameters and are '
    'NEVER defaulted here.')

_GAIN_BASIS = (
    'Pressure-coupled driving gain per unit Re(R_p), from Culick & Yang '
    '(1990) Eq. (99) alpha_c = (a/(2*E_n^2)) * (A_b^(r) + M_b) * '
    'integral(psi_n^2 dS) with (A_b^(r) + M_b) = gamma*M_b*Re(R_p) '
    '(their Eq. 93 with the flame-temperature fluctuation term dropped, and '
    'Eq. 92a normalisation R_b = gamma*R_p). For a straight chamber with '
    'psi_n = cos(n*pi*z/L) and E_n^2 = S_c*L/2 this reduces to '
    'gain = (a/L) * (S_b/S_c) * gamma * M_b * <psi^2>, with <psi^2> = 1/2 the '
    'exact mean of cos^2 over the full length. Cross-checked against the '
    'paper\'s worked example: 288.7/29.2/16.9 1/s for the first three modes '
    'vs its published Table 1 values 288.1/28.5/16.7.')


class QSHODBand:
    """(A, B) parametre bandı + ZORUNLU geçerlilik zarfı üstverisi.

    Üstverisiz bant kabul edilmez: formülasyon sınıfı, basınç aralığı, sıcaklık
    aralığı ve kaynak künyesi olmadan kurulamaz (karar 3 sıkılaştırması).
    Sıcaklık tek bir referans değerse ``(T, T)`` verilir — böylece zarf testi
    uydurma bir tolerans gerektirmez (karar 4: referans sıcaklık kaydın
    PARÇASIDIR).
    """

    __slots__ = ('a_range', 'b_range', 'pressure_exponent_n',
                 'formulation_class', 'pressure_range_Pa',
                 'temperature_range_K', 'source')

    def __init__(self, a_range, b_range, pressure_exponent_n,
                 formulation_class, pressure_range_Pa, temperature_range_K,
                 source):
        self.a_range = self._range('a_range', a_range)
        self.b_range = self._range('b_range', b_range)
        n = pressure_exponent_n
        if isinstance(n, bool) or not isinstance(n, (int, float)):
            raise ValueError(
                f'pressure_exponent_n must be a finite number (got {n!r}).')
        n = float(n)
        if not math.isfinite(n) or not (0.0 < n < 2.0):
            raise ValueError(
                f'pressure_exponent_n must lie in (0, 2) (got {n!r}).')
        self.pressure_exponent_n = n
        self.formulation_class = self._text('formulation_class',
                                            formulation_class)
        self.pressure_range_Pa = self._range('pressure_range_Pa',
                                             pressure_range_Pa)
        self.temperature_range_K = self._range('temperature_range_K',
                                               temperature_range_K)
        self.source = self._text('source', source)

    @staticmethod
    def _range(name, value):
        try:
            low, high = value
        except (TypeError, ValueError):
            raise ValueError(
                f'{name} must be a (low, high) pair (got {value!r}).') from None
        low = _positive(f'{name}[0]', low)
        high = _positive(f'{name}[1]', high)
        if high < low:
            raise ValueError(
                f'{name} must satisfy low <= high (got {value!r}).')
        return (low, high)

    @staticmethod
    def _text(name, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f'{name} is mandatory metadata for a response band: a band '
                f'without it cannot state where it is valid (got {value!r}).')
        return value.strip()

    def corners(self):
        """Bandın dört (A, B) köşesi — zarf taraması için."""
        return [(a, b) for a in self.a_range for b in self.b_range]

    def envelope_check(self, pressure_Pa, temperature_K):
        """Çalışma noktası zarfın içinde mi? → (confidence, gerekçe)."""
        p = _positive('pressure_Pa', pressure_Pa)
        t = _positive('temperature_K', temperature_K)
        outside = []
        if not (self.pressure_range_Pa[0] <= p <= self.pressure_range_Pa[1]):
            outside.append(
                f'pressure {p:.4g} Pa outside '
                f'[{self.pressure_range_Pa[0]:.4g}, '
                f'{self.pressure_range_Pa[1]:.4g}] Pa')
        if not (self.temperature_range_K[0] <= t
                <= self.temperature_range_K[1]):
            outside.append(
                f'temperature {t:.4g} K outside '
                f'[{self.temperature_range_K[0]:.4g}, '
                f'{self.temperature_range_K[1]:.4g}] K')
        if outside:
            return CONFIDENCE_EXTRAPOLATED, (
                f'Operating point is OUTSIDE the validity envelope of the '
                f'band ({"; ".join(outside)}); the band is still shown but '
                f'flagged as extrapolated. Envelope source: {self.source}')
        return CONFIDENCE_FIRM, (
            f'Operating point lies inside the validity envelope of the band '
            f'(formulation class "{self.formulation_class}", '
            f'{self.pressure_range_Pa[0]:.4g}-{self.pressure_range_Pa[1]:.4g} '
            f'Pa, {self.temperature_range_K[0]:.4g}-'
            f'{self.temperature_range_K[1]:.4g} K). Source: {self.source}')

    def as_dict(self):
        return {
            'a_range': self.a_range,
            'b_range': self.b_range,
            'pressure_exponent_n': self.pressure_exponent_n,
            'formulation_class': self.formulation_class,
            'pressure_range_Pa': self.pressure_range_Pa,
            'temperature_range_K': self.temperature_range_K,
            'source': self.source,
        }


def qshod_lambda(omega_rad_s, thermal_diffusivity_m2_s, burn_rate_m_s):
    """λ = [1 + √(1 + 4iΩ)]/2 ve Ω = κ·ω/ṙ_b² (boyutsuz frekans)."""
    omega = _positive('omega_rad_s', omega_rad_s)
    kappa = _positive('thermal_diffusivity_m2_s', thermal_diffusivity_m2_s)
    r_b = _positive('burn_rate_m_s', burn_rate_m_s)
    omega_nd = kappa * omega / (r_b * r_b)
    lam = (1.0 + cmath.sqrt(1.0 + 4.0j * omega_nd)) / 2.0
    return lam, omega_nd


def qshod_response(a_param, b_param, pressure_exponent_n, omega_rad_s,
                   thermal_diffusivity_m2_s, burn_rate_m_s):
    """QSHOD tepki fonksiyonu R_p (karmaşık) + boyutsuz frekans Ω.

    Returns:
        dict: ``response`` (complex), ``response_real``, ``response_imag``,
        ``omega_nondim``, ``lambda``, ``basis``.
    """
    a = _positive('a_param', a_param)
    b = _positive('b_param', b_param)
    n = _positive('pressure_exponent_n', pressure_exponent_n, upper=2.0)
    lam, omega_nd = qshod_lambda(omega_rad_s, thermal_diffusivity_m2_s,
                                 burn_rate_m_s)
    denom = lam + a / lam - (1.0 + a) + a * b
    if denom == 0:
        raise ValueError(
            'QSHOD denominator vanished (resonant singularity) for '
            f'A={a!r}, B={b!r}, Omega={omega_nd!r}: the response is unbounded '
            'there, so no finite number is reported.')
    response = n * a * b / denom
    return {
        'response': response,
        'response_real': float(response.real),
        'response_imag': float(response.imag),
        'omega_nondim': float(omega_nd),
        'lambda': lam,
        'basis': _QSHOD_BASIS,
    }


def qshod_response_band(band, omega_rad_s, thermal_diffusivity_m2_s,
                        burn_rate_m_s, pressure_Pa, temperature_K):
    """Bant köşelerinde Re(R_p) taraması + geçerlilik zarfı rozeti.

    Args:
        band: ``QSHODBand`` (üstverisi zorunlu).
        omega_rad_s: mod açısal frekansı [rad/s].
        thermal_diffusivity_m2_s, burn_rate_m_s: yakıtın κ ve ṙ_b değerleri.
        pressure_Pa, temperature_K: çalışma noktası (zarf testi için).

    Returns:
        dict: köşe değerleri, Re(R_p) min/maks, ``confidence`` ve gerekçesi.
    """
    if not isinstance(band, QSHODBand):
        raise ValueError(
            'band must be a QSHODBand instance carrying its validity '
            'envelope metadata (no bare (A, B) pair is accepted).')
    confidence, confidence_basis = band.envelope_check(pressure_Pa,
                                                       temperature_K)
    _, omega_nd = qshod_lambda(omega_rad_s, thermal_diffusivity_m2_s,
                               burn_rate_m_s)
    corners = []
    for a, b in band.corners():
        row = qshod_response(a, b, band.pressure_exponent_n, omega_rad_s,
                             thermal_diffusivity_m2_s, burn_rate_m_s)
        corners.append({'a_param': a, 'b_param': b,
                        'response_real': row['response_real'],
                        'response_imag': row['response_imag']})
    reals = [c['response_real'] for c in corners]
    return {
        'band': band.as_dict(),
        'corners': corners,
        'response_real_min': min(reals),
        'response_real_max': max(reals),
        'omega_nondim': float(omega_nd),
        'confidence': confidence,
        'confidence_basis': confidence_basis,
        'basis': _QSHOD_BASIS,
    }


def response_gain_uniform_chamber(sound_speed_m_s, chamber_length_m,
                                  burning_surface_area_m2, port_area_m2,
                                  surface_mach, gamma,
                                  mode_shape_mean_square=0.5):
    """Birim Re(R_p) başına sürükleme kazancı [1/s] (düzgün kamara kapanışı).

    gain = (ā/L)·(S_b/S_c)·γ·M_b·⟨ψ²⟩ ; α_c = gain·Re(R_p).

    ``mode_shape_mean_square`` düz tüpte cos²'nin TAM ortalamasıdır (1/2);
    başka bir yanma yüzeyi yerleşimi için çağıran kendi değerini verir
    (uydurma değil, geometriden gelen ortalama).
    """
    a = _positive('sound_speed_m_s', sound_speed_m_s)
    length = _positive('chamber_length_m', chamber_length_m)
    s_b = _positive('burning_surface_area_m2', burning_surface_area_m2)
    s_c = _positive('port_area_m2', port_area_m2)
    mach = _positive('surface_mach', surface_mach, upper=1.0)
    g = _validate_gamma(gamma)
    psi2 = _positive('mode_shape_mean_square', mode_shape_mean_square,
                     upper=1.0 + 1e-12)
    gain = (a / length) * (s_b / s_c) * g * mach * psi2
    return {
        'gain_1_s': gain,
        'mode_shape_mean_square': psi2,
        'basis': _GAIN_BASIS,
        'inputs': {
            'sound_speed_m_s': a,
            'chamber_length_m': length,
            'burning_surface_area_m2': s_b,
            'port_area_m2': s_c,
            'surface_mach': mach,
            'gamma': g,
            '_basis': "Echo of the caller's inputs (SI).",
        },
    }


def critical_response_real(damping_total_1_s, response_gain_1_s):
    """R_crit: modu NÖTR yapacak Re(R_p) eşiği (hüküm DEĞİL).

    α_c + Σα_kayıp = 0 ⇒ Re(R_p)_crit = |Σα_kayıp|/kazanç.

    Args:
        damping_total_1_s: bütçenin toplamı Σα [1/s]; NEGATİF olmalı (net
            kayıp). Pozitifse mod, yanma tepkisi OLMADAN bile sürükleniyor
            demektir ve eşik tanımsızdır → None + gerekçe.
        response_gain_1_s: birim Re(R_p) başına kazanç [1/s] (> 0).

    Returns:
        dict: ``critical_response_real`` (float ya da None), yorum alanı ve
        beyanlar. 'verdict' anahtarı YOKTUR (yapısal bekçi).
    """
    if (isinstance(damping_total_1_s, bool)
            or not isinstance(damping_total_1_s, (int, float))
            or not math.isfinite(float(damping_total_1_s))):
        raise ValueError(
            f'damping_total_1_s must be a finite number [1/s] '
            f'(got {damping_total_1_s!r}).')
    gain = _positive('response_gain_1_s', response_gain_1_s)
    total = float(damping_total_1_s)

    if total >= 0.0:
        r_crit = None
        note = (
            'The supplied damping budget is not a net loss (sum >= 0), so no '
            'finite critical response exists: the mode is already being '
            'driven by the terms in the budget itself. No threshold is '
            'fabricated.')
    else:
        r_crit = -total / gain
        note = (
            f'A pressure-coupled response with Re(R_p) = {r_crit:.4g} would '
            f'exactly cancel the modelled losses ({-total:.4g} 1/s) at a '
            f'driving gain of {gain:.4g} 1/s per unit Re(R_p).')

    payload = {
        'critical_response_real': r_crit,
        'damping_total_1_s': total,
        'response_gain_1_s': gain,
        'interpretation': 'threshold_not_verdict',
        'interpretation_basis': (
            'This is the response the combustion WOULD have to deliver for '
            'the mode to be neutral — a comparison yardstick, never a '
            'stability verdict. HRMA does not measure the response function '
            '(it comes from T-burner style tests), so no verdict is issued '
            'on this path (design doc section 3.0).'),
        'note': note,
        'not_modelled': {
            'combustion_response_measurement':
                STABILITY_NOT_MODELLED['combustion_response_measurement'],
            'velocity_coupling': (
                'Velocity coupling (response to the acoustic velocity along '
                'the burning surface) is NOT modelled; only pressure coupling '
                'enters this threshold.'),
            'flame_temperature_fluctuation': (
                'The flame-temperature fluctuation term of Culick & Yang '
                'Eq. (93) is dropped, so the gain covers the mass-flux '
                'response only.'),
        },
    }
    return forbid_verdict_key(payload, 'critical_response_real')


def critical_response_table(acoustic_result, damping_budgets,
                            response_gain_1_s, literature_band=None):
    """Akustik mod tablosunun her satırı için R_crit (HÜKÜMSÜZ tablo).

    Mod tablosu ÜRETİLMEZ: ``hrma.analysis.acoustic_modes`` çıktısı olduğu
    gibi okunur (tek kaynak; o modül taşınmadı, değiştirilmedi).

    Args:
        acoustic_result: ``AcousticModeAnalyzer.analyze()`` çıktısı.
        damping_budgets: tek bir bütçe sözlüğü (mod bağımsız, ör. yalnız lüle
            terimi) ya da {mod etiketi: bütçe} eşlemesi.
        response_gain_1_s: birim Re(R_p) başına kazanç [1/s].
        literature_band: opsiyonel {'low', 'high', 'source'} kıyas bandı;
            verilirse ``source`` ZORUNLUDUR (künyesiz bant kabul edilmez).

    Returns:
        dict: ``modes`` satırları + beyanlar; hiçbir yerde 'verdict' yok.
    """
    if not isinstance(acoustic_result, dict) or 'modes' not in acoustic_result:
        raise ValueError(
            'acoustic_result must be the dict returned by '
            'AcousticModeAnalyzer.analyze() (it must carry a "modes" list).')
    band = None
    if literature_band is not None:
        band = dict(literature_band)
        if not band.get('source'):
            raise ValueError(
                'literature_band must carry a "source" citation; an '
                'uncited comparison band is not published.')

    rows = []
    for mode in acoustic_result['modes']:
        label = mode.get('label')
        if isinstance(damping_budgets, dict) and 'terms' in damping_budgets:
            budget = damping_budgets           # tek bütçe, tüm modlara
        else:
            budget = damping_budgets[label]    # mod başına bütçe
        total = budget['total_damping_1_s']
        row = critical_response_real(total, response_gain_1_s)
        row['label'] = label
        row['frequency_hz'] = mode.get('frequency_hz')
        row['damping'] = dict(budget['terms'])
        row['damping_not_modelled'] = list(budget['not_modelled'].keys())
        if band is not None:
            row['literature_band'] = band
        rows.append(row)

    payload = {
        'modes': rows,
        'response_gain_1_s': float(response_gain_1_s),
        'mode_table_source': (
            'Modes are read from hrma.analysis.acoustic_modes '
            '(model: ' + str(acoustic_result.get('model')) + '); no second '
            'mode table is produced here.'),
        'interpretation': 'threshold_not_verdict',
        'bias_basis': (
            'Damping terms that are not modelled bias every R_crit LOW '
            '(pessimistic): with more losses accounted for, a higher '
            'combustion response would be needed to drive the mode.'),
    }
    return forbid_verdict_key(payload, 'critical_response_table')
