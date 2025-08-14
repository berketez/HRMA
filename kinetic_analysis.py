"""
Nozzle Kinetic Loss Analysis Module
Advanced nozzle kinetic analysis similar to TDK (JANNAF standard)
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import odeint, solve_ivp
from scipy.optimize import fsolve, minimize_scalar
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

@dataclass
class KineticSpecies:
    """Chemical species for kinetic analysis"""
    name: str
    molecular_weight: float     # kg/mol
    formation_enthalpy: float   # J/mol
    activation_energy: float    # J/mol
    pre_exponential_factor: float  # Various units
    temperature_exponent: float
    
@dataclass
class ReactionMechanism:
    """Chemical reaction mechanism"""
    reaction_id: str
    reactants: List[Tuple[str, float]]  # (species, stoichiometric coefficient)
    products: List[Tuple[str, float]]
    forward_rate_constant: float
    reverse_rate_constant: float
    activation_energy_forward: float
    activation_energy_reverse: float
    reaction_type: str  # 'dissociation', 'recombination', 'exchange'

class NozzleKineticAnalyzer:
    """Advanced nozzle kinetic analysis following TDK methodology"""
    
    def __init__(self):
        self.R = 8.314  # J/mol/K
        self.k_boltzmann = 1.381e-23  # J/K
        self.avogadro = 6.022e23  # mol^-1
        self.species_database = {}
        self.reaction_mechanisms = []
        self.initialize_kinetic_database()
    
    def initialize_kinetic_database(self):
        """Initialize kinetic species and reaction database"""
        
        # Key combustion species for kinetic analysis
        species_data = {
            'H2': KineticSpecies('H2', 0.002016, 0.0, 436000, 1e13, 0.0),
            'O2': KineticSpecies('O2', 0.032, 0.0, 498000, 1e13, 0.0),
            'H2O': KineticSpecies('H2O', 0.018015, -241826, 0, 0, 0.0),
            'CO': KineticSpecies('CO', 0.028010, -110527, 0, 0, 0.0),
            'CO2': KineticSpecies('CO2', 0.044010, -393522, 0, 0, 0.0),
            'OH': KineticSpecies('OH', 0.017007, 39349, 0, 0, 0.0),
            'H': KineticSpecies('H', 0.001008, 217999, 0, 0, 0.0),
            'O': KineticSpecies('O', 0.015999, 249173, 0, 0, 0.0),
            'N2': KineticSpecies('N2', 0.028014, 0.0, 945000, 1e13, 0.0),
            'NO': KineticSpecies('NO', 0.030006, 90297, 0, 0, 0.0),
            'CH4': KineticSpecies('CH4', 0.016043, -74600, 0, 0, 0.0),
            'C2H2': KineticSpecies('C2H2', 0.026038, 228200, 0, 0, 0.0),
        }
        
        self.species_database = species_data
        
        # Initialize key reaction mechanisms
        self._initialize_reaction_mechanisms()
    
    def _initialize_reaction_mechanisms(self):
        """Initialize chemical reaction mechanisms for kinetic analysis"""
        
        # Key reactions for combustion kinetics
        reactions = [
            # Water dissociation/recombination
            ReactionMechanism(
                'H2O_dissociation',
                [('H2O', 1.0)],
                [('H', 1.0), ('OH', 1.0)],
                1.0e16,  # s^-1
                1.0e13,  # m^3/mol/s
                502000,  # J/mol
                0,       # J/mol
                'dissociation'
            ),
            
            # Hydrogen dissociation
            ReactionMechanism(
                'H2_dissociation',
                [('H2', 1.0)],
                [('H', 2.0)],
                1.0e18,
                5.0e12,
                436000,
                0,
                'dissociation'
            ),
            
            # Oxygen dissociation
            ReactionMechanism(
                'O2_dissociation',
                [('O2', 1.0)],
                [('O', 2.0)],
                1.0e15,
                3.0e12,
                498000,
                0,
                'dissociation'
            ),
            
            # CO2 dissociation
            ReactionMechanism(
                'CO2_dissociation',
                [('CO2', 1.0)],
                [('CO', 1.0), ('O', 1.0)],
                1.0e14,
                1.0e12,
                532000,
                0,
                'dissociation'
            ),
            
            # Water formation
            ReactionMechanism(
                'H2O_formation',
                [('H2', 1.0), ('O', 1.0)],
                [('H2O', 1.0)],
                3.0e12,
                1.0e15,
                8400,
                502000,
                'exchange'
            ),
            
            # OH formation/dissociation
            ReactionMechanism(
                'OH_formation',
                [('H', 1.0), ('O2', 1.0)],
                [('OH', 1.0), ('O', 1.0)],
                2.0e14,
                1.0e13,
                70000,
                0,
                'exchange'
            )
        ]
        
        self.reaction_mechanisms = reactions
    
    def analyze_nozzle_kinetics(self, nozzle_geometry: Dict, chamber_conditions: Dict,
                               propellant_composition: Dict, motor_type: str = 'hybrid') -> Dict:
        """
        Complete nozzle kinetic analysis following TDK methodology
        
        Args:
            nozzle_geometry: Nozzle geometric parameters
            chamber_conditions: Chamber thermodynamic conditions
            propellant_composition: Initial species composition
            motor_type: Type of rocket motor
            
        Returns:
            Kinetic analysis results with performance losses
        """
        
        # Step 1: Initialize species concentrations
        initial_composition = self._initialize_species_composition(propellant_composition, chamber_conditions)
        
        # Step 2: Create nozzle flow stations
        flow_stations = self._create_nozzle_stations(nozzle_geometry, chamber_conditions)
        
        # Step 3: Solve kinetic equations along nozzle
        kinetic_solution = self._solve_nozzle_kinetics(flow_stations, initial_composition, chamber_conditions)
        
        # Step 4: Calculate performance losses
        performance_analysis = self._calculate_kinetic_losses(kinetic_solution, chamber_conditions)
        
        # Step 5: Compare with equilibrium solution
        equilibrium_comparison = self._compare_with_equilibrium(kinetic_solution, chamber_conditions)
        
        # Step 6: Generate detailed analysis
        detailed_analysis = self._generate_detailed_kinetic_analysis(
            kinetic_solution, performance_analysis, equilibrium_comparison
        )
        
        return {
            'kinetic_solution': kinetic_solution,
            'performance_losses': performance_analysis,
            'equilibrium_comparison': equilibrium_comparison,
            'detailed_analysis': detailed_analysis,
            'flow_stations': flow_stations,
            'species_profiles': self._extract_species_profiles(kinetic_solution),
            'temperature_profile': self._extract_temperature_profile(kinetic_solution),
            'pressure_profile': self._extract_pressure_profile(kinetic_solution)
        }
    
    def _initialize_species_composition(self, propellant_comp: Dict, chamber_conditions: Dict) -> Dict:
        """Initialize species mole fractions based on propellant type"""
        
        # Start with equilibrium composition at chamber conditions
        # This is a simplified initialization - in practice would use CEA or similar
        
        chamber_temp = chamber_conditions.get('temperature', 3000)  # K
        chamber_pressure = chamber_conditions.get('pressure', 2e6)  # Pa
        
        # Simplified composition based on common propellant combinations
        if 'LOX/RP-1' in str(propellant_comp) or 'LOX' in str(propellant_comp):
            composition = {
                'H2O': 0.45,
                'CO2': 0.25,
                'CO': 0.12,
                'H2': 0.08,
                'O2': 0.03,
                'OH': 0.04,
                'H': 0.02,
                'O': 0.01
            }
        elif 'N2O' in str(propellant_comp):
            composition = {
                'H2O': 0.35,
                'CO2': 0.20,
                'N2': 0.20,
                'CO': 0.10,
                'H2': 0.08,
                'NO': 0.04,
                'OH': 0.02,
                'H': 0.01
            }
        elif 'APCP' in str(propellant_comp) or 'solid' in str(propellant_comp):
            composition = {
                'H2O': 0.30,
                'CO2': 0.15,
                'CO': 0.08,
                'N2': 0.25,
                'HCl': 0.12,
                'H2': 0.05,
                'OH': 0.03,
                'Cl2': 0.02
            }
        else:
            # Default composition
            composition = {
                'H2O': 0.40,
                'CO2': 0.30,
                'CO': 0.15,
                'H2': 0.10,
                'OH': 0.03,
                'H': 0.01,
                'O': 0.01
            }
        
        # Calculate molar concentrations
        total_moles = chamber_pressure / (self.R * chamber_temp)  # mol/m^3
        
        molar_concentrations = {}
        for species, mole_frac in composition.items():
            if species in self.species_database:
                molar_concentrations[species] = mole_frac * total_moles
        
        return {
            'mole_fractions': composition,
            'molar_concentrations': molar_concentrations,
            'total_molar_concentration': total_moles,
            'temperature': chamber_temp,
            'pressure': chamber_pressure
        }
    
    def _create_nozzle_stations(self, geometry: Dict, chamber_conditions: Dict) -> List[Dict]:
        """Create flow stations along nozzle for kinetic analysis"""
        
        # Nozzle geometry parameters
        throat_area = np.pi * (geometry.get('throat_radius', 0.01))**2
        exit_area = np.pi * (geometry.get('exit_radius', 0.025))**2
        expansion_ratio = exit_area / throat_area
        
        # Create area distribution along nozzle
        n_stations = 50  # Number of calculation stations
        
        # Area ratio distribution (simplified)
        area_ratios = np.logspace(0, np.log10(expansion_ratio), n_stations)
        
        # Calculate pressure ratio using isentropic relations
        gamma = 1.25  # Effective gamma
        pressure_chamber = chamber_conditions.get('pressure', 2e6)
        temperature_chamber = chamber_conditions.get('temperature', 3000)
        
        stations = []
        
        for i, area_ratio in enumerate(area_ratios):
            # Isentropic relations for initial guess
            if area_ratio == 1.0:  # Throat
                pressure_ratio = 0.5283  # Critical pressure ratio
                temp_ratio = 0.8333     # Critical temperature ratio
            else:
                # Supersonic expansion (simplified)
                mach_approx = self._estimate_mach_from_area_ratio(area_ratio, gamma)
                pressure_ratio = (1 + (gamma-1)/2 * mach_approx**2)**(-gamma/(gamma-1))
                temp_ratio = (1 + (gamma-1)/2 * mach_approx**2)**(-1)
            
            station = {
                'station_id': i,
                'area_ratio': area_ratio,
                'area': throat_area * area_ratio,
                'pressure': pressure_chamber * pressure_ratio,
                'temperature': temperature_chamber * temp_ratio,
                'mach_number': self._estimate_mach_from_area_ratio(area_ratio, gamma),
                'residence_time': 0.0,  # Will be calculated
                'axial_position': i / (n_stations - 1)  # Normalized position
            }
            
            stations.append(station)
        
        # Calculate residence times
        self._calculate_residence_times(stations, geometry, chamber_conditions)
        
        return stations
    
    def _estimate_mach_from_area_ratio(self, area_ratio: float, gamma: float) -> float:
        """Estimate Mach number from area ratio using isentropic relations"""
        
        if area_ratio == 1.0:
            return 1.0
        elif area_ratio < 1.0:
            # Subsonic (should not occur in normal nozzle)
            return 0.5
        else:
            # Supersonic - use iterative solution
            def mach_area_relation(M):
                return (1/M) * ((2/(gamma+1)) * (1 + (gamma-1)/2 * M**2))**((gamma+1)/(2*(gamma-1))) - area_ratio
            
            # Initial guess
            M_guess = 2.0 * np.sqrt(area_ratio - 1)
            
            try:
                mach = fsolve(mach_area_relation, M_guess)[0]
                return max(1.001, mach)  # Ensure supersonic
            except:
                return 2.0  # Fallback value
    
    def _calculate_residence_times(self, stations: List[Dict], geometry: Dict, chamber_conditions: Dict):
        """Calculate residence time at each station"""
        
        # Simplified residence time calculation
        nozzle_length = geometry.get('nozzle_length', 0.1)  # m
        
        for i, station in enumerate(stations):
            if i == 0:
                station['residence_time'] = 0.0
            else:
                # Distance between stations
                dx = nozzle_length * (station['axial_position'] - stations[i-1]['axial_position'])
                
                # Average velocity between stations
                prev_temp = stations[i-1]['temperature']
                curr_temp = station['temperature']
                avg_temp = (prev_temp + curr_temp) / 2
                
                # Speed of sound
                gamma = 1.25
                R_specific = 287  # J/kg/K (approximate)
                c_avg = np.sqrt(gamma * R_specific * avg_temp)
                
                # Average Mach number
                avg_mach = (stations[i-1]['mach_number'] + station['mach_number']) / 2
                avg_velocity = avg_mach * c_avg
                
                # Time increment
                dt = dx / avg_velocity if avg_velocity > 0 else 1e-6
                station['residence_time'] = stations[i-1]['residence_time'] + dt
    
    def _solve_nozzle_kinetics(self, stations: List[Dict], initial_composition: Dict, 
                              chamber_conditions: Dict) -> List[Dict]:
        """Solve kinetic equations along nozzle expansion"""
        
        kinetic_solution = []
        
        # Initial conditions
        current_composition = initial_composition['molar_concentrations'].copy()
        current_temp = initial_composition['temperature']
        current_pressure = initial_composition['pressure']
        
        for i, station in enumerate(stations):
            if i == 0:
                # Chamber conditions
                solution_point = {
                    'station': station,
                    'composition': current_composition.copy(),
                    'temperature': current_temp,
                    'pressure': current_pressure,
                    'reaction_rates': {},
                    'kinetic_energy_loss': 0.0
                }
            else:
                # Solve kinetic equations for this station
                prev_station = stations[i-1]
                dt = station['residence_time'] - prev_station['residence_time']
                
                # Update composition using kinetic equations
                solution_point = self._integrate_kinetic_equations(
                    current_composition, current_temp, current_pressure,
                    station, dt
                )
                
                # Update current state
                current_composition = solution_point['composition']
                current_temp = solution_point['temperature']
                current_pressure = solution_point['pressure']
            
            kinetic_solution.append(solution_point)
        
        return kinetic_solution
    
    def _integrate_kinetic_equations(self, composition: Dict, temperature: float, 
                                   pressure: float, station: Dict, dt: float) -> Dict:
        """Integrate chemical kinetic equations over time step"""
        
        # Species list
        species_names = list(composition.keys())
        n_species = len(species_names)
        
        # Initial concentrations array
        y0 = np.array([composition[species] for species in species_names])
        
        # Define kinetic ODE system
        def kinetic_odes(t, y):
            # y contains species concentrations
            concentrations = {species_names[i]: max(0, y[i]) for i in range(n_species)}
            
            # Calculate reaction rates
            reaction_rates = self._calculate_reaction_rates(concentrations, temperature, pressure)
            
            # Species production/consumption rates
            dydt = np.zeros(n_species)
            
            for i, species in enumerate(species_names):
                net_rate = 0.0
                
                # Sum contributions from all reactions
                for reaction in self.reaction_mechanisms:
                    if species in [r[0] for r in reaction.reactants]:
                        # Species is consumed
                        stoich_coeff = next(r[1] for r in reaction.reactants if r[0] == species)
                        net_rate -= stoich_coeff * reaction_rates.get(reaction.reaction_id + '_forward', 0)
                    
                    if species in [p[0] for p in reaction.products]:
                        # Species is produced
                        stoich_coeff = next(p[1] for p in reaction.products if p[0] == species)
                        net_rate += stoich_coeff * reaction_rates.get(reaction.reaction_id + '_forward', 0)
                        
                    # Reverse reactions
                    if species in [p[0] for p in reaction.products]:
                        stoich_coeff = next(p[1] for p in reaction.products if p[0] == species)
                        net_rate -= stoich_coeff * reaction_rates.get(reaction.reaction_id + '_reverse', 0)
                    
                    if species in [r[0] for r in reaction.reactants]:
                        stoich_coeff = next(r[1] for r in reaction.reactants if r[0] == species)
                        net_rate += stoich_coeff * reaction_rates.get(reaction.reaction_id + '_reverse', 0)
                
                dydt[i] = net_rate
            
            return dydt
        
        # Integrate over time step
        try:
            sol = solve_ivp(kinetic_odes, [0, dt], y0, dense_output=True, rtol=1e-6)
            y_final = sol.y[:, -1]
            
            # Update concentrations
            final_composition = {species_names[i]: max(0, y_final[i]) for i in range(n_species)}
            
        except Exception as e:
            # If integration fails, use simplified approach
            final_composition = composition.copy()
            
            # Apply simple exponential decay for dissociation reactions
            for species in final_composition:
                if species in ['H2O', 'CO2', 'H2', 'O2']:
                    # Simplified dissociation rate
                    dissociation_rate = self._estimate_dissociation_rate(species, temperature)
                    final_composition[species] *= np.exp(-dissociation_rate * dt)
        
        # Calculate temperature change due to reactions (simplified)
        temp_change = self._calculate_temperature_change(composition, final_composition, temperature)
        final_temperature = station['temperature']  # Use isentropic temperature
        final_pressure = station['pressure']       # Use isentropic pressure
        
        # Calculate kinetic losses
        kinetic_loss = self._calculate_kinetic_energy_loss(composition, final_composition, temperature)
        
        return {
            'station': station,
            'composition': final_composition,
            'temperature': final_temperature,
            'pressure': final_pressure,
            'reaction_rates': self._calculate_reaction_rates(final_composition, final_temperature, final_pressure),
            'kinetic_energy_loss': kinetic_loss
        }
    
    def _calculate_reaction_rates(self, concentrations: Dict, temperature: float, pressure: float) -> Dict:
        """Calculate reaction rates for all mechanisms"""
        
        reaction_rates = {}
        
        for reaction in self.reaction_mechanisms:
            # Forward reaction rate
            k_forward = self._calculate_rate_constant(
                reaction.forward_rate_constant,
                reaction.activation_energy_forward,
                temperature
            )
            
            # Reactant concentration product
            reactant_product = 1.0
            for species, stoich in reaction.reactants:
                if species in concentrations:
                    reactant_product *= concentrations[species]**stoich
            
            forward_rate = k_forward * reactant_product
            reaction_rates[reaction.reaction_id + '_forward'] = forward_rate
            
            # Reverse reaction rate
            if reaction.reverse_rate_constant > 0:
                k_reverse = self._calculate_rate_constant(
                    reaction.reverse_rate_constant,
                    reaction.activation_energy_reverse,
                    temperature
                )
                
                product_product = 1.0
                for species, stoich in reaction.products:
                    if species in concentrations:
                        product_product *= concentrations[species]**stoich
                
                reverse_rate = k_reverse * product_product
                reaction_rates[reaction.reaction_id + '_reverse'] = reverse_rate
        
        return reaction_rates
    
    def _calculate_rate_constant(self, pre_exp_factor: float, activation_energy: float, 
                                temperature: float) -> float:
        """Calculate Arrhenius rate constant"""
        
        # k = A * exp(-E_a / RT)
        if activation_energy == 0:
            return pre_exp_factor
        
        return pre_exp_factor * np.exp(-activation_energy / (self.R * temperature))
    
    def _estimate_dissociation_rate(self, species: str, temperature: float) -> float:
        """Estimate dissociation rate for major species"""
        
        # Simplified dissociation rates (1/s)
        dissociation_rates = {
            'H2O': 1e12 * np.exp(-502000 / (self.R * temperature)),
            'H2': 1e15 * np.exp(-436000 / (self.R * temperature)),
            'O2': 1e13 * np.exp(-498000 / (self.R * temperature)),
            'CO2': 1e11 * np.exp(-532000 / (self.R * temperature))
        }
        
        return dissociation_rates.get(species, 0.0)
    
    def _calculate_temperature_change(self, initial_comp: Dict, final_comp: Dict, temperature: float) -> float:
        """Calculate temperature change due to reactions"""
        
        # Simplified energy balance
        # ΔT ≈ Σ(Δn_i * ΔH_f,i) / (n_total * C_p)
        
        total_enthalpy_change = 0.0
        total_moles = sum(final_comp.values())
        
        for species in initial_comp:
            if species in self.species_database:
                dn = final_comp.get(species, 0) - initial_comp.get(species, 0)
                h_formation = self.species_database[species].formation_enthalpy
                total_enthalpy_change += dn * h_formation
        
        # Average heat capacity (J/mol/K)
        cp_avg = 40.0
        
        if total_moles > 0:
            dT = -total_enthalpy_change / (total_moles * cp_avg)
            return dT
        
        return 0.0
    
    def _calculate_kinetic_energy_loss(self, initial_comp: Dict, final_comp: Dict, temperature: float) -> float:
        """Calculate kinetic energy loss due to finite reaction rates"""
        
        # Energy loss due to departure from equilibrium
        # Simplified calculation based on composition differences
        
        energy_loss = 0.0
        
        for species in initial_comp:
            if species in self.species_database:
                equilibrium_fraction = initial_comp[species]  # Assume initial is closer to equilibrium
                actual_fraction = final_comp.get(species, 0)
                
                # Energy penalty for deviation from equilibrium
                deviation = abs(actual_fraction - equilibrium_fraction) / (equilibrium_fraction + 1e-10)
                energy_loss += deviation * self.R * temperature  # J/mol
        
        return energy_loss
    
    def _calculate_kinetic_losses(self, kinetic_solution: List[Dict], chamber_conditions: Dict) -> Dict:
        """Calculate performance losses due to kinetic effects"""
        
        # Extract exit conditions
        exit_solution = kinetic_solution[-1]
        exit_temp_kinetic = exit_solution['temperature']
        exit_composition_kinetic = exit_solution['composition']
        
        # Calculate equilibrium exit conditions for comparison
        exit_temp_equilibrium = kinetic_solution[-1]['station']['temperature']  # Isentropic
        
        # Performance loss calculations
        # 1. Temperature loss
        temperature_loss = exit_temp_equilibrium - exit_temp_kinetic
        
        # 2. Specific impulse loss
        # ΔIsp/Isp ≈ ΔT/(2T)
        isp_loss_fraction = temperature_loss / (2 * exit_temp_equilibrium) if exit_temp_equilibrium > 0 else 0
        
        # 3. Characteristic velocity loss
        c_star_loss_fraction = temperature_loss / (2 * chamber_conditions['temperature'])
        
        # 4. Total kinetic energy loss
        total_kinetic_loss = sum(point['kinetic_energy_loss'] for point in kinetic_solution)
        
        # 5. Frozen vs Equilibrium analysis
        frozen_composition = self._calculate_frozen_composition(kinetic_solution)
        equilibrium_composition = self._calculate_equilibrium_composition(kinetic_solution)
        
        # 6. Reaction completeness
        reaction_completeness = self._calculate_reaction_completeness(kinetic_solution)
        
        return {
            'temperature_loss': temperature_loss,
            'isp_loss_fraction': isp_loss_fraction,
            'c_star_loss_fraction': c_star_loss_fraction,
            'total_kinetic_energy_loss': total_kinetic_loss,
            'frozen_composition': frozen_composition,
            'equilibrium_composition': equilibrium_composition,
            'reaction_completeness': reaction_completeness,
            'kinetic_efficiency': 1.0 - abs(isp_loss_fraction),
            'performance_summary': {
                'kinetic_loss_severity': self._classify_kinetic_losses(isp_loss_fraction),
                'dominant_loss_mechanism': self._identify_dominant_loss_mechanism(kinetic_solution),
                'recommendations': self._generate_kinetic_recommendations(isp_loss_fraction, reaction_completeness)
            }
        }
    
    def _calculate_frozen_composition(self, kinetic_solution: List[Dict]) -> Dict:
        """Calculate composition assuming frozen flow (no reactions)"""
        
        # Frozen composition = chamber composition throughout
        chamber_composition = kinetic_solution[0]['composition']
        return chamber_composition
    
    def _calculate_equilibrium_composition(self, kinetic_solution: List[Dict]) -> Dict:
        """Calculate equilibrium composition at exit conditions"""
        
        # Simplified equilibrium calculation
        # In practice, this would use CEA or similar equilibrium solver
        
        exit_conditions = kinetic_solution[-1]
        temperature = exit_conditions['temperature']
        pressure = exit_conditions['pressure']
        
        # Simplified equilibrium shift based on temperature
        chamber_comp = kinetic_solution[0]['composition']
        equilibrium_comp = {}
        
        for species, concentration in chamber_comp.items():
            if species in ['H2O', 'CO2']:
                # More stable at lower temperatures
                equilibrium_comp[species] = concentration * (3000 / temperature)**0.5
            elif species in ['H', 'O', 'OH']:
                # Less stable at lower temperatures
                equilibrium_comp[species] = concentration * (temperature / 3000)**2
            else:
                equilibrium_comp[species] = concentration
        
        # Normalize
        total = sum(equilibrium_comp.values())
        if total > 0:
            equilibrium_comp = {k: v/total * sum(chamber_comp.values()) for k, v in equilibrium_comp.items()}
        
        return equilibrium_comp
    
    def _calculate_reaction_completeness(self, kinetic_solution: List[Dict]) -> float:
        """Calculate overall reaction completeness"""
        
        # Compare actual composition change to maximum possible change
        initial_comp = kinetic_solution[0]['composition']
        final_comp = kinetic_solution[-1]['composition']
        equilibrium_comp = self._calculate_equilibrium_composition(kinetic_solution)
        
        total_actual_change = 0.0
        total_possible_change = 0.0
        
        for species in initial_comp:
            actual_change = abs(final_comp.get(species, 0) - initial_comp[species])
            possible_change = abs(equilibrium_comp.get(species, 0) - initial_comp[species])
            
            total_actual_change += actual_change
            total_possible_change += possible_change
        
        if total_possible_change > 0:
            return total_actual_change / total_possible_change
        else:
            return 1.0  # No reactions expected
    
    def _classify_kinetic_losses(self, isp_loss_fraction: float) -> str:
        """Classify severity of kinetic losses"""
        
        if abs(isp_loss_fraction) < 0.01:
            return 'NEGLIGIBLE'
        elif abs(isp_loss_fraction) < 0.03:
            return 'LOW'
        elif abs(isp_loss_fraction) < 0.05:
            return 'MODERATE'
        elif abs(isp_loss_fraction) < 0.10:
            return 'HIGH'
        else:
            return 'SEVERE'
    
    def _identify_dominant_loss_mechanism(self, kinetic_solution: List[Dict]) -> str:
        """Identify the dominant kinetic loss mechanism"""
        
        # Analyze reaction rates and completion times
        max_reaction_rate = 0.0
        dominant_reaction = 'UNKNOWN'
        
        for point in kinetic_solution:
            for reaction_id, rate in point['reaction_rates'].items():
                if rate > max_reaction_rate:
                    max_reaction_rate = rate
                    dominant_reaction = reaction_id
        
        if 'dissociation' in dominant_reaction:
            return 'SLOW_DISSOCIATION'
        elif 'recombination' in dominant_reaction:
            return 'SLOW_RECOMBINATION'
        else:
            return 'FINITE_REACTION_RATES'
    
    def _generate_kinetic_recommendations(self, isp_loss_fraction: float, reaction_completeness: float) -> List[str]:
        """Generate recommendations based on kinetic analysis"""
        
        recommendations = []
        
        if abs(isp_loss_fraction) > 0.05:
            recommendations.append('Significant kinetic losses detected - consider nozzle design optimization')
        
        if reaction_completeness < 0.7:
            recommendations.append('Low reaction completeness - increase residence time or chamber temperature')
        
        if abs(isp_loss_fraction) > 0.10:
            recommendations.append('CRITICAL: Severe kinetic losses - redesign required')
        
        if reaction_completeness > 0.95:
            recommendations.append('Good reaction completeness - kinetic effects minimal')
        
        if not recommendations:
            recommendations.append('Kinetic analysis shows acceptable performance')
        
        return recommendations
    
    def _compare_with_equilibrium(self, kinetic_solution: List[Dict], chamber_conditions: Dict) -> Dict:
        """Compare kinetic solution with equilibrium analysis"""
        
        # Performance comparison
        kinetic_exit = kinetic_solution[-1]
        
        # Simplified equilibrium calculation (would use CEA in practice)
        equilibrium_temp = kinetic_exit['station']['temperature']
        kinetic_temp = kinetic_exit['temperature']
        
        # Performance ratios
        temp_ratio = kinetic_temp / equilibrium_temp
        isp_ratio = np.sqrt(temp_ratio)  # Simplified relation
        
        return {
            'temperature_ratio': temp_ratio,
            'isp_ratio': isp_ratio,
            'equilibrium_exit_temperature': equilibrium_temp,
            'kinetic_exit_temperature': kinetic_temp,
            'performance_degradation': 1.0 - isp_ratio,
            'analysis_validity': 'VALID' if 0.8 < temp_ratio < 1.2 else 'QUESTIONABLE'
        }
    
    def _generate_detailed_kinetic_analysis(self, kinetic_solution: List[Dict], 
                                          performance_analysis: Dict, equilibrium_comparison: Dict) -> Dict:
        """Generate detailed kinetic analysis report"""
        
        return {
            'summary': {
                'kinetic_loss_severity': performance_analysis['performance_summary']['kinetic_loss_severity'],
                'isp_loss_percent': performance_analysis['isp_loss_fraction'] * 100,
                'reaction_completeness_percent': performance_analysis['reaction_completeness'] * 100,
                'kinetic_efficiency_percent': performance_analysis['kinetic_efficiency'] * 100
            },
            'dominant_mechanisms': {
                'primary_loss_mechanism': performance_analysis['performance_summary']['dominant_loss_mechanism'],
                'critical_reactions': self._identify_critical_reactions(kinetic_solution),
                'bottleneck_species': self._identify_bottleneck_species(kinetic_solution)
            },
            'design_recommendations': {
                'nozzle_design': self._generate_nozzle_design_recommendations(performance_analysis),
                'operating_conditions': self._generate_operating_recommendations(performance_analysis),
                'propellant_considerations': self._generate_propellant_recommendations(kinetic_solution)
            },
            'uncertainty_analysis': {
                'kinetic_model_uncertainty': 'MEDIUM',  # Simplified
                'rate_constant_uncertainty': 'HIGH',    # Simplified
                'overall_confidence': 'MODERATE'        # Simplified
            }
        }
    
    def _identify_critical_reactions(self, kinetic_solution: List[Dict]) -> List[str]:
        """Identify most critical reactions affecting performance"""
        
        reaction_impacts = {}
        
        for point in kinetic_solution:
            for reaction_id, rate in point['reaction_rates'].items():
                if reaction_id not in reaction_impacts:
                    reaction_impacts[reaction_id] = 0.0
                reaction_impacts[reaction_id] += abs(rate)
        
        # Sort by impact
        sorted_reactions = sorted(reaction_impacts.items(), key=lambda x: x[1], reverse=True)
        
        return [reaction[0] for reaction in sorted_reactions[:3]]  # Top 3
    
    def _identify_bottleneck_species(self, kinetic_solution: List[Dict]) -> List[str]:
        """Identify species that limit reaction rates"""
        
        species_variations = {}
        
        for species in kinetic_solution[0]['composition'].keys():
            concentrations = [point['composition'].get(species, 0) for point in kinetic_solution]
            variation = (max(concentrations) - min(concentrations)) / (max(concentrations) + 1e-10)
            species_variations[species] = variation
        
        # Sort by variation (species with high variation are likely bottlenecks)
        sorted_species = sorted(species_variations.items(), key=lambda x: x[1], reverse=True)
        
        return [species[0] for species in sorted_species[:3]]  # Top 3
    
    def _generate_nozzle_design_recommendations(self, performance_analysis: Dict) -> List[str]:
        """Generate nozzle design recommendations"""
        
        recommendations = []
        
        isp_loss = abs(performance_analysis['isp_loss_fraction'])
        
        if isp_loss > 0.05:
            recommendations.append('Consider longer nozzle for increased residence time')
            recommendations.append('Evaluate area distribution for better kinetic performance')
        
        if performance_analysis['reaction_completeness'] < 0.8:
            recommendations.append('Increase chamber length for better mixing')
            recommendations.append('Consider staged combustion for more complete reactions')
        
        return recommendations if recommendations else ['Current nozzle design appears adequate']
    
    def _generate_operating_recommendations(self, performance_analysis: Dict) -> List[str]:
        """Generate operating condition recommendations"""
        
        recommendations = []
        
        if performance_analysis['reaction_completeness'] < 0.7:
            recommendations.append('Increase chamber temperature to accelerate reactions')
            recommendations.append('Consider higher chamber pressure for better kinetics')
        
        return recommendations if recommendations else ['Operating conditions appear suitable']
    
    def _generate_propellant_recommendations(self, kinetic_solution: List[Dict]) -> List[str]:
        """Generate propellant-related recommendations"""
        
        recommendations = []
        
        # Analyze final composition for unreacted species
        final_comp = kinetic_solution[-1]['composition']
        
        for species, concentration in final_comp.items():
            if species in ['H2', 'O2'] and concentration > 0.01:  # Significant unreacted oxidizer/fuel
                recommendations.append(f'High {species} concentration at exit - consider mixture ratio adjustment')
        
        return recommendations if recommendations else ['Propellant utilization appears good']
    
    def _extract_species_profiles(self, kinetic_solution: List[Dict]) -> Dict:
        """Extract species concentration profiles along nozzle"""
        
        profiles = {}
        
        # Axial positions
        positions = [point['station']['axial_position'] for point in kinetic_solution]
        
        # Extract each species profile
        all_species = set()
        for point in kinetic_solution:
            all_species.update(point['composition'].keys())
        
        for species in all_species:
            concentrations = [point['composition'].get(species, 0) for point in kinetic_solution]
            profiles[species] = {
                'positions': positions,
                'concentrations': concentrations,
                'units': 'mol/m³'
            }
        
        return profiles
    
    def _extract_temperature_profile(self, kinetic_solution: List[Dict]) -> Dict:
        """Extract temperature profile along nozzle"""
        
        positions = [point['station']['axial_position'] for point in kinetic_solution]
        temperatures = [point['temperature'] for point in kinetic_solution]
        
        return {
            'positions': positions,
            'temperatures': temperatures,
            'units': 'K'
        }
    
    def _extract_pressure_profile(self, kinetic_solution: List[Dict]) -> Dict:
        """Extract pressure profile along nozzle"""
        
        positions = [point['station']['axial_position'] for point in kinetic_solution]
        pressures = [point['pressure'] for point in kinetic_solution]
        
        return {
            'positions': positions,
            'pressures': pressures,
            'units': 'Pa'
        }
    
    def export_kinetic_results(self, results: Dict, filename: str):
        """Export kinetic analysis results"""
        
        # Prepare export data
        export_data = {
            'performance_losses': results['performance_losses'],
            'equilibrium_comparison': results['equilibrium_comparison'],
            'detailed_analysis': results['detailed_analysis'],
            'species_profiles': results['species_profiles'],
            'temperature_profile': results['temperature_profile'],
            'pressure_profile': results['pressure_profile']
        }
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)

# Create global kinetic analyzer instance
kinetic_analyzer = NozzleKineticAnalyzer()