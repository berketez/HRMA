"""ÖH D29 · kulvar app-api-dogrulama · aşama 2/2 bekçisi.

Tek kalem: **P16B1-44** — ``ambient_temp`` 14 sarsımın 14'ünde HTTP 200
(kapı yok); aynı sınıfta ``oxidizer_temp`` ve ``pressure_drop``.
Kaynak: ``docs/scofield/raw/P16/B1-rapor.md#P16B1-44``.
Ölçüm: ``docs/scofield/raw/OH/D29/app-api-dogrulama/a2/once.json`` (taban
``4dc63c11``) ⟷ ``sonra.json``; betik ``a2/olcum.py`` (aynı betik).

HÜKÜM ÜÇ AYAKTA AYRIŞTI:

* ``ambient_temp`` — BAŞLIK DOĞRU, ONARILDI. Değer katmanında hiç kapı
  yoktu; motor zarfı (180-340 K) bant dışını sessizce düşürüp
  ``defaults_used``a not yazıyordu. Kabul 14/14 -> 3/14 (kalan üçü
  "verilmedi": ``""``, ``null``, anahtar yok).
* ``pressure_drop`` — BAŞLIK KISMEN DOĞRU, ONARILDI. Tek başına bandı
  YOKTUR (uydurulmadı); iki İLİŞKİ kapısı kondu — negatif ΔP reddi ve
  enjektör girişinin (Pc + ΔP) besleme bandını (kanonik ``tank_pressure``
  üst ucu) aşamaması. Sonlu olmayan değeri ucun kendi ``not_finite``
  kapısı zaten 422 ile reddediyordu; ona DOKUNULMADI.
* ``oxidizer_temp`` — BAŞLIK ÇÜRÜTÜLDÜ, BAŞKA BİR KUSUR ÇIKTI. Kalem
  "negatif / 1e9 / ham NaN değerlerinde 200" diyordu; ölçüm 14 sarsımın
  yalnız 1'inde 200 buldu (anahtar yok = verilmedi) ve 11'i N₂O doymuş
  sıvı zarfıyla ADIYLA reddediyordu. Ama DEĞER katmanı kırıktı: ``null``
  ve ``[1, 2]`` HTTP **500** + ham Python metni veriyordu, ``""`` ve
  ``"293.15"`` ise 400 ile "Unknown format code 'f'" basıyordu.
"""

import contextlib
import io

import pytest

from hrma.constants import AMBIENT_TEMPERATURE_BAND_K
from hrma.validation.motor_validation import (
    CANONICAL_LIMITS, CANONICAL_TO_PRODUCT_FIELD, FIELD_ALIASES,
    motor_validator)

#: Sağlıklı hibrit gövde — bu aşamanın hiçbir onarımı bunu reddetmemeli.
P16B144_HIBRIT = {
    'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
    'chamber_pressure': 20.0, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
}


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _gonder(istemci, **ek):
    yuk = dict(P16B144_HIBRIT)
    yuk.update(ek)
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        return istemci.post('/calculate', json=yuk)


def _alan_kaydi(yanit, alan):
    govde = yanit.get_json() or {}
    for kayit in (govde.get('invalid_fields') or []):
        if kayit.get('field') == alan:
            return kayit
    return None


def _hukum(yuk):
    """Kapı katmanının hükmü — ``/calculate`` 400'ü birebir buradan doğar."""
    return motor_validator.validate_motor_data_detailed(yuk, 'hybrid')


# ===========================================================================
# 1. ambient_temp — BANT KAPISI (başlığın kendisi)
# ===========================================================================
class TestP16B144OrtamSicakligiKapisi:
    """ÖNCE: 14/14 kabul, 0 künye. SONRA: 3/14 kabul, 11 künye."""

    @pytest.mark.parametrize('ad,deger', [
        ('sifir', 0),
        ('eksi_bir', -1),
        ('1e-9', 1e-9),
        ('1e9', 1e9),
        ('ham_nan', float('nan')),
        ('ham_inf', float('inf')),
        ('dize_NaN', 'NaN'),
        ('liste', [1, 2]),
        ('mantiksal', True),
        ('yirmi_kelvin', 20.0),
    ])
    def test_bant_disi_deger_adiyla_reddediliyor(self, ad, deger):
        ok, _mesajlar, kayitlar = _hukum(dict(P16B144_HIBRIT,
                                              ambient_temp=deger))
        assert ok is False, f'{ad}: hâlâ kabul ediliyor'
        benim = [k for k in kayitlar if k.get('field') == 'ambient_temp']
        assert benim, f'{ad}: ret ADSIZ (invalid_fields boş): {kayitlar}'
        # ÖH D32 fix-35d / OH-D31-10 — GEREKÇE KODU KANONU. İzin listesi
        # ``not_a_number``ı taşıyordu; o ad EMEKLİ oldu ve tel biçimi reddi
        # merkezin adını (``input_guard.is_json_number`` ->
        # ``not_a_json_number``) alıyor, bayrak ise kendi adını
        # (``boolean_is_not_a_number``). Liste GEVŞEMEDİ: eskisi de dört
        # adlıydı, yenisi de; yalnız adlar kanona taşındı.
        assert benim[0]['reason'] in (
            'out_of_range', 'not_finite', 'not_a_json_number',
            'boolean_is_not_a_number'), benim[0]
        assert benim[0]['resolved_as'] == 'ambient_temperature', benim[0]

    @pytest.mark.parametrize('deger', [180.0, 233.15, 293.15, 340.0])
    def test_bant_ici_deger_kabul_ediliyor(self, deger):
        ok, _m, kayitlar = _hukum(dict(P16B144_HIBRIT, ambient_temp=deger))
        assert ok is True, (deger, kayitlar)

    @pytest.mark.parametrize('deger', ['', None])
    def test_verilmedi_sozlesmesi_korunuyor(self, deger):
        """``""``/``null`` "verilmedi"dir — alanın KENDİ sözleşmesi.

        ``hybrid_rocket_engine._resolve_ambient_temperature`` ilk satırı:
        ``if value is None or value == '': return None``. Kapı kendi
        kuralını dayatmaz, o sözleşmeyi izler.
        """
        ok, _m, kayitlar = _hukum(dict(P16B144_HIBRIT, ambient_temp=deger))
        assert ok is True, kayitlar

    def test_uc_katmaninda_400_ve_kunye(self, istemci):
        yanit = _gonder(istemci, ambient_temp=1e9)
        assert yanit.status_code == 400, yanit.status_code
        kayit = _alan_kaydi(yanit, 'ambient_temp')
        assert kayit is not None, yanit.get_json()
        assert kayit['accepted_range'] == [180.0, 340.0], kayit
        assert kayit['unit'] == 'K', kayit

    def test_saglikli_govde_hala_200(self, istemci):
        assert _gonder(istemci, ambient_temp=293.15).status_code == 200

    def test_bos_dize_bayragi_yalniz_sozlesmesi_olan_alanda(self):
        """``bos_verilmedi`` bir GENEL gevşetme değildir.

        Bayrağı olmayan alanda ``""`` hâlâ "sayı değil" diye reddedilir;
        aksi hâlde bu onarım, ölçülmemiş bir yüzeyi sessizce gevşetirdi.
        """
        assert FIELD_ALIASES['ambient_temp']['bos_verilmedi'] is True
        for ad in ('chamber_temperature', 'chamber_diameter_input',
                   'chamber_length_override', 'initial_port_diameter'):
            assert FIELD_ALIASES[ad]['bos_verilmedi'] is False, ad
        ok, _m, kayitlar = _hukum(dict(P16B144_HIBRIT, chamber_temperature=''))
        assert ok is False
        # OH-D31-10 (fix-35d): boş dize bir JSON SAYISI değildir; ret adı
        # merkezin adıdır. İddia aynen: bayrağı olmayan alanda ``""``
        # HÂLÂ reddedilir, genel bir gevşetme yoktur.
        assert any(k.get('field') == 'chamber_temperature'
                   and k.get('reason') == 'not_a_json_number'
                   for k in kayitlar)


# ===========================================================================
# 2. TEK KAYNAK — bant iki yerde iki sayı olamaz (Doktrin 4)
# ===========================================================================
class TestP16B144BantTekKaynak:

    def test_kanonik_bant_merkezden_okunuyor(self):
        assert CANONICAL_LIMITS['ambient_temperature'] == {
            'min': AMBIENT_TEMPERATURE_BAND_K[0],
            'max': AMBIENT_TEMPERATURE_BAND_K[1], 'unit': 'K'}

    def test_motor_zarfi_ayni_addan_besleniyor(self):
        """Motorun ``_resolve_ambient_temperature`` gövdesinde artık
        çıplak 180/340 literali YOKTUR (ölçüldü: ``a2/once.json`` K4
        ``float_sabitler = [180.0, 340.0]`` -> ``sonra.json`` ``[]``)."""
        import ast
        import inspect

        from hrma.engines import hybrid_rocket_engine as hre
        kaynak = inspect.getsource(hre.HybridRocketEngine
                                   ._resolve_ambient_temperature)
        agac = ast.parse(kaynak.lstrip())
        sabitler = [n.value for n in ast.walk(agac)
                    if isinstance(n, ast.Constant)
                    and isinstance(n.value, float)]
        assert sabitler == [], (
            'zarf sayısı gövdeye geri yazılmış (iki kaynak): %s' % sabitler)
        assert 'AMBIENT_TEMPERATURE_BAND_K' in kaynak

    def test_motor_zarfi_ile_kapi_ayni_sayiyi_uyguluyor(self):
        """İki taraf da aynı sınırı görüyor mu — DAVRANIŞLA ölç."""
        with contextlib.redirect_stdout(io.StringIO()):
            from hrma.engines.hybrid_rocket_engine import HybridRocketEngine
        motor = HybridRocketEngine.__new__(HybridRocketEngine)
        motor._defaults_used = []
        alt, ust = AMBIENT_TEMPERATURE_BAND_K
        assert motor._resolve_ambient_temperature(alt) == alt
        assert motor._resolve_ambient_temperature(ust) == ust
        assert motor._resolve_ambient_temperature(alt - 1.0) is None
        assert motor._resolve_ambient_temperature(ust + 1.0) is None
        # Beyan dalı SÖKÜLMEDİ — kütüphane kullanımında hâlâ not düşer.
        assert any('ambient_temperature(out_of_range' in str(b)
                   for b in motor._defaults_used), motor._defaults_used

    def test_kanonik_ad_okunmuyorsa_urun_adi_soyleniyor(self, istemci):
        """``ambient_temperature`` kanonik adıyla gelen istek 422 alır ve
        okunan ürün adını (``ambient_temp``) söyler — OH-D25-19 sözleşmesi
        yeni bant girdisinde de işliyor."""
        assert CANONICAL_TO_PRODUCT_FIELD['ambient_temperature'] == (
            'ambient_temp', 'K')
        yanit = _gonder(istemci, ambient_temperature=293.15)
        assert yanit.status_code == 422, yanit.status_code
        kayit = _alan_kaydi(yanit, 'ambient_temperature')
        assert kayit is not None, yanit.get_json()
        assert kayit['use_instead'] == 'ambient_temp', kayit


# ===========================================================================
# 3. pressure_drop — İLİŞKİ KAPISI (sayı uydurulmadı)
# ===========================================================================
class TestP16B144BasincDusumuIliskisi:
    """ÖNCE (``a2/once.json`` K1H): ``-1`` -> 200 (sessizce OTOMATİK dala
    düşüyordu), ``1e9`` -> 200 (enjektör 1e9 bar ΔP ile boyutlandı)."""

    def test_negatif_dusum_reddediliyor(self):
        ok, _m, kayitlar = _hukum(dict(P16B144_HIBRIT, pressure_drop=-1))
        assert ok is False
        kayit = [k for k in kayitlar if k['field'] == 'pressure_drop'][0]
        assert kayit['reason'] == 'negative_pressure_drop', kayit

    def test_sifir_otomatik_sentineli_korunuyor(self):
        """0, ``utils/injector_design``in KENDİ "sen boyutlandır"
        işaretidir; reddedilemez."""
        ok, _m, kayitlar = _hukum(dict(P16B144_HIBRIT, pressure_drop=0))
        assert ok is True, kayitlar

    def test_besleme_tavani_kanondan_okunuyor(self):
        tavan = CANONICAL_LIMITS['tank_pressure']['max']
        pc = P16B144_HIBRIT['chamber_pressure']
        # Tam tavanda kabul, bir bar üstünde ret — sayı bu testte YAZILMAZ.
        ok_sinir, _m, _k = _hukum(dict(P16B144_HIBRIT,
                                       pressure_drop=tavan - pc))
        assert ok_sinir is True
        ok_asan, _m, kayitlar = _hukum(dict(P16B144_HIBRIT,
                                            pressure_drop=tavan - pc + 1))
        assert ok_asan is False
        kayit = [k for k in kayitlar if k['field'] == 'pressure_drop'][0]
        assert kayit['reason'] == 'feed_pressure_exceeded', kayit
        assert kayit['accepted_range'] == [0.0, tavan - pc], kayit
        assert kayit['resolved_as'] == 'tank_pressure', kayit

    def test_oda_basinci_yoksa_iliski_DEGERLENDIRILEMEDI_deniyor(self):
        """Sayı uydurmak yerine söylenir (P12bB1-12 kuralı)."""
        yuk = {k: v for k, v in P16B144_HIBRIT.items()
               if k != 'chamber_pressure'}
        yuk['pressure_drop'] = 1e9
        _ok, _m, kayitlar = _hukum(yuk)
        kayit = [k for k in kayitlar if k['field'] == 'pressure_drop'][0]
        assert kayit['reason'] == 'feed_limit_not_evaluable', kayit

    def test_sonlu_olmayan_deger_MEVCUT_kapida_kaliyor(self, istemci):
        """NaN reddi zaten sağlıklıydı (422 ``not_finite``); bu onarım onu
        400'e KAYDIRMAZ (ÖK-22: sağlıklı envanter gevşetilmez/oynatılmaz)."""
        ok, _m, kayitlar = _hukum(dict(P16B144_HIBRIT,
                                       pressure_drop=float('nan')))
        assert ok is True, 'ilişki kapısı sonlu olmayanı sahiplenmiş'
        assert not [k for k in kayitlar if k['field'] == 'pressure_drop']
        yanit = _gonder(istemci, pressure_drop=float('nan'))
        assert yanit.status_code == 422, yanit.status_code

    def test_uc_katmaninda_400(self, istemci):
        assert _gonder(istemci, pressure_drop=1e9).status_code == 400
        assert _gonder(istemci, pressure_drop=-1).status_code == 400
        assert _gonder(istemci, pressure_drop=4.0).status_code == 200


# ===========================================================================
# 4. oxidizer_temp — BAŞLIK ÇÜRÜTÜLDÜ, DEĞER KATMANI ONARILDI
# ===========================================================================
class TestP16B144OksitleyiciSicakligi:
    """Fizik kapısı ZATEN vardı (N₂O doymuş sıvı zarfı, NIST WebBook);
    kırık olan değer katmanıydı — iki sarsım HTTP 500 veriyordu."""

    #: ÖH D31 fix-34a (14 Eylül 2026) — RET SÖZLEŞMESİ DEĞİŞTİ, İDDİA
    #: KORUNDU. ``''`` ve ``[1, 2]`` artık D30'da inen MERKEZÎ tip kapısına
    #: takılıyor (``hrma/validation/motor_validation.py::_sayisal_kapi``,
    #: ÖH D30 / P12bB1-12 + OH-D29-07, ``NUMERIC_ONLY_FIELDS``) ve ret
    #: N₂O doymuş sıvı katmanına HİÇ ULAŞMIYOR. Ret daha erken ve daha
    #: MAKİNE-OKURDUR: üst düzey ``error`` alanı artık toplu
    #: ``'Validation failed'``, ad ve gerekçe ise ``invalid_fields``
    #: kaydında (``field``/``reason: not_a_number``/``value`` yankısı) ve
    #: ``details`` metninde (``oxidizer_temp must be numeric, got str``)
    #: duruyor. ÖLÇÜLDÜ: ``docs/scofield/raw/OH/D31/fix34/a/
    #: oxtemp_sozlesme.json`` (aynı ölçüm D31 tabanı 9d70e9ed ağacında da
    #: aynı sonucu verdi — yani gerileme değil, D30 sözleşmesi).
    #:
    #: Bekçi bu yüzden ÇEVRİLDİ, gevşetilmedi: "sayı olmayan değer ADIYLA
    #: 400" iddiası aynen duruyor, yalnız adın YAZILI OLDUĞU YER yeni
    #: sözleşmeden okunuyor. ``[1, 2]`` vakasında beklenen ad
    #: ``tank_temperature`` (fizik katmanının çözdüğü ürün alanı) yerine
    #: ``oxidizer_temp`` (kullanıcının GÖNDERDİĞİ alan) oldu; bilgi
    #: kaybı yok, ret artık gönderilen alanı adlandırıyor.
    #:
    #: ÜRÜN GERİLEMESİ DEĞİL — ÖLÇÜLDÜ: canlı yol sayı gönderiyor
    #: (``advanced.html`` ``oxidizer_temp: parseFloat(...) || 293``), yani
    #: tip kapısı kullanıcının gördüğü akışı kapatmıyor. Fizik zarfı kolu
    #: da ölü kalmadı: ``test_fizik_zarfi_hala_adiyla_reddediyor`` 1e9 ile
    #: doymuş sıvı zarfı metnini ayrıca sınıyor.
    #: ÖH D32 fix-35d — ``null`` VAKASI BU SINIFTAN ÇIKTI (çapa kayması,
    #: iddia korundu). ÖLÇÜLDÜ (bu ağaç, fix-35d öncesi taban ``6ccb91eb``
    #: ağacında da aynı): ``oxidizer_temp: null`` artık HTTP **200** alıyor
    #: ve yanıt ``defaults_applied`` künyesini taşıyor; gövde, alanı HİÇ
    #: göndermemekle BİT-AYNI davranıyor. Bu ÖH D32 app-api-uc a1'in
    #: bilinçli kararıdır (ÖK-21 / OH-D31-13: 18 SESSİZ yedek tek kaynağa
    #: taşındı ve her biri adıyla BEYAN edildi). ``null`` deponun her
    #: yerinde "verilmedi"dir (``input_guard``: ``None``/``''`` incelenmez),
    #: yani bu sınıfın konusu olan "SAYI OLMAYAN değer" kümesine hiç ait
    #: değildi. Not-supplied sözleşmesi aşağıda AYRI bekçiyle sınanır
    #: (``test_null_verilmedi_sozlesmesi``), yani kapsam kaybı yok.
    @pytest.mark.parametrize('ad,deger,beklenen_tip', [
        ('bos_dize', '', 'str'),
        ('liste', [1, 2], 'list'),
    ])
    def test_sayi_olmayan_deger_ADIYLA_400(self, istemci, ad, deger,
                                           beklenen_tip):
        yanit = _gonder(istemci, oxidizer_temp=deger)
        assert yanit.status_code == 400, (
            f'{ad}: HTTP {yanit.status_code} (500 = ham Python sızıntısı)')
        govde = yanit.get_json() or {}
        metin = str(govde.get('error', ''))
        ayrinti = ' | '.join(str(x) for x in (govde.get('details') or []))
        if beklenen_tip is None:
            # Ret FİZİK katmanından geliyor: ad ve birim metinde YAZILI.
            assert 'oxidizer_temp' in metin, metin[:200]
            assert 'must be a finite number in kelvin' in metin, metin[:200]
        else:
            # Ret MERKEZÎ tip kapısından geliyor: ad makine-okur kayıtta.
            kayit = _alan_kaydi(yanit, 'oxidizer_temp')
            assert kayit is not None, (ad, govde)
            # OH-D31-10 kanonu (fix-35d): merkezin adı.
            assert kayit['reason'] == 'not_a_json_number', (ad, kayit)
            assert kayit['value'] == str(deger)[:60], (ad, kayit)
            assert (f'oxidizer_temp must be numeric, got {beklenen_tip}'
                    in ayrinti), (ad, ayrinti[:200])
        for sizinti in ('__format__', 'float() argument',
                        'Unknown format code'):
            assert sizinti not in metin + ayrinti, (ad, metin[:200],
                                                    ayrinti[:200])

    def test_null_verilmedi_sozlesmesi(self, istemci):
        """``null`` = "verilmedi" ve bu SESSİZ değil, BEYANLI geçer.

        ÖH D32 fix-35d. Kapsam kaybı olmasın diye ayrı bekçi: ``null``
        gönderen gövde ile alanı HİÇ göndermeyen gövde aynı HTTP sınıfını
        alır, ve yanıt uygulanan yedeği ``defaults_applied`` künyesiyle
        ADIYLA yayımlar (ÖK-21 / OH-D31-13). Sessiz varsayıma dönüş bu
        bekçiyi kırar.
        """
        null_yanit = _gonder(istemci, oxidizer_temp=None)
        yok_yanit = _gonder(istemci)
        assert null_yanit.status_code == yok_yanit.status_code == 200
        govde = null_yanit.get_json() or {}
        assert govde.get('defaults_applied'), (
            'yedek uygulandı ama künyesi yok — sessiz varsayım geri geldi')

    def test_fizik_zarfi_hala_adiyla_reddediyor(self, istemci):
        """ÇÜRÜTME KANITI: kalem "1e9 -> 200" diyordu; ölçüm 400 buldu ve
        bu onarımdan SONRA da 400'dür (gerileme yok)."""
        yanit = _gonder(istemci, oxidizer_temp=1e9)
        assert yanit.status_code == 400, yanit.status_code
        metin = str((yanit.get_json() or {}).get('error', ''))
        assert 'saturated-liquid envelope' in metin or \
            'triple point' in metin, metin[:200]

    def test_saglikli_ve_verilmedi_200(self, istemci):
        assert _gonder(istemci, oxidizer_temp=293.0).status_code == 200
        assert _gonder(istemci).status_code == 200
