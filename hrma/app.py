import os
import sys

# app.py DOĞRUDAN çalıştırılırsa (python hrma/app.py / python app.py) depo
# kökü sys.path'te olmaz → "ModuleNotFoundError: No module named 'hrma'"
# (2026-07-15 Windows geri dönütü). run.py/run_windows.py bunu zaten yapıyor;
# app.py'ye de eklendi ki hangi dosya çalıştırılırsa çalışsın 'hrma' bulunur.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import numpy as np
import json
import io
import contextlib
import platform

# Apply Windows fixes before importing other modules
if platform.system() == 'Windows':
    try:
        from hrma.utils.windows_compatibility import windows_compat, apply_windows_fixes
        windows_fixes = apply_windows_fixes()
        if windows_fixes:
            print(f"Windows compatibility fixes applied: {windows_fixes['fixes_applied']}")
    except ImportError:
        print("Windows compatibility module not found - continuing without fixes")

# Engines
from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
from hrma.engines.solid_rocket_engine import SolidRocketEngine
from hrma.engines.liquid_rocket_engine import LiquidRocketEngine

# Utils
from hrma.utils.injector_design import InjectorDesign
from hrma.utils.common_fixes import validation, calculations, graph_fixes, fuel_mixer, export_fixes
from hrma.utils.optimum_of_ratio import of_optimizer

# Validation
# v2.5.0 G1 (2026-07-17): experimental_validator emekli — sentetik kayitlar
# tests/fixtures'a tasindi, gercek deney DB'si hrma.validation.experiment_db
from hrma.validation.validation_system import validator
from hrma.validation.motor_validation import motor_validator

# Analysis
from hrma.analysis.regression_analysis import regression_analyzer
from hrma.analysis.safety_analysis import SafetyAnalyzer
from hrma.analysis.structural_analysis import StructuralAnalyzer
from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer
from hrma.analysis.cfd_analysis import cfd_analyzer
from hrma.analysis.kinetic_analysis import kinetic_analyzer
from hrma.analysis.trajectory_analysis import TrajectoryAnalyzer

# Dalga 4A — hızlı gerçekçi modeller (sahte CFD/kinetik yerine):
# quasi-1D lüle akışı, kademeli kinetik verim, kullanıcı CSV doğrulaması,
# hafif iş kuyruğu (docs/ANALIZ_PLATFORM_PLANI.md)
from hrma.analysis.nozzle_flow_1d import NozzleFlow1D
from hrma.analysis.kinetic_efficiency import (
    kinetic_efficiency, VALID_FIDELITY_LEVELS as KINETIC_FIDELITY_LEVELS,
    CANTERA_AVAILABLE as KINETIC_CANTERA_AVAILABLE,
)
from hrma.validation.user_data_validation import (
    parse_thrust_csv, compare as compare_thrust_curves,
)
from hrma.utils.job_runner import job_runner

# Data
from hrma.data.propellant_database import propellant_db
from hrma.data.open_source_propellant_api import propellant_api
from hrma.data.chemical_database import chemical_db
from hrma.data.database_integrations import DatabaseManager

import traceback
import warnings

# Visualization
from hrma.visualization.visualization import (
    create_motor_plot, create_injector_plot, create_performance_plots,
    create_heat_transfer_plots, create_combustion_analysis_plots,
    create_structural_analysis_plots, create_real_time_dashboard,
    create_3d_motor_visualization, create_comparative_analysis_plot,
    create_chamber_pressure_mixture_ratio_3d_surface,
    create_nozzle_mach_area_ratio_contour,
    create_wall_heat_flux_waterfall_plot,
    create_improved_motor_cross_section,
    create_improved_injector_design
)
from hrma.export.motor_geometry import (
    solid_results_to_motor_geometry,
    liquid_results_to_motor_geometry,
)
from hrma.constants import G_0
from hrma.visualization.advanced_results import (
    create_cea_style_results, create_altitude_performance_plot,
    create_mass_fractions_plot, create_thrust_altitude_plot
)

# Export
from hrma.export.openrocket_integration import OpenRocketExporter
from hrma.export.cad_visualization import MotorCADDesigner

from datetime import datetime

app = Flask(__name__)
CORS(app)

# Apply Windows-specific Flask configurations
if platform.system() == 'Windows':
    try:
        if 'windows_compat' in globals():
            windows_compat.fix_flask_configuration(app)
            print("Windows Flask configurations applied")
    except Exception as e:
        print(f"Could not apply Windows Flask fixes: {e}")

def sanitize_json_values(obj):
    """Recursively sanitize JSON values to handle NaN, Infinity and NumPy arrays"""
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            try:
                sanitized[str(k)] = sanitize_json_values(v)
            except Exception:
                sanitized[str(k)] = "serialization_error"
        return sanitized
    elif isinstance(obj, (list, tuple)):
        sanitized = []
        for item in obj:
            try:
                sanitized.append(sanitize_json_values(item))
            except Exception:
                sanitized.append("serialization_error")
        return sanitized
    elif isinstance(obj, np.ndarray):
        try:
            return sanitize_json_values(obj.tolist())  # Convert NumPy array to list
        except Exception:
            return "numpy_array_error"
    elif isinstance(obj, (np.integer, np.floating)):
        try:
            val = float(obj)  # Convert NumPy numbers to Python numbers
            if np.isnan(val):
                return 0.0  # Replace NaN with 0
            elif np.isinf(val):
                return 1e10 if val > 0 else -1e10  # Replace infinity with large number
            else:
                return val
        except Exception:
            return 0.0
    elif isinstance(obj, float):
        if np.isnan(obj):
            return 0.0  # Replace NaN with 0 instead of None
        elif np.isinf(obj):
            return 1e10 if obj > 0 else -1e10  # Replace infinity with large number
        else:
            return obj
    elif isinstance(obj, (int, bool, str, type(None))):
        return obj
    else:
        # Handle any other types by converting to string
        try:
            return str(obj)
        except Exception:
            return "unknown_type"

def validate_input_range(value, min_val, max_val, name):
    """Validate input values within physical limits"""
    if value < min_val or value > max_val:
        raise ValueError(f"{name} value must be between {min_val}-{max_val}, given: {value}")
    return True

def validate_positive(value, name):
    """Positive value check"""
    if value <= 0:
        raise ValueError(f"{name} must be positive, given: {value}")
    return True


def build_time_history(motor_results):
    """Gerçek zaman serilerinden dashboard time_history sözlüğü kurar.

    OPUS/keşif düzeltmesi: eski kod motor_results['time_history'] okuyordu —
    böyle bir anahtar hiç üretilmiyor, dashboard'un alt 3 paneli hep boş
    kalıyordu. Gerçek seriler port_history'de (Euler marşından, ~200 nokta).

    Dönen şema (create_real_time_dashboard beklentisi):
      {'time': [s], 'propellant_mass': [kg], 'burn_rate': [mm/s],
       'port_diameter': [mm]}
    Yakıt tüketimi D² oranıyla ölçeklenir (m_f·(D²−D0²)/(Df²−D0²)) —
    grain geometrisi kütle bütçesiyle aynı kaynaktan, ek anahtar gerekmez.
    """
    ph = (motor_results or {}).get('port_history') or {}
    t = ph.get('time')
    D = ph.get('port_diameter')
    if not t or not D or len(t) < 3 or len(t) != len(D):
        return None
    t = np.asarray(t, dtype=float)
    D = np.asarray(D, dtype=float)

    m_ox = float(motor_results.get('oxidizer_mass', 0.0) or 0.0)
    m_f = float(motor_results.get('fuel_mass', 0.0) or 0.0)
    t_b = float(motor_results.get('burn_time', t[-1]) or t[-1])
    D0, Df = D[0], D[-1]

    ox_consumed = m_ox * np.clip(t / max(t_b, 1e-9), 0.0, 1.0)
    denom = max(Df ** 2 - D0 ** 2, 1e-12)
    fuel_consumed = m_f * np.clip((D ** 2 - D0 ** 2) / denom, 0.0, 1.0)
    propellant_mass = (m_ox + m_f) - ox_consumed - fuel_consumed

    # Yanma hızı: r = (dD/dt)/2 [m/s] → mm/s
    burn_rate = np.gradient(D, t) / 2.0 * 1000.0

    return {
        'time': t.tolist(),
        'propellant_mass': np.maximum(propellant_mass, 0.0).tolist(),
        'burn_rate': np.maximum(burn_rate, 0.0).tolist(),
        'port_diameter': (D * 1000.0).tolist(),  # mm
    }

# Initialize database manager and trajectory analyzer
db_manager = DatabaseManager()
trajectory_analyzer = TrajectoryAnalyzer() 
openrocket_exporter = OpenRocketExporter()
cad_designer = MotorCADDesigner()

@app.context_processor
def inject_app_version():
    # Şablonlar sürümü tek kaynaktan gösterir (hrma/__init__.py)
    from hrma import __version__
    return {'app_version': __version__}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/hybrid')
def hybrid():
    return render_template('advanced.html')

@app.route('/solid')
def solid():
    return render_template('solid.html')

@app.route('/liquid')
def liquid():
    return render_template('liquid.html')

@app.route('/formulas')
def formulas():
    return render_template('formulas.html')

@app.route('/test')
def test():
    return jsonify({'status': 'ok', 'message': 'HRMA is running'})

# ---- Otomatik güncelleme (GitHub Releases) ----
# Arayüz açılışta /api/update/check'i çağırır; yeni sürüm varsa modal gösterir.
# İndirme URL'si istemciden alınmaz (bkz. hrma/utils/update_checker.py).

@app.route('/api/update/check')
def update_check():
    from hrma.utils.update_checker import check_for_update
    return jsonify(check_for_update())

@app.route('/api/update/download', methods=['POST'])
def update_download():
    from hrma.utils.update_checker import start_download
    return jsonify(start_download())

@app.route('/api/update/status')
def update_status():
    from hrma.utils.update_checker import download_status
    return jsonify(download_status())

@app.route('/api/update/open-download', methods=['POST'])
def update_open_download():
    # Manuel/yedek indirme: uygulama içi indirme yavaş/başarısız olursa
    # (GitHub CDN yavaşlığı, ağ kısıtı) kullanıcı buradan sistem tarayıcısında
    # doğrudan asset URL'sini (yoksa Releases sayfasını) açar. Sunucu tarafı
    # webbrowser.open olduğu için pywebview/exe, Chromium ve her tarayıcıda
    # aynı çalışır — istemci ortamına bağımlı değil.
    from hrma.utils.update_checker import open_download_in_browser
    return jsonify(open_download_in_browser())

@app.route('/test-simple')
def test_simple():
    return '<h1>SIMPLE TEST</h1><p>If you see this, Flask is working!</p><a href="/">Home Page</a>'

@app.route('/calculate', methods=['POST'])
def calculate():
    try:
        data = request.json

        # Determine motor type (default to hybrid for this endpoint)
        motor_type = data.get('motor_type', 'hybrid')

        # Use comprehensive validator
        is_valid, validation_messages = motor_validator.validate_motor_data(data, motor_type)
        if not is_valid:
            return jsonify({
                'error': 'Validation failed',
                'details': validation_messages,
                'motor_type': motor_type,
                'status': 'validation_error'
            }), 400

        # Log warnings but continue
        if validation_messages:
            app.logger.info(f"Validation warnings: {validation_messages}")
        
        # Create engine instance with support for total impulse
        # Only pass user-provided values, let the engine use fuel-specific defaults
        engine = HybridRocketEngine(
            thrust=data.get('thrust'),
            burn_time=data.get('burn_time'),
            total_impulse=data.get('total_impulse'),
            of_ratio=data.get('of_ratio', 1.0),
            chamber_pressure=data.get('chamber_pressure', 20.0),
            atmospheric_pressure=data.get('atmospheric_pressure', 1.0),
            chamber_temperature=data.get('chamber_temperature'),  # None if not provided
            gamma=data.get('gamma', 1.25),
            gas_constant=data.get('gas_constant'),  # None if not provided
            l_star=data.get('l_star', 1.0),
            expansion_ratio=data.get('expansion_ratio', 0),
            nozzle_type=data.get('nozzle_type', 'conical'),
            thrust_coefficient=data.get('thrust_coefficient', 0),
            regression_a=data.get('regression_a'),  # None if not provided
            regression_n=data.get('regression_n'),  # None if not provided
            fuel_density=data.get('fuel_density'),  # None if not provided
            combustion_type=data.get('combustion_type', 'infinite'),
            chamber_diameter_input=data.get('chamber_diameter_input', 0),
            fuel_type=data.get('fuel_type', 'htpb'),
            oxidizer_type=data.get('oxidizer_type', 'n2o'),
            injector_type=data.get('injector_type', 'showerhead'),
            initial_port_diameter=data.get('initial_port_diameter') or None,
            initial_gox=data.get('mass_flux_chamber') or None,
            tank_temperature=data.get('oxidizer_temp') or None,
            motor_name=data.get('motor_name', ''),
            motor_description=data.get('motor_description', '')
        )

        # Calculate motor geometry and performance
        motor_results = engine.calculate()

        # Design injector
        injector = InjectorDesign(
            mdot_ox=motor_results['mdot_ox'],
            chamber_pressure=data['chamber_pressure'],
            oxidizer_phase=data.get('oxidizer_phase', 'liquid'),
            oxidizer_density=data.get('oxidizer_density', 1220),
            oxidizer_viscosity=data.get('oxidizer_viscosity', 0.0002),
            oxidizer_temp=data.get('oxidizer_temp', 293),
            oxidizer_type=data.get('oxidizer_type', 'n2o'),
            tank_pressure=data.get('tank_pressure', 50.0),
            pressure_drop=data.get('pressure_drop', 0),
            discharge_coefficient=data.get('discharge_coefficient', 0.7),
            injector_type=data.get('injector_type', 'showerhead')
        )
        
        # Add type-specific parameters
        if data.get('injector_type', 'showerhead') == 'showerhead':
            injector.set_showerhead_params(
                target_velocity=data.get('target_velocity', 30),
                n_holes=data.get('n_holes', 0),
                hole_diameter_min=data.get('hole_diameter_min', 0.3),
                hole_diameter_max=data.get('hole_diameter_max', 2.0),
                plate_thickness=data.get('plate_thickness', 3.0)
            )
        elif data.get('injector_type', 'showerhead') == 'pintle':
            injector.set_pintle_params(
                outer_diameter=data.get('outer_diameter', 50),
                pintle_diameter=data.get('pintle_diameter', 25)
            )
        elif data.get('injector_type', 'showerhead') == 'swirl':
            injector.set_swirl_params(
                n_slots=data.get('n_slots', 6),
                slot_width=data.get('slot_width', 0),
                slot_height=data.get('slot_height', 0)
            )
        
        injector_results = injector.calculate()

        # Fizik limiti doğrulaması (ValidationSystem, Sutton & Biblarz +
        # NASA SP-8089 aralıkları): rapor üretilemezse /calculate ASLA
        # kırılmaz — hata loglanır, 'validation' anahtarı yanıttan atlanır.
        validation_report = None
        try:
            combo = f"{data.get('oxidizer_type', 'n2o')}_{data.get('fuel_type', 'htpb')}"
            if combo not in validator.performance_limits['specific_impulse']:
                combo = 'n2o_htpb'
            validation_report = validator.comprehensive_validation(
                motor_results, injector_results, combo
            )
        except Exception as val_error:
            app.logger.warning(f"Validation report skipped: {val_error}")

        # Create visualizations - Use improved visuals
        try:
            # New improved motor cross-section
            motor_plot = create_improved_motor_cross_section(motor_results)
        except Exception:
            # Fallback to old version if new one fails
            motor_plot = create_motor_plot(motor_results)
        
        try:
            # New improved injector design
            injector_plot = create_improved_injector_design(injector_results)
        except Exception:
            # Fallback to old version if new one fails
            injector_plot = create_injector_plot(injector_results, data['injector_type'])
        performance_plots = create_performance_plots(motor_results, injector_results)

        # plots.injector = enjektör tip şeması, plots.performance = dashboard.
        # (Eski davranış şemayı dashboard ile eziyordu; ayrı div'lerde
        # gösterilir — advanced.html #injector_plot / #performance_plots.)
        
        # Create advanced analysis visualizations
        #
        # Dalga 0 (2026-07-14): Isı ve yapısal analiz burada İKİNCİ kez
        # hesaplanıp plot'lanıyordu (plots.heat_transfer /
        # plots.structural_analysis) ama HİÇBİR şablon bu plot'ları render
        # etmiyordu — ~251 KB ölü yük + çifte hesap. Kaldırıldı. Motor
        # İÇİNDEKİ sonuçlar (motor.heat_transfer_analysis,
        # motor.structural_analysis) KALIR: 3D ısı haritası
        # (motor_viz3d.js) ve analiz panelleri onları okur.
        combustion_analysis_plot = None
        real_time_dashboard_plot = None
        motor_3d_plot = None

        # Generate combustion analysis
        if data.get('include_combustion_analysis', True):
            try:
                from hrma.engines.combustion_analysis import CombustionAnalyzer
                combustion_analyzer = CombustionAnalyzer()
                fuel_composition = {data.get('fuel_type', 'htpb'): 100.0}
                combustion_data = combustion_analyzer.analyze_combustion(
                    fuel_composition, 'N2O', data.get('of_ratio', 1.0),
                    data.get('chamber_pressure', 20.0)
                )
                combustion_analysis_plot = create_combustion_analysis_plots(combustion_data)
            except Exception as e:
                print(f"Combustion analysis error: {e}")
        
        # (Yapısal analiz çifte hesabı da kaldırıldı — bkz. yukarıdaki not.)

        # Generate real-time dashboard
        if data.get('include_realtime_dashboard', True):
            try:
                # Gerçek port_history serilerinden kur (eski 'time_history'
                # anahtarı hiç üretilmiyordu — alt 3 panel hep boştu)
                time_data = build_time_history(motor_results)
                real_time_dashboard_plot = create_real_time_dashboard(motor_results, time_data)
            except Exception as e:
                print(f"Real-time dashboard error: {e}")
        
        # Generate 3D visualization
        motor_3d_plot = None
        if data.get('include_3d_visualization', True):
            try:
                motor_3d_plot = create_3d_motor_visualization(motor_results)
            except Exception as viz_error:
                print(f"3D visualization error: {str(viz_error)}")
                motor_3d_plot = {'error': f'3D visualization failed: {str(viz_error)}'}
        
        # Create advanced analysis results
        cea_style_results = create_cea_style_results(motor_results)
        
        # Create additional plots if data is available
        altitude_performance_plot = None
        mass_fractions_plot = None
        thrust_altitude_plot = None
        
        if 'altitude_performance' in motor_results:
            altitude_performance_plot = create_altitude_performance_plot(
                motor_results['altitude_performance']['altitude_performance']
            )
        
        if 'mass_fractions' in motor_results:
            mass_fractions_plot = create_mass_fractions_plot(motor_results['mass_fractions'])
        
        if 'thrust_altitude_analysis' in motor_results:
            thrust_altitude_plot = create_thrust_altitude_plot(
                motor_results['thrust_altitude_analysis']['thrust_altitude_data']
            )
        
        # Generate OpenRocket export data
        openrocket_data = {
            'eng_file': openrocket_exporter.export_motor_file(motor_results),
            'motor_summary': openrocket_exporter.export_motor_summary(motor_results) if hasattr(openrocket_exporter, 'export_motor_summary') else {},
            'flight_profile': openrocket_exporter.create_flight_simulation_data(motor_results)
        }
        
        # Generate 3D CAD design
        cad_data = None
        if data.get('generate_cad', True):
            try:
                cad_data = cad_designer.generate_3d_motor_assembly(motor_results)
                
                # Export STL files if requested
                if data.get('export_stl', False):
                    if cad_data and 'assembly_meshes' in cad_data:
                        stl_files = cad_designer.export_stl_files(cad_data['assembly_meshes'])
                        cad_data['exported_stl_files'] = stl_files
            except Exception as cad_error:
                print(f"CAD generation error: {str(cad_error)}")
                cad_data = {'error': f'CAD generation failed: {str(cad_error)}'}
        
        # Calculate trajectory if requested
        trajectory_data = None
        if data.get('calculate_trajectory', True):
            # Set vehicle parameters
            trajectory_analyzer.set_vehicle_parameters(
                mass_dry=data.get('vehicle_mass_dry', 50),
                diameter=data.get('vehicle_diameter', 0.15),
                drag_coefficient=data.get('drag_coefficient', 0.5),
                length=data.get('vehicle_length', 2.0)
            )
            
            # Launch parameters
            launch_params = {
                'launch_angle': data.get('launch_angle', 85),
                'launch_altitude': data.get('launch_altitude', 0),
                'wind_speed': data.get('wind_speed', 0),
                'wind_direction': data.get('wind_direction', 0)
            }
            
            # Calculate trajectory
            try:
                trajectory_data = trajectory_analyzer.calculate_trajectory(motor_results, launch_params)
                trajectory_plot = trajectory_analyzer.create_trajectory_plots(trajectory_data)
            except Exception as traj_error:
                print(f"Trajectory calculation error: {str(traj_error)}")
                trajectory_data = {'error': f'Trajectory calculation failed: {str(traj_error)}'}
                trajectory_plot = None
        else:
            trajectory_plot = None
        
        # Combine results
        results = {
            'motor': motor_results,
            'injector': injector_results,
            'trajectory': trajectory_data,
            'cea_results': cea_style_results,
            'openrocket': openrocket_data,
            'cad_design': cad_data,
            # Design outputs from engine calculation
            'design_summary': motor_results.get('design_summary', {}),
            'nozzle_angles': motor_results.get('nozzle_angles', {}),
            'grain_design': motor_results.get('grain_design', {}),
            'injector_design': motor_results.get('injector_design', {}),
            'plots': {
                'motor': motor_plot,
                'injector': injector_plot,
                'performance': performance_plots,
                'trajectory': trajectory_plot,
                'altitude_performance': altitude_performance_plot,
                'mass_fractions': mass_fractions_plot,
                'thrust_altitude': thrust_altitude_plot,
                # 'heat_transfer' ve 'structural_analysis' plot anahtarları
                # bilinçli olarak KALDIRILDI (Dalga 0): hiçbir şablon render
                # etmiyordu; analiz panelleri motor.* sonuçlarını okur.
                'combustion_analysis': combustion_analysis_plot,
                'realtime_dashboard': real_time_dashboard_plot,
                'motor_3d': motor_3d_plot
            }
        }

        # ValidationSystem raporu (UI kontratı: results.validation)
        if validation_report is not None:
            results['validation'] = validation_report

        # Sanitize results to handle NaN and Infinity values
        try:
            sanitized_results = sanitize_json_values(results)

            # Test JSON serialization before returning
            test_json = json.dumps(sanitized_results, indent=2)

            return jsonify(sanitized_results)
            
        except (TypeError, ValueError) as json_error:
            print(f"JSON Serialization Error: {str(json_error)}")
            
            # Return basic results without problematic data
            basic_results = {
                'motor': {
                    'thrust': motor_results.get('thrust', 0),
                    'specific_impulse': motor_results.get('specific_impulse', 0),
                    'chamber_pressure': motor_results.get('chamber_pressure', 0),
                    'burn_time': motor_results.get('burn_time', 0)
                },
                'cea_results': cea_style_results if isinstance(cea_style_results, str) else "Calculation completed",
                'error_info': f"Full results had serialization issues: {str(json_error)}"
            }
            
            return jsonify(sanitize_json_values(basic_results))
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error in calculate: {str(e)}")
        print(f"Traceback: {error_traceback}")
        return jsonify({
            'error': str(e),
            'traceback': error_traceback,
            'received_data': data,
            'error_type': type(e).__name__
        }), 400

@app.route('/api/burn-rate/resolve', methods=['POST'])
def api_burn_rate_resolve():
    """Merkezi burn_rate_db rejim fitinden tasarım basıncında (a, n) çözer.

    Girdi:  {propellant: 'kndx'|'knsb', pressure_bar: float}
    Çıktı:  motor konvansiyonunda a-n (r[m/s] = a·P[bar]^n) + rejim aralığı,
            geçerlilik bayrağı ve kaynak künyesi. Katı sayfasındaki burn-rate
            preset dropdown'ı bu endpoint'le a/n alanlarını doldurur — böylece
            tasarım yolu ile korelasyon/doğrulama yolu AYNI merkezi katsayıyı
            kullanır (CLAUDE.md kural 11).
    """
    try:
        from hrma.data import burn_rate_db
        data = request.json or {}
        prop = str(data.get('propellant', '')).lower()
        if not burn_rate_db.has_law(prop):
            return jsonify({'status': 'error',
                            'error': f"No published burn-rate law for "
                                     f"'{prop}'. Available: "
                                     f"{sorted(burn_rate_db.BURN_RATE_LAWS)}"
                            }), 400
        p_bar = float(data.get('pressure_bar', 0))
        if not (0 < p_bar <= 1000):
            return jsonify({'status': 'error',
                            'error': 'pressure_bar must be in (0, 1000]'}), 400
        result = burn_rate_db.resolve_engine_coeffs(prop, p_bar)
        result['status'] = 'success'
        result['propellant'] = prop
        result['pressure_bar'] = p_bar
        return jsonify(result)
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400


@app.route('/api/quick-geometry', methods=['POST'])
def quick_geometry():
    """İnteraktif tasarım modu: yalnız motor çözücüsü + 2D kesit.

    /calculate'in ağır adımları (yörünge, CAD, OpenRocket, tüm grafikler)
    atlanır; 3D dijital ikiz ile kesitin slider'la canlı güncellenmesi için
    ~1 sn içinde geometri döndürür. Motor sözlüğü /calculate'teki
    results['motor'] ile aynı şemadadır (port_history ve
    heat_transfer_analysis dahil).
    """
    try:
        data = request.json or {}
        engine = HybridRocketEngine(
            thrust=data.get('thrust'),
            burn_time=data.get('burn_time'),
            total_impulse=data.get('total_impulse'),
            of_ratio=data.get('of_ratio', 1.0),
            chamber_pressure=data.get('chamber_pressure', 20.0),
            atmospheric_pressure=data.get('atmospheric_pressure', 1.0),
            chamber_temperature=data.get('chamber_temperature'),
            gamma=data.get('gamma', 1.25),
            gas_constant=data.get('gas_constant'),
            l_star=data.get('l_star', 1.0),
            expansion_ratio=data.get('expansion_ratio', 0),
            nozzle_type=data.get('nozzle_type', 'conical'),
            thrust_coefficient=data.get('thrust_coefficient', 0),
            regression_a=data.get('regression_a'),
            regression_n=data.get('regression_n'),
            fuel_density=data.get('fuel_density'),
            combustion_type=data.get('combustion_type', 'infinite'),
            chamber_diameter_input=data.get('chamber_diameter_input', 0),
            fuel_type=data.get('fuel_type', 'htpb'),
            oxidizer_type=data.get('oxidizer_type', 'n2o'),
            injector_type=data.get('injector_type', 'showerhead'),
            initial_port_diameter=data.get('initial_port_diameter') or None,
            initial_gox=data.get('mass_flux_chamber') or None,
            tank_temperature=data.get('oxidizer_temp') or None,
            motor_name=data.get('motor_name', ''),
            motor_description=data.get('motor_description', '')
        )
        motor_results = engine.calculate()

        try:
            motor_plot = create_improved_motor_cross_section(motor_results)
        except Exception as plot_err:
            print(f"Quick geometry cross-section error: {plot_err}")
            motor_plot = None

        return jsonify(sanitize_json_values({
            'status': 'success',
            'motor': motor_results,
            'plots': {'motor': motor_plot}
        }))
    except Exception as e:
        print(f"Quick geometry error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 400


@app.route('/api/transient-analysis', methods=['POST'])
def transient_analysis():
    """Zaman-çözümlü iç balistik: gerçek Pc(t) ve F(t) eğrileri.

    Girdi: /calculate ile aynı motor parametreleri + opsiyonel:
      feed_mode: 'regulated' (varsayılan) | 'blowdown'
      tank_temperature: blowdown tank başlangıç sıcaklığı [K, vars. 293.15]
      liquid_fill_fraction: tank sıvı doluluk oranı [vars. 0.85]

    Çıktı: time/thrust/chamber_pressure/of_ratio/port_diameter dizileri,
    blowdown'da tank basınç-sıcaklık geçmişi, durdurma olayı ve uyarılar.
    """
    try:
        data = request.json or {}
        engine = HybridRocketEngine(
            thrust=data.get('thrust'),
            burn_time=data.get('burn_time'),
            total_impulse=data.get('total_impulse'),
            of_ratio=data.get('of_ratio', 1.0),
            chamber_pressure=data.get('chamber_pressure', 20.0),
            atmospheric_pressure=data.get('atmospheric_pressure', 1.0),
            chamber_temperature=data.get('chamber_temperature'),
            gamma=data.get('gamma', 1.25),
            gas_constant=data.get('gas_constant'),
            l_star=data.get('l_star', 1.0),
            expansion_ratio=data.get('expansion_ratio', 0),
            nozzle_type=data.get('nozzle_type', 'conical'),
            thrust_coefficient=data.get('thrust_coefficient', 0),
            regression_a=data.get('regression_a'),
            regression_n=data.get('regression_n'),
            fuel_density=data.get('fuel_density'),
            combustion_type=data.get('combustion_type', 'infinite'),
            chamber_diameter_input=data.get('chamber_diameter_input', 0),
            fuel_type=data.get('fuel_type', 'htpb'),
            oxidizer_type=data.get('oxidizer_type', 'n2o'),
            injector_type=data.get('injector_type', 'showerhead'),
            initial_port_diameter=data.get('initial_port_diameter') or None,
            initial_gox=data.get('mass_flux_chamber') or None,
            tank_temperature=data.get('tank_temperature') or data.get('oxidizer_temp') or None,
        )
        engine.calculate()

        from hrma.analysis.transient_ballistics import (
            TransientBallistics, ThroatErosionModel)

        # Dalga 3 — opsiyonel boğaz erozyonu kuplajı (varsayılan KAPALI).
        # erosion_a_ref_mm_s: özel katsayı [mm/s @ 70 bar]; çelik/bakır gibi
        # 'not recommended' malzemelerde ZORUNLU (modelsiz ValueError → 400).
        erosion_model = None
        erosion_a_ref = data.get('erosion_a_ref_mm_s')
        if data.get('erosion_enabled') or erosion_a_ref is not None:
            erosion_model = ThroatErosionModel.for_material(
                data.get('throat_material', 'graphite'),
                a_ref_mm_s=(float(erosion_a_ref)
                            if erosion_a_ref is not None else None))

        solver = TransientBallistics(
            engine,
            feed_mode=data.get('feed_mode', 'regulated'),
            tank_temperature=float(data.get('tank_temperature', 293.15)),
            liquid_fill_fraction=float(data.get('liquid_fill_fraction', 0.85)),
            erosion_model=erosion_model,
        )
        tr = solver.solve()

        # Dizileri JSON'a uygun listelere çevir (sanitize NaN/Inf'i halleder)
        payload = {k: (v.tolist() if hasattr(v, 'tolist') else v)
                   for k, v in tr.items()}
        return jsonify(sanitize_json_values({
            'status': 'success',
            'transient': payload,
            'design_point': {
                'thrust': engine.F,
                'chamber_pressure_bar': engine.P_c,
                'burn_time': engine.t_b,
                'total_impulse_design': engine.F * engine.t_b,
            },
        }))
    except ValueError as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/injector-design', methods=['POST'])
def injector_design_api():
    """Enjektör tasarımı — docs/10_Enjektor_ARGE.md bölüm C sözleşmesi.

    Girdi: spec B.1 alanları (motor_type, injector_type, mdot_ox, ...).
    Kolaylık: from_results=true + motor_results bloğu gönderilirse
    mdot_ox/mdot_fuel/Pc_bar/T_c_K/mw_gas oradan doldurulur (istekte
    açıkça verilen alan kazanır).

    Yanıt: 200 {'status':'success','design':{...}} | 400 doğrulama |
    500 beklenmeyen hata. Saf hesaptır, dosya yazmaz.
    """
    try:
        data = request.json or {}
        spec = {k: v for k, v in data.items()
                if k not in ('from_results', 'motor_results')}

        if data.get('from_results') and isinstance(
                data.get('motor_results'), dict):
            mr = data['motor_results']
            for key in ('mdot_ox', 'mdot_fuel', 'Pc_bar', 'T_c_K', 'mw_gas'):
                if spec.get(key) in (None, '', 0) and mr.get(key) is not None:
                    spec[key] = mr[key]

        from hrma.engines.injector_design import design_injector
        design = design_injector(spec)
        if isinstance(design, dict) and design.get('status') == 'error':
            return jsonify({'status': 'error',
                            'error': design.get('error', 'tasarım hatası')}), 400
        return jsonify(sanitize_json_values(
            {'status': 'success', 'design': design}))
    except ValueError as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/six-dof-analysis', methods=['POST'])
def six_dof_analysis():
    """6-DOF rijit gövde uçuş analizi (Barrowman stabilite + weathercock).

    Girdi (JSON):
      Araç: body_diameter, body_length, nose_length [m], nose_type,
            dry_mass, propellant_mass [kg], cd0
      Kanat: fin_count, fin_root_chord, fin_tip_chord, fin_span,
             fin_sweep [m], fin_position (ops.)
      İtki: thrust [N] + burn_time [s] YA DA thrust_curve {time, thrust}
            (/api/transient-analysis çıktısı doğrudan verilebilir)
      Atış: launch_elevation_deg, launch_azimuth_deg, rail_length,
            wind_speed [m/s], wind_direction_deg (rüzgârın geldiği yön)
      CG:   x_cg_full, x_cg_empty [m, burundan] (ops.)

    Çıktı: apoje, maks hız/Mach/α, statik marj (dolu/boş), stabilite
    hükmü, yörünge zaman serileri (seyreltilmiş).
    """
    try:
        data = request.json or {}
        from hrma.analysis.six_dof_trajectory import (
            BarrowmanAero, SixDOFTrajectory)
        aero = BarrowmanAero(
            body_diameter=float(data.get('body_diameter', 0.1)),
            nose_length=float(data.get('nose_length', 0.3)),
            body_length=float(data.get('body_length', 2.0)),
            nose_type=data.get('nose_type', 'ogive'),
            fin_count=int(data.get('fin_count', 4)),
            fin_root_chord=float(data.get('fin_root_chord', 0.15)),
            fin_tip_chord=float(data.get('fin_tip_chord', 0.075)),
            fin_span=float(data.get('fin_span', 0.1)),
            fin_sweep=float(data.get('fin_sweep', 0.05)),
            fin_position=data.get('fin_position'),
        )
        solver = SixDOFTrajectory(
            aero=aero,
            dry_mass=float(data.get('dry_mass', 20.0)),
            propellant_mass=float(data.get('propellant_mass', 10.0)),
            thrust_curve=data.get('thrust_curve'),
            thrust=data.get('thrust'),
            burn_time=data.get('burn_time'),
            x_cg_full=data.get('x_cg_full'),
            x_cg_empty=data.get('x_cg_empty'),
            cd0=float(data.get('cd0', 0.5)),
            wind_speed=float(data.get('wind_speed', 0.0)),
            wind_direction_deg=float(data.get('wind_direction_deg', 0.0)),
            launch_elevation_deg=float(data.get('launch_elevation_deg', 90.0)),
            launch_azimuth_deg=float(data.get('launch_azimuth_deg', 0.0)),
            rail_length=float(data.get('rail_length', 5.0)),
        )
        res = solver.solve(t_max=float(data.get('t_max', 400.0)))

        # Zaman serilerini ~300 noktaya seyrelt
        import numpy as _np
        n = len(res['time'])
        idx = _np.linspace(0, n - 1, min(300, n)).astype(int)
        series = {
            'time': res['time'][idx].tolist(),
            'altitude': res['altitude'][idx].tolist(),
            'north': res['position'][0][idx].tolist(),
            'east': res['position'][1][idx].tolist(),
            'speed': res['speed'][idx].tolist(),
            'mach': res['mach'][idx].tolist(),
            'alpha_deg': res['alpha_deg'][idx].tolist(),
        }
        summary = {k: res[k] for k in (
            'apogee', 'apogee_time', 'max_speed', 'max_mach',
            'max_alpha_deg', 'static_margin_full', 'static_margin_empty',
            'stable', 'cn_alpha', 'x_cp', 'end_reason',
            'lateral_drift_at_end')}
        return jsonify(sanitize_json_values({
            'status': 'success', 'summary': summary, 'series': series}))
    except ValueError as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Dalga 3 — Analiz platformu endpoint'leri (docs/ANALIZ_PLATFORM_PLANI.md):
# basınçlı kap (ASME VIII / AIAA S-080 + Faupel burst), termal koruma
# (ablasyon Q* / heat-sink / radyasyon dengesi) ve cıvatalı bağlantı
# (Shigley). Modüller: hrma/analysis/{pressure_vessel, thermal_protection,
# bolted_joint}.py — burada yalnız girdi doğrulama + HTTP zarafeti var.
# ---------------------------------------------------------------------------

def _json_float(data, key):
    """JSON alanını float'a çevirir; yok / None / '' ise None döner.

    Sayıya çevrilemeyen değer ValueError yükseltir (endpoint 400'e çevirir).
    """
    v = data.get(key)
    if v is None or v == '':
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' must be a number (got {v!r})")


def _json_bool(data, key, default):
    """JSON alanını bool'a çevirir ('true'/'false' string'leri dahil)."""
    v = data.get(key)
    if v is None or v == '':
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ('true', '1', 'yes', 'on'):
        return True
    if s in ('false', '0', 'no', 'off'):
        return False
    raise ValueError(f"'{key}' must be a boolean (got {v!r})")


@app.route('/api/pressure-vessel-analysis', methods=['POST'])
def pressure_vessel_analysis():
    """Basınçlı kap boyutlandırma + gerçek kopma (burst) basıncı.

    Girdi (JSON): meop_bar (ZORUNLU), inner_diameter_mm (ZORUNLU),
      material (vars. 'aluminum_6061'), wall_thickness_mm (None → otomatik
      boyutlandırma), temperature_K (vars. 293.15), weld_efficiency
      {0.70, 0.85, 1.00} (vars. 1.0), head_type (vars. 'ellipsoidal_2_1'),
      code_mode 'aiaa_s080' (vars.) | 'asme_viii'.

    Yanıt 200: PressureVesselAnalyzer.analyze() sözlüğü (status alanı
    PASS/MARGINAL/FAIL; actual_burst_pressure_bar "kaç barda patlar").
    Hata 400: {'error': mesaj} — tüm girdi hataları ValueError.
    """
    try:
        data = request.json or {}
        from hrma.analysis.pressure_vessel import PressureVesselAnalyzer

        meop_bar = _json_float(data, 'meop_bar')
        inner_diameter_mm = _json_float(data, 'inner_diameter_mm')
        if meop_bar is None:
            raise ValueError(
                "'meop_bar' is required (maximum expected operating "
                "pressure, bar)")
        if inner_diameter_mm is None:
            raise ValueError("'inner_diameter_mm' is required")

        temperature_K = _json_float(data, 'temperature_K')
        weld_efficiency = _json_float(data, 'weld_efficiency')

        result = PressureVesselAnalyzer().analyze(
            meop_bar=meop_bar,
            inner_diameter_mm=inner_diameter_mm,
            material=data.get('material', 'aluminum_6061'),
            wall_thickness_mm=_json_float(data, 'wall_thickness_mm'),
            temperature_K=(293.15 if temperature_K is None
                           else temperature_K),
            weld_efficiency=(1.0 if weld_efficiency is None
                             else weld_efficiency),
            head_type=data.get('head_type', 'ellipsoidal_2_1'),
            code_mode=data.get('code_mode', 'aiaa_s080'),
        )
        return jsonify(sanitize_json_values(result))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# Termal koruma — mod bazlı parametre beyaz listeleri. Panel tek formdan
# tüm alanları gönderir; hedef modun kabul etmediği alanlar burada sessizce
# düşer (TypeError 500'e düşmesin). Anahtar adları modül imzalarıyla birebir
# (hrma/analysis/thermal_protection.py).
_TP_MODE_KEYS = {
    'ablative': ('q_net_W_m2', 'burn_time_s', 'time_s', 'material',
                 'design_margin', 'density_kg_m3'),
    'heat_sink': ('h_gas_W_m2K', 'T_recovery_K', 'burn_time_s',
                  'wall_thickness_m', 'wall_material', 'T_initial_K',
                  'n_nodes', 'cfl_safety', 'store_history'),
    'radiation_equilibrium': ('h_gas_W_m2K', 'T_recovery_K', 'emissivity',
                              'material'),
}


@app.route('/api/thermal-protection', methods=['POST'])
@app.route('/api/analysis/thermal-protection', methods=['POST'])
def thermal_protection_analysis():
    """Termal koruma analizi (üç mod).

    Girdi (JSON): {'mode': 'ablative' | 'heat_sink' |
    'radiation_equilibrium', ...mod parametreleri} — şema için
    hrma/analysis/thermal_protection.py docstring'lerine bakınız.

    Kolaylıklar (panel sözleşmesi):
      * ablative: 'q_star_MJ_kg' kabul edilir → q_star_J_kg (x 1e6).
      * radiation_equilibrium: 'radiation_material' kabul edilir →
        'material' (panel, ablatif malzeme seçicisiyle çakışmasın diye
        ayrı alan adı kullanır).
      * heat_sink: store_history verilmezse True (panel T_w(t) grafiği).

    Yanıt 200: ThermalProtectionAnalyzer.analyze() sözlüğü (model_note
    alanı 'Simplified model' rozetine bağlanır). Hata 400: {'error': ...}.
    """
    try:
        data = request.json or {}
        mode = data.get('mode', 'ablative')
        if mode not in _TP_MODE_KEYS:
            raise ValueError(
                f"Unknown mode '{mode}'. "
                f"Available: {sorted(_TP_MODE_KEYS)}")

        params = {k: data[k] for k in _TP_MODE_KEYS[mode]
                  if data.get(k) not in (None, '')}

        if mode == 'ablative' and data.get('q_star_MJ_kg') not in (None, ''):
            params['q_star_J_kg'] = float(data['q_star_MJ_kg']) * 1e6
        if (mode == 'radiation_equilibrium'
                and data.get('radiation_material') not in (None, '')):
            params['material'] = data['radiation_material']
        if mode == 'heat_sink':
            params['store_history'] = _json_bool(data, 'store_history', True)

        from hrma.analysis.thermal_protection import ThermalProtectionAnalyzer
        result = ThermalProtectionAnalyzer().analyze(mode, **params)
        return jsonify(sanitize_json_values(result))
    except (ValueError, KeyError) as e:
        # KeyError: bilinmeyen materials_db anahtarı (get_material)
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/bolted-joint', methods=['POST'])
def bolted_joint_analysis():
    """Cıvatalı bağlantı (flanş/kapak) analizi — Shigley yöntemi.

    Girdi (JSON): pressure_bar + seal_diameter_mm VEYA
    external_axial_load_n (en az biri zorunlu); bolt_count (ZORUNLU);
    size 'M4'..'M24' (vars. 'M8'); property_class '8.8'|'10.9'|'12.9'|
    'A2-70' (vars. '8.8'); grip_length_mm (vars. 20); member_material
    (materials_db anahtarı, vars. 'aluminum_6061'); lubricated (vars.
    false); reusable (vars. true).

    Yanıt 200: {'status': 'success', 'joint': {...}} — tork önerisi
    ±%25 ön-yük saçılım bandıyla, ayrılma marjı ve emniyet faktörleri.
    Hata 400: {'status': 'error', 'error': mesaj}.
    """
    try:
        data = request.json or {}
        from hrma.analysis.bolted_joint import analyze_bolted_joint

        pressure_bar = _json_float(data, 'pressure_bar')
        seal_diameter_mm = _json_float(data, 'seal_diameter_mm')
        external_load_n = _json_float(data, 'external_axial_load_n')
        if pressure_bar is None and external_load_n is None:
            raise ValueError(
                "Provide either 'pressure_bar' (with 'seal_diameter_mm') "
                "or 'external_axial_load_n'")

        bolt_count = data.get('bolt_count')
        if bolt_count in (None, ''):
            raise ValueError("'bolt_count' is required (integer >= 1)")
        try:
            bolt_count = int(bolt_count)
        except (TypeError, ValueError):
            raise ValueError(
                f"'bolt_count' must be an integer >= 1 (got {bolt_count!r})")

        grip_length_mm = _json_float(data, 'grip_length_mm')

        joint = analyze_bolted_joint(
            pressure_bar=pressure_bar,
            seal_diameter_mm=seal_diameter_mm,
            bolt_count=bolt_count,
            size=data.get('size', 'M8'),
            property_class=data.get('property_class', '8.8'),
            grip_length_mm=(20.0 if grip_length_mm is None
                            else grip_length_mm),
            member_material=data.get('member_material', 'aluminum_6061'),
            lubricated=_json_bool(data, 'lubricated', False),
            reusable=_json_bool(data, 'reusable', True),
            external_axial_load_n=external_load_n,
        )
        return jsonify(sanitize_json_values(
            {'status': 'success', 'joint': joint}))
    except (ValueError, KeyError) as e:
        # KeyError: bilinmeyen materials_db anahtarı (get_material)
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Dalga 4B — Soğutma & besleme sistemi endpoint'leri
# (docs/ANALIZ_PLATFORM_PLANI.md). Modüller literatür referanslı, HTTP katmanı
# burada yalnız girdi doğrulama + birim çevirisi + zarafet yapar:
#   /api/regen-cooling      -> hrma.analysis.regen_cooling.RegenCooling
#   /api/slosh-analysis     -> hrma.analysis.slosh_analysis.analyze_slosh
#   /api/pressurant-sizing  -> hrma.analysis.pressurant_sizing.analyze_pressurant
#   /api/water-hammer       -> hrma.analysis.water_hammer.WaterHammerAnalyzer
# Tüm modüller geçersiz girdide ValueError yükseltir -> endpoint 400'e çevirir.
# Basınçlar arayüzde bar; modül SI (Pa) beklediği için burada çevrilir.
# ---------------------------------------------------------------------------


def _bar_to_pa(data, key):
    """'<key>' alanını bar'dan Pa'ya çevirir; yok/boş ise None döner."""
    v = _json_float(data, key)
    return None if v is None else v * 1e5


@app.route('/api/regen-cooling', methods=['POST'])
def regen_cooling_analysis():
    """Rejeneratif soğutma 1D istasyon marşı (analiz modu — otomatik
    boyutlandırma YOK, kanal geometrisi kullanıcı girdisidir).

    Girdi (JSON): chamber_pressure (bar, ZORUNLU), chamber_temperature (K,
      ZORUNLU), throat_diameter (m, ZORUNLU); nozul için expansion_ratio (>1)
      VEYA exit_diameter (m) — en az biri; gamma (vars. 1.2),
      molecular_weight (g/mol, vars. 24); coolant 'water'|'rp1' (vars.
      water); coolant_mdot (kg/s, vars. 1); coolant_inlet_temp (K, vars.
      300); coolant_inlet_pressure (bar, vars. 30); n_channels (vars. 64);
      channel_width, channel_height, wall_thickness (MM — burada m'ye
      çevrilir); wall_material (materials_db anahtarı, vars. copper);
      flow_direction 'counterflow'|'coflow' (vars. counterflow); n_stations
      (20-50, vars. 40).

    Yanıt 200: {'status':'success', 'cooling': RegenCooling.solve()} —
      istasyon dizileri (x_mm, T_wall_hot_K, T_wall_cold_K, T_coolant_K,
      P_coolant_bar, q_MW_m2, velocity_m_s), summary (peak wall T, malzeme
      limiti, dP, çıkış T, koklaşma durumu, uyarılar) ve model_note.
    Hata 400: {'status':'error','error': mesaj} — tüm girdi hataları ValueError.
    """
    try:
        data = request.json or {}
        from hrma.analysis.regen_cooling import RegenCooling

        chamber_pressure_bar = _json_float(data, 'chamber_pressure')
        chamber_temperature = _json_float(data, 'chamber_temperature')
        throat_diameter = _json_float(data, 'throat_diameter')
        if chamber_pressure_bar is None:
            raise ValueError("'chamber_pressure' is required (bar)")
        if chamber_temperature is None:
            raise ValueError("'chamber_temperature' is required (K)")
        if throat_diameter is None:
            raise ValueError("'throat_diameter' is required (m)")

        gamma = _json_float(data, 'gamma')
        molecular_weight = _json_float(data, 'molecular_weight')
        coolant_mdot = _json_float(data, 'coolant_mdot')
        coolant_inlet_temp = _json_float(data, 'coolant_inlet_temp')
        coolant_inlet_pressure_bar = _json_float(data, 'coolant_inlet_pressure')
        n_channels = _json_float(data, 'n_channels')
        n_stations = _json_float(data, 'n_stations')
        expansion_ratio = _json_float(data, 'expansion_ratio')
        exit_diameter = _json_float(data, 'exit_diameter')

        # Kanal geometrisi arayüzde mm; modül SI (m) bekler.
        channel_width_mm = _json_float(data, 'channel_width')
        channel_height_mm = _json_float(data, 'channel_height')
        wall_thickness_mm = _json_float(data, 'wall_thickness')

        kwargs = dict(
            chamber_pressure=chamber_pressure_bar * 1e5,
            chamber_temperature=chamber_temperature,
            throat_diameter=throat_diameter,
            coolant=data.get('coolant', 'water'),
            wall_material=data.get('wall_material', 'copper'),
            flow_direction=data.get('flow_direction', 'counterflow'),
        )
        if gamma is not None:
            kwargs['gamma'] = gamma
        if molecular_weight is not None:
            kwargs['molecular_weight'] = molecular_weight
        if coolant_mdot is not None:
            kwargs['coolant_mdot'] = coolant_mdot
        if coolant_inlet_temp is not None:
            kwargs['coolant_inlet_temp'] = coolant_inlet_temp
        if coolant_inlet_pressure_bar is not None:
            kwargs['coolant_inlet_pressure'] = coolant_inlet_pressure_bar * 1e5
        if n_channels is not None:
            kwargs['n_channels'] = int(n_channels)
        if n_stations is not None:
            kwargs['n_stations'] = int(n_stations)
        if expansion_ratio is not None:
            kwargs['expansion_ratio'] = expansion_ratio
        if exit_diameter is not None:
            kwargs['exit_diameter'] = exit_diameter
        if channel_width_mm is not None:
            kwargs['channel_width'] = channel_width_mm / 1e3
        if channel_height_mm is not None:
            kwargs['channel_height'] = channel_height_mm / 1e3
        if wall_thickness_mm is not None:
            kwargs['wall_thickness'] = wall_thickness_mm / 1e3

        result = RegenCooling(**kwargs).solve()
        return jsonify(sanitize_json_values(
            {'status': 'success', 'cooling': result}))
    except (ValueError, KeyError) as e:
        # KeyError: bilinmeyen materials_db anahtarı (get_material)
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/slosh-analysis', methods=['POST'])
def slosh_analysis_api():
    """Yakıt çalkalanması (slosh) analizi — dik silindirik tank, doğrusal
    serbest yüzey teorisi (NASA SP-106 / Dodge 2000).

    Girdi (JSON): radius (m, ZORUNLU), fill_height (m, ZORUNLU), g_eff
      (m/s^2, vars. 9.80665), fluid_density (kg/m^3, ops.), liquid_mass
      (kg, ops.), baffle_width_ratio (w/R, ops. — verilmezse hedef sönümleme
      önerisi döner), baffle_depth_ratio (d_s/R, vars. 0.10),
      control_frequencies / structural_frequencies (Hz listeleri, ops.),
      coincidence_margin (vars. 0.20).

    Yanıt 200: {'status':'success', 'slosh': analyze_slosh()} — f1_hz,
      slosh_mass_ratio, pendulum_length, modes, fill_sweep (doluluk eğrisi
      dizileri), baffle (sönümleme), coincidence_warnings, model_note.
    Hata 400: {'status':'error','error': mesaj}.
    """
    try:
        data = request.json or {}
        from hrma.analysis.slosh_analysis import analyze_slosh

        radius = _json_float(data, 'radius')
        fill_height = _json_float(data, 'fill_height')
        if radius is None:
            raise ValueError("'radius' is required (m)")
        if fill_height is None:
            raise ValueError("'fill_height' is required (m)")

        g_eff = _json_float(data, 'g_eff')
        fluid_density = _json_float(data, 'fluid_density')
        liquid_mass = _json_float(data, 'liquid_mass')
        baffle_width_ratio = _json_float(data, 'baffle_width_ratio')
        baffle_depth_ratio = _json_float(data, 'baffle_depth_ratio')
        coincidence_margin = _json_float(data, 'coincidence_margin')

        def _freq_list(key):
            v = data.get(key)
            if v in (None, ''):
                return None
            if isinstance(v, (list, tuple)):
                out = [float(x) for x in v if x not in (None, '')]
                return out or None
            # virgülle ayrılmış string de kabul et (panel kolaylığı)
            try:
                out = [float(x) for x in str(v).split(',') if x.strip()]
                return out or None
            except (TypeError, ValueError):
                raise ValueError(f"'{key}' must be a list of frequencies [Hz]")

        analyze_kwargs = dict(
            radius=radius,
            fill_height=fill_height,
            g_eff=(9.80665 if g_eff is None else g_eff),
            fluid_density=fluid_density,
            liquid_mass=liquid_mass,
            baffle_depth_ratio=(0.10 if baffle_depth_ratio is None
                                else baffle_depth_ratio),
            control_frequencies=_freq_list('control_frequencies'),
            structural_frequencies=_freq_list('structural_frequencies'),
        )
        if baffle_width_ratio is not None:
            analyze_kwargs['baffle_width_ratio'] = baffle_width_ratio
        if coincidence_margin is not None:
            analyze_kwargs['coincidence_margin'] = coincidence_margin

        result = analyze_slosh(**analyze_kwargs)
        return jsonify(sanitize_json_values(
            {'status': 'success', 'slosh': result}))
    except (ValueError, KeyError) as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/pressurant-sizing', methods=['POST'])
def pressurant_sizing_api():
    """Basınçlandırıcı gaz (helyum/azot) boyutlandırma — regüleli veya
    blowdown besleme mimarisi (Sutton 9. baskı Böl. 6; Huzel & Huang Böl. 5).

    Girdi (JSON): mode 'regulated' (vars.) | 'blowdown'.
      Ortak: propellant_volume (m^3, ZORUNLU); gas 'helium'|'nitrogen';
        initial_temperature (K, vars. 293.15).
      regulated: tank_pressure (bar, ZORUNLU); storage_pressure (bar, vars.
        200); regulator_margin (vars. 0.10); collapse_factor (vars. 1.0).
      blowdown: initial_ullage_volume (m^3, ZORUNLU); initial_pressure (bar,
        ZORUNLU); polytropic_n (vars. 1.2).

    Yanıt 200: {'status':'success','mode':mode,'pressurant': result}.
    Hata 400: {'status':'error','error': mesaj}.
    """
    try:
        data = request.json or {}
        from hrma.analysis.pressurant_sizing import analyze_pressurant

        mode = str(data.get('mode', 'regulated')).strip().lower()
        if mode not in ('regulated', 'blowdown'):
            raise ValueError("'mode' must be 'regulated' or 'blowdown'")

        propellant_volume = _json_float(data, 'propellant_volume')
        if propellant_volume is None:
            raise ValueError("'propellant_volume' is required (m^3)")
        initial_temperature = _json_float(data, 'initial_temperature')
        gas = data.get('gas', 'helium' if mode == 'regulated' else 'nitrogen')

        if mode == 'regulated':
            tank_pressure_pa = _bar_to_pa(data, 'tank_pressure')
            if tank_pressure_pa is None:
                raise ValueError("'tank_pressure' is required (bar)")
            storage_pressure_pa = _bar_to_pa(data, 'storage_pressure')
            regulator_margin = _json_float(data, 'regulator_margin')
            collapse_factor = _json_float(data, 'collapse_factor')
            kwargs = dict(
                mode='regulated',
                propellant_volume=propellant_volume,
                tank_pressure=tank_pressure_pa,
                gas=gas,
            )
            if initial_temperature is not None:
                kwargs['initial_temperature'] = initial_temperature
            if storage_pressure_pa is not None:
                kwargs['storage_pressure'] = storage_pressure_pa
            if regulator_margin is not None:
                kwargs['regulator_margin'] = regulator_margin
            if collapse_factor is not None:
                kwargs['collapse_factor'] = collapse_factor
        else:  # blowdown
            initial_ullage_volume = _json_float(data, 'initial_ullage_volume')
            initial_pressure_pa = _bar_to_pa(data, 'initial_pressure')
            if initial_ullage_volume is None:
                raise ValueError("'initial_ullage_volume' is required (m^3)")
            if initial_pressure_pa is None:
                raise ValueError("'initial_pressure' is required (bar)")
            polytropic_n = _json_float(data, 'polytropic_n')
            kwargs = dict(
                mode='blowdown',
                propellant_volume=propellant_volume,
                initial_ullage_volume=initial_ullage_volume,
                initial_pressure=initial_pressure_pa,
                gas=gas,
            )
            if initial_temperature is not None:
                kwargs['initial_temperature'] = initial_temperature
            if polytropic_n is not None:
                kwargs['polytropic_n'] = polytropic_n

        result = analyze_pressurant(**kwargs)
        return jsonify(sanitize_json_values(
            {'status': 'success', 'mode': mode, 'pressurant': result}))
    except (ValueError, KeyError) as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/water-hammer', methods=['POST'])
def water_hammer_api():
    """Su koçu (water hammer) besleme hattı geçici basınç analizi
    (Joukowsky/Allievi + ince-cidar hoop basınç sınıfı kıyası).

    Girdi (JSON): fluid 'water'|'n2o'|'rp1'|'lox' (özel sıvı için
      bulk_modulus_Pa + density_kg_m3 birlikte); line_length_m (ZORUNLU),
      line_id_mm (ZORUNLU), wall_thickness_mm (ZORUNLU), working_pressure_bar
      (ZORUNLU); mdot_kg_s VEYA flow_velocity_m_s (en az biri); pipe_material
      (materials_db anahtarı, vars. ss_304); valve_closure_time_ms (ops. —
      None ani kapanma); pipe_mawp_bar (ops.); delta_v_m_s (ops.).

    Yanıt 200: {'status':'success','water_hammer': WaterHammerAnalyzer.
      analyze()} — wave_speed, critical_closure_time, joukowsky/applied
      pressure rise, peak_pressure, pipe MAWP/akma/kopma, status
      (SAFE/MARGINAL/UNSAFE), recommendation, recommended_closure_time_ms.
    Hata 400: {'status':'error','error': mesaj}.
    """
    try:
        data = request.json or {}
        from hrma.analysis.water_hammer import WaterHammerAnalyzer

        fluid = data.get('fluid', 'water')
        line_length_m = _json_float(data, 'line_length_m')
        line_id_mm = _json_float(data, 'line_id_mm')
        wall_thickness_mm = _json_float(data, 'wall_thickness_mm')
        working_pressure_bar = _json_float(data, 'working_pressure_bar')
        if line_length_m is None:
            raise ValueError("'line_length_m' is required (m)")
        if line_id_mm is None:
            raise ValueError("'line_id_mm' is required (mm)")
        if wall_thickness_mm is None:
            raise ValueError("'wall_thickness_mm' is required (mm)")
        if working_pressure_bar is None:
            raise ValueError("'working_pressure_bar' is required (bar)")

        result = WaterHammerAnalyzer().analyze(
            fluid=fluid,
            line_length_m=line_length_m,
            line_id_mm=line_id_mm,
            wall_thickness_mm=wall_thickness_mm,
            working_pressure_bar=working_pressure_bar,
            mdot_kg_s=_json_float(data, 'mdot_kg_s'),
            flow_velocity_m_s=_json_float(data, 'flow_velocity_m_s'),
            valve_closure_time_ms=_json_float(data, 'valve_closure_time_ms'),
            pipe_material=data.get('pipe_material', 'ss_304'),
            pipe_mawp_bar=_json_float(data, 'pipe_mawp_bar'),
            bulk_modulus_Pa=_json_float(data, 'bulk_modulus_Pa'),
            density_kg_m3=_json_float(data, 'density_kg_m3'),
            delta_v_m_s=_json_float(data, 'delta_v_m_s'),
        )
        return jsonify(sanitize_json_values(
            {'status': 'success', 'water_hammer': result}))
    except (ValueError, KeyError) as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/calculate_solid', methods=['POST'])
def calculate_solid():
    try:
        data = request.json
        print("Solid motor data received:", data)
        
        # Solid motor input validation
        chamber_diameter = data.get('chamber_diameter', 100)
        validate_input_range(chamber_diameter, 10, 2000, "Chamber diameter (mm)")
        
        grain_length = data.get('grain_length', 500)
        validate_input_range(grain_length, 50, 5000, "Grain length (mm)")
        
        core_diameter = data.get('core_diameter', 30)
        validate_input_range(core_diameter, 5, chamber_diameter-5, "Core diameter (mm)")
        
        chamber_pressure = data.get('chamber_pressure', 40)
        validate_input_range(chamber_pressure, 5, 200, "Chamber pressure (bar)")
        
        burn_rate_a = data.get('burn_rate_a', 0.005)
        validate_input_range(burn_rate_a, 0.0001, 0.1, "Burn rate coefficient")

        # Alt sınır -0.5: KN-şeker plateau/mesa rejimlerinde n NEGATİFTİR
        # (Nakka 1999 KNDX n=-0.148, KNSB n=-0.314 — bkz. burn_rate_db).
        # Eski [0.1, 1.0] aralığı merkezi db preset'lerini reddediyordu.
        burn_rate_n = data.get('burn_rate_n', 0.35)
        validate_input_range(burn_rate_n, -0.5, 1.0, "Burn rate exponent")
        
        # Create solid motor instance
        # overrides=data: formun yoğunluk/C*/gama/segman/star/sıcaklık gibi
        # alanları motora işlensin (2026-07-13 — girdi-backend kopukluğu fixi;
        # motor yalnız tanıdığı ve fiziksel aralıktaki anahtarları uygular)
        motor = SolidRocketEngine(
            grain_type=data.get('grain_type', 'bates'),
            propellant_type=data.get('propellant_type', 'apcp'),
            chamber_diameter=chamber_diameter,
            grain_length=grain_length,
            core_diameter=core_diameter,
            chamber_pressure=chamber_pressure,
            burn_rate_a=burn_rate_a,
            burn_rate_n=burn_rate_n,
            overrides=data
        )
        
        # Calculate motor performance
        results = motor.calculate_performance()

        # Sanitize results
        sanitized_results = sanitize_json_values(results)

        # Hibrit paritesi: motor kesiti + ortak geometri (2026-07-13)
        try:
            geo = solid_results_to_motor_geometry(sanitized_results)
            sanitized_results['motor_geometry'] = sanitize_json_values(geo)
            sanitized_results.setdefault('plots', {})['motor'] = \
                create_improved_motor_cross_section(geo, motor_type='solid')
        except Exception:
            traceback.print_exc()  # kesit çizimi hesabı düşürmesin

        # Hibrit paritesi (v2.5.2): performans panosu artık motor tipini
        # sonuç sözlüğünden kendisi tespit ediyor, tek argümanla çağrılır.
        try:
            sanitized_results.setdefault('plots', {})['performance'] = \
                create_performance_plots(sanitized_results)
        except Exception:
            traceback.print_exc()  # pano hesabı düşürmesin

        print("Solid motor calculation successful!")
        return jsonify(sanitized_results)
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Solid motor calculation error: {str(e)}")
        print(f"Traceback: {error_traceback}")
        return jsonify({
            'error': str(e),
            'traceback': error_traceback,
            'error_type': type(e).__name__
        }), 400

@app.route('/calculate_liquid', methods=['POST'])
def calculate_liquid():
    try:
        data = request.json
        print("Liquid motor data received:", data)
        
        # Liquid motor input validation
        thrust = data.get('thrust', 10000)
        validate_positive(thrust, "Thrust")
        validate_input_range(thrust, 100, 1e7, "Thrust (N)")
        
        chamber_pressure = data.get('chamber_pressure', 100)
        validate_input_range(chamber_pressure, 10, 500, "Chamber pressure (bar)")
        
        mixture_ratio = data.get('mixture_ratio', 2.5)
        validate_input_range(mixture_ratio, 0.5, 20, "Mixture ratio")
        
        # Validate tank pressure (Issue #6)
        tank_pressure = data.get('tank_pressure', chamber_pressure * 1.5)
        is_valid, msg = validation.validate_pressure_consistency(tank_pressure, chamber_pressure)
        if not is_valid:
            raise ValueError(msg)
        
        # Create liquid motor instance
        # v2.5.2: formdaki ~55 sayısal girdinin HİÇBİRİ motora ulaşmıyordu
        # (kurucu 7 parametre alıyordu, katı motordaki overrides bağlantısı
        # sıvıda hiç kurulmamıştı). Kullanıcı genişleme oranı, L*, soğutma
        # kanalı, enjektör ΔP gibi onlarca alanı doldurup sonucun değişmediğini
        # göremiyordu. Motor artık aralık doğrulamalı `overrides` kabul ediyor;
        # bağlanamayan alanlar sonuçta `unwired_inputs`, aralık dışı değerler
        # `input_warnings` ile AÇIKÇA beyan ediliyor (sessiz yutma yok).
        engine = LiquidRocketEngine(
            thrust=thrust,
            chamber_pressure=chamber_pressure,
            mixture_ratio=mixture_ratio,
            fuel_type=data.get('fuel_type', 'rp1'),
            oxidizer_type=data.get('oxidizer_type', 'lox'),
            cooling_type=data.get('cooling_type', 'regenerative'),
            injector_type=data.get('injector_type', 'impinging'),
            overrides=data
        )
        
        # Calculate engine performance
        results = engine.calculate_performance()

        # Sanitize results
        sanitized_results = sanitize_json_values(results)

        # Hibrit paritesi: motor kesiti + ortak geometri (2026-07-13)
        try:
            geo = liquid_results_to_motor_geometry(sanitized_results)
            sanitized_results['motor_geometry'] = sanitize_json_values(geo)
            sanitized_results.setdefault('plots', {})['motor'] = \
                create_improved_motor_cross_section(geo, motor_type='liquid')
        except Exception:
            traceback.print_exc()  # kesit çizimi hesabı düşürmesin

        # Hibrit paritesi (v2.5.2): performans panosu artık motor tipini
        # sonuç sözlüğünden kendisi tespit ediyor, tek argümanla çağrılır.
        try:
            sanitized_results.setdefault('plots', {})['performance'] = \
                create_performance_plots(sanitized_results)
        except Exception:
            traceback.print_exc()  # pano hesabı düşürmesin

        print("Liquid motor calculation successful!")
        return jsonify(sanitized_results)
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Liquid motor calculation error: {str(e)}")
        print(f"Traceback: {error_traceback}")
        return jsonify({
            'error': str(e),
            'traceback': error_traceback,
            'error_type': type(e).__name__
        }), 400

@app.route('/api/solid-monte-carlo', methods=['POST'])
def solid_monte_carlo():
    """Katı motor Monte Carlo analizi — üretim toleransı belirsizlikleri.

    Girdi: /calculate_solid ile aynı form alanları + opsiyonel n_samples.
    Çıktı: başarı oranı, itki/Isp/yanma süresi/tepe basıncı istatistikleri
    ve histogram verileri (frontend çizer).
    """
    try:
        data = request.json or {}
        motor = SolidRocketEngine(
            grain_type=data.get('grain_type', 'bates'),
            propellant_type=data.get('propellant_type', 'apcp'),
            chamber_diameter=data.get('chamber_diameter', 100),
            grain_length=data.get('grain_length', 500),
            core_diameter=data.get('core_diameter', 30),
            chamber_pressure=data.get('chamber_pressure', 40),
            burn_rate_a=data.get('burn_rate_a', 0.005),
            burn_rate_n=data.get('burn_rate_n', 0.35),
            overrides=data
        )
        mc = motor.run_monte_carlo(n_samples=int(data.get('n_samples', 300)))
        if mc.get('error'):
            return jsonify({'status': 'error', 'error': mc['error']}), 400
        return jsonify({'status': 'success', **sanitize_json_values(mc)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/export_tank_cad', methods=['POST'])
def export_tank_cad():
    """Export tank CAD files (STEP, STL, drawings)"""
    try:
        data = request.get_json()
        tank_data = data.get('tank_data')
        
        if not tank_data:
            return jsonify({'error': 'Tank data not found'}), 400
        
        # Import CAD generator
        from hrma.export.cad_export import cad_generator
        
        # Generate CAD files
        print("Generating tank CAD files...")
        zip_file_path = cad_generator.generate_tank_cad(tank_data)
        
        print(f"CAD files generated: {zip_file_path}")
        
        # Return zip file
        return send_file(
            zip_file_path,
            as_attachment=True,
            download_name=f'propellant_tanks_cad_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip',
            mimetype='application/zip'
        )
        
    except Exception as e:
        traceback.print_exc()
        print(f"CAD export error: {str(e)}")
        return jsonify({'error': f'CAD export error: {str(e)}'}), 500

def _motor_cad_zip_response(geo, motor_type, default_name):
    """Ortak CAD paket üreticisi: STEP (varsa) + STL'leri ZIP'ler.

    STEP build123d yoksa paket STL-only iner; MANIFEST durumu açıkça yazar
    (sessiz eksilme yasak). Enjektör katısı katıda, grain katısı sıvıda üretilmez.
    """
    name = geo.get('motor_name') or default_name
    arc = {}
    manifest = [f'HRMA CAD paketi — {name} ({motor_type})', '']

    # STEP (gerçek parametrik katılar)
    try:
        from hrma.export.step_export import generate_step_assembly
        step_files = generate_step_assembly(geo, motor_type=motor_type)
        for key, path in step_files.items():
            arc[f'step/{name}_{key}.step'] = path
        manifest.append(f'STEP: {len(step_files)} dosya (AP214, mm)')
    except Exception as e:
        manifest.append(f'STEP: FAILED ({e})')

    # STL (mesh'ler) — motor tipine uymayan bileşenler filtrelenir
    try:
        cad_data = cad_designer.generate_3d_motor_assembly(geo)
        meshes = cad_data.get('assembly_meshes') or []
        skip = {'solid': {'Injector'}, 'liquid': {'Fuel Grain'}}.get(motor_type, set())
        meshes = [(n, m) for n, m in meshes if n not in skip]
        stl_files = cad_designer.export_stl_files(meshes) if meshes else []
        for p in stl_files:
            arc[f'stl/{os.path.basename(p)}'] = p
        manifest.append(f'STL: {len(stl_files)} dosya (mm, 3D baskı/CAM)')
    except Exception as e:
        manifest.append(f'STL: FAILED ({e})')

    if not arc:
        return jsonify({'status': 'error',
                        'error': 'CAD üretilemedi: ' + ' | '.join(manifest)}), 500

    buf = _zip_files(arc, readme_text='\n'.join(manifest) + '\n')
    return send_file(buf, as_attachment=True,
                     download_name=f'{name}_CAD_package.zip',
                     mimetype='application/zip')


@app.route('/export_solid_motor_cad', methods=['POST'])
def export_solid_motor_cad():
    """Katı motor CAD paketi: STEP + STL (kamara, nozul, grain)."""
    try:
        data = request.get_json() or {}
        # JS ya ham /calculate_solid sonucunu ('results') ya da eski sözleşmeyle
        # 'motor_data' gönderir — ikisi de katı sonuç sözlüğü kabul edilir
        results = data.get('results') or data.get('motor_data')
        if not results:
            return jsonify({'error': 'Motor data not found'}), 400
        geo = solid_results_to_motor_geometry(results)
        return _motor_cad_zip_response(geo, 'solid', 'UZAYTEK_SOLID')
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'CAD export error: {str(e)}'}), 500


@app.route('/export_liquid_cad', methods=['POST'])
def export_liquid_cad():
    """Sıvı motor CAD paketi: STEP + STL (kamara, nozul, enjektör)."""
    try:
        data = request.get_json() or {}
        results = data.get('results') or data.get('motor_data')
        if not results:
            return jsonify({'error': 'Motor data not found'}), 400
        geo = liquid_results_to_motor_geometry(results)
        return _motor_cad_zip_response(geo, 'liquid', 'UZAYTEK_LIQUID')
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'CAD export error: {str(e)}'}), 500

@app.route('/parametric-analysis', methods=['POST'])
def parametric_analysis():
    """Parametric analysis for motor design optimization"""
    try:
        data = request.json
        
        # Get base parameters (all form data except sweep parameters)
        base_params = {k: v for k, v in data.items() if k not in ['param_type', 'param_start', 'param_end', 'param_steps']}
        
        # Get sweep parameters from the request
        sweep_param = data.get('param_type', 'of_ratio')
        param_start = data.get('param_start', 0.5)
        param_end = data.get('param_end', 3.0)
        sweep_points = data.get('param_steps', 20)
        
        sweep_range = [param_start, param_end]
        
        # Generate sweep values
        sweep_values = np.linspace(sweep_range[0], sweep_range[1], sweep_points)
        
        results = []
        
        for value in sweep_values:
            try:
                # Update sweep parameter
                current_params = base_params.copy()
                current_params[sweep_param] = value
                
                # Create engine with current parameters
                engine = HybridRocketEngine(
                    thrust=current_params.get('thrust'),
                    burn_time=current_params.get('burn_time'),
                    total_impulse=current_params.get('total_impulse'),
                    of_ratio=current_params.get('of_ratio', 1.0),
                    chamber_pressure=current_params.get('chamber_pressure', 20.0),
                    atmospheric_pressure=current_params.get('atmospheric_pressure', 1.0),
                    chamber_temperature=current_params.get('chamber_temperature'),  # None if not provided
                    gamma=current_params.get('gamma', 1.25),
                    gas_constant=current_params.get('gas_constant'),  # None if not provided
                    l_star=current_params.get('l_star', 1.0),
                    expansion_ratio=current_params.get('expansion_ratio', 0),
                    nozzle_type=current_params.get('nozzle_type', 'conical'),
                    thrust_coefficient=current_params.get('thrust_coefficient', 0),
                    regression_a=current_params.get('regression_a'),  # None if not provided
                    regression_n=current_params.get('regression_n'),  # None if not provided
                    fuel_density=current_params.get('fuel_density'),  # None if not provided
                    combustion_type=current_params.get('combustion_type', 'infinite'),
                    chamber_diameter_input=current_params.get('chamber_diameter_input', 0),
                    fuel_type=current_params.get('fuel_type', 'htpb')
                )
                
                # Calculate results
                motor_results = engine.calculate()
                
                # Store key results
                point_result = {
                    'sweep_value': value,
                    'isp': motor_results['isp'],
                    'thrust': motor_results['thrust'],
                    'total_impulse': motor_results['total_impulse'],
                    'chamber_pressure': motor_results['chamber_pressure'],
                    'propellant_mass_total': motor_results['propellant_mass_total'],
                    'throat_diameter': motor_results['throat_diameter'] * 1000,  # Convert to mm
                    'expansion_ratio': motor_results['expansion_ratio'],
                    'c_star': motor_results['c_star'],
                    'cf': motor_results['cf']
                }
                
                # Calculate trajectory if requested
                if data.get('include_trajectory', False):
                    trajectory_analyzer.set_vehicle_parameters(
                        mass_dry=data.get('vehicle_mass_dry', 50),
                        diameter=data.get('vehicle_diameter', 0.15)
                    )
                    
                    launch_params = {
                        'launch_angle': data.get('launch_angle', 85),
                        'launch_altitude': data.get('launch_altitude', 0)
                    }
                    
                    trajectory_data = trajectory_analyzer.calculate_trajectory(motor_results, launch_params)
                    point_result['max_altitude'] = trajectory_data['performance']['trajectory_metrics']['max_altitude']
                    point_result['max_velocity'] = trajectory_data['performance']['trajectory_metrics']['max_velocity']
                    point_result['total_flight_time'] = trajectory_data['performance']['trajectory_metrics']['total_flight_time']
                
                results.append(point_result)
                
            except Exception as e:
                # Skip failed points
                print(f"Failed calculation for {sweep_param}={value}: {str(e)}")
                continue
        
        # Create parametric analysis plot
        parametric_plot = create_parametric_plot(results, sweep_param)
        
        return jsonify({
            'sweep_parameter': sweep_param,
            'sweep_range': sweep_range,
            'results': results,
            'plot': parametric_plot,
            'plot_data': parametric_plot,  # Add plot_data field for compatibility
            'status': 'success'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400

def create_parametric_plot(results, sweep_param):
    """Create parametric analysis visualization"""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    
    if not results:
        return None
    
    # Extract data
    sweep_values = [r['sweep_value'] for r in results]
    isp_values = [r['isp'] for r in results]
    thrust_values = [r['thrust'] for r in results]
    mass_values = [r['propellant_mass_total'] for r in results]
    throat_diameter_values = [r['throat_diameter'] for r in results]
    
    # Create subplots
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            f'Specific Impulse vs {sweep_param.replace("_", " ").title()}',
            f'Thrust vs {sweep_param.replace("_", " ").title()}',
            f'Propellant Mass vs {sweep_param.replace("_", " ").title()}',
            f'Throat Diameter vs {sweep_param.replace("_", " ").title()}'
        )
    )
    
    # Isp plot
    fig.add_trace(
        go.Scatter(
            x=sweep_values,
            y=isp_values,
            mode='lines+markers',
            name='Specific Impulse',
            line=dict(color='blue', width=3),
            marker=dict(size=6)
        ),
        row=1, col=1
    )
    
    # Thrust plot
    fig.add_trace(
        go.Scatter(
            x=sweep_values,
            y=thrust_values,
            mode='lines+markers',
            name='Thrust',
            line=dict(color='red', width=3),
            marker=dict(size=6)
        ),
        row=1, col=2
    )
    
    # Mass plot
    fig.add_trace(
        go.Scatter(
            x=sweep_values,
            y=mass_values,
            mode='lines+markers',
            name='Propellant Mass',
            line=dict(color='green', width=3),
            marker=dict(size=6)
        ),
        row=2, col=1
    )
    
    # Throat diameter plot
    fig.add_trace(
        go.Scatter(
            x=sweep_values,
            y=throat_diameter_values,
            mode='lines+markers',
            name='Throat Diameter',
            line=dict(color='orange', width=3),
            marker=dict(size=6)
        ),
        row=2, col=2
    )
    
    # Add trajectory data if available
    if 'max_altitude' in results[0]:
        altitude_values = [r['max_altitude'] / 1000 for r in results]  # Convert to km
        fig.add_trace(
            go.Scatter(
                x=sweep_values,
                y=altitude_values,
                mode='lines+markers',
                name='Max Altitude (km)',
                line=dict(color='purple', width=3),
                marker=dict(size=6),
                yaxis='y5'
            ),
            row=1, col=1
        )
    
    # Update layout
    fig.update_layout(
        title=dict(
            text=f'Parametric Analysis: {sweep_param.replace("_", " ").title()} Sweep',
            x=0.5,
            font=dict(size=16, family='Arial')
        ),
        showlegend=False,
        height=600,
        width=1000
    )
    
    # Update axis labels
    fig.update_xaxes(title_text=sweep_param.replace('_', ' ').title(), row=1, col=1)
    fig.update_yaxes(title_text='Isp (s)', row=1, col=1)
    fig.update_xaxes(title_text=sweep_param.replace('_', ' ').title(), row=1, col=2)
    fig.update_yaxes(title_text='Thrust (N)', row=1, col=2)
    fig.update_xaxes(title_text=sweep_param.replace('_', ' ').title(), row=2, col=1)
    fig.update_yaxes(title_text='Mass (kg)', row=2, col=1)
    fig.update_xaxes(title_text=sweep_param.replace('_', ' ').title(), row=2, col=2)
    fig.update_yaxes(title_text='Throat Diameter (mm)', row=2, col=2)
    
    return fig.to_json()

@app.route('/api/comparative-analysis', methods=['POST'])
def comparative_analysis():
    """Create comparative analysis between multiple motor configurations.

    Dalga 4A onarımı (2026-07-14): eski kod eksik metrik anahtarlarında
    (thrust/isp/total_impulse/total_mass) KeyError -> 500 veriyordu.
    Şema doğrulaması artık onarılmış create_comparative_analysis_plot
    içinde yapılır (ValueError -> net 400 mesajı); "en iyi" sıralamaları
    yalnız ilgili metriği taşıyan konfigürasyonlar üzerinden hesaplanır.
    """
    try:
        data = request.get_json(silent=True) or {}
        motor_configs = data.get('motor_configs', {})

        if not isinstance(motor_configs, dict):
            return jsonify({
                'status': 'error',
                'error': ("motor_configs must be an object of "
                          "{config_name: {metric: value}} entries."),
            }), 400
        if len(motor_configs) < 2:
            return jsonify({
                'status': 'error',
                'error': ('At least 2 motor configurations are required '
                          'for comparison.'),
            }), 400

        # Onarılmış plot fonksiyonu: eksik anahtar tolere edilir, yapısal
        # bozukluk ValueError ile net mesaj verir (visualization.py).
        try:
            comparative_plot = create_comparative_analysis_plot(motor_configs)
        except ValueError as exc:
            return jsonify({'status': 'error', 'error': str(exc)}), 400

        def _numeric(value):
            return isinstance(value, (int, float)) and np.isfinite(value)

        def _best_by(metric_fn):
            # metric_fn(cfg) -> sayısal skor veya None; skoru olmayan
            # konfigürasyon sıralamaya girmez (eski kodun KeyError tuzağı)
            scored = {}
            for name, cfg in motor_configs.items():
                if not isinstance(cfg, dict):
                    continue
                score = metric_fn(cfg)
                if score is not None:
                    scored[name] = score
            if not scored:
                return None
            return max(scored, key=scored.get)

        best_thrust = _best_by(
            lambda c: c['thrust'] if _numeric(c.get('thrust')) else None)
        best_isp = _best_by(
            lambda c: c['isp'] if _numeric(c.get('isp')) else None)
        best_efficiency = _best_by(
            lambda c: (c['isp'] / c['total_mass'])
            if (_numeric(c.get('isp')) and _numeric(c.get('total_mass'))
                and c['total_mass'] > 0) else None)

        return jsonify({
            'status': 'success',
            'plot': comparative_plot,
            'analysis': {
                'best_thrust': best_thrust,
                'best_isp': best_isp,
                'best_efficiency': best_efficiency,
                'total_configs': len(motor_configs)
            }
        })

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/advanced-analysis', methods=['POST'])
def advanced_analysis():
    """Generate comprehensive advanced analysis plots"""
    try:
        data = request.json
        motor_data = data.get('motor_data', {})
        analysis_types = data.get('analysis_types', [])
        
        results = {}
        
        # Heat transfer analysis
        # Dalga 0 düzeltmesi (2026-07-14): analyze_chamber_thermal diye bir
        # metot HİÇ olmadı — bu dal her çağrıda AttributeError -> 500
        # veriyordu. Gerçek API analyze_heat_transfer'dir; girdi sözlüğü
        # onun beklediği anahtarlarla kurulur.
        if 'heat_transfer' in analysis_types:
            heat_analyzer = HeatTransferAnalyzer()
            ht_input = {
                'chamber_pressure': float(motor_data.get('chamber_pressure', 20.0)),   # bar
                'chamber_temperature': float(motor_data.get('chamber_temperature', 3000.0)),  # K
                'chamber_diameter': float(motor_data.get('chamber_diameter', 0.1)),    # m
                'chamber_length': float(motor_data.get('chamber_length', 0.5)),        # m
                'burn_time': float(motor_data.get('burn_time', 10.0)),                 # s
                'mdot_total': float(motor_data.get('mdot_total', 1.0)),                # kg/s
            }
            # Varsa gerçek gaz/boğaz değerlerini geçir (Bartz fallback'i yerine)
            for key in ('gamma', 'molecular_weight', 'gas_constant',
                        'throat_diameter', 'c_star'):
                if motor_data.get(key) is not None:
                    try:
                        ht_input[key] = float(motor_data[key])
                    except (TypeError, ValueError):
                        pass
            heat_data = heat_analyzer.analyze_heat_transfer(
                ht_input,
                material=data.get('material_type', 'steel'),
                wall_thickness=float(data.get('wall_thickness', 0.005)),
                cooling_type=data.get('cooling_type', 'natural')
            )
            # Plot fonksiyonunun beklediği zones/effectiveness alanlarını ekle
            if 'cooling_analysis' in heat_data and 'zones' not in heat_data['cooling_analysis']:
                ca = heat_data['cooling_analysis']
                ca['zones'] = ['Chamber', 'Throat', 'Nozzle']
                ca['effectiveness'] = [ca.get('cooling_efficiency', 0.8)] * 3
            results['heat_transfer_plot'] = create_heat_transfer_plots(heat_data)
            results['heat_analysis'] = heat_data
        
        # Combustion analysis
        if 'combustion' in analysis_types:
            from hrma.engines.combustion_analysis import CombustionAnalyzer
            combustion_analyzer = CombustionAnalyzer()
            fuel_composition = {data.get('fuel_type', 'htpb'): 100.0}
            combustion_data = combustion_analyzer.analyze_combustion(
                fuel_composition, 'N2O', data.get('of_ratio', 1.0),
                data.get('chamber_pressure', 20.0)
            )
            results['combustion_plot'] = create_combustion_analysis_plots(combustion_data)
            results['combustion_analysis'] = combustion_data
        
        # Structural analysis
        if 'structural' in analysis_types:
            structural_analyzer = StructuralAnalyzer()
            structural_data = structural_analyzer.analyze_structure(
                motor_data, material=data.get('material_type', 'steel_4130')
            )
            results['structural_plot'] = create_structural_analysis_plots(structural_data)
            results['structural_analysis'] = structural_data
        
        # 3D visualization
        if '3d_visualization' in analysis_types:
            results['motor_3d_plot'] = create_3d_motor_visualization(motor_data)
        
        # Real-time dashboard
        if 'realtime_dashboard' in analysis_types:
            time_data = build_time_history(motor_data)
            results['dashboard_plot'] = create_real_time_dashboard(motor_data, time_data)
        
        return jsonify({
            'status': 'success',
            'results': results
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/oxidizer-properties', methods=['POST'])
def get_live_oxidizer_properties():
    """Get oxidizer properties with proper data for different oxidizers"""
    try:
        data = request.json
        oxidizer_type = data.get('oxidizer_type', 'n2o')
        temperature = data.get('temperature', 293.15)
        
        print(f"OXIDIZER REQUEST: {oxidizer_type} at {temperature}K")
        
        # Define comprehensive oxidizer properties
        oxidizer_properties = {
            'n2o': {
                'density': get_oxidizer_density('n2o', temperature),
                'viscosity': 2.8e-4,
                'formula': 'N2O',
                'molecular_weight': 44.013,
                'boiling_point': 184.67,
                'vapor_pressure_20c': 5.17e6,  # Pa
                'enthalpy_formation': -82.05,  # kJ/mol
                'name': 'Nitrous Oxide',
                'phase_at_stp': 'gas',
                'storage_pressure': 5.17e6  # Pa, self-pressurizing
            },
            'lox': {
                'density': get_oxidizer_density('lox', temperature),
                'viscosity': 1.95e-4,
                'formula': 'O2',
                'molecular_weight': 31.998,
                'boiling_point': 90.15,
                'vapor_pressure_20c': 0,  # Cryogenic
                'enthalpy_formation': 0.0,
                'name': 'Liquid Oxygen',
                'phase_at_stp': 'liquid',
                'storage_pressure': 3.5e5  # Pa, typical tank pressure
            },
            'h2o2': {
                'density': 1450 - 1.5 * (temperature - 293.15),  # Temperature dependent
                'viscosity': 1.2e-3,
                'formula': 'H2O2',
                'molecular_weight': 34.015,
                'boiling_point': 423.35,
                'vapor_pressure_20c': 200,  # Pa
                'enthalpy_formation': -187.78,  # kJ/mol
                'name': 'Hydrogen Peroxide',
                'phase_at_stp': 'liquid',
                'storage_pressure': 1.5e5  # Pa
            },
            'air': {
                'density': 1.225 * (293.15 / temperature) * (101325 / 101325),  # Ideal gas
                'viscosity': 1.8e-5,
                'formula': 'Air',
                'molecular_weight': 28.97,
                'boiling_point': 78.8,  # N2 dominant
                'vapor_pressure_20c': 101325,  # Pa
                'enthalpy_formation': 0.0,
                'name': 'Compressed Air',
                'phase_at_stp': 'gas',
                'storage_pressure': 2.0e7  # Pa, high pressure
            }
        }
        
        if oxidizer_type in oxidizer_properties:
            properties = oxidizer_properties[oxidizer_type]
            
            print(f"OXIDIZER RESPONSE: {oxidizer_type} - density: {properties['density']:.1f} kg/m³")
            
            return jsonify({
                'status': 'success',
                'properties': properties,
                'source': 'HRMA Oxidizer Database',
                'temperature': temperature
            })
        else:
            return jsonify({
                'status': 'error', 
                'error': f'Unknown oxidizer type: {oxidizer_type}'
            })
        
    except Exception as e:
        print(f"Oxidizer properties error: {str(e)}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/validate-fuel', methods=['POST'])
def validate_fuel_composition():
    """Validate fuel composition with NASA CEA"""
    try:
        data = request.json
        composition = data.get('composition', [])
        
        # Convert composition to required format
        composition_tuples = [(comp['formula'], comp['percentage']) for comp in composition]
        
        result = db_manager.validate_fuel_composition(composition_tuples)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/database-status', methods=['GET'])
def check_database_status():
    """Check status of all database connections"""
    try:
        status = db_manager.test_connections()
        return jsonify(status)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/altitude-to-pressure', methods=['POST'])
def altitude_to_pressure():
    """Convert altitude to atmospheric pressure"""
    try:
        data = request.json
        altitude = data.get('altitude', 0)
        
        # Standard atmosphere calculation
        P0 = 1.01325  # Sea level pressure in bar
        T0 = 288.15   # Sea level temperature in K
        L = 0.0065    # Temperature lapse rate in K/m
        g = 9.80665   # Gravitational acceleration
        M = 0.0289644 # Molar mass of air
        R = 8.31432   # Universal gas constant
        
        if altitude < 11000:
            # Troposphere
            T = T0 - L * altitude
            pressure = P0 * (T / T0) ** ((g * M) / (R * L))
        else:
            # Simplified stratosphere
            T11 = T0 - L * 11000
            P11 = P0 * (T11 / T0) ** ((g * M) / (R * L))
            pressure = P11 * np.exp((-g * M * (altitude - 11000)) / (R * T11))
        
        return jsonify({
            'altitude': altitude,
            'pressure': pressure,
            'temperature': T if altitude < 11000 else T11
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Note: Removed duplicate /api/find-optimum-of endpoint - using the newer version below

@app.route('/api/export-eng', methods=['POST'])
def export_eng_file():
    """Export motor data as .eng file for OpenRocket"""
    try:
        data = request.json
        motor_data = data.get('motor_data', {})
        
        # Generate .eng file content
        eng_content = openrocket_exporter.export_eng_file(motor_data)
        
        # Generate filename
        motor_name = motor_data.get('motor_name', 'UZAYTEK-HRM-001')
        filename = f"{motor_name.replace(' ', '_')}.eng"
        
        return jsonify({
            'status': 'success',
            'filename': filename,
            'content': eng_content,
            'motor_summary': openrocket_exporter.export_motor_summary(motor_data)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ---------------------------------------------------------------------------
# GERÇEK export uçları (2026-07-13): DXF / çizim PDF'i / STEP / STL zip /
# komple paket. Eski popup butonları alert'ten ibaretti; artık her buton
# gerçek dosya indirir. Üreticiler: hrma/export/drawing_generator.py (kaleido
# + ezdxf + reportlab) ve hrma/export/step_export.py (build123d/OCC).
# ---------------------------------------------------------------------------

def _zip_files(file_map, readme_text=None):
    """{arşiv_adı: dosya_yolu} sözlüğünü bellekte ZIP'ler; BytesIO döner."""
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for arcname, path in file_map.items():
            if path and os.path.exists(path):
                zf.write(path, arcname)
        if readme_text:
            zf.writestr('README.txt', readme_text)
    buf.seek(0)
    return buf


@app.route('/api/export-dxf', methods=['POST'])
def export_dxf():
    """2D imalat çizimi (DXF): iç akış konturu + kamara + grain profili."""
    try:
        from hrma.export.drawing_generator import generate_dxf
        motor_data = (request.json or {}).get('motor_data', {})
        path = generate_dxf(motor_data)
        name = motor_data.get('motor_name', 'HRMA_MOTOR')
        return send_file(path, as_attachment=True,
                         download_name=f'{name}_profile.dxf',
                         mimetype='application/dxf')
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/export-drawings-pdf', methods=['POST'])
def export_drawings_pdf():
    """Antetli çok sayfalı teknik çizim PDF'i (kesit + enjektör + tablo)."""
    try:
        from hrma.export.drawing_generator import generate_drawing_pdf
        motor_data = (request.json or {}).get('motor_data', {})
        path = generate_drawing_pdf(motor_data)
        name = motor_data.get('motor_name', 'HRMA_MOTOR')
        return send_file(path, as_attachment=True,
                         download_name=f'{name}_technical_drawings.pdf',
                         mimetype='application/pdf')
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/export-step', methods=['POST'])
def export_step_files():
    """Gerçek STEP katıları (build123d): bileşenler + assembly, ZIP olarak."""
    try:
        from hrma.export.step_export import generate_step_assembly
        motor_data = (request.json or {}).get('motor_data', {})
        files = generate_step_assembly(motor_data)
        name = motor_data.get('motor_name', 'HRMA_MOTOR')
        arc = {f'{name}_{k}.step': p for k, p in files.items()}
        buf = _zip_files(arc, readme_text=(
            'HRMA STEP export (AP214)\n'
            'Solver-generated parametric solids: chamber, nozzle (true contour),\n'
            'fuel grain, injector plate (drilled orifices) + assembly.\n'
            'Units: millimetres.\n'))
        return send_file(buf, as_attachment=True,
                         download_name=f'{name}_STEP_package.zip',
                         mimetype='application/zip')
    except RuntimeError as e:
        # build123d yok — kullanıcıya açık mesaj (sessiz düşüş yasak)
        return jsonify({'status': 'error', 'error': str(e)}), 501
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/export-stl-zip', methods=['POST'])
def export_stl_zip():
    """Tüm bileşen STL'leri + birleşik assembly tek ZIP'te."""
    try:
        motor_data = (request.json or {}).get('motor_data', {})
        cad_data = cad_designer.generate_3d_motor_assembly(motor_data)
        if not cad_data or 'assembly_meshes' not in cad_data:
            return jsonify({'status': 'error',
                            'error': 'CAD montajı üretilemedi'}), 500
        stl_files = cad_designer.export_stl_files(cad_data['assembly_meshes'])
        if not stl_files:
            return jsonify({'status': 'error',
                            'error': 'STL üretilemedi'}), 500
        name = motor_data.get('motor_name', 'HRMA_MOTOR')
        arc = {os.path.basename(p): p for p in stl_files}
        buf = _zip_files(arc, readme_text=(
            'HRMA STL export\n'
            'Watertight closed-profile revolve solids from solver geometry.\n'
            'motor_assembly.stl = combined single-file model.\n'
            'Units: millimetres. Suitable for 3D printing / CAM import.\n'))
        return send_file(buf, as_attachment=True,
                         download_name=f'{name}_STL_package.zip',
                         mimetype='application/zip')
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/export-complete-zip', methods=['POST'])
def export_complete_zip():
    """Komple tasarım paketi: STL + DXF + çizim PDF'i + STEP + .eng + geometri.

    Her alt üretici bağımsız denenir; başaramayanlar MANIFEST'te 'FAILED'
    olarak raporlanır (paket sessizce eksilmez).
    """
    try:
        motor_data = (request.json or {}).get('motor_data', {})
        name = motor_data.get('motor_name', 'HRMA_MOTOR')
        arc = {}
        manifest = []

        def attempt(label, fn):
            try:
                fn()
                manifest.append(f'[OK]     {label}')
            except Exception as exc:
                manifest.append(f'[FAILED] {label}: {exc}')

        def add_stl():
            cad_data = cad_designer.generate_3d_motor_assembly(motor_data)
            for p in cad_designer.export_stl_files(cad_data['assembly_meshes']):
                arc[f'stl/{os.path.basename(p)}'] = p

        def add_dxf():
            from hrma.export.drawing_generator import generate_dxf
            arc[f'drawings/{name}_profile.dxf'] = generate_dxf(motor_data)

        def add_drawpdf():
            from hrma.export.drawing_generator import generate_drawing_pdf
            arc[f'drawings/{name}_technical_drawings.pdf'] = \
                generate_drawing_pdf(motor_data)

        def add_step():
            from hrma.export.step_export import generate_step_assembly
            for k, p in generate_step_assembly(motor_data).items():
                arc[f'step/{name}_{k}.step'] = p

        eng_holder = {}

        def add_eng():
            eng_holder['content'] = openrocket_exporter.export_motor_file(motor_data)

        attempt('STL solids', add_stl)
        attempt('DXF manufacturing profile', add_dxf)
        attempt('Technical drawing PDF', add_drawpdf)
        attempt('STEP solids (build123d)', add_step)
        attempt('OpenRocket .eng (real thrust curve if transient present)', add_eng)

        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for arcname, path in arc.items():
                if path and os.path.exists(path):
                    zf.write(path, arcname)
            if eng_holder.get('content'):
                zf.writestr(f'openrocket/{name}.eng', eng_holder['content'])
            zf.writestr('geometry/motor_geometry.json',
                        json.dumps(sanitize_json_values(motor_data), indent=2))
            zf.writestr('MANIFEST.txt',
                        'HRMA COMPLETE DESIGN PACKAGE\n'
                        + datetime.now().strftime('%Y-%m-%d %H:%M') + '\n\n'
                        + '\n'.join(manifest) + '\n')
        buf.seek(0)
        return send_file(buf, as_attachment=True,
                         download_name=f'{name}_complete_package.zip',
                         mimetype='application/zip')
    except Exception as e:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/export-cad', methods=['POST'])
def export_cad_files():
    """Export CAD files (STL, technical drawings, etc.)"""
    try:
        data = request.json
        motor_data = data.get('motor_data', {})
        export_formats = data.get('formats', ['stl', 'technical_drawings'])
        
        results = {}
        
        # Generate CAD assembly
        cad_data = cad_designer.generate_3d_motor_assembly(motor_data)
        
        # Export STL files if requested
        if 'stl' in export_formats:
            stl_files = cad_designer.export_stl_files(cad_data['assembly_meshes'])
            results['stl_files'] = stl_files
            results['stl_download_links'] = [f"/download/stl/{file.split('/')[-1]}" for file in stl_files]
        
        # Technical drawings
        if 'technical_drawings' in export_formats:
            results['technical_drawings'] = cad_data['technical_drawings']
        
        # Material specifications
        if 'materials' in export_formats:
            results['material_specs'] = cad_data['material_specifications']
            results['manufacturing_notes'] = cad_data['manufacturing_notes']
        
        # 3D visualization
        if '3d_plot' in export_formats:
            results['plotly_3d'] = cad_data['plotly_visualization']
        
        # Performance summary
        results['performance_summary'] = cad_data['performance_summary']
        
        return jsonify({
            'status': 'success',
            'cad_exports': results,
            'motor_name': motor_data.get('motor_name', 'UZAYTEK-HRM-001')
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/export-openrocket', methods=['POST'])
def export_openrocket_files():
    """Export OpenRocket compatible files"""
    try:
        data = request.json
        motor_data = data.get('motor_data', {})
        rocket_params = data.get('rocket_params', None)
        
        # Generate motor file (.eng format)
        eng_content = openrocket_exporter.export_motor_file(motor_data)
        
        # Generate flight simulation data
        flight_data = openrocket_exporter.create_flight_simulation_data(motor_data, rocket_params)
        
        # Generate motor designation
        # v2.5.2 (Codex bulgusu): burada kendi kopyası kuruluyordu ve
        # throat_diameter'ı METRE varsayıp 1000 ile çarpıyordu. Katı motorda
        # o alan zaten mm olduğu için isimlendirme "N47927-..." çıkıyordu.
        # Tek doğruluk kaynağı dışa aktarıcının kendi çözücüsüdür (normalize
        # motor_geometry varsa ondan, yoksa büyüklük çıkarımıyla).
        motor_designation = openrocket_exporter._designation(motor_data)
        
        return jsonify({
            'status': 'success',
            'motor_designation': motor_designation,
            'eng_file_content': eng_content,
            'flight_simulation': flight_data,
            'download_filename': f"{motor_designation}.eng",
            'openrocket_instructions': [
                "1. Save the .eng file to OpenRocket's motor directory",
                "2. In OpenRocket, go to Edit → Preferences → Motors",
                "3. Add the motor directory path",
                "4. Select your motor in the motor selection dialog",
                "5. Run simulation with your rocket design"
            ]
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/generate-complete-package', methods=['POST'])
def generate_complete_design_package():
    """Generate complete motor design package with all files"""
    try:
        data = request.json
        motor_data = data.get('motor_data', {})
        package_options = data.get('package_options', {
            'include_cad': True,
            'include_openrocket': True,
            'include_analysis': True,
            'include_manufacturing': True
        })
        
        complete_package = {}
        
        # CAD files and drawings
        if package_options.get('include_cad', True):
            cad_data = cad_designer.generate_3d_motor_assembly(motor_data)
            stl_files = cad_designer.export_stl_files(cad_data['assembly_meshes'])
            
            complete_package['cad'] = {
                'stl_files': stl_files,
                'technical_drawings': cad_data['technical_drawings'],
                'material_specifications': cad_data['material_specifications'],
                'plotly_3d_model': cad_data['plotly_visualization'],
                'performance_summary': cad_data['performance_summary']
            }
        
        # OpenRocket integration
        if package_options.get('include_openrocket', True):
            eng_content = openrocket_exporter.export_motor_file(motor_data)
            flight_data = openrocket_exporter.create_flight_simulation_data(motor_data)
            
            complete_package['openrocket'] = {
                'eng_file': eng_content,
                'flight_simulation': flight_data,
                'motor_class': openrocket_exporter._get_motor_class(motor_data.get('total_impulse', 10000))
            }
        
        # Analysis reports
        if package_options.get('include_analysis', True):
            # Dalga 2 (2026-07-14): Eski sabit 'safety_factor: 4.0' ve ondan
            # türetilen uydurma burst_pressure/material_limits kaldırıldı.
            # Gerçek yapısal analiz sonucu varsa o raporlanır; yoksa alan
            # 'NOT ANALYZED' olarak işaretlenir — değer UYDURULMAZ.
            structural_pkg = motor_data.get('structural_analysis') or {}
            safety_sub_pkg = structural_pkg.get('safety_analysis') or {}
            safety_section = {
                'chamber_pressure': motor_data.get('chamber_pressure', 0),
            }
            if structural_pkg.get('safety_factor') is not None:
                safety_section.update({
                    'safety_factor': structural_pkg.get('safety_factor'),
                    'safety_factor_pressure': structural_pkg.get('safety_factor_pressure'),
                    'safety_factor_total': structural_pkg.get('safety_factor_total'),
                    'status': safety_sub_pkg.get('status', 'UNKNOWN'),
                    'risk_level': safety_sub_pkg.get('risk_level', 'UNKNOWN'),
                })
            else:
                safety_section.update({
                    'safety_factor': None,
                    'status': 'NOT ANALYZED',
                    'note': 'Run the structural analysis to obtain real safety factors.',
                })
            complete_package['analysis'] = {
                'motor_performance': motor_data,
                'safety_analysis': safety_section,
                'weight_breakdown': {
                    'chamber_mass': cad_data['performance_summary']['mass_breakdown']['chamber_mass'] if 'cad_data' in locals() else 'N/A',
                    'nozzle_mass': cad_data['performance_summary']['mass_breakdown']['nozzle_mass'] if 'cad_data' in locals() else 'N/A',
                    'total_dry_mass': cad_data['performance_summary']['mass_breakdown']['total_dry_mass'] if 'cad_data' in locals() else 'N/A'
                }
            }
        
        # Manufacturing package
        if package_options.get('include_manufacturing', True):
            complete_package['manufacturing'] = {
                'bill_of_materials': [
                    {'part': 'Combustion Chamber', 'material': 'AISI 304 SS', 'quantity': 1},
                    {'part': 'Nozzle', 'material': 'Graphite ATJ', 'quantity': 1},
                    {'part': 'Injector Head', 'material': 'AISI 316 SS', 'quantity': 1},
                    {'part': 'O-rings', 'material': 'Viton', 'quantity': 3},
                    {'part': 'Bolts M8x30', 'material': 'Steel', 'quantity': 8}
                ],
                'manufacturing_notes': cad_data['manufacturing_notes'] if 'cad_data' in locals() else [],
                'assembly_instructions': [
                    "1. Machine all components per technical drawings",
                    "2. Pressure test chamber to 1.5x operating pressure",
                    "3. Install fuel grain with proper centering",
                    "4. Mount nozzle with high-temp sealant",
                    "5. Attach injector with O-ring seals",
                    "6. Perform final leak test before use"
                ],
                'quality_control': [
                    "Visual inspection of all welds",
                    "Dimensional verification ±0.1mm",
                    "Surface finish Ra 3.2 μm max",
                    "Pressure test certification"
                ]
            }
        
        # Generate summary report
        motor_name = motor_data.get('motor_name', 'UZAYTEK-HRM-001')
        complete_package['summary'] = {
            'motor_designation': motor_name,
            'total_impulse': f"{motor_data.get('total_impulse', 0):.0f} N⋅s",
            'thrust': f"{motor_data.get('thrust', 0):.0f} N",
            'burn_time': f"{motor_data.get('burn_time', 0):.1f} s",
            'isp': f"{motor_data.get('isp', 0):.1f} s",
            'chamber_pressure': f"{motor_data.get('chamber_pressure', 0):.1f} bar",
            'design_status': 'Ready for manufacturing',
            'estimated_cost': '$500-800 USD',
            'development_time': '2-4 weeks'
        }
        
        return jsonify({
            'status': 'success',
            'complete_package': complete_package,
            'package_info': {
                'motor_name': motor_name,
                'generation_date': datetime.now().isoformat(),
                'package_version': '1.0',
                'files_included': len([k for k, v in package_options.items() if v])
            }
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/download/stl/<filename>')
def download_stl_file(filename):
    """Download STL files"""
    try:
        import os
        
        file_path = f"./cad_exports/{filename}"
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return jsonify({'error': 'File not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export-simulation', methods=['POST'])
def export_simulation_file():
    """Export complete simulation data for OpenRocket"""
    try:
        data = request.json
        motor_data = data.get('motor_data', {})
        rocket_data = data.get('rocket_data', None)
        
        # Generate simulation file
        simulation_content = openrocket_exporter.create_simulation_file(motor_data, rocket_data)
        flight_profile = openrocket_exporter.generate_flight_profile(motor_data, rocket_data)
        
        motor_name = motor_data.get('motor_name', 'UZAYTEK-HRM-001')
        filename = f"{motor_name.replace(' ', '_')}_simulation.json"
        
        return jsonify({
            'status': 'success',
            'filename': filename,
            'simulation_content': simulation_content,
            'flight_profile': flight_profile
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/generate-3d', methods=['POST'])
def generate_3d():
    """Generate 3D visualization for motor"""
    try:
        data = request.json
        motor_data = data.get('motor_data', {})
        injector_data = data.get('injector_data', {})
        
        # Generate 3D visualization safely
        try:
            from hrma.visualization.visualization import create_3d_motor_visualization
            motor_3d_plot = create_3d_motor_visualization(motor_data)
        except Exception as viz_error:
            # Fallback: Create simple 3D plot
            import plotly.graph_objects as go
            fig = go.Figure()
            
            # Simple 3D cylinder representation
            theta = np.linspace(0, 2*np.pi, 20)
            z = np.linspace(0, 100, 20)
            theta_mesh, z_mesh = np.meshgrid(theta, z)
            x = 50 * np.cos(theta_mesh)
            y = 50 * np.sin(theta_mesh)
            
            fig.add_trace(go.Surface(
                x=x, y=y, z=z_mesh,
                colorscale='Viridis',
                name='Motor Chamber'
            ))
            
            fig.update_layout(
                title='3D Motor Visualization',
                scene=dict(
                    xaxis_title='X (mm)',
                    yaxis_title='Y (mm)',
                    zaxis_title='Z (mm)'
                ),
                width=800,
                height=600
            )
            
            motor_3d_plot = fig.to_json()
        
        return jsonify({
            'status': 'success',
            'plot_data': motor_3d_plot
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/export-stl', methods=['POST'])
def export_stl():
    """Export motor design as STL file with comprehensive error handling"""
    try:
        data = request.json
        motor_data = data.get('motor_data', {})
        motor_type = motor_data.get('motor_type', 'hybrid')
        
        # Validate export request
        is_valid, validation_msg = motor_validator.validate_export_request(data, 'stl')
        if not is_valid:
            return jsonify({
                'error': validation_msg,
                'status': 'failed'
            }), 400
        
        # Sanitize motor data for safe processing
        motor_data = motor_validator.sanitize_export_data(motor_data)
        
        # Ensure critical parameters exist for different motor types
        if motor_type == 'hybrid':
            # Hybrid motor specific requirements
            if 'fuel_type' not in motor_data:
                motor_data['fuel_type'] = 'htpb'
            if 'oxidizer_type' not in motor_data:
                motor_data['oxidizer_type'] = 'n2o'
            if 'port_diameter' not in motor_data and 'thrust' in motor_data:
                # Estimate port diameter from thrust
                motor_data['port_diameter'] = 0.02 * np.sqrt(motor_data['thrust'] / 1000)
        elif motor_type == 'solid':
            if 'propellant_type' not in motor_data:
                motor_data['propellant_type'] = 'apcp'
            if 'grain_geometry' not in motor_data:
                motor_data['grain_geometry'] = 'bates'
        elif motor_type == 'liquid':
            if 'fuel_type' not in motor_data:
                motor_data['fuel_type'] = 'rp1'
            if 'oxidizer_type' not in motor_data:
                motor_data['oxidizer_type'] = 'lox'
        
        # Generate 3D CAD model using the CAD designer
        print(f"Generating 3D assembly for {motor_type} motor...")
        print(f"Motor data: {json.dumps(motor_data, indent=2)}")
        
        try:
            cad_data = cad_designer.generate_3d_motor_assembly(motor_data)
        except Exception as cad_error:
            print(f"CAD generation error: {str(cad_error)}")
            # Provide fallback basic geometry
            cad_data = generate_fallback_cad_geometry(motor_data, motor_type)
        
        # Export STL files to disk
        if cad_data and 'assembly_meshes' in cad_data:
            print("Exporting STL files...")
            try:
                stl_files = cad_designer.export_stl_files(cad_data['assembly_meshes'])
            except Exception as export_error:
                print(f"STL export error: {str(export_error)}")
                # Generate basic STL content directly
                stl_content = generate_basic_stl_content(motor_data, motor_type)
                motor_name = motor_data.get('motor_name', f'UZAYTEK_{motor_type.upper()}_Motor')
                filename = f"{motor_name.replace(' ', '_')}_{motor_type}.stl"
                
                from flask import Response
                return Response(
                    stl_content.encode('utf-8') if isinstance(stl_content, str) else stl_content,
                    mimetype='application/sla',
                    headers={'Content-Disposition': f'attachment;filename={filename}'}
                )
            
            # Read the main motor assembly STL file
            if stl_files:
                main_stl_path = None
                for file_path in stl_files:
                    if 'motor_assembly' in file_path.lower() or 'complete' in file_path.lower():
                        main_stl_path = file_path
                        break
                
                # If no main assembly found, use the first file
                if not main_stl_path:
                    main_stl_path = stl_files[0]
                
                # Read the STL file content
                import os
                if os.path.exists(main_stl_path):
                    with open(main_stl_path, 'rb') as f:
                        stl_content = f.read()
                else:
                    # Generate basic STL if file not found
                    stl_content = generate_basic_stl_content(motor_data, motor_type)
                    stl_content = stl_content.encode('utf-8') if isinstance(stl_content, str) else stl_content
                
                # Create filename from motor data
                motor_name = motor_data.get('motor_name', f'UZAYTEK_{motor_type.upper()}_Motor')
                filename = f"{motor_name.replace(' ', '_')}_{motor_type}.stl"
                
                # Create response with STL file
                from flask import Response
                return Response(
                    stl_content,
                    mimetype='application/sla',
                    headers={'Content-Disposition': f'attachment;filename={filename}'}
                )
            else:
                # Generate basic STL content as fallback
                stl_content = generate_basic_stl_content(motor_data, motor_type)
                motor_name = motor_data.get('motor_name', f'UZAYTEK_{motor_type.upper()}_Motor')
                filename = f"{motor_name.replace(' ', '_')}_{motor_type}.stl"
                
                from flask import Response
                return Response(
                    stl_content.encode('utf-8') if isinstance(stl_content, str) else stl_content,
                    mimetype='application/sla',
                    headers={'Content-Disposition': f'attachment;filename={filename}'}
                )
        else:
            # Generate basic STL content as final fallback
            stl_content = generate_basic_stl_content(motor_data, motor_type)
            motor_name = motor_data.get('motor_name', f'UZAYTEK_{motor_type.upper()}_Motor')
            filename = f"{motor_name.replace(' ', '_')}_{motor_type}.stl"
            
            from flask import Response
            return Response(
                stl_content.encode('utf-8') if isinstance(stl_content, str) else stl_content,
                mimetype='application/sla',
                headers={'Content-Disposition': f'attachment;filename={filename}'}
            )
        
    except Exception as e:
        error_msg = f"STL Export Error: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        
        # Return error response
        return jsonify({
            'error': error_msg,
            'details': str(e),
            'traceback': traceback.format_exc(),
            'status': 'failed'
        }), 500

def generate_basic_stl_content(motor_data, motor_type):
    """Generate basic STL content for motor geometry"""
    try:
        # Get motor dimensions
        chamber_length = motor_data.get('chamber_length', 0.5) * 1000  # Convert to mm
        chamber_diameter = motor_data.get('chamber_diameter', 0.1) * 1000  # Convert to mm
        throat_diameter = motor_data.get('throat_diameter', 0.03) * 1000  # Convert to mm
        exit_diameter = motor_data.get('exit_diameter', throat_diameter * 2)  # Convert to mm
        
        # Generate a basic cylindrical chamber with nozzle representation
        stl_content = f"""solid {motor_type}_motor
facet normal 0 0 -1
  outer loop
    vertex 0 0 0
    vertex {chamber_diameter/2} 0 0
    vertex {chamber_diameter/2 * 0.866} {chamber_diameter/4} 0
  endloop
endfacet
facet normal 0 0 -1
  outer loop
    vertex 0 0 0
    vertex {chamber_diameter/2 * 0.866} {chamber_diameter/4} 0
    vertex {chamber_diameter/2 * 0.5} {chamber_diameter/2 * 0.866} 0
  endloop
endfacet
facet normal 0 0 -1
  outer loop
    vertex 0 0 0
    vertex {chamber_diameter/2 * 0.5} {chamber_diameter/2 * 0.866} 0
    vertex 0 {chamber_diameter/2} 0
  endloop
endfacet
facet normal 0 0 1
  outer loop
    vertex 0 0 {chamber_length}
    vertex {chamber_diameter/2} 0 {chamber_length}
    vertex {chamber_diameter/2 * 0.866} {chamber_diameter/4} {chamber_length}
  endloop
endfacet
facet normal 0 0 1
  outer loop
    vertex 0 0 {chamber_length}
    vertex {chamber_diameter/2 * 0.866} {chamber_diameter/4} {chamber_length}
    vertex {chamber_diameter/2 * 0.5} {chamber_diameter/2 * 0.866} {chamber_length}
  endloop
endfacet
facet normal 0 0 1
  outer loop
    vertex 0 0 {chamber_length}
    vertex {chamber_diameter/2 * 0.5} {chamber_diameter/2 * 0.866} {chamber_length}
    vertex 0 {chamber_diameter/2} {chamber_length}
  endloop
endfacet
endsolid {motor_type}_motor"""
        
        return stl_content
    except Exception as e:
        print(f"Error generating basic STL: {e}")
        # Return absolute minimum STL
        return """solid motor
facet normal 0 0 1
  outer loop
    vertex 0 0 0
    vertex 10 0 0
    vertex 5 10 0
  endloop
endfacet
endsolid motor"""

def generate_fallback_cad_geometry(motor_data, motor_type):
    """Generate fallback CAD geometry when main CAD generation fails"""
    import trimesh
    
    try:
        # Get motor dimensions with defaults
        chamber_length = motor_data.get('chamber_length', 0.5)
        chamber_diameter = motor_data.get('chamber_diameter', 0.1)
        throat_diameter = motor_data.get('throat_diameter', 0.03)
        
        # Create basic cylinder for chamber
        chamber_mesh = trimesh.creation.cylinder(
            radius=chamber_diameter/2,
            height=chamber_length,
            sections=16
        )
        
        # Create basic cone for nozzle
        nozzle_mesh = trimesh.creation.cone(
            radius=throat_diameter/2,
            height=chamber_length * 0.3,
            sections=16
        )
        
        # Position nozzle at end of chamber
        nozzle_mesh.apply_translation([0, 0, -chamber_length/2 - chamber_length*0.15])
        
        # Combine meshes
        assembly = trimesh.util.concatenate([chamber_mesh, nozzle_mesh])
        
        return {
            'assembly_meshes': [('Motor Assembly', assembly)],
            'technical_drawings': {},
            'material_specifications': {},
            'plotly_visualization': {},
            'performance_summary': {
                'mass_breakdown': {
                    'chamber_mass': chamber_length * chamber_diameter * 2.7,  # Rough estimate
                    'nozzle_mass': throat_diameter * 0.5,
                    'total_dry_mass': chamber_length * chamber_diameter * 3.0
                }
            },
            'manufacturing_notes': ['Fallback geometry - simplified representation']
        }
    except Exception as e:
        print(f"Error generating fallback CAD: {e}")
        return None

@app.route('/api/get-propellant-properties', methods=['POST'])
def get_propellant_properties():
    """Get propellant properties from open-source databases"""
    try:
        data = request.json
        propellant_type = data.get('propellant_type', 'hybrid_fuel')
        propellant_name = data.get('propellant_name', 'htpb')
        
        # First try local database
        local_props = propellant_db.get_propellant_properties(propellant_name)
        
        # Then fetch from open-source APIs
        api_props = propellant_api.get_propellant_for_ui(propellant_type, propellant_name)
        
        # Merge properties (API data takes precedence for real-time accuracy)
        if local_props:
            merged_props = {**local_props, **api_props}
        else:
            merged_props = api_props
        
        return jsonify({
            'status': 'success',
            'properties': merged_props,
            'source': api_props.get('data_source', 'Combined sources')
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/find-optimum-of', methods=['POST'])
def find_optimum_of_ratio():
    """Find optimum O/F ratio for maximum ISP.

    Tek doğruluk kaynağı: CombustionAnalyzer'ın gerçek denge taraması.
    Desteklenmeyen yakıt/oksitleyici çiftinde sessiz 7.0 varsayılanı
    dönmek yerine 400 + açıklayıcı hata döner (kullanıcı şikayeti:
    propellant seçilmeden 'optimum' üretiliyordu).
    """
    try:
        data = request.json
        motor_type = data.get('motor_type', 'hybrid')
        oxidizer = data.get('oxidizer', 'n2o')
        fuel = data.get('fuel', 'htpb')
        chamber_pressure = data.get('chamber_pressure', 20.0)

        if fuel in ('custom', 'mixture') or oxidizer == 'custom':
            return jsonify({
                'status': 'error',
                'error': ('Optimum O/F requires a defined propellant pair. '
                          'Select a specific fuel and oxidizer first; custom or mixture '
                          'compositions need a full combustion analysis run.')
            }), 400

        from hrma.engines.combustion_analysis import CombustionAnalyzer
        analyzer = CombustionAnalyzer()
        fuel_composition = {fuel: 100.0}
        opt = analyzer.find_optimum_of_ratio(
            fuel_composition, oxidizer, chamber_pressure
        )
        max_isp = float(opt.get('maximum_isp', 0) or 0)
        optimum_of = float(opt.get('optimum_of_ratio', 0) or 0)
        # minimize_scalar başarısız noktalara -1000 cezası verir; tüm
        # noktalar başarısızsa max_isp fiziksel bandın dışında kalır.
        if not (50.0 < max_isp < 600.0) or optimum_of <= 0:
            return jsonify({
                'status': 'error',
                'error': (f'No reliable combustion data for {oxidizer.upper()}/{fuel.upper()}. '
                          'Optimum O/F cannot be determined for this pair — verify the '
                          'propellant selection.')
            }), 400

        # Isp-O/F eğrisi (UI performance_curve bekliyor)
        performance_curve = None
        try:
            import numpy as _np
            of_scan = _np.linspace(max(0.5, optimum_of * 0.4), optimum_of * 1.8, 15)
            isp_vals = []
            for _of in of_scan:
                try:
                    r = analyzer.analyze_combustion(
                        fuel_composition, oxidizer, float(_of), chamber_pressure)
                    isp_vals.append(float(r['performance']['isp']))
                except Exception:
                    isp_vals.append(None)
            if any(v is not None for v in isp_vals):
                performance_curve = {
                    'of_ratios': [float(v) for v in of_scan],
                    'isp_values': isp_vals,
                }
        except Exception as curve_err:
            app.logger.info(f"Optimum O/F curve skipped: {curve_err}")

        recommendation = None
        try:
            recommendation = of_optimizer.get_recommendation(motor_type, oxidizer, fuel)
        except Exception:
            pass

        return jsonify({
            'status': 'success',
            'optimum_of_ratio': optimum_of,
            'max_isp': max_isp,
            'method': 'combustion equilibrium scan (CombustionAnalyzer)',
            'performance_curve': performance_curve,
            'recommendation': recommendation,
        })

    except (ValueError, KeyError) as e:
        return jsonify({'status': 'error', 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/regression-analysis', methods=['POST'])
def regression_analysis():
    """Perform regression rate analysis for hybrid motors"""
    try:
        data = request.json
        motor_data = data.get('motor_data', {})
        
        # Perform regression analysis
        regression_data = regression_analyzer.analyze_regression_vs_time(motor_data)
        
        # Create regression plot
        regression_plot = regression_analyzer.create_regression_plot(regression_data)
        
        # Fuel comparison if requested
        comparison_plot = None
        if data.get('compare_fuels', False):
            comparison_plot = regression_analyzer.compare_fuel_types(motor_data)
        
        return jsonify({
            'status': 'success',
            'regression_data': regression_data,
            'regression_plot': regression_plot,
            'comparison_plot': comparison_plot
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/trajectory-analysis', methods=['POST'])
def trajectory_analysis():
    """Perform trajectory analysis"""
    try:
        data = request.json
        
        # Extract trajectory parameters
        initial_mass = float(data.get('initial_mass', 50))
        final_mass = float(data.get('final_mass', 25))
        drag_coefficient = float(data.get('drag_coefficient', 0.5))
        reference_area = float(data.get('reference_area', 0.1))
        
        # Genel itki kaynağı (2026-07-13): istek doğrudan thrust + burn_time
        # veriyorsa (katı/sıvı sayfaları) hibrit motor kurulmaz — mevcut
        # hesap sonuçları kullanılır. Verilmemişse eski hibrit yolu çalışır.
        direct_thrust = data.get('thrust')
        direct_burn_time = data.get('burn_time')
        engine = None
        if not (direct_thrust and direct_burn_time):
            # Extract base motor data
            fuel_type = data.get('fuel_type', 'paraffin')
            oxidizer_type = data.get('oxidizer_type', 'n2o')
            of_ratio = float(data.get('of_ratio', 2.5))
            chamber_pressure = float(data.get('chamber_pressure', 20))  # bar

            # Create hybrid rocket engine for trajectory analysis
            engine = HybridRocketEngine(
                fuel_type=fuel_type,
                chamber_pressure=chamber_pressure,
                of_ratio=of_ratio,
                thrust=1000,  # Default thrust for trajectory analysis
                burn_time=10  # Default burn time
            )

            # Calculate engine performance
            engine.calculate()

        # Create trajectory analyzer
        trajectory_analyzer = TrajectoryAnalyzer()
        
        # Set vehicle parameters
        trajectory_analyzer.set_vehicle_parameters(
            mass_dry=final_mass,
            diameter=np.sqrt(4 * reference_area / np.pi),  # Calculate diameter from reference area
            drag_coefficient=drag_coefficient
        )
        
        # Prepare motor data for trajectory analysis
        if engine is not None:
            motor_data = {
                'thrust': engine.F,
                'burn_time': 10.0,
                'total_impulse': engine.F * 10.0,
                'isp': engine.Isp,
                'mass_flow_rate': engine.mdot_total,
                'propellant_mass_total': initial_mass - final_mass
            }
        else:
            thrust = float(direct_thrust)
            burn_time = float(direct_burn_time)
            isp = float(data.get('isp', 200.0))
            motor_data = {
                'thrust': thrust,
                'burn_time': burn_time,
                'total_impulse': float(data.get('total_impulse',
                                                thrust * burn_time)),
                'isp': isp,
                'mass_flow_rate': thrust / (isp * G_0) if isp > 0 else 0.0,
                'propellant_mass_total': initial_mass - final_mass
            }
        
        # Prepare launch parameters
        launch_params = {
            'initial_mass': initial_mass,
            'final_mass': final_mass,
            'launch_angle': 85.0,  # Near-vertical launch (85 degrees)
            'launch_altitude': 0.0,
            'launch_latitude': 40.0,  # Default latitude
            'launch_longitude': 0.0,  # Default longitude
            'wind_speed': 0.0,  # No wind
            'wind_direction': 0.0  # Wind direction in degrees
        }
        
        # Calculate trajectory with error tracking
        try:
            print("About to call calculate_trajectory...")
            print(f"Motor data keys: {motor_data.keys()}")
            print(f"Launch params keys: {launch_params.keys()}")
            results = trajectory_analyzer.calculate_trajectory(motor_data, launch_params)
            print("calculate_trajectory completed successfully")
        except Exception as calc_error:
            print(f"calculate_trajectory failed: {calc_error}")
            print(f"Error type: {type(calc_error)}")
            print("Calculate trajectory traceback:")
            traceback.print_exc()
            raise calc_error
        
        # Debug: Print result structure
        print("Trajectory results keys:", results.keys() if isinstance(results, dict) else type(results))
        
        # Create trajectory plot with detailed error tracking
        try:
            print("About to call create_trajectory_plots...")
            trajectory_plot = trajectory_analyzer.create_trajectory_plots(results)
            print("create_trajectory_plots completed successfully")
            
        except Exception as plot_error:
            print(f"create_trajectory_plots failed: {plot_error}")
            print(f"Error type: {type(plot_error)}")
            print(f"Error args: {plot_error.args}")
            print("Full traceback:")
            traceback.print_exc()
            
            # Fallback plot
            trajectory_plot = json.dumps({
                'data': [{'x': [0, 10], 'y': [0, 1000], 'type': 'scatter', 'name': 'Trajectory'}],
                'layout': {'title': 'Trajectory Analysis', 'xaxis': {'title': 'Time (s)'}, 'yaxis': {'title': 'Altitude (m)'}}
            })
        
        return jsonify({
            'status': 'success',
            'trajectory_data': sanitize_json_values(results),
            'plot_data': trajectory_plot,
            'engine_data': {
                'thrust': motor_data['thrust'],
                'isp': motor_data['isp'],
                'burn_time': motor_data['burn_time'],
                'total_impulse': motor_data['total_impulse']
            }
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/analyze_safety', methods=['POST'])
def analyze_safety():
    """Comprehensive safety analysis endpoint"""
    try:
        data = request.json
        
        # Extract motor parameters
        motor_type = data.get('motor_type', 'hybrid')
        chamber_pressure = float(data.get('chamber_pressure', 20))  # bar
        chamber_temperature = float(data.get('chamber_temperature', 3000))  # K
        thrust = float(data.get('thrust', 1000))  # N
        burn_time = float(data.get('burn_time', 10))  # s
        propellant_mass = float(data.get('propellant_mass', 5))  # kg
        propellant_type = data.get('propellant_type', 'composite')
        facility_type = data.get('facility_type', 'test_stand')
        
        # Prepare motor data dictionary
        motor_data = {
            'chamber_pressure': chamber_pressure,
            'chamber_temperature': chamber_temperature,
            'thrust': thrust,
            'burn_time': burn_time,
            'chamber_diameter': float(data.get('chamber_diameter', 0.1)),
            'wall_thickness': float(data.get('wall_thickness', 0.005))
        }
        
        # Initialize safety analyzer
        safety_analyzer = SafetyAnalyzer()
        
        # Perform comprehensive safety analysis
        # Dalga 0 (2026-07-14): malzeme artık istekten geçer — yapısal
        # emniyet merkezi materials_db dayanımlarıyla hesaplanır (eski
        # sabit 250/400 MPa jenerik çelik kalktı).
        safety_results = safety_analyzer.analyze_comprehensive_safety(
            motor_data=motor_data,
            propellant_mass=propellant_mass,
            propellant_type=propellant_type,
            facility_type=facility_type,
            material=data.get('material', 'steel_4130')
        )
        
        return jsonify({
            'status': 'success',
            'safety_analysis': sanitize_json_values(safety_results)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/analyze_structural_safety', methods=['POST'])
def analyze_structural_safety():
    """Detailed structural safety analysis endpoint"""
    try:
        data = request.json
        
        # Extract parameters
        chamber_pressure = float(data.get('chamber_pressure', 20))  # bar
        chamber_diameter = float(data.get('chamber_diameter', 0.1))  # m
        chamber_length = float(data.get('chamber_length', 0.5))  # m
        throat_diameter = float(data.get('throat_diameter', 0.02))  # m
        burn_time = float(data.get('burn_time', 10))  # s
        material = data.get('material', 'steel_4130')

        motor_data = {
            'chamber_pressure': chamber_pressure,
            'chamber_diameter': chamber_diameter,
            'chamber_length': chamber_length,
            'throat_diameter': throat_diameter,
            'burn_time': burn_time
        }
        # Termal senaryo bu uçta pasif kalıyordu: gaz sıcaklığı geçilmeyince
        # yapısal modül termal gerilmeyi hiç değerlendirmiyordu (2026-07-14).
        # İstemci gönderirse geçir; 0/boş "termal analizi atla" demektir.
        if data.get('chamber_temperature'):
            motor_data['chamber_temperature'] = float(data['chamber_temperature'])

        # Isı transfer analizinden gelen gerçek cidar sıcaklıkları varsa
        # geçir — yapısal modül termal gradyanı tahmin etmek yerine bunları
        # kullanır (v2.5.2 sözleşmesi, structural_analysis._estimate_wall_delta_T).
        for wall_key in ('wall_temperature_hot', 'wall_temperature_cold'):
            if data.get(wall_key):
                motor_data[wall_key] = float(data[wall_key])

        # Initialize structural analyzer
        structural_analyzer = StructuralAnalyzer()
        
        # Perform structural analysis
        structural_results = structural_analyzer.analyze_structure(
            motor_data=motor_data,
            material=material,
            design_pressure_factor=1.5
        )
        
        return jsonify({
            'status': 'success',
            'structural_analysis': sanitize_json_values(structural_results)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/analyze_thermal_safety', methods=['POST'])
def analyze_thermal_safety():
    """Detailed thermal safety analysis endpoint"""
    try:
        data = request.json
        
        # Extract parameters
        chamber_pressure = float(data.get('chamber_pressure', 20))  # bar
        chamber_temperature = float(data.get('chamber_temperature', 3000))  # K
        chamber_diameter = float(data.get('chamber_diameter', 0.1))  # m
        chamber_length = float(data.get('chamber_length', 0.5))  # m
        burn_time = float(data.get('burn_time', 10))  # s
        mdot_total = float(data.get('mdot_total', 1.0))  # kg/s
        material = data.get('material', 'steel')
        wall_thickness = float(data.get('wall_thickness', 0.005))  # m
        cooling_type = data.get('cooling_type', 'natural')
        
        motor_data = {
            'chamber_pressure': chamber_pressure,
            'chamber_temperature': chamber_temperature,
            'chamber_diameter': chamber_diameter,
            'chamber_length': chamber_length,
            'burn_time': burn_time,
            'mdot_total': mdot_total
        }
        
        # Initialize heat transfer analyzer
        thermal_analyzer = HeatTransferAnalyzer()
        
        # Perform thermal analysis
        thermal_results = thermal_analyzer.analyze_heat_transfer(
            motor_data=motor_data,
            material=material,
            wall_thickness=wall_thickness,
            ambient_temp=293.15,
            cooling_type=cooling_type
        )
        
        return jsonify({
            'status': 'success',
            'thermal_analysis': sanitize_json_values(thermal_results)
        })

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/analysis/wall-profile', methods=['POST'])
def analyze_wall_profile():
    """Eksenel cidar ısı profili (Dalga 2).

    Nozul konturu boyunca (hazne -> boğaz -> çıkış) A(x)/A_t, izantropik
    M(x), Bartz h_g(x), tasarım ısı akısı q(x) ve denge cidar sıcaklığı
    T_wall_eq(x) dizilerini döner. Grafik ÇİZMEZ — frontend çizer.

    Girdi şeması /analyze_thermal_safety ile aynı çekirdek alanları kullanır
    (chamber_pressure, chamber_temperature, chamber_diameter, chamber_length,
    burn_time, mdot_total, material, wall_thickness, cooling_type) + isteğe
    bağlı geometri/gaz alanları (throat_diameter, exit_diameter,
    expansion_ratio, nozzle_type, gamma, molecular_weight, n_stations...).
    """
    try:
        data = request.json or {}

        # Çekirdek alanlar — /analyze_thermal_safety ile bire bir aynı
        motor_data = {
            'chamber_pressure': float(data.get('chamber_pressure', 20)),   # bar
            'chamber_temperature': float(data.get('chamber_temperature', 3000)),  # K
            'chamber_diameter': float(data.get('chamber_diameter', 0.1)),  # m
            'chamber_length': float(data.get('chamber_length', 0.5)),      # m
            'burn_time': float(data.get('burn_time', 10)),                 # s
            'mdot_total': float(data.get('mdot_total', 1.0)),              # kg/s
        }
        material = data.get('material', 'steel')
        wall_thickness = float(data.get('wall_thickness', 0.005))  # m
        cooling_type = data.get('cooling_type', 'natural')

        # İsteğe bağlı sayısal alanlar: verilirse geçir (0/boş = "kullanma")
        optional_numeric = (
            'gamma', 'molecular_weight', 'gas_constant', 'c_star',
            'throat_diameter', 'exit_diameter', 'expansion_ratio',
            'throat_radius_curvature', 'coolant_side_coefficient',
        )
        for key in optional_numeric:
            value = data.get(key)
            if value in (None, '', 0, '0'):
                continue
            try:
                motor_data[key] = float(value)
            except (TypeError, ValueError):
                pass
        if data.get('nozzle_type'):
            # sample_nozzle_inner_contour konik/bell ayrımını buradan okur
            motor_data['nozzle_angles'] = {'nozzle_type': str(data['nozzle_type'])}

        n_stations = int(data.get('n_stations', 40))

        thermal_analyzer = HeatTransferAnalyzer()
        profile = thermal_analyzer.analyze_axial_profile(
            motor_data,
            n_stations=n_stations,
            material=material,
            wall_thickness=wall_thickness,
            ambient_temp=float(data.get('ambient_temp', 293.15)),
            cooling_type=cooling_type,
        )

        return jsonify({
            'status': 'success',
            'wall_profile': sanitize_json_values(profile)
        })

    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/chemical-database', methods=['GET'])
def get_chemical_database():
    """Get chemical species database information"""
    try:
        validation_results = chemical_db.validate_database()
        all_species = chemical_db.get_all_species_names()
        
        return jsonify({
            'status': 'success',
            'database_info': validation_results,
            'available_species': all_species[:50],  # Return first 50 species
            'total_species': len(all_species)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/chemical-species', methods=['POST'])
def get_chemical_species():
    """Get specific chemical species data"""
    try:
        data = request.json
        species_name = data.get('species_name')
        temperature = data.get('temperature', 2000)  # K
        
        species = chemical_db.get_species(species_name)
        if not species:
            return jsonify({'status': 'error', 'error': 'Species not found'}), 404
        
        # Calculate thermodynamic properties
        cp = chemical_db.calculate_cp(species_name, temperature)
        enthalpy = chemical_db.calculate_enthalpy(species_name, temperature)
        entropy = chemical_db.calculate_entropy(species_name, temperature)
        
        return jsonify({
            'status': 'success',
            'species_data': {
                'name': species.name,
                'formula': species.formula,
                'molecular_weight': species.molecular_weight,
                'phase': species.phase,
                'source': species.source,
                'thermodynamic_properties': {
                    'temperature': temperature,
                    'cp': cp,
                    'enthalpy': enthalpy,
                    'entropy': entropy
                }
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

# v2.5.0 G1 (2026-07-17, karar K5): olu /api/experimental-validation endpoint'i
# KALDIRILDI. Sinifta hic var olmamis metotlari cagiriyordu
# (validate_against_experiments / calculate_confidence_metrics -> AttributeError
# -> 500) ve frontend'de hicbir referansi yoktu. Halefi: G2 dalgasindaki
# korelasyon endpoint'leri (/api/validation/correlation-*) olacak.

@app.route('/api/cfd-analysis', methods=['POST'])
def perform_cfd_analysis():
    """Perform 2D CFD analysis"""
    # Dalga 0 bekçisi (2026-07-14): mevcut çözücü gerçek CFD değil —
    # kütle korunumu yok, 3 iterasyonda ıraksıyor (|u|→7.5e10 m/s),
    # NaN -> 500. Dalga 4A: quasi-1D halef uç noktası yayında —
    # 501 yanıtı artık yönlendirme alanı taşır. Orijinal işleyici korunur.
    return jsonify({
        'error': ('This analysis is being rebuilt on the reduced-order '
                  'physics architecture. Its successor endpoint is live: '
                  'POST /api/flow-analysis (quasi-1D compressible nozzle '
                  'flow with Fast Screening / Engineering fidelity levels).'),
        'status': 'unavailable',
        'successor': '/api/flow-analysis'
    }), 501
    try:
        data = request.json
        motor_type = data.get('motor_type', 'hybrid')
        
        # Motor geometry
        motor_geometry = {
            'chamber_length': data.get('chamber_length', 0.5),
            'chamber_radius': data.get('chamber_radius', 0.05),
            'throat_radius': data.get('throat_radius', 0.01),
            'exit_radius': data.get('exit_radius', 0.025),
            'nozzle_length': data.get('nozzle_length', 0.1)
        }
        
        # Boundary conditions
        from hrma.analysis.cfd_analysis import BoundaryConditions
        boundary_conditions = BoundaryConditions(
            inlet_pressure=data.get('chamber_pressure', 2e6),
            inlet_temperature=data.get('chamber_temperature', 3000),
            outlet_pressure=data.get('outlet_pressure', 101325),
            wall_temperature=data.get('wall_temperature', 500),
            mass_flow_rate=data.get('mass_flow_rate', 1.0)
        )
        
        # Perform CFD analysis
        cfd_results = cfd_analyzer.analyze_motor_flow(
            motor_geometry, boundary_conditions, motor_type
        )
        
        # Validate solution
        validation = cfd_analyzer.validate_cfd_solution(cfd_results)
        
        return jsonify({
            'status': 'success',
            'cfd_results': {
                'performance_metrics': sanitize_json_values(cfd_results['performance_metrics']),
                'visualizations': cfd_results['visualizations'],
                'convergence_info': cfd_results['convergence_info'],
                'validation': validation
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/kinetic-analysis', methods=['POST'])
def perform_kinetic_analysis():
    """Perform nozzle kinetic loss analysis"""
    # Dalga 0 bekçisi (2026-07-14): stiff ODE + explicit RK45 tek istasyonda
    # ~23 dk sürüyor ve tek-worker masaüstü uygulamasını KİLİTLİYOR; bitse
    # bile isp_loss ≡ 0 dönüyordu. Dalga 4A: kademeli kinetik verim halefi
    # yayında — 501 yanıtı yönlendirme alanı taşır. Orijinal işleyici korunur.
    return jsonify({
        'error': ('This analysis is being rebuilt on the reduced-order '
                  'physics architecture. Its successor endpoint is live: '
                  'POST /api/kinetic-efficiency (tiered frozen/shifting '
                  'kinetic-loss model: fast / engineering / high_fidelity).'),
        'status': 'unavailable',
        'successor': '/api/kinetic-efficiency'
    }), 501
    try:
        data = request.json
        motor_type = data.get('motor_type', 'hybrid')
        
        # Nozzle geometry
        nozzle_geometry = {
            'throat_radius': data.get('throat_radius', 0.01),
            'exit_radius': data.get('exit_radius', 0.025),
            'nozzle_length': data.get('nozzle_length', 0.1),
            'chamber_radius': data.get('chamber_radius', 0.05)
        }
        
        # Chamber conditions
        chamber_conditions = {
            'pressure': data.get('chamber_pressure', 2e6),
            'temperature': data.get('chamber_temperature', 3000)
        }
        
        # Propellant composition
        propellant_composition = {
            'propellant_type': data.get('propellant_combination', 'N2O/HTPB'),
            'of_ratio': data.get('of_ratio', 1.0)
        }
        
        # Perform kinetic analysis
        kinetic_results = kinetic_analyzer.analyze_nozzle_kinetics(
            nozzle_geometry, chamber_conditions, propellant_composition, motor_type
        )
        
        return jsonify({
            'status': 'success',
            'kinetic_results': {
                'performance_losses': sanitize_json_values(kinetic_results['performance_losses']),
                'equilibrium_comparison': sanitize_json_values(kinetic_results['equilibrium_comparison']),
                'detailed_analysis': kinetic_results['detailed_analysis'],
                'species_profiles': sanitize_json_values(kinetic_results['species_profiles']),
                'temperature_profile': sanitize_json_values(kinetic_results['temperature_profile'])
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/professional-analysis', methods=['POST'])
def perform_complete_professional_analysis():
    """Perform complete professional-grade analysis using all modules"""
    # Dalga 0 bekçisi (2026-07-14): bu uç CFD + kinetik çözücüleri birlikte
    # çağırıyor — ikisi de yukarıdaki nedenlerle emekliye ayrıldı (kilitleme
    # + ıraksama riski). v2.4.6: halefler yayında — 501 yanıtı yönlendirme
    # alanı taşır. Orijinal işleyici aşağıda korunur.
    return jsonify({
        'error': ('This analysis is being rebuilt on the reduced-order '
                  'physics architecture. Its successors are live: '
                  'POST /api/flow-analysis, POST /api/kinetic-efficiency '
                  'and the Analysis Deck panels '
                  '(structural/thermal/safety/flow/validation).'),
        'status': 'unavailable',
        'successor': ['/api/flow-analysis', '/api/kinetic-efficiency',
                      'Analysis Deck panels (structural/thermal/safety/flow/validation)']
    }), 501
    try:
        data = request.json
        motor_type = data.get('motor_type', 'hybrid')
        
        # Common parameters
        motor_geometry = {
            'chamber_length': data.get('chamber_length', 0.5),
            'chamber_radius': data.get('chamber_radius', 0.05),
            'throat_radius': data.get('throat_radius', 0.01),
            'exit_radius': data.get('exit_radius', 0.025),
            'nozzle_length': data.get('nozzle_length', 0.1)
        }
        
        chamber_conditions = {
            'pressure': data.get('chamber_pressure', 2e6),
            'temperature': data.get('chamber_temperature', 3000)
        }
        
        propellant_combination = data.get('propellant_combination', 'N2O/HTPB')
        
        # 1. Chemical Database Analysis
        database_info = chemical_db.validate_database()
        
        # 2. Experimental Validation — v2.5.0 G1: sentetik experimental_validator
        # emekli (bu blok zaten yukaridaki 501 nedeniyle erisilemez; korunan
        # olu kodun tutarliligi icin bos sonuc birakildi). Halef: experiment_db
        # + G2 korelasyon koducusu.
        validation_results = {}
        
        # 3. CFD Analysis
        from hrma.analysis.cfd_analysis import BoundaryConditions
        boundary_conditions = BoundaryConditions(
            inlet_pressure=chamber_conditions['pressure'],
            inlet_temperature=chamber_conditions['temperature'],
            outlet_pressure=101325,
            wall_temperature=500,
            mass_flow_rate=data.get('mass_flow_rate', 1.0)
        )
        
        cfd_results = cfd_analyzer.analyze_motor_flow(
            motor_geometry, boundary_conditions, motor_type
        )
        
        # 4. Kinetic Analysis
        propellant_composition = {
            'propellant_type': propellant_combination,
            'of_ratio': data.get('of_ratio', 1.0)
        }
        
        kinetic_results = kinetic_analyzer.analyze_nozzle_kinetics(
            motor_geometry, chamber_conditions, propellant_composition, motor_type
        )
        
        # Compile comprehensive report
        professional_analysis = {
            'analysis_summary': {
                'motor_type': motor_type,
                'propellant_combination': propellant_combination,
                'analysis_timestamp': datetime.now().isoformat(),
                'professional_grade': True
            },
            'chemical_database': {
                'total_species': database_info['total_species'],
                'nasa_cea_compatible': True,
                'thermodynamic_accuracy': 'HIGH'
            },
            'experimental_validation': {
                'status': 'retired',
                'note': ('Synthetic experimental-validation layer removed in '
                         'v2.5.0; real-experiment correlation lives in '
                         'hrma/validation/experiment_db.py (runner in G2).')
            },
            'cfd_analysis': {
                'convergence_achieved': cfd_results['convergence_info']['converged'],
                'solution_quality': cfd_analyzer.validate_cfd_solution(cfd_results)['solution_quality'],
                'performance_metrics': cfd_results['performance_metrics']
            },
            'kinetic_analysis': {
                'kinetic_efficiency': kinetic_results['performance_losses']['kinetic_efficiency'],
                'loss_severity': kinetic_results['performance_losses']['performance_summary']['kinetic_loss_severity'],
                'isp_loss_percent': kinetic_results['performance_losses']['isp_loss_fraction'] * 100
            },
            'overall_assessment': {
                'professional_readiness': 'READY_FOR_PRODUCTION',
                'industry_standard_compliance': 'NASA_CEA_COMPATIBLE',
                'confidence_rating': 'HIGH'
            }
        }
        
        return jsonify({
            'status': 'success',
            'professional_analysis': sanitize_json_values(professional_analysis),
            'detailed_results': {
                'validation': sanitize_json_values(validation_results),
                'cfd': sanitize_json_values(cfd_results['performance_metrics']),
                'kinetic': sanitize_json_values(kinetic_results['performance_losses'])
            }
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/api/get-fuel-properties', methods=['POST'])
def get_fuel_properties():
    try:
        data = request.json
        fuel_type = data.get('fuel_type', 'htpb')
        temperature = data.get('temperature', 298.15)
        
        print(f"FETCHING NASA CEA DATA: {fuel_type} at {temperature}K")
        
        # Get fuel properties from chemical database
        fuel_mapping = {
            'rp1': 'RP1',
            'lh2': 'H2', 
            'methane': 'CH4',
            'mmh': 'MMH',
            'udmh': 'UDMH',
            'htpb': 'HTPB',
            'paraffin': 'Paraffin'
        }
        
        species_name = fuel_mapping.get(fuel_type, fuel_type.upper())
        species = chemical_db.get_species(species_name)
        
        if species:
            # Calculate properties at requested temperature
            cp = chemical_db.calculate_cp(species_name, temperature)
            enthalpy = chemical_db.calculate_enthalpy(species_name, temperature)
            entropy = chemical_db.calculate_entropy(species_name, temperature)
            
            properties = {
                'density': species.molecular_weight * 10 if species.phase == 'liquid' else species.molecular_weight,
                'enthalpy_formation': species.enthalpy_formation / 1000,  # Convert to kJ/mol
                'formula': species.formula,
                'phase': species.phase,
                'cp': cp / 1000,  # Convert to kJ/mol/K
                'enthalpy': enthalpy / 1000,
                'entropy': entropy / 1000,
                'source': species.source,
                'molecular_weight': species.molecular_weight,
                'temperature': temperature,
                'timestamp': datetime.now().isoformat()
            }
            
            print(f"NASA CEA RESPONSE: {species_name} - MW: {species.molecular_weight}, dHf: {species.enthalpy_formation}")
            
            return jsonify({
                'status': 'success',
                'properties': sanitize_json_values(properties),
                'source': 'NASA CEA Database',
                'real_time': True
            })
        else:
            print(f"Species not found: {species_name}, trying fallback...")
            
            # Fallback properties for common fuels
            fallback_props = get_cached_fuel_properties(fuel_type, temperature)
            
            return jsonify({
                'status': 'success',
                'properties': sanitize_json_values(fallback_props),
                'source': 'Cached Database',
                'note': f'Species {species_name} not found in NASA CEA, using cached data'
            })
            
    except Exception as e:
        print(f"NASA CEA ERROR: {str(e)}")
        return jsonify({
            'status': 'error', 
            'error': f'NASA CEA Database Error: {str(e)}'
        }), 500


def get_cached_fuel_properties(fuel_type, temperature):
    """Get cached fuel properties"""
    cache_data = {
        'rp1': {
            'density': 810.0,
            'enthalpy_formation': -194.2,  # kJ/mol
            'formula': 'C12H23',
            'phase': 'liquid',
            'heating_value': 43000  # kJ/kg
        },
        'lh2': {
            'density': 71.0,
            'enthalpy_formation': 0.0,
            'formula': 'H2',
            'phase': 'liquid',
            'heating_value': 120000
        },
        'methane': {
            'density': 423.0,
            'enthalpy_formation': -74.6,
            'formula': 'CH4', 
            'phase': 'liquid',
            'heating_value': 50000
        }
    }
    
    props = cache_data.get(fuel_type, cache_data['rp1']).copy()
    props.update({
        'temperature': temperature,
        'source': 'Cached Database',
        'timestamp': datetime.now().isoformat()
    })
    return props

def get_oxidizer_density(oxidizer_type, temperature):
    """Calculate oxidizer density with temperature dependency"""
    base_densities = {
        'lox': (1141.0, 90.15, -4.0),    # (density at Tb, Tb, dρ/dT)
        'n2o4': (1443.0, 261.95, -2.8),
        'n2o': (1220.0, 184.67, -2.5)
    }
    
    if oxidizer_type in base_densities:
        rho_base, t_base, drho_dt = base_densities[oxidizer_type]
        return max(10.0, rho_base + drho_dt * (temperature - t_base))
    return 1141.0  # Default to LOX

def get_oxidizer_viscosity(oxidizer_type, temperature):
    """Calculate oxidizer viscosity"""
    viscosities = {
        'lox': 1.95e-4,
        'n2o4': 4.2e-4, 
        'n2o': 2.8e-4
    }
    return viscosities.get(oxidizer_type, 1.95e-4)

def get_oxidizer_conductivity(oxidizer_type, temperature):
    """Calculate thermal conductivity"""
    conductivities = {
        'lox': 0.15,
        'n2o4': 0.12,
        'n2o': 0.20
    }
    return conductivities.get(oxidizer_type, 0.15)

def get_cached_oxidizer_properties(oxidizer_type, temperature):
    """Get cached oxidizer properties when live data unavailable"""
    
    # Realistic oxidizer properties database with temperature dependency
    cache_data = {
        'lox': {
            'density': get_oxidizer_density('lox', temperature),
            'viscosity': 1.95e-4,
            'heat_capacity': 1.7,
            'thermal_conductivity': 0.15,
            'formula': 'O2',
            'boiling_point': 90.15,
            'critical_temperature': 154.8,
            'molecular_weight': 31.998
        },
        'n2o4': {
            'density': get_oxidizer_density('n2o4', temperature),
            'viscosity': 4.2e-4,
            'heat_capacity': 1.4,
            'thermal_conductivity': 0.12,
            'formula': 'N2O4', 
            'boiling_point': 294.3,
            'critical_temperature': 431.35,
            'molecular_weight': 92.011
        },
        'n2o': {
            'density': get_oxidizer_density('n2o', temperature),
            'viscosity': 2.8e-4,
            'heat_capacity': 2.2,
            'thermal_conductivity': 0.20,
            'formula': 'N2O',
            'boiling_point': 184.67,
            'critical_temperature': 309.57,
            'molecular_weight': 44.013
        }
    }
    
    props = cache_data.get(oxidizer_type, cache_data['lox']).copy()
    props.update({
        'temperature': temperature,
        'source': 'Cached Database',
        'timestamp': datetime.now().isoformat(),
        'note': 'Live NIST data unavailable'
    })
    return props

@app.route('/api/advanced-performance-analysis', methods=['POST'])
def advanced_performance_analysis():
    """Generate advanced performance analysis graphs based on NASA standards"""
    try:
        data = request.json
        analysis_type = data.get('analysis_type', '3d_surface')
        
        if analysis_type == '3d_surface':
            # Chamber Pressure vs Mixture Ratio vs Isp (NASA SP-125)
            # v2.5.2 (Codex bulgusu): yakıt/oksitleyici KİMLİĞİ bu sözlüğe
            # konmuyordu, bu yüzden LOX/RP-1 koşusunda bile denge yüzeyi
            # _resolve_surface_propellant'ın HTPB/N2O referans çiftiyle
            # çözülüyordu. Kimlik ve tarama aralıkları artık aktarılır;
            # verilmezse görselleştirme "referans çift" uyarısını basar.
            engine_data = {
                'base_isp': data.get('base_isp', 300),
                'optimal_of_ratio': data.get('optimal_of_ratio', 3.5),
                'optimal_chamber_pressure': data.get('chamber_pressure', 50),
                'fuel_type': data.get('fuel_type'),
                'fuel_composition': data.get('fuel_composition'),
                'oxidizer_type': data.get('oxidizer_type'),
                'pc_range': data.get('pc_range'),
                'of_range': data.get('of_range'),
                'grid_n': data.get('grid_n'),
            }
            engine_data = {k: v for k, v in engine_data.items() if v is not None}

            plot_json = create_chamber_pressure_mixture_ratio_3d_surface(engine_data)

            return jsonify({
                'status': 'success',
                'plot_data': plot_json,
                'analysis_info': {
                    'title': '3D Performance Surface Analysis',
                    'reference': 'NASA SP-125 Liquid-Propellant Rocket Engine Performance',
                    'description': 'Shows optimum O/F ratio and chamber pressure regions with combustion instability bands'
                }
            })

        elif analysis_type == 'nozzle_mach':
            # Nozzle Mach-Area Ratio Contour (NASA-STD-5012)
            # v2.5.2 (Codex bulgusu): yalnız throat_area / nozzle_length /
            # expansion_ratio aktarılıyordu; gaz hâli (gamma, MW, Tc), oda
            # basıncı, hazne çapı ve ortam basıncı DÜŞÜYORDU. Çözücü kendi
            # 20 bar / gamma 1.20 / 1 atm varsayılanlarına iniyor, oda
            # basıncını değiştirmek grafiği hiç değiştirmiyordu. Aynı ısı
            # akısı dalındaki desen uygulanır: alan varsa geçilir, yoksa
            # hiç konmaz ve figür "assumed" listesinde açıkça yazar.
            cfd_data = {
                'throat_area': data.get('throat_area', 0.001),
                'throat_diameter': data.get('throat_diameter'),
                'exit_diameter': data.get('exit_diameter'),
                'nozzle_length': data.get('nozzle_length', 0.1),
                'expansion_ratio': data.get('expansion_ratio', 16),
                'chamber_diameter': data.get('chamber_diameter'),
                'chamber_pressure': data.get('chamber_pressure'),
                'chamber_temperature': data.get('chamber_temperature'),
                'gamma': data.get('gamma'),
                'molecular_weight': data.get('molecular_weight'),
                # Görselleştirme sözleşmesi: ambient_pressure PASCAL
                # (NozzleFlow1D.from_motor_data ambient_pressure=Pa bekler).
                # Bar cinsinden gönderen çağıranlar için ayrı anahtar.
                'ambient_pressure': (
                    data.get('ambient_pressure')
                    if data.get('ambient_pressure') is not None
                    else (float(data['ambient_pressure_bar']) * 1e5
                          if data.get('ambient_pressure_bar') is not None
                          else None)),
            }
            cfd_data = {k: v for k, v in cfd_data.items() if v is not None}

            plot_json = create_nozzle_mach_area_ratio_contour(cfd_data)
            
            return jsonify({
                'status': 'success',
                'plot_data': plot_json,
                'analysis_info': {
                    'title': 'Nozzle Mach Distribution Analysis',
                    'reference': 'NASA-STD-5012 Pressure Vessels & Pressurized Systems',
                    'description': 'Visualizes Mach distribution and shock/threshold regions for over/under-expansion detection'
                }
            })
            
        elif analysis_type == 'heat_flux':
            # Wall Heat Flux Waterfall (NASA SP-8124)
            # v2.5.2: panel throat_area / chamber_pressure / expansion_ratio
            # gönderiyordu ama bu sözlüğe konmuyordu, dolayısıyla ısı akısı
            # GERÇEK Bartz hesabına giremeyip "not available" durumuna
            # düşüyordu. Üç alan da geçiriliyor; ek olarak malzeme, gaz
            # özellikleri ve kütle debisi de varsa aktarılır.
            thermal_data = {
                'burn_time': data.get('burn_time', 30),
                'chamber_length': data.get('chamber_length', 0.5),
                'nozzle_length': data.get('nozzle_length', 0.1),
                'base_heat_flux': data.get('base_heat_flux', 2e6),
                'critical_heat_flux': data.get('critical_heat_flux', 4.0),
                'molecular_weight': data.get('molecular_weight'),
                'throat_area': data.get('throat_area'),
                'throat_diameter': data.get('throat_diameter'),
                'chamber_pressure': data.get('chamber_pressure'),
                'chamber_temperature': data.get('chamber_temperature'),
                'expansion_ratio': data.get('expansion_ratio'),
                'chamber_diameter': data.get('chamber_diameter'),
                'mdot_total': data.get('mdot_total'),
                'gamma': data.get('gamma'),
                'material': data.get('material'),
                'c_star': data.get('c_star'),
            }
            thermal_data = {k: v for k, v in thermal_data.items() if v is not None}
            
            plot_json = create_wall_heat_flux_waterfall_plot(thermal_data)
            
            return jsonify({
                'status': 'success',
                'plot_data': plot_json,
                'analysis_info': {
                    'title': 'Wall Heat Flux Waterfall Analysis',
                    'reference': 'NASA SP-8124 Thermal Design Criteria',
                    'description': 'Gradient colored waterfall showing local heat flux along cooling channels with thermal runaway detection'
                }
            })
            
        else:
            return jsonify({
                'status': 'error',
                'error': f'Unknown analysis type: {analysis_type}',
                'available_types': ['3d_surface', 'nozzle_mach', 'heat_flux']
            }), 400
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

# PDF Export Endpoints
def _build_pdf_analysis_sections(motor_data, analysis_results):
    """PDF rapor bölümlerini motorun GERÇEK analiz sonuçlarıyla doldurur.

    Kaynak öncelik sırası (Dalga 2, 2026-07-14):
      motor sonuçları (motor_data.heat_transfer_analysis /
      structural_analysis) > istekle gelen analysis_results alanları.
    Sabit/uydurma değer ÜRETİLMEZ: veri yoksa ilgili alan hiç konmaz;
    pdf_generator eksik alanları 'N/A' olarak basar. (Eski app.js sabit
    SF 4.0/3.0/4.0 dürüstlük sorununun rapor katmanındaki karşılığı.)
    """
    out = dict(analysis_results or {})
    md = motor_data or {}

    def _num(value):
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        return f if np.isfinite(f) else None

    # ---- Performans: motor sonucundaki gerçek değerler öncelikli ----
    performance = dict(out.get('performance') or {})
    perf_sources = {
        'thrust': ('thrust',),
        'specific_impulse': ('specific_impulse', 'isp'),
        'chamber_pressure': ('chamber_pressure',),
        'burn_time': ('burn_time',),
        'total_impulse': ('total_impulse',),
        'exit_velocity': ('exit_velocity',),
        'mass_flow_rate': ('mdot_total', 'total_mdot', 'mass_flow_rate'),
    }
    for target, sources in perf_sources.items():
        for source in sources:
            value = _num(md.get(source))
            if value is not None:
                performance[target] = value
                break
    if performance:
        out['performance'] = performance

    # ---- Termal: heat_transfer_analysis (Bartz) gerçek sonuçları ----
    heat = md.get('heat_transfer_analysis') or out.get('heat_transfer_analysis') or {}
    if isinstance(heat, dict) and heat:
        wall = heat.get('wall_analysis') or {}
        gas_side = heat.get('gas_side_analysis') or {}
        cooling = heat.get('cooling_analysis') or {}
        thermal = dict(out.get('thermal') or {})
        heat_flux = _num(gas_side.get('heat_flux'))
        candidates = {
            'max_wall_temp': _num(wall.get('max_temperature')),
            'heat_flux': heat_flux / 1e6 if heat_flux is not None else None,  # W/m^2 -> MW/m^2
            'cooling_req': _num(cooling.get('peak_heat_rate')),  # kW
            'adiabatic_wall_temp': _num(gas_side.get('adiabatic_wall_temperature')),
            'gas_side_coefficient': _num(gas_side.get('gas_side_coefficient')),
        }
        for key, value in candidates.items():
            if value is not None:
                thermal[key] = value
        if thermal:
            out['thermal'] = thermal

    # ---- Yapısal: gerçek SF'ler (sabit 4.0 kalıntısı YOK) ----
    structural_src = md.get('structural_analysis') or out.get('structural_analysis') or {}
    if isinstance(structural_src, dict) and structural_src:
        safety_sub = structural_src.get('safety_analysis') or {}
        chamber = structural_src.get('chamber_analysis') or {}
        structural = dict(out.get('structural') or {})
        candidates = {
            'safety_factor': _num(structural_src.get('safety_factor')),
            'safety_factor_pressure': _num(structural_src.get('safety_factor_pressure')),
            'safety_factor_total': _num(structural_src.get('safety_factor_total')),
            'min_safety_factor': _num(safety_sub.get('minimum_safety_factor')),
            'von_mises_stress_MPa': _num(chamber.get('von_mises_stress')),
            'hoop_stress_MPa': _num(chamber.get('hoop_stress')),
        }
        for key, value in candidates.items():
            if value is not None:
                structural[key] = value
        if safety_sub.get('status'):
            structural['status'] = str(safety_sub['status'])
        if safety_sub.get('risk_level'):
            structural['risk_level'] = str(safety_sub['risk_level'])
        if structural:
            out['structural'] = structural

    # ---- Güvenlik özeti: istekle geldiyse aynen korunur ----
    # (out zaten istekten kopyalandı; 'safety' anahtarına dokunulmaz.)
    return out


@app.route('/api/materials', methods=['GET'])
def get_materials_catalog():
    """Merkezi malzeme kütüphanesini döndürür.

    Sözleşme (v2.5.2): {ok, materials: {key: {name, source, tags, ...}},
    aliases: {...}}. Paneller (static/js/materials_catalog.js) select
    listelerini buradan doldurur; endpoint yoksa hardcoded fallback'e düşer.
    """
    try:
        from hrma.data.materials_db import MATERIALS, ALIASES
        return jsonify(sanitize_json_values({
            'ok': True,
            'materials': MATERIALS,
            'aliases': ALIASES,
        }))
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/propellants', methods=['GET'])
def get_propellants_catalog():
    """Merkezi katı yakıt kataloğunu döndürür.

    Sözleşme (v2.5.2) — /api/materials ile birebir aynı desen:
        {ok: true,
         propellants: {key: {...tüm kayıt alanları}},
         aliases: {alias: canonical_key}}
    Katı sayfası (static/js/propellant_catalog.js) yakıt seçicisini ve
    otomatik dolan özellik alanlarını buradan besler; endpoint yoksa
    sayfa kendi hardcoded fallback listesine düşer.

    Tek doğruluk kaynağı: hrma/data/propellants_db.py — yanma hızı yasası
    olan yakıtlarda (KNDX/KNSB) a-n değerleri merkezi burn_rate_db'den
    türetilir, burada ayrıca yazılmaz.
    """
    try:
        from hrma.data.propellants_db import PROPELLANTS, ALIASES
        return jsonify(sanitize_json_values({
            'ok': True,
            'propellants': PROPELLANTS,
            'aliases': ALIASES,
        }))
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/export-xlsx', methods=['POST'])
def export_xlsx():
    """Genel amaçlı Excel (xlsx) dışa aktarma.

    Girdi: {filename: 'name.xlsx', sheets: [{name, headers: [...],
    rows: [[...], ...]}]}. Transient sonuçları, regresyon analizi ve
    genel analiz özeti bu uçtan insan-dostu Excel olarak iner
    (kullanıcı şikayeti: .json indirmesi kullanışsızdı).
    """
    try:
        from io import BytesIO
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter

        data = request.json or {}
        sheets = data.get('sheets') or []
        if not sheets:
            return jsonify({'status': 'error', 'error': 'No sheets provided'}), 400

        wb = Workbook()
        wb.remove(wb.active)
        header_font = Font(bold=True)
        for idx, sheet in enumerate(sheets[:20]):
            title = str(sheet.get('name') or f'Sheet{idx + 1}')[:31]
            ws = wb.create_sheet(title=title)
            headers = sheet.get('headers') or []
            rows = sheet.get('rows') or []
            if headers:
                ws.append([str(h) for h in headers])
                for cell in ws[1]:
                    cell.font = header_font
            for row in rows[:100000]:
                ws.append([
                    (float(v) if isinstance(v, (int, float)) and not isinstance(v, bool)
                     else ('' if v is None else str(v)))
                    for v in (row if isinstance(row, (list, tuple)) else [row])
                ])
            # Kolon genişliklerini başlığa göre kabaca ayarla
            for col_idx, h in enumerate(headers, start=1):
                ws.column_dimensions[get_column_letter(col_idx)].width = max(12, min(32, len(str(h)) + 4))

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        filename = str(data.get('filename') or 'hrma_export.xlsx')
        if not filename.endswith('.xlsx'):
            filename += '.xlsx'
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename,
        )
    except ImportError:
        return jsonify({
            'status': 'error',
            'error': 'openpyxl is not installed on the server; falling back to CSV is recommended.'
        }), 501
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/export-pdf/<report_type>', methods=['POST'])
def export_pdf_report(report_type):
    """Export motor analysis as PDF report"""
    try:
        from hrma.export.pdf_generator import PDFReportGenerator

        data = request.json
        motor_data = data.get('motor_data', {})
        analysis_results = data.get('analysis_results', {})
        charts = data.get('charts', [])

        # Dalga 2: rapor bölümleri motor sonuçlarındaki GERÇEK analizlerle
        # beslenir (heat_transfer_analysis + structural_analysis + istekle
        # gelen safety özeti). Sabit değer enjekte edilmez.
        analysis_results = _build_pdf_analysis_sections(motor_data, analysis_results)

        pdf_generator = PDFReportGenerator()
        
        # Generate different types of reports
        if report_type == 'summary':
            pdf_bytes = pdf_generator.generate_quick_summary_report(motor_data, analysis_results)
            filename = f"motor_summary_{motor_data.get('motor_name', 'unnamed')}.pdf"
        elif report_type == 'technical':
            pdf_bytes = pdf_generator.generate_technical_report(motor_data, analysis_results, charts)
            filename = f"motor_technical_{motor_data.get('motor_name', 'unnamed')}.pdf"
        else:
            pdf_bytes = pdf_generator.generate_motor_analysis_report(
                motor_data, analysis_results, charts, 'complete'
            )
            filename = f"motor_complete_{motor_data.get('motor_name', 'unnamed')}.pdf"
        
        # Return PDF file
        pdf_buffer = io.BytesIO(pdf_bytes)
        pdf_buffer.seek(0)
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'PDF generation failed: {str(e)}'
        }), 500

@app.route('/api/export-chart-pdf', methods=['POST'])
def export_chart_as_pdf():
    """Export individual chart as PDF"""
    try:
        from hrma.export.pdf_generator import PDFReportGenerator
        
        data = request.json
        chart_json = data.get('chart_data', '')
        chart_title = data.get('chart_title', 'Chart')
        motor_name = data.get('motor_name', 'unnamed')
        
        pdf_generator = PDFReportGenerator()
        
        # Convert chart to image
        chart_image = pdf_generator.export_plotly_chart_to_image(chart_json)
        
        if not chart_image:
            return jsonify({
                'status': 'error',
                'error': 'Failed to convert chart to image'
            }), 400
        
        # Create simple PDF with just the chart
        motor_data = {'motor_name': motor_name, 'motor_type': 'analysis'}
        analysis_results = {'chart_title': chart_title}
        
        pdf_bytes = pdf_generator.generate_motor_analysis_report(
            motor_data, analysis_results, [chart_image], 'summary'
        )
        
        pdf_buffer = io.BytesIO(pdf_bytes)
        pdf_buffer.seek(0)
        
        filename = f"chart_{chart_title.lower().replace(' ', '_')}_{motor_name}.pdf"
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'Chart PDF export failed: {str(e)}'
        }), 500

@app.route('/api/detailed-cad/<motor_type>', methods=['POST'])
def generate_detailed_cad(motor_type):
    """Generate detailed engineering CAD visualization"""
    try:
        from hrma.export.cad_visualization import DetailedCADGenerator
        
        data = request.json
        cad_generator = DetailedCADGenerator()
        
        if motor_type == 'liquid':
            result = cad_generator.generate_liquid_motor_cad(data)
        elif motor_type == 'solid':
            result = cad_generator.generate_solid_motor_cad(data)
        else:
            return jsonify({
                'status': 'error',
                'error': f'Unknown motor type: {motor_type}'
            }), 400
        
        return jsonify({
            'status': 'success',
            'cad_data': result['plot_json'],
            'component_details': result['component_details'],
            'dimensions': result.get('dimensions', {}),
            'design_info': {
                'title': f'Engineering CAD: {motor_type.title()} Motor',
                'description': 'Detailed engineering visualization with cross-section view',
                'features': [
                    'External component details',
                    'Internal structure cross-section', 
                    'Injector hole patterns',
                    'Cooling channel layout',
                    'Mounting flanges and sensors'
                ]
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'CAD generation failed: {str(e)}'
        }), 500

# ============================================================================
# Dalga 4A — Akış / Kinetik / Doğrulama / İş kuyruğu uç noktaları (2026-07-14)
# Mimari: docs/ANALIZ_PLATFORM_PLANI.md — sahte CFD/kinetik yerine hızlı
# gerçekçi modeller; UI seviyeleri Fast Screening / Engineering / High-Fidelity.
# ============================================================================

# /api/flow-analysis'in kabul ettiği seviyeler (High-Fidelity kinetik zinciri
# /api/kinetic-efficiency üzerinden yürür; akış modeli quasi-1D kalır)
FLOW_FIDELITY_LEVELS = ('fast', 'engineering')


def _flow_float(data, key, default=None):
    """İstek gövdesinden sayısal alan oku; bozuksa net İngilizce ValueError."""
    value = data.get(key, default)
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Field '{key}' must be a number, got {value!r}.")
    if not np.isfinite(value):
        raise ValueError(f"Field '{key}' must be finite.")
    return value


def _kinetic_evaluate_job(kwargs, progress_callback=None):
    """job_runner işi: kinetik verim değerlendirmesi (async yol).

    progress_callback runner tarafından enjekte edilir; değerlendirme tek
    parça olduğundan yalnız başla/bitti işaretlenir.
    """
    if progress_callback:
        progress_callback(0.1)
    result = kinetic_efficiency.evaluate(**kwargs)
    if progress_callback:
        progress_callback(1.0)
    return sanitize_json_values(result)


def _run_kinetic_chain(data, chamber_pressure_bar, throat_diameter,
                       nozzle_profile=None):
    """Ortak kinetik verim zinciri (flow-analysis + kinetic-efficiency).

    Returns (result_dict_or_None, note_or_None). Yakıt tanımı yoksa None +
    açıklayıcı not döner; değerlendirme hatası da not olarak raporlanır
    (akış analizi kinetik zincir yüzünden 500'e düşmez).
    """
    of_ratio = data.get('of_ratio')
    if of_ratio is None:
        return None, ("Kinetic-efficiency chain skipped: provide 'of_ratio' "
                      "(and optionally 'fuel_type', 'oxidizer_type') to "
                      "evaluate nozzle kinetic losses.")
    fidelity = str(data.get('kinetic_fidelity',
                            data.get('fidelity', 'engineering')))
    if fidelity not in KINETIC_FIDELITY_LEVELS:
        fidelity = 'engineering'
    fuel_composition = data.get('fuel_composition')
    if not isinstance(fuel_composition, dict) or not fuel_composition:
        fuel_composition = {str(data.get('fuel_type', 'htpb')): 100.0}
    try:
        result = kinetic_efficiency.evaluate(
            fuel_composition=fuel_composition,
            oxidizer_type=str(data.get('oxidizer_type', 'N2O')),
            of_ratio=float(of_ratio),
            chamber_pressure=chamber_pressure_bar,
            fidelity=fidelity,
            characteristic_length=_flow_float(data, 'characteristic_length'),
            throat_diameter=throat_diameter,
            nozzle_profile=nozzle_profile,
        )
        return sanitize_json_values(result), None
    except Exception as exc:
        return None, f"Kinetic-efficiency chain failed: {exc}"


@app.route('/api/flow-analysis', methods=['POST'])
def flow_analysis():
    """Quasi-1D compressible nozzle flow (successor of /api/cfd-analysis).

    Fidelity levels (Wave 4 architecture):
      fast        — isentropic summary: regime classification, CF/thrust,
                    throat state (no station arrays, no Bartz coupling).
      engineering — full 30-60 station arrays (P, M, T, rho, u, wall P),
                    axial Bartz h_g/q coupling, and the kinetic-efficiency
                    chain when the propellant definition is supplied
                    (of_ratio [+ fuel_type/oxidizer_type]).

    Units follow the repo convention: chamber_pressure in bar, temperatures
    in K, diameters in m, ambient_pressure in Pa.
    """
    data = request.get_json(silent=True) or {}

    fidelity = str(data.get('fidelity', 'engineering')).lower()
    if fidelity not in FLOW_FIDELITY_LEVELS:
        return jsonify({
            'status': 'error',
            'error': (f"fidelity must be one of {list(FLOW_FIDELITY_LEVELS)}; "
                      f"got '{fidelity}'. High-fidelity finite-rate kinetics "
                      "is served by POST /api/kinetic-efficiency."),
        }), 400

    try:
        chamber_pressure_bar = _flow_float(data, 'chamber_pressure', 20.0)
        chamber_temperature = _flow_float(data, 'chamber_temperature', 3000.0)
        gamma = _flow_float(data, 'gamma', 1.2)
        molecular_weight = _flow_float(data, 'molecular_weight', 24.0)
        throat_diameter = _flow_float(data, 'throat_diameter', 0.02)
        exit_diameter = _flow_float(data, 'exit_diameter')
        expansion_ratio = _flow_float(data, 'expansion_ratio')
        ambient_pressure = _flow_float(data, 'ambient_pressure', 101325.0)
        n_stations = int(_flow_float(data, 'n_stations', 45))
        separation_factor = _flow_float(data, 'separation_factor', 0.40)
        wall_temperature = _flow_float(data, 'wall_temperature', 800.0)
        friction_loss_fraction = _flow_float(
            data, 'friction_loss_fraction', 0.015)
    except ValueError as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 400

    # Geometri varsayılanı: ne çıkış çapı ne genişleme oranı verilmişse
    # tipik ε=4 (küçük atmosferik motor) ile çalışılır — panel önerileri
    # gerçek motor sonuçlarından doldurur.
    if exit_diameter is None and expansion_ratio is None:
        expansion_ratio = 4.0

    motor_data = {}
    if data.get('nozzle_type'):
        # sample_nozzle_inner_contour konik/bell ayrımını buradan okur
        motor_data['nozzle_angles'] = {'nozzle_type': str(data['nozzle_type'])}
    if data.get('chamber_diameter') is not None:
        try:
            motor_data['chamber_diameter'] = float(data['chamber_diameter'])
        except (TypeError, ValueError):
            pass

    try:
        solver = NozzleFlow1D(
            chamber_pressure=chamber_pressure_bar * 1e5,
            chamber_temperature=chamber_temperature,
            gamma=gamma,
            molecular_weight=molecular_weight,
            throat_diameter=throat_diameter,
            exit_diameter=exit_diameter,
            expansion_ratio=expansion_ratio,
            ambient_pressure=ambient_pressure,
            n_stations=n_stations,
            separation_factor=separation_factor,
            wall_temperature=wall_temperature,
            friction_loss_fraction=friction_loss_fraction,
            motor_data=motor_data,
        )
        flow = solver.solve(include_bartz=(fidelity == 'engineering'))
    except ValueError as exc:
        # Modülün fizik doğrulamaları (Pa >= Pc, gamma bandı...) — net 400
        return jsonify({'status': 'error', 'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 500

    kinetic_result = None
    kinetic_note = None
    if fidelity == 'fast':
        # İzantropik özet: istasyon dizileri taşınmaz (hızlı tarama seviyesi)
        flow.pop('stations', None)
        kinetic_note = ("Fast Screening level: station arrays and the "
                        "kinetic-efficiency chain require the Engineering "
                        "fidelity level.")
    else:
        nozzle_profile = None
        stations = flow.get('stations') or {}
        if stations.get('x_mm'):
            # Yüksek doğruluk kinetiği için quasi-1D profil (mm -> m)
            nozzle_profile = {
                'x': [v / 1000.0 for v in stations['x_mm']],
                'T': stations['temperature_K'],
                'P': stations['pressure_Pa'],
                'u': stations['velocity_m_s'],
            }
        kinetic_result, kinetic_note = _run_kinetic_chain(
            data, chamber_pressure_bar, throat_diameter,
            nozzle_profile=nozzle_profile)

    response = {
        'status': 'success',
        'fidelity': fidelity,
        'fidelity_levels': list(FLOW_FIDELITY_LEVELS),
        'flow': sanitize_json_values(flow),
        'kinetic_efficiency': kinetic_result,
    }
    if kinetic_note:
        response['kinetic_note'] = kinetic_note
    return jsonify(response)


@app.route('/api/kinetic-efficiency', methods=['POST'])
def kinetic_efficiency_analysis():
    """Tiered nozzle kinetic-efficiency analysis (successor of
    /api/kinetic-analysis).

    Fidelity: 'fast' (equilibrium reference), 'engineering' (JANNAF-style
    Damköhler correlation), 'high_fidelity' (Cantera finite-rate along a
    nozzle T(x), P(x) profile; graceful fallback to engineering — the
    'fidelity_used' field always reports what actually ran).

    Special modes:
      {'probe': true}  — capability probe only: reports whether the
                         high-fidelity path is available (no heavy work).
      {'async': true}  — queue the evaluation on the job runner; returns
                         202 with a job id to poll via GET /api/jobs/<id>.
    """
    data = request.get_json(silent=True) or {}

    # --- Yetenek sondası: Cantera + reaksiyonlu mekanizma var mı? ---
    # Panel, High-Fidelity seçeneğini fidelity_used alanından tespit eder.
    if data.get('probe'):
        available = False
        detail = 'Cantera is not installed'
        if KINETIC_CANTERA_AVAILABLE:
            try:
                # Modülün kendi mekanizma çözücüsü (önbellekli); reaksiyonsuz
                # termo-dosyalar (nasa_gas.yaml) elenir.
                kinetic_efficiency._get_kinetics_gas()
                available = True
                detail = (f"Cantera mechanism "
                          f"'{kinetic_efficiency._kin_mech_name}' ready")
            except Exception as exc:
                detail = str(exc)
        levels = ['fast', 'engineering'] + (['high_fidelity'] if available
                                            else [])
        return jsonify({
            'status': 'success',
            'probe': True,
            'fidelity_requested': 'high_fidelity',
            'fidelity_used': 'high_fidelity' if available else 'engineering',
            'cantera_available': bool(KINETIC_CANTERA_AVAILABLE),
            'fidelity_levels': levels,
            'detail': detail,
        })

    fidelity = str(data.get('fidelity', 'engineering'))
    if fidelity not in KINETIC_FIDELITY_LEVELS:
        return jsonify({
            'status': 'error',
            'error': (f"fidelity must be one of "
                      f"{list(KINETIC_FIDELITY_LEVELS)}; got '{fidelity}'."),
        }), 400

    try:
        of_ratio = _flow_float(data, 'of_ratio')
        chamber_pressure_bar = _flow_float(data, 'chamber_pressure', 20.0)
        characteristic_length = _flow_float(data, 'characteristic_length')
        throat_diameter = _flow_float(data, 'throat_diameter')
    except ValueError as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 400
    if of_ratio is None:
        return jsonify({
            'status': 'error',
            'error': ("Field 'of_ratio' is required (oxidizer-to-fuel mass "
                      "ratio, e.g. 6.0 for N2O/HTPB)."),
        }), 400

    fuel_composition = data.get('fuel_composition')
    if not isinstance(fuel_composition, dict) or not fuel_composition:
        fuel_composition = {str(data.get('fuel_type', 'htpb')): 100.0}

    kwargs = {
        'fuel_composition': fuel_composition,
        'oxidizer_type': str(data.get('oxidizer_type', 'N2O')),
        'of_ratio': of_ratio,
        'chamber_pressure': chamber_pressure_bar,
        'fidelity': fidelity,
        'characteristic_length': characteristic_length,
        'throat_diameter': throat_diameter,
        'nozzle_profile': data.get('nozzle_profile'),
    }

    if data.get('async'):
        # Uzun sürebilecek yol (Cantera BDF) iş kuyruğuna atılır; istemci
        # GET /api/jobs/<id> ile yoklar (job_runner sözleşmesi).
        job_id = job_runner.submit(_kinetic_evaluate_job, kwargs)
        return jsonify({
            'status': 'queued',
            'job_id': job_id,
            'poll_url': f'/api/jobs/{job_id}',
        }), 202

    try:
        result = kinetic_efficiency.evaluate(**kwargs)
    except ValueError as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 400
    except Exception as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 500

    payload = {'status': 'success'}
    payload.update(sanitize_json_values(result))
    return jsonify(payload)


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Poll a queued analysis job (job_runner contract).

    States: queued | running | done | error. A finished job carries
    'result'; a failed one carries 'error'. Records expire after the
    runner TTL (default 1 h) and then return 404.
    """
    try:
        status = job_runner.status(job_id)
    except KeyError:
        return jsonify({
            'status': 'error',
            'error': f'Unknown or expired job id: {job_id}',
        }), 404
    return jsonify({'status': 'success', 'job': sanitize_json_values(status)})


@app.route('/api/validation/upload-csv', methods=['POST'])
def validation_upload_csv():
    """Parse a user static-fire thrust CSV and (optionally) compare it with
    the HRMA prediction.

    Accepts either:
      - a plain-text body (text/csv, text/plain): parse only, or
      - JSON {'csv_text': str, 'predicted_curve': {'time': [...],
        'thrust': [...]}} — parse + quantitative comparison (total impulse,
        peak/mean thrust, NFPA 1125 burn time, RMSE/NRMSE, English
        assessment).
    """
    predicted_curve = None
    csv_text = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        csv_text = data.get('csv_text')
        predicted_curve = data.get('predicted_curve')
    else:
        csv_text = request.get_data(as_text=True)

    if not isinstance(csv_text, str) or not csv_text.strip():
        return jsonify({
            'status': 'error',
            'error': ("No CSV content provided. Send the file as a "
                      "text/csv body, or as JSON {'csv_text': '...'} with "
                      "an optional 'predicted_curve' {'time', 'thrust'}."),
        }), 400

    try:
        parsed = parse_thrust_csv(csv_text)
    except ValueError as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 400

    parsed_out = {
        'time': parsed['time'].tolist(),
        'thrust': parsed['thrust'].tolist(),
        'n_points': parsed['n_points'],
        'warnings': parsed['warnings'],
    }

    comparison = None
    if predicted_curve is not None:
        try:
            comparison = sanitize_json_values(
                compare_thrust_curves(parsed, predicted_curve))
        except ValueError as exc:
            # CSV çözüldü ama karşılaştırma anlamsız (örtüşme yok vb.):
            # panel çözümlemeyi yine gösterebilsin diye parsed eklenir.
            return jsonify({
                'status': 'error',
                'error': str(exc),
                'parsed': parsed_out,
            }), 400

    return jsonify({
        'status': 'success',
        'parsed': parsed_out,
        'comparison': comparison,
    })


# ---------------------------------------------------------------------------
# v2.5.0 G3 — Belirsizlik nicelemesi (UQ) endpoint'i
# ---------------------------------------------------------------------------
# Kontrat (G3 API dalgası): POST /api/uncertainty-analysis
#   fast / engineering  -> senkron 'ok' gövdesi
#   high_fidelity       -> job_runner'a kuyruklanır (202 + job_id; sonuç
#                          GET /api/jobs/<id> sözleşmesiyle, job.result =
#                          aynı 'ok' gövdesi)
# Motor print gürültüsü endpoint kapsamında os.devnull'a yönlendirilir.

_UQ_MOTOR_TYPES = ('hybrid', 'solid', 'liquid')


class _UQAnalysisError(RuntimeError):
    """UQ koşusu status='error' döndürdü (örnek #0 tutarlılık kırılması
    dahil) — sessiz düşme yok, 500 + mesajla yukarı taşınır."""


def _uq_contract_body(motor_type, level, result):
    """run_uncertainty sonucunu G3 API kontrat gövdesine çevirir.

    Kontrat alanlarına ek olarak şeffaflık alanları taşınır (sampler,
    uq_version, inputs_used künyeleri, yöntem notu) — kontratın üst kümesi.
    'cv' yüzde cinsindendir (mevcut solid MC cv_percent geleneği); aynı değer
    'cv_percent' adıyla da yankılanır ki birim belirsizliği kalmasın.
    """
    outputs = {}
    for key, block in result['outputs'].items():
        outputs[key] = {
            'nominal': block['nominal'],
            'mean': block['mean'],
            'std': block['std'],
            'cv': block['cv_percent'],
            'cv_percent': block['cv_percent'],
            'p5': block['p5'],
            'p25': block['p25'],
            'p50': block['p50'],
            'p75': block['p75'],
            'p95': block['p95'],
            'histogram': block['histogram'],
        }
    sensitivity = {}
    for key, rows in result['sensitivity'].items():
        if key == 'method_note':
            continue
        sensitivity[key] = [
            {'param': row['param'], 'rho': row['spearman']} for row in rows
        ]
    body = {
        'status': 'ok',
        'motor_type': motor_type,
        'level': level,
        'n_samples': result['n_samples'],
        'failed_samples': result['failed_samples'],
        'seed': result['seed'],
        'timing_s': result['timing']['wall_s'],
        'mean_shift_percent': result['consistency']['mean_shift_percent'],
        'outputs': outputs,
        'sensitivity': sensitivity,
        'sensitivity_method_note': result['sensitivity'].get('method_note'),
        'sampler': result['sampler'],
        'uq_version': result['uq_version'],
        'inputs_used': result['inputs_used'],
        'consistency_note': result['consistency'].get('note'),
    }
    if result.get('warning'):
        body['warning'] = result['warning']
    return body


def _run_uq_analysis(motor_type, level, seed, inputs, overrides,
                     n_samples=None, progress_callback=None):
    """Senkron ve job yolunun ortak çekirdeği.

    Raises:
        ValueError: girdi/dağılım doğrulama hatası (endpoint 400'e çevirir).
        _UQAnalysisError: koşu status='error' bitirdi (endpoint 500).
    """
    from hrma.analysis import uncertainty as _uq
    from hrma.analysis import uq_adapters as _uqa

    distributions = _uqa.build_distributions(motor_type, overrides)
    if n_samples is None:
        n = _uq.LEVEL_BUDGETS[level]
    else:
        n = max(50, min(int(n_samples), 10000))  # spec 7.1 kırpması
    track = (level == 'high_fidelity')  # spec: yalnız High-Fidelity O/F izler

    cb = None
    if progress_callback is not None:
        def cb(done, total):
            progress_callback(done / max(total, 1))

    with open(os.devnull, 'w') as devnull, \
            contextlib.redirect_stdout(devnull):
        factory = _uqa.make_factory(motor_type, inputs,
                                    track_performance=track)
        result = _uq.run_uncertainty(
            factory, distributions, n_samples=n, seed=seed,
            progress_callback=cb)

    if result.get('status') != 'success':
        raise _UQAnalysisError(
            result.get('error') or 'uncertainty analysis failed')
    return sanitize_json_values(_uq_contract_body(motor_type, level, result))


def _uncertainty_job(payload, progress_callback=None):
    """job_runner işi: high_fidelity UQ koşusu (job.result = 'ok' gövdesi)."""
    return _run_uq_analysis(
        payload['motor_type'], payload['level'], payload['seed'],
        payload['inputs'], payload['overrides'], payload.get('n_samples'),
        progress_callback=progress_callback)


@app.route('/api/uncertainty-analysis', methods=['POST'])
def uncertainty_analysis():
    """Monte Carlo / LHS uncertainty analysis (G3 contract).

    Request: {motor_type, level, seed?, inputs, distribution_overrides?,
    n_samples?}. fast/engineering run synchronously; high_fidelity is queued
    on the job runner (202 + job_id, poll GET /api/jobs/<id>; the finished
    job's result is the same 'ok' body).
    """
    data = request.get_json(silent=True) or {}

    motor_type = data.get('motor_type')
    if motor_type not in _UQ_MOTOR_TYPES:
        return jsonify({
            'status': 'error',
            'error': (f"motor_type must be one of {list(_UQ_MOTOR_TYPES)}; "
                      f"got {motor_type!r}."),
        }), 400

    from hrma.analysis.uncertainty import LEVEL_BUDGETS as _LEVELS
    level = data.get('level')
    if level not in _LEVELS:
        return jsonify({
            'status': 'error',
            'error': (f"level must be one of {sorted(_LEVELS)}; "
                      f"got {level!r}."),
        }), 400

    try:
        seed = int(data.get('seed', 42))
    except (TypeError, ValueError):
        return jsonify({'status': 'error',
                        'error': "Field 'seed' must be an integer."}), 400

    inputs = data.get('inputs')
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        return jsonify({'status': 'error',
                        'error': "Field 'inputs' must be an object with the "
                                 "motor form fields."}), 400

    overrides = data.get('distribution_overrides')
    n_samples = data.get('n_samples')
    if n_samples is not None:
        try:
            n_samples = int(n_samples)
        except (TypeError, ValueError):
            return jsonify({'status': 'error',
                            'error': "Field 'n_samples' must be an "
                                     "integer."}), 400

    # Dağılım kümesi erken doğrulanır: bozuk override job kuyruğuna girmeden
    # net bir 400 ile dönsün (job yolunda hata ancak poll'da görünürdü).
    try:
        from hrma.analysis import uq_adapters as _uqa
        _uqa.build_distributions(motor_type, overrides)
    except ValueError as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 400

    if level == 'high_fidelity':
        job_id = job_runner.submit(_uncertainty_job, {
            'motor_type': motor_type,
            'level': level,
            'seed': seed,
            'inputs': inputs,
            'overrides': overrides,
            'n_samples': n_samples,
        })
        return jsonify({
            'status': 'queued',
            'job_id': job_id,
            'poll_url': f'/api/jobs/{job_id}',
        }), 202

    try:
        body = _run_uq_analysis(motor_type, level, seed, inputs, overrides,
                                n_samples)
    except ValueError as exc:
        return jsonify({'status': 'error', 'error': str(exc)}), 400
    except _UQAnalysisError as exc:
        # Örnek #0 tutarlılık kırılması dahil: sessiz düşme yok (spec 7.3)
        return jsonify({'status': 'error', 'error': str(exc)}), 500
    except Exception as exc:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(exc)}), 500
    return jsonify(body)


# ---------------------------------------------------------------------------
# v2.5.0 G3 — Otomatik korelasyon raporu endpoint'i
# ---------------------------------------------------------------------------
# GET  /api/correlation-report          -> önbellekli özet (ilk çağrı koşar)
# POST /api/correlation-report {refresh:true} -> önbelleği yok say, yeniden koş
# Önbellek anahtarı: deney DB içerik hash'i (correlation_runner.db_content_hash)

_CORRELATION_CACHE = {}


def _correlation_report_body(refresh=False):
    """Korelasyon rapor gövdesini kurar (modül-içi {db_hash: gövde} önbelleği).

    Koşu ~15-25 s sürer (Cantera denge çözümleri); ilk çağrı senkron kabul
    edilir, sonrakiler cached=true ile anında döner. DB içeriği değişince
    hash değişir ve önbellek kendiliğinden ıskalar.
    """
    from hrma.validation import correlation_runner as _cr
    from hrma.validation.experiment_db import (load_records,
                                               records_for_statistics)
    from hrma.validation.status_report import correlation_cells

    records = load_records()
    stat_records = sorted(records_for_statistics(records),
                          key=lambda r: r.get('test_id', ''))
    db_hash = _cr.db_content_hash(stat_records)

    if not refresh and db_hash in _CORRELATION_CACHE:
        body = dict(_CORRELATION_CACHE[db_hash])
        body['cached'] = True
        return body

    with open(os.devnull, 'w') as devnull, \
            contextlib.redirect_stdout(devnull):
        result = _cr.run_correlation(records=records)

    skipped_scores = {}
    for rr in result['records']:
        for score in rr.get('scores', {}).values():
            status = score.get('status')
            if status and status != 'scored':
                skipped_scores[status] = skipped_scores.get(status, 0) + 1

    body = sanitize_json_values({
        'status': 'ok',
        'db_hash': result['db_content_hash'],
        'cached': False,
        'generated_s': result['timing']['total_s'],
        'record_counts': {
            'total': result['n_records'],
            'scored': result['status_counts'].get('ok', 0),
            'insufficient_inputs': result['status_counts'].get(
                'insufficient_inputs', 0),
            'not_supported': result['status_counts'].get('not_supported', 0),
            'runner_error': result['status_counts'].get('runner_error', 0),
        },
        'cells': correlation_cells(result['statistics']),
        'skipped_summary': {
            'status_counts': result['status_counts'],
            'not_supported': result['not_supported'],
            'insufficient_inputs': result['insufficient_inputs'],
            'runner_errors': result['runner_errors'],
            'skipped_score_counts': dict(sorted(skipped_scores.items())),
        },
        'markdown': _cr.to_markdown(result),
    })

    # Tek girdilik önbellek: DB değişince eski sonuç bellekte birikmesin
    _CORRELATION_CACHE.clear()
    _CORRELATION_CACHE[db_hash] = body
    return dict(body)


@app.route('/api/correlation-report', methods=['GET', 'POST'])
def correlation_report():
    """Real-experiment correlation report (G3 contract).

    GET returns the cached report when the experiment DB is unchanged
    (cached=true); the first call runs the full correlation synchronously.
    POST with {"refresh": true} ignores the cache and re-runs.
    """
    refresh = False
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        refresh = bool(data.get('refresh'))
    try:
        body = _correlation_report_body(refresh=refresh)
    except Exception as exc:
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(exc)}), 500
    return jsonify(body)


if __name__ == '__main__':
    # Gerçek giriş noktası hrma/run.py (waitress, 8080); bu blok yalnız geliştirme içindir.
    print("Starting Motor Analysis on port 8080...")
    app.run(debug=True, port=8080, host='127.0.0.1')