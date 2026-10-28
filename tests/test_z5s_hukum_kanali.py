"""ÖH Z5S / S6 — güvenlik ve termal hükümlerin ÜRÜNE İNEN kanalı.

Kapatılan kalemler (taban ``df67bce``; ölçüm dosyaları
``docs/scofield/raw/OH/Z5S/s6/once_supurme.json`` ve
``docs/scofield/raw/OH/Z5S/s6/once_kapi.json``, onarım sonrası
``sonra_supurme.json`` / ``sonra_kapi.json``):

* **P7B3-21 (KRİTİK)** — ``/analyze_safety`` toksik hükmü. Kalemin başlığı
  "panelin gönderebildiği HER değer NONE" diyordu; ÖLÇÜM bunu KISMEN
  ÇÜRÜTTÜ: ``'liquid_monoprop'`` (panelin gönderebildiği bir değer)
  ``MEDIUM`` + üç bileşen + dolu PPE üretiyordu. GERÇEK kusur iki
  tanedir ve ikisi de kapatıldı:

  1. **Bilinmeyende fail-open.** ``toxic_map.get(propellant_type, [])``
     yüzünden ``'peynir'``, ``'hydrazine'``, ``''`` ve tanınmayan her değer
     sessizce ``'NONE'`` + ``ppe_requirements: []`` alıyordu. Bilinmeyen bir
     itici için "toksik tehlike yok" KAZANILMAMIŞ bir hükümdür.
  2. **Ölü dal.** ``'liquid_biprop'`` ve ``'solid_monoprop'`` dallarındaki
     alt dize koşulu (``'n2o4' in propellant_type``) ASLA doğru olamazdı,
     çünkü sözlük anahtarı TAM eşleşmeyle seçiliyordu. LOX/RP-1 ile
     N2O4/MMH aynı hükmü (``'NONE'``) görüyordu.

  Bu dosyadaki bekçi TOTOLOJİK DEĞİLDİR: itici değerleri
  ``static/js/panels/safety_panel.js`` içindeki ``PROPELLANTS`` listesinden
  OKUNUR, yani ürünün gerçekten gönderebildiği kümedir. Eski bekçi ürünün
  hiç gönderemediği ``'hydrazine'`` ile yeşil kalıyordu.

* **P16B3-25** — ``propellant_mass = 0``. Taban ölçümünde bu vaka ZATEN
  fail-closed (422 + ``invalid_fields``); kalem S1/S3 kapılarıyla kapanmış.
  Bekçi kapının GERİ ALINMAMASI içindir.

* **P7B3-25** — ``/analyze_thermal_safety`` boş gövde. Taban ölçümünde bu
  da ZATEN 422 (``missing_fields`` dokuz alan). Uydurma 13,03 MW/m²
  yolunun geri gelmediği kilitlenir.

* **P16B3-04** — künye ``ambient_temp``i "istekten yankılandı" diye ilan
  ediyordu ama uç modüle SABİT 293,15 K geçiriyordu (ölçüldü: 500 K
  gönderilen ve gönderilmeyen istek BİT-AYNI). Künye kaldırılmadı,
  DOĞRU hâle getirildi: alan artık gerçekten okunuyor.

* **P7B3-29** — ``/api/fea/thermal`` gelen profilin beyanlarını
  (``warnings``, ``y_plus_max``, ``source``) sessizce düşürüyordu.

* **P16B3-15** — ``/analyze_structural_safety`` atılan cidarı
  ``design_basis``te anlatıyordu ama ÜST DÜZEY
  ``inputs_treated_as_absent`` kanalına hiç yazmıyordu.

* **S1-04** — iki kardeş kapı birbirinin TERSİYDİ; ``wall_thickness = 1e9``
  yapısal uçta 422, termal uçta HTTP 200 + tam hüküm veriyordu. Birleşim
  kapısı ``app.py::_cidar_birim_kapisi``tır ve iki uç da onu çağırır.

EK MADDELER: ``/api/get-fuel-properties`` ``cp/1000`` None'da 500 atıyordu
(P9B4-12 / OH-Z5-04) ve ``/api/six-dof-analysis`` sabit ``summary`` listesi
CG künyesini düşürüyordu (OH-Z5-11).

SÖZLEŞME: bu uçlar DOĞRULAMA yoludur. Reddedilen alan için (a) 4xx,
(b) gövdede makine-okur ALAN ADI, (c) Python istisna metni YOK. Kabul
edilen istekte SAYI DEĞİŞMEZ; eklenen tek şey beyandır (kanıt:
``docs/scofield/raw/OH/Z5S/s6/gecerli_govde_farki.json`` — üç motor
``/calculate`` çapası 44.594 yaprakta BİT-AYNI).
"""

import contextlib
import io
import json
import re
from pathlib import Path

import pytest

from tests.support.fea_lule import ag_malzemesi

from hrma.app import app
# ÖH D30 a3: cidar sentineli künyesinin TEK KAYNAĞI (a1 · P16B1-33/-42);
# ad bu bekçiye KOPYALANMAZ, uçtan okunur.
from hrma.app import WALL_INPUT_SIZING_SENTINEL
from hrma.analysis.safety_analysis import (
    KNOWN_PROPELLANT_CLASSES,
    TOXIC_LEVEL_NOT_EVALUATED,
    TOXIC_RESOLUTION_NOT_TABULATED,
    TOXIC_RESOLUTION_TABULATED,
    TOXIC_RESOLUTION_UNDETERMINED,
    TOXIC_RESOLUTION_UNRECOGNISED,
    SafetyAnalyzer,
)

KOK = Path(__file__).resolve().parents[1]
PANEL_JS = KOK / 'hrma' / 'static' / 'js' / 'panels' / 'safety_panel.js'

#: Gövdeye sızmaması gereken Python iç metinleri (kardeş dosyaların listesi).
PYTHON_SIZINTISI = (
    'Traceback', 'not supported between', 'unsupported operand',
    'object of type', 'TypeError', 'KeyError', 'AttributeError',
    'NoneType', 'could not convert string to float',
    'float() argument', 'must be a string or a real number',
)

# Gövdeler kampanyanın KANONİK ölçüm gövdeleridir
# (``docs/scofield/raw/OH/Z5S/s3/capa.py``); sayı yeniden seçilmez, kardeş
# paketlerle aynı motor ölçülür. Bu uçların ZORUNLU alanı olduğu için
# ``wall_thickness`` eklendi (S3 çapası onu ayrı bir eksende süpürüyordu).
GUVENLIK = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
    'thrust': 1000.0, 'burn_time': 10.0, 'propellant_mass': 5.0,
    'chamber_diameter': 0.1, 'wall_thickness': 0.005,
}
TERMAL = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
    'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10.0,
    'throat_diameter': 0.02, 'material': 'steel_4130',
    'wall_thickness': 0.005,
}
YAPISAL = {
    'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
    'chamber_length': 0.5, 'throat_diameter': 0.02,
    'burn_time': 10.0, 'material': 'steel_4130',
    'wall_thickness': 0.005,
}


def _sessiz(fn, *a, **k):
    """Motor/veritabanı modülleri stdout'a bolca basıyor; testte sessize al."""
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon), contextlib.redirect_stderr(tampon):
        return fn(*a, **k)


@pytest.fixture(scope='module')
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _panel_iticileri():
    """``safety_panel.js`` PROPELLANTS listesinin ANAHTARLARI.

    Bekçinin totolojik olmamasının mekanizması budur: itici değerleri
    testin kendi hayalinden değil, ÜRÜNÜN seçicisinden gelir. Panel
    listesi değişirse bu bekçi otomatik olarak yeni kümeyi sınar.
    """
    metin = PANEL_JS.read_text(encoding='utf-8')
    blok = re.search(r'const PROPELLANTS = \[(.*?)\];', metin, re.S)
    assert blok, 'safety_panel.js içinde PROPELLANTS listesi bulunamadı'
    anahtarlar = re.findall(r"\[\s*'([^']+)'", blok.group(1))
    assert len(anahtarlar) >= 3, anahtarlar
    return anahtarlar


PANEL_ITICILERI = _panel_iticileri()


def _sizinti_yok(govde):
    metin = json.dumps(govde, ensure_ascii=False)
    sizanlar = [im for im in PYTHON_SIZINTISI if im in metin]
    assert not sizanlar, 'Gövdeye Python iç metni sızıyor %r: %s' % (
        sizanlar, metin[:400])


def _adli_ret(yanit, alan, beklenen_sinif=(400, 422)):
    """Reddin üç ayağı: 4xx sınıfı, makine-okur ALAN ADI, sızıntı yokluğu."""
    assert yanit.status_code in beklenen_sinif, (
        'Fizik dışı / tipsiz girdi kabul edildi (HTTP %s)' % yanit.status_code)
    govde = yanit.get_json()
    _sizinti_yok(govde)
    alanlar = [k.get('field') for k in (govde.get('invalid_fields') or [])]
    alanlar += govde.get('missing_fields') or []
    assert alan in alanlar, (
        "Ret gövdesi '%s' alanını adlandırmıyor: %s"
        % (alan, json.dumps(govde, ensure_ascii=False)[:400]))
    return govde


def _guvenlik(client, **ek):
    """Tam yanıt gövdesi (üst seviye ``toxic_basis`` künyesi dâhil)."""
    yanit = _sessiz(client.post, '/analyze_safety', json=dict(GUVENLIK, **ek))
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    return yanit.get_json()


def _toksik(client, **ek):
    return _guvenlik(client, **ek)['safety_analysis']


def _toksik_kunyesi(client, **ek):
    """Hüküm künyesi ÜST SEVİYEDEDİR (kardeşi ``thermal_basis`` gibi).

    Blok içinde durmamasının gerekçesi ``app.py::_lift_toxic_basis``ta
    yazılıdır: künye bir tehlike ölçüsü değil, o ölçünün dayanağıdır ve
    ``toxic_hazards`` bloğunun anahtar kümesini (dolayısıyla panel
    sözleşmesini) genişletmez.
    """
    govde = _guvenlik(client, **ek)
    return govde['toxic_basis'], govde['safety_analysis']['toxic_hazards']


# ---------------------------------------------------------------------------
# P7B3-21 (KRİTİK) — toksik hüküm KAZANILIR
# ---------------------------------------------------------------------------
class TestToksikHukumKazanilir:

    def test_panel_listesi_sozlesmeyle_ortusuyor(self):
        """Bekçinin çapası: panel seçicisi ile sunucu sözleşmesi AYNI küme.

        Bu eşitlik bozulursa kalanın hepsi anlamını yitirir — panel bir
        değer gönderebilir ama sunucu onu tanımaz (ya da tersi).
        """
        assert sorted(PANEL_ITICILERI) == sorted(KNOWN_PROPELLANT_CLASSES), (
            'safety_panel.js PROPELLANTS ile KNOWN_PROPELLANT_CLASSES '
            'ayrışmış: panel=%s sunucu=%s'
            % (sorted(PANEL_ITICILERI), sorted(KNOWN_PROPELLANT_CLASSES)))

    @pytest.mark.parametrize('itici', PANEL_ITICILERI)
    def test_panelin_gonderdigi_deger_hukmu_KAZANIR_ya_da_GERI_CEKER(
            self, client, itici):
        """Panelin her değeri ya hüküm üretir ya da AÇIKÇA geri çeker.

        Yasak olan üçüncü hâl: sessizce ``'NONE'`` basmak. Her yanıtta
        çözünürlük künyesi (``toxic_inventory_resolution``) bulunmak
        zorundadır — hükmün nereden geldiği okunabilir olmalı.
        """
        kunye, toksik = _toksik_kunyesi(client, propellant_type=itici)
        cozunurluk = kunye.get('toxic_inventory_resolution')
        assert cozunurluk in (TOXIC_RESOLUTION_TABULATED,
                              TOXIC_RESOLUTION_UNDETERMINED,
                              TOXIC_RESOLUTION_NOT_TABULATED), (
            "'%s' için çözünürlük künyesi yok/tanınmıyor: %r"
            % (itici, cozunurluk))
        assert kunye.get('toxic_inventory_basis'), (
            "'%s' hükmünün dayanağı yazılmamış" % itici)
        assert kunye.get('propellant_class') == itici

        if cozunurluk == TOXIC_RESOLUTION_UNDETERMINED:
            assert toksik['toxic_hazard_level'] == TOXIC_LEVEL_NOT_EVALUATED
        else:
            assert toksik['toxic_hazard_level'] != TOXIC_LEVEL_NOT_EVALUATED

    def test_hukum_urunun_gonderebildigi_bir_degerle_GERCEKTEN_atesleniyor(
            self, client):
        """Kapanış şartının birinci ayağı: hüküm ürün yolundan ateşlenebilir.

        Eski bekçi ürünün gönderemediği ``'hydrazine'`` ile yeşildi. Burada
        değer PANEL LİSTESİNDEN gelir ve en az biri gerçek bir envanter
        üretmek zorundadır.
        """
        atesleyenler = []
        for itici in PANEL_ITICILERI:
            toksik = _toksik(client, propellant_type=itici)['toxic_hazards']
            if toksik.get('toxic_components'):
                atesleyenler.append((itici, toksik))
        assert atesleyenler, (
            'Panelin gönderebildiği HİÇBİR değer toksik envanter üretmiyor '
            '— hüküm üründe ateşlenemiyor demektir')
        itici, toksik = atesleyenler[0]
        assert toksik['toxic_hazard_level'] in ('LOW', 'MEDIUM', 'HIGH'), (
            '%s için seviye yayımlanmadı: %r' % (itici, toksik))
        assert toksik.get('ppe_requirements'), (
            '%s için PPE listesi boş' % itici)
        assert toksik.get('release_scenarios'), (
            '%s için salım senaryosu üretilmedi' % itici)

    #: ÖH D15 birleştirme (1 Eyl 2026) — ALTI DEĞER İKİYE AYRILDI.
    #: Yapısal kulvarın P5B2-02 onarımı serbest metinde TABLOLU bileşen
    #: adı arıyor; ``'hydrazine'`` ve ``'n2o4'`` artık ADIYLA çözülüyor ve
    #: hüküm KAZANILIYOR (ölçüldü: ``resolution='tabulated'``,
    #: ``toxic_components=['hydrazine'] / ['n2o4']``, seviye MEDIUM). Bu
    #: bir fail-open değil, envanterin gerçekten bulunmasıdır — bekçinin
    #: eski varsayımı ("bu adlar tanınmaz") ÇÜRÜDÜ. Kalan dördü hâlâ
    #: çözülmüyor ve hüküm geri çekiliyor. Bekçi bu yüzden iki kola
    #: ayrıldı: kazanılmamış hüküm YASAK, kazanılmış hüküm ise DAYANAĞINI
    #: göstermek ZORUNDA.
    COZULEN_ADLAR = ['hydrazine', 'n2o4']
    COZULMEYEN_ADLAR = ['peynir', 'APCP', 'liquid', 'LOX/RP-1']

    @pytest.mark.parametrize('itici', COZULMEYEN_ADLAR)
    def test_bilinmeyen_itici_FAIL_CLOSED(self, client, itici):
        """Kapanış şartının ikinci ayağı: tanınmayan itici hüküm ÜRETMEZ."""
        analiz_govdesi = _guvenlik(client, propellant_type=itici)
        toksik = analiz_govdesi['safety_analysis']['toxic_hazards']
        assert toksik['toxic_hazard_level'] == TOXIC_LEVEL_NOT_EVALUATED, (
            "'%s' için hüküm yayımlandı (fail-open): %r"
            % (itici, toksik['toxic_hazard_level']))
        assert not toksik.get('toxic_components'), (
            "'%s' için envanter yokken bileşen listesi dolu" % itici)
        kunye = analiz_govdesi['toxic_basis']
        # Hüküm GERİ ÇEKİLDİĞİNİ söyleyen iki çözünürlük. Birleştirmeden
        # sonra ürün, çözülemeyen adı motor_type yedeğiyle bir SINIFA
        # bağlıyor (``class_inventory_undetermined``); hüküm yine
        # yayımlanmıyor ama künye artık daha kesin konuşuyor.
        assert kunye['toxic_inventory_resolution'] in (
            TOXIC_RESOLUTION_UNRECOGNISED,
            TOXIC_RESOLUTION_UNDETERMINED), kunye
        assert kunye.get('toxic_hazard_level_withheld_because'), (
            'hüküm geri çekildi ama gerekçesi yazılmadı')
        assert kunye.get('known_propellant_classes'), (
            'kullanıcıya hangi sınıfların tanındığı söylenmiyor')
        # ÖH D15: sınıf motor_type yedeğinden geldiyse kullanıcının YAZDIĞI
        # adın tanınmadığı SÖYLENMEK ZORUNDA. Aksi hâlde 'APCP' yazan
        # kullanıcı yanıtta yalnız 'liquid_biprop' görür ve adının
        # anlaşıldığını sanır.
        if kunye.get('propellant_class_source') == 'motor_type':
            dayanak = str(kunye.get('toxic_inventory_basis') or '')
            # Değer TIRNAKLI aranır: sınıf açıklamasının kendi metni
            # ('liquid_biprop ...') tesadüfen eşleşmesin.
            assert 'propellant_type' in dayanak and repr(itici) in dayanak, (
                "'%s' tanınmadı ama künye bunu söylemiyor: %r"
                % (itici, dayanak[:200]))
            # Sınıfın NEREDEN geldiği de yazılı olmalı. Motor tipinin
            # DEĞERİ burada YENİDEN YAZILMAZ (gövde onu göndermiyor; ucun
            # kendi varsayılanı) — yalnız kaynağın adı aranır.
            assert 'motor_type' in dayanak, (
                "sınıfın motor_type'tan geldiği söylenmiyor: %r"
                % dayanak[:200])
        else:
            assert kunye.get('propellant_class') is None, kunye

    @pytest.mark.parametrize('itici', COZULEN_ADLAR)
    def test_ADIYLA_cozulen_itici_hukmu_KAZANIR(self, client, itici):
        """İkinci ayağın ikizi: yayımlanan hüküm dayanağını göstermeli.

        Bu adlar ``self.toxic_hazards`` tablosunda ADIYLA vardır; hüküm
        oradan KAZANILIR. Bekçi hükmün varlığını değil, DAYANAĞINI kilitler:
        tablolu bileşen olmadan seviye yayımlanamaz.
        """
        analiz_govdesi = _guvenlik(client, propellant_type=itici)
        toksik = analiz_govdesi['safety_analysis']['toxic_hazards']
        kunye = analiz_govdesi['toxic_basis']
        assert kunye['toxic_inventory_resolution'] == (
            TOXIC_RESOLUTION_TABULATED), kunye
        assert itici.lower() in [str(b).lower()
                                 for b in toksik['toxic_components']], toksik
        assert toksik['toxic_hazard_level'] in ('LOW', 'MEDIUM', 'HIGH'), (
            "'%s' tabloda var ama seviye yayımlanmadı: %r"
            % (itici, toksik['toxic_hazard_level']))
        assert toksik.get('ppe_requirements'), toksik
        assert 'toxic_hazard_level_withheld_because' not in kunye or not (
            kunye.get('toxic_hazard_level_withheld_because')), (
            'hüküm hem yayımlandı hem "geri çekildi" diyor')

    def test_bos_dize_ILAN_EDILEN_varsayilana_dusuyor(self, client):
        """``''`` "verilmedi" demektir ve künye ile gerçek ÖRTÜŞMELİ.

        Taban ölçümünde ``defaults_applied`` "propellant_type varsayılanı
        uygulandı" diyordu ama ``data.get(key, default)`` anahtar VARSA
        varsayılanı uygulamıyor: çözücüye boş dize gidiyordu. İki iddia
        artık aynı değeri anlatıyor.
        """
        yanit = _sessiz(client.post, '/analyze_safety',
                        json=dict(GUVENLIK, propellant_type=''))
        assert yanit.status_code == 200
        govde = yanit.get_json()
        # ÖH D35 / OH-ON-06 — BEKÇİ ÇEVRİLDİ (gerekçeli). Bekçinin KONUSU
        # "künye ile çözücü AYNI değeri anlatsın" idi ve o konu KORUNUYOR;
        # değişen, anlattıkları değerin ne olduğudur. ``propellant_type``a
        # artık varsayılan UYGULANMIYOR (ölçüldü: o varsayılan bir hibrit
        # motora KATI kompozit hükmü bastırıyordu), dolayısıyla künyenin
        # "varsayılan uygulandı" demesi YALAN olurdu. İki iddia yine
        # örtüşüyor: künye de çözücü de "bu alan verilmedi" diyor.
        assert 'propellant_type' not in govde['defaults_applied'], (
            'uç, uygulamadığı bir varsayılanı künyede sayıyor')
        kunye = govde['toxic_basis']
        assert kunye['propellant_class'] is None, (
            'itici sınıfı verilmemişken künye bir sınıf ilan ediyor: %r'
            % kunye['propellant_class'])
        patlama = govde['safety_analysis']['explosive_hazards']
        assert patlama.get('explosive_verdict_withheld_because'), (
            'sınıf kazanılmadan patlayıcı ekseni yayımlandı')

    @pytest.mark.parametrize('itici', ['peynir', 'liquid_biprop'])
    def test_geri_cekilen_eksen_genel_hukmu_DUSURMUYOR(self, client, itici):
        """Ölçülmemiş eksen "düşük risk" diye okunamaz.

        Deponun kendi kanalı kullanılır: skor ``None`` -> eksen maksimuma
        girmez, ``risks_not_evaluated`` içinde adıyla yazılır, genel skor
        KISMİ imlenir ve kazanılmamış ``ACCEPTABLE`` geri çekilir.
        """
        risk = _toksik(client, propellant_type=itici)['risk_assessment']
        assert risk['individual_risks']['toxic'] is None, (
            'geri çekilen eksene sayı basılmış: %r'
            % risk['individual_risks']['toxic'])
        assert 'toxic' in risk['risks_not_evaluated']
        assert risk['overall_risk_score_is_partial'] is True
        assert risk['acceptability'] not in ('ACCEPTABLE',
                                             'ACCEPTABLE_WITH_CONTROLS'), (
            'toksik eksen ölçülmemişken kabul kararı verilmiş: %r'
            % risk['acceptability'])

    def test_kunye_UST_SEVIYEDE_blok_kumesi_genislemiyor(self, client):
        """Panel sözleşmesi korunur: ``toxic_hazards`` yeni çocuk kazanmaz.

        ``tests/test_z5_panel_sagirlik.py`` "uçtan gelen her dolu çocuk
        ekranda geçmeli" diyor ve ``safety_panel.js`` bu paketin mülkü
        DEĞİL. Künye bu yüzden bloğun içinde değil, kardeşi
        ``thermal_basis`` ile aynı yerde — üst seviyede — durur.
        """
        for itici in ('composite', 'liquid_monoprop', 'peynir'):
            govde = _guvenlik(client, propellant_type=itici)
            toksik = govde['safety_analysis']['toxic_hazards']
            sizan = [ad for ad in ('toxic_inventory_resolution',
                                   'toxic_inventory_basis', 'propellant_class',
                                   'known_propellant_classes',
                                   'toxic_hazard_level_withheld_because')
                     if ad in toksik]
            assert not sizan, (
                "'%s': künye alanları bloğa sızmış (panel sağırlık bekçisini "
                'kırar): %s' % (itici, sizan))
            assert govde['toxic_basis']['toxic_hazard_level'] == toksik[
                'toxic_hazard_level'], 'künye ile blok farklı seviye söylüyor'

    def test_bos_envanterde_bile_PPE_listesi_bos_degil(self, client):
        """Kalemin "boş PPE" ayağı: envanter yoksa da tezgâh PPE'si vardır."""
        for itici in ('composite', 'peynir'):
            toksik = _toksik(client, propellant_type=itici)['toxic_hazards']
            assert toksik.get('ppe_requirements'), (
                "'%s' için PPE listesi boş — 'hiç koruyucu gerekmez' diye "
                'okunur' % itici)

    def test_olu_dal_canlandi_serbest_metin_envanteri_cozuyor(self):
        """``'liquid_biprop n2o4'`` artık N2O4'ü tanıyor (eski kod: asla)."""
        analizci = SafetyAnalyzer()
        kunye = analizci._classify_toxic_inventory('liquid_biprop n2o4')
        assert kunye['components'] == ['n2o4']
        assert kunye['resolution'] == TOXIC_RESOLUTION_TABULATED
        cip = analizci._classify_toxic_inventory('liquid_biprop')
        assert cip['components'] == []
        assert cip['resolution'] == TOXIC_RESOLUTION_UNDETERMINED

    def test_toksik_tavsiye_olculmemis_eksende_SUSMUYOR(self, client):
        """Fail-closed tavsiye: eksen ölçülmediyse gaz algılama/PPE önerilir."""
        analiz = _toksik(client, propellant_type='peynir')
        kodlar = [str(o.get('code') if isinstance(o, dict) else o)
                  for o in (analiz.get('recommendations') or [])]
        assert any('toxic_gas_detection' in k for k in kodlar), (
            'toksik eksen ölçülmemişken tavsiye kanalı sustu: %s' % kodlar)


# ---------------------------------------------------------------------------
# P16B3-25 — propellant_mass = 0 (taban ölçümünde ZATEN kapalı; geri alınmaz)
# ---------------------------------------------------------------------------
class TestSifirIticiKutlesi:

    @pytest.mark.parametrize('deger', [0, 0.0, -5])
    def test_sifir_ve_negatif_kutle_adli_4xx(self, client, deger):
        yanit = _sessiz(client.post, '/analyze_safety',
                        json=dict(GUVENLIK, propellant_mass=deger))
        govde = _adli_ret(yanit, 'propellant_mass')
        assert govde.get('error') == 'invalid_safety_input'

    def test_sifir_kutle_TAM_GUVENLIK_PAKETI_uretmiyor(self, client):
        """Kalemin ölçümü: mprop=0 -> risk LOW + 98 sayılık paket."""
        yanit = _sessiz(client.post, '/analyze_safety',
                        json=dict(GUVENLIK, propellant_mass=0))
        govde = yanit.get_json()
        assert 'safety_analysis' not in govde, (
            'sıfır itici kütlesiyle güvenlik paketi yayımlanmış')


# ---------------------------------------------------------------------------
# P7B3-25 — /analyze_thermal_safety kapısı (taban: ZATEN kapalı)
# ---------------------------------------------------------------------------
class TestTermalKapi:

    def test_bos_govde_hukum_uretmiyor(self, client):
        yanit = _sessiz(client.post, '/analyze_thermal_safety', json={})
        assert yanit.status_code == 422
        govde = yanit.get_json()
        _sizinti_yok(govde)
        assert govde.get('error') == 'incomplete_thermal_input'
        eksik = govde.get('missing_fields') or []
        for alan in ('chamber_pressure', 'chamber_temperature',
                     'chamber_diameter', 'chamber_length', 'wall_thickness'):
            assert alan in eksik, '%s eksik listesinde yok: %s' % (alan, eksik)
        assert 'thermal_analysis' not in govde
        assert 'risk_level' not in json.dumps(govde)

    def test_gecerli_govde_hala_hukum_uretiyor(self, client):
        """Kapı, meşru koşumu kesmiyor (kapının ters yönü)."""
        yanit = _sessiz(client.post, '/analyze_thermal_safety', json=TERMAL)
        assert yanit.status_code == 200
        assert yanit.get_json()['thermal_analysis']


# ---------------------------------------------------------------------------
# P16B3-04 — ambient_temp künyesi DOĞRU
# ---------------------------------------------------------------------------
class TestOrtamSicakligiKanali:

    def test_kunye_iddiasi_gercek_kanalla_ortusuyor(self, client):
        """Künye "istekten yankılandı" diyorsa uç o alanı GERÇEKTEN okumalı."""
        yok = _sessiz(client.post, '/analyze_thermal_safety', json=TERMAL)
        var = _sessiz(client.post, '/analyze_thermal_safety',
                      json=dict(TERMAL, ambient_temp=500.0))
        assert yok.status_code == var.status_code == 200

        def _oku(yanit):
            tasarim = (yanit.get_json()['thermal_analysis']
                       ['design_parameters'])
            return tasarim['ambient_temperature'], tasarim.get(
                'ambient_temperature_basis') or ''

        varsayilan, kunye = _oku(yok)
        gonderilen, _ = _oku(var)
        assert 'ambient_temp' in kunye, (
            'künye artık istek alanını anmıyor — bekçi bayat: %r' % kunye[:200])
        assert varsayilan == pytest.approx(293.15)
        assert gonderilen == pytest.approx(500.0), (
            'ambient_temp gönderildi ama yaprak %r K\'de donuk kaldı — kanal '
            'kopmuş' % gonderilen)

    def test_kanal_yalniz_yanki_degil_HESAP_degisiyor(self, client):
        """Girdinin yankısı değil, cidar sıcaklıkları da kıpırdamalı."""
        yok = _sessiz(client.post, '/analyze_thermal_safety',
                      json=TERMAL).get_json()
        var = _sessiz(client.post, '/analyze_thermal_safety',
                      json=dict(TERMAL, ambient_temp=500.0)).get_json()

        def _yapraklar(d, p=''):
            if isinstance(d, dict):
                for k, v in d.items():
                    yield from _yapraklar(v, p + '.' + str(k))
            elif isinstance(d, list):
                for i, v in enumerate(d):
                    yield from _yapraklar(v, p + '[%d]' % i)
            else:
                yield p, d

        a, b = dict(_yapraklar(yok)), dict(_yapraklar(var))
        degisen = [k for k in a if k in b and a[k] != b[k]]
        yanki = {k for k in degisen if 'ambient' in k}
        assert len(degisen) - len(yanki) >= 5, (
            'ambient_temp yalnız yankı oynatıyor (yankı dışı %d yaprak) — '
            'alan hesaba girmiyor olabilir' % (len(degisen) - len(yanki)))

    def test_alan_verilmezse_govde_BIT_AYNI(self, client):
        """Kanal açılması meşru koşumun sayılarını DEĞİŞTİRMEZ."""
        bir = _sessiz(client.post, '/analyze_thermal_safety',
                      json=TERMAL).get_json()
        iki = _sessiz(client.post, '/analyze_thermal_safety',
                      json=dict(TERMAL, ambient_temp=None)).get_json()
        bir_metin = json.dumps(bir, sort_keys=True)
        iki_kopya = dict(iki)
        iki_kopya.pop('inputs_treated_as_absent', None)
        assert json.dumps(iki_kopya, sort_keys=True) == bir_metin

    @pytest.mark.parametrize('deger,gerekce', [
        (-5, 'must_be_positive'), (0, 'must_be_positive'),
        ('peynir', 'not_a_number'), (True, 'not_a_number'),
        (float('nan'), 'not_finite'), (float('inf'), 'not_finite'),
    ])
    def test_bozuk_ortam_sicakligi_adli_4xx(self, client, deger, gerekce):
        yanit = _sessiz(client.post, '/analyze_thermal_safety',
                        json=dict(TERMAL, ambient_temp=deger))
        govde = _adli_ret(yanit, 'ambient_temp')
        gerekceler = [k.get('reason') for k in govde['invalid_fields']]
        assert gerekce in gerekceler, gerekceler


# ---------------------------------------------------------------------------
# S1-04 — iki kardeş kapının BİRLEŞİMİ
# ---------------------------------------------------------------------------
class TestKardesKapiBirlesimi:

    #: Birleşim kapısının reddetmek ZORUNDA olduğu değerler. 0/negatif
    #: listede YOKTUR: o, yapısal uçta ilan edilmiş bir boyutlandırma
    #: sentinelidir (panelin varsayılanı) ve asimetri BEYANLIDIR.
    RET_VAKALARI = [
        ('birim_hatasi', 1e9),
        ('bool', True),
        ('nan', float('nan')),
        ('inf', float('inf')),
        ('metin', 'peynir'),
        ('liste', [1, 2]),
    ]

    @pytest.mark.parametrize('ad,deger', RET_VAKALARI)
    @pytest.mark.parametrize('uc,taban', [
        ('/analyze_structural_safety', YAPISAL),
        ('/analyze_thermal_safety', TERMAL),
    ])
    def test_iki_uc_da_AYNI_kumeyi_reddediyor(self, client, uc, taban, ad,
                                              deger):
        """Hiçbir uç diğerinin üst kümesi değil sorunu: artık ikisi de red.

        Taban ölçümünde ``1e9`` yapısal uçta 422, termal uçta HTTP 200 +
        7715 baytlık TAM termal hüküm veriyordu.
        """
        yanit = _sessiz(client.post, uc,
                        json=dict(taban, wall_thickness=deger))
        _adli_ret(yanit, 'wall_thickness')

    @pytest.mark.parametrize('deger', [0, -0.005])
    def test_sentinel_asimetrisi_BEYANLI(self, client, deger):
        """0/negatif: yapısal uçta boyutlandırma kipi, termal uçta red.

        Fark meşrudur (tasarım yolu / doğrulama yolu) ama SESSİZ olamaz:
        yapısal uç kullanıcının değerinin atıldığını yazmak zorundadır.
        """
        yapisal = _sessiz(client.post, '/analyze_structural_safety',
                          json=dict(YAPISAL, wall_thickness=deger))
        assert yapisal.status_code == 200
        govde = yapisal.get_json()
        assert 'wall_thickness' in (govde.get('inputs_treated_as_absent')
                                    or []), (
            'atılan cidar üst düzey kanalda beyan edilmiyor: %s'
            % json.dumps(govde.get('inputs_treated_as_absent')))
        temel = govde['design_basis']
        assert temel['is_verification'] is False
        assert temel['verdict'] == 'withheld'

        termal = _sessiz(client.post, '/analyze_thermal_safety',
                         json=dict(TERMAL, wall_thickness=deger))
        _adli_ret(termal, 'wall_thickness')

    def test_gecerli_cidarda_iki_uc_da_hukum_veriyor(self, client):
        for uc, taban in (('/analyze_structural_safety', YAPISAL),
                          ('/analyze_thermal_safety', TERMAL)):
            yanit = _sessiz(client.post, uc, json=taban)
            assert yanit.status_code == 200, uc
            assert yanit.get_json().get('inputs_treated_as_absent') is None, (
                '%s: geçerli cidarda "yok sayıldı" beyanı basılmış' % uc)

    def test_ortak_kapi_TEK_yerde(self):
        """Birleşim kapısı iki uçta KOPYALANMAZ; tek işlevden gelir."""
        from hrma import app as app_modulu
        kaynak = Path(app_modulu.__file__).read_text(encoding='utf-8')
        assert kaynak.count('_cidar_birim_kapisi(') >= 3, (
            'ortak kapı iki uçtan da çağrılmıyor')


# ---------------------------------------------------------------------------
# P16B3-15 — atılan cidar ADIYLA söylenir
# ---------------------------------------------------------------------------
class TestAtilanCidarBeyani:

    # P16B1-33 (D30 app-api-uc a1, 0dd609b7): wall_thickness=0 artık 'hiç verilmedi' ile
    # AYNI künyeyi taşımaz — kendi adıyla 'sizing_sentinel' (panelin 'benim için boyutlandır'
    # sözleşmesi); sınıf (sized_by_hrma) ve is_verification=False değişmedi.
    @pytest.mark.parametrize('deger,durum', [
        # ÇEVRİLDİ — ÖH D30 / app-api-uc **a1** · P16B1-33 + P16B1-42.
        # ``0`` satırı ``'not_supplied'`` bekliyordu ve KUSURU KORUYORDU:
        # kullanıcı alanı GÖNDERİYOR (değeri 0), ürün ise "hiç vermediniz"
        # diyordu. a1 künyeyi doğruya çevirdi (0 = "sen boyutlandır"
        # sentineli) ama bu bekçiyi çevirmemişti; borç a3 süpürmesinde
        # yakalandı (ölçüm: a2 ağacı ``294e6559`` bu satırda KIRMIZI,
        # dalga tabanı ``ab7cf68b`` yeşil). Ad KOPYALANMAZ, a1'in tek
        # kaynağından okunur. Sentinel DAVRANIŞI değişmedi: alan yine
        # "yok sayılanlar" listesinde ve hüküm yine geri çekiliyor —
        # aşağıdaki üç iddia aynen duruyor.
        (0, WALL_INPUT_SIZING_SENTINEL), (-1.0, 'not_positive'),
    ])
    def test_atilan_deger_kunyesiyle_yayimlaniyor(self, client, deger, durum):
        yanit = _sessiz(client.post, '/analyze_structural_safety',
                        json=dict(YAPISAL, wall_thickness=deger))
        assert yanit.status_code == 200
        govde = yanit.get_json()
        assert govde['inputs_treated_as_absent'] == ['wall_thickness']
        kunye = govde['inputs_treated_as_absent_basis']['wall_thickness']
        assert kunye['input_status'] == durum
        assert str(deger) in str(kunye['submitted'])
        assert kunye['reason']

    def test_kullanicinin_cidari_kullanildiginda_beyan_YOK(self, client):
        yanit = _sessiz(client.post, '/analyze_structural_safety',
                        json=dict(YAPISAL, wall_thickness=0.005))
        govde = yanit.get_json()
        assert 'inputs_treated_as_absent' not in govde
        assert govde['design_basis']['is_verification'] is True


# ---------------------------------------------------------------------------
# P7B3-29 — /api/fea/thermal gelen profilin beyanlarını DÜŞÜRMÜYOR
# ---------------------------------------------------------------------------
HIBRIT_GOVDE = {
    'motor_type': 'hybrid', 'thrust': 5000, 'burn_time': 10,
    'chamber_pressure': 20, 'of_ratio': 2.5, 'fuel_type': 'htpb',
    'oxidizer_type': 'n2o', 'expansion_ratio': 4.0, 'nozzle_type': 'conical',
    'chamber_material': 'steel_4130', 'wall_thickness': 5,
}
FEA_KUCUK = {'n_axial': 12, 'n_radial': 4, 'max_halvings': 3}
FEA_BASLIK = {'Host': '127.0.0.1:8080'}


@pytest.fixture(scope='module')
def motor(client):
    yanit = _sessiz(client.post, '/calculate', json=HIBRIT_GOVDE,
                    headers=FEA_BASLIK)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    return yanit.get_json()['motor']


@pytest.fixture(scope='module')
def profil(client, motor):
    yanit = _sessiz(client.post, '/api/analysis/wall-profile', json={
        'chamber_pressure': motor['chamber_pressure'],
        'chamber_temperature': motor['chamber_temperature'],
        'chamber_diameter': motor['chamber_diameter'],
        'chamber_length': motor['chamber_length'],
        'burn_time': motor['burn_time'],
        'mdot_total': motor['mdot_total'],
        'throat_diameter': motor['throat_diameter'],
        'exit_diameter': motor['exit_diameter'],
        'expansion_ratio': motor['expansion_ratio'],
        # V301/FİZİK-2 (NK-12) — ÇEVRİLDİ, gerekçeli: termal alan yalnız
        # lüledir ve ağ motorun LÜLE malzemesiyle (bu motorda grafit)
        # çözülür; profil de ağın malzemesiyle istenir (P7B3-30 kapısı).
        # Eski 'steel_4130' kamara malzemesiydi — kusurun kendisi. Bu
        # sınıfın iddiası (profil beyanları düşmüyor) malzemeden bağımsızdır.
        'nozzle_type': 'conical',
        'material': ag_malzemesi(motor, 'steel_4130'),
        'wall_thickness': 0.005,
    }, headers=FEA_BASLIK)
    assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
    return yanit.get_json()['wall_profile']


class TestProfilBeyanlariKorunuyor:

    def _kos(self, client, motor, profil):
        yanit = _sessiz(client.post, '/api/fea/thermal',
                        json=dict(FEA_KUCUK, motor=motor,
                                  axial_profile=profil,
                                  ambient_temperature_K=293.15),
                        headers=FEA_BASLIK)
        assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
        return yanit.get_json()['fea']

    def test_profil_uyarisi_FEA_uyari_kanalina_gecer(self, client, motor,
                                                     profil):
        """h(z)'nin güvenilmez olduğunu söyleyen uyarı yanıtta GÖRÜNMELİ."""
        beyanli = dict(profil)
        beyanli['warnings'] = [{'code': 'warn.cfd.y_plus_out_of_band',
                                'severity': 'warning'}]
        beyanli['y_plus_max'] = 141.3
        beyanli['source'] = 'hrma/cfd/steady.py'

        sade = self._kos(client, motor, profil)
        zengin = self._kos(client, motor, beyanli)

        kodlar = [u.get('code') for u in (zengin.get('warnings') or [])
                  if isinstance(u, dict)]
        assert 'warn.cfd.y_plus_out_of_band' in kodlar, (
            'profilin uyarısı FEA yanıtından düştü: %s' % kodlar)
        kaynaklar = [u.get('origin') for u in (zengin.get('warnings') or [])
                     if isinstance(u, dict)]
        assert 'axial_profile' in kaynaklar, (
            'taşınan uyarının kaynağı imlenmemiş')
        assert zengin.get('warnings_include_supplied_profile') is True

        beyan = zengin['axial_profile_declarations']['supplied_by_caller']
        assert beyan['y_plus_max'] == 141.3
        assert beyan['source'] == 'hrma/cfd/steady.py'

        # Sayılar DEĞİŞMEDİ: beyan taşımak fiziği kıpırdatmaz.
        assert (zengin['scalars']['peak_wall_T_K']
                == pytest.approx(sade['scalars']['peak_wall_T_K']))

    def test_cozucunun_okudugu_alanlar_ADIYLA_ilan_ediliyor(self, client,
                                                            motor, profil):
        """ÖH D18 / P6B2-01 ŞART — liste ``wall_resolution``ı da SAYAR.

        ÇEVRİLDİ (gerekçe): bu bekçi ``consumed_by_solver`` listesini tam
        üç adla kilitliyordu. D16'da köprüye (``fea/bridge.py``) duvar
        çözünürlüğü kapısı girdi: profilin ``wall_resolution`` bloğu
        ``resolved is not True`` ise profil FAIL-CLOSED reddediliyor.
        Yani alan o günden beri TÜKETİLİYOR — ama beyan kanalı onu hâlâ
        "çözücünün okumadığı" alanlar arasında gösteriyordu ve BU BEKÇİ
        o yanlış beyanı SÖZLEŞME hâline getiriyordu (kusuru koruyan
        bekçi). Ölçüm: docs/scofield/raw/OH/D18/fea-cfd/a1/
        once_p6b2_01_beyan.json — aynı profilin yalnız bu bloğu
        değiştirilince köprünün hükmü NOT_MODELLED ⟷ ok arasında dönüyor.
        """
        from hrma.fea.bridge import THERMAL_PROFILE_CONSUMED_KEYS
        fea = self._kos(client, motor, profil)
        beyan = fea['axial_profile_declarations']
        # ÖH D24 / P6B2-01 ŞARTI: tam liste artık ELLE yazılmaz — köprünün
        # tek kaynağına bağlanır. Bekçi böylece köprüye yeni bir tüketilen
        # alan eklendiğinde sessizce eskimez; kilitlediği şey listenin
        # İÇERİĞİ değil, uç katmanının köprüyle AYNI listeyi söylemesidir.
        assert beyan['consumed_by_solver'] == list(
            THERMAL_PROFILE_CONSUMED_KEYS)
        assert beyan['_basis']
        # Çözücünün okuduğu alanlar beyan kanalında TEKRARLANMAZ.
        for anahtar in THERMAL_PROFILE_CONSUMED_KEYS:
            assert anahtar not in beyan['supplied_by_caller']

    def test_sayisal_diziler_beyan_kanalinda_KOPYALANMIYOR(self, client,
                                                           motor, profil):
        """Beyan kanalı sayı taşımaz; adı ve uzunluğu duyurur."""
        fea = self._kos(client, motor, profil)
        gelen = fea['axial_profile_declarations']['supplied_by_caller']
        assert gelen['q_MW']['echoed'] is False
        assert gelen['q_MW']['item_count'] == len(profil['q_MW'])
        assert gelen['q_MW']['reason']


# ---------------------------------------------------------------------------
# EK MADDE 1 (P9B4-12 / OH-Z5-04) — /api/get-fuel-properties fail-closed
# ---------------------------------------------------------------------------
class TestYakitOzellikleriFailClosed:

    @pytest.mark.parametrize('yakit', ['htpb', 'paraffin', 'rp1'])
    def test_kazanilmamis_katsayida_500_yok_null_var(self, client, yakit):
        """Taban ölçümü: ``htpb`` ve ``paraffin`` HTTP 500 + ham Python metni."""
        yanit = _sessiz(client.post, '/api/get-fuel-properties',
                        json={'fuel_type': yakit})
        assert yanit.status_code == 200, yanit.get_data(as_text=True)[:300]
        govde = yanit.get_json()
        _sizinti_yok(govde)
        ozellikler = govde['properties']
        assert ozellikler['cp'] is None, (
            '%s için uydurma cp basılmış: %r' % (yakit, ozellikler['cp']))
        assert 'cp' in ozellikler['unavailable_fields']
        assert ozellikler['unavailable_reason'], (
            'sayı basılmadı ama NEDENİ söylenmedi')
        assert ozellikler['data_status']['coefficients_usable'] is False
        assert govde['real_time'] is False, (
            'hesap koşmadığı hâlde "gerçek zamanlı" iddiası duruyor')

    @pytest.mark.parametrize('yakit', ['lh2', 'methane'])
    def test_kazanilmis_katsayida_sayi_HALA_uretiliyor(self, client, yakit):
        """Fail-closed kapı meşru yolu kesmiyor."""
        yanit = _sessiz(client.post, '/api/get-fuel-properties',
                        json={'fuel_type': yakit})
        assert yanit.status_code == 200
        govde = yanit.get_json()
        assert isinstance(govde['properties']['cp'], float)
        assert govde['properties'].get('unavailable_fields') is None
        assert govde['real_time'] is True

    # ÖH D27 / app-api a3 (P7B4-02) — İKİ BEKÇİ GEREKÇELİ ÇEVRİLDİ.
    #
    # İkisi de tanınmayan bir yakıt için HTTP 200 ŞART KOŞUYORDU; yani
    # ürünün RP-1 kaydını "etanolün özellikleri" diye yayımlamasını
    # KİLİTLİYORLARDI. Birincisi ikamenin ADIYLA söylenmesini istiyordu —
    # o beyan D26 a4'te geldi ve ölçülerek doğrulandı (``a3/once.json``
    # K2: ``substituted_record='rp1'``, ``substituted_basis`` dolu). Ama
    # Doktrin 1: BEYAN ÇÖZÜM DEĞİLDİR. ``status='success'`` diyen bir
    # gövdede duran 810,0 kg/m³ ve ``C12H23``, üstüne yazılan cümleyle
    # etanolün özelliği hâline gelmez.
    #
    # İDDİA KORUNDU, YÖNÜ DÖNDÜ: "ikame edilen kayıt adıyla söylensin"
    # yerine "İKAME EDİLMESİN" sınanıyor; ikinci bekçi de aynı biçimde
    # 200 yerine adlı 422 istiyor. Onarımın geri alınması ikisini de
    # KIRMIZI yapar (ters-mutasyon M3).
    def test_taninmayan_yakit_IKAME_EDILMEZ_adiyla_reddedilir(self, client):
        """Tanınmayan yakıt RP-1'in sayılarını ALMAZ; adıyla reddedilir."""
        for ad in ('peynir', 'ethanol'):
            yanit = _sessiz(client.post, '/api/get-fuel-properties',
                            json={'fuel_type': ad})
            assert yanit.status_code == 422, (
                '%s için hâlâ hüküm yayımlanıyor: %s'
                % (ad, yanit.get_data(as_text=True)[:200]))
            govde = yanit.get_json()
            assert govde['error'] == 'unknown_fuel'
            alanlar = [k['field'] for k in govde['invalid_fields']]
            assert alanlar == ['fuel_type']
            # Sayı YAYIMLANMADI: RP-1'in iki imzası gövdenin hiçbir yerinde
            metin = json.dumps(govde)
            assert 'C12H23' not in metin
            assert '810' not in metin.replace('810 kg/m^3', '')
            # Kullanıcı ne isteyebileceğini yanıttan öğrenir
            assert 'rp1' in govde['accepted_fuel_types']

    def test_kayitsiz_yakit_da_ADLI_422_alir(self, client):
        yanit = _sessiz(client.post, '/api/get-fuel-properties',
                        json={'fuel_type': 'nonexistent_but_cached'})
        assert yanit.status_code == 422
        assert yanit.get_json()['error'] == 'unknown_fuel'


# ---------------------------------------------------------------------------
# EK MADDE 2 (OH-Z5-11) — /api/six-dof-analysis künyeleri düşmüyor
# ---------------------------------------------------------------------------
#: Kampanyanın kanonik 6-DOF gövdesi (``s3/capa.py::SIXDOF``) CG'yi VERİYOR;
#: bu paketin ölçtüğü şey ise CG VERİLMEDİĞİNDE ne olduğudur. Bu yüzden
#: gövde AYRI ADLA durur ve farkı adında taşır: aynı motor, eksik CG.
SIXDOF_CG_YOK = {
    'body_diameter': 0.1, 'body_length': 2.0, 'dry_mass': 20.0,
    'thrust': 1000.0, 'burn_time': 10.0, 'propellant_mass': 5.0, 'cd0': 0.5,
}


class TestUcusOzetiKunyeleri:

    def test_varsayilan_CG_ile_kararlilik_hukmu_kunyesiz_YAYIMLANMIYOR(
            self, client):
        yanit = _sessiz(client.post, '/api/six-dof-analysis',
                        json=SIXDOF_CG_YOK)
        assert yanit.status_code == 200
        govde = yanit.get_json()
        ozet, kunye = govde['summary'], govde['stability_basis']
        assert 'stable' in ozet, 'kararlılık hükmü yayımlanmıyor'
        assert ozet['x_cg_full'] is not None
        assert ozet['x_cg_empty'] is not None
        assert kunye['x_cg_is_estimate'] is True
        assert kunye['x_cg_source'] == 'assumed_length_fraction'
        assert 'static_margin_basis' in kunye, (
            'statik marj VARSAYILAN CG üzerine kurulu ama bu söylenmiyor')
        assert kunye['_basis']

    def test_kunye_UST_SEVIYEDE_ozet_kumesi_borcu_buyutmuyor(self, client):
        """``tests/test_wave4b_contract.py`` borç envanteri BÜYÜMEZ.

        ``sixdof_panel.js`` ``x_cg_full`` / ``x_cg_empty`` / ``warnings``
        adlarını zaten okuyor; dayanak alanlarını okumuyor. Bu yüzden künye
        özete DEĞİL, kardeşi ``thermal_basis`` ile aynı yere — üst seviyeye
        — konur.
        """
        govde = _sessiz(client.post, '/api/six-dof-analysis',
                        json=SIXDOF_CG_YOK).get_json()
        sizan = [ad for ad in ('x_cg_source', 'x_cg_is_estimate',
                               'static_margin_basis', 'converged',
                               'solver_message', 'input_defaults_substituted',
                               'input_defaults_substituted_basis')
                 if ad in govde['summary']]
        assert not sizan, (
            'künye alanları özete sızmış (ters-yön borç envanterini '
            'büyütür): %s' % sizan)

    def test_kullanici_CG_verirse_kunye_dogrulamaya_doner(self, client):
        yanit = _sessiz(client.post, '/api/six-dof-analysis',
                        json=dict(SIXDOF_CG_YOK, x_cg_full=1.2,
                                  x_cg_empty=1.0))
        kunye = yanit.get_json()['stability_basis']
        assert kunye['x_cg_is_estimate'] is False
        assert kunye['x_cg_source'] == 'supplied'
        assert 'static_margin_basis' not in kunye

    def test_ucun_kendi_varsayilanlari_BEYAN_ediliyor(self, client):
        yanit = _sessiz(client.post, '/api/six-dof-analysis',
                        json=SIXDOF_CG_YOK)
        kunye = yanit.get_json()['stability_basis']
        ikame = kunye['input_defaults_substituted']
        for alan in ('nose_length', 'fin_count', 'rail_length',
                     'launch_elevation_deg'):
            assert alan in ikame, '%s ikame edildi ama beyan edilmedi' % alan
        for alan in ('body_diameter', 'body_length', 'dry_mass', 'cd0'):
            assert alan not in ikame, (
                '%s kullanıcıdan geldi ama "varsayılan" diye imlendi' % alan)
        assert kunye['input_defaults_substituted_basis']

    def test_cozucu_uyarilari_ozetten_dusmuyor(self, client):
        yanit = _sessiz(client.post, '/api/six-dof-analysis',
                        json=SIXDOF_CG_YOK)
        govde = yanit.get_json()
        kodlar = [u.get('code') for u in (govde['summary'].get('warnings') or [])
                  if isinstance(u, dict)]
        assert kodlar, 'çözücünün uyarıları uç yüzünden düşüyor'
        assert govde['stability_basis']['solver_converged'] is True
