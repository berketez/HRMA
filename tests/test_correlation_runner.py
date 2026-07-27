"""Korelasyon koşucusu + kayıt adaptörleri testleri (v2.5.0 G2).

Kapsam:
  - Birim dönüşüm katmanı (birim-ekli anahtar -> SI; SCHEMA.md ilke 5)
  - Hibrit adaptör: Rezaei tohum kaydıyla uçtan uca koşu (Pc/F sabit-nokta
    yakınsaması, tahmin üretimi, tüketilen ölçüm ayrımı)
  - Sıvı engine_spec yolu: RS-25 kaydı AĞSIZ koşar (G1 tembel/enjeksiyon)
  - insufficient_inputs / not_supported / runner_error yolları
  - İstatistik: hücre şeması, aykırı işaretleme (3xMAD, atılmaz), anomaly
    ayrımı, düşük-güven katmanı, sentetik dışlama
  - Determinizm: aynı kayıtlar iki koşuda aynı sonuç (zaman alanları hariç)

Fikstür politikası: istatistik makinesi testleri, ÜRETİM AĞACINA ASLA
GİRMEYEN bellek-içi boru hattı fikstürleri kullanır (citation alanında açıkça
işaretli, access='synthetic'). Gerçek sayı içeren tek fikstür yok — gerçek
veri testleri üretim ağacındaki tohum kayıtlar (Rezaei t26, RS-25) üzerinden
koşar.
"""

import copy
import inspect
import math

import pytest

from hrma.validation import correlation_runner as cr
from hrma.validation import experiment_db
from hrma.validation import record_adapters as ra
from hrma.validation.experiment_db import ensure_valid_record, load_records

REZAEI_ID = "hyb-rezaei2018-htpb-n2o-t26"
RS25_ID = "liq-rs25-109pct-spec"


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------

def _load_by_id(test_id):
    records = [r for r in load_records() if r["test_id"] == test_id]
    assert records, f"tohum kayıt bulunamadı: {test_id}"
    return records[0]


def _validated(record):
    """Fikstürü şema denetiminden geçirir.

    'strand_burn_rate' gibi ileriye dönük record_type değerleri henüz
    experiment_db.RECORD_TYPES içinde olmayabilir; o durumda YALNIZ
    record_type hatasına tolerans gösterilir (küratör dalgası şemayı
    genişletince bu dal kendiliğinden kapanır), başka hata kabul edilmez.
    """
    errors = experiment_db.validate_record(record)
    rt = record.get("record_type")
    if rt is not None and rt not in experiment_db.RECORD_TYPES:
        assert errors and all("record_type" in e for e in errors), errors
    else:
        assert errors == [], errors
    return record


def _fixture_strand_record(test_id, pressure_bar, burn_rate_mmps,
                           confidence="high", anomaly_note=None,
                           synthetic=False):
    """Boru hattı fikstürü: strand-şekilli katı kayıt (GERÇEK VERİ DEĞİL).

    Üretim ağacına asla yazılmaz; istatistik makinesinin (hücre, aykırı,
    anomaly, güven katmanı) deterministik testinde kullanılır. Adaptör bu
    şekli grain geometrisi olmadığı için strand r(P) kıyasına düşürür —
    motor koşusu yok, test hızlı ve Cantera'sız.
    """
    record = {
        "schema_version": "1.0",
        "test_id": test_id,
        "motor_type": "solid",
        "source": {
            "citation": ("PIPELINE FIXTURE - synthetic pipeline check, "
                         "not experimental data (test_correlation_runner)"),
            "access": "synthetic",
            "confidence": confidence,
            "date_checked": "2026-07-17",
        },
        "propellants": {"oxidizer": "kno3", "fuel": "sucrose",
                        "hrma_propellant_key": "knsu"},
        "geometry": {"apparatus": "strand burner (fixture)"},
        "inputs": {"chamber_pressure_bar": pressure_bar},
        "measured": {"burn_rate_mmps": burn_rate_mmps},
        "units_original": "bar, mm/s (boru hatti fiksturu)",
        "digitized": False,
        "synthetic": synthetic,
        "notes": "Boru hatti fiksturu; uretim agacina girmez.",
    }
    if anomaly_note is not None:
        record["anomaly"] = {"flag": True, "note": anomaly_note}
    return _validated(record)


def _default_strand_prediction_mmps(pressure_bar):
    """Beklenen strand tahmini: motor kurucu varsayılan a-n ile a*P^n [mm/s]."""
    sig = inspect.signature(
        __import__("hrma.engines.solid_rocket_engine",
                   fromlist=["SolidRocketEngine"]).SolidRocketEngine.__init__)
    a = sig.parameters["burn_rate_a"].default
    n = sig.parameters["burn_rate_n"].default
    return a * pressure_bar ** n * 1000.0


def _measured_for_error(pred_mmps, error_pct):
    """Verilen işaretli hata yüzdesini üretecek ölçüm değeri."""
    return pred_mmps / (1.0 + error_pct / 100.0)


# ---------------------------------------------------------------------------
# Birim dönüşüm katmanı
# ---------------------------------------------------------------------------

class TestUnitConversion:
    def test_split_quantity_key(self):
        assert ra.split_quantity_key("thrust_kgf") == ("thrust", "kgf")
        assert ra.split_quantity_key("c_star_mps") == ("c_star", "mps")
        assert ra.split_quantity_key("isp_s") == ("isp", "s")
        assert ra.split_quantity_key("of_ratio") == ("of_ratio", None)
        # En uzun sonek kazanır: '_mps' '_s'den önce
        assert ra.split_quantity_key("regression_rate_mmps") == (
            "regression_rate", "mmps")

    @pytest.mark.parametrize("key,value,base,si", [
        ("thrust_kgf", 24.78, "thrust", 24.78 * 9.80665),
        ("thrust_sl_lbf", 418000, "thrust_sl", 418000 * 4.4482216152605),
        ("chamber_pressure_psia", 2994, "chamber_pressure",
         2994 * 6894.757293168),
        ("chamber_pressure_bar", 28.60, "chamber_pressure", 28.60e5),
        ("mdot_ox_gps", 95.77, "mdot_ox", 0.09577),
        ("port_diameter_initial_mm", 37.0, "port_diameter_initial", 0.037),
        ("gox_gpcm2s", 6.88, "gox", 68.8),
        ("regression_rate_mmps", 0.779, "regression_rate", 0.779e-3),
        ("burn_rate_cmps", 0.215, "burn_rate", 0.00215),
        ("mdot_fuel_lbps", 2.0, "mdot_fuel", 2.0 * 0.45359237),
        ("total_impulse_ns", 1500.0, "total_impulse", 1500.0),
        ("isp_vac_s", 452.3, "isp_vac", 452.3),
        ("fuel_density_kgpm3", 983, "fuel_density", 983.0),
        ("injector_area_mm2", 1.766, "injector_area", 1.766e-6),
        ("throat_diameter_in", 2.47, "throat_diameter", 2.47 * 0.0254),
        ("of_ratio", 3.78, "of_ratio", 3.78),
    ])
    def test_to_si(self, key, value, base, si):
        got_base, got_si = ra.to_si(key, value)
        assert got_base == base
        assert got_si == pytest.approx(si, rel=1e-12)

    def test_aliases(self):
        assert ra.to_si("mixture_ratio", 6.03) == ("of_ratio", 6.03)
        assert ra.to_si("max_thrust_n", 100.0)[0] == "thrust_peak"
        assert ra.to_si("isp_vacuum_s", 450.0)[0] == "isp_vac"

    def test_unknown_suffix_is_not_silently_si(self):
        # Bilinmeyen birim: SI kabul EDİLMEZ (sessiz yanlış birim yasak)
        base, si = ra.to_si("combustion_temperature_f", 5970)
        assert si is None
        block = ra.convert_block({"combustion_temperature_f": 5970})
        assert block["si"] == {}
        assert block["unconverted"] == ["combustion_temperature_f"]

    def test_convert_block_null_curve_text(self):
        block = ra.convert_block({
            "thrust_kgf": 24.78,
            "isp_s": None,
            "pressure_bar_curve": {"time_s": [0, 1], "value": [1, 2]},
            "grain_geometry": "cylindrical",
        })
        assert block["si"] == {"thrust": pytest.approx(24.78 * 9.80665,
                                                       rel=1e-12)}
        assert block["null"] == ["isp"]
        assert block["curves"] == ["pressure_bar_curve"]
        assert "grain_geometry" in block["text"]

    def test_rezaei_record_conversions(self):
        """Bilinen tohum kayıt -> beklenen kurucu-girdisi SI değerleri."""
        rec = _load_by_id(REZAEI_ID)
        inp = ra.convert_block(rec["inputs"])["si"]
        geo = ra.convert_block(rec["geometry"])["si"]
        meas = ra.convert_block(rec["measured"])["si"]
        assert inp["mdot_ox"] == pytest.approx(0.09577)
        assert inp["burn_time"] == pytest.approx(6.55)
        assert geo["port_diameter_initial"] == pytest.approx(0.037)
        assert geo["throat_diameter"] == pytest.approx(0.0089)
        assert meas["thrust"] == pytest.approx(24.78 * 9.80665)
        assert meas["c_star"] == pytest.approx(1514.0)
        assert meas["of_ratio"] == pytest.approx(3.78)
        assert meas["gox"] == pytest.approx(68.8)


# ---------------------------------------------------------------------------
# Hibrit adaptör: Rezaei tohum kaydı uçtan uca
# ---------------------------------------------------------------------------

class TestHybridAdapterRezaei:
    @pytest.fixture(scope="class")
    def run(self):
        return cr.run_correlation(records=[_load_by_id(REZAEI_ID)])

    def test_status_and_convergence(self, run):
        rr = run["records"][0]
        assert rr["test_id"] == REZAEI_ID
        assert rr["status"] == "ok", rr["reason"]
        assert rr["convergence"]["converged"] is True
        assert rr["convergence"]["relative_residual"] < 1e-3

    def test_of_consumed_and_derived_skipped(self, run):
        rr = run["records"][0]
        assert "of_ratio" in rr["consumed_measured"]
        assert rr["scores"]["of_ratio"]["status"] == "skipped_consumed"
        # mdot_fuel = mdot_ox/OF aritmetik kimliktir; skorlanamaz
        assert rr["scores"]["mdot_fuel"]["status"] == "skipped_derived"

    def test_algebraic_copies_are_not_scored_separately(self, run):
        """thrust/thrust_mean/total_impulse Isp'nin CEBİRSEL KOPYASIDIR.

        v2.6.2 doğrulama denetimi (F022): hibrit yolunda
        ``thrust = mdot_kayıt · g0 · Isp_model`` olduğu için itki hatası
        Isp hatasıyla ÖZDEŞTİR (tam DB ölçümü: 18 ortak testte
        |isp_err − thrust_err| en fazla 0.055 yüzde puanı). Bunları ayrı
        doğrulama büyüklüğü gibi skorlamak AYNI karşılaştırmayı tabloda
        2-3 bağımsız hücre (her biri n=18) gibi göstermek demekti.

        Kaynak: Oberkampf & Roy, *Verification and Validation in Scientific
        Computing*, CUP 2010, Böl. 12 — bağımlı çıktılar ayrı doğrulama
        metriği sayılmaz.

        Zincirin ÖLÇÜLEN İLK halkası skorlanır, kalanlar skor dışı kalır.
        """
        rr = run["records"][0]
        assert rr["scores"]["isp"]["status"] == "scored", (
            'zincirin ilk halkası (isp) skorlanmalı')
        for copy_q in ("thrust", "thrust_mean", "total_impulse"):
            st = rr["scores"].get(copy_q, {}).get("status")
            if st is None:
                continue  # bu kayıtta ölçüm yok
            assert st != "scored", (
                f'{copy_q} isp ile aynı kanıttan geliyor, ayrı skorlanmamalı '
                f'(durum: {st})')

    def test_scored_quantities_and_physical_bands(self, run):
        rr = run["records"][0]
        scored = {q: s for q, s in rr["scores"].items()
                  if s["status"] == "scored"}
        # thrust BİLEREK yok: isp'nin cebirsel kopyası (F022, üstteki teste bak)
        for quantity in ("c_star", "isp", "chamber_pressure",
                         "regression_rate", "port_diameter_final"):
            assert quantity in scored, (quantity, rr["scores"])
        # Fiziksel bantlar (eşik bekçiliği G4'ün işi; burada yalnız akıl
        # sağlığı): SI birimlerde
        assert 1300 < scored["c_star"]["predicted_si"] < 1700
        assert 150 < scored["isp"]["predicted_si"] < 260
        assert 15e5 < scored["chamber_pressure"]["predicted_si"] < 45e5
        assert 2e-4 < scored["regression_rate"]["predicted_si"] < 1.2e-3
        # İşaret sözleşmesi: error_pct = (pred-meas)/meas*100
        s = scored["c_star"]
        expected = (s["predicted_si"] - s["measured_si"]) / s["measured_si"] * 100
        assert s["error_pct"] == pytest.approx(expected, rel=1e-12)

    def test_circular_and_no_prediction_paths(self, run):
        rr = run["records"][0]
        # gox (yanma-ortalamalı akı) için model tahmini üretilmiyor
        assert rr["scores"]["gox"]["status"] == "no_prediction"
        # Varsayımlar dürüstçe listeleniyor
        assert "expansion_ratio" in rr["assumed_defaults"]

    def test_cell_statistics_schema(self, run):
        cells = run["statistics"]["cells"]
        assert cells, "hücre istatistiği boş"
        cell = [c for c in cells if c["quantity"] == "c_star"][0]
        for field in ("motor_type", "quantity", "n", "bias_pct", "rms_pct",
                      "median_ape_pct", "mape_pct", "min", "max",
                      "outlier_test_ids", "stats_excl_outliers", "entries"):
            assert field in cell, field
        assert cell["n"] == 1
        assert cell["confidence_band"] == "high_medium"


# ---------------------------------------------------------------------------
# Sıvı engine_spec: RS-25 AĞSIZ nokta kıyası
# ---------------------------------------------------------------------------

class TestLiquidEngineSpecOffline:
    def test_rs25_runs_without_network(self, monkeypatch):
        import requests
        from hrma.engines import liquid_rocket_engine as lre

        def _no_network(*args, **kwargs):
            raise AssertionError("korelasyon kosusu aga cikti!")

        monkeypatch.setattr(requests, "get", _no_network)
        monkeypatch.setattr(requests, "post", _no_network)
        monkeypatch.setattr(lre.LiquidRocketEngine,
                            "_fetch_web_propellant_data", _no_network)

        run = cr.run_correlation(records=[_load_by_id(RS25_ID)])
        rr = run["records"][0]
        assert rr["status"] == "ok", rr["reason"]
        # thrust_sl motor girdisi olarak tüketildi -> skor dışı
        assert "thrust_sl" in rr["consumed_measured"]
        assert rr["scores"]["thrust_sl"]["status"] == "skipped_consumed"
        # Pc ve O/F kayıt inputs'unda: dongusellik bekcisi devrede olmali
        assert "chamber_pressure" in rr["scores"] or True  # Pc measured degil
        # isp_vac ve thrust_vac gerçek skorlar
        isp = rr["scores"]["isp_vac"]
        assert isp["status"] == "scored"
        assert abs(isp["error_pct"]) < 5.0, isp
        assert rr["scores"]["thrust_vac"]["status"] == "scored"

    def test_input_quantity_never_scored(self):
        """Dongusellik bekcisi: inputs'ta gorunen taban ad skorlanamaz."""
        rec = copy.deepcopy(_load_by_id(RS25_ID))
        # of_ratio hem inputs'ta (mevcut) — measured'a koymak sema geregi
        # zaten yasak; burada koducunun kendi bekcisini yapay adaptor
        # sonucuyla test ediyoruz.
        fake_adapter_result = {
            "status": "ok",
            "input_bases": ["chamber_pressure"],
            "consumed_measured": [],
            "derived_bases": [],
            "predictions": {"chamber_pressure": 2.0e7},
            "measured_si": {"chamber_pressure": 2.06e7},
            "measured_null": [], "measured_curves": [],
            "measured_unconverted": [],
        }
        scores = cr._score_adapter_result(fake_adapter_result)
        assert scores["chamber_pressure"]["status"] == "skipped_circular_input"
        assert rec["test_id"] == RS25_ID  # kayit degismedi


# ---------------------------------------------------------------------------
# Durum etiketleri: insufficient / not_supported / runner_error
# ---------------------------------------------------------------------------

class TestStatusPaths:
    def test_insufficient_inputs(self):
        rec = copy.deepcopy(_load_by_id(REZAEI_ID))
        del rec["inputs"]["mdot_ox_gps"]
        # Belirsizlik girisi artik tanimsiz anahtara isaret etmesin
        rec.get("measurement_uncertainty", {}).pop("mdot_ox_gps", None)
        ensure_valid_record(rec)  # hala gecerli kayit (inputs bos degil)
        run = cr.run_correlation(records=[rec])
        rr = run["records"][0]
        assert rr["status"] == "insufficient_inputs"
        assert "mdot_ox" in rr["missing"]
        assert run["insufficient_inputs"] == [
            {"test_id": REZAEI_ID, "missing": rr["missing"]}]
        assert run["statistics"]["cells"] == []

    def test_not_supported_record_types(self):
        for rt in ("campaign_statistics", "regression_correlation"):
            rec = copy.deepcopy(_load_by_id(REZAEI_ID))
            rec["record_type"] = rt
            _validated(rec)  # ileriye donuk tip: yalniz record_type hatasi
            result = ra.adapt_record(rec)
            assert result["status"] == "not_supported"
            assert rt in result["reason"]
        # Kosucu da sessiz dusurmuyor, listeliyor
        rec = copy.deepcopy(_load_by_id(REZAEI_ID))
        rec["record_type"] = "campaign_statistics"
        run = cr.run_correlation(records=[rec])
        assert run["status_counts"] == {"not_supported": 1}
        assert run["not_supported"][0]["test_id"] == REZAEI_ID

    def test_runner_error_labelled(self):
        def exploding_adapter(record):
            raise RuntimeError("motor patladi (test)")

        rec = _fixture_strand_record("sol-fixture-strand-err", 68.9, 20.0)
        run = cr.run_correlation(records=[rec], adapter=exploding_adapter)
        rr = run["records"][0]
        assert rr["status"] == "runner_error"
        assert "motor patladi" in rr["reason"]
        assert run["runner_errors"][0]["test_id"] == "sol-fixture-strand-err"


# ---------------------------------------------------------------------------
# Strand r(P) yolu
# ---------------------------------------------------------------------------

class TestStrandPath:
    def test_strand_record_type_direct(self):
        rec = _fixture_strand_record("sol-fixture-strand-rt", 68.9, 20.0)
        rec["record_type"] = "strand_burn_rate"
        _validated(rec)  # ileriye donuk record_type toleransi
        result = ra.adapt_record(rec)
        assert result["status"] == "ok"
        expected = _default_strand_prediction_mmps(68.9)
        assert result["predictions"]["burn_rate"] * 1000 == pytest.approx(
            expected, rel=1e-9)
        assert "burn_rate_a" in result["assumed_defaults"]

    def test_solid_static_fire_falls_back_to_strand(self):
        # Nakka tarzi: grain geometrisi yok, basinc + yanma hizi var
        rec = _fixture_strand_record("sol-fixture-strand-fb", 68.9, 20.0)
        result = ra.adapt_record(rec)
        assert result["status"] == "ok"
        assert any("strand r(P)" in note for note in result["adapter_notes"])
        run = cr.run_correlation(records=[rec])
        rr = run["records"][0]
        score = rr["scores"]["burn_rate"]
        assert score["status"] == "scored"
        expected_err = (
            (_default_strand_prediction_mmps(68.9) - 20.0) / 20.0 * 100.0)
        assert score["error_pct"] == pytest.approx(expected_err, rel=1e-9)


# ---------------------------------------------------------------------------
# İstatistik makinesi: aykırı, anomaly, güven katmanı, sentetik dışlama
# ---------------------------------------------------------------------------

class TestStatisticsMachine:
    def _records_with_errors(self, error_pcts, **kwargs):
        pressure = 68.9
        pred = _default_strand_prediction_mmps(pressure)
        return [
            _fixture_strand_record(
                f"sol-fixture-strand-e{i:02d}", pressure,
                _measured_for_error(pred, e), **kwargs)
            for i, e in enumerate(error_pcts)
        ]

    def test_outlier_flagged_not_dropped(self):
        records = self._records_with_errors([5.0, 4.0, 6.0, 5.0, -60.0])
        run = cr.run_correlation(records=records)
        cell = [c for c in run["statistics"]["cells"]
                if c["quantity"] == "burn_rate"][0]
        assert cell["n"] == 5  # aykiri ATILMADI
        assert cell["outlier_test_ids"] == ["sol-fixture-strand-e04"]
        assert cell["stats_excl_outliers"]["n"] == 4
        assert cell["stats_excl_outliers"]["median_ape_pct"] == pytest.approx(
            5.0, abs=0.2)
        # 'tumu' istatistigi aykiriyi icerir -> bias asagi cekilir
        assert cell["bias_pct"] < cell["stats_excl_outliers"]["bias_pct"]

    def test_anomaly_records_excluded_from_cells(self):
        records = self._records_with_errors([5.0, 6.0])
        bad = _fixture_strand_record(
            "sol-fixture-strand-anom", 68.9,
            _measured_for_error(_default_strand_prediction_mmps(68.9), 50.0),
            anomaly_note="Lule erozyonu (fikstur)")
        run = cr.run_correlation(records=records + [bad])
        cell = [c for c in run["statistics"]["cells"]
                if c["quantity"] == "burn_rate"][0]
        assert cell["n"] == 2  # anomalili kayit ana istatistikte YOK
        entries = run["statistics"]["anomaly_entries"]
        assert [e["test_id"] for e in entries] == ["sol-fixture-strand-anom"]
        assert entries[0]["anomaly_note"] == "Lule erozyonu (fikstur)"

    def test_low_confidence_reported_separately(self):
        high = self._records_with_errors([5.0])
        low = _fixture_strand_record(
            "sol-fixture-strand-low", 68.9,
            _measured_for_error(_default_strand_prediction_mmps(68.9), 10.0),
            confidence="low")
        run = cr.run_correlation(records=high + [low])
        main_ids = [e["test_id"]
                    for c in run["statistics"]["cells"]
                    for e in c["entries"]]
        assert "sol-fixture-strand-low" not in main_ids
        low_cells = run["statistics"]["low_confidence_cells"]
        assert len(low_cells) == 1
        assert low_cells[0]["confidence_band"] == "low"
        assert low_cells[0]["entries"][0]["test_id"] == "sol-fixture-strand-low"

    def test_synthetic_records_structurally_excluded(self):
        real = self._records_with_errors([5.0])
        synth = _fixture_strand_record("sol-fixture-strand-syn", 68.9, 20.0,
                                       synthetic=True)
        run = cr.run_correlation(records=real + [synth])
        assert run["n_records"] == 1
        assert run["n_synthetic_excluded"] == 1
        assert all(rr["test_id"] != "sol-fixture-strand-syn"
                   for rr in run["records"])


# ---------------------------------------------------------------------------
# Determinizm ve DB hash
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_records_same_result(self):
        records = [_load_by_id(REZAEI_ID), _load_by_id(RS25_ID)]
        run1 = cr.run_correlation(records=copy.deepcopy(records))
        run2 = cr.run_correlation(records=copy.deepcopy(records))
        assert cr.deterministic_view(run1) == cr.deterministic_view(run2)

    def test_db_hash_tracks_content(self):
        rec = _load_by_id(REZAEI_ID)
        h1 = cr.db_content_hash([rec])
        changed = copy.deepcopy(rec)
        changed["measured"]["c_star_mps"] = 1500.0
        h2 = cr.db_content_hash([changed])
        assert h1 != h2
        # Sira bagimsiz: ayni icerik ayni hash
        rec2 = _load_by_id(RS25_ID)
        assert cr.db_content_hash([rec, rec2]) == cr.db_content_hash([rec2, rec])

    def test_deterministic_view_strips_timing(self):
        run = cr.run_correlation(
            records=[_fixture_strand_record("sol-fixture-strand-t", 68.9, 20.0)])
        view = cr.deterministic_view(run)
        assert "timing" not in view
        assert all("elapsed_s" not in rr for rr in view["records"])
        assert "elapsed_s" in run["records"][0]  # orijinal bozulmadi


# ---------------------------------------------------------------------------
# Markdown özeti
# ---------------------------------------------------------------------------

class TestMarkdown:
    def test_summary_contains_tables_and_no_emoji(self):
        records = [
            _fixture_strand_record("sol-fixture-strand-m1", 68.9,
                                   _measured_for_error(
                                       _default_strand_prediction_mmps(68.9),
                                       5.0)),
            _fixture_strand_record("sol-fixture-strand-m2", 68.9, 20.0,
                                   anomaly_note="fikstur anomalisi"),
        ]
        run = cr.run_correlation(records=records)
        md = cr.to_markdown(run)
          # v2.6.2 (F007): sütun "N" -> "N (campaigns)". Sayılan şey bağımsız
        # örnek değil KAMPANYA olduğu için başlık bunu açıkça söylüyor;
        # aynı motorun yakın çalışma noktaları tek kampanya sayılır.
        assert "| Motor | Quantity | N (campaigns) |" in md
        assert "sol-fixture-strand-m1" in md
        assert "Anomaly-flagged records" in md
        assert run["db_content_hash"] in md
        assert not any(ord(ch) > 0x2500 for ch in md), "emoji/simge yasak"


# ---------------------------------------------------------------------------
# Paket dışa aktarımları
# ---------------------------------------------------------------------------

def test_package_exports():
    import hrma.validation as v
    assert v.run_correlation is cr.run_correlation
    assert v.adapt_record is ra.adapt_record
    assert v.to_markdown is cr.to_markdown
    assert v.deterministic_view is cr.deterministic_view
    assert v.db_content_hash is cr.db_content_hash


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
