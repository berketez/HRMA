"""
Lüle akış ayrılması kriterleri — Summerfield, Schmucker, Kalt-Badal (F1).

NE OLDUĞU / NE OLMADIĞI
-----------------------
Aşırı genleşmiş lülede sınır tabaka ayrılmasının VAR/YOK kararı ve ayrılma
konumu tahmini için üç yayımlanmış deneysel korelasyon. Sınır tabaka
ÇÖZÜLMEZ: duvar basıncı, ``hrma.flow.quasi1d`` ile aynı bağıntılardan gelen
tam-akan izantropik yarı-1B çekirdek basıncıyla temsil edilir (sürtünmesiz
yaklaşım — çıktıda beyanlıdır). Motor sonuç sözlüğünden bağımsız saf
fiziktir; girdiler SI (Pa, m, m²).

KRİTERLER VE FORMÜL KAYNAKLARI
------------------------------
Summerfield (sabit eşik):
    P_sep / P_a = k,  k ≈ 0.35-0.40 (varsayılan 0.40, muhafazakâr uç —
    ``engines/nozzle_design.py._SEPARATION_PRESSURE_FRACTION`` ile aynı değer).
    Kaynak: Summerfield, Foster & Swan, "Flow Separation in Overexpanded
    Supersonic Exhaust Nozzles", Jet Propulsion 24 (1954); Sutton & Biblarz,
    "Rocket Propulsion Elements", 9. baskı, Böl. 3.
    Geçerlilik: küçük/orta alan oranlı konik lüle verisinden, lüle basınç
    oranı (P0/Pa) kabaca 15-20 bandında türetildi; Mach ve basınç oranı
    bağımlılığı taşımaz, yüksek basınç oranında ERKEN (muhafazakâr) ayrılma
    öngörür.

Schmucker (yerel Mach bağımlı):
    P_sep / P_a = (1.88·M_sep − 1)^(−0.64)
    Kaynak: Schmucker, R.H., "Flow Processes in Overexpanded Chemical
    Rocket Nozzles — Part 1: Flow Separation", TU München TB-7/TB-10 (1973);
    İngilizce çeviri NASA TM-77396 (1984). Derleme: Östlund, "Flow Processes
    in Rocket Engine Nozzles with Focus on Flow Separation and Side-Loads",
    KTH TRITA-MEK 2002:09.
    Geçerlilik: sıcak gaz bell lüle verisi (J-2/J-2S dahil); ayrılma Mach'ı
    kabaca 1.5-4.5 bandında türetildi.

Kalt-Badal (basınç oranı bağımlı):
    P_sep / P_a = (2/3)·(P0/P_a)^(−1/5)
    Katsayı tam 2/3'tür (literatürde 0.667 diye yuvarlanır).
    Kaynak: Kalt, S., Badal, D., "Conical Rocket Nozzle Performance Under
    Flow Separated Conditions", Journal of Spacecraft and Rockets 2(3),
    1965. Derleme: Östlund (2002), a.g.e.; Stark, AIAA 2005-3940, Ek.
    Geçerlilik: soğuk akış konik lüle deneyleri; lüle basınç oranı kabaca
    10-10³ bandı.

Üç formül de ``data/validation/nozzle_separation_criteria.json``'daki
künyeli formüllerle birebir aynıdır; sayısal uyum, o dosyanın türetilmiş
değerlerini kullanan bekçi testleriyle korunur (tests/flow). Kriterler
BİRBİRİYLE UYUŞMAZ — bu alanın gerçek belirsizliğidir; bu yüzden üçü
birden raporlanır ve kontrol eden kriter beyan edilir.

MODELLENMEYENLER (çıktıda ``not_modelled`` olarak da beyan edilir)
------------------------------------------------------------------
- ``side_loads``: ayrılma kaynaklı yanal yükler.
- ``fss_rss_distinction``: serbest/kısıtlı şok ayrılması (FSS/RSS) ayrımı.
- ``boundary_layer_state``: sınır tabaka çözümü yok (laminer/türbülanslı
  durumu, kalınlık, ayrılma sonrası geri basınç dağılımı).
- ``shock_boundary_layer_interaction``: ayrılma şoku yapısı ve etkileşimi.
- ``transient_effects``: ateşleme/söndürme geçişlerinde ayrılma histerezisi.
"""

import numpy as np
from typing import Dict, Optional, Sequence

from scipy.optimize import brentq

from hrma.flow.quasi1d import (
    _validate_area_profile,
    area_ratio_from_mach,
    isentropic_ratios,
    mach_from_area_ratio,
    mach_from_pressure_ratio,
)

__all__ = [
    'SEPARATION_NOT_MODELLED',
    'SUMMERFIELD_FACTOR_DEFAULT',
    'SUMMERFIELD_FACTOR_BAND',
    'CRITERION_SUMMERFIELD',
    'CRITERION_SCHMUCKER',
    'CRITERION_KALT_BADAL',
    'summerfield_pressure_ratio',
    'schmucker_pressure_ratio',
    'kalt_badal_pressure_ratio',
    'assess_separation',
]

#: Summerfield eşiği: literatür bandı 0.35-0.40; varsayılan muhafazakâr uç.
#: engines/nozzle_design.py._SEPARATION_PRESSURE_FRACTION ile aynı değer
#: (parametre tutarlılığı kuralı — o modül motor katmanına ait olduğu için
#: buradan import edilmez, değer eşitliği bekçi testiyle korunur).
SUMMERFIELD_FACTOR_DEFAULT = 0.4
SUMMERFIELD_FACTOR_BAND = (0.35, 0.40)

CRITERION_SUMMERFIELD = 'summerfield'
CRITERION_SCHMUCKER = 'schmucker'
CRITERION_KALT_BADAL = 'kalt_badal'

_ALL_CRITERIA = (CRITERION_SUMMERFIELD, CRITERION_SCHMUCKER,
                 CRITERION_KALT_BADAL)

SEPARATION_NOT_MODELLED = {
    'side_loads': (
        'Ayrılma kaynaklı yanal (side-load) kuvvetler modellenmedi; yalnız '
        'ayrılma var/yok kararı ve konum tahmini verilir.'),
    'fss_rss_distinction': (
        'Serbest şok ayrılması (FSS) ile kısıtlı şok ayrılması (RSS) ayrımı '
        'modellenmedi; kriterler klasik FSS verisinden türetilmiştir.'),
    'boundary_layer_state': (
        'Sınır tabaka çözülmez: laminer/türbülanslı durum, kalınlık ve '
        'ayrılma sonrası duvar basıncı dağılımı modellenmedi. Duvar basıncı '
        'izantropik yarı-1B çekirdek basıncıyla temsil edilir.'),
    'shock_boundary_layer_interaction': (
        'Ayrılma şoku yapısı ve şok-sınır tabaka etkileşimi modellenmedi.'),
    'transient_effects': (
        'Ateşleme/söndürme geçişlerindeki ayrılma histerezisi modellenmedi; '
        'karar kararlı hâl içindir.'),
}

_VALIDITY = {
    CRITERION_SUMMERFIELD: (
        'Konik lüle verisi, lüle basınç oranı (P0/Pa) ~15-20 bandından; '
        'Mach ve basınç oranı bağımlılığı yok — yüksek basınç oranında '
        'muhafazakâr (erken ayrılma) tarafta kalır. Eşik bandı 0.35-0.40.'),
    CRITERION_SCHMUCKER: (
        'Sıcak gaz bell lüle verisinden (J-2/J-2S dahil); ayrılma Mach '
        'sayısı ~1.5-4.5 bandında türetildi. Bandın dışında dışkestirimdir.'),
    CRITERION_KALT_BADAL: (
        'Soğuk akış konik lüle deneylerinden; lüle basınç oranı (P0/Pa) '
        '~10-1000 bandı. Sıcak gaz bell lülede dışkestirimdir.'),
}

_BASIS = {
    CRITERION_SUMMERFIELD: (
        'P_sep/P_a = k (varsayılan 0.40). Summerfield, Foster & Swan, Jet '
        'Propulsion 24 (1954); Sutton & Biblarz 9. baskı, Böl. 3.'),
    CRITERION_SCHMUCKER: (
        'P_sep/P_a = (1.88·M_sep − 1)^(−0.64). Schmucker (1973), TU München '
        'TB-7/TB-10; NASA TM-77396; Östlund (2002).'),
    CRITERION_KALT_BADAL: (
        'P_sep/P_a = (2/3)·(P0/P_a)^(−1/5). Kalt & Badal, J. Spacecraft '
        'and Rockets 2(3), 1965; Östlund (2002); Stark AIAA 2005-3940 Ek '
        '(data/validation/nozzle_separation_criteria.json ile birebir).'),
}


# --------------------------------------------------------------------------
# Eşik fonksiyonları (saf, tek başına test edilebilir)
# --------------------------------------------------------------------------

def summerfield_pressure_ratio(
        factor: float = SUMMERFIELD_FACTOR_DEFAULT) -> float:
    """Summerfield ayrılma eşiği P_sep/P_a (sabit).

    Kaynak: Summerfield, Foster & Swan (1954); Sutton & Biblarz, 9. baskı,
    Böl. 3. Literatür bandı 0.35-0.40; bandın dışı ValueError.
    """
    f = float(factor)
    if not (0.2 <= f <= 0.6):
        raise ValueError(
            'Summerfield eşiği fiziksel bandın çok dışında (0.2-0.6 kabul '
            'edilir; literatür bandı 0.35-0.40).')
    return f


def schmucker_pressure_ratio(mach_local: float) -> float:
    """Schmucker ayrılma eşiği P_sep/P_a = (1.88·M − 1)^(−0.64).

    M yereldeki (ayrılma istasyonundaki) Mach sayısıdır. Kaynak: Schmucker
    (1973); NASA TM-77396; Östlund (2002). Türetim bandı M ≈ 1.5-4.5.
    """
    M = float(mach_local)
    if 1.88 * M - 1.0 <= 0.0:
        raise ValueError('Schmucker eşiği için 1.88·M − 1 > 0 gerekli.')
    return float((1.88 * M - 1.0) ** (-0.64))


def kalt_badal_pressure_ratio(npr: float) -> float:
    """Kalt-Badal ayrılma eşiği P_sep/P_a = (2/3)·(P0/P_a)^(−1/5).

    npr = P0/P_a lüle basınç oranıdır. Katsayı tam 2/3'tür (literatürde
    0.667 diye yuvarlanır) — data/validation/nozzle_separation_criteria.json
    künyeli formülüyle birebir. Kaynak: Kalt & Badal (1965); Östlund (2002);
    Stark, AIAA 2005-3940, Ek. Türetim bandı NPR ≈ 10-1000.
    """
    r = float(npr)
    if r <= 1.0:
        raise ValueError('Kalt-Badal eşiği için P0/P_a > 1 gerekli.')
    return float((2.0 / 3.0) * r ** (-0.2))


# --------------------------------------------------------------------------
# Değerlendirme
# --------------------------------------------------------------------------

def _criterion_from_threshold(name: str, P_sep: float, P0: float, Pa: float,
                              gamma: float, M_exit: float, P_exit: float,
                              x_div: Optional[np.ndarray],
                              eps_div: Optional[np.ndarray]) -> Dict:
    """AÇIK eşikli kriter (Summerfield, Kalt-Badal) için sonuç sözlüğü.

    Ayrılma kararı: tam-akan duvar basıncı x boyunca monoton düştüğü için
    eşik, çıkış basıncı eşiğin altındaysa lüle İÇİNDE aşılır.
    """
    result = {
        'criterion': name,
        'separated': bool(P_exit < P_sep),
        'wall_pressure_sep_Pa': float(P_sep),
        'pressure_ratio_threshold': float(P_sep / Pa),
        'mach_sep': None,
        'area_ratio_sep': None,
        'x_sep_m': None,
        'validity': _VALIDITY[name],
        'validity_warning': None,
        '_basis': _BASIS[name],
    }
    if not result['separated']:
        return result
    # Boğazdaki (M=1) statik basınç: eşik bunun da üstündeyse korelasyon
    # ayrılmayı boğaza kadar taşır — türetim bandının dışıdır, beyan edilir.
    P_throat = P0 * isentropic_ratios(1.0, gamma)[1]
    if P_sep >= P_throat:
        result['mach_sep'] = 1.0
        result['area_ratio_sep'] = 1.0
        result['validity_warning'] = (
            'Eşik basıncı boğaz statik basıncının üstünde: kriter türetim '
            'bandının dışında, ayrılma konumu boğaza kırpıldı.')
    else:
        M_sep = mach_from_pressure_ratio(P0 / P_sep, gamma)
        result['mach_sep'] = float(M_sep)
        result['area_ratio_sep'] = float(area_ratio_from_mach(M_sep, gamma))
    if x_div is not None and result['area_ratio_sep'] is not None:
        result['x_sep_m'] = float(np.interp(result['area_ratio_sep'],
                                            eps_div, x_div))
    return result


def _criterion_schmucker(P0: float, Pa: float, gamma: float, M_exit: float,
                         P_exit: float, x_div: Optional[np.ndarray],
                         eps_div: Optional[np.ndarray]) -> Dict:
    """Schmucker kriteri: eşik yerel Mach'a bağlı olduğundan örtük çözülür.

    g(M) = P_duvar(M) − P_a·(1.88·M − 1)^(−0.64) işaret değiştirdiği
    istasyon ayrılma istasyonudur (brentq).
    """
    name = CRITERION_SCHMUCKER
    result = {
        'criterion': name,
        'separated': False,
        'wall_pressure_sep_Pa': None,
        'pressure_ratio_threshold': None,
        'mach_sep': None,
        'area_ratio_sep': None,
        'x_sep_m': None,
        'validity': _VALIDITY[name],
        'validity_warning': None,
        '_basis': _BASIS[name],
    }

    def gap(M: float) -> float:
        return (P0 * isentropic_ratios(M, gamma)[1]
                - Pa * schmucker_pressure_ratio(M))

    g_exit = gap(M_exit)
    if g_exit >= 0.0:
        # Çıkışta bile duvar basıncı eşiğin üstünde: yapışık akış.
        return result
    result['separated'] = True
    M_lo = 1.0 + 1e-6
    if gap(M_lo) <= 0.0:
        # Eşik daha boğazda aşılmış: türetim bandı dışı, boğaza kırp.
        result['mach_sep'] = 1.0
        result['area_ratio_sep'] = 1.0
        result['wall_pressure_sep_Pa'] = float(
            P0 * isentropic_ratios(1.0, gamma)[1])
        result['validity_warning'] = (
            'Eşik boğazda zaten aşılmış: kriter türetim bandının dışında, '
            'ayrılma konumu boğaza kırpıldı.')
    else:
        M_sep = brentq(gap, M_lo, M_exit, xtol=1e-12, maxiter=200)
        result['mach_sep'] = float(M_sep)
        result['area_ratio_sep'] = float(area_ratio_from_mach(M_sep, gamma))
        result['wall_pressure_sep_Pa'] = float(
            P0 * isentropic_ratios(M_sep, gamma)[1])
        result['pressure_ratio_threshold'] = float(
            schmucker_pressure_ratio(M_sep))
        if not (1.5 <= M_sep <= 4.5):
            result['validity_warning'] = (
                f'Ayrılma Mach sayısı {M_sep:.2f}, türetim bandının '
                f'(1.5-4.5) dışında — dışkestirim.')
    if x_div is not None and result['area_ratio_sep'] is not None:
        result['x_sep_m'] = float(np.interp(result['area_ratio_sep'],
                                            eps_div, x_div))
    return result


def assess_separation(P0: float, Pa: float, gamma: float,
                      x: Optional[Sequence[float]] = None,
                      area: Optional[Sequence[float]] = None,
                      area_ratio_exit: Optional[float] = None,
                      summerfield_factor: float = SUMMERFIELD_FACTOR_DEFAULT
                      ) -> Dict:
    """Lüle çıkış koşullarından ayrılma değerlendirmesi (üç kriter).

    Args:
        P0: Rezervuar (durma) basıncı [Pa].
        Pa: Ortam basıncı [Pa]. 0 (vakum) verilirse ayrılma tanımsızdır ve
            'not_applicable' beyanıyla döner.
        gamma: İzantropik üs.
        x, area: İsteğe bağlı alan profili [m, m²] (tek boğazlı
            yakınsak-ıraksak; ``quasi1d`` ile aynı doğrulama). Verilirse
            ayrılma konumu x cinsinden de raporlanır.
        area_ratio_exit: Profil verilmezse çıkış alan oranı A_e/A_t;
            konum yalnız alan oranı cinsinden raporlanır (x_sep_m = None).
        summerfield_factor: Summerfield eşiği (varsayılan 0.40; bant
            0.35-0.40 — bandın dışı beyanla işaretlenir).

    Returns:
        Beyanlı sözlük: ``separated`` (herhangi bir kriter tetiklenirse
        True), ``controlling_criterion`` (en YUKARI ayrılma öngören —
        muhafazakâr — kriter), ``x_sep_m`` / ``area_ratio_sep`` (kontrol
        eden kriterin konumu), ``criteria`` (kriter başına ayrıntı),
        ``full_flow_exit``, ``not_modelled``, ``_basis``.

    Varsayım (beyanlı): ıraksak bölümde TAM AKAN izantropik ses-üstü
    çekirdek. Lüle içinde normal şok rejimi hüküm sürüyorsa (bkz.
    ``quasi1d.solve_nozzle`` rejim çıktısı) bu kriterler tasarım amaçlı
    yaklaşık göstergedir.
    """
    P0 = float(P0)
    Pa = float(Pa)
    g = float(gamma)
    if P0 <= 0.0:
        raise ValueError('P0 pozitif olmalı.')
    if Pa < 0.0:
        raise ValueError('Ortam basıncı negatif olamaz.')
    if not (1.0 < g < 2.0):
        raise ValueError('gamma (1, 2) aralığında olmalı (mükemmel gaz).')

    x_div = None
    eps_div = None
    if (x is None) != (area is None):
        raise ValueError('x ve area birlikte verilmeli.')
    if x is not None:
        x_arr, a_arr, it = _validate_area_profile(x, area)
        x_div = x_arr[it:]
        eps_div = a_arr[it:] / float(a_arr[it])
        eps_e = float(eps_div[-1])
        if area_ratio_exit is not None:
            raise ValueError(
                'Ya profil (x, area) ya area_ratio_exit verilmeli, ikisi '
                'birden değil.')
    elif area_ratio_exit is not None:
        eps_e = float(area_ratio_exit)
        if eps_e <= 1.0:
            raise ValueError('area_ratio_exit > 1 olmalı.')
    else:
        raise ValueError('Profil (x, area) ya da area_ratio_exit gerekli.')

    M_exit = mach_from_area_ratio(eps_e, g, supersonic=True)
    P_exit = P0 * isentropic_ratios(M_exit, g)[1]
    common_basis = (
        'Duvar basıncı, tam-akan izantropik yarı-1B çekirdek basıncıyla '
        'temsil edilir (hrma.flow.quasi1d bağıntıları; Anderson 3. baskı, '
        'Eş. 3.30 + 5.20). Kriterler yayımlanmış deneysel korelasyonlardır.')

    base = {
        'ambient_pressure_Pa': Pa,
        'full_flow_exit': {
            'mach': float(M_exit),
            'pressure_Pa': float(P_exit),
            'pressure_over_ambient': (float(P_exit / Pa) if Pa > 0.0
                                      else None),
            '_basis': 'Tam-akan izantropik ses-üstü dal, çıkış istasyonu.',
        },
        'not_modelled': dict(SEPARATION_NOT_MODELLED),
        '_basis': common_basis,
    }

    if Pa <= 0.0:
        base.update({
            'separated': False,
            'controlling_criterion': None,
            'x_sep_m': None,
            'area_ratio_sep': None,
            'criteria': {},
            'not_applicable_reason': (
                'Vakumda (Pa = 0) aşırı genleşme ve ayrılma tanımsızdır; '
                'kriterler ortam basıncına göre tanımlıdır.'),
        })
        return base

    factor = summerfield_pressure_ratio(summerfield_factor)
    criteria = {
        CRITERION_SUMMERFIELD: _criterion_from_threshold(
            CRITERION_SUMMERFIELD, factor * Pa, P0, Pa, g, M_exit, P_exit,
            x_div, eps_div),
        CRITERION_SCHMUCKER: _criterion_schmucker(
            P0, Pa, g, M_exit, P_exit, x_div, eps_div),
        CRITERION_KALT_BADAL: _criterion_from_threshold(
            CRITERION_KALT_BADAL, kalt_badal_pressure_ratio(P0 / Pa) * Pa,
            P0, Pa, g, M_exit, P_exit, x_div, eps_div),
    }
    if not (SUMMERFIELD_FACTOR_BAND[0] <= factor
            <= SUMMERFIELD_FACTOR_BAND[1]):
        criteria[CRITERION_SUMMERFIELD]['validity_warning'] = (
            f'Seçilen eşik {factor:.2f}, literatür bandının '
            f'({SUMMERFIELD_FACTOR_BAND[0]:.2f}-'
            f'{SUMMERFIELD_FACTOR_BAND[1]:.2f}) dışında.')

    separated_names = [name for name in _ALL_CRITERIA
                       if criteria[name]['separated']]
    controlling = None
    if separated_names:
        # En küçük alan oranında (en yukarıda) ayrılma öngören kriter
        # kontrol eder — muhafazakâr seçim.
        controlling = min(
            separated_names,
            key=lambda name: criteria[name]['area_ratio_sep'])
    base.update({
        'separated': bool(separated_names),
        'separated_criteria': separated_names,
        'controlling_criterion': controlling,
        'controlling_criterion_basis': (
            'Ayrılmayı en yukarıda (en küçük A/A_t) öngören kriter '
            'muhafazakâr seçimle kontrol eder.'),
        'x_sep_m': (criteria[controlling]['x_sep_m']
                    if controlling else None),
        'area_ratio_sep': (criteria[controlling]['area_ratio_sep']
                           if controlling else None),
        'criteria': criteria,
    })
    return base
