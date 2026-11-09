"""3.0.6 (9 Kas, ana model) — itici özellik yanıtı geç gelince kayıtlı değer EZİLMEZ.

Kusur (rc.3 yerel tam süpürmesi, test_v301_proje_gidis_donus [liquid-sonraki],
yalnız yük altında): sıvı sayfası açılırken varsayılan itici çifti için
başlayan /api/get-propellant-properties isteği, proje geri yüklendikten SONRA
dönüyor ve kullanıcının kayıtlı yoğunluk/viskozitesini başka iticinin tablo
değerine eziyordu; seçili yakıtın kendi yanıtı da projeden gelen yakıt
yoğunluğunu/viskozitesini eziyordu. Özellik ucu 3 s geciktirilince her koşuda
üretildi: kayıtlı 938 / 3,7 → LH2 70,9495 / 1,359e-05 ve LOX 1141,16 /
1,947e-04.

Onarım (hrma/templates/liquid.html loadPropellantProperties): yalnız en son
ve hâlâ seçili itici çiftine ait istek yazar; oksitleyici değişince önceki
oksitleyicinin otomatik değeri hemen boşalır; aynı yakıtta projeden gelen
(sahibi 'restored') değer yanıtla ezilmez.

Bu bekçi zamanlamayı ŞANSA bırakmaz: proje açılırken bütün özellik
yanıtları TUTULUR, geri yükleme bittikten sonra hepsi birden salınır — yük
altındaki en kötü sıra her koşuda kurulur.
"""
import json
import urllib.parse

import pytest

from tests.test_v301_proje_gidis_donus import (  # noqa: F401  (düzenekler)
    GD_SAYFA, JS_DOLDUR, JS_KAYDET, sunucu, tarayici)

pytestmark = pytest.mark.kabul_ui

OZELLIK_UCU = '**/api/get-propellant-properties'
OZELLIK_ALANLARI = ('fuel_density', 'fuel_viscosity',
                    'oxidizer_density', 'oxidizer_viscosity')


def _alanlar(sayfa, ad):
    return (sayfa.evaluate('(a) => HRMAProjectBar._buildPayload(a).inputs', ad)
            .get('fields') or {})


#: Kullanıcının elle yazdığı, tablo değerlerinden (LH2 70,9495; N2O4 hâl
#: çözümsüz; RP-1 / LOX tablo) FARKLI değerler — ezilirse görünür.
ELLE = {'fuel_density': '901.5', 'fuel_viscosity': '0.00123',
        'oxidizer_density': '1420.5', 'oxidizer_viscosity': '0.000456'}


def _kaydet(tarayici, sunucu, ad):
    """Sıvı sayfası: seçiciler bir sonraki seçenekte, bütün yanıtlar gelir,
    özellik alanları ELLE (gerçek klavye olayı) yazılır → kayıt."""
    sayfa = tarayici.new_page(viewport={'width': 1440, 'height': 900})
    sayfa.set_default_timeout(30000)
    try:
        sayfa.goto(sunucu + GD_SAYFA['liquid'][0])
        sayfa.wait_for_load_state('networkidle')
        sayfa.wait_for_function('window.HRMAProjectBar && HRMAProjectBar._state')
        sayfa.wait_for_timeout(800)
        sayfa.evaluate(JS_DOLDUR, {'kip': 'next', 'zorla': {}})
        sayfa.wait_for_load_state('networkidle')
        sayfa.wait_for_timeout(1500)          # bütün yanıtlar geldi
        for alan, deger in ELLE.items():
            sayfa.fill('#' + alan, deger)
        sayfa.wait_for_timeout(500)
        kayit = sayfa.evaluate(JS_KAYDET, ad)
        assert kayit['durum'] == 200, kayit
        return _alanlar(sayfa, ad)
    finally:
        sayfa.close()


def _yanitlar_tutularak_ac(tarayici, sunucu, ad):
    """Projeyi açar; özellik yanıtlarını geri yükleme BİTENE kadar tutar."""
    sayfa = tarayici.new_page(viewport={'width': 1440, 'height': 900})
    sayfa.set_default_timeout(30000)
    tutulan = []
    sayfa.route(OZELLIK_UCU, lambda r: tutulan.append(r))
    try:
        sayfa.goto(sunucu + GD_SAYFA['liquid'][0] + '?project='
                   + urllib.parse.quote(ad), wait_until='domcontentloaded')
        sayfa.wait_for_function('window.HRMAProjectBar && HRMAProjectBar._state'
                                ' && HRMAProjectBar._state.name === '
                                + json.dumps(ad))
        sayfa.wait_for_timeout(2500)          # geri yükleme + yeniden uygulama
        sayi = len(tutulan)
        for r in tutulan:                      # en kötü sıra: hepsi geç
            r.continue_()
        sayfa.unroute(OZELLIK_UCU)
        sayfa.wait_for_timeout(2500)
        return sayi, _alanlar(sayfa, ad)
    finally:
        sayfa.close()


def test_gec_gelen_ozellik_yaniti_kayitli_degeri_ezmez(tarayici, sunucu):
    ad = 'gd-ozellik-yarisi'
    kayit = _kaydet(tarayici, sunucu, ad)
    # Ön koşul: senaryo bu alanlara gerçekten değer yazdı (boş ⟷ boş
    # karşılaştırması bekçiyi dişsiz bırakırdı).
    for k in OZELLIK_ALANLARI:
        assert str(kayit.get(k)) in (ELLE[k], str(float(ELLE[k]))), (
            'elle yazılan değer kayda girmedi', k, kayit.get(k))
    sayi, sonra = _yanitlar_tutularak_ac(tarayici, sunucu, ad)
    assert sayi >= 2, ('özellik isteği tutulamadı — bekçi yarışı kuramadı', sayi)
    kayip = {k: {'kayit': kayit.get(k), 'sonra': sonra.get(k)}
             for k in OZELLIK_ALANLARI if kayit.get(k) != sonra.get(k)}
    assert not kayip, ('S1 veri kaybı: geç gelen özellik yanıtı kayıtlı değeri '
                       'ezdi', kayip)
    tum = {k: (kayit[k], sonra.get(k, '<yok>')) for k in kayit
           if kayit[k] != sonra.get(k, '<yok>')}
    assert not tum, ('kayıtlı alan yüklemede değişti', tum)
