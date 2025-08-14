"""
Advanced Results Display Module
NASA CEA-style comprehensive results tables and charts
"""

import numpy as np
import json
from typing import Dict, List, Optional

def create_cea_style_results(motor_results: Dict) -> str:
    """Create NASA CEA-style results output"""
    
    results_text = []
    
    # Header
    results_text.append("=" * 80)
    results_text.append("UZAYTEK HYBRID ROCKET MOTOR ANALYSIS")
    results_text.append("THEORETICAL ROCKET PERFORMANCE")
    results_text.append("=" * 80)
    results_text.append("")
    
    # Motor Information
    results_text.append("MOTOR CONFIGURATION:")
    results_text.append(f"  Motor Name: {motor_results.get('motor_name', 'UZAYTEK-HRM-001')}")
    results_text.append(f"  Fuel Type: {motor_results.get('fuel_type', 'HTPB').upper()}")
    results_text.append(f"  Oxidizer: N2O")
    results_text.append(f"  O/F Ratio: {motor_results.get('of_ratio', 0):.4f}")
    
    if 'stoichiometric_of' in motor_results:
        results_text.append(f"  O/F Stoichiometric: {motor_results['stoichiometric_of']:.4f}")
        results_text.append(f"  Equivalence Ratio: {motor_results['equivalence_ratio']:.4f}")
    
    results_text.append("")
    
    # Operating Conditions
    results_text.append("OPERATING CONDITIONS:")
    results_text.append(f"  Chamber Pressure: {motor_results['chamber_pressure']:.2f} bar")
    results_text.append(f"  Chamber Temperature: {motor_results['chamber_temperature']:.1f} K")
    results_text.append(f"  Burn Time: {motor_results['burn_time']:.1f} s")
    results_text.append(f"  Total Impulse: {motor_results['total_impulse']:.0f} N⋅s")
    results_text.append("")
    
    # Combustion Properties Table
    if 'mass_fractions' in motor_results:
        results_text.append("COMBUSTION PROPERTIES:")
        results_text.append("")
        results_text.append("Parameter".ljust(25) + "Chamber".rjust(12) + "Throat".rjust(12) + "Exit".rjust(12) + "Unit".rjust(15))
        results_text.append("-" * 80)
        
        conditions = motor_results.get('combustion_analysis', {}).get('conditions', {})
        
        # Pressure
        p_chamber = conditions.get('chamber', {}).get('P', 0)
        p_throat = conditions.get('throat', {}).get('P', 0) 
        p_exit = conditions.get('exit', {}).get('P', 0)
        results_text.append("Pressure".ljust(25) + f"{p_chamber:.4f}".rjust(12) + f"{p_throat:.4f}".rjust(12) + f"{p_exit:.4f}".rjust(12) + "bar".rjust(15))
        
        # Temperature
        t_chamber = conditions.get('chamber', {}).get('T', 0)
        t_throat = conditions.get('throat', {}).get('T', 0)
        t_exit = conditions.get('exit', {}).get('T', 0)
        results_text.append("Temperature".ljust(25) + f"{t_chamber:.1f}".rjust(12) + f"{t_throat:.1f}".rjust(12) + f"{t_exit:.1f}".rjust(12) + "K".rjust(15))
        
        results_text.append("")
        
        # Mass Fractions
        results_text.append("MASS FRACTIONS:")
        results_text.append("")
        results_text.append("Species".ljust(15) + "Chamber".rjust(12) + "Throat".rjust(12) + "Exit".rjust(12))
        results_text.append("-" * 60)
        
        mass_fractions = motor_results['mass_fractions']
        
        # Major species
        major_species = ['CO2', 'CO', 'H2O', 'H2', 'N2', 'OH', 'O2', 'NO']
        
        for species in major_species:
            chamber_frac = mass_fractions.get('chamber', {}).get(species, 0)
            throat_frac = mass_fractions.get('throat', {}).get(species, 0)
            exit_frac = mass_fractions.get('exit', {}).get(species, 0)
            
            if chamber_frac > 0.0001 or throat_frac > 0.0001 or exit_frac > 0.0001:
                results_text.append(f"*{species}".ljust(15) + f"{chamber_frac:.6f}".rjust(12) + 
                                  f"{throat_frac:.6f}".rjust(12) + f"{exit_frac:.6f}".rjust(12))
        
        results_text.append("")
    
    # Motor Geometry
    results_text.append("MOTOR GEOMETRY:")
    results_text.append("")
    results_text.append("Chamber Design".ljust(35) + "Nozzle Design".rjust(35))
    results_text.append("-" * 35 + " " + "-" * 35)
    
    # Chamber parameters
    dc = motor_results['chamber_diameter'] * 1000  # Convert to mm
    lc = motor_results['chamber_length'] * 1000
    vc = motor_results['chamber_volume'] * 1e6  # Convert to cm³
    
    # Nozzle parameters  
    dt = motor_results['throat_diameter'] * 1000
    de = motor_results['exit_diameter'] * 1000
    expansion_ratio = motor_results['expansion_ratio']
    
    results_text.append(f"Dc: {dc:.2f} mm".ljust(35) + f"Dt: {dt:.2f} mm".rjust(35))
    results_text.append(f"Lc: {lc:.2f} mm".ljust(35) + f"De: {de:.2f} mm".rjust(35))
    results_text.append(f"Vc: {vc:.1f} cm³".ljust(35) + f"Ae/At: {expansion_ratio:.2f}".rjust(35))
    
    if 'nozzle_contour' in motor_results:
        contour = motor_results['nozzle_contour']
        nozzle_length = contour.get('total_length', 0)
        nozzle_type = contour.get('divergent', {}).get('type', 'bell')
        results_text.append(f"L*: {motor_results.get('l_star', 1.0):.2f} m".ljust(35) + 
                          f"Length: {nozzle_length:.2f} mm".rjust(35))
        results_text.append(f"".ljust(35) + f"Type: {nozzle_type.title()}".rjust(35))
    
    results_text.append("")
    
    # Performance Parameters
    results_text.append("PERFORMANCE PARAMETERS:")
    results_text.append("")
    results_text.append("Parameter".ljust(30) + "Sea Level".rjust(15) + "Vacuum".rjust(15) + "Units".rjust(15))
    results_text.append("-" * 75)
    
    sea_level_isp = motor_results.get('sea_level_isp', motor_results['isp'])
    vacuum_isp = motor_results.get('vacuum_isp', motor_results['isp'] * 1.15)
    
    results_text.append("Specific Impulse".ljust(30) + f"{sea_level_isp:.1f}".rjust(15) + 
                       f"{vacuum_isp:.1f}".rjust(15) + "s".rjust(15))
    results_text.append("Thrust".ljust(30) + f"{motor_results['thrust']:.0f}".rjust(15) + 
                       f"{motor_results['thrust'] * 1.15:.0f}".rjust(15) + "N".rjust(15))
    results_text.append("C*".ljust(30) + f"{motor_results['c_star']:.1f}".rjust(15) + 
                       f"{motor_results['c_star']:.1f}".rjust(15) + "m/s".rjust(15))
    results_text.append("Cf".ljust(30) + f"{motor_results['cf']:.4f}".rjust(15) + 
                       f"{motor_results['cf'] * 1.15:.4f}".rjust(15) + "-".rjust(15))
    
    results_text.append("")
    
    # Mass Flow Rates
    results_text.append("MASS FLOW RATES:")
    results_text.append("-" * 40)
    results_text.append(f"Total: {motor_results['mdot_total']:.4f} kg/s")
    results_text.append(f"Oxidizer: {motor_results['mdot_ox']:.4f} kg/s")
    results_text.append(f"Fuel: {motor_results['mdot_f']:.4f} kg/s")
    results_text.append("")
    
    # Propellant Masses
    results_text.append("PROPELLANT LOADING:")
    results_text.append("-" * 40)
    results_text.append(f"Total: {motor_results['propellant_mass_total']:.2f} kg")
    results_text.append(f"Oxidizer: {motor_results['oxidizer_mass']:.2f} kg")
    results_text.append(f"Fuel: {motor_results['fuel_mass']:.2f} kg")
    results_text.append("")
    
    # Fuel Grain Design
    results_text.append("FUEL GRAIN DESIGN:")
    results_text.append("-" * 40)
    port_initial = motor_results['port_diameter_initial'] * 1000
    port_final = motor_results['port_diameter_final'] * 1000
    regression_rate = motor_results['regression_rate'] * 1000  # Convert to mm/s
    
    results_text.append(f"Initial Port Diameter: {port_initial:.2f} mm")
    results_text.append(f"Final Port Diameter: {port_final:.2f} mm")
    results_text.append(f"Regression Rate: {regression_rate:.3f} mm/s")
    results_text.append(f"Initial G_ox: {motor_results['g_ox_initial']:.1f} kg/(m²⋅s)")
    results_text.append(f"Final G_ox: {motor_results['g_ox_final']:.1f} kg/(m²⋅s)")
    results_text.append("")
    
    # Thermodynamic Properties
    if 'combustion_analysis' in motor_results and 'thermodynamic_properties' in motor_results['combustion_analysis']['performance']:
        thermo_props = motor_results['combustion_analysis']['performance']['thermodynamic_properties']
        
        results_text.append("THERMODYNAMIC PROPERTIES:")
        results_text.append("")
        results_text.append("Station".ljust(15) + "Enthalpy".ljust(12) + "Entropy".ljust(12) + "Density".ljust(12) + "Cp".ljust(12))
        results_text.append("".ljust(15) + "(kJ/kg)".ljust(12) + "(kJ/kg·K)".ljust(12) + "(kg/m³)".ljust(12) + "(kJ/kg·K)".ljust(12))
        results_text.append("-" * 75)
        
        for station in ['chamber', 'throat', 'exit']:
            if station in thermo_props['stations']:
                props = thermo_props['stations'][station]
                results_text.append(f"{station.title()}".ljust(15) + 
                                  f"{props['enthalpy']:.1f}".ljust(12) + 
                                  f"{props['entropy']:.4f}".ljust(12) + 
                                  f"{props['density']:.2f}".ljust(12) + 
                                  f"{props['cp']:.3f}".ljust(12))
        
        results_text.append("")
        results_text.append(f"Isentropic Efficiency: {thermo_props['isentropic_efficiency']:.1%}")
        results_text.append(f"Enthalpy Change: {thermo_props['deltas']['enthalpy_change']:.1f} kJ/kg")
        results_text.append(f"Entropy Change: {thermo_props['deltas']['entropy_change']:.4f} kJ/kg·K")
        results_text.append("")
    
    # Optimization Results
    if 'optimum_of_ratio' in motor_results:
        results_text.append("OPTIMIZATION ANALYSIS:")
        results_text.append("-" * 40)
        results_text.append(f"Current O/F: {motor_results['of_ratio']:.4f}")
        results_text.append(f"Optimum O/F: {motor_results['optimum_of_ratio']:.4f}")
        results_text.append(f"Maximum Isp: {motor_results['maximum_isp']:.1f} s")
        results_text.append(f"Current Isp: {motor_results['isp']:.1f} s")
        
        isp_efficiency = (motor_results['isp'] / motor_results['maximum_isp']) * 100
        results_text.append(f"Isp Efficiency: {isp_efficiency:.1f}%")
        results_text.append("")
    
    # Total Impulse to Thrust Analysis
    if 'thrust_altitude_analysis' in motor_results:
        thrust_analysis = motor_results['thrust_altitude_analysis']
        
        results_text.append("TOTAL IMPULSE ANALYSIS:")
        results_text.append("-" * 40)
        results_text.append(f"Input Total Impulse: {thrust_analysis['input_total_impulse']:.0f} N·s")
        results_text.append(f"Sea Level Thrust: {thrust_analysis['base_thrust_sea_level']:.0f} N")
        results_text.append(f"Maximum Thrust: {thrust_analysis['max_thrust']:.0f} N at {thrust_analysis['max_thrust_altitude']:.0f} m")
        results_text.append(f"Vacuum Thrust: {thrust_analysis['vacuum_thrust']:.0f} N")
        results_text.append("")
        
        results_text.append("THRUST vs ALTITUDE:")
        results_text.append("Altitude".ljust(12) + "Thrust".ljust(12) + "Isp".ljust(12) + "Efficiency".ljust(12))
        results_text.append("(m)".ljust(12) + "(N)".ljust(12) + "(s)".ljust(12) + "(%)".ljust(12))
        results_text.append("-" * 48)
        
        for point in thrust_analysis['thrust_altitude_data'][:6]:  # Show first 6 points
            results_text.append(f"{point['altitude']:.0f}".ljust(12) + 
                              f"{point['thrust']:.0f}".ljust(12) + 
                              f"{point['isp']:.1f}".ljust(12) + 
                              f"{point['impulse_efficiency']*100:.1f}".ljust(12))
        
        results_text.append("")
    
    # Altitude Performance Table
    if 'altitude_performance' in motor_results:
        results_text.append("ALTITUDE PERFORMANCE:")
        results_text.append("")
        results_text.append("Altitude".ljust(12) + "Pressure".ljust(12) + "Isp".ljust(12) + 
                          "Thrust".ljust(12) + "Cf".ljust(12))
        results_text.append("(m)".ljust(12) + "(bar)".ljust(12) + "(s)".ljust(12) + 
                          "(N)".ljust(12) + "(-)".ljust(12))
        results_text.append("-" * 60)
        
        alt_data = motor_results['altitude_performance']['altitude_performance']
        for point in alt_data[:8]:  # Show first 8 points
            results_text.append(f"{point['altitude']:.0f}".ljust(12) + 
                              f"{point['pressure']:.4f}".ljust(12) + 
                              f"{point['isp']:.1f}".ljust(12) + 
                              f"{point['thrust']:.0f}".ljust(12) + 
                              f"{point['cf']:.4f}".ljust(12))
        
        results_text.append("")
    
    results_text.append("=" * 80)
    results_text.append("Analysis completed with UZAYTEK Advanced Hybrid Rocket Analysis Software")
    results_text.append("=" * 80)
    
    return "\n".join(results_text)

def create_altitude_performance_plot(altitude_data: List[Dict]) -> str:
    """Create altitude performance visualization"""
    
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    # Extract data
    altitudes = [p['altitude'] / 1000 for p in altitude_data]  # Convert to km
    isp_values = [p['isp'] for p in altitude_data]
    thrust_values = [p['thrust'] for p in altitude_data]
    cf_values = [p['cf'] for p in altitude_data]
    pressure_values = [p['pressure'] for p in altitude_data]
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Specific Impulse vs Altitude', 'Thrust vs Altitude',
                       'Thrust Coefficient vs Altitude', 'Atmospheric Pressure vs Altitude'),
        vertical_spacing=0.12
    )
    
    # Isp vs altitude
    fig.add_trace(
        go.Scatter(x=altitudes, y=isp_values, mode='lines+markers',
                  name='Specific Impulse', line=dict(color='blue', width=3)),
        row=1, col=1
    )
    
    # Thrust vs altitude  
    fig.add_trace(
        go.Scatter(x=altitudes, y=thrust_values, mode='lines+markers',
                  name='Thrust', line=dict(color='red', width=3)),
        row=1, col=2
    )
    
    # Cf vs altitude
    fig.add_trace(
        go.Scatter(x=altitudes, y=cf_values, mode='lines+markers',
                  name='Thrust Coefficient', line=dict(color='green', width=3)),
        row=2, col=1
    )
    
    # Pressure vs altitude
    fig.add_trace(
        go.Scatter(x=altitudes, y=pressure_values, mode='lines+markers',
                  name='Atmospheric Pressure', line=dict(color='orange', width=3)),
        row=2, col=2
    )
    
    # Update layout
    fig.update_layout(
        title='Altitude Performance Analysis',
        showlegend=False,
        height=600,
        width=1000
    )
    
    # Update axes
    fig.update_xaxes(title_text="Altitude (km)", row=1, col=1)
    fig.update_yaxes(title_text="Isp (s)", row=1, col=1)
    fig.update_xaxes(title_text="Altitude (km)", row=1, col=2)
    fig.update_yaxes(title_text="Thrust (N)", row=1, col=2)
    fig.update_xaxes(title_text="Altitude (km)", row=2, col=1)
    fig.update_yaxes(title_text="Cf (-)", row=2, col=1)
    fig.update_xaxes(title_text="Altitude (km)", row=2, col=2)
    fig.update_yaxes(title_text="Pressure (bar)", row=2, col=2)
    
    return fig.to_json()

def create_mass_fractions_plot(mass_fractions: Dict) -> str:
    """Create mass fractions visualization"""
    
    import plotly.graph_objects as go
    
    stations = ['Chamber', 'Throat', 'Exit']
    
    # Major species to plot
    species_list = ['CO2', 'CO', 'H2O', 'N2', 'H2', 'OH', 'O2', 'NO']
    colors = ['red', 'orange', 'blue', 'green', 'purple', 'brown', 'pink', 'gray']
    
    fig = go.Figure()
    
    for i, species in enumerate(species_list):
        chamber_frac = mass_fractions.get('chamber', {}).get(species, 0)
        throat_frac = mass_fractions.get('throat', {}).get(species, 0)
        exit_frac = mass_fractions.get('exit', {}).get(species, 0)
        
        fractions = [chamber_frac, throat_frac, exit_frac]
        
        if max(fractions) > 0.001:  # Only plot significant species
            fig.add_trace(go.Scatter(
                x=stations,
                y=fractions,
                mode='lines+markers',
                name=species,
                line=dict(color=colors[i % len(colors)], width=3),
                marker=dict(size=8)
            ))
    
    fig.update_layout(
        title='Mass Fractions Through Nozzle',
        xaxis_title='Nozzle Station',
        yaxis_title='Mass Fraction',
        yaxis_type='log',
        width=800,
        height=500,
        hovermode='x unified'
    )
    
    return fig.to_json()

def create_thrust_altitude_plot(thrust_data: List[Dict]) -> str:
    """Create thrust vs altitude visualization"""
    
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    # Extract data
    altitudes = [p['altitude'] / 1000 for p in thrust_data]  # Convert to km
    thrust_values = [p['thrust'] for p in thrust_data]
    isp_values = [p['isp'] for p in thrust_data]
    efficiency_values = [p['impulse_efficiency'] * 100 for p in thrust_data]
    
    # Create subplots
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=('Thrust vs Altitude', 'Specific Impulse vs Altitude', 'Impulse Efficiency vs Altitude'),
        horizontal_spacing=0.1
    )
    
    # Thrust vs altitude
    fig.add_trace(
        go.Scatter(x=altitudes, y=thrust_values, mode='lines+markers',
                  name='Thrust', line=dict(color='red', width=3)),
        row=1, col=1
    )
    
    # Isp vs altitude  
    fig.add_trace(
        go.Scatter(x=altitudes, y=isp_values, mode='lines+markers',
                  name='Specific Impulse', line=dict(color='blue', width=3)),
        row=1, col=2
    )
    
    # Efficiency vs altitude
    fig.add_trace(
        go.Scatter(x=altitudes, y=efficiency_values, mode='lines+markers',
                  name='Impulse Efficiency', line=dict(color='green', width=3)),
        row=1, col=3
    )
    
    # Update layout
    fig.update_layout(
        title='Total Impulse Analysis - Altitude Performance',
        showlegend=False,
        height=400,
        width=1200
    )
    
    # Update axes
    fig.update_xaxes(title_text="Altitude (km)", row=1, col=1)
    fig.update_yaxes(title_text="Thrust (N)", row=1, col=1)
    fig.update_xaxes(title_text="Altitude (km)", row=1, col=2)
    fig.update_yaxes(title_text="Isp (s)", row=1, col=2)
    fig.update_xaxes(title_text="Altitude (km)", row=1, col=3)
    fig.update_yaxes(title_text="Efficiency (%)", row=1, col=3)
    
    return fig.to_json()