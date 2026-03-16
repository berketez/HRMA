"""
2D CFD Analysis Module
Computational Fluid Dynamics analysis for rocket motor internal flows
"""

import numpy as np
import matplotlib.pyplot as plt
from scipy import sparse
from scipy.sparse.linalg import spsolve
from scipy.interpolate import griddata
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

@dataclass
class CFDGrid:
    """2D CFD computational grid"""
    x: np.ndarray  # X coordinates
    y: np.ndarray  # Y coordinates
    nx: int        # Number of x points
    ny: int        # Number of y points
    dx: float      # Grid spacing in x
    dy: float      # Grid spacing in y

@dataclass
class FlowProperties:
    """Flow properties at each grid point"""
    pressure: np.ndarray      # Pressure field
    velocity_x: np.ndarray    # X-velocity field
    velocity_y: np.ndarray    # Y-velocity field
    temperature: np.ndarray   # Temperature field
    density: np.ndarray       # Density field
    mach_number: np.ndarray   # Mach number field

@dataclass
class BoundaryConditions:
    """Boundary conditions for CFD analysis"""
    inlet_pressure: float     # Inlet stagnation pressure (Pa)
    inlet_temperature: float  # Inlet stagnation temperature (K)
    outlet_pressure: float    # Outlet static pressure (Pa)
    wall_temperature: float   # Wall temperature (K)
    mass_flow_rate: float     # Mass flow rate (kg/s)

class CFD2DAnalyzer:
    """2D CFD analysis for rocket motor flows"""
    
    def __init__(self):
        self.gamma = 1.25  # Specific heat ratio
        self.R = 287.0     # Gas constant J/kg/K
        self.mu_ref = 1.8e-5  # Reference viscosity kg/m/s
        self.T_ref = 288.0    # Reference temperature K
        self.convergence_tolerance = 1e-6
        self.max_iterations = 1000
    
    def analyze_motor_flow(self, motor_geometry: Dict, boundary_conditions: BoundaryConditions,
                          motor_type: str = 'hybrid') -> Dict:
        """
        Complete 2D CFD analysis of rocket motor internal flow
        
        Args:
            motor_geometry: Motor geometric parameters
            boundary_conditions: Flow boundary conditions  
            motor_type: 'hybrid', 'liquid', or 'solid'
            
        Returns:
            CFD analysis results
        """
        
        # Generate computational grid
        grid = self._generate_motor_grid(motor_geometry, motor_type)
        
        # Initialize flow field
        flow_props = self._initialize_flow_field(grid, boundary_conditions)
        
        # Solve flow equations
        converged_flow = self._solve_flow_equations(grid, flow_props, boundary_conditions, motor_type)
        
        # Post-process results
        results = self._post_process_results(grid, converged_flow, boundary_conditions, motor_geometry)
        
        # Generate visualizations
        visualizations = self._generate_visualizations(grid, converged_flow, motor_type)
        
        return {
            'flow_field': converged_flow,
            'grid': grid,
            'performance_metrics': results,
            'visualizations': visualizations,
            'boundary_conditions': boundary_conditions,
            'convergence_info': self.convergence_info
        }
    
    def _generate_motor_grid(self, geometry: Dict, motor_type: str) -> CFDGrid:
        """Generate 2D computational grid for motor geometry"""
        
        # Extract geometry parameters
        chamber_length = geometry.get('chamber_length', 0.5)  # m
        chamber_radius = geometry.get('chamber_radius', 0.05)  # m
        throat_radius = geometry.get('throat_radius', 0.01)   # m
        exit_radius = geometry.get('exit_radius', 0.025)      # m
        nozzle_length = geometry.get('nozzle_length', 0.1)    # m
        
        # Grid resolution
        nx_chamber = 80
        nx_nozzle = 60
        ny = 50
        
        # X coordinates
        x_chamber = np.linspace(0, chamber_length, nx_chamber + 1)
        x_nozzle = np.linspace(chamber_length, chamber_length + nozzle_length, nx_nozzle)
        x = np.concatenate([x_chamber, x_nozzle[1:]])  # Remove duplicate point
        nx = len(x)
        
        # Y coordinates (from centerline to wall)
        if motor_type == 'hybrid':
            # Include fuel grain geometry
            port_radius = geometry.get('port_radius', chamber_radius * 0.7)
            fuel_grain_thickness = chamber_radius - port_radius
            
            # Create non-uniform y grid with clustering near grain surface
            y_port = np.linspace(0, port_radius, int(ny * 0.4))
            y_grain = np.linspace(port_radius, chamber_radius, int(ny * 0.6))
            y_chamber = np.concatenate([y_port, y_grain[1:]])
        else:
            y_chamber = np.linspace(0, chamber_radius, ny)
        
        # Create 2D grid
        X, Y = np.meshgrid(x, y_chamber)
        
        # Adjust Y coordinates for nozzle contour
        nozzle_start_idx = nx_chamber
        for i in range(nozzle_start_idx, nx):
            # Linear nozzle contour (can be improved with bell or conical)
            x_nozzle_local = (x[i] - chamber_length) / nozzle_length
            
            if x_nozzle_local <= 0.5:  # Converging section
                radius_local = chamber_radius - (chamber_radius - throat_radius) * x_nozzle_local * 2
            else:  # Diverging section
                radius_local = throat_radius + (exit_radius - throat_radius) * (x_nozzle_local - 0.5) * 2
            
            # Scale Y coordinates to nozzle contour
            Y[:, i] = Y[:, i] * radius_local / chamber_radius
        
        # Calculate grid spacing
        dx = np.mean(np.diff(x))
        dy = np.mean(np.diff(y_chamber))
        
        return CFDGrid(X, Y, nx, len(y_chamber), dx, dy)
    
    def _initialize_flow_field(self, grid: CFDGrid, bc: BoundaryConditions) -> FlowProperties:
        """Initialize flow field with reasonable initial conditions"""
        
        nx, ny = grid.nx, grid.ny
        
        # Initialize with linear pressure drop
        pressure = np.zeros((ny, nx))
        for i in range(nx):
            pressure[:, i] = bc.inlet_pressure - (bc.inlet_pressure - bc.outlet_pressure) * i / (nx - 1)
        
        # Initialize temperature (constant for now)
        temperature = np.full((ny, nx), bc.inlet_temperature)
        
        # Initialize density from ideal gas law
        density = pressure / (self.R * temperature)
        
        # Initialize velocities (small initial values)
        velocity_x = np.full((ny, nx), 10.0)  # m/s
        velocity_y = np.zeros((ny, nx))
        
        # Calculate Mach number
        c = np.sqrt(self.gamma * self.R * temperature)  # Speed of sound
        velocity_mag = np.sqrt(velocity_x**2 + velocity_y**2)
        mach_number = velocity_mag / c
        
        return FlowProperties(pressure, velocity_x, velocity_y, temperature, density, mach_number)
    
    def _solve_flow_equations(self, grid: CFDGrid, flow: FlowProperties, 
                             bc: BoundaryConditions, motor_type: str) -> FlowProperties:
        """Solve 2D flow equations using finite difference method"""
        
        self.convergence_info = {'iterations': 0, 'residual': 1.0, 'converged': False}
        
        # Relaxation factors for stability
        relaxation_factors = {
            'pressure': 0.3,
            'velocity': 0.5,
            'temperature': 0.4,
            'density': 0.3
        }
        
        for iteration in range(self.max_iterations):
            # Store old values for convergence check
            p_old = flow.pressure.copy()
            u_old = flow.velocity_x.copy()
            v_old = flow.velocity_y.copy()
            T_old = flow.temperature.copy()
            rho_old = flow.density.copy()
            
            # Solve momentum equations
            self._solve_momentum_equations(grid, flow, bc, relaxation_factors, motor_type)
            
            # Solve energy equation
            self._solve_energy_equation(grid, flow, bc, relaxation_factors)
            
            # Update density from equation of state
            flow.density = flow.pressure / (self.R * flow.temperature)
            
            # Apply boundary conditions
            self._apply_boundary_conditions(grid, flow, bc, motor_type)
            
            # Update Mach number
            c = np.sqrt(self.gamma * self.R * flow.temperature)
            velocity_mag = np.sqrt(flow.velocity_x**2 + flow.velocity_y**2)
            flow.mach_number = velocity_mag / c
            
            # Check convergence
            residual_p = np.max(np.abs(flow.pressure - p_old)) / np.max(np.abs(flow.pressure))
            residual_u = np.max(np.abs(flow.velocity_x - u_old)) / np.max(np.abs(flow.velocity_x))
            residual_v = np.max(np.abs(flow.velocity_y - v_old)) / (np.max(np.abs(flow.velocity_y)) + 1e-10)
            residual_T = np.max(np.abs(flow.temperature - T_old)) / np.max(np.abs(flow.temperature))
            
            max_residual = max(residual_p, residual_u, residual_v, residual_T)
            
            self.convergence_info['iterations'] = iteration + 1
            self.convergence_info['residual'] = max_residual
            
            if max_residual < self.convergence_tolerance:
                self.convergence_info['converged'] = True
                break
            
            # Print progress every 100 iterations
            if (iteration + 1) % 100 == 0:
                print(f"CFD Iteration {iteration + 1}: Residual = {max_residual:.2e}")
        
        return flow
    
    def _solve_momentum_equations(self, grid: CFDGrid, flow: FlowProperties, 
                                 bc: BoundaryConditions, relax: Dict, motor_type: str):
        """Solve 2D momentum equations"""
        
        nx, ny = grid.nx, grid.ny
        dx, dy = grid.dx, grid.dy
        
        # Calculate dynamic viscosity (Sutherland's law)
        mu = self.mu_ref * (flow.temperature / self.T_ref)**1.5 * \
             ((self.T_ref + 110) / (flow.temperature + 110))
        
        # X-momentum equation
        u_new = flow.velocity_x.copy()
        for i in range(1, nx-1):
            for j in range(1, ny-1):
                # Convective terms
                dudx = (flow.velocity_x[j, i+1] - flow.velocity_x[j, i-1]) / (2 * dx)
                dudy = (flow.velocity_x[j+1, i] - flow.velocity_x[j-1, i]) / (2 * dy)
                
                convective = flow.velocity_x[j, i] * dudx + flow.velocity_y[j, i] * dudy
                
                # Pressure gradient
                dpdx = (flow.pressure[j, i+1] - flow.pressure[j, i-1]) / (2 * dx)
                
                # Viscous terms (simplified)
                d2udx2 = (flow.velocity_x[j, i+1] - 2*flow.velocity_x[j, i] + flow.velocity_x[j, i-1]) / dx**2
                d2udy2 = (flow.velocity_x[j+1, i] - 2*flow.velocity_x[j, i] + flow.velocity_x[j-1, i]) / dy**2
                
                viscous = mu[j, i] / flow.density[j, i] * (d2udx2 + d2udy2)
                
                # Source terms for hybrid motors (mass addition)
                source = 0.0
                if motor_type == 'hybrid' and j > ny * 0.7:  # Near fuel grain surface
                    fuel_regression_rate = 0.001  # m/s (simplified)
                    source = fuel_regression_rate * flow.density[j, i]
                
                # Update velocity
                du_dt = -convective - dpdx / flow.density[j, i] + viscous + source
                u_new[j, i] += relax['velocity'] * du_dt * 0.001  # Time step
        
        flow.velocity_x = u_new
        
        # Y-momentum equation (similar structure)
        v_new = flow.velocity_y.copy()
        for i in range(1, nx-1):
            for j in range(1, ny-1):
                # Convective terms
                dvdx = (flow.velocity_y[j, i+1] - flow.velocity_y[j, i-1]) / (2 * dx)
                dvdy = (flow.velocity_y[j+1, i] - flow.velocity_y[j-1, i]) / (2 * dy)
                
                convective = flow.velocity_x[j, i] * dvdx + flow.velocity_y[j, i] * dvdy
                
                # Pressure gradient
                dpdy = (flow.pressure[j+1, i] - flow.pressure[j-1, i]) / (2 * dy)
                
                # Viscous terms
                d2vdx2 = (flow.velocity_y[j, i+1] - 2*flow.velocity_y[j, i] + flow.velocity_y[j, i-1]) / dx**2
                d2vdy2 = (flow.velocity_y[j+1, i] - 2*flow.velocity_y[j, i] + flow.velocity_y[j-1, i]) / dy**2
                
                viscous = mu[j, i] / flow.density[j, i] * (d2vdx2 + d2vdy2)
                
                # Update velocity
                dv_dt = -convective - dpdy / flow.density[j, i] + viscous
                v_new[j, i] += relax['velocity'] * dv_dt * 0.001
        
        flow.velocity_y = v_new
    
    def _solve_energy_equation(self, grid: CFDGrid, flow: FlowProperties, 
                              bc: BoundaryConditions, relax: Dict):
        """Solve energy equation for temperature field"""
        
        nx, ny = grid.nx, grid.ny
        dx, dy = grid.dx, grid.dy
        
        # Specific heat at constant pressure
        cp = self.gamma * self.R / (self.gamma - 1)
        
        # Thermal conductivity (Prandtl number = 0.72)
        Pr = 0.72
        mu = self.mu_ref * (flow.temperature / self.T_ref)**1.5 * \
             ((self.T_ref + 110) / (flow.temperature + 110))
        k = cp * mu / Pr
        
        T_new = flow.temperature.copy()
        
        for i in range(1, nx-1):
            for j in range(1, ny-1):
                # Convective terms
                dTdx = (flow.temperature[j, i+1] - flow.temperature[j, i-1]) / (2 * dx)
                dTdy = (flow.temperature[j+1, i] - flow.temperature[j-1, i]) / (2 * dy)
                
                convective = flow.velocity_x[j, i] * dTdx + flow.velocity_y[j, i] * dTdy
                
                # Conductive terms
                d2Tdx2 = (flow.temperature[j, i+1] - 2*flow.temperature[j, i] + flow.temperature[j, i-1]) / dx**2
                d2Tdy2 = (flow.temperature[j+1, i] - 2*flow.temperature[j, i] + flow.temperature[j-1, i]) / dy**2
                
                conductive = k[j, i] / (flow.density[j, i] * cp) * (d2Tdx2 + d2Tdy2)
                
                # Viscous dissipation (simplified)
                viscous_dissipation = mu[j, i] / (flow.density[j, i] * cp) * \
                                    ((dTdx)**2 + (dTdy)**2) * 0.1
                
                # Update temperature
                dT_dt = -convective + conductive + viscous_dissipation
                T_new[j, i] += relax['temperature'] * dT_dt * 0.001
        
        flow.temperature = T_new
    
    def _apply_boundary_conditions(self, grid: CFDGrid, flow: FlowProperties, 
                                  bc: BoundaryConditions, motor_type: str):
        """Apply boundary conditions"""
        
        nx, ny = grid.nx, grid.ny
        
        # Inlet boundary (stagnation conditions)
        flow.pressure[:, 0] = bc.inlet_pressure
        flow.temperature[:, 0] = bc.inlet_temperature
        flow.velocity_x[:, 0] = np.maximum(10.0, flow.velocity_x[:, 0])  # Minimum inflow velocity
        flow.velocity_y[:, 0] = 0.0
        
        # Outlet boundary (constant pressure)
        flow.pressure[:, -1] = bc.outlet_pressure
        
        # Extrapolate other properties at outlet
        flow.velocity_x[:, -1] = 2*flow.velocity_x[:, -2] - flow.velocity_x[:, -3]
        flow.velocity_y[:, -1] = 2*flow.velocity_y[:, -2] - flow.velocity_y[:, -3]
        flow.temperature[:, -1] = 2*flow.temperature[:, -2] - flow.temperature[:, -3]
        
        # Centerline boundary (symmetry)
        flow.velocity_y[0, :] = 0.0  # No flow across centerline
        
        # Extrapolate other properties
        flow.pressure[0, :] = flow.pressure[1, :]
        flow.velocity_x[0, :] = flow.velocity_x[1, :]
        flow.temperature[0, :] = flow.temperature[1, :]
        
        # Wall boundary (no-slip condition)
        flow.velocity_x[-1, :] = 0.0
        flow.velocity_y[-1, :] = 0.0
        flow.temperature[-1, :] = bc.wall_temperature
        
        # Wall pressure (zero gradient)
        flow.pressure[-1, :] = flow.pressure[-2, :]
        
        # Hybrid motor specific: fuel grain surface
        if motor_type == 'hybrid':
            # Fuel grain surface is approximately at 70% of radius
            grain_surface_idx = int(ny * 0.7)
            
            # Mass injection at grain surface
            injection_velocity = 0.01  # m/s (simplified regression rate)
            flow.velocity_y[grain_surface_idx, :] = injection_velocity
            
            # Temperature at grain surface
            flow.temperature[grain_surface_idx, :] = 800.0  # K (fuel pyrolysis temperature)
    
    def _post_process_results(self, grid: CFDGrid, flow: FlowProperties, 
                             bc: BoundaryConditions, geometry: Dict) -> Dict:
        """Post-process CFD results to extract performance metrics"""
        
        # Extract throat conditions
        throat_x_idx = int(grid.nx * 0.85)  # Approximate throat location
        throat_conditions = {
            'pressure': np.mean(flow.pressure[:, throat_x_idx]),
            'temperature': np.mean(flow.temperature[:, throat_x_idx]),
            'velocity': np.mean(flow.velocity_x[:, throat_x_idx]),
            'mach_number': np.mean(flow.mach_number[:, throat_x_idx]),
            'density': np.mean(flow.density[:, throat_x_idx])
        }
        
        # Extract exit conditions
        exit_conditions = {
            'pressure': np.mean(flow.pressure[:, -1]),
            'temperature': np.mean(flow.temperature[:, -1]),
            'velocity': np.mean(flow.velocity_x[:, -1]),
            'mach_number': np.mean(flow.mach_number[:, -1]),
            'density': np.mean(flow.density[:, -1])
        }
        
        # Calculate performance parameters
        # Mass flow rate through throat
        throat_area = np.pi * (geometry.get('throat_radius', 0.01))**2
        mass_flow_rate = throat_conditions['density'] * throat_conditions['velocity'] * throat_area
        
        # Thrust calculation (simplified)
        exit_area = np.pi * (geometry.get('exit_radius', 0.025))**2
        thrust = mass_flow_rate * exit_conditions['velocity'] + \
                (exit_conditions['pressure'] - 101325) * exit_area
        
        # Specific impulse
        g0 = 9.81
        isp = thrust / (mass_flow_rate * g0) if mass_flow_rate > 0 else 0
        
        # Characteristic velocity
        c_star = throat_conditions['pressure'] * throat_area / mass_flow_rate if mass_flow_rate > 0 else 0
        
        # Thrust coefficient
        cf = thrust / (throat_conditions['pressure'] * throat_area) if throat_conditions['pressure'] > 0 else 0
        
        # Heat transfer analysis
        heat_transfer_metrics = self._calculate_heat_transfer(grid, flow, geometry)
        
        # Mixing efficiency (for hybrid motors)
        mixing_efficiency = self._calculate_mixing_efficiency(flow, grid)
        
        return {
            'throat_conditions': throat_conditions,
            'exit_conditions': exit_conditions,
            'performance': {
                'mass_flow_rate': mass_flow_rate,
                'thrust': thrust,
                'specific_impulse': isp,
                'characteristic_velocity': c_star,
                'thrust_coefficient': cf
            },
            'heat_transfer': heat_transfer_metrics,
            'mixing_efficiency': mixing_efficiency,
            'flow_quality': {
                'max_mach_number': np.max(flow.mach_number),
                'pressure_recovery': exit_conditions['pressure'] / throat_conditions['pressure'],
                'temperature_drop': (throat_conditions['temperature'] - exit_conditions['temperature']) / throat_conditions['temperature']
            }
        }
    
    def _calculate_heat_transfer(self, grid: CFDGrid, flow: FlowProperties, geometry: Dict) -> Dict:
        """Calculate heat transfer characteristics"""
        
        nx, ny = grid.nx, grid.ny
        
        # Wall heat flux calculation
        wall_heat_flux = np.zeros(nx)
        wall_temperature = flow.temperature[-1, :]  # Wall temperature
        gas_temperature = flow.temperature[-2, :]   # Gas temperature near wall
        
        # Simplified heat transfer coefficient
        reynolds_number = flow.density[-2, :] * flow.velocity_x[-2, :] * 0.01 / 1e-5  # Simplified
        nusselt_number = 0.023 * reynolds_number**0.8 * 0.72**0.4  # Dittus-Boelter
        
        thermal_conductivity = 0.05  # W/m/K (approximate for combustion gases)
        h = nusselt_number * thermal_conductivity / 0.01  # Heat transfer coefficient
        
        wall_heat_flux = h * (gas_temperature - wall_temperature)
        
        # Total heat transfer rate
        perimeter = 2 * np.pi * grid.Y[-1, :]  # Wall perimeter at each x-location
        dx_array = np.diff(grid.x[0, :])
        dx_array = np.append(dx_array, dx_array[-1])
        
        total_heat_rate = np.sum(wall_heat_flux * perimeter * dx_array)
        
        return {
            'wall_heat_flux': wall_heat_flux,
            'max_heat_flux': np.max(wall_heat_flux),
            'avg_heat_flux': np.mean(wall_heat_flux),
            'total_heat_rate': total_heat_rate,
            'max_wall_temperature': np.max(wall_temperature),
            'heat_transfer_coefficient': h
        }
    
    def _calculate_mixing_efficiency(self, flow: FlowProperties, grid: CFDGrid) -> float:
        """Calculate mixing efficiency for hybrid motors"""
        
        # Simplified mixing efficiency based on velocity profile uniformity
        nx, ny = grid.nx, grid.ny
        
        mixing_efficiencies = []
        
        for i in range(nx):
            velocity_profile = flow.velocity_x[:, i]
            mean_velocity = np.mean(velocity_profile)
            
            if mean_velocity > 0:
                # Calculate velocity uniformity
                velocity_std = np.std(velocity_profile)
                uniformity = 1.0 - velocity_std / mean_velocity
                mixing_efficiencies.append(max(0, min(1, uniformity)))
        
        return np.mean(mixing_efficiencies) if mixing_efficiencies else 0.8
    
    def _generate_visualizations(self, grid: CFDGrid, flow: FlowProperties, motor_type: str) -> Dict:
        """Generate CFD visualization data"""
        
        visualizations = {}
        
        # Pressure contour data
        visualizations['pressure_contour'] = {
            'x': grid.x.tolist(),
            'y': grid.y.tolist(),
            'z': flow.pressure.tolist(),
            'title': 'Pressure Distribution (Pa)',
            'colorscale': 'Viridis'
        }
        
        # Velocity magnitude contour
        velocity_mag = np.sqrt(flow.velocity_x**2 + flow.velocity_y**2)
        visualizations['velocity_contour'] = {
            'x': grid.x.tolist(),
            'y': grid.y.tolist(),
            'z': velocity_mag.tolist(),
            'title': 'Velocity Magnitude (m/s)',
            'colorscale': 'Jet'
        }
        
        # Temperature contour
        visualizations['temperature_contour'] = {
            'x': grid.x.tolist(),
            'y': grid.y.tolist(),
            'z': flow.temperature.tolist(),
            'title': 'Temperature Distribution (K)',
            'colorscale': 'Hot'
        }
        
        # Mach number contour
        visualizations['mach_contour'] = {
            'x': grid.x.tolist(),
            'y': grid.y.tolist(),
            'z': flow.mach_number.tolist(),
            'title': 'Mach Number Distribution',
            'colorscale': 'RdYlBu'
        }
        
        # Streamlines data
        # Simplified streamline calculation
        step = 4  # Skip points for cleaner visualization
        x_stream = grid.x[::step, ::step]
        y_stream = grid.y[::step, ::step]
        u_stream = flow.velocity_x[::step, ::step]
        v_stream = flow.velocity_y[::step, ::step]
        
        visualizations['streamlines'] = {
            'x': x_stream.tolist(),
            'y': y_stream.tolist(),
            'u': u_stream.tolist(),
            'v': v_stream.tolist(),
            'title': 'Flow Streamlines'
        }
        
        # Centerline properties
        centerline_idx = 0  # Centerline
        visualizations['centerline_properties'] = {
            'x': grid.x[centerline_idx, :].tolist(),
            'pressure': flow.pressure[centerline_idx, :].tolist(),
            'velocity': flow.velocity_x[centerline_idx, :].tolist(),
            'temperature': flow.temperature[centerline_idx, :].tolist(),
            'mach_number': flow.mach_number[centerline_idx, :].tolist()
        }
        
        # Wall properties
        wall_idx = -1  # Wall
        visualizations['wall_properties'] = {
            'x': grid.x[wall_idx, :].tolist(),
            'pressure': flow.pressure[wall_idx, :].tolist(),
            'temperature': flow.temperature[wall_idx, :].tolist(),
            'heat_flux': self._calculate_wall_heat_flux(grid, flow).tolist()
        }
        
        return visualizations
    
    def _calculate_wall_heat_flux(self, grid: CFDGrid, flow: FlowProperties) -> np.ndarray:
        """Calculate heat flux at wall"""
        nx = grid.nx
        dy = grid.dy
        
        # Temperature gradient at wall
        dT_dy_wall = (flow.temperature[-1, :] - flow.temperature[-2, :]) / dy
        
        # Thermal conductivity (simplified)
        k = 0.05  # W/m/K
        
        heat_flux = -k * dT_dy_wall
        
        return heat_flux
    
    def export_cfd_results(self, results: Dict, filename: str):
        """Export CFD results to file"""
        
        # Prepare data for export
        export_data = {
            'performance_metrics': results['performance_metrics'],
            'convergence_info': results['convergence_info'],
            'boundary_conditions': {
                'inlet_pressure': results['boundary_conditions'].inlet_pressure,
                'inlet_temperature': results['boundary_conditions'].inlet_temperature,
                'outlet_pressure': results['boundary_conditions'].outlet_pressure,
                'wall_temperature': results['boundary_conditions'].wall_temperature,
                'mass_flow_rate': results['boundary_conditions'].mass_flow_rate
            },
            'visualizations': results['visualizations']
        }
        
        with open(filename, 'w') as f:
            json.dump(export_data, f, indent=2)
    
    def validate_cfd_solution(self, results: Dict) -> Dict:
        """Validate CFD solution quality"""
        
        validation = {
            'convergence_achieved': results['convergence_info']['converged'],
            'mass_conservation_error': 0.0,  # Placeholder
            'energy_conservation_error': 0.0,  # Placeholder
            'solution_quality': 'UNKNOWN'
        }
        
        # Check convergence
        if not validation['convergence_achieved']:
            validation['solution_quality'] = 'POOR - NOT CONVERGED'
            return validation
        
        # Check physical reasonableness
        flow = results['flow_field']
        
        # Check for negative values
        if np.any(flow.pressure < 0) or np.any(flow.temperature < 0) or np.any(flow.density < 0):
            validation['solution_quality'] = 'POOR - NEGATIVE VALUES'
            return validation
        
        # Check Mach number range
        max_mach = np.max(flow.mach_number)
        if max_mach > 5.0:
            validation['solution_quality'] = 'QUESTIONABLE - HIGH MACH NUMBER'
        elif max_mach < 0.1:
            validation['solution_quality'] = 'QUESTIONABLE - LOW MACH NUMBER'
        else:
            validation['solution_quality'] = 'GOOD'
        
        return validation

# Create global CFD analyzer instance
cfd_analyzer = CFD2DAnalyzer()