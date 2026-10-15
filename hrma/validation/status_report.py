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


def _cr_dependence_label(stats: Dict[str, Any]) -> str:
    """Bağımlılık künyesi — TEK KAYNAK ``correlation_runner._dependence_label``.

    P10B2-01: künye metni burada İKİNCİ KEZ yazılmaz; markdown tablosunun
    "Dependence" sütununu üreten fonksiyonun ta kendisi çağrılır, böylece
    iki yüz aynı cümleyi basar. İçe aktarma fonksiyon içindedir (modül
    döngüsel bağımlılık kurmasın — ``_cr_criterion_text`` ile aynı desen).
    """
    from hrma.validation.correlation_runner import _dependence_label
    return _dependence_label(stats)


#: P10B2-01 (ÖH D16 / app-api) — BAĞIMLILIK KÜNYESİ SERİLEŞTİRİCİDE DÜŞÜYORDU.
#:
#: ÖLÇÜLDÜ (taban 6fde52b): ``correlation_runner`` hücresi ``n_in_sample``,
#: ``n_campaigns``, ``n_weak_evidence``, ``median_measurement_u_pct``
#: alanlarını doğru hesaplıyor ve ``to_markdown`` bunları "Dependence"
#: sütununda yayımlıyordu (``'in-sample' in to_markdown(...)`` → True).
#: Ürün yüzüne çıkan İKİ kanal ise künyeyi taşımıyordu: düz hücre yalnız 9
#: anahtar taşıyordu ve ``generate_status_section`` çıktısında
#: ``'in-sample'`` HİÇ geçmiyordu (→ False). Sonuç: yayımlanan
#: "solid / burn_rate medAPE %0,51" satırı, 27/27 girişi fitin KENDİ kaynak
#: verisi olan bir in-sample denetimini bağımsız doğrulama gibi gösteriyordu.
#:
#: Onarım: künye alanları düz hücreye ve yayımlanan tabloya taşındı. Sayı
#: değişmedi — değişen, sayının NEYE dayandığının artık söylenmesi.
_DEPENDENCE_FIELDS = (
    ("n_campaigns", "n_campaigns"),
    ("n_in_sample", "n_in_sample"),
    ("n_weak_evidence", "n_weak_evidence"),
    ("n_with_measurement_u", "n_with_measurement_u"),
    ("median_measurement_u_pct", "median_measurement_u_pct"),
    ("median_abs_normalized_error", "median_abs_normalized_error"),
)


#: ÖH D27 / app-api a3 (P13B4-05) — HÜCRENİN DÜRÜSTLÜK ALANLARI.
#:
#: ÖLÇÜLDÜ (``docs/scofield/raw/OH/D27/app-api/a3/once.json`` K1, worktree
#: ``a67dd68``): ``correlation_runner._cell`` YİRMİ anahtar üretiyor,
#: ``_flatten_cell`` ONALTI yayımlıyordu. Düşen yedi anahtarın ikisi
#: (``min``/``max``) ``worst_test_id`` içinde YAŞIYOR, biri (``entries``)
#: ham satır listesidir ve düz görünüm tasarımı gereği taşımaz. Kalan
#: DÖRDÜ ise hücrenin dürüstlük künyesiydi ve GEREKÇESİZ düşüyordu:
#:
#:   ``confidence_band``      hangi güven katmanının hücresi
#:   ``campaign_stats``       F006 kampanya düzeyi özeti (kümelenmiş veri)
#:   ``outlier_test_ids``     F035 modifiye z-skoru aykırıları
#:   ``stats_excl_outliers``  aynı hücrenin aykırısız satırı
#:
#: Bunlar hücrenin YAN BİLGİSİ değil, yayımlanan medAPE'nin NE OLDUĞUNU
#: söyleyen alanlardır: 27 girişli bir hücre 2 kampanyadan geliyorsa ve
#: 3 aykırı taşıyorsa, o sayı kampanya sayısı ve aykırı listesi olmadan
#: okunamaz (Hurlbert 1984; ASME V&V 20-2009 Böl. 3 — modülün kendi
#: gerekçeleri). ``_flatten_cell`` API katmanıyla PAYLAŞILAN tek
#: düzleştirme olduğu için burada düşen alan kullanıcıya giden gövdede bir
#: daha DOĞMAZ.
#:
#: Sayı ÜRETİLMEDİ: dördü de hücrenin kendi değerleridir, hücrede yoksa
#: ``None`` kalır. Bekçi: ``tests/test_fazb_serilestirici_esligi.py::
#: test_s1_korelasyon_hucresi_alan_esligi`` (xfail borç imi KALDIRILDI).
_HONESTY_FIELDS = ("confidence_band", "campaign_stats", "outlier_test_ids",
                   "stats_excl_outliers")


def _flatten_cell(cell: Dict[str, Any], layer: str) -> Dict[str, Any]:
    """correlation_runner hücresini API/rapor şekline indirger.

    P10B2-01: bağımlılık/belirsizlik künyesi de taşınır — hücrenin n'si
    kadar, o n'in NE OLDUĞU da yayımlanan bilginin parçasıdır.

    ÖH D27 a3 / P13B4-05: hücrenin DÖRT dürüstlük alanı da taşınır
    (bkz. ``_HONESTY_FIELDS``).
    """
    worst = cell["max"]
    if abs(cell["min"]["error_pct"]) > abs(cell["max"]["error_pct"]):
        worst = cell["min"]
    duz = {
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
    for hedef, kaynak in _DEPENDENCE_FIELDS:
        duz[hedef] = cell.get(kaynak)
    for ad in _HONESTY_FIELDS:
        duz[ad] = cell.get(ad)
    duz["dependence"] = _cr_dependence_label(cell)
    return duz


def correlation_cells(statistics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Koşu istatistiğini katmanlı düz hücre listesine çevirir.

    Katmanlar: 'main' (high+medium), 'low_confidence' (ayrı raporlanan low
    kayıtlar), 'anomaly' (anomaly.flag=true — DENEYİN veri kalitesi
    gerekçesiyle ana istatistiğe girmeyen girişler), 'out_of_scope'
    (model_scope.in_scope=false — MODELİN ilan ettiği kapsam gerekçesiyle
    girmeyen girişler; P10B2-06). Aykırı işaretleme bilgisi
    correlation_runner sonucunda durur; bu düz görünüm rapor/panel içindir.

    İki dışlama gerekçesi AYRI katmanlarda yayımlanır: aynı etikette
    toplanırsa okur "model bunu yapamıyor" ile "deney bozuktu" arasındaki
    farkı göremez ve başlık istatistiği modelin zorlandığı vakaları
    veri kusuru kılığında dışarıda bırakır.
    """
    cells: List[Dict[str, Any]] = []
    for layer, cell_list in (("main", statistics.get("cells", [])),
                             ("low_confidence",
                              statistics.get("low_confidence_cells", []))):
        for cell in cell_list:
            cells.append(_flatten_cell(cell, layer))

    grouped: Dict[Any, List[Dict[str, Any]]] = {}
    for katman, anahtar in (("anomaly", "anomaly_entries"),
                            ("out_of_scope", "out_of_scope_entries")):
        for entry in statistics.get(anahtar, []):
            grouped.setdefault(
                (katman, entry["motor_type"], entry["quantity"]), []
            ).append(entry)
    for (katman_adi, motor_type, quantity), entries in sorted(grouped.items()):
        errors = [e["error_pct"] for e in entries]
        apes = [abs(e) for e in errors]
        worst = max(entries, key=lambda e: abs(e["error_pct"]))
        # P10B2-01: anomali/kapsam-dışı hücresi de bağımlılık künyesini taşır —
        # sayımlar girişlerin KENDİ bayraklarından türetilir
        # (correlation_runner._cell_stats ile aynı ölçüt).
        u_vals = [e["measurement_u_pct"] for e in entries
                  if e.get("measurement_u_pct") is not None]
        anomali_kunye = {
            "n": len(errors),
            "n_campaigns": len({e.get("campaign") or e["test_id"]
                                for e in entries}),
            "n_in_sample": sum(1 for e in entries
                               if "in_sample" in (e.get("flags") or ())),
            "n_weak_evidence": sum(1 for e in entries
                                   if "weak_evidence" in (e.get("flags") or ())),
            "n_with_measurement_u": len(u_vals),
            "median_measurement_u_pct": (float(_stats.median(u_vals))
                                         if u_vals else None),
            "median_abs_normalized_error": None,
        }
        hucre = {
            "motor_type": motor_type,
            "quantity": quantity,
            "layer": katman_adi,
            "bias_percent": float(_stats.fmean(errors)),
            "rms_percent": float(math.sqrt(_stats.fmean(e * e
                                                        for e in errors))),
            "median_ape_percent": float(_stats.median(apes)),
            "mape_percent": float(_stats.fmean(apes)),
            "worst_test_id": worst["test_id"],
        }
        hucre.update(anomali_kunye)
        # ÖH D27 a3 / P13B4-05: iki katman AYNI şekle iner. Anomali/kapsam
        # dışı hücresi ``_cell`` üreticisinden gelmediği için bu dört alanı
        # taşımaz; ``None``/boş olarak DURUR ki tüketici "alan yok" ile
        # "değer yok" arasında ayrım yapmak zorunda kalmasın.
        hucre["confidence_band"] = None
        hucre["campaign_stats"] = None
        hucre["outlier_test_ids"] = []
        hucre["stats_excl_outliers"] = None
        hucre["dependence"] = _cr_dependence_label(anomali_kunye)
        cells.append(hucre)
    return cells


def _cr_criterion_text() -> str:
    """Aykırı ölçütünün metni — TEK KAYNAK ``correlation_runner`` sabitleri.

    P10B2-07 kardeşi: belge metni eşikleri ELLE yazmaz, sabitten türetir;
    eşik değişince belge kendiliğinden güncellenir. İçe aktarma fonksiyonun
    içindedir (modül döngüsel bağımlılık kurmasın: ``correlation_runner``
    ``status_report``u değil, ``status_report`` onu okur).
    """
    from hrma.validation.correlation_runner import OUTLIER_CRITERION_TEXT
    return OUTLIER_CRITERION_TEXT


def _records_with_scored_quantity(result: Dict[str, Any]) -> int:
    """Kaç kayıt EN AZ BİR büyüklüğü gerçekten skorladı? (P10B2-10)

    ``status_counts['ok']`` bir DURUM sayımıdır: adaptörün kaydı koşturmayı
    başardığını söyler, tabloya bir sayı girdiğini DEĞİL. ÖLÇÜLDÜ (tam DB,
    28 Ağustos 2026): 98 kayıt "ok", ama bunların 6'sı SIFIR büyüklük
    skorluyor — RL10-A-3-3A'nın BEŞ gerçek ateşleme kaydı
    (``liq-rl10a33a-t1..t5``) ve F-1 spec kaydı
    (``liq-f1-sa503-1968-spec``). Ölçülen büyüklüklerinin tamamı ya motor
    girdisi olarak tüketiliyor ya cebirsel türev sayılıyor; hiçbiri hataya
    dönüşmüyor. "scored 98" başlığı bu yüzden ŞİŞİKTİ: okur, 98 kaydın
    tabloya katkıda bulunduğunu sanıyordu.
    """
    n = 0
    for rr in result.get("records", []):
        if rr.get("status") != "ok":
            continue
        if any(s.get("status") == "scored"
               for s in (rr.get("scores") or {}).values()):
            n += 1
    return n


def _row_numbers(cell: Dict[str, Any]) -> Dict[str, str]:
    """Tablo satırının sayısal sütunları (P10B2-15 tek-gözlem künyesi).

    n=1 hücrede bias / medyan APE / RMS aynı tek sayının üç kopyasıdır
    (bias = e, medAPE = RMS = |e|). Yayımda yalnız İŞARETLİ HATA basılır;
    saçılım sütunları "-" kalır ve büyüklük adı künyeyi taşır. Tek gözlemde
    saçılım yoktur — uydurulmaz.
    """
    if int(cell.get("n", 0)) == 1:
        return {
            "quantity": f"{cell['quantity']} (single observation)",
            "median_ape": "-",
            "rms": "-",
        }
    return {
        "quantity": cell["quantity"],
        "median_ape": f"{cell['median_ape_percent']:.1f}",
        "rms": f"{cell['rms_percent']:.1f}",
    }


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
        # P10B2-10: "ok" bir DURUM sayımıdır, tabloya katkı DEĞİLDİR —
        # ikisi ayrı ayrı yazılır (bkz. _records_with_scored_quantity).
        f"- Records: {result['n_records']} total, "
        f"adapter ok {counts.get('ok', 0)} "
        f"(with at least one scored quantity: "
        f"{_records_with_scored_quantity(result)}), "
        f"insufficient inputs {counts.get('insufficient_inputs', 0)}, "
        f"not supported (v1) {counts.get('not_supported', 0)}, "
        f"runner errors {counts.get('runner_error', 0)}",
        "- Signed error convention: (predicted - measured) / measured x 100. "
        f"Outliers ({_cr_criterion_text()}) are flagged, never dropped; "
        "records excluded from the headline are aggregated in their own "
        "layer and the reason is kept distinct: `anomaly` means the "
        "EXPERIMENT is suspect (data quality), `out_of_scope` means HRMA's "
        "own declared model does not cover the configuration. An "
        "`out_of_scope` row is 'measured and withheld', not 'not measured'. "
        "Cells marked "
        "'single observation' report the signed error only (with n=1 the "
        "scatter columns would repeat that one number). Dependence column: "
        "'in-sample' entries are scored against the fit's own source data "
        "(an implementation check, not an independent validation); "
        "'weak-evidence' entries carry a curator caveat; u_meas is the "
        "median reported measurement uncertainty.",
        "",
        "| Motor | Quantity | Layer | N | Bias % | Median APE % | RMS % "
        "| Worst test | Dependence |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    cells = correlation_cells(result["statistics"])
    if not cells:
        lines.append("| - | no scored quantities | | | | | | | |")
    for cell in cells:
        sayilar = _row_numbers(cell)
        lines.append(
            f"| {cell['motor_type']} | {sayilar['quantity']} "
            f"| {cell['layer']} "
            f"| {cell['n']} | {cell['bias_percent']:+.1f} "
            f"| {sayilar['median_ape']} "
            f"| {sayilar['rms']} "
            f"| {cell['worst_test_id']} "
            # P10B2-01: satırın NEYE dayandığı (in-sample / zayıf kanıt /
            # ölçüm belirsizliği) yayımlanan tabloda durur.
            f"| {cell.get('dependence') or '-'} |")

    # P10B2-08: hükmü geri çekilen hücreler belgede SESSİZCE kaybolmaz.
    withheld = result["statistics"].get("non_converged_withheld_cells") or []
    for cell in withheld:
        lines.append(
            f"- Withheld (no converged run): {cell['motor_type']} "
            f"{cell['quantity']} ({cell['confidence_band']}, n={cell['n']})")
    non_conv = result["statistics"].get("non_converged_entries") or []
    if non_conv:
        ids = sorted({e["test_id"] for e in non_conv})
        lines.append(
            f"- Non-converged runs (flagged, kept): {len(non_conv)} scored "
            f"quantities from {len(ids)} record(s): " + ", ".join(ids))
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
