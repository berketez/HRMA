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

    m_delivered = m_adia  # conservative (upper) bound for sizing

    # Storage bottle sizing (isothermal blowdown of the bottle) -----------
    P_min = (1.0 + float(regulator_margin)) * P_tank
    if P_min >= P_store:
        raise ValueError(
            "storage_pressure must exceed (1+regulator_margin)*tank_pressure")
    usable_density = (P_store - P_min) / (R * T0)          # kg/m^3
    bottle_volume = m_delivered / usable_density
    stored_mass = P_store * bottle_volume / (R * T0)
    residual_mass = stored_mass - m_delivered
    bottle_count = int(math.ceil(bottle_volume / float(standard_bottle_volume)))

    note = ("Regulated stored-gas system (Sutton 9th ed. Ch. 6; Huzel & Huang "
            "Ch. 5). Delivered gas is bounded by the isothermal (slow) and "
            "adiabatic (fast) limits; the real value lies between. Bottle "
            "sizing assumes isothermal blowdown to P_min=(1+margin)*P_tank -- "
            "fast blowdown cools the bottle and temporarily reduces the "
            "deliverable mass, so add operational margin.")
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
            'stored_mass_kg': float(stored_mass),
            'residual_mass_kg': float(residual_mass),
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


def analyze_pressurant(mode='regulated', **kwargs):
    """Dispatch to :func:`regulated_pressurant` or :func:`blowdown_pressurant`."""
    m = str(mode).strip().lower()
    if m == 'regulated':
        return regulated_pressurant(**kwargs)
    if m == 'blowdown':
        return blowdown_pressurant(**kwargs)
    raise ValueError("mode must be 'regulated' or 'blowdown'")
