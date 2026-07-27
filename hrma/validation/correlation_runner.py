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
   Ek durustluk alanlari (2026-07-27 fizik denetimi):
   - n_campaigns (F006): kayitlar bagimsiz gozlem DEGILDIR — ayni kampanyanin
     ardisik atislari sistematik (tesis/enjektor/olcum zinciri) hatayi
     paylasir; hucre 'kayit / bagimsiz kampanya' ikilisini ve kampanya
     duzeyinde ozet istatistigi (campaign_stats) tasir.
   - n_in_sample / n_weak_evidence (F007): adaptorun 'IN-SAMPLE' ve 'ZAYIF
     KANIT' bayraklari (quantity_flags) artik hucreye ve markdown ozetine
     tasinir; fitin kendi verisine karsi olculen skorlar niteliksiz sayi
     olarak yayilamaz.
   - measurement_u_pct / median_measurement_u_pct (F008 eki): kayitlarin
     bildirdigi olcum belirsizligi skora ve hucreye tasinir; coverage_k
     biliniyorsa normalize hata E_n = error_pct/(k*u_pct) verilir, k
     bilinmiyorsa verilmez (uydurulmaz; ISO/IEC Guide 98-3 / ASME V&V
     20-2009 Bol. 2).
   Aykiri isaretleme (F035): modifiye z-skoru
   |0.6745*(hata - medyan)/MAD| > 3.5 -> ISARETLENIR, ATILMAZ
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
import warnings as _warnings
from typing import Any, Dict, Iterable, List, Optional

from hrma.validation import record_adapters
from hrma.validation.experiment_db import load_records, records_for_statistics

__all__ = [
    "RUNNER_VERSION",
    "MAIN_CONFIDENCE_LEVELS",
    "OUTLIER_MAD_SCALE",
    "OUTLIER_MODIFIED_Z",
    "db_content_hash",
    "run_correlation",
    "deterministic_view",
    "to_markdown",
]

RUNNER_VERSION = "1"
# Ana istatistik katmani (Berke onayli K2): low ayri raporlanir.
MAIN_CONFIDENCE_LEVELS = ("high", "medium")
# F035 (2026-07-27): eski esik |hata - medyan| > 3*ham MAD idi
# (OUTLIER_MAD_FACTOR = 3.0, kaynaksiz). Ham MAD normal dagilimda sigma'nin
# 0.6745 katidir (sigma ~ 1.4826*MAD; Rousseeuw & Croux, JASA 88(424), 1993),
# yani 3*ham MAD yalnizca ~2.02 sigma'ya karsilik geliyordu ve temiz normal
# veride n=27'de orneklerin ~%6.2'sini aykiri isaretliyordu (beklenen %0.27'nin
# ~23 kati; katalog Monte Carlo olcumu). Yeni esik modifiye z-skorudur:
# |0.6745*(hata - medyan)/MAD| > 3.5 (Iglewicz & Hoaglin, 'How to Detect and
# Handle Outliers', ASQC Basic References in Quality Control Vol. 16, 1993).
OUTLIER_MAD_SCALE = 0.6745
OUTLIER_MODIFIED_Z = 3.5
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

def _measurement_uncertainty_map(record: Dict[str, Any]) -> Dict[str, Any]:
    """Kayittaki ``measurement_uncertainty`` blogunu kanonik taban ada indirger.

    F008 eki (2026-07-27, dogrulama denetimi): kosucu bu blogu HIC okumuyordu
    — medAPE gibi sayilarin yaninda deneysel hata cubugu yoktu ve model
    hatasi ile olcum sacilimi ayrismiyordu. Sema: SCHEMA.md
    'measurement_uncertainty blogu' (value/type/coverage_k/source);
    metrik ilkesi: ASME V&V 20-2009 Bol. 2 (karsilastirma hatasi E = S - D
    ve u_val) ve ISO/IEC Guide 98-3 (GUM). coverage_k null olan kayitlarda k
    bilinmedigi icin normalize hata HESAPLANMAZ (uydurma k yasak); yalniz
    goreli belirsizlik raporlanir.

    Returns:
        {taban_ad: {'type', 'coverage_k', 'u_rel_pct', 'u_si'}} — 'relative'
        tipte u_rel_pct dolu (yuzde); 'absolute' tipte u_si dolu (SI,
        birim-ekli anahtar to_si ile cevrilir; cevrilemeyen None kalir).
    """
    block = record.get("measurement_uncertainty") or {}
    out: Dict[str, Any] = {}
    for key, spec in block.items():
        if not isinstance(spec, dict) or spec.get("value") is None:
            continue
        base, _ = record_adapters.split_quantity_key(key)
        base = record_adapters.BASE_ALIASES.get(base, base)
        entry = {
            "type": spec.get("type"),
            "coverage_k": spec.get("coverage_k"),
            "u_rel_pct": None,
            "u_si": None,
        }
        if spec.get("type") == "relative":
            entry["u_rel_pct"] = float(spec["value"]) * 100.0
        elif spec.get("type") == "absolute":
            # Birim carpani dogrusal oldugu icin belirsizlik ayni carpani alir.
            _, si = record_adapters.to_si(key, spec["value"])
            entry["u_si"] = si
        out[base] = entry
    return out


def _score_adapter_result(adapter_result: Dict[str, Any],
                          measurement_u: Optional[Dict[str, Any]] = None
                          ) -> Dict[str, Any]:
    """Adaptor sonucundan buyukluk-basina skor sozlugu uretir.

    Her measured taban adi icin bir giris doner:
      status: 'scored' | 'skipped_circular_input' | 'skipped_consumed' |
              'skipped_derived' | 'no_prediction' | 'measured_zero' |
              'measured_null' | 'curve_skipped_v1' | 'unknown_unit'
    'scored' girislerde predicted/measured (SI) ve isaretli error_pct bulunur.
    Kayit olcum belirsizligi bildiriyorsa (F008 eki) 'measurement_u_pct' ve
    'coverage_k' eklenir; k biliniyorsa normalize hata E_n = error_pct /
    (k * u_pct) da verilir (ASME V&V 20-2009: |E_n| <= 1 model-olcum uyumu).
    """
    scores: Dict[str, Any] = {}
    input_bases = set(adapter_result.get("input_bases", []))
    consumed = set(adapter_result.get("consumed_measured", []))
    derived = set(adapter_result.get("derived_bases", []))
    predictions = adapter_result.get("predictions", {})
    # F007: adaptorun makine-okunur bagimlilik bayraklari skora tasinir.
    quantity_flags = adapter_result.get("quantity_flags", {})

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
            flags = sorted(quantity_flags.get(base, []))
            if flags:
                scores[base]["flags"] = flags
            mu = (measurement_u or {}).get(base)
            if mu is not None:
                u_pct = mu["u_rel_pct"]
                if u_pct is None and mu["u_si"] is not None:
                    u_pct = abs(mu["u_si"]) / abs(float(measured)) * 100.0
                if u_pct is not None:
                    scores[base]["measurement_u_pct"] = float(u_pct)
                    k = mu.get("coverage_k")
                    scores[base]["coverage_k"] = k
                    if isinstance(k, (int, float)) and k > 0 and u_pct > 0:
                        scores[base]["normalized_error"] = float(
                            error_pct / (k * u_pct))
    for base in adapter_result.get("measured_null", []):
        scores.setdefault(base, {"status": "measured_null"})
    for base in adapter_result.get("measured_curves", []):
        scores.setdefault(base, {"status": "curve_skipped_v1"})
    for key in adapter_result.get("measured_unconverted", []):
        scores.setdefault(key, {"status": "unknown_unit"})
    return dict(sorted(scores.items()))


# --- Hucre istatistigi -------------------------------------------------------

def _campaign_key(record: Dict[str, Any]) -> str:
    """Kaydin bagimsiz-kampanya anahtari (F006).

    Ayni yayina/kampanyaya ait kayitlar ayni kaynak kunyesini (source.citation)
    tasir; kunye yoksa kayit tek basina kampanya sayilir (test_id). Kampanya =
    'sistematik hatayi paylasan olcum kumesi' yaklasimi: ASME V&V 20-2009
    Bol. 3 (tekrarli olcumlerde sistematik vs rastgele bilesen ayrimi).
    """
    citation = (record.get("source") or {}).get("citation")
    if citation and str(citation).strip():
        return str(citation).strip()
    return str(record.get("test_id") or "?")


def _basic_stats(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    errors = [e["error_pct"] for e in entries]
    apes = [abs(e) for e in errors]
    mn = min(entries, key=lambda e: e["error_pct"])
    mx = max(entries, key=lambda e: e["error_pct"])
    # F006: 'n' bagimsiz gozlem sayisi DEGILDIR — ayni kampanyanin atislari
    # sistematik hatayi paylasir (pseudoreplication; Hurlbert, Ecological
    # Monographs 54(2), 1984). Etkin serbestlik derecesi kampanya sayisina
    # yakindir; ikisi de raporlanir. Olculen fark (tam DB): hybrid c_star/isp
    # n=18 -> 1 kampanya, hybrid Pc/regresyon n=35 -> 2, solid burn_rate
    # n=27 -> 2; yalniz sivi hucreleri gercekten bagimsizdir (14 ayri motor).
    campaigns = {e.get("campaign") or e["test_id"] for e in entries}
    # F008 eki: kayitlarin bildirdigi olcum belirsizligi hucre duzeyinde
    # ozetlenir — medAPE'nin olcum gurultusunden ayrissip ayrismadigi ancak
    # boyle okunabilir (or. hybrid c_star medAPE %2.3 vs u_olcum ~%0.8:
    # model hatasi olcum sacilmasinin ~3 kati, ayrisabilir durumda).
    u_vals = [e["measurement_u_pct"] for e in entries
              if e.get("measurement_u_pct") is not None]
    en_vals = [abs(e["normalized_error"]) for e in entries
               if e.get("normalized_error") is not None]
    return {
        "n": len(errors),
        "n_campaigns": len(campaigns),
        # F007: bagimlilik bayragi tasiyan girislerin sayimi hucrede gorunur.
        "n_in_sample": sum(1 for e in entries
                           if "in_sample" in (e.get("flags") or ())),
        "n_weak_evidence": sum(1 for e in entries
                               if "weak_evidence" in (e.get("flags") or ())),
        "n_with_measurement_u": len(u_vals),
        "median_measurement_u_pct": (float(_stats.median(u_vals))
                                     if u_vals else None),
        # coverage_k bildirilmis kayit yoksa None — k uydurulmaz (GUM).
        "median_abs_normalized_error": (float(_stats.median(en_vals))
                                        if en_vals else None),
        "bias_pct": float(_stats.fmean(errors)),
        "rms_pct": float(math.sqrt(_stats.fmean(e * e for e in errors))),
        "median_ape_pct": float(_stats.median(apes)),
        "mape_pct": float(_stats.fmean(apes)),
        "min": {"error_pct": mn["error_pct"], "test_id": mn["test_id"]},
        "max": {"error_pct": mx["error_pct"], "test_id": mx["test_id"]},
    }


def _campaign_stats(entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Kampanya duzeyinde ozet (F006): kampanya-ici ortalama -> ustu istatistik.

    Kumelenmis veride durust ozet, once kampanya icinde ortalama alip sonra
    kampanyalar arasinda istatistik vermektir (Hurlbert 1984; ASME V&V
    20-2009 Bol. 3). Tek kampanyali hucrede None doner — 'kampanyalar arasi
    sacilim' diye bir sey yoktur ve uydurulmaz.
    """
    groups: Dict[str, List[float]] = {}
    for e in entries:
        groups.setdefault(e.get("campaign") or e["test_id"], []).append(
            e["error_pct"])
    if len(groups) < 2:
        return None
    means = sorted(float(_stats.fmean(v)) for v in groups.values())
    return {
        "n_campaigns": len(groups),
        "bias_pct": float(_stats.fmean(means)),
        "median_ape_pct": float(_stats.median(abs(m) for m in means)),
        "note": ("Campaign-level view: per-campaign mean signed errors, "
                 "then statistics across campaigns (clustered data)."),
    }


def _mad_outliers(entries: List[Dict[str, Any]]) -> List[str]:
    """Modifiye z-skoru |0.6745*(hata - medyan)/MAD| > 3.5 olan test_id'ler.

    F035 (2026-07-27): eski esik 3*ham MAD yalnizca ~2.02 sigma idi
    (gerekce OUTLIER_MAD_SCALE sabitinin yorumunda). OLCULEN etki (tam DB
    kosusu, once -> sonra): hybrid c_star 1 -> 0, hybrid isp 2 -> 0,
    liquid isp_vac 1 -> 0 (vulcain21 modifiye z ~2.9, esik altinda),
    liquid thrust_vac 1 -> 1 (rd0120 gercekten uc), solid burn_rate
    5 -> 3 (kndx-p05, knsb-p09/p10 kaldi). 'excl. outliers' satirindaki
    yapay iyilesme azaldi ama tamamen kaybolmadi: solid RMS 'aykirisiz'
    satiri %1.99 -> %0.71 yerine artik %1.99 -> %0.88. MAD=0 ise aykiri
    yok. NOT: n >= 3 alt siniri mevcut test sozlesmesiyle korundu; n < 6'da
    MAD kaba bir tahmindir ve isaret yalniz sunumsaldir (aykirilar hicbir
    zaman atilmaz).
    """
    if len(entries) < 3:
        return []
    errors = [e["error_pct"] for e in entries]
    med = _stats.median(errors)
    mad = _stats.median([abs(e - med) for e in errors])
    if mad <= 0:
        return []
    return sorted(
        e["test_id"] for e in entries
        if abs(OUTLIER_MAD_SCALE * (e["error_pct"] - med) / mad)
        > OUTLIER_MODIFIED_Z)


def _cell(motor_type: str, quantity: str,
          entries: List[Dict[str, Any]], band: str) -> Dict[str, Any]:
    entries = sorted(entries, key=lambda e: e["test_id"])
    out_entries = []
    for e in entries:
        item = {"test_id": e["test_id"], "error_pct": e["error_pct"],
                "confidence": e["confidence"]}
        if e.get("flags"):
            item["flags"] = list(e["flags"])  # F007: giris duzeyinde gorunur
        if e.get("measurement_u_pct") is not None:  # F008 eki
            item["measurement_u_pct"] = e["measurement_u_pct"]
        if e.get("normalized_error") is not None:
            item["normalized_error"] = e["normalized_error"]
        out_entries.append(item)
    cell = {
        "motor_type": motor_type,
        "quantity": quantity,
        "confidence_band": band,
        **_basic_stats(entries),
        # F006: kampanya duzeyinde ozet (tek kampanyada None — uydurulmaz)
        "campaign_stats": _campaign_stats(entries),
        "entries": out_entries,
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
                # F006: kampanya anahtari hucre-ici gruplamada kullanilir
                # (cikti entries listesine yazilmaz — kunye uzun).
                "campaign": rr.get("campaign"),
                # F007: adaptor bagimlilik bayraklari ('in_sample', ...)
                "flags": score.get("flags", []),
                # F008 eki: kayit belirsizlik bildiriyorsa hucreye tasinir.
                "measurement_u_pct": score.get("measurement_u_pct"),
                "normalized_error": score.get("normalized_error"),
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
        # Motor uyarilari (warnings.warn) kayit basina YAKALANIR ve sonuca
        # yazilir — 'gox' bugu aylarca yalniz stderr'e akan uyarilarla gizlendi
        # (2026-07-18 fizik incelemesi); uyari artik gorunur veri.
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            try:
                adapter_result = adapter(rec)
                status = adapter_result.get("status", "runner_error")
                reason = adapter_result.get("reason")
            except Exception as exc:  # patlayan kayit listede kalir (etiketli)
                adapter_result = {}
                status = "runner_error"
                reason = f"{type(exc).__name__}: {exc}"
        engine_warnings = sorted({str(w.message) for w in caught})
        elapsed = time.perf_counter() - t0

        rr = {
            "test_id": rec.get("test_id"),
            "motor_type": rec.get("motor_type"),
            "record_type": rec.get("record_type", "static_fire"),
            "confidence": rec.get("source", {}).get("confidence"),
            "campaign": _campaign_key(rec),  # F006
            "quantity_flags": adapter_result.get("quantity_flags", {}),
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
            "engine_warnings": engine_warnings,
            "scores": (_score_adapter_result(
                adapter_result,
                measurement_u=_measurement_uncertainty_map(rec))
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


def _dependence_label(stats: Dict[str, Any]) -> str:
    """F007/F008 hucre bagimlilik/belirsizlik etiketi (markdown Dependence)."""
    parts = []
    if stats.get("n_in_sample"):
        parts.append(f"{stats['n_in_sample']}/{stats['n']} in-sample")
    if stats.get("n_weak_evidence"):
        parts.append(f"{stats['n_weak_evidence']}/{stats['n']} weak-evidence")
    if stats.get("median_measurement_u_pct") is not None:
        parts.append(
            f"u_meas~{stats['median_measurement_u_pct']:.2f}% "
            f"(n={stats['n_with_measurement_u']})")
    return "; ".join(parts) or "-"


def _cell_rows(cells: List[Dict[str, Any]]) -> List[str]:
    rows = []
    for cell in cells:
        outliers = ", ".join(cell["outlier_test_ids"]) or "-"
        rows.append(
            f"| {cell['motor_type']} | {cell['quantity']} "
            f"| {cell['n']} ({cell['n_campaigns']}) "
            f"| {_fmt_pct(cell['bias_pct'])} "
            f"| {cell['median_ape_pct']:.1f} "
            f"| {cell['rms_pct']:.1f} "
            f"| {_fmt_pct(cell['min']['error_pct'])} ({cell['min']['test_id']}) "
            f"| {_fmt_pct(cell['max']['error_pct'])} ({cell['max']['test_id']}) "
            f"| {_dependence_label(cell)} "
            f"| {outliers} |")
        if cell["stats_excl_outliers"]:
            ex = cell["stats_excl_outliers"]
            rows.append(
                f"| {cell['motor_type']} | {cell['quantity']} (excl. outliers) "
                f"| {ex['n']} ({ex['n_campaigns']}) "
                f"| {_fmt_pct(ex['bias_pct'])} "
                f"| {ex['median_ape_pct']:.1f} | {ex['rms_pct']:.1f} "
                f"| {_fmt_pct(ex['min']['error_pct'])} ({ex['min']['test_id']}) "
                f"| {_fmt_pct(ex['max']['error_pct'])} ({ex['max']['test_id']}) "
                f"| {_dependence_label(ex)} "
                f"| flagged, not dropped |")
    return rows


_TABLE_HEADER = (
    "| Motor | Quantity | N (campaigns) | Bias % | Median APE % | RMS % "
    "| Min % (test) | Max % (test) | Dependence | Outliers |\n"
    "|---|---|---|---|---|---|---|---|---|---|")


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
        "Outliers use the modified z-score |0.6745*(error - median)/MAD| > "
        "3.5 (Iglewicz & Hoaglin, 1993); they are flagged, never dropped. "
        "N is 'records (independent campaigns)': records from the same "
        "campaign share systematic error, so the effective sample size is "
        "closer to the campaign count than to N. Dependence column: "
        "'in-sample' entries are scored against the fit's own source data "
        "(implementation check, NOT independent prediction); 'weak-evidence' "
        "entries are derived from a consumed measurement (consistency check); "
        "'u_meas' is the median reported measurement uncertainty where "
        "records declare one (no coverage factor k reported in the current "
        "DB, so errors are not normalized by k*u).",
        "",
        "## Main statistics (confidence: high + medium)",
        "",
        _TABLE_HEADER,
    ]
    lines += _cell_rows(result["statistics"]["cells"]) or ["| - | no scored quantities | | | | | | | | |"]

    # F006: kampanya duzeyinde ozet (kumelenmis veride durust gorunum).
    camp_cells = [c for c in result["statistics"]["cells"]
                  if c.get("campaign_stats")]
    if camp_cells:
        lines += ["", "## Campaign-level statistics (clustered data)", "",
                  "Per-campaign mean signed errors, then statistics across "
                  "campaigns; single-campaign cells cannot appear here.", "",
                  "| Motor | Quantity | Campaigns | Bias % | Median APE % |",
                  "|---|---|---|---|---|"]
        for cell in camp_cells:
            cs = cell["campaign_stats"]
            lines.append(
                f"| {cell['motor_type']} | {cell['quantity']} "
                f"| {cs['n_campaigns']} | {_fmt_pct(cs['bias_pct'])} "
                f"| {cs['median_ape_pct']:.1f} |")

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

    warned = [rr for rr in result.get("records", [])
              if rr.get("engine_warnings")]
    if warned:
        lines += ["", "## Engine warnings during record runs", ""]
        for rr in warned:
            for msg in rr["engine_warnings"]:
                lines.append(f"- `{rr['test_id']}`: {msg}")

    return "\n".join(lines) + "\n"
