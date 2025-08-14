# Export & Reporting Modules Documentation

## 1. pdf_generator.py

### Overview
Professional PDF report generation system for rocket motor analysis results with charts, tables, and technical drawings.

### Key Classes

#### `PDFReportGenerator`

##### Core Methods:

- **`__init__(report_config=None)`**
  - Initializes report generator
  - Sets up styles and templates
  - Configures page layout

- **`generate_report(analysis_data, output_path, report_type='full')`**
  - Main report generation method
  - Parameters:
    - `analysis_data`: Complete analysis results
    - `output_path`: PDF file destination
    - `report_type`: 'full', 'summary', 'technical'
  - Returns: File path of generated PDF

- **`add_cover_page(title, subtitle, author, date)`**
  - Creates professional cover page
  - Company branding
  - Document metadata

- **`add_executive_summary(key_results)`**
  - High-level results overview
  - Key performance metrics
  - Design recommendations

- **`add_technical_section(section_data)`**
  - Detailed technical data
  - Equations and calculations
  - Supporting charts

- **`add_charts(plot_data, chart_type)`**
  - Embeds Plotly charts as images
  - Chart types: 'performance', 'thermal', 'structural'
  - Auto-scaling and positioning

- **`add_data_tables(table_data, format_style)`**
  - Formatted data tables
  - Styles: 'grid', 'simple', 'professional'
  - Automatic pagination

- **`add_appendix(supplementary_data)`**
  - Reference data
  - Assumptions and limitations
  - Nomenclature

### Report Sections Structure
```python
report_structure = {
    'cover': {
        'title': 'Rocket Motor Analysis Report',
        'subtitle': 'Design Configuration #001',
        'date': datetime.now(),
        'logo': 'assets/logo.png'
    },
    'summary': {
        'motor_type': 'Hybrid',
        'thrust': '5000 N',
        'burn_time': '10 s',
        'total_impulse': '50000 N·s'
    },
    'sections': [
        {
            'title': 'Performance Analysis',
            'content': [...],
            'charts': [...],
            'tables': [...]
        },
        {
            'title': 'Thermal Analysis',
            'content': [...],
            'charts': [...]
        }
    ],
    'appendices': [...]
}
```

### Styling Configuration
```python
styles = {
    'title': ParagraphStyle(
        'CustomTitle',
        fontSize=24,
        textColor=colors.HexColor('#2C3E50'),
        alignment=TA_CENTER,
        spaceAfter=30
    ),
    'heading1': ParagraphStyle(
        'Heading1',
        fontSize=18,
        textColor=colors.HexColor('#34495E'),
        spaceBefore=12,
        spaceAfter=6
    ),
    'body': ParagraphStyle(
        'BodyText',
        fontSize=11,
        leading=14,
        alignment=TA_LEFT
    )
}
```

### Table Formatting
```python
table_style = TableStyle([
    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, 0), 12),
    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
    ('GRID', (0, 0), (-1, -1), 1, colors.black)
])
```

---

## 2. openrocket_integration.py

### Overview
Integration module for OpenRocket file format (.ork) import/export, enabling interoperability with the popular open-source rocket simulation software.

### Key Classes

#### `OpenRocketExporter`

##### Primary Methods:

- **`__init__(motor_data)`**
  - Initializes with motor analysis data
  - Sets up XML structure
  - Validates data completeness

- **`export_to_ork(output_path, include_simulation=True)`**
  - Exports to OpenRocket format
  - Parameters:
    - `output_path`: .ork file destination
    - `include_simulation`: Add simulation data
  - Returns: Success status

- **`create_motor_definition()`**
  - Generates motor XML element
  - Thrust curve data
  - Propellant properties
  - Physical dimensions

- **`create_rocket_design()`**
  - Complete rocket structure
  - Component tree
  - Mass properties
  - Aerodynamic surfaces

- **`add_thrust_curve(time_data, thrust_data)`**
  - Time-thrust data points
  - Interpolation settings
  - Total impulse calculation

- **`import_from_ork(file_path)`**
  - Reads OpenRocket files
  - Extracts motor data
  - Maps to internal format

### OpenRocket XML Structure
```xml
<openrocket version="1.9">
    <rocket>
        <name>HRMA Motor Design</name>
        <motor>
            <manufacturer>UZAYTEK</manufacturer>
            <designation>UT-5000</designation>
            <diameter unit="m">0.100</diameter>
            <length unit="m">0.500</length>
            <propellant>
                <type>hybrid</type>
                <mass unit="kg">2.5</mass>
            </propellant>
            <thrust-curve>
                <data-point t="0.0" thrust="0.0"/>
                <data-point t="0.1" thrust="4500.0"/>
                <data-point t="5.0" thrust="5000.0"/>
                <data-point t="10.0" thrust="0.0"/>
            </thrust-curve>
        </motor>
    </rocket>
</openrocket>
```

### Data Mapping
```python
mapping = {
    'hrma_to_ork': {
        'chamber_diameter': 'motor.diameter',
        'chamber_length': 'motor.length',
        'propellant_mass': 'motor.propellant.mass',
        'thrust_curve': 'motor.thrust_curve',
        'burn_time': 'motor.burn_time'
    },
    'ork_to_hrma': {
        'motor.diameter': 'chamber_diameter',
        'motor.length': 'chamber_length',
        'motor.propellant.mass': 'propellant_mass'
    }
}
```

### Simulation Data Export
```python
simulation_data = {
    'launch_conditions': {
        'altitude': 0,
        'temperature': 288.15,
        'pressure': 101325,
        'wind_speed': 0
    },
    'flight_events': [
        {'time': 0, 'event': 'ignition'},
        {'time': 10, 'event': 'burnout'},
        {'time': 25, 'event': 'apogee'},
        {'time': 60, 'event': 'landing'}
    ],
    'trajectory': {
        'time': [...],
        'altitude': [...],
        'velocity': [...],
        'acceleration': [...]
    }
}
```

---

## 3. Export Utilities

### Common Export Functions

#### `export_to_csv(data, filename, include_metadata=True)`
- **Purpose:** Export analysis data to CSV format
- **Features:**
  - Automatic column detection
  - Metadata header section
  - UTF-8 encoding
  - Excel compatibility

#### `export_to_json(data, filename, pretty_print=True)`
- **Purpose:** JSON export for API integration
- **Features:**
  - Nested structure preservation
  - ISO date formatting
  - Compressed option available
  - Schema validation

#### `export_to_matlab(data, filename)`
- **Purpose:** MATLAB .mat file export
- **Features:**
  - Variable name sanitization
  - Matrix structure preservation
  - Metadata inclusion
  - Version compatibility

#### `export_to_excel(data, filename, create_charts=True)`
- **Purpose:** Excel workbook with multiple sheets
- **Features:**
  - Formatted cells
  - Embedded charts
  - Formulas preservation
  - Conditional formatting

### Report Templates

#### Technical Report Template
```python
technical_template = {
    'sections': [
        'Executive Summary',
        'Design Requirements',
        'Performance Analysis',
        'Thermal Analysis',
        'Structural Analysis',
        'Safety Assessment',
        'Test Plan',
        'Conclusions',
        'Appendices'
    ],
    'formatting': {
        'font': 'Times New Roman',
        'size': 12,
        'margins': (1, 1, 1, 1),  # inches
        'line_spacing': 1.5
    }
}
```

#### Quick Summary Template
```python
summary_template = {
    'sections': [
        'Key Results',
        'Performance Metrics',
        'Design Parameters',
        'Recommendations'
    ],
    'max_pages': 3,
    'include_charts': True
}
```

---

## Usage Examples

### PDF Report Generation
```python
from pdf_generator import PDFReportGenerator

generator = PDFReportGenerator()
generator.generate_report(
    analysis_data={
        'motor_type': 'hybrid',
        'results': {...},
        'charts': [...]
    },
    output_path='reports/analysis_001.pdf',
    report_type='full'
)
```

### OpenRocket Export
```python
from openrocket_integration import OpenRocketExporter

exporter = OpenRocketExporter(motor_data)
exporter.add_thrust_curve(time_array, thrust_array)
exporter.export_to_ork('designs/motor_v1.ork')
```

### CSV Export
```python
from export_utilities import export_to_csv

export_to_csv(
    data=performance_results,
    filename='results/performance.csv',
    include_metadata=True
)
```

---

## Advanced Features

### Multi-Language Support
```python
translations = {
    'en': {
        'title': 'Rocket Motor Analysis Report',
        'thrust': 'Thrust',
        'pressure': 'Pressure'
    },
    'tr': {
        'title': 'Roket Motoru Analiz Raporu',
        'thrust': 'İtki',
        'pressure': 'Basınç'
    }
}
```

### Custom Branding
```python
branding = {
    'logo_path': 'assets/company_logo.png',
    'colors': {
        'primary': '#2C3E50',
        'secondary': '#3498DB',
        'accent': '#E74C3C'
    },
    'footer_text': '© 2025 UZAYTEK Engineering',
    'watermark': True
}
```

### Batch Processing
```python
def batch_export(analyses_list, format='pdf'):
    """Export multiple analyses in batch"""
    results = []
    for analysis in analyses_list:
        if format == 'pdf':
            path = generate_pdf(analysis)
        elif format == 'ork':
            path = export_to_openrocket(analysis)
        results.append(path)
    return results
```

### Export Queue System
```python
class ExportQueue:
    def __init__(self):
        self.queue = []
        self.processing = False
    
    def add_job(self, data, format, priority=5):
        self.queue.append({
            'data': data,
            'format': format,
            'priority': priority,
            'status': 'pending'
        })
    
    def process_queue(self):
        self.queue.sort(key=lambda x: x['priority'])
        for job in self.queue:
            self.process_job(job)
```

---

## Performance Optimization

### Chart Rendering
- Pre-render charts in background
- Use vector formats when possible
- Implement lazy loading
- Cache generated images

### PDF Generation
- Stream large documents
- Compress images
- Optimize font embedding
- Use page templates

### File I/O
- Buffered writing
- Async operations for large files
- Compression for archives
- Temporary file cleanup