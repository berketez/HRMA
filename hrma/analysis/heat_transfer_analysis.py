"""
Heat Transfer Analysis Module
Chamber wall temperature and cooling analysis for hybrid rocket motors.

REVISION (2026-06): Gas-side heat transfer rewritten from a tube-flow
Dittus-Boelter correlation to the Bartz throat correlation, which is the
physically correct model for rocket nozzle/throat gas-side convection.
The previous implementation under-predicted the gas-side coefficient by
~4-15x (UNSAFE direction: burn-through risk invisible). See validation in
tests/test_heat_transfer_validation.py.

Key references:
  - Bartz, D.R. (1957), "A Simple Equation for Rapid Estimation of Rocket
    Nozzle Convective Heat Transfer Coefficients", Jet Propulsion 27(1).
  - Sutton & Biblarz, "Rocket Propulsion Elements", 9th ed., Eq. 8-22 (Bartz).
  - NASA SP-8124, "Liquid Rocket Engine Self-Cooled Combustion Chambers".
  - Huzel & Huang, "Modern Engineering for Design of Liquid-Propellant
    Rocket Engines", AIAA, Chapter 4 (cooling).

IMPORTANT UNITS NOTE (g0 pitfall):
  Sutton 9th ed. Eq. 8-22 is written in US customary units, where the
  (Pc*g0/c*) group uses g0 = 32.174 lbm*ft/(lbf*s^2) as a unit-conversion
  factor between lbf and lbm. In a *consistent SI* system Pc/c* already has
  units of mass flux [kg/(m^2*s)], so g0 must NOT appear. Including g0 in SI
  inflates h_g by g0^0.8 ~ 6.2x. This module uses the SI-consistent form
  (no g0). Dimensional check: kg/s^3/K = W/(m^2*K) exactly (verified).
"""

import numpy as np
import json
import warnings
from typing import Dict, List, Tuple, Optional

from scipy.optimize import brentq

from hrma.data.materials_db import build_materials_view

# Universal gas constant [J/(mol*K)] for frozen Cp / R_specific derivation.
R_UNIVERSAL = 8314.462618  # J/(kmol*K) == J/(mol*K)*1000; here used with MW in g/mol

# ----------------------------------------------------------------------
# Gaz radyasyonu (Leckner) sabitleri
# ----------------------------------------------------------------------
# Yanma ürünü ışıyan tür mol kesri varsayılanları. Hidrokarbon yakıt +
# N2O/LOX oksitleyici sistemlerinde (HTPB/N2O, RP-1/LOX, parafin/N2O)
# denge kompozisyonu tipik olarak ~%20-30 H2O ve ~%10-20 CO2 içerir
# (kalan N2/CO/H2/OH: kızılötesinde ya şeffaf ya ikincil). RocketCEA /
# Cantera kompozisyonu motor_data['x_H2O'] / ['x_CO2'] ile geçilirse
# bu varsayımlar devre dışı kalır.
DEFAULT_X_H2O = 0.25
DEFAULT_X_CO2 = 0.15

# Ortalama ışın uzunluğu katsayısı: L = 0.9 * D (silindirik hazne için
# standart mühendislik yaklaşımı; Hottel ortalama ışın uzunluğu tablosu,
# sonsuz silindir 0.95D, L/D~1 silindir 0.6-0.7D bandının üst-orta değeri).
MEAN_BEAM_LENGTH_FACTOR = 0.9

# Leckner (1972) toplam emisivite korelasyonu katsayı matrisleri.
# Kaynak: B. Leckner, "Spectral and total emissivity of water vapor and
# carbon dioxide", Combustion and Flame 19(1):33-48, 1972; M.F. Modest,
# "Radiative Heat Transfer", 3rd ed., Academic Press, Table 10.4
# (2. baskı Table 11.2) düzeninde:
#
#   eps_0 = exp( sum_i a_i(t) * x^i ),   x = log10(p_a*L / 1 bar*cm),
#   a_i(t) = sum_j C[i][j] * t^j,        t = T / 1000 K.
#
# Satırlar a_0, a_1, a_2; sütunlar t^0, t^1, t^2 (CO2 için t^3 dahil).
_LECKNER_T0 = 1000.0  # K
_LECKNER_H2O = (
    (-2.2118, -1.1987, 0.035596),
    (0.85667, 0.93048, -0.14391),
    (-0.10838, -0.17156, 0.045915),
)
_LECKNER_CO2 = (
    (-3.9893, 2.7669, -2.1081, 0.39163),
    (1.2710, -1.1090, 1.0195, -0.21897),
    (-0.23678, 0.19731, -0.19544, 0.044644),
)
# Korelasyonun fit aralığı dışına taşmayı önleyen kelepçeler (mühendislik
# bekçileri; literatür sınırı değil): sıcaklık Leckner fit aralığında
# tutulur (~300-3000 K). Roket haznesi 3000 K üstünde kalabilir; eps_g
# sıcaklıkla düştüğünden T'yi 3000'de kelepçelemek emisiviteyi hafif
# ABARTIR = muhafazakâr yön (tasarım-yükü felsefesi, codex teyitli).
# Optik derinlik 1e-4..1e3 bar*cm bandında tutulur.
_LECKNER_T_MIN = 300.0    # K
_LECKNER_T_MAX = 3000.0   # K
_LECKNER_PAL_MIN = 1e-4   # bar*cm
_LECKNER_PAL_MAX = 1e3    # bar*cm

class HeatTransferAnalyzer:
    """Heat transfer analysis for hybrid rocket motor chambers"""

    def __init__(self):
        self.stefan_boltzmann = 5.670374419e-8  # W/(m^2*K^4), CODATA 2018
        self.g0 = 9.80665  # m/s^2 (standard gravity; NOT used in SI Bartz)

        # Malzeme veritabanı — MERKEZİ kaynaktan (Dalga 0, 2026-07-14).
        # Eski yerel termal tablo hrma/data/materials_db.py'ye taşındı ve
        # yapısal (mekanik) alanlarla TEK kayıtta birleştirildi (parametre
        # tutarlılığı kuralı). Termal değerler bire bir korunmuştur:
        # steel / steel_4130 / copper / ablative / graphite değişmedi.
        # 'aluminum' ve 'inconel' jenerik anahtarları artık alaşım
        # kayıtlarına (6061-T6, 718) çözülür; ss_304, ss_316, cucrzr ve
        # titanium_6al4v yeni seçilebilir malzemelerdir.
        # 'max_service_temperature': denge cidar sıcaklığı klamp üst sınırı.
        self.materials = build_materials_view()

    # ------------------------------------------------------------------
    # Gas property model (replaces hardcoded k=0.2, mu=5e-5, cp=1200)
    # ------------------------------------------------------------------
    def _get_gas_properties(self, motor_data: Dict, chamber_temperature: float) -> Dict:
        """
        Resolve combustion-gas transport properties for the Bartz correlation.

        Priority order (most authoritative first):
          1. Properties supplied directly in motor_data (e.g. from a prior
             Cantera / RocketCEA equilibrium solve upstream).
          2. Cantera equilibrium of an upstream-provided mechanism/composition
             (motor_data['cantera_gas'] handle), if present.
          3. Bartz-recommended frozen estimates derived from gamma and
             molecular weight, with a temperature-dependent viscosity
             correlation (Bartz 1957 / Sutton & Biblarz).

        Bartz (1957) recommends evaluating cp and Pr in the FROZEN sense:
            Pr = 4*gamma / (9*gamma - 5)              (Sutton & Biblarz Eq. 8-23)
            cp = gamma * R_specific / (gamma - 1)      (calorically-perfect)
        and a viscosity from the kinetic-theory-like correlation:
            mu = 1.184e-7 * (MW)^0.5 * T^0.6   [kg/(m*s)], MW in g/mol, T in K
            (Bartz 1957; reproduced in Sutton & Biblarz 9th ed.)
        """
        # --- gamma / molecular weight / R_specific ---
        gamma = motor_data.get('gamma', motor_data.get('gamma_avg', 1.20))
        # guard against non-physical gamma
        if not (1.05 < gamma < 1.67):
            gamma = 1.20
        molecular_weight = motor_data.get('molecular_weight', None)  # g/mol
        R_specific = motor_data.get('gas_constant', None)            # J/(kg*K)
        if molecular_weight is None and R_specific is not None:
            molecular_weight = R_UNIVERSAL / R_specific
        if molecular_weight is None:
            molecular_weight = 24.0  # g/mol, typical hybrid combustion product mix
        if R_specific is None:
            R_specific = R_UNIVERSAL / molecular_weight

        # --- Prandtl number (frozen, Bartz/Sutton Eq. 8-23) ---
        prandtl = motor_data.get('prandtl', None)
        if prandtl is None:
            prandtl = 4.0 * gamma / (9.0 * gamma - 5.0)

        # --- specific heat cp ---
        gas_cp = motor_data.get('gas_cp', None)  # J/(kg*K)
        if gas_cp is None:
            # calorically-perfect frozen cp from gamma, R_specific
            gas_cp = gamma * R_specific / (gamma - 1.0)

        # --- dynamic viscosity mu [Pa*s] ---
        gas_viscosity = motor_data.get('gas_viscosity', None)
        if gas_viscosity is None:
            # Bartz 1957 viscosity correlation (SI):
            #   mu = 1.184e-7 * MW^0.5 * T^0.6   [kg/(m*s)]
            # MW in g/mol, T in K. Validated vs RocketCEA chamber transport
            # (within ~10-20% for typical 13-30 g/mol combustion gases).
            gas_viscosity = 1.184e-7 * (molecular_weight ** 0.5) * (chamber_temperature ** 0.6)

        # --- thermal conductivity k [W/(m*K)] (derived from Pr definition) ---
        gas_conductivity = motor_data.get('gas_conductivity', None)
        if gas_conductivity is None:
            # k = cp * mu / Pr  (consistent with the Prandtl number above)
            gas_conductivity = gas_cp * gas_viscosity / prandtl

        # --- optional Cantera refinement (only if a gas handle is provided) ---
        # We never silently fabricate a mechanism here; only refine if upstream
        # passed a configured Cantera Solution object set to the burned state.
        cantera_gas = motor_data.get('cantera_gas', None)
        if cantera_gas is not None:
            try:
                cp_ct = float(cantera_gas.cp_mass)           # J/(kg*K)
                mu_ct = float(cantera_gas.viscosity)         # Pa*s
                k_ct = float(cantera_gas.thermal_conductivity)  # W/(m*K)
                if cp_ct > 0 and mu_ct > 0 and k_ct > 0:
                    gas_cp = cp_ct
                    gas_viscosity = mu_ct
                    gas_conductivity = k_ct
                    prandtl = cp_ct * mu_ct / k_ct
            except Exception:
                # fall back silently to the analytic estimates above
                pass

        return {
            'gamma': gamma,
            'molecular_weight': molecular_weight,
            'gas_constant': R_specific,
            'gas_cp': gas_cp,
            'gas_viscosity': gas_viscosity,
            'gas_conductivity': gas_conductivity,
            'prandtl': prandtl,
        }

    # ------------------------------------------------------------------
    # Gaz radyasyonu: Leckner (1972) toplam emisivite / absorptivite
    # ------------------------------------------------------------------
    # Eski model gazı kara cisim sayıyordu (q_rad = eps_w*sigma*(Taw^4-Tw^4)),
    # bu roket haznesi ölçeğinde radyasyonu ~2-6x abartır. Yanma gazı GRİ
    # değil seçici ışıyandır: yalnız H2O ve CO2 bantları önemlidir ve
    # eps_g optik derinliğe (p_i*L) bağlıdır. Aşağıdaki model:
    #   eps_g = eps_H2O + eps_CO2 - delta_eps   (bant örtüşme düzeltmesi)
    # Kaynaklar:
    #   - B. Leckner, "Spectral and total emissivity of water vapor and
    #     carbon dioxide", Combustion and Flame 19(1):33-48, 1972.
    #   - M.F. Modest, "Radiative Heat Transfer", 3rd ed., Academic Press,
    #     Table 10.4 (katsayılar), Eq. (10.140)-(10.145) (basınç ve örtüşme
    #     düzeltmeleri), Eq. (10.146) (absorptivite ölçekleme kuralı).
    #   - Cengel & Ghajar, "Heat and Mass Transfer", 5th ed., Bl. 13-5
    #     (duvar etkin emisivitesi (eps_w+1)/2 yaklaşımı, eps_w > 0.7 için).

    def _species_emissivity(self, species: str, T_g: float, p_total_bar: float,
                            p_partial_bar: float, path_length_cm: float) -> float:
        """
        Tek ışıyan tür (H2O veya CO2) toplam emisivitesi — Leckner (1972).

        eps_0 (1 bar referans) Modest Table 10.4 katsayı matrisiyle,
        basınç düzeltmesi (eps/eps_0) aynı tablonun P_E / (p_a L)_m / A / B / c
        parametreleriyle hesaplanır. Korelasyon fit aralığı dışına taşma
        modül sabitlerindeki kelepçelerle önlenir.
        """
        pal = p_partial_bar * path_length_cm  # bar*cm optik derinlik
        if pal < _LECKNER_PAL_MIN:
            return 0.0  # tür yok ya da optik olarak ihmal edilebilir ince
        pal = min(pal, _LECKNER_PAL_MAX)

        T = min(max(T_g, _LECKNER_T_MIN), _LECKNER_T_MAX)
        t = T / _LECKNER_T0
        x = np.log10(pal)

        # eps_0 = exp(sum_i a_i(t) x^i), a_i(t) = sum_j C[i][j] t^j
        if species == 'h2o':
            coeffs = _LECKNER_H2O
        elif species == 'co2':
            coeffs = _LECKNER_CO2
        else:
            raise ValueError(f"Bilinmeyen ışıyan tür: {species}")
        ln_eps0 = 0.0
        for i, row in enumerate(coeffs):
            a_i = sum(c * t ** j for j, c in enumerate(row))
            ln_eps0 += a_i * x ** i
        eps0 = float(np.exp(ln_eps0))

        # Basınç düzeltmesi (Modest Eq. 10.140-10.143, Table 10.4):
        #   eps/eps_0 = 1 - (A-1)(1-P_E)/(A+B-1+P_E)
        #               * exp(-c*(log10((p_a L)_m/(p_a L)))^2)
        # Payda +P_E: -P_E formu P_E ~ A+B-1 (~2 bar) noktasında kutup
        # üretir ve roket haznesi basınçları tam o bölgeden geçer; +P_E
        # kutupsuzdur ve yüksek basınçta eps/eps_0 > 1 verir (çizgi
        # genişlemesi fiziğiyle tutarlı; codex GPT-5.5 çapraz teyitli).
        if species == 'h2o':
            P_E = p_total_bar + 2.56 * p_partial_bar / np.sqrt(t)
            pal_m = 13.2 * t ** 2
            # Leckner H2O: t < 0.75 için A sabit 2.144 (Modest Table 10.4).
            # Hazne gazında t ~ 3 olduğundan etkisiz; absorptivite duvar
            # sıcaklığında (t ~ 0.6-1.1) değerlendirildiği için orada önemli.
            A = 2.144 if t < 0.75 else 1.888 - 2.053 * np.log10(t)
            B = 1.10 * t ** (-1.4)
            c_damp = 0.5
        else:  # co2
            P_E = p_total_bar + 0.28 * p_partial_bar
            pal_m = 0.054 / t ** 2 if t < 0.7 else 0.225 * t ** 2
            A = 1.0 + 0.1 * t ** (-1.45)
            B = 0.23
            c_damp = 1.47

        denom = A + B - 1.0 + P_E
        if abs(denom) < 1e-6:
            factor = 1.0  # savunmacı bekçi (P_E >= 0 iken erişilmez)
        else:
            factor = 1.0 - ((A - 1.0) * (1.0 - P_E) / denom) * np.exp(
                -c_damp * (np.log10(pal_m / pal)) ** 2
            )
        # Fit aralığı dışındaki uçlarda düzeltme patlamasın: Leckner
        # çizelgelerinde basınç düzeltmesi ~0.3x-2x bandında kalır.
        factor = min(max(factor, 0.3), 2.0)

        return float(min(max(eps0 * factor, 0.0), 0.995))

    def _gas_emissivity(self, T_g: float, p_total_bar: float, beam_length_m: float,
                        x_H2O: float = DEFAULT_X_H2O,
                        x_CO2: float = DEFAULT_X_CO2) -> float:
        """
        Toplam yanma gazı emisivitesi eps_g(T_g, p, L) — Leckner (1972).

            eps_g = eps_H2O + eps_CO2 - delta_eps

        delta_eps: H2O/CO2 bant örtüşme düzeltmesi (Leckner; Modest Eq. 10.145):
            zeta = p_w/(p_w+p_c)
            delta_eps = (zeta/(10.7+101*zeta) - 0.0089*zeta^10.4)
                        * (log10((p_w+p_c)*L))^2.76
        Formül T >= 1000 K bandı için verilmiştir; daha düşük sıcaklıklarda
        (absorptivite değerlendirmesinde duvar sıcaklığı) aynı ifade küçük
        değerler ürettiğinden mühendislik yaklaşımı olarak korunur.

        Args:
            T_g: Gaz (statik) sıcaklığı [K].
            p_total_bar: Toplam basınç [bar].
            beam_length_m: Ortalama ışın uzunluğu L [m]
                (silindirik hazne için L = 0.9*D, modül sabiti).
            x_H2O, x_CO2: Işıyan tür mol kesirleri. Varsayılanlar hidrokarbon
                yakıt + N2O/LOX yanması denge kompozisyonunun tipik bandı
                (modül sabitleri DEFAULT_X_H2O/DEFAULT_X_CO2, gerekçe orada).

        Returns:
            eps_g in [0, 0.995].
        """
        L_cm = max(beam_length_m, 0.0) * 100.0
        p_w = max(x_H2O, 0.0) * p_total_bar
        p_c = max(x_CO2, 0.0) * p_total_bar

        eps_w = self._species_emissivity('h2o', T_g, p_total_bar, p_w, L_cm)
        eps_c = self._species_emissivity('co2', T_g, p_total_bar, p_c, L_cm)

        # Bant örtüşme düzeltmesi — yalnız iki tür de mevcutken ve toplam
        # optik derinlik > 1 bar*cm iken anlamlı (log10 tabanı; altında
        # negatif tabanın kesirli kuvveti tanımsız olur, örtüşme zaten ~0).
        delta_eps = 0.0
        pal_sum = (p_w + p_c) * L_cm
        if eps_w > 0.0 and eps_c > 0.0 and pal_sum > 1.0:
            zeta = p_w / (p_w + p_c)
            delta_eps = (
                zeta / (10.7 + 101.0 * zeta) - 0.0089 * zeta ** 10.4
            ) * np.log10(pal_sum) ** 2.76
            delta_eps = min(max(delta_eps, 0.0), eps_w + eps_c)

        return float(min(max(eps_w + eps_c - delta_eps, 0.0), 0.995))

    def _gas_absorptivity(self, T_g: float, T_w: float, p_total_bar: float,
                          beam_length_m: float,
                          x_H2O: float = DEFAULT_X_H2O,
                          x_CO2: float = DEFAULT_X_CO2) -> float:
        """
        Gazın duvar ışınımına karşı absorptivitesi — Leckner pratik kuralı
        (Modest Eq. 10.146):

            alpha_g(T_g -> T_w) = (T_g/T_w)^0.5 * eps_g(T_w, p*L*(T_w/T_g))

        Emisivite duvar sıcaklığında, optik derinlik T_w/T_g ile
        ölçeklenmiş yol üzerinden değerlendirilir.
        """
        T_g_eff = max(T_g, 1.0)
        T_w_eff = max(T_w, _LECKNER_T_MIN)  # korelasyon alt sınırı
        scale = T_w_eff / T_g_eff
        alpha = (T_g_eff / T_w_eff) ** 0.5 * self._gas_emissivity(
            T_w_eff, p_total_bar, beam_length_m * scale, x_H2O, x_CO2
        )
        return float(min(max(alpha, 0.0), 0.995))

    def _gas_radiation_flux(self, T_g: float, T_w: float, p_total_bar: float,
                            beam_length_m: float,
                            x_H2O: float = DEFAULT_X_H2O,
                            x_CO2: float = DEFAULT_X_CO2,
                            wall_emissivity: float = 0.8) -> float:
        """
        Gaz-duvar net radyatif ısı akısı [W/m^2]:

            q_rad = sigma * (eps_w+1)/2 * (eps_g*T_g^4 - alpha_g*T_w^4)

        (eps_w+1)/2 etkin duvar emisivitesi, gri duvar (eps_w > ~0.7) ile
        izotermal gaz arasındaki alışveriş için standart mühendislik
        yaklaşımıdır (Hottel; Cengel & Ghajar Bl. 13-5). Eski kara cisim
        modeline göre q_rad DÜŞER — beklenen fiziksel davranış budur
        (roket haznesinde radyasyon toplam akının tipik %5-30'u).
        """
        eps_g = self._gas_emissivity(T_g, p_total_bar, beam_length_m, x_H2O, x_CO2)
        alpha_g = self._gas_absorptivity(T_g, T_w, p_total_bar, beam_length_m,
                                         x_H2O, x_CO2)
        eps_wall_eff = 0.5 * (min(max(wall_emissivity, 0.0), 1.0) + 1.0)
        T_w_pos = max(T_w, 0.0)
        return float(
            eps_wall_eff * self.stefan_boltzmann
            * (eps_g * T_g ** 4 - alpha_g * T_w_pos ** 4)
        )

    # ------------------------------------------------------------------
    # Throat conditions (replaces throat_flux = chamber*1.5 hardcode)
    # ------------------------------------------------------------------
    def _resolve_throat_conditions(self, motor_data: Dict, chamber_pressure: float,
                                   chamber_temperature: float, gas: Dict,
                                   mdot_total: float) -> Dict:
        """
        Compute real throat geometry and stagnation->throat conditions.

        c* (characteristic velocity) from theory if not provided:
            c* = sqrt(gamma * R * Tc) / ( gamma * sqrt( (2/(gamma+1))^((gamma+1)/(gamma-1)) ) )
            (Sutton & Biblarz Eq. 3-32)
        Throat area from continuity at the choked throat if not provided:
            A_t = mdot * c* / Pc          (definition of c*: Pc*A_t = mdot*c*)
        Throat temperature (static) for sigma correction:
            T_t = Tc / (1 + (gamma-1)/2)   (M=1)
        """
        gamma = gas['gamma']
        R = gas['gas_constant']

        # characteristic velocity c* [m/s]
        c_star = motor_data.get('c_star', motor_data.get('cstar', None))
        if c_star is None:
            num = np.sqrt(gamma * R * chamber_temperature)
            den = gamma * np.sqrt((2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0)))
            c_star = num / den

        # throat diameter [m]
        throat_diameter = motor_data.get('throat_diameter', None)
        throat_area = motor_data.get('throat_area', None)
        if throat_diameter is not None:
            throat_area = np.pi * (throat_diameter / 2.0) ** 2
        elif throat_area is not None:
            throat_diameter = 2.0 * np.sqrt(throat_area / np.pi)
        else:
            # A_t = mdot * c* / Pc  (continuity at choked throat)
            if mdot_total > 0 and chamber_pressure > 0:
                throat_area = mdot_total * c_star / chamber_pressure
            else:
                # last resort: assume throat ~ 0.3 * chamber diameter
                chamber_diameter = motor_data.get('chamber_diameter', 0.1)
                throat_area = np.pi * (0.3 * chamber_diameter / 2.0) ** 2
            throat_diameter = 2.0 * np.sqrt(throat_area / np.pi)

        # throat radius of curvature (for the (Dt/Rc)^0.1 term).
        # Typical converging-diverging nozzles: Rc ~ 0.5..2 * throat radius.
        # Use Rc = 1.5 * throat_radius if not provided (common Bartz assumption).
        throat_radius = throat_diameter / 2.0
        rc = motor_data.get('throat_radius_curvature', 1.5 * throat_radius)
        rc_over_dt = max(rc / throat_diameter, 0.25)  # keep correction bounded

        # static throat temperature (M=1)
        throat_temperature = chamber_temperature / (1.0 + (gamma - 1.0) / 2.0)

        return {
            'c_star': c_star,
            'throat_diameter': throat_diameter,
            'throat_area': throat_area,
            'throat_radius_curvature': rc,
            'rc_over_dt': rc_over_dt,
            'throat_temperature': throat_temperature,
        }

    # ------------------------------------------------------------------
    # Bartz gas-side coefficient
    # ------------------------------------------------------------------
    def _bartz_coefficient(self, throat_diameter: float, chamber_pressure: float,
                           c_star: float, gas: Dict, chamber_temperature: float,
                           wall_temperature: float, rc_over_dt: float,
                           area_ratio_local: float = 1.0, mach_local: float = 1.0) -> float:
        """
        Bartz convective heat-transfer coefficient (SI-consistent, no g0).

        Sutton & Biblarz 9th ed. Eq. 8-22 (Bartz 1957), SI form:

          h_g = (0.026 / D_t^0.2)
                * (mu^0.2 * cp / Pr^0.6)
                * (Pc / c*)^0.8
                * (D_t / R_c)^0.1
                * (A_t / A)^0.9
                * sigma

        with the boundary-layer property correction (Sutton Eq. 8-22):

          sigma = 1 / { [ 0.5*(Tw/Tc)*(1 + (g-1)/2 * M^2) + 0.5 ]^0.68
                        * [ 1 + (g-1)/2 * M^2 ]^0.12 }

        Returns h_g in W/(m^2*K).  area_ratio_local = A_t/A (=1 at throat).
        """
        mu = gas['gas_viscosity']
        cp = gas['gas_cp']
        Pr = gas['prandtl']
        gamma = gas['gamma']

        # boundary-layer correction factor sigma
        m2 = 1.0 + (gamma - 1.0) / 2.0 * mach_local ** 2
        t_ratio = wall_temperature / chamber_temperature
        sigma = 1.0 / ((0.5 * t_ratio * m2 + 0.5) ** 0.68 * m2 ** 0.12)

        # NO g0 in SI: Pc/c* already has units kg/(m^2*s).
        mass_flux_term = (chamber_pressure / c_star) ** 0.8
        prop_term = (mu ** 0.2) * cp / (Pr ** 0.6)
        curvature_term = (1.0 / rc_over_dt) ** 0.1  # (D_t / R_c)^0.1
        area_term = area_ratio_local ** 0.9

        h_g = (0.026 / throat_diameter ** 0.2) * prop_term * mass_flux_term \
            * curvature_term * area_term * sigma
        return h_g

    def _adiabatic_wall_temperature(self, chamber_temperature: float, gas: Dict,
                                    mach_local: float = 1.0) -> float:
        """
        Adiabatic (recovery) wall temperature — the correct driving temperature
        for q = h_g*(Taw - Tw), NOT the stagnation temperature.

          Taw = Tc * (1 + r*(g-1)/2 * M^2) / (1 + (g-1)/2 * M^2)
          r   = Pr^(1/3)  (turbulent recovery factor; Sutton & Biblarz)
        """
        gamma = gas['gamma']
        Pr = gas['prandtl']
        r = Pr ** (1.0 / 3.0)
        m2 = (gamma - 1.0) / 2.0 * mach_local ** 2
        return chamber_temperature * (1.0 + r * m2) / (1.0 + m2)

    def _coolant_side_coefficient(self, motor_data: Dict, cooling_type: str) -> float:
        """
        Soğutucu tarafı film katsayısı [W/(m^2*K)] — TEK merkezi kaynak.

        Rejeneratif değer soğutma kanallarındaki yüksek hızlı sıvıyı yansıtır
        (Huzel & Huang Böl. 4: kriyojenik/sıvı rejeneratif için tipik olarak
        1e4-5e4 W/m^2/K); önceki 2000 W/m^2/K bir mertebe düşüktü ve cidarı
        adyabatiğe yakın kilitliyordu. Hem throat-analizi hem eksenel profil
        aynı değerleri kullanır (parametre tutarlılığı kuralı).
        """
        h_coolant = motor_data.get('coolant_side_coefficient', None)
        if h_coolant is not None:
            return float(h_coolant)
        if cooling_type == 'forced':
            return 100.0     # zorlanmış hava soğutması
        if cooling_type == 'regenerative':
            return 20000.0   # sıvı rejeneratif soğutma (Huzel & Huang)
        return 25.0          # doğal taşınım (hava) — bilinmeyen tip dahil

    @staticmethod
    def _mach_from_area_ratio(area_ratio: float, gamma: float,
                              supersonic: bool) -> float:
        """
        İzantropik alan-Mach bağıntısını çözer (Sutton & Biblarz Eq. 3-14):

          A/A* = (1/M) * [ (2/(g+1)) * (1 + (g-1)/2 * M^2) ]^((g+1)/(2(g-1)))

        area_ratio = A/A_t (>= 1). supersonic=False konverjan (subsonik dal),
        True diverjan (süpersonik dal) içindir; boğazda (A/A_t=1) M=1 döner.
        """
        eps = float(area_ratio)
        if eps <= 1.0 + 1e-9:
            return 1.0
        exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))

        def f(M):
            return (1.0 / M) * ((2.0 / (gamma + 1.0))
                                * (1.0 + (gamma - 1.0) / 2.0 * M * M)) ** exponent - eps

        if supersonic:
            return float(brentq(f, 1.0 + 1e-9, 100.0, xtol=1e-10, maxiter=200))
        return float(brentq(f, 1e-6, 1.0 - 1e-9, xtol=1e-12, maxiter=200))

    # ==================================================================
    # PUBLIC API (signature preserved)
    # ==================================================================
    def analyze_heat_transfer(self, motor_data: Dict, material: str = 'steel',
                            wall_thickness: float = 0.005, ambient_temp: float = 293.15,
                            cooling_type: str = 'natural') -> Dict:
        """
        Complete heat transfer analysis (Bartz-based gas side).

        Args:
            motor_data: Motor performance and geometry data. Recognized optional
                keys (used when present, otherwise physically derived):
                  chamber_pressure [bar], chamber_temperature [K],
                  chamber_diameter [m], chamber_length [m], burn_time [s],
                  mdot_total [kg/s], gamma, molecular_weight [g/mol],
                  gas_constant [J/kg/K], gas_cp, gas_viscosity, gas_conductivity,
                  prandtl, c_star [m/s], throat_diameter [m], throat_area [m^2],
                  throat_radius_curvature [m], cantera_gas (Cantera Solution).
            material: Wall material key (hrma.data.materials_db: steel,
                steel_4130, ss_304, ss_316, aluminum_6061, titanium_6al4v,
                inconel_718, copper, cucrzr, ablative, graphite; aliases
                aluminum/inconel/titanium resolve to the alloy records).
            wall_thickness: Wall thickness in meters.
            ambient_temp: Ambient / coolant inlet temperature in K.
            cooling_type: 'natural', 'forced', 'regenerative'.

        Returns:
            Heat transfer analysis results (dict). Top-level keys preserved:
            heat_transfer_coefficients, gas_side_analysis, wall_analysis,
            cooling_analysis, safety_analysis, material_properties,
            design_parameters.
        """
        # Extract motor parameters
        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
        chamber_length = motor_data.get('chamber_length', 0.5)  # m
        burn_time = motor_data.get('burn_time', 10)  # s
        mdot_total = motor_data.get('mdot_total', 1.0)  # kg/s

        # Get material properties (steel_4130 now resolves directly)
        mat_props = self.materials.get(material, self.materials['steel'])

        # Resolve gas properties + throat conditions (no hardcoding)
        gas = self._get_gas_properties(motor_data, chamber_temperature)
        throat = self._resolve_throat_conditions(
            motor_data, chamber_pressure, chamber_temperature, gas, mdot_total
        )

        # Calculate heat transfer coefficients (Bartz gas side)
        heat_transfer_coeffs = self._calculate_heat_transfer_coefficients(
            motor_data, mat_props, cooling_type, gas, throat,
            chamber_pressure, chamber_temperature
        )

        # Gas-side heat transfer (with energy-balance wall temperature)
        gas_side_analysis = self._analyze_gas_side_heat_transfer(
            chamber_pressure, chamber_temperature, chamber_diameter, chamber_length,
            mdot_total, heat_transfer_coeffs, gas, throat, mat_props,
            wall_thickness, ambient_temp
        )

        # Wall temperature distribution (uses the energy-balance flux)
        wall_analysis = self._analyze_wall_temperature(
            gas_side_analysis['heat_flux'], wall_thickness, mat_props,
            ambient_temp, heat_transfer_coeffs['coolant_side'],
            chamber_temperature, gas_side_analysis
        )

        # Cooling requirements
        cooling_analysis = self._analyze_cooling_requirements(
            gas_side_analysis['total_heat_rate'], burn_time, motor_data, cooling_type
        )

        # Safety analysis
        safety_analysis = self._analyze_thermal_safety(
            wall_analysis['max_temperature'], mat_props, wall_thickness, chamber_pressure
        )
        # Surface energy-balance warnings.
        safety_analysis['warnings'] = (
            list(safety_analysis.get('warnings', [])) + gas_side_analysis.get('warnings', [])
        )

        return {
            'heat_transfer_coefficients': heat_transfer_coeffs,
            'gas_side_analysis': gas_side_analysis,
            'wall_analysis': wall_analysis,
            'cooling_analysis': cooling_analysis,
            'safety_analysis': safety_analysis,
            'material_properties': mat_props,
            'design_parameters': {
                'material': material,
                'wall_thickness': wall_thickness * 1000,  # mm
                'cooling_type': cooling_type,
                'ambient_temperature': ambient_temp
            }
        }

    def analyze_axial_profile(self, motor_data: Dict, n_stations: int = 40,
                              material: str = 'steel',
                              wall_thickness: float = 0.005,
                              ambient_temp: float = 293.15,
                              cooling_type: str = 'natural') -> Dict:
        """
        Eksenel ısı yükü profili: hazne çıkışı -> boğaz -> nozul çıkışı.

        Nozul iç konturu TEK ortak geometri kaynağından örneklenir
        (hrma.engines.nozzle_design.sample_nozzle_inner_contour — 2D/3D/CAD
        ile aynı kontur; kopya geometri YOK). Her istasyonda:

          - A(x)/A_t alan oranı (kontur yarıçapından),
          - izantropik M(x) (konverjanda subsonik, diverjanda süpersonik dal),
          - Bartz h_g(x) = _bartz_coefficient(area_ratio_local=A_t/A, M) —
            throat-analiziyle AYNI korelasyon ve gaz özellikleri,
          - kurtarma (recovery/adyabatik cidar) sıcaklığı Taw(x),
          - muhafazakâr tasarım ısı akısı q(x) (taşınım + radyasyon,
            referans soğutulmuş cidarda — modülün 'design flux' felsefesi),
          - belirtilen soğutma için denge cidar sıcaklığı T_wall_eq(x)
            (yüzey enerji dengesi, bisection).

        Args:
            motor_data: analyze_heat_transfer ile aynı şema (chamber_pressure
                [bar], chamber_temperature [K], gamma, molecular_weight,
                mdot_total, throat_diameter/exit_diameter [m], ...).
            n_stations: Toplam istasyon sayısı (boğaz istasyonu garanti dahil).
            material / wall_thickness / ambient_temp / cooling_type:
                analyze_heat_transfer ile aynı cidar girdileri.

        Returns:
            {'x_mm', 'area_ratio', 'mach', 'h_g', 'q_MW', 'T_wall_eq',
             'T_recovery', 'x_throat_mm', 'x_exit_mm', 'throat_index', ...}
            Tüm diziler eşit uzunluktadır; grafik üretilmez (frontend çizer).
        """
        # Tembel import: hrma.engines.__init__ -> hybrid_rocket_engine ->
        # heat_transfer_analysis zinciri modül-üstü importta döngü yaratır.
        from hrma.engines.nozzle_design import sample_nozzle_inner_contour

        n_stations = int(max(5, min(int(n_stations), 400)))

        chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        mdot_total = motor_data.get('mdot_total', 1.0)  # kg/s

        mat_props = self.materials.get(material, self.materials['steel'])
        gas = self._get_gas_properties(motor_data, chamber_temperature)
        throat = self._resolve_throat_conditions(
            motor_data, chamber_pressure, chamber_temperature, gas, mdot_total
        )
        gamma = gas['gamma']

        # --- Kontur: geometri sözlüğünü çözülen boğaz/çıkış çapıyla besle ---
        # (motor_data'da yoksa sampler'ın jenerik fallback'i yerine Bartz ile
        # tutarlı gerçek boğaz çapı kullanılır; alan oranları fizikle uyumlu
        # kalır.)
        md_geo = dict(motor_data)
        md_geo.setdefault('throat_diameter', throat['throat_diameter'])
        if md_geo.get('exit_diameter') in (None, 0, ''):
            expansion_ratio = motor_data.get('expansion_ratio', None)
            try:
                expansion_ratio = float(expansion_ratio)
            except (TypeError, ValueError):
                expansion_ratio = 0.0
            if expansion_ratio and expansion_ratio > 1.0:
                md_geo['exit_diameter'] = (
                    md_geo['throat_diameter'] * np.sqrt(expansion_ratio)
                )
            else:
                md_geo.pop('exit_diameter', None)

        contour_pts, contour_meta = sample_nozzle_inner_contour(md_geo)
        z_pts = np.array([p[0] for p in contour_pts], dtype=float)  # mm
        r_pts = np.array([p[1] for p in contour_pts], dtype=float)  # mm
        z_throat = float(contour_meta['z_throat'])
        z_exit = float(contour_meta['z_exit'])
        r_throat = float(contour_meta['r_throat'])

        # --- İstasyon ızgarası: boğaz istasyonu KESİN dahil ---
        # Konverjan/diverjan pay dağılımı uzunlukla orantılı; boğaz noktası
        # iki parçanın ortak ucu (q maks ve M=1 tam boğazda yakalanır).
        frac_conv = z_throat / z_exit if z_exit > 0 else 0.5
        n_conv_st = int(round(n_stations * frac_conv))
        n_conv_st = min(max(n_conv_st, 2), n_stations - 1)
        n_div_st = n_stations - n_conv_st + 1  # boğaz paylaşılır
        x_conv = np.linspace(0.0, z_throat, n_conv_st)
        x_div = np.linspace(z_throat, z_exit, n_div_st)[1:]
        x_mm = np.concatenate([x_conv, x_div])
        throat_index = n_conv_st - 1

        # Kontur z ekseni monotonik artar (konverjan -> yay -> diverjan);
        # doğrusal interpolasyon güvenlidir ve tüm örnek yarıçaplar >= r_t.
        r_mm = np.interp(x_mm, z_pts, r_pts)
        area_ratio = np.maximum((r_mm / r_throat) ** 2, 1.0)  # A/A_t >= 1
        area_ratio[throat_index] = 1.0  # boğazda kesin 1 (interp toleransı)

        # --- İstasyon döngüsü ---
        throat_d = throat['throat_diameter']
        c_star = throat['c_star']
        rc_over_dt = throat['rc_over_dt']
        emissivity = mat_props.get('emissivity', 0.8)
        # Işıyan tür kesirleri: kompozisyon verilmişse ondan, yoksa modül
        # varsayılanı (DEFAULT_X_H2O/DEFAULT_X_CO2 — gerekçe sabitlerde).
        x_h2o_frac = float(motor_data.get('x_H2O', DEFAULT_X_H2O))
        x_co2_frac = float(motor_data.get('x_CO2', DEFAULT_X_CO2))
        k_wall = mat_props['thermal_conductivity']
        allowable = mat_props.get('allowable_temperature', 1073)
        h_coolant = self._coolant_side_coefficient(motor_data, cooling_type)
        R_out = wall_thickness / k_wall + 1.0 / h_coolant  # m^2*K/W

        mach = np.empty(n_stations)
        h_g = np.empty(n_stations)
        q_flux = np.empty(n_stations)     # W/m^2
        t_recovery = np.empty(n_stations)
        t_wall_eq = np.empty(n_stations)

        for i in range(n_stations):
            supersonic = i > throat_index
            M = self._mach_from_area_ratio(area_ratio[i], gamma, supersonic)
            mach[i] = M

            # Kurtarma (adyabatik cidar) sıcaklığı — q'nun sürücü sıcaklığı.
            Taw = self._adiabatic_wall_temperature(chamber_temperature, gas, M)
            t_recovery[i] = Taw

            # Referans soğutulmuş cidar (modülün tasarım-akısı felsefesi):
            # malzeme izin sıcaklığı, ama Taw'ın ~%80'inden sıcak değil.
            Tw_ref = min(allowable, 0.8 * Taw)
            Tw_ref = max(Tw_ref, ambient_temp)

            h_i = self._bartz_coefficient(
                throat_d, chamber_pressure, c_star, gas,
                chamber_temperature, Tw_ref, rc_over_dt,
                area_ratio_local=1.0 / area_ratio[i],  # A_t/A (boğazda 1)
                mach_local=M
            )
            h_g[i] = h_i

            # Radyasyon: Leckner gaz emisivitesi (kara cisim DEĞİL). Yayan
            # gaz yerel STATİK sıcaklık/basınçta; ışın uzunluğu yerel çapla.
            T_stat = chamber_temperature / (1.0 + 0.5 * (gamma - 1.0) * M * M)
            p_stat_bar = (chamber_pressure / 1e5) * (
                1.0 + 0.5 * (gamma - 1.0) * M * M
            ) ** (-gamma / (gamma - 1.0))
            beam_local = MEAN_BEAM_LENGTH_FACTOR * (2.0 * r_mm[i] / 1000.0)

            def gas_side_flux(Tw):
                q_conv = h_i * (Taw - Tw)
                q_rad = self._gas_radiation_flux(
                    T_stat, Tw, p_stat_bar, beam_local,
                    x_H2O=x_h2o_frac, x_CO2=x_co2_frac,
                    wall_emissivity=emissivity,
                )
                return q_conv + max(q_rad, 0.0)

            q_flux[i] = gas_side_flux(Tw_ref)

            # Denge cidar sıcaklığı: q_in(Tw) = (Tw - T_amb)/R_out, bisection.
            def q_out(Tw):
                return (Tw - ambient_temp) / R_out

            lo, hi = ambient_temp, Taw
            if (gas_side_flux(lo) - q_out(lo)) <= 0:
                t_wall_eq[i] = ambient_temp
            elif (gas_side_flux(hi) - q_out(hi)) >= 0:
                t_wall_eq[i] = hi
            else:
                for _ in range(200):
                    mid = 0.5 * (lo + hi)
                    if (gas_side_flux(mid) - q_out(mid)) > 0:
                        lo = mid
                    else:
                        hi = mid
                    if hi - lo < 1e-3:
                        break
                t_wall_eq[i] = 0.5 * (lo + hi)

        return {
            # İstenen çekirdek şema — tüm diziler eşit uzunlukta
            'x_mm': x_mm.tolist(),
            'area_ratio': area_ratio.tolist(),      # A(x)/A_t (>= 1)
            'mach': mach.tolist(),
            'h_g': h_g.tolist(),                    # W/(m^2*K)
            'q_MW': (q_flux / 1e6).tolist(),        # MW/m^2 (tasarım yükü)
            'T_wall_eq': t_wall_eq.tolist(),        # K (denge, verilen soğutma)
            # Ek (additive) meta — frontend işaretçileri ve teşhis için
            'T_recovery': t_recovery.tolist(),      # K (adyabatik cidar)
            'x_throat_mm': z_throat,
            'x_exit_mm': z_exit,
            'throat_index': throat_index,
            'throat_diameter_m': throat_d,
            'nozzle_type': contour_meta.get('noz_type'),
            'material': material,
            'cooling_type': cooling_type,
            'wall_thickness_mm': wall_thickness * 1000.0,
            'n_stations': n_stations,
        }

    def _calculate_heat_transfer_coefficients(self, motor_data: Dict,
                                           mat_props: Dict, cooling_type: str,
                                           gas: Optional[Dict] = None,
                                           throat: Optional[Dict] = None,
                                           chamber_pressure: Optional[float] = None,
                                           chamber_temperature: Optional[float] = None) -> Dict:
        """
        Calculate heat transfer coefficients.

        Gas side now uses the Bartz throat correlation (physically correct for
        rocket nozzles) instead of the Dittus-Boelter pipe-flow correlation,
        which under-predicted h_g by ~4-15x in the unsafe direction.
        """
        # Backward-compatible resolution if called without the new args.
        if chamber_pressure is None:
            chamber_pressure = motor_data.get('chamber_pressure', 20.0) * 1e5  # Pa
        if chamber_temperature is None:
            chamber_temperature = motor_data.get('chamber_temperature', 3000)  # K
        mdot_total = motor_data.get('mdot_total', 1.0)
        if gas is None:
            gas = self._get_gas_properties(motor_data, chamber_temperature)
        if throat is None:
            throat = self._resolve_throat_conditions(
                motor_data, chamber_pressure, chamber_temperature, gas, mdot_total
            )

        # --- Gas-side: Bartz at the throat (M=1, A_t/A=1) ---
        # Use an estimated cooled-wall temperature for the first sigma estimate;
        # the gas-side analysis later refines wall temperature via energy balance.
        wall_guess = min(0.5 * chamber_temperature, mat_props.get('max_service_temperature', 2000) * 0.8)
        h_gas = self._bartz_coefficient(
            throat['throat_diameter'], chamber_pressure, throat['c_star'],
            gas, chamber_temperature, wall_guess, throat['rc_over_dt'],
            area_ratio_local=1.0, mach_local=1.0
        )

        # Reynolds / Nusselt reported at the throat for reference/diagnostics.
        throat_d = throat['throat_diameter']
        # Boğaz statik yoğunluğu STATİK boğaz basıncıyla hesaplanmalı: tıkanmış
        # (M=1) boğazda statik basınç P_t = Pc·(2/(γ+1))^(γ/(γ-1)) < Pc'dir.
        # Durgunluk oda basıncı Pc'yi statik boğaz sıcaklığıyla (T_t) eşleştirmek
        # yoğunluğu -ve dolayısıyla raporlanan Reynolds/Nusselt'i- ~1.8x şişirir.
        # Tutarlılık: rho_t·a_t = Pc/c* (boğaz kütle akısı). Yalnız diagnostik
        # (h_gas ayrı Bartz korelasyonuyla hesaplanır, bu değerden etkilenmez).
        throat_static_pressure = chamber_pressure * (2.0 / (gas['gamma'] + 1.0)) ** (
            gas['gamma'] / (gas['gamma'] - 1.0))
        rho_throat = throat_static_pressure / (gas['gas_constant'] * throat['throat_temperature'])
        a_throat = np.sqrt(gas['gamma'] * gas['gas_constant'] * throat['throat_temperature'])
        v_throat = a_throat  # M=1
        reynolds = rho_throat * v_throat * throat_d / gas['gas_viscosity']
        prandtl = gas['prandtl']
        nusselt = h_gas * throat_d / gas['gas_conductivity']

        # --- Coolant side ---
        h_coolant = self._coolant_side_coefficient(motor_data, cooling_type)

        return {
            'gas_side': h_gas,
            'coolant_side': h_coolant,
            'reynolds_number': reynolds,
            'prandtl_number': prandtl,
            'nusselt_number': nusselt,
            # extra diagnostics (additive, do not break existing consumers)
            'correlation': 'Bartz (Sutton & Biblarz 9th ed. Eq. 8-22)',
            'c_star': throat['c_star'],
            'throat_diameter': throat['throat_diameter'],
            'gas_viscosity': gas['gas_viscosity'],
            'gas_conductivity': gas['gas_conductivity'],
            'gas_cp': gas['gas_cp'],
            'gamma': gas['gamma'],
        }

    def _analyze_gas_side_heat_transfer(self, pressure: float, temperature: float,
                                      diameter: float, length: float, mdot: float,
                                      coeffs: Dict, gas: Dict, throat: Dict,
                                      mat_props: Dict, wall_thickness: float,
                                      ambient_temp: float) -> Dict:
        """
        Analyze gas-side heat transfer.

        Two distinct quantities are computed, and conflating them is exactly the
        bug that previously hid burn-through:

        (A) DESIGN HEAT FLUX (safety-relevant load). The convective+radiative
            heat flux the cooling system MUST remove, evaluated at a conservative
            *reference cooled wall temperature* (the material allowable temp,
            bounded). This is q = h_g*(Taw - Tw_ref) + q_rad(Taw, Tw_ref), where
            q_rad uses the Leckner (1972) H2O/CO2 gas emissivity model (see
            _gas_radiation_flux) instead of the former black-body assumption.
            It must NOT be allowed to collapse to zero — letting the wall float to
            the adiabatic temperature drives q->0 and masks the danger.

        (B) EQUILIBRIUM WALL TEMPERATURE (cooling-adequacy check). The steady
            wall temperature actually reached for the *specified* cooling, from
            the surface energy balance q_in(Tw) = q_out(Tw):
                q_in  = h_g*(Taw - Tw) + q_rad(Taw, Tw)   [Leckner gas radiation]
                q_out = (Tw - T_coolant) / (R_cond + R_coolant)
            If Tw floats near Taw, the cooling is grossly inadequate (warn).

        References: Bartz (1957); Sutton & Biblarz 9th ed. Ch. 8;
        NASA SP-8124; Huzel & Huang Ch. 4; Leckner, Comb. Flame 19:33 (1972).
        """
        warnings_list: List[str] = []

        h_gas = coeffs['gas_side']
        h_coolant = coeffs['coolant_side']
        k_wall = mat_props['thermal_conductivity']
        emissivity = mat_props.get('emissivity', 0.8)
        max_service = mat_props.get('max_service_temperature', 2000)
        allowable = mat_props.get('allowable_temperature', 1073)

        # Adiabatic wall (recovery) temperature at the throat (M=1).
        Taw = self._adiabatic_wall_temperature(temperature, gas, mach_local=1.0)

        # --- (A) DESIGN HEAT FLUX at a conservative reference cooled wall ---
        # Reference wall temperature: the material allowable temperature, but not
        # warmer than ~80% of Taw (a well-cooled wall is always below Taw). This
        # guarantees a non-zero, conservative thermal load even if the modelled
        # cooling is weak. Lower reference wall => higher (more conservative) q.
        Tw_ref = min(allowable, 0.8 * Taw)
        Tw_ref = max(Tw_ref, ambient_temp)

        # Radyasyon: Leckner gaz emisivitesi (kara cisim DEĞİL). Muhafazakâr
        # tasarım yükü felsefesine uygun olarak hazne koşulları kullanılır
        # (T_g = Taw ~ T_c, p = P_c, L = 0.9*D_hazne); nozulda statik T/p
        # düşer, yani bu seçim güvenli taraftadır.
        p_total_bar = pressure / 1e5
        beam_length = MEAN_BEAM_LENGTH_FACTOR * diameter

        def gas_side_flux(Tw, h):
            q_conv = h * (Taw - Tw)
            q_rad = self._gas_radiation_flux(
                Taw, Tw, p_total_bar, beam_length, wall_emissivity=emissivity
            )
            return q_conv + max(q_rad, 0.0)

        throat_heat_flux = gas_side_flux(Tw_ref, h_gas)  # W/m^2 (real design load)

        # --- (B) EQUILIBRIUM WALL TEMPERATURE for the specified cooling ---
        R_cond = wall_thickness / k_wall
        R_coolant = 1.0 / h_coolant
        R_out = R_cond + R_coolant

        def q_out(Tw):
            return (Tw - ambient_temp) / R_out

        lo, hi = ambient_temp, Taw
        if (gas_side_flux(lo, h_gas) - q_out(lo)) <= 0:
            T_wall = ambient_temp
        elif (gas_side_flux(hi, h_gas) - q_out(hi)) >= 0:
            T_wall = hi
        else:
            for _ in range(200):
                mid = 0.5 * (lo + hi)
                if (gas_side_flux(mid, h_gas) - q_out(mid)) > 0:
                    lo = mid
                else:
                    hi = mid
                if hi - lo < 1e-3:
                    break
            T_wall = 0.5 * (lo + hi)

        # --- Physical clamp / warnings on equilibrium wall temperature ---
        wall_unphysical = False
        mat_name = material_name(mat_props, self.materials)
        if T_wall > max_service:
            wall_unphysical = True
            warnings_list.append(
                f"UNSAFE: equilibrium wall temperature {T_wall:.0f} K exceeds "
                f"{mat_name} service limit {max_service:.0f} K with the specified "
                f"cooling — burn-through likely. Required cooling load "
                f"q={throat_heat_flux/1e6:.1f} MW/m^2 at the throat."
            )
        elif T_wall > allowable:
            warnings_list.append(
                f"WARNING: equilibrium wall temperature {T_wall:.0f} K exceeds "
                f"{mat_name} allowable {allowable:.0f} K — strength margin lost."
            )
        if T_wall > 3500:
            warnings_list.append(
                f"Wall temperature {T_wall:.0f} K is non-physical for any solid "
                f"liner (>3500 K). Regenerative/film cooling or ablative liner required."
            )
        if T_wall >= 0.95 * Taw:
            warnings_list.append(
                "Equilibrium wall temperature pinned near the adiabatic-wall "
                "temperature: modelled cooling is grossly insufficient."
            )

        # The 'heat_flux' key (consumed downstream) is the conservative design
        # load — NEVER the masked near-adiabatic value.
        heat_flux = throat_heat_flux

        # --- Chamber-barrel flux (lower than throat: A_t/A < 1) ---
        throat_area = throat['throat_area']
        surface_area = np.pi * diameter * length + np.pi * (diameter / 2.0) ** 2  # m^2
        chamber_area = np.pi * (diameter / 2.0) ** 2
        area_ratio_chamber = throat_area / chamber_area if chamber_area > 0 else 0.1
        area_ratio_chamber = min(area_ratio_chamber, 1.0)
        h_chamber = self._bartz_coefficient(
            throat['throat_diameter'], pressure, throat['c_star'], gas,
            temperature, Tw_ref, throat['rc_over_dt'],
            area_ratio_local=area_ratio_chamber, mach_local=0.2
        )
        chamber_heat_flux = gas_side_flux(Tw_ref, h_chamber)  # W/m^2 (design load)

        # Total heat rate: chamber flux over barrel area + throat flux over throat.
        total_heat_rate = chamber_heat_flux * surface_area + throat_heat_flux * throat_area  # W

        return {
            'heat_flux': heat_flux,                  # W/m^2 (conservative design load, throat)
            'total_heat_rate': total_heat_rate,      # W
            'surface_area': surface_area,            # m^2
            'throat_heat_flux': throat_heat_flux,    # W/m^2 (real Bartz, not chamber*1.5)
            'chamber_heat_flux': chamber_heat_flux,  # W/m^2 (real Bartz at A_t/A)
            'gas_temperature': temperature,          # K (stagnation/chamber)
            'adiabatic_wall_temperature': Taw,       # K (recovery temperature)
            'reference_wall_temperature': Tw_ref,    # K (cooled wall for design flux)
            'estimated_wall_temperature': T_wall,    # K (equilibrium, given cooling)
            'gas_side_coefficient': h_gas,           # W/m^2/K
            'wall_temperature_unphysical': wall_unphysical,
            'warnings': warnings_list,
        }

    def _analyze_wall_temperature(self, heat_flux: float, thickness: float,
                                mat_props: Dict, ambient_temp: float, h_coolant: float,
                                chamber_temperature: Optional[float] = None,
                                gas_side: Optional[Dict] = None) -> Dict:
        """
        Analyze wall temperature distribution.

        The hot-side (inner) wall temperature is taken from the gas-side energy
        balance when available; the conduction drop across the wall and the
        coolant-side drop are then back-computed consistently from the flux.
        """
        k = mat_props['thermal_conductivity']

        # Thermal resistance analysis [m^2*K/W]
        R_conduction = thickness / k
        R_convection = 1.0 / h_coolant
        R_total = R_conduction + R_convection

        # Temperature drops driven by the (now physical) heat flux.
        delta_T_conduction = heat_flux * R_conduction
        delta_T_convection = heat_flux * R_convection

        if gas_side is not None and 'estimated_wall_temperature' in gas_side:
            # Inner hot-wall from energy balance; outer/coolant temps from flux.
            T_inner = gas_side['estimated_wall_temperature']
            T_outer = T_inner - delta_T_conduction
        else:
            # Backward-compatible resistance-network estimate.
            T_inner = ambient_temp + heat_flux * R_total
            T_outer = ambient_temp + heat_flux * R_convection
        T_average = (T_inner + T_outer) / 2.0

        # Temperature gradient through the wall
        temp_gradient = delta_T_conduction / thickness if thickness > 0 else 0.0

        return {
            'inner_temperature': T_inner,
            'outer_temperature': T_outer,
            'average_temperature': T_average,
            'max_temperature': T_inner,
            'temperature_gradient': temp_gradient,
            'thermal_resistance': {
                'conduction': R_conduction,
                'convection': R_convection,
                'total': R_total
            },
            'temperature_drops': {
                'conduction': delta_T_conduction,
                'convection': delta_T_convection
            }
        }

    def _analyze_cooling_requirements(self, heat_rate: float, burn_time: float,
                                    motor_data: Dict, cooling_type: str) -> Dict:
        """Analyze cooling requirements"""

        # Total heat energy
        total_heat_energy = heat_rate * burn_time  # J

        # Cooling capacity requirements
        if cooling_type == 'natural':
            required_surface_area = heat_rate / (25.0 * 50)  # m² (natural convection)
            coolant_flow_rate = 0  # No active cooling
        elif cooling_type == 'forced':
            required_surface_area = heat_rate / (100.0 * 100)  # m² (forced air)
            coolant_flow_rate = heat_rate / (1000 * 20)  # kg/s (air flow)
        elif cooling_type == 'regenerative':
            coolant_flow_rate = heat_rate / (4180 * 50)  # kg/s (water, 50K rise)
            required_surface_area = heat_rate / (2000.0 * 100)  # m²
        else:
            required_surface_area = 0
            coolant_flow_rate = 0

        # Heat sink analysis (for passive cooling)
        heat_sink_mass = total_heat_energy / (460 * 200)  # kg (steel, 200K rise)

        return {
            'total_heat_energy': total_heat_energy / 1e6,  # MJ
            'peak_heat_rate': heat_rate / 1000,  # kW
            'required_cooling_area': required_surface_area,  # m²
            'coolant_flow_rate': coolant_flow_rate,  # kg/s
            'heat_sink_mass': heat_sink_mass,  # kg
            'cooling_efficiency': self._calculate_cooling_efficiency(cooling_type),
            'recommendations': self._get_cooling_recommendations(cooling_type, heat_rate)
        }

    def _analyze_thermal_safety(self, max_temp: float, mat_props: Dict,
                              thickness: float, pressure: float) -> Dict:
        """Analyze thermal safety margins"""

        allowable_temp = mat_props['allowable_temperature']
        melting_point = mat_props['melting_point']

        # Safety factors (guard against division by zero / negative temps)
        max_temp_safe = max(max_temp, 1.0)
        temp_safety_factor = allowable_temp / max_temp_safe
        melting_safety_factor = melting_point / max_temp_safe

        # Thermal stress (simplified)
        thermal_expansion = 12e-6  # 1/K (typical for steel)
        elastic_modulus = 200e9    # Pa
        thermal_stress = elastic_modulus * thermal_expansion * (max_temp - 293)

        # Allowable stress (simplified)
        yield_strength = 250e6  # Pa (typical for steel)
        stress_safety_factor = yield_strength / thermal_stress if thermal_stress > 0 else 1e6

        # Risk assessment
        risk_level = 'LOW'
        if temp_safety_factor < 1.5:
            risk_level = 'HIGH'
        elif temp_safety_factor < 2.0:
            risk_level = 'MEDIUM'

        warnings_list = []
        if temp_safety_factor < 1.0:
            warnings_list.append('Wall temperature exceeds allowable limit')
        if melting_safety_factor < 2.0:
            warnings_list.append('Wall temperature approaches melting point')
        if stress_safety_factor < 2.0:
            warnings_list.append('High thermal stress - consider thicker walls')

        return {
            'temperature_safety_factor': temp_safety_factor,
            'melting_safety_factor': melting_safety_factor,
            'stress_safety_factor': stress_safety_factor,
            'thermal_stress': thermal_stress / 1e6,  # MPa
            'risk_level': risk_level,
            'warnings': warnings_list,
            'recommendations': self._get_safety_recommendations(temp_safety_factor, thickness)
        }

    def _calculate_cooling_efficiency(self, cooling_type: str) -> float:
        """Calculate cooling system efficiency"""
        efficiencies = {
            'natural': 0.3,
            'forced': 0.6,
            'regenerative': 0.9
        }
        return efficiencies.get(cooling_type, 0.3)

    def _get_cooling_recommendations(self, cooling_type: str, heat_rate: float) -> List[str]:
        """Get cooling system recommendations"""
        recommendations = []

        if heat_rate > 100000:  # > 100 kW
            recommendations.append('High heat load - consider regenerative cooling')
            recommendations.append('Use high thermal conductivity materials')

        if cooling_type == 'natural' and heat_rate > 10000:
            recommendations.append('Natural cooling insufficient - use forced cooling')

        recommendations.append('Consider heat sink or thermal mass for short burns')
        recommendations.append('Monitor wall temperature during operation')

        return recommendations

    def _get_safety_recommendations(self, temp_safety_factor: float, thickness: float) -> List[str]:
        """Get thermal safety recommendations"""
        recommendations = []

        if temp_safety_factor < 1.5:
            recommendations.append('Increase wall thickness')
            recommendations.append('Improve cooling system')
            recommendations.append('Use higher temperature material')

        if thickness < 0.003:
            recommendations.append('Minimum wall thickness should be 3mm')

        recommendations.append('Consider thermal barrier coating')
        recommendations.append('Implement temperature monitoring')

        return recommendations


def material_name(mat_props: Dict, materials_db: Dict) -> str:
    """Reverse-lookup a material name from its property dict (best effort)."""
    for name, props in materials_db.items():
        if props is mat_props:
            return name
    return 'material'
