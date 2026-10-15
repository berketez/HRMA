"""ÖH Dalga-15 · yapısal-sistem kulvarı · aşama 1 — onarım bekçileri.

Her sınıf TEK bir kalemi tutar ve o kalemin ÖLÇÜLEN kusurunu görür.
Ters-mutasyon kanıtı: onarım geçici olarak geri alındığında (kaynak
baytına ters-değiştirme, ``git checkout`` DEĞİL) bu testlerin kırmızıya
döndüğü ölçülmüştür; kanıt
``docs/scofield/raw/OH/D15/yapisal-sistem/a1/mutasyon.json``.

Taban ölçümü: ``.../a1/once.json`` · onarım sonrası ``.../a1/sonra.json``.
"""
import pytest

from hrma.analysis.safety_analysis import (SafetyAnalyzer,
                                           UnresolvedChamberMaterial,
                                           TOXIC_LEVEL_NOT_EVALUATED)
from hrma.analysis.regression_analysis import (RegressionAnalyzer,
                                               UnresolvedFuelType)


@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


# =====================================================================
# P5B2-02 [KRİTİK] — toksik envanter serbest metinden çözülür, çözülemeyen
# iticide TIBBİ hüküm yayımlanmaz
# =====================================================================
class TestP5B202ToksikEslemeCozunur:

    def test_urun_adlari_tabloya_cozulur(self):
        """ÖLÇÜLEN (once.json): ürünün gerçekten gönderdiği altı adın
        ALTISI da ``unrecognised_propellant_class`` ile hükümsüz kalıyordu
        (``n2o4_mmh``, ``mmh``, ``n2o4``, ``hydrazine``, ``udmh``,
        ``nto_mmh``). Kardeş kol (``_resolve_explosive_class``) aynı metni
        çözebiliyordu."""
        sa = SafetyAnalyzer()
        beklenen = {
            'n2o4_mmh': {'n2o4', 'mmh'},
            'nto_mmh': {'mmh'},
            'mmh': {'mmh'},
            'n2o4': {'n2o4'},
            'hydrazine': {'hydrazine'},
            'udmh': {'udmh'},
            'n2o_htpb': {'n2o'},
        }
        for ad, bilesenler in beklenen.items():
            k = sa._analyze_toxic_hazards(ad, 120.0, 'test_stand')
            assert set(k['toxic_components']) == bilesenler, ad
            assert k['toxic_inventory_resolution'] == 'tabulated', ad
            assert k['toxic_hazard_level'] not in (
                'NONE', TOXIC_LEVEL_NOT_EVALUATED), ad

    def test_n2o4_icinde_n2o_yakalanmaz(self):
        """Tam sözcük eşleşmesi: 'n2o4' iticisi azot protoksit sayılmaz."""
        sa = SafetyAnalyzer()
        assert sa._analyze_toxic_hazards(
            'n2o4', 1.0, 'test_stand')['toxic_components'] == ['n2o4']

    def test_cozulemeyen_iticide_antidot_hukmu_yayimlanmaz(self):
        """ÖLÇÜLEN (once.json): toksik seviye ``NOT_EVALUATED`` olan 12
        vakanın 12'sinde yanıt yine de 'No specific antidote required —
        supportive care' basıyordu. Değerlendirilmemiş bir tehlike için
        verilmiş TIBBİ hüküm kazanılmamıştır."""
        sa = SafetyAnalyzer()
        k = sa._analyze_toxic_hazards('lox_rp1', 120.0, 'test_stand')
        assert k['toxic_hazard_level'] == TOXIC_LEVEL_NOT_EVALUATED
        antidot = sa._determine_required_antidotes(k)
        assert len(antidot) == 1
        assert 'NOT EVALUATED' in antidot[0]
        assert 'no antidote is needed' in antidot[0]
        # Kazanılmış "yok" hükmü (tablolu bileşeni olmayan tanınan sınıf)
        # eski cümleyi KORUR — iki durum artık ayrı.
        kk = sa._analyze_toxic_hazards('composite', 120.0, 'test_stand')
        assert kk['toxic_hazard_level'] == 'NONE'
        assert sa._determine_required_antidotes(kk) == [
            'No specific antidote required — supportive care']

    def test_urun_ucu_hipergolik_motoru_toksik_sayar(self, istemci):
        r = istemci.post('/analyze_safety', json={
            'chamber_pressure': 70, 'propellant_mass': 120.0,
            'chamber_diameter': 0.12, 'wall_thickness': 0.003,
            'motor_type': 'liquid', 'propellant_type': 'n2o4_mmh',
            'material': 'steel_4130'})
        assert r.status_code == 200
        sa = r.get_json()['safety_analysis']
        assert sa['toxic_hazards']['toxic_hazard_level'] == 'HIGH'
        assert set(sa['toxic_hazards']['toxic_components']) == {'n2o4', 'mmh'}


# =====================================================================
# P5B2-03 [KRİTİK] — yazım hatalı malzeme sessizce steel_4130 olmaz
# =====================================================================
class TestP5B203MalzemeFailClosed:

    OLCULEN_YAZIM_HATALARI = ('aluminum6061', 'AL6061', 'unobtainium', '')

    def test_uc_kolun_ucu_de_reddediyor(self):
        """ÖLÇÜLEN (once.json): üç ayrı ``except KeyError -> steel_4130``
        yedeği vardı. ``'aluminum6061'`` akma SF'yi 1,9643 -> 3,2857
        çıkarıyordu (yön EMNİYETSİZ, uyarı YOK)."""
        sa = SafetyAnalyzer()
        md = {'chamber_pressure': 70.0, 'chamber_diameter': 0.12,
              'wall_thickness': 0.003, 'chamber_temperature': 3000.0,
              'burn_time': 10.0}
        for ad in self.OLCULEN_YAZIM_HATALARI:
            with pytest.raises(UnresolvedChamberMaterial):
                sa._analyze_structural_safety(md, ad)
            with pytest.raises(UnresolvedChamberMaterial):
                sa._analyze_thermal_safety(md, ad)
            with pytest.raises(UnresolvedChamberMaterial):
                sa._estimate_case_mass(100.0, md, ad)

    def test_gercek_alüminyum_gercek_sayiyi_verir(self):
        sa = SafetyAnalyzer()
        md = {'chamber_pressure': 70.0, 'chamber_diameter': 0.12,
              'wall_thickness': 0.003}
        r = sa._analyze_structural_safety(md, 'aluminum_6061')
        assert r['yield_strength_mpa'] == pytest.approx(275.0)
        assert r['yield_safety_factor'] == pytest.approx(1.9643, abs=1e-3)

    def test_ret_alan_adini_ve_secenekleri_tasir(self):
        sa = SafetyAnalyzer()
        with pytest.raises(UnresolvedChamberMaterial) as h:
            sa._analyze_structural_safety(
                {'chamber_pressure': 70.0, 'chamber_diameter': 0.12,
                 'wall_thickness': 0.003}, 'aluminum6061')
        assert 'aluminum6061' in str(h.value)
        assert 'aluminum_6061' in h.value.available


# =====================================================================
# P5B4-38 [KRİTİK] — yakıt kimliği üretici ile tüketici arasında kaybolmaz
# =====================================================================
class TestP5B438YakitKimligi:

    TEMEL = {'burn_time': 12.0, 'mdot_ox': 2.0,
             'port_diameter_initial': 0.08129, 'chamber_length': 0.5,
             'grain_length': 0.4}

    def test_kimliksiz_cagri_hukum_uretmez(self):
        """ÖLÇÜLEN (once.json): ``fuel_type`` yokken r_dot[0] 1002,3 mm/s
        (HTPB) çıkıyordu; aynı gövde parafinle 4692,7 mm/s — 4,68 kat."""
        ra = RegressionAnalyzer()
        with pytest.raises(UnresolvedFuelType):
            ra.analyze_regression_vs_time(dict(self.TEMEL))

    def test_kimlik_sayiyi_yonetiyor(self):
        ra = RegressionAnalyzer()
        d = dict(self.TEMEL)
        d['fuel_type'] = 'htpb'
        htpb = ra.analyze_regression_vs_time(d)['regression_rate'][0]
        d['fuel_type'] = 'paraffin'
        par = ra.analyze_regression_vs_time(d)['regression_rate'][0]
        assert par / htpb > 4.0     # ölçülen 4,68

    def test_hibrit_calculate_yakiti_yayimliyor(self, istemci):
        """ÖLÇÜLEN (once.json): hibrit motor sonucunda ``fuel_type``
        anahtarı YOKTU; panel bu sözlüğü regresyona veriyordu."""
        r = istemci.post('/calculate', json={
            'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
            'chamber_pressure': 20.0, 'fuel_type': 'paraffin',
            'oxidizer_type': 'n2o'})
        assert r.status_code == 200
        assert r.get_json()['motor']['fuel_type'] == 'paraffin'

    def test_uc_kimliksiz_istegi_reddediyor(self, istemci):
        r = istemci.post('/api/regression-analysis',
                         json={'motor_data': dict(self.TEMEL)})
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'missing_fuel_type'
        assert j['missing_fields'] == ['fuel_type']


# =====================================================================
# P5B2-04 [YÜKSEK] — yangın sınıfı serbest metinden değil, çözülen sınıftan
# =====================================================================
class TestP5B204YanginSinifi:

    def test_sivi_motor_class_b_alir(self):
        """ÖLÇÜLEN (once.json): ``lox_rp1`` ve ``n2o4_mmh`` sıvı motorlara
        'Class 1.3-type solid propellant fire (cannot be smothered)' +
        'Let solid propellant burn out' yazılıyordu."""
        sa = SafetyAnalyzer()
        for ad in ('lox_rp1', 'n2o4_mmh', 'liquid_biprop'):
            sinif = sa._classify_fire_hazard(ad, 'liquid')
            assert sinif.startswith('Class B'), ad
            adimlar = sa._generate_fire_fighting_procedures(sinif)
            assert not any('burn out' in a for a in adimlar), ad

    def test_kati_motor_class_13_kalir(self):
        sa = SafetyAnalyzer()
        for ad in ('apcp', 'composite'):
            assert 'Class 1.3' in sa._classify_fire_hazard(ad, 'solid')

    def test_hibrit_class_a_alir(self):
        sa = SafetyAnalyzer()
        assert sa._classify_fire_hazard(
            'n2o_htpb', 'hybrid').startswith('Class A')

    def test_urun_ucu_sivi_motora_kopuk_yaziyor(self, istemci):
        r = istemci.post('/analyze_safety', json={
            'chamber_pressure': 70, 'propellant_mass': 120.0,
            'chamber_diameter': 0.12, 'wall_thickness': 0.003,
            'motor_type': 'liquid', 'propellant_type': 'lox_rp1',
            'material': 'steel_4130'})
        assert r.status_code == 200
        fh = r.get_json()['safety_analysis']['fire_hazards']
        assert fh['fire_classification'].startswith('Class B')
        assert 'Foam' in fh['suppression_system']['primary_agent']


# =====================================================================
# P5B2-08 [YÜKSEK] — girdisiz belirsizlik isteği rapor üretemez
# =====================================================================
class TestP5B208BelirsizlikKapisi:

    def test_girdisiz_istek_422(self, istemci):
        """ÖLÇÜLEN (once.json): ``{'motor_type':'hybrid','level':'fast'}``
        HTTP 200 + 12 042 bayt + hibrit isp nominali 134,05 s veriyordu;
        kardeş uç ``POST /analyze_safety -d '{}'`` aynı durumda 422."""
        r = istemci.post('/api/uncertainty-analysis',
                         json={'motor_type': 'hybrid', 'level': 'fast'})
        assert r.status_code == 422
        j = r.get_json()
        assert j['error'] == 'incomplete_uncertainty_input'
        assert j['missing_fields'] == ['inputs']

    def test_bos_sozluk_de_reddedilir(self, istemci):
        r = istemci.post('/api/uncertainty-analysis',
                         json={'motor_type': 'hybrid', 'level': 'fast',
                               'inputs': {}})
        assert r.status_code == 422

    def test_gercek_girdi_hala_kosuyor(self, istemci):
        r = istemci.post('/api/uncertainty-analysis', json={
            'motor_type': 'hybrid', 'level': 'fast',
            'inputs': {'thrust': 1000, 'burn_time': 10, 'of_ratio': 6.0,
                       'chamber_pressure': 20.0, 'fuel_type': 'htpb',
                       'oxidizer_type': 'n2o'}})
        assert r.status_code in (200, 202)


# =====================================================================
# ÖH Dalga-15 · aşama 1 · B1 öbeği (P5B1-03..08) — yapısal hüküm zinciri
# Taban: ``.../a1/once_b1.json`` · onarım sonrası ``.../a1/sonra_b1.json``
# =====================================================================
from hrma.analysis.structural_analysis import StructuralAnalyzer  # noqa: E402
from hrma.analysis.pressure_vessel import PressureVesselAnalyzer  # noqa: E402
from hrma.analysis import bolted_joint as _bj                     # noqa: E402

_B1_MOTOR = {'chamber_pressure': 40.0, 'chamber_diameter': 0.1,
             'chamber_length': 0.5, 'throat_diameter': 0.02,
             'burn_time': 10.0}


class TestP5B103YorulmaSicaklikGoruyor:
    """P5B1-03 — yorulma cidar sıcaklığından habersizdi."""

    def test_n_f_sicaklikla_dusuyor(self):
        """ÖLÇÜLEN (once_b1.json): 300 / 700 / 800 / 811 K'de n_f BİREBİR
        2,331944 — hazne cidarı %61 derate edilirken yorulma hiç
        kıpırdamıyordu (konservatif OLMAYAN yön)."""
        A = StructuralAnalyzer()
        nf = []
        for T in (300.0, 700.0, 811.0):
            r = A.analyze_structure(
                dict(_B1_MOTOR, chamber_pressure=80.0,
                     wall_temperature_hot=T, wall_temperature_cold=T),
                material='steel_4130', actual_wall_thickness=0.004)
            nf.append(r['fatigue_analysis']['fatigue_safety_factor'])
        assert len(set(nf)) == 3, (
            f"yorulma emniyet katsayısı sıcaklıkla değişmiyor: {nf}")
        assert nf[0] > nf[1] > nf[2], (
            f"yorulma katsayısı sıcaklıkla DÜŞMELİ, ölçülen: {nf}")

    def test_yorulma_siniri_derate_akmayi_asamaz(self):
        """ÖLÇÜLEN (once_b1.json): 800 K ve 811 K'de yayımlanan
        fatigue_limit 230,0 MPa, aynı yanıttaki derate edilmiş akma
        183,87 / 176,28 MPa — sonsuz-ömür dayanım sınırının akmayı aşması
        fiziksel olarak imkânsız."""
        A = StructuralAnalyzer()
        for T in (300.0, 700.0, 800.0, 811.0):
            r = A.analyze_structure(
                dict(_B1_MOTOR, chamber_pressure=80.0,
                     wall_temperature_hot=T, wall_temperature_cold=T),
                material='steel_4130', actual_wall_thickness=0.004)
            S_e = r['fatigue_analysis']['fatigue_limit']
            akma = r['chamber_analysis']['yield_strength_used_MPa']
            assert S_e <= akma, (
                f"T={T} K: yorulma sınırı {S_e:.2f} MPa, derate akma "
                f"{akma:.2f} MPa — imkânsız çift")

    def test_derating_kunyesi_yayimlaniyor(self):
        A = StructuralAnalyzer()
        r = A.analyze_structure(
            dict(_B1_MOTOR, chamber_pressure=80.0,
                 wall_temperature_hot=811.0, wall_temperature_cold=811.0),
            material='steel_4130', actual_wall_thickness=0.004)
        fa = r['fatigue_analysis']
        assert isinstance(fa.get('strength_derating_basis'), str)
        assert fa.get('strength_retention_factor') is not None
        assert fa['fatigue_limit'] < fa['fatigue_limit_room_MPa']


class TestP5B104KaynakVerimiGovdede:
    """P5B1-04 — aiaa_s080 kaynak verimini gövdede yok sayıyordu."""

    def test_t_req_ve_mawp_E_ile_degisir(self):
        """ÖLÇÜLEN (once_b1.json; 60 bar, D_iç 150 mm, steel_4130):
        E = 0,70 / 0,85 / 1,00 için t_req = 1,481888 mm ve MAWP =
        60,6891 bar BİREBİR aynıydı; başlık ise %43 değişiyordu."""
        PV = PressureVesselAnalyzer()
        t = {}
        for E in (0.70, 0.85, 1.00):
            r = PV.analyze(meop_bar=60.0, inner_diameter_mm=150.0,
                           material='steel_4130', weld_efficiency=E,
                           code_mode='aiaa_s080')
            t[E] = r['required_thickness_mm']
        assert len(set(t.values())) == 3, (
            f"kaynak verimi gövde kalınlığını etkilemiyor: {t}")
        assert t[0.70] > t[0.85] > t[1.00], (
            f"düşük kaynak verimi DAHA KALIN cidar istemeli: {t}")

    def test_E_bir_iken_bit_ayni(self):
        """E = 1,00 varsayılanında hiçbir sayı kıpırdamamalı (taban
        değeri: t_req = 1,481888035126235 mm)."""
        PV = PressureVesselAnalyzer()
        r = PV.analyze(meop_bar=60.0, inner_diameter_mm=150.0,
                       material='steel_4130', weld_efficiency=1.00,
                       code_mode='aiaa_s080')
        assert r['required_thickness_mm'] == pytest.approx(
            1.481888035126235, rel=1e-12)


class TestP5B105UyeMalzemesiZorunlu:
    """P5B1-05 — üye malzemesi varsayılanı ayrılma hükmünü çeviriyordu."""

    def test_modul_uye_malzemesiz_hukum_vermez(self):
        with pytest.raises(ValueError) as ex:
            _bj.analyze_bolted_joint(pressure_bar=95.0,
                                     seal_diameter_mm=160.0, bolt_count=8,
                                     size='M10', property_class='8.8',
                                     grip_length_mm=30.0)
        assert 'member_material' in str(ex.value)

    def test_sinif_kurucusu_da_ister(self):
        with pytest.raises(ValueError):
            _bj.BoltedJointAnalyzer(size='M10', property_class='8.8',
                                    bolt_count=8, grip_length_mm=30.0)

    def test_uc_alan_adiyla_reddeder(self, istemci):
        r = istemci.post('/api/bolted-joint', json={
            'pressure_bar': 95.0, 'seal_diameter_mm': 160.0,
            'bolt_count': 8, 'size': 'M10', 'property_class': '8.8',
            'grip_length_mm': 30.0})
        assert r.status_code == 400, r.get_data(as_text=True)[:200]
        assert 'member_material' in r.get_data(as_text=True)

    def test_malzeme_verilince_hukum_ceviriyor_hala_gorulur(self):
        """ÖLÇÜLEN (once_b1.json): 95 / 100 / 110 bar'da ``separated``
        alüminyumda False, çelikte True. Kusur varsayılanın SESSİZ
        olmasıydı; fizik doğru ve korunur."""
        alu = _bj.analyze_bolted_joint(
            pressure_bar=100.0, seal_diameter_mm=160.0, bolt_count=8,
            size='M10', property_class='8.8', grip_length_mm=30.0,
            member_material='aluminum_6061')
        cel = _bj.analyze_bolted_joint(
            pressure_bar=100.0, seal_diameter_mm=160.0, bolt_count=8,
            size='M10', property_class='8.8', grip_length_mm=30.0,
            member_material='steel_4130')
        assert alu['separation']['separated'] is False
        assert cel['separation']['separated'] is True


class TestP5B106TekCivataCevabi:
    """P5B1-06 — motor yolu ile ön-yük modeli çelişiyordu."""

    def test_sikma_boyu_yoksa_hukum_yok(self):
        """ÖLÇÜLEN (once_b1.json): sıkma boyu olmadan bile ürün
        ``bolt_safety_factor = 4,0`` yayımlıyor, hiçbir hüküm alanı
        taşımıyordu (``fastener_status`` YOKTU)."""
        A = StructuralAnalyzer()
        fas = A.analyze_structure(
            dict(_B1_MOTOR, chamber_pressure=100.0, chamber_diameter=0.15),
            material='steel_4130',
            actual_wall_thickness=0.006)['fastener_analysis']
        assert fas['fastener_status'] == 'NOT_EVALUATED'
        assert fas['preload_analysis'] is None
        assert 'grip length' in fas['preload_analysis_basis']
        assert fas['bolt_safety_factor_is_design_input'] is True

    def test_sikma_boyu_verilince_onyuk_hukmu_yayimlanir(self):
        """ÖLÇÜLEN (once_b1.json): Pc = 100 bar / D = 150 mm / 8 x M20
        için bağımsız ön-yük modeli proof_SF_min = 0,9964 (proof İHLALİ)
        derken motor yolu 4,0 yayımlıyordu — tek motorda iki cevap."""
        A = StructuralAnalyzer()
        fas = A.analyze_structure(
            dict(_B1_MOTOR, chamber_pressure=100.0, chamber_diameter=0.15,
                 closure_grip_length_m=0.020),
            material='steel_4130',
            actual_wall_thickness=0.006)['fastener_analysis']
        pre = fas['preload_analysis']
        assert pre is not None
        assert pre['proof_SF_min'] == pytest.approx(0.9964115922883197,
                                                    rel=1e-9)
        assert fas['fastener_status'] == 'CRITICAL', (
            "ön-yük modeli proof ihlali diyorken cıvata bloğu hüküm "
            f"vermiyor: {fas['fastener_status']}")

    def test_iki_uretici_ayni_sayiyi_verir(self):
        """Aynı bağlantı, aynı tasarım basıncı: motor yolu artık ön-yük
        modelini ÇAĞIRIYOR, dolayısıyla sayı birebir aynı olmalı."""
        A = StructuralAnalyzer()
        fas = A.analyze_structure(
            dict(_B1_MOTOR, chamber_pressure=100.0, chamber_diameter=0.15,
                 closure_grip_length_m=0.020),
            material='steel_4130',
            actual_wall_thickness=0.006)['fastener_analysis']
        bagimsiz = _bj.analyze_bolted_joint(
            pressure_bar=1.5 * 100.0, seal_diameter_mm=150.0,
            bolt_count=int(fas['num_bolts']),
            size=str(fas['recommended_bolt_size']), property_class='8.8',
            grip_length_mm=20.0, member_material='steel_4130')
        assert (fas['preload_analysis']['proof_SF_min']
                == bagimsiz['safety_factors']['proof_SF_min'])


class TestP5B107GevrekKirilmaHukmuBaglar:
    """P5B1-07 — kriyojenik gevrek kırılma yalnız uyarıydı."""

    def test_dbtt_duyarli_malzeme_20K_de_onay_alamaz(self):
        """ÖLÇÜLEN (once_b1.json; 5 bar MEOP, D_iç 400 mm, cidar 8 mm,
        T = 20 K): steel / steel_4130 / ss_17_4ph / molybdenum_tzm /
        tungsten — BEŞİ de status = PASS, burst_margin 15,57…51,37."""
        PV = PressureVesselAnalyzer()
        for malzeme in ('steel', 'steel_4130', 'ss_17_4ph',
                        'molybdenum_tzm', 'tungsten'):
            r = PV.analyze(meop_bar=5.0, inner_diameter_mm=400.0,
                           material=malzeme, wall_thickness_mm=8.0,
                           temperature_K=20.0)
            assert r['status'] == 'NOT_EVALUATED', (
                f"{malzeme}: DBTT-duyarlı malzeme 20 K'de "
                f"'{r['status']}' hükmü alıyor")
            assert any('brittle' in w.lower()
                       for w in r['warnings']), (
                f"{malzeme}: gevrek kırılma gerekçesi "
                "uyarı listesinde yok")

    def test_ostenitik_ve_aluminyum_etkilenmez(self):
        PV = PressureVesselAnalyzer()
        for malzeme in ('ss_316', 'aluminum_6061'):
            r = PV.analyze(meop_bar=5.0, inner_diameter_mm=400.0,
                           material=malzeme, wall_thickness_mm=8.0,
                           temperature_K=20.0)
            assert r['status'] == 'PASS', (malzeme, r['status'])
            assert 'NOT_EVALUATED' not in r['status']

    def test_oda_sicakliginda_kapi_kapali(self):
        PV = PressureVesselAnalyzer()
        r = PV.analyze(meop_bar=60.0, inner_diameter_mm=150.0,
                       material='steel_4130', wall_thickness_mm=8.0)
        assert r['status'] in ('PASS', 'MARGINAL', 'FAIL')


class TestP5B108OnerilenCidarHedefiTutturur:
    """P5B1-08 — boyutlandırma ince-cidardan, doğrulama Lame'den."""

    def test_kalin_cidar_rejiminde_hedef_tutturulur(self):
        """ÖLÇÜLEN (once_b1.json; steel_4130, D = 100 mm, SF hedefi 4,0,
        imalat payı 1,2 → beklenen 4,80): 200 bar'da ulaşılan 4,0737
        (%15,1 eksik), 400 bar'da 3,4556 (%28,0 eksik)."""
        A = StructuralAnalyzer()
        for Pc in (200.0, 400.0):
            ca = A.analyze_structure(dict(_B1_MOTOR, chamber_pressure=Pc),
                                     material='steel_4130',
                                     design_safety_factor=4.0)['chamber_analysis']
            assert ca['sizing_stress_model'] == ca['pressure_hoop_model'], (
                "boyutlandırma ve değerlendirme farklı modelden: "
                f"{ca['sizing_stress_model']} ⟷ {ca['pressure_hoop_model']}")
            assert ca['hoop_safety_factor'] == pytest.approx(4.8, rel=1e-9), (
                f"Pc={Pc} bar: hedef 4,80, ulaşılan "
                f"{ca['hoop_safety_factor']:.4f}")

    def test_ince_cidar_rejimi_bit_ayni(self):
        """40 bar (t/r = 0,0628) taban değerleri BİREBİR korunmalı."""
        A = StructuralAnalyzer()
        ca = A.analyze_structure(dict(_B1_MOTOR, chamber_pressure=40.0),
                                 material='steel_4130',
                                 design_safety_factor=4.0)['chamber_analysis']
        assert ca['recommended_thickness'] == pytest.approx(
            3.139994320874469, rel=1e-12)
        assert ca['sizing_stress_model'] == 'thin_wall'

    def test_ulasilamaz_hedef_adiyla_beyan_edilir(self):
        """ÖLÇÜLEN (once_b1.json): 3000 bar'da ulaşılan 0,9585 (%80
        eksik) iken künye hâlâ 'SF = target x allowance' diyordu."""
        A = StructuralAnalyzer()
        ca = A.analyze_structure(dict(_B1_MOTOR, chamber_pressure=3000.0),
                                 material='steel_4130',
                                 design_safety_factor=4.0)['chamber_analysis']
        assert ca['sizing_feasible'] is False
        assert isinstance(ca['sizing_infeasible_reason'], str)
        assert 'target_SF x manufacturing allowance' not in \
            ca['safety_factor_basis'], (
                "kalın-cidar rejiminde künye hâlâ hedefin geri okunduğunu "
                "iddia ediyor")
