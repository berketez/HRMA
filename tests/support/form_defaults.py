"""Şablonun KENDİ ``value=`` varsayılanları — FORM yolunun tek kurucusu.

Neden bu modül (ÖH D35 · OH-ON-03, ÖLÇÜLDÜ 22 Eylül 2026)
----------------------------------------------------------
Bir ``.hrma`` örneği yüklendiğinde arayüz yalnız dosyadaki alanları doldurur;
dosyada OLMAYAN her alan şablonun kendi ``value=`` varsayılanıyla kalır ve
"Hesapla"ya basıldığında toplayıcı (``collectAllParameters``) onları da
gönderir. Yani aynı proje için İKİ yük vardır:

  * API yolu   : yalnız ``inputs.fields`` (örnekleri üreten betiğin yolu),
  * FORM yolu  : ``inputs.fields`` + şablon varsayılanları (kullanıcının yolu).

``docs/scofield/raw/OH/D35/onemli-kati-cad/a1/10_once.json`` A bölümü: katı
örnekte FORM yolu API yolundan 51 alan FAZLA gönderiyordu ve yayımlanan
sayılar ayrışıyordu — Isp 140,109 s ⟷ 125,401 s (%-10,4974), toplam itki
3306,767 N·s ⟷ 2959,642 N·s, c* 915,9 m/s ⟷ 870,105 m/s. Kullanıcı proje
şeridinde 140,1 s görüp Hesapla'ya basınca 125,4 s alıyordu.

``11_once_duyarlilik.json``: o 51 alandan YALNIZ 6'sı yaprağı oynatıyor
(``cf_efficiency``, ``combustion_efficiency``, ``erosion_factor``,
``initial_temp``, ``kinetic_efficiency``, ``nozzle_efficiency``); altısı
birden eklendiğinde sonuç TAM FORM yüküyle bit-aynı çıkıyor
(``asgari_form_ile_AYNI_MI: true``). Hibrit ve sıvı örneklerde kayma YOKTUR
(``12_once_hibrit_sivi.json``: altı yaprakta da %0,0).

TEK KAYNAK (Doktrin 4): sayılar BURADA YAZILMAZ. Şablonun ``value=``
öznitelikleri ``tests.support.inventory.field_specs`` ile okunur; sayfadaki
varsayılan değişirse bu modül onu kendiliğinden görür.
"""

from __future__ import annotations

from typing import Dict, Iterable, Set

from tests.support import inventory


def _html(sayfa: str) -> str:
    return inventory._read(inventory.PAGES[sayfa][0])


def toplayicinin_okudugu_alanlar(sayfa: str) -> Set[str]:
    """Şablonda HERHANGİ bir yerde okunan alan id'leri (toplayıcı + yardımcı).

    Toplayıcı gövdesi değil ŞABLONUN TAMAMI taranır: bazı sayfalar alanları
    alt fonksiyonlarda okur (``inventory.build`` aynı gerekçeyle böyle yapar).
    """
    return inventory.collected_fields(_html(sayfa))


def sayisal_varsayilanlar(sayfa: str) -> Dict[str, float]:
    """Sayfanın gönderdiği SAYI alanlarının şablon varsayılanları.

    Kapsam bilerek dardır ve beyanlıdır:

      * yalnız toplayıcının okuduğu alanlar (okunmayan alan gönderilmez),
      * yalnız ``kind == 'number'`` (onay kutusunun ``value`` özniteliği bir
        varsayılan DEĞİL, gönderilecek değerdir; ``select`` varsayılanı
        ``selected`` özniteliğinden gelir, ``value=``den değil),
      * yalnız ``value=`` dolu olanlar — boş bırakılan alan formda da boştur
        ve ÖK-21 gereği anahtarı hiç gönderilmez.

    Sayı ÜRETİLMEZ: değer şablonun kendi ``value=`` özniteliğidir.
    """
    html = _html(sayfa)
    okunan = inventory.collected_fields(html)
    out: Dict[str, float] = {}
    for alan, spec in inventory.field_specs(html).items():
        if alan not in okunan or spec.kind != 'number':
            continue
        if spec.default in (None, ''):
            continue
        try:
            out[alan] = float(spec.default)
        except (TypeError, ValueError):
            continue
    return out


def eksik_form_alanlari(sayfa: str, alanlar: Iterable[str]) -> Dict[str, float]:
    """Belgede OLMAYAN, ama formun varsayılanıyla göndereceği sayı alanları."""
    var = set(alanlar)
    return {ad: deger for ad, deger in sayisal_varsayilanlar(sayfa).items()
            if ad not in var}


def form_yuku(motor_type: str, fields: Dict) -> Dict:
    """``inputs.fields`` -> KULLANICININ gördüğü yük (form varsayılanları dâhil).

    ``calculate_payload`` API yolunu kurar; bu işlev onun üstüne sayfanın
    doldurduğu boşlukları ekler. İkisi arasındaki fark ``.hrma``nın
    taşımadığı her alandır.
    """
    from tests.test_example_projects import calculate_payload
    sayfa = SAYFA[motor_type]
    yuk = calculate_payload(motor_type, fields)
    yuk.update(eksik_form_alanlari(sayfa, yuk))
    return yuk


#: motor_type -> şablon sayfası (``inventory.PAGES`` anahtarı).
SAYFA = {'hybrid': 'hybrid', 'solid': 'solid', 'liquid': 'liquid'}
