## HRMA v2.4.0

**New — analysis deck**
- Structural safety deck: pressure vessel, buckling, fatigue, bolted joints (Shigley), Goodman fatigue
- Thermal protection: ablation (Q*), heat-sink finite-difference, radiative equilibrium
- Pressure vessel sizing (ASME / SP-8007 / Faupel) with burst and auto-size
- Quasi-1D nozzle flow with Summerfield separation, staged combustion kinetics (Cantera optional)
- Feed system: slosh (SP-106), pressurant sizing (He/N2), water hammer (Joukowsky)
- Regenerative cooling (1D station march, Dittus-Boelter, coking limit) for liquid engines
- User-CSV validation against HRMA predictions
- 13 on-deck analysis panels reachable from the hybrid / solid / liquid pages

**New — desktop identity**
- The macOS menu bar and About panel now show "HRMA vX.Y.Z" instead of "Python 3.12"
- App menu: Check for Updates…, Open Output Folder; Help menu with GitHub links
- The installed version is shown on the home page, footer, window title and splash

**Fixed**
- OpenRocket .eng download (response key mismatch — the button did nothing before)
- Regression-rate summary crash (schema mismatch on `toFixed`)
- PDF report buttons on the solid and liquid pages stayed stuck on "Generating PDF…"
- Windows source install: `python app.py` failing with "No module named 'hrma'"
- Windows source install: clearer Python 3.10–3.13 guard and wheel-only pip install
  (Python 3.14 has no wheels for numpy<2 / CoolProp / RocketCEA and fell back to a source build)
- Emoji removed from the interface for a cleaner engineering look

**Downloads**
- Windows 10/11: `HRMA-Setup-2.4.0.exe`
- macOS 11+ (Apple Silicon): `HRMA-Setup-2.4.0-macOS.dmg`
