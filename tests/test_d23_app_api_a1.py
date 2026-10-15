# -*- coding: utf-8 -*-
"""ÖH D23 · app-api · aşama-1 bekçileri — P10B2-06.

KUSUR (ölçüldü, taban ef527ae; kanıt
``docs/scofield/raw/OH/D23/app-api/a1/once_p10b2_06.json``):

``anomaly`` alanı bir VERİ KALİTESİ bayrağıdır (lüle erozyonu, tıkalı basınç
hattı, çatlak tane, bildiri-içi tutarsızlık — veritabanındaki diğer 21 kaydın
gerekçeleri bunlar). Dört Heydari S4A1 swirl kaydı ise AYNI bayrağı taşıyordu
ve notu şunu söylüyordu: *"Swirl (1 eksenel + 4 teğetsel) enjeksiyon: HRMA v1
EKSENEL hibrit modelinin kapsamı dışında"*. Yani gerekçe deneyin kusuru değil
MODELİN sınırıydı; koşucu (``correlation_runner._aggregate``) bu kayıtları
``if rr["anomaly"]`` ile KOŞULSUZ dışlıyordu.

Ölçülen etki (tam DB, 212 kayıt):
  * ``hybrid/c_star`` yayımlanan önyargı %-0,12 (n=18) ⟷ dört kayıt dâhil
    %+2,45 (n=22): büyüklük ~21×, İŞARET DÖNÜYOR. Tablonun en güçlü iddiası
    modelin zorlandığı vakalar çıkarıldığı için o kadar güçlü görünüyordu.
  * ``('hybrid','thrust')`` ana katmanda HİÇ hücre değildi; oysa DB'nin TEK
    hibrit itki karşılaştırması bu dört kayıttır (%+19..+36). ``to_markdown``
    çıktısında hibrit itki satırı YOKTU — okur bunu "ölçülmedi" diye okur.
  * ``VALIDATION_STATUS.md`` hibrit itki satırını ``anomaly`` etiketiyle
    basıyordu; okur "deneyler bozuktu" diye okur.

ONARIM: kayıt şemasına ``model_scope`` bloğu (``{in_scope, note}``) eklendi;
dört kaydın gerekçe metni birebir korunarak oraya taşındı; koşucu kapsam-dışı
katmanı ANOMALİDEN ÖNCE ayırıyor, etkiyi SAYIYLA yayımlıyor
(``n_out_of_scope`` + ``stats_incl_out_of_scope``) ve kanıtın TAMAMI kapsam
dışı olan hücreyi adıyla geri çekiyor (``out_of_scope_withheld_cells``) —
"ölçüldü, çıkarıldı" artık "ölçülmedi" gibi okunamıyor.

Bekçiler koşucuyu SENTETİK fikstürle sınar (tam DB koşusu ~2 dk sürer;
karantina bütünlüğü ayrıca ``tests/test_correlation_guards.py``de gerçek DB
üzerinde kilitli). Şema/kayıt tarafı dosyadan doğrudan okunur.
"""

import json
from pathlib import Path

import pytest

from hrma.validation import experiment_db
from hrma.validation.correlation_runner import run_correlation, to_markdown
from hrma.validation.status_report import correlation_cells

KOK = Path(__file__).resolve().parents[1]
SWIRL_KAYITLARI = sorted(
    (KOK / "hrma/data/validation_records/hybrid").glob(
        "hyb-heydari2017-htpb-n2o-s4a1-*.json"))


# --- fikstür koşucu ---------------------------------------------------------

def _kayit(test_id, motor_type="hybrid", confidence="high",
           measured=None, model_scope=None, anomaly=None):
    rec = {
        "test_id": test_id,
        "motor_type": motor_type,
        "source": {"citation": ("BORU HATTI FİKSTÜRÜ — deneysel veri "
                                "DEĞİL (test_d23_app_api_a1)"),
                   "access": "synthetic",
                   "confidence": confidence, "date_checked": "2026-09-05"},
        "propellants": {"oxidizer": "n2o", "fuel": "htpb"},
        "geometry": {"note": "fikstür"},
        "inputs": {"chamber_pressure_bar": 20.0},
        "measured": measured or {"c_star": 1500.0},
        "units_original": "SI",
        "digitized": False,
    }
    if model_scope is not None:
        rec["model_scope"] = model_scope
    if anomaly is not None:
        rec["anomaly"] = anomaly
    return rec


def _adapter_fabrikasi(hatalar):
    """test_id -> {büyüklük: hata_yüzdesi} eşlemesinden adaptör üretir."""

    def _adapt(rec):
        tahminler = {}
        for q, hata in hatalar[rec["test_id"]].items():
            olculen = float(rec["measured"][q])
            tahminler[q] = olculen * (1.0 + hata / 100.0)
        return {"status": "ok", "predictions": tahminler,
                "measured_si": {q: float(rec["measured"][q])
                                for q in tahminler}}

    return _adapt


@pytest.fixture(scope="module")
def kosu():
    """3 kapsam-içi + 2 kapsam-dışı c_star; itkinin TAMAMI kapsam dışı."""
    kayitlar = [
        _kayit("fx-in-1", measured={"c_star": 1500.0}),
        _kayit("fx-in-2", measured={"c_star": 1500.0}),
        _kayit("fx-in-3", measured={"c_star": 1500.0}),
        _kayit("fx-oos-1", measured={"c_star": 1500.0, "thrust": 1000.0},
               model_scope={"in_scope": False,
                            "note": "fikstür: swirl enjeksiyon, v1 eksenel "
                                    "model kapsamı dışı"}),
        _kayit("fx-oos-2", measured={"c_star": 1500.0, "thrust": 1000.0},
               model_scope={"in_scope": False,
                            "note": "fikstür: swirl enjeksiyon, v1 eksenel "
                                    "model kapsamı dışı"},
               anomaly={"flag": True, "note": "fikstür: lüle erozyonu da var"}),
    ]
    hatalar = {
        "fx-in-1": {"c_star": 0.0},
        "fx-in-2": {"c_star": 1.0},
        "fx-in-3": {"c_star": -1.0},
        "fx-oos-1": {"c_star": 30.0, "thrust": 25.0},
        "fx-oos-2": {"c_star": 30.0, "thrust": 35.0},
    }
    return run_correlation(records=kayitlar,
                           adapter=_adapter_fabrikasi(hatalar))


def _hucre(kosu, mt, q):
    for c in kosu["statistics"]["cells"]:
        if c["motor_type"] == mt and c["quantity"] == q:
            return c
    return None


# --- 1) şema: model_scope birinci sınıf alan --------------------------------

class TestSema:
    def test_model_scope_izinli_alan(self):
        assert "model_scope" in experiment_db._TOP_LEVEL_ALLOWED, (
            "model_scope üst düzey alan olarak tanınmıyor — kapsam gerekçesi "
            "yine anomaly bayrağına sığınmak zorunda kalır.")

    def test_in_scope_false_gerekce_ister(self):
        rec = _kayit("fx-1", model_scope={"in_scope": False})
        hatalar = experiment_db.validate_record(rec)
        assert any("model_scope.note" in e for e in hatalar), (
            "in_scope=false gerekçesiz kabul ediliyor — fail-closed ihlali: "
            "modelin HANGİ varsayımının kaydı kapsamadığı yazılmalı.")

    def test_in_scope_bool_olmali(self):
        rec = _kayit("fx-1", model_scope={"in_scope": "hayir", "note": "x"})
        assert any("model_scope.in_scope" in e
                   for e in experiment_db.validate_record(rec))

    def test_bilinmeyen_alan_reddedilir(self):
        rec = _kayit("fx-1", model_scope={"in_scope": False, "note": "x",
                                          "sebep": "y"})
        assert any("model_scope" in e and "bilinmeyen" in e
                   for e in experiment_db.validate_record(rec))

    def test_gecerli_kayit(self):
        rec = _kayit("fx-1", model_scope={"in_scope": False,
                                          "note": "swirl enjeksiyon"})
        assert experiment_db.validate_record(rec) == []

    def test_ozet_ikisini_ayri_sayar(self):
        ozet = experiment_db.summarize([
            _kayit("fx-a", anomaly={"flag": True, "note": "lüle erozyonu"}),
            _kayit("fx-b", model_scope={"in_scope": False, "note": "swirl"}),
        ])
        assert ozet["n_anomalies"] == 1
        assert ozet["n_out_of_scope"] == 1, (
            "model kapsamı dışı kayıt anomali sayılıyor — 'kaç deney bozuktu' "
            "sorusunun cevabı modelin kendi sınırlarıyla şişer.")


# --- 2) ürün kayıtları: dört swirl kaydı doğru sınıfta ----------------------

class TestSwirlKayitlari:
    def test_dort_kayit_var(self):
        assert len(SWIRL_KAYITLARI) == 4

    @pytest.mark.parametrize("yol", SWIRL_KAYITLARI,
                             ids=lambda p: p.stem)
    def test_model_kapsami_anomali_degil(self, yol):
        d = json.loads(yol.read_text(encoding="utf-8"))
        assert d.get("model_scope", {}).get("in_scope") is False, (
            f"{d['test_id']}: model kapsamı gerekçesi model_scope bloğunda "
            "değil.")
        assert "kapsamı dışında" in d["model_scope"]["note"], (
            "gerekçe metni kaybolmuş — kaydın kendi cümlesi korunmalı.")
        assert "anomaly" not in d, (
            f"{d['test_id']}: MODELİN sınırı hâlâ DENEYİN anomalisi olarak "
            "işaretli (P10B2-06 kusuru geri geldi).")

    def test_gercek_anomali_kayitlari_dokunulmadi(self):
        yol = (KOK / "hrma/data/validation_records/hybrid"
               / "hyb-karabeyoglu2003-paraffin-gox-t4l-12.json")
        d = json.loads(yol.read_text(encoding="utf-8"))
        assert d["anomaly"]["flag"] is True, (
            "bildiri-içi tutarsızlık GERÇEK bir veri anomalisidir; "
            "yeniden sınıflandırma onu kapsamamalı.")
        assert "model_scope" not in d


# --- 3) koşucu: ayrı katman, görünür etki, fail-closed geri çekme -----------

class TestKosucuKatmanlari:
    def test_kapsam_disi_ayri_katman(self, kosu):
        st = kosu["statistics"]
        kapsam = {e["test_id"] for e in st["out_of_scope_entries"]}
        anomali = {e["test_id"] for e in st["anomaly_entries"]}
        assert kapsam == {"fx-oos-1", "fx-oos-2"}
        assert anomali == set(), (
            "kapsam-dışı kayıt anomali listesine sızdı — iki gerekçe "
            "birbirine karıştı.")

    def test_iki_gerekce_birlikte_kaybolmaz(self, kosu):
        giris = next(e for e in kosu["statistics"]["out_of_scope_entries"]
                     if e["test_id"] == "fx-oos-2")
        assert giris["also_anomaly_flagged"] is True, (
            "hem kapsam dışı hem anomali olan kayıtta anomali gerekçesi "
            "kayboldu.")
        assert giris["anomaly_note"]
        assert giris["model_scope_note"]

    def test_ana_hucreye_sizmaz(self, kosu):
        hucre = _hucre(kosu, "hybrid", "c_star")
        assert {e["test_id"] for e in hucre["entries"]} == {
            "fx-in-1", "fx-in-2", "fx-in-3"}

    def test_etki_sayiyla_yayimlanir(self, kosu):
        """Beyan değil ÖLÇÜM: alternatif istatistik hücrede durur."""
        hucre = _hucre(kosu, "hybrid", "c_star")
        assert hucre["n_out_of_scope"] == 2
        assert hucre["out_of_scope_test_ids"] == ["fx-oos-1", "fx-oos-2"]
        inc = hucre["stats_incl_out_of_scope"]
        assert inc is not None, (
            "başlığın kapsam-dışı dışlamasına duyarlılığı yayımlanmıyor — "
            "okur %0'lık önyargının %20'ye çıktığını göremez.")
        assert inc["n"] == 5
        # yayımlanan bias 0,0 ⟷ kapsam dışı dâhil +12,0 (3x0 + 2x30)/5
        assert hucre["bias_pct"] == pytest.approx(0.0, abs=1e-9)
        assert inc["bias_pct"] == pytest.approx(12.0, abs=1e-9)

    def test_kapsam_disi_yoksa_alan_bos(self, kosu):
        """Uydurma yok: kapsam-dışı gözlemi olmayan hücrede alternatif yok."""
        kosu2 = run_correlation(
            records=[_kayit("fx-in-1"), _kayit("fx-in-2")],
            adapter=_adapter_fabrikasi({"fx-in-1": {"c_star": 1.0},
                                        "fx-in-2": {"c_star": -1.0}}))
        hucre = _hucre(kosu2, "hybrid", "c_star")
        assert hucre["n_out_of_scope"] == 0
        assert hucre["stats_incl_out_of_scope"] is None

    def test_tamami_kapsam_disi_hucre_adiyla_geri_cekilir(self, kosu):
        """FAIL-CLOSED: 'ölçüldü, çıkarıldı' ≠ 'ölçülmedi'."""
        st = kosu["statistics"]
        assert _hucre(kosu, "hybrid", "thrust") is None, (
            "kanıtın tamamı kapsam dışı olan hücre ana istatistiğe girdi.")
        geri = [c for c in st["out_of_scope_withheld_cells"]
                if c["quantity"] == "thrust"]
        assert len(geri) == 1, (
            "hibrit itki hücresi tablodan SESSİZCE düştü — okur bunu "
            "'ölçülmedi' diye okur, oysa ölçüldü ve çıkarıldı.")
        c = geri[0]
        assert c["n"] == 2
        assert c["test_ids"] == ["fx-oos-1", "fx-oos-2"]
        assert c["error_pct_min"] == pytest.approx(25.0)
        assert c["error_pct_max"] == pytest.approx(35.0)
        assert c["model_scope_notes"], "geri çekme gerekçesi boş"


# --- 4) yayım kanalları: markdown + VALIDATION_STATUS düzleştiricisi --------

class TestYayimKanallari:
    def test_markdown_kapsam_bolumu(self, kosu):
        md = to_markdown(kosu)
        assert "Out-of-model-scope records" in md, (
            "markdown kapsam-dışı bölümünü basmıyor.")
        assert "Cells withheld (entirely outside the model scope)" in md
        assert "| hybrid | thrust |" in md, (
            "geri çekilen hibrit itki hücresi markdown'da görünmüyor.")
        assert "(incl. out-of-scope)" in md, (
            "başlığın duyarlılık satırı tabloda yok.")

    def test_duzlestirici_kapsam_katmani(self, kosu):
        cells = correlation_cells(kosu["statistics"])
        katmanlar = {(c["motor_type"], c["quantity"]): c["layer"]
                     for c in cells if c["layer"] == "out_of_scope"}
        assert katmanlar.get(("hybrid", "thrust")) == "out_of_scope", (
            "VALIDATION_STATUS düzleştiricisi hibrit itkiyi hâlâ 'anomaly' "
            "etiketiyle basıyor — okur deneyin bozuk olduğunu sanır.")
        assert ("hybrid", "c_star") in katmanlar

    def test_yayimlanan_belge_katmani(self):
        """docs/VALIDATION_STATUS.md yeniden üretildi mi (etiket doğru mu)?"""
        metin = (KOK / "docs/VALIDATION_STATUS.md").read_text(encoding="utf-8")
        satirlar = [s for s in metin.splitlines()
                    if s.startswith("| hybrid | thrust |")]
        assert satirlar, "yayımlanan belgede hibrit itki satırı yok."
        assert all("| out_of_scope |" in s for s in satirlar), (
            "yayımlanan belge hibrit itkiyi hâlâ 'anomaly' katmanında "
            "gösteriyor — belge yeniden üretilmemiş.")
