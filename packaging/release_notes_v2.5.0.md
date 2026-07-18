# HRMA v2.5.0 — Confidence Release

The theme of this release is trust: every headline number HRMA produces now
carries an uncertainty band, and the model is correlated against a
hand-verified database of real static-fire and engine data — with the
misses reported as honestly as the hits.

## Uncertainty Quantification (new)

- Monte Carlo UQ core with Latin Hypercube sampling: `/api/uncertainty-analysis`
  and an UNCERTAINTY panel in the Analysis Dock (hybrid, solid, liquid).
- P50 with [P5, P95] confidence bands for c*, Isp, chamber pressure,
  regression rate and totals; Spearman rank sensitivity tornado.
- Three levels: Fast (200 samples), Engineering (1000), High-Fidelity (3000,
  queued in background). Sample #0 is guaranteed to be the nominal case.

## Real-experiment validation database + correlation (new)

- 136 hand-verified records from primary sources (Rezaei, Karabeyoglu,
  Whitmore, Hansen, Wei, Palacz hybrid campaigns; Nakka solid strand data;
  RL10/F-1/J-2/RS-25/Vulcain/Merlin liquid ratings), each with citation,
  confidence level and anomaly flags.
- Automatic correlation runner + CORRELATION panel (db-hash cached).
  Signed error convention, MAD outlier flagging (never dropped), anomaly
  quarantine, per-record engine-warning capture.
- Paper-quality correlation report with parity figures:
  `docs/correlation_report/` (md + PDF).
- Correlation guard tests freeze the baseline per cell against the DB
  content hash — silent degradation fails CI; suspicious sudden improvement
  warns (anti-circularity).

## Physics corrections found by the correlation run

- **Gaseous oxygen (GOX) oxidizer was not handled** in the combustion
  equilibrium — GOX cases ran an oxygen-free "combustion". Fixed; GOX c*
  now matches NASA CEA within ~1 %. Unknown propellant keys now raise
  instead of silently producing garbage.
- **HTPB heat of formation corrected** to the CEA R-45 card value (the old
  estimate under-predicted flame temperature by ~300 K in the fuel-rich
  region). Hybrid c* vs 18 static fires: median APE 2.3 %, bias ~0.
- **Solid burn rates**: published Nakka KNDX/KNSB piecewise regime fits now
  live in a central, unit-explicit database; the strand comparison dropped
  from +84 % bias to under 1 % (labelled in-sample, see VALIDATION_STATUS).
- Validation layer evaluates G_ox-based regression coefficients on their own
  flux basis; oxidizer-aware plausibility bands for c* warnings.
- Honesty note: hybrid Isp correlation moved from +1.8 % to +9.6 % — the old
  number was two errors cancelling. See VALIDATION_STATUS.md for the full
  read-before-quoting notes.

## UI

- UNCERTAINTY and CORRELATION dock panels on all three motor pages,
  verified in a live browser pass.
- Fixed Plotly charts rendering at default width when drawn in a hidden
  dock tab (resize on tab activation + first-draw deferral).

Full validation posture: VALIDATION_STATUS.md (auto-generated correlation
block + honesty notes). User guide: USER_MANUAL.md section 7.
