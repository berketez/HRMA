"""``ambient_temp`` kanalının HTTP dikişi (v2.6.27, otuz ikinci parti).

DEFTER KALEMİ: "index.html'de ambient_temp alanı YOK ama app.py okuyor — iki
yaprak 293,15 K'de donuk" (kanal var / kapı yok ailesi).

ÖLÇÜM İKİ ÖNCÜLÜ DE DÜZELTTİ, ikisi de sessiz geçilmiyor:

1. KAPI index.html'e AİT DEĞİL. ``templates/index.html`` açılış sayfasıdır
   (``/`` rotası): içinde tek bir form alanı, tek bir toplayıcı ve tek bir
   ``/calculate`` çağrısı yoktur — yalnız üç motor kartı vardır. Hibrit form
   sayfası ``templates/advanced.html``'dir (``/hybrid`` rotası,
   ``getFormData`` toplayıcısı; tests/support/inventory.PAGES bunu
   sözleşme olarak yazıyor). Kapı oraya açılmalıdır ve o dosya bu partide
   BAŞKA BİR AJANIN kapsamındaydı — bu yüzden kapı bu dosyada açılmadı,
   borç ``tests/test_stability_hibrit_chug.py::KAPISIZ_BILINEN`` kümesinde
   ('ambient_temp' satırı) iki yönlü eşikle DURUYOR. Kapı açıldığı gün o
   satır aynı commit'te silinmek zorundadır, yoksa o test kırmızı olur.

2. "İki yaprak donuk" ölçümü eksikti: kanal açıldığında değişen yaprak sayısı
   781'dir (aşağıda ölçülüyor). Donuk olan iki yaprak, ``layer_b``
   sarsımının SABİT ÇIKTI listesinde görünenlerdir; sarsım şablondan alan
   okuduğu için kapı olmayınca ambient_temp hiç sarsılmıyor ve o iki yaprak
   "hiçbir girdiden etkilenmiyor" görünüyor.

Bu dosya kapının ARKASINDAKİ kanalı kilitler: ``app.py::calculate``
içindeki ``ambient_temperature=data.get('ambient_temp')`` kablosu sökülürse
kırmızı olur (mutasyonla ölçüldü). Kapı açıldığında bu bekçi zaten yerinde
olur — açılan kapının bir şeye bağlandığı buradan bilinir.
"""

import pytest

# Yük TEK KAYNAKTAN gelir (o dosyanın kendi sözleşmesi: "kopyalanmaz,
# buradan import edilir") — ikinci bir hibrit taban yükü yazmak, motor
# sözleşmesi değişince sessizce eskiyen bir ikiz yaratırdı.
from tests.support import shake
from tests.test_field_wiring_layer_b import HYBRID_BASE

#: Isı transferi modülünün kendi varsayılanı (kullanıcı vermezse).
SUNUCU_VARSAYILANI_K = 293.15

#: Ölçüm noktası: motor bandının (180-340 K) içinde, varsayılandan uzak.
#: -40 °C = 233,15 K — yüksek irtifa / kış fırlatması.
OLCUM_DEGERI_K = 233.15

#: Bant dışı: kullanıcı °C sanıp 174 °C girmiş gibi (ölçülen tuzak).
BANT_DISI_K = 447.0

#: ``ambient_temp`` verilmediğinde donuk kalan İKİ yaprak (defter kalemi).
DONUK_YAPRAKLAR = (
    'heat_transfer_analysis.design_parameters.ambient_temperature',
    'heat_transfer_analysis.cooling_analysis.heat_sink_initial_temperature_K',
)


def _yapraklar(dugum, onek=''):
    if isinstance(dugum, dict):
        for k, v in dugum.items():
            yield from _yapraklar(v, f'{onek}.{k}')
    elif isinstance(dugum, list):
        for i, v in enumerate(dugum):
            yield from _yapraklar(v, f'{onek}[{i}]')
    else:
        yield onek.lstrip('.'), dugum


def _oku(sonuc, yol):
    dugum = sonuc['motor']
    for parca in yol.split('.'):
        dugum = dugum[parca]
    return dugum


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _kos(client, **ek):
    yuk = dict(HYBRID_BASE)
    yuk.update(ek)
    yanit = client.post('/calculate', json=yuk, headers=shake.HEADERS)
    assert yanit.status_code == 200, (
        '/calculate %d döndü (yük: %s)' % (yanit.status_code, sorted(ek)))
    return yanit.get_json()


@pytest.fixture(scope='module')
def kapisiz(client):
    """ambient_temp GÖNDERİLMEDEN — bugünkü arayüzün gerçek durumu."""
    return _kos(client)


@pytest.fixture(scope='module')
def kapili(client):
    """ambient_temp GÖNDERİLEREK — kapı açıldığında olacak durum."""
    return _kos(client, ambient_temp=OLCUM_DEGERI_K)


def test_iki_donuk_yaprak_kanal_beslenince_canlaniyor(kapisiz, kapili):
    """Defterdeki iki yaprak, alan verilince kıpırdamalı.

    Bu testin kırmızıya döndüğü tek yol app.py'deki kablonun sökülmesidir
    (ölçüldü: ``ambient_temperature=data.get('ambient_temp')`` satırı
    kaldırılınca bu dosyada 4 test kırmızı).
    """
    for yol in DONUK_YAPRAKLAR:
        assert _oku(kapisiz, yol) == pytest.approx(SUNUCU_VARSAYILANI_K), (
            f'{yol}: alan gönderilmeden sunucu varsayılanı beklenirdi')
        assert _oku(kapili, yol) == pytest.approx(OLCUM_DEGERI_K), (
            f'{yol}: alan gönderildi ama yaprak {SUNUCU_VARSAYILANI_K} K\'de '
            'donuk kaldı — kanal kopmuş olabilir')


def test_kanal_yalniz_yanki_degil(kapisiz, kapili):
    """Girdinin yankısı değil, HESABIN kendisi değişmeli.

    Ölçülen: 781 yaprak değişiyor (ısı transferi duvar sıcaklıkları, ısı
    kuyusu kütlesi, yapısal termal gerilme/emniyet katsayıları, yörünge
    zinciri ve openrocket yankı kopyaları dâhil). Eşik BİLEREK gevşek
    (>= 200) ve tam sayı DONDURULMADI: 781 tüm yanıt ağacının bir özelliği,
    bu dikişin değil — dondurmak bu bekçiyi her ilgisiz motor değişikliğinde
    öten bir alarma çevirirdi. Yankı olmadığının KESİN kanıtı, aşağıdaki
    'yalnız yankı olsaydı' karşı-ölçümüdür.
    """
    d0 = dict(_yapraklar(kapisiz))
    d1 = dict(_yapraklar(kapili))
    degisen = [k for k in d0 if k in d1 and d0[k] != d1[k]]
    assert len(degisen) >= 200, (
        'ambient_temp yalnız %d yaprak oynatıyor (781 ölçülmüştü) — kanal '
        'daralmış olabilir: %s' % (len(degisen), degisen[:20]))

    # Karşı-ölçüm: değişenler yalnızca girdinin yankısı (ambient/initial
    # sıcaklık alanları) olsaydı bu alan fiilen ÖLÜ olurdu.
    yanki = {k for k in degisen
             if 'ambient' in k or 'initial_temperature' in k}
    assert len(degisen) - len(yanki) >= 100, (
        'değişen yaprakların neredeyse tamamı girdi yankısı — alan hesaba '
        'girmiyor olabilir (yankı dışı: %d)' % (len(degisen) - len(yanki)))


def test_verilmediginde_varsayilan_BEYAN_ediliyor(kapisiz):
    """Alan yokken sunucu varsayılanı sessizce değil, beyanla düşer."""
    dayanak = _oku(
        kapisiz, 'heat_transfer_analysis.cooling_analysis.heat_sink_delta_T_basis')
    assert 'initial temperature' in dayanak and '293' in dayanak, (
        'ısı kuyusu dayanağı kullanılan ortam sıcaklığını yazmıyor: %r'
        % dayanak)


def test_bant_disi_deger_uydurulmuyor_ADIYLA_reddediliyor(client):
    """°C/K karışıklığı sessizce kabul edilmemeli — ARTIK REDDEDİLİYOR.

    Motorun fiziksel zarfı 180-340 K (``hybrid_rocket_engine.
    _resolve_ambient_temperature``; gerekçe: Vostok -89 °C ... Ölüm Vadisi
    +57 °C).

    ÇEVRİLDİ — ÖH D29 / app-api-dogrulama a2, defter P16B1-44.
    ÖNCEKİ HÂLİ (``..._beyanla_dusuyor``): bant dışı değer HTTP 200 alır,
    motor varsayılana döner ve bunu ``defaults_used`` içinde BEYAN ederdi.
    O hâl kusuru KORUYAN bir bekçiydi — bu dosyanın kendi başlığı bile
    "kapıya konacak min/max da bu banttan gelmelidir" diyerek kapının
    eksik olduğunu yazıyordu — ve Doktrin 1 beyanı çözüm saymaz:
    kullanıcının gönderdiği 447 K uygulanmıyor ama isteği de
    reddedilmiyordu. ÖLÇÜLDÜ (``docs/scofield/raw/OH/D29/
    app-api-dogrulama/a2/once.json`` K1, taban ``4dc63c11``):
    ``ambient_temp`` 14 sarsımın 14'ünde kabul ediliyordu.

    Kapı artık DEĞER katmanındadır (``motor_validation.FIELD_ALIASES``:
    ``ambient_temp`` -> kanonik ``ambient_temperature``); bant SAYISI
    değişmedi, ``hrma.constants.AMBIENT_TEMPERATURE_BAND_K``ten okunuyor
    ve motorun kendi zarfı da artık aynı addan besleniyor (tek kaynak).

    Motorun sessiz düşme dalı SÖKÜLMEDİ: uç katmanı kapıyı geçmeyen bir
    çağrı yaparsa (kütüphane kullanımı) beyan hâlâ üretilir; bu
    ``tests/test_d29_app_api_dogrulama_a2.py`` içinde ayrıca kilitlidir.
    """
    yuk = dict(HYBRID_BASE)
    yuk['ambient_temp'] = BANT_DISI_K
    yanit = client.post('/calculate', json=yuk, headers=shake.HEADERS)
    assert yanit.status_code == 400, (
        'bant dışı ortam sıcaklığı hâlâ kabul ediliyor: HTTP %d'
        % yanit.status_code)
    govde = yanit.get_json()
    kayitlar = [k for k in (govde.get('invalid_fields') or [])
                if k.get('field') == 'ambient_temp']
    assert kayitlar, (
        'ret ADSIZ: invalid_fields içinde ambient_temp yok: %s' % govde)
    assert kayitlar[0]['accepted_range'] == [180.0, 340.0], kayitlar[0]
    assert kayitlar[0]['unit'] == 'K', kayitlar[0]
