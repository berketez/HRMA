# Chapter 9: User Manual

## Table of Contents
1. [Getting Started](#getting-started)
2. [Web Interface Guide](#web-interface-guide)
3. [Motor Analysis Workflows](#motor-analysis-workflows)
4. [API Usage Examples](#api-usage-examples)
5. [Data Import and Export](#data-import-and-export)
6. [Troubleshooting](#troubleshooting)
7. [Performance Optimization Tips](#performance-optimization-tips)
8. [Advanced Features](#advanced-features)
9. [Integration with External Tools](#integration-with-external-tools)
10. [Frequently Asked Questions](#frequently-asked-questions)

## 1. Getting Started

### System Requirements
HRMA is designed to run on modern computing platforms with sufficient processing power for complex aerospace calculations.

#### Minimum Requirements
```
Operating System: Windows 10+, macOS 10.15+, Ubuntu 20.04+
Processor: Intel Core i5 or AMD Ryzen 5 (quad-core minimum)
Memory: 8 GB RAM
Storage: 5 GB available space
Network: Internet connection for NASA CEA validation
Browser: Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
```

#### Recommended Requirements
```
Operating System: Windows 11, macOS 12+, Ubuntu 22.04+
Processor: Intel Core i7/i9 or AMD Ryzen 7/9 (8+ cores)
Memory: 16+ GB RAM
Storage: 50+ GB available space (SSD recommended)
Network: High-speed internet for real-time validation
Browser: Latest version of Chrome or Firefox
```

### Installation and Setup

#### Quick Start Installation
```bash
# Download HRMA
git clone https://github.com/hrma/hrma-platform.git
cd hrma-platform

# Install dependencies
pip install -r requirements.txt

# Initialize database
python scripts/setup_database.py

# Start the application
python main.py
```

#### Web Access
Once HRMA is running, access the web interface at:
```
http://localhost:8000
```

### First-Time Configuration

#### User Account Setup
1. Navigate to `http://localhost:8000/register`
2. Create your account with aerospace engineering credentials
3. Verify email address (if configured)
4. Set up your analysis preferences

#### Workspace Configuration
```python
# Navigate to Settings > Workspace
{
    "default_units": "SI",              # SI or Imperial
    "precision": "high",                # low, medium, high
    "validation": "nasa_cea",           # Enable NASA CEA validation
    "auto_save": true,                  # Auto-save analyses
    "export_format": "pdf",             # Default export format
    "theme": "aerospace_dark"           # UI theme
}
```

## 2. Web Interface Guide

### Dashboard Overview
The HRMA dashboard provides a comprehensive overview of your rocket motor analyses and system status.

#### Main Dashboard Components
```
┌─────────────────────────────────────────────────────────────────────┐
│  HRMA - Hybrid Rocket Motor Analysis                    [Profile] ▼  │
├─────────────────────────────────────────────────────────────────────┤
│  Dashboard    Projects    Analysis    Validation    Reports    Help   │
├─────────────────┬───────────────────┬───────────────────────────────┤
│                 │                   │                               │
│  Quick Actions  │   Recent Projects │    System Status              │
│  • New Analysis │   • Apollo Redux  │    ✓ NASA CEA Connected      │
│  • Load Project │   • Mars Ascent   │    ✓ Database Healthy        │
│  • Import Data  │   • Lunar Lander  │    ⚠ Cache 85% Full          │
│  • Help Guide   │   • See All →     │    ℹ Last Sync: 2 min ago    │
│                 │                   │                               │
├─────────────────┼───────────────────┼───────────────────────────────┤
│                 │                   │                               │
│  Analysis Types │   Performance     │    Quick Stats                │
│  🚀 Solid       │   Overview        │    • Total Analyses: 1,247   │
│  💧 Liquid      │   [CHART]         │    • This Month: 89           │
│  🔥 Hybrid      │                   │    • Success Rate: 98.2%     │
│  📊 Compare     │                   │    • Avg Analysis Time: 2.3s │
│                 │                   │                               │
└─────────────────┴───────────────────┴───────────────────────────────┘
```

#### Navigation Menu
- **Dashboard**: Main overview and system status
- **Projects**: Manage rocket motor projects and configurations
- **Analysis**: Perform detailed motor performance analysis
- **Validation**: NASA CEA validation and comparison tools
- **Reports**: Generate professional analysis reports
- **Help**: Documentation, tutorials, and support

### Project Management

#### Creating a New Project
1. Click **Projects** > **New Project**
2. Fill in project details:
```yaml
Project Information:
  Name: "Mars Ascent Vehicle Main Engine"
  Description: "Liquid methane/oxygen engine for Mars ascent"
  Motor Type: "Liquid"
  Propellant: "CH4/LOX"
  
Design Requirements:
  Target Thrust: "45,000 N"
  Target Isp: "350 seconds"
  Chamber Pressure: "7.0 MPa"
  Mission Duration: "420 seconds"
  
Team Information:
  Lead Engineer: "Dr. Sarah Chen"
  Organization: "Mars Exploration Program"
  Classification: "Internal Use Only"
```

3. Click **Create Project** to initialize

#### Project Dashboard
Each project has its own dedicated dashboard with:
- **Analysis History**: Timeline of all performed analyses
- **Performance Trends**: Graphical representation of design evolution
- **Team Collaboration**: Comments, notes, and version control
- **File Management**: CAD files, test data, reports

### Analysis Workflow Interface

#### Step-by-Step Analysis Wizard
HRMA provides a guided analysis wizard for beginners and quick analyses:

```
Step 1: Motor Type Selection
┌─────────────────────────────────────────────────────────┐
│  Select Rocket Motor Type:                              │
│                                                         │
│  🚀 Solid Rocket Motor                                  │
│     • Best for: Simple designs, high thrust-to-weight  │
│     • Examples: Space Shuttle SRB, military missiles   │
│     • Analysis time: ~30 seconds                       │
│                                                         │
│  💧 Liquid Rocket Motor                                 │
│     • Best for: High performance, throttleable         │
│     • Examples: SpaceX Merlin, NASA RS-25              │
│     • Analysis time: ~60 seconds                       │
│                                                         │
│  🔥 Hybrid Rocket Motor                                 │
│     • Best for: Safety, simplicity, restartable        │
│     • Examples: Virgin Galactic, some sounding rockets │
│     • Analysis time: ~45 seconds                       │
│                                                         │
│                    [Continue] [Cancel]                  │
└─────────────────────────────────────────────────────────┘
```

#### Advanced Parameter Input
For experienced users, HRMA provides comprehensive parameter input:

```python
# Liquid Motor Analysis Parameters
{
    "propellant_combination": {
        "fuel": "LH2",                    # Liquid hydrogen
        "oxidizer": "LOX",                # Liquid oxygen
        "mixture_ratio": 6.0,             # O/F ratio
        "fuel_temperature": 20.3,         # Kelvin
        "oxidizer_temperature": 90.2      # Kelvin
    },
    
    "chamber_conditions": {
        "pressure": 7000000,              # Pa (70 bar)
        "temperature": 3588,              # K (NASA CEA)
        "c_star_efficiency": 0.97         # Combustion efficiency
    },
    
    "nozzle_geometry": {
        "throat_diameter": 0.200,         # meters
        "area_ratio": 40.0,               # Ae/At
        "nozzle_type": "bell",            # bell, conical, aerospike
        "length_fraction": 0.8            # 80% bell nozzle
    },
    
    "mission_profile": {
        "altitude_profile": [0, 50000, 100000, 150000],  # meters
        "flight_time": 480,               # seconds
        "throttle_profile": "constant"    # constant, variable
    }
}
```

### Real-Time Analysis Display
During analysis, HRMA provides real-time feedback:

```
Analysis Progress: Mars Ascent Vehicle Main Engine
┌─────────────────────────────────────────────────────────────────┐
│  Propellant Analysis        ████████████████████  100% ✓        │
│  Thermodynamic Calculation  ████████████████████  100% ✓        │
│  Nozzle Design             ████████████████████  100% ✓        │
│  Performance Analysis      ██████████████████    90%  ⟳        │
│  NASA CEA Validation       ████████              40%  ⟳        │
│  Report Generation         ░░░░░░░░░░░░░░░░░░░░  0%   ⏸        │
└─────────────────────────────────────────────────────────────────┘

Current Step: Performance Analysis
• Calculating thrust coefficient... ✓
• Computing specific impulse... ✓
• Analyzing altitude performance... ⟳
• Optimizing nozzle contour... ⏳

Estimated completion: 23 seconds
```

## 3. Motor Analysis Workflows

### Solid Rocket Motor Analysis

#### Basic Solid Motor Workflow
1. **Propellant Selection**
   ```python
   # Common solid propellants in HRMA database
   solid_propellants = {
       "APCP": {  # Ammonium Perchlorate Composite Propellant
           "description": "Most common modern solid propellant",
           "typical_isp": "260-280 seconds",
           "density": "1750 kg/m³",
           "burn_rate": "a=0.0348, n=0.35"
       },
       "NEPE": {  # Nitrate Ester Plasticized Polyether
           "description": "High-energy military propellant",
           "typical_isp": "270-290 seconds", 
           "density": "1800 kg/m³",
           "burn_rate": "a=0.0421, n=0.33"
       },
       "Double_Base": {  # Nitrocellulose/Nitroglycerin
           "description": "Traditional propellant, higher burn rate exponent",
           "typical_isp": "230-250 seconds",
           "density": "1600 kg/m³", 
           "burn_rate": "a=0.0234, n=0.78"
       }
   }
   ```

2. **Grain Geometry Design**
   ```
   Select Grain Configuration:
   ┌──────────────────────────────────────────────────────────┐
   │  ⚫ BATES Grain (Cylindrical with central port)          │
   │     • Simple manufacturing                               │
   │     • Progressive-neutral burning                        │
   │     • Good for small motors                              │
   │                                                          │
   │  ⭐ STAR Grain (Star-shaped cross-section)               │
   │     • More complex geometry                              │
   │     • Higher surface area                                │
   │     • Progressive burning characteristics                │
   │                                                          │
   │  🔷 FINOCYL Grain (Fins + central cylinder)             │
   │     • Advanced design                                    │
   │     • Optimized burning surface                          │
   │     • Used in large motors                               │
   └──────────────────────────────────────────────────────────┘
   ```

3. **Analysis Results Display**
   ```
   Solid Motor Analysis Results: APCP BATES Grain
   ┌─────────────────────────────────────────────────────────────┐
   │  Performance Summary                                        │
   │  • Total Impulse: 2,850,000 N·s                           │
   │  • Average Thrust: 142,500 N                               │
   │  • Burn Time: 20.0 seconds                                 │
   │  • Specific Impulse: 268.4 seconds                         │
   │  • Chamber Pressure: 6.2 MPa (avg)                        │
   │                                                             │
   │  Grain Geometry                                             │
   │  • Outer Diameter: 0.60 m                                  │
   │  • Core Diameter: 0.15 m                                   │
   │  • Grain Length: 1.2 m                                     │
   │  • Web Thickness: 0.225 m                                  │
   │  • Propellant Mass: 1,088 kg                               │
   │                                                             │
   │  Nozzle Design                                              │
   │  • Throat Diameter: 0.084 m                                │
   │  • Exit Diameter: 0.189 m                                  │
   │  • Area Ratio: 5.1                                         │
   │  • Nozzle Length: 0.31 m                                   │
   └─────────────────────────────────────────────────────────────┘
   ```

### Liquid Rocket Motor Analysis

#### Comprehensive Liquid Motor Workflow
1. **Propellant System Design**
   ```python
   # Example: SpaceX Merlin-class engine
   liquid_system = {
       "propellants": {
           "fuel": {
               "type": "RP-1",
               "density": 810,           # kg/m³
               "temperature": 288,       # K
               "supply_pressure": 4.5e6  # Pa
           },
           "oxidizer": {
               "type": "LOX", 
               "density": 1141,          # kg/m³
               "temperature": 90.2,      # K
               "supply_pressure": 4.5e6  # Pa
           }
       },
       
       "feed_system": {
           "type": "gas_generator",      # gas_generator, staged_combustion, electric
           "turbopump_efficiency": 0.75,
           "pressure_drop": 0.5e6        # Pa
       },
       
       "injection": {
           "type": "unlike_doublet",     # unlike_doublet, shear_coaxial, pintle
           "pressure_drop": 1.2e6,       # Pa
           "injection_velocity": 45.0    # m/s
       }
   }
   ```

2. **Feed System Analysis**
   ```
   Feed System Analysis: Gas Generator Cycle
   ┌──────────────────────────────────────────────────────────┐
   │  Turbopump Performance                                   │
   │  • Fuel Pump Pressure Rise: 8.5 MPa                     │
   │  • Oxidizer Pump Pressure Rise: 9.2 MPa                 │
   │  • Turbine Power Required: 2.8 MW                       │
   │  • Gas Generator O/F Ratio: 0.3 (fuel-rich)            │
   │                                                          │
   │  Mass Flow Rates                                         │
   │  • Main Fuel Flow: 140.2 kg/s                           │
   │  • Main Oxidizer Flow: 241.6 kg/s                       │
   │  • Gas Gen Fuel Flow: 2.1 kg/s                          │
   │  • Gas Gen Oxidizer Flow: 0.63 kg/s                     │
   │  • Total Propellant Flow: 384.5 kg/s                    │
   │                                                          │
   │  System Pressures                                        │
   │  • Tank Pressure: 4.5 MPa                               │
   │  • Pump Outlet: 12.8 MPa                                │
   │  • Chamber Pressure: 9.7 MPa                            │
   │  • Nozzle Exit: 0.085 MPa (sea level)                   │
   └──────────────────────────────────────────────────────────┘
   ```

3. **Cooling System Analysis**
   ```python
   # Regenerative cooling analysis
   cooling_analysis = {
       "coolant": "RP-1",                    # Fuel as coolant
       "coolant_flow_rate": 140.2,           # kg/s
       "heat_transfer": {
           "chamber_heat_flux": 8.5e6,       # W/m² (high)
           "nozzle_heat_flux": 12.3e6,       # W/m² (maximum at throat)
           "cooling_channels": 158,           # Number of channels
           "channel_width": 0.003,            # m
           "channel_depth": 0.004             # m
       },
       "material_properties": {
           "chamber_material": "Inconel 718",
           "thermal_conductivity": 11.4,      # W/m·K
           "melting_point": 1609,             # K
           "max_operating_temp": 1200         # K (design limit)
       }
   }
   ```

### Hybrid Rocket Motor Analysis

#### Hybrid Motor Analysis Process
1. **Fuel Grain Design**
   ```python
   # Hybrid fuel grain configuration
   hybrid_fuel = {
       "fuel_type": "HTPB",                  # Hydroxyl-terminated polybutadiene
       "fuel_properties": {
           "density": 920,                   # kg/m³
           "regression_rate": {
               "a": 0.047,                   # mm/s at 1 MPa
               "n": 0.68                     # Pressure exponent
           },
           "c_star": 1520                    # m/s (with N2O)
       },
       
       "grain_geometry": {
           "type": "single_port",            # single_port, multi_port, wagon_wheel
           "outer_diameter": 0.15,           # m
           "initial_port_diameter": 0.05,    # m
           "grain_length": 0.80,             # m
           "number_of_ports": 1
       }
   }
   ```

2. **Oxidizer System**
   ```
   Oxidizer System Configuration: Nitrous Oxide (N2O)
   ┌──────────────────────────────────────────────────────────┐
   │  Storage System                                          │
   │  • Storage Pressure: 5.0 MPa (self-pressurizing)        │
   │  • Storage Temperature: 288 K                            │
   │  • Oxidizer Mass: 45.2 kg                               │
   │  • Tank Volume: 67.5 liters                             │
   │  • Fill Ratio: 67% (liquid/vapor equilibrium)           │
   │                                                          │
   │  Injection System                                        │
   │  • Injector Type: Showerhead                            │
   │  • Number of Orifices: 37                               │
   │  • Orifice Diameter: 1.2 mm                             │
   │  • Injection Pressure: 4.2 MPa                          │
   │  • Flow Coefficient (Cd): 0.63                          │
   │                                                          │
   │  Safety Features                                         │
   │  • Pressure Relief Valve: 6.0 MPa                       │
   │  • Remote Venting System: Available                     │
   │  • Emergency Shutdown: Pneumatic                        │
   │  • Fill/Drain Disconnect: Quick-connect                 │
   └──────────────────────────────────────────────────────────┘
   ```

3. **Burn Analysis**
   ```
   Hybrid Motor Burn Analysis: HTPB/N2O
   ┌──────────────────────────────────────────────────────────────────┐
   │  Time    Chamber     Fuel Flow   Ox Flow    Thrust    Port Dia   │
   │  (s)     Press.(MPa) Rate(kg/s)  Rate(kg/s)  (N)     (mm)       │
   │  ────────────────────────────────────────────────────────────── │
   │  0.0     3.8         0.12        2.45       1,847     50.0       │
   │  5.0     3.6         0.18        2.31       1,756     52.8       │
   │  10.0    3.4         0.24        2.18       1,665     56.2       │
   │  15.0    3.2         0.31        2.06       1,574     60.1       │
   │  20.0    3.0         0.39        1.95       1,483     64.6       │
   │  25.0    2.8         0.48        1.84       1,392     69.7       │
   │  30.0    2.6         0.58        1.74       1,301     75.4       │
   │                                                                  │
   │  Average Performance                                             │
   │  • Total Impulse: 46,890 N·s                                    │
   │  • Average Thrust: 1,563 N                                      │
   │  • Average Isp: 245 seconds                                     │
   │  • Fuel Consumption: 9.7 kg                                     │
   │  • Oxidizer Consumption: 64.4 kg                                │
   │  • Final O/F Ratio: 6.6                                         │
   └──────────────────────────────────────────────────────────────────┘
   ```

## 4. API Usage Examples

### RESTful API Access

#### Authentication
```python
import requests
import json

# API endpoint
base_url = "http://localhost:8000/api/v1"

# Authenticate and get access token
auth_response = requests.post(
    f"{base_url}/auth/login",
    json={
        "username": "aerospace_engineer@example.com",
        "password": "secure_password"
    }
)

token = auth_response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
```

#### Simple Motor Analysis
```python
# Quick liquid motor analysis
analysis_request = {
    "motor_type": "liquid",
    "propellants": {
        "fuel": "LH2",
        "oxidizer": "LOX",
        "mixture_ratio": 6.0
    },
    "chamber_pressure": 7000000,  # 70 bar
    "nozzle": {
        "throat_area": 0.0314,    # m² (200mm diameter)
        "area_ratio": 40.0,
        "nozzle_type": "bell"
    },
    "mission": {
        "altitude": 100000,       # m (100 km)
        "ambient_pressure": 0     # Pa (vacuum)
    }
}

response = requests.post(
    f"{base_url}/analysis/liquid",
    headers=headers,
    json=analysis_request
)

results = response.json()
print(f"Thrust: {results['performance']['thrust']:.0f} N")
print(f"Isp: {results['performance']['specific_impulse']:.1f} s")
print(f"C*: {results['thermodynamics']['c_star']:.0f} m/s")
```

#### Batch Analysis for Parametric Studies
```python
# Parametric study: varying mixture ratio
mixture_ratios = [4.0, 5.0, 6.0, 7.0, 8.0]
results = []

for mr in mixture_ratios:
    analysis_request["propellants"]["mixture_ratio"] = mr
    
    response = requests.post(
        f"{base_url}/analysis/liquid",
        headers=headers,
        json=analysis_request
    )
    
    if response.status_code == 200:
        result = response.json()
        results.append({
            "mixture_ratio": mr,
            "isp": result["performance"]["specific_impulse"],
            "thrust": result["performance"]["thrust"],
            "c_star": result["thermodynamics"]["c_star"]
        })

# Find optimal mixture ratio
optimal = max(results, key=lambda x: x["isp"])
print(f"Optimal MR: {optimal['mixture_ratio']} (Isp: {optimal['isp']:.1f}s)")
```

### WebSocket Real-Time Analysis
```python
import asyncio
import websockets
import json

async def real_time_analysis():
    """Real-time analysis with WebSocket connection."""
    uri = "ws://localhost:8000/ws/analysis"
    
    async with websockets.connect(uri, extra_headers=headers) as websocket:
        # Send analysis request
        await websocket.send(json.dumps({
            "type": "start_analysis",
            "data": analysis_request
        }))
        
        # Receive real-time updates
        async for message in websocket:
            data = json.loads(message)
            
            if data["type"] == "progress":
                print(f"Progress: {data['percentage']:.1f}% - {data['step']}")
            
            elif data["type"] == "intermediate_result":
                print(f"Intermediate: {data['parameter']} = {data['value']}")
            
            elif data["type"] == "completion":
                print("Analysis complete!")
                results = data["results"]
                break
            
            elif data["type"] == "error":
                print(f"Analysis error: {data['message']}")
                break

# Run async analysis
asyncio.run(real_time_analysis())
```

### NASA CEA Validation API
```python
# Validate HRMA results against NASA CEA
validation_request = {
    "propellant_combination": "LH2/LOX",
    "mixture_ratio": 6.0,
    "chamber_pressure": 7000000,
    "area_ratio": 40.0,
    "hrma_results": {
        "c_star": 1580.0,
        "isp": 452.3,
        "chamber_temperature": 3588.0,
        "gamma": 1.135
    }
}

validation_response = requests.post(
    f"{base_url}/validation/nasa-cea",
    headers=headers,
    json=validation_request
)

validation = validation_response.json()
print("NASA CEA Validation Results:")
for parameter, data in validation["comparison"].items():
    status = "✓ PASS" if data["error_percent"] < 2.0 else "✗ FAIL"
    print(f"  {parameter}: {status} ({data['error_percent']:.2f}% error)")
```

## 5. Data Import and Export

### Supported File Formats

#### Import Capabilities
```python
supported_imports = {
    "propellant_data": [".csv", ".json", ".xlsx"],
    "test_data": [".csv", ".dat", ".txt", ".xlsx"],
    "cad_geometry": [".step", ".iges", ".stl"],
    "cea_outputs": [".out", ".plt", ".csv"],
    "project_files": [".hrma", ".json", ".zip"]
}
```

#### Export Capabilities  
```python
supported_exports = {
    "analysis_results": [".pdf", ".docx", ".csv", ".json", ".xlsx"],
    "performance_plots": [".png", ".svg", ".pdf", ".eps"],
    "3d_models": [".step", ".iges", ".stl", ".obj"],
    "simulation_data": [".csv", ".hdf5", ".mat"],
    "project_archive": [".hrma", ".zip"]
}
```

### Import Workflows

#### Importing Test Data
```python
# Example: Import static fire test data
test_data_import = {
    "file_path": "/data/static_fire_test_2024.csv",
    "data_type": "test_results",
    "columns_mapping": {
        "time_s": "time",
        "thrust_N": "thrust", 
        "chamber_pressure_psi": "chamber_pressure",
        "propellant_flow_lbs": "mass_flow_rate"
    },
    "unit_conversions": {
        "chamber_pressure": "psi_to_pa",
        "mass_flow_rate": "lbs_to_kg"
    }
}

# Import via web interface
response = requests.post(
    f"{base_url}/import/test-data",
    headers=headers,
    json=test_data_import
)
```

#### Importing NASA CEA Data
```
NASA CEA Import Wizard
┌─────────────────────────────────────────────────────────────────────┐
│  Step 1: Select CEA Output File                                     │
│  File: mars_ascent_cea_output.out                   [Browse...]      │
│                                                                     │
│  Step 2: Parse CEA Data                                             │
│  ✓ Propellant combination detected: CH4/LOX                        │
│  ✓ Mixture ratio range: 2.0 to 4.0                                 │
│  ✓ Pressure range: 10 to 100 bar                                   │
│  ✓ 45 data points identified                                       │
│                                                                     │
│  Step 3: Import Options                                             │
│  □ Overwrite existing data for this propellant                     │
│  ☑ Create validation cases for HRMA comparison                     │
│  ☑ Generate interpolation tables for fast lookup                   │
│  □ Export processed data to CSV                                    │
│                                                                     │
│                    [Import Data] [Cancel]                          │
└─────────────────────────────────────────────────────────────────────┘
```

### Export Workflows

#### Professional Report Generation
```python
# Generate comprehensive analysis report
report_config = {
    "analysis_id": "mars_ascent_analysis_001",
    "template": "aerospace_professional",
    "sections": [
        "executive_summary",
        "technical_specifications", 
        "performance_analysis",
        "validation_results",
        "recommendations",
        "appendices"
    ],
    "formatting": {
        "include_equations": True,
        "include_plots": True,
        "plot_dpi": 300,
        "color_scheme": "professional",
        "page_layout": "letter"
    },
    "export_format": "pdf"
}

response = requests.post(
    f"{base_url}/export/report",
    headers=headers,
    json=report_config
)

# Download generated report
if response.status_code == 200:
    report_url = response.json()["download_url"]
    report_content = requests.get(f"{base_url}{report_url}").content
    
    with open("mars_ascent_analysis_report.pdf", "wb") as f:
        f.write(report_content)
```

#### Batch Data Export
```python
# Export multiple analyses for comparison
batch_export = {
    "export_type": "comparative_analysis",
    "analysis_ids": [
        "solid_motor_apcp_001",
        "solid_motor_nepe_001", 
        "liquid_motor_rp1_001",
        "hybrid_motor_htpb_001"
    ],
    "export_format": "xlsx",
    "include_charts": True,
    "chart_types": ["thrust_curves", "isp_comparison", "cost_analysis"]
}

response = requests.post(
    f"{base_url}/export/batch",
    headers=headers,
    json=batch_export
)
```

## 6. Troubleshooting

### Common Issues and Solutions

#### Analysis Failures

**Issue**: "Thermodynamic calculation failed to converge"
```
Error Code: THERMO_001
Description: Thermodynamic iteration did not converge within maximum iterations

Possible Causes:
1. Extreme mixture ratios outside physical bounds
2. Invalid propellant combination
3. Unrealistic chamber conditions

Solutions:
• Check mixture ratio is within propellant limits (typically 0.5-15)
• Verify chamber pressure is reasonable (0.1-20 MPa)
• Ensure propellant combination is chemically feasible
• Try reducing calculation precision temporarily
```

**Issue**: "NASA CEA validation timeout"
```
Error Code: CEA_TIMEOUT
Description: NASA CEA validation server did not respond within timeout period

Troubleshooting Steps:
1. Check internet connectivity
2. Verify NASA CEA server status at http://cea.nasa.gov
3. Try analysis without validation temporarily
4. Contact system administrator if persistent

Workaround:
• Disable CEA validation: Settings > Validation > NASA CEA: OFF
• Use cached CEA data if available
• Perform offline validation later
```

#### Performance Issues

**Issue**: Slow analysis performance
```
Performance Optimization Checklist:
□ Reduce analysis precision if high accuracy not required
□ Use cached propellant data instead of real-time calculations
□ Disable unnecessary validation steps
□ Close other resource-intensive applications
□ Check available system memory (recommended: 16+ GB)
□ Verify SSD storage for better I/O performance
```

**Issue**: Memory usage warnings
```
Memory Management:
• Current usage: 12.4 GB / 16.0 GB available
• Recommendation: Close unused projects
• Clear analysis cache: Settings > Performance > Clear Cache
• Reduce batch analysis size (max recommended: 50 cases)
• Consider upgrading system RAM for large parametric studies
```

#### Data Import/Export Issues

**Issue**: "Unsupported file format"
```
File Format Troubleshooting:
1. Verify file extension matches content type
2. Check for file corruption (try opening in original application)
3. Convert to supported format:
   • CSV for tabular data
   • JSON for structured data  
   • PDF for reports
4. Check file size limits (max: 100 MB per file)
```

#### Validation Discrepancies

**Issue**: Large differences between HRMA and NASA CEA results
```
Validation Troubleshooting:
1. Verify exact propellant specifications match
2. Check mixture ratio precision (±0.1 difference can cause 1-2% error)
3. Confirm chamber pressure units (Pa vs. bar vs. psi)
4. Review ambient conditions (altitude, atmospheric pressure)
5. Check for frozen vs. equilibrium flow assumptions

Acceptable Tolerances:
• C* (characteristic velocity): ±2%
• Isp (specific impulse): ±3%
• Chamber temperature: ±50 K
• Thrust coefficient: ±2%
```

### System Health Monitoring

#### Performance Dashboard
```
System Health Status
┌─────────────────────────────────────────────────────────────────────┐
│  Component Status                               Last Updated: 14:32  │
│                                                                     │
│  🟢 Analysis Engine        Healthy    Response: 1.2s  Load: 23%     │
│  🟢 Database               Healthy    Queries: 847/s  Conn: 12/50    │
│  🟡 NASA CEA Interface     Warning    Latency: 4.8s  Timeout: 2     │
│  🟢 Cache System           Healthy    Hit Rate: 94%  Size: 2.1 GB    │
│  🟢 File Storage           Healthy    Usage: 67%    Free: 15.2 GB    │
│  🔴 Backup Service         Error      Last: 3 days ago              │
│                                                                     │
│  Recent Errors (Last 24h): 3                                       │
│  • CEA timeout (x2): Non-critical, using cached data               │
│  • File upload size exceeded: User education needed                │
│                                                                     │
│  Recommendations:                                                   │
│  • Schedule backup service maintenance                              │
│  • Monitor CEA interface stability                                  │
│  • Clear old cache files to free storage                          │
└─────────────────────────────────────────────────────────────────────┘
```

## 7. Performance Optimization Tips

### Analysis Speed Optimization

#### Quick Analysis Settings
```python
# Fast analysis configuration (±5% accuracy)
fast_config = {
    "precision": "medium",           # low, medium, high
    "nasa_cea_validation": False,    # Skip validation for speed
    "use_cached_data": True,         # Use precomputed propellant data  
    "simplified_nozzle": True,       # Use approximations for nozzle
    "max_iterations": 50,            # Reduce iteration count
    "convergence_tolerance": 1e-4    # Relaxed tolerance
}

# Apply configuration
response = requests.post(
    f"{base_url}/config/analysis",
    headers=headers,
    json=fast_config
)
```

#### Batch Processing Optimization
```python
# Efficient parametric study setup
parametric_study = {
    "base_configuration": analysis_request,
    "parameters": {
        "mixture_ratio": {
            "range": [4.0, 8.0],
            "step": 0.5,
            "priority": "high"        # Calculate first for early feedback
        },
        "chamber_pressure": {
            "range": [5e6, 12e6],
            "step": 1e6,
            "priority": "medium"
        },
        "area_ratio": {
            "range": [10, 50],
            "step": 10,
            "priority": "low"
        }
    },
    "parallel_processing": {
        "enabled": True,
        "max_workers": 8,             # Match CPU cores
        "batch_size": 20              # Process in chunks
    }
}
```

### Memory Management

#### Cache Configuration
```
Cache Management Settings
┌─────────────────────────────────────────────────────────────────┐
│  Propellant Data Cache                                          │
│  • Size Limit: 2.0 GB                                          │
│  • Current Usage: 1.2 GB (60%)                                 │
│  • Hit Rate: 94.3%                                             │
│  • Auto-cleanup: Weekly                                        │
│                                                                 │
│  Analysis Results Cache                                         │
│  • Size Limit: 500 MB                                          │
│  • Current Usage: 287 MB (57%)                                 │
│  • Retention: 30 days                                          │
│  • Compression: Enabled                                        │
│                                                                 │
│  NASA CEA Cache                                                 │
│  • Size Limit: 1.0 GB                                          │
│  • Current Usage: 643 MB (64%)                                 │
│  • Offline Mode: Available                                     │
│  • Update Frequency: Daily                                     │
│                                                                 │
│                [Clear All] [Optimize] [Configure]              │
└─────────────────────────────────────────────────────────────────┘
```

## 8. Advanced Features

### Multi-Objective Optimization

#### Optimization Setup Interface
```
Multi-Objective Optimization: Mars Ascent Engine
┌─────────────────────────────────────────────────────────────────────┐
│  Objectives (Select 2-4)                    Weight    Current       │
│  ☑ Maximize Specific Impulse               30%       ───────────    │
│  ☑ Minimize Engine Mass                    25%       ───────────    │
│  ☑ Maximize Thrust-to-Weight Ratio         35%       ███████████    │
│  ☑ Minimize Manufacturing Cost             10%       ───────────    │
│  ☐ Minimize Development Risk                0%       ───────────    │
│                                                                     │
│  Design Variables                      Min        Current      Max  │
│  Chamber Pressure (MPa)               5.0        7.0          15.0  │
│  Mixture Ratio                        2.5        3.8          4.5   │
│  Area Ratio                           15         35           65    │
│  Nozzle Length/Throat Dia             0.5        1.2          2.0   │
│                                                                     │
│  Constraints                                                        │
│  ☑ Chamber temperature < 3800 K                                    │
│  ☑ Nozzle exit pressure > ambient                                  │
│  ☑ Thrust > 40,000 N minimum                                       │
│  ☑ Engine mass < 500 kg maximum                                    │
│                                                                     │
│  Algorithm: NSGA-II    Population: 100    Generations: 50          │
│                                                                     │
│              [Start Optimization] [Load Previous] [Cancel]          │
└─────────────────────────────────────────────────────────────────────┘
```

#### Pareto Front Visualization
```python
# Optimization results visualization
import matplotlib.pyplot as plt
import numpy as np

def plot_pareto_front(optimization_results):
    """Plot multi-objective optimization Pareto front."""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 10))
    
    # Extract objectives from results
    isp_values = [r['objectives']['specific_impulse'] for r in optimization_results]
    mass_values = [r['objectives']['engine_mass'] for r in optimization_results]
    tw_ratios = [r['objectives']['thrust_to_weight'] for r in optimization_results]
    costs = [r['objectives']['manufacturing_cost'] for r in optimization_results]
    
    # Isp vs. Engine Mass
    scatter1 = ax1.scatter(isp_values, mass_values, c=tw_ratios, 
                          cmap='viridis', alpha=0.6)
    ax1.set_xlabel('Specific Impulse (s)')
    ax1.set_ylabel('Engine Mass (kg)')
    ax1.set_title('Isp vs. Mass (colored by T/W)')
    plt.colorbar(scatter1, ax=ax1, label='Thrust-to-Weight')
    
    # Isp vs. T/W Ratio
    scatter2 = ax2.scatter(isp_values, tw_ratios, c=costs, 
                          cmap='plasma', alpha=0.6)
    ax2.set_xlabel('Specific Impulse (s)')
    ax2.set_ylabel('Thrust-to-Weight Ratio')
    ax2.set_title('Isp vs. T/W (colored by Cost)')
    plt.colorbar(scatter2, ax=ax2, label='Cost ($M)')
    
    # 3D Pareto surface
    from mpl_toolkits.mplot3d import Axes3D
    ax3 = fig.add_subplot(223, projection='3d')
    scatter3 = ax3.scatter(isp_values, tw_ratios, costs, 
                          c=mass_values, cmap='coolwarm', alpha=0.6)
    ax3.set_xlabel('Isp (s)')
    ax3.set_ylabel('T/W Ratio')
    ax3.set_zlabel('Cost ($M)')
    ax3.set_title('3D Pareto Surface')
    
    # Parallel coordinates plot
    from pandas.plotting import parallel_coordinates
    import pandas as pd
    
    df = pd.DataFrame({
        'Isp': isp_values,
        'Mass': mass_values, 
        'T/W': tw_ratios,
        'Cost': costs,
        'Design': range(len(optimization_results))
    })
    
    parallel_coordinates(df, 'Design', ax=ax4, alpha=0.3)
    ax4.set_title('Parallel Coordinates')
    ax4.legend().remove()
    
    plt.tight_layout()
    return fig
```

### Uncertainty Quantification

#### Monte Carlo Analysis
```python
# Uncertainty analysis setup
uncertainty_config = {
    "analysis_type": "monte_carlo",
    "sample_size": 1000,
    "input_uncertainties": {
        "chamber_pressure": {
            "distribution": "normal",
            "mean": 7.0e6,
            "std_dev": 0.2e6,           # ±3% uncertainty
            "bounds": [6.0e6, 8.0e6]
        },
        "mixture_ratio": {
            "distribution": "uniform", 
            "min": 5.8,
            "max": 6.2,                 # ±3% around nominal
        },
        "nozzle_efficiency": {
            "distribution": "beta",
            "alpha": 5,
            "beta": 2,                  # Skewed toward high efficiency
            "bounds": [0.92, 0.98]
        }
    },
    "output_statistics": [
        "mean", "std_dev", "percentiles", 
        "confidence_intervals", "sensitivity_indices"
    ]
}
```

#### Sensitivity Analysis Results
```
Uncertainty Analysis Results: LH2/LOX Engine
┌─────────────────────────────────────────────────────────────────────┐
│  Output Statistics (1000 Monte Carlo samples)                      │
│                                                                     │
│  Specific Impulse (s)                                               │
│  • Mean: 451.2 ± 8.4 s (±1.9%)                                     │
│  • 95% Confidence Interval: [435.7, 466.8] s                       │
│  • Distribution: Approximately normal                               │
│                                                                     │
│  Thrust (N)                                                         │
│  • Mean: 245,800 ± 12,400 N (±5.0%)                                │
│  • 95% Confidence Interval: [222,100, 269,500] N                   │
│  • Distribution: Right-skewed                                      │
│                                                                     │
│  Sensitivity Indices (Sobol)                                       │
│  Input Parameter          First Order    Total Order               │
│  Chamber Pressure         0.42           0.48                       │
│  Mixture Ratio           0.31           0.38                       │
│  Nozzle Efficiency       0.15           0.18                       │
│  Interactions            ---             0.04                       │
│                                                                     │
│  Risk Assessment                                                    │
│  • Probability(Isp < 440s): 12.3%                                  │
│  • Probability(Thrust < 230kN): 8.7%                               │
│  • Overall success probability: 91.3%                              │
└─────────────────────────────────────────────────────────────────────┘
```

## 9. Integration with External Tools

### CAD Integration

#### SolidWorks Plugin Interface
```python
# HRMA SolidWorks integration example
class HRMASolidWorksPlugin:
    """
    SolidWorks plugin for direct CAD-to-HRMA analysis integration.
    
    Features:
    - Extract nozzle geometry from CAD models
    - Generate parametric nozzle designs
    - Update CAD based on optimization results
    """
    
    def extract_nozzle_geometry(self, solidworks_model):
        """Extract nozzle dimensions from SolidWorks model."""
        # Connect to SolidWorks API
        sw_app = win32com.client.Dispatch("SldWorks.Application")
        sw_model = sw_app.ActiveDoc
        
        # Extract key dimensions
        geometry = {
            "throat_diameter": self.get_dimension(sw_model, "throat_dia"),
            "exit_diameter": self.get_dimension(sw_model, "exit_dia"),
            "nozzle_length": self.get_dimension(sw_model, "nozzle_length"),
            "chamber_diameter": self.get_dimension(sw_model, "chamber_dia"),
            "contour_points": self.extract_contour(sw_model)
        }
        
        return geometry
    
    def update_cad_from_optimization(self, sw_model, optimal_design):
        """Update SolidWorks model based on optimization results."""
        for param, value in optimal_design.items():
            if param in ["throat_diameter", "exit_diameter", "nozzle_length"]:
                self.set_dimension(sw_model, param, value)
        
        # Rebuild model
        sw_model.ForceRebuild3(True)
```

#### ANSYS Fluent Integration
```python
# HRMA-to-ANSYS workflow
class ANSYSIntegration:
    """
    Integration with ANSYS Fluent for detailed CFD validation.
    
    Workflow:
    1. Export HRMA nozzle geometry
    2. Generate ANSYS mesh  
    3. Set up boundary conditions
    4. Run CFD simulation
    5. Import results back to HRMA
    """
    
    def generate_fluent_case(self, hrma_results, cfd_settings):
        """Generate ANSYS Fluent case file from HRMA results."""
        case_template = """
        ; ANSYS Fluent Case File Generated by HRMA
        ; Nozzle Analysis: {motor_name}
        
        /define/models/viscous/spalart-allmaras yes
        /define/materials/fluid/air air yes ideal-gas no no no no no
        
        ; Boundary Conditions from HRMA
        /define/boundary-conditions/pressure-inlet inlet yes no {chamber_pressure} no 0 no {chamber_temperature} no no yes 5 10
        /define/boundary-conditions/pressure-outlet outlet yes no {exit_pressure} no {exit_temperature} no no no no
        /define/boundary-conditions/wall wall 0 no 0 no no no 0 no 0 no no
        
        ; Solution settings
        /solve/set/discretization-scheme/pressure 12
        /solve/set/discretization-scheme/momentum 1
        /solve/set/under-relaxation/pressure 0.3
        /solve/set/under-relaxation/momentum 0.7
        
        ; Initialize and solve
        /solve/initialize/compute-defaults/pressure-inlet inlet
        /solve/iterate {iterations}
        """
        
        return case_template.format(
            motor_name=hrma_results["motor_name"],
            chamber_pressure=hrma_results["chamber_pressure"],
            chamber_temperature=hrma_results["chamber_temperature"], 
            exit_pressure=hrma_results["exit_pressure"],
            exit_temperature=hrma_results["exit_temperature"],
            iterations=cfd_settings.get("iterations", 1000)
        )
```

### MATLAB/Simulink Integration
```matlab
% HRMA MATLAB Toolbox Example
function results = hrma_analysis(motor_config)
    % MATLAB interface to HRMA analysis engine
    
    % Set up HTTP request to HRMA API
    url = 'http://localhost:8000/api/v1/analysis/liquid';
    options = weboptions('MediaType', 'application/json', ...
                        'RequestMethod', 'POST', ...
                        'HeaderFields', {'Authorization', 'Bearer YOUR_TOKEN'});
    
    % Send analysis request
    response = webwrite(url, motor_config, options);
    
    % Extract results for MATLAB processing
    results.thrust = response.performance.thrust;
    results.isp = response.performance.specific_impulse;
    results.chamber_pressure = response.conditions.chamber_pressure;
    results.exit_velocity = response.performance.exit_velocity;
    
    % Create MATLAB plots
    figure;
    subplot(2,2,1);
    plot(response.altitude_profile, response.thrust_profile);
    xlabel('Altitude (m)');
    ylabel('Thrust (N)');
    title('Thrust vs Altitude');
    
    subplot(2,2,2);
    plot(response.altitude_profile, response.isp_profile);
    xlabel('Altitude (m)');
    ylabel('Specific Impulse (s)');
    title('Isp vs Altitude');
    
    % Export to Simulink
    assignin('base', 'hrma_thrust_data', response.thrust_profile);
    assignin('base', 'hrma_time_data', response.time_profile);
end
```

## 10. Frequently Asked Questions

### Technical Questions

**Q: What's the difference between effective and theoretical C* values?**
A: Theoretical C* is calculated from perfect chemical equilibrium, while effective C* accounts for real-world losses:
- Combustion inefficiency (incomplete mixing, finite reaction rates)
- Heat transfer losses to chamber walls
- Two-phase flow effects (liquid droplets, particles)
- Boundary layer losses

HRMA uses effective C* values based on NASA test data:
- LH2/LOX: 1580 m/s effective (vs. 2356 m/s theoretical)
- RP-1/LOX: 1715 m/s effective (vs. ~2400 m/s theoretical)

**Q: How accurate are HRMA predictions compared to actual test data?**
A: HRMA accuracy depends on the motor type and configuration:
- Liquid motors: ±3% for thrust, ±2% for Isp (when well-characterized propellants)
- Solid motors: ±5% for thrust, ±3% for Isp (grain geometry dependent)
- Hybrid motors: ±8% for thrust, ±5% for Isp (higher uncertainty due to regression rate)

**Q: Can HRMA handle non-standard propellant combinations?**
A: Yes, HRMA supports:
- Custom propellant formulations using the PropellantBuilder
- Green propellants (hydrogen peroxide, nitrous oxide, etc.)
- Experimental combinations (with reduced accuracy)
- Import of NASA CEA data for validation

### Usage Questions

**Q: What's the recommended workflow for a new motor design?**
A: Follow this systematic approach:
1. Define mission requirements (thrust, Isp, duration)
2. Select appropriate motor type and propellants
3. Perform initial sizing analysis
4. Conduct parametric studies to optimize design
5. Validate results with NASA CEA
6. Generate detailed design documentation
7. Export to CAD for mechanical design

**Q: How do I troubleshoot convergence failures?**
A: Try these steps in order:
1. Check input parameters for physical reasonableness
2. Reduce precision temporarily to identify problematic regions
3. Adjust mixture ratio in smaller steps
4. Use different initial guess values
5. Enable debug logging to identify where convergence fails
6. Contact support with specific error messages

**Q: Can HRMA predict transient motor behavior?**
A: HRMA provides steady-state analysis by default, but includes transient capabilities:
- Solid motors: Burn-back analysis with time-varying thrust
- Liquid motors: Startup/shutdown transients
- Hybrid motors: Fuel regression and performance evolution
- All types: Altitude compensation effects during flight

### Performance Questions

**Q: How can I speed up large parametric studies?**
A: Optimization strategies:
1. Use "medium" precision instead of "high" (5x faster)
2. Disable NASA CEA validation for preliminary studies
3. Enable parallel processing (scales with CPU cores)
4. Use cached propellant data when possible
5. Process in smaller batches to monitor progress
6. Consider cloud computing for very large studies

**Q: What are HRMA's system requirements for large analyses?**
A: For intensive use:
- CPU: 8+ cores recommended for parallel processing
- RAM: 32+ GB for large parametric studies (1000+ cases)
- Storage: SSD recommended, 100+ GB for extensive databases
- Network: Stable connection for NASA CEA validation
- Consider dedicated analysis servers for team environments

### Integration Questions

**Q: How do I integrate HRMA with our existing design workflow?**
A: HRMA provides multiple integration options:
- RESTful API for custom applications
- Python SDK for scripting and automation  
- SolidWorks plugin for direct CAD integration
- MATLAB toolbox for analysis and visualization
- Export capabilities for reports and data sharing

**Q: Can HRMA results be used for flight certification?**
A: HRMA provides engineering estimates suitable for:
- Preliminary design and sizing
- Trade studies and optimization
- Mission planning analysis
- Educational and research purposes

For flight certification, additional validation is required:
- Detailed CFD analysis
- Physical testing and correlation
- Independent verification and validation
- Compliance with applicable safety standards

**Q: How often is HRMA updated with new propellant data?**
A: HRMA follows this update schedule:
- NASA CEA database: Monthly synchronization
- Propellant properties: Quarterly updates
- Software features: Bi-annual releases
- Security patches: As needed
- User can manually import new propellant data anytime

---

This comprehensive User Manual provides step-by-step guidance for using HRMA effectively, from basic analysis to advanced optimization and integration workflows. The manual emphasizes practical usage while maintaining technical accuracy for aerospace engineering applications.