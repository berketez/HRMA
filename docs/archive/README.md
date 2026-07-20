# Archived Documentation — Do Not Use as Reference

The documents in this directory describe an **early-stage aspirational /
fictional architecture** of HRMA. They do **not** reflect the shipped
product. Examples of content that was never implemented:

- A public REST API (`/api/v1`, `api.hrma.space`, authentication, rate
  limits, WebSockets) — HRMA is a local desktop application; its Flask
  routes are internal to the app.
- Redis caching, PostgreSQL, Kubernetes/microservice deployment, React
  SPA, Kong/Istio gateways — none of these exist.
- A MATLAB toolchain and `.mat` exports — HRMA is pure Python.
- Module/function listings written for a planned flat layout, naming
  classes and functions that were never created.

These files are kept only as project history. Verified spot checks
(2026-07-16) confirmed multiple functions, routes, and services documented
here are absent from the codebase.

**Current, accurate sources:**

- [`README.md`](../../README.md) (repository root) — product overview,
  features, real project structure
- [`USER_MANUAL.md`](../USER_MANUAL.md) — installation and usage of the
  actual application
- [`VALIDATION_STATUS.md`](../VALIDATION_STATUS.md) — what is verified,
  what is not
- [`docs/ANALIZ_PLATFORM_PLANI.md`](../ANALIZ_PLATFORM_PLANI.md) — analysis
  platform plan and its implementation status
- [`docs/bolum2..bolum9`](../) — theory derivations tied to the real code
  paths
- [`docs/10_Enjektor_ARGE.md`](../10_Enjektor_ARGE.md) — injector design
  module contract (implemented)
