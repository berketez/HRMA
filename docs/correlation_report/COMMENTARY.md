### Overall agreement

Across the three motor types HRMA tracks the measured data at the level
expected of a preliminary-design tool built on theoretical thermochemistry.
Hybrid characteristic velocity agrees with 18 static-fire measurements to a
median APE of about 2 % with essentially zero bias after the 2026-07-18
thermochemistry corrections (HTPB heat of formation moved to the CEA R-45
card value; gaseous-oxygen oxidizer path fixed). Liquid vacuum specific
impulse matches four published engine ratings (RL10, F-1, J-2, Vulcain
family) within ~3 %. Solid strand burn rates reproduce the Nakka KNDX/KNSB
dataset to below 1 % median APE, with the important caveat discussed under
Limitations: that comparison is in-sample by construction.

### Systematic biases

The remaining biases are one-directional and physically interpretable, and
we deliberately report them rather than tune them away:

- **Chamber pressure (hybrid, +17 %)**: HRMA closes the pressure loop with
  the *theoretical* equilibrium c\*. The measured combustion efficiencies in
  the GOX/paraffin campaign (0.77-0.90) are not fed back into the model —
  doing so would make the comparison circular. A positive offset of roughly
  1/eta_c\* is therefore the expected behaviour of an uncalibrated
  theoretical model, and the per-test residuals close to within a few percent
  when multiplied by the *measured* efficiency (reported for information
  only, never scored).
- **Isp and thrust (hybrid, +10 %)**: the model uses ideal nozzle thrust
  coefficients; divergence, viscous and small-throat losses are not modelled
  and the records carry no nozzle geometry that would allow a defensible
  correction. Note that the previous release reported an artificially good
  +1.8 % here — that was two errors cancelling (a c\* deficit multiplied by
  the CF excess), which the thermochemistry fix has made visible.
- **Regression rate (hybrid, -20 %)**: the aggregate hides two subsets. The
  paraffin/GOX campaign sits close to its own published law once the flux
  basis is honoured (coefficients are G_ox-based fits and are now evaluated
  as such in the validation layer). The low-flux HTPB/N2O laboratory motor
  subset is under-predicted by up to a factor of two: the single published
  a-n set (Doran 2007, validity ~10-30 g/cm^2 s) does not extend to the
  3-7 g/cm^2 s regime where radiation and small-motor effects dominate. This
  is a documented model limit; no coefficient was fitted to the validation
  data.

### Outliers and anomalies

Anomaly-flagged records are excluded from all headline statistics but kept
visible (open markers in the parity figures). They are exactly the tests the
source paper itself marks as off-nominal: nozzle failure and erosion cases,
fuel-port failures, a premature oxidizer cut, plus one record (4L-12) whose
published port diameter contradicts the paper's own mass-flux columns and
grain outer diameter — an internal inconsistency confirmed against the
primary PDF and quarantined rather than "corrected" by guesswork. The worst
main-layer chamber-pressure point is the throttling test (4Thr-1), which a
steady-state average-flow model can only represent approximately; it is
tagged off-nominal but retained. MAD-based outliers are flagged in the
tables and never dropped.

### Limitations

The database is small and uneven: 136 records, of which 76 currently score
(53 lack sufficient inputs for a blind rerun, 7 record types are not yet
supported by the v1 adapters). Liquid engines contribute only published
rating points, not test campaigns; the solid cell is a strand-burner
comparison whose coefficients derive from the same source dataset
(implementation validation, not independent prediction — the
`fit_source_records` field in `hrma/data/burn_rate_db.py` makes this
mechanically traceable); flight records are absent entirely. Delivered
combustion efficiency, nozzle losses and erosive effects are outside the
current model form and show up as the systematic biases discussed above.
Correlation-guard tests freeze the current table per cell against the
database content hash, so any silent degradation — or a suspiciously sudden
improvement, the classic symptom of measurement leaking into prediction —
fails or warns in CI.
