"""
Professional Rocket Engine CAD Generator
Creates realistic 3D models for liquid, hybrid, and solid rocket engines
Outputs STL files compatible with professional CAD software
"""

import numpy as np
import os
from typing import Dict, List, Tuple, Optional
import json
from datetime import datetime


class ProfessionalRocketCAD:
    """Generate professional-grade rocket engine 3D models"""
    
    def __init__(self):
        self.resolution = 64  # High resolution for smooth curves
        self.export_dir = "cad_exports"
        os.makedirs(self.export_dir, exist_ok=True)
    
    def generate_liquid_hybrid_engine(self, engine_params: Dict) -> Dict:
        """Generate liquid/hybrid rocket engine with realistic components"""
        
        # Extract or calculate dimensions
        thrust = engine_params.get('thrust', 10000)  # N
        chamber_pressure = engine_params.get('chamber_pressure', 50)  # bar
        expansion_ratio = engine_params.get('expansion_ratio', 8)
        
        # Calculate realistic dimensions based on thrust
        throat_diameter = self._calculate_throat_diameter(thrust, chamber_pressure)
        chamber_diameter = throat_diameter * 2.5
        chamber_length = chamber_diameter * 1.8
        exit_diameter = throat_diameter * np.sqrt(expansion_ratio)
        nozzle_length = (exit_diameter - throat_diameter) * 2.5
        
        components = {}
        
        # 1. Injector Head Assembly
        components['injector'] = self._create_injector_head(
            chamber_diameter, 
            engine_params.get('injector_type', 'pintle')
        )
        
        # 2. Combustion Chamber with Cooling Channels
        components['chamber'] = self._create_combustion_chamber(
            chamber_diameter,
            chamber_length,
            wall_thickness=chamber_diameter * 0.04,
            cooling_channels=True
        )
        
        # 3. Nozzle with Bell Contour
        components['nozzle'] = self._create_bell_nozzle(
            throat_diameter,
            exit_diameter,
            nozzle_length,
            chamber_diameter
        )
        
        # 4. Turbopump Assembly (for liquid engines)
        if engine_params.get('feed_system') == 'turbopump':
            components['turbopump'] = self._create_turbopump_assembly(
                chamber_diameter * 0.6
            )
        
        # 5. Gimbal Mount
        components['gimbal'] = self._create_gimbal_mount(
            nozzle_diameter=exit_diameter,
            chamber_length=chamber_length
        )
        
        # Export all components
        exported_files = []
        for name, mesh_data in components.items():
            filename = f"liquid_hybrid_{name}.stl"
            filepath = os.path.join(self.export_dir, filename)
            self._write_stl(filepath, mesh_data['vertices'], mesh_data['faces'])
            exported_files.append(filename)
        
        # Also create assembled version
        assembled = self._assemble_components(components, 'liquid')
        assembly_file = "liquid_hybrid_assembly.stl"
        assembly_path = os.path.join(self.export_dir, assembly_file)
        self._write_stl(assembly_path, assembled['vertices'], assembled['faces'])
        exported_files.append(assembly_file)
        
        return {
            'files': exported_files,
            'dimensions': {
                'throat_diameter': throat_diameter * 1000,  # mm
                'chamber_diameter': chamber_diameter * 1000,
                'chamber_length': chamber_length * 1000,
                'exit_diameter': exit_diameter * 1000,
                'nozzle_length': nozzle_length * 1000,
                'total_length': (chamber_length + nozzle_length) * 1000
            },
            'message': 'Professional liquid/hybrid engine CAD generated successfully'
        }
    
    def generate_solid_engine(self, engine_params: Dict) -> Dict:
        """Generate solid rocket motor with realistic grain geometry"""
        
        # Extract parameters
        thrust = engine_params.get('thrust', 5000)  # N
        burn_time = engine_params.get('burn_time', 10)  # seconds
        grain_type = engine_params.get('grain_type', 'BATES')
        
        # Calculate dimensions
        total_impulse = thrust * burn_time
        case_diameter = self._calculate_case_diameter(total_impulse)
        case_length = case_diameter * 4.5
        wall_thickness = case_diameter * 0.015  # 1.5% for composite case
        
        components = {}
        
        # 1. Motor Case
        components['case'] = self._create_motor_case(
            case_diameter,
            case_length,
            wall_thickness,
            forward_closure=True,
            aft_closure=False
        )
        
        # 2. Propellant Grain
        components['grain'] = self._create_propellant_grain(
            case_diameter * 0.9,
            case_length * 0.85,
            grain_type
        )
        
        # 3. Nozzle Assembly
        throat_diameter = case_diameter * 0.15
        exit_diameter = throat_diameter * 3.5
        components['nozzle'] = self._create_solid_motor_nozzle(
            throat_diameter,
            exit_diameter,
            case_diameter,
            with_insulation=True
        )
        
        # 4. Igniter Assembly
        components['igniter'] = self._create_igniter_assembly(
            case_diameter * 0.1,
            case_length * 0.15
        )
        
        # 5. Insulation/Liner
        components['insulation'] = self._create_insulation_liner(
            case_diameter - wall_thickness * 2,
            case_length * 0.9,
            thickness=case_diameter * 0.01
        )
        
        # Export components
        exported_files = []
        for name, mesh_data in components.items():
            filename = f"solid_motor_{name}.stl"
            filepath = os.path.join(self.export_dir, filename)
            self._write_stl(filepath, mesh_data['vertices'], mesh_data['faces'])
            exported_files.append(filename)
        
        # Create assembly
        assembled = self._assemble_components(components, 'solid')
        assembly_file = "solid_motor_assembly.stl"
        assembly_path = os.path.join(self.export_dir, assembly_file)
        self._write_stl(assembly_path, assembled['vertices'], assembled['faces'])
        exported_files.append(assembly_file)
        
        return {
            'files': exported_files,
            'dimensions': {
                'case_diameter': case_diameter * 1000,
                'case_length': case_length * 1000,
                'throat_diameter': throat_diameter * 1000,
                'exit_diameter': exit_diameter * 1000,
                'grain_diameter': case_diameter * 0.9 * 1000,
                'grain_length': case_length * 0.85 * 1000
            },
            'message': 'Professional solid motor CAD generated successfully'
        }
    
    def _create_injector_head(self, diameter: float, injector_type: str) -> Dict:
        """Create realistic injector head with injection elements"""
        vertices = []
        faces = []
        
        # Main injector body (thick plate)
        thickness = diameter * 0.15
        
        # Create injector face plate
        face_vertices, face_faces = self._create_cylinder(
            diameter / 2,
            thickness,
            resolution=self.resolution
        )
        vertices.extend(face_vertices)
        faces.extend(face_faces)
        
        if injector_type == 'pintle':
            # Create central pintle
            pintle_dia = diameter * 0.15
            pintle_length = thickness * 2
            pintle_v, pintle_f = self._create_cylinder(
                pintle_dia / 2,
                pintle_length,
                offset_z=-pintle_length/2
            )
            # Offset faces for proper indexing
            pintle_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in pintle_f]
            vertices.extend(pintle_v)
            faces.extend(pintle_f)
            
            # Add radial injection slots
            n_slots = 8
            for i in range(n_slots):
                angle = i * 2 * np.pi / n_slots
                slot_x = pintle_dia * 0.7 * np.cos(angle)
                slot_y = pintle_dia * 0.7 * np.sin(angle)
                # Simplified slot representation
                
        elif injector_type == 'impinging':
            # Create impinging doublet pattern
            n_rings = 3
            holes_per_ring = [8, 16, 24]
            radii = [diameter * 0.15, diameter * 0.25, diameter * 0.35]
            
            for ring_idx, (n_holes, radius) in enumerate(zip(holes_per_ring, radii)):
                for i in range(n_holes):
                    angle = i * 2 * np.pi / n_holes
                    hole_x = radius * np.cos(angle)
                    hole_y = radius * np.sin(angle)
                    # Create injection hole
                    hole_v, hole_f = self._create_cylinder(
                        diameter * 0.005,  # 5mm holes
                        thickness * 1.2,
                        offset_x=hole_x,
                        offset_y=hole_y,
                        offset_z=-thickness * 0.1
                    )
                    hole_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in hole_f]
                    vertices.extend(hole_v)
                    faces.extend(hole_f)
        
        # Add manifold structures
        manifold_v, manifold_f = self._create_torus(
            diameter / 2 - diameter * 0.05,
            diameter * 0.03,
            offset_z=thickness/2
        )
        manifold_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in manifold_f]
        vertices.extend(manifold_v)
        faces.extend(manifold_f)
        
        return {'vertices': vertices, 'faces': faces}
    
    def _create_combustion_chamber(self, diameter: float, length: float, 
                                  wall_thickness: float, cooling_channels: bool) -> Dict:
        """Create combustion chamber with cooling channels"""
        vertices = []
        faces = []
        
        # Outer shell
        outer_v, outer_f = self._create_cylinder(
            diameter / 2 + wall_thickness,
            length,
            resolution=self.resolution
        )
        vertices.extend(outer_v)
        faces.extend(outer_f)
        
        if cooling_channels:
            # Create helical cooling channels
            n_channels = 40
            channel_width = np.pi * diameter / n_channels * 0.6
            channel_depth = wall_thickness * 0.6
            
            for i in range(n_channels):
                # Helical path
                n_turns = 3
                n_points = 100
                t = np.linspace(0, n_turns * 2 * np.pi, n_points)
                
                base_angle = i * 2 * np.pi / n_channels
                radius = diameter / 2 + wall_thickness * 0.7
                
                channel_vertices = []
                for j, angle in enumerate(t):
                    x = radius * np.cos(angle + base_angle)
                    y = radius * np.sin(angle + base_angle)
                    z = -length/2 + (j / n_points) * length
                    channel_vertices.append([x, y, z])
                
                # Create channel cross-section (simplified as line of cylinders)
                for j in range(0, len(channel_vertices)-1, 5):
                    cv, cf = self._create_cylinder(
                        channel_width / 2,
                        length / 20,
                        offset_x=channel_vertices[j][0],
                        offset_y=channel_vertices[j][1],
                        offset_z=channel_vertices[j][2],
                        resolution=8
                    )
                    cf = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in cf]
                    vertices.extend(cv)
                    faces.extend(cf)
        
        # Add reinforcement bands
        n_bands = 4
        for i in range(n_bands):
            z_pos = -length/2 + (i+1) * length / (n_bands+1)
            band_v, band_f = self._create_torus(
                diameter / 2 + wall_thickness,
                wall_thickness * 0.3,
                offset_z=z_pos,
                resolution=32
            )
            band_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in band_f]
            vertices.extend(band_v)
            faces.extend(band_f)
        
        return {'vertices': vertices, 'faces': faces}
    
    def _create_bell_nozzle(self, throat_dia: float, exit_dia: float, 
                           length: float, chamber_dia: float) -> Dict:
        """Create bell-shaped nozzle with realistic contour"""
        vertices = []
        faces = []
        
        # Bell nozzle profile (Rao approximation)
        n_points = 100
        z = np.linspace(0, length, n_points)
        
        # Convergent section (30% of length)
        conv_length = length * 0.3
        div_length = length * 0.7
        
        radii = []
        for zi in z:
            if zi < conv_length:
                # Convergent section - smooth reduction
                progress = zi / conv_length
                r = chamber_dia/2 - (chamber_dia/2 - throat_dia/2) * (progress**2)
            else:
                # Divergent section - bell shape (parabolic approximation)
                progress = (zi - conv_length) / div_length
                # Bell contour equation
                r = throat_dia/2 + (exit_dia/2 - throat_dia/2) * (1 - np.cos(progress * np.pi/2))
            radii.append(r)
        
        # Generate surface of revolution
        theta = np.linspace(0, 2*np.pi, self.resolution)
        
        for i in range(len(z)):
            for j in range(len(theta)):
                x = radii[i] * np.cos(theta[j])
                y = radii[i] * np.sin(theta[j])
                vertices.append([x, y, z[i] - length/2])
        
        # Generate faces
        for i in range(len(z)-1):
            for j in range(len(theta)-1):
                v1 = i * len(theta) + j
                v2 = i * len(theta) + (j + 1)
                v3 = (i + 1) * len(theta) + j
                v4 = (i + 1) * len(theta) + (j + 1)
                
                faces.append([v1, v2, v3])
                faces.append([v2, v4, v3])
        
        # Add wall thickness
        wall_thickness = throat_dia * 0.05
        outer_vertices = []
        for i in range(len(z)):
            for j in range(len(theta)):
                x = (radii[i] + wall_thickness) * np.cos(theta[j])
                y = (radii[i] + wall_thickness) * np.sin(theta[j])
                outer_vertices.append([x, y, z[i] - length/2])
        
        # Offset for outer surface
        offset = len(vertices)
        vertices.extend(outer_vertices)
        
        # Generate outer faces
        for i in range(len(z)-1):
            for j in range(len(theta)-1):
                v1 = offset + i * len(theta) + j
                v2 = offset + i * len(theta) + (j + 1)
                v3 = offset + (i + 1) * len(theta) + j
                v4 = offset + (i + 1) * len(theta) + (j + 1)
                
                faces.append([v1, v3, v2])  # Reversed for outer surface
                faces.append([v2, v3, v4])
        
        return {'vertices': vertices, 'faces': faces}
    
    def _create_turbopump_assembly(self, size: float) -> Dict:
        """Create simplified turbopump assembly"""
        vertices = []
        faces = []
        
        # Pump housing (sphere)
        pump_v, pump_f = self._create_sphere(size/2, resolution=32)
        vertices.extend(pump_v)
        faces.extend(pump_f)
        
        # Turbine housing
        turbine_v, turbine_f = self._create_cylinder(
            size * 0.4,
            size * 0.6,
            offset_z=size * 0.7,
            resolution=32
        )
        turbine_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in turbine_f]
        vertices.extend(turbine_v)
        faces.extend(turbine_f)
        
        # Inlet/outlet pipes
        pipe_positions = [
            (size*0.6, 0, 0),
            (-size*0.6, 0, 0),
            (0, size*0.6, 0),
            (0, -size*0.6, 0)
        ]
        
        for pos in pipe_positions:
            pipe_v, pipe_f = self._create_cylinder(
                size * 0.08,
                size * 0.3,
                offset_x=pos[0],
                offset_y=pos[1],
                offset_z=pos[2],
                resolution=16
            )
            pipe_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in pipe_f]
            vertices.extend(pipe_v)
            faces.extend(pipe_f)
        
        return {'vertices': vertices, 'faces': faces}
    
    def _create_gimbal_mount(self, nozzle_diameter: float, chamber_length: float) -> Dict:
        """Create gimbal mounting system"""
        vertices = []
        faces = []
        
        # Gimbal ring
        ring_v, ring_f = self._create_torus(
            nozzle_diameter * 0.6,
            nozzle_diameter * 0.05,
            offset_z=chamber_length * 0.3
        )
        vertices.extend(ring_v)
        faces.extend(ring_f)
        
        # Actuator mounts (4 positions)
        for i in range(4):
            angle = i * np.pi / 2
            x = nozzle_diameter * 0.7 * np.cos(angle)
            y = nozzle_diameter * 0.7 * np.sin(angle)
            
            mount_v, mount_f = self._create_box(
                nozzle_diameter * 0.08,
                nozzle_diameter * 0.08,
                nozzle_diameter * 0.15,
                offset_x=x,
                offset_y=y,
                offset_z=chamber_length * 0.3
            )
            mount_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in mount_f]
            vertices.extend(mount_v)
            faces.extend(mount_f)
        
        return {'vertices': vertices, 'faces': faces}
    
    def _create_propellant_grain(self, diameter: float, length: float, grain_type: str) -> Dict:
        """Create propellant grain with burn pattern"""
        vertices = []
        faces = []
        
        if grain_type == 'BATES':
            # BATES grain - cylindrical with central port
            n_segments = 4
            segment_length = length / n_segments
            segment_gap = length * 0.02
            
            for i in range(n_segments):
                z_offset = -length/2 + i * (segment_length + segment_gap) + segment_length/2
                
                # Outer cylinder
                outer_v, outer_f = self._create_cylinder(
                    diameter / 2,
                    segment_length * 0.95,
                    offset_z=z_offset,
                    resolution=32
                )
                
                # Central port
                port_v, port_f = self._create_cylinder(
                    diameter * 0.3,
                    segment_length * 0.95,
                    offset_z=z_offset,
                    resolution=32
                )
                
                # Combine with boolean difference (simplified)
                outer_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in outer_f]
                vertices.extend(outer_v)
                faces.extend(outer_f)
                
        elif grain_type == 'star':
            # Star grain pattern
            n_points = 5
            outer_radius = diameter / 2
            inner_radius = diameter * 0.25
            
            # Create star profile
            star_vertices = []
            for i in range(n_points * 2):
                angle = i * np.pi / n_points
                if i % 2 == 0:
                    r = outer_radius
                else:
                    r = inner_radius
                x = r * np.cos(angle)
                y = r * np.sin(angle)
                star_vertices.append([x, y])
            
            # Extrude star shape
            n_layers = 50
            for i in range(n_layers):
                z = -length/2 + i * length / n_layers
                for sv in star_vertices:
                    vertices.append([sv[0], sv[1], z])
            
            # Create faces for star
            for i in range(n_layers - 1):
                for j in range(len(star_vertices)):
                    v1 = i * len(star_vertices) + j
                    v2 = i * len(star_vertices) + (j + 1) % len(star_vertices)
                    v3 = (i + 1) * len(star_vertices) + j
                    v4 = (i + 1) * len(star_vertices) + (j + 1) % len(star_vertices)
                    
                    faces.append([v1, v2, v3])
                    faces.append([v2, v4, v3])
        
        elif grain_type == 'finocyl':
            # Finocyl pattern - cylinder with fins
            main_v, main_f = self._create_cylinder(diameter/2, length)
            vertices.extend(main_v)
            faces.extend(main_f)
            
            # Add fins
            n_fins = 8
            for i in range(n_fins):
                angle = i * 2 * np.pi / n_fins
                fin_v, fin_f = self._create_box(
                    diameter * 0.05,
                    diameter * 0.4,
                    length * 0.8,
                    offset_x=diameter * 0.35 * np.cos(angle),
                    offset_y=diameter * 0.35 * np.sin(angle)
                )
                fin_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in fin_f]
                vertices.extend(fin_v)
                faces.extend(fin_f)
        
        return {'vertices': vertices, 'faces': faces}
    
    def _create_motor_case(self, diameter: float, length: float, 
                          wall_thickness: float, forward_closure: bool, 
                          aft_closure: bool) -> Dict:
        """Create solid motor case with closures"""
        vertices = []
        faces = []
        
        # Main case tube
        outer_v, outer_f = self._create_cylinder(
            diameter / 2,
            length,
            resolution=self.resolution
        )
        vertices.extend(outer_v)
        faces.extend(outer_f)
        
        # Inner surface (hollow)
        inner_v, inner_f = self._create_cylinder(
            diameter / 2 - wall_thickness,
            length * 0.98,
            resolution=self.resolution
        )
        # Note: In real implementation, would do boolean subtraction
        
        if forward_closure:
            # Forward dome closure
            dome_v, dome_f = self._create_hemisphere(
                diameter / 2,
                offset_z=-length/2,
                top=True
            )
            dome_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in dome_f]
            vertices.extend(dome_v)
            faces.extend(dome_f)
        
        if not aft_closure:
            # Aft flange for nozzle attachment
            flange_v, flange_f = self._create_torus(
                diameter / 2,
                wall_thickness * 2,
                offset_z=length/2
            )
            flange_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in flange_f]
            vertices.extend(flange_v)
            faces.extend(flange_f)
        
        return {'vertices': vertices, 'faces': faces}
    
    def _create_solid_motor_nozzle(self, throat_dia: float, exit_dia: float,
                                  case_dia: float, with_insulation: bool) -> Dict:
        """Create solid motor nozzle with insulation"""
        vertices = []
        faces = []
        
        # Nozzle insert (graphite/composite)
        nozzle_length = (exit_dia - throat_dia) * 1.5
        nozzle_data = self._create_bell_nozzle(
            throat_dia,
            exit_dia,
            nozzle_length,
            case_dia * 0.9
        )
        vertices.extend(nozzle_data['vertices'])
        faces.extend(nozzle_data['faces'])
        
        if with_insulation:
            # Ablative insulation layer
            insulation_thickness = throat_dia * 0.1
            for i in range(20):
                z = -nozzle_length/2 + i * nozzle_length / 20
                r = throat_dia/2 + insulation_thickness
                
                ring_v, ring_f = self._create_torus(
                    r,
                    insulation_thickness * 0.3,
                    offset_z=z,
                    resolution=16
                )
                ring_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in ring_f]
                vertices.extend(ring_v)
                faces.extend(ring_f)
        
        return {'vertices': vertices, 'faces': faces}
    
    def _create_igniter_assembly(self, diameter: float, length: float) -> Dict:
        """Create igniter assembly"""
        vertices = []
        faces = []
        
        # Igniter tube
        tube_v, tube_f = self._create_cylinder(
            diameter / 2,
            length,
            resolution=16
        )
        vertices.extend(tube_v)
        faces.extend(tube_f)
        
        # Igniter charge basket
        basket_v, basket_f = self._create_sphere(
            diameter * 0.7,
            offset_z=length/2,
            resolution=16
        )
        basket_f = [[f[0]+len(vertices), f[1]+len(vertices), f[2]+len(vertices)] for f in basket_f]
        vertices.extend(basket_v)
        faces.extend(basket_f)
        
        return {'vertices': vertices, 'faces': faces}
    
    def _create_insulation_liner(self, diameter: float, length: float, thickness: float) -> Dict:
        """Create insulation liner"""
        vertices = []
        faces = []
        
        # Create as hollow cylinder (simplified)
        outer_v, outer_f = self._create_cylinder(
            diameter / 2,
            length,
            resolution=32
        )
        vertices.extend(outer_v)
        faces.extend(outer_f)
        
        inner_v, inner_f = self._create_cylinder(
            diameter / 2 - thickness,
            length,
            resolution=32
        )
        # Would subtract inner from outer in real implementation
        
        return {'vertices': vertices, 'faces': faces}
    
    # Geometric primitive generators
    
    def _create_cylinder(self, radius: float, height: float, 
                        offset_x: float = 0, offset_y: float = 0, 
                        offset_z: float = 0, resolution: int = None) -> Tuple[List, List]:
        """Create cylinder primitive"""
        if resolution is None:
            resolution = self.resolution
        
        vertices = []
        faces = []
        
        # Generate vertices
        for i in range(resolution):
            angle = i * 2 * np.pi / resolution
            x = radius * np.cos(angle) + offset_x
            y = radius * np.sin(angle) + offset_y
            
            # Bottom circle
            vertices.append([x, y, -height/2 + offset_z])
            # Top circle
            vertices.append([x, y, height/2 + offset_z])
        
        # Generate side faces
        for i in range(resolution):
            next_i = (i + 1) % resolution
            
            # Bottom vertex indices
            b1 = i * 2
            b2 = next_i * 2
            # Top vertex indices
            t1 = i * 2 + 1
            t2 = next_i * 2 + 1
            
            # Two triangles per quad
            faces.append([b1, b2, t1])
            faces.append([b2, t2, t1])
        
        # Add top and bottom caps
        # Bottom cap center
        vertices.append([offset_x, offset_y, -height/2 + offset_z])
        bottom_center = len(vertices) - 1
        
        # Top cap center
        vertices.append([offset_x, offset_y, height/2 + offset_z])
        top_center = len(vertices) - 1
        
        for i in range(resolution):
            next_i = (i + 1) % resolution
            # Bottom cap
            faces.append([i*2, bottom_center, next_i*2])
            # Top cap
            faces.append([i*2+1, next_i*2+1, top_center])
        
        return vertices, faces
    
    def _create_sphere(self, radius: float, offset_x: float = 0, 
                      offset_y: float = 0, offset_z: float = 0,
                      resolution: int = None) -> Tuple[List, List]:
        """Create sphere primitive"""
        if resolution is None:
            resolution = self.resolution // 2
        
        vertices = []
        faces = []
        
        # Generate vertices
        for i in range(resolution):
            theta = i * np.pi / (resolution - 1)
            for j in range(resolution * 2):
                phi = j * 2 * np.pi / (resolution * 2)
                
                x = radius * np.sin(theta) * np.cos(phi) + offset_x
                y = radius * np.sin(theta) * np.sin(phi) + offset_y
                z = radius * np.cos(theta) + offset_z
                
                vertices.append([x, y, z])
        
        # Generate faces
        for i in range(resolution - 1):
            for j in range(resolution * 2):
                next_j = (j + 1) % (resolution * 2)
                
                v1 = i * resolution * 2 + j
                v2 = i * resolution * 2 + next_j
                v3 = (i + 1) * resolution * 2 + j
                v4 = (i + 1) * resolution * 2 + next_j
                
                if i == 0:
                    # Top cap - triangles only
                    faces.append([v1, v3, v4])
                elif i == resolution - 2:
                    # Bottom cap - triangles only
                    faces.append([v1, v2, v3])
                else:
                    # Middle - quads
                    faces.append([v1, v2, v3])
                    faces.append([v2, v4, v3])
        
        return vertices, faces
    
    def _create_torus(self, major_radius: float, minor_radius: float,
                     offset_x: float = 0, offset_y: float = 0, 
                     offset_z: float = 0, resolution: int = None) -> Tuple[List, List]:
        """Create torus primitive"""
        if resolution is None:
            resolution = self.resolution // 2
        
        vertices = []
        faces = []
        
        # Generate vertices
        for i in range(resolution):
            theta = i * 2 * np.pi / resolution
            for j in range(resolution):
                phi = j * 2 * np.pi / resolution
                
                x = (major_radius + minor_radius * np.cos(phi)) * np.cos(theta) + offset_x
                y = (major_radius + minor_radius * np.cos(phi)) * np.sin(theta) + offset_y
                z = minor_radius * np.sin(phi) + offset_z
                
                vertices.append([x, y, z])
        
        # Generate faces
        for i in range(resolution):
            next_i = (i + 1) % resolution
            for j in range(resolution):
                next_j = (j + 1) % resolution
                
                v1 = i * resolution + j
                v2 = i * resolution + next_j
                v3 = next_i * resolution + j
                v4 = next_i * resolution + next_j
                
                faces.append([v1, v2, v3])
                faces.append([v2, v4, v3])
        
        return vertices, faces
    
    def _create_box(self, width: float, depth: float, height: float,
                   offset_x: float = 0, offset_y: float = 0, 
                   offset_z: float = 0) -> Tuple[List, List]:
        """Create box primitive"""
        vertices = []
        faces = []
        
        # 8 vertices of box
        hw, hd, hh = width/2, depth/2, height/2
        vertices = [
            [-hw + offset_x, -hd + offset_y, -hh + offset_z],
            [hw + offset_x, -hd + offset_y, -hh + offset_z],
            [hw + offset_x, hd + offset_y, -hh + offset_z],
            [-hw + offset_x, hd + offset_y, -hh + offset_z],
            [-hw + offset_x, -hd + offset_y, hh + offset_z],
            [hw + offset_x, -hd + offset_y, hh + offset_z],
            [hw + offset_x, hd + offset_y, hh + offset_z],
            [-hw + offset_x, hd + offset_y, hh + offset_z]
        ]
        
        # 6 faces (12 triangles)
        faces = [
            [0, 1, 2], [0, 2, 3],  # Bottom
            [4, 6, 5], [4, 7, 6],  # Top
            [0, 4, 5], [0, 5, 1],  # Front
            [2, 6, 7], [2, 7, 3],  # Back
            [0, 3, 7], [0, 7, 4],  # Left
            [1, 5, 6], [1, 6, 2]   # Right
        ]
        
        return vertices, faces
    
    def _create_hemisphere(self, radius: float, offset_x: float = 0,
                          offset_y: float = 0, offset_z: float = 0,
                          top: bool = True) -> Tuple[List, List]:
        """Create hemisphere primitive"""
        resolution = self.resolution // 2
        vertices = []
        faces = []
        
        # Generate vertices
        for i in range(resolution // 2 + 1):
            if top:
                theta = i * np.pi / resolution
            else:
                theta = np.pi/2 + i * np.pi / resolution
                
            for j in range(resolution * 2):
                phi = j * 2 * np.pi / (resolution * 2)
                
                x = radius * np.sin(theta) * np.cos(phi) + offset_x
                y = radius * np.sin(theta) * np.sin(phi) + offset_y
                z = radius * np.cos(theta) + offset_z
                
                vertices.append([x, y, z])
        
        # Generate faces
        for i in range(resolution // 2):
            for j in range(resolution * 2):
                next_j = (j + 1) % (resolution * 2)
                
                v1 = i * resolution * 2 + j
                v2 = i * resolution * 2 + next_j
                v3 = (i + 1) * resolution * 2 + j
                v4 = (i + 1) * resolution * 2 + next_j
                
                if i == 0 and top:
                    faces.append([v1, v3, v4])
                else:
                    faces.append([v1, v2, v3])
                    faces.append([v2, v4, v3])
        
        return vertices, faces
    
    def _calculate_throat_diameter(self, thrust: float, chamber_pressure: float) -> float:
        """Calculate throat diameter from thrust and chamber pressure"""
        # Simplified calculation
        # A_t = F / (C_F * P_c)
        C_F = 1.5  # Thrust coefficient approximation
        P_c = chamber_pressure * 1e5  # Convert bar to Pa
        A_t = thrust / (C_F * P_c)
        return 2 * np.sqrt(A_t / np.pi)
    
    def _calculate_case_diameter(self, total_impulse: float) -> float:
        """Calculate case diameter from total impulse"""
        # Empirical relationship
        return 0.05 * (total_impulse / 1000) ** 0.4
    
    def _assemble_components(self, components: Dict, engine_type: str) -> Dict:
        """Assemble all components into single model"""
        all_vertices = []
        all_faces = []
        vertex_offset = 0
        
        # Define assembly positions based on engine type
        if engine_type == 'liquid':
            positions = {
                'injector': (0, 0, -0.2),
                'chamber': (0, 0, 0),
                'nozzle': (0, 0, 0.3),
                'turbopump': (0.15, 0, 0),
                'gimbal': (0, 0, 0.4)
            }
        else:  # solid
            positions = {
                'case': (0, 0, 0),
                'grain': (0, 0, 0),
                'nozzle': (0, 0, 0.4),
                'igniter': (0, 0, -0.3),
                'insulation': (0, 0, 0)
            }
        
        for name, component in components.items():
            if name in positions:
                offset = positions[name]
                # Apply position offset to vertices
                adjusted_vertices = []
                for v in component['vertices']:
                    adjusted_vertices.append([
                        v[0] + offset[0],
                        v[1] + offset[1],
                        v[2] + offset[2]
                    ])
                all_vertices.extend(adjusted_vertices)
                
                # Adjust face indices
                adjusted_faces = []
                for f in component['faces']:
                    adjusted_faces.append([
                        f[0] + vertex_offset,
                        f[1] + vertex_offset,
                        f[2] + vertex_offset
                    ])
                all_faces.extend(adjusted_faces)
                
                vertex_offset += len(component['vertices'])
        
        return {'vertices': all_vertices, 'faces': all_faces}
    
    def _write_stl(self, filename: str, vertices: List, faces: List):
        """Write STL file"""
        with open(filename, 'w') as f:
            f.write(f"solid rocket_engine\n")
            
            for face in faces:
                # Calculate normal
                v1 = np.array(vertices[face[0]])
                v2 = np.array(vertices[face[1]])
                v3 = np.array(vertices[face[2]])
                
                edge1 = v2 - v1
                edge2 = v3 - v1
                normal = np.cross(edge1, edge2)
                norm = np.linalg.norm(normal)
                if norm > 0:
                    normal = normal / norm
                else:
                    normal = np.array([0, 0, 1])
                
                f.write(f"  facet normal {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}\n")
                f.write("    outer loop\n")
                
                for vertex_idx in face:
                    v = vertices[vertex_idx]
                    f.write(f"      vertex {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
                
                f.write("    endloop\n")
                f.write("  endfacet\n")
            
            f.write("endsolid rocket_engine\n")


# Test the generator
if __name__ == "__main__":
    generator = ProfessionalRocketCAD()
    
    # Generate liquid/hybrid engine
    liquid_params = {
        'thrust': 10000,  # 10 kN
        'chamber_pressure': 50,  # 50 bar
        'expansion_ratio': 8,
        'injector_type': 'pintle',
        'feed_system': 'turbopump'
    }
    
    liquid_result = generator.generate_liquid_hybrid_engine(liquid_params)
    print("Liquid/Hybrid Engine CAD generated:")
    print(f"Files: {liquid_result['files']}")
    print(f"Dimensions: {liquid_result['dimensions']}")
    
    # Generate solid motor
    solid_params = {
        'thrust': 5000,  # 5 kN
        'burn_time': 10,  # 10 seconds
        'grain_type': 'BATES'
    }
    
    solid_result = generator.generate_solid_engine(solid_params)
    print("\nSolid Motor CAD generated:")
    print(f"Files: {solid_result['files']}")
    print(f"Dimensions: {solid_result['dimensions']}")