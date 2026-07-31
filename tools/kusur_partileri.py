#!/usr/bin/env python3
"""Sabit çıktı bulgularını çakışmasız yazma partilerine ayırır.

Neden: 138 kusur birden fazla ajanla kapatılacak. İki ajan aynı dosyaya
yazarsa son yazan kazanır ve diğerinin işi sessizce kaybolur (14 Mayıs 2026
dersi). Bu araç partileri **elle değil ölçümden** üretir: her kalemin
dokunacağı dosya kümesi çıkarılır, aynı dosyayı paylaşan kalemler tek
bileşende toplanır, bileşenler partilere dağıtılır. Sonuçta hiçbir dosya iki
partide görünmez.

Kullanım:
    python3 tools/kusur_partileri.py
    python3 tools/kusur_partileri.py --rapor <yol> --cikti <yol>

Çıktı: docs/dev/kusur_partileri.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VARSAYILAN_RAPOR = os.path.expanduser(
    "~/HRMA-kurtarma/takim-raporlari/sabit-bulgular.json"
)
VARSAYILAN_CIKTI = os.path.join(REPO, "docs", "dev", "kusur_partileri.json")

# Bu dosyalar merkezî düğüm: pek çok kalem onlara dokunur. Paralel yazılmaz,
# ana model tek elden işler.
HUB_DOSYALAR = {"app.py"}

#: Dosya adı ve varsa ardındaki satır numarası (`injector_design.py:1291`).
DOSYA_DESENI = re.compile(r"([A-Za-z0-9_./-]+\.(?:py|js|html))(?::(\d+))?")

# Rapor metninde geçen ama depoda karşılığı olmayan adları elemek için
# kullanılan dizinler.
ARAMA_DIZINLERI = ("hrma", "tools", "tests")


def satir_sayisi(goreli_yol: str) -> int:
    try:
        with open(os.path.join(REPO, goreli_yol), encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def depo_dosyalarini_indeksle() -> dict[str, list[str]]:
    """Dosya adı -> depo içindeki tam yolların listesi."""
    indeks: dict[str, list[str]] = defaultdict(list)
    for kok in ARAMA_DIZINLERI:
        tam_kok = os.path.join(REPO, kok)
        if not os.path.isdir(tam_kok):
            continue
        for dizin, _alt, dosyalar in os.walk(tam_kok):
            if "__pycache__" in dizin or "/node_modules" in dizin:
                continue
            for ad in dosyalar:
                if ad.endswith((".py", ".js", ".html")):
                    goreli = os.path.relpath(os.path.join(dizin, ad), REPO)
                    indeks[ad].append(goreli)
    return indeks


def kalemin_dosyalari(kalem: dict, indeks: dict[str, list[str]]) -> set[str]:
    """Kalemin YAZILACAĞI dosyalar.

    `mevcut_fonksiyon` bilerek dışarıda: orası okunacak kaynak, düzenlenecek
    yer değil. Düzenleme `nerede` (mevcut sabitin bulunduğu yer) ve
    `onerilen_baglama` (yapılacak değişiklik) alanlarında tarif edilir.
    """
    metin = " ".join(
        str(kalem.get(alan) or "") for alan in ("nerede", "onerilen_baglama")
    )
    bulunan: set[str] = set()
    belirsiz: list[str] = []
    for ham, satir in DOSYA_DESENI.findall(metin):
        ad = ham.split("/")[-1]
        adaylar = indeks.get(ad)
        if not adaylar:
            continue  # depoda yok — rapor metnindeki serbest ad
        if len(adaylar) == 1:
            bulunan.add(adaylar[0])
            continue

        # 1) Rapor tam yol ipucu verdiyse (hrma/engines/x.py) onu kullan.
        ipucu = ham.strip("/")
        kalanlar = [y for y in adaylar if y.endswith(ipucu)] if "/" in ipucu else list(adaylar)

        # 2) Satır numarası verildiyse o satıra sahip olmayan adayları ele.
        #    (`injector_design.py:1291` — utils sürümü 1058 satır, olamaz.)
        if satir and len(kalanlar) > 1:
            n = int(satir)
            uyanlar = [y for y in kalanlar if satir_sayisi(y) >= n]
            if uyanlar:
                kalanlar = uyanlar

        if len(kalanlar) == 1:
            bulunan.add(kalanlar[0])
        else:
            # Ayırt edilemedi: sessizce tahmin etme, kayda geç ve insana bırak.
            secilen = sorted(kalanlar)[0]
            bulunan.add(secilen)
            belirsiz.append(f"{ham}{':' + satir if satir else ''} -> {secilen} (adaylar: {', '.join(sorted(kalanlar))})")

    if belirsiz:
        kalem.setdefault("_belirsiz_dosyalar", []).extend(belirsiz)
    return bulunan


class BirlesimBul:
    """Union-find: aynı dosyaya dokunan kalemleri tek bileşene toplar."""

    def __init__(self) -> None:
        self.ata: dict[str, str] = {}

    def bul(self, x: str) -> str:
        self.ata.setdefault(x, x)
        while self.ata[x] != x:
            self.ata[x] = self.ata[self.ata[x]]
            x = self.ata[x]
        return x

    def birlestir(self, a: str, b: str) -> None:
        ka, kb = self.bul(a), self.bul(b)
        if ka != kb:
            self.ata[kb] = ka


def partileri_uret(rapor_yolu: str, parti_tavani: int = 60) -> dict:
    with open(rapor_yolu, encoding="utf-8") as f:
        gruplar = json.load(f)

    indeks = depo_dosyalarini_indeksle()

    kusurlar = []
    for grup in gruplar:
        for kalem in grup.get("kalemler", []):
            if kalem.get("sinif") != "KUSUR":
                continue
            kayit = dict(kalem)
            kayit["_grup"] = grup.get("grup", "")
            # kayit'e (kopyaya) geçir: belirsizlik kaydı çıktıya girsin.
            kayit["_dosyalar"] = sorted(kalemin_dosyalari(kayit, indeks))
            kusurlar.append(kayit)

    # Sınıflandırma:
    #   seri   — hub'a (app.py) dokunanlar ve dosyası çıkarılamayanlar
    #   tekil  — tek dosyaya dokunanlar: doğal sahip o dosyadır
    #   köprü  — birden çok dosyaya dokunanlar: iki aileyi birbirine bağlar
    seri_hub, seri_dosyasiz, tekil, kopru = [], [], [], []
    for k in kusurlar:
        adlar = {os.path.basename(d) for d in k["_dosyalar"]}
        if adlar & HUB_DOSYALAR:
            seri_hub.append(k)
        elif not k["_dosyalar"]:
            seri_dosyasiz.append(k)
        elif len(k["_dosyalar"]) == 1:
            tekil.append(k)
        else:
            kopru.append(k)

    # Tekil kalemler dosyalarına göre kümelenir — bunlar tanım gereği çakışmaz.
    uf = BirlesimBul()
    kume: dict[str, list[dict]] = defaultdict(list)
    for k in tekil:
        dosya = k["_dosyalar"][0]
        uf.bul(f"f:{dosya}")
        kume[f"f:{dosya}"].append(k)

    def kok_boyut(kok: str) -> int:
        return sum(len(v) for a, v in kume.items() if uf.bul(a) == kok)

    # Köprü kalemleri: bağladıkları aileleri birleştirmek partiyi tavanın
    # üstüne çıkarmıyorsa birleştir, çıkarıyorsa kalemi seriye al. Böylece
    # birkaç köprü yüzünden 123 kalemin tek bloba çökmesi engellenir.
    kopru_seri = []
    for k in sorted(kopru, key=lambda x: len(x["_dosyalar"])):
        kokler = {uf.bul(f"f:{d}") for d in k["_dosyalar"]}
        birlesik = sum(kok_boyut(kk) for kk in kokler) + 1
        if birlesik <= parti_tavani:
            ilk = sorted(kokler)[0]
            for kk in kokler:
                uf.birlestir(ilk, kk)
            kume.setdefault(f"f:{k['_dosyalar'][0]}", []).append(k)
        else:
            kopru_seri.append(k)

    bilesenler: dict[str, list[dict]] = defaultdict(list)
    for anahtar, kalemler in kume.items():
        bilesenler[uf.bul(anahtar)].extend(kalemler)

    partiler = []
    for sira, bilesen in enumerate(
        sorted(bilesenler.values(), key=len, reverse=True), start=1
    ):
        partiler.append(
            {
                "ad": f"P{sira}",
                "sahip": "ajan",
                "dosyalar": sorted({d for k in bilesen for d in k["_dosyalar"]}),
                "kalem_sayisi": len(bilesen),
                "kalemler": bilesen,
            }
        )

    # Seri parti: hub + köprü + dosyası çıkarılamayanlar. Ana model tek elden
    # işler, bu yüzden diğer partilerin dosyalarına dokunması sorun değil —
    # ajanlar bittikten SONRA çalışır.
    seri = seri_hub + kopru_seri + seri_dosyasiz
    if seri:
        partiler.append(
            {
                "ad": f"P{len(partiler) + 1}",
                "sahip": "ana model",
                "dosyalar": sorted({d for k in seri for d in k["_dosyalar"]}),
                "kalem_sayisi": len(seri),
                "kalemler": seri,
                "seri": True,
                "not": (
                    f"{len(seri_hub)} hub (app.py) + {len(kopru_seri)} köprü + "
                    f"{len(seri_dosyasiz)} yeri belirsiz — ajanlardan SONRA, tek elden"
                ),
            }
        )

    return {
        "kaynak": rapor_yolu,
        "toplam_kusur": len(kusurlar),
        "parti_sayisi": len(partiler),
        "partiler": partiler,
    }


def cakisma_denetimi(sonuc: dict) -> list[str]:
    """İki PARALEL parti aynı dosyaya yazıyorsa hata döndürür.

    Seri parti (ana model) denetim dışıdır: ajanlar bittikten sonra tek elden
    çalıştığı için dosya paylaşması eşzamanlı yazma değildir.
    """
    sahip: dict[str, str] = {}
    hatalar = []
    for parti in sonuc["partiler"]:
        if parti.get("seri"):
            continue
        for d in parti["dosyalar"]:
            if d in sahip and sahip[d] != parti["ad"]:
                hatalar.append(f"{d}: {sahip[d]} ve {parti['ad']} ikisi de yazacak")
            sahip[d] = parti["ad"]
    return hatalar


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rapor", default=VARSAYILAN_RAPOR)
    ap.add_argument("--cikti", default=VARSAYILAN_CIKTI)
    ap.add_argument(
        "--tavan",
        type=int,
        default=60,
        help="Bir partinin taşıyabileceği en fazla kalem; aşan köprüler seriye düşer",
    )
    args = ap.parse_args()

    if not os.path.exists(args.rapor):
        print(f"Rapor bulunamadı: {args.rapor}", file=sys.stderr)
        return 1

    sonuc = partileri_uret(args.rapor, parti_tavani=args.tavan)
    hatalar = cakisma_denetimi(sonuc)

    os.makedirs(os.path.dirname(args.cikti), exist_ok=True)
    with open(args.cikti, "w", encoding="utf-8") as f:
        json.dump(sonuc, f, ensure_ascii=False, indent=2)

    print(f"Toplam kusur: {sonuc['toplam_kusur']}")
    print(f"Parti sayısı: {sonuc['parti_sayisi']}\n")
    for parti in sonuc["partiler"]:
        dosya_ozeti = ", ".join(os.path.basename(d) for d in parti["dosyalar"][:4])
        if len(parti["dosyalar"]) > 4:
            dosya_ozeti += f" (+{len(parti['dosyalar']) - 4})"
        print(
            f"  {parti['ad']:4s} {parti['kalem_sayisi']:3d} kalem  "
            f"[{parti['sahip']}]  {dosya_ozeti or '(dosya yok)'}"
        )
        if parti.get("not"):
            print(f"        not: {parti['not']}")

    belirsizler = [
        (p["ad"], k["yol"], b)
        for p in sonuc["partiler"]
        for k in p["kalemler"]
        for b in k.get("_belirsiz_dosyalar", [])
    ]
    if belirsizler:
        print(f"\nAYIRT EDİLEMEYEN DOSYA ADI ({len(belirsizler)}) — elle teyit edilmeli:")
        for parti, yol, b in belirsizler:
            print(f"  {parti}  {yol[:55]}")
            print(f"        {b}")

    print(f"\nYazıldı: {args.cikti}")

    if hatalar:
        print("\nÇAKIŞMA VAR:", file=sys.stderr)
        for h in hatalar:
            print("  -", h, file=sys.stderr)
        return 2

    print("Çakışma denetimi: temiz — hiçbir dosya iki partide değil.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
