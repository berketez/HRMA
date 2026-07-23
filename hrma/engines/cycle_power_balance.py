"""Sıvı roket motoru ÇEVRİM GÜÇ DENGESİ çözücüsü.

2026-07-22 Raptor denetimi (Bölüm 2a/2b/2f) bulgusu: staged_combustion /
expander / tap_off seçimleri aynı gaz-jeneratörü hesabına düşüyor, güç
dengesi kapanmıyor, türbin debisi Isp'den düşülmüyor, FFSC yok, mil hep
tek. Bu modül her çevrimi KENDİ topolojisiyle ve kapanan güç dengesiyle
çözer. liquid_rocket_engine.py'ye entegrasyon sonraki adımdır; API bu
yüzden çağıran koddaki büyüklüklerle (pompa giriş basıncı, hat düşümleri,
enjektör ΔP oranı, rejeneratif ΔP) doğrudan eşleşecek biçimde tasarlandı.

Desteklenen çevrimler (``cycle_type``):

* ``pressure_fed``                 — pompa yok; tank basıncı yeterlilik kontrolü.
* ``gas_generator``                — açık çevrim; GG debisi güç dengesinden
                                     İTERATİF çözülür, Isp kaybı düşülür.
* ``tap_off``                      — açık çevrim; sıcak gaz ana odadan alınır.
* ``staged_combustion``            — kapalı çevrim, TEK ön yakıcı
                                     (``preburner_mode``: fuel_rich | ox_rich);
                                     türbin PR güç dengesinden çözülür.
* ``full_flow_staged_combustion``  — kapalı çevrim, İKİ mil / iki ön yakıcı;
                                     her mil için ayrı güç dengesi kapanır.
* ``expander``                     — kapalı çevrim; türbin gazı rejeneratif
                                     ceketten çıkan yakıt (ısı yükü girdi).

API kararı (belgeli): görev taslağındaki ``pump_dp_ox_bar`` /
``pump_dp_fuel_bar`` girdileri KALDIRILDI, çünkü kapalı çevrimlerde pompa
basınç yükselmesi bir SONUÇTUR (ön yakıcı basıncı + türbin PR + hat/enjektör
zincirinden çıkar), girdi olamaz. Bunun yerine zincirin bileşenleri girilir:
pompa giriş basınçları, hat düşümleri, enjektör ΔP oranı, rejeneratif ΔP.
Açık çevrimde de aynı zincir kullanılır; böylece iki tür çevrim aynı
sözleşmeyle çağrılır.

Fizik modeli ve kaynaklar:

* Pompa gücü  P = ṁ·ΔP/(ρ·η)                     (Sutton & Biblarz, "Rocket
  Propulsion Elements" 9th ed., Ch. 10; Huzel & Huang Ch. 6).
* Türbin özgül işi Δh = η_t·cp·T_in·(1 − PR^(−(γ−1)/γ)) (izentropik iş ×
  izentropik verim; Sutton 9th ed. Ch. 10, Eq. 10-19 civarı).
* Ön yakıcı / GG gaz özellikleri: NASA CEA (RocketCEA v1.2.x kurulu
  kütüphane) — Tc get_Tcomb'dan, DONMUŞ cp get_Chamber_Cp(frozen=1)'den;
  γ_frozen = cp/(cp − R/MW). Türbin genişlemesi donmuş kabul edilir
  (standart varsayım; Sutton Ch. 3 ve Ch. 10).
* GG / tap-off egzoz Isp'si: türbin çıkış koşulundan küçük nozulla ideal
  genişleme, v_e = sqrt(2·cp·T_e·(1 − (p_a/p_e)^((γ−1)/γ))) (Sutton Ch. 3).
* Açık çevrim Isp kaybı: debi-ağırlıklı karışım ortalaması,
  Isp_motor = ((ṁ_toplam − ṁ_bleed)·Isp_ana + ṁ_bleed·Isp_egzoz)/ṁ_toplam.
* Staged combustion basınç zinciri: türbin çıkışı ana enjektöre boşalır,
  p_türbin_çıkış = Pc·(1 + gaz enjektör ΔP oranı); ön yakıcı basıncı
  p_pb = p_türbin_çıkış × PR; pompa çıkışı = p_pb·(1 + ön yakıcı enjektör
  ΔP oranı) + hat/rejeneratif düşümleri (Sutton Ch. 6 çevrim şemaları;
  NASA SP-8107 "Turbopump Systems for Liquid Rocket Engines").
* FFSC topolojisi: iki bağımsız mil; TÜM oksitleyici ox-zengin ön
  yakıcıdan, TÜM yakıt yakıt-zengin ön yakıcıdan geçer (çapraz beslenen
  küçük akışlar pompa çıkışından alınır); ana odaya iki GAZ akışı girer
  (Raptor mimarisi; Sutton 9th ed. Ch. 6 full-flow şeması).

Sayısal çözüm: açık çevrimde ṁ_bleed sabit-nokta iterasyonu, kapalı
çevrimde türbin PR brentq köküyle bulunur; yakınsamama açık uyarı ve
``converged=False`` ile raporlanır. Model bir büyüklüğü çözemiyorsa
``not_modelled`` listesine etiket ekler — sahte sayı döndürmez.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

import numpy as np
from scipy.optimize import brentq

from hrma.constants import G_0, R_UNIVERSAL, PA_PER_BAR

# ---------------------------------------------------------------------------
# SABİTLER — hepsi kaynaklı (uydurma denetimi kuralı).
# ---------------------------------------------------------------------------

# Türbin giriş sıcaklığı (TIT) varsayılanları [K].
# * Gaz jeneratörü / tap-off: soğutmasız türbin pratiği 900-1100 K
#   (Sutton 9th ed. Ch. 10; NASA SP-8110 "Liquid Rocket Engine Turbines").
# * Yakıtça zengin ön yakıcı (staged): RS-25 ön yakıcıları ~1000 K sınıfı
#   (NASA RS-25/SSME verileri); varsayılan 900 K muhafazakar seçimdir.
# * Ox-zengin ön yakıcı: RD-170 ailesi ~772 K (Sutton 9th ed. Ch. 6 ORSC
#   anlatımı); varsayılan 750 K.
TIT_DEFAULT_K = {
    'gas_generator': 1000.0,
    'tap_off': 900.0,
    'staged_fuel_rich': 900.0,
    'staged_ox_rich': 750.0,
    'ffsc_fuel_rich': 900.0,
    'ffsc_ox_rich': 750.0,
    'expander': None,            # rejeneratif ısı yükünden hesaplanır
}
# Soğutmasız türbin kanadı pratik üst sınırı (Sutton Ch. 10 / SP-8110).
TIT_UNCOOLED_LIMIT_K = 1100.0
# Ox-zengin ortamda metal tutuşması riski nedeniyle pratik üst sınır
# (RD-170 uçuş pratiği ~772 K; Sutton 9th ed. Ch. 6).
TIT_OX_RICH_LIMIT_K = 850.0

# Enjektör ΔP oranları (ΔP/Pc).
# Sıvı enjeksiyon: chug kararlılığı için 0.15-0.20 (NASA SP-8089
# "Liquid Rocket Engine Injectors").
INJECTOR_DP_FRAC_LIQUID_DEFAULT = 0.20
# Sıcak gaz enjeksiyonu (türbin egzozu ana odaya): Huzel & Huang Ch. 4
# enjektör ΔP kılavuzunun alt bandı; VARSAYIM olarak etiketlenir.
INJECTOR_DP_FRAC_GAS_DEFAULT = 0.15
# Ön yakıcı / GG enjektörü ΔP oranı (SP-8089 alt bandı, varsayım).
INJECTOR_DP_FRAC_PREBURNER_DEFAULT = 0.15

# Açık çevrim türbin basınç oranı varsayılanı: F-1 GG türbini PR 16.4
# (Sutton 9th ed. Table 10-3 turbopump örnekleri); tipik GG türbinleri
# 10-25 aralığındadır.
OPEN_CYCLE_TURBINE_PR_DEFAULT = 16.0
# Tek gövdeli (çok sıralı impuls) türbinde pratik PR uyarı eşiği
# (Huzel & Huang Ch. 6).
OPEN_CYCLE_TURBINE_PR_WARN = 25.0

# Staged combustion türbin PR fizik aralığı: türbin ana odaya boşaldığı
# için PR küçük kalır (Sutton Ch. 6; denetim raporu Bölüm 2a).
STAGED_PR_TYPICAL = (1.3, 2.2)
# Kök arama aralığı (fizik aralığının dışına çıkılırsa uyarı üretilir).
PR_SOLVE_MIN, PR_SOLVE_MAX = 1.02, 4.0

# Pompa verim varsayılanı (Sutton 9th ed. Table 10-3; ana pompalar 0.65-0.80).
ETA_PUMP_DEFAULT = 0.75

# Türbin verimi ÇEVRİM SINIFINA bağlıdır — tek bir sabit fiziksel değildir.
# NASA SP-8110 "Liquid Rocket Engine Turbines" (1974), s. 17 ve fig. 13-14:
#   * Açık çevrim (gaz jeneratörü / tap-off): türbin YÜKSEK basınç oranında
#     (egzoz atmosfere) çalışan kısmi-giriş impuls kademesidir; iki sıralı
#     hız-bileşik türbinlerin ölçülen verimi %35-65 bandındadır.
#   * Kapalı çevrim (staged / full-flow staged / expander): türbin egzozu
#     ana odaya boşaldığı için basınç oranı DÜŞÜK tutulur; bu da türbini
#     "daha verimli hız-oranı bölgesinde" çalıştırır ve SP-8110'un birebir
#     ifadesiyle bu türbinler "%80'in üzerinde verime ulaşabilir".
# Ölçülen doğrulama (RS-25/SSME, Block IIA, Boeing/Rocketdyne SSME Orientation
# 1998): HPFTP türbini %81.1, HPOTP türbini %74.6. Kapalı çevrim varsayılanı
# bu iki ölçülen değerin ortasında (0.78) ve SP-8110 alt sınırının altında
# muhafazakâr seçilmiştir. Açık çevrim varsayılanı F-1 sınıfı GG türbini
# pratiğiyle uyumludur (Sutton 9th ed. Table 10-3).
ETA_TURBINE_OPEN_DEFAULT = 0.65
ETA_TURBINE_CLOSED_DEFAULT = 0.78
# Geriye dönük uyumluluk (eski tek-değer sabiti açık çevrim değerine eşittir).
ETA_TURBINE_DEFAULT = ETA_TURBINE_OPEN_DEFAULT

# Açık çevrim bleed oranı makullük sınırları: %25 üstü uyarı, %50 üstü
# yakınsamadı kabul edilir (tarihsel GG motorlarında oran %1.5-7;
# Sutton Ch. 6 çevrim karşılaştırması).
BLEED_FRACTION_WARN = 0.25
BLEED_FRACTION_FAIL = 0.50

# NBP sıvı yoğunlukları [kg/m³] — çağıran değer vermezse kullanılır.
# Kaynaklar: NIST WebBook (O2 @90.2 K, H2 @20.3 K, CH4 @111.7 K);
# RP-1: MIL-DTL-25576 (15 °C tipik).
DENSITY_NBP_KG_M3 = {
    'lox': 1141.0,
    'lh2': 70.85,
    'methane': 422.6,
    'rp1': 810.0,
}

# Yakıt molekül ağırlıkları [kg/kmol] (NIST): expander türbin gazı için.
FUEL_MOLAR_MASS_KG_KMOL = {'lh2': 2.016, 'methane': 16.043, 'rp1': 170.0}
# Yakıt NBP sıcaklıkları [K] (NIST WebBook): expander pompa girişi varsayımı.
FUEL_NBP_K = {'lh2': 20.3, 'methane': 111.7, 'rp1': 298.15}
# CoolProp akışkan adları (expander çevrimi gerçek gaz cp'si için).
COOLPROP_FLUID = {'lh2': 'Hydrogen', 'methane': 'Methane'}

# Ön yakıcı O/F kök arama aralıkları (CEA Tc eğrisi bu aralıklarda
# monotondur; uçlar CEA'nın yakınsadığı değerlerle sınandı).
FUEL_RICH_MR_BOUNDS = {'rp1': (0.05, 1.2), 'methane': (0.05, 1.8),
                       'lh2': (0.25, 3.5)}
OX_RICH_MR_BOUNDS = (4.5, 120.0)

# RocketCEA yakıt/oksitleyici ad eşlemesi.
_CEA_FUEL = {'rp1': 'RP1', 'methane': 'CH4', 'lh2': 'LH2'}
_CEA_OX = {'lox': 'LOX'}

_VALID_CYCLES = ('pressure_fed', 'gas_generator', 'tap_off',
                 'staged_combustion', 'full_flow_staged_combustion',
                 'expander')

_FUEL_SYNONYMS = {'rp1': 'rp1', 'rp-1': 'rp1', 'kerosene': 'rp1',
                  'methane': 'methane', 'ch4': 'methane', 'lch4': 'methane',
                  'lh2': 'lh2', 'hydrogen': 'lh2', 'h2': 'lh2'}
_OX_SYNONYMS = {'lox': 'lox', 'o2': 'lox', 'oxygen': 'lox'}

_CEA_CACHE: Dict = {}


def _norm_fuel(name: str) -> str:
    key = _FUEL_SYNONYMS.get(str(name).strip().lower())
    if key is None:
        raise ValueError(f"Unsupported fuel for the cycle solver: {name!r} "
                         f"(supported: rp1, methane, lh2)")
    return key


def _norm_ox(name: str) -> str:
    key = _OX_SYNONYMS.get(str(name).strip().lower())
    if key is None:
        raise ValueError(f"Unsupported oxidizer for the cycle solver: "
                         f"{name!r} (supported: lox)")
    return key


def _get_cea(fuel: str, oxidizer: str):
    """Önbellekli CEA_Obj; RocketCEA yoksa None (sahte sayı üretmez)."""
    key = (oxidizer, fuel)
    if key in _CEA_CACHE:
        return _CEA_CACHE[key]
    try:
        from rocketcea.cea_obj import CEA_Obj
        obj = CEA_Obj(oxName=_CEA_OX[oxidizer], fuelName=_CEA_FUEL[fuel])
    except Exception:
        obj = None
    _CEA_CACHE[key] = obj
    return obj


# BTU/(lbm·°R) -> J/(kg·K) (kesin dönüşüm, NIST birim tanımları).
_BTU_LBM_R_TO_J_KG_K = 4186.8
_BAR_TO_PSIA = 14.503773773


def preburner_gas_properties(fuel: str, oxidizer: str, mr: float,
                             p_bar: float) -> Optional[Dict]:
    """Ön yakıcı / GG yanma gazının (Tc, cp_frozen, γ_frozen, MW) seti.

    Kaynak: NASA CEA (RocketCEA). Türbin genişlemesi donmuş kabul edildiği
    için cp DONMUŞ değerdir; γ = cp/(cp − R/MW) termik mükemmel gaz
    bağıntısındandır. RocketCEA yoksa None döner (çağıran 'not_modelled'
    etiketler).
    """
    fuel = _norm_fuel(fuel)
    oxidizer = _norm_ox(oxidizer)
    cea = _get_cea(fuel, oxidizer)
    if cea is None:
        return None
    pc_psia = p_bar * _BAR_TO_PSIA
    t_k = float(cea.get_Tcomb(Pc=pc_psia, MR=mr)) / 1.8  # °R -> K
    mw, gamma_eq = cea.get_Chamber_MolWt_gamma(Pc=pc_psia, MR=mr, eps=2.0)
    cp = float(cea.get_Chamber_Cp(Pc=pc_psia, MR=mr, eps=2.0,
                                  frozen=1)) * _BTU_LBM_R_TO_J_KG_K
    r_sp = R_UNIVERSAL / float(mw)
    gamma_fr = cp / max(cp - r_sp, 1e-6)
    return {
        'temperature_K': t_k,
        'molecular_weight': float(mw),
        'cp_J_kgK': cp,
        'gamma': float(gamma_fr),
        'gamma_equilibrium': float(gamma_eq),
        'model': ('NASA CEA (RocketCEA) chamber solution; frozen cp, '
                  'gamma from cp/(cp - R/MW)'),
    }


def solve_preburner_of(fuel: str, oxidizer: str, p_bar: float, tit_K: float,
                       mode: str) -> Dict:
    """TIT kısıtından ön yakıcı O/F çözümü (CEA Tc eğrisi üstünde brentq).

    ``mode``: 'fuel_rich' (Tc, O/F ile artar) veya 'ox_rich' (stokiyometri
    üstünde Tc, O/F ile azalır). Kök aralık dışında kalırsa en yakın uca
    kırpılır ve uyarı döner.
    """
    fuel = _norm_fuel(fuel)
    oxidizer = _norm_ox(oxidizer)
    warnings: List[str] = []
    cea = _get_cea(fuel, oxidizer)
    if cea is None:
        return {'status': 'not_modelled', 'warnings': [
            'RocketCEA is not importable; preburner gas properties cannot '
            'be computed.']}
    pc_psia = p_bar * _BAR_TO_PSIA

    def t_of(mr):
        return float(cea.get_Tcomb(Pc=pc_psia, MR=mr)) / 1.8

    if mode == 'fuel_rich':
        lo, hi = FUEL_RICH_MR_BOUNDS[fuel]
        increasing = True
    elif mode == 'ox_rich':
        lo, hi = OX_RICH_MR_BOUNDS
        increasing = False
    else:
        raise ValueError(f"preburner mode must be 'fuel_rich' or 'ox_rich', "
                         f"got {mode!r}")

    t_lo, t_hi = t_of(lo), t_of(hi)
    t_min, t_max = (t_lo, t_hi) if increasing else (t_hi, t_lo)
    if tit_K <= t_min:
        mr = lo if increasing else hi
        warnings.append(
            f"Requested turbine inlet temperature {tit_K:.0f} K is below "
            f"the {t_min:.0f} K reachable at the O/F search bound; the "
            f"preburner O/F is clamped to {mr:g} and the resulting "
            f"temperature is {t_min:.0f} K.")
        props = preburner_gas_properties(fuel, oxidizer, mr, p_bar)
        return {'status': 'clamped', 'mr': mr, 'warnings': warnings,
                'gas': props}
    if tit_K >= t_max:
        mr = hi if increasing else lo
        warnings.append(
            f"Requested turbine inlet temperature {tit_K:.0f} K exceeds the "
            f"{t_max:.0f} K reachable at the O/F search bound; the "
            f"preburner O/F is clamped to {mr:g}.")
        props = preburner_gas_properties(fuel, oxidizer, mr, p_bar)
        return {'status': 'clamped', 'mr': mr, 'warnings': warnings,
                'gas': props}

    mr = float(brentq(lambda m: t_of(m) - tit_K, lo, hi, xtol=1e-10,
                      rtol=1e-12))
    props = preburner_gas_properties(fuel, oxidizer, mr, p_bar)
    return {'status': 'solved', 'mr': mr, 'warnings': warnings, 'gas': props}


def _turbine_specific_work(gas: Dict, tit_K: float, pr: float,
                           eta_turbine: float) -> float:
    """Gerçek türbin özgül işi [J/kg] (Sutton Ch. 10, izentropik iş × η)."""
    gamma = gas['gamma']
    x = (gamma - 1.0) / gamma
    return eta_turbine * gas['cp_J_kgK'] * tit_K * (1.0 - pr ** (-x))


def _turbine_exit_temp(gas: Dict, tit_K: float, pr: float,
                       eta_turbine: float) -> float:
    gamma = gas['gamma']
    x = (gamma - 1.0) / gamma
    return tit_K * (1.0 - eta_turbine * (1.0 - pr ** (-x)))


def _pump_power_w(mdot: float, dp_bar: float, rho: float, eta: float) -> float:
    """Pompa mil gücü [W]: P = ṁ·ΔP/(ρ·η) (Sutton Ch. 10)."""
    return mdot * max(dp_bar, 0.0) * PA_PER_BAR / (max(rho, 1e-9)
                                                   * max(eta, 1e-3))


def _exhaust_isp_s(gas: Dict, t_exit_K: float, p_exit_bar: float,
                   p_amb_bar: float) -> float:
    """Türbin egzozunun küçük nozulla ideal genişleme Isp'si [s].

    v_e = sqrt(2·cp·T_e·(1 − (p_a/p_e)^((γ−1)/γ))) (Sutton Ch. 3). Egzoz
    basıncı ortamın altındaysa genişleme yapılamaz; 0 döner (çağıran uyarır).
    """
    if p_exit_bar <= p_amb_bar:
        return 0.0
    gamma = gas['gamma']
    x = (gamma - 1.0) / gamma
    ve = np.sqrt(2.0 * gas['cp_J_kgK'] * max(t_exit_K, 1.0)
                 * (1.0 - (p_amb_bar / p_exit_bar) ** x))
    return float(ve / G_0)


@dataclass
class CycleSolution:
    """Çevrim güç dengesi çözümü.

    Tüm güçler W, basınçlar bar, debiler kg/s, sıcaklıklar K, Isp s.
    ``shafts`` mil başına pompa/türbin dökümüdür; ``power_residual_rel``
    |P_türbin − P_pompa| / P_pompa kapanma artığıdır (mil başına en kötüsü).
    """
    cycle_type: str
    converged: bool = False
    iterations: int = 0
    pump_discharge_ox_bar: Optional[float] = None
    pump_discharge_fuel_bar: Optional[float] = None
    pump_power_ox_W: float = 0.0
    pump_power_fuel_W: float = 0.0
    pump_power_total_W: float = 0.0
    turbine_power_total_W: float = 0.0
    turbine_mdot_total_kg_s: float = 0.0
    power_residual_rel: float = float('nan')
    shafts: List[Dict] = field(default_factory=list)
    preburners: List[Dict] = field(default_factory=list)
    main_chamber: Dict = field(default_factory=dict)
    isp_mode: str = 'not_modelled'
    isp_loss_s: Optional[float] = None
    isp_engine_s: Optional[float] = None
    secondary_exhaust_isp_s: Optional[float] = None
    required_tank_pressure_ox_bar: Optional[float] = None
    required_tank_pressure_fuel_bar: Optional[float] = None
    tank_pressure_margin_bar: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    not_modelled: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


def _flow_split(mdot: float, mr: float):
    """(ṁ_ox, ṁ_yakıt) — O/F tanımından."""
    m_ox = mdot * mr / (1.0 + mr)
    return m_ox, mdot - m_ox


def _shaft_dict(name, pumps, turbine, pump_power, turbine_power):
    resid = abs(turbine_power - pump_power) / max(pump_power, 1e-9)
    return {'name': name, 'pumps': pumps, 'turbine': turbine,
            'pump_power_W': pump_power, 'turbine_power_W': turbine_power,
            'power_residual_rel': resid}


def _pump_dict(propellant, mdot, inlet_bar, discharge_bar, power_w, eta,
               note=None):
    d = {'propellant': propellant, 'mdot_kg_s': mdot,
         'inlet_pressure_bar': inlet_bar, 'discharge_pressure_bar': discharge_bar,
         'dp_bar': discharge_bar - inlet_bar, 'power_W': power_w,
         'efficiency': eta}
    if note:
        d['note'] = note
    return d


def _turbine_dict(mdot, tit, p_in_bar, pr, gas, eta, dh, power_w):
    return {'mdot_kg_s': mdot, 'inlet_temp_K': tit,
            'inlet_pressure_bar': p_in_bar, 'pressure_ratio': pr,
            'exit_pressure_bar': p_in_bar / pr,
            'exit_temp_K': _turbine_exit_temp(gas, tit, pr, eta),
            'specific_work_J_kg': dh, 'efficiency': eta, 'power_W': power_w,
            'gas': gas}


def solve_cycle(cycle_type: str,
                pc_bar: float,
                mdot_total: float,
                mr: float,
                fuel: str,
                oxidizer: str = 'lox',
                *,
                rho_ox: Optional[float] = None,
                rho_fuel: Optional[float] = None,
                pump_inlet_ox_bar: float = 3.0,
                pump_inlet_fuel_bar: float = 3.0,
                line_dp_ox_bar: float = 2.0,
                line_dp_fuel_bar: float = 2.0,
                regen_dp_bar: float = 0.0,
                injector_dp_frac: float = INJECTOR_DP_FRAC_LIQUID_DEFAULT,
                gas_injector_dp_frac: float = INJECTOR_DP_FRAC_GAS_DEFAULT,
                preburner_injector_dp_frac: float =
                INJECTOR_DP_FRAC_PREBURNER_DEFAULT,
                eta_pump_ox: float = ETA_PUMP_DEFAULT,
                eta_pump_fuel: float = ETA_PUMP_DEFAULT,
                eta_turbine: Optional[float] = None,
                tit_K: Optional[float] = None,
                preburner_mode: str = 'fuel_rich',
                turbine_pr: Optional[float] = None,
                regen_heat_kw: Optional[float] = None,
                fuel_inlet_temp_K: Optional[float] = None,
                tank_pressure_bar: Optional[float] = None,
                ambient_pressure_bar: float = 1.01325,
                isp_main_s: Optional[float] = None) -> CycleSolution:
    """Çevrim güç dengesini çözer; ``CycleSolution`` döndürür.

    Zorunlu girdiler: çevrim tipi, ana oda basıncı [bar], toplam pompalanan
    debi [kg/s], ana oda O/F'i, yakıt/oksitleyici adları. Diğerleri makul,
    KAYNAKLI varsayılanlarla gelir ve çözümde ``assumptions`` listesine
    yazılır. ``isp_main_s`` verilirse açık çevrimlerde Isp kaybı hesaplanır;
    verilmezse kayıp 'not_modelled' etiketlenir (uydurulmaz).

    ``eta_turbine`` None bırakılırsa çevrim SINIFINA göre seçilir: açık çevrim
    (GG/tap-off) için 0.65, kapalı çevrim (staged/FFSC/expander) için 0.78.
    Gerekçe ve kaynak ETA_TURBINE_OPEN_DEFAULT / ETA_TURBINE_CLOSED_DEFAULT
    sabitlerinin başındadır (NASA SP-8110). Sayı verilirse aynen kullanılır.
    """
    if cycle_type not in _VALID_CYCLES:
        raise ValueError(f"Unknown cycle_type {cycle_type!r}; valid options: "
                         f"{', '.join(_VALID_CYCLES)}")
    fuel = _norm_fuel(fuel)
    oxidizer = _norm_ox(oxidizer)
    if pc_bar <= 0 or mdot_total <= 0 or mr <= 0:
        raise ValueError('pc_bar, mdot_total and mr must be positive')

    sol = CycleSolution(cycle_type=cycle_type)

    # Türbin verimi çevrim SINIFINA göre varsayılır (kullanıcı vermediyse).
    # Fiziksel gerekçe: açık çevrim türbinleri yüksek basınç oranlı kısmi-giriş
    # impuls kademesidir (%35-65), kapalı çevrim türbinleri düşük basınç oranlı
    # tam-giriş reaksiyon türbinidir ve %80 üzeri verime ulaşır (NASA SP-8110,
    # s. 17 ve fig. 13-14; RS-25 ölçülen 0.746-0.811). Tek bir 0.65 değeri
    # kapalı yüksek-Pc çevrimlerde türbin gücünü ~%20 eksik hesaplar ve güç
    # dengesini yüksek oda basıncında YALANCI olarak açık bırakır.
    if eta_turbine is None:
        if cycle_type in ('gas_generator', 'tap_off'):
            eta_turbine = ETA_TURBINE_OPEN_DEFAULT
            if cycle_type != 'pressure_fed':
                sol.assumptions.append(
                    f'Turbine efficiency assumed {eta_turbine:.2f} for the '
                    f'open cycle (high-pressure-ratio partial-admission '
                    f'impulse turbine; NASA SP-8110 fig. 13-14, 35-65% band).')
        else:
            eta_turbine = ETA_TURBINE_CLOSED_DEFAULT
            if cycle_type != 'pressure_fed':
                sol.assumptions.append(
                    f'Turbine efficiency assumed {eta_turbine:.2f} for the '
                    f'closed cycle (low-pressure-ratio full-admission reaction '
                    f'turbine; NASA SP-8110 p. 17 ">80%"; RS-25 measured HPFTP '
                    f'0.811 / HPOTP 0.746).')

    if rho_ox is None:
        rho_ox = DENSITY_NBP_KG_M3[oxidizer]
        sol.assumptions.append(
            f'Oxidizer density taken as the NBP value {rho_ox:g} kg/m3 '
            f'(NIST WebBook).')
    if rho_fuel is None:
        rho_fuel = DENSITY_NBP_KG_M3[fuel]
        sol.assumptions.append(
            f'Fuel density taken as the NBP value {rho_fuel:g} kg/m3 '
            f'(NIST WebBook / MIL-DTL-25576 for RP-1).')

    m_ox_total, m_fuel_total = _flow_split(mdot_total, mr)
    inj_dp_liq = injector_dp_frac * pc_bar
    inj_dp_gas = gas_injector_dp_frac * pc_bar
    sol.assumptions.append(
        f'Liquid injector pressure drop {injector_dp_frac:.0%} of Pc '
        f'(NASA SP-8089 chug-stability guidance 15-20%).')

    # ------------------------------------------------------------------
    # PRESSURE FED — pompa yok, tank basıncı yeterlilik kontrolü.
    # ------------------------------------------------------------------
    if cycle_type == 'pressure_fed':
        req_ox = pc_bar + inj_dp_liq + line_dp_ox_bar
        req_fuel = pc_bar + inj_dp_liq + line_dp_fuel_bar + regen_dp_bar
        sol.required_tank_pressure_ox_bar = req_ox
        sol.required_tank_pressure_fuel_bar = req_fuel
        sol.main_chamber = {
            'mdot_kg_s': mdot_total, 'mr': mr,
            'inlet_streams': [
                {'label': 'liquid oxidizer', 'mdot_kg_s': m_ox_total,
                 'pressure_bar': pc_bar + inj_dp_liq, 'phase': 'liquid'},
                {'label': 'liquid fuel', 'mdot_kg_s': m_fuel_total,
                 'pressure_bar': pc_bar + inj_dp_liq, 'phase': 'liquid'}]}
        sol.isp_mode = 'no_cycle_loss'
        sol.isp_loss_s = 0.0
        sol.isp_engine_s = isp_main_s
        sol.power_residual_rel = 0.0
        if tank_pressure_bar is None:
            sol.warnings.append(
                'Pressure-fed cycle: no tank pressure was supplied, so the '
                'feasibility margin cannot be checked; the required tank '
                'pressures are reported.')
            sol.converged = True
        else:
            margin = tank_pressure_bar - max(req_ox, req_fuel)
            sol.tank_pressure_margin_bar = margin
            sol.converged = margin >= 0.0
            if margin < 0.0:
                sol.warnings.append(
                    f'Pressure-fed cycle infeasible: tank pressure '
                    f'{tank_pressure_bar:g} bar is {-margin:.1f} bar below '
                    f'the {max(req_ox, req_fuel):.1f} bar required by the '
                    f'chamber, injector and line losses.')
        return sol

    # Ortak sıvı zincirleri (ana odaya sıvı basan hatlar için).
    disch_ox_main = pc_bar + inj_dp_liq + line_dp_ox_bar
    disch_fuel_main = pc_bar + inj_dp_liq + line_dp_fuel_bar + regen_dp_bar

    # ------------------------------------------------------------------
    # GAZ JENERATÖRÜ ve TAP-OFF — açık çevrimler.
    # ------------------------------------------------------------------
    if cycle_type in ('gas_generator', 'tap_off'):
        tit = float(tit_K if tit_K is not None else TIT_DEFAULT_K[cycle_type])
        if tit > TIT_UNCOOLED_LIMIT_K:
            sol.warnings.append(
                f'Turbine inlet temperature {tit:.0f} K exceeds the '
                f'{TIT_UNCOOLED_LIMIT_K:.0f} K uncooled-blade practical '
                f'limit (Sutton Ch. 10 / NASA SP-8110); blade cooling or a '
                f'lower gas-generator temperature is required.')
        if tit_K is None:
            sol.assumptions.append(
                f'Turbine inlet temperature assumed {tit:.0f} K '
                f'(uncooled-turbine practice, Sutton Ch. 10 / NASA SP-8110).')

        if cycle_type == 'gas_generator':
            # GG her iki pompa çıkışından beslenir; GG odası en düşük
            # çıkışın enjektör düşümü gerisindedir.
            p_gas = (min(disch_ox_main, disch_fuel_main)
                     / (1.0 + preburner_injector_dp_frac))
            source_name = 'gas_generator'
        else:
            # Tap-off: sıcak gaz ana odadan alınır; alım kanalı kaybı ihmal
            # edilir (varsayım).
            p_gas = pc_bar
            source_name = 'tap_off_bleed'
            sol.assumptions.append(
                'Tap-off duct pressure loss neglected; bleed gas enters the '
                'turbine at chamber pressure.')
            sol.assumptions.append(
                'Tap-off gas modelled as fuel-rich boundary-layer combustion '
                'products at the turbine temperature limit (J-2S flight '
                'practice; Sutton 9th ed. Ch. 6).')

        pb = solve_preburner_of(fuel, oxidizer, p_gas, tit, 'fuel_rich')
        sol.warnings.extend(pb.get('warnings', []))
        if pb.get('status') == 'not_modelled':
            sol.not_modelled += ['preburner_gas_properties', 'power_balance',
                                 'isp_loss']
            return sol
        gas = pb['gas']
        mr_gg = pb['mr']

        pr = float(turbine_pr if turbine_pr is not None
                   else OPEN_CYCLE_TURBINE_PR_DEFAULT)
        if turbine_pr is None:
            sol.assumptions.append(
                f'Open-cycle turbine pressure ratio assumed {pr:g} '
                f'(F-1 class gas-generator turbine, Sutton 9th ed. '
                f'Table 10-3).')
        if pr > OPEN_CYCLE_TURBINE_PR_WARN:
            sol.warnings.append(
                f'Turbine pressure ratio {pr:g} exceeds the practical '
                f'{OPEN_CYCLE_TURBINE_PR_WARN:g} single-body limit '
                f'(Huzel & Huang Ch. 6); a multi-stage unit is implied.')
        p_exit = p_gas / pr
        if p_exit <= ambient_pressure_bar:
            sol.warnings.append(
                f'Turbine exit pressure {p_exit:.2f} bar is not above the '
                f'ambient {ambient_pressure_bar:.2f} bar; the requested '
                f'pressure ratio cannot be realised and no exhaust thrust '
                f'is credited.')

        dh = _turbine_specific_work(gas, tit, pr, eta_turbine)

        # Sabit-nokta: bleed debisi güç gereksinimini (O/F bölüşümü yoluyla)
        # zayıfça etkiler; ṁ_bleed = P_pompa/Δh iterasyonu.
        mdot_bleed = 0.03 * mdot_total
        iters = 0
        for iters in range(1, 101):
            mdot_main = mdot_total - mdot_bleed
            if cycle_type == 'gas_generator':
                m_ox_b, m_f_b = _flow_split(mdot_bleed, mr_gg)
            else:
                # Tap-off gazı ana odadan alınır: pompalanan bölüşüm ana
                # O/F'te kalır.
                m_ox_b, m_f_b = _flow_split(mdot_bleed, mr)
            m_ox_mc, m_f_mc = _flow_split(mdot_main, mr)
            m_ox_pump = m_ox_mc + m_ox_b
            m_f_pump = m_f_mc + m_f_b
            p_ox = _pump_power_w(m_ox_pump, disch_ox_main - pump_inlet_ox_bar,
                                 rho_ox, eta_pump_ox)
            p_f = _pump_power_w(m_f_pump, disch_fuel_main - pump_inlet_fuel_bar,
                                rho_fuel, eta_pump_fuel)
            p_req = p_ox + p_f
            new_bleed = p_req / max(dh, 1e-9)
            if abs(new_bleed - mdot_bleed) <= 1e-13 * max(mdot_bleed, 1e-9):
                mdot_bleed = new_bleed
                break
            mdot_bleed = new_bleed
        sol.iterations = iters

        bleed_frac = mdot_bleed / mdot_total
        if bleed_frac > BLEED_FRACTION_FAIL:
            sol.converged = False
            sol.warnings.append(
                f'Open-cycle power balance does not close: the required '
                f'bleed flow is {bleed_frac:.0%} of the total flow. The '
                f'pump pressure rise or the turbine conditions are '
                f'infeasible for this cycle.')
            sol.not_modelled.append('power_balance')
            return sol
        if bleed_frac > BLEED_FRACTION_WARN:
            sol.warnings.append(
                f'Bleed flow fraction {bleed_frac:.0%} is far above the '
                f'1.5-7% historical gas-generator range (Sutton Ch. 6); '
                f'the design point is likely infeasible.')

        turbine_power = mdot_bleed * dh
        p_turbine_in = p_gas
        sol.pump_discharge_ox_bar = disch_ox_main
        sol.pump_discharge_fuel_bar = disch_fuel_main
        sol.pump_power_ox_W = p_ox
        sol.pump_power_fuel_W = p_f
        sol.pump_power_total_W = p_req
        sol.turbine_power_total_W = turbine_power
        sol.turbine_mdot_total_kg_s = mdot_bleed
        pumps = [
            _pump_dict('oxidizer', m_ox_pump, pump_inlet_ox_bar,
                       disch_ox_main, p_ox, eta_pump_ox),
            _pump_dict('fuel', m_f_pump, pump_inlet_fuel_bar,
                       disch_fuel_main, p_f, eta_pump_fuel)]
        turbine = _turbine_dict(mdot_bleed, tit, p_turbine_in, pr, gas,
                                eta_turbine, dh, turbine_power)
        sol.shafts = [_shaft_dict('main', pumps, turbine, p_req,
                                  turbine_power)]
        sol.power_residual_rel = sol.shafts[0]['power_residual_rel']
        if cycle_type == 'gas_generator':
            sol.preburners = [{
                'name': source_name, 'mode': 'fuel_rich', 'of_ratio': mr_gg,
                'pressure_bar': p_gas, 'temperature_K': gas['temperature_K'],
                'mdot_ox_kg_s': m_ox_b, 'mdot_fuel_kg_s': m_f_b,
                'mdot_total_kg_s': mdot_bleed, 'gas': gas}]
        mdot_main = mdot_total - mdot_bleed
        sol.main_chamber = {
            'mdot_kg_s': mdot_main, 'mr': mr,
            'inlet_streams': [
                {'label': 'liquid oxidizer',
                 'mdot_kg_s': _flow_split(mdot_main, mr)[0],
                 'pressure_bar': pc_bar + inj_dp_liq, 'phase': 'liquid'},
                {'label': 'liquid fuel',
                 'mdot_kg_s': _flow_split(mdot_main, mr)[1],
                 'pressure_bar': pc_bar + inj_dp_liq, 'phase': 'liquid'}]}

        # Açık çevrim Isp kaybı: düşük Isp'li egzozla karışım ortalaması.
        t_exit = _turbine_exit_temp(gas, tit, pr, eta_turbine)
        isp_gg = _exhaust_isp_s(gas, t_exit, p_exit, ambient_pressure_bar)
        sol.secondary_exhaust_isp_s = isp_gg
        if isp_main_s is not None:
            isp_engine = ((mdot_main * isp_main_s + mdot_bleed * isp_gg)
                          / mdot_total)
            sol.isp_engine_s = isp_engine
            sol.isp_loss_s = isp_main_s - isp_engine
            sol.isp_mode = 'open_cycle_mixture_average'
        else:
            sol.isp_mode = 'not_modelled'
            sol.not_modelled.append('isp_loss')
            sol.warnings.append(
                'Main-chamber Isp was not supplied (isp_main_s); the '
                'open-cycle Isp loss is not modelled rather than guessed.')
        sol.converged = True
        return sol

    # ------------------------------------------------------------------
    # STAGED COMBUSTION — tek ön yakıcı, kapalı çevrim.
    # ------------------------------------------------------------------
    if cycle_type == 'staged_combustion':
        if preburner_mode not in ('fuel_rich', 'ox_rich'):
            raise ValueError("preburner_mode must be 'fuel_rich' or "
                             "'ox_rich'")
        if preburner_mode == 'ox_rich' and fuel == 'lh2':
            sol.warnings.append(
                'Oxidizer-rich preburner with LH2 has no flight precedent '
                'and the CEA ox-rich fit is unvalidated for this pair; '
                'results should be treated with caution.')
        default_key = ('staged_fuel_rich' if preburner_mode == 'fuel_rich'
                       else 'staged_ox_rich')
        tit = float(tit_K if tit_K is not None else TIT_DEFAULT_K[default_key])
        limit = (TIT_UNCOOLED_LIMIT_K if preburner_mode == 'fuel_rich'
                 else TIT_OX_RICH_LIMIT_K)
        if tit > limit:
            sol.warnings.append(
                f'Preburner temperature {tit:.0f} K exceeds the '
                f'{limit:.0f} K practical limit for a {preburner_mode} '
                f'preburner (Sutton Ch. 6/10; RD-170 practice for ox-rich).')
        if tit_K is None:
            sol.assumptions.append(
                f'Preburner temperature assumed {tit:.0f} K '
                f'({preburner_mode}; RS-25 / RD-170 class practice).')

        p_te = pc_bar + inj_dp_gas          # türbin çıkışı ana enjektöre
        sol.assumptions.append(
            f'Turbine exhaust feeds the main injector with a hot-gas '
            f'pressure drop of {gas_injector_dp_frac:.0%} of Pc '
            f'(Huzel & Huang Ch. 4 injector guidance; assumption).')

        # O/F, ön yakıcı basıncına zayıf bağlıdır -> dış iterasyon.
        p_pb_guess = p_te * 1.7
        pr_root = None
        pb = None
        detail = {}
        for outer in range(6):
            pb = solve_preburner_of(fuel, oxidizer, p_pb_guess, tit,
                                    preburner_mode)
            if pb.get('status') == 'not_modelled':
                sol.warnings.extend(pb.get('warnings', []))
                sol.not_modelled += ['preburner_gas_properties',
                                     'power_balance']
                return sol
            gas = pb['gas']
            mr_pb = pb['mr']
            if preburner_mode == 'fuel_rich':
                pb_fuel = m_fuel_total
                pb_ox = mr_pb * pb_fuel
                if pb_ox > m_ox_total:
                    sol.warnings.append(
                        'Preburner oxidizer demand exceeds the total '
                        'oxidizer flow; the temperature constraint cannot '
                        'be met at this engine mixture ratio.')
                    sol.not_modelled.append('power_balance')
                    return sol
            else:
                pb_ox = m_ox_total
                pb_fuel = pb_ox / mr_pb
                if pb_fuel > m_fuel_total:
                    sol.warnings.append(
                        'Preburner fuel demand exceeds the total fuel flow; '
                        'the temperature constraint cannot be met at this '
                        'engine mixture ratio.')
                    sol.not_modelled.append('power_balance')
                    return sol
            mdot_turb = pb_ox + pb_fuel

            def powers(pr):
                p_pb = p_te * pr
                pb_feed = p_pb * (1.0 + preburner_injector_dp_frac)
                if preburner_mode == 'fuel_rich':
                    d_fuel = pb_feed + regen_dp_bar + line_dp_fuel_bar
                    d_ox_boost = pb_feed + line_dp_ox_bar
                    p_fp = _pump_power_w(m_fuel_total,
                                         d_fuel - pump_inlet_fuel_bar,
                                         rho_fuel, eta_pump_fuel)
                    # Oksitleyici: ana kademe ana oda zincirine, küçük ön
                    # yakıcı akışı ek (boost) kademeyle ön yakıcı basıncına
                    # (RS-25 HPOTP ana+boost mimarisi; NASA SP-8107).
                    p_op = (_pump_power_w(m_ox_total,
                                          disch_ox_main - pump_inlet_ox_bar,
                                          rho_ox, eta_pump_ox)
                            + _pump_power_w(pb_ox,
                                            max(d_ox_boost - disch_ox_main,
                                                0.0),
                                            rho_ox, eta_pump_ox))
                    d_ox_report = max(disch_ox_main, d_ox_boost)
                    d_fuel_report = d_fuel
                else:
                    d_ox = pb_feed + line_dp_ox_bar
                    d_fuel_boost = pb_feed + line_dp_fuel_bar + regen_dp_bar
                    p_op = _pump_power_w(m_ox_total,
                                         d_ox - pump_inlet_ox_bar,
                                         rho_ox, eta_pump_ox)
                    p_fp = (_pump_power_w(m_fuel_total,
                                          disch_fuel_main
                                          - pump_inlet_fuel_bar,
                                          rho_fuel, eta_pump_fuel)
                            + _pump_power_w(pb_fuel,
                                            max(d_fuel_boost
                                                - disch_fuel_main, 0.0),
                                            rho_fuel, eta_pump_fuel))
                    d_ox_report = d_ox
                    d_fuel_report = max(disch_fuel_main, d_fuel_boost)
                p_avail = mdot_turb * _turbine_specific_work(gas, tit, pr,
                                                             eta_turbine)
                return (p_avail, p_op + p_fp, p_op, p_fp, d_ox_report,
                        d_fuel_report, p_pb)

            def resid(pr):
                p_avail, p_req = powers(pr)[:2]
                return p_avail - p_req

            # İlk işaret değişimini ara (alçak PR kökü fiziksel çözümdür).
            grid = np.linspace(PR_SOLVE_MIN, PR_SOLVE_MAX, 40)
            vals = [resid(g) for g in grid]
            bracket = None
            for a, b, fa, fb in zip(grid[:-1], grid[1:], vals[:-1], vals[1:]):
                if fa <= 0.0 <= fb or fa >= 0.0 >= fb:
                    bracket = (a, b)
                    break
            if bracket is None:
                # En iyi (en küçük açık) durum türbin gücü artığının TEPE
                # noktasıdır; PR_SOLVE_MAX'taki artık değil (artık PR* sonrası
                # yeniden düşer). Eksiği tepe noktasından raporla.
                best_pr = float(grid[int(np.argmax(vals))])
                best_deficit = -max(vals) / 1e6
                turb_frac = mdot_turb / mdot_total
                sol.warnings.append(
                    f'Staged-combustion power balance does not close for any '
                    f'turbine pressure ratio in [{PR_SOLVE_MIN:g}, '
                    f'{PR_SOLVE_MAX:g}]. At the {tit:.0f} K {preburner_mode} '
                    f'preburner limit only {mdot_turb:.0f} of {mdot_total:.0f} '
                    f'kg/s ({turb_frac:.0%}) drives the single turbine, so its '
                    f'power ceiling stays {best_deficit:.1f} MW below the pump '
                    f'demand even at the most favourable pressure ratio '
                    f'(PR={best_pr:.2f}); raising the pressure ratio further '
                    f'only widens the gap. A single preburner passes only part '
                    f'of the propellant through the turbine, so this chamber '
                    f'pressure is out of reach at the material temperature '
                    f'limit. Full-flow staged combustion (all propellant '
                    f'through two turbines) removes this limit — which is why '
                    f'high-pressure methane engines such as Raptor use the '
                    f'full-flow architecture rather than a single preburner.')
                sol.not_modelled.append('power_balance')
                sol.converged = False
                return sol
            pr_root = float(brentq(resid, bracket[0], bracket[1],
                                   xtol=1e-13, rtol=1e-15))
            detail = dict(zip(('p_avail', 'p_req', 'p_op', 'p_fp',
                               'd_ox', 'd_fuel', 'p_pb'), powers(pr_root)))
            if abs(detail['p_pb'] - p_pb_guess) / p_pb_guess < 1e-3:
                break
            p_pb_guess = detail['p_pb']
        sol.iterations = outer + 1
        sol.warnings.extend(pb.get('warnings', []))

        if not (STAGED_PR_TYPICAL[0] <= pr_root <= STAGED_PR_TYPICAL[1]):
            sol.warnings.append(
                f'Solved turbine pressure ratio {pr_root:.2f} lies outside '
                f'the {STAGED_PR_TYPICAL[0]:g}-{STAGED_PR_TYPICAL[1]:g} '
                f'range typical of staged-combustion turbines '
                f'(Sutton Ch. 6).')

        gas = pb['gas']
        mr_pb = pb['mr']
        dh = _turbine_specific_work(gas, tit, pr_root, eta_turbine)
        sol.pump_discharge_ox_bar = detail['d_ox']
        sol.pump_discharge_fuel_bar = detail['d_fuel']
        sol.pump_power_ox_W = detail['p_op']
        sol.pump_power_fuel_W = detail['p_fp']
        sol.pump_power_total_W = detail['p_req']
        sol.turbine_power_total_W = detail['p_avail']
        sol.turbine_mdot_total_kg_s = mdot_turb
        pumps = [
            _pump_dict('oxidizer', m_ox_total, pump_inlet_ox_bar,
                       detail['d_ox'], detail['p_op'], eta_pump_ox,
                       note=('main stage to the chamber chain plus a boost '
                             'stage for the preburner flow'
                             if preburner_mode == 'fuel_rich' else None)),
            _pump_dict('fuel', m_fuel_total, pump_inlet_fuel_bar,
                       detail['d_fuel'], detail['p_fp'], eta_pump_fuel,
                       note=('main stage to the chamber chain plus a boost '
                             'stage for the preburner flow'
                             if preburner_mode == 'ox_rich' else None))]
        turbine = _turbine_dict(mdot_turb, tit, detail['p_pb'], pr_root, gas,
                                eta_turbine, dh, detail['p_avail'])
        sol.shafts = [_shaft_dict('main', pumps, turbine, detail['p_req'],
                                  detail['p_avail'])]
        sol.power_residual_rel = sol.shafts[0]['power_residual_rel']
        sol.preburners = [{
            'name': 'preburner', 'mode': preburner_mode, 'of_ratio': mr_pb,
            'pressure_bar': detail['p_pb'],
            'temperature_K': gas['temperature_K'],
            'mdot_ox_kg_s': pb_ox, 'mdot_fuel_kg_s': pb_fuel,
            'mdot_total_kg_s': mdot_turb, 'gas': gas}]
        t_exit = _turbine_exit_temp(gas, tit, pr_root, eta_turbine)
        if preburner_mode == 'fuel_rich':
            liquid = {'label': 'liquid oxidizer',
                      'mdot_kg_s': m_ox_total - pb_ox,
                      'pressure_bar': pc_bar + inj_dp_liq, 'phase': 'liquid'}
            gas_label = 'fuel-rich preburner products (turbine exhaust)'
        else:
            liquid = {'label': 'liquid fuel',
                      'mdot_kg_s': m_fuel_total - pb_fuel,
                      'pressure_bar': pc_bar + inj_dp_liq, 'phase': 'liquid'}
            gas_label = 'ox-rich preburner products (turbine exhaust)'
        sol.main_chamber = {
            'mdot_kg_s': mdot_total, 'mr': mr,
            'inlet_streams': [
                {'label': gas_label, 'mdot_kg_s': mdot_turb,
                 'pressure_bar': p_te, 'temperature_K': t_exit,
                 'phase': 'gas'}, liquid]}
        # Kapalı çevrim: türbin gazı ana odada yanar; Isp cezası yok
        # (enerji sistemde kalır — Sutton Ch. 6).
        sol.isp_mode = 'closed_cycle_no_loss'
        sol.isp_loss_s = 0.0
        sol.isp_engine_s = isp_main_s
        sol.converged = True
        return sol

    # ------------------------------------------------------------------
    # FFSC — iki mil, iki ön yakıcı, kapalı çevrim.
    # ------------------------------------------------------------------
    if cycle_type == 'full_flow_staged_combustion':
        tit_f = float(tit_K if tit_K is not None
                      else TIT_DEFAULT_K['ffsc_fuel_rich'])
        tit_ox = float(TIT_DEFAULT_K['ffsc_ox_rich'])
        if tit_K is None:
            sol.assumptions.append(
                f'Preburner temperatures assumed {tit_f:.0f} K (fuel-rich '
                f'shaft) and {tit_ox:.0f} K (ox-rich shaft); RS-25 / RD-170 '
                f'class practice.')
        else:
            # Kullanıcı TIT'i yakıt-zengin mile uygulanır; ox-zengin taraf
            # kendi malzeme sınırıyla kalır.
            sol.assumptions.append(
                f'User turbine inlet temperature {tit_f:.0f} K applied to '
                f'the fuel-rich shaft; the ox-rich shaft keeps the '
                f'{tit_ox:.0f} K material limit.')
        if tit_f > TIT_UNCOOLED_LIMIT_K:
            sol.warnings.append(
                f'Fuel-rich preburner temperature {tit_f:.0f} K exceeds the '
                f'{TIT_UNCOOLED_LIMIT_K:.0f} K uncooled-blade limit '
                f'(Sutton Ch. 10 / NASA SP-8110).')

        p_te = pc_bar + inj_dp_gas
        sol.assumptions.append(
            f'Both turbine exhausts feed the main injector as gas with a '
            f'{gas_injector_dp_frac:.0%} of Pc hot-gas injector drop '
            f'(assumption; Huzel & Huang Ch. 4).')
        sol.assumptions.append(
            'Cross feeds (fuel to the ox-rich preburner, oxidizer to the '
            'fuel-rich preburner) are tapped from the opposite pump '
            'discharge; their extra boost power is not modelled separately '
            '(small flows, Raptor-style architecture).')

        # Ön yakıcı O/F'leri (basınca zayıf bağlılık -> dış iterasyon).
        p_fpb_guess, p_opb_guess = p_te * 1.7, p_te * 1.7
        shaft_results = {}
        pb_f = pb_ox = None
        for outer in range(6):
            pb_f = solve_preburner_of(fuel, oxidizer, p_fpb_guess, tit_f,
                                      'fuel_rich')
            pb_ox = solve_preburner_of(fuel, oxidizer, p_opb_guess, tit_ox,
                                       'ox_rich')
            if (pb_f.get('status') == 'not_modelled'
                    or pb_ox.get('status') == 'not_modelled'):
                sol.warnings.extend(pb_f.get('warnings', []))
                sol.warnings.extend(pb_ox.get('warnings', []))
                sol.not_modelled += ['preburner_gas_properties',
                                     'power_balance']
                return sol
            mr_fpb, mr_opb = pb_f['mr'], pb_ox['mr']
            # Akış bölüşümü (kapalı form): x = ox ön yakıcısına giden yakıt,
            # y = yakıt ön yakıcısına giden oksitleyici.
            # y = mr_fpb·(m_f − x); x = (m_ox − y)/mr_opb
            denom = 1.0 - mr_fpb / mr_opb
            x = ((m_ox_total - mr_fpb * m_fuel_total) / mr_opb) / denom
            x = float(np.clip(x, 0.0, m_fuel_total))
            y = mr_fpb * (m_fuel_total - x)
            fpb_fuel = m_fuel_total - x
            fpb_ox = y
            opb_ox = m_ox_total - y
            opb_fuel = x
            mdot_turb_f = fpb_fuel + fpb_ox
            mdot_turb_ox = opb_ox + opb_fuel

            def solve_shaft(gas, tit, mdot_turb, pump_mdot, rho, eta_pump,
                            inlet_bar, extra_dp_bar):
                """Tek milin PR kökü: türbin gücü = pompa gücü."""
                def powers(pr):
                    p_pb = p_te * pr
                    disch = (p_pb * (1.0 + preburner_injector_dp_frac)
                             + extra_dp_bar)
                    p_pump = _pump_power_w(pump_mdot, disch - inlet_bar,
                                           rho, eta_pump)
                    p_avail = mdot_turb * _turbine_specific_work(
                        gas, tit, pr, eta_turbine)
                    return p_avail, p_pump, disch, p_pb

                def resid(pr):
                    p_avail, p_pump = powers(pr)[:2]
                    return p_avail - p_pump

                grid = np.linspace(PR_SOLVE_MIN, PR_SOLVE_MAX, 40)
                vals = [resid(g) for g in grid]
                for a, b, fa, fb in zip(grid[:-1], grid[1:], vals[:-1],
                                        vals[1:]):
                    if fa <= 0.0 <= fb or fa >= 0.0 >= fb:
                        pr = float(brentq(resid, a, b, xtol=1e-13,
                                          rtol=1e-15))
                        p_avail, p_pump, disch, p_pb = powers(pr)
                        return {'pr': pr, 'p_avail': p_avail,
                                'p_pump': p_pump, 'discharge_bar': disch,
                                'p_pb': p_pb}
                # Kök yok: en iyi (en küçük açık) durumu teşhis için döndür.
                return {'pr': None, 'best_deficit_W': -max(vals),
                        'best_pr': float(grid[int(np.argmax(vals))]),
                        'mdot_turb': mdot_turb}

            res_f = solve_shaft(pb_f['gas'], tit_f, mdot_turb_f,
                                m_fuel_total, rho_fuel, eta_pump_fuel,
                                pump_inlet_fuel_bar,
                                regen_dp_bar + line_dp_fuel_bar)
            res_ox = solve_shaft(pb_ox['gas'], tit_ox, mdot_turb_ox,
                                 m_ox_total, rho_ox, eta_pump_ox,
                                 pump_inlet_ox_bar, line_dp_ox_bar)
            if res_f['pr'] is None or res_ox['pr'] is None:
                bad = res_f if res_f['pr'] is None else res_ox
                side = 'fuel-rich' if res_f['pr'] is None else 'oxidizer-rich'
                sol.warnings.append(
                    f'FFSC {side} shaft power balance does not close for any '
                    f'turbine pressure ratio in [{PR_SOLVE_MIN:g}, '
                    f'{PR_SOLVE_MAX:g}]. Its {bad["mdot_turb"]:.0f} kg/s '
                    f'turbine flow at the preburner temperature limit leaves a '
                    f'{bad["best_deficit_W"] / 1e6:.1f} MW power shortfall '
                    f'against the pump even at the most favourable pressure '
                    f'ratio (PR={bad["best_pr"]:.2f}); a higher pressure ratio '
                    f'only widens the gap. The cycle is infeasible at this '
                    f'design point with the given efficiencies and temperature '
                    f'limits.')
                sol.not_modelled.append('power_balance')
                sol.converged = False
                return sol
            shaft_results = {'fuel': res_f, 'ox': res_ox}
            if (abs(res_f['p_pb'] - p_fpb_guess) / p_fpb_guess < 1e-3
                    and abs(res_ox['p_pb'] - p_opb_guess) / p_opb_guess
                    < 1e-3):
                break
            p_fpb_guess, p_opb_guess = res_f['p_pb'], res_ox['p_pb']
        sol.iterations = outer + 1
        sol.warnings.extend(pb_f.get('warnings', []))
        sol.warnings.extend(pb_ox.get('warnings', []))

        for name, res in shaft_results.items():
            if not (STAGED_PR_TYPICAL[0] <= res['pr']
                    <= STAGED_PR_TYPICAL[1]):
                sol.warnings.append(
                    f'FFSC {name}-shaft turbine pressure ratio '
                    f"{res['pr']:.2f} lies outside the "
                    f'{STAGED_PR_TYPICAL[0]:g}-{STAGED_PR_TYPICAL[1]:g} '
                    f'range typical of staged-combustion turbines '
                    f'(Sutton Ch. 6).')

        res_f, res_ox = shaft_results['fuel'], shaft_results['ox']
        gas_f, gas_o = pb_f['gas'], pb_ox['gas']
        dh_f = _turbine_specific_work(gas_f, tit_f, res_f['pr'], eta_turbine)
        dh_o = _turbine_specific_work(gas_o, tit_ox, res_ox['pr'],
                                      eta_turbine)
        sol.pump_discharge_fuel_bar = res_f['discharge_bar']
        sol.pump_discharge_ox_bar = res_ox['discharge_bar']
        sol.pump_power_fuel_W = res_f['p_pump']
        sol.pump_power_ox_W = res_ox['p_pump']
        sol.pump_power_total_W = res_f['p_pump'] + res_ox['p_pump']
        sol.turbine_power_total_W = res_f['p_avail'] + res_ox['p_avail']
        sol.turbine_mdot_total_kg_s = mdot_turb_f + mdot_turb_ox
        fuel_shaft = _shaft_dict(
            'fuel',
            [_pump_dict('fuel', m_fuel_total, pump_inlet_fuel_bar,
                        res_f['discharge_bar'], res_f['p_pump'],
                        eta_pump_fuel)],
            _turbine_dict(mdot_turb_f, tit_f, res_f['p_pb'], res_f['pr'],
                          gas_f, eta_turbine, dh_f, res_f['p_avail']),
            res_f['p_pump'], res_f['p_avail'])
        ox_shaft = _shaft_dict(
            'ox',
            [_pump_dict('oxidizer', m_ox_total, pump_inlet_ox_bar,
                        res_ox['discharge_bar'], res_ox['p_pump'],
                        eta_pump_ox)],
            _turbine_dict(mdot_turb_ox, tit_ox, res_ox['p_pb'],
                          res_ox['pr'], gas_o, eta_turbine, dh_o,
                          res_ox['p_avail']),
            res_ox['p_pump'], res_ox['p_avail'])
        sol.shafts = [fuel_shaft, ox_shaft]
        sol.power_residual_rel = max(fuel_shaft['power_residual_rel'],
                                     ox_shaft['power_residual_rel'])
        sol.preburners = [
            {'name': 'fuel_rich_preburner', 'mode': 'fuel_rich',
             'of_ratio': pb_f['mr'], 'pressure_bar': res_f['p_pb'],
             'temperature_K': gas_f['temperature_K'],
             'mdot_ox_kg_s': fpb_ox, 'mdot_fuel_kg_s': fpb_fuel,
             'mdot_total_kg_s': mdot_turb_f, 'gas': gas_f},
            {'name': 'ox_rich_preburner', 'mode': 'ox_rich',
             'of_ratio': pb_ox['mr'], 'pressure_bar': res_ox['p_pb'],
             'temperature_K': gas_o['temperature_K'],
             'mdot_ox_kg_s': opb_ox, 'mdot_fuel_kg_s': opb_fuel,
             'mdot_total_kg_s': mdot_turb_ox, 'gas': gas_o}]
        # Ana odaya İKİ GAZ akışı girer (gaz-gaz enjektör ajanının girdisi).
        sol.main_chamber = {
            'mdot_kg_s': mdot_total, 'mr': mr,
            'inlet_streams': [
                {'label': 'fuel-rich preburner products (turbine exhaust)',
                 'mdot_kg_s': mdot_turb_f, 'pressure_bar': p_te,
                 'temperature_K': _turbine_exit_temp(gas_f, tit_f,
                                                     res_f['pr'],
                                                     eta_turbine),
                 'phase': 'gas'},
                {'label': 'ox-rich preburner products (turbine exhaust)',
                 'mdot_kg_s': mdot_turb_ox, 'pressure_bar': p_te,
                 'temperature_K': _turbine_exit_temp(gas_o, tit_ox,
                                                     res_ox['pr'],
                                                     eta_turbine),
                 'phase': 'gas'}]}
        sol.isp_mode = 'closed_cycle_no_loss'
        sol.isp_loss_s = 0.0
        sol.isp_engine_s = isp_main_s
        sol.converged = True
        return sol

    # ------------------------------------------------------------------
    # EXPANDER — türbin gazı rejeneratif ceketten çıkan yakıt.
    # ------------------------------------------------------------------
    if cycle_type == 'expander':
        if regen_heat_kw is None:
            sol.warnings.append(
                'Expander cycle requires the regenerative heat pickup '
                '(regen_heat_kw); without it the turbine inlet state cannot '
                'be computed and the power balance is not modelled.')
            sol.not_modelled += ['turbine_inlet_state', 'power_balance']
            return sol
        fluid = COOLPROP_FLUID.get(fuel)
        if fluid is None:
            sol.warnings.append(
                f'Expander cycle with {fuel} is not supported: no real-gas '
                f'property source is available for it (CoolProp), and RP-1 '
                f'expander engines have no flight precedent.')
            sol.not_modelled += ['turbine_inlet_state', 'power_balance']
            return sol
        t_f0 = float(fuel_inlet_temp_K if fuel_inlet_temp_K is not None
                     else FUEL_NBP_K[fuel])
        if fuel_inlet_temp_K is None:
            sol.assumptions.append(
                f'Fuel pump inlet temperature assumed at the NBP '
                f'{t_f0:g} K (NIST WebBook).')

        p_te = pc_bar + inj_dp_gas
        # Türbin giriş sıcaklığı: ceket enerji dengesi
        # h_out = h(T0, p) + Q/ṁ (CoolProp gerçek gaz; pseudo-kritik cp
        # tepesi dahil).
        import CoolProp.CoolProp as CP
        p_ref = p_te * 1.7 * PA_PER_BAR      # başlangıç basınç tahmini
        try:
            h_in = CP.PropsSI('H', 'T', t_f0, 'P', p_ref, fluid)
            h_out = h_in + regen_heat_kw * 1000.0 / m_fuel_total
            tit = float(CP.PropsSI('T', 'H', h_out, 'P', p_ref, fluid))
            cp_turb = float(CP.PropsSI('C', 'T', tit, 'P', p_ref, fluid))
        except Exception as exc:
            sol.warnings.append(
                f'CoolProp could not evaluate the coolant state '
                f'({exc}); the expander balance is not modelled.')
            sol.not_modelled += ['turbine_inlet_state', 'power_balance']
            return sol
        sol.assumptions.append(
            'Coolant-side gas properties evaluated with CoolProp at the '
            'initial discharge-pressure estimate; the weak pressure '
            'dependence of cp at turbine conditions is neglected.')
        r_sp = R_UNIVERSAL / FUEL_MOLAR_MASS_KG_KMOL[fuel]
        gamma_t = cp_turb / max(cp_turb - r_sp, 1e-6)
        gas = {'temperature_K': tit, 'molecular_weight':
               FUEL_MOLAR_MASS_KG_KMOL[fuel], 'cp_J_kgK': cp_turb,
               'gamma': gamma_t,
               'model': ('real-gas cp from CoolProp at the turbine inlet '
                         'state; gamma from cp/(cp - R/MW)')}

        def powers(pr):
            disch_f = p_te * pr + regen_dp_bar + line_dp_fuel_bar
            p_fp = _pump_power_w(m_fuel_total, disch_f - pump_inlet_fuel_bar,
                                 rho_fuel, eta_pump_fuel)
            p_op = _pump_power_w(m_ox_total,
                                 disch_ox_main - pump_inlet_ox_bar,
                                 rho_ox, eta_pump_ox)
            p_avail = m_fuel_total * _turbine_specific_work(gas, tit, pr,
                                                            eta_turbine)
            return p_avail, p_op + p_fp, p_op, p_fp, disch_f

        def resid(pr):
            p_avail, p_req = powers(pr)[:2]
            return p_avail - p_req

        grid = np.linspace(PR_SOLVE_MIN, PR_SOLVE_MAX, 40)
        vals = [resid(g) for g in grid]
        bracket = None
        for a, b, fa, fb in zip(grid[:-1], grid[1:], vals[:-1], vals[1:]):
            if fa <= 0.0 <= fb or fa >= 0.0 >= fb:
                bracket = (a, b)
                break
        if bracket is None:
            deficit = -resid(PR_SOLVE_MAX)
            sol.warnings.append(
                f'Expander power balance does not close: the chamber heat '
                f'pickup ({regen_heat_kw:g} kW) cannot supply the '
                f'{powers(PR_SOLVE_MAX)[1] / 1e6:.2f} MW pump power at any '
                f'turbine pressure ratio up to {PR_SOLVE_MAX:g} '
                f'(deficit {deficit / 1e6:.2f} MW). This is the natural '
                f'expander power limit — the cycle suits small engines '
                f'(Sutton Ch. 6).')
            sol.not_modelled.append('power_balance')
            sol.converged = False
            return sol
        pr_root = float(brentq(resid, bracket[0], bracket[1], xtol=1e-13,
                               rtol=1e-15))
        p_avail, p_req, p_op, p_fp, disch_f = powers(pr_root)
        dh = _turbine_specific_work(gas, tit, pr_root, eta_turbine)
        sol.iterations = 1
        sol.pump_discharge_fuel_bar = disch_f
        sol.pump_discharge_ox_bar = disch_ox_main
        sol.pump_power_fuel_W = p_fp
        sol.pump_power_ox_W = p_op
        sol.pump_power_total_W = p_req
        sol.turbine_power_total_W = p_avail
        sol.turbine_mdot_total_kg_s = m_fuel_total
        pumps = [
            _pump_dict('oxidizer', m_ox_total, pump_inlet_ox_bar,
                       disch_ox_main, p_op, eta_pump_ox),
            _pump_dict('fuel', m_fuel_total, pump_inlet_fuel_bar, disch_f,
                       p_fp, eta_pump_fuel)]
        turbine = _turbine_dict(m_fuel_total, tit, p_te * pr_root, pr_root,
                                gas, eta_turbine, dh, p_avail)
        sol.shafts = [_shaft_dict('main', pumps, turbine, p_req, p_avail)]
        sol.power_residual_rel = sol.shafts[0]['power_residual_rel']
        sol.main_chamber = {
            'mdot_kg_s': mdot_total, 'mr': mr,
            'inlet_streams': [
                {'label': 'liquid oxidizer', 'mdot_kg_s': m_ox_total,
                 'pressure_bar': pc_bar + inj_dp_liq, 'phase': 'liquid'},
                {'label': 'heated fuel (turbine exhaust)',
                 'mdot_kg_s': m_fuel_total, 'pressure_bar': p_te,
                 'temperature_K': _turbine_exit_temp(gas, tit, pr_root,
                                                     eta_turbine),
                 'phase': 'gas'}]}
        sol.isp_mode = 'closed_cycle_no_loss'
        sol.isp_loss_s = 0.0
        sol.isp_engine_s = isp_main_s
        sol.converged = True
        return sol

    raise AssertionError('unreachable')  # pragma: no cover
