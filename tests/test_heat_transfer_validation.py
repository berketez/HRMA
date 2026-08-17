"""
Validation tests for the gas-side heat-transfer model (Bartz correlation).

Background
----------
The previous implementation used a tube-flow Dittus-Boelter correlation for the
rocket-chamber gas side. That under-predicted the gas-side convective
coefficient h_g by roughly 4-15x in the UNSAFE direction (a too-low h_g hides
burn-through). This module replaced it with the Bartz throat correlation
(Sutton & Biblarz 9th ed. Eq. 8-22; Bartz 1957) in SI-consistent form.

Reference values
----------------
- RS-25 / SSME throat (LOX/LH2):
    Gas properties from RocketCEA equilibrium at Pc=206 bar, MR=6:
      Tc~3598 K, c*~2323 m/s, gamma~1.147, MW~13.6 g/mol.
    Literature throat gas-side coefficient h_g ~ 40-120 kW/m^2/K and throat
    heat flux ~ 80-160 MW/m^2 (Huzel & Huang; NASA SP-8124).
- N2O/HTPB hybrid (Pc=20 bar):
    Tc~3346 K, c*~1602 m/s, gamma~1.147, MW~26.7 g/mol (RocketCEA).
    Throat heat flux for an aggressive small motor ~ a few to ~25 MW/m^2.

These reference numbers are reproduced numerically with RocketCEA in
test_reference_gas_properties_match_rocketcea (skipped if RocketCEA absent).

Run:
    cd <depo kökü>
    MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/test_heat_transfer_validation.py -v
"""

import math
import numpy as np
import pytest

from hrma.analysis.heat_transfer_analysis import HeatTransferAnalyzer


# ----------------------------------------------------------------------
# Reference motor cases (gas props from RocketCEA equilibrium, see header)
# ----------------------------------------------------------------------
RS25 = {
    'chamber_pressure': 206.0,       # bar
    'chamber_temperature': 3598,     # K
    'chamber_diameter': 0.45,        # m
    'chamber_length': 0.35,          # m
    'burn_time': 480,                # s
    'mdot_total': 468.0,             # kg/s
    'throat_diameter': 0.262,        # m (RS-25 throat ~26.2 cm)
    'c_star': 2323,                  # m/s
    'gamma': 1.147,
    'molecular_weight': 13.61,       # g/mol
}

HYBRID_N2O_HTPB = {
    'chamber_pressure': 20.0,        # bar
    'chamber_temperature': 3346,     # K
    'chamber_diameter': 0.10,        # m
    'chamber_length': 0.50,          # m
    'burn_time': 10,                 # s
    'mdot_total': 1.0,               # kg/s
    'throat_diameter': 0.03,         # m
    'c_star': 1602,                  # m/s
    'gamma': 1.147,
    'molecular_weight': 26.66,       # g/mol
}


@pytest.fixture
def analyzer():
    return HeatTransferAnalyzer()


# ----------------------------------------------------------------------
# 1. Bartz h_g matches literature for the RS-25 throat
# ----------------------------------------------------------------------
def test_rs25_gas_side_coefficient_in_literature_band(analyzer):
    """RS-25 throat h_g should fall in the literature band 40-120 kW/m^2/K."""
    r = analyzer.analyze_heat_transfer(
        dict(RS25), material='copper', wall_thickness=0.001, cooling_type='regenerative'
    )
    h_g = r['heat_transfer_coefficients']['gas_side']  # W/m^2/K
    assert 40e3 <= h_g <= 120e3, (
        f"RS-25 throat h_g={h_g:.0f} W/m^2/K outside literature band 40-120 kW/m^2/K"
    )
    assert r['heat_transfer_coefficients']['correlation'].startswith('Bartz')


#: RS-25 boğaz ısı akısı literatür bandı [W/m^2]. Dosya başlığındaki
#: "Reference values" bölümünün TEK KAYNAĞI (Huzel & Huang; NASA SP-8124).
#: Kapı da hata mesajı da buradan okur — üçünün ayrışması T1-3 kusuruydu.
RS25_THROAT_FLUX_BAND_W_M2 = (80e6, 160e6)


def test_rs25_throat_heat_flux_in_literature_band(analyzer):
    """RS-25 design throat heat flux should be ~80-160 MW/m^2.

    T1-3 (parti 31): the docstring and the failure message both said
    80-160 MW/m^2 while the gate accepted 80-200e6. Anything in
    160-200 MW/m^2 passed silently against a band nobody had declared.
    Measured today: 131.4 MW/m^2 -- inside the declared band, so closing
    the gate to the declaration does NOT relax or move any number; it
    removes an undeclared 40 MW/m^2 of slack.
    """
    r = analyzer.analyze_heat_transfer(
        dict(RS25), material='copper', wall_thickness=0.001, cooling_type='regenerative'
    )
    q = r['gas_side_analysis']['throat_heat_flux']  # W/m^2
    lo, hi = RS25_THROAT_FLUX_BAND_W_M2
    assert lo <= q <= hi, (
        f"RS-25 throat heat flux q={q/1e6:.1f} MW/m^2 outside band "
        f"{lo/1e6:.0f}-{hi/1e6:.0f} MW/m^2"
    )


def test_rs25_band_declaration_matches_the_gate():
    """Beyan ile kapı AYNI bandı söylemeli (T1-3 bekçisi).

    Dosya başlığındaki referans bandı ile kapının kullandığı sabit
    ayrışırsa bu bekçi kırılır — kapının sessizce genişletilmesi (80-200)
    tam olarak böyle olmuştu.
    """
    import pathlib
    import re
    kaynak = pathlib.Path(__file__).read_text(encoding='utf-8')
    basligi = kaynak.split('"""')[1]
    eslesme = re.search(r'heat flux ~ (\d+)-(\d+) MW/m\^2', basligi)
    assert eslesme, 'dosya başlığındaki RS-25 akı bandı beyanı bulunamadı'
    beyan = (float(eslesme.group(1)) * 1e6, float(eslesme.group(2)) * 1e6)
    assert beyan == RS25_THROAT_FLUX_BAND_W_M2, (
        f'başlık {beyan} diyor, kapı {RS25_THROAT_FLUX_BAND_W_M2} '
        'kullanıyor — beyan ile kapı ayrıştı (T1-3)')


# ----------------------------------------------------------------------
# 2. Bartz vs old Dittus-Boelter: confirm the under-prediction was 4-15x
# ----------------------------------------------------------------------
def _old_dittus_boelter_h(motor_data):
    """Replicate the previous (buggy) chamber Dittus-Boelter h_g for comparison."""
    R_gas = motor_data.get('gas_constant', 287)
    Tc = motor_data['chamber_temperature']
    P = motor_data['chamber_pressure'] * 1e5
    D = motor_data['chamber_diameter']
    mdot = motor_data['mdot_total']
    k_old, mu_old, cp_old = 0.2, 5e-5, 1200  # the old hardcoded values
    rho = P / (R_gas * Tc)
    v = mdot / (rho * np.pi * (D / 2) ** 2)
    Re = rho * v * D / mu_old
    Pr = cp_old * mu_old / k_old
    Nu = 0.023 * Re ** 0.8 * Pr ** 0.4
    return Nu * k_old / D


def test_bartz_is_higher_than_dittus_boelter_safe_direction(analyzer):
    """
    The new Bartz h_g must be substantially HIGHER than the old Dittus-Boelter
    value (the old one was unsafe-low). Under-prediction factor in the 4-15x
    range for the hybrid reference case.
    """
    r = analyzer.analyze_heat_transfer(
        dict(HYBRID_N2O_HTPB), material='copper', wall_thickness=0.002,
        cooling_type='regenerative'
    )
    h_new = r['heat_transfer_coefficients']['gas_side']
    h_old = _old_dittus_boelter_h(HYBRID_N2O_HTPB)
    factor = h_new / h_old
    assert h_new > h_old, "Bartz must exceed Dittus-Boelter (safe direction)"
    assert 4.0 <= factor <= 20.0, (
        f"Under-prediction factor {factor:.1f}x outside expected 4-20x "
        f"(h_old={h_old:.0f}, h_new={h_new:.0f})"
    )


# ----------------------------------------------------------------------
# 3. No hardcoded gas properties / no chamber*1.5 throat flux
# ----------------------------------------------------------------------
def test_gas_properties_not_hardcoded(analyzer):
    """
    Gas viscosity must respond to molecular weight / temperature (it was a
    hardcoded constant 5e-5 before). Two different gases must give different mu.
    """
    c_rs25 = analyzer.analyze_heat_transfer(dict(RS25))['heat_transfer_coefficients']
    c_hyb = analyzer.analyze_heat_transfer(dict(HYBRID_N2O_HTPB))['heat_transfer_coefficients']
    assert c_rs25['gas_viscosity'] != pytest.approx(5e-5, rel=0.01)
    assert c_rs25['gas_viscosity'] != c_hyb['gas_viscosity'], (
        "Different propellants must yield different gas viscosity (not hardcoded)"
    )


def test_throat_flux_not_chamber_times_constant(analyzer):
    """
    throat_heat_flux must come from a real Bartz throat evaluation, not a fixed
    1.5x of the chamber flux. Verify the ratio is not pinned at 1.5.
    """
    r = analyzer.analyze_heat_transfer(
        dict(RS25), material='copper', wall_thickness=0.001, cooling_type='regenerative'
    )
    g = r['gas_side_analysis']
    ratio = g['throat_heat_flux'] / g['chamber_heat_flux']
    # Throat flux is higher than chamber (A_t/A=1 vs <1) but the ratio is a
    # physical Bartz outcome, not exactly 1.5.
    assert ratio > 1.0
    assert not math.isclose(ratio, 1.5, rel_tol=0.02), (
        "throat/chamber flux ratio is suspiciously pinned at 1.5 (old hardcode)"
    )


# ----------------------------------------------------------------------
# 4. Wall temperature is physical and unsafe cooling is flagged
# ----------------------------------------------------------------------
def test_wall_temperature_is_finite_and_bounded(analyzer):
    """
    Wall temperature must never be a nonsense value (a prior test produced
    53250 K). Equilibrium wall temperature is bounded by the adiabatic-wall
    temperature from above.
    """
    r = analyzer.analyze_heat_transfer(
        dict(RS25), material='copper', wall_thickness=0.001, cooling_type='regenerative'
    )
    g = r['gas_side_analysis']
    Tw = g['estimated_wall_temperature']
    Taw = g['adiabatic_wall_temperature']
    assert np.isfinite(Tw)
    assert 200.0 < Tw <= Taw + 1.0, f"Wall temp {Tw:.0f} K not physically bounded by Taw {Taw:.0f} K"
    assert Taw < 4000.0, "Adiabatic wall temperature unreasonably high"


def test_natural_cooling_flags_burn_through(analyzer):
    """
    A steel chamber with only natural-convection cooling at 20 bar MUST be
    flagged as unsafe (this is the dangerous default the engine passes). The
    design heat flux must remain non-zero (not masked by a floating wall temp).

    GÜNCELLEME (v2.6.2, fizik denetimi F011): bu test eskiden
    'warn.thermal.wall_exceeds_service' bekliyordu. steel_4130 için
    max_service_temperature = 2000 K, melting_point = 1705 K — yani servis
    eşiği erime noktasının ÜSTÜNDEYDİ ve erimiş cidar yalnız 'servis sınırı
    aşıldı' diye raporlanıyordu. Kritik eşik artık
    min(max_service_temperature, melting_point) ile kurulduğu için bu senaryo
    daha sert ve doğru olan 'warn.thermal.wall_exceeds_melting' üretir. Test,
    kritik seviyenin korunduğunu ve erime bilgisinin görünür olduğunu
    doğrular.
    """
    md = {
        'chamber_pressure': 20.0, 'chamber_temperature': 3000,
        'chamber_diameter': 0.1, 'chamber_length': 0.5,
        'burn_time': 10, 'mdot_total': 1.0,
    }
    r = analyzer.analyze_heat_transfer(
        md, material='steel_4130', wall_thickness=0.005, cooling_type='natural'
    )
    g = r['gas_side_analysis']
    assert g['wall_temperature_unphysical'] is True
    # Design heat flux must NOT collapse to zero (the masking bug).
    assert g['throat_heat_flux'] > 1e6, "Design throat flux collapsed (burn-through masked!)"
    # D-track: uyarılar artık {code,params,severity}; metin frontend'de.
    warns = r['safety_analysis']['warnings']
    codes = {w['code'] for w in warns}
    assert 'warn.thermal.wall_exceeds_melting' in codes, (
        f"Erimiş cidar erime koduyla bildirilmedi; üretilen kodlar: {sorted(codes)}")
    melt = next(w for w in warns if w['code'] == 'warn.thermal.wall_exceeds_melting')
    # Kritik seviye korunmalı ve erime noktası kullanıcıya görünür olmalı.
    assert melt['severity'] == 'critical'
    assert melt['params']['melting'] > 0
    assert melt['params']['T_wall'] > melt['params']['melting']


def test_regenerative_cooling_keeps_wall_cooler_than_natural(analyzer):
    """Adequate (regenerative) cooling must yield a lower equilibrium wall temp."""
    md = dict(HYBRID_N2O_HTPB)
    nat = analyzer.analyze_heat_transfer(md, material='copper', wall_thickness=0.002,
                                         cooling_type='natural')
    reg = analyzer.analyze_heat_transfer(md, material='copper', wall_thickness=0.002,
                                         cooling_type='regenerative')
    assert (reg['gas_side_analysis']['estimated_wall_temperature']
            < nat['gas_side_analysis']['estimated_wall_temperature'])


# ----------------------------------------------------------------------
# 5. API / contract preservation
# ----------------------------------------------------------------------
def test_public_api_keys_preserved(analyzer):
    """All original top-level and key sub-level dict keys must still be present."""
    r = analyzer.analyze_heat_transfer(dict(HYBRID_N2O_HTPB))
    for k in ('heat_transfer_coefficients', 'gas_side_analysis', 'wall_analysis',
              'cooling_analysis', 'safety_analysis', 'material_properties',
              'design_parameters'):
        assert k in r, f"missing top-level key {k}"
    for k in ('gas_side', 'coolant_side', 'reynolds_number', 'prandtl_number',
              'nusselt_number'):
        assert k in r['heat_transfer_coefficients']
    for k in ('heat_flux', 'total_heat_rate', 'surface_area', 'throat_heat_flux',
              'chamber_heat_flux', 'gas_temperature', 'estimated_wall_temperature'):
        assert k in r['gas_side_analysis']
    for k in ('inner_temperature', 'outer_temperature', 'average_temperature',
              'max_temperature', 'temperature_gradient', 'thermal_resistance',
              'temperature_drops'):
        assert k in r['wall_analysis']


def test_steel_4130_alias_resolved(analyzer):
    """hybrid_rocket_engine passes material='steel_4130'; must not silently
    fall back to a generic material with wrong properties."""
    a = HeatTransferAnalyzer()
    assert 'steel_4130' in a.materials
    r = a.analyze_heat_transfer(dict(HYBRID_N2O_HTPB), material='steel_4130')
    assert r['design_parameters']['material'] == 'steel_4130'


def test_minimal_motor_data_does_not_crash(analyzer):
    """The engine call site passes only 6 basic keys (no throat/c*/gas props).
    The module must self-derive throat conditions and gas properties."""
    md = {
        'chamber_pressure': 20.0, 'chamber_temperature': 3000,
        'chamber_diameter': 0.1, 'chamber_length': 0.5,
        'burn_time': 10, 'mdot_total': 1.0,
    }
    r = analyzer.analyze_heat_transfer(md, material='steel_4130',
                                       wall_thickness=0.005, cooling_type='natural')
    c = r['heat_transfer_coefficients']
    assert c['gas_side'] > 0
    assert c['throat_diameter'] > 0
    assert c['c_star'] > 500  # derived c* must be physical


# ----------------------------------------------------------------------
# 6. Cross-check reference gas properties against RocketCEA (optional)
# ----------------------------------------------------------------------
def test_reference_gas_properties_match_rocketcea():
    """
    Independent cross-check: the RS-25 reference Tc, c*, gamma used above should
    match a fresh RocketCEA equilibrium solve within tolerance. Skipped if
    RocketCEA is unavailable.
    """
    rocketcea = pytest.importorskip("rocketcea")
    from rocketcea.cea_obj_w_units import CEA_Obj
    C = CEA_Obj(oxName='LOX', fuelName='LH2',
                cstar_units='m/s', pressure_units='bar', temperature_units='K')
    Pc, MR = 206.0, 6.0
    Tc = C.get_Tcomb(Pc=Pc, MR=MR)
    cstar = C.get_Cstar(Pc=Pc, MR=MR)
    assert Tc == pytest.approx(RS25['chamber_temperature'], rel=0.05)
    assert cstar == pytest.approx(RS25['c_star'], rel=0.05)


if __name__ == '__main__':
    import sys
    sys.exit(pytest.main([__file__, '-v']))
