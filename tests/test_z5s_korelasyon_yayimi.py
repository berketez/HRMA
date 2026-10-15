"""ÖH Z5S / P10-Z5S-C — hrma/validation yayım dürüstlüğü bekçileri.

Kalemler: P10B2-09, P10B2-08, P10B2-02, P10B2-03, P10B2-10, P10B2-15,
P10B2-07, P10B2-13.

ORTAK SUÇLAMA: modülün KENDİ ilan ettiği dürüstlük alanları ya
serileştiricide düşüyor, ya bayat/yanlış basılıyor, ya da doğrulayıcının
kendisi null girdide çöküp doğru teşhisini yutuyor. Bu dosya UÇ + YAYIM
katmanını ölçer.

BU BEKÇİ NEYİ YİNELEMEZ: ``tests/test_fazb_serilestirici_esligi.py`` zaten
``status_report._flatten_cell``in hücre düzeyinde düşürdüğü alanları ölçüyor
ve o kusurun BOYUNU (iç 20 / yayım 9) donduruyor — bu dosya hücre şekline
DOKUNMAZ, uç gövdesinin (``_correlation_report_body``) ve markdown/belge
üreticilerinin ne yayımladığını ölçer.

FİKSTÜR POLİTİKASI: istatistik makinesi bellek-içi boru hattı fikstürleriyle
sınanır (``access='synthetic'``, üretim ağacına asla girmez —
``test_correlation_runner.py`` ile aynı politika). Gerçek sayı iddiaları
(birim soneki çözülemeyen AMROC kayıtları, RL10'un sıfır-büyüklük skorlayan
beş kaydı) ÜRETİM kayıtları üzerinden ölçülür.
"""

import copy
import inspect
import json

import pytest

from hrma.validation import correlation_runner as cr
from hrma.validation import record_adapters as ra
from hrma.validation import status_report as sr
from hrma.validation.experiment_db import load_records

# --- Ölçülen üretim kayıtları (P10B2-02 / P10B2-10 çapaları) ---------------

#: ``mdot_ox`` kayıtta DURUYOR ama soneki (``lbmps``) UNIT_TO_SI'de yok.
BIRIM_COZULEMEYEN = {
    "hyb-amroc1993-htpb-lox-dm01-b1": "mdot_ox_lbmps",
    "hyb-amroc1993-htpb-lox-dm01-b2": "mdot_ox_lbmps",
    "hyb-amroc1993-htpb-lox-dm01-b3": "mdot_ox_lbmps",
    "hyb-amroc1993-htpb-lox-dm01-b4": "mdot_ox_lbmps",
    "hyb-knowles2004-htpb-lox-htt-002": "mdot_ox_max_lbmps",
}


@pytest.fixture(scope="module")
def uretim_kayitlari():
    return {r["test_id"]: r for r in load_records()}


# ---------------------------------------------------------------------------
# Fikstürler: strand boru hattı (Cantera'sız, hızlı)
# ---------------------------------------------------------------------------

def _strand_fikstur(test_id, pressure_bar=68.9, burn_rate_mmps=9.0,
                    confidence="high"):
    return {
        "schema_version": "1.0",
        "test_id": test_id,
        "motor_type": "solid",
        "source": {
            "citation": ("PIPELINE FIXTURE - synthetic pipeline check, "
                         "not experimental data (test_z5s_korelasyon_yayimi)"),
            "access": "synthetic",
            "confidence": confidence,
            "date_checked": "2026-08-28",
        },
        "propellants": {"oxidizer": "kno3", "fuel": "sucrose",
                        "hrma_propellant_key": "knsu"},
        "geometry": {"apparatus": "strand burner (fixture)"},
        "inputs": {"chamber_pressure_bar": pressure_bar},
        "measured": {"burn_rate_mmps": burn_rate_mmps},
        "units_original": "bar, mm/s (boru hatti fiksturu)",
        "digitized": False,
        "synthetic": False,
        "notes": "Boru hatti fiksturu; uretim agacina girmez.",
    }


def _yakinsamayan_adaptor(non_converged_ids, residual=2.5e-3, iterations=12):
    """Gerçek adaptörü sarar, adı verilen kayıtlara converged=False takar.

    Sahte SAYI üretmez: tahminler/ölçümler gerçek adaptörden gelir, yalnız
    çözücünün kendi yakınsama bayrağı deneysel olarak False'a çekilir —
    hibrit sabit-nokta döngüsünü Cantera ile koşturmadan aynı durumu kurmanın
    tek dürüst yolu.
    """
    # Taban adaptör ÜRETİM fonksiyonudur ve sarmalayıcı kurulurken bağlanır:
    # monkeypatch ile ``ra.adapt_record`` değiştirildiğinde sarmalayıcı kendi
    # kendini çağırmasın (sonsuz özyineleme).
    taban = ra.adapt_record

    def adaptor(record):
        sonuc = taban(record)
        if record.get("test_id") in non_converged_ids:
            sonuc["convergence"] = {"converged": False,
                                    "iterations": iterations,
                                    "relative_residual": residual}
        else:
            sonuc["convergence"] = {"converged": True, "iterations": 3,
                                    "relative_residual": 1e-9}
        return sonuc
    return adaptor


# ===========================================================================
# P10B2-08 — yakınsamayan koşu ARTIK skordan ayrışıyor ve yayımda görünüyor
# ===========================================================================

class TestYakinsamaHukmu:
    """ÖLÇÜLDÜ (tam DB, 2026-08-28): 48 kayıt ``convergence`` bloğu üretiyor,
    biri (hyb-karabeyoglu2003-paraffin-gox-t4p-04, bağıl kalıntı 1,389e-4 >
    tolerans 1e-4) YAKINSAMIYOR — ve skorlama yolu bu bayrağı hiç
    okumuyordu."""

    def test_karisik_hucrede_yakinsamayan_giris_adiyla_yayimlanir(self):
        kayitlar = [_strand_fikstur("sol-fixture-nc-a"),
                    _strand_fikstur("sol-fixture-nc-b")]
        kosu = cr.run_correlation(
            records=kayitlar,
            adapter=_yakinsamayan_adaptor({"sol-fixture-nc-a"}))
        ist = kosu["statistics"]
        yakinsamayan = ist["non_converged_entries"]
        assert yakinsamayan, (
            "yakınsamayan koşu hiçbir çıktı kanalına taşınmıyor — "
            "correlation_runner._is_non_converged okunmuyor olabilir")
        assert {e["test_id"] for e in yakinsamayan} == {"sol-fixture-nc-a"}
        giris = yakinsamayan[0]
        assert giris["relative_residual"] == pytest.approx(2.5e-3)
        assert giris["iterations"] == 12
        # Karışık hücre: yakınsayan kanıt VAR, hücre yayımlanmaya devam eder.
        assert ist["cells"], "karışık hücre gereksiz yere geri çekildi"
        assert ist["non_converged_withheld_cells"] == []

    def test_tumu_yakinsamayan_hucrenin_hukmu_geri_cekilir(self):
        """Fail-closed: hüküm yakınsamamış koşulardan KAZANILAMAZ.

        Z4'te FEA için verilen kuralın kardeşi — sayı silinmez, hüküm geri
        çekilir: hücre üretilmez ama girişler ``non_converged_entries``
        listesinde adıyla durur."""
        kayitlar = [_strand_fikstur("sol-fixture-nc-c"),
                    _strand_fikstur("sol-fixture-nc-d")]
        kosu = cr.run_correlation(
            records=kayitlar,
            adapter=_yakinsamayan_adaptor({"sol-fixture-nc-c",
                                           "sol-fixture-nc-d"}))
        ist = kosu["statistics"]
        assert ist["cells"] == [], (
            "girişlerinin TAMAMI yakınsamamış hücre hâlâ yayımlanıyor — "
            "yakınsamamış koşudan hüküm kazanılıyor (fail-open)")
        geri_cekilen = ist["non_converged_withheld_cells"]
        assert len(geri_cekilen) == 1, geri_cekilen
        assert geri_cekilen[0]["motor_type"] == "solid"
        assert geri_cekilen[0]["quantity"] == "burn_rate"
        assert geri_cekilen[0]["n"] == 2
        # Sayı SİLİNMEDİ: iki giriş de listede duruyor.
        assert len(ist["non_converged_entries"]) == 2

    def test_geri_cekme_KATMAN_BASINA_karar_verilir(self):
        """Aynı (motor, büyüklük) hem main hem low katmanında olabilir.

        Tek bir sayaçla karar verilirse karışık main hücresi, low
        katmanındaki yakınsamayan girişlerin sayısı yüzünden yanlışlıkla
        geri çekilir. Karar giriş düzeyinde, hücre bandı içinde verilir."""
        kayitlar = [
            _strand_fikstur("sol-fixture-band-a", confidence="high"),
            _strand_fikstur("sol-fixture-band-b", confidence="high",
                            burn_rate_mmps=9.5),
            _strand_fikstur("sol-fixture-band-c", confidence="low",
                            burn_rate_mmps=10.0),
        ]
        kosu = cr.run_correlation(
            records=kayitlar,
            adapter=_yakinsamayan_adaptor({"sol-fixture-band-a",
                                           "sol-fixture-band-c"}))
        ist = kosu["statistics"]
        assert [(c["quantity"], c["n"]) for c in ist["cells"]] == [
            ("burn_rate", 2)], "karışık main hücresi haksız yere geri çekildi"
        assert ist["low_confidence_cells"] == []
        assert [c["confidence_band"] for c
                in ist["non_converged_withheld_cells"]] == ["low"]

    def test_ic_bayrak_yayimlanan_girise_sizmiyor(self):
        """``_non_converged`` bir İÇ muhasebe alanıdır; hücre girişlerinin
        yayımlanan şekli değişmemeli (serileştirici sözleşmesi)."""
        kosu = cr.run_correlation(
            records=[_strand_fikstur("sol-fixture-nc-h")],
            adapter=_yakinsamayan_adaptor(set()))
        giris = kosu["statistics"]["cells"][0]["entries"][0]
        assert "_non_converged" not in giris, giris

    def test_markdown_yakinsamayan_bolumu_basiyor(self):
        kayitlar = [_strand_fikstur("sol-fixture-nc-e"),
                    _strand_fikstur("sol-fixture-nc-f")]
        kosu = cr.run_correlation(
            records=kayitlar,
            adapter=_yakinsamayan_adaptor({"sol-fixture-nc-e"}))
        md = cr.to_markdown(kosu)
        assert "## Non-converged runs (flagged, kept)" in md, (
            "markdown özeti yakınsamayan koşuyu anmıyor")
        assert "sol-fixture-nc-e" in md
        assert not any(ord(ch) > 0x2500 for ch in md), "emoji/simge yasak"

    def test_bilinmeyen_yakinsama_yakinsamamis_sayilmaz(self):
        """``convergence`` bloğu ÜRETMEYEN adaptör (strand/sıvı yolu)
        suçlanamaz: bilinmiyor ≠ yakınsamadı (uydurma yasağı)."""
        kosu = cr.run_correlation(
            records=[_strand_fikstur("sol-fixture-nc-g")])
        assert kosu["records"][0]["convergence"] is None
        assert kosu["statistics"]["non_converged_entries"] == []
        assert kosu["statistics"]["non_converged_withheld_cells"] == []
        assert kosu["statistics"]["cells"], "hüküm gereksiz yere geri çekildi"


# ===========================================================================
# P10B2-02 — 'insufficient_inputs' GEREKÇESİ iki sınıfı ayırıyor
# ===========================================================================

class TestYetersizGirdiGerekcesi:
    """ÖLÇÜLDÜ: beş üretim kaydında gerekçe "gerekli girdiler eksik: ...
    mdot_ox ..." diyordu; değer kayıtta duruyor (``mdot_ox_lbmps: 619``),
    eksik olan şey sonekin birim tablosunda BULUNMAMASI."""

    @pytest.mark.parametrize("test_id", sorted(BIRIM_COZULEMEYEN))
    def test_birim_cozulemeyen_kayit_dogru_sinifi_soyluyor(
            self, uretim_kayitlari, test_id):
        anahtar = BIRIM_COZULEMEYEN[test_id]
        rec = uretim_kayitlari.get(test_id)
        assert rec is not None, f"üretim kaydı yok: {test_id} (bekçi öncülü)"
        sonuc = ra.adapt_record(rec)
        assert sonuc["status"] == "insufficient_inputs"
        # 1) 'missing' listesi BİREBİR aynı kalır (mevcut sözleşme).
        assert "mdot_ox" in sonuc["missing"]
        # 2) Gerekçe artık "mdot_ox eksik" DEMİYOR.
        eksik_cumlesi = sonuc["reason"].split(";")[0]
        assert "mdot_ox" not in eksik_cumlesi, (
            f"gerekçe hâlâ mdot_ox'u 'eksik' sayıyor: {sonuc['reason']}")
        # 3) İkinci sınıf ADIYLA ve kayıttaki ANAHTARLA yazılıyor.
        assert "birim soneki cozulemedi" in sonuc["reason"], sonuc["reason"]
        assert anahtar in sonuc["reason"], sonuc["reason"]
        # 4) Makine-okur ayrıntı.
        detay = {d["field"]: d for d in sonuc["missing_detail"]}
        assert detay["mdot_ox"]["reason"] == "unit_unresolved"
        assert anahtar in detay["mdot_ox"]["record_keys"]

    def test_gercekten_yok_olan_alan_hala_value_absent(self,
                                                       uretim_kayitlari):
        """Karşı-örnek: birim sorunu OLMAYAN eksiklik eski sınıfta kalır
        (yeni sınıf her şeyi yutmuyor)."""
        rec = copy.deepcopy(uretim_kayitlari["hyb-rezaei2018-htpb-n2o-t26"])
        rec["inputs"].pop("mdot_ox_gps", None)
        rec.get("measurement_uncertainty", {}).pop("mdot_ox_gps", None)
        sonuc = ra.adapt_record(rec)
        assert sonuc["status"] == "insufficient_inputs"
        detay = {d["field"]: d for d in sonuc["missing_detail"]}
        assert detay["mdot_ox"]["reason"] == "value_absent"
        assert detay["mdot_ox"]["record_keys"] == []
        assert sonuc["reason"].startswith(
            "kayitta motor kosusu icin gerekli girdiler eksik:")

    def test_birim_tablosuna_sonek_EKLENMEDI(self):
        """Kapsam bekçisi: bu onarım birim tablosuna dokunmaz.

        ``lbmps`` eklemek beş kaydı koşturur ve yayımlanan istatistiği
        değiştirir (ayrı kalem, P10B2-11). Bu bekçi kapsam kaymasını
        yakalar."""
        assert "lbmps" not in ra.UNIT_TO_SI, (
            "birim tablosuna 'lbmps' eklenmiş — yayımlanan korelasyon "
            "istatistiği değişmiş olabilir; bilinçli karar (P10B2-11) "
            "gerektirir")


# ===========================================================================
# P10B2-03 — strand a-n BEYANI, KULLANILAN katsayıdan üretiliyor
# ===========================================================================

class TestStrandBeyanEsitligi:
    """ÖLÇÜLDÜ (50 bar, knsu): beyan edilen 0,005/0,35 ile motorun gerçekte
    çözdüğü 0,0022334/0,35 arasında hızda %55,3 fark vardı."""

    def test_beyan_edilen_an_tahmini_URETIYOR(self):
        rec = _strand_fikstur("sol-fixture-an-1", pressure_bar=50.0)
        sonuc = ra.adapt_record(rec)
        assert sonuc["status"] == "ok"
        a = sonuc["assumed_defaults"]["burn_rate_a"]
        n = sonuc["assumed_defaults"]["burn_rate_n"]
        # EŞİTLİK sınaması: beyan edilen a-n, yayımlanan tahmini birebir
        # üretmeli. Eski kod sabit 0,005 beyan edip başka bir sayıyla
        # koşuyordu; bu satır o hâlde kırılır.
        assert sonuc["predictions"]["burn_rate"] == pytest.approx(
            a * 50.0 ** n, rel=1e-12), (
            f"beyan edilen a-n ({a}, {n}) yayımlanan tahmini üretmiyor — "
            "kullanılmayan varsayımın beyanı dürüstlük ihlalidir")

    def test_beyan_motorun_cozdugu_katsayidir(self):
        from hrma.engines.solid_rocket_engine import SolidRocketEngine
        motor = SolidRocketEngine(propellant_type="knsu",
                                  chamber_pressure=50.0)
        sonuc = ra.adapt_record(_strand_fikstur("sol-fixture-an-2",
                                                pressure_bar=50.0))
        assert sonuc["assumed_defaults"]["burn_rate_a"] == pytest.approx(
            float(motor.a), rel=1e-12)
        assert sonuc["assumed_defaults"]["burn_rate_n"] == pytest.approx(
            float(motor.n), rel=1e-12)

    def test_kaynakta_elle_yazilmis_an_sabiti_kalmadi(self):
        """Kaynak çapası: strand dalında 0.005 / 0.35 literalleri gitmiş
        olmalı (aynı kusurun geri sızmasına karşı)."""
        kaynak = inspect.getsource(ra._run_strand)
        for literal in ("0.005", "0.35"):
            assert f'"burn_rate_a"] = {literal}' not in kaynak
            assert f'"burn_rate_n"] = {literal}' not in kaynak


# ===========================================================================
# P10B2-10 — "scored N" başlığı artık şişik değil
# ===========================================================================

def _sahte_kosu_sifir_buyuklukle():
    """İki 'ok' kayıt: biri gerçekten skorluyor, biri SIFIR büyüklük.

    Üretimdeki karşılığı ölçüldü: 98 'ok' kaydın 6'sı sıfır büyüklük
    skorluyor (RL10-A-3-3A'nın beş gerçek ateşleme kaydı + F-1 spec)."""
    return {
        "runner_version": "1", "adapter_version": "1",
        "db_content_hash": "0" * 64,
        "n_records": 2,
        "status_counts": {"ok": 2},
        "records": [
            {"test_id": "skorlayan", "status": "ok",
             "scores": {"burn_rate": {"status": "scored", "error_pct": 3.0}}},
            {"test_id": "sifir-buyukluk", "status": "ok",
             "scores": {"isp": {"status": "skipped_consumed"},
                        "thrust": {"status": "skipped_derived"}}},
        ],
        "statistics": {"cells": [], "low_confidence_cells": [],
                       "anomaly_entries": [], "non_converged_entries": [],
                       "non_converged_withheld_cells": []},
    }


class TestSkorlandiBasligi:
    def test_baslik_iki_sayiyi_AYRI_yaziyor(self):
        sonuc = _sahte_kosu_sifir_buyuklukle()
        metin = sr.generate_status_section(sonuc, generated_on="2026-08-28")
        assert "adapter ok 2" in metin, metin
        assert "with at least one scored quantity: 1" in metin, metin
        # Eski şişik ifade geri gelemez.
        assert "scored 2," not in metin, (
            "başlık yine 'scored 2' diyor — durum sayımı tabloya katkı gibi "
            "yayımlanıyor")

    def test_sayaci_sifir_buyuklukleri_saymiyor(self):
        assert sr._records_with_scored_quantity(
            _sahte_kosu_sifir_buyuklukle()) == 1

    def test_uretimde_sifir_buyuklukle_skorlanan_kayitlar_var(
            self, uretim_kayitlari):
        """Öncül çapası: RL10'un beş kaydı ve F-1 spec'i DB'de duruyor.

        Bu bekçi sayıyı koşmadan (tam koşu ~3 dk) öncülü dondurur; sayının
        kendisi ``docs/scofield/raw/OH/Z5S/p10c/once_korelasyon.json``da
        ölçülmüştür (98 ok / 92 skorlayan)."""
        for tid in ("liq-rl10a33a-t1", "liq-rl10a33a-t5",
                    "liq-f1-sa503-1968-spec"):
            assert tid in uretim_kayitlari, tid


# ===========================================================================
# P10B2-15 — n=1 hücrede DÖRT sütun tekrarlanmıyor
# ===========================================================================

def _n1_kosu():
    kayitlar = [_strand_fikstur("sol-fixture-n1", burn_rate_mmps=8.0)]
    return cr.run_correlation(records=kayitlar)


class TestTekGozlemKunyesi:
    def test_hucre_gercekten_n1_ve_dort_sayi_ozdes(self):
        """Öncül: n=1'de bias = medAPE = RMS = MAPE cebirsel olarak aynı."""
        hucre = _n1_kosu()["statistics"]["cells"][0]
        assert hucre["n"] == 1
        assert abs(hucre["bias_pct"]) == pytest.approx(hucre["rms_pct"])
        assert hucre["rms_pct"] == pytest.approx(hucre["median_ape_pct"])
        assert hucre["median_ape_pct"] == pytest.approx(hucre["mape_pct"])

    def test_markdown_satiri_sacilim_sutunlarini_bos_birakiyor(self):
        md = cr.to_markdown(_n1_kosu())
        satir = [s for s in md.splitlines()
                 if s.startswith("| solid | burn_rate")]
        assert satir, md
        assert "(single observation)" in satir[0], satir[0]
        hucreler = [h.strip() for h in satir[0].split("|")]
        # Median APE % ve RMS % sütunları: 1=Motor 2=Quantity 3=N 4=Bias
        # 5=MedianAPE 6=RMS
        assert hucreler[5] == "-", satir[0]
        assert hucreler[6] == "-", satir[0]

    def test_belge_tablosu_sacilim_sutunlarini_bos_birakiyor(self):
        metin = sr.generate_status_section(_n1_kosu(),
                                           generated_on="2026-08-28")
        satir = [s for s in metin.splitlines()
                 if s.startswith("| solid | burn_rate")]
        assert satir, metin
        assert "(single observation)" in satir[0], satir[0]
        hucreler = [h.strip() for h in satir[0].split("|")]
        # 1=Motor 2=Quantity 3=Layer 4=N 5=Bias 6=MedianAPE 7=RMS
        assert hucreler[6] == "-", satir[0]
        assert hucreler[7] == "-", satir[0]

    def test_n_buyukse_sayilar_yerinde_kaliyor(self):
        """Karşı-örnek: n>1 hücrede sütunlar boşaltılmaz."""
        kayitlar = [_strand_fikstur(f"sol-fixture-n3-{i}",
                                    burn_rate_mmps=8.0 + i)
                    for i in range(3)]
        md = cr.to_markdown(cr.run_correlation(records=kayitlar))
        satir = [s for s in md.splitlines()
                 if s.startswith("| solid | burn_rate")][0]
        assert "(single observation)" not in satir, satir
        hucreler = [h.strip() for h in satir.split("|")]
        assert hucreler[5] != "-" and hucreler[6] != "-", satir


# ===========================================================================
# P10B2-07 — aykırı ölçütü SABİTTEN üretiliyor (bayat metin yok)
# ===========================================================================

class TestAykiriOlcutuMetni:
    def test_olcut_metni_sabitlerden_turuyor(self):
        assert str(cr.OUTLIER_MAD_SCALE) in cr.OUTLIER_CRITERION_TEXT
        assert str(cr.OUTLIER_MODIFIED_Z) in cr.OUTLIER_CRITERION_TEXT
        assert "MAD" in cr.OUTLIER_CRITERION_TEXT

    def test_paper_report_yayiminda_bayat_olcut_yok(self):
        from hrma.validation import paper_report as pr
        sonuc = _n1_kosu()
        metin = pr._build_markdown(sonuc, [], "hata_dagilimi",
                                   timestamp="2026-08-28T00:00:00Z")
        assert cr.OUTLIER_CRITERION_TEXT in metin, (
            "yayımlanan Markdown kodun uyguladığı aykırı ölçütünü yazmıyor")
        assert "3*MAD" not in metin, (
            "bayat '3*MAD' ölçütü yayımda hâlâ duruyor (F035 öncesi metin)")

    def test_paper_report_kaynaginda_elle_yazilmis_olcut_kalmadi(self):
        from hrma.validation import paper_report as pr
        kaynak = inspect.getsource(pr._summary_page)
        kaynak += inspect.getsource(pr._build_markdown)
        assert 'Outliers (>3*MAD)' not in kaynak
        assert "|error - median| > 3*MAD" not in kaynak
        assert kaynak.count("cr.OUTLIER_CRITERION_TEXT") == 2, (
            "iki yayım metninden biri yine elle yazılmış olabilir")

    def test_belge_basligi_olcutu_beyan_ediyor(self):
        metin = sr.generate_status_section(_n1_kosu(),
                                           generated_on="2026-08-28")
        assert cr.OUTLIER_CRITERION_TEXT in metin


# ===========================================================================
# P10B2-13 — doğrulayıcı null/yanlış tipli itici alanında ÇÖKMÜYOR
# ===========================================================================

@pytest.fixture(scope="module")
def istemci():
    from hrma.app import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestIticiAlaniTipKapisi:
    """ÖLÇÜLDÜ (28 Ağustos 2026, onarım öncesi):

        POST /calculate {"fuel_type": null, ...}
        -> 400 {"error": "'NoneType' object has no attribute 'lower'",
                "error_type": "AttributeError"}

    Doğrulayıcının KENDİ ürettiği doğru teşhis ("Missing required parameter:
    fuel_type") kaybolup yerine ham Python hatası geçiyordu."""

    @pytest.mark.parametrize("motor_type,alan,yuk", [
        ("hybrid", "fuel_type",
         {"thrust": 1000, "burn_time": 10, "fuel_type": None,
          "oxidizer_type": "n2o", "of_ratio": 6.0}),
        ("hybrid", "oxidizer_type",
         {"thrust": 1000, "burn_time": 10, "fuel_type": "htpb",
          "oxidizer_type": None, "of_ratio": 6.0}),
        ("solid", "propellant_type",
         {"thrust": 1000, "burn_time": 10, "propellant_type": None}),
        ("liquid", "fuel_type",
         {"thrust": 1000, "burn_time": 10, "fuel_type": None,
          "oxidizer_type": "lox", "mixture_ratio": 2.3,
          "chamber_pressure": 70}),
    ])
    def test_null_itici_alani_cokmuyor_ve_adlandiriliyor(self, motor_type,
                                                         alan, yuk):
        from hrma.validation.motor_validation import motor_validator
        ok, mesajlar, sorunlar = motor_validator.validate_motor_data_detailed(
            yuk, motor_type)
        assert ok is False
        assert any(s["field"] == alan and s["reason"] == "missing_required"
                   for s in sorunlar), sorunlar
        assert any(alan in m for m in mesajlar), mesajlar

    @pytest.mark.parametrize("deger", [123, 4.5, ["htpb"], {"ad": "htpb"},
                                       True])
    def test_str_olmayan_itici_adi_adli_wrong_type(self, deger):
        from hrma.validation.motor_validation import motor_validator
        yuk = {"thrust": 1000, "burn_time": 10, "fuel_type": deger,
               "oxidizer_type": "n2o", "of_ratio": 6.0}
        ok, _mesajlar, sorunlar = motor_validator.validate_motor_data_detailed(
            yuk, "hybrid")
        assert ok is False
        kayit = [s for s in sorunlar if s["field"] == "fuel_type"]
        assert kayit and kayit[0]["reason"] == "wrong_type", sorunlar
        assert kayit[0]["expected_type"] == "string"

    def test_ucta_adli_4xx_ham_python_hatasi_degil(self, istemci):
        yanit = istemci.post("/calculate", json={
            "motor_type": "hybrid", "thrust": 1000, "burn_time": 10,
            "fuel_type": None, "oxidizer_type": "n2o", "of_ratio": 6.0,
            "chamber_pressure": 20})
        assert yanit.status_code == 400
        govde = yanit.get_json()
        assert govde["status"] == "validation_error"
        assert govde.get("error_type") != "AttributeError", govde
        alanlar = {s["field"] for s in govde["invalid_fields"]}
        assert "fuel_type" in alanlar, govde
        metin = json.dumps(govde)
        assert "has no attribute" not in metin, (
            "uç hâlâ ham Python hatası yayımlıyor")

    def test_gecerli_yukte_davranis_degismedi(self):
        from hrma.validation.motor_validation import motor_validator
        ok, _m, sorunlar = motor_validator.validate_motor_data_detailed(
            {"thrust": 1000, "burn_time": 10, "fuel_type": "htpb",
             "oxidizer_type": "n2o", "of_ratio": 6.0}, "hybrid")
        assert ok is True
        assert sorunlar == []


# ===========================================================================
# P10B2-09 — assumed_defaults + adapter_notes UÇ GÖVDESİNE iniyor
# ===========================================================================

@pytest.fixture
def kucuk_uc_govdesi(monkeypatch):
    """``/api/correlation-report`` gövdesi, KÜÇÜK bir kayıt kümesiyle.

    Tam DB koşusu ~3 dakikadır; uç sözleşmesi bellek-içi strand fikstürleriyle
    ölçülür. Ürün kodunun kendisi (``_correlation_report_body``) koşar —
    sahte gövde kurulmaz."""
    from hrma import app as app_modulu
    from hrma.validation import experiment_db as edb

    kayitlar = [_strand_fikstur("sol-fixture-uc-1", burn_rate_mmps=8.0),
                _strand_fikstur("sol-fixture-uc-2", burn_rate_mmps=9.5),
                _strand_fikstur("sol-fixture-uc-3", burn_rate_mmps=10.5)]
    monkeypatch.setattr(edb, "load_records", lambda *a, **k: list(kayitlar))
    monkeypatch.setattr(ra, "adapt_record",
                        _yakinsamayan_adaptor({"sol-fixture-uc-1"}))
    app_modulu._CORRELATION_CACHE.clear()
    govde = app_modulu._correlation_report_body(refresh=True)
    app_modulu._CORRELATION_CACHE.clear()
    return govde


class TestUcGovdesiDurustlukKanallari:
    def test_assumed_defaults_ve_adapter_notes_yayimlaniyor(
            self, kucuk_uc_govdesi):
        blok = kucuk_uc_govdesi["declared_assumptions"]
        assert blok["records_with_assumed_defaults"] == 3
        assert blok["records_with_adapter_notes"] == 3
        assert blok["assumed_default_counts"]["burn_rate_a"] == 3
        kayit = {r["test_id"]: r for r in blok["records"]}
        assert set(kayit) == {"sol-fixture-uc-1", "sol-fixture-uc-2",
                              "sol-fixture-uc-3"}
        ornek = kayit["sol-fixture-uc-2"]
        assert "burn_rate_a" in ornek["assumed_defaults"]
        assert any("strand r(P)" in n for n in ornek["adapter_notes"])

    def test_hucre_sekli_DEGISMEDI(self, kucuk_uc_govdesi):
        """Kapsam bekçisi: Z5S dürüstlük kanalları hücreye DEĞİL gövdeye
        eklendi — bu paket hücre şekline dokunmaz.

        ÖH D16 / app-api P10B2-01: hücre şekli o kalemin onarımıyla
        genişledi (bağımlılık/belirsizlik künyesi + ``dependence``).
        Bekçi hâlâ "Z5S bu şekli değiştirmedi" iddiasını taşır: Z5S'in
        dokunmadığı DOKUZ çekirdek anahtar aynen yerinde olmalı ve hücre
        yalnız P10B2-01'in taşıdığı künye alanlarıyla genişlemiş olmalı.
        """
        cekirdek = {
            "motor_type", "quantity", "layer", "n", "bias_percent",
            "rms_percent", "median_ape_percent", "mape_percent",
            "worst_test_id"}
        p10b2_01_kunyesi = {
            "n_campaigns", "n_in_sample", "n_weak_evidence",
            "n_with_measurement_u", "median_measurement_u_pct",
            "median_abs_normalized_error", "dependence"}
        # ÖH D27 / app-api a3 (P13B4-05): hücre şekli İKİNCİ KEZ genişledi.
        # Bekçinin iddiası ("Z5S bu şekle dokunmadı") AYNEN korunur; izin
        # verilen genişleme kümesine P13B4-05'in taşıdığı dört DÜRÜSTLÜK
        # alanı eklendi — tek kaynaktan okunur ki liste ile ürün ayrışamasın.
        from hrma.validation.status_report import _HONESTY_FIELDS
        p10b2_01_kunyesi = p10b2_01_kunyesi | set(_HONESTY_FIELDS)
        for hucre in kucuk_uc_govdesi["cells"]:
            assert cekirdek <= set(hucre), sorted(hucre)
            assert set(hucre) - cekirdek <= p10b2_01_kunyesi, sorted(hucre)

    def test_yakinsamayan_blok_ucta_gorunur(self, kucuk_uc_govdesi):
        blok = kucuk_uc_govdesi["non_converged"]
        assert blok["record_ids"] == ["sol-fixture-uc-1"]
        assert blok["entries"], blok
        assert blok["withheld_cells"] == []

    def test_record_counts_skorlayan_kayit_sayisini_ayri_veriyor(
            self, kucuk_uc_govdesi):
        sayim = kucuk_uc_govdesi["record_counts"]
        assert sayim["with_scored_quantity"] == 3
        # Dört terimli toplam kimliği KORUNDU (mevcut uç bekçisi buna bakıyor).
        assert sayim["total"] == (sayim["scored"]
                                  + sayim["insufficient_inputs"]
                                  + sayim["not_supported"]
                                  + sayim["runner_error"])

    def test_yetersiz_girdi_gerekcesi_ucta(self, monkeypatch):
        """Birim soneki çözülemeyen kayıt uçta da doğru sınıfla görünüyor."""
        from hrma import app as app_modulu
        from hrma.validation import experiment_db as edb

        rec = [r for r in load_records()
               if r["test_id"] == "hyb-amroc1993-htpb-lox-dm01-b1"]
        assert rec, "üretim kaydı yok (bekçi öncülü)"
        monkeypatch.setattr(edb, "load_records", lambda *a, **k: list(rec))
        app_modulu._CORRELATION_CACHE.clear()
        govde = app_modulu._correlation_report_body(refresh=True)
        app_modulu._CORRELATION_CACHE.clear()
        ayrinti = govde["insufficient_inputs_detail"]
        assert len(ayrinti) == 1, ayrinti
        assert "birim soneki cozulemedi" in ayrinti[0]["reason"]
        alanlar = {d["field"]: d["reason"]
                   for d in ayrinti[0]["missing_detail"]}
        assert alanlar["mdot_ox"] == "unit_unresolved"
        assert alanlar["burn_time"] == "value_absent"


# ===========================================================================
# Kapsam bekçisi — geçerli gövde bit-aynı kaldı
# ===========================================================================

def test_gecerli_kosu_hucre_sayilari_degismedi():
    """Yakınsama hükmü, ``convergence`` bloğu OLMAYAN yollara dokunmuyor.

    Strand/sıvı adaptörleri bu bloğu üretmez; onların hücreleri eskisi gibi
    üretilmelidir (fail-closed kapısı yalnız adı geçen kayıtlara uygulanır)."""
    kayitlar = [_strand_fikstur(f"sol-fixture-taban-{i}",
                                burn_rate_mmps=8.0 + 0.5 * i)
                for i in range(4)]
    kosu = cr.run_correlation(records=kayitlar)
    hucreler = kosu["statistics"]["cells"]
    assert len(hucreler) == 1
    assert hucreler[0]["n"] == 4
