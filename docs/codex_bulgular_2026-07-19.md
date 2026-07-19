# Codex (gpt-5.6-sol, xhigh) bağımsız hata taraması

Tarih: 2026-07-19, v2.5.2 yayınından hemen önce. Kendi denetim ve temizlik
dalgalarımız bittikten SONRA koşuldu; amaç bizim kaçırdığımızı bulmak.

Doğrulama durumu (ana Claude tarafından kodla teyit edildi):
- Birim sözleşmesi kırılması: **DOĞRULANDI ve tarif edildiğinden kötü.**
  Katı motor `throat_diameter` MİLİMETRE (44.798), sıvı ve hibrit METRE
  (0.0278 / 0.0216). Sıvı `chamber_length` MİLİMETRE (97.96), hibrit METRE
  (0.629). `.eng` dışa aktarıcı hepsini metre sanıp 1000 ile çarpıyor.
  Normalize sözleşme `motor_geometry` zaten var ve üç tipte de üretiliyor;
  tüketiciler onu kullanmalı.
- c* verimi iptali: **DOĞRULANDI.** verim 1.0 -> c*=1598.20, verim 0.8 ->
  1278.56, yani `self.c_star` zaten verimle çarpılmış; ona bölmek kaybı
  sıfırlıyor.

Aşağısı Codex'in ham çıktısıdır.

---

hrma/engines/liquid_rocket_engine.py:1480  
WHAT IS WRONG: The cooling integration treats the first 30% of `L_nozzle` as convergent and only 70% as divergent.  
WHY IT IS WRONG: `L_nozzle` was calculated as the throat-to-exit divergent length. The convergent length must be added separately, and conical surface area should use slant length.  
HOW IT SHOWS UP: Nozzle area, heat load, coolant temperature rise, and cooling pressure drop are wrong.  
CONFIDENCE: high

hrma/engines/liquid_rocket_engine.py:2154  
WHAT IS WRONG: Exit Mach is calculated from `Pc/Pambient` even when the user selected a fixed expansion ratio.  
WHY IT IS WRONG: For fixed geometry, exit Mach is determined by `Ae/At` and gamma and remains constant with altitude; ambient pressure only changes pressure thrust and flow regime.  
HOW IT SHOWS UP: A fixed nozzle reports Mach increasing from about 3 at sea level to over 14 at altitude, and exit velocity is consequently wrong.  
CONFIDENCE: high

hrma/engines/hybrid_rocket_engine.py:827  
WHAT IS WRONG: When the entered chamber is smaller than the initial port, the code warns and disables the port limit by setting it to infinity.  
WHY IT IS WRONG: Such geometry is impossible and must be rejected. Later, loaded fuel mass uses `Dch²-Dport²`, which becomes negative.  
HOW IT SHOWS UP: Results can contain a port larger than the chamber and negative loaded fuel mass.  
CONFIDENCE: high

hrma/engines/solid_rocket_engine.py:3621  
WHAT IS WRONG: Burn time and impulse omit the final integration step.  
WHY IT IS WRONG: Samples are stored before advancing `t`; after the last web increment, `time[-1]` is one `dt` before actual burnout, and `trapz` excludes that interval. A terminal burnout sample should be appended or impulse accumulated per step.  
HOW IT SHOWS UP: Burn time and total impulse are systematically low, especially for short burns or coarse time steps.  
CONFIDENCE: high

hrma/engines/solid_rocket_engine.py:3609  
WHAT IS WRONG: `convergence_achieved` is hard-coded true regardless of whether the 100-iteration pressure solve converged.  
WHY IT IS WRONG: The loop has no convergence flag or `for/else`; moreover, `n=1.0` is accepted although the stated fixed-point contraction assumes `n<1`.  
HOW IT SHOWS UP: A last-iterate pressure curve can be returned as successfully converged with no warning.  
CONFIDENCE: high

hrma/engines/solid_rocket_engine.py:1735  
WHAT IS WRONG: Delivered c-star is divided by `self.c_star` after `self.c_star` has already been multiplied by combustion efficiency.  
WHY IT IS WRONG: This cancels the entered combustion loss. The denominator must be the preserved theoretical c-star.  
HOW IT SHOWS UP: Entering 80% combustion efficiency reduces thrust/Isp but the loss breakdown still reports approximately zero combustion loss.  
CONFIDENCE: high

hrma/engines/liquid_rocket_engine.py:2450  
WHAT IS WRONG: Feed-system tank volume prefers web-database density over the explicit user density, while detailed tank design uses `self.rho_ox/self.rho_fuel`. The two paths also use different reserve/ullage models.  
WHY IT IS WRONG: Explicit overrides must have highest priority, and one tank-sizing model should be the source of truth.  
HOW IT SHOWS UP: Changing density can update the detailed tank card but not the feed-system tank volume; the same run displays contradictory tank sizes.  
CONFIDENCE: high

hrma/engines/solid_rocket_engine.py:2825  
WHAT IS WRONG: Selecting the UI’s `composite` case material falls through `get_material()` and silently retains steel density.  
WHY IT IS WRONG: `composite` has no materials-database alias, although the cost table defines it as 1600 kg/m³; the mass calculation therefore uses roughly 7850 kg/m³.  
HOW IT SHOWS UP: Composite motors receive steel-like dry mass and an incorrect thrust-to-weight ratio.  
CONFIDENCE: high

hrma/engines/solid_rocket_engine.py:3871  
WHAT IS WRONG: The design summary recomputes wall thickness using hard-coded 250 MPa steel and safety factor 3 instead of `_case_design()`.  
WHY IT IS WRONG: Structural analysis and dry mass use the selected material, yield strength, safety factor, and entered thickness. The summary must use that same result.  
HOW IT SHOWS UP: An entered 8 mm case can appear as 4.2 mm in the design summary while structural analysis reports 8 mm.  
CONFIDENCE: high

hrma/engines/solid_rocket_engine.py:3741  
WHAT IS WRONG: Nozzle geometry is always generated with 30° convergent and 15° divergent half-angles, ignoring the stored form inputs.  
WHY IT IS WRONG: Convergent and divergent lengths scale as `ΔD/(2 tan(angle))`; the entered angles must drive these dimensions.  
HOW IT SHOWS UP: Changing nozzle-angle fields does not change nozzle length or exported geometry, and the result reports different angles from the form.  
CONFIDENCE: high

hrma/app.py:4029  
WHAT IS WRONG: The nozzle-Mach endpoint forwards only throat area, length, and expansion ratio, discarding supplied gamma, chamber pressure/temperature, molecular weight, chamber diameter, and ambient pressure.  
WHY IT IS WRONG: Gamma controls the area–Mach solution, while `Pc/Pa` controls shock and separation branches. The solver consequently uses its 20 bar, gamma 1.2, one-atmosphere defaults.  
HOW IT SHOWS UP: Changing chamber pressure or gas properties does not change the displayed regime or Mach solution.  
CONFIDENCE: high

hrma/app.py:4009  
WHAT IS WRONG: The real equilibrium performance surface never receives the current fuel or oxidizer identity.  
WHY IT IS WRONG: The visualization accepts these fields, but this endpoint drops them and therefore always solves its HTPB/N₂O reference pair.  
HOW IT SHOWS UP: A LOX/RP-1 or solid-motor run displays an equilibrium surface for HTPB/N₂O.  
CONFIDENCE: high

hrma/static/js/panels/performance_panel.js:179  
WHAT IS WRONG: Liquid results expose `mixture_ratio`, `optimal_mixture_ratio`, and `isp_sea_level`, but the panel reads `of_ratio` and `isp`.  
WHY IT IS WRONG: The producer and consumer key names do not match.  
HOW IT SHOWS UP: Liquid design markers silently remain at the panel defaults of O/F 3.5 and Isp 300 s.  
CONFIDENCE: high

hrma/static/js/panels/performance_panel.js:182  
WHAT IS WRONG: The panel treats mixed-unit top-level results as universal SI: liquid `chamber_length` is millimetres but is inserted into a metre field, while solid `throat_diameter` is millimetres but is squared as metres at line 194.  
WHY IT IS WRONG: Both values require division by 1000, or the normalized `motor_geometry` object should be used.  
HOW IT SHOWS UP: Liquid heat-flux plots can get a chamber 1000× too long; solid throat area becomes 1,000,000× too large.  
CONFIDENCE: high

hrma/static/js/panels/performance_panel.js:163  
WHAT IS WRONG: The heat-flux payload has no fields or result mappings for chamber temperature, gamma, molecular weight, or mass flow.  
WHY IT IS WRONG: These values are available from motor results and are required by the Bartz/nozzle solver; omission forces the 3000 K, gamma 1.2, MW 24, and 1 kg/s defaults.  
HOW IT SHOWS UP: Different propellants can produce nearly identical “real solver” heat-flux plots when geometry and pressure match.  
CONFIDENCE: high

hrma/export/openrocket_integration.py:99  
WHAT IS WRONG: The RASP `.eng` header’s motor diameter is populated with nozzle throat diameter.  
WHY IT IS WRONG: That field is the motor casing/body diameter in millimetres, not the throat diameter.  
HOW IT SHOWS UP: OpenRocket imports a motor whose physical diameter is far too small, affecting fit and vehicle geometry.  
CONFIDENCE: high

hrma/templates/solid.html:4127  
WHAT IS WRONG: The solid `.eng` payload drops the real `thrust_curve`, chamber length, and available dry mass.  
WHY IT IS WRONG: The exporter then falls back to constant thrust, a 500 mm length, and loaded mass equal to propellant mass only.  
HOW IT SHOWS UP: OpenRocket loses ignition/peak/tail behavior and substantially underestimates motor mass while importing the wrong length.  
CONFIDENCE: high

hrma/app.py:2929  
WHAT IS WRONG: The STL fallback returns six partial end-cap triangles with no lateral wall or nozzle, yet sends it as a successful STL download.  
WHY IT IS WRONG: This is an open, non-watertight surface rather than a solid mesh; throat and exit dimensions calculated above are not used at all.  
HOW IT SHOWS UP: A CAD failure silently produces a downloadable but non-manifold, unsliceable motor file.  
CONFIDENCE: high