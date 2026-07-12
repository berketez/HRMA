"""
3D CAD Visualization Module for Hybrid Rocket Motors
Combines motor assembly visualization (MotorCADDesigner) and
detailed engineering cross-section views (DetailedCADGenerator).

Both classes use Plotly for interactive 3D rendering.
MotorCADDesigner also uses trimesh for mesh-based geometry.
"""

import numpy as np
import trimesh

from hrma.engines.nozzle_design import sample_nozzle_inner_contour
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Dict, List, Tuple, Optional
import json
import base64
import math
from io import BytesIO


# =============================================================================
# MotorCADDesigner - 3D Motor Assembly (trimesh + Plotly)
# Originally from cad_design.py
# =============================================================================

def _real_nested(d, path):
    """İç içe dict'ten sonlu pozitif float çek (yoksa None)."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    try:
        v = float(cur)
    except (TypeError, ValueError):
        return None
    return v if (np.isfinite(v) and v > 0) else None


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

        # Yerel kopyada çalış: aşağıdaki motor_data.update(...) çağrıcının
        # motor_results sözlüğünü YERİNDE değiştiriyordu (chamber_length'i
        # kaba L* kuralıyla ezip /calculate yanıtını bozuyordu)
        motor_data = dict(motor_data)

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

            # ---- GERÇEK ÇÖZÜCÜ GEOMETRİSİ ----
            # Önce motor_results'taki hesaplanmış değerler; anahtar yoksa eski
            # kaba kurallara düşülür. (Eski davranış: port=0.4·D, L=f(L*) gibi
            # kurallar çözücü çıktısını YOK SAYIYORDU — STL çıktısı analizle
            # tutarsızdı.)
            def _real(key, lo, hi):
                v = motor_data.get(key)
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    return None
                return v if (np.isfinite(v) and lo < v < hi) else None

            total_impulse = motor_data.get('total_impulse', 10000)
            thrust = motor_data.get('thrust', 1000)
            burn_time = motor_data.get('burn_time', 10)
            l_star = motor_data.get('l_star', 1.0)

            chamber_length = _real('chamber_length', 0.02, 5.0)
            if chamber_length is None:
                # Eski L* kuralı (yalnız gerçek değer yoksa)
                throat_area = np.pi * (throat_diameter / 2) ** 2
                chamber_length = (l_star * throat_area) / (np.pi * (chamber_diameter / 2) ** 2)
                chamber_length = max(0.3, min(2.0, chamber_length))
            if motor_config.get('chamber_length_override'):
                chamber_length = motor_config['chamber_length_override'] / 1000.0

            # Nozul konturu: 2D kesit ve 3D görselleştirmeyle AYNI kaynak
            noz_pts_mm, noz_meta = sample_nozzle_inner_contour(motor_data)
            nozzle_length = noz_meta['z_exit'] / 1000.0

            # Duvar kalınlıkları
            struct = motor_data.get('structural_analysis') or {}
            wall_case = _real_nested(struct, ('chamber_analysis', 'recommended_thickness'))
            wall_case = (wall_case / 1000.0) if wall_case else max(0.004, 0.045 * chamber_diameter)
            wall_case = min(wall_case, 0.12 * chamber_diameter)
            noz_geo = motor_data.get('nozzle_geometry') or {}
            wall_noz = noz_geo.get('wall_thickness')
            wall_noz = (wall_noz / 1000.0) if wall_noz else max(0.003, 0.1 * throat_diameter)

            # Grain: gerçek port + gerçek boy
            port_diameter = _real('port_diameter_initial', 1e-4, 2.0) or chamber_diameter * 0.4
            grain_length = _real('grain_length', 0.005, 5.0) or (chamber_length - 0.05)
            grain_length = min(grain_length, 0.98 * chamber_length)
            liner = min(max(0.02 * chamber_diameter, 0.0015), 0.005)

            # Enjektör: gerçek orifis sayısı/çapı
            inj = motor_data.get('injector_design') or {}
            injector_orifices = inj.get('number_of_orifices')
            if injector_orifices:
                injector_orifices = int(round(injector_orifices))
            elif injector_config.get('n_holes_override'):
                injector_orifices = injector_config['n_holes_override']
            else:
                injector_orifices = 8
            injector_orifices = max(1, min(injector_orifices, 16))  # boolean kararlılığı
            ori_mm = inj.get('orifice_diameter_mm')
            if ori_mm:
                orifice_diameter = max(0.0005, min(0.01, ori_mm / 1000.0))
            else:
                mdot_ox = motor_data.get('mdot_ox', 1.0)
                inj_v = injector_config.get('injection_velocity', 30)
                a_tot = mdot_ox / (motor_data.get('oxidizer_density', 1200) * inj_v)
                orifice_diameter = max(0.001, min(0.01, 2 * (a_tot / injector_orifices / np.pi) ** 0.5))

            # Türetilen boyutları KOPYAYA yaz (çağıranın dict'i korunur)
            motor_data.update({
                'chamber_length': chamber_length,
                'nozzle_length': nozzle_length,
                'port_diameter': port_diameter,
                'injector_orifices': injector_orifices,
                'orifice_diameter': orifice_diameter,
                'design_config': design_config
            })

            # ---- Bileşen katıları (kapalı profil revolve — boolean'sız, watertight) ----
            print("CAD Debug - Creating chamber mesh...")
            cap_t = min(max(1.6 * wall_case, 0.008), 0.3 * chamber_diameter / 2 + 0.008)
            chamber_mesh = self._chamber_solid(chamber_diameter, chamber_length, wall_case, cap_t)

            print("CAD Debug - Creating nozzle mesh...")
            nozzle_mesh = self._nozzle_solid(noz_pts_mm, wall_noz)

            print("CAD Debug - Creating injector mesh...")
            injector_mesh = self._create_injector_head(chamber_diameter, motor_data)

            print("CAD Debug - Creating fuel grain mesh...")
            slack = max(0.004, chamber_length - grain_length)
            zg0 = 0.35 * slack
            fuel_grain_mesh = self._grain_solid(
                chamber_diameter / 2 - liner, port_diameter / 2, zg0, zg0 + grain_length
            )

            # ---- Yerleşim: z=0 kapak iç yüzü, kamara [0, L], nozul [L, L+Ln] ----
            assembly_meshes = []

            chamber_mesh.visual.face_colors = [200, 200, 200, 100]
            assembly_meshes.append(('Chamber', chamber_mesh))

            nozzle_mesh.apply_translation([0, 0, chamber_length])
            nozzle_mesh.visual.face_colors = [50, 50, 50, 255]
            assembly_meshes.append(('Nozzle', nozzle_mesh))

            # Enjektör plakası kamara içinde, kapak iç yüzüne yakın
            injector_mesh.apply_translation([0, 0, 0.006 + 0.015])
            injector_mesh.visual.face_colors = [150, 150, 150, 200]
            assembly_meshes.append(('Injector', injector_mesh))

            fuel_grain_mesh.visual.face_colors = [139, 69, 19, 150]
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


    @staticmethod
    def _fix_solid(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Revolve çıktısını STL'e uygun hale getir: dejenere üçgenleri at,
        normal yönünü dışa çevir (negatif hacim = ters sarım)."""
        mesh.update_faces(mesh.nondegenerate_faces())
        mesh.remove_unreferenced_vertices()
        mesh.merge_vertices()
        if mesh.volume < 0:
            mesh.invert()
        return mesh

    def _chamber_solid(self, diameter: float, length: float,
                       wall: float, cap_t: float) -> trimesh.Trimesh:
        """Baş kapak + silindirik tüp tek kapalı profil revolve katısı (m)."""
        r_in = diameter / 2
        r_out = r_in + wall
        profile = np.array([
            [0.0, -cap_t],
            [r_out, -cap_t],
            [r_out, length],
            [r_in, length],
            [r_in, 0.0],
            [0.0, 0.0],
            [0.0, -cap_t],
        ])
        return self._fix_solid(trimesh.creation.revolve(profile))

    def _nozzle_solid(self, inner_pts_mm, wall: float) -> trimesh.Trimesh:
        """Gerçek iç konturdan duvarlı nozul katısı.

        inner_pts_mm: sample_nozzle_inner_contour çıktısı [(z_mm, r_mm), ...]
        (z=0 konverjan başlangıcı). Dönen katı z=0'dan başlar (metre).
        """
        inner = [(r / 1000.0, z / 1000.0) for z, r in inner_pts_mm]
        outer = [(r + wall, z) for r, z in reversed(inner)]
        profile = np.array(inner + outer + [inner[0]])
        return self._fix_solid(trimesh.creation.revolve(profile))

    def _grain_solid(self, r_outer: float, r_port: float,
                     z0: float, z1: float) -> trimesh.Trimesh:
        """Silindirik delikli yakıt grain'i — halka profil revolve (m)."""
        r_port = min(max(r_port, 1e-4), r_outer - 5e-4)
        profile = np.array([
            [r_port, z0],
            [r_outer, z0],
            [r_outer, z1],
            [r_port, z1],
            [r_port, z0],
        ])
        return self._fix_solid(trimesh.creation.revolve(profile))

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
                'diameter': '+-0.1 mm',
                'length': '+-0.5 mm'
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
                    'density': '7.85 g/cm3',
                    'melting_point': '1400-1450 C',
                    'thermal_conductivity': '16.2 W/m K'
                },
                'heat_treatment': 'Solution annealed at 1050 C',
                'certification': 'ASME SA-240'
            },
            'nozzle_material': {
                'designation': 'High-Density Graphite',
                'properties': {
                    'compressive_strength': '137 MPa',
                    'tensile_strength': '41 MPa',
                    'density': '2.2 g/cm3',
                    'max_temperature': '3000 C',
                    'thermal_conductivity': '150 W/m K'
                },
                'grade': 'ATJ Graphite',
                'machining': 'CNC machined, diamond polished'
            },
            'injector_material': {
                'designation': 'AISI 316 Stainless Steel',
                'properties': {
                    'tensile_strength': '515-620 MPa',
                    'yield_strength': '205-310 MPa',
                    'density': '7.98 g/cm3',
                    'corrosion_resistance': 'Excellent',
                    'thermal_conductivity': '16.3 W/m K'
                },
                'finish': 'Electropolished Ra 0.4 um'
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
                'chamber_volume': chamber_volume * 1e6,  # cm3
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
            density = 7850  # kg/m3 for steel
            return volume * density

        elif component == 'nozzle':
            # Simplified nozzle volume calculation
            avg_radius = motor_data.get('throat_diameter', 0.02) / 2
            length = motor_data.get('nozzle_length', 0.15)
            volume = np.pi * avg_radius**2 * length * 0.7  # Account for hollow
            density = 2200  # kg/m3 for graphite
            return volume * density

        elif component == 'injector':
            radius = motor_data.get('chamber_diameter', 0.1) / 2
            thickness = 0.03
            volume = np.pi * radius**2 * thickness * 0.9  # Account for holes
            density = 7850  # kg/m3 for steel
            return volume * density

        return 1.0  # Default

    def export_stl_files(self, assembly_meshes: List, output_dir: str = "./cad_exports/"):
        """Export STL files for 3D printing/machining"""

        import os
        os.makedirs(output_dir, exist_ok=True)

        exported_files = []
        valid_meshes = []

        try:
            # First export individual components
            for name, mesh in assembly_meshes:
                if mesh is not None and hasattr(mesh, 'export'):
                    filename = f"{output_dir}/{name.lower().replace(' ', '_')}.stl"
                    try:
                        mesh.export(filename)
                        exported_files.append(filename)
                        valid_meshes.append(mesh)
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

            # Create combined motor assembly STL
            if valid_meshes:
                try:
                    import trimesh.util
                    combined_mesh = trimesh.util.concatenate(valid_meshes)
                    assembly_filename = f"{output_dir}/motor_assembly.stl"
                    combined_mesh.export(assembly_filename)
                    exported_files.append(assembly_filename)
                    print(f"Successfully exported combined assembly: {assembly_filename}")
                except Exception as e:
                    print(f"Error creating combined assembly: {str(e)}")
                    # Fallback to basic combined STL
                    assembly_filename = f"{output_dir}/motor_assembly.stl"
                    basic_assembly_stl = """solid motor_assembly
facet normal 0.0 0.0 1.0
outer loop
vertex -0.05 -0.05 0.0
vertex 0.05 -0.05 0.0
vertex 0.0 0.05 0.0
endloop
endfacet
endsolid motor_assembly"""
                    with open(assembly_filename, 'w') as f:
                        f.write(basic_assembly_stl)
                    exported_files.append(assembly_filename)

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

        # Ensure motor_assembly.stl is first in the list if it exists
        motor_assembly_files = [f for f in exported_files if 'motor_assembly' in f.lower()]
        other_files = [f for f in exported_files if 'motor_assembly' not in f.lower()]

        if motor_assembly_files:
            exported_files = motor_assembly_files + other_files

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


# =============================================================================
# DetailedCADGenerator - Engineering Cross-Section Views (Plotly)
# Originally from detailed_cad_generator.py
# =============================================================================

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
                # Convergent section (linear with 15 deg half-angle)
                progress = x / conv_length
                r = chamber_radius - (chamber_radius - throat_radius) * progress
            else:
                # Divergent section (linear with 12 deg half-angle)
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
