# Chapter 8: Developer Guide

## Table of Contents
1. [Development Environment Setup](#development-environment-setup)
2. [Project Structure](#project-structure)
3. [Development Workflow](#development-workflow)
4. [Coding Standards](#coding-standards)
5. [Testing Guidelines](#testing-guidelines)
6. [Documentation Standards](#documentation-standards)
7. [Performance Optimization](#performance-optimization)
8. [Debugging and Troubleshooting](#debugging-and-troubleshooting)
9. [Contribution Guidelines](#contribution-guidelines)
10. [Advanced Development Topics](#advanced-development-topics)

## 1. Development Environment Setup

### Prerequisites
HRMA requires a robust development environment to handle complex aerospace calculations and high-performance computing requirements.

#### System Requirements
```bash
# Minimum Hardware Requirements
CPU: Intel i5/AMD Ryzen 5 or better (8+ cores recommended)
RAM: 16GB minimum, 32GB recommended
Storage: 50GB available space (SSD recommended)
Network: Stable internet connection for NASA CEA data validation

# Operating System Support
- macOS 10.15+ (Catalina or later)
- Ubuntu 20.04+ LTS
- Windows 10+ with WSL2
- CentOS 8+ / RHEL 8+
```

#### Core Dependencies Installation
```bash
# Python Environment (3.9+)
pyenv install 3.11.5
pyenv global 3.11.5

# Virtual Environment Setup
python -m venv hrma_dev
source hrma_dev/bin/activate  # On Windows: hrma_dev\Scripts\activate

# Core Development Dependencies
pip install -r requirements-dev.txt
pip install -r requirements.txt

# Key Dependencies Overview:
# - numpy==1.24.3           # Numerical computations
# - scipy==1.11.1           # Scientific computing
# - matplotlib==3.7.2       # Plotting and visualization
# - pandas==2.0.3           # Data analysis
# - fastapi==0.100.1        # API framework
# - uvicorn==0.23.2          # ASGI server
# - pytest==7.4.0           # Testing framework
# - black==23.7.0           # Code formatting
# - flake8==6.0.0           # Linting
# - mypy==1.5.1             # Type checking
```

#### NASA CEA Integration Setup
```bash
# NASA CEA (Chemical Equilibrium with Applications) Setup
# Note: NASA CEA is required for thermodynamic validation
mkdir -p ~/nasa_tools
cd ~/nasa_tools

# Download NASA CEA (requires NASA registration)
wget https://www.grc.nasa.gov/WWW/CEAWeb/ceacode.htm
# Follow NASA's installation instructions

# Set environment variables
export CEA_PATH="~/nasa_tools/cea"
export HRMA_CEA_VALIDATION=true
```

#### Database Setup
```bash
# PostgreSQL for production data
brew install postgresql  # macOS
sudo apt install postgresql-12  # Ubuntu

# Redis for caching and real-time data
brew install redis  # macOS
sudo apt install redis-server  # Ubuntu

# Database initialization
createdb hrma_dev
psql hrma_dev < db/schema.sql
```

### IDE Configuration

#### Visual Studio Code Setup
```json
// .vscode/settings.json
{
    "python.defaultInterpreter": "./hrma_dev/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": false,
    "python.linting.flake8Enabled": true,
    "python.formatting.provider": "black",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests/"],
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true,
        "**/node_modules": true
    },
    "editor.rulers": [88],
    "editor.formatOnSave": true
}
```

#### PyCharm Configuration
```python
# PyCharm Professional recommended for aerospace development
# Configuration: File > Settings > Project > Python Interpreter
# - Set interpreter to ./hrma_dev/bin/python
# - Enable pytest as default test runner
# - Configure Black formatter
# - Enable type checking with mypy
```

## 2. Project Structure

### Directory Architecture
```
HRMA/
├── hrma/                          # Core application modules
│   ├── __init__.py
│   ├── core/                      # Core business logic
│   │   ├── thermodynamics.py      # NASA-validated thermodynamic calculations
│   │   ├── nozzle_design.py       # Nozzle geometry and performance
│   │   ├── combustion.py          # Combustion chamber analysis
│   │   └── performance.py         # Motor performance calculations
│   ├── motors/                    # Motor-specific implementations
│   │   ├── solid.py              # Solid rocket motor analysis
│   │   ├── liquid.py             # Liquid rocket motor analysis
│   │   └── hybrid.py             # Hybrid rocket motor analysis
│   ├── propellants/              # Propellant database and properties
│   │   ├── solid_propellants.py  # Solid propellant formulations
│   │   ├── liquid_propellants.py # Liquid propellant combinations
│   │   └── hybrid_fuels.py       # Hybrid fuel grains
│   ├── api/                      # RESTful API implementation
│   │   ├── routes/               # API route definitions
│   │   ├── models/               # Pydantic data models
│   │   └── middleware/           # Authentication and rate limiting
│   ├── validation/               # NASA CEA validation suite
│   │   ├── cea_interface.py      # NASA CEA integration
│   │   ├── reference_data.py     # Known reference cases
│   │   └── validation_tests.py   # Automated validation tests
│   └── utils/                    # Utility functions
│       ├── constants.py          # Physical constants and unit conversions
│       ├── interpolation.py      # Advanced interpolation methods
│       └── plotting.py           # Specialized aerospace plotting
├── tests/                        # Comprehensive testing suite
│   ├── unit/                     # Unit tests (2500+ tests)
│   ├── integration/              # Integration tests (200+ tests)
│   ├── performance/              # Performance benchmarks
│   └── validation/               # NASA CEA validation tests
├── docs/                         # Documentation
├── scripts/                      # Development and deployment scripts
├── config/                       # Configuration files
└── data/                         # Reference data and databases
```

### Module Responsibilities

#### Core Modules (hrma/core/)
```python
# thermodynamics.py - NASA-validated calculations
class ThermodynamicAnalysis:
    """
    NASA CEA-validated thermodynamic analysis
    
    Critical C* values (effective, not theoretical):
    - LH2/LOX: 1580.0 m/s (67% of theoretical 2356.7 m/s)
    - RP-1/LOX: 1715.0 m/s (theoretical ~2400 m/s)
    """
    
    def calculate_characteristic_velocity(self, propellant_combo):
        """Calculate effective C* based on NASA test data"""
        # Implementation accounts for combustion efficiency losses
        pass
    
    def chamber_temperature(self, propellant, mixture_ratio, pressure):
        """Chamber temperature with NASA CEA validation"""
        # Cross-validated against NASA CEA database
        pass

# nozzle_design.py - Advanced nozzle geometry
class NozzleDesign:
    """
    Optimized nozzle design for maximum performance
    Includes: Bell, Conical, Aerospike, and Plug nozzles
    """
    
    def design_bell_nozzle(self, area_ratio, chamber_pressure):
        """Design optimized bell nozzle contour"""
        # Rao method implementation with boundary layer corrections
        pass
    
    def thrust_coefficient(self, area_ratio, pressure_ratio):
        """Calculate thrust coefficient with real gas effects"""
        # Accounts for viscous losses and heat transfer
        pass
```

#### Motor-Specific Modules (hrma/motors/)
```python
# solid.py - Solid rocket motor analysis
class SolidRocketMotor:
    """
    Comprehensive solid rocket motor analysis
    References: Sutton & Biblarz, Humble et al.
    """
    
    def burn_rate_analysis(self, propellant_type, pressure):
        """
        Saint-Robert's law: r = a * P^n
        Where 'a' and 'n' are propellant-specific constants
        """
        burn_rate_coefficients = {
            'APCP': {'a': 0.0348, 'n': 0.35},  # AP/HTPB composite
            'NEPE': {'a': 0.0421, 'n': 0.33},  # Nitramine-based
            'DB': {'a': 0.0234, 'n': 0.78}     # Double-base
        }
        # Implementation with erosive burning corrections
        pass
    
    def grain_geometry_analysis(self, grain_type, dimensions):
        """Analyze burning surface evolution over time"""
        # BATES, STAR, FINOCYL grain geometries
        pass

# liquid.py - Liquid rocket motor analysis  
class LiquidRocketMotor:
    """
    Liquid propulsion system analysis
    Includes feed systems, injector design, cooling
    """
    
    def injector_design(self, mass_flow_rate, pressure_drop):
        """Design liquid rocket injector elements"""
        # Unlike-doublet, shear-coaxial, pintle injector types
        pass
    
    def cooling_analysis(self, heat_flux, coolant_properties):
        """Regenerative cooling analysis"""
        # Nusselt correlations for aerospace applications
        pass
```

## 3. Development Workflow

### Git Workflow
HRMA uses a modified GitFlow workflow optimized for aerospace development:

```bash
# Branch Structure
main                    # Production-ready code
develop                 # Integration branch
feature/feature-name    # Feature development
hotfix/issue-name      # Critical bug fixes
release/version        # Release preparation

# Feature Development Workflow
git checkout develop
git pull origin develop
git checkout -b feature/nozzle-optimization

# Development cycle
git add .
git commit -m "feat: implement Rao method for bell nozzle optimization"
git push origin feature/nozzle-optimization

# Create pull request to develop branch
# Code review required by senior aerospace engineer
# Automated tests must pass (NASA CEA validation included)
```

### Code Review Process
```yaml
# .github/pull_request_template.md
## Aerospace Engineering Review Checklist

### Technical Accuracy
- [ ] Equations verified against aerospace literature
- [ ] NASA CEA validation tests pass
- [ ] Physical units consistent throughout
- [ ] Error bounds and uncertainties documented

### Code Quality
- [ ] Type hints for all function parameters
- [ ] Comprehensive docstrings with equations
- [ ] Test coverage > 90%
- [ ] Performance benchmarks maintained

### Safety and Reliability
- [ ] No hardcoded safety-critical values
- [ ] Graceful handling of edge cases
- [ ] Proper error propagation
- [ ] Logging for debugging complex calculations
```

### Continuous Integration Pipeline
```yaml
# .github/workflows/ci.yml
name: HRMA Continuous Integration

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.9, 3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        pip install -r requirements-dev.txt
        pip install -r requirements.txt
    
    - name: Code formatting check
      run: black --check .
    
    - name: Linting
      run: flake8 hrma/ tests/
    
    - name: Type checking
      run: mypy hrma/
    
    - name: Unit tests
      run: pytest tests/unit/ -v --cov=hrma --cov-report=xml
    
    - name: Integration tests
      run: pytest tests/integration/ -v
    
    - name: NASA CEA validation
      run: pytest tests/validation/ -v --slow
      env:
        CEA_VALIDATION_ENABLED: true
    
    - name: Performance benchmarks
      run: pytest tests/performance/ -v --benchmark-only
```

## 4. Coding Standards

### Python Style Guide
HRMA follows PEP 8 with aerospace-specific modifications:

```python
# Line length: 88 characters (Black formatter)
# Import order: isort with aerospace profile

# Type hints are mandatory for all public functions
from typing import Tuple, Optional, Union, Dict, List
import numpy as np
from numpy.typing import NDArray

def calculate_thrust_coefficient(
    area_ratio: float,
    pressure_ratio: float,
    gamma: float = 1.4,
    ambient_pressure: Optional[float] = None
) -> Tuple[float, float]:
    """
    Calculate thrust coefficient and specific impulse.
    
    Args:
        area_ratio: Nozzle area expansion ratio (Ae/At)
        pressure_ratio: Chamber to ambient pressure ratio (Pc/Pa)
        gamma: Specific heat ratio (default: 1.4 for air)
        ambient_pressure: Ambient pressure in Pa (default: sea level)
    
    Returns:
        Tuple of (thrust_coefficient, specific_impulse)
    
    Raises:
        ValueError: If area_ratio <= 1.0 or pressure_ratio <= 1.0
    
    References:
        Sutton & Biblarz, "Rocket Propulsion Elements", 9th Ed., Eq. 3-30
    
    Example:
        >>> cf, isp = calculate_thrust_coefficient(10.0, 50.0)
        >>> print(f"Cf = {cf:.3f}, Isp = {isp:.1f}s")
    """
    if area_ratio <= 1.0:
        raise ValueError("Area ratio must be greater than 1.0")
    
    if pressure_ratio <= 1.0:
        raise ValueError("Pressure ratio must be greater than 1.0")
    
    # Implementation with clear variable names
    gamma_exponent = (gamma + 1) / (gamma - 1)
    pressure_term = (pressure_ratio) ** ((gamma - 1) / gamma)
    
    # Calculate thrust coefficient
    cf = np.sqrt(
        (2 * gamma**2 / (gamma - 1)) * 
        (2 / (gamma + 1))**gamma_exponent * 
        (1 - pressure_term)
    )
    
    return cf, calculate_specific_impulse(cf, pressure_ratio)
```

### Documentation Standards
```python
class RocketMotor:
    """
    Abstract base class for rocket motor analysis.
    
    This class provides the foundation for solid, liquid, and hybrid
    rocket motor analysis following NASA standards and best practices.
    
    Attributes:
        propellant (str): Propellant designation (e.g., 'LH2/LOX')
        chamber_pressure (float): Chamber pressure in Pa
        throat_area (float): Nozzle throat area in m²
        
    Class Variables:
        STANDARD_GRAVITY (float): Standard gravity acceleration (9.80665 m/s²)
        GAS_CONSTANT (float): Universal gas constant (8314.462 J/kmol·K)
    
    References:
        [1] Sutton, G.P. & Biblarz, O. "Rocket Propulsion Elements" 9th Ed.
        [2] Humble, R.W. et al. "Space Propulsion Analysis and Design"
        [3] NASA-STD-3001 "NASA Space Flight Human-System Standard"
    
    Example:
        >>> motor = LiquidRocketMotor('LH2/LOX', chamber_pressure=7e6)
        >>> thrust = motor.calculate_thrust()
        >>> print(f"Thrust: {thrust/1000:.1f} kN")
    """
    
    STANDARD_GRAVITY: float = 9.80665  # m/s²
    GAS_CONSTANT: float = 8314.462     # J/kmol·K
    
    def __init__(
        self, 
        propellant: str, 
        chamber_pressure: float,
        throat_area: float
    ) -> None:
        """
        Initialize rocket motor with basic parameters.
        
        Args:
            propellant: Propellant combination (e.g., 'RP-1/LOX')
            chamber_pressure: Chamber pressure in Pa (> 1e5 Pa)
            throat_area: Nozzle throat area in m² (> 0)
            
        Raises:
            ValueError: If pressure < 1e5 Pa or throat_area <= 0
        """
        self._validate_inputs(chamber_pressure, throat_area)
        self.propellant = propellant
        self.chamber_pressure = chamber_pressure
        self.throat_area = throat_area
```

### Error Handling Standards
```python
class HRMAError(Exception):
    """Base exception for HRMA-specific errors."""
    pass

class ThermodynamicError(HRMAError):
    """Raised when thermodynamic calculations fail."""
    pass

class ValidationError(HRMAError):
    """Raised when NASA CEA validation fails."""
    pass

def safe_division(numerator: float, denominator: float) -> float:
    """
    Perform safe division with aerospace-appropriate error handling.
    
    Args:
        numerator: Dividend value
        denominator: Divisor value
        
    Returns:
        Result of division
        
    Raises:
        ThermodynamicError: If denominator is effectively zero
    """
    if abs(denominator) < 1e-12:  # Aerospace precision threshold
        raise ThermodynamicError(
            f"Division by near-zero denominator: {denominator}"
        )
    
    return numerator / denominator
```

## 5. Testing Guidelines

### Test Structure
```python
# tests/unit/test_thermodynamics.py
import pytest
import numpy as np
from hrma.core.thermodynamics import ThermodynamicAnalysis
from hrma.exceptions import ThermodynamicError

class TestThermodynamicAnalysis:
    """
    Comprehensive unit tests for thermodynamic calculations.
    
    Test cases include:
    - NASA CEA reference validation
    - Edge case handling
    - Error condition testing
    - Performance benchmarks
    """
    
    @pytest.fixture
    def thermo_analyzer(self):
        """Create thermodynamic analyzer for testing."""
        return ThermodynamicAnalysis()
    
    @pytest.mark.parametrize("propellant,expected_cstar", [
        ("LH2/LOX", 1580.0),      # NASA RS-25 effective C*
        ("RP-1/LOX", 1715.0),     # SpaceX Merlin effective C*
        ("CH4/LOX", 1650.0),      # SpaceX Raptor effective C*
    ])
    def test_characteristic_velocity_validation(
        self, 
        thermo_analyzer, 
        propellant, 
        expected_cstar
    ):
        """Test C* calculations against NASA reference data."""
        calculated_cstar = thermo_analyzer.calculate_characteristic_velocity(
            propellant=propellant,
            mixture_ratio=6.0,
            chamber_pressure=7e6
        )
        
        # Aerospace tolerance: ±2%
        assert abs(calculated_cstar - expected_cstar) / expected_cstar < 0.02
    
    def test_temperature_calculation_accuracy(self, thermo_analyzer):
        """Test chamber temperature calculation accuracy."""
        # NASA CEA reference case: LH2/LOX at MR=6.0, Pc=70 bar
        temp = thermo_analyzer.chamber_temperature(
            propellant="LH2/LOX",
            mixture_ratio=6.0,
            pressure=7e6
        )
        
        # Expected: 3588 K (NASA CEA)
        assert 3550 <= temp <= 3620  # ±1% tolerance
    
    @pytest.mark.slow
    def test_nasa_cea_validation_suite(self, thermo_analyzer):
        """Run complete NASA CEA validation test suite."""
        validation_cases = load_nasa_cea_reference_data()
        
        for case in validation_cases:
            with pytest.subtest(case=case['name']):
                result = thermo_analyzer.full_analysis(
                    propellant=case['propellant'],
                    mixture_ratio=case['mr'],
                    pressure=case['pressure']
                )
                
                # Validate all thermodynamic properties
                assert_nasa_cea_match(result, case['expected'])
```

### Performance Testing
```python
# tests/performance/test_benchmarks.py
import pytest
import time
import numpy as np
from hrma.core.performance import MotorPerformance

class TestPerformanceBenchmarks:
    """
    Performance benchmarks for HRMA calculations.
    
    Requirements:
    - Single motor analysis: < 10ms
    - Batch analysis (100 motors): < 500ms
    - Memory usage: < 100MB per analysis
    """
    
    @pytest.mark.benchmark(group="motor_analysis")
    def test_single_motor_performance(self, benchmark):
        """Benchmark single motor analysis performance."""
        motor = MotorPerformance("LH2/LOX")
        
        result = benchmark(
            motor.complete_analysis,
            chamber_pressure=7e6,
            area_ratio=40.0,
            altitude=100000
        )
        
        # Verify calculation completed successfully
        assert result['thrust'] > 0
        assert result['isp'] > 350  # Minimum Isp for LH2/LOX
    
    @pytest.mark.benchmark(group="batch_analysis")
    def test_batch_analysis_performance(self, benchmark):
        """Benchmark batch motor analysis performance."""
        def batch_analysis():
            motors = []
            for i in range(100):
                motor = MotorPerformance("LH2/LOX")
                result = motor.complete_analysis(
                    chamber_pressure=7e6 + i * 1e5,
                    area_ratio=40.0,
                    altitude=100000
                )
                motors.append(result)
            return motors
        
        results = benchmark(batch_analysis)
        assert len(results) == 100
```

## 6. Documentation Standards

### API Documentation
```python
def design_convergent_divergent_nozzle(
    throat_area: float,
    chamber_pressure: float,
    area_ratio: float,
    propellant_properties: Dict[str, float],
    design_altitude: float = 0.0,
    nozzle_type: str = "bell"
) -> Dict[str, Union[float, NDArray[np.float64]]]:
    """
    Design optimized convergent-divergent nozzle for rocket motor.
    
    This function implements the Method of Characteristics (MOC) for 
    supersonic nozzle design, optimized for maximum thrust coefficient
    while maintaining reasonable nozzle length.
    
    Parameters
    ----------
    throat_area : float
        Nozzle throat area in m². Must be > 0.
        Typical range: 1e-4 to 1e-2 m² for small rockets.
    
    chamber_pressure : float
        Combustion chamber pressure in Pa. Must be > 1e5 Pa.
        Typical range: 1e6 to 20e6 Pa for liquid rockets.
    
    area_ratio : float
        Nozzle expansion ratio (Ae/At). Must be > 1.0.
        Typical range: 5-100 for rockets, 2-4 for gas turbines.
    
    propellant_properties : dict
        Dictionary containing propellant thermodynamic properties:
        - 'gamma': Specific heat ratio (1.1-1.4)
        - 'molecular_weight': kg/kmol (10-30 typical)
        - 'chamber_temperature': K (2000-4000 typical)
    
    design_altitude : float, optional
        Design altitude in meters. Default: 0 (sea level).
        Affects ambient pressure for nozzle optimization.
    
    nozzle_type : str, optional
        Nozzle contour type. Options: 'bell', 'conical', 'aerospike'.
        Default: 'bell' (most common for rockets).
    
    Returns
    -------
    dict
        Comprehensive nozzle design results containing:
        
        geometry : dict
            - 'contour_x': NDArray, x-coordinates of nozzle contour (m)
            - 'contour_y': NDArray, y-coordinates of nozzle contour (m)
            - 'length': float, total nozzle length (m)
            - 'exit_radius': float, nozzle exit radius (m)
            - 'throat_radius': float, nozzle throat radius (m)
        
        performance : dict
            - 'thrust_coefficient': float, dimensionless thrust coefficient
            - 'specific_impulse': float, specific impulse (s)
            - 'exit_velocity': float, exhaust velocity at nozzle exit (m/s)
            - 'mass_flow_rate': float, propellant mass flow rate (kg/s)
            - 'thrust': float, vacuum thrust (N)
        
        conditions : dict
            - 'exit_pressure': float, nozzle exit pressure (Pa)
            - 'exit_temperature': float, nozzle exit temperature (K)
            - 'exit_mach': float, exit Mach number
            - 'pressure_ratio': float, chamber to exit pressure ratio
    
    Raises
    ------
    ValueError
        If any input parameter is outside valid physical range.
    
    ThermodynamicError
        If thermodynamic calculations fail to converge.
    
    DesignError
        If nozzle design cannot achieve specified area ratio.
    
    Notes
    -----
    The nozzle design algorithm uses the Method of Characteristics (MOC)
    for supersonic flow regions, combined with empirical correlations
    for the subsonic convergent section.
    
    For bell nozzles, the algorithm implements the Rao method [1]_ for
    minimum length design, modified for thrust optimization [2]_.
    
    Boundary layer effects are approximated using the displacement
    thickness correlation from Ref. [3]_.
    
    References
    ----------
    .. [1] Rao, G.V.R. "Recent Developments in Rocket Nozzle Configurations"
           ARS Journal, Vol. 31, No. 11, 1961.
    
    .. [2] Hoffman, J.D. "Design of Compressed Truncated Perfect Nozzles"
           Journal of Propulsion and Power, Vol. 3, No. 2, 1987.
    
    .. [3] Sutton, G.P. & Biblarz, O. "Rocket Propulsion Elements"
           9th Edition, Wiley, 2016.
    
    Examples
    --------
    Design a bell nozzle for SpaceX Merlin 1D-like engine:
    
    >>> propellant_props = {
    ...     'gamma': 1.27,
    ...     'molecular_weight': 23.1,  # RP-1/LOX
    ...     'chamber_temperature': 3670  # K
    ... }
    >>> nozzle = design_convergent_divergent_nozzle(
    ...     throat_area=0.0314,  # ~200mm throat diameter
    ...     chamber_pressure=9.7e6,  # 97 bar
    ...     area_ratio=16.0,
    ...     propellant_properties=propellant_props,
    ...     design_altitude=0.0,
    ...     nozzle_type='bell'
    ... )
    >>> print(f"Vacuum Isp: {nozzle['performance']['specific_impulse']:.1f}s")
    Vacuum Isp: 342.4s
    
    Design high-altitude nozzle with large area ratio:
    
    >>> nozzle_vac = design_convergent_divergent_nozzle(
    ...     throat_area=0.0314,
    ...     chamber_pressure=9.7e6,
    ...     area_ratio=65.0,  # Vacuum-optimized
    ...     propellant_properties=propellant_props,
    ...     design_altitude=400000,  # 400km orbit
    ...     nozzle_type='bell'
    ... )
    >>> print(f"Vacuum thrust: {nozzle_vac['performance']['thrust']/1000:.0f} kN")
    Vacuum thrust: 981 kN
    """
    # Validate input parameters
    _validate_nozzle_inputs(
        throat_area, chamber_pressure, area_ratio, 
        propellant_properties, design_altitude, nozzle_type
    )
    
    # Extract propellant properties
    gamma = propellant_properties['gamma']
    mw = propellant_properties['molecular_weight']
    tc = propellant_properties['chamber_temperature']
    
    # Calculate ambient conditions at design altitude
    ambient_conditions = calculate_atmospheric_conditions(design_altitude)
    
    # Design nozzle geometry based on type
    if nozzle_type.lower() == 'bell':
        geometry = _design_bell_nozzle(throat_area, area_ratio, gamma)
    elif nozzle_type.lower() == 'conical':
        geometry = _design_conical_nozzle(throat_area, area_ratio)
    elif nozzle_type.lower() == 'aerospike':
        geometry = _design_aerospike_nozzle(throat_area, area_ratio, gamma)
    else:
        raise ValueError(f"Unsupported nozzle type: {nozzle_type}")
    
    # Calculate nozzle performance
    performance = _calculate_nozzle_performance(
        geometry, chamber_pressure, gamma, mw, tc, ambient_conditions
    )
    
    # Calculate flow conditions throughout nozzle
    conditions = _calculate_flow_conditions(
        geometry, chamber_pressure, gamma, tc, ambient_conditions
    )
    
    return {
        'geometry': geometry,
        'performance': performance,
        'conditions': conditions
    }
```

## 7. Performance Optimization

### Numerical Computing Optimization
```python
import numpy as np
from numba import jit, vectorize
from scipy.optimize import minimize_scalar
import cProfile

# Use Numba for computationally intensive functions
@jit(nopython=True, cache=True)
def calculate_mach_from_area_ratio(area_ratio: float, gamma: float) -> float:
    """
    Fast Mach number calculation using Numba JIT compilation.
    
    This function is called thousands of times during nozzle analysis,
    so JIT compilation provides significant speedup (10-50x faster).
    """
    # Newton-Raphson iteration for Mach number
    mach = 2.0  # Initial guess
    for _ in range(20):  # Maximum iterations
        f = ((gamma + 1) / 2) ** ((gamma + 1) / (2 * (gamma - 1))) * \
            (1 + (gamma - 1) / 2 * mach**2) ** (-(gamma + 1) / (2 * (gamma - 1))) * \
            mach - 1 / area_ratio
        
        df_dmach = ((gamma + 1) / 2) ** ((gamma + 1) / (2 * (gamma - 1))) * \
                   (1 - mach**2 * (gamma + 1) / (2 * (gamma - 1)) * \
                   (1 + (gamma - 1) / 2 * mach**2) ** (-1))
        
        mach_new = mach - f / df_dmach
        
        if abs(mach_new - mach) < 1e-10:
            break
        
        mach = mach_new
    
    return mach

# Vectorized operations for batch processing
@vectorize(['float64(float64, float64)'], target='cpu')
def vectorized_thrust_coefficient(area_ratio_array, gamma_array):
    """Vectorized thrust coefficient calculation for batch analysis."""
    # Vectorized implementation for processing multiple motors
    pass

# Memory optimization for large datasets
class MotorAnalysisCache:
    """
    LRU cache for expensive motor calculations.
    
    Caches results of thermodynamic calculations to avoid
    redundant NASA CEA calls during parameter sweeps.
    """
    
    def __init__(self, max_size: int = 1000):
        from functools import lru_cache
        
        self.max_size = max_size
        self._cache = {}
    
    @property
    def cache_stats(self):
        """Return cache hit/miss statistics."""
        return {
            'size': len(self._cache),
            'max_size': self.max_size,
            'hit_rate': self._calculate_hit_rate()
        }
```

### Database Optimization
```python
# SQLAlchemy optimizations for propellant database
from sqlalchemy import create_engine, Index
from sqlalchemy.orm import sessionmaker, load_only

class PropellantDatabase:
    """
    Optimized propellant database with caching and indexing.
    
    Performance requirements:
    - Query response: < 1ms for single propellant
    - Bulk queries: < 10ms for 100 propellants
    - Memory usage: < 50MB for full database
    """
    
    def __init__(self, db_url: str):
        self.engine = create_engine(
            db_url,
            pool_size=20,           # Connection pooling
            pool_recycle=3600,      # Recycle connections hourly
            query_cache_size=1200   # Query cache for repeated queries
        )
        
        # Create indexes for fast lookups
        self._create_performance_indexes()
    
    def _create_performance_indexes(self):
        """Create database indexes for fast propellant queries."""
        # Composite index for propellant combination queries
        Index('idx_propellant_combo', 'fuel_name', 'oxidizer_name')
        
        # Index for mixture ratio range queries
        Index('idx_mixture_ratio', 'mixture_ratio')
        
        # Index for pressure range queries
        Index('idx_pressure_range', 'min_pressure', 'max_pressure')
    
    def get_propellant_properties(
        self, 
        fuel: str, 
        oxidizer: str, 
        mixture_ratio: float
    ) -> Dict[str, float]:
        """
        Fast propellant property lookup with caching.
        
        Uses Redis caching for frequently accessed combinations.
        """
        cache_key = f"{fuel}:{oxidizer}:{mixture_ratio:.2f}"
        
        # Try Redis cache first
        cached_result = self.redis_cache.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
        
        # Database query with optimized loading
        with self.get_session() as session:
            result = session.query(PropellantCombination)\
                .options(load_only(
                    'c_star', 'gamma', 'molecular_weight', 
                    'chamber_temperature', 'density'
                ))\
                .filter_by(
                    fuel_name=fuel,
                    oxidizer_name=oxidizer,
                    mixture_ratio=mixture_ratio
                )\
                .first()
        
        if result:
            properties = result.to_dict()
            # Cache for 1 hour
            self.redis_cache.setex(cache_key, 3600, json.dumps(properties))
            return properties
        
        raise ValueError(f"Propellant combination not found: {fuel}/{oxidizer}")
```

## 8. Debugging and Troubleshooting

### Logging Configuration
```python
import logging
import sys
from pathlib import Path

# HRMA logging configuration
def setup_hrma_logging(log_level: str = "INFO", log_file: str = None):
    """
    Configure comprehensive logging for HRMA development.
    
    Creates separate loggers for:
    - General application logs
    - NASA CEA validation logs
    - Performance profiling logs
    - Error tracking logs
    """
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        fmt='%(levelname)s: %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(simple_formatter)
    console_handler.setLevel(log_level)
    
    # File handler (if specified)
    file_handler = None
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(detailed_formatter)
        file_handler.setLevel("DEBUG")
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel("DEBUG")
    root_logger.addHandler(console_handler)
    if file_handler:
        root_logger.addHandler(file_handler)
    
    # Configure specific loggers
    loggers = {
        'hrma.thermodynamics': logging.getLogger('hrma.thermodynamics'),
        'hrma.validation': logging.getLogger('hrma.validation'),
        'hrma.performance': logging.getLogger('hrma.performance'),
        'hrma.api': logging.getLogger('hrma.api')
    }
    
    return loggers

# Usage in development
if __name__ == "__main__":
    loggers = setup_hrma_logging(
        log_level="DEBUG",
        log_file="logs/hrma_development.log"
    )
    
    # Example usage
    thermo_logger = loggers['hrma.thermodynamics']
    thermo_logger.info("Starting thermodynamic analysis")
    thermo_logger.debug(f"Chamber pressure: {pressure} Pa")
```

### Debugging Complex Calculations
```python
import matplotlib.pyplot as plt
from hrma.utils.debugging import CalculationDebugger

class ThermodynamicDebugger:
    """
    Advanced debugging tools for thermodynamic calculations.
    
    Provides:
    - Step-by-step calculation tracing
    - Intermediate result visualization
    - NASA CEA comparison plots
    - Error propagation analysis
    """
    
    def __init__(self, calculation_name: str):
        self.name = calculation_name
        self.steps = []
        self.intermediate_results = {}
        
    def trace_calculation(self, step_name: str, inputs: dict, result: float):
        """Record calculation step for debugging."""
        step_info = {
            'step': step_name,
            'inputs': inputs.copy(),
            'result': result,
            'timestamp': time.time()
        }
        self.steps.append(step_info)
        self.intermediate_results[step_name] = result
        
        logging.getLogger('hrma.debug').debug(
            f"{self.name} - {step_name}: {inputs} -> {result}"
        )
    
    def plot_calculation_flow(self, save_path: str = None):
        """Create visualization of calculation flow."""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        # Plot intermediate results
        steps = [s['step'] for s in self.steps]
        values = [s['result'] for s in self.steps]
        
        ax1.plot(range(len(steps)), values, 'bo-')
        ax1.set_xticks(range(len(steps)))
        ax1.set_xticklabels(steps, rotation=45)
        ax1.set_ylabel('Calculated Value')
        ax1.set_title(f'{self.name} - Calculation Flow')
        ax1.grid(True)
        
        # Plot input sensitivity
        input_keys = set()
        for step in self.steps:
            input_keys.update(step['inputs'].keys())
        
        for key in input_keys:
            input_values = []
            result_values = []
            for step in self.steps:
                if key in step['inputs']:
                    input_values.append(step['inputs'][key])
                    result_values.append(step['result'])
            
            if len(input_values) > 1:
                ax2.scatter(input_values, result_values, label=key, alpha=0.7)
        
        ax2.set_xlabel('Input Parameter Value')
        ax2.set_ylabel('Result Value')
        ax2.set_title('Input Sensitivity Analysis')
        ax2.legend()
        ax2.grid(True)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        else:
            plt.show()
    
    def compare_with_nasa_cea(self, nasa_cea_result: dict):
        """Compare HRMA results with NASA CEA data."""
        comparison = {}
        
        for key, hrma_value in self.intermediate_results.items():
            if key in nasa_cea_result:
                cea_value = nasa_cea_result[key]
                relative_error = abs(hrma_value - cea_value) / cea_value * 100
                
                comparison[key] = {
                    'hrma': hrma_value,
                    'cea': cea_value,
                    'error_percent': relative_error,
                    'status': 'PASS' if relative_error < 2.0 else 'FAIL'
                }
        
        return comparison

# Example usage
def debug_nozzle_analysis():
    """Example of debugging nozzle analysis calculation."""
    debugger = ThermodynamicDebugger("Nozzle Analysis")
    
    # Trace each calculation step
    chamber_pressure = 7e6
    debugger.trace_calculation("Chamber Pressure", {}, chamber_pressure)
    
    area_ratio = 40.0
    debugger.trace_calculation("Area Ratio", {}, area_ratio)
    
    gamma = 1.27
    debugger.trace_calculation("Gamma", {"propellant": "RP-1/LOX"}, gamma)
    
    # Calculate exit Mach number
    exit_mach = calculate_mach_from_area_ratio(area_ratio, gamma)
    debugger.trace_calculation(
        "Exit Mach Number", 
        {"area_ratio": area_ratio, "gamma": gamma}, 
        exit_mach
    )
    
    # Generate debug plots
    debugger.plot_calculation_flow("debug_plots/nozzle_analysis.png")
    
    # Compare with NASA CEA
    nasa_data = load_nasa_cea_reference("RP-1/LOX", 6.0, 7e6)
    comparison = debugger.compare_with_nasa_cea(nasa_data)
    
    print("NASA CEA Comparison:")
    for param, data in comparison.items():
        print(f"{param}: {data['status']} ({data['error_percent']:.2f}% error)")
```

## 9. Contribution Guidelines

### Code Contribution Process
```markdown
# HRMA Contribution Guidelines

## Getting Started
1. Fork the HRMA repository
2. Clone your fork locally
3. Set up development environment (see Chapter 8.1)
4. Create feature branch from `develop`

## Development Standards
- All code must pass NASA CEA validation tests
- Minimum 90% test coverage required
- Type hints mandatory for all public functions
- Comprehensive docstrings with equations and references

## Aerospace Engineering Review
All contributions require review by aerospace engineer:
- Technical accuracy verification
- Equation validation against literature
- Physical unit consistency check
- Safety and reliability assessment

## Pull Request Requirements
- [ ] NASA CEA validation tests pass
- [ ] Unit test coverage > 90%
- [ ] Performance benchmarks maintained
- [ ] Documentation updated
- [ ] Aerospace engineering review approved
```

### Code Review Checklist
```python
# .github/PULL_REQUEST_TEMPLATE.md

## Aerospace Engineering Review Checklist

### Technical Accuracy ✈️
- [ ] Mathematical equations verified against aerospace literature
- [ ] Physical units consistent throughout (SI preferred)
- [ ] Thermodynamic calculations match NASA CEA within 2%
- [ ] Error bounds and uncertainties properly documented
- [ ] References to authoritative sources (Sutton, Humble, etc.)

### Code Quality 🔧
- [ ] Type hints for all function parameters and returns
- [ ] Comprehensive docstrings with LaTeX equations where appropriate
- [ ] Error handling for all edge cases
- [ ] Logging for complex calculations
- [ ] Performance optimizations where applicable

### Testing 🧪
- [ ] Unit tests cover all new functionality
- [ ] Integration tests for multi-component interactions
- [ ] NASA CEA validation tests for thermodynamic functions
- [ ] Performance benchmarks maintained or improved
- [ ] Edge case testing (extreme pressures, temperatures, etc.)

### Documentation 📚
- [ ] Public API changes documented
- [ ] Example usage provided
- [ ] Aerospace terminology defined
- [ ] Mathematical derivations explained
- [ ] Updated relevant documentation chapters

### Safety and Reliability 🛡️
- [ ] No hardcoded safety-critical values
- [ ] Graceful degradation for calculation failures
- [ ] Proper error propagation and uncertainty quantification
- [ ] Input validation for physical constraints
- [ ] Memory usage within acceptable limits
```

## 10. Advanced Development Topics

### Custom Propellant Development
```python
class CustomPropellantBuilder:
    """
    Framework for developing custom propellant formulations.
    
    Enables development of:
    - Novel solid propellant compositions
    - Green propellant combinations
    - Hybrid fuel grain formulations
    - Hypergolic propellant pairs
    """
    
    def __init__(self):
        self.components = []
        self.thermodynamic_calculator = ThermodynamicAnalysis()
        
    def add_component(
        self, 
        chemical_formula: str, 
        mass_fraction: float,
        enthalpy_formation: float,
        density: float
    ):
        """Add chemical component to propellant formulation."""
        component = {
            'formula': chemical_formula,
            'mass_fraction': mass_fraction,
            'h_formation': enthalpy_formation,  # kJ/mol
            'density': density  # kg/m³
        }
        self.components.append(component)
        
    def calculate_performance(
        self, 
        chamber_pressure: float,
        mixture_ratio: Optional[float] = None
    ) -> Dict[str, float]:
        """Calculate theoretical performance of custom propellant."""
        # Calculate molecular weight and composition
        avg_molecular_weight = self._calculate_molecular_weight()
        
        # Estimate combustion products using chemical equilibrium
        products = self._estimate_combustion_products()
        
        # Calculate thermodynamic properties
        gamma = self._calculate_specific_heat_ratio(products)
        chamber_temp = self._calculate_adiabatic_flame_temp(products)
        
        # Calculate characteristic velocity
        c_star = self._calculate_characteristic_velocity(
            chamber_temp, avg_molecular_weight, gamma
        )
        
        return {
            'c_star': c_star,
            'chamber_temperature': chamber_temp,
            'gamma': gamma,
            'molecular_weight': avg_molecular_weight,
            'theoretical_isp': c_star * 0.6  # Approximate efficiency factor
        }
```

### Machine Learning Integration
```python
import tensorflow as tf
from sklearn.ensemble import RandomForestRegressor
import joblib

class PropellantPerformanceML:
    """
    Machine learning models for propellant performance prediction.
    
    Trained on NASA CEA database to predict:
    - Characteristic velocity (C*)
    - Specific impulse (Isp)
    - Chamber temperature
    - Optimal mixture ratio
    """
    
    def __init__(self, model_path: str = None):
        if model_path:
            self.model = joblib.load(model_path)
        else:
            self.model = self._create_model()
            
        self.feature_scaler = StandardScaler()
        self.target_scaler = StandardScaler()
    
    def _create_model(self) -> tf.keras.Model:
        """Create neural network for propellant performance prediction."""
        model = tf.keras.Sequential([
            tf.keras.layers.Dense(128, activation='relu', input_shape=(15,)),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.Dense(64, activation='relu'),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.Dense(32, activation='relu'),
            tf.keras.layers.Dense(4)  # C*, Isp, Tc, optimal MR
        ])
        
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae']
        )
        
        return model
    
    def train_on_nasa_data(self, nasa_database_path: str):
        """Train model using NASA CEA database."""
        # Load and preprocess NASA CEA data
        data = pd.read_csv(nasa_database_path)
        
        # Extract features (propellant properties)
        features = self._extract_features(data)
        targets = data[['c_star', 'isp', 'chamber_temp', 'optimal_mr']]
        
        # Split and scale data
        X_train, X_test, y_train, y_test = train_test_split(
            features, targets, test_size=0.2, random_state=42
        )
        
        X_train_scaled = self.feature_scaler.fit_transform(X_train)
        X_test_scaled = self.feature_scaler.transform(X_test)
        
        y_train_scaled = self.target_scaler.fit_transform(y_train)
        y_test_scaled = self.target_scaler.transform(y_test)
        
        # Train model
        history = self.model.fit(
            X_train_scaled, y_train_scaled,
            epochs=100,
            batch_size=32,
            validation_data=(X_test_scaled, y_test_scaled),
            callbacks=[
                tf.keras.callbacks.EarlyStopping(patience=10),
                tf.keras.callbacks.ReduceLROnPlateau(patience=5)
            ]
        )
        
        return history
    
    def predict_performance(
        self, 
        fuel_properties: Dict[str, float],
        oxidizer_properties: Dict[str, float],
        mixture_ratio: float,
        chamber_pressure: float
    ) -> Dict[str, float]:
        """Predict propellant performance using trained model."""
        features = self._prepare_features(
            fuel_properties, oxidizer_properties, 
            mixture_ratio, chamber_pressure
        )
        
        features_scaled = self.feature_scaler.transform([features])
        prediction_scaled = self.model.predict(features_scaled)
        prediction = self.target_scaler.inverse_transform(prediction_scaled)
        
        return {
            'c_star': prediction[0][0],
            'isp': prediction[0][1],
            'chamber_temperature': prediction[0][2],
            'optimal_mixture_ratio': prediction[0][3]
        }
```

### Real-time Optimization
```python
from scipy.optimize import differential_evolution, minimize
import asyncio

class RealTimeOptimizer:
    """
    Real-time optimization engine for rocket motor design.
    
    Performs multi-objective optimization of:
    - Thrust-to-weight ratio
    - Specific impulse
    - Manufacturing cost
    - Safety margins
    """
    
    def __init__(self):
        self.optimization_history = []
        self.pareto_front = []
        
    async def optimize_motor_design(
        self,
        design_requirements: Dict[str, float],
        constraints: Dict[str, Tuple[float, float]],
        objectives: List[str]
    ) -> Dict[str, Any]:
        """
        Asynchronous multi-objective optimization.
        
        Args:
            design_requirements: Target performance metrics
            constraints: Parameter bounds (min, max)
            objectives: List of optimization objectives
        
        Returns:
            Optimal design parameters and performance
        """
        
        def objective_function(x):
            """Multi-objective function for optimization."""
            # Extract design parameters
            chamber_pressure = x[0]
            area_ratio = x[1]
            propellant_mr = x[2]
            nozzle_length_ratio = x[3]
            
            try:
                # Calculate motor performance
                performance = self._calculate_motor_performance(
                    chamber_pressure, area_ratio, propellant_mr, nozzle_length_ratio
                )
                
                # Calculate objective values
                objectives_values = []
                
                if 'thrust_to_weight' in objectives:
                    tw_ratio = performance['thrust'] / performance['motor_mass']
                    objectives_values.append(-tw_ratio)  # Maximize (minimize negative)
                
                if 'specific_impulse' in objectives:
                    objectives_values.append(-performance['isp'])  # Maximize
                
                if 'manufacturing_cost' in objectives:
                    cost = self._estimate_manufacturing_cost(x)
                    objectives_values.append(cost)  # Minimize
                
                if 'safety_margin' in objectives:
                    safety = self._calculate_safety_margin(performance, constraints)
                    objectives_values.append(-safety)  # Maximize
                
                # Weighted sum approach (can be replaced with NSGA-II)
                weights = [0.3, 0.4, 0.2, 0.1]  # Adjust based on priorities
                return sum(w * obj for w, obj in zip(weights, objectives_values))
                
            except Exception as e:
                logging.error(f"Optimization error: {e}")
                return 1e6  # High penalty for failed evaluations
        
        # Define parameter bounds
        bounds = [
            constraints.get('chamber_pressure', (1e6, 20e6)),
            constraints.get('area_ratio', (5.0, 100.0)),
            constraints.get('mixture_ratio', (2.0, 8.0)),
            constraints.get('nozzle_length_ratio', (0.5, 2.0))
        ]
        
        # Run optimization asynchronously
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: differential_evolution(
                objective_function,
                bounds,
                maxiter=100,
                popsize=15,
                seed=42
            )
        )
        
        # Extract optimal parameters
        optimal_params = {
            'chamber_pressure': result.x[0],
            'area_ratio': result.x[1],
            'mixture_ratio': result.x[2],
            'nozzle_length_ratio': result.x[3]
        }
        
        # Calculate final performance
        optimal_performance = self._calculate_motor_performance(
            *result.x
        )
        
        return {
            'optimal_parameters': optimal_params,
            'performance': optimal_performance,
            'optimization_result': result,
            'convergence_history': self.optimization_history
        }
```

This comprehensive Developer Guide provides all the necessary information for contributing to HRMA development, from environment setup to advanced optimization techniques. The guide emphasizes aerospace engineering accuracy, NASA standards compliance, and robust testing practices essential for rocket motor analysis software.