// Solid Rocket Motor Analysis (SRMA) - JavaScript Implementation
// High-precision calculations with Monte Carlo analysis capabilities

class SolidRocketMotorAnalyzer {
    constructor() {
        this.tolerance = 1e-6; // Calculation tolerance (0.0001% error rate)
        this.maxIterations = 1000;
        this.monteCarloRuns = 10000;
        this.results = {};
        this.thrustCurve = [];
        this.pressureCurve = [];
        
        // Physical constants
        this.constants = {
            R: 8314.4621, // Universal gas constant (J/kmol·K)
            g0: 9.80665, // Standard gravity (m/s²)
            atmosphericPressure: 101325, // Pa
            stefanBoltzmann: 5.670374419e-8 // W/m²·K⁴
        };
        
        this.bindEvents();
    }

    bindEvents() {
        // Auto-calculate expansion ratio when diameters change
        document.getElementById('throat-diameter').addEventListener('input', this.updateExpansionRatio.bind(this));
        document.getElementById('exit-diameter').addEventListener('input', this.updateExpansionRatio.bind(this));
        
        // Auto-calculate masses when parameters change
        const massInputs = ['density', 'outer-diameter', 'inner-diameter', 'grain-length', 'grain-count'];
        massInputs.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('input', this.calculatePropellantMass.bind(this));
            }
        });
        
        // Update total masses when individual masses change
        const individualMasses = ['case-mass', 'nozzle-mass', 'insulation-mass', 'avionics-mass', 'closure-mass'];
        individualMasses.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('input', this.updateTotalMasses.bind(this));
            }
        });
    }

    // Tab functionality
    openTab(evt, tabName) {
        const tabcontent = document.getElementsByClassName("tab-content");
        const tabbuttons = document.getElementsByClassName("tab-button");
        
        for (let i = 0; i < tabcontent.length; i++) {
            tabcontent[i].classList.remove("active");
        }
        
        for (let i = 0; i < tabbuttons.length; i++) {
            tabbuttons[i].classList.remove("active");
        }
        
        document.getElementById(tabName).classList.add("active");
        evt.currentTarget.classList.add("active");
    }

    // Toggle grain parameter sections based on grain type
    toggleGrainParameters() {
        const grainType = document.getElementById('grain-type').value;
        const starConfig = document.getElementById('star-config');
        const finocylConfig = document.getElementById('finocyl-config');
        
        // Hide all config sections
        starConfig.style.display = 'none';
        finocylConfig.style.display = 'none';
        
        // Show relevant config section
        switch(grainType) {
            case 'star':
                starConfig.style.display = 'block';
                break;
            case 'finocyl':
                finocylConfig.style.display = 'block';
                break;
        }
    }

    // Calculate expansion ratio
    updateExpansionRatio() {
        const dt = parseFloat(document.getElementById('throat-diameter').value) || 0;
        const de = parseFloat(document.getElementById('exit-diameter').value) || 0;
        
        if (dt > 0 && de > 0) {
            const expansionRatio = Math.pow(de / dt, 2);
            document.getElementById('expansion-ratio').value = expansionRatio.toFixed(2);
        }
    }

    // Calculate characteristic velocity
    calculateCharVelocity() {
        const tc = parseFloat(document.getElementById('flame-temp').value) || 3200;
        const gamma = parseFloat(document.getElementById('gamma').value) || 1.25;
        const M = parseFloat(document.getElementById('molecular-weight').value) || 28.5;
        
        // c* = sqrt(gamma * R * Tc) / (gamma * ((gamma + 1) / 2)^((gamma + 1) / (2 * (gamma - 1))))
        const numerator = Math.sqrt(gamma * this.constants.R * tc / M);
        const exponent = (gamma + 1) / (2 * (gamma - 1));
        const denominator = gamma * Math.pow((gamma + 1) / 2, exponent);
        
        const cStar = numerator / denominator;
        document.getElementById('char-velocity').value = cStar.toFixed(1);
        
        return cStar;
    }

    // Calculate propellant mass based on grain geometry
    calculatePropellantMass() {
        const density = parseFloat(document.getElementById('density').value) || 1800;
        const outerDiameter = parseFloat(document.getElementById('outer-diameter').value) || 100;
        const innerDiameter = parseFloat(document.getElementById('inner-diameter').value) || 30;
        const grainLength = parseFloat(document.getElementById('grain-length').value) || 200;
        const grainCount = parseFloat(document.getElementById('grain-count').value) || 3;
        const grainType = document.getElementById('grain-type').value;
        
        // Convert to meters
        const Do = outerDiameter / 1000;
        const Di = innerDiameter / 1000;
        const L = grainLength / 1000;
        
        let grainVolume = 0;
        
        switch(grainType) {
            case 'cylindrical':
                grainVolume = Math.PI * (Math.pow(Do/2, 2) - Math.pow(Di/2, 2)) * L;
                break;
                
            case 'star':
                const starPoints = parseFloat(document.getElementById('star-points').value) || 6;
                const starRadius = parseFloat(document.getElementById('star-radius').value) || 15;
                const Rs = (starRadius / 1000) / 2; // Convert to meters and radius
                
                // Simplified star grain volume calculation
                const starArea = Math.PI * (Math.pow(Do/2, 2) - Math.pow(Di/2, 2)) + 
                                starPoints * 0.5 * Rs * Rs * Math.sin(2 * Math.PI / starPoints);
                grainVolume = starArea * L;
                break;
                
            case 'finocyl':
                const finCount = parseFloat(document.getElementById('fin-count').value) || 4;
                const finWidth = (parseFloat(document.getElementById('fin-width').value) || 8) / 1000;
                const finLength = (parseFloat(document.getElementById('fin-length').value) || 20) / 1000;
                
                // Base cylindrical volume plus fin slots
                const baseVolume = Math.PI * (Math.pow(Do/2, 2) - Math.pow(Di/2, 2)) * L;
                const finVolume = finCount * finWidth * finLength * L;
                grainVolume = baseVolume + finVolume;
                break;
                
            case 'slotted':
                // Simplified slotted grain calculation
                grainVolume = Math.PI * (Math.pow(Do/2, 2) - Math.pow(Di/2, 2)) * L * 1.2; // 20% increase for slots
                break;
                
            default:
                grainVolume = Math.PI * (Math.pow(Do/2, 2) - Math.pow(Di/2, 2)) * L;
        }
        
        const totalVolume = grainVolume * grainCount;
        const propellantMass = totalVolume * density;
        
        document.getElementById('propellant-mass').value = propellantMass.toFixed(3);
        this.updateTotalMasses();
        
        return propellantMass;
    }

    // Update total masses
    updateTotalMasses() {
        const propellantMass = parseFloat(document.getElementById('propellant-mass').value) || 0;
        const caseMass = parseFloat(document.getElementById('case-mass').value) || 0;
        const nozzleMass = parseFloat(document.getElementById('nozzle-mass').value) || 0;
        const insulationMass = parseFloat(document.getElementById('insulation-mass').value) || 0;
        const avionicsMass = parseFloat(document.getElementById('avionics-mass').value) || 0;
        const closureMass = parseFloat(document.getElementById('closure-mass').value) || 0;
        
        const dryMass = caseMass + nozzleMass + insulationMass + avionicsMass + closureMass;
        const wetMass = dryMass + propellantMass;
        
        document.getElementById('dry-mass').value = dryMass.toFixed(3);
        document.getElementById('wet-mass').value = wetMass.toFixed(3);
    }

    // Main analysis function
    async performAnalysis() {
        try {
            document.getElementById('calculate-btn').innerHTML = '<div class="loading"></div> Calculating...';
            
            // Collect all input parameters
            const params = this.collectParameters();
            
            // Validate inputs
            if (!this.validateInputs(params)) {
                throw new Error('Girdi parametreleri eksik veya hatalı!');
            }
            
            // Perform calculations
            const results = await this.calculatePerformance(params);
            
            // Display results
            this.displayResults(results);
            
            // Generate curves
            this.generateCurves(params, results);
            
            document.getElementById('calculate-btn').innerHTML = 'Start Analysis';
            
        } catch (error) {
            console.error('Analysis error:', error);
            alert('Analysis error: ' + error.message);
            document.getElementById('calculate-btn').innerHTML = 'Start Analysis';
        }
    }

    // Collect all parameters from the form
    collectParameters() {
        return {
            // Propellant properties
            propellantName: document.getElementById('propellant-name').value,
            density: parseFloat(document.getElementById('density').value) || 1800,
            heatValue: parseFloat(document.getElementById('heat-value').value) || 2500,
            flameTemp: parseFloat(document.getElementById('flame-temp').value) || 3200,
            molecularWeight: parseFloat(document.getElementById('molecular-weight').value) || 28.5,
            gamma: parseFloat(document.getElementById('gamma').value) || 1.25,
            charVelocity: parseFloat(document.getElementById('char-velocity').value) || 1550,
            erosiveK: parseFloat(document.getElementById('erosive-k').value) || 0.0002,
            erosiveM: parseFloat(document.getElementById('erosive-m').value) || 0.8,
            tempCoeff: parseFloat(document.getElementById('temp-coeff').value) || 0.002,
            burnRateCoeff: parseFloat(document.getElementById('burn-rate-coeff').value) || 8.2,
            burnRateExp: parseFloat(document.getElementById('burn-rate-exp').value) || 0.35,
            
            // Grain geometry
            grainCount: parseFloat(document.getElementById('grain-count').value) || 3,
            webThickness: parseFloat(document.getElementById('web-thickness').value) || 25,
            grainType: document.getElementById('grain-type').value,
            outerDiameter: parseFloat(document.getElementById('outer-diameter').value) || 100,
            innerDiameter: parseFloat(document.getElementById('inner-diameter').value) || 30,
            grainLength: parseFloat(document.getElementById('grain-length').value) || 200,
            grainGap: parseFloat(document.getElementById('grain-gap').value) || 2,
            insulationThickness: parseFloat(document.getElementById('insulation-thickness').value) || 3,
            
            // Chamber properties
            chamberVolume: parseFloat(document.getElementById('chamber-volume').value) || 2.5,
            yieldStrength: parseFloat(document.getElementById('yield-strength').value) || 250,
            safetyFactor: parseFloat(document.getElementById('safety-factor').value) || 2.5,
            linerThickness: parseFloat(document.getElementById('liner-thickness').value) || 2,
            linerDensity: parseFloat(document.getElementById('liner-density').value) || 1200,
            initialTemp: parseFloat(document.getElementById('initial-temp').value) || 298,
            caseThickness: parseFloat(document.getElementById('case-thickness').value) || 8,
            
            // Nozzle properties
            throatDiameter: parseFloat(document.getElementById('throat-diameter').value) || 15,
            exitDiameter: parseFloat(document.getElementById('exit-diameter').value) || 35,
            expansionRatio: parseFloat(document.getElementById('expansion-ratio').value) || 5.44,
            convergentAngle: parseFloat(document.getElementById('convergent-angle').value) || 45,
            divergentAngle: parseFloat(document.getElementById('divergent-angle').value) || 15,
            nozzleEfficiency: parseFloat(document.getElementById('nozzle-efficiency').value) || 0.95,
            erosionFactor: parseFloat(document.getElementById('erosion-factor').value) || 0.001,
            
            // Efficiency factors
            combustionEfficiency: parseFloat(document.getElementById('combustion-efficiency').value) || 0.95,
            cfEfficiency: parseFloat(document.getElementById('cf-efficiency').value) || 0.98,
            overallEfficiency: parseFloat(document.getElementById('overall-efficiency').value) || 0.92,
            dischargeCoeff: parseFloat(document.getElementById('discharge-coeff').value) || 0.98,
            kineticEfficiency: parseFloat(document.getElementById('kinetic-efficiency').value) || 0.97,
            divergenceLoss: parseFloat(document.getElementById('divergence-loss').value) || 0.02,
            twoPhaseeLoss: parseFloat(document.getElementById('two-phase-loss').value) || 0.98,
            
            // Initial conditions
            ignitionDelay: parseFloat(document.getElementById('ignition-delay').value) || 50,
            atmPressure: parseFloat(document.getElementById('atm-pressure').value) || 101.325,
            testAltitude: parseFloat(document.getElementById('test-altitude').value) || 0,
            ambientTemp: parseFloat(document.getElementById('ambient-temp').value) || 298,
            humidity: parseFloat(document.getElementById('humidity').value) || 60,
            windSpeed: parseFloat(document.getElementById('wind-speed').value) || 0,
            chamberPressure: parseFloat(document.getElementById('chamber-pressure').value) || 7,
            
            // Mass breakdown
            propellantMass: parseFloat(document.getElementById('propellant-mass').value) || 0,
            caseMass: parseFloat(document.getElementById('case-mass').value) || 2.5,
            nozzleMass: parseFloat(document.getElementById('nozzle-mass').value) || 0.5,
            insulationMass: parseFloat(document.getElementById('insulation-mass').value) || 0.3,
            avionicsMass: parseFloat(document.getElementById('avionics-mass').value) || 0.2,
            closureMass: parseFloat(document.getElementById('closure-mass').value) || 0.8,
            dryMass: parseFloat(document.getElementById('dry-mass').value) || 0,
            wetMass: parseFloat(document.getElementById('wet-mass').value) || 0,
            
            // Measurement parameters
            pressureSensorRange: parseFloat(document.getElementById('pressure-sensor-range').value) || 10,
            samplingFreq: parseFloat(document.getElementById('sampling-freq').value) || 1000,
            loadCellCapacity: parseFloat(document.getElementById('load-cell-capacity').value) || 5000,
            calibrationFactor: parseFloat(document.getElementById('calibration-factor').value) || 1.0,
            dataCollectionTime: parseFloat(document.getElementById('data-collection-time').value) || 10,
            filterCutoff: parseFloat(document.getElementById('filter-cutoff').value) || 100,
            uncertaintyLevel: parseFloat(document.getElementById('uncertainty-level').value) || 2
        };
    }

    // Validate input parameters
    validateInputs(params) {
        // Critical parameter validation
        if (params.density <= 0) {
            alert('Yakıt yoğunluğu pozitif olmalıdır!');
            return false;
        }
        
        if (params.throatDiameter <= 0 || params.exitDiameter <= 0) {
            alert('Nozul çapları pozitif olmalıdır!');
            return false;
        }
        
        if (params.exitDiameter <= params.throatDiameter) {
            alert('Çıkış çapı boğaz çapından büyük olmalıdır!');
            return false;
        }
        
        if (params.propellantMass <= 0) {
            alert('Fuel mass must be calculated or entered!');
            return false;
        }
        
        if (params.safetyFactor < 1) {
            alert('Emniyet katsayısı 1\'den büyük olmalıdır!');
            return false;
        }
        
        return true;
    }

    // Calculate motor performance
    async calculatePerformance(params) {
        const results = {};
        
        // Calculate burning surface area and burning time
        const burningAnalysis = this.calculateBurningCharacteristics(params);
        
        // Calculate chamber pressure using iterative method
        const chamberPressure = this.calculateChamberPressure(params, burningAnalysis);
        
        // Calculate thrust characteristics
        const thrustAnalysis = this.calculateThrustCharacteristics(params, chamberPressure);
        
        // Calculate specific impulse
        const specificImpulse = this.calculateSpecificImpulse(params, thrustAnalysis);
        
        // Calculate safety analysis
        const safetyAnalysis = this.calculateSafetyAnalysis(params, chamberPressure);
        
        // Combine results
        Object.assign(results, burningAnalysis, thrustAnalysis, specificImpulse, safetyAnalysis);
        
        // Calculate performance coefficients
        results.thrustWeightRatio = results.maxThrust / (params.wetMass * this.constants.g0);
        results.loadingDensity = (params.propellantMass / (params.chamberVolume / 1000)) * 100; // Convert to %
        results.calculatedCstar = params.charVelocity * params.combustionEfficiency;
        results.thrustCoefficient = results.maxThrust / (chamberPressure.maxPressure * 1e6 * Math.PI * Math.pow(params.throatDiameter / 2000, 2));
        
        this.results = results;
        return results;
    }

    // Calculate burning characteristics
    calculateBurningCharacteristics(params) {
        const results = {};
        
        // Convert dimensions to meters
        const Do = params.outerDiameter / 1000;
        const Di = params.innerDiameter / 1000;
        const L = params.grainLength / 1000;
        const web = params.webThickness / 1000;
        
        // Calculate initial burning surface area
        let initialBurningSurface = 0;
        
        switch(params.grainType) {
            case 'cylindrical':
                // Port area only (ends inhibited)
                initialBurningSurface = Math.PI * Di * L * params.grainCount;
                break;
                
            case 'star':
                const starPoints = parseFloat(document.getElementById('star-points').value) || 6;
                const starRadius = parseFloat(document.getElementById('star-radius').value) || 15;
                const Rs = (starRadius / 1000) / 2;
                
                // Port perimeter with star geometry
                const starPerimeter = Math.PI * Di + starPoints * 2 * Rs * Math.sin(Math.PI / starPoints);
                initialBurningSurface = starPerimeter * L * params.grainCount;
                break;
                
            case 'finocyl':
                const finCount = parseFloat(document.getElementById('fin-count').value) || 4;
                const finWidth = (parseFloat(document.getElementById('fin-width').value) || 8) / 1000;
                const finLength = (parseFloat(document.getElementById('fin-length').value) || 20) / 1000;
                
                // Port area plus fin surfaces
                const portSurface = Math.PI * Di * L;
                const finSurface = finCount * 2 * finLength * L; // Both sides of fins
                initialBurningSurface = (portSurface + finSurface) * params.grainCount;
                break;
                
            default:
                initialBurningSurface = Math.PI * Di * L * params.grainCount;
        }
        
        // Calculate burn time (simplified)
        const averageBurnRate = params.burnRateCoeff * Math.pow(params.chamberPressure, params.burnRateExp) / 1000; // Convert mm/s to m/s
        results.burnTime = web / averageBurnRate;
        
        results.initialBurningSurface = initialBurningSurface;
        results.averageBurnRate = averageBurnRate * 1000; // Convert back to mm/s
        
        return results;
    }

    // Calculate chamber pressure using iterative solution
    calculateChamberPressure(params, burningAnalysis) {
        const results = {};
        
        // Convert units
        const At = Math.PI * Math.pow(params.throatDiameter / 2000, 2); // m²
        const rho = params.density; // kg/m³
        const cStar = params.charVelocity * params.combustionEfficiency; // m/s
        
        let pressure = params.chamberPressure * 1e6; // Convert MPa to Pa
        let converged = false;
        let iterations = 0;
        
        // Iterative pressure calculation
        while (!converged && iterations < this.maxIterations) {
            const oldPressure = pressure;
            
            // Burn rate at current pressure
            const burnRate = params.burnRateCoeff * Math.pow(pressure / 1e6, params.burnRateExp) / 1000; // m/s
            
            // Mass flow rate
            const massFlowRate = rho * burningAnalysis.initialBurningSurface * burnRate;
            
            // Chamber pressure from mass flow and throat conditions
            pressure = (massFlowRate * cStar) / At;
            
            // Temperature correction
            const tempCorrection = 1 + params.tempCoeff * (params.initialTemp - 298);
            pressure *= tempCorrection;
            
            // Check convergence
            if (Math.abs(pressure - oldPressure) / oldPressure < this.tolerance) {
                converged = true;
            }
            
            iterations++;
        }
        
        if (!converged) {
            console.warn('Chamber pressure calculation did not converge');
        }
        
        results.maxPressure = pressure / 1e6; // Convert back to MPa
        results.iterations = iterations;
        results.converged = converged;
        
        return results;
    }

    // Calculate thrust characteristics
    calculateThrustCharacteristics(params, chamberPressure) {
        const results = {};
        
        // Convert units
        const At = Math.PI * Math.pow(params.throatDiameter / 2000, 2); // m²
        const Ae = Math.PI * Math.pow(params.exitDiameter / 2000, 2); // m²
        const Pc = chamberPressure.maxPressure * 1e6; // Pa
        const Pa = params.atmPressure * 1000; // Pa
        const gamma = params.gamma;
        
        // Calculate exit pressure using isentropic relations
        const expansionRatio = Ae / At;
        const pressureRatio = Math.pow(1 + (gamma - 1) / 2 * Math.pow(1 / expansionRatio * Math.sqrt((gamma + 1) / 2), gamma / (gamma - 1)), -gamma / (gamma - 1));
        const Pe = Pc * pressureRatio;
        
        // Calculate exit velocity
        const Ve = Math.sqrt(2 * gamma / (gamma - 1) * this.constants.R * params.flameTemp / params.molecularWeight * (1 - Math.pow(Pe / Pc, (gamma - 1) / gamma)));
        
        // Calculate thrust
        const thrustPressure = At * Pc * Math.sqrt(2 * gamma * gamma / (gamma - 1) * Math.pow(2 / (gamma + 1), (gamma + 1) / (gamma - 1)));
        const thrustMomentum = (Pe - Pa) * Ae;
        const theoreticalThrust = (thrustPressure + thrustMomentum) * params.nozzleEfficiency;
        
        results.maxThrust = theoreticalThrust;
        results.avgThrust = theoreticalThrust * 0.85; // Simplified average
        results.totalImpulse = results.avgThrust * results.burnTime || (params.propellantMass * params.charVelocity * params.overallEfficiency / this.constants.g0);
        results.exitVelocity = Ve;
        results.exitPressure = Pe / 1000; // Convert to kPa
        
        return results;
    }

    // Calculate specific impulse
    calculateSpecificImpulse(params, thrustAnalysis) {
        const results = {};
        
        const totalImpulse = thrustAnalysis.totalImpulse || (params.propellantMass * params.charVelocity * params.overallEfficiency / this.constants.g0);
        results.specificImpulse = totalImpulse / (params.propellantMass * this.constants.g0);
        
        return results;
    }

    // Calculate safety analysis
    calculateSafetyAnalysis(params, chamberPressure) {
        const results = {};
        
        // Case stress calculation (thin-walled cylinder)
        const Do = params.outerDiameter / 1000; // Outer diameter in meters
        const t = params.caseThickness / 1000; // Wall thickness in meters
        const Pc = chamberPressure.maxPressure * 1e6; // Pressure in Pa
        
        // Hoop stress
        const hoopStress = (Pc * Do) / (2 * t) / 1e6; // Convert to MPa
        
        results.caseStress = hoopStress;
        results.actualSafetyFactor = params.yieldStrength / hoopStress;
        
        // Nozzle erosion
        const burnTime = results.burnTime || 5; // Default burn time if not calculated
        results.nozzleErosion = params.erosionFactor * burnTime;
        
        return results;
    }

    // Display results in the UI
    displayResults(results) {
        // Basic performance
        document.getElementById('total-impulse').textContent = (results.totalImpulse || 0).toFixed(1) + ' N·s';
        document.getElementById('max-thrust').textContent = (results.maxThrust || 0).toFixed(1) + ' N';
        document.getElementById('avg-thrust').textContent = (results.avgThrust || 0).toFixed(1) + ' N';
        document.getElementById('specific-impulse').textContent = (results.specificImpulse || 0).toFixed(1) + ' s';
        document.getElementById('burn-time').textContent = (results.burnTime || 0).toFixed(2) + ' s';
        document.getElementById('max-pressure').textContent = (results.maxPressure || 0).toFixed(2) + ' MPa';
        
        // Performance coefficients
        document.getElementById('thrust-weight-ratio').textContent = (results.thrustWeightRatio || 0).toFixed(2);
        document.getElementById('loading-density').textContent = (results.loadingDensity || 0).toFixed(1) + ' %';
        document.getElementById('calculated-cstar').textContent = (results.calculatedCstar || 0).toFixed(0) + ' m/s';
        document.getElementById('thrust-coefficient').textContent = (results.thrustCoefficient || 0).toFixed(3);
        
        // Safety analysis
        document.getElementById('case-stress').textContent = (results.caseStress || 0).toFixed(1) + ' MPa';
        document.getElementById('actual-safety-factor').textContent = (results.actualSafetyFactor || 0).toFixed(2);
        document.getElementById('nozzle-erosion').textContent = (results.nozzleErosion || 0).toFixed(3) + ' mm';
    }

    // Generate thrust and pressure curves
    generateCurves(params, results) {
        const timeSteps = 100;
        const burnTime = results.burnTime || 5;
        const dt = burnTime / timeSteps;
        
        this.thrustCurve = [];
        this.pressureCurve = [];
        
        for (let i = 0; i <= timeSteps; i++) {
            const t = i * dt;
            
            // Simplified thrust curve (could be made more sophisticated)
            let thrustFactor = 1.0;
            if (t < burnTime * 0.1) {
                // Startup transient
                thrustFactor = t / (burnTime * 0.1);
            } else if (t > burnTime * 0.9) {
                // Tail-off
                thrustFactor = (burnTime - t) / (burnTime * 0.1);
            }
            
            const thrust = results.maxThrust * thrustFactor;
            const pressure = results.maxPressure * thrustFactor;
            
            this.thrustCurve.push({ time: t, thrust: thrust });
            this.pressureCurve.push({ time: t, pressure: pressure });
        }
        
        this.drawCurves();
    }

    // Draw curves on canvas
    drawCurves() {
        this.drawThrustCurve();
        this.drawPressureCurve();
    }

    drawThrustCurve() {
        const canvas = document.getElementById('thrust-curve');
        const ctx = canvas.getContext('2d');
        
        // Clear canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Set up coordinates
        const margin = 60;
        const width = canvas.width - 2 * margin;
        const height = canvas.height - 2 * margin;
        
        if (this.thrustCurve.length === 0) return;
        
        const maxTime = Math.max(...this.thrustCurve.map(p => p.time));
        const maxThrust = Math.max(...this.thrustCurve.map(p => p.thrust));
        
        // Draw axes
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(margin, margin);
        ctx.lineTo(margin, margin + height);
        ctx.lineTo(margin + width, margin + height);
        ctx.stroke();
        
        // Draw grid
        ctx.strokeStyle = '#ddd';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 10; i++) {
            const x = margin + (i / 10) * width;
            const y = margin + (i / 10) * height;
            
            ctx.beginPath();
            ctx.moveTo(x, margin);
            ctx.lineTo(x, margin + height);
            ctx.stroke();
            
            ctx.beginPath();
            ctx.moveTo(margin, y);
            ctx.lineTo(margin + width, y);
            ctx.stroke();
        }
        
        // Draw curve
        ctx.strokeStyle = '#3498db';
        ctx.lineWidth = 3;
        ctx.beginPath();
        
        for (let i = 0; i < this.thrustCurve.length; i++) {
            const point = this.thrustCurve[i];
            const x = margin + (point.time / maxTime) * width;
            const y = margin + height - (point.thrust / maxThrust) * height;
            
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.stroke();
        
        // Add labels
        ctx.fillStyle = '#333';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('İtki Eğrisi', canvas.width / 2, 30);
        ctx.fillText('Zaman (s)', canvas.width / 2, canvas.height - 10);
        
        ctx.save();
        ctx.translate(15, canvas.height / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('İtki (N)', 0, 0);
        ctx.restore();
        
        // Add scale labels
        ctx.textAlign = 'right';
        ctx.fillText(maxThrust.toFixed(0) + ' N', margin - 10, margin + 5);
        ctx.fillText('0', margin - 10, margin + height + 5);
        
        ctx.textAlign = 'center';
        ctx.fillText('0', margin, margin + height + 20);
        ctx.fillText(maxTime.toFixed(1) + ' s', margin + width, margin + height + 20);
    }

    drawPressureCurve() {
        const canvas = document.getElementById('pressure-curve');
        const ctx = canvas.getContext('2d');
        
        // Clear canvas
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Set up coordinates
        const margin = 60;
        const width = canvas.width - 2 * margin;
        const height = canvas.height - 2 * margin;
        
        if (this.pressureCurve.length === 0) return;
        
        const maxTime = Math.max(...this.pressureCurve.map(p => p.time));
        const maxPressure = Math.max(...this.pressureCurve.map(p => p.pressure));
        
        // Draw axes
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(margin, margin);
        ctx.lineTo(margin, margin + height);
        ctx.lineTo(margin + width, margin + height);
        ctx.stroke();
        
        // Draw grid
        ctx.strokeStyle = '#ddd';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 10; i++) {
            const x = margin + (i / 10) * width;
            const y = margin + (i / 10) * height;
            
            ctx.beginPath();
            ctx.moveTo(x, margin);
            ctx.lineTo(x, margin + height);
            ctx.stroke();
            
            ctx.beginPath();
            ctx.moveTo(margin, y);
            ctx.lineTo(margin + width, y);
            ctx.stroke();
        }
        
        // Draw curve
        ctx.strokeStyle = '#e74c3c';
        ctx.lineWidth = 3;
        ctx.beginPath();
        
        for (let i = 0; i < this.pressureCurve.length; i++) {
            const point = this.pressureCurve[i];
            const x = margin + (point.time / maxTime) * width;
            const y = margin + height - (point.pressure / maxPressure) * height;
            
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.stroke();
        
        // Add labels
        ctx.fillStyle = '#333';
        ctx.font = '14px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Basınç Eğrisi', canvas.width / 2, 30);
        ctx.fillText('Zaman (s)', canvas.width / 2, canvas.height - 10);
        
        ctx.save();
        ctx.translate(15, canvas.height / 2);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText('Basınç (MPa)', 0, 0);
        ctx.restore();
        
        // Add scale labels
        ctx.textAlign = 'right';
        ctx.fillText(maxPressure.toFixed(1) + ' MPa', margin - 10, margin + 5);
        ctx.fillText('0', margin - 10, margin + height + 5);
        
        ctx.textAlign = 'center';
        ctx.fillText('0', margin, margin + height + 20);
        ctx.fillText(maxTime.toFixed(1) + ' s', margin + width, margin + height + 20);
    }

    // Monte Carlo Analysis
    async runMonteCarloAnalysis() {
        try {
            document.getElementById('monte-carlo-btn').innerHTML = '<div class="loading"></div> Monte Carlo Analysis...';
            
            const params = this.collectParameters();
            const results = [];
            
            // Define parameter uncertainties (based on uncertainty level)
            const uncertaintyFactor = params.uncertaintyLevel / 100;
            
            for (let run = 0; run < this.monteCarloRuns; run++) {
                // Generate random variations
                const variedParams = this.generateRandomParameters(params, uncertaintyFactor);
                
                try {
                    // Calculate performance for this run
                    const result = await this.calculatePerformance(variedParams);
                    results.push(result);
                } catch (error) {
                    // Skip failed runs
                    continue;
                }
                
                // Update progress occasionally
                if (run % 1000 === 0) {
                    const progress = (run / this.monteCarloRuns) * 100;
                    document.getElementById('monte-carlo-btn').innerHTML = `<div class="loading"></div> ${progress.toFixed(0)}%`;
                    await new Promise(resolve => setTimeout(resolve, 1)); // Allow UI update
                }
            }
            
            // Analyze results
            const statistics = this.calculateStatistics(results);
            this.displayMonteCarloResults(statistics);
            
            document.getElementById('monte-carlo-btn').innerHTML = 'Monte Carlo Analysis';
            
        } catch (error) {
            console.error('Monte Carlo analysis error:', error);
            alert('Monte Carlo analysis error: ' + error.message);
            document.getElementById('monte-carlo-btn').innerHTML = 'Monte Carlo Analysis';
        }
    }

    // Generate random parameter variations
    generateRandomParameters(baseParams, uncertaintyFactor) {
        const variedParams = { ...baseParams };
        
        // Parameters to vary (with their uncertainty factors)
        const variableParams = [
            'density', 'burnRateCoeff', 'burnRateExp', 'charVelocity',
            'combustionEfficiency', 'nozzleEfficiency', 'throatDiameter',
            'exitDiameter', 'propellantMass', 'yieldStrength'
        ];
        
        variableParams.forEach(param => {
            if (variedParams[param] !== undefined) {
                const baseValue = variedParams[param];
                const variation = this.normalRandom() * uncertaintyFactor * baseValue;
                variedParams[param] = Math.max(baseValue + variation, baseValue * 0.5); // Ensure positive values
            }
        });
        
        return variedParams;
    }

    // Generate normal random number (Box-Muller transform)
    normalRandom() {
        if (this.spare !== undefined) {
            const temp = this.spare;
            this.spare = undefined;
            return temp;
        }
        
        const u = Math.random();
        const v = Math.random();
        const mag = Math.sqrt(-2 * Math.log(u));
        
        this.spare = mag * Math.cos(2 * Math.PI * v);
        return mag * Math.sin(2 * Math.PI * v);
    }

    // Calculate statistics from Monte Carlo results
    calculateStatistics(results) {
        if (results.length === 0) {
            return { successRate: 0 };
        }
        
        const statistics = {};
        
        // Success rate
        statistics.successRate = (results.length / this.monteCarloRuns) * 100;
        
        // Calculate statistics for key parameters
        const parameters = ['maxThrust', 'specificImpulse', 'burnTime', 'maxPressure'];
        
        parameters.forEach(param => {
            const values = results.map(r => r[param]).filter(v => v !== undefined && !isNaN(v));
            
            if (values.length > 0) {
                const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
                const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length;
                const stdDev = Math.sqrt(variance);
                
                // Sort for percentiles
                values.sort((a, b) => a - b);
                const p5 = values[Math.floor(values.length * 0.05)];
                const p95 = values[Math.floor(values.length * 0.95)];
                
                statistics[param] = {
                    mean: mean,
                    stdDev: stdDev,
                    cv: (stdDev / mean) * 100, // Coefficient of variation (%)
                    p5: p5,
                    p95: p95,
                    confidenceInterval: `${p5.toFixed(2)} - ${p95.toFixed(2)}`
                };
            }
        });
        
        return statistics;
    }

    // Display Monte Carlo results
    displayMonteCarloResults(statistics) {
        if (statistics.maxThrust) {
            document.getElementById('thrust-std-dev').textContent = statistics.maxThrust.cv.toFixed(1) + ' %';
            document.getElementById('confidence-interval').textContent = statistics.maxThrust.confidenceInterval;
        }
        
        document.getElementById('success-rate').textContent = statistics.successRate.toFixed(1) + ' %';
    }
}

// Global functions for HTML event handlers
let analyzer;

function openTab(evt, tabName) {
    if (analyzer) {
        analyzer.openTab(evt, tabName);
    }
}

function toggleGrainParameters() {
    if (analyzer) {
        analyzer.toggleGrainParameters();
    }
}

function calculateCharVelocity() {
    if (analyzer) {
        analyzer.calculateCharVelocity();
    }
}

function calculatePropellantMass() {
    if (analyzer) {
        analyzer.calculatePropellantMass();
    }
}

function performAnalysis() {
    if (analyzer) {
        analyzer.performAnalysis();
    }
}

function runMonteCarloAnalysis() {
    if (analyzer) {
        analyzer.runMonteCarloAnalysis();
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    analyzer = new SolidRocketMotorAnalyzer();
    
    // Set default values
    analyzer.calculatePropellantMass();
    analyzer.updateTotalMasses();
});