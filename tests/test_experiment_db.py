"""Deney veritabani (experiment_db) kapsam testleri — v2.5.0 G1.

Kapsam:
  1. Elle yazilmis sema dogrulayicisi (gecerli kayit, eksik alan,
     inputs/measured cakismasi reddi, egri kurallari).
  2. Sentetik dislama garantileri (uretim agaci bekcisi + summarize'in
     parametresiz kosulsuz dislamasi).
  3. tests/fixtures/synthetic_experiments.json yuklemesi (11 tasinmis kayit).
  4. Uretim agacindaki gercek tohum kayitlarin (Rezaei t26, RS-25) yuklenip
     dogrulanmasi.
  5. Sokum teyidi: eski sentetik experimental_validator sembolu artik yok.
"""

import copy
import inspect
import json
from pathlib import Path

import pytest

from hrma.validation.experiment_db import (
    DEFAULT_RECORDS_DIR,
    ValidationRecordError,
    ensure_valid_record,
    filter_records,
    load_records,
    load_records_from_file,
    records_for_statistics,
    summarize,
    validate_record,
)

FIXTURES_FILE = Path(__file__).resolve().parent / "fixtures" / "synthetic_experiments.json"


def make_valid_record(**overrides):
    """Asgari gecerli kayit ureticisi (testler kopya uzerinde oynar)."""
    record = {
        "schema_version": "1.0",
        "test_id": "hyb-ornek2020-t01",
        "motor_type": "hybrid",
        "source": {
            "citation": "Yazar, 'Baslik', Dergi, 1(1), 1-10, 2020",
            "access": "open",
            "confidence": "high",
            "date_checked": "2026-07-17",
        },
        "propellants": {"oxidizer": "n2o", "fuel": "htpb"},
        "geometry": {"throat_diameter_mm": 8.9},
        "inputs": {"mdot_ox_gps": 95.77, "burn_time_s": 6.55},
        "measured": {"c_star_mps": 1514, "isp_s": 204.6},
        "units_original": "g/s, s, m/s (kaynak tablosu)",
        "digitized": False,
    }
    record.update(copy.deepcopy(overrides))
    return record


def write_record(base_dir, subdir, record, filename=None):
    """Kaydi gecici uretim-agaci duzeninde diske yaz."""
    d = base_dir / subdir
    d.mkdir(parents=True, exist_ok=True)
    name = filename or f"{record['test_id']}.json"
    path = d / name
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. Sema dogrulayicisi
# ---------------------------------------------------------------------------

class TestValidator:
    def test_valid_record_passes(self):
        assert validate_record(make_valid_record()) == []

    def test_ensure_valid_returns_record(self):
        record = make_valid_record()
        assert ensure_valid_record(record) is record

    def test_non_dict_rejected(self):
        assert validate_record([1, 2, 3]) != []

    @pytest.mark.parametrize("missing", [
        "test_id", "motor_type", "source", "propellants", "geometry",
        "inputs", "measured", "units_original", "digitized",
    ])
    def test_missing_required_field(self, missing):
        record = make_valid_record()
        del record[missing]
        errors = validate_record(record)
        assert any(missing in e for e in errors), errors

    def test_unknown_top_level_field_rejected(self):
        record = make_valid_record()
        record["measurd"] = {"isp_s": 100}  # kasitli yazim hatasi
        errors = validate_record(record)
        assert any("bilinmeyen" in e and "measurd" in e for e in errors), errors

    def test_bad_motor_type(self):
        errors = validate_record(make_valid_record(motor_type="turbojet"))
        assert any("motor_type" in e for e in errors)

    def test_bad_confidence(self):
        record = make_valid_record()
        record["source"]["confidence"] = "very_high"
        errors = validate_record(record)
        assert any("source.confidence" in e for e in errors)

    def test_bad_access(self):
        record = make_valid_record()
        record["source"]["access"] = "secret"
        errors = validate_record(record)
        assert any("source.access" in e for e in errors)

    def test_bad_date_format(self):
        record = make_valid_record()
        record["source"]["date_checked"] = "17.07.2026"
        errors = validate_record(record)
        assert any("date_checked" in e for e in errors)

    def test_missing_citation(self):
        record = make_valid_record()
        del record["source"]["citation"]
        errors = validate_record(record)
        assert any("source.citation" in e for e in errors)

    def test_inputs_measured_overlap_rejected(self):
        """Dongusellik bekcisi: ayni anahtar iki blokta birden olamaz."""
        record = make_valid_record()
        record["measured"]["burn_time_s"] = 6.55  # inputs'ta da var
        errors = validate_record(record)
        # 2026-08-04: doğrulayıcı mesajları düzgün Türkçe imlaya geçti
        # ("dongusellik" -> "döngüsellik") — bekçi yeni metni arar.
        assert any("döngüsellik" in e and "burn_time_s" in e for e in errors), errors

    def test_inputs_value_must_be_number(self):
        record = make_valid_record()
        record["inputs"]["mdot_ox_gps"] = "95.77"
        errors = validate_record(record)
        assert any("inputs.mdot_ox_gps" in e for e in errors)

    def test_inputs_null_rejected(self):
        record = make_valid_record()
        record["inputs"]["mdot_ox_gps"] = None
        assert validate_record(record) != []

    def test_nan_rejected(self):
        record = make_valid_record()
        record["measured"]["isp_s"] = float("nan")
        errors = validate_record(record)
        assert any("measured.isp_s" in e for e in errors)

    def test_bool_is_not_a_number(self):
        record = make_valid_record()
        record["inputs"]["mdot_ox_gps"] = True
        assert validate_record(record) != []

    def test_measured_null_allowed(self):
        record = make_valid_record()
        record["measured"]["thrust_n"] = None
        assert validate_record(record) == []

    def test_empty_inputs_rejected(self):
        record = make_valid_record(inputs={})
        errors = validate_record(record)
        assert any("inputs" in e for e in errors)

    def test_uncertainty_key_must_exist(self):
        record = make_valid_record()
        record["measurement_uncertainty"] = {
            "nonexistent_qty": {"value": 0.01}
        }
        errors = validate_record(record)
        assert any("nonexistent_qty" in e for e in errors)

    def test_uncertainty_on_input_key_allowed(self):
        """Girdi belirsizligi (UQ icin) kayda baglanabilir."""
        record = make_valid_record()
        record["measurement_uncertainty"] = {
            "mdot_ox_gps": {"value": 0.0074, "type": "relative", "coverage_k": None}
        }
        assert validate_record(record) == []

    def test_uncertainty_value_positive(self):
        record = make_valid_record()
        record["measurement_uncertainty"] = {"isp_s": {"value": -0.01}}
        errors = validate_record(record)
        assert any("value" in e for e in errors)

    def test_curve_valid(self):
        record = make_valid_record()
        record["measured"]["pressure_trace_bar"] = {
            "time_s": [0.0, 1.0, 2.0], "value": [10.0, 11.0, 10.5]
        }
        assert validate_record(record) == []

    def test_curve_length_mismatch(self):
        record = make_valid_record()
        record["measured"]["pressure_trace_bar"] = {
            "time_s": [0.0, 1.0, 2.0], "value": [10.0, 11.0]
        }
        errors = validate_record(record)
        assert any("uzunlukları eşit" in e for e in errors)

    def test_curve_time_must_increase(self):
        record = make_valid_record()
        record["measured"]["pressure_trace_bar"] = {
            "time_s": [0.0, 2.0, 1.0], "value": [10.0, 11.0, 10.5]
        }
        errors = validate_record(record)
        assert any("kesin artan" in e for e in errors)

    def test_anomaly_flag_requires_note(self):
        record = make_valid_record()
        record["anomaly"] = {"flag": True}
        errors = validate_record(record)
        assert any("anomaly.note" in e for e in errors)

    def test_anomaly_valid(self):
        record = make_valid_record()
        record["anomaly"] = {"flag": True, "note": "Lule erozyonu gozlendi"}
        assert validate_record(record) == []

    def test_synthetic_must_be_bool(self):
        record = make_valid_record(synthetic="yes")
        errors = validate_record(record)
        assert any("synthetic" in e for e in errors)

    def test_bad_schema_version(self):
        record = make_valid_record(schema_version="9.9")
        errors = validate_record(record)
        assert any("schema_version" in e for e in errors)

    def test_error_messages_are_addressed(self):
        """ValidationRecordError mesaji dosya yolunu ve hatalari tasimali."""
        record = make_valid_record()
        del record["units_original"]
        with pytest.raises(ValidationRecordError) as exc_info:
            ensure_valid_record(record, path="ornek.json")
        assert "ornek.json" in str(exc_info.value)
        assert "units_original" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 2. Uretim agaci yuklemesi + yapisal sentetik bekcisi
# ---------------------------------------------------------------------------

class TestLoadRecordsTree:
    def test_synthetic_in_production_tree_raises(self, tmp_path):
        record = make_valid_record(synthetic=True)
        write_record(tmp_path, "hybrid", record)
        with pytest.raises(ValidationRecordError) as exc_info:
            load_records(base_dir=tmp_path)
        assert "sentetik" in str(exc_info.value).lower()

    def test_synthetic_loadable_only_with_explicit_flag(self, tmp_path):
        """Boru hatti testleri icin acik bayrakla yuklenebilir (uretim yolu degil)."""
        record = make_valid_record(synthetic=True)
        write_record(tmp_path, "hybrid", record)
        records = load_records(base_dir=tmp_path, exclude_synthetic=False)
        assert len(records) == 1 and records[0]["synthetic"] is True

    def test_folder_motor_type_mismatch_raises(self, tmp_path):
        record = make_valid_record()  # motor_type: hybrid
        write_record(tmp_path, "solid", record)
        with pytest.raises(ValidationRecordError) as exc_info:
            load_records(base_dir=tmp_path)
        assert "uyusmazligi" in str(exc_info.value)

    def test_duplicate_test_id_raises(self, tmp_path):
        write_record(tmp_path, "hybrid", make_valid_record(), filename="a.json")
        write_record(tmp_path, "hybrid", make_valid_record(), filename="b.json")
        with pytest.raises(ValidationRecordError) as exc_info:
            load_records(base_dir=tmp_path)
        assert "benzersiz" in str(exc_info.value)

    def test_invalid_record_stops_loading(self, tmp_path):
        bad = make_valid_record()
        del bad["units_original"]
        write_record(tmp_path, "hybrid", bad)
        with pytest.raises(ValidationRecordError):
            load_records(base_dir=tmp_path)

    def test_broken_json_reports_path(self, tmp_path):
        d = tmp_path / "hybrid"
        d.mkdir(parents=True)
        (d / "bozuk.json").write_text("{bozuk", encoding="utf-8")
        with pytest.raises(ValidationRecordError) as exc_info:
            load_records(base_dir=tmp_path)
        assert "bozuk.json" in str(exc_info.value)

    def test_missing_base_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_records(base_dir=tmp_path / "yok")

    def test_filters(self, tmp_path):
        hyb = make_valid_record()
        sol = make_valid_record(test_id="sol-ornek-01", motor_type="solid")
        sol["source"]["confidence"] = "medium"
        write_record(tmp_path, "hybrid", hyb)
        write_record(tmp_path, "solid", sol)

        assert len(load_records(base_dir=tmp_path)) == 2
        only_solid = load_records(base_dir=tmp_path, motor_type="solid")
        assert [r["test_id"] for r in only_solid] == ["sol-ornek-01"]
        only_high = load_records(base_dir=tmp_path, confidence="high")
        assert [r["test_id"] for r in only_high] == ["hyb-ornek2020-t01"]
        both = load_records(base_dir=tmp_path, confidence={"high", "medium"})
        assert len(both) == 2

    def test_invalid_filter_value_raises(self, tmp_path):
        (tmp_path / "hybrid").mkdir()
        with pytest.raises(ValueError):
            load_records(base_dir=tmp_path, motor_type="plasma")
        with pytest.raises(ValueError):
            load_records(base_dir=tmp_path, confidence="certain")


# ---------------------------------------------------------------------------
# 3. Fikstur dosyasi (tasinan 11 sentetik kayit)
# ---------------------------------------------------------------------------

class TestSyntheticFixtures:
    def test_fixture_file_exists(self):
        assert FIXTURES_FILE.is_file()

    def test_default_load_excludes_all_synthetic(self):
        """Varsayilan cagri sentetikleri filtreler: fikstur dosyasi bos doner."""
        assert load_records_from_file(FIXTURES_FILE) == []

    def test_fixtures_load_with_explicit_flag(self):
        records = load_records_from_file(FIXTURES_FILE, exclude_synthetic=False)
        assert len(records) == 11
        assert all(r["synthetic"] is True for r in records)
        assert all(r["source"]["confidence"] == "low" for r in records)
        ids = [r["test_id"] for r in records]
        assert len(set(ids)) == 11

    def test_fixtures_cover_all_motor_types(self):
        records = load_records_from_file(FIXTURES_FILE, exclude_synthetic=False)
        assert {r["motor_type"] for r in records} == {"hybrid", "solid", "liquid"}

    def test_fixtures_are_schema_valid(self):
        for record in load_records_from_file(FIXTURES_FILE, exclude_synthetic=False):
            assert validate_record(record) == [], record["test_id"]

    def test_fixture_curve_exercises_curve_path(self):
        records = load_records_from_file(FIXTURES_FILE, exclude_synthetic=False)
        with_curve = [
            r for r in records
            if any(isinstance(v, dict) for v in r["measured"].values())
        ]
        assert with_curve, "en az bir fikstur egri objesi tasimali"


# ---------------------------------------------------------------------------
# 4. Gercek tohum kayitlar (uretim agaci)
# ---------------------------------------------------------------------------

class TestProductionSeedRecords:
    def test_production_tree_loads(self):
        records = load_records()
        assert len(records) >= 2
        assert all(not r.get("synthetic", False) for r in records)

    def test_rezaei_anchor_present(self):
        records = load_records(motor_type="hybrid")
        by_id = {r["test_id"]: r for r in records}
        rezaei = by_id["hyb-rezaei2018-htpb-n2o-t26"]
        assert rezaei["source"]["confidence"] == "high"
        assert rezaei["measured"]["regression_rate_mmps"] == pytest.approx(0.779)
        assert rezaei["measured"]["c_star_mps"] == pytest.approx(1514)
        assert rezaei["measured"]["gox_gpcm2s"] == pytest.approx(6.88)
        assert rezaei["inputs"]["mdot_ox_gps"] == pytest.approx(95.77)
        # dongusellik: girdiler skorlanamaz, kesisme yok
        assert not set(rezaei["inputs"]) & set(rezaei["measured"])

    def test_rs25_anchor_present(self):
        records = load_records(motor_type="liquid")
        by_id = {r["test_id"]: r for r in records}
        rs25 = by_id["liq-rs25-109pct-spec"]
        assert rs25["record_type"] == "engine_spec"
        assert rs25["measured"]["isp_vac_s"] == pytest.approx(452.3)
        assert rs25["measured"]["thrust_vac_lbf"] == pytest.approx(512300)
        assert rs25["inputs"]["chamber_pressure_psia"] == pytest.approx(2994)
        assert not set(rs25["inputs"]) & set(rs25["measured"])

    def test_production_records_have_dated_sources(self):
        for record in load_records():
            assert record["source"]["date_checked"] >= "2026-01-01"
            assert record["source"]["citation"].strip()


# ---------------------------------------------------------------------------
# 5. Istatistik ozet + yapisal dislama garantileri
# ---------------------------------------------------------------------------

class TestStatisticsGuards:
    def test_records_for_statistics_drops_synthetic(self):
        real = make_valid_record()
        syn = make_valid_record(test_id="syn-ornek-01", synthetic=True)
        assert records_for_statistics([real, syn]) == [real]

    def test_summarize_excludes_synthetic_unconditionally(self):
        real = make_valid_record()
        syn_records = load_records_from_file(FIXTURES_FILE, exclude_synthetic=False)
        summary = summarize([real] + syn_records)
        assert summary["n_records"] == 1
        assert summary["n_synthetic_excluded"] == 11
        assert summary["test_ids"] == ["hyb-ornek2020-t01"]

    def test_summarize_has_no_inclusion_parameter(self):
        """Yapisal garanti: summarize/records_for_statistics'e sentetik dahil
        etme parametresi eklenemez — eklenirse bu test kirilir ve karar
        code review'a duser."""
        assert list(inspect.signature(summarize).parameters) == ["records"]
        assert list(inspect.signature(records_for_statistics).parameters) == ["records"]

    def test_summarize_production_tree(self):
        summary = summarize(load_records())
        assert summary["n_records"] >= 2
        assert summary["n_synthetic_excluded"] == 0
        assert summary["by_motor_type"].get("hybrid", 0) >= 1
        assert summary["by_motor_type"].get("liquid", 0) >= 1
        assert summary["by_confidence"].get("high", 0) >= 2
        assert summary["n_with_uncertainty"] >= 1

    def test_filter_records_in_memory(self):
        real = make_valid_record()
        syn = make_valid_record(test_id="syn-ornek-01", synthetic=True)
        assert filter_records([real, syn]) == [real]
        assert filter_records([real, syn], exclude_synthetic=False) == [real, syn]
        assert filter_records([real], motor_type="solid") == []


# ---------------------------------------------------------------------------
# 6. Sokum teyidi
# ---------------------------------------------------------------------------

class TestTeardown:
    def test_old_synthetic_validator_symbol_gone(self):
        """Eski global experimental_validator ve sinifi artik var olmamali."""
        import hrma.validation.experimental_validation as old_module
        assert not hasattr(old_module, "experimental_validator")
        assert not hasattr(old_module, "ExperimentalValidation")

    def test_validation_package_exports_experiment_db(self):
        import hrma.validation as vpkg
        assert hasattr(vpkg, "experiment_db")
        assert hasattr(vpkg, "load_records")
        assert hasattr(vpkg, "summarize")

    def test_default_records_dir_is_tracked_package_data(self):
        assert DEFAULT_RECORDS_DIR.name == "validation_records"
        assert (DEFAULT_RECORDS_DIR / "SCHEMA.md").is_file()
