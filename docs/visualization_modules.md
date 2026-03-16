# Visualization Modules Documentation

## 1. visualization.py

### Overview
Primary visualization engine for creating professional plots and charts for rocket motor analysis data.

### Key Classes and Functions

#### `create_motor_plot(motor_data)`
- **Purpose:** Generates cross-sectional view of rocket motor
- **Parameters:**
  - `motor_data` (dict): Contains chamber dimensions, port diameters, throat/exit diameters
- **Returns:** Plotly figure object
- **Features:**
  - Converts measurements to mm for readability
  - Creates realistic nozzle geometry
  - Adds chamber, grain, and nozzle components
  - Professional styling with hover information

#### `create_injector_plot(injector_data)`
- **Purpose:** Visualizes injector design and spray patterns
- **Parameters:**
  - `injector_data` (dict): Injector type, hole patterns, flow rates
- **Returns:** Plotly figure with injector visualization
- **Supports:** Showerhead, impinging, swirl, and pintle injectors

#### `create_performance_plots(performance_data)`
- **Purpose:** Multi-panel performance charts
- **Parameters:**
  - `performance_data` (dict): Thrust, pressure, ISP vs time data
- **Returns:** Subplot figure with performance metrics
- **Charts Include:**
  - Thrust vs Time
  - Chamber Pressure vs Time
  - Specific Impulse vs Time
  - Mass Flow Rate vs Time

#### `create_heat_transfer_plots(heat_data)`
- **Purpose:** Thermal analysis visualization
- **Parameters:**
  - `heat_data` (dict): Wall temperatures, heat flux, cooling data
- **Returns:** Heat transfer analysis charts
- **Visualizations:**
  - Wall temperature distribution
  - Heat flux contours
  - Cooling channel effectiveness
  - Thermal protection system performance

#### `create_combustion_analysis_plots(combustion_data)`
- **Purpose:** Combustion characteristics visualization
- **Features:**
  - Temperature distribution
  - Species concentration
  - Reaction zones
  - Flame structure

#### `create_structural_analysis_plots(structural_data)`
- **Purpose:** Structural integrity visualization
- **Displays:**
  - Stress distribution
  - Safety factors
  - Deformation analysis
  - Material limits

#### `create_real_time_dashboard(streaming_data)`
- **Purpose:** Live data monitoring dashboard
- **Features:**
  - Real-time updates
  - Multiple data streams
  - Alert indicators
  - Historical trends

#### `create_3d_motor_visualization(motor_geometry)`
- **Purpose:** Interactive 3D motor model
- **Capabilities:**
  - Rotatable 3D view
  - Component isolation
  - Cutaway views
  - Dimension annotations

#### `create_comparative_analysis_plot(comparison_data)`
- **Purpose:** Compare multiple motor designs
- **Features:**
  - Side-by-side comparisons
  - Performance deltas
  - Design trade-offs
  - Optimization paths

#### `create_chamber_pressure_mixture_ratio_3d_surface()`
- **Purpose:** 3D surface plot of chamber pressure vs mixture ratio
- **Visualization:**
  - Optimization surface
  - Performance peaks
  - Operating envelope
  - Efficiency contours

#### `create_nozzle_mach_area_ratio_contour()`
- **Purpose:** Nozzle flow field visualization
- **Shows:**
  - Mach number distribution
  - Area ratio effects
  - Shock patterns
  - Flow separation

#### `create_wall_heat_flux_waterfall_plot()`
- **Purpose:** Time-evolution of wall heat flux
- **Features:**
  - 3D waterfall display
  - Temporal changes
  - Hot spot identification
  - Cooling requirements

### Dependencies
- `plotly.graph_objects`: Core plotting library
- `plotly.express`: Quick plot generation
- `numpy`: Numerical operations
- `scipy.interpolate`: Data smoothing

---

## 2. visualization_improved.py

### Overview
Enhanced visualization module with advanced rendering capabilities and improved aesthetics.

### Key Functions

#### `create_improved_motor_cross_section(motor_params)`
- **Purpose:** High-fidelity motor cross-section with materials
- **Enhancements:**
  - Material textures
  - Gradient fills
  - Dimensional callouts
  - Component labels
  - Export-ready quality

#### `create_improved_injector_design(injector_params)`
- **Purpose:** Detailed injector visualization with flow patterns
- **Features:**
  - Flow streamlines
  - Pressure drop visualization
  - Mixing efficiency
  - Spray cone angles
  - Velocity vectors

### Advanced Features
- **Animation Support:** Time-based animations for transient phenomena
- **High-Resolution Export:** Publication-quality image export
- **Custom Colormaps:** Optimized for technical visualization
- **Interactive Legends:** Toggle component visibility
- **Measurement Tools:** On-plot dimension measurements

### Improvements Over Base Module
1. **Better Performance:** Optimized rendering for large datasets
2. **Enhanced Interactivity:** More responsive controls
3. **Professional Styling:** Publication-ready aesthetics
4. **Extended Format Support:** SVG, PDF, high-DPI PNG
5. **Accessibility Features:** Colorblind-friendly palettes

---

## 3. advanced_results.py

### Overview
Specialized module for generating professional analysis outputs similar to NASA CEA format.

### Key Functions

#### `create_cea_style_results(engine_data, output_format='text')`
- **Purpose:** Generate NASA CEA-style performance tables
- **Parameters:**
  - `engine_data`: Complete engine analysis results
  - `output_format`: 'text', 'html', or 'latex'
- **Output Format:**
  ```
  THEORETICAL ROCKET PERFORMANCE
  Pin = X bar, Pe/Pc = Y
  CHAMBER  THROAT  EXIT
  Parameters listed in standard CEA format
  ```

#### `create_altitude_performance_plot(altitude_range, performance_data)`
- **Purpose:** Performance variation with altitude
- **Visualizes:**
  - Thrust vs altitude
  - ISP vs altitude
  - Pressure ratio effects
  - Atmospheric compensation

#### `create_mass_fractions_plot(species_data)`
- **Purpose:** Chemical species mass fraction visualization
- **Features:**
  - Major species tracking
  - Minor species (ppm level)
  - Temperature correlation
  - Equilibrium vs frozen flow

#### `create_thrust_altitude_plot(trajectory_data)`
- **Purpose:** Thrust profile during ascent
- **Shows:**
  - Thrust variation
  - Dynamic pressure effects
  - Throttling regions
  - Stage separation points

### Output Formats
1. **Text Tables:** ASCII formatted for console/file output
2. **HTML Tables:** Web-ready with styling
3. **LaTeX Tables:** Publication-ready format
4. **CSV Export:** Data analysis compatibility
5. **JSON Export:** API/database integration

### Professional Features
- **Unit System Toggle:** SI/Imperial units
- **Precision Control:** Configurable decimal places
- **Reference Conditions:** Sea level/vacuum toggle
- **Frozen/Equilibrium:** Flow assumption selection
- **Uncertainty Bands:** Error propagation display

---

## Usage Examples

### Basic Visualization
```python
from visualization import create_motor_plot

motor_data = {
    'chamber_length': 0.3,
    'chamber_diameter': 0.1,
    'port_diameter_initial': 0.03,
    'throat_diameter': 0.02,
    'exit_diameter': 0.08
}

fig = create_motor_plot(motor_data)
fig.show()
```

### Advanced Results
```python
from advanced_results import create_cea_style_results

results = create_cea_style_results(
    engine_data,
    output_format='html'
)
```

### Improved Visualization
```python
from visualization_improved import create_improved_motor_cross_section

enhanced_fig = create_improved_motor_cross_section({
    'motor_params': motor_data,
    'show_materials': True,
    'show_dimensions': True
})
```

---

## Configuration Options

### Global Settings
- `DPI_EXPORT`: Export resolution (default: 300)
- `COLOR_SCHEME`: 'default', 'professional', 'print'
- `FONT_FAMILY`: Plot font selection
- `GRID_STYLE`: Grid line appearance
- `BACKGROUND`: Plot background color

### Performance Optimization
- Use `decimation` for large datasets
- Enable `webgl` for 3D plots
- Implement `caching` for repeated plots
- Utilize `batch_mode` for multiple exports