# -*- coding: utf-8 -*-
"""ÖH Dalga-24 · arayüz · aşama-1 bekçileri — **OH-Z1-02**.

Kalem üç şey söylüyordu:

1. ``OX_REF_DENSITY`` sayı tablosu ``simple.html`` ve ``uzaytek.html``
   içinde KOPYA duruyor (aynı üç sayı iki dosyada).
2. h2o2 görünümü ayrışıyor: şablon 1438 (%98 gerçeği), uç 1450 (merkezî
   tablonun %98 etiketli %100 değeri) — kullanıcı iki sayı görebilir.
3. Rozet/durum metinleri için EN+TR i18n borcu ödenmemiş
   (``i18n_pages.js`` yazılamamış).

ÖLÇÜM (2026-09-05, taban 88a29d3):

* (1) ve (2) daha önceki dalgalarda KAPANMIŞ. Sayı tablosu yalnız
  ``hrma/static/js/oxidizer_reference_density.js`` içinde yazılı
  (D17), uç ile ön yüz 1438,1 ⟷ 1438,0'da buluşuyor (28 Ağustos etiket
  dürüstlüğü kararı). Bu dosya o iki kazanımı KİLİTLER: geri gelirlerse
  kırmızı yanar.
* (3) AÇIKTI ve bu aşamada kapatıldı. İki sayfa da i18n çekirdeğini hiç
  yüklemiyordu; ``docs/scofield/raw/OH/D24/arayuz/a1/once_i18n.json``:
  simple.html 48, uzaytek.html 139 işaretlenmemiş görünür metin, sıfır
  ``data-i18n``, sıfır sözlük anahtarı. Ana menüden Türkçe seçmek bu iki
  sayfada HİÇBİR ŞEYİ değiştirmiyordu.

Sözleşmenin GENİŞ yüzü ``tests/test_i18n_pages.py`` içindedir (iki sayfa
oraya eklendi: sözdizimi, iki yönlü anahtar tutarlılığı, EN/TR eşitliği,
kapsam, terim sözlüğü, altyapı). Buradakiler kalemin KENDİ iddialarıdır.

ÖH D36 SÖKÜMÜ (Berke, 23 Eylül 2026 — dalga36/sokum): iki sayfa, onların
sözlük anahtarları ve yalnız onların yüklediği
``oxidizer_reference_density.js`` TAMAMEN söküldü. Yalnız sökülen yüzeyi
ölçen 13 düğüm emekli (aşağıda adlarıyla); h2o2 düğümünün ÜRÜN ayağı (uç ⟷
merkezî tablo, 1450 değil) kalır. Geri dönüş bekçisi:
``tests/test_d36_sokum_a1.py``.
"""

import os


# ---------------------------------------------------------------------------
# 1. Sayı tablosu TEK KAYNAK
# ---------------------------------------------------------------------------
# test_oksitleyici_referans_tablosu_tek_dosyada, test_sablonlar_tabloyu_panelden_okuyor,
# test_kunye_betimleyicileri_de_kopya_degil (3 düğüm) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum


# ---------------------------------------------------------------------------
# 2. h2o2: ön yüz ⟷ uç ayrışması
# ---------------------------------------------------------------------------
def test_h2o2_uc_ve_merkezi_tablo_ayni_sayiyi_soyluyor():
    """Kalem iddiası: şablon 1438, uç 1450 gösteriyordu.

    1450 kg/m³ %100 SAF H₂O₂'nin 20 °C değeridir; ürünün kimliği ise
    "Hydrogen Peroxide (98%)". %98 çözeltinin 293,15 K değeri 1438,1'dir.

    ÖH D36 sökümü (Berke 23 Eyl, dalga36/sokum): ön yüzdeki kopya tablo
    (``oxidizer_reference_density.js``) tek tüketicisi olan iki sayfayla
    birlikte söküldü; ön yüz ayağı emekli. Düğümün ÜRÜN ayağı kalır: uç,
    merkezî tablonun (``PropellantDatabase``) söylediği sayıyı söyler ve
    bu sayı %100 saf değeri (1450) DEĞİLDİR.
    """
    os.environ.setdefault('HRMA_HEADLESS', '1')
    from hrma.app import app
    from hrma.data.propellant_database import propellant_db

    with app.test_client() as c:
        yanit = c.post('/api/get-propellant-properties',
                       json={'propellant_type': 'oxidizer',
                             'propellant_name': 'h2o2'})
    assert yanit.status_code == 200, yanit.status_code
    uc = (yanit.get_json() or {}).get('properties', {}).get('density')
    assert isinstance(uc, (int, float)), 'uç yoğunluk vermedi: %r' % uc
    merkez = (propellant_db.get_propellant_properties('h2o2') or {}).get(
        'density')
    assert isinstance(merkez, (int, float)), 'merkezî tabloda h2o2 yok'
    assert abs(uc - merkez) <= 0.2, (
        'h2o2 yoğunluğu ayrışıyor: merkezî tablo %.1f, uç %.1f kg/m³'
        % (merkez, uc))
    assert abs(uc - 1450.0) > 1.0, (
        'uç %.1f kg/m³ döndürüyor: bu %%100 saf H2O2 değeridir, ürünün '
        'kimliği ise %%98 çözelti (etiket dürüstlüğü kararı, 28 Ağustos).'
        % uc)


# ---------------------------------------------------------------------------
# 3. i18n borcu: iki sayfa da dil seçimini GÖRÜYOR
# ---------------------------------------------------------------------------
# test_sayfa_i18n_katmanini_yukluyor, test_sayfa_dil_secicisini_basiyor,
# test_dil_degisince_sonuclar_yeniden_ciziliyor,
# test_sayfada_isaretlenmemis_gorunur_metin_kalmadi (4 × 2 = 8 düğüm) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum
# test_sozlukte_iki_sayfanin_metinleri_var (1 düğüm; simple. 82 / uzt. 213 tabanı) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum
# test_iki_sayfa_da_gercekten_servis_ediliyor (1 düğüm) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum
