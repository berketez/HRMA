# HRMA - Release Process

How an HRMA version is built, published, and delivered to installed
applications. The full build details live in
[`packaging/README.md`](../packaging/README.md); this document is the
overview.

## Single Source of Version Truth

The version lives in **one** place:

```python
# hrma/__init__.py
__version__ = "2.4.6"
```

Every build script (`build_mac_app.sh`, `build_dmg.sh`,
`publish_release.sh`) reads the version from this file. The Windows
installer receives it explicitly on the makensis command line and it must
match `__init__.py`; the version is never hardcoded anywhere else.

## Release Artifacts

Each release ships exactly two assets, named so the in-app update checker
can find them:

| Platform | Asset | Built by |
|---|---|---|
| macOS 11+ (Apple Silicon) | `HRMA-Setup-X.Y.Z-macOS.dmg` | `packaging/build_mac_app.sh` + `packaging/build_dmg.sh` |
| Windows 10/11 | `HRMA-Setup-X.Y.Z.exe` | `packaging/build_win_payload.sh` + `makensis -DVERSION=X.Y.Z packaging/hrma.nsi` |

Both bundles embed a Python 3.12 runtime and all dependencies (CoolProp,
build123d/OpenCascade, RocketCEA, offline Plotly/Three.js, ...), so end users
never need Python or an internet connection. Both are produced on a single
macOS machine; no Windows build machine is required (the exe is
cross-assembled with NSIS via `brew install makensis`).

## Code Signing (macOS) — mandatory, fail-closed

`build_mac_app.sh` ad-hoc signs the bundle (`codesign --force --no-strict
-s -`) and then verifies it (`codesign --verify --deep`) as its final step.
**If either step fails, the build stops.** Release gate 6/6 re-verifies the
built `.app` (`--deep`) and the app *inside* the DMG, the latter twice: a
fast `--deep` check on the mounted volume plus the gold standard — an
xattr-stripped copy (`ditto --noextattr`) that must pass the full
`codesign --verify --deep --strict`. An unsigned artifact closes the gate.

Why this is non-negotiable: versions 2.6.0-2.6.2 shipped **unsigned**
because the old codesign line ended in `2>/dev/null || true` and swallowed
its own failure. Pre-Tahoe macOS tolerated the unsigned app; macOS Tahoe's
`lsd` records it as launch-disabled (error -67062, "code object is not
signed at all"), `open` reports "executable is missing", and the auto-update
helper rolls the user back to the previous version (field incident,
2026-07-28, `~/Documents/HRMA/hrma_update_log.txt`).

Two empirically measured constraints shape the current design (2026-07-30,
reproduced on the real 1.4 GB bundle):

1. **The build tree lives under iCloud sync.** Finder/fileproviderd rewrites
   `com.apple.FinderInfo` onto the `.app` root within milliseconds of
   removal, so a clean-then-sign sequence loses the race and codesign fails
   with "resource fork, Finder information, or similar detritus not
   allowed". Signing therefore uses `--no-strict`, which skips only that
   detritus pre-check; the xattr is not part of the seal, so the produced
   signature is identical to one made on a clean tree. Strict
   *verification* rejects the same detritus, which is why in-place
   verification uses `--deep` without `--strict`; the strict check runs in
   the release gate on an xattr-stripped copy of the DMG payload (measured:
   it passes). Long term, moving the build tree out of iCloud
   (`packaging/mac/build.noindex` -> a non-synced location) would remove
   this constraint entirely; that requires touching `build_dmg.sh` and is
   left as a recommendation.
2. **Everything in `Contents/MacOS` must itself be signed code.** The
   launcher script `hrma_baslat.sh` used to live there and broke the bundle
   signature ("code object is not signed at all — In subcomponent"). The
   script now lives in `Contents/Resources/` (hash-sealed like any resource)
   with a symlink at `Contents/MacOS/hrma_baslat.sh`; the arm64 stub invokes
   it through `/bin/bash`, so no executable bit or nested signature is
   needed. The update helper copies with `ditto`, which preserves symlinks.

The signature is **ad-hoc** (`-s -`): Gatekeeper's `spctl --assess` rejects
ad-hoc apps by design, so the acceptance criterion is `codesign --verify
--deep --strict`, which is exactly the check that catches the "not signed at
all" failure mode. Guard tests: `tests/test_packaging_signature.py`.

## Release Steps

```bash
# 1) Bump the version (single source)
#    edit hrma/__init__.py -> __version__ = "X.Y.Z"

# 2) Build macOS app + DMG (reads version from hrma/__init__.py)
bash packaging/build_mac_app.sh
bash packaging/test_bundle_mac.sh     # import + server smoke test (mandatory)
bash packaging/build_dmg.sh           # -> dist/HRMA-Setup-X.Y.Z-macOS.dmg

# 3) Build Windows installer (version passed explicitly, must match step 1)
bash packaging/build_win_payload.sh   # embedded Python + win_amd64 wheels
makensis -DVERSION=X.Y.Z packaging/hrma.nsi   # -> HRMA-Setup-X.Y.Z.exe

# 4) Publish the GitHub Release
bash packaging/publish_release.sh "Release notes..."
```

`publish_release.sh`:

- reads the version from `hrma/__init__.py` and verifies both assets exist
  in `dist/`,
- creates the GitHub Release `vX.Y.Z` with both assets
  (`gh release create`),
- rewrites the direct download links in `README.md` to the new version
  (commit that change afterwards).

## How Installed Apps Pick Up the Release

The in-app update checker (`hrma/utils/update_checker.py`) runs at startup:

1. It queries the GitHub Releases API for the latest release of
   `berketez/HRMA` and compares the tag (`vX.Y.Z`) against the running
   `__version__`.
2. If newer, it selects the platform-appropriate asset from the release
   **by file suffix**: `.dmg` on macOS, `.exe` on Windows. Asset URLs come
   only from the GitHub API response, so external URL injection is not
   possible.
3. The UI offers a one-click download into the user's Downloads folder with
   progress reporting, then hands off to the OS installer. If no matching
   asset exists, the Releases page is opened instead.
4. When offline, the check fails silently and the app runs normally.

This is why the asset naming convention above is a contract: a release
without a `.dmg` and an `.exe` asset will not be offered to installed
applications on that platform.

## Version History (recent)

- **v2.4.6**: comparative analysis panel, Leckner gas-emissivity
  radiation, NHNE injector fallback fixes, real pintle/swirl cross-section
  drawings, warning panel in the UI, documentation overhaul, dead-route
  cleanup (`/optimize`, `/api/generate-cad`).
- **v2.4.5**: physics audit: 32 findings fixed (kinetic efficiency,
  explosion energy, altitude Isp, T/W, Bartz, erosive burning), brand
  sweep.
- **v2.4.0**: 13-panel Analysis Deck, quasi-1D nozzle flow, staged
  kinetics, materials database, 1,000+ automated tests.
- **v2.3**: native desktop window (pywebview), instant splash, automatic
  updates via GitHub Releases, English installers.

Release notes for shipped versions are kept in
`packaging/release_notes_v*.md`.

## Support

- Create an issue: https://github.com/berketez/HRMA/issues
- Documentation: `README.md`, `docs/USER_MANUAL.md`, `docs/`
