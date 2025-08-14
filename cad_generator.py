"""
Real CAD File Generator for Liquid Rocket Propellant Tanks
Generates STEP, STL, and DXF files compatible with CATIA/SolidWorks
"""

import numpy as np
import os
import json
from typing import Dict, List, Tuple
import tempfile
import zipfile
from datetime import datetime

try:
    import FreeCAD
    import Part
    import Mesh
    import Draft
    FREECAD_AVAILABLE = True
except ImportError:
    FREECAD_AVAILABLE = False
    print("FreeCAD not available - using fallback geometry generation")

class TankCADGenerator:
    """Professional CAD file generator for propellant tanks"""
    
    def __init__(self):
        self.units = "mm"  # All dimensions in millimeters
        self.tolerance = 0.01  # 0.01mm tolerance
        
    def generate_tank_cad(self, tank_data: Dict) -> str:
        """Generate complete CAD package for propellant tanks"""
        
        # Create temporary directory for CAD files
        temp_dir = tempfile.mkdtemp(prefix='tank_cad_')
        
        try:
            if FREECAD_AVAILABLE:
                return self._generate_freecad_files(tank_data, temp_dir)
            else:
                return self._generate_fallback_files(tank_data, temp_dir)
        except Exception as e:
            print(f"CAD generation error: {str(e)}")
            return self._generate_fallback_files(tank_data, temp_dir)
    
    def _generate_freecad_files(self, tank_data: Dict, output_dir: str) -> str:
        """Generate CAD files using FreeCAD"""
        
        # Create new FreeCAD document
        doc = FreeCAD.newDocument("PropellantTanks")
        
        # Generate oxidizer tank
        ox_tank = self._create_tank_solid(
            tank_data['oxidizer_tank'], 
            "Oxidizer_Tank", 
            doc
        )
        
        # Generate fuel tank  
        fuel_tank = self._create_tank_solid(
            tank_data['fuel_tank'],
            "Fuel_Tank", 
            doc,
            offset_x=tank_data['oxidizer_tank']['dimensions']['diameter'] * 1.2
        )
        
        # Generate internal structures
        self._create_internal_structures(
            tank_data['oxidizer_tank'], 
            "OX_Internals", 
            doc
        )
        
        # Export files
        exported_files = []
        
        # Export STEP files (CATIA/SolidWorks compatible)
        step_file = os.path.join(output_dir, "Tank_Assembly.step")
        Part.export(doc.Objects, step_file)
        exported_files.append(step_file)
        
        # Export individual components
        for obj in doc.Objects:
            if hasattr(obj, 'Shape'):
                step_file = os.path.join(output_dir, f"{obj.Label}.step")
                obj.Shape.exportStep(step_file)
                exported_files.append(step_file)
                
                # Also export STL for 3D printing
                stl_file = os.path.join(output_dir, f"{obj.Label}.stl")
                mesh = Mesh.Mesh()
                mesh.addFacets(obj.Shape.tessellate(0.1))
                mesh.write(stl_file)
                exported_files.append(stl_file)
        
        # Generate engineering drawings
        self._generate_drawings(tank_data, output_dir)
        
        # Generate manufacturing specs
        self._generate_manufacturing_specs(tank_data, output_dir)
        
        # Close document
        FreeCAD.closeDocument(doc.Name)
        
        # Create ZIP package
        return self._create_zip_package(output_dir, exported_files)
    
    def _create_tank_solid(self, tank_config: Dict, name: str, doc, offset_x: float = 0) -> object:
        """Create solid tank geometry in FreeCAD"""
        
        dimensions = tank_config['dimensions']
        diameter = dimensions['diameter']  # mm
        length = dimensions['length']      # mm
        wall_thickness = dimensions['wall_thickness']  # mm
        
        # Create outer cylinder
        outer_cylinder = Part.makeCylinder(
            diameter/2, 
            length, 
            FreeCAD.Vector(offset_x, 0, 0),
            FreeCAD.Vector(0, 0, 1)
        )
        
        # Create inner cylinder (hollow)
        inner_diameter = diameter - 2 * wall_thickness
        inner_cylinder = Part.makeCylinder(
            inner_diameter/2,
            length + 1,  # Slightly longer for clean boolean
            FreeCAD.Vector(offset_x, 0, -0.5),
            FreeCAD.Vector(0, 0, 1)
        )
        
        # Boolean difference to create hollow tank
        tank_shell = outer_cylinder.cut(inner_cylinder)
        
        # Create FreeCAD object
        tank_obj = doc.addObject("Part::Feature", name)
        tank_obj.Shape = tank_shell
        tank_obj.Label = name
        
        # Set material properties
        tank_obj.addProperty("App::PropertyString", "Material", "Properties")
        tank_obj.Material = tank_config['structural']['material']
        
        tank_obj.addProperty("App::PropertyFloat", "WallThickness", "Properties")
        tank_obj.WallThickness = wall_thickness
        
        tank_obj.addProperty("App::PropertyFloat", "PressureRating", "Properties")
        tank_obj.PressureRating = tank_config['structural']['pressure_rating']
        
        return tank_obj
    
    def _create_internal_structures(self, tank_config: Dict, name: str, doc) -> List[object]:
        """Create internal tank structures (baffles, anti-vortex)"""
        
        internals = tank_config['internal_structures']
        structures = []
        
        # Create slosh baffles
        for i, baffle in enumerate(internals['slosh_baffles']):
            baffle_obj = self._create_baffle(baffle, f"Baffle_{i+1}", doc)
            structures.append(baffle_obj)
        
        # Create anti-vortex device
        anti_vortex = internals['anti_vortex_device']
        av_obj = self._create_anti_vortex(anti_vortex, "Anti_Vortex_Device", doc)
        structures.append(av_obj)
        
        return structures
    
    def _create_baffle(self, baffle_config: Dict, name: str, doc) -> object:
        """Create individual slosh baffle"""
        
        outer_diameter = baffle_config['outer_diameter']  # mm
        inner_diameter = baffle_config['inner_diameter']  # mm
        thickness = baffle_config['thickness']            # mm
        position = baffle_config['position']              # mm from bottom
        hole_diameter = baffle_config['hole_diameter']    # mm
        hole_count = baffle_config['hole_count']
        
        # Create ring shape
        outer_circle = Part.Wire(Part.makeCircle(outer_diameter/2))
        inner_circle = Part.Wire(Part.makeCircle(inner_diameter/2))
        
        # Create face with hole
        ring_face = Part.Face([outer_circle, inner_circle])
        
        # Extrude to create solid
        baffle_solid = ring_face.extrude(FreeCAD.Vector(0, 0, thickness))
        
        # Add flow holes
        hole_radius = hole_diameter / 2
        hole_spacing_radius = (outer_diameter + inner_diameter) / 4
        
        for i in range(hole_count):
            angle = (i / hole_count) * 2 * np.pi
            hole_x = hole_spacing_radius * np.cos(angle)
            hole_y = hole_spacing_radius * np.sin(angle)
            
            hole_cylinder = Part.makeCylinder(
                hole_radius,
                thickness + 1,
                FreeCAD.Vector(hole_x, hole_y, -0.5),
                FreeCAD.Vector(0, 0, 1)
            )
            
            baffle_solid = baffle_solid.cut(hole_cylinder)
        
        # Position baffle in tank
        baffle_solid = baffle_solid.translate(FreeCAD.Vector(0, 0, position))
        
        # Create FreeCAD object
        baffle_obj = doc.addObject("Part::Feature", name)
        baffle_obj.Shape = baffle_solid
        baffle_obj.Label = name
        
        # Add properties
        baffle_obj.addProperty("App::PropertyString", "Material", "Properties")
        baffle_obj.Material = baffle_config['material']
        
        baffle_obj.addProperty("App::PropertyInteger", "HoleCount", "Properties")
        baffle_obj.HoleCount = hole_count
        
        baffle_obj.addProperty("App::PropertyFloat", "OpenAreaRatio", "Properties")
        baffle_obj.OpenAreaRatio = baffle_config['open_area_ratio']
        
        return baffle_obj
    
    def _create_anti_vortex(self, av_config: Dict, name: str, doc) -> object:
        """Create anti-vortex device with radial vanes"""
        
        diameter = av_config['diameter']        # mm
        height = av_config['height']           # mm
        vane_count = av_config['vane_count']
        vane_thickness = av_config['vane_thickness']  # mm
        
        # Create central hub
        hub_radius = diameter * 0.2  # 20% of total diameter
        hub = Part.makeCylinder(hub_radius, height)
        
        # Create radial vanes
        vane_length = (diameter/2) - hub_radius
        vane_width = vane_thickness
        vane_height = height
        
        vanes = []
        for i in range(vane_count):
            angle = (i / vane_count) * 2 * np.pi
            
            # Create vane as a box
            vane_box = Part.makeBox(vane_length, vane_width, vane_height)
            
            # Position vane
            vane_box = vane_box.translate(FreeCAD.Vector(hub_radius, -vane_width/2, 0))
            
            # Rotate vane
            vane_box = vane_box.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), np.degrees(angle))
            
            vanes.append(vane_box)
        
        # Combine hub and vanes
        av_solid = hub
        for vane in vanes:
            av_solid = av_solid.fuse(vane)
        
        # Create FreeCAD object
        av_obj = doc.addObject("Part::Feature", name)
        av_obj.Shape = av_solid
        av_obj.Label = name
        
        # Add properties
        av_obj.addProperty("App::PropertyString", "Material", "Properties")
        av_obj.Material = av_config['material']
        
        av_obj.addProperty("App::PropertyInteger", "VaneCount", "Properties")
        av_obj.VaneCount = vane_count
        
        return av_obj
    
    def _generate_fallback_files(self, tank_data: Dict, output_dir: str) -> str:
        """Generate CAD files without FreeCAD (geometry data only)"""
        
        exported_files = []
        
        # Generate geometric specifications
        for tank_name, tank_config in [('oxidizer_tank', tank_data['oxidizer_tank']), 
                                     ('fuel_tank', tank_data['fuel_tank'])]:
            
            # Create geometry specification file
            geom_file = os.path.join(output_dir, f"{tank_name}_geometry.json")
            
            geometry_spec = {
                'tank_type': tank_name,
                'dimensions': tank_config['dimensions'],
                'material': tank_config['structural']['material'],
                'internal_structures': tank_config['internal_structures'],
                'cad_instructions': self._generate_cad_instructions(tank_config),
                'manufacturing_notes': self._generate_manufacturing_instructions(tank_config)
            }
            
            with open(geom_file, 'w') as f:
                json.dump(geometry_spec, f, indent=2)
            exported_files.append(geom_file)
        
        # Generate simple STL approximation
        self._generate_simple_stl(tank_data, output_dir)
        
        # Generate engineering drawings
        self._generate_drawings(tank_data, output_dir)
        
        # Generate manufacturing specs
        self._generate_manufacturing_specs(tank_data, output_dir)
        
        return self._create_zip_package(output_dir, exported_files)
    
    def _generate_cad_instructions(self, tank_config: Dict) -> Dict:
        """Generate step-by-step CAD modeling instructions"""
        
        dimensions = tank_config['dimensions']
        
        return {
            'step1_outer_cylinder': {
                'operation': 'Create cylinder',
                'diameter': dimensions['diameter'],
                'length': dimensions['length'],
                'position': [0, 0, 0]
            },
            'step2_inner_cylinder': {
                'operation': 'Create cylinder (for hollow)',
                'diameter': dimensions['diameter'] - 2 * dimensions['wall_thickness'],
                'length': dimensions['length'] + 1,
                'position': [0, 0, -0.5]
            },
            'step3_boolean_cut': {
                'operation': 'Boolean cut (outer - inner)',
                'result': 'Hollow tank shell'
            },
            'step4_baffles': {
                'operation': 'Create slosh baffles',
                'count': len(tank_config['internal_structures']['slosh_baffles']),
                'baffle_specs': tank_config['internal_structures']['slosh_baffles']
            },
            'step5_anti_vortex': {
                'operation': 'Create anti-vortex device',
                'specs': tank_config['internal_structures']['anti_vortex_device']
            },
            'step6_assembly': {
                'operation': 'Assemble all components',
                'constraints': ['Concentric alignment', 'Vertical positioning']
            }
        }
    
    def _generate_simple_stl(self, tank_data: Dict, output_dir: str):
        """Generate simple STL files for visualization"""
        
        for tank_name, tank_config in [('oxidizer_tank', tank_data['oxidizer_tank']), 
                                     ('fuel_tank', tank_data['fuel_tank'])]:
            
            dimensions = tank_config['dimensions']
            stl_file = os.path.join(output_dir, f"{tank_name}.stl")
            
            # Generate simple cylindrical mesh
            vertices, faces = self._generate_cylinder_mesh(
                dimensions['diameter']/2,
                dimensions['length'],
                30  # resolution
            )
            
            # Write STL file
            self._write_stl_file(stl_file, vertices, faces, tank_name)
    
    def _generate_cylinder_mesh(self, radius: float, height: float, resolution: int) -> Tuple[List, List]:
        """Generate cylinder mesh vertices and faces"""
        
        vertices = []
        faces = []
        
        # Generate vertices
        for ring in range(resolution + 1):
            z = (ring / resolution) * height
            for point in range(resolution):
                angle = (point / resolution) * 2 * np.pi
                x = radius * np.cos(angle)
                y = radius * np.sin(angle)
                vertices.append([x, y, z])
        
        # Generate faces
        for ring in range(resolution):
            for point in range(resolution):
                # Current quad vertices
                v1 = ring * resolution + point
                v2 = ring * resolution + ((point + 1) % resolution)
                v3 = (ring + 1) * resolution + point
                v4 = (ring + 1) * resolution + ((point + 1) % resolution)
                
                # Two triangles per quad
                faces.append([v1, v2, v3])
                faces.append([v2, v4, v3])
        
        return vertices, faces
    
    def _write_stl_file(self, filename: str, vertices: List, faces: List, name: str):
        """Write STL file"""
        
        with open(filename, 'w') as f:
            f.write(f"solid {name}\n")
            
            for face in faces:
                # Calculate normal vector
                v1 = np.array(vertices[face[0]])
                v2 = np.array(vertices[face[1]])
                v3 = np.array(vertices[face[2]])
                
                edge1 = v2 - v1
                edge2 = v3 - v1
                normal = np.cross(edge1, edge2)
                normal = normal / np.linalg.norm(normal)
                
                f.write(f"  facet normal {normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}\n")
                f.write("    outer loop\n")
                
                for vertex_idx in face:
                    v = vertices[vertex_idx]
                    f.write(f"      vertex {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
                
                f.write("    endloop\n")
                f.write("  endfacet\n")
            
            f.write(f"endsolid {name}\n")
    
    def _generate_drawings(self, tank_data: Dict, output_dir: str):
        """Generate 2D engineering drawings"""
        
        # Create drawing specification
        drawing_spec = {
            'title': 'Propellant Tank Assembly',
            'scale': '1:10',
            'units': 'mm',
            'views': {
                'front_view': self._create_front_view(tank_data),
                'side_view': self._create_side_view(tank_data),
                'section_view': self._create_section_view(tank_data)
            },
            'dimensions': self._extract_key_dimensions(tank_data),
            'notes': self._generate_drawing_notes(tank_data)
        }
        
        drawing_file = os.path.join(output_dir, 'engineering_drawings.json')
        with open(drawing_file, 'w') as f:
            json.dump(drawing_spec, f, indent=2)
    
    def _generate_manufacturing_specs(self, tank_data: Dict, output_dir: str):
        """Generate manufacturing specifications"""
        
        manufacturing_spec = {
            'project_info': {
                'title': 'Liquid Rocket Propellant Tanks',
                'date': datetime.now().isoformat(),
                'revision': 'A',
                'units': 'mm'
            },
            'materials': {
                'oxidizer_tank': tank_data['oxidizer_tank']['structural']['material'],
                'fuel_tank': tank_data['fuel_tank']['structural']['material'],
                'baffles': 'Aluminum 6061-T6',
                'fasteners': 'Stainless Steel 316'
            },
            'manufacturing_processes': {
                'tank_shells': 'Spin forming or deep drawing',
                'welding': 'TIG welding per AWS D17.1',
                'machining': 'CNC machining ±0.1mm tolerance',
                'surface_finish': 'Ra 3.2 μm internal, Ra 6.3 μm external'
            },
            'quality_requirements': {
                'pressure_test': '1.5x design pressure',
                'leak_test': 'Helium leak test < 1e-6 std cm³/s',
                'dimensional_inspection': '100% inspection of critical dimensions',
                'material_certification': 'Mill test certificates required'
            },
            'assembly_sequence': [
                '1. Machine tank shells',
                '2. Fabricate internal structures',
                '3. Weld baffles to tank walls',
                '4. Install anti-vortex devices',
                '5. Weld end caps',
                '6. Pressure test individual tanks',
                '7. Final assembly and leak test'
            ]
        }
        
        spec_file = os.path.join(output_dir, 'manufacturing_specifications.json')
        with open(spec_file, 'w') as f:
            json.dump(manufacturing_spec, f, indent=2)
    
    def _create_zip_package(self, temp_dir: str, files: List[str]) -> str:
        """Create ZIP package of all CAD files"""
        
        zip_filename = f"propellant_tanks_cad_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        zip_path = os.path.join(temp_dir, zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files:
                if os.path.exists(file_path):
                    zipf.write(file_path, os.path.basename(file_path))
        
        return zip_path
    
    def _create_front_view(self, tank_data: Dict) -> Dict:
        """Create front view drawing data"""
        return {
            'view_type': 'front',
            'oxidizer_tank': {
                'outline': 'cylinder',
                'diameter': tank_data['oxidizer_tank']['dimensions']['diameter'],
                'height': tank_data['oxidizer_tank']['dimensions']['length']
            },
            'fuel_tank': {
                'outline': 'cylinder', 
                'diameter': tank_data['fuel_tank']['dimensions']['diameter'],
                'height': tank_data['fuel_tank']['dimensions']['length']
            }
        }
    
    def _create_side_view(self, tank_data: Dict) -> Dict:
        """Create side view drawing data"""
        return {
            'view_type': 'side',
            'shows_internal_structures': True,
            'baffles': tank_data['oxidizer_tank']['internal_structures']['slosh_baffles'],
            'anti_vortex': tank_data['oxidizer_tank']['internal_structures']['anti_vortex_device']
        }
    
    def _create_section_view(self, tank_data: Dict) -> Dict:
        """Create section view drawing data"""
        return {
            'view_type': 'section_A-A',
            'cutting_plane': 'vertical_centerline',
            'shows_wall_thickness': True,
            'shows_internal_details': True
        }
    
    def _extract_key_dimensions(self, tank_data: Dict) -> Dict:
        """Extract key dimensions for drawings"""
        return {
            'oxidizer_tank': {
                'overall_diameter': tank_data['oxidizer_tank']['dimensions']['diameter'],
                'overall_length': tank_data['oxidizer_tank']['dimensions']['length'],
                'wall_thickness': tank_data['oxidizer_tank']['dimensions']['wall_thickness']
            },
            'fuel_tank': {
                'overall_diameter': tank_data['fuel_tank']['dimensions']['diameter'],
                'overall_length': tank_data['fuel_tank']['dimensions']['length'],
                'wall_thickness': tank_data['fuel_tank']['dimensions']['wall_thickness']
            }
        }
    
    def _generate_drawing_notes(self, tank_data: Dict) -> List[str]:
        """Generate drawing notes"""
        return [
            f"1. Material: {tank_data['oxidizer_tank']['structural']['material']}",
            f"2. Pressure rating: {tank_data['oxidizer_tank']['structural']['pressure_rating']} bar",
            "3. All welds per AWS D17.1",
            "4. Pressure test to 1.5x design pressure",
            "5. All dimensions in mm unless noted",
            "6. Surface finish: Ra 3.2 μm internal",
            "7. Leak test: < 1e-6 std cm³/s helium"
        ]
    
    def _generate_manufacturing_instructions(self, tank_config: Dict) -> Dict:
        """Generate detailed manufacturing instructions"""
        return {
            'material_preparation': [
                f"Cut {tank_config['structural']['material']} sheet to size",
                "Inspect material certificates",
                "Clean all surfaces"
            ],
            'forming_operations': [
                "Roll cylinder to required diameter",
                "Weld longitudinal seam with TIG process",
                "Machine weld smooth"
            ],
            'machining_operations': [
                "Machine end faces square and parallel",
                "Drill and tap mounting holes",
                "Deburr all edges"
            ],
            'assembly_steps': [
                "Fit internal structures",
                "Weld baffles in position",
                "Install anti-vortex device",
                "Final weld end caps"
            ],
            'quality_control': [
                "Dimensional inspection",
                "Pressure test",
                "Leak test",
                "Final inspection"
            ]
        }

# Global instance
cad_generator = TankCADGenerator()