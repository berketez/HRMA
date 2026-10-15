"""ÖH Dalga-31 / yapisal-sistem a1 — onarım bekçileri.

Üç kalem:
  P5B1-15 + OH-D30-13 (çift kalem sınıfı: AD BÜTÜNÜ İDDİA EDİYOR)
      ``buckling_status`` bütün burkulmayı iddia ederken yalnız eksenel
      modu kapsıyordu; dış basınç modu hiçbir uygulanan basınçla
      karşılaştırılmıyordu.
  OH-D30-13
      ``actual_burst_pressure_bar`` adı ölçülmüş dayanım ima ediyordu;
      sayı iki kapalı-form korelasyonun minimumudur.
  P7B2-23
      ``/api/slosh-analysis`` ret gövdesi makine-okur değildi
      (``invalid_fields`` yok) ve tank yarıçapı büyüklük ekseninde hiçbir
      zarf beyanı yayımlanmıyordu.

Ölçümler: docs/scofield/raw/OH/D31/yapisal-sistem/a1/{once,sonra}.json
"""
import math

import pytest

from hrma.analysis.structural_analysis import (
    StructuralAnalyzer,
    BUCKLING_VERDICT_NOT_EVALUATED,
    BUCKLING_SF_CRITICAL_BELOW,
    BUCKLING_SF_MARGINAL_BELOW,
    BUCKLING_GROUND_REFERENCE_PRESSURE_PA,
)
from hrma.analysis.pressure_vessel import PressureVesselAnalyzer
from hrma.analysis.slosh_analysis import (
    analyze_slosh, SloshGirdiHatasi, SLOSH_RADIUS_BAND,
    SLOSH_BOND_NUMBER_LOWER_LIMIT,
)
from hrma.constants import P_SEA_LEVEL_PA


@pytest.fixture(scope='module')
def analyzer():
    return StructuralAnalyzer()


@pytest.fixture(scope='module')
def mat(analyzer):
    return analyzer.materials['steel_4130']


# ===========================================================================
# P5B1-15 — dış basınç modu artık bir hükme bağlı
# ===========================================================================
class TestP5B1_15DisBasincZarfi:

    @pytest.mark.parametrize('t,p_cr_beklenen', [
        (0.0005, 0.000539316147125445),
        (0.001, 0.00431452917700356),
        (0.005, 0.5393161471254451),
    ])
    def test_kazanilmamis_safe_kalkti(self, analyzer, mat, t, p_cr_beklenen):
        """ÖLÇÜLDÜ (once.json K1): üç kalınlıkta da kritik dış basınç 1 atm
        ALTINDA iken ``buckling_status = 'SAFE'`` ve SF = inf idi.

        Yük durumu beyan edilmediğinde hüküm KAZANILMAMIŞTIR: dış basınç
        modu NOT_EVALUATED, birleşik hüküm de NOT_EVALUATED olmalıdır.
        Eksenel modun kendi hükmü ayrı adla durur.
        """
        out = analyzer._check_buckling(5e5, 0.5, t, 2.0, mat)
        assert out['critical_external_pressure_bar'] == pytest.approx(
            p_cr_beklenen, rel=1e-9)
        assert out['critical_external_pressure_bar'] < 1.01325
        assert out['external_buckling_status'] == BUCKLING_VERDICT_NOT_EVALUATED
        assert out['external_buckling_safety_factor'] is None
        assert out['applied_external_pressure_bar'] is None
        # KAZANILMAMIŞ ONAY YAYIMLANMAZ:
        assert out['buckling_status'] == BUCKLING_VERDICT_NOT_EVALUATED
        assert out['buckling_status'] != 'SAFE'
        # Eksenel mod kendi adıyla durur (yük yok -> SF = inf -> SAFE):
        assert out['axial_buckling_status'] == 'SAFE'
        assert math.isinf(out['axial_buckling_safety_factor'])

    def test_yer_senaryosu_hukum_uretir(self, analyzer, mat):
        """Zarf: max(p_dis - p_ic_min, 0). 1 atm dış / 0 iç -> CRITICAL."""
        out = analyzer._check_buckling(
            5e5, 0.5, 0.0005, 2.0, mat,
            external_pressure=P_SEA_LEVEL_PA, internal_pressure_min=0.0)
        assert out['applied_external_pressure_bar'] == pytest.approx(1.01325)
        sf = out['external_buckling_safety_factor']
        assert sf is not None and sf < BUCKLING_SF_CRITICAL_BELOW
        assert sf == pytest.approx(
            out['critical_external_pressure_bar'] / 1.01325, rel=1e-9)
        assert out['external_buckling_status'] == 'CRITICAL'
        # Birleşik hüküm en kötü modu alır.
        assert out['buckling_status'] == 'CRITICAL'

    def test_gercek_motor_cidari_safe_kalir(self, analyzer, mat):
        """Ø150 mm / 3 mm cidar: dış basınç modu rahatça geçer.

        Onarım ürünü sahte kırmızıya boğmuyor — zarf beyan edildiğinde
        gerçek bir motor cidarı SAFE alır.
        """
        out = analyzer._check_buckling(
            5e5, 0.075, 0.003, 0.5, mat,
            external_pressure=P_SEA_LEVEL_PA, internal_pressure_min=0.0)
        assert out['external_buckling_safety_factor'] > BUCKLING_SF_MARGINAL_BELOW
        assert out['external_buckling_status'] == 'SAFE'
        assert out['buckling_status'] == 'SAFE'

    def test_zarf_sifira_cokunce_not_evaluated(self, analyzer, mat):
        """İç basınç dışa eşit/üstünse zarf 0'dır; bu SAFE DEĞİL,
        NOT_EVALUATED'dır (kazanılmamış onay yasağı)."""
        out = analyzer._check_buckling(
            5e5, 0.5, 0.0005, 2.0, mat,
            external_pressure=P_SEA_LEVEL_PA,
            internal_pressure_min=P_SEA_LEVEL_PA)
        assert out['applied_external_pressure_bar'] == pytest.approx(0.0)
        assert out['external_buckling_status'] == BUCKLING_VERDICT_NOT_EVALUATED
        assert out['external_buckling_safety_factor'] is None
        assert out['buckling_status'] == BUCKLING_VERDICT_NOT_EVALUATED

    def test_ic_basinc_min_verilmezse_bosluk_alinir(self, analyzer, mat):
        """``internal_pressure_min`` verilmezse 0 (tam boşluk) — zarfın en
        konservatif hâli; sessizce 'ortam basıncı' varsayılmaz."""
        a = analyzer._check_buckling(5e5, 0.5, 0.005, 2.0, mat,
                                     external_pressure=P_SEA_LEVEL_PA)
        b = analyzer._check_buckling(5e5, 0.5, 0.005, 2.0, mat,
                                     external_pressure=P_SEA_LEVEL_PA,
                                     internal_pressure_min=0.0)
        assert (a['applied_external_pressure_bar']
                == pytest.approx(b['applied_external_pressure_bar']))
        assert a['external_buckling_status'] == b['external_buckling_status']

    def test_kapsam_kunyesi_adiyla_yazar(self, analyzer, mat):
        """``buckling_status`` hangi modları kapsadığını ADIYLA söyler."""
        out = analyzer._check_buckling(5e5, 0.5, 0.005, 2.0, mat)
        kapsam = out['buckling_status_scope']
        assert 'axial_buckling_status' in kapsam
        assert 'external_buckling_status' in kapsam
        assert 'NOT_EVALUATED' in kapsam
        # Yer referansı ADIYLA yayımlanır ama KENDİLİĞİNDEN uygulanmaz.
        # SAYISAL yaprak olarak basılmaz (sıfır eşikli sabit yaprak
        # envanteri, ÖK-22); değer künye METNİNDE adıyla geçer.
        assert ('%.5f bar' % (BUCKLING_GROUND_REFERENCE_PRESSURE_PA / 1e5)
                in out['ground_reference_source'])
        assert 'P_SEA_LEVEL_PA' in out['ground_reference_source']
        assert 'ground_reference_external_pressure_bar' not in out
        assert out['applied_external_pressure_bar'] is None

    def test_karsilastirma_alani_var(self, analyzer, mat):
        """test_structural_validation.py:244 sözleşmesi (borç imi kaldırıldı):
        1 atm altı kritik basınçta ya karşılaştırma alanı olmalı ya da
        hüküm SAFE olmamalı. Artık İKİSİ de sağlanıyor."""
        out = analyzer._check_buckling(5e5, 0.5, 0.0005, 2.0, mat)
        karsilastirma = [k for k in out
                         if 'external' in k.lower()
                         and any(s in k.lower() for s in
                                 ('applied', 'safety', 'margin', 'status'))]
        assert karsilastirma
        assert out['buckling_status'] != 'SAFE'

    def test_motor_yolu_yuk_durumunu_tasir(self, analyzer):
        """``analyze_structure`` zarfı motor gövdesinden geçirir."""
        motor = {'chamber_pressure': 50.0, 'chamber_diameter': 0.15,
                 'chamber_length': 0.5, 'throat_diameter': 0.05,
                 'burn_time': 10.0, 'thrust': 5.0e5}
        yok = analyzer.analyze_structure(motor, material='steel_4130')
        assert (yok['buckling_analysis']['external_buckling_status']
                == BUCKLING_VERDICT_NOT_EVALUATED)
        var = analyzer.analyze_structure(
            dict(motor, external_pressure=P_SEA_LEVEL_PA,
                 internal_pressure_min=0.0), material='steel_4130')
        assert var['buckling_analysis']['external_buckling_safety_factor'] is not None
        assert (var['buckling_analysis']['applied_external_pressure_bar']
                == pytest.approx(1.01325))


# ===========================================================================
# OH-D30-13 — 'actual' ölçülmüş demek değildir
# ===========================================================================
class TestOHD30_13KopmaBasinciAdi:

    @pytest.fixture(scope='class')
    def kap(self):
        return PressureVesselAnalyzer().analyze(
            meop_bar=60.0, inner_diameter_mm=150.0,
            wall_thickness_mm=3.0, material='steel_4130')

    def test_kunye_modeli_adiyla_beyan_eder(self, kap):
        """ÖLÇÜLDÜ (once.json K2): künye YOKTU (kunye_var_mi=false)."""
        kunye = kap['actual_burst_pressure_basis']
        assert 'MODEL PREDICTION' in kunye
        assert 'not a measured strength' in kunye
        assert 'Faupel' in kunye
        assert 'No hydrostatic burst test' in kunye

    def test_durust_ad_ayni_sayiyi_basar(self, kap):
        """Dürüst ad EKLENİR, eski ad KIRILMAZ — ikisi bit-aynı."""
        assert kap['predicted_burst_pressure_bar'] == pytest.approx(
            kap['actual_burst_pressure_bar'], rel=0, abs=0)
        # Sayı min(Faupel, ince cidar) olmayı sürdürür (çapa).
        assert kap['actual_burst_pressure_bar'] == pytest.approx(
            min(kap['burst_faupel_bar'], kap['burst_thin_wall_bar']),
            rel=1e-12)

    def test_safety_analysis_kunyeyi_tasir(self):
        """Panelin okuduğu ``pressure_safety`` bloğu künyeyi taşımalı;
        aksi hâlde ekrandaki alan adı tek başına 'ölçülmüş' der."""
        from hrma.analysis.safety_analysis import SafetyAnalyzer
        sa = SafetyAnalyzer()
        res = sa._analyze_pressure_vessel_safety(
            chamber_pressure=40.0, diameter=0.1, wall_thickness=0.002,
            material='steel_4130')
        assert res['actual_burst_pressure_bar'] is not None
        assert 'MODEL PREDICTION' in (res['actual_burst_pressure_basis'] or '')
        assert res['predicted_burst_pressure_bar'] == pytest.approx(
            res['actual_burst_pressure_bar'], rel=0, abs=0)


# ===========================================================================
# P7B2-23 — makine-okur ret + büyüklük ekseni beyanı
# ===========================================================================
@pytest.fixture(scope='module')
def istemci():
    from hrma.app import app
    app.config['TESTING'] = True
    return app.test_client()


class TestP7B2_23SloshRetGovdesi:

    @pytest.mark.parametrize('govde,alan,sebep', [
        ({'radius': 0.5, 'fill_height': 1.0,
          'control_frequencies': ['abc']}, 'control_frequencies',
         'not_a_number'),
        ({'radius': 0.5, 'fill_height': 1.0,
          'control_frequencies': 'abc'}, 'control_frequencies',
         'not_a_number'),
        ({'radius': 0.5, 'fill_height': -1.0}, 'fill_height',
         'not_positive'),
        ({'radius': 'abc', 'fill_height': 1.0}, 'radius', 'not_a_number'),
        ({'fill_height': 1.0}, 'radius', 'required'),
        ({'radius': 0.5}, 'fill_height', 'required'),
        ({'radius': 0.5, 'fill_height': 1.0,
          'coincidence_margin': 5.0}, 'coincidence_margin',
         'above_band_maximum'),
    ])
    def test_ret_govdesi_makine_okur(self, istemci, govde, alan, sebep):
        """ÖLÇÜLDÜ (once.json K3): dört ret vakasının dördünde de
        ``invalid_fields`` anahtarı gövdede YOKTU; hangi alanın
        reddedildiği yalnız İngilizce cümleden çıkarılabiliyordu."""
        r = istemci.post('/api/slosh-analysis', json=govde)
        assert r.status_code == 400
        j = r.get_json()
        assert 'invalid_fields' in j, j
        assert j['invalid_fields'], j
        kayit = j['invalid_fields'][0]
        assert kayit['field'] == alan
        assert kayit['reason'] == sebep
        # Serbest metin AYNEN durur (mevcut tüketiciler kırılmaz).
        assert j['error'] == kayit['message']

    def test_iki_kol_ayni_dili_konusur(self, istemci):
        """D29 onarımı (liste/dize kolu tek cümle) YÜRÜRLÜKTE kalır ve
        artık künyeleri de aynıdır."""
        a = istemci.post('/api/slosh-analysis', json={
            'radius': 0.5, 'fill_height': 1.0,
            'control_frequencies': ['abc']}).get_json()
        b = istemci.post('/api/slosh-analysis', json={
            'radius': 0.5, 'fill_height': 1.0,
            'control_frequencies': 'abc'}).get_json()
        assert a['error'] == b['error']
        assert a['invalid_fields'] == b['invalid_fields']

    def test_saglikli_govde_200_kalir(self, istemci):
        r = istemci.post('/api/slosh-analysis', json={
            'radius': 0.5, 'fill_height': 1.0, 'fluid_density': 1000.0})
        assert r.status_code == 200
        s = r.get_json()['slosh']
        assert s['f1_hz'] == pytest.approx(0.9558086926296774, rel=1e-12)
        assert 'invalid_fields' not in r.get_json()


class TestP7B2_23BuyuklukEkseni:

    def test_bant_yok_beyani_adiyla(self):
        """ÖLÇÜLDÜ (once.json K3 ``buyukluk_ekseni_2e6``): radius =
        fill_height = 2e6 m HTTP 200 + f1_hz = 0,00046632 veriyordu ve
        gövdede tek bir zarf/büyüklük alanı YOKTU.

        Kanonik bant YOK; bant UYDURULMAZ — yokluğu ve NEDEN
        değerlendirilemediği adıyla yayımlanır.
        """
        s = analyze_slosh(radius=2e6, fill_height=2e6, fluid_density=1000.0)
        z = s['size_envelope']
        assert z['canonical_radius_band_m'] is SLOSH_RADIUS_BAND is None
        assert z['radius_band_status'] == 'not_declared'
        assert z['radius_gate_applied'] is False
        assert z['bond_number'] is None
        assert z['bond_number_status'] == 'not_evaluated'
        assert z['missing_input_for_bond_number'] == 'surface_tension'
        # Eşik SAYISAL yaprak değil; metinde adıyla geçer (ÖK-22).
        assert 'bond_number_lower_limit' not in z
        assert ('Bo ~ %g' % SLOSH_BOND_NUMBER_LOWER_LIMIT) in z['basis']
        assert 'SP-106' in z['basis'] and 'Dodge' in z['basis']
        assert 'Bond number' in z['basis']
        assert 'scale-free' in z['basis']

    def test_beyan_saglikli_govdede_de_var(self, istemci):
        """Zarf beyanı yalnız uç vakada değil, HER yanıtta iner."""
        j = istemci.post('/api/slosh-analysis', json={
            'radius': 0.5, 'fill_height': 1.0}).get_json()
        assert j['slosh']['size_envelope']['radius_band_status'] \
            == 'not_declared'

    def test_hata_sinifi_valueerror_alt_sinifidir(self):
        """Mevcut tüketiciler ``except ValueError`` ile yakalamayı sürdürür."""
        assert issubclass(SloshGirdiHatasi, ValueError)
        with pytest.raises(ValueError):
            analyze_slosh(radius=-1.0, fill_height=1.0)


# ===========================================================================
# P15B2-01 / OH-D30-08 dağıtımı — iki yerel değer kapısı merkeze bağlandı
# ===========================================================================
class TestP15B201MerkeziKapi:
    """``_structural_input_gate`` ve ``_fizik_disi_degilse`` artık
    ``hrma.utils.input_guard`` merkezini kullanır. Hüküm BİT-AYNI kalır;
    bekçi kuralın MERKEZDEN geldiğini ve ayrışmadığını sınar."""

    def test_structural_kapi_merkezi_kurali_kullanir(self, analyzer):
        from hrma.utils.input_guard import is_json_number
        from hrma.analysis import structural_analysis as sa
        assert sa.is_json_number is is_json_number
        # Aynı kötü girdi, aynı hüküm: dize ve bool sayı DEĞİLDİR.
        gecersiz, _ = sa._structural_input_gate({'chamber_pressure': '40.0'})
        assert [g['reason'] for g in gecersiz] == ['not_a_number']
        gecersiz, _ = sa._structural_input_gate({'chamber_pressure': True})
        assert [g['reason'] for g in gecersiz] == ['not_a_number']
        # Geçerli sayı geçer (davranış değişmedi).
        gecersiz, _ = sa._structural_input_gate({'chamber_pressure': 40.0})
        assert gecersiz == []

    def test_safety_kapi_merkezi_kurali_kullanir(self):
        from hrma.utils.input_guard import finite_number
        from hrma.analysis import safety_analysis as sfa
        assert sfa.finite_number is finite_number
        with pytest.raises(sfa.NonPhysicalSafetyInput):
            sfa._fizik_disi_degilse('chamber_pressure', float('nan'))
        with pytest.raises(sfa.NonPhysicalSafetyInput):
            sfa._fizik_disi_degilse('chamber_pressure', float('inf'))
        with pytest.raises(sfa.NonPhysicalSafetyInput):
            sfa._fizik_disi_degilse('chamber_pressure', True)
        assert sfa._fizik_disi_degilse('chamber_pressure', 40.0) == 40.0
