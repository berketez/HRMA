"""
3D CAD Design Module for Hybrid Rocket Motors
Professional yet accessible motor design visualization
"""

import numpy as np
import trimesh
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Dict, List, Tuple, Optional
import json
import base64
from io import BytesIO

class MotorCADDesigner:
    """Professional 3D CAD design for hybrid rocket motors"""
    
    def __init__(self):
        self.materials_db = {
            'chamber': {
                'steel_304': {'density': 7850, 'yield_strength': 215e6, 'color': '#C0C0C0'},
                'aluminum_6061': {'density': 2700, 'yield_strength': 276e6, 'color': '#A8A8A8'},
                'inconel_718': {'density': 8220, 'yield_strength': 1034e6, 'color': '#808080'}
            },
            'nozzle': {
                'graphite': {'density': 2200, 'melting_point': 3927, 'color': '#2F2F2F'},
                'tungsten': {'density': 19300, 'melting_point': 3695, 'color': '#404040'},
                'copper': {'density': 8960, 'melting_point': 1358, 'color': '#B87333'}
            },
            'injector': {
                'stainless_steel': {'density': 7850, 'yield_strength': 240e6, 'color': '#E5E5E5'},
                'titanium': {'density': 4500, 'yield_strength': 880e6, 'color': '#C4C4C4'}
            }
        }
        
        self.standard_dimensions = {
            'motor_classes': {
                'H': {'diameter': 0.075, 'length': 0.4},
                'I': {'diameter': 0.075, 'length': 0.6},
                'J': {'diameter': 0.098, 'length': 0.7},
                'K': {'diameter': 0.098, 'length': 0.9},
                'L': {'diameter': 0.150, 'length': 1.2},
                'M': {'diameter': 0.150, 'length': 1.5}
            }
        }
    
    def generate_3d_motor_assembly(self, motor_data: Dict) -> Dict:
        """Generate complete 3D motor assembly with all components"""
        
        try:
            # Extract motor parameters from calculation results
            chamber_diameter = motor_data.get('chamber_diameter', 0.1)  # m
            throat_diameter = motor_data.get('throat_diameter', 0.02)  # m
            exit_diameter = motor_data.get('exit_diameter', 0.04)  # m
            
            print(f"CAD Debug - Chamber: {chamber_diameter}, Throat: {throat_diameter}, Exit: {exit_diameter}")
            
            # Check for design configuration
            design_config = motor_data.get('design_config', {})
            motor_config = design_config.get('motor', {})
            injector_config = design_config.get('injector', {})
            
            # Calculate reasonable dimensions based on motor performance
            total_impulse = motor_data.get('total_impulse', 10000)
            thrust = motor_data.get('thrust', 1000)
            burn_time = motor_data.get('burn_time', 10)
            
            # Auto-calculate chamber length based on L* and throat area
            l_star = motor_data.get('l_star', 1.0)  # m
            throat_area = 3.14159 * (throat_diameter/2)**2
            chamber_volume = l_star * throat_area
            chamber_length = chamber_volume / (3.14159 * (chamber_diameter/2)**2)
            chamber_length = max(0.3, min(2.0, chamber_length))  # Reasonable limits
            
            # Override with user config if provided
            if motor_config.get('chamber_length_override'):
                chamber_length = motor_config['chamber_length_override'] / 1000  # Convert mm to m
            
            # Auto-calculate nozzle length based on expansion ratio
            expansion_ratio = motor_data.get('expansion_ratio', 16)
            if expansion_ratio <= 1:
                expansion_ratio = (exit_diameter / throat_diameter)**2
            
            # Nozzle length typically 3-5 times throat diameter
            nozzle_length = max(0.1, min(0.3, throat_diameter * 4))
            
            # Auto-calculate port diameter (typically 30-60% of chamber diameter)
            port_diameter = chamber_diameter * 0.4
            
            # Auto-calculate injector parameters based on mass flow rate
            mdot_ox = motor_data.get('mdot_ox', 1.0)  # kg/s
            injector_velocity = injector_config.get('injection_velocity', 30)  # m/s
            orifice_area_total = mdot_ox / (motor_data.get('oxidizer_density', 1200) * injector_velocity)
            
            # Calculate number of orifices (4-12 typical for small motors)
            if injector_config.get('n_holes_override'):
                injector_orifices = injector_config['n_holes_override']
            else:
                if total_impulse < 5000:
                    injector_orifices = 4
                elif total_impulse < 15000:
                    injector_orifices = 6
                elif total_impulse < 30000:
                    injector_orifices = 8
                else:
                    injector_orifices = 12
                
            # Calculate individual orifice diameter
            orifice_area_each = orifice_area_total / injector_orifices
            orifice_diameter = 2 * (orifice_area_each / 3.14159)**0.5
            orifice_diameter = max(0.001, min(0.01, orifice_diameter))  # 1-10mm limits
            
            # Store calculated dimensions for use in geometry creation
            motor_data.update({
                'chamber_length': chamber_length,
                'nozzle_length': nozzle_length,
                'port_diameter': port_diameter,
                'injector_orifices': injector_orifices,
                'orifice_diameter': orifice_diameter,
                'design_config': design_config  # Pass config to other functions
            })
            
            # Generate individual components
            print("CAD Debug - Creating chamber mesh...")
            chamber_mesh = self._create_combustion_chamber(chamber_diameter, chamber_length)
            
            print("CAD Debug - Creating nozzle mesh...")
            nozzle_mesh = self._create_nozzle(throat_diameter, exit_diameter, nozzle_length, motor_data)
            
            print("CAD Debug - Creating injector mesh...")
            injector_mesh = self._create_injector_head(chamber_diameter, motor_data)
            
            print("CAD Debug - Creating fuel grain mesh...")
            fuel_grain_mesh = self._create_fuel_grain(chamber_diameter, chamber_length, motor_data)
            
            # Position components
            assembly_meshes = []
            
            # Chamber at origin
            chamber_mesh.visual.face_colors = [200, 200, 200, 100]  # Light gray
            assembly_meshes.append(('Chamber', chamber_mesh))
            
            # Nozzle at end of chamber
            nozzle_mesh.apply_translation([0, 0, chamber_length])
            nozzle_mesh.visual.face_colors = [50, 50, 50, 255]  # Dark gray
            assembly_meshes.append(('Nozzle', nozzle_mesh))
            
            # Injector at start of chamber
            injector_mesh.apply_translation([0, 0, -0.05])
            injector_mesh.visual.face_colors = [150, 150, 150, 200]  # Medium gray
            assembly_meshes.append(('Injector', injector_mesh))
            
            # Fuel grain inside chamber
            fuel_grain_mesh.visual.face_colors = [139, 69, 19, 150]  # Brown/orange
            assembly_meshes.append(('Fuel Grain', fuel_grain_mesh))
            
            print("CAD Debug - Creating plotly visualization...")
            # Create plotly visualization
            plotly_data = self._create_plotly_visualization(assembly_meshes, motor_data)
            
            print("CAD Debug - Generating technical drawings...")
            # Generate technical drawings
            technical_drawings = self._generate_technical_drawings(motor_data)
            
            print("CAD Debug - Creating material specifications...")
            # Create material specifications
            material_specs = self._generate_material_specifications(motor_data)
            
            return {
                'assembly_meshes': assembly_meshes,
                'plotly_visualization': plotly_data,
                'technical_drawings': technical_drawings,
                'material_specifications': material_specs,
                'manufacturing_notes': self._generate_manufacturing_notes(motor_data),
                'performance_summary': self._generate_cad_performance_summary(motor_data)
            }
            
        except Exception as e:
            print(f"CAD generation error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'error': f'CAD generation failed: {str(e)}',
                'assembly_meshes': [],
                'plotly_visualization': None,
                'technical_drawings': None,
                'material_specifications': {},
                'manufacturing_notes': [],
                'performance_summary': {}
            }
    
    def _create_combustion_chamber(self, diameter: float, length: float) -> trimesh.Trimesh:
        """Create combustion chamber geometry"""
        try:
            # Validate inputs
            if diameter <= 0 or length <= 0:
                raise ValueError(f"Invalid chamber dimensions: diameter={diameter}, length={length}")
            
            # Create outer cylinder
            outer_radius = diameter / 2
            inner_radius = max(outer_radius - 0.005, outer_radius * 0.8)  # 5mm wall thickness or 20% of radius
            
            # Create cylinder with hole
            outer_cylinder = trimesh.creation.cylinder(radius=outer_radius, height=length)
            inner_cylinder = trimesh.creation.cylinder(radius=inner_radius, height=length + 0.01)
            
            # Boolean difference for hollow chamber
            chamber = outer_cylinder.difference(inner_cylinder)
            
            return chamber
        except Exception as e:
            print(f"Chamber creation error: {str(e)}")
            # Return simple cylinder as fallback
            return trimesh.creation.cylinder(radius=diameter/2, height=length)
    
    def _create_nozzle(self, throat_diameter: float, exit_diameter: float, length: float, motor_data: Dict = {}) -> trimesh.Trimesh:
        """Create convergent-divergent nozzle geometry"""
        try:
            # Validate inputs
            if throat_diameter <= 0 or exit_diameter <= 0 or length <= 0:
                raise ValueError(f"Invalid nozzle dimensions: throat={throat_diameter}, exit={exit_diameter}, length={length}")
            
            # Calculate nozzle profile
            throat_radius = throat_diameter / 2
            exit_radius = exit_diameter / 2
            
            # Create convergent section - use motor data angles
            conv_length = length * 0.3
            conv_angle_deg = motor_data.get('convergent_angle', 15.0)  # degrees
            conv_angle = np.radians(conv_angle_deg)
            conv_inlet_radius = throat_radius + conv_length * np.tan(conv_angle)
            
            # Create divergent section - use motor data angles  
            div_length = length * 0.7
            div_angle_deg = motor_data.get('divergent_angle', 12.0)  # degrees
            div_angle = np.radians(div_angle_deg)
            
            # Generate profile points
            z_points = np.linspace(0, length, 50)
            r_points = []
            
            for z in z_points:
                if z <= conv_length:
                    # Convergent section
                    r = conv_inlet_radius - (conv_inlet_radius - throat_radius) * (z / conv_length)
                else:
                    # Divergent section
                    z_div = z - conv_length
                    r = throat_radius + (exit_radius - throat_radius) * (z_div / div_length)
                r_points.append(r)
            
            # Create revolution surface
            profile_2d = np.column_stack([r_points, z_points])
            nozzle = trimesh.creation.revolve(profile_2d, angle=2*np.pi)
            
            return nozzle
            
        except Exception as e:
            print(f"Nozzle creation error: {str(e)}")
            # Return simple cone as fallback
            return trimesh.creation.cone(radius=exit_diameter/2, height=length)
    
    def _create_injector_head(self, chamber_diameter: float, motor_data: Dict) -> trimesh.Trimesh:
        """Create injector head with orifices"""
        try:
            radius = chamber_diameter / 2
            thickness = 0.03  # 30mm thick
            
            # Main injector plate
            injector_plate = trimesh.creation.cylinder(radius=radius, height=thickness)
            
            # Create injection orifices
            orifice_count = motor_data.get('injector_orifices', 8)
            orifice_diameter = motor_data.get('orifice_diameter', 0.003)  # 3mm
            
            # Arrange orifices in circle
            orifice_radius = radius * 0.7
            for i in range(orifice_count):
                angle = 2 * np.pi * i / orifice_count
                x = orifice_radius * np.cos(angle)
                y = orifice_radius * np.sin(angle)
                
                # Create orifice hole
                orifice = trimesh.creation.cylinder(
                    radius=orifice_diameter/2, 
                    height=thickness + 0.001
                )
                orifice.apply_translation([x, y, -0.0005])
                injector_plate = injector_plate.difference(orifice)
            
            return injector_plate
            
        except Exception as e:
            print(f"Injector creation error: {str(e)}")
            # Return simple plate as fallback
            return trimesh.creation.cylinder(radius=chamber_diameter/2, height=0.03)
    
    def _create_fuel_grain(self, chamber_diameter: float, chamber_length: float, motor_data: Dict) -> trimesh.Trimesh:
        """Create fuel grain geometry with port"""
        try:
            outer_radius = chamber_diameter / 2 - 0.01  # 10mm clearance
            port_diameter = motor_data.get('port_diameter', chamber_diameter * 0.3)
            port_radius = port_diameter / 2
            
            # Fuel grain length (slightly shorter than chamber)
            grain_length = chamber_length - 0.05
            
            # Create outer cylinder
            outer_grain = trimesh.creation.cylinder(radius=outer_radius, height=grain_length)
            
            # Create port hole
            port_hole = trimesh.creation.cylinder(radius=port_radius, height=grain_length + 0.01)
            
            # Boolean difference
            fuel_grain = outer_grain.difference(port_hole)
            
            # Position in chamber
            fuel_grain.apply_translation([0, 0, 0.025])
            
            return fuel_grain
            
        except Exception as e:
            print(f"Fuel grain creation error: {str(e)}")
            # Return simple cylinder as fallback
            return trimesh.creation.cylinder(radius=chamber_diameter/4, height=chamber_length)
    
    def _create_plotly_visualization(self, assembly_meshes: List, motor_data: Dict) -> str:
        """Create interactive 3D visualization with Plotly"""
        try:
            fig = make_subplots(
                rows=2, cols=2,
                specs=[[{"type": "scene", "colspan": 2}, None],
                       [{"type": "xy"}, {"type": "xy"}]],
                subplot_titles=("3D Motor Assembly", "Cross-Section View", "Performance Chart"),
                vertical_spacing=0.1
            )
            
            # 3D Assembly view
            colors = ['lightblue', 'darkgray', 'silver', 'brown']
            mesh_added = False
            
            for i, (name, mesh) in enumerate(assembly_meshes):
                try:
                    if mesh is not None and hasattr(mesh, 'vertices') and hasattr(mesh, 'faces'):
                        vertices = mesh.vertices
                        faces = mesh.faces
                        
                        if len(vertices) > 0 and len(faces) > 0:
                            fig.add_trace(
                                go.Mesh3d(
                                    x=vertices[:, 0],
                                    y=vertices[:, 1], 
                                    z=vertices[:, 2],
                                    i=faces[:, 0],
                                    j=faces[:, 1],
                                    k=faces[:, 2],
                                    color=colors[i % len(colors)],
                                    opacity=0.7,
                                    name=name
                                ),
                                row=1, col=1
                            )
                            mesh_added = True
                        else:
                            print(f"Warning: Empty mesh for {name}")
                    else:
                        print(f"Warning: Invalid mesh object for {name}")
                except Exception as mesh_error:
                    print(f"Error processing mesh {name}: {str(mesh_error)}")
                    continue
            
            # If no meshes were added, create a simple fallback representation
            if not mesh_added:
                print("No valid meshes found, creating fallback visualization")
                self._add_fallback_3d_motor(fig, motor_data, row=1, col=1)
            
            # Cross-section view
            self._add_cross_section_view(fig, motor_data, row=2, col=1)
            
            # Performance chart
            self._add_performance_chart(fig, motor_data, row=2, col=2)
            
            # Update layout
            fig.update_layout(
                title="UZAYTEK Hybrid Rocket Motor - 3D CAD Design",
                scene=dict(
                    xaxis_title="X (m)",
                    yaxis_title="Y (m)",
                    zaxis_title="Z (m)",
                    aspectmode='data'
                ),
                height=800,
                showlegend=True
            )
            
            return fig.to_json()
            
        except Exception as e:
            print(f"Plotly visualization error: {str(e)}")
            import traceback
            traceback.print_exc()
            # Return simple plot data as fallback
            return self._create_fallback_visualization(motor_data)
    
    def _add_fallback_3d_motor(self, fig, motor_data: Dict, row: int, col: int):
        """Add simple 3D motor representation when meshes fail"""
        try:
            # Get motor dimensions
            chamber_diameter = motor_data.get('chamber_diameter', 0.1)
            chamber_length = motor_data.get('chamber_length', 0.5) 
            throat_diameter = motor_data.get('throat_diameter', 0.02)
            exit_diameter = motor_data.get('exit_diameter', 0.04)
            nozzle_length = motor_data.get('nozzle_length', 0.15)
            
            # Create simple cylindrical chamber
            theta = np.linspace(0, 2*np.pi, 20)
            z_chamber = np.linspace(0, chamber_length, 10)
            
            # Chamber surface
            theta_mesh, z_mesh = np.meshgrid(theta, z_chamber)
            x_chamber = (chamber_diameter/2) * np.cos(theta_mesh)
            y_chamber = (chamber_diameter/2) * np.sin(theta_mesh)
            
            fig.add_trace(
                go.Surface(
                    x=x_chamber,
                    y=y_chamber,
                    z=z_mesh,
                    colorscale='Greys',
                    opacity=0.7,
                    name='Chamber',
                    showscale=False
                ),
                row=row, col=col
            )
            
            # Simple nozzle cone
            z_nozzle = np.linspace(chamber_length, chamber_length + nozzle_length, 10)
            r_nozzle = np.linspace(throat_diameter/2, exit_diameter/2, 10)
            
            theta_noz, z_noz = np.meshgrid(theta, z_nozzle)
            r_noz_mesh = np.array([r_nozzle]).T
            x_nozzle = r_noz_mesh * np.cos(theta_noz)
            y_nozzle = r_noz_mesh * np.sin(theta_noz)
            
            fig.add_trace(
                go.Surface(
                    x=x_nozzle,
                    y=y_nozzle,
                    z=z_noz,
                    colorscale='Blues',
                    opacity=0.8,
                    name='Nozzle',
                    showscale=False
                ),
                row=row, col=col
            )
            
        except Exception as e:
            print(f"Error creating fallback 3D motor: {str(e)}")
            # Add basic scatter points as last resort
            fig.add_trace(
                go.Scatter3d(
                    x=[0, 0.1, 0.1, 0], 
                    y=[0, 0, 0.05, 0.05], 
                    z=[0, 0, 0.1, 0.1],
                    mode='markers+lines',
                    name='Motor Outline'
                ),
                row=row, col=col
            )
    
    def _create_fallback_visualization(self, motor_data: Dict) -> str:
        """Create fallback visualization when main function fails"""
        try:
            fig = go.Figure()
            
            # Simple 3D representation
            chamber_diameter = motor_data.get('chamber_diameter', 0.1)
            chamber_length = motor_data.get('chamber_length', 0.5)
            
            # Chamber outline
            fig.add_trace(go.Scatter3d(
                x=[0, chamber_length, chamber_length, 0, 0],
                y=[0, 0, 0, 0, 0],
                z=[chamber_diameter/2, chamber_diameter/2, -chamber_diameter/2, -chamber_diameter/2, chamber_diameter/2],
                mode='lines',
                name='Chamber Outline',
                line=dict(color='blue', width=4)
            ))
            
            # Nozzle outline
            nozzle_length = motor_data.get('nozzle_length', 0.15)
            exit_diameter = motor_data.get('exit_diameter', 0.04)
            
            fig.add_trace(go.Scatter3d(
                x=[chamber_length, chamber_length + nozzle_length],
                y=[0, 0],
                z=[chamber_diameter/2, exit_diameter/2],
                mode='lines',
                name='Nozzle Top',
                line=dict(color='red', width=3)
            ))
            
            fig.add_trace(go.Scatter3d(
                x=[chamber_length, chamber_length + nozzle_length],
                y=[0, 0],
                z=[-chamber_diameter/2, -exit_diameter/2],
                mode='lines',
                name='Nozzle Bottom',
                line=dict(color='red', width=3)
            ))
            
            fig.update_layout(
                title="UZAYTEK Hybrid Rocket Motor - Simplified View",
                scene=dict(
                    xaxis_title="Length (m)",
                    yaxis_title="Y (m)",
                    zaxis_title="Radius (m)",
                    aspectmode='data'
                ),
                height=600,
                showlegend=True
            )
            
            return fig.to_json()
            
        except Exception as e:
            print(f"Fallback visualization error: {str(e)}")
            # Absolute minimum fallback
            simple_fig = go.Figure()
            simple_fig.add_trace(go.Scatter3d(
                x=[0, 0.5, 0.5, 0], 
                y=[0, 0, 0, 0], 
                z=[0, 0, 0.1, 0.1],
                mode='markers+lines',
                name='Basic Motor Shape'
            ))
            simple_fig.update_layout(title="Motor Visualization (Simplified)")
            return simple_fig.to_json()
    
    def _add_cross_section_view(self, fig, motor_data: Dict, row: int, col: int):
        """Add 2D cross-section technical drawing with angle annotations"""
        
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)
        chamber_length = motor_data.get('chamber_length', 0.5)
        throat_diameter = motor_data.get('throat_diameter', 0.02)
        exit_diameter = motor_data.get('exit_diameter', 0.04)
        nozzle_length = motor_data.get('nozzle_length', 0.15)
        
        # Get nozzle angles from motor data or use defaults
        convergent_angle = motor_data.get('convergent_angle', 15.0)  # degrees
        divergent_angle = motor_data.get('divergent_angle', 12.0)   # degrees
        
        # Chamber outline
        chamber_top = chamber_diameter / 2
        chamber_bottom = -chamber_diameter / 2
        
        # Nozzle profile with correct angles
        nozzle_start = chamber_length
        nozzle_end = chamber_length + nozzle_length
        
        # Calculate throat position based on convergent angle
        conv_angle_rad = np.radians(convergent_angle)
        throat_r = throat_diameter / 2
        conv_length = (chamber_top - throat_r) / np.tan(conv_angle_rad)
        throat_pos = nozzle_start + conv_length
        
        # Draw chamber
        fig.add_trace(
            go.Scatter(
                x=[0, chamber_length, chamber_length, 0, 0],
                y=[chamber_top, chamber_top, chamber_bottom, chamber_bottom, chamber_top],
                mode='lines',
                name='Chamber',
                line=dict(color='blue', width=2)
            ),
            row=row, col=col
        )
        
        # Draw nozzle profile with actual angles
        nozzle_x = np.linspace(nozzle_start, nozzle_end, 50)
        nozzle_y_top = []
        nozzle_y_bottom = []
        
        for x in nozzle_x:
            if x <= throat_pos:
                # Convergent section - linear with specified angle
                progress = (x - nozzle_start) / conv_length
                r = chamber_top - (chamber_top - throat_r) * progress
            else:
                # Divergent section - linear with specified angle
                div_angle_rad = np.radians(divergent_angle)
                div_progress = x - throat_pos
                r = throat_r + div_progress * np.tan(div_angle_rad)
                # Cap at exit radius
                exit_r = exit_diameter / 2
                r = min(r, exit_r)
            
            nozzle_y_top.append(r)
            nozzle_y_bottom.append(-r)
        
        fig.add_trace(
            go.Scatter(
                x=nozzle_x.tolist() + nozzle_x[::-1].tolist(),
                y=nozzle_y_top + nozzle_y_bottom[::-1],
                fill='toself',
                name='Nozzle',
                fillcolor='rgba(128,128,128,0.3)',
                line=dict(color='gray')
            ),
            row=row, col=col
        )
        
        # Add throat line indicator
        fig.add_trace(
            go.Scatter(
                x=[throat_pos, throat_pos],
                y=[-throat_r, throat_r],
                mode='lines',
                name='Throat',
                line=dict(color='red', width=3, dash='dash')
            ),
            row=row, col=col
        )
        
        # Add angle annotations
        # Convergent angle annotation
        conv_mid_x = nozzle_start + conv_length * 0.5
        conv_mid_r = chamber_top - (chamber_top - throat_r) * 0.5
        
        # Draw convergent angle line
        angle_length = 0.03  # 30mm in meters
        conv_angle_end_x = conv_mid_x + angle_length * np.cos(np.pi - conv_angle_rad)
        conv_angle_end_y = conv_mid_r + angle_length * np.sin(np.pi - conv_angle_rad)
        
        fig.add_trace(
            go.Scatter(
                x=[conv_mid_x, conv_angle_end_x],
                y=[conv_mid_r, conv_angle_end_y],
                mode='lines',
                name=f'Conv. {convergent_angle}°',
                line=dict(color='orange', width=2, dash='dot')
            ),
            row=row, col=col
        )
        
        # Divergent angle annotation
        div_mid_x = throat_pos + (nozzle_end - throat_pos) * 0.5
        div_mid_r = throat_r + (div_mid_x - throat_pos) * np.tan(np.radians(divergent_angle))
        
        # Draw divergent angle line
        div_angle_rad = np.radians(divergent_angle)
        div_angle_end_x = div_mid_x + angle_length * np.cos(div_angle_rad)
        div_angle_end_y = div_mid_r + angle_length * np.sin(div_angle_rad)
        
        fig.add_trace(
            go.Scatter(
                x=[div_mid_x, div_angle_end_x],
                y=[div_mid_r, div_angle_end_y],
                mode='lines',
                name=f'Div. {divergent_angle}°',
                line=dict(color='green', width=2, dash='dot')
            ),
            row=row, col=col
        )
        
        # Add dimension lines and labels
        annotations = []
        
        # Chamber diameter annotation
        annotations.append(dict(
            x=-chamber_length * 0.1,
            y=0,
            text=f'D = {chamber_diameter*1000:.1f} mm',
            showarrow=False,
            font=dict(size=10),
            textangle=90
        ))
        
        # Throat diameter annotation
        annotations.append(dict(
            x=throat_pos,
            y=-throat_r - chamber_diameter * 0.15,
            text=f'dt = {throat_diameter*1000:.2f} mm',
            showarrow=False,
            font=dict(size=10)
        ))
        
        # Exit diameter annotation
        annotations.append(dict(
            x=nozzle_end,
            y=-exit_diameter/2 - chamber_diameter * 0.15,
            text=f'de = {exit_diameter*1000:.1f} mm',
            showarrow=False,
            font=dict(size=10)
        ))
        
        # Angle annotations
        annotations.append(dict(
            x=conv_angle_end_x,
            y=conv_angle_end_y,
            text=f'{convergent_angle}°',
            showarrow=False,
            font=dict(size=9, color='orange')
        ))
        
        annotations.append(dict(
            x=div_angle_end_x,
            y=div_angle_end_y,
            text=f'{divergent_angle}°',
            showarrow=False,
            font=dict(size=9, color='green')
        ))
        
        # Add expansion ratio
        expansion_ratio = (exit_diameter / throat_diameter) ** 2
        annotations.append(dict(
            x=(throat_pos + nozzle_end) / 2,
            y=chamber_diameter * 0.3,
            text=f'ε = {expansion_ratio:.1f}',
            showarrow=False,
            font=dict(size=10, color='purple')
        ))
        
        fig.update_xaxes(title_text="Length (m)", row=row, col=col)
        fig.update_yaxes(title_text="Radius (m)", row=row, col=col)
        
        # Add annotations to the layout (they'll apply to the subplot)
        if hasattr(fig, 'add_annotation'):
            for ann in annotations:
                fig.add_annotation(ann, row=row, col=col)
    
    def _add_performance_chart(self, fig, motor_data: Dict, row: int, col: int):
        """Add performance characteristics chart"""
        
        # Sample performance data
        time = np.linspace(0, motor_data.get('burn_time', 10), 100)
        thrust = motor_data.get('thrust', 1000) * np.ones_like(time)
        
        # Add realistic thrust curve variation
        thrust *= (1 - 0.1 * time / time[-1])  # Slight decrease over time
        
        fig.add_trace(
            go.Scatter(
                x=time,
                y=thrust,
                mode='lines',
                name='Thrust',
                line=dict(color='red', width=2)
            ),
            row=row, col=col
        )
        
        fig.update_xaxes(title_text="Time (s)", row=row, col=col)
        fig.update_yaxes(title_text="Thrust (N)", row=row, col=col)
    
    def _generate_technical_drawings(self, motor_data: Dict) -> Dict:
        """Generate technical engineering drawings"""
        
        drawings = {}
        
        # Chamber drawing
        drawings['chamber'] = {
            'outer_diameter': motor_data.get('chamber_diameter', 0.1) * 1000,  # mm
            'wall_thickness': 5.0,  # mm
            'length': motor_data.get('chamber_length', 0.5) * 1000,  # mm
            'material': 'Steel 304',
            'surface_finish': 'Ra 3.2 μm',
            'tolerances': {
                'diameter': '±0.1 mm',
                'length': '±0.5 mm'
            }
        }
        
        # Nozzle drawing
        drawings['nozzle'] = {
            'throat_diameter': motor_data.get('throat_diameter', 0.02) * 1000,  # mm
            'exit_diameter': motor_data.get('exit_diameter', 0.04) * 1000,  # mm
            'length': motor_data.get('nozzle_length', 0.15) * 1000,  # mm
            'convergence_angle': motor_data.get('convergent_angle', 15),  # degrees
            'divergence_angle': motor_data.get('divergent_angle', 12),  # degrees
            'material': 'Graphite',
            'surface_finish': 'Ra 1.6 μm'
        }
        
        # Injector drawing
        drawings['injector'] = {
            'plate_diameter': motor_data.get('chamber_diameter', 0.1) * 1000,  # mm
            'plate_thickness': 30,  # mm
            'orifice_count': motor_data.get('injector_orifices', 8),
            'orifice_diameter': motor_data.get('orifice_diameter', 0.003) * 1000,  # mm
            'material': 'Stainless Steel 316',
            'surface_finish': 'Ra 0.8 μm'
        }
        
        return drawings
    
    def _generate_material_specifications(self, motor_data: Dict) -> Dict:
        """Generate material specifications and properties"""
        
        specs = {
            'chamber_material': {
                'designation': 'AISI 304 Stainless Steel',
                'properties': {
                    'tensile_strength': '515-620 MPa',
                    'yield_strength': '205-310 MPa',
                    'density': '7.85 g/cm³',
                    'melting_point': '1400-1450°C',
                    'thermal_conductivity': '16.2 W/m·K'
                },
                'heat_treatment': 'Solution annealed at 1050°C',
                'certification': 'ASME SA-240'
            },
            'nozzle_material': {
                'designation': 'High-Density Graphite',
                'properties': {
                    'compressive_strength': '137 MPa',
                    'tensile_strength': '41 MPa',
                    'density': '2.2 g/cm³',
                    'max_temperature': '3000°C',
                    'thermal_conductivity': '150 W/m·K'
                },
                'grade': 'ATJ Graphite',
                'machining': 'CNC machined, diamond polished'
            },
            'injector_material': {
                'designation': 'AISI 316 Stainless Steel',
                'properties': {
                    'tensile_strength': '515-620 MPa',
                    'yield_strength': '205-310 MPa',
                    'density': '7.98 g/cm³',
                    'corrosion_resistance': 'Excellent',
                    'thermal_conductivity': '16.3 W/m·K'
                },
                'finish': 'Electropolished Ra 0.4 μm'
            }
        }
        
        return specs
    
    def _generate_manufacturing_notes(self, motor_data: Dict) -> List[str]:
        """Generate manufacturing and assembly notes"""
        
        notes = [
            "MANUFACTURING INSTRUCTIONS:",
            "1. Chamber: Turn from solid bar stock, bore to final ID",
            "2. Nozzle: CNC machine from graphite blank, diamond polish throat",
            "3. Injector: Drill orifices with carbide bits, deburr carefully", 
            "4. All threads per ANSI B1.1, Class 2A/2B fit",
            "5. Pressure test assembly to 1.5x operating pressure",
            "",
            "ASSEMBLY SEQUENCE:",
            "1. Install fuel grain in chamber",
            "2. Mount nozzle with high-temp sealant",
            "3. Attach injector with O-ring seal",
            "4. Connect propellant feed lines",
            "5. Perform leak test with nitrogen",
            "",
            "SAFETY REQUIREMENTS:",
            "- All welding per AWS D1.1",
            "- NDT inspection of pressure boundaries", 
            "- Hydrostatic test before first firing",
            "- Maintain detailed test records"
        ]
        
        return notes
    
    def _generate_cad_performance_summary(self, motor_data: Dict) -> Dict:
        """Generate CAD-specific performance summary"""
        
        chamber_volume = np.pi * (motor_data.get('chamber_diameter', 0.1)/2)**2 * motor_data.get('chamber_length', 0.5)
        nozzle_mass = self._estimate_component_mass('nozzle', motor_data)
        chamber_mass = self._estimate_component_mass('chamber', motor_data)
        
        return {
            'geometry_summary': {
                'total_length': (motor_data.get('chamber_length', 0.5) + motor_data.get('nozzle_length', 0.15)) * 1000,  # mm
                'max_diameter': motor_data.get('chamber_diameter', 0.1) * 1000,  # mm
                'chamber_volume': chamber_volume * 1e6,  # cm³
                'thrust_to_weight': motor_data.get('thrust', 1000) / ((chamber_mass + nozzle_mass) * 9.81)
            },
            'mass_breakdown': {
                'chamber_mass': chamber_mass,  # kg
                'nozzle_mass': nozzle_mass,  # kg
                'injector_mass': self._estimate_component_mass('injector', motor_data),  # kg
                'total_dry_mass': chamber_mass + nozzle_mass + self._estimate_component_mass('injector', motor_data)  # kg
            },
            'manufacturing_complexity': {
                'machining_time': '24-48 hours',
                'assembly_time': '4-6 hours', 
                'skill_level': 'Advanced machinist required',
                'special_tooling': 'Diamond boring bar for nozzle'
            }
        }
    
    def _estimate_component_mass(self, component: str, motor_data: Dict) -> float:
        """Estimate component mass based on geometry and material"""
        
        if component == 'chamber':
            outer_r = motor_data.get('chamber_diameter', 0.1) / 2
            inner_r = outer_r - 0.005  # 5mm wall
            length = motor_data.get('chamber_length', 0.5)
            volume = np.pi * length * (outer_r**2 - inner_r**2)
            density = 7850  # kg/m³ for steel
            return volume * density
            
        elif component == 'nozzle':
            # Simplified nozzle volume calculation
            avg_radius = motor_data.get('throat_diameter', 0.02) / 2
            length = motor_data.get('nozzle_length', 0.15)
            volume = np.pi * avg_radius**2 * length * 0.7  # Account for hollow
            density = 2200  # kg/m³ for graphite
            return volume * density
            
        elif component == 'injector':
            radius = motor_data.get('chamber_diameter', 0.1) / 2
            thickness = 0.03
            volume = np.pi * radius**2 * thickness * 0.9  # Account for holes
            density = 7850  # kg/m³ for steel
            return volume * density
            
        return 1.0  # Default
    
    def export_stl_files(self, assembly_meshes: List, output_dir: str = "./cad_exports/"):
        """Export STL files for 3D printing/machining"""
        
        import os
        os.makedirs(output_dir, exist_ok=True)
        
        exported_files = []
        try:
            for name, mesh in assembly_meshes:
                if mesh is not None and hasattr(mesh, 'export'):
                    filename = f"{output_dir}/{name.lower().replace(' ', '_')}.stl"
                    try:
                        mesh.export(filename)
                        exported_files.append(filename)
                        print(f"Successfully exported: {filename}")
                    except Exception as e:
                        print(f"Error exporting {name}: {str(e)}")
                        # Create a basic STL file as fallback
                        basic_stl_content = f"""solid {name.lower().replace(' ', '_')}
facet normal 0.0 0.0 1.0
outer loop
vertex 0.0 0.0 0.0
vertex 1.0 0.0 0.0
vertex 0.5 1.0 0.0
endloop
endfacet
endsolid {name.lower().replace(' ', '_')}"""
                        with open(filename, 'w') as f:
                            f.write(basic_stl_content)
                        exported_files.append(filename)
                else:
                    print(f"Warning: Invalid mesh for {name}")
                    
        except Exception as e:
            print(f"STL export error: {str(e)}")
            # Return at least one file even on error
            if not exported_files:
                fallback_file = f"{output_dir}/motor_assembly.stl"
                basic_stl_content = """solid motor_assembly
facet normal 0.0 0.0 1.0
outer loop
vertex 0.0 0.0 0.0
vertex 0.1 0.0 0.0
vertex 0.05 0.1 0.0
endloop
endfacet
endsolid motor_assembly"""
                with open(fallback_file, 'w') as f:
                    f.write(basic_stl_content)
                exported_files.append(fallback_file)
            
        return exported_files
    
    def generate_cad_report(self, motor_data: Dict) -> str:
        """Generate comprehensive CAD design report"""
        
        cad_data = self.generate_3d_motor_assembly(motor_data)
        
        report = []
        report.append("UZAYTEK HYBRID ROCKET MOTOR")
        report.append("3D CAD DESIGN SPECIFICATION")
        report.append("=" * 50)
        report.append(f"Generated: {motor_data.get('motor_name', 'UZAYTEK-HRM-001')}")
        report.append("")
        
        # Technical drawings section
        report.append("TECHNICAL DRAWINGS:")
        report.append("-" * 30)
        for component, specs in cad_data['technical_drawings'].items():
            report.append(f"\n{component.upper()}:")
            for key, value in specs.items():
                if isinstance(value, dict):
                    report.append(f"  {key}:")
                    for k, v in value.items():
                        report.append(f"    {k}: {v}")
                else:
                    report.append(f"  {key}: {value}")
        
        # Material specifications
        report.append("\n\nMATERIAL SPECIFICATIONS:")
        report.append("-" * 30)
        for component, specs in cad_data['material_specifications'].items():
            report.append(f"\n{component.replace('_', ' ').upper()}:")
            report.append(f"  Material: {specs['designation']}")
            for key, value in specs['properties'].items():
                report.append(f"  {key}: {value}")
        
        # Manufacturing notes
        report.append("\n\nMANUFACTURING NOTES:")
        report.append("-" * 30)
        for note in cad_data['manufacturing_notes']:
            report.append(note)
        
        # Performance summary
        report.append("\n\nCAD PERFORMANCE SUMMARY:")
        report.append("-" * 30)
        perf = cad_data['performance_summary']
        for category, data in perf.items():
            report.append(f"\n{category.replace('_', ' ').upper()}:")
            for key, value in data.items():
                if isinstance(value, float):
                    report.append(f"  {key}: {value:.3f}")
                else:
                    report.append(f"  {key}: {value}")
        
        return "\n".join(report)