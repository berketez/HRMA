"""ÖH Dalga-27 · app-api · aşama-3 bekçileri.

Kalemler (11): OH-B2-02, P7B4-02, OH-D26-17, OH-D26-20, H1-Y7, P13B4-05
(onarıldı) · OH-D25-09, H1-Y6, P16B1-20, OH-B1-01 (ölçümle çürütüldü —
bekçi kapanışı DONDURUR) · P15B2-01 (kısmen: envanter + devir listesi).

Ölçüm kanıtı: ``docs/scofield/raw/OH/D27/app-api/a3/once.json`` ⟷
``sonra.json``; ters-mutasyon: ``mutasyon.json``.
"""

import json
import math

import pytest


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _post(istemci, yol, govde):
    y = istemci.post(yol, json=govde)
    try:
        g = y.get_json() or {}
    except Exception:  # pragma: no cover
        g = {}
    return y.status_code, g


# ===========================================================================
# OH-B2-02 [yüksek] — /api/water-hammer buhar basıncını KABUL EDER
# ===========================================================================
SU_KOCU_HAT = {
    'line_length_m': 10.0, 'line_id_mm': 25.4, 'wall_thickness_mm': 1.5,
    'working_pressure_bar': 25.0, 'mdot_kg_s': 3.74, 'pipe_material': 'ss_304',
}
OZEL_AKISKAN = dict(SU_KOCU_HAT, fluid='my_fluid',
                    bulk_modulus_Pa=2.15e9, density_kg_m3=998.0)


class TestOHB202BuharBasinciUctanGirer:
    """Tabloda kaydı olmayan akışkanda kapı KAPATILABİLİR olmalı.

    ÖLÇÜLDÜ (``a3/once.json`` K6): ucun kaynağında ``vapor_pressure_Pa``
    adı **0** kez geçiyordu; ``my_fluid`` + ``vapor_pressure_Pa: 3169``
    isteğinde yanıt yine ``vapor_pressure_Pa=None`` ve
    ``column_separation=None`` idi. Modül katmanı parametreyi zaten kabul
    ediyordu (``WaterHammerAnalyzer.analyze`` imzası) — kanal vardı, kapı
    yoktu.
    """

    def test_gonderilen_buhar_basinci_COZUCUYE_ULASIR(self, istemci):
        kod, g = _post(istemci, '/api/water-hammer',
                       dict(OZEL_AKISKAN, vapor_pressure_Pa=3169.0))
        assert kod == 200, g
        wh = g['water_hammer']
        assert wh['vapor_pressure_Pa'] == pytest.approx(3169.0, rel=1e-12)
        assert wh['column_separation'] is True, (
            'buhar basıncı verildi ama kolon-ayrılması hükmü hâlâ '
            'kazanılmamış görünüyor')

    def test_verilmezse_davranis_BIT_AYNI(self, istemci):
        """Alan gönderilmezse çapa korunur: tabloda yoksa hüküm YOK."""
        kod, g = _post(istemci, '/api/water-hammer', dict(OZEL_AKISKAN))
        assert kod == 200
        wh = g['water_hammer']
        assert wh['vapor_pressure_Pa'] is None
        assert wh['column_separation'] is None

    def test_tablo_akiskaninda_tablo_degeri_ayakta(self, istemci):
        kod, g = _post(istemci, '/api/water-hammer',
                       dict(SU_KOCU_HAT, fluid='water'))
        assert kod == 200
        wh = g['water_hammer']
        assert wh['vapor_pressure_Pa'] == pytest.approx(2339.0, rel=1e-9)
        assert wh['column_separation'] is True
        assert wh['status'] == 'MARGINAL'

    def test_negatif_mutlak_basinc_ADIYLA_reddedilir(self, istemci):
        kod, g = _post(istemci, '/api/water-hammer',
                       dict(OZEL_AKISKAN, vapor_pressure_Pa=-1.0))
        assert kod == 422, g
        assert g['error'] == 'invalid_vapor_pressure'
        assert [k['field'] for k in g['invalid_fields']] == [
            'vapor_pressure_Pa']
        assert g['invalid_fields'][0]['reason'] == (
            'must_be_finite_and_non_negative')
        assert 'water_hammer' not in g

    @pytest.mark.parametrize('deger', [float('nan'), float('inf')])
    def test_sonlu_olmayan_deger_UST_KAPIDA_adiyla_dusuyor(self, istemci,
                                                           deger):
        """nan/inf zaten ``_json_float``ta adıyla reddediliyor (400).

        Yeni kapı onu İKİNCİ KEZ yazmaz (Doktrin 4): burada sınanan şey,
        sonlu olmayan bir buhar basıncının HİÇBİR yoldan çözücüye
        ulaşmadığı ve reddin alanı adlandırdığıdır.
        """
        kod, g = _post(istemci, '/api/water-hammer',
                       dict(OZEL_AKISKAN, vapor_pressure_Pa=deger))
        assert kod in (400, 422), g
        assert 'vapor_pressure_Pa' in json.dumps(g)
        assert 'water_hammer' not in g

    def test_uc_kaynaginda_ad_GERCEKTEN_var(self):
        """Kanalın kapısı KODDA — 'geçiyordu ama okunmuyordu' geri gelemez."""
        import inspect
        from hrma import app as _m
        kaynak = inspect.getsource(_m.water_hammer_api)
        assert kaynak.count('vapor_pressure_Pa') >= 3
        assert 'vapor_pressure_Pa=_vp_ham' in kaynak


# ===========================================================================
# P7B4-02 — /api/get-fuel-properties tanınmayan yakıtta FAIL-CLOSED
# ===========================================================================
class TestP7B402TaninmayanYakit:
    """ÖLÇÜLDÜ (``a3/once.json`` K2): ``ethanol`` ve ``peynir`` HTTP 200 +
    ``status='success'`` + ``density 810,0`` + ``formula 'C12H23'`` (RP-1)
    alıyordu. Beyan (``substituted_record``) D26 a4'te eklenmişti ve
    ölçüldü — ama beyan çözüm değildir (Doktrin 1).
    """

    @pytest.mark.parametrize('yakit', ['ethanol', 'peynir', 'zzz_yok'])
    def test_hukum_yayimlanmaz(self, istemci, yakit):
        kod, g = _post(istemci, '/api/get-fuel-properties',
                       {'fuel_type': yakit})
        assert kod == 422, g
        assert g['error'] == 'unknown_fuel'
        assert g['status'] == 'error'
        assert 'properties' not in g
        # RP-1'in imzası gövdenin HİÇBİR yerinde
        metin = json.dumps(g)
        assert 'C12H23' not in metin
        assert '810' not in metin

    def test_ret_alani_ve_kabul_edilenleri_soyler(self, istemci):
        kod, g = _post(istemci, '/api/get-fuel-properties',
                       {'fuel_type': 'ethanol'})
        assert kod == 422
        assert [k['field'] for k in g['invalid_fields']] == ['fuel_type']
        assert g['invalid_fields'][0]['reason'] == 'no_species_or_cached_record'
        from hrma.app import CACHED_FUEL_PROPERTIES
        assert g['accepted_fuel_types'] == sorted(CACHED_FUEL_PROPERTIES)

    @pytest.mark.parametrize('yakit', ['rp1', 'lh2', 'methane', 'htpb'])
    def test_MESRU_yol_daralmadi(self, istemci, yakit):
        """ÖK-22: kaydı olan yakıt hüküm almaya devam eder."""
        kod, g = _post(istemci, '/api/get-fuel-properties',
                       {'fuel_type': yakit})
        assert kod == 200, g
        assert g['status'] == 'success'
        assert g['properties'].get('substituted_record') is None


# ===========================================================================
# OH-D26-17 — CACHED_FUEL_PROPERTIES: KÜNYESİZ KAYIT YOK
# ===========================================================================
class TestOHD2617KunyeliKayit:
    """ÖLÇÜLDÜ (``a3/once.json`` K2): ürünün KENDİ varsayılan hibrit yakıtı
    ``htpb``, ``density: null`` +
    ``density_unavailable_reason='no_measured_density_record_for_this_fuel'``
    alıyordu — tabloda üç kayıt vardı ve HTPB onlardan biri değildi.
    """

    def test_htpb_kaydi_var_ve_LITERATURDEN(self):
        from hrma.app import CACHED_FUEL_PROPERTIES
        kayit = CACHED_FUEL_PROPERTIES['htpb']
        assert kayit['density'] == 920.0
        kaynak = kayit['density_reference']
        assert 'Chiaverini' in kaynak and 'AIAA' in kaynak
        assert '920' in kaynak

    def test_HER_kayit_kaynak_kunyesi_tasir(self):
        """Künyesiz kayıt yapısal olarak imkânsız."""
        from hrma.app import (CACHED_FUEL_PROPERTIES,
                              CACHED_FUEL_REQUIRED_KEYS)
        for ad, kayit in CACHED_FUEL_PROPERTIES.items():
            eksik = CACHED_FUEL_REQUIRED_KEYS - set(kayit)
            assert not eksik, f"'{ad}' kaydında eksik künye alanı: {eksik}"
            assert isinstance(kayit['density_reference'], str)
            assert len(kayit['density_reference']) > 40, ad

    def test_htpb_yogunlugu_UCTAN_kaynagiyla_yayimlanir(self, istemci):
        kod, g = _post(istemci, '/api/get-fuel-properties',
                       {'fuel_type': 'htpb'})
        assert kod == 200
        pr = g['properties']
        assert pr['density'] == 920.0
        assert pr['density_unavailable_reason'] is None
        assert 'Chiaverini' in pr['density_source']

    def test_kunye_IKI_YERDE_yazilmaz(self):
        """Doktrin 4: yayımlanan künye kaydın KENDİSİNDEN okunur."""
        import inspect
        from hrma import app as _m
        kaynak = inspect.getsource(_m._fuel_density_kunyesi)
        assert "kayit['density_reference']" in kaynak


# ===========================================================================
# OH-D26-20 — /api/flow-analysis tam fail-closed
# ===========================================================================
class TestOHD2620FlowFailClosed:
    """ÖLÇÜLDÜ (``a3/once.json`` K5): ``{}`` gövdesi HTTP 200 + tam bir
    quasi-1D çözüm + 9 ``defaults_applied`` künyesi alıyordu.
    """

    def test_bos_govde_COZULMEZ(self, istemci):
        kod, g = _post(istemci, '/api/flow-analysis', {})
        assert kod == 422, f'boş gövde hâlâ çözülüyor: {kod}'
        assert g['error'] == 'incomplete_flow_input'
        assert 'flow' not in g and 'performance' not in g

    def test_zorunlu_alti_alan_ADIYLA(self, istemci):
        from hrma.app import FLOW_REQUIRED_FIELDS
        kod, g = _post(istemci, '/api/flow-analysis', {})
        assert kod == 422
        assert len(FLOW_REQUIRED_FIELDS) == 6
        assert sorted(g['missing_fields']) == sorted(FLOW_REQUIRED_FIELDS)
        for kayit in g['invalid_fields']:
            assert kayit['reason'] == 'required_not_supplied'
            assert kayit['basis'], kayit

    def test_ODENEN_BORC_kaynakta_YAZILI(self):
        """ÖH D32 / arayuz-panel a2 (OH-D31-14) — MANDAL ÇEVRİLDİ.

        Eski hâli ``test_KALAN_BORC_kaynakta_YAZILI`` idi ve kaynakta
        "KALAN BORÇ" ibaresinin DURMASINI şart koşuyordu; borç ödenince o
        iddia kusuru (alan-alan kapının yokluğunu) koruyan bir mandala
        dönüşürdü. İddia ZAYIFLATILMADI, ters çevrildi: kapının artık
        alan-alan olduğu ve bunun gerekçesinin kaynakta durduğu sınanıyor.
        """
        import inspect
        from hrma import app as _m
        kaynak = inspect.getsource(_m.flow_analysis)
        # Kapı alan-alan: küme üstünde dönen bir yüklem, ``if not data``
        # değil.
        assert ('_flow_eksik = [ad for ad in FLOW_REQUIRED_FIELDS'
                in kaynak), 'kapı alan-alan hâlinden geri döndü'
        assert 'if not data else []' not in kaynak, (
            'yalnız boş gövdeyi kapatan eski ölçüt geri geldi')
        # Gerekçe ve devir zinciri kaynakta duruyor.
        assert 'OH-D31-14' in kaynak
        assert 'ÖK-21' in kaynak
        assert 'P7B4-06' in inspect.getsource(_m._flow_bos_deger)

    @pytest.mark.parametrize('yuk', [{'fidelity': 'fast'},
                                     {'chamber_pressure': 20.0},
                                     {'gamma': None}])
    def test_EKSIK_govde_ALAN_ADIYLA_reddedilir(self, istemci, yuk):
        """ÖH D32 / arayuz-panel a2 (OH-D31-14) — MANDAL ÇEVRİLDİ.

        Eski hâli ``test_BOS_OLMAYAN_govde_reddedilmez`` idi: boş OLMAYAN
        her gövdenin ``incomplete_flow_input`` ALMAMASINI şart koşuyordu,
        yani D27'de ölçülen iki engelin (``advanced.html``in boş alanı
        ``null`` göndermesi + ÖK-21) sürmesini kilitliyordu. İKİ ENGEL DE
        D31 / arayuz-panel a2'de kalktı (``numById`` anahtarı düşürüyor,
        ``flow_panel.js``in altı zorunlu alanı boş doğuyor), bu yüzden
        mandal çevrildi. Aynı üç gövde artık ALAN ADIYLA reddedilmelidir.
        """
        from hrma.app import FLOW_REQUIRED_FIELDS
        kod, g = _post(istemci, '/api/flow-analysis', dict(yuk))
        assert kod == 422, f'motoru tarif etmeyen gövde çözüldü: {kod}'
        assert g['error'] == 'incomplete_flow_input'
        eksik = set(g['missing_fields'])
        # Gönderilen alan eksik sayılmaz; gönderilmeyenlerin hepsi anılır.
        assert eksik == {ad for ad in FLOW_REQUIRED_FIELDS
                         if yuk.get(ad) in (None, '')}, g
        assert 'flow' not in g and 'performance' not in g

    def test_zorunlu_alan_eksikken_BEYAN_KANALI_kapali(self, istemci):
        """Beyan, kapının yerine geçemez (Doktrin 1).

        Eski hâli ``test_kismi_govdede_BEYAN_yurulukte`` idi ve kısmî
        gövdenin 200 + künye almasını şart koşuyordu — künye doğruydu ama
        uydurulan sayıyı doğru yapmıyordu. Artık zorunlu alan eksikken
        hiçbir künye üretilmez, çünkü hiçbir şey çözülmez.
        """
        kod, g = _post(istemci, '/api/flow-analysis',
                       {'chamber_pressure': 20.0, 'fidelity': 'fast'})
        assert kod == 422, g
        assert g.get('defaults_applied') is None

    def test_model_secimleri_beyanli_varsayilan_KALIR(self, istemci):
        """ÖK-19 ikinci şıkkı: yöntem seçimi künyeyle kalır.

        ÖH D32 (OH-D31-14): gövdeye ``expansion_ratio`` eklendi — lüle
        geometrisi artık uydurulmuyor (ikinci ayak). İDDİA DEĞİŞMEDİ:
        motor tam tarif edildiğinde düşen tek şey üç YÖNTEM seçimidir ve
        üçü de adıyla beyan edilir.
        """
        from hrma.app import FLOW_ANALYSIS_DEFAULTS, FLOW_REQUIRED_FIELDS
        yuk = {ad: FLOW_ANALYSIS_DEFAULTS[ad][0] for ad in FLOW_REQUIRED_FIELDS
               if ad in FLOW_ANALYSIS_DEFAULTS}
        yuk['chamber_pressure'] = 20.0
        yuk['expansion_ratio'] = 4.0
        yuk['fidelity'] = 'fast'
        kod, g = _post(istemci, '/api/flow-analysis', yuk)
        assert kod == 200, g
        beyan = sorted(k['field'] for k in (g.get('defaults_applied') or []))
        assert beyan == ['n_stations', 'separation_factor',
                         'wall_temperature']

    def test_iki_kanal_birbirini_YUTMAZ(self, istemci):
        """Boş istek: ret VAR, künye YOK. Dolu istek: künye VAR, ret YOK.

        ÖH D32 (OH-D31-14): "dolu istek" artık motoru GERÇEKTEN tarif eden
        gövdedir; eski ``{'fidelity': 'engineering'}`` gövdesi motorun
        hiçbir alanını taşımıyordu ve o yüzden 422 alır.
        """
        from hrma.app import FLOW_ANALYSIS_DEFAULTS, FLOW_REQUIRED_FIELDS
        kod, g = _post(istemci, '/api/flow-analysis', {})
        assert kod == 422
        assert g.get('defaults_applied') is None
        tam = {ad: FLOW_ANALYSIS_DEFAULTS[ad][0] for ad in FLOW_REQUIRED_FIELDS
               if ad in FLOW_ANALYSIS_DEFAULTS}
        tam.update(chamber_pressure=20.0, expansion_ratio=4.0,
                   fidelity='engineering')
        kod2, g2 = _post(istemci, '/api/flow-analysis', tam)
        assert kod2 == 200, g2
        assert g2.get('error') != 'incomplete_flow_input'
        assert g2.get('defaults_applied'), (
            'motor tarif edildi, yöntem seçimleri düştü — künye YOK')

    def test_kapinin_dayanagi_KARDES_UCTA_da_var(self):
        """Desen icat değil: /api/uncertainty-analysis aynı doktrini uygular."""
        import inspect
        from hrma import app as _m
        kaynak = inspect.getsource(_m.uncertainty_analysis)
        assert 'incomplete_uncertainty_input' in kaynak
        assert 'if not inputs:' in kaynak

    def test_saglikli_govde_HALA_cozuluyor(self, istemci):
        from hrma.app import FLOW_ANALYSIS_DEFAULTS
        yuk = {ad: v[0] for ad, v in FLOW_ANALYSIS_DEFAULTS.items()}
        yuk.update(chamber_pressure=20.0, expansion_ratio=4.0,
                   fidelity='fast')
        kod, g = _post(istemci, '/api/flow-analysis', yuk)
        assert kod == 200, g
        assert g['status'] == 'success'
        assert g.get('defaults_applied') in (None, [])


# ===========================================================================
# H1-Y7 — /api/trajectory-analysis okunmayan alan sessiz kalmaz
# ===========================================================================
YORUNGE = {'thrust': 5000, 'burn_time': 10, 'initial_mass': 50,
           'final_mass': 25, 'drag_coefficient': 0.5, 'reference_area': 0.1}


class TestH1Y7OkunmayanAlan:
    """ÖLÇÜLDÜ (``a3/once.json`` K9): ``thrust=-1000/0``,
    ``final_mass=-10``, ``initial_mass=0``, ``reference_area=0/-1``,
    ``drag_coefficient=-1``, ``burn_time=-5`` — sekizi de 422 alan adıyla.
    ``dry_mass=-10`` ise HTTP **200** + 305.727 baytlık TAM yörünge.
    """

    def test_celisen_kutle_HUKUM_ALMAZ(self, istemci):
        kod, g = _post(istemci, '/api/trajectory-analysis',
                       dict(YORUNGE, dry_mass=-10))
        assert kod == 422, f'çelişen kütle hâlâ yörünge alıyor: {kod}'
        assert g['error'] == 'contradictory_vehicle_mass'
        alanlar = sorted(k['field'] for k in g['invalid_fields'])
        assert alanlar == ['dry_mass', 'final_mass']
        for k in g['invalid_fields']:
            assert k['canonical_field'] == 'final_mass'
        assert 'trajectory' not in g

    def test_uyumlu_takma_ad_ADIYLA_beyan_edilir(self, istemci):
        kod, g = _post(istemci, '/api/trajectory-analysis',
                       dict(YORUNGE, dry_mass=25))
        assert kod == 200
        beyan = g['inputs_not_read']
        assert [k['field'] for k in beyan] == ['dry_mass']
        assert beyan[0]['reason'] == 'not_read_by_this_endpoint'
        assert beyan[0]['canonical_field'] == 'final_mass'

    def test_saglikli_govde_BIT_AYNI(self, istemci):
        """Çapa: takma ad gönderilmezse alan HİÇ eklenmez."""
        kod, g = _post(istemci, '/api/trajectory-analysis', dict(YORUNGE))
        assert kod == 200
        assert 'inputs_not_read' not in g

    def test_takma_ad_tablosu_ICAT_DEGIL(self):
        """``dry_mass`` kardeş ucun KANONİK alan adıdır."""
        from hrma.app import (_TRAJECTORY_TAKMA_ADLAR,
                              _SIXDOF_UC_VARSAYILANLARI,
                              _TRAJECTORY_VEHICLE_FIELDS)
        for tak, kanon in _TRAJECTORY_TAKMA_ADLAR.items():
            assert tak in _SIXDOF_UC_VARSAYILANLARI, tak
            assert kanon in _TRAJECTORY_VEHICLE_FIELDS, kanon


# ===========================================================================
# P13B4-05 — status_report._flatten_cell dürüstlük alanları
# ===========================================================================
class TestP13B405AlanEsligi:
    """ÖLÇÜLDÜ (``a3/once.json`` K1): iç hücre 20 anahtar, yayım 16;
    düşen dördü (``confidence_band``, ``campaign_stats``,
    ``outlier_test_ids``, ``stats_excl_outliers``) hücrenin DÜRÜSTLÜK
    künyesiydi ve gerekçesiz düşüyordu. Borç imi
    ``tests/test_fazb_serilestirici_esligi.py``de xfail(strict) idi ve
    onarımla KALDIRILDI.
    """

    def test_dort_durustluk_alani_YAYIMLANIYOR(self):
        from hrma.validation.correlation_runner import _cell
        from hrma.validation.status_report import (_flatten_cell,
                                                   _HONESTY_FIELDS)
        girisler = [
            {'test_id': 'a', 'error_pct': 3.0, 'confidence': 'high',
             'campaign': 'k1', 'flags': ['in_sample'],
             'measurement_u_pct': 0.8, 'normalized_error': 0.4},
            {'test_id': 'b', 'error_pct': -5.0, 'confidence': 'high',
             'campaign': 'k2', 'flags': [], 'measurement_u_pct': 1.2,
             'normalized_error': 1.1},
            {'test_id': 'c', 'error_pct': 1.0, 'confidence': 'medium',
             'campaign': 'k2', 'flags': [], 'measurement_u_pct': None,
             'normalized_error': None},
        ]
        ic = _cell('hybrid', 'c_star', girisler, 'high_medium')
        yayim = _flatten_cell(ic, 'main')
        assert len(_HONESTY_FIELDS) == 4
        for ad in _HONESTY_FIELDS:
            assert ad in yayim, f'{ad} yeniden düşürülmüş'
            assert yayim[ad] == ic[ad]
        assert yayim['confidence_band'] == 'high_medium'
        assert yayim['campaign_stats']['n_campaigns'] == 2

    def test_iki_katman_AYNI_sekle_iner(self):
        """Anomali hücresi de dört alanı taşır (tüketici ayrım yapmasın)."""
        from hrma.validation.status_report import (correlation_cells,
                                                   _HONESTY_FIELDS)
        hucreler = correlation_cells({
            'cells': [], 'low_confidence_cells': [],
            'anomaly_entries': [
                {'motor_type': 'solid', 'quantity': 'burn_rate',
                 'error_pct': 4.0, 'test_id': 'x', 'flags': []}],
            'out_of_scope_entries': [],
        })
        assert len(hucreler) == 1
        for ad in _HONESTY_FIELDS:
            assert ad in hucreler[0], ad

    def test_borc_imi_KALKTI(self):
        """Bekçinin ÜSTÜNDE xfail DEKORATÖRÜ kalmadı (yorum sayılmaz)."""
        import ast as _ast
        import inspect
        import tests.test_fazb_serilestirici_esligi as _m
        agac = _ast.parse(inspect.getsource(_m))
        bulundu = [d for d in agac.body
                   if isinstance(d, _ast.FunctionDef)
                   and d.name == 'test_s1_korelasyon_hucresi_alan_esligi']
        assert len(bulundu) == 1
        assert bulundu[0].decorator_list == [], (
            'P13B4-05 borç imi hâlâ duruyor — XPASS süiti kırar')


# ===========================================================================
# ÖLÇÜMLE ÇÜRÜTÜLEN DÖRT KALEM — kapanış DONDURULUR
# ===========================================================================
class TestCurutulenKalemler:
    """Dördü de defterde açık/bekçi-kırmızı görünüyordu; ölçüm başlıklarını
    çürüttü. Bu sınıf kapanışı dondurur: geri gelirse kırmızı verir.
    """

    def test_OHD2509_solid_ret_govdesi_ADLI_JSON(self, istemci):
        """OH-D25-09: '400 DÜZ METİN, invalid_fields yok' — ÇÜRÜK."""
        taban = {'motor_name': 'x', 'propellant_type': 'APCP',
                 'chamber_pressure': 50, 'chamber_diameter': 100,
                 'chamber_length': 500, 'grain_length': 400,
                 'grain_type': 'BATES', 'burn_time': 3, 'thrust': 1000}
        for cd in (0, 100):
            kod, g = _post(istemci, '/calculate_solid',
                           dict(taban, core_diameter=cd))
            assert kod == 400
            kayit = g['invalid_fields'][0]
            assert kayit['field'] == 'core_diameter'
            assert kayit['accepted_range'] == [5.0, 95.0]
            assert kayit['accepted_range_source']
            assert kayit['canonical_range'] == [0.0, 100.0]
            kod2, g2 = _post(istemci, '/api/solid-monte-carlo',
                             dict(taban, core_diameter=cd))
            assert kod2 == 422
            assert g2['invalid_fields'][0]['field'] == 'core_diameter'

    @pytest.mark.parametrize('n', [0, -5, 1])
    def test_H1Y6_n_samples_sessizce_50ye_CIKMIYOR(self, istemci, n):
        """H1-Y6: 'n_samples 0 ve -5 sessizce 50'ye çıkıyor' — ÇÜRÜK."""
        kod, g = _post(istemci, '/api/uncertainty-analysis', {
            'motor_type': 'hybrid', 'level': 'fast', 'n_samples': n,
            'inputs': {'thrust': 3000, 'burn_time': 10,
                       'chamber_pressure': 20, 'of_ratio': 6.0}})
        assert kod == 400
        assert g['error'] == 'n_samples_out_of_range'
        kayit = g['invalid_fields'][0]
        assert kayit['field'] == 'n_samples'
        assert kayit['value'] == n
        assert kayit['accepted_range'][0] == 2

    @pytest.mark.parametrize('gm', [1.10, 1.40])
    def test_P16B120_gamma_BEYANSIZ_degil(self, istemci, gm):
        """P16B1-20: 'gamma ölü ve BEYANSIZ, inputs_not_used boş' — ÇÜRÜK."""
        kod, g = _post(istemci, '/calculate', {
            'motor_name': 'x', 'thrust': 3000, 'burn_time': 10,
            'chamber_pressure': 20, 'of_ratio': 6.0, 'fuel_type': 'htpb',
            'oxidizer_type': 'n2o', 'include_plots': False, 'gamma': gm})
        assert kod == 200
        beyan = [d for d in (g.get('inputs_not_used') or [])
                 if d['field'] == 'gamma']
        assert len(beyan) == 1, 'gamma beyanı yok — kalem geri gelmiş'
        assert beyan[0]['submitted'] == pytest.approx(gm)
        assert beyan[0]['reason'] == 'solved_by_model'
        assert beyan[0]['submitted_value_echo_count'] == 0
        assert beyan[0]['used_by_model'] != gm
        assert math.isfinite(beyan[0]['used_by_model'])

    def test_OHB101_dp_reddi_alani_ADLANDIRIR(self, istemci):
        """OH-B1-01: 'ΔP retinin gerekçesi alanı adlandırmıyor' — ÇÜRÜK."""
        pc = 100.0
        # Birleşme etkileşimi (ana model, 8 Eyl): D27 sivi a1 / OH-D26-12 ile
        # tank basıncı kapısı ÇEVRİME bağlandı — turbopompalı varsayılanda
        # tank_pressure OKUNMAZ (422 tank_pressure_not_read_in_turbopump_cycle).
        # Bu iddia (ΔP reddi alanı adlandırır) BASINÇ BESLEMELİ çevrimde
        # kurulur; gövde çevrimi ilan eder, iddia değişmedi.
        kod, g = _post(istemci, '/calculate_liquid', {
            'thrust': 10000.0, 'chamber_pressure': pc, 'mixture_ratio': 2.5,
            'fuel_type': 'rp1', 'oxidizer_type': 'lox',
            'engine_cycle': 'pressure_fed',
            'tank_pressure': pc * 1.02})
        assert kod == 400
        havuz = json.dumps(g).lower()
        assert 'tank_pressure' in havuz
        assert any(k['field'] == 'tank_pressure'
                   for k in (g.get('invalid_fields') or []))


# ===========================================================================
# P15B2-01 (kısmen) — merkezî kapının kapsamı BÜYÜDÜ, envanter dondu
# ===========================================================================
class TestP15B201Envanter:
    """Kalan bağımsız çevirici tanımları başka kulvarların sahasında;
    envanter ``a3/rapor.md`` §P15B2-01'de kulvar kulvar devredildi.
    Bu bekçi devrin BÜYÜMEMESİNİ sınar.
    """

    def test_merkezi_kapi_urun_dosyalarinda_YAYGIN(self):
        import subprocess
        p = subprocess.run(['git', 'grep', '-l', '-F', 'input_guard',
                            '--', 'hrma/'], capture_output=True, text=True)
        dosyalar = [x for x in p.stdout.split() if x]
        assert len(dosyalar) >= 18, dosyalar

    def test_app_api_sahasinda_bagimsiz_tanim_ARTMIYOR(self):
        """Bu kulvarın kendi dosyalarındaki çevirici tanımı sayısı donduruldu."""
        import subprocess
        p = subprocess.run(
            ['git', 'grep', '-cE',
             r'^def _(mm_to_m|mm_to_m_read|mm_to_m_optional|positive_float|'
             r'json_float|request_number|flow_float)\(',
             '--', 'hrma/app.py'], capture_output=True, text=True)
        sayi = int((p.stdout.strip() or '0').split(':')[-1] or 0)
        assert sayi <= 7, (
            f'app.py bağımsız çevirici tanımı 7den 8e çıktı ({sayi}) — '
            'merkezîleştirme geri gidiyor')
