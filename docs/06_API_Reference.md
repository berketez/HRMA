# 🌐 HRMA API Reference
## Complete RESTful API Documentation

> **🎯 "A well-designed API is like a good user interface - it makes complex tasks simple and intuitive"**

---

## 📖 TABLE OF CONTENTS

1. [API Overview](#api-overview)
2. [Authentication & Security](#authentication--security)
3. [Core Analysis Endpoints](#core-analysis-endpoints)
4. [Propellant Data Endpoints](#propellant-data-endpoints)
5. [Validation Endpoints](#validation-endpoints)
6. [Export & Integration Endpoints](#export--integration-endpoints)
7. [Utility Endpoints](#utility-endpoints)
8. [WebSocket API](#websocket-api)
9. [Error Handling](#error-handling)
10. [Rate Limiting & Quotas](#rate-limiting--quotas)

---

## 🏛️ API OVERVIEW

### **Base Information**

```yaml
API Version: v1
Base URL: https://api.hrma.space/v1
Protocol: HTTPS only
Data Format: JSON
Authentication: API Key + JWT (optional)
Rate Limiting: Yes
Status Page: https://status.hrma.space
```

### **OpenAPI Specification**

```json
{
  "openapi": "3.0.3",
  "info": {
    "title": "HRMA API",
    "version": "1.0.0",
    "description": "Hybrid Rocket Motor Analysis API",
    "contact": {
      "name": "HRMA Support",
      "url": "https://github.com/hrma/hrma",
      "email": "support@hrma.space"
    },
    "license": {
      "name": "MIT",
      "url": "https://opensource.org/licenses/MIT"
    }
  },
  "servers": [
    {
      "url": "https://api.hrma.space/v1",
      "description": "Production server"
    },
    {
      "url": "https://staging-api.hrma.space/v1",
      "description": "Staging server"
    }
  ]
}
```

### **Standard Response Format**

All API responses follow a consistent format:

```json
{
  "success": true,
  "data": {},
  "metadata": {
    "request_id": "req_1234567890",
    "timestamp": "2025-08-14T12:00:00Z",
    "processing_time": 1.234,
    "version": "1.0.0"
  },
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 1000,
    "pages": 20
  }
}
```

### **Error Response Format**

```json
{
  "success": false,
  "error": {
    "code": "INVALID_PARAMETERS",
    "message": "One or more parameters are invalid",
    "details": {
      "field": "motor_type",
      "issue": "Must be one of: solid, liquid, hybrid"
    }
  },
  "metadata": {
    "request_id": "req_1234567890",
    "timestamp": "2025-08-14T12:00:00Z"
  }
}
```

---

## 🔐 AUTHENTICATION & SECURITY

### **API Key Authentication**

Include your API key in the request header:

```http
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

### **Getting an API Key**

```bash
curl -X POST https://api.hrma.space/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "organization": "Your Organization",
    "use_case": "Research/Commercial/Educational"
  }'
```

**Response:**
```json
{
  "success": true,
  "data": {
    "api_key": "hrma_live_1234567890abcdef",
    "expires_at": "2026-08-14T12:00:00Z",
    "rate_limit": "1000/hour",
    "features": ["analysis", "validation", "export"]
  }
}
```

### **JWT Token Authentication (Optional)**

For enhanced security, you can use JWT tokens:

```bash
curl -X POST https://api.hrma.space/v1/auth/token \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "expires_in": 3600
  }'
```

### **Security Headers**

All requests should include recommended security headers:

```http
X-API-Version: v1
X-Request-ID: unique-request-identifier
User-Agent: YourApp/1.0.0 (contact@yourcompany.com)
```

---

## 🚀 CORE ANALYSIS ENDPOINTS

### **Motor Analysis**

#### **POST /analysis/motor**

Perform comprehensive rocket motor analysis.

**Request:**
```http
POST /api/v1/analysis/motor
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "motor_type": "solid",
  "parameters": {
    "propellant": {
      "type": "APCP",
      "density": 1800,
      "burn_rate_coefficient": 5.0e-8,
      "pressure_exponent": 0.35
    },
    "grain_geometry": {
      "type": "bates",
      "outer_radius": 0.1,
      "initial_port_radius": 0.02,
      "length": 0.5
    },
    "nozzle": {
      "throat_radius": 0.015,
      "expansion_ratio": 10,
      "type": "conical"
    },
    "operating_conditions": {
      "ambient_pressure": 101325,
      "ambient_temperature": 288.15
    }
  },
  "analysis_options": {
    "validate_with_nasa": true,
    "generate_cad": false,
    "time_step": 0.01,
    "max_burn_time": 30
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "analysis_id": "analysis_1234567890",
    "motor_type": "solid",
    "performance_metrics": {
      "max_thrust": 5000.0,
      "average_thrust": 4200.0,
      "total_impulse": 126000.0,
      "specific_impulse_vacuum": 285.5,
      "specific_impulse_sea_level": 251.2,
      "burn_time": 30.0,
      "chamber_pressure_max": 5.5e6,
      "characteristic_velocity": 1520.0
    },
    "time_history": {
      "time": [0.0, 0.01, 0.02, "..."],
      "thrust": [0.0, 4800.0, 4850.0, "..."],
      "chamber_pressure": [0.0, 5.2e6, 5.3e6, "..."],
      "mass_flow_rate": [0.0, 2.1, 2.15, "..."]
    },
    "geometry_analysis": {
      "initial_port_area": 0.001256,
      "final_port_area": 0.031416,
      "web_burned": 0.08,
      "propellant_mass": 141.37
    },
    "nasa_validation": {
      "validation_status": "excellent",
      "deviations": {
        "specific_impulse": 0.08,
        "characteristic_velocity": 0.05,
        "combustion_temperature": 0.12
      }
    }
  },
  "metadata": {
    "request_id": "req_motor_analysis_001",
    "timestamp": "2025-08-14T12:00:00Z",
    "processing_time": 2.345,
    "version": "1.0.0",
    "analysis_complexity": "standard"
  }
}
```

#### **POST /analysis/liquid**

Liquid rocket engine analysis with detailed subsystem modeling.

**Request:**
```http
POST /api/v1/analysis/liquid
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "propellants": {
    "fuel": "lh2",
    "oxidizer": "lox",
    "mixture_ratio": 6.0
  },
  "performance_requirements": {
    "thrust_vacuum": 2000000,
    "chamber_pressure": 20000000
  },
  "cycle_type": "staged_combustion",
  "design_constraints": {
    "max_mass": 3500,
    "envelope_diameter": 2.5,
    "envelope_length": 5.0
  },
  "analysis_options": {
    "include_feed_system": true,
    "include_cooling": true,
    "include_turbomachinery": true,
    "optimization_target": "specific_impulse"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "analysis_id": "analysis_liquid_001",
    "engine_type": "liquid",
    "performance_prediction": {
      "thrust_vacuum": 2000000.0,
      "thrust_sea_level": 1620000.0,
      "specific_impulse_vacuum": 452.3,
      "specific_impulse_sea_level": 366.2,
      "chamber_pressure": 20000000.0,
      "chamber_temperature": 3357.4,
      "mixture_ratio_actual": 6.0,
      "characteristic_velocity_effective": 1580.0
    },
    "subsystem_analysis": {
      "combustion_chamber": {
        "volume": 0.08,
        "length": 0.6,
        "diameter": 0.4,
        "wall_thickness": 0.008,
        "cooling_method": "regenerative"
      },
      "feed_system": {
        "cycle_type": "staged_combustion",
        "turbopump_power": 28000000,
        "preburner_conditions": {
          "pressure": 25000000,
          "temperature": 650,
          "mixture_ratio": 0.3
        }
      },
      "nozzle": {
        "throat_diameter": 0.12,
        "exit_diameter": 1.8,
        "expansion_ratio": 225,
        "length": 2.2
      }
    },
    "mass_breakdown": {
      "dry_mass": 3177,
      "combustion_chamber": 850,
      "nozzle": 920,
      "turbomachinery": 1200,
      "other": 207
    },
    "nasa_validation": {
      "validation_status": "excellent",
      "reference_engine": "RS-25",
      "deviations": {
        "specific_impulse": 0.02,
        "chamber_pressure": 0.01,
        "mixture_ratio": 0.0
      }
    }
  },
  "metadata": {
    "request_id": "req_liquid_001",
    "timestamp": "2025-08-14T12:00:00Z",
    "processing_time": 8.456,
    "complexity": "high",
    "analysis_features": [
      "thermodynamic_cycle",
      "feed_system",
      "cooling_analysis",
      "nasa_validation"
    ]
  }
}
```

#### **POST /analysis/hybrid**

Hybrid rocket motor analysis with regression rate modeling.

**Request:**
```http
POST /api/v1/analysis/hybrid
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "fuel_grain": {
    "type": "htpb",
    "initial_port_radius": 0.05,
    "outer_radius": 0.15,
    "length": 1.0,
    "density": 920,
    "regression_coefficient": 3.6e-5,
    "mass_flux_exponent": 0.62
  },
  "oxidizer_system": {
    "type": "lox",
    "mass_flow_rate": 5.0,
    "injection_pressure": 3000000,
    "tank_pressure": 3500000
  },
  "injection_system": {
    "type": "axial",
    "number_of_injectors": 8,
    "injection_velocity": 15.0,
    "swirl_number": 0.0
  },
  "operating_profile": {
    "burn_duration": 60.0,
    "throttling": false
  },
  "analysis_options": {
    "regression_model": "enhanced",
    "mixing_analysis": true,
    "port_evolution": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "analysis_id": "analysis_hybrid_001",
    "motor_type": "hybrid",
    "performance_prediction": {
      "average_thrust": 12000.0,
      "total_impulse": 720000.0,
      "specific_impulse_average": 295.0,
      "burn_time": 60.0,
      "propellant_mass_total": 250.0,
      "oxidizer_mass": 300.0,
      "fuel_mass_consumed": 183.7
    },
    "regression_analysis": {
      "initial_regression_rate": 0.4e-3,
      "final_regression_rate": 0.8e-3,
      "average_regression_rate": 0.6e-3,
      "enhancement_factor": 1.0,
      "web_burned": 0.1
    },
    "port_evolution": {
      "initial_port_radius": 0.05,
      "final_port_radius": 0.15,
      "port_area_initial": 0.007854,
      "port_area_final": 0.070686,
      "burning_surface_evolution": {
        "initial": 0.314,
        "final": 0.942,
        "average": 0.628
      }
    },
    "mixture_ratio_evolution": {
      "initial": 8.5,
      "final": 4.2,
      "average": 6.1,
      "optimal_range": [5.5, 7.0]
    },
    "combustion_efficiency": {
      "average": 0.87,
      "factors": {
        "mixing_efficiency": 0.91,
        "residence_time": 0.95,
        "temperature_effects": 1.0
      }
    }
  },
  "metadata": {
    "request_id": "req_hybrid_001",
    "timestamp": "2025-08-14T12:00:00Z",
    "processing_time": 5.678,
    "analysis_features": [
      "regression_modeling",
      "port_evolution",
      "mixture_ratio_shift",
      "combustion_efficiency"
    ]
  }
}
```

### **Batch Analysis**

#### **POST /analysis/batch**

Process multiple motor analyses in a single request.

**Request:**
```http
POST /api/v1/analysis/batch
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "analyses": [
    {
      "id": "config_001",
      "motor_type": "solid",
      "parameters": {}
    },
    {
      "id": "config_002", 
      "motor_type": "solid",
      "parameters": {}
    }
  ],
  "batch_options": {
    "parallel_processing": true,
    "max_concurrent": 5,
    "priority": "normal"
  }
}
```

### **Analysis Status**

#### **GET /analysis/{analysis_id}/status**

Get the status of a running analysis.

**Request:**
```http
GET /api/v1/analysis/analysis_1234567890/status
Authorization: Bearer YOUR_API_KEY
```

**Response:**
```json
{
  "success": true,
  "data": {
    "analysis_id": "analysis_1234567890",
    "status": "completed",
    "progress": 100,
    "current_stage": "nasa_validation",
    "estimated_completion": "2025-08-14T12:02:30Z",
    "started_at": "2025-08-14T12:00:00Z",
    "completed_at": "2025-08-14T12:02:15Z",
    "processing_time": 135.0
  }
}
```

#### **GET /analysis/{analysis_id}/results**

Retrieve completed analysis results.

**Request:**
```http
GET /api/v1/analysis/analysis_1234567890/results
Authorization: Bearer YOUR_API_KEY
```

---

## 🧪 PROPELLANT DATA ENDPOINTS

### **Propellant Database**

#### **GET /propellants**

Get list of available propellants.

**Request:**
```http
GET /api/v1/propellants?type=solid&page=1&per_page=50
Authorization: Bearer YOUR_API_KEY
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "name": "APCP",
      "type": "solid",
      "description": "Ammonium Perchlorate Composite Propellant",
      "classification": "oxidizer_rich",
      "density": 1800,
      "characteristic_velocity": 1520,
      "data_source": "NASA_TP_1999_209380",
      "last_updated": "2025-08-14T12:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 247,
    "pages": 5
  }
}
```

#### **GET /propellants/{propellant_name}**

Get detailed propellant properties.

**Request:**
```http
GET /api/v1/propellants/APCP?temperature=298.15&pressure=101325
Authorization: Bearer YOUR_API_KEY
```

**Response:**
```json
{
  "success": true,
  "data": {
    "name": "APCP",
    "type": "solid",
    "properties": {
      "density": 1800,
      "burn_rate_coefficient": 5.0e-8,
      "pressure_exponent": 0.35,
      "temperature_sensitivity": 0.002,
      "flame_temperature": 3200,
      "molecular_weight": 25.5,
      "gamma": 1.25,
      "characteristic_velocity": 1520
    },
    "composition": {
      "ammonium_perchlorate": 0.68,
      "aluminum": 0.18,
      "binder_htpb": 0.13,
      "additives": 0.01
    },
    "conditions": {
      "temperature": 298.15,
      "pressure": 101325,
      "reference_conditions": true
    },
    "data_quality": {
      "source": "NASA_verified",
      "confidence": "high",
      "last_validated": "2025-08-14T12:00:00Z"
    }
  }
}
```

### **Real-time Propellant Data**

#### **GET /propellants/realtime/{propellant_name}**

Get real-time propellant data from external sources.

**Request:**
```http
GET /api/v1/propellants/realtime/lox?sources=nist,nasa&temperature=90.2
Authorization: Bearer YOUR_API_KEY
```

**Response:**
```json
{
  "success": true,
  "data": {
    "propellant": "lox",
    "sources_queried": ["nist", "nasa"],
    "properties": {
      "density": 1141.7,
      "viscosity": 0.000194,
      "thermal_conductivity": 0.150,
      "specific_heat": 1699,
      "vapor_pressure": 101325
    },
    "source_data": {
      "nist": {
        "status": "success",
        "last_updated": "2025-08-14T11:55:00Z",
        "confidence": "high"
      },
      "nasa": {
        "status": "success", 
        "last_updated": "2025-08-14T11:50:00Z",
        "confidence": "high"
      }
    },
    "data_freshness": "excellent",
    "cache_status": "fresh"
  }
}
```

### **Propellant Combinations**

#### **GET /propellants/combinations**

Get validated propellant combinations.

**Request:**
```http
GET /api/v1/propellants/combinations?motor_type=liquid
Authorization: Bearer YOUR_API_KEY
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "fuel": "lh2",
      "oxidizer": "lox",
      "mixture_ratio_optimal": 6.0,
      "performance": {
        "specific_impulse_vacuum": 452.3,
        "characteristic_velocity": 2356.7,
        "combustion_temperature": 3357.4
      },
      "applications": ["upper_stage", "heavy_lift"],
      "heritage": ["RS-25", "RL-10"],
      "maturity": "operational"
    },
    {
      "fuel": "rp1",
      "oxidizer": "lox", 
      "mixture_ratio_optimal": 2.56,
      "performance": {
        "specific_impulse_vacuum": 353.2,
        "characteristic_velocity": 1823.4,
        "combustion_temperature": 3670.2
      },
      "applications": ["booster", "first_stage"],
      "heritage": ["F-1", "Merlin"],
      "maturity": "operational"
    }
  ]
}
```

---

## ✅ VALIDATION ENDPOINTS

### **NASA CEA Validation**

#### **POST /validation/nasa-cea**

Validate analysis results against NASA CEA.

**Request:**
```http
POST /api/v1/validation/nasa-cea
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "validation_request": {
    "fuel": "rp1",
    "oxidizer": "lox",
    "chamber_pressure": 70,
    "mixture_ratio": 2.56,
    "expansion_ratios": [1, 10, 50, 100]
  },
  "hrma_results": {
    "specific_impulse_vacuum": 353.2,
    "characteristic_velocity": 1715.0,
    "combustion_temperature": 3670.2
  },
  "validation_options": {
    "tolerance_level": "strict",
    "include_statistical_analysis": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "validation_id": "val_cea_001",
    "validation_status": "excellent",
    "overall_deviation": 0.08,
    "cea_results": {
      "specific_impulse_vacuum": 353.48,
      "characteristic_velocity": 1714.2,
      "combustion_temperature": 3674.1,
      "gamma": 1.22,
      "molecular_weight": 22.86
    },
    "comparisons": {
      "specific_impulse_vacuum": {
        "hrma_value": 353.2,
        "cea_value": 353.48,
        "absolute_deviation": -0.28,
        "relative_deviation_percent": -0.08,
        "assessment": "excellent"
      },
      "characteristic_velocity": {
        "hrma_value": 1715.0,
        "cea_value": 1714.2,
        "absolute_deviation": 0.8,
        "relative_deviation_percent": 0.05,
        "assessment": "excellent"
      }
    },
    "statistical_analysis": {
      "mean_deviation": 0.065,
      "standard_deviation": 0.023,
      "confidence_interval_95": [0.04, 0.09],
      "correlation_coefficient": 0.9987
    },
    "validation_metadata": {
      "cea_version": "2.0.43",
      "validation_timestamp": "2025-08-14T12:00:00Z",
      "reference_database": "NASA_thermodynamic_2020"
    }
  }
}
```

### **Historical Motor Validation**

#### **POST /validation/historical**

Validate against historical motor data.

**Request:**
```http
POST /api/v1/validation/historical
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "reference_motor": "F-1",
  "hrma_results": {
    "thrust_sea_level": 6770000,
    "specific_impulse_sea_level": 263,
    "chamber_pressure": 70e5
  },
  "validation_parameters": {
    "tolerance_level": "engineering",
    "include_uncertainty": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "validation_id": "val_hist_f1_001",
    "reference_motor": {
      "name": "F-1",
      "manufacturer": "Rocketdyne",
      "heritage": "Saturn V",
      "data_source": "NASA_historical_records"
    },
    "validation_results": {
      "overall_assessment": "good",
      "thrust_deviation": 0.3,
      "isp_deviation": 1.2,
      "pressure_deviation": 0.8
    },
    "historical_data": {
      "thrust_sea_level": 6770400,
      "specific_impulse_sea_level": 263.3,
      "chamber_pressure": 69.8e5,
      "burn_time": 150,
      "reliability": 0.96
    },
    "uncertainty_analysis": {
      "data_uncertainty": "±2%",
      "measurement_uncertainty": "±1.5%",
      "model_uncertainty": "±1%",
      "combined_uncertainty": "±2.9%"
    }
  }
}
```

### **Validation History**

#### **GET /validation/history**

Get validation history and trends.

**Request:**
```http
GET /api/v1/validation/history?motor_type=liquid&days=30
Authorization: Bearer YOUR_API_KEY
```

**Response:**
```json
{
  "success": true,
  "data": {
    "summary": {
      "total_validations": 1247,
      "average_deviation": 0.12,
      "excellent_rate": 0.78,
      "good_rate": 0.19,
      "poor_rate": 0.03
    },
    "trends": {
      "improvement_trend": "positive",
      "average_deviation_30d": 0.09,
      "average_deviation_90d": 0.15,
      "validation_count_trend": "increasing"
    },
    "recent_validations": [
      {
        "validation_id": "val_001",
        "motor_type": "liquid",
        "status": "excellent",
        "deviation": 0.05,
        "timestamp": "2025-08-14T11:30:00Z"
      }
    ]
  }
}
```

---

## 📤 EXPORT & INTEGRATION ENDPOINTS

### **PDF Report Generation**

#### **POST /export/pdf**

Generate professional PDF reports.

**Request:**
```http
POST /api/v1/export/pdf
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "analysis_id": "analysis_1234567890",
  "report_type": "technical_report",
  "options": {
    "include_charts": true,
    "include_cad_drawings": false,
    "include_validation": true,
    "include_equations": true,
    "format": "US_letter",
    "company_branding": {
      "logo_url": "https://example.com/logo.png",
      "company_name": "Your Company",
      "report_title": "Motor Analysis Report"
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "export_id": "exp_pdf_001",
    "status": "completed",
    "download_url": "https://api.hrma.space/v1/downloads/exp_pdf_001",
    "file_size": 2847392,
    "expires_at": "2025-08-21T12:00:00Z",
    "report_metadata": {
      "pages": 24,
      "charts_included": 8,
      "equations_included": 15,
      "generation_time": 12.3
    }
  }
}
```

### **CAD File Export**

#### **POST /export/cad**

Export 3D CAD models.

**Request:**
```http
POST /api/v1/export/cad
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "analysis_id": "analysis_1234567890",
  "export_format": "step",
  "components": ["motor_case", "nozzle", "grain", "assembly"],
  "options": {
    "units": "metric",
    "precision": "high",
    "include_materials": true,
    "include_assembly": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "export_id": "exp_cad_001",
    "status": "completed",
    "files": [
      {
        "component": "motor_case",
        "format": "step",
        "download_url": "https://api.hrma.space/v1/downloads/motor_case.step",
        "file_size": 1024000
      },
      {
        "component": "nozzle",
        "format": "step", 
        "download_url": "https://api.hrma.space/v1/downloads/nozzle.step",
        "file_size": 768000
      }
    ],
    "assembly_file": {
      "download_url": "https://api.hrma.space/v1/downloads/complete_assembly.step",
      "file_size": 3072000
    }
  }
}
```

### **OpenRocket Integration**

#### **POST /export/openrocket**

Export OpenRocket compatible files.

**Request:**
```http
POST /api/v1/export/openrocket
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "analysis_id": "analysis_1234567890",
  "export_options": {
    "include_motor_file": true,
    "include_thrust_curve": true,
    "motor_designation": "Custom_M_1520",
    "certification_level": "research"
  }
}
```

---

## 🛠️ UTILITY ENDPOINTS

### **Health Check**

#### **GET /health**

Service health check.

**Request:**
```http
GET /api/v1/health
```

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "timestamp": "2025-08-14T12:00:00Z",
    "version": "1.0.0",
    "uptime": 86400,
    "checks": {
      "database": "healthy",
      "nasa_api": "healthy", 
      "nist_api": "healthy",
      "cache": "healthy",
      "disk_space": "healthy"
    },
    "performance": {
      "avg_response_time": "145ms",
      "requests_per_second": 1250,
      "error_rate": 0.003
    }
  }
}
```

### **API Information**

#### **GET /info**

API version and capability information.

**Request:**
```http
GET /api/v1/info
```

**Response:**
```json
{
  "success": true,
  "data": {
    "api_version": "1.0.0",
    "hrma_version": "1.0.0",
    "supported_features": [
      "solid_motor_analysis",
      "liquid_engine_analysis", 
      "hybrid_motor_analysis",
      "nasa_validation",
      "pdf_export",
      "cad_export",
      "batch_processing"
    ],
    "rate_limits": {
      "default": "1000/hour",
      "premium": "10000/hour"
    },
    "supported_formats": {
      "input": ["json"],
      "export": ["pdf", "step", "iges", "stl", "ork"]
    }
  }
}
```

### **Unit Conversion**

#### **POST /utils/convert**

Convert between different unit systems.

**Request:**
```http
POST /api/v1/utils/convert
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "conversions": [
    {
      "value": 1000,
      "from_unit": "N",
      "to_unit": "lbf"
    },
    {
      "value": 300,
      "from_unit": "K",
      "to_unit": "C"
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "conversions": [
      {
        "original_value": 1000,
        "from_unit": "N",
        "converted_value": 224.809,
        "to_unit": "lbf",
        "conversion_factor": 0.224809
      },
      {
        "original_value": 300,
        "from_unit": "K",
        "converted_value": 26.85,
        "to_unit": "C",
        "conversion_type": "temperature"
      }
    ]
  }
}
```

---

## 🔄 WEBSOCKET API

### **Connection**

Connect to real-time analysis updates:

```javascript
const ws = new WebSocket('wss://api.hrma.space/v1/realtime');

// Authentication
ws.onopen = function(event) {
    ws.send(JSON.stringify({
        type: 'auth',
        token: 'YOUR_API_KEY'
    }));
};
```

### **Real-time Analysis**

```javascript
// Start analysis
ws.send(JSON.stringify({
    type: 'start_analysis',
    data: {
        motor_type: 'solid',
        parameters: {
            // Motor parameters
        }
    }
}));

// Listen for progress updates
ws.onmessage = function(event) {
    const message = JSON.parse(event.data);
    
    switch(message.type) {
        case 'analysis_progress':
            console.log(`Progress: ${message.data.progress}%`);
            console.log(`Stage: ${message.data.stage}`);
            break;
            
        case 'analysis_complete':
            console.log('Analysis completed');
            console.log(message.data.results);
            break;
            
        case 'analysis_error':
            console.error('Analysis failed:', message.data.error);
            break;
    }
};
```

### **Message Types**

| Message Type | Direction | Description |
|-------------|-----------|-------------|
| `auth` | Client → Server | Authentication |
| `start_analysis` | Client → Server | Start motor analysis |
| `analysis_progress` | Server → Client | Progress updates |
| `analysis_complete` | Server → Client | Analysis results |
| `analysis_error` | Server → Client | Error notifications |
| `heartbeat` | Bidirectional | Connection keepalive |

---

## ❌ ERROR HANDLING

### **Error Codes**

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INVALID_API_KEY` | 401 | Invalid or missing API key |
| `RATE_LIMIT_EXCEEDED` | 429 | Rate limit exceeded |
| `INVALID_PARAMETERS` | 400 | Invalid request parameters |
| `ANALYSIS_FAILED` | 422 | Analysis execution failed |
| `NASA_VALIDATION_FAILED` | 422 | NASA CEA validation failed |
| `EXPORT_FAILED` | 422 | Export generation failed |
| `PROPELLANT_NOT_FOUND` | 404 | Propellant not in database |
| `INTERNAL_ERROR` | 500 | Internal server error |

### **Error Response Examples**

#### **Invalid Parameters**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_PARAMETERS",
    "message": "Motor type must be specified",
    "details": {
      "field": "motor_type",
      "provided": null,
      "expected": "solid|liquid|hybrid"
    }
  },
  "metadata": {
    "request_id": "req_error_001",
    "timestamp": "2025-08-14T12:00:00Z"
  }
}
```

#### **Analysis Failed**
```json
{
  "success": false,
  "error": {
    "code": "ANALYSIS_FAILED", 
    "message": "Combustion analysis convergence failed",
    "details": {
      "stage": "combustion_analysis",
      "iterations": 1000,
      "convergence_error": 0.01,
      "suggested_fix": "Reduce mixture ratio or increase chamber pressure"
    }
  }
}
```

### **Error Handling Best Practices**

1. **Always check the `success` field**
2. **Use `error.code` for programmatic handling**
3. **Display `error.message` to users**
4. **Log `request_id` for support requests**
5. **Implement exponential backoff for retries**

---

## 🚦 RATE LIMITING & QUOTAS

### **Rate Limits**

| Tier | Requests/Hour | Concurrent | Analysis/Day |
|------|---------------|------------|--------------|
| **Free** | 100 | 2 | 10 |
| **Developer** | 1,000 | 5 | 100 |
| **Professional** | 10,000 | 20 | 1,000 |
| **Enterprise** | Unlimited | 100 | Unlimited |

### **Rate Limit Headers**

```http
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1692014400
X-RateLimit-Retry-After: 3600
```

### **Rate Limit Exceeded Response**

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded",
    "details": {
      "limit": 1000,
      "window": "1 hour",
      "retry_after": 3600,
      "current_usage": 1000
    }
  }
}
```

### **Best Practices**

1. **Monitor rate limit headers**
2. **Implement exponential backoff**
3. **Cache responses when possible**
4. **Use batch endpoints for multiple operations**
5. **Consider WebSocket for real-time updates**

---

## 📊 API USAGE EXAMPLES

### **Python SDK Example**

```python
import hrma

# Initialize client
client = hrma.Client(api_key="YOUR_API_KEY")

# Analyze solid motor
result = client.analyze_motor(
    motor_type="solid",
    parameters={
        "propellant": {"type": "APCP"},
        "grain_geometry": {
            "type": "bates",
            "outer_radius": 0.1,
            "initial_port_radius": 0.02,
            "length": 0.5
        },
        "nozzle": {
            "throat_radius": 0.015,
            "expansion_ratio": 10
        }
    },
    validate_with_nasa=True
)

print(f"Max Thrust: {result['performance_metrics']['max_thrust']} N")
print(f"Specific Impulse: {result['performance_metrics']['specific_impulse_vacuum']} s")
```

### **JavaScript Example**

```javascript
const HRMA = require('hrma-js');

const client = new HRMA.Client('YOUR_API_KEY');

async function analyzeMotor() {
    try {
        const result = await client.analyzeLiquidEngine({
            propellants: {
                fuel: 'lh2',
                oxidizer: 'lox',
                mixture_ratio: 6.0
            },
            performance_requirements: {
                thrust_vacuum: 2000000,
                chamber_pressure: 20000000
            },
            cycle_type: 'staged_combustion'
        });
        
        console.log('Analysis completed:', result.analysis_id);
        console.log('Specific Impulse:', result.performance_prediction.specific_impulse_vacuum);
        
    } catch (error) {
        console.error('Analysis failed:', error.message);
    }
}

analyzeMotor();
```

### **cURL Examples**

#### **Basic Analysis**
```bash
curl -X POST https://api.hrma.space/v1/analysis/motor \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "motor_type": "solid",
    "parameters": {
      "propellant": {"type": "APCP"},
      "grain_geometry": {
        "type": "bates",
        "outer_radius": 0.1,
        "initial_port_radius": 0.02,
        "length": 0.5
      }
    }
  }'
```

#### **Get Propellant Properties**
```bash
curl "https://api.hrma.space/v1/propellants/APCP?temperature=298.15" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## 📋 CONCLUSION

The HRMA API provides **comprehensive programmatic access** to all rocket motor analysis capabilities with:

### **Key Strengths**

- ✅ **RESTful Design** - Industry standard REST architecture
- ✅ **Comprehensive Coverage** - All HRMA features accessible via API
- ✅ **Real-time Updates** - WebSocket support for long-running analyses  
- ✅ **NASA Validation** - Built-in validation against reference standards
- ✅ **Professional Exports** - PDF reports and CAD files
- ✅ **Developer Friendly** - SDKs, clear documentation, examples

### **Performance & Reliability**

- ✅ **High Throughput** - 1250+ requests/second capacity
- ✅ **Low Latency** - Sub-second response times
- ✅ **99.9% Uptime** - Production-grade reliability
- ✅ **Global CDN** - Worldwide low-latency access

### **Enterprise Ready**

- ✅ **Authentication & Security** - API keys, JWT, HTTPS
- ✅ **Rate Limiting** - Fair usage policies
- ✅ **Monitoring** - Comprehensive health checks
- ✅ **Support** - Technical support and SLA options

The HRMA API enables **seamless integration** of rocket motor analysis into any workflow, from research projects to commercial applications.

---

> **"A well-designed API is like a good contract - clear expectations, reliable performance, and mutual benefit."**  
> — HRMA API Team

**Documentation Date**: August 14, 2025  
**Version**: 1.0  
**Status**: Living Document - Updated with each API release

---