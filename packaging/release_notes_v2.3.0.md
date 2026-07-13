## HRMA v2.3.0

**New**
- Native desktop window (macOS WebKit / Windows WebView2) — no browser required
- Instant splash screen: the window opens in about a second while computation engines load in the background
- Automatic updates: HRMA checks GitHub Releases at startup and installs new versions with one click
- Fully offline: Plotly, Three.js and MathJax are now bundled — no internet needed after installation
- English setup wizard and user-facing text

**Fixed**
- Startup time reduced dramatically (dead heavy imports removed, bytecode precompiled)
- Regression analysis chart crash (Plotly 6 compatibility)
- Comprehensive safety analysis now returns a full risk report
- STEP assembly part names (chamber / nozzle / fuel_grain / injector)
- OpenRocket .eng file RASP compliance (plugged-motor delay code)

**Downloads**
- Windows 10/11: `HRMA-Setup-2.3.0.exe`
- macOS 11+ (Apple Silicon): `HRMA-Setup-2.3.0-macOS.dmg`
