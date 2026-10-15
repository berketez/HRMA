"""
Motor Data Validation and Error Handling Module
Professional validation for safety-critical rocket motor parameters
"""

import math

import numpy as np
from typing import Dict, Tuple, Optional, List

# ÖH D29 / P15B2-01: deger katmani kapilarinin TEK KAYNAGI.
# ÖH D30 / OH-D29-07: istek sinirindaki "bu bir JSON sayisi mi" kurali da
# ayni merkezden okunur — kural uc yerde uc kez YAZILMAZ.
from hrma.utils.input_guard import finite_number, is_json_number
# ÖH D29 / P16B1-44: ortam sicakligi zarfi — sayi burada YAZILMAZ, okunur.
from hrma.constants import AMBIENT_TEMPERATURE_BAND_K


def _num(value):
    """Sayisal girdiyi float'a zorlar; sayiya cevrilemiyorsa None doner.

    v2.6.26 — DOGRULAYICI STRING GIRDIDE COKUYORDU. Bu modul degerleri
    ``motor_data.get(...)`` ile ham okuyup dogrudan carpiyordu; kayitli bir
    proje ya da API cagrisi sayiyi metin olarak tasidiginda (ornegin
    ``{"chamber_pressure": "20"}``) ``chamber_p * safety_factor`` satiri
    ``TypeError: can't multiply sequence by non-int`` veriyordu. Kullanici,
    girdisinin neresinin yanlis oldugunu soyleyen bir mesaj yerine ic Python
    hatasi goruyordu — oysa dogrulayicinin isi tam olarak bunu onlemek.

    None donmesi "bu alan sayisal degil" demektir; cagiran taraf o kontrolu
    ATLAR, sessizce 0 varsaymaz.

    ÖH D29 / app-api-dogrulama a1 · defter P15B2-01 — MERKEZE BAĞLANDI.
    Kural artik ``hrma.utils.input_guard.finite_number``dadir; bu ad yalniz
    okunabilirlik icin durur. Yerel kopya iki noktada merkezden AYRISIYORDU
    (olculdu, ``once.json`` -> ``P15B2-01``): ``numpy.bool_`` Python
    ``bool``un alt sinifi DEGILDIR, yani ``np.bool_(True)`` bu kapidan
    1,0 olarak geciyordu; merkez ``dtype.kind == 'b'`` ordek denetimiyle
    onu da eler.
    """
    return finite_number(value)


#: ÜRÜN ALAN ADI -> KANONİK BANT ADI (ÖH Z5S / S3, P16B1-37 + P16B1-36).
#:
#: ÖLÇÜLDÜ (28 Ağustos 2026, ``docs/scofield/raw/OH/Z5S/s3/once_supurme.json``):
#: ``MotorDataValidator.limits`` 14 bant tanımlıyor ama hibrit ``/calculate``
#: yükünde bunların yalnız 4'ü (``thrust``, ``burn_time``, ``chamber_pressure``,
#: ``of_ratio``) görülüyordu. Kalan 10'u ULAŞILAMAZDI — kapı vardı, KANAL ADI
#: TUTMUYORDU. Aynı sayı iki farklı adla iki farklı hükme uğruyordu:
#:
#:     {"temperature": -500}          -> HTTP 400, "outside valid range"
#:     {"chamber_temperature": -500}  -> HTTP 200, tam motor tasarımı
#:
#: Bu tablo o boşluğu kapatır. Bant DEĞERLERİ DEĞİŞMEZ (yeni eşik icat etmek
#: Berke kararıdır); yalnızca ürünün gerçekten gönderdiği adla ULAŞILABİLİR
#: hâle gelirler.
#:
#: NEDEN DÜZ BİR AD EŞLEMESİ DEĞİL — ÜÇ TUZAK ÖLÇÜLDÜ:
#:
#: 1. BİRİM. ``chamber_diameter_input`` MİLİMETREdir
#:    (``hybrid_rocket_engine.py``: ``chamber_diameter_input / 1000``), kanonik
#:    ``chamber_diameter`` bandı ise METRE. Düz eşleme, ürünün meşru 100 mm'lik
#:    haznesini "100 m, [0,01; 5] m dışında" diye reddederdi. Bu yüzden her
#:    girdi bir ÇARPAN taşır ve hata mesajı bandı KULLANICININ BİRİMİNDE yazar.
#: 2. "0 = OTOMATİK". ``chamber_diameter_input``, ``initial_port_diameter`` ve
#:    ``chamber_length_override`` arayüzde ``value="0"`` ile doğar ve motor
#:    ``> 0`` değilse alanı "verilmedi" sayar. Bu üç alanda 0, bir ölçüm değil
#:    "sen boyutlandır" işaretidir; bandın altında kalır ama REDDEDİLEMEZ.
#:    (Deponun "0 ile verilmedi karıştırılmaz" ilkesi burada tersine işler:
#:    alanın KENDİ sözleşmesi 0'ı yokluk sayar.)
#: 3. BİRİM ÇELİŞKİSİ. ``chamber_length_override`` için ürün ile motor AYNI
#:    FİKİRDE DEĞİL: arayüz milimetre gönderiyor (``advanced.html`` değişkeni
#:    ``chamberLenMm``, ``step_import_ui.js`` eşlemesi ``chamber_length_mm``),
#:    motor ise metre okuyor (``_resolve_chamber_length_override``: 20'nin
#:    üstünü "birim karışıklığı" diye reddediyor). Hangisinin doğru olduğu bir
#:    BİRİM KANONU kararıdır ve bu turun işi değildir. Bu yüzden o alana tek
#:    okumaya dayalı bir bant DAYATILMAZ: iki okumanın BİRLEŞİMİ uygulanır,
#:    yani yalnız HER İKİ okumada da imkânsız olan değer reddedilir. Böylece
#:    ürünün bugün gönderdiği hiçbir meşru sayı yanlışlıkla reddedilmez, ama
#:    1e9 / NaN gibi hiçbir okumada anlamı olmayan girdi kapıyı geçemez.
#:
#: Alanlar: ``kanonik`` bant adı; ``carpanlar`` ürün biriminden kanonik birime
#: (birden fazlaysa birim çelişkilidir, birleşim uygulanır); ``birim`` mesajda
#: yazılacak etiket; ``sifir_otomatik`` 0'ın "verilmedi" demek olup olmadığı;
#: ``bos_verilmedi`` boş dizenin ("") "verilmedi" demek olup olmadığı.
#:
#: ``bos_verilmedi`` NEDEN VAR (ÖH D29 / P16B1-44). Boş dize varsayılan olarak
#: bir SAYI DEĞİLDİR ve reddedilir; ama bir alanın KENDİ sözleşmesi boşu
#: "verilmedi" sayıyorsa kapı o sözleşmeyi izler, kendi kuralını dayatmaz.
#: ``ambient_temp`` böyledir: ``hybrid_rocket_engine._resolve_ambient_
#: temperature`` ilk satırında ``if value is None or value == '': return
#: None`` der ve ``advanced.html`` alanı ``value=""`` ile doğar. Bayrak
#: yalnız o sözleşmeyi YANSITIR; yeni bir hüküm kurmaz.
FIELD_ALIASES = {
    'chamber_temperature': {
        'kanonik': 'temperature', 'carpanlar': (1.0,), 'birim': 'K',
        'sifir_otomatik': False, 'bos_verilmedi': False,
    },
    'chamber_diameter_input': {
        'kanonik': 'chamber_diameter', 'carpanlar': (0.001,), 'birim': 'mm',
        'sifir_otomatik': True, 'bos_verilmedi': False,
    },
    'chamber_length_override': {
        'kanonik': 'chamber_length', 'carpanlar': (1.0, 0.001),
        'birim': 'm or mm', 'sifir_otomatik': True, 'bos_verilmedi': False,
    },
    'initial_port_diameter': {
        'kanonik': 'port_diameter', 'carpanlar': (1.0,), 'birim': 'm',
        'sifir_otomatik': True, 'bos_verilmedi': False,
    },
    # ÖH D29 / P16B1-44 — ORTAM SICAKLIĞI. Kanal vardı, kapı yoktu.
    # ÖLÇÜLDÜ (``a2/once.json`` K1): ``ambient_temp``in 14 sarsımının 14'ü
    # kabul ediliyordu (``1e9``, ham ``NaN``, ham ``Infinity``, ``-1``, 0,
    # ``[1,2]``, ``"NaN"`` dâhil) ve HTTP 200 dönüyordu. Motorun zarfı
    # (``_resolve_ambient_temperature``) bant dışını SESSİZCE düşürüp
    # ``defaults_used``a not yazıyordu: kullanıcının sayısı uygulanmıyor
    # ama isteği de reddedilmiyordu (Doktrin 1 — beyan çözüm değildir).
    # Bant YENİ DEĞİL: ``hrma.constants.AMBIENT_TEMPERATURE_BAND_K``,
    # motorun kendi zarfı. 0 burada "otomatik" DEĞİLDİR — üç arayüz
    # alanının aksine ``advanced.html`` boş bırakılan ortam sıcaklığını
    # HİÇ GÖNDERMEZ (``optNum`` -> ``null`` ise alan eklenmez), yani 0
    # gerçekten gönderilmiş bir ölçümdür ve 0 K bir ölçüm olamaz.
    'ambient_temp': {
        'kanonik': 'ambient_temperature', 'carpanlar': (1.0,), 'birim': 'K',
        'sifir_otomatik': False, 'bos_verilmedi': True,
    },
}


#: KANONİK BANT ADI -> (ürünün GERÇEKTEN OKUNAN alan adı, o adın birimi).
#:
#: Bu İKİNCİ BİR TABLO DEĞİLDİR: yukarıdaki ``FIELD_ALIASES``in tersidir ve
#: ondan türetilir (Doktrin 4, tek kaynak). Yeni bir alan ``FIELD_ALIASES``e
#: girdiğinde burası kendiliğinden büyür.
#:
#: NEDEN GEREKLİ (ÖH D26 / OH-D25-19): ``FIELD_ALIASES`` "ürün adıyla gelen
#: sayı kanonik bandı görsün" yönünü kapatır. TERS yön açıktı: kanonik ADIN
#: KENDİSİ gövdede gönderildiğinde bant uygulanıyor (bant dışı 400 alıyor)
#: ama uç o adı HİÇ OKUMUYOR. Yani alan doğrulanıyor, sonra sessizce
#: düşüyor.
CANONICAL_TO_PRODUCT_FIELD = {
    tanim['kanonik']: (urun_ad, tanim['birim'])
    for urun_ad, tanim in FIELD_ALIASES.items()
}


#: KANONİK BANT TABLOSU — **SI KANONU** (ÖH D26 / P16B1-49 B ayağı).
#:
#: Bu sözlük ``MotorDataValidator.__init__`` içinde ELLE yazılıydı; oradan
#: modül düzeyine ALINDI, sayıları DEĞİŞMEDİ. Taşınmasının tek sebebi
#: aşağıdaki ``FORM_LIMITS``in ondan TÜRETİLEBİLMESİ: bir tablo, kendisinden
#: sonra tanımlanan bir sınıfın gövdesinden okuyamaz.
#:
#: KANON KARARI (ana model hükmü, 7 Eylül 2026). Kalemin B ayağı D25'te
#: ölçülüp açık bırakılmıştı; engel gerekçesi "hangi okumanın KANON olduğu
#: AYRI bir birim-kanonu kararı" idi. Karar şudur:
#:
#:     **Kanon SI'dir** (metre, bar, kelvin, saniye, newton) ve bu tabloda
#:     yazılıdır. Form/uç katmanının bandı KENDİ SAYISINI TUTAMAZ;
#:     kullanıcının birimindeki (mm) görünümü buradan TÜRETİLİR.
#:
#: Karar yeni bir doktrin değil, deponun KENDİ emsalidir:
#:   * ``hrma/analysis/bolted_joint.py::seal_diameter_max_mm`` —
#:     "Tek kaynak ``MotorDataValidator.limits['chamber_diameter']``
#:     (max 5,0 m)" deyip ``* 1e3`` ile mm görünümünü üretiyor;
#:   * ``hrma/export/motor_geometry.py::_plausible_band_m`` — birim çözümünü
#:     yalnız ``unit == 'm'`` olan kanonik banda dayandırıyor;
#:   * ``hrma/analysis/pressure_vessel.py`` ve ``safety_analysis.py`` aynı
#:     tabloyu sıcaklık kanonu olarak okuyor.
#:
#: ÖLÇÜLDÜ (``docs/scofield/raw/OH/D26/app-api/a2/once.json`` K1/K2): aynı
#: fiziksel alanın (``chamber_diameter``) mm cinsinden ÜST SINIRI üründe İKİ
#: FARKLI SAYIYLA dolaşıyordu — ``FORM_LIMITS['solid']`` 2000, kanondan
#: türeten ``seal_diameter_max_mm`` 5000. ``grain_length`` için 5000 ⟷ 10000.
#: İki tablonun ALT uçları zaten birebir örtüşüyordu (10 = 0,01 × 1000;
#: 50 = 0,05 × 1000), yani bu girdiler kanondan TÜRETİLMİŞ ama üst uçları
#: sonradan elle yazılmıştı: tek kaynağın yarısı kopmuştu.
CANONICAL_LIMITS = {
    'thrust': {'min': 10, 'max': 1000000, 'unit': 'N'},  # 10N to 1MN
    'chamber_pressure': {'min': 1, 'max': 500, 'unit': 'bar'},  # 1 to 500 bar
    'burn_time': {'min': 0.1, 'max': 300, 'unit': 's'},  # 0.1s to 5 minutes
    'chamber_diameter': {'min': 0.01, 'max': 5.0, 'unit': 'm'},  # 1cm to 5m
    'chamber_length': {'min': 0.05, 'max': 20.0, 'unit': 'm'},  # 5cm to 20m
    'throat_diameter': {'min': 0.001, 'max': 2.0, 'unit': 'm'},  # 1mm to 2m
    'exit_diameter': {'min': 0.002, 'max': 5.0, 'unit': 'm'},  # 2mm to 5m
    'of_ratio': {'min': 0.5, 'max': 20.0, 'unit': ''},  # O/F ratio
    'mixture_ratio': {'min': 0.5, 'max': 20.0, 'unit': ''},  # Mixture ratio
    'port_diameter': {'min': 0.005, 'max': 1.0, 'unit': 'm'},  # 5mm to 1m
    'grain_length': {'min': 0.05, 'max': 10.0, 'unit': 'm'},  # 5cm to 10m
    'web_thickness': {'min': 0.001, 'max': 0.5, 'unit': 'm'},  # 1mm to 50cm
    'tank_pressure': {'min': 5, 'max': 700, 'unit': 'bar'},  # 5 to 700 bar
    'temperature': {'min': 200, 'max': 5000, 'unit': 'K'},  # 200K to 5000K
    # ÖH D29 / P16B1-44 — ORTAM sıcaklığı ODA sıcaklığı DEĞİLDİR ve
    # ``temperature`` bandını (200-5000 K, yanma odası kanonu) paylaşamaz:
    # o bant 5000 K'lik bir "ortamı" kabul eder, alt ucu ise ürünün kendi
    # arayüzünün izin verdiği 180 K'i REDDEDERDİ. Sayı burada YAZILMAZ,
    # ``hrma.constants``tan okunur (Doktrin 4) — kaynağı motorun kendi
    # zarfıdır, bkz. ``AMBIENT_TEMPERATURE_BAND_SOURCE``.
    'ambient_temperature': {'min': AMBIENT_TEMPERATURE_BAND_K[0],
                            'max': AMBIENT_TEMPERATURE_BAND_K[1],
                            'unit': 'K'},
}


def canonical_band_m(alan):
    """``alan`` için kanonik METRE bandı ``(min, max)``, yoksa ``None``.

    Birimi ``'m'`` OLMAYAN satırlar (bar, K, N, s) bilerek dışarıda kalır:
    bu fonksiyonun tek işi UZUNLUK kanonunu yayımlamaktır. Tek kaynak
    :data:`CANONICAL_LIMITS`; burada sayı yazılmaz.
    """
    band = CANONICAL_LIMITS.get(alan)
    if not isinstance(band, dict) or band.get('unit') != 'm':
        return None
    try:
        return float(band['min']), float(band['max'])
    except (KeyError, TypeError, ValueError):   # pragma: no cover - bozuk tablo
        return None


#: Kanonik tabloda ÇAP olan alanlar. Liste ADLARDAN ibarettir; her birinin
#: sayısal bandı yukarıdaki tablodan okunur.
DIAMETER_CANONICAL_FIELDS = ('chamber_diameter', 'throat_diameter',
                             'exit_diameter', 'port_diameter')

#: BİRİM ÇIKARIM TAVANI [m] — ÖK-16 / defter P7B1-06 (eski kimlik P15B2-04).
#:
#: Üst seviye motor sonuçları uzunluğun birimini BEYAN ETMEDİĞİ için dışa
#: aktarım hattı (``hrma/export/motor_geometry.py::length_in_meters``) birimi
#: büyüklükten çıkarır: ``f > tavan -> değer milimetredir``. O tavan bugüne
#: kadar ``motor_geometry`` içinde ELLE ``1.0`` yazılıydı ve bu, aynı fiziksel
#: büyüklüğün İKİNCİ ve ÇELİŞEN bir zarfı demekti — kanonik
#: ``chamber_diameter`` bandının üst ucu 5,0 m'dir.
#:
#: ÖLÇÜLDÜ (``docs/scofield/raw/OH/D31/app-api-dogrulama/a1/once.json``,
#: bölüm B1/B2): 10 dışa aktarım alanının 5'inde eşik ile kanonik bandın üst
#: ucu ayrışıyordu ve ayrışma CANLI bir kusur üretiyordu — kanonik bandın
#: İÇİNDEki (meşru) bir kasa çapı milimetre sayılıyordu:
#:
#:   ===========================  =========  =============  ==============
#:   girdi (case_outer_diameter)  kanon içi  okunan (önce)  okunan (sonra)
#:   ===========================  =========  =============  ==============
#:   1,5                          evet       0,0015 m       1,5 m
#:   2,5                          evet       0,0025 m       2,5 m
#:   4,9                          evet       0,0049 m       4,9 m
#:   100,0                        hayır      0,1 m          0,1 m
#:   ===========================  =========  =============  ==============
#:
#: Yani 1,5 m'lik bir kasa ``.eng`` başlığına 1,5 MİLİMETRE olarak giriyordu
#: (1000 kat). ``case_outer_diameter`` kanonik tabloda YOKTUR, dolayısıyla
#: iki-okuma birleşim kuralına (``length_in_meters_banded``) düşemez ve
#: tek-eşikli yolda kalır; tavan yanlışsa sayı sessizce yeniden yorumlanır.
#:
#: Tavan burada SAYIYLA yazılmaz, kanondan TÜRETİLİR: ürünün kendi zarfında
#: bir çapın alabileceği EN BÜYÜK meşru metre değeri, çap alanlarının kanonik
#: üst uçlarının en büyüğüdür. Bandı olan alan zaten kendi bandını kullanır
#: (birleşim kuralı); bu tavan yalnız bandı OLMAYAN çap alanlarının yedeğidir.
#:
#: Emsal: ``hrma/analysis/bolted_joint.py::seal_diameter_max_mm`` aynı tablodan
#: ``* 1e3`` ile mm görünümünü türetiyor (CLAUDE.md kural 11 / Doktrin 4).
DIAMETER_UNIT_INFERENCE_MAX_M = max(
    CANONICAL_LIMITS[_alan]['max'] for _alan in DIAMETER_CANONICAL_FIELDS)


#: Kanonik tabloda EKSEN BOYU olan alanlar. Liste ADLARDAN ibarettir; her
#: birinin sayısal bandı yukarıdaki tablodan okunur.
LENGTH_CANONICAL_FIELDS = ('chamber_length', 'grain_length')

#: BİRİM ÇIKARIM TAVANI [m] — UZUNLUK tarafı (ÖH D32; defter P7B1-06'nın
#: D31'den devredilen ayağı. ÇAP tarafı için bkz.
#: :data:`DIAMETER_UNIT_INFERENCE_MAX_M`).
#:
#: ``motor_geometry.LENGTH_SI_MAX_M`` bugüne kadar ELLE ``5.0`` yazılıydı ve
#: doğrulayıcının KENDİ kanonuyla çelişiyordu: ``chamber_length`` bandının üst
#: ucu **20,0 m**, ``grain_length``ınki 10,0 m'dir. Aynı fiziksel büyüklüğün
#: İKİ ve çelişen zarfı (CLAUDE.md kural 11 / Doktrin 4).
#:
#: ÖLÇÜLDÜ (``docs/scofield/raw/OH/D32/app-api-dogrulama/a1/once.json``,
#: bölüm B1/B3): dışa aktarım tablosundaki 10 alandan 3'ü — ``nozzle_length``,
#: ``nozzle_convergent_length``, ``nozzle_divergent_length`` — kanonik tabloda
#: YOKTUR, dolayısıyla iki-okuma birleşim kuralına (``length_in_meters_banded``)
#: düşemez ve tek-eşikli yolda kalır. Orada eşik yanlışsa sayı sessizce yeniden
#: yorumlanır:
#:
#:   ================  ======================  ==============  ==============
#:   girdi (nozzle_*)  kanonik boy bandı içi   okunan (önce)   okunan (sonra)
#:   ================  ======================  ==============  ==============
#:   6,0               evet ([0,05; 20,0])     0,006 m (mm)    6,0 m (si)
#:   12,0              evet                    0,012 m (mm)    12,0 m (si)
#:   19,0              evet                    0,019 m (mm)    19,0 m (si)
#:   21,0              hayır                   0,021 m (mm)    0,021 m (mm)
#:   350,0             hayır                   0,35 m (mm)     0,35 m (mm)
#:   ================  ======================  ==============  ==============
#:
#: Yani 6 m'lik meşru bir lüle imalat paketine 6 MİLİMETRE olarak giriyordu
#: (1000 kat) — ``case_outer_diameter`` için D31'de ölçülen kusurun uzunluk
#: tarafındaki ikizi. Bu boyların gerçekliğini ürünün KENDİ ölçümü söylüyor:
#: ÖH D15 / harita H1a tek alan sarsımıyla 6,733 m / 6,897 m / 17,318 m kamara
#: boyları üretmişti (``tests/test_d15_harita.py`` sınıf gövdesi).
#:
#: Tavan burada SAYIYLA yazılmaz, kanondan TÜRETİLİR: ürünün kendi zarfında bir
#: eksen boyunun alabileceği EN BÜYÜK meşru metre değeri, boy alanlarının
#: kanonik üst uçlarının en büyüğüdür. Bandı OLAN alan zaten kendi bandını
#: kullanır; bu tavan yalnız bandı OLMAYAN boy alanlarının yedeğidir.
#:
#: KAPSAM DIŞI — ``motor_geometry.THICKNESS_SI_MAX_M`` (0,1 m): ``wall_thickness``
#: / ``recommended_thickness`` için kullanılıyor. Kanonik tablodaki
#: ``web_thickness`` (katı yakıt AĞI, üst uç 0,5 m) BAŞKA bir büyüklüktür;
#: ondan cidar kalınlığı tavanı türetilemez. Kanonik kaynak yok → sayı
#: uydurulmadı, sabit olduğu yerde bırakıldı (fail-closed).
LENGTH_UNIT_INFERENCE_MAX_M = max(
    CANONICAL_LIMITS[_alan]['max'] for _alan in LENGTH_CANONICAL_FIELDS)


#: KANONİK BİRİM -> GÖRÜNTÜ BİRİMİ çarpanı. Burada YALNIZ BİRİM ÇEVRİMİ
#: vardır; hiçbir katsayı fiziksel bir karar taşımaz. Yeni bir görüntü birimi
#: (cm, inç) gerekirse buraya girer ve aşağıdaki kanon denetimi onu da bağlar.
GORUNUM_CARPANI = {
    ('m', 'm'): 1.0,
    ('m', 'mm'): 1000.0,
}


def kanon_gorunumu(kanonik, birim):
    """Kanonik SI bandının ``birim`` cinsinden GÖRÜNÜMÜ — YENİ SAYI DEĞİL.

    ``FORM_LIMITS`` girdisini elle yazmak yerine bununla üretmek, aynı bandın
    iki yerde iki farklı sayıyla durmasını (Doktrin 4 ihlali) YAPISAL olarak
    imkânsız kılar: form katmanı bandın DEĞERİNİ değil yalnız GÖRÜNTÜ
    BİRİMİNİ seçer.

    Raises:
        KeyError: bilinmeyen kanonik ad ya da tanımsız birim çifti. Sessiz
            yedek YOKTUR (fail-closed): tablo tutarsızsa modül yüklenmez.
    """
    band = CANONICAL_LIMITS[kanonik]
    carpan = GORUNUM_CARPANI[(band['unit'], birim)]
    return (band['min'] * carpan, band['max'] * carpan, birim)


#: MOTOR FORMUNA GÖRE UÇ BANTLARI — TEK KAYNAK (ÖH Z5S / S3, P16B2-12).
#:
#: ÖLÇÜLDÜ: aynı fiziksel alanın üç formda üç farklı bandı vardı ve üçü de
#: ``app.py`` içinde ELLE YAZILMIŞ sabitlerdi (``validate_input_range(...,
#: 5, 200, ...)`` gibi 13 çağrı). ``chamber_pressure = 3 bar`` hibritte 200,
#: katıda 400, sıvıda 400 dönüyordu; hiçbir yanıt kabul edilen bandı
#: SÖYLEMİYORDU, yani kullanıcı aynı sayıyı üç sekmeye yazıp neden birinin
#: kabul edilip ikisinin reddedildiğini öğrenemiyordu.
#:
#: DEĞERLER AYNEN KORUNDU — bu tablo bir davranış değişikliği değil, dağınık
#: sabitlerin tek kaynağa toplanmasıdır. Bant farklarının kendisi (5-200 ⟷
#: 10-500 ⟷ 1-500) fiziksel bir gerekçeye mi dayanıyor yoksa tarihsel bir
#: kaza mı olduğu AYRI bir karardır (Berke'lik); burada yalnız kaynak
#: tekilleştirilir ve bant yanıtta BEYAN EDİLİR.
#:
#: Biçim: ``{form: {alan: (alt, ust, birim_etiketi)}}``. Uç katmanı bandı
#: buradan okur ve reddi ``field`` + ``accepted_range`` + ``unit`` +
#: ``motor_form`` ile makine-okur hâlde yayımlar.
#: ÖH D21 / P16B1-11 + P16B1-17 — HİBRİT ODA BANTLARI TEK NESNEDİR.
#:
#: İki tüketici daha (``/api/advanced-analysis`` ısı kolu ve
#: ``/api/find-optimum-of``) bugüne kadar BANTSIZ koşuyordu. Bandı oraya
#: KOPYALAMAK aynı sayıyı üçüncü ve dördüncü kez yazmak olurdu (Doktrin 4:
#: tek kaynak). Bunun yerine hibrit formunun kendi iki bandı adlandırıldı;
#: yeni form girdileri AYNI demeti gösterir. ``quick_geometry`` satırları
#: bit-aynı kalır ve YENİ BİR SAYI YAZILMAZ.
_HIBRIT_ODA_BASINCI_BANDI = (1, 500, 'bar')
_HIBRIT_ODA_SICAKLIGI_BANDI = (300, 6000, 'K')

FORM_LIMITS = {
    # /api/quick-geometry (hibrit ön geometri)
    'quick_geometry': {
        'chamber_pressure': _HIBRIT_ODA_BASINCI_BANDI,
        'thrust': (1, 1e7, 'N'),
        'burn_time': (0.1, 1000, 's'),
        'of_ratio': (0.1, 50, ''),
        'chamber_temperature': _HIBRIT_ODA_SICAKLIGI_BANDI,
    },
    # /calculate_solid
    'solid': {
        # ÖH D26 / P16B1-49 (B ayağı) — BİRİM ÇELİŞKİSİ, KANONDAN TÜRETİLDİ.
        # Bu iki satır elle yazılı (10, 2000) ve (50, 5000) idi; kanonun mm
        # görünümü ise (10, 5000) ve (50, 10000). ALT uçlar zaten örtüşüyordu,
        # ÜST uçlar kopmuştu. Sayı İCAT EDİLMEDİ: kanonun kendi üst sınırının
        # mm karşılığı yazılır — ``bolted_joint.seal_diameter_max_mm()``in
        # ürettiği 5000 mm ile aynı ifade. Ölçüm ve gerekçe:
        # ``docs/scofield/raw/OH/D26/app-api/a2/rapor.md`` §1.
        'chamber_diameter': kanon_gorunumu('chamber_diameter', 'mm'),
        'grain_length': kanon_gorunumu('grain_length', 'mm'),
        'chamber_pressure': (5, 200, 'bar'),
        'burn_rate_a': (0.0001, 0.1, ''),
        'burn_rate_n': (-0.5, 1.0, ''),
    },
    # /calculate_liquid
    'liquid': {
        'thrust': (100, 1e7, 'N'),
        'chamber_pressure': (10, 500, 'bar'),
        'mixture_ratio': (0.5, 20, ''),
    },
    # ÖH D21 / P16B1-11 — /api/advanced-analysis ısı transferi kolu.
    # ÖLÇÜLDÜ (``once.json`` K5, taban ``4cf44f8``): ``motor_data.
    # chamber_temperature = 1e9`` HTTP 200 + ``chamber_heat_flux =
    # 6,035480180542779e+27`` W/m² + ``adiabatic_wall_temperature =
    # 994 442 521,4 K`` yayımlıyordu. Kardeş hibrit ucu (``/api/
    # quick-geometry``) AYNI alanı AYNI bantla zaten reddediyor; eksik
    # olan tek şey aynı bandın bu kola bağlanmasıydı.
    'advanced_heat_transfer': {
        'chamber_temperature': _HIBRIT_ODA_SICAKLIGI_BANDI,
    },
    # ÖH D21 / P16B1-17 — /api/find-optimum-of.
    # ÖLÇÜLDÜ (``once.json`` K11): ``chamber_pressure = 1e9`` (bar) HTTP
    # 200 + ``max_isp = 356,53`` s; ``2e6`` (Pa'nın bar sanılması) HTTP
    # 200 + ``max_isp = 354,99`` s. İki fiziksel imkânsız basınç da
    # "optimum" hükmü üretiyordu.
    'find_optimum_of': {
        'chamber_pressure': _HIBRIT_ODA_BASINCI_BANDI,
    },
}


#: BANDI OLMAYAN ama SAYISAL olan alanlar — ÖH D30 / defter P12bB1-12 ve
#: OH-D29-07.
#:
#: ÖLÇÜLDÜ (``docs/scofield/raw/OH/D30/app-api-dogrulama/a1/once.json``,
#: taban ``ab7cf68b``): aşağıdaki alanların HİÇBİRİ ``CANONICAL_LIMITS``,
#: ``FIELD_ALIASES`` ya da ``FORM_LIMITS`` tablolarında YOKTU; ``liquid.html``
#: girdilerinde de ``min``/``max`` niteliği yoktu. D29 arayuz-panel a1 bandı
#: ölçülebilen üç alana koydu ve kalan altısı için **bant UYDURMADI** —
#: doğru karar: bir alanın meşru büyüklüğü aracın kendi tasarımına bağlıysa
#: (roket kütlesi, referans alanı) ona sayı dayatmak mühendislik uydurmasıdır
#: (Doktrin 4 + Doktrin 6; emsal: :meth:`_besleme_basinci_sorunlari`).
#:
#: BANT YOKTUR AMA KAPI VARDIR. Bandı olmayan alan "her şey serbest"
#: demek değildir: FİZİK hâlâ konuşur — bir kütle, alan, süre ya da O/F
#: oranı sonlu ve pozitif olmak zorundadır. Bu tablo o ayrımı MAKİNE-OKUR
#: biçimde yazar: ``sayisal`` (tel biçimi sayı olmalı) ve ``pozitif``
#: (fiziksel işaret kısıtı). Bant DEĞERİ İCAT EDİLMEZ; künye
#: :func:`accepted_range_kunyesi` ile "band yok" diye BEYAN EDİLİR.
#:
#: ``gerekce`` alanı, kısıtın nereden geldiğini söyler — sayı değil, olgu.
NUMERIC_ONLY_FIELDS = {
    # OH-D29-07: sayı-benzeri DİZE bu alanda kabul ediliyordu (HTTP 200),
    # aynı biçimdeki dize /calculate_solid ve /calculate_liquid'de 400
    # alıyordu. Bandı yok (bir oksitleyici deposu sıcaklığının ürün
    # genelinde ölçülmüş bir zarfı YOK), ama tel biçimi kuralı ortaktır.
    'oxidizer_temp': {'sayisal': True, 'pozitif': True,
                      'gerekce': 'mutlak sıcaklık: 0 K altı yoktur'},
    # P12bB1-12 kalan 6 alan — bant yok, fizik var.
    'stoichiometric_of': {'sayisal': True, 'pozitif': True,
                          'gerekce': 'kütle oranı: negatif/sıfır tanımsız'},
    'initial_mass': {'sayisal': True, 'pozitif': True,
                     'gerekce': 'kütle pozitiftir (traj_initial_mass)'},
    'final_mass': {'sayisal': True, 'pozitif': True,
                   'gerekce': 'kütle pozitiftir (traj_final_mass)'},
    'drag_coefficient': {'sayisal': True, 'pozitif': True,
                         'gerekce': 'sürükleme katsayısı pozitiftir '
                                    '(traj_drag_coeff)'},
    'reference_area': {'sayisal': True, 'pozitif': True,
                       'gerekce': 'alan pozitiftir (traj_ref_area)'},
    # ``traj_burn_time`` BURAYA GİRMEZ: aynı büyüklüğün KANONİK bandı zaten
    # var (``CANONICAL_LIMITS['burn_time']`` = 0,1-300 s) ve
    # :func:`accepted_range_kunyesi` onu döndürür. Alanı "bant yok" diye
    # yazmak ölçüme AYKIRI olurdu — altı alanın yalnız BEŞİ bandsızdır.
}


def accepted_range_kunyesi(field, form=None):
    """Bir alanın KABUL BANDI künyesi — TEK KAYNAK, uydurma YOK.

    ÖH D30 / defter P12bB1-12. Uç katmanı ve arayüz aynı soruyu soruyor:
    "bu alanın kabul edilen aralığı nedir?" Yanıt bugüne kadar üç yerden
    (kanon tablosu, form tablosu, HTML ``min``/``max``) parça parça
    okunuyordu; bandı OLMAYAN alan için ise hiçbir yanıt yoktu — sessizlik
    "bant var ama söylemiyoruz" ile "bant yok" arasındaki farkı siliyordu.

    Döner: ``field``, ``accepted_range`` (``[alt, ust]`` ya da ``None``),
    ``unit``, ``basis`` ve ``band_yok``.

    ``basis`` değerleri:
      * ``form_band`` — ``FORM_LIMITS[form][field]``
      * ``canonical_band`` — ``CANONICAL_LIMITS[field]`` (SI kanonu)
      * ``alias_band`` — ``FIELD_ALIASES`` üzerinden kanona bağlı
      * ``physical_only`` — SAYISAL BANT YOK; yalnız fiziksel kısıt
        (:data:`NUMERIC_ONLY_FIELDS`), ``limits`` alanında adıyla yazılı
      * ``unknown`` — alan bu üründe tanınmıyor (beyan: bilinmiyor)

    Sayı ÜRETMEZ: bilinmeyen alana bant uydurmaz, ``None`` yayımlar.
    """
    if form is not None and field in FORM_LIMITS.get(form, {}):
        alt, ust, birim = FORM_LIMITS[form][field]
        return {'field': field, 'accepted_range': [alt, ust], 'unit': birim,
                'basis': 'form_band', 'band_yok': False}
    if field in CANONICAL_LIMITS:
        band = CANONICAL_LIMITS[field]
        return {'field': field, 'accepted_range': [band['min'], band['max']],
                'unit': band['unit'], 'basis': 'canonical_band',
                'band_yok': False}
    takma = FIELD_ALIASES.get(field)
    if takma is not None and takma['kanonik'] in CANONICAL_LIMITS:
        band = CANONICAL_LIMITS[takma['kanonik']]
        altlar = [band['min'] / c for c in takma['carpanlar']]
        ustler = [band['max'] / c for c in takma['carpanlar']]
        return {'field': field, 'accepted_range': [min(altlar), max(ustler)],
                'unit': takma['birim'], 'basis': 'alias_band',
                'band_yok': False}
    kural = NUMERIC_ONLY_FIELDS.get(field)
    if kural is not None:
        limitler = ['finite']
        if kural['pozitif']:
            limitler.append('> 0')
        return {'field': field, 'accepted_range': None, 'unit': None,
                'basis': 'physical_only', 'band_yok': True,
                'limits': limitler, 'reason': kural['gerekce']}
    return {'field': field, 'accepted_range': None, 'unit': None,
            'basis': 'unknown', 'band_yok': True}


def _bandsiz_sayisal_sorun(param, value):
    r"""Bandı olmayan SAYISAL alanın tip + fiziksel işaret kapısı.

    ÖH D30 / P12bB1-12 + OH-D29-07. ``(mesaj, makine_kaydi)`` döner; sorun
    yoksa ``(None, None)``. Mesaj BİÇİMLERİ mevcut ikisiyle birebir aynıdır
    (``i18n_charts.js`` süzgeçleri: ``^(.+) must be numeric, got (.+)$`` ve
    ``^(.+) = (.+) is outside valid range \[(.+)\] (.*)$``), yani yeni bir
    çeviri borcu DOĞMAZ.
    """
    kural = NUMERIC_ONLY_FIELDS.get(param)
    if kural is None:
        return None, None
    if not (is_json_number(value) or isinstance(value, bool)):
        # ÖH D32 / OH-D31-10 — gerekçe kodu kanonu: tel-biçimi reddinin
        # adı merkezin adıdır (``input_guard.is_json_number``).
        # ``not_a_number`` EMEKLİ. Mesaj BİÇİMİ değişmedi (i18n süzgeci).
        return (f"{param} must be numeric, got {type(value).__name__}",
                {'field': param, 'reason': 'not_a_json_number',
                 'value': str(value)[:60], 'resolved_as': None,
                 'accepted_range': None, 'band_yok': True})
    sayi = float(value)
    sonlu = math.isfinite(sayi)
    if sonlu and (not kural['pozitif'] or sayi > 0.0):
        return None, None
    limitler = 'finite' + (', > 0' if kural['pozitif'] else '')
    return (f"{param} = {value} is outside valid range [{limitler}] "
            f"({kural['gerekce']})",
            {'field': param,
             'reason': 'not_finite' if not sonlu else 'not_positive',
             'value': (str(value) if not sonlu else sayi),
             'accepted_range': None, 'band_yok': True,
             'limits': limitler, 'resolved_as': None})


def _bant_kanonu_denetimi():
    """BANT KANONU — modül yüklenirken uygulanan fail-closed değişmez.

    ÖH D26 / P16B1-49 (B ayağı). İki kural denetlenir; ihlali ``RuntimeError``
    ile modülü yüklenmez kılar, çünkü bant tablosu tutarsızken hangi sayının
    uygulandığı KOŞUM SIRASINA kalır ve bu sessiz bir ret/kabul kaymasıdır.

    KURAL 1 — BİRİM ÇELİŞKİSİ AYRI SAYI TUTAMAZ. Bir ``FORM_LIMITS``
    girdisinin adı kanonik bir bant adıysa ve BİRİM ETİKETİ kanonikten
    farklıysa, o girdi kanonik bandın SALT BİRİM ÇEVRİMİ olmak zorundadır.
    (Birim etiketi AYNI olduğunda sayı farkı forma özgü bir DARALTMADIR —
    ``solid.chamber_pressure`` 5-200 ⟷ kanon 1-500 gibi — ve o farkın
    fiziksel mi tarihsel mi olduğu deponun kendi beyanına göre AYRI bir
    karardır. Bu denetim onlara dokunmaz.)

    KURAL 2 — ARAMA SIRASI BELİRSİZ OLAMAZ. ``_band_kaydi`` önce kanonik
    adı, sonra ``FIELD_ALIASES``i arar. Bir ad HER İKİ tabloda birden
    bulunursa hangi bandın uygulandığı yalnız bu sıraya bağlı kalır; kesişim
    BOŞ tutulur.
    """
    for form, alanlar in FORM_LIMITS.items():
        for alan, (alt, ust, birim) in alanlar.items():
            kanon = CANONICAL_LIMITS.get(alan)
            if kanon is None or kanon['unit'] == birim:
                continue
            beklenen = kanon_gorunumu(alan, birim)
            if (alt, ust) != beklenen[:2]:
                raise RuntimeError(
                    "BANT KANONU IHLALI: FORM_LIMITS[%r][%r] = %r, kanonun "
                    "%s gorunumu %r. Birim celiskili bir form bandi kendi "
                    "sayisini tutamaz; kanon_gorunumu(...) ile turetin."
                    % (form, alan, (alt, ust, birim), birim, beklenen))
    kesisim = sorted(set(FIELD_ALIASES) & set(CANONICAL_LIMITS))
    if kesisim:
        raise RuntimeError(
            'BANT KANONU IHLALI: %r adlari hem kanonik hem takma ad; '
            '_band_kaydi arama sirasi hangi bandin uygulandigini belirler.'
            % (kesisim,))


_bant_kanonu_denetimi()


#: ÖH D28 a1 / P16B1-34 — LÜLE GEOMETRİSİNİN İKİ TUTARLILIK KURALI,
#: TEK KAYNAKTA.
#:
#: Kurallar YENİ DEĞİLDİR: ``MotorDataValidator._check_physical_consistency``
#: bunları v2.6.x'ten beri yazıyor ve ``/calculate`` yolunda uyguluyor.
#: ÖLÇÜLDÜ (taban ``7cd08bcc``, ``a1/once2.json`` K11): ``POST
#: /api/generate-3d`` boğazı odadan BÜYÜK (0,5 m ⟷ 0,05 m) ve çıkışı
#: boğazdan KÜÇÜK (0,05 m ⟷ 0,2 m) olan iki gövdeyi de HTTP 200 + sahne
#: ile yanıtlıyordu (9 073 / 8 973 bayt); ucun gövdesinde doğrulayıcıya
#: yapılan TEK bir çağrı bile yoktu (``uc_govdesinde_validator = 0``).
#: Yani depo kuralı biliyor, çizim ucu onu hiç sormuyordu.
#:
#: Kural buraya ALINDI (kopyalanmadı): sınıf metodu artık bu işlevi
#: çağırır, dolayısıyla iki tüketicinin hükmü ayrışamaz (Doktrin 4).
def nozzle_geometry_errors(motor_data):
    """Boğaz/oda/çıkış çapı tutarsızlıklarını künyeli olarak döndürür.

    Returns:
        ``[{'field', 'reason', 'message', 'values'}]`` — tutarsızlık yoksa
        boş liste. Okunamayan/eksik alan SESSİZCE geçilir: bu işlev bir
        varlık kapısı değil, TUTARLILIK kapısıdır; eksik alanın hükmü
        çağıranın kendi zorunluluk kapısına aittir.
    """
    veri = motor_data if isinstance(motor_data, dict) else {}
    throat_d = _num(veri.get('throat_diameter'))
    chamber_d = _num(veri.get('chamber_diameter'))
    exit_d = _num(veri.get('exit_diameter'))
    kayitlar = []
    if throat_d and chamber_d and throat_d >= chamber_d:
        kayitlar.append({
            'field': 'throat_diameter',
            'reason': 'throat_not_smaller_than_chamber',
            'values': {'throat_diameter': throat_d,
                       'chamber_diameter': chamber_d},
            'message': (f"Throat diameter ({throat_d}m) must be smaller than "
                        f"chamber diameter ({chamber_d}m)"),
        })
    if throat_d and exit_d and exit_d <= throat_d:
        kayitlar.append({
            'field': 'exit_diameter',
            'reason': 'exit_not_larger_than_throat',
            'values': {'exit_diameter': exit_d, 'throat_diameter': throat_d},
            'message': (f"Exit diameter ({exit_d}m) must be larger than "
                        f"throat diameter ({throat_d}m)"),
        })
    return kayitlar


class MotorDataValidator:
    """Comprehensive motor data validation for all motor types"""

    def __init__(self):
        # Physical limits based on real-world constraints.
        # ÖH D26 / P16B1-49 (B ayağı): sayılar buradan MODÜL DÜZEYİNE
        # (``CANONICAL_LIMITS``) alındı — ``FORM_LIMITS`` onları türetiyor.
        # Örnek başına kopya, bugünkü sözlük değişmeziyle birebir aynıdır:
        # bir tüketicinin bandı yerinde değiştirmesi başkasını etkilemez.
        self.limits = {ad: dict(band)
                       for ad, band in CANONICAL_LIMITS.items()}

        # Material safety factors
        self.safety_factors = {
            'pressure_vessel': 4.0,  # NASA standard for pressure vessels
            'structural': 2.5,  # Structural components
            'thermal': 2.0,  # Thermal margins
            'combustion': 1.5  # Combustion stability margin
        }
        
        # Valid propellant combinations
        self.valid_propellants = {
            'hybrid': {
                'fuels': ['htpb', 'abs', 'pmma', 'pe', 'paraffin', 'sorbitol'],
                'oxidizers': ['n2o', 'lox', 'h2o2', 'gox', 'n2o4']
            },
            'solid': {
                'propellants': ['apcp', 'ap', 'an', 'db', 'nepe', 'htpb_composite', 
                               'black_powder', 'sugar', 'kno3_sugar']
            },
            'liquid': {
                'fuels': ['rp1', 'lh2', 'methane', 'ethanol', 'udmh', 'mmh', 
                         'aerozine50', 'kerosene'],
                'oxidizers': ['lox', 'n2o4', 'h2o2', 'nitric_acid', 'clf3', 
                             'f2', 'n2o', 'gox']
            }
        }
    
    def _band_kaydi(self, param, value):
        """Gönderilen bir alanı bant denetimine hazırlar.

        Döndürür: ``None`` (bu alanın bandı yok / denetlenmez) ya da
        ``{'kanonik', 'alt', 'ust', 'birim', 'takma_ad'}`` — alt/üst
        KULLANICININ BİRİMİNDEdir, böylece hata mesajı kullanıcının yazdığı
        sayıyla aynı ölçekte konuşur.

        Birim çelişkili alanda (bkz. :data:`FIELD_ALIASES` 3. tuzak) iki
        okumanın BİRLEŞİMİ döner: yalnız her iki okumada da imkânsız olan
        değer reddedilir.

        ARAMA SIRASI (ÖH D26 / P16B1-49 B ayağı): **önce kanonik ad, sonra
        takma ad.** Sıra bir tercih değil, kanonun kendisidir — kanonik ad
        SI'dir ve gövdede o adla gelen sayı SI okunur. Sıra ancak bir ad HER
        İKİ tabloda birden bulunursa gözlenebilir hâle gelirdi; bu yüzden
        kesişim :func:`_bant_kanonu_denetimi` KURAL 2 ile BOŞ tutulur (bugün
        boş — ölçüldü, ``a2/once.json`` K5). Yöntem TEKTİR: ``/calculate`` ve
        ``/api/transient-analysis`` aynı ``validate_motor_data_detailed``
        üzerinden buraya iner, yani iki uç aynı sırayı kullanır.
        """
        if param in self.limits:
            limit = self.limits[param]
            return {'kanonik': param, 'alt': limit['min'], 'ust': limit['max'],
                    'birim': limit['unit'], 'takma_ad': None}

        takma = FIELD_ALIASES.get(param)
        if takma is None:
            return None
        limit = self.limits.get(takma['kanonik'])
        if limit is None:                       # savunma: tablo tutarsızsa sus
            return None
        # Kanonik bandı ürün birimine çevir; birden fazla çarpan varsa
        # birleşimi al (en gevşek okuma kazanır).
        altlar = [limit['min'] / c for c in takma['carpanlar']]
        ustler = [limit['max'] / c for c in takma['carpanlar']]
        return {'kanonik': takma['kanonik'], 'alt': min(altlar),
                'ust': max(ustler), 'birim': takma['birim'],
                'takma_ad': takma}

    def check_band_problems(self, motor_data: Dict):
        """Bant kapısının KAMUYA AÇIK yüzü — ``(mesajlar, kayıtlar)``.

        ÖH D33-2 / app-api-uc a1 (OH-D33-04). ``hrma/app.py``in
        ``/api/quick-geometry`` ucu bu kapıyı ÖZEL adıyla
        (``motor_validator._bant_sorunlari``) çağırıyordu: modül dışından
        çağrılan bir ``_``-adı, sınıfın hangi yüzünün sözleşme olduğunu
        belirsiz bırakır — iç adın imzası sessizce değişirse uç kırılır ve
        "bu zaten özeldi" savunması kusuru meşrulaştırır.

        Sarmalayıcı KURAL EKLEMEZ, YENİ SAYI YAZMAZ: gövde tek satırdır ve
        aynı iç uygulamayı çağırır (TEK KAYNAK). Dönen üçlü sözleşme
        (mesaj biçimi, ``invalid_fields`` kayıtları) bit-aynıdır.
        """
        return self._bant_sorunlari(motor_data)

    def _bant_sorunlari(self, motor_data: Dict):
        """Bant kapısını uygular; (mesajlar, makine_okur_kayitlar) döner.

        ``mesajlar`` BİÇİMİ DEĞİŞMEDİ — arayüzün çeviri süzgeci
        (``i18n_charts.js``: ``^(.+) = (.+) is outside valid range
        \\[(.+)\\] (.*)$`` ve ``^(.+) must be numeric, got (.+)$``) aynen
        eşleşmeye devam eder, yeni çeviri borcu doğmaz.

        P16B1-23 — NaN KÖRLÜĞÜ: eski kapı ``value < min or value > max``
        yazıyordu. IEEE-754'te NaN ile yapılan HER karşılaştırma ``False``
        döndüğü için NaN her bandı geçiyordu (ölçüldü: ``tank_pressure``,
        ``chamber_pressure``, ``thrust``, ``of_ratio`` — dördünde de
        ``is_valid=True``, tek bir mesaj bile yok). ``inf`` yakalanıyordu,
        çünkü ``inf > max`` doğrudur; yani kapı sonsuzu görüp NaN'ı
        görmüyordu. Aynı kusur ``app.py::validate_input_range``te 2026-07-23'te
        teşhis edilip ``_reject_non_finite`` ile kapatılmıştı — bu modül o
        onarımdan pay almamıştı. NaN artık ``inf`` ile AYNI mesajı alır
        (biçim korunur, çeviri bedava gelir).
        """
        mesajlar: List[str] = []
        kayitlar: List[Dict] = []
        for param, value in motor_data.items():
            if value is None:
                continue
            kayit = self._band_kaydi(param, value)
            if kayit is None:
                mesaj, kayit_d = _bandsiz_sayisal_sorun(param, value)
                if mesaj is not None:
                    mesajlar.append(mesaj)
                    kayitlar.append(kayit_d)
                continue
            # ÖH D29 / P16B1-44 — ALANIN KENDİ "VERİLMEDİ" SÖZLEŞMESİ.
            # Boş dize kural olarak sayı değildir; ama tüketicisi onu
            # "verilmedi" sayan alanda kapı o sözleşmeyi izler (bkz.
            # :data:`FIELD_ALIASES` ``bos_verilmedi``). Bayrağı olmayan
            # alanda davranış BİT-AYNI kalır: "" hâlâ reddedilir.
            if value == '' and kayit['takma_ad'] is not None \
                    and kayit['takma_ad'].get('bos_verilmedi'):
                continue
            # TİP KURALI TEK KAYNAKTAN (ÖH D30 / OH-D29-07):
            # ``input_guard.is_json_number``. Buradaki literal
            # ``isinstance(value, (int, float))`` kuralın ÜÇÜNCÜ kopyasıydı
            # (ötekiler: ``app.py::_form_band_kapisi`` sayı_zorunlu kolu ve
            # merkezin kendisi) ve kopyalar AYRIŞMIŞTI — ölçüm için bkz.
            # :func:`hrma.utils.input_guard.is_json_number` künyesi.
            #
            # TEK SAPMA ``bool``dur ve BİLEREK korunmuştur: bu kapı bugün
            # bool'u sayı sayıyor ve bunu ölçen bir bekçi var
            # (``tests/test_v262_release_gate.py``). Sapma artık GÖRÜNÜR;
            # merkezin hükmü ``False``tur, buradaki muafiyet adıyla yazılı.
            if not (is_json_number(value) or isinstance(value, bool)):
                mesajlar.append(
                    f"{param} must be numeric, got {type(value).__name__}")
                # ÖH D32 / OH-D31-10 — kanonik ad (bkz.
                # :func:`_bandsiz_sayisal_sorun`).
                kayitlar.append({'field': param,
                                 'reason': 'not_a_json_number',
                                 'value': str(value)[:60],
                                 'resolved_as': kayit['kanonik']})
                continue
            sayi = float(value)
            if kayit['takma_ad'] is not None \
                    and kayit['takma_ad']['sifir_otomatik'] and sayi == 0.0:
                # 0 bu alanda "sen boyutlandır" demektir, bir ölçüm değil.
                continue
            sonsuz_degil = math.isfinite(sayi)
            if sonsuz_degil and kayit['alt'] <= sayi <= kayit['ust']:
                continue
            mesajlar.append(
                f"{param} = {value} {kayit['birim']} is outside valid range "
                f"[{kayit['alt']}, {kayit['ust']}] {kayit['birim']}")
            kayitlar.append({
                'field': param,
                'reason': ('not_finite' if not sonsuz_degil
                           else 'out_of_range'),
                'value': (str(value) if not sonsuz_degil else sayi),
                'accepted_range': [kayit['alt'], kayit['ust']],
                'unit': kayit['birim'],
                'resolved_as': kayit['kanonik'],
            })
        return mesajlar, kayitlar

    def _besleme_basinci_sorunlari(self, motor_data: Dict):
        """Enjektör basınç düşümünün İLİŞKİ kapısı (ÖH D29 / P16B1-44).

        NEDEN SAYI DEĞİL İLİŞKİ. ``pressure_drop`` [bar] için üründe TEK
        BAŞINA bir bant YOKTUR ve uydurulmaz (Doktrin 4 / P12bB1-12): alanın
        meşru büyüklüğü oda basıncına ve besleme sistemine bağlıdır. Bu
        yüzden kapı iki İLİŞKİ uygular; ikisi de deponun kendi hükmüdür:

        1. ΔP < 0 REDDEDİLİR. ÖLÇÜLDÜ (``a2/once.json`` K1H): ``-1``
           gönderildiğinde HTTP 200 dönüyordu, çünkü
           ``utils/injector_design`` ``if pressure_drop > 0`` yazıyor ve
           negatif değer sessizce OTOMATİK dala düşüyordu — kullanıcının
           sayısı uygulanmıyor, reddedilmiyor, yanıtta da anılmıyordu
           (Doktrin 1: sessiz yedek yasak). 0 ise o modülün KENDİ
           "sen boyutlandır" sentinelidir ve REDDEDİLMEZ.
        2. ENJEKTÖR GİRİŞİ BESLEME BANDINI AŞAMAZ. Orifisin üstündeki
           basınç ``P₁ = Pc + ΔP``tir (``utils/injector_design``:
           ``injector_inlet_pressure_bar``) ve bu bir BESLEME tarafı
           basıncıdır; ürünün besleme basıncı için kanonu
           ``CANONICAL_LIMITS['tank_pressure']``tir. ÖLÇÜLDÜ: ``1e9``
           gönderildiğinde HTTP 200 + enjektör 1e9 bar ΔP ile
           boyutlandırılıyordu. Yeni sayı yazılmaz; kanonun ÜST ucu okunur.

        Sonlu olmayan değer BU kapının işi DEĞİLDİR: onu uç katmanının
        kendi ``not_finite`` kapısı zaten 422 ile reddediyor (ölçüldü,
        ``a2/once.json`` K1H ``pressure_drop/ham_nan`` -> 422). Aynı reddi
        400'e çevirmek sağlıklı bir envanteri gevşetmek/kaydırmak olurdu
        (ÖK-22), bu yüzden sonsuz/NaN buradan DOKUNULMADAN geçer.
        """
        mesajlar: List[str] = []
        kayitlar: List[Dict] = []
        ham = motor_data.get('pressure_drop')
        if ham is None or ham == '':
            return mesajlar, kayitlar
        dp = finite_number(ham)
        if dp is None:                    # sayı değil / sonlu değil -> uçta
            return mesajlar, kayitlar
        if dp < 0:
            mesajlar.append(
                f'pressure_drop = {ham} bar is outside valid range '
                f'[0, feed limit] bar')
            kayitlar.append({
                'field': 'pressure_drop', 'reason': 'negative_pressure_drop',
                'value': dp, 'unit': 'bar',
                'note': ('an injector pressure DROP cannot be below zero; '
                         '0 means "size it automatically"'),
            })
            return mesajlar, kayitlar
        pc = finite_number(motor_data.get('chamber_pressure'))
        if pc is None:
            # İlişki DEĞERLENDİRİLEMEZ — sayı uydurmak yerine söylenir.
            kayitlar.append({
                'field': 'pressure_drop', 'reason': 'feed_limit_not_evaluable',
                'value': dp, 'unit': 'bar',
                'note': ('chamber_pressure was not supplied, so the injector '
                         'inlet pressure Pc + dP could not be checked '
                         'against the feed band'),
            })
            return mesajlar, kayitlar
        tavan = self.limits['tank_pressure']['max']
        giris = pc + dp
        if giris > tavan:
            mesajlar.append(
                f'pressure_drop = {ham} bar is outside valid range '
                f'[0, {tavan - pc}] bar')
            kayitlar.append({
                'field': 'pressure_drop', 'reason': 'feed_pressure_exceeded',
                'value': dp,
                'accepted_range': [0.0, tavan - pc],
                'unit': 'bar',
                'resolved_as': 'tank_pressure',
                'note': (f'the injector inlet pressure Pc + dP = {giris} bar '
                         f'exceeds the feed band this product accepts '
                         f'(tank_pressure max {tavan} bar)'),
            })
        return mesajlar, kayitlar

    def validate_motor_data(self, motor_data: Dict,
                            motor_type: str) -> Tuple[bool, List[str]]:
        """
        Validate motor data for safety and feasibility

        Returns:
            Tuple of (is_valid, list_of_errors/warnings)
        """
        ok, mesajlar, _kayitlar = self.validate_motor_data_detailed(
            motor_data, motor_type)
        return ok, mesajlar

    def validate_motor_data_detailed(self, motor_data: Dict, motor_type: str):
        """:meth:`validate_motor_data` + makine-okur alan kayıtları.

        ``(is_valid, messages, field_problems)`` döner. İlk iki öğe eski
        sözleşmeyle BİREBİR aynıdır (mevcut çağıranlar etkilenmez); üçüncüsü
        uç katmanının ``invalid_fields`` yayımlaması içindir — reddin hangi
        ALANDAN geldiği ve hangi BANDIN uygulandığı artık metinden
        ayrıştırılmak zorunda değil (adlı-4xx sözleşmesi).
        """
        errors = []
        warnings = []
        field_problems: List[Dict] = []

        # Validate motor type
        if motor_type not in ['hybrid', 'solid', 'liquid']:
            errors.append(f"Invalid motor type: {motor_type}")
            return False, errors, [{'field': 'motor_type',
                                    'reason': 'unknown_motor_type',
                                    'value': str(motor_type)[:60]}]

        # Check required parameters for each motor type
        required_params = self._get_required_parameters(motor_type)
        for param in required_params:
            if param not in motor_data or motor_data[param] is None:
                errors.append(f"Missing required parameter: {param}")
                field_problems.append({'field': param,
                                       'reason': 'missing_required'})

        # Validate parameter ranges (kanonik adlar + ürün takma adları)
        bant_mesajlari, bant_kayitlari = self._bant_sorunlari(motor_data)
        errors.extend(bant_mesajlari)
        field_problems.extend(bant_kayitlari)

        # ÖH D29 / P16B1-44 — İLİŞKİ KAPISI (tek başına bandı olmayan alan).
        besleme_mesajlari, besleme_kayitlari = \
            self._besleme_basinci_sorunlari(motor_data)
        errors.extend(besleme_mesajlari)
        field_problems.extend(besleme_kayitlari)

        # Validate propellant combinations (P10B2-13: alan kayıtları da alınır)
        if motor_type == 'hybrid':
            self._validate_hybrid_propellants(motor_data, errors, warnings,
                                              field_problems)
        elif motor_type == 'solid':
            self._validate_solid_propellants(motor_data, errors, warnings,
                                             field_problems)
        elif motor_type == 'liquid':
            self._validate_liquid_propellants(motor_data, errors, warnings,
                                              field_problems)
        
        # Physical consistency checks
        self._check_physical_consistency(motor_data, motor_type, errors, warnings)
        
        # Safety checks
        self._perform_safety_checks(motor_data, motor_type, errors, warnings)
        
        # Combine errors and warnings
        all_messages = errors + warnings
        is_valid = len(errors) == 0

        return is_valid, all_messages, field_problems

    def _get_required_parameters(self, motor_type: str) -> List[str]:
        """Get required parameters for each motor type"""
        base_params = ['thrust', 'burn_time']
        
        if motor_type == 'hybrid':
            return base_params + ['fuel_type', 'oxidizer_type', 'of_ratio']
        elif motor_type == 'solid':
            return base_params + ['propellant_type']
        elif motor_type == 'liquid':
            return base_params + ['fuel_type', 'oxidizer_type', 'mixture_ratio', 
                                 'chamber_pressure']
        return base_params
    
    def _itici_adi(self, motor_data: Dict, alan: str, errors: List,
                   field_problems: List) -> str:
        """İtici adı alanını GÜVENLE okur; tipi yanlışsa ADIYLA reddeder.

        ÖH Z5S / P10-C (P10B2-13). ÖLÇÜLDÜ (28 Ağustos 2026): üç itici
        doğrulayıcısı da ``motor_data.get('fuel_type', '').lower()`` deseniyle
        yazılmıştı. Anahtar VARSA ve değeri ``None`` ise ``.lower()``
        ``AttributeError`` verir; sayı gönderildiğinde de aynı şey olur. Kusur
        doğrulayıcının kendi çıktısını yutuyordu:

            POST /calculate {"fuel_type": null, ...}
            -> HTTP 400 {"error": "'NoneType' object has no attribute
                          'lower'", "error_type": "AttributeError"}

        Yani kullanıcı, doğrulayıcının ZATEN ürettiği doğru teşhisi
        ("Missing required parameter: fuel_type") hiç görmüyordu; yerine ham
        bir Python hatası geçiyordu — alan adı yok, gerekçe yok, bant yok.

        Bu yardımcı iki sınıfı ayırır ve İKİSİNİ DE ADLANDIRIR:
          * ``None`` / anahtar yok  -> sessiz atlanır; zorunlu-alan döngüsü
            bu alanı zaten ``missing_required`` olarak adlandırmıştır
            (çift mesaj üretilmez).
          * str olmayan bir değer   -> ``wrong_type`` hatası + makine-okur
            alan kaydı; hüküm fail-closed'dur (is_valid=False), uç katmanı
            adlı 400'ünü basar.
        """
        if alan not in motor_data:
            return ''
        value = motor_data[alan]
        if value is None:
            # Zorunlu-alan kapısı bu durumu ADIYLA raporladı; burada yalnız
            # kombinasyon denetimi atlanır (ham çökme yerine sessiz geçiş).
            return ''
        if not isinstance(value, str):
            errors.append(
                f"{alan} must be a propellant name (text), got "
                f"{type(value).__name__}")
            field_problems.append({
                'field': alan,
                'reason': 'wrong_type',
                'value': str(value)[:60],
                'expected_type': 'string',
            })
            return ''
        return value.lower()

    def _validate_hybrid_propellants(self, motor_data: Dict, errors: List,
                                     warnings: List,
                                     field_problems: Optional[List] = None):
        """Validate hybrid motor propellant combination"""
        if field_problems is None:
            field_problems = []
        fuel = self._itici_adi(motor_data, 'fuel_type', errors, field_problems)
        oxidizer = self._itici_adi(motor_data, 'oxidizer_type', errors,
                                   field_problems)

        if fuel and fuel not in self.valid_propellants['hybrid']['fuels']:
            warnings.append(f"Unusual hybrid fuel: {fuel}. Common fuels: "
                          f"{', '.join(self.valid_propellants['hybrid']['fuels'])}")
        
        if oxidizer and oxidizer not in self.valid_propellants['hybrid']['oxidizers']:
            warnings.append(f"Unusual hybrid oxidizer: {oxidizer}. Common oxidizers: "
                          f"{', '.join(self.valid_propellants['hybrid']['oxidizers'])}")
        
        # Check dangerous combinations
        if fuel == 'htpb' and oxidizer == 'clf3':
            warnings.append("WARNING: HTPB/ClF3 is extremely hypergolic and dangerous!")
    
    def _validate_solid_propellants(self, motor_data: Dict, errors: List,
                                    warnings: List,
                                    field_problems: Optional[List] = None):
        """Validate solid motor propellant"""
        if field_problems is None:
            field_problems = []
        propellant = self._itici_adi(motor_data, 'propellant_type', errors,
                                     field_problems)

        if propellant and propellant not in self.valid_propellants['solid']['propellants']:
            warnings.append(f"Unusual solid propellant: {propellant}. Common propellants: "
                          f"{', '.join(self.valid_propellants['solid']['propellants'][:5])}")
        
        # Safety warnings for amateur propellants
        if propellant in ['black_powder', 'sugar', 'kno3_sugar']:
            warnings.append(f"WARNING: {propellant} is an amateur propellant. "
                          "Professional supervision recommended.")
    
    def _validate_liquid_propellants(self, motor_data: Dict, errors: List,
                                     warnings: List,
                                     field_problems: Optional[List] = None):
        """Validate liquid motor propellant combination"""
        if field_problems is None:
            field_problems = []
        fuel = self._itici_adi(motor_data, 'fuel_type', errors, field_problems)
        oxidizer = self._itici_adi(motor_data, 'oxidizer_type', errors,
                                   field_problems)

        if fuel and fuel not in self.valid_propellants['liquid']['fuels']:
            warnings.append(f"Unusual liquid fuel: {fuel}. Common fuels: "
                          f"{', '.join(self.valid_propellants['liquid']['fuels'][:5])}")
        
        if oxidizer and oxidizer not in self.valid_propellants['liquid']['oxidizers']:
            warnings.append(f"Unusual liquid oxidizer: {oxidizer}. Common oxidizers: "
                          f"{', '.join(self.valid_propellants['liquid']['oxidizers'][:5])}")
        
        # Check hypergolic combinations
        hypergolic_pairs = [
            ('udmh', 'n2o4'), ('mmh', 'n2o4'), ('aerozine50', 'n2o4')
        ]
        
        if (fuel, oxidizer) in hypergolic_pairs:
            warnings.append(f"WARNING: {fuel}/{oxidizer} is hypergolic - ignites on contact!")
        
        # Check cryogenic handling
        cryo_propellants = ['lh2', 'lox', 'methane']
        if fuel in cryo_propellants or oxidizer in cryo_propellants:
            warnings.append("Note: Cryogenic propellants require specialized handling equipment")
    
    def _check_physical_consistency(self, motor_data: Dict, motor_type: str, 
                                   errors: List, warnings: List):
        """Check physical consistency of parameters"""
        
        # Throat must be smaller than chamber
        # Faz 5 / B11 ile aynı kusur: bu iki alan da HAM okunuyordu ve metin
        # geldiğinde karşılaştırma çöküyordu. Ölçüldü (3 Ağustos 2026):
        # throat_diameter="0.02" -> TypeError: '>=' not supported between
        # instances of 'str' and 'float'.
        errors.extend(k['message'] for k in nozzle_geometry_errors(motor_data))
        chamber_d = _num(motor_data.get('chamber_diameter'))

        # Chamber pressure vs tank pressure (for liquid)
        if motor_type == 'liquid':
            chamber_p = _num(motor_data.get('chamber_pressure'))
            tank_p = _num(motor_data.get('tank_pressure'))
            if chamber_p and tank_p and tank_p <= chamber_p:
                errors.append(f"Tank pressure ({tank_p} bar) must be higher than "
                            f"chamber pressure ({chamber_p} bar)")
        
        # Port diameter checks for hybrid
        if motor_type == 'hybrid':
            port_d = _num(motor_data.get('port_diameter'))
            if port_d and chamber_d and port_d >= chamber_d * 0.8:
                warnings.append(f"Port diameter ({port_d}m) is very large relative to "
                              f"chamber ({chamber_d}m). Check structural integrity.")
        
        # Total impulse vs thrust and burn time
        thrust = _num(motor_data.get('thrust'))
        burn_time = _num(motor_data.get('burn_time'))
        total_impulse = _num(motor_data.get('total_impulse'))
        
        if thrust and burn_time and total_impulse:
            calculated_impulse = thrust * burn_time
            if abs(calculated_impulse - total_impulse) > 0.1 * total_impulse:
                warnings.append(f"Total impulse ({total_impulse} Ns) doesn't match "
                              f"thrust×time ({calculated_impulse} Ns)")
    
    def _perform_safety_checks(self, motor_data: Dict, motor_type: str,
                              errors: List, warnings: List):
        """Perform safety-critical checks.

        v2.6.26 / Faz 5 (B11) — TİP DENETİMSİZ KARŞILAŞTIRMA:
        Aşağıdaki üç eşik (``thrust``, ``chamber_temperature``,
        ``burn_time``) değeri ``motor_data.get(...)`` ile HAM okuyup
        doğrudan ``>`` ile karşılaştırıyordu. Sayısal bir alan metin olarak
        geldiğinde (form gönderimi ya da kayıtlı ``.hrma`` projesinden gelen
        en olağan bozulma) satır ham Python hatası veriyordu:

            thrust="1000"              -> TypeError: '>' not supported
            burn_time="5"                 between instances of 'str' and 'int'
            chamber_temperature="3000"

        Ölçüm (3 Ağustos 2026, HEAD 9d3728e): üç alanın üçü de
        ``validate_motor_data(..., 'hybrid')`` çağrısını istisnayla
        düşürüyordu; ``/calculate`` bu yüzden HTTP 400 + ham TypeError
        metniyle komple kilitleniyordu. Oysa aynı fonksiyonun ilk bloğu
        (:107) "thrust must be numeric, got str" diye ANLAŞILIR hatayı zaten
        üretmişti — kullanıcı onu hiç göremiyordu, çünkü bu blok ondan sonra
        koşup çöküyordu.

        Düzeltme: ``chamber_pressure``'ın v2.6.26'da zaten yaptığı gibi
        ``_num()`` kullanılır. ``_num`` sayıya çevrilemeyen değere None döner
        ve o kontrol ATLANIR (sessizce 0 varsayılmaz); alanın sayısal
        olmadığı bilgisi yukarıdaki tip denetiminden zaten hata listesine
        girmiştir.
        """

        # Chamber pressure safety factor
        chamber_p = _num(motor_data.get('chamber_pressure'))
        if chamber_p:
            burst_p = chamber_p * self.safety_factors['pressure_vessel']
            if burst_p > 2000:  # Extreme pressure warning
                warnings.append(f"CRITICAL: Burst pressure ({burst_p} bar) requires "
                              "specialized high-pressure equipment")

        # Thrust level safety
        thrust = _num(motor_data.get('thrust'))
        if thrust:
            if thrust > 50000:  # 50 kN
                warnings.append(f"High thrust ({thrust}N) requires professional "
                              "test stand and safety equipment")
            elif thrust > 10000:  # 10 kN
                warnings.append(f"Moderate thrust ({thrust}N) requires reinforced "
                              "test stand and remote operations")

        # Temperature warnings
        temperature = _num(motor_data.get('chamber_temperature',
                                          motor_data.get('temperature')))
        if temperature and temperature > 3500:
            warnings.append(f"Extreme temperature ({temperature}K) requires "
                          "advanced cooling and thermal protection")

        # Burn time warnings
        burn_time = _num(motor_data.get('burn_time'))
        if burn_time and burn_time > 60:
            warnings.append(f"Long burn time ({burn_time}s) requires thermal "
                          "management and structural analysis")
    
    def sanitize_export_data(self, data: Dict) -> Dict:
        """Dışa aktarım verisini güvenli hale getirir.

        v2.6.26 düzeltmesi (SAN-ZERO-6) — SESSİZ VERİ BOZULMASI:
        Bu fonksiyon eskiden None/NaN/Inf değerleri 0'a çeviriyordu. Çıktısı
        /api/export-stl üzerinden İMALATA gidebilecek STL dosyasına aktığı
        için, çözücünün hesaplayamadığı bir boğaz çapı sessizce 0 olup
        geometriyi değiştiriyordu (ölçüm: aynı istek NaN ile ve gerçek
        değerle FARKLI STL üretti, hiçbir uyarı dönmedi).

        Yeni sözleşme app.py::sanitize_json_values (v2.6.2) ile AYNIDIR:
        sonlu olmayan sayı ``None`` döner. 0 gerçek bir ölçümdür ve aynen
        korunur; "hesaplanamadı" ile "sıfır" bir daha karışmaz. Çağıran taraf
        None'ı eksik/hesaplanamamış saymakla yükümlüdür. Ortak yardımcıya
        taşınamadı: app.py bu modülü import ettiği için (app.py:46) tersi
        döngüsel import olurdu; semantik burada yerel olarak eşitlendi.

        Listelerdeki ve dizilerdeki çıplak sayılar da taranır (eski kod
        listelerde yalnız dict elemanlarını geziyordu, listedeki NaN
        hayatta kalıyordu).
        """
        return {key: self._sanitize_value(value) for key, value in data.items()}

    def _sanitize_value(self, value):
        """Tek bir değeri dışa aktarım sözleşmesine göre temizler."""
        if value is None:
            return None
        # bool, int'in alt sınıfıdır; sayı yoluna girerse bayraklar 1.0/0.0
        # olur (app.py sözleşmesi bool'u korur).
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, np.integer)):
            return int(value)
        if isinstance(value, (float, np.floating)):
            # P15B2-01: sonluluk kurali merkezden (yerel kopya yok).
            return finite_number(value)
        if isinstance(value, str):
            return value.replace('\x00', '').strip()
        if isinstance(value, dict):
            return {key: self._sanitize_value(item)
                    for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._sanitize_value(item) for item in value]
        if isinstance(value, np.ndarray):
            return [self._sanitize_value(item) for item in value.tolist()]
        return str(value)
    
    def validate_export_request(self, export_data: Dict, export_type: str) -> Tuple[bool, str]:
        """Validate export request data"""
        
        if export_type not in ['stl', 'pdf', 'openrocket', 'cad', 'simulation']:
            return False, f"Invalid export type: {export_type}"
        
        if 'motor_data' not in export_data:
            return False, "No motor data provided for export"
        
        motor_data = export_data['motor_data']
        if not motor_data:
            return False, "Motor data is empty"
        
        # Check minimum required fields for export
        if export_type == 'stl':
            required = ['chamber_diameter', 'chamber_length']
            for field in required:
                if field not in motor_data or motor_data[field] is None:
                    return False, f"Missing required field for STL export: {field}"
        
        elif export_type == 'pdf':
            if 'thrust' not in motor_data:
                return False, "Missing thrust data for PDF report"
        
        elif export_type == 'openrocket':
            required = ['thrust', 'burn_time', 'propellant_mass']
            for field in required:
                if field not in motor_data or motor_data[field] is None:
                    return False, f"Missing required field for OpenRocket: {field}"
        
        return True, "Validation passed"

# Global validator instance
motor_validator = MotorDataValidator()