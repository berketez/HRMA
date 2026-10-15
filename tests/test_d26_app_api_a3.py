"""ÖH D26 / app-api aşama-3 bekçileri.

Kapsanan kalemler:

* **OH-Z5-02** — ``test_field_wiring_layer_b`` sabit-yaprak listesinin
  app-api sahasındaki 5 yaprağı (dördü künyeli im, biri sınıflandırma
  onarımı); eşik 5 -> 1.
* **OH-D19-08** (ŞART) — ``/calculate`` serileştirme yedeği yardımcıya
  çıktı; DİNAMİK bekçi artık gövdeyi doğrudan ölçüyor.
* **OH-D19-09** (ŞART) — beş kardeş uçta düşüş beyanı + sayı/beyan tek
  çağrıdan.
* **OH-D25-18** — ``/api/oxidizer-properties`` sessiz n2o varsayımı.
* **OH-D25-23** — ret gövdesinde bandın iki adı (ENGELLİ: ölçüm + dondurma).
* **OH-D25-11** — ``expansion_ratio`` bool kapısı (ÇÜRÜTÜLDÜ, kilit).
* **OH-D25-17** — öksüz uç kararı.

Ölçüm: ``docs/scofield/raw/OH/D26/app-api/a3/once.json`` ->
``sonra.json``. Ters-mutasyon: ``.../a3/mutasyon.json``.
"""
import contextlib
import io
import math
import re
import sys
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
APP_KAYNAK = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')
sys.path.insert(0, str(KOK / 'tests'))


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, yol, yuk):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = istemci.post(yol, json=yuk)
    try:
        j = r.get_json()
    except Exception:
        j = None
    return r.status_code, (j if isinstance(j, dict) else {})


HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'fuel_type': 'htpb', 'oxidizer_type': 'n2o',
          'chamber_pressure': 20.0}


# ---------------------------------------------------------------------------
# OH-D19-08 — Fable-D21 ŞART: yedek bloğu yardımcıda + DİNAMİK bekçi
# ---------------------------------------------------------------------------
class TestOHD1908YedekYardimcisi:
    """``_serilestirme_yedegi`` gövdeyi sayı uydurmadan kurar."""

    def test_yardimci_var_ve_uc_onu_cagiriyor(self):
        assert 'def _serilestirme_yedegi(' in APP_KAYNAK
        assert '_yedek_govde, _yedek_kod = _serilestirme_yedegi(' in APP_KAYNAK

    def test_eksik_alan_sifirla_doldurulmaz(self):
        """ŞART (1): yalnız ``thrust`` üretilmişse gövdede yalnız o olur."""
        from hrma.app import _serilestirme_yedegi
        govde, kod = _serilestirme_yedegi({'thrust': 1000.0}, None,
                                          TypeError('x'))
        assert kod == 500
        assert govde['motor'] == {'thrust': 1000.0}
        assert 'chamber_pressure' not in govde['motor']
        assert govde['unavailable_fields'] == [
            'specific_impulse', 'chamber_pressure', 'burn_time']

    def test_sonlu_olmayan_ve_bool_sayi_sayilmaz(self):
        """ŞART (2): inf / True / nan gövdeye SIZMAZ."""
        from hrma.app import _serilestirme_yedegi
        govde, kod = _serilestirme_yedegi(
            {'thrust': float('inf'), 'chamber_pressure': True,
             'burn_time': float('nan')}, None, ValueError('y'))
        assert kod == 500
        for ad in ('thrust', 'chamber_pressure', 'burn_time'):
            assert ad not in govde['motor'], govde['motor']
            assert ad in govde['unavailable_fields']
        assert govde['motor'] == {}

    def test_govde_hicbir_alanda_sifir_yayimlamaz(self):
        """Semantik mutasyonun hedefi: ``_temel_motor[_ad] = 0``."""
        from hrma.app import _serilestirme_yedegi
        govde, _ = _serilestirme_yedegi({}, None, TypeError('z'))
        assert govde['motor'] == {}
        assert 0 not in govde['motor'].values()
        assert govde['status'] == 'error'
        assert govde['error'] == 'result_serialization_failed'

    def test_uretilen_sonlu_sayi_aynen_gecer(self):
        """Sağlıklı yol bit-aynı: gerçekten üretilen sayı taşınır."""
        from hrma.app import _serilestirme_yedegi
        govde, _ = _serilestirme_yedegi(
            {'thrust': 1000.0, 'specific_impulse': 220.0,
             'chamber_pressure': 20.0, 'burn_time': 10.0}, 'CEA metni',
            TypeError('q'))
        assert govde['motor'] == {'thrust': 1000.0, 'specific_impulse': 220.0,
                                  'chamber_pressure': 20.0, 'burn_time': 10.0}
        assert 'unavailable_fields' not in govde
        assert govde['cea_results'] == 'CEA metni'

    def test_uc_seviyesi_serilestirme_coktugunde_500(self, istemci,
                                                     monkeypatch):
        """ŞART (3): uç üzerinden — 500 + motor içinde 0 YOK."""
        import hrma.app as uygulama
        _asil = uygulama.sanitize_json_values
        durum = {'n': 0}

        def _kirilgan(x):
            durum['n'] += 1
            if durum['n'] == 1:
                raise TypeError('serilestirme sinandi')
            return _asil(x)

        monkeypatch.setattr(uygulama, 'sanitize_json_values', _kirilgan)
        kod, govde = _post(istemci, '/calculate', dict(HIBRIT))
        assert kod == 500, govde
        assert govde.get('error') == 'result_serialization_failed'
        for ad, deger in (govde.get('motor') or {}).items():
            assert deger != 0, (ad, deger)
            assert math.isfinite(deger)


# ---------------------------------------------------------------------------
# OH-D19-09 — Fable-D21 ŞART: beş uç + tek çağrı
# ---------------------------------------------------------------------------
#: ŞART'ın istediği beş uç (üçü D21'de zaten vardı, burada dördü + biri).
SART_UCLARI = (
    ('/api/transient-analysis', {'thrust': 1000, 'burn_time': 10,
                                 'of_ratio': 6.0, 'fuel_type': 'htpb',
                                 'oxidizer_type': 'n2o'}),
    ('/api/kinetic-efficiency', {'of_ratio': 6.0,
                                 'characteristic_length': 1.0,
                                 'throat_diameter': 0.03}),
    ('/parametric-analysis', {'param_type': 'of_ratio', 'param_start': 4,
                              'param_end': 8, 'param_steps': 3,
                              'thrust': 1000, 'burn_time': 10,
                              'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}),
)


#: ÖH D32 / arayuz-panel a2 (OH-D31-14) — ``/api/flow-analysis`` BU
#: TUPLE'DAN ÇIKTI. Satır "oda basıncı gönderilmedi -> künyeyle beyan
#: edilir" diyordu; o uçta ``chamber_pressure`` ARTIK DÜŞMÜYOR, alan-alan
#: kapı onu adıyla istiyor (422 ``incomplete_flow_input``). Künye zayıf
#: hükümdü, kapı güçlü hüküm: satır silinmedi, HÜKMÜ SERTLEŞTİ ve aşağıdaki
#: tabloya taşındı. Toplam satır sayısı kilitli (kimse sessizce düşüremez).
FAIL_CLOSED_UCLARI = (
    ('/api/flow-analysis', {'fidelity': 'engineering'}, 'chamber_pressure'),
)

TOPLAM_SART_SATIRI = 4


class TestOHD1909BesUc:
    """Düşüş -> künye var; değer verilince künye YOK."""

    def test_satir_sayisi_kilitli(self):
        """ÖH D32: bir uç tablodan sessizce düşürülemez."""
        assert len(SART_UCLARI) + len(FAIL_CLOSED_UCLARI) == \
            TOPLAM_SART_SATIRI

    @pytest.mark.parametrize('yol,yuk,alan', FAIL_CLOSED_UCLARI)
    def test_dusmeyen_alan_ADIYLA_istenir(self, istemci, yol, yuk, alan):
        """ÖH D32 (OH-D31-14): künye yerine kapı — ve künye kanalı susar."""
        kod, govde = _post(istemci, yol, dict(yuk))
        assert kod == 422, f'{yol}: {alan} uydurularak çözüldü (HTTP {kod})'
        assert alan in (govde.get('missing_fields') or []), govde
        assert govde.get('defaults_applied') is None, govde

    @pytest.mark.parametrize('yol,yuk', SART_UCLARI)
    def test_dusus_adiyla_yayimlanir(self, istemci, yol, yuk):
        kod, govde = _post(istemci, yol, yuk)
        assert kod == 200, f'{yol}: HTTP {kod}'
        kunye = govde.get('defaults_applied')
        assert kunye, f'{yol}: oda basıncı varsayılanda çözüldü, beyan YOK'
        kayit = next(k for k in kunye if k.get('field') == 'chamber_pressure')
        assert kayit.get('unit') == 'bar'
        assert isinstance(kayit.get('value'), (int, float))

    @pytest.mark.parametrize('yol,yuk', SART_UCLARI)
    def test_deger_verilince_kunye_yok(self, istemci, yol, yuk):
        """ÖH D26 a4 (P7B4-05) — DARALTILDI: ölçülen şey BASINÇ künyesinin
        yokluğudur. Geniş hâli, ``/api/flow-analysis``taki sekiz uydurma
        varsayılanın (3000 K · γ 1,2 · MW 24 · D_t 0,02 m · 101.325 Pa ·
        45 · 0,40 · 800 K) SESSİZ kalmasını koruyan bir bekçiye
        dönüşmüştü. Gerekçe: ``a4/rapor.md`` §P7B4-05."""
        _tam = dict(yuk, chamber_pressure=25.0)
        kod, govde = _post(istemci, yol, _tam)
        assert kod == 200, f'{yol}: HTTP {kod}'
        beyan = [k.get('field') for k in (govde.get('defaults_applied') or [])]
        assert 'chamber_pressure' not in beyan, (
            f'{yol}: basınç gönderildiği hâlde künyesi eklendi: {beyan}')
        for ad in beyan:
            assert _tam.get(ad) in (None, ''), (
                f'{yol}: {ad} gönderilmişken varsayılan künyesi basıldı')

    def test_advanced_analysis_ust_seviyede_kunye(self, istemci):
        _yuk = {k: v for k, v in HIBRIT.items() if k != 'chamber_pressure'}
        kod, govde = _post(istemci, '/api/advanced-analysis',
                           {'motor_data': _yuk,
                            'analysis_types': ['combustion']})
        assert kod == 200, govde
        kunye = govde.get('defaults_applied')
        assert kunye and any(k.get('field') == 'chamber_pressure'
                             for k in kunye), govde.keys()
        kod2, govde2 = _post(istemci, '/api/advanced-analysis',
                             {'motor_data': dict(HIBRIT),
                              'analysis_types': ['combustion']})
        assert kod2 == 200
        assert 'defaults_applied' not in govde2

    def test_parametric_basinc_taranirken_kunye_yok(self, istemci):
        """ŞART: ``param_type='chamber_pressure'`` iken düşüş yoktur.

        ÖH D27 / P16S1-02 — İDDİA DARALTILDI, GEVŞETİLMEDİ. Bu bekçi
        ``defaults_applied`` anahtarının HİÇ olmamasını sınıyordu; bu
        yalnız oda basıncı TEK beyan edilen alan olduğu sürece doğru bir
        vekildi. D27'de aynı uç, ``gamma`` / ``l_star`` /
        ``atmospheric_pressure`` gibi ON BİR sessiz yedeğini de beyan
        etmeye başladı (ölçüm: ``a1/once.json`` K4 — önce 6/6 koşumda
        ``defaults_applied = null``), yani liste artık boş değil.
        ŞART'ın söylediği şey ise alan başınadır: "basınç zaten taranıyor,
        ONUN için düşüş beyanı yalan olur". Bekçi tam olarak bunu ölçüyor
        ve KARDEŞ alanların beyanının da gerçekten geldiğini doğruluyor —
        eski hâlinden daha dar bir iddiadır.
        """
        kod, govde = _post(istemci, '/parametric-analysis', {
            'param_type': 'chamber_pressure', 'param_start': 10,
            'param_end': 30, 'param_steps': 3, 'thrust': 1000,
            'burn_time': 10, 'fuel_type': 'htpb', 'oxidizer_type': 'n2o'})
        assert kod == 200, govde
        beyan = {k['field'] for k in govde.get('defaults_applied') or []}
        assert 'chamber_pressure' not in beyan, (
            'basınç zaten taranıyor; "varsayılana düşüldü" beyanı yalan olur')
        assert 'gamma' in beyan, (
            'kardeş yedeklerin beyanı kayboldu — bekçi boş listeyle de '
            'yeşile dönmemeli')

    def test_sayi_ve_beyan_tek_cagridan(self):
        """ŞART ikinci ayak: ayrık okuma sitesi KALMADI."""
        canli = [s for s in APP_KAYNAK.split('\n')
                 if "data.get('chamber_pressure', _CALCULATE_PC_DEFAULT_BAR)"
                 in s and not s.lstrip().startswith('#')]
        assert canli == [], f'ayrık okuma geri geldi: {canli}'
        assert '_pc_qg_basinc = _pc_varsayilan_kunyesi(' in APP_KAYNAK
        assert '_pc_tr_basinc = _pc_varsayilan_kunyesi(' in APP_KAYNAK

    @pytest.mark.parametrize('yol,yuk', SART_UCLARI[:1])
    def test_bos_dize_sayi_ile_beyani_ayirmaz(self, istemci, yol, yuk):
        """``''`` gövdesinde sayı ile beyan AYRIŞAMAZ.

        Eski kodda değer ``data.get('chamber_pressure', 20.0)`` ile,
        beyan ``_pc_varsayilan_kunyesi`` ile okunuyordu: künye üreticisi
        boş dizeyi "gönderilmedi" sayıp düşüşü beyan ederken ``data.get``
        boş dizeyi DEĞER sayıp çözücüye geçiriyordu — iki okuma ayrışıyordu.
        Tek çağrıya indikten sonra ucun kendi tip kapısı boş dizeyi ADIYLA
        reddediyor (fail-closed) ve ayrışacak ikinci okuma KALMIYOR.
        """
        kod, govde = _post(istemci, yol, dict(yuk, chamber_pressure=''))
        assert kod in (400, 422), govde
        alanlar = [k.get('field')
                   for k in govde.get('invalid_fields', [])]
        assert 'chamber_pressure' in alanlar, govde
        # Reddedilen istekten hiçbir sayı sızmaz.
        assert 'defaults_applied' not in govde, (
            'istek reddedildi ama "varsayılana düşüldü" beyanı yayımlandı')


# ---------------------------------------------------------------------------
# OH-D25-18 — /api/oxidizer-properties sessiz n2o
# ---------------------------------------------------------------------------
class TestOHD2518SessizOksitleyici:

    def test_alan_yoksa_sayi_uretilmez(self, istemci):
        kod, govde = _post(istemci, '/api/oxidizer-properties', {})
        assert kod == 422, govde
        assert govde.get('error') == 'oxidizer_type_not_supplied'
        assert [k['field'] for k in govde['invalid_fields']] == [
            'oxidizer_type']
        # Sayı UYDURULMADI.
        assert 'properties' not in govde
        assert govde.get('status') == 'error'

    def test_yalniz_sicaklik_gonderilirse_de_reddedilir(self, istemci):
        kod, govde = _post(istemci, '/api/oxidizer-properties',
                           {'temperature': 300})
        assert kod == 422, govde
        assert govde.get('error') == 'oxidizer_type_not_supplied'

    def test_acik_null_da_gonderilmemis_sayilir(self, istemci):
        kod, govde = _post(istemci, '/api/oxidizer-properties',
                           {'oxidizer_type': None})
        assert kod == 422, govde
        assert govde.get('error') == 'oxidizer_type_not_supplied'

    def test_bos_dize_eski_sozlesmeyle_reddedilir(self, istemci):
        """Kapı DAR: boş dize OH-D17-23 sözleşmesinde kalır.

        ``''`` bir ADDIR (çözülemeyen bir ad) ve o uç zaten HTTP 400 +
        ``error_code`` + ``field`` + ``accepted_values`` veriyor — daha
        zengin bir fail-closed gövde. Yeni kapı onu YUTMAZ.
        """
        kod, govde = _post(istemci, '/api/oxidizer-properties',
                           {'oxidizer_type': ''})
        assert kod == 400, govde
        assert govde.get('field') == 'oxidizer_type'
        assert govde.get('accepted_values')

    def test_saglikli_istek_bit_ayni_kalir(self, istemci):
        """Çapa: adı gönderen istek DEĞİŞMEDİ."""
        kod, govde = _post(istemci, '/api/oxidizer-properties',
                           {'oxidizer_type': 'n2o', 'temperature': 293.15})
        assert kod == 200, govde
        assert govde.get('status') == 'success'


# ---------------------------------------------------------------------------
# OH-D25-23 — bandın TEK adı
# ---------------------------------------------------------------------------
class TestOHD2523IkiAdOlculdu:
    """OH-D25-23 — **BU SINIF ÇEVRİLDİ** (ÖH D27 a2'de kalem KAPANDI).

    D26'daki hâli ``TestOHD2523IkiAdOlculdu`` adıyla kusuru DONDURUYORDU:
    ``assert 'allowed_range' in problems[0]``, ``_canli('allowed_range')
    == 4``, ``'OH-D25-23 · ENGELLİ (kardeş dal)' in APP_KAYNAK``. O hâl
    onarım değil ÖLÇÜMDÜ ve kendi gerekçesinde şunu yazıyordu: *"kapanırsa
    bu bekçi kırmızı olur ve kalem aynı commit'te güncellenmek zorunda
    kalır."* Kalem D27 a2'de kapandı, bu yüzden bekçi aynı commit'te
    çevrildi — Doktrin 3 (kusuru koruyan bekçi ÖNCE çevrilir).

    D26'nın engeli ölçülmüş bir kardeş-dal engeliydi: paylaşımlı kapının
    çıktısı ``_ust_sinir_ihlalleri`` üzerinden
    ``/api/regression-analysis``e de gidiyor ve
    ``tests/test_d16_yapisal_sistem_a1.py:101`` adı SABİT okuyordu
    (``KeyError: 'allowed_range'``); o dosyaya D26'da ``hibrit`` kardeş
    dalı dokunuyordu. D27'de hibrit ana ağaca birleşti ve 11 D27 kardeş
    dalının hiçbiri ne o dosyaya ne bu satırlara dokunuyor (ölçüldü:
    ``docs/scofield/raw/OH/D27/app-api/a2/kardes_dal.json``).

    Sınıfın İŞİ AYNI KALDI, yönü döndü: eskiden "ayrışma hâlâ ayakta"
    diyordu, şimdi "ayrışma kapandı ve GERİ GELEMEZ" diyor. Ad üçe
    çıkamaz, ikiye de dönemez.
    """

    def test_paylasimli_kapi_KANON_adi_yayimlar(self):
        from hrma.app import _collect_unphysical_fields
        problems = _collect_unphysical_fields({'a': 7.0},
                                              ranges={'a': (0.0, 5.0)})
        assert problems[0]['reason'] == 'out_of_range'
        assert problems[0]['accepted_range'] == [0.0, 5.0]
        assert 'allowed_range' not in problems[0], (
            'eski ad geri geldi — OH-D25-23 yeniden açıldı')

    def test_eski_adin_CANLI_uretici_sayisi_sifir(self):
        """Sayım YASTIKSIZ ve YALNIZ CANLI KOD üstünde (D26 deseninin

        aynısı): açıklama satırları sayılmaz — kapanış notu eski adı
        tarihsel ölçüm olarak yorumda taşıyor."""
        def _canli(ad):
            return len([r for r in APP_KAYNAK.split('\n')
                        if "'%s'" % ad in r and not r.lstrip().startswith('#')])
        # D26 ölçümü: allowed_range 4, allowed_range_m 1, accepted_range 17.
        assert _canli('allowed_range') == 0, (
            'eski bant adı canlı koda geri döndü; ayrışma yeniden açıldı')
        assert _canli('allowed_range_m') == 0, (
            'eski adın ``_m`` birim kardeşi canlı koda geri döndü')
        assert _canli('accepted_range') >= 21, (
            'kanonik ad kayboldu ya da azaldı — 17 eski + 4 devralınan '
            'site en az 21 eder')

    def test_alti_dof_ile_kardesi_ARTIK_ayni_adi_kullaniyor(self, istemci):
        """Kapanışın ÜRÜN yüzündeki kanıtı: iki uç, tek ad."""
        kod, govde = _post(istemci, '/api/six-dof-analysis',
                           {'mass': 10, 'thrust': 1000, 'burn_time': 10,
                            'cd0': 1e9})
        assert kod == 422, govde
        kayit = [k for k in govde.get('invalid_fields', [])
                 if k.get('field') == 'cd0']
        assert kayit, govde
        assert 'accepted_range' in kayit[0], (
            '6-DOF reddi kanonik bandı yayımlamıyor: %r' % (kayit[0],))
        assert 'allowed_range' not in kayit[0]

        # Kardeş uç (``/calculate``, hibrit) AYNI adı kullanmalı — kalemin
        # tam metni bu iki ucun ayrışmasıydı.
        kod2, govde2 = _post(istemci, '/calculate',
                             dict(HIBRIT, burn_time=1e9))
        kardes = [k for k in (govde2.get('invalid_fields') or [])
                  if isinstance(k, dict) and k.get('field') == 'burn_time']
        assert kardes, govde2
        assert 'accepted_range' in kardes[0], kardes[0]
        assert (set(k for k in kayit[0] if 'range' in k)
                == set(k for k in kardes[0] if 'range' in k
                       and not k.endswith(('_text', '_exclusive',
                                           '_source')))), (
            'iki uç aynı kavramı hâlâ farklı adla yayımlıyor: %r vs %r'
            % (sorted(kayit[0]), sorted(kardes[0])))

    def test_kapanis_kaynakta_adiyla_yazili(self):
        """Kapanış gerekçesi koda yazıldı (engel notunun yerine)."""
        assert 'OH-D25-23 · KAPANDI' in APP_KAYNAK
        assert 'OH-D25-23 · ENGELLİ (kardeş dal)' not in APP_KAYNAK


# ---------------------------------------------------------------------------
# OH-D25-11 — expansion_ratio bool (ÇÜRÜTÜLDÜ; kapı KİLİTLENİR)
# ---------------------------------------------------------------------------
class TestOHD2511BoolKapisi:
    """Kalemin başlığı ("true -> 1,0, false -> 0 aşağıya iniyor") bugünün
    tabanında ÖLÇÜMLE ÇÜRÜTÜLDÜ (``a3/once.json`` K5): ikisi de HTTP 400 +
    ``invalid_fields=['expansion_ratio']``. Bekçi kapıyı KİLİTLER."""

    @pytest.mark.parametrize('deger', [True, False])
    def test_bool_epsilon_adiyla_reddedilir(self, istemci, deger):
        kod, govde = _post(istemci, '/calculate',
                           dict(HIBRIT, expansion_ratio=deger))
        assert kod == 400, govde
        alanlar = [k.get('field')
                   for k in govde.get('invalid_fields', [])]
        assert 'expansion_ratio' in alanlar, govde
        # Sayı UYDURULMADI: ne 1,0 ne 0 aşağıya indi.
        assert 'motor' not in govde


# ---------------------------------------------------------------------------
# OH-D25-17 — öksüz uç kararı
# ---------------------------------------------------------------------------
class TestOHD2517OksuzUc:
    """Karar: iki uç KALDIRILMAZ, ürün-dışı API yüzeyi olarak BEYAN EDİLİR.

    Ölçüldü (``a3/once.json`` K7): ``templates/`` + ``static/`` içinde
    ``/api/chemical-species`` 0, ``/api/get-fuel-properties`` 0 geçiş.
    Kaldırma app-api'nin tek başına veremeyeceği bir karardır (uçlar dış
    tüketiciye açık HTTP yüzeyidir ve sürüm sözleşmesi taşır); bağlama ise
    ``templates/`` sahibinin (arayuz) işidir. Bu dalgada yapılan: ÖKSÜZLÜK
    KODA YAZILDI — uç kendi yanıtında ürün yüzünde çağrılmadığını söylüyor,
    böylece "kullanılıyor sanılan" uç sessiz kalmıyor.
    """

    @pytest.mark.parametrize('yol', ['/api/chemical-species',
                                     '/api/get-fuel-properties'])
    def test_urun_yuzunde_gecis_yok(self, yol):
        n = 0
        for alt in ('templates', 'static'):
            d = KOK / 'hrma' / alt
            for p in d.rglob('*'):
                if p.is_file() and p.suffix in ('.html', '.js'):
                    n += p.read_text('utf-8', errors='ignore').count(yol)
        assert n == 0, (
            f'{yol} artık ürün yüzünde çağrılıyor ({n} geçiş) — öksüzlük '
            'beyanı bayatladı, kaldırın')

    @pytest.mark.parametrize('yol,yuk', [
        ('/api/chemical-species', {'species_name': 'H2O',
          'temperature': 3000}),
        ('/api/get-fuel-properties', {'fuel_type': 'htpb'}),
    ])
    def test_yanit_oksuzlugu_beyan_ediyor(self, istemci, yol, yuk):
        kod, govde = _post(istemci, yol, yuk)
        assert kod == 200, govde
        kunye = govde.get('surface_note')
        assert kunye, f'{yol}: öksüzlük beyanı yanıtta yok'
        assert 'not called by the shipped user interface' in kunye


# ---------------------------------------------------------------------------
# OH-Z5-02 — beş yaprağın hükmü
# ---------------------------------------------------------------------------
class TestOHZ502AppApiYapraklari:

    def test_aynalanmis_beyan_yankisi_taniniyor(self):
        from support import shake
        assert shake.is_declaration_echo('.inputs_not_used[0].submitted')
        assert shake.is_declaration_echo(
            '.input_warnings[0].params.submitted')
        # DAR: çözücünün kendi sonucu kapsam DIŞI.
        assert not shake.is_declaration_echo(
            '.input_warnings[0].params.used_by_model')
        assert not shake.is_declaration_echo('.inputs_not_used[0].used_by_model')

    def test_dort_yaprak_kunyeli_imde(self):
        kaynak = (KOK / 'tests' / 'test_field_wiring_layer_b.py').read_text(
            'utf-8')
        for yol in ('inputs_not_used[0].submitted_value_echo_count',
                    'inputs_not_used[0].solved_value_echo_count',
                    'validation.injector_assessment.pressure_drop_ratio'
                    '.band[0]',
                    'validation.injector_assessment.pressure_drop_ratio'
                    '.band[1]'):
            assert "'%s'," % yol in kaynak, yol
        # Künye: her im kendi kod kanıtını taşıyor.
        assert 'validation_system.py:99' in kaynak
        assert 'z5_sayac_gecis.json' in kaynak

    #: D26'da YAYIMLANAN eşik. İki yanı da 1'di; sayı buradan yalnız
    #: AŞAĞI gidebilir (borç ödendikçe), yukarı ASLA (ÖK-22).
    D26_YAYIMLANAN_ESIK = 1

    def test_esik_ayni_committe_dustu(self):
        """Eşik İKİ YANLI ve yalnız SIKILAŞABİLİR.

        ÖH D30 / fix-29a — BAYAT METİN MANDALI. Bu bekçi eşiği
        ``'assert len(suspicious) <= 1,' in kaynak`` diye METİN olarak
        arıyordu, yani D26'daki SAYIYI kendi gövdesine kopyalamıştı. ÖH
        D29 termo-uçuş a1 (7de9049f, OH-D28-01) borcu gerçekten kapatıp
        eşiği iki yanından da 1 -> 0 indirince — yani bekçinin KORUDUĞU
        şey iyileşince — bu test kırmızıya döndü: onarımı cezalandıran,
        gevşemeyi göremeyen bir mandal.

        İddia korunur ama İLİŞKİ olarak ölçülür (D25 kalıbı,
        ``test_d23_bekci_cevirisi_a1::…::test_esik_gevsetilmedi``):
        eşiğin iki yanı da VAR, birbirine EŞİT (iki yanlı sözleşme) ve
        D26'da yayımlanan değeri AŞMIYOR. Eşiği yükselten bir hamle
        kırmızı yanar; indiren hamle sessizce geçer, çünkü mandalın
        koruduğu yön budur.
        """
        kaynak = (KOK / 'tests' / 'test_field_wiring_layer_b.py').read_text(
            'utf-8')
        ust = re.findall(r'assert len\(suspicious\) <= (\d+),', kaynak)
        alt = re.findall(r'assert len\(suspicious\) >= (\d+),', kaynak)
        assert len(ust) == 1 and len(alt) == 1, (
            'iki yanlı eşik sözleşmesi bozulmuş (üst %r, alt %r) — her iki '
            'yan da TAM BİR KEZ yazılmalı' % (ust, alt))
        ust, alt = int(ust[0]), int(alt[0])
        assert ust == alt, (
            'eşiğin iki yanı ayrışmış (üst %d, alt %d): tek yönlü eşik, '
            'borcu BEYAZ LİSTEYE alarak gizlemeyi göremez' % (ust, alt))
        assert ust <= self.D26_YAYIMLANAN_ESIK, (
            'eşik D26 yayımından (%d) YUKARI çekilmiş (%d) — bu bir '
            'gevşetmedir (ÖK-22): sabit yaprak borcu ancak kod onarılarak '
            'düşürülür, eşik büyütülerek değil.'
            % (self.D26_YAYIMLANAN_ESIK, ust))

    def test_enjektor_bandi_yayimlanan_esiktir(self):
        """İmin gerekçesi ÖLÇÜLÜR: bant deponun tek tanım noktasından."""
        from hrma.analysis.acoustic_modes import CHUG_DP_RATIO_MINIMUM
        from hrma.validation.validation_system import ValidationSystem
        vs = ValidationSystem()
        bant = vs.injector_limits['pressure_drop_ratio']
        assert bant[0] == CHUG_DP_RATIO_MINIMUM
        kaynak = vs.injector_limit_sources['pressure_drop_ratio']
        assert 'CHUG_DP_RATIO_MINIMUM' in kaynak
        assert 'SP-8089' in kaynak
