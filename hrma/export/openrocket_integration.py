"""
OpenRocket Integration Module
Export motor data to OpenRocket .eng format and create flight simulation files
"""

import numpy as np
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime

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
        motor_name = motor_data.get('motor_name', 'UZAYTEK-HRM-001')
        total_impulse = motor_data.get('total_impulse', 10000)  # N·s
        burn_time = motor_data.get('burn_time', 10)  # s
        propellant_mass = motor_data.get('propellant_mass_total', 1.0)  # kg
        throat_diameter = motor_data.get('throat_diameter', 0.02) * 1000  # mm
        chamber_length = motor_data.get('chamber_length', 0.5) * 1000  # mm
        
        # Determine motor class
        motor_class = self._get_motor_class(total_impulse)
        
        # Generate thrust curve
        thrust_curve = self._generate_thrust_curve(motor_data)
        
        # Create motor designation
        motor_designation = f"{motor_class}{int(throat_diameter)}-{motor_name}"
        
        # Generate .eng file content
        eng_content = self._create_eng_file(
            motor_designation, throat_diameter, chamber_length,
            propellant_mass, total_impulse, thrust_curve, motor_data
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
        motor_name = motor_data.get('motor_name', 'UZAYTEK-HRM-001')
        total_impulse = motor_data.get('total_impulse', 0)
        motor_class = self._get_motor_class(total_impulse)
        
        report.append(f"Designation: {motor_class}{int(motor_data.get('throat_diameter', 0.02) * 1000)}-{motor_name}")
        report.append(f"Motor Class: {motor_class}")
        report.append(f"Total Impulse: {total_impulse:.0f} N·s")
        report.append(f"Average Thrust: {motor_data.get('thrust', 0):.0f} N")
        report.append(f"Burn Time: {motor_data.get('burn_time', 0):.1f} s")
        report.append(f"Specific Impulse: {motor_data.get('isp', 0):.1f} s")
        report.append("")
        
        # Physical dimensions
        report.append("PHYSICAL DIMENSIONS:")
        report.append("-" * 30)
        report.append(f"Throat Diameter: {motor_data.get('throat_diameter', 0) * 1000:.2f} mm")
        report.append(f"Exit Diameter: {motor_data.get('exit_diameter', 0) * 1000:.2f} mm")
        report.append(f"Chamber Diameter: {motor_data.get('chamber_diameter', 0) * 1000:.2f} mm")
        report.append(f"Chamber Length: {motor_data.get('chamber_length', 0) * 1000:.2f} mm")
        report.append(f"Total Mass: {motor_data.get('propellant_mass_total', 0):.2f} kg")
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
    
    def _generate_thrust_curve(self, motor_data: Dict) -> List[Tuple[float, float]]:
        """Generate thrust vs time curve"""
        
        burn_time = motor_data.get('burn_time', 10)
        avg_thrust = motor_data.get('thrust', 1000)
        
        # Realistic hybrid motor thrust curve
        time_points = np.linspace(0, burn_time, 100)
        thrust_points = []
        
        for t in time_points:
            # Hybrid motor characteristic: slight decrease over time due to port enlargement
            if t < 0.1:
                # Startup transient
                thrust = avg_thrust * (t / 0.1) * 0.8
            elif t > burn_time - 0.5:
                # Tail-off
                thrust = avg_thrust * (burn_time - t) / 0.5 * 0.3
            else:
                # Main burn phase with slight regression
                regression_factor = 1.0 - 0.15 * (t / burn_time)  # 15% decrease over burn
                thrust = avg_thrust * regression_factor
            
            thrust_points.append((t, max(0, thrust)))
        
        return thrust_points
    
    def _create_eng_file(self, designation: str, diameter: float, length: float,
                        prop_mass: float, total_impulse: float, 
                        thrust_curve: List[Tuple[float, float]], motor_data: Dict) -> str:
        """Create .eng file content"""
        
        lines = []
        
        # Header comment
        lines.append(f"; {designation}")
        lines.append(f"; UZAYTEK Hybrid Rocket Motor")
        lines.append(f"; Generated by UZAYTEK Analysis Software")
        lines.append(f"; {datetime.now().strftime('%Y-%m-%d')}")
        lines.append(";")
        
        # Motor line format: name diameter length delays prop_mass loaded_mass manufacturer
        loaded_mass = prop_mass + 0.5  # Add case mass estimate
        manufacturer = "UZAYTEK"
        delays = "0"  # No ejection delay for hybrid motors
        
        motor_line = f"{designation} {diameter:.1f} {length:.1f} {delays} {prop_mass:.3f} {loaded_mass:.3f} {manufacturer}"
        lines.append(motor_line)
        
        # Thrust curve data
        for time, thrust in thrust_curve:
            lines.append(f"{time:.3f} {thrust:.1f}")
        
        # End marker
        lines.append(";")
        
        return "\n".join(lines)
    
    def _calculate_flight_performance(self, motor_data: Dict, rocket_params: Dict) -> Dict:
        """Calculate estimated flight performance"""
        
        # Basic rocket equation calculations
        total_impulse = motor_data.get('total_impulse', 10000)
        prop_mass = motor_data.get('propellant_mass_total', 1.0)
        dry_mass = rocket_params.get('dry_mass', 5.0)
        
        # Mass ratio
        wet_mass = dry_mass + prop_mass
        mass_ratio = wet_mass / dry_mass
        
        # Ideal velocity (rocket equation)
        isp = motor_data.get('isp', 250)
        delta_v = isp * 9.81 * np.log(mass_ratio)
        
        # Estimated apogee (simple ballistic)
        # Assumes 85% vertical efficiency
        efficiency = 0.85
        apogee = (efficiency * delta_v)**2 / (2 * 9.81)
        
        # Maximum acceleration
        avg_thrust = motor_data.get('thrust', 1000)
        max_acceleration = avg_thrust / dry_mass  # At burnout
        
        # Time to apogee (approximate)
        time_to_apogee = efficiency * delta_v / 9.81
        
        return {
            'estimated_apogee': apogee,  # m
            'delta_v': delta_v,  # m/s
            'max_acceleration': max_acceleration,  # m/s²
            'time_to_apogee': time_to_apogee,  # s
            'mass_ratio': mass_ratio,
            'burnout_velocity': efficiency * delta_v  # m/s
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
        
        motor_name = motor_data.get('motor_name', 'UZAYTEK-HRM-001')
        total_impulse = motor_data.get('total_impulse', 10000)
        motor_class = self._get_motor_class(total_impulse)
        throat_diameter = motor_data.get('throat_diameter', 0.02) * 1000
        motor_designation = f"{motor_class}{int(throat_diameter)}-{motor_name}"
        
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
                    <length>{motor_data.get('chamber_length', 0.5)}</length>
                    <outerradius>{motor_data.get('chamber_diameter', 0.1)/2}</outerradius>
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
        
        motor_name = motor_data.get('motor_name', 'UZAYTEK-HRM-001')
        total_impulse = motor_data.get('total_impulse', 10000)
        motor_class = self._get_motor_class(total_impulse)
        throat_diameter = motor_data.get('throat_diameter', 0.02) * 1000
        motor_designation = f"{motor_class}{int(throat_diameter)}-{motor_name}"
        
        return {
            'designation': motor_designation,
            'motor_class': motor_class,
            'total_impulse': total_impulse,
            'average_thrust': motor_data.get('thrust', 0),
            'burn_time': motor_data.get('burn_time', 0),
            'specific_impulse': motor_data.get('isp', 0),
            'propellant_mass': motor_data.get('propellant_mass_total', 0),
            'throat_diameter': throat_diameter,
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
        
        # Calculate flight performance
        flight_performance = self._calculate_flight_performance(motor_data, rocket_params)
        
        # Generate trajectory points
        burn_time = motor_data.get('burn_time', 10)
        thrust_curve = self._generate_thrust_curve(motor_data)
        
        # Simplified trajectory calculation
        time_points = np.linspace(0, burn_time * 3, 200)  # Extend beyond burn time
        altitude_points = []
        velocity_points = []
        acceleration_points = []
        
        current_velocity = 0
        current_altitude = 0
        mass = rocket_params['dry_mass'] + motor_data.get('propellant_mass_total', 1.0)
        
        for i, t in enumerate(time_points):
            # Get thrust at current time
            thrust = 0
            for thrust_time, thrust_value in thrust_curve:
                if abs(thrust_time - t) < 0.01:
                    thrust = thrust_value
                    break
            
            # Calculate forces
            weight = mass * 9.81
            drag = 0.5 * 1.225 * rocket_params.get('drag_coefficient', 0.5) * \
                   np.pi * (rocket_params['diameter']/2)**2 * current_velocity**2
            
            net_force = thrust - weight - drag
            acceleration = net_force / mass if mass > 0 else -9.81
            
            # Update kinematics
            if i > 0:
                dt = time_points[i] - time_points[i-1]
                current_velocity += acceleration * dt
                current_altitude += current_velocity * dt
                
                # Mass consumption during burn
                if t <= burn_time and thrust > 0:
                    mass_flow_rate = motor_data.get('propellant_mass_total', 1.0) / burn_time
                    mass = max(rocket_params['dry_mass'], mass - mass_flow_rate * dt)
            
            # Stop if rocket hits ground
            if current_altitude < 0:
                current_altitude = 0
                current_velocity = 0
            
            altitude_points.append(max(0, current_altitude))
            velocity_points.append(current_velocity)
            acceleration_points.append(acceleration)
        
        return {
            'time_data': time_points.tolist(),
            'altitude_data': altitude_points,
            'velocity_data': velocity_points,
            'acceleration_data': acceleration_points,
            'thrust_curve': thrust_curve,
            'performance_summary': flight_performance,
            'max_altitude': max(altitude_points),
            'max_velocity': max(velocity_points),
            'max_acceleration': max(acceleration_points),
            'flight_time': time_points[-1],
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