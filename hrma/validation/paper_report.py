"""Paper-kalite korelasyon rapor ureticisi (v2.5.0 G4).

``hrma.validation.correlation_runner.run_correlation`` ciktisindan makale
kalitesinde bir rapor uretir: parite figurleri, isaretli hata dagilimi,
Markdown ozeti (Ingilizce) ve tek PDF. Amac gercek-deney DB'si vs HRMA
korelasyonunu dogrudan makaleye tasinabilir gorsel + sayilarla belgelemek.

Tasarim kararlari (dogruluk ve durustluk):
  - Parite noktalari ``result["records"][].scores`` icinden toplanir (hucre
    istatistigi yalniz isaretli hatayi tutar, tahmin/olcum degerlerini degil).
  - Katman ayrimi correlation_runner._aggregate ile BIREBIR ayni: anomaly
    isaretli kayit ana istatistige girmez (ayri ici bos isaretci); low-guven
    kayit ayri; main = high + medium.
  - Aykirilar (cell["outlier_test_ids"]) isaretlenir ama ATILMAZ (parite
    figurunde koyu halka, hata dagiliminda koyu kenar).
  - Determinizm: ayni ``result`` -> ayni Markdown (tek istisna: zaman damgasi
    satiri, ``timestamp`` parametresiyle sabitlenebilir). PNG'ler metadata'siz
    (matplotlib PNG'ye 'Software' etiketi gomer, ``metadata={"Software": None}``
    ile soyulur).

Renk politikasi (paper icin beyaz zemin, renk-koru guvenli):
  - Ana seri: mavi #2563a8 (dolu isaretci)
  - Anomaly: turuncu #ff8c33 (ici bos isaretci)
  - y=x ve referans cizgiler: notr gri
  - Cirtlak ('red'/'blue'/'green' CSS adlari, Jet/Rainbow, #667eea ailesi) YOK.

CLI:
    python3 -m hrma.validation.paper_report [--out DIR] [--from-json PATH]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")  # basssiz (headless) render — pencere/GUI acmaz
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from hrma.validation import correlation_runner as cr  # noqa: E402
from hrma.validation.correlation_runner import (  # noqa: E402
    MAIN_CONFIDENCE_LEVELS,
    run_correlation,
    to_markdown,
)

__all__ = [
    "REPORT_VERSION",
    "generate_report",
]

REPORT_VERSION = "1"

# --- Renk paleti (renk-koru guvenli, beyaz zemin) ---------------------------
_BLUE = "#2563a8"        # ana seri dolu isaretci
_BLUE_EDGE = "#123a63"   # ana seri kenari (koyu mavi)
_ORANGE = "#ff8c33"      # anomaly (ici bos)
_GRAY = "#888888"        # y=x cizgisi
_BAND = "#2563a8"        # +-%10 bant dolgusu (dusuk alfa)
_OUTLIER_EDGE = "#1a1a1a"  # aykiri koyu halka
_ZERO_LINE = "#555555"   # hata dagiliminda 0 cizgisi

# Log-log secim esigi: (maks/min) bu carpani asarsa ve tum degerler pozitifse
# eksenler log-log yapilir (burn_rate/regression_rate gibi dekatlar-asan
# buyukluklerde okunaklilik icin).
_LOG_SPAN_THRESHOLD = 50.0

# +-%10 kabul bandi (parite figuru + hata dagilimi referansi).
_BAND_PCT = 10.0

# Buyuk hucrede aykiri isaret disinda ek onlem gerekmez; MAD zaten runner'da.

# SI birim etiketleri (eksen basligi icin). Bilinmeyen -> "SI"; boyutsuz -> "".
_SI_UNIT_BY_BASE: Dict[str, str] = {
    "thrust": "N", "thrust_mean": "N", "thrust_peak": "N",
    "thrust_sl": "N", "thrust_vac": "N",
    "chamber_pressure": "Pa", "chamber_pressure_peak": "Pa",
    "c_star": "m/s",
    "isp": "s", "isp_vac": "s", "isp_sl": "s",
    "regression_rate": "m/s", "burn_rate": "m/s",
    "port_diameter_initial": "m", "port_diameter_final": "m",
    "throat_diameter": "m",
    "total_impulse": "N.s",
    "mdot_ox": "kg/s", "mdot_fuel": "kg/s", "mdot_total": "kg/s",
    "gox": "kg/(m^2.s)",
    "fuel_density": "kg/m^3",
    "injector_area": "m^2",
    "of_ratio": "", "expansion_ratio": "", "eta_c_star": "",
}

# Matplotlib stil baglami (global rcParams'i KIRLETMEZ, rc_context ile lokal).
_STYLE: Dict[str, Any] = {
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
    "savefig.edgecolor": "white",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 8,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "axes.grid": True,
    "grid.color": "#dddddd",
    "grid.linewidth": 0.6,
    "axes.edgecolor": "#333333",
    "axes.linewidth": 0.8,
}

# PNG'den 'Software' etiketini soy (matplotlib surumu gomer -> byte-determinizm
# icin temizle). PNG varsayilan olarak tarih gommez, bu yeterli.
_PNG_METADATA = {"Software": None}

# PDF metadata: sabit basliklar + CreationDate None (tarih gomulmesin).
_PDF_METADATA = {
    "Title": "HRMA correlation report",
    "Author": "HRMA validation",
    "Subject": "Real-experiment database vs HRMA correlation",
    "CreationDate": None,
}


# --- Yardimcilar -------------------------------------------------------------

def _slug(value: Any) -> str:
    """Dosya adina guvenli kucuk-harf slug (a-z0-9_)."""
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_") or "x"


def _unit_label(quantity: str) -> str:
    """Buyukluk taban adi -> SI birim etiketi (bilinmeyen 'SI')."""
    if quantity in _SI_UNIT_BY_BASE:
        return _SI_UNIT_BY_BASE[quantity]
    return "SI"


def _axis_label(prefix: str, quantity: str) -> str:
    unit = _unit_label(quantity)
    if unit == "":
        return f"{prefix} {quantity}"
    return f"{prefix} {quantity} [{unit}]"


def _collect_points(result: Dict[str, Any]) -> Dict[Tuple[str, str],
                                                    Dict[str, List[Dict]]]:
    """(motor_type, quantity) -> {'main','low','anomaly'} nokta listeleri.

    Katman ayrimi correlation_runner._aggregate ile BIREBIR ayni. Her nokta:
    {test_id, predicted, measured, error_pct, confidence, outlier}. Aykiri
    isareti hucre istatistigindeki outlier_test_ids'ten alinir (yalniz main
    katmani icin anlamli).
    """
    # (motor_type, quantity) -> aykiri test_id kumesi (main hucrelerden)
    outliers: Dict[Tuple[str, str], set] = {}
    for cell in result.get("statistics", {}).get("cells", []):
        key = (cell["motor_type"], cell["quantity"])
        outliers[key] = set(cell.get("outlier_test_ids", []))

    points: Dict[Tuple[str, str], Dict[str, List[Dict]]] = {}
    for rr in result.get("records", []):
        if rr.get("status") != "ok":
            continue
        motor_type = rr.get("motor_type")
        confidence = rr.get("confidence")
        is_anomaly = bool(rr.get("anomaly"))
        for quantity, score in rr.get("scores", {}).items():
            if score.get("status") != "scored":
                continue
            key = (motor_type, quantity)
            layer = ("anomaly" if is_anomaly
                     else "main" if confidence in MAIN_CONFIDENCE_LEVELS
                     else "low")
            bucket = points.setdefault(
                key, {"main": [], "low": [], "anomaly": []})
            bucket[layer].append({
                "test_id": rr.get("test_id"),
                "predicted": float(score["predicted_si"]),
                "measured": float(score["measured_si"]),
                "error_pct": float(score["error_pct"]),
                "confidence": confidence,
                "outlier": rr.get("test_id") in outliers.get(key, set()),
            })
    # Deterministik siralama (test_id'ye gore)
    for bucket in points.values():
        for lst in bucket.values():
            lst.sort(key=lambda p: str(p["test_id"]))
    return points


def _use_log(values: List[float]) -> bool:
    """Tum degerler pozitif ve (maks/min) esigi asiyorsa log-log kullan."""
    vals = [v for v in values if v is not None]
    if not vals or any(v <= 0 for v in vals):
        return False
    lo, hi = min(vals), max(vals)
    return hi / lo >= _LOG_SPAN_THRESHOLD


def _find_cell(cells: List[Dict[str, Any]], motor_type: str,
               quantity: str) -> Optional[Dict[str, Any]]:
    for cell in cells:
        if cell["motor_type"] == motor_type and cell["quantity"] == quantity:
            return cell
    return None


# --- Figur 1: parite --------------------------------------------------------

def _parity_figure(cell: Dict[str, Any],
                   layers: Dict[str, List[Dict]]) -> "plt.Figure":
    """Bir (motor_type x quantity) hucresi icin predicted-vs-measured figuru.

    Ana katman dolu mavi; anomaly ici bos turuncu (AYNI figurde, efsanede
    'excluded from statistics' notuyla). y=x + %10 bant. Aykirilar koyu halka.
    """
    motor_type = cell["motor_type"]
    quantity = cell["quantity"]
    main = layers.get("main", [])
    anomaly = layers.get("anomaly", [])

    all_vals: List[float] = []
    for p in main + anomaly:
        all_vals.extend([p["measured"], p["predicted"]])
    logscale = _use_log(all_vals)

    lo, hi = min(all_vals), max(all_vals)
    if logscale:
        lo_lim, hi_lim = lo / 1.15, hi * 1.15
        band_x = np.geomspace(lo_lim, hi_lim, 200)
    else:
        span = hi - lo or (abs(hi) or 1.0)
        lo_lim, hi_lim = lo - 0.06 * span, hi + 0.06 * span
        band_x = np.linspace(lo_lim, hi_lim, 200)

    fig, ax = plt.subplots(figsize=(5.0, 5.0), constrained_layout=True)

    # +-%10 bant (dolgu) + kenar cizgileri
    frac = _BAND_PCT / 100.0
    ax.fill_between(band_x, (1 - frac) * band_x, (1 + frac) * band_x,
                    color=_BAND, alpha=0.10, linewidth=0,
                    label=f"+/-{_BAND_PCT:.0f}% band", zorder=1)
    ax.plot(band_x, band_x, color=_GRAY, linewidth=1.2, linestyle="-",
            label="y = x", zorder=2)

    # Ana katman: aykiri olmayanlar + aykirilar (koyu halka)
    main_reg = [p for p in main if not p["outlier"]]
    main_out = [p for p in main if p["outlier"]]
    if main_reg:
        ax.scatter([p["measured"] for p in main_reg],
                   [p["predicted"] for p in main_reg],
                   s=42, facecolor=_BLUE, edgecolor=_BLUE_EDGE,
                   linewidth=0.7, zorder=4,
                   label=f"main (high+medium), n={len(main)}")
    if main_out:
        ax.scatter([p["measured"] for p in main_out],
                   [p["predicted"] for p in main_out],
                   s=60, facecolor=_BLUE, edgecolor=_OUTLIER_EDGE,
                   linewidth=1.6, zorder=5,
                   label="outlier (flagged, kept)")
    if anomaly:
        ax.scatter([p["measured"] for p in anomaly],
                   [p["predicted"] for p in anomaly],
                   s=52, facecolor="none", edgecolor=_ORANGE,
                   linewidth=1.4, zorder=3,
                   label="anomaly-flagged (excluded from statistics)")

    if logscale:
        ax.set_xscale("log")
        ax.set_yscale("log")
    ax.set_xlim(lo_lim, hi_lim)
    ax.set_ylim(lo_lim, hi_lim)
    ax.set_aspect("equal", "box")

    ax.set_xlabel(_axis_label("Measured", quantity))
    ax.set_ylabel(_axis_label("Predicted", quantity))
    ax.set_title(f"{motor_type} - {quantity} (n={cell['n']})")
    ax.legend(loc="best", framealpha=0.9)
    return fig


# --- Figur 2: isaretli hata dagilimi ----------------------------------------

def _error_distribution_figure(result: Dict[str, Any],
                               points: Dict[Tuple[str, str],
                                            Dict[str, List[Dict]]]
                               ) -> "plt.Figure":
    """Hucre basina isaretli hata (%) strip grafigi; bias + 0 cizgisi gorunur.

    Az nokta -> strip (her nokta ayri gorunur, bias korunur). Cok noktali
    hucre de strip'te okunakli kalir (deterministik dagitim). Anomaly ve low
    ana istatistige girmedigi icin bu figur yalniz main hucrelerini gosterir.
    """
    cells = result.get("statistics", {}).get("cells", [])
    rows = [c for c in cells]  # zaten (motor_type, quantity) sirali

    fig, ax = plt.subplots(
        figsize=(7.2, max(2.6, 0.55 * len(rows) + 1.4)),
        constrained_layout=True)

    if not rows:
        ax.axis("off")
        ax.text(0.5, 0.5, "No main-layer scored cells",
                ha="center", va="center", fontsize=11, color="#555555")
        return fig

    # Referans: 0 cizgisi + +-%10 bant golgesi
    ax.axvspan(-_BAND_PCT, _BAND_PCT, color=_BLUE, alpha=0.06, zorder=0)
    ax.axvline(0.0, color=_ZERO_LINE, linewidth=1.1, linestyle="--",
               zorder=1, label="zero bias")

    labels: List[str] = []
    for row_idx, cell in enumerate(rows):
        key = (cell["motor_type"], cell["quantity"])
        pts = points.get(key, {}).get("main", [])
        n = len(pts)
        # Deterministik dikey dagitim (jitter yerine sabit ofset)
        if n > 1:
            offs = np.linspace(-0.24, 0.24, n)
        else:
            offs = np.zeros(n)
        reg_x, reg_y, out_x, out_y = [], [], [], []
        for off, p in zip(offs, pts):
            if p["outlier"]:
                out_x.append(p["error_pct"])
                out_y.append(row_idx + off)
            else:
                reg_x.append(p["error_pct"])
                reg_y.append(row_idx + off)
        if reg_x:
            ax.scatter(reg_x, reg_y, s=34, facecolor=_BLUE,
                       edgecolor=_BLUE_EDGE, linewidth=0.6, zorder=3)
        if out_x:
            ax.scatter(out_x, out_y, s=52, facecolor=_BLUE,
                       edgecolor=_OUTLIER_EDGE, linewidth=1.5, zorder=4)
        # Bias isaretcisi (turuncu elmas)
        ax.scatter([cell["bias_pct"]], [row_idx], s=90, marker="D",
                   facecolor=_ORANGE, edgecolor=_OUTLIER_EDGE,
                   linewidth=0.8, zorder=5)
        labels.append(f"{cell['motor_type']}:{cell['quantity']} (n={n})")

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.invert_yaxis()
    ax.set_xlabel("Signed error % = (predicted - measured) / measured * 100")
    ax.set_title("Signed error per cell (diamond = bias, main layer)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="best", framealpha=0.9)
    return fig


# --- PDF ozet sayfasi --------------------------------------------------------

def _summary_page(result: Dict[str, Any]) -> "plt.Figure":
    """PDF ilk sayfasi: baslik + metadata + ana istatistik tablosu."""
    fig = plt.figure(figsize=(8.27, 11.69))  # A4 portre
    fig.text(0.5, 0.955, "HRMA correlation report",
             ha="center", va="top", fontsize=16, fontweight="bold")
    fig.text(0.5, 0.925,
             "Real-experiment database vs HRMA (auto-generated)",
             ha="center", va="top", fontsize=10, color="#444444")

    stats = result.get("statistics", {})
    meta_lines = [
        f"Runner version: {result.get('runner_version')} "
        f"(adapter {result.get('adapter_version')}, "
        f"report {REPORT_VERSION})",
        f"Records in statistics: {result.get('n_records')} "
        f"(synthetic excluded: {result.get('n_synthetic_excluded')})",
        f"DB content hash: {result.get('db_content_hash')}",
        f"Main cells: {len(stats.get('cells', []))} | "
        f"low-confidence cells: {len(stats.get('low_confidence_cells', []))} "
        f"| anomaly entries: {len(stats.get('anomaly_entries', []))}",
        "Status counts: " + ", ".join(
            f"{k}={v}" for k, v in result.get("status_counts", {}).items()),
        "Signed error: (predicted - measured) / measured * 100. "
        "Outliers (>3*MAD) flagged, never dropped.",
    ]
    y = 0.885
    for line in meta_lines:
        fig.text(0.07, y, line, ha="left", va="top", fontsize=9,
                 family="DejaVu Sans")
        y -= 0.022

    # Ana istatistik tablosu (main hucreler)
    cells = stats.get("cells", [])
    ax = fig.add_axes([0.06, 0.06, 0.88, 0.66])
    ax.axis("off")
    if not cells:
        ax.text(0.5, 0.95, "No main-layer scored cells",
                ha="center", va="top", fontsize=11, color="#555555")
    else:
        max_rows = 30
        shown = cells[:max_rows]
        col_labels = ["Motor", "Quantity", "N", "Bias %",
                      "MedAPE %", "RMS %", "Max % (test)"]
        table_rows = []
        for c in shown:
            table_rows.append([
                c["motor_type"], c["quantity"], str(c["n"]),
                f"{c['bias_pct']:+.1f}", f"{c['median_ape_pct']:.1f}",
                f"{c['rms_pct']:.1f}",
                f"{c['max']['error_pct']:+.1f} ({c['max']['test_id']})",
            ])
        tbl = ax.table(cellText=table_rows, colLabels=col_labels,
                       loc="upper center", cellLoc="center")
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(7)
        tbl.scale(1.0, 1.25)
        # Baslik satirini vurgula
        for col in range(len(col_labels)):
            hdr = tbl[0, col]
            hdr.set_facecolor(_BLUE)
            hdr.set_text_props(color="white", fontweight="bold")
        if len(cells) > max_rows:
            ax.text(0.5, 0.02,
                    f"... {len(cells) - max_rows} more cells in Markdown report",
                    ha="center", va="bottom", fontsize=8, color="#777777")
    return fig


# --- Markdown ----------------------------------------------------------------

def _detailed_tables(result: Dict[str, Any]) -> str:
    """correlation_runner.to_markdown ciktisindan H1 basligini soyar."""
    text = to_markdown(result)
    lines = text.splitlines()
    # Ilk H1 satirini ve onu izleyen bos satirlari at
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    return "\n".join(lines).rstrip() + "\n"


def _build_markdown(result: Dict[str, Any],
                    parity_basenames: List[Tuple[str, str, str]],
                    error_basename: str,
                    timestamp: str,
                    commentary: Optional[str] = None) -> str:
    """Ingilizce, emoji YOK, deterministik (zaman damgasi tek satirda izole)."""
    stats = result.get("statistics", {})
    cells = stats.get("cells", [])

    lines: List[str] = [
        "# HRMA validation: correlation report",
        "",
        f"Generated: {timestamp}",
        "",
        "Auto-generated numbers; narrative added by authors.",
        "",
        "## Overview",
        "",
        f"- Runner version: {result.get('runner_version')} "
        f"(adapter {result.get('adapter_version')}, report {REPORT_VERSION})",
        f"- Records in statistics pipeline: {result.get('n_records')} "
        f"(synthetic excluded: {result.get('n_synthetic_excluded')})",
        f"- DB content hash: `{result.get('db_content_hash')}`",
        f"- Main cells: {len(cells)} | low-confidence cells: "
        f"{len(stats.get('low_confidence_cells', []))} | "
        f"anomaly entries: {len(stats.get('anomaly_entries', []))}",
        "- Status counts: " + ", ".join(
            f"{k}={v}" for k, v in result.get("status_counts", {}).items()),
        "",
        "## Confidence layers",
        "",
        "- Main (high + medium): drives the headline statistics; drawn as "
        "filled blue markers in parity figures.",
        "- Low-confidence: reported separately, kept out of the headline "
        "statistics (see detailed tables).",
        "- Anomaly-flagged: excluded from statistics; drawn as open orange "
        "markers so they stay visible without biasing the numbers.",
        "- Outliers (|error - median| > 3*MAD): flagged (dark ring), never "
        "dropped; an 'excl. outliers' row is provided as extra information.",
        "",
        "## Figures",
        "",
    ]

    if parity_basenames:
        lines.append("Parity (predicted vs measured, y=x with "
                     f"+/-{_BAND_PCT:.0f}% band):")
        lines.append("")
        for motor_type, quantity, basename in parity_basenames:
            cell = _find_cell(cells, motor_type, quantity)
            if cell is not None:
                caption = (f"{motor_type} {quantity}: n={cell['n']}, "
                           f"bias={cell['bias_pct']:+.1f}%, "
                           f"median APE={cell['median_ape_pct']:.1f}%, "
                           f"RMS={cell['rms_pct']:.1f}%")
            else:
                caption = f"{motor_type} {quantity}"
            lines.append(f"- `{basename}` - {caption}")
        lines.append("")
    else:
        lines += ["No cell reached n>=3; no parity figure produced.", ""]

    lines += [
        f"Signed error distribution: `{error_basename}` - one row per main "
        "cell, diamond marks the bias, dashed line marks zero.",
        "",
    ]
    if commentary:
        # Yazar anlatisi ayri dosyadan (COMMENTARY.md) enjekte edilir; boylece
        # rapor yeniden uretildiginde elle yazilan anlati KAYBOLMAZ.
        lines += [
            "## Author commentary",
            "",
            "> The numbers above are auto-generated; the narrative below is "
            "maintained by the authors in `COMMENTARY.md`.",
            "",
            commentary.strip(),
            "",
        ]
    else:
        lines += [
            "## Author commentary (skeleton)",
            "",
            "> The numbers above are auto-generated; the narrative below is "
            "written by the authors. (Create COMMENTARY.md next to this "
            "report to have it injected here on every regeneration.)",
            "",
            "### Overall agreement",
            "",
            "_(authors: summarise how close predictions track measurements "
            "across motor types.)_",
            "",
            "### Systematic biases",
            "",
            "_(authors: comment on the sign of the bias per quantity and the "
            "likely physical cause.)_",
            "",
            "### Outliers and anomalies",
            "",
            "_(authors: discuss flagged outliers and anomaly-tagged records "
            "and why they are kept out of the headline numbers.)_",
            "",
            "### Limitations",
            "",
            "_(authors: state coverage gaps, unsupported record types and "
            "quantities with too few points.)_",
            "",
        ]
    lines += [
        "## Detailed correlation tables",
        "",
        _detailed_tables(result).rstrip(),
        "",
    ]
    return "\n".join(lines) + "\n"


# --- Ana giris ---------------------------------------------------------------

def generate_report(result: Optional[Dict[str, Any]] = None,
                    out_dir: str = "docs/correlation_report",
                    *, timestamp: Optional[str] = None) -> Dict[str, Any]:
    """Korelasyon sonucundan paper-kalite rapor uretir; dosya yollari doner.

    Args:
        result: ``run_correlation`` ciktisi. None ise ``run_correlation()``
            calistirilir (gercek DB, 1-2 dk surebilir).
        out_dir: cikti dizini (olusturulur). Uretilenler: report.md,
            parity_<motor>_<quantity>.png (n>=3 hucreler), error_distribution.png,
            report.pdf.
        timestamp: Markdown'daki 'Generated' satiri icin sabit deger; None ise
            yerel saat. Testlerde determinizm icin sabitlenebilir.

    Returns:
        {'out_dir','markdown','pdf','parity_figures','error_distribution',
         'figures','n_parity_figures','db_content_hash'} — tum yollar mutlak.
    """
    if result is None:
        result = run_correlation()
    if timestamp is None:
        timestamp = _dt.datetime.now().isoformat(timespec="seconds")

    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    points = _collect_points(result)
    cells = result.get("statistics", {}).get("cells", [])

    pdf_path = os.path.join(out_dir, "report.pdf")
    md_path = os.path.join(out_dir, "report.md")
    error_png = os.path.join(out_dir, "error_distribution.png")

    parity_paths: List[str] = []
    parity_basenames: List[Tuple[str, str, str]] = []

    with plt.rc_context(_STYLE):
        with PdfPages(pdf_path, metadata=_PDF_METADATA) as pdf:
            # Sayfa 1: ozet + tablo
            sfig = _summary_page(result)
            pdf.savefig(sfig)
            plt.close(sfig)

            # Parite figurleri: yalniz n>=3 hucreler
            for cell in cells:
                if cell["n"] < 3:
                    continue
                key = (cell["motor_type"], cell["quantity"])
                layers = points.get(
                    key, {"main": [], "low": [], "anomaly": []})
                fig = _parity_figure(cell, layers)
                basename = (f"parity_{_slug(cell['motor_type'])}_"
                            f"{_slug(cell['quantity'])}.png")
                png_path = os.path.join(out_dir, basename)
                fig.savefig(png_path, dpi=150, metadata=_PNG_METADATA)
                pdf.savefig(fig)
                plt.close(fig)
                parity_paths.append(png_path)
                parity_basenames.append(
                    (cell["motor_type"], cell["quantity"], basename))

            # Hata dagilimi figuru (her zaman uretilir)
            efig = _error_distribution_figure(result, points)
            efig.savefig(error_png, dpi=150, metadata=_PNG_METADATA)
            pdf.savefig(efig)
            plt.close(efig)

    commentary = None
    commentary_path = os.path.join(out_dir, "COMMENTARY.md")
    if os.path.exists(commentary_path):
        with open(commentary_path, encoding="utf-8") as fh:
            commentary = fh.read()

    md = _build_markdown(result, parity_basenames,
                         os.path.basename(error_png), timestamp,
                         commentary=commentary)
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md)

    figures = parity_paths + [error_png]
    return {
        "out_dir": out_dir,
        "markdown": md_path,
        "pdf": pdf_path,
        "parity_figures": parity_paths,
        "error_distribution": error_png,
        "figures": figures,
        "n_parity_figures": len(parity_paths),
        "db_content_hash": result.get("db_content_hash"),
    }


# --- CLI ---------------------------------------------------------------------

def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m hrma.validation.paper_report",
        description="Generate a paper-quality HRMA correlation report.")
    parser.add_argument("--out", default="docs/correlation_report",
                        help="output directory (default: docs/correlation_report)")
    parser.add_argument("--from-json", default=None,
                        help="load run_correlation result from a JSON file "
                             "instead of running the correlation")
    args = parser.parse_args(argv)

    result = None
    if args.from_json:
        with open(args.from_json, encoding="utf-8") as fh:
            result = json.load(fh)

    info = generate_report(result=result, out_dir=args.out)
    print("HRMA correlation report generated:")
    print(f"  out_dir: {info['out_dir']}")
    print(f"  markdown: {info['markdown']}")
    print(f"  pdf: {info['pdf']}")
    print(f"  parity figures: {info['n_parity_figures']}")
    for path in info["figures"]:
        print(f"    - {path}")
    print(f"  db_content_hash: {info['db_content_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
