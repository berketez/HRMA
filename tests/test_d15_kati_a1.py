# -*- coding: utf-8 -*-
"""ÖH Dalga-15 · katı motor · aşama 1 — sekiz onarımın bekçisi.

Her sınıf TEK bir kalemi tutar ve kalemin ONARIMDAN ÖNCEKİ davranışını
reddeder; onarım geçici olarak geri alındığında (ters mutasyon) kırmızıya
döner. Ölçüm dosyaları: ``docs/scofield/raw/OH/D15/kati/a1/once.json`` ve
``sonra.json``; üreten betik aynı dizindeki ``olcum.py``.

Kapsanan kalemler:
  P2B1-02  form varsayılanı yakıt tablosunu ezemez
  P2B1-04  KNSU 65/35 tek kayıttan türer, yalnız yoğunluk tabanı ayrışır
  P2B1-10  katalog adı kendi kaydına döner (ayırt edici parça atılmaz)
  P2B2-02  material_utilization_percent = 100·sigma/sigma_y
  P2B2-06  star/wagon_wheel port kesiti GERÇEK poligondur
  P2B2-08  yayımlanan Isp kullanıcının diverjan yarı açısını görür
  P2B2-09  irtifa satırının CF/Isp'si o satırın KENDİ (kırpılmış) lülesinindir
  P2B2-12  kapak birleşimi kasa malzemesini görür; göremiyorsa boyutlandırmaz
"""

import math
import warnings

import pytest

from hrma.constants import G_0
from hrma.data.propellants_db import PROPELLANTS
from hrma.engines.solid_rocket_engine import (
    SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG,
    SolidRocketEngine,
    _catalog_key_from_text,
    _conical_divergence_efficiency,
)

TABAN = dict(grain_type='bates', propellant_type='apcp',
             chamber_diameter=100, grain_length=500,
             core_diameter=30, chamber_pressure=40)


def _motor(**kw):
    p = dict(TABAN)
    p.update(kw)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return SolidRocketEngine(**p)


def _sessiz(fn, *a, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return fn(*a, **kw)


# ---------------------------------------------------------------------------
# P2B1-02 — form varsayılanı kalibre tablo değerini ezemez
# ---------------------------------------------------------------------------
class TestFormVarsayilaniTabloyuEzemez:
    """solid.html her koşuda erosive_k=0.0002 ve temp_coeff=0.002 gönderir
    (kullanıcı alana dokunmasa da). Bu değerlerin literatür dayanağı yok,
    APCP tablosunun k=0,0136'sının var — ve fark 68 kat. Ölçülen bedel:
    erozif-duyarlı motorda tepe itki 13.423 -> 7.851 N (-%41,5)."""

    EROZIF = dict(chamber_diameter=100, grain_length=1000, core_diameter=12,
                  chamber_pressure=40)
    FORM = {'erosive_k': 0.0002, 'temp_coeff': 0.002}

    def test_beyansiz_form_degeri_uygulanmaz(self):
        tablo = _motor()
        form = _motor(overrides=dict(self.FORM))
        assert tablo.erosive_burning_coeff == pytest.approx(0.0136)
        assert form.erosive_burning_coeff == pytest.approx(
            tablo.erosive_burning_coeff, rel=0, abs=0), (
            'beyan edilmemiş form varsayılanı yakıt tablosunu ezdi')
        assert form.burn_rate_temp_coeff == pytest.approx(
            tablo.burn_rate_temp_coeff, rel=0, abs=0)

    def test_beyanli_kullanici_degeri_hala_uygulanir(self):
        """Kural 'kullanıcıyı yok say' değil, 'beyansız form varsayılanını
        yok say'dır: bayrak gelince değer aynen uygulanır."""
        ov = dict(self.FORM, erosive_k_override=True, temp_coeff_override=True)
        e = _motor(overrides=ov)
        assert e.erosive_burning_coeff == pytest.approx(0.0002)
        assert e.burn_rate_temp_coeff == pytest.approx(0.002)

    def test_urun_yuzunde_tepe_itki_gerceklesir(self):
        tablo = _sessiz(_motor(**self.EROZIF).calculate_thrust_curve)
        form = _sessiz(
            _motor(overrides=dict(self.FORM), **self.EROZIF)
            .calculate_thrust_curve)
        assert max(form['thrust']) == pytest.approx(max(tablo['thrust']),
                                                    rel=1e-9)
        assert max(tablo['thrust']) > 12000.0, (
            'erozif yanma kapanmış görünüyor')

    def test_kunye_uygulanmayan_form_degerini_soyler(self):
        """Beyan çözüm değildir ama gerçeği söylemek zorundadır: sayının
        kaynağı ve GÖZ ARDI EDİLEN form değeri yayımlanır."""
        r = _sessiz(_motor(overrides=dict(self.FORM)).calculate_performance)
        kaynak = (r['detailed_analysis']['grain_regression_analysis']
                  ['erosive_burning_effects']['erosive_coefficient_k_source'])
        assert 'propellant table' in kaynak
        assert '0.0002' in kaynak and 'NOT applied' in kaynak
        assert 'erosive_k_override' in kaynak
        sigma = (r['environmental_analysis']['temperature_effects']
                 ['sigma_p_source'])
        assert 'temp_coeff' in sigma and 'NOT applied' in sigma

    def test_kalibre_deger_yoksa_kullanici_degeri_uygulanir(self):
        """Jenerik yakıtta tablo katsayısı YOK; orada form değeri tek
        kaynaktır ve uygulanır (fail-closed 'hiç kullanma' değildir)."""
        e = _motor(propellant_type='hayali_yakit',
                   overrides=dict(self.FORM))
        assert e.erosive_burning_coeff == pytest.approx(0.0002)


# ---------------------------------------------------------------------------
# P2B1-04 — KNSU 65/35: tek kimya, iki yoğunluk tabanı
# ---------------------------------------------------------------------------
class TestKnsuTekKayittanTurer:
    """'sugar' ve 'knsu' aynı bileşimdir (KNO3 %65 / sakaroz %35) ve
    termokimyaları zaten aynıydı; ikincil katsayıların ayrışması (erozif
    +%26, sigma_p +%9,8, nozul verimi 0,978 ⟷ 0,983) veri ikilemesiydi."""

    KIMYA = ('c_star', 'gamma', 'T_c', 'mw_exhaust', 'nozzle_efficiency',
             'burn_rate_temp_coeff', 'erosive_burning_coeff')

    def test_bilesimden_turemis_her_katsayi_ayni(self):
        a, b = _motor(propellant_type='sugar'), _motor(propellant_type='knsu')
        for alan in self.KIMYA:
            assert getattr(a, alan) == pytest.approx(getattr(b, alan),
                                                     rel=0, abs=0), alan

    def test_yalnizca_yogunluk_ayrisir_ve_adinda_yazar(self):
        a, b = _motor(propellant_type='sugar'), _motor(propellant_type='knsu')
        assert a.rho_p == pytest.approx(1785)
        assert b.rho_p == pytest.approx(1889)
        assert 'cast bulk' in a.propellant_name.lower()
        assert 'ideal' in b.propellant_name.lower()


# ---------------------------------------------------------------------------
# P2B1-10 — katalog adı kendi kaydına döner
# ---------------------------------------------------------------------------
class TestKatalogAdiKendiKaydinaDoner:
    """Ad çözümü ayraçtan önceki ilk parçayı deniyordu; niteleyici
    ('(non-aluminized)', '(cast bulk density)') eşleşmeden ÖNCE atılıyordu."""

    @pytest.mark.parametrize('anahtar', sorted(PROPELLANTS))
    def test_her_ad_kendi_anahtarina_coz(self, anahtar):
        ad = PROPELLANTS[anahtar].get('name')
        assert _catalog_key_from_text(ad) == anahtar, ad

    def test_metalsiz_apcp_aluminyumlu_kayda_dusmez(self):
        e = _motor(overrides={
            'propellant_name': 'AP/HTPB Composite (non-aluminized)'})
        assert e.propellant_type == 'apcp_nonaluminized'
        assert e.T_c == pytest.approx(2550.0), (
            'alüminyumlu APCP alev sıcaklığı (3614,8 K) devralınmış')

    def test_serbest_metin_yolu_hala_calisiyor(self):
        """Kısaltma yolu kaldırılmadı: katalog adı olmayan serbest metinde
        ilk parça hâlâ anahtarı verir."""
        assert _catalog_key_from_text('KNDX - kendi karisimim') == 'kndx'
        assert _catalog_key_from_text('boyle bir yakit yok') is None


# ---------------------------------------------------------------------------
# P2B2-02 — malzeme kullanım oranı
# ---------------------------------------------------------------------------
class TestMalzemeKullanimOrani:
    """Alan 100/SF*2.0 idi; 2,0 çarpanının kodda/künyede dayanağı yoktu ve
    SF=1,5 ile %133,3 gibi imkânsız çiftler yayımlanıyordu."""

    VAKALAR = [({}, 40), ({'case_thickness': 2.0}, 40),
               ({'case_thickness': 3.0}, 100), ({'case_thickness': 1.0}, 100)]

    @pytest.mark.parametrize('ov,pc', VAKALAR)
    def test_oran_gerilme_dayanim_oranidir(self, ov, pc):
        e = _motor(overrides=dict(ov), chamber_pressure=pc)
        s = _sessiz(e._calculate_structural_analysis)['case_analysis']
        beklenen = 100.0 * s['hoop_stress_mpa'] / s['yield_strength_mpa']
        assert s['material_utilization_percent'] == pytest.approx(beklenen,
                                                                  rel=1e-12)
        assert s['material_utilization_percent'] == pytest.approx(
            100.0 / s['safety_factor'], rel=1e-12)

    def test_emniyetli_kasada_yuzde_yuz_asilmaz(self):
        e = _motor(overrides={'case_thickness': 3.0}, chamber_pressure=100)
        s = _sessiz(e._calculate_structural_analysis)['case_analysis']
        assert s['safety_factor'] > 1.0
        assert s['material_utilization_percent'] < 100.0, (
            'SF > 1 iken kullanım %100 üstü olamaz')


# ---------------------------------------------------------------------------
# P2B2-06 — star / wagon_wheel port kesiti
# ---------------------------------------------------------------------------
class TestPortKesitiGercekPoligon:
    """Modülün kendi gerekçesi (slotted için 'dairesel yaklaşıklık akıyı
    %30'a varan oranda şişirir') star ve wagon_wheel'e uygulanmamıştı;
    ölçülen şişme %75-173."""

    @pytest.mark.parametrize('tip', ['star', 'wagon_wheel'])
    @pytest.mark.parametrize('w_mm', [0.0, 5.0, 10.0])
    def test_alan_gercek_poligondan_gelir(self, tip, w_mm):
        shapely = pytest.importorskip(
            'shapely',
            reason='star/wagon_wheel gerçek kesiti poligon ofsetiyle '
                   'hesaplanır; shapely olmadan bu bekçi ölçüm yapamaz '
                   '(kurulum: pip install shapely)')
        assert shapely is not None
        e = _motor(grain_type=tip)
        w = w_mm / 1000.0
        gercek = e._offset_port_area(e._grain_port_polygon(), w)
        assert e._port_flow_area(w) == pytest.approx(gercek, rel=1e-12)

    @pytest.mark.parametrize('tip', ['star', 'wagon_wheel'])
    def test_dairesel_esdegerden_olculebilir_bicimde_ayrilir(self, tip):
        pytest.importorskip(
            'shapely',
            reason='gerçek kesit poligon ofseti gerektirir (pip install '
                   'shapely)')
        e = _motor(grain_type=tip)
        dairesel = math.pi * (e.D_core / 2) ** 2
        assert e._port_flow_area(0.0) > 1.5 * dairesel, (
            'kesit hâlâ dairesel eşdeğerle hesaplanıyor')

    def test_bates_kapali_formda_kalir(self):
        """BATES portu GERÇEKTEN dairedir; onu poligona çevirmek gereksiz
        maliyet ve gürültü olurdu."""
        e = _motor(grain_type='bates')
        for w in (0.0, 0.005, 0.010):
            assert e._port_flow_area(w) == pytest.approx(
                math.pi * (e.D_core / 2 + w) ** 2, rel=1e-12)


# ---------------------------------------------------------------------------
# P2B2-08 — diverjan yarı açısı performansa girer
# ---------------------------------------------------------------------------
class TestDiverjansAcisiIspyeGirer:
    """Çizilen/ihraç edilen lüle kullanıcının açısındaydı, yayımlanan Isp
    15 derecelik referans verimdeydi: 15/20/30/45 derecede Isp bit-özdeşti
    ve aynı yanıt %14,64 diverjans kaybını 'verimin içinde' ilan ediyordu."""

    def test_isp_aciya_bagli(self):
        i15 = _sessiz(_motor(overrides={'divergent_angle': 15.0})
                      .calculate_performance)['specific_impulse']
        i45 = _sessiz(_motor(overrides={'divergent_angle': 45.0})
                      .calculate_performance)['specific_impulse']
        assert i45 < i15 * 0.95, 'Isp hâlâ açıdan bağımsız'

    @pytest.mark.parametrize('aci', [20.0, 30.0, 45.0])
    def test_oran_lambda_oranidir(self, aci):
        taban = _sessiz(_motor(overrides={
            'divergent_angle': SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG})
            .calculate_performance)['specific_impulse']
        olculen = _sessiz(_motor(overrides={'divergent_angle': aci})
                          .calculate_performance)['specific_impulse']
        beklenen = _conical_divergence_efficiency(aci) / \
            _conical_divergence_efficiency(
                SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG)
        assert olculen / taban == pytest.approx(beklenen, rel=1e-9)

    def test_referans_acida_davranis_degismez(self):
        """15 derece = tablo veriminin referansı; orada çarpan tam 1.0."""
        e = _motor(overrides={
            'divergent_angle': SOLID_NOZZLE_REFERENCE_HALF_ANGLE_DEG})
        assert e._divergence_efficiency_correction() == 1.0
        assert _motor()._divergence_efficiency_correction() == 1.0

    def test_kunye_kaybin_verimin_icinde_oldugunu_iddia_etmez(self):
        e = _motor(overrides={'divergent_angle': 45.0})
        kayip = e._isp_loss_breakdown(100.0)
        assert kayip['divergence_efficiency_applied'] < 0.90
        assert kayip['nozzle_losses'] > kayip['divergence_losses'] * 0.9, (
            'toplam nozul kaybı diverjans kaybını kapsayamıyor — künye '
            'aritmetik olarak yanlışlanıyor')


# ---------------------------------------------------------------------------
# P2B2-09 — irtifa satırının CF/Isp'si kendi lülesinin
# ---------------------------------------------------------------------------
class TestIrtifaSatiriKendiLulesini_Yayimlar:
    """ε [2,5; 500] bandına kırpılıyor ama CF/Isp optimum-genişleme
    formülünden geliyordu: deniz seviyesinde %12,25 fazla Isp."""

    @staticmethod
    def _gercek_isp(e, satir):
        from hrma.engines.nozzle_design import NozzleDesigner
        eps = satir['expansion_ratio']
        pe = NozzleDesigner.exit_pressure_from_expansion(eps, e.gamma, e.P_c)
        g = e.gamma
        cf_mom = math.sqrt(
            2 * g ** 2 / (g - 1)
            * (2 / (g + 1)) ** ((g + 1) / (g - 1))
            * (1 - (pe / e.P_c) ** ((g - 1) / g)))
        cf = cf_mom + (pe - satir['pressure']) / e.P_c * eps
        return cf * satir['nozzle_efficiency'] * e.c_star / e.g0

    def test_kirpilmis_satir_kirpilmis_lulenin_isp_sini_yayimlar(self):
        e = _motor(chamber_pressure=5.0,
                   overrides={'chamber_pressure': 5.0, 'gamma': 1.5})
        satirlar = _sessiz(e.calculate_altitude_performance, [0, 1000, 5000])
        kirpilan = [s for s in satirlar if s['expansion_ratio_clamped']]
        assert kirpilan, 'bu köşede kırpma bekleniyordu'
        for s in kirpilan:
            assert s['specific_impulse'] == pytest.approx(
                self._gercek_isp(e, s), rel=1e-9), s['altitude']

    def test_kirpilmamis_satirda_optimum_ozdeslik_surer(self):
        e = _motor()
        satir = _sessiz(e.calculate_altitude_performance, [0])[0]
        assert not satir['expansion_ratio_clamped']
        assert satir['pressure_thrust_term'] == 0.0
        assert satir['exit_velocity'] == pytest.approx(
            satir['specific_impulse'] * G_0, rel=1e-12)

    def test_basinc_itki_terimi_yayimlanir(self):
        e = _motor(chamber_pressure=5.0,
                   overrides={'chamber_pressure': 5.0, 'gamma': 1.5})
        satir = _sessiz(e.calculate_altitude_performance, [0])[0]
        assert satir['pressure_thrust_term'] < 0.0, (
            'deniz seviyesinde ε=2,5 aşırı genişlemiştir; basınç-itki terimi '
            'negatif olmak zorunda')
        assert satir['exit_velocity'] != pytest.approx(
            satir['specific_impulse'] * G_0, rel=1e-6)


# ---------------------------------------------------------------------------
# P2B2-12 — kapak birleşimi kasa malzemesini görür
# ---------------------------------------------------------------------------
class TestKapakBirlesimiKasayiGorur:
    """Üyeler daima aluminum_6061 idi: çelik kasada yayımlanan overload
    n_L=0,861 (eşiğin altı) iken gerçeği 1,833 (eşiğin üstü)."""

    @staticmethod
    def _birlesim(malzeme):
        e = _motor(overrides={'case_material': malzeme,
                              'closure_bolt_count': 8})
        s = _sessiz(e._calculate_structural_analysis)
        return s['assembly_integrity']['closure_joint']

    @pytest.mark.parametrize('malzeme', ['steel', 'aluminum', 'titanium'])
    def test_uye_malzemesi_kasadan_gelir(self, malzeme):
        cj = self._birlesim(malzeme)
        assert cj['status'] == 'sized'
        assert cj['member_material'] == malzeme
        assert cj['member_material_source'] == 'case_material'

    def test_hukum_kasa_malzemesiyle_degisir(self):
        celik = self._birlesim('steel')
        alum = self._birlesim('aluminum')
        assert celik['overload_factor'] > 1.0 > alum['overload_factor'], (
            'çelik ve alüminyum kasa aynı aşırı yük hükmünü veriyor')
        assert celik['proof_safety_factor'] != pytest.approx(
            alum['proof_safety_factor'], rel=1e-9)

    def test_kaydi_olmayan_malzemede_boyutlandirmaz(self):
        """Fail-closed: elastisite modülü kayıtlı olmayan kompozit sargıda
        birleşim sessizce alüminyumla çözülmez."""
        cj = self._birlesim('composite')
        assert cj['status'] == 'not_sized'
        assert cj.get('member_material') is None
        assert 'elastic modulus' in cj['basis']

    def test_kullanici_uye_malzemesini_acikca_verebilir(self):
        e = _motor(overrides={'case_material': 'composite',
                              'closure_member_material': 'steel_4130',
                              'closure_bolt_count': 8})
        cj = _sessiz(e._calculate_structural_analysis)[
            'assembly_integrity']['closure_joint']
        assert cj['status'] == 'sized'
        assert cj['member_material'] == 'steel_4130'
        assert cj['member_material_source'] == 'user_supplied'
