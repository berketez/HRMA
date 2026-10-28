"""ÖH Dalga-15 · kulvar **app-api** · aşama 2 — onarım bekçileri.

Her sınıf bir defter kalemine bağlıdır ve iddiası ÖLÇÜLMÜŞ vakalardan
kurulur (``docs/scofield/raw/OH/D15/app-api/a2/once.json`` ⟷ ``sonra.json``).
Sayılar üründen İTHAL EDİLMEZ; koşum çıktısından gelir.

Ters-mutasyon tablosu: ``docs/scofield/raw/OH/D15/app-api/a2/mutasyon.py``
(her onarım geçici olarak geri alınır, ilgili sınıf KIRMIZI olmalı).
"""

import contextlib
import glob
import io
import json
import os
import shutil
import tempfile
import warnings

import pytest

from hrma.engines.solid_rocket_engine import SOLID_DEFAULT_GEOMETRY_MM

warnings.filterwarnings('ignore')


# ---------------------------------------------------------------------------
# Ortak fikstürler
# ---------------------------------------------------------------------------
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


def gonder(client, yol, govde):
    yanit = _sessiz(client.post, yol, json=govde)
    try:
        return yanit.status_code, (yanit.get_json() or {})
    except Exception:  # pragma: no cover
        return yanit.status_code, {}


#: ``/calculate_liquid``in beş zorunlu alanı (eksikse 422 ``incomplete_input``
#: gelir ve sınanan kapıya HİÇ ulaşılmaz).
SIVI = {'thrust': 10000.0, 'chamber_pressure': 100.0, 'mixture_ratio': 2.5,
        'fuel_type': 'rp1', 'oxidizer_type': 'lox'}

#: ``/calculate_solid`` geometri kipi (``B2-repro-14.py`` gövdesi birebir).
# v3.0.1 T-ÇAPA-B: eski çekirdek 30 mm @ 40 bar port boğulan motordu
# (A_p/A_t 0,947); K-A kapısından beri 422. Konu port değil: geometri
# tek tanım SOLID_DEFAULT_GEOMETRY_MM'den (kopyalanmaz).
KATI = {'chamber_pressure': 40, 'propellant_type': 'apcp',
        **SOLID_DEFAULT_GEOMETRY_MM}


# ===========================================================================
# P7B2-08 — tanınmayan cooling_type sessizce "soğutmasız" fiziğe düşmez
# ===========================================================================
class TestP7B208SogutmaTipiKapisi:
    """ÖLÇÜLDÜ (once.json): ``'regenerativ'`` (tek harf eksik) HTTP 200 +
    ΔP 1,4780 -> 0 bar, T_cold 350 -> 800 K, ``regenerative`` tabanına göre
    571 yaprak farklı, künye "Regenerativ". Yön emniyetsiz: ceket ΔP'si
    sıfırlandığı için pompa basma basıncı DÜŞÜK boyutlandırılıyor.
    """

    #: Ölçülen tanınan beş seçenek (hepsi ayrı sayı üretiyor).
    TANINAN = ('regenerative', 'ablative', 'film_cooling', 'radiative',
               'dump_cooling')
    #: Ölçülen tanınmayan değerler (üçü de aynı "soğutmasız" dala düşüyordu).
    TANINMAYAN = ('regenerativ', 'banana', 'film')

    @pytest.mark.parametrize('ct', TANINMAYAN)
    def test_taninmayan_deger_422_ve_alan_adli(self, client, ct):
        kod, govde = gonder(client, '/calculate_liquid',
                            dict(SIVI, cooling_type=ct))
        assert kod == 422, (
            f'{ct!r} tanınmayan soğutma tipidir ve fail-closed reddedilmeliydi; '
            f'uç HTTP {kod} döndü: {str(govde)[:200]}')
        assert govde.get('error') == 'unsupported_cooling_type', govde
        alanlar = govde.get('invalid_fields') or []
        assert alanlar and alanlar[0].get('field') == 'cooling_type', govde
        assert alanlar[0].get('allowed_values'), (
            'ret, kabul edilen değerleri söylemiyor')

    @pytest.mark.parametrize('ct', TANINMAYAN)
    def test_reddedilen_istek_TASARIM_URETMEZ(self, client, ct):
        """Fail-closed: gövdede soğutma sayısı KALMAZ."""
        _, govde = gonder(client, '/calculate_liquid',
                          dict(SIVI, cooling_type=ct))
        ham = json.dumps(govde)
        assert 'cooling_system' not in ham and 'thermal_protection' not in ham, (
            f'{ct!r}: reddedilen istekte soğutma tasarımı yayımlandı')

    @pytest.mark.parametrize('ct', TANINAN)
    def test_taninan_deger_gecer(self, client, ct):
        kod, _ = gonder(client, '/calculate_liquid',
                        dict(SIVI, cooling_type=ct))
        assert kod == 200, f'{ct!r} ürünün kendi seçeneğidir; HTTP {kod}'

    @pytest.mark.parametrize('ham', (None, ''))
    def test_verilmedi_varsayilana_duser(self, client, ham):
        """``None``/boş dize "gönderilmedi"dir (depo geneli input_guard)."""
        kod, _ = gonder(client, '/calculate_liquid',
                        dict(SIVI, cooling_type=ham))
        assert kod == 200, f'{ham!r} gönderilmemiş sayılmalıydı; HTTP {kod}'

    def test_beyaz_liste_UCTA_YAZILI_DEGIL(self):
        """Tek kaynak: liste motor modülünden ithal edilir, kopyalanmaz."""
        import ast
        import inspect
        from hrma import app as app_modulu
        kaynak = inspect.getsource(app_modulu.calculate_liquid)
        agac = ast.parse(kaynak.lstrip())
        dizeler = [d.value for d in ast.walk(agac)
                   if isinstance(d, ast.Constant) and isinstance(d.value, str)]
        for ct in ('ablative', 'radiative', 'film_cooling', 'dump_cooling'):
            assert ct not in dizeler, (
                f'{ct!r} uç gövdesine YAZILMIŞ — beyaz listenin ikinci kopyası')


# ===========================================================================
# P7B2-09 — tank basıncı: ret ALANI adlandırır, kabul edilen değer BEYAN edilir
# ===========================================================================
class TestP7B209TankBasinci:
    """ÖLÇÜLDÜ (once.json): ``tank_pressure=3`` -> 400 "must be greater than
    chamber pressure (100 bar)" iken AYNI koşumun çözücüsü
    ``detailed_feed_system.tank_pressure_bar = 3,0`` yayımlıyor; kabul edilen
    116 ⟷ 200 bar yanıtları arasında değişen yaprak sayısı **0** ve
    ``unwired_inputs``te ``tank_pressure`` geçiş sayısı **0**.
    """

    # ÖH D27 / OH-D26-12 — İKİ BEKÇİ ÇEVRİLDİ (gerekçe aşağıda).
    # Bu sınıfın iki testi de gövdeye ÇEVRİM yazmıyordu, yani uç
    # turbopompalı varsayılana düşüyordu ve sınıf kusuru KORUYORDU:
    #   * birincisi "3 bar tank -> 400" davranışını kilitliyordu; oysa
    #     turbopompalı çevrimde 3 bar tank NORMALDİR (çözücünün kendisi
    #     2,768 bar yayımlıyor), ret gerekçesi ("hazne basıncından büyük
    #     olmalı") yanlış bir önermeye dayanıyordu;
    #   * ikincisi "okunmayan alan KABUL edilir, yalnız beyan edilir"
    #     davranışını kilitliyordu; beyan ÇÖZÜM DEĞİLDİR (Doktrin 1) ve
    #     ölçüm gösterdi ki 116 ⟷ 200 bar arasında değişen yaprak sayısı 0.
    # Onarımdan sonra turbopompalı çevrimde alan ADIYLA reddediliyor
    # (422 ``tank_pressure_not_read_in_turbopump_cycle`` + use_instead), ve
    # kapının ESKİ önermesi yalnız basınç beslemeli çevrimde yaşıyor.
    # İki test de bu iki eksene bölündü: hangi çevrimde hangi hüküm.

    def test_turbopompali_cevrimde_alan_ADIYLA_reddedilir(self, client):
        """Okunmayan alan sessizce yutulmaz: 422 + use_instead."""
        for deger in (3, 45, 200):
            kod, govde = gonder(client, '/calculate_liquid',
                                dict(SIVI, tank_pressure=deger))
            assert kod == 422, (
                f'tank_pressure={deger}: turbopompalı çevrimde bu alan '
                f'okunmuyor, adıyla reddedilmeliydi; HTTP {kod}')
            assert govde.get('error') == (
                'tank_pressure_not_read_in_turbopump_cycle'), govde
            alanlar = govde.get('invalid_fields') or []
            assert alanlar and alanlar[0].get('field') == 'tank_pressure', govde
            assert alanlar[0].get('use_instead') == 'feed_pressure', alanlar[0]
            not_metni = str(alanlar[0].get('note', '')).lower()
            assert 'detailed_feed_system' in not_metni, (
                'ret, çözücünün KENDİ tank basıncını ayrı bir büyüklük '
                f'olarak anmıyor: {alanlar[0]!r}')
            # FAIL-CLOSED: reddedilen istekte tasarım yayımlanmaz.
            for anahtar in ('motor_geometry', 'performance', 'plots'):
                assert anahtar not in govde, (
                    f'reddedilen istekte {anahtar} var')

    def test_basinc_beslemeli_cevrimde_dP_kapisi_YASIYOR(self, client):
        """Tank gerçekten enjektörü besliyorsa eski hüküm aynen durur."""
        kod, govde = gonder(client, '/calculate_liquid',
                            dict(SIVI, engine_cycle='pressure_fed',
                                 tank_pressure=3))
        assert kod == 400, f'ΔP kapısı 400 vermeliydi; HTTP {kod}'
        alanlar = govde.get('invalid_fields') or []
        assert alanlar and alanlar[0].get('field') == 'tank_pressure', govde
        not_metni = str(alanlar[0].get('note', '')).lower()
        assert 'detailed_feed_system' in not_metni, (
            'ret, çözücünün KENDİ tank basıncını ayrı bir büyüklük olarak '
            f'anmıyor: {alanlar[0]!r}')
        # Sağlıklı değer basınç beslemeli çevrimde GEÇER (kapsam daralmadı).
        # V301/L-A (SV-03): çözücü basınç beslemede tankı feed_pressure'dan
        # okur; yalnız tank_pressure gönderen gövde 3 bar yedek tankla
        # tasarım yayımlıyordu ve artık 422 alıyor. Sağlıklı vaka aynı
        # basıncı iki alanda da verir (ölçüldü: 200, marj 76,25 bar).
        kod2, _ = gonder(client, '/calculate_liquid',
                         dict(SIVI, engine_cycle='pressure_fed',
                              tank_pressure=200, feed_pressure=200))
        assert kod2 == 200, f'sağlıklı basınç beslemeli vaka; HTTP {kod2}'

    def test_gonderilmediginde_beyan_YOK(self, client):
        """Sağlıklı gövde bit-aynı kalır — beyan yalnız gönderilince çıkar."""
        kod, govde = gonder(client, '/calculate_liquid', dict(SIVI))
        assert kod == 200
        adlar = {k.get('field') for k in (govde.get('inputs_not_used') or [])
                 if isinstance(k, dict)}
        assert 'tank_pressure' not in adlar


# ===========================================================================
# P7B2-15 — test_altitude ⟷ atm_pressure çakışması
# ===========================================================================
class TestP7B215OrtamBasinciCakismasi:
    """ÖLÇÜLDÜ (once.json): ``test_altitude=10000`` + ``atm_pressure=101,325``
    HTTP 200 ve ``ambient_pressure = 1,01325 bar`` (10 km'nin gerçeği
    0,26436) -> ``average_thrust`` 3064,878 N ⟷ 3457,311 N (**−%11,4**).
    Künye yine "user test_altitude / atm_pressure input" diyordu.
    """

    def test_catisan_govde_hukum_yayimlamaz(self, client):
        kod, govde = gonder(client, '/calculate_solid',
                            dict(KATI, test_altitude=10000,
                                 atm_pressure=101.325))
        assert kod == 422, (
            f'iki ayrı geri basınç istendi; hüküm yayımlanmamalıydı. HTTP {kod}')
        assert govde.get('error') == 'ambient_pressure_channel_conflict', govde
        adlar = [k.get('field') for k in (govde.get('invalid_fields') or [])]
        assert set(adlar) == {'test_altitude', 'atm_pressure'}, adlar
        assert 'nozzle_design' not in govde, 'reddedilen istekte tasarım var'

    def test_arayuzun_varsayilan_yolu_DEGISMEZ(self, client):
        """alt=0 + atm=101,325 kPa aynı basıncı söyler — çakışma değildir."""
        kod, govde = gonder(client, '/calculate_solid',
                            dict(KATI, test_altitude=0, atm_pressure=101.325))
        assert kod == 200, f'arayüzün varsayılan yolu kırıldı; HTTP {kod}'
        amb = govde['nozzle_design']['performance']['ambient_pressure']
        assert amb == pytest.approx(1.01325, rel=1e-9)

    @pytest.mark.parametrize('ek,beklenen', (
        ({'test_altitude': 3000}, 0.7010854467002587),
        ({'atm_pressure': 70.0}, 0.70),
        ({'test_altitude': 10000, 'atm_pressure': 26.436267593807633},
         0.26436267593807633),
    ))
    def test_tek_kanal_ve_TUTARLI_ciftler_gecer(self, client, ek, beklenen):
        kod, govde = gonder(client, '/calculate_solid', dict(KATI, **ek))
        assert kod == 200, f'{ek} ölçülmüş sağlıklı vakadır; HTTP {kod}'
        amb = govde['nozzle_design']['performance']['ambient_pressure']
        assert amb == pytest.approx(beklenen, rel=1e-9)


# ===========================================================================
# P7B3-01 — paket ucu ⟷ /api/export-stl kapı paritesi
# ===========================================================================
TAM_GEO = {'motor_type': 'hybrid', 'chamber_diameter': 0.1,
           'chamber_length': 0.3, 'port_diameter': 0.05,
           'throat_diameter': 0.02, 'exit_diameter': 0.04}

#: Ölçülen parite matrisi (once.json): ``eksik_port`` satırında
#: /api/export-stl 422 iken paket 200 + 4 STL + total_length 481,746 mm;
#: ``sifir_cap`` satırında paket ham 500 veriyordu.
PARITE_GOVDELERI = {
    'bos_motor_data': {},
    'yalniz_ad': {'motor_name': 'D15'},
    'eksik_port': {'motor_type': 'hybrid', 'chamber_diameter': 0.1,
                   'chamber_length': 0.3},
    'sifir_cap': dict(TAM_GEO, chamber_diameter=0),
    'tam_geometri': dict(TAM_GEO),
}


class TestP7B301PaketStlKapiParitesi:

    @pytest.mark.parametrize('ad', sorted(PARITE_GOVDELERI))
    def test_ayni_govde_ayni_karar(self, client, ad):
        md = PARITE_GOVDELERI[ad]
        kod_s, _ = gonder(client, '/api/export-stl', {'motor_data': md})
        kod_p, govde_p = gonder(
            client, '/api/generate-complete-package',
            {'motor_data': md, 'package_options': {'include_openrocket': False}})
        assert (kod_s < 400) == (kod_p < 400), (
            f'{ad}: aynı gövde, aynı üreticiler, KARŞIT hüküm — '
            f'/api/export-stl HTTP {kod_s}, paket HTTP {kod_p}')
        if kod_p >= 400:
            stl = ((govde_p.get('complete_package') or {})
                   .get('cad', {}).get('stl_files')) or []
            assert not stl, f'{ad}: reddedilen istekte STL üretilmiş'

    def test_eksik_geometri_paket_ucunda_ADLI_reddedilir(self, client):
        kod, govde = gonder(
            client, '/api/generate-complete-package',
            {'motor_data': PARITE_GOVDELERI['eksik_port'],
             'package_options': {'include_openrocket': False}})
        assert kod == 422, f'HTTP {kod}'
        assert govde.get('missing_fields') == ['port_diameter'], govde

    def test_analiz_only_paket_geometri_ISTEMEZ(self, client):
        """``include_cad=False`` yolu etkilenmez (kardeş kapının koşulu)."""
        kod, _ = gonder(
            client, '/api/generate-complete-package',
            {'motor_data': {'motor_name': 'D15', 'chamber_pressure': 20.0},
             'package_options': {'include_cad': False,
                                 'include_openrocket': False}})
        assert kod == 200, f'analiz-only paket geometri istedi; HTTP {kod}'


# ===========================================================================
# P7B3-03 — sunucu yolu sızmaz, bağlantı çalışır, disk SINIRLI
# ===========================================================================
class TestP7B303PaketDosyaKanali:
    """ÖLÇÜLDÜ (once.json): ``stl_files`` dört MUTLAK geçici yol taşıyordu
    (``/var/folders/.../T/hrma_stl_*/motor_assembly.stl``), ``GET
    /download/stl/motor_assembly.stl`` **404** veriyordu ve altı çağrı
    3.458.016 bayt kalıcı artık bırakıyordu.
    """

    @pytest.fixture(scope='class')
    def paket(self, client):
        return gonder(
            client, '/api/generate-complete-package',
            {'motor_data': dict(TAM_GEO),
             'package_options': {'include_openrocket': False}})

    def _stl(self, paket):
        kod, govde = paket
        assert kod == 200, govde
        return ((govde.get('complete_package') or {})
                .get('cad', {}).get('stl_files')) or []

    def test_gecici_dizin_yolu_ISTEMCIYE_SIZMAZ(self, paket):
        stl = self._stl(paket)
        assert stl, 'geçerli geometride STL üretilmedi'
        tmp = tempfile.gettempdir()
        sizan = [p for p in stl if isinstance(p, str) and tmp in p]
        assert not sizan, f'sunucu geçici yolu yayımlandı: {sizan[:1]}'
        assert all(str(p).startswith('/download/stl/') for p in stl), stl

    def test_yayimlanan_baglanti_GERCEKTEN_indirilir(self, client, paket):
        stl = self._stl(paket)
        yanit = _sessiz(client.get, stl[0])
        assert yanit.status_code == 200, (
            f'yayımlanan bağlantı indirilemiyor: {stl[0]} -> '
            f'HTTP {yanit.status_code}')
        assert len(yanit.get_data()) > 0

    def test_defterden_dusen_kaydin_gecici_dizini_SILINIR(self):
        """Disk sınırı: defter LRU'dur, düşen kaydın dosyası da gider."""
        from hrma import app as app_modulu
        dizin = tempfile.mkdtemp(prefix='hrma_stl_')
        yol = os.path.join(dizin, 'motor_assembly.stl')
        with open(yol, 'w', encoding='utf-8') as f:
            f.write('solid x\nendsolid x\n')
        app_modulu._register_stl_download(yol)
        assert os.path.isdir(dizin)
        try:
            for _ in range(app_modulu._STL_REGISTRY_MAX + 1):
                app_modulu._register_stl_download(
                    os.path.join(tempfile.mkdtemp(prefix='hrma_stl_'), 'x.stl'))
            assert not os.path.isdir(dizin), (
                'defterden düşen kaydın geçici dizini silinmedi — disk '
                'kullanımı sınırsız')
        finally:
            shutil.rmtree(dizin, ignore_errors=True)
            for d in glob.glob(os.path.join(tempfile.gettempdir(),
                                            'hrma_stl_*')):
                shutil.rmtree(d, ignore_errors=True)


# ===========================================================================
# P7B3-06 — /api/generate-3d geometri kapısı
# ===========================================================================
CANLI_3D_GEOMETRI = {'chamber_diameter': 0.07886006296452648,
                     'chamber_length': 0.6828995552952049,
                     'port_diameter_initial': 0.03715320136049897,
                     'throat_diameter': 0.021581375069740737,
                     'exit_diameter': 0.04217346517795156}


class TestP7B306UcBoyutGeometriKapisi:
    """ÖLÇÜLDÜ (once.json): BOŞ gövde HTTP 200 + 573.085 baytlık, dört izli,
    "3D Hybrid Rocket Motor Visualization" başlıklı tam çizim — kullanıcının
    vermediği Ø100 mm × 300 mm motor; ``defaults_applied`` YOK.
    """

    @pytest.mark.parametrize('govde', ({}, {'motor_data': {}},
                                       {'motor_data': {'motor_name': 'D15'}}))
    def test_geometrisiz_istek_CIZIM_URETMEZ(self, client, govde):
        kod, cevap = gonder(client, '/api/generate-3d', govde)
        assert kod == 422, f'{govde} -> HTTP {kod}: uydurma motor çizildi'
        assert cevap.get('status') == 'incomplete_geometry', cevap
        assert cevap.get('missing_fields'), cevap
        assert 'plot_data' not in cevap, 'reddedilen istekte çizim var'

    def test_canli_motor_sonucu_GECER(self, client):
        """Ürün yolu: ``advanced.html`` ``currentResults.motor`` gönderiyor."""
        kod, cevap = gonder(client, '/api/generate-3d',
                            {'motor_data': dict(CANLI_3D_GEOMETRI)})
        assert kod == 200, f'canlı motor sonucu reddedildi; HTTP {kod}: {cevap}'
        assert cevap.get('plot_data')

    def test_sifir_olcu_verilmedi_ile_AYNI_kefede(self, client):
        kod, cevap = gonder(
            client, '/api/generate-3d',
            {'motor_data': dict(CANLI_3D_GEOMETRI, chamber_diameter=0)})
        assert kod == 422
        assert 'chamber_diameter' in (cevap.get('missing_fields') or [])


# ===========================================================================
# P7B3-08 / -09 / -10 — itici özellikleri künyesi, birimi, kimliği
# ===========================================================================
def _itici(client, ad, tur):
    return gonder(client, '/api/get-propellant-properties',
                  {'propellant_name': ad, 'propellant_type': tur})


class TestP7B308KunyeAlanAlanDogru:
    """ÖLÇÜLDÜ (once.json), hepsi ``source='CoolProp (NIST REFPROP-based)'``
    künyesiyle: n2o viskozite 0,0002 (CoolProp bu sayıyı HİÇ üretmiyor),
    n2o yoğunluk 745,0 ⟷ 785,1040 (%5,11), lox viskozite 0,00019 ⟷
    0,000194661 (%2,39), lh2 özgül ısı 14,3 ⟷ 9722,913 (%99,85).
    """

    @pytest.mark.parametrize('ad,tur', (('n2o', 'oxidizer'),
                                        ('n2o', 'liquid_oxidizer'),
                                        ('lox', 'liquid_oxidizer'),
                                        ('lh2', 'liquid_oxidizer'),
                                        ('lh2', 'liquid_fuel')))
    def test_alan_basina_kunye_yayimlanir(self, client, ad, tur):
        kod, govde = _itici(client, ad, tur)
        assert kod == 200, govde
        kaynaklar = (govde.get('properties') or {}).get('property_sources')
        assert isinstance(kaynaklar, dict) and kaynaklar, (
            f'{ad}/{tur}: alan başına künye yok — tek künye bütün sözlüğü '
            f'örtüyor')
        for alan, deger in (govde.get('properties') or {}).items():
            if alan in ('density', 'viscosity', 'thermal_conductivity',
                        'specific_heat') and deger is not None:
                assert alan in kaynaklar, f'{ad}/{tur}: {alan} künyesiz'

    def test_yerel_deger_COOLPROP_kunyesiyle_yayimlanmaz(self, client):
        """lh2/liquid_oxidizer: özgül ısı yerel tablodan gelir."""
        kod, govde = _itici(client, 'lh2', 'liquid_oxidizer')
        assert kod == 200
        kaynaklar = (govde['properties'] or {})['property_sources']
        assert not str(kaynaklar['specific_heat']).startswith('CoolProp'), (
            'yerel tablodan gelen özgül ısı CoolProp künyesiyle yayımlanıyor')

    def test_karma_kaynakta_UST_KUNYE_coolprop_iddia_etmez(self, client):
        """n2o/oxidizer: yoğunluk CoolProp, viskozite yerel tablo."""
        kod, govde = _itici(client, 'n2o', 'oxidizer')
        assert kod == 200
        kaynaklar = (govde['properties'] or {})['property_sources']
        karma = {str(v).startswith('CoolProp') for v in kaynaklar.values()}
        if karma == {True, False}:
            assert not str(govde['source']).startswith('CoolProp'), (
                'karma kaynakta üst künye hâlâ sözlüğün TAMAMI için '
                f'CoolProp iddia ediyor: {govde["source"]!r}')

    def test_ust_kunye_yerel_tablo_ADLARINI_TASIMAZ(self, client):
        """Karma künye canlılık rozetini besleyen metindir; yerel tablo adı
        (ör. 'NIST WebBook') oraya kopyalanırsa yerel değer CANLI görünür."""
        kod, govde = _itici(client, 'n2o', 'oxidizer')
        assert kod == 200
        import re
        assert not re.search(r'pubchem|webbook|nist\.gov',
                             str(govde['source']), re.I), govde['source']


class TestP7B309OzgulIsiTekBirim:
    """ÖLÇÜLDÜ (once.json): ``lh2`` özgül ısısı ``liquid_oxidizer`` kolunda
    14,3 ⟷ ``liquid_fuel`` kolunda 9722,913 = **679,9 kat**; yanıtta ``unit``
    geçen TEK alan yoktu. Tüketici ``templates/advanced.html`` dönen sayıyı
    ``J/kg·K`` diye basıyor.
    """

    VAKALAR = (('lh2', 'liquid_oxidizer'), ('lh2', 'liquid_fuel'),
               ('rp1', 'liquid_fuel'), ('htpb', 'hybrid_fuel'))

    @pytest.mark.parametrize('ad,tur', VAKALAR)
    def test_birim_ACIKCA_yazilir(self, client, ad, tur):
        kod, govde = _itici(client, ad, tur)
        assert kod == 200
        ozellikler = govde['properties'] or {}
        if ozellikler.get('specific_heat') is None:
            pytest.skip(f'{ad}/{tur}: özgül ısı yayımlanmıyor')
        assert ozellikler.get('specific_heat_unit') == 'J/(kg*K)', (
            f'{ad}/{tur}: birim beyanı yok — aynı anahtar iki birim taşıyor')

    def test_ayni_akiskan_iki_etikette_AYNI_BUYUKLUK_MERTEBESINDE(self, client):
        """679,9 kat ayrışma ölçülmüştü; birim birleşince mertebe kapanır."""
        _, ox = _itici(client, 'lh2', 'liquid_oxidizer')
        _, fu = _itici(client, 'lh2', 'liquid_fuel')
        a = (ox['properties'] or {})['specific_heat']
        b = (fu['properties'] or {})['specific_heat']
        oran = max(a, b) / min(a, b)
        assert oran < 10.0, (
            f'aynı akışkanın özgül ısısı etikete göre {oran:.1f} kat '
            f'ayrışıyor ({a} ⟷ {b}) — birim hâlâ karışık')

    def test_yerel_deger_COOLPROP_SAYISIYLA_ezilmez(self, client):
        """Birim düzeltmesi 1000x'lik bir EZME olmamalı (T14 şartı)."""
        _, ox = _itici(client, 'lh2', 'liquid_oxidizer')
        cp = (ox['properties'] or {})['specific_heat']
        assert cp == pytest.approx(14300.0), (
            f'yerel tablo değeri (14,3 kJ/(kg·K)) korunmadı: {cp}')


class TestP7B310TaninmayanIticiAdi:
    """ÖLÇÜLDÜ (once.json): ``'ZZZ_NOT_A_PROPELLANT'`` -> HTTP 200 +
    ``source: 'Built-in propellant table'`` (o tabloda kayıt YOK).
    """

    @pytest.mark.parametrize('ad', ('ZZZ_NOT_A_PROPELLANT', 'banana', ''))
    def test_taninmayan_ad_reddedilir(self, client, ad):
        kod, govde = _itici(client, ad, 'liquid_fuel')
        assert kod == 422, f'{ad!r} -> HTTP {kod}: {str(govde)[:200]}'
        assert govde.get('error') == 'unresolved_propellant_name', govde
        alanlar = govde.get('invalid_fields') or []
        assert alanlar and alanlar[0].get('field') == 'propellant_name', govde
        assert 'properties' not in govde, 'reddedilen istekte özellik var'
        assert 'source' not in govde, (
            'reddedilen istekte HÂLÂ kaynak künyesi var — var olmayan bir '
            'tablo kaydına atıf')

    @pytest.mark.parametrize('ad,tur', (('rp1', 'liquid_fuel'),
                                        ('htpb', 'hybrid_fuel'),
                                        ('n2o4', 'oxidizer'),
                                        ('lox', 'oxidizer')))
    def test_taninan_ad_gecer(self, client, ad, tur):
        kod, govde = _itici(client, ad, tur)
        assert kod == 200, f'{ad}/{tur} ürünün kendi iticisidir; HTTP {kod}'


# ===========================================================================
# P7B3-14 / -15 — /api/regression-analysis
# ===========================================================================
#: ÖH D15 birleştirme (1 Eyl 2026) — ``/api/regression-analysis``in
#: ZORUNLU alanları (yapısal kulvar P5B4-01/-38). Sayılar S1'in kanonik
#: ölçüm gövdesinden alındı (``tests/test_z5s_govde_kapisi.py``); burada
#: yeniden SEÇİLMEZ ki iki paket aynı motoru ölçsün.
TAM_REGRESYON_GOVDESI = {'burn_time': 10.0, 'mdot_ox': 0.38,
                         'port_diameter_initial': 0.037,
                         'fuel_type': 'htpb'}


class TestP7B314OkunmayanAnahtar:
    """ÖLÇÜLDÜ (once.json): ``port_diameter`` altı ayrı değerde (0,02 / 0,05 /
    0,12 / 20 / 50 ve alan yok) çıktıyı BİREBİR aynı bırakıyordu
    (port[0]=30,0 mm, r_dot[0]=2,0629); kontrol kolu
    ``port_diameter_initial`` 0,02 -> 20,0 mm, 0,05 -> 50,0 mm.
    """

    @pytest.mark.parametrize('deger', (0.02, 0.05, 0.12, 20.0, 50.0))
    def test_okunmayan_anahtar_SESSIZCE_dusmez(self, client, deger):
        kod, govde = gonder(client, '/api/regression-analysis',
                            {'motor_data': {'port_diameter': deger,
                                            'burn_time': 10.0}})
        assert kod == 422, (
            f'port_diameter={deger} okunmuyor ve sessizce düşüyordu; '
            f'HTTP {kod}')
        assert govde.get('error') == 'unread_regression_input', govde
        kayit = (govde.get('invalid_fields') or [{}])[0]
        assert kayit.get('field') == 'port_diameter', govde
        assert kayit.get('use_instead') == 'port_diameter_initial', kayit

    @pytest.mark.parametrize('deger,beklenen', ((0.02, 20.0), (0.05, 50.0)))
    def test_OKUNAN_anahtar_gercekten_okunur(self, client, deger, beklenen):
        """Kontrol kolu — kapı doğru alanı işaret ediyor mu?

        ÖH D15 birleştirme (1 Eyl 2026): yapısal kulvar (P5B4-01/-38)
        ``burn_time`` / ``mdot_ox`` / ``fuel_type``i zorunlu kıldı, bu
        yüzden kontrol kolu artık TAM gövdeyle sorulur. Ölçülen iddia
        değişmedi: okunan ad gerçekten eğriyi sürüyor (0,02 m -> 20,0 mm,
        0,05 m -> 50,0 mm), okunmayan ad ise yukarıdaki bekçide adıyla
        reddediliyor.
        """
        kod, govde = gonder(client, '/api/regression-analysis',
                            {'motor_data': dict(TAM_REGRESYON_GOVDESI,
                                                port_diameter_initial=deger)})
        assert kod == 200, govde
        port = govde['regression_data']['port_diameter']
        assert port[0] == pytest.approx(beklenen)


class TestP7B315BosGovdeVeBeyan:
    """ÖLÇÜLDÜ (once.json): ``{}`` ve ``{'motor_data': {}}`` HTTP 200 ile
    100 noktalık tam eğri basıyordu (r_dot 2,0629 -> 1,0065; port 30,0 ->
    57,2658 mm); ``defaults_applied`` yok, ``unit``/``basis`` içeren alan
    sayısı **0**.
    """

    @pytest.mark.parametrize('govde', ({}, {'motor_data': {}},
                                       {'motor_data': {'motor_name': 'D15'}}))
    def test_egri_girdisi_TASIMAYAN_govde_egri_uretmez(self, client, govde):
        kod, cevap = gonder(client, '/api/regression-analysis', govde)
        assert kod == 422, f'{govde} -> HTTP {kod}: uydurma eğri basıldı'
        assert cevap.get('error') == 'incomplete_regression_input', cevap
        assert 'regression_data' not in cevap

    def test_kismi_govdede_VARSAYILANLAR_beyan_edilir(self, client):
        """Varsayılana düşen büyüklük ADIYLA beyan edilir (ÖK-19).

        ÖH D15 birleştirme (1 Eyl 2026): eğriyi YÖNETEN üç alan artık
        varsayılana DÜŞEMEZ — yapısal kulvarın kapısı onları zorunlu
        kıldı ve eksikse 422 verir (kardeş bekçi:
        ``test_egri_girdisi_TASIMAYAN_govde_egri_uretmez`` ile
        ``tests/test_d15_yapisal_sistem_a2.py``). Beyan ayağının konusu
        bu yüzden YÖNETMEYEN eğri alanına daraldı: ``port_diameter_final``
        gönderilmediğinde 200 dönülür ama düşüş SESSİZ KALMAZ. Kapsam
        daralması bir gevşeme değil: iki alan için "beyan et" şartı,
        "hiç kabul etme" şartıyla değiştirildi.
        """
        kod, cevap = gonder(client, '/api/regression-analysis',
                            {'motor_data': dict(TAM_REGRESYON_GOVDESI,
                                                port_diameter_initial=0.04)})
        assert kod == 200, cevap
        beyan = cevap.get('defaults_applied') or []
        adlar = {k.get('field') for k in beyan if isinstance(k, dict)}
        assert {'port_diameter_final'} <= adlar, (
            f'varsayılana düşen büyüklük beyan edilmiyor: {adlar}')
        assert not ({'burn_time', 'mdot_ox', 'port_diameter_initial'} & adlar), (
            f'kullanıcının VERDİĞİ alan varsayılan diye beyan edildi: {adlar}')
        for kayit in beyan:
            assert kayit.get('reason') == 'not_supplied', kayit
            assert kayit.get('applied_by'), kayit

    def test_YONETEN_alan_varsayilana_DUSEMEZ(self, client):
        """Beyan ayağının ikizi: yöneten alan beyanla da geçiştirilemez.

        ÖK-19 "varsayılan kalacaksa beyan ZORUNLU" der; eğriyi yöneten
        alanlarda ürün bir adım ileri gitti ve varsayılanı hiç uygulamıyor.
        Bu bekçi o kararı kilitler — biri kapıyı kaldırıp yerine beyan
        koyarsa kırmızıya döner.
        """
        for eksik in ('burn_time', 'mdot_ox', 'port_diameter_initial'):
            govde = {k: v for k, v in TAM_REGRESYON_GOVDESI.items()
                     if k != eksik}
            kod, cevap = gonder(client, '/api/regression-analysis',
                                {'motor_data': govde})
            assert kod == 422, f'{eksik} yokken eğri basıldı: {cevap}'
            assert cevap.get('error') == 'incomplete_regression_input', cevap
            assert eksik in (cevap.get('missing_fields') or []), cevap
            assert 'regression_data' not in cevap

    def test_tam_govdede_BEYAN_YOK(self, client):
        """Düşüş yoksa alan da yok — sağlıklı gövde bit-aynı kalır."""
        kod, cevap = gonder(client, '/api/regression-analysis',
                            {'motor_data': dict(TAM_REGRESYON_GOVDESI,
                                                port_diameter_final=0.052)})
        assert kod == 200, cevap
        assert 'defaults_applied' not in cevap

    def test_BIRIM_beyani_yayimlanir(self, client):
        kod, cevap = gonder(client, '/api/regression-analysis',
                            {'motor_data': dict(TAM_REGRESYON_GOVDESI,
                                                port_diameter_final=0.052)})
        assert kod == 200
        birimler = cevap['regression_data'].get('units')
        assert isinstance(birimler, dict) and birimler, (
            'yanıt ağacında tek bir birim alanı yok')
        assert birimler.get('port_diameter') == 'mm', birimler
        assert birimler.get('regression_rate') == 'mm/s', birimler

    def test_girdi_METRE_cikti_MILIMETRE_ayrimi_gorunur(self, client):
        """Aynı ad iki birim taşıyor; beyan bunu görünür kılmalı."""
        kod, cevap = gonder(client, '/api/regression-analysis',
                            {'motor_data': dict(TAM_REGRESYON_GOVDESI,
                                                mdot_ox=1.0,
                                                port_diameter_initial=0.03,
                                                port_diameter_final=0.05)})
        assert kod == 200
        port = cevap['regression_data']['port_diameter']
        assert port[0] == pytest.approx(30.0), port[0]
        assert cevap['regression_data']['units']['port_diameter'] == 'mm'
