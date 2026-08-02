# Security Policy

## Reporting a vulnerability

Send the report to **btezgocen97@gmail.com** with `HRMA security` in the
subject line. Please include:

- the HRMA version (Help → About, or `hrma/__init__.py` `__version__`),
- your operating system and how you installed HRMA (installer or source),
- the smallest input, file or request that reproduces the problem,
- what you observed and what you expected.

Do **not** open a public GitHub issue for an unfixed vulnerability, and do not
attach real credentials, private keys, or proprietary motor data to the report.

### What to expect

| Stage | Target |
|---|---|
| Acknowledgement that the report arrived | 5 working days |
| First assessment (reproduced / not reproduced / need more input) | 15 days |
| Fix or documented mitigation for a confirmed issue | 90 days |
| Public disclosure | after the fix ships, or 90 days after the report — whichever comes first, coordinated with the reporter |

This is a single-maintainer project, not a company with an on-call rota. The
timelines above are the honest targets; if one is going to be missed you will
be told, rather than left waiting.

## Supported versions

Only the **latest published release** receives security fixes. HRMA ships as a
self-updating desktop application (`hrma/utils/update_checker.py`), so the
supported path for any security fix is "update to the newest release".

| Version | Supported |
|---|---|
| Latest release (2.6.x line) | Yes |
| Any older release | No — update instead |

## Threat model (what this project does and does not defend against)

HRMA is a **local desktop application**. It runs a Flask/waitress server bound
to `127.0.0.1` and opens its own window; it is not designed, hardened or tested
as a multi-user or internet-facing service.

**In scope** — these are treated as security bugs:

- Escaping the loopback binding, or the `Host`/`Origin` gate that rejects
  non-loopback requests (`hrma/app.py`).
- Code execution or file writes triggered by opening/importing a file
  (`.ork` rocket files, `.xlsx`/`.csv` imports, cached propellant data,
  saved motor JSON).
- Path traversal or arbitrary file read/write through any export endpoint
  (STEP, DXF, STL, PDF, XLSX, ZIP) — including the archive entry names.
- Formula/command injection into generated artefacts (spreadsheet formulas,
  shell metacharacters in filenames).
- Leaking user data outside the machine, including into the support bundle or
  log files.
- Denial of service that a *single legitimate-looking input* can cause (an
  unbounded allocation from one uploaded file, not a flood of requests).

**Out of scope** — real, but not treated as vulnerabilities here:

- Anything that requires an attacker who already has local code execution or
  can write to your home directory. That attacker has already won.
- Exposing HRMA to a network yourself (reverse proxy, `--host 0.0.0.0`
  modifications, port forwarding). HRMA is not built for this.
- Request-flood denial of service against your own loopback server.
- Numerical/physics errors. Those are correctness bugs — please report them as
  normal issues; see `docs/VALIDATION_STATUS.md` for the known limits.

## Known, deliberately accepted weaknesses

Stated here rather than discovered later:

- **macOS packages are ad-hoc signed** (`codesign -s -`), not signed with an
  Apple Developer ID and **not notarized**. The release gate verifies that the
  signature exists and that the seal holds (`packaging/release_gate.sh`, step
  7/7), which is what caught three unsigned releases, but ad-hoc signing does
  not prove publisher identity. Gatekeeper will warn you.
- **Windows installers are unsigned.** SmartScreen will warn you.
- **Git tags are lightweight and commits are unsigned.** There is no
  cryptographic chain from a release artefact back to a signed commit. What
  *is* enforced mechanically is the ordering and the exact-SHA binding:
  artefacts must be built after the commit they claim to represent, and CI must
  be green for that exact SHA before publishing
  (`packaging/release_gate.sh`, `.github/workflows/release.yml`).
- **The auto-updater trusts GitHub's TLS and the release API**, nothing more.
  There is no signature verification of the downloaded installer.

If you need a stronger supply chain than this, build from source and verify the
tree yourself.
