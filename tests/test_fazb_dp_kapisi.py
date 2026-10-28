"""ÖH Faz B-1 / B11 — ``/calculate_liquid`` tank ΔP kapısının UÇ bekçisi.

BAĞLANAN DEFTER KALEMLERİ
-------------------------
P14M2-04b (yüksek, açık)
    ``hrma/utils/common_fixes.py:22``'deki chug eşiğinin canlı kopyası
    ``0,15·Pc`` → ``0,015·Pc`` yönünde GEVŞETİLDİĞİNDE ``/calculate_liquid``
    fail-closed ΔP kapısı **tamamen açılıyor** (ΔP/Pc = 0,02 ve 0,10'da
    HTTP 400 → 200) ve mutasyoncunun koşumunda **0 kırmızı** çıkıyor.
    Hakem ölçümü (P14 H2 §M2-04b): ``grep -rn
    "validate_pressure_consistency\\|CommonValidation\\|common_fixes" tests/``
    → **hiç eşleşme yok**; modülün adını anan TEK test dosyası yoktu.
    12 dosyalık sıvı odaklı küme (410 test) mutasyonda sessiz kalıyordu.
P14M2-04 (orta, açık) — çaprazı
    Aynı satırın SIKMA yönündeki mutasyonu (0,15 → daha büyük) yalnız
    kolateral yakalanıyordu: 11 kırmızı + 119 hatanın hiçbiri eşik testi
    değildi, eşiğin kendi bekçisi ``test_chug_esigi_tek_kaynak`` YEŞİL
    kaldı. Yani o bekçi eşiğin ADINI sınıyor, DAVRANIŞINI değil.

Bu dosya envanter boşluğunu da kapatır: adı geçen modül artık ``tests/``
altında anılıyor. Ama asıl iş envanter değil DAVRANIŞ — bir birim testi
``validate_pressure_consistency``ı doğrudan çağırsaydı modül adı geçerdi
ama kapının ÜRÜN ucunda CANLI olduğunu kanıtlayamazdı. Kapı gerçek bir
emniyet kapısıdır: yetersiz enjektör ΔP'si chug (düşük frekanslı yanma
kararsızlığı) demektir ve kabul edilen tasarım kullanıcıya "geçerli" diye
döner. Bu yüzden bekçi UÇTAN, Flask test istemcisiyle ölçer.

SAYILAR NEREDEN GELİYOR — EŞİĞİ-KENDİNDEN-TÜRETME YASAĞI
--------------------------------------------------------
Aşağıdaki hiçbir sayı üründen İTHAL EDİLMEZ. ``common_fixes`` içindeki
``0.15`` katsayısı ne import edilir ne de dosyadan okunur (P14 H2 kural
adayı + savcı §3.1 adım 9: *bir eşiği koruyan iddia o eşikten TÜRETİLMİŞ
olamaz*; karşı örnek P14M4-03d). Sayılar **ölçülmüş vakalardır** —
26 Ağustos 2026, HEAD 344714d, ``docs/scofield/raw/P14/H2-probe-cf.py``
sondasının yeniden koşumu:

    Pc = 100 bar,  tank = 102,0 → ΔP/Pc = 0,02 → HTTP 400
        "Insufficient pressure drop. Need at least 15.0 bar drop ..."
    Pc = 100 bar,  tank = 110,0 → ΔP/Pc = 0,10 → HTTP 400  (aynı gerekçe)
    Pc = 100 bar,  tank = 120,0 → ΔP/Pc = 0,20 → HTTP 200
    Pc = 100 bar,  tank = 100,0 → ΔP/Pc = 0,00 → HTTP 400  (birinci dal)
    Pc = 100 bar,  tank =  95,0 → ΔP/Pc = -0,05 → HTTP 400 (birinci dal)
    Pc =  40 bar,  tank =  44,0 → ΔP/Pc = 0,10 → HTTP 400
        "Insufficient pressure drop. Need at least 6.0 bar drop ..."
    Pc =  40 bar,  tank =  48,0 → ΔP/Pc = 0,20 → HTTP 200

Yani eşik ORANDIR, mutlak bar değil: Pc = 40'ta 8 bar'lık düşüş geçiyor,
Pc = 100'de 10 bar'lık düşüş geçmiyor. ``TestKapiOrandir`` bu ayrımı
kilitler — ``0.15 * chamber_pressure`` yerine sabit ``15`` yazan bir
mutasyon Pc = 40 / ΔP/Pc = 0,20 vakasını 400'e çevirirdi.

BU BEKÇİNİN GÖREMEDİĞİ (dürüst çözünürlük beyanı)
-------------------------------------------------
Çapa vakaları ΔP/Pc ∈ {0,02; 0,10} ve {0,20}. Dolayısıyla bekçi, eşiği
0,10'un ALTINA indiren her gevşetmeyi görür (P14M2-04b'nin 0,015'i dahil,
10× pay) ve 0,20'nin ÜSTÜNE çıkaran her sıkmayı görür. Aradaki ince
kaydırmalar (ör. 0,15 → 0,12) bu bekçiye GÖRÜNMEZ. Aralığı daraltmak
mümkündü ama o zaman sınır eşiğin kendisinden türetilmiş olurdu — kural
gereği yapılmadı. Ölçülen vakaların dışına çıkan bir iddia yazılmadı.

YÖNTEM
------
Sunucuya port bağlanmaz; ``app.test_client()`` kullanılır
(``tests/test_endpoint_guards.py`` ile aynı fikstür sözleşmesi).
Reddin GEREKÇESİ de sınanır: yalnız durum koduna bakmak, isteği başka
bir sebeple (eksik girdi 422, aralık dışı değer) düşüren bir yolu ΔP
kapısı sanmaya yol açardı.
"""

import warnings

import pytest

warnings.filterwarnings('ignore')


# ---------------------------------------------------------------------------
# Ölçülmüş vakalar — sayılar üründen değil, koşum çıktısından gelir
# ---------------------------------------------------------------------------

#: Sonda koşumunun oda basıncı (bar). ``/calculate_liquid`` aralık kapısı
#: 10-500 bar kabul eder; 100 bar sondanın ölçtüğü noktadır.
PC_ANA = 100.0

#: İkinci ölçek noktası — kapının ORAN mı MUTLAK mı olduğunu ayırır.
PC_IKINCI = 40.0

#: Kapının ISIRDIĞI ölçülmüş ΔP/Pc oranları (her ikisi de HTTP 400).
ISIRAN_ORANLAR = (0.02, 0.10)

#: Kapının GEÇİRDİĞİ ölçülmüş ΔP/Pc oranı (HTTP 200).
GECEN_ORAN = 0.20

#: Reddin ΔP kapısından geldiğini ayırt eden gerekçe parçası. Backend EN
#: üretir (bkz. tests/test_app_hata_dili.py sözleşmesi), bu yüzden metin
#: İngilizce aranır. Tam metin değil ÇEKİRDEĞİ aranır: "15.0 bar" gibi
#: eşikten türeyen bir sayı iddiaya SOKULMAZ.
RET_GEREKCESI = 'insufficient pressure drop'

#: Birinci dalın (tank ≤ Pc) gerekçe çekirdeği.
RET_GEREKCESI_SIRALAMA = 'must be greater than chamber pressure'

#: Reddin FAIL-CLOSED olduğunu gösteren şart: yanıt gövdesinde tasarım
#: üretilmiş olamaz. Bu anahtarlar 200 yanıtında bulunur (ölçüldü).
TASARIM_ANAHTARLARI = ('motor_geometry', 'performance', 'plots')


def istek_govdesi(pc, tank_bar):
    """``/calculate_liquid``'in beş zorunlu alanı + sınanan tank basıncı.

    Beş kritik alan (thrust, chamber_pressure, mixture_ratio, fuel_type,
    oxidizer_type) eksik bırakılırsa uç 422 ``incomplete_input`` döner ve
    ΔP kapısına HİÇ ULAŞILMAZ (hrma/app.py, Faz 4B bulgu 57.3 bloğu).
    Bekçinin 400'ü o 422 ile karışmasın diye gövde eksiksiz gönderilir.
    """
    return {
        'thrust': 10000.0,
        'chamber_pressure': pc,
        'mixture_ratio': 2.5,
        'fuel_type': 'rp1',
        'oxidizer_type': 'lox',
        # ÖH D27 / OH-D26-12 — ÖNERME AÇIK YAZILIYOR (bekçi ÇEVRİLDİ).
        # Bu dosyanın bütün iddiaları "tank enjektörü besler" önermesine
        # dayanır: ΔP/Pc oranı TANK ile HAZNE arasındaki düşüşten kurulur.
        # O önerme YALNIZ basınç beslemeli çevrimde doğrudur; gövde çevrimi
        # söylemediği için uç turbopompalı varsayılana düşüyordu ve bekçi
        # kendi fiziğini SÖYLEMEDEN ölçüyordu. Turbopompalı çevrimde
        # ``tank_pressure`` bu ucun okumadığı bir alandır ve artık adıyla
        # reddediliyor (422 ``tank_pressure_not_read_in_turbopump_cycle``);
        # yani buraya çevrim yazılmazsa bu dosya ΔP kapısını DEĞİL o yeni
        # kapıyı ölçerdi.
        #
        # ÇAPA KORUNDU — sayılar değişmedi, YENİDEN ÖLÇÜLDÜ (8 Eyl 2026,
        # dal dalga27/sivi; ``docs/scofield/raw/OH/D27/sivi/a1/sonra.json``
        # ``OH-D26-12.fazb_capasi``): engine_cycle='pressure_fed' ile
        #   Pc=100: ΔP/Pc 0,02 -> 400 | 0,10 -> 400 | 0,20 -> 200 |
        #           0,00 -> 400 | -0,05 -> 400
        #   Pc= 40: ΔP/Pc 0,02 -> 400 | 0,10 -> 400 | 0,20 -> 200 |
        #           0,00 -> 400 | -0,05 -> 400
        # yani ölçülen yedi vakanın yedisi de AYNI kaldı. Eşik hâlâ
        # üründen türetilmiyor; eklenen tek şey gövdenin kendi önermesini
        # ilan etmesidir.
        'engine_cycle': 'pressure_fed',
        'tank_pressure': tank_bar,
        # V301/L-A (SV-03) — BEKLENTİ KORUNDU, GÖVDE TAMAMLANDI. Bu gövde
        # yalnız ``tank_pressure`` gönderiyordu; çözücü basınç beslemeli
        # çevrimde tankı ``feed_pressure``dan okur, yani "sağlıklı" 0,20
        # vakası aslında 3 bar'lık yedek tankla (marj -119 bar, critical
        # uyarı) 200 alıyordu. V301/L-A'dan beri o yedek tasarım 422
        # ``pressure_fed_feed_pressure_not_supplied`` ile reddediliyor.
        # Ölçüldü (L-A sonda, Pc 100 / tank 120): ΔP_enj varsayılanı (%22)
        # ile gerekli besleme 123,76 bar -> 422; bu yüzden gövde aynı tankı
        # ``feed_pressure`` olarak da verir ve enjektör ΔP'sini 0,10·Pc
        # (Pc 100'de 10 bar, Pc 40'ta 4 bar) seçer — iki ölçek noktası da
        # 200 (marj 8,25 / 2,13 bar). Chug kapısının ölçtüğü oran (tank −
        # Pc) DEĞİŞMEDİ; ısıran vakalar aynı 400'ü aynı gerekçeyle alır.
        'feed_pressure': tank_bar,
        'injector_pressure_drop': 0.10 * pc,
    }


def tank_basinci(pc, dp_orani):
    """ΔP/Pc oranından tank basıncı (bar). Eşikle ilgisi yok — girdi kurar."""
    return pc * (1.0 + dp_orani)


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def gonder(client, pc, dp_orani):
    """İsteği gönderir; (durum kodu, gövde sözlüğü) döndürür."""
    yanit = client.post('/calculate_liquid',
                        json=istek_govdesi(pc, tank_basinci(pc, dp_orani)))
    try:
        govde = yanit.get_json() or {}
    except Exception:  # pragma: no cover — gövde JSON değilse iddia zaten düşer
        govde = {}
    return yanit.status_code, govde


# ===========================================================================
# 1) Kapı ISIRIYOR mu — P14M2-04b'nin doğrudan bekçisi
# ===========================================================================

class TestYetersizDpReddedilir:
    """ΔP/Pc = 0,02 ve 0,10 → HTTP 400, gerekçesi ΔP kapısının kendisi.

    P14M2-04b'nin mutasyonu (0,15 → 0,015) bu sınıfın İKİ testini de
    kırmızıya çevirir: her iki oran da 400 yerine 200 döner (ölçüldü).
    """

    @pytest.mark.parametrize('dp_orani', ISIRAN_ORANLAR)
    def test_yetersiz_dp_400_doner(self, client, dp_orani):
        kod, govde = gonder(client, PC_ANA, dp_orani)
        assert kod == 400, (
            f"ΔP/Pc={dp_orani} yetersiz enjektör düşüşüdür (chug riski) ve "
            f"fail-closed reddedilmeliydi; uç HTTP {kod} döndü. "
            f"Gövde: {str(govde)[:200]}")

    @pytest.mark.parametrize('dp_orani', ISIRAN_ORANLAR)
    def test_ret_gerekcesi_dp_kapisini_gosterir(self, client, dp_orani):
        """400, ΔP kapısından gelmeli — başka bir doğrulamadan değil."""
        kod, govde = gonder(client, PC_ANA, dp_orani)
        assert kod == 400
        metin = str(govde.get('error', '')).lower()
        assert RET_GEREKCESI in metin, (
            f"ΔP/Pc={dp_orani} reddedildi ama gerekçe ΔP kapısına ait "
            f"görünmüyor: {metin!r}. Bekçi yanlış kapıyı sınıyor olabilir.")

    @pytest.mark.parametrize('dp_orani', ISIRAN_ORANLAR)
    def test_ret_fail_closed_tasarim_uretmez(self, client, dp_orani):
        """Reddedilen istek TASARIM DÖNDÜRMEZ (uyarıp hesaplamak yasak).

        Kapı 'uyarı üretip devam et' biçimine dönüştürülürse durum kodu
        200 olmasa bile gövde tasarım taşıyabilir; bu iddia o yolu kapatır.
        """
        kod, govde = gonder(client, PC_ANA, dp_orani)
        assert kod == 400
        sizan = [a for a in TASARIM_ANAHTARLARI if a in govde]
        assert not sizan, (
            f"Fail-closed ret tasarım sızdırdı: {sizan}")


# ===========================================================================
# 2) Kapı SAĞLIKLI tasarımı geçiriyor mu — sıkma yönü (P14M2-04 çaprazı)
# ===========================================================================

class TestSaglikliDpGecer:
    """ΔP/Pc = 0,20 → HTTP 200. Kapı fail-closed ama kapalı-takılı değil.

    P14M2-04'ün SIKMA mutasyonu (0,15 → büyütme) bu testi kırmızıya
    çevirir. O mutasyon bugün yalnız kolateral yakalanıyordu; eşiğin kendi
    bekçisi ``test_chug_esigi_tek_kaynak`` YEŞİL kalıyordu (ad sınıyor,
    davranış sınamıyor).
    """

    def test_yeterli_dp_200_doner(self, client):
        kod, govde = gonder(client, PC_ANA, GECEN_ORAN)
        assert kod == 200, (
            f"ΔP/Pc={GECEN_ORAN} ölçülmüş SAĞLIKLI vakadır; uç HTTP {kod} "
            f"döndü. Gövde: {str(govde)[:200]}")

    def test_gecen_istek_gercekten_tasarim_uretir(self, client):
        """200 boş kabuk olmamalı — kapı 'geçirdi' derken hesap da olmalı."""
        kod, govde = gonder(client, PC_ANA, GECEN_ORAN)
        assert kod == 200
        assert 'motor_geometry' in govde, (
            'Kabul edilen istek tasarım üretmedi; 200 içi boş.')


# ===========================================================================
# 3) Kapı ORAN kapısıdır, mutlak bar kapısı değil
# ===========================================================================

class TestKapiOrandir:
    """Aynı ΔP/Pc oranı FARKLI oda basıncında aynı hükmü vermeli.

    Ölçülen ayrım: Pc = 40 bar'da 8 bar'lık düşüş (ΔP/Pc = 0,20) GEÇİYOR,
    Pc = 100 bar'da 10 bar'lık düşüş (ΔP/Pc = 0,10) GEÇMİYOR. Eşiği sabit
    bir bar değerine çeviren bir mutasyon (``0.15 * chamber_pressure`` →
    ``15``) ikinci testi kırmızıya çevirir; birinci ölçek noktası tek
    başına o mutasyonu göremezdi.
    """

    def test_ikinci_olcekte_de_yetersiz_dp_reddedilir(self, client):
        kod, govde = gonder(client, PC_IKINCI, 0.10)
        assert kod == 400, (
            f"Pc={PC_IKINCI} bar'da ΔP/Pc=0,10 da reddedilmeliydi "
            f"(kapı orandır); uç HTTP {kod} döndü.")
        assert RET_GEREKCESI in str(govde.get('error', '')).lower()

    def test_ikinci_olcekte_saglikli_dp_gecer(self, client):
        kod, govde = gonder(client, PC_IKINCI, GECEN_ORAN)
        assert kod == 200, (
            f"Pc={PC_IKINCI} bar'da ΔP/Pc=0,20 (yalnız {PC_IKINCI * 0.2:.0f} "
            f"bar düşüş) ölçülmüş SAĞLIKLI vakadır; uç HTTP {kod} döndü. "
            f"Eşik mutlak bar'a çevrilmiş olabilir. "
            f"Gövde: {str(govde)[:200]}")


# ===========================================================================
# 4) Kapının BİRİNCİ dalı — tank basıncı oda basıncını geçmeli
# ===========================================================================

class TestTankOdadanYuksekOlmali:
    """``tank ≤ Pc`` dalı ayrı bir iddiadır ve ayrı gerekçe üretir.

    Bu dal silinirse ΔP dalı yine ısırırdı (0 ve negatif düşüş zaten
    eşiğin altında), o yüzden davranış farkı YALNIZ gerekçede görünür.
    İddia bu yüzden gerekçeye de bakar.
    """

    @pytest.mark.parametrize('dp_orani', (0.0, -0.05))
    def test_tank_odaya_esit_veya_dusukse_reddedilir(self, client, dp_orani):
        kod, govde = gonder(client, PC_ANA, dp_orani)
        assert kod == 400, (
            f"ΔP/Pc={dp_orani}: tank basıncı oda basıncını geçmiyor, "
            f"besleme fiziksel olarak imkânsız; uç HTTP {kod} döndü.")
        assert RET_GEREKCESI_SIRALAMA in str(govde.get('error', '')).lower(), (
            'Sıralama dalı kendi gerekçesini üretmiyor; ΔP dalına '
            'düşmüş olabilir (ayrı iddia kayboldu).')


# ===========================================================================
# 5) BELGELİ KIRMIZI — ret gerekçesi hangi ALANI düzelteceğini söylemiyor
# ===========================================================================

class TestRetGerekcesiAlaniAdlandirir:
    """Ret gerekçesi, düzeltilecek istek ALANINI adlandırmalı.

    ÖLÇÜLEN (26 Ağustos 2026, HEAD 344714d): gerekçe
    "Insufficient pressure drop. Need at least 15.0 bar drop for proper
    injection" — içinde ne ``tank_pressure`` ne de "tank" geçiyor. Oysa
    ``/calculate_liquid`` gövdesinde ÜÇ ayrı basınç-düşüşü alanı var
    (``tank_pressure``, ``feed_pressure``, ``injector_pressure_drop`` —
    bkz. ``tests/test_liquid_input_wiring.py`` BASE_PAYLOAD); çağıran
    hangisini düzelteceğini yanıttan çıkaramıyor.

    Bu, deponun KENDİ sözleşmesine de aykırı: aynı ucun eksik-girdi dalı
    422 + ``missing_fields`` döndürüyor, ``input_guard`` ise her sorunu
    ``{'field', 'reason', 'value'}`` üçlüsüyle adlandırıyor
    (``hrma/app.py:977-1010``). Yalnız bu fail-closed dal alansız.

    Kapının KENDİSİ doğru çalıştığı için bu ayrı bir kalemdir: davranış
    doğru, TEŞHİS EDİLEBİLİRLİK eksik. Defterde P14M2-04b'nin altında
    kayıtlı DEĞİL — Faz B-1 ölçümünde YENİ bulundu, koordinatöre devir.
    Onarım (gerekçeye alan adı eklenmesi) inince xfail KALKAR; strict
    olduğu için kalkmazsa süit XPASS ile uyarır.

    ONARILDI — ÖH D15 / kulvar app-api / aşama 2 (P7B2-09, birinci ayak).
    ``hrma/app.py`` ΔP reddi artık ``invalid_fields`` taşıyor:
    ``{'field': 'tank_pressure', 'reason':
    'insufficient_injector_pressure_drop', 'value': ...}``; ``note``
    alanında çözücünün KENDİ tank basıncının (turbopompalı çevrimde
    3,0 bar) ayrı bir büyüklük olduğu da yazılı. Bu sınıfın
    ``xfail(strict=True)`` işareti bu yüzden KALDIRILDI — dosyanın kendi
    yazdığı şart yerine geldi. İddia AYNEN korundu ve artık ileri yönde
    (yeşil) koşuyor: onarımın geri alınması bu testi KIRMIZI yapar.
    """

    @pytest.mark.parametrize('dp_orani', ISIRAN_ORANLAR)
    def test_gerekce_alan_adini_tasir(self, client, dp_orani):
        kod, govde = gonder(client, PC_ANA, dp_orani)
        assert kod == 400
        havuz = ' '.join(str(govde.get(a, '')) for a in
                         ('error', 'field', 'fields', 'invalid_fields')).lower()
        assert 'tank_pressure' in havuz, (
            f"Ret gerekçesi düzeltilecek alanı adlandırmıyor: "
            f"{str(govde)[:200]}")
