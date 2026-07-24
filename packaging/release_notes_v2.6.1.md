# HRMA v2.6.1 — Update reliability + user guide

A focused follow-up to v2.6.0 that fixes the automatic-update path, removes
the last piece of fabricated output found in an external review, and ships an
illustrated user guide in English and Turkish.

## Automatic updates keep working when GitHub throttles the network

The update check used only the GitHub REST API, which allows anonymous
clients **60 requests per hour per IP address**. On a shared or NAT'd network
(dorm, office, mobile carrier) that quota can already be exhausted by someone
else, and HRMA then reported *"Could not reach the update server"* even though
a new version was published.

- HRMA now falls back to GitHub's ordinary release pages, which are **not**
  subject to the API quota: the latest tag is resolved from the
  `/releases/latest` redirect, installer links from the release's asset
  fragment, and the release notes from the Atom feed.
- Only download links belonging to this repository are accepted on the
  fallback path, so a foreign link on the page can never become the installer
  URL.
- When both paths fail, the message now states the real cause (rate limit vs.
  no network) and offers a one-click link to the releases page.

## Clearer macOS update experience

The silent macOS install copies ~1.5 GB and could take a few minutes with no
on-screen feedback, which looked like a crash. Now:

- A system notification is shown when the install starts, and again when it
  finishes.
- The update dialog states that the install takes 2–4 minutes and that HRMA
  should not be opened by hand until it reopens itself.
- Half-finished `.download` files left by a mid-update quit are cleaned up
  automatically.

## Honesty and documentation

- Removed a hard-coded "performance optimization" block from the solid-motor
  output (fixed expansion ratio, chamber pressure and margin unrelated to the
  analyzed motor). It was unused and fabricated; a guard test now prevents it
  from returning.
- `app.py` no longer starts in Flask debug mode when run directly (opt in with
  `HRMA_DEBUG=1`).
- README and `VALIDATION_STATUS.md` brought back in sync with the current
  correlation database (n = 14 liquid vacuum Isp, ~209 records); the overstated
  "digital twin" wording is now "interactive 3D model" throughout.
- **New illustrated user guide** (English and Turkish) with a complete worked
  example, shipped as a PDF inside the app (top-bar "User Guide" link) and in
  `docs/user_guide/`.

## Downloads

| Platform | Installer |
|---|---|
| Windows 10/11 | `HRMA-Setup-2.6.1.exe` |
| macOS 11+ (Apple Silicon) | `HRMA-Setup-2.6.1-macOS.dmg` |

Tests: 2711 passed, 1 skipped.
