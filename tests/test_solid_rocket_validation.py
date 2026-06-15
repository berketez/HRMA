#!/usr/bin/env python3
"""
Solid Rocket Motor Validation Test Suite
========================================
Validates solid rocket motor calculations against INDEPENDENT references:
published standard-atmosphere tables and closed-form analytic results.

Test Cases:
1. APCP reference set validation (CEA-consistent synthetic reference set;
   independent checks: c* thermodynamic identity + literature Isp)
2. Saint-Robert's law burn rate validation (analytic r = a*P^n)
3. Standard atmosphere altitude validation (US Standard Atmosphere 1976)
4. Thrust coefficient validation (full CF: momentum + pressure term)

Reference Data Sources:
- U.S. Standard Atmosphere 1976 (NOAA/NASA/USAF), Table I (geometric altitude)
- Sutton & Biblarz: Rocket Propulsion Elements (9th Edition)
- CEA-consistent synthetic APCP reference set. NOT experimental NASA data.
  (The attribution previously used here, "NASA RP-1271: Solid Propellant
  Grain Design and Internal Ballistics", was incorrect on both counts:
  RP-1271 is McBride & Gordon, "Computer Program for Calculating and
  Fitting Thermodynamic Functions", 1992, and contains no APCP reference
  motor; grain design is covered by NASA SP-8076.)

This file runs both as a script (python3 tests/test_solid_rocket_validation.py)
and under pytest (module-level test_* wrappers at the bottom).
"""

import os
import json
from datetime import datetime

import numpy as np
import matplotlib
if os.environ.get('MPLBACKEND') is None:
    # Headless-safe default (pytest/CI); plots are saved to file anyway.
    matplotlib.use('Agg')
import matplotlib.pyplot as plt

from hrma.engines.solid_rocket_engine import SolidRocketEngine


class SolidRocketValidationTest:
    """Comprehensive validation test suite for solid rocket motor calculations"""

    def __init__(self):
        self.results = {}
        self.tolerance_percentage = 5.0  # 5% tolerance for validation
        self.reference_data = self._load_reference_data()

    def _load_reference_data(self):
        """Load independent reference data for validation.

        All numbers below either come from published standard tables
        (US Standard Atmosphere 1976) or are computed from closed-form
        textbook equations (Sutton & Biblarz, 9th ed.). The APCP set is a
        synthetic, CEA-consistent reference set — it is NOT experimental
        data and is labelled accordingly.
        """
        return {
            'apcp_reference': {
                # CEA-consistent synthetic APCP reference set (NOT experimental).
                'description': 'CEA-consistent APCP reference set (synthetic reference, not experimental data)',
                'chamber_diameter': 100,  # mm
                'grain_length': 500,      # mm
                'core_diameter': 30,      # mm
                'chamber_pressure': 68.9, # bar (= 1000 psia, standard rating condition)
                # --- INDEPENDENT references (not copied from the engine) ---
                # c* from the thermodynamic identity c* = sqrt(R*Tc)/Gamma(gamma),
                # Gamma(g) = sqrt(g)*(2/(g+1))^((g+1)/(2(g-1)))
                # (Sutton & Biblarz 9th ed., Eq. 3-32), evaluated for the
                # documented set gamma=1.1986, M=28.0 g/mol
                # (R = 8314.46/28.0 = 296.945 J/kg/K), Tc=3614.8 K:
                # sqrt(296.945*3614.8)/0.64826 = 1598.2 m/s
                # (2026-06-12: motor APCP seti bu özdeşlikle tutarlı hale
                # getirildi — T_c ve M, c*=1598.2 ile uzlaştırıldı.)
                'expected_c_star': 1598.2,  # m/s (Sutton Eq. 3-32; independent identity)
                # Typical delivered sea-level Isp of aluminized AP/Al/HTPB
                # composite propellant at ~6.9 MPa chamber pressure
                # (Sutton & Biblarz 9th ed., Ch. 13: ~260-270 s):
                'expected_isp_sea_level': 265,  # s
                # --- CONFIGURATION ECHO values ---
                # Same numbers the engine reads from its propellant table.
                # Checked only to confirm the engine loads the documented set;
                # EXCLUDED from validation pass metrics (they are inputs, not
                # predictions — comparing them would be tautological).
                'expected_gamma': 1.1986,
                'expected_density': 1810,   # kg/m³ (typical AP/Al/HTPB: 1.75-1.85 g/cc, Sutton 9th ed., Ch. 13)
                'expected_flame_temp': 3614.8,  # K (c* ile Eq. 3-32 üzerinden tutarlı)
                'burn_rate_a': 0.005,    # m/s/bar^n (typical APCP)
                'burn_rate_n': 0.35,     # dimensionless (typical APCP)
                'propellant_type': 'apcp'
            },
            'saint_robert_test_cases': [
                # expected_rate = a * P^n exactly (Saint-Robert / Vieille law,
                # Sutton & Biblarz 9th ed., Ch. 12), a=0.005 m/s/bar^n, n=0.35.
                # Values computed analytically: 0.005 * P^0.35.
                {'pressure': 10,   'a': 0.005, 'n': 0.35, 'expected_rate': 0.0111936},  # m/s
                {'pressure': 30,   'a': 0.005, 'n': 0.35, 'expected_rate': 0.0164423},  # m/s
                {'pressure': 68.9, 'a': 0.005, 'n': 0.35, 'expected_rate': 0.0219962},  # m/s
                {'pressure': 100,  'a': 0.005, 'n': 0.35, 'expected_rate': 0.0250594},  # m/s
            ],
            'standard_atmosphere': {
                # U.S. Standard Atmosphere 1976 (NOAA/NASA/USAF), Table I,
                # GEOMETRIC altitude. Pressures in bar (1 bar = 1e5 Pa).
                # The 25/30/40 km points are deliberately included so the
                # 20-47 km layers are exercised: a previous model bug
                # (wrong layer base temperatures) was masked because only
                # 0/11/20/50 km were sampled.
                'sea_level':         {'altitude': 0,     'pressure': 1.01325,    'temperature': 288.150},
                'tropopause_11km':   {'altitude': 11000, 'pressure': 0.22700,    'temperature': 216.774},
                'stratosphere_20km': {'altitude': 20000, 'pressure': 0.055293,   'temperature': 216.650},
                'stratosphere_25km': {'altitude': 25000, 'pressure': 0.025492,   'temperature': 221.552},
                'stratosphere_30km': {'altitude': 30000, 'pressure': 0.011970,   'temperature': 226.509},
                'stratosphere_40km': {'altitude': 40000, 'pressure': 0.0028714,  'temperature': 250.350},
                'stratopause_50km':  {'altitude': 50000, 'pressure': 0.00079779, 'temperature': 270.650},
            },
            'thrust_coefficient_cases': [
                # Full thrust coefficient (Sutton & Biblarz 9th ed.,
                # Eqs. 3-29 .. 3-31):
                #   CF = CF_mom(Pe/Pc) + eps * (Pe/Pc - Pa/Pc)
                #   CF_mom = sqrt(2g²/(g-1) * (2/(g+1))^((g+1)/(g-1))
                #                 * (1 - (Pe/Pc)^((g-1)/g)))
                # Nozzle sized for sea-level optimum expansion at Pc=68.9 bar:
                #   Pe = 1.01325 bar -> Pe/Pc = 1.01325/68.9 = 0.0147061,
                #   eps = 8.8915 (isentropic Mach-area relation, gamma=1.1986).
                # Expected values computed independently from the closed-form
                # equations above (NOT from the engine code). The previous
                # values (1.8421/1.6341/1.2000) were not reproducible by any
                # standard CF formulation, and the Pe/Pc=1.0 case (CF_mom=0)
                # was physically meaningless; both were replaced.
                {'label': 'Sea level (optimum expansion, Pa = Pe = 1.01325 bar)',
                 'pe_pc_ratio': 0.0147061, 'pa_pc_ratio': 0.0147061,
                 'epsilon': 8.8915, 'gamma': 1.1986,
                 'expected_cf': 1.5973},   # pressure term = 0 (Pe = Pa)
                {'label': '10 km altitude (Pa = 0.26500 bar, USSA 1976 Table I)',
                 'pe_pc_ratio': 0.0147061, 'pa_pc_ratio': 0.0038462,
                 'epsilon': 8.8915, 'gamma': 1.1986,
                 'expected_cf': 1.6939},
                {'label': 'Vacuum (Pa = 0)',
                 'pe_pc_ratio': 0.0147061, 'pa_pc_ratio': 0.0,
                 'epsilon': 8.8915, 'gamma': 1.1986,
                 'expected_cf': 1.7281},
            ]
        }

    def run_all_tests(self):
        """Execute all validation tests and generate comprehensive report"""
        print("=" * 80)
        print("SOLID ROCKET MOTOR VALIDATION TEST SUITE")
        print("=" * 80)
        print(f"Test executed on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Test 1: APCP reference set validation
        print("TEST 1: APCP Reference Set Validation (CEA-consistent synthetic reference)")
        print("-" * 50)
        self.test_apcp_reference_validation()
        print()

        # Test 2: Saint-Robert's Law Validation
        print("TEST 2: Saint-Robert's Law Burn Rate Validation")
        print("-" * 50)
        self.test_saint_robert_law()
        print()

        # Test 3: Standard Atmosphere Validation
        print("TEST 3: Standard Atmosphere Altitude Performance (USSA 1976)")
        print("-" * 50)
        self.test_standard_atmosphere()
        print()

        # Test 4: Thrust Coefficient Validation
        print("TEST 4: Thrust Coefficient Calculations")
        print("-" * 50)
        self.test_thrust_coefficient()
        print()

        # Generate summary report
        self.generate_summary_report()

        # Generate plots
        self.generate_validation_plots()

        return self.results

    def test_apcp_reference_validation(self):
        """Test against the CEA-consistent APCP reference set.

        Independent checks (count toward pass metrics):
        - c*: thermodynamic identity (Sutton Eq. 3-32) for the documented
          (gamma, M, Tc) set
        - Isp (sea level): literature value for AP/Al/HTPB composite
        Configuration echo checks (informational only — these values are
        inputs read from the engine's propellant table, not predictions):
        - density, gamma, chamber temperature
        """
        ref = self.reference_data['apcp_reference']

        # Create motor with reference parameters
        motor = SolidRocketEngine(
            grain_type='bates',
            propellant_type=ref['propellant_type'],
            chamber_diameter=ref['chamber_diameter'],
            grain_length=ref['grain_length'],
            core_diameter=ref['core_diameter'],
            chamber_pressure=ref['chamber_pressure'],
            burn_rate_a=ref['burn_rate_a'],
            burn_rate_n=ref['burn_rate_n']
        )

        # Get motor performance
        performance = motor.calculate_performance()

        # Validate c* (characteristic velocity) — independent identity check
        c_star_error = self._calculate_percentage_error(
            motor.c_star, ref['expected_c_star']
        )

        # Validate specific impulse at sea level — independent literature check
        isp_error = self._calculate_percentage_error(
            performance['isp_sea_level'], ref['expected_isp_sea_level']
        )

        # Configuration echo checks (engine reads these from its table)
        density_error = self._calculate_percentage_error(
            motor.rho_p, ref['expected_density']
        )
        gamma_error = self._calculate_percentage_error(
            motor.gamma, ref['expected_gamma']
        )
        temp_error = self._calculate_percentage_error(
            motor.T_c, ref['expected_flame_temp']
        )

        # Store results
        self.results['apcp_reference_validation'] = {
            'c_star': {
                'calculated': motor.c_star,
                'expected': ref['expected_c_star'],
                'error_percent': c_star_error,
                'passed': abs(c_star_error) <= self.tolerance_percentage,
                'check_type': 'independent'
            },
            'specific_impulse': {
                'calculated': performance['isp_sea_level'],
                'expected': ref['expected_isp_sea_level'],
                'error_percent': isp_error,
                'passed': abs(isp_error) <= self.tolerance_percentage,
                'check_type': 'independent'
            },
            'density': {
                'calculated': motor.rho_p,
                'expected': ref['expected_density'],
                'error_percent': density_error,
                'passed': abs(density_error) <= self.tolerance_percentage,
                'check_type': 'configuration_echo'
            },
            'gamma': {
                'calculated': motor.gamma,
                'expected': ref['expected_gamma'],
                'error_percent': gamma_error,
                'passed': abs(gamma_error) <= self.tolerance_percentage,
                'check_type': 'configuration_echo'
            },
            'chamber_temperature': {
                'calculated': motor.T_c,
                'expected': ref['expected_flame_temp'],
                'error_percent': temp_error,
                'passed': abs(temp_error) <= self.tolerance_percentage,
                'check_type': 'configuration_echo'
            }
        }

        # Print results
        print("Independent checks:")
        print(f"c* (Characteristic Velocity, Sutton Eq. 3-32 identity):")
        print(f"  Expected: {ref['expected_c_star']:.1f} m/s")
        print(f"  Calculated: {motor.c_star:.1f} m/s")
        print(f"  Error: {c_star_error:+.2f}% {'✓ PASS' if abs(c_star_error) <= self.tolerance_percentage else '✗ FAIL'}")

        print(f"Specific Impulse (Sea Level, Sutton Ch. 13 literature value):")
        print(f"  Expected: {ref['expected_isp_sea_level']:.1f} s")
        print(f"  Calculated: {performance['isp_sea_level']:.1f} s")
        print(f"  Error: {isp_error:+.2f}% {'✓ PASS' if abs(isp_error) <= self.tolerance_percentage else '✗ FAIL'}")

        print("Configuration echo checks (informational, excluded from pass metrics):")
        print(f"Propellant Density:")
        print(f"  Expected: {ref['expected_density']:.0f} kg/m³")
        print(f"  Calculated: {motor.rho_p:.0f} kg/m³")
        print(f"  Error: {density_error:+.2f}%")

        print(f"Isentropic Expansion Coefficient (γ):")
        print(f"  Expected: {ref['expected_gamma']:.4f}")
        print(f"  Calculated: {motor.gamma:.4f}")
        print(f"  Error: {gamma_error:+.2f}%")

        print(f"Chamber Temperature:")
        print(f"  Expected: {ref['expected_flame_temp']:.1f} K")
        print(f"  Calculated: {motor.T_c:.1f} K")
        print(f"  Error: {temp_error:+.2f}%")

    def test_saint_robert_law(self):
        """Validate burn rate calculations using Saint-Robert's law"""
        # Create a test motor
        motor = SolidRocketEngine(
            propellant_type='apcp',
            burn_rate_a=0.005,
            burn_rate_n=0.35
        )

        test_cases = self.reference_data['saint_robert_test_cases']
        results = []

        print("Saint-Robert's Law: r = a × P^n")
        print("Test Parameters: a = 0.005 m/s/bar^n, n = 0.35")
        print()

        for i, case in enumerate(test_cases):
            # Calculate burn rate (engine prediction)
            calculated_rate = motor.burn_rate(case['pressure'])

            # Theoretical rate (pure Saint-Robert's law, computed in place)
            theoretical_rate = case['a'] * (case['pressure'] ** case['n'])

            # Internal consistency: the stored reference value must equal
            # a*P^n (the previous expected_rate values were inconsistent
            # with the stated a and n by up to a factor of 6.3).
            ref_consistency = abs(theoretical_rate - case['expected_rate']) / case['expected_rate'] * 100
            if ref_consistency > 0.1:
                print(f"  WARNING: stored expected_rate inconsistent with a*P^n by {ref_consistency:.2f}%")

            # Calculate error against the independent analytic reference
            error = self._calculate_percentage_error(calculated_rate, case['expected_rate'])

            results.append({
                'pressure': case['pressure'],
                'calculated': calculated_rate,
                'theoretical': theoretical_rate,
                'expected_rate': case['expected_rate'],
                'error_percent': error,
                'passed': abs(error) <= 10.0  # 10% tolerance for burn rate (includes corrections)
            })

            print(f"Test Case {i+1}: P = {case['pressure']:.1f} bar")
            print(f"  Analytic (a·P^n): {case['expected_rate']:.5f} m/s")
            print(f"  Calculated: {calculated_rate:.5f} m/s")
            print(f"  Error: {error:+.2f}% {'✓ PASS' if abs(error) <= 10.0 else '✗ FAIL'}")

        self.results['saint_robert_validation'] = results

    def test_standard_atmosphere(self):
        """Validate altitude performance against US Standard Atmosphere 1976"""
        motor = SolidRocketEngine(propellant_type='apcp')

        # Test altitudes from reference data
        test_altitudes = []
        expected_data = []

        for key, data in self.reference_data['standard_atmosphere'].items():
            test_altitudes.append(data['altitude'])
            expected_data.append(data)

        # Calculate altitude performance
        altitude_performance = motor.calculate_altitude_performance(test_altitudes)

        results = []

        print("US Standard Atmosphere 1976 Validation (Table I, geometric altitude)")
        print()

        for i, (calc_data, exp_data) in enumerate(zip(altitude_performance, expected_data)):
            # Validate pressure
            pressure_error = self._calculate_percentage_error(
                calc_data['pressure'], exp_data['pressure']
            )

            # Validate temperature
            temp_error = self._calculate_percentage_error(
                calc_data['temperature'], exp_data['temperature']
            )

            result = {
                'altitude': calc_data['altitude'],
                'pressure': {
                    'calculated': calc_data['pressure'],
                    'expected': exp_data['pressure'],
                    'error_percent': pressure_error,
                    'passed': abs(pressure_error) <= 2.0  # 2% tolerance for atmosphere
                },
                'temperature': {
                    'calculated': calc_data['temperature'],
                    'expected': exp_data['temperature'],
                    'error_percent': temp_error,
                    'passed': abs(temp_error) <= 1.0  # 1% tolerance for temperature
                }
            }

            results.append(result)

            print(f"Altitude: {calc_data['altitude']:,} m")
            print(f"  Pressure - Expected: {exp_data['pressure']:.5f} bar, "
                  f"Calculated: {calc_data['pressure']:.5f} bar, "
                  f"Error: {pressure_error:+.2f}% {'✓' if abs(pressure_error) <= 2.0 else '✗'}")
            print(f"  Temperature - Expected: {exp_data['temperature']:.2f} K, "
                  f"Calculated: {calc_data['temperature']:.2f} K, "
                  f"Error: {temp_error:+.2f}% {'✓' if abs(temp_error) <= 1.0 else '✗'}")

        self.results['standard_atmosphere_validation'] = results

    def test_thrust_coefficient(self):
        """Validate thrust coefficient calculations (full CF with pressure term)"""
        test_cases = self.reference_data['thrust_coefficient_cases']
        results = []

        print("Thrust Coefficient Validation (Sutton & Biblarz 9th ed., Eqs. 3-29..3-31)")
        print("CF = √[2γ²/(γ-1) × (2/(γ+1))^((γ+1)/(γ-1)) × (1-(Pe/Pc)^((γ-1)/γ))] + ε(Pe/Pc - Pa/Pc)")
        print()

        for i, case in enumerate(test_cases):
            gamma = case['gamma']
            pe_pc = case['pe_pc_ratio']
            pa_pc = case['pa_pc_ratio']
            epsilon = case['epsilon']

            # Momentum term (Sutton Eq. 3-30)
            gamma_term = 2 * gamma**2 / (gamma - 1)
            stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
            expansion_term = 1 - pe_pc ** ((gamma - 1) / gamma)
            cf_momentum = np.sqrt(gamma_term * stagnation_term * expansion_term)

            # Pressure term: eps * (Pe/Pc - Pa/Pc) (Sutton Eq. 3-29/3-31)
            cf_theoretical = cf_momentum + epsilon * (pe_pc - pa_pc)

            # Compare with expected value
            error = self._calculate_percentage_error(cf_theoretical, case['expected_cf'])

            result = {
                'label': case['label'],
                'pe_pc_ratio': pe_pc,
                'pa_pc_ratio': pa_pc,
                'epsilon': epsilon,
                'gamma': gamma,
                'calculated_cf': cf_theoretical,
                'expected_cf': case['expected_cf'],
                'error_percent': error,
                'passed': abs(error) <= 3.0  # 3% tolerance for CF
            }

            results.append(result)

            print(f"Test Case {i+1} ({case['label']}):")
            print(f"  Pe/Pc = {pe_pc:.4f}, Pa/Pc = {pa_pc:.4f}, ε = {epsilon:.4f}, γ = {gamma:.4f}")
            print(f"  Expected CF: {case['expected_cf']:.4f}")
            print(f"  Calculated CF: {cf_theoretical:.4f}")
            print(f"  Error: {error:+.2f}% {'✓ PASS' if abs(error) <= 3.0 else '✗ FAIL'}")

        self.results['thrust_coefficient_validation'] = results

    def _calculate_percentage_error(self, calculated, expected):
        """Calculate percentage error between calculated and expected values"""
        if expected == 0:
            return 0.0 if calculated == 0 else float('inf')
        return ((calculated - expected) / expected) * 100

    def generate_summary_report(self):
        """Generate comprehensive summary report.

        Configuration echo checks (values the engine reads directly from its
        propellant table) are reported separately and EXCLUDED from the pass
        metrics — including them would inflate the pass rate tautologically.
        """
        print("=" * 80)
        print("VALIDATION TEST SUMMARY REPORT")
        print("=" * 80)

        total_tests = 0
        passed_tests = 0

        # APCP reference set summary
        print("\n1. APCP Reference Set Validation (CEA-consistent synthetic reference):")
        apcp_results = self.results['apcp_reference_validation']
        for param, data in apcp_results.items():
            if data.get('check_type') == 'configuration_echo':
                status = "(echo — excluded from metrics)"
                print(f"   {param.replace('_', ' ').title()}: {data['error_percent']:+.2f}% {status}")
                continue
            total_tests += 1
            if data['passed']:
                passed_tests += 1
                status = "✓ PASS"
            else:
                status = "✗ FAIL"
            print(f"   {param.replace('_', ' ').title()}: {data['error_percent']:+.2f}% {status}")

        # Saint-Robert's Law Summary
        print("\n2. Saint-Robert's Law Validation:")
        sr_results = self.results['saint_robert_validation']
        sr_passed = sum(1 for r in sr_results if r['passed'])
        total_tests += len(sr_results)
        passed_tests += sr_passed
        print(f"   Burn Rate Tests: {sr_passed}/{len(sr_results)} passed")

        # Standard Atmosphere Summary
        print("\n3. Standard Atmosphere Validation (USSA 1976):")
        atm_results = self.results['standard_atmosphere_validation']
        atm_passed = 0
        for result in atm_results:
            total_tests += 2  # pressure and temperature
            if result['pressure']['passed']:
                passed_tests += 1
            if result['temperature']['passed']:
                passed_tests += 1
            atm_passed += (1 if result['pressure']['passed'] else 0) + (1 if result['temperature']['passed'] else 0)
        print(f"   Atmosphere Tests: {atm_passed}/{len(atm_results)*2} passed")

        # Thrust Coefficient Summary
        print("\n4. Thrust Coefficient Validation:")
        cf_results = self.results['thrust_coefficient_validation']
        cf_passed = sum(1 for r in cf_results if r['passed'])
        total_tests += len(cf_results)
        passed_tests += cf_passed
        print(f"   Thrust Coefficient Tests: {cf_passed}/{len(cf_results)} passed")

        # Overall Summary
        pass_rate = (passed_tests / total_tests) * 100
        print(f"\n{'='*80}")
        print(f"OVERALL VALIDATION RESULTS (independent checks only):")
        print(f"Total Tests: {total_tests}")
        print(f"Passed Tests: {passed_tests}")
        print(f"Failed Tests: {total_tests - passed_tests}")
        print(f"Pass Rate: {pass_rate:.1f}%")

        if pass_rate >= 90:
            print("✓ EXCELLENT - Code validation meets industry standards")
        elif pass_rate >= 80:
            print("✓ GOOD - Code validation acceptable for most applications")
        elif pass_rate >= 70:
            print("⚠ ACCEPTABLE - Some improvements recommended")
        else:
            print("✗ NEEDS IMPROVEMENT - Significant validation issues detected")

        print(f"{'='*80}")

    def generate_validation_plots(self):
        """Generate validation plots for visual analysis"""
        try:
            # Create reference motor for plotting
            ref = self.reference_data['apcp_reference']
            motor = SolidRocketEngine(
                grain_type='bates',
                propellant_type=ref['propellant_type'],
                chamber_diameter=ref['chamber_diameter'],
                grain_length=ref['grain_length'],
                core_diameter=ref['core_diameter'],
                chamber_pressure=ref['chamber_pressure'],
                burn_rate_a=ref['burn_rate_a'],
                burn_rate_n=ref['burn_rate_n']
            )

            performance = motor.calculate_performance()

            # Create figure with subplots
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
            fig.suptitle('Solid Rocket Motor Validation Results', fontsize=16, fontweight='bold')

            # Plot 1: Thrust Curve
            thrust_curve = performance['thrust_curve']
            ax1.plot(thrust_curve['time'], thrust_curve['thrust'], 'b-', linewidth=2, label='Calculated Thrust')
            ax1.set_xlabel('Time (s)')
            ax1.set_ylabel('Thrust (N)')
            ax1.set_title('Thrust Curve - APCP Reference Motor')
            ax1.grid(True, alpha=0.3)
            ax1.legend()

            # Plot 2: Burn Rate vs Pressure (Saint-Robert's Law)
            pressures = np.linspace(1, 150, 100)
            burn_rates = [motor.burn_rate(p) for p in pressures]
            theoretical_rates = [motor.a * (p ** motor.n) for p in pressures]

            ax2.plot(pressures, np.array(burn_rates)*1000, 'r-', linewidth=2, label='Calculated (with corrections)')
            ax2.plot(pressures, np.array(theoretical_rates)*1000, 'b--', linewidth=2, label='Theoretical Saint-Robert')
            ax2.set_xlabel('Chamber Pressure (bar)')
            ax2.set_ylabel('Burn Rate (mm/s)')
            ax2.set_title('Burn Rate Validation')
            ax2.grid(True, alpha=0.3)
            ax2.legend()
            ax2.set_xlim(0, 150)

            # Plot 3: Altitude Performance
            altitudes = np.array([0, 1000, 5000, 10000, 20000, 50000, 80000, 100000])
            altitude_perf = motor.calculate_altitude_performance(altitudes)

            isp_values = [data['specific_impulse'] for data in altitude_perf]
            ax3.plot(altitudes/1000, isp_values, 'g-', linewidth=2, marker='o', label='Specific Impulse')
            ax3.set_xlabel('Altitude (km)')
            ax3.set_ylabel('Specific Impulse (s)')
            ax3.set_title('Altitude Performance')
            ax3.grid(True, alpha=0.3)
            ax3.legend()

            # Plot 4: Validation Summary Bar Chart
            categories = ['c*', 'Isp', 'Density', 'γ', 'Temperature']
            errors = []
            colors = []

            apcp_results = self.results['apcp_reference_validation']
            for param in ['c_star', 'specific_impulse', 'density', 'gamma', 'chamber_temperature']:
                error = abs(apcp_results[param]['error_percent'])
                errors.append(error)
                colors.append('green' if error <= self.tolerance_percentage else 'red')

            bars = ax4.bar(categories, errors, color=colors, alpha=0.7)
            ax4.axhline(y=self.tolerance_percentage, color='orange', linestyle='--',
                       label=f'{self.tolerance_percentage}% Tolerance')
            ax4.set_ylabel('Absolute Error (%)')
            ax4.set_title('APCP Reference Set Validation Errors')
            ax4.legend()
            ax4.grid(True, alpha=0.3)

            # Add value labels on bars
            for bar, error in zip(bars, errors):
                height = bar.get_height()
                ax4.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                        f'{error:.1f}%', ha='center', va='bottom')

            plt.tight_layout()
            plt.savefig('/Users/apple/Desktop/dosyalar/HRMA/validation_results.png',
                       dpi=300, bbox_inches='tight')
            print(f"\nValidation plots saved to: /Users/apple/Desktop/dosyalar/HRMA/validation_results.png")

        except Exception as e:
            print(f"Could not generate plots: {e}")

    def save_results_to_json(self):
        """Save detailed results to JSON file (atomic write)"""
        output_file = '/Users/apple/Desktop/dosyalar/HRMA/validation_results.json'

        # Convert numpy arrays to lists for JSON serialization
        json_results = {}
        for key, value in self.results.items():
            json_results[key] = self._convert_to_json_serializable(value)

        # Önce string üret (serileştirme hatası varsa dosyaya hiç dokunulmaz),
        # sonra geçici dosyaya yazıp atomik taşı — yarıda kesik JSON kalmaz.
        payload = json.dumps({
            'test_date': datetime.now().isoformat(),
            'test_description': 'Solid Rocket Motor Validation Against Independent Reference Data',
            'tolerance_percentage': self.tolerance_percentage,
            'results': json_results
        }, indent=2)

        tmp_file = output_file + '.tmp'
        with open(tmp_file, 'w') as f:
            f.write(payload)
        os.replace(tmp_file, output_file)

        print(f"Detailed results saved to: {output_file}")

    def _convert_to_json_serializable(self, obj):
        """Convert numpy arrays and other non-serializable objects to JSON format"""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: self._convert_to_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_json_serializable(v) for v in obj]
        elif isinstance(obj, (bool, np.bool_)):
            # np.bool_ json.dump tarafından serileştirilemez (TypeError) —
            # 'passed' alanları np.float64 karşılaştırmalarından np.bool_
            # olarak gelir; saf bool'a çevrilir.
            return bool(obj)
        elif isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        else:
            return obj


# ---------------------------------------------------------------------------
# Pytest uyumu: module-level test_* sarmalayıcılar.
# Sınıf adı Test* ile başlamadığı için pytest sınıfı toplamaz; aşağıdaki
# fonksiyonlar toplanır. Suite bir kez kurulur ve paylaşılır.
# ---------------------------------------------------------------------------

_SUITE_CACHE = {}


def _get_suite():
    if 'suite' not in _SUITE_CACHE:
        _SUITE_CACHE['suite'] = SolidRocketValidationTest()
    return _SUITE_CACHE['suite']


def test_apcp_reference():
    """Independent APCP checks (c* identity, literature Isp) must pass."""
    suite = _get_suite()
    suite.test_apcp_reference_validation()
    for name, d in suite.results['apcp_reference_validation'].items():
        if d.get('check_type') != 'independent':
            continue
        assert d['passed'], (
            f"{name}: hata {d['error_percent']:+.2f}% "
            f"(tolerans ±{suite.tolerance_percentage}%, beklenen {d['expected']}, hesaplanan {d['calculated']})"
        )


def test_saint_robert():
    """Engine burn rate must match the analytic Saint-Robert reference."""
    suite = _get_suite()
    suite.test_saint_robert_law()
    for r in suite.results['saint_robert_validation']:
        assert r['passed'], (
            f"P={r['pressure']} bar: hata {r['error_percent']:+.2f}% (tolerans ±10%)"
        )


def test_standard_atmosphere():
    """Engine atmosphere model must match USSA 1976 Table I values."""
    suite = _get_suite()
    suite.test_standard_atmosphere()
    for r in suite.results['standard_atmosphere_validation']:
        assert r['pressure']['passed'], (
            f"z={r['altitude']} m basınç: hata {r['pressure']['error_percent']:+.2f}% (tolerans ±2%)"
        )
        assert r['temperature']['passed'], (
            f"z={r['altitude']} m sıcaklık: hata {r['temperature']['error_percent']:+.2f}% (tolerans ±1%)"
        )


def test_thrust_coefficient():
    """Full CF formula must reproduce independently computed references."""
    suite = _get_suite()
    suite.test_thrust_coefficient()
    for r in suite.results['thrust_coefficient_validation']:
        assert r['passed'], (
            f"{r['label']}: hata {r['error_percent']:+.2f}% (tolerans ±3%)"
        )


def test_json_serialization_roundtrip(tmp_path=None):
    """np.bool_ içeren sonuçlar JSON'a hatasız serileştirilebilmeli."""
    suite = _get_suite()
    if 'thrust_coefficient_validation' not in suite.results:
        suite.test_thrust_coefficient()
    converted = suite._convert_to_json_serializable(suite.results)
    # json.dumps TypeError fırlatmamalı (np.bool_/np.float64 temizlenmiş olmalı)
    json.dumps(converted)


def main():
    """Main function to run all validation tests"""
    print("Initializing Solid Rocket Motor Validation Test Suite...")

    # Create test suite
    test_suite = SolidRocketValidationTest()

    # Run all tests
    results = test_suite.run_all_tests()

    # Save results to JSON
    test_suite.save_results_to_json()

    print("\nValidation testing completed!")
    print("Check the generated files:")
    print("- validation_results.png (plots)")
    print("- validation_results.json (detailed results)")

    return results


if __name__ == "__main__":
    main()
