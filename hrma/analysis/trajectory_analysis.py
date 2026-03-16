"""
Trajectory Analysis Module for Hybrid Rocket Motors
Detailed flight trajectory calculations and analysis
"""

import numpy as np
import json
from scipy.integrate import solve_ivp
from typing import Dict, List, Tuple, Optional

class TrajectoryAnalyzer:
    """Complete trajectory analysis for hybrid rocket motors"""
    
    def __init__(self):
        # Earth parameters
        self.g0 = 9.80665  # Standard gravity (m/s²)
        self.R_earth = 6371000  # Earth radius (m)
        self.atmosphere_model = 'standard'  # 'standard' or 'custom'
        
        # Default vehicle parameters
        self.vehicle_mass_dry = 50  # kg
        self.vehicle_diameter = 0.15  # m
        self.drag_coefficient = 0.5
        self.vehicle_length = 2.0  # m
        
    def set_vehicle_parameters(self, mass_dry: float, diameter: float, 
                             drag_coefficient: float = 0.5, length: float = 2.0):
        """Set vehicle physical parameters"""
        self.vehicle_mass_dry = mass_dry
        self.vehicle_diameter = diameter
        self.drag_coefficient = drag_coefficient
        self.vehicle_length = length
        
    def calculate_trajectory(self, motor_data: Dict, launch_params: Dict) -> Dict:
        """
        Calculate complete trajectory from launch to landing
        
        Args:
            motor_data: Motor performance data from HybridRocketEngine
            launch_params: Launch parameters (angle, location, etc.)
            
        Returns:
            Complete trajectory data with analysis
        """
        
        # Extract motor parameters
        thrust = motor_data['thrust']  # N
        burn_time = motor_data['burn_time']  # s
        total_impulse = motor_data['total_impulse']  # N*s
        isp = motor_data['isp']  # s
        propellant_mass = motor_data['propellant_mass_total']  # kg
        
        # Extract launch parameters
        launch_angle = np.radians(launch_params.get('launch_angle', 85))  # degrees to radians
        launch_altitude = launch_params.get('launch_altitude', 0)  # m
        wind_speed = launch_params.get('wind_speed', 0)  # m/s
        wind_direction = np.radians(launch_params.get('wind_direction', 0))  # degrees to radians
        
        # Calculate vehicle parameters
        total_mass_loaded = self.vehicle_mass_dry + propellant_mass
        cross_sectional_area = np.pi * (self.vehicle_diameter / 2)**2
        
        # Phase 1: Powered flight (motor burning)
        powered_flight = self._calculate_powered_flight(
            thrust, burn_time, total_mass_loaded, propellant_mass,
            launch_angle, launch_altitude, cross_sectional_area
        )
        
        # Phase 2: Coasting flight (after burnout)
        coasting_flight = self._calculate_coasting_flight(
            powered_flight['final_state'], cross_sectional_area
        )
        
        # Phase 3: Descent with recovery
        descent_flight = self._calculate_descent_flight(
            coasting_flight['apogee_state'], cross_sectional_area
        )
        
        # Combine all phases
        trajectory_data = self._combine_flight_phases(
            powered_flight, coasting_flight, descent_flight
        )
        
        # Calculate performance metrics
        performance_metrics = self._calculate_performance_metrics(
            trajectory_data, motor_data, launch_params
        )
        
        return {
            'trajectory': trajectory_data,
            'performance': performance_metrics,
            'motor_data': motor_data,
            'vehicle_parameters': {
                'mass_dry': self.vehicle_mass_dry,
                'mass_loaded': total_mass_loaded,
                'diameter': self.vehicle_diameter,
                'drag_coefficient': self.drag_coefficient,
                'cross_sectional_area': cross_sectional_area
            }
        }
    
    def _calculate_powered_flight(self, thrust: float, burn_time: float, 
                                total_mass: float, propellant_mass: float,
                                launch_angle: float, launch_altitude: float,
                                cross_sectional_area: float) -> Dict:
        """Calculate powered flight phase (motor burning)"""
        
        def powered_flight_dynamics(t, y):
            """Dynamics during powered flight"""
            x, z, vx, vz, mass = y
            
            # Current altitude
            altitude = z
            
            # Atmospheric properties
            rho, g = self._get_atmospheric_properties(altitude)
            
            # Current velocity magnitude
            v_mag = np.sqrt(vx**2 + vz**2)
            
            # Mass flow rate (constant during burn)
            if t <= burn_time:
                mdot = propellant_mass / burn_time
                thrust_current = thrust
            else:
                mdot = 0
                thrust_current = 0
            
            # Thrust vector (along velocity direction initially, then vertical)
            if v_mag > 1:  # After initial acceleration
                thrust_direction_x = vx / v_mag
                thrust_direction_z = vz / v_mag
            else:  # Initial launch
                thrust_direction_x = np.sin(launch_angle)
                thrust_direction_z = np.cos(launch_angle)
            
            # Forces
            # Thrust force
            Fx_thrust = thrust_current * thrust_direction_x
            Fz_thrust = thrust_current * thrust_direction_z
            
            # Drag force
            drag_magnitude = 0.5 * rho * v_mag**2 * self.drag_coefficient * cross_sectional_area
            if v_mag > 0:
                Fx_drag = -drag_magnitude * (vx / v_mag)
                Fz_drag = -drag_magnitude * (vz / v_mag)
            else:
                Fx_drag = Fz_drag = 0
            
            # Gravity force
            Fz_gravity = -mass * g
            
            # Total forces
            Fx_total = Fx_thrust + Fx_drag
            Fz_total = Fz_thrust + Fz_drag + Fz_gravity
            
            # Accelerations
            ax = Fx_total / mass
            az = Fz_total / mass
            
            # Mass change
            dmdt = -mdot
            
            return [vx, vz, ax, az, dmdt]
        
        # Initial conditions
        y0 = [0, launch_altitude, 0, 0, total_mass]  # x, z, vx, vz, mass
        
        # Time span (extend beyond burn time for transition)
        t_span = (0, burn_time + 2)
        t_eval = np.linspace(0, burn_time + 2, int((burn_time + 2) * 50))
        
        # Solve ODE
        sol = solve_ivp(powered_flight_dynamics, t_span, y0, t_eval=t_eval, 
                       method='RK45', rtol=1e-8)
        
        return {
            'time': sol.t,
            'position_x': sol.y[0],
            'position_z': sol.y[1],
            'velocity_x': sol.y[2],
            'velocity_z': sol.y[3],
            'mass': sol.y[4],
            'final_state': [sol.y[0][-1], sol.y[1][-1], sol.y[2][-1], sol.y[3][-1], sol.y[4][-1]],
            'max_altitude_powered': np.max(sol.y[1]),
            'burnout_time': burn_time
        }
    
    def _calculate_coasting_flight(self, initial_state: List, cross_sectional_area: float) -> Dict:
        """Calculate coasting flight phase (ballistic trajectory to apogee)"""
        
        def coasting_dynamics(t, y):
            """Dynamics during coasting flight"""
            x, z, vx, vz = y
            
            # Atmospheric properties
            rho, g = self._get_atmospheric_properties(z)
            
            # Velocity magnitude
            v_mag = np.sqrt(vx**2 + vz**2)
            
            # Drag force
            mass = initial_state[4]  # Constant mass after burnout
            drag_magnitude = 0.5 * rho * v_mag**2 * self.drag_coefficient * cross_sectional_area
            
            if v_mag > 0:
                Fx_drag = -drag_magnitude * (vx / v_mag)
                Fz_drag = -drag_magnitude * (vz / v_mag)
            else:
                Fx_drag = Fz_drag = 0
            
            # Gravity force
            Fz_gravity = -mass * g
            
            # Accelerations
            ax = Fx_drag / mass
            az = (Fz_drag + Fz_gravity) / mass
            
            return [vx, vz, ax, az]
        
        # Initial conditions from powered flight
        y0 = initial_state[:4]  # x, z, vx, vz
        
        # Time span (until apogee - when vz becomes zero)
        def apogee_event(t, y):
            return y[3]  # vz = 0
        apogee_event.terminal = True
        apogee_event.direction = -1
        
        t_span = (0, 200)  # Maximum 200 seconds
        
        # Solve ODE
        sol = solve_ivp(coasting_dynamics, t_span, y0, events=apogee_event,
                       method='RK45', rtol=1e-8, dense_output=True)
        
        return {
            'time': sol.t,
            'position_x': sol.y[0],
            'position_z': sol.y[1],
            'velocity_x': sol.y[2],
            'velocity_z': sol.y[3],
            'apogee_time': sol.t[-1],
            'apogee_altitude': sol.y[1][-1],
            'apogee_state': [sol.y[0][-1], sol.y[1][-1], sol.y[2][-1], sol.y[3][-1], initial_state[4]]
        }
    
    def _calculate_descent_flight(self, apogee_state: List, cross_sectional_area: float) -> Dict:
        """Calculate descent flight phase (with recovery system)"""
        
        def descent_dynamics(t, y):
            """Dynamics during descent"""
            x, z, vx, vz = y
            
            # Atmospheric properties
            rho, g = self._get_atmospheric_properties(z)
            
            # Velocity magnitude
            v_mag = np.sqrt(vx**2 + vz**2)
            
            # Mass (constant during descent)
            mass = apogee_state[4]
            
            # Drag coefficient changes with recovery system deployment
            # Assume parachute deploys at apogee
            if t > 2:  # 2 seconds after apogee for deployment
                drag_coeff_current = 1.4  # Parachute deployed
                area_current = 2.0  # m² - parachute area
            else:
                drag_coeff_current = self.drag_coefficient
                area_current = cross_sectional_area
            
            # Drag force
            drag_magnitude = 0.5 * rho * v_mag**2 * drag_coeff_current * area_current
            
            if v_mag > 0:
                Fx_drag = -drag_magnitude * (vx / v_mag)
                Fz_drag = -drag_magnitude * (vz / v_mag)
            else:
                Fx_drag = Fz_drag = 0
            
            # Gravity force
            Fz_gravity = -mass * g
            
            # Accelerations
            ax = Fx_drag / mass
            az = (Fz_drag + Fz_gravity) / mass
            
            return [vx, vz, ax, az]
        
        # Initial conditions at apogee
        y0 = apogee_state[:4]
        
        # Ground impact event
        def ground_event(t, y):
            return y[1]  # z = 0 (ground level)
        ground_event.terminal = True
        ground_event.direction = -1
        
        t_span = (0, 500)  # Maximum 500 seconds
        
        # Solve ODE
        sol = solve_ivp(descent_dynamics, t_span, y0, events=ground_event,
                       method='RK45', rtol=1e-8)
        
        return {
            'time': sol.t,
            'position_x': sol.y[0],
            'position_z': sol.y[1],
            'velocity_x': sol.y[2],
            'velocity_z': sol.y[3],
            'landing_time': sol.t[-1],
            'landing_velocity': np.sqrt(sol.y[2][-1]**2 + sol.y[3][-1]**2),
            'landing_position_x': sol.y[0][-1]
        }
    
    def _combine_flight_phases(self, powered: Dict, coasting: Dict, descent: Dict) -> Dict:
        """Combine all flight phases into complete trajectory"""
        
        # Time offsets
        coasting_time_offset = powered['time'][-1]
        descent_time_offset = coasting_time_offset + coasting['time'][-1]
        
        # Combine time arrays
        time_powered = powered['time']
        time_coasting = coasting['time'] + coasting_time_offset
        time_descent = descent['time'] + descent_time_offset
        
        # Complete trajectory
        complete_time = np.concatenate([time_powered, time_coasting[1:], time_descent[1:]])
        complete_x = np.concatenate([powered['position_x'], coasting['position_x'][1:], descent['position_x'][1:]])
        complete_z = np.concatenate([powered['position_z'], coasting['position_z'][1:], descent['position_z'][1:]])
        complete_vx = np.concatenate([powered['velocity_x'], coasting['velocity_x'][1:], descent['velocity_x'][1:]])
        complete_vz = np.concatenate([powered['velocity_z'], coasting['velocity_z'][1:], descent['velocity_z'][1:]])
        
        # Calculate derived quantities
        complete_velocity = np.sqrt(complete_vx**2 + complete_vz**2)
        complete_acceleration = np.gradient(complete_velocity, complete_time)
        complete_altitude = complete_z
        
        return {
            'time': complete_time,
            'position_x': complete_x,
            'position_z': complete_z,
            'altitude': complete_altitude,
            'velocity_x': complete_vx,
            'velocity_z': complete_vz,
            'velocity_magnitude': complete_velocity,
            'acceleration': complete_acceleration,
            'phases': {
                'powered': powered,
                'coasting': coasting,
                'descent': descent
            }
        }
    
    def _calculate_performance_metrics(self, trajectory: Dict, motor_data: Dict, launch_params: Dict) -> Dict:
        """Calculate trajectory performance metrics"""
        
        # Basic trajectory metrics
        max_altitude = np.max(trajectory['altitude'])
        max_velocity = np.max(trajectory['velocity_magnitude'])
        max_acceleration = np.max(trajectory['acceleration'])
        total_flight_time = trajectory['time'][-1]
        range_distance = trajectory['position_x'][-1]
        
        # Motor performance metrics
        thrust_to_weight = motor_data['thrust'] / (self.vehicle_mass_dry * self.g0)
        total_impulse_to_weight = motor_data['total_impulse'] / (self.vehicle_mass_dry * self.g0)
        
        # Efficiency metrics
        burnout_altitude = trajectory['phases']['powered']['max_altitude_powered']
        burnout_velocity = np.sqrt(
            trajectory['phases']['powered']['velocity_x'][-1]**2 + 
            trajectory['phases']['powered']['velocity_z'][-1]**2
        )
        
        # Safety metrics
        landing_velocity = trajectory['phases']['descent']['landing_velocity']
        max_g_force = max_acceleration / self.g0
        
        return {
            'trajectory_metrics': {
                'max_altitude': max_altitude,
                'max_velocity': max_velocity,
                'max_acceleration': max_acceleration,
                'max_g_force': max_g_force,
                'total_flight_time': total_flight_time,
                'range_distance': range_distance,
                'landing_velocity': landing_velocity
            },
            'motor_performance': {
                'thrust_to_weight_ratio': thrust_to_weight,
                'total_impulse_to_weight': total_impulse_to_weight,
                'burnout_altitude': burnout_altitude,
                'burnout_velocity': burnout_velocity,
                'altitude_efficiency': burnout_altitude / max_altitude * 100  # %
            },
            'phase_breakdown': {
                'powered_flight_time': trajectory['phases']['powered']['burnout_time'],
                'coasting_time': trajectory['phases']['coasting']['apogee_time'],
                'descent_time': trajectory['phases']['descent']['landing_time'],
                'apogee_time': (trajectory['phases']['powered']['burnout_time'] + 
                              trajectory['phases']['coasting']['apogee_time'])
            }
        }
    
    def _get_atmospheric_properties(self, altitude: float) -> Tuple[float, float]:
        """Get atmospheric density and gravity at given altitude"""
        
        # Standard atmosphere model
        if altitude < 0:
            altitude = 0
        
        # Temperature and pressure models
        if altitude <= 11000:  # Troposphere
            T = 288.15 - 0.0065 * altitude  # K
            P = 101325 * (T / 288.15)**(self.g0 * 0.0289644 / (8.31432 * 0.0065))  # Pa
        elif altitude <= 20000:  # Lower stratosphere
            T = 216.65  # K
            P = 22632 * np.exp(-self.g0 * 0.0289644 * (altitude - 11000) / (8.31432 * T))  # Pa
        else:  # Simplified upper atmosphere
            T = 216.65  # K
            P = 22632 * np.exp(-self.g0 * 0.0289644 * (20000 - 11000) / (8.31432 * T))  # Pa
            P *= np.exp(-(altitude - 20000) / 8000)  # Exponential decay
        
        # Density from ideal gas law
        rho = P / (287.053 * T)  # kg/m³
        
        # Gravity variation with altitude
        g = self.g0 * (self.R_earth / (self.R_earth + altitude))**2
        
        return rho, g
    
    def create_trajectory_plots(self, trajectory_data: Dict) -> str:
        """Create comprehensive trajectory visualization plots"""
        
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        
        trajectory = trajectory_data['trajectory']
        performance = trajectory_data['performance']
        
        # Create subplots
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                'Trajectory Profile', 'Altitude vs Time',
                'Velocity Profile', 'Acceleration Profile', 
                'Flight Phases', 'Performance Summary'
            ),
            specs=[
                [{'type': 'scatter'}, {'type': 'scatter'}],
                [{'type': 'scatter'}, {'type': 'scatter'}],
                [{'type': 'scatter'}, {'type': 'indicator'}]
            ]
        )
        
        # 1. Trajectory profile (altitude vs range)
        fig.add_trace(
            go.Scatter(
                x=trajectory['position_x'] / 1000,  # Convert to km
                y=trajectory['altitude'] / 1000,  # Convert to km
                mode='lines',
                name='Flight Path',
                line=dict(color='blue', width=3),
                hovertemplate='Range: %{x:.2f} km<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=1
        )
        
        # Mark important points
        powered_phase = trajectory['phases']['powered']
        coasting_phase = trajectory['phases']['coasting']
        
        # Burnout point
        fig.add_trace(
            go.Scatter(
                x=[powered_phase['position_x'][-1] / 1000],
                y=[powered_phase['position_z'][-1] / 1000],
                mode='markers',
                name='Motor Burnout',
                marker=dict(color='red', size=10, symbol='circle'),
                hovertemplate='Burnout<br>Range: %{x:.2f} km<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=1
        )
        
        # Apogee point
        fig.add_trace(
            go.Scatter(
                x=[coasting_phase['position_x'][-1] / 1000],
                y=[coasting_phase['position_z'][-1] / 1000],
                mode='markers',
                name='Apogee',
                marker=dict(color='green', size=12, symbol='triangle-up'),
                hovertemplate='Apogee<br>Range: %{x:.2f} km<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=1
        )
        
        # 2. Altitude vs time
        fig.add_trace(
            go.Scatter(
                x=trajectory['time'],
                y=trajectory['altitude'] / 1000,  # Convert to km
                mode='lines',
                name='Altitude',
                line=dict(color='green', width=3),
                hovertemplate='Time: %{x:.1f} s<br>Altitude: %{y:.2f} km'
            ),
            row=1, col=2
        )
        
        # 3. Velocity profile
        fig.add_trace(
            go.Scatter(
                x=trajectory['time'],
                y=trajectory['velocity_magnitude'],
                mode='lines',
                name='Total Velocity',
                line=dict(color='red', width=3),
                hovertemplate='Time: %{x:.1f} s<br>Velocity: %{y:.1f} m/s'
            ),
            row=2, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=trajectory['time'],
                y=trajectory['velocity_z'],
                mode='lines',
                name='Vertical Velocity',
                line=dict(color='orange', width=2, dash='dash'),
                hovertemplate='Time: %{x:.1f} s<br>Vertical Velocity: %{y:.1f} m/s'
            ),
            row=2, col=1
        )
        
        # 4. Acceleration profile
        fig.add_trace(
            go.Scatter(
                x=trajectory['time'][1:],  # Skip first point for gradient
                y=trajectory['acceleration'][1:] / self.g0,  # Convert to g's
                mode='lines',
                name='Acceleration',
                line=dict(color='purple', width=3),
                hovertemplate='Time: %{x:.1f} s<br>Acceleration: %{y:.1f} g'
            ),
            row=2, col=2
        )
        
        # 5. Flight phases
        phase_times = [0, powered_phase['burnout_time'], 
                      powered_phase['burnout_time'] + coasting_phase['apogee_time'],
                      trajectory['time'][-1]]
        phase_names = ['Launch', 'Burnout', 'Apogee', 'Landing']
        phase_altitudes = [0, powered_phase['position_z'][-1] / 1000,
                          coasting_phase['position_z'][-1] / 1000, 0]
        
        fig.add_trace(
            go.Scatter(
                x=phase_times,
                y=phase_altitudes,
                mode='lines+markers',
                name='Flight Phases',
                line=dict(color='black', width=2),
                marker=dict(size=8, color='red'),
                text=phase_names,
                textposition='top center',
                hovertemplate='%{text}<br>Time: %{x:.1f} s<br>Altitude: %{y:.2f} km'
            ),
            row=3, col=1
        )
        
        # 6. Performance summary gauge
        max_altitude_km = performance['trajectory_metrics']['max_altitude'] / 1000
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=max_altitude_km,
                title={'text': "Maximum Altitude (km)"},
                domain={'x': [0, 1], 'y': [0, 1]},
                gauge={
                    'axis': {'range': [0, max(10, max_altitude_km * 1.2)]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [0, max_altitude_km * 0.5], 'color': "lightgray"},
                        {'range': [max_altitude_km * 0.5, max_altitude_km * 0.8], 'color': "yellow"},
                        {'range': [max_altitude_km * 0.8, max_altitude_km * 1.2], 'color': "green"}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': max_altitude_km
                    }
                }
            ),
            row=3, col=2
        )
        
        # Update layout
        fig.update_layout(
            title=dict(
                text="Complete Trajectory Analysis",
                x=0.5,
                font=dict(size=18, family='Arial')
            ),
            showlegend=True,
            height=900,
            width=1200,
            hovermode='closest'
        )
        
        # Update axes labels
        fig.update_xaxes(title_text="Range (km)", row=1, col=1)
        fig.update_yaxes(title_text="Altitude (km)", row=1, col=1)
        fig.update_xaxes(title_text="Time (s)", row=1, col=2)
        fig.update_yaxes(title_text="Altitude (km)", row=1, col=2)
        fig.update_xaxes(title_text="Time (s)", row=2, col=1)
        fig.update_yaxes(title_text="Velocity (m/s)", row=2, col=1)
        fig.update_xaxes(title_text="Time (s)", row=2, col=2)
        fig.update_yaxes(title_text="Acceleration (g)", row=2, col=2)
        fig.update_xaxes(title_text="Time (s)", row=3, col=1)
        fig.update_yaxes(title_text="Altitude (km)", row=3, col=1)
        
        return fig.to_json()