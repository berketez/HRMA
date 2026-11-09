# -*- coding: utf-8 -*-
"""V306/ÖLÇÜT kalem 5 — ölçüt (benchmark) sisteminin bekçileri.

Ne kilitlenir, ne kilitlenmez
-----------------------------
Bugünkü sayılar test beklentisi olarak DONDURULMAZ (başka kulvarlar yayımlanan
sayıları bilinçli değiştiriyor). Kilitlenen:
  * vaka dosyalarının sözleşmesi (15 vaka, 3 sistem × 5 seviye, künye, adımlar);
  * koşucunun hükümleri: adım sözleşmesi (HTTP + izlenen çıktının varlığı +
    adlı ret), gerçek motor kıyası (bant MEVCUT bekçilerden okunur; ikinci
    tanım yok) ve belirlenimcilik/fark raporu ayrımı;
  * hızlı alt küme (her yakıt sisteminden bir vaka) normal test koşusunda
    uçtan uca koşar; tam 15 vaka ``agir_canli_uc`` işaretli (gecelik + yayın).
Ters mutasyonlar: aşağıdaki ``*_kaldi_*`` testleri yapay sapmanın KALDI
hükmüne döndüğünü sınar (RAPOR.md'de CLI düzeyinde de ölçüldü).
"""

import copy
import importlib.util
import json
import math
import os
import pathlib
import sys

import pytest

KOK = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK / "tools"))

import olcut_kos as ok  # noqa: E402


def _modul(yol, ad):
    spec = importlib.util.spec_from_file_location(ad, yol)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture(scope="module")
def vakalar():
    return ok.vakalari_yukle()


@pytest.fixture(scope="module")
def bantlar():
    return ok.bantlari_yukle()


@pytest.fixture(scope="module")
def kayitlar():
    from hrma.validation.experiment_db import load_records
    return {r["test_id"]: r for r in load_records()}


# --- 1. vaka dosyaları -----------------------------------------------------

def test_on_bes_vaka_uc_sistem_bes_seviye(vakalar):
    kimlikler = sorted(v["kimlik"] for v in vakalar)
    beklenen = sorted(f"{s}_L{i}" for s in ("sivi", "hibrit", "kati")
                      for i in range(1, 6))
    assert kimlikler == beklenen


def test_vaka_kunyesi_ve_motor_adimi(vakalar):
    for v in vakalar:
        k = v["kaynak"]
        for alan in ("dosya", "tur_surumu", "tur_commit", "tur_tarihi"):
            assert k.get(alan), f"{v['kimlik']}: künyede {alan} yok"
        uclar = [a["uc"] for a in v["adimlar"]]
        assert any(u in ("/calculate_liquid", "/calculate", "/calculate_solid")
                   for u in uclar), f"{v['kimlik']}: motor adımı yok"
        for a in v["adimlar"]:
            if a["beklenen"]["http_durum"] == 200:
                assert a["izlenen"], f"{v['kimlik']}.{a['ad']}: izlenen yok"
            if a.get("turetilmis"):
                assert a.get("turetme_notu"), (
                    f"{v['kimlik']}.{a['ad']}: türetilmiş gövde gerekçesiz")


def test_gercek_motor_vakalari_kayitlara_bagli(vakalar, kayitlar):
    bagli = {v["kimlik"]: [k["kayit"] for k in v["kayit_kiyasi"]]
             for v in vakalar if v["kayit_kiyasi"]}
    assert {"sivi_L4", "sivi_L5", "kati_L1"} <= set(bagli)
    for kimlik, liste in bagli.items():
        for tid in liste:
            assert tid in kayitlar, f"{kimlik}: kayıt yok {tid}"


def test_vaka_dosyasi_sema_hatasi_fail_closed(tmp_path):
    bozuk = {"sema": ok.SEMA, "kimlik": "x_L1", "sistem": "x",
             "seviye": "L1", "kaynak": {}, "adimlar": [],
             "kayit_kiyasi": []}
    (tmp_path / "x_L1.json").write_text(json.dumps(bozuk), encoding="utf-8")
    with pytest.raises(ok.VakaHatasi):
        ok.vakalari_yukle(str(tmp_path))
    with pytest.raises(ok.VakaHatasi):
        ok.vakalari_yukle(secim=["yok_L9"])


# --- 2. bantlar mevcut bekçilerden ------------------------------------------

def test_bantlar_bekcilerle_ayni(bantlar):
    """ast ile okunan bant = bekçi modülünün çalışma anındaki değeri."""
    g = _modul(KOK / "tests" / "test_correlation_guards.py", "_olcut_g")
    f3 = _modul(KOK / "tests" / "test_f3_yayimlanmis_korelasyon.py",
                "_olcut_f3")
    assert bantlar["hucre_tavani"] == g.PHYSICS_CEILING_MEDAPE
    assert bantlar["kayit_bandi"] == f3.BANTLAR
    assert bantlar["kayit_bandi_tol"] == f3.BANT_TOL


# --- 3. kıyas hükümleri (ters mutasyon dahil) -------------------------------

def _rl10_kiyasi():
    return {"kayit": "liq-rl10a33a-nominal-spec", "vaka_yolu": {
        "adim": "m", "eslesme": [
            {"kayit_anahtari": "isp_vac_s", "yanit_yolu": "isp_vacuum"},
            {"kayit_anahtari": "thrust_vac_n", "yanit_yolu": "thrust_vacuum",
             "dongusel": True, "dongusel_neden": "girdi"}]}}


def test_gercek_motor_bant_icinde_gecti(kayitlar, bantlar):
    sonuc = ok.kayit_kiyasi(_rl10_kiyasi(), {"m": {
        "isp_vacuum": 445.0 * 0.97, "thrust_vacuum": 1.0}}, kayitlar, bantlar)
    assert sonuc["hukum"] == ok.GECTI, sonuc["nedenler"]
    satir = {r["taban"]: r for r in sonuc["vaka_yolu"]["satirlar"]}
    assert satir["isp_vac"]["hukum"] == ok.GECTI
    assert satir["isp_vac"]["bant_kaynagi"].startswith(
        "tests/test_correlation_guards.py")
    # döngüsel büyüklük ne kadar saparsa sapsın skor dışı kalır
    assert satir["thrust_vac"]["durum"] == "dongusel_skor_disi"


def test_gercek_motor_yapay_sapma_kaldi_der(kayitlar, bantlar):
    """Ters mutasyon: izlenen çıktıya tavan dışı sapma -> KALDI."""
    sonuc = ok.kayit_kiyasi(_rl10_kiyasi(), {"m": {
        "isp_vacuum": 445.0 * 1.06, "thrust_vacuum": 1.0}}, kayitlar, bantlar)
    assert sonuc["hukum"] == ok.KALDI
    assert any("isp_vac" in n for n in sonuc["nedenler"])


def test_alt_sinir_ve_tahmin_yok(kayitlar, bantlar):
    kiyas = {"kayit": "liq-f1-sa503-1968-spec", "vaka_yolu": {
        "adim": "m", "eslesme": [
            {"kayit_anahtari": "isp_sl_min_s", "yanit_yolu": "isp_sea_level",
             "tur": "alt_sinir"}]}}
    assert ok.kayit_kiyasi(kiyas, {"m": {"isp_sea_level": 261.0}}, kayitlar,
                           bantlar)["hukum"] == ok.GECTI
    assert ok.kayit_kiyasi(kiyas, {"m": {"isp_sea_level": 259.0}}, kayitlar,
                           bantlar)["hukum"] == ok.KALDI
    assert ok.kayit_kiyasi(kiyas, {"m": {}}, kayitlar,
                           bantlar)["hukum"] == ok.KALDI


def test_kayit_yolu_f3_bandi(kayitlar, bantlar):
    """Kayıt yolu = resmî korelasyon koşucusu; bant F3 bekçisinden."""
    sonuc = ok.kayit_kiyasi({"kayit": "sol-nakka2000-kappa-ksb002",
                             "kayit_yolu": True}, {}, kayitlar, bantlar)
    assert sonuc["kayit_yolu"]["adaptor_durumu"] == "ok"
    skorlu = [r for r in sonuc["kayit_yolu"]["satirlar"]
              if r["durum"] == "scored"]
    assert skorlu and all(r["bant_kaynagi"].startswith(
        "tests/test_f3_yayimlanmis_korelasyon.py") for r in skorlu)
    assert sonuc["hukum"] == ok.GECTI, sonuc["nedenler"]
    # ters mutasyon: bandın merkezi 2 × tolerans kaydırılırsa KALDI
    kaydirilmis = copy.deepcopy(bantlar)
    anahtar = ("sol-nakka2000-kappa-ksb002", "isp")
    kaydirilmis["kayit_bandi"][anahtar] += 2 * bantlar["kayit_bandi_tol"]
    assert ok.kayit_kiyasi({"kayit": "sol-nakka2000-kappa-ksb002",
                            "kayit_yolu": True}, {}, kayitlar,
                           kaydirilmis)["hukum"] == ok.KALDI


# --- 4. belirlenimcilik / fark raporu ----------------------------------------

def _sahte_sonuc(deger, kod="abc"):
    adim = {"ad": "motor", "http_durum": 200, "izlenen": {"isp_s": deger},
            "uyari_kodlari": ["warn.x"], "parmak_izi": {"*": "1", "a": "1"}}
    return {"meta": {"kod_kimligi": {"git_head": kod},
                     "is_parcacigi_ortami": {"OMP_NUM_THREADS": "2"}},
            "vakalar": [{"kimlik": "sivi_L1", "vaka_sha256": "v",
                         "adimlar": [adim]}]}


def test_ayni_kod_bit_ayni_gecti():
    o = ok.onceki_kiyasi(_sahte_sonuc(221.72397695453841),
                         _sahte_sonuc(221.72397695453841))
    assert o["vakalar"][0]["tur"] == "belirlenimcilik"
    assert o["vakalar"][0]["hukum"] == ok.GECTI


def test_ayni_kod_son_bit_sapmasi_kaldi_der():
    """Ters mutasyon: aynı kod + aynı vaka, 1 ulp sapma -> KALDI (adıyla)."""
    eski = 221.72397695453841
    yeni = math.nextafter(eski, math.inf)
    assert yeni != eski and abs(yeni - eski) < 1e-12
    o = ok.onceki_kiyasi(_sahte_sonuc(yeni), _sahte_sonuc(eski))
    v = o["vakalar"][0]
    assert v["hukum"] == ok.KALDI
    assert v["farkli_cikti"][0]["cikti"] == "motor.isp_s"


def test_farkli_kod_fark_raporu_hukum_vermez():
    o = ok.onceki_kiyasi(_sahte_sonuc(230.0, kod="yeni"),
                         _sahte_sonuc(221.7, kod="eski"))
    v = o["vakalar"][0]
    assert v["tur"] == "fark_raporu" and v["hukum"] == ok.BILGI
    assert v["farkli_cikti"][0]["goreli_fark_yuzde"] == pytest.approx(
        (230.0 - 221.7) / 221.7 * 100.0)


# --- 5. uçtan uca: hızlı alt küme (normal test) / tam koşu (gecelik) ---------

def _uctan_uca(secim, tekrar=1):
    vakalar = ok.vakalari_yukle(secim=list(secim))
    sonuc = ok.kos(vakalar, tekrar=tekrar)
    nedenler = [f"{v['kimlik']}: {n}" for v in sonuc["vakalar"]
                for n in v["nedenler"]]
    return sonuc, nedenler


def test_hizli_alt_kume_her_sistemden_bir_vaka():
    sistemler = {k.split("_")[0] for k in ok.HIZLI_ALT_KUME}
    assert sistemler == {"sivi", "hibrit", "kati"}
    sonuc, nedenler = _uctan_uca(ok.HIZLI_ALT_KUME)
    assert sonuc["genel_hukum"] == ok.GECTI, nedenler
    # hızlı kümede adlı ret ve gerçek motor kıyası gerçekten koşmuş olmalı
    adimlar = {(v["kimlik"], a["ad"]): a for v in sonuc["vakalar"]
               for a in v["adimlar"]}
    ret = adimlar[("sivi_L5", "kapsam_disi_itki_reddi")]
    assert ret["http_durum"] == 400 and ret["gecersiz_alanlar"]
    kati = next(v for v in sonuc["vakalar"] if v["kimlik"] == "kati_L1")
    assert kati["kayit_kiyasi"][0]["kayit_yolu"]["adaptor_durumu"] == "ok"


def test_hizli_alt_kume_kati_surec_ici_bit_ayni():
    sonuc, nedenler = _uctan_uca(["kati_L1"], tekrar=2)
    assert sonuc["tekrar"]["kati_L1"]["bit_ayni"], sonuc["tekrar"]
    assert sonuc["genel_hukum"] == ok.GECTI, nedenler


@pytest.mark.agir_canli_uc
def test_tam_olcut_kosusu_on_bes_vaka():
    sonuc, nedenler = _uctan_uca([v["kimlik"] for v in ok.vakalari_yukle()])
    assert len(sonuc["vakalar"]) == 15
    assert sonuc["genel_hukum"] == ok.GECTI, nedenler


def test_cli_secim_ve_cikti(tmp_path):
    kod = ok.main(["--cikti", str(tmp_path), "--secim", "kati_L1"])
    assert kod == 0
    sonuc = json.loads((tmp_path / "olcut_sonuc.json").read_text("utf-8"))
    assert sonuc["sema"] == ok.SONUC_SEMASI
    assert [v["kimlik"] for v in sonuc["vakalar"]] == ["kati_L1"]
    ozet = (tmp_path / "olcut_ozet.md").read_text("utf-8")
    assert "kati_L1" in ozet and "Gerçek motor kıyasları" in ozet
    # --onceki ile aynı kod -> belirlenimcilik GECTI
    kod2 = ok.main(["--cikti", str(tmp_path / "b"), "--secim", "kati_L1",
                    "--onceki", str(tmp_path / "olcut_sonuc.json")])
    assert kod2 == 0
    assert ok.main(["--cikti", str(tmp_path / "c"), "--secim", "yok_L1"]) == 2
