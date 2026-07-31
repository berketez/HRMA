"""
OpenRocket Integration Module
Export motor data to OpenRocket .eng format and create flight simulation files
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from hrma.constants import G_0, M_AIR, R_STAR_ICAO, isa_pressure, isa_temperature

# ---------------------------------------------------------------------------
# .eng (RASP) üretim sabitleri — TEK tanım noktası (CLAUDE.md kural 11).
# ---------------------------------------------------------------------------
# RASP formatı eğrinin sıfır itkiyle bitmesini ister. Bu son nokta bir FORMAT
# sonlandırıcısıdır, modellenmiş bir sönme rampası DEĞİLDİR; toplam impulsu
# etkilemesin diye çok kısa tutulur.
ENG_ZERO_TERMINATOR_DT_S = 0.01
# OpenRocket için yeterli çözünürlük (gerçek eğri bundan uzunsa seyreltilir).
ENG_MAX_SAMPLES = 100

# İtki eğrisinin hangi kaynaktan geldiği .eng yorum satırına yazılır; kullanıcı
# dosyanın kendisine bakarak gerçek çözümü mü yoksa sabit itki varsayımını mı
# indirdiğini görebilir (2026-07-19 uydurma denetimi, kritik bulgu).
THRUST_SOURCE_LABELS = {
    'transient': 'transient ballistics solver (time-resolved)',
    # v2.6.26: bu etiket "solid grain burn-back solver" diye SABİTTİ, çünkü
    # `thrust_curve` yalnız katı motorda vardı. Aynı sürümde hibrit motor da
    # zaman-adımlı eğri üretmeye başlayınca hibrit dosyalar KATI çözücüsüyle
    # üretilmiş gibi etiketleniyordu. Motor eğrinin yanında kendi `basis`
    # açıklamasını taşıyorsa o kullanılır (aşağıdaki _thrust_curve_label);
    # buradaki değer yalnız beyansız eski sonuçlar için yedektir.
    'thrust_curve': 'grain burn-back solver (time-resolved)',
    'constant': 'constant-thrust approximation; no transient solution available',
}


def _thrust_curve_label(curve):
    """Eğrinin kendi `basis` beyanını etikete çevirir; yoksa genel etiket.

    Çözücü hangi denklemi kullandığını `basis` alanında yazıyor; dosyayı açan
    kişi bunu görmelidir. Uydurma değil, motorun kendi beyanı taşınır.
    """
    genel = THRUST_SOURCE_LABELS['thrust_curve']
    if not isinstance(curve, dict):
        return genel
    basis = curve.get('basis')
    if not basis:
        return genel
    basis = ' '.join(str(basis).split())
    return f'{genel}; {basis}'

# Yüklü kütle (loaded mass) kaynağı etiketleri.
MASS_SOURCE_LABELS = {
    'structural': 'inert mass from structural analysis (chamber + nozzle + end caps)',
    'reported': 'inert mass reported by solver',
    'none': ('inert (case/structure) mass NOT available in this export; '
             'loaded mass = propellant mass only - enter case mass in OpenRocket'),
}

# ---------------------------------------------------------------------------
# BİRİM SÖZLEŞMESİ (2026-07-19 Codex denetimi, bulgu 1)
# ---------------------------------------------------------------------------
# Üst seviye motor sonuçları motor tipine göre FARKLI birim kullanır:
#   katı   : throat_diameter = 47.93  -> MİLİMETRE, chamber_length üst seviyede yok
#   sıvı   : throat_diameter = 0.0278 -> METRE,     chamber_length = 97.96 -> MİLİMETRE
#   hibrit : throat_diameter = 0.0305 -> METRE,     chamber_length = 0.882 -> METRE
# Bu dosya eskiden hepsini METRE sanıp 1000 ile çarpıyordu; katı motorda
# .eng başlığına 47927 mm çap yazılıyordu.
#
# Tek doğruluk kaynağı: hrma/export/motor_geometry.py'nin ürettiği normalize
# `motor_geometry` bloğu (HER alanı SI). /calculate_solid ve /calculate_liquid
# yanıtlarında bu blok döner; hibrit sonucu zaten SI'dır. Blok yoksa değer
# BÜYÜKLÜĞÜNDEN çıkarılır ve hangi yolun kullanıldığı .eng yorum satırına ve
# export_motor_summary çıktısına yazılır — sessiz tahmin yok.
GEOMETRY_SOURCE_LABELS = {
    'motor_geometry': 'normalized motor_geometry block (SI, no unit inference)',
    'inferred': 'top-level results; unit inferred from magnitude (see notes)',
    'missing': 'geometry not supplied; exporter placeholders used',
}

# Çıkarım eşikleri. Bu sınıftaki (amatör/üniversite) motorlarda bir çap metre
# cinsinden 1 m'yi, bir boy 5 m'yi geçmez; geçiyorsa değer milimetredir.
# Belirsiz bant (ör. 1.0) çap için mm kabul edilir: 1 m boğaz bu yazılımın
# kapsamı dışında, 1 mm boğaz ise gerçek bir mikro-motor ölçüsüdür.
DIAMETER_SI_MAX_M = 1.0
LENGTH_SI_MAX_M = 5.0
THICKNESS_SI_MAX_M = 0.1

# .eng başlığındaki 2. alanın ne olduğu: RASP formatında motor KASA (gövde)
# çapıdır, boğaz çapı değil. Kasa dış çapı bulunamazsa hangi ölçünün yazıldığı
# dosyaya not düşülür.
CASE_DIAMETER_SOURCE_LABELS = {
    'explicit': 'motor casing outer diameter (from results)',
    'chamber_plus_wall': 'casing outer diameter = chamber inner diameter + 2 x wall thickness',
    'chamber': ('chamber inner diameter (wall thickness not available - '
                'outer diameter is slightly larger)'),
    'exit': ('nozzle exit diameter used as casing placeholder - chamber '
             'diameter NOT available; check the diameter in OpenRocket'),
    'throat': ('WARNING: casing diameter NOT available; throat diameter '
               'written as placeholder - correct it in OpenRocket'),
}


def _length_in_meters(value, si_max: float) -> Tuple[Optional[float], str]:
    """Bir uzunluğu metreye çevirir; birimi büyüklüğünden çıkarır.

    Döner: (metre, 'si' | 'mm' | 'missing'). Üst seviye sonuçlar birimi beyan
    etmediği için başka yol yok; çağıran hangi yolun seçildiğini raporlar.
    """
    f = _finite_positive(value)
    if f is None:
        return None, 'missing'
    if f > si_max:
        return f / 1000.0, 'mm'
    return f, 'si'


def _nested(data, *path):
    """İç içe sözlükten güvenli okuma; ara düğüm sözlük değilse None."""
    node = data
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _finite_positive(value) -> Optional[float]:
    """Sonlu ve pozitif float döndürür; aksi halde None."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if (np.isfinite(f) and f > 0.0) else None


def _air_density(altitude_m: float) -> float:
    """ISA hava yoğunluğu [kg/m^3] — basınç/sıcaklık tek kaynaktan (constants)."""
    h = float(max(0.0, altitude_m))
    T = isa_temperature(h)
    p = isa_pressure(h)
    return float(p * M_AIR / (R_STAR_ICAO * T))


class OpenRocketExporter:
    """Export motor data to OpenRocket compatible formats"""
    
    def __init__(self):
        # Standard motor designations
        self.motor_classes = {
            # Total impulse ranges (N·s)
            'A': (1.26, 2.5),
            'B': (2.51, 5.0),
            'C': (5.01, 10.0),
            'D': (10.01, 20.0),
            'E': (20.01, 40.0),
            'F': (40.01, 80.0),
            'G': (80.01, 160.0),
            'H': (160.01, 320.0),
            'I': (320.01, 640.0),
            'J': (640.01, 1280.0),
            'K': (1280.01, 2560.0),
            'L': (2560.01, 5120.0),
            'M': (5120.01, 10240.0),
            'N': (10240.01, 20480.0),
            'O': (20480.01, 40960.0)
        }
    
    def export_motor_file(self, motor_data: Dict, filename: str = None) -> str:
        """
        Export motor data to OpenRocket .eng format
        
        Args:
            motor_data: Complete motor analysis results
            filename: Output filename (optional)
            
        Returns:
            Generated .eng file content
        """
        
        # Extract motor parameters
        total_impulse = motor_data.get('total_impulse', 10000)  # N·s
        propellant_mass = motor_data.get('propellant_mass_total', 1.0)  # kg

        # Geometri TEK yardımcıdan (birim sözleşmesi; bkz. resolve_geometry)
        geometry = self.resolve_geometry(motor_data)
        # RASP başlığının 2. alanı motor KASA çapıdır (mm), boğaz çapı değil.
        case_diameter = self._mm(geometry['case_diameter'], 0.0)
        chamber_length = self._mm(geometry['chamber_length'], 500.0)

        # Generate thrust curve (gerçek çözüm varsa ondan)
        thrust_curve, thrust_source = self.resolve_thrust_curve(motor_data)

        # Create motor designation
        motor_designation = self._designation(motor_data, geometry)

        # Generate .eng file content
        eng_content = self._create_eng_file(
            motor_designation, case_diameter, chamber_length,
            propellant_mass, total_impulse, thrust_curve, motor_data,
            thrust_source=thrust_source, geometry=geometry
        )
        
        # Save to file if filename provided
        if filename:
            if not filename.endswith('.eng'):
                filename += '.eng'
            with open(filename, 'w') as f:
                f.write(eng_content)
        
        return eng_content
    
    def create_flight_simulation_data(self, motor_data: Dict, rocket_params: Dict = None) -> Dict:
        """
        Create flight simulation parameters for OpenRocket integration
        
        Args:
            motor_data: Motor analysis results
            rocket_params: Rocket parameters (mass, drag, etc.)
            
        Returns:
            Flight simulation data
        """
        
        if rocket_params is None:
            rocket_params = {
                'dry_mass': 5.0,  # kg
                'diameter': 0.1,  # m
                'length': 1.5,    # m
                'drag_coefficient': 0.5,
                'fin_count': 4
            }
        
        # Calculate flight performance
        flight_data = self._calculate_flight_performance(motor_data, rocket_params)
        
        # Generate OpenRocket simulation parameters
        simulation_params = {
            'motor_data': motor_data,
            'rocket_parameters': rocket_params,
            'flight_performance': flight_data,
            'simulation_settings': {
                'time_step': 0.01,  # s
                'max_altitude': 50000,  # m
                'wind_speed': 0,  # m/s
                'launch_angle': 85,  # degrees
                'launch_rod_length': 3  # m
            }
        }
        
        return simulation_params
    
    def generate_technical_report(self, motor_data: Dict) -> str:
        """Generate technical report for OpenRocket documentation"""
        
        report = []
        
        # Header
        report.append("UZAYTEK HYBRID ROCKET MOTOR")
        report.append("OpenRocket Integration Report")
        report.append("=" * 50)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Motor specifications
        report.append("MOTOR SPECIFICATIONS:")
        report.append("-" * 30)
        total_impulse = motor_data.get('total_impulse', 0)
        motor_class = self._get_motor_class(total_impulse)
        # Geometri TEK yardımcıdan; ham alanlar mm/m karışıktır (bulgu 1)
        geometry = self.resolve_geometry(motor_data)

        report.append(f"Designation: {self._designation(motor_data, geometry)}")
        report.append(f"Motor Class: {motor_class}")
        report.append(f"Total Impulse: {total_impulse:.0f} N·s")
        report.append(f"Average Thrust: {motor_data.get('thrust', 0):.0f} N")
        report.append(f"Burn Time: {motor_data.get('burn_time', 0):.1f} s")
        report.append(f"Specific Impulse: {motor_data.get('isp', 0):.1f} s")
        report.append("")
        
        # Physical dimensions
        report.append("PHYSICAL DIMENSIONS:")
        report.append("-" * 30)
        def dim(label: str, key: str):
            value = geometry.get(key)
            if value is None:
                report.append(f"{label}: not available")
            else:
                report.append(f"{label}: {value * 1000.0:.2f} mm")

        dim("Throat Diameter", 'throat_diameter')
        dim("Exit Diameter", 'exit_diameter')
        dim("Chamber Diameter", 'chamber_diameter')
        dim("Chamber Length", 'chamber_length')
        dim("Case (body) Diameter", 'case_diameter')
        report.append(f"Propellant Mass: {motor_data.get('propellant_mass_total', 0):.2f} kg")
        report.append(f"Geometry source: "
                      f"{GEOMETRY_SOURCE_LABELS.get(geometry.get('source'), 'unknown')}")
        report.append("")
        
        # Performance characteristics
        report.append("PERFORMANCE CHARACTERISTICS:")
        report.append("-" * 30)
        report.append(f"Chamber Pressure: {motor_data.get('chamber_pressure', 0):.1f} bar")
        report.append(f"O/F Ratio: {motor_data.get('of_ratio', 0):.2f}")
        report.append(f"C* Efficiency: {motor_data.get('c_star', 0):.0f} m/s")
        report.append(f"Thrust Coefficient: {motor_data.get('cf', 0):.3f}")
        report.append("")
        
        # OpenRocket compatibility
        report.append("OPENROCKET COMPATIBILITY:")
        report.append("-" * 30)
        report.append("✓ .eng file format supported")
        report.append("✓ Thrust curve data included")
        report.append("✓ Motor mass properties calculated")
        report.append("✓ Burn time profile generated")
        report.append("")
        
        # Usage instructions
        report.append("USAGE INSTRUCTIONS:")
        report.append("-" * 30)
        report.append("1. Export motor as .eng file")
        report.append("2. Copy file to OpenRocket motor directory")
        report.append("3. Load motor in OpenRocket simulation")
        report.append("4. Configure rocket parameters")
        report.append("5. Run flight simulation")
        report.append("")
        
        return "\n".join(report)
    
    def _get_motor_class(self, total_impulse: float) -> str:
        """Determine motor class from total impulse"""
        
        for motor_class, (min_impulse, max_impulse) in self.motor_classes.items():
            if min_impulse <= total_impulse <= max_impulse:
                return motor_class
        
        # For very large motors
        if total_impulse > 40960:
            return 'P+'
        
        return 'A'  # Default
    
    def resolve_thrust_curve(self, motor_data: Dict
                             ) -> Tuple[List[Tuple[float, float]], str]:
        """İtki-zaman eğrisini GERÇEK çözüm kaynaklarından çözer.

        Öncelik sırası:
          1. motor_data['transient']    — transient_ballistics (time[], thrust[])
          2. motor_data['thrust_curve'] — katı motor grain burn-back çözücüsü
          3. sabit itki                 — hiçbir zaman-çözümlü eğri yoksa

        3. seçenekte ŞEKİL UYDURULMAZ: eskiden buraya %15 doğrusal düşüş +
        0.1 s yükselme rampası (x0.8) + 0.5 s sönme (x0.3) ekleniyor ve dosya
        "gerçekçi hibrit itki eğrisi" diye OpenRocket'a gidiyordu (2026-07-19
        denetimi, kritik bulgu). Artık sabit itki yazılır ve bunun bir varsayım
        olduğu .eng yorum satırına düşülür.

        Döner: (noktalar, kaynak_anahtarı)
        """
        for key in ('transient', 'thrust_curve'):
            block = motor_data.get(key) or {}
            if not isinstance(block, dict):
                continue
            t_real = block.get('time')
            f_real = block.get('thrust')
            if t_real is None or f_real is None:
                continue
            t_real = np.asarray(t_real, dtype=float)
            f_real = np.asarray(f_real, dtype=float)
            if t_real.size < 4 or t_real.size != f_real.size:
                continue
            if not np.all(np.isfinite(t_real)) or not np.all(np.isfinite(f_real)):
                continue

            pts: List[Tuple[float, float]] = []
            if t_real[0] > 0.0:
                pts.append((0.0, 0.0))  # RASP: eğri sıfırdan başlar
            idx = np.unique(np.linspace(0, t_real.size - 1,
                                        min(ENG_MAX_SAMPLES, t_real.size)
                                        ).astype(int))
            for i in idx:
                pts.append((float(t_real[i]), max(0.0, float(f_real[i]))))
            if pts[-1][1] > 0.0:  # format gereği sıfırla bitir
                pts.append((pts[-1][0] + ENG_ZERO_TERMINATOR_DT_S, 0.0))
            return pts, key

        # ---- Zaman-çözümlü eğri yok: SABİT itki (uydurma şekil üretilmez) ----
        burn_time = _finite_positive(motor_data.get('burn_time')) or 10.0
        avg_thrust = _finite_positive(motor_data.get('thrust')) or 1000.0
        points = [
            (0.0, 0.0),
            (ENG_ZERO_TERMINATOR_DT_S, avg_thrust),
            (burn_time, avg_thrust),
            (burn_time + ENG_ZERO_TERMINATOR_DT_S, 0.0),
        ]
        return points, 'constant'

    def _generate_thrust_curve(self, motor_data: Dict) -> List[Tuple[float, float]]:
        """Geriye dönük uyum: yalnız nokta listesini döndürür."""
        points, _source = self.resolve_thrust_curve(motor_data)
        return points

    @staticmethod
    def resolve_inert_mass(motor_data: Dict) -> Tuple[Optional[float], str]:
        """Motorun kuru (kasa/yapı) kütlesini GERÇEK analizden çözer.

        Eski kod her motorda `prop_mass + 0.5` yazıyordu — 10 kg iticili bir
        motorun kasası 0.5 kg değildir ve OpenRocket yüklü kütleyi doğrudan
        apoje hesabında kullanır (2026-07-19 denetimi).

        Döner: (kütle_kg veya None, kaynak_anahtarı)
        """
        struct = motor_data.get('structural_analysis') or {}
        if isinstance(struct, dict):
            weight = struct.get('weight_analysis') or {}
            if isinstance(weight, dict):
                mass = _finite_positive(weight.get('total_weight'))
                if mass is not None:
                    return mass, 'structural'

        for key in ('dry_mass', 'motor_mass', 'engine_mass', 'total_dry_mass',
                    'inert_mass', 'case_mass'):
            mass = _finite_positive(motor_data.get(key))
            if mass is not None:
                return mass, 'reported'

        return None, 'none'

    # ------------------------------------------------------------------
    # Geometri sözleşmesi — TEK yardımcı (2026-07-19 Codex bulgu 1 ve 2)
    # ------------------------------------------------------------------
    @staticmethod
    def _wall_thickness_m(motor_data: Dict) -> Optional[float]:
        """Kasa cidar kalınlığını [m] gerçek analizlerden çeker.

        Aranan yerler (ilk bulunan kazanır): CAD kasa tasarımı, katı motor
        kasa analizi, sıvı kamara yapısı, hibrit kamara analizi. '_mm' ekli
        anahtarlar birimini beyan eder; diğerlerinde büyüklükten çıkarılır.
        """
        explicit_mm = [
            _nested(motor_data, 'cad_design', 'case_design', 'wall_thickness'),
            _nested(motor_data, 'structural_analysis', 'case_analysis',
                    'wall_thickness_mm'),
            _nested(motor_data, 'structural_analysis', 'case_analysis',
                    'recommended_wall_thickness_mm'),
        ]
        for value in explicit_mm:
            t = _finite_positive(value)
            if t is not None:
                return t / 1000.0

        inferred = [
            _nested(motor_data, 'structural_analysis', 'chamber_structure',
                    'wall_thickness'),
            _nested(motor_data, 'structural_analysis', 'chamber_analysis',
                    'recommended_thickness'),
            _nested(motor_data, 'structural_analysis', 'chamber_analysis',
                    'minimum_thickness'),
            motor_data.get('wall_thickness'),
        ]
        for value in inferred:
            t, _unit = _length_in_meters(value, THICKNESS_SI_MAX_M)
            if t is not None:
                return t
        return None

    def resolve_geometry(self, motor_data: Dict) -> Dict:
        """Motor geometrisini SI [m] olarak çözer ve kaynağını raporlar.

        Öncelik:
          1. `motor_geometry` bloğu — motor_geometry.py'de normalize edilmiş,
             birimi GARANTİ SI. Katı/sıvı yanıtlarında hazır gelir.
          2. Üst seviye alanlar — birim beyan edilmediği için büyüklükten
             çıkarılır (_length_in_meters).

        Döner: throat/exit/chamber çapları, kamara boyu, .eng başlığı için
        kasa dış çapı, `source` (GEOMETRY_SOURCE_LABELS) ve okunan her alanın
        hangi yoldan geldiğini gösteren `fields` + `notes`.
        """
        md = motor_data if isinstance(motor_data, dict) else {}
        geo = md.get('motor_geometry')
        geo = geo if isinstance(geo, dict) else None

        fields: Dict[str, str] = {}
        notes: List[str] = []

        def pick(key: str, si_max: float) -> Optional[float]:
            if geo is not None:
                value = _finite_positive(geo.get(key))
                if value is not None:
                    fields[key] = 'motor_geometry'
                    return value
            value, unit = _length_in_meters(md.get(key), si_max)
            fields[key] = unit
            if unit == 'mm':
                notes.append(f'{key} read as mm ({float(md[key]):.4g})')
            return value

        throat_d = pick('throat_diameter', DIAMETER_SI_MAX_M)
        exit_d = pick('exit_diameter', DIAMETER_SI_MAX_M)
        chamber_d = pick('chamber_diameter', DIAMETER_SI_MAX_M)
        chamber_l = pick('chamber_length', LENGTH_SI_MAX_M)

        # --- Kasa (gövde) dış çapı: .eng başlığının 2. alanı --------------
        case_d = None
        case_src = 'throat'
        for key in ('case_outer_diameter', 'casing_diameter', 'case_diameter'):
            value, unit = _length_in_meters(
                (geo or {}).get(key, md.get(key)), DIAMETER_SI_MAX_M)
            if value is not None:
                case_d, case_src = value, 'explicit'
                fields[key] = unit if geo is None else 'motor_geometry'
                break
        if case_d is None:
            outer_mm = _finite_positive(
                _nested(md, 'cad_design', 'case_design', 'outer_diameter'))
            if outer_mm is not None:
                case_d, case_src = outer_mm / 1000.0, 'explicit'
                fields['case_outer_diameter'] = 'cad_design.case_design (mm)'
        if case_d is None and chamber_d is not None:
            wall = self._wall_thickness_m(md)
            if wall is not None:
                case_d, case_src = chamber_d + 2.0 * wall, 'chamber_plus_wall'
            else:
                case_d, case_src = chamber_d, 'chamber'
        if case_d is None and exit_d is not None:
            case_d, case_src = exit_d, 'exit'
        if case_d is None and throat_d is not None:
            case_d, case_src = throat_d, 'throat'

        source = 'motor_geometry' if geo else 'inferred'
        if throat_d is None and chamber_d is None and chamber_l is None:
            source = 'missing'

        return {
            'throat_diameter': throat_d,
            'exit_diameter': exit_d,
            'chamber_diameter': chamber_d,
            'chamber_length': chamber_l,
            'case_diameter': case_d,
            'case_diameter_source': case_src,
            'source': source,
            'fields': fields,
            'notes': notes,
        }

    @staticmethod
    def _mm(value: Optional[float], fallback_mm: float) -> float:
        """SI metreyi .eng/rapor için milimetreye çevirir; yoksa yedek değer."""
        return float(value) * 1000.0 if value is not None else float(fallback_mm)

    def _designation(self, motor_data: Dict, geometry: Dict = None) -> str:
        """`<sınıf><kasa çapı mm>-<motor adı>`.

        Sınıf harfi TOPLAM İMPULSTAN gelir (değişmedi). Sayı eskiden boğaz
        çapıydı ve birim karışıklığı yüzünden katı motorda 47927 çıkıyordu;
        artık ticari motor adlandırmasıyla uyumlu olarak kasa çapıdır (mm).
        """
        geo = geometry if geometry is not None else self.resolve_geometry(motor_data)
        motor_name = motor_data.get('motor_name', 'UZAYTEK-HRM-001')
        motor_class = self._get_motor_class(motor_data.get('total_impulse', 10000))
        case_mm = self._mm(geo.get('case_diameter'), 0.0)
        return f"{motor_class}{int(round(case_mm))}-{motor_name}"

    def _create_eng_file(self, designation: str, diameter: float, length: float,
                        prop_mass: float, total_impulse: float,
                        thrust_curve: List[Tuple[float, float]], motor_data: Dict,
                        thrust_source: str = 'constant',
                        geometry: Dict = None) -> str:
        """Create .eng file content.

        Dosya kendini beyan eder: itki eğrisinin, yüklü kütlenin ve (2026-07-19
        Codex denetiminden sonra) GEOMETRİNİN hangi kaynaktan geldiği yorum
        satırlarına yazılır. `diameter` motor KASA çapıdır (mm), boğaz çapı
        değil — RASP başlığının 2. alanı budur.
        """

        geometry = geometry or self.resolve_geometry(motor_data)
        lines = []

        # Header comment
        lines.append(f"; {designation}")
        lines.append(f"; UZAYTEK Rocket Motor")
        lines.append(f"; Generated by UZAYTEK Analysis Software")
        lines.append(f"; {datetime.now().strftime('%Y-%m-%d')}")
        _egri_etiketi = (
            _thrust_curve_label(motor_data.get('thrust_curve'))
            if thrust_source == 'thrust_curve'
            else THRUST_SOURCE_LABELS.get(thrust_source, thrust_source))
        lines.append(f"; thrust curve: {_egri_etiketi}")
        lines.append(f"; geometry source: "
                     f"{GEOMETRY_SOURCE_LABELS.get(geometry.get('source'), 'unknown')}")
        for note in geometry.get('notes') or []:
            lines.append(f"; geometry note: {note}")
        lines.append(f"; diameter field = "
                     f"{CASE_DIAMETER_SOURCE_LABELS.get(geometry.get('case_diameter_source'), 'unknown')}")
        if geometry.get('chamber_length') is None:
            lines.append("; length field = exporter placeholder; chamber length "
                         "NOT available in this export - correct it in OpenRocket")
        else:
            lines.append("; length field = chamber length (nozzle not included)")
        throat_m = geometry.get('throat_diameter')
        if throat_m is not None:
            lines.append(f"; throat diameter: {throat_m * 1000.0:.2f} mm "
                         "(not written to the header - reference only)")

        # Motor line format: name diameter length delays prop_mass loaded_mass manufacturer
        inert_mass, mass_source = self.resolve_inert_mass(motor_data)
        # inert_mass None ise yüklü kütle = yalnız itici kütlesi yazılır; bu
        # bir varsayılan DEĞİL, dosyanın beyan ettiği bir eksikliktir. RASP
        # sözdizimi bozulmasın diye uyarı ';' yorum satırı olarak motor
        # satırından ÖNCE eklenir (v2.6.26, ZERO-PAT-8).
        loaded_mass = prop_mass + (inert_mass if inert_mass is not None else 0.0)
        lines.append(f"; loaded mass: {MASS_SOURCE_LABELS[mass_source]}")
        if inert_mass is not None:
            lines.append(f"; inert mass used: {inert_mass:.3f} kg")
        else:
            lines.append("; WARNING: loaded mass EXCLUDES motor case mass "
                         "(no structural analysis in this export) - apogee "
                         "will be overestimated until you set the case mass "
                         "in OpenRocket")
        lines.append(";")
        manufacturer = "UZAYTEK"
        delays = "P"  # RASP: tıpalı motor (ejeksiyon yükü yok); "0" anında ateşleme demekti

        motor_line = f"{designation} {diameter:.1f} {length:.1f} {delays} {prop_mass:.3f} {loaded_mass:.3f} {manufacturer}"
        lines.append(motor_line)
        
        # Thrust curve data (RASP: ilk örnek t>0 ve F>0 olmalı)
        for time, thrust in thrust_curve:
            if time <= 0 and thrust <= 0:
                continue
            lines.append(f"{time:.3f} {thrust:.1f}")
        
        # End marker
        lines.append(";")
        
        return "\n".join(lines)
    
    def _calculate_flight_performance(self, motor_data: Dict, rocket_params: Dict) -> Dict:
        """Closed-form (drag-free) flight estimate.

        Eski kod burnout hızını keyfi bir `efficiency = 0.85` çarpanıyla
        kısaltıyor ve apojeyi bundan türetiyordu; sayı ne yerçekimi kaybını ne
        de sürüklemeyi içeriyordu ama 'estimated_apogee' adıyla dönüyordu
        (2026-07-19 denetimi: aynı yanıttaki zaman-adımlı apoje ile 134 kat
        fark). Artık keyfi çarpan yok:

          Δv_ideal = Isp·g0·ln(m_wet/m_dry)                 (Tsiolkovsky)
          v_bo     = Δv_ideal - g0·t_b                      (dik uçuş, yerçekimi kaybı)
          h_bo     ≈ v_bo·t_b/2                             (yanma fazı, doğrusal hız)
          h_coast  = v_bo²/(2·g0)                           (sürüklemesiz süzülüş)

        Sonuç SÜRÜKLEMESİZ ÜST SINIRDIR ve döndürülen sözlükte böyle
        etiketlenir; gerçek irtifa için generate_flight_profile'ın zaman-adımlı
        (ISA sürüklemeli) çözümü kullanılmalıdır.
        """

        prop_mass = _finite_positive(motor_data.get('propellant_mass_total')) or 1.0
        dry_mass = _finite_positive(rocket_params.get('dry_mass')) or 5.0
        burn_time = _finite_positive(motor_data.get('burn_time')) or 10.0

        # Mass ratio
        wet_mass = dry_mass + prop_mass
        mass_ratio = wet_mass / dry_mass

        # Ideal velocity (rocket equation)
        isp = _finite_positive(motor_data.get('isp')) or 250.0
        delta_v = isp * G_0 * np.log(mass_ratio)

        # Burnout velocity after gravity loss (vertical flight)
        burnout_velocity = max(0.0, delta_v - G_0 * burn_time)
        altitude_at_burnout = burnout_velocity * burn_time / 2.0
        coast_height = burnout_velocity ** 2 / (2.0 * G_0)
        apogee = altitude_at_burnout + coast_height

        # Maximum acceleration at burnout (lightest mass, full thrust)
        avg_thrust = _finite_positive(motor_data.get('thrust')) or 1000.0
        max_acceleration = avg_thrust / dry_mass - G_0

        time_to_apogee = burn_time + burnout_velocity / G_0

        return {
            'estimated_apogee': apogee,  # m
            'estimated_apogee_method': ('closed-form vertical flight: rocket '
                                        'equation minus gravity loss, NO drag '
                                        '- upper bound only'),
            'delta_v': delta_v,  # m/s
            'max_acceleration': max_acceleration,  # m/s^2 (net, at burnout)
            'time_to_apogee': time_to_apogee,  # s
            'mass_ratio': mass_ratio,
            'burnout_velocity': burnout_velocity,  # m/s
            'altitude_at_burnout': altitude_at_burnout  # m
        }
    
    def create_ork_project_template(self, motor_data: Dict, rocket_params: Dict = None) -> str:
        """Create OpenRocket project template XML"""
        
        if rocket_params is None:
            rocket_params = {
                'name': 'UZAYTEK Test Rocket',
                'dry_mass': 5.0,
                'diameter': 0.1,
                'length': 1.5,
                'fin_count': 4
            }
        
        # Geometri TEK yardımcıdan (birim sözleşmesi): motor yuvası boyu ve
        # yarıçapı eskiden ham alanlardan METRE sanılarak alınıyordu; katı
        # motorda 100 m çaplı, 0.6 m yerine 600 m boyunda bir yuva çıkıyordu.
        geometry = self.resolve_geometry(motor_data)
        motor_designation = self._designation(motor_data, geometry)
        mount_length_m = geometry.get('chamber_length') or 0.5
        mount_radius_m = (geometry.get('case_diameter') or 0.1) / 2.0

        # Simplified OpenRocket XML template
        xml_template = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<openrocket version="1.5" creator="UZAYTEK">
    <rocket>
        <name>{rocket_params['name']}</name>
        <axialoffset method="absolute">0.0</axialoffset>
        
        <stage>
            <name>Stage 1</name>
            
            <!-- Nose Cone -->
            <nosecone>
                <name>Nose Cone</name>
                <shape>OGIVE</shape>
                <length>0.3</length>
                <aftradius>{rocket_params['diameter']/2}</aftradius>
                <material type="bulk" density="500.0">Fiberglass</material>
                <thickness>0.003</thickness>
            </nosecone>
            
            <!-- Body Tube -->
            <bodytube>
                <name>Body Tube</name>
                <length>{rocket_params['length']}</length>
                <outerradius>{rocket_params['diameter']/2}</outerradius>
                <material type="bulk" density="700.0">Phenolic</material>
                <thickness>0.005</thickness>
                
                <!-- Motor Mount -->
                <motormount>
                    <name>Motor Mount</name>
                    <length>{mount_length_m}</length>
                    <outerradius>{mount_radius_m}</outerradius>
                    <material type="bulk" density="7850.0">Steel</material>
                    <thickness>0.005</thickness>
                    <motorconfig>
                        <configid>default</configid>
                        <motor>{motor_designation}</motor>
                    </motorconfig>
                </motormount>
                
                <!-- Fins -->
                <finset>
                    <name>Fins</name>
                    <fincount>{rocket_params.get('fin_count', 4)}</fincount>
                    <rootchord>0.15</rootchord>
                    <tipchord>0.05</tipchord>
                    <height>0.1</height>
                    <sweepangle>45.0</sweepangle>
                    <material type="bulk" density="500.0">Fiberglass</material>
                    <thickness>0.003</thickness>
                </finset>
            </bodytube>
        </stage>
        
        <!-- Flight Configuration -->
        <flightconfiguration>
            <configid>default</configid>
            <name>Default Configuration</name>
            <motorconfig>
                <configid>default</configid>
                <motor>{motor_designation}</motor>
            </motorconfig>
        </flightconfiguration>
    </rocket>
    
    <!-- Simulation -->
    <simulation>
        <name>UZAYTEK Motor Test</name>
        <flightconfiguration>default</flightconfiguration>
        <conditions>
            <configid>default</configid>
            <launchrodlength>3.0</launchrodlength>
            <launchrodangle>85.0</launchrodangle>
            <windaverage>0.0</windaverage>
            <atmosphere model="isa"/>
        </conditions>
    </simulation>
</openrocket>"""
        
        return xml_template
    
    def export_eng_file(self, motor_data: Dict, filename: str = None) -> str:
        """Alias for export_motor_file for compatibility"""
        return self.export_motor_file(motor_data, filename)
    
    def export_motor_summary(self, motor_data: Dict) -> Dict:
        """Export motor summary data for OpenRocket integration"""
        
        total_impulse = motor_data.get('total_impulse', 10000)
        motor_class = self._get_motor_class(total_impulse)
        geometry = self.resolve_geometry(motor_data)
        motor_designation = self._designation(motor_data, geometry)
        throat_mm = geometry.get('throat_diameter')
        case_mm = geometry.get('case_diameter')

        return {
            'designation': motor_designation,
            'motor_class': motor_class,
            'total_impulse': total_impulse,
            'average_thrust': motor_data.get('thrust', 0),
            'burn_time': motor_data.get('burn_time', 0),
            'specific_impulse': motor_data.get('isp', 0),
            'propellant_mass': motor_data.get('propellant_mass_total', 0),
            # mm — birim sözleşmesi resolve_geometry'de çözülür
            'throat_diameter': throat_mm * 1000.0 if throat_mm is not None else None,
            'case_diameter': case_mm * 1000.0 if case_mm is not None else None,
            'geometry_source': geometry.get('source'),
            'geometry_notes': geometry.get('notes'),
            'case_diameter_source': geometry.get('case_diameter_source'),
            'chamber_pressure': motor_data.get('chamber_pressure', 0),
            'of_ratio': motor_data.get('of_ratio', 0),
            'manufacturer': 'UZAYTEK',
            'certification_status': 'Experimental'
        }
    
    def generate_flight_profile(self, motor_data: Dict, rocket_params: Dict = None) -> Dict:
        """Generate flight profile data for OpenRocket simulation"""
        
        if rocket_params is None:
            rocket_params = {
                'dry_mass': 5.0,
                'diameter': 0.1,
                'length': 1.5,
                'drag_coefficient': 0.5
            }

        # Uçuş önizlemesi GERÇEK itici kütlesi ister (v2.6.26, ZERO-PAT-8):
        # eski kod çözülemeyen kütleyi `or 0.0` ile 0 kg yapıyordu — 0 kg
        # itici, itki eğrisi uygulanırken kütlesi hiç azalmayan "yakıtsız"
        # bir araç demektir ve yörünge sessizce anlamsızlaşıyordu. Kütle
        # yoksa simülasyon ATLANIR ve nedeni çıktıda beyan edilir; uydurma
        # varsayılan yok. Anahtarlar başarılı yanıtla aynı tutulur ki çağıran
        # taraf KeyError yemesin (boş listeler grafikte boş eksen çizer).
        prop_mass = _finite_positive(motor_data.get('propellant_mass_total'))
        if prop_mass is None:
            return {
                'status': 'insufficient_data',
                'error': ('flight profile not computed: propellant_mass_total '
                          'is missing, non-finite or non-positive - no '
                          'default mass is assumed'),
                'missing_fields': ['propellant_mass_total'],
                'time_data': [],
                'altitude_data': [],
                'velocity_data': [],
                'acceleration_data': [],
                'thrust_data': [],
                'thrust_curve': [],
                'thrust_curve_source': None,
                'performance_summary': None,
                'max_altitude': None,
                'max_altitude_method': None,
                'max_velocity': None,
                'max_acceleration': None,
                'flight_time': None,
                'burnout_time': None,
            }

        # Calculate flight performance
        flight_performance = self._calculate_flight_performance(motor_data, rocket_params)

        # Generate trajectory points
        burn_time = _finite_positive(motor_data.get('burn_time')) or 10.0
        thrust_curve, thrust_source = self.resolve_thrust_curve(motor_data)

        # İtki eğrisi ARA-DEĞERLENİR. Eski kod `abs(t_curve - t) < 0.01`
        # toleransıyla eşleşme arıyordu; zaman ızgaraları uyuşmadığı için
        # adımların çoğunda itki 0 alınıyor ve yörünge anlamsız çıkıyordu
        # (2026-07-19 denetimi: 200 adımın yalnız 13'ünde itki eşleşiyordu).
        curve_t = np.array([p[0] for p in thrust_curve], dtype=float)
        curve_f = np.array([p[1] for p in thrust_curve], dtype=float)
        order = np.argsort(curve_t)
        curve_t, curve_f = curve_t[order], curve_f[order]
        curve_end = float(curve_t[-1]) if curve_t.size else 0.0

        # Zaman ızgarası: yanma fazını yeterince örnekle (burnout'a kadar en az
        # 200 adım), sonra süzülüş fazını ekle.
        n_steps = 600
        flight_time = max(burn_time * 3.0, curve_end * 1.5)
        time_points = np.linspace(0.0, flight_time, n_steps)

        altitude_points = []
        velocity_points = []
        acceleration_points = []
        thrust_points = []

        dry_mass = float(rocket_params.get('dry_mass', 5.0))
        # prop_mass yukarıda çözüldü ve None ise fonksiyon çoktan döndü;
        # burada `or 0.0` yedeği YOK (0 kg itici uydurması ZERO-PAT-8'di).
        current_velocity = 0.0
        current_altitude = 0.0
        mass = dry_mass + prop_mass
        # Kütle akışı gerçek eğrinin toplam impulsuna orantılı tüketilir.
        total_impulse_curve = float(np.trapz(curve_f, curve_t)) if curve_t.size > 1 else 0.0
        ref_area = np.pi * (float(rocket_params.get('diameter', 0.1)) / 2.0) ** 2
        cd = float(rocket_params.get('drag_coefficient', 0.5))
        landed = False

        for i, t in enumerate(time_points):
            thrust = float(np.interp(t, curve_t, curve_f, left=0.0, right=0.0)) \
                if curve_t.size else 0.0

            weight = mass * G_0
            rho = _air_density(current_altitude)
            # Sürükleme HER ZAMAN hareketin tersine etki eder: v*|v| işareti
            # taşır (eski kod v**2 kullandığı için iniş fazında sürükleme
            # aşağı yönde ekleniyordu).
            drag = 0.5 * rho * cd * ref_area * current_velocity * abs(current_velocity)

            net_force = thrust - weight - drag
            acceleration = net_force / mass if mass > 0 else -G_0

            if landed:
                acceleration = 0.0

            if i > 0 and not landed:
                dt = float(time_points[i] - time_points[i - 1])
                current_velocity += acceleration * dt
                current_altitude += current_velocity * dt

                # İtici tüketimi: anlık impuls payıyla orantılı
                if total_impulse_curve > 0.0 and thrust > 0.0:
                    mass = max(dry_mass,
                               mass - prop_mass * (thrust * dt) / total_impulse_curve)

                if current_altitude <= 0.0:
                    current_altitude = 0.0
                    current_velocity = 0.0
                    landed = True

            altitude_points.append(max(0.0, current_altitude))
            velocity_points.append(current_velocity)
            acceleration_points.append(acceleration)
            thrust_points.append(thrust)

        return {
            'status': 'ok',
            'time_data': time_points.tolist(),
            'altitude_data': altitude_points,
            'velocity_data': velocity_points,
            'acceleration_data': acceleration_points,
            'thrust_data': thrust_points,
            'thrust_curve': thrust_curve,
            'thrust_curve_source': THRUST_SOURCE_LABELS.get(thrust_source, thrust_source),
            'performance_summary': flight_performance,
            'max_altitude': max(altitude_points),
            # İki apoje sayısı aynı yanıtta dönüyor; hangisinin hangi modelden
            # geldiği artık açıkça yazılı (denetim bulgusu: 134x fark).
            'max_altitude_method': ('1-DOF time-marched integration with ISA '
                                    'drag, using the thrust curve above'),
            'max_velocity': max(velocity_points),
            'max_acceleration': max(acceleration_points),
            'flight_time': float(time_points[-1]),
            'burnout_time': burn_time
        }
    
    def create_simulation_file(self, motor_data: Dict, rocket_data: Dict = None) -> str:
        """Create OpenRocket simulation file content"""
        
        if rocket_data is None:
            rocket_data = {
                'name': 'UZAYTEK Test Rocket',
                'dry_mass': 5.0,
                'diameter': 0.1,
                'length': 1.5
            }
        
        # Generate XML content for simulation
        simulation_data = self.create_flight_simulation_data(motor_data, rocket_data)
        ork_template = self.create_ork_project_template(motor_data, rocket_data)
        
        return ork_template