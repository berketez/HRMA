"""Paper-kalite korelasyon rapor ureticisi testleri (v2.5.0 G4).

Kapsam:
  - Sahte/mini ``run_correlation`` sonucu (run_correlation cikti semasina uygun,
    2-3 hucre + anomaly + low + aykiri girisli) uzerinde ``generate_report``:
      * report.md tablo satirlarini icerir, emoji YOK
      * parite PNG'leri (n>=3 hucreler) ve error_distribution.png olusur
      * report.pdf olusur ve gecerli PDF baslar
      * iki kosunun md'si BIREBIR ayni (determinizm; sabit timestamp ile)
  - Katman toplama (main/low/anomaly) correlation_runner._aggregate ile tutarli
  - n<3 hucre parite figuru URETMEZ

Fikstur politikasi: TAM 136-kayit kosusu YAPILMAZ (dakikalar surer). Bellek-ici
sahte sonuc sozlugu, gercek istatistik makinesiyle (cr._aggregate) tutarli
kurulur; boylece parite noktalari ile hucre outlier_test_ids birbirini tutar.
"""

import copy
import os

import pytest

from hrma.validation import correlation_runner as cr
from hrma.validation import paper_report as pr

FIXED_TS = "2026-07-18T00:00:00"


# ---------------------------------------------------------------------------
# Sahte sonuc kurucu
# ---------------------------------------------------------------------------

def _score(predicted, measured):
    return {
        "status": "scored",
        "predicted_si": float(predicted),
        "measured_si": float(measured),
        "error_pct": (predicted - measured) / measured * 100.0,
    }


def _rec(test_id, motor_type, confidence, scores,
         anomaly=False, anomaly_note=None):
    return {
        "test_id": test_id,
        "motor_type": motor_type,
        "record_type": "static_fire",
        "confidence": confidence,
        "anomaly": anomaly,
        "anomaly_note": anomaly_note,
        "status": "ok",
        "reason": None,
        "missing": [],
        "consumed_measured": [],
        "derived_bases": [],
        "assumed_defaults": {},
        "adapter_notes": [],
        "convergence": None,
        "scores": scores,
        "elapsed_s": 0.0,
    }


def _scored_for_error(measured, error_pct):
    """Verilen isaretli hatayi uretecek tahmin degerini kurar."""
    predicted = measured * (1.0 + error_pct / 100.0)
    return _score(predicted, measured)


def _fake_result():
    """run_correlation cikti semasina uygun mini sonuc.

    Hucreler:
      - hybrid/c_star: 4 main nokta, biri buyuk aykiri (~+40%) -> MAD isaretler
        (n>=3 -> parite figuru), + 1 anomaly kayit (ayni buyukluk)
      - hybrid/isp: 3 main nokta (n>=3 -> parite figuru)
      - solid/burn_rate: 2 main + 1 low (n<3 -> parite figuru YOK)
    """
    c_star_meas = 1500.0
    isp_meas = 250.0
    br_meas = 0.006  # m/s

    records = [
        # hybrid c_star (main, biri aykiri)
        _rec("hyb-a", "hybrid", "high",
             {"c_star": _scored_for_error(c_star_meas, 3.0)}),
        _rec("hyb-b", "hybrid", "high",
             {"c_star": _scored_for_error(c_star_meas, 4.0)}),
        _rec("hyb-c", "hybrid", "medium",
             {"c_star": _scored_for_error(c_star_meas, 5.0)}),
        _rec("hyb-d", "hybrid", "high",
             {"c_star": _scored_for_error(c_star_meas, 40.0)}),  # aykiri
        # hybrid c_star anomaly (ana istatistige girmez)
        _rec("hyb-anom", "hybrid", "high",
             {"c_star": _scored_for_error(c_star_meas, 60.0)},
             anomaly=True, anomaly_note="Nozzle erosion (fixture)"),
        # hybrid isp (main)
        _rec("hyb-e", "hybrid", "high",
             {"isp": _scored_for_error(isp_meas, 2.0)}),
        _rec("hyb-f", "hybrid", "medium",
             {"isp": _scored_for_error(isp_meas, -3.0)}),
        _rec("hyb-g", "hybrid", "high",
             {"isp": _scored_for_error(isp_meas, 1.0)}),
        # solid burn_rate (2 main + 1 low -> hucre n=2, parite yok)
        _rec("sol-a", "solid", "high",
             {"burn_rate": _scored_for_error(br_meas, 6.0)}),
        _rec("sol-b", "solid", "high",
             {"burn_rate": _scored_for_error(br_meas, -4.0)}),
        _rec("sol-low", "solid", "low",
             {"burn_rate": _scored_for_error(br_meas, 10.0)}),
    ]

    stats = cr._aggregate(records)
    status_counts = {"ok": len(records)}
    return {
        "runner_version": cr.RUNNER_VERSION,
        "adapter_version": "1",
        "db_content_hash": "deadbeef" * 8,  # 64 hex, sabit
        "n_records": len(records),
        "n_synthetic_excluded": 0,
        "records": records,
        "statistics": stats,
        "status_counts": status_counts,
        "not_supported": [],
        "insufficient_inputs": [],
        "runner_errors": [],
        "timing": {"total_s": 0.0},
    }


# ---------------------------------------------------------------------------
# Katman toplama
# ---------------------------------------------------------------------------

class TestCollectPoints:
    def test_layer_split_matches_aggregate(self):
        result = _fake_result()
        points = pr._collect_points(result)
        cs = points[("hybrid", "c_star")]
        # main: 4 kayit (high/high/medium/high), anomaly: 1, low: 0
        assert len(cs["main"]) == 4
        assert len(cs["anomaly"]) == 1
        assert cs["anomaly"][0]["test_id"] == "hyb-anom"
        # aykiri isaretli (hyb-d, +40%)
        outliers = [p["test_id"] for p in cs["main"] if p["outlier"]]
        assert outliers == ["hyb-d"]
        # solid burn_rate: main 2, low 1
        br = points[("solid", "burn_rate")]
        assert len(br["main"]) == 2
        assert len(br["low"]) == 1

    def test_points_have_predicted_measured(self):
        result = _fake_result()
        points = pr._collect_points(result)
        p = points[("hybrid", "isp")]["main"][0]
        assert "predicted" in p and "measured" in p
        assert p["measured"] > 0 and p["predicted"] > 0


# ---------------------------------------------------------------------------
# Rapor uretimi
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_files_created(self, tmp_path):
        result = _fake_result()
        info = pr.generate_report(result=result, out_dir=str(tmp_path),
                                  timestamp=FIXED_TS)
        assert os.path.exists(info["markdown"])
        assert os.path.exists(info["pdf"])
        assert os.path.exists(info["error_distribution"])
        # n>=3 hucreler: hybrid/c_star, hybrid/isp -> 2 parite figuru
        assert info["n_parity_figures"] == 2
        names = sorted(os.path.basename(p) for p in info["parity_figures"])
        assert names == ["parity_hybrid_c_star.png", "parity_hybrid_isp.png"]
        for path in info["parity_figures"]:
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0

    def test_solid_cell_below_threshold_has_no_parity(self, tmp_path):
        result = _fake_result()
        info = pr.generate_report(result=result, out_dir=str(tmp_path),
                                  timestamp=FIXED_TS)
        names = [os.path.basename(p) for p in info["parity_figures"]]
        assert "parity_solid_burn_rate.png" not in names

    def test_pdf_is_valid(self, tmp_path):
        result = _fake_result()
        info = pr.generate_report(result=result, out_dir=str(tmp_path),
                                  timestamp=FIXED_TS)
        with open(info["pdf"], "rb") as fh:
            head = fh.read(5)
        assert head == b"%PDF-", "gecerli PDF basligi yok"

    def test_markdown_contains_tables_and_no_emoji(self, tmp_path):
        result = _fake_result()
        info = pr.generate_report(result=result, out_dir=str(tmp_path),
                                  timestamp=FIXED_TS)
        md = open(info["markdown"], encoding="utf-8").read()
        # Detay tablo basligi (to_markdown'dan)
          # v2.6.2 (F007): sütun "N" -> "N (campaigns)". Sayılan şey bağımsız
        # örnek değil KAMPANYA olduğu için başlık bunu açıkça söylüyor;
        # aynı motorun yakın çalışma noktaları tek kampanya sayılır.
        assert "| Motor | Quantity | N (campaigns) |" in md
        # Hucre satiri: motor tipi + buyukluk
        assert "hybrid" in md
        assert "c_star" in md
        assert "isp" in md
        # DB hash raporda
        assert result["db_content_hash"] in md
        # Figur referanslari
        assert "parity_hybrid_c_star.png" in md
        assert "error_distribution.png" in md
        # Katman aciklamalari + yorum iskeleti
        assert "Confidence layers" in md
        assert "Author commentary" in md
        assert "narrative added by authors" in md
        # Anomaly ayri raporlaniyor (detay tabloda)
        assert "Anomaly-flagged" in md
        # Emoji/simge yok
        assert not any(ord(ch) > 0x2500 for ch in md), "emoji/simge yasak"

    def test_deterministic_markdown(self, tmp_path):
        result = _fake_result()
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        info1 = pr.generate_report(result=copy.deepcopy(result),
                                   out_dir=str(out1), timestamp=FIXED_TS)
        info2 = pr.generate_report(result=copy.deepcopy(result),
                                   out_dir=str(out2), timestamp=FIXED_TS)
        md1 = open(info1["markdown"], encoding="utf-8").read()
        md2 = open(info2["markdown"], encoding="utf-8").read()
        assert md1 == md2, "ayni sonuc + ayni timestamp -> ayni md olmali"

    def test_default_out_dir_not_required(self, tmp_path, monkeypatch):
        """out_dir verilmezse default docs/correlation_report; burada tmp."""
        result = _fake_result()
        target = tmp_path / "nested" / "report_dir"
        info = pr.generate_report(result=result, out_dir=str(target),
                                  timestamp=FIXED_TS)
        assert os.path.isdir(info["out_dir"])
        assert info["out_dir"] == os.path.abspath(str(target))


# ---------------------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_use_log_detects_wide_span(self):
        assert pr._use_log([1.0, 1000.0]) is True
        assert pr._use_log([1.0, 2.0]) is False
        # negatif/sifir -> log kullanma
        assert pr._use_log([-1.0, 100.0]) is False
        assert pr._use_log([0.0, 100.0]) is False

    def test_slug_is_filesystem_safe(self):
        assert pr._slug("hybrid") == "hybrid"
        assert pr._slug("c_star") == "c_star"
        assert pr._slug("Motor Type!") == "motor_type"

    def test_unit_label_known_and_unknown(self):
        assert pr._unit_label("thrust") == "N"
        assert pr._unit_label("c_star") == "m/s"
        assert pr._unit_label("of_ratio") == ""
        assert pr._unit_label("totally_unknown_quantity") == "SI"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
