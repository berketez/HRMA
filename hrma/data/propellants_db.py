"""
Merkezi katı yakıt (propellant) kataloğu — v2.5.2.

NEDEN VAR
---------
Katı yakıt özellikleri şu ana kadar ÜÇ ayrı yerde yaşıyordu:

  1. hrma/engines/solid_rocket_engine.py -> _set_propellant_properties()
     (rho, c*, gamma, T_c, MW; motorun gerçekten kullandığı referans set)
  2. hrma/data/propellant_database.py    -> PropellantDatabase.propellants
     (yoğunluk + birim etiketi olmayan a-n çiftleri; kaba gösterim)
  3. hrma/data/burn_rate_db.py           -> BURN_RATE_LAWS
     (KNDX/KNSB için birim-açık, rejim-parçalı ve DOĞRULANMIŞ a-n yasaları)

Kullanıcı arayüzü "yakıtı seç, özellikler kendiliğinden gelsin" isteğini
karşılamak için tek bir tabloya ihtiyaç duyar. Bu modül o tabloyu kurar ve
üç kaynağın ÇAKIŞMADIĞI bir birleşim üretir:

  * Termokimya (rho, c*, gamma, T_c, MW) motorun referans setinden BİREBİR
    kopyalanır — katalogtan seçilen değer motorun kullandığı değerdir.
  * Yanma hızı yasası olan yakıtlarda (KNDX, KNSB) a-n katsayıları
    burn_rate_db'den TÜRETİLİR (import anında), literal yazılmaz. Böylece
    merkezi yasa değişirse katalog otomatik izler; sapma fiziksel olarak
    imkânsızdır (CLAUDE.md kural 11 — parametre tutarlılığı).
  * propellant_database.py'deki birim-etiketsiz a-n çiftleri KULLANILMAZ
    (2026-07-18 fizik incelemesi bunların hiçbir birim yorumunda Nakka
    fitleriyle uyuşmadığını tespit etti).

BİRİM SÖZLEŞMESİ (tek ve zorunlu)
---------------------------------
    burn_rate_a, burn_rate_n:  r [m/s] = a * (P [bar]) ** n
Bu, SolidRocketEngine.calculate_burn_rate ve /api/burn-rate/resolve ile
AYNI konvansiyondur; katalog değeri doğrudan motora verilebilir.
Literatür genelde r [mm/s] = a' * (P [MPa])^n verir; dönüşüm:
    a = a' / (1000 * 10**n)                (bkz. BURN_RATE_MM_MPA_TO_M_BAR)

DÜRÜSTLÜK NOTU
--------------
Her kaydın 'validated' alanı, yanma hızı yasasının HRMA doğrulama
kayıtlarına karşı sınanıp sınanmadığını söyler:
    True  -> burn_rate_db rejim fiti (KNDX/KNSB; kaynak: Nakka 1999/2001)
    False -> gösterim amaçlı, literatür-tipik ('typical' notlu) değer
'validated: False' olan bir yakıtla yapılan yanma hızı hesabı tasarım
kararına temel alınmamalıdır; kullanıcıya bu ayrım UI'da gösterilebilsin
diye alan kayıt şemasının parçasıdır.
"""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Dict, List, Optional, Tuple

from hrma.data import burn_rate_db

__all__ = [
    'PROPELLANTS', 'ALIASES', 'REQUIRED_FIELDS', 'VALID_FAMILIES',
    'PROPELLANT_REFERENCE_PRESSURE_BAR', 'UNIVERSAL_GAS_CONSTANT',
    'get_propellant', 'get_propellant_safe', 'list_propellants',
    'list_propellant_keys', 'build_propellants_view', 'resolve',
    'burn_rate_mps', 'cstar_from_thermo', 'mm_mpa_to_m_bar',
]

# ---------------------------------------------------------------------------
# Sabitler (magic number yasağı — tek tanım noktası)
# ---------------------------------------------------------------------------

# Rejim-parçalı yasası olan yakıtlarda (KNDX/KNSB) katalogda gösterilecek
# tek (a, n) çiftinin çözüldüğü referans basınç. SolidRocketEngine'in
# varsayılan tasarım basıncıyla (chamber_pressure=40 bar) aynıdır.
PROPELLANT_REFERENCE_PRESSURE_BAR: float = 40.0

# Evrensel gaz sabiti [J/(kmol*K)] — c* türetiminde kullanılır.
UNIVERSAL_GAS_CONSTANT: float = 8314.462618

# r[mm/s] = a'*(P[MPa])^n  ->  r[m/s] = a*(P[bar])^n dönüşüm tabanı.
BURN_RATE_MM_MPA_TO_M_BAR: float = 1000.0  # mm->m; 10**n çarpanı n'e bağlıdır

# Kayıt şeması — eksik alan modül yüklenirken ValueError yükseltir.
REQUIRED_FIELDS: Tuple[str, ...] = (
    'key', 'name', 'family', 'oxidizer', 'fuel',
    'density', 'burn_rate_a', 'burn_rate_n', 'burn_rate_ref',
    'c_star', 'gamma', 'flame_temperature', 'molecular_weight',
    'source', 'notes',
)

# Yakıt aileleri — UI gruplama anahtarı.
VALID_FAMILIES = frozenset({'composite', 'sugar', 'double_base', 'other'})

# Fiziksel akıl-sağlığı bandı (doğrulama için; motorun _apply_overrides
# bandıyla uyumlu olmalı ki katalog değeri sessizce reddedilmesin).
_PHYSICAL_RANGES: Dict[str, Tuple[float, float]] = {
    'density': (500.0, 3000.0),            # kg/m^3
    'c_star': (800.0, 2500.0),             # m/s
    'gamma': (1.05, 1.5),                  # -
    'flame_temperature': (1000.0, 4500.0),  # K
    'molecular_weight': (10.0, 80.0),      # kg/kmol
    'burn_rate_a': (1e-5, 1e-1),           # m/s @ 1 bar
    'burn_rate_n': (-1.0, 1.0),            # -
}


def mm_mpa_to_m_bar(a_mm_mpa: float, n: float) -> float:
    """r[mm/s]=a'(P[MPa])^n katsayısını r[m/s]=a(P[bar])^n katsayısına çevirir."""
    return float(a_mm_mpa) / (BURN_RATE_MM_MPA_TO_M_BAR * 10.0 ** float(n))


def cstar_from_thermo(gamma: float, flame_temperature: float,
                      molecular_weight: float) -> float:
    """İdeal (tek fazlı) karakteristik hız — Sutton & Biblarz Eq. 3-32.

        c* = sqrt(R_u/M * T_c) / Gamma(gamma)
        Gamma = sqrt(g) * (2/(g+1))**((g+1)/(2*(g-1)))

    İki fazlı (Al2O3, K2CO3 yoğuşmalı) yakıtlarda gerçek c* bunun ALTINDA
    kalır; bu yüzden katalogta ölçülmüş/CEA c* varsa o kullanılır ve bu
    fonksiyon yalnızca tutarlılık denetiminde çağrılır.
    """
    g = float(gamma)
    vandenkerckhove = math.sqrt(g) * (2.0 / (g + 1.0)) ** (
        (g + 1.0) / (2.0 * (g - 1.0)))
    return math.sqrt(UNIVERSAL_GAS_CONSTANT / float(molecular_weight)
                     * float(flame_temperature)) / vandenkerckhove


# ---------------------------------------------------------------------------
# Katalog
# ---------------------------------------------------------------------------
# Kaynak kısaltmaları:
#   [ENG]  hrma/engines/solid_rocket_engine.py referans seti (CEA-tutarlı)
#   [BRDB] hrma/data/burn_rate_db.py (Nakka 1999/2001 rejim fitleri)
#   [S&B]  Sutton & Biblarz, Rocket Propulsion Elements, 9. baskı
#   [NAKKA] R. Nakka, Experimental Rocketry (nakka-rocketry.net) yayımlanmış
#           termokimya tabloları

# APCP referans seti TEK yerde tutulur; hem 'apcp' hem 'htpb_ap_al' aynı
# fiziksel yakıtı (AP/Al/HTPB) tarif eder ve değerleri buradan alır —
# iki kayıt arasında sayısal sapma yapısal olarak imkânsızdır.
_APCP_REFERENCE: Dict[str, object] = {
    'density': 1810.0,
    'c_star': 1598.2,
    'gamma': 1.1986,
    'flame_temperature': 3614.8,
    'molecular_weight': 28.0,
    # r[mm/s] = 5.0*(P[MPa])^0.35 -> motor konvansiyonu
    'burn_rate_a': mm_mpa_to_m_bar(5.0, 0.35),
    'burn_rate_n': 0.35,
    'burn_rate_ref': ("a' = 5.0 mm/s at 1 MPa, n = 0.35 (r = a'*P[MPa]^n); "
                      "stored here as r[m/s] = a*P[bar]^n. Typical AP/HTPB/Al "
                      "composite; [S&B] Ch. 12 burn-rate band."),
}

PROPELLANTS: Dict[str, Dict] = {

    # ---------------------- composite (AP based) ---------------------------
    'apcp': dict(
        _APCP_REFERENCE,
        key='apcp',
        name='APCP - Ammonium Perchlorate Composite (AP/Al/HTPB)',
        family='composite',
        oxidizer='Ammonium perchlorate (NH4ClO4), ~68%',
        fuel='Aluminum ~18% + HTPB binder ~14%',
        source=('[ENG] HRMA solid reference set (NASA CEA consistent, '
                'Pc = 68.9 bar); thermochemistry satisfies [S&B] Eq. 3-32 '
                'identity c* = sqrt(R*Tc)/Gamma exactly.'),
        notes=('Baseline composite used by the solver default. Burn-rate '
               'law is typical, not validated against HRMA records.'),
        engine_key='apcp',
        c_star_basis='cea',
        validated=False,
    ),

    'htpb_ap_al': dict(
        _APCP_REFERENCE,
        key='htpb_ap_al',
        name='HTPB/AP/Al Composite (aluminized)',
        family='composite',
        oxidizer='Ammonium perchlorate (NH4ClO4), ~68%',
        fuel='Aluminum ~18% + HTPB binder ~14%',
        source='[ENG] Shares the APCP reference set (identical formulation).',
        notes=('Composition-explicit key for the same propellant as "apcp"; '
               'values are shared by construction so the two entries can '
               'never drift apart.'),
        engine_key='apcp',
        c_star_basis='cea',
        validated=False,
    ),

    'apcp_nonaluminized': {
        'key': 'apcp_nonaluminized',
        'name': 'AP/HTPB Composite (non-aluminized)',
        'family': 'composite',
        'oxidizer': 'Ammonium perchlorate (NH4ClO4), ~85%',
        'fuel': 'HTPB binder ~15% (no metal fuel)',
        'density': 1700.0,
        'burn_rate_a': mm_mpa_to_m_bar(4.5, 0.36),
        'burn_rate_n': 0.36,
        'burn_rate_ref': ("a' = 4.5 mm/s at 1 MPa, n = 0.36 "
                          "(r = a'*P[MPa]^n); typical, indicative only."),
        'c_star': 1425.9,
        'gamma': 1.22,
        'flame_temperature': 2550.0,
        'molecular_weight': 24.5,
        'source': ('[S&B] Ch. 12 - non-metallized AP/HTPB property band; c* '
                   'from the Eq. 3-32 identity for the tabulated (gamma, '
                   'Tc, M), which is legitimate here because the exhaust is '
                   'essentially single phase.'),
        'notes': ('Typical values. Removing aluminum lowers flame '
                  'temperature and c* but leaves an essentially smoke-free '
                  'single-phase exhaust.'),
        'engine_key': None,
        'c_star_basis': 'eq3-32',
        'validated': False,
    },

    'pban_ap_al': {
        'key': 'pban_ap_al',
        'name': 'PBAN/AP/Al Composite (Shuttle SRB class)',
        'family': 'composite',
        'oxidizer': 'Ammonium perchlorate (NH4ClO4), ~70%',
        'fuel': 'Aluminum ~16% + PBAN binder ~14%',
        'density': 1790.0,
        'burn_rate_a': mm_mpa_to_m_bar(4.0, 0.32),
        'burn_rate_n': 0.32,
        'burn_rate_ref': ("a' = 4.0 mm/s at 1 MPa, n = 0.32 "
                          "(r = a'*P[MPa]^n); typical, indicative only."),
        'c_star': 1457.0,
        'gamma': 1.18,
        'flame_temperature': 3100.0,
        'molecular_weight': 27.5,
        'source': ('Density / flame temperature / exponent carried over from '
                   "hrma/data/propellant_database.py entry 'pban' "
                   '(NASA Space Shuttle SRB class); c* = 0.97 x the Eq. 3-32 '
                   'ideal value for that thermochemistry.'),
        'notes': ('Typical values. c* is deliberately held below the ideal '
                  'single-phase Eq. 3-32 result because condensed Al2O3 '
                  'does not expand with the gas. Published SRB c* figures '
                  'near 1590 m/s go with a higher flame temperature '
                  '(~3370 K) than the value carried in this repository, so '
                  'treat this entry as indicative.'),
        'engine_key': None,
        'c_star_basis': 'typical',
        'validated': False,
    },

    'blue_thunder': {
        'key': 'blue_thunder',
        'name': 'Fast Commercial Composite (Blue Thunder class)',
        'family': 'composite',
        'oxidizer': 'Ammonium perchlorate (NH4ClO4) with burn-rate catalyst',
        'fuel': 'Polyester / polyurethane binder (non-aluminized)',
        'density': 1750.0,
        'burn_rate_a': mm_mpa_to_m_bar(9.0, 0.40),
        'burn_rate_n': 0.40,
        'burn_rate_ref': ("a' = 9.0 mm/s at 1 MPa, n = 0.40 "
                          "(r = a'*P[MPa]^n); typical, indicative only."),
        'c_star': 1429.6,
        'gamma': 1.21,
        'flame_temperature': 2600.0,
        'molecular_weight': 25.0,
        'source': ('Generic fast-burning catalysed AP composite; property '
                   'band from [S&B] Ch. 12 - no manufacturer data sheet is '
                   'bundled with HRMA. c* from the Eq. 3-32 identity '
                   '(non-metallized, single-phase exhaust).'),
        'notes': ('Typical values, NOT a manufacturer specification. High '
                  'burn rate and high pressure exponent make this class '
                  'sensitive to erosive burning; treat results as '
                  'indicative.'),
        'engine_key': None,
        'c_star_basis': 'eq3-32',
        'validated': False,
    },

    # --------------------------- sugar family ------------------------------
    'kndx': {
        'key': 'kndx',
        'name': 'KNDX - Potassium Nitrate/Dextrose 65/35',
        'family': 'sugar',
        'oxidizer': 'Potassium nitrate (KNO3), 65%',
        'fuel': 'Dextrose (C6H12O6), 35%',
        'density': 1850.0,
        # a, n import anında burn_rate_db'den TÜRETİLİR (placeholder).
        'burn_rate_a': 0.0,
        'burn_rate_n': 0.0,
        'burn_rate_ref': '',
        'c_star': 912.4,
        'gamma': 1.1308,
        'flame_temperature': 1710.0,
        'molecular_weight': 42.39,
        'source': ('Burn rate: [BRDB] regime fits (Nakka 1999/2001). '
                   'Thermochemistry: [NAKKA] published KNDX equilibrium '
                   'table (Tc, M, k); density from '
                   "hrma/data/propellant_database.py entry 'kndx'."),
        'notes': ('Burn-rate law is pressure-regime piecewise (plateau/mesa); '
                  'the single (a, n) pair shown here is the regime resolved '
                  'at the catalogue reference pressure - use '
                  '/api/burn-rate/resolve for the design pressure.'),
        'engine_key': None,
        'c_star_basis': 'eq3-32',
        'validated': True,
    },

    'knsb': {
        'key': 'knsb',
        'name': 'KNSB - Potassium Nitrate/Sorbitol 65/35',
        'family': 'sugar',
        'oxidizer': 'Potassium nitrate (KNO3), 65%',
        'fuel': 'Sorbitol (C6H14O6), 35%',
        'density': 1841.0,
        'burn_rate_a': 0.0,
        'burn_rate_n': 0.0,
        'burn_rate_ref': '',
        'c_star': 908.1,
        'gamma': 1.1361,
        'flame_temperature': 1600.0,
        'molecular_weight': 39.9,
        'source': ('Burn rate: [BRDB] regime fits (Nakka 1999/2001). '
                   'Thermochemistry and ideal density: [NAKKA] published '
                   'KNSB equilibrium table.'),
        'notes': ('Same piecewise burn-rate caveat as KNDX. Density is the '
                  'ideal (void-free) value; cast grains typically reach '
                  '94-97% of it.'),
        'engine_key': None,
        'c_star_basis': 'eq3-32',
        'validated': True,
    },

    'knsu': {
        'key': 'knsu',
        'name': 'KNSU - Potassium Nitrate/Sucrose 65/35',
        'family': 'sugar',
        'oxidizer': 'Potassium nitrate (KNO3), 65%',
        'fuel': 'Sucrose (C12H22O11), 35%',
        'density': 1889.0,
        'burn_rate_a': mm_mpa_to_m_bar(8.26, 0.319),
        'burn_rate_n': 0.319,
        'burn_rate_ref': ("a' = 8.26 mm/s at 1 MPa, n = 0.319 "
                          "(r = a'*P[MPa]^n), single fit over the whole "
                          'pressure range; [NAKKA] KNSU.'),
        'c_star': 921.0,
        'gamma': 1.1235,
        'flame_temperature': 1719.0,
        'molecular_weight': 37.21,
        'source': ('[ENG] KNSU reference set (NASA CEA, two-phase K2CO3 '
                   'condensation included; matches [NAKKA] c* ~ 917 m/s and '
                   'Tc ~ 1720 K).'),
        'notes': ('Ideal (void-free) density. c* is the CEA two-phase value, '
                  'deliberately below the single-phase Eq. 3-32 result. '
                  'Burn-rate fit is not regime-split in HRMA records.'),
        'engine_key': 'knsu',
        'c_star_basis': 'cea',
        'validated': False,
    },

    'sugar': {
        'key': 'sugar',
        'name': 'KNSU - Potassium Nitrate/Sucrose (cast bulk density)',
        'family': 'sugar',
        'oxidizer': 'Potassium nitrate (KNO3), 65%',
        'fuel': 'Sucrose (C12H22O11), 35%',
        'density': 1785.0,
        'burn_rate_a': mm_mpa_to_m_bar(8.26, 0.319),
        'burn_rate_n': 0.319,
        'burn_rate_ref': ("a' = 8.26 mm/s at 1 MPa, n = 0.319 "
                          "(r = a'*P[MPa]^n); [NAKKA] KNSU."),
        'c_star': 921.0,
        'gamma': 1.1235,
        'flame_temperature': 1719.0,
        'molecular_weight': 37.21,
        'source': "[ENG] 'sugar' reference set (same chemistry as KNSU).",
        'notes': ('Identical chemistry to "knsu" but carries the cast bulk '
                  'density (~94% of ideal) that the solver uses for its '
                  '"sugar" propellant type - pick this one for hand-cast '
                  'grains, "knsu" for void-free theoretical mass.'),
        'engine_key': 'sugar',
        'c_star_basis': 'cea',
        'validated': False,
    },

    'kner': {
        'key': 'kner',
        'name': 'KNER - Potassium Nitrate/Erythritol 65/35',
        'family': 'sugar',
        'oxidizer': 'Potassium nitrate (KNO3), 65%',
        'fuel': 'Erythritol (C4H10O4), 35%',
        'density': 1820.0,
        'burn_rate_a': mm_mpa_to_m_bar(6.0, 0.30),
        'burn_rate_n': 0.30,
        'burn_rate_ref': ("a' = 6.0 mm/s at 1 MPa, n = 0.30 "
                          "(r = a'*P[MPa]^n); typical, indicative only - no "
                          'validated fit in HRMA records.'),
        'c_star': 922.6,
        'gamma': 1.1391,
        'flame_temperature': 1608.0,
        'molecular_weight': 38.78,
        'source': ('Thermochemistry and ideal density: [NAKKA] published '
                   'KNER equilibrium table. Burn rate: typical sugar-family '
                   'value, not validated.'),
        'notes': ('Typical burn rate. Erythritol casts at a lower '
                  'temperature than sorbitol, which is its main practical '
                  'advantage; use KNDX or KNSB when a validated burn-rate '
                  'law matters.'),
        'engine_key': None,
        'c_star_basis': 'eq3-32',
        'validated': False,
    },

    # ------------------------- double base / other -------------------------
    'double_base': {
        'key': 'double_base',
        'name': 'Double Base (Nitrocellulose/Nitroglycerin)',
        'family': 'double_base',
        'oxidizer': 'Self-oxidizing nitrate esters (NC + NG)',
        'fuel': 'Nitrocellulose + nitroglycerin matrix (homogeneous)',
        'density': 1580.0,
        'burn_rate_a': mm_mpa_to_m_bar(5.0, 0.70),
        'burn_rate_n': 0.70,
        'burn_rate_ref': ("a' = 5.0 mm/s at 1 MPa, n = 0.70 "
                          "(r = a'*P[MPa]^n); typical, indicative only."),
        'c_star': 1186.7,
        'gamma': 1.2612,
        'flame_temperature': 2789.3,
        'molecular_weight': 26.89,
        'source': '[ENG] double base reference set.',
        'notes': ('Typical burn rate; double-base propellants have a high '
                  'pressure exponent, so chamber pressure excursions are '
                  'strongly self-amplifying. Homogeneous propellant - '
                  'oxidizer and fuel are the same molecules.'),
        'engine_key': 'double_base',
        'c_star_basis': 'engine-reference',
        'validated': False,
    },

    'black_powder': {
        'key': 'black_powder',
        'name': 'Black Powder (KNO3/Charcoal/Sulfur)',
        'family': 'other',
        'oxidizer': 'Potassium nitrate (KNO3), ~75%',
        'fuel': 'Charcoal ~15% + sulfur ~10%',
        'density': 1650.0,
        'burn_rate_a': mm_mpa_to_m_bar(12.0, 0.30),
        'burn_rate_n': 0.30,
        'burn_rate_ref': ("a' = 12.0 mm/s at 1 MPa, n = 0.30 "
                          "(r = a'*P[MPa]^n); typical, indicative only."),
        'c_star': 945.3,
        'gamma': 1.251,
        'flame_temperature': 2216.4,
        'molecular_weight': 33.21,
        'source': '[ENG] black powder reference set (ballistics data).',
        'notes': ('Typical burn rate. Pressed black powder is used for '
                  'ejection charges and small motors; heavy condensed-phase '
                  'products make measured c* far below the ideal value.'),
        'engine_key': 'black_powder',
        'c_star_basis': 'engine-reference',
        'validated': False,
    },
}

# Yaygın kısaltmalar / eski anahtarlar -> kanonik kayıt.
ALIASES: Dict[str, str] = {
    'ap': 'apcp',
    'ap_htpb_al': 'htpb_ap_al',
    'htpb/ap/al': 'htpb_ap_al',
    'apcp_al': 'htpb_ap_al',
    'ap_htpb': 'apcp_nonaluminized',
    'apcp_no_al': 'apcp_nonaluminized',
    'pban': 'pban_ap_al',
    'kn_dx': 'kndx',
    'kn-dx': 'kndx',
    'kn_sb': 'knsb',
    'kn-sb': 'knsb',
    'kn_su': 'knsu',
    'kn-su': 'knsu',
    'kn_er': 'kner',
    'kn-er': 'kner',
    'dextrose': 'kndx',
    'sorbitol': 'knsb',
    'sucrose': 'knsu',
    'erythritol': 'kner',
    'db': 'double_base',
    'nc_ng': 'double_base',
    'bp': 'black_powder',
    'gunpowder': 'black_powder',
}


# ---------------------------------------------------------------------------
# Merkezi yanma hızı yasasının katalogla birleştirilmesi
# ---------------------------------------------------------------------------

def _apply_central_burn_rate_laws() -> None:
    """burn_rate_db yasası olan yakıtlarda a-n'i TÜRETİR (literal yazmaz).

    Böylece merkezi yasa güncellenirse katalog kendiliğinden izler; iki
    kaynak arasında sayısal çelişki oluşamaz. Yasası olmayan yakıtlar
    kendi (typical) literal değerlerinde kalır.
    """
    for key, rec in PROPELLANTS.items():
        if not burn_rate_db.has_law(key):
            continue
        coeffs = burn_rate_db.resolve_engine_coeffs(
            key, PROPELLANT_REFERENCE_PRESSURE_BAR)
        regime = coeffs['regime']
        rec['burn_rate_a'] = coeffs['a']
        rec['burn_rate_n'] = coeffs['n']
        rec['burn_rate_ref'] = (
            'r [m/s] = a * (P [bar])^n, resolved from the central '
            'burn_rate_db regime fit at '
            f'{PROPELLANT_REFERENCE_PRESSURE_BAR:.0f} bar '
            f'(valid regime {regime["p_min_mpa"]:.3f}-'
            f'{regime["p_max_mpa"]:.2f} MPa). Source: {coeffs["source"]}'
        )
        rec['has_regime_law'] = True
        rec['burn_rate_reference_pressure_bar'] = (
            PROPELLANT_REFERENCE_PRESSURE_BAR)
    # Tüm kayıtlar AYNI anahtar kümesini taşısın (istemci sözleşmesi tek
    # şekilli olsun): yasası olmayanlarda referans basınç None'dır.
    for rec in PROPELLANTS.values():
        rec.setdefault('has_regime_law', False)
        rec.setdefault('burn_rate_reference_pressure_bar', None)


_apply_central_burn_rate_laws()


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------

def _validate_propellants() -> None:
    """Şema + fiziksel bant + alias hedefi denetimi (yükleme anında).

    Amaç: yeni yakıt eklerken şema sapmasını import anında yakalamak,
    analiz ortasında sessiz KeyError yaşamamak.
    """
    for key, rec in PROPELLANTS.items():
        missing = [f for f in REQUIRED_FIELDS if f not in rec]
        if missing:
            raise ValueError(
                f"propellants_db record '{key}' is missing required "
                f"field(s): {missing} (schema: REQUIRED_FIELDS)")
        empty = [f for f in REQUIRED_FIELDS
                 if isinstance(rec[f], str) and not rec[f].strip()]
        if empty:
            raise ValueError(
                f"propellants_db record '{key}' has empty text field(s): "
                f"{empty}")
        if rec['key'] != key:
            raise ValueError(
                f"propellants_db record '{key}' carries mismatched "
                f"'key' field '{rec['key']}'")
        if rec['family'] not in VALID_FAMILIES:
            raise ValueError(
                f"propellants_db record '{key}' has invalid family "
                f"'{rec['family']}' (valid: {sorted(VALID_FAMILIES)})")
        for field, (lo, hi) in _PHYSICAL_RANGES.items():
            value = rec[field]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(
                    f"propellants_db record '{key}' field '{field}' must be "
                    f"numeric, got {type(value).__name__}")
            if not (lo <= float(value) <= hi):
                raise ValueError(
                    f"propellants_db record '{key}' field '{field}' = "
                    f"{value} is outside the physical range [{lo}, {hi}]")
    for alias, target in ALIASES.items():
        if target not in PROPELLANTS:
            raise ValueError(
                f"propellants_db alias '{alias}' points to unknown "
                f"record '{target}'")
        if alias in PROPELLANTS:
            raise ValueError(
                f"propellants_db alias '{alias}' shadows a canonical record")


_validate_propellants()


# ---------------------------------------------------------------------------
# Genel API
# ---------------------------------------------------------------------------

def resolve(key: str) -> str:
    """Alias'ı kanonik anahtara çevirir; bilinmeyen ad KeyError."""
    k = str(key).strip().lower()
    k = ALIASES.get(k, k)
    if k not in PROPELLANTS:
        raise KeyError(
            f"Unknown propellant '{key}'. Canonical keys: "
            f"{sorted(PROPELLANTS)}; aliases: {sorted(ALIASES)}")
    return k


def get_propellant(key: str) -> Dict:
    """Kaydın BAĞIMSIZ kopyasını döndürür (çağıran değiştirse DB bozulmaz)."""
    return deepcopy(PROPELLANTS[resolve(key)])


def get_propellant_safe(key: str) -> Optional[Dict]:
    """Bilinmeyen adda KeyError yerine None döndürür (UI yolu)."""
    try:
        return get_propellant(key)
    except KeyError:
        return None


def list_propellant_keys(family: Optional[str] = None) -> List[str]:
    """Kanonik anahtarları (alias'sız) alfabetik döndürür.

    family verilirse yalnız o aileden olanlar döner; geçersiz aile adı
    ValueError yükseltir (sessiz boş liste yerine).
    """
    if family is None:
        return sorted(PROPELLANTS)
    fam = str(family).lower()
    if fam not in VALID_FAMILIES:
        raise ValueError(
            f"Unknown propellant family '{family}' "
            f"(valid: {sorted(VALID_FAMILIES)})")
    return sorted(k for k, r in PROPELLANTS.items() if r['family'] == fam)


def list_propellants(family: Optional[str] = None) -> List[Dict]:
    """Kayıt kopyalarını alfabetik döndürür (UI listeleri için)."""
    return [get_propellant(k) for k in list_propellant_keys(family)]


def build_propellants_view() -> Dict[str, Dict]:
    """Kanonik + alias anahtarlı tam görünüm (taze kopyalar)."""
    view = {k: deepcopy(rec) for k, rec in PROPELLANTS.items()}
    for alias, target in ALIASES.items():
        view[alias] = view[target]
    return view


def burn_rate_mps(key: str, pressure_bar: float) -> float:
    """r [m/s] — rejim yasası varsa ONDAN, yoksa katalog (a, n) çiftinden.

    Merkezi yasası olan yakıtlarda (KNDX/KNSB) katalogtaki tek (a, n)
    çifti referans basınç rejimine aittir; başka bir basınçta doğru sonuç
    yalnız burn_rate_db'den gelir - bu sarmalayıcı o seçimi otomatik yapar.
    """
    k = resolve(key)
    p_bar = float(pressure_bar)
    if p_bar <= 0:
        raise ValueError('pressure_bar must be positive')
    if burn_rate_db.has_law(k):
        return burn_rate_db.burn_rate_mps(k, p_bar * 1e5)
    rec = PROPELLANTS[k]
    return float(rec['burn_rate_a']) * p_bar ** float(rec['burn_rate_n'])
