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
    öngörür. KU q3 beyanı (LULE-1a #3): "muhafazakâr" YALNIZ "tam dolu akış
    mı?" kararı içindir; ayrılmış Cf/Isp için erken ayrılma iyimser yönde
    olabilir, yanal ve yapısal yük konumu için yön belirsizdir.

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
    critical_pressures,
    isentropic_ratios,
    mach_from_area_ratio,
    mach_from_pressure_ratio,
)

__all__ = [
    'SEPARATION_NOT_MODELLED',
    'SUMMERFIELD_FACTOR_DEFAULT',
    'SUMMERFIELD_FACTOR_BAND',
    'SUMMERFIELD_FACTOR_ACCEPT_BAND',
    'SUMMERFIELD_NPR_BAND', 'SCHMUCKER_MACH_SEP_BAND',
    'KALT_BADAL_NPR_BAND', 'DERIVATION_BANDS',
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
#: Summerfield k'sının KABUL bandı (literatür bandından geniş: kullanıcı
#: deneyleri için). ÖH defter P6B3-03 — bu ikili eskiden
#: ``summerfield_pressure_ratio`` gövdesinde ÇIPLAK LİTERAL (0.2 / 0.6)
#: olarak duruyordu ve hrma.analysis.nozzle_flow_1d'deki
#: SEPARATION_FACTOR_MIN/MAX ikizinden sessizce ayrışabilirdi. Tek kaynak
#: burasıdır; ayrışma hrma.cfd.separation'daki SÜRÜKLENME KAPISINDA patlar.
SUMMERFIELD_FACTOR_ACCEPT_BAND = (0.2, 0.6)

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
        'modellenmedi; kriterler klasik FSS verisinden türetilmiştir. '
        'TOP/parabolik (Rao %80 benzeri) konturda RSS ve FSS↔RSS histerezisi '
        'olasıdır (Östlund 2002, §6.3.2); bu konturlarda karar FSS '
        'varsayımına dayanır.'),
    'hot_gas_conservatism': (
        'Kriterlerin muhafazakârlığı YALNIZ "tam dolu akış mı?" kararı '
        'içindir: sıcak gaz verisi (DLR P8 Calo ve BKE; Hagemann vd. 2003, '
        'Suslov vd. 2010) üç kriterin de tam dolu akış eşiğini muhafazakâr '
        'tarafta verdiğini gösterir; Schmucker büyük sıcak motor ortalamasını '
        '(üst taraf) temsil eder. Ayrılmış Cf/Isp için erken ayrılma iyimser '
        'olabilir; yanal/yapısal yük konumu için yön belirsizdir.'),
    'separation_margin_band': (
        'Marj bölgesi yoktur: karar ikilidir (P_e < P_sep). NASA SP-8120 '
        '§3.1.2.1.3 (s. 67-68) çıkış duvar basıncı ayrılma basıncına %20 '
        'yakınsa alan oranının düşürülmesini ya da konturun değiştirilmesini '
        'önerir; bu "marjinal" durum burada uyarı olarak üretilmez.'),
    'stark_criterion': (
        'Stark (2005) ölçütü P_sep/P_a = π/(3·M_sep) HESAPLANMAZ (bilgi '
        'satırı). Geniş soğuk + sıcak gaz veritabanına dayanan bu ölçüt, '
        'buradaki üç kriterin ayrılmayı daha YUKARI akışta (daha küçük '
        'alan oranında) öngördüğünü söyler.'),
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

#: Ölçütlerin TÜRETİM BANTLARI — ÖH defter P6B3-04.
#: Bu sayılar eskiden YALNIZ ``_VALIDITY`` düz metninde duruyordu ve
#: HİÇBİR kod onları okumuyordu: NPR = 5'te (Kalt-Badal bandı 10-1000,
#: Summerfield bandı 15-20) üç ölçüt de ``validity_warning = None``
#: yayımlıyordu — ölçüldü (a2/once.json). Sayılar artık hem metnin hem
#: hükmün TEK kaynağıdır; ikisi sessizce ayrışamaz.
#: Kaynaklar: Summerfield, Foster & Swan (1954) konik lüle verisi;
#: Schmucker (1973) / NASA TM-77396 / Östlund (2002) sıcak gaz bell lüle;
#: Kalt & Badal (1965) soğuk akış konik lüle deneyleri.
#: KU-K6 (6 Eki 2026, LULE-1a #5) — SCHMUCKER bandının künyesi: ÜST sınır
#: 4,5 Östlund (2002) Eş. 32-33'ün 2,5 ≤ M_i ≤ 4,5 aralığıyla uyumludur
#: (Schmucker 1984, TM-77396 s. 38: M_i ≤ 5, üstünde veri yok). ALT sınır
#: 1,5 KAYNAKSIZDIR: Schmucker verisi ortalama M_i ≈ 2,6-4,9'u kapsar
#: (Şek. 21/25 görsel okuma, LULE-1a notu) ve Stark & Wagner (2007)
#: ölçütlerini Ma > 2,5 için verir. Sayı DEĞİŞMEDİ (bant değişirse bant
#: dışı hükmü değişir — o karar ayrı kalemdir).
SUMMERFIELD_NPR_BAND = (15.0, 20.0)
SCHMUCKER_MACH_SEP_BAND = (1.5, 4.5)
KALT_BADAL_NPR_BAND = (10.0, 1000.0)

#: Ölçüt -> (büyüklüğün adı, bant). Bant denetimi tek döngüde çalışır.
DERIVATION_BANDS = {
    CRITERION_SUMMERFIELD: ('nozzle_pressure_ratio', SUMMERFIELD_NPR_BAND),
    CRITERION_SCHMUCKER: ('mach_sep', SCHMUCKER_MACH_SEP_BAND),
    CRITERION_KALT_BADAL: ('nozzle_pressure_ratio', KALT_BADAL_NPR_BAND),
}

_VALIDITY = {
    CRITERION_SUMMERFIELD: (
        f'Konik lüle verisi, lüle basınç oranı (P0/Pa) '
        f'~{SUMMERFIELD_NPR_BAND[0]:g}-{SUMMERFIELD_NPR_BAND[1]:g} '
        f'bandından; Mach ve basınç oranı bağımlılığı yok — yüksek basınç '
        f'oranında muhafazakâr (erken ayrılma) tarafta kalır — bu '
        f'muhafazakârlık "tam dolu akış mı?" kararı içindir, ayrılmış '
        f'Cf/Isp için değil. Eşik bandı '
        f'{SUMMERFIELD_FACTOR_BAND[0]:.2f}-{SUMMERFIELD_FACTOR_BAND[1]:.2f}.'),
    CRITERION_SCHMUCKER: (
        f'Sıcak gaz bell lüle verisinden (J-2/J-2S dahil); ayrılma Mach '
        f'sayısı ~{SCHMUCKER_MACH_SEP_BAND[0]:g}-'
        f'{SCHMUCKER_MACH_SEP_BAND[1]:g} bandında türetildi. Bandın '
        f'dışında dışkestirimdir.'),
    CRITERION_KALT_BADAL: (
        f'Soğuk akış konik lüle deneylerinden; lüle basınç oranı (P0/Pa) '
        f'~{KALT_BADAL_NPR_BAND[0]:g}-{KALT_BADAL_NPR_BAND[1]:g} bandı. '
        f'Sıcak gaz bell lülede dışkestirimdir.'),
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
    lo, hi = SUMMERFIELD_FACTOR_ACCEPT_BAND
    if not (lo <= f <= hi):
        raise ValueError(
            f'Summerfield eşiği fiziksel bandın çok dışında ({lo}-{hi} '
            f'kabul edilir; literatür bandı {SUMMERFIELD_FACTOR_BAND[0]}-'
            f'{SUMMERFIELD_FACTOR_BAND[1]}).')
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
        # P6B3-13: iki alan AYRI sözleşmedir ve şemada HER İKİ kriterde de
        # bulunur. wall_pressure_sep_Pa = bildirilen istasyonun duvar
        # basıncı; threshold_pressure_Pa = korelasyonun eşiği. Kırpılmamış
        # dalda ikisi TANIM GEREĞİ eşittir (istasyon P_sep'ten türetilir),
        # boğaza kırpılan dalda ayrışırlar.
        'wall_pressure_sep_Pa': float(P_sep),
        'threshold_pressure_Pa': float(P_sep),
        'pressure_ratio_threshold': float(P_sep / Pa),
        'mach_sep': None,
        'area_ratio_sep': None,
        'x_sep_m': None,
        'validity': _VALIDITY[name],
        'validity_warning': None,
        'outside_validity_band': False,
        'derivation_band': {
            'quantity': DERIVATION_BANDS[name][0],
            'low': float(DERIVATION_BANDS[name][1][0]),
            'high': float(DERIVATION_BANDS[name][1][1]),
        },
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
        # P6B3-13: ``wall_pressure_sep_Pa`` BİLDİRİLEN İSTASYONUN duvar
        # basıncıdır, korelasyonun eşiği değil. Konum boğaza kırpıldığında
        # bildirilen istasyon A/A* = 1'dir ve oradaki duvar basıncı
        # P₀·(2/(γ+1))^(γ/(γ−1))'dir — eşik P_sep DEĞİL. Ölçüldü (D25 a2,
        # ``docs/scofield/raw/OH/D25/fea-cfd/a2/once_a2.json`` → P6B3-13;
        # γ = 1,2, P₀ = 50 bar, P_a = 45 bar): kalt_badal bu dalda
        # 2,937445 MPa yazıyordu, boğazın gerçek duvar basıncı
        # 2,822370 MPa — %4,077 fark. Kardeş dal ``_criterion_schmucker``
        # AYNI kırpmada boğaz basıncını zaten doğru yazıyor (ölçülen sapma
        # %0,000); iki dal artık AYNI sözleşmeyi izler.
        # Eşiğin kendisi SİLİNMEZ: ``threshold_pressure_Pa`` alanında
        # ADIYLA durur (``pressure_ratio_threshold`` × P_a ile tutarlı).
        result['threshold_pressure_Pa'] = float(P_sep)
        result['wall_pressure_sep_Pa'] = float(P_throat)
        result['validity_warning'] = (
            'Eşik basıncı boğaz statik basıncının üstünde: kriter türetim '
            'bandının dışında, ayrılma konumu boğaza kırpıldı. '
            'wall_pressure_sep_Pa bildirilen istasyonun (A/A* = 1) GERÇEK '
            'duvar basıncıdır; korelasyonun eşiği threshold_pressure_Pa '
            'alanında ayrıca yayımlanır.')
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
        'threshold_pressure_Pa': None,
        'pressure_ratio_threshold': None,
        'mach_sep': None,
        'area_ratio_sep': None,
        'x_sep_m': None,
        'validity': _VALIDITY[name],
        'validity_warning': None,
        'outside_validity_band': False,
        'derivation_band': {
            'quantity': DERIVATION_BANDS[name][0],
            'low': float(DERIVATION_BANDS[name][1][0]),
            'high': float(DERIVATION_BANDS[name][1][1]),
        },
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
        # P6B3-13 sözleşmesi: eşik de ADIYLA yayımlanır (bu dal duvar
        # basıncını zaten doğru yazıyordu; eksik olan eşik alanıydı).
        result['threshold_pressure_Pa'] = float(
            Pa * schmucker_pressure_ratio(1.0))
        result['pressure_ratio_threshold'] = float(
            schmucker_pressure_ratio(1.0))
        result['validity_warning'] = (
            'Eşik boğazda zaten aşılmış: kriter türetim bandının dışında, '
            'ayrılma konumu boğaza kırpıldı. wall_pressure_sep_Pa '
            'bildirilen istasyonun (A/A* = 1) gerçek duvar basıncıdır; '
            'korelasyonun eşiği threshold_pressure_Pa alanındadır.')
    else:
        M_sep = brentq(gap, M_lo, M_exit, xtol=1e-12, maxiter=200)
        result['mach_sep'] = float(M_sep)
        result['area_ratio_sep'] = float(area_ratio_from_mach(M_sep, gamma))
        result['wall_pressure_sep_Pa'] = float(
            P0 * isentropic_ratios(M_sep, gamma)[1])
        result['pressure_ratio_threshold'] = float(
            schmucker_pressure_ratio(M_sep))
        # Kök koşulu gereği eşik = duvar basıncı (g(M_sep) = 0).
        result['threshold_pressure_Pa'] = float(
            Pa * schmucker_pressure_ratio(M_sep))
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

    # --- ÖH D16 / P6B3-01: REJİM KAPISI (BOĞULMAMIŞ AKIŞ) ----------------
    # Aşağıdaki satır ``supersonic=True`` diyerek TAM AKAN bir süpersonik
    # çekirdeği ZORLA kurar. Boğaz boğulmamışsa lülede hiçbir yerde ses-üstü
    # akış YOKTUR ve o çekirdek UYDURMADIR: ölçüldü (a1 ``once.json`` K5;
    # P0 = 20 bar, Pa = 0,995·P0, ε = 6, γ = 1,2) yarı-1B çözümün kendi maks
    # Mach'ı 0,72 iken bu blok ``separated=True`` ve
    # ``full_flow_exit.mach = 2,9173`` yayımlıyordu — ürün yüzünde
    # ``regime='subsonic_unchoked'``, ``throat.choked=False`` yazan AYNI
    # sonuç sözlüğünde.
    #
    # Üç ölçüt de (Summerfield / Schmucker / Kalt-Badal) AŞIRI GENLEŞMİŞ
    # SES-ÜSTÜ duvar sınır tabakası deneylerinden kalibrelidir; ses-altı
    # akışta varsayım "yaklaşık" değil TAMAMEN geçersizdir. Bu yüzden hüküm
    # fail-closed geri çekilir (``separated=None``) ve uydurma çekirdek
    # HİÇ yayımlanmaz — vakum dalındaki (Pa ≤ 0) beyan deseninin aynısı.
    #
    # Boğulma sınırı KOPYALANMIYOR: birinci kritik geri basınç modülün kendi
    # tek kaynağından (``quasi1d.critical_pressures``) alınır; ikinci bir
    # eşik bağıntısı yazılmadı.
    if Pa > 0.0:
        _krit = critical_pressures(eps_e, P0, g)
        _p_bogulma = float(_krit['choked_subsonic_exit_Pa'])
        if Pa >= _p_bogulma:
            return {
                'ambient_pressure_Pa': Pa,
                'separated': None,
                'separated_criteria': [],
                'controlling_criterion': None,
                'controlling_criterion_basis': None,
                'x_sep_m': None,
                'area_ratio_sep': None,
                'criteria': {},
                'full_flow_exit': None,
                'not_modelled': dict(SEPARATION_NOT_MODELLED),
                'not_applicable_reason': (
                    f'Boğaz BOĞULMAMIŞ: ortam basıncı {Pa:.6g} Pa, birinci '
                    f'kritik geri basınç {_p_bogulma:.6g} Pa (A_e/A_t = '
                    f'{eps_e:.4g}, γ = {g:.4g}) — P_ortam ≥ P_kritik olduğu '
                    'için lülede hiçbir yerde ses-üstü akış yoktur. Üç '
                    'ayrılma ölçütü de aşırı genleşmiş SES-ÜSTÜ duvar sınır '
                    'tabakası deneylerinden kalibrelidir; ses-altı rejimde '
                    'geçerli değildirler. Ayrılma hükmü VERİLMEZ ve tam-akan '
                    'süpersonik çekirdek (full_flow_exit) YAYIMLANMAZ — '
                    'var olmayan bir çekirdekten hüküm türetilmez.'),
                '_basis': (
                    'Boğulma sınırı hrma.flow.quasi1d.critical_pressures '
                    '(Anderson, Modern Compressible Flow, 3. baskı, Böl. '
                    '5.4) birinci kritiğidir; bu modülde ikinci kez '
                    'tanımlanmamıştır.'),
            }

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
    _uyarilar = {ad: [] for ad in _ALL_CRITERIA}
    if not (SUMMERFIELD_FACTOR_BAND[0] <= factor
            <= SUMMERFIELD_FACTOR_BAND[1]):
        _uyarilar[CRITERION_SUMMERFIELD].append(
            f'Seçilen eşik {factor:.2f}, literatür bandının '
            f'({SUMMERFIELD_FACTOR_BAND[0]:.2f}-'
            f'{SUMMERFIELD_FACTOR_BAND[1]:.2f}) dışında.')

    # --- TÜRETİM BANDI HÜKMÜ (ÖH defter P6B3-04) ------------------------
    # Bantlar ``_VALIDITY`` metninde YAZILIYDI ama HİÇBİR kod onları
    # okumuyordu: NPR = 5'te (Kalt-Badal 10-1000, Summerfield 15-20) üç
    # ölçüt de outside_validity_band = False yayımlıyordu. Sayı GİZLENMEZ
    # — dışkestirim olduğu ADIYLA söylenir; ölçüt bandın dışında da bir
    # gösterge verir ama artık "kalibreli" gibi okunamaz.
    npr = P0 / Pa
    for _ad in (CRITERION_SUMMERFIELD, CRITERION_KALT_BADAL):
        _lo, _hi = DERIVATION_BANDS[_ad][1]
        if not (_lo <= npr <= _hi):
            _uyarilar[_ad].append(
                f'Lüle basınç oranı NPR = P0/Pa = {npr:.4g}, ölçütün '
                f'türetim bandının ({_lo:g}-{_hi:g}) dışında: sonuç '
                f'DIŞKESTİRİMDİR.')
    # Schmucker'ın bandı AYRILMA MACH'ı üstündedir; ayrılma öngörülmediyse
    # o büyüklük tanımsızdır ve uydurma bir hüküm verilmez.
    _m_sep = criteria[CRITERION_SCHMUCKER].get('mach_sep')
    if criteria[CRITERION_SCHMUCKER]['separated'] and _m_sep is not None:
        _lo, _hi = DERIVATION_BANDS[CRITERION_SCHMUCKER][1]
        if not (_lo <= float(_m_sep) <= _hi):
            _uyarilar[CRITERION_SCHMUCKER].append(
                f'Ayrılma Mach sayısı M_sep = {float(_m_sep):.4g}, ölçütün '
                f'türetim bandının ({_lo:g}-{_hi:g}) dışında: sonuç '
                f'DIŞKESTİRİMDİR.')
    for _ad, _liste in _uyarilar.items():
        _var = criteria[_ad].get('validity_warning')
        if _var:                       # boğaza kırpma uyarısı korunur
            _liste = [_var] + _liste
        criteria[_ad]['validity_warning'] = (' '.join(_liste) if _liste
                                             else None)
        criteria[_ad]['outside_validity_band'] = bool(_liste)

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
