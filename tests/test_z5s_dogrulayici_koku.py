"""ÖH Z5S / S3 — DOĞRULAYICI KÖKÜNÜN ÜÇ YAPISAL DELİĞİ + İKİ HESAP BOMBASI.

Kapsanan defter kalemleri: P16B1-37, P16B1-36, P16B1-23, P16S1-01, P16B1-49,
P16B2-12, P16B1-39, P16B1-52 + EK MADDE (simple/uzaytek rotaları — 23 Eyl
2026'da tersine çevrildi: iki sayfa söküldü, bekçi 404 ister).

Bu dosyadaki her bekçi, ONARIMDAN ÖNCE ÖLÇÜLMÜŞ bir davranışa karşı yazıldı.
Ölçüm kanıtı: ``docs/scofield/raw/OH/Z5S/s3/`` (once_supurme.json,
once_kapsam.json, once_bomba_repro.json, once_capa.json ⟷ sonra/taban_capa.json).

BEKÇİLERİN İDDİASI — "kapı var" DEĞİL, "kapı ULAŞILABİLİR":
Bu paketin kusurlarının ortağı, kapının kodda DURMASI ama ürünün gönderdiği
istekle hiç TETİKLENEMEMESİYDİ. Bu yüzden testler doğrulayıcıyı doğrudan
çağırmakla yetinmez; ürünün gerçekten gönderdiği alan adlarıyla UÇTAN geçer.
"""
import json
import math

import pytest

from hrma.validation.motor_validation import (
    FIELD_ALIASES, FORM_LIMITS, motor_validator)


# --- ortak yükler ---------------------------------------------------------
#: Sağlıklı hibrit gövde: bu paketin hiçbir onarımı bunu reddetmemelidir.
HIBRIT = {
    'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
    'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
    'chamber_pressure': 20.0, 'l_star': 1.0, 'expansion_ratio': 4.0,
    'include_plots': False,
}
YAPISAL = {
    'chamber_pressure': 20.0, 'chamber_diameter': 0.1,
    'chamber_length': 0.5, 'throat_diameter': 0.02, 'burn_time': 10.0,
}
TERMAL = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
    'chamber_diameter': 0.1, 'chamber_length': 0.5, 'burn_time': 10.0,
    'throat_diameter': 0.02, 'wall_thickness': 0.005,
}
GUVENLIK = {
    'chamber_pressure': 20.0, 'chamber_temperature': 3000.0,
    'thrust': 1000.0, 'burn_time': 10.0, 'propellant_mass': 5.0,
    'chamber_diameter': 0.1, 'wall_thickness': 0.005,
}


@pytest.fixture
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _alanlar(govde):
    """Yanıttaki ``invalid_fields`` kayıtlarının alan adları."""
    return [k.get('field') for k in (govde or {}).get('invalid_fields', [])]


# ===========================================================================
# P16B1-37 + P16B1-36 — KANAL ADI TUTMUYOR
# ===========================================================================
class TestKanalAdi:
    """Doğrulayıcının bandı ÜRÜNÜN gönderdiği adla da tetiklenmeli.

    ÖLÇÜLDÜ (once_supurme.json, A bölümü): 14 bandın 10'u hibrit yükünde
    ULAŞILAMAZDI. Aynı sayı iki adla iki farklı hükme uğruyordu::

        {"temperature": -500}          -> HTTP 400
        {"chamber_temperature": -500}  -> HTTP 200 + tam motor tasarımı

    Dördü de ``ULASILAMAZ: true`` ölçüldü: chamber_temperature,
    chamber_diameter_input, chamber_length_override, initial_port_diameter.
    """

    @pytest.mark.parametrize('urun_ad,deger', [
        ('chamber_temperature', -500.0),      # P16B1-36'nın tam vakası
        ('chamber_diameter_input', 9000.0),   # 9000 mm = 9 m > 5 m
        ('initial_port_diameter', 9000.0),    # 9000 m
        ('chamber_length_override', 1e9),     # her iki birim okumasında da yok
    ])
    def test_urun_adiyla_bant_ulasilabilir(self, client, urun_ad, deger):
        r = client.post('/calculate', json=dict(HIBRIT, **{urun_ad: deger}))
        assert r.status_code == 400, (
            f'{urun_ad}={deger} hâlâ kabul ediliyor (HTTP {r.status_code}): '
            'kanal adı tutmuyor, bant ULAŞILAMAZ. %s'
            % r.get_data(as_text=True)[:300])
        j = r.get_json() or {}
        assert urun_ad in _alanlar(j), (
            'ret gerekçesi KULLANICININ alan adını söylemiyor: %s'
            % json.dumps(j, ensure_ascii=False)[:400])

    def test_kunye_hangi_kanonik_banda_cozuldugunu_soyluyor(self, client):
        """Reddi okuyan, hangi bandın uygulandığını metinden çıkarmak
        zorunda kalmamalı (adlı-4xx sözleşmesi)."""
        r = client.post('/calculate',
                        json=dict(HIBRIT, chamber_temperature=-500.0))
        kayit = (r.get_json() or {})['invalid_fields'][0]
        assert kayit['resolved_as'] == 'temperature'
        assert kayit['accepted_range'] == [200.0, 5000.0]
        assert kayit['unit'] == 'K'

    def test_eksi_500_kelvin_solved_by_model_diye_gecistirilmiyor(self, client):
        """P16B1-36: −500 K, 3000 K ile AYNI beyan biçimini alamaz.

        Ölçülen eski davranış: HTTP 200 ve
        ``reason='solved_by_model', submitted=-500,0`` — yani imkânsız
        sıcaklık, çözücünün üzerine yazdığı MEŞRU bir girdi gibi
        sunuluyordu.
        """
        r = client.post('/calculate',
                        json=dict(HIBRIT, chamber_temperature=-500.0))
        assert r.status_code == 400
        govde = json.dumps(r.get_json() or {}, ensure_ascii=False)
        assert 'solved_by_model' not in govde, (
            'imkânsız sıcaklık hâlâ "çözücü kendi hesapladı" diye '
            'geçiştiriliyor: %s' % govde[:400])


class TestKanalAdiGerilemeKapisi:
    """Takma ad tablosu ÜRÜNÜN MEŞRU gönderimini reddetmemeli.

    Bu sınıf, onarımın kendi tuzağına karşıdır. Düz bir ad eşlemesi üç
    canlı sayfayı kırardı; ölçülen üç tuzak (bkz. ``FIELD_ALIASES``):
    birim (mm ⟷ m), "0 = otomatik" sentineli, ve ürün ile motorun birim
    konusunda ANLAŞAMADIĞI alan.
    """

    @pytest.mark.parametrize('urun_ad,deger,gerekce', [
        ('chamber_diameter_input', 0, 'arayüz varsayılanı: 0 = otomatik'),
        ('initial_port_diameter', 0, 'arayüz varsayılanı: 0 = otomatik'),
        ('chamber_length_override', 0, 'arayüz varsayılanı: 0 = otomatik'),
        ('chamber_diameter_input', 100.0, '100 mm hazne = 0,1 m, meşru'),
        ('initial_port_diameter', 0.03, '30 mm port = 0,03 m, meşru'),
        ('chamber_length_override', 500.0, 'arayüz mm gönderiyor (500 mm)'),
        ('chamber_length_override', 0.5, 'motor m okuyor (0,5 m)'),
        ('chamber_temperature', 3000.0, 'tipik hazne sıcaklığı'),
    ])
    def test_mesru_urun_degeri_reddedilmiyor(self, client, urun_ad, deger,
                                             gerekce):
        r = client.post('/calculate', json=dict(HIBRIT, **{urun_ad: deger}))
        assert r.status_code == 200, (
            f'{urun_ad}={deger} reddedildi ({gerekce}) — bant kapısı ürünün '
            'kendi gönderdiği değeri kırıyor: %s'
            % r.get_data(as_text=True)[:300])

    def test_birim_celiskili_alan_tek_okumaya_baglanmadi(self):
        """``chamber_length_override`` için ürün mm, motor m diyor.

        Bu bir BİRİM KANONU kararıdır ve bu turda verilmedi. Bekçi, tablonun
        o alanda tek bir okumaya bağlanmadığını (yani iki okumanın
        birleşiminin uygulandığını) sabitler — biri seçilirse bu test
        kırmızıya döner ve kararın bilinçli verildiği görülür.
        """
        assert len(FIELD_ALIASES['chamber_length_override']['carpanlar']) == 2

    def test_sifir_otomatik_alanlari_kayitli(self):
        for ad in ('chamber_diameter_input', 'initial_port_diameter',
                   'chamber_length_override'):
            assert FIELD_ALIASES[ad]['sifir_otomatik'] is True, ad
        assert FIELD_ALIASES['chamber_temperature']['sifir_otomatik'] is False


# ===========================================================================
# P16B1-23 — NaN ARALIK BANDINI GEÇİYOR
# ===========================================================================
class TestNanKorlugu:
    """``value < min or value > max`` NaN'da İKİSİ DE False.

    ÖLÇÜLDÜ (once_supurme.json, B bölümü): ``tank_pressure``,
    ``chamber_pressure``, ``thrust``, ``of_ratio`` — dördünde de NaN için
    ``is_valid=True`` ve TEK BİR MESAJ BİLE YOK. ``inf`` yakalanıyordu
    (``inf > max`` doğrudur), yani kapı sonsuzu görüp NaN'ı görmüyordu.
    """

    @pytest.mark.parametrize('alan', ['tank_pressure', 'chamber_pressure',
                                      'thrust', 'of_ratio', 'burn_time'])
    def test_nan_banda_takiliyor(self, alan):
        ok, mesajlar = motor_validator.validate_motor_data(
            dict(HIBRIT, **{alan: float('nan')}), 'hybrid')
        assert ok is False, (
            f'{alan}=NaN doğrulayıcıyı geçti — bant NaN körü '
            '(IEEE-754: NaN ile her karşılaştırma False)')
        assert any(alan in m and 'range' in m for m in mesajlar), mesajlar

    def test_nan_hazne_basinci_ucta_da_reddediliyor(self, client):
        """Ürün yüzü: NaN ile motor p=nan bar ile koşturulmamalı."""
        r = client.post('/calculate',
                        json=dict(HIBRIT, chamber_pressure=float('nan')))
        assert r.status_code == 400, r.get_data(as_text=True)[:300]
        kayit = [k for k in (r.get_json() or {}).get('invalid_fields', [])
                 if k.get('field') == 'chamber_pressure']
        assert kayit and kayit[0]['reason'] == 'not_finite', kayit

    def test_sonsuz_davranisi_degismedi(self):
        """``inf`` zaten yakalanıyordu; onarım onu bozmamalı."""
        ok, mesajlar = motor_validator.validate_motor_data(
            dict(HIBRIT, thrust=float('inf')), 'hybrid')
        assert ok is False
        assert any('thrust' in m and 'range' in m for m in mesajlar)

    def test_mesaj_bicimi_ceviri_suzgeciyle_uyumlu(self):
        """i18n borcunu artırmama şartı.

        ``i18n_charts.js`` şu deseni çeviriyor:
        ``^(.+) = (.+) is outside valid range \\[(.+)\\] (.*)$``.
        NaN mesajı bilerek AYNI biçimde üretilir, yeni çeviri anahtarı
        doğmaz.
        """
        import re
        _, mesajlar = motor_validator.validate_motor_data(
            dict(HIBRIT, chamber_pressure=float('nan')), 'hybrid')
        desen = re.compile(r'^(.+) = (.+) is outside valid range \[(.+)\] (.*)$')
        assert any(desen.match(m) for m in mesajlar), mesajlar


# ===========================================================================
# P16S1-01 + P16B1-49 — ÜST SINIR DELİĞİ
# ===========================================================================
class TestUstSinir:
    """"En olgun kapı" 1e9'a 200 basıyordu.

    ÖLÇÜLDÜ (once_supurme.json C + once_kapsam.json): 4 çağrı yerinden 1'i
    ``ranges=`` geçiyordu; kapılı 23 alanın 3'ünün üst sınırı vardı. Beş
    sarsımın beşi de HTTP 200 + TAM hüküm veriyordu (16.963 / 16.379 /
    18.058 / 7.651 / 8.022 yaprak).
    """

    @pytest.mark.parametrize('yol,taban,alan', [
        ('/analyze_structural_safety', YAPISAL, 'chamber_pressure'),
        ('/analyze_structural_safety', YAPISAL, 'chamber_diameter'),
        ('/analyze_thermal_safety', TERMAL, 'chamber_pressure'),
        ('/analyze_thermal_safety', TERMAL, 'chamber_temperature'),
        ('/analyze_safety', GUVENLIK, 'chamber_pressure'),
    ])
    def test_1e9_hukum_uretemiyor(self, client, yol, taban, alan):
        r = client.post(yol, json=dict(taban, **{alan: 1e9}))
        assert r.status_code == 422, (
            f'{yol} {alan}=1e9 için HTTP {r.status_code} — üst sınır yok, '
            'fiziksel olarak imkânsız girdiden hüküm basılıyor')
        j = r.get_json() or {}
        kayit = [k for k in j.get('invalid_fields', [])
                 if k.get('field') == alan]
        assert kayit, j
        assert kayit[0]['reason'] == 'out_of_range'
        # ÖH D27 a2 / OH-D25-23 — BEKÇİ ÇEVRİLDİ: bandın adı kanona
        # (``accepted_range``) geçti; testin sorduğu şey değişmedi
        # ("ret kabul edilen bandı söylüyor mu"), yalnız anahtar adı.
        assert 'accepted_range' in kayit[0], (
            'ret kabul edilen bandı SÖYLEMİYOR: %s' % kayit[0])

    @pytest.mark.parametrize('yol,taban', [
        ('/analyze_structural_safety', YAPISAL),
        ('/analyze_thermal_safety', TERMAL),
        ('/analyze_safety', GUVENLIK),
    ])
    def test_saglikli_govde_hala_hukum_uretiyor(self, client, yol, taban):
        """Üst sınır eklemek ALT sınır eklemek DEĞİLDİR."""
        r = client.post(yol, json=taban)
        assert r.status_code == 200, r.get_data(as_text=True)[:300]

    def test_ust_sinir_kanonik_tablodan_geliyor(self):
        """Yeni eşik İCAT EDİLMEDİ: sınırlar deponun kendi tablosundan.

        Bu bekçi, birinin ileride bu uçlara elle bir sayı yazmasını
        engeller — sınır ``motor_validator.limits`` ile aynı kalmalı.
        """
        from hrma.app import _ust_sinir_bandi
        bant = _ust_sinir_bandi(('chamber_pressure', 'chamber_diameter',
                                 'chamber_temperature'))
        assert bant['chamber_pressure'] == (
            0.0, float(motor_validator.limits['chamber_pressure']['max']))
        assert bant['chamber_diameter'] == (
            0.0, float(motor_validator.limits['chamber_diameter']['max']))
        # takma ad üzerinden çözülen alan
        assert bant['chamber_temperature'] == (
            0.0, float(motor_validator.limits['temperature']['max']))

    def test_alt_sinir_eklenmedi(self):
        """Aralığın altı 0.0'dır: "> 0" koşulu ``positive``ın işidir."""
        from hrma.app import _ust_sinir_bandi
        for _alan, (alt, _ust) in _ust_sinir_bandi(
                ('chamber_pressure', 'burn_time', 'thrust')).items():
            assert alt == 0.0

    @pytest.mark.parametrize('alan', ['chamber_pressure', 'chamber_diameter',
                                      'chamber_length', 'throat_diameter'])
    def test_tek_bozuk_alan_tek_satir_uretiyor(self, client, alan):
        """Üst sınır eklemek, aynı hatayı İKİ KEZ bildirmek değildir.

        ``ranges`` kapalı bir aralıktır: doğrudan geçilseydi
        ``chamber_pressure = -1`` hem ``must_be_positive`` hem
        ``out_of_range`` üretir ve arayüzde tek hata iki satır olarak
        görünürdü. Mevcut bir bekçi bunu zaten ölçüyor
        (``tests/test_faz5_app_analiz.py``); buradaki ikiz, S3'ün o
        sözleşmeyi kırmadığını kendi dosyasında da sabitler.
        """
        r = client.post('/analyze_structural_safety',
                        json=dict(YAPISAL, **{alan: -1}))
        assert r.status_code == 422
        assert _alanlar(r.get_json()) == [alan], (
            'tek bozuk alan için birden çok ret satırı üretildi: %s'
            % json.dumps(r.get_json(), ensure_ascii=False)[:300])

    def test_tablosuz_alana_dokunulmadi(self):
        """Kanonik bandı olmayan alana sınır UYDURULMAZ."""
        from hrma.app import _ust_sinir_bandi
        bant = _ust_sinir_bandi(('propellant_mass', 'mdot_total',
                                 'wall_thickness'))
        assert bant == {}, (
            'kanonik tabloda karşılığı olmayan alana eşik icat edildi: %s'
            % bant)


# ===========================================================================
# P16B2-12 — ÜÇ FORMDA ÜÇ BANT, HİÇBİRİ BEYAN EDİLMİYOR
# ===========================================================================
class TestFormBantlari:
    """Aynı fiziksel alan üç sekmede üç farklı bant; yanıt bandı söylemiyor.

    ÖLÇÜLDÜ (once_supurme.json, D bölümü): ``chamber_pressure = 3 bar``
    hibritte 200, katıda 400 (5-200), sıvıda 400 (10-500). 18 sarsımın
    18'inde ``bant_beyani: false``.
    """

    KATI = {'motor_name': 'S3', 'propellant_type': 'APCP', 'burn_time': 3.0,
            'chamber_diameter': 98.0, 'core_diameter': 30.0,
            'grain_length': 500.0, 'expansion_ratio': 6.0}
    SIVI = {'motor_name': 'S3', 'thrust': 5000, 'burn_time': 20,
            'of_ratio': 2.2, 'fuel_type': 'rp1', 'oxidizer_type': 'lox',
            'expansion_ratio': 8.0, 'mixture_ratio': 2.2}

    @pytest.mark.parametrize('yol,taban,form,alt,ust', [
        ('/calculate_solid', KATI, 'solid', 5, 200),
        ('/calculate_liquid', SIVI, 'liquid', 10, 500),
    ])
    def test_ret_bandi_beyan_ediyor(self, client, yol, taban, form, alt, ust):
        r = client.post(yol, json=dict(taban, chamber_pressure=3.0))
        assert r.status_code == 400
        kayit = (r.get_json() or {}).get('invalid_fields')
        assert kayit, (
            'ret hâlâ yalnız insan metni — kullanıcı hangi bandın '
            'uygulandığını makine-okur biçimde göremiyor: %s'
            % r.get_data(as_text=True)[:300])
        assert kayit[0]['field'] == 'chamber_pressure'
        assert kayit[0]['accepted_range'] == [alt, ust]
        assert kayit[0]['unit'] == 'bar'
        assert kayit[0]['motor_form'] == form, (
            'hangi motor formunun bandı olduğu söylenmiyor — kullanıcının '
            'asıl sorusu bu')

    def test_bant_degerleri_degismedi(self):
        """Tek kaynağa toplamak, DEĞER değiştirmek değildir.

        Bantların birbirinden farklı olmasının fiziksel bir gerekçesi mi
        yoksa tarihsel bir kaza mı olduğu AYRI bir karardır (Berke'lik).
        Bu bekçi, tekilleştirmenin sessizce bir bandı kaydırmadığını
        sabitler — tarihsel değerler burada yazılıdır.

        ÖH D26 / P16B1-49 (B ayağı) — İKİ SATIR ÇEVRİLDİ, GEREKÇESİYLE.
        Bu bekçi ``AYNI BİRİMDE`` yazılmış tarihsel bant farklarını korumak
        için yazılmıştı ve o işini yapmaya devam ediyor (basınç ve itki
        satırları AYNEN duruyor). Ama iki satırı, farklı bir sınıfa ait bir
        kusuru da kilitliyordu: ``solid.chamber_diameter`` ve
        ``solid.grain_length`` MİLİMETREdir, kanonik bantları
        (``CANONICAL_LIMITS``) METREdir; yani bu iki girdi "aynı birimde
        farklı sayı" değil, **BİRİM ÇELİŞKİSİ** taşıyordu. Ölçüldü
        (``docs/scofield/raw/OH/D26/app-api/a2/once.json`` K1/K2): alt uçları
        kanonun mm görünümüyle BİREBİR aynıydı (10 = 0,01 × 1000;
        50 = 0,05 × 1000) ama üst uçları elle yazılmıştı, öyle ki aynı alanın
        mm üst sınırı üründe iki farklı sayıyla dolaşıyordu — burada 2000,
        kanondan türeten ``bolted_joint.seal_diameter_max_mm()``de 5000.
        Karar (ana model hükmü): kanon SI'dir, form katmanı GÖRÜNTÜ birimidir
        ve ayrı sayı tutamaz. İki satır bu yüzden sabit sayıdan TÜRETİME
        çevrildi; sayı icat edilmedi, kanonun kendi ifadesi yazıldı.
        """
        assert FORM_LIMITS['solid']['chamber_pressure'][:2] == (5, 200)
        assert FORM_LIMITS['liquid']['chamber_pressure'][:2] == (10, 500)
        assert FORM_LIMITS['quick_geometry']['chamber_pressure'][:2] == (1, 500)
        assert FORM_LIMITS['liquid']['thrust'][:2] == (100, 1e7)
        assert FORM_LIMITS['liquid']['mixture_ratio'][:2] == (0.5, 20)
        # Birim çelişkili iki girdi: DEĞER değil, KANONUN GÖRÜNÜMÜ sabitlenir.
        from hrma.validation.motor_validation import (
            CANONICAL_LIMITS, kanon_gorunumu)
        for _alan in ('chamber_diameter', 'grain_length'):
            assert FORM_LIMITS['solid'][_alan] == kanon_gorunumu(_alan, 'mm')
            assert FORM_LIMITS['solid'][_alan][:2] == (
                CANONICAL_LIMITS[_alan]['min'] * 1000.0,
                CANONICAL_LIMITS[_alan]['max'] * 1000.0)

    def test_uc_form_ayni_sayiya_hala_farkli_davraniyor_ve_bunu_soyluyor(
            self, client):
        """Farkın KENDİSİ onarılmadı (karar Berke'lik) ama ARTIK GÖRÜNÜR.

        7 bar: katıda geçer, sıvıda geçmez. Onarımın iddiası "üç bandı
        eşitledim" DEĞİL, "hangi bandın niye uygulandığı yanıtta yazıyor".
        """
        kati = client.post('/calculate_solid',
                           json=dict(self.KATI, chamber_pressure=7.0))
        sivi = client.post('/calculate_liquid',
                           json=dict(self.SIVI, chamber_pressure=7.0))
        assert kati.status_code == 200
        assert sivi.status_code == 400
        kayit = (sivi.get_json() or {})['invalid_fields'][0]
        assert kayit['accepted_range'] == [10, 500]
        assert kayit['motor_form'] == 'liquid'


# ===========================================================================
# P16B1-39 — TÜRETİLEN BÜYÜKLÜĞE KAPI YOK
# ===========================================================================
class TestTuretilenBuyukluk:
    """``I = F · t_b`` çözümünün ürettiği sayı hiçbir bandı görmüyordu.

    ÖLÇÜLDÜ (once_bomba_repro.json): ``total_impulse = 1e9`` + ``thrust =
    1000`` -> HTTP 200 ve ``burn_time = 1.000.000,0 s`` (11,6 GÜN).
    Kullanıcının gönderdiği 10 s atılıyor, yerine geçen sayı ise
    ``burn_time``in kendi [0,1; 300] s bandına HİÇ sorulmuyordu.

    NOT — DEFTER İDDİASI KISMEN ÇÜRÜTÜLDÜ: "20+ dakika CPU" bugün
    üretilemedi (1e9 ile 5,9 s ölçüldü; motor 200.000 adımlık integrasyon
    sınırı taşıyor). Kalem bir SÜRE kalemi değil, HÜKÜM kalemidir.
    """

    def test_turetilen_yanma_suresi_bandina_sorulyor(self, client):
        r = client.post('/calculate', json=dict(HIBRIT, total_impulse=1e9))
        assert r.status_code == 400, (
            'türetilen 1e6 s yanma süresiyle "başarılı" motor yayımlandı '
            '(HTTP %s)' % r.status_code)
        kayit = (r.get_json() or {})['invalid_fields'][0]
        assert kayit['field'] == 'burn_time'
        assert kayit['reason'] == 'derived_value_out_of_range'
        assert kayit['derived_from'] == ['total_impulse', 'thrust'], kayit
        assert kayit['accepted_range'] == [0.1, 300]

    def test_turetilen_itki_bandina_sorulyor(self):
        """Denklemin öteki dalı: ``total_impulse`` + ``burn_time`` -> F.

        ÖLÇÜLDÜ: bu dal ``/calculate`` UCUNDAN erişilemez — ``thrust`` o
        uçta ZORUNLU alandır (``_get_required_parameters``), yani itki
        gelmediğinde istek zaten "Missing required parameter: thrust" ile
        400 alır ve türetme hiç yapılmaz. Bu yüzden dal kapının KENDİSİNDE
        sınanır: uç sözleşmesi bir gün gevşerse (itki isteğe bağlı olursa)
        kapı hazır durur ve bu bekçi o günü yakalar.
        """
        from hrma.app import _turetilen_buyukluk_ihlali
        kayit = _turetilen_buyukluk_ihlali(
            {'total_impulse': 1e9, 'burn_time': 10})
        assert kayit is not None, 'türetilen itki hiçbir banda sorulmuyor'
        assert kayit['field'] == 'thrust'
        assert kayit['derived_from'] == ['total_impulse', 'burn_time']
        assert kayit['value'] == pytest.approx(1e8)
        assert kayit['accepted_range'] == [10, 1000000]

    def test_uc_itkiyi_zorunlu_tuttugu_icin_o_dal_ucta_kapali(self, client):
        """Ölçümün ikinci yarısı: uçta gerçekten ne oluyor (dürüstlük)."""
        govde = {k: v for k, v in HIBRIT.items() if k != 'thrust'}
        r = client.post('/calculate', json=dict(govde, total_impulse=1e9))
        assert r.status_code == 400
        assert any(k.get('reason') == 'missing_required'
                   and k.get('field') == 'thrust'
                   for k in (r.get_json() or {}).get('invalid_fields', []))

    def test_bant_ici_turetme_dokunulmadan_geciyor(self, client):
        """10.000 N·s / 1000 N = 10 s — banda uyar, hesap koşmalı."""
        r = client.post('/calculate', json=dict(HIBRIT, total_impulse=10000.0))
        assert r.status_code == 200, r.get_data(as_text=True)[:300]

    def test_yeni_esik_icat_edilmedi(self):
        """Türetilene uygulanan bant, alanın KENDİ bandıyla aynı olmalı."""
        from hrma.app import _turetilen_buyukluk_ihlali
        kayit = _turetilen_buyukluk_ihlali(
            {'total_impulse': 1e9, 'thrust': 1000})
        assert kayit['accepted_range'] == [
            motor_validator.limits['burn_time']['min'],
            motor_validator.limits['burn_time']['max']]

    def test_impuls_yoksa_kapi_hic_calismiyor(self):
        """``total_impulse`` gelmediyse türetme de yok, kapı da yok."""
        from hrma.app import _turetilen_buyukluk_ihlali
        assert _turetilen_buyukluk_ihlali(
            {'thrust': 1000, 'burn_time': 10}) is None


# ===========================================================================
# P16B1-52 — İNİŞ İNTEGRASYONU HESAP BOMBASI
# ===========================================================================
class TestHesapBombasi:
    """``parachute_area = 1e9`` isteği bitmiyordu.

    ÖLÇÜLDÜ (once_bomba_repro.json): ``/calculate`` + ``parachute_area=1e9``
    180 s bütçesini AŞTI ve süreç öldürüldü (aynı istek alansız 2,4 s).
    Alan yalnız bu yolda taşınıyor: ``/api/trajectory-analysis`` (0,07 s) ve
    ``/api/six-dof-analysis`` (0,09 s) anahtarı hiç okumuyor.

    Bekçi bütçeyi küçültüp GERÇEK bomba gövdesiyle koşar: mekanizmanın
    ateşlendiğini, adlandırılmış hata döndüğünü ve YARIM yörünge
    yayımlanmadığını sınar (60 s'lik gerçek bütçeyi süitte beklemeden).
    """

    def test_butce_dolunca_adli_hata_doner_ve_yarim_yorunge_yayimlanmaz(
            self, client, monkeypatch):
        import hrma.app as uygulama
        monkeypatch.setattr(uygulama, '_CALCULATE_TRAJECTORY_BUDGET_S', 2.0)
        r = client.post('/calculate', json=dict(HIBRIT, parachute_area=1e9))
        assert r.status_code == 200, (
            'motor sonucu da kayboldu — bütçe kapısı fazla geniş kesiyor')
        govde = r.get_json() or {}
        yorunge = govde.get('trajectory') or {}
        assert yorunge.get('error') == 'trajectory_time_budget_exceeded', (
            'bütçe aşımı ADIYLA bildirilmiyor: %s'
            % json.dumps(yorunge, default=str)[:300])
        assert yorunge.get('budget_s') == 2.0
        # Yarım integrasyondan güvenlik sayısı yayımlanmamalı.
        assert 'landing_velocity' not in json.dumps(yorunge, default=str)

    def test_saglikli_parasut_hala_gercek_yorunge_uretiyor(self, client):
        """Bütçe kapısı meşru koşuyu kesmemeli (9 m² tipik bir paraşüt)."""
        r = client.post('/calculate', json=dict(HIBRIT, parachute_area=9.0))
        assert r.status_code == 200
        yorunge = (r.get_json() or {}).get('trajectory') or {}
        assert yorunge.get('error') is None, yorunge

    def test_butce_kardes_uctan_geliyor(self):
        """Yeni eşik icat edilmedi: altı-serbestlik uçunun ölçülmüş bütçesi."""
        from hrma.app import (_CALCULATE_TRAJECTORY_BUDGET_S,
                              _SIXDOF_WALL_CLOCK_BUDGET_S)
        assert _CALCULATE_TRAJECTORY_BUDGET_S == _SIXDOF_WALL_CLOCK_BUDGET_S


# ===========================================================================
# EK MADDE (Berke, 28 Ağustos) — TERSİNE ÇEVRİLDİ (Berke, 23 Eylül): SÖKÜLDÜ
# ===========================================================================
class TestSokulenSayfalar:
    """``simple.html`` ve ``uzaytek.html`` 28 Ağustos'ta rota kazanmıştı
    ("Rota eklensin"); 23 Eylül'de Berke iki sayfanın TAMAMEN sökülmesine
    karar verdi ("he sil onları yav tamamen yok et", B1 kararları 2 ve 6).
    Eski bekçi "sayfa servis ediliyor" diyordu; artık tersini kilitler.
    Geniş söküm bekçisi: ``tests/test_d36_sokum_a1.py``.
    """

    @pytest.mark.parametrize('yol', ['/simple', '/uzaytek'])
    def test_sayfa_artik_servis_edilmiyor(self, client, yol):
        r = client.get(yol)
        assert r.status_code == 404, (
            f'{yol} yeniden servis ediliyor (HTTP {r.status_code}) — sayfa '
            '23 Eylül 2026\'da söküldü (dalga36/sokum)')

    # test_sayfa_canli_hesap_motoruna_bagli (2 düğüm) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum
    # test_sablonlar_baglam_degiskeni_istemiyor (1 düğüm) emekli — sayfa sökümü: Berke 23 Eyl, dalga36/sokum


# ===========================================================================
# GERİLEME KAPISI — geçerli gövde davranışı
# ===========================================================================
class TestGerileme:

    def test_saglikli_hibrit_govde_gecerli(self):
        ok, mesajlar = motor_validator.validate_motor_data(HIBRIT, 'hybrid')
        assert ok is True and not mesajlar, mesajlar

    def test_eski_sozlesme_korundu(self):
        """``validate_motor_data`` hâlâ 2'li demet döner (çağıranlar)."""
        sonuc = motor_validator.validate_motor_data(HIBRIT, 'hybrid')
        assert isinstance(sonuc, tuple) and len(sonuc) == 2

    def test_ayrintili_surum_ayni_hukmu_veriyor(self):
        ok1, m1 = motor_validator.validate_motor_data(HIBRIT, 'hybrid')
        ok2, m2, kayitlar = motor_validator.validate_motor_data_detailed(
            HIBRIT, 'hybrid')
        assert (ok1, m1) == (ok2, m2)
        assert kayitlar == []

    def test_bool_kapisi_bu_turda_degistirilmedi(self):
        """Tip reddi ``input_guard``ın işidir; bant kapısı bool'a dokunmadı.

        (``tests/test_v262_release_gate.py`` bunu ayrıca ölçüyor; buradaki
        ikiz, S3'ün o bekçiyi kırmadığını dosya içinde de sabitler.)
        """
        ok, mesajlar = motor_validator.validate_motor_data(
            dict(HIBRIT, burn_time=True), 'hybrid')
        assert ok is True and not mesajlar

    def test_takma_ad_tablosu_kanonik_tabloyla_tutarli(self):
        """Her takma ad, gerçekten var olan bir banda çözülmeli."""
        for urun_ad, kayit in FIELD_ALIASES.items():
            assert kayit['kanonik'] in motor_validator.limits, urun_ad
            assert kayit['carpanlar'] and all(
                isinstance(c, float) and c > 0 for c in kayit['carpanlar'])
            assert urun_ad not in motor_validator.limits, (
                f'{urun_ad} hem kanonik hem takma ad — çift denetim')

    def test_form_tablosu_bantlari_sonlu_ve_sirali(self):
        for form, alanlar in FORM_LIMITS.items():
            for alan, (alt, ust, _birim) in alanlar.items():
                assert math.isfinite(alt) and math.isfinite(ust), (form, alan)
                assert alt < ust, (form, alan)
