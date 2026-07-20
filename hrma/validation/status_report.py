"""VALIDATION_STATUS.md otomatik korelasyon bölgesi üreticisi (v2.5.0 G3).

Spec: docs/arge-guven-2026-07/arge_korelasyon_tasarim.md Bölüm 4.1 —
işaretçili bölge yaklaşımı: belgenin el yazısı kısımları korunur, yalnız
``AUTO-CORRELATION`` işaretçileri arasındaki tablo yeniden üretilir.

Kullanım:
    python3 -m hrma.validation.status_report            # koş + belgeyi güncelle
    python3 -m hrma.validation.status_report --dry-run  # koş + bölgeyi yazdır

``correlation_cells`` yardımcısı API katmanıyla (app.py
``/api/correlation-report``) PAYLAŞILAN tek hücre-düzleştirme
implementasyonudur: main / low_confidence hücreleri + anomaly girişlerinin
(motor_type x quantity) toplulaştırması aynı şekle iner
(bias_percent / rms_percent / median_ape_percent / mape_percent /
worst_test_id). Üretilen metin İngilizce'dir ve emoji içermez (UI kuralı).
"""

from __future__ import annotations

import argparse
import contextlib
import math
import os
import statistics as _stats
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "MARKER_BEGIN",
    "MARKER_END",
    "DEFAULT_STATUS_PATH",
    "correlation_cells",
    "generate_status_section",
    "update_validation_status",
    "main",
]

MARKER_BEGIN = "<!-- AUTO-CORRELATION:BEGIN -->"
MARKER_END = "<!-- AUTO-CORRELATION:END -->"

# hrma/validation/status_report.py -> repo kökü / docs/VALIDATION_STATUS.md
# (v2.5.4 kök temizliği: gevşek .md dosyaları docs/ altına taşındı)
DEFAULT_STATUS_PATH = Path(__file__).resolve().parents[2] / "docs" / "VALIDATION_STATUS.md"


def _flatten_cell(cell: Dict[str, Any], layer: str) -> Dict[str, Any]:
    """correlation_runner hücresini API/rapor şekline indirger."""
    worst = cell["max"]
    if abs(cell["min"]["error_pct"]) > abs(cell["max"]["error_pct"]):
        worst = cell["min"]
    return {
        "motor_type": cell["motor_type"],
        "quantity": cell["quantity"],
        "layer": layer,
        "n": cell["n"],
        "bias_percent": cell["bias_pct"],
        "rms_percent": cell["rms_pct"],
        "median_ape_percent": cell["median_ape_pct"],
        "mape_percent": cell["mape_pct"],
        "worst_test_id": worst["test_id"],
    }


def correlation_cells(statistics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Koşu istatistiğini katmanlı düz hücre listesine çevirir.

    Katmanlar: 'main' (high+medium), 'low_confidence' (ayrı raporlanan low
    kayıtlar), 'anomaly' (anomaly.flag=true — ana istatistiğe girmeyen
    girişlerin hücre-toplulaştırması). Aykırı işaretleme bilgisi
    correlation_runner sonucunda durur; bu düz görünüm rapor/panel içindir.
    """
    cells: List[Dict[str, Any]] = []
    for layer, cell_list in (("main", statistics.get("cells", [])),
                             ("low_confidence",
                              statistics.get("low_confidence_cells", []))):
        for cell in cell_list:
            cells.append(_flatten_cell(cell, layer))

    grouped: Dict[Any, List[Dict[str, Any]]] = {}
    for entry in statistics.get("anomaly_entries", []):
        grouped.setdefault(
            (entry["motor_type"], entry["quantity"]), []).append(entry)
    for (motor_type, quantity), entries in sorted(grouped.items()):
        errors = [e["error_pct"] for e in entries]
        apes = [abs(e) for e in errors]
        worst = max(entries, key=lambda e: abs(e["error_pct"]))
        cells.append({
            "motor_type": motor_type,
            "quantity": quantity,
            "layer": "anomaly",
            "n": len(errors),
            "bias_percent": float(_stats.fmean(errors)),
            "rms_percent": float(math.sqrt(_stats.fmean(e * e
                                                        for e in errors))),
            "median_ape_percent": float(_stats.median(apes)),
            "mape_percent": float(_stats.fmean(apes)),
            "worst_test_id": worst["test_id"],
        })
    return cells


def generate_status_section(result: Dict[str, Any],
                            generated_on: Optional[str] = None) -> str:
    """Koşu sonucundan işaretçiler ARASINA girecek markdown'ı üretir.

    İşaretçilerin kendisi dahil DEĞİLDİR; ``update_validation_status``
    bölgeyi işaretçiler arasına yerleştirir. İngilizce, emoji'siz.
    """
    generated_on = generated_on or date.today().isoformat()
    counts = result["status_counts"]
    lines = [
        "*This block is auto-generated from the real-experiment correlation "
        "run; do not edit it by hand. Regenerate with "
        "`python3 -m hrma.validation.status_report`.*",
        "",
        f"- Generated: {generated_on} (runner v{result['runner_version']}, "
        f"adapter v{result['adapter_version']})",
        f"- Experiment DB content hash: `{result['db_content_hash']}`",
        f"- Records: {result['n_records']} total, "
        f"scored {counts.get('ok', 0)}, "
        f"insufficient inputs {counts.get('insufficient_inputs', 0)}, "
        f"not supported (v1) {counts.get('not_supported', 0)}, "
        f"runner errors {counts.get('runner_error', 0)}",
        "- Signed error convention: (predicted - measured) / measured x 100. "
        "Outliers are flagged, never dropped; anomaly-flagged records are "
        "aggregated separately.",
        "",
        "| Motor | Quantity | Layer | N | Bias % | Median APE % | RMS % "
        "| Worst test |",
        "|---|---|---|---|---|---|---|---|",
    ]
    cells = correlation_cells(result["statistics"])
    if not cells:
        lines.append("| - | no scored quantities | | | | | | |")
    for cell in cells:
        lines.append(
            f"| {cell['motor_type']} | {cell['quantity']} | {cell['layer']} "
            f"| {cell['n']} | {cell['bias_percent']:+.1f} "
            f"| {cell['median_ape_percent']:.1f} "
            f"| {cell['rms_percent']:.1f} "
            f"| {cell['worst_test_id']} |")
    return "\n".join(lines)


def update_validation_status(result: Dict[str, Any],
                             path: Optional[Path] = None,
                             generated_on: Optional[str] = None) -> Path:
    """İşaretçiler arasındaki bölgeyi yeniden üretir; belgenin kalanına
    DOKUNMAZ. İşaretçiler yoksa hata (bölge elle bir kez eklenmelidir ki
    üretici belgenin el yazısı yapısına karar vermek zorunda kalmasın)."""
    path = Path(path) if path is not None else DEFAULT_STATUS_PATH
    text = path.read_text(encoding="utf-8")
    if MARKER_BEGIN not in text or MARKER_END not in text:
        raise ValueError(
            f"{path}: '{MARKER_BEGIN}' / '{MARKER_END}' isaretcileri yok — "
            "otomatik bolge belgeye bir kez elle eklenmeli")
    head, rest = text.split(MARKER_BEGIN, 1)
    _, tail = rest.split(MARKER_END, 1)
    section = generate_status_section(result, generated_on=generated_on)
    new_text = f"{head}{MARKER_BEGIN}\n{section}\n{MARKER_END}{tail}"
    path.write_text(new_text, encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m hrma.validation.status_report",
        description=("Run the real-experiment correlation and refresh the "
                     "AUTO-CORRELATION block of VALIDATION_STATUS.md."))
    parser.add_argument("--status-file", default=None,
                        help="Path to VALIDATION_STATUS.md (default: repo "
                             "root copy).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the generated block instead of writing "
                             "the file.")
    args = parser.parse_args(argv)

    from hrma.validation import correlation_runner as _cr

    with open(os.devnull, "w", encoding="utf-8") as devnull, \
            contextlib.redirect_stdout(devnull):
        result = _cr.run_correlation()

    if args.dry_run:
        print(generate_status_section(result))
        return 0

    path = update_validation_status(
        result,
        path=Path(args.status_file) if args.status_file else None)
    counts = result["status_counts"]
    print(f"Updated {path} (records: {result['n_records']}, "
          f"scored: {counts.get('ok', 0)}, "
          f"db hash: {result['db_content_hash'][:12]}...)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
