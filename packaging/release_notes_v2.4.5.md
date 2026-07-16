## HRMA v2.4.5

**Physics audit — 32 verified findings fixed**
A full physics/computation audit (7 domain auditors + adversarial verification)
was run over the entire engine and analysis codebase. All fixes are
literature-referenced (Sutton & Biblarz, NASA SP-8007, ASME BPVC, Kingery-
Bulmash, Lenoir-Robillard, Shigley) and covered by 1038 passing tests.

Highlights:
- Kinetic efficiency no longer reports a fake 100% for every motor
- Blast overpressure safety distances were 30-60x too SMALL — now Kingery-Bulmash correct
- Altitude/vacuum Isp no longer over-predicted (fixed-nozzle pressure-thrust term, Sutton Eq. 3-29)
- Nozzle divergence loss no longer double-counted (solid motors)
- Optimum O/F and oxidizer density now follow the selected oxidizer (LOX/H2O2 were using N2O)
- Liquid engine exit velocity / residence time / acoustic frequency now use combustion-gas
  properties instead of air constants
- Thrust-to-weight now uses gross (loaded) mass
- 2:1 elliptical head thickness per ASME UG-32(d) (was hemisphere formula, 2x thin)
- Solid motor throat heat flux now computed with the Bartz correlation (was a placeholder ~1000x low)
- c* efficiency now normalized to each propellant's own theoretical c*
- Axial buckling now checked against real compressive load (thrust), not internal-pressure tension
- Erosive burning geometric dependency corrected to Lenoir-Robillard form (D^-0.2) with
  recalibrated coefficients (cross-checked against literature)
- Bolt sizing per thread stress area (ISO 898-1), fragment ranges drag-limited,
  Gurney equation mass terms corrected, 6-DOF atmosphere guarded above 84.8 km

**Improvements**
- Update flow: always-visible "download in your browser" fallback with stall detection
- Windows installer now performs a clean update (removes old files first)
- Splash and window title now say "UZAYTEK Rocket Motor Analysis" (the suite covers
  hybrid, solid and liquid motors)

**Downloads**
- Windows 10/11: `HRMA-Setup-2.4.5.exe`
- macOS 11+ (Apple Silicon): `HRMA-Setup-2.4.5-macOS.dmg`
