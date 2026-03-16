"""
Safety Limits and Margin Checking System for Rocket Motors
Critical for preventing motor explosion and mission failure
"""

import numpy as np
from typing import Dict, List, Tuple, Optional


class SafetyLimits:
    """Safety limits with margin checking for rocket motors"""
    
    def __init__(self, 
                 pc_max: float = 300e5,  # Pa (300 bar max)
                 temp_wall_max: float = 1200,  # K
                 thrust_max: float = 10e6,  # N
                 safety_factor: float = 1.8,  # NASA recommended for liquid motors
                 throat_diameter_min: float = 0.001,  # m (1mm)
                 throat_diameter_max: float = 2.0):  # m (2000mm)
        """
        Initialize safety limits with margins
        
        Args:
            pc_max: Maximum chamber pressure (Pa)
            temp_wall_max: Maximum wall temperature (K)  
            thrust_max: Maximum thrust (N)
            safety_factor: Safety factor applied to all limits
            throat_diameter_min/max: Throat diameter sanity bounds (m)
        """
        self.pc_limit = pc_max / safety_factor
        self.temp_limit = temp_wall_max / safety_factor
        self.thrust_limit = thrust_max / safety_factor
        self.sf = safety_factor
        
        self.throat_dia_min = throat_diameter_min
        self.throat_dia_max = throat_diameter_max
        
        self.violations = []  # Track all violations
        
    def check_chamber_pressure(self, pc: float, motor_name: str = "Motor") -> bool:
        """Check chamber pressure against limits"""
        if pc > self.pc_limit:
            violation = {
                'parameter': 'Chamber Pressure',
                'value': pc / 1e5,  # Convert to bar for readability
                'limit': self.pc_limit / 1e5,  # bar
                'unit': 'bar',
                'motor': motor_name,
                'severity': 'CRITICAL',
                'risk': 'Motor explosion - chamber rupture'
            }
            self.violations.append(violation)
            return False
        return True
    
    def check_wall_temperature(self, temp: float, motor_name: str = "Motor") -> bool:
        """Check wall temperature against limits"""
        if temp > self.temp_limit:
            violation = {
                'parameter': 'Wall Temperature',
                'value': temp,
                'limit': self.temp_limit,
                'unit': 'K',
                'motor': motor_name,
                'severity': 'CRITICAL',
                'risk': 'Motor burnthrough - structural failure'
            }
            self.violations.append(violation)
            return False
        return True
    
    def check_thrust(self, thrust: float, motor_name: str = "Motor") -> bool:
        """Check thrust against limits"""
        if thrust > self.thrust_limit:
            violation = {
                'parameter': 'Thrust',
                'value': thrust / 1000,  # kN
                'limit': self.thrust_limit / 1000,  # kN
                'unit': 'kN', 
                'motor': motor_name,
                'severity': 'HIGH',
                'risk': 'Structural overload - vehicle failure'
            }
            self.violations.append(violation)
            return False
        return True
    
    def check_throat_diameter(self, throat_dia: float, motor_name: str = "Motor") -> bool:
        """Check throat diameter for sanity bounds"""
        throat_mm = throat_dia * 1000  # Convert to mm
        
        if throat_dia < self.throat_dia_min:
            violation = {
                'parameter': 'Throat Diameter (too small)',
                'value': throat_mm,
                'limit': self.throat_dia_min * 1000,
                'unit': 'mm',
                'motor': motor_name,
                'severity': 'CRITICAL',
                'risk': 'Excessive pressure - motor explosion'
            }
            self.violations.append(violation)
            return False
            
        if throat_dia > self.throat_dia_max:
            violation = {
                'parameter': 'Throat Diameter (too large)',
                'value': throat_mm,  
                'limit': self.throat_dia_max * 1000,
                'unit': 'mm',
                'motor': motor_name,
                'severity': 'HIGH',
                'risk': 'Calculation error - performance loss'
            }
            self.violations.append(violation)
            return False
            
        return True
    
    def check_mass_flow_rate(self, mdot: float, thrust: float, 
                           expected_isp: float = 300, tolerance: float = 0.3,
                           motor_name: str = "Motor") -> bool:
        """Check mass flow rate against expected value"""
        g0 = 9.80665
        expected_mdot = thrust / (expected_isp * g0)
        error = abs(mdot - expected_mdot) / expected_mdot
        
        if error > tolerance:
            violation = {
                'parameter': 'Mass Flow Rate',
                'value': mdot,
                'limit': expected_mdot,
                'unit': 'kg/s',
                'motor': motor_name,
                'severity': 'MEDIUM',
                'risk': f'Flow calculation error - {error*100:.1f}% deviation',
                'error_percent': error * 100
            }
            self.violations.append(violation)
            return False
        return True
    
    def comprehensive_check(self, motor_params: Dict, motor_name: str = "Motor") -> Dict:
        """Run all safety checks on motor parameters"""
        results = {
            'safe': True,
            'violations': [],
            'summary': {
                'critical': 0,
                'high': 0, 
                'medium': 0
            }
        }
        
        # Clear previous violations for this motor
        self.violations = [v for v in self.violations if v['motor'] != motor_name]
        
        # Run checks
        checks = [
            ('chamber_pressure', self.check_chamber_pressure),
            ('wall_temperature', self.check_wall_temperature),
            ('thrust', self.check_thrust),
            ('throat_diameter', self.check_throat_diameter)
        ]
        
        for param_name, check_func in checks:
            if param_name in motor_params:
                safe = check_func(motor_params[param_name], motor_name)
                if not safe:
                    results['safe'] = False
        
        # Mass flow rate check (needs multiple parameters)
        if all(p in motor_params for p in ['mass_flow_rate', 'thrust']):
            safe = self.check_mass_flow_rate(
                motor_params['mass_flow_rate'],
                motor_params['thrust'], 
                motor_params.get('expected_isp', 300),
                motor_name=motor_name
            )
            if not safe:
                results['safe'] = False
        
        # Get violations for this motor
        motor_violations = [v for v in self.violations if v['motor'] == motor_name]
        results['violations'] = motor_violations
        
        # Count by severity
        for violation in motor_violations:
            severity = violation['severity'].lower()
            if severity in results['summary']:
                results['summary'][severity] += 1
        
        return results
    
    def generate_safety_report(self) -> str:
        """Generate human-readable safety report"""
        if not self.violations:
            return "SAFETY STATUS: ALL CHECKS PASSED - MOTOR SAFE FOR OPERATION"
        
        report = ["SAFETY VIOLATION REPORT", "=" * 50]
        
        critical_violations = [v for v in self.violations if v['severity'] == 'CRITICAL']
        if critical_violations:
            report.append("\nCRITICAL VIOLATIONS (IMMEDIATE DANGER):")
            for v in critical_violations:
                report.append(f"  {v['motor']}: {v['parameter']}")
                report.append(f"    Value: {v['value']:.2f} {v['unit']}")
                report.append(f"    Limit: {v['limit']:.2f} {v['unit']}")
                report.append(f"    Risk: {v['risk']}")
                report.append("")
        
        high_violations = [v for v in self.violations if v['severity'] == 'HIGH']  
        if high_violations:
            report.append("HIGH PRIORITY VIOLATIONS:")
            for v in high_violations:
                report.append(f"  {v['motor']}: {v['parameter']}")
                report.append(f"    Value: {v['value']:.2f} {v['unit']}")
                report.append(f"    Limit: {v['limit']:.2f} {v['unit']}")
                report.append(f"    Risk: {v['risk']}")
                report.append("")
        
        medium_violations = [v for v in self.violations if v['severity'] == 'MEDIUM']
        if medium_violations:
            report.append("MEDIUM PRIORITY VIOLATIONS:")
            for v in medium_violations:
                report.append(f"  {v['motor']}: {v['parameter']}")
                report.append(f"    Value: {v['value']:.2f} {v['unit']}")
                if 'error_percent' in v:
                    report.append(f"    Error: {v['error_percent']:.1f}%")
                report.append(f"    Risk: {v['risk']}")
                report.append("")
        
        if critical_violations:
            report.append("RECOMMENDATION: DO NOT OPERATE - CRITICAL SAFETY RISK")
        elif high_violations:
            report.append("RECOMMENDATION: REVIEW DESIGN BEFORE OPERATION")
        else:
            report.append("RECOMMENDATION: MONITOR DURING OPERATION")
        
        return "\n".join(report)
    
    def clear_violations(self):
        """Clear all recorded violations"""
        self.violations = []


class MotorValidator:
    """High-level motor validation with known reference data"""
    
    def __init__(self):
        self.safety_limits = SafetyLimits()
        
        # Reference motor data for validation
        self.reference_motors = {
            'RS-25': {
                'thrust_vac': 2279000,  # N
                'thrust_sl': 1860000,   # N
                'isp_vac': 452,         # s
                'isp_sl': 366,          # s
                'chamber_pressure': 204e5,  # Pa
                'throat_diameter': 0.240,   # m
                'mass_flow_rate_sl': 563,   # kg/s
                'propellant': 'LOX/LH2'
            },
            'F-1': {
                'thrust_sl': 6770000,      # N
                'isp_sl': 263,             # s
                'chamber_pressure': 70e5,   # Pa
                'throat_diameter': 0.630,   # m
                'mass_flow_rate_sl': 2578,  # kg/s
                'propellant': 'LOX/RP-1'
            }
        }
    
    def validate_against_reference(self, calculated_params: Dict, 
                                 reference_motor: str) -> Dict:
        """Validate calculated parameters against known reference motor"""
        if reference_motor not in self.reference_motors:
            return {'status': 'error', 'message': 'Unknown reference motor'}
        
        ref = self.reference_motors[reference_motor]
        results = {'status': 'success', 'comparisons': [], 'overall_error': 0}
        
        # Compare key parameters
        comparisons = [
            ('thrust', 'thrust_sl', 'N'),
            ('chamber_pressure', 'chamber_pressure', 'Pa'),
            ('throat_diameter', 'throat_diameter', 'm'),
            ('mass_flow_rate', 'mass_flow_rate_sl', 'kg/s')
        ]
        
        total_error = 0
        valid_comparisons = 0
        
        for calc_key, ref_key, unit in comparisons:
            if calc_key in calculated_params and ref_key in ref:
                calc_val = calculated_params[calc_key]
                ref_val = ref[ref_key]
                error_pct = abs(calc_val - ref_val) / ref_val * 100
                
                comparison = {
                    'parameter': calc_key,
                    'calculated': calc_val,
                    'reference': ref_val,
                    'unit': unit,
                    'error_percent': error_pct,
                    'status': 'PASS' if error_pct < 25 else 'FAIL'
                }
                results['comparisons'].append(comparison)
                
                total_error += error_pct
                valid_comparisons += 1
        
        if valid_comparisons > 0:
            results['overall_error'] = total_error / valid_comparisons
            results['validation_status'] = 'PASS' if results['overall_error'] < 20 else 'FAIL'
        
        return results