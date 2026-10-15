# -*- coding: utf-8 -*-
"""Bağıl fark yüzdesi — ``hrma.validation`` paketinin TEK tanım noktası.

ÖH D29 / app-api-dogrulama a1 · defter P10B2-16.

ÖLÇÜLEN KUSUR (taban ``4c27fa51``, ``once.json`` -> ``P10B2-16``): aynı
paket içinde İKİ ayrı yüzde sözleşmesi yan yana duruyordu ve hangisinin
hangi büyüklüğe böldüğü yalnızca kaynak koddan okunabiliyordu:

    user_data_validation._pct_diff(ölçülen=1000, tahmin=1100)  ->  -9,0909 %
    correlation_runner.score_record  (aynı çift)               -> +10,0000 %

İşaret ZIT, büyüklük 0,909 puan farklı — çünkü biri TAHMİNE, öteki ÖLÇÜME
bölüyordu. Aynı iki sayı, aynı paketten, iki farklı cevap.

Bu modül formülü bir kez yazar ve KİMİN REFERANS olduğunu çağıranın ADIYLA
söylemesini ZORUNLU kılar (``reference=`` bir rol adıdır, serbest metin
değil). Böylece üçüncü bir sözleşmenin sessizce eklenmesi imkânsızdır:
yeni çağıran da referansını ilan etmek zorundadır.

REFERANS SEÇİMİ BİR ÜRÜN KARARIYDI ve VERİLDİ (ÖH D30 / OH-D28-12,
ana model hükmü 9 Eylül 2026): KANON ÖLÇÜMDÜR — metroloji geleneği
(ASME V&V 20-2009 Böl. 2: E = S − D, D deneysel veri) ölçümü referans
alır. ``correlation_runner`` bunu zaten uyguluyordu; ``user_data_validation``
tarihsel olarak tahmine bölüyordu ve D30'da kanona hizalandı. Yayımlanan
``*_diff_pct`` alanlarının işareti bu yüzden kaydı (sürüm notu borcu).
Payda hâlâ her çağırandan ADIYLA istenir ve yayımlanan sözlükte
makine-okunur biçimde durur: kanon sessizce geri kayamaz.
"""

from __future__ import annotations

#: Geçerli referans rolleri. Serbest metin kabul edilmez (ÖK-04: dize
#: kopyalamak yerine ad okunur).
REFERENCE_MEASUREMENT = 'measurement'   # ASME V&V 20: deneysel veriye bölünür
REFERENCE_PREDICTION = 'prediction'     # modele/tahmine bölünür

_REFERENCES = (REFERENCE_MEASUREMENT, REFERENCE_PREDICTION)

#: PAKET KANONU (ÖH D30 / OH-D28-12 + P10B2-16; ana model kararı hüküm-18,
#: 9 Eylül 2026). Bu paketin YAYIMLADIĞI her bağıl fark ÖLÇÜME bölünür.
#: D29'da formül tekilleşmiş ama iki payda yan yana bırakılmıştı; ölçüm
#: (``docs/scofield/raw/OH/D30/app-api-dogrulama/a1/once.json``) aynı çiftin
#: iki modülde ZIT İŞARETLİ iki yüzde ürettiğini gösterdi. Kanon tektir.
#:
#: :data:`REFERENCE_PREDICTION` SÖKÜLMEDİ ama YAYIMLANAN yoldan çıkarıldı:
#: rolü ADIYLA isteyen bir rapor (ör. "tahmine göre sapma" sütunu) onu
#: açıkça geçirebilir; hiçbir çağıran ONU VARSAYILAN OLARAK ALAMAZ, çünkü
#: ``reference=`` zorunlu anahtar sözcüktür. Bugün paket içinde yayımlanan
#: yolda kullanan YOKTUR (bekçi: ``tests/test_d30_app_api_dogrulama_a1.py``).
CANONICAL_REFERENCE = REFERENCE_MEASUREMENT


def relative_difference_pct(value: float, reference_value: float, *,
                            reference: str) -> float:
    """``(value - reference_value) / reference_value * 100``.

    Args:
        value: karşılaştırılan büyüklük.
        reference_value: PAYDA — bölünen referans.
        reference: paydanın ROLÜ; :data:`REFERENCE_MEASUREMENT` ya da
            :data:`REFERENCE_PREDICTION`. Zorunludur ve anahtar sözcükle
            verilir: bir yüzdenin neye göre olduğu yayımlanabilir bir
            olgudur, çağıranın hatırlamasına bırakılmaz.

    Raises:
        ValueError: rol tanınmıyor ya da payda sıfır (sessiz ``inf``/``nan``
            üretilmez — fail-closed).
    """
    if reference not in _REFERENCES:
        raise ValueError(
            f'reference must be one of {_REFERENCES}; got {reference!r}')
    payda = float(reference_value)
    if payda == 0.0:
        raise ValueError(
            f'relative difference is undefined against a zero {reference}')
    return (float(value) - payda) / payda * 100.0
