# Contributing to HRMA

HRMA computes numbers that people use to decide how much pressure a chamber
will see and how thick its wall has to be. That single fact sets the tone of
everything below: **a plausible number is worse than no number**, because a
missing number gets questioned and a plausible wrong one does not.

Read `docs/VALIDATION_STATUS.md` before you change any physics. It is the
honest statement of what is verified, what is validated, and what is not.

## 1. Development setup

Python **3.10–3.13** (3.12 recommended). Python 3.14 is not supported: HRMA
pins `numpy<2` and the compiled dependencies (CoolProp, RocketCEA, manifold3d)
have no 3.14 wheels for that ABI.

```bash
git clone https://github.com/berketez/HRMA.git
cd HRMA
python3 -m pip install -r requirements-dev.txt   # includes requirements.txt
```

Notes that will save you an afternoon:

- **`numpy<2` is a hard pin.** Installing `build123d` (STEP export) drags in
  numpy 2.x, which removes `np.trapz` and breaks a large part of the suite.
  That is why `build123d`/`OCP` are deliberately absent from
  `requirements-dev.txt` and the STEP tests use `pytest.importorskip`. If you
  need them, use a separate environment.
- **RocketCEA compiles Fortran on install** — you need `gfortran`.
- **RocketCEA uses one shared scratch directory** (`~/RocketCEA`). Two CEA
  processes at once can corrupt it (`Fortran runtime error: End of file`). If
  you run test sessions in parallel, give each one its own directory with
  `rocketcea.cea_obj.set_rocketcea_data_dir(...)`.
- `cantera` is required, not optional. Without it the combustion solver falls
  back to a propellant-independent composition and silently produces wrong c*.

Run the app:

```bash
python3 hrma/run.py          # http://localhost:8080
```

## 2. Running the tests

```bash
MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/ -q      # full suite
MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/test_correlation_guards.py -q
```

The full suite takes roughly 15–20 minutes locally (several tests run real
thermochemistry and real solvers — that is the point of them). CI runs exactly
the same command on a clean machine: `.github/workflows/tests.yml`.

`MPLBACKEND=Agg` is required on headless machines, and `PYTHONPATH=.` is
required because HRMA is not installed as a package.

## 3. What a correct change looks like

### 3.1 Never invent a number

This is the project's oldest and most expensive class of bug, and there is
machinery in the repo dedicated to it:

- If a quantity cannot be computed from the user's input, **do not substitute a
  default and present it as a result.** Declare it: return `None`, raise, or
  emit an explicit `NOT_MODELLED` / `not available` marker that reaches the
  user interface.
- If a value comes from a template, a handbook or a placeholder rather than
  from this analysis, it must carry a `basis`/`source` field saying so.
- Status strings (`OPTIMIZED`, `CALCULATED`, `ACCEPTABLE`) are **verdicts**.
  A verdict must read the flags the solver wrote — a run that did not converge
  cannot report `CALCULATED`.
- The same applies to the user interface: no placeholder readouts, no animated
  progress that is not driven by real progress.

### 3.2 Units are part of the contract

Two separate 1000× errors (STL written in metres while the documentation said
millimetres; DXF `$INSUNITS` set to metres while the geometry was in
millimetres) survived several manual sweeps. When you touch geometry, export,
or any cross-module interface, state the unit in the name or the comment, and
add a test that reads the artefact back and checks an absolute dimension.

### 3.3 Cite standards correctly or not at all

`docs/STANDART_ATIFLARI.md` is the registry of every standard HRMA cites:
number, full title, revision, the clause used, and where it is used.
`tools/iddia_lint.py` checks the tree against it and also rejects unearned
claims ("NASA-grade accurate", "validated", "professional-grade"):

```bash
python3 tools/iddia_lint.py          # exit 1 if there is an unregistered hit
python3 tools/iddia_lint.py --debt   # the acknowledged open debts
```

If you add a citation, add it to the registry first.

### 3.4 Every behaviour change needs a guard test

Not "a test" — a test that **fails on the old behaviour**. Run it against the
unfixed code and watch it go red before you keep it. Three tests in this repo
were previously locking defects in place as if they were contracts (a wrong
inertia formula frozen to `rel=1e-12`, a string check that missed the actual
sentence, a bounding box measured from STEP text instead of the imported
solid), which is exactly what happens when a test is written after the fact to
match whatever the code already does.

New defects get an entry in `docs/BULGU_KAYIT_DEFTERI.md` linked to the test
that guards them; `tests/test_findings_registry.py` verifies that every
referenced `test_file.py::test_name` actually exists.

### 3.5 Comments explain *why*, with the measurement

Turkish is fine (and dominant) in comments; use correct Turkish characters
(`ç ğ ı İ ö ş ü`). Code symbols — variables, functions, classes — stay in
English. The important part is content: write down the number you measured.

```python
# Ölçüm: analiz 124,0 mm cidar veriyor, STEP 109,0 mm yazıyordu — katıda
# anahtar adı 'case_analysis', export 'chamber_analysis' arıyordu.
```

## 4. Pull requests

Before opening one:

1. `MPLBACKEND=Agg PYTHONPATH=. python3 -m pytest tests/ -q` is green
   — the whole suite, not a subset. A green subset is how a red release
   happened once already.
2. `python3 tools/iddia_lint.py` exits 0.
3. New or changed behaviour has a guard test, and you have seen it fail
   without your fix.
4. `git diff` contains nothing unrelated to the stated purpose.

In the description, state: what was wrong, how you measured it (the actual
numbers), what changed, and what test now prevents the regression. "Improved
accuracy" is not a description.

### Optional but recommended: pre-commit

```bash
python3 -m pip install pre-commit
pre-commit install
pre-commit run --all-files      # first run, to see where you stand
```

`.pre-commit-config.yaml` runs the fast checks only (syntax-level flake8, file
hygiene, the claim lint). It is a seatbelt, not the test suite.

## 5. Releases

Releases are gated mechanically, because they have gone wrong twice:

- v2.6.2 was published 14 minutes after CI finished **red**, and the
  application computed nothing on the user's machine.
- v2.6.25's installers were built **37 minutes before** the commit they claimed
  to represent, and the release went out **7 minutes 25 seconds before** CI
  turned green.

So:

```bash
bash packaging/release_gate.sh          # 7 gates, all must pass
bash packaging/publish_release.sh       # runs the gate, then publishes
```

The gate checks version consistency across `hrma/__init__.py`,
`hrma/data/changelog.json`, `packaging/release_notes_v*.md` and README; a clean
and pushed tree; **artefact mtime later than the commit**; **all CI runs for
that exact SHA complete and green**; the full local suite; a live smoke test on
a non-default port; and the macOS package signature.

The gate can only be skipped for **draft** releases, and only with a written
reason (`TASLAK=1 KAPIYI_ATLA=1 KAPIYI_ATLA_GEREKCE="..."`). The reason is
recorded in `packaging/release_gate_bypass.log` and printed at the top of the
draft's own release notes. A public release cannot be produced with the gate
skipped.

At release time also bump `version`/`date-released` in `CITATION.cff`.

## 6. Ground rules

- MIT licensed (see `LICENSE`); contributions are accepted under the same
  licence.
- Do not commit secrets, tokens, or personal data. Do not commit build outputs
  (`dist/`, `packaging/mac/`, `packaging/win/`) — they are gitignored and
  measured in gigabytes.
- Security issues go to `SECURITY.md`, not to a public issue.
