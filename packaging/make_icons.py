#!/usr/bin/env python3
"""HRMA simge üretimi — macOS 26 (Tahoe) simge standardizasyonu için.

NEDEN BU DOSYA VAR (v2.6.25 saha hatası)
----------------------------------------
Kullanıcı, uygulama KAPALIYKEN Dock/Finder simgesinin bozuk göründüğünü
bildirdi: gri bir sistem karosunun içine küçültülmüş ikinci bir lacivert karo
(karo içinde karo). Uygulama AÇIKKEN simge doğru görünüyordu.

Ölçülen sebep: macOS 26 Tahoe, ``Assets.car`` (Icon Composer varlığı)
taşımayan uygulamaların eski ``.icns`` sanatını KENDİ yuvarlatılmış karosunun
içine gömer. Bizim sanatımız zaten kendi yuvarlatılmış karosunu çiziyor ve
1024 tuvalin yalnız %80,5'ini dolduruyordu (macOS Big Sur ızgarası) — sonuç
iki kat karo.

Doğrulama (NSWorkspace.iconForFile_ ile üç bundle karşılaştırıldı):
    mevcut sanat  (dolu 0.805) -> karo içinde karo        BOZUK
    tam taşma     (dolu 1.000) -> tek karo, tam yuva      DOĞRU
    Brave (referans, Assets.car'lı)                       DOĞRU ile birebir

Yani Xcode/actool gerekmiyor: sanat eserini TUVALİN TAMAMINA yaymak yeterli,
yuvarlatmayı sistem yapıyor.

İKİ AYRI VARLIK ÜRETİLİR
------------------------
1. ``icon.icns``  — TAM TAŞMA. Bundle simgesi; Finder, Dock (kapalıyken),
   Launchpad burayı okur ve sistem maskesini uygular.
2. ``icon_runtime.png`` — YUVARLATILMIŞ (kendi karosu, %80,5 dolu).
   ``launcher.py`` çalışma anında ``setApplicationIconImage_`` ile bunu verir.
   O çağrı sistem maskesini BYPASS eder, ham görüntüyü çizer; oraya tam taşma
   vermek keskin köşeli bir kare üretirdi. İki varlık bu yüzden ayrı.

Windows (``hrma.ico``) DEĞİŞMEZ: Windows simgeye sistem karosu uygulamaz,
tam taşma orada keskin köşeli kare olarak görünürdü. Mevcut yuvarlatılmış
sanat Windows için doğrudur.

Kullanım:
    python3 packaging/make_icons.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

BURASI = os.path.dirname(os.path.abspath(__file__))
KAYNAK = os.path.join(BURASI, "icon_1024.png")

#: macOS .icns için gereken kenar uzunlukları (her biri ayrıca @2x üretilir).
BOYUTLAR = (16, 32, 128, 256, 512)


def tam_tasma_uret(kaynak_png):
    """Yuvarlatılmış sanatı tuvalin tamamını dolduran opak kareye çevirir.

    Alfa sınırlayıcı kutusuna kırpar, 1024'e büyütür ve saydam köşeleri
    sanatın kendi zemin rengiyle doldurur — böylece sistem maskesi
    uygulandığında köşelerde boşluk kalmaz.
    """
    im = Image.open(kaynak_png).convert("RGBA")
    kutu = im.split()[3].getbbox()
    if kutu is None:
        raise SystemExit("Kaynak simge tamamen saydam: %s" % kaynak_png)
    kirpik = im.crop(kutu)
    yayilmis = kirpik.resize((1024, 1024), Image.LANCZOS)
    # Zemin rengi: karonun sol kenar ortası (glif değil, arka plan)
    zemin = kirpik.getpixel((int(kirpik.width * 0.12), kirpik.height // 2))
    tuval = Image.new("RGBA", (1024, 1024), zemin[:3] + (255,))
    tuval.alpha_composite(yayilmis)
    return tuval


def icns_yaz(kaynak_im, hedef_icns):
    """Verilen 1024 görüntüden .icns üretir (iconutil ile)."""
    gecici = tempfile.mkdtemp(prefix="hrma-icon-")
    try:
        iconset = os.path.join(gecici, "icon.iconset")
        os.makedirs(iconset)
        for kenar in BOYUTLAR:
            kaynak_im.resize((kenar, kenar), Image.LANCZOS).save(
                os.path.join(iconset, "icon_%dx%d.png" % (kenar, kenar)))
            kaynak_im.resize((kenar * 2, kenar * 2), Image.LANCZOS).save(
                os.path.join(iconset, "icon_%dx%d@2x.png" % (kenar, kenar)))
        subprocess.run(
            ["iconutil", "-c", "icns", iconset, "-o", hedef_icns], check=True)
    finally:
        shutil.rmtree(gecici, ignore_errors=True)


def main():
    if sys.platform != "darwin":
        raise SystemExit("iconutil yalnız macOS'ta var; bu betik macOS'ta koşar.")
    if not os.path.isfile(KAYNAK):
        raise SystemExit("Kaynak bulunamadı: %s" % KAYNAK)

    tam = tam_tasma_uret(KAYNAK)
    tam_yol = os.path.join(BURASI, "icon_1024_fullbleed.png")
    tam.save(tam_yol)

    icns_yol = os.path.join(BURASI, "icon.icns")
    icns_yaz(tam, icns_yol)

    # Çalışma anı simgesi: yuvarlatılmış ORİJİNAL sanat, olduğu gibi.
    calisma_yol = os.path.join(BURASI, "icon_runtime.png")
    shutil.copyfile(KAYNAK, calisma_yol)

    print("icon.icns              (tam taşma, bundle simgesi)  yazıldı")
    print("icon_1024_fullbleed.png (üretim kaynağı)            yazıldı")
    print("icon_runtime.png       (yuvarlak, çalışma anı)      yazıldı")


if __name__ == "__main__":
    main()
