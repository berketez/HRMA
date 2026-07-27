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
# Ölçülen doğrulama (RS-25/SSME Block IIA): "Space Shuttle Main Engine
# Orientation", Rocketdyne Propulsion & Power (Boeing), BC98-04, Haziran 1998,
# "Key Performance Parameters" tabloları — HPFTP türbin verimi %81.1, HPOTP
# türbin verimi %74.6 (ikisi de %104.5 RPL'de; HPFTP PR 1.50, HPOTP PR 1.53).
# ATIF 2026-07-25'te BELGE İNDİRİLİP DOĞRULANDI (denetimde "doğrulanamadı"
# işaretliydi; belge gerçekten bu iki sayıyı içeriyor, uydurma DEĞİL).
# Kapalı çevrim varsayılanı bu iki ölçülen değerin ortasında (0.78) ve
# SP-8110'un ">%80" ifadesinin altında muhafazakâr seçilmiştir.
#
# DÜRÜSTLÜK ETİKETİ (2026-07-25 fizik denetimi): açık çevrim varsayılanı 0.65,
# SP-8110'un doğrulanmış %35-65 bandının ÜST UCUDUR — bant ortası 0.50'dir.
# Yani açık çevrim varsayılanı İYİMSERDİR: 0.50 ile GG bleed debisi ve
# dolayısıyla açık çevrim Isp kaybı ~%30 artar (F-1 örneğinde Isp kaybı
# 2.26 s -> ~2.7 s). Kullanıcı eta_turbine vererek bandın istediği yerinde
# çalışabilir; varsayılan seçim F-1 sınıfı GG türbini pratiğiyle uyumludur
# (Sutton 9th ed. Table 10-3).
ETA_TURBINE_OPEN_DEFAULT = 0.65
ETA_TURBINE_OPEN_BAND = (0.35, 0.65)   # NASA SP-8110 s.15-17 ölçülen bant
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


def _w(code: str, severity: str = "warning", **params) -> Dict:
    """i18n uyarısı: sabit İngilizce metin YERİNE ``{code, params, severity}``.

    Dil frontend'e taşınır; ``TF(code, params)`` metni kurar. ``severity`` ∈
    {"critical", "warning", "info"}. Çevrim uyarıları için varsayılan
    "warning"; varsayımlar (assumptions) "info".
    """
    return {"code": code, "params": params, "severity": severity}


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
            _w('warn.cycle.preburner_cea_unavailable', 'warning')]}
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
        warnings.append(_w("warn.cycle.preburner_tit_below_bound", "warning",
                           tit=round(float(tit_K), 0), t_min=round(float(t_min), 0),
                           mr=round(float(mr), 3)))
        props = preburner_gas_properties(fuel, oxidizer, mr, p_bar)
        return {'status': 'clamped', 'mr': mr, 'warnings': warnings,
                'gas': props}
    if tit_K >= t_max:
        mr = hi if increasing else lo
        warnings.append(_w("warn.cycle.preburner_tit_above_bound", "warning",
                           tit=round(float(tit_K), 0), t_max=round(float(t_max), 0),
                           mr=round(float(mr), 3)))
        props = preburner_gas_properties(fuel, oxidizer, mr, p_bar)
        return {'status': 'clamped', 'mr': mr, 'warnings': warnings,
                'gas': props}

    mr = float(brentq(lambda m: t_of(m) - tit_K, lo, hi, xtol=1e-10,
                      rtol=1e-12))
    props = preburner_gas_properties(fuel, oxidizer, mr, p_bar)
    return {'status': 'solved', 'mr': mr, 'warnings': warnings, 'gas': props}


def _turbine_specific_work(gas: Dict, tit_K: float, pr: float,
                           eta_turbine: float) -> float:
    """Gerçek türbin özgül işi [J/kg] (Sutton Ch. 10, izentropik iş × η).

    GEÇERLİLİK ZARFI (v2.6.2 fizik denetimi, bulgu F010): bu bağıntı termik
    mükemmel gaz varsayar ve YALNIZ yanma gazı dallarında (GG / tap-off /
    staged / FFSC; CEA çıktısı, Tr > 4.5) kullanılır. Expander çevriminin
    yoğun süperkritik itici akışkanında GEÇERSİZDİR — orada
    ``_turbine_work_real_gas`` kullanılır (aynı bulgunun düzeltmesi).
    """
    gamma = gas['gamma']
    x = (gamma - 1.0) / gamma
    return eta_turbine * gas['cp_J_kgK'] * tit_K * (1.0 - pr ** (-x))


def _turbine_exit_temp(gas: Dict, tit_K: float, pr: float,
                       eta_turbine: float) -> float:
    gamma = gas['gamma']
    x = (gamma - 1.0) / gamma
    return tit_K * (1.0 - eta_turbine * (1.0 - pr ** (-x)))


def _turbine_work_real_gas(fluid: str, t_in_K: float, p_in_Pa: float,
                           pr: float, eta_turbine: float):
    """GERÇEK GAZ türbin özgül işi [J/kg] ve çıkış sıcaklığı [K].

    v2.6.2 fizik denetimi, bulgu F010 düzeltmesi.

    Neden ayrı bir fonksiyon: expander çevriminde türbin akışkanı yanma gazı
    DEĞİL, yoğun süperkritik itici buharıdır (CH4 ~277 K / 133 bar; H2
    ~40-130 K / 45-70 bar). Bu rejimde ``_turbine_specific_work``un dayandığı
    TERMİK MÜKEMMEL GAZ bağıntısı γ = cp/(cp − R) GEÇERSİZDİR: cp − cv >> R
    olduğu için γ ciddi biçimde yanlış çıkar (metan 133 bar/277 K'de kod
    γ = 1.16, gerçek cp/cv = 2.08) ve türbin işi %40-50 FAZLA hesaplanır —
    expander güç dengesi yalancı biçimde İYİMSER kapanır.

    Doğrusu izentropik entalpi düşümünü doğrudan almaktır:
        s1 = s(T_in, p_in);  h2s = h(p_in/PR, s1);  Δh = η·(h1 − h2s)
    Bu, izentropik verim tanımının kendisidir (Sutton & Biblarz 9. baskı
    Böl. 10) ve hiçbir ideal gaz varsayımı içermez. Gerçek gaz özellikleri:
    CoolProp 6.8.0 (NIST REFPROP tabanlı; H2: Leachman 2009, CH4: Setzmann &
    Wagner 1991 EOS).

    Yanma gazı dalları (GG / tap-off / staged / FFSC) bu fonksiyonu KULLANMAZ:
    orada CEA zaten ideal gaz çözer ve Tr > 4.5 olduğu için termik mükemmel
    gaz bağıntısı geçerlidir (RS-25'e karşı doğrulandı).

    Returns
    -------
    (dh_J_kg, t_exit_K)
    """
    import CoolProp.CoolProp as CP
    h1 = float(CP.PropsSI('H', 'T', t_in_K, 'P', p_in_Pa, fluid))
    s1 = float(CP.PropsSI('S', 'T', t_in_K, 'P', p_in_Pa, fluid))
    p_out = p_in_Pa / max(pr, 1.0 + 1e-12)
    h2s = float(CP.PropsSI('H', 'P', p_out, 'S', s1, fluid))
    dh = eta_turbine * (h1 - h2s)
    t_exit = float(CP.PropsSI('T', 'P', p_out, 'H', h1 - dh, fluid))
    return dh, t_exit


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


def _turbine_dict(mdot, tit, p_in_bar, pr, gas, eta, dh, power_w,
                  exit_temp_K=None):
    """Türbin raporu. ``exit_temp_K`` verilirse mükemmel-gaz bağıntısı yerine
    o kullanılır (expander dalı gerçek gaz çıkış sıcaklığını CoolProp'tan
    hesaplar; orada γ bağıntısı geçersizdir)."""
    return {'mdot_kg_s': mdot, 'inlet_temp_K': tit,
            'inlet_pressure_bar': p_in_bar, 'pressure_ratio': pr,
            'exit_pressure_bar': p_in_bar / pr,
            'exit_temp_K': (_turbine_exit_temp(gas, tit, pr, eta)
                            if exit_temp_K is None else float(exit_temp_K)),
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
                tit_ox_K: Optional[float] = None,
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

    ``tit_ox_K`` YALNIZ full_flow_staged_combustion çevriminde anlamlıdır:
    FFSC'de İKİ ayrı ön yakıcı vardır ve ``tit_K`` yakıt-zengin milin türbin
    giriş sıcaklığıdır. Ox-zengin mil eskiden koşulsuz 750 K'ye sabitliydi;
    2026-07-25 fizik denetimi (F009) bunun ox milinin enerji marjını yapay
    olarak daralttığını, eşit derecede savunulabilir girdilerle var olan bir
    motorun 'güç dengesi kurulamıyor' diye reddedildiğini ölçtü. Artık
    kullanıcıya açıktır; verilmezse yine 750 K (RD-170 ailesi ~772 K,
    Sutton 9. baskı Böl. 6 ORSC) ve TIT_OX_RICH_LIMIT_K = 850 K üstünde
    metal tutuşma uyarısı üretilir.
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
                sol.assumptions.append(_w(
                    'warn.cycle.turbine_eff_open_assumed', 'info',
                    eta=eta_turbine))
        else:
            eta_turbine = ETA_TURBINE_CLOSED_DEFAULT
            if cycle_type != 'pressure_fed':
                sol.assumptions.append(_w(
                    'warn.cycle.turbine_eff_closed_assumed', 'info',
                    eta=eta_turbine))

    if rho_ox is None:
        rho_ox = DENSITY_NBP_KG_M3[oxidizer]
        sol.assumptions.append(_w('warn.cycle.ox_density_nbp', 'info',
                                  rho=rho_ox))
    if rho_fuel is None:
        rho_fuel = DENSITY_NBP_KG_M3[fuel]
        sol.assumptions.append(_w('warn.cycle.fuel_density_nbp', 'info',
                                  rho=rho_fuel))

    m_ox_total, m_fuel_total = _flow_split(mdot_total, mr)
    inj_dp_liq = injector_dp_frac * pc_bar
    inj_dp_gas = gas_injector_dp_frac * pc_bar
    sol.assumptions.append(_w('warn.cycle.liquid_injector_dp', 'info',
                              frac=injector_dp_frac))

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
            sol.warnings.append(_w('warn.cycle.pressure_fed_no_tank_pressure', 'warning'))
            sol.converged = True
        else:
            margin = tank_pressure_bar - max(req_ox, req_fuel)
            sol.tank_pressure_margin_bar = margin
            sol.converged = margin >= 0.0
            if margin < 0.0:
                sol.warnings.append(_w('warn.cycle.pressure_fed_infeasible', 'critical',
                                       tank=round(float(tank_pressure_bar), 3),
                                       deficit=round(float(-margin), 1),
                                       required=round(float(max(req_ox, req_fuel)), 1)))
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
            sol.warnings.append(_w('warn.cycle.tit_exceeds_uncooled', 'warning',
                                   tit=round(float(tit), 0),
                                   limit=round(float(TIT_UNCOOLED_LIMIT_K), 0)))
        if tit_K is None:
            sol.assumptions.append(_w('warn.cycle.tit_assumed_uncooled', 'info',
                                      tit=round(float(tit), 0)))

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
            sol.assumptions.append(_w('warn.cycle.tapoff_duct_loss_neglected', 'info'))
            sol.assumptions.append(_w('warn.cycle.tapoff_gas_model', 'info'))

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
            sol.assumptions.append(_w('warn.cycle.open_cycle_pr_assumed', 'info',
                                      pr=round(float(pr), 3)))
        if pr > OPEN_CYCLE_TURBINE_PR_WARN:
            sol.warnings.append(_w('warn.cycle.turbine_pr_exceeds_single_body', 'warning',
                                   pr=round(float(pr), 3),
                                   limit=round(float(OPEN_CYCLE_TURBINE_PR_WARN), 3)))
        p_exit = p_gas / pr
        if p_exit <= ambient_pressure_bar:
            sol.warnings.append(_w('warn.cycle.turbine_exit_below_ambient', 'warning',
                                   p_exit=round(float(p_exit), 2),
                                   ambient=round(float(ambient_pressure_bar), 2)))

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
            sol.warnings.append(_w('warn.cycle.open_cycle_bleed_infeasible', 'critical',
                                   pct=round(float(bleed_frac * 100), 0)))
            sol.not_modelled.append('power_balance')
            return sol
        if bleed_frac > BLEED_FRACTION_WARN:
            sol.warnings.append(_w('warn.cycle.open_cycle_bleed_high', 'warning',
                                   pct=round(float(bleed_frac * 100), 0)))

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
            sol.warnings.append(_w('warn.cycle.open_cycle_isp_not_supplied', 'warning'))
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
            sol.warnings.append(_w('warn.cycle.ox_rich_lh2_no_precedent', 'warning'))
        default_key = ('staged_fuel_rich' if preburner_mode == 'fuel_rich'
                       else 'staged_ox_rich')
        tit = float(tit_K if tit_K is not None else TIT_DEFAULT_K[default_key])
        limit = (TIT_UNCOOLED_LIMIT_K if preburner_mode == 'fuel_rich'
                 else TIT_OX_RICH_LIMIT_K)
        if tit > limit:
            sol.warnings.append(_w('warn.cycle.preburner_temp_exceeds_limit', 'warning',
                                   tit=round(float(tit), 0), limit=round(float(limit), 0),
                                   mode=preburner_mode))
        if tit_K is None:
            sol.assumptions.append(_w('warn.cycle.preburner_temp_assumed', 'info',
                                      tit=round(float(tit), 0), mode=preburner_mode))

        p_te = pc_bar + inj_dp_gas          # türbin çıkışı ana enjektöre
        sol.assumptions.append(_w('warn.cycle.staged_hot_gas_injector_drop', 'info',
                                  pct=round(float(gas_injector_dp_frac * 100), 0)))

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
                    sol.warnings.append(_w(
                        'warn.cycle.preburner_ox_demand_exceeds_total',
                        'critical'))
                    sol.not_modelled.append('power_balance')
                    return sol
            else:
                pb_ox = m_ox_total
                pb_fuel = pb_ox / mr_pb
                if pb_fuel > m_fuel_total:
                    sol.warnings.append(_w(
                        'warn.cycle.preburner_fuel_demand_exceeds_total',
                        'critical'))
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
                sol.warnings.append(_w(
                    'warn.cycle.staged_power_balance_infeasible', 'critical',
                    pr_min=PR_SOLVE_MIN, pr_max=PR_SOLVE_MAX, tit=tit,
                    preburner_mode=preburner_mode, mdot_turb=mdot_turb,
                    mdot_total=mdot_total, turb_frac=turb_frac,
                    deficit_mw=best_deficit, best_pr=best_pr))
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
            sol.warnings.append(_w(
                'warn.cycle.staged_pr_outside_typical', 'warning',
                pr=pr_root, pr_lo=STAGED_PR_TYPICAL[0],
                pr_hi=STAGED_PR_TYPICAL[1]))

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
        # F009 (2026-07-25): ox-zengin mil TIT'i artık kullanıcıya AÇIK.
        tit_ox = float(tit_ox_K if tit_ox_K is not None
                       else TIT_DEFAULT_K['ffsc_ox_rich'])
        if tit_K is None and tit_ox_K is None:
            sol.assumptions.append(_w(
                'warn.cycle.ffsc_preburner_temps_assumed', 'info',
                tit_fuel=tit_f, tit_ox=tit_ox))
        elif tit_ox_K is not None:
            sol.assumptions.append(_w(
                'warn.cycle.ffsc_both_tits_user', 'info',
                tit_fuel=tit_f, tit_ox=tit_ox))
        else:
            # Kullanıcı TIT'i yakıt-zengin mile uygulanır; ox-zengin taraf
            # varsayılan malzeme sınırıyla kalır (tit_ox_K ile ezilebilir).
            sol.assumptions.append(_w(
                'warn.cycle.ffsc_user_tit_fuel_shaft',  'info',
                tit_fuel=tit_f, tit_ox=tit_ox))
        if tit_f > TIT_UNCOOLED_LIMIT_K:
            sol.warnings.append(_w(
                'warn.cycle.ffsc_fuel_rich_exceeds_uncooled', 'warning',
                tit_fuel=tit_f, limit=TIT_UNCOOLED_LIMIT_K))
        if tit_ox > TIT_OX_RICH_LIMIT_K:
            # Ox-zengin sıcak gazda metal tutuşma riski (RD-170 pratiği ~772 K;
            # Sutton 9. baskı Böl. 6). Kullanıcı bandı aşarsa sessiz kalınmaz.
            sol.warnings.append(_w(
                'warn.cycle.ffsc_ox_rich_exceeds_limit', 'warning',
                tit_ox=tit_ox, limit=TIT_OX_RICH_LIMIT_K))

        p_te = pc_bar + inj_dp_gas
        sol.assumptions.append(_w(
            'warn.cycle.ffsc_hot_gas_injector_drop', 'info',
            frac=gas_injector_dp_frac))

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
                            inlet_bar, extra_dp_bar, cross_mdot=0.0,
                            cross_feed_bar=0.0):
                """Tek milin PR kökü: türbin gücü = pompa gücü.

                ``cross_mdot`` / ``cross_feed_bar`` (F103, 2026-07-25): bu
                milin pompaladığı iticinin KARŞI ön yakıcıya giden küçük
                payı ve o payın gerektirdiği besleme basıncı. FFSC'de ox-zengin
                ön yakıcı YAKITLA, yakıt-zengin ön yakıcı OKSİTLEYİCİYLE
                beslenir; iki ön yakıcının basıncı farklı olduğu için biri
                diğerinin pompa çıkışının ÜSTÜNDE kalabilir. Ölçüldü (Raptor
                300 bar): ox ön yakıcısına giden 8.43 kg/s yakıt 774.3 bar
                istiyordu, yakıt pompası 628.8 bar veriyordu — 145.6 bar açık,
                sessizce yok sayılıyordu. Gerçek FFSC motorlarında bu iş bir
                kick/boost kademesiyle yapılır; staged dalı aynı muhasebeyi
                zaten uyguluyordu (RS-25 HPOTP ana+boost, NASA SP-8107),
                FFSC dalında simetri eksikti.
                """
                def powers(pr):
                    p_pb = p_te * pr
                    disch = (p_pb * (1.0 + preburner_injector_dp_frac)
                             + extra_dp_bar)
                    p_pump = _pump_power_w(pump_mdot, disch - inlet_bar,
                                           rho, eta_pump)
                    # Çapraz besleme boost kademesi: yalnız karşı ön yakıcı
                    # bu milin çıkışından YÜKSEKTEyse güç harcanır.
                    p_boost = _pump_power_w(cross_mdot,
                                            max(cross_feed_bar - disch, 0.0),
                                            rho, eta_pump)
                    p_avail = mdot_turb * _turbine_specific_work(
                        gas, tit, pr, eta_turbine)
                    return (p_avail, p_pump + p_boost, disch, p_pb, p_boost)

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
                        p_avail, p_pump, disch, p_pb, p_boost = powers(pr)
                        return {'pr': pr, 'p_avail': p_avail,
                                'p_pump': p_pump, 'discharge_bar': disch,
                                'p_pb': p_pb, 'p_boost': p_boost,
                                'cross_feed_bar': cross_feed_bar,
                                'cross_mdot': cross_mdot}
                # Kök yok: en iyi (en küçük açık) durumu teşhis için döndür.
                return {'pr': None, 'best_deficit_W': -max(vals),
                        'best_pr': float(grid[int(np.argmax(vals))]),
                        'mdot_turb': mdot_turb}

            # Karşı ön yakıcının besleme basıncı (dış iterasyon tahmininden).
            opb_feed_bar = (p_opb_guess * (1.0 + preburner_injector_dp_frac)
                            + line_dp_fuel_bar)   # ox ön yakıcısına YAKIT
            fpb_feed_bar = (p_fpb_guess * (1.0 + preburner_injector_dp_frac)
                            + line_dp_ox_bar)     # yakıt ön yakıcısına OKS
            res_f = solve_shaft(pb_f['gas'], tit_f, mdot_turb_f,
                                m_fuel_total, rho_fuel, eta_pump_fuel,
                                pump_inlet_fuel_bar,
                                regen_dp_bar + line_dp_fuel_bar,
                                cross_mdot=opb_fuel,
                                cross_feed_bar=opb_feed_bar)
            res_ox = solve_shaft(pb_ox['gas'], tit_ox, mdot_turb_ox,
                                 m_ox_total, rho_ox, eta_pump_ox,
                                 pump_inlet_ox_bar, line_dp_ox_bar,
                                 cross_mdot=fpb_ox,
                                 cross_feed_bar=fpb_feed_bar)
            if res_f['pr'] is None or res_ox['pr'] is None:
                bad = res_f if res_f['pr'] is None else res_ox
                # Dilsiz kod: metni frontend kurar (TF ile çevrilir).
                side = 'fuel_rich' if res_f['pr'] is None else 'ox_rich'
                sol.warnings.append(_w(
                    'warn.cycle.ffsc_shaft_balance_infeasible', 'critical',
                    side=side, pr_min=PR_SOLVE_MIN, pr_max=PR_SOLVE_MAX,
                    mdot_turb=bad['mdot_turb'],
                    deficit_mw=bad['best_deficit_W'] / 1e6,
                    best_pr=bad['best_pr']))
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
                sol.warnings.append(_w(
                    'warn.cycle.ffsc_shaft_pr_outside_typical', 'warning',
                    shaft=name, pr=res['pr'], pr_lo=STAGED_PR_TYPICAL[0],
                    pr_hi=STAGED_PR_TYPICAL[1]))

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
        # Çapraz besleme boost kademeleri (F103): sıfırdan büyükse raporla.
        def _cross_note(res, propellant, target):
            if res.get('p_boost', 0.0) <= 0.0:
                return None
            return (f"includes a cross-feed boost stage: "
                    f"{res['cross_mdot']:.2f} kg/s of {propellant} raised to "
                    f"{res['cross_feed_bar']:.1f} bar for the {target} "
                    f"preburner ({res['p_boost'] / 1e6:.3f} MW)")

        note_f = _cross_note(res_f, 'fuel', 'ox-rich')
        note_ox = _cross_note(res_ox, 'oxidizer', 'fuel-rich')
        if note_f or note_ox:
            sol.assumptions.append(_w(
                'warn.cycle.ffsc_cross_feed_boost', 'info',
                boost_fuel_mw=round(res_f.get('p_boost', 0.0) / 1e6, 4),
                boost_ox_mw=round(res_ox.get('p_boost', 0.0) / 1e6, 4)))
        fuel_shaft = _shaft_dict(
            'fuel',
            [_pump_dict('fuel', m_fuel_total, pump_inlet_fuel_bar,
                        res_f['discharge_bar'], res_f['p_pump'],
                        eta_pump_fuel, note=note_f)],
            _turbine_dict(mdot_turb_f, tit_f, res_f['p_pb'], res_f['pr'],
                          gas_f, eta_turbine, dh_f, res_f['p_avail']),
            res_f['p_pump'], res_f['p_avail'])
        ox_shaft = _shaft_dict(
            'ox',
            [_pump_dict('oxidizer', m_ox_total, pump_inlet_ox_bar,
                        res_ox['discharge_bar'], res_ox['p_pump'],
                        eta_pump_ox, note=note_ox)],
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
            sol.warnings.append(_w(
                'warn.cycle.expander_requires_regen_heat', 'critical'))
            sol.not_modelled += ['turbine_inlet_state', 'power_balance']
            return sol
        fluid = COOLPROP_FLUID.get(fuel)
        if fluid is None:
            sol.warnings.append(_w(
                'warn.cycle.expander_fuel_unsupported', 'critical',
                fuel=fuel))
            sol.not_modelled += ['turbine_inlet_state', 'power_balance']
            return sol
        t_f0 = float(fuel_inlet_temp_K if fuel_inlet_temp_K is not None
                     else FUEL_NBP_K[fuel])
        if fuel_inlet_temp_K is None:
            sol.assumptions.append(_w(
                'warn.cycle.fuel_pump_inlet_nbp_assumed', 'info',
                temp_k=t_f0))

        p_te = pc_bar + inj_dp_gas
        # Türbin giriş sıcaklığı: ceket enerji dengesi
        # h_out = h(T0, p) + Q/ṁ (CoolProp gerçek gaz; pseudo-kritik cp
        # tepesi dahil).
        import CoolProp.CoolProp as CP

        # DIŞ İTERASYON (2026-07-25 fizik denetimi F036): eskiden türbin giriş
        # durumu SABİT bir tahminde (p_ref = p_te·1.7) okunuyor, PR çözüldükten
        # sonra bir daha güncellenmiyordu. Gerçek türbin giriş basıncı
        # p_te·PR'dir. Kriyojenik H2'de özellikler basınca çok duyarlıdır
        # (CoolProp, Leachman 2009 EOS: 40 K'de cp = 23112 J/kgK @40 bar,
        # 16221 @64 bar -> %-30), bu yüzden staged/FFSC dallarındaki gibi bir
        # dış iterasyon eklendi: özellikler p_te·PR'de yeniden okunur.
        pr_root = 1.7                        # başlangıç PR tahmini
        gas = None
        tit = float('nan')
        outer_used = 0
        for outer in range(6):
            outer_used = outer + 1
            p_ref = p_te * pr_root * PA_PER_BAR   # türbin girişi [Pa]
            try:
                h_in = CP.PropsSI('H', 'T', t_f0, 'P', p_ref, fluid)
                h_out = h_in + regen_heat_kw * 1000.0 / m_fuel_total
                tit = float(CP.PropsSI('T', 'H', h_out, 'P', p_ref, fluid))
                cp_turb = float(CP.PropsSI('C', 'T', tit, 'P', p_ref, fluid))
                cv_turb = float(CP.PropsSI('O', 'T', tit, 'P', p_ref, fluid))
            except Exception as exc:
                sol.warnings.append(_w(
                    'warn.cycle.coolprop_state_failed', 'critical',
                    error=str(exc)))
                sol.not_modelled += ['turbine_inlet_state', 'power_balance']
                return sol
            r_sp = R_UNIVERSAL / FUEL_MOLAR_MASS_KG_KMOL[fuel]
            # v2.6.2 fizik denetimi, bulgu F010: 'gamma' artık GERÇEK
            # cp/cv'dir (raporlama için). Termik mükemmel gaz değeri
            # cp/(cp−R) yalnız karşılaştırma amacıyla saklanır — türbin
            # işinde ARTIK KULLANILMAZ (bkz. _turbine_work_real_gas; eski
            # bağıntı CH4 133 bar/277 K'de işi %43 FAZLA hesaplıyordu).
            gas = {'temperature_K': tit,
                   'molecular_weight': FUEL_MOLAR_MASS_KG_KMOL[fuel],
                   'cp_J_kgK': cp_turb, 'cv_J_kgK': cv_turb,
                   'gamma': float(cp_turb / max(cv_turb, 1e-9)),
                   'gamma_thermally_perfect': float(
                       cp_turb / max(cp_turb - r_sp, 1e-6)),
                   'inlet_pressure_bar': float(p_ref / PA_PER_BAR),
                   'model': ('real-gas CoolProp state at the turbine inlet '
                             '(p = p_te*PR); turbine work from the isentropic '
                             'enthalpy drop, NOT from a perfect-gas gamma')}

            def powers(pr, _p_ref=p_ref, _tit=tit):
                disch_f = p_te * pr + regen_dp_bar + line_dp_fuel_bar
                p_fp = _pump_power_w(m_fuel_total,
                                     disch_f - pump_inlet_fuel_bar,
                                     rho_fuel, eta_pump_fuel)
                p_op = _pump_power_w(m_ox_total,
                                     disch_ox_main - pump_inlet_ox_bar,
                                     rho_ox, eta_pump_ox)
                # Türbin girişi p_te·pr; özellikler _p_ref'te sabitlenmiş
                # dış iterasyon adımının durumundan gelir, ama izentropik
                # düşüm gerçek giriş basıncından alınır.
                dh_pr, _ = _turbine_work_real_gas(
                    fluid, _tit, p_te * pr * PA_PER_BAR, pr, eta_turbine)
                p_avail = m_fuel_total * dh_pr
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
                # Artık fonksiyonunun TEPE noktası en iyi durumdur (türbin işi
                # PR ile doyarken pompa gücü doğrusal büyür).
                best_pr = float(grid[int(np.argmax(vals))])
                deficit = -max(vals)
                sol.warnings.append(_w(
                    'warn.cycle.expander_power_balance_infeasible', 'critical',
                    regen_heat_kw=regen_heat_kw,
                    pump_power_mw=powers(best_pr)[1] / 1e6,
                    pr_max=PR_SOLVE_MAX, deficit_mw=deficit / 1e6))
                sol.not_modelled.append('power_balance')
                sol.converged = False
                return sol
            pr_new = float(brentq(resid, bracket[0], bracket[1], xtol=1e-13,
                                  rtol=1e-15))
            converged_outer = abs(pr_new - pr_root) / max(pr_root, 1e-9) < 1e-4
            pr_root = pr_new
            if converged_outer:
                break

        sol.assumptions.append(_w(
            'warn.cycle.expander_real_gas_turbine', 'info',
            gamma_real=round(float(gas['gamma']), 3),
            gamma_perfect=round(float(gas['gamma_thermally_perfect']), 3)))
        sol.assumptions.append(_w(
            'warn.cycle.expander_inlet_pressure_iterated', 'info',
            iterations=outer_used,
            p_in_bar=round(float(p_te * pr_root), 1)))
        p_avail, p_req, p_op, p_fp, disch_f = powers(pr_root)
        dh, t_exit_turb = _turbine_work_real_gas(
            fluid, tit, p_te * pr_root * PA_PER_BAR, pr_root, eta_turbine)
        sol.iterations = outer_used
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
                                gas, eta_turbine, dh, p_avail,
                                exit_temp_K=t_exit_turb)
        sol.shafts = [_shaft_dict('main', pumps, turbine, p_req, p_avail)]
        sol.power_residual_rel = sol.shafts[0]['power_residual_rel']
        sol.main_chamber = {
            'mdot_kg_s': mdot_total, 'mr': mr,
            'inlet_streams': [
                {'label': 'liquid oxidizer', 'mdot_kg_s': m_ox_total,
                 'pressure_bar': pc_bar + inj_dp_liq, 'phase': 'liquid'},
                {'label': 'heated fuel (turbine exhaust)',
                 'mdot_kg_s': m_fuel_total, 'pressure_bar': p_te,
                 'temperature_K': float(t_exit_turb),
                 'phase': 'gas'}]}
        sol.isp_mode = 'closed_cycle_no_loss'
        sol.isp_loss_s = 0.0
        sol.isp_engine_s = isp_main_s
        sol.converged = True
        return sol

    raise AssertionError('unreachable')  # pragma: no cover
