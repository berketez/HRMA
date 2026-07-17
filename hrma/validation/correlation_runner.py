"""Otomatik korelasyon kosucusu (v2.5.0 G2) — gercek-deney DB'si vs HRMA.

Spec: docs/arge-guven-2026-07/arge_korelasyon_tasarim.md Bolum 3.

Akis:
1. Kayitlar ``experiment_db.load_records`` ile alinir (uretim agacinda
   sentetik kayit yapisal olarak yasak) ya da parametreyle verilir; her iki
   yolda da ``records_for_statistics`` sentetikleri KOSULSUZ dislar.
2. Her kayit ``record_adapters.adapt_record`` ile kosulur. Kayit basina
   try/except + sure olcumu vardir; patlayan kayit 'runner_error' etiketiyle
   listede kalir (sessiz dusme yok).
3. Skorlama: yalniz ``measured`` anahtarlari skorlanabilir. Bir buyukluk
   ayni zamanda inputs'ta gorunuyorsa 'skipped_circular_input' (dongusellik
   bekcisi — semadaki yapisal bekcinin kosucu tarafindaki esi); adaptorun
   motor girdisi olarak tukettigi olcumler 'skipped_consumed'; tuketilen
   girdilerin aritmetik turevleri 'skipped_derived'. error_pct isaretlidir:
   (tahmin - olcum) / olcum * 100 (bias gorunur kalsin).
4. Toplulastirma (motor_type x buyukluk) hucresi basina: n, bias (ortalama
   isaretli hata %), RMS %, medyan APE %, MAPE %, min/maks (test_id ile).
   Aykiri isaretleme: |hata - medyan| > 3*MAD -> ISARETLENIR, ATILMAZ
   (rapor hem 'tumu' hem 'aykirisiz' istatistigi verir). anomaly.flag=true
   kayitlar ana istatistige GIRMEZ, ayri listede raporlanir. Guven katmani:
   ana istatistik high+medium; low ayri hucre listesinde (Berke onayli K2).
5. Determinizm: kosucu saf fonksiyondur — ayni DB ayni sonuc. DB icerik
   hash'i (sha256) sonuca yazilir (spec 3.4 cache mantiginin temeli).
   Zaman olcumleri ('elapsed_s', 'timing') dogal olarak deterministik
   DEGILDIR; ``deterministic_view`` bunlari soyarak karsilastirilabilir
   gorunum verir.

Cikti: JSON-hazir dict + ``to_markdown`` ozet tablosu (Ingilizce, emoji yok).
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics as _stats
import time
from typing import Any, Dict, Iterable, List, Optional

from hrma.validation import record_adapters
from hrma.validation.experiment_db import load_records, records_for_statistics

__all__ = [
    "RUNNER_VERSION",
    "MAIN_CONFIDENCE_LEVELS",
    "OUTLIER_MAD_FACTOR",
    "db_content_hash",
    "run_correlation",
    "deterministic_view",
    "to_markdown",
]

RUNNER_VERSION = "1"
# Ana istatistik katmani (Berke onayli K2): low ayri raporlanir.
MAIN_CONFIDENCE_LEVELS = ("high", "medium")
OUTLIER_MAD_FACTOR = 3.0
# Kayit basina sure uyari esigi (s). Kosucu tek is parcaciklidir; kosuyu
# KESMEZ (yarim motor hesabi guvenle iptal edilemez), sonuca uyari yazar.
PER_RECORD_TIME_WARN_S = 120.0


def db_content_hash(records: Iterable[Dict[str, Any]]) -> str:
    """Kayit kumesinin icerik hash'i (sha256, test_id sirali kanonik JSON).

    Ayni kayit icerigi ayni hash'i verir; kayit eklenmesi/degismesi hash'i
    degistirir. Bekci mesajlarinin 'DB mi degisti fizik mi' ayrimi bu hash'e
    dayanir (spec 5.2).
    """
    canonical = sorted(records, key=lambda r: r.get("test_id", ""))
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- Skorlama ----------------------------------------------------------------

def _score_adapter_result(adapter_result: Dict[str, Any]) -> Dict[str, Any]:
    """Adaptor sonucundan buyukluk-basina skor sozlugu uretir.

    Her measured taban adi icin bir giris doner:
      status: 'scored' | 'skipped_circular_input' | 'skipped_consumed' |
              'skipped_derived' | 'no_prediction' | 'measured_zero' |
              'measured_null' | 'curve_skipped_v1' | 'unknown_unit'
    'scored' girislerde predicted/measured (SI) ve isaretli error_pct bulunur.
    """
    scores: Dict[str, Any] = {}
    input_bases = set(adapter_result.get("input_bases", []))
    consumed = set(adapter_result.get("consumed_measured", []))
    derived = set(adapter_result.get("derived_bases", []))
    predictions = adapter_result.get("predictions", {})

    for base, measured in adapter_result.get("measured_si", {}).items():
        if base in input_bases:
            scores[base] = {"status": "skipped_circular_input"}
        elif base in consumed:
            scores[base] = {"status": "skipped_consumed"}
        elif base in derived:
            scores[base] = {"status": "skipped_derived"}
        elif base not in predictions:
            scores[base] = {"status": "no_prediction"}
        elif measured == 0:
            scores[base] = {"status": "measured_zero"}
        else:
            predicted = float(predictions[base])
            error_pct = (predicted - measured) / measured * 100.0
            scores[base] = {
                "status": "scored",
                "predicted_si": predicted,
                "measured_si": float(measured),
                "error_pct": float(error_pct),
            }
    for base in adapter_result.get("measured_null", []):
        scores.setdefault(base, {"status": "measured_null"})
    for base in adapter_result.get("measured_curves", []):
        scores.setdefault(base, {"status": "curve_skipped_v1"})
    for key in adapter_result.get("measured_unconverted", []):
        scores.setdefault(key, {"status": "unknown_unit"})
    return dict(sorted(scores.items()))


# --- Hucre istatistigi -------------------------------------------------------

def _basic_stats(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    errors = [e["error_pct"] for e in entries]
    apes = [abs(e) for e in errors]
    mn = min(entries, key=lambda e: e["error_pct"])
    mx = max(entries, key=lambda e: e["error_pct"])
    return {
        "n": len(errors),
        "bias_pct": float(_stats.fmean(errors)),
        "rms_pct": float(math.sqrt(_stats.fmean(e * e for e in errors))),
        "median_ape_pct": float(_stats.median(apes)),
        "mape_pct": float(_stats.fmean(apes)),
        "min": {"error_pct": mn["error_pct"], "test_id": mn["test_id"]},
        "max": {"error_pct": mx["error_pct"], "test_id": mx["test_id"]},
    }


def _mad_outliers(entries: List[Dict[str, Any]]) -> List[str]:
    """|hata - medyan| > 3*MAD olan test_id'ler (MAD=0 ise aykiri yok)."""
    if len(entries) < 3:
        return []
    errors = [e["error_pct"] for e in entries]
    med = _stats.median(errors)
    mad = _stats.median([abs(e - med) for e in errors])
    if mad <= 0:
        return []
    return sorted(e["test_id"] for e in entries
                  if abs(e["error_pct"] - med) > OUTLIER_MAD_FACTOR * mad)


def _cell(motor_type: str, quantity: str,
          entries: List[Dict[str, Any]], band: str) -> Dict[str, Any]:
    entries = sorted(entries, key=lambda e: e["test_id"])
    cell = {
        "motor_type": motor_type,
        "quantity": quantity,
        "confidence_band": band,
        **_basic_stats(entries),
        "entries": [
            {"test_id": e["test_id"], "error_pct": e["error_pct"],
             "confidence": e["confidence"]}
            for e in entries
        ],
    }
    outlier_ids = _mad_outliers(entries)
    cell["outlier_test_ids"] = outlier_ids
    if outlier_ids:
        kept = [e for e in entries if e["test_id"] not in outlier_ids]
        # Aykirilar ana istatistikten ATILMAZ; 'aykirisiz' satiri EK bilgidir.
        cell["stats_excl_outliers"] = _basic_stats(kept) if kept else None
    else:
        cell["stats_excl_outliers"] = None
    return cell


def _aggregate(record_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    main: Dict[Any, List[Dict[str, Any]]] = {}
    low: Dict[Any, List[Dict[str, Any]]] = {}
    anomaly_entries: List[Dict[str, Any]] = []

    for rr in record_results:
        if rr["status"] != "ok":
            continue
        for quantity, score in rr["scores"].items():
            if score.get("status") != "scored":
                continue
            entry = {
                "test_id": rr["test_id"],
                "error_pct": score["error_pct"],
                "confidence": rr["confidence"],
            }
            key = (rr["motor_type"], quantity)
            if rr["anomaly"]:
                anomaly_entries.append({
                    "test_id": rr["test_id"],
                    "motor_type": rr["motor_type"],
                    "quantity": quantity,
                    "error_pct": score["error_pct"],
                    "confidence": rr["confidence"],
                    "anomaly_note": rr.get("anomaly_note"),
                })
            elif rr["confidence"] in MAIN_CONFIDENCE_LEVELS:
                main.setdefault(key, []).append(entry)
            else:
                low.setdefault(key, []).append(entry)

    cells = [_cell(mt, q, entries, "high_medium")
             for (mt, q), entries in sorted(main.items())]
    low_cells = [_cell(mt, q, entries, "low")
                 for (mt, q), entries in sorted(low.items())]
    anomaly_entries.sort(key=lambda e: (e["test_id"], e["quantity"]))
    return {
        "cells": cells,
        "low_confidence_cells": low_cells,
        "anomaly_entries": anomaly_entries,
    }


# --- Kosucu ------------------------------------------------------------------

def run_correlation(records: Optional[Iterable[Dict[str, Any]]] = None,
                    base_dir: Optional[str] = None,
                    adapter=None) -> Dict[str, Any]:
    """Korelasyon kosusunu yapar; JSON-hazir sonuc sozlugu dondurur.

    Args:
        records: Onceden yuklenmis kayit listesi. None ise uretim agaci
            ``load_records(base_dir)`` ile yuklenir (sema denetimli; sentetik
            kayit uretim agacinda zaten hata). Dogrudan verilen listelerde de
            sentetikler ``records_for_statistics`` ile kosulsuz dislanir.
        base_dir: load_records icin kok dizin (records verilmisse kullanilmaz).
        adapter: kayit -> adaptor sonucu cagrilabiliri (test enjeksiyonu
            icin; varsayilan record_adapters.adapt_record).

    Returns:
        {'runner_version', 'adapter_version', 'db_content_hash', 'n_records',
         'n_synthetic_excluded', 'records', 'statistics', 'status_counts',
         'not_supported', 'insufficient_inputs', 'runner_errors', 'timing'}
        'timing' ve kayit-basina 'elapsed_s' deterministik degildir;
        karsilastirma icin deterministic_view kullanilir.
    """
    if adapter is None:
        adapter = record_adapters.adapt_record
    if records is None:
        records = load_records(base_dir=base_dir)
    all_records = list(records)
    stat_records = records_for_statistics(all_records)  # sentetik yapisal disi
    stat_records = sorted(stat_records, key=lambda r: r.get("test_id", ""))

    t_total0 = time.perf_counter()
    record_results: List[Dict[str, Any]] = []
    for rec in stat_records:
        t0 = time.perf_counter()
        try:
            adapter_result = adapter(rec)
            status = adapter_result.get("status", "runner_error")
            reason = adapter_result.get("reason")
        except Exception as exc:  # patlayan kayit listede kalir (etiketli)
            adapter_result = {}
            status = "runner_error"
            reason = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - t0

        rr = {
            "test_id": rec.get("test_id"),
            "motor_type": rec.get("motor_type"),
            "record_type": rec.get("record_type", "static_fire"),
            "confidence": rec.get("source", {}).get("confidence"),
            "anomaly": bool(rec.get("anomaly", {}).get("flag", False)),
            "anomaly_note": rec.get("anomaly", {}).get("note"),
            "status": status,
            "reason": reason,
            "missing": adapter_result.get("missing", []),
            "consumed_measured": adapter_result.get("consumed_measured", []),
            "derived_bases": adapter_result.get("derived_bases", []),
            "assumed_defaults": adapter_result.get("assumed_defaults", {}),
            "adapter_notes": adapter_result.get("adapter_notes", []),
            "convergence": adapter_result.get("convergence"),
            "scores": (_score_adapter_result(adapter_result)
                       if status == "ok" else {}),
            "elapsed_s": round(elapsed, 3),
        }
        if elapsed > PER_RECORD_TIME_WARN_S:
            rr["time_warning"] = (
                f"record run took {elapsed:.1f} s "
                f"(threshold {PER_RECORD_TIME_WARN_S:.0f} s)")
        record_results.append(rr)

    status_counts: Dict[str, int] = {}
    for rr in record_results:
        status_counts[rr["status"]] = status_counts.get(rr["status"], 0) + 1

    result = {
        "runner_version": RUNNER_VERSION,
        "adapter_version": record_adapters.ADAPTER_VERSION,
        "db_content_hash": db_content_hash(stat_records),
        "n_records": len(stat_records),
        "n_synthetic_excluded": len(all_records) - len(stat_records),
        "records": record_results,
        "statistics": _aggregate(record_results),
        "status_counts": dict(sorted(status_counts.items())),
        "not_supported": [
            {"test_id": rr["test_id"], "reason": rr["reason"]}
            for rr in record_results if rr["status"] == "not_supported"
        ],
        "insufficient_inputs": [
            {"test_id": rr["test_id"], "missing": rr["missing"]}
            for rr in record_results if rr["status"] == "insufficient_inputs"
        ],
        "runner_errors": [
            {"test_id": rr["test_id"], "reason": rr["reason"]}
            for rr in record_results if rr["status"] == "runner_error"
        ],
        "timing": {"total_s": round(time.perf_counter() - t_total0, 3)},
    }
    return result


def deterministic_view(result: Dict[str, Any]) -> Dict[str, Any]:
    """Zaman olcumlerinden arindirilmis derin kopya (determinizm kiyasi icin).

    Ayni DB + ayni kod ile iki kosunun deterministic_view'lari birebir esittir
    (spec 3.4); cache karsilastirmasi ve testler bu gorunumu kullanmalidir.
    """
    view = json.loads(json.dumps(result))
    view.pop("timing", None)
    for rr in view.get("records", []):
        rr.pop("elapsed_s", None)
        rr.pop("time_warning", None)
    return view


# --- Markdown ozeti ----------------------------------------------------------

def _fmt_pct(value: float) -> str:
    return f"{value:+.1f}"


def _cell_rows(cells: List[Dict[str, Any]]) -> List[str]:
    rows = []
    for cell in cells:
        outliers = ", ".join(cell["outlier_test_ids"]) or "-"
        rows.append(
            f"| {cell['motor_type']} | {cell['quantity']} | {cell['n']} "
            f"| {_fmt_pct(cell['bias_pct'])} "
            f"| {cell['median_ape_pct']:.1f} "
            f"| {cell['rms_pct']:.1f} "
            f"| {_fmt_pct(cell['min']['error_pct'])} ({cell['min']['test_id']}) "
            f"| {_fmt_pct(cell['max']['error_pct'])} ({cell['max']['test_id']}) "
            f"| {outliers} |")
        if cell["stats_excl_outliers"]:
            ex = cell["stats_excl_outliers"]
            rows.append(
                f"| {cell['motor_type']} | {cell['quantity']} (excl. outliers) "
                f"| {ex['n']} | {_fmt_pct(ex['bias_pct'])} "
                f"| {ex['median_ape_pct']:.1f} | {ex['rms_pct']:.1f} "
                f"| {_fmt_pct(ex['min']['error_pct'])} ({ex['min']['test_id']}) "
                f"| {_fmt_pct(ex['max']['error_pct'])} ({ex['max']['test_id']}) "
                f"| flagged, not dropped |")
    return rows


_TABLE_HEADER = (
    "| Motor | Quantity | N | Bias % | Median APE % | RMS % "
    "| Min % (test) | Max % (test) | Outliers |\n"
    "|---|---|---|---|---|---|---|---|---|")


def to_markdown(result: Dict[str, Any]) -> str:
    """Kosu sonucundan Ingilizce Markdown ozeti uretir (emoji yok)."""
    lines = [
        "# HRMA correlation summary (real-experiment database)",
        "",
        f"- Runner version: {result['runner_version']} "
        f"(adapter {result['adapter_version']})",
        f"- Records in statistics pipeline: {result['n_records']} "
        f"(synthetic excluded: {result['n_synthetic_excluded']})",
        f"- DB content hash: `{result['db_content_hash']}`",
        f"- Status counts: "
        + ", ".join(f"{k}={v}" for k, v in result["status_counts"].items()),
        "",
        "Signed error convention: (predicted - measured) / measured * 100. "
        "Outliers (|error - median| > 3*MAD) are flagged, never dropped.",
        "",
        "## Main statistics (confidence: high + medium)",
        "",
        _TABLE_HEADER,
    ]
    lines += _cell_rows(result["statistics"]["cells"]) or ["| - | no scored quantities | | | | | | | |"]

    low = result["statistics"]["low_confidence_cells"]
    if low:
        lines += ["", "## Low-confidence records (reported separately)", "",
                  _TABLE_HEADER]
        lines += _cell_rows(low)

    anomalies = result["statistics"]["anomaly_entries"]
    if anomalies:
        lines += ["", "## Anomaly-flagged records (excluded from statistics)",
                  "", "| Test | Quantity | Error % | Note |", "|---|---|---|---|"]
        for entry in anomalies:
            lines.append(
                f"| {entry['test_id']} | {entry['quantity']} "
                f"| {_fmt_pct(entry['error_pct'])} "
                f"| {entry.get('anomaly_note') or '-'} |")

    for title, key, field in (
            ("Not supported (v1)", "not_supported", "reason"),
            ("Insufficient inputs", "insufficient_inputs", "missing"),
            ("Runner errors", "runner_errors", "reason")):
        items = result[key]
        if items:
            lines += ["", f"## {title}", ""]
            for item in items:
                lines.append(f"- `{item['test_id']}`: {item[field]}")

    return "\n".join(lines) + "\n"
