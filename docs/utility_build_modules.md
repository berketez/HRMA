# Utility & Build Modules Documentation

## 1. common_fixes.py

### Overview
Collection of utility functions and fixes for common issues in rocket motor calculations, providing validation, conversions, and error handling.

### Key Modules

#### `validation` Module
Provides input validation and sanity checks.

##### Functions:
- **`validate_positive(value, name, allow_zero=False)`**
  - Ensures value is positive
  - Optional zero allowance
  - Raises ValueError with descriptive message

- **`validate_range(value, min_val, max_val, name)`**
  - Range validation
  - Inclusive bounds
  - Returns validated value

- **`validate_units(value, expected_unit, name)`**
  - Unit consistency check
  - Automatic conversion support
  - Warning for unit mismatches

#### `calculations` Module
Common calculation utilities and corrections.

##### Functions:
- **`safe_divide(numerator, denominator, default=0)`**
  - Division by zero protection
  - Configurable default value
  - NaN handling

- **`interpolate_missing(data_array, method='linear')`**
  - Fill missing data points
  - Methods: 'linear', 'cubic', 'nearest'
  - Preserves array shape

- **`smooth_data(data, window_size=5, method='gaussian')`**
  - Data smoothing
  - Methods: 'gaussian', 'moving_average', 'savgol'
  - Edge preservation

#### `graph_fixes` Module
Plotting and visualization corrections.

##### Functions:
- **`fix_axis_limits(fig, padding=0.1)`**
  - Auto-adjust axis ranges
  - Proportional padding
  - Handles log scales

- **`remove_outliers(data, threshold=3)`**
  - Statistical outlier removal
  - Z-score based
  - Returns cleaned data and indices

- **`ensure_monotonic(x_data, y_data)`**
  - Ensures monotonic x-axis
  - Sorts and removes duplicates
  - Preserves data relationships

#### `fuel_mixer` Module
Propellant mixing calculations and corrections.

##### Functions:
- **`calculate_mixture_ratio(oxidizer_flow, fuel_flow)`**
  - O/F ratio calculation
  - Unit conversion
  - Validation checks

- **`optimal_mixture_ratio(fuel_type, oxidizer_type)`**
  - Returns theoretical optimal O/F
  - Database lookup
  - Temperature corrections

- **`mixture_properties(components, mass_fractions)`**
  - Weighted average properties
  - Non-ideal mixing corrections
  - Returns property dictionary

#### `export_fixes` Module
Export format corrections and compatibility.

##### Functions:
- **`sanitize_filename(filename)`**
  - Remove invalid characters
  - Length limits
  - OS compatibility

- **`fix_encoding(text, target='utf-8')`**
  - Character encoding fixes
  - Fallback encodings
  - Error replacement

- **`format_number(value, precision=3, notation='auto')`**
  - Number formatting
  - Scientific notation control
  - Locale awareness

---

## 2. optimum_of_ratio.py

### Overview
Optimization module for finding optimal oxidizer-to-fuel ratios for maximum performance.

### Key Classes

#### `OFOptimizer`

##### Core Methods:

- **`__init__(fuel, oxidizer, pressure, expansion_ratio)`**
  - Initialize optimizer
  - Set boundary conditions
  - Load propellant data

- **`find_optimal_ratio(objective='isp')`**
  - Find optimal O/F ratio
  - Objectives: 'isp', 'thrust', 'c_star', 'density_isp'
  - Returns: Optimal ratio and performance

- **`calculate_performance(of_ratio)`**
  - Performance at specific O/F
  - Full thermodynamic calculation
  - Returns: Performance dictionary

- **`plot_optimization_curve(of_range=(0.5, 8.0))`**
  - Visualization of performance vs O/F
  - Multiple metrics overlay
  - Optimal point marking

- **`multi_objective_optimization(weights)`**
  - Weighted optimization
  - Pareto frontier
  - Trade-off analysis

### Optimization Algorithms
```python
optimization_methods = {
    'golden_section': {
        'tolerance': 1e-5,
        'max_iterations': 100,
        'bounds': (0.5, 8.0)
    },
    'brent': {
        'tolerance': 1e-6,
        'bracket': (1.0, 3.0, 6.0)
    },
    'differential_evolution': {
        'population': 15,
        'generations': 100,
        'mutation': 0.5
    }
}
```

### Performance Metrics
```python
def calculate_metrics(of_ratio):
    return {
        'isp': specific_impulse,  # seconds
        'c_star': characteristic_velocity,  # m/s
        'cf': thrust_coefficient,  # dimensionless
        'temperature': combustion_temp,  # K
        'molecular_weight': exhaust_mw,  # g/mol
        'density_isp': isp * average_density,  # s·g/cm³
        'cost_efficiency': performance_per_dollar
    }
```

---

## 3. Build Scripts

### 3.1 build_windows.py

#### Overview
Windows executable builder using PyInstaller.

#### Key Functions:

- **`prepare_build_environment()`**
  - Clean previous builds
  - Create build directories
  - Copy resources

- **`configure_pyinstaller()`**
  - Generate spec file
  - Hidden imports configuration
  - Icon and version info

- **`build_executable()`**
  - Run PyInstaller
  - Single file or directory mode
  - Console or windowed

- **`create_installer()`**
  - NSIS or Inno Setup
  - Start menu shortcuts
  - Registry entries

#### Build Configuration:
```python
build_config = {
    'name': 'HRMA',
    'version': '1.0.0',
    'icon': 'assets/icon.ico',
    'console': False,
    'onefile': True,
    'hidden_imports': [
        'scipy.special._ufuncs_cxx',
        'pkg_resources.py2_warn'
    ],
    'data_files': [
        ('templates', 'templates'),
        ('static', 'static'),
        ('propellant_cache', 'propellant_cache')
    ]
}
```

### 3.2 build_macos.py

#### Overview
macOS application bundle builder.

#### Key Functions:

- **`create_app_bundle()`**
  - .app directory structure
  - Info.plist generation
  - Resource copying

- **`sign_application(identity)`**
  - Code signing
  - Entitlements
  - Notarization preparation

- **`create_dmg()`**
  - DMG disk image
  - Background image
  - Drag-to-install setup

#### macOS Specific:
```python
info_plist = {
    'CFBundleName': 'HRMA',
    'CFBundleDisplayName': 'Hybrid Rocket Motor Analysis',
    'CFBundleIdentifier': 'com.uzaytek.hrma',
    'CFBundleVersion': '1.0.0',
    'CFBundlePackageType': 'APPL',
    'CFBundleSignature': 'HRMA',
    'CFBundleExecutable': 'HRMA',
    'NSHighResolutionCapable': True,
    'LSMinimumSystemVersion': '10.13'
}
```

---

## 4. Installation & Launch Scripts

### 4.1 install.py

#### Overview
Cross-platform installation script for dependencies and initial setup.

#### Key Functions:

- **`check_python_version()`**
  - Verify Python 3.8+
  - Display version info
  - Compatibility warnings

- **`install_dependencies()`**
  - pip installation
  - Requirements.txt processing
  - Optional dependencies

- **`setup_database()`**
  - Create database tables
  - Load initial data
  - Verify integrity

- **`configure_environment()`**
  - Environment variables
  - Path configuration
  - Permission settings

- **`run_tests()`**
  - Basic functionality tests
  - Import verification
  - API connectivity

#### Installation Flow:
```python
installation_steps = [
    'Check Python version',
    'Update pip',
    'Install core dependencies',
    'Install optional dependencies',
    'Create directories',
    'Initialize database',
    'Download propellant data',
    'Run verification tests',
    'Create shortcuts'
]
```

### 4.2 run.py

#### Overview
Unix/Linux/macOS application launcher.

#### Key Features:
```bash
#!/usr/bin/env python3
# Features:
# - Port availability check
# - Browser auto-launch
# - Process management
# - Graceful shutdown
# - Log file creation
```

#### Functions:
- **`find_available_port(start=5000)`**
  - Port scanning
  - Fallback ports
  - Conflict resolution

- **`launch_browser(url, delay=2)`**
  - Cross-browser support
  - Delayed launch
  - Fallback to manual

- **`setup_signal_handlers()`**
  - SIGINT/SIGTERM handling
  - Cleanup operations
  - Child process termination

### 4.3 run_windows.py

#### Overview
Windows-specific launcher with enhanced features.

#### Key Features:
```python
# Windows-specific features:
# - Windows firewall exception
# - System tray icon
# - Windows service mode
# - UAC elevation request
```

#### Functions:
- **`check_firewall()`**
  - Firewall rule check
  - Exception addition
  - User prompt

- **`create_tray_icon()`**
  - System tray integration
  - Context menu
  - Notifications

- **`run_as_service()`**
  - Windows service wrapper
  - Auto-start configuration
  - Service management

---

## 5. Desktop Application

### desktop_app.py

#### Overview
Desktop application wrapper using system webview.

#### Key Classes:

#### `DesktopApp`

##### Methods:
- **`__init__(title, width=1200, height=800)`**
  - Window initialization
  - Default dimensions
  - Icon setup

- **`create_window()`**
  - Native window creation
  - Webview embedding
  - Menu bar setup

- **`setup_menu()`**
  - File menu (Open, Save, Export)
  - Edit menu (Copy, Paste)
  - View menu (Zoom, Fullscreen)
  - Help menu (Documentation, About)

- **`handle_file_dialogs()`**
  - Native file choosers
  - Save/Open dialogs
  - Default directories

- **`bridge_js_python()`**
  - JavaScript to Python calls
  - Event handling
  - Data exchange

#### Configuration:
```python
desktop_config = {
    'window': {
        'title': 'HRMA - Rocket Motor Analysis',
        'width': 1200,
        'height': 800,
        'resizable': True,
        'fullscreen': False,
        'min_size': (800, 600)
    },
    'webview': {
        'debug': False,
        'js_api': True,
        'user_agent': 'HRMA Desktop/1.0'
    }
}
```

---

## Usage Examples

### Common Fixes Usage
```python
from common_fixes import validation, calculations

# Validate input
thrust = validation.validate_positive(5000, 'thrust')
of_ratio = validation.validate_range(2.5, 0.5, 8.0, 'O/F ratio')

# Safe calculations
isp = calculations.safe_divide(thrust, mass_flow, default=0)
smooth_thrust = calculations.smooth_data(thrust_array)
```

### O/F Optimization
```python
from optimum_of_ratio import of_optimizer

optimizer = of_optimizer.OFOptimizer('RP-1', 'LOX', 100, 50)
optimal_ratio, performance = optimizer.find_optimal_ratio('isp')
print(f"Optimal O/F: {optimal_ratio:.2f}")
print(f"Max ISP: {performance['isp']:.1f} s")
```

### Building Executable
```python
# Windows
python build_windows.py --onefile --icon=icon.ico

# macOS
python build_macos.py --sign "Developer ID" --dmg
```

### Installation
```python
# Run installation
python install.py --full --test

# Launch application
python run.py --port 5000 --browser chrome
```

---

## Troubleshooting

### Common Issues

#### Port Already in Use
```python
# Solution in run.py
def find_free_port():
    for port in range(5000, 5100):
        if is_port_available(port):
            return port
    raise RuntimeError("No available ports")
```

#### Missing Dependencies
```python
# Auto-install in install.py
def install_missing_packages():
    import importlib
    for package in required_packages:
        try:
            importlib.import_module(package)
        except ImportError:
            pip_install(package)
```

#### Build Failures
```python
# Debug mode in build scripts
DEBUG = True
if DEBUG:
    pyinstaller_args.append('--debug=all')
    pyinstaller_args.append('--log-level=DEBUG')
```

---

## Best Practices

### Error Handling
- Always use try-except blocks
- Log errors to file
- Provide user-friendly messages
- Implement fallback behaviors

### Performance
- Cache expensive calculations
- Use lazy loading
- Implement progress indicators
- Optimize startup time

### Cross-Platform
- Test on all target platforms
- Handle path separators correctly
- Respect OS conventions
- Provide platform-specific features