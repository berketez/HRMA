# Database & API Modules Documentation

## 1. database_integrations.py

### Overview
Central database management system for all HRMA data persistence and retrieval operations.

### Key Classes

#### `DatabaseManager`
Main database interface class handling all database operations.

##### Methods:
- **`__init__(db_path='experimental_data.db')`**
  - Initializes SQLite connection
  - Creates tables if not exists
  - Sets up connection pooling

- **`save_analysis_results(analysis_type, data, metadata)`**
  - Stores analysis results with timestamps
  - Parameters:
    - `analysis_type`: 'solid', 'liquid', 'hybrid'
    - `data`: Result dictionary
    - `metadata`: User info, version, notes
  - Returns: Record ID

- **`get_analysis_history(user_id=None, limit=100)`**
  - Retrieves past analyses
  - Supports filtering by user
  - Pagination support

- **`export_to_csv(query_params, filename)`**
  - Exports query results to CSV
  - Includes headers and metadata

- **`import_experimental_data(file_path, data_type)`**
  - Imports test data from external files
  - Validates data format
  - Maps to internal schema

### Database Schema
```sql
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    analysis_type TEXT,
    input_params TEXT,
    results TEXT,
    user_id TEXT,
    version TEXT
);

CREATE TABLE propellants (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE,
    formula TEXT,
    properties TEXT,
    source TEXT,
    validated BOOLEAN
);

CREATE TABLE test_data (
    id INTEGER PRIMARY KEY,
    test_date DATETIME,
    motor_type TEXT,
    test_conditions TEXT,
    measurements TEXT,
    notes TEXT
);
```

---

## 2. propellant_database.py

### Overview
Comprehensive propellant properties database with caching and interpolation capabilities.

### Key Components

#### `PropellantDatabase` Class

##### Core Methods:
- **`get_propellant(name, temperature=298.15, pressure=101.325)`**
  - Retrieves propellant properties
  - Temperature/pressure corrections
  - Returns: Property dictionary

- **`add_custom_propellant(properties_dict)`**
  - Adds user-defined propellants
  - Validation against schema
  - Persistence to database

- **`search_propellants(criteria)`**
  - Search by multiple parameters
  - Fuzzy matching support
  - Returns: List of matches

- **`get_mixture_properties(components, ratios)`**
  - Calculates mixture properties
  - Rule of mixtures
  - Non-ideal corrections

### Propellant Properties Structure
```python
{
    'name': 'HTPB',
    'formula': 'C7H10',
    'density': 920,  # kg/m³
    'heat_of_formation': -50000,  # J/mol
    'specific_heat': 1800,  # J/kg·K
    'thermal_conductivity': 0.25,  # W/m·K
    'viscosity': 40,  # Pa·s at 298K
    'surface_tension': 0.03,  # N/m
    'burn_rate_coefficient': 0.005,
    'burn_rate_exponent': 0.35,
    'temperature_sensitivity': 0.002,
    'categories': ['fuel', 'solid', 'polymer']
}
```

### Caching System
- **Memory Cache:** Recently accessed propellants
- **Disk Cache:** Serialized pickle files in `propellant_cache/`
- **Cache Invalidation:** Temperature/pressure based
- **Cache Statistics:** Hit rate monitoring

---

## 3. chemical_database.py

### Overview
Chemical species thermodynamic and transport properties database.

### Key Features

#### `ChemicalDatabase` Class

##### Primary Methods:
- **`get_species(formula, phase='gas')`**
  - NASA polynomial coefficients
  - Phase: 'gas', 'liquid', 'solid'
  - Temperature range validation

- **`calculate_enthalpy(species, temperature)`**
  - Uses NASA 7-coefficient polynomials
  - Automatic range selection
  - Returns: H in J/mol

- **`calculate_entropy(species, temperature)`**
  - Standard entropy calculation
  - Returns: S in J/mol·K

- **`get_gibbs_energy(species, T, P)`**
  - Gibbs free energy
  - Pressure corrections
  - Returns: G in J/mol

### NASA Polynomial Format
```python
{
    'H2O': {
        'phase': 'gas',
        'mw': 18.015,
        'T_ranges': [(200, 1000), (1000, 6000)],
        'coefficients': {
            'low': [4.198, -2.036e-3, 6.520e-6, -5.487e-9, 1.771e-12, -30293.7, -0.849],
            'high': [2.677, 2.973e-3, -7.737e-7, 9.443e-11, -4.269e-15, -29885.9, 6.887]
        }
    }
}
```

---

## 4. external_data_fetcher.py

### Overview
External API integration for real-time data retrieval.

### Key Functions

#### `DataFetcher` Class

##### Methods:
- **`fetch_atmospheric_data(altitude, latitude, longitude)`**
  - Weather/atmospheric conditions
  - APIs: OpenWeatherMap, NOAA
  - Returns: Pressure, temperature, density

- **`get_material_properties(material_name, temperature=None)`**
  - Material database queries
  - Sources: MatWeb, NIST
  - Caching enabled

- **`fetch_nasa_cea_data(propellants, conditions)`**
  - NASA CEA web interface
  - Automated form submission
  - Result parsing

- **`get_launch_site_data(site_name)`**
  - Launch site conditions
  - Elevation, coordinates
  - Historical weather

### API Configuration
```python
API_KEYS = {
    'openweather': 'your_key_here',
    'nasa': 'public_access',
    'nist': 'registered_user'
}

RATE_LIMITS = {
    'openweather': 60,  # calls/minute
    'nasa': 10,
    'nist': 100
}
```

---

## 5. web_propellant_api.py

### Overview
RESTful API for propellant data serving.

### API Endpoints

#### `PropellantAPI` Class

##### Routes:
- **`GET /api/propellants`**
  - List all propellants
  - Pagination: `?page=1&limit=20`
  - Filtering: `?type=solid&category=fuel`

- **`GET /api/propellants/{name}`**
  - Specific propellant details
  - Temperature/pressure params
  - Format: JSON or XML

- **`POST /api/propellants/calculate`**
  - Mixture calculations
  - Body: Component list with ratios
  - Returns: Calculated properties

- **`GET /api/propellants/search`**
  - Search functionality
  - Query: `?q=ammonium`
  - Fuzzy matching enabled

### Response Format
```json
{
    "status": "success",
    "data": {
        "propellant": {
            "name": "AP",
            "properties": {...}
        }
    },
    "meta": {
        "version": "1.0",
        "timestamp": "2025-01-01T00:00:00Z"
    }
}
```

---

## 6. open_source_propellant_api.py

### Overview
Community-driven propellant database with contribution system.

### Key Features

#### `OpenSourcePropellantAPI` Class

##### Core Functions:
- **`submit_propellant(data, contributor_info)`**
  - Community submissions
  - Peer review queue
  - Version tracking

- **`validate_submission(submission_id, validator_id)`**
  - Expert validation
  - Comments and corrections
  - Approval workflow

- **`get_community_propellants(status='approved')`**
  - Browse submissions
  - Status: 'pending', 'approved', 'rejected'
  - Sort by rating/downloads

- **`rate_propellant(propellant_id, rating, comment)`**
  - User feedback system
  - 1-5 star rating
  - Usage reports

### Contribution Workflow
1. **Submission**: User submits new propellant data
2. **Validation**: Auto-validation checks
3. **Review**: Community expert review
4. **Testing**: Optional experimental validation
5. **Approval**: Admin final approval
6. **Publication**: Added to public database

### Data Validation Rules
- Chemical formula verification
- Property range checks
- Unit consistency
- Source citation required
- Duplicate detection

---

## Usage Examples

### Database Integration
```python
from database_integrations import DatabaseManager

db = DatabaseManager()
result_id = db.save_analysis_results(
    analysis_type='hybrid',
    data={'thrust': 5000, 'isp': 250},
    metadata={'user': 'test_user'}
)
```

### Propellant Lookup
```python
from propellant_database import propellant_db

htpb = propellant_db.get_propellant('HTPB', temperature=300)
print(f"Density: {htpb['density']} kg/m³")
```

### External Data
```python
from external_data_fetcher import data_fetcher

atmosphere = data_fetcher.fetch_atmospheric_data(
    altitude=10000,  # meters
    latitude=28.5,
    longitude=-80.5
)
```

### API Usage
```python
from web_propellant_api import propellant_api

# Search for propellants
results = propellant_api.search('perchlorate')

# Calculate mixture
mixture = propellant_api.calculate_mixture({
    'AP': 0.7,
    'HTPB': 0.15,
    'Al': 0.15
})
```

---

## Performance Considerations

### Caching Strategy
- **L1 Cache**: In-memory (recent queries)
- **L2 Cache**: Disk-based (frequent queries)
- **L3 Cache**: Database (all queries)

### Optimization Tips
1. Batch database queries when possible
2. Use connection pooling for concurrent access
3. Implement lazy loading for large datasets
4. Enable compression for API responses
5. Use indexed columns for frequent searches

### Error Handling
- Graceful degradation for API failures
- Fallback to cached data when offline
- Validation before database writes
- Transaction rollback on errors
- Detailed logging for debugging