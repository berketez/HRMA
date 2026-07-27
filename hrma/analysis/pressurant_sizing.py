"""Pressurant (pressurizing gas) sizing for regulated and blowdown feed systems.

Sizes the inert pressurant gas (helium or nitrogen) required to expel the
propellant from a rocket propellant tank, for both a regulated (constant tank
pressure) architecture and a blowdown (falling tank pressure) architecture.
References:

    - Sutton, G.P. & Biblarz, O., "Rocket Propulsion Elements", 9th ed., 2017,
      Chapter 6 ("Gas Pressure Feed Systems"), Eqs. 6-1..6-6.
    - Huzel, D.K. & Huang, D.H., "Modern Engineering for Design of
      Liquid-Propellant Rocket Engines", AIAA Vol. 147, 1992, Chapter 5
      (pressurization systems, stored-gas and blowdown sizing).

Regulated system
----------------
A high-pressure bottle feeds the propellant tank through a regulator that holds
the tank pressure ``P_tank`` constant while the propellant volume ``V_p`` is
expelled.  The pressurant mass that ends up occupying the emptied propellant
volume is the ideal-gas inventory at ``P_tank`` and the gas end temperature
``T_final`` (Sutton Eq. 6-1), times an optional pressurant-collapse correction:

    m_gas = P_tank * V_p / (R_specific * T_final) * f_correction              (1)

Two thermodynamic bounds are reported and the real value lies between them:

    - Isothermal (slow): the gas equilibrates to the initial temperature,
      T_final = T_initial  -> minimum gas mass (densest gas).
    - Adiabatic (fast): the gas is delivered by an isentropic expansion from the
      storage pressure to the tank pressure and stays cold,
      T_final = T_initial * (P_tank / P_store)^((gamma-1)/gamma)  (Sutton Eq.
      6-4 style) -> lower T -> higher gas mass.  Hence m_adiabatic > m_isothermal.

Stored gas and bottle sizing: a storage bottle blown down (isothermally, the
conservative-enough sizing assumption) from ``P_store`` to a minimum usable
pressure ``P_min = (1 + margin) * P_tank`` delivers a usable gas density
``(P_store - P_min)/(R_specific * T_initial)``.  The required bottle water
volume, residual (unusable) gas, and standard-bottle count follow.

Blowdown system
---------------
No regulator: the pressurant gas trapped above the propellant simply expands
polytropically as the propellant leaves, so the tank pressure falls.  With a
polytropic index ``n`` (1.0 isothermal .. gamma adiabatic):

    P_final = P_initial * (V_ullage_0 / (V_ullage_0 + V_p))^n                 (2)
    T_final = T_initial * (P_final / P_initial)^((n-1)/n)                      (3)

The blowdown ratio B = P_initial / P_final drives engine off-design behaviour.

Gas constants
-------------
Specific gas constants are the central CODATA-2018 universal gas constant
(``hrma.constants.R_UNIVERSAL`` = 8314.462618 J/(kmol.K)) divided by the molar
mass in kg/kmol.  Ratios of specific heats are the standard near-ideal values
(monatomic He: 5/3; diatomic N2: 7/5).
"""

from __future__ import annotations

import math

# Merkezi sabitlerden import (magic-number tutarsızlığını önlemek için).
from hrma.constants import R_UNIVERSAL  # J/(kmol*K), CODATA 2018

try:  # Gerçek gaz (Z faktörü, entalpi) — kuruluysa kullanılır.
    from CoolProp.CoolProp import PropsSI as _PropsSI
    _COOLPROP = True
except ImportError:  # pragma: no cover - CoolProp kurulu olmayan ortam
    _PropsSI = None
    _COOLPROP = False

#: CoolProp akışkan adları (basınçlandırma gazları).
_COOLPROP_GAS = {'helium': 'Helium', 'nitrogen': 'Nitrogen'}


def compressibility_factor(gas_key, pressure_Pa, temperature_K):
    """Sıkıştırılabilirlik faktörü Z = p / (rho * R * T)  [-].

    NEDEN GEREKLİ (2026-07-25 fizik denetimi, F055): bu modülün varsayılan
    depolama basınçları 200-400 bar bandındadır ve o bantta ideal gaz yasası
    YETERSİZDİR. Ölçülen (CoolProp 6.8.0 = NIST REFPROP tabanlı; Helium:
    Ortiz-Vega 2013 EOS, Nitrogen: Span 2000 EOS):
        He  200 bar / 293 K -> Z = 1.095      He 300 bar / 293 K -> Z = 1.141
        He  300 bar / 200 K -> Z = 1.213      He 400 bar / 200 K -> Z = 1.281
        N2  200 bar / 293 K -> Z = 1.052      N2 300 bar / 293 K -> Z = 1.140
    Z > 1 demek, aynı su hacmindeki şişeye ideal gaz yasasının söylediğinden
    %5-28 DAHA AZ gaz sığıyor demektir; Z ihmal edilirse şişe hacmi ve şişe
    sayısı o oranda EKSİK boyutlanır.

    Returns
    -------
    (Z, real_gas_used) : tuple[float, bool]
        CoolProp yoksa (1.0, False) döner — sahte düzeltme uygulanmaz, çağıran
        durumu 'ideal_gas' olarak etiketler.
    """
    if not _COOLPROP or gas_key not in _COOLPROP_GAS:
        return 1.0, False
    try:
        rho = float(_PropsSI('D', 'T', float(temperature_K), 'P',
                             float(pressure_Pa), _COOLPROP_GAS[gas_key]))
        R = GAS_PROPERTIES[gas_key]['R']
        return float(pressure_Pa) / (rho * R * float(temperature_K)), True
    except Exception:  # pragma: no cover - CoolProp zarf dışı
        return 1.0, False

#: Pressurant gas properties.  ``M`` molar mass [kg/kmol] (CODATA), ``gamma``
#: ratio of specific heats (ideal), ``R`` specific gas constant [J/(kg.K)],
#: computed as R_UNIVERSAL [J/(kmol.K)] / M [kg/kmol].
GAS_PROPERTIES = {
    'helium': {
        'M': 4.002602,
        'gamma': 1.667,  # monatomic, 5/3
        'R': R_UNIVERSAL / 4.002602,         # 2077.3 J/(kg.K)
    },
    'nitrogen': {
        'M': 28.0134,
        'gamma': 1.400,  # diatomic, 7/5
        'R': R_UNIVERSAL / 28.0134,          # 296.80 J/(kg.K)
    },
}

#: Standard high-pressure storage bottle water volume [m^3] (50 L industrial).
STANDARD_BOTTLE_VOLUME = 0.050
#: Common commercial storage pressures [Pa].
STANDARD_STORAGE_PRESSURES = (200e5, 300e5)


def gas_properties(gas):
    """Return the property dict for ``gas`` ('helium' or 'nitrogen')."""
    key = str(gas).strip().lower()
    aliases = {'he': 'helium', 'n2': 'nitrogen', 'gn2': 'nitrogen'}
    key = aliases.get(key, key)
    if key not in GAS_PROPERTIES:
        raise ValueError(
            f"unknown gas '{gas}'; choose from {sorted(GAS_PROPERTIES)}")
    return key, GAS_PROPERTIES[key]


def regulated_pressurant(propellant_volume, tank_pressure, gas='helium',
                         initial_temperature=293.15, storage_pressure=200e5,
                         regulator_margin=0.10, collapse_factor=1.0,
                         standard_bottle_volume=STANDARD_BOTTLE_VOLUME):
    """Size a regulated (constant-tank-pressure) pressurization system.

    Parameters
    ----------
    propellant_volume : float
        Propellant volume to be expelled V_p [m^3].
    tank_pressure : float
        Regulated propellant-tank pressure P_tank [Pa].
    gas : str
        'helium' or 'nitrogen'.
    initial_temperature : float
        Initial pressurant temperature [K].
    storage_pressure : float
        High-pressure bottle initial pressure P_store [Pa].
    regulator_margin : float
        Fractional margin above tank pressure below which the bottle can no
        longer feed the regulator; P_min = (1+margin) * P_tank.
    collapse_factor : float
        Pressurant-collapse / use factor f_correction in Eq. (1) (Sutton Ch. 6;
        heat loss to cold propellant contracts the ullage gas -> typically
        1.0-1.6).  Default 1.0; tagged ``'approximate'`` when > 1.
    standard_bottle_volume : float
        Water volume of one storage bottle [m^3] for the count estimate.

    Returns
    -------
    dict with isothermal/adiabatic delivered-mass bounds, storage sizing, and
    a ``model_note``.
    """
    V_p = float(propellant_volume)
    P_tank = float(tank_pressure)
    T0 = float(initial_temperature)
    P_store = float(storage_pressure)
    if V_p <= 0.0 or P_tank <= 0.0 or T0 <= 0.0 or P_store <= 0.0:
        raise ValueError("volume, pressures and temperature must be positive")
    if P_store <= P_tank:
        raise ValueError("storage_pressure must exceed tank_pressure")

    name, props = gas_properties(gas)
    R = props['R']
    gamma = props['gamma']
    f_corr = float(collapse_factor)

    # Eq. (1) delivered-mass bounds ---------------------------------------
    # Isothermal (slow): T_final = T0.
    m_iso = P_tank * V_p / (R * T0) * f_corr
    # Adiabatic (fast): isentropic expansion P_store -> P_tank cools the gas.
    T_adia = T0 * (P_tank / P_store) ** ((gamma - 1.0) / gamma)
    m_adia = P_tank * V_p / (R * T_adia) * f_corr

    # ------------------------------------------------------------------
    # DEPOLAMA BOYUTLANDIRMA — kapalı form enerji dengesi (F054 düzeltmesi).
    #
    # ESKİ (YANLIŞ) YOL: teslim edilen kütle TAM ADYABATİK sınırdan (m_adia,
    # en soğuk/en ağır) alınıyor, ama şişe boşalması İZOTERMAL kabul ediliyordu
    # (usable_density = (P_s − P_min)/(R·T0)). İki varsayım birbiriyle
    # tutarsızdı ve şişe kütlesini/sayısını ÖLÇÜLEN oranlarda şişiriyordu:
    #   He 200->20 bar: 9.27 kg / 282 L  (kapalı form 6.15 kg / 187 L) = 1.51x
    #   He 300->20 bar: 10.47 kg / 213 L (kapalı form 5.94 kg / 121 L) = 1.76x
    #   N2 200->20 bar: 49.87 kg / 217 L (kapalı form 35.9 kg / 156 L) = 1.39x
    #
    # DOĞRUSU (Sutton & Biblarz 9. baskı Böl. 6, Eş. 6-1; Huzel & Huang Böl. 5):
    # şişe + tank ullage'ının TOPLAM adyabatik enerji dengesinden (ideal gaz):
    #     cv/R · p_s·V_b = cv/R · (p_f·V_b + p_t·V_p) + p_t·V_p
    #  => V_b = gamma · p_t · V_p / (p_s − p_f)          (p_f = son şişe basıncı)
    #  => m_depo = gamma · p_t · V_p / (R·T0·(1 − p_f/p_s))
    # Bağıntı burada bağımsız olarak türetildi; p_f = P_tank alındığında
    # ders kitabı formuna indirgenir. Sıcaklık ayrımı (şişe/tank) enerji
    # dengesinde ideal gaz yasasıyla sadeleşir, yani V_b bu ayrımdan BAĞIMSIZDIR.
    # ------------------------------------------------------------------
    P_min = (1.0 + float(regulator_margin)) * P_tank
    if P_min >= P_store:
        raise ValueError(
            "storage_pressure must exceed (1+regulator_margin)*tank_pressure")

    bottle_volume_ideal = gamma * P_tank * V_p * f_corr / (P_store - P_min)

    # Gerçek gaz düzeltmesi (F055): ideal gaz yasası 200-400 bar'da yoğunluğu
    # FAZLA tahmin eder; aynı kütleyi tutmak için şişe Z katı büyümelidir.
    Z_store, real_gas = compressibility_factor(name, P_store, T0)
    Z_min, _ = compressibility_factor(name, P_min, T0)
    bottle_volume = bottle_volume_ideal * Z_store
    stored_mass = P_store * bottle_volume / (Z_store * R * T0)

    # Şişede kalan (kullanılamayan) gaz: şişenin izentropik (hızlı) boşalma
    # sıcaklığında — en soğuk, dolayısıyla en yoğun, yani KONSERVATİF kalıntı.
    T_bottle_final = T0 * (P_min / P_store) ** ((gamma - 1.0) / gamma)
    Z_res, _ = compressibility_factor(name, P_min, T_bottle_final)
    residual_mass = P_min * bottle_volume / (Z_res * R * T_bottle_final)
    m_delivered = stored_mass - residual_mass
    usable_density = m_delivered / bottle_volume
    bottle_count = int(math.ceil(bottle_volume / float(standard_bottle_volume)))

    note = ("Regulated stored-gas system sized from the closed-form adiabatic "
            "energy balance V_bottle = gamma*P_tank*V_p/(P_store-P_min) "
            "(Sutton 9th ed. Ch. 6 Eq. 6-1 family; Huzel & Huang Ch. 5). The "
            "isothermal/adiabatic ullage masses below are diagnostic bounds on "
            "the gas that ends up in the tank, not the sizing basis. Residual "
            "bottle gas is evaluated at the isentropic blowdown temperature "
            "(coldest, densest -> conservative).")
    if real_gas:
        note += (f" Real-gas compressibility applied: Z={Z_store:.3f} at "
                 f"{P_store / 1e5:.0f} bar (CoolProp/NIST); the ideal-gas "
                 f"bottle would be {Z_store:.3f}x too small.")
    else:
        note += (" CoolProp unavailable -> ideal gas (Z=1) assumed; at "
                 "200-400 bar this UNDER-sizes the bottle by 5-28%.")
    if f_corr != 1.0:
        note += " Pressurant-collapse correction applied (approximate)."

    return {
        'gas': name,
        'R_specific': R,
        'gamma': gamma,
        'tank_pressure': P_tank,
        'propellant_volume': V_p,
        'storage_pressure': P_store,
        'collapse_factor': f_corr,
        'isothermal': {
            'gas_mass_kg': float(m_iso),
            'final_temperature_K': T0,
            'gas_density_kgm3': float(P_tank / (R * T0)),
        },
        'adiabatic': {
            'gas_mass_kg': float(m_adia),
            'final_temperature_K': float(T_adia),
            'gas_density_kgm3': float(P_tank / (R * T_adia)),
        },
        'recommended_delivered_mass_kg': float(m_delivered),
        'storage': {
            'min_usable_pressure_Pa': float(P_min),
            'usable_density_kgm3': float(usable_density),
            'bottle_water_volume_m3': float(bottle_volume),
            'bottle_water_volume_ideal_gas_m3': float(bottle_volume_ideal),
            'stored_mass_kg': float(stored_mass),
            'residual_mass_kg': float(residual_mass),
            'residual_temperature_K': float(T_bottle_final),
            'compressibility_factor_store': float(Z_store),
            'compressibility_factor_min': float(Z_min),
            'real_gas_model': ('CoolProp (NIST REFPROP-based)' if real_gas
                               else 'ideal gas (CoolProp unavailable)'),
            'sizing_method': ('closed_form_adiabatic_energy_balance'
                              '_with_real_gas_density' if real_gas else
                              'closed_form_adiabatic_energy_balance_ideal'),
            'standard_bottle_volume_m3': float(standard_bottle_volume),
            'bottle_count': bottle_count,
        },
        'model_note': note,
        'confidence': 'medium',
    }


def blowdown_pressurant(propellant_volume, initial_ullage_volume,
                        initial_pressure, gas='nitrogen',
                        initial_temperature=293.15, polytropic_n=1.2):
    """Blowdown (falling-pressure) pressurization of a single trapped-gas tank.

    Parameters
    ----------
    propellant_volume : float
        Propellant volume expelled V_p [m^3].
    initial_ullage_volume : float
        Initial gas (ullage) volume above the propellant V_u0 [m^3].
    initial_pressure : float
        Initial tank pressure P_initial [Pa].
    gas : str
        'helium' or 'nitrogen' (for the trapped-gas mass).
    initial_temperature : float
        Initial gas temperature [K].
    polytropic_n : float
        Polytropic exponent n (1.0 isothermal .. gamma adiabatic), Eq. (2)-(3).

    Returns
    -------
    dict with final pressure/temperature, blowdown ratio and trapped gas mass.
    """
    V_p = float(propellant_volume)
    V_u0 = float(initial_ullage_volume)
    P0 = float(initial_pressure)
    T0 = float(initial_temperature)
    n = float(polytropic_n)
    if V_p <= 0.0 or V_u0 <= 0.0 or P0 <= 0.0 or T0 <= 0.0:
        raise ValueError("volumes, pressure and temperature must be positive")
    if n <= 0.0:
        raise ValueError("polytropic_n must be positive")

    name, props = gas_properties(gas)
    R = props['R']

    V_uf = V_u0 + V_p
    P_final = P0 * (V_u0 / V_uf) ** n                       # Eq. (2)
    T_final = T0 * (P_final / P0) ** ((n - 1.0) / n)        # Eq. (3)
    blowdown_ratio = P0 / P_final
    gas_mass = P0 * V_u0 / (R * T0)                         # fixed trapped mass

    return {
        'gas': name,
        'R_specific': R,
        'polytropic_n': n,
        'initial_pressure': P0,
        'final_pressure': float(P_final),
        'blowdown_ratio': float(blowdown_ratio),
        'initial_temperature_K': T0,
        'final_temperature_K': float(T_final),
        'initial_ullage_volume': V_u0,
        'final_ullage_volume': float(V_uf),
        'expelled_volume': V_p,
        'gas_mass_kg': float(gas_mass),
        'model_note': (
            "Blowdown pressurization (Huzel & Huang Ch. 5): trapped gas expands "
            "polytropically (n=1 isothermal, n=gamma adiabatic); tank pressure "
            "falls by the blowdown ratio. Engine must tolerate the P range."),
        'confidence': 'medium',
    }


# Autogenous basınçlandırma gaz özellikleri (ısıtılmış itici buharı).
# cp: sabit basınç özgül ısısı [J/(kg·K)], R: özgül gaz sabiti [J/(kg·K)].
# Kaynak: NIST Webbook (gaz fazı, oda basıncı mertebesinde) + Sutton &
# Biblarz 9. baskı Böl. 6 (autogenous/self-pressurization).
# Ek alanlar (2026-07-25 fizik denetimi, F052 — ısı değiştirici yükü):
#   T_nbp   : normal kaynama noktası [K]
#   h_fg    : NBP'de buharlaşma gizli ısısı [J/kg]
#   cp_cryo : NBP'den varsayılan besleme sıcaklığına ORTALAMA gaz cp'si
#             [J/(kg·K)] — CoolProp yokken kullanılan yedek yol için.
# Kaynak: CoolProp 6.8.0 (NIST REFPROP tabanlı EOS; O2: Schmidt & Wagner,
# CH4: Setzmann & Wagner, H2: Leachman) ile 1 atm doygunlukta ölçüldü:
#   O2  NBP 90.19 K, h_fg 213.1 kJ/kg   CH4 NBP 111.67 K, h_fg 510.8 kJ/kg
#   H2  NBP 20.37 K, h_fg 448.7 kJ/kg
AUTOGENOUS_GAS = {
    # Gaz haldeki metan (~300 K): R = 8314.46/16.04
    'methane': {'R': 518.3, 'cp': 2230.0, 'name': 'gaseous methane (GCH4)',
                'coolprop': 'Methane', 'T_nbp': 111.67, 'h_fg': 510.8e3,
                'cp_cryo': 2076.5},
    # Gaz oksijen (~300 K): R = 8314.46/32.00
    'oxygen': {'R': 259.8, 'cp': 918.0, 'name': 'gaseous oxygen (GOX)',
               'coolprop': 'Oxygen', 'T_nbp': 90.19, 'h_fg': 213.1e3,
               'cp_cryo': 910.2},
    # Gaz hidrojen (~300 K): R = 8314.46/2.016
    'hydrogen': {'R': 4124.0, 'cp': 14300.0, 'name': 'gaseous hydrogen (GH2)',
                 'coolprop': 'Hydrogen', 'T_nbp': 20.37, 'h_fg': 448.7e3,
                 'cp_cryo': 11737.5},
}

#: Autogenous basınçlandırmada gaz çökmesi (collapse) düzeltme bandı.
#: Sutton & Biblarz 9. baskı Böl. 6 / Huzel & Huang Böl. 5 'pressurant
#: collapse / use factor'; bu modülün regulated dalı da aynı 1.0-1.6 bandını
#: kullanır. 1.0 = çökme yok (İYİMSER ALT SINIR).
AUTOGENOUS_COLLAPSE_BAND = (1.0, 1.6)

# Autogenous besleme gazının tanka giriş sıcaklığı [K]: itici, ısı
# değiştiriciden (soğutma ceketi / ön yakıcı musluğu) geçip ısıtılarak
# tanka gaz olarak döner. Değerler uçmuş motorların tipik autogenous
# besleme sıcaklığı bandındadır (Huzel & Huang Ch. 5). ETİKETLİ varsayım.
AUTOGENOUS_FEED_TEMP_K = {'methane': 250.0, 'oxygen': 250.0, 'hydrogen': 200.0}


def autogenous_vaporization_enthalpy(gas_key, feed_temperature, tank_pressure):
    """Sıvı iticiyi besleme gazına çevirmenin özgül entalpi yükü [J/kg].

    NEDEN AYRI FONKSİYON (2026-07-25 fizik denetimi, F052): eski kod
    ``m_gas · cp_gaz · max(T − 90 K, 0)`` yazıyordu; yani yalnız GAZ duyulur
    ısısını alıyor, BUHARLAŞMA GİZLİ ISISINI (h_fg) tamamen atlıyordu. 90 K
    sabit tabanı da yalnız oksijen için doğruydu (metan NBP 111.67 K,
    hidrojen 20.37 K).

    Doğrusu tam entalpi farkıdır (ısı değiştiricinin gerçekte yapması gereken
    iş):

        dh = h(T_besleme, p_tank) − h_sıvı,doygun(NBP)
           = (sıvı duyulur) + h_fg + (gaz duyulur)

    ÖLÇÜLDÜ (6 bar tank, modülün kendi varsayılan besleme sıcaklıkları;
    CoolProp 6.8.0 = NIST REFPROP tabanlı):
        GOX  250 K : eski 147 kJ/kg   → doğru 358.5 kJ/kg  (eski %-59 EKSİK)
        GCH4 250 K : eski 357 kJ/kg   → doğru 798.1 kJ/kg  (eski %-55 EKSİK)
        GH2  200 K : eski 1573 kJ/kg  → doğru 2557.1 kJ/kg (eski %-39 EKSİK)
    Yani ısı değiştirici yükü yaklaşık İKİ KAT eksik raporlanıyordu.

    Returns
    -------
    (dh_J_kg, method) : tuple[float, str]
        ``method`` = 'coolprop_enthalpy_difference' veya (CoolProp yoksa)
        'h_fg_plus_mean_cp' — yedek yol h_fg + cp_ort·(T − T_NBP) ile
        yaklaşır. cp_ort değerleri NBP→varsayılan besleme sıcaklığı aralığında
        CoolProp'a uydurulduğu için o noktada sapma ~%0'dır; ÖLÇÜLEN sapma
        aralığın dışına çıkıldıkça büyür (O2: 150 K %+1.2, 400 K %−0.7;
        CH4: 150 K %+2.7, 400 K %−3.4; H2: 150 K %+3.7, 400 K %−9.2).
    """
    gas = AUTOGENOUS_GAS[gas_key]
    T = float(feed_temperature)
    if _COOLPROP and gas.get('coolprop'):
        try:
            h_liq = float(_PropsSI('H', 'P', 101325.0, 'Q', 0, gas['coolprop']))
            h_gas = float(_PropsSI('H', 'T', T, 'P', float(tank_pressure),
                                   gas['coolprop']))
            return max(h_gas - h_liq, 0.0), 'coolprop_enthalpy_difference'
        except Exception:  # pragma: no cover - CoolProp zarf dışı durum
            pass
    dh = gas['h_fg'] + gas['cp_cryo'] * max(T - gas['T_nbp'], 0.0)
    return max(dh, 0.0), 'h_fg_plus_mean_cp'


def autogenous_pressurant(propellant_volume, tank_pressure, propellant,
                          feed_temperature=None, expulsion_efficiency=0.95,
                          collapse_factor=1.0):
    """Autogenous (kendinden) basınçlandırma gaz debisi ve kütlesi.

    Autogenous basınçlandırmada ayrı bir inert gaz şişesi (helyum/azot) YOKTUR:
    iticinin bir kısmı ısı değiştiriciden geçirilip gaz hâline getirilerek kendi
    tankına geri beslenir (LOX tankı GOX ile, metan tankı GCH4 ile). Raptor,
    Starship ve birçok modern metan/LOX motoru bu yolu kullanır; helyum
    lojistiğini ve ortak-kütle sorununu ortadan kaldırır.

    Model (ideal gaz, düzenlenmiş/regulated tank — Sutton & Biblarz 9. baskı
    Böl. 6, Eş. 6-1): boşalan itici hacmini SABİT tank basıncında dolduran gaz
    envanteri
        m_gas = P_tank · V_p / (R · T_besleme) / η_boşaltma · f_çökme
    Burada R gazın özgül sabiti, T_besleme gazın tanka giriş sıcaklığıdır.
    Bu kütle iticiden ALINIR (tanka geri döner ama itki üretmez), bu yüzden
    sistem bütçesine 'iticiden çalınan pay' olarak işlenir.

    ÇÖKME (COLLAPSE) DÜZELTMESİ — F053 (2026-07-25 fizik denetimi)
    --------------------------------------------------------------
    ``regulated_pressurant`` kriyojenik tanklarda gazın soğuk sıvıya ısı
    kaptırıp büzülmesi için bir ``collapse_factor`` (1.0-1.6) sunuyordu;
    autogenous yolunda böyle bir düzeltme HİÇ YOKTU. Oysa autogenous'ta durum
    daha ağırdır: GOX bir LOX tankının serbest yüzeyinde YOĞUŞUR, GCH4 metan
    üstünde yoğuşur; gerçek gaz talebi ideal envanterin belirgin üstündedir.
    Artık aynı parametre buraya da açılmıştır. Varsayılan 1.0 bir modelleme
    tercihi değil, açıkça etiketlenmiş İYİMSER ALT SINIRDIR: çıktıda
    ``collapse_factor_is_optimistic_lower_bound`` alanı ve model notu bunu
    söyler. Kodun kendi alıntıladığı 1.0-1.6 bandı temel alınırsa varsayılan
    gaz kütlesi %0-60 EKSİK olabilir (sayısal çökme faktörü tank geometrisi,
    çalkalanma ve giriş difüzörüne bağlıdır; bu modülde modellenmez).
    Kaynak: Sutton & Biblarz 9. baskı Böl. 6; Huzel & Huang Böl. 5
    (pressurant collapse / use factor).

    Args:
        collapse_factor: Basınçlandırma-çökmesi düzeltmesi [-], band
            :data:`AUTOGENOUS_COLLAPSE_BAND` (1.0-1.6). 1.0 = çökme yok
            (iyimser alt sınır).

    Desteklenmeyen itici için sahte sayı ÜRETMEZ: {'status': 'not_modelled'}.
    """
    key = str(propellant).strip().lower()
    alias = {'lox': 'oxygen', 'lch4': 'methane', 'ch4': 'methane',
             'lh2': 'hydrogen', 'gox': 'oxygen', 'gch4': 'methane'}
    key = alias.get(key, key)
    if key not in AUTOGENOUS_GAS:
        return {'status': 'not_modelled', 'reason':
                f"autogenous basınçlandırma '{propellant}' için modellenmedi "
                f"(desteklenen: {sorted(AUTOGENOUS_GAS)})"}
    gas = AUTOGENOUS_GAS[key]
    T = float(feed_temperature if feed_temperature is not None
              else AUTOGENOUS_FEED_TEMP_K[key])
    eta = float(expulsion_efficiency)
    f_coll = float(collapse_factor)
    if propellant_volume <= 0 or tank_pressure <= 0 or T <= 0 or eta <= 0:
        return {'status': 'error', 'reason': 'girdi pozitif olmalı'}
    lo_c, hi_c = AUTOGENOUS_COLLAPSE_BAND
    if not (lo_c <= f_coll <= hi_c):
        return {'status': 'error', 'reason':
                f'collapse_factor {lo_c}-{hi_c} bandında olmalı '
                f'(verilen: {f_coll})'}
    m_gas_ideal = (float(tank_pressure) * float(propellant_volume)
                   / (gas['R'] * T) / eta)
    # F053: çökme düzeltmesi (varsayılan 1.0 = iyimser alt sınır).
    m_gas = m_gas_ideal * f_coll
    # F052: ısı değiştirici yükü = sıvı duyulur + GİZLİ ISI + gaz duyulur.
    dh, dh_method = autogenous_vaporization_enthalpy(key, T, tank_pressure)
    heat_duty_j = m_gas * dh
    note = (
        'Autogenous (kendinden) basınçlandırma: itici, ısı değiştiriciden '
        'geçirilip gaz olarak kendi tankına geri beslenir (ayrı helyum '
        'şişesi yok). İdeal-gaz, düzenlenmiş tank; Sutton & Biblarz 9. '
        'baskı Böl. 6, Eş. 6-1. Besleme sıcaklığı etiketli varsayımdır. '
        'Isı değiştirici yükü tam entalpi farkıdır (sıvı duyulur + '
        'buharlaşma gizli ısısı h_fg + gaz duyulur), yalnız gaz duyulur '
        'ısısı değil.')
    if f_coll <= 1.0:
        note += (' UYARI: basınçlandırma-çökmesi düzeltmesi uygulanmadı '
                 '(collapse_factor = 1.0). Bu bir İYİMSER ALT SINIRDIR — '
                 'GOX soğuk LOX yüzeyinde, GCH4 metan yüzeyinde yoğuşur ve '
                 'gerçek gaz talebi bu envanterin üstündedir. Sutton Böl. 6 '
                 '/ Huzel & Huang Böl. 5 bandı 1.0-1.6; kriyojenik tank için '
                 'collapse_factor verin.')
    else:
        note += (f' Basınçlandırma-çökmesi düzeltmesi uygulandı '
                 f'(collapse_factor = {f_coll:g}, band {lo_c}-{hi_c}).')
    return {
        'status': 'ok',
        'gas': gas['name'],
        'feed_temperature_k': T,
        'gas_mass_kg': m_gas,
        'gas_mass_no_collapse_kg': m_gas_ideal,
        'collapse_factor': f_coll,
        'collapse_factor_band': [lo_c, hi_c],
        'collapse_factor_is_optimistic_lower_bound': bool(f_coll <= 1.0),
        'gas_specific_R': gas['R'],
        'approx_heat_duty_j': heat_duty_j,
        'vaporization_enthalpy_j_kg': dh,
        'vaporization_enthalpy_method': dh_method,
        'latent_heat_nbp_j_kg': gas['h_fg'],
        'normal_boiling_point_k': gas['T_nbp'],
        'model_note': note,
        'confidence': 'medium',
    }


def analyze_pressurant(mode='regulated', **kwargs):
    """Dispatch to :func:`regulated_pressurant` or :func:`blowdown_pressurant`."""
    m = str(mode).strip().lower()
    if m == 'regulated':
        return regulated_pressurant(**kwargs)
    if m == 'blowdown':
        return blowdown_pressurant(**kwargs)
    if m == 'autogenous':
        return autogenous_pressurant(**kwargs)
    raise ValueError("mode must be 'regulated', 'blowdown', or 'autogenous'")
