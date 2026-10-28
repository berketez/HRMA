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

from hrma.constants import R_UNIVERSAL
from hrma.data import burn_rate_db

__all__ = [
    'PROPELLANTS', 'ALIASES', 'REQUIRED_FIELDS', 'VALID_FAMILIES',
    'PROPELLANT_REFERENCE_PRESSURE_BAR', 'UNIVERSAL_GAS_CONSTANT',
    'get_propellant', 'get_propellant_safe', 'list_propellants',
    'list_propellant_keys', 'build_propellants_view', 'resolve',
    'burn_rate_mps', 'cstar_from_thermo', 'mm_mpa_to_m_bar',
    'PROPELLANT_FORM_FIELDS', 'propellant_form_values',
]

# ---------------------------------------------------------------------------
# Sabitler (magic number yasağı — tek tanım noktası)
# ---------------------------------------------------------------------------

# Rejim-parçalı yasası olan yakıtlarda (KNDX/KNSB) katalogda gösterilecek
# tek (a, n) çiftinin çözüldüğü referans basınç. SolidRocketEngine'in
# varsayılan tasarım basıncıyla (chamber_pressure=40 bar) aynıdır.
PROPELLANT_REFERENCE_PRESSURE_BAR: float = 40.0

# Evrensel gaz sabiti [J/(kmol*K)] — c* türetiminde kullanılır.
# ÖH D18 / altyapi (P10B3-10): yerel literal KALKTI, merkezî tanımdan gelir.
# Ad geriye uyum için korunur (bu modülü UNIVERSAL_GAS_CONSTANT adıyla
# okuyan çağıranlar var); tanım noktası artık tek: hrma/constants.py.
UNIVERSAL_GAS_CONSTANT: float = R_UNIVERSAL

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
    # V301/N-CEA-2: alt sınır 800 -> 700 m/s. Kara barutun NASA CEA c*'ı
    # (nominal kart, 10-150 bar) 784,6-788,7 m/s; eski sınır CEA'nın
    # kendi değerini reddederdi. 700 HRMA seçimi (ölçülen en düşük CEA
    # değerinin ~%11 altı). Motorun form bandı bu demeti okur
    # (PROPELLANT_C_STAR_RANGE_M_S).
    'c_star': (700.0, 2500.0),             # m/s
    'gamma': (1.05, 1.5),                  # -
    'flame_temperature': (1000.0, 4500.0),  # K
    'molecular_weight': (10.0, 80.0),      # kg/kmol
    'burn_rate_a': (1e-5, 1e-1),           # m/s @ 1 bar
    'burn_rate_n': (-1.0, 1.0),            # -
}

#: İtici YOĞUNLUK bandının KAMUYA AÇIK adı (kg/m^3).
#:
#: ÖH D15 / defter P9B3-11: ``.eng`` (RASP) dışa aktarımı da bu banda
#: ihtiyaç duyuyor — RASP başlığı motorun ZARFINI (çap x boy) ve YÜKLÜ
#: İTİCİ KÜTLESİNİ birlikte yazar, dolayısıyla ikisi bir ima edilen bulk
#: yoğunluk üretir. Band ikinci kez YAZILMAZ: doğrulayıcının kullandığı
#: ``_PHYSICAL_RANGES['density']`` demetinin kendisi yayımlanır.
PROPELLANT_DENSITY_RANGE_KG_M3: Tuple[float, float] = _PHYSICAL_RANGES[
    'density']

#: c* kabul bandı (m/s) — katalog doğrulayıcısı ve motorun 'char_velocity'
#: form bandı AYNI demeti okur (V301/N-CEA-2; eskiden motorda satır içi).
PROPELLANT_C_STAR_RANGE_M_S: Tuple[float, float] = _PHYSICAL_RANGES['c_star']


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
# iki kayıt arasında sayısal sapma yapısal olarak imkânsızdır. Motorun
# 'apcp' tablosu da (solid_rocket_engine._set_propellant_properties) bu
# kayıttan TÜRETİLİR; ikinci bir kopya yoktur (ÖH KİTAP p1b, B11).
#
# ÖH KİTAP p1b (B11, Ö-4) — SEÇENEK F (ana model kararı, 12 Eki 2026).
# Eski dörtlü (T_c 3614,8 K; c* 1598,2 m/s; gamma 1,1986; M 28,0) c*'tan tek
# gaz formülüyle GERİ ÇÖZÜLMÜŞ eşdeğer bir setti; T_c denge alev sıcaklığı
# değildi (+215,15 K). Termokimya artık aynı bileşimin TEK bir NASA CEA
# koşumundan gelir: AP 68 / Al 18 / HTPB R-45 14 (kütlece), Pc = 68,9 bar
# (≈1000 psia), sonsuz kesitli hazne (Gordon & McBride, NASA RP-1311 Part I,
# 1994, §6.1 ve Eş. 2.71-2.74, 6.11; RocketCEA 1.2.1 → CEA2). Kanıt:
# docs/scofield/raw/OH/KITAP/p1b/kanit/cea_P1B_68.9bar_eps10_{denge,donmus}.out
#   * flame_temperature, c_star, gamma, molecular_weight: KAYDIRMALI DENGE
#     dörtlüsü (oda T 3399,65 K; CSTAR 1585,4 m/s; oda GAMMAs 1,1338;
#     M(1/n) 27,829 kg/kmol, yoğuşkan faz dahil). Genleşme ve performans
#     (c* özdeşliği, C_F, ε, çıkış sıcaklığı) bu dörtlüyle yapılır.
#   * gamma_frozen_chamber: aynı koşumun DONMUŞ bileşimli oda GAMMAs'ı
#     (1,1862). Motor onu YALNIZ "donmuş" bileşim formülü cp = γR/(γ−1)'in
#     değerlendirildiği yerlerde kullanır (solid_rocket_engine.
#     _frozen_gas_gamma): Bartz gaz özellikleri (cp, Pr = 4γ/(9γ−5)), ısıl
#     analizin tepkime entalpisi ve iki faz modülünün gaz-yalnız gamma'sı
#     (2. tur, karar §28-36 Ş-2 A). Denge γ_s reaksiyon ısısını ve yoğuşkan
#     fazı içerir, bu formüllere girince cp'yi ×1,41 şişirir (rapor §3.1).
#     Bartz taşınım özelliklerinin kendisi (Eucken Pr ⟷ CEA taşınım) ayrı
#     kalemdir (rapor D-3, P4).
#: APCP referans setinin CEA koşum basıncı [bar] (künye metni bundan
#: türetilir; ≈1000 psia).
_APCP_CEA_CHAMBER_PRESSURE_BAR: float = 68.9

_APCP_REFERENCE: Dict[str, object] = {
    'density': 1810.0,
    'c_star': 1585.4,
    'gamma': 1.1338,
    'flame_temperature': 3399.65,
    'molecular_weight': 27.829,
    'gamma_frozen_chamber': 1.1862,
    # r[mm/s] = 5.0*(P[MPa])^0.35 -> motor konvansiyonu
    'burn_rate_a': mm_mpa_to_m_bar(5.0, 0.35),
    'burn_rate_n': 0.35,
    'burn_rate_ref': ("a' = 5.0 mm/s at 1 MPa, n = 0.35 (r = a'*P[MPa]^n); "
                      "stored here as r[m/s] = a*P[bar]^n. Typical AP/HTPB/Al "
                      "composite; [S&B] Ch. 12 burn-rate band."),
}


def _apcp_reference_source() -> str:
    """'apcp' künye metni — sayılar ``_APCP_REFERENCE``'tan TÜRETİLİR.

    ÖH KİTAP p1b (B11, 2. tur; denetim Ş-6, H-9): metin değerleri literal
    olarak ikinci kez yazmaz; kayıt değişirse künye onu izler (bekçi:
    tests/test_kitap_p1b.py::test_B11_kunye_metni_kayit_degerlerinden).
    Özdeşlik sapması da kaydın kendi dörtlüsünden hesaplanır.
    """
    ref = _APCP_REFERENCE
    ideal = cstar_from_thermo(ref['gamma'], ref['flame_temperature'],
                              ref['molecular_weight'])
    sapma_yuzde = 100.0 * (float(ref['c_star']) - ideal) / ideal
    return (
        'NASA CEA (Gordon & McBride, NASA RP-1311 Part I, 1994; '
        'RocketCEA 1.2.1 / CEA2): AP 68 / Al 18 / HTPB R-45 14 wt%, '
        f'Pc = {_APCP_CEA_CHAMBER_PRESSURE_BAR} bar, infinite-area chamber. '
        'Shifting-equilibrium '
        f"chamber T = {ref['flame_temperature']} K, "
        f"c* = {ref['c_star']} m/s, gamma_s = {ref['gamma']}, "
        f"M(1/n) = {ref['molecular_weight']} kg/kmol (condensed phase "
        'included); the quartet meets the [S&B] Eq. 3-32 single-phase '
        f'identity to {sapma_yuzde:.2f}% (two-phase). '
        f"gamma_frozen_chamber = {ref['gamma_frozen_chamber']} is the "
        'frozen-composition chamber gamma_s of the same run; the solver '
        'uses it only where the frozen-composition formula cp = '
        'gamma*R/(gamma-1) is evaluated: the Bartz gas properties (cp, Pr), '
        'the reaction enthalpy of the thermal analysis and the gas-only '
        'gamma of the two-phase loss module. Expansion and performance use '
        'the equilibrium gamma_s. '
        'One pressure only: the Tc dependence on motor pressure is '
        'not modelled.')


PROPELLANTS: Dict[str, Dict] = {

    # ---------------------- composite (AP based) ---------------------------
    'apcp': dict(
        _APCP_REFERENCE,
        key='apcp',
        name='APCP - Ammonium Perchlorate Composite (AP/Al/HTPB)',
        family='composite',
        oxidizer='Ammonium perchlorate (NH4ClO4), ~68%',
        fuel='Aluminum ~18% + HTPB binder ~14%',
        source=_apcp_reference_source(),
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
        source=('Shares the APCP reference set (identical formulation; '
                'NASA CEA quartet and frozen chamber gamma, see "apcp").'),
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
        # V301/N-CEA-2 K4 (26 Eki 2026): eski "tipik" bant (c* 1425,9,
        # gamma 1,22, T_c 2550, M 24,5; S&B Böl. 12) kaydın KENDİ nominal
        # bileşiminin NASA CEA çözümüyle değiştirildi: T_c -%10,2, c* -%5,7
        # (docs/scofield/raw/OH/V301/cea/RAPOR.md C2-K4). Değerler: RocketCEA
        # (CEA2), AP 85 / HTPB R-45 15 (APCP kanıt koşumunun R-45 kartı),
        # 68,9 bar (_APCP_CEA_CHAMBER_PRESSURE_BAR), kayan denge; M = 1/n.
        # Motor, bileşimi bildiği için kendi Pc'sinde CEA'yı yeniden koşar;
        # bu dörtlü CEA yokken kullanılan beyanlı tek basınçlı yedektir.
        'c_star': 1512.8,
        'gamma': 1.1894,
        'flame_temperature': 2838.9,
        'molecular_weight': 24.580,
        'source': ('NASA CEA (RocketCEA/CEA2), nominal composition AP 85 / '
                   'HTPB (R-45 card of the APCP evidence run) 15 wt%, 68.9 '
                   'bar, shifting equilibrium; M = 1/n. Nominal composition, '
                   'HRMA choice: the formulation is only given as ~85/~15 '
                   '(docs/scofield/raw/OH/V301/cea/kati-gecis).'),
        'notes': ('Removing aluminum lowers flame temperature and c* and '
                  'leaves an essentially smoke-free single-phase exhaust. '
                  'Thermochemistry is the CEA solution of the nominal '
                  'composition, not a measured value.'),
        'engine_key': None,
        'c_star_basis': 'cea',
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
        'c_star': 915.9,
        'gamma': 1.1220,
        'flame_temperature': 1713.1,
        'molecular_weight': 37.51,
        'source': ('Burn rate: [BRDB] regime fits (Nakka 1999/2001). '
                   'Thermochemistry: NASA CEA two-phase equilibrium, '
                   'Pc = 1000 psia, O/F = 65/35, K2CO3 condensation '
                   "included - the SAME basis and reference pressure the "
                   "'knsu' record uses. Reactant enthalpies of formation: "
                   'KNO3 from the CEA thermo.inp record KNO3(a) '
                   '(Gurvich 1982 pt1 p407, dHf = -494.0 kJ/mol); '
                   'alpha-D-glucose from the NIST Chemistry WebBook '
                   '(dHf(solid) = -1271.1 kJ/mol, Cox & Pilcher 1970 '
                   'reanalysis of Ponomarev & Migarskaya 1960). Density '
                   "from hrma/data/propellant_database.py entry 'kndx'."),
        'notes': ('Burn-rate law is pressure-regime piecewise (plateau/mesa); '
                  'the single (a, n) pair shown here is the regime resolved '
                  'at the catalogue reference pressure - use '
                  '/api/burn-rate/resolve for the design pressure. '
                  'Thermochemistry re-derived in v2.6.27 (OH-D19-22): the '
                  'previous set mixed a [NAKKA] table (Tc, M, k) with a c* '
                  'produced by the single-phase Eq. 3-32 identity, so the '
                  'declared condensed-phase fraction X_p = 0.44 could not '
                  'be inside that c*. The CEA run reproduces the published '
                  "'knsu' quadruple to 0.1%, and its KNDX flame temperature "
                  'agrees with the [NAKKA] table to 0.2%; the molecular '
                  'weight does not, because the two codes report it on '
                  'different conventions - the catalogue now carries the '
                  'CEA one throughout the sugar family.'),
        'engine_key': None,
        'c_star_basis': 'cea',
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
        'c_star': 911.3,
        'gamma': 1.1279,
        'flame_temperature': 1601.3,
        'molecular_weight': 35.41,
        'source': ('Burn rate: [BRDB] regime fits (Nakka 1999/2001). Ideal '
                   'density: [NAKKA] published KNSB equilibrium table. '
                   'Thermochemistry: NASA CEA two-phase equilibrium, '
                   'Pc = 1000 psia, O/F = 65/35, K2CO3 condensation '
                   "included - the SAME basis and reference pressure the "
                   "'knsu' record uses. Reactant enthalpies of formation: "
                   'KNO3 from the CEA thermo.inp record KNO3(a) '
                   '(Gurvich 1982 pt1 p407, dHf = -494.0 kJ/mol); sorbitol '
                   '(D-glucitol) from the NIST Chemistry WebBook '
                   '(dHf(solid) = -1353.7 +/- 1.4 kJ/mol, Gerasimov, Blokh '
                   '& Gubareva 1985).'),
        'notes': ('Same piecewise burn-rate caveat as KNDX. Density is the '
                  'ideal (void-free) value; cast grains typically reach '
                  '94-97% of it. Thermochemistry re-derived in v2.6.27 '
                  '(OH-D19-22) on the same CEA basis as KNDX and KNSU; the '
                  'CEA flame temperature agrees with the [NAKKA] KNSB table '
                  'to 0.1%, the molecular weight is reported on the CEA '
                  'convention used across the sugar family.'),
        'engine_key': None,
        'c_star_basis': 'cea',
        'validated': True,
    },

    'knsu': {
        'key': 'knsu',
        # ÖH D34 · OH-GT-17 — AD YOĞUNLUK TABANINI SÖYLER.
        # ÖLÇÜLDÜ (a1/once.json): bu satır ile 'sugar' satırının
        # burn_rate_a, burn_rate_n, c_star, gamma,
        # flame_temperature ve molecular_weight alanları BİREBİR
        # aynı; tek gerçek fark yoğunluk (1889 ⟷ 1785, +%5,83) ve
        # o fark seçim listesinde OKUNMUYORDU: bu satırın adı
        # yalnız '65/35' diyordu, ötekininki '65/35' bile demiyordu.
        # Kullanıcı iki satırdan birini seçerken itkiyi %5,83
        # kaydıran kararı kör veriyordu. Ada SAYI YAZILMAZ (tek
        # kaynak 'density' alanıdır), yalnız TABANIN ADI yazılır.
        # Aynı iki ad hrma/engines/solid_rocket_engine.py'de de
        # kuruluyordu; oradaki iki satır artık BU kaydı okuyor.
        'name': 'KNSU - Potassium Nitrate/Sucrose 65/35 '
                '(ideal/theoretical maximum density)',
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
        # ÖH D34 · OH-GT-17 — kardeş satırla aynı bileşim (65/35)
        # adında da yazılı; ayrım yoğunluk TABANINDA (bkz. 'knsu').
        'name': 'KNSU - Potassium Nitrate/Sucrose 65/35 '
                '(cast bulk density)',
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
        'c_star': 1406.8,   # ÖH D15 P2B1-01: Eq. 3-32 (gamma, T_c, M) ideali 1406,774; eski 1186,7 tek fazlı kayıtta mazeretsiz -%15,64 idi
        'gamma': 1.2612,
        'flame_temperature': 2789.3,
        'molecular_weight': 26.89,
        'source': '[ENG] double base reference set.',
        'notes': ('Typical burn rate; double-base propellants have a high '
                  'pressure exponent, so chamber pressure excursions are '
                  'strongly self-amplifying. Homogeneous propellant - '
                  'oxidizer and fuel are the same molecules.'),
        'engine_key': 'double_base',
        # ÖH D17 (P2B1-01): kayıt 'engine-reference' diyordu ve
        # tests/test_propellants_db.py'nin kimlik denetimi bu beyanla kaydı
        # ATLIYORDU (muafiyet). c* zaten Eq. 3-32 idealine çekilmişti
        # (1406,8 ⟷ 1406,7742, +%0,0018), yani beyan BAYATTI; doğru adıyla
        # yazıldı ve kayıt kimlik denetiminin İÇİNE girdi.
        'c_star_basis': 'eq3-32',
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
        # V301/N-CEA-2 K5 (26 Eki 2026): eski kayıt (c* 945,3, gamma 1,251,
        # T_c 2216,4, M 33,21; künye "[ENG] black powder reference set",
        # sayfasız, kaynağı bulunamadı) c*'ı CEA ideal dengesinin (~787 m/s)
        # %20 ÜSTÜNDEYDİ — ölçülmüş bir c* ideal dengeyi aşamaz. Değerler:
        # RocketCEA (CEA2), nominal KNO3 75 / C(gr) 15 / S 10, 1000 psia,
        # kayan denge; M = 1/n. DÜŞÜK GÜVEN: odun kömürü için kaynaklı bir
        # formül bulunamadı, kart grafit varsayıyor.
        'c_star': 787.1,
        'gamma': 1.0913,
        'flame_temperature': 1915.7,
        'molecular_weight': 65.411,
        'source': ('NASA CEA (RocketCEA/CEA2), nominal composition KNO3 75 / '
                   'charcoal 15 / sulfur 10 wt% with charcoal taken as '
                   'graphite C(gr), 1000 psia, shifting equilibrium; M = 1/n. '
                   'LOW CONFIDENCE: no sourced charcoal formula; the former '
                   'value (c* 945.3 m/s, unsourced) was above the CEA ideal '
                   'and was removed (docs/scofield/raw/OH/V301/cea/'
                   'kati-gecis).'),
        'notes': ('Typical burn rate. Pressed black powder is used for '
                  'ejection charges and small motors; heavy condensed-phase '
                  'products (K2CO3, K2S) give a low c*. Real charcoal carries '
                  'H and O and gives more gas than the graphite card.'),
        'engine_key': 'black_powder',
        # ÖH D17 (P2B1-01): 'engine-reference' bir MUAFİYET etiketiydi —
        # hiçbir test onu denetlemiyordu. Ölçülen c* tek fazlı Eq. 3-32
        # idealinin (1131,6563 m/s) %16,4676 ALTINDA; bu eksiklik kaydın
        # kendi yoğuşmuş faz kütle kesriyle (X_p = 0,55) sınırlıdır, yani
        # AÇIKLANMIŞTIR. Etiket artık ölçüyü adlandırıyor ve
        # _c_star_identity_audit ile denetleniyor.
        'c_star_basis': 'cea',
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
# c* ⟷ (gamma, T_c, M) özdeşlik denetimi — ÖH Z5S / P9B4-18
# ---------------------------------------------------------------------------
# Bulgu: 'double_base' kaydının c*'ı kendi (gamma, T_c, M) üçlüsünün Eq. 3-32
# ideal değerinin %15,64 ALTINDA. Modülün bu tür sapmalar için verdiği TEK
# gerekçe (cstar_from_thermo docstring'i: "İki fazlı (Al2O3, K2CO3 yoğuşmalı)
# yakıtlarda gerçek c* bunun ALTINDA kalır") bu kayda UYMUYOR: kaydın kendi
# 'fuel'/'notes' alanları yakıtın HOMOJEN (tek fazlı nitrat esteri) olduğunu
# söylüyor. Yani sapma vardı, gerekçesi yoktu ve okuyucu sapmayı hiç
# göremiyordu — c* ve üçlü yan yana basılıyor, tutarlıymış gibi duruyordu.
#
# Onarım BEYAN düzeyinde: HİÇBİR SAYI DEĞİŞMEZ (c*, gamma, T_c, M aynı).
# Sapma her kayıt için HESAPLANIP kayda iliştirilir (uydurulmuş değil,
# kaydın kendi sayılarından türetilmiş), gerekçesi olmayan kayıt bunu
# açıkça yazar. Alan kümesi tüm kayıtlarda aynı kalır (istemci sözleşmesi).
_CSTAR_NOTLARI: Dict[str, str] = {
    # ÖH D15 P2B1-01 (1 Eyl 2026): 'double_base' notu KALDIRILDI — c* 1186,7 → 1406,8
    # (Eq. 3-32 ideali 1406,774; sapma %0,002). Sözlük bilerek boş bırakıldı:
    # ileride beyanlı bir sapma doğarsa aynı kanaldan yayımlanır.
}


def _attach_cstar_identity_check() -> None:
    """Her kayda ideal c* ve sapmasını iliştirir (türetilmiş, yazılmamış)."""
    for key, rec in PROPELLANTS.items():
        ideal = cstar_from_thermo(rec['gamma'], rec['flame_temperature'],
                                  rec['molecular_weight'])
        rec['c_star_ideal_mps'] = ideal
        rec['c_star_ideal_deviation_pct'] = 100.0 * (
            float(rec['c_star']) - ideal) / ideal
        rec['c_star_deviation_note'] = _CSTAR_NOTLARI.get(key)


_attach_cstar_identity_check()


# ---------------------------------------------------------------------------
# Donmuş oda gamma'sı alanı — ÖH KİTAP p1b (B11, seçenek F)
# ---------------------------------------------------------------------------
# 'gamma_frozen_chamber' bugün yalnız APCP referans setinde (_APCP_REFERENCE)
# ölçülmüş bir değer taşır. İstemci sözleşmesi tüm kayıtların AYNI alan
# kümesini taşımasını ister (test_z5s_katalog_kapilari::
# test_kayit_sekli_tek_tip_kaldi); bu yüzden alan her kayda iliştirilir ve
# ölçülmüş değeri olmayan kayıtta None'dır. None "ayrı donmuş değer yok"
# demektir: motor o yakıtta Bartz gaz özelliklerini kaydın tek gamma'sından
# türetir (bugünkü davranış, bit-özdeş). Değer UYDURULMAZ.
#
# Fail-closed denetim: değer varsa sayısal olmalı, gamma bandında kalmalı ve
# kaydın denge gamma'sından KÜÇÜK olmamalı (kaydırmalı denge reaksiyon
# ısısını cp'ye katar, izantropik üssü düşürür: γ_s,denge ≤ γ_s,donmuş;
# RP-1311 Eş. 2.71-2.74).
GAMMA_FROZEN_CHAMBER_FIELD: str = 'gamma_frozen_chamber'


def _attach_frozen_chamber_gamma() -> None:
    """Her kayda donmuş oda gamma'sı alanını iliştirir (yoksa None)."""
    lo, hi = _PHYSICAL_RANGES['gamma']
    for key, rec in PROPELLANTS.items():
        value = rec.setdefault(GAMMA_FROZEN_CHAMBER_FIELD, None)
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(
                f"propellants_db record '{key}' field "
                f"'{GAMMA_FROZEN_CHAMBER_FIELD}' must be numeric or None, "
                f"got {type(value).__name__}")
        if not (lo <= float(value) <= hi):
            raise ValueError(
                f"propellants_db record '{key}' field "
                f"'{GAMMA_FROZEN_CHAMBER_FIELD}' = {value} is outside the "
                f"physical range [{lo}, {hi}]")
        if float(value) < float(rec['gamma']):
            raise ValueError(
                f"propellants_db record '{key}': frozen chamber gamma "
                f"{value} is below the equilibrium gamma {rec['gamma']}")


_attach_frozen_chamber_gamma()


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


#: Bir form sayfasının ön dolduracağı termokimya alanları (katalog alan
#: adlarıyla). Katı sayfasının JS haritası (``solid.html``
#: ``PROPELLANT_FIELD_MAP``) bu beş alanı aynı adlarla okur.
PROPELLANT_FORM_FIELDS: Tuple[str, ...] = (
    'density', 'flame_temperature', 'molecular_weight', 'gamma', 'c_star')


def propellant_form_values(key: str) -> Dict[str, float]:
    """Kaydın form ön doldurma sayıları — SALT OKUMA.

    ÖH KİTAP p1b 4. tur (14 Eki 2026, CLAUDE.md §11): katı sayfası
    ``APCP`` adını taşıyıp yoğunluk 1850, T_c 3200, M 28,5, γ 1,25,
    c* 1550 diye KATALOGDA OLMAYAN beş sayı yazıyordu (ikinci literal
    kopya). Sayfayı sunan görünüm bu sayıları artık buradan alır; şablon
    sayı yazmaz. Değerler kaydın kendisidir (``get_propellant`` kopyası),
    türetilmez, yuvarlanmaz.

    Args:
        key: kanonik anahtar ya da takma ad (``resolve`` kuralları).

    Returns:
        ``PROPELLANT_FORM_FIELDS`` alanı -> float. Kayıtta sonlu sayı
        olmayan alan sözlüğe KONMAZ: sayfa o alanı boş bırakır, sayı
        uydurulmaz.

    Raises:
        KeyError: bilinmeyen anahtar (sessiz boş sözlük yerine).
    """
    rec = get_propellant(key)
    out: Dict[str, float] = {}
    for alan in PROPELLANT_FORM_FIELDS:
        deger = rec.get(alan)
        if (isinstance(deger, (int, float)) and not isinstance(deger, bool)
                and math.isfinite(float(deger))):
            out[alan] = float(deger)
    return out


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
    """Kanonik + alias anahtarlı tam görünüm — HER anahtar TAZE kopya.

    ÖH Z5S / P9B4-20: docstring "taze kopyalar" diyordu ama alias anahtarı
    kanonik kaydın AYNI nesnesini paylaşıyordu (``v['ap'] is v['apcp']``
    -> True). Alias üzerinden yapılan tek bir yazma kanonik kaydı da
    bozuyordu; çağıran taraf "kopya aldım" sanıyordu. Beyan ile davranış
    burada davranış düzeltilerek birleştirildi.

    NOT — materials_db.build_materials_view BİLEREK ters yönde çalışır
    (alias kanonik kopyayla aynı nesnedir), çünkü orada KİMLİK TABANLI
    ters arama yapan bir tüketici var (heat_transfer_analysis.material_name).
    Bu modülün görünümünde öyle bir tüketici yok; paylaşım yalnız sessiz
    bozulma riski üretiyordu.
    """
    view = {k: deepcopy(rec) for k, rec in PROPELLANTS.items()}
    for alias, target in ALIASES.items():
        view[alias] = deepcopy(PROPELLANTS[target])
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
