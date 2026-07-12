"""Katı ve sıvı motor sonuçlarını ortak motor-geometri sözlüğüne çevirir.

Kesit çizimi (create_improved_motor_cross_section), STEP/STL üreticileri ve
teknik çizimler hibrit-şekilli, METRE bazlı bir motor_data sözlüğü bekler.
Katı motor rotası mm bazlı, sıvı motor rotası KARIŞIK birimli (chamber mm,
throat/exit m) sonuç döndürür — dönüşümler burada tek noktada yapılır.
"""

import numpy as np


def _num(v, fb):
    try:
        f = float(v)
        return f if np.isfinite(f) else fb
    except (TypeError, ValueError):
        return fb


def solid_results_to_motor_geometry(results):
    """/calculate_solid sonucundan hibrit-şekilli geometri (m) üretir.

    Katıda 'port' çekirdek (core) deliğidir: başlangıç portu = core çapı,
    son port = grain dış çapı (web tamamen yanar).
    """
    r = results or {}
    gd = r.get('grain_design') or {}
    ks = ((r.get('design_summary') or {}).get('key_dimensions')) or {}
    case = ((r.get('cad_design') or {}).get('case_design')) or {}

    grain_len_mm = _num(gd.get('grain_length_mm'), _num(r.get('grain_length'), 500.0))
    chamber_d_mm = _num(case.get('inner_diameter'),
                        _num(r.get('chamber_diameter'), 100.0))
    chamber_l_mm = _num(case.get('length'),
                        _num(ks.get('motor_length_mm'), grain_len_mm / 0.85))
    chamber_l_mm = max(chamber_l_mm, grain_len_mm * 1.05)
    core_d_mm = _num(gd.get('inner_diameter_mm'), _num(r.get('core_diameter'), 30.0))
    grain_od_mm = _num(gd.get('outer_diameter_mm'), chamber_d_mm - 4.0)

    return {
        'motor_name': r.get('motor_name') or 'UZAYTEK_SOLID',
        'chamber_diameter': chamber_d_mm / 1000.0,
        'chamber_length': chamber_l_mm / 1000.0,
        'throat_diameter': _num(r.get('throat_diameter'), 20.0) / 1000.0,
        'exit_diameter': _num(r.get('exit_diameter'), 60.0) / 1000.0,
        'expansion_ratio': _num(r.get('expansion_ratio'), 9.0),
        'chamber_pressure': _num(r.get('chamber_pressure'), 40.0),
        'burn_time': _num(r.get('burn_time'), 0.0),
        'thrust': _num(r.get('average_thrust'), 0.0),
        'total_impulse': _num(r.get('total_impulse'), 0.0),
        'isp': _num(r.get('specific_impulse'), 0.0),
        'propellant_mass_total': _num(r.get('propellant_mass'), 0.0),
        'grain_length': grain_len_mm / 1000.0,
        'port_diameter_initial': core_d_mm / 1000.0,
        'port_diameter_final': grain_od_mm / 1000.0,
        'grain_design': gd,
        'nozzle_angles': r.get('nozzle_angles') or {},
        'structural_analysis': r.get('structural_analysis') or {},
    }


def liquid_results_to_motor_geometry(results):
    """/calculate_liquid sonucundan hibrit-şekilli geometri (m) üretir.

    Dikkat — sıvı rotasının birimleri karışıktır: chamber_diameter ve
    chamber_length MM, throat_diameter ve exit_diameter METRE döner.
    """
    r = results or {}
    inj = r.get('injector_design') or {}
    ang = r.get('nozzle_angles') or {}

    return {
        'motor_name': r.get('motor_name') or 'UZAYTEK_LIQUID',
        'chamber_diameter': _num(r.get('chamber_diameter'), 150.0) / 1000.0,
        'chamber_length': _num(r.get('chamber_length'), 300.0) / 1000.0,
        'throat_diameter': _num(r.get('throat_diameter'), 0.03),
        'exit_diameter': _num(r.get('exit_diameter'), 0.09),
        'expansion_ratio': _num(r.get('expansion_ratio'), 9.0),
        'chamber_pressure': _num(r.get('chamber_pressure'), 50.0),
        'burn_time': _num(r.get('burn_time'), 0.0),
        'thrust': _num(r.get('thrust'), 0.0),
        'isp': _num(r.get('isp_sea_level'), 0.0),
        'of_ratio': _num(r.get('mixture_ratio'), 0.0),
        'nozzle_angles': ang,
        'injector_design': {
            'injector_type': inj.get('injector_type'),
            'number_of_orifices': int(_num(inj.get('number_of_elements'), 12)),
            'orifice_diameter_mm': _num(inj.get('fuel_orifice_diameter_mm'), 1.5),
            'injection_pressure_drop_bar':
                _num(inj.get('injection_pressure_drop_fuel_bar'), 0.0),
        },
    }
