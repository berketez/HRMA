# -*- coding: utf-8 -*-
"""ÖH D25 / app-api aşama-1 bekçileri — P16B1-49 (kök neden kalemi).

Kalemin başlığı: *deponun ÖRNEK kapısı ``input_guard.num``
``/calculate``in 83 alanından 3'üne bağlı*.

Bu tur oranı DAVRANIŞSAL ölçtü (statik AST taraması yanıltıcıydı: D24'ün
"11 alan korunuyor" sayısı, ``input_guard`` çağrılarını ``app.py``nin
TAMAMINDA aradığı için ``/calculate`` dışındaki uçların kapılarını da
sayıyordu — ör. ``contraction_ratio`` kapısı yalnız
``/api/quick-geometry``te var, ``/calculate`` onu ``data.get(..., 0)`` ile
ham okuyor).

Ölçüm (``docs/scofield/raw/OH/D25/app-api/a1/once_A.json``, taban
``cdf2106``): hibrit sayfasının gerçekten gönderdiği **28** sayısal alan
beş sarsımla (NaN / ±Infinity / ``true`` / liste / çevrilemeyen dize)
sondalandı; **140 hücrenin 31'i HTTP 200** döndü. Yayımlanan gövdede NaN
yaprağı YOKTU — kullanıcı sonlu ve sağlıklı GÖRÜNEN tam bir motor
tasarımı alıyordu, girdinin okunamadığına dair tek satır beyan yoktu.

Onarımdan sonra (``sonra_A.json``): açık hücre **31 -> 5**; kalan beşi
``wall_thickness``tir ve KUSUR DEĞİLDİR (bkz.
:class:`TestP16B149KasaCidariKapsamDisi`).

Bekçinin iki yönü vardır: kapının KAPANDIĞINI ve sağlıklı envanterin
DARALMADIĞINI (ÖK-22) birlikte kilitler.
"""
import math

import pytest

from hrma.app import app, _CALCULATE_TIP_KAPISI_ALANLARI


@pytest.fixture()
def istemci():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


#: Hibrit sayfasının (``templates/advanced.html::getFormData``) gövdesiyle
#: aynı taban. Tek kaynak ``tests/test_field_wiring_layer_b.HYBRID_BASE``
#: olduğu için oradan okunur — iki yerde iki farklı taban olmasın.
def _taban():
    from tests.test_field_wiring_layer_b import HYBRID_BASE
    govde = dict(HYBRID_BASE)
    govde['include_plots'] = False
    return govde


#: Ölçümdeki beş sarsım.
SARSIMLAR = [
    ('nan', float('nan')),
    ('inf', float('inf')),
    ('bool', True),
    ('liste', [1, 2]),
    ('dize', 'abc'),
]

#: Ölçülen açık hücrelerin sağlıklı (ürünün kendi varsayılanı olan)
#: karşılıkları — ÖK-22 karşı-testi için.
SAGLIKLI_DEGERLER = {
    'oxidizer_density': 1220,
    'oxidizer_viscosity': 0.0002,
    'target_velocity': 30,
    'hole_diameter_min': 0.3,
    'hole_diameter_max': 2.0,
    'plate_thickness': 3.0,
    'contraction_ratio': 0,
    'mass_flux_chamber': 0,
    'pressure_drop': 5.0,
    'initial_port_diameter': 0.05,
}


def _adli_mi(govde, alan):
    """Yanıt reddi ADIYLA mı yapıyor? (``invalid_fields[].field``)"""
    if not isinstance(govde, dict):
        return False
    for kayit in (govde.get('invalid_fields') or []):
        if isinstance(kayit, dict) and kayit.get('field') == alan:
            return True
    return False


class TestP16B149TipSonlulukKapisi:
    """ÖLÇÜLDÜ (once_A.json): on alanın NaN / ±Inf / ``true`` sarsımları
    HTTP 200 + 33.3 bin sayısal yapraklı TAM tasarım döndürüyordu.
    """

    @pytest.mark.parametrize('alan', list(_CALCULATE_TIP_KAPISI_ALANLARI))
    @pytest.mark.parametrize('etiket,deger', SARSIMLAR)
    def test_okunamayan_girdi_adiyla_reddedilir(self, istemci, alan,
                                                etiket, deger):
        govde = _taban()
        govde[alan] = deger
        y = istemci.post('/calculate', json=govde)
        assert y.status_code in (400, 422), (
            f'{alan} / {etiket}: okunamayan girdi için HTTP '
            f'{y.status_code} — hüküm yayımlanmamalıydı')
        j = y.get_json()
        assert _adli_mi(j, alan), (
            f'{alan} / {etiket}: red ADSIZ — invalid_fields içinde alan yok')

    @pytest.mark.parametrize('alan,deger', sorted(SAGLIKLI_DEGERLER.items()))
    def test_saglikli_deger_reddedilmez(self, istemci, alan, deger):
        """ÖK-22 — kapı sağlıklı envanteri DARALTMAZ."""
        govde = _taban()
        govde[alan] = deger
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 200, (
            f'{alan} = {deger} ürünün kendi varsayılanıdır; '
            f'HTTP {y.status_code} alındı')

    def test_alan_gonderilmezse_yol_degismez(self, istemci):
        """Kapı yalnız GÖNDERİLMİŞ değeri denetler."""
        govde = _taban()
        for alan in _CALCULATE_TIP_KAPISI_ALANLARI:
            govde.pop(alan, None)
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 200

    def test_bos_dize_verilmedi_sayilir(self, istemci):
        """``''`` "verilmedi" demektir (deponun ``input_guard`` ilkesi);
        ``0`` ile ASLA karıştırılmaz — bu yüzden ``''`` reddedilmez."""
        govde = _taban()
        govde['target_velocity'] = ''
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 200

    def test_sifir_verilmedi_sayilmaz(self, istemci):
        """``0`` geçerli bir değerdir ve varsayılana DÜŞMEZ; kapı onu
        reddetmediği gibi "yok" da saymaz."""
        govde = _taban()
        govde['contraction_ratio'] = 0
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 200

    def test_sayi_benzeri_dize_gecer(self, istemci):
        """``"1220"`` çözülebilir bir sayıdır; kapı tip adına onu
        reddetmez (kayıtlı proje / API çağrısı sayıyı metin taşıyabilir)."""
        govde = _taban()
        govde['oxidizer_density'] = '1220'
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 200

    def test_kapi_yeni_esik_getirmez(self):
        """Doktrin 4 — kapı ``lo``/``hi`` ALMAZ; bant nerede tanımlıysa
        orada kalır. Yardımcının gövdesinde sayısal sınır olmamalı."""
        import inspect
        from hrma import app as app_modulu
        kaynak = inspect.getsource(app_modulu._calculate_tip_kapisi)
        assert 'lo=' not in kaynak and 'hi=' not in kaynak


class TestP16B149CdMantiksalDelik:
    """``discharge_coefficient`` kapısının TEK açık hücresi ``true``ydu:
    ``float(True) == 1,0`` ve 1,0 ``USER_CD_RANGE``in üst ucudur, yani
    bandın İÇİNE düşüyordu (ölçüldü: HTTP 200 + 33.385 yaprak).
    """

    def test_mantiksal_deger_cd_yerine_gecemez(self, istemci):
        govde = _taban()
        govde['discharge_coefficient'] = True
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 422
        assert _adli_mi(y.get_json(), 'discharge_coefficient')

    def test_false_da_reddedilir(self, istemci):
        govde = _taban()
        govde['discharge_coefficient'] = False
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 422

    def test_bandin_ust_ucu_sayi_olarak_gecerlidir(self, istemci):
        """ÖK-22 — reddedilen ``true``dur, 1,0 SAYISI değil."""
        from hrma.engines.injector_design import USER_CD_RANGE
        govde = _taban()
        govde['discharge_coefficient'] = float(USER_CD_RANGE[1])
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 200


class TestP16B149KasaCidariKapsamDisi:
    """``wall_thickness``in beş hücresi de 200'dür ve bu KUSUR DEĞİLDİR.

    ``_withhold_unearned_vessel_verdict`` hükmü ADIYLA geri çeker
    (ölçüldü: 33.386 -> 32.657 yaprak, 729 yaprak yayımlanmıyor). ÖH
    D24'te P16B2-06 tam bu yüzden ÇÜRÜTÜLDÜ. Bu bekçi, D25 kapısının o
    kazanılmış davranışı DEĞİŞTİRMEDİĞİNİ kilitler (ÖK-22).
    """

    @pytest.mark.parametrize('deger', [float('nan'), float('inf'), True,
                                       [1, 2], 'abc'])
    def test_cidar_hukmu_geri_cekilir_ama_istek_reddedilmez(self, istemci,
                                                            deger):
        govde = _taban()
        govde['wall_thickness'] = deger
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 200
        assert 'wall_thickness' not in _CALCULATE_TIP_KAPISI_ALANLARI


class TestP16B149BantBirimSondasi:
    """BANT ULAŞILABİLİRLİĞİ — kalemin ikinci ayağı ölçüldü.

    Kalem "``motor_validation.limits`` 14 aralığın 9'u yanlış alan
    adında" diyordu. BUGÜN ÖLÇÜLDÜ (``once_BC.json``): 14 bandın TAMAMI
    kendi kanonik adıyla ULAŞILIYOR — statik AST taraması yanıltmıştı
    (``chamber_pressure`` ``data['chamber_pressure']`` ile okunduğu için
    ``data.get`` taramasına düşmüyordu; ``_bant_sorunlari`` ise gövdenin
    TÜM anahtarlarını gezer).

    Kalan kusur AD değil BİRİMdir ve bu bekçi onu ÖLÇÜM olarak kilitler:
    beş geometri bandı METRE cinsindendir, ürünün her yüzeyi ise aynı
    adları MİLİMETRE ile gönderir. Onarımı bu aşamada AÇILMADI (rapor
    §4); bekçi bugünkü davranışı kayda geçirir ki sessizce değişmesin.
    """

    #: (alan, ürünün kendi meşru varsayılanı [mm], kaynağı)
    MM_ALANLARI = [
        ('chamber_diameter', 100, 'solid.html:982 value=100'),
        ('throat_diameter', 50, 'liquid.html:1314 value=50'),
        ('exit_diameter', 35, 'solid.html:1149 value=35'),
        ('grain_length', 500, 'solid.html:735 value=500'),
        ('web_thickness', 35, 'solid.html:688 value=35'),
    ]

    @pytest.mark.parametrize('alan,deger,kaynak', MM_ALANLARI)
    def test_metre_bandi_urunun_milimetresini_reddediyor(self, istemci, alan,
                                                         deger, kaynak):
        from hrma.validation.motor_validation import MotorDataValidator
        limit = MotorDataValidator().limits[alan]
        assert limit['unit'] == 'm', (
            f'{alan} bandının birimi değişmiş: {limit["unit"]}')
        govde = _taban()
        govde[alan] = deger
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 400, (
            f'{alan} = {deger} ({kaynak}) bugün 400 alıyor; davranış '
            f'değiştiyse bant birimi kararı verilmiş demektir — kalemi '
            f'güncelle')
        assert _adli_mi(y.get_json(), alan)

    @pytest.mark.parametrize('alan,deger,kaynak', MM_ALANLARI)
    def test_metre_bandi_milimetre_olcegindeki_sacmaligi_geciriyor(
            self, istemci, alan, deger, kaynak):
        """Kusurun ÖTEKİ yönü: aynı 1000 kat kayma bandı ALTTAN da
        gevşetir. ``throat_diameter = 0,5`` kullanıcı için 0,5 mm'dir
        (bu motor sınıfı için saçma) ama bant onu 0,5 m okur ve geçirir.

        ÖH D26 / OH-D25-19 — BEKÇİ ÇEVRİLDİ (kusuru koruyordu).
        Bu bekçi "bant içi değer 200 alıyor"u KAYIT olarak kilitliyordu;
        oysa 200'ün kendisi kusurun bir parçasıydı: ÖLÇÜLDÜ (taban
        ``7751531``, ``docs/scofield/raw/OH/D26/app-api/a1/once.json`` K1)
        ``chamber_diameter`` bant İÇİNDE gönderildiğinde çözücüye HİÇ
        ulaşmıyor, yanıt alanı hiç göndermeyen gövdeyle bit-aynı kalıyor
        ve tek bir beyan yaprağı bile yazılmıyordu. Artık ürünün gerçekten
        okuduğu bir kardeş adı OLAN alanlar (``CANONICAL_TO_PRODUCT_FIELD``,
        ``FIELD_ALIASES``ten türetilir) 422 ile ADIYLA reddediliyor.

        Kalan alanlarda ölçüm DEĞİŞMEDİ: onların gösterilecek bir ürün adı
        yok, hâlâ 200 alıyorlar ve hâlâ okunmuyorlar (K6). Beklenti tek
        kaynaktan türetilir ki o alanlar kapandığında bekçi sessizce
        bayatlamasın.
        """
        from hrma.validation.motor_validation import (
            CANONICAL_TO_PRODUCT_FIELD, MotorDataValidator)
        limit = MotorDataValidator().limits[alan]
        mm_olcegi = 0.5 * (limit['min'] + limit['max'])
        govde = _taban()
        govde[alan] = mm_olcegi
        y = istemci.post('/calculate', json=govde)
        if alan in CANONICAL_TO_PRODUCT_FIELD:
            assert y.status_code == 422, (
                f'{alan} okunmayan kanonik ad kapısından geçti '
                f'(HTTP {y.status_code})')
            j = y.get_json() or {}
            assert j.get('error') == 'unread_canonical_field'
            assert _adli_mi(j, alan)
        else:
            assert y.status_code == 200, (
                f'{alan} = {mm_olcegi} (kullanıcının birimiyle {mm_olcegi} '
                f'mm) bugün geçiyor')

    def test_ondort_bandin_hepsi_kanonik_adiyla_ulasilabilir(self, istemci):
        """Kalemin "9'u yanlış alan adında" iddiası ölçümle çürütüldü."""
        from hrma.validation.motor_validation import MotorDataValidator
        dogrulayici = MotorDataValidator()
        for alan, limit in dogrulayici.limits.items():
            govde = _taban()
            govde[alan] = 1e9
            y = istemci.post('/calculate', json=govde)
            assert y.status_code == 400, f'{alan}: 1e9 geçti'
            assert _adli_mi(y.get_json(), alan), f'{alan}: red adsız'


class TestP16B149TuretilenBuyuklukAyagi:
    """Kalemin "+2 hesap bombası" ayağının BİRİNCİSİ (``total_impulse``)
    önceki dalgada kapanmıştı; bu bekçi geri dönüşü engeller.
    ÖLÇÜLDÜ (once_BC.json C): ``total_impulse = 1e9`` -> HTTP 400,
    0,0 sn (kalemin iddia ettiği 15-20 dakikalık CPU YOK).
    """

    def test_toplam_itki_bombasi_kapali(self, istemci):
        govde = _taban()
        govde['total_impulse'] = 1e9
        y = istemci.post('/calculate', json=govde)
        assert y.status_code == 400
        assert _adli_mi(y.get_json(), 'burn_time') or \
            _adli_mi(y.get_json(), 'total_impulse')
