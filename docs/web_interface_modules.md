# Web Interface Modules Documentation

## 1. app.py - Main Flask Application

### Overview
Central Flask web server that handles all HTTP requests, API endpoints, and serves the web interface for the HRMA system.

### Application Structure

#### Flask App Initialization
```python
app = Flask(__name__)
CORS(app)  # Enable cross-origin requests
```

### Key Routes and Endpoints

#### Main Pages

- **`@app.route('/')`**
  - Landing page
  - Motor type selection
  - Quick start guides

- **`@app.route('/solid')`**
  - Solid rocket motor interface
  - BATES grain calculator
  - Burn rate analysis

- **`@app.route('/liquid')`**
  - Liquid engine interface
  - Bipropellant selection
  - Cooling system design

- **`@app.route('/hybrid')`**
  - Hybrid motor interface
  - Regression rate calculator
  - Port geometry evolution

- **`@app.route('/advanced')`**
  - Advanced analysis tools
  - Multi-parameter optimization
  - Comparative analysis

#### API Endpoints

##### Analysis Endpoints

- **`@app.route('/api/analyze/solid', methods=['POST'])`**
  ```python
  def analyze_solid():
      data = request.json
      engine = SolidRocketEngine(**data)
      results = engine.analyze()
      return jsonify(sanitize_json_values(results))
  ```

- **`@app.route('/api/analyze/liquid', methods=['POST'])`**
  ```python
  def analyze_liquid():
      data = request.json
      engine = LiquidRocketEngine(**data)
      results = engine.analyze()
      return jsonify(sanitize_json_values(results))
  ```

- **`@app.route('/api/analyze/hybrid', methods=['POST'])`**
  ```python
  def analyze_hybrid():
      data = request.json
      engine = HybridRocketEngine(**data)
      results = engine.analyze()
      return jsonify(sanitize_json_values(results))
  ```

##### Data Management

- **`@app.route('/api/save', methods=['POST'])`**
  - Save analysis to database
  - User session management
  - Version control

- **`@app.route('/api/load/<analysis_id>')`**
  - Load previous analysis
  - Permission checking
  - Data validation

- **`@app.route('/api/export/<format>', methods=['POST'])`**
  - Export results
  - Formats: PDF, CSV, JSON, ORK
  - Async processing for large files

##### Visualization

- **`@app.route('/api/plot/<plot_type>', methods=['POST'])`**
  - Generate plots
  - Types: motor, performance, thermal, structural
  - Returns base64 encoded images or Plotly JSON

##### Propellant Database

- **`@app.route('/api/propellants')`**
  - List available propellants
  - Search and filter
  - Custom propellant support

- **`@app.route('/api/propellant/<name>')`**
  - Get specific propellant properties
  - Temperature/pressure corrections
  - Source citations

### Helper Functions

#### `sanitize_json_values(obj)`
```python
def sanitize_json_values(obj):
    """Handle NaN, Infinity, and NumPy arrays in JSON"""
    if isinstance(obj, dict):
        return {k: sanitize_json_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_json_values(item) for item in obj]
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif np.isnan(obj) or np.isinf(obj):
        return None
    return obj
```

#### `validate_request_data(data, schema)`
```python
def validate_request_data(data, schema):
    """Validate incoming request data against schema"""
    required_fields = schema.get('required', [])
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")
    return True
```

### Error Handling
```python
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(ValueError)
def value_error(error):
    return jsonify({'error': str(error)}), 400
```

---

## 2. HTML Templates

### templates/index.html
Main landing page with motor type selection.

#### Key Sections:
```html
<!-- Header -->
<div class="header">
    <h1>HRMA - Hybrid Rocket Motor Analysis</h1>
    <p>Professional Design & Analysis Platform</p>
</div>

<!-- Motor Type Selection -->
<div class="motor-selection">
    <div class="motor-card" onclick="location.href='/solid'">
        <h2>Solid Motor</h2>
        <p>APCP, HTPB propellants</p>
    </div>
    <div class="motor-card" onclick="location.href='/liquid'">
        <h2>Liquid Engine</h2>
        <p>Bipropellant systems</p>
    </div>
    <div class="motor-card" onclick="location.href='/hybrid'">
        <h2>Hybrid Motor</h2>
        <p>Solid fuel + liquid oxidizer</p>
    </div>
</div>
```

### templates/advanced.html
Advanced analysis interface with comprehensive controls.

#### Features:
- Multi-tab interface
- Real-time validation
- Interactive parameter adjustment
- Live result updates
- Export options

```html
<!-- Tab Navigation -->
<ul class="nav nav-tabs">
    <li><a data-toggle="tab" href="#performance">Performance</a></li>
    <li><a data-toggle="tab" href="#thermal">Thermal</a></li>
    <li><a data-toggle="tab" href="#structural">Structural</a></li>
    <li><a data-toggle="tab" href="#trajectory">Trajectory</a></li>
</ul>

<!-- Parameter Input Forms -->
<div class="tab-content">
    <div id="performance" class="tab-pane">
        <!-- Performance parameters -->
    </div>
</div>
```

### templates/solid.html
Solid rocket motor specific interface.

#### Unique Elements:
- Grain geometry selector
- Burn rate calculator
- Pressure-time curves
- Grain regression visualization

### templates/liquid.html
Liquid engine specific interface.

#### Unique Elements:
- Propellant combination matrix
- Injector pattern designer
- Cooling channel calculator
- Turbopump specifications

### templates/formulas.html
Reference page with equations and calculations.

#### Content:
- Tsiolkovsky equation
- Thrust equations
- Heat transfer formulas
- Structural calculations
- Unit conversions

---

## 3. JavaScript (static/js/app.js)

### Overview
Client-side JavaScript for interactivity and AJAX communication.

### Key Functions

#### API Communication

```javascript
async function analyzeMotor(motorType, parameters) {
    try {
        const response = await fetch(`/api/analyze/${motorType}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(parameters)
        });
        const data = await response.json();
        displayResults(data);
    } catch (error) {
        showError('Analysis failed: ' + error.message);
    }
}
```

#### Form Handling

```javascript
function collectFormData(formId) {
    const form = document.getElementById(formId);
    const formData = new FormData(form);
    const data = {};
    
    formData.forEach((value, key) => {
        // Handle numeric inputs
        if (!isNaN(value) && value !== '') {
            data[key] = parseFloat(value);
        } else {
            data[key] = value;
        }
    });
    
    return data;
}
```

#### Dynamic UI Updates

```javascript
function updateInjectorParams() {
    const injectorType = document.getElementById('injector_type').value;
    const paramsDiv = document.getElementById('injectorParams');
    
    // Clear existing parameters
    paramsDiv.innerHTML = '';
    
    // Add type-specific parameters
    if (injectorType === 'showerhead') {
        paramsDiv.innerHTML = `
            <label>Number of Holes</label>
            <input type="number" id="n_holes" value="50">
            <label>Hole Diameter (mm)</label>
            <input type="number" id="hole_diameter" value="2">
        `;
    }
    // ... other injector types
}
```

#### Real-time Validation

```javascript
function validateInput(element) {
    const value = parseFloat(element.value);
    const min = parseFloat(element.getAttribute('data-min'));
    const max = parseFloat(element.getAttribute('data-max'));
    
    if (value < min || value > max) {
        element.classList.add('error');
        showWarning(`Value must be between ${min} and ${max}`);
        return false;
    }
    
    element.classList.remove('error');
    return true;
}
```

#### Chart Rendering

```javascript
function renderChart(chartData, containerId) {
    const layout = {
        title: chartData.title,
        xaxis: { title: chartData.xLabel },
        yaxis: { title: chartData.yLabel },
        showlegend: true
    };
    
    Plotly.newPlot(containerId, chartData.traces, layout);
}
```

#### Export Functions

```javascript
async function exportResults(format) {
    const results = getCurrentResults();
    
    const response = await fetch(`/api/export/${format}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(results)
    });
    
    if (format === 'pdf' || format === 'csv') {
        // Download file
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `analysis.${format}`;
        a.click();
    }
}
```

---

## 4. CSS Styling (static/css/style.css)

### Overview
Comprehensive styling for the web interface with responsive design.

### Key Styles

#### Layout Structure
```css
body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: #f5f6fa;
    color: #2c3e50;
    margin: 0;
    padding: 0;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

.header {
    background: linear-gradient(135deg, #3498db 0%, #2980b9 100%);
    padding: 30px;
    text-align: center;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
}
```

#### Form Styling
```css
.form-group {
    margin-bottom: 20px;
}

.form-control {
    width: 100%;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 14px;
}

.form-control:focus {
    border-color: #3498db;
    outline: none;
    box-shadow: 0 0 5px rgba(52, 152, 219, 0.3);
}

.form-control.error {
    border-color: #e74c3c;
    background-color: #fff5f5;
}
```

#### Buttons
```css
.btn {
    padding: 10px 20px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.3s;
}

.btn-primary {
    background: #3498db;
    color: white;
}

.btn-primary:hover {
    background: #2980b9;
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}

.btn-success {
    background: #27ae60;
    color: white;
}

.btn-danger {
    background: #e74c3c;
    color: white;
}
```

#### Cards and Panels
```css
.card {
    background: white;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 20px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.card-header {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 15px;
    padding-bottom: 10px;
    border-bottom: 2px solid #ecf0f1;
}
```

#### Responsive Design
```css
@media (max-width: 768px) {
    .container {
        padding: 10px;
    }
    
    .grid-2 {
        grid-template-columns: 1fr;
    }
    
    .header h1 {
        font-size: 24px;
    }
    
    .btn {
        width: 100%;
        margin-bottom: 10px;
    }
}
```

#### Animation Effects
```css
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
}

.fade-in {
    animation: fadeIn 0.5s ease-out;
}

.spinner {
    border: 3px solid #f3f3f3;
    border-top: 3px solid #3498db;
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
```

---

## 5. Additional Web Components

### Session Management
```python
# In app.py
from flask import session

app.secret_key = 'your-secret-key-here'

@app.route('/api/session/save', methods=['POST'])
def save_to_session():
    data = request.json
    session['analysis_data'] = data
    return jsonify({'status': 'saved'})

@app.route('/api/session/load')
def load_from_session():
    data = session.get('analysis_data', {})
    return jsonify(data)
```

### WebSocket Support (Optional)
```javascript
// Real-time updates
const socket = new WebSocket('ws://localhost:5000/ws');

socket.onmessage = function(event) {
    const data = JSON.parse(event.data);
    updateDashboard(data);
};

socket.onerror = function(error) {
    console.error('WebSocket error:', error);
};
```

### Progressive Web App Features
```json
// manifest.json
{
    "name": "HRMA - Rocket Motor Analysis",
    "short_name": "HRMA",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#f5f6fa",
    "theme_color": "#3498db",
    "icons": [
        {
            "src": "/static/icon-192.png",
            "sizes": "192x192",
            "type": "image/png"
        }
    ]
}
```

---

## Security Considerations

### Input Sanitization
```python
from flask import escape

def sanitize_input(user_input):
    # Remove HTML tags
    cleaned = escape(user_input)
    # Additional validation
    if len(cleaned) > 1000:
        raise ValueError("Input too long")
    return cleaned
```

### Rate Limiting
```python
from flask_limiter import Limiter

limiter = Limiter(
    app,
    key_func=lambda: request.remote_addr,
    default_limits=["100 per hour"]
)

@app.route('/api/analyze/hybrid')
@limiter.limit("10 per minute")
def analyze_hybrid():
    # Analysis code
    pass
```

### CSRF Protection
```python
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

# In JavaScript
fetch('/api/analyze', {
    headers: {
        'X-CSRFToken': getCookie('csrf_token')
    }
})
```