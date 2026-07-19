"""
3D CAD Visualization Module for Hybrid Rocket Motors
Combines motor assembly visualization (MotorCADDesigner) and
detailed engineering cross-section views (DetailedCADGenerator).

Both classes use Plotly for interactive 3D rendering.
MotorCADDesigner also uses trimesh for mesh-based geometry.
"""

import numpy as np
import trimesh

from hrma.constants import G_0
from hrma.data.materials_db import get_material
from hrma.engines.nozzle_design import sample_nozzle_inner_contour
import plotly.graph_objects as go
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


# ---------------------------------------------------------------------------
# Çıktı etiketleri — TEK tanım noktası (CLAUDE.md kural 11).
# Bir imalat değeri çözücüden gelmiyorsa sabit sayı UYDURULMAZ; alan bu
# metinle işaretlenir, kullanıcı neyin hesaplanmadığını görür.
# ---------------------------------------------------------------------------
NOT_AVAILABLE_SPEC = 'NOT AVAILABLE - not produced by this analysis run'

# Yapısal analiz yoksa 3B mesh ve kütle hesabı AYNI yedek cidar kuralını
# kullanır (görsel ile kütlenin çelişmemesi için tek sabit).
CHAMBER_WALL_FALLBACK_FRACTION = 0.045  # cidar / kamara çapı

# 3B mesh üretiminde delik sayısı üst sınırı (boolean kararlılığı). YALNIZ
# mesh için geçerlidir; teknik çizim ve spesifikasyon çıktısı gerçek sayıyı
# yazar (bkz. _injector_spec).
MESH_MAX_INJECTOR_ORIFICES = 16

# İmalat süresi/beceri tahminleri atölye deneyimi kaynaklıdır; motorun
# hesabından türetilmez ve çıktıda böyle etiketlenir.
MANUFACTURING_EFFORT_BASIS = ('typical machine-shop experience for this size '
                              'class; not computed from the analysis')

# Tolerans ve yüzey pürüzlülüğü bu yazılımın tasarım çıktısı DEĞİLDİR; standart
# atölye değerleridir ve çizim sözlüğünde kaynağıyla birlikte verilir.
DRAWING_TOLERANCE_BASIS = ('ISO 2768-m general tolerances (workshop standard, '
                           'not computed by this analysis)')
DRAWING_SURFACE_FINISH_BASIS = ('ISO 1302 typical machined finish (workshop '
                                'standard, not computed by this analysis)')
DRAWING_SURFACE_FINISH_CHAMBER = 'Ra 3.2 um'
DRAWING_SURFACE_FINISH_NOZZLE = 'Ra 1.6 um'
DRAWING_SURFACE_FINISH_INJECTOR = 'Ra 0.8 um'


def _real_scalar(value):
    """Sonlu pozitif float döndürür; aksi halde None (uydurma varsayılan yok)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if (np.isfinite(v) and v > 0) else None


def _nozzle_half_angles(motor_data):
    """Lüle yarı açılarını ÇÖZÜCÜ çıktısından okur.

    Döner: (konverjan_derece|None, diverjan_derece|None, lüle_tipi)
    Kaynak sırası: nozzle_angles -> nozzle_contour.divergent. Bell lülede
    diverjan açısı boğaz çıkış açısıdır (tek bir konik açı yoktur), bu yüzden
    tip de döndürülür ve çizim etiketinde kullanılır. Değer yoksa None döner —
    çağıran sabit 15°/12° uydurmak yerine açıyı hiç etiketlemez.
    """
    md = motor_data or {}
    angles = md.get('nozzle_angles') or {}
    divergent = (md.get('nozzle_contour') or {}).get('divergent') or {}

    conv = _real_scalar(angles.get('convergent_half_angle_deg'))
    noz_type = (divergent.get('type') or angles.get('nozzle_type') or '').lower()

    div = _real_scalar(angles.get('divergent_half_angle_deg'))
    if noz_type == 'bell':
        # Bell: boğaz çıkış açısı gerçek imalat açısıdır
        div = _real_scalar(divergent.get('throat_angle')) or div
    elif div is None:
        div = _real_scalar(divergent.get('half_angle'))

    return conv, div, (noz_type or 'conical')


def _nozzle_length_m(motor_data):
    """Lüle boyu [m] — sonuçta varsa oradan, yoksa GERÇEK kontur uzunluğundan.

    Sabit 0.15 m yedeği kullanılmaz: sample_nozzle_inner_contour zaten motorun
    kendi geometrisinden çıkarılmış konturu döndürür.
    """
    md = motor_data or {}
    length = _real_scalar(md.get('nozzle_length'))
    if length is not None:
        return length
    try:
        _pts, meta = sample_nozzle_inner_contour(md)
        return float(meta['z_exit']) / 1000.0
    except Exception:
        return None


def _injector_spec(motor_data):
    """Enjektör için TEK doğruluk kaynağı: motor sonucundaki injector_design.

    Döner: {'n_orifices', 'orifice_diameter_mm', 'plate_diameter_mm',
            'type', 'pressure_drop_bar', 'source'}
    Aynı motor koşusunda ekran grafiği, teknik çizim PDF'i ve CAD sözlüğü
    farklı delik sayıları gösteriyordu (2026-07-19 denetimi, kritik bulgu);
    bütün CAD/çizim katmanı artık bu tek fonksiyondan okur. Değer yoksa
    None bırakılır — sabit sayı uydurulmaz.
    """
    md = motor_data or {}
    # Öncelik: kullanıcının enjektör panelinden gelen sonuç (ΔP/hız hedefleri
    # oradan giriliyor) motor sonucuna eklenmişse o kazanır; yoksa motorun
    # kendi injector_design'ı.
    panel = md.get('injector_results') or {}
    inj = panel or md.get('injector_design') or md.get('injector') or {}
    source_name = ('injector panel (injector_results)' if panel
                   else 'motor result injector_design')
    detail = md.get('injector_design_detail') or {}
    ox = (detail.get('ox_circuit') or {}) if isinstance(detail, dict) else {}

    n = (inj.get('number_of_orifices') or inj.get('n_holes')
         or inj.get('n_elements') or ox.get('n_orifices'))
    n = _real_scalar(n)
    d_mm = _real_scalar(inj.get('orifice_diameter_mm')
                        or inj.get('hole_diameter')
                        or ox.get('orifice_d_mm'))
    dp = _real_scalar(inj.get('injection_pressure_drop_bar')
                      or ox.get('delta_p_bar'))
    plate_mm = _real_scalar(md.get('chamber_diameter'))
    plate_mm = plate_mm * 1000.0 if plate_mm is not None else None

    return {
        'n_orifices': int(round(n)) if n else None,
        'orifice_diameter_mm': d_mm,
        'plate_diameter_mm': plate_mm,
        'type': inj.get('injector_type') or detail.get('injector_type'),
        'pressure_drop_bar': dp,
        'source': source_name if n else 'not available',
    }


def _chamber_wall_thickness_m(motor_data):
    """Kamara cidar kalınlığı [m] — yapısal analizin GERÇEK önerisi.

    Döner: (kalınlık_m|None, kaynak_etiketi)
    """
    struct = (motor_data or {}).get('structural_analysis') or {}
    t_mm = _real_nested(struct, ('chamber_analysis', 'recommended_thickness'))
    if t_mm is not None:
        return t_mm / 1000.0, 'structural analysis (recommended thickness)'
    return None, 'not available'


def _chamber_material(motor_data):
    """Kamara malzemesi — yapısal analizde SEÇİLEN kayıt.

    Döner: (materials_db kaydı|None, görünen_ad, yoğunluk_kg_m3|None)
    """
    struct = (motor_data or {}).get('structural_analysis') or {}
    props = struct.get('material_properties') or {}
    key = ((struct.get('design_parameters') or {}).get('material')
           or (motor_data or {}).get('chamber_material'))
    name = props.get('name')
    density = _real_scalar(props.get('density'))
    if key and not (name and density):
        try:
            rec = get_material(str(key))
            name = name or rec.get('name')
            density = density or _real_scalar(rec.get('density'))
        except Exception:
            pass
    return key, name, density


def _cad_material(db_key, fields, color):
    """Merkezi materials_db kaydından CAD tablosu girdisi üretir.

    Sayısal alanlar (density, yield_strength, melting_point...) TEK
    doğruluk kaynağından (hrma/data/materials_db.py) okunur; yalnız
    görsel alanlar (color) bu modülde yerel kalır. Önceki yerel tablo
    merkezle çelişiyordu (Inconel 1034 vs 1100 MPa, grafit 2200 vs
    1800 kg/m^3 vb.).
    """
    rec = get_material(db_key)
    entry = {f: rec[f] for f in fields}
    entry['color'] = color
    return entry


class MotorCADDesigner:
    """Professional 3D CAD design for hybrid rocket motors"""

    def __init__(self):
        # Anahtarlar geriye dönük korunur; değerler merkezi DB'den gelir.
        self.materials_db = {
            'chamber': {
                'steel_304': _cad_material('ss_304', ('density', 'yield_strength'), '#C0C0C0'),
                'aluminum_6061': _cad_material('aluminum_6061', ('density', 'yield_strength'), '#A8A8A8'),
                'inconel_718': _cad_material('inconel_718', ('density', 'yield_strength'), '#808080'),
            },
            'nozzle': {
                'graphite': _cad_material('graphite', ('density', 'melting_point'), '#2F2F2F'),
                'tungsten': _cad_material('tungsten', ('density', 'melting_point'), '#404040'),
                'copper': _cad_material('copper', ('density', 'melting_point'), '#B87333'),
            },
            'injector': {
                'stainless_steel': _cad_material('ss_316', ('density', 'yield_strength'), '#E5E5E5'),
                'titanium': _cad_material('titanium_6al4v', ('density', 'yield_strength'), '#C4C4C4'),
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
            wall_case = ((wall_case / 1000.0) if wall_case else
                         max(0.004, CHAMBER_WALL_FALLBACK_FRACTION * chamber_diameter))
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
            # Gerçek (kırpılmamış) sayı korunur: MESH kararlılığı için delik
            # sayısı sınırlanır ama teknik çizim/spesifikasyon çıktısı gerçek
            # sayıyı yazmalıdır (2026-07-19 denetimi: çözücü 41 orifis derken
            # çizimde 16 görünüyordu).
            injector_orifices_real = injector_orifices
            injector_orifices = max(1, min(injector_orifices,
                                           MESH_MAX_INJECTOR_ORIFICES))
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
                'injector_orifices': injector_orifices,          # MESH için kırpılmış
                'injector_orifices_real': injector_orifices_real,  # gerçek sayı
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
                            # BDATA DUZELTMESI (v2.5.2): plotly 6.x numpy
                            # dizilerini fig.to_json()'da ikili (base64
                            # 'bdata') olarak yaziyor; gomulu plotly.js
                            # 1.58.5 bu bicimi cozemez ve 3D gorunum BOS
                            # kalir. Listeye cevirerek duz JSON uretiyoruz.
                            fig.add_trace(
                                go.Mesh3d(
                                    x=vertices[:, 0].tolist(),
                                    y=vertices[:, 1].tolist(),
                                    z=vertices[:, 2].tolist(),
                                    i=faces[:, 0].tolist(),
                                    j=faces[:, 1].tolist(),
                                    k=faces[:, 2].tolist(),
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
        """2D kesit — geometri ve açılar ÇÖZÜCÜNÜN kendi çıktısından.

        Eski sürüm açıları `motor_data.get('convergent_angle', 15.0)` /
        `('divergent_angle', 12.0)` ile okuyordu; bu anahtarlar motor
        sonucunda HİÇ YOK, dolayısıyla her motor için 15°/12° çiziliyor ve
        lejantta öyle etiketleniyordu (2026-07-19 denetimi). Gerçek değerler
        `nozzle_angles` / `nozzle_contour.divergent` altında. Ayrıca kontur
        artık sample_nozzle_inner_contour ile çizilir — 2D kesit, 3D CAD ve
        DXF ile TEK kaynak (bell lüle artık düz koni gibi görünmez).
        """

        chamber_diameter = motor_data.get('chamber_diameter', 0.1)
        chamber_length = motor_data.get('chamber_length', 0.5)
        throat_diameter = motor_data.get('throat_diameter', 0.02)
        exit_diameter = motor_data.get('exit_diameter', 0.04)

        conv_deg, div_deg, angle_type = _nozzle_half_angles(motor_data)

        chamber_top = chamber_diameter / 2
        chamber_bottom = -chamber_diameter / 2
        nozzle_start = chamber_length

        # Gerçek iç kontur (mm -> m); z=0 kamara çıkışı
        pts_mm, meta = sample_nozzle_inner_contour(motor_data)
        noz_x = [nozzle_start + z / 1000.0 for z, _r in pts_mm]
        noz_r = [r / 1000.0 for _z, r in pts_mm]
        throat_pos = nozzle_start + meta['z_throat'] / 1000.0
        throat_r = meta['r_throat'] / 1000.0
        nozzle_end = nozzle_start + meta['z_exit'] / 1000.0

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

        # Draw nozzle profile from the solver contour
        fig.add_trace(
            go.Scatter(
                x=noz_x + noz_x[::-1],
                y=noz_r + [-r for r in noz_r[::-1]],
                fill='toself',
                name=f'Nozzle ({meta.get("noz_type", "conical")})',
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

        annotations = []
        angle_length = 0.03  # açı göstergesi çizgi boyu [m]

        # Açı göstergeleri YALNIZ gerçek açı varsa çizilir/etiketlenir.
        if conv_deg is not None:
            conv_angle_rad = np.radians(conv_deg)
            conv_mid_x = nozzle_start + (throat_pos - nozzle_start) * 0.5
            conv_mid_r = chamber_top - (chamber_top - throat_r) * 0.5
            conv_end_x = conv_mid_x + angle_length * np.cos(np.pi - conv_angle_rad)
            conv_end_y = conv_mid_r + angle_length * np.sin(np.pi - conv_angle_rad)
            fig.add_trace(
                go.Scatter(
                    x=[conv_mid_x, conv_end_x],
                    y=[conv_mid_r, conv_end_y],
                    mode='lines',
                    name=f'Conv. {conv_deg:.1f}°',
                    line=dict(color='orange', width=2, dash='dot')
                ),
                row=row, col=col
            )
            annotations.append(dict(
                x=conv_end_x, y=conv_end_y,
                text=f'{conv_deg:.1f}°',
                showarrow=False,
                font=dict(size=9, color='orange')
            ))

        if div_deg is not None:
            div_angle_rad = np.radians(div_deg)
            div_mid_x = throat_pos + (nozzle_end - throat_pos) * 0.5
            div_mid_r = throat_r + (div_mid_x - throat_pos) * np.tan(div_angle_rad)
            div_end_x = div_mid_x + angle_length * np.cos(div_angle_rad)
            div_end_y = div_mid_r + angle_length * np.sin(div_angle_rad)
            div_label = ('Div. throat %.1f°' % div_deg if angle_type == 'bell'
                         else 'Div. %.1f°' % div_deg)
            fig.add_trace(
                go.Scatter(
                    x=[div_mid_x, div_end_x],
                    y=[div_mid_r, div_end_y],
                    mode='lines',
                    name=div_label,
                    line=dict(color='green', width=2, dash='dot')
                ),
                row=row, col=col
            )
            annotations.append(dict(
                x=div_end_x, y=div_end_y,
                text=f'{div_deg:.1f}°',
                showarrow=False,
                font=dict(size=9, color='green')
            ))

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

        # Expansion ratio: çözücünün değeri varsa o, yoksa geometriden
        expansion_ratio = _real_scalar(motor_data.get('expansion_ratio'))
        if expansion_ratio is None:
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
        """Add performance characteristics chart.

        DUZELTME (v2.5.2): eski surum burada UYDURMA bir egri ciziyordu
        (sabit itkiye %10'luk dogrusal dusus ekleyip 'realistic thrust curve
        variation' diye etiketliyordu). Teknik cizim ciktisinda hesaplanmamis
        bir egriyi hesaplanmis gibi gostermek yanilticidir. Artik once GERCEK
        egri aranir (transient / thrust_curve / port_history); yoksa sabit
        tasarim itkisi cizilir ve etikette bunun bir VARSAYIM oldugu yazar.

        Ayrica diziler listeye cevrilir: plotly 6.x numpy'i ikili (bdata)
        yaziyor, gomulu plotly.js 1.58.5 cozemiyor ve egri BOS kaliyordu.
        """
        time_s, thrust_n, label = None, None, None

        transient = motor_data.get('transient') or {}
        curve = motor_data.get('thrust_curve') or {}
        if transient.get('time') and transient.get('thrust'):
            time_s = list(transient['time'])
            thrust_n = list(transient['thrust'])
            label = 'Thrust (computed transient)'
        elif curve.get('time') and curve.get('thrust'):
            time_s = list(curve['time'])
            thrust_n = list(curve['thrust'])
            label = 'Thrust (computed curve)'
        else:
            burn_time = float(motor_data.get('burn_time', 10) or 10)
            design_thrust = float(motor_data.get('thrust', 1000) or 1000)
            time_s = [0.0, burn_time]
            thrust_n = [design_thrust, design_thrust]
            label = 'Thrust (design point, constant-thrust assumption)'

        fig.add_trace(
            go.Scatter(
                x=[float(v) for v in time_s],
                y=[float(v) for v in thrust_n],
                mode='lines',
                name=label,
                line=dict(color='red', width=2)
            ),
            row=row, col=col
        )

        fig.update_xaxes(title_text="Time (s)", row=row, col=col)
        fig.update_yaxes(title_text="Thrust (N)", row=row, col=col)

    def _generate_technical_drawings(self, motor_data: Dict) -> Dict:
        """İmalat spesifikasyonu — ÇÖZÜCÜNÜN kendi sonuçlarından.

        Eski sürümde cidar kalınlığı sabit 5.0 mm, enjektör plakası 30 mm ve
        malzemeler ('Steel 304' / 'Graphite' / 'Stainless Steel 316') motor
        sonucundan bağımsızdı; 20 kN'lik bir motorda yapısal analiz 29 mm cidar
        isterken çizim 5 mm yazıyordu (2026-07-19 denetimi). Artık:
          - cidar kalınlığı: structural_analysis.chamber_analysis
          - enjektör plakası: structural_analysis.end_cap_analysis (düz kapak)
          - malzeme: yapısal analizde seçilen materials_db kaydı
          - lüle açıları: nozzle_angles / nozzle_contour
        Değer yoksa sabit sayı yazılmaz; alan NOT_AVAILABLE_SPEC olur.
        Tolerans ve yüzey pürüzlülüğü tasarım kararı DEĞİLDİR; standart
        değerler 'basis' alanında kaynağıyla etiketlenir.
        """

        drawings = {}

        wall_m, wall_source = _chamber_wall_thickness_m(motor_data)
        _mat_key, mat_name, _rho = _chamber_material(motor_data)
        conv_deg, div_deg, noz_type = _nozzle_half_angles(motor_data)
        inj = _injector_spec(motor_data)

        struct = motor_data.get('structural_analysis') or {}
        plate_mm = _real_nested(struct, ('end_cap_analysis', 'flat_head_thickness'))

        # Chamber drawing
        drawings['chamber'] = {
            'outer_diameter': motor_data.get('chamber_diameter', 0.1) * 1000,  # mm
            'wall_thickness': (wall_m * 1000.0) if wall_m else NOT_AVAILABLE_SPEC,
            'wall_thickness_source': wall_source,
            'length': motor_data.get('chamber_length', 0.5) * 1000,  # mm
            'material': mat_name or NOT_AVAILABLE_SPEC,
            'surface_finish': DRAWING_SURFACE_FINISH_CHAMBER,
            'finish_basis': DRAWING_SURFACE_FINISH_BASIS,
            'tolerances': {
                'diameter': '+-0.1 mm',
                'length': '+-0.5 mm',
                'basis': DRAWING_TOLERANCE_BASIS
            }
        }

        # Nozzle drawing
        drawings['nozzle'] = {
            'throat_diameter': motor_data.get('throat_diameter', 0.02) * 1000,  # mm
            'exit_diameter': motor_data.get('exit_diameter', 0.04) * 1000,  # mm
            'length': ((_nozzle_length_m(motor_data) or 0.0) * 1000
                       or NOT_AVAILABLE_SPEC),  # mm
            'nozzle_type': noz_type,
            'convergence_angle': conv_deg if conv_deg is not None else NOT_AVAILABLE_SPEC,
            'divergence_angle': div_deg if div_deg is not None else NOT_AVAILABLE_SPEC,
            'divergence_angle_meaning': ('bell: throat exit angle (theta_n); the '
                                         'wall angle decreases toward the exit'
                                         if noz_type == 'bell'
                                         else 'conical: constant half angle'),
            'divergent_exit_angle': (
                _real_scalar(((motor_data.get('nozzle_contour') or {})
                              .get('divergent') or {}).get('exit_angle'))
                or NOT_AVAILABLE_SPEC),
            'angle_source': 'solver nozzle_angles / nozzle_contour',
            'material': (motor_data.get('nozzle_material')
                         or motor_data.get('throat_material')
                         or NOT_AVAILABLE_SPEC),
            'surface_finish': DRAWING_SURFACE_FINISH_NOZZLE,
            'finish_basis': DRAWING_SURFACE_FINISH_BASIS
        }

        # Injector drawing
        drawings['injector'] = {
            'plate_diameter': (inj['plate_diameter_mm']
                               if inj['plate_diameter_mm'] else NOT_AVAILABLE_SPEC),
            'plate_thickness': plate_mm if plate_mm else NOT_AVAILABLE_SPEC,
            'plate_thickness_source': ('structural analysis (flat closure head '
                                       'at chamber pressure)' if plate_mm
                                       else 'not available'),
            'orifice_count': inj['n_orifices'] or NOT_AVAILABLE_SPEC,
            'orifice_diameter': inj['orifice_diameter_mm'] or NOT_AVAILABLE_SPEC,
            'injector_type': inj['type'] or NOT_AVAILABLE_SPEC,
            'orifice_source': inj['source'],
            'material': motor_data.get('injector_material') or NOT_AVAILABLE_SPEC,
            'surface_finish': DRAWING_SURFACE_FINISH_INJECTOR,
            'finish_basis': DRAWING_SURFACE_FINISH_BASIS
        }

        return drawings

    def _generate_material_specifications(self, motor_data: Dict) -> Dict:
        """Malzeme spesifikasyonları — kamara kaydı materials_db'den (gerçek).

        Kamara malzemesi yapısal analizde SEÇİLEN kayıttır; özellikleri merkezi
        materials_db'den okunur (eski sürüm kullanıcı ne seçerse seçsin
        'AISI 304' basıyordu). Lüle/enjektör için motor sonucunda malzeme
        seçimi yoksa satır 'reference design' olarak etiketlenir.
        """

        mat_key, mat_name, _rho = _chamber_material(motor_data)
        chamber_spec = None
        if mat_key:
            try:
                rec = get_material(str(mat_key))
                chamber_spec = {
                    'designation': rec.get('name', mat_name),
                    'properties': {
                        'tensile_strength': f"{rec['ultimate_strength'] / 1e6:.0f} MPa",
                        'yield_strength': f"{rec['yield_strength'] / 1e6:.0f} MPa",
                        'density': f"{rec['density'] / 1000.0:.2f} g/cm3",
                        'melting_point': f"{rec.get('melting_point', 'n/a')} K",
                        'thermal_conductivity': f"{rec.get('thermal_conductivity', 'n/a')} W/m K"
                    },
                    'source': rec.get('source', 'hrma materials_db'),
                    'selected_by': 'structural analysis material selection'
                }
            except Exception:
                chamber_spec = None

        specs = {
            'chamber_material': chamber_spec or {
                'designation': NOT_AVAILABLE_SPEC,
                'properties': {},
                'source': 'no material selected in this analysis run'
            },
            # Lüle ve enjektör malzemesi bu analiz koşusunda SEÇİLMİYOR; aşağıdaki
            # kayıtlar merkezi materials_db'den okunan REFERANS tasarımlardır ve
            # 'basis' alanıyla böyle etiketlenir (kullanıcı seçimi değildir).
            'nozzle_material': self._reference_material_spec(
                motor_data.get('nozzle_material') or motor_data.get('throat_material'),
                'graphite'),
            'injector_material': self._reference_material_spec(
                motor_data.get('injector_material'), 'ss_316')
        }

        return specs

    @staticmethod
    def _reference_material_spec(selected_key, default_key) -> Dict:
        """materials_db kaydından spesifikasyon; seçim yoksa referans etiketi."""
        key = selected_key or default_key
        try:
            rec = get_material(str(key))
        except Exception:
            return {'designation': NOT_AVAILABLE_SPEC, 'properties': {},
                    'basis': 'material not found in materials_db'}
        return {
            'designation': rec.get('name', str(key)),
            'properties': {
                'tensile_strength': f"{rec['ultimate_strength'] / 1e6:.0f} MPa",
                'yield_strength': f"{rec['yield_strength'] / 1e6:.0f} MPa",
                'density': f"{rec['density'] / 1000.0:.2f} g/cm3",
                'melting_point': f"{rec.get('melting_point', 'n/a')} K",
                'thermal_conductivity': f"{rec.get('thermal_conductivity', 'n/a')} W/m K"
            },
            'source': rec.get('source', 'hrma materials_db'),
            'basis': ('selected in this analysis run' if selected_key
                      else 'reference design - not selected in this analysis run')
        }

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
        """CAD kütle/geometri özeti — kütleler GERÇEK kalınlık ve malzemeden."""

        chamber_volume = np.pi * (motor_data.get('chamber_diameter', 0.1)/2)**2 * motor_data.get('chamber_length', 0.5)
        nozzle_mass = self._estimate_component_mass('nozzle', motor_data)
        chamber_mass = self._estimate_component_mass('chamber', motor_data)
        injector_mass = self._estimate_component_mass('injector', motor_data)
        dry_mass = chamber_mass + nozzle_mass + injector_mass

        wall_m, wall_source = _chamber_wall_thickness_m(motor_data)
        _key, mat_name, _rho = _chamber_material(motor_data)

        return {
            'geometry_summary': {
                'total_length': ((_real_scalar(motor_data.get('chamber_length')) or 0.0)
                                 + (_nozzle_length_m(motor_data) or 0.0)) * 1000,  # mm
                'max_diameter': motor_data.get('chamber_diameter', 0.1) * 1000,  # mm
                'chamber_volume': chamber_volume * 1e6,  # cm3
                'thrust_to_weight': (motor_data.get('thrust', 1000) / (dry_mass * G_0)
                                     if dry_mass > 0 else None)
            },
            'mass_breakdown': {
                'chamber_mass': chamber_mass,  # kg
                'nozzle_mass': nozzle_mass,  # kg
                'injector_mass': injector_mass,  # kg
                'total_dry_mass': dry_mass,  # kg
                # Kütlelerin neye dayandığı kullanıcıya açıkça söylenir.
                'wall_thickness_mm': (wall_m * 1000.0) if wall_m else None,
                'wall_thickness_source': wall_source,
                'chamber_material': mat_name or NOT_AVAILABLE_SPEC,
            },
            'manufacturing_complexity': {
                'machining_time': '24-48 hours',
                'assembly_time': '4-6 hours',
                'skill_level': 'Advanced machinist required',
                'special_tooling': 'Diamond boring bar for nozzle',
                'basis': MANUFACTURING_EFFORT_BASIS
            }
        }

    def _estimate_component_mass(self, component: str, motor_data: Dict) -> float:
        """Bileşen kütlesi — GERÇEK cidar kalınlığı ve GERÇEK malzeme yoğunluğu.

        Eski sürüm kamara kütlesini sabit 5 mm cidar + sabit 7850 kg/m^3 ile
        hesaplıyordu; aynı motor sonucunda yapısal analizin önerdiği kalınlık
        (ör. 20 kN motorda 29 mm) hazır dururken kütle 5 kata kadar sapıyor,
        buradan türeyen total_dry_mass ve thrust_to_weight de yanlış çıkıyordu
        (2026-07-19 denetimi, kritik bulgu).

        Kalınlık/yoğunluk yoksa CAD katmanının 3B meshte kullandığı AYNI
        yedek kural uygulanır (0.045·D_ch) — böylece görsel ile kütle çelişmez.
        """

        wall_m, _src = _chamber_wall_thickness_m(motor_data)
        _key, _name, density = _chamber_material(motor_data)
        chamber_d = _real_scalar(motor_data.get('chamber_diameter')) or 0.1
        if wall_m is None:
            # 3B mesh ile aynı yedek kural (bkz. generate_3d_motor_assembly)
            wall_m = max(0.004, CHAMBER_WALL_FALLBACK_FRACTION * chamber_d)
        # DİKKAT: mesh tarafındaki 0.12·D üst sınırı burada UYGULANMAZ; o sınır
        # görsel içindir. Kütle, yapısal analizin gerçek kalınlığını yansıtmalı.
        if density is None:
            density = get_material('steel_4130')['density']

        if component == 'chamber':
            # Yapısal analizle AYNI hacim modeli: cidar iç çapın DIŞINA eklenir
            # (structural_analysis._calculate_weight ile birebir tutarlı).
            inner_r = chamber_d / 2
            outer_r = inner_r + wall_m
            length = _real_scalar(motor_data.get('chamber_length')) or 0.5
            volume = np.pi * length * (outer_r**2 - inner_r**2)
            return volume * density

        elif component == 'nozzle':
            # Öncelik: çözücünün kendi lüle kütlesi (gerçek kontur + cidar)
            noz_geo = motor_data.get('nozzle_geometry') or {}
            mass = _real_scalar(noz_geo.get('estimated_mass'))
            if mass is not None:
                return mass
            struct_noz = _real_nested(motor_data.get('structural_analysis') or {},
                                      ('weight_analysis', 'nozzle_weight'))
            if struct_noz is not None:
                return struct_noz
            # Yedek: gerçek kontur yüzeyinden kabuk hacmi (grafit yoğunluğu)
            pts_mm, meta = sample_nozzle_inner_contour(motor_data)
            wall_noz = max(0.003, 0.1 * (_real_scalar(motor_data.get('throat_diameter')) or 0.02))
            volume = 0.0
            for (z0, r0), (z1, r1) in zip(pts_mm[:-1], pts_mm[1:]):
                dz = (z1 - z0) / 1000.0
                r_mid = (r0 + r1) / 2000.0
                volume += 2 * np.pi * r_mid * wall_noz * abs(dz)
            return volume * get_material('graphite')['density']

        elif component == 'injector':
            # Plaka kalınlığı: yapısal analizin düz kapak kalınlığı
            plate_m = _real_nested(motor_data.get('structural_analysis') or {},
                                   ('end_cap_analysis', 'flat_head_thickness'))
            plate_m = (plate_m / 1000.0) if plate_m else wall_m * 2.0
            radius = chamber_d / 2 + wall_m
            # Orifis deliklerinin çıkardığı hacim GERÇEK delik sayısı/çapından
            inj = _injector_spec(motor_data)
            hole_volume = 0.0
            if inj['n_orifices'] and inj['orifice_diameter_mm']:
                r_hole = inj['orifice_diameter_mm'] / 2000.0
                hole_volume = inj['n_orifices'] * np.pi * r_hole**2 * plate_m
            volume = max(0.0, np.pi * radius**2 * plate_m - hole_volume)
            return volume * density

        return 0.0

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
                        # OPUS DENETİM DÜZELTMESİ: eski kod hata durumunda
                        # SESSİZCE tek-üçgenlik sahte STL yazıyordu — bozuk
                        # çıktı geçerli exportmuş gibi pakete giriyordu.
                        # Artık hata yükseltilir; endpoint kullanıcıya raporlar.
                        raise RuntimeError(
                            f"{name} STL export başarısız: {e}") from e
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
                    # Birleşik assembly üretilemezse sahte STL YAZILMAZ —
                    # bileşen dosyaları geçerliyse onlarla devam edilir,
                    # hiçbiri yoksa hata yükseltilir (aşağıda).
                    print(f"Error creating combined assembly: {str(e)}")

        except RuntimeError:
            raise
        except Exception as e:
            # OPUS DENETİM DÜZELTMESİ: eski catch-all, tek-üçgenlik sahte
            # STL yazıp başarı gibi dönüyordu. Bozuk çıktı üretmek yasak.
            raise RuntimeError(f"STL export başarısız: {e}") from e

        if not exported_files:
            raise RuntimeError("STL export başarısız: geçerli mesh üretilemedi")

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
        """Sıvı motor bileşen özeti — çözücü sonucundan.

        Eski sürüm bu bloğu tamamen sabit dolduruyordu (24 kanal, 24 delik,
        'Inconel 718' / 'C-C Composite' / 'Stainless Steel 316L', 'Regenerative')
        ve kullanıcı bunu kendi tasarımının bileşen özeti sanıyordu; aynı
        oturumda çözücü 80 kanal raporluyordu (2026-07-19 denetimi).

        Beklenen sözleşme — istek gövdesinde motor sonucunun şu alanları
        bulunmalıdır: injector_design (number_of_elements / number_of_orifices),
        cooling_system (cooling_channels), cooling_type, chamber_material,
        nozzle_material, injector_material. Alan yoksa SABİT DEĞER YAZILMAZ;
        NOT_AVAILABLE_SPEC döner. (Not: yalnızca UI'nin sabit gönderdiği
        'injector_holes' anahtarı bilerek okunmaz — o bir arayüz sabitidir,
        tasarım sonucu değil.)
        """
        md = motor_data or {}
        inj_design = md.get('injector_design') or {}
        cooling = md.get('cooling_system') or {}

        holes = _real_scalar(inj_design.get('number_of_elements')
                             or inj_design.get('number_of_orifices')
                             or md.get('injector_elements'))
        channels = _real_scalar(cooling.get('cooling_channels')
                                or md.get('cooling_channels'))
        dp = _real_scalar(inj_design.get('injection_pressure_drop_fuel_bar')
                          or inj_design.get('injection_pressure_drop_bar')
                          or md.get('injector_dp'))
        thrust = _real_scalar(md.get('thrust'))
        isp = _real_scalar(md.get('isp'))
        pc = _real_scalar(md.get('chamber_pressure'))

        return {
            'injector': {
                'type': (inj_design.get('injector_type') or md.get('injector_type')
                         or NOT_AVAILABLE_SPEC),
                'hole_count': int(round(holes)) if holes else NOT_AVAILABLE_SPEC,
                'pressure_drop': f"{dp:.2f} bar" if dp else NOT_AVAILABLE_SPEC,
                'source': 'solver injector_design' if holes else 'not available'
            },
            'cooling': {
                'type': md.get('cooling_type') or NOT_AVAILABLE_SPEC,
                'channel_count': int(round(channels)) if channels else NOT_AVAILABLE_SPEC,
                'coolant': md.get('fuel_type') or NOT_AVAILABLE_SPEC,
                'source': 'solver cooling_system' if channels else 'not available'
            },
            'materials': {
                'chamber': (_chamber_material(md)[1] or md.get('chamber_material')
                            or NOT_AVAILABLE_SPEC),
                'nozzle': md.get('nozzle_material') or NOT_AVAILABLE_SPEC,
                'injector': md.get('injector_material') or NOT_AVAILABLE_SPEC
            },
            'performance': {
                'thrust': f"{thrust:.0f} N" if thrust else NOT_AVAILABLE_SPEC,
                'isp': f"{isp:.1f} s" if isp else NOT_AVAILABLE_SPEC,
                'chamber_pressure': f"{pc:.1f} bar" if pc else NOT_AVAILABLE_SPEC
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
        """Katı motor bileşen özeti — kasa verileri YAPISAL analizden.

        Eski sürüm kasayı sabit yazıyordu ('Steel 4130', '5mm', SF 2.5);
        emniyet katsayısı bu yazılımın en kritik çıktısı ve gerçek yapısal
        analiz zaten mevcuttu (2026-07-19 denetimi).
        """
        md = motor_data or {}
        struct = md.get('structural_analysis') or {}
        wall_m, wall_source = _chamber_wall_thickness_m(md)
        _key, mat_name, _rho = _chamber_material(md)
        sf = (_real_scalar(struct.get('safety_factor_total'))
              or _real_scalar(struct.get('safety_factor'))
              or _real_nested(struct, ('safety_analysis', 'minimum_safety_factor')))
        grain = md.get('grain_design') or {}

        return {
            'grain': {
                'type': (grain.get('grain_type') or md.get('grain_type')
                         or NOT_AVAILABLE_SPEC),
                'segments': (grain.get('number_of_segments')
                             or md.get('grain_count') or NOT_AVAILABLE_SPEC),
                'inhibitor': (grain.get('inhibitor') or md.get('inhibitor')
                              or NOT_AVAILABLE_SPEC)
            },
            'case': {
                'material': mat_name or NOT_AVAILABLE_SPEC,
                'thickness': (f"{wall_m * 1000.0:.2f} mm" if wall_m
                              else NOT_AVAILABLE_SPEC),
                'thickness_source': wall_source,
                'factor_of_safety': sf if sf else NOT_AVAILABLE_SPEC,
                'factor_of_safety_source': ('structural analysis' if sf
                                            else 'not available')
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
