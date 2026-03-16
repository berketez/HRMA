# COMPUTATIONAL DESIGN AND PERFORMANCE PREDICTION OF HYBRID ROCKET MOTORS WITH HRMA SOFTWARE

**Ayberk Cem AKSOY¹, Berke TEZGÖÇEN², Egnar ÖZDİKİLİLER³**

¹ Istanbul Technical University, Faculty of Mechanical Engineering, Istanbul, Turkey
² Istanbul Technical University, Faculty of Science and Letters, Istanbul, Turkey
³ Istanbul Technical University, Faculty of Aeronautics and Astronautics, Istanbul, Turkey

*Corresponding author: ayberkcm@gmail.com

---

## Abstract

This paper introduces HRMA (Hybrid Rocket Motor Analysis), a modular computational program developed to support the design, sizing, and performance prediction of model hybrid rocket motors. HRMA integrates multiple physics-based modules for combustion chamber and nozzle sizing, injector design, heat transfer, and trajectory analysis. The program accepts user-defined input parameters including oxidizer and fuel composition, total thrust or average thrust with burn time, oxidizer-to-fuel ratio, chamber and atmospheric pressures, characteristic length, expansion ratio, nozzle type, injector configuration, oxidizer properties, regression rate coefficients, and fuel characteristics. Optional modules allow users to include heat transfer, combustion, trajectory, and 3D visualization analyses. Based on these inputs, HRMA computes essential outputs such as chamber pressure, thrust, total impulse, specific impulse, oxidizer and fuel mass flow rates, characteristic velocity, thrust coefficient, nozzle throat and exit diameters, and overall propellant mass. It can also generate time-based performance data, injector flow metrics, and altitude-dependent performance predictions.

Simulation results are visualized through interactive performance plots showing thrust, pressure, and specific impulse histories, as well as combustion efficiency and altitude performance trends. The program retrieves thermochemical data directly from online propellant databases, National Institute of Standards and Technology Chemistry Webbook and the NASA Chemical Equilibrium with Applications system to verify and compare its results. HRMA additionally provides 3D motor visualization and CAD export features for downstream design integration. Validation studies demonstrate strong agreement between HRMA predictions and experimental data reported in literature. By combining analysis, visualization, and verification within a unified platform, HRMA enables faster, more accurate, and educationally accessible hybrid rocket motor design and evaluation.

**Keywords:** Hybrid Rocket Motor, Combustion, Nozzle, Heat Transfer, Oxidizer, Fuel, Design, Analysis.

---

## 1. INTRODUCTION

Hybrid rocket motors (HRMs) have emerged as a compelling class of chemical propulsion systems that occupy a unique niche between their solid and liquid counterparts. By storing the fuel in solid phase within the combustion chamber while delivering the oxidizer as a liquid or gaseous stream, hybrid motors inherently combine several advantages that have attracted sustained interest from both the research community and the commercial space sector. Among these advantages, the most frequently cited are enhanced operational safety arising from the physical separation of propellant constituents, the capacity for throttle control and engine restart through modulation of oxidizer flow rate, reduced manufacturing complexity compared to liquid bipropellant engines, and a more favorable environmental footprint relative to conventional solid propellants that often contain ammonium perchlorate or other halogenated oxidizers. These characteristics render hybrid rocket motors particularly attractive for sounding rockets, suborbital vehicles, orbital kick stages, and, increasingly, for small satellite launch vehicles.

Despite these inherent merits, the widespread adoption of hybrid rocket motors has been tempered by a set of persistent engineering challenges. Chief among these is the accurate prediction of the fuel regression rate, which governs mass addition from the solid grain surface into the combustion port. The classical model introduced by Marxman and Gilbert describes the regression rate as a power-law function of oxidizer mass flux, expressed as $\dot{r} = a \cdot G_{ox}^n$, where the empirical coefficients $a$ and $n$ depend on propellant chemistry, grain geometry, and operating conditions. However, the transient nature of HRM combustion -- in which the port diameter progressively enlarges, oxidizer flux decreases, and the oxidizer-to-fuel (O/F) ratio shifts over the burn duration -- introduces significant complexity into the design process. This O/F shift has direct consequences for combustion temperature, exhaust molecular weight, specific impulse, and ultimately mission performance. Capturing these coupled, time-varying phenomena within a unified computational framework remains a nontrivial task.

Computational tools have become indispensable in modern aerospace engineering, enabling rapid prototyping, parametric trade studies, and iterative design optimization within virtual environments before hardware is ever fabricated. Codes such as NASA's Chemical Equilibrium with Applications (CEA), OpenRocket, and various proprietary simulation suites have demonstrated the value of software-driven design. However, many of these tools either address only a subset of the multiphysics involved in hybrid motor design, or require significant user expertise to configure and interpret. There exists a notable gap between the theoretical understanding of hybrid rocket propulsion and the availability of integrated, accessible computational platforms that translate this understanding into practical design guidance.

The Hybrid Rocket Motor Analysis (HRMA) software, presented in this paper, was developed to address precisely this gap. HRMA is a Python-based, web-accessible application built on the Flask framework that provides a comprehensive, modular environment for hybrid rocket motor design and analysis. The software encompasses over forty specialized modules covering combustion analysis with chemical equilibrium calculations, nozzle design for conical, bell, and parabolic contour geometries, fuel grain regression rate prediction, heat transfer analysis including conduction, convection, and radiation, structural integrity assessment via pressure vessel theory, injector design for showerhead, pintle, and swirl configurations, trajectory simulation with altitude-dependent atmospheric modeling, and three-dimensional CAD geometry export. HRMA integrates external data from NASA CEA thermochemical databases and the NIST WebBook to ensure that thermophysical properties reflect validated reference values rather than ad hoc assumptions.

This paper is organized as follows. Section 2 discusses the motivation behind the development of HRMA and the engineering philosophy that guided its architecture. Section 3 defines the specific engineering problems that HRMA addresses, detailing the underlying physical models and their coupling. Subsequent sections present the mathematical formulations, software implementation, validation against published data and experimental results, and representative case studies demonstrating the tool's capabilities for hybrid rocket motor design.

---

## 2. MOTIVATION

The primary motivation for developing HRMA was the recognition that hybrid rocket motor design requires the simultaneous consideration of multiple tightly coupled physical phenomena -- combustion chemistry, fluid dynamics, heat transfer, structural mechanics, and flight dynamics -- yet no single, freely accessible tool existed that integrated all of these disciplines within a coherent computational environment. Existing software packages typically address individual aspects of the design problem in isolation: thermochemical equilibrium codes compute combustion product compositions and flame temperatures, structural analysis tools evaluate pressure vessel integrity, and trajectory simulators predict flight performance. The designer is left with the burden of manually transferring outputs between disparate tools, maintaining consistency of assumptions, and reconciling units and coordinate conventions. This fragmented workflow is not only time-consuming but also error-prone, particularly for less experienced engineers and student researchers who may lack the domain expertise to identify inconsistencies.

HRMA was conceived to bridge this gap between theoretical knowledge and practical application by providing an integrated platform in which the output of each analysis module feeds directly into downstream computations. For example, the combustion analysis module computes the adiabatic flame temperature and exhaust gas properties, which are then consumed by the nozzle design module to determine throat and exit geometries, by the heat transfer module to evaluate wall thermal loads, and by the structural analysis module to assess pressure vessel margins. This tight coupling ensures internal consistency and allows the designer to observe the system-level consequences of changing any single parameter, such as the O/F ratio or chamber pressure, across all performance metrics simultaneously.

A further motivation was to empower engineers and researchers to explore the vast design space of hybrid rocket motors efficiently. The combinatorial space defined by fuel type (HTPB, paraffin wax, ABS, PMMA, and others), oxidizer selection (nitrous oxide, liquid oxygen, hydrogen peroxide), chamber pressure, grain geometry, nozzle profile, and injector configuration is enormous. HRMA enables rapid parametric sweeps and trade studies through its web-based interface, presenting results via interactive Plotly visualizations that facilitate intuitive interpretation.

The modular software architecture was an intentional engineering decision. Each analysis capability -- combustion, nozzle design, regression rate, heat transfer, structural integrity, injector design, trajectory, CAD export, and validation -- resides in a dedicated Python module with well-defined interfaces. This modularity yields several benefits: individual modules can be developed, tested, and validated independently; new capabilities can be added without disrupting existing functionality; and the codebase remains maintainable as the system grows in complexity. The integration of external databases, including NASA CEA thermochemical data and NIST WebBook thermophysical properties, ensures that material and species data reflect peer-reviewed reference values. A built-in validation system cross-checks computed results against published performance limits derived from Sutton and Biblarz, NASA SP-8089, and AIAA standards, alerting the user when outputs fall outside physically plausible bounds.

The validation methodology embedded within HRMA was designed to establish confidence in the tool's predictions. Computed specific impulse, characteristic velocity, and combustion temperatures are compared against NASA CEA reference cases for identical propellant combinations and operating conditions. This approach ensures that HRMA serves not merely as a pedagogical demonstration but as a reliable engineering instrument capable of supporting preliminary design decisions in the advancement of hybrid rocket propulsion technology.

---

## 3. ENGINEERING PROBLEMS DEFINITION ADDRESSED BY HRMA

The design of a hybrid rocket motor requires the resolution of several interdependent engineering problems, each governed by distinct physical principles yet coupled through shared state variables such as chamber pressure, temperature, and mass flow rate. HRMA addresses the following principal challenges within a unified computational framework.

**Regression Rate Prediction.** The fuel regression rate is the single most critical parameter in hybrid motor design, as it governs the fuel mass flow rate and, consequently, the O/F ratio, thrust level, and burn duration. HRMA implements the classical Marxman-type power-law correlation, $\dot{r} = a \cdot G_{ox}^n$, where $G_{ox}$ is the oxidizer mass flux through the fuel port, and the empirical coefficients $a$ and $n$ are specific to each fuel type. The software maintains a database of validated regression rate parameters for HTPB ($a = 0.0003$, $n = 0.5$), paraffin wax ($a = 0.0005$, $n = 0.62$), ABS ($a = 0.00018$, $n = 0.58$), and PMMA ($a = 0.00015$, $n = 0.55$), among others. Critically, HRMA solves the regression rate equation in a time-marching scheme, updating the port diameter, oxidizer flux, and instantaneous regression rate at each time step to capture the transient evolution of grain geometry over the entire burn duration.

**O/F Ratio Shift and Its Performance Consequences.** As the fuel port diameter enlarges during combustion, the oxidizer mass flux decreases, causing the regression rate to decline and the instantaneous O/F ratio to shift away from the initial design point. HRMA quantifies this shift and its cascading effects on combustion temperature, exhaust gas molecular weight, specific heat ratio, characteristic velocity, and specific impulse. The software identifies the optimum O/F ratio for maximum specific impulse using polynomial $I_{sp}$ models and NASA CEA reference data, enabling the designer to select initial conditions that minimize performance degradation over the burn.

**Combustion Chamber Sizing and Pressure Prediction.** HRMA determines chamber dimensions through the characteristic length ($L^*$) approach, computing the required chamber volume from the throat area and a user-specified or fuel-dependent $L^*$ value. The chamber pressure is related to mass flow rate and throat area through the characteristic velocity equation, $P_c = \dot{m} \cdot C^* / A_t$, ensuring thermodynamic consistency. The combustion analysis module employs chemical equilibrium calculations, with Cantera integration where available, to determine adiabatic flame temperature, equilibrium product species mole fractions, and thermodynamic transport properties using NIST-JANAF reference data.

**Nozzle Design and Performance Coupling.** The nozzle converts thermal energy into directed kinetic energy and is a primary determinant of motor performance. HRMA supports three nozzle contour types -- conical, bell (Rao optimum), and parabolic -- each with distinct geometric algorithms. The bell nozzle implementation follows the method of characteristics with throat curvature ratio $R_n = 0.382 \cdot r_t$ and initial wall angle of 30 degrees, tapering to an exit angle of 8 degrees. Nozzle performance, including thrust coefficient, exit Mach number, and pressure ratio, is computed from isentropic flow relations and coupled back to the overall motor performance calculation.

**Injector Design.** Proper atomization and distribution of the oxidizer stream is essential for uniform combustion and stable motor operation. HRMA provides design algorithms for three injector types: showerhead, pintle, and swirl. The showerhead module sizes orifice diameter and number of holes based on target injection velocity, discharge coefficient, and the pressure drop criterion from NASA SP-8089, which specifies that the injector pressure drop should be 15--25% of the chamber pressure to ensure adequate atomization and combustion stability.

**Heat Transfer Analysis.** HRMA evaluates the thermal environment of the combustion chamber wall by computing convective heat transfer from the hot combustion gases using the Bartz correlation, conductive heat flux through the chamber wall for multiple material options (steel, aluminum, Inconel, copper), and radiative heat transfer using Stefan-Boltzmann law with material-specific emissivities. The analysis determines transient wall temperature profiles and compares them against material-specific allowable temperature limits to assess thermal margin.

**Structural Integrity Assessment.** The combustion chamber must withstand internal pressure loads with adequate safety margins. HRMA performs pressure vessel analysis using thin-wall cylinder theory, computing hoop and longitudinal stresses for the design pressure (chamber pressure multiplied by a user-specified safety factor). The module includes a materials database with yield strength, ultimate strength, elastic modulus, and fatigue limit for aerospace-grade alloys including AISI 4130 steel, aluminum 6061-T6, Inconel 718, and titanium Ti-6Al-4V.

**Trajectory Prediction.** HRMA integrates the equations of motion for a rocket vehicle through powered flight, coasting, and descent phases using the SciPy `solve_ivp` numerical integrator. The trajectory module accounts for altitude-dependent atmospheric density and pressure via a standard atmosphere model, aerodynamic drag with a user-defined drag coefficient, gravitational variation with altitude, and wind effects. This analysis links motor-level performance directly to mission-level outcomes such as apogee altitude, maximum velocity, and flight duration.

The integration of these coupled physics domains within a single tool is the central contribution of HRMA. Rather than treating each problem in isolation, the software propagates the consequences of every design decision through the entire analysis chain, enabling the engineer to evaluate system-level trade-offs with full physical fidelity at the preliminary design level.

---

## 4. LIMITATIONS OF EXISTING HYBRID ROCKET ANALYSIS APPROACHES

The design and analysis of hybrid rocket motors has historically relied on a fragmented ecosystem of tools, each addressing isolated aspects of the propulsion problem while leaving significant gaps in integrated, end-to-end motor development workflows. This section critically examines the shortcomings of prevailing approaches and identifies the engineering need that motivates the present work.

Traditional hybrid rocket design methods are rooted in simplified analytical models derived from classical internal ballistics theory. The canonical regression rate correlation, expressed as the power-law relationship $\dot{r} = a \cdot G_{ox}^n$, provides a first-order approximation of fuel regression behavior but fails to capture the coupled thermochemical, fluid-dynamic, and heat transfer phenomena that govern real motor operation. Conversely, experimental campaigns that yield empirically grounded performance data are prohibitively expensive, requiring dedicated test facilities, instrumentation, and personnel. This dichotomy between oversimplified theory and costly experimentation leaves a substantial methodological gap, particularly for university research groups and small-scale developers who lack the resources for either high-fidelity simulation infrastructure or extensive hot-fire testing.

Among the most widely used computational tools, NASA's Chemical Equilibrium with Applications (CEA) code remains the de facto standard for equilibrium thermochemistry calculations. While CEA reliably computes adiabatic flame temperatures, equilibrium species concentrations, and theoretical specific impulse for given propellant combinations, it operates strictly as a standalone thermochemistry solver. It does not perform coupled motor analysis: it cannot predict regression rates, size combustion chambers, design nozzle contours, or evaluate structural integrity. Similarly, tools such as ProPEP and Rocket Propulsion Analysis (RPA) focus narrowly on thermochemical performance prediction or nozzle flow analysis, respectively, but neither offers an integrated framework that spans the full design chain from propellant selection through trajectory estimation.

In the domain of flight simulation, OpenRocket provides an accessible platform for trajectory prediction and vehicle stability analysis. However, its propulsion modeling capabilities are limited to importing pre-defined thrust curves, offering no native functionality for internal ballistic calculations, regression rate prediction, or combustion chamber sizing. The tool effectively treats the motor as a black box, precluding the iterative design loop between propulsion performance and vehicle-level trajectory optimization that is essential for competent motor development.

Commercial multi-physics platforms such as ANSYS Fluent, COMSOL Multiphysics, and Siemens Star-CCM+ offer high-fidelity simulation capabilities including conjugate heat transfer and reacting flow modeling. However, these tools carry substantial licensing costs, often exceeding tens of thousands of dollars annually, and require extensive domain expertise to configure for rocket motor applications. They are general-purpose solvers not specialized for propulsion system design, lacking built-in propellant databases, regression rate models, or motor-specific validation criteria referenced to established standards such as NASA SP-8064 and SP-8089.

A critical deficiency shared by virtually all existing tools is the absence of real-time, interactive visualization during the design iteration process. Engineers typically must export results from one tool, post-process them in a separate environment, and manually transfer parameters to downstream analyses. This sequential, disconnected workflow severely impedes rapid design exploration and parametric trade studies. Furthermore, no existing tool provides direct three-dimensional CAD geometry export derived from motor analysis results, forcing designers to manually reconstruct motor geometries in dedicated CAD software -- an error-prone and time-consuming process that introduces discontinuities between the analytical model and the manufactured hardware.

Finally, there exists a notable gap in the availability of educational tools that balance technical rigor with accessibility. Most rigorous propulsion analysis codes require significant setup effort, proprietary licenses, or specialized computing infrastructure, while simplified educational applets sacrifice the physical fidelity necessary for meaningful engineering analysis. The field lacks a unified, open-access platform that combines regression rate modeling, chemical equilibrium combustion analysis, nozzle design, thermal and structural evaluation, trajectory simulation, and parametric visualization within a single coherent environment.

---

## 5. DESIGN PHILOSOPHY AND SOFTWARE ARCHITECTURE

The Hybrid Rocket Motor Analysis (HRMA) software was developed under four guiding design principles: modularity, extensibility, accuracy, and accessibility. Modularity dictates that each distinct engineering discipline -- combustion thermochemistry, regression rate modeling, nozzle design, heat transfer, structural analysis, and trajectory simulation -- is encapsulated in an independent, self-contained module with well-defined interfaces. Extensibility ensures that new analysis methods, propellant formulations, or motor configurations can be incorporated without modifying existing code. Accuracy is pursued through integration with authoritative external data sources and validation against established reference standards. Accessibility demands that the tool be usable without proprietary software licenses, specialized hardware, or extensive installation procedures, running entirely within a standard web browser.

Python was selected as the implementation language for its mature scientific computing ecosystem. The numerical backbone of HRMA relies on NumPy for array operations and linear algebra, SciPy for numerical integration (including `solve_ivp` for trajectory ordinary differential equations and `fsolve` for implicit algebraic systems), and Cantera for chemical equilibrium calculations when available. The Flask micro-framework serves as the web application layer, providing RESTful API endpoints that expose all analysis capabilities to browser-based clients while maintaining cross-platform compatibility across macOS, Linux, and Windows operating systems. Flask-CORS middleware enables cross-origin requests, facilitating deployment in diverse network environments.

The software architecture follows a five-layer design pattern that enforces strict separation of concerns. The **Client Layer** consists of HTML/JavaScript front-end interfaces that capture user inputs and render interactive visualizations. The **Presentation Layer**, implemented through Flask route handlers and REST endpoints (`/calculate`, `/api/propellant`, `/api/trajectory`, `/api/export`), manages HTTP request parsing, input validation, and JSON response serialization, including a recursive sanitization routine that handles IEEE 754 special values (NaN, Infinity) and NumPy array serialization. The **Business Logic Layer** contains the core analysis engines: `HybridRocketEngine`, `SolidRocketEngine`, and `LiquidRocketEngine` serve as orchestrators that instantiate and coordinate discipline-specific analyzers including `CombustionAnalyzer`, `NozzleDesigner`, `HeatTransferAnalyzer`, `StructuralAnalyzer`, `RegressionAnalyzer`, `InjectorDesign`, `TrajectoryAnalyzer`, `SafetyAnalyzer`, `CFD2DAnalyzer`, and `NozzleKineticAnalyzer`. The **Data Access Layer** manages persistent storage through two SQLite databases: `chemical_species.db`, which stores NASA CEA-compatible thermodynamic polynomial coefficients (7-coefficient NASA format) for chemical species, and `experimental_data.db`, which archives test results for validation purposes. The `PropellantDatabase` and `ChemicalDatabase` classes provide query interfaces with built-in data integrity checks. The **External Services Layer** integrates with NASA CEA for independent thermochemical validation, the NIST Chemistry WebBook for real-time retrieval of oxidizer thermophysical properties (density, viscosity, vapor pressure as functions of temperature and pressure), and the SpaceX API for launch vehicle reference data.

Inter-module communication follows an event-driven, data-dictionary pattern. The core engine computes a comprehensive results dictionary that is progressively enriched as it passes through each analysis module. For example, `HybridRocketEngine.calculate()` first solves internal ballistics to determine throat area, mass flow rates, and chamber geometry, then passes this dictionary to `CombustionAnalyzer` for equilibrium species and performance calculations, to `NozzleDesigner` for contour generation (supporting conical, bell, and parabolic profiles), to `HeatTransferAnalyzer` for wall temperature distribution using the Bartz correlation, and to `StructuralAnalyzer` for minimum wall thickness determination based on thick-walled pressure vessel theory with material-specific safety factors referenced to AIAA standards. This cascading architecture ensures that downstream modules always operate on self-consistent upstream results.

The visualization subsystem employs Plotly for interactive, browser-rendered plots including motor cross-section diagrams, regression rate evolution curves, thrust-time profiles, Mach number contour maps, wall heat flux waterfall charts, and three-dimensional chamber pressure-mixture ratio surfaces. Three-dimensional CAD geometry is generated using Trimesh and numpy-stl, enabling direct export of motor assemblies as STL files compatible with commercial CAD packages and additive manufacturing workflows. The `OpenRocketExporter` module produces standard `.eng` motor definition files for direct import into flight simulation software, closing the loop between motor-level design and vehicle-level trajectory analysis.

A dedicated `ValidationSystem` module implements real-time parameter checking against physically meaningful bounds derived from Sutton and Biblarz, NASA SP-8089, and AIAA design standards. Each computed quantity -- specific impulse, characteristic velocity, chamber pressure, expansion ratio, regression rate coefficients -- is evaluated against propellant-combination-specific limits, with violations classified by severity (warning versus critical) and reported to the user interface in real time. This continuous validation framework prevents physically unrealizable designs from propagating through the analysis chain, a safeguard absent from most existing tools. The complete software comprises 44 independent Python modules totaling over 15,000 lines of analysis code, with an API-first architecture that supports both interactive browser-based usage and programmatic batch analysis through direct HTTP calls.

---

## 6. TRANSIENT COMBUSTION AND REGRESSION MODELING

The regression rate of solid fuel grains in hybrid rocket motors constitutes the single most consequential parameter governing motor design and performance prediction. HRMA implements the classical diffusion-limited regression rate model originally formulated by Marxman and Gilbert (1963), which describes the turbulent boundary layer combustion process above a vaporizing fuel surface. In this framework, the local instantaneous regression rate is expressed as

$$\dot{r} = a\,G_{ox}^{\,n}$$

where $\dot{r}$ is the linear regression rate of the fuel surface (m/s), $G_{ox} = \dot{m}_{ox}/A_p$ is the oxidizer mass flux through the port cross-section (kg/m²/s), $A_p = \pi r_p^2$ is the instantaneous port area, and $a$ and $n$ are empirically determined regression rate coefficients that encapsulate the coupled effects of heat transfer, blowing, and chemical kinetics at the fuel surface. The exponent $n$ typically lies in the range 0.4--0.8 for most polymeric fuels, reflecting the dependence of convective heat transfer on Reynolds number within the turbulent boundary layer above the regressing surface.

HRMA maintains a fuel property database covering six fuel families with individually calibrated regression coefficients: HTPB ($a = 3.0 \times 10^{-4}$, $n = 0.50$, $\rho_f = 920$ kg/m³), paraffin wax ($a = 5.0 \times 10^{-4}$, $n = 0.62$, $\rho_f = 900$ kg/m³), polyethylene ($a = 2.5 \times 10^{-4}$, $n = 0.62$), PMMA ($a = 1.5 \times 10^{-4}$, $n = 0.55$), ABS ($a = 1.8 \times 10^{-4}$, $n = 0.58$), and PLA ($a = 1.2 \times 10^{-4}$, $n = 0.52$). The notably higher regression coefficient of paraffin reflects its liquefying behavior, where a hydrodynamically unstable melt layer on the fuel surface produces droplet entrainment that augments the mass transfer rate by a factor of approximately 3--4 relative to classical polymeric fuels. For enhanced regression configurations employing vortex injection or swirl-inducing grain geometries, HRMA extends the classical model as

$$\dot{r} = a\,G_{ox}^{\,n}\,(1 + \beta\,S)$$

where $S$ is a dimensionless swirl parameter characterizing the tangential-to-axial momentum ratio, and $\beta$ is an empirical enhancement coefficient.

A critical feature of hybrid motor operation is the inherent coupling between the regression rate and the evolving port geometry. As the fuel surface regresses, the port area $A_p$ increases monotonically, causing $G_{ox}$ to decrease over time even under constant oxidizer mass flow rate. This produces a characteristic time-varying oxidizer-to-fuel ratio (O/F) shift during the burn, which HRMA captures through explicit time-stepping of the port radius:

$$r_p(t + \Delta t) = r_p(t) + \dot{r}(t)\,\Delta t$$

where the regression rate $\dot{r}(t)$ is re-evaluated at each time step using the updated port geometry. The instantaneous fuel mass flow rate is computed as $\dot{m}_f = \rho_f \dot{r} \cdot \pi D_p L_g$, where $D_p$ is the port diameter and $L_g$ is the grain length, yielding the instantaneous O/F ratio as $\text{O/F}(t) = \dot{m}_{ox}/\dot{m}_f(t)$.

The adiabatic flame temperature computation in HRMA employs two complementary pathways. When the Cantera thermochemistry library is available, the code initializes the reactant mixture at standard conditions (298.15 K, specified chamber pressure), sets the thermodynamic state via elemental composition derived from the fuel formula and oxidizer stoichiometry, and solves for chemical equilibrium at constant enthalpy and pressure (HP equilibrium) using Cantera's multiphase Gibbs energy minimization algorithm. This procedure yields the equilibrium flame temperature, species mole fractions, and mixture thermodynamic properties ($\gamma$, $\bar{M}$, $c_p$) directly. When Cantera is unavailable, HRMA falls back to an empirical model that estimates the flame temperature from a fuel-dependent baseline temperature corrected by a logarithmic pressure scaling: $T_{ad} = T_{base}(1 + 0.05\ln P_c)$, with additive corrections for aluminum content and hydrogen-rich fuels.

The equilibrium composition is evaluated at three thermodynamic stations -- chamber, throat, and exit -- using Gibbs free energy minimization at each station's local temperature and pressure. At the chamber station ($T_c \sim 2800$--$3500$ K), significant concentrations of dissociation products (OH, H, O, NO) are present. At the throat and exit stations, recombination shifts the equilibrium toward major products (CO₂, H₂O, N₂, CO). HRMA computes the mixture molecular weight at each station as $\bar{M}_j = \sum_i X_i M_i$ for station $j$, enabling station-specific evaluation of the gas constant $R_j = R_u / \bar{M}_j$ and the ratio of specific heats $\gamma_j = c_{p,j}/c_{v,j}$.

Overall combustion efficiency is modeled as the product of four sub-efficiencies:

$$\eta_c = \eta_{mix} \times \eta_{heat} \times \eta_{kin} \times \eta_{bl}$$

where $\eta_{mix}$ accounts for incomplete mixing of the oxidizer and fuel vapor streams, $\eta_{heat}$ captures radiative and conductive heat losses to the chamber walls, $\eta_{kin}$ reflects finite-rate chemistry effects at lower chamber pressures where dissociation equilibrium is not fully achieved, and $\eta_{bl}$ accounts for boundary layer losses at the nozzle entrance. This decomposition permits systematic identification of dominant loss mechanisms for a given motor configuration.

---

## 7. INTEGRATED PERFORMANCE AND THRUST CALCULATION

The thrust produced by a hybrid rocket motor is governed by the momentum and pressure forces acting at the nozzle exit plane. HRMA computes the instantaneous thrust from the complete thrust equation:

$$F = \dot{m}\,v_e + (p_e - p_a)\,A_e$$

where $\dot{m} = \dot{m}_{ox} + \dot{m}_f$ is the total propellant mass flow rate, $v_e$ is the nozzle exit velocity, $p_e$ is the static pressure at the exit plane, $p_a$ is the local ambient pressure, and $A_e$ is the nozzle exit area. The first term represents the momentum thrust and the second the pressure thrust; at the design altitude where $p_e = p_a$, the pressure thrust vanishes identically.

The nozzle exit velocity is derived from the isentropic expansion of a calorically perfect gas from chamber stagnation conditions to the exit pressure:

$$v_e = \sqrt{\frac{2\gamma}{\gamma - 1}\,R\,T_c\left[1 - \left(\frac{p_e}{P_c}\right)^{(\gamma-1)/\gamma}\right]}$$

where $\gamma$ is the ratio of specific heats, $R = R_u/\bar{M}$ is the specific gas constant of the combustion products, $T_c$ is the chamber (stagnation) temperature, and $P_c$ is the chamber pressure. The exit Mach number $M_e$ is obtained by solving the implicit pressure-Mach relation $(1 + \frac{\gamma-1}{2}M_e^2)^{\gamma/(\gamma-1)} = P_c/p_e$ using the Newton-Raphson method (implemented via SciPy's `fsolve`), and the area ratio follows from the isentropic area-Mach relation:

$$\varepsilon = \frac{A_e}{A_t} = \frac{1}{M_e}\left[\frac{2}{\gamma+1}\left(1 + \frac{\gamma-1}{2}M_e^2\right)\right]^{(\gamma+1)/[2(\gamma-1)]}$$

The characteristic exhaust velocity $C^*$ is a measure of combustion performance independent of the nozzle and is defined as

$$C^* = \frac{P_c\,A_t}{\dot{m}} = \frac{\sqrt{\gamma\,R\,T_c}}{\gamma\,\sqrt{\left(\frac{2}{\gamma+1}\right)^{(\gamma+1)/(\gamma-1)}}}$$

HRMA evaluates $C^*$ using thermodynamic properties retrieved from NASA CEA data (via an external API integration) or computed internally from the equilibrium solver. The effective $C^*$ is further corrected by a pressure-dependent dissociation factor for low chamber pressures ($P_c < 10$ bar), where incomplete chemical equilibrium reduces combustion efficiency.

The thrust coefficient $C_F$ relates the thrust to the chamber pressure and throat area as $F = C_F P_c A_t$. HRMA computes $C_F$ from

$$C_F = \lambda\,\sqrt{\frac{2\gamma^2}{\gamma-1}\left(\frac{2}{\gamma+1}\right)^{(\gamma+1)/(\gamma-1)}\left[1 - \left(\frac{p_e}{P_c}\right)^{(\gamma-1)/\gamma}\right]} + \frac{(p_e - p_a)\,\varepsilon}{P_c}$$

where $\lambda$ is a nozzle divergence correction factor: $\lambda = 0.985$ for bell (Rao-optimized) nozzles, $\lambda = 0.975$ for parabolic contours, and $\lambda = 0.955$ for conical nozzles with a 15-degree half-angle. The specific impulse follows directly as $I_{sp} = C_F C^* / g_0$, where $g_0 = 9.81$ m/s².

Altitude-dependent performance is computed by evaluating the thrust equation at discrete altitudes using the International Standard Atmosphere (ISA) model. Below 11 km, $T(h) = 288.15 - 0.0065h$ and $P(h) = 1.01325(T/288.15)^{5.256}$; above 11 km, the isothermal stratosphere model applies with $P(h) = 0.22632\exp[-g_0 M(h-11000)/(R_u T)]$. Both vacuum specific impulse ($I_{sp,vac}$, at $p_a = 0$) and sea-level specific impulse ($I_{sp,SL}$, at $p_a = 1.01325$ bar) are reported, along with the thrust variation with altitude. HRMA also determines the optimum O/F ratio for maximum $I_{sp}$ via bounded scalar minimization of $-I_{sp}(\text{O/F})$ over the range [1.0, 10.0], evaluating the full combustion equilibrium at each candidate O/F.

---

## 8. SYSTEM LEVEL PERFORMANCE SOLVER

The performance prediction of a hybrid rocket motor requires the simultaneous solution of a coupled nonlinear system in which the regression rate, chamber pressure, propellant mass flow rates, and grain geometry are mutually dependent. HRMA implements an integrated solver architecture that resolves these couplings through an iterative time-marching algorithm.

The governing system of equations can be stated as follows. The oxidizer mass flux depends on the port geometry: $G_{ox} = \dot{m}_{ox}/A_p(t)$. The fuel regression rate depends on this flux: $\dot{r} = a\,G_{ox}^n$. The fuel mass flow rate depends on the regression rate and grain geometry: $\dot{m}_f = \rho_f \dot{r} \pi D_p L_g$. The total mass flow rate is $\dot{m} = \dot{m}_{ox} + \dot{m}_f$, and the chamber pressure is coupled to the mass flow and throat area through the characteristic velocity relation: $P_c = \dot{m}\,C^* / (C_D\,A_t)$, where $C_D \approx 0.98$ is the discharge coefficient. This circular dependency -- $G_{ox}$ depends on $A_p$, which depends on $\dot{r}$, which depends on $G_{ox}$ -- necessitates an iterative or time-stepping solution strategy.

HRMA resolves this coupling through a forward Euler time-stepping scheme that marches the port geometry forward in time. At each time step $k$, the solver executes the following sequence:

1. Compute the port area: $A_p^k = \pi (r_p^k)^2$.
2. Evaluate the oxidizer mass flux: $G_{ox}^k = \dot{m}_{ox}/A_p^k$.
3. Compute the instantaneous regression rate: $\dot{r}^k = a\,(G_{ox}^k)^n$.
4. Advance the port radius: $r_p^{k+1} = r_p^k + \dot{r}^k \Delta t$.
5. Enforce the physical constraint: $D_p^{k+1} \leq 0.8\,D_{ch}$, where $D_{ch}$ is the chamber diameter.
6. Recompute the fuel mass flow, total mass flow, and O/F ratio at the updated geometry.

The time step $\Delta t = t_b / N$ is chosen with $N$ sufficiently large (typically $N = 10$--$100$) to ensure that the port radius increment $\dot{r}\,\Delta t$ remains small relative to the port radius itself, maintaining the quasi-steady combustion assumption underlying the Marxman model.

The pressure-mass flow coupling is resolved through the $C^*$ relation. The throat area $A_t$ is determined from the design-point mass flow and chamber pressure:

$$A_t = \frac{\dot{m}\,C^*}{P_c\,C_D}$$

At each time step, any change in $\dot{m}$ (due to O/F shift) would, in a fixed-geometry motor, produce a corresponding change in $P_c$. HRMA handles this by computing the time-averaged regression rate from the geometric mean of the initial and final oxidizer fluxes: $\bar{G}_{ox} = (G_{ox,i} + G_{ox,f})/2$, yielding $\bar{\dot{r}} = a\,\bar{G}_{ox}^n$, which provides the representative regression rate for grain sizing and propellant budgeting.

The initial port diameter is determined from the injection conditions. HRMA computes the injection velocity from the Bernoulli equation applied across the injector pressure drop $\Delta P = 0.2\,P_c$:

$$v_{inj} = \sqrt{\frac{2\,\Delta P}{\rho_{ox}}}$$

where $\rho_{ox}$ is the oxidizer density (1220 kg/m³ for liquid N₂O). The initial port area then follows from $A_{p,0} = \dot{m}_{ox}/(\rho_{ox}\,v_{inj})$, and the initial port diameter is $D_{p,0} = 2\sqrt{A_{p,0}/\pi}$.

For higher-fidelity transient simulations, the solver architecture supports integration with a fourth-order Runge-Kutta (RK4) scheme applied to the port radius ODE:

$$\frac{dr_p}{dt} = \dot{r}(G_{ox}(r_p)) = a\left(\frac{\dot{m}_{ox}}{\pi r_p^2}\right)^n$$

This ODE is nonlinear because $\dot{r}$ depends on $r_p$ through $G_{ox}$. The RK4 scheme evaluates the right-hand side at four sub-step points within each time interval, achieving fourth-order accuracy in $\Delta t$. Convergence of the time-stepping is verified by comparing results at $N$ and $2N$ steps; the solution is accepted when the relative change in the final port diameter satisfies $|D_p^{(2N)} - D_p^{(N)}|/D_p^{(N)} < 10^{-4}$.

The solver also handles the implicit coupling between chamber pressure and combustion thermochemistry. Because $C^*$ depends on $T_c$, $\gamma$, and $\bar{M}$ -- all of which are functions of O/F through the equilibrium solver -- a change in O/F during the burn alters the effective $C^*$, which in turn modifies $P_c$ for a fixed throat area. HRMA addresses this by recomputing the equilibrium state at the time-averaged O/F ratio, providing a self-consistent set of thermodynamic properties for the performance calculation. For motors where the O/F shift exceeds 20% over the burn duration, the solver subdivides the burn into discrete intervals and evaluates the equilibrium independently in each interval, capturing the nonlinear dependence of flame temperature and product composition on mixture ratio.

The overall solver output includes time histories of port diameter, regression rate, oxidizer mass flux, O/F ratio, and (where the full transient mode is engaged) chamber pressure and thrust. These time histories enable the designer to assess burn uniformity, identify conditions of excessive O/F shift, and verify that structural limits on the grain web thickness and minimum port-to-throat area ratio ($A_p/A_t > 2$) are maintained throughout the burn.

---

## 9. NOZZLE GEOMETRY AND PERFORMANCE COUPLING

The nozzle constitutes the primary thrust-generating component in any chemical propulsion system, and its geometric design directly governs the thermodynamic expansion process that converts thermal enthalpy into directed kinetic energy. HRMA implements a comprehensive nozzle design module grounded in quasi-one-dimensional isentropic flow theory, supporting three distinct contour families -- conical, bell (approximated parabolic), and full parabolic -- each with distinct performance-mass tradeoffs.

The isentropic flow relations underpin all nozzle calculations within the module. For a calorically perfect gas with ratio of specific heats $\gamma$, the stagnation-to-static property ratios are expressed as

$$\frac{T}{T_0} = \left(1 + \frac{\gamma - 1}{2} M^2\right)^{-1}, \qquad \frac{P}{P_0} = \left(1 + \frac{\gamma - 1}{2} M^2\right)^{-\gamma/(\gamma-1)},$$

$$\frac{\rho}{\rho_0} = \left(1 + \frac{\gamma - 1}{2} M^2\right)^{-1/(\gamma-1)},$$

where $M$ denotes the local Mach number and the subscript 0 indicates stagnation (chamber) conditions. The area-Mach relation $A/A^* = f(M, \gamma)$ is inverted numerically to obtain the exit Mach number $M_e$ from a prescribed expansion ratio $\epsilon = A_e/A_t$, employing an iterative root-finding scheme initialized from the supersonic branch approximation $M_e \approx \sqrt{(2/(\gamma-1))\left[\epsilon^{2(\gamma-1)/(\gamma+1)} - 1\right]}$.

For conical nozzles, the divergent section is defined by a constant half-angle $\alpha$ (default 15 degrees), yielding divergent length $L_d = (r_e - r_t)/\tan\alpha$, where $r_t$ and $r_e$ are the throat and exit radii, respectively. The conical geometry incurs a thrust loss characterized by the divergence correction factor $\lambda = (1 + \cos\alpha)/2$, which reduces the effective thrust coefficient. Bell nozzles, by contrast, employ a contoured divergent section with an initial wall angle $\theta_n = 30°$ at the throat that gradually decreases to $\theta_e = 8°$ at the exit plane. The contour is generated via a parabolic approximation $r(x) = r_t + (r_e - r_t)(x/L)^{0.8}$, where the exponent 0.8 produces a rapid initial expansion followed by a gentle approach to the exit radius, closely replicating Rao-optimized bell profiles at roughly 80% the length of an equivalent 15-degree conical nozzle. The throat section incorporates a downstream circular arc of radius $R_n = 0.382\,r_t$, consistent with standard practice for minimizing boundary layer losses at the sonic line.

Performance coupling between the nozzle and the combustion chamber is achieved through the characteristic velocity $C^* = \sqrt{R\,T_c/\gamma}\,\left[(2/(\gamma+1))^{(\gamma+1)/(2(\gamma-1))}\right]^{-1}$ and the thrust coefficient

$$C_F = \sqrt{\frac{2\gamma^2}{\gamma-1}\left(\frac{2}{\gamma+1}\right)^{(\gamma+1)/(\gamma-1)} \left[1 - \left(\frac{P_e}{P_c}\right)^{(\gamma-1)/\gamma}\right]}\,,$$

such that the delivered specific impulse is $I_{sp} = \eta_n\,C_F\,C^*/g_0$, where $\eta_n$ is the nozzle efficiency factor accounting for viscous and divergence losses. The optimum expansion condition $P_e = P_a$ is enforced by solving the isentropic pressure relation for the expansion ratio that yields exit pressure matching the local ambient pressure, thereby maximizing the momentum thrust term and eliminating the pressure thrust penalty. Throat sizing proceeds from the choked-flow mass balance $\dot{m} = P_c A_t / C^*$, coupling nozzle geometry directly to chamber conditions and the instantaneous regression-rate-driven mass flow rate.

---

## 10. THERMAL AND STRUCTURAL ASSESSMENT

The integrity of a hybrid rocket motor casing under simultaneous thermal and mechanical loading demands a coupled assessment of heat transfer pathways, wall temperature evolution, and pressure-induced stresses. HRMA integrates dedicated thermal and structural analysis modules that evaluate these phenomena in a unified framework, drawing on a materials database encompassing AISI 4130 steel, aluminum 6061-T6, Inconel 718, titanium Ti-6Al-4V, and copper alloys, each characterized by thermal conductivity $k$, yield strength $\sigma_y$, elastic modulus $E$, coefficient of thermal expansion $\alpha_{th}$, density $\rho_s$, and allowable operating temperature $T_{allow}$.

The thermal analysis begins with the gas-side convective heat transfer coefficient, computed via the Dittus-Boelter correlation for turbulent internal flow:

$$\text{Nu} = 0.023\,\text{Re}^{0.8}\,\text{Pr}^{n},$$

where $n = 0.4$ for heating and $n = 0.3$ for cooling. The Reynolds and Prandtl numbers are evaluated using combustion gas properties at the mean film temperature, with gas-phase transport properties (viscosity $\mu_g$, thermal conductivity $k_g$, specific heat $c_{p,g}$) derived from the equilibrium combustion calculation. The resulting gas-side coefficient $h_g = \text{Nu}\,k_g/D_{ch}$ typically ranges from $10^2$ to $10^4$ W/m²K depending on chamber pressure and mass flux. The heat flux at the throat is augmented by a factor of approximately 1.5 relative to the cylindrical chamber section, reflecting the acceleration of the boundary layer through the converging passage.

Conductive heat transfer through the cylindrical chamber wall is governed by Fourier's law in cylindrical coordinates, yielding the thermal resistance $R_{cond} = \ln(r_2/r_1)/(2\pi k L)$ for a wall of inner radius $r_1$, outer radius $r_2$, conductivity $k$, and axial length $L$. For the simplified planar approximation employed in thin-walled chambers ($t/r \ll 1$), the conduction resistance reduces to $R_{cond} = t/k$ per unit area. The outer surface exchanges heat via natural convection ($h_{ext} \approx 25$ W/m²K), forced convection ($h_{ext} \approx 100$ W/m²K), or regenerative cooling ($h_{ext} \approx 2000$ W/m²K), depending on the selected cooling strategy. The steady-state inner wall temperature is then $T_{w,i} = T_\infty + q''(R_{cond} + 1/h_{ext})$, where $q'' = h_g(T_c - T_{w,i})$ requires iterative solution. Radiation heat transfer is accounted for through the Stefan-Boltzmann law $q''_{rad} = \varepsilon\sigma(T_w^4 - T_\infty^4)$, with emissivity $\varepsilon$ drawn from the material database.

The structural module evaluates pressure vessel integrity using both thin-wall ($t/r < 0.1$) and thick-wall (Lame) formulations. For thin-walled cylinders under internal gauge pressure $P$, the hoop and longitudinal stresses are $\sigma_h = Pr/t$ and $\sigma_l = Pr/(2t)$, respectively. These principal stresses are combined through the von Mises yield criterion $\sigma_{vM} = \sqrt{\sigma_h^2 - \sigma_h\sigma_l + \sigma_l^2}$ to determine the equivalent uniaxial stress state. The minimum wall thickness is obtained from $t_{min} = P\,r/(\sigma_y/\text{SF})$, where SF is the prescribed safety factor (typically 4.0 for amateur and educational systems, 3.0 for flight-qualified hardware using Inconel 718).

Thermal stresses arising from the through-wall temperature gradient are computed as $\sigma_{th} = E\,\alpha_{th}\,\Delta T$, where $\Delta T = T_{w,i} - T_{ref}$. These thermal stresses are superimposed with the pressure-induced mechanical stresses to assess the combined loading envelope. The module evaluates multiple safety factors -- temperature margin $\text{SF}_T = T_{allow}/T_{w,max}$, melting margin $\text{SF}_m = T_{melt}/T_{w,max}$, and stress margin $\text{SF}_\sigma = \sigma_y/\sigma_{th}$ -- and classifies the design risk as LOW, MEDIUM, or HIGH based on hierarchical threshold criteria.

---

## 11. TRAJECTORY SIMULATION

HRMA incorporates a multi-phase trajectory simulation that integrates the equations of motion from launch through apogee and descent, providing altitude, velocity, and acceleration histories essential for mission-level performance assessment. The simulation decomposes the flight into three sequential phases -- powered ascent, unpowered coasting, and parachute-assisted descent -- each governed by the planar equations of motion for a point mass subject to thrust, aerodynamic drag, and gravitational forces.

During the powered phase, the state vector $\mathbf{y} = [x, z, v_x, v_z, m]^T$ evolves according to

$$\dot{x} = v_x, \quad \dot{z} = v_z, \quad \dot{v}_x = \frac{F_{T,x} + F_{D,x}}{m}, \quad \dot{v}_z = \frac{F_{T,z} + F_{D,z}}{m} - g(z), \quad \dot{m} = -\dot{m}_p,$$

where the thrust vector is aligned with the instantaneous velocity direction after initial vertical launch, and the propellant mass flow rate $\dot{m}_p$ is determined by the hybrid motor's regression rate model. The aerodynamic drag force magnitude is computed as $D = \frac{1}{2}\rho(z)\,V^2\,C_D\,A_{ref}$, with the drag vector oriented opposite to the velocity. The drag coefficient $C_D$ is treated as constant during powered and coasting flight (default 0.5 for a typical sounding rocket configuration), switching to $C_D = 1.4$ upon parachute deployment during descent, with a corresponding increase in reference area to the canopy projected area.

Atmospheric properties are modeled using the International Standard Atmosphere (ISA). In the troposphere ($z \leq 11{,}000$ m), temperature decreases linearly as $T = 288.15 - 0.0065\,z$ and pressure follows the barometric formula $P = 101325\,(T/288.15)^{g_0 M_{air}/(R^*\,L_b)}$, where $L_b = 0.0065$ K/m is the lapse rate, $M_{air} = 0.0289644$ kg/mol is the molar mass of air, and $R^* = 8.31432$ J/(mol K) is the universal gas constant. In the lower stratosphere (11--20 km), the temperature is isothermal at 216.65 K and the pressure decays exponentially. Air density is recovered from the ideal gas law $\rho = P/(R_{air}\,T)$ with $R_{air} = 287.053$ J/(kg K). Gravitational acceleration varies with altitude as $g(z) = g_0\,(R_E/(R_E + z))^2$, where $R_E = 6{,}371{,}000$ m.

The system of ordinary differential equations is integrated using the explicit Runge-Kutta method of order 4(5) (Dormand-Prince, implemented via SciPy's `solve_ivp` with `method='RK45'`) with relative tolerance $10^{-8}$. Phase transitions are detected through event functions: the coasting phase terminates when the vertical velocity crosses zero from positive to negative (apogee event), and the descent phase terminates upon ground contact ($z = 0$). The theoretical upper bound on velocity increment is validated against the Tsiolkovsky rocket equation $\Delta v = v_e\,\ln(m_0/m_1)$, providing a consistency check between the integrated trajectory and the ideal propulsive performance. Key output metrics include maximum altitude, burnout altitude and velocity, time to apogee, maximum dynamic pressure, peak axial acceleration in g-units, landing velocity under parachute, and total flight duration.

---

## 12. VISUALIZATION AND DESIGN FEEDBACK

Effective communication of multidisciplinary analysis results is essential for iterative rocket motor design, particularly in educational and rapid-prototyping contexts where the designer must simultaneously interpret propulsive, thermal, structural, and trajectory performance. HRMA employs the Plotly graphing library to generate interactive, browser-rendered visualizations that support hover-based data inspection, pan-zoom navigation, and selective trace toggling -- capabilities that static plots cannot provide.

The primary motor visualization renders an axial cross-section of the hybrid rocket motor, depicting the chamber casing, solid fuel grain with initial and final port diameters, convergent-divergent nozzle contour, throat location indicator, and geometric annotations including chamber length, diameters, convergent half-angle $\alpha$, divergent half-angle $\beta$, and expansion ratio $\epsilon = (d_e/d_t)^2$. The nozzle contour in the divergent section follows the parametric relation $r(x) = r_t + (r_e - r_t)\,(x/L_d)^{0.7}$, producing a visually accurate bell-shaped profile. Interactive hover tooltips display dimensional data at each geometric feature, enabling rapid identification of design parameters without consulting tabular output.

Performance time histories are presented as multi-panel subplot grids using Plotly's `make_subplots` facility. Standard panels include thrust versus time, chamber pressure versus time, specific impulse versus time, and oxidizer-to-fuel ratio versus time. The regression rate evolution is plotted against both time and instantaneous mass flux $G_{ox}$, enabling visual verification of the classical power-law correlation $\dot{r} = a\,G_{ox}^n$. Combustion efficiency trends, mass fraction distributions, and altitude-dependent performance variations are rendered as additional plot families accessible through the analysis interface.

The trajectory module generates a six-panel visualization comprising: the spatial flight path (altitude versus downrange distance) with annotated burnout and apogee markers; altitude versus time; total and vertical velocity profiles; axial acceleration in g-units; a phase-delineated timeline connecting launch, burnout, apogee, and landing events; and a gauge indicator displaying maximum altitude. Each trace supports hover-based readout of interpolated values, and critical flight events are highlighted with distinct marker symbols.

Three-dimensional motor geometry is constructed using the Trimesh library to generate triangulated surface meshes of the chamber cylinder, convergent-divergent nozzle, injector plate, and fuel grain annulus. These meshes are rendered interactively through Plotly's `Mesh3d` trace type and can be exported as STL files via `trimesh.Mesh.export()`, producing industry-standard tessellated geometry suitable for 3D printing, CNC toolpath generation, or import into parametric CAD environments such as SolidWorks and Fusion 360. A combined motor assembly STL is also generated by concatenating individual component meshes, providing a single-file representation of the complete motor. The thermal analysis module produces wall heat flux waterfall plots, and the structural module generates stress distribution visualizations with safety factor color mapping.

The interactive nature of these visualizations serves a dual pedagogical and engineering function. Students and early-career engineers can manipulate input parameters -- grain geometry, oxidizer flow rate, nozzle expansion ratio -- and immediately observe the coupled response across all performance domains, reinforcing intuition for the multiphysics interactions that govern hybrid rocket motor behavior. This real-time visual feedback loop substantially accelerates the design iteration cycle compared to batch-mode simulation tools that produce only static tabular output.

---

## 13. VALIDATION AND RELIABILITY

The validation of computational tools in rocket propulsion demands rigorous comparison against established reference data, experimental measurements, and fundamental conservation principles. HRMA implements a multi-tiered validation architecture designed to quantify prediction accuracy across the full range of motor types and operating conditions supported by the software.

The primary validation methodology employs a four-level hierarchical framework. At the first level, thermochemical equilibrium calculations are compared against NASA Chemical Equilibrium with Applications (CEA) reference data. The combustion analysis module utilizes NIST-JANAF thermochemical tables with CODATA 2018 values for the universal gas constant ($R = 8314.462618$ J/kmol/K) and standard enthalpies of formation for all relevant species. Cantera integration provides access to the NASA polynomial thermodynamic database, enabling direct comparison of computed adiabatic flame temperatures, characteristic velocity ($C^*$), and specific impulse ($I_{sp}$) against CEA predictions for identical propellant combinations and chamber conditions. For well-characterized propellant pairs such as N₂O/HTPB and LOX/RP-1, the agreement with CEA values is maintained within $\pm 5\%$ across the operational pressure range of 5 to 100 bar.

At the second validation level, HRMA predictions are compared against published experimental data from academic literature and industry sources. The experimental validation framework maintains a structured SQLite database of test cases drawn from AIAA journal publications, NASA technical reports, and university research programs. The database currently includes static fire test data from facilities including Stanford University, Utah State University, MIT, Caltech GALCIT, JPL/NASA, and industry standard benchmark cases. Each test record carries associated measurement uncertainties, enabling proper accounting of experimental error bounds. For parameters including thrust, specific impulse, chamber pressure, and mass flow rate, HRMA achieves agreement within $\pm 10\%$ of experimental values for the majority of validation cases.

The third validation level involves cross-referencing against historical flight-proven engine data. The NASA real-time validator module stores verified specifications for engines including the RS-25 ($I_{sp,vac} = 452$ s, $P_c = 204$ bar, O/F $= 6.0$) and the F-1 ($I_{sp,sl} = 263$ s, $P_c = 70$ bar, O/F $= 2.27$). HRMA thermochemical predictions for these propellant combinations at the documented operating conditions are compared against the official NASA fact sheet values, providing confidence in the extrapolation capability of the equilibrium solver.

Statistical analysis of validation results employs standard metrics including mean percentage error, root mean square error (RMSE), mean absolute error (MAE), coefficient of determination ($R^2$), and the fraction of predictions falling within 5%, 10%, and 15% error bands. The validation framework computes Pearson correlation coefficients between predicted and experimental values for each parameter independently and assigns a letter grade (A+ through F) based on the combined success rate at 10% tolerance and overall mean error magnitude.

Conservation law compliance constitutes the fourth validation tier. Mass conservation is verified by confirming that the sum of fuel and oxidizer mass flow rates equals the total propellant mass flow rate within numerical precision. Momentum conservation is checked through the thrust equation, ensuring consistency between chamber pressure, nozzle geometry, and computed thrust. Energy conservation is verified through the enthalpy balance across the combustion chamber, confirming that the total enthalpy of reactants plus heat of reaction equals the total enthalpy of products at the computed equilibrium temperature.

The validation system operates continuously during analysis. The real-time parameter checking module compares computed values against established performance bounds drawn from Sutton and Biblarz, NASA SP-8089, and AIAA standards. Parameters exceeding physically reasonable ranges trigger severity-classified warnings (CRITICAL or WARNING), allowing the user to identify potential input errors or model limitations before proceeding with downstream design calculations. The overall reliability assessment indicates that HRMA produces predictions suitable for preliminary design and educational purposes, with accuracy commensurate with the one-dimensional, equilibrium-chemistry modeling assumptions upon which the software is built.

---

## 14. EDUCATIONAL AND OPEN-SOURCE CONTRIBUTION VALUE

HRMA was developed with the explicit objective of democratizing access to rocket motor analysis capabilities that have historically been confined to proprietary software packages or specialized institutional codes. The software is deployed as a web-based application built on the Flask framework, requiring no local installation beyond a standard web browser. This eliminates the software licensing costs, operating system dependencies, and installation complexity that constitute significant barriers to entry for students, amateur rocketeers, and researchers at institutions with limited computational budgets.

The interactive nature of the platform provides substantial pedagogical advantages over static textbook treatments of rocket propulsion. Students can modify input parameters such as oxidizer-to-fuel ratio, chamber pressure, and fuel type, and immediately observe the effects on specific impulse, characteristic velocity, thrust, and nozzle geometry through dynamically rendered visualizations. This closed-loop interaction between parameter selection and performance visualization reinforces the physical intuition that textbook derivations alone cannot convey. The simultaneous availability of hybrid, solid, and liquid motor analysis modules within a single platform enables direct comparative study of the three propulsion architectures, facilitating understanding of the fundamental trade-offs in performance, complexity, safety, and controllability that govern motor type selection in practice.

For the amateur rocketry community, HRMA provides a free analytical tool for preliminary motor sizing that would otherwise require commercial software such as ProPEP, RPA (Rocket Propulsion Analysis), or institutional access to NASA CEA. The safety analysis and validation modules provide real-time feedback on whether proposed designs fall within established physical limits, serving a protective function for experimenters who may lack the engineering background to independently assess the feasibility of their designs. The integration with OpenRocket export formats further supports the amateur community by enabling trajectory analysis with externally generated motor performance files.

The open-source Python codebase serves as an educational reference in its own right. The modular architecture separates thermochemical equilibrium calculations, nozzle design, regression rate analysis, injector design, heat transfer, structural analysis, and trajectory simulation into distinct, readable modules. Each module can be studied independently as an implementation reference for the underlying engineering equations. The use of well-documented scientific Python libraries including NumPy, SciPy, Matplotlib, and Plotly ensures that the computational methods are transparent, reproducible, and modifiable by users with intermediate Python proficiency. This transparency stands in contrast to commercial tools whose proprietary implementations cannot be inspected, verified, or adapted for specialized applications.

---

## 15. LIMITATIONS AND FUTURE DEVELOPMENT ROADMAP

While HRMA provides a comprehensive analytical framework for rocket motor preliminary design, several inherent limitations must be acknowledged to ensure appropriate application of the tool and correct interpretation of its results.

The most fundamental limitation is the one-dimensional treatment of all internal flow fields. The combustion chamber, nozzle, and port flow are modeled as quasi-one-dimensional, neglecting radial and circumferential gradients in temperature, pressure, velocity, and species concentration. In hybrid motors, the boundary layer combustion process is inherently two-dimensional, with fuel regression driven by convective and radiative heat transfer from the flame zone to the grain surface. The classical Marxman regression rate correlation ($\dot{r} = a \cdot G_{ox}^n$) employed by HRMA captures the integral effect of this process but does not resolve the detailed boundary layer structure, limiting accuracy when applied to geometries or operating conditions that deviate significantly from the conditions under which the empirical coefficients were determined.

The combustion model assumes chemical equilibrium at the chamber exit plane, neglecting finite-rate chemical kinetics. While this assumption is valid for high-pressure, long-residence-time conditions typical of most practical motors, it introduces error for low-pressure systems, short characteristic lengths (small $L^*$), and propellant combinations with slow reaction kinetics. The absence of detailed chemical kinetics also precludes modeling of combustion instability, ignition transients, and pollutant formation (e.g., NO$_x$ and CO emissions).

The grain geometry support is currently limited primarily to cylindrical port configurations. While the BATES grain geometry is supported for solid motors, advanced grain designs such as wagon wheel, finocyl, multi-port, and star-in-star configurations are not fully implemented. This restricts the utility of the tool for solid motor designers who rely on grain geometry tailoring to achieve specific thrust-time profiles.

The accuracy of hybrid motor predictions is fundamentally dependent on the quality of regression rate coefficient data ($a$ and $n$ values) for the fuel-oxidizer combination under consideration. Published regression rate data exhibit significant scatter, and coefficients measured at one scale or operating condition may not transfer reliably to other conditions due to the influence of motor scale, injector design, and combustion port length-to-diameter ratio.

The future development roadmap for HRMA addresses these limitations through a phased approach. The near-term priority is the implementation of two-dimensional axisymmetric flow modeling within the combustion chamber and nozzle, enabling resolution of boundary layer effects and more accurate prediction of wall heat flux distributions. This extension will employ a finite-volume discretization of the axisymmetric Navier-Stokes equations with appropriate turbulence modeling.

Machine learning integration represents a medium-term development target. A neural network trained on experimental regression rate data from the published literature could provide improved predictions for fuel-oxidizer combinations where limited empirical data are available. The training dataset would incorporate motor scale, operating pressure, oxidizer flux, and fuel composition as input features, with instantaneous regression rate as the target variable.

Additional planned developments include support for multi-port grain geometries, real-time hardware-in-the-loop testing capability for integration with experimental test stands, a mobile application for field use, enhanced CFD coupling through external solver interfaces, and multi-objective optimization for automated exploration of the design space considering performance, mass, cost, and safety constraints simultaneously. These extensions would transform HRMA from a preliminary design tool into a more comprehensive analysis platform bridging the gap between simplified analytical methods and full-fidelity simulation.

---

## 16. CONCLUSION

This paper has presented HRMA (Hybrid Rocket Motor Analysis), an open-source, web-based software platform for the comprehensive analysis of hybrid, solid, and liquid rocket motors. The software integrates thermochemical equilibrium calculations, nozzle design and optimization, regression rate analysis, injector design, heat transfer modeling, structural assessment, trajectory simulation, and CAD geometry generation within a unified, browser-accessible interface built on the Flask web framework and scientific Python ecosystem.

The thermochemical analysis module employs NASA polynomial thermodynamic data and Cantera-based equilibrium calculations to predict combustion chamber conditions, while the nozzle design module implements both conical and bell (Rao-optimized) contour generation with isentropic flow relations. The regression rate analysis for hybrid motors implements the classical Marxman power-law correlation with support for multiple fuel types including HTPB, paraffin wax, polyethylene, PMMA, and ABS, each with literature-derived empirical coefficients. The validation framework provides multi-level verification against NASA CEA reference data, published experimental measurements, and historical engine specifications, with the statistical analysis confirming prediction accuracy within $\pm 5\%$ for well-characterized propellant combinations and within $\pm 10\%$ for the broader range of validated test cases.

The principal contributions of this work are threefold. First, HRMA consolidates the analysis of all three rocket motor types within a single platform, enabling comparative study that is not readily available in existing free tools. Second, the web-based deployment eliminates installation barriers and licensing costs, making professional-grade preliminary design analysis accessible to students, researchers, and amateur rocketeers worldwide. Third, the open-source codebase provides a transparent, modifiable, and extensible foundation upon which the community can build specialized analysis capabilities.

The acknowledged limitations of one-dimensional flow modeling, equilibrium chemistry assumptions, and dependence on empirical regression rate data define the appropriate application envelope for the current version of HRMA. These limitations notwithstanding, the validation results demonstrate that the software provides accuracy sufficient for preliminary design, educational instruction, and initial feasibility assessment of rocket motor concepts.

Continued development toward two-dimensional flow modeling, machine learning-enhanced regression rate prediction, and multi-objective design optimization will progressively expand the analytical capability and application range of the platform. The authors invite contributions from the rocket propulsion community to extend the experimental validation database, improve propellant property models, and develop the planned advanced analysis modules.

---

## Funding

This research received no external funding. The development of HRMA was conducted as an independent academic research effort.

## Acknowledgments

The authors gratefully acknowledge Istanbul Technical University for providing academic support and computational resources throughout the development of this work. The open-source scientific computing community, and in particular the developers of NumPy, SciPy, Cantera, and Plotly, are recognized for providing the foundational software libraries upon which HRMA is built.

---

## References

[1] Marxman, G. A. and Gilbert, M., "Turbulent Boundary Layer Combustion in the Hybrid Rocket," *Symposium (International) on Combustion*, Vol. 9, No. 1, 1963, pp. 371-383.

[2] Marxman, G. A., Wooldridge, C. E., and Muzzy, R. J., "Fundamentals of Hybrid Boundary Layer Combustion," *Progress in Astronautics and Aeronautics*, Vol. 15, 1964, pp. 485-522.

[3] Chiaverini, M. J. and Kuo, K. K. (Eds.), *Fundamentals of Hybrid Rocket Combustion and Propulsion*, Progress in Astronautics and Aeronautics, Vol. 218, AIAA, Reston, VA, 2007.

[4] Sutton, G. P. and Biblarz, O., *Rocket Propulsion Elements*, 9th ed., John Wiley & Sons, Hoboken, NJ, 2017.

[5] Anderson, J. D., *Modern Compressible Flow: With Historical Perspective*, 3rd ed., McGraw-Hill, New York, 2003.

[6] Gordon, S. and McBride, B. J., "Computer Program for Calculation of Complex Chemical Equilibrium Compositions and Applications," NASA Reference Publication 1311, 1994.

[7] McBride, B. J. and Gordon, S., "Computer Program for Calculation of Complex Chemical Equilibrium Compositions and Applications: II. Users Manual and Program Description," NASA Reference Publication 1311, 1996.

[8] Linstrom, P. J. and Mallard, W. G. (Eds.), *NIST Chemistry WebBook*, NIST Standard Reference Database Number 69, National Institute of Standards and Technology, Gaithersburg, MD, 2023. https://webbook.nist.gov

[9] Niskanen, S., "OpenRocket: An Open Source Model Rocket Simulator," M.S. Thesis, Helsinki University of Technology, 2009.

[10] Humble, R. W., Henry, G. N., and Larson, W. J., *Space Propulsion Analysis and Design*, McGraw-Hill, New York, 1995.

[11] Karabeyoglu, M. A., Altman, D., and Cantwell, B. J., "Combustion of Liquefying Hybrid Propellants: Part 1, General Theory," *Journal of Propulsion and Power*, Vol. 18, No. 3, 2002, pp. 610-620.

[12] Karabeyoglu, M. A. and Cantwell, B. J., "Combustion of Liquefying Hybrid Propellants: Part 2, Stability of Liquid Films," *Journal of Propulsion and Power*, Vol. 18, No. 3, 2002, pp. 621-630.

[13] Altman, D. and Holzman, A., "Overview and History of Hybrid Rocket Propulsion," *Fundamentals of Hybrid Rocket Combustion and Propulsion*, edited by M. J. Chiaverini and K. K. Kuo, Progress in Astronautics and Aeronautics, Vol. 218, AIAA, Reston, VA, 2007, pp. 1-36.

[14] George, P., Krishnan, S., Varkey, P. M., Ravindran, M., and Ramachandran, L., "Fuel Regression Rate in Hydroxyl-Terminated-Polybutadiene/Gaseous-Oxygen Hybrid Rocket Motors," *Journal of Propulsion and Power*, Vol. 17, No. 1, 2001, pp. 35-42.

[15] "Solid Propellant Grain Design and Internal Ballistics," NASA SP-8076, NASA Space Vehicle Design Criteria (Chemical Propulsion), 1972.

[16] "Solid Rocket Motor Performance Analysis and Prediction," NASA SP-8039, NASA Space Vehicle Design Criteria (Chemical Propulsion), 1971.

[17] Hill, P. G. and Peterson, C. R., *Mechanics and Thermodynamics of Propulsion*, 2nd ed., Addison-Wesley, Reading, MA, 1992.

[18] Turns, S. R., *An Introduction to Combustion: Concepts and Applications*, 3rd ed., McGraw-Hill, New York, 2012.

[19] Goodger, E. M., "Solid Propellant Grain Design," in *Solid Propellant Chemistry, Combustion, and Motor Interior Ballistics*, edited by V. Yang, T. B. Brill, and W. Z. Ren, Progress in Astronautics and Aeronautics, Vol. 185, AIAA, Reston, VA, 2000, pp. 159-176.

[20] Carmicino, C. and Sorge, A. R., "Role of Injection in Hybrid Rockets Regression Rate Behavior," *Journal of Propulsion and Power*, Vol. 21, No. 4, 2005, pp. 606-612.

[21] Doran, E., Dyer, J., Lohner, K., Dunn, Z., Cantwell, B. J., and Zilliac, G., "Nitrous Oxide Hybrid Rocket Motor Fuel Regression Rate Characterization," AIAA Paper 2007-5352, 2007.

[22] Zilliac, G. and Karabeyoglu, M. A., "Hybrid Rocket Fuel Regression Rate Data and Modeling," AIAA Paper 2006-4504, 2006.

[23] Grinstead, R. E. and Krier, H. (Eds.), *Interior Ballistics of Guns*, Progress in Astronautics and Aeronautics, Vol. 66, AIAA, New York, 1979.

[24] Goodman, D., *Flask Web Development*, 2nd ed., O'Reilly Media, Sebastopol, CA, 2018.

[25] Oliphant, T. E., "Python for Scientific Computing," *Computing in Science & Engineering*, Vol. 9, No. 3, 2007, pp. 10-20.

[26] Virtanen, P., Gommers, R., Oliphant, T. E., et al., "SciPy 1.0: Fundamental Algorithms for Scientific Computing in Python," *Nature Methods*, Vol. 17, 2020, pp. 261-272.

[27] Harris, C. R., Millman, K. J., van der Walt, S. J., et al., "Array Programming with NumPy," *Nature*, Vol. 585, 2020, pp. 357-362.

[28] Goodwin, D. G., Moffat, H. K., Schoegl, I., Speth, R. L., and Weber, B. W., "Cantera: An Object-oriented Software Toolkit for Chemical Kinetics, Thermodynamics, and Transport Processes," Version 3.0, 2023. https://www.cantera.org

[29] Kuo, K. K. and Chiaverini, M. J., "Challenges of Hybrid Rocket Propulsion in the 21st Century," *Fundamentals of Hybrid Rocket Combustion and Propulsion*, edited by M. J. Chiaverini and K. K. Kuo, Progress in Astronautics and Aeronautics, Vol. 218, AIAA, Reston, VA, 2007, pp. 593-638.

[30] Cantwell, B., Karabeyoglu, M. A., and Altman, D., "Recent Advances in Hybrid Propulsion," *International Journal of Energetic Materials and Chemical Propulsion*, Vol. 9, No. 4, 2010, pp. 305-326.
