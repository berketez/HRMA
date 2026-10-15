"""ÖH Dalga-17 · kulvar **app-api** · aşama 1 — onarım bekçileri.

Her sınıf bir defter kalemine bağlıdır ve iddiası ÖLÇÜLMÜŞ vakalardan
kurulur (``docs/scofield/raw/OH/D17/app-api/a1/once_p16.json`` /
``once_sart.json`` ⟷ ``sonra_*.json``). Sayılar üründen İTHAL EDİLMEZ;
koşum çıktısından gelir.

Ters-mutasyon tablosu: ``docs/scofield/raw/OH/D17/app-api/a1/mutasyon.py``
(her onarım geçici olarak geri alınır, ilgili sınıf KIRMIZI olmalı).
"""

import ast
import contextlib
import io
import os
import warnings

import pytest

warnings.filterwarnings('ignore')

_APP_PY = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), 'hrma', 'app.py')


@pytest.fixture(scope='module')
def client():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


def _post(client, yol, govde):
    return _sessiz(client.post, yol, json=govde)


#: Ölçümlerin hepsinde kullanılan hibrit taban gövde (``once_p16.json``).
HIBRIT = {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
          'chamber_pressure': 20.0, 'fuel_type': 'htpb',
          'oxidizer_type': 'n2o'}


def _hibrit(**ek):
    y = dict(HIBRIT)
    y.update(ek)
    return y


def _yapraklar(o, p=''):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _yapraklar(v, p + '/' + str(k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _yapraklar(v, p + '/%d' % i)
    else:
        yield p, o


def _alanlar(j):
    return {k.get('field') for k in (j.get('invalid_fields') or [])
            if isinstance(k, dict)}


def _neden(j, alan):
    for k in (j.get('invalid_fields') or []):
        if isinstance(k, dict) and k.get('field') == alan:
            return k.get('reason')
    return None


# ---------------------------------------------------------------------------
# P16B1-09 — MANTIKSAL DEĞER SAYISAL ALANDA SAYI DEĞİLDİR
# ---------------------------------------------------------------------------
class TestP16B109BoolSizmasi:
    """``of_ratio``/``expansion_ratio`` = ``true`` -> HTTP 200 idi.

    ÖLÇÜLDÜ (``once_p16.json``, taban ``2426b4d``): kardeş alanlar
    (``chamber_pressure``, ``thrust``, ``burn_time``,
    ``chamber_diameter_input``) aynı gövdede ZATEN 400 alıyordu; yani
    kusur bir ASİMETRİYDİ. ``expansion_ratio = true`` ayrıca yanıt
    ağacının üç ayrı yerinde JSON mantıksal değeri olarak yayımlanıyor
    (``"expansion_ratio": true``) ve çıkış çapını boğaz çapına
    EŞİTLİYORDU (23,5108 mm = 23,5108 mm — lülesiz motor).
    """

    @pytest.mark.parametrize('alan', ['of_ratio', 'expansion_ratio'])
    def test_true_adli_400_alir(self, client, alan):
        r = _post(client, '/calculate', _hibrit(**{alan: True}))
        assert r.status_code == 400
        j = r.get_json()
        assert alan in _alanlar(j)
        # ÖH D32 fix-35d / OH-D31-10: bayrak artık KENDİ adıyla düşüyor
        # (kardeş kapı ``_tasarim_hedefi_kapisi`` bu adı zaten kullanıyordu).
        # Kalemin iddiası aynen duruyor: ``true`` HTTP 200 ALAMAZ.
        assert _neden(j, alan) == 'boolean_is_not_a_number'

    @pytest.mark.parametrize('alan', ['of_ratio', 'expansion_ratio',
                                      'l_star', 'thrust_coefficient',
                                      'regression_n', 'fuel_density'])
    def test_bool_hicbir_bagli_sayisal_alanda_gecmez(self, client, alan):
        r = _post(client, '/calculate', _hibrit(**{alan: True}))
        assert r.status_code == 400, alan

    def test_mantiksal_deger_yanitta_sayi_diye_yayimlanmaz(self, client):
        """``"expansion_ratio": true`` yaprağı bir daha üretilemez."""
        r = _post(client, '/calculate', _hibrit(expansion_ratio=True))
        j = r.get_json() or {}
        bool_yapraklar = [p for p, v in _yapraklar(j)
                          if p.endswith('expansion_ratio')
                          and isinstance(v, bool)]
        assert bool_yapraklar == []

    def test_gecerli_govde_hala_200(self, client):
        assert _post(client, '/calculate', _hibrit()).status_code == 200

    def test_kapi_kendi_esigini_yazmaz(self):
        """Kapı deponun kendi kümelerinden okur; sayı ikinci kez yazılmaz.

        ÖK-18 / CLAUDE.md kural 11: ``/calculate``in girdi sözleşmesi
        bloğunda hiçbir sayısal sabit bulunmamalı; işaret sözleşmesi
        ``PARAMETRIC_*`` kümelerinden gelir.
        """
        agac = ast.parse(open(_APP_PY, encoding='utf-8').read())
        hedef = None
        for d in ast.walk(agac):
            if isinstance(d, ast.FunctionDef) and d.name == 'calculate':
                hedef = d
                break
        assert hedef is not None
        kaynak = ast.dump(hedef)
        for ad in ('PARAMETRIC_POSITIVE_PARAMS',
                   'PARAMETRIC_NON_NEGATIVE_PARAMS',
                   'PARAMETRIC_WIRED_PARAMS'):
            assert ad in kaynak, ad


# ---------------------------------------------------------------------------
# P16B1-08 — expansion_ratio bandı
# ---------------------------------------------------------------------------
class TestP16B108GenislemeOraniBandi:
    """ÖLÇÜLDÜ (``once_p16.json``): ``expansion_ratio`` bandı YOKTU.

    ``-4`` ve ``0`` sessizce düşüp yerine çözücünün 3,818742260282583'ü
    geçiyordu (kullanıcı bunu yanıtın hiçbir yerinden öğrenemiyordu);
    ``1e9`` ise HTTP 200 ile ``exit_diameter = 701,360 m`` yayımlıyordu —
    ürünün kendi tablosu (``motor_validator.limits['exit_diameter']``)
    5,0 m diyor.
    """

    def test_negatif_epsilon_adli_400(self, client):
        r = _post(client, '/calculate', _hibrit(expansion_ratio=-4.0))
        assert r.status_code == 400
        j = r.get_json()
        assert 'expansion_ratio' in _alanlar(j)
        assert _neden(j, 'expansion_ratio') == 'must_be_non_negative'

    def test_1e9_cizilemeyecek_cikis_capi_uretmez(self, client):
        r = _post(client, '/calculate', _hibrit(expansion_ratio=1e9))
        assert r.status_code == 400
        j = r.get_json()
        kayit = [k for k in j['invalid_fields']
                 if k.get('field') == 'exit_diameter']
        assert kayit, j['invalid_fields']
        assert kayit[0]['derived'] is True
        # Bant ÜRÜNÜN kendi tablosundan gelir, testte yazılmaz.
        from hrma.validation.motor_validation import motor_validator
        # ÖH D27 a2 / OH-D25-23 — ad kanona çevrildi; okunan sayı aynı.
        assert kayit[0]['accepted_range'][1] == \
            motor_validator.limits['exit_diameter']['max']

    def test_sifir_epsilon_artik_sessiz_degil(self, client):
        """``ε = 0`` deponun sözleşmesinde "otomatik" demek — ama söylenir."""
        r = _post(client, '/calculate', _hibrit(expansion_ratio=0.0))
        assert r.status_code == 200
        beyanlar = r.get_json().get('inputs_not_used') or []
        alanlar = {b.get('field') for b in beyanlar}
        assert 'expansion_ratio' in alanlar, beyanlar

    def test_kullanilan_epsilon_beyan_uretmez(self, client):
        """ε gerçekten kullanıldıysa gövde bit-aynı kalır (çapa korunur)."""
        r = _post(client, '/calculate', _hibrit(expansion_ratio=8.0))
        assert r.status_code == 200
        beyanlar = r.get_json().get('inputs_not_used') or []
        assert 'expansion_ratio' not in {b.get('field') for b in beyanlar}

    def test_turetilen_geometri_demeti_bandi_yeniden_yazmaz(self):
        """Demet adlardan ibarettir; eşik ``motor_validator.limits``ten."""
        import hrma.app as happ
        from hrma.validation.motor_validation import motor_validator
        for ad in happ._COZULEN_GEOMETRI_ALANLARI:
            assert ad in motor_validator.limits, ad
        assert 'exit_diameter' in happ._COZULEN_GEOMETRI_ALANLARI


# ---------------------------------------------------------------------------
# P16B1-07 — çürütüldü, ama kapanış çivilenir
# ---------------------------------------------------------------------------
class TestP16B107OdaCapiUstSiniri:
    """Başlık ÇÜRÜTÜLDÜ: ``chamber_diameter_input = 1e9`` bugün 400.

    Bekçi YOKTU (defterde kalem açıktı). ÖLÇÜLDÜ (``once_p16.json``,
    taban ``2426b4d``): 5001 / 1e5 / 1e6 / 1e9 mm'nin DÖRDÜ de adlı 400
    alıyor, 100 mm 200 alıyor. Kapanış geri dönebilirdi; artık dönemez.
    """

    @pytest.mark.parametrize('mm', [5001.0, 1e5, 1e6, 1e9])
    def test_bant_disi_oda_capi_adli_400(self, client, mm):
        r = _post(client, '/calculate',
                  _hibrit(chamber_diameter_input=mm))
        assert r.status_code == 400
        assert 'chamber_diameter_input' in _alanlar(r.get_json())

    def test_bant_ici_oda_capi_200(self, client):
        r = _post(client, '/calculate',
                  _hibrit(chamber_diameter_input=100.0))
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# P7B1-04 (Fable-D15 ŞART) — ölü blok kaldırıldı, önermesi bekçiye bağlandı
# ---------------------------------------------------------------------------
class TestP7B104OluBlok:
    """Silinen yedek bloğun DAYANDIĞI önerme artık burada ölçülür.

    ÖLÇÜLDÜ (``once_sart.json``, taban ``2426b4d``): altı gövdenin
    altısında da ``motor.gas_constant`` DOLU (325,8155166501117) ve
    ``gas_constant_basis`` yaprak sayısı **0** — yani yedek dal hiç
    girilmiyor, künyesi hiçbir kullanıcıya ulaşmıyordu.
    """

    def test_cozucu_kendi_R_sini_yayimliyor(self, client):
        j = _post(client, '/calculate', _hibrit()).get_json()
        R = (j.get('motor') or {}).get('gas_constant')
        assert isinstance(R, (int, float)) and not isinstance(R, bool)
        assert R > 0

    @pytest.mark.parametrize('alan,deger', [('gas_constant', 250.0),
                                            ('gamma', 1.4)])
    def test_beyan_atesliyor(self, client, alan, deger):
        j = _post(client, '/calculate', _hibrit(**{alan: deger})).get_json()
        beyanlar = j.get('inputs_not_used') or []
        kayit = [b for b in beyanlar if b.get('field') == alan]
        assert kayit, beyanlar
        assert kayit[0]['submitted'] == pytest.approx(deger)
        assert kayit[0]['used_by_model'] != pytest.approx(deger)

    def test_olu_yedek_geri_gelmedi(self):
        """``gas_constant_basis`` ürün kodunda ÇALIŞAN bir ifade değildir."""
        agac = ast.parse(open(_APP_PY, encoding='utf-8').read())
        for d in ast.walk(agac):
            if isinstance(d, ast.Constant) and isinstance(d.value, str):
                assert 'gas_constant_basis' not in d.value


# ---------------------------------------------------------------------------
# P7B1-09 (Fable-D15 ŞART) — M <= 10 bandının GEREKÇESİ karar metninde
# ---------------------------------------------------------------------------
SIXDOF = {'thrust': 1e9, 'burn_time': 10, 'dry_mass': 20,
          'propellant_mass': 10, 'body_diameter': 0.1, 'body_length': 2.0}


class TestP7B109BandGerekcesi:
    """ÖLÇÜLDÜ (``once_sart.json``): karar metni bandı SÖYLÜYOR ama
    sayının NEREDEN geldiğini söylemiyordu (``basis_ackeret_gerekce``
    False). Gerekçe yalnız kaynak kodu yorumundaydı — kullanıcı
    ``M <= 10``ün neden 10 olduğunu hiçbir kanaldan göremiyordu.
    """

    def test_karar_metni_bandin_dayanagini_soyluyor(self, client):
        r = _post(client, '/api/six-dof-analysis', SIXDOF)
        assert r.status_code == 200
        j = r.get_json() or {}
        ozet = j.get('summary') if isinstance(j.get('summary'), dict) else j
        metin = ozet.get('aero_model_basis') or ''
        assert ozet.get('aero_model_out_of_band') is True
        assert 'Ackeret' in metin
        assert 'twice' in metin
        # M ~ 5 sayısı METİNDE İKİNCİ KEZ YAZILMAZ; banttan türetilir.
        import hrma.app as happ
        assert f'{happ._SIXDOF_AERO_MACH_LIMIT / 2.0:g}' in metin
        assert f'{happ._SIXDOF_AERO_MACH_LIMIT:g}' in metin

    def test_hukum_hala_geri_cekiliyor(self, client):
        j = _post(client, '/api/six-dof-analysis', SIXDOF).get_json() or {}
        ozet = j.get('summary') if isinstance(j.get('summary'), dict) else j
        for hukum in ('apogee', 'apogee_time', 'stable'):
            assert ozet.get(hukum) is None, hukum

    def test_gerekce_kaynak_kodunda_sayi_kopyalamiyor(self):
        """Karar metninde ``5`` ya da ``10`` düz sabit olarak geçmez."""
        kaynak = open(_APP_PY, encoding='utf-8').read()
        i = kaynak.find("'Where the band comes from:")
        assert i > 0
        blok = kaynak[i:i + 900]
        assert '_SIXDOF_AERO_MACH_LIMIT / 2.0' in blok
        assert 'M ~ 5' not in blok


# ---------------------------------------------------------------------------
# P7B3-06 (Fable-D15 ŞART) — çizilmeyen alan ADIYLA beyan edilir
# ---------------------------------------------------------------------------
TAM_GEO = {'chamber_diameter': 0.1, 'chamber_length': 0.3,
           'port_diameter_initial': 0.03, 'throat_diameter': 0.02,
           'exit_diameter': 0.08}


class TestP7B306CizilmeyenAlan:
    """ÖLÇÜLDÜ (``once_sart.json``, ``P7B3-06``): ``port_diameter_final``
    yok / 0,05 / 0,09 / 0,50 / true / -0,05 olarak altı kez süpürüldü —
    altı yanıt da 426.210 bayt ve BAYT ÖZDEŞ. Yani uç bu alana bir
    varsayılan UYGULAMIYOR, alanı hiç okumuyor; ŞART'ın öngördüğü
    ``defaults_applied`` beyanı yazılsaydı künye ikinci kez yalan söylerdi.
    Doğru beyan: gönderildi, OKUNMADI.
    """

    def test_gonderilen_ama_cizilmeyen_alan_beyan_ediliyor(self, client):
        md = dict(TAM_GEO, port_diameter_final=0.05)
        r = _post(client, '/api/generate-3d', {'motor_data': md})
        assert r.status_code == 200
        beyanlar = r.get_json().get('inputs_not_used') or []
        kayit = [b for b in beyanlar
                 if b.get('field') == 'port_diameter_final']
        assert kayit, r.get_json().keys()
        assert kayit[0]['reason'] == 'field_not_read'
        # Beyan uydurma değil: gerçekten okunan alanları ADIYLA sayar.
        import hrma.app as happ
        for ad in happ._3D_REQUIRED_GEOMETRY_FIELDS:
            assert ad in kayit[0]['message']

    def test_alan_gonderilmezse_govde_bit_ayni(self, client):
        r = _post(client, '/api/generate-3d', {'motor_data': dict(TAM_GEO)})
        assert r.status_code == 200
        assert 'inputs_not_used' not in (r.get_json() or {})

    def test_beyan_cizimi_degistirmiyor(self, client):
        """Beyan bir ÇÖZÜM değil: sahne aynı kalmalı (ölçüm korunur)."""
        a = _post(client, '/api/generate-3d',
                  {'motor_data': dict(TAM_GEO)}).get_json()['plot_data']
        b = _post(client, '/api/generate-3d',
                  {'motor_data': dict(TAM_GEO, port_diameter_final=0.5)}
                  ).get_json()['plot_data']
        assert a == b

    def test_bos_govde_hala_reddediliyor(self, client):
        """D15 a2 onarımının canlılığı (ŞART denetimi, kural 27.1)."""
        r = _post(client, '/api/generate-3d', {})
        assert r.status_code == 422
        j = r.get_json()
        assert j['status'] == 'incomplete_geometry'
        assert set(j['missing_fields']) == set(j['required_fields'])


# ---------------------------------------------------------------------------
# P13B1-02 (D16 DEVİR, birinci yarı) — testlerde HİÇ çağrılmayan ürün uçları
# ---------------------------------------------------------------------------
class TestP13B102CagrilmayanUclar:
    """ÖLÇÜLDÜ (``once_p13.json``, taban ``2426b4d``): ``hrma/app.py``de
    98 rota var ve **10'unun yolu ``tests/`` ağacının hiçbir dosyasında
    geçmiyordu** (defterdeki "14 uç" sayısı aradaki dalgalarda düşmüş).
    Bu sınıf o onunu ilk kez çağırır; iddialar ``once_p13_uclar.json``
    koşumundan gelir, üründen İTHAL EDİLMEZ.

    ``/api/update/open-download`` KASITLI olarak çağrılmaz — sistem
    tarayıcısını açan yan etkili bir uçtur; yalnız METOT sözleşmesi
    (GET -> 405) ölçülür, gövdesi hiç çalıştırılmaz.
    """

    def test_changelog_surum_listesi_dondurur(self, client):
        r = _sessiz(client.get, '/api/changelog')
        assert r.status_code == 200
        assert 'versions' in (r.get_json() or {})

    def test_kimya_veritabani_tur_sayisini_beyan_eder(self, client):
        r = _sessiz(client.get, '/api/chemical-database')
        assert r.status_code == 200
        j = r.get_json()
        assert j['status'] == 'success'
        # Sayı testte YAZILMAZ: envanterin kendi iki alanı tutarlı olmalı.
        assert j['total_species'] == len(j['available_species'])

    # --- ÖH D27 a4 / P7B4-12 · BEKÇİ ÇEVRİLDİ (gerekçe) ---------------
    # İDDİA DEĞİŞMEDİ: çözülemeyen tür için sayı uydurulmaz (fail-closed).
    # DEĞİŞEN, o reddin KODUDUR. Bu test iki AYRI durumu tek koda
    # bağlıyordu ve böylece bir kusuru donduruyordu: ``{}`` ve
    # ``{'species': 'H2O'}`` gövdelerinde ``species_name`` alanı HİÇ
    # GÖNDERİLMEMİŞTİR — kullanıcının SORMADIĞI bir türün "bulunamadığını"
    # söylemek yanlıştır ve yanıt hangi alanın doldurulacağını da
    # söylemiyordu (ölçüm: ``a4/once.json`` K2, üç vakada da 404, gövdede
    # alan adı yok).
    #
    # Ayrım artık ucun kendi sözleşmesindedir: alan YOK -> 422 + alan adı,
    # alan VAR ama tür tanınmıyor -> 404 (gerçekten "bulunamadı"). 404 kolu
    # KALDIRILMADI, gerçek bir tanınmayan adla ölçülür.
    @pytest.mark.parametrize('govde', [{}, {'species': 'H2O'},
                                       {'species_name': ''},
                                       {'species_name': None}])
    def test_tur_adi_verilmediyse_adli_422(self, client, govde):
        """Sayı uydurulmaz; eksik alan ADIYLA reddedilir (fail-closed)."""
        r = _post(client, '/api/chemical-species', govde)
        assert r.status_code == 422
        j = r.get_json() or {}
        assert j.get('status') == 'error'
        assert j.get('missing_fields') == ['species_name']

    @pytest.mark.parametrize('ad', ['peynir', 'Xx9'])
    def test_kimya_turu_cozulemezse_adli_404(self, client, ad):
        """Çözülemeyen tür için sayı uydurulmaz (fail-closed)."""
        r = _post(client, '/api/chemical-species', {'species_name': ad})
        assert r.status_code == 404
        assert (r.get_json() or {}).get('status') == 'error'

    def test_kilavuz_durumu_iki_alanli(self, client):
        r = _sessiz(client.get, '/api/user-guide/status')
        assert r.status_code == 200
        j = r.get_json()
        assert set(j) == {'available', 'url'}
        # ``available`` DİL BAŞINA sözlüktür; kapsam ürünün kendi
        # ``USER_GUIDE_FILES`` envanterinden gelir, testte yazılmaz.
        import hrma.app as happ
        assert set(j['available']) == set(happ.USER_GUIDE_FILES)
        assert all(isinstance(v, bool) for v in j['available'].values())

    def test_basit_saglik_ucu_ayakta(self, client):
        assert _sessiz(client.get, '/test-simple').status_code == 200

    def test_bulunmayan_is_kimligi_404(self, client):
        r = _sessiz(client.get, '/api/jobs/bulunmayan-is')
        assert r.status_code == 404
        assert (r.get_json() or {}).get('status') == 'error'

    def test_detayli_cad_bos_govdeyi_adiyla_reddediyor(self, client):
        r = _post(client, '/api/detailed-cad/hybrid', {})
        assert r.status_code == 422
        assert 'required_any_of' in (r.get_json() or {})

    def test_grafik_pdf_bos_govdeyi_reddediyor(self, client):
        r = _post(client, '/api/export-chart-pdf', {})
        assert r.status_code == 400

    def test_indirme_ucu_metot_sozlesmesi(self, client):
        """Yan etkili uç ÇALIŞTIRILMADAN sözleşmesi ölçülür."""
        r = _sessiz(client.get, '/api/update/open-download')
        assert r.status_code == 405
        assert 'POST' in (r.get_json() or {}).get('allowed_methods', [])

    def test_pdf_raporu_bos_govdeden_uretilmez(self, client):
        """BOŞ gövdeden motor analiz raporu üretilmez.

        ÖH D18 / ihracat a1 — XFAIL ÇEVRİLDİ. D17'de bu bekçi
        ``xfail(strict=True)`` idi: kusur ÖLÇÜLMÜŞ ama uç ihracat
        kulvarının sahasında olduğu için o dalgada onarılamamıştı ve
        bekçi "kusur giderildiğinde XPASS(strict) ile kırmızıya dönsün"
        diye bilerek öyle bırakılmıştı. D18/ihracat a1'de
        ``/api/export-pdf/<tip>`` ucuna ``no_motor_data`` kapısı kondu
        (ölçüm: ``docs/scofield/raw/OH/D18/ihracat/a1/{once,sonra}.json``
        E bölümü; boş gövde 200 + 5.397-6.351 B PDF -> 422). İşaret
        kaldırıldı, iddia AYNEN korundu.
        """
        r = _post(client, '/api/export-pdf/analysis', {})
        assert r.status_code >= 400
