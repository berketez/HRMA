# HRMA v2.5.1

Maintenance release on top of the v2.5.0 Confidence Release: a visible 3D
deck on the liquid page, database-driven KN-sugar burn-rate presets, four
text-overlap UI fixes and 63 new fully-cited hybrid validation records.

## Liquid page: 3D engine simulation now visible

- The Three.js parametric digital twin used to mount inside a buried
  trajectory sub-tab where nobody could find it. It now renders in a
  dedicated "3D Motor Simulasyonu" panel in the main results flow, right
  after the motor cross-section, immediately after each calculation.
- The trajectory tab's CAD view now consistently uses the Plotly 3D CAD
  (the Three.js scene is a singleton and cannot live in two places).
- Fixed the altitude-performance plot collapsing to 148 px (axis labels
  were rendered on top of each other).

## Solid page: KNDX/KNSB burn-rate presets from the central database

- New "Burn Rate Preset" selector fills the Saint-Robert a and n fields
  from the central validated burn-rate database (Nakka 1999/2001 piecewise
  regime fits) at the current chamber pressure, via the new
  `/api/burn-rate/resolve` endpoint. Changing the pressure re-resolves the
  regime; editing a or n by hand switches back to Custom.
- The burn-rate exponent validation range was widened from [0.1, 1.0] to
  [-0.5, 1.0]: KN-sugar plateau/mesa regimes have physically NEGATIVE
  pressure exponents and were previously rejected. The UQ sampler clamp
  was aligned. The coefficient unit label was corrected to (m/s/bar^n).

## UI text-overlap fixes (all motor pages swept)

- Hybrid performance dashboard: the injector gauge printed its own title
  on top of the subplot annotation — the unit moved into the number.
- Motor cross-section: the divergent-angle label collided with the
  vertical diameter dimension labels on short nozzles; it now sits below
  the nozzle with a pixel-space offset.
- Design Report tables rendered label and value glued together
  ("Reynolds Number88548") — table cells now have proper padding and a
  right-aligned value column.

## Validation database: 63 new hybrid records (136 -> 199 total)

- New fully-cited sources: Cardillo 2023 (14 tests, paraffin/GOX, with
  published uncertainties), Scaramuzzino/Carmicino 2013 (25 tests,
  HTPB+additives with gaseous N2O), Heydari 2017 (10 tests, HTPB/N2O,
  axial + swirl), Battista 2019 (4 tests, 1000 N paraffin/GOX),
  HPDP 250K 2003 (4 large-scale firings), AMROC DM-01 1993 (4 firings),
  Sims 1998 (24-inch motor c* with a stated 95 % confidence interval)
  and Knowles 2004 (10-inch HTPB/LOX).
- Honesty note: the headline correlation statistics are UNCHANGED. Most
  new records lack a published initial port or throat diameter and are
  reported as insufficient-inputs rather than guessed; the Heydari swirl
  series is quarantined in the anomaly layer because HRMA v1 models axial
  injection (the source's own regression fits differ by regime:
  axial r = 0.40 G^0.37 vs swirl r = 0.14 G^1.40). A new guard test locks
  this quarantine. Full breakdown:
  `docs/arge-guven-2026-07/arge_hibrit_veri_genisletme.md`.

1311 tests green.
