# HRMA v2.6.2 — Major release

The largest correctness release HRMA has had.

Two independent reviews were run against v2.6.1: an external audit of the
public source, and a line-by-line physics audit of every equation in the code.
Together they produced **over 300 findings**, including four critical physics
errors that were changing numbers users act on. All of them are fixed here,
each one measured before and after rather than estimated.

On top of that, the launch site becomes a real feature: **you can now fly the
motor you just designed** over NASA satellite imagery, with its actual thrust
curve, from a launch site you pick anywhere on Earth — with Earth rotation
modelled and a stability gate that refuses to animate a vehicle that would
tumble.

At a glance:

- **4 critical physics errors** fixed (swirl injector, slosh damping, chamber
  wall, end caps) — plus ~100 further corrections across every engine and
  analysis module
- **2 security holes** closed, one of them an arbitrary file read on Windows
- **Launch site wired end to end** — real motor, real thrust curve, satellite
  tiles, Coriolis, stability gate
- **Fabricated output removed** — fake regulatory compliance, fake successful
  exports, `NaN` presented as `0.0`, invented manufacturing specifications
- **Cantera is now a required dependency** — its silent absence was producing
  thermochemistry that ignored the propellant entirely
- **~3000 tests**, including a machine-checked release gate that verifies every
  fix below is still in place

## Physics corrections

Each of these was measured against a reference before and after the fix, not
estimated.

**A swirl-injector coefficient was inverted.** The Giffen–Muraszew geometric
constant was written as √(32/π²) = 1.80063 instead of its reciprocal
π/(4√2) = 0.55536. The consequence was visible but easy to miss: the largest
spray half-angle the code could produce was **15.9°**, while real
pressure-swirl atomisers routinely reach 30–60°. Discharge coefficient came
out 2.0–2.7× low, and since Cd sets the injection area directly
(A = ṁ/(Cd·√(2ρΔP))), total orifice area was **1.7–2.7× oversized**. The
default 45° spray target is now solved exactly; previously it silently fell
back to a fixed constant.

**Ring-baffle slosh damping was missing its amplitude term.** The Miles
correlation scales as √(η/R), where η is the free-surface wave amplitude. That
factor was absent, which implicitly assumed a wave amplitude equal to the whole
tank radius — contradicting the module's own declared small-amplitude theory.
A single ring baffle reported **18.6% of critical damping**; measured
single-baffle values are 1–10%. Overestimated damping is *not* conservative for
slosh stability, so the error pushed designs in the unsafe direction.

**The chamber-wall safety factor was tautological.** The code sized the wall
from an allowable stress and then computed the safety factor against that same
allowable, so the answer algebraically reduced to `safety_factor × 1.2` —
pressure, radius and material strength all cancelled. Measured: identical
4.8000 at 5, 20 and 50 bar. Sizing and verification are now separate modes;
verification requires the actual wall thickness.

**End-cap margins used a cylinder formula on a flat plate.** `P·R/t` is the
thin-wall hoop relation for a cylinder; it was applied to a flat circular
closure at the bolt-circle radius, which has no basis in Roark, Shigley or
ASME. It read 2.6× high at 5 bar and **3.0× low at 300 bar** — the dangerous
direction at high pressure.

**Tank STEP export scaled its geometry twice.** The producer emitted
millimetres and the consumer multiplied by 1000 again, so a 300 mm tank was
built as 300 metres. OpenCascade could not construct that solid and returned
an empty one *without raising*, so the safety path never triggered and users
downloaded a valid-looking but entirely empty STEP file.

**Product composition ignored the propellant.** When Cantera was unavailable,
equilibrium composition came from a fixed dictionary: LOX/HTPB, which contains
no nitrogen at all, still reported 54% N₂, and mean molecular weight was pinned
at 29.6 g/mol for every propellant pair. Measured c* error: −4.4% to −13.4%.
The fallback now derives composition from an elemental atom balance with a
water-gas-shift equilibrium, and **Cantera is a required dependency** — its
absence was silent, and the build now fails rather than ship an installer that
computes fabricated thermochemistry.

## Honest output

**Regulatory compliance is no longer claimed.** `nfpa_compliance`,
`osha_compliance` and `dot_compliance` returned an unconditional `True` — the
source comments said "would check ... requirements" — and the UI drew them as
green **OK** badges for every motor, of any size, with any propellant. These
fields now return `NOT_EVALUATED` and the panel states that the software does
not evaluate compliance and points to a qualified EHS authority.

**Failed exports no longer report success.** `/api/export-stl` had four
fallback paths, all returning HTTP 200. If CAD generation failed you received a
6-facet placeholder — not watertight, no nozzle, no port — while the UI said
"STL exported successfully". Export is now fail-closed: missing geometry
returns 422, a failed kernel returns 500.

**NaN and infinity no longer become numbers.** The final filter on nearly every
API response converted `NaN` to `0.0` and `±∞` to `±1e10`, so a divide-by-zero
or a diverged solver arrived on screen as a plausible measurement. They are now
`null` and render as a dash. A genuine zero is still a zero.

**Warnings were being suppressed process-wide.** Four modules called
`warnings.filterwarnings('ignore')` with no arguments, which installs a global
catch-all — importing a single engine module silenced NumPy's divide-by-zero
and invalid-value warnings across the entire application. Combined with the
NaN coercion above, this formed a complete silent-corruption chain: numerical
error → no warning → NaN → 0.0 → displayed as a measurement.

**Tank manufacturing output is labelled.** The tank CAD package shipped a
`manufacturing_specifications.json` whose baffle material, fastener grade, weld
process, ±0.1 mm tolerance, surface finish, test pressures and assembly
sequence were all fixed text; only the shell material came from the analysis.
Every field now carries `source: analysis` or `source: template`, and the file
is named for what it is.

## Security

**Arbitrary file read on Windows.** `/download/stl/<filename>` passed its
argument straight to `send_file`. Flask's default converter blocks `/` but not
backslash, and on Windows `\` is a path separator — so
`..\..\..\Windows\win.ini` escaped the export directory. Combined with the
wildcard CORS policy below, any web page open in the browser could read files
while HRMA was running.

**Wildcard CORS removed.** `CORS(app)` allowed every origin to read every
response. Binding to 127.0.0.1 is not sufficient protection: a malicious page
can still issue requests to a local port, and the wildcard let it read the
answers. Cross-origin state-changing requests are now rejected.

**Bounded work.** Request bodies are capped at 32 MB, the 6-DOF integrator has
a time-horizon limit (an escape trajectory never terminated), and concurrent
correlation runs are serialised instead of duplicating a two-minute job.

## Launch site

The flight page used to fly a hard-coded demo vehicle. It now flies **the motor
you calculated** — carried across with its real thrust curve — or a saved
`.hrma` project recomputed on the server. The engine-derived fields are locked
and marked; airframe and fin values are yours. Engine inert mass and airframe
dry mass are summed by the solver and kept separate from propellant mass, so
neither is double-counted.

The 3D Earth now loads NASA GIBS satellite imagery (~500 m) with a persistent
on-disk cache and a size cap. Offline, no substitute texture is drawn — the
base map simply stays.

Site latitude reaches the 6-DOF solver, so Earth rotation is modelled rather
than assumed away. Measured lateral drift for a 5 km sounding rocket: 1017 m at
the equator against 1030 m with rotation disabled.

Playback controls stay disabled until a flight is solved, and remain disabled
if the solved vehicle is aerodynamically unstable — the trajectory is still
drawn, but the app will not animate a rocket that would tumble.

## Verification

The full audit, with the measured numerical effect of every finding, is in
`docs/v262_specs/PHYSICS_AUDIT.md`.

A machine-checked release gate (`tests/test_v262_release_gate.py`) asserts that
each fix above is still in place and that every declared feature is actually
reachable from the UI. That last check exists because the recurring failure in
this codebase has been modules that were written but never connected —
`input_guard.py`, `flight_vehicle.py` and `tile_cache.py` were each complete
and each unreachable.
