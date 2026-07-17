"""RETIRED MODULE (v2.5.0 G1, 2026-07-17) — synthetic layer dismantled.

This module previously held an in-memory "experimental" database of 11
SYNTHETIC records (literature-inspired operating points with generated
sinusoid + seeded-noise time series), persisted them to SQLite
(data/experimental_data.db) on every startup, and exposed a global
``experimental_validator`` instance.

Per the v2.5.0 correlation design (docs/arge-guven-2026-07/
arge_korelasyon_tasarim.md, decisions K1/K5/K6, Berke-approved):

- The 11 synthetic records were converted to the new record schema and moved
  to ``tests/fixtures/synthetic_experiments.json`` (each with
  ``synthetic: true``). They exist ONLY as deterministic pipeline fixtures
  and are structurally barred from production statistics.
- The SQLite layer is fully retired: nothing writes or reads
  ``data/experimental_data.db`` anymore.
- The dead ``/api/experimental-validation`` endpoint (which called methods
  that never existed on this class) was removed from ``hrma/app.py``.

Successor: the git-tracked REAL experiment database.

- Records: ``hrma/data/validation_records/{hybrid,solid,liquid}/*.json``
  (schema: ``hrma/data/validation_records/SCHEMA.md``)
- Loader/validator/statistics: ``hrma.validation.experiment_db``
- Correlation runner: G2 dalgasinda (``correlation.py``) gelecek.

Bu dosya bilerek bos bir mezar tasidir: eski ``experimental_validator``
sembolunu import etmeye calisan bayat kod ImportError ile YUKSEK SESLE
kirilsin (sessizce sentetik veri uretmesin) diye geriye-uyumluluk shim'i
konmamistir.
"""
