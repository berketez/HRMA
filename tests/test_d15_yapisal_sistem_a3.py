"""ÖH Dalga-15 · kulvar ``yapisal-sistem`` · aşama 3 bekçileri.

Her sınıf BİR kalemi savunur. İddialar ölçülmüş sayılara çapalıdır
(``docs/scofield/raw/OH/D15/yapisal-sistem/a3/once.json``) ve her biri
ters-mutasyonla kırmızı verdiği doğrulanarak yazılmıştır
(``.../a3/mutasyon.json``).

Kullanıcıya dönen ürün metinleri İngilizce'dir (depo kuralı); test adları
ve gerekçeler Türkçe.
"""
import contextlib
import io

import pytest

from hrma.analysis.bolted_joint import (
    BOLT_BEARING_FACE_DIAMETER_MM,
    BOLT_CLEARANCE_HOLE_DIAMETER_MM,
    analyze_bolted_joint,
    seal_diameter_max_mm,
)
from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
from hrma.analysis.safety_analysis import (
    NonPhysicalSafetyInput,
    SafetyAnalyzer,
    sicaklik_bandi_K,
)
from hrma.analysis import uq_adapters


def _sessiz(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        with contextlib.redirect_stderr(io.StringIO()):
            return fn(*a, **kw)


@pytest.fixture(scope='module')
def istemci():
    with contextlib.redirect_stdout(io.StringIO()):
        from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


def _post(istemci, yol, yuk):
    r = _sessiz(istemci.post, yol, json=yuk)
    return r.status_code, (r.get_json() or {})


#: ``/analyze_safety`` sağlıklı gövdesi (a3 ölçümünün taban isteği).
A3_EMNIYET_TABANI = {
    'motor_type': 'solid', 'chamber_pressure': 70, 'propellant_mass': 6.0,
    'chamber_diameter': 0.12, 'wall_thickness': 0.003,
    'chamber_temperature': 2900, 'thrust': 4000, 'burn_time': 6,
    'chamber_length': 0.5, 'throat_diameter': 0.03,
    'propellant_type': 'composite', 'material': 'steel_4130',
}

#: Modül düzeyi motor sözlüğü (aynı motor).
A3_MOTOR_YUKU = {
    'chamber_pressure': 70.0, 'chamber_temperature': 2900.0,
    'thrust': 4000.0, 'burn_time': 6.0, 'chamber_diameter': 0.12,
    'wall_thickness': 0.003, 'chamber_length': 0.5, 'throat_diameter': 0.03,
}


# ===========================================================================
# P5B1-12 — kap PASS alırken kendi başlık gereksinimini karşılamıyor
# ===========================================================================
class TestKapBaslikKapisi:
    """Ölçüldü: ASME kipi, steel_4130, 60 bar, Ø150 mm, cidar 3,0 mm,
    torisferik başlık -> gövde 2,195427934206858 mm (sağlanıyor), başlık
    3,8298530017859598 mm (cidarın 1,2766 katı), ``status = PASS``,
    'head' geçen TEK uyarı yok."""

    KIP = 'asme_viii'
    ORTAK = dict(meop_bar=60.0, inner_diameter_mm=150.0,
                 material='steel_4130', wall_thickness_mm=3.0)

    def _analiz(self, **kw):
        return _sessiz(PressureVesselAnalyzer(code_mode=self.KIP).analyze,
                       **{**self.ORTAK, **kw})

    def test_baslik_gereksinimi_karsilanmayinca_kabul_verilmez(self):
        r = self._analiz(head_type='torispherical')
        assert r['head_thickness_selected_mm'] == pytest.approx(
            3.8298530017859598, rel=1e-9), 'ölçülen başlık gereksinimi kaydı'
        assert r['head_margin'] < 1.0
        assert r['status'] == 'FAIL', (
            'kapak gereksinimi sağlanmadan hiçbir kabul hükmü kazanılamaz')

    def test_gerekce_uyari_listesinde_adiyla_yaziyor(self):
        r = self._analiz(head_type='torispherical')
        basliga_deginen = [w for w in r['warnings'] if 'head' in w.lower()]
        assert basliga_deginen, (
            'kusur tam olarak buydu: başlıkla ilgili TEK uyarı yoktu')
        assert any('HEAD UNDER-THICKNESS' in w for w in basliga_deginen)

    def test_gerekli_kalinliktaki_baslik_hukmu_bozmaz(self):
        """Ayırt edicilik: kapak yeterliyse hüküm ESKİSİ gibi kalır."""
        r = self._analiz(head_type='torispherical', head_thickness_mm=4.0)
        assert r['head_margin'] > 1.0
        assert r['status'] == 'PASS'
        assert not [w for w in r['warnings'] if 'UNDER-THICKNESS' in w]

    def test_elipsoidal_baslik_bu_kapta_zaten_saglaniyor(self):
        """Kapı ayırt edicidir: aynı kapta elipsoidal başlık 2,1638 mm
        istiyor ve 3,0 mm cidarla sağlanıyor -> PASS korunur."""
        r = self._analiz(head_type='ellipsoidal_2_1')
        assert r['head_thickness_selected_mm'] == pytest.approx(
            2.1637587580711637, rel=1e-9)
        assert r['status'] == 'PASS'

    def test_verilmeyen_kapak_kalinligi_beyanla_govdeden_alinir(self):
        """ÖK-19: varsayılan kalacaksa BEYAN zorunlu."""
        r = self._analiz(head_type='ellipsoidal_2_1')
        assert r['inputs']['head_thickness_mm'] is None, (
            "'0 ile verilmedi' karıştırılmaz")
        assert r['head_thickness_available_mm'] == pytest.approx(3.0)
        assert any('SAME wall thickness as the shell' in a
                   for a in r['assumptions'])


# ===========================================================================
# P5B1-13 — bolted_joint girdi kapısı
# ===========================================================================
class TestCivataliBaglantiGirdiKapisi:
    """Ölçüldü (M10 / 8.8 / 8 cıvata / sıkma boyu 30 mm / 60 bar):
    -160 mm ile +160 mm BİREBİR aynı sonucu veriyordu (yük
    120637,15789784805 N, ayrılma marjı 1,504767406275233); 0 mm 'sonsuz
    marj' + ``separated = False``; 1e9 mm kabul (yük 4,7e18 N). Üçü de
    ürün yüzünde HTTP 200."""

    TABAN = dict(bolt_count=8, size='M10', property_class='8.8',
                 grip_length_mm=30.0, member_material='steel_4130')

    def test_saglikli_cap_sayilari_degismedi(self):
        r = _sessiz(analyze_bolted_joint, pressure_bar=60.0,
                    seal_diameter_mm=160.0, **self.TABAN)
        assert r['loads']['total_external_load_N'] == pytest.approx(
            120637.15789784805, rel=1e-9)
        assert r['separation']['margin'] == pytest.approx(
            1.504767406275233, rel=1e-9)

    @pytest.mark.parametrize('cap', [-160.0, 0.0])
    def test_negatif_ve_sifir_cap_reddedilir(self, cap):
        with pytest.raises(ValueError) as exc:
            _sessiz(analyze_bolted_joint, pressure_bar=60.0,
                    seal_diameter_mm=cap, **self.TABAN)
        assert 'seal_diameter_mm' in str(exc.value)

    def test_bir_milyar_mm_cap_reddedilir(self):
        with pytest.raises(ValueError) as exc:
            _sessiz(analyze_bolted_joint, pressure_bar=60.0,
                    seal_diameter_mm=1e9, **self.TABAN)
        assert 'seal_diameter_mm' in str(exc.value)

    def test_ust_sinir_deponun_kanonik_tablosundan(self):
        """Doktrin 4: yeni eşik icat edilmez."""
        from hrma.validation.motor_validation import MotorDataValidator
        beklenen = float(
            MotorDataValidator().limits['chamber_diameter']['max']) * 1e3
        assert seal_diameter_max_mm() == pytest.approx(beklenen)

    @pytest.mark.parametrize('cap', [-160.0, 0.0, 1e9])
    def test_ucta_400_ve_alan_adi(self, istemci, cap):
        durum, govde = _post(istemci, '/api/bolted-joint', {
            'pressure_bar': 60.0, 'seal_diameter_mm': cap, **self.TABAN})
        assert durum == 400, 'üç vaka da HTTP 200 veriyordu'
        assert 'seal_diameter_mm' in str(govde.get('error'))


# ===========================================================================
# P5B1-14 — üye ezilmesi (bearing) modeli
# ===========================================================================
class TestUyeEzilmesiModeli:
    """Ölçüldü (M24 / 12.9 / 8 cıvata / 60 bar x 160 mm): çıktının hiçbir
    yerinde 'bearing'/'crush' geçen alan YOKTU ve varsayımlar listesinde de
    beyan yoktu; magnezyum üyede (akma 220 MPa) 1232,676 N·m tork
    öneriliyordu."""

    ORTAK = dict(pressure_bar=60.0, seal_diameter_mm=160.0, bolt_count=8,
                 size='M24', property_class='12.9', grip_length_mm=30.0)

    def test_magnezyum_uyede_ezilme_hukmu_cikar(self):
        r = _sessiz(analyze_bolted_joint,
                    member_material='magnesium_az31b', **self.ORTAK)
        b = r['bearing']
        assert b['member_yield_strength_MPa'] == pytest.approx(220.0)
        assert b['bearing_stress_MPa'] > b['member_yield_strength_MPa']
        assert b['bearing_safety_factor'] < 1.0
        assert b['member_crushing'] is True
        assert any('MEMBER CRUSHING' in w for w in r['warnings']), (
            'tork reçetesi uyarısız yayımlanıyordu')

    def test_dusuk_dayanimli_civata_celik_uyede_ezilme_uretmez(self):
        """Ayırt edicilik: model her koşulda 'eziliyor' demiyor.

        ÖLÇÜLDÜ (aynı yük, A2-70 paslanmaz cıvata / çelik üye):
        yatak gerilmesi 387,96 MPa, üye akması 460,0 MPa, SF 1,1847 ->
        ezilme YOK. Aynı üye 12.9 sınıfıyla eziliyor (SF 0,5033) — fark
        cıvatanın proof dayanımından, yani ön-yükten geliyor. Bu, pullu
        montajın neden standart olduğunun sayısal karşılığıdır ve
        varsayım listesinde 'WITHOUT a washer' olarak yazılıdır.
        """
        r = _sessiz(analyze_bolted_joint,
                    member_material='steel_4130',
                    **{**self.ORTAK, 'property_class': 'A2-70'})
        b = r['bearing']
        assert b['member_yield_strength_MPa'] == pytest.approx(460.0)
        assert b['bearing_safety_factor'] > 1.0
        assert b['member_crushing'] is False
        assert not [w for w in r['warnings'] if 'MEMBER CRUSHING' in w]

    def test_yatak_alani_iso_tablolarindan(self):
        """Sayı uydurulmadı: ISO 4014 d_w ⟷ ISO 273 delik."""
        import math
        r = _sessiz(analyze_bolted_joint,
                    member_material='steel_4130', **self.ORTAK)
        b = r['bearing']
        d_w = BOLT_BEARING_FACE_DIAMETER_MM['M24']
        d_h = BOLT_CLEARANCE_HOLE_DIAMETER_MM['M24']
        assert b['bearing_face_diameter_mm'] == d_w
        assert b['clearance_hole_diameter_mm'] == d_h
        assert b['bearing_area_mm2'] == pytest.approx(
            math.pi / 4.0 * (d_w ** 2 - d_h ** 2), rel=1e-9)

    def test_yatak_gerilmesi_maksimum_on_yuke_gore(self):
        """NASA-STD-5020A §6.2: akma/ezilme MAKSİMUM ön-yükte sınanır."""
        r = _sessiz(analyze_bolted_joint,
                    member_material='steel_4130', **self.ORTAK)
        b, y = r['bearing'], r['loads']
        assert b['bearing_stress_MPa'] * 1e6 == pytest.approx(
            y['bolt_total_load_max_preload_N']
            / (b['bearing_area_mm2'] * 1e-6), rel=1e-9)

    def test_varsayim_listesi_pulsuz_montaji_soyluyor(self):
        r = _sessiz(analyze_bolted_joint,
                    member_material='steel_4130', **self.ORTAK)
        assert any('WITHOUT a washer' in a for a in r['assumptions'])


# ===========================================================================
# P5B1-19 / P5B2-17 — fizik dışı sıcaklık kapısı
# ===========================================================================
class TestFizikDisiSicaklikKapisi:
    """Ölçüldü: ``pressure_vessel`` 1e9 K'yi KABUL ediyordu ve derating
    eğrisinin son noktasında sabitlendiği için sonuç 3000 K ile bit-aynı
    çıkıyordu (burst_margin 0,5869935949953238, retention 0,15).
    ``/analyze_structural_safety`` 1e9 / -500 / 50000 K'de HTTP 200 ve
    ``thermal_margin_ratio = 1233045,6226880394`` basıyordu."""

    A3_YAPISAL_ISTEK = {'chamber_pressure': 40, 'chamber_diameter': 0.1,
                        'chamber_length': 0.5, 'throat_diameter': 0.02,
                        'burn_time': 10, 'material': 'steel_4130',
                        'wall_thickness': 0.005}

    def test_bant_deponun_kanonik_tablosundan(self):
        from hrma.validation.motor_validation import MotorDataValidator
        limit = MotorDataValidator().limits['temperature']
        assert sicaklik_bandi_K() == (float(limit['min']),
                                      float(limit['max']))

    def test_kap_bir_milyar_kelvini_reddeder(self):
        with pytest.raises(ValueError) as exc:
            _sessiz(PressureVesselAnalyzer().analyze, meop_bar=60.0,
                    inner_diameter_mm=150.0, material='steel_4130',
                    wall_thickness_mm=5.0, temperature_K=1e9)
        assert 'temperature' in str(exc.value).lower()

    def test_kriyojenik_kap_hala_analiz_edilir(self):
        """Ayırt edicilik + a2 regresyonu: alt uca DOKUNULMADI."""
        r = _sessiz(PressureVesselAnalyzer().analyze, meop_bar=5.0,
                    inner_diameter_mm=400.0, material='ss_304',
                    wall_thickness_mm=8.0, temperature_K=20.0)
        assert r['status'] in ('PASS', 'MARGINAL', 'FAIL', 'NOT_EVALUATED')
        assert r['derating']['temperature_K'] == pytest.approx(20.0)

    @pytest.mark.parametrize('sicaklik', [1e9, -500, 50000])
    def test_yapisal_uc_fizik_disi_sicakligi_reddeder(self, istemci,
                                                     sicaklik):
        durum, govde = _post(istemci, '/analyze_structural_safety',
                             {**self.A3_YAPISAL_ISTEK,
                              'chamber_temperature': sicaklik})
        assert durum == 422, 'üçü de HTTP 200 alıyordu'
        assert 'chamber_temperature' in [
            f.get('field') for f in govde.get('invalid_fields', [])]

    def test_yapisal_uc_saglikli_sicakligi_kabul_eder(self, istemci):
        durum, _ = _post(istemci, '/analyze_structural_safety',
                         {**self.A3_YAPISAL_ISTEK, 'chamber_temperature': 3000})
        assert durum == 200

    @pytest.mark.parametrize('alan,deger', [
        ('wall_temperature_hot', -500.0),
        ('wall_temperature_hot', 1e9),
        ('chamber_temperature', 1e9),
    ])
    def test_modul_termal_kolu_fizik_disi_cidari_reddeder(self, alan, deger):
        md = dict(A3_MOTOR_YUKU)
        md[alan] = deger
        if alan == 'wall_temperature_hot':
            md['wall_temperature_cold'] = deger
        with pytest.raises(NonPhysicalSafetyInput) as exc:
            _sessiz(SafetyAnalyzer()._analyze_thermal_safety, md,
                    material='aluminum_6061')
        assert exc.value.field in ('wall_temperature_hot',
                                   'chamber_temperature')

    def test_eksi_500_K_cidar_artik_en_guvenli_hukmu_uretemez(self):
        """Kusurun kalbi: -500 K cidar SF=inf + 'Selected material
        acceptable' + termal risk 2,0 (kümenin EN GÜVENLİ hükmü)
        veriyordu."""
        md = dict(A3_MOTOR_YUKU, wall_temperature_hot=-500.0,
                  wall_temperature_cold=-500.0)
        with pytest.raises(NonPhysicalSafetyInput):
            _sessiz(SafetyAnalyzer()._analyze_thermal_safety, md,
                    material='aluminum_6061')

    def test_ucta_bir_milyar_kelvin_cidar_422(self, istemci):
        durum, govde = _post(istemci, '/analyze_safety', {
            **A3_EMNIYET_TABANI, 'wall_temperature_hot': 1e9,
            'wall_temperature_cold': 1e9})
        assert durum == 422, 'bu vaka HTTP 200 veriyordu'
        assert govde.get('error') == 'invalid_safety_input'


# ===========================================================================
# P5B2-07 — hibrit fuel_density sıfır katkı
# ===========================================================================
class TestSifirKatkiliParametre:
    """Ölçüldü: ``fuel_density`` +3σ'da (çarpan 1,06) altı sözleşme
    çıktısının ALTISINI DA bit-aynı bırakıyor."""

    KURUCU = {'thrust': 1000.0, 'burn_time': 10.0, 'of_ratio': 6.0,
              'chamber_pressure': 20.0, 'fuel_type': 'htpb',
              'oxidizer_type': 'n2o'}

    def test_sifir_katki_olcumu_iki_yonlu(self):
        """Liste bir İDDİA değil ÖLÇÜMDÜR: adı ±3σ ile sınarız.

        Bu test iki yönlü çalışır — listedeki bir ad katkı vermeye
        başlarsa da, listede olmayan bir ad sıfır katkılı çıkarsa da
        kırmızı verir.
        """
        fab = _sessiz(uq_adapters.make_hybrid_factory, dict(self.KURUCU))
        anahtarlar = uq_adapters.CONTRACT_OUTPUTS['hybrid']
        nominal = _sessiz(fab, {})
        olculen_sifir = set()
        for ad in ('fuel_density', 'regression_lambda', 'chamber_pressure'):
            for carpan in (0.94, 1.06):
                sapan = _sessiz(fab, {ad: carpan})
                if any(sapan.get(k) != nominal.get(k) for k in anahtarlar):
                    break
            else:
                olculen_sifir.add(ad)
        beyan = set(uq_adapters.ZERO_CONTRACT_INFLUENCE['hybrid'])
        assert olculen_sifir == (beyan & {'fuel_density',
                                          'regression_lambda',
                                          'chamber_pressure'}), (
            f'ölçülen sıfır-katkılı küme {sorted(olculen_sifir)}, beyan '
            f'{sorted(beyan)} — ZERO_CONTRACT_INFLUENCE güncellenmeli')

    def test_sifir_katkili_parametre_dagilimdan_dusurulur(self):
        """ÖH D26 fix-25a — ``fuel_density`` GERİ GELDİ, ``cd_injector`` kalır.

        Kural değişmedi ("ölçülen katkı sıfırsa düşür"); ölçüm değişti.
        Yukarıdaki iki yönlü bekçi parametrenin artık katkı verdiğini
        gösterdi (isp bağıl 2,2e-04, gürültü tabanının 8 mertebe üstünde),
        dolayısıyla düşürmenin dayanağı kalmadı. Düşürmeyi sürdürmek
        belirsizliği EKSİK bildirmek olurdu. Sahte-0 kaygısı bu satır için
        geçerli değil: ölçüldü, duyarlılık katsayıları 0 değil
        (isp ρ = -0,0562; regression_rate_avg ρ = +0,1335; seed 42, fast).
        ``cd_injector`` ise HÂLÂ dışarıda — o kurucuya hiç eşlenemiyor.
        """
        dag = uq_adapters.build_distributions('hybrid')
        assert 'cd_injector' not in dag, (
            'haritalanamayan ad dağılıma giremez — sahte 0 satırı')
        assert {'regression_lambda', 'regression_n_delta', 'eta_c_star',
                'chamber_pressure', 'fuel_density'} <= set(dag)

    def test_dusurulen_adin_gerekcesi_makine_okur(self):
        # ÖH D26 fix-25a: ``fuel_density`` düşürülen adlardan ÇIKTI (katkı
        # ölçüldü); geriye yalnız haritalanamayan ``cd_injector`` kalıyor.
        kayit = uq_adapters.withheld_distributions('hybrid')
        assert set(kayit) == {'cd_injector'}
        assert 'motor constructor' in kayit['cd_injector']


# ===========================================================================
# P5B2-11 — kopma basıncı hesaplanamayınca fail-open
# ===========================================================================
class TestBasincRiskiFailOpen:
    """Ölçüldü: ``burst_margin is None`` -> skor 2,0 (MEDIUM_PRESSURE
    tabanı) iken GERÇEKTEN ölçülmüş marj 1,5 -> 3,0. Yani 'değerlendirilemedi'
    bilinen-kötüden daha güvenli görünüyordu."""

    def test_olculemeyen_marj_skorlanmaz(self):
        skor = SafetyAnalyzer()._score_pressure_risk(
            {'vessel_classification': 'MEDIUM_PRESSURE', 'burst_margin': None})
        assert skor is None, 'eksik hesap düşük risk DEĞİLDİR'

    @pytest.mark.parametrize('marj,beklenen', [
        (5.0, 2.0), (1.5, 3.0), (1.1, 4.0), (0.8, 5.0)])
    def test_olculen_marjlarin_sayilari_degismedi(self, marj, beklenen):
        skor = SafetyAnalyzer()._score_pressure_risk(
            {'vessel_classification': 'MEDIUM_PRESSURE',
             'burst_margin': marj})
        assert skor == beklenen

    def test_olculemeyen_eksen_adiyla_yazilir_ve_onay_geri_cekilir(self):
        sa = SafetyAnalyzer()
        r = _sessiz(sa._calculate_overall_risk,
                    {'yield_safety_factor': 9.0},
                    {'vessel_classification': 'MEDIUM_PRESSURE',
                     'burst_margin': None},
                    {'thermal_verdict': 'issued',
                     'estimated_wall_temperature_k': 300.0},
                    {'tnt_equivalent_kg': 0.1},
                    {'toxic_hazard_level': 'NONE'},
                    {'auto_ignition_risk': {'risk_level': 'LOW'}})
        assert 'pressure' in r['risks_not_evaluated']
        assert r['overall_risk_score_is_partial'] is True
        assert r['acceptability'] == 'NOT_EVALUATED', (
            'kazanılmamış ACCEPTABLE geri çekilmeli')


# ===========================================================================
# P5B2-13 — thermal_stress_mpa hiçbir hükümde kullanılmıyor
# ===========================================================================
class TestTermalGerilmeHukmeGirer:
    """Ölçüldü (steel_4130, cidar 2801/400 K, 70 bar, Ø120 mm, 3 mm):
    ``thermal_stress_mpa = 4045,5205479452056`` (460 MPa akmanın 8,79 katı)
    yayımlanıyordu ama ``structural_integrity`` MARGINAL, yapısal eksen 2,0
    kalıyordu. Ayırt edici kanıt: skorlayıcıya gerilme 1,0 / 4045,5 / hiç
    verildiğinde ÜÇÜNDE DE aynı skor çıkıyordu."""

    SICAK = dict(A3_MOTOR_YUKU, wall_temperature_hot=2801.0,
                 wall_temperature_cold=400.0)

    @pytest.fixture(scope='class')
    def sonuc(self):
        return _sessiz(SafetyAnalyzer().analyze_comprehensive_safety,
                       dict(self.SICAK), 6.0, propellant_type='composite',
                       material='steel_4130', motor_type='solid')

    def test_termal_gerilme_sayisi_degismedi(self, sonuc):
        assert sonuc['thermal_safety']['thermal_stress_mpa'] == pytest.approx(
            4045.5205479452056, rel=1e-9)

    def test_gerilmenin_kiyasi_yayimlanir(self, sonuc):
        t = sonuc['thermal_safety']
        assert t['thermal_stress_safety_factor'] is not None
        assert t['thermal_stress_safety_factor'] < 1.0, (
            'cidar termal gradyanla tek başına akıyor')
        assert t['derated_yield_strength_MPa'] is not None
        assert t['thermal_stress_safety_factor'] == pytest.approx(
            t['derated_yield_strength_MPa'] / t['thermal_stress_mpa'],
            rel=1e-9)

    def test_yapisal_hukum_gerilmeyi_gorur(self, sonuc):
        s = sonuc['structural_safety']
        assert s['yield_safety_factor'] == pytest.approx(
            3.2857142857142856, rel=1e-9), 'basınç-tek katsayısı korunuyor'
        assert s['combined_safety_factor'] < 1.0
        assert s['governing_safety_factor'] == s['combined_safety_factor']
        assert s['structural_integrity'] == 'UNSAFE', (
            'MARGINAL bir kabuldü ve kazanılmamıştı')

    def test_yapisal_eksen_gerilmeyle_hareket_eder(self, sonuc):
        """Kusurun ayırt edici kanıtı: eksen artık sayıyı OKUYOR."""
        sa = SafetyAnalyzer()
        s = dict(sonuc['structural_safety'])
        yuksek = sa._score_structural_risk(s)
        s['governing_safety_factor'] = 9.0
        dusuk = sa._score_structural_risk(s)
        assert yuksek == 5.0 and dusuk == 1.0

    def test_termal_zincir_kosmadiginda_uydurma_yok(self):
        """Fail-closed: gerilme hesaplanamadıysa birleşik katsayı None."""
        sa = SafetyAnalyzer()
        s = {'hoop_stress_mpa': 140.0, 'yield_safety_factor': 3.28}
        sa._merge_thermal_stress_into_structural(
            s, {'thermal_verdict': 'withheld', 'thermal_stress_mpa': None,
                'derated_yield_strength_MPa': None})
        assert s['combined_safety_factor'] is None
        assert 'NOT EVALUATED' in s['combined_stress_basis']
        assert 'PRESSURE load only' in s['combined_stress_basis']


# ===========================================================================
# P5B2-14 — otomatik tutuşma serbest metne bakıyor
# ===========================================================================
class TestOtomatikTutusmaSinifCozer:
    """Ölçüldü: ``lox_rp1`` ve ``n2o4_mmh`` yangın SINIFI Class B çıkarken
    tutuşma riski LOW alıyor, sabit deluge önerisi hiç tetiklenmiyor ve
    yangın ekseni 3,0 yerine 2,0 oluyordu. ``apcp`` (2900 K) da LOW idi."""

    def _yangin(self, ptype, mtype, T=2900):
        return _sessiz(SafetyAnalyzer()._analyze_fire_hazards, ptype, 6.0,
                       {'chamber_temperature': T, 'motor_type': mtype})

    @pytest.mark.parametrize('ptype,mtype', [
        ('lox_rp1', 'liquid'), ('n2o4_mmh', 'liquid'),
        ('liquid_biprop', 'liquid'),
    ])
    def test_sivi_itici_adi_ne_olursa_olsun_MEDIUM(self, ptype, mtype):
        fh = self._yangin(ptype, mtype)
        assert fh['auto_ignition_risk']['risk_level'] == 'MEDIUM'
        assert SafetyAnalyzer()._score_fire_risk(fh) == 3.0
        assert any('Fixed remote-actuated deluge' in s
                   for s in fh['suppression_system']['systems'])

    @pytest.mark.parametrize('ptype', ['apcp', 'composite'])
    def test_sicak_kati_itici_MEDIUM(self, ptype):
        fh = self._yangin(ptype, 'solid')
        assert fh['auto_ignition_risk']['risk_level'] == 'MEDIUM'

    def test_soguk_kati_itici_LOW_kalir(self):
        """Ayırt edicilik: 2500 K eşiği korunuyor."""
        fh = self._yangin('composite', 'solid', T=1000)
        assert fh['auto_ignition_risk']['risk_level'] == 'LOW'
        assert SafetyAnalyzer()._score_fire_risk(fh) == 2.0

    def test_hukmun_dayanagi_yaziyor(self):
        fh = self._yangin('lox_rp1', 'liquid')
        air = fh['auto_ignition_risk']
        assert air['resolved_class'] == 'liquid_biprop'
        assert 'lox_rp1' in air['basis']

    def test_sinif_ve_tutusma_ayni_yanitta_celismiyor(self):
        """Kusurun kalbi: aynı yanıtta sınıf Class B, tutuşma LOW idi."""
        fh = self._yangin('lox_rp1', 'liquid')
        assert 'Class B' in fh['fire_classification']
        assert fh['auto_ignition_risk']['risk_level'] != 'LOW'


# ===========================================================================
# P5B2-15 / P5B2-16 — fizik dışı büyüklük ve sessiz kırpma
# ===========================================================================
class TestModulFizikKapisi:
    """Ölçüldü (modül yüzü): ``wall_thickness = 0`` ve
    ``chamber_diameter = 0`` çıplak ``ZeroDivisionError``,
    ``propellant_mass = -6`` ``TypeError`` (karmaşık sayı) veriyordu;
    ``thrust = -4000`` ise HÜKÜM basıp ``required_restraint_force_n``i
    sessizce 0,0 yapıyordu."""

    @pytest.mark.parametrize('alan,deger', [
        ('wall_thickness', 0), ('wall_thickness', -0.003),
        ('chamber_diameter', 0), ('chamber_diameter', -0.12),
        ('thrust', -4000.0), ('burn_time', -6.0),
    ])
    def test_fizik_disi_alan_adiyla_reddedilir(self, alan, deger):
        md = dict(A3_MOTOR_YUKU)
        md[alan] = deger
        with pytest.raises(NonPhysicalSafetyInput) as exc:
            _sessiz(SafetyAnalyzer().analyze_comprehensive_safety, md, 6.0,
                    propellant_type='composite', material='steel_4130',
                    motor_type='solid')
        assert exc.value.field == alan

    @pytest.mark.parametrize('kutle', [0.0, -6.0])
    def test_yakit_kutlesi_kapisi(self, kutle):
        with pytest.raises(NonPhysicalSafetyInput) as exc:
            _sessiz(SafetyAnalyzer().analyze_comprehensive_safety,
                    dict(A3_MOTOR_YUKU), kutle, propellant_type='composite',
                    material='steel_4130', motor_type='solid')
        assert exc.value.field == 'propellant_mass'

    def test_saglikli_motor_hala_hukum_uretir(self):
        r = _sessiz(SafetyAnalyzer().analyze_comprehensive_safety,
                    dict(A3_MOTOR_YUKU), 6.0, propellant_type='composite',
                    material='steel_4130', motor_type='solid')
        assert r['structural_safety']['hoop_stress_mpa'] == pytest.approx(
            140.0, rel=1e-9)
        assert r['explosive_hazards']['tnt_equivalent_kg'] == pytest.approx(
            2.52, rel=1e-9)

    @pytest.mark.parametrize('itki,sure', [(-4000.0, 6.0), (4000.0, -6.0),
                                           (0.0, 6.0)])
    def test_parca_kolu_sessizce_kirpmaz(self, itki, sure):
        with pytest.raises(NonPhysicalSafetyInput):
            _sessiz(SafetyAnalyzer()._calculate_fragment_hazards, 6.0,
                    itki, sure,
                    {'chamber_diameter': 0.12, 'wall_thickness': 0.003,
                     'chamber_length': 0.5}, 'steel_4130')

    def test_pozitif_itkide_baglama_kuvveti_degismedi(self):
        r = _sessiz(SafetyAnalyzer()._calculate_fragment_hazards, 6.0,
                    4000.0, 6.0,
                    {'chamber_diameter': 0.12, 'wall_thickness': 0.003,
                     'chamber_length': 0.5}, 'steel_4130')
        um = r['unrestrained_motor']
        assert um['required_restraint_force_n'] == pytest.approx(16000.0)
        assert um['total_impulse_ns'] == pytest.approx(24000.0)

    def test_uc_kapisi_fizik_disi_cidari_422_yapar(self, istemci):
        """UÇ kapısı (modül kapısı DEĞİL) — ÖH D17 / P5B2-15 ŞARTI.

        Eski adı ``test_uc_modul_kapisini_422ye_cevirir`` ve docstring'i
        "Modül kapısı çıplak 500'e düşmez" idi; AYIRT EDİCİ DEĞİLDİ.
        ÖLÇÜLDÜ (D17 once.json K4): ``wall_thickness = 0`` daha ucun kendi
        ``_collect_unphysical_fields`` kapısında 422 alıyor
        (``reason: must_be_positive``), yani ``except
        NonPhysicalSafetyInput`` dalı devre dışıyken bile bu test YEŞİL
        kalıyordu. Fable'ın önerdiği ayırt edici vaka
        (``wall_temperature_hot = 1e9``) da bu ağaçta ayırt edici DEĞİL:
        uçtaki ``_ust_sinir_ihlalleri`` onu ``above_physical_maximum`` ile
        yakalıyor (D16'da eklendi). Bu düğüm artık iddia ettiği şeyi —
        UCUN kapısını — ölçüyor; modül kapısının 422'ye çevrildiğini
        ``test_modul_kapisi_422ye_cevrilir`` sınıyor.
        """
        durum, govde = _post(istemci, '/analyze_safety',
                             {**A3_EMNIYET_TABANI, 'wall_thickness': 0})
        assert durum == 422
        assert govde.get('error') == 'invalid_safety_input'
        assert [a['field'] for a in govde['invalid_fields']] == [
            'wall_thickness']
        assert govde['invalid_fields'][0]['reason'] == 'must_be_positive'

    def test_modul_kapisi_422ye_cevrilir(self, istemci, monkeypatch):
        """AYIRT EDİCİ: uç kapısı DÜŞÜRÜLÜNCE modül kapısı 422 üretmeli.

        ÖH D17 / P5B2-15 (Fable-D15 ŞARTI). Uçtaki ön-denetim
        (``_collect_unphysical_fields`` + ``_ust_sinir_ihlalleri`` +
        ``_collect_non_text_fields``) fizik dışı alanı ZATEN yakaladığı
        için modül kapısının çevirisi normal yolda hiç sınanamıyor. Burada
        yalnız ÖN-DENETİM susturulur; istek modüle iner ve
        ``NonPhysicalSafetyInput`` yükselir. İddia: yanıt çıplak 500
        DEĞİL, kardeş 422 sözleşmesi + alan adı.

        ``except NonPhysicalSafetyInput`` dalı kaldırılırsa bu düğüm
        KIRMIZI olur (ters-mutasyon: mutasyon.json 'P5B2-15/modul-cevirisi').
        """
        import hrma.app as _app

        monkeypatch.setattr(_app, '_collect_unphysical_fields',
                            lambda *a, **k: [])
        monkeypatch.setattr(_app, '_ust_sinir_ihlalleri',
                            lambda *a, **k: [])
        durum, govde = _post(istemci, '/analyze_safety',
                             {**A3_EMNIYET_TABANI, 'wall_thickness': 0})
        assert durum == 422, f'çıplak {durum} — modül kapısı çevrilmiyor'
        assert govde.get('error') == 'invalid_safety_input'
        assert govde['invalid_fields'][0]['field'] == 'wall_thickness'
        assert govde['error'] == 'invalid_safety_input'
        assert 'wall_thickness' in [f['field']
                                    for f in govde['invalid_fields']]
