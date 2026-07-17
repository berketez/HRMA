"""Dogrulama modulleri."""

try:
    from hrma.validation.validation_system import validator, ValidationSystem
    from hrma.validation.motor_validation import motor_validator, MotorDataValidator
except ImportError as e:
    import warnings
    warnings.warn(f"Could not import some validation modules: {e}")

# v2.5.0 G1 (2026-07-17): sentetik experimental_validation katmani emekli
# edildi (kayitlar tests/fixtures/synthetic_experiments.json'a tasindi,
# SQLite yolu kaldirildi). Gercek deney kayitlari icin: experiment_db.
# Not: experiment_db saf fonksiyon modulu — import yan etkisi (dosya
# yukleme/DB kurma) YOKTUR; eski experimental_validator'in acilista SQLite
# kurma davranisi bilerek geri getirilmedi.
from hrma.validation import experiment_db
from hrma.validation.experiment_db import (
    ValidationRecordError,
    ensure_valid_record,
    load_records,
    load_records_from_file,
    records_for_statistics,
    summarize,
    validate_record,
)

# v2.5.0 G2 (2026-07-17): korelasyon kosucusu + kayit->motor adaptorleri.
# Iki modul de import aninda motor/kayit YUKLEMEZ (motor importlari fonksiyon
# icindedir) — acilis suresi etkilenmez.
from hrma.validation import correlation_runner, record_adapters
from hrma.validation.correlation_runner import (
    db_content_hash,
    deterministic_view,
    run_correlation,
    to_markdown,
)
from hrma.validation.record_adapters import adapt_record
