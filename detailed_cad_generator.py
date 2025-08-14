"""
Detailed Engineering CAD Generator for Rocket Motors
Creates realistic engineering-level 3D visualizations with cross-sections
"""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import math
from typing import Dict, List, Tuple


class DetailedCADGenerator:
    """Generate detailed engineering CAD visualizations for rocket motors"""
    
    def __init__(self):
        self.colors = {
            'chamber': '#2E4057',      # Dark blue-gray
            'nozzle': '#048A81',       # Teal
            'injector': '#C73E1D',     # Red
            'cooling': '#0077B6',      # Blue
            'fuel_feed': '#F77F00',    # Orange
            'ox_feed': '#FCBF49',      # Yellow
            'insulation': '#F8F9FA',   # Light gray
            'structure': '#495057',    # Gray
            'bolts': '#212529',        # Dark gray
            'seals': '#28A745',        # Green
            'sensors': '#6F42C1'       # Purple
        }
    
    def generate_liquid_motor_cad(self, motor_data: Dict) -> Dict:
        """Generate detailed liquid motor CAD with cross-section"""
        
        # Extract dimensions
        chamber_diameter = motor_data.get('chamber_diameter', 100) / 1000  # Convert to meters
        chamber_length = motor_data.get('chamber_length', 200) / 1000
        throat_diameter = motor_data.get('throat_diameter', 50) / 1000
        exit_diameter = motor_data.get('exit_diameter', 80) / 1000
        nozzle_length = motor_data.get('nozzle_length', 150) / 1000
        
        # Create dual view: External + Cross-section
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('External View', 'Cross-Section View'),
            specs=[[{'type': 'scatter3d'}, {'type': 'scatter3d'}]],
            horizontal_spacing=0.05
        )
        
        # Generate external view components
        external_traces = self._create_external_components(
            chamber_diameter, chamber_length, throat_diameter, 
            exit_diameter, nozzle_length, motor_data
        )
        
        # Generate cross-section components
        cross_section_traces = self._create_cross_section_components(
            chamber_diameter, chamber_length, throat_diameter,
            exit_diameter, nozzle_length, motor_data
        )
        
        # Add external view traces
        for trace in external_traces:
            fig.add_trace(trace, row=1, col=1)
        
        # Add cross-section traces
        for trace in cross_section_traces:
            fig.add_trace(trace, row=1, col=2)
        
        # Update layout
        fig.update_layout(
            title={
                'text': f'Engineering CAD: {motor_data.get("motor_name", "Liquid Motor")}',
                'x': 0.5,
                'font': {'size': 16}
            },
            scene=dict(
                xaxis_title='Length (m)',
                yaxis_title='Width (m)', 
                zaxis_title='Height (m)',
                camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
                aspectmode='cube'
            ),
            scene2=dict(
                xaxis_title='Length (m)',
                yaxis_title='Radius (m)',
                zaxis_title='Height (m)', 
                camera=dict(eye=dict(x=0.1, y=1.8, z=1.2)),
                aspectmode='cube'
            ),
            showlegend=True,
            width=1400,
            height=700
        )
        
        return {
            'plot_json': fig.to_json(),
            'component_details': self._get_component_details(motor_data),
            'dimensions': {
                'chamber_diameter': chamber_diameter * 1000,
                'chamber_length': chamber_length * 1000,
                'throat_diameter': throat_diameter * 1000,
                'exit_diameter': exit_diameter * 1000,
                'nozzle_length': nozzle_length * 1000
            }
        }
    
    def _create_external_components(self, chamber_dia, chamber_len, throat_dia, 
                                  exit_dia, nozzle_len, motor_data) -> List:
        """Create external view components"""
        traces = []
        
        # Main chamber body
        chamber_mesh = self._create_cylinder_mesh(
            center=(0, 0, 0),
            radius=chamber_dia/2,
            height=chamber_len,
            color=self.colors['chamber'],
            name='Chamber Body'
        )
        traces.append(chamber_mesh)
        
        # Injector head
        injector_thickness = 0.05
        injector_mesh = self._create_cylinder_mesh(
            center=(-injector_thickness/2, 0, 0),
            radius=chamber_dia/2 + 0.01,
            height=injector_thickness,
            color=self.colors['injector'],
            name='Injector Head'
        )
        traces.append(injector_mesh)
        
        # Nozzle
        nozzle_mesh = self._create_nozzle_mesh(
            start_pos=(chamber_len, 0, 0),
            throat_radius=throat_dia/2,
            exit_radius=exit_dia/2,
            length=nozzle_len,
            color=self.colors['nozzle'],
            name='Nozzle',
            motor_data=motor_data
        )
        traces.append(nozzle_mesh)
        
        # Cooling jacket
        cooling_mesh = self._create_cylinder_mesh(
            center=(chamber_len/2, 0, 0),
            radius=chamber_dia/2 + 0.02,
            height=chamber_len * 0.8,
            color=self.colors['cooling'],
            opacity=0.3,
            name='Cooling Jacket'
        )
        traces.append(cooling_mesh)
        
        # Feed lines
        # Oxidizer feed (top)
        ox_feed = self._create_feed_line(
            start=(chamber_len * 0.3, chamber_dia/2 + 0.03, chamber_dia/2 + 0.05),
            end=(chamber_len * 0.3, chamber_dia/2 + 0.03, chamber_dia/2 + 0.15),
            radius=0.015,
            color=self.colors['ox_feed'],
            name='Oxidizer Feed'
        )
        traces.append(ox_feed)
        
        # Fuel feed (side)
        fuel_feed = self._create_feed_line(
            start=(chamber_len * 0.7, chamber_dia/2 + 0.05, 0),
            end=(chamber_len * 0.7, chamber_dia/2 + 0.15, 0),
            radius=0.012,
            color=self.colors['fuel_feed'],
            name='Fuel Feed'
        )
        traces.append(fuel_feed)
        
        # Mounting flanges
        flanges = self._create_mounting_flanges(chamber_dia, chamber_len)
        traces.extend(flanges)
        
        # Sensors and instrumentation
        sensors = self._create_sensors(chamber_dia, chamber_len)
        traces.extend(sensors)
        
        return traces
    
    def _create_cross_section_components(self, chamber_dia, chamber_len, throat_dia,
                                       exit_dia, nozzle_len, motor_data) -> List:
        """Create cross-section view showing internal components"""
        traces = []
        
        # Chamber wall cross-section
        wall_thickness = 0.008  # 8mm wall
        chamber_profile = self._create_chamber_cross_section(
            chamber_dia, chamber_len, wall_thickness
        )
        traces.append(chamber_profile)
        
        # Injector internal structure
        injector_internal = self._create_injector_cross_section(
            chamber_dia, motor_data
        )
        traces.extend(injector_internal)
        
        # Cooling channels
        cooling_channels = self._create_cooling_channels_cross_section(
            chamber_dia, chamber_len
        )
        traces.extend(cooling_channels)
        
        # Nozzle internal profile
        nozzle_profile = self._create_nozzle_cross_section(
            chamber_len, throat_dia, exit_dia, nozzle_len
        )
        traces.append(nozzle_profile)
        
        # Combustion chamber internal
        combustion_chamber = self._create_combustion_chamber_cross_section(
            chamber_dia, chamber_len
        )
        traces.append(combustion_chamber)
        
        # Flow visualization arrows
        flow_arrows = self._create_flow_arrows_cross_section(
            chamber_dia, chamber_len, nozzle_len
        )
        traces.extend(flow_arrows)
        
        return traces
    
    def _create_cylinder_mesh(self, center, radius, height, color, name, opacity=0.8):
        """Create a detailed cylinder mesh"""
        n_theta = 32
        n_z = 2
        
        theta = np.linspace(0, 2*np.pi, n_theta)
        z = np.linspace(-height/2, height/2, n_z)
        
        # Create mesh points
        x_cyl = []
        y_cyl = []
        z_cyl = []
        
        for zi in z:
            for th in theta:
                x_cyl.append(center[0] + zi)
                y_cyl.append(center[1] + radius * np.cos(th))
                z_cyl.append(center[2] + radius * np.sin(th))
        
        # Create faces
        i, j, k = [], [], []
        for iz in range(n_z - 1):
            for ith in range(n_theta - 1):
                # Current quad indices
                p1 = iz * n_theta + ith
                p2 = iz * n_theta + (ith + 1)
                p3 = (iz + 1) * n_theta + ith
                p4 = (iz + 1) * n_theta + (ith + 1)
                
                # Two triangles per quad
                i.extend([p1, p2, p1])
                j.extend([p2, p4, p3])
                k.extend([p3, p3, p4])
        
        return go.Mesh3d(
            x=x_cyl, y=y_cyl, z=z_cyl,
            i=i, j=j, k=k,
            color=color,
            opacity=opacity,
            name=name,
            showlegend=True
        )
    
    def _create_nozzle_mesh(self, start_pos, throat_radius, exit_radius, length, color, name, motor_data=None):
        """Create detailed nozzle with convergent-divergent profile and angles"""
        n_points = 50
        
        # Nozzle geometry with proper angles
        conv_length = length * 0.3  # 30% convergent
        div_length = length * 0.7   # 70% divergent
        
        # Angles for nozzle sections - use calculated values from motor data
        if motor_data:
            conv_angle = motor_data.get('convergent_angle', 15.0)  # degrees (convergent half-angle)
            div_angle = motor_data.get('divergent_angle', 12.0)   # degrees (divergent half-angle)
            
            # Override with nozzle design data if available
            nozzle_data = motor_data.get('nozzle_design', {})
            if 'convergence_angle' in nozzle_data:
                conv_angle = nozzle_data['convergence_angle']
            if 'divergence_angle' in nozzle_data:
                div_angle = nozzle_data['divergence_angle']
        else:
            # Default values when no motor data provided
            conv_angle = 15.0
            div_angle = 12.0
        
        # Calculate chamber radius from convergent angle
        chamber_radius = throat_radius + conv_length * math.tan(math.radians(conv_angle))
        
        # Nozzle profile with linear convergent and divergent sections
        x_profile = np.linspace(0, length, n_points)
        
        r_profile = []
        for x in x_profile:
            if x < conv_length:
                # Convergent section (linear with 15° half-angle)
                progress = x / conv_length
                r = chamber_radius - (chamber_radius - throat_radius) * progress
            else:
                # Divergent section (linear with 12° half-angle)
                div_x = x - conv_length
                r = throat_radius + div_x * math.tan(math.radians(div_angle))
            r_profile.append(r)
        
        # Create revolution surface
        theta = np.linspace(0, 2*np.pi, 32)
        x_noz, y_noz, z_noz = [], [], []
        
        for i, x in enumerate(x_profile):
            for th in theta:
                x_noz.append(start_pos[0] + x)
                y_noz.append(start_pos[1] + r_profile[i] * np.cos(th))
                z_noz.append(start_pos[2] + r_profile[i] * np.sin(th))
        
        return go.Scatter3d(
            x=x_noz, y=y_noz, z=z_noz,
            mode='markers',
            marker=dict(size=2, color=color),
            name=name,
            showlegend=True
        )
    
    def _create_injector_cross_section(self, chamber_dia, motor_data):
        """Create detailed injector cross-section"""
        traces = []
        
        # Get injector pattern from motor data
        injector_type = motor_data.get('injector_type', 'unlike_impinging')
        hole_count = motor_data.get('injector_holes', 24)
        
        # Create injector holes pattern
        if injector_type == 'unlike_impinging':
            holes = self._create_impinging_injector_holes(chamber_dia, hole_count)
        else:
            holes = self._create_coaxial_injector_holes(chamber_dia, hole_count)
        
        traces.extend(holes)
        
        # Injector face
        injector_face = go.Scatter3d(
            x=[-0.02, -0.02, -0.02, -0.02],
            y=[-chamber_dia/2, chamber_dia/2, chamber_dia/2, -chamber_dia/2],
            z=[-chamber_dia/2, -chamber_dia/2, chamber_dia/2, chamber_dia/2],
            mode='lines',
            line=dict(color=self.colors['injector'], width=6),
            name='Injector Face',
            showlegend=True
        )
        traces.append(injector_face)
        
        return traces
    
    def _create_cooling_channels_cross_section(self, chamber_dia, chamber_len):
        """Create cooling channel cross-section"""
        traces = []
        
        # Cooling channels around chamber wall
        n_channels = 24
        channel_depth = 0.003  # 3mm deep
        
        for i in range(n_channels):
            angle = i * 2 * np.pi / n_channels
            
            # Channel path
            x_channel = np.linspace(0, chamber_len, 20)
            y_channel = [(chamber_dia/2 - channel_depth) * np.cos(angle)] * 20
            z_channel = [(chamber_dia/2 - channel_depth) * np.sin(angle)] * 20
            
            channel = go.Scatter3d(
                x=x_channel,
                y=y_channel, 
                z=z_channel,
                mode='lines',
                line=dict(color=self.colors['cooling'], width=3),
                name='Cooling Channel' if i == 0 else None,
                showlegend=True if i == 0 else False
            )
            traces.append(channel)
        
        return traces
    
    def _create_chamber_cross_section(self, chamber_dia, chamber_len, wall_thickness):
        """Create chamber wall cross-section"""
        
        # Outer wall
        x_outer = [0, chamber_len, chamber_len, 0, 0]
        y_outer = [chamber_dia/2 + wall_thickness, chamber_dia/2 + wall_thickness, 
                  -chamber_dia/2 - wall_thickness, -chamber_dia/2 - wall_thickness, 
                  chamber_dia/2 + wall_thickness]
        z_outer = [0, 0, 0, 0, 0]
        
        # Inner wall
        x_inner = [0, chamber_len, chamber_len, 0, 0]
        y_inner = [chamber_dia/2, chamber_dia/2, -chamber_dia/2, -chamber_dia/2, chamber_dia/2]
        z_inner = [0, 0, 0, 0, 0]
        
        return go.Scatter3d(
            x=x_outer + x_inner,
            y=y_outer + y_inner,
            z=z_outer + z_inner,
            mode='lines',
            line=dict(color=self.colors['chamber'], width=4),
            name='Chamber Wall',
            showlegend=True
        )
    
    def _create_mounting_flanges(self, chamber_dia, chamber_len):
        """Create mounting flanges and bolt patterns"""
        traces = []
        
        # Forward flange
        forward_flange = self._create_flange(
            position=(-0.03, 0, 0),
            inner_dia=chamber_dia,
            outer_dia=chamber_dia + 0.04,
            thickness=0.02,
            bolt_count=8
        )
        traces.extend(forward_flange)
        
        # Aft flange  
        aft_flange = self._create_flange(
            position=(chamber_len + 0.01, 0, 0),
            inner_dia=chamber_dia,
            outer_dia=chamber_dia + 0.04,
            thickness=0.02,
            bolt_count=8
        )
        traces.extend(aft_flange)
        
        return traces
    
    def _create_sensors(self, chamber_dia, chamber_len):
        """Create sensor and instrumentation components"""
        traces = []
        
        # Pressure transducers
        pressure_sensors = [
            {'pos': (chamber_len * 0.2, chamber_dia/2 + 0.01, chamber_dia/4), 'name': 'Chamber Pressure'},
            {'pos': (chamber_len * 0.8, chamber_dia/2 + 0.01, -chamber_dia/4), 'name': 'Injector Pressure'}
        ]
        
        for sensor in pressure_sensors:
            sensor_trace = go.Scatter3d(
                x=[sensor['pos'][0]],
                y=[sensor['pos'][1]],
                z=[sensor['pos'][2]],
                mode='markers',
                marker=dict(size=8, color=self.colors['sensors'], symbol='diamond'),
                name=sensor['name'],
                showlegend=True
            )
            traces.append(sensor_trace)
        
        return traces
    
    def _get_component_details(self, motor_data) -> Dict:
        """Get detailed component specifications"""
        return {
            'injector': {
                'type': motor_data.get('injector_type', 'Unlike Impinging'),
                'hole_count': motor_data.get('injector_holes', 24),
                'pressure_drop': f"{motor_data.get('injector_dp', 15)} bar"
            },
            'cooling': {
                'type': 'Regenerative',
                'channel_count': 24,
                'coolant': motor_data.get('fuel_type', 'RP-1')
            },
            'materials': {
                'chamber': 'Inconel 718',
                'nozzle': 'C-C Composite', 
                'injector': 'Stainless Steel 316L'
            },
            'performance': {
                'thrust': f"{motor_data.get('thrust', 5000)} N",
                'isp': f"{motor_data.get('isp', 320)} s",
                'chamber_pressure': f"{motor_data.get('chamber_pressure', 50)} bar"
            }
        }
    
    def generate_solid_motor_cad(self, motor_data: Dict) -> Dict:
        """Generate detailed solid motor CAD with grain geometry"""
        
        # Similar structure but for solid motor
        # Will implement grain patterns, inhibitor, case details
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('External View', 'Grain Cross-Section'), 
            specs=[[{'type': 'scatter3d'}, {'type': 'scatter3d'}]],
            horizontal_spacing=0.05
        )
        
        # Add solid motor specific components...
        # (Implementation would be similar but with grain geometry, inhibitors, etc.)
        
        return {
            'plot_json': fig.to_json(),
            'component_details': self._get_solid_component_details(motor_data)
        }
    
    def _get_solid_component_details(self, motor_data) -> Dict:
        """Get solid motor component details"""
        return {
            'grain': {
                'type': motor_data.get('grain_type', 'BATES'),
                'segments': motor_data.get('grain_count', 3),
                'inhibitor': 'Phenolic'
            },
            'case': {
                'material': 'Steel 4130',
                'thickness': '5mm',
                'factor_of_safety': 2.5
            }
        }
    
    def _create_impinging_injector_holes(self, chamber_dia, hole_count):
        """Create impinging injector holes pattern"""  
        traces = []
        
        # Create concentric rings of holes
        inner_ring = hole_count // 3
        middle_ring = hole_count // 3  
        outer_ring = hole_count - inner_ring - middle_ring
        
        rings = [
            (inner_ring, chamber_dia * 0.15),
            (middle_ring, chamber_dia * 0.25),
            (outer_ring, chamber_dia * 0.35)
        ]
        
        for holes_in_ring, radius in rings:
            for i in range(holes_in_ring):
                angle = i * 2 * np.pi / holes_in_ring
                x_hole = -0.015
                y_hole = radius * np.cos(angle)
                z_hole = radius * np.sin(angle)
                
                hole = go.Scatter3d(
                    x=[x_hole], y=[y_hole], z=[z_hole],
                    mode='markers',
                    marker=dict(size=4, color=self.colors['fuel_feed']),
                    name='Injector Hole' if len(traces) == 0 else None,
                    showlegend=True if len(traces) == 0 else False
                )
                traces.append(hole)
        
        return traces
    
    def _create_coaxial_injector_holes(self, chamber_dia, hole_count):
        """Create coaxial injector holes pattern"""
        traces = []
        
        # Coaxial elements in grid pattern
        rows = int(np.sqrt(hole_count))
        cols = hole_count // rows
        
        for i in range(rows):
            for j in range(cols):
                y_pos = (i - rows/2) * chamber_dia * 0.1
                z_pos = (j - cols/2) * chamber_dia * 0.1
                
                # Central fuel hole
                fuel_hole = go.Scatter3d(
                    x=[-0.015], y=[y_pos], z=[z_pos],
                    mode='markers',
                    marker=dict(size=3, color=self.colors['fuel_feed']),
                    name='Fuel Hole' if len(traces) == 0 else None,
                    showlegend=True if len(traces) == 0 else False
                )
                traces.append(fuel_hole)
                
                # Surrounding oxidizer holes
                for k in range(4):
                    angle = k * np.pi / 2
                    ox_y = y_pos + 0.005 * np.cos(angle)
                    ox_z = z_pos + 0.005 * np.sin(angle)
                    
                    ox_hole = go.Scatter3d(
                        x=[-0.015], y=[ox_y], z=[ox_z],
                        mode='markers', 
                        marker=dict(size=2, color=self.colors['ox_feed']),
                        name='Oxidizer Hole' if len(traces) == 1 else None,
                        showlegend=True if len(traces) == 1 else False
                    )
                    traces.append(ox_hole)
        
        return traces
    
    def _create_feed_line(self, start, end, radius, color, name):
        """Create a feed line pipe"""
        # Simple cylinder between two points
        direction = np.array(end) - np.array(start)
        length = np.linalg.norm(direction)
        
        # Create cylinder along line
        n_points = 20
        theta = np.linspace(0, 2*np.pi, n_points)
        
        x_line = np.linspace(start[0], end[0], 10)
        y_line, z_line = [], []
        
        for x in x_line:
            for th in theta:
                # Perpendicular to line direction
                y_line.append(start[1] + radius * np.cos(th))
                z_line.append(start[2] + radius * np.sin(th))
        
        return go.Scatter3d(
            x=x_line * len(theta),
            y=y_line,
            z=z_line,
            mode='markers',
            marker=dict(size=2, color=color),
            name=name,
            showlegend=True
        )
    
    def _create_flange(self, position, inner_dia, outer_dia, thickness, bolt_count):
        """Create mounting flange with bolt pattern"""
        traces = []
        
        # Flange body
        flange_body = self._create_cylinder_mesh(
            center=position,
            radius=outer_dia/2,
            height=thickness,
            color=self.colors['structure'],
            name='Flange'
        )
        traces.append(flange_body)
        
        # Bolt holes
        bolt_radius = (inner_dia + outer_dia) / 4
        for i in range(bolt_count):
            angle = i * 2 * np.pi / bolt_count
            bolt_y = position[1] + bolt_radius * np.cos(angle)
            bolt_z = position[2] + bolt_radius * np.sin(angle)
            
            bolt = go.Scatter3d(
                x=[position[0]],
                y=[bolt_y],
                z=[bolt_z],
                mode='markers',
                marker=dict(size=4, color=self.colors['bolts'], symbol='circle'),
                name='Bolt' if i == 0 else None,
                showlegend=True if i == 0 else False
            )
            traces.append(bolt)
        
        return traces
    
    def _create_nozzle_cross_section(self, chamber_len, throat_dia, exit_dia, nozzle_len):
        """Create nozzle cross-section profile"""
        n_points = 50
        x_profile = np.linspace(chamber_len, chamber_len + nozzle_len, n_points)
        
        # Bell nozzle profile
        r_profile = []
        for x in x_profile:
            progress = (x - chamber_len) / nozzle_len
            if progress < 0.3:  # Convergent
                r = throat_dia/2 + (exit_dia/2 - throat_dia/2) * (1 - ((1-progress)/0.3)**2)
            else:  # Divergent
                div_progress = (progress - 0.3) / 0.7
                r = throat_dia/2 + (exit_dia/2 - throat_dia/2) * (div_progress**0.6)
            r_profile.append(r)
        
        # Upper and lower profiles
        return go.Scatter3d(
            x=list(x_profile) + list(x_profile),
            y=r_profile + [-r for r in r_profile],
            z=[0] * len(r_profile) * 2,
            mode='lines',
            line=dict(color=self.colors['nozzle'], width=4),
            name='Nozzle Profile',
            showlegend=True
        )
    
    def _create_combustion_chamber_cross_section(self, chamber_dia, chamber_len):
        """Create combustion chamber internal view"""
        return go.Scatter3d(
            x=[0, chamber_len, chamber_len, 0, 0],
            y=[chamber_dia/2, chamber_dia/2, -chamber_dia/2, -chamber_dia/2, chamber_dia/2],
            z=[0, 0, 0, 0, 0],
            mode='lines',
            line=dict(color='rgba(255, 100, 0, 0.5)', width=3, dash='dash'),
            name='Combustion Chamber',
            showlegend=True
        )
    
    def _create_flow_arrows_cross_section(self, chamber_dia, chamber_len, nozzle_len):
        """Create flow direction arrows"""
        traces = []
        
        # Flow arrows in chamber
        n_arrows = 5
        for i in range(n_arrows):
            x_pos = chamber_len * (i + 1) / (n_arrows + 1)
            
            arrow = go.Scatter3d(
                x=[x_pos, x_pos + 0.02],
                y=[0, 0],
                z=[0, 0],
                mode='lines+markers',
                line=dict(color='red', width=4),
                marker=dict(size=[2, 6], symbol=['circle', 'diamond']),
                name='Flow Direction' if i == 0 else None,
                showlegend=True if i == 0 else False
            )
            traces.append(arrow)
        
        return traces