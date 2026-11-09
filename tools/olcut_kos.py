#!/usr/bin/env python3
"""HRMA ölçüt (benchmark) koşucusu — arayüzsüz, tek komut, kaynaklı kıyas.

Neden var (V306/ÖLÇÜT, 4 Kas 2026)
----------------------------------
2 Kasım mühendis turu sıvı / hibrit / katı için 5000 ft'ten uzaya beş seviyede
(L1–L5) 15 motor tasarladı. Turun gerçek API gövdeleri ``olcut/vakalar/``
altında vaka dosyasına çevrildi (künye her dosyanın ``kaynak`` bloğunda). Bu
araç o vakaları uygulamanın KENDİ hesap yolundan — Flask test istemcisiyle,
arayüzün çağırdığı uçların aynısından — koşar. Ağ, tarayıcı, sunucu portu
gerekmez.

Ne ölçer, neyi ölçmez
---------------------
Bu araç bugünkü sayıları test beklentisi olarak DONDURMAZ. Hüküm üç
kaynaktan gelir:

1. **Adım sözleşmesi.** Her adımın beklenen HTTP durumu (200 ya da adlı ret:
   ``invalid_fields`` içinde beklenen alan + neden) ve izlenen her çıktının
   yanıtta bulunması. Bir çıktı yoldan kaybolursa (alan adı değişti, hesap
   çıktıyı üretmez oldu) KALDI — vaka dosyası bilinçli güncellenir.
2. **Gerçek motor kıyası.** Vakanın karşılığı olan kaynaklı doğrulama kaydı
   (``hrma/data/validation_records``) ile sapma. İki yol:
     * vaka yolu: turun gövdesiyle API yanıtı ⟷ kaydın ölçülen değeri;
     * kayıt yolu: kaydın kendisi korelasyon koşucusundan
       (``run_correlation(records=[kayıt])``, resmî doğrulama yolu).
   Birim çevirisi ``record_adapters.to_si``, hata formülü
   ``correlation_runner`` ile AYNIDIR. Bant İKİNCİ KEZ TANIMLANMAZ: mevcut
   bekçilerden okunur — kayıt düzeyi bantlar
   ``tests/test_f3_yayimlanmis_korelasyon.py::BANTLAR`` (± ``BANT_TOL``,
   yalnız kayıt yolunda; o bantlar adaptörün kendi girdileri içindir) ve
   hücre fizik tavanları ``tests/test_correlation_guards.py::
   PHYSICS_CEILING_MEDAPE`` (tek kayda |hata| ≤ tavan olarak). Bandı olmayan
   büyüklük yalnız raporlanır (BİLGİ). Kayıt anahtarı ``*_min`` ise kaynak bir
   ALT SINIR yayımlamıştır; hüküm tahmin ≥ sınırdır. Girdiyle eşlenmiş
   (döngüsel) büyüklük skor dışıdır.
3. **Belirlenimcilik.** ``--tekrar N`` aynı süreçte N koşu; ``--onceki``
   önceki koşunun JSON'u. Kod kimliği (git HEAD + ``hrma/`` ve bu aracın
   kirli farkı) ve vaka dosyası aynıysa izlenen her çıktı BİT AYNI olmalı;
   değilse KALDI ve sapan çıktı adıyla yazılır. Kod kimliği farklıysa
   (sürümler arası) hüküm verilmez; FARK RAPORU yazılır (eski, yeni, göreli
   fark, eklenen/kalkan uyarı kodları).

Kullanım
--------
    python3 tools/olcut_kos.py --cikti DIZIN                 # 15 vaka
    python3 tools/olcut_kos.py --cikti DIZIN --hizli         # sistem başına 1
    python3 tools/olcut_kos.py --cikti DIZIN --secim sivi_L4,kati_L1
    python3 tools/olcut_kos.py --cikti DIZIN --tekrar 2      # süreç içi tekrar
    python3 tools/olcut_kos.py --cikti DIZIN --onceki ESKI/olcut_sonuc.json

Çıktı: ``DIZIN/olcut_sonuc.json`` (makine) + ``DIZIN/olcut_ozet.md`` (insan).
Çıkış kodu: 0 = KALDI yok, 1 = en az bir KALDI, 2 = kullanım/vaka hatası.
Vakalar SIRALI koşar (tek süreç). İş parçacığı ortam değişkenleri
(OMP/VECLIB/OPENBLAS/MKL/NUMEXPR) meta bloğuna yazılır: belirlenimcilik
kıyası aynı ortamda anlamlıdır.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

DEPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DEPO not in sys.path:
    sys.path.insert(0, DEPO)

VAKA_DIZINI = os.path.join(DEPO, "olcut", "vakalar")
SEMA = "hrma-olcut-vaka/1"
SONUC_SEMASI = "hrma-olcut-sonuc/1"

#: Normal test koşusundaki hızlı alt küme: her yakıt sisteminden bir vaka.
#: Seçim ölçüme dayanır (RAPOR.md): gerçek motor kıyası (katı L1 KSB-002),
#: adlı ret adımı (sıvı L5) ve hibritin dört uç türü (hibrit L3) kapsanır.
HIZLI_ALT_KUME = ("sivi_L5", "hibrit_L3", "kati_L1")

#: Belirlenimcilik parmak izinden çıkarılan yanıt anahtarları (her koşuda
#: değişen ölçüm/izleme alanları; hesap çıktısı DEĞİL). Ölçüldü: iki ardışık
#: koşuda başka hiçbir anahtar değişmedi (RAPOR.md, belirlenimcilik).
OYNAK_ANAHTARLAR = frozenset({"trace_id", "solver_wall_time_s"})

#: Uyarı kodlarının toplandığı anahtar son eki (yanıtın ilk iki düzeyi).
UYARI_SONEKI = "warnings"

ISIRAN_ORTAM = ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
                "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS")

GECTI, KALDI, BILGI = "GECTI", "KALDI", "BILGI"


class VakaHatasi(Exception):
    """Vaka dosyası okunamaz ya da şemaya uymaz (fail-closed)."""


# ---------------------------------------------------------------------------
# Vaka dosyaları
# ---------------------------------------------------------------------------

def _dosya_sha256(yol: str) -> str:
    with open(yol, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def vaka_dogrula(vaka: Dict[str, Any], yol: str) -> None:
    """Asgari şema denetimi; eksik alan sessizce geçmez."""
    if vaka.get("sema") != SEMA:
        raise VakaHatasi(f"{yol}: sema '{vaka.get('sema')}' != {SEMA}")
    for alan in ("kimlik", "sistem", "seviye", "kaynak", "adimlar",
                 "kayit_kiyasi"):
        if alan not in vaka:
            raise VakaHatasi(f"{yol}: '{alan}' alanı yok")
    if not vaka["adimlar"]:
        raise VakaHatasi(f"{yol}: adım yok")
    adlar = set()
    for adim in vaka["adimlar"]:
        for alan in ("ad", "uc", "govde", "beklenen", "izlenen"):
            if alan not in adim:
                raise VakaHatasi(f"{yol}: adım '{adim.get('ad')}' '{alan}' yok")
        if adim["ad"] in adlar:
            raise VakaHatasi(f"{yol}: adım adı tekrar: {adim['ad']}")
        adlar.add(adim["ad"])
        if "http_durum" not in adim["beklenen"]:
            raise VakaHatasi(f"{yol}: adım '{adim['ad']}' beklenen durum yok")
    for kiyas in vaka["kayit_kiyasi"]:
        if "kayit" not in kiyas:
            raise VakaHatasi(f"{yol}: kayıt kıyasında 'kayit' yok")
        vy = kiyas.get("vaka_yolu")
        if vy and vy.get("adim") not in adlar:
            raise VakaHatasi(
                f"{yol}: kayıt kıyası bilinmeyen adıma bağlı: {vy.get('adim')}")


def vakalari_yukle(dizin: str = VAKA_DIZINI,
                   secim: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    if not os.path.isdir(dizin):
        raise VakaHatasi(f"vaka dizini yok: {dizin}")
    dosyalar = sorted(f for f in os.listdir(dizin) if f.endswith(".json"))
    vakalar = []
    for ad in dosyalar:
        yol = os.path.join(dizin, ad)
        with open(yol, encoding="utf-8") as f:
            vaka = json.load(f)
        vaka_dogrula(vaka, yol)
        if os.path.splitext(ad)[0] != vaka["kimlik"]:
            raise VakaHatasi(f"{yol}: dosya adı kimlikle uyuşmuyor")
        vaka["_dosya"] = os.path.relpath(yol, DEPO)
        vaka["_sha256"] = _dosya_sha256(yol)
        vakalar.append(vaka)
    if secim:
        bilinen = {v["kimlik"] for v in vakalar}
        bilinmeyen = [k for k in secim if k not in bilinen]
        if bilinmeyen:
            raise VakaHatasi(f"bilinmeyen vaka: {bilinmeyen}")
        vakalar = [v for v in vakalar if v["kimlik"] in secim]
    return vakalar


# ---------------------------------------------------------------------------
# Bantlar — mevcut bekçilerden okunur (ikinci tanım YOK)
# ---------------------------------------------------------------------------

def _modul_sabitleri(yol: str, adlar: Tuple[str, ...]) -> Dict[str, Any]:
    """Test modülünü ÇALIŞTIRMADAN üst düzey sabitlerini okur (ast)."""
    with open(yol, encoding="utf-8") as f:
        agac = ast.parse(f.read(), filename=yol)
    bulunan: Dict[str, Any] = {}
    for dugum in agac.body:
        if isinstance(dugum, ast.Assign) and len(dugum.targets) == 1 \
                and isinstance(dugum.targets[0], ast.Name) \
                and dugum.targets[0].id in adlar:
            bulunan[dugum.targets[0].id] = ast.literal_eval(dugum.value)
    eksik = [a for a in adlar if a not in bulunan]
    if eksik:
        raise VakaHatasi(f"bant kaynağı {yol}: {eksik} bulunamadı")
    return bulunan


def bantlari_yukle() -> Dict[str, Any]:
    guards = os.path.join(DEPO, "tests", "test_correlation_guards.py")
    f3 = os.path.join(DEPO, "tests", "test_f3_yayimlanmis_korelasyon.py")
    g = _modul_sabitleri(guards, ("PHYSICS_CEILING_MEDAPE",))
    k = _modul_sabitleri(f3, ("BANTLAR", "BANT_TOL"))
    return {
        "hucre_tavani": g["PHYSICS_CEILING_MEDAPE"],
        "kayit_bandi": k["BANTLAR"],
        "kayit_bandi_tol": k["BANT_TOL"],
        "kaynaklar": {
            "hucre_tavani": "tests/test_correlation_guards.py::"
                            "PHYSICS_CEILING_MEDAPE",
            "kayit_bandi": "tests/test_f3_yayimlanmis_korelasyon.py::"
                           "BANTLAR ± BANT_TOL",
        },
    }


# ---------------------------------------------------------------------------
# Yanıt okuma yardımcıları
# ---------------------------------------------------------------------------

_YOK = object()


def _ceket_kapisi_bekletti(yanit: Any, yol: str) -> bool:
    """Sıvı yanıtı bu yolu EK7 ceket yayım kapısıyla mı bekletti?

    ``cooling_circuit_publication`` bloğu (``status = not_solved`` +
    ``withheld_reason_code``) ``design`` kapsamında yayımlanmayan her üst
    alanı, ``cooling_circuit`` kapsamında ``withheld_fields`` yollarını
    bekletir (V306/SIVI-CEKET-A).
    """
    if not isinstance(yanit, dict):
        return False
    kapi = yanit.get("cooling_circuit_publication")
    if not (isinstance(kapi, dict) and kapi.get("status") == "not_solved"
            and kapi.get("withheld_reason_code")):
        return False
    if kapi.get("scope") == "design":
        return yanit.get(yol.split(".")[0]) is None
    return any(yol == y or yol.startswith(y + ".")
               for y in kapi.get("withheld_fields") or [])


def yol_oku(veri: Any, yol: str) -> Any:
    """Noktalı yolu okur; yoksa ``_YOK``."""
    dugum = veri
    for parca in yol.split("."):
        if isinstance(dugum, dict) and parca in dugum:
            dugum = dugum[parca]
        else:
            return _YOK
    return dugum


def _kanonik(veri: Any) -> str:
    return json.dumps(veri, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=True, default=str)


def _oynaksiz(veri: Any) -> Any:
    if isinstance(veri, dict):
        return {k: _oynaksiz(v) for k, v in veri.items()
                if k not in OYNAK_ANAHTARLAR}
    if isinstance(veri, list):
        return [_oynaksiz(v) for v in veri]
    return veri


def parmak_izi(yanit: Any) -> Dict[str, str]:
    """Yanıtın ilk iki düzeyi için anahtar başına sha256 (16 hane).

    Sürümler arası ya da tekrar koşu farkını ADIYLA bulmak içindir; oynak
    anahtarlar (``OYNAK_ANAHTARLAR``) çıkarılır.
    """
    iz: Dict[str, str] = {}
    temiz = _oynaksiz(yanit)
    iz["*"] = hashlib.sha256(_kanonik(temiz).encode()).hexdigest()[:16]
    if isinstance(temiz, dict):
        for k, v in temiz.items():
            iz[k] = hashlib.sha256(_kanonik(v).encode()).hexdigest()[:16]
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    iz[f"{k}.{k2}"] = hashlib.sha256(
                        _kanonik(v2).encode()).hexdigest()[:16]
    return iz


def uyari_kodlari(yanit: Any) -> List[str]:
    """Yanıtın ilk iki düzeyindeki '*warnings' listelerinden kodlar."""
    kodlar: List[str] = []

    def _topla(liste):
        for oge in liste:
            if isinstance(oge, dict):
                kod = oge.get("code") or oge.get("key") or oge.get("message")
            else:
                kod = oge
            if kod is not None:
                kod = str(kod)
                if kod not in kodlar:
                    kodlar.append(kod)

    if isinstance(yanit, dict):
        for k, v in yanit.items():
            if k.endswith(UYARI_SONEKI) and isinstance(v, list):
                _topla(v)
            elif isinstance(v, dict):
                for k2, v2 in v.items():
                    if k2.endswith(UYARI_SONEKI) and isinstance(v2, list):
                        _topla(v2)
    return kodlar


def _uyari_ozeti(yakalanan, en_cok: int = 5) -> List[Dict[str, Any]]:
    """Yakalanan Python uyarılarının en sık ``en_cok`` tanesi (tür + ileti).

    Sayılar belirlenimcilik kıyasına girmez: modül düzeyi uyarılar yalnız
    sürecin ilk çağrısında düşer (önbellek/ısınma), hesap çıktısı değildir.
    """
    sayac: Dict[Tuple[str, str], int] = {}
    for w in yakalanan:
        anahtar = (w.category.__name__, str(w.message)[:160])
        sayac[anahtar] = sayac.get(anahtar, 0) + 1
    sirali = sorted(sayac.items(), key=lambda x: (-x[1], x[0]))[:en_cok]
    return [{"tur": t, "ileti": m, "sayi": n} for (t, m), n in sirali]


def _json_deger(deger: Any) -> Any:
    """JSON'a bit-aynı girebilen değer (float repr gidiş-dönüşte birebir)."""
    if isinstance(deger, (bool, int, float, str)) or deger is None:
        return deger
    return _kanonik(deger)


# ---------------------------------------------------------------------------
# Koşu
# ---------------------------------------------------------------------------

def _istemci():
    from hrma.app import app
    app.config["TESTING"] = True  # örnek proje tohumlaması kapalı
    return app.test_client()


def adim_kos(istemci, adim: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    with warnings.catch_warnings(record=True) as yakalanan, \
            contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("always")
        yanit = istemci.post(adim["uc"], json=adim["govde"])
    sure = time.perf_counter() - t0
    govde = yanit.get_json(silent=True)
    sonuc: Dict[str, Any] = {
        "ad": adim["ad"],
        "uc": adim["uc"],
        "http_durum": yanit.status_code,
        "sure_s": round(sure, 3),
        "izlenen": {},
        "eksik_cikti": [],
        "uyari_kodlari": uyari_kodlari(govde),
        "python_uyarisi_sayisi": len(yakalanan),
        "python_uyarilari": _uyari_ozeti(yakalanan),
        "parmak_izi": parmak_izi(govde) if govde is not None else {},
        "hukum": GECTI,
        "nedenler": [],
    }
    beklenen = adim["beklenen"]
    if yanit.status_code != beklenen["http_durum"]:
        sonuc["hukum"] = KALDI
        sonuc["nedenler"].append(
            f"HTTP {yanit.status_code} (beklenen {beklenen['http_durum']})")
    alan = beklenen.get("gecersiz_alan")
    if alan:
        gecersiz = (govde or {}).get("invalid_fields") or []
        sonuc["gecersiz_alanlar"] = [
            {k: g.get(k) for k in ("field", "reason", "accepted_range",
                                   "value", "unit")}
            for g in gecersiz if isinstance(g, dict)]
        if not any(all(g.get(k) == v for k, v in alan.items())
                   for g in gecersiz if isinstance(g, dict)):
            sonuc["hukum"] = KALDI
            sonuc["nedenler"].append(
                f"beklenen adlı ret yok: {alan} ∉ invalid_fields")
    if yanit.status_code == 200 and isinstance(govde, dict):
        for cikti in adim["izlenen"]:
            deger = yol_oku(govde, cikti["yol"])
            if deger is _YOK:
                sonuc["eksik_cikti"].append(cikti["ad"])
            else:
                sonuc["izlenen"][cikti["ad"]] = _json_deger(deger)
        if sonuc["eksik_cikti"]:
            sonuc["hukum"] = KALDI
            sonuc["nedenler"].append(
                "izlenen çıktı yanıtta yok: " + ", ".join(sonuc["eksik_cikti"]))
    elif yanit.status_code != 200 and isinstance(govde, dict):
        sonuc["hata"] = {k: govde.get(k) for k in ("error", "error_type",
                                                  "status") if k in govde}
    return sonuc, govde


def _bant_hukmu(motor: str, taban: str, hata: float, test_id: str,
                yol_turu: str, bantlar: Dict[str, Any]) -> Dict[str, Any]:
    if yol_turu == "kayit":
        merkez = bantlar["kayit_bandi"].get((test_id, taban))
        if merkez is not None:
            tol = bantlar["kayit_bandi_tol"]
            gecti = abs(hata - merkez) <= tol
            return {"hukum": GECTI if gecti else KALDI,
                    "bant": f"{merkez:+.2f} ± {tol:.2f} %",
                    "bant_kaynagi": bantlar["kaynaklar"]["kayit_bandi"]}
    tavan = bantlar["hucre_tavani"].get((motor, taban))
    if tavan is not None:
        gecti = abs(hata) <= tavan
        return {"hukum": GECTI if gecti else KALDI,
                "bant": f"|hata| ≤ {tavan:.2f} %",
                "bant_kaynagi": bantlar["kaynaklar"]["hucre_tavani"]}
    return {"hukum": BILGI, "bant": None,
            "bant_kaynagi": "bant yok — yalnız rapor (ikinci bant tanımı "
                            "açılmaz)"}


def kayit_kiyasi(kiyas: Dict[str, Any], yanitlar: Dict[str, Any],
                 kayitlar: Dict[str, Any], bantlar: Dict[str, Any]
                 ) -> Dict[str, Any]:
    from hrma.validation import record_adapters as ra
    from hrma.validation.correlation_runner import (
        SCORE_ERROR_REFERENCE, relative_difference_pct, run_correlation)

    tid = kiyas["kayit"]
    kayit = kayitlar.get(tid)
    sonuc: Dict[str, Any] = {"kayit": tid, "hukum": GECTI, "nedenler": []}
    if kayit is None:
        sonuc["hukum"] = KALDI
        sonuc["nedenler"].append(f"kayıt bulunamadı: {tid}")
        return sonuc
    motor = kayit["motor_type"]
    sonuc["kaynak"] = kayit["source"]["citation"]

    vy = kiyas.get("vaka_yolu")
    if vy:
        yanit = yanitlar.get(vy["adim"])
        satirlar = []
        for es in vy["eslesme"]:
            anahtar = es["kayit_anahtari"]
            satir = {"kayit_anahtari": anahtar, "yanit_yolu": es["yanit_yolu"]}
            olcum = kayit["measured"].get(anahtar)
            taban, olcum_si = ra.to_si(anahtar, olcum) \
                if isinstance(olcum, (int, float)) else (anahtar, None)
            tahmin = yol_oku(yanit, es["yanit_yolu"]) \
                if isinstance(yanit, dict) else _YOK
            satir["taban"] = taban
            if olcum_si is None:
                satir.update(durum="birim_cozulemedi", hukum=BILGI)
                satir["not"] = ("record_adapters.to_si bu soneki çevirmiyor"
                                if olcum is not None else "kayıtta değer yok")
            elif tahmin is None and _ceket_kapisi_bekletti(yanit,
                                                           es["yanit_yolu"]):
                # V306/SIVI-CEKET-A (K5_KARAR EK7): motor bu sayıyı ADLI
                # nedenle bekletti (ceketin geçerli çözümü yok). Eksik yol
                # (tahmin_yok, KALDI) değildir; kıyas yapılamaz, neden yazılır.
                kapi = yanit.get("cooling_circuit_publication") or {}
                satir.update(durum="yayimlanmadi", hukum=BILGI)
                satir["not"] = (f"{kapi.get('withheld_reason')} "
                                f"({kapi.get('code')})")
            elif tahmin is _YOK or not isinstance(tahmin, (int, float)):
                satir.update(durum="tahmin_yok", hukum=KALDI)
                sonuc["nedenler"].append(f"vaka yolu {anahtar}: yanıtta yok")
            else:
                hata = relative_difference_pct(
                    float(tahmin), olcum_si, reference=SCORE_ERROR_REFERENCE)
                satir.update(tahmin_si=float(tahmin), olcum_si=olcum_si,
                             hata_yuzde=float(hata))
                if es.get("dongusel"):
                    satir.update(durum="dongusel_skor_disi", hukum=BILGI)
                    satir["not"] = es.get("dongusel_neden")
                elif es.get("tur") == "alt_sinir":
                    gecti = float(tahmin) >= olcum_si
                    satir.update(durum="alt_sinir", hukum=GECTI if gecti
                                 else KALDI,
                                 bant="tahmin ≥ kaynağın yayımladığı alt sınır")
                else:
                    satir.update(durum="nokta")
                    satir.update(_bant_hukmu(motor, taban, float(hata), tid,
                                             "vaka", bantlar))
                if satir["hukum"] == KALDI and satir["durum"] != "tahmin_yok":
                    sonuc["nedenler"].append(
                        f"vaka yolu {taban}: hata {hata:+.2f} % bant dışı "
                        f"({satir.get('bant')})")
            satirlar.append(satir)
        sonuc["vaka_yolu"] = {"adim": vy["adim"], "satirlar": satirlar}

    if kiyas.get("kayit_yolu"):
        with warnings.catch_warnings(), \
                contextlib.redirect_stdout(io.StringIO()):
            warnings.simplefilter("ignore")
            kosu = run_correlation(records=[kayit])
        rr = kosu["records"][0]
        satirlar = []
        for taban, skor in sorted(rr.get("scores", {}).items()):
            satir = {"taban": taban, "durum": skor["status"]}
            if skor["status"] == "scored":
                hata = skor["error_pct"]
                satir.update(tahmin_si=skor["predicted_si"],
                             olcum_si=skor["measured_si"], hata_yuzde=hata)
                satir.update(_bant_hukmu(motor, taban, hata, tid, "kayit",
                                         bantlar))
                if satir["hukum"] == KALDI:
                    sonuc["nedenler"].append(
                        f"kayıt yolu {taban}: hata {hata:+.2f} % bant dışı "
                        f"({satir['bant']})")
            else:
                satir["hukum"] = BILGI
            satirlar.append(satir)
        sonuc["kayit_yolu"] = {
            "adaptor_durumu": rr["status"],
            "neden": rr.get("reason"),
            "eksik": rr.get("missing"),
            "anomali": rr.get("anomaly"),
            "kapsam_disi": rr.get("out_of_scope"),
            "satirlar": satirlar,
        }
        if rr["status"] == "runner_error":
            sonuc["nedenler"].append(f"kayıt yolu koşucu hatası: {rr['reason']}")
    if sonuc["nedenler"]:
        sonuc["hukum"] = KALDI
    return sonuc


def vaka_kos(istemci, vaka: Dict[str, Any], kayitlar: Dict[str, Any],
             bantlar: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    adimlar = []
    yanitlar = {}
    for adim in vaka["adimlar"]:
        sonuc, govde = adim_kos(istemci, adim)
        adimlar.append(sonuc)
        yanitlar[adim["ad"]] = govde
    kiyaslar = [kayit_kiyasi(k, yanitlar, kayitlar, bantlar)
                for k in vaka["kayit_kiyasi"]]
    nedenler = [f"{a['ad']}: {n}" for a in adimlar for n in a["nedenler"]]
    nedenler += [f"{k['kayit']}: {n}" for k in kiyaslar for n in k["nedenler"]]
    return {
        "kimlik": vaka["kimlik"],
        "sistem": vaka["sistem"],
        "seviye": vaka["seviye"],
        "gercek_motor": vaka.get("gercek_motor", False),
        "vaka_dosyasi": vaka["_dosya"],
        "vaka_sha256": vaka["_sha256"],
        "sure_s": round(time.perf_counter() - t0, 3),
        "adimlar": adimlar,
        "kayit_kiyasi": kiyaslar,
        "hukum": KALDI if nedenler else GECTI,
        "nedenler": nedenler,
    }


# ---------------------------------------------------------------------------
# Belirlenimcilik ve sürümler arası fark
# ---------------------------------------------------------------------------

def _izlenen_haritasi(vaka_sonucu: Dict[str, Any]) -> Dict[str, Any]:
    return {f"{a['ad']}.{k}": v for a in vaka_sonucu["adimlar"]
            for k, v in a["izlenen"].items()}


def _ayni(a: Any, b: Any) -> bool:
    return _kanonik(a) == _kanonik(b)


def tekrar_kiyasi(kosular: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aynı süreçteki N koşunun izlenen çıktı + parmak izi eşitliği."""
    ilk = kosular[0]
    sapanlar = []
    for sonraki in kosular[1:]:
        a, b = _izlenen_haritasi(ilk), _izlenen_haritasi(sonraki)
        for ad in sorted(set(a) | set(b)):
            if not _ayni(a.get(ad), b.get(ad)):
                sapanlar.append({"cikti": ad, "ilk": a.get(ad),
                                 "tekrar": b.get(ad)})
        for x, y in zip(ilk["adimlar"], sonraki["adimlar"]):
            for anahtar in sorted(set(x["parmak_izi"]) | set(y["parmak_izi"])):
                if x["parmak_izi"].get(anahtar) != y["parmak_izi"].get(anahtar) \
                        and anahtar != "*":
                    sapanlar.append({"yanit_anahtari": f"{x['ad']}.{anahtar}"})
    return {"tekrar_sayisi": len(kosular), "bit_ayni": not sapanlar,
            "sapanlar": sapanlar}


def _goreli_fark(eski: Any, yeni: Any) -> Optional[float]:
    if isinstance(eski, (int, float)) and isinstance(yeni, (int, float)) \
            and not isinstance(eski, bool) and not isinstance(yeni, bool) \
            and eski != 0:
        return (float(yeni) - float(eski)) / abs(float(eski)) * 100.0
    return None


def onceki_kiyasi(simdi: Dict[str, Any], onceki: Dict[str, Any]
                  ) -> Dict[str, Any]:
    ayni_kod = simdi["meta"]["kod_kimligi"] == onceki["meta"]["kod_kimligi"]
    ayni_ortam = simdi["meta"]["is_parcacigi_ortami"] == \
        onceki["meta"]["is_parcacigi_ortami"]
    onceki_vakalar = {v["kimlik"]: v for v in onceki["vakalar"]}
    vakalar = []
    for v in simdi["vakalar"]:
        o = onceki_vakalar.get(v["kimlik"])
        if o is None:
            vakalar.append({"kimlik": v["kimlik"], "durum": "onceki_kosuda_yok"})
            continue
        ayni_vaka = o["vaka_sha256"] == v["vaka_sha256"]
        a, b = _izlenen_haritasi(o), _izlenen_haritasi(v)
        farklar = []
        for ad in sorted(set(a) | set(b)):
            if not _ayni(a.get(ad), b.get(ad)):
                farklar.append({"cikti": ad, "onceki": a.get(ad),
                                "simdi": b.get(ad),
                                "goreli_fark_yuzde": _goreli_fark(a.get(ad),
                                                                  b.get(ad))})
        uyari_farki = []
        oa = {x["ad"]: x for x in o["adimlar"]}
        for adim in v["adimlar"]:
            ox = oa.get(adim["ad"])
            if ox is None:
                continue
            eklenen = [k for k in adim["uyari_kodlari"]
                       if k not in ox["uyari_kodlari"]]
            kalkan = [k for k in ox["uyari_kodlari"]
                      if k not in adim["uyari_kodlari"]]
            if eklenen or kalkan or ox["http_durum"] != adim["http_durum"]:
                uyari_farki.append({"adim": adim["ad"], "eklenen": eklenen,
                                    "kalkan": kalkan,
                                    "http": [ox["http_durum"],
                                             adim["http_durum"]]})
        yanit_farki = []
        for adim in v["adimlar"]:
            ox = oa.get(adim["ad"])
            if ox is None:
                continue
            a_iz, o_iz = adim["parmak_izi"], ox["parmak_izi"]
            for anahtar in sorted(set(a_iz) | set(o_iz)):
                if anahtar != "*" and a_iz.get(anahtar) != o_iz.get(anahtar):
                    yanit_farki.append(f"{adim['ad']}.{anahtar}")
        kayit = {"kimlik": v["kimlik"], "ayni_vaka_dosyasi": ayni_vaka,
                 "farkli_cikti": farklar, "uyari_ve_durum_farki": uyari_farki,
                 "farkli_yanit_anahtari": yanit_farki}
        if ayni_kod and ayni_vaka and ayni_ortam:
            kayit["tur"] = "belirlenimcilik"
            kayit["hukum"] = KALDI if (farklar or uyari_farki
                                       or yanit_farki) else GECTI
        else:
            kayit["tur"] = "fark_raporu"
            kayit["hukum"] = BILGI
        vakalar.append(kayit)
    return {"onceki_kod_kimligi": onceki["meta"]["kod_kimligi"],
            "ayni_kod": ayni_kod, "ayni_is_parcacigi_ortami": ayni_ortam,
            "vakalar": vakalar}


# ---------------------------------------------------------------------------
# Meta, rapor
# ---------------------------------------------------------------------------

def _git(*args: str) -> Optional[str]:
    try:
        cikti = subprocess.run(["git", "-C", DEPO, *args], capture_output=True,
                               timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return cikti.stdout.decode("utf-8", "replace") if cikti.returncode == 0 \
        else None


def kod_kimligi() -> Dict[str, Any]:
    head = (_git("rev-parse", "HEAD") or "").strip() or None
    fark = _git("diff", "HEAD", "--binary", "--", "hrma", "tools/olcut_kos.py")
    return {
        "git_head": head,
        "kirli_fark_sha256": (hashlib.sha256(fark.encode()).hexdigest()[:16]
                              if fark else None),
        # İzlenmeyen (yeni) araç dosyası git farkında görünmez; kendisi ayrıca.
        "arac_sha256": _dosya_sha256(os.path.abspath(__file__))[:16],
    }


def meta_bilgisi() -> Dict[str, Any]:
    import hrma
    try:
        import numpy
        numpy_surumu = numpy.__version__
    except ImportError:  # pragma: no cover
        numpy_surumu = None
    return {
        "hrma_surumu": getattr(hrma, "__version__", None),
        "kod_kimligi": kod_kimligi(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": numpy_surumu,
        "is_parcacigi_ortami": {k: os.environ.get(k) for k in ISIRAN_ORTAM},
        "baslangic_utc": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
    }


def _sayi(deger: Any) -> str:
    if isinstance(deger, bool) or not isinstance(deger, (int, float)):
        return str(deger)
    return f"{deger:.6g}"


def ozet_markdown(sonuc: Dict[str, Any]) -> str:
    m = sonuc["meta"]
    s = [
        "# HRMA ölçüt koşusu",
        "",
        f"- HRMA {m['hrma_surumu']} · git {m['kod_kimligi']['git_head']}"
        f" · kirli fark {m['kod_kimligi']['kirli_fark_sha256']}",
        f"- Başlangıç (UTC): {m['baslangic_utc']} · toplam "
        f"{sonuc['toplam_sure_s']:.1f} s · Python {m['python']}",
        f"- İş parçacığı ortamı: {m['is_parcacigi_ortami']}",
        f"- Genel hüküm: **{sonuc['genel_hukum']}** "
        f"({sonuc['sayim']['GECTI']} geçti, {sonuc['sayim']['KALDI']} kaldı)",
        "",
        "| Vaka | Hüküm | Süre s | Adımlar (HTTP) | Uyarı kodu | Kayıt kıyası |",
        "|---|---|---|---|---|---|",
    ]
    for v in sonuc["vakalar"]:
        adim = ", ".join(f"{a['ad']}({a['http_durum']})" for a in v["adimlar"])
        uyari = sum(len(a["uyari_kodlari"]) for a in v["adimlar"])
        kiyas = ", ".join(f"{k['kayit']}: {k['hukum']}"
                          for k in v["kayit_kiyasi"]) or "—"
        s.append(f"| {v['kimlik']} | {v['hukum']} | {v['sure_s']:.1f} | "
                 f"{adim} | {uyari} | {kiyas} |")
    s += ["", "## İzlenen çıktılar", ""]
    for v in sonuc["vakalar"]:
        s.append(f"### {v['kimlik']}")
        for a in v["adimlar"]:
            if a["izlenen"]:
                s.append(f"- {a['ad']}: " + "; ".join(
                    f"{k} = {_sayi(x)}" for k, x in a["izlenen"].items()))
            if a.get("gecersiz_alanlar"):
                s.append(f"- {a['ad']}: adlı ret {a['gecersiz_alanlar']}")
        for n in v["nedenler"]:
            s.append(f"- **KALDI:** {n}")
        s.append("")
    s += ["## Gerçek motor kıyasları", ""]
    for v in sonuc["vakalar"]:
        for k in v["kayit_kiyasi"]:
            ky = k.get("kayit_yolu")
            if ky:
                s.append(f"- {v['kimlik']} · {k['kayit']} · kayıt yolu "
                         f"adaptör durumu: {ky['adaptor_durumu']}"
                         + (f" (eksik: {', '.join(ky['eksik'])})"
                            if ky.get("eksik") else "")
                         + f" · hüküm {k['hukum']}")
    s += ["",
          "| Vaka | Kayıt | Yol | Büyüklük | Tahmin (SI) | Ölçüm (SI) | "
          "Hata % | Bant | Hüküm |",
          "|---|---|---|---|---|---|---|---|---|"]
    for v in sonuc["vakalar"]:
        for k in v["kayit_kiyasi"]:
            for yol in ("vaka_yolu", "kayit_yolu"):
                for r in (k.get(yol) or {}).get("satirlar", []):
                    hata = r.get("hata_yuzde")
                    s.append(
                        f"| {v['kimlik']} | {k['kayit']} | {yol} | "
                        f"{r.get('taban')} ({r.get('durum')}) | "
                        f"{_sayi(r.get('tahmin_si', '—'))} | "
                        f"{_sayi(r.get('olcum_si', '—'))} | "
                        f"{'—' if hata is None else f'{hata:+.2f}'} | "
                        f"{r.get('bant') or '—'} | {r['hukum']} |")
    if "tekrar" in sonuc:
        s += ["", "## Süreç içi tekrar (belirlenimcilik)", ""]
        for kimlik, t in sonuc["tekrar"].items():
            s.append(f"- {kimlik}: {t['tekrar_sayisi']} koşu, bit aynı = "
                     f"{t['bit_ayni']}" + (f"; sapan: {t['sapanlar'][:5]}"
                                           if t["sapanlar"] else ""))
    if "onceki" in sonuc:
        o = sonuc["onceki"]
        s += ["", "## Önceki koşuyla kıyas", "",
              f"- Önceki kod kimliği: {o['onceki_kod_kimligi']} · aynı kod: "
              f"{o['ayni_kod']} · aynı iş parçacığı ortamı: "
              f"{o['ayni_is_parcacigi_ortami']}", ""]
        for v in o["vakalar"]:
            if v.get("durum") == "onceki_kosuda_yok":
                s.append(f"- {v['kimlik']}: önceki koşuda yok")
                continue
            s.append(f"- {v['kimlik']} [{v['tur']}] {v['hukum']}: "
                     f"{len(v['farkli_cikti'])} çıktı farklı, "
                     f"{len(v['uyari_ve_durum_farki'])} adımda uyarı/durum "
                     f"farkı, {len(v['farkli_yanit_anahtari'])} yanıt anahtarı "
                     f"farklı" + (f" (ilk 8: {v['farkli_yanit_anahtari'][:8]})"
                                  if v["farkli_yanit_anahtari"] else ""))
            for f in v["farkli_cikti"]:
                g = f["goreli_fark_yuzde"]
                s.append(f"  - {f['cikti']}: {_sayi(f['onceki'])} → "
                         f"{_sayi(f['simdi'])}"
                         + ("" if g is None else f" ({g:+.4g} %)"))
            for u in v["uyari_ve_durum_farki"]:
                s.append(f"  - {u['adim']}: +{u['eklenen']} −{u['kalkan']} "
                         f"HTTP {u['http']}")
    s.append("")
    return "\n".join(s)


def kos(vakalar: List[Dict[str, Any]], tekrar: int = 1,
        onceki: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from hrma.validation.experiment_db import load_records

    bantlar = bantlari_yukle()
    gerekli = {k["kayit"] for v in vakalar for k in v["kayit_kiyasi"]}
    kayitlar = {r["test_id"]: r for r in load_records()
                if r.get("test_id") in gerekli}
    meta = meta_bilgisi()
    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="hrma-olcut-") as proje_dizini:
        eski = os.environ.get("HRMA_PROJECTS_DIR")
        os.environ["HRMA_PROJECTS_DIR"] = proje_dizini  # kullanıcı dizinine yazılmaz
        try:
            istemci = _istemci()
            sonuclar = []
            tekrarlar = {}
            for vaka in vakalar:
                kosular = [vaka_kos(istemci, vaka, kayitlar, bantlar)
                           for _ in range(max(1, tekrar))]
                sonuclar.append(kosular[0])
                if tekrar > 1:
                    tekrarlar[vaka["kimlik"]] = tekrar_kiyasi(kosular)
                    if not tekrarlar[vaka["kimlik"]]["bit_ayni"]:
                        kosular[0]["hukum"] = KALDI
                        kosular[0]["nedenler"].append(
                            "süreç içi tekrar bit aynı değil: " + ", ".join(
                                str(x.get("cikti") or x.get("yanit_anahtari"))
                                for x in tekrarlar[vaka["kimlik"]]["sapanlar"]
                                [:10]))
        finally:
            if eski is None:
                os.environ.pop("HRMA_PROJECTS_DIR", None)
            else:
                os.environ["HRMA_PROJECTS_DIR"] = eski
    sonuc: Dict[str, Any] = {
        "sema": SONUC_SEMASI,
        "meta": meta,
        "bant_kaynaklari": bantlar["kaynaklar"],
        "toplam_sure_s": round(time.perf_counter() - t0, 3),
        "vakalar": sonuclar,
    }
    if tekrar > 1:
        sonuc["tekrar"] = tekrarlar
    if onceki is not None:
        sonuc["onceki"] = onceki_kiyasi(sonuc, onceki)
        for k in sonuc["onceki"]["vakalar"]:
            if k.get("hukum") == KALDI:
                v = next(x for x in sonuclar if x["kimlik"] == k["kimlik"])
                v["hukum"] = KALDI
                v["nedenler"].append(
                    "önceki koşuyla (aynı kod + vaka + ortam) bit aynı değil: "
                    + ", ".join([f["cikti"] for f in k["farkli_cikti"]]
                                + k["farkli_yanit_anahtari"])[:600])
    sayim = {GECTI: 0, KALDI: 0}
    for v in sonuclar:
        sayim[v["hukum"]] += 1
    sonuc["sayim"] = sayim
    sonuc["genel_hukum"] = KALDI if sayim[KALDI] else GECTI
    return sonuc


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="HRMA ölçüt koşucusu (olcut/vakalar, arayüzsüz).")
    ap.add_argument("--cikti", required=True,
                    help="olcut_sonuc.json ve olcut_ozet.md yazılacak dizin")
    grup = ap.add_mutually_exclusive_group()
    grup.add_argument("--secim", help="virgüllü vaka kimlikleri")
    grup.add_argument("--hizli", action="store_true",
                      help=f"hızlı alt küme: {', '.join(HIZLI_ALT_KUME)}")
    ap.add_argument("--tekrar", type=int, default=1,
                    help="aynı süreçte vaka başına koşu sayısı (belirlenimcilik)")
    ap.add_argument("--onceki", help="önceki koşunun olcut_sonuc.json'u")
    ap.add_argument("--vaka-dizini", default=VAKA_DIZINI)
    arg = ap.parse_args(argv)
    if arg.tekrar < 1:
        ap.error("--tekrar en az 1")
    secim = (HIZLI_ALT_KUME if arg.hizli else
             [s.strip() for s in arg.secim.split(",")] if arg.secim else None)
    try:
        vakalar = vakalari_yukle(arg.vaka_dizini, list(secim) if secim else None)
        onceki = None
        if arg.onceki:
            with open(arg.onceki, encoding="utf-8") as f:
                onceki = json.load(f)
            if onceki.get("sema") != SONUC_SEMASI:
                raise VakaHatasi(f"--onceki şeması {onceki.get('sema')}")
        sonuc = kos(vakalar, tekrar=arg.tekrar, onceki=onceki)
    except VakaHatasi as hata:
        print(f"HATA: {hata}", file=sys.stderr)
        return 2
    os.makedirs(arg.cikti, exist_ok=True)
    with open(os.path.join(arg.cikti, "olcut_sonuc.json"), "w",
              encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    with open(os.path.join(arg.cikti, "olcut_ozet.md"), "w",
              encoding="utf-8") as f:
        f.write(ozet_markdown(sonuc))
    for v in sonuc["vakalar"]:
        print(f"{v['kimlik']:<10} {v['hukum']:<5} {v['sure_s']:7.1f} s"
              + ("" if not v["nedenler"] else "  " + " | ".join(v["nedenler"])))
    print(f"GENEL: {sonuc['genel_hukum']} {sonuc['sayim']}")
    return 1 if sonuc["genel_hukum"] == KALDI else 0


if __name__ == "__main__":
    raise SystemExit(main())
