// JavaScript for Hybrid Rocket Motor Analysis Tool

// currentResults is defined in advanced.html to avoid conflicts

// Update injector parameters based on selected type
function updateInjectorParams() {
    const injectorType = document.getElementById('injector_type');
    const paramsDiv = document.getElementById('injectorParams');
    
    // Safety checks
    if (!injectorType || !paramsDiv) {
        console.log('Injector elements not found, skipping update');
        return;
    }
    
    let html = '';
    
    if (injectorType.value === 'showerhead') {
        html = `
            <div id="showerhead_params">
                <div class="mb-3">
                    <label class="form-label">Target Velocity (m/s)</label>
                    <input type="number" class="form-control" id="target_velocity" value="30" step="1">
                </div>
                <div class="mb-3">
                    <label class="form-label">Number of Holes (0 for auto)</label>
                    <input type="number" class="form-control" id="n_holes" value="0" step="1">
                </div>
                <div class="mb-3">
                    <label class="form-label">Min Hole Diameter (mm)</label>
                    <input type="number" class="form-control" id="hole_diameter_min" value="0.3" step="0.1">
                </div>
                <div class="mb-3">
                    <label class="form-label">Max Hole Diameter (mm)</label>
                    <input type="number" class="form-control" id="hole_diameter_max" value="2.0" step="0.1">
                </div>
                <div class="mb-3">
                    <label class="form-label">Plate Thickness (mm)</label>
                    <input type="number" class="form-control" id="plate_thickness" value="3.0" step="0.1">
                </div>
            </div>
        `;
    } else if (injectorType.value === 'pintle') {
        html = `
            <div id="pintle_params">
                <div class="mb-3">
                    <label class="form-label">Outer Diameter (mm)</label>
                    <input type="number" class="form-control" id="outer_diameter" value="50" step="1">
                </div>
                <div class="mb-3">
                    <label class="form-label">Pintle Diameter (mm)</label>
                    <input type="number" class="form-control" id="pintle_diameter" value="25" step="1">
                </div>
            </div>
        `;
    } else if (injectorType.value === 'swirl') {
        html = `
            <div id="swirl_params">
                <div class="mb-3">
                    <label class="form-label">Number of Slots</label>
                    <input type="number" class="form-control" id="n_slots" value="6" step="1">
                </div>
                <div class="mb-3">
                    <label class="form-label">Slot Width (mm, 0 for auto)</label>
                    <input type="number" class="form-control" id="slot_width" value="0" step="0.1">
                </div>
                <div class="mb-3">
                    <label class="form-label">Slot Height (mm, 0 for auto)</label>
                    <input type="number" class="form-control" id="slot_height" value="0" step="0.1">
                </div>
            </div>
        `;
    }
    
    paramsDiv.innerHTML = html;
}

// Safe parseFloat with fallback - only for NaN/invalid values
function safeParseFloat(value, fallback = 0) {
    const parsed = parseFloat(value);
    return isNaN(parsed) || !isFinite(parsed) ? fallback : parsed;
}

// Collect form data
function getFormData() {
    const data = {
        // Basic parameters
        motor_name: document.getElementById('motor_name') ? document.getElementById('motor_name').value || 'UZAYTEK-HRM-001' : 'UZAYTEK-HRM-001',
        motor_description: document.getElementById('motor_description') ? document.getElementById('motor_description').value || '' : '',
        thrust: safeParseFloat(document.getElementById('thrust').value),
        burn_time: safeParseFloat(document.getElementById('burn_time').value),
        total_impulse: document.getElementById('total_impulse') ? safeParseFloat(document.getElementById('total_impulse').value) : safeParseFloat(document.getElementById('thrust').value) * safeParseFloat(document.getElementById('burn_time').value),
        of_ratio: safeParseFloat(document.getElementById('of_ratio').value),
        chamber_pressure: safeParseFloat(document.getElementById('chamber_pressure').value),
        tank_pressure: safeParseFloat(document.getElementById('tank_pressure').value),
        
        // Advanced parameters
        atmospheric_pressure: safeParseFloat(document.getElementById('single_pressure')?.value, 1.01325),
        chamber_temperature: document.getElementById('chamber_temperature') ? safeParseFloat(document.getElementById('chamber_temperature').value, 2800) : 2800,
        gamma: document.getElementById('gamma') ? safeParseFloat(document.getElementById('gamma').value, 1.25) : 1.25,
        gas_constant: document.getElementById('gas_constant') ? safeParseFloat(document.getElementById('gas_constant').value, 296) : 296,
        l_star: safeParseFloat(document.getElementById('l_star')?.value, 1.0),
        expansion_ratio: document.getElementById('expansion_ratio') ? safeParseFloat(document.getElementById('expansion_ratio').value, 16) : 16,
        nozzle_type: document.getElementById('nozzle_type') ? document.getElementById('nozzle_type').value || 'conical' : 'conical',
        combustion_type: document.getElementById('combustion_type') ? document.getElementById('combustion_type').value || 'infinite' : 'infinite',
        chamber_diameter_input: document.getElementById('chamber_diameter_input') ? safeParseFloat(document.getElementById('chamber_diameter_input').value, 0) : 0,
        contraction_ratio: document.getElementById('contraction_ratio') ? safeParseFloat(document.getElementById('contraction_ratio').value, 0) : 0,
        mass_flux_chamber: document.getElementById('mass_flux_chamber') ? safeParseFloat(document.getElementById('mass_flux_chamber').value, 0) : 0,
        fuel_type: document.getElementById('fuel_type') ? document.getElementById('fuel_type').value || 'htpb' : 'htpb',
        fuel_density: document.getElementById('fuel_density') ? safeParseFloat(document.getElementById('fuel_density').value, 920) : 920,
        regression_a: document.getElementById('regression_a') ? safeParseFloat(document.getElementById('regression_a').value, 0.0003) : 0.0003,
        regression_n: document.getElementById('regression_n') ? safeParseFloat(document.getElementById('regression_n').value, 0.5) : 0.5,
        oxidizer_type: document.getElementById('oxidizer_type') ? document.getElementById('oxidizer_type').value || 'n2o' : 'n2o',
        oxidizer_phase: document.getElementById('oxidizer_phase') ? document.getElementById('oxidizer_phase').value || 'liquid' : 'liquid',
        oxidizer_density: document.getElementById('oxidizer_density') ? safeParseFloat(document.getElementById('oxidizer_density').value, 1220) : 1220,
        oxidizer_viscosity: document.getElementById('oxidizer_viscosity') ? safeParseFloat(document.getElementById('oxidizer_viscosity').value, 0.0002) : 0.0002,
        oxidizer_temp: document.getElementById('oxidizer_temp') ? safeParseFloat(document.getElementById('oxidizer_temp').value, 293) : 293,
        
        // Injector parameters
        injector_type: document.getElementById('injector_type') ? document.getElementById('injector_type').value || 'showerhead' : 'showerhead',
        target_velocity: document.getElementById('target_velocity') ? safeParseFloat(document.getElementById('target_velocity').value, 30) : 30,
        hole_diameter_min: document.getElementById('hole_diameter_min') ? safeParseFloat(document.getElementById('hole_diameter_min').value, 0.3) : 0.3,
        hole_diameter_max: document.getElementById('hole_diameter_max') ? safeParseFloat(document.getElementById('hole_diameter_max').value, 2) : 2,
        plate_thickness: document.getElementById('plate_thickness') ? safeParseFloat(document.getElementById('plate_thickness').value, 3) : 3,
        
        // Trajectory parameters
        calculate_trajectory: document.getElementById('calculate_trajectory') ? document.getElementById('calculate_trajectory').checked : false,
        vehicle_mass_dry: document.getElementById('vehicle_mass_dry') ? safeParseFloat(document.getElementById('vehicle_mass_dry').value, 50) : 50,
        vehicle_diameter: document.getElementById('vehicle_diameter') ? safeParseFloat(document.getElementById('vehicle_diameter').value, 0.15) : 0.15,
        drag_coefficient: document.getElementById('drag_coefficient') ? safeParseFloat(document.getElementById('drag_coefficient').value, 0.5) : 0.5,
        vehicle_length: document.getElementById('vehicle_length') ? safeParseFloat(document.getElementById('vehicle_length').value, 2) : 2,
        launch_angle: document.getElementById('launch_angle') ? safeParseFloat(document.getElementById('launch_angle').value, 85) : 85,
        launch_altitude: document.getElementById('launch_altitude') ? safeParseFloat(document.getElementById('launch_altitude').value, 0) : 0,
        wind_speed: document.getElementById('wind_speed') ? safeParseFloat(document.getElementById('wind_speed').value, 0) : 0,
        wind_direction: document.getElementById('wind_direction') ? safeParseFloat(document.getElementById('wind_direction').value, 0) : 0
    };
    
    // Add injector-specific parameters
    const injectorType = document.getElementById('injector_type').value;
    
    if (injectorType === 'showerhead') {
        data.target_velocity = document.getElementById('target_velocity') ? safeParseFloat(document.getElementById('target_velocity').value, 30) : 30;
        data.n_holes = document.getElementById('n_holes') ? parseInt(document.getElementById('n_holes').value || 0) : 0;
        data.hole_diameter_min = document.getElementById('hole_diameter_min') ? safeParseFloat(document.getElementById('hole_diameter_min').value, 0.3) : 0.3;
        data.hole_diameter_max = document.getElementById('hole_diameter_max') ? safeParseFloat(document.getElementById('hole_diameter_max').value, 2.0) : 2.0;
        data.plate_thickness = document.getElementById('plate_thickness') ? safeParseFloat(document.getElementById('plate_thickness').value, 3.0) : 3.0;
    } else if (injectorType.value === 'pintle') {
        data.outer_diameter = safeParseFloat(document.getElementById('outer_diameter').value, 50);
        data.pintle_diameter = safeParseFloat(document.getElementById('pintle_diameter').value, 25);
    } else if (injectorType.value === 'swirl') {
        data.n_slots = parseInt(document.getElementById('n_slots').value || 6);
        data.slot_width = safeParseFloat(document.getElementById('slot_width').value, 0);
        data.slot_height = safeParseFloat(document.getElementById('slot_height').value, 0);
    }
    
    return data;
}

// Main calculation function
async function calculate() {
    // Prevent any browser form validation
    event?.preventDefault?.();
    
    const data = getFormData();
    
    // Validate inputs
    if (!validateInputs(data)) {
        return;
    }
    
    // Show loading indicator
    showLoading(true);
    hideWelcomeMessage();
    
    try {
        console.log('Sending data to backend:', data);
        
        const response = await fetch('/calculate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        console.log('Response status:', response.status);
        console.log('Response headers:', response.headers);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('Error response text:', errorText);
            throw new Error(`HTTP error! status: ${response.status}, body: ${errorText}`);
        }
        
        const responseText = await response.text();
        console.log('Raw response text:', responseText);
        
        let results;
        try {
            results = JSON.parse(responseText);
            console.log('Parsed results:', results);
        } catch (parseError) {
            console.error('JSON parse error:', parseError);
            throw new Error(`Failed to parse response: ${parseError.message}. Raw response: ${responseText}`);
        }
        
        if (results.error) {
            throw new Error(results.error);
        }
        
        currentResults = results;
        displayCalculationResults(results);
        
        // Enable export buttons
        const exportBtn = document.getElementById('exportResultsBtn');
        if (exportBtn) {
            exportBtn.disabled = false;
        }
        
        // Enable STL and OpenRocket export buttons
        const exportSTLBtn = document.getElementById('exportSTLBtn');
        const downloadEngBtn = document.getElementById('downloadEngBtn');
        if (exportSTLBtn) {
            exportSTLBtn.disabled = false;
        }
        if (downloadEngBtn) {
            downloadEngBtn.disabled = false;
        }
        
        // Reset CAD status now that we have results
        if (typeof resetCADStatus === 'function') {
            resetCADStatus();
        }
        
    } catch (error) {
        handleError(error, 'Main Calculation Function');
    } finally {
        showLoading(false);
    }
}

// Validate inputs
function validateInputs(data) {
    const errors = [];
    
    // Check for NaN values
    Object.keys(data).forEach(key => {
        if (typeof data[key] === 'number' && (isNaN(data[key]) || !isFinite(data[key]))) {
            errors.push(`${key.replace('_', ' ')} has invalid value (${data[key]})`);
        }
    });
    
    if (data.thrust <= 0) errors.push('Thrust must be positive');
    if (data.burn_time <= 0) errors.push('Burn time must be positive');
    if (data.of_ratio <= 0) errors.push('O/F ratio must be positive');
    if (data.chamber_pressure <= 0) errors.push('Chamber pressure must be positive');
    
    // Detailed tank pressure validation
    if (data.tank_pressure <= 0) {
        errors.push('Tank pressure must be positive');
    } else if (data.tank_pressure <= data.chamber_pressure) {
        const minRequired = data.chamber_pressure * 1.2; // Minimum 20% higher
        errors.push(`Tank pressure (${data.tank_pressure} bar) must be higher than chamber pressure (${data.chamber_pressure} bar). Minimum required: ${minRequired.toFixed(1)} bar`);
    } else if (data.tank_pressure < data.chamber_pressure * 1.2) {
        const minRecommended = data.chamber_pressure * 1.2;
        errors.push(`Warning: Tank pressure (${data.tank_pressure} bar) should be at least 20% higher than chamber pressure. Recommended minimum: ${minRecommended.toFixed(1)} bar`);
    }
    
    // Additional range checks
    if (data.of_ratio > 20) errors.push('O/F ratio too high (max 20)');
    if (data.chamber_pressure > 200) errors.push('Chamber pressure too high (max 200 bar)');
    if (data.burn_time > 300) errors.push('Burn time too long (max 300 seconds)');
    
    // Chamber diameter check
    if (data.chamber_diameter_input > 0 && data.chamber_diameter_input < 10) {
        errors.push('Chamber diameter too small (min 10mm)');
    }
    if (data.chamber_diameter_input > 1000) {
        errors.push('Chamber diameter too large (max 1000mm)');
    }
    
    // Finite area combustion validation
    if (data.combustion_type === 'finite') {
        const hasContractionRatio = data.contraction_ratio && data.contraction_ratio > 0;
        const hasMassFlux = data.mass_flux_chamber && data.mass_flux_chamber > 0;
        
        if (hasContractionRatio && hasMassFlux) {
            errors.push('For finite area combustion, fill only ONE parameter: either contraction ratio OR mass flux chamber (not both)');
        } else if (!hasContractionRatio && !hasMassFlux) {
            errors.push('For finite area combustion, you must fill either contraction ratio OR mass flux chamber');
        }
    }
    
    if (errors.length > 0) {
        showError('Input validation failed:\n• ' + errors.join('\n• '));
        return false;
    }
    
    return true;
}

// Display results
function displayCalculationResults(results) {
    const resultsPanel = document.getElementById('resultsPanel');
    resultsPanel.style.display = 'block';
    resultsPanel.classList.add('fade-in');
    
    // Validate and fix injector diameter if needed
    validateAndFixInjectorDiameter(results);
    
    // Display performance metrics
    displayPerformanceMetrics(results.motor);
    
    // Display plots
    displayPlots(results.plots);
    
    // Display design report
    displayDesignReport(results.motor, results.injector);
    
    // Display motor design table
    displayMotorTable(results.motor);
    
    // Display injector design table
    displayInjectorTable(results.injector);
    
    // Display warnings
    displayWarnings(results.injector.warnings || []);
    
    // Show export panel after successful calculation
    const exportPanel = document.getElementById('exportActionsPanel');
    if (exportPanel) {
        exportPanel.style.display = 'block';
    }
}

// Validate and fix injector diameter
function validateAndFixInjectorDiameter(results) {
    const chamberDiameter = results.motor.chamber_diameter * 1000; // Convert to mm
    
    // Check injector outer diameter for different types
    if (results.injector.type === 'pintle' && results.injector.outer_diameter) {
        if (results.injector.outer_diameter > chamberDiameter * 0.9) {
            // Injector should be max 90% of chamber diameter for clearance
            results.injector.outer_diameter = chamberDiameter * 0.8;
            
            // Add warning
            if (!results.injector.warnings) {
                results.injector.warnings = [];
            }
            results.injector.warnings.push(`Injector diameter limited to ${results.injector.outer_diameter.toFixed(1)}mm (80% of chamber diameter)`);
        }
    }
    
    if (results.injector.type === 'showerhead') {
        // Calculate effective injector plate diameter
        const effectiveDiameter = Math.sqrt(results.injector.n_holes || 1) * (results.injector.hole_diameter || 1) * 3;
        
        if (effectiveDiameter > chamberDiameter * 0.9) {
            // Recalculate hole parameters
            const maxDiameter = chamberDiameter * 0.8;
            const holeCount = results.injector.n_holes || 20;
            results.injector.hole_diameter = maxDiameter / (Math.sqrt(holeCount) * 3);
            
            if (!results.injector.warnings) {
                results.injector.warnings = [];
            }
            results.injector.warnings.push(`Hole pattern adjusted to fit within chamber diameter (${chamberDiameter.toFixed(1)}mm)`);
        }
    }
    
    // Ensure injector diameter field exists for display
    if (!results.injector.injector_diameter) {
        results.injector.injector_diameter = chamberDiameter * 0.8;
    }
}

// Display performance metrics
function displayPerformanceMetrics(motorData) {
    const metricsDiv = document.getElementById('performanceMetrics');
    
    const metrics = [
        { label: 'Specific Impulse', value: motorData.isp.toFixed(1), unit: 's', color: '#667eea' },
        { label: 'Thrust', value: motorData.thrust.toFixed(0), unit: 'N', color: '#764ba2' },
        { label: 'Chamber Pressure', value: motorData.chamber_pressure.toFixed(1), unit: 'bar', color: '#f093fb' },
        { label: 'Mass Flow Rate', value: motorData.mdot_total.toFixed(3), unit: 'kg/s', color: '#f5576c' }
    ];
    
    let html = '';
    metrics.forEach(metric => {
        html += `
            <div class="col-md-3 col-sm-6">
                <div class="metric-card" style="background: linear-gradient(135deg, ${metric.color} 0%, ${metric.color}aa 100%);">
                    <div class="metric-value">${metric.value}</div>
                    <div class="metric-label">${metric.label}</div>
                    <div class="metric-unit">${metric.unit}</div>
                </div>
            </div>
        `;
    });
    
    metricsDiv.innerHTML = html;
}

// Display plots
function displayPlots(plots) {
    // Helper function to safely create plots
    function safePlotCreate(elementId, plotData) {
        const element = document.getElementById(elementId);
        if (element && plotData) {
            try {
                const parsedData = JSON.parse(plotData);
                
                // Enhanced config for better responsive behavior
                const config = {
                    responsive: true,
                    displayModeBar: true,
                    displaylogo: false,
                    modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
                    toImageButtonOptions: {
                        format: 'png',
                        filename: elementId,
                        height: 500,
                        width: 700,
                        scale: 1
                    }
                };
                
                // Update layout for better responsiveness
                if (parsedData.layout) {
                    parsedData.layout.autosize = true;
                    if (!parsedData.layout.margin) {
                        parsedData.layout.margin = { l: 60, r: 30, t: 60, b: 60 };
                    }
                    // Ensure proper sizing
                    parsedData.layout.width = undefined;
                    parsedData.layout.height = undefined;
                }
                
                Plotly.newPlot(elementId, parsedData.data, parsedData.layout, config);
                
                // Force resize on window resize
                window.addEventListener('resize', () => {
                    Plotly.Plots.resize(elementId);
                });
                
            } catch (e) {
                console.warn(`Failed to create plot for ${elementId}:`, e);
                element.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">Plot data unavailable</div>';
            }
        } else if (element) {
            element.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">No data available</div>';
        }
    }
    
    // Motor plot
    safePlotCreate('motor_plot', plots.motor);
    
    // Injector plot
    safePlotCreate('injector_plot', plots.injector);
    
    // Performance plots
    safePlotCreate('performance_plots', plots.performance);
    
    // 3D Motor visualization
    if (plots.motor_3d && !plots.motor_3d.error) {
        const motor3DElement = document.getElementById('motor_3d_plot');
        if (motor3DElement) {
            try {
                const plot3D = typeof plots.motor_3d === 'string' ? JSON.parse(plots.motor_3d) : plots.motor_3d;
                Plotly.newPlot('motor_3d_plot', plot3D.data, plot3D.layout, {
                    responsive: true,
                    displayModeBar: true,
                    displaylogo: false
                });
                // Show 3D panel
                const panel3D = document.getElementById('cad3DPanel');
                if (panel3D) {
                    panel3D.style.display = 'block';
                }
            } catch (e) {
                console.warn('Failed to create 3D motor plot:', e);
                motor3DElement.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">3D visualization unavailable</div>';
            }
        }
    } else if (plots.motor_3d && plots.motor_3d.error) {
        console.warn('3D motor plot error:', plots.motor_3d.error);
    }
    
    // Trajectory plot
    if (plots.trajectory && !plots.trajectory.error) {
        safePlotCreate('trajectory_plot', plots.trajectory);
        const trajectoryPanel = document.getElementById('trajectoryPanel');
        if (trajectoryPanel) {
            trajectoryPanel.style.display = 'block';
        }
    } else if (plots.trajectory && plots.trajectory.error) {
        console.warn('Trajectory plot error:', plots.trajectory.error);
    }
}

// Display design report
function displayDesignReport(motorData, injectorData) {
    const reportDiv = document.getElementById('designReport');
    
    let html = `
        <div class="report-section">
            <h6>Motor Performance</h6>
            <table class="report-table table table-striped">
                <tbody>
                    <tr><td>Specific Impulse (Isp)</td><td>${motorData.isp.toFixed(1)} s</td></tr>
                    <tr><td>Characteristic Velocity (C*)</td><td>${motorData.c_star.toFixed(0)} m/s</td></tr>
                    <tr><td>Thrust Coefficient (CF)</td><td>${motorData.cf.toFixed(3)}</td></tr>
                    <tr><td>Throat Diameter</td><td>${(motorData.throat_diameter * 1000).toFixed(1)} mm</td></tr>
                    <tr><td>Exit Diameter</td><td>${(motorData.exit_diameter * 1000).toFixed(1)} mm</td></tr>
                    <tr><td>Expansion Ratio</td><td>${motorData.expansion_ratio.toFixed(1)}</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="report-section">
            <h6>Motor Geometry</h6>
            <table class="report-table table table-striped">
                <tbody>
                    <tr><td>Chamber Diameter</td><td>${(motorData.chamber_diameter * 1000).toFixed(1)} mm</td></tr>
                    <tr><td>Chamber Length</td><td>${(motorData.chamber_length * 1000).toFixed(1)} mm</td></tr>
                    <tr><td>Chamber Volume</td><td>${(motorData.chamber_volume * 1e6).toFixed(1)} cm³</td></tr>
                    <tr><td>Initial Port Diameter</td><td>${(motorData.port_diameter_initial * 1000).toFixed(1)} mm</td></tr>
                    <tr><td>Final Port Diameter</td><td>${(motorData.port_diameter_final * 1000).toFixed(1)} mm</td></tr>
                    <tr><td>Regression Rate</td><td>${motorData.regression_rate ? (motorData.regression_rate * 1000).toFixed(2) : 'N/A'} mm/s</td></tr>
                    <tr><td>Avg Regression Rate</td><td>${motorData.regression_rate_avg ? (motorData.regression_rate_avg * 1000).toFixed(2) : 'N/A'} mm/s</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="report-section">
            <h6>Injector Design</h6>
            <table class="report-table table table-striped">
                <tbody>
                    <tr><td>Type</td><td>${injectorData.type.charAt(0).toUpperCase() + injectorData.type.slice(1)}</td></tr>
                    <tr><td>Exit Velocity</td><td>${injectorData.exit_velocity.toFixed(1)} m/s</td></tr>
                    <tr><td>Reynolds Number</td><td>${injectorData.reynolds_number.toFixed(0)}</td></tr>
                    <tr><td>Pressure Drop</td><td>${injectorData.pressure_drop.toFixed(2)} bar</td></tr>
    `;
    
    // Add type-specific parameters
    if (injectorData.type === 'showerhead') {
        html += `
                    <tr><td>Number of Holes</td><td>${injectorData.n_holes}</td></tr>
                    <tr><td>Hole Diameter</td><td>${injectorData.hole_diameter.toFixed(2)} mm</td></tr>
                    <tr><td>L/D Ratio</td><td>${injectorData.L_D_ratio.toFixed(1)}</td></tr>
        `;
    } else if (injectorData.type === 'pintle') {
        html += `
                    <tr><td>Outer Diameter</td><td>${injectorData.outer_diameter.toFixed(1)} mm</td></tr>
                    <tr><td>Pintle Diameter</td><td>${injectorData.pintle_diameter.toFixed(1)} mm</td></tr>
                    <tr><td>Gap</td><td>${injectorData.gap.toFixed(2)} mm</td></tr>
        `;
    } else if (injectorData.type === 'swirl') {
        html += `
                    <tr><td>Number of Slots</td><td>${injectorData.n_slots}</td></tr>
                    <tr><td>Slot Width</td><td>${injectorData.slot_width.toFixed(2)} mm</td></tr>
                    <tr><td>Slot Height</td><td>${injectorData.slot_height.toFixed(2)} mm</td></tr>
                    <tr><td>Spray Angle</td><td>${injectorData.spray_angle}°</td></tr>
        `;
    }
    
    html += `
                </tbody>
            </table>
        </div>
        
        <div class="report-section">
            <h6>Propellant</h6>
            <table class="report-table table table-striped">
                <tbody>
                    <tr><td>Total Mass Flow Rate</td><td>${motorData.mdot_total.toFixed(3)} kg/s</td></tr>
                    <tr><td>Oxidizer Mass Flow Rate</td><td>${motorData.mdot_ox.toFixed(3)} kg/s</td></tr>
                    <tr><td>Fuel Mass Flow Rate</td><td>${motorData.mdot_f.toFixed(3)} kg/s</td></tr>
                    <tr><td>Total Propellant Mass</td><td>${motorData.propellant_mass_total.toFixed(2)} kg</td></tr>
                    <tr><td>Oxidizer Mass</td><td>${motorData.oxidizer_mass.toFixed(2)} kg</td></tr>
                    <tr><td>Fuel Mass</td><td>${motorData.fuel_mass.toFixed(2)} kg</td></tr>
                </tbody>
            </table>
        </div>
    `;
    
    reportDiv.innerHTML = html;
}

// Display warnings
function displayWarnings(warnings) {
    const warningsPanel = document.getElementById('warningsPanel');
    const warningsList = document.getElementById('warningsList');
    
    // Check if elements exist (they might not exist on all pages)
    if (!warningsPanel || !warningsList) {
        console.warn('Warning elements not found on this page');
        return;
    }
    
    if (warnings && warnings.length > 0) {
        let html = '';
        warnings.forEach(warning => {
            html += `
                <div class="warning-item">
                    <i class="fas fa-exclamation-triangle"></i>
                    ${warning}
                </div>
            `;
        });
        
        warningsList.innerHTML = html;
        warningsPanel.style.display = 'block';
    } else {
        warningsPanel.style.display = 'none';
    }
}

// Optimization function
async function optimize() {
    if (!currentResults) {
        showError('Please calculate first before optimizing');
        return;
    }
    
    showLoading(true);
    
    try {
        const data = getFormData();
        
        const response = await fetch('/optimize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const results = await response.json();
        
        if (results.error) {
            throw new Error(results.error);
        }
        
        showInfo('Optimization completed: ' + results.message);
        
    } catch (error) {
        handleError(error, 'Optimization Function');
    } finally {
        showLoading(false);
    }
}

// Export report function
function exportReport() {
    if (!currentResults) {
        showError('No results to export');
        return;
    }
    
    // Create a simple text report
    let report = 'HYBRID ROCKET MOTOR ANALYSIS REPORT\n';
    report += '=====================================\n\n';
    
    report += 'MOTOR PERFORMANCE:\n';
    report += `Specific Impulse: ${currentResults.motor.isp.toFixed(1)} s\n`;
    report += `Thrust: ${currentResults.motor.thrust.toFixed(0)} N\n`;
    report += `Chamber Pressure: ${currentResults.motor.chamber_pressure.toFixed(1)} bar\n`;
    report += `Mass Flow Rate: ${currentResults.motor.mdot_total.toFixed(3)} kg/s\n\n`;
    
    report += 'INJECTOR DESIGN:\n';
    report += `Type: ${currentResults.injector.type}\n`;
    report += `Exit Velocity: ${currentResults.injector.exit_velocity.toFixed(1)} m/s\n`;
    report += `Reynolds Number: ${currentResults.injector.reynolds_number.toFixed(0)}\n`;
    report += `Pressure Drop: ${currentResults.injector.pressure_drop.toFixed(2)} bar\n\n`;
    
    if (currentResults.injector.warnings.length > 0) {
        report += 'WARNINGS:\n';
        currentResults.injector.warnings.forEach(warning => {
            report += `• ${warning}\n`;
        });
    }
    
    // Download the report
    const blob = new Blob([report], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'hybrid_rocket_report.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

function exportRegressionData() {
    alert('Export regression data functionality is not implemented yet.');
}

// Advanced Error Handler
function handleError(error, context = 'Unknown') {
    console.group('ERROR DETAILS');
    console.error('Context:', context);
    console.error('Error Type:', error.constructor.name);
    console.error('Error Message:', error.message);
    console.error('Stack Trace:', error.stack);
    
    // Check for specific error types
    let errorSource = 'Unknown';
    let userMessage = error.message;
    
    if (error.message.includes('pattern')) {
        errorSource = 'Form Validation';
        userMessage = 'Form validation error - check input formats';
    } else if (error.message.includes('HTTP')) {
        errorSource = 'Network/Backend';
        userMessage = 'Server communication error';
    } else if (error instanceof TypeError) {
        errorSource = 'JavaScript Type Error';
        userMessage = 'Data type mismatch in calculations';
    } else if (error instanceof ReferenceError) {
        errorSource = 'JavaScript Reference Error';
        userMessage = 'Missing function or variable';
    } else if (error.message.includes('JSON')) {
        errorSource = 'Data Parsing';
        userMessage = 'Invalid data format received from server';
    }
    
    console.error('Error Source:', errorSource);
    console.groupEnd();
    
    // Show detailed error to user
    const detailedError = `
ERROR DETECTED

Source: ${errorSource}
Context: ${context}
Message: ${userMessage}

Technical Details:
- Type: ${error.constructor.name}
- Original: ${error.message}
- Time: ${new Date().toLocaleString()}

Check browser console for full stack trace.
    `;
    
    alert(detailedError);
    return { source: errorSource, context, originalError: error };
}

// Utility functions
function showLoading(show) {
    const indicator = document.getElementById('loading');
    if (indicator) {
        indicator.style.display = show ? 'block' : 'none';
    }
}

function hideWelcomeMessage() {
    const welcome = document.getElementById('welcomeMessage');
    if (welcome) {
        welcome.style.display = 'none';
    }
}

function showError(message) {
    alert('Error: ' + message);
}

function showInfo(message) {
    alert('Info: ' + message);
}

function showMessage(message, type = 'info') {
    // Type can be: 'info', 'success', 'warning', 'error'
    const prefix = type.charAt(0).toUpperCase() + type.slice(1);
    alert(`${prefix}: ${message}`);
}

function showSuccess(message) {
    showMessage(message, 'success');
}

function showWarning(message) {
    showMessage(message, 'warning');
}

// Initialize the page
document.addEventListener('DOMContentLoaded', function() {
    updateInjectorParams();
});

// Ask AI Analysis
function askAI() {
    if (!currentResults) {
        showError('No results to analyze. Please run calculations first.');
        return;
    }
    
    // Prepare AI-friendly JSON
    const aiData = prepareAIData(currentResults);
    
    // Create prompt
    const prompt = `Please analyze this comprehensive hybrid rocket motor design data and provide detailed engineering insights:

${JSON.stringify(aiData, null, 2)}

As an expert aerospace engineer, please provide detailed analysis in the following areas:

**PERFORMANCE ANALYSIS:**
1. Evaluate the specific impulse and thrust efficiency
2. Assess the O/F ratio optimization  
3. Review combustion chamber and nozzle design effectiveness
4. Comment on propellant utilization efficiency

**SAFETY & STRUCTURAL ASSESSMENT:**
1. Review the calculated hoop stress and wall thickness recommendations
2. Evaluate the safety factors and design margins
3. Assess thermal management and cooling requirements
4. Identify any critical failure modes or risks

**DESIGN OPTIMIZATION:**
1. Suggest improvements for better performance
2. Recommend material selections based on thermal/structural analysis
3. Optimize injector design for better mixing
4. Propose nozzle geometry refinements

**COMPARATIVE ANALYSIS:**
1. Compare this design to typical hybrid rockets in its class
2. Benchmark against industry standards and best practices
3. Assess manufacturability and cost considerations

**RISK ASSESSMENT:**
1. Evaluate the identified risk factors
2. Suggest mitigation strategies
3. Recommend testing protocols
4. Identify compliance with safety standards

Please provide specific numerical recommendations where applicable and explain the engineering rationale behind your suggestions.`;
    
    // Copy to clipboard
    navigator.clipboard.writeText(prompt).then(() => {
        showInfo('Analysis data copied to clipboard! Paste it into your favorite AI assistant.');
        
        // Optional: Show the data in a modal
        showAIDataModal(aiData, prompt);
    }).catch(err => {
        console.error('Failed to copy:', err);
        showError('Failed to copy data. Check console for details.');
    });
}

// Function to get display name for fuel type
function getFuelTypeDisplayName(fuelType) {
    const currentFuelType = document.getElementById('fuel_type').value;
    
    // Check if custom composition is being used
    if (currentFuelType === 'custom') {
        const compositionRows = document.querySelectorAll('#custom_fuel_config .composition-row');
        let customName = 'Custom Composition (';
        let compounds = [];
        
        compositionRows.forEach(row => {
            const compound = row.querySelector('.compound').value.trim();
            const percentage = row.querySelector('.percentage').value;
            if (compound && percentage) {
                compounds.push(`${compound}: ${percentage}%`);
            }
        });
        
        if (compounds.length > 0) {
            customName += compounds.join(', ') + ')';
        } else {
            customName += 'No composition specified)';
        }
        
        return customName;
    }
    
    // Check if custom mixture is being used
    if (currentFuelType === 'mixture') {
        const mixtureRows = document.querySelectorAll('#custom_fuel_mixture .mixture-component');
        let mixtureName = 'Custom Mixture (';
        let components = [];
        
        mixtureRows.forEach(row => {
            const fuelSelect = row.querySelector('.mixture-fuel');
            const percentage = row.querySelector('.mixture-percentage').value;
            if (fuelSelect && percentage) {
                const fuelName = fuelSelect.options[fuelSelect.selectedIndex].text;
                components.push(`${fuelName}: ${percentage}%`);
            }
        });
        
        if (components.length > 0) {
            mixtureName += components.join(', ') + ')';
        } else {
            mixtureName += 'No components specified)';
        }
        
        return mixtureName;
    }
    
    // Return standard fuel type display name
    const fuelNames = {
        'htpb': 'HTPB (Hydroxyl-terminated polybutadiene)',
        'pe': 'Polyethylene',
        'pmma': 'PMMA (Polymethyl methacrylate)',
        'paraffin': 'Paraffin Wax',
        'abs': 'ABS Plastic',
        'pla': 'PLA Plastic',
        'carbon': 'Carbon (Graphite)',
        'aluminum': 'Aluminum Powder',
        'al2o3': 'Aluminum Oxide (Al2O3)'
    };
    
    return fuelNames[fuelType] || (fuelType ? fuelType.toUpperCase() : 'Unknown Fuel');
}

// Prepare AI-friendly data
function prepareAIData(results) {
    return {
        analysis_type: "Hybrid Rocket Motor Design",
        timestamp: new Date().toISOString(),
        schema_version: "1.0",
        units_system: "SI_mixed", // Note: Mixed units used (bar for pressure, mm for dimensions)
        generator: "HRMA v2.0",
        run_id: generateRunId(),
        
        input_parameters: {
            thrust_N: results.motor.thrust,
            burn_time_s: results.motor.burn_time,
            total_impulse_Ns: results.motor.total_impulse,
            of_ratio_dimensionless: results.motor.of_ratio,
            chamber_pressure_bar: results.motor.chamber_pressure, // CRITICAL: Unit assumed as bar
            fuel_type: getFuelTypeDisplayName(results.motor.fuel_type),
            oxidizer: 'N2O',
            reference_conditions: {
                ambient_pressure_Pa: 101325,
                ambient_temperature_K: 293.15,
                performance_basis: "sea_level_standard"
            }
        },
        
        performance_results: {
            specific_impulse_sec: {
                value: results.motor.isp,
                derived_from: "c_star_and_cf",
                reference: "sea_level_standard"
            },
            c_star_m_s: results.motor.c_star,
            thrust_coefficient_dimensionless: results.motor.cf,
            total_mass_flow_kg_s: results.motor.mdot_total,
            oxidizer_flow_kg_s: results.motor.mdot_ox,
            fuel_flow_kg_s: results.motor.mdot_f,
            propellant_mass_kg: {
                value: results.motor.propellant_mass_total,
                derived_from: "mass_flow_and_burn_time",
                calculation_method: "mdot_total * burn_time"
            },
            thrust_to_weight_ratio: {
                value: results.motor.thrust / (results.motor.propellant_mass_total * 9.81),
                reference_mass_kg: results.motor.propellant_mass_total,
                description: "thrust / (propellant_mass * g0)"
            }
        },
        
        geometry: {
            chamber_diameter_mm: results.motor.chamber_diameter * 1000,
            chamber_length_mm: results.motor.chamber_length * 1000,
            throat_diameter_mm: results.motor.throat_diameter * 1000,
            exit_diameter_mm: results.motor.exit_diameter * 1000,
            expansion_ratio_dimensionless: results.motor.expansion_ratio,
            port_diameter_initial_mm: results.motor.port_diameter_initial * 1000,
            port_diameter_final_mm: results.motor.port_diameter_final * 1000,
            
            // Geometry validation and anomaly detection
            l_over_d_ratio: (results.motor.chamber_length * 1000) / (results.motor.chamber_diameter * 1000),
            geometry_anomalies: detectGeometryAnomalies(results.motor),
            
            nozzle_geometry: {
                convergent_angle_deg: results.motor.convergent_angle || 15.0,
                divergent_angle_deg: results.motor.divergent_angle || 12.0,
                angle_definition: "half_angles_from_centerline",
                nozzle_type: "conical_assumed"
            }
        },
        
        injector_design: {
            type: results.injector.type,
            exit_velocity_m_s: results.injector.exit_velocity,
            pressure_drop_bar: results.injector.pressure_drop,
            reynolds_number: {
                value: results.injector.reynolds_number,
                reference_diameter: "injector_hole_diameter",
                fluid: "oxidizer",
                calculation_note: "Re = ρvd/μ for oxidizer flow"
            },
            discharge_coefficient: 0.65, // Assumed typical value
            ...(results.injector.type === 'showerhead' && {
                holes_count: results.injector.n_holes,
                hole_diameter_mm: results.injector.hole_diameter,
                l_over_d_ratio: 2.0, // Assumed typical value
                plate_thickness_mm: 3.0 // Assumed
            }),
            flow_characteristics: {
                oxidizer_inlet_temperature_K: 293.15,
                inlet_pressure_bar: (results.motor.chamber_pressure || 20) + (results.injector.pressure_drop || 5),
                flash_boiling_risk: results.injector.pressure_drop < 3.0 ? "HIGH" : "LOW",
                cavitation_index: calculateCavitationIndex(results.injector)
            }
        },
        
        warnings: structurizeWarnings(results.injector.warnings || []),
        
        efficiency_metrics: {
            combustion_efficiency_estimate: 0.95,
            nozzle_efficiency_estimate: 0.98,
            overall_efficiency_estimate: 0.93
        },
        
        thermal_analysis: {
            chamber_temperature_K: results.motor.chamber_temperature || 3000,
            nozzle_angles: {
                convergent_angle_deg: results.motor.convergent_angle || 15.0,
                divergent_angle_deg: results.motor.divergent_angle || 12.0
            },
            material_properties: {
                recommended_materials: ['Steel 4130', 'Inconel 718', 'Aluminum 6061'],
                thermal_considerations: {
                    max_wall_temperature_K: 1200,
                    cooling_required: results.motor.chamber_temperature > 2500
                }
            }
        },
        
        structural_analysis: {
            design_pressure_bar: (results.motor.chamber_pressure * 1.5) || 30,
            safety_factors: {
                chamber_wall: 4.0,
                nozzle: 3.0,
                injector: 4.0
            },
            stress_analysis: {
                hoop_stress_estimate_MPa: calculateHoopStress(results.motor),
                wall_thickness_recommendation_mm: calculateWallThickness(results.motor),
                burst_pressure_factor: 4.0
            }
        },
        
        safety_considerations: {
            critical_parameters: {
                chamber_pressure_limit_bar: 50,
                of_ratio_range: [2.0, 8.0],
                thrust_to_weight_ratio: results.motor.thrust / (results.motor.propellant_mass_total * 9.81)
            },
            risk_factors: identifyRiskFactors(results),
            recommended_testing: [
                'Cold flow tests',
                'Static fire tests',
                'Burst pressure testing',
                'Thermal cycling tests'
            ]
        },
        
        manufacturing_data: {
            tolerances: {
                chamber_diameter_mm: {
                    type: "bilateral",
                    plus: 0.1,
                    minus: 0.1,
                    unit: "mm",
                    grade: "IT7"
                },
                throat_diameter_mm: {
                    type: "bilateral", 
                    plus: 0.05,
                    minus: 0.05,
                    unit: "mm",
                    grade: "IT6",
                    critical: true
                },
                surface_finish: {
                    parameter: "Ra",
                    value: 3.2,
                    unit: "μm",
                    measurement_standard: "ISO4287"
                }
            },
            machining_requirements: {
                chamber: {
                    method: "CNC turning",
                    material_removal_rate: "conservative",
                    heat_treatment: "stress_relief_required"
                },
                nozzle: {
                    method: "CNC machining + EDM finish",
                    throat_fabrication: "wire_EDM_preferred",
                    convergent_divergent_matching: "±0.02mm"
                },
                injector: {
                    method: "precision_drilling + EDM",
                    hole_pattern_tolerance: "±0.02mm",
                    flow_testing_required: true
                }
            }
        }
    };
}

// Helper calculation functions for AI data

function generateRunId() {
    return 'RUN_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 5);
}

function detectGeometryAnomalies(motorData) {
    const anomalies = [];
    
    // L/D ratio check
    const lOverD = (motorData.chamber_length * 1000) / (motorData.chamber_diameter * 1000);
    if (lOverD < 0.1) {
        anomalies.push({
            type: "SCALE_ANOMALY",
            severity: "HIGH", 
            message: `Extremely low L/D ratio: ${lOverD.toFixed(3)}`,
            likely_cause: "Unit conversion error or data entry mistake"
        });
    }
    
    // Port diameter vs chamber check
    const portFinalMm = motorData.port_diameter_final * 1000;
    const chamberMm = motorData.chamber_diameter * 1000;
    const minWallThickness = 5; // mm minimum wall
    
    if (portFinalMm > (chamberMm - 2 * minWallThickness)) {
        anomalies.push({
            type: "WALL_THICKNESS_VIOLATION",
            severity: "CRITICAL",
            message: `Final port diameter too large for safe wall thickness`,
            values: {port_final_mm: portFinalMm, chamber_mm: chamberMm, min_wall_mm: minWallThickness}
        });
    }
    
    return anomalies;
}

function structurizeWarnings(warningStrings) {
    return warningStrings.map((warning, index) => ({
        id: `WARN_${index + 1}`,
        code: warning.includes('flash') ? 'FLASH_BOILING' : 'GENERAL',
        severity: warning.includes('flash') ? 'HIGH' : 'MEDIUM',
        message: warning,
        timestamp: new Date().toISOString(),
        path: 'injector_design'
    }));
}

function calculateCavitationIndex(injectorData) {
    // Simplified cavitation index calculation
    const pressureDrop = injectorData.pressure_drop || 5;
    const inletPressure = 25; // Assumed tank pressure in bar
    return pressureDrop / inletPressure;
}

function calculateHoopStress(motorData) {
    // Hoop stress calculation: σ = PD/(2t)
    // Assuming 5mm wall thickness for estimation
    const pressure = (motorData.chamber_pressure || 20) * 1e5; // Pa
    const diameter = (motorData.chamber_diameter || 0.1) * 1000; // mm  
    const thickness = 5; // mm, estimated
    
    const hoopStress = (pressure * diameter) / (2 * thickness * 1e6); // Convert to MPa
    return Math.round(hoopStress * 100) / 100;
}

function calculateWallThickness(motorData) {
    // Wall thickness calculation based on pressure vessel design
    // t = PD/(2σ) * SF
    const pressure = (motorData.chamber_pressure || 20) * 1e5; // Pa
    const diameter = (motorData.chamber_diameter || 0.1) * 1000; // mm
    const allowableStress = 200e6; // Pa, steel yield strength / safety factor
    const safetyFactor = 4.0;
    
    const thickness = (pressure * diameter) / (2 * allowableStress) * safetyFactor;
    return Math.max(3.0, Math.round(thickness * 100) / 100); // Minimum 3mm
}

function identifyRiskFactors(results) {
    const risks = [];
    
    // High pressure risk
    if (results.motor.chamber_pressure > 40) {
        risks.push('HIGH_PRESSURE: Chamber pressure exceeds 40 bar - requires robust design');
    }
    
    // O/F ratio risks
    const ofRatio = results.motor.of_ratio;
    if (ofRatio < 2.0) {
        risks.push('RICH_MIXTURE: Low O/F ratio may cause incomplete combustion');
    } else if (ofRatio > 8.0) {
        risks.push('LEAN_MIXTURE: High O/F ratio may cause overheating');
    }
    
    // Thrust density risk
    const thrustDensity = results.motor.thrust / (Math.PI * Math.pow(results.motor.chamber_diameter/2, 2));
    if (thrustDensity > 5000000) { // N/m²
        risks.push('HIGH_THRUST_DENSITY: May cause thermal stress issues');
    }
    
    // Expansion ratio risk
    if (results.motor.expansion_ratio > 20) {
        risks.push('HIGH_EXPANSION_RATIO: Risk of flow separation in nozzle');
    }
    
    // Port diameter risk
    const portRatio = results.motor.port_diameter_final / results.motor.port_diameter_initial;
    if (portRatio > 3.0) {
        risks.push('EXCESSIVE_REGRESSION: Large port growth may affect performance');
    }
    
    return risks.length > 0 ? risks : ['LOW_RISK: Design parameters within normal ranges'];
}

// Show AI data in modal
function showAIDataModal(data, prompt) {
    // Create modal HTML
    const modalHTML = `
        <div id="aiModal" style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 9999; display: flex; align-items: center; justify-content: center;">
            <div style="background: white; padding: 30px; border-radius: 10px; max-width: 80%; max-height: 80%; overflow-y: auto;">
                <h2 style="margin-bottom: 20px;">AI Analysis Data</h2>
                <p style="margin-bottom: 15px;">The following data has been copied to your clipboard. You can paste it into ChatGPT, Claude, or any AI assistant:</p>
                <pre style="background: #f5f5f5; padding: 15px; border-radius: 5px; overflow-x: auto; max-height: 400px;">${prompt}</pre>
                <div style="text-align: center; margin-top: 20px;">
                    <button onclick="document.getElementById('aiModal').remove()" style="background: #3498db; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer;">Close</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', modalHTML);
}

// Handle Enter key in form
document.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && e.target.classList.contains('form-control')) {
        e.preventDefault();
        calculate();
    }
});

// Show design configuration panel
function showDesignConfig() {
    if (!currentResults) {
        showError('Please calculate motor first');
        return;
    }
    
    // Hide export panel temporarily
    document.getElementById('exportActionsPanel').style.display = 'none';
    
    // Show config panel
    document.getElementById('designConfigPanel').style.display = 'block';
    
    // Auto-fill values from analysis results
    autoFillDesignConfig();
}

// Auto-fill design configuration from analysis results
function autoFillDesignConfig() {
    if (!currentResults) return;
    
    // Motor parameters
    const motor = currentResults.motor;
    const injector = currentResults.injector;
    
    // Auto-fill chamber dimensions (convert to mm)
    const chamberLength = document.getElementById('chamber_length_override');
    if (chamberLength && motor.chamber_length) {
        chamberLength.placeholder = `Auto: ${(motor.chamber_length * 1000).toFixed(0)} mm`;
    }
    
    // Auto-fill injector parameters
    if (injector.exit_velocity) {
        document.getElementById('injection_velocity').value = Math.round(injector.exit_velocity);
    }
    
    if (injector.n_holes) {
        document.getElementById('n_holes_override').placeholder = `Auto: ${injector.n_holes} holes`;
    }
    
    if (injector.pressure_drop && motor.chamber_pressure) {
        const dropPercent = (injector.pressure_drop / motor.chamber_pressure * 100).toFixed(0);
        document.getElementById('pressure_drop_percent').value = dropPercent;
    }
    
    // Update CAD button status
    document.getElementById('generateCADBtn').disabled = false;
}

// Switch configuration tabs
function switchConfigTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(content => {
        if (content.parentElement.id === 'designConfigPanel') {
            content.style.display = 'none';
        }
    });
    
    // Remove active class from all tabs
    document.querySelectorAll('#designConfigPanel .tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab
    document.getElementById(tabName).style.display = 'block';
    
    // Add active class to clicked tab
    event.target.classList.add('active');
}

// Apply design configuration
function applyDesignConfig() {
    // Store configuration
    window.designConfig = {
        motor: {
            chamber_material: document.getElementById('chamber_material').value,
            wall_thickness: parseFloat(document.getElementById('wall_thickness').value),
            safety_factor: parseFloat(document.getElementById('safety_factor').value),
            nozzle_material: document.getElementById('nozzle_material').value,
            chamber_length_override: parseFloat(document.getElementById('chamber_length_override').value) || null,
            nozzle_contour: document.getElementById('nozzle_contour').value
        },
        injector: {
            material: document.getElementById('injector_material').value,
            injection_velocity: parseFloat(document.getElementById('injection_velocity').value),
            pressure_drop_percent: parseFloat(document.getElementById('pressure_drop_percent').value),
            n_holes_override: parseInt(document.getElementById('n_holes_override').value) || null,
            hole_pattern: document.getElementById('hole_pattern').value,
            cooling_channels: document.getElementById('cooling_channels').value
        }
    };
    
    // Hide config panel and show export panel
    document.getElementById('designConfigPanel').style.display = 'none';
    document.getElementById('exportActionsPanel').style.display = 'block';
    
    // Enable CAD generation
    document.getElementById('generateCADBtn').disabled = false;
    
    showSuccess('Design configuration applied successfully');
}

// CAD Generation Functions
async function generateCAD() {
    if (!currentResults) {
        showError('Please calculate motor first');
        return;
    }
    
    if (!window.designConfig) {
        showError('Please configure design parameters first');
        showDesignConfig();
        return;
    }
    
    showLoading(true);
    const cadStatus = document.getElementById('cadStatus');
    cadStatus.textContent = 'Generating 3D model...';
    
    try {
        // Merge analysis results with design config
        const cadData = {
            ...currentResults.motor,
            design_config: window.designConfig
        };
        
        const response = await fetch('/api/export-cad', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                motor_data: cadData,
                formats: ['stl', 'technical_drawings', 'materials', '3d_plot']
            })
        });
        
        if (!response.ok) throw new Error('CAD generation failed');
        
        const data = await response.json();
        
        // Display 3D visualization
        if (data.cad_exports.plotly_3d) {
            document.getElementById('cad3DPanel').style.display = 'block';
            const plot3D = JSON.parse(data.cad_exports.plotly_3d);
            Plotly.newPlot('motor_3d_plot', plot3D.data, plot3D.layout, {responsive: true});
        }
        
        // Enable STL export button
        document.getElementById('exportSTLBtn').disabled = false;
        window.cadExportData = data.cad_exports;
        
        cadStatus.textContent = 'CAD model generated successfully!';
        showSuccess('3D CAD model generated successfully');
        
    } catch (error) {
        cadStatus.textContent = 'CAD generation failed';
        showError('Failed to generate CAD: ' + error.message);
    } finally {
        showLoading(false);
    }
}

async function exportSTL() {
    if (!currentResults || !currentResults.motor) {
        showError('Please run motor analysis first');
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/export-stl', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                motor_data: currentResults.motor,
                export_format: 'stl'
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        // Check if response is JSON (error) or binary (STL file)
        const contentType = response.headers.get('content-type');
        
        if (contentType && contentType.includes('application/json')) {
            const result = await response.json();
            if (result.status === 'error') {
                throw new Error(result.error || 'STL export failed');
            }
            // Handle multiple files case
            if (result.stl_files && result.stl_files.length > 0) {
                showSuccess('STL files generated. Check downloads folder.');
                return;
            }
        }
        
        // Handle single STL file download
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        
        const motorName = currentResults.motor.motor_name || 'UZAYTEK_motor';
        a.download = `${motorName}_assembly.stl`;
        
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showSuccess('STL file exported successfully');
        
    } catch (error) {
        console.error('Error exporting STL:', error);
        showError('Error exporting STL: ' + error.message);
    } finally {
        showLoading(false);
    }
}

// OpenRocket Export Functions
async function exportOpenRocket() {
    if (!currentResults) {
        showError('Please calculate motor first');
        return;
    }
    
    showLoading(true);
    const openrocketStatus = document.getElementById('openrocketStatus');
    openrocketStatus.textContent = 'Generating OpenRocket file...';
    
    try {
        const response = await fetch('/api/export-openrocket', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                motor_data: currentResults.motor
            })
        });
        
        if (!response.ok) throw new Error('OpenRocket export failed');
        
        const data = await response.json();
        
        // Store eng file content for download
        window.openrocketData = data;
        document.getElementById('downloadEngBtn').disabled = false;
        
        openrocketStatus.textContent = `Motor: ${data.motor_designation} - Ready for download`;
        showSuccess('OpenRocket file generated successfully');
        
    } catch (error) {
        openrocketStatus.textContent = 'Export failed';
        showError('Failed to export OpenRocket: ' + error.message);
    } finally {
        showLoading(false);
    }
}

async function downloadEngFile() {
    if (!currentResults || !currentResults.motor) {
        showError('Please run motor analysis first');
        return;
    }
    
    showLoading(true);
    
    try {
        const response = await fetch('/api/export-openrocket', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                motor_data: currentResults.motor,
                motor_name: document.getElementById('motor_name')?.value || 'UZAYTEK_Motor'
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // Download the .eng file
            const blob = new Blob([result.eng_file_content], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = result.download_filename || 'motor.eng';
            document.body.appendChild(a);
            a.click();
            URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
            showSuccess('OpenRocket motor file downloaded successfully');
        } else {
            throw new Error(result.error || 'Failed to generate motor file');
        }
        
    } catch (error) {
        console.error('Error downloading motor file:', error);
        showError('Error downloading motor file: ' + error.message);
    } finally {
        showLoading(false);
    }
}

// Complete Package Generation
async function generateCompletePackage() {
    if (!currentResults) {
        showError('Please calculate motor first');
        return;
    }
    
    showLoading(true);
    const packageStatus = document.getElementById('packageStatus');
    packageStatus.textContent = 'Generating complete package...';
    
    try {
        const response = await fetch('/api/generate-complete-package', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                motor_data: currentResults.motor,
                package_options: {
                    include_cad: true,
                    include_openrocket: true,
                    include_analysis: true,
                    include_manufacturing: true
                }
            })
        });
        
        if (!response.ok) throw new Error('Package generation failed');
        
        const data = await response.json();
        
        // Download as JSON package
        const blob = new Blob([JSON.stringify(data.complete_package, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${data.package_info.motor_name}_complete_package.json`;
        a.click();
        URL.revokeObjectURL(url);
        
        packageStatus.textContent = 'Complete package downloaded!';
        showSuccess('Complete design package generated successfully');
        
    } catch (error) {
        packageStatus.textContent = 'Package generation failed';
        showError('Failed to generate package: ' + error.message);
    } finally {
        showLoading(false);
    }
}

// 3D View Controls
function rotate3DView() {
    if (window.Plotly) {
        Plotly.relayout('motor_3d_plot', {
            'scene.camera': {
                eye: {
                    x: 1.5 * Math.cos(Date.now() / 1000),
                    y: 1.5 * Math.sin(Date.now() / 1000),
                    z: 0.5
                }
            }
        });
    }
}

function reset3DView() {
    if (window.Plotly) {
        Plotly.relayout('motor_3d_plot', {
            'scene.camera': {
                eye: {x: 1.25, y: 1.25, z: 1.25}
            }
        });
    }
}

function toggleWireframe() {
    // This would toggle wireframe mode - implementation depends on plot type
    console.log('Wireframe toggle not implemented yet');
}

// Parametric Analysis
async function calculateParametric() {
    try {
        // Check if required elements exist
        if (!document.getElementById('param_type') || 
            !document.getElementById('param_start') || 
            !document.getElementById('param_end') || 
            !document.getElementById('param_steps')) {
            showError('Parametric analysis form elements not found');
            return;
        }
        
        showLoading(true);
        showMessage('Parametric analysis started...', 'info');
        
        // Get form data
        const paramType = document.getElementById('param_type').value;
        const paramStart = parseFloat(document.getElementById('param_start').value);
        const paramEnd = parseFloat(document.getElementById('param_end').value);
        const paramSteps = parseInt(document.getElementById('param_steps').value);
        
        // Validate parametric inputs
        if (isNaN(paramStart) || isNaN(paramEnd) || isNaN(paramSteps)) {
            throw new Error('Invalid parametric analysis inputs');
        }
        
        if (paramStart >= paramEnd) {
            throw new Error('Start value must be less than end value');
        }
        
        if (paramSteps < 3 || paramSteps > 50) {
            throw new Error('Number of steps must be between 3 and 50');
        }
        
        const baseData = getFormData();
        
        const requestData = {
            ...baseData,
            param_type: paramType,
            param_start: paramStart,
            param_end: paramEnd,
            param_steps: paramSteps
        };
        
        console.log('Sending parametric analysis request:', requestData);
        
        const response = await fetch('/parametric-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
        }
        
        const result = await response.json();
        
        if (result.error) {
            throw new Error(result.error);
        }
        
        console.log('Parametric analysis result:', result);
        
        // Display parametric plot
        const plotContainer = document.getElementById('parametric_plot');
        if (!plotContainer) {
            // Create plot container if it doesn't exist
            const parametricTab = document.getElementById('parametric_tab');
            if (parametricTab) {
                const newContainer = document.createElement('div');
                newContainer.id = 'parametric_plot';
                newContainer.className = 'plot-container';
                parametricTab.appendChild(newContainer);
            }
        }
        
        if (result.plot_data) {
            let plotData;
            // Handle both string and object plot data
            if (typeof result.plot_data === 'string') {
                plotData = JSON.parse(result.plot_data);
            } else {
                plotData = result.plot_data;
            }
            
            Plotly.newPlot('parametric_plot', plotData.data, plotData.layout, {responsive: true});
            
            // Show the parametric tab if hidden
            const parametricTab = document.getElementById('parametric_tab');
            if (parametricTab && parametricTab.style.display === 'none') {
                parametricTab.style.display = 'block';
            }
        } else if (result.plot) {
            // Alternative: check for 'plot' field
            const plotData = typeof result.plot === 'string' ? JSON.parse(result.plot) : result.plot;
            Plotly.newPlot('parametric_plot', plotData.data, plotData.layout, {responsive: true});
        } else {
            showWarning('No plot data received from parametric analysis');
        }
        
        showSuccess('Parametric analysis completed successfully');
        
    } catch (error) {
        console.error('Parametric analysis error:', error);
        showError('Parametric analysis failed: ' + error.message);
    } finally {
        showLoading(false);
    }
}

// Trajectory Analysis
async function calculateTrajectory() {
    try {
        // Check if required elements exist
        const requiredElements = ['initial_mass', 'final_mass', 'drag_coefficient', 'reference_area'];
        for (const elementId of requiredElements) {
            if (!document.getElementById(elementId)) {
                showError(`Trajectory analysis form element not found: ${elementId}`);
                return;
            }
        }
        
        showLoading(true);
        showMessage('Trajectory analysis started...', 'info');
        
        // Get trajectory specific data
        const initialMass = parseFloat(document.getElementById('initial_mass').value);
        const finalMass = parseFloat(document.getElementById('final_mass').value);
        const dragCoeff = parseFloat(document.getElementById('drag_coefficient').value);
        const refArea = parseFloat(document.getElementById('reference_area').value);
        const trajAltStart = parseFloat(document.getElementById('traj_alt_start')?.value || 0);
        const trajAltEnd = parseFloat(document.getElementById('traj_alt_end')?.value || 10000);
        const trajPoints = parseInt(document.getElementById('traj_points')?.value || 20);
        const launchAngle = parseFloat(document.getElementById('launch_angle')?.value || 90);
        const windSpeed = parseFloat(document.getElementById('wind_speed')?.value || 0);
        
        // Validate trajectory inputs
        if (isNaN(initialMass) || isNaN(finalMass) || isNaN(dragCoeff) || isNaN(refArea)) {
            throw new Error('Invalid trajectory analysis inputs');
        }
        
        if (initialMass <= finalMass) {
            throw new Error('Initial mass must be greater than final mass');
        }
        
        if (dragCoeff <= 0 || refArea <= 0) {
            throw new Error('Drag coefficient and reference area must be positive');
        }
        
        if (trajAltStart >= trajAltEnd) {
            throw new Error('Starting altitude must be less than final altitude');
        }
        
        const baseData = getFormData();
        
        const requestData = {
            ...baseData,
            initial_mass: initialMass,
            final_mass: finalMass,
            drag_coefficient: dragCoeff,
            reference_area: refArea,
            trajectory_start_altitude: trajAltStart,
            trajectory_end_altitude: trajAltEnd,
            trajectory_points: trajPoints,
            launch_angle: launchAngle,
            wind_speed: windSpeed
        };
        
        console.log('Sending trajectory analysis request:', requestData);
        
        // Call trajectory analysis API
        const response = await fetch('/api/trajectory-analysis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
        }
        
        const result = await response.json();
        
        if (result.status === 'error' || result.error) {
            throw new Error(result.error || 'Trajectory analysis failed');
        }
        
        console.log('Trajectory analysis result:', result);
        
        // Display trajectory plot
        const plotContainer = document.getElementById('trajectory_plot');
        if (!plotContainer) {
            // Create plot container if it doesn't exist
            const trajectoryTab = document.getElementById('trajectory_tab');
            if (trajectoryTab) {
                const newContainer = document.createElement('div');
                newContainer.id = 'trajectory_plot';
                newContainer.className = 'plot-container';
                trajectoryTab.appendChild(newContainer);
            }
        }
        
        if (result.plot_data) {
            try {
                console.log('Plot data type:', typeof result.plot_data);
                if (typeof result.plot_data === 'string') {
                    console.log('Plot data preview:', result.plot_data.substring(0, 100));
                }
                
                let plotData;
                if (typeof result.plot_data === 'string') {
                    plotData = JSON.parse(result.plot_data);
                } else {
                    plotData = result.plot_data; // Already parsed
                }
                
                Plotly.newPlot('trajectory_plot', plotData.data, plotData.layout, {responsive: true});
                console.log('Trajectory plot created successfully');
                
                // Show the trajectory tab if hidden
                const trajectoryTab = document.getElementById('trajectory_tab');
                if (trajectoryTab && trajectoryTab.style.display === 'none') {
                    trajectoryTab.style.display = 'block';
                }
            } catch (parseError) {
                console.error('Plot data parsing error:', parseError);
                console.error('Raw plot data:', result.plot_data);
                showWarning('Plot visualization failed, but trajectory data is available');
            }
        } else {
            showWarning('No plot data received from trajectory analysis');
        }
        
        // Show success message with engine data
        if (result.engine_data) {
            const engineData = result.engine_data;
            showMessage(`Trajectory analysis completed! Engine: ${engineData.thrust.toFixed(0)}N thrust, ${engineData.isp.toFixed(1)}s Isp`, 'success');
        } else {
            showMessage('Trajectory analysis completed successfully!', 'success');
        }
        
    } catch (error) {
        showError('Trajectory analysis failed: ' + error.message);
    } finally {
        showLoading(false);
    }
}

// Display Motor Design Table
function displayMotorTable(motorData) {
    const motorTableBody = document.querySelector('#motor_table tbody');
    if (!motorTableBody) return;
    
    const motorRows = [
        ['Throat Diameter', (motorData.throat_diameter * 1000).toFixed(1), 'mm'],
        ['Exit Diameter', (motorData.exit_diameter * 1000).toFixed(1), 'mm'],
        ['Expansion Ratio', motorData.expansion_ratio.toFixed(1), '-'],
        ['Chamber Diameter', (motorData.chamber_diameter * 1000).toFixed(1), 'mm'],
        ['Chamber Length', (motorData.chamber_length * 1000).toFixed(1), 'mm'],
        ['Chamber Volume', (motorData.chamber_volume * 1e6).toFixed(1), 'cm³'],
        ['Chamber Pressure', (motorData.chamber_pressure).toFixed(1), 'bar'],
        ['Thrust', (motorData.thrust).toFixed(0), 'N'],
        ['Specific Impulse', motorData.isp.toFixed(1), 's'],
        ['Characteristic Velocity', motorData.c_star.toFixed(0), 'm/s'],
        ['Thrust Coefficient', motorData.cf.toFixed(3), '-'],
        ['Mass Flow Rate', motorData.mdot_total.toFixed(3), 'kg/s']
    ];
    
    motorTableBody.innerHTML = '';
    motorRows.forEach(([param, value, unit]) => {
        const row = motorTableBody.insertRow();
        row.insertCell(0).textContent = param;
        row.insertCell(1).textContent = value;
        row.insertCell(2).textContent = unit;
    });
}

// Display Injector Design Table
function displayInjectorTable(injectorData) {
    const injectorTableBody = document.querySelector('#injector_table tbody');
    if (!injectorTableBody) return;
    
    const injectorRows = [
        ['Type', injectorData.type, '-'],
        ['Exit Velocity', injectorData.exit_velocity.toFixed(1), 'm/s'],
        ['Reynolds Number', injectorData.reynolds_number.toFixed(0), '-'],
        ['Pressure Drop', injectorData.pressure_drop.toFixed(2), 'bar']
    ];
    
    // Add type-specific parameters
    if (injectorData.type === 'showerhead') {
        injectorRows.push(['Number of Holes', injectorData.n_holes || 'N/A', '-']);
        injectorRows.push(['Hole Diameter', injectorData.hole_diameter ? injectorData.hole_diameter.toFixed(2) : 'N/A', 'mm']);
        injectorRows.push(['L/D Ratio', injectorData.l_d_ratio ? injectorData.l_d_ratio.toFixed(1) : 'N/A', '-']);
    } else if (injectorData.type === 'pintle') {
        injectorRows.push(['Outer Diameter', injectorData.outer_diameter ? injectorData.outer_diameter.toFixed(1) : 'N/A', 'mm']);
        injectorRows.push(['Pintle Diameter', injectorData.pintle_diameter ? injectorData.pintle_diameter.toFixed(1) : 'N/A', 'mm']);
        injectorRows.push(['Gap', injectorData.gap ? injectorData.gap.toFixed(2) : 'N/A', 'mm']);
    }
    
    // Add common parameters
    injectorRows.push(['Discharge Coefficient', injectorData.discharge_coefficient ? injectorData.discharge_coefficient.toFixed(3) : 'N/A', '-']);
    injectorRows.push(['Injection Area', injectorData.injection_area ? (injectorData.injection_area * 1e6).toFixed(2) : 'N/A', 'mm²']);
    
    // Add injector diameter if available
    if (injectorData.injector_diameter) {
        injectorRows.push(['Max Injector Diameter', injectorData.injector_diameter.toFixed(1), 'mm']);
    }
    
    injectorRows.push(['Weber Number', injectorData.weber_number ? injectorData.weber_number.toFixed(0) : 'N/A', '-']);
    injectorRows.push(['Momentum Ratio', injectorData.momentum_ratio ? injectorData.momentum_ratio.toFixed(2) : 'N/A', '-']);
    injectorRows.push(['Mixing Efficiency', injectorData.mixing_efficiency ? (injectorData.mixing_efficiency * 100).toFixed(1) : 'N/A', '%']);
    
    injectorTableBody.innerHTML = '';
    injectorRows.forEach(([param, value, unit]) => {
        const row = injectorTableBody.insertRow();
        row.insertCell(0).textContent = param;
        row.insertCell(1).textContent = value;
        row.insertCell(2).textContent = unit;
    });
}