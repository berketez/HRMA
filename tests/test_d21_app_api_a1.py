"""ÖH D21 / app-api aşama-1 bekçileri.

Kapsanan kalemler:

* **OH-D17-23** — ``/api/oxidizer-properties`` tanınmayan akışkanda HTTP 200
  + ``{'status':'error'}`` gövdesi döndürüyordu; ayrıca ucun ÜST kapısı
  (bant) adı ``normalize_oxidizer`` ile çözerken ALT kapı (çözücü) ham adı
  okuyordu.
* **OH-D19-08** — ``/calculate`` serileştirme hata yolunda dört alan
  ``…get(ad, 0)`` ile okunuyor, çözülemeyen oda basıncı **0 bar** olarak
  yayımlanıyordu (sıfır uydurması).
* **OH-D19-09** — yedi kardeş uç ``chamber_pressure`` varsayılanını ÇIPLAK
  ``20.0`` olarak yazıyor ve düşüşü beyan etmiyordu.
* **OH-D18-01** — ürün yüzünün çağırdığı beş rota uç üzerinden hiç
  sınanmıyordu.

Her sınıf, onarım geçici olarak geri alındığında KIRMIZIYA döner
(ters-mutasyon kanıtı: ``docs/scofield/raw/OH/D21/app-api/a1/mutasyon.json``).
"""
import ast
import contextlib
import io
import json
import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
D21_APP_KAYNAGI = (KOK / 'hrma' / 'app.py').read_text(encoding='utf-8')


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


def _get(istemci, yol):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            r = istemci.get(yol)
    return r.status_code, r.get_data(as_text=True)


def _sayfa_dogrula(r, yol):
    """Ürün sayfası GERÇEKTEN açıldı mı? (boş 200 kabul edilmez)"""
    assert r.status_code == 200, f'{yol}: HTTP {r.status_code}'
    metin = r.get_data(as_text=True)
    assert 'html' in metin[:400].lower(), f'{yol}: HTML gövdesi değil'
    assert len(metin) > 1000, f'{yol}: gövde boş görünüyor ({len(metin)})'


# ---------------------------------------------------------------------------
# OH-D17-23
# ---------------------------------------------------------------------------
class TestOHD1723OksitleyiciHataKodu:
    """Hata gövdesi 200 ile dönmez; ad iki kapıda AYNI normalize edilir."""

    #: ÖLÇÜLDÜ (``once.json`` K1, taban ``35aa279``): bu üç girdinin ÜÇÜ de
    #: HTTP 200 + ``{'status':'error','error':'Unknown oxidizer type: …'}``
    #: döndürüyordu. ``fetch`` sarmalayıcıları ``response.ok``a bakar.
    OLCULEN_200_HATALARI = ('n2o4', 'kerosene', '')

    @pytest.mark.parametrize('ad', OLCULEN_200_HATALARI)
    def test_cozulemeyen_akiskan_200_donmez(self, istemci, ad):
        kod, govde = _post(istemci, '/api/oxidizer-properties',
                           {'oxidizer_type': ad})
        assert kod == 400, (
            f'{ad!r} çözülemedi ama HTTP {kod} döndü; hata gövdesi başarı '
            'koduyla taşınıyor')
        assert govde.get('status') == 'error'
        assert govde.get('error_code'), (
            'ret ADSIZ: tüketici hangi hatayı aldığını ayırt edemez')
        assert govde.get('field') == 'oxidizer_type'
        assert govde.get('accepted_values'), 'kabul edilen küme yayımlanmıyor'

    def test_iki_durum_ayri_kodla_ayrilir(self, istemci):
        """Tanınan-ama-modelsiz akışkan ile tanınmayan ad AYNI şey değildir.

        ``n2o4`` deponun ``OXIDIZER_ALIASES``/``OXIDIZER_DENSITY_ENVELOPE``
        tablolarında VARDIR; bu uçta özellik modeli yoktur. ``kerosene``
        bir oksitleyici bile değildir.
        """
        _, bilinen = _post(istemci, '/api/oxidizer-properties',
                           {'oxidizer_type': 'n2o4'})
        _, bilinmeyen = _post(istemci, '/api/oxidizer-properties',
                              {'oxidizer_type': 'kerosene'})
        assert bilinen.get('error_code') == 'oxidizer_properties_unavailable'
        assert bilinen.get('resolved_as') == 'n2o4'
        assert bilinmeyen.get('error_code') == 'oxidizer_type_unknown'
        assert bilinen['error_code'] != bilinmeyen['error_code']

    def test_hicbir_ret_gövdesinde_sayi_yok(self, istemci):
        """Fail-closed: çözülemeyen durumda özellik SAYISI yayımlanmaz."""
        for ad in ('n2o4', 'kerosene'):
            _, govde = _post(istemci, '/api/oxidizer-properties',
                             {'oxidizer_type': ad})
            for alan in ('density', 'viscosity', 'vapor_pressure',
                         'molecular_weight'):
                assert alan not in govde, (
                    f'{ad}: reddedilen istekte {alan} sayısı yayımlanıyor')

    #: ÖLÇÜLDÜ: ``nitrous`` @ 2000 K bant kapısından 400 alıyordu (üst kapı
    #: adı çözüyor) ama @ 293 K "Unknown oxidizer type" alıyordu (alt kapı
    #: ham adı okuyor). Aynı akışkan, iki sözleşme.
    OKSITLEYICI_TAKMA_ADLARI = (('nitrous', 'n2o'), ('nitrous_oxide', 'n2o'),
                   ('oxygen', 'lox'), ('hydrogen_peroxide', 'h2o2'))

    @pytest.mark.parametrize('takma,kanonik', OKSITLEYICI_TAKMA_ADLARI)
    def test_takma_ad_iki_kapida_ayni_cozulur(self, istemci, takma, kanonik):
        kod, govde = _post(istemci, '/api/oxidizer-properties',
                           {'oxidizer_type': takma})
        assert kod == 200, (
            f'{takma!r} bant kapısında {kanonik} olarak çözülüyor ama '
            f'çözücüde çözülemiyor: HTTP {kod}')
        assert govde.get('status') == 'success'

    def test_kanonik_adlarin_sozlesmesi_degismedi(self, istemci):
        """Çapa: bugün çalışan ÜÇ ad AYNEN 200 kalır.

        ÖH D31 / P7B2-03 — ÇEVRİLDİ, gerekçe: bu çapa kurulduğunda
        ``air`` bu ucun kabul listesindeydi. ÖLÇÜLDÜ (``D31/app-api-uc/
        a2/once.json`` K5) ki ``air`` bu üründe oksitleyici DEĞİLDİR:
        ``normalize_oxidizer('air')`` None döner, ``advanced.html``
        seçeneği ``disabled``, ``/calculate`` 400,
        ``/api/get-propellant-properties`` 422 verir — yalnız bu uç 200 +
        yoğunluk yayımlıyordu. Bölme söküldü; ``air`` artık aşağıdaki
        bekçide kardeşleriyle aynı sözleşmededir. Çapanın KENDİSİ
        (üç gerçek oksitleyicinin 200 kalması) BOZULMADI.
        """
        for ad in ('n2o', 'lox', 'h2o2'):
            kod, govde = _post(istemci, '/api/oxidizer-properties',
                               {'oxidizer_type': ad})
            assert kod == 200 and govde.get('status') == 'success', \
                f'{ad}: HTTP {kod}'

    def test_air_kabul_listesinde_DEGIL(self, istemci):
        """ÖH D31 / P7B2-03 — sökülen bölmenin kilidi."""
        kod, govde = _post(istemci, '/api/oxidizer-properties',
                           {'oxidizer_type': 'air'})
        assert kod == 400, f'air hâlâ sayı yayımlıyor: HTTP {kod}'
        assert 'air' not in (govde.get('accepted_values') or [])


# ---------------------------------------------------------------------------
# OH-D19-08
# ---------------------------------------------------------------------------
class TestOHD1908SifirUydurmasi:
    """Serileştirme hata yolu eksik alanı 0 ile doldurmaz."""

    def test_ciplak_sifir_yedegi_kalmadi(self):
        """``motor_results.get(<ad>, 0)`` deseni ``/calculate``te yok.

        ÖLÇÜLDÜ (``once.json`` K2): dört alan bu desende okunuyordu ve
        blok YALNIZ çözümün serileştirilemediği anda çalışır — yani tam da
        sayının güvenilmez olduğu anda 0 yayımlanıyordu.
        """
        kalan = re.findall(r"motor_results\.get\('\w+',\s*0\)", D21_APP_KAYNAGI)
        assert kalan == [], (
            f'sıfır yedeği geri geldi: {kalan}')

    def test_yedek_blok_eksigi_adiyla_bildirir(self):
        """Blok, eksik alanı ATLAR ve ``unavailable_fields``e yazar."""
        assert 'unavailable_fields' in D21_APP_KAYNAGI
        assert "'error': 'result_serialization_failed'" in D21_APP_KAYNAGI

    def test_yedek_blok_basari_kodu_donmez(self):
        """Gövde ``error_info`` taşırken HTTP 200 dönmek yasak.

        ``response.ok``a bakan tüketici, hesabın çöktüğü yanıtı başarı
        sayardı (OH-D17-23 ile aynı gerekçe).
        """
        # ÖH D26 a3 (Fable-D21 ŞART): blok ``_serilestirme_yedegi``
        # yardımcısına çıktı; statik bekçi YENİ ŞEKLE bağlandı ve artık TEK
        # bekçi değil — dinamik ölçüm tests/test_d26_app_api_a3.py::
        # TestOHD1908YedekYardimcisi'nde.
        blok = D21_APP_KAYNAGI.split('def _serilestirme_yedegi(', 1)
        assert len(blok) == 2, 'yedek yardımcısı bulunamadı'
        kuyruk = blok[1][:2400]
        assert 'return govde, 500' in kuyruk, 'yedek hâlâ 200 ile dönüyor'
        assert ('_yedek_govde, _yedek_kod = _serilestirme_yedegi('
                in D21_APP_KAYNAGI), 'uç yardımcıyı çağırmıyor'

    def test_sifir_dolduran_yedek_gercekten_sifir_uretiyordu(self):
        """Ters-mutasyonun hedefi: kusurlu satır 0 üretiyordu.

        Bu bir birim ölçümüdür — kusurlu deseni ayrı çalıştırıp 0'ın
        gerçekten yayımlanacağını gösterir; bekçinin neyi koruduğu
        böylece koda bağlanır.
        """
        motor_results = {'thrust': 1000.0}     # oda basıncı YOK
        kusurlu = motor_results.get('chamber_pressure', 0)
        assert kusurlu == 0
        onarilmis = {}
        for ad in ('thrust', 'chamber_pressure'):
            d = motor_results.get(ad)
            if isinstance(d, (int, float)) and not isinstance(d, bool):
                onarilmis[ad] = d
        assert 'chamber_pressure' not in onarilmis


# ---------------------------------------------------------------------------
# OH-D19-09
# ---------------------------------------------------------------------------
class TestOHD1909CiplakVarsayilan:
    """Yedi kardeş site tek kaynaktan okur ve düşüşü beyan eder."""

    def test_ciplak_20_0_sitesi_kalmadi(self):
        """ÖLÇÜLDÜ (``once.json`` K3): 8 eşleşme, 7'si CANLI KOD.

        Kalan tek eşleşme ``/calculate`` içindeki AÇIKLAMA satırıdır
        (eski satırı belgeliyor); o yüzden sayım kod satırları üstünde
        yapılır.
        """
        canli = [s for s in D21_APP_KAYNAGI.split('\n')
                 if re.search(r"'chamber_pressure',\s*20\.0", s)
                 and not s.lstrip().startswith('#')]
        assert canli == [], f'çıplak varsayılan geri geldi: {canli}'

    def test_tek_kaynak_sabiti_okunuyor(self):
        """Sayı iki yerde yazılmaz (Doktrin 4)."""
        # ÖH D26 a3 (ŞART OH-D19-09 ikinci ayak): iki site sayıyı künye
        # üreticisinin DÖNÜŞÜNDEN alıyor; sayım o iki siteyi de sayar.
        assert (D21_APP_KAYNAGI.count(
            "'chamber_pressure', _CALCULATE_PC_DEFAULT_BAR")
                + D21_APP_KAYNAGI.count('= _pc_varsayilan_kunyesi(')) >= 5
        # Tek kaynak: çıplak 20.0 hiçbir CANLI satırda yok.
        assert [s for s in D21_APP_KAYNAGI.split('\n')
                if re.search(r"'chamber_pressure',\s*20\.0", s)
                and not s.lstrip().startswith('#')] == []

    #: Gövdesinde ``chamber_pressure`` GÖNDERİLMEYEN istekler. Her biri
    #: bugün bir sayı yayımlıyor; hangi basınçta çözüldüğü ADIYLA
    #: söylenmelidir (ÖK-19).
    BEYAN_BEKLEYEN = (
        ('/calculate', {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                        'fuel_type': 'htpb', 'oxidizer_type': 'n2o'}),
        ('/api/find-optimum-of', {'motor_type': 'hybrid', 'oxidizer': 'n2o',
                                  'fuel': 'htpb'}),
        ('/api/quick-geometry', {'thrust': 1000, 'burn_time': 10,
                                 'of_ratio': 6.0, 'fuel_type': 'htpb',
                                 'oxidizer_type': 'n2o'}),
        # --- ÖH D26 a3 (Fable-D21 ŞART) — DÖRT UÇ EKLENDİ ----------------
        # Fable ölçtü: transient/flow künyesi sökülünce sınıf 9/9 YEŞİL
        # kalıyordu (KÖR bekçi); kinetic/parametric için dinamik bekçi hiç
        # yoktu. Beşinci uç (``/api/advanced-analysis``) bu tuple'a GİRMEZ:
        # gövdesi ``motor_data`` sarmalı taşıdığı için ikili
        # parametrizasyonun ``dict(yuk, chamber_pressure=25.0)`` hamlesi
        # orada yanlış yere yazardı; o uç ayrı bekçidedir
        # (tests/test_d26_app_api_a3.py::TestOHD1909BesUc::
        # test_advanced_analysis_ust_seviyede_kunye).
        ('/api/transient-analysis', {'thrust': 1000, 'burn_time': 10,
                                     'of_ratio': 6.0, 'fuel_type': 'htpb',
                                     'oxidizer_type': 'n2o'}),
        ('/api/kinetic-efficiency', {'of_ratio': 6.0,
                                     'characteristic_length': 1.0,
                                     'throat_diameter': 0.03}),
        ('/parametric-analysis', {'param_type': 'of_ratio', 'param_start': 4,
                                  'param_end': 8, 'param_steps': 3,
                                  'thrust': 1000, 'burn_time': 10,
                                  'fuel_type': 'htpb',
                                  'oxidizer_type': 'n2o'}),
    )

    #: ÖH D32 / arayuz-panel a2 (OH-D31-14) — ``/api/flow-analysis``
    #: ``BEYAN_BEKLEYEN``den ÇIKTI. O uçta ``chamber_pressure`` artık
    #: düşmüyor: alan-alan kapı onu adıyla istiyor (422
    #: ``incomplete_flow_input``). Künye zayıf hükümdü, kapı güçlü hüküm —
    #: satır silinmedi, HÜKMÜ SERTLEŞTİ ve buraya taşındı.
    FAIL_CLOSED_BEKLEYEN = (
        ('/api/flow-analysis', {'fidelity': 'engineering'},
         'chamber_pressure'),
    )

    #: İki tablonun toplamı kilitli: kimse bir ucu sessizce düşüremez.
    TOPLAM_UC_SATIRI = 7

    def test_satir_sayisi_kilitli(self):
        assert (len(self.BEYAN_BEKLEYEN) + len(self.FAIL_CLOSED_BEKLEYEN)
                == self.TOPLAM_UC_SATIRI)

    @pytest.mark.parametrize('yol,yuk,alan', FAIL_CLOSED_BEKLEYEN)
    def test_dusmeyen_alan_ADIYLA_istenir(self, istemci, yol, yuk, alan):
        """ÖH D32 (OH-D31-14): künye yerine kapı — künye kanalı susar."""
        kod, govde = _post(istemci, yol, dict(yuk))
        assert kod == 422, f'{yol}: {alan} uydurularak çözüldü (HTTP {kod})'
        assert alan in (govde.get('missing_fields') or []), govde
        assert govde.get('defaults_applied') is None, govde

    @pytest.mark.parametrize('yol,yuk', BEYAN_BEKLEYEN)
    def test_dusus_adiyla_yayimlanir(self, istemci, yol, yuk):
        kod, govde = _post(istemci, yol, yuk)
        assert kod == 200, f'{yol}: HTTP {kod}'
        kunye = govde.get('defaults_applied')
        assert kunye, (
            f'{yol}: oda basıncı gönderilmedi, varsayılanda çözüldü ve '
            'yanıt bunu hiçbir yerde söylemiyor')
        alanlar = [k.get('field') for k in kunye if isinstance(k, dict)]
        assert 'chamber_pressure' in alanlar
        kayit = next(k for k in kunye if k.get('field') == 'chamber_pressure')
        assert kayit.get('unit') == 'bar'
        assert isinstance(kayit.get('value'), (int, float))

    @pytest.mark.parametrize('yol,yuk', BEYAN_BEKLEYEN)
    def test_deger_gonderildiginde_kunye_eklenmez(self, istemci, yol, yuk):
        """Çapa korunur: kullanıcı BASINCI verdiyse basınç künyesi çıkmaz.

        ÖH D26 / app-api a4 (P7B4-05) — DARALTILDI, GEREKÇE: bekçi eskiden
        ``defaults_applied`` anahtarının BÜTÜNÜNÜN yokluğunu şart
        koşuyordu. O gün bu ucun tek beyanlı varsayılanı basınçtı, yani
        iki ifade denkti. P7B4-05 ölçümü (``a4/once.json`` K9) gösterdi ki
        ``/api/flow-analysis`` boş gövdeye DOKUZ uydurma varsayılanla çözüm
        yayımlıyor ve kalan sekizi (3000 K · γ 1,2 · MW 24 · D_t 0,02 m ·
        101.325 Pa · 45 · 0,40 · 800 K) SESSİZDİ. Sekizi de aynı kanaldan
        beyan edilince bu gövdede de künye doğar — ama BASINÇ künyesi
        doğmaz, çapanın koruduğu şey odur. Bekçi artık tam olarak onu
        ölçüyor: geniş hâli, sekiz sayının sessiz kalmasını KORUYAN bir
        bekçiye dönüşmüştü (ÖK-05 "kusuru koruyan bekçi").
        """
        kod, govde = _post(istemci, yol, dict(yuk, chamber_pressure=25.0))
        assert kod == 200, f'{yol}: HTTP {kod}'
        beyan = [k.get('field') for k in (govde.get('defaults_applied') or [])]
        assert 'chamber_pressure' not in beyan, (
            f'{yol}: basınç gönderildiği hâlde künyesi eklendi '
            f'(çapa kırılır): {beyan}')
        # Beyan edilen HER alan gerçekten GÖNDERİLMEMİŞ olmalı.
        for ad in beyan:
            assert dict(yuk, chamber_pressure=25.0).get(ad) in (None, ''), (
                f'{yol}: {ad} gönderilmişken varsayılan künyesi basıldı')

    def test_optimum_kunyesi_yalan_soylemiyor(self, istemci):
        """``optimum_of_ratio_basis`` "requested" demeyi bırakır.

        Eski metin oda basıncı gönderilmese de "at the requested chamber
        pressure" diyordu.
        """
        _, yok = _post(istemci, '/api/find-optimum-of',
                       {'motor_type': 'hybrid', 'oxidizer': 'n2o',
                        'fuel': 'htpb'})
        _, var = _post(istemci, '/api/find-optimum-of',
                       {'motor_type': 'hybrid', 'oxidizer': 'n2o',
                        'fuel': 'htpb', 'chamber_pressure': 25.0})
        assert 'assumed default' in yok.get('optimum_of_ratio_basis', '')
        assert var.get('optimum_of_ratio_basis', '').endswith(
            'requested chamber pressure')


# ---------------------------------------------------------------------------
# OH-D18-01
# ---------------------------------------------------------------------------
class TestOHD1801UcBekcileri:
    """fix-8'in bulduğu beş rota artık UÇ ÜZERİNDEN sınanıyor."""

    # NOT — rota dizgileri BİLEREK ``istemci.post``/``istemci.get`` çağrısının
    # BİRİNCİ ARGÜMANINA sabit olarak yazıldı. ``test_d18_bekci_cevirisi_a1``
    # akış haritası uçları AST ile sayar (``_testin_cagirdiklari``); yardımcı
    # sarmalayıcıdan geçen çağrı o sayımda GÖRÜNMEZ ve borç ödenmemiş
    # sayılırdı. Ölçüm aracının gördüğü biçimde yazmak bu bekçinin şartıdır.

    def test_yanma_kararliligi_adsiz_mod_reddeder(self, istemci):
        """ÇEVRİLDİ — ÖH D30 / app-api-uc a3 · P16B3-35.

        Bekçinin iddiası ("mod verilmeden hüküm üretilmez") DEĞİŞMEDİ,
        beklenen kod 400 → **422** oldu. Gerekçe: gönderilmeyen ``mode``
        "tanınmayan değer" dalından geçiyor ve yanıt *"Unknown mode
        **None**"* diyordu (ölçüm: ``docs/scofield/raw/OH/D30/
        app-api-uc/a3/once.json`` K3). Eksik zorunlu girdinin bu uçtaki
        kurulu sözleşmesi 422 + ``missing_fields``tir (aynı fonksiyonun
        mod-içi kapısı). Tanınmayan MOD hâlâ 400 — bir alt bekçi
        (``test_yanma_kararliligi_taninmayan_modda_sayi_uretmez``) onu
        ölçmeye devam ediyor.

        Çağrı satırı BİÇİMİ korundu: ``test_d18_bekci_cevirisi_a1`` akış
        haritası uçları AST ile, ``istemci.post('<yol>', ...)`` birinci
        argümanından sayıyor.
        """
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = istemci.post('/api/analysis/combustion-stability', json={})
        assert r.status_code == 422, (
            f'HTTP {r.status_code}: mod verilmeden hüküm üretildi')
        assert 'mode' in r.get_data(as_text=True).lower()
        assert (r.get_json() or {}).get('missing_fields') == ['mode']

    def test_yanma_kararliligi_taninmayan_modda_sayi_uretmez(self, istemci):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = istemci.post('/api/analysis/combustion-stability',
                                 json={'mode': 'yok-boyle-bir-mod'})
        assert r.status_code == 400
        govde = r.get_json() or {}
        assert 'stability' not in govde, 'reddedilen istekte hüküm yayımlandı'

    def test_termal_fea_motor_sonucu_olmadan_hesap_yapmaz(self, istemci):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = istemci.post('/api/fea/thermal', json={})
        assert r.status_code == 400, f'HTTP {r.status_code}'
        govde = r.get_json() or {}
        assert govde.get('error') == 'missing_motor_results'
        assert govde.get('checked_fields'), 'hangi alanların arandığı yok'
        for alan in ('temperature_field', 'mesh', 'max_temperature'):
            assert alan not in govde, (
                f'motor sonucu yokken {alan} yayımlandı')

    def test_formuller_sayfasi_acilir(self, istemci):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = istemci.get('/formulas')
        _sayfa_dogrula(r, '/formulas')

    def test_hibrit_sayfasi_acilir(self, istemci):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = istemci.get('/hybrid')
        _sayfa_dogrula(r, '/hybrid')

    def test_firlatma_sahasi_sayfasi_acilir(self, istemci):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = istemci.get('/launch-site')
        _sayfa_dogrula(r, '/launch-site')

    def test_envanterden_bes_rota_silindi(self):
        """Borç ADIYLA sayılıyordu; bekçi geldi, satır silinir (ÖK-22).

        Envanter GEVŞETİLMEDİ — tersine daraldı: bu beş rota artık uç
        üzerinden sınandığı için borç listesinde durmalarının gerekçesi
        kalmadı.
        """
        metin = (KOK / 'tests' / 'test_d18_bekci_cevirisi_a1.py').read_text(
            encoding='utf-8')
        agac = ast.parse(metin)
        envanter = None
        for d in ast.walk(agac):
            if (isinstance(d, ast.Assign) and d.targets
                    and isinstance(d.targets[0], ast.Name)
                    and d.targets[0].id
                    == 'UC_BEKCISI_OLMAYAN_URUN_ROTALARI'):
                envanter = {e.value for e in ast.walk(d.value)
                            if isinstance(e, ast.Constant)
                            and isinstance(e.value, str)}
        assert envanter is not None, 'envanter bulunamadı'
        for rota in ('/api/analysis/combustion-stability', '/api/fea/thermal',
                     '/formulas', '/hybrid', '/launch-site'):
            assert rota not in envanter, (
                f'{rota} bekçisi yazıldı ama borç listesinden silinmedi')


# ---------------------------------------------------------------------------
# P15B1-05 (kalan yarı: birim tuzağı)
# ---------------------------------------------------------------------------
class TestP15B105BirimTuzagi:
    """``cp``/``enthalpy``/``entropy`` iki uçta 1000 kat ayrışıyordu."""

    def test_iki_ucun_birim_sozlesmesi_govdede(self, istemci):
        """ÖLÇÜLDÜ: aynı üç ad, iki uç, tam 1000 kat fark, birim YAZILI DEĞİL.

        ``/api/chemical-species`` ``chemical_database.calculate_cp``in ham
        ``J/mol/K`` çıktısını, ``/api/get-fuel-properties`` ise aynı adı
        ``_kJ()`` ile 1000'e bölünmüş hâlde yayımlıyordu. Sayı DEĞİŞMEDİ;
        değişen, birimin gövdede olmasıdır.
        """
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = istemci.post('/api/chemical-species',
                                 json={'species_name': 'CO2',
                                       'temperature': 2000})
        assert r.status_code == 200, f'HTTP {r.status_code}'
        termo = (r.get_json() or {}).get(
            'species_data', {}).get('thermodynamic_properties', {})
        birimler = termo.get('units')
        assert birimler, 'ham J tabanlı uç birimini yayımlamıyor'
        assert birimler['cp'] == 'J/mol/K'
        assert birimler['enthalpy'] == 'J/mol'

    def test_kardes_uc_kj_birimini_yayimliyor(self, istemci):
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                r = istemci.post('/api/get-fuel-properties',
                                 json={'fuel_type': 'htpb',
                                       'temperature': 2000})
        assert r.status_code == 200, f'HTTP {r.status_code}'
        govde = r.get_json() or {}
        ozellikler = govde.get('properties', govde)
        birimler = ozellikler.get('units')
        assert birimler, 'kJ tabanlı uç birimini yayımlamıyor'
        assert birimler['cp'] == 'kJ/mol/K'
        assert birimler['enthalpy'] == 'kJ/mol'

    def test_birim_dizgileri_tek_kaynakta(self):
        """Doktrin 4: birim dizgisi iki uçta ayrı ayrı yazılmaz."""
        assert '_TERMO_BIRIMLERI_J' in D21_APP_KAYNAGI
        assert '_TERMO_BIRIMLERI_KJ' in D21_APP_KAYNAGI
        # Uçlar sabiti OKUR; dizgiyi kendileri yazmaz.
        assert D21_APP_KAYNAGI.count("'cp': 'J/mol/K'") == 1
        assert D21_APP_KAYNAGI.count("'cp': 'kJ/mol/K'") == 1

    def test_iki_taban_gercekten_1000_kat_ayrisiyor(self, istemci):
        """Tuzağın kendisi ölçülür: aynı tür, aynı T, iki uç, 1000 kat."""
        with contextlib.redirect_stdout(io.StringIO()):
            with contextlib.redirect_stderr(io.StringIO()):
                a = istemci.post('/api/chemical-species',
                                 json={'species_name': 'CO2',
                                       'temperature': 2000})
        ham = (a.get_json() or {}).get('species_data', {}).get(
            'thermodynamic_properties', {})
        # NOT: ``cp`` bu türde ``None`` olabilir (P9B4-12 fail-closed dalı:
        # katsayı kazanılmamışsa sayı üretilmez). Ölçülen şey SAYI DEĞİL,
        # BİRİM SÖZLEŞMESİdir — iki ucun tabanı ayırt edilebiliyor mu?
        assert ham['units']['cp'].startswith('J/'), (
            'ham uç birimi kJ olarak ilan edilirse iki uç ayırt edilemez')
        assert not ham['units']['cp'].startswith('kJ/')


# ---------------------------------------------------------------------------
# ÖH D27 / app-api a3 (OH-D26-20) — /api/flow-analysis TAM FAIL-CLOSED
# ---------------------------------------------------------------------------
class TestOHD2620FlowFailClosed:
    """Eksik gövde artık hüküm ALMIYOR; iki eski bekçinin çevrildiği yer.

    ÖLÇÜLDÜ (``docs/scofield/raw/OH/D27/app-api/a3/once.json`` K5, worktree
    ``a67dd68``): ``{}`` gövdesi HTTP 200 + ``status='success'`` + tam bir
    quasi-1D akış çözümü + DOKUZ ``defaults_applied`` künyesi alıyordu.
    Künye D26 a4'te (P7B4-05) doğru biçimde eklenmişti; kusur beyanın
    yokluğu değil, beyanın ÇÖZÜM SAYILMASIYDI (Doktrin 1).

    Ayrım tabloya değil tablonun KENDİ gerekçesine dayanır: motorun kendisi
    olan altı büyüklük zorunlu, model/ayrıklaştırma seçimi olan üçü
    (``n_stations``, ``separation_factor``, ``wall_temperature``) beyanlı
    varsayılan olarak kalır.
    """

    def test_bos_govde_hukum_ALMAZ(self, istemci):
        kod, govde = _post(istemci, '/api/flow-analysis', {})
        assert kod == 422, f'boş gövde hâlâ çözülüyor: HTTP {kod}'
        assert govde['error'] == 'incomplete_flow_input'
        assert 'flow' not in govde, 'reddedilen istekte akış çözümü var'
        assert govde.get('defaults_applied') is None

    def test_paylasimli_parametrizasyon_YABANCI_UCLARA_DOKUNULMADI(self):
        """ÖH D33-2 / app-api-uc a1 (OH-D32-13) — MANDAL ÇEVRİLDİ.

        Eski hâli ``test_paylasimli_parametrizasyon_DOKUNULMADI`` idi ve
        ``/api/flow-analysis``in ``BEYAN_BEKLEYEN`` tablosunda DURMASINI
        şart koşuyordu — yani o uçta kusurun (motorun künyeyle
        uydurulmasının) sürmesini kilitleyen bir mandaldı. Kapı alan-alan
        indiği için (ölçüm: ``D33-2/app-api-uc/a1/sonra_ohd3114.json`` K1,
        18/18 istek 422) uç ``FAIL_CLOSED_BEKLEYEN``e taşındı.

        İDDİANIN ASIL ÇEKİRDEĞİ KORUNDU ve GÜÇLENDİ: bu bekçinin derdi
        "paylaşımlı tablodaki YABANCI uçlara dokunulmadı" idi; o uçlar
        adıyla sayılıyor, ayrıca ``/api/flow-analysis``in iki tablodan
        BİRİNDE ve yalnız birinde olduğu mandallanıyor.
        """
        yollar = [y for y, _ in
                 TestOHD1909CiplakVarsayilan.BEYAN_BEKLEYEN]
        fail_closed = [y for y, _s, _a in
                       TestOHD1909CiplakVarsayilan.FAIL_CLOSED_BEKLEYEN]
        # Yabancı kulvarların uçları tabloda AYNEN duruyor.
        for yabanci in ('/api/transient-analysis', '/api/kinetic-efficiency',
                        '/parametric-analysis', '/api/quick-geometry',
                        '/api/find-optimum-of', '/calculate'):
            assert yabanci in yollar, f'{yabanci} tablodan düşürülmüş'
        assert len(yollar) >= 5
        # Akış ucu künye tablosundan çıktı, kapı tablosuna girdi — ikisinde
        # birden ya da hiçbirinde olamaz.
        assert '/api/flow-analysis' not in yollar
        assert '/api/flow-analysis' in fail_closed
