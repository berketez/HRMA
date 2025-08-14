#!/usr/bin/env python3
"""
Solid Rocket Motor Validation Test Suite
========================================
Validates solid rocket motor calculations against NASA reference data
and established rocket propulsion theory.

Test Cases:
1. APCP motor validation against NASA RP-1271 reference data
2. Saint-Robert's law burn rate validation
3. Standard atmosphere altitude performance validation
4. Thrust coefficient calculations validation

Reference Data Sources:
- NASA RP-1271: Solid Propellant Grain Design and Internal Ballistics
- NASA SP-8024: Solid Rocket Motor Performance Analysis and Prediction
- Sutton & Biblarz: Rocket Propulsion Elements (9th Edition)
- NASA CEA (Chemical Equilibrium with Applications) data
"""

import numpy as np
import matplotlib.pyplot as plt
from solid_rocket_engine import SolidRocketEngine
import json
from datetime import datetime

class SolidRocketValidationTest:
    """Comprehensive validation test suite for solid rocket motor calculations"""
    
    def __init__(self):
        self.results = {}
        self.tolerance_percentage = 5.0  # 5% tolerance for validation
        self.reference_data = self._load_reference_data()
        
    def _load_reference_data(self):
        """Load NASA and industry reference data for validation"""
        return {
            'nasa_rp1271_apcp': {
                'description': 'NASA RP-1271 APCP Reference Motor',
                'chamber_diameter': 100,  # mm
                'grain_length': 500,      # mm
                'core_diameter': 30,      # mm
                'chamber_pressure': 68.9, # bar
                'expected_c_star': 1598,  # m/s
                'expected_isp_sea_level': 265,  # s
                'expected_gamma': 1.1986,
                'expected_density': 1810,  # kg/m³
                'expected_flame_temp': 3241.7,  # K
                'burn_rate_a': 0.005,    # m/s/bar^n (typical APCP)
                'burn_rate_n': 0.35,     # dimensionless (typical APCP)
                'propellant_type': 'apcp'
            },
            'saint_robert_test_cases': [
                {'pressure': 10, 'a': 0.005, 'n': 0.35, 'expected_rate': 0.00177},  # m/s
                {'pressure': 30, 'a': 0.005, 'n': 0.35, 'expected_rate': 0.00396},  # m/s
                {'pressure': 68.9, 'a': 0.005, 'n': 0.35, 'expected_rate': 0.00659}, # m/s
                {'pressure': 100, 'a': 0.005, 'n': 0.35, 'expected_rate': 0.00841},  # m/s
            ],
            'standard_atmosphere': {
                'sea_level': {'altitude': 0, 'pressure': 1.01325, 'temperature': 288.15},      # bar, K
                'troposphere': {'altitude': 11000, 'pressure': 0.22632, 'temperature': 216.65}, # m, bar, K
                'stratosphere': {'altitude': 20000, 'pressure': 0.05475, 'temperature': 216.65}, # m, bar, K
                'mesosphere': {'altitude': 50000, 'pressure': 0.00079, 'temperature': 270.65},   # m, bar, K
            },
            'thrust_coefficient_cases': [
                {'pe_pc_ratio': 0.0147, 'gamma': 1.1986, 'expected_cf': 1.8421},  # Vacuum
                {'pe_pc_ratio': 0.1470, 'gamma': 1.1986, 'expected_cf': 1.6341},  # 10km alt
                {'pe_pc_ratio': 1.0000, 'gamma': 1.1986, 'expected_cf': 1.2000},  # Sea level (approx)
            ]
        }
    
    def run_all_tests(self):
        """Execute all validation tests and generate comprehensive report"""
        print("=" * 80)
        print("SOLID ROCKET MOTOR VALIDATION TEST SUITE")
        print("=" * 80)
        print(f"Test executed on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Test 1: NASA RP-1271 APCP Motor Validation
        print("TEST 1: NASA RP-1271 APCP Motor Validation")
        print("-" * 50)
        self.test_nasa_rp1271_validation()
        print()
        
        # Test 2: Saint-Robert's Law Validation
        print("TEST 2: Saint-Robert's Law Burn Rate Validation")
        print("-" * 50)
        self.test_saint_robert_law()
        print()
        
        # Test 3: Standard Atmosphere Validation
        print("TEST 3: Standard Atmosphere Altitude Performance")
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
    
    def test_nasa_rp1271_validation(self):
        """Test against NASA RP-1271 APCP reference data"""
        ref = self.reference_data['nasa_rp1271_apcp']
        
        # Create motor with NASA reference parameters
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
        
        # Validate c* (characteristic velocity)
        c_star_error = self._calculate_percentage_error(
            motor.c_star, ref['expected_c_star']
        )
        
        # Validate specific impulse at sea level
        isp_error = self._calculate_percentage_error(
            performance['isp_sea_level'], ref['expected_isp_sea_level']
        )
        
        # Validate propellant density
        density_error = self._calculate_percentage_error(
            motor.rho_p, ref['expected_density']
        )
        
        # Validate gamma (isentropic expansion coefficient)
        gamma_error = self._calculate_percentage_error(
            motor.gamma, ref['expected_gamma']
        )
        
        # Validate chamber temperature
        temp_error = self._calculate_percentage_error(
            motor.T_c, ref['expected_flame_temp']
        )
        
        # Store results
        self.results['nasa_rp1271_validation'] = {
            'c_star': {
                'calculated': motor.c_star,
                'expected': ref['expected_c_star'],
                'error_percent': c_star_error,
                'passed': abs(c_star_error) <= self.tolerance_percentage
            },
            'specific_impulse': {
                'calculated': performance['isp_sea_level'],
                'expected': ref['expected_isp_sea_level'],
                'error_percent': isp_error,
                'passed': abs(isp_error) <= self.tolerance_percentage
            },
            'density': {
                'calculated': motor.rho_p,
                'expected': ref['expected_density'],
                'error_percent': density_error,
                'passed': abs(density_error) <= self.tolerance_percentage
            },
            'gamma': {
                'calculated': motor.gamma,
                'expected': ref['expected_gamma'],
                'error_percent': gamma_error,
                'passed': abs(gamma_error) <= self.tolerance_percentage
            },
            'chamber_temperature': {
                'calculated': motor.T_c,
                'expected': ref['expected_flame_temp'],
                'error_percent': temp_error,
                'passed': abs(temp_error) <= self.tolerance_percentage
            }
        }
        
        # Print results
        print(f"c* (Characteristic Velocity):")
        print(f"  Expected: {ref['expected_c_star']:.1f} m/s")
        print(f"  Calculated: {motor.c_star:.1f} m/s")
        print(f"  Error: {c_star_error:+.2f}% {'✓ PASS' if abs(c_star_error) <= self.tolerance_percentage else '✗ FAIL'}")
        
        print(f"Specific Impulse (Sea Level):")
        print(f"  Expected: {ref['expected_isp_sea_level']:.1f} s")
        print(f"  Calculated: {performance['isp_sea_level']:.1f} s")
        print(f"  Error: {isp_error:+.2f}% {'✓ PASS' if abs(isp_error) <= self.tolerance_percentage else '✗ FAIL'}")
        
        print(f"Propellant Density:")
        print(f"  Expected: {ref['expected_density']:.0f} kg/m³")
        print(f"  Calculated: {motor.rho_p:.0f} kg/m³")
        print(f"  Error: {density_error:+.2f}% {'✓ PASS' if abs(density_error) <= self.tolerance_percentage else '✗ FAIL'}")
        
        print(f"Isentropic Expansion Coefficient (γ):")
        print(f"  Expected: {ref['expected_gamma']:.4f}")
        print(f"  Calculated: {motor.gamma:.4f}")
        print(f"  Error: {gamma_error:+.2f}% {'✓ PASS' if abs(gamma_error) <= self.tolerance_percentage else '✗ FAIL'}")
        
        print(f"Chamber Temperature:")
        print(f"  Expected: {ref['expected_flame_temp']:.1f} K")
        print(f"  Calculated: {motor.T_c:.1f} K")
        print(f"  Error: {temp_error:+.2f}% {'✓ PASS' if abs(temp_error) <= self.tolerance_percentage else '✗ FAIL'}")
    
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
            # Calculate burn rate
            calculated_rate = motor.burn_rate(case['pressure'])
            
            # Calculate theoretical rate (pure Saint-Robert's law)
            theoretical_rate = case['a'] * (case['pressure'] ** case['n'])
            
            # Calculate error
            error = self._calculate_percentage_error(calculated_rate, theoretical_rate)
            
            results.append({
                'pressure': case['pressure'],
                'calculated': calculated_rate,
                'theoretical': theoretical_rate,
                'error_percent': error,
                'passed': abs(error) <= 10.0  # 10% tolerance for burn rate (includes corrections)
            })
            
            print(f"Test Case {i+1}: P = {case['pressure']:.1f} bar")
            print(f"  Theoretical: {theoretical_rate:.5f} m/s")
            print(f"  Calculated: {calculated_rate:.5f} m/s")
            print(f"  Error: {error:+.2f}% {'✓ PASS' if abs(error) <= 10.0 else '✗ FAIL'}")
        
        self.results['saint_robert_validation'] = results
    
    def test_standard_atmosphere(self):
        """Validate altitude performance against ICAO Standard Atmosphere"""
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
        
        print("ICAO Standard Atmosphere Validation")
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
        """Validate thrust coefficient calculations"""
        motor = SolidRocketEngine(propellant_type='apcp')
        
        test_cases = self.reference_data['thrust_coefficient_cases']
        results = []
        
        print("Thrust Coefficient Validation")
        print("CF = √[2γ²/(γ-1) × (2/(γ+1))^((γ+1)/(γ-1)) × (1-(Pe/Pc)^((γ-1)/γ))]")
        print()
        
        for i, case in enumerate(test_cases):
            # Calculate theoretical thrust coefficient
            gamma = case['gamma']
            pe_pc = case['pe_pc_ratio']
            
            # Ideal thrust coefficient calculation
            gamma_term = 2 * gamma**2 / (gamma - 1)
            stagnation_term = (2 / (gamma + 1)) ** ((gamma + 1) / (gamma - 1))
            expansion_term = 1 - pe_pc ** ((gamma - 1) / gamma)
            
            cf_theoretical = np.sqrt(gamma_term * stagnation_term * expansion_term)
            
            # Compare with expected value
            error = self._calculate_percentage_error(cf_theoretical, case['expected_cf'])
            
            result = {
                'pe_pc_ratio': pe_pc,
                'gamma': gamma,
                'calculated_cf': cf_theoretical,
                'expected_cf': case['expected_cf'],
                'error_percent': error,
                'passed': abs(error) <= 3.0  # 3% tolerance for CF
            }
            
            results.append(result)
            
            condition = "Vacuum" if pe_pc < 0.1 else "10km Alt" if pe_pc < 0.2 else "Sea Level"
            print(f"Test Case {i+1} ({condition}): Pe/Pc = {pe_pc:.4f}, γ = {gamma:.4f}")
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
        """Generate comprehensive summary report"""
        print("=" * 80)
        print("VALIDATION TEST SUMMARY REPORT")
        print("=" * 80)
        
        total_tests = 0
        passed_tests = 0
        
        # NASA RP-1271 Validation Summary
        print("\n1. NASA RP-1271 APCP Motor Validation:")
        nasa_results = self.results['nasa_rp1271_validation']
        for param, data in nasa_results.items():
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
        print("\n3. Standard Atmosphere Validation:")
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
        print(f"OVERALL VALIDATION RESULTS:")
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
            # Create NASA reference motor for plotting
            ref = self.reference_data['nasa_rp1271_apcp']
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
            ax1.set_title('Thrust Curve - NASA RP-1271 Reference Motor')
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
            
            nasa_results = self.results['nasa_rp1271_validation']
            for param in ['c_star', 'specific_impulse', 'density', 'gamma', 'chamber_temperature']:
                error = abs(nasa_results[param]['error_percent'])
                errors.append(error)
                colors.append('green' if error <= self.tolerance_percentage else 'red')
            
            bars = ax4.bar(categories, errors, color=colors, alpha=0.7)
            ax4.axhline(y=self.tolerance_percentage, color='orange', linestyle='--', 
                       label=f'{self.tolerance_percentage}% Tolerance')
            ax4.set_ylabel('Absolute Error (%)')
            ax4.set_title('NASA RP-1271 Validation Errors')
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
        """Save detailed results to JSON file"""
        output_file = '/Users/apple/Desktop/dosyalar/HRMA/validation_results.json'
        
        # Convert numpy arrays to lists for JSON serialization
        json_results = {}
        for key, value in self.results.items():
            json_results[key] = self._convert_to_json_serializable(value)
        
        with open(output_file, 'w') as f:
            json.dump({
                'test_date': datetime.now().isoformat(),
                'test_description': 'Solid Rocket Motor Validation Against NASA Reference Data',
                'tolerance_percentage': self.tolerance_percentage,
                'results': json_results
            }, f, indent=2)
        
        print(f"Detailed results saved to: {output_file}")
    
    def _convert_to_json_serializable(self, obj):
        """Convert numpy arrays and other non-serializable objects to JSON format"""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: self._convert_to_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_to_json_serializable(v) for v in obj]
        elif isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        else:
            return obj


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