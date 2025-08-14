"""
Advanced Combustion Analysis Module
NASA CEA-style chemical equilibrium and performance calculations with Cantera integration
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from scipy.optimize import minimize_scalar, fsolve
import cantera as ct

class CombustionAnalyzer:
    """Advanced combustion analysis with chemical equilibrium"""
    
    def __init__(self):
        # Gas constant (NIST 2018 değeri - maksimum hassasiyet)
        self.R_universal = 8314.462618  # J/(kmol·K) - CODATA 2018
        
        # Cantera gaz objesi - NASA-CEA veritabanı kullanarak
        try:
            # Önce NASA-CEA veritabanını dene
            self.gas = ct.Solution('nasa_gas.yaml')
            self.cantera_available = True
        except:
            try:
                # GRI-Mech 3.0 detaylı kimya
                self.gas = ct.Solution('gri30.yaml')
                self.cantera_available = True
            except:
                try:
                    # H2/O2 basit mekanizma
                    self.gas = ct.Solution('h2o2.yaml')
                    self.cantera_available = True
                except:
                    self.cantera_available = False
        
        # N2O/HTPB hibrit roket için özel propellant tanımları
        self.propellant_specs = {
            'n2o': {
                'formula': 'N2O',
                'molecular_weight': 44.013,  # g/mol
                'density_liquid': 1220,  # kg/m³ (at 20°C)
                'enthalpy_formation': 82.05  # kJ/mol
            },
            'htpb': {
                'formula': 'C4H6',  # Simplified HTPB monomer
                'molecular_weight': 54.09,  # g/mol
                'density': 920,  # kg/m³
                'enthalpy_formation': -125.0  # kJ/mol (estimated)
            },
            'paraffin': {
                'formula': 'C12H26',  # Typical paraffin wax
                'molecular_weight': 170.33,  # g/mol
                'density': 900,  # kg/m³
                'enthalpy_formation': -290.0  # kJ/mol
            }
        }
        
        # Standard enthalpies of formation (kJ/mol) at 298K - NIST-JANAF güncel değerleri
        self.species_data = {
            # Major combustion products (NIST 2023 değerleri)
            'CO2': {'Hf': -393.522, 'MW': 44.0095, 'phase': 'gas'},
            'CO': {'Hf': -110.527, 'MW': 28.0101, 'phase': 'gas'},
            'H2O': {'Hf': -241.826, 'MW': 18.01528, 'phase': 'gas'},
            'H2': {'Hf': 0.0, 'MW': 2.01588, 'phase': 'gas'},
            'N2': {'Hf': 0.0, 'MW': 28.0134, 'phase': 'gas'},
            'O2': {'Hf': 0.0, 'MW': 31.9988, 'phase': 'gas'},
            'OH': {'Hf': 39.46, 'MW': 17.01, 'phase': 'gas'},
            'H': {'Hf': 217.97, 'MW': 1.01, 'phase': 'gas'},
            'O': {'Hf': 249.17, 'MW': 16.00, 'phase': 'gas'},
            'NO': {'Hf': 90.25, 'MW': 30.01, 'phase': 'gas'},
            'NO2': {'Hf': 33.18, 'MW': 46.01, 'phase': 'gas'},
            
            # Condensed phases
            'AL2O3_s': {'Hf': -1675.7, 'MW': 101.96, 'phase': 'solid'},
            'AL2O3_l': {'Hf': -1582.0, 'MW': 101.96, 'phase': 'liquid'},
            'C_s': {'Hf': 0.0, 'MW': 12.01, 'phase': 'solid'},
            
            # Fuel components
            'C12H26': {'Hf': -290.0, 'MW': 170.33, 'phase': 'liquid'},  # Paraffin approximation
            'AL': {'Hf': 0.0, 'MW': 26.98, 'phase': 'solid'},
            'HTPB': {'Hf': -125.0, 'MW': 54.0, 'phase': 'solid'},  # Approximation C4H6
        }
    
    def analyze_combustion(self, fuel_composition: Dict, oxidizer_type: str, 
                          of_ratio: float, chamber_pressure: float, 
                          chamber_temperature: float = None) -> Dict:
        """
        Comprehensive combustion analysis
        
        Args:
            fuel_composition: {'formula': percentage} dict
            oxidizer_type: 'N2O', 'LOX', etc.
            of_ratio: Oxidizer/Fuel mass ratio
            chamber_pressure: Chamber pressure in bar
            chamber_temperature: Optional chamber temperature in K
            
        Returns:
            Complete combustion analysis results
        """
        
        # Calculate elemental composition
        elements = self._calculate_elemental_composition(fuel_composition, oxidizer_type, of_ratio)
        
        # Calculate stoichiometric O/F ratio
        of_stoich = self._calculate_stoichiometric_of(fuel_composition, oxidizer_type)
        
        # Calculate chemical equilibrium
        if chamber_temperature is None:
            chamber_temperature = self._estimate_flame_temperature(elements, chamber_pressure)
        
        # Calculate species concentrations at different stations using Cantera
        chamber_composition = self._calculate_equilibrium_composition(
            elements, chamber_pressure, chamber_temperature, 'chamber'
        )
        
        # Cantera'dan gerçek termodinamik değerleri al
        if self.cantera_available and isinstance(chamber_composition, dict) and 'gamma' in chamber_composition:
            chamber_temperature = chamber_composition['temperature']
            gamma_chamber = chamber_composition['gamma']
            molecular_weight = chamber_composition['molecular_weight']
            gas_constant = self.R_universal / molecular_weight  # J/kg·K
        else:
            # Fallback değerler
            gamma_chamber = 1.25
            molecular_weight = 25.0  # Typical for combustion gases
            gas_constant = self.R_universal / molecular_weight
        
        throat_pressure = chamber_pressure / 1.89  # Typical choked flow pressure ratio
        throat_temperature = chamber_temperature * 0.85  # Typical expansion cooling
        throat_composition = self._calculate_equilibrium_composition(
            elements, throat_pressure, throat_temperature, 'throat'
        )
        
        exit_pressure = 1.0  # Sea level
        exit_temperature = self._calculate_exit_temperature(
            chamber_temperature, chamber_pressure, exit_pressure
        )
        exit_composition = self._calculate_equilibrium_composition(
            elements, exit_pressure, exit_temperature, 'exit'
        )
        
        # Calculate performance parameters
        performance = self._calculate_performance_parameters(
            chamber_composition, throat_composition, exit_composition,
            chamber_pressure, throat_pressure, exit_pressure,
            chamber_temperature, throat_temperature, exit_temperature
        )
        
        return {
            'stoichiometric_of': of_stoich,
            'equivalence_ratio': of_stoich / of_ratio,
            'elemental_composition': elements,
            'compositions': {
                'chamber': chamber_composition,
                'throat': throat_composition,
                'exit': exit_composition
            },
            'conditions': {
                'chamber': {'P': chamber_pressure, 'T': chamber_temperature},
                'throat': {'P': throat_pressure, 'T': throat_temperature},
                'exit': {'P': exit_pressure, 'T': exit_temperature}
            },
            'performance': performance
        }
    
    def _calculate_elemental_composition(self, fuel_composition: Dict, 
                                       oxidizer_type: str, of_ratio: float) -> Dict:
        """Calculate elemental mass composition of reactants"""
        
        elements = {'C': 0, 'H': 0, 'O': 0, 'N': 0, 'AL': 0}
        
        total_mass = 1.0 + of_ratio  # Fuel + oxidizer
        fuel_mass_fraction = 1.0 / total_mass
        oxidizer_mass_fraction = of_ratio / total_mass
        
        # Process fuel composition
        for fuel_type, percentage in fuel_composition.items():
            fuel_fraction = (percentage / 100.0) * fuel_mass_fraction
            
            if fuel_type == 'paraffin':
                # C12H26 approximation
                elements['C'] += fuel_fraction * 12 * 12.01 / 170.33
                elements['H'] += fuel_fraction * 26 * 1.01 / 170.33
            elif fuel_type == 'htpb':
                # C4H6 approximation
                elements['C'] += fuel_fraction * 4 * 12.01 / 54.0
                elements['H'] += fuel_fraction * 6 * 1.01 / 54.0
            elif fuel_type == 'aluminum':
                elements['AL'] += fuel_fraction * 26.98 / 26.98
            elif fuel_type == 'abs':
                # ABS approximated as C8H8 (simplified)
                elements['C'] += fuel_fraction * 8 * 12.01 / 104.15
                elements['H'] += fuel_fraction * 8 * 1.01 / 104.15
            elif fuel_type == 'pla':
                # PLA approximated as C3H4O2
                elements['C'] += fuel_fraction * 3 * 12.01 / 72.06
                elements['H'] += fuel_fraction * 4 * 1.01 / 72.06
                elements['O'] += fuel_fraction * 2 * 16.00 / 72.06
            elif fuel_type == 'pe':
                # Polyethylene C2H4
                elements['C'] += fuel_fraction * 2 * 12.01 / 28.05
                elements['H'] += fuel_fraction * 4 * 1.01 / 28.05
            elif fuel_type == 'pmma':
                # PMMA approximated as C5H8O2
                elements['C'] += fuel_fraction * 5 * 12.01 / 100.12
                elements['H'] += fuel_fraction * 8 * 1.01 / 100.12
                elements['O'] += fuel_fraction * 2 * 16.00 / 100.12
        
        # Process oxidizer
        if oxidizer_type.lower() == 'n2o':
            # N2O
            elements['N'] += oxidizer_mass_fraction * 2 * 14.01 / 44.01
            elements['O'] += oxidizer_mass_fraction * 16.00 / 44.01
        elif oxidizer_type.lower() == 'lox':
            # O2
            elements['O'] += oxidizer_mass_fraction * 2 * 16.00 / 32.00
        elif oxidizer_type.lower() == 'h2o2':
            # H2O2
            elements['H'] += oxidizer_mass_fraction * 2 * 1.01 / 34.01
            elements['O'] += oxidizer_mass_fraction * 2 * 16.00 / 34.01
        elif oxidizer_type.lower() == 'air':
            # Air (simplified as 21% O2, 79% N2)
            elements['O'] += oxidizer_mass_fraction * 0.21 * 2 * 16.00 / 32.00
            elements['N'] += oxidizer_mass_fraction * 0.79 * 2 * 14.01 / 28.01
        
        return elements
    
    def _calculate_stoichiometric_of(self, fuel_composition: Dict, oxidizer_type: str) -> float:
        """Calculate stoichiometric O/F ratio"""
        
        # Calculate oxygen requirement for complete combustion
        oxygen_required = 0  # kg O2 per kg fuel
        
        for fuel_type, percentage in fuel_composition.items():
            fuel_fraction = percentage / 100.0
            
            if fuel_type == 'paraffin':
                # C12H26 + 18.5 O2 → 12 CO2 + 13 H2O
                # MW_fuel = 170.33, MW_O2 = 32.0
                oxygen_required += fuel_fraction * (18.5 * 32.0) / 170.33
            elif fuel_type == 'htpb':
                # C4H6 + 5.5 O2 → 4 CO2 + 3 H2O
                # MW_fuel = 54.0, MW_O2 = 32.0
                oxygen_required += fuel_fraction * (5.5 * 32.0) / 54.0
            elif fuel_type == 'aluminum':
                # 4 Al + 3 O2 → 2 Al2O3
                # MW_Al = 26.98, MW_O2 = 32.0
                oxygen_required += fuel_fraction * (3 * 32.0) / (4 * 26.98)
            elif fuel_type == 'abs':
                # C8H8 + 10 O2 → 8 CO2 + 4 H2O
                oxygen_required += fuel_fraction * (10 * 32.0) / 104.15
            elif fuel_type == 'pla':
                # C3H4O2 + 3 O2 → 3 CO2 + 2 H2O
                oxygen_required += fuel_fraction * (3 * 32.0) / 72.06
            elif fuel_type == 'pe':
                # C2H4 + 3 O2 → 2 CO2 + 2 H2O
                oxygen_required += fuel_fraction * (3 * 32.0) / 28.05
            elif fuel_type == 'pmma':
                # C5H8O2 + 6 O2 → 5 CO2 + 4 H2O
                oxygen_required += fuel_fraction * (6 * 32.0) / 100.12
        
        # Convert to oxidizer mass
        if oxidizer_type.lower() == 'n2o':
            # N2O contains 36.36% oxygen by mass
            oxidizer_required = oxygen_required / 0.3636
        elif oxidizer_type.lower() == 'lox':
            # Pure oxygen
            oxidizer_required = oxygen_required
        elif oxidizer_type.lower() == 'h2o2':
            # H2O2 contains 94.12% oxygen by mass
            oxidizer_required = oxygen_required / 0.9412
        elif oxidizer_type.lower() == 'air':
            # Air contains 23.14% oxygen by mass
            oxidizer_required = oxygen_required / 0.2314
        else:
            oxidizer_required = oxygen_required  # Default assumption
        
        return oxidizer_required
    
    def _estimate_flame_temperature(self, elements: Dict, pressure: float) -> float:
        """Calculate adiabatic flame temperature using Cantera"""
        if not self.cantera_available:
            # Fallback basit model
            base_temp = 3200  # K
            if elements['AL'] > 0.1:
                base_temp += 500
            if elements['H'] > 0.1:
                base_temp += 200
            return base_temp * (1.0 + 0.05 * np.log(pressure))
        
        try:
            # Cantera ile adiabatic flame temperature hesaplama
            self.gas.TPX = 298.15, pressure * 1e5, self._elements_to_cantera_composition(elements)
            self.gas.equilibrate('HP')  # Adiabatic (constant enthalpy and pressure)
            return self.gas.T
        except:
            # Hata durumunda fallback
            return 3000.0  # Realistic default for hybrid rockets
    
    def _elements_to_cantera_composition(self, elements: Dict) -> str:
        """Convert elemental composition to Cantera format"""
        # Cantera composition string formatında döndür
        comp_parts = []
        for element, moles in elements.items():
            if moles > 1e-10:  # Çok küçük değerleri filtrele
                comp_parts.append(f"{element}:{moles:.6f}")
        return ",".join(comp_parts)
    
    def _calculate_equilibrium_composition(self, elements: Dict, pressure: float, 
                                         temperature: float, station: str) -> Dict:
        """Calculate chemical equilibrium composition using Cantera"""
        
        if not self.cantera_available:
            # Fallback basit model
            return self._fallback_equilibrium_composition(elements, pressure, temperature, station)
        
        try:
            # Cantera ile kimyasal denge hesaplama
            comp_str = self._elements_to_cantera_composition(elements)
            self.gas.TPX = temperature, pressure * 1e5, comp_str
            self.gas.equilibrate('TP')  # Constant temperature and pressure
            
            # Sonuçları çıkar
            composition = {}
            species_names = self.gas.species_names
            mole_fractions = self.gas.X
            mass_fractions = self.gas.Y
            
            for i, species in enumerate(species_names):
                if mole_fractions[i] > 1e-10:  # Sadece anlamlı miktarları dahil et
                    composition[species] = {
                        'mole_fraction': mole_fractions[i],
                        'mass_fraction': mass_fractions[i]
                    }
            
            return {
                'species': composition,
                'temperature': self.gas.T,
                'pressure': self.gas.P / 1e5,  # bar cinsinden
                'density': self.gas.density,
                'molecular_weight': self.gas.mean_molecular_weight,
                'cp': self.gas.cp,
                'cv': self.gas.cv,
                'gamma': self.gas.cp / self.gas.cv,
                'enthalpy': self.gas.enthalpy_mass,
                'entropy': self.gas.entropy_mass
            }
            
        except Exception as e:
            # Hata durumunda fallback
            return self._fallback_equilibrium_composition(elements, pressure, temperature, station)
    
    def _fallback_equilibrium_composition(self, elements: Dict, pressure: float, 
                                        temperature: float, station: str) -> Dict:
        """Fallback equilibrium model for when Cantera is not available"""
        composition = {}
        
        if station == 'chamber':
            # High temperature, major species
            composition = {
                'CO2': 0.22,
                'CO': 0.08,
                'H2O': 0.12,
                'H2': 0.02,
                'N2': 0.54,
                'OH': 0.015,
                'H': 0.001,
                'O': 0.001,
                'NO': 0.002,
                'AL2O3_l': elements.get('AL', 0) * 0.5  # Liquid alumina
            }
        elif station == 'throat':
            # Partially frozen composition
            composition = {
                'CO2': 0.24,
                'CO': 0.06,
                'H2O': 0.13,
                'H2': 0.015,
                'N2': 0.545,
                'OH': 0.008,
                'H': 0.0005,
                'O': 0.0005,
                'NO': 0.001,
                'AL2O3_s': elements.get('AL', 0) * 0.5  # Solidified alumina
            }
        else:  # exit
            # Frozen composition, condensed species
            composition = {
                'CO2': 0.26,
                'CO': 0.04,
                'H2O': 0.14,
                'H2': 0.01,
                'N2': 0.55,
                'OH': 0.001,
                'H': 0.0001,
                'O': 0.0001,
                'NO': 0.0001,
                'AL2O3_s': elements.get('AL', 0) * 0.5
            }
        
        # Normalize to ensure sum = 1
        total = sum(composition.values())
        if total > 0:
            composition = {species: frac/total for species, frac in composition.items()}
        
        return composition
    
    def _calculate_exit_temperature(self, T_chamber: float, P_chamber: float, P_exit: float) -> float:
        """Calculate exit temperature using isentropic expansion"""
        gamma = 1.25  # Average specific heat ratio
        pressure_ratio = P_chamber / P_exit
        return T_chamber / (pressure_ratio ** ((gamma - 1) / gamma))
    
    def _calculate_performance_parameters(self, chamber_comp: Dict, throat_comp: Dict, 
                                        exit_comp: Dict, P_c: float, P_t: float, P_e: float,
                                        T_c: float, T_t: float, T_e: float) -> Dict:
        """Calculate performance parameters"""
        
        # Calculate average molecular weight (Cantera uyumlu)
        def calc_mw(composition):
            if isinstance(composition, dict):
                # Cantera formatı kontrolü
                if 'molecular_weight' in composition:
                    return composition['molecular_weight']
                elif 'species' in composition:
                    # Species bazlı hesaplama
                    mw = 0
                    for species, data in composition['species'].items():
                        if isinstance(data, dict) and 'mass_fraction' in data:
                            if species in self.species_data:
                                mw += data['mass_fraction'] * self.species_data[species]['MW']
                    return max(mw, 25.0)  # Minimum MW
                else:
                    # Eski format
                    mw = 0
                    for species, fraction in composition.items():
                        if species in self.species_data:
                            mw += fraction * self.species_data[species]['MW']
                    return max(mw, 25.0)  # Minimum MW
            return 25.0  # Default MW
        
        MW_c = calc_mw(chamber_comp)
        MW_t = calc_mw(throat_comp)
        MW_e = calc_mw(exit_comp)
        
        # Gas constants (güvenli bölme)
        R_c = self.R_universal / max(MW_c, 10.0)  # Minimum MW limit
        R_t = self.R_universal / max(MW_t, 10.0)
        R_e = self.R_universal / max(MW_e, 10.0)
        
        # Thermodynamic properties
        thermo_props = self._calculate_thermodynamic_properties(
            chamber_comp, throat_comp, exit_comp, T_c, T_t, T_e, P_c, P_t, P_e
        )
        
        # Characteristic velocity - use chamber gamma from thermodynamic properties
        # Access gamma from 'stations' -> 'chamber'
        gamma = thermo_props['stations']['chamber']['gamma']
        c_star = np.sqrt(R_c * T_c / gamma) / ((2/(gamma+1))**((gamma+1)/(2*(gamma-1))))
        
        # Throat velocity (choked)
        v_throat = np.sqrt(gamma * R_t * T_t)
        
        # Exit velocity
        v_exit = np.sqrt(2 * gamma * R_e * T_e / (gamma - 1) * (1 - (P_e/P_c)**((gamma-1)/gamma)))
        
        # Specific impulse
        g0 = 9.81
        isp = v_exit / g0
        
        # Thrust coefficient
        cf = v_exit / c_star
        
        return {
            'molecular_weights': {'chamber': MW_c, 'throat': MW_t, 'exit': MW_e},
            'gas_constants': {'chamber': R_c, 'throat': R_t, 'exit': R_e},
            'velocities': {'throat': v_throat, 'exit': v_exit},
            'c_star': c_star,
            'cf': cf,
            'isp': isp,
            'gamma_avg': gamma,
            'thermodynamic_properties': thermo_props
        }
    
    def find_optimum_of_ratio(self, fuel_composition: Dict, oxidizer_type: str, 
                             chamber_pressure: float, of_range: Tuple[float, float] = (1.0, 10.0)) -> Dict:
        """Find O/F ratio for maximum specific impulse"""
        
        def negative_isp(of_ratio):
            try:
                results = self.analyze_combustion(fuel_composition, oxidizer_type, of_ratio, chamber_pressure)
                return -results['performance']['isp']  # Negative because we minimize
            except:
                return 1000  # Large penalty for failed calculations
        
        # Optimize
        result = minimize_scalar(negative_isp, bounds=of_range, method='bounded')
        
        optimum_of = result.x
        max_isp = -result.fun
        
        # Get full analysis at optimum
        optimum_analysis = self.analyze_combustion(fuel_composition, oxidizer_type, optimum_of, chamber_pressure)
        
        return {
            'optimum_of_ratio': optimum_of,
            'maximum_isp': max_isp,
            'analysis': optimum_analysis
        }
    
    def calculate_altitude_performance(self, motor_data: Dict, altitudes: List[float]) -> Dict:
        """Calculate performance at different altitudes"""
        
        performance_data = []
        
        for altitude in altitudes:
            # Standard atmosphere
            if altitude < 11000:
                T = 288.15 - 0.0065 * altitude
                P = 1.01325 * (T / 288.15)**(9.80665 * 0.0289644 / (8.31432 * 0.0065))
            else:
                T = 216.65
                P = 0.22632 * np.exp(-9.80665 * 0.0289644 * (altitude - 11000) / (8.31432 * T))
            
            # Adjust performance for altitude
            gamma = motor_data.get('gamma_avg', 1.25)
            P_c = motor_data['chamber_pressure']
            
            # Exit velocity at this altitude
            pressure_ratio = P_c / P
            if pressure_ratio > 1:
                v_exit = np.sqrt(2 * gamma * motor_data['gas_constants']['chamber'] * 
                               motor_data['conditions']['chamber']['T'] / (gamma - 1) * 
                               (1 - (P / P_c)**((gamma - 1) / gamma)))
                
                cf = v_exit / motor_data['performance']['c_star']
                isp = v_exit / 9.81
                thrust = motor_data.get('mdot_total', 1.0) * v_exit
            else:
                # Under-expanded
                v_exit = motor_data['performance']['velocities']['exit']
                cf = motor_data['performance']['cf']
                isp = motor_data['performance']['isp']
                thrust = motor_data.get('mdot_total', 1.0) * v_exit
            
            performance_data.append({
                'altitude': altitude,
                'pressure': P,
                'temperature': T,
                'exit_velocity': v_exit,
                'cf': cf,
                'isp': isp,
                'thrust': thrust
            })
        
        return {
            'altitude_performance': performance_data,
            'sea_level_isp': performance_data[0]['isp'] if performance_data else 0,
            'vacuum_isp': max([p['isp'] for p in performance_data]) if performance_data else 0
        }
    
    def _calculate_thermodynamic_properties(self, chamber_comp: Dict, throat_comp: Dict, 
                                          exit_comp: Dict, T_c: float, T_t: float, T_e: float,
                                          P_c: float, P_t: float, P_e: float) -> Dict:
        """Calculate detailed thermodynamic properties"""
        
        # Standard enthalpies and entropies (simplified NASA polynomials)
        def calc_enthalpy(composition: Dict, temperature: float) -> float:
            """Calculate mixture enthalpy in kJ/kg"""
            h_mix = 0
            total_mass_frac = 0
            
            for species, mass_frac in composition.items():
                if species in self.species_data and mass_frac > 0:
                    # Simplified enthalpy calculation using temperature dependence
                    h_f = self.species_data[species]['Hf']  # Formation enthalpy at 298K
                    
                    # Temperature correction (simplified)
                    if species in ['CO2', 'H2O', 'N2']:
                        cp = 1.0  # kJ/kg·K (simplified)
                    elif species in ['CO', 'H2']:
                        cp = 1.4
                    else:
                        cp = 1.2
                    
                    # Enthalpy = formation + sensible
                    h_species = h_f + cp * (temperature - 298.15)
                    h_mix += mass_frac * h_species / self.species_data[species]['MW'] * 1000
                    total_mass_frac += mass_frac
            
            return h_mix / max(total_mass_frac, 0.001)  # kJ/kg
        
        def calc_entropy(composition: Dict, temperature: float, pressure: float) -> float:
            """Calculate mixture entropy in kJ/kg·K"""
            s_mix = 0
            total_mass_frac = 0
            
            for species, mass_frac in composition.items():
                if species in self.species_data and mass_frac > 0:
                    # Standard entropy at 298K and 1 bar (simplified values)
                    s0_values = {
                        'CO2': 0.214, 'CO': 0.198, 'H2O': 0.189, 'H2': 0.131,
                        'N2': 0.192, 'O2': 0.205, 'OH': 0.184, 'NO': 0.211
                    }
                    
                    s0 = s0_values.get(species, 0.2)  # kJ/kg·K
                    
                    # Temperature and pressure corrections
                    cp = 1.2  # Simplified
                    s_species = s0 + cp * np.log(temperature / 298.15) - \
                               self.R_universal / self.species_data[species]['MW'] * np.log(pressure)
                    
                    s_mix += mass_frac * s_species
                    total_mass_frac += mass_frac
            
            return s_mix / max(total_mass_frac, 0.001)
        
        def calc_gibbs_energy(enthalpy: float, entropy: float, temperature: float) -> float:
            """Calculate Gibbs free energy"""
            return enthalpy - temperature * entropy
        
        # Calculate properties for each station
        properties = {}
        
        stations = [
            ('chamber', chamber_comp, T_c, P_c),
            ('throat', throat_comp, T_t, P_t),
            ('exit', exit_comp, T_e, P_e)
        ]
        
        for station_name, comp, T, P in stations:
            h = calc_enthalpy(comp, T)
            s = calc_entropy(comp, T, P)
            g = calc_gibbs_energy(h, s, T)
            
            # Specific heat capacity (simplified, unit-consistent)
            # Use cp, cv in J/kg·K for internal calculations, then store in kJ/kg·K
            cp_j = 1200.0  # J/kg·K (equivalent to 1.2 kJ/kg·K)
            cv_j = cp_j - self.R_universal / 30.0  # J/kg·K
            # Guard against non-physical negative cv
            cv_j = max(cv_j, 1e-3)
            gamma_local = cp_j / cv_j
            
            # Speed of sound (güvenli sqrt)
            R_mix = self.R_universal / 30.0  # J/kg·K - approximate mixture gas constant
            T_safe = max(T, 300)  # Minimum 300K sıcaklık sınırı
            a = np.sqrt(gamma_local * R_mix * T_safe)
            
            # Density (from ideal gas law)
            rho = P * 1e5 / (R_mix * T)  # kg/m³
            
            properties[station_name] = {
                'enthalpy': h,  # kJ/kg
                'entropy': s,   # kJ/kg·K
                'gibbs_energy': g,  # kJ/kg
                'cp': cp_j / 1000.0,       # kJ/kg·K
                'cv': cv_j / 1000.0,       # kJ/kg·K
                'gamma': gamma_local,
                'speed_of_sound': a,  # m/s
                'density': rho,       # kg/m³
                'temperature': T,     # K
                'pressure': P         # bar
            }
        
        # Calculate property changes
        delta_h = properties['exit']['enthalpy'] - properties['chamber']['enthalpy']
        delta_s = properties['exit']['entropy'] - properties['chamber']['entropy']
        
        return {
            'stations': properties,
            'deltas': {
                'enthalpy_change': delta_h,      # kJ/kg
                'entropy_change': delta_s,       # kJ/kg·K
                'pressure_ratio': P_c / P_e,
                'temperature_ratio': T_c / T_e
            },
            'isentropic_efficiency': self._calculate_isentropic_efficiency(properties),
            'flow_properties': {
                'mass_averaged_gamma': sum(p['gamma'] for p in properties.values()) / 3,
                'mass_averaged_cp': sum(p['cp'] for p in properties.values()) / 3,
                'mass_averaged_mw': sum(30.0 for _ in properties.values()) / 3  # Simplified
            }
        }
    
    def _calculate_isentropic_efficiency(self, properties: Dict) -> float:
        """Calculate nozzle isentropic efficiency"""
        
        # Actual enthalpy drop
        h_actual = properties['chamber']['enthalpy'] - properties['exit']['enthalpy']
        
        # Isentropic enthalpy drop (simplified calculation)
        T_c = properties['chamber']['temperature']
        T_e_isentropic = T_c * (properties['exit']['pressure'] / properties['chamber']['pressure'])**0.286
        
        # Simplified isentropic enthalpy
        cp_avg = properties['chamber']['cp']
        h_isentropic = cp_avg * (T_c - T_e_isentropic)
        
        # Efficiency
        eta_s = h_actual / max(h_isentropic, 0.001)
        
        return min(1.0, max(0.8, eta_s))  # Clamp between 80% and 100%
    
    def calculate_thrust_at_altitudes(self, total_impulse: float, motor_data: Dict, 
                                    altitudes: List[float]) -> Dict:
        """Calculate thrust at different altitudes from total impulse"""
        
        thrust_data = []
        
        # Base performance at sea level
        base_isp = motor_data['performance']['isp']
        base_thrust = total_impulse / motor_data.get('burn_time', 10)  # Default 10s burn
        base_mdot = base_thrust / (base_isp * 9.81)
        
        for altitude in altitudes:
            # Standard atmosphere
            if altitude < 11000:
                T = 288.15 - 0.0065 * altitude
                P = 1.01325 * (T / 288.15)**(9.80665 * 0.0289644 / (8.31432 * 0.0065))
            else:
                T = 216.65
                P = 0.22632 * np.exp(-9.80665 * 0.0289644 * (altitude - 11000) / (8.31432 * T))
            
            # Adjust performance for altitude
            gamma = motor_data['performance'].get('gamma_avg', 1.25)
            P_c = motor_data.get('chamber_pressure', 20.0)  # bar
            R = motor_data['performance']['gas_constants']['chamber']
            T_c = motor_data['conditions']['chamber']['T']
            
            # Exit velocity at this altitude
            pressure_ratio = P_c / P
            if pressure_ratio > 1:
                v_exit = np.sqrt(2 * gamma * R * T_c / (gamma - 1) * 
                               (1 - (P / P_c)**((gamma - 1) / gamma)))
                
                # Specific impulse at altitude
                isp_alt = v_exit / 9.81
                
                # Thrust at altitude (constant mass flow rate)
                thrust_alt = base_mdot * v_exit
                
                # Effective total impulse available at this altitude
                effective_total_impulse = thrust_alt * motor_data.get('burn_time', 10)
                
            else:
                # Under-expanded (shouldn't happen at reasonable altitudes)
                v_exit = motor_data['performance']['velocities']['exit']
                isp_alt = motor_data['performance']['isp']
                thrust_alt = base_thrust
                effective_total_impulse = total_impulse
            
            thrust_data.append({
                'altitude': altitude,
                'pressure': P,
                'temperature': T,
                'thrust': thrust_alt,
                'isp': isp_alt,
                'exit_velocity': v_exit,
                'effective_total_impulse': effective_total_impulse,
                'impulse_efficiency': effective_total_impulse / total_impulse
            })
        
        return {
            'thrust_altitude_data': thrust_data,
            'input_total_impulse': total_impulse,
            'base_thrust_sea_level': base_thrust,
            'max_thrust': max([p['thrust'] for p in thrust_data]),
            'max_thrust_altitude': thrust_data[np.argmax([p['thrust'] for p in thrust_data])]['altitude'],
            'vacuum_thrust': thrust_data[-1]['thrust'] if thrust_data else 0
        }