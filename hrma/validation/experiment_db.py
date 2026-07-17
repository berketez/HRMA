"""Experiment database: git-tracked JSON validation records (v2.5.0 G1).

Loads, validates and summarizes REAL experiment records stored as one JSON
file per record under ``hrma/data/validation_records/{hybrid,solid,liquid}/``.
This module replaces the retired synthetic layer in
``experimental_validation.py`` (11 generated records + SQLite), whose records
now live only in ``tests/fixtures/synthetic_experiments.json`` with
``synthetic: true``.

Design guarantees (see hrma/data/validation_records/SCHEMA.md):

1. inputs / measured separation is a structural circularity guard: a key may
   not appear in both blocks; the validator rejects such records.
2. Synthetic records are structurally barred from production statistics:
   ``load_records`` (production tree) RAISES if it finds ``synthetic: true``,
   and ``summarize`` / ``records_for_statistics`` exclude synthetic records
   unconditionally — there is no parameter to include them.
3. No new dependencies: the validator is hand-written (``jsonschema`` is
   intentionally NOT used; it is not in the packaged bundle).

Hata mesajlari Turkce'dir (kuratorluk PR'larinda dogrudan okunur).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

__all__ = [
    "SCHEMA_VERSION",
    "MOTOR_TYPES",
    "CONFIDENCE_LEVELS",
    "ACCESS_VALUES",
    "RECORD_TYPES",
    "DEFAULT_RECORDS_DIR",
    "ValidationRecordError",
    "validate_record",
    "ensure_valid_record",
    "load_records",
    "load_records_from_file",
    "filter_records",
    "records_for_statistics",
    "summarize",
]

SCHEMA_VERSION = "1.0"
MOTOR_TYPES = ("hybrid", "solid", "liquid")
CONFIDENCE_LEVELS = ("high", "medium", "low")
ACCESS_VALUES = (
    "open", "paywalled", "public_domain", "webpage",
    "vendor_datasheet", "book", "synthetic",
)
# v2.5.0 G3 genislemesi: kuratorluk dalgasinin tags icinde tasidigi turler
# artik birinci sinif record_type degerleridir.
#   strand_burn_rate       -> Crawford/strand r(P) olcum noktasi (motor kosusu
#                             yok; Saint-Robert a-n noktasal kiyasi)
#   campaign_statistics    -> cok-yakmali kampanya mu/sigma/CI ozeti
#                             (v1 kosucusunda not_supported)
#   regression_correlation -> kaynagin kendi a-n / guc-yasasi fiti
#                             (v1 kosucusunda not_supported)
#   engine_test_point      -> motor testi nokta olcumu (engine_spec yoluyla
#                             nokta kiyas kosusu)
RECORD_TYPES = (
    "static_fire", "flight", "engine_spec",
    "strand_burn_rate", "campaign_statistics", "regression_correlation",
    "engine_test_point",
)
DATA_EXTRACTION_VALUES = ("table", "text", "figure_digitized", "vendor_datasheet")
UNCERTAINTY_TYPES = ("relative", "absolute")

# Kayit dosyalari paket icinde yasar (git-izlenen kuratorluk urunu);
# repo kokundeki gitignore'lu data/ dizini (hrma.DATA_DIR) ile karistirma.
DEFAULT_RECORDS_DIR = Path(__file__).resolve().parent.parent / "data" / "validation_records"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TEST_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,63}$", re.IGNORECASE)

_TOP_LEVEL_REQUIRED = (
    "test_id", "motor_type", "source", "propellants", "geometry",
    "inputs", "measured", "units_original", "digitized",
)
_TOP_LEVEL_OPTIONAL = (
    "schema_version", "record_type", "measurement_uncertainty",
    "anomaly", "synthetic", "tags", "notes",
)
_TOP_LEVEL_ALLOWED = frozenset(_TOP_LEVEL_REQUIRED + _TOP_LEVEL_OPTIONAL)

_SOURCE_REQUIRED = ("citation", "access", "confidence", "date_checked")
_SOURCE_OPTIONAL = ("doi", "url", "erratum", "data_extraction", "extraction_note")
_SOURCE_ALLOWED = frozenset(_SOURCE_REQUIRED + _SOURCE_OPTIONAL)

_UNCERTAINTY_ALLOWED = frozenset(("value", "type", "coverage_k", "source"))


class ValidationRecordError(ValueError):
    """Kayit sema denetiminden gecemedi (veya yukleme kurali ihlali)."""

    def __init__(self, errors: List[str], path: Optional[Union[str, Path]] = None):
        self.errors = list(errors)
        self.path = str(path) if path is not None else None
        prefix = f"{self.path}: " if self.path else ""
        message = prefix + "kayit dogrulamasi basarisiz:\n  - " + "\n  - ".join(self.errors)
        super().__init__(message)


def _is_number(value: Any) -> bool:
    """Sonlu gercek sayi mi (bool SAYI degildir)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _validate_curve(key: str, curve: Dict[str, Any], errors: List[str]) -> None:
    """measured altindaki egri objesini denetle: {"time_s": [...], "value": [...]}."""
    extra = set(curve) - {"time_s", "value"}
    if extra:
        errors.append(
            f"measured.{key}: egri objesinde bilinmeyen alan(lar): {sorted(extra)} "
            f"(izin verilen: time_s, value)"
        )
    for part in ("time_s", "value"):
        if part not in curve:
            errors.append(f"measured.{key}: egri objesinde '{part}' listesi eksik")
    times = curve.get("time_s")
    values = curve.get("value")
    for part_name, seq in (("time_s", times), ("value", values)):
        if seq is None:
            continue
        if not isinstance(seq, list) or len(seq) < 2:
            errors.append(f"measured.{key}.{part_name}: en az 2 elemanli liste olmali")
        elif not all(_is_number(v) for v in seq):
            errors.append(f"measured.{key}.{part_name}: tum elemanlar sonlu sayi olmali")
    if isinstance(times, list) and isinstance(values, list):
        if len(times) != len(values):
            errors.append(
                f"measured.{key}: time_s ({len(times)}) ve value ({len(values)}) "
                f"uzunluklari esit olmali"
            )
        if len(times) >= 2 and all(_is_number(v) for v in times):
            if any(t2 <= t1 for t1, t2 in zip(times, times[1:])):
                errors.append(f"measured.{key}.time_s: kesin artan olmali (zaman serisi)")


def validate_record(record: Any) -> List[str]:
    """Tek kaydi sema kurallarina gore denetle; hata listesi dondur (bos = gecerli).

    Elle yazilmis dogrulayici — jsonschema bagimliligi bilinçli olarak yok.
    Mesajlar Turkce ve alan-adresli ("source.confidence: ..." gibi).
    """
    errors: List[str] = []

    if not isinstance(record, dict):
        return ["kayit bir JSON objesi (sozluk) olmali"]

    # --- bilinmeyen ust duzey alanlar (yazim hatasi korumasi) ---
    unknown = set(record) - _TOP_LEVEL_ALLOWED
    if unknown:
        errors.append(
            f"bilinmeyen ust duzey alan(lar): {sorted(unknown)} "
            f"(izin verilenler: {sorted(_TOP_LEVEL_ALLOWED)})"
        )

    # --- zorunlu alan varligi ---
    for field in _TOP_LEVEL_REQUIRED:
        if field not in record:
            errors.append(f"zorunlu alan eksik: '{field}'")

    # --- schema_version ---
    if "schema_version" in record and record["schema_version"] != SCHEMA_VERSION:
        errors.append(
            f"schema_version: '{record['schema_version']}' desteklenmiyor "
            f"(beklenen: '{SCHEMA_VERSION}')"
        )

    # --- test_id ---
    test_id = record.get("test_id")
    if test_id is not None:
        if not _is_nonempty_str(test_id):
            errors.append("test_id: bos olmayan bir metin olmali")
        elif not _TEST_ID_RE.match(test_id):
            errors.append(
                f"test_id: '{test_id}' desen disi — [a-z0-9][a-z0-9_.-]{{2,63}} "
                f"bekleniyor (or. 'hyb-rezaei2018-t26')"
            )

    # --- motor_type / record_type ---
    if "motor_type" in record and record["motor_type"] not in MOTOR_TYPES:
        errors.append(
            f"motor_type: '{record['motor_type']}' gecersiz "
            f"(gecerli degerler: {list(MOTOR_TYPES)})"
        )
    if "record_type" in record and record["record_type"] not in RECORD_TYPES:
        errors.append(
            f"record_type: '{record['record_type']}' gecersiz "
            f"(gecerli degerler: {list(RECORD_TYPES)})"
        )

    # --- source ---
    source = record.get("source")
    if source is not None:
        if not isinstance(source, dict):
            errors.append("source: bir obje olmali (citation/access/confidence/date_checked)")
        else:
            unknown_src = set(source) - _SOURCE_ALLOWED
            if unknown_src:
                errors.append(f"source: bilinmeyen alan(lar): {sorted(unknown_src)}")
            for field in _SOURCE_REQUIRED:
                if field not in source:
                    errors.append(f"source.{field}: zorunlu alan eksik")
            if "citation" in source and not _is_nonempty_str(source["citation"]):
                errors.append("source.citation: bos olmayan tam kunye metni olmali")
            if "access" in source and source["access"] not in ACCESS_VALUES:
                errors.append(
                    f"source.access: '{source['access']}' gecersiz "
                    f"(gecerli degerler: {list(ACCESS_VALUES)})"
                )
            if "confidence" in source and source["confidence"] not in CONFIDENCE_LEVELS:
                errors.append(
                    f"source.confidence: '{source['confidence']}' gecersiz "
                    f"(gecerli degerler: {list(CONFIDENCE_LEVELS)})"
                )
            if "date_checked" in source:
                dc = source["date_checked"]
                if not (isinstance(dc, str) and _DATE_RE.match(dc)):
                    errors.append("source.date_checked: 'YYYY-AA-GG' bicimli tarih olmali")
            for opt in ("doi", "erratum"):
                if opt in source and source[opt] is not None and not _is_nonempty_str(source[opt]):
                    errors.append(f"source.{opt}: metin veya null olmali (tahmin YAZILMAZ)")
            if "url" in source and not _is_nonempty_str(source["url"]):
                errors.append("source.url: bos olmayan metin olmali")
            if ("data_extraction" in source
                    and source["data_extraction"] not in DATA_EXTRACTION_VALUES):
                errors.append(
                    f"source.data_extraction: '{source['data_extraction']}' gecersiz "
                    f"(gecerli degerler: {list(DATA_EXTRACTION_VALUES)})"
                )

    # --- propellants ---
    propellants = record.get("propellants")
    if propellants is not None:
        if not isinstance(propellants, dict) or not propellants:
            errors.append("propellants: bos olmayan bir obje olmali (or. oxidizer/fuel)")
        else:
            for key, value in propellants.items():
                if not (value is None or isinstance(value, str) or _is_number(value)):
                    errors.append(f"propellants.{key}: metin, sayi veya null olmali")

    # --- geometry ---
    geometry = record.get("geometry")
    if geometry is not None:
        if not isinstance(geometry, dict):
            errors.append("geometry: bir obje olmali")
        else:
            for key, value in geometry.items():
                if not (value is None or isinstance(value, (str, bool)) or _is_number(value)):
                    errors.append(f"geometry.{key}: metin, sayi, bool veya null olmali")

    # --- inputs ---
    inputs = record.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, dict) or not inputs:
            errors.append("inputs: bos olmayan bir obje olmali (deneyde ayarlanan buyuklukler)")
        else:
            for key, value in inputs.items():
                if not _is_number(value):
                    errors.append(
                        f"inputs.{key}: sonlu bir sayi olmali "
                        f"(olculmemis girdi kayda hic yazilmaz, null kullanilmaz)"
                    )

    # --- measured ---
    measured = record.get("measured")
    if measured is not None:
        if not isinstance(measured, dict) or not measured:
            errors.append("measured: bos olmayan bir obje olmali (deneyde olculen sonuclar)")
        else:
            for key, value in measured.items():
                if value is None or _is_number(value):
                    continue
                if isinstance(value, dict):
                    _validate_curve(key, value, errors)
                else:
                    errors.append(
                        f"measured.{key}: sonlu sayi, null veya egri objesi "
                        f"({{'time_s': [...], 'value': [...]}}) olmali"
                    )

    # --- dongusellik bekcisi: inputs ve measured kesisemez ---
    if isinstance(inputs, dict) and isinstance(measured, dict):
        overlap = sorted(set(inputs) & set(measured))
        if overlap:
            errors.append(
                f"dongusellik bekcisi: su anahtar(lar) hem inputs hem measured "
                f"icinde: {overlap} — bir buyukluk ayni anda girdi ve olculen "
                f"sonuc olamaz (girdiyle 'dogrulama' donguseldir)"
            )

    # --- measurement_uncertainty ---
    unc = record.get("measurement_uncertainty")
    if unc is not None:
        if not isinstance(unc, dict):
            errors.append("measurement_uncertainty: bir obje olmali")
        else:
            known_keys = set()
            if isinstance(inputs, dict):
                known_keys |= set(inputs)
            if isinstance(measured, dict):
                known_keys |= set(measured)
            for key, entry in unc.items():
                if key not in known_keys:
                    errors.append(
                        f"measurement_uncertainty.{key}: bu anahtar ne inputs ne "
                        f"measured icinde tanimli — belirsizlik yalnizca kayitli "
                        f"bir buyukluge baglanabilir"
                    )
                if not isinstance(entry, dict):
                    errors.append(
                        f"measurement_uncertainty.{key}: obje olmali "
                        f"({{'value': ..., 'coverage_k': ...}})"
                    )
                    continue
                unknown_unc = set(entry) - _UNCERTAINTY_ALLOWED
                if unknown_unc:
                    errors.append(
                        f"measurement_uncertainty.{key}: bilinmeyen alan(lar): "
                        f"{sorted(unknown_unc)}"
                    )
                if "value" not in entry:
                    errors.append(f"measurement_uncertainty.{key}.value: zorunlu alan eksik")
                elif not (_is_number(entry["value"]) and entry["value"] > 0):
                    errors.append(
                        f"measurement_uncertainty.{key}.value: pozitif sonlu sayi olmali "
                        f"(belirsizlik ASLA uydurulmaz; kaynak vermiyorsa alan hic yazilmaz)"
                    )
                if "type" in entry and entry["type"] not in UNCERTAINTY_TYPES:
                    errors.append(
                        f"measurement_uncertainty.{key}.type: "
                        f"{list(UNCERTAINTY_TYPES)} icinden olmali"
                    )
                if "coverage_k" in entry:
                    ck = entry["coverage_k"]
                    if not (ck is None or _is_number(ck) or _is_nonempty_str(ck)):
                        errors.append(
                            f"measurement_uncertainty.{key}.coverage_k: sayi, metin "
                            f"(or. 'stated') veya null olmali"
                        )

    # --- anomaly ---
    anomaly = record.get("anomaly")
    if anomaly is not None:
        if not isinstance(anomaly, dict):
            errors.append("anomaly: bir obje olmali ({'flag': bool, 'note': str})")
        else:
            unknown_an = set(anomaly) - {"flag", "note"}
            if unknown_an:
                errors.append(f"anomaly: bilinmeyen alan(lar): {sorted(unknown_an)}")
            flag = anomaly.get("flag")
            if not isinstance(flag, bool):
                errors.append("anomaly.flag: bool olmali (zorunlu)")
            if flag is True and not _is_nonempty_str(anomaly.get("note")):
                errors.append("anomaly.note: flag true ise bos olmayan aciklama zorunlu")
            if "note" in anomaly and anomaly["note"] is not None \
                    and not isinstance(anomaly["note"], str):
                errors.append("anomaly.note: metin olmali")

    # --- units_original / digitized / synthetic / tags / notes ---
    if "units_original" in record and not _is_nonempty_str(record["units_original"]):
        errors.append("units_original: kaynagin orijinal birimlerini ozetleyen metin olmali")
    if "digitized" in record and not isinstance(record["digitized"], bool):
        errors.append("digitized: bool olmali (grafikten sayisallastirma bayragi)")
    if "synthetic" in record and not isinstance(record["synthetic"], bool):
        errors.append("synthetic: bool olmali (varsayilan false)")
    if "tags" in record:
        tags = record["tags"]
        if not isinstance(tags, list) or not all(_is_nonempty_str(t) for t in tags):
            errors.append("tags: bos olmayan metinlerden olusan liste olmali")
    if "notes" in record and not isinstance(record["notes"], str):
        errors.append("notes: metin olmali")

    return errors


def ensure_valid_record(record: Any, path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Kaydi denetle; gecersizse ValidationRecordError firlat, gecerliyse kaydi dondur."""
    errors = validate_record(record)
    if errors:
        raise ValidationRecordError(errors, path=path)
    return record


def is_synthetic(record: Dict[str, Any]) -> bool:
    """Kayit sentetik mi (varsayilan: degil)."""
    return bool(record.get("synthetic", False))


def _normalize_filter(value: Optional[Union[str, Iterable[str]]],
                      valid: Tuple[str, ...], name: str) -> Optional[frozenset]:
    """motor_type/confidence filtre argumanini kumeye cevir ve denetle."""
    if value is None:
        return None
    if isinstance(value, str):
        values = {value}
    else:
        values = set(value)
    invalid = values - set(valid)
    if invalid:
        raise ValueError(
            f"{name} filtresi gecersiz deger(ler) iceriyor: {sorted(invalid)} "
            f"(gecerli: {list(valid)})"
        )
    return frozenset(values)


def _read_json(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValidationRecordError(
            [f"JSON cozumlenemedi: {exc}"], path=path
        ) from exc


def load_records(base_dir: Optional[Union[str, Path]] = None,
                 motor_type: Optional[Union[str, Iterable[str]]] = None,
                 confidence: Optional[Union[str, Iterable[str]]] = None,
                 exclude_synthetic: bool = True) -> List[Dict[str, Any]]:
    """Uretim agacindan ({hybrid,solid,liquid}/*.json) kayitlari yukle ve denetle.

    - Her kayit sema denetiminden gecer; gecemeyen kayit yuklemeyi DURDURUR
      (ValidationRecordError). Sessizce atlanan kayit yoktur.
    - Alt klasor adi kaydin motor_type alaniyla uyusmak zorundadir.
    - test_id tum agacta benzersiz olmalidir.
    - exclude_synthetic=True (VARSAYILAN) iken sentetik kayit bulunursa HATA
      firlatilir: sentetik kayitlarin uretim agacinda yeri yoktur (fikstur
      dosyasi icin load_records_from_file kullanilir). Bu, sentetik verinin
      korelasyon istatistigine sizmasina karsi yapisal bekcidir.
    - motor_type / confidence filtreleri tek deger veya kume kabul eder.
    """
    base = Path(base_dir) if base_dir is not None else DEFAULT_RECORDS_DIR
    if not base.is_dir():
        raise FileNotFoundError(
            f"Dogrulama kayit dizini bulunamadi: {base} "
            f"(beklenen yerlesim: hrma/data/validation_records/)"
        )

    motor_filter = _normalize_filter(motor_type, MOTOR_TYPES, "motor_type")
    conf_filter = _normalize_filter(confidence, CONFIDENCE_LEVELS, "confidence")

    records: List[Dict[str, Any]] = []
    seen_ids: Dict[str, str] = {}

    for subdir_name in MOTOR_TYPES:
        subdir = base / subdir_name
        if not subdir.is_dir():
            continue
        for path in sorted(subdir.glob("*.json")):
            record = _read_json(path)
            ensure_valid_record(record, path=path)

            if record["motor_type"] != subdir_name:
                raise ValidationRecordError(
                    [f"klasor/motor_type uyusmazligi: kayit '{record['motor_type']}' "
                     f"diyor ama '{subdir_name}/' klasorunde duruyor"],
                    path=path,
                )

            test_id = record["test_id"]
            if test_id in seen_ids:
                raise ValidationRecordError(
                    [f"test_id '{test_id}' benzersiz degil "
                     f"(ilk gorulen: {seen_ids[test_id]})"],
                    path=path,
                )
            seen_ids[test_id] = str(path)

            if exclude_synthetic and is_synthetic(record):
                raise ValidationRecordError(
                    ["sentetik kayit uretim agacinda YASAK: synthetic: true "
                     "kayitlar yalnizca tests/fixtures/ altinda yasayabilir "
                     "(korelasyon istatistigi kirlenme bekcisi)"],
                    path=path,
                )

            if motor_filter is not None and record["motor_type"] not in motor_filter:
                continue
            if conf_filter is not None and record["source"]["confidence"] not in conf_filter:
                continue
            records.append(record)

    return records


def load_records_from_file(path: Union[str, Path],
                           exclude_synthetic: bool = True) -> List[Dict[str, Any]]:
    """Tek JSON dosyasindan (kayit listesi veya tek kayit) yukle ve denetle.

    Test fiksturleri (tests/fixtures/synthetic_experiments.json) icin giris
    noktasi. Varsayilan exclude_synthetic=True sentetik kayitlari FILTRELER
    (dosya tabanli yol uretim yolu degildir; sert hata yerine bos sonuc doner).
    Boru hatti testleri sentetik fiksturleri exclude_synthetic=False ile alir.
    """
    p = Path(path)
    data = _read_json(p)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValidationRecordError(
            ["dosya bir kayit objesi veya kayit listesi icermeli"], path=p
        )

    records: List[Dict[str, Any]] = []
    seen_ids: Dict[str, int] = {}
    for i, record in enumerate(data):
        ensure_valid_record(record, path=f"{p}[{i}]")
        test_id = record["test_id"]
        if test_id in seen_ids:
            raise ValidationRecordError(
                [f"test_id '{test_id}' benzersiz degil "
                 f"(ayni dosyada indeks {seen_ids[test_id]} ve {i})"],
                path=p,
            )
        seen_ids[test_id] = i
        if exclude_synthetic and is_synthetic(record):
            continue
        records.append(record)
    return records


def filter_records(records: Iterable[Dict[str, Any]],
                   motor_type: Optional[Union[str, Iterable[str]]] = None,
                   confidence: Optional[Union[str, Iterable[str]]] = None,
                   exclude_synthetic: bool = True) -> List[Dict[str, Any]]:
    """Bellekteki kayit listesini filtrele (yukleme sonrasi ikincil suzgec)."""
    motor_filter = _normalize_filter(motor_type, MOTOR_TYPES, "motor_type")
    conf_filter = _normalize_filter(confidence, CONFIDENCE_LEVELS, "confidence")
    out = []
    for record in records:
        if exclude_synthetic and is_synthetic(record):
            continue
        if motor_filter is not None and record.get("motor_type") not in motor_filter:
            continue
        if conf_filter is not None:
            conf = record.get("source", {}).get("confidence")
            if conf not in conf_filter:
                continue
        out.append(record)
    return out


def records_for_statistics(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Istatistige girebilecek kayitlar: sentetikler KOSULSUZ dislanir.

    Bu fonksiyonun sentetik kayitlari dahil edecek bir parametresi BILEREK
    yoktur (yapisal bekci). Korelasyon koducusu (G2) istatistik girisini
    buradan almalidir.
    """
    return [r for r in records if not is_synthetic(r)]


def summarize(records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Kayit kumesinin istatistik ozeti (sentetikler yapisal olarak haric).

    Sentetik kayitlar ozete giremez; kac tanesinin dislandigi
    ``n_synthetic_excluded`` alaninda gorunur kalir. Dahil etme parametresi
    bilerek yoktur.
    """
    records = list(records)
    stat_records = records_for_statistics(records)

    by_motor: Dict[str, int] = {}
    by_confidence: Dict[str, int] = {}
    by_record_type: Dict[str, int] = {}
    propellant_pairs: Dict[str, int] = {}
    measured_quantities: Dict[str, int] = {}
    n_digitized = 0
    n_with_uncertainty = 0
    n_anomalies = 0
    test_ids: List[str] = []

    for record in stat_records:
        test_ids.append(record["test_id"])
        by_motor[record["motor_type"]] = by_motor.get(record["motor_type"], 0) + 1
        conf = record["source"]["confidence"]
        by_confidence[conf] = by_confidence.get(conf, 0) + 1
        rtype = record.get("record_type", "static_fire")
        by_record_type[rtype] = by_record_type.get(rtype, 0) + 1

        prop = record.get("propellants", {})
        pair = f"{prop.get('oxidizer', '?')}/{prop.get('fuel', '?')}"
        propellant_pairs[pair] = propellant_pairs.get(pair, 0) + 1

        for key, value in record.get("measured", {}).items():
            if value is not None:
                measured_quantities[key] = measured_quantities.get(key, 0) + 1

        if record.get("digitized", False):
            n_digitized += 1
        if record.get("measurement_uncertainty"):
            n_with_uncertainty += 1
        if record.get("anomaly", {}).get("flag", False):
            n_anomalies += 1

    return {
        "n_records": len(stat_records),
        "n_synthetic_excluded": len(records) - len(stat_records),
        "by_motor_type": by_motor,
        "by_confidence": by_confidence,
        "by_record_type": by_record_type,
        "propellant_pairs": propellant_pairs,
        "measured_quantities": measured_quantities,
        "n_digitized": n_digitized,
        "n_with_uncertainty": n_with_uncertainty,
        "n_anomalies": n_anomalies,
        "test_ids": sorted(test_ids),
    }
